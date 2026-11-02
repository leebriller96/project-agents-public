#!/usr/bin/env python3
# guard.py — Claude Code 훅: 파이프라인 원칙을 "지침" 이 아니라 도구 호출 시점에 강제한다.
#
# 등록: .claude/settings.json 의 hooks (PreToolUse · PostToolUse · SubagentStop)
#   python tools/hooks/guard.py pre-tool-use     # stdin: 훅 입력 JSON
#   python tools/hooks/guard.py post-tool-use
#   python tools/hooks/guard.py subagent-stop
#
# 강제하는 것
#   1) 이모지 금지 — Write·Edit·MultiEdit·NotebookEdit 의 새 내용, Bash 명령 문자열에 이모지가 있으면 차단.
#      대상 파일을 가리지 않는다(생성 소스·Mapper·yml·DDL·레포트·지침 전부). 예외 없음.
#   2) 게이트 없는 완료 기록 금지 — workspace/<project>/state.yaml 에서 어떤 단계·slice 가 done 으로 바뀌면
#      그 단계 레포트로 `gate.py check` 를 돌려 FAIL 이면 쓰기를 막는다. Bash 로 state.yaml 을 직접 고치는 것은
#      이 검사를 우회하므로 막고 `python tools/state.py set` 을 쓰게 한다(state.py 가 done 전환에 같은 게이트를 돌린다).
#      state.py 실행은 state.yaml 에 쓰는 명령 패턴이 아니므로 막지 않는다. Edit/Write 경로의 완료 전환 검사도 유지한다.
#   3) 결과 블록 없는 서브에이전트 종료 금지 — 파이프라인 에이전트(.claude/agents/*.md)가 pa-agent-result 블록
#      (pipeline-core §12) 없이, 또는 이모지를 넣은 채 끝내려 하면 종료를 막고 보완을 요구한다.
#      보고 산문이 길면(기본 3000자) 막는다 — 보고 전문은 오케스트레이터 문맥에 남아 그 뒤 모든 호출에서 다시 읽힌다.
#   4) 긴 Bash 출력 축약(PostToolUse) — 빌드·테스트 로그가 문맥에 통째로 남으면 그 뒤 모든 호출이 그것을 다시 읽는다
#      (캐시 읽기 비용의 주원인). 기준(기본 6000자)을 넘으면 전체는 로그 파일에 두고 모델에는 앞부분·오류·실패·결과 요약 줄·
#      끝부분만 보여 준다. 명령에 PA_FULL_OUTPUT=1 이 있으면 축약하지 않는다. (pipeline-core §26)
#   5) git 훅 우회 금지 — Bash 의 git 명령에 core.hooksPath 덮어쓰기·--no-verify·commit -n 이 있으면 차단.
#   6) PowerShell 도구 — Bash 와 같은 보호 대상(state.yaml·잠긴 spec·잠금 매니페스트·기준 이미지 기록)을 쓰기 계열
#      cmdlet(별칭·모듈 한정 이름·매개변수 약어 포함)·따옴표 밖 리다이렉션·.NET 파일 쓰기로 쓰면 차단. 대상이 리터럴이
#      아니면 보호 대상 이름이 보일 때 보수적으로 차단. 사람 전용 명령·훅 우회도 Bash 와 같다.
#   7) 인계 도구(SubagentHandback) — 넘기는 보고를 3) 의 결과 계약으로 본다(블록 결손·깨진 JSON·필수 키·이모지만 차단,
#      산문 상한은 경고만) 그리고 저장한다.
#      SubagentStop 도 transcript 의 인계 메시지를 보고로 읽는다(인계 보고는 마지막 텍스트 메시지에 없다).
#   8) 보호 폴더 통째 삭제·이동(Bash·PowerShell 공통) — specs·visual 과 그 상위, 잠긴 파일이 든 상위 폴더,
#      저장소 루트를 끝 / 유무와 관계없이 지우거나 옮기면 차단한다. gitignore 대상까지 지우는 git clean 도 차단한다.
#      읽기는 막지 않는다. 사고를 막는 장치이지 악의적 우회를 막는 보안 경계가 아니다(한계는 16-hooks.md).
#
# 저장소 밖 강제: git pre-commit 훅(tools/hooks/pre-commit, 설치 tools/install_hooks.py)이 커밋 시점에
#   이모지·커밋 금지 경로를 다시 본다 — Claude Code 가 아닌 에이전트·사람의 커밋에도 걸린다.
#
# 종료 코드: 0 허용 · 2 차단(stderr 가 Claude 에게 전달된다)
# 훅 자체의 예기치 않은 오류는 차단하지 않는다(도구 사용이 멈추는 것을 막기 위해). 게이트·selfcheck·CI 가 2차 방어선이다.

import collections
import fnmatch
import glob
import json
import itertools
import os
import posixpath
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)

from _emoji import find_emoji  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

# state.yaml 키 → (단계, slice). slice 가 None 이면 단계 전체 레포트
STAGE_KEYS = {
    "stage0_ingest": (0, None), "stage1_slicing": (1, None), "stage2_scaffold": (2, "scaffold"),
    "stage2_common_port": (2, "common-port"),
    "stage3_common": (3, None), "stage4_scaffold": (4, "scaffold-fe"), "stage5_integration": (5, None),
    "stage6_security": (6, None), "stage7_qa": (7, None), "stage8_deliverables": (8, None),
    "stage9_packaging": (9, None),
}
SLICE_KEYS = {"stage2_backend": 2, "stage4_frontend": 4, "stage5_integration": 5}
UNIT_KEYS = {"stage2_backend": 2, "stage4_frontend": 4}   # 큰 slice 를 나눈 unit (slices.<id>.units.<unit>)

# Bash 로 state.yaml 에 "쓰는" 패턴만 잡는다 (읽기·grep·2>/dev/null 은 허용)
_ST = r"[^\s\"';|&]*state\.yaml"
BASH_STATE_WRITES = [
    re.compile(r">>?\s*[\"']?" + _ST),                                    # 리다이렉션으로 덮어쓰기·덧붙이기
    re.compile(r"\btee\b[^|;&]*" + _ST),
    re.compile(r"\b(?:sed|perl)\b[^|;&]*\s-i\S*[^|;&]*" + _ST),
    re.compile(r"\b(?:mv|cp|install)\b[^|;&]*" + _ST + r"\s*(?:$|[;&|])"),  # 대상(마지막 인자)이 state.yaml
    re.compile(r"(?:Set-Content|Out-File|Add-Content)[^|;&]*" + _ST),
]
STATE_BASENAME = "state.yaml"
PY_OPEN_STATE_RE = re.compile(r"(?:open|Path|dump_yaml|write_text)\(\s*[^)]*state\.yaml")
PY_WRITE_RE = re.compile(r"(?:dump\(|\.write\(|write_text|open\([^)]*[\"'][wa]\+?[\"'])")


def deny(msg):
    sys.stderr.write(msg.rstrip() + "\n")
    sys.exit(2)


def new_texts(tool, ti):
    """도구 입력에서 '새로 쓰이는 내용' 을 모은다."""
    out = []
    for k in ("content", "file_text", "new_string", "new_source", "command"):
        v = ti.get(k)
        if isinstance(v, str):
            out.append(v)
    for e in ti.get("edits") or []:
        if isinstance(e, dict) and isinstance(e.get("new_string"), str):
            out.append(e["new_string"])
    return out


def check_emoji(tool, ti):
    hits = []
    for text in new_texts(tool, ti):
        hits.extend(find_emoji(text))
    if hits:
        where = ti.get("file_path") or ti.get("notebook_path") or "Bash 명령"
        sample = ", ".join(f"{cp}({no}줄)" for no, _c, _ch, cp in hits[:5])
        deny(f"[이모지 금지] {where} 에 쓰려는 내용에 이모지가 있다: {sample}\n"
             "project-agents 는 코드 주석·Mapper 쿼리 주석·yml 주석·DDL COMMENT·레포트·지침 어디에도 이모지를 쓰지 않는다 (CLAUDE.md).\n"
             "텍스트로 바꿔 다시 쓴다 (예: 완료·주의·[의미차이:태그명]). 테스트에서 이모지 문자가 필요하면 escape(\\uXXXX)로 쓴다.")


# ---------------------------------------------------------------- 공개본 금지어 (쓰기 시점)
#
# 실측(2026-10-06, 하루에 세 번): 프로브 시험에 실측 명령을 그대로 붙여 쓰다가 고객 식별 문자열
# (프로젝트명·패키지 경로·시스템 약어)이 tracked 파일로 들어갔다. 세 번 모두 **커밋 뒤에**
# `publish-public --check` 로 잡혔다 - 이미 이력에 박힌 뒤였다.
# 이모지와 같은 성질이므로 같은 자리(쓰기 시점)에서 막는다. 뒤에 있는 publish-public·CI 는 그대로 남는다.
#
# 적용 범위: 이 저장소 안의 **git 에 올라가는** 파일만. workspace/·config/project.yaml 같은
# gitignore 대상과 target_dir 의 파일은 고객 이름이 있어야 정상이므로 보지 않는다.
# 규칙 파일 자신(config/publish-public/rules.yaml)도 제외한다 - 금지어 목록이 거기 있다.
DENY_RULES_REL = "config/publish-public/rules.yaml"
_DENY_CACHE = {}


def deny_patterns():
    """공개본 금지어 정규식. 규칙 파일이 없거나 깨졌으면 빈 목록(검사하지 않는다)."""
    if "pats" in _DENY_CACHE:
        return _DENY_CACHE["pats"]
    pats = []
    try:
        import yaml
        with open(os.path.join(ROOT, DENY_RULES_REL), encoding="utf-8") as f:
            for raw in (yaml.safe_load(f) or {}).get("deny") or []:
                try:
                    pats.append((str(raw), re.compile(str(raw))))
                except re.error:
                    pass
    except Exception:
        pats = []
    _DENY_CACHE["pats"] = pats
    return pats


def is_published_path(path):
    """이 저장소 안의 git 에 올라가는 경로인가 (gitignore 대상·저장소 밖·규칙 파일은 아니다)."""
    if not path:
        return False
    ap = os.path.abspath(path)
    root = os.path.abspath(ROOT)
    if not (ap == root or ap.startswith(root + os.sep)):
        return False
    rel = os.path.relpath(ap, root).replace(os.sep, "/")
    if rel == DENY_RULES_REL:
        return False
    try:
        r = subprocess.run(["git", "check-ignore", "-q", rel], cwd=root,
                           capture_output=True, timeout=10)
    except Exception:
        return False            # git 을 못 쓰면 검사하지 않는다 (쓰기를 전부 막는 쪽이 더 나쁘다)
    # check-ignore 의 종료 코드: 0 = gitignore 대상 · 1 = 아님 · 그 밖(128 등) = 오류(저장소가 아니다 등).
    # 오류를 "추적 대상" 으로 보면 git 저장소가 아닌 곳의 쓰기를 전부 막는다 — 모르면 검사하지 않는다.
    return r.returncode == 1


