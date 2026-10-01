#!/usr/bin/env python3
# common_usage.py — AS-IS 공통 코드 사용 행렬 (메서드·SQL statement 단위)
#
# 배경(실측): 업무(slice) 단위로 차세대 변환을 하면, 각 업무 에이전트가 자기가 쓰는 공통 메서드만 보고 판단해
#   공통 클래스를 부분 이관하거나 private 메서드로 복제했다. 그 뒤 "공통만 변환" 을 따로 돌리면 업무 코드와 어긋나
#   "업무 변환 → 공통 변환 → 다시 짝지어 검사" 라는 중복 공정이 생겼다. Mapper 도 같은 현상이 있었다.
# 해결: 업무 변환 전에 "공통의 어느 메서드·statement 를 어느 업무가 쓰는가" 를 도구로 전수 계산하고(이 파일),
#   그것을 근거로 공통 계약(common_contract.py)을 한 번 확정한 뒤, 공통은 전담 에이전트가 먼저 변환하고
#   업무 slice 는 계약을 소비만 한다. 이 행렬은 AI 판단이 아니라 정적 분석이므로 같은 입력이면 항상 같은 결과다.
#
# 사용법:
#   python tools/common_usage.py                                  # config 의 asis.source_dir + workspace slices.yaml
#   python tools/common_usage.py --source <AS-IS 루트> --slices <slices.yaml> --out <파일.yaml> [--md <파일.md>]
#   python tools/common_usage.py ... --format json                # 표준 출력
#
# 판정 규칙
#   - slice 소유 코드: slices.yaml 의 asis.packages 로 시작하는 패키지, asis.programs 에 적힌 파일명
#   - 공통 코드: 어느 slice 에도 속하지 않는 AS-IS 클래스 (+ config asis.common_packages 로 강제 지정 가능)
#   - 사용 경로: direct(업무 코드가 직접 호출) · inherited(상속받은 메서드를 m()/this.m()/super.m() 로 호출)
#                · via:<클래스#메서드/인자수>(공통 메서드가 내부에서 호출 — 전이 폐포)
#   - SQL: SqlSession/iBatis 호출의 문자열 id, Mapper 인터페이스 호출(namespace = 인터페이스 FQN), <include refid>
#   - 해석 불가(동적 SQL id 등)는 unresolved 로 남긴다. 추측으로 채우지 않는다.
#   - 범위 제외(brownfield): slices.yaml 의 unassigned.asis(이번 차수 범위 외)와 pre_pipeline(이전 차수에 이미 이관)에
#     적힌 프로그램·패키지·namespace 는 공통이 아니다. 별도 분류(out_of_scope·pre_pipeline)로 집계만 하고,
#     그 코드에서 출발하는 호출은 slice 사용으로 세지 않는다 — 그 코드만 쓰는 공통 메서드는 공통이 되지 않는다.
#   - 모듈(config project.modules 가 있을 때): 공통 항목마다 사용 slice 의 module 집합(modules)을 함께 계산한다.
#   - slice 소유 클래스의 미사용 public 메서드: 다른 클래스가 호출하는 클래스(서비스·DAO 등)인데 그 메서드만
#     아무도 부르지 않는 경우를 slice_unused_methods 로 남긴다(진입점 클래스·프레임워크 진입점은 제외).
# 의존성: pyyaml

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, config, fix_console_encoding, load_yaml, workspace  # noqa: E402
import _javasrc as js  # noqa: E402

fix_console_encoding()

# 프레임워크·컨테이너가 호출하는 진입점 — 정적 호출이 없어도 "미사용" 이 아니다
ENTRY_METHOD_ANNOTATIONS = {"Bean", "RequestMapping", "GetMapping", "PostMapping", "PutMapping", "DeleteMapping",
                            "PatchMapping", "Scheduled", "EventListener", "PostConstruct", "PreDestroy", "ExceptionHandler",
                            "InitBinder", "ModelAttribute", "Override", "KafkaListener", "JmsListener", "Test"}
ENTRY_CLASS_ANNOTATIONS = {"Controller", "RestController", "ControllerAdvice", "RestControllerAdvice", "Configuration",
                           "SpringBootApplication", "Component", "WebServlet", "WebFilter", "Aspect"}
STMT_TAGS = ("select", "insert", "update", "delete", "statement", "procedure")
NS_RE = re.compile(r"<(mapper|sqlMap)\b[^>]*\bnamespace\s*=\s*\"([^\"]+)\"")
STMT_RE = re.compile(r"<(" + "|".join(STMT_TAGS) + r")\b([^>]*)>", re.S)
SQL_FRAG_RE = re.compile(r"<sql\b([^>]*)>", re.S)
ID_RE = re.compile(r"\bid\s*=\s*\"([^\"]+)\"")
INCLUDE_RE = re.compile(r"<include\b[^>]*\brefid\s*=\s*\"([^\"]+)\"")


