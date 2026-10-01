# tools/hooks/guard.py — 훅이 원칙(이모지 금지·게이트 없는 완료 금지·결과 블록 필수)을 실제로 막는지
import json
import os
import subprocess
import sys

from conftest import dev_meta

SMILE = "\U0001F600"   # 이모지 문자는 escape 로만 쓴다
CHECK = "\u2705"


def guard(sandbox, mode, payload):
    return subprocess.run([sys.executable, os.path.join(sandbox.root, "tools", "hooks", "guard.py"), mode],
                          input=json.dumps(payload, ensure_ascii=False), capture_output=True, text=True,
                          encoding="utf-8", cwd=sandbox.root, env=dict(os.environ, PYTHONIOENCODING="utf-8"))


def pre(sandbox, tool, **tool_input):
    return guard(sandbox, "pre-tool-use", {"tool_name": tool, "tool_input": tool_input})


# ---------------------------------------------------------------- 이모지

def test_write_with_emoji_is_denied_for_any_file(sandbox):
    for path, text in [
        ("target/backend/src/main/java/x/A.java", f"/** 서비스 {CHECK} */\nclass A {{}}\n"),
        ("target/backend/src/main/resources/mapper/A.xml", f"<!-- 조회 {SMILE} -->\n"),
        ("target/backend/src/main/resources/application.yml", f"# 설정 {CHECK}\n"),
        ("target/backend/src/main/resources/db/migration/V1__a.sql", f"COMMENT '아이디 {SMILE}'\n"),
        ("workspace/t/reports/2609281100_stage2_a.md", f"# 레포트 {CHECK}\n"),
    ]:
        p = pre(sandbox, "Write", file_path=os.path.join(sandbox.root, path), content=text)
        assert p.returncode == 2, path
        assert "이모지 금지" in p.stderr


def test_edit_multiedit_bash_with_emoji_are_denied(sandbox):
    f = os.path.join(sandbox.root, "target", "A.java")
    assert pre(sandbox, "Edit", file_path=f, old_string="a", new_string=f"b {SMILE}").returncode == 2
    assert pre(sandbox, "MultiEdit", file_path=f,
               edits=[{"old_string": "a", "new_string": "b"}, {"old_string": "c", "new_string": CHECK}]).returncode == 2
    assert pre(sandbox, "Bash", command=f"echo '{CHECK}' >> target/README.md").returncode == 2


def test_clean_writes_and_emoji_removal_are_allowed(sandbox):
    f = os.path.join(sandbox.root, "target", "A.java")
    assert pre(sandbox, "Write", file_path=f, content="/** 서비스 → 응답 · ≥ 3 */\nclass A {}\n").returncode == 0
    # 이모지를 지우는 편집(old 에만 이모지)은 허용
    assert pre(sandbox, "Edit", file_path=f, old_string=f"완료 {CHECK}", new_string="완료").returncode == 0
    assert pre(sandbox, "Bash", command="python -m pytest -q").returncode == 0


# ---------------------------------------------------------------- state.yaml 완료 전환

