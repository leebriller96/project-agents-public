# tools/state.py — state.yaml 을 도구로만 고치고 done 은 게이트를 통과할 때만 기록하는지
import json
import os
import sys

import pytest

from conftest import REPO, dev_meta

sys.path.insert(0, os.path.join(REPO, "tools"))

import state  # noqa: E402

CHECK = chr(0x2705)   # 이모지 문자는 코드로만 만든다

STATE = """# 파이프라인 상태 (주석은 보존된다)
project: demo
iteration: 1
updated_at: 2026-01-01 09:00     # KST

stages:
  stage0_ingest: done
  stage3_common: pending         # 단계 전체 값
  stage5_integration: pending

slices:
  notice:
    stage2_backend: in_progress
    stage4_frontend: pending
    stage5_integration: pending
    blocked_reason: null
  board:
    stage2_backend: done
    stage4_frontend: pending
    stage5_integration: pending
    blocked_reason: hold - 다른 사유
  claim:
    stage2_backend: in_progress
    stage4_frontend: pending
    stage5_integration: pending
    units:
      core: {stage2_backend: done, stage4_frontend: pending}
      intake:
        stage2_backend: pending
        stage4_frontend: pending

log:
- at: 2026-01-01 09:00
  stage: stage0_ingest
  slice: null
  result: done
  note: 시작 - 이어지는 줄이
    있는 메모
"""


def _file(tmp_path, text=STATE):
    p = tmp_path / "state.yaml"
    p.write_text(text, encoding="utf-8", newline="\n")
    return str(p)


