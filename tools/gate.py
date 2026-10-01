#!/usr/bin/env python3
# gate.py — 단계 레포트의 게이트 메타(pa-meta 블록)를 기계적으로 검증한다.
#
# 목적: "빌드·테스트 통과", "확인 필요 있음" 같은 문장을 사람이 읽고 믿는 대신
#       (1) 실행 증거(명령·종료코드·테스트 개수)가 실제로 있는지
#       (2) target_dir 의 git 실측(HEAD/브랜치/dirty/변경파일)이 레포트 기재와 같은지
#       (3) slice 의 traits 가 요구하는 검증 축이 닫히거나 예약됐는지
#       (4) 요구사항 ID 가 테스트까지 이어지는지
#       (5) 미해결 항목(open item)이 RR 이나 승인 없이 조용히 사라지지 않는지
#       (6) 레포트에 자격증명·개인정보가 섞이지 않았는지
#       (7) 바뀐 소스가 상품화 품질 규칙(Javadoc·로깅·traceId·Mapper 주석·이모지 금지)을 지키는지 (tools/quality.py)
#       (8) 테스트 개수·실패 수가 실제 결과 파일(JUnit XML)과 같은지 (gates[].results)
#       (9) 레포트에 이모지가 없는지
#       (12) 브라우저 화면 기준 이미지가 모두 승인됐고 픽셀 비교 실패가 없는지 (tools/visual.py)
#       (11) 잠긴 기대 동작 테스트(spec)가 그대로이고 전부 실행·통과했는지 (tools/spec_lock.py)
#       (10) 공통 계약 준수 — 업무 slice 의 공통 복제·공통 영역 침범, common-port 의 계약 이행 (tools/common_contract.py)
#       (14) 착수 보류(hold) slice 의 완료 기록, slice 의 모듈(module) 경로 밖 변경 (config project.module_paths)
#       (15) 판단으로 정한 것(대체 매핑·'불필요' 판정·의미 차이 수용·범위 제외·지시와 다른 결정)이 판단 기록(JD)으로 남고,
#            검증 단계(5·7)가 영향 slice 마다 다시 확인했는지 (tools/judgment.py, pipeline-core §21)
#       (13) 큰 slice 의 unit 분할 — unit 은 배정된 AS-IS 를 빠짐없이 다뤘는지, slice 완료는 모든 unit 완료·흐름 테스트·
#            AS-IS 전수 대조를 거쳤는지 (tools/slice_units.py)
#       를 도구가 대조한다.
#
# 사용법:
#   python tools/gate.py check --report workspace/<p>/reports/2609221130_stage2_notice_....md
#   python tools/gate.py check --stage 2 --slice notice          # 최신 레포트 자동 탐색
#   python tools/gate.py check --stage 5 --slice notice --format json
#   python tools/gate.py check --stage 2 --slice claim --unit intake   # unit 레포트 (큰 slice 를 나눈 경우)
#   python tools/gate.py template --stage 2 --slice notice        # 메타 블록 골격 출력
#   python tools/gate.py plan [--to 5] [--max 4]                  # /run 진행 계획(웨이브·축·멈춤 조건)
#   python tools/gate.py trace [--slice notice] [--strict]        # 요구사항 → 계약 → 테스트 추적 대조
#   python tools/gate.py secrets <파일|디렉토리> ...              # 비밀정보 스캔만
#   python tools/gate.py oi new --stage 2 --slice notice --kind unverified --severity high \
#          --summary "..." --evidence "파일:라인" --target 5
#   python tools/gate.py oi import --report <레포트> --write     # pa-meta 의 open_items 일괄 채번
#   python tools/gate.py oi list [--status open] [--slice notice]
#   python tools/gate.py oi set OI-0003 converted --rr RR-0041 [--note "..."]
#   python tools/gate.py oi set OI-0004 accepted --approved-by 사용자 --expiry 2026-10-31 --note "..."
#   python tools/gate.py oi set OI-0004 open --target 2 --note "..."        # 닫을 단계 재예약
#   python tools/gate.py oi set OI-0005 resolved --jd JD-0002              # decision 해소는 판단 기록과 연결
#
# 종료 코드: 0 통과(WARN 포함) · 1 차단(FAIL) · 2 입력/실행 오류
# 의존성: pyyaml

import argparse
import datetime
import glob
import json
import os
import re
import subprocess
import sys

from _common import (ROOT, config, dump_yaml, file_lock, fix_console_encoding, load_yaml,
                     safe_relpath, target_dir, workspace)
import judgment

# Windows 콘솔(cp949)에서도 한글이 깨지지 않도록 출력 인코딩을 고정한다
fix_console_encoding()

KST = datetime.timezone(datetime.timedelta(hours=9), name="KST")

META_START = "<!-- pa-meta:start"
META_END = "pa-meta:end -->"

RESULTS = ("done", "done_with_gaps", "blocked", "failed")
OI_KINDS = ("evidence_gap", "decision", "unverified", "risk", "deferred")

# 검증 축 — "앞 단계가 보지 못하는 축" 에서만 새 결함이 나온다는 실측(채점표 7건)에서 나온 분류
AXES = ("unit", "module", "real-db", "real-server", "browser", "concurrency", "security-static")
# 모든 slice 가 공통으로 요구하는 축. module 이상은 slice 특성(traits)이 요구할 때만 본다 —
# 기본 요구를 넓히면 axis 를 적지 않은 기존 관행이 곧바로 차단돼 도구가 무시당한다.
BASE_AXES = ("unit",)
# slice 특성(traits) → 반드시 닫아야 하는 축. config 의 verification.trait_axes 로 덮어쓸 수 있다.
TRAIT_AXES = {
    "file-upload": ["real-server"],       # 서블릿/파서 단계가 서비스보다 먼저 갈린다 (multipart NUL·413 실측)
    "transaction": ["real-db"],           # H2 로는 못 보는 방언·캐스트 (Timestamp·H2 override 실측)
    "batch": ["real-db"],
    "counter": ["concurrency"],           # 조회수·시퀀스 (REQUIRES_NEW 커넥션 2중 점유 실측)
    "concurrency-sensitive": ["concurrency"],
    "rich-text": ["browser"],             # jsdom 이 못 잡는 로드 크래시 (Tiptap 실측)
    "dom-heavy": ["browser"],
    "auth": ["real-server"],              # 필터·프록시 경로 (XFF 위조 실측)
    "proxy-header": ["real-server"],
    "external-io": ["real-server"],
    "sanitizer": ["security-static"],
}
# 각 축을 닫는 것이 자연스러운 단계 (안내용)
AXIS_STAGE = {"unit": 2, "module": 2, "real-db": 5, "real-server": 5,
              "browser": 4, "concurrency": 7, "security-static": 6}
# 포함 관계 — 바깥 축을 닫으면 안쪽 축도 닫힌 것으로 본다 (실 서버 테스트는 컨텍스트·로직을 이미 지난다)
AXIS_IMPLIES = {
    "module": ["unit"],
    "real-db": ["unit", "module"],
    "real-server": ["unit", "module"],
    "browser": ["unit"],
}


def expand_axes(axes):
    out = set()
    for a in axes:
        if not a:
            continue
        out.add(a)
        out.update(AXIS_IMPLIES.get(a, []))
    return out


def gate_axes(g):
    """gates[].axis 는 문자열 또는 배열."""
    a = g.get("axis")
    if isinstance(a, str):
        return [a]
    if isinstance(a, list):
        return [x for x in a if isinstance(x, str)]
    return []
SEVERITIES = ("blocker", "high", "medium", "low")
OI_STATUSES = ("open", "resolved", "converted", "accepted")
BLOCKING_SEV = ("blocker", "high")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")

# 개발 단계(빌드·테스트 게이트가 완료 조건인 단계)
DEV_STAGES = (2, 3, 4)

# 자격증명·개인정보 패턴. 값이 플레이스홀더면 건너뛴다.
SECRET_PATTERNS = {
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,}\b"),
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
    "bearer": re.compile(r"(?i)authorization\s*[:=]\s*bearer\s+[A-Za-z0-9._~+/-]{12,}"),
    "password": re.compile(r"(?i)(?:password|passwd|pwd|secret|token|api[_-]?key)\s*[:=]\s*(\S+)"),
    "cookie": re.compile(r"(?i)(?:set-cookie|jsessionid|session(?:id|token))\s*[:=]\s*(\S+)"),
    "phone": re.compile(r"(?<!\d)01[016789][- ]?\d{3,4}[- ]?\d{4}(?!\d)"),
    "rrn": re.compile(r"(?<!\d)\d{6}[- ]\d{7}(?!\d)"),
}
# 플레이스홀더로 간주해 넘기는 값
PLACEHOLDER_RE = re.compile(
    r"^[\"'`]?(?:\*+|x{3,}|<[^>]*>|\{\{?[^}]*\}?\}|\$\{[^}]*\}|redacted|masked|dummy|sample|example|changeme|"
    r"password|secret|token|test|none|null|nil|생략|마스킹|비공개)[\"'`,.]?$",
    re.IGNORECASE,
)


def now_kst(full=True) -> str:
    n = datetime.datetime.now(KST)
    return n.strftime("%Y-%m-%d %H:%M") if full else n.strftime("%y%m%d%H%M")


WS = workspace()
REPORTS = os.path.join(WS, "reports")
OI_FILE = os.path.join(WS, "open-items.yaml")
RR_DIR = os.path.join(WS, "refactor-requests")
# 쓰기 훅(guard.py)은 기록하려는 새 state 를 임시 파일로 넘겨, 쓰기 전에 그 내용으로 판정하게 한다
STATE = os.environ.get("PA_STATE_FILE") or os.path.join(WS, "state.yaml")


# ---------------------------------------------------------------- 결과 형식

def finding(severity, field, message, action=""):
    return {"severity": severity, "field": field, "message": message, "action": action}


def result_of(hook, findings, evidence, skipped=False):
    blocking = any(f["severity"] in ("FAIL", "CRITICAL") for f in findings)
    if skipped:
        res = "SKIPPED"
    elif blocking:
        res = "FAIL"
    elif findings:
        res = "WARN"
    else:
        res = "PASS"
    return {"hook": hook, "result": res, "findings": findings, "evidence": evidence}


def fail(field, message, action=""):
    return finding("FAIL", field, message, action)


def warn(field, message, action=""):
    return finding("WARN", field, message, action)


# ---------------------------------------------------------------- 메타 파싱

def extract_meta(path):
    """레포트에서 pa-meta 블록의 JSON 을 꺼낸다. (meta, error)"""
    if not os.path.exists(path):
        return None, f"레포트가 없다: {path}"
    with open(path, encoding="utf-8") as f:
        text = f.read()
    s, e = text.find(META_START), text.find(META_END)
    if s < 0 or e < 0 or e <= s:
        return None, "pa-meta 블록이 없다 (templates/report-meta.md 형식으로 레포트 끝에 넣는다)"
    block = text[s + len(META_START):e]
    l, r = block.find("{"), block.rfind("}")
    if l < 0 or r < l:
        return None, "pa-meta 블록에 JSON 객체가 없다"
    try:
        meta = json.loads(block[l:r + 1])
    except json.JSONDecodeError as ex:
        return None, f"pa-meta JSON 파싱 실패: {ex.msg} (line {ex.lineno})"
    if not isinstance(meta, dict):
        return None, "pa-meta 는 객체여야 한다"
    return meta, None


def find_report(stage, slice_id, unit=None):
    """최신 레포트 자동 탐색: yymmddhhmm_stage<N>_<slice|all>_*.md, unit 레포트는 yymmddhhmm_stage<N>_<slice>_unit-<unit>_*.md"""
    if not os.path.isdir(REPORTS):
        return None
    if unit:
        pat = f"*_stage{stage}_{slice_id}_unit-{unit}_*.md"
    else:
        pat = f"*_stage{stage}_{slice_id}_*.md" if slice_id else f"*_stage{stage}_*.md"
    hits = glob.glob(os.path.join(REPORTS, pat))
    if not unit:   # slice 레포트를 찾을 때 unit 레포트를 집지 않는다
        hits = [h for h in hits if "_unit-" not in os.path.basename(h)]
    return sorted(hits)[-1] if hits else None


# ---------------------------------------------------------------- 훅