def rel(p, base):
    try:
        return os.path.relpath(p, base).replace(os.sep, "/")
    except ValueError:   # Windows 에서 드라이브가 다르면 상대경로가 없다
        return os.path.abspath(p).replace(os.sep, "/")


# ---------------------------------------------------------------- 수집

def scan_sources(src):
    java, xml = [], []
    for dp, dns, fns in os.walk(src):
        dns[:] = sorted(d for d in dns if d not in (".git", "target", "build", "node_modules", "test"))
        for fn in sorted(fns):
            p = os.path.join(dp, fn)
            if "/src/test/" in p.replace(os.sep, "/"):
                continue
            if fn.endswith(".java"):
                java.append(p)
            elif fn.endswith(".xml"):
                xml.append(p)
    return java, xml


def parse_mappers(xml_files, src):
    """namespace·statement·fragment 와 include 관계."""
    stmts, frags = {}, {}
    for p in xml_files:
        try:
            text = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        nm = NS_RE.search(text)
        if not nm:
            continue
        ns = nm.group(2)
        for regex, store, kind in ((STMT_RE, stmts, "stmt"), (SQL_FRAG_RE, frags, "frag")):
            for m in regex.finditer(text):
                attrs = m.group(2) if kind == "stmt" else m.group(1)
                im = ID_RE.search(attrs)
                if not im:
                    continue
                tag = m.group(1) if kind == "stmt" else "sql"
                end = text.find(f"</{tag}>", m.end())
                body = text[m.end(): end if end >= 0 else m.end()]
                sid = f"{ns}.{im.group(1)}"
                includes = []
                for inc in INCLUDE_RE.findall(body):
                    includes.append(inc if "." in inc else f"{ns}.{inc}")
                store[sid] = {"id": sid, "namespace": ns, "tag": tag, "file": rel(p, src),
                              "line": js.line_of(text, m.start()), "includes": sorted(set(includes)),
                              "sql": " ".join(body.split())}
    return stmts, frags


class Index:
    def __init__(self, classes):
        self.by_fqn = {c.fqn: c for c in classes}
        self.by_simple = {}
        for c in classes:
            self.by_simple.setdefault(c.name, []).append(c)

    def resolve_type(self, simple, ctx):
        if not simple:
            return None
        if simple in self.by_fqn:
            return simple
        for imp in ctx.imports:
            if imp.endswith("." + simple) and imp in self.by_fqn:
                return imp
        cand = f"{ctx.package}.{simple}" if ctx.package else simple
        if cand in self.by_fqn:
            return cand
        for imp in ctx.imports:
            if imp.endswith(".*") and f"{imp[:-2]}.{simple}" in self.by_fqn:
                return f"{imp[:-2]}.{simple}"
        return None

    def chain(self, fqn):
        """fqn 과 그 상위 클래스·인터페이스(이 소스 안에 있는 것만)."""
        out, todo, seen = [], [fqn], set()
        while todo:
            f = todo.pop(0)
            if f in seen or f not in self.by_fqn:
                continue
            seen.add(f)
            out.append(f)
            c = self.by_fqn[f]
            for sup in c.extends + c.implements:
                r = self.resolve_type(sup, c)
                if r:
                    todo.append(r)
        return out

    def field_type(self, c, name):
        for f in self.chain(c.fqn):
            t = self.by_fqn[f].fields.get(name)
            if t:
                return self.resolve_type(t, self.by_fqn[f])
        return None

    def find_method(self, fqn, name, arity):
        """(선언 클래스 fqn, 메서드) — 인자 수가 맞는 것 우선, 없으면 이름이 유일할 때만."""
        byname = []
        for f in self.chain(fqn):
            for m in self.by_fqn[f].methods:
                if m.name == name:
                    if m.arity == arity:
                        return f, m
                    byname.append((f, m))
        if len({(f, m.key) for f, m in byname}) == 1:
            return byname[0]
        return None


# ---------------------------------------------------------------- 범위 제외 (brownfield)

SCOPES = ("out_of_scope", "pre_pipeline")


def _as_list(v):
    if v is None or v == "":
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


def _scope_add(bucket, entry, reason_key):
    """entry(dict 또는 문자열)의 프로그램·패키지·namespace 를 bucket 에 더한다."""
    if isinstance(entry, str):
        bucket["programs"][entry] = ""
        return
    if not isinstance(entry, dict):
        return
    asis = entry.get("asis") if isinstance(entry.get("asis"), dict) else entry
    reason = str(entry.get(reason_key) or entry.get("reason") or entry.get("note") or entry.get("area") or "")
    for key, singular in (("programs", "program"), ("packages", "package"), ("namespaces", "namespace")):
        for v in _as_list(asis.get(key)) + _as_list(asis.get(singular)):
            if v:
                bucket[key][str(v)] = reason