def _read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _history(path):
    hp = os.path.join(os.path.dirname(path), "state-history.jsonl")
    if not os.path.exists(hp):
        return []
    with open(hp, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def _block(text, sid):
    """slices.<sid> 블록 줄들."""
    lines = text.split("\n")
    start = lines.index(f"  {sid}:")
    out = [lines[start]]
    for ln in lines[start + 1:]:
        if ln.startswith("    ") or not ln.strip():
            out.append(ln)
        else:
            break
    return out


@pytest.fixture(autouse=True)
def _no_state_env(monkeypatch):
    """실행 환경의 state 경로 변수를 끊는다 - 남아 있으면 sandbox 밖 파일에 쓸 수 있다(자식 프로세스도 상속)."""
    monkeypatch.delenv("PA_STATE_FILE", raising=False)
    monkeypatch.delenv(state.STATE_PATH_ENV, raising=False)


@pytest.fixture
def fake_gate(monkeypatch):
    calls = []

    def run(rc):
        def _g(stage, sl, unit, text, report=None):
            calls.append((stage, sl, unit, text))
            return rc, ["레포트 2601010900_stage2_notice_backend.md"] + ([] if rc == 0 else ["gate-proof: test_count 0"])
        monkeypatch.setattr(state, "run_gate", _g)
        return calls
    return run


def _sandbox_state(sandbox):
    os.makedirs(sandbox.ws, exist_ok=True)
    path = os.path.join(sandbox.ws, "state.yaml")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(STATE)
    return path


# ---------------------------------------------------------------- done 은 게이트로

def test_done_rejected_when_gate_fails_and_file_unchanged(tmp_path, fake_gate, capsys):
    path = _file(tmp_path)
    calls = fake_gate(1)
    rc = state.main(["--file", path, "set", "--stage", "2", "--slice", "notice", "--value", "done"])
    assert rc == 1
    assert calls and calls[0][:3] == (2, "notice", None)
    assert _read(path) == STATE
    assert _history(path) == []
    assert "차단(FAIL)" in capsys.readouterr().err


def test_done_recorded_when_gate_passes_and_judged_on_new_state(tmp_path, fake_gate):
    path = _file(tmp_path)
    calls = fake_gate(0)
    rc = state.main(["--file", path, "set", "--stage", "2", "--slice", "notice", "--value", "done"])
    assert rc == 0
    assert "  notice:\n    stage2_backend: done\n" in _read(path)
    # 게이트는 기록하려는 새 state 로 판정한다 (guard.py 와 같은 방식)
    assert "  notice:\n    stage2_backend: done\n" in calls[0][3]
    h = _history(path)
    assert h[-1]["key"] == "slices.notice.stage2_backend"
    assert h[-1]["from"] == "in_progress" and h[-1]["to"] == "done"
    assert "통과" in h[-1]["gate"]


def test_stage_level_and_pseudo_slice_and_unit_gate_arguments(tmp_path, fake_gate):
    path = _file(tmp_path, STATE.replace("  stage0_ingest: done\n", "  stage0_ingest: done\n  stage2_common_port: pending\n"))
    calls = fake_gate(0)
    assert state.main(["--file", path, "set", "--stage", "3", "--value", "done"]) == 0
    assert state.main(["--file", path, "set", "--stage", "2", "--slice", "common-port", "--value", "done"]) == 0
    assert state.main(["--file", path, "set", "--stage", "4", "--slice", "claim", "--unit", "core", "--value", "done"]) == 0
    assert [c[:3] for c in calls] == [(3, None, None), (2, "common-port", None), (4, "claim", "core")]
    text = _read(path)
    assert "  stage3_common: done         # 단계 전체 값\n" in text      # 줄 끝 주석 보존
    assert "  stage2_common_port: done\n" in text
    assert "      core: {stage2_backend: done, stage4_frontend: done}\n" in text


def test_real_gate_without_report_rejects_done(sandbox):
    """가짜가 아닌 gate.py 로도 거부되는지 (레포트 없음 -> FAIL)."""
    path = _sandbox_state(sandbox)
    p = sandbox.run("state.py", "set", "--stage", "2", "--slice", "notice", "--value", "done")
    assert p.returncode == 1, p.stdout + p.stderr
    assert _read(path) == STATE


def test_real_gate_with_passing_report_records_done(sandbox):
    path = _sandbox_state(sandbox)
    sandbox.write_report("2609281100_stage2_notice_backend.md", dev_meta())
    p = sandbox.run("state.py", "set", "--stage", "2", "--slice", "notice", "--value", "done")
    assert p.returncode == 0, p.stdout + p.stderr
    assert "  notice:\n    stage2_backend: done\n" in _read(path)


def test_finalize_next_hint_is_a_command_state_tool_accepts(sandbox):
    path = _sandbox_state(sandbox)
    sandbox.write_report("2609281100_stage2_notice_backend.md", dev_meta())
    p = sandbox.run("gate.py", "finalize", "--stage", "2", "--slice", "notice")
    hint = [ln for ln in p.stdout.splitlines() if ln.startswith("다음: ")]
    assert hint and "python tools/state.py set --stage 2 --slice notice --value done" in hint[0], p.stdout
    cmd = hint[0][len("다음: python tools/"):].split("  (")[0].split()
    q = sandbox.run(*cmd)
    assert q.returncode == 0, q.stdout + q.stderr
    assert "  notice:\n    stage2_backend: done\n" in _read(path)


def test_real_gate_rejects_done_from_blocked_report(sandbox):
    """result=blocked 레포트는 기록 정합만 통과한다 - 완료 근거가 아니므로 done 을 쓰지 않는다."""
    path = _sandbox_state(sandbox)
    sandbox.write_report("2609281100_stage2_notice_backend.md", dev_meta(result="blocked"))
    p = sandbox.run("state.py", "set", "--stage", "2", "--slice", "notice", "--value", "done")
    assert p.returncode == 1, p.stdout + p.stderr
    assert _read(path) == STATE


# ---------------------------------------------------------------- blocked·거부

def test_blocked_requires_reason(tmp_path):
    path = _file(tmp_path)
    rc = state.main(["--file", path, "set", "--stage", "2", "--slice", "notice", "--value", "blocked"])
    assert rc == 2
    assert _read(path) == STATE


def test_blocked_writes_reason_and_unit_prefix(tmp_path):
    import yaml
    path = _file(tmp_path)
    assert state.main(["--file", path, "set", "--stage", "5", "--slice", "notice", "--value", "blocked",
                       "--reason", "DB 미기동: 포트 # 충돌"]) == 0
    text = _read(path)
    assert "    stage5_integration: blocked\n" in text
    assert yaml.safe_load(text)["slices"]["notice"]["blocked_reason"] == "[stage5_integration] DB 미기동: 포트 # 충돌"
    # blocked_reason 줄이 없는 slice 에는 units 앞에 넣는다
    assert state.main(["--file", path, "set", "--stage", "2", "--slice", "claim", "--unit", "intake",
                       "--value", "blocked", "--reason", "선행 unit 대기"]) == 0
    d = yaml.safe_load(_read(path))
    assert d["slices"]["claim"]["blocked_reason"] == "[unit intake.stage2_backend] 선행 unit 대기"
    assert d["slices"]["claim"]["units"]["intake"]["stage2_backend"] == "blocked"
    assert list(d["slices"]["claim"].keys()) == ["stage2_backend", "stage4_frontend", "stage5_integration",
                                                  "blocked_reason", "units"]
    h = _history(path)
    assert h[-1]["reason"] == "선행 unit 대기" and h[-1]["blocked_reason_from"] is None


def test_unblock_clears_only_own_reason(tmp_path):
    """두 unit 이 막히면 사유가 둘 다 남고, 하나를 풀면 그 사유만 지운다. 사람이 적은 라벨 없는 글은 남는다."""
    import yaml
    path = _file(tmp_path)
    for uid, why in (("intake", "선행 대기"), ("core", "DB 없음")):
        assert state.main(["--file", path, "set", "--stage", "2", "--slice", "claim", "--unit", uid,
                           "--value", "blocked", "--reason", why]) == 0
    reason = lambda: yaml.safe_load(_read(path))["slices"]["claim"]["blocked_reason"]  # noqa: E731
    assert reason() == "[unit intake.stage2_backend] 선행 대기 | [unit core.stage2_backend] DB 없음"
    assert state.main(["--file", path, "set", "--stage", "2", "--slice", "claim", "--unit", "core",
                       "--value", "in_progress"]) == 0
    assert reason() == "[unit intake.stage2_backend] 선행 대기"
    assert state.main(["--file", path, "set", "--stage", "2", "--slice", "claim", "--unit", "intake",
                       "--value", "pending"]) == 0
    assert reason() is None
    assert "    blocked_reason: null\n" in _read(path)
    # 라벨 없는 사람 글(hold 사유)은 blocked 를 풀어도 남는다
    assert state.main(["--file", path, "set", "--stage", "4", "--slice", "board", "--value", "blocked",
                       "--reason", "화면 근거 없음"]) == 0
    assert yaml.safe_load(_read(path))["slices"]["board"]["blocked_reason"] == "hold - 다른 사유 | [stage4_frontend] 화면 근거 없음"
    assert state.main(["--file", path, "set", "--stage", "4", "--slice", "board", "--value", "in_progress"]) == 0
    assert "    blocked_reason: hold - 다른 사유\n" in _read(path)
    h = _history(path)
    assert h[-1]["blocked_reason_to"] == "hold - 다른 사유"


def test_reason_separator_is_replaced_so_unblock_leaves_no_orphan(tmp_path, capsys):
    """사유 안의 ' | ' 는 ' / ' 로 바꿔 저장한다 - 그대로 두면 풀 때 뒷부분이 라벨 없는 조각으로 남는다."""
    import yaml
    path = _file(tmp_path)
    assert state.main(["--file", path, "set", "--stage", "5", "--slice", "notice", "--value", "blocked",
                       "--reason", "DB 없음  |  포트 충돌"]) == 0
    assert "' / ' 로 바꿔" in capsys.readouterr().err
    d = yaml.safe_load(_read(path))
    assert d["slices"]["notice"]["blocked_reason"] == "[stage5_integration] DB 없음 / 포트 충돌"
    assert _history(path)[-1]["reason"] == "DB 없음 / 포트 충돌"
    assert state.main(["--file", path, "set", "--stage", "5", "--slice", "notice", "--value", "in_progress"]) == 0
    assert yaml.safe_load(_read(path))["slices"]["notice"]["blocked_reason"] is None


def test_template_state_blocked_and_unblock(tmp_path):
    """templates/state.yaml 원문(값 없이 적힌 `blocked_reason:` + 줄 끝 주석)에서 blocked 를 기록·해제한다."""
    import yaml
    with open(os.path.join(REPO, "templates", "state.yaml"), "rb") as f:
        raw = f.read()
    p = tmp_path / "state.yaml"
    p.write_bytes(raw)
    path = str(p)
    sid = next(iter(yaml.safe_load(raw.decode("utf-8"))["slices"]))
    assert state.main(["--file", path, "set", "--stage", "5", "--slice", sid, "--value", "blocked",
                       "--reason", "환경 미기동"]) == 0
    text = _read(path)
    d = yaml.safe_load(text)
    assert d["slices"][sid]["stage5_integration"] == "blocked"
    assert d["slices"][sid]["blocked_reason"] == "[stage5_integration] 환경 미기동"
    line = [ln for ln in text.splitlines() if "blocked_reason: '[stage5_integration]" in ln][0]
    assert "# blocked 일 때 사유" in line                       # 줄 끝 주석 보존
    assert state.main(["--file", path, "set", "--stage", "5", "--slice", sid, "--value", "in_progress"]) == 0
    assert yaml.safe_load(_read(path))["slices"][sid]["blocked_reason"] is None
    # 흐름 매핑 unit 도 템플릿 그대로 고친다
    units_sid = [k for k, v in d["slices"].items() if isinstance(v, dict) and v.get("units")][0]
    uid = next(iter(d["slices"][units_sid]["units"]))
    assert state.main(["--file", path, "set", "--stage", "4", "--slice", units_sid, "--unit", uid,
                       "--value", "in_progress"]) == 0
    assert yaml.safe_load(_read(path))["slices"][units_sid]["units"][uid]["stage4_frontend"] == "in_progress"


def test_unknown_slice_unit_stage_rejected(tmp_path):
    path = _file(tmp_path)
    for args in (["--stage", "2", "--slice", "nope"],
                 ["--stage", "2", "--slice", "claim", "--unit", "nope"],
                 ["--stage", "5", "--slice", "claim", "--unit", "core"],     # unit 에는 5단계가 없다
                 ["--stage", "stage9_packaging"],                             # 이 파일에 없는 단계 키
                 ["--stage", "2"]):                                           # 2 는 단계 전체 값으로 모호
        assert state.main(["--file", path, "set", *args, "--value", "pending"]) == 2, args
    assert _read(path) == STATE
    assert _history(path) == []


def test_done_elsewhere_needs_human_declaration(tmp_path):
    path = _file(tmp_path)
    assert state.main(["--file", path, "set", "--stage", "4", "--slice", "notice", "--value", "done_elsewhere"]) == 2
    decl = STATE + ("elsewhere:\n  slices.notice.stage4_frontend:\n    where: 다른 환경\n    evidence: 표\n"
                    "    not_verified_here: 레포트\n    declared_by: '사람:담당'\n")
    path = _file(tmp_path, decl)
    assert state.main(["--file", path, "set", "--stage", "4", "--slice", "notice", "--value", "done_elsewhere"]) == 0


def test_reason_with_emoji_rejected(tmp_path):
    path = _file(tmp_path)
    assert state.main(["--file", path, "set", "--stage", "2", "--slice", "notice", "--value", "blocked",
                       "--reason", "막힘 " + CHECK]) == 2
    assert _read(path) == STATE


# ---------------------------------------------------------------- 이력·블록 보존

def test_history_appended_and_updated_at_stamped(tmp_path):
    path = _file(tmp_path)
    assert state.main(["--file", path, "set", "--stage", "4", "--slice", "notice", "--value", "in_progress",
                       "--reason", "시작", "--by", "오케스트레이터"]) == 0
    assert state.main(["--file", path, "set", "--stage", "stage3_common", "--value", "in_progress"]) == 0
    h = _history(path)
    assert len(h) == 2
    assert h[0] == {"at": h[0]["at"], "key": "slices.notice.stage4_frontend", "from": "pending",
                    "to": "in_progress", "reason": "시작", "by": "오케스트레이터"}
    assert len(h[0]["at"]) == 16 and h[0]["at"][4] == "-"          # YYYY-MM-DD HH:MM
    assert f"updated_at: {h[1]['at']}     # KST\n" in _read(path)
    # 같은 값이면 바꾸지 않고 이력도 남기지 않는다
    assert state.main(["--file", path, "set", "--stage", "stage3_common", "--value", "in_progress"]) == 0
    assert len(_history(path)) == 2


def test_other_slice_blocks_and_comments_unchanged(tmp_path):
    path = _file(tmp_path)
    assert state.main(["--file", path, "set", "--stage", "4", "--slice", "board", "--value", "in_progress"]) == 0
    assert state.main(["--file", path, "set", "--stage", "4", "--slice", "claim", "--unit", "core",
                       "--value", "in_progress"]) == 0
    text = _read(path)
    assert _block(text, "notice") == _block(STATE, "notice")
    assert "      core: {stage2_backend: done, stage4_frontend: in_progress}\n" in text
    assert "    blocked_reason: hold - 다른 사유\n" in text
    assert text.startswith("# 파이프라인 상태 (주석은 보존된다)\n")
    assert text.split("\nlog:\n")[1] == STATE.split("\nlog:\n")[1]
    # 바뀐 줄은 정확히 세 줄(board·core·updated_at)이고 줄 수는 그대로다
    before, after = STATE.split("\n"), text.split("\n")
    assert len(before) == len(after)
    assert len([1 for a, b in zip(before, after) if a != b]) == 3


def test_crlf_preserved(tmp_path):
    p = tmp_path / "state.yaml"
    p.write_bytes(STATE.replace("\n", "\r\n").encode("utf-8"))
    assert state.main(["--file", str(p), "set", "--stage", "4", "--slice", "board", "--value", "in_progress"]) == 0
    raw = p.read_bytes().decode("utf-8")
    assert "\r\n    stage4_frontend: in_progress\r\n" in raw
    assert "\n" not in raw.replace("\r\n", "")


def test_get_and_show(tmp_path, capsys):
    path = _file(tmp_path)
    assert state.main(["--file", path, "get", "--stage", "2", "--slice", "claim", "--unit", "core"]) == 0
    assert capsys.readouterr().out.strip() == "done"
    assert state.main(["--file", path, "show"]) == 0
    out = capsys.readouterr().out
    assert "stage3_common=pending" in out and "board: s2=done" in out and "core(s2=done s4=pending)" in out


def test_gate_runs_without_lock_and_change_during_gate_is_not_overwritten(tmp_path, monkeypatch):
    """게이트는 잠금 밖에서 돈다. 그 사이 다른 쓰기가 있으면 쓰지 않고 3(다시 실행)으로 끝난다."""
    from _common import file_lock
    path = _file(tmp_path)
    other = STATE.replace("  board:\n    stage2_backend: done\n    stage4_frontend: pending",
                          "  board:\n    stage2_backend: done\n    stage4_frontend: in_progress")

    def gate(stage, sl, unit, text, report=None):
        with file_lock(path, timeout=1):     # 잠금을 쥐고 있지 않아야 1초 안에 잡힌다
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(other)               # 판정하는 동안 다른 쓰기가 들어온다
        return 0, ["레포트 x.md"]
    monkeypatch.setattr(state, "run_gate", gate)
    rc = state.main(["--file", path, "set", "--stage", "2", "--slice", "notice", "--value", "done"])
    assert rc == 3
    assert _read(path) == other              # 다른 쓰기가 그대로 남는다
    assert _history(path) == []


def test_unchanged_during_gate_is_written_and_lock_free_gate(tmp_path, monkeypatch):
    from _common import file_lock
    path = _file(tmp_path)
    seen = []

    def gate(stage, sl, unit, text, report=None):
        with file_lock(path, timeout=1):
            seen.append("잠금 획득")
        return 0, ["레포트 x.md"]
    monkeypatch.setattr(state, "run_gate", gate)
    assert state.main(["--file", path, "set", "--stage", "2", "--slice", "notice", "--value", "done"]) == 0
    assert seen == ["잠금 획득"]
    assert "  notice:\n    stage2_backend: done\n" in _read(path)
    assert len(_history(path)) == 1
    assert not os.path.exists(path + ".lock")


def test_report_relative_path_is_resolved_from_caller_cwd(tmp_path, monkeypatch):
    calls = []

    class P:
        returncode = 0
        stdout = '{"report": "r.md", "results": []}'
        stderr = ""
    monkeypatch.setattr(state.subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw)) or P())
    monkeypatch.chdir(tmp_path)
    rc, _lines = state.run_gate(2, "notice", None, "a: 1\n", report=os.path.join("rel", "r.md"))
    cmd, kw = calls[0]
    assert rc == 0
    assert cmd[cmd.index("--report") + 1] == os.path.join(str(tmp_path), "rel", "r.md")
    assert kw["env"]["PA_STATE_FILE"] != ""   # gate 판정용 새 state 는 PA_STATE_FILE 로 넘긴다