def hook_report_meta(ctx):
    meta, err = ctx["meta"], ctx["meta_error"]
    ev = [ctx["report"]]
    if err:
        return result_of("report-meta", [fail("meta", err, "레포트 끝에 pa-meta 블록을 넣는다")], ev)
    f = []
    if meta.get("schema") != 1:
        f.append(fail("schema", "schema 는 1 이어야 한다"))
    for key in ("stage", "result", "agent"):
        if not meta.get(key) and meta.get(key) != 0:
            f.append(fail(key, f"{key} 가 비었다"))
    if meta.get("result") not in RESULTS:
        f.append(fail("result", f"result 는 {'|'.join(RESULTS)} 중 하나여야 한다 (현재: {meta.get('result')})"))
    try:
        stage = int(meta.get("stage"))
    except (TypeError, ValueError):
        stage = None
        f.append(fail("stage", "stage 는 정수여야 한다"))
    if stage is not None and ctx["stage"] is not None and stage != ctx["stage"]:
        f.append(fail("stage", f"레포트 메타의 stage({stage}) 가 검사 대상 stage({ctx['stage']}) 와 다르다"))
    if ctx["slice"] and meta.get("slice") and meta.get("slice") != ctx["slice"]:
        f.append(fail("slice", f"메타 slice({meta.get('slice')}) 가 검사 대상({ctx['slice']}) 과 다르다"))
    if ctx.get("unit") and meta.get("unit") != ctx["unit"]:
        f.append(fail("unit", f"메타 unit({meta.get('unit') or '-'}) 가 검사 대상({ctx['unit']}) 과 다르다"))
    if not meta.get("finished_at"):
        f.append(warn("finished_at", "종료 시각이 없다"))
    return result_of("report-meta", f, ev)


def hook_gate_proof(ctx):
    """빌드·테스트 실행 증거 검사. '조용한 0건 매칭'(EXIT 0 · 0 tests)을 차단한다."""
    meta = ctx["meta"]
    ev = [ctx["report"]]
    if not meta:
        return result_of("gate-proof", [], ev, skipped=True)
    f = []
    stage = meta.get("stage")
    gates = meta.get("gates")
    if not isinstance(gates, list):
        return result_of("gate-proof", [fail("gates", "gates 배열이 없다")], ev)
    kinds = set()
    for i, g in enumerate(gates):
        fld = f"gates[{i}]"
        if not isinstance(g, dict):
            f.append(fail(fld, "게이트 항목은 객체여야 한다"))
            continue
        kind = g.get("kind")
        kinds.add(kind)
        if kind not in ("build", "test", "lint", "typecheck", "smoke", "scan", "other"):
            f.append(fail(f"{fld}.kind", f"알 수 없는 kind: {kind}"))
        if kind in ("test", "smoke", "scan"):
            axes = gate_axes(g)
            if g.get("axis") is None:
                f.append(warn(f"{fld}.axis", f"검증 축이 없다 ({'|'.join(AXES)})", "어느 축을 닫은 실행인지 적는다"))
            elif not axes:
                f.append(fail(f"{fld}.axis", "axis 는 문자열 또는 문자열 배열이어야 한다"))
            for a in axes:
                if a not in AXES:
                    f.append(fail(f"{fld}.axis", f"알 수 없는 axis: {a}"))
        if not str(g.get("command", "")).strip():
            f.append(fail(f"{fld}.command", "실행한 명령을 그대로 적는다"))
        if not isinstance(g.get("exit_code"), int):
            f.append(fail(f"{fld}.exit_code", "종료 코드(정수)를 적는다"))
        elif g["exit_code"] != 0 and meta.get("result") in ("done", "done_with_gaps"):
            f.append(fail(f"{fld}.exit_code",
                          f"종료 코드 {g['exit_code']} 인데 result={meta.get('result')} 다",
                          "게이트를 통과시키거나 result 를 blocked/failed 로 내린다"))
        if not g.get("executed_at"):
            f.append(warn(f"{fld}.executed_at", "실행 시각이 없다"))
        else:
            # 에이전트가 시각을 실측하지 않고 지어 적으면 미래 시각이 나온다 (실측: 기록 시점보다 30분 뒤)
            ts = parse_kst(g["executed_at"])
            if ts is not None and ts > datetime.datetime.now(KST).timestamp() + STALE_SLACK_SEC:
                f.append(fail(f"{fld}.executed_at", f"실행 시각 {g['executed_at']} 이 현재보다 미래다",
                              "python tools/kst_now.py --full 로 실측한 값을 적는다"))
        if kind in ("test", "smoke"):
            tc = g.get("test_count")
            if not isinstance(tc, int):
                f.append(fail(f"{fld}.test_count", "테스트 개수를 적는다 (집계 명령 근거 포함)"))
            elif tc <= 0:
                f.append(fail(f"{fld}.test_count",
                              "테스트가 0건인데 통과로 기록됐다 (필터가 아무것도 매칭하지 않은 경우)",
                              "필터 패턴을 고쳐 실제 실행 개수를 확인한다"))
            if isinstance(g.get("failures"), int) and g["failures"] > 0 and meta.get("result") == "done":
                f.append(fail(f"{fld}.failures", f"실패 {g['failures']}건인데 result=done 이다"))
    if isinstance(stage, int) and stage in DEV_STAGES and meta.get("result") in ("done", "done_with_gaps"):
        for need in ("build", "test"):
            if need not in kinds:
                f.append(fail("gates", f"{stage}단계 완료에는 {need} 게이트 기록이 필요하다"))
    return result_of("gate-proof", f, ev)


def git(cwd, *args):
    try:
        p = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=False,
                           encoding="utf-8", errors="replace")
    except OSError as ex:
        return None, str(ex)
    if p.returncode != 0:
        return None, (p.stderr or "").strip() or f"git exit {p.returncode}"
    return p.stdout.strip(), None


def hook_repo_consistency(ctx):
    """레포트가 적은 브랜치/HEAD/dirty/변경파일을 target_dir 의 git 으로 실측 대조."""
    meta = ctx["meta"]
    ev = [ctx["report"]]
    if not meta:
        return result_of("repo-consistency", [], ev, skipped=True)
    repo = meta.get("repo")
    stage = meta.get("stage")
    if repo is None:
        sev = fail if (isinstance(stage, int) and stage in DEV_STAGES) else warn
        return result_of("repo-consistency", [sev("repo", "repo(브랜치·HEAD·변경파일) 기록이 없다")], ev)
    if not isinstance(repo, dict):
        return result_of("repo-consistency", [fail("repo", "repo 는 객체여야 한다")], ev)
    f = []
    head = repo.get("head")
    if head != "NOT_CHANGED" and not (isinstance(head, str) and SHA_RE.match(head or "")):
        f.append(fail("repo.head", "head 는 커밋 SHA 또는 NOT_CHANGED 여야 한다"))
    if head == "NOT_CHANGED" and repo.get("changed_files"):
        f.append(fail("repo.changed_files", "head=NOT_CHANGED 인데 변경 파일이 있다"))
    td = ctx["target_dir"]
    # git worktree 는 .git 이 디렉토리가 아니라 파일(gitdir: …)이다 — 둘 다 인정한다
    if not td or not os.path.exists(os.path.join(td, ".git")):
        f.append(warn("repo.actual", f"target_dir git 을 찾지 못해 메타 내부 검사만 했다: {td}"))
        return result_of("repo-consistency", f, ev)
    ev.append(td)
    actual_head, e1 = git(td, "rev-parse", "HEAD")
    actual_branch, e2 = git(td, "branch", "--show-current")
    status, e3 = git(td, "status", "--porcelain")
    if e1 or e2 or e3:
        f.append(warn("repo.actual", f"git 실행 실패: {e1 or e2 or e3}"))
        return result_of("repo-consistency", f, ev)
    if head and head != "NOT_CHANGED" and actual_head and not actual_head.startswith(head):
        f.append(fail("repo.head", f"기재 HEAD({head}) 와 실제 HEAD({actual_head[:12]}) 가 다르다",
                      "레포트를 현재 HEAD 로 갱신하거나 커밋 후 다시 기록한다"))
    if repo.get("branch") and actual_branch and repo["branch"] != actual_branch:
        f.append(fail("repo.branch", f"기재 브랜치({repo['branch']}) ≠ 실제({actual_branch})"))
    if isinstance(repo.get("dirty"), bool) and repo["dirty"] != bool(status):
        f.append(fail("repo.dirty", f"기재 dirty={repo['dirty']} ≠ 실제 {bool(status)}",
                      "커밋하지 않은 변경이 있으면 dirty=true 로 적는다"))
    declared = repo.get("changed_files")
    base = repo.get("base")
    if isinstance(declared, list) and declared:
        for p in declared:
            if not isinstance(p, str) or os.path.isabs(p) or ".." in p.replace("\\", "/").split("/"):
                f.append(fail("repo.changed_files", f"repo 기준 상대경로여야 한다: {p}"))
        if base:
            diff, e4 = git(td, "diff", "--name-only", f"{base}...HEAD")
            if e4:
                f.append(warn("repo.changed_files", f"base({base}) 대조 불가: {e4}"))
            else:
                actual = {l.strip() for l in (diff or "").splitlines() if l.strip()}
                decl = {p.replace("\\", "/").strip() for p in declared if isinstance(p, str)}
                missing = sorted(actual - decl)
                extra = sorted(decl - actual)
                if missing or extra:
                    detail = []
                    if missing:
                        detail.append("누락: " + ", ".join(missing[:8]) + (" …" if len(missing) > 8 else ""))
                    if extra:
                        detail.append("초과: " + ", ".join(extra[:8]) + (" …" if len(extra) > 8 else ""))
                    f.append(fail("repo.changed_files", "기재 변경 파일이 git diff 와 다르다 (" + "; ".join(detail) + ")",
                                  "git diff --name-only base...HEAD 결과로 갱신한다"))
        else:
            f.append(warn("repo.base", "base 가 없어 변경 파일 대조를 건너뛰었다"))
    return result_of("repo-consistency", f, ev)


def load_open_items():
    if not os.path.exists(OI_FILE):
        return {"items": []}
    data = load_yaml(OI_FILE)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return {"items": []}
    return data


def rr_exists(rid):
    return bool(rid) and os.path.exists(os.path.join(RR_DIR, f"{rid}.yaml"))


def hook_open_items(ctx):
    """미해결 항목이 RR·승인 없이 사라지지 않는지. (레포트 메타 ↔ open-items.yaml 대조)"""
    meta = ctx["meta"]
    ev = [ctx["report"], OI_FILE]
    if not meta:
        return result_of("open-items", [], ev, skipped=True)
    f = []
    store = {i.get("id"): i for i in load_open_items()["items"] if isinstance(i, dict)}
    items = meta.get("open_items")
    if items is None:
        return result_of("open-items", [warn("open_items", "open_items 키가 없다 (없으면 빈 배열로 적는다)")], ev)
    if not isinstance(items, list):
        return result_of("open-items", [fail("open_items", "open_items 는 배열이어야 한다")], ev)
    for i, it in enumerate(items):
        fld = f"open_items[{i}]"
        if not isinstance(it, dict):
            f.append(fail(fld, "항목은 객체여야 한다"))
            continue
        oid = it.get("id")
        if not oid:
            f.append(fail(f"{fld}.id", "OI-NNNN id 가 필요하다 (python tools/gate.py oi new …)"))
        elif oid not in store:
            f.append(fail(f"{fld}.id", f"{oid} 가 open-items.yaml 에 없다", "gate.py oi new 로 먼저 채번한다"))
        if it.get("kind") not in OI_KINDS:
            f.append(fail(f"{fld}.kind", f"kind 는 {'|'.join(OI_KINDS)} 중 하나여야 한다"))
        sev = it.get("severity")
        if sev not in SEVERITIES:
            f.append(fail(f"{fld}.severity", f"severity 는 {'|'.join(SEVERITIES)} 중 하나여야 한다"))
        if not str(it.get("evidence", "")).strip():
            f.append(fail(f"{fld}.evidence", "근거(파일:라인·명령·레포트 절)가 없다"))
        target = it.get("target_stage")
        if target is None or target == "":
            f.append(fail(f"{fld}.target_stage", "어느 단계가 닫을 항목인지 적는다 (사람 결정 대기는 0)"))
        status = (store.get(oid) or it).get("status", "open")
        rid = (store.get(oid) or it).get("rr_id") or it.get("rr_id")
        # RR(리팩토링 요구서)은 "이미 있는 코드의 결함" 을 고치라는 요구다. 그래서 RR 전환을 요구할 수 있는 것은
        # 코드가 존재하는 단계(2~7)에서 나온 unverified·risk 뿐이다.
        # decision·evidence_gap·deferred 는 다음 단계가 자기 일로 받아 닫는 정상 경로이므로 예약(target_stage)만 있으면 된다.
        stage_num = meta.get("stage") if isinstance(meta.get("stage"), int) else None
        code_exists = stage_num is not None and stage_num >= 2
        rr_applicable = it.get("kind") in ("unverified", "risk") and code_exists
        if sev in BLOCKING_SEV and meta.get("result") in ("done", "done_with_gaps"):
            if not rr_applicable and status == "open":
                where = "사람 결정 대기" if str(target) == "0" else f"stage{target} 가 닫을 항목으로 예약"
                f.append(warn(f"{fld}", f"{sev} 항목이 열린 채 넘어간다 ({where})",
                              "사용자 보고에 포함하고, 그 단계 착수 시 oi list --target 으로 받아 처리한다"))
            elif status == "open" and not rid:
                f.append(fail(f"{fld}", f"{sev} 항목이 RR 연결·사람 승인 없이 열린 채로 완료 처리됐다",
                              "RR 로 변환(gate.py oi set <id> converted --rr RR-xxxx)하거나 accepted 승인을 받는다"))
            if rid and not rr_exists(rid):
                f.append(fail(f"{fld}.rr_id", f"{rid} 파일이 없다"))
            if status == "accepted":
                rec = store.get(oid, {})
                if not rec.get("approved_by"):
                    f.append(fail(f"{fld}", "accepted 는 approved_by(사람) 기록이 필요하다"))
                exp = str(rec.get("expiry") or "")
                try:
                    ok = datetime.date.fromisoformat(exp) >= datetime.datetime.now(KST).date()
                except ValueError:
                    ok = False
                if not ok:
                    f.append(fail(f"{fld}", f"accepted 의 expiry({exp or '없음'}) 가 없거나 지났다"))
    # 이번 단계·slice 가 닫기로 한 항목이 레포트에서 언급되지 않은 경우.
    # 같은 단계라도 레포트는 slice 마다 나뉘므로, 이름이 정확히 일치하는 항목만 누락으로 본다.
    # slice 가 특정되지 않은 항목(all·공란)은 어느 레포트가 닫을지 알 수 없어 건수만 알린다.
    stage, sl = meta.get("stage"), meta.get("slice")
    listed = {it.get("id") for it in items if isinstance(it, dict)}
    pending_other = 0
    for oid, rec in store.items():
        if rec.get("status") != "open" or str(rec.get("target_stage")) != str(stage) or oid in listed:
            continue
        if sl and rec.get("slice") == sl:
            f.append(warn("open_items", f"{oid} 는 이 단계·이 slice 가 닫기로 한 항목인데 레포트에 없다",
                          "처리했으면 resolved 로, 남았으면 메타에 싣는다"))
        else:
            pending_other += 1
    if pending_other:
        f.append(warn("open_items",
                      f"이 단계가 닫기로 한 항목 {pending_other}건이 아직 열려 있다(다른 slice 몫이거나 미배정)",
                      f"python tools/gate.py oi list --status open --target {stage} 로 확인한다"))
    if not isinstance(meta.get("rr_ids"), list):
        f.append(warn("rr_ids", "rr_ids 배열이 없다"))
    else:
        for rid in meta["rr_ids"]:
            if not rr_exists(rid):
                f.append(fail("rr_ids", f"{rid} 파일이 없다"))
    return result_of("open-items", f, ev)


