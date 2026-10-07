#!/usr/bin/env python3
# datasources.py — 데이터소스 지도(workspace/<project>/knowledge/DATASOURCES.yaml)로 SQL 이관 판정과
#                  외부 데이터소스 테이블의 CREATE 금지를 기계로 확인한다 (pipeline-core §22)
#
# 배경(실측): AS-IS 매퍼가 여러 데이터소스(서로 다른 DB 엔진)를 쓰고, 한 매퍼 파일에 여러 데이터소스 쿼리가 섞이며,
#   외부 데이터소스 쿼리가 이관 대상(주 데이터소스) 테이블과 **같은 이름**의 테이블을 쓰는 경우가 있었다.
#   "이관 대상 DB 에 있는 테이블이면 이관" 이라는 한 축만 쓰면 외부 쿼리를 대상 DB 방언으로 잘못 변환하고,
#   더 나아가 외부 테이블을 우리 DB 에 CREATE 해 버리는 사고로 이어진다. 그래서 판정은 두 축으로 한다:
#     (1) 그 statement 를 실제로 실행하는 데이터소스(매퍼 파일 위치가 아니라 호출 세션·팩토리)
#     (2) 대상 테이블이 이관 대상(주 데이터소스 DDL)인가
#   그리고 외부 데이터소스 테이블은 마이그레이션·DDL·스키마 파일·테스트 시드 어디에서도 CREATE 하지 않는다.
#
# 사용법:
#   python tools/datasources.py validate [--file <DATASOURCES.yaml>]                 # 규격·비밀정보 검사
#   python tools/datasources.py judge --datasource <id> --tables T1,T2 [--write]     # statement 하나의 이관 판정
#   python tools/datasources.py lookup <테이블>                                       # 테이블이 어느 데이터소스 소속인가
#   python tools/datasources.py check [<target_dir>] [--files a.sql ...] [--format json]   # 외부 테이블 CREATE 검사
#
# 판정(judge):
#   주(main) 데이터소스 실행 + 테이블 전부 이관 대상     → convert       (대상 DB 방언으로 변환)
#   주 데이터소스 실행 + 이관 대상에 없는 테이블 있음     → not_migrated  (이관 안 함, 근거 부족 기록)
#   외부(external) 데이터소스 실행                        → keep_dialect  (테이블 이름이 같아도 원래 방언 그대로, 그 데이터소스로 실행)
#   범위 밖(out_of_scope) 데이터소스 실행                 → out_of_scope  (이번 차수 구성 안 함)
#
# check: target 의 SQL 파일 전부와 코드·설정 파일(.xml·.java·.kt·.groovy·.yml·.yaml)에서
#   CREATE TABLE · CREATE VIEW · CREATE SYNONYM(OR REPLACE·IF NOT EXISTS·스키마 접두 포함) 대상이
#   외부·범위 밖 데이터소스 테이블 또는 미확정 외부 테이블(unresolved_tables)이고 주 데이터소스 이관 대상
#   (tables_from·tables·inbound_tables·merged_tables)에 없으면 critical. 이름이 겹치지만 이관 대상이면 info(동명).
#   수신 테이블(inbound_tables)을 src/main 의 코드·Mapper 가 쓰기(INSERT·UPDATE·DELETE·MERGE)하면 warn.
#   사람이 예외로 둔 로컬 시험 대체물(local_stubs: table·files glob(시험 데이터 경로)·evidence·decided_by 사람)은 warn.
#   데이터소스 지도가 없으면 검사를 건너뛴다(종료 코드 0, 생략 안내).
#
# 종료 코드: 0 통과(warn·info·생략 포함) · 1 차단(critical 또는 지도 규격 오류) · 2 입력 오류
# 의존성: pyyaml

import argparse
import fnmatch
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, fix_console_encoding, load_yaml, safe_relpath, target_dir, workspace  # noqa: E402

fix_console_encoding()

ROLES = ("main", "external", "out_of_scope")
# 지도에는 데이터소스 id·운영 엔진·용도·이관 여부·테이블 이름만 둔다. 접속 정보·계정은 키 이름부터 받지 않는다.
FORBIDDEN_KEYS = {"url", "jdbc_url", "jdbcurl", "host", "hostname", "port", "password", "passwd", "pwd",
                  "username", "user", "account", "secret", "credential", "credentials", "token"}