def test_state_tool_ignores_gate_state_env(tmp_path, monkeypatch):
    """gate 의 PA_STATE_FILE 이 남아 있어도 state.py 기본 경로는 그것을 따르지 않는다."""
    decoy = _file(tmp_path)
    monkeypatch.setenv("PA_STATE_FILE", decoy)
    assert state.default_state_path() != os.path.abspath(decoy)
    monkeypatch.setenv(state.STATE_PATH_ENV, decoy)
    assert state.default_state_path() == decoy


def test_multiline_value_replaced_and_blank_line_kept(tmp_path):
    """여러 줄 값은 이어지는 줄까지 바꾸고, 그 사이 빈 줄은 남긴다. 나머지 줄은 그대로다."""
    import yaml
    text = STATE.replace("    blocked_reason: hold - 다른 사유\n",
                         "    blocked_reason: hold - 다른\n\n      사유\n")
    path = _file(tmp_path, text)
    assert yaml.safe_load(text)["slices"]["board"]["blocked_reason"] == "hold - 다른\n사유"
    assert state.main(["--file", path, "set", "--stage", "4", "--slice", "board", "--value", "blocked",
                       "--reason", "막힘"]) == 0
    out = _read(path)
    assert "      사유\n" not in out
    d = yaml.safe_load(out)
    assert d["slices"]["board"]["blocked_reason"] == "hold - 다른 사유 | [stage4_frontend] 막힘"
    assert len(out.split("\n")) == len(text.split("\n")) - 1


def test_line_diff_check_rejects_lost_lines():
    """의미가 같아도 줄이 더 없어지면(주석 손실 등) 거부한다."""
    before = ["a: 1", "# 주석", "b: 2"]
    with pytest.raises(state.StateError):
        state.check_line_diff(before, ["a: 3", "b: 2"], 1, 1)
    state.check_line_diff(before, ["a: 3", "# 주석", "b: 2"], 1, 1)


def test_edit_refuses_when_result_would_change_other_values():
    """줄 편집 결과를 다시 읽어 대상 값 말고 다른 값이 다르면 쓰지 않는다 - 블록 경계 안전장치."""
    import yaml
    data = yaml.safe_load(STATE)
    with pytest.raises(state.StateError):
        state.edit_text(STATE.replace("stage0_ingest: done", "stage0_ingest: pending"), data,
                        [(("stages", "stage3_common"), "done")])