def scope_from_slices(doc):
    """slices.yaml 문서 전체에서 범위 제외 목록을 뽑는다.

    unassigned.asis: 이번 차수 범위 외 AS-IS (문자열이면 프로그램 파일명, dict 면 program(s)·package(s)·namespace(s)·kind·reason)
    pre_pipeline   : 이전 차수에 이미 이관된 영역 ({area, asis: {packages, programs, namespaces}, tobe: [경로], module, note})
    """
    out = {s: {"programs": {}, "packages": {}, "namespaces": {}} for s in SCOPES}
    if not isinstance(doc, dict):
        return out
    un = doc.get("unassigned") if isinstance(doc.get("unassigned"), dict) else {}
    for e in un.get("asis") or []:
        _scope_add(out["out_of_scope"], e, "reason")
    for e in doc.get("pre_pipeline") or []:
        _scope_add(out["pre_pipeline"], e, "note")
    return out


def scope_is_empty(scope):
    return not scope or not any(v for b in scope.values() for v in b.values())


def class_scope(c, scope):
    """범위 제외 분류(out_of_scope|pre_pipeline) 또는 None. 파일명·패키지 접두어·(Mapper 인터페이스면) namespace 로 판정."""
    if not scope:
        return None
    for name in SCOPES:
        b = scope.get(name) or {}
        if os.path.basename(c.file) in (b.get("programs") or {}):
            return name
        if any(c.package == p or c.package.startswith(p + ".") for p in (b.get("packages") or {})):
            return name
        if c.fqn in (b.get("namespaces") or {}):
            return name
    return None


def namespace_scope(ns, scope):
    if not scope:
        return None
    for name in SCOPES:
        if ns in ((scope.get(name) or {}).get("namespaces") or {}):
            return name
    return None


# ---------------------------------------------------------------- 분석

def call_edges(classes, idx, stmts):
    """메서드별 호출 간선. (fqn, 메서드 key) → {"methods": [(대상 fqn, key, 경로, 위치)], "sql": [(id, 위치)], "unresolved": [...]}

    common_usage(업무 간)와 slice_units(slice 안 unit 간)가 같은 간선을 쓴다 — 호출 해석 규칙이 하나다.
    """
    mapper_ifaces = {c.fqn for c in classes if c.kind == "interface" and c.fqn in {v["namespace"] for v in stmts.values()}}

    edges = {}
    for c in classes:
        for m in c.methods:
            calls, local_types = js.body_calls(c, m)
            out = {"methods": [], "sql": [], "unresolved": []}
            for kind, recv, name, arity, pos, extra in calls:
                target = None
                if kind in ("bare", "this"):
                    target = idx.find_method(c.fqn, name, arity)
                    how = "self"
                elif kind == "super":
                    for sup in c.extends:
                        r = idx.resolve_type(sup, c)
                        if r:
                            target = idx.find_method(r, name, arity)
                    how = "self"
                else:
                    t = local_types.get(recv)
                    tf = idx.resolve_type(t, c) if t else idx.field_type(c, recv)
                    if tf:
                        target = idx.find_method(tf, name, arity)
                        if target is None and tf in mapper_ifaces:
                            out["sql"].append((f"{tf}.{name}", pos))
                    elif recv[:1].isupper():
                        sf = idx.resolve_type(recv, c)
                        if sf:
                            target = idx.find_method(sf, name, arity)
                    how = "qual"
                    if extra is not None and name in js.SQL_METHODS and target is None:
                        lit = re.fullmatch(r"\"([^\"]+)\"", extra.strip())
                        if lit:
                            out["sql"].append((lit.group(1), pos))
                        else:
                            out["unresolved"].append({"file": c.file, "line": js.line_of(c.text, pos),
                                                      "call": f"{recv}.{name}({extra.strip()})"})
                if target:
                    decl_fqn, decl_m = target
                    if decl_fqn in mapper_ifaces:
                        # Mapper 인터페이스 메서드 = namespace(인터페이스 FQN).메서드명 statement
                        out["sql"].append((f"{decl_fqn}.{decl_m.name}", pos))
                    inherited = how == "self" and decl_fqn != c.fqn
                    out["methods"].append((decl_fqn, decl_m.key, "inherited" if inherited else "direct", pos))
            edges[(c.fqn, m.key)] = out
    return edges, mapper_ifaces