SECRET_VALUE_RE = re.compile(r"(?i)jdbc:[a-z]|ldap://|(?:password|passwd|pwd)\s*[=:]")
SEVERITY_ORDER = {"critical": 0, "warn": 1, "info": 2}

# 검사 대상 파일 — SQL 은 전부, 코드·설정은 DDL 문자열이 들어갈 수 있는 것만
SQL_EXTS = (".sql",)
CODE_EXTS = (".xml", ".java", ".kt", ".groovy", ".yml", ".yaml")
SKIP_DIRS = {"node_modules", "build", "target", "dist", ".gradle", ".git", ".idea", "out", "bin",
             "coverage", ".next", ".turbo", "generated", "__generated__"}

_IDENT = r"(?:`[^`]+`|\"[^\"]+\"|\[[^\]]+\]|[A-Za-z_][\w$#]*)"
NAME_RE = rf"({_IDENT}(?:\s*\.\s*{_IDENT}){{0,3}})"
CREATE_RE = re.compile(
    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:OR\s+ALTER\s+)?(?:(?:GLOBAL|LOCAL)\s+)?(?:TEMPORARY\s+|TEMP\s+)?"
    r"(?:ALGORITHM\s*=\s*\w+\s+)?(?:DEFINER\s*=\s*\S+\s+)?(?:SQL\s+SECURITY\s+\w+\s+)?"
    r"(?:NO\s*FORCE\s+|FORCE\s+)?(?:EDITIONABLE\s+|NONEDITIONABLE\s+)?(?:PUBLIC\s+)?"
    r"(TABLE|MATERIALIZED\s+VIEW|VIEW|SYNONYM)\s+(?:IF\s+NOT\s+EXISTS\s+)?" + NAME_RE,
    re.IGNORECASE)
WRITE_RE = re.compile(r"\b(INSERT\s+(?:IGNORE\s+)?INTO|REPLACE\s+INTO|MERGE\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE\s+TABLE)\s+"
                      + NAME_RE, re.IGNORECASE)


# ---------------------------------------------------------------- 경로·읽기

def datasources_path():
    return os.path.join(workspace(), "knowledge", "DATASOURCES.yaml")


def base_dir(path):
    """tables_from 의 상대경로 기준: 지도 파일이 knowledge/ 아래면 workspace/<project>/, 아니면 지도 파일 폴더."""
    d = os.path.dirname(os.path.abspath(path))
    return os.path.dirname(d) if os.path.basename(d) == "knowledge" else d


def load(path=None):
    p = path or datasources_path()
    if not os.path.exists(p):
        return None
    return load_yaml(p)


def norm(name):
    """테이블 이름 정규화: 따옴표·역따옴표·대괄호 제거, 스키마·DB 접두 제거(마지막 마디), 대문자."""
    s = re.sub(r"[`\"\[\]\s]", "", str(name or ""))
    return s.split(".")[-1].upper()


def as_list(v):
    if v in (None, ""):
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


def entry_table(e):
    """inbound_tables·merged_tables 항목은 문자열 또는 {table, ...}."""
    return e.get("table") if isinstance(e, dict) else e


# ---------------------------------------------------------------- 주석 제거·CREATE 추출

def strip_comments(text, ext):
    """주석을 지운다(줄 번호 보존). SQL·XML 은 -- 줄 주석, Java 계열은 // 줄 주석, 공통으로 /* */·<!-- -->."""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    t = re.sub(r"/\*.*?\*/", blank, text, flags=re.S)
    t = re.sub(r"<!--.*?-->", blank, t, flags=re.S)
    if ext in (".sql", ".xml", ".yml", ".yaml"):
        t = re.sub(r"--[^\n]*", blank, t)
    if ext in (".java", ".kt", ".groovy"):
        t = re.sub(r"(?m)^\s*//[^\n]*", blank, t)
    if ext in (".yml", ".yaml"):
        t = re.sub(r"(?m)^\s*#[^\n]*", blank, t)
    return t


