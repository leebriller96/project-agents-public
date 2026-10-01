#!/usr/bin/env python3
# guard.py — Claude Code 훅: 파이프라인 원칙을 "지침" 이 아니라 도구 호출 시점에 강제한다.
#
# 등록: .claude/settings.json 의 hooks (PreToolUse · SubagentStop)
#   python tools/hooks/guard.py pre-tool-use     # stdin: 훅 입력 JSON
#   python tools/hooks/guard.py subagent-stop
#
# 강제하는 것
#   1) 이모지 금지 — Write·Edit·MultiEdit·NotebookEdit 의 새 내용, Bash 명령 문자열에 이모지가 있으면 차단.
#      대상 파일을 가리지 않는다(생성 소스·Mapper·yml·DDL·레포트·지침 전부). 예외 없음.
#   2) 게이트 없는 완료 기록 금지 — workspace/<project>/state.yaml 에서 어떤 단계·slice 가 done 으로 바뀌면
#      그 단계 레포트로 `gate.py check` 를 돌려 FAIL 이면 쓰기를 막는다. Bash 로 state.yaml 을 고치는 것은
#      이 검사를 우회하므로 막고 Edit/Write 를 쓰게 한다.
#   3) 결과 블록 없는 서브에이전트 종료 금지 — 파이프라인 에이전트(.claude/agents/*.md)가 pa-agent-result 블록
#      (pipeline-core §12) 없이, 또는 이모지를 넣은 채 끝내려 하면 종료를 막고 보완을 요구한다.
#
# 종료 코드: 0 허용 · 2 차단(stderr 가 Claude 에게 전달된다)
# 훅 자체의 예기치 않은 오류는 차단하지 않는다(도구 사용이 멈추는 것을 막기 위해). 게이트·selfcheck·CI 가 2차 방어선이다.

import glob
import json
import os
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
             + "\n레포트·pa-meta 를 고쳐 gate 를 통과시키거나, 상태를 blocked 로 기록한다.")


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
    if any(r.search(cmd) for r in BASH_STATE_WRITES) or py_write:
        deny("[게이트] Bash 로 state.yaml 을 고치면 완료 전환 게이트 검사를 우회한다.\n"
             "state.yaml 은 Edit/Write 도구로 고친다 (RR 집계는 python tools/rr.py stats --write).")


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


def check_human_only_bash(ti):
    cmd = ti.get("command") or ""
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
    if new.get("approved") is True and old.get("approved") is not True:
        deny("[사람 전용] 공통 계약의 approved 를 에이전트가 바꿀 수 없다.\n"
             "사람이 직접: ! python tools/common_contract.py approve --by <이름>")


SPEC_BASH_WRITE_RE = re.compile(r"(\bsed\b[^|;&\n]*\s-i|>|\btee\b|\bmv\b|\brm\b|\bcp\b|\bperl\b[^|;&\n]*\s-i|"
                                r"\bgit\s+(?:checkout|restore|stash)\b|open\([^)]*[\"'][wa]\+?[\"']|write_text|\btruncate\b)")


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
    if not SPEC_BASH_WRITE_RE.search(cmd):
        return
    import spec_lock
    for sl, m in spec_lock.all_manifests().items():
        for r in m.get("files") or {}:
            if r in cmd or os.path.basename(r) in cmd:
                deny(f"[잠금] Bash 명령이 {sl} 의 잠긴 기대 동작 테스트({r})를 바꿀 수 있다. 잠긴 테스트는 고치지 않는다.")


def pre_tool_use(data):
    tool = data.get("tool_name") or ""
    ti = data.get("tool_input") or {}
    if not isinstance(ti, dict):
        return
    check_emoji(tool, ti)
    if tool == "Bash":
        check_human_only_bash(ti)
        check_bash_state(ti)
        check_locked_spec_bash(ti)
    elif tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        check_locked_spec_write(tool, ti)
        if tool != "NotebookEdit":
            check_state(tool, ti)
            check_contract_approval(tool, ti)


def pipeline_agents():
    return {os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(ROOT, ".claude", "agents", "*.md"))}


RESULT_BLOCK_RE = re.compile(r"```json\s+pa-agent-result\s*\n(.*?)```", re.S)
REQUIRED_KEYS = ("schema", "agent", "result", "gates", "changed_files", "not_executed")


def last_message_from_transcript(path):
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("type") != "assistant":
            continue
        content = (rec.get("message") or {}).get("content")
        if isinstance(content, str):
            return content
        texts = [c.get("text", "") for c in content or [] if isinstance(c, dict) and c.get("type") == "text"]
        if texts:
            return "\n".join(texts)
    return None


def subagent_stop(data):
    if data.get("stop_hook_active"):
        return   # 이미 한 번 막아 보완 중이면 무한 반복을 피한다
    agent = data.get("agent_type") or ""
    if agent not in pipeline_agents():
        return
    msg = data.get("last_assistant_message")
    if msg is None and data.get("agent_transcript_path"):
        msg = last_message_from_transcript(data["agent_transcript_path"])
    if msg is None:
        return   # 판단할 근거가 없으면 막지 않는다
    problems = []
    hits = find_emoji(msg)
    if hits:
        problems.append("보고에 이모지가 있다: " + ", ".join(cp for _n, _c, _ch, cp in hits[:5]) + " — 텍스트로 바꾼다")
    m = RESULT_BLOCK_RE.search(msg)
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