def implementations(classes, idx):
    """(상위 타입 fqn, 메서드 key) → [(구현 클래스 fqn, 메서드 key)]. 인터페이스·추상 메서드 호출을 구현체로 잇는다.
    common_usage(업무 간)와 slice_units(unit 간)가 같은 연결을 쓴다."""
    out = {}
    for c in classes:
        if c.kind == "interface":
            continue
        for anc in idx.chain(c.fqn)[1:]:
            base = idx.by_fqn.get(anc)
            if base is None:
                continue
            keys = {m.key for m in base.methods}
            for m in c.methods:
                if m.body_start is not None and m.key in keys:
                    out.setdefault((anc, m.key), []).append((c.fqn, m.key))
    return out


def analyze(src, slices, common_packages=None, scope=None, modules=None):
    """사용 행렬.

    scope  : scope_from_slices() 결과 — 범위 외·이전 차수 이관 코드를 공통 판정에서 뺀다 (없으면 종전 동작)
    modules: config project.modules — 있으면 항목마다 사용 slice 의 module 집합을 계산한다 (없으면 종전 동작)
    """
    use_scope = not scope_is_empty(scope)
    slice_module = {s["id"]: s.get("module") for s in slices} if modules else {}
    java_files, xml_files = scan_sources(src)
    classes = []
    for p in java_files:
        try:
            text = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        classes.extend(js.parse_file(p, text))
    idx = Index(classes)
    stmts, frags = parse_mappers(xml_files, src)

    # 소유 판정
    owner = {c.fqn: class_owner(c, slices, common_packages) for c in classes}
    excl = {}           # fqn → out_of_scope|pre_pipeline (slice 가 소유하지 않는 클래스만)
    if use_scope:
        for c in classes:
            if owner[c.fqn] is None:
                sc = class_scope(c, scope)
                if sc:
                    excl[c.fqn] = sc
    ns_owner = {}
    for s in slices:
        for ns in (s.get("asis") or {}).get("namespaces") or []:
            ns_owner[ns] = s["id"]
    edges, mapper_ifaces = call_edges(classes, idx, stmts)
    impls = implementations(classes, idx)

    # slice 루트에서 전이 폐포
    usage = {}          # (fqn, key) → {slice: 사유}
    class_use = {}      # fqn → {slice: 사유}
    stmt_use = {}       # sql id → {slice: 사유}
    cross = []
    unresolved = []
    missing_sql = {}
    excl_use = {}       # 범위 제외 클래스 fqn → {slice: 사유} (slice 가 범위 외·이전 차수 코드를 호출)
    ex_usage, ex_class_use, ex_stmt_use = {}, {}, {}   # 범위 제외 코드가 쓰는 공통 (집계만)

    def closure(group, is_slice, root_fqns, u_meth, u_cls, u_stmt):
        """group(slice id 또는 범위 제외 분류)의 루트 클래스에서 공통으로의 전이 폐포."""
        todo = []
        for c in classes:
            if c.fqn not in root_fqns:
                continue
            for sup in c.extends:
                r = idx.resolve_type(sup, c)
                if r and owner.get(r) is None and r not in excl:
                    u_cls.setdefault(r, {}).setdefault(group, f"extends:{c.name}")
            for m in c.methods:
                todo.append((c.fqn, m.key, None))
        seen = set()
        while todo:
            fqn, key, via = todo.pop()
            if (fqn, key) in seen:
                continue
            seen.add((fqn, key))
            e = edges.get((fqn, key), {"methods": [], "sql": [], "unresolved": []})
            src_is_root = fqn in root_fqns
            # 인터페이스(상위 타입) 메서드 호출은 실제로는 구현체 메서드가 실행된다 — 구현체까지 따라가야
            # 구현이 쓰는 statement 가 '미사용' 으로 빠지지 않는다(실측: 공통 서비스 구현 SQL 26건 누락)
            targets = [(tf, tk, how) for tf, tk, how, _pos in e["methods"]]
            targets += [(i_f, i_k, "dispatch") for tf, tk, _h, _p in e["methods"] for i_f, i_k in impls.get((tf, tk), [])]
            for tf, tk, how in targets:
                towner = owner.get(tf)
                if tf in excl:
                    # 범위 외·이전 차수 이관 코드 — 공통이 아니므로 더 따라가지 않는다
                    if is_slice and tf not in root_fqns:
                        excl_use.setdefault(tf, {}).setdefault(group, how if src_is_root else f"via:{short(fqn)}#{key}")
                    continue
                if towner is None:
                    reason = how if src_is_root else f"via:{short(fqn)}#{key}"
                    u_meth.setdefault((tf, tk), {}).setdefault(group, reason)
                    u_cls.setdefault(tf, {}).setdefault(group, "uses")
                    todo.append((tf, tk, reason))
                elif is_slice and towner != group:
                    cross.append({"from": group, "to": towner, "what": f"{short(tf)}#{tk}", "kind": "method"})
            for sql_id, _pos in e["sql"]:
                reason = "direct" if src_is_root else f"via:{short(fqn)}#{key}"
                if sql_id not in stmts:
                    if is_slice:
                        missing_sql.setdefault(sql_id, set()).add(group)
                    continue
                u_stmt.setdefault(sql_id, {}).setdefault(group, reason)
                so = ns_owner.get(stmts[sql_id]["namespace"])
                if is_slice and so and so != group:
                    cross.append({"from": group, "to": so, "what": sql_id, "kind": "statement"})
            if is_slice:
                for u in e["unresolved"]:
                    unresolved.append(dict(u, slice=group, file=rel(u["file"], src)))

    for s in slices:
        sid = s["id"]
        closure(sid, True, {c.fqn for c in classes if owner[c.fqn] == sid}, usage, class_use, stmt_use)
    for sc in SCOPES:
        roots = {f for f, v in excl.items() if v == sc}
        if roots:
            closure(sc, False, roots, ex_usage, ex_class_use, ex_stmt_use)

    # 동적 id 는 도달하지 않은 메서드에도 있을 수 있다 — 모두 기록(도달 slice 없음)
    reached = {(u["file"], u["line"]) for u in unresolved}
    for c in classes:
        for m in c.methods:
            for u in edges[(c.fqn, m.key)]["unresolved"]:
                k = (rel(u["file"], src), u["line"])
                if k not in reached:
                    unresolved.append(dict(u, slice=None, file=k[0]))

    # fragment 사용: statement → include 전이
    frag_use = {}
    def walk_frag(fid, sid, reason, depth=0):
        if fid not in frags or depth > 20:
            return
        frag_use.setdefault(fid, {}).setdefault(sid, reason)
        for inc in frags[fid]["includes"]:
            walk_frag(inc, sid, f"via:{fid}", depth + 1)
    for st_id, users in stmt_use.items():
        for sid in users:
            for inc in stmts[st_id]["includes"]:
                walk_frag(inc, sid, f"via:{st_id}")

    # 결과 조립 (정렬 고정)
    def mods(used):
        return sorted({slice_module[x] for x in used if slice_module.get(x)})

    common = []
    for c in sorted(classes, key=lambda x: x.fqn):
        if owner[c.fqn] is not None or c.fqn in excl:
            continue
        methods = []
        for m in sorted(c.methods, key=lambda x: (x.name, x.arity)):
            used = usage.get((c.fqn, m.key), {})
            calls = sorted({f"{short(tf)}#{tk}" if tf != c.fqn else tk
                            for tf, tk, _h, _p in edges[(c.fqn, m.key)]["methods"] if owner.get(tf) is None})
            sqls = sorted({s for s, _p in edges[(c.fqn, m.key)]["sql"]})
            entry = entry_reason(c, m)
            row = {"id": m.key, "signature": m.sig, "line": js.line_of(c.text, m.start),
                   "used_by": dict(sorted(used.items())), "calls": calls, "sql": sqls, "entry": entry}
            if use_scope:
                row["excluded_use"] = dict(sorted(ex_usage.get((c.fqn, m.key), {}).items()))
            if modules:
                row["modules"] = mods(used)
            methods.append(row)
        crow = {"class": c.fqn, "file": rel(c.file, src), "kind": c.kind,
                "extends": c.extends, "used_by": dict(sorted(class_use.get(c.fqn, {}).items())),
                "methods": methods}
        if use_scope:
            crow["excluded_use"] = dict(sorted(ex_class_use.get(c.fqn, {}).items()))
        if modules:
            crow["modules"] = mods(class_use.get(c.fqn, {}))
        common.append(crow)

    def stmt_rows(store, use, ex_use):
        rows = []
        for sid in sorted(store):
            st = store[sid]
            row = {"id": sid, "tag": st["tag"], "file": st["file"], "line": st["line"],
                   "namespace_owner": ns_owner.get(st["namespace"]), "includes": st["includes"],
                   "used_by": dict(sorted(use.get(sid, {}).items()))}
            if use_scope:
                row["scope"] = namespace_scope(st["namespace"], scope)
                row["excluded_use"] = dict(sorted(ex_use.get(sid, {}).items()))
            if modules:
                row["modules"] = mods(use.get(sid, {}))
            rows.append(row)
        return rows

    # 범위 제외 코드가 쓰는 fragment (집계만)
    ex_frag_use = {}
    for st_id, users in ex_stmt_use.items():
        for grp in users:
            for inc in stmts[st_id]["includes"]:
                if inc in frags:
                    ex_frag_use.setdefault(inc, {}).setdefault(grp, f"via:{st_id}")

    cross_u = sorted({json.dumps(x, sort_keys=True, ensure_ascii=False) for x in cross})
    result = {
        "schema": 1,
        "generated_by": "tools/common_usage.py",
        "slices": [s["id"] for s in slices],
        "common_classes": common,
        "statements": stmt_rows(stmts, stmt_use, ex_stmt_use),
        "fragments": stmt_rows(frags, frag_use, ex_frag_use),
        "cross_slice": [json.loads(x) for x in cross_u],
        "missing_sql": [{"id": k, "used_by": sorted(v)} for k, v in sorted(missing_sql.items())],
        "unresolved": sorted(unresolved, key=lambda u: (u["file"], u["line"], u["call"])),
        "slice_unused_methods": slice_unused_methods(classes, idx, owner, edges, src),
    }
    if use_scope:
        result["excluded_classes"] = [
            {"class": c.fqn, "file": rel(c.file, src), "scope": excl[c.fqn],
             "used_by": dict(sorted(excl_use.get(c.fqn, {}).items()))}
            for c in sorted(classes, key=lambda x: x.fqn) if c.fqn in excl]
    if modules:
        result["modules"] = list(modules)
        result["slice_modules"] = {k: v for k, v in slice_module.items()}
    result["summary"] = summarize(result)
    return result