def hook_judgments(ctx):
    """판단으로 정한 것이 판단 기록(JD)으로 남고, 검증 단계가 그것을 다시 확인했는지. (pipeline-core §21)"""
    meta = ctx["meta"]
    ev = [ctx["report"], judgment.JD_FILE]
    if not meta:
        return result_of("judgments", [], ev, skipped=True)
    f = [finding(sev, fld, msg, act) for sev, fld, msg, act in judgment.meta_findings(meta)]
    return result_of("judgments", f, ev)


def hook_state_consistency(ctx):
    """state.yaml 의 상태와 레포트 result 가 모순되지 않는지."""
    meta = ctx["meta"]
    ev = [ctx["report"], STATE]
    if not meta or not os.path.exists(STATE):
        return result_of("state-consistency", [], ev, skipped=True)
    try:
        st = load_yaml(STATE)
    except Exception as ex:
        return result_of("state-consistency", [warn("state", f"state.yaml 읽기 실패: {ex}")], ev)
    f = []
    stage, sl = meta.get("stage"), meta.get("slice")
    expect = {"done": "done", "done_with_gaps": "done", "blocked": "blocked", "failed": "blocked"}.get(meta.get("result"))
    key_by_stage = {0: "stage0_ingest", 1: "stage1_slicing", 3: "stage3_common", 5: "stage5_integration",
                    6: "stage6_security", 7: "stage7_qa", 8: "stage8_deliverables"}
    if sl == "common-port":                 # 공통 선행 변환도 단계 단위 항목이다
        key_by_stage.update({2: "stage2_common_port"})
        sl = None
    if sl in ("scaffold", "scaffold-fe"):   # 골격 레포트는 slices 가 아니라 stages 를 본다
        key_by_stage.update({2: "stage2_scaffold", 4: "stage4_scaffold"})
        sl = None
    actual = None
    skey = {2: "stage2_backend", 4: "stage4_frontend", 5: "stage5_integration"}.get(stage, "")
    if sl and isinstance(st.get("slices"), dict) and sl in st["slices"]:
        node = st["slices"][sl] or {}
        if meta.get("unit"):   # unit 레포트는 slices.<id>.units.<unit> 을 본다
            node = ((node.get("units") or {}).get(meta["unit"]) or {})
        actual = node.get(skey, None)
    if actual is None and stage in key_by_stage:
        actual = (st.get("stages") or {}).get(key_by_stage[stage])
    if actual is None:
        f.append(warn("state", "state.yaml 에서 해당 항목을 찾지 못했다"))
    elif expect and actual not in (expect, "in_progress"):
        f.append(fail("state", f"레포트 result={meta.get('result')} 인데 state.yaml 은 {actual} 이다",
                      "웨이브 종료 시 state.yaml 을 갱신한다"))
    return result_of("state-consistency", f, ev)


def load_slices():
    path = os.path.join(WS, "slices", "slices.yaml")
    if not os.path.exists(path):
        return None, path
    try:
        return load_yaml(path), path
    except Exception:
        return None, path


def slice_entry(slice_id):
    data, path = load_slices()
    if not data or not slice_id:
        return None, path
    for s in (data.get("slices") or []):
        if isinstance(s, dict) and s.get("id") == slice_id:
            return s, path
    return None, path


def trait_axis_map():
    cfg = (config().get("verification") or {})
    custom = cfg.get("trait_axes")
    if isinstance(custom, dict):
        merged = dict(TRAIT_AXES)
        merged.update({k: list(v) for k, v in custom.items() if isinstance(v, list)})
        return merged
    return TRAIT_AXES


def hook_coverage_axis(ctx):
    """slice 의 특성(traits)이 요구하는 검증 축이 닫혔거나, 닫을 단계가 예약돼 있는지.

    실측 근거: 파이프라인이 스스로 만든 결함 7건은 전부 '앞 단계가 보지 못한 축'에서만 잡혔다.
    """
    meta = ctx["meta"]
    if not meta:
        return result_of("coverage-axis", [], [ctx["report"]], skipped=True)
    slice_id = meta.get("slice")
    entry, spath = slice_entry(slice_id)
    ev = [ctx["report"], spath]
    if not slice_id or slice_id == "all" or entry is None:
        return result_of("coverage-axis", [], ev, skipped=True)
    traits = entry.get("traits")
    if not isinstance(traits, list) or not traits:
        return result_of("coverage-axis",
                         [warn("traits", f"slices.yaml 의 {slice_id} 에 traits 가 없어 축 검사를 건너뛴다",
                               "stage1 에서 traits(file-upload·transaction·counter·rich-text·auth 등)를 채운다")], ev)
    amap = trait_axis_map()
    required = set(BASE_AXES)
    unknown = []
    for t in traits:
        if t in amap:
            required.update(amap[t])
        else:
            unknown.append(t)
    declared = []
    for g in (meta.get("gates") or []):
        if not isinstance(g, dict) or g.get("exit_code") != 0:
            continue
        axes = gate_axes(g)
        if axes:
            declared.extend(axes)
        elif g.get("kind") in ("test", "smoke"):
            declared.append("unit")   # 축 미기재 테스트는 가장 약한 축만 닫은 것으로 본다
    covered = expand_axes(declared)
    deferred = {i.get("axis") for i in (meta.get("open_items") or [])
                if isinstance(i, dict) and i.get("axis")}
    f = []
    for t in unknown:
        f.append(warn("traits", f"알 수 없는 trait: {t}", "config 의 verification.trait_axes 에 매핑을 추가한다"))
    missing = sorted(required - covered - deferred)
    stage = meta.get("stage")
    for axis in missing:
        owner = AXIS_STAGE.get(axis, 5)
        blocking = isinstance(stage, int) and stage >= owner
        msg = f"{slice_id}({','.join(traits)}) 가 요구하는 '{axis}' 축이 닫히지도, 예약되지도 않았다"
        act = (f"그 축으로 실행해 gates[].axis={axis} 로 남기거나, "
               f"python tools/gate.py oi new --stage {stage} --slice {slice_id} --kind unverified "
               f"--axis {axis} --target {owner} … 로 넘긴다")
        f.append(finding("FAIL" if blocking else "WARN", f"axis.{axis}", msg, act))
    return result_of("coverage-axis", f, ev)


TEST_GLOBS = ("**/src/test/**/*.java", "**/*.test.ts", "**/*.test.tsx", "**/*.spec.ts", "**/*.spec.tsx")


def collect_test_text(td, cache={}):
    if td in cache:
        return cache[td]
    chunks = []
    for pat in TEST_GLOBS:
        for p in glob.glob(os.path.join(td, pat), recursive=True):
            # 빌드 산출물은 target_dir 안쪽 경로로만 판정한다 (target_dir 자체가 .../target 이면 전부 빠지던 문제)
            r = os.sep + os.path.relpath(p, td)
            if "node_modules" in r or os.sep + "target" + os.sep in r or os.sep + "dist" + os.sep in r:
                continue
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    chunks.append(fh.read())
            except OSError:
                continue
    cache[td] = "\n".join(chunks)
    return cache[td]


def trace_slice(td, entry):
    """slice 의 요구사항 ID 가 테스트까지 살아 있는지. (found, missing, contract_ok)"""
    reqs = [str(r) for r in (entry.get("requirements") or [])]
    text = collect_test_text(td) if td else ""
    found, missing = [], []
    for r in reqs:
        (found if r and r in text else missing).append(r)
    contract = os.path.join(td, "docs", "api", f"{entry.get('id')}.yaml") if td else ""
    contract_ok = (not entry.get("apis")) or (contract and os.path.exists(contract))
    return found, missing, contract_ok, contract


def hook_traceability(ctx):
    """요구사항 ID 가 slices → 테스트까지 이어지는지. 8단계에서 '끊긴 추적' 으로 드러나던 것을 앞당긴다."""
    meta = ctx["meta"]
    if not meta:
        return result_of("traceability", [], [ctx["report"]], skipped=True)
    slice_id = meta.get("slice")
    entry, spath = slice_entry(slice_id)
    ev = [ctx["report"], spath]
    td = ctx["target_dir"]
    if entry is None or not td or not os.path.isdir(td):
        return result_of("traceability", [], ev, skipped=True)
    found, missing, contract_ok, contract = trace_slice(td, entry)
    stage = meta.get("stage")
    blocking = isinstance(stage, int) and stage == 8
    f = []
    if not found and not missing:
        return result_of("traceability", [warn("requirements", f"{slice_id} 에 requirements 가 없다")], ev)
    for r in missing:
        f.append(finding("FAIL" if blocking else "WARN", f"trace.{r}",
                         f"{r} 을 인용한 테스트를 찾지 못했다 (8단계 추적표에서 끊긴 연결이 된다)",
                         "요구사항을 다루는 테스트의 @DisplayName·describe 에 요구사항 ID 를 적는다"))
    if not contract_ok:
        f.append(finding("FAIL" if blocking else "WARN", "trace.contract",
                         f"API 가 있는 slice 인데 계약 파일이 없다: {contract}", "2단계에서 계약을 산출한다"))
    return result_of("traceability", f, ev)