def _state(sandbox, backend="in_progress"):
    os.makedirs(sandbox.ws, exist_ok=True)
    path = os.path.join(sandbox.ws, "state.yaml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"iteration: 1\nstages:\n  stage3_common: pending\nslices:\n  notice:\n    stage2_backend: {backend}\n")
    return path


def test_marking_done_without_passing_report_is_denied(sandbox):
    path = _state(sandbox)
    p = pre(sandbox, "Edit", file_path=path, old_string="stage2_backend: in_progress", new_string="stage2_backend: done")
    assert p.returncode == 2
    assert "slices.notice.stage2_backend" in p.stderr


def test_marking_done_with_failing_report_is_denied(sandbox):
    path = _state(sandbox)
    meta = dev_meta()
    meta["gates"][1]["test_count"] = 0           # 0건 통과 → gate FAIL
    sandbox.write_report("2609281100_stage2_notice_backend.md", meta)
    p = pre(sandbox, "Edit", file_path=path, old_string="stage2_backend: in_progress", new_string="stage2_backend: done")
    assert p.returncode == 2
    assert "gate-proof" in p.stderr


def test_marking_done_with_passing_report_is_allowed(sandbox):
    path = _state(sandbox)
    sandbox.write_report("2609281100_stage2_notice_backend.md", dev_meta())
    gate = sandbox.run("gate.py", "check", "--stage", "2", "--slice", "notice", "--skip", "state-consistency")
    assert gate.returncode == 0, gate.stdout
    p = pre(sandbox, "Edit", file_path=path, old_string="stage2_backend: in_progress", new_string="stage2_backend: done")
    assert p.returncode == 0, p.stderr


def test_other_state_changes_are_not_gated(sandbox):
    path = _state(sandbox)
    p = pre(sandbox, "Edit", file_path=path, old_string="stage2_backend: in_progress", new_string="stage2_backend: blocked")
    assert p.returncode == 0
    # Write 로 전체를 바꿔도 done 전환이 없으면 허용
    p = pre(sandbox, "Write", file_path=path, content="iteration: 2\nstages:\n  stage3_common: in_progress\n")
    assert p.returncode == 0


def test_bash_writes_to_state_are_denied_but_reads_allowed(sandbox):
    for cmd in ["sed -i 's/in_progress/done/' workspace/t/state.yaml",
                "echo x > workspace/t/state.yaml",
                "python -c \"import yaml;yaml.safe_dump({},open('workspace/t/state.yaml','w'))\"",
                "cp /tmp/s.yaml workspace/t/state.yaml"]:
        assert pre(sandbox, "Bash", command=cmd).returncode == 2, cmd
    for cmd in ["cat workspace/t/state.yaml 2>/dev/null", "grep done workspace/t/state.yaml | head",
                "python tools/rr.py stats --write",
                # 다른 파일에 쓰는 명령의 문구 안에 state.yaml 이라는 단어만 있는 경우 (실측 오탐)
                "python - <<'X'\nopen('CLAUDE.md','w').write('진행은 state.yaml 에만 기록한다')\nX"]:
        assert pre(sandbox, "Bash", command=cmd).returncode == 0, cmd


# ---------------------------------------------------------------- 서브에이전트 결과 블록

def _agents(sandbox):
    d = os.path.join(sandbox.root, ".claude", "agents")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "backend-developer.md"), "w", encoding="utf-8") as f:
        f.write("---\nname: backend-developer\ndescription: x\n---\n")


GOOD_BLOCK = ('보고 요약\n\n```json pa-agent-result\n{"schema": 1, "agent": "backend-developer", "result": "done", '
              '"gates": [], "changed_files": [], "not_executed": []}\n```\n')


def test_subagent_without_result_block_is_blocked(sandbox):
    _agents(sandbox)
    p = guard(sandbox, "subagent-stop", {"agent_type": "backend-developer", "last_assistant_message": "끝났습니다."})
    assert p.returncode == 2 and "pa-agent-result" in p.stderr


def test_subagent_with_broken_or_incomplete_block_is_blocked(sandbox):
    _agents(sandbox)
    broken = GOOD_BLOCK.replace('"not_executed": []', '"not_executed": [')
    assert guard(sandbox, "subagent-stop", {"agent_type": "backend-developer",
                                            "last_assistant_message": broken}).returncode == 2
    partial = GOOD_BLOCK.replace(', "not_executed": []', "")
    p = guard(sandbox, "subagent-stop", {"agent_type": "backend-developer", "last_assistant_message": partial})
    assert p.returncode == 2 and "not_executed" in p.stderr


def test_subagent_report_with_emoji_is_blocked(sandbox):
    _agents(sandbox)
    p = guard(sandbox, "subagent-stop", {"agent_type": "backend-developer",
                                         "last_assistant_message": f"완료 {CHECK}\n" + GOOD_BLOCK})
    assert p.returncode == 2 and "이모지" in p.stderr


def test_valid_subagent_report_and_non_pipeline_agents_pass(sandbox):
    _agents(sandbox)
    assert guard(sandbox, "subagent-stop", {"agent_type": "backend-developer",
                                            "last_assistant_message": GOOD_BLOCK}).returncode == 0
    assert guard(sandbox, "subagent-stop", {"agent_type": "Explore", "last_assistant_message": "x"}).returncode == 0
    # 이미 한 번 막았으면 반복하지 않는다
    assert guard(sandbox, "subagent-stop", {"agent_type": "backend-developer", "stop_hook_active": True,
                                            "last_assistant_message": "x"}).returncode == 0