def slice_unused_methods(classes, idx, owner, edges, src):
    """slice 소유 클래스의 미사용 public 메서드.

    다른 클래스가 호출하는 클래스(서비스·DAO 등 — 피호출 클래스)인데 그 메서드는 아무도 부르지 않는 경우만 본다.
    아무도 부르지 않는 클래스(컨트롤러·액션 등 진입점 클래스)와 프레임워크 진입점 메서드는 판단 근거가 없어 뺀다.
    상위 타입(인터페이스)의 같은 메서드가 호출되면 사용으로 본다.
    """
    incoming, callers = set(), {}
    for (fqn, _key), e in edges.items():
        for tf, tk, _h, _p in e["methods"]:
            incoming.add((tf, tk))
            callers.setdefault(tf, set()).add(fqn)
    out = []
    for c in sorted(classes, key=lambda x: x.fqn):
        o = owner.get(c.fqn)
        if o is None or c.kind != "class":
            continue
        chain = idx.chain(c.fqn)
        # 피호출 클래스: 다른 클래스가 이 클래스(또는 이 클래스가 구현한 인터페이스)를 호출한다.
        # 상위 클래스 호출은 세지 않는다 — 공통 상위 클래스는 모든 하위 업무 클래스가 부른다.
        targets = [c.fqn] + [f for f in chain[1:] if idx.by_fqn[f].kind == "interface"]
        if not any(caller != c.fqn for t in targets for caller in callers.get(t, ())):
            continue
        for m in sorted(c.methods, key=lambda x: (x.name, x.arity)):
            if m.is_ctor or m.body_start is None or "public" not in m.sig.split("(")[0]:
                continue
            if entry_reason(c, m):
                continue
            if any((f, m.key) in incoming for f in chain):
                continue
            out.append({"slice": o, "class": c.fqn, "method": m.key, "signature": m.sig,
                        "file": rel(c.file, src), "line": js.line_of(c.text, m.start)})
    return out