def hook_cost_record(ctx):
    """단계 비용(소요·tool call) 기록. 회차 간 비교 근거이며 누락은 경고만 한다."""
    meta = ctx["meta"]
    if not meta:
        return result_of("cost-record", [], [ctx["report"]], skipped=True)
    cost = meta.get("cost")
    f = []
    if cost is None:
        f.append(warn("cost", "cost(소요 시간·tool call·토큰) 기록이 없다",
                      "cost: {duration_min, tool_calls, tokens_k} 를 남기면 회차 간 비용 비교가 된다"))
    elif not isinstance(cost, dict):
        f.append(fail("cost", "cost 는 객체여야 한다"))
    else:
        for k in ("duration_min", "tool_calls"):
            v = cost.get(k)
            if v is not None and not isinstance(v, (int, float)):
                f.append(fail(f"cost.{k}", f"{k} 는 숫자여야 한다"))
        if cost.get("duration_min") is None:
            f.append(warn("cost.duration_min", "소요 시간이 없다"))
    # 판별력 실측(mutation·수정 전 재현) 기록 — 산문에만 남으면 기계 추적이 안 된다(실측: 범위를 한 클래스로 좁혀
    # 보고한 것을 reviewer 가 잡았다). gates[] 에 실으면 gate-proof 가 "실패를 통과로 기재" 로 읽으므로 별도 칸이다.
    disc = meta.get("discrimination")
    if disc is not None:
        if not isinstance(disc, list):
            f.append(fail("discrimination", "discrimination 은 배열이어야 한다"))
        else:
            for i, d in enumerate(disc):
                fld = f"discrimination[{i}]"
                if not isinstance(d, dict):
                    f.append(fail(fld, "항목은 객체여야 한다"))
                    continue
                if not str(d.get("target", "")).strip():
                    f.append(fail(f"{fld}.target", "무엇의 판별력을 증명했는지(테스트·지적 id) 적는다"))
                method = d.get("method")
                if method not in ("mutation", "pre_fix_repro", "absent_pre_fix", "other"):
                    f.append(fail(f"{fld}.method", "method 는 mutation | pre_fix_repro | absent_pre_fix | other"))
                if not str(d.get("scope", "")).strip():
                    f.append(fail(f"{fld}.scope", "실행 범위(모듈·클래스)를 적는다 — 범위를 좁혀 일반화한 오보가 실측됐다",
                                  "모듈 전체(-pl <모듈> test)로 1회 실행하는 것이 기준이다"))
                # absent_pre_fix = 수정 전에는 판별 수단(메서드·오류코드)이 없어 재현 단언을 쓸 수조차 없던 경우.
                # 이때만 failures 0 을 허용하되, 해악의 실재 증거와 mutation 을 둘 다 요구한다 —
                # "재현 불가" 가 판별력 면제로 쓰이면 규격이 자리끼움 숫자를 부른다(실측: failures:1 로 적고 통과).
                if method == "absent_pre_fix":
                    if d.get("failures") not in (0, None):
                        f.append(warn(f"{fld}.failures", "absent_pre_fix 는 failures 0 이 정상이다"))
                    if not str(d.get("harm_evidence", "")).strip():
                        f.append(fail(f"{fld}.harm_evidence",
                                      "결함의 해악이 실재함을 증명하는 통과 단언(예: FK 위반 재현)을 적는다"))
                    if not str(d.get("mutation", "")).strip():
                        f.append(fail(f"{fld}.mutation",
                                      "수정 후 구현에 결함을 주입해 새 테스트가 잡는지 확인한 기록을 적는다",
                                      "absent_pre_fix 는 mutation 을 면제하지 않는다 — 재현이 불가능하면 mutation 이 의무다"))
                elif not isinstance(d.get("failures"), int) or d["failures"] <= 0:
                    f.append(fail(f"{fld}.failures", "재현 실패 건수(1 이상)를 적는다 — 0 이면 판별력을 증명하지 못했다"))
                ev = str(d.get("evidence", "")).strip()
                if not ev:
                    f.append(warn(f"{fld}.evidence", "실패 실행의 surefire XML 사본 경로를 남긴다",
                                  "최종 실행이 XML 을 덮어써 독립 검증이 불가능했다(실측)"))
                else:
                    # evidence 의 XML 을 실제로 읽어 declared failures·tests 와 대조한다.
                    # scope 를 "모듈 전체" 로 적고 단일 클래스만 돌린 오보가 두 회차 연속 실측됐다(§14-6).
                    tests, fails, found = 0, 0, 0
                    for token in re.split(r"[,\s]+", ev):
                        token = token.strip().rstrip(",")
                        if not token or not token.endswith(".xml") and "*" not in token:
                            continue
                        base = token if os.path.isabs(token) else os.path.join(ROOT, token)
                        for xml in sorted(glob.glob(base)):
                            try:
                                text = open(xml, encoding="utf-8", errors="replace").read(4000)
                            except OSError:
                                continue
                            found += 1
                            mt = re.search(r'tests="(\d+)"', text)
                            mf = re.search(r'failures="(\d+)"', text)
                            me = re.search(r'errors="(\d+)"', text)
                            tests += int(mt.group(1)) if mt else 0
                            fails += (int(mf.group(1)) if mf else 0) + (int(me.group(1)) if me else 0)
                    if not found:
                        f.append(warn(f"{fld}.evidence", f"XML 사본을 찾지 못했다: {ev[:60]}",
                                      "경로를 repo 기준 상대경로로 적는다"))
                    else:
                        declared = d.get("failures")
                        if isinstance(declared, int) and declared > 0 and fails != declared:
                            f.append(fail(f"{fld}.failures",
                                          f"선언한 실패 {declared}건 ≠ XML 실측 {fails}건 (사본 {found}개)",
                                          "실패 실행의 XML 사본과 선언을 일치시킨다"))
                        scope = str(d.get("scope", ""))
                        if "전체" in scope and str(tests) not in scope:
                            f.append(warn(f"{fld}.scope",
                                          f"scope 에 '전체' 라고 적혔는데 XML 사본의 테스트 수는 {tests}건이다",
                                          "모듈 전체로 돌렸다면 그 건수를 scope 에 적는다 — 단일 클래스 결과를 전체로 일반화한 오보가 2회 실측됐다"))
                if not str(d.get("restored", "")).strip():
                    f.append(warn(f"{fld}.restored", "되돌림 확인 방법(grep·재통과 건수)을 적는다"))
    risks = meta.get("risk_surface")
    if risks is not None:
        if not isinstance(risks, list):
            f.append(fail("risk_surface", "risk_surface 는 배열이어야 한다"))
        else:
            for i, r in enumerate(risks):
                if not isinstance(r, dict):
                    f.append(fail(f"risk_surface[{i}]", "항목은 객체여야 한다"))
                    continue
                if not str(r.get("what", "")).strip():
                    f.append(fail(f"risk_surface[{i}].what", "이 변경이 무엇을 깨뜨릴 수 있는지 적는다"))
                if r.get("axis") and r["axis"] not in AXES:
                    f.append(fail(f"risk_surface[{i}].axis", f"알 수 없는 axis: {r['axis']}"))
                if not str(r.get("covered_by", "")).strip():
                    f.append(fail(f"risk_surface[{i}].covered_by",
                                  "무엇으로 덮었는지(테스트명) 또는 '미검증' 을 적는다",
                                  "미검증이면 확인 필요 항목으로 남긴다"))
    return result_of("cost-record", f, [ctx["report"]])


def scan_secrets_text(text, label):
    f = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for name, pat in SECRET_PATTERNS.items():
            m = pat.search(line)
            if not m:
                continue
            value = m.group(1) if m.groups() else m.group(0)
            if PLACEHOLDER_RE.match(value.strip()):
                continue
            if name == "password" and re.search(r"(?i)(?:password|token|secret|api[_-]?key)\s*[:=]\s*[\"'`]?\$?\{", line):
                continue
            snippet = line.strip()[:110]
            f.append(finding("FAIL", f"{label}:{line_no}", f"{name} 로 보이는 값이 있다: {snippet}",
                             "값을 마스킹(***)하거나 참조 경로만 남긴다"))
    return f


def hook_secret_scan(ctx):
    ev = [ctx["report"]]
    if not os.path.exists(ctx["report"]):
        return result_of("secret-scan", [], ev, skipped=True)
    with open(ctx["report"], encoding="utf-8") as fp:
        text = fp.read()
    return result_of("secret-scan", scan_secrets_text(text, os.path.basename(ctx["report"])), ev)