# ---------------------------------------------------------------- 사람 전용 (공통 계약 승인·잠금 해제)

APPROVE_CMD = "python tools/common_contract.py " + "approve --by 에이전트"   # 이 파일을 Bash 로 다룰 때 훅에 걸리지 않게 나눠 쓴다
UNLOCK_CMD = "python tools/spec_lock.py " + "unlock --slice loan --by 에이전트 --reason x"


def test_agent_cannot_approve_contract_or_unlock_specs(sandbox):
    assert pre(sandbox, "Bash", command=APPROVE_CMD).returncode == 2
    assert pre(sandbox, "Bash", command=UNLOCK_CMD).returncode == 2
    assert pre(sandbox, "Bash", command="cd /x && " + APPROVE_CMD).returncode == 2
    assert pre(sandbox, "Bash", command="bash -c '" + APPROVE_CMD + "'").returncode == 2
    assert pre(sandbox, "Bash", command="python tools/common_contract.py --contract a.yaml " + "approve --by x").returncode == 2
    # 안내 문구 안에 명령이 적혀 있을 뿐인 경우는 허용 (실측 오탐)
    doc = "python - <<'X'\nprint('승인은 사람 몫: ! " + APPROVE_CMD + "')\nX"
    assert pre(sandbox, "Bash", command=doc).returncode == 0
    assert pre(sandbox, "Bash", command="python tools/common_contract.py validate").returncode == 0
    d = os.path.join(sandbox.ws, "contracts")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "common-contract.yaml")
    with open(path, "w", encoding="utf-8") as f:
        f.write("schema: 1\napproved: false\nitems: []\n")
    p = pre(sandbox, "Edit", file_path=path, old_string="approved: false", new_string="approved: true")
    assert p.returncode == 2 and "사람 전용" in p.stderr
    # 승인과 무관한 편집(owner 결정 등)은 허용
    assert pre(sandbox, "Edit", file_path=path, old_string="items: []", new_string="items: []\nnote: x").returncode == 0


# ---------------------------------------------------------------- 입력 인코딩

def test_hook_reads_stdin_as_utf8_even_on_cp949_console(sandbox):
    # 실측: Windows 한국어 콘솔(cp949)에서 훅이 stdin 을 OS 기본 인코딩으로 읽어 한글 state.yaml 쓰기를
    # "YAML 로 읽히지 않는다" 로 막았다. 기존 테스트는 PYTHONIOENCODING=utf-8 을 넣어 이 결함을 가렸다.
    os.makedirs(sandbox.ws, exist_ok=True)
    path = os.path.join(sandbox.ws, "state.yaml")
    payload = {"tool_name": "Write", "tool_input": {"file_path": path,
               "content": "# 상태 파일\nproject: t\nstages:\n  stage0_ingest: in_progress\nlog:\n- note: 0단계 시작\n"}}
    p = subprocess.run([sys.executable, os.path.join(sandbox.root, "tools", "hooks", "guard.py"), "pre-tool-use"],
                       input=json.dumps(payload, ensure_ascii=False).encode("utf-8"), capture_output=True,
                       cwd=sandbox.root, env=dict(os.environ, PYTHONIOENCODING="cp949"))
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    # 같은 조건에서 이모지 판정도 한글 때문에 틀어지지 않고 동작한다
    payload["tool_input"] = {"file_path": os.path.join(sandbox.root, "target", "A.java"),
                             "content": f"/** 서비스 {SMILE} */\n"}
    p = subprocess.run([sys.executable, os.path.join(sandbox.root, "tools", "hooks", "guard.py"), "pre-tool-use"],
                       input=json.dumps(payload, ensure_ascii=False).encode("utf-8"), capture_output=True,
                       cwd=sandbox.root, env=dict(os.environ, PYTHONIOENCODING="cp949"))
    assert p.returncode == 2