def class_owner(c, slices, common_packages=None):
    """클래스의 소유 slice id. asis.packages 접두어 또는 asis.programs 파일명으로 판정하고, 어디에도 없으면 None(공통)."""
    o = None
    for s in slices:
        asis = s.get("asis") or {}
        if any(c.package == p or c.package.startswith(p + ".") for p in asis.get("packages") or []):
            o = s["id"]
        if os.path.basename(c.file) in (asis.get("programs") or []):
            o = s["id"]
    if common_packages and any(c.package == p or c.package.startswith(p + ".") for p in common_packages):
        o = None
    return o


def entry_reason(c, m):
    """프레임워크 진입점이면 그 근거(어노테이션·main·생성자), 아니면 None."""
    hit = sorted(set(m.annotations) & ENTRY_METHOD_ANNOTATIONS)
    if hit:
        return "@" + ",@".join(hit)
    if m.name == "main" and m.is_static:
        return "main"
    if m.is_ctor:
        return "constructor"
    # 접근자는 바인딩·ORM·직렬화가 리플렉션으로 호출한다 — 정적 호출이 없다고 폐기 후보가 되면 안 된다
    if re.match(r"^(get|set|is)[A-Z]", m.name) and m.body_start is not None and c.fields:
        return "accessor"
    ch = sorted(set(c.annotations) & ENTRY_CLASS_ANNOTATIONS)
    if ch and m.body_start is not None and "public" in m.sig.split("(")[0]:
        return "class@" + ",@".join(ch)
    return None