def parse_kst(s):
    """'YYYY-MM-DD HH:MM' (KST) → epoch 초. 형식이 다르면 None."""
    try:
        d = datetime.datetime.strptime(str(s).strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    return d.replace(tzinfo=KST).timestamp()


STALE_SLACK_SEC = 120   # started_at 은 분 단위로 적으므로 2분 여유를 둔다


def hook_test_evidence(ctx):
    """테스트 개수·실패 수를 에이전트 기재값이 아니라 실제 결과 파일(JUnit XML)로 대조한다.

    gates[].results 에 결과 파일 glob(target_dir 기준)을 적는다. 도구가 <testcase> 를 세어
    test_count·failures 와 비교하고, 결과 파일이 이번 단계 시작(started_at) 이전 것이면 재사용으로 본다.
    results 가 없을 때는 config pipeline.gate.test_evidence: strict 면 차단, 아니면 경고.
    """
    meta = ctx["meta"]
    ev = [ctx["report"]]
    if not meta or not isinstance(meta.get("gates"), list):
        return result_of("test-evidence", [], ev, skipped=True)
    import _junit
    mode = ((config().get("pipeline") or {}).get("gate") or {}).get("test_evidence", "warn")
    strict = mode == "strict"
    base = ctx["target_dir"] or ROOT
    started = parse_kst(meta.get("started_at"))
    f = []
    checked = 0
    for i, g in enumerate(meta["gates"]):
        if not isinstance(g, dict) or g.get("kind") not in ("test", "smoke"):
            continue
        fld = f"gates[{i}]"
        results = g.get("results")
        if not results:
            msg = "결과 파일 경로(results)가 없어 테스트 수를 자기 기재값으로만 믿었다"
            act = "results 에 JUnit XML glob 을 적는다 (예: backend/build/test-results/test/*.xml, frontend/reports/junit.xml)"
            f.append(fail(f"{fld}.results", msg, act) if strict else warn(f"{fld}.results", msg, act))
            continue
        files = _junit.resolve(results, base)
        if not files:
            f.append(fail(f"{fld}.results", f"결과 파일이 없다: {results}", "실제 실행 후 생성된 경로를 적는다"))
            continue
        s = _junit.summarize(files)
        checked += 1
        ev.append(f"{fld}: files={s['files']} tests={s['tests']} failures={s['failures']} "
                  f"errors={s['errors']} skipped={s['skipped']}")
        if s["parse_errors"]:
            f.append(fail(f"{fld}.results", f"결과 파일 파싱 실패 {len(s['parse_errors'])}개: "
                                            f"{os.path.basename(s['parse_errors'][0])}"))
        tc = g.get("test_count")
        if isinstance(tc, int) and tc != s["tests"]:
            f.append(fail(f"{fld}.test_count", f"기재 {tc}건 ≠ 결과 파일 실측 {s['tests']}건 ({s['files']}개 파일)",
                          "결과 파일에서 센 값을 적는다 (필터·캐시로 일부만 실행됐을 수 있다)"))
        declared_fail = g.get("failures") if isinstance(g.get("failures"), int) else 0
        actual_fail = s["failures"] + s["errors"]
        if declared_fail != actual_fail:
            f.append(fail(f"{fld}.failures", f"기재 실패 {declared_fail}건 ≠ 결과 파일 실측 {actual_fail}건"))
        if actual_fail and meta.get("result") in ("done", "done_with_gaps"):
            f.append(fail(f"{fld}", f"결과 파일에 실패 {actual_fail}건이 있는데 result={meta.get('result')} 다"))
        if isinstance(g.get("skipped"), int) and g["skipped"] != s["skipped"]:
            f.append(warn(f"{fld}.skipped", f"기재 skip {g['skipped']}건 ≠ 결과 파일 {s['skipped']}건"))
        if started and s["oldest_mtime"] is not None and s["oldest_mtime"] < started - STALE_SLACK_SEC:
            f.append(fail(f"{fld}.results", "이번 단계 시작(started_at) 이전에 만들어진 결과 파일이 섞여 있다",
                          "이전 실행 결과를 재사용하지 않는다. clean 후 다시 실행한다 (Gradle: cleanTest test --no-build-cache)"))
    if not checked and not f:
        return result_of("test-evidence", [], ev, skipped=True)
    return result_of("test-evidence", f, ev)


def hook_no_emoji(ctx):
    """레포트에 이모지가 없는지 (CLAUDE.md 이모지 금지 — 예외 없음)."""
    ev = [ctx["report"]]
    if not os.path.exists(ctx["report"]):
        return result_of("no-emoji", [], ev, skipped=True)
    from _emoji import find_emoji
    with open(ctx["report"], encoding="utf-8", errors="replace") as fp:
        hits = find_emoji(fp.read())
    f = [fail(f"{os.path.basename(ctx['report'])}:{no}", f"이모지 {cp} ({col}열)", "텍스트로 바꾼다 (예: 완료·주의·[의미차이:태그명])")
         for no, col, _ch, cp in hits[:20]]
    if len(hits) > 20:
        f.append(fail("no-emoji", f"외 {len(hits) - 20}건"))
    return result_of("no-emoji", f, ev)


def hook_common_integrity(ctx):
    """공통 계약 준수 — 업무 slice 의 공통 복제·공통 영역 침범, common-port 의 계약 이행 (tools/common_contract.py).

    배경(실측): 업무 단위 변환 중 공통 클래스가 업무별로 쪼개지거나 private 으로 복제됐고, 공통만 따로 변환하면
    업무 코드와 어긋났다. 공통은 계약으로 먼저 확정하고 common-porter 만 수정하며, 업무 slice 는 소비만 한다.
    """
    meta = ctx["meta"]
    ev = [ctx["report"]]
    if not meta or meta.get("stage") not in (2, 3, 4):
        return result_of("common-integrity", [], ev, skipped=True)
    import common_contract as ccm
    cfg = config()
    data = ccm.load_contract()
    sl = meta.get("slice")
    done = meta.get("result") in ("done", "done_with_gaps")
    mode = (cfg.get("project") or {}).get("mode")
    strict = ((cfg.get("pipeline") or {}).get("gate") or {}).get("common_contract") == "strict"
    if not data:
        if mode == "migration" and meta.get("stage") == 2 and sl not in ("scaffold",):
            msg = "공통 계약(contracts/common-contract.yaml)이 없다 — 업무 변환 전에 공통을 확정하지 않으면 공통 클래스가 업무별로 쪼개진다"
            act = "python tools/common_usage.py → python tools/common_contract.py init → 사람 검토·승인 → /stage2 common-port"
            return result_of("common-integrity", [fail("common-contract", msg, act) if strict else warn("common-contract", msg, act)], ev)
        return result_of("common-integrity", [], ev, skipped=True)
    ev.append(ccm.contract_path())
    f = []
    if not data.get("approved") and done and sl not in ("scaffold",):
        f.append(fail("common-contract", "공통 계약이 승인되지 않은 채 단계가 완료됐다",
                      "사람이 직접 python tools/common_contract.py approve --by <이름> 로 승인한다"))
    td = ctx["target_dir"]
    if not td or not os.path.isdir(td):
        return result_of("common-integrity", f, ev)
    asis = (cfg.get("asis") or {}).get("source_dir")
    if asis and not os.path.isabs(asis):
        asis = os.path.normpath(os.path.join(ROOT, asis))
    repo = meta.get("repo") if isinstance(meta.get("repo"), dict) else {}
    files = [p for p in (repo.get("changed_files") or []) if isinstance(p, str)]
    if sl == "common-port":
        found = ccm.fulfillment_findings(td, data) if done else []
    elif meta.get("stage") == 3:
        found = []   # 공통화 단계는 공통 영역을 고칠 수 있는 유일한 자리다
    else:
        entry, _sp = slice_entry(sl)
        mpaths = (cfg.get("project") or {}).get("module_paths")
        found = ccm.integrity_findings(sl, files, td, data, asis, (entry or {}).get("module"),
                                       mpaths if isinstance(mpaths, dict) else None)
    for sev, where, msg, act in found[:PRODUCTIZATION_SHOW]:
        f.append(finding(sev, where, msg, act))
    if len(found) > PRODUCTIZATION_SHOW:
        f.append(warn("common-integrity", f"외 {len(found) - PRODUCTIZATION_SHOW}건",
                      "python tools/common_contract.py check 로 전체를 본다"))
    return result_of("common-integrity", f, ev)


def hook_spec_lock(ctx):
    """잠긴 기대 동작 테스트(spec) — 해시가 그대로인지, spec 스위트를 전부 실행해 통과했는지 (tools/spec_lock.py).

    기대 동작 테스트는 behavior-spec-writer 가 구현 전에 AS-IS 동작 계약만 보고 쓰고 잠근다. developer 가 테스트를 고쳐
    통과시키는 자기 확인 편향을 막는다. config verification.locked_spec: required 면 잠금 없는 완료를 차단한다.
    """
    meta = ctx["meta"]
    ev = [ctx["report"]]
    if not meta or meta.get("stage") not in (2, 4):
        return result_of("spec-lock", [], ev, skipped=True)
    sl = meta.get("slice")
    if sl in ("scaffold", "scaffold-fe", None, "", "all"):
        return result_of("spec-lock", [], ev, skipped=True)
    import spec_lock
    cfg = config()
    policy = (cfg.get("verification") or {}).get("locked_spec", "optional")
    done = meta.get("result") in ("done", "done_with_gaps")
    m = spec_lock.load_manifest(sl)
    if not m:
        if policy == "required" and done:
            return result_of("spec-lock", [fail("spec", f"{sl} 의 기대 동작 테스트가 잠기지 않은 채 완료됐다",
                                                "behavior-spec-writer 로 spec 을 쓰고 python tools/spec_lock.py lock --slice <id> 후 구현한다")], ev)
        if policy != "off" and (cfg.get("project") or {}).get("mode") == "migration":
            return result_of("spec-lock", [warn("spec", f"{sl} 에 잠긴 기대 동작 테스트가 없다 — 자기 확인 편향을 막는 장치가 없다",
                                                "verification.locked_spec: required 를 권장")], ev)
        return result_of("spec-lock", [], ev, skipped=True)
    td = ctx["target_dir"]
    ev.append(spec_lock.manifest_path(sl))
    f = []
    if td and os.path.isdir(td):
        for kind, r, msg in spec_lock.verify(sl, td):
            f.append(fail(f"spec:{r}", msg, "잠긴 테스트를 원래대로 되돌리고 코드를 고친다. 테스트가 틀렸으면 사람이 unlock"))
    spec_gates = [g for g in meta.get("gates") or [] if isinstance(g, dict) and g.get("suite") == "spec"]
    if not spec_gates:
        f.append(fail("gates", "잠긴 기대 동작 테스트(spec 스위트) 실행 기록이 없다",
                      "gates[] 에 suite: spec 인 test 게이트(명령·결과 파일 포함)를 적는다"))
    else:
        ran = sum(g.get("test_count") or 0 for g in spec_gates if isinstance(g.get("test_count"), int))
        if ran < int(m.get("test_count") or 0):
            f.append(fail("gates", f"잠긴 기대 동작 테스트 {m.get('test_count')}건 중 {ran}건만 실행됐다",
                          "spec 스위트 전체를 실행한다 (필터로 일부만 돌리지 않는다)"))
        failed = sum(g.get("failures") or 0 for g in spec_gates if isinstance(g.get("failures"), int))
        if failed and done:
            f.append(fail("gates", f"기대 동작 테스트 실패 {failed}건인데 완료로 기록됐다"))
    return result_of("spec-lock", f, ev)


def hook_visual(ctx):
    """브라우저 화면 검증 — 기준 이미지가 모두 승인됐고 픽셀 비교 실패(diff)가 없는지 (tools/visual.py).

    config verification.visual.enabled: true 일 때만. 4단계(slice)·5단계에서 본다.
    """
    meta = ctx["meta"]
    ev = [ctx["report"]]
    vc = (config().get("verification") or {}).get("visual") or {}
    if not meta or not vc.get("enabled") or meta.get("stage") not in (4, 5):
        return result_of("visual", [], ev, skipped=True)
    td = ctx["target_dir"]
    if not td or not os.path.isdir(td):
        return result_of("visual", [], ev, skipped=True)
    import visual
    sl = meta.get("slice")
    r = visual.pending(td, None if sl in (None, "", "all", "scaffold-fe") else sl)
    ev.append(f"baselines={r['baselines']} approved={r['approved']} pending={r['images']} tokens~{r['estimated_tokens']}")
    f = []
    if r["baselines"] == 0 and meta.get("stage") == 4 and sl not in ("scaffold-fe",):
        f.append(warn("visual", "이 slice 의 기준 이미지(toHaveScreenshot)가 없다", "화면·상태마다 Playwright 스크린샷 단언을 둔다"))
    for i in r["items"][:PRODUCTIZATION_SHOW]:
        msg = {"new-baseline": "승인되지 않은 새 기준 이미지", "changed-baseline": "승인 후 바뀐 기준 이미지",
               "failed-diff": "픽셀 비교 실패(diff)"}[i["reason"]]
        f.append(fail(i["file"], msg, "ui-verifier 가 검토해 승인(python tools/visual.py approve)하거나 결함이면 RR"))
    return result_of("visual", f, ev)


PRODUCTIZATION_SHOW = 30   # 게이트 출력에 싣는 상세 건수 상한 (전체는 tools/quality.py 로 본다)


def hook_productization(ctx):
    """생성 소스의 상품화 품질(Javadoc·로깅·traceId·Mapper 주석·콘솔 출력) — tools/quality.py 규칙으로 점검.

    이번 단계가 바꾼 파일(repo.changed_files)만 본다. 목록이 없으면 target_dir 전체를 본다.
    critical 은 항상 차단, major 는 config pipeline.gate.productization: strict 일 때 차단(기본은 경고).
    """
    meta = ctx["meta"]
    ev = [ctx["report"]]
    td = ctx["target_dir"]
    if not meta or not td or not os.path.isdir(td):
        return result_of("productization", [], ev, skipped=True)
    repo = meta.get("repo") if isinstance(meta.get("repo"), dict) else {}
    if repo.get("head") == "NOT_CHANGED":
        return result_of("productization", [], ev, skipped=True)
    files = [p for p in (repo.get("changed_files") or []) if isinstance(p, str)]
    import quality   # tools/ 가 sys.path[0] 이므로 같은 폴더 모듈로 불러온다
    res = quality.scan(td, files or None)
    mode = ((config().get("pipeline") or {}).get("gate") or {}).get("productization", "warn")
    strict = mode == "strict"
    f = []
    for it in res["findings"][:PRODUCTIZATION_SHOW]:
        block = it["severity"] == "critical" or (strict and it["severity"] == "major")
        f.append(finding("FAIL" if block else "WARN", f"{it['file']}:{it['line']}",
                         f"{it['rule']} {it['detail']}", quality.RULES[it["rule"]][2]))
    rest = len(res["findings"]) - PRODUCTIZATION_SHOW
    if rest > 0:
        f.append(warn("productization", f"외 {rest}건 생략",
                      f"python tools/quality.py {td} --format json 으로 전체를 본다"))
    cov = {k: v for k, v in res["coverage"].items() if v is not None}
    ev.append(f"quality mode={res['mode']} strict={strict} counts={res['counts']} coverage={cov}")
    return result_of("productization", f, ev)


def latest_unit_meta(stage, slice_id, unit):
    rp = find_report(stage, slice_id, unit)
    if not rp:
        return None, None
    meta, _err = extract_meta(rp)
    return meta, rp


def unit_state(st, slice_id, unit, stage):
    key = {2: "stage2_backend", 4: "stage4_frontend"}.get(stage)
    node = (((st.get("slices") or {}).get(slice_id) or {}).get("units") or {}).get(unit) or {}
    return node.get(key) if key else None


def hook_unit_scope(ctx):
    """큰 slice 를 업무 프로세스 기준 unit 으로 나눈 경우의 범위·완결성 (tools/slice_units.py).

    unit 레포트(meta.unit): 선행 unit 이 끝났는지, 배정된 AS-IS(프로그램·메서드·statement)를 asis_covered 에 빠짐없이 적었는지.
    행렬은 methods 키가 없는 옛 형식도 읽는다(slice_units.load_assignment).
    slice 레포트(2·4단계): 모든 unit 완료, unit 레포트들의 asis_covered 합이 배정 전체를 덮는지, (2단계) 흐름 테스트 실행.
    5단계: 흐름 id 를 인용한 테스트가 있는지(경고).
    """
    meta = ctx["meta"]
    ev = [ctx["report"]]
    if not meta or meta.get("stage") not in (2, 4, 5):
        return result_of("unit-scope", [], ev, skipped=True)
    sl = meta.get("slice")
    entry, spath = slice_entry(sl)
    unit = meta.get("unit") or ""
    if entry is None or not entry.get("units"):
        if unit:
            return result_of("unit-scope", [fail("unit", f"{sl} 에 units 가 없는데 unit 레포트({unit})다",
                                                 "slices.yaml 에 units 를 정의하고 승인받는다")], ev)
        return result_of("unit-scope", [], ev, skipped=True)
    import slice_units as su
    ev.append(spath)
    units = {u.get("id"): u for u in su.units_of(entry)}
    assignment, apath = su.load_assignment(entry)
    if apath:
        ev.append(apath)
    stage = meta.get("stage")
    done = meta.get("result") in ("done", "done_with_gaps")
    f = []
    try:
        st = load_yaml(STATE) if os.path.exists(STATE) else {}
    except Exception:
        st = {}
    if unit:
        if unit not in units:
            return result_of("unit-scope", [fail("unit", f"{sl} 에 unit {unit} 이 없다")], ev)
        if stage == 5:
            return result_of("unit-scope", [fail("unit", "5단계는 slice 단위로 돈다 (unit 레포트 없음)")], ev)
        for d in sorted(su.transitive_deps(list(units.values())).get(unit, set())):
            ds = unit_state(st, sl, d, stage)
            if ds != "done":
                f.append(fail(f"depends_on.{d}", f"선행 unit {d} 가 끝나지 않았다 (state: {ds or '없음'})",
                              f"python tools/slice_units.py order --slice {sl} 순서대로 돈다"))
        if stage == 2:
            # 배정 항목: 클래스 통째(File.java)·메서드 단위(File.java#메서드)·statement. 메서드는 .java 유무를 같게 본다
            want = {su.norm_item(x) for x in su.unit_items(assignment, unit)}
            got = {su.norm_item(x) for x in (meta.get("asis_covered") or [])}
            missing = sorted(want - got)
            if missing and done:
                f.append(fail("asis_covered", f"unit {unit} 에 배정된 AS-IS {len(missing)}건을 다뤘다는 기록이 없다: "
                                              + ", ".join(missing[:10]) + (" …" if len(missing) > 10 else ""),
                              "변환했으면 pa-meta asis_covered 에 적고, 못 했으면 result 를 done 으로 두지 않는다"))
            other = {}
            for uid in units:
                if uid != unit:
                    for x in su.unit_items(assignment, uid):
                        other[su.norm_item(x)] = uid
            for x in sorted(got):
                if x in other:
                    f.append(warn(f"asis_covered.{x}", f"{x} 는 unit {other[x]} 소유다 — 범위를 벗어났다",
                                  "다른 unit 의 AS-IS 는 읽기만 한다. 공유가 필요하면 core 로 올리는 재분할을 요청한다"))
        return result_of("unit-scope", f, ev)

    # slice 단위 레포트
    flows = [fl for fl in (entry.get("flows") or []) if isinstance(fl, dict) and fl.get("id")]
    if stage in (2, 4) and done:
        for uid in units:
            us = unit_state(st, sl, uid, stage)
            if us != "done":
                f.append(fail(f"units.{uid}", f"unit {uid} 가 끝나지 않았다 (state: {us or '없음'})",
                              "slice 는 모든 unit 이 게이트를 통과한 뒤에만 완료한다"))
    if stage == 2 and done:
        covered = set()
        for uid in units:
            um, _rp = latest_unit_meta(stage, sl, uid)
            covered |= {su.norm_item(x) for x in ((um or {}).get("asis_covered") or [])}
        want = set()
        for uid in units:
            want |= {su.norm_item(x) for x in su.unit_items(assignment, uid)}
        missing = sorted(want - covered)
        if missing:
            f.append(fail("asis_covered", f"AS-IS 전수 대조: {len(missing)}건이 어느 unit 레포트에도 없다: "
                                          + ", ".join(missing[:10]) + (" …" if len(missing) > 10 else ""),
                          "빠진 항목을 소유 unit 에서 변환하고 그 unit 레포트의 asis_covered 에 적는다"))
        if not apath and (config().get("project") or {}).get("mode") == "migration":
            f.append(warn("matrix", "unit 배정 행렬이 없어 slices.yaml 선언만으로 대조했다",
                          f"python tools/slice_units.py matrix --slice {sl}"))
    if flows and stage in (2, 5):
        td = ctx["target_dir"]
        text = collect_test_text(td) if td and os.path.isdir(td) else ""
        blocking = stage == 2 and done
        if stage == 2:
            fg = [g for g in meta.get("gates") or [] if isinstance(g, dict) and g.get("suite") == "flow"]
            ran = sum(g.get("test_count") or 0 for g in fg if isinstance(g.get("test_count"), int) and g.get("exit_code") == 0)
            if not ran and done:
                f.append(fail("gates", "unit 을 가로지르는 흐름 테스트(suite: flow) 실행 기록이 없다",
                              "flows 의 시나리오를 테스트로 만들어 gates[] 에 suite: flow 로 적는다"))
        if td and os.path.isdir(td):
            for fl in flows:
                if fl["id"] not in text:
                    f.append(finding("FAIL" if blocking else "WARN", f"flow.{fl['id']}",
                                     f"{fl['id']}({fl.get('name', '')}) 를 인용한 테스트가 없다 — unit 사이 이음매가 검증되지 않는다",
                                     "흐름 테스트의 @DisplayName·describe 에 flow id 를 적는다"))
    return result_of("unit-scope", f, ev)


def held(s):
    """slices.yaml 의 hold — 근거 부족으로 착수 보류. true 또는 사유 문자열."""
    return bool(isinstance(s, dict) and s.get("hold"))


def hold_text(s):
    reason = s.get("hold_reason") or (s.get("hold") if isinstance(s.get("hold"), str) else "")
    return f"근거 대기 hold{(' — ' + str(reason)) if reason else ''}"


def hook_slice_scope(ctx):
    """slice 의 착수 보류(hold)와 모듈 경계.

    hold: 근거가 모자라 착수를 보류한 slice 의 2·4단계 완료는 차단한다 (slices 승인·공통 계약 계산에는 포함된다).
    module: slice 에 module 이 있고 config project.module_paths 에 그 모듈 경로가 있으면, 변경 파일이 자기 모듈 경로와
            승인된 공통 경로(공통 계약 tobe·project.common_module 의 경로) 밖일 때 경고한다. 매핑이 없으면 검사하지 않는다.
    """
    meta = ctx["meta"]
    ev = [ctx["report"]]
    if not meta or meta.get("stage") not in (2, 4):
        return result_of("slice-scope", [], ev, skipped=True)
    sl = meta.get("slice")
    if sl in ("scaffold", "common-port", None, "") or str(sl).startswith("common"):
        return result_of("slice-scope", [], ev, skipped=True)
    entry, spath = slice_entry(sl)
    if not entry:
        return result_of("slice-scope", [], ev, skipped=True)
    ev.append(spath)
    f = []
    if held(entry) and meta.get("result") in ("done", "done_with_gaps"):
        f.append(fail("hold", f"{sl} 는 {hold_text(entry)} 인데 완료로 기록됐다",
                      "근거를 확보해 slices.yaml 의 hold 를 풀고(사람 승인) 다시 진행한다"))
    module = entry.get("module")
    proj = config().get("project") or {}
    mpaths = proj.get("module_paths") if isinstance(proj.get("module_paths"), dict) else {}
    if module and mpaths.get(module):
        own = [str(p) for p in (mpaths.get(module) if isinstance(mpaths.get(module), list) else [mpaths.get(module)])]
        allowed = list(own)
        cm = proj.get("common_module")
        if cm and mpaths.get(cm):
            allowed += [str(p) for p in (mpaths[cm] if isinstance(mpaths[cm], list) else [mpaths[cm]])]
        try:
            import common_contract as ccm
            data = ccm.load_contract() or {}
        except Exception:
            data = {}
        tobe = data.get("tobe") or {}
        allowed += [str(tobe.get(k) or "") for k in ("common_module", "shared_mapper_dir")]
        mc = tobe.get("module_common") if isinstance(tobe.get("module_common"), dict) else {}
        allowed += [str(p) for p in (mc.get(module) if isinstance(mc.get(module), list) else [mc.get(module)]) if p]
        allowed += [str(p) for p in (entry.get("existing_code") or []) if isinstance(p, str)]
        repo = meta.get("repo") if isinstance(meta.get("repo"), dict) else {}
        roots = [a.replace("\\", "/").strip("/") for a in allowed if a and a.strip("/")]
        outside = []
        for p in repo.get("changed_files") or []:
            if not isinstance(p, str):
                continue
            fr = p.replace("\\", "/").strip("/")
            if not any(fr == r or fr.startswith(r + "/") for r in roots):
                outside.append(p)
        for p in outside[:PRODUCTIZATION_SHOW]:
            f.append(warn(f"module.{module}", f"변경 파일 {p} 가 {module} 모듈 경로({', '.join(own)})·승인된 공통 경로 밖이다",
                          "다른 모듈 코드는 복사 규약(공통 계약 copy)을 따르거나, 공통이면 공통 요청(CR)으로 돌린다"))
        if len(outside) > PRODUCTIZATION_SHOW:
            f.append(warn(f"module.{module}", f"외 {len(outside) - PRODUCTIZATION_SHOW}건"))
    return result_of("slice-scope", f, ev)


HOOKS = {
    "report-meta": hook_report_meta,
    "gate-proof": hook_gate_proof,
    "repo-consistency": hook_repo_consistency,
    "coverage-axis": hook_coverage_axis,
    "traceability": hook_traceability,
    "open-items": hook_open_items,
    "judgments": hook_judgments,
    "state-consistency": hook_state_consistency,
    "cost-record": hook_cost_record,
    "secret-scan": hook_secret_scan,
    "productization": hook_productization,
    "test-evidence": hook_test_evidence,
    "no-emoji": hook_no_emoji,
    "common-integrity": hook_common_integrity,
    "spec-lock": hook_spec_lock,
    "visual": hook_visual,
    "unit-scope": hook_unit_scope,
    "slice-scope": hook_slice_scope,
}
PROFILES = {
    # 2·3·4단계: 빌드·테스트 증거와 git 실측까지
    "dev": ["report-meta", "gate-proof", "test-evidence", "repo-consistency", "coverage-axis", "traceability",
            "open-items", "judgments", "state-consistency", "cost-record", "secret-scan", "no-emoji", "productization",
            "common-integrity", "spec-lock", "visual", "unit-scope", "slice-scope"],
    # 5·6·7단계: 검증 단계 — 결함은 RR, 미확인은 open item 으로 나갔는지
    "verify": ["report-meta", "gate-proof", "test-evidence", "coverage-axis", "open-items", "judgments",
               "state-consistency",
               "cost-record", "secret-scan", "no-emoji", "visual", "unit-scope"],
    # 0·1단계
    "doc": ["report-meta", "open-items", "judgments", "state-consistency", "cost-record", "secret-scan", "no-emoji"],
    # 8단계: 추적 체인이 끊기면 산출물이 비어 나온다 → 여기서는 차단
    "deliver": ["report-meta", "traceability", "open-items", "judgments", "state-consistency", "cost-record", "secret-scan",
                "no-emoji"],
    "all": list(HOOKS),
}
STAGE_PROFILE = {0: "doc", 1: "doc", 2: "dev", 3: "dev", 4: "dev", 5: "verify", 6: "verify", 7: "verify", 8: "deliver"}


# ---------------------------------------------------------------- 명령

def cmd_check(args):
    report = args.report
    stage = args.stage
    if report and not os.path.isabs(report):
        report = os.path.normpath(os.path.join(ROOT, report))
    if not report:
        if stage is None:
            sys.exit("[gate] --report 또는 --stage 가 필요하다")
        report = find_report(stage, args.slice, args.unit)
        if not report:
            sys.exit(f"[gate] stage{stage} {args.slice or ''} {('unit ' + args.unit) if args.unit else ''} 레포트를 찾지 못했다: {REPORTS}")
    meta, meta_error = extract_meta(report)
    if stage is None and meta and isinstance(meta.get("stage"), int):
        stage = meta["stage"]
    profile = args.profile or STAGE_PROFILE.get(stage, "all")
    ctx = {"report": report, "meta": meta, "meta_error": meta_error, "stage": args.stage,
           "slice": args.slice, "unit": args.unit, "target_dir": target_dir()}
    skip = set(args.skip or [])
    unknown = skip - set(HOOKS)
    if unknown:
        sys.exit(f"[gate] 알 수 없는 훅: {', '.join(sorted(unknown))}")
    results = [HOOKS[h](ctx) for h in PROFILES[profile] if h not in skip]
    blocked = any(r["result"] == "FAIL" for r in results)
    if args.format == "json":
        print(json.dumps({"schema": 1, "report": report, "stage": stage, "slice": args.slice, "unit": args.unit,
                          "profile": profile, "blocked": blocked, "results": results},
                         ensure_ascii=False, indent=2))
    else:
        print(f"레포트: {report}")
        print(f"프로파일: {profile} (stage {stage})")
        for r in results:
            print(f"[{r['result']}] {r['hook']}")
            for it in r["findings"]:
                print(f"    - {it['severity']} {it['field']}: {it['message']}")
                if it["action"]:
                    print(f"      → {it['action']}")
        print("결과: " + ("차단(FAIL)" if blocked else "통과"))
    return 1 if blocked else 0


def cmd_template(args):
    meta = {
        "schema": 1,
        "stage": args.stage,
        "slice": args.slice or "",
        **({"unit": args.unit, "asis_covered": []} if args.unit else {}),
        "iteration": 1,
        "agent": args.agent or "",
        "result": "done",
        "started_at": now_kst(),
        "finished_at": now_kst(),
        "repo": {"dir": target_dir() or "", "branch": "", "head": "", "base": "", "dirty": False,
                 "changed_files": []},
        "gates": [
            {"kind": "build", "command": "", "exit_code": 0, "executed_at": now_kst()},
            {"kind": "test", "command": "", "exit_code": 0, "executed_at": now_kst(),
             "axis": "unit", "test_count": 0, "failures": 0, "skipped": 0,
             "results": ["backend/build/test-results/test/*.xml"]},
        ],
        "open_items": [],
        "judgments": [],
        "rr_ids": [],
        "common_candidates": [],
        "not_executed": [],
        "risk_surface": [],
        "cost": {"duration_min": 0, "tool_calls": 0, "tokens_k": 0},
    }
    entry, _sp = slice_entry(args.slice)
    if entry and entry.get("units") and not args.unit and args.stage == 2:
        # unit 으로 나눈 slice 의 통합 레포트 — unit 을 가로지르는 흐름 테스트를 따로 적는다
        meta["gates"].append({"kind": "test", "suite": "flow", "command": "", "exit_code": 0, "executed_at": now_kst(),
                              "axis": "unit", "test_count": 0, "failures": 0, "skipped": 0, "results": []})
    print(META_START)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(META_END)
    return 0


def cmd_secrets(args):
    findings = []
    for target in args.paths:
        p = target if os.path.isabs(target) else os.path.normpath(os.path.join(ROOT, target))
        files = []
        if os.path.isdir(p):
            for ext in ("*.md", "*.txt", "*.json", "*.yaml", "*.yml", "*.log", "*.html"):
                files.extend(glob.glob(os.path.join(p, "**", ext), recursive=True))
        else:
            files.append(p)
        for fp in files:
            try:
                with open(fp, encoding="utf-8", errors="replace") as fh:
                    findings.extend(scan_secrets_text(fh.read(), safe_relpath(fp, ROOT)))
            except OSError as ex:
                print(f"[gate] 읽기 실패 {fp}: {ex}", file=sys.stderr)
    if args.format == "json":
        print(json.dumps({"findings": findings}, ensure_ascii=False, indent=2))
    else:
        for it in findings:
            print(f"- {it['field']}: {it['message']}")
        print(f"총 {len(findings)}건")
    return 1 if findings else 0


# ---------------------------------------------------------------- open item

def next_oi_id(items):
    nums = [int(m.group(1)) for i in items
            for m in [re.match(r"OI-(\d{4})$", str(i.get("id", "")))] if m]
    return f"OI-{(max(nums) + 1 if nums else 1):04d}"


def cmd_oi(args):
    os.makedirs(WS, exist_ok=True)
    if args.oi_cmd == "import":
        return cmd_oi_import(args)
    if args.oi_cmd == "list":
        return oi_list(args, load_open_items()["items"])
    # new·set 은 open-items.yaml 을 읽고-고치고-쓴다. 병렬 에이전트가 서로의 기록을 덮어쓰지 않도록
    # 읽기부터 쓰기까지를 하나의 잠금 안에서 처리한다.
    with file_lock(OI_FILE):
        data = load_open_items()
        if args.oi_cmd == "new":
            return oi_new(args, data)
        if args.oi_cmd == "set":
            return oi_set(args, data)
    return 2


def oi_new(args, data):
    """확인 필요 항목 1건을 채번해 추가한다. (호출자가 OI_FILE 잠금을 잡고 있어야 한다)"""
    items = data["items"]
    if args.kind not in OI_KINDS:
        sys.exit(f"[gate] kind 는 {'|'.join(OI_KINDS)}")
    if args.severity not in SEVERITIES:
        sys.exit(f"[gate] severity 는 {'|'.join(SEVERITIES)}")
    if args.axis and args.axis not in AXES:
        sys.exit(f"[gate] axis 는 {'|'.join(AXES)}")
    oid = next_oi_id(items)
    rec = {"id": oid, "found_at": now_kst(), "stage": args.stage, "slice": args.slice or "",
           "kind": args.kind, "severity": args.severity, "summary": args.summary,
           "evidence": args.evidence, "target_stage": args.target, "axis": args.axis or "",
           "owner": args.owner or "", "rr_id": "", "status": "open",
           "approved_by": "", "expiry": "", "note": ""}
    items.append(rec)
    dump_yaml(OI_FILE, data)
    print(oid)
    print(OI_FILE)
    return 0


def oi_list(args, items):
    """확인 필요 항목을 조건으로 걸러 표로 출력한다. (읽기 전용이라 잠그지 않는다)"""
    rows = [i for i in items
            if (not args.status or i.get("status") == args.status)
            and (not args.slice or i.get("slice") == args.slice)
            and (args.target is None or str(i.get("target_stage")) == str(args.target))]
    if not rows:
        print("해당 항목 없음")
        return 0
    print(f"{'ID':<8} {'sev':<7} {'kind':<12} {'→단계':<6} {'상태':<10} slice / 요약")
    for i in rows:
        print(f"{i.get('id',''):<8} {i.get('severity',''):<7} {i.get('kind',''):<12} "
              f"{str(i.get('target_stage','')):<6} {i.get('status',''):<10} "
              f"{i.get('slice','')} / {str(i.get('summary',''))[:60]}")
    print(f"총 {len(rows)}건")
    return 0


def oi_set(args, data):
    """확인 필요 항목의 상태를 바꾼다. (호출자가 OI_FILE 잠금을 잡고 있어야 한다)"""
    if args.status not in OI_STATUSES:
        sys.exit(f"[gate] status 는 {'|'.join(OI_STATUSES)}")
    for i in data["items"]:
        if i.get("id") == args.id:
            i["status"] = args.status
            if args.rr:
                i["rr_id"] = args.rr
            if args.note:
                i["note"] = args.note
            if args.approved_by:
                i["approved_by"] = args.approved_by
            if args.expiry:
                i["expiry"] = args.expiry
            if args.target is not None:
                # 재예약: 닫을 단계를 옮긴다. 이전 값은 note 에 남겨 추적이 끊기지 않게 한다
                prev = i.get("target_stage")
                i["target_stage"] = args.target
                i["note"] = (f"{i.get('note', '')} " if i.get("note") else "") + f"[재예약 {prev}→{args.target}]"
            i["updated_at"] = now_kst()
            if args.status == "converted" and not i.get("rr_id"):
                sys.exit("[gate] converted 는 --rr RR-xxxx 가 필요하다")
            if args.jd:
                if args.jd not in {j.get("id") for j in judgment.load_judgments()["items"] if isinstance(j, dict)}:
                    sys.exit(f"[gate] {args.jd} 가 judgments.yaml 에 없다")
                i["jd_id"] = args.jd
            if args.status == "resolved" and i.get("kind") == "decision" and not i.get("jd_id"):
                # 결정은 판단이다 — 무엇으로 정했는지가 재검증 대상으로 남아야 한다 (pipeline-core §21)
                sys.exit("[gate] decision 항목의 resolved 는 --jd JD-xxxx 가 필요하다 "
                         "(python tools/judgment.py new … --oi " + str(i.get("id")) + " 로 먼저 채번)")
            if args.status == "accepted" and not (i.get("approved_by") and i.get("expiry")):
                sys.exit("[gate] accepted 는 --approved-by 와 --expiry(YYYY-MM-DD) 가 필요하다")
            dump_yaml(OI_FILE, data)
            print(f"{args.id} → {args.status}")
            return 0
    sys.exit(f"[gate] {args.id} 를 찾지 못했다")


def cmd_plan(args):
    """/run 의 진행 계획을 계산한다 — 선행조건·웨이브·축 요구·멈춤 조건.

    /run 이 이 계산을 매번 산문으로 재구현하면 어긋난다. 계획은 도구가 한 곳에서 만든다.
    """
    cfg = config()
    if not os.path.exists(STATE):
        sys.exit(f"[gate] state.yaml 이 없다: {STATE}")
    st = load_yaml(STATE)
    sl_data, spath = load_slices()
    if not sl_data:
        sys.exit(f"[gate] slices.yaml 을 읽지 못했다: {spath}")
    all_slices = {s["id"]: s for s in (sl_data.get("slices") or []) if isinstance(s, dict)}
    maxp = int(((cfg.get("pipeline") or {}).get("max_parallel") or 1))
    amap = trait_axis_map()

    # 착수 보류(hold): 근거 대기 slice 와 그것에 (전이적으로) 의존하는 slice 는 착수 대상에서 뺀다
    held_ids = {i for i, s in all_slices.items() if held(s)}
    blocked_by_hold = {}
    changed = True
    while changed:
        changed = False
        for i, s in all_slices.items():
            if i in held_ids or i in blocked_by_hold:
                continue
            deps = [d for d in (s.get("depends_on") or []) if d in held_ids or d in blocked_by_hold]
            if deps:
                blocked_by_hold[i] = deps
                changed = True
    hold_notes = [f"{i}: {hold_text(all_slices[i])}" for i in sorted(held_ids)]
    hold_notes += [f"{i}: 선행 slice {', '.join(d)} 가 근거 대기 hold" for i, d in sorted(blocked_by_hold.items())]
    slices = {i: s for i, s in all_slices.items() if i not in held_ids and i not in blocked_by_hold}

    # 웨이브 편성 (depends_on 위상 정렬)
    waves, done, remaining, cyc = [], set(), dict(slices), []
    while remaining:
        ready = sorted([i for i, s in remaining.items()
                        if all(d in done for d in (s.get("depends_on") or []))],
                       key=lambda i: slices[i].get("priority", 99))
        if not ready:
            cyc = sorted(remaining)
            break
        waves.append(ready)
        done |= set(ready)
        for i in ready:
            remaining.pop(i)

    # 열린 확인 필요 항목 / RR
    items = [i for i in load_open_items()["items"] if isinstance(i, dict) and i.get("status") == "open"]
    blocking = [i for i in items if i.get("severity") in BLOCKING_SEV]
    unreserved = [i for i in blocking if i.get("target_stage") in (None, "")]
    rr_open = int((st.get("refactor_requests") or {}).get("open") or 0)

    # 멈춤 조건 (run.md 의 표를 그대로 검사)
    stops = []
    if not sl_data.get("approved"):
        stops.append("slices.yaml approved=false — 1단계 승인은 사람 몫 (pipeline-core §10)")
    if unreserved:
        stops.append(f"blocker/high 확인 필요 항목 {len(unreserved)}건이 닫을 단계 예약 없이 열려 있다")
    if cyc:
        stops.append(f"depends_on 순환: {', '.join(cyc)}")

    # 큰 slice 의 unit 분할 (slice_units.py) — 구조 오류는 멈춤, 기준 초과인데 나누지 않은 slice 는 알림
    import slice_units as su
    th = su.thresholds(cfg)
    unit_plan, size_notes = {}, []
    sstate_all = st.get("slices") or {}
    for i, s in slices.items():
        v, reasons = su.verdict(su.slice_metrics(s, None, th["chars_per_token"]), th)
        if su.units_of(s):
            bad = [x for x in su.validate_structure(s) if x["severity"] == "FAIL"]
            if bad:
                stops.append(f"{i} 의 unit 분할 구조 오류 {len(bad)}건 — python tools/slice_units.py validate --slice {i}")
            waves_u, _c = su.unit_waves(su.units_of(s))
            seq = [u for w in waves_u for u in w]
            un = ((sstate_all.get(i) or {}).get("units") or {})
            unit_plan[i] = {"sequence": seq,
                            "stage2_done": sum(1 for u in seq if (un.get(u) or {}).get("stage2_backend") == "done"),
                            "stage4_done": sum(1 for u in seq if (un.get(u) or {}).get("stage4_frontend") == "done"),
                            "flows": [fl.get("id") for fl in (s.get("flows") or []) if isinstance(fl, dict)]}
        elif v == "split":
            size_notes.append(f"{i}: {'; '.join(reasons)}")

    # 실행 가능한 단계 계산 (pipeline-core §4)
    stages = st.get("stages") or {}
    sstate = st.get("slices") or {}
    steps = []
    if rr_open and (blocking or rr_open >= 5):
        steps.append(("/refactor", f"열린 RR {rr_open}건 — 다음 단계 전에 먼저 반영"))
    if stages.get("stage2_scaffold") != "done":
        steps.append(("/stage2 scaffold", "골격 1회 — 환경 점검 후 빌드·테스트 게이트"))
    # 차세대: 업무 변환 전에 공통 계약을 확정하고 공통을 먼저 변환한다 (공통 클래스의 업무별 분해 방지)
    if (cfg.get("project") or {}).get("mode") == "migration":
        import common_contract as ccm
        contract = ccm.load_contract()
        if not contract:
            stops.append("공통 계약이 없다 — tools/common_usage.py → tools/common_contract.py init → 사람 검토·승인")
        elif not contract.get("approved"):
            stops.append("공통 계약 approved=false — 승인은 사람 몫 (pipeline-core §17)")
        elif stages.get("stage2_common_port") != "done":
            steps.append(("/stage2 common-port", "공통 선행 변환 — 계약된 공통 전부를 common-porter 가 한 번에"))
    todo2 = [i for i in slices if (sstate.get(i) or {}).get("stage2_backend") != "done"]
    if todo2:
        steps.append(("/stage2 all", f"웨이브 {len(waves)}단 × 동시 {maxp}개, 대상 {len(todo2)} slice"))
    if any((sstate.get(i) or {}).get("stage2_backend") == "done" for i in slices) or todo2:
        steps.append(("/stage3", "공통화 — 공통 후보 흡수"))
    todo4 = [i for i in slices if (sstate.get(i) or {}).get("stage4_frontend") != "done"]
    if todo4:
        steps.append(("/stage4 all", f"프론트 골격 + 웨이브, 대상 {len(todo4)} slice"))
    todo5 = [i for i in slices if (sstate.get(i) or {}).get("stage5_integration") != "done"]
    if todo5 and args.to >= 5:
        steps.append(("/stage5 all", f"통합 테스트, 대상 {len(todo5)} slice"))
    if args.to >= 6 and stages.get("stage6_security") != "done":
        steps.append(("/stage6", "보안 점검"))
    if args.to >= 7 and stages.get("stage7_qa") != "done":
        steps.append(("/stage7", "QA 자동화"))
    if args.to >= 8 and stages.get("stage8_deliverables") != "done":
        steps.append(("/stage8", "산출물"))
    planned, deferred_steps = steps[:args.max], steps[args.max:]

    # 축 요구 집계
    axis_slices = {}
    for i, s in slices.items():
        for t in (s.get("traits") or []):
            for a in amap.get(t, []):
                axis_slices.setdefault(a, []).append(i)
    for a in axis_slices:
        axis_slices[a] = sorted(set(axis_slices[a]))

    batches = sum(-(-len(w) // maxp) for w in waves)
    plan = {
        "project": (cfg.get("project") or {}).get("name"),
        "to": args.to, "max": args.max, "max_parallel": maxp,
        "slices": len(slices), "waves": waves, "batches": batches,
        "serial_waves": [w[0] for w in waves if len(w) == 1],
        "open_items": {"open": len(items), "blocking": len(blocking), "unreserved": len(unreserved)},
        "rr_open": rr_open,
        "axis_requirements": {a: {"slices": len(v), "closed_by": f"stage{AXIS_STAGE.get(a, 5)}"}
                              for a, v in sorted(axis_slices.items())},
        "steps": [{"command": c, "note": n} for c, n in planned],
        "deferred": [{"command": c, "note": n} for c, n in deferred_steps],
        "stops": stops,
        "runnable": not stops,
        "units": unit_plan,
        "split_candidates": size_notes,
        "held": hold_notes,
    }
    if args.format == "json":
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    print(f"/run --to {args.to} --max {args.max} --dry   (project={plan['project']}, max_parallel={maxp})")
    print("\n[선행 확인]")
    print(f"  slices.yaml approved : {sl_data.get('approved')}")
    print(f"  열린 확인 필요 항목  : {len(items)}건 (blocker/high {len(blocking)}, 예약 없음 {len(unreserved)})")
    print(f"  열린 RR              : {rr_open}건")
    print(f"  stage2 골격          : {stages.get('stage2_scaffold')}")
    if (cfg.get("project") or {}).get("mode") == "migration":
        print(f"  stage2 공통 선행 변환: {stages.get('stage2_common_port')}")
    print(f"\n[웨이브] slice {len(slices)} / 동시 {maxp} → 배치 {batches}회")
    for n, w in enumerate(waves, 1):
        mark = "  <- slice 1개, 병렬 손실" if len(w) == 1 else ""
        print(f"  w{n} ({len(w)}) {', '.join(w)}{mark}")
    if unit_plan or size_notes:
        print("\n[unit 분할 — 큰 slice]")
        for i, u in unit_plan.items():
            print(f"  {i:<16} unit {len(u['sequence'])}개 순차: {' -> '.join(u['sequence'])}"
                  f"  (BE {u['stage2_done']}/{len(u['sequence'])}, FE {u['stage4_done']}/{len(u['sequence'])})"
                  f"  흐름 {', '.join(u['flows']) or '-'}")
        for n in size_notes:
            print(f"  분할 후보(units 없음) {n}")
    if hold_notes:
        print("\n[착수 보류 — 근거 대기 hold, 이번 계획에서 제외]")
        for n in hold_notes:
            print(f"  - {n}")
    print(f"\n[진행 계획] 최대 {args.max}단계")
    for n, (c, note) in enumerate(planned, 1):
        print(f"  {n}. {c:<18} {note}")
    for c, note in deferred_steps:
        print(f"  -  {c:<18} {note}  (--max 초과 → 다음 /run)")
    print("\n[검증 축 요구]")
    for a, v in plan["axis_requirements"].items():
        print(f"  {a:<16} {v['slices']:>2} slice   닫을 단계 {v['closed_by']}")
    print(f"\n[판정] {'실행 가능' if plan['runnable'] else '멈춤'}")
    for s in stops:
        print(f"  x {s}")
    if stops:
        print(f"\n  사람이 할 일: {stops[0]}")
        print(f"  이어갈 명령 : /run --to {args.to}")
    return 0


def write_meta_back(report, meta):
    """레포트의 pa-meta 블록을 갱신한 meta 로 교체한다."""
    with open(report, encoding="utf-8") as fh:
        text = fh.read()
    s, e = text.find(META_START), text.find(META_END)
    if s < 0 or e < 0:
        return False
    body = json.dumps(meta, ensure_ascii=False, indent=2)
    new = text[:s] + META_START + "\n" + body + "\n" + text[e:]
    with open(report, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(new)
    return True


def cmd_oi_import(args):
    """레포트 pa-meta 의 open_items 를 일괄 채번하고 레포트에 id 를 써넣는다.

    규모가 커지면 항목이 수십 건이 되므로 한 건씩 oi new 를 부르는 것은 현실적이지 않다.
    """
    report = args.report if os.path.isabs(args.report) else os.path.normpath(os.path.join(ROOT, args.report))
    meta, err = extract_meta(report)
    if err:
        sys.exit(f"[gate] {err}")
    items = meta.get("open_items")
    if not isinstance(items, list):
        sys.exit("[gate] pa-meta.open_items 가 배열이 아니다")
    os.makedirs(WS, exist_ok=True)
    # 채번과 저장을 한 잠금 안에서 해야 병렬 호출이 같은 번호를 받지 않는다
    with file_lock(OI_FILE):
        return _oi_import_locked(args, report, meta, items)


def _oi_import_locked(args, report, meta, items):
    data = load_open_items()
    store = data["items"]
    known = {i.get("id") for i in store if isinstance(i, dict)}
    added, skipped = [], 0
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("id") and it["id"] in known:
            skipped += 1
            continue
        if it.get("kind") not in OI_KINDS or it.get("severity") not in SEVERITIES:
            sys.exit(f"[gate] kind/severity 가 유효하지 않다: {it.get('summary', '')[:40]}")
        oid = next_oi_id(store)
        rec = {"id": oid, "found_at": now_kst(), "stage": meta.get("stage"),
               "slice": it.get("slice") or meta.get("slice") or "",
               "kind": it["kind"], "severity": it["severity"],
               "summary": it.get("summary", ""), "evidence": it.get("evidence", ""),
               "target_stage": it.get("target_stage"), "axis": it.get("axis") or "",
               "owner": it.get("owner") or "", "rr_id": "", "status": "open",
               "approved_by": "", "expiry": "", "note": ""}
        store.append(rec)
        known.add(oid)
        it["id"] = oid
        added.append(rec)
    dump_yaml(OI_FILE, data)
    if args.write:
        write_meta_back(report, meta)
    print(f"채번 {len(added)}건 (기존 {skipped}건 건너뜀) → {OI_FILE}")
    for rec in added:
        print(f"  {rec['id']} {rec['severity']:<7} {rec['kind']:<12} →stage{rec['target_stage']}  {str(rec['summary'])[:56]}")
    if args.write:
        print(f"레포트 pa-meta 갱신: {report}")
    else:
        print("레포트에 id 를 써넣으려면 --write 를 붙인다")
    return 0


def cmd_trace(args):
    """요구사항 ID → 계약 → 테스트 추적 체인을 slice 별로 전수 대조."""
    data, spath = load_slices()
    if not data:
        sys.exit(f"[gate] slices.yaml 을 읽지 못했다: {spath}")
    td = target_dir()
    if not td or not os.path.isdir(td):
        sys.exit(f"[gate] target_dir 이 없다: {td}")
    rows, broken = [], 0
    for entry in (data.get("slices") or []):
        if not isinstance(entry, dict):
            continue
        if args.slice and entry.get("id") != args.slice:
            continue
        found, missing, contract_ok, contract = trace_slice(td, entry)
        broken += len(missing) + (0 if contract_ok else 1)
        rows.append((entry.get("id"), len(found), missing, contract_ok))
    if args.format == "json":
        print(json.dumps({"slices": [{"id": i, "traced": t, "missing": m, "contract": c}
                                     for i, t, m, c in rows], "broken": broken},
                         ensure_ascii=False, indent=2))
    else:
        print(f"{'slice':<18} {'추적됨':<7} {'계약':<6} 끊긴 요구사항")
        for i, t, m, c in rows:
            print(f"{i:<18} {t:<7} {'OK' if c else '없음':<6} {', '.join(m) if m else '-'}")
        print(f"끊긴 연결 총 {broken}건")
    return 1 if broken and args.strict else 0


def build_parser():
    p = argparse.ArgumentParser(description="단계 레포트 게이트 메타 검증")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="레포트 게이트 검사")
    c.add_argument("--report")
    c.add_argument("--stage", type=int)
    c.add_argument("--slice")
    c.add_argument("--unit", help="큰 slice 를 나눈 unit id (unit 레포트 검사)")
    c.add_argument("--profile", choices=sorted(PROFILES))
    c.add_argument("--format", choices=["human", "json"], default="human")
    c.add_argument("--skip", action="append", metavar="HOOK",
                   help="이 훅은 건너뛴다 (반복 지정). 쓰기 훅이 state 전환 직전에 state-consistency 를 뺄 때 쓴다")
    c.set_defaults(fn=cmd_check)

    t = sub.add_parser("template", help="pa-meta 블록 골격 출력")
    t.add_argument("--stage", type=int, required=True)
    t.add_argument("--slice")
    t.add_argument("--unit")
    t.add_argument("--agent")
    t.set_defaults(fn=cmd_template)

    pl = sub.add_parser("plan", help="/run 의 진행 계획 계산 (선행조건·웨이브·축·멈춤 조건)")
    pl.add_argument("--to", type=int, default=5, help="여기까지 진행 (기본 5)")
    pl.add_argument("--max", type=int, default=4, help="한 번에 실행할 최대 단계 수 (기본 4)")
    pl.add_argument("--format", choices=["human", "json"], default="human")
    pl.set_defaults(fn=cmd_plan)

    tr = sub.add_parser("trace", help="요구사항 → 계약 → 테스트 추적 체인 대조")
    tr.add_argument("--slice")
    tr.add_argument("--format", choices=["human", "json"], default="human")
    tr.add_argument("--strict", action="store_true", help="끊긴 연결이 있으면 종료 코드 1")
    tr.set_defaults(fn=cmd_trace)

    s = sub.add_parser("secrets", help="자격증명·개인정보 스캔")
    s.add_argument("paths", nargs="+")
    s.add_argument("--format", choices=["human", "json"], default="human")
    s.set_defaults(fn=cmd_secrets)

    o = sub.add_parser("oi", help="확인 필요 항목(open item) 관리")
    osub = o.add_subparsers(dest="oi_cmd", required=True)
    on = osub.add_parser("new")
    on.add_argument("--stage", type=int, required=True)
    on.add_argument("--slice")
    on.add_argument("--kind", required=True, choices=OI_KINDS)
    on.add_argument("--severity", required=True, choices=SEVERITIES)
    on.add_argument("--summary", required=True)
    on.add_argument("--evidence", required=True)
    on.add_argument("--target", type=int, required=True, help="닫을 단계")
    on.add_argument("--axis", choices=AXES, help="이 항목이 기다리는 검증 축")
    on.add_argument("--owner")
    oim = osub.add_parser("import", help="레포트 pa-meta 의 open_items 를 일괄 채번")
    oim.add_argument("--report", required=True)
    oim.add_argument("--write", action="store_true", help="레포트 pa-meta 에 채번한 id 를 써넣는다")
    ol = osub.add_parser("list")
    ol.add_argument("--status", choices=OI_STATUSES)
    ol.add_argument("--slice")
    ol.add_argument("--target", type=int)
    os_ = osub.add_parser("set")
    os_.add_argument("id")
    os_.add_argument("status", choices=OI_STATUSES)
    os_.add_argument("--rr")
    os_.add_argument("--note")
    os_.add_argument("--approved-by", dest="approved_by")
    os_.add_argument("--expiry")
    os_.add_argument("--target", type=int, help="닫을 단계 재예약 (예: 1단계 예약 항목을 2단계로)")
    os_.add_argument("--jd", help="이 항목을 해소한 판단 기록 (decision 의 resolved 에 필수)")
    o.set_defaults(fn=cmd_oi)
    return p


def main():
    args = build_parser().parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