def extract_creates(text, ext=".sql"):
    """[(줄 번호, 종류, 원래 이름)] — CREATE TABLE·VIEW·SYNONYM."""
    t = strip_comments(text, ext)
    out = []
    for m in CREATE_RE.finditer(t):
        kind = re.sub(r"\s+", " ", m.group(1).upper())
        out.append((t.count("\n", 0, m.start()) + 1, kind, re.sub(r"\s+", "", m.group(2))))
    return out


def extract_writes(text, ext):
    t = strip_comments(text, ext)
    out = []
    for m in WRITE_RE.finditer(t):
        out.append((t.count("\n", 0, m.start()) + 1, re.sub(r"\s+", " ", m.group(1).upper()),
                    re.sub(r"\s+", "", m.group(2))))
    return out


def read_text(p):
    with open(p, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def resolve(path, base):
    if os.path.isabs(path):
        return path
    for b in (base, ROOT):
        p = os.path.normpath(os.path.join(b, path))
        if os.path.exists(p):
            return p
    return os.path.normpath(os.path.join(base, path))


# ---------------------------------------------------------------- 지도 해석

def main_entry(data):
    for d in (data or {}).get("datasources") or []:
        if isinstance(d, dict) and d.get("role") == "main":
            return d
    return None


def main_tables(data, base):
    """주 데이터소스 이관 대상 테이블(정규화 이름) → 출처 표시."""
    m = main_entry(data) or {}
    out = {}
    for f in as_list(m.get("tables_from")):
        p = resolve(str(f), base)
        if os.path.isfile(p):
            for _ln, kind, name in extract_creates(read_text(p), os.path.splitext(p)[1].lower() or ".sql"):
                out.setdefault(norm(name), f"tables_from:{f}")
    for t in as_list(m.get("tables")):
        out.setdefault(norm(t), "tables")
    for e in as_list(m.get("inbound_tables")):
        out[norm(entry_table(e))] = "inbound"
    for e in as_list(m.get("merged_tables")):
        out.setdefault(norm(entry_table(e)), "merged")
    out.pop("", None)
    return out


def inbound_set(data):
    m = main_entry(data) or {}
    return {norm(entry_table(e)) for e in as_list(m.get("inbound_tables")) if entry_table(e)}


def external_index(data):
    """외부·범위 밖 데이터소스 테이블(정규화 이름) → [데이터소스 id…]. 미확정 외부 테이블은 'unresolved'."""
    idx = {}
    for d in (data or {}).get("datasources") or []:
        if not isinstance(d, dict) or d.get("role") not in ("external", "out_of_scope"):
            continue
        for t in as_list(d.get("tables")):
            idx.setdefault(norm(t), [])
            if d.get("id") not in idx[norm(t)]:
                idx[norm(t)].append(str(d.get("id")))
    for e in as_list((data or {}).get("unresolved_tables")):
        n = norm(entry_table(e))
        idx.setdefault(n, [])
        if "unresolved" not in idx[n]:
            idx[n].append("unresolved")
    idx.pop("", None)
    return idx


def find_ds(data, ds_id):
    for d in (data or {}).get("datasources") or []:
        if isinstance(d, dict) and str(d.get("id")) == str(ds_id):
            return d
    return None


# ---------------------------------------------------------------- 검증

def _scan_secrets(node, where, errs):
    if isinstance(node, dict):
        for k, v in node.items():
            if str(k).lower() in FORBIDDEN_KEYS:
                errs.append(f"{where}.{k}: 접속 정보·계정 키는 지도에 두지 않는다 (id·엔진·용도·이관 여부·테이블 이름만)")
            _scan_secrets(v, f"{where}.{k}", errs)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _scan_secrets(v, f"{where}[{i}]", errs)
    elif isinstance(node, str) and SECRET_VALUE_RE.search(node):
        errs.append(f"{where}: 접속 문자열·비밀값으로 보이는 값이 있다 — 지우고 경로·변수명만 남긴다")


def validate(data, base):
    """(errors, warnings). errors 가 있으면 지도를 믿을 수 없으므로 검사를 차단한다."""
    errs, warns = [], []
    if not isinstance(data, dict):
        return ["지도 파일이 비었거나 형식이 잘못됐다"], warns
    if data.get("schema") != 1:
        errs.append("schema 는 1 이어야 한다")
    _scan_secrets(data, "DATASOURCES", errs)
    dss = data.get("datasources")
    if not isinstance(dss, list) or not dss:
        errs.append("datasources 목록이 비었다")
        return errs, warns
    ids, mains = set(), []
    for i, d in enumerate(dss):
        if not isinstance(d, dict):
            errs.append(f"datasources[{i}]: 객체여야 한다")
            continue
        did = str(d.get("id") or "")
        if not did:
            errs.append(f"datasources[{i}]: id 가 없다")
        elif did in ids:
            errs.append(f"{did}: id 중복")
        ids.add(did)
        role = d.get("role")
        if role not in ROLES:
            errs.append(f"{did}: role 은 {'|'.join(ROLES)} 중 하나 (현재: {role})")
        if not str(d.get("engine") or "").strip():
            errs.append(f"{did}: engine(운영 프로필 기준 AS-IS 엔진)이 비었다")
        if role == "main":
            mains.append(did)
            for f in as_list(d.get("tables_from")):
                if not os.path.isfile(resolve(str(f), base)):
                    errs.append(f"{did}: tables_from 파일이 없다: {f}")
            if not as_list(d.get("tables_from")) and not as_list(d.get("tables")):
                warns.append(f"{did}: 이관 대상 테이블(tables_from·tables)이 비었다 — 외부 테이블과 이름이 겹치면 전부 차단된다")
            for key in ("inbound_tables", "merged_tables"):
                for e in as_list(d.get(key)):
                    if not entry_table(e):
                        errs.append(f"{did}.{key}: table 이 빈 항목이 있다")
                    elif not isinstance(e, dict) or not str(e.get("evidence") or "").strip():
                        warns.append(f"{did}.{key}: {entry_table(e)} 에 근거(evidence)가 없다 — "
                                     "다른 스키마·시스템 테이블을 주 DB 소유로 본 판단이므로 근거를 적는다")
        else:
            if as_list(d.get("tables_from")) or as_list(d.get("inbound_tables")) or as_list(d.get("merged_tables")):
                errs.append(f"{did}: tables_from·inbound_tables·merged_tables 는 main 에만 둔다")
            if role == "external" and not as_list(d.get("tables")):
                warns.append(f"{did}: 외부 데이터소스인데 tables 가 비었다 — CREATE 금지 검사가 이 데이터소스를 보지 못한다")
    for i, s in enumerate(as_list(data.get("local_stubs"))):
        where = f"local_stubs[{i}]"
        if not isinstance(s, dict) or not str(s.get("table") or "").strip():
            errs.append(f"{where}: table 이 없다")
            continue
        globs = as_list(s.get("files"))
        if not globs:
            errs.append(f"{where}: files(허용할 파일 경로 glob)가 없다 — 예외는 파일 단위로만 준다")
        for g in globs:
            if not re.search(r"test", str(g), re.I):
                errs.append(f"{where}: files {g} 는 시험 데이터 경로가 아니다 — 로컬 시험 대체물만 예외로 둔다")
        if not str(s.get("evidence") or "").strip():
            errs.append(f"{where}: evidence(로컬에서만 실행된다는 근거)가 없다")
        if not str(s.get("decided_by") or "").startswith("사람:"):
            errs.append(f"{where}: decided_by 는 '사람:<이름>' 이어야 한다 — 외부 테이블 CREATE 예외는 사람만 준다")
    for i, e in enumerate(as_list(data.get("pre_existing_violations"))):
        where = f"pre_existing_violations[{i}]"
        if not isinstance(e, dict) or not str(e.get("table") or "").strip():
            errs.append(f"{where}: table 이 없다")
            continue
        if not as_list(e.get("files")):
            errs.append(f"{where}: files(이 위반이 있는 파일 경로 glob)가 없다 — 부채는 파일 단위로만 등록한다")
        if not str(e.get("found_at") or "").strip():
            errs.append(f"{where}: found_at(발견 회차·시각)이 없다")
        if not str(e.get("evidence") or "").strip():
            errs.append(f"{where}: evidence(무엇을 근거로 기존 부채로 보는가)가 없다")
        oi = str(e.get("decision_oi") or "")
        if not re.fullmatch(r"OI-\d{4}", oi):
            errs.append(f"{where}: decision_oi 는 'OI-0000' 형식의 확인 필요 항목 id 여야 한다 — "
                        "부채가 영구 면제가 되지 않게 닫을 항목을 반드시 연결한다")
    if len(mains) != 1:
        errs.append(f"role: main 데이터소스는 정확히 하나여야 한다 (현재 {len(mains)}개: {', '.join(mains) or '-'})")
    if not str(data.get("target_engine") or "").strip():
        warns.append("target_engine(주 데이터소스의 TO-BE 엔진)이 비었다")
    return errs, warns


# ---------------------------------------------------------------- 판정

def judge(data, base, ds_id, tables, write=False):
    """statement 하나의 이관 판정. 반환 dict: decision·dialect·reason·tables."""
    d = find_ds(data, ds_id)
    names = [norm(t) for t in tables if norm(t)]
    if not d:
        return {"decision": "error", "dialect": "", "reason": f"지도에 없는 데이터소스: {ds_id}", "tables": names}
    role = d.get("role")
    mains = main_tables(data, base)
    ext = external_index(data)
    if role == "external":
        same = [n for n in names if n in mains]
        reason = f"외부 데이터소스({ds_id}, 운영 엔진 {d.get('engine')}) 실행 — 원래 방언 그대로 그 데이터소스로 실행한다"
        if same:
            reason += f". 이관 대상과 같은 이름({', '.join(same)})이지만 다른 DB 의 테이블이다 — 대상 DB 방언으로 바꾸지 않는다"
        return {"decision": "keep_dialect", "dialect": str(d.get("engine")), "reason": reason, "tables": names}
    if role == "out_of_scope":
        return {"decision": "out_of_scope", "dialect": str(d.get("engine")),
                "reason": f"범위 밖 데이터소스({ds_id}) — 이번 차수에 구성하지 않는다(범위에 들어오면 재검토)", "tables": names}
    missing = [n for n in names if n not in mains]
    if missing:
        hint = [f"{n}({'/'.join(ext[n])} 소속)" for n in missing if n in ext]
        reason = f"주 데이터소스 실행이지만 이관 대상에 없는 테이블: {', '.join(missing)} — 이관 안 함(근거 부족 기록)"
        if hint:
            reason += f". 외부 데이터소스 테이블과 이름이 같다: {', '.join(hint)} — 실행 세션을 다시 확인한다"
        return {"decision": "not_migrated", "dialect": "", "reason": reason, "tables": names}
    reason = "주 데이터소스 실행 + 테이블 전부 이관 대상 — 대상 DB 방언으로 변환한다"
    inb = sorted(set(names) & inbound_set(data))
    if inb and write:
        reason += f". 주의: 수신 테이블({', '.join(inb)})에 쓰기 — 외부 시스템이 채우는 테이블이므로 테스트 시드 외에는 쓰지 않는다"
    return {"decision": "convert", "dialect": str(data.get("target_engine") or ""), "reason": reason, "tables": names}


# ---------------------------------------------------------------- 검사

def local_stub_for(data, table_norm, relpath):
    """사람이 예외로 둔 로컬 시험 대체물(local_stubs)이면 그 항목. 테이블과 파일 glob 이 모두 맞아야 한다."""
    rp = relpath.replace(os.sep, "/")
    for s in as_list((data or {}).get("local_stubs")):
        if not isinstance(s, dict) or norm(str(s.get("table") or "")) != table_norm:
            continue
        if any(fnmatch.fnmatch(rp, str(g)) for g in as_list(s.get("files"))):
            return s
    return None


def pre_existing_for(data, table_norm, relpath):
    """기존 부채(pre_existing_violations)로 등록된 위반이면 그 항목.

    배경(brownfield): 지도를 처음 만든 회차에 이미 target 안에 있던 위반은 파이프라인이 만든 것이 아니고,
    그 단계가 고칠 수도(남의 영역) 면제할 수도(예외는 사람만) 없다. 그대로 두면 다음 단계의 첫 업무 slice 가
    자기 변경과 무관한 이유로 막힌다. 그래서 **기준선** 을 둔다 — 등록된 것만 warn 으로 내리고
    새로 생긴 것은 critical 로 남긴다(규약 9절의 "기준선보다 나빠지지 않았는가" 와 같은 방식).
    local_stubs 와 다르다: 그쪽은 사람만 만드는 시험 전용 예외고, 이쪽은 에이전트가 등록할 수 있는 부채 목록이며
    decision_oi(그 부채를 닫을 확인 필요 항목)를 반드시 달아야 한다 — 영구 면제가 되지 않게.
    """
    rp = relpath.replace(os.sep, "/")
    for e in as_list((data or {}).get("pre_existing_violations")):
        if not isinstance(e, dict) or norm(str(e.get("table") or "")) != table_norm:
            continue
        if any(fnmatch.fnmatch(rp, str(g)) for g in as_list(e.get("files"))):
            return e
    return None


def is_test_path(rs):
    return ("/src/test/" in rs or "/__tests__/" in rs or "/tests/" in rs or "/e2e/" in rs)


def candidate_files(td, files=None):
    """files 가 없으면 target 전체(SQL·코드·설정). 있으면 그 파일들 + target 의 모든 SQL 파일."""
    out = set()
    for dp, dns, fns in os.walk(td):
        dns[:] = sorted(x for x in dns if x not in SKIP_DIRS and not x.startswith("."))
        for fn in fns:
            low = fn.lower()
            if low.endswith(SQL_EXTS) or (files is None and low.endswith(CODE_EXTS)):
                out.add(os.path.normpath(os.path.join(dp, fn)))
    for f in files or []:
        p = f if os.path.isabs(f) else os.path.join(td, f)
        if os.path.isfile(p) and p.lower().endswith(SQL_EXTS + CODE_EXTS):
            rs = "/" + safe_relpath(p, td)
            if not any(f"/{x}/" in rs for x in SKIP_DIRS):
                out.add(os.path.normpath(p))
    return sorted(out)


def scan_ddl(td, data, base, files=None):
    """외부 테이블 CREATE 검사. 결과 dict(결정적)."""
    td = os.path.abspath(td)
    mains = main_tables(data, base)
    ext = external_index(data)
    inbound = inbound_set(data)
    findings, scanned = [], 0
    baseline_hit = set()
    for p in candidate_files(td, files):
        r = safe_relpath(p, td)
        ext_name = os.path.splitext(p)[1].lower()
        try:
            text = read_text(p)
        except OSError:
            continue
        scanned += 1
        if "CREATE" in text.upper():
            for ln, kind, raw in extract_creates(text, ext_name):
                n = norm(raw)
                stub = local_stub_for(data, n, r)
                if n in ext and n not in mains and stub:
                    findings.append({"severity": "warn", "kind": "local_stub", "file": r, "line": ln,
                                     "object": kind, "table": raw, "datasources": ext[n],
                                     "detail": f"CREATE {kind} {raw} — 외부 데이터소스({'/'.join(ext[n])}) 테이블의 로컬 시험 대체물"
                                               f"(사람 예외: {stub.get('decided_by')}). 새로 만들지 않는다"})
                elif n in ext and n not in mains and pre_existing_for(data, n, r):
                    pe = pre_existing_for(data, n, r)
                    baseline_hit.add(id(pe))
                    findings.append({"severity": "warn", "kind": "pre_existing", "file": r, "line": ln,
                                     "object": kind, "table": raw, "datasources": ext[n],
                                     "decision_oi": str(pe.get("decision_oi") or ""),
                                     "detail": f"CREATE {kind} {raw} — 외부 데이터소스({'/'.join(ext[n])}) 테이블을 우리 DB 에 만든다. "
                                               f"지도에 기존 부채로 등록됨(발견 {pe.get('found_at')}, 닫을 항목 {pe.get('decision_oi')}) — "
                                               "새로 만드는 것은 여전히 금지다"})
                elif n in ext and n not in mains:
                    findings.append({"severity": "critical", "kind": "external_create", "file": r, "line": ln,
                                     "object": kind, "table": raw, "datasources": ext[n],
                                     "detail": f"CREATE {kind} {raw} — 외부 데이터소스({'/'.join(ext[n])}) 테이블을 우리 DB 에 만든다"})
                elif n in mains and (n in ext or mains[n] in ("inbound", "merged")):
                    what = {"inbound": "수신 테이블(외부 시스템이 우리 DB 로 적재)", "merged": "다른 스키마·데이터소스에서 합친 테이블"}
                    note = what.get(mains[n], "이관 대상")
                    if n in ext:
                        note += f" — 외부 데이터소스({'/'.join(ext[n])})에 같은 이름이 있다(동명, 허용)"
                    findings.append({"severity": "info", "kind": "overlap" if n in ext else mains[n], "file": r,
                                     "line": ln, "object": kind, "table": raw, "datasources": ext.get(n, []),
                                     "detail": f"CREATE {kind} {raw} — {note}"})
        rs = "/" + r
        if inbound and ext_name in (".xml", ".java", ".kt", ".groovy") and "/src/main/" in rs and not is_test_path(rs):
            for ln, verb, raw in extract_writes(text, ext_name):
                if norm(raw) in inbound:
                    findings.append({"severity": "warn", "kind": "inbound_write", "file": r, "line": ln,
                                     "object": verb, "table": raw, "datasources": [],
                                     "detail": f"{verb} {raw} — 수신 테이블은 외부 시스템이 채운다. 테스트 시드 외에 우리 코드가 쓰지 않는다"})
    # 기준선이 썩지 않게: 등록해 둔 부채가 더는 걸리지 않으면 목록에서 지우라고 알린다.
    # (파일 목록을 준 부분 검사에서는 안 걸리는 것이 정상이므로 전수 검사일 때만 본다)
    stale_baseline = []
    if files is None:
        for e in as_list((data or {}).get("pre_existing_violations")):
            if isinstance(e, dict) and id(e) not in baseline_hit:
                stale_baseline.append(f"{e.get('table')} ({', '.join(str(g) for g in as_list(e.get('files')))})")
    findings.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], f["file"], f["line"], f["table"]))
    counts = {"critical": 0, "warn": 0, "info": 0}
    for f in findings:
        counts[f["severity"]] += 1
    return {"schema": 1, "target": td.replace(os.sep, "/"), "mode": "full" if files is None else "files+sql",
            "scanned_files": scanned, "main_tables": len(mains), "external_tables": len(ext),
            "counts": counts, "findings": findings, "stale_baseline": stale_baseline}