def short(fqn):
    return fqn.rsplit(".", 1)[-1]


def summarize(r):
    methods = [m for c in r["common_classes"] for m in c["methods"] if not m["id"].startswith("<init>")]
    by_n = {"shared": 0, "single": 0, "unused": 0, "entry": 0}
    for m in methods:
        n = len(m["used_by"])
        by_n["shared" if n >= 2 else "single" if n == 1 else "entry" if m.get("entry") else "unused"] += 1
    st = {"shared": 0, "single": 0, "unused": 0}
    scoped = {}
    for s in r["statements"]:
        if s.get("scope"):
            scoped[s["scope"]] = scoped.get(s["scope"], 0) + 1
            continue
        n = len(s["used_by"])
        st["shared" if n >= 2 else "single" if n == 1 else "unused"] += 1
    extra = {"slice_unused_methods": len(r.get("slice_unused_methods") or [])}
    if "excluded_classes" in r:
        for sc in SCOPES:
            extra[f"{sc}_classes"] = sum(1 for c in r["excluded_classes"] if c["scope"] == sc)
            extra[f"statements_{sc}"] = scoped.get(sc, 0)
        extra["excluded_used_by_slices"] = sum(1 for c in r["excluded_classes"] if c["used_by"])
    if "modules" in r:
        extra["methods_multi_module"] = sum(1 for m in methods if len(m.get("modules") or []) >= 2)
        extra["statements_multi_module"] = sum(1 for s in r["statements"] if len(s.get("modules") or []) >= 2)
        extra["slices_without_module"] = sorted(k for k, v in (r.get("slice_modules") or {}).items() if not v)
    return {"common_classes": len(r["common_classes"]), "common_methods": len(methods),
            "methods_shared": by_n["shared"], "methods_single_slice": by_n["single"], "methods_unused": by_n["unused"],
            "methods_entry_only": by_n["entry"],
            "statements": len(r["statements"]), "statements_shared": st["shared"],
            "statements_single_slice": st["single"], "statements_unused": st["unused"],
            "cross_slice": len(r["cross_slice"]), "unresolved": len(r["unresolved"]),
            "missing_sql": len(r["missing_sql"]), **extra}