def check_deny_words(tool, ti):
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    if not path or not is_published_path(path):
        return
    pats = deny_patterns()
    if not pats:
        return
    for text in new_texts(tool, ti):
        for ln, line in enumerate(text.splitlines(), start=1):
            for raw, rx in pats:
                m = rx.search(line)
                if m:
                    rel = os.path.relpath(os.path.abspath(path), os.path.abspath(ROOT))
                    deny(f"[공개본 금지어] {rel.replace(os.sep, '/')} 에 쓰려는 내용 {ln}줄에 "
                         f"«{m.group(0)}» 가 있다 (규칙 {raw}).\n"
                         "이 저장소의 git 에 올라가는 파일에는 고객 식별 문자열을 두지 않는다 (CLAUDE.md).\n"
                         "일반화해서 다시 쓴다 — 예: 프로젝트명은 demo·sample, 패키지는 com.example, "
                         "시스템명은 유형(영문 풀네임 -> 약어 등)으로. 실제 이름은 workspace/ 에만 둔다.")


def is_state_file(path):
    if not path:
        return False
    p = os.path.abspath(path).replace(os.sep, "/")
    return p.endswith("/state.yaml") and "/workspace/" in p


def apply_edit(path, ti):
    """Edit·MultiEdit 적용 후의 파일 내용을 계산한다."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        text = ""
    edits = ti.get("edits") or [ti]
    for e in edits:
        old, new = e.get("old_string"), e.get("new_string")
        if not isinstance(old, str) or not isinstance(new, str):
            continue
        text = text.replace(old, new) if e.get("replace_all") else text.replace(old, new, 1)
    return text


def done_transitions(old, new):
    """old→new 에서 새로 done 이 된 (단계, slice, 키, unit) 목록. unit 이 먼저 나오도록 정렬한다."""
    out = []
    os_, ns = (old or {}).get("stages") or {}, (new or {}).get("stages") or {}
    for k, v in ns.items():
        if v == "done" and os_.get(k) != "done" and k in STAGE_KEYS:
            st, sl = STAGE_KEYS[k]
            out.append((st, sl, f"stages.{k}", None))
    osl, nsl = (old or {}).get("slices") or {}, (new or {}).get("slices") or {}
    for sid, node in nsl.items():
        if not isinstance(node, dict):
            continue
        prev = osl.get(sid) if isinstance(osl.get(sid), dict) else {}
        ou = prev.get("units") if isinstance(prev.get("units"), dict) else {}
        for uid, un in (node.get("units") or {}).items() if isinstance(node.get("units"), dict) else []:
            if not isinstance(un, dict):
                continue
            pu = ou.get(uid) if isinstance(ou.get(uid), dict) else {}
            for k, st in UNIT_KEYS.items():
                if un.get(k) == "done" and pu.get(k) != "done":
                    out.append((st, sid, f"slices.{sid}.units.{uid}.{k}", uid))
        for k, st in SLICE_KEYS.items():
            if node.get(k) == "done" and prev.get(k) != "done":
                out.append((st, sid, f"slices.{sid}.{k}", None))
    return out


def run_gate(stage, slice_id, unit=None, state_file=None):
    cmd = [sys.executable, os.path.join(TOOLS, "gate.py"), "check", "--stage", str(stage),
           "--format", "json", "--skip", "state-consistency"]
    if slice_id:
        cmd += ["--slice", slice_id]
    if unit:
        cmd += ["--unit", unit]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if state_file:   # 기록하려는 새 state 로 판정한다 (unit 완료와 slice 완료를 한 번에 쓰는 경우)
        env["PA_STATE_FILE"] = state_file
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env=env)
    return p


def check_state(tool, ti):
    path = ti.get("file_path")
    if not is_state_file(path):
        return
    import yaml
    try:
        with open(path, encoding="utf-8") as f:
            old = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        old = {}
    new_text = ti.get("content") if tool == "Write" else apply_edit(path, ti)
    if new_text is None:
        new_text = ti.get("file_text", "")
    try:
        new = yaml.safe_load(new_text) or {}
    except yaml.YAMLError as ex:
        deny(f"[state.yaml] 고친 결과가 YAML 로 읽히지 않는다: {ex}")
    problems = []
    trans = done_transitions(old, new)
    tmp = None
    if trans:
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix=".yaml", prefix="pa-state-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(new_text)
    try:
        for stage, sl, key, unit in trans:
            problems.extend(gate_problem(stage, sl, key, unit, tmp))
    finally:
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass
    if problems:
        deny("[게이트] 게이트를 통과하지 못한 단계를 done 으로 기록할 수 없다 (pipeline-core §9).\n"
             + "\n".join(problems)
             + "\n레포트·pa-meta 를 고쳐 gate 를 통과시키거나, 상태를 blocked 로 기록한다."
             + "\n상태 값은 python tools/state.py set 으로 고치는 것이 기본이다 (변경 이력이 남는다).")


def gate_problem(stage, sl, key, unit, state_file):
    """한 전환의 게이트를 돌려, 막히면 설명 한 줄(목록)을 돌려준다."""
    p = run_gate(stage, sl, unit, state_file)
    if p.returncode == 0:
        return []
    try:
        res = json.loads(p.stdout)
        fails = [f"{r['hook']}: {it['field']} {it['message']}" for r in res["results"]
                 for it in r["findings"] if it["severity"] in ("FAIL", "CRITICAL")]
    except (json.JSONDecodeError, KeyError):
        fails = [(p.stderr or p.stdout).strip()[:300] or f"gate.py 종료 코드 {p.returncode}"]
    return [f"- {key} = done → gate.py check --stage {stage}"
            + (f" --slice {sl}" if sl else "") + (f" --unit {unit}" if unit else "")
            + " 차단:\n    " + "\n    ".join(fails[:8])]


def check_bash_state(ti):
    cmd = ti.get("command") or ""
    if "state.yaml" not in cmd:
        return
    # 파이썬 쓰기는 state.yaml 이 실제로 열리는 경로일 때만 본다 (명령 안의 문서 문구에 단어만 있는 경우는 허용)
    py_write = PY_OPEN_STATE_RE.search(cmd) and PY_WRITE_RE.search(cmd)
    # 리다이렉션은 **대상 경로**로 본다 - 종전에는 `>` 가 보이기만 하면 막아
    # 지침 문구의 자리표시자(`workspace/<project>/state.yaml`)에 걸렸다(실측 오검출).
    redir = any(os.path.basename(t) == STATE_BASENAME for t in redirect_targets(cmd))
    arg_write = any(r.search(cmd) for r in BASH_STATE_WRITES[1:])
    if redir or arg_write or py_write:
        deny("[게이트] Bash 로 state.yaml 을 직접 고치면 완료 전환 게이트 검사를 우회한다.\n"
             "상태 값은 python tools/state.py set --stage N [--slice id] [--unit u] --value <값> 으로 고친다\n"
             "(done 은 gate.py check 통과 시에만 기록, blocked 는 --reason 필수, 변경 이력 자동 기록).\n"
             "RR 집계는 python tools/rr.py stats --write, slice 추가 같은 구조 변경은 Edit 도구로 한다.")


# 사람만 실행하는 명령 — 에이전트가 스스로 승인·잠금 해제하면 통제 장치가 의미를 잃는다.
# 사람은 Claude Code 에서 `!` 로 시작하는 셸 모드나 별도 터미널에서 직접 실행한다(도구 호출이 아니므로 훅 대상이 아니다).
def _invocation(script, sub):
    """script 의 sub 명령이 '실행되는 위치'(명령 시작·; && | 뒤·$( · 따옴표 안의 bash -c)에 있을 때만 맞는다.
    문서 문구나 안내 문자열에 명령이 적혀 있는 것만으로는 막지 않는다(실측 오탐)."""
    return re.compile(r"(?:^|[;&|\n`]\s*|\$\(\s*|[\"']\s*)(?:[\w./\\:-]*python[\w.]*|py(?:\s+-3)?)\s+"
                      r"[^\n;&|]*?" + re.escape(script) + r"\s+(?:--\w+(?:[ =]\S+)?\s+)*" + sub + r"\b", re.M)


HUMAN_ONLY_COMMANDS = [
    (_invocation("common_contract.py", "approve"),
     "공통 계약 승인은 사람이 직접 한다: ! python tools/common_contract.py approve --by <이름>"),
    (_invocation("spec_lock.py", "unlock"),
     "잠긴 기대 동작 테스트의 잠금 해제는 사람이 직접 한다: ! python tools/spec_lock.py unlock --slice <id> --by <이름> --reason \"…\""),
]


VISUAL_APPROVE_RX = _invocation("visual.py", "approve")


def delegated():
    """사용자가 사람 전용 명령(공통 계약 승인·잠금 해제·기준 이미지 승인)을 에이전트에 위임했는가.

    프로젝트 설정 `approvals.delegate_to_agent: true` 일 때만 참이다(기본 거짓 - 사람만).
    배경(실측): 사용자가 모바일 원격제어로 진행하면서 `!` 셸 명령을 칠 수 없어 진행이 멈췄고,
    사용자가 "python 명령을 쳐야 넘어가는 일이 없게" 를 지시했다. 위임하면 에이전트가 실행하되
    `--by <위임자>(위임)` 으로 기록하고 실행할 때마다 사용자에게 한 줄로 보고한다(pipeline-core §18)."""
    try:
        from _common import config
        return bool(((config() or {}).get("approvals") or {}).get("delegate_to_agent"))
    except Exception:  # noqa: BLE001 - 설정을 못 읽으면 위임하지 않은 것으로 본다
        return False


def check_human_only_bash(ti):
    cmd = ti.get("command") or ""
    if delegated():
        return
    for rx, msg in HUMAN_ONLY_COMMANDS:
        if rx.search(cmd):
            deny(f"[사람 전용] {msg}")
    if VISUAL_APPROVE_RX.search(cmd):
        from _common import config
        if ((config().get("verification") or {}).get("visual") or {}).get("approver") == "human":
            deny("[사람 전용] 기준 이미지 승인은 사람이 한다(verification.visual.approver: human): "
                 "! python tools/visual.py approve --files <png…> --by <이름>")


def new_file_text(tool, ti):
    path = ti.get("file_path")
    if tool == "Write":
        return ti.get("content") if ti.get("content") is not None else ti.get("file_text", "")
    return apply_edit(path, ti)


def check_contract_approval(tool, ti):
    """공통 계약 파일의 approved 를 false→true 로 바꾸는 편집을 막는다."""
    path = ti.get("file_path") or ""
    if not path.replace(os.sep, "/").endswith("contracts/common-contract.yaml"):
        return
    import yaml
    try:
        with open(path, encoding="utf-8") as f:
            old = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        old = {}
    try:
        new = yaml.safe_load(new_file_text(tool, ti) or "") or {}
    except yaml.YAMLError:
        return
    if new.get("approved") is True and old.get("approved") is not True and not delegated():
        deny("[사람 전용] 공통 계약의 approved 를 에이전트가 바꿀 수 없다.\n"
             "사람이 직접: ! python tools/common_contract.py approve --by <이름>")


# 잠긴 테스트를 Bash 로 고치는 것을 막는다. 두 경로를 **따로** 본다 - 섞으면 오검출이 난다.
#
# 실측(2026-10-06, 같은 부류로 세 번): 리다이렉션을 "> 가 있으면 쓰기" 로 뭉뚱그려 보고
# 파일 이름이 명령문에 **보이기만** 하면 막았더니, 잠긴 테스트를 **읽거나 근거로 인용**하는 명령이 줄줄이 막혔다.
#   - rr.py new --evidence "<잠긴 spec 경로>" 2>&1      (표준오류 복제)
#   - grep -n X <잠긴 spec 경로> 2>/dev/null            (널 장치로 버림)
# 18절은 "테스트가 틀렸다고 판단되면 근거를 RR 로 남긴다" 고 정해 두었는데 그 정상 경로가 막혔다.
#
# 그래서:
#  (1) 리다이렉션은 **대상 경로**를 뽑아 잠긴 파일인지 본다. 파일 서술자 복제(2>&1·>&2)와
#      널 장치(/dev/null)는 애초에 대상이 아니다.
#  (2) 파일을 **인자로 받는** 쓰기 명령(sed -i·rm·mv·cp·tee·truncate·git checkout 등)은
#      종전처럼 명령문에 이름이 보이면 막는다 - 이 명령들은 읽기용으로 쓸 일이 없다.
SPEC_REDIR_RE = re.compile(r"(?<![0-9&])>>?\s*([^\s;|&<>]+)")
SPEC_NULL_TARGETS = ("/dev/null", "nul", "NUL", "/dev/zero")
SPEC_ARG_WRITE_RE = re.compile(r"(\bsed\b[^|;&\n]*\s-i|\bperl\b[^|;&\n]*\s-i|\btee\b|\bmv\b|\brm\b|\bcp\b|"
                               r"\bgit\s+(?:checkout|restore|stash)\b|open\([^)]*[\"\'][wa]\+?[\"\']|"
                               r"write_text|\btruncate\b|\bdd\b)")


# 실측(2026-10-14): 여러 slice 가 같은 이름의 spec 파일(`SpecApp.tsx`·`harness.ts`·`*SpecSupport.java`)을 가진다.
# 파일 이름만 비교했더니 **다른 slice** 의 같은 이름 파일(아직 잠기지 않은 새 slice 의 spec 작성 등)을 다루는
# `git stash`·`cp` 명령, 그리고 그 이름을 주석·문자열로 담기만 한 명령까지 막혔다.
# 명령에 디렉터리까지 적힌 경로는 그 경로로 판정하고, 이름만 적힌 경우(cd 뒤 상대 이름 등)는
# 어느 파일인지 알 수 없으므로 종전처럼 막는다.
PATH_TOKEN_RE = re.compile(r"[^\s;|&<>\"'=(),`]+")


def path_refers_to_locked(token, rel):
    """명령 속 경로 토큰 하나가 잠긴 파일 rel 을 가리킬 수 있는가."""
    t = token.strip().strip("\"'").replace("\\", "/")
    base = os.path.basename(rel)
    if t != base and not t.endswith("/" + base):
        return False
    if "/" not in t:
        return True  # 이름만 - 어느 디렉터리인지 모르므로 보수적으로 잠긴 파일로 본다
    while t.startswith("./"):
        t = t[2:]
    return t == rel or t.endswith("/" + rel) or rel.endswith("/" + t)


def cmd_refers_to_locked(cmd, rel):
    return any(path_refers_to_locked(m.group(0), rel) for m in PATH_TOKEN_RE.finditer(cmd))


def locked_files():
    """{slice: [상대경로…]} - 잠긴 기대 동작 테스트 전체."""
    import spec_lock
    return {sl: list((m.get("files") or {}).keys()) for sl, m in spec_lock.all_manifests().items()}


# `<project>/path` 의 `>` 는 **자리표시자의 닫는 꺾쇠**다 - 리다이렉션이 아니다.
# 실측(2026-10-06): 지침 문구 `workspace/<project>/state.yaml` 때문에 "Bash 로 state.yaml 를 고친다" 로 막혔다.
PLACEHOLDER_CLOSE_RE = re.compile(r"<[^<>\s]*>$")


def redirect_targets(cmd):
    """명령문의 리다이렉션 대상 경로.

    제외: 파일 서술자 복제(`2>&1`·`>&2`) · 널 장치(`/dev/null`) · 자리표시자 닫는 꺾쇠(`<project>/…`).
    """
    out = []
    for m in SPEC_REDIR_RE.finditer(cmd):
        if PLACEHOLDER_CLOSE_RE.search(cmd[:m.start() + 1]):
            continue
        t = m.group(1).strip().strip("\"'")
        if not t or t in SPEC_NULL_TARGETS:
            continue
        out.append(t.replace("\\", "/"))
    return out


def check_locked_spec_write(tool, ti):
    """잠긴 기대 동작 테스트(spec)와 잠금 매니페스트를 도구로 고치지 못하게 한다 (spec_lock.py)."""
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    norm = os.path.abspath(path).replace(os.sep, "/") if path else ""
    if norm and re.search(r"/workspace/[^/]+/specs/", norm):
        deny("[잠금] 잠금 매니페스트는 python tools/spec_lock.py 로만 바뀐다 (직접 편집 금지).")
    if norm and re.search(r"/workspace/[^/]+/visual/", norm):
        deny("[잠금] 기준 이미지 승인 기록은 python tools/visual.py approve 로만 바뀐다 (직접 편집 금지).")
    if not path:
        return
    import spec_lock
    sl = spec_lock.locked_slice_of(path)
    if sl:
        deny(f"[잠금] {path} 는 {sl} 의 잠긴 기대 동작 테스트다. 코드를 고쳐 테스트를 통과시킨다 — 테스트는 바꾸지 않는다.\n"
             "테스트 자체가 틀렸다고 판단되면 근거를 보고의 deviations 와 RR 로 남기고, 잠금 해제는 사람이 한다.")


def check_locked_spec_bash(ti):
    cmd = ti.get("command") or ""
    locked = locked_files()
    if not locked:
        return
    # (1) 리다이렉션 — 대상 경로가 잠긴 파일인가
    targets = redirect_targets(cmd)
    if targets:
        for sl, rels in locked.items():
            for r in rels:
                for t in targets:
                    if path_refers_to_locked(t, r):
                        deny(f"[잠금] Bash 명령이 {sl} 의 잠긴 기대 동작 테스트({r})로 출력을 돌린다. "
                             "잠긴 테스트는 고치지 않는다.")
    # (2) 파일을 인자로 받는 쓰기 명령 — 이름이 보이면 막는다
    if SPEC_ARG_WRITE_RE.search(cmd):
        for sl, rels in locked.items():
            for r in rels:
                if cmd_refers_to_locked(cmd, r):
                    deny(f"[잠금] Bash 명령이 {sl} 의 잠긴 기대 동작 테스트({r})를 바꿀 수 있다. "
                         "잠긴 테스트는 고치지 않는다.\n"
                         "읽기·인용은 막지 않는다 — 리다이렉션으로 그 파일에 쓰거나 "
                         "sed -i·rm·mv·cp·git checkout 류로 다루는 것만 막는다.")


# git 훅을 끄는 커밋·push 를 막는다 - 실측: 에이전트가 커밋에 -c core.hooksPath=/dev/null 을 붙였다
GIT_PREFIX = r"\bgit(?:\s+-[cC]\s*(?:\"[^\"]*\"|'[^']*'|\S+))*\s+"
GIT_HOOK_BYPASS_RE = [
    re.compile(r"\bgit(?:\s+-[cC]\s*(?:\"[^\"]*\"|'[^']*'|\S+))*\s+-c\s*core\.hooks[Pp]ath\b"),
    re.compile(GIT_PREFIX + r"(?:commit|push|merge|am|rebase|cherry-pick)\b[^\n|;&]*\s--no-verify\b"),
    re.compile(GIT_PREFIX + r"commit\b[^\n|;&'\"]*\s-n\b"),
]


def check_git_hook_bypass(ti):
    cmd = ti.get("command") or ""
    if any(r.search(cmd) for r in GIT_HOOK_BYPASS_RE):
        deny("[훅 우회] git 훅을 끄는 옵션(core.hooksPath·--no-verify·commit -n)은 쓰지 않는다. "
             "훅이 막으면 원인을 고치고, 훅이 잘못됐으면 사용자에게 보고한다.")


# ---------------------------------------------------------------- PowerShell 도구 (RR-0602)
#
# Bash 와 같은 보호 대상(state.yaml·잠긴 기대 동작 테스트·잠금 매니페스트·기준 이미지 기록)을 PowerShell 로 쓰는 빈틈을 막는다.
# 정적 판정이다. 명령을 구간(; | 줄바꿈 & ( ) { })으로 나누고 구간 맨 앞 cmdlet(모듈 한정 이름·별칭 포함)의 **대상 경로**를
# 뽑아 보호 대상과 대조한다. 매개변수 이름은 PowerShell 처럼 고유 접두 약어(-Dest·-LiteralP)를 받는다.
# 대상이 리터럴이 아니면(변수·식·Join-Path·파이프 입력) 명령에 보호 대상 이름이 보일 때 보수적으로 막는다.
# 리다이렉션(> >> 2> *>)은 따옴표 밖의 것만 본다. 읽기(Get-Content·Select-String)와 python tools/state.py 실행은 막지 않는다.
# 남는 한계(16-hooks.md): 보호 대상 이름이 명령 어디에도 보이지 않는 간접 쓰기(이름을 조립·다른 스크립트 실행)는 못 본다.

# cmdlet 정본 이름 → (별칭, 대상 경로 매개변수, 위치 인자 규칙, 아는 값 매개변수)
#   위치 규칙: first = 첫 위치 인자가 대상 · all = 위치 인자 전부 · second = 두 번째(복사 대상) · move = 첫·두 번째(옮기기)
PS_WRITE_CMDLETS = {
    "set-content": ({"sc"}, ("path", "literalpath", "pspath"), "first", ("value", "encoding", "stream", "filter", "include", "exclude", "credential", "delimiter")),
    "add-content": ({"ac"}, ("path", "literalpath", "pspath"), "first", ("value", "encoding", "stream", "filter", "include", "exclude", "credential")),
    "clear-content": ({"clc"}, ("path", "literalpath", "pspath"), "all", ("stream", "filter", "include", "exclude", "credential")),
    "out-file": (set(), ("filepath", "literalpath", "pspath", "path"), "first", ("encoding", "inputobject", "width")),
    "tee-object": ({"tee"}, ("filepath", "literalpath", "pspath", "path"), "first", ("inputobject", "variable", "encoding")),
    "new-item": ({"ni"}, ("path", "literalpath", "pspath"), "first", ("name", "itemtype", "type", "value", "credential")),
    "export-csv": ({"epcsv"}, ("path", "literalpath", "pspath"), "first", ("inputobject", "delimiter", "encoding", "useculture", "quotefields", "usequotes")),
    "export-clixml": (set(), ("path", "literalpath", "pspath"), "first", ("inputobject", "depth", "encoding")),
    "export-alias": ({"epal"}, ("path", "literalpath", "pspath"), "first", ("name", "description", "scope", "as")),
    "export-formatdata": (set(), ("path", "literalpath", "pspath"), "first", ("inputobject",)),
    "start-transcript": (set(), ("path", "literalpath", "pspath", "outputdirectory"), "first", ()),
    "compress-archive": (set(), ("destinationpath",), "second", ("path", "literalpath", "compressionlevel")),
    "expand-archive": (set(), ("destinationpath",), "second", ("path", "literalpath")),
    "invoke-webrequest": ({"iwr", "curl", "wget"}, ("outfile",), "none", ("uri", "method", "body", "headers", "contenttype", "infile", "credential")),
    "invoke-restmethod": ({"irm"}, ("outfile",), "none", ("uri", "method", "body", "headers", "contenttype", "infile", "credential")),
    "remove-item": ({"ri", "rm", "del", "erase", "rd", "rmdir"}, ("path", "literalpath", "pspath"), "all", ("filter", "include", "exclude", "stream", "credential")),
    "copy-item": ({"cpi", "cp", "copy"}, ("destination",), "second", ("path", "literalpath", "pspath", "filter", "include", "exclude", "credential", "fromsession", "tosession")),
    "move-item": ({"mi", "mv", "move"}, ("destination", "path", "literalpath", "pspath"), "move", ("filter", "include", "exclude", "credential")),
    "rename-item": ({"rni", "ren"}, ("newname", "path", "literalpath", "pspath"), "move", ("credential",)),
}
PS_ALIAS = {a: name for name, (aliases, *_r) in PS_WRITE_CMDLETS.items() for a in aliases | {name}}
# 값을 받지 않는 스위치 - 다음 토큰을 값으로 먹지 않는다
PS_SWITCHES = ("force", "recurse", "append", "noclobber", "nonewline", "passthru", "whatif", "confirm",
               "container", "asbytestream", "raw", "verbose", "debug", "notypeinformation", "includetypeinformation",
               "update", "usebasicparsing", "skipcertificatecheck", "useculture")
# 접두 약어가 아닌 매개변수 별칭. -ea·-ev·-ov 같은 값 매개변수는 모르는 매개변수로 다음 토큰을 값으로 먹는다.
PS_PARAM_ALIASES = {"lp": "literalpath", "cf": "confirm", "wi": "whatif", "vb": "verbose", "db": "debug"}
PS_NULL_TARGETS = ("$null", "nul", "/dev/null")
# .NET 직접 쓰기 - 첫 인자(옮기기·복사는 두 번째도)가 대상
PS_DOTNET_WRITE_RE = re.compile(
    r"\[(?:System\.)?IO\.(?:File|FileInfo|StreamWriter|FileStream)\]::(?:WriteAll\w*|AppendAll\w*|AppendText|Create\w*|"
    r"OpenWrite|Open|Delete|Move|Copy|Replace|new)\s*\(([^)]*)\)"
    r"|New-Object\s+(?:-TypeName\s+)?(?:System\.)?IO\.(?:StreamWriter|FileStream)\s*(?:-ArgumentList\s*)?\(?([^)\n;|]*)",
    re.I)


BRACED_VAR_MAX = 256      # 닫는 중괄호를 찾는 거리. 짝 없는 `${` 가 많은 입력에서 훅이 느려지지 않게 한다


def _ps_split(cmd):
    """명령문을 ; | 줄바꿈 & ( ) { } 기준으로 나눈 (토큰 목록, 끝 구분자) 목록. 따옴표 안의 구분자는 나누지 않는다.
    `&&`·`||` 는 구분자 하나로 본다. 토큰이 빈 구간도 돌려준다 - 문장 끝 구분자를 잃지 않기 위해서다."""
    segs, cur, tok, quote, i = [], [], "", None, 0
    while i < len(cmd):
        ch = cmd[i]
        if quote:
            if ch == quote:
                if quote == "'" and cmd[i + 1:i + 2] == "'":   # '' 는 작은따옴표 escape
                    tok += "'"
                    i += 2
                    continue
                quote = None
            elif ch == "`" and quote == '"' and i + 1 < len(cmd):
                tok += cmd[i + 1]
                i += 2
                continue
            else:
                tok += ch
        elif ch in "'\"":
            quote = ch
        elif ch == "$" and cmd[i + 1:i + 2] == "{" and 0 < cmd.find("}", i, i + BRACED_VAR_MAX) \
                and "\n" not in cmd[i:cmd.find("}", i, i + BRACED_VAR_MAX)]:
            j = cmd.find("}", i, i + BRACED_VAR_MAX) + 1      # ${D} 는 변수 하나다 - 중괄호에서 나누면 대상이 낱개 $ 로 남는다
            tok += cmd[i:j]
            i = j
            continue
        elif ch in " \t":
            if tok:
                cur.append(tok)
            tok = ""
        elif ch in ";|\n\r&(){}":
            if tok:
                cur.append(tok)
            sep = cmd[i:i + 2] if cmd[i:i + 2] in ("&&", "||") else ch
            segs.append((cur, sep))
            tok, cur = "", []
            i += len(sep)
            continue
        else:
            tok += ch
        i += 1
    if tok:
        cur.append(tok)
    if cur:
        segs.append((cur, ""))
    return segs


def _ps_segments(cmd):
    """명령문을 나눈 토큰 목록들 (빈 구간 제외)."""
    return [toks for toks, _sep in _ps_split(cmd) if toks]


def ps_unquoted(cmd):
    """따옴표 안 내용을 공백으로 지운 명령문 (문구 안 단어로 오검출하지 않게)."""
    out, quote = [], None
    for ch in cmd:
        if quote:
            out.append(" " if ch != quote else ch)
            if ch == quote:
                quote = None
        else:
            if ch in "'\"":
                quote = ch
            out.append(ch)
    return "".join(out)


def ps_redirect_targets(cmd):
    """따옴표 밖 리다이렉션(> >> 2> 3>> *>)의 대상. 스트림 합치기(2>&1)·$null 은 제외."""
    out, quote, i, n = [], None, 0, len(cmd)
    while i < n:
        ch = cmd[i]
        if quote:
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            i += 1
            continue
        if ch != ">":
            i += 1
            continue
        i += 1
        if i < n and cmd[i] == ">":
            i += 1
        while i < n and cmd[i] in " \t":
            i += 1
        if i < n and cmd[i] == "&":
            continue                       # 2>&1 - 파일이 아니다
        if i < n and cmd[i] in "'\"":
            q = cmd[i]
            j = cmd.find(q, i + 1)
            j = n if j < 0 else j
            t, i = cmd[i + 1:j], j + 1
        else:
            m = re.match(r"[^\s;|&<>()]+", cmd[i:])
            t = m.group(0) if m else ""
            i += len(t)
        if t and t.lower() not in PS_NULL_TARGETS:
            out.append(t)
    return out


def _ps_param(key, cands):
    """매개변수 이름(약어 포함)이 cands 중 하나의 접두면 그 정본 이름. 여럿이면 앞의 것(경로 쪽을 먼저 둔다)."""
    for c in cands:
        if c.startswith(key):
            return c
    return None


def _ps_args(tokens, path_params, value_params):
    """cmdlet 뒤 인자 → ({정본 경로 매개변수: [값]}, 위치 인자 목록).

    이름은 PowerShell 처럼 고유 접두 약어를 받는다. 경로 매개변수와 겹치는 약어는 경로로 본다(보수적으로).
    값 매개변수·모르는 매개변수는 다음 토큰을 값으로 먹고, 스위치는 먹지 않는다."""
    named, positional, i = {}, [], 0
    while i < len(tokens):
        t = tokens[i]
        if re.match(r"^-[A-Za-z]", t):
            name, colon, val = t[1:].partition(":")
            key = PS_PARAM_ALIASES.get(name.lower(), name.lower())
            canon = _ps_param(key, path_params)
            has_next = i + 1 < len(tokens) and not re.match(r"^-[A-Za-z]", tokens[i + 1])
            if canon:
                if colon:
                    named.setdefault(canon, []).append(val)
                elif has_next:
                    named.setdefault(canon, []).append(tokens[i + 1])
                    i += 1
                else:
                    named.setdefault(canon, []).append("")   # 값이 따로 오지 않음 - 식·파이프 입력
            elif colon:
                pass
            elif _ps_param(key, value_params) or not _ps_param(key, PS_SWITCHES):
                if has_next:
                    i += 1
        else:
            positional.append(t)
        i += 1
    return named, positional


def _ps_cmdlet(tok):
    """토큰이 쓰기 cmdlet 이면 정본 이름. 모듈 한정 이름(Microsoft.PowerShell.Management\\Set-Content)도 받는다."""
    name = tok.lower()
    if "\\" in name and re.match(r"^[\w.]+\\[\w-]+$", name):
        name = name.rsplit("\\", 1)[1]
    return PS_ALIAS.get(name)


def ps_writes(cmd):
    """PowerShell 명령의 쓰기 대상. (리터럴 대상 목록, 리터럴이 아닌 대상이 있는가)."""
    out, dynamic = [], False
    for seg in _ps_segments(cmd):
        for k, tok in enumerate(seg):
            # cmdlet 은 구간 맨 앞(또는 대입 = 뒤)에 온다 - `git rm` 같은 다른 명령의 인자는 cmdlet 이 아니다
            if k > 0 and seg[k - 1] != "=":
                continue
            canon = _ps_cmdlet(tok)
            if not canon:
                continue
            _al, path_params, rule, value_params = PS_WRITE_CMDLETS[canon]
            named, pos = _ps_args(seg[k + 1:], path_params, value_params)
            src = [v for p in ("path", "literalpath", "pspath") for v in named.get(p, [])]
            found = []
            if rule == "first":
                found = [v for p in path_params for v in named.get(p, [])] or pos[:1]
            elif rule == "all":
                found = [v for p in path_params for v in named.get(p, [])] + pos
            elif rule == "second":
                dest = [v for p in path_params for v in named.get(p, [])]
                found = dest or (pos if src else pos[1:])[:1]
            elif rule == "move":
                dest = named.get("destination", []) + named.get("newname", [])
                if not dest:
                    dest = (pos if src else pos[1:])[:1]
                found = dest + (src or pos[:1])        # 옮기기·이름 바꾸기는 원본도 없앤다
            else:
                found = [v for p in path_params for v in named.get(p, [])]
            if canon == "new-item":
                names = _ps_args(seg[k + 1:], ("name",), ())[0].get("name", [])
                if names:
                    found = [(b.rstrip("/\\") + "/" if b else "") + nm for b in (found or [""]) for nm in names]
            if not found and rule != "none":
                dynamic = True                           # 대상이 식·파이프 입력으로 온다
            for t in found:
                if not t or t.startswith(("$", "@")) or "$(" in t:
                    dynamic = True
                else:
                    out.append(t)
            break
    for m in PS_DOTNET_WRITE_RE.finditer(cmd):
        args = m.group(1) if m.group(1) is not None else (m.group(2) or "")
        lits = re.findall(r"[\"']([^\"']+)[\"']", args)
        if lits:
            out += lits[:2]
        else:
            dynamic = True
    for t in ps_redirect_targets(cmd):
        if t.startswith("$") or "$(" in t:
            dynamic = True
        else:
            out.append(t)
    return [t.replace("\\", "/") for t in out if t and t.strip().lower() not in PS_NULL_TARGETS], dynamic


def ps_write_targets(cmd):
    return ps_writes(cmd)[0]


# 보호 폴더. 경로 토큰 하나에도, 명령문 전체(대상이 파이프 입력일 때)에도 쓴다 - 그래서 앞뒤를 인자 경계로 본다.
# 끝 / 를 요구하면 폴더 통째 삭제·이동(`rm -rf workspace/<p>/specs`)이 통과하고, 끝을 그냥 풀면 `specs_old.txt` 까지 걸린다.
PROTECTED_DIR_RE = re.compile(r"(?:^|[/\s\"'=(,;|&])workspace/[^/\s\"']+/(?:specs|visual)(?=[/\s\"'`;|&,()<>*?\[]|$)", re.I)
# 보호 폴더의 상위(workspace, workspace/<project>) - 지우거나 옮길 때만 본다. 점이 있는 이름은 폴더가 아니라 파일로 본다.
PROTECTED_PARENT_RE = re.compile(r"(?:^|/)workspace(?:/[^/.*?\[\s]+)?$", re.I)
PROTECTED_LEAF_NAMES = ("specs", "visual")
WORKSPACE_NAMES = ("workspace",)
GLOB_CHARS_RE = re.compile(r"[*?\[]")

# 명령 하나의 판정 재료 (Bash·PowerShell 공통).
#   gone: 지우거나 옮기는 원본 경로. dynamic: 대상을 리터럴로 알 수 없는 삭제가 있다.
#   into: 옮기는 목적지 - 상위 폴더로 넣는 것은 막지 않고 specs·visual 안일 때만 막는다.
#   git_clean: gitignore 대상까지 지우는 git clean 이 있다.
Removals = collections.namedtuple("Removals", "gone dynamic into git_clean")


def _norm_target(token):
    """경로 토큰을 판정용으로 정리한다: 따옴표·역슬래시·`.`·`..`·끝 / 와 끝의 `/*`(폴더 안 전부)."""
    t = token.strip().strip("\"'").replace("\\", "/")
    if not t:
        return ""
    t = re.sub(r"(?:/\*+)+$", "", posixpath.normpath(t))
    return posixpath.normpath(t) if t else ""


def _abs_key(path):
    """절대 경로 비교용 표기(소문자, Git Bash 의 /c/x 는 c:/x). 상대 경로면 None."""
    p = re.sub(r"^/([a-z])(?=/|$)", r"\1:", _norm_target(path).lower())
    return p if len(p) > 1 and (p.startswith("/") or re.match(r"^[a-z]:", p)) else None


def contains_repo(token):
    """절대 경로 토큰이 이 저장소 루트이거나 그 상위인가."""
    key, root = _abs_key(token), _abs_key(ROOT)
    return bool(key and root and (root == key or root.startswith(key + "/")))


def _seg_matches(seg, names):
    """경로 한 구간(글자 패턴 포함)이 이름 중 하나에 맞는가. `*`·`?` 뿐인 구간은 아무 폴더에나 맞아 판단 근거가 못 된다."""
    s = seg.lower()
    return bool(s.strip("*?")) and any(fnmatch.fnmatchcase(n, s) for n in names)


def _glob_touches_protected(t):
    """글자 패턴 경로(`workspace/p/spec*`·`work*/p/specs`)가 보호 폴더나 그 상위에 맞을 수 있는가."""
    segs = t.split("/")
    for i, seg in enumerate(segs):
        if not _seg_matches(seg, WORKSPACE_NAMES):
            continue
        rest = segs[i + 1:]
        if not rest or (len(rest) == 1 and "." not in rest[0]):
            return True
        if len(rest) >= 2 and _seg_matches(rest[1], PROTECTED_LEAF_NAMES):
            return True
    return False


def touches_protected(token):
    """이 경로를 지우거나 옮기면 보호 폴더가 사라지는가."""
    t = _norm_target(token)
    if not t:
        return False
    if PROTECTED_DIR_RE.search(t) or PROTECTED_PARENT_RE.search(t) or contains_repo(t):
        return True
    return bool(GLOB_CHARS_RE.search(t)) and _glob_touches_protected(t)


def path_contains_locked(token, rel, base=None):
    """경로 토큰이 잠긴 파일 rel 의 상위 폴더인가. 대소문자는 접어서 본다(Windows 파일 시스템이 구분하지 않는다).
    잠금 경로는 target_dir 기준 상대경로라 뒷부분 일치도 본다. 한 단계짜리 이름(`server`)은 그 이름 그대로일 때만 맞다 -
    `/tmp/server` 까지 막지 않는다. base(target_dir 의 절대 경로 표기)를 주면 절대 경로 토큰은 잠긴 파일의 절대 경로로 비교한다."""
    t = _norm_target(token).lower()
    if not t or t in (".", ".."):
        return False
    rel = rel.lower()
    key = _abs_key(t)
    if key and base and (base + "/" + rel).startswith(key + "/"):
        return True
    d = posixpath.dirname(rel)
    while d:
        if t == d or ("/" in d and t.endswith("/" + d)) or ("/" in t and d.endswith("/" + t)):
            return True
        d = posixpath.dirname(d)
    return False


def check_protected_removal(label, rem, cmd):
    """지우거나 옮기는 대상이 보호 폴더(또는 그 상위)·잠긴 파일의 상위 폴더인지 본다 (Bash·PowerShell 공통)."""
    norm = cmd.replace("\\", "/")
    if rem.git_clean:
        deny(f"[잠금] {label} 명령의 git clean -x·-X 는 gitignore 대상인 workspace/ 를 지운다. git 으로 복구할 수 없다.\n"
             "-x 없이 쓰거나(-fd), 지울 경로를 workspace 밖으로 적거나, -n 으로 미리 본다.")
    if (any(touches_protected(t) for t in rem.gone)
            or any(PROTECTED_DIR_RE.search(_norm_target(t)) for t in rem.into)
            or (rem.dynamic and PROTECTED_DIR_RE.search(norm))):
        deny(f"[잠금] {label} 명령이 보호 폴더(workspace/<project>/specs·visual 또는 그 상위 폴더)를 지우거나 옮긴다.\n"
             "잠금 매니페스트·기준 이미지 승인 기록은 spec_lock.py·visual.py 로만 바뀐다. 읽기(ls·cat 등)는 막지 않는다.")
    if not (rem.gone or rem.dynamic):
        return
    locked = locked_files()
    if not locked:
        return
    tokens = list(rem.gone)
    if rem.dynamic:
        tokens += [m.group(0) for m in PATH_TOKEN_RE.finditer(norm) if "/" in m.group(0)]
    from _common import target_dir
    base = _abs_key(target_dir() or "")
    for sl, rels in locked.items():
        for r in rels:
            if any(path_contains_locked(t, r, base) for t in tokens):
                deny(f"[잠금] {label} 명령이 {sl} 의 잠긴 기대 동작 테스트({r})가 든 폴더를 지우거나 옮긴다. "
                     "잠긴 테스트는 고치지 않는다.")


# Bash 에서 파일을 없애거나 옮기는 명령. 복사·리다이렉션은 여기서 보지 않는다(16-hooks.md 의 한계).
BASH_REMOVERS = ("rm", "rmdir", "unlink", "mv")
BASH_PREFIX_WORDS = ("then", "do", "else", "elif", "if", "while", "until", "!")
BASH_DECL_WORDS = ("export", "declare", "typeset", "readonly", "local")
# 다른 명령을 실행하는 앞붙이 → 값을 받는 짧은 옵션. 통상 형태만 본다(긴 옵션의 값은 따로 보지 않는다).
BASH_WRAPPERS = {"sudo": "ugChprtTU", "doas": "uC", "timeout": "sk", "nice": "n", "ionice": "cnp", "env": "uCS",
                 "time": "fo", "command": "", "exec": "a", "nohup": ""}
BASH_ASSIGN_RE = re.compile(r"^\w+=")
BASH_VAR_RE = re.compile(r"\$\{?(\w+)\}?")
BASH_REDIRECT_RE = re.compile(r"^[\d*]*[<>]")
# xargs 의 값 받는 옵션. 짧은 옵션은 값 없는 옵션(-0·-p·-r·-t·-x)과 붙어 올 수 있다.
XARGS_VALUE_SHORT_RE = re.compile(r"-[0prtx]*[aEILnPsdJ]")
XARGS_VALUE_LONG = ("--arg-file", "--delimiter", "--eof", "--max-lines", "--max-args", "--max-procs", "--max-chars",
                    "--process-slot-var")
BASH_FIND_NAME_TESTS = ("-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename")
# 문서를 파일로 쓰는 heredoc 본문의 줄을 명령으로 읽지 않는다. 구분자는 맨 이름·따옴표·역슬래시(<<\E) 형식이 있다.
BASH_HEREDOC_RE = re.compile(r"((?<!<)<<-?[ \t]*\\?([\"']?)([\w.+-]+)\2[^\n]*)\n(?:.*?\n)??[ \t]*\3[ \t]*(?=\n|$)", re.S)
# 대입값은 판정에만 쓴다. `A=$A$A` 를 거듭해도 값이 불어나지 않게 길이와 개수를 자른다.
ASSIGN_MAX_LEN, ASSIGN_MAX_VALUES = 1024, 64
GIT_VALUE_OPTIONS = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env")
# 이 구분자에서 문장이 끝난다. 파이프·괄호·중괄호는 같은 문장이다 - 대상이 파이프 입력이면 문장 안의 경로를 본다.
STATEMENT_SEPS = (";", "\n", "\r", "&&", "||")


def bash_script(cmd):
    """판정용 Bash 명령문: heredoc 본문을 빼고 줄 잇기(`\\` + 줄바꿈)를 푼다."""
    return BASH_HEREDOC_RE.sub(r"\1\n", cmd).replace("\\\n", " ")


def _expand(tokens, assigned, fold=False):
    """변수를 대입값으로 펼친다. 값이 여럿이면(for 목록) 값마다 한 토큰이고, 모르는 변수는 그대로 둔다.
    하위 경로를 지우는 명령을 폴더 전체 삭제로 읽지 않으려는 것이다(실측: `D=<모듈>; rm "$D/임시파일"` 오탐).
    fold: PowerShell 은 변수 이름의 대소문자를 구분하지 않는다."""
    out = []
    for t in tokens:
        vals = [t]
        for name in dict.fromkeys(BASH_VAR_RE.findall(t)):
            known = assigned.get(name.lower() if fold else name)
            if known:
                pat = re.compile(r"\$\{?" + name + r"\}?(?!\w)", re.I if fold else 0)
                vals = [pat.sub(lambda _m: v, x) for x in vals for v in known][:ASSIGN_MAX_VALUES]
        out += vals
    return out


def _assign(assigned, key, values, fold=False):
    assigned[key] = [v[:ASSIGN_MAX_LEN] for v in _expand(values, assigned, fold)[:ASSIGN_MAX_VALUES]]


def _strip_redirects(rest):
    """인자에서 리다이렉션을 뺀다. 인자 사이에 와도 뒤의 인자는 그대로 본다(`rm 2>/dev/null -rf x`)."""
    out, skip = [], False
    for t in rest:
        if skip:
            skip = False
        elif BASH_REDIRECT_RE.match(t):
            skip = bool(re.fullmatch(r"[\d*]*[<>]+", t))    # `> 파일` 처럼 대상이 다음 토큰이다
        else:
            out.append(t)
    return out


def _path_args(rest):
    """옵션과 리다이렉션을 뺀 인자."""
    return [t for t in _strip_redirects(rest) if not t.startswith("-")]


def _cmd_name(tok):
    name = tok.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def _bash_head(toks, assigned):
    """앞붙이(제어 낱말·대입·export·sudo·timeout 류)를 벗긴 (명령 이름, 인자). 대입은 assigned 에 기록한다."""
    toks = list(toks)
    while toks:
        word = toks[0].lower()
        if BASH_ASSIGN_RE.match(toks[0]):
            key, val = toks.pop(0).split("=", 1)
            _assign(assigned, key, [val])
        elif word in BASH_PREFIX_WORDS:
            toks.pop(0)
        elif word in BASH_DECL_WORDS:
            toks.pop(0)
            while toks and toks[0].startswith("-"):
                toks.pop(0)
        elif word in BASH_WRAPPERS:
            toks.pop(0)
            if word == "command" and toks[:1] in (["-v"], ["-V"]):
                return "", []                               # 명령 위치 확인일 뿐 실행하지 않는다
            while toks and toks[0].startswith("-"):
                opt = toks.pop(0)
                if len(opt) == 2 and opt[1] in BASH_WRAPPERS[word] and toks:
                    toks.pop(0)
            if word == "timeout" and toks:
                toks.pop(0)                                 # 제한 시간
        else:
            break
    return (_cmd_name(toks[0]), toks[1:]) if toks else ("", [])


def _mv_paths(rest):
    """mv 인자 → (원본 목록, 목적지 목록). 목적지는 마지막 인자이거나 -t 값이다."""
    args, dest, it = [], [], iter(_strip_redirects(rest))
    for t in it:
        if t in ("-t", "--target-directory"):
            dest.append(next(it, ""))
        elif t.startswith("--target-directory="):
            dest.append(t.split("=", 1)[1])
        elif not t.startswith("-"):
            args.append(t)
    if dest or len(args) < 2:
        return args, dest
    return args[:-1], args[-1:]


def _under(base, paths):
    return [posixpath.join(base, p.replace("\\", "/")) for p in paths] if base else list(paths)


def _git_sub(rest):
    """git 뒤 인자 → (하위 명령, -C 기준 폴더, 리다이렉션을 뺀 나머지 인자). 전역 옵션(-C·-c·--no-pager 등)을 건너뛴다."""
    base, i = "", 0
    while i < len(rest) and rest[i].startswith("-"):
        if rest[i] in GIT_VALUE_OPTIONS and i + 1 < len(rest):
            if rest[i] == "-C":
                base = posixpath.join(base, rest[i + 1].replace("\\", "/"))
            i += 1
        i += 1
    return (rest[i], base, _strip_redirects(rest[i + 1:])) if i < len(rest) else ("", base, [])


def _clean_path_unsafe(path):
    """git clean -x 의 대상이 보호 폴더 밖임을 리터럴로 확인할 수 없는가."""
    t = _norm_target(path).lower()
    return (t in ("", ".") or t.startswith("..") or "$" in t or bool(GLOB_CHARS_RE.search(t))
            or "workspace" in t.split("/") or contains_repo(t))


def _git_clean_unsafe(base, args):
    """gitignore 대상까지 지우는 git clean 인가. -n(미리 보기)과 -x·-X 없는 형태는 지우지 않으므로 통과한다."""
    flags, paths, it = "", [], iter(args)
    for t in it:
        if t == "--dry-run":
            return False
        if t == "--exclude":
            next(it, None)
        elif t.startswith("--"):
            continue
        elif t.startswith("-"):
            head, has_e, tail = t[1:].partition("e")        # -e 뒤는 제외 패턴이지 옵션이 아니다
            flags += head
            if has_e and not tail:
                next(it, None)
        else:
            paths.append(t)
    if "n" in flags or not re.search(r"[xX]", flags):
        return False
    return any(_clean_path_unsafe(p) for p in _under(base, paths) or [base or "."])


def _git_effects(rest):
    """git 명령의 (지우는 경로, 옮길 목적지, 위험한 clean 인가). `git rm --cached` 는 작업 트리를 건드리지 않아 대상이 아니다."""
    sub, base, args = _git_sub(rest)
    if sub == "rm" and "--cached" not in args:
        return _under(base, _path_args(args)), [], False
    if sub == "mv":
        src, dest = _mv_paths(args)
        return _under(base, src), _under(base, dest), False
    return [], [], sub == "clean" and _git_clean_unsafe(base, args)


def _xargs_command(rest):
    """xargs 가 실행하는 (명령 이름, 인자). 옵션과 그 값을 건너뛴 첫 명령 낱말이다. 없으면 ("", [])."""
    rest, i = _strip_redirects(rest), 0
    while i < len(rest) and rest[i].startswith("-"):
        takes_value = rest[i] in XARGS_VALUE_LONG or XARGS_VALUE_SHORT_RE.fullmatch(rest[i])
        i += 2 if takes_value else 1
        if rest[i - 1:i] == ["--"]:
            break
    return _bash_head(rest[i:], {})


def _git_takes_input(rest):
    """파이프 입력을 경로로 받아 지우거나 옮기는 git 명령인가. `git rm --cached` 는 작업 트리를 건드리지 않는다."""
    sub, _base, args = _git_sub(rest)
    return sub == "mv" or (sub == "rm" and "--cached" not in args)


def _find_targets(rest):
    """find 인자 → 지우는 시작 경로들. 저장소 안을 도는 find 의 이름 조건(-name·-path)이 보호 이름에 맞으면 보호 폴더도 넣는다.
    `! -name specs`·`-name specs -prune` 은 보호 폴더를 빼는 조건이다."""
    rest = list(itertools.dropwhile(lambda t: t in ("-H", "-L", "-P"), rest))
    starts = list(itertools.takewhile(lambda t: not t.startswith("-") and t != "!", rest))
    norm = [_norm_target(s).lower() for s in starts] or ["."]
    if not any(t in (".", "..") or "workspace" in t.split("/") or contains_repo(t) for t in norm):
        return starts
    for i, (test, value) in enumerate(zip(rest, rest[1:])):
        if test.lower() not in BASH_FIND_NAME_TESTS:
            continue
        if rest[i - 1:i] in (["!"], ["-not"]) or rest[i + 2:i + 3] == ["-prune"]:
            continue
        if any(_seg_matches(seg, PROTECTED_LEAF_NAMES + WORKSPACE_NAMES) for seg in value.replace("\\", "/").split("/")):
            return starts + ["workspace"]
    return starts


def bash_removals(cmd):
    """Bash 명령이 지우거나 옮기는 대상 (Removals).

    따옴표 안 문구(`echo 'rm -rf …'`·`--title '…'`)는 인자 하나로 남아 명령으로 읽히지 않는다.
    대상이 파이프 입력이면(`ls <폴더> | xargs rm`) 같은 문장의 경로를 대상으로 본다."""
    gone, into, assigned, stmt = [], [], {}, []
    dynamic = piped = clean = False

    def add(tokens, where=None):
        (gone if where is None else where).extend(_expand(tokens, assigned))

    for toks, sep in _ps_split(bash_script(cmd)):
        name, rest = "", []
        if toks[:1] and toks[0].lower() == "for" and toks[2:3] == ["in"]:
            _assign(assigned, toks[1], toks[3:])
        else:
            name, rest = _bash_head(toks, assigned)
        if name:
            stmt.append((name, rest))
        if name == "xargs":
            x_name, x_rest = _xargs_command(rest)
            piped = piped or x_name in BASH_REMOVERS or (x_name == "git" and _git_takes_input(x_rest))
            if x_name == "git":
                name, rest = x_name, x_rest
        if name == "git":
            g_gone, g_into, g_clean = _git_effects(rest)
            add(g_gone)
            add(g_into, into)
            clean = clean or g_clean
        elif name == "find":
            executes = any(a in ("-exec", "-execdir", "-ok", "-okdir") and _cmd_name(b) in BASH_REMOVERS
                           for a, b in zip(rest, rest[1:]))
            if "-delete" in rest or executes:
                add(_find_targets(rest))
        elif name == "mv":
            src, dest = _mv_paths(rest)
            piped = piped or not src                # `xargs -I {} mv {} /x` 는 {} 에서 구간이 나뉜다
            add(src)
            add(dest, into)
        elif name in BASH_REMOVERS:
            args = _path_args(rest)
            piped = piped or not args
            add(args)
        if sep in STATEMENT_SEPS:
            if piped:
                dynamic = True
                for nm, rs in stmt:
                    add(_find_targets(rs) if nm == "find" else _path_args(rs))
            stmt, piped = [], False
    if piped:
        dynamic = True
        for nm, rs in stmt:
            add(_find_targets(rs) if nm == "find" else _path_args(rs))
    return Removals(gone, dynamic, into, clean)


def check_protected_removal_bash(ti):
    cmd = ti.get("command") or ""
    check_protected_removal("Bash", bash_removals(cmd), bash_script(cmd))


PS_DOTNET_REMOVE_RE = re.compile(r"\[(?:System\.)?IO\.(?:File|Directory)\]::(?:Delete|Move)\s*\(([^)]*)\)", re.I)
PS_ASSIGN_RE = re.compile(r"^\$([\w:]+)=(.*)$", re.S)


def _ps_assign(seg):
    """대입 구간이면 (소문자 변수 이름, 값 토큰들). `$d='x'`·`$d = 'x'`·`$d = Join-Path a b` 를 받는다."""
    if not seg or not seg[0].startswith("$"):
        return None
    m = PS_ASSIGN_RE.match(seg[0])
    if m:
        return m.group(1).lower(), ([m.group(2)] if m.group(2) else []) + seg[1:]
    if len(seg) > 1 and seg[1].startswith("=") and not seg[1].startswith("=="):
        return seg[0][1:].lower(), ([seg[1][1:]] if len(seg[1]) > 1 else []) + seg[2:]
    return None


def _ps_list(tokens):
    """쉼표 목록(`a,workspace`·`'a','b'`)을 나눈다. 값이 없는 빈 토큰은 그대로 둔다 - 식·파이프 입력 표시다."""
    return [p for t in tokens for p in t.split(",") if p or not t]


def ps_removals(cmd):
    """PowerShell 명령이 지우거나 옮기는 원본 경로 (Removals). 변수는 같은 명령의 대입값으로 펼치고, 대상이 리터럴이
    아니면(파이프 입력·식·모르는 변수) 같은 문장의 경로를 대상으로 본다."""
    gone, into, assigned, stmt = [], [], {}, []
    dynamic = open_ended = clean = False

    def flush():
        gone.extend(_ps_list(_expand(_path_args(stmt), assigned, fold=True)))

    for seg, sep in _ps_split(cmd):
        stmt += seg
        hit = _ps_assign(seg)
        if hit:
            _assign(assigned, hit[0], hit[1], fold=True)
        if seg and _cmd_name(seg[0]) == "git":
            g_gone, g_into, g_clean = _git_effects(seg[1:])
            gone.extend(g_gone)
            into.extend(g_into)
            clean = clean or g_clean
        for k, tok in enumerate(seg):
            if k > 0 and seg[k - 1] != "=":
                continue
            canon = _ps_cmdlet(tok)
            if canon not in ("remove-item", "move-item", "rename-item"):
                continue
            _al, path_params, _rule, value_params = PS_WRITE_CMDLETS[canon]
            named, pos = _ps_args(seg[k + 1:], path_params, value_params)
            src = [v for p in ("path", "literalpath", "pspath") for v in named.get(p, [])]
            found = src + pos if canon == "remove-item" else (src or pos[:1])
            open_ended = open_ended or not found
            for t in _ps_list(_expand(found, assigned, fold=True)):
                if not t or t.startswith(("$", "@")) or "$(" in t:
                    open_ended = True
                if t:
                    gone.append(t)
            break
        if sep in STATEMENT_SEPS:
            if open_ended:
                dynamic = True
                flush()
            stmt, open_ended = [], False
    if open_ended:
        dynamic = True
        flush()
    for m in PS_DOTNET_REMOVE_RE.finditer(cmd):
        lits = re.findall(r"[\"']([^\"']+)[\"']", m.group(1))
        if lits:
            gone.append(lits[0])
        else:
            dynamic = True
    return Removals(gone, dynamic, into, clean)


def check_powershell(ti):
    cmd = ti.get("command") or ""
    check_human_only_bash(ti)
    check_git_hook_bypass(ti)
    targets, dynamic = ps_writes(cmd)
    bare = ps_unquoted(cmd)
    low = cmd.lower().replace("\\", "/")
    state_msg = ("[게이트] PowerShell 로 state.yaml 을 직접 쓰거나 지우면 완료 전환 게이트 검사를 우회한다.\n"
                 "상태 값은 python tools/state.py set --stage N [--slice id] [--unit u] --value <값> 으로 고친다\n"
                 "(done 은 gate.py check 통과 시에만 기록, blocked 는 --reason 필수, 변경 이력 자동 기록).\n"
                 "구조 변경은 Edit 도구로 한다.")
    # (1) state.yaml - 리터럴 대상, 대상이 리터럴이 아닌데 이름이 보이는 경우, python·sed 쓰기
    if any(os.path.basename(t).lower() == STATE_BASENAME for t in targets):
        deny(state_msg)
    if dynamic and STATE_BASENAME in low:
        deny(state_msg + "\n(쓰기 대상이 변수·식이라 판정할 수 없어 명령에 state.yaml 이 보이면 막는다 - 대상 경로를 리터럴로 쓰거나 state.py 를 쓴다)")
    if STATE_BASENAME in low:
        py_write = PY_OPEN_STATE_RE.search(cmd) and PY_WRITE_RE.search(cmd)
        if py_write or BASH_STATE_WRITES[2].search(bare):       # python 쓰기 · sed/perl -i (따옴표 밖)
            deny(state_msg)
    # (2) 잠금 매니페스트·기준 이미지 승인 기록
    if any(PROTECTED_DIR_RE.search(_norm_target(t)) for t in targets) or (dynamic and PROTECTED_DIR_RE.search(low)):
        deny("[잠금] 잠금 매니페스트·기준 이미지 승인 기록은 spec_lock.py·visual.py 로만 바뀐다 (PowerShell 직접 쓰기 금지).")
    check_protected_removal("PowerShell", ps_removals(cmd), cmd)
    # (3) 잠긴 기대 동작 테스트
    if not (targets or dynamic or SPEC_ARG_WRITE_RE.search(bare)):
        return
    locked = locked_files()
    for sl, rels in locked.items():
        for r in rels:
            if any(path_refers_to_locked(t, r) for t in targets) or (
                    (dynamic or SPEC_ARG_WRITE_RE.search(bare)) and cmd_refers_to_locked(cmd.replace("\\", "/"), r)):
                deny(f"[잠금] PowerShell 명령이 {sl} 의 잠긴 기대 동작 테스트({r})를 바꿀 수 있다. "
                     "잠긴 테스트는 고치지 않는다.")


def pre_tool_use(data):
    tool = data.get("tool_name") or ""
    ti = data.get("tool_input") or {}
    if not isinstance(ti, dict):
        return
    check_emoji(tool, ti)
    if tool in HANDBACK_TOOLS:
        check_handback(data)
        return
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        check_deny_words(tool, ti)
    if tool == "PowerShell":
        check_powershell(ti)
    elif tool == "Bash":
        check_human_only_bash(ti)
        check_git_hook_bypass(ti)
        check_bash_state(ti)
        check_protected_removal_bash(ti)
        check_locked_spec_bash(ti)
    elif tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        check_locked_spec_write(tool, ti)
        if tool != "NotebookEdit":
            check_state(tool, ti)
            check_contract_approval(tool, ti)


# ---------------------------------------------------------------- 4) 긴 Bash 출력 축약 (PostToolUse)
COMPACT_DEFAULT = 6000          # 이 글자 수를 넘는 Bash 출력만 축약한다
REPORT_PROSE_DEFAULT = 3000     # 서브에이전트 보고에서 결과 블록 밖 산문의 상한
LOG_KEEP = 400                  # 보관할 로그 파일 수 (오래된 것부터 지운다)
FULL_OUTPUT_MARK = "PA_FULL_OUTPUT=1"
# 오류·실패·결과 요약 줄 (Maven·Gradle·JUnit·npm·pnpm·vitest·Playwright·tsc·pytest·일반)
KEY_LINE_RE = re.compile(
    r"(\[ERROR\]|\bERROR\b|\bFAIL(?:ED|URE|S)?\b|\bfailed\b|\bfailing\b|\bError:|\berror\b(?: TS\d+)?:|"
    r"Exception\b|Caused by|AssertionError|Assertion|expected|Expected|"
    r"Tests run:|Tests:|Test Files|Test Suites:|\d+ (?:passed|failed|skipped)|BUILD (?:SUCCESS|FAILURE|FAILED)|"
    r"npm ERR!|ELIFECYCLE|Traceback|SyntaxError|cannot find symbol|COMPILATION ERROR|exit code|Exit code|"
    r"\u2713|\u2717|\u2718|\u00d7)")
STACK_LINE_RE = re.compile(r"^\s+at |^\s+\.\.\. \d+ more|^\s*at [\w$.]+\(")


def token_cfg():
    try:
        from _common import config
        return ((config().get("pipeline") or {}).get("token") or {})
    except Exception:
        return {}


def log_dir():
    try:
        from _common import config, workspace
        if (config().get("project") or {}).get("name"):
            return os.path.join(workspace(), "logs", "bash")
    except Exception:
        pass
    return os.path.join(ROOT, "workspace", "_bash-logs")   # workspace/*/ 는 .gitignore 대상


def save_log(text, cmd):
    import hashlib
    import time
    d = log_dir()
    os.makedirs(d, exist_ok=True)
    name = time.strftime("%y%m%d%H%M%S") + "_" + hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:8] + ".log"
    path = os.path.join(d, name)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("$ " + (cmd or "") + "\n\n" + text)
    try:
        logs = sorted(glob.glob(os.path.join(d, "*.log")))
        for old in logs[:-LOG_KEEP]:
            os.remove(old)
    except OSError:
        pass
    return path


def compact_output(text, limit, path):
    """앞 15줄 + 핵심 줄(오류·실패·결과 요약, 스택은 블록당 3줄) + 끝 40줄. 결과는 대략 limit 안팎."""
    lines = text.split("\n")
    head, tail = lines[:15], lines[-40:] if len(lines) > 55 else []
    body = lines[15:len(lines) - len(tail)]
    keys, stack_run, last = [], 0, -2
    for i, ln in enumerate(body):
        if STACK_LINE_RE.search(ln):
            stack_run += 1
            if stack_run <= 3 and last == i - 1:
                keys.append(ln[:300])
                last = i
            continue
        stack_run = 0
        if KEY_LINE_RE.search(ln):
            if last < i - 1 and keys:
                keys.append("  ...")
            keys.append(ln[:400])
            last = i
    budget = max(40, limit // 80)
    if len(keys) > budget:
        keys = keys[:budget // 2] + [f"  ... (핵심 줄 {len(keys) - budget}개 생략 — 로그 파일 참고)"] + keys[-budget // 2:]
    out = [f"[출력 축약] 원본 {len(text):,}자·{len(lines):,}줄 → 앞부분·오류·실패·결과 요약 줄·끝부분만 보인다 (pipeline-core §26).",
           f"전체 로그: {path}",
           "더 필요하면 그 파일을 Grep 하거나 Read 의 offset·limit 로 필요한 부분만 본다. 전체가 꼭 필요하면 명령에 PA_FULL_OUTPUT=1 을 붙인다.",
           "---- 앞 15줄 ----"] + head
    if keys:
        out += ["---- 핵심 줄 ----"] + keys
    if tail:
        out += ["---- 끝 40줄 ----"] + tail
    return "\n".join(out)


def post_tool_use(data):
    if (data.get("tool_name") or "") != "Bash":
        return None
    cmd = ((data.get("tool_input") or {}).get("command") or "")
    if FULL_OUTPUT_MARK in cmd:
        return None
    resp = data.get("tool_response")
    if not isinstance(resp, dict) or resp.get("isImage"):
        return None
    out, err = resp.get("stdout") or "", resp.get("stderr") or ""
    if not isinstance(out, str) or not isinstance(err, str):
        return None
    cfg = token_cfg()
    limit = cfg.get("bash_compact_chars", COMPACT_DEFAULT)
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = COMPACT_DEFAULT
    text = out + (("\n[stderr]\n" + err) if err else "")
    if limit <= 0 or len(text) <= limit:
        return None
    path = save_log(text, cmd)
    new = dict(resp)
    new["stdout"] = compact_output(text, limit, path)
    new["stderr"] = ""
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": new}}


def pipeline_agents():
    return {os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(ROOT, ".claude", "agents", "*.md"))}


# 머리는 "```json pa-agent-result" 와 json 표기가 없는 "```pa-agent-result" 둘 다 받는다
# (§12 는 앞의 형식을 정하지만, 실측 보고에 뒤의 형식도 섞여 와서 "블록 없음" 으로 막혔다).
RESULT_BLOCK_RE = re.compile(r"```(?:json[ \t]+)?pa-agent-result[ \t]*\r?\n(.*?)```", re.S)
REQUIRED_KEYS = ("schema", "agent", "result", "gates", "changed_files", "not_executed")
# 서브에이전트가 보고를 메시지 인계 도구로 넘기는 경우의 도구 이름. 보고 본문은 그 도구 입력의 message 에만 있다.
HANDBACK_TOOLS = ("SubagentHandback",)
RESULT_COMPARE_SECONDS = 600    # 같은 보고의 이중 저장을 비교하는 시간 창(실측 인계 간격은 2초)


def _transcript_records(path):
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def last_message_from_transcript(path):
    for rec in reversed(_transcript_records(path)):
        if rec.get("type") != "assistant":
            continue
        content = (rec.get("message") or {}).get("content")
        if isinstance(content, str):
            return content
        texts = [c.get("text", "") for c in content or [] if isinstance(c, dict) and c.get("type") == "text"]
        if texts:
            return "\n".join(texts)
    return None


def handback_message_from_transcript(path):
    """transcript 에서 마지막 인계 도구 호출(SubagentHandback)의 message. 없으면 None.

    실측(2026-10-30): 보고를 인계 도구로 넘긴 서브에이전트는 보고 본문이 도구 입력에만 있고,
    마지막 텍스트 메시지는 "검증이 끝났다" 같은 한 줄이다. 텍스트만 보면 결과 블록을 찾지 못한다."""
    for rec in reversed(_transcript_records(path)):
        if rec.get("type") != "assistant":
            continue
        content = (rec.get("message") or {}).get("content")
        for c in reversed(content if isinstance(content, list) else []):
            if (isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") in HANDBACK_TOOLS
                    and isinstance((c.get("input") or {}).get("message"), str)):
                return c["input"]["message"]
    return None


def report_message(data):
    """SubagentStop 입력에서 보고 본문을 고른다. 인계 도구로 넘긴 보고가 있으면 그것이 보고다."""
    tp = data.get("agent_transcript_path") or ""
    handback = handback_message_from_transcript(tp) if tp else None
    msg = data.get("last_assistant_message")
    if handback is not None and (not isinstance(msg, str) or not RESULT_BLOCK_RE.search(msg)):
        return handback
    if msg is None and tp:
        msg = last_message_from_transcript(tp)
    return msg


def subagent_stop(data):
    if data.get("stop_hook_active"):
        return   # 이미 한 번 막아 보완 중이면 무한 반복을 피한다
    agent = data.get("agent_type") or ""
    if agent not in pipeline_agents():
        return
    msg = report_message(data)
    if msg is None:
        return   # 판단할 근거가 없으면 막지 않는다
    check_report(agent, msg)


def check_handback(data):
    """PreToolUse(SubagentHandback) - 인계 도구로 넘기는 보고를 넘기기 전에 같은 결과 계약으로 본다.

    인계로 끝나는 실행은 SubagentStop 이 보고를 보지 못하거나 돌지 않을 수 있다(실측: 10-30 의 인계 보고
    결과 블록이 한 건도 저장되지 않았다). 도구 호출 시점에는 보고 본문이 tool_input.message 에 확실히 있다.
    막는 것: 블록 결손·깨진 JSON·필수 키 누락·배열 형식·이모지. 산문 상한은 경고만 내고 저장한다.
    에이전트 유형을 모르면(훅 입력에 agent_type 이 없으면) 블록의 agent 값으로 판단하고, 그것도 없으면 막지 않는다
    (블록이 아예 없는 인계는 이때 SubagentStop 이 2차로 본다)."""
    ti = data.get("tool_input") or {}
    msg = ti.get("message") if isinstance(ti, dict) else None
    if not isinstance(msg, str):
        return
    agent = data.get("agent_type") or ""
    if not agent:
        m = RESULT_BLOCK_RE.search(msg)
        try:
            agent = str((json.loads(m.group(1)) if m else {}).get("agent") or "")
        except (json.JSONDecodeError, AttributeError):
            agent = ""
    if agent not in pipeline_agents():
        return
    check_report(agent, msg, prose_blocks=False)


def check_report(agent, msg, prose_blocks=True):
    """보고 본문을 결과 계약(§12)으로 판정한다. 막히면 종료 코드 2, 받아들이면 결과 블록을 저장한다.

    prose_blocks=False(인계 시점): 산문 상한은 막지 않고 경고만 낸다. 블록 결함은 넘기기 전에 고치는 것이 가장 싸지만,
    산문 상한은 문맥 비용 문제라 인계를 막아 재시도를 부를 만큼 급하지 않다(검토 추천안, 실측 인계 38건 중 초과 0건)."""
    problems, warns = [], []
    hits = find_emoji(msg)
    if hits:
        problems.append("보고에 이모지가 있다: " + ", ".join(cp for _n, _c, _ch, cp in hits[:5]) + " — 텍스트로 바꾼다")
    m = RESULT_BLOCK_RE.search(msg)
    block = {}
    prose = RESULT_BLOCK_RE.sub("", msg).strip()
    try:
        prose_limit = int(token_cfg().get("report_prose_chars", REPORT_PROSE_DEFAULT))
    except (TypeError, ValueError):
        prose_limit = REPORT_PROSE_DEFAULT
    if prose_limit > 0 and len(prose) > prose_limit:
        (problems if prose_blocks else warns).append(f"보고 산문이 {len(prose):,}자로 상한({prose_limit:,}자)을 넘는다 — 표·목록·상세는 레포트 파일에 쓰고, "
                        "보고에는 요약과 레포트 경로(pa-agent-result.report_file)만 둔다 (pipeline-core §12·§26)")
    if not m:
        problems.append("보고 끝에 ```json pa-agent-result``` 블록이 없다 (pipeline-core §12)")
    else:
        try:
            block = json.loads(m.group(1))
            missing = [k for k in REQUIRED_KEYS if k not in block]
            if missing:
                problems.append("pa-agent-result 에 필수 키가 없다: " + ", ".join(missing))
            for k in ("gates", "changed_files", "not_executed"):
                if k in block and not isinstance(block[k], list):
                    problems.append(f"pa-agent-result.{k} 는 배열이어야 한다")
        except json.JSONDecodeError as ex:
            problems.append(f"pa-agent-result JSON 파싱 실패: {ex.msg} (line {ex.lineno})")
    if problems:
        deny(f"[결과 계약] {agent} 의 보고를 받을 수 없다.\n- " + "\n- ".join(problems)
             + "\n보고를 보완해 다시 끝낸다. 실행하지 못한 검증은 not_executed 에 이유와 함께 적는다.")
    for w in warns:
        sys.stderr.write(f"[결과 계약 경고] {agent}: {w}\n")
    save_run(agent, block)


def _mtime(path):
    """파일 수정 시각. 사라진 파일·깨진 링크는 0 - 정렬 중 예외로 이번 블록을 버리지 않는다."""
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def save_run(agent, block):
    """받아들인 결과 블록을 workspace/<project>/reports/agent-results/ 에 저장한다 — 에이전트가 같은 JSON 을
    한 번 더 쓰지 않아도 오케스트레이터가 `tools/ingest_result.py --json <파일>` 로 바로 옮긴다 (pipeline-core §12·§26).
    실패해도 막지 않는다."""
    try:
        import time
        from _common import workspace
        d = os.path.join(workspace(), "reports", "agent-results")
        os.makedirs(d, exist_ok=True)
        parts = [time.strftime("%y%m%d%H%M%S"), agent, str(block.get("stage", "")), str(block.get("slice") or "all")]
        if block.get("unit"):
            parts.append(str(block["unit"]))
        name = "_".join(re.sub(r"[^\w.-]", "-", x) for x in parts)
        path = os.path.join(d, name + ".json")
        # 같은 보고가 두 번 들어오면(인계 도구 PreToolUse 와 SubagentStop 이 둘 다 도는 경우) 한 번만 남긴다
        saved = dict(block, agent=block.get("agent") or agent)
        # 비교 창은 수정 시각 순이어야 한다. 이름순이면 손으로 지은 stage*.json 이 시각 접두 파일 뒤에 놓여
        # 창을 다 차지하고, 방금 저장한 파일이 창에 들어오지 못해 같은 보고가 두 파일로 남는다(실측).
        # 최근 파일로 제한한다 - 며칠 뒤의 정당한 재실행은 블록이 글자까지 같아도 그 실행의 파일이 있어야 한다.
        now = time.time()
        for stamp, old in sorted((_mtime(p), p) for p in glob.glob(os.path.join(d, "*.json")))[-30:]:
            if now - stamp > RESULT_COMPARE_SECONDS:
                continue
            try:
                with open(old, encoding="utf-8") as fh:
                    if json.load(fh) == saved:
                        return
            except (OSError, ValueError):
                continue
        n = 1
        while os.path.exists(path):
            n += 1
            path = os.path.join(d, f"{name}-{n}.json")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(saved, f, ensure_ascii=False, indent=2)
    except Exception as ex:
        sys.stderr.write(f"[guard] 결과 블록 저장 실패(차단하지 않음): {ex}\n")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        # 훅 입력은 UTF-8 이다. sys.stdin 은 OS 기본 인코딩(Windows 한국어 = cp949)으로 읽으므로
        # 한글이 깨져 YAML 파싱·이모지 판정이 틀어진다 — 바이트로 받아 직접 디코딩한다.
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (json.JSONDecodeError, ValueError):
        return 0
    try:
        if mode == "pre-tool-use":
            pre_tool_use(data)
        elif mode == "post-tool-use":
            res = post_tool_use(data)
            if res:
                sys.stdout.write(json.dumps(res, ensure_ascii=False))
        elif mode == "subagent-stop":
            subagent_stop(data)
    except SystemExit:
        raise
    except Exception as ex:   # 훅 자체 결함으로 작업이 멈추지 않게 한다
        sys.stderr.write(f"[guard] 훅 내부 오류(차단하지 않음): {ex}\n")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