# ---------------------------------------------------------------- 명령

def _load_or_exit(args):
    path = os.path.abspath(args.file) if args.file else datasources_path()
    data = load(path)
    return path, data


def cmd_validate(args):
    path, data = _load_or_exit(args)
    if data is None:
        print(f"[datasources] 지도 파일이 없다: {safe_relpath(path, ROOT)} (templates/DATASOURCES.yaml 로 만든다)")
        return 2
    errs, warns = validate(data, base_dir(path))
    for e in errs:
        print(f"- 오류 {e}")
    for w in warns:
        print(f"- 경고 {w}")
    mains = main_tables(data, base_dir(path)) if not errs else {}
    print(f"데이터소스 {len(data.get('datasources') or [])}개 · 이관 대상 테이블 {len(mains)} · "
          f"외부 테이블 {len(external_index(data))} · 오류 {len(errs)} · 경고 {len(warns)}")
    return 1 if errs else 0


def cmd_judge(args):
    path, data = _load_or_exit(args)
    if data is None:
        print(f"[datasources] 지도 파일이 없다: {safe_relpath(path, ROOT)}")
        return 2
    tables = [t.strip() for t in re.split(r"[,\s]+", args.tables or "") if t.strip()]
    res = judge(data, base_dir(path), args.datasource, tables, write=args.write)
    if args.format == "json":
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(f"판정: {res['decision']}  방언: {res['dialect'] or '-'}")
        print(f"근거: {res['reason']}")
    return 1 if res["decision"] == "error" else 0