def to_markdown(r):
    lines = ["# 공통 코드 사용 행렬 (COMMON_USAGE)", "",
             "> `tools/common_usage.py` 가 AS-IS 정적 분석으로 생성. 손으로 고치지 않는다(다시 생성한다).", ""]
    s = r["summary"]
    lines += ["## 요약", "", "| 항목 | 값 |", "|---|---|"] + [f"| {k} | {v} |" for k, v in s.items()] + [""]
    sl = r["slices"]
    lines += ["## 공통 메서드 × 업무", "", "| 클래스 | 메서드 | " + " | ".join(sl) + " | 진입점 | 내부 호출 | SQL |",
              "|---|---|" + "---|" * len(sl) + "---|---|---|"]
    for c in r["common_classes"]:
        for m in c["methods"]:
            cells = [m["used_by"].get(x, "") for x in sl]
            lines.append(f"| {c['class'].rsplit('.', 1)[-1]} | {m['id']} | " + " | ".join(cells)
                         + f" | {m.get('entry') or ''} | {', '.join(m['calls'])} | {', '.join(m['sql'])} |")
    lines += ["", "## SQL statement × 업무", "", "| statement | 소유 namespace | " + " | ".join(sl) + " | include |",
              "|---|---|" + "---|" * len(sl) + "---|"]
    for st in r["statements"] + r["fragments"]:
        cells = [st["used_by"].get(x, "") for x in sl]
        lines.append(f"| {st['id']} | {st['namespace_owner'] or '(공통)'} | " + " | ".join(cells)
                     + f" | {', '.join(st['includes'])} |")
    if r.get("excluded_classes"):
        lines += ["", "## 범위 제외 (공통 아님 — 집계만)", "",
                  "> unassigned.asis(이번 차수 범위 외)·pre_pipeline(이전 차수 이관) 코드. slice 가 호출하면 사용 slice 에 표시된다.", "",
                  "| 클래스 | 분류 | 호출한 slice |", "|---|---|---|"]
        lines += [f"| {c['class']} | {c['scope']} | {', '.join(c['used_by']) or '-'} |" for c in r["excluded_classes"]]
    if r.get("slice_unused_methods"):
        lines += ["", "## 업무 소유 클래스의 미사용 public 메서드 (사람 판단)", "", "| slice | 클래스 | 메서드 | 위치 |", "|---|---|---|---|"]
        lines += [f"| {u['slice']} | {short(u['class'])} | {u['method']} | {u['file']}:{u['line']} |" for u in r["slice_unused_methods"]]
    if r["cross_slice"]:
        lines += ["", "## 업무 간 교차 사용 (slice 경계 재검토 대상)", "", "| 사용 slice | 소유 slice | 대상 | 종류 |", "|---|---|---|---|"]
        lines += [f"| {x['from']} | {x['to']} | {x['what']} | {x['kind']} |" for x in r["cross_slice"]]
    if r["unresolved"] or r["missing_sql"]:
        lines += ["", "## 해석 불가 (사람 확인 필요)", ""]
        lines += [f"- 동적 호출 `{u['call']}` — {u['file']}:{u['line']} (도달 slice: {u['slice'] or '없음'})" for u in r["unresolved"]]
        lines += [f"- 정의 없는 SQL id `{m['id']}` — 사용: {', '.join(m['used_by'])}" for m in r["missing_sql"]]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="AS-IS 공통 코드 사용 행렬 (메서드·statement 단위)")
    ap.add_argument("--source", help="AS-IS 소스 루트 (기본: config asis.source_dir)")
    ap.add_argument("--slices", help="slices.yaml (기본: workspace/<project>/slices/slices.yaml)")
    ap.add_argument("--out", help="YAML 출력 경로 (기본: workspace/<project>/knowledge/COMMON_USAGE.yaml)")
    ap.add_argument("--md", help="사람용 Markdown 출력 경로 (기본: --out 과 같은 이름의 .md)")
    ap.add_argument("--format", choices=["yaml", "json"], help="파일 대신 표준 출력으로")
    args = ap.parse_args(argv)
    cfg = config()
    src = args.source or (cfg.get("asis") or {}).get("source_dir")
    if src and not os.path.isabs(src):
        src = os.path.normpath(os.path.join(ROOT, src))
    if not src or not os.path.isdir(src):
        print(f"[common_usage] AS-IS 소스 디렉토리가 없다: {src}", file=sys.stderr)
        return 2
    sp = args.slices or os.path.join(workspace(), "slices", "slices.yaml")
    try:
        doc = load_yaml(sp)
    except OSError:
        print(f"[common_usage] slices.yaml 을 읽지 못했다: {sp}", file=sys.stderr)
        return 2
    slices = [s for s in (doc.get("slices") or []) if isinstance(s, dict) and s.get("id")]
    modules = (cfg.get("project") or {}).get("modules") or None
    result = analyze(src, slices, (cfg.get("asis") or {}).get("common_packages"),
                     scope=scope_from_slices(doc), modules=modules)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    import yaml
    if args.format == "yaml":
        print(yaml.safe_dump(result, allow_unicode=True, sort_keys=False))
        return 0
    out = args.out or os.path.join(workspace(), "knowledge", "COMMON_USAGE.yaml")
    from _common import atomic_write_text
    atomic_write_text(out, yaml.safe_dump(result, allow_unicode=True, sort_keys=False))
    md = args.md or os.path.splitext(out)[0] + ".md"
    atomic_write_text(md, to_markdown(result))
    s = result["summary"]
    print(f"공통 클래스 {s['common_classes']} · 공통 메서드 {s['common_methods']} "
          f"(공유 {s['methods_shared']} / 단일 업무 {s['methods_single_slice']} / 프레임워크 진입점 {s['methods_entry_only']}"
          f" / 미사용 {s['methods_unused']})")
    print(f"statement {s['statements']} (공유 {s['statements_shared']} / 단일 {s['statements_single_slice']} / 미사용 {s['statements_unused']})"
          f" · 업무 간 교차 {s['cross_slice']} · 해석 불가 {s['unresolved']} · 정의 없는 SQL {s['missing_sql']}")
    if "out_of_scope_classes" in s:
        print(f"범위 제외(공통 아님): 범위 외 클래스 {s['out_of_scope_classes']} · statement {s['statements_out_of_scope']}"
              f" / 이전 차수 이관 클래스 {s['pre_pipeline_classes']} · statement {s['statements_pre_pipeline']}")
    if "methods_multi_module" in s:
        print(f"여러 모듈이 쓰는 공통: 메서드 {s['methods_multi_module']} · statement {s['statements_multi_module']}"
              + (f" · module 없는 slice: {', '.join(s['slices_without_module'])}" if s["slices_without_module"] else ""))
    print(f"업무 소유 클래스의 미사용 public 메서드 {s['slice_unused_methods']}")
    print(f"→ {out}\n→ {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
