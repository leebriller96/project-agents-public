#!/usr/bin/env python3
# slice_units.py — 큰 slice 를 업무 프로세스(상태 전이) 기준 unit 으로 나누고, 그 분할이 안전한지 기계로 판정한다.
#
# 배경: slice 는 업무 경계로 나누지만 크기가 고르지 않다. '이벤트' 는 API 1~2개인데 '보험금 청구' 는 접수·심사·
#   지급·부지급·이의·조회가 얽힌 작은 프로젝트급이다. 에이전트 한 번이 정확히 다룰 수 있는 양을 넘으면
#   (1) 뒤로 갈수록 AS-IS 원문을 다시 읽지 않아 분기·statement 가 빠지고 (2) 비슷한 분기를 하나로 합치며
#   (3) reviewer·spec 도 대표 경로만 본다 — 전부 빌드·단위테스트는 통과하므로 게이트에 드러나지 않는다.
# 해결: 크기를 측정해 기준을 넘는 slice 만 unit 으로 나눈다(필요할 때만). slice 는 계약·소유·검증의 단위로 남고
#   unit 은 에이전트 1회 실행의 단위다. 나누는 기준은 업무 프로세스의 상태 전이이고, 여러 unit 이 함께 쓰는 코드는
#   먼저 core unit 에서 변환한다. 공용 유틸·상위 클래스·DAO 같은 공유 클래스는 클래스 통째로 core 에 둔다(공통 계약과
#   같은 구조를 slice 안에 적용 — 공통 클래스 분해 방지). 단 진입점 클래스(컨트롤러)와 업무 서비스 구현체는 메서드 단위로
#   배정한다 — 수천 줄 컨트롤러를 통째로 core 에 올리면 core 가 에이전트 한도를 넘고 다른 unit 이 비기 때문이다(아래 split_kind).
#   이음매(unit 사이 상태 인계)는 흐름(flow) 테스트로, 누락은 AS-IS 전수 배정으로 막는다.
#
# 행렬(knowledge/units/<slice>.yaml, schema 2)의 assignment.<unit>:
#   programs   — 클래스 통째로 배정된 파일명 (OrderUtil.java)
#   methods    — 메서드 단위로 배정된 항목 (OrderController.java#insert, 오버로드는 #insert/2, 선언부·필드·생성자는 #<decl>)
#   statements — SQL statement·fragment id
#   methods 키가 없는 옛 행렬(schema 1)도 그대로 읽는다.
#
# 사용법:
#   python tools/slice_units.py measure [--source <AS-IS>] [--slices <slices.yaml>] [--format json]
#   python tools/slice_units.py matrix --slice <id> [--source ...] [--out <yaml>] [--format json]
#   python tools/slice_units.py validate [--slice <id>] [--source ...] [--format json]     # FAIL 이 있으면 종료 코드 1
#   python tools/slice_units.py order --slice <id> [--format json]
#
# 판정은 정적 분석과 slices.yaml 선언만으로 하며 같은 입력이면 항상 같은 결과다.
# 의존성: pyyaml

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, atomic_write_text, config, fix_console_encoding, load_yaml, workspace  # noqa: E402

fix_console_encoding()

UNIT_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
FLOW_ID_RE = re.compile(r"^FLOW-[A-Za-z0-9-]+$")
TRANSITION_RE = re.compile(r"^\s*(\S.*?)\s*->\s*(\S.*?)\s*$")
UNIT_KINDS = ("core", "step", "query")

# 기준값은 초기 추정치다. 실제로 돌려 본 결과로 config/project.yaml 의 slicing 에서 조정하고 근거를 LESSONS 에 남긴다.
DEFAULTS = {
    "size": {"asis_tokens": 60000, "apis": 20, "screens": 10, "statements": 60, "methods": 200, "transitions": 8},
    "unit_max": {"asis_tokens": 40000, "apis": 12, "screens": 6, "statements": 40},
    "merge_below": {"asis_tokens": 8000, "apis": 3, "screens": 2},
    "chars_per_token": 4,
}
METRIC_LABEL = {"asis_tokens": "AS-IS 입력 토큰 추정", "apis": "API", "screens": "화면", "statements": "SQL statement",
                "methods": "메서드", "transitions": "상태 전이", "programs": "프로그램"}


def finding(severity, field, message, action=""):
    return {"severity": severity, "field": field, "message": message, "action": action}


def thresholds(cfg=None):
    cfg = cfg if cfg is not None else config()
    user = (cfg.get("slicing") or {}) if isinstance(cfg, dict) else {}
    out = {}
    for k, v in DEFAULTS.items():
        if isinstance(v, dict):
            merged = dict(v)
            merged.update({a: b for a, b in (user.get(k) or {}).items() if isinstance(b, (int, float))})
            out[k] = merged
        else:
            out[k] = user.get(k) if isinstance(user.get(k), (int, float)) and user.get(k) > 0 else v
    return out


def slices_path(path=None):
    return path or os.path.join(workspace(), "slices", "slices.yaml")


def load_slices(path=None):
    p = slices_path(path)
    data = load_yaml(p)
    return [s for s in (data.get("slices") or []) if isinstance(s, dict) and s.get("id")], p


def find_slice(slices, sid):
    for s in slices:
        if s.get("id") == sid:
            return s
    return None


def source_dir(arg=None):
    src = arg or (config().get("asis") or {}).get("source_dir")
    if src and not os.path.isabs(src):
        src = os.path.normpath(os.path.join(ROOT, src))
    return src if src and os.path.isdir(src) else None


def units_of(entry):
    return [u for u in (entry.get("units") or []) if isinstance(u, dict)]


def non_core(units):
    return [u for u in units if u.get("kind") != "core"]


def core_unit(units):
    for u in units:
        if u.get("kind") == "core":
            return u
    return None


def parse_transition(t):
    m = TRANSITION_RE.match(str(t))
    return (m.group(1), m.group(2)) if m else None


def norm_transition(t):
    p = parse_transition(t)
    return f"{p[0]} -> {p[1]}" if p else str(t).strip()


# ---------------------------------------------------------------- AS-IS 해석

# 메서드 단위 배정 대상 (그 밖은 전부 클래스 통째)
#   - 진입점 클래스(컨트롤러): @Controller·@RestController·@RequestMapping 이 붙었거나 이름이 *Controller·*Action
#   - 업무 서비스 구현체: 이름이 *ServiceImpl 이거나 @Service
# 실측: 레거시의 진입점·서비스 구현체는 한 클래스에 수천 줄로 모든 단계의 메서드가 몰려 있어, 클래스 통째로 배정하면
#   모든 unit 이 그 클래스를 함께 써 전부 core 로 올라가고(core 가 unit 상한의 수 배) step·query unit 은 빈 껍데기가 됐다.
#   이 두 종류는 메서드가 곧 업무 단계의 경계이므로 메서드를 unit 에 나눠도 "클래스 분해" 가 아니다.
# 비대상(클래스 통째 유지): 공용 유틸·상위 클래스(slice 안 다른 클래스가 상속)·추상 클래스·인터페이스·DAO·Mapper·도우미.
#   pipeline-core §17 의 "공통 클래스 분해 금지" 는 이쪽에 대한 것이다 — 여러 unit 이 쓰면 core 에 클래스 통째로 둔다.
ENTRY_CLASS_ANNOTATIONS = {"Controller", "RestController", "RequestMapping"}
SERVICE_CLASS_ANNOTATIONS = {"Service"}
DECL = "<decl>"          # 메서드 단위 배정 클래스의 선언부·필드·생성자·초기화 블록 (행렬 id: File.java#<decl>)
TOP_N = 5                # 상한 초과 unit 에 보여 줄 큰 항목 수