def cmd_lookup(args):
    path, data = _load_or_exit(args)
    if data is None:
        print(f"[datasources] 지도 파일이 없다: {safe_relpath(path, ROOT)}")
        return 2
    n = norm(args.table)
    mains = main_tables(data, base_dir(path))
    ext = external_index(data)
    m = main_entry(data) or {}
    print(f"{n}: 이관 대상({m.get('id', 'main')}) = {'예 (' + mains[n] + ')' if n in mains else '아니오'}"
          f" · 외부 = {', '.join(ext.get(n, [])) or '없음'}")
    if n in mains and n in ext:
        print("동명 주의: 실행 세션으로 판정한다 — 외부 세션 statement 는 원래 방언 유지, 주 세션 statement 만 변환")
    return 0


def cmd_check(args):
    path, data = _load_or_exit(args)
    root = args.target or target_dir()
    if data is None:
        msg = f"데이터소스 지도가 없어 외부 테이블 CREATE 검사를 건너뛴다: {safe_relpath(path, ROOT)}"
        if args.format == "json":
            print(json.dumps({"schema": 1, "skipped": True, "reason": msg}, ensure_ascii=False, indent=2))
        else:
            print("[생략] " + msg)
        return 0
    if not root or not os.path.isdir(root):
        print(f"[datasources] 점검 대상 디렉토리가 없다: {root}", file=sys.stderr)
        return 2
    errs, warns = validate(data, base_dir(path))
    res = scan_ddl(root, data, base_dir(path), args.files)
    res["map_errors"], res["map_warnings"] = errs, warns
    blocked = bool(errs) or res["counts"]["critical"] > 0
    if args.format == "json":
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(f"대상: {root} ({res['mode']}, 파일 {res['scanned_files']}개)")
        print(f"이관 대상 테이블 {res['main_tables']} · 외부 테이블 {res['external_tables']}")
        for e in errs:
            print(f"- [지도 오류] {e}")
        for w in warns:
            print(f"- [지도 경고] {w}")
        for sb in res.get("stale_baseline") or []:
            print(f"- [지도 경고] 기존 부채 목록에 남아 있는데 더는 걸리지 않는다: {sb} — 해소됐으면 지운다")
        c = res["counts"]
        print(f"발견: critical {c['critical']} · warn {c['warn']} · info {c['info']}")
        for f in res["findings"][:args.limit]:
            print(f"- [{f['severity']}] {f['file']}:{f['line']}  {f['detail']}")
        rest = len(res["findings"]) - args.limit
        if rest > 0:
            print(f"  ... 외 {rest}건 (--format json 으로 전체 확인)")
        print("결과: " + ("차단" if blocked else "통과"))
    return 1 if blocked else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="데이터소스 지도로 SQL 이관 판정·외부 테이블 CREATE 금지 검사")
    ap.add_argument("--file", help="지도 파일 (기본: workspace/<project>/knowledge/DATASOURCES.yaml)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate", help="규격·비밀정보 검사")
    j = sub.add_parser("judge", help="statement 하나의 이관 판정")
    j.add_argument("--datasource", required=True, help="실행 데이터소스 id (호출 세션 기준)")
    j.add_argument("--tables", required=True, help="statement 가 쓰는 테이블 (쉼표 구분)")
    j.add_argument("--write", action="store_true", help="쓰기 statement 면 표시 (수신 테이블 쓰기 주의)")
    j.add_argument("--format", choices=["human", "json"], default="human")
    lk = sub.add_parser("lookup", help="테이블 소속 조회")
    lk.add_argument("table")
    c = sub.add_parser("check", help="외부 테이블 CREATE 검사")
    c.add_argument("target", nargs="?", help="점검할 디렉토리 (생략 시 config 의 target_dir)")
    c.add_argument("--files", nargs="+", help="이 파일들 + target 의 모든 SQL 파일만 본다")
    c.add_argument("--format", choices=["human", "json"], default="human")
    c.add_argument("--limit", type=int, default=50)
    args = ap.parse_args(argv)
    return {"validate": cmd_validate, "judge": cmd_judge, "lookup": cmd_lookup, "check": cmd_check}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