class Source:
    """AS-IS 소스를 한 번만 파싱해 측정·행렬이 함께 쓴다."""

    def __init__(self, src, slices, common_packages=None):
        import _javasrc as js
        import common_usage as cu
        self.src, self.cu, self.js = src, cu, js
        java, xml = cu.scan_sources(src)
        self.classes = []
        self.file_text = {}
        for p in java:
            try:
                text = open(p, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            self.file_text[p] = text
            self.classes.extend(js.parse_file(p, text))
        self.stmts, self.frags = cu.parse_mappers(xml, src)
        self.common_packages = common_packages
        self.owner = {c.fqn: cu.class_owner(c, slices, common_packages) for c in self.classes}
        self.ns_owner = {}
        for s in slices:
            for ns in (s.get("asis") or {}).get("namespaces") or []:
                self.ns_owner[ns] = s["id"]
        self.idx = cu.Index(self.classes)
        self.edges, self.mapper_ifaces = cu.call_edges(self.classes, self.idx, self.stmts)
        self.impls = self._implementations()
        self._sizes = {}

    def slice_classes(self, sid):
        return [c for c in self.classes if self.owner.get(c.fqn) == sid]

    def slice_statements(self, sid):
        return {k: v for k, v in self.stmts.items() if self.ns_owner.get(v["namespace"]) == sid}

    def slice_fragments(self, sid):
        return {k: v for k, v in self.frags.items() if self.ns_owner.get(v["namespace"]) == sid}

    def _implementations(self):
        """(상위 타입 fqn, 메서드 key) → 구현 메서드 목록 — common_usage.implementations 와 같은 규칙을 쓴다."""
        return self.cu.implementations(self.classes, self.idx)

    def callees(self, node):
        e = self.edges.get(node)
        if not e:
            return []
        out = []
        for tf, tk, _how, _pos in e["methods"]:
            out.append((tf, tk))
            out.extend(self.impls.get((tf, tk), []))
        return out

    def parents(self, sid):
        """slice 안에서 다른 slice 클래스가 상속하는 클래스 (상위 클래스 = 클래스 통째)."""
        out = set()
        for c in self.slice_classes(sid):
            for sup in c.extends:
                r = self.idx.resolve_type(sup, c)
                if r:
                    out.add(r)
        return out

    def item_sizes(self, sid):
        """배정 항목 id → 문자 수. 파일명(클래스 통째)·File.java#메서드·File.java#<decl>."""
        if sid in self._sizes:
            return self._sizes[sid]
        out = {}
        firsts = {}
        for c in self.slice_classes(sid):
            firsts.setdefault(c.file, c)
            if c.head_start < firsts[c.file].head_start:
                firsts[c.file] = c
        for c in self.slice_classes(sid):
            b = os.path.basename(c.file)
            out[b] = len(self.file_text.get(c.file, c.text or ""))
            ids = method_ids(c)
            spent = 0
            for m in c.methods:
                if m.is_ctor:
                    continue
                s, e = m.span
                out[ids[m.key]] = e - s
                spent += e - s
            s, e = c.span
            # 선언부 = 클래스 범위에서 메서드 본문을 뺀 나머지(필드·생성자·어노테이션) + 파일 머리(package·import)는 첫 클래스에
            out[f"{b}#{DECL}"] = max(0, (e - s) - spent) + (s if firsts[c.file] is c else 0)
        self._sizes[sid] = out
        return out


def split_kind(c, parents=()):
    """메서드 단위 배정 대상이면 'entry'(진입점) 또는 'service'(업무 서비스 구현체), 아니면 None(클래스 통째).
    적용 대상·비대상 규칙은 이 절 머리 주석을 따른다."""
    if c.kind != "class" or c.fqn in parents:
        return None
    header = c.masked[c.head_start:c.body_open] if c.masked else ""
    if re.search(r"(?<![\w$])abstract(?![\w$])", header):
        return None
    if set(c.annotations) & ENTRY_CLASS_ANNOTATIONS or c.name.endswith(("Controller", "Action")):
        return "entry"
    if c.name.endswith("ServiceImpl") or set(c.annotations) & SERVICE_CLASS_ANNOTATIONS:
        return "service"
    return None


def method_ids(c):
    """메서드 key(name/인자수) → 행렬 id. 오버로드가 없으면 File.java#name, 있으면 File.java#name/인자수."""
    b = os.path.basename(c.file)
    names = {}
    for m in c.methods:
        if not m.is_ctor:
            names[m.name] = names.get(m.name, 0) + 1
    return {m.key: (f"{b}#{m.name}" if names[m.name] == 1 else f"{b}#{m.key}") for m in c.methods if not m.is_ctor}


def norm_item(x):
    """배정 항목 비교용 정규화 — 'OrderController.java#insert' 와 'OrderController#insert' 를 같게 본다."""
    x = str(x).strip()
    if "#" in x:
        cls, m = x.split("#", 1)
        cls = cls[:-5] if cls.endswith(".java") else cls
        return f"{cls}#{m}"
    return x


def norm_api(p):
    """요청 경로 비교용 정규화 → (HTTP 메서드 또는 None, 경로).
    'POST ' 같은 메서드 접두어 제거, .do 확장자 무시, /api 접두어 무시(TO-BE), 경로 변수 이름 무시, 끝 '/' 무시."""
    p = str(p).strip()
    http = None
    m = re.match(r"^([A-Za-z]+)\s+(\S.*)$", p)
    if m and m.group(1).upper() in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
        http, p = m.group(1).upper(), m.group(2).strip()
    p = p.split("?", 1)[0]
    if not p.startswith("/"):
        p = "/" + p
    p = re.sub(r"/{2,}", "/", p)
    p = re.sub(r"\{[^}]*\}", "{}", p)
    if p.endswith(".do"):
        p = p[:-3]
    p = p.rstrip("/") or "/"
    if p == "/api" or p.startswith("/api/"):
        p = p[4:] or "/"
    return http, p


def join_path(a, b):
    a, b = (a or "").strip(), (b or "").strip()
    if not a:
        return b or "/"
    if not b:
        return a
    return a.rstrip("/") + "/" + b.lstrip("/")


def endpoints(src_obj, classes):
    """컨트롤러 메서드의 요청 매핑 = 클래스 레벨 매핑 x 메서드 레벨 매핑. [(fqn, key, http 목록, 정규화 경로, 원문 경로)]"""
    js = src_obj.js
    out = []
    for c in classes:
        if not c.masked:
            continue
        cls_maps = js.request_mappings(c.text, c.masked, c.head_start, c.body_open) or [([], [""])]
        for m in c.methods:
            if m.is_ctor or m.body_start is None:
                continue
            for http, paths in js.request_mappings(c.text, c.masked, m.start, m.body_start):
                for chttp, cpaths in cls_maps:
                    for cp in cpaths:
                        for mp in paths:
                            raw = join_path(cp, mp)
                            out.append((c.fqn, m.key, sorted(set(http) | set(chttp)), norm_api(raw)[1], raw))
    return out


def chars_of_classes(src_obj, classes):
    seen, n = set(), 0
    for c in classes:
        if c.file in seen:
            continue
        seen.add(c.file)
        n += len(src_obj.file_text.get(c.file, c.text or ""))
    return n


def chars_of_statements(stmts):
    return sum(len(v.get("sql") or "") for v in stmts.values())


# ---------------------------------------------------------------- 측정

def slice_metrics(entry, src_obj=None, cpt=4):
    m = {"apis": len(entry.get("apis") or []), "screens": len(entry.get("screens") or []),
         "requirements": len(entry.get("requirements") or []),
         "transitions": len(((entry.get("process") or {}).get("transitions")) or [])}
    if src_obj is not None:
        cls = src_obj.slice_classes(entry["id"])
        st = src_obj.slice_statements(entry["id"])
        m["programs"] = len({c.file for c in cls})
        m["methods"] = sum(len(c.methods) for c in cls)
        m["statements"] = len(st)
        m["asis_tokens"] = int((chars_of_classes(src_obj, cls) + chars_of_statements(st)) / cpt)
    return m


def verdict(metrics, th):
    over = [f"{METRIC_LABEL.get(k, k)} {metrics[k]} > {v}" for k, v in th["size"].items()
            if isinstance(metrics.get(k), (int, float)) and metrics[k] > v]
    if over:
        return "split", over
    small = th["merge_below"]
    if all(isinstance(metrics.get(k), (int, float)) and metrics[k] <= v for k, v in small.items() if k in metrics) \
            and any(k in metrics for k in small):
        return "merge", [f"{METRIC_LABEL.get(k, k)} {metrics[k]} <= {v}" for k, v in small.items() if k in metrics]
    return "ok", []


def unit_metrics(entry, unit, assignment, src_obj=None, cpt=4):
    """unit 의 크기. 토큰 추정 = 클래스 통째 배정 파일 전체 + 메서드 단위 배정 메서드 본문(+ 선언부는 배정된 unit 에 한 번) + statement."""
    m = {"apis": len(unit.get("apis") or []), "screens": len(unit.get("screens") or []),
         "transitions": len(unit.get("transitions") or [])}
    if src_obj is not None and assignment is not None:
        mine = assignment.get(unit["id"]) or {}
        progs = set(mine.get("programs") or [])
        meths = sorted(set(mine.get("methods") or []))
        cls = [c for c in src_obj.slice_classes(entry["id"]) if os.path.basename(c.file) in progs]
        st = {k: v for k, v in src_obj.stmts.items() if k in set(mine.get("statements") or [])}
        sizes = src_obj.item_sizes(entry["id"])
        m["programs"] = len(progs)
        m["methods"] = len([x for x in meths if not x.endswith("#" + DECL)])
        m["statements"] = len(st)
        m["asis_tokens"] = int((chars_of_classes(src_obj, cls) + sum(sizes.get(x, 0) for x in meths)
                                + chars_of_statements(st)) / cpt)
    return m


def top_items(entry, unit_id, assignment, src_obj, cpt=4, n=TOP_N):
    """unit 에 배정된 항목 중 큰 것 n개 [(id, 토큰 추정)]. 메서드 단위 항목을 우선 보여 주고, 없으면 클래스 통째 항목."""
    mine = assignment.get(unit_id) or {}
    sizes = src_obj.item_sizes(entry["id"])
    items = [x for x in (mine.get("methods") or []) if not str(x).endswith("#" + DECL)] or list(mine.get("programs") or [])
    rows = sorted(((x, int(sizes.get(x, 0) / cpt)) for x in items), key=lambda r: (-r[1], r[0]))
    return rows[:n]


def measure(slices, src=None, cfg=None):
    th = thresholds(cfg)
    cpt = th["chars_per_token"]
    cfg = cfg if cfg is not None else config()
    src_obj = Source(src, slices, (cfg.get("asis") or {}).get("common_packages")) if src else None
    rows = []
    for s in slices:
        met = slice_metrics(s, src_obj, cpt)
        v, reasons = verdict(met, th)
        row = {"slice": s["id"], "name": s.get("name", ""), "metrics": met, "verdict": v, "reasons": reasons,
               "units": len(units_of(s))}
        if units_of(s):
            assignment = derive(src_obj, s)["assignment"] if src_obj is not None else None
            urows = []
            for u in units_of(s):
                um = unit_metrics(s, u, assignment, src_obj, cpt)
                over = [f"{METRIC_LABEL.get(k, k)} {um[k]} > {lim}" for k, lim in th["unit_max"].items()
                        if isinstance(um.get(k), (int, float)) and um[k] > lim]
                ur = {"unit": u.get("id"), "kind": u.get("kind"), "metrics": um, "over": over}
                if over and assignment is not None:
                    ur["top"] = [{"item": x, "asis_tokens": t} for x, t in top_items(s, u["id"], assignment, src_obj, cpt)]
                urows.append(ur)
            row["unit_rows"] = urows
        rows.append(row)
    return {"schema": 1, "generated_by": "tools/slice_units.py measure", "thresholds": th,
            "source": bool(src_obj), "slices": rows}


# ---------------------------------------------------------------- 행렬 (slice 내부 공유 판정)

def resolve_method_spec(spec, classes):
    """'OrderController#insert' · 'OrderController.java#insert' · 'OrderController#insert/2' · 'com.x.OrderController#insert'
    → [(fqn, key)]. 이름만 주면 오버로드 전부."""
    if "#" not in str(spec):
        return []
    cls, meth = str(spec).split("#", 1)
    cls = cls.strip()
    cls = cls[:-5] if cls.endswith(".java") else cls
    out = []
    for c in classes:
        if cls not in (c.name, c.fqn, os.path.basename(c.file)[:-5]):
            continue
        for m in c.methods:
            if not m.is_ctor and (m.key == meth or m.name == meth):
                out.append((c.fqn, m.key))
    return sorted(set(out))


def derive(src_obj, entry):
    """slice 안의 클래스·메서드·statement 를 unit 에 배정한다.

    - 진입점: step·query unit 의 asis.programs(클래스 통째), asis.methods(메서드), apis(요청 경로 → 컨트롤러 메서드 자동 대응).
      나머지 slice 코드를 어느 unit 이 (전이적으로) 쓰는지 메서드 호출 그래프로 계산한다.
    - 메서드 단위 배정(진입점 클래스·업무 서비스 구현체, split_kind): 메서드를 쓰는 unit 이 하나면 그 unit, 둘 이상이면 core.
      선언부·필드·생성자(File.java#<decl>)는 그 클래스의 메서드가 2개 이상 unit 에 걸치면 core, 아니면 그 unit.
    - 클래스 통째 배정(그 밖 전부): 2개 이상 unit 이 쓰는 클래스는 core 여야 한다(선언 필수). core 에 선언돼 있지 않으면 FAIL.
    - core 가 부르는 것은 core 다: core 메서드가 부르는 메서드 단위 항목은 core 로 올리고, 클래스 통째 항목이 unit 에 있으면 FAIL.
    - statement 는 호출하는 메서드를 따라간다: core 메서드가 호출하거나 2개 이상 unit 이 쓰면 core, 한 unit 만 쓰면 그 unit.
    """
    sid = entry["id"]
    units = units_of(entry)
    core = core_unit(units)
    core_id = core.get("id") if core else None
    CORE = core_id or "core"
    discard_raw = set(((entry.get("asis") or {}).get("discard")) or [])
    discard = {norm_item(x) for x in discard_raw}
    findings = []

    slice_cls = {c.fqn: c for c in src_obj.slice_classes(sid)}
    slice_st = src_obj.slice_statements(sid)
    slice_fr = src_obj.slice_fragments(sid)
    base = {fqn: os.path.basename(c.file) for fqn, c in slice_cls.items()}
    by_base = {}
    for fqn in sorted(slice_cls):
        by_base.setdefault(base[fqn], []).append(fqn)
    mids = {fqn: method_ids(c) for fqn, c in slice_cls.items()}

    def mid(node):
        fqn, key = node
        if fqn in mids:
            return mids[fqn].get(key) or f"{base[fqn]}#{key.split('/')[0]}"
        return f"{fqn.rsplit('.', 1)[-1]}#{key}"

    # 1. 클래스 통째 선언 (asis.programs · asis.packages)
    declared = {}   # program → unit id
    for u in units:
        for p in (u.get("asis") or {}).get("programs") or []:
            if p in declared and declared[p] != u.get("id"):
                findings.append(finding("FAIL", f"units.{u.get('id')}.asis.programs",
                                        f"{p} 가 {declared[p]} 과 {u.get('id')} 에 중복 배정됐다",
                                        "한 프로그램은 한 unit 만 소유한다. 둘 다 쓰면 core 로 올린다"))
            declared.setdefault(p, u.get("id"))
    for u in non_core(units):
        for pkg in (u.get("asis") or {}).get("packages") or []:
            for fqn, c in slice_cls.items():
                if c.package == pkg or c.package.startswith(pkg + "."):
                    declared.setdefault(base[fqn], u.get("id"))

    parents = src_obj.parents(sid)
    split = {}
    for fqn, c in slice_cls.items():
        prog = base[fqn]
        if prog in declared or norm_item(prog) in discard:
            continue
        k = split_kind(c, parents)
        if k:
            split[fqn] = k
    split_nodes = {(fqn, m.key) for fqn in split for m in slice_cls[fqn].methods if not m.is_ctor}

    # 2. 메서드 선언 (asis.methods)
    declared_m = {}   # (fqn, key) → unit id
    slice_list = [slice_cls[f] for f in sorted(slice_cls)]
    for u in units:
        for spec in (u.get("asis") or {}).get("methods") or []:
            nodes = resolve_method_spec(spec, slice_list)
            if not nodes:
                findings.append(finding("FAIL", f"units.{u.get('id')}.asis.methods",
                                        f"{spec} 에 해당하는 slice 안 메서드를 찾지 못했다",
                                        "'클래스명#메서드명' (오버로드는 '#메서드명/인자수') 으로 적는다"))
            for n in nodes:
                if n in declared_m and declared_m[n] != u.get("id"):
                    findings.append(finding("FAIL", f"units.{u.get('id')}.asis.methods",
                                            f"{mid(n)} 가 {declared_m[n]} 과 {u.get('id')} 에 중복 배정됐다",
                                            "한 메서드는 한 unit 만 소유한다. 둘 다 쓰면 core 로 올린다"))
                declared_m.setdefault(n, u.get("id"))

    # 3. API(요청 경로) → 컨트롤러 메서드
    eps = endpoints(src_obj, [slice_cls[f] for f in sorted(split) if split[f] == "entry"])
    api_owner, api_rows, unmatched = {}, [], []
    for u in non_core(units):
        uid = u.get("id")
        for api in u.get("apis") or []:
            http, path = norm_api(api)
            cands = [e for e in eps if e[3] == path]
            if len(cands) > 1 and http:
                narrowed = [e for e in cands if not e[2] or http in e[2]]
                cands = narrowed or cands
            nodes = sorted({(e[0], e[1]) for e in cands})
            if not nodes:
                unmatched.append((uid, api))
            for n in nodes:
                if n in api_owner and api_owner[n] != uid:
                    findings.append(finding("FAIL", f"units.{uid}.apis",
                                            f"{mid(n)} 가 API 경로로 {api_owner[n]} 과 {uid} 에 함께 대응된다",
                                            "한 컨트롤러 메서드는 한 unit 의 API 다. apis 배정을 고친다"))
                elif n in declared_m and declared_m[n] != uid:
                    findings.append(finding("FAIL", f"units.{uid}.apis",
                                            f"{mid(n)} 는 API 경로상 {uid} 소유인데 asis.methods 로 {declared_m[n]} 에 선언됐다",
                                            "API 배정과 asis.methods 선언 중 하나를 고친다"))
                api_owner.setdefault(n, uid)
            api_rows.append({"unit": uid, "api": str(api), "methods": [mid(n) for n in nodes]})
    if eps:
        for uid, api in unmatched:
            findings.append(finding("WARN", f"units.{uid}.apis",
                                    f"API {api} 에 대응하는 컨트롤러 메서드를 찾지 못했다 (요청 매핑 경로 대조)",
                                    "경로가 AS-IS 와 다르면 unit 의 asis.methods 에 '컨트롤러#메서드' 로 진입점을 적는다"))

    # 4. unit 별 도달 (메서드 호출 그래프 전이 폐포)
    roots = {u.get("id"): set() for u in non_core(units) if u.get("id")}
    for prog, uid in declared.items():
        if uid in roots:
            for fqn in by_base.get(prog, []):
                roots[uid] |= {(fqn, m.key) for m in slice_cls[fqn].methods}
    for n, uid in list(declared_m.items()) + list(api_owner.items()):
        if uid in roots:
            roots[uid].add(n)
    usage, stmt_users, stmt_callers, unresolved = {}, {}, {}, {}
    for uid in sorted(roots):
        todo, seen = sorted(roots[uid], reverse=True), set()
        while todo:
            n = todo.pop()
            if n in seen:
                continue
            seen.add(n)
            usage.setdefault(n, set()).add(uid)
            e = src_obj.edges.get(n) or {"sql": [], "unresolved": []}
            for q, _pos in e["sql"]:
                if q in slice_st:
                    stmt_users.setdefault(q, set()).add(uid)
                    if n[0] in slice_cls:
                        stmt_callers.setdefault(q, set()).add(n)
            for x in e["unresolved"]:
                unresolved.setdefault((x["file"], x["line"], x["call"]), set()).add(uid)
            todo.extend(t for t in src_obj.callees(n) if t not in seen)
    class_used = {}
    for (fqn, _k), us in usage.items():
        if fqn in slice_cls:
            class_used.setdefault(fqn, set()).update(us)
    for fqn in sorted(slice_cls):   # 하위 클래스를 쓰면 상위 클래스도 쓴다
        for anc in src_obj.idx.chain(fqn)[1:]:
            if anc in slice_cls and class_used.get(fqn):
                class_used.setdefault(anc, set()).update(class_used[fqn])

    # 5. 클래스 통째 배정
    class_rows, class_unit, cross = [], {}, []
    node_unit = {}   # slice 메서드 → 배정 unit (statement 배정·core 전파에 쓴다)
    core_programs = set(((core or {}).get("asis") or {}).get("programs") or [])
    for fqn in sorted(slice_cls):
        if fqn in split:
            continue
        c = slice_cls[fqn]
        prog = base[fqn]
        used = set(class_used.get(fqn, set()))
        dec = declared.get(prog)
        if dec is not None:
            assigned = dec
        elif norm_item(prog) in discard:
            assigned = "discard"
        elif len(used) >= 2:
            assigned = CORE
            findings.append(finding("FAIL", f"class.{prog}",
                                    f"{prog} 를 unit {', '.join(sorted(used))} 가 함께 쓰는데 core 에 없다 "
                                    "(각 unit 이 자기 쓰는 메서드만 옮기면 클래스가 분해된다)",
                                    f"slices.yaml 의 {sid}.units 중 core 의 asis.programs 에 {prog} 를 넣는다"))
        elif len(used) == 1:
            assigned = next(iter(used))
        else:
            assigned = None
            findings.append(finding("FAIL", f"class.{prog}",
                                    f"{prog} 는 어느 unit 도 쓰지 않고 어디에도 배정되지 않았다 (변환에서 빠진다)",
                                    "진입점이면 해당 unit 의 asis.programs 에, 공용이면 core 에, 폐기면 slice 의 asis.discard 에 적는다"))
        if dec is not None and dec != core_id and used - {dec}:
            others = sorted(used - {dec})
            for o in others:
                cross.append({"from": o, "to": dec, "what": prog, "kind": "class"})
            findings.append(finding("FAIL", f"class.{prog}",
                                    f"{prog} 는 {dec} 에 배정됐지만 {', '.join(others)} 도 쓴다",
                                    "여러 unit 이 쓰는 클래스는 core 로 올린다 (각 unit 이 부분 이관하면 클래스가 분해된다)"))
        if dec == core_id and core_id and len(used) <= 1 and prog in core_programs:
            findings.append(finding("WARN", f"class.{prog}",
                                    f"{prog} 는 core 에 있지만 쓰는 unit 이 {len(used)}개다",
                                    "core 가 비대해지면 core 도 에이전트 한도를 넘는다. 한 unit 만 쓰면 그 unit 으로 내린다"))
        class_unit[prog] = assigned
        for m in c.methods:
            node_unit[(fqn, m.key)] = assigned
        class_rows.append({"class": fqn, "program": prog, "declared": dec, "used_by": sorted(used),
                           "assigned": assigned})

    # 6. 메서드 단위 배정 (진입점 클래스·업무 서비스 구현체)
    method_rows = {}
    for fqn in sorted(split):
        c = slice_cls[fqn]
        class_rows.append({"class": fqn, "program": base[fqn], "declared": None,
                           "used_by": sorted(class_used.get(fqn, set())), "assigned": None, "split": split[fqn]})
        for m in c.methods:
            if m.is_ctor:
                continue
            n = (fqn, m.key)
            used = set(usage.get(n, set()))
            dec = declared_m.get(n)
            if norm_item(mid(n)) in discard:
                assigned = "discard"
                if used:
                    findings.append(finding("WARN", f"method.{mid(n)}",
                                            f"{mid(n)} 는 폐기로 적혔지만 unit {', '.join(sorted(used))} 가 쓴다"))
            elif dec is not None:
                assigned = dec
                if dec != core_id and used - {dec}:
                    others = sorted(used - {dec})
                    for o in others:
                        cross.append({"from": o, "to": dec, "what": mid(n), "kind": "method"})
                    findings.append(finding("FAIL", f"method.{mid(n)}",
                                            f"{mid(n)} 는 {dec} 에 선언됐지만 {', '.join(others)} 도 쓴다",
                                            "여러 unit 이 쓰는 메서드는 선언을 지워 core 로 올린다"))
            elif len(used) >= 2:
                assigned = CORE
            elif len(used) == 1:
                assigned = next(iter(used))
            else:
                assigned = None
            node_unit[n] = assigned
            method_rows[n] = {"id": mid(n), "class": fqn, "declared": dec, "used_by": sorted(used), "assigned": assigned}

    # 7. core 가 부르는 것은 core (core 는 다른 unit 보다 먼저 변환되므로 unit 소유 코드를 부를 수 없다)
    blamed = set()

    def propagate():
        changed = True
        while changed:
            changed = False
            for n in sorted(node_unit):
                if node_unit[n] != CORE:
                    continue
                for t in src_obj.callees(n):
                    if t not in node_unit or node_unit[t] in (CORE, "discard"):
                        continue
                    if t in split_nodes and t not in declared_m:
                        node_unit[t] = CORE
                        method_rows[t]["assigned"] = CORE
                        method_rows[t]["via_core"] = mid(n)
                        changed = True
                    elif (n, t) not in blamed and node_unit[t] is not None:
                        blamed.add((n, t))
                        what = base.get(t[0], t[0]) if t not in split_nodes else mid(t)
                        findings.append(finding("FAIL", f"class.{what}" if t not in split_nodes else f"method.{what}",
                                                f"core 의 {mid(n)} 가 부르는 {what} 가 {node_unit[t]} 에 배정됐다",
                                                "core 가 부르는 코드는 core 에 둔다 (core 의 asis.programs·asis.methods 에 넣는다)"))
    propagate()
    for n, row in method_rows.items():
        if row["assigned"] is None:
            findings.append(finding("FAIL", f"method.{row['id']}",
                                    f"{row['id']} 는 어느 unit 도 쓰지 않고 어디에도 배정되지 않았다 (변환에서 빠진다)",
                                    "진입점이면 unit 의 apis 또는 asis.methods 에, 폐기면 slice 의 asis.discard 에 'File.java#메서드' 로 적는다"))

    # 선언부(필드·생성자): 메서드가 2개 이상 unit 에 걸치면 core
    for fqn in sorted(split):
        c = slice_cls[fqn]
        owners = {node_unit[(fqn, m.key)] for m in c.methods if not m.is_ctor} - {None, "discard"}
        if CORE in owners or len(owners) >= 2:
            d = CORE
        elif owners:
            d = next(iter(owners))
        else:
            d = "discard"
        did = f"{base[fqn]}#{DECL}"
        method_rows[(fqn, DECL)] = {"id": did, "class": fqn, "declared": None, "used_by": sorted(owners - {CORE}),
                                    "assigned": d, "decl": True}
        for m in c.methods:
            if m.is_ctor:
                node_unit[(fqn, m.key)] = d
    propagate()

    # 8. statement: 호출 메서드를 따라간다
    stmt_rows, stmt_unit, declared_st = [], {}, {}
    for u in units:
        for q in (u.get("asis") or {}).get("statements") or []:
            declared_st.setdefault(q, u.get("id"))
    for q in sorted(slice_st):
        users = set(stmt_users.get(q, set()))
        callers = stmt_callers.get(q, set())
        from_core = any(node_unit.get(n) == CORE for n in callers) if core_id else False
        if from_core or len(users) >= 2:
            need = CORE
        elif len(users) == 1:
            need = next(iter(users))
        else:
            need = None
        dec = declared_st.get(q)
        assigned = dec or need
        if dec and need and dec != need:
            findings.append(finding("FAIL", f"statement.{q}",
                                    f"{q} 는 {dec} 에 선언됐지만 호출 관계상 {need} 소유다 (사용: {', '.join(sorted(users)) or '-'})",
                                    "선언을 지우거나 호출 관계에 맞게 고친다"))
        if assigned is None:
            findings.append(finding("WARN", f"statement.{q}", f"{q} 는 어느 unit 도 쓰지 않는다",
                                    "동적 호출이면 unit 의 asis.statements 에 선언하고, 폐기면 레포트에 근거를 남긴다"))
        stmt_unit[q] = assigned
        stmt_rows.append({"id": q, "used_by": sorted(users), "callers": sorted(mid(n) for n in callers),
                          "assigned": assigned})
    # fragment 는 include 하는 statement 의 배정을 따라간다 (2개 이상 unit 이거나 core 면 core)
    frag_users = {}

    def walk_frag(fid, owner, depth=0):
        if fid not in slice_fr or depth > 20:
            return
        frag_users.setdefault(fid, set()).add(owner)
        for inc in slice_fr[fid]["includes"]:
            walk_frag(inc, owner, depth + 1)
    for q, a in stmt_unit.items():
        if a:
            for inc in src_obj.stmts[q]["includes"]:
                walk_frag(inc, a)
    for fid in sorted(slice_fr):
        owners = frag_users.get(fid, set())
        stmt_unit[fid] = CORE if (CORE in owners or len(owners) >= 2) else (next(iter(owners)) if owners else None)
        stmt_rows.append({"id": fid, "used_by": sorted(owners), "callers": [], "assigned": stmt_unit[fid],
                          "fragment": True})

    for (file, line, call), us in sorted(unresolved.items()):
        findings.append(finding("WARN", "unresolved",
                                f"동적 SQL 호출 {call} ({src_obj.cu.rel(file, src_obj.src)}:{line}) — 배정 불가",
                                "해당 unit 의 asis.statements 에 실제 id 를 선언한다"))

    assignment = {}
    for u in units:
        uid = u["id"]
        assignment[uid] = {"programs": sorted(p for p, a in class_unit.items() if a == uid),
                           "methods": sorted(r["id"] for r in method_rows.values() if r["assigned"] == uid),
                           "statements": sorted(q for q, a in stmt_unit.items() if a == uid)}
    for q, a in declared_st.items():
        if a in assignment and q not in assignment[a]["statements"]:
            assignment[a]["statements"].append(q)
            assignment[a]["statements"].sort()
    discarded = sorted([p for p, a in class_unit.items() if a == "discard"]
                       + [r["id"] for r in method_rows.values() if r["assigned"] == "discard" and not r.get("decl")])
    return {"schema": 2, "generated_by": "tools/slice_units.py matrix", "slice": sid,
            "classes": sorted(class_rows, key=lambda r: r["program"]),
            "methods": sorted(method_rows.values(), key=lambda r: r["id"]),
            "apis": api_rows, "statements": stmt_rows,
            "cross_unit": sorted(cross, key=lambda x: (x["what"], x["from"])), "assignment": assignment,
            "discard": discarded, "findings": findings}


def matrix_path(sid):
    return os.path.join(workspace(), "knowledge", "units", f"{sid}.yaml")


def load_assignment(entry):
    """unit → {programs, methods, statements}. 행렬 파일이 있으면 그것을, 없으면 slices.yaml 선언을 쓴다.
    methods 키가 없는 옛 행렬(schema 1)도 그대로 읽는다 — 없는 키는 빈 목록으로 본다."""
    p = matrix_path(entry["id"])
    if os.path.exists(p):
        try:
            data = load_yaml(p)
            if isinstance(data.get("assignment"), dict):
                return data["assignment"], p
        except Exception:
            pass
    out = {}
    for u in units_of(entry):
        a = u.get("asis") or {}
        out[u["id"]] = {"programs": sorted(a.get("programs") or []), "methods": sorted(a.get("methods") or []),
                        "statements": sorted(a.get("statements") or [])}
    return out, None


def unit_items(assignment, uid):
    a = assignment.get(uid) or {}
    return set(a.get("programs") or []) | set(a.get("methods") or []) | set(a.get("statements") or [])


def validate_assignment(entry, assignment):
    """행렬 파일(assignment)의 형식 검증. schema 1(methods 없음)과 2 를 모두 읽는다."""
    f = []
    ids = {u.get("id") for u in units_of(entry)}
    owner = {}
    for uid, a in sorted((assignment or {}).items()):
        if uid not in ids:
            f.append(finding("FAIL", f"matrix.{uid}", f"행렬에 slices.yaml 에 없는 unit 이 있다: {uid}",
                             f"python tools/slice_units.py matrix --slice {entry['id']} 로 다시 만든다"))
            continue
        if not isinstance(a, dict):
            f.append(finding("FAIL", f"matrix.{uid}", "배정 형식 오류 (programs·methods·statements 목록이어야 한다)"))
            continue
        for x in a.get("methods") or []:
            if "#" not in str(x):
                f.append(finding("FAIL", f"matrix.{uid}.methods", f"메서드 항목 형식 오류: {x!r}", "'File.java#메서드'"))
        for x in sorted(unit_items(assignment, uid)):
            k = norm_item(x)
            if k in owner and owner[k] != uid:
                f.append(finding("FAIL", f"matrix.{uid}", f"{x} 가 {owner[k]} 과 {uid} 에 함께 배정됐다"))
            owner.setdefault(k, uid)
    return f


def same_assignment(a, b):
    def canon(x):
        return {u: sorted(norm_item(i) for i in unit_items(x, u)) for u in (x or {})}
    return canon(a) == canon(b)


# ---------------------------------------------------------------- 구조 검증

def transitive_deps(units):
    by = {u.get("id"): u for u in units}
    out = {}

    def walk(uid, seen):
        for d in (by.get(uid) or {}).get("depends_on") or []:
            if d not in seen and d in by:
                seen.add(d)
                walk(d, seen)
        return seen
    for uid in by:
        out[uid] = walk(uid, set())
    return out


def unit_waves(units):
    by = {u.get("id"): u for u in units}
    done, remaining, waves = set(), dict(by), []
    while remaining:
        ready = [i for i, u in remaining.items() if all(d in done or d not in by for d in (u.get("depends_on") or []))]
        if not ready:
            return waves, sorted(remaining)
        ready.sort(key=lambda i: (0 if by[i].get("kind") == "core" else 1, list(by).index(i)))
        waves.append(ready)
        done |= set(ready)
        for i in ready:
            remaining.pop(i)
    return waves, []


def validate_structure(entry):
    sid = entry["id"]
    units = units_of(entry)
    f = []
    if not units:
        return f
    ids = [u.get("id") for u in units]
    for u in units:
        uid = u.get("id")
        if not uid or not UNIT_ID_RE.match(str(uid)):
            f.append(finding("FAIL", "units.id", f"unit id 형식 오류: {uid!r}", "영문 소문자·숫자·하이픈"))
        if u.get("kind") not in UNIT_KINDS:
            f.append(finding("FAIL", f"units.{uid}.kind", f"kind 는 {'|'.join(UNIT_KINDS)} 중 하나여야 한다 (현재 {u.get('kind')!r})"))
    dup = sorted({i for i in ids if ids.count(i) > 1})
    for i in dup:
        f.append(finding("FAIL", "units.id", f"unit id 중복: {i}"))
    cores = [u for u in units if u.get("kind") == "core"]
    if len(cores) != 1:
        f.append(finding("FAIL", "units.core", f"core unit 은 정확히 1개여야 한다 (현재 {len(cores)}개)",
                         "여러 unit 이 함께 쓰는 엔티티·상태·서비스·SQL 을 먼저 변환하는 core 를 첫 unit 으로 둔다"))
    elif units[0].get("kind") != "core":
        f.append(finding("FAIL", "units.core", "core unit 은 목록의 첫 번째여야 한다"))
    steps = [u for u in units if u.get("kind") == "step"]
    if len(non_core(units)) < 2:
        f.append(finding("WARN", "units", "core 를 뺀 unit 이 2개 미만이다 — 나눌 이유가 없다", "units 를 지우고 slice 하나로 돈다"))

    # 의존
    known = set(ids)
    for u in units:
        for d in u.get("depends_on") or []:
            if d not in known:
                f.append(finding("FAIL", f"units.{u.get('id')}.depends_on", f"없는 unit: {d}"))
    _waves, cyc = unit_waves(units)
    if cyc:
        f.append(finding("FAIL", "units.depends_on", f"unit 의존 순환: {', '.join(cyc)}"))
    if len(cores) == 1:
        cid = cores[0].get("id")
        if cores[0].get("depends_on"):
            f.append(finding("FAIL", f"units.{cid}.depends_on", "core 는 다른 unit 에 의존할 수 없다"))
        deps = transitive_deps(units)
        for u in non_core(units):
            if cid not in deps.get(u.get("id"), set()):
                f.append(finding("FAIL", f"units.{u.get('id')}.depends_on", f"{u.get('id')} 가 core({cid}) 에 의존하지 않는다",
                                 "모든 unit 은 직접 또는 전이적으로 core 뒤에 온다"))
        for k in ("apis", "screens", "transitions"):
            if cores[0].get(k):
                f.append(finding("FAIL", f"units.{cid}.{k}", f"core 는 {k} 를 가지지 않는다 — 기반만 만든다",
                                 "API·화면·상태 전이는 step/query unit 에 배정한다"))

    # 업무 프로세스(상태 전이)
    proc = entry.get("process") or {}
    ptrans = [norm_transition(t) for t in (proc.get("transitions") or [])]
    for t in proc.get("transitions") or []:
        if not parse_transition(t):
            f.append(finding("FAIL", "process.transitions", f"상태 전이 형식 오류: {t!r}", "'이전상태 -> 다음상태' (시작은 START)"))
    states = set(proc.get("states") or [])
    if states:
        for t in ptrans:
            p = parse_transition(t)
            if p:
                for s in p:
                    if s != "START" and s not in states:
                        f.append(finding("WARN", "process.transitions", f"{t} 의 '{s}' 가 process.states 에 없다"))
    if steps and not ptrans:
        f.append(finding("FAIL", "process", f"{sid} 에 step unit 이 있는데 process.transitions 가 없다",
                         "unit 은 업무 프로세스(상태 전이) 기준으로 나눈다. slice 의 process.states·transitions 를 먼저 적는다"))
    owned = {}
    for u in units:
        for t in u.get("transitions") or []:
            nt = norm_transition(t)
            if u.get("kind") != "step":
                f.append(finding("FAIL", f"units.{u.get('id')}.transitions", f"{u.get('kind')} unit 은 상태 전이를 가지지 않는다: {nt}"))
                continue
            if ptrans and nt not in ptrans:
                f.append(finding("FAIL", f"units.{u.get('id')}.transitions", f"process 에 없는 상태 전이: {nt}"))
            if nt in owned and owned[nt] != u.get("id"):
                f.append(finding("FAIL", f"units.{u.get('id')}.transitions", f"{nt} 를 {owned[nt]} 와 {u.get('id')} 가 함께 소유한다",
                                 "상태 전이 하나는 unit 하나가 소유한다"))
            owned.setdefault(nt, u.get("id"))
    for u in steps:
        if not u.get("transitions"):
            f.append(finding("FAIL", f"units.{u.get('id')}.transitions", f"step unit {u.get('id')} 가 소유한 상태 전이가 없다",
                             "상태를 바꾸지 않는 기능이면 kind: query 로 둔다"))
    for t in ptrans:
        if steps and t not in owned:
            f.append(finding("FAIL", "process.transitions", f"상태 전이 {t} 를 소유한 unit 이 없다",
                             "빠진 전이는 변환에서도 빠진다. step unit 하나에 배정한다"))

    # API·화면·요구사항 분배 (한 번씩)
    for k in ("apis", "screens"):
        want = [str(x) for x in (entry.get(k) or [])]
        seen = {}
        for u in non_core(units):
            for x in u.get(k) or []:
                x = str(x)
                if x not in want:
                    f.append(finding("FAIL", f"units.{u.get('id')}.{k}", f"slice 에 없는 {k}: {x}", "slice 의 목록에 먼저 넣는다"))
                if x in seen:
                    f.append(finding("FAIL", f"units.{u.get('id')}.{k}", f"{x} 를 {seen[x]} 와 {u.get('id')} 가 함께 가진다",
                                     "한 unit 에만 둔다. 여러 단계가 쓰는 조회는 query unit 으로 뺀다"))
                seen.setdefault(x, u.get("id"))
        for x in want:
            if x not in seen:
                f.append(finding("FAIL", f"{k}", f"{x} 가 어느 unit 에도 배정되지 않았다", "빠진 항목은 변환에서도 빠진다"))
    reqs = [str(x) for x in (entry.get("requirements") or [])]
    covered = set()
    for u in units:
        for x in u.get("requirements") or []:
            if str(x) not in reqs:
                f.append(finding("FAIL", f"units.{u.get('id')}.requirements", f"slice 에 없는 요구사항: {x}"))
            covered.add(str(x))
    flows = [fl for fl in (entry.get("flows") or []) if isinstance(fl, dict)]
    for fl in flows:
        covered |= {str(x) for x in (fl.get("requirements") or [])}
    for x in reqs:
        if x not in covered:
            f.append(finding("FAIL", "requirements", f"{x} 가 어느 unit·flow 에도 없다"))

    # AS-IS 프로그램 전수
    decl = {}
    for u in units:
        for p in (u.get("asis") or {}).get("programs") or []:
            if p in decl and decl[p] != u.get("id"):
                f.append(finding("FAIL", f"units.{u.get('id')}.asis.programs", f"{p} 를 {decl[p]} 와 {u.get('id')} 가 함께 가진다"))
            decl.setdefault(p, u.get("id"))
    # 메서드 단위로 배정되는 클래스(진입점·업무 서비스 구현체, §20)와 한 unit 만 쓰는 클래스는 unit 의 asis.programs 에 적지 않는다 —
    # 행렬(knowledge/units/<slice>.yaml)의 assignment.<unit>.methods·programs 나 unit 의 asis.methods 가 그 클래스를 덮는다.
    # 적지 않았다고 FAIL 로 보면 거대 컨트롤러를 다시 core 에 통째로 올리게 된다(실측: 실전 허브 slice core 8.7만 토큰).
    by_method = set()
    for u in units:
        for spec in (u.get("asis") or {}).get("methods") or []:
            by_method.add(str(spec).split("#", 1)[0].strip())
    try:
        assignment, _apath = load_assignment(entry)
    except Exception:
        assignment = {}
    for a in (assignment or {}).values():
        if isinstance(a, dict):
            # 행렬이 클래스 통째로 자동 배정한 프로그램(한 unit 만 쓰는 인터페이스·도우미)도 덮인 것으로 본다
            for x in list(a.get("methods") or []) + list(a.get("programs") or []):
                by_method.add(str(x).split("#", 1)[0].strip())
    by_method = {x[:-5] if x.endswith(".java") else x for x in by_method}
    for p in ((entry.get("asis") or {}).get("programs") or []):
        if p not in decl and p not in ((entry.get("asis") or {}).get("discard") or []) \
                and (p[:-5] if p.endswith(".java") else p) not in by_method:
            f.append(finding("FAIL", "asis.programs", f"slice 의 AS-IS 프로그램 {p} 가 어느 unit 에도 없다",
                             "진입점·업무 서비스 구현체면 행렬(matrix)이 메서드 단위로 배정한다 — "
                             f"python tools/slice_units.py matrix --slice {sid} 를 먼저 돌린다"))

    # 흐름(이음매) 테스트
    fids = [fl.get("id") for fl in flows]
    if len(non_core(units)) >= 2 and not flows:
        f.append(finding("FAIL", "flows", f"{sid} 에 unit 이 여러 개인데 flows 가 없다",
                         "unit 사이 상태 인계(이음매)는 흐름 테스트로만 드러난다. unit 을 가로지르는 시나리오를 flows 에 적는다"))
    for i in sorted({x for x in fids if fids.count(x) > 1}):
        f.append(finding("FAIL", "flows.id", f"flow id 중복: {i}"))
    in_flow = set()
    for fl in flows:
        fid = fl.get("id")
        if not fid or not FLOW_ID_RE.match(str(fid)):
            f.append(finding("FAIL", "flows.id", f"flow id 형식 오류: {fid!r}", "FLOW-<slice>-NN"))
        fu = fl.get("units") or []
        if len(fu) < 2:
            f.append(finding("FAIL", f"flows.{fid}", "flow 는 unit 2개 이상을 가로질러야 한다"))
        for x in fu:
            if x not in known:
                f.append(finding("FAIL", f"flows.{fid}", f"없는 unit: {x}"))
            elif core_unit(units) is not None and x == core_unit(units).get("id"):
                f.append(finding("FAIL", f"flows.{fid}", "flow 에 core 를 넣지 않는다 (core 는 모든 unit 의 바탕이다)"))
            in_flow.add(x)
    for u in non_core(units):
        if flows and u.get("id") not in in_flow:
            f.append(finding("FAIL", "flows", f"unit {u.get('id')} 가 어느 flow 에도 없다",
                             "그 unit 이 앞뒤 unit 과 상태를 주고받는 경로를 flow 로 적는다"))
    return f


def validate(entry, src_obj=None, th=None, assignment=None):
    """구조·크기·행렬 검증. assignment 는 행렬 파일(knowledge/units/<slice>.yaml)의 배정 — 주면 형식을 검사하고,
    AS-IS 소스도 있으면 지금 소스로 다시 계산한 배정과 다른지(행렬이 오래됐는지) 본다."""
    th = th or thresholds()
    f = list(validate_structure(entry))
    if assignment is not None and units_of(entry):
        f.extend(validate_assignment(entry, assignment))
    met = slice_metrics(entry, src_obj, th["chars_per_token"])
    v, reasons = verdict(met, th)
    units = units_of(entry)
    if v == "split" and not units:
        f.append(finding("WARN", "size", f"{entry['id']} 가 분할 기준을 넘는다: {'; '.join(reasons)}",
                         "업무 프로세스(상태 전이) 기준 units 를 정의하거나, 나누지 않는 근거를 레포트에 남긴다"))
    if units and v != "split":
        f.append(finding("WARN", "size", f"{entry['id']} 는 분할 기준 이하인데 units 가 있다 — 과분할이면 unit 마다 드는 비용만 늘어난다"))
    matrix = None
    if src_obj is not None and units:
        matrix = derive(src_obj, entry)
        f.extend(matrix["findings"])
        if assignment is not None and not same_assignment(assignment, matrix["assignment"]):
            f.append(finding("WARN", "matrix", "행렬 파일의 배정이 지금 소스·선언으로 계산한 배정과 다르다 (오래된 행렬이면 게이트 대조가 어긋난다)",
                             f"python tools/slice_units.py matrix --slice {entry['id']} 로 다시 만든다"))
        cpt = th["chars_per_token"]
        for u in units:
            um = unit_metrics(entry, u, matrix["assignment"], src_obj, cpt)
            for k, lim in th["unit_max"].items():
                if isinstance(um.get(k), (int, float)) and um[k] > lim:
                    msg = f"unit {u['id']} 의 {METRIC_LABEL.get(k, k)} {um[k]} > {lim}"
                    act = "그 unit 의 상태 전이를 더 잘게 나눈다"
                    if k == "asis_tokens":
                        top = top_items(entry, u["id"], matrix["assignment"], src_obj, cpt)
                        if top:
                            msg += " — 크기 상위: " + ", ".join(f"{x} {t}" for x, t in top)
                        if u.get("kind") == "core":
                            act = ("core 에 올라간 큰 메서드부터 본다: 한 unit 만 쓰게 호출을 정리하거나(그 unit 으로 내려간다), "
                                   "상태 전이를 다시 나눠 공유를 줄인다")
                    f.append(finding("WARN", f"units.{u['id']}.size", msg, act))
    return f, met, v, matrix


# ---------------------------------------------------------------- 출력

def print_findings(f):
    for it in f:
        print(f"  - {it['severity']} {it['field']}: {it['message']}")
        if it.get("action"):
            print(f"      -> {it['action']}")


def cmd_measure(args):
    slices, _p = load_slices(args.slices)
    src = source_dir(args.source)
    res = measure(slices, src)
    if args.format == "json":
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    print(f"slice 크기 측정 (AS-IS 소스: {'있음' if src else '없음 — slices.yaml 선언만'})")
    print(f"{'slice':<16} {'판정':<6} {'API':>4} {'화면':>4} {'전이':>4} {'stmt':>5} {'메서드':>6} {'토큰추정':>9}  unit")
    label = {"split": "분할", "merge": "묶기", "ok": "적정"}
    for r in res["slices"]:
        m = r["metrics"]
        print(f"{r['slice']:<16} {label[r['verdict']]:<6} {m['apis']:>4} {m['screens']:>4} {m['transitions']:>4} "
              f"{m.get('statements', '-'):>5} {m.get('methods', '-'):>6} {m.get('asis_tokens', '-'):>9}  {r['units'] or '-'}")
        for why in r["reasons"]:
            print(f"    {why}")
        for u in r.get("unit_rows") or []:
            um = u["metrics"]
            print(f"    unit {u['unit']:<12} {u['kind']:<6} API {um['apis']} 화면 {um['screens']} 전이 {um['transitions']}"
                  f" 프로그램 {um.get('programs', '-')} 메서드 {um.get('methods', '-')} stmt {um.get('statements', '-')}"
                  f" 토큰추정 {um.get('asis_tokens', '-')}"
                  + (f"  상한 초과: {'; '.join(u['over'])}" if u["over"] else ""))
            for t in u.get("top") or []:
                print(f"        크기 상위 {t['item']} {t['asis_tokens']}")
    return 0


def cmd_matrix(args):
    slices, _p = load_slices(args.slices)
    entry = find_slice(slices, args.slice)
    if entry is None:
        print(f"[slice_units] slice 를 찾지 못했다: {args.slice}", file=sys.stderr)
        return 2
    if not units_of(entry):
        print(f"[slice_units] {args.slice} 에 units 가 없다", file=sys.stderr)
        return 2
    src = source_dir(args.source)
    if not src:
        print("[slice_units] AS-IS 소스가 없어 행렬을 만들 수 없다 (config asis.source_dir 또는 --source)", file=sys.stderr)
        return 2
    cfg = config()
    res = derive(Source(src, slices, (cfg.get("asis") or {}).get("common_packages")), entry)
    if args.format == "json":
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    import yaml
    out = args.out or matrix_path(args.slice)
    atomic_write_text(out, yaml.safe_dump(res, allow_unicode=True, sort_keys=False))
    print(f"{args.slice} unit 배정")
    for uid, a in res["assignment"].items():
        print(f"  {uid:<12} 프로그램 {len(a['programs'])} · 메서드 {len(a.get('methods') or [])} · statement {len(a['statements'])}"
              f"  {', '.join(a['programs'])}")
    fails = [x for x in res["findings"] if x["severity"] == "FAIL"]
    print(f"판정: FAIL {len(fails)} · WARN {len(res['findings']) - len(fails)}")
    print_findings(res["findings"])
    print(f"-> {out}")
    return 1 if fails else 0


def cmd_validate(args):
    slices, _p = load_slices(args.slices)
    targets = [find_slice(slices, args.slice)] if args.slice else slices
    if args.slice and targets[0] is None:
        print(f"[slice_units] slice 를 찾지 못했다: {args.slice}", file=sys.stderr)
        return 2
    src = source_dir(args.source)
    cfg = config()
    src_obj = Source(src, slices, (cfg.get("asis") or {}).get("common_packages")) if src else None
    th = thresholds(cfg)
    out, blocked = [], False
    for e in targets:
        assignment, apath = load_assignment(e) if units_of(e) else (None, None)
        f, met, v, _m = validate(e, src_obj, th, assignment if apath else None)
        blocked |= any(x["severity"] == "FAIL" for x in f)
        out.append({"slice": e["id"], "verdict": v, "metrics": met, "units": len(units_of(e)), "findings": f})
    if args.format == "json":
        print(json.dumps({"schema": 1, "blocked": blocked, "slices": out}, ensure_ascii=False, indent=2))
    else:
        for r in out:
            if not r["findings"]:
                continue
            print(f"[{r['slice']}] 판정 {r['verdict']} · unit {r['units']}")
            print_findings(r["findings"])
        print("결과: " + ("차단(FAIL)" if blocked else "통과"))
    return 1 if blocked else 0


def cmd_order(args):
    slices, _p = load_slices(args.slices)
    entry = find_slice(slices, args.slice)
    if entry is None or not units_of(entry):
        print(f"[slice_units] units 가 있는 slice 가 아니다: {args.slice}", file=sys.stderr)
        return 2
    waves, cyc = unit_waves(units_of(entry))
    parallel = bool((config().get("slicing") or {}).get("unit_parallel"))
    seq = [u for w in waves for u in w]
    res = {"slice": args.slice, "waves": waves, "sequence": seq, "cycle": cyc, "parallel": parallel,
           "flows": [fl.get("id") for fl in (entry.get("flows") or []) if isinstance(fl, dict)]}
    if args.format == "json":
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        mode = "웨이브 안 병렬 허용" if parallel else "순차 (같은 slice 의 unit 은 파일을 공유하므로 기본은 순차)"
        print(f"{args.slice} unit 실행 순서 — {mode}")
        for n, w in enumerate(waves, 1):
            print(f"  w{n}: {', '.join(w)}")
        print(f"  이후: slice 통합 — 흐름 테스트 {', '.join(res['flows']) or '(없음)'} · AS-IS 전수 대조")
        if cyc:
            print(f"  순환: {', '.join(cyc)}")
    return 1 if cyc else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="큰 slice 의 업무 프로세스 기준 unit 분할 — 측정·행렬·검증·순서")
    ap.add_argument("--slices", help="slices.yaml (기본: workspace/<project>/slices/slices.yaml)")
    ap.add_argument("--source", help="AS-IS 소스 루트 (기본: config asis.source_dir)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure", help="slice 크기 측정과 분할·묶기 후보 판정")
    m.add_argument("--format", choices=["text", "json"], default="text")
    x = sub.add_parser("matrix", help="slice 내부 unit 사용 행렬과 배정 (knowledge/units/<slice>.yaml)")
    x.add_argument("--slice", required=True)
    x.add_argument("--out")
    x.add_argument("--format", choices=["text", "json"], default="text")
    v = sub.add_parser("validate", help="units 구조·상태 전이·분배·core·흐름 검증")
    v.add_argument("--slice")
    v.add_argument("--format", choices=["text", "json"], default="text")
    o = sub.add_parser("order", help="unit 실행 순서")
    o.add_argument("--slice", required=True)
    o.add_argument("--format", choices=["text", "json"], default="text")
    args = ap.parse_args(argv)
    return {"measure": cmd_measure, "matrix": cmd_matrix, "validate": cmd_validate, "order": cmd_order}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
