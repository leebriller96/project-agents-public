# tools/hooks/guard.py — 훅이 원칙(이모지 금지·게이트 없는 완료 금지·결과 블록 필수)을 실제로 막는지
import json
import os
import re
import subprocess
import sys

from conftest import REPO, dev_meta

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


def test_bash_state_deny_points_to_state_tool_and_state_tool_is_allowed(sandbox):
    """직접 쓰기 차단 문구는 state.py 를 안내하고, state.py 실행 자체는 막지 않는다."""
    p = pre(sandbox, "Bash", command="sed -i 's/in_progress/done/' workspace/t/state.yaml")
    assert p.returncode == 2 and "python tools/state.py set" in p.stderr
    for cmd in ["python tools/state.py set --stage 2 --slice notice --value done",
                "python tools/state.py --file workspace/t/state.yaml set --stage 5 --slice notice "
                "--value blocked --reason '환경 미기동'",
                "python tools/state.py show > /tmp/state-summary.txt"]:
        assert pre(sandbox, "Bash", command=cmd).returncode == 0, cmd


def test_git_hook_bypass_is_denied_but_similar_flags_allowed(sandbox):
    # 실측: 에이전트가 커밋에 -c core.hooksPath=/dev/null 을 붙였다(훅이 없어 실제 손실은 없었지만 지침 위반)
    for cmd in ["git -c core.hooksPath=/dev/null commit -m x",
                "git -C ../t -c core.hooksPath=NUL commit -qm x",
                "git commit --no-verify -m x",
                "git commit -n -m x",
                "git push --no-verify origin shared-dev"]:
        p = pre(sandbox, "Bash", command=cmd)
        assert p.returncode == 2, cmd
        assert "훅 우회" in p.stderr
    for cmd in ["git log -n 5", "git commit -m 'no verify 문구'", "grep -n hooksPath docs/x.md",
                "git -c user.name=t commit -m x"]:
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


def test_delegated_approvals_let_agent_run_human_only_commands(sandbox):
    # 사용자가 위임(approvals.delegate_to_agent: true)하면 에이전트가 세 명령을 실행할 수 있다
    sandbox.write_config("approvals:\n  delegate_to_agent: true\n  delegated_by: 사용자\n"
                         "verification:\n  visual:\n    approver: human\n")
    assert pre(sandbox, "Bash", command=APPROVE_CMD).returncode == 0
    assert pre(sandbox, "Bash", command=UNLOCK_CMD).returncode == 0
    assert pre(sandbox, "Bash", command="python tools/visual.py " + "approve --files a.png --by x").returncode == 0
    d = os.path.join(sandbox.ws, "contracts")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "common-contract.yaml")
    with open(path, "w", encoding="utf-8") as f:
        f.write("schema: 1\napproved: false\nitems: []\n")
    assert pre(sandbox, "Edit", file_path=path, old_string="approved: false", new_string="approved: true").returncode == 0


def test_delegation_off_keeps_human_only(sandbox):
    sandbox.write_config("approvals:\n  delegate_to_agent: false\n")
    assert pre(sandbox, "Bash", command=UNLOCK_CMD).returncode == 2


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

# ---------------------------------------------------------------- 잠긴 spec 쓰기 판정 (양방향)

def _lock_manifest(sandbox, rel):
    """sandbox 에 slice 하나의 잠금 매니페스트를 심는다."""
    d = os.path.join(sandbox.ws, "specs")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "loan.lock.json"), "w", encoding="utf-8") as f:
        json.dump({"schema": 1, "slice": "loan", "locked_at": "2026-10-06 00:00",
                   "files": {rel: {"sha256": "0" * 64, "lines": 1}}}, f)


def test_locked_spec_bash_guard_tells_writes_from_stderr_redirection(sandbox):
    """잠긴 spec 을 **근거로 인용**하는 명령은 막지 않고, 실제로 **고치는** 명령은 막는다.

    실측(2026-10-06): `rr.py new --evidence '<잠긴 spec 경로>' 2>&1` 이 막혔다.
    `2>&1` 은 표준오류를 표준출력으로 복제할 뿐 파일을 쓰지 않는데 `>` 패턴에 걸렸다.
    잠긴 spec 이 틀렸다고 보이면 RR 로 남기는 것이 18절이 정해 둔 사용법이므로 이 오검출은 그 길을 막았다.
    """
    rel = "server/user/src/test/java/com/example/user/spec/loan/LoanSpecTest.java"
    _lock_manifest(sandbox, rel)

    # (1) 막지 않아야 하는 것 — 경로를 인용만 한다
    quote = "python tools/rr.py new --title t --evidence " + chr(34) + rel + ":53" + chr(34) + " 2>&1"
    assert pre(sandbox, "Bash", command=quote).returncode == 0
    assert pre(sandbox, "Bash", command="cat " + rel + " 2>&1 | head -5").returncode == 0
    assert pre(sandbox, "Bash", command="grep -c RPT_X " + rel + " 2>&1").returncode == 0
    assert pre(sandbox, "Bash", command="echo 점검 >&2 && wc -l " + rel).returncode == 0

    # (2) 막아야 하는 것 — 실제로 고친다
    for cmd in ("sed -i s/a/b/ " + rel,
                "echo x > " + rel,
                "echo x >> " + rel,
                "rm " + rel,
                "mv " + rel + " /tmp/x",
                "git checkout -- " + rel,
                "cat x > LoanSpecTest.java"):
        p = pre(sandbox, "Bash", command=cmd)
        assert p.returncode == 2, "막지 못했다: " + cmd
        assert "잠금" in p.stderr, cmd


def test_locked_spec_bash_guard_tells_same_basename_in_other_slice(sandbox):
    """다른 slice 의 **같은 이름** spec 파일을 다루는 명령은 막지 않는다.

    실측(2026-10-14): 여러 slice 가 `SpecApp.tsx`·`harness.ts` 같은 같은 이름의 spec 파일을 가진다.
    파일 이름만 비교했더니 아직 잠기지 않은 새 slice 의 spec 을 옮기는 `cp`·`git stash` 명령까지 막혔다.
    디렉터리까지 적힌 경로는 그 경로로 판정하고, 이름만 적힌 경우는 종전처럼 막는다.
    """
    rel = "apps/user/src/features/loan/__spec__/loan/SpecApp.tsx"
    other = "apps/user/src/features/card/__spec__/card/SpecApp.tsx"
    _lock_manifest(sandbox, rel)

    # (1) 막지 않아야 하는 것 — 다른 slice 의 같은 이름 파일
    for cmd in ("cp /tmp/x " + other,
                "git stash push -- " + other,
                "rm ./" + other,
                "echo x > " + other):
        assert pre(sandbox, "Bash", command=cmd).returncode == 0, "막혔다: " + cmd

    # (2) 막아야 하는 것 — 잠긴 파일 자신(전체·뒷부분 경로) 또는 이름만 적은 경우
    for cmd in ("cp /tmp/x " + rel,
                "rm ./" + rel,
                "rm C:/work/target/" + rel,
                "git checkout -- loan/SpecApp.tsx",
                "echo x > " + rel,
                "cd apps/user/src/features/loan/__spec__/loan && rm SpecApp.tsx"):
        p = pre(sandbox, "Bash", command=cmd)
        assert p.returncode == 2, "막지 못했다: " + cmd
        assert "잠금" in p.stderr, cmd


def test_locked_spec_guard_separates_redirection_target_from_read(sandbox):
    """읽기·인용은 막지 않고, 그 파일에 **쓰는 것**만 막는다.

    실측(2026-10-06, 같은 부류로 세 번): "> 가 있으면 쓰기" + "이름이 보이면 그 파일" 로 뭉뚱그렸더니
    `2>&1`(표준오류 복제)과 `2>/dev/null`(널 장치)에 걸려, 잠긴 테스트를 **근거로 인용**해 RR 을 만드는
    명령이 막혔다. 18절이 정해 둔 유일한 정상 경로였다.
    """
    rel = "server/user/src/test/java/com/example/user/spec/loan/LoanSpecTest.java"
    base = os.path.basename(rel)
    _lock_manifest(sandbox, rel)

    # (1) 막지 않아야 하는 것 — 읽기·인용. 리다이렉션이 있어도 대상이 그 파일이 아니다
    for cmd in ("grep -n X " + rel + " 2>/dev/null",
                'python tools/rr.py new --evidence "' + rel + ':53" 2>&1',
                "cat " + rel + " | head -5",
                "wc -l " + rel,
                "grep X " + rel + " > /tmp/out.txt",
                "echo 점검 >&2 && wc -l " + rel,
                "python -c \"print(open('" + rel + "').read())\""):
        p = pre(sandbox, "Bash", command=cmd)
        assert p.returncode == 0, "막지 말아야 한다: " + cmd + "\n" + p.stderr

    # (2) 막아야 하는 것 — 리다이렉션 대상이 그 파일이거나, 인자형 쓰기 명령이 그 파일을 다룬다
    for cmd in ("echo x > " + rel,
                "echo x >> " + rel,
                "cat y > " + base,
                "sed -i s/a/b/ " + rel,
                "rm " + rel,
                "mv " + rel + " /tmp/x",
                "cp /tmp/x " + rel,
                "git checkout -- " + rel,
                "echo x | tee " + rel,
                "truncate -s 0 " + rel):
        p = pre(sandbox, "Bash", command=cmd)
        assert p.returncode == 2, "막아야 한다: " + cmd
        assert "잠금" in p.stderr, cmd


def test_redirect_target_parser_ignores_fd_dup_and_null_device():
    import sys as _s
    import os as _o
    _s.path.insert(0, _o.path.join(REPO, "tools", "hooks"))
    import guard as g
    assert g.redirect_targets("grep x a.java 2>/dev/null") == []
    assert g.redirect_targets("cmd 2>&1") == []
    assert g.redirect_targets("echo x >&2") == []
    assert g.redirect_targets("echo x > out.txt") == ["out.txt"]
    assert g.redirect_targets("echo x >> out.txt") == ["out.txt"]
    assert g.redirect_targets("a > b.txt 2>/dev/null && c >> d.txt") == ["b.txt", "d.txt"]
    assert g.redirect_targets("cmd 1>f.txt") == []          # fd 번호가 붙은 것은 보지 않는다 (보수적)
    assert g.redirect_targets("cat a | wc -l") == []


def test_state_guard_ignores_placeholder_angle_bracket(sandbox):
    """`workspace/<project>/state.yaml` 의 `>` 는 자리표시자 닫는 꺾쇠다 — 리다이렉션이 아니다.

    실측(2026-10-06): 에이전트 **지침 파일**을 고치는 명령이 그 문구 때문에 막혔다
    ("Bash 로 state.yaml 을 고친다" 로 오판). 같은 부류의 오검출이 하루에 네 번째였다.
    """
    st = "state" + ".yaml"
    real = "workspace/demo/" + st

    # (1) 막지 말아야 하는 것 — 문구에 단어가 있을 뿐이거나 읽기다
    for cmd in ('python - <<P\nnew = "workspace/<project>/' + st + ' 은 직접 고치지 않는다"\nP',
                "cat " + real,
                "grep -n stages " + real + " 2>/dev/null",
                'echo "' + st + ' 은 Edit 으로 고친다"',
                "cat " + real + " > /tmp/copy.yaml"):
        p = pre(sandbox, "Bash", command=cmd)
        assert p.returncode == 0, "막지 말아야 한다: " + cmd + "\n" + p.stderr

    # (2) 막아야 하는 것 — 공백 없는 리다이렉션도 포함한다 (우회를 열지 않았다)
    for cmd in ("echo x > " + real,
                "echo x >> " + real,
                "echo x >" + real,
                "echo x | tee " + real,
                "sed -i s/a/b/ " + real,
                "mv /tmp/x " + real,
                "python -c \"open('" + real + "','w').write('x')\""):
        p = pre(sandbox, "Bash", command=cmd)
        assert p.returncode == 2, "막아야 한다: " + cmd
        assert "게이트" in p.stderr, cmd


def test_placeholder_close_detection():
    import sys as _s
    import os as _o
    _s.path.insert(0, _o.path.join(REPO, "tools", "hooks"))
    import guard as g
    # 자리표시자 뒤의 경로는 리다이렉션 대상이 아니다
    assert g.redirect_targets("doc: workspace/<project>/specs/a.json") == []
    assert g.redirect_targets("see <dir>/file.txt") == []
    # 진짜 리다이렉션은 그대로 잡는다
    assert g.redirect_targets("echo x > out.txt") == ["out.txt"]
    assert g.redirect_targets("echo x >out.txt") == ["out.txt"]
    assert g.redirect_targets("echo x >> a/b.txt") == ["a/b.txt"]
    # 섞여 있어도 가린다
    assert g.redirect_targets("echo <ph>/x && echo y > z.txt") == ["z.txt"]


def test_deny_words_are_blocked_at_write_time_only_for_tracked_files(sandbox):
    """공개본 금지어는 **쓰기 시점**에 막는다 — 커밋 뒤에 잡으면 이미 이력에 박힌다.

    실측(2026-10-06, 하루에 세 번): 프로브 시험에 실측 명령을 그대로 붙여 쓰다가 고객 식별
    문자열이 tracked 파일로 들어갔다. 세 번 모두 커밋 뒤 `publish-public --check` 로 잡혔다.
    이모지와 같은 성질이므로 같은 자리에서 막는다.

    범위: 이 저장소의 **git 에 올라가는** 파일만. gitignore 대상(workspace·config/project.yaml)·
    저장소 밖(target_dir)·규칙 파일 자신은 고객 이름이 있어야 정상이다.
    """
    bad = "zzcustomer"      # 샌드박스 규칙에만 넣는 가짜 금지어
    # 샌드박스를 git 저장소로 만들고 이 repo 와 같은 무시 규칙을 둔다 (판정이 gitignore 에 걸려 있다)
    subprocess.run(["git", "init", "-q"], cwd=sandbox.root, capture_output=True)
    with open(os.path.join(sandbox.root, ".gitignore"), "w", encoding="utf-8") as f:
        f.write("workspace/*/\nconfig/project.yaml\n")
    rules = os.path.join(sandbox.root, "config", "publish-public", "rules.yaml")
    os.makedirs(os.path.dirname(rules), exist_ok=True)
    with open(rules, "w", encoding="utf-8") as f:
        f.write("deny:\n  - '(?i)" + bad + "'\n")

    def w(path, content):
        return pre(sandbox, "Write", file_path=os.path.join(sandbox.root, path), content=content)

    # (1) tracked 파일은 막는다
    p = w("tests/test_x.py", 'rel = "' + bad + '/a"\n')
    assert p.returncode == 2, p.stdout
    assert "공개본 금지어" in p.stderr and bad in p.stderr, p.stderr
    assert "일반화해서 다시 쓴다" in p.stderr

    # Edit 의 new_string 도 본다
    p = pre(sandbox, "Edit", file_path=os.path.join(sandbox.root, "docs", "x.md"),
            old_string="a", new_string=bad + " 사례")
    assert p.returncode == 2, p.stderr

    # (2) gitignore 대상·규칙 파일 자신·저장소 밖·깨끗한 내용은 막지 않는다
    assert w("workspace/demo/HANDOFF.md", bad + " 인계\n").returncode == 0
    assert w("config/project.yaml", "project:\n  name: " + bad + "\n").returncode == 0
    assert w("config/publish-public/rules.yaml", "deny:\n  - '" + bad + "'\n").returncode == 0
    assert w("tests/test_x.py", 'rel = "demo/a"\n').returncode == 0
    outside = pre(sandbox, "Write", file_path=os.path.join(sandbox.root, "..", "other-repo", "x.md"),
                  content=bad + "\n")
    assert outside.returncode == 0, outside.stderr

    # (3) 규칙 파일이 없으면 검사하지 않는다 (뒤로 호환 — 다른 프로젝트는 이 규칙이 없다)
    os.remove(rules)
    assert w("tests/test_x.py", 'rel = "' + bad + '/a"\n').returncode == 0


# ---------------------------------------------------------------- 토큰 절감 (pipeline-core §26)

def _maven_log(n=400):
    return "\n".join([f"[INFO] 컴파일 {i}" for i in range(n)]
                     + ["[ERROR] Tests run: 12, Failures: 1", "java.lang.AssertionError: expected 1 but 2"]
                     + [f"    at a.b.C{i}(C.java:{i})" for i in range(10)]
                     + [f"[INFO] 끝 {i}" for i in range(60)] + ["BUILD FAILURE"])


def post(sandbox, command, stdout, stderr=""):
    return guard(sandbox, "post-tool-use", {"tool_name": "Bash", "tool_input": {"command": command},
                                            "tool_response": {"stdout": stdout, "stderr": stderr,
                                                              "interrupted": False, "isImage": False}})


def test_long_bash_output_is_compacted_and_full_log_kept(sandbox):
    log = _maven_log()
    p = post(sandbox, "mvn test", log)
    assert p.returncode == 0
    out = json.loads(p.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PostToolUse"
    new = out["updatedToolOutput"]
    assert new["interrupted"] is False and new["isImage"] is False and new["stderr"] == ""
    text = new["stdout"]
    assert len(text) < len(log) / 3
    # 실패 정보는 빠지지 않는다: 실패 줄·단언 메시지·스택 앞 3줄·끝부분
    assert "Tests run: 12, Failures: 1" in text and "AssertionError" in text and "BUILD FAILURE" in text
    assert "C2(C.java:2)" in text and "C3(C.java:3)" not in text
    path = text.split("전체 로그: ", 1)[1].split("\n", 1)[0]
    assert path.startswith(os.path.join(sandbox.ws, "logs", "bash"))
    with open(path, encoding="utf-8") as f:
        assert f.read().endswith(log)


def test_short_output_full_mark_and_off_switch_are_left_alone(sandbox):
    assert post(sandbox, "ls", "a\nb\n").stdout == ""
    assert post(sandbox, "PA_FULL_OUTPUT=1 mvn test", _maven_log()).stdout == ""
    assert guard(sandbox, "post-tool-use", {"tool_name": "Read", "tool_input": {},
                                            "tool_response": {"stdout": _maven_log()}}).stdout == ""
    sandbox.write_config("pipeline:\n  token:\n    bash_compact_chars: 0\n")
    assert post(sandbox, "mvn test", _maven_log()).stdout == ""


def test_long_subagent_prose_is_blocked(sandbox):
    _agents(sandbox)
    long_prose = "상세 표 " * 1000 + "\n" + GOOD_BLOCK
    p = guard(sandbox, "subagent-stop", {"agent_type": "backend-developer", "last_assistant_message": long_prose})
    assert p.returncode == 2 and "report_file" in p.stderr
    # 결과 블록 안의 내용은 산문 길이에 세지 않는다
    big_block = GOOD_BLOCK.replace('"changed_files": []', '"changed_files": [' + ",".join(['"a/b.java"'] * 800) + "]")
    assert guard(sandbox, "subagent-stop", {"agent_type": "backend-developer",
                                            "last_assistant_message": big_block}).returncode == 0


# ---------------------------------------------------------------- PowerShell 도구 (RR-0602)

PS_STATE = "workspace/t/" + "state.yaml"


def test_powershell_writes_to_state_are_denied(sandbox):
    for cmd in ["Set-Content -Path " + PS_STATE + " -Value x",
                "(Get-Content " + PS_STATE + ") -replace 'a','b' | Set-Content " + PS_STATE.replace("/", "\\"),
                "Add-Content " + PS_STATE + " 'x: 1'",
                "'x' | Out-File -FilePath " + PS_STATE + " -Encoding utf8",
                "'x' > " + PS_STATE,
                "'x' >> " + PS_STATE,
                "Remove-Item -Force " + PS_STATE,
                "del " + PS_STATE,
                "Copy-Item C:/tmp/s.yaml -Destination " + PS_STATE,
                "Copy-Item C:/tmp/s.yaml " + PS_STATE,
                "Move-Item " + PS_STATE + " C:/tmp/old.yaml",
                "Set-Content -Path:" + PS_STATE + " -Value x -Confirm:$false",
                "[IO.File]::WriteAllText('" + PS_STATE + "', 'x')"]:
        p = pre(sandbox, "PowerShell", command=cmd)
        assert p.returncode == 2, "막지 못했다: " + cmd
        assert "state.py set" in p.stderr, cmd


def test_powershell_reads_and_state_tool_are_allowed(sandbox):
    for cmd in ["Get-Content " + PS_STATE + " | Select-String done",
                "Copy-Item " + PS_STATE + " C:/tmp/backup.yaml",
                "python tools/state.py set --stage 2 --slice notice --value done",
                "python tools/state.py --file " + PS_STATE + " set --stage 5 --slice notice --value blocked --reason x",
                "python tools/state.py show > C:/tmp/state-summary.txt",
                "git rm --cached " + PS_STATE,
                "'x' | Out-File -FilePath out.txt 2>$null",
                "Set-Content -Path docs/x.md -Value 'state.yaml 은 state.py 로 고친다'"]:
        p = pre(sandbox, "PowerShell", command=cmd)
        assert p.returncode == 0, f"{cmd}\n{p.stderr}"


def test_powershell_locked_spec_and_manifest_and_hook_bypass(sandbox):
    rel = "server/user/src/test/java/com/example/user/spec/loan/LoanSpecTest.java"
    _lock_manifest(sandbox, rel)
    for cmd in ["Set-Content " + rel + " 'x'", "Remove-Item " + rel, "'x' > " + rel,
                "Copy-Item C:/tmp/x.java -Destination " + rel,
                "Set-Content workspace/t/specs/loan.lock.json '{}'"]:
        p = pre(sandbox, "PowerShell", command=cmd)
        assert p.returncode == 2 and "잠금" in p.stderr, cmd
    assert pre(sandbox, "PowerShell", command="Get-Content " + rel + " | Select-Object -First 5").returncode == 0
    p = pre(sandbox, "PowerShell", command="git commit --no-" + "verify -m x")
    assert p.returncode == 2 and "훅 우회" in p.stderr
    assert pre(sandbox, "PowerShell", command="Write-Output " + chr(0x2705)).returncode == 2


# ---------------------------------------------------------------- 인계 도구 보고·결과 블록 저장

def _saved(sandbox):
    d = os.path.join(sandbox.ws, "reports", "agent-results")
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


def _transcript(sandbox, handback_message, last_text="모든 검증이 끝났다. 보고를 전달한다."):
    """인계 도구로 보고를 넘긴 서브에이전트 transcript (실측 구조: 짧은 텍스트 -> SubagentHandback tool_use -> tool_result)."""
    path = os.path.join(sandbox.root, "agent.jsonl")
    recs = [
        {"type": "assistant", "message": {"content": [{"type": "text", "text": last_text}]}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "SubagentHandback",
                                                       "input": {"message": handback_message}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": "delivered"}]}},
    ]
    with open(path, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


def test_result_block_without_json_tag_is_accepted(sandbox):
    _agents(sandbox)
    plain = GOOD_BLOCK.replace("```json pa-agent-result", "```pa-agent-result")
    p = guard(sandbox, "subagent-stop", {"agent_type": "backend-developer", "last_assistant_message": plain})
    assert p.returncode == 0, p.stderr
    assert len(_saved(sandbox)) == 1


def test_subagent_stop_reads_handback_report_from_transcript(sandbox):
    """실측(10-30): 보고가 인계 도구 입력에만 있고 마지막 텍스트는 한 줄이라 결과 블록을 저장하지 못했다."""
    _agents(sandbox)
    tp = _transcript(sandbox, GOOD_BLOCK)
    p = guard(sandbox, "subagent-stop", {"agent_type": "backend-developer", "agent_transcript_path": tp,
                                         "last_assistant_message": "모든 검증이 끝났다. 보고를 전달한다."})
    assert p.returncode == 0, p.stderr
    assert len(_saved(sandbox)) == 1
    # last_assistant_message 가 비어 와도 같다 (같은 보고는 한 번만 저장한다)
    p = guard(sandbox, "subagent-stop", {"agent_type": "backend-developer", "agent_transcript_path": tp})
    assert p.returncode == 0 and len(_saved(sandbox)) == 1


def test_subagent_stop_blocks_handback_report_without_block(sandbox):
    _agents(sandbox)
    tp = _transcript(sandbox, "끝났습니다.")
    p = guard(sandbox, "subagent-stop", {"agent_type": "backend-developer", "agent_transcript_path": tp,
                                         "last_assistant_message": "끝."})
    assert p.returncode == 2 and "pa-agent-result" in p.stderr


def test_handback_pre_tool_use_checks_and_saves_once(sandbox):
    _agents(sandbox)
    ok = guard(sandbox, "pre-tool-use", {"tool_name": "SubagentHandback", "agent_type": "backend-developer",
                                         "tool_input": {"message": GOOD_BLOCK}})
    assert ok.returncode == 0, ok.stderr
    assert len(_saved(sandbox)) == 1
    # 뒤이어 SubagentStop 이 같은 보고를 보면 두 번 저장하지 않는다
    tp = _transcript(sandbox, GOOD_BLOCK)
    assert guard(sandbox, "subagent-stop", {"agent_type": "backend-developer",
                                            "agent_transcript_path": tp}).returncode == 0
    assert len(_saved(sandbox)) == 1
    # 블록 없는 인계는 넘기기 전에 막는다
    bad = guard(sandbox, "pre-tool-use", {"tool_name": "SubagentHandback", "agent_type": "backend-developer",
                                          "tool_input": {"message": "끝났습니다."}})
    assert bad.returncode == 2 and "pa-agent-result" in bad.stderr
    # agent_type 이 없으면 블록의 agent 로 판단한다 - 그것도 읽을 수 없으면(깨진 JSON) 막지 않는다
    partial = GOOD_BLOCK.replace(', "not_executed": []', "")
    assert guard(sandbox, "pre-tool-use", {"tool_name": "SubagentHandback",
                                           "tool_input": {"message": partial}}).returncode == 2
    broken = GOOD_BLOCK.replace('"not_executed": []', '"not_executed": [')
    assert guard(sandbox, "pre-tool-use", {"tool_name": "SubagentHandback",
                                           "tool_input": {"message": broken}}).returncode == 0
    # 파이프라인 밖 에이전트는 보지 않는다
    assert guard(sandbox, "pre-tool-use", {"tool_name": "SubagentHandback", "agent_type": "general-purpose",
                                           "tool_input": {"message": "x"}}).returncode == 0


# ---------------------------------------------------------------- PowerShell 2회차 (RV-0600-2~5·10)

PS_DENY_R2 = [
    # RV-0600-2 New-Item·Export-*·그 밖의 쓰기 cmdlet
    "New-Item -Force -Path " + PS_STATE + " -Value 'x'",
    "ni " + PS_STATE + " -Force -Value x",
    "New-Item -Path workspace/t -Name " + "state.yaml" + " -ItemType File -Force",
    "Get-Process | Export-Csv -Path " + PS_STATE,
    "epcsv " + PS_STATE + " -NoTypeInformation",
    "$o | Export-Clixml " + PS_STATE,
    "Start-Transcript -Path " + PS_STATE,
    "Invoke-WebRequest http://x/y -OutFile " + PS_STATE,
    "Rename-Item " + PS_STATE + " old.yaml",
    # RV-0600-3 매개변수 약어
    "Set-Content -Pa " + PS_STATE + " -Value x",
    "Set-Content -LiteralP " + PS_STATE + " -Value x",
    "'x' | Out-File -FileP " + PS_STATE,
    "Copy-Item C:/tmp/s.yaml -Dest " + PS_STATE,
    "Copy-Item -Pa C:/tmp/s.yaml -Dest " + PS_STATE + " -Fo",
    # RV-0600-4 비리터럴 대상·모듈 한정 이름·.NET·2>
    "$p = '" + PS_STATE + "'; Set-Content $p 'x'",
    "Set-Content (Join-Path workspace/t " + "state.yaml" + ") 'x'",
    "Set-Content -Path \"$root/" + PS_STATE + "\" -Value x",
    "Get-ChildItem workspace -Recurse -Filter " + "state.yaml" + " | Remove-Item",
    "Microsoft.PowerShell.Management\\Set-Content " + PS_STATE + " 'x'",
    "[IO.File]::Create('" + PS_STATE + "')",
    "[System.IO.File]::OpenWrite('" + PS_STATE + "')",
    "New-Object System.IO.StreamWriter('" + PS_STATE + "')",
    "Write-Error x 2> " + PS_STATE,
    "Write-Output x *>> " + PS_STATE,
]


def test_powershell_r2_writes_are_denied(sandbox):
    for cmd in PS_DENY_R2:
        p = pre(sandbox, "PowerShell", command=cmd)
        assert p.returncode == 2, "막지 못했다: " + cmd
        assert "state.py set" in p.stderr, cmd


PS_ALLOW_R2 = [
    # RV-0600-5 따옴표 안 문구 오검출
    "Write-Output 'see tee " + PS_STATE + "'",
    "Write-Output 'a > " + PS_STATE + "'",
    "Write-Output \"sed -i x " + PS_STATE + "\"",
    # 비리터럴 대상이지만 보호 대상 이름이 없다
    "$p = 'docs/a.md'; Set-Content $p 'x'",
    "Remove-Item $tmp -Recurse -Force",
    "New-Item -ItemType Directory -Force C:/tmp/x",
    "'x' 2>&1 | Out-File log.txt",
    "Get-ChildItem *.tmp | Remove-Item",
    # 보호 대상은 읽기·원본만
    "Copy-Item -Path " + PS_STATE + " -Dest C:/tmp/b.yaml",
    "Export-Csv -Path out.csv -InputObject (Get-Content " + PS_STATE + ")",
    "python tools/state.py set --stage 5 --slice notice --value blocked --reason 'state.yaml 은 손대지 않음'",
]


def test_powershell_r2_reads_and_quoted_text_are_allowed(sandbox):
    for cmd in PS_ALLOW_R2:
        p = pre(sandbox, "PowerShell", command=cmd)
        assert p.returncode == 0, f"{cmd}\n{p.stderr}"


def test_powershell_r2_locked_spec_new_item_and_dynamic(sandbox):
    rel = "server/user/src/test/java/com/example/user/spec/loan/LoanSpecTest.java"
    _lock_manifest(sandbox, rel)
    for cmd in ["New-Item -Force -Path " + rel + " -Value x",
                "$f = '" + rel + "'; Set-Content $f 'x'",
                "Copy-Item C:/tmp/x.java -Dest " + rel,
                "Export-Clixml -Path workspace/t/visual/approved.json -InputObject $x"]:
        p = pre(sandbox, "PowerShell", command=cmd)
        assert p.returncode == 2 and "잠금" in p.stderr, cmd
    assert pre(sandbox, "PowerShell", command="Write-Output 'rm " + rel + "'").returncode == 0


def test_handback_long_prose_is_saved_with_warning_not_blocked(sandbox):
    """인계 시점에는 산문 상한을 막지 않고 경고만 낸다(검토 추천안). SubagentStop 은 종전대로 막는다."""
    _agents(sandbox)
    long_prose = "상세 표 " * 1000 + "\n" + GOOD_BLOCK
    p = guard(sandbox, "pre-tool-use", {"tool_name": "SubagentHandback", "agent_type": "backend-developer",
                                        "tool_input": {"message": long_prose}})
    assert p.returncode == 0, p.stderr
    assert "경고" in p.stderr and "report_file" in p.stderr
    assert len(_saved(sandbox)) == 1
    # 이모지는 인계 시점에도 막는다
    p = guard(sandbox, "pre-tool-use", {"tool_name": "SubagentHandback", "agent_type": "backend-developer",
                                        "tool_input": {"message": "완료 " + chr(0x2705) + "\n" + GOOD_BLOCK}})
    assert p.returncode == 2 and "이모지" in p.stderr


# ---------------------------------------------------------------- 보호 폴더 통째 삭제·이동 (RR-0604)

SPEC_REL = "server/user/src/test/java/com/example/user/spec/loan/LoanSpecTest.java"


def test_bash_removes_or_moves_protected_dir_without_trailing_slash(sandbox):
    """끝 / 없는 폴더 경로로 통째 삭제·이동하면 막는다. 종전에는 Bash 에 보호 폴더 판정 자체가 없었다."""
    for cmd in ("rm -rf workspace/t/specs",
                "rm -rf workspace/t/specs/",
                "rm -rf workspace/t/visual",
                "rm -rf workspace/t/specs*",
                "rm -rf 'workspace/t/specs'",
                "rm -rf ./workspace/t/specs && echo 끝",
                "rm -rf workspace/t/reports/../specs",
                "rm -rf C:\\work\\repo\\workspace\\t\\specs",
                "rm -rf /c/work/repo/workspace/t/visual 2>/dev/null",
                "rmdir workspace/t/visual",
                "rm workspace/t/specs/loan.lock.json",
                "mv workspace/t/specs /tmp/specs.bak",
                "mv /tmp/x workspace/t/specs",
                "cd /tmp; rm -rf /work/workspace/t/specs",
                "git rm -r workspace/t/specs",
                "find workspace/t/specs -delete",
                "find workspace/t/specs -name '*.json' -exec rm {} +",
                "ls workspace/t/specs | xargs rm",
                "D=workspace/t/specs; rm -rf $D",
                "if true; then rm -rf workspace/t/visual; fi"):
        p = pre(sandbox, "Bash", command=cmd)
        assert p.returncode == 2, "막지 못했다: " + cmd
        assert "잠금" in p.stderr, cmd


def test_powershell_removes_or_moves_protected_dir_without_trailing_slash(sandbox):
    for cmd in ("Remove-Item -Recurse -Force workspace/t/specs",
                "Remove-Item -Recurse workspace/t/visual",
                "Remove-Item -Recurse -Force 'workspace\\t\\specs'",
                "ri workspace/t/specs -Recurse",
                "Move-Item workspace/t/specs C:/tmp/specs",
                "Move-Item -Path workspace/t/visual -Destination C:/tmp/v",
                "Rename-Item workspace/t/specs specs2",
                "Get-ChildItem workspace/t/specs/ | Remove-Item",
                "Get-ChildItem workspace/t/specs | Remove-Item -Recurse",
                "[IO.Directory]::Delete('workspace/t/specs', $true)",
                "[System.IO.Directory]::Move('workspace/t/visual', 'C:/tmp/v')"):
        p = pre(sandbox, "PowerShell", command=cmd)
        assert p.returncode == 2, "막지 못했다: " + cmd
        assert "잠금" in p.stderr, cmd


def test_removing_parent_of_protected_dir_is_denied(sandbox):
    for tool, cmd in (("Bash", "rm -rf workspace/t"),
                      ("Bash", "rm -rf workspace/t/"),
                      ("Bash", "rm -rf workspace/t/*"),
                      ("Bash", "rm -rf workspace"),
                      ("Bash", "mv workspace/t /tmp/old"),
                      ("PowerShell", "Remove-Item -Recurse -Force workspace/t"),
                      ("PowerShell", "Remove-Item -Recurse workspace"),
                      ("PowerShell", "Move-Item workspace/t C:/tmp/old")):
        p = pre(sandbox, tool, command=cmd)
        assert p.returncode == 2, "막지 못했다: " + cmd
        assert "잠금" in p.stderr, cmd


def test_removing_parent_of_locked_file_is_denied(sandbox):
    """잠긴 파일 하나를 직접 적지 않아도 그 파일이 든 폴더를 없애면 막는다."""
    _lock_manifest(sandbox, SPEC_REL)
    d = os.path.dirname(SPEC_REL)
    for tool, cmd in (("Bash", "rm -rf " + d),
                      ("Bash", "rm -rf " + d + "/"),
                      ("Bash", "rm -rf " + d + "/*"),
                      ("Bash", "rm -rf ./server/user/src/test"),
                      ("Bash", "rm -rf /c/work/target/" + d),
                      ("Bash", "rm -rf src/test/java"),
                      ("Bash", "rm -rf server"),
                      ("Bash", "mv " + d + " /tmp/x"),
                      ("Bash", "git rm -r " + d),
                      ("Bash", "find " + d + " -delete"),
                      ("Bash", "ls " + d + " | xargs rm"),
                      ("Bash", "D=" + d + "; rm -rf \"$D\""),
                      ("Bash", "S=server/user; rm -rf \"${S}/src/test\""),
                      ("PowerShell", "Remove-Item -Recurse -Force " + d),
                      ("PowerShell", "Remove-Item -Recurse -Force " + d.replace("/", "\\")),
                      ("PowerShell", "Move-Item " + d + " C:/tmp/x"),
                      ("PowerShell", "Get-ChildItem " + d + " | Remove-Item")):
        p = pre(sandbox, tool, command=cmd)
        assert p.returncode == 2, "막지 못했다: " + cmd
        assert "잠금" in p.stderr, cmd


def test_protected_dir_read_commands_are_allowed(sandbox):
    """읽기·인용·비슷한 이름은 막지 않는다."""
    _lock_manifest(sandbox, SPEC_REL)
    d = os.path.dirname(SPEC_REL)
    for cmd in ("ls workspace/t/specs",
                "ls -la workspace/t/visual",
                "cat workspace/t/specs/loan.lock.json",
                "grep -r loan workspace/t/specs | head -5",
                "find workspace/t/specs -name '*.json'",
                "cp workspace/t/specs/loan.lock.json /tmp/loan.json",
                "du -sh workspace/t",
                "ls " + d,
                "find " + d + " -name '*.java'",
                "echo 'rm -rf workspace/t/specs 는 막힌다'",
                "python tools/rr.py new --title 'rm -rf workspace/t/specs 빈틈' 2>&1",
                "git commit -m 'mv workspace/t/specs 차단'",
                "cat > /tmp/note.md <<'E'\nrm -rf workspace/t/specs\nmv workspace/t/visual /tmp\nE\necho 끝",
                "ls workspace/t/specs; rm -f $TMPFILE",
                "D=" + d + "; rm -f $D/zzTmpProbe.test.tsx",
                "S=server/user; rm -f \"$S/target/surefire-reports/\"*Scratch*",
                "ls workspace/t/specs; rm -rf /tmp/x",
                "rm -rf workspace/t/reports/old",
                "rm -f workspace/t/specs_old.txt",
                "rm -f workspace/t/visual_report.md",
                "mv workspace/t/reports/a.md workspace/t/reports/b.md",
                "rm -rf /tmp/server",
                "rm -rf build target/classes server/user/target",
                "rm -f workspace/notes.txt"):
        p = pre(sandbox, "Bash", command=cmd)
        assert p.returncode == 0, "오탐: " + cmd + " / " + p.stderr
    for cmd in ("Get-ChildItem workspace/t/specs",
                "Get-Content workspace/t/specs/loan.lock.json | Select-Object -First 5",
                "Test-Path workspace/t/visual",
                "Get-ChildItem " + d,
                "Copy-Item workspace/t/specs/loan.lock.json C:/tmp/loan.json",
                "Write-Output 'Remove-Item workspace/t/specs'",
                "Remove-Item workspace/t/reports/old.md",
                "Remove-Item workspace/t/visual_report.md",
                "Remove-Item -Recurse C:/tmp/server",
                "Copy-Item C:/tmp/a.md workspace/t/a.md",
                "New-Item -ItemType Directory workspace/t/reports/x"):
        p = pre(sandbox, "PowerShell", command=cmd)
        assert p.returncode == 0, "오탐: " + cmd + " / " + p.stderr


# ---------------------------------------------------------------- 결과 파일 중복 (RR-0604)

def test_handback_and_stop_save_once_even_with_named_files_in_dir(sandbox):
    """실측: 손으로 지은 stage*.json 이 이름순 맨 뒤를 차지해 중복 검사 창에 새 파일이 들어오지 못했다."""
    _agents(sandbox)
    d = os.path.join(sandbox.ws, "reports", "agent-results")
    os.makedirs(d, exist_ok=True)
    for i in range(40):
        with open(os.path.join(d, f"stage5_old_{i:02d}.json"), "w", encoding="utf-8") as f:
            json.dump({"n": i}, f)
    before = set(_saved(sandbox))
    assert guard(sandbox, "pre-tool-use", {"tool_name": "SubagentHandback", "agent_type": "backend-developer",
                                           "tool_input": {"message": GOOD_BLOCK}}).returncode == 0
    tp = _transcript(sandbox, GOOD_BLOCK)
    assert guard(sandbox, "subagent-stop", {"agent_type": "backend-developer",
                                            "agent_transcript_path": tp}).returncode == 0
    new = sorted(set(_saved(sandbox)) - before)
    assert len(new) == 1, new
    # ingest 가 찾는 이름 형식과 저장 경로는 그대로다: <시각>_<에이전트>_<단계>_<slice>.json
    assert re.fullmatch(r"\d{12}_backend-developer_\d*_[\w.-]+\.json", new[0]), new[0]


def test_different_results_are_each_saved(sandbox):
    _agents(sandbox)
    other = GOOD_BLOCK.replace('"result": "done"', '"result": "blocked"')
    assert other != GOOD_BLOCK
    for msg in (GOOD_BLOCK, other):
        assert guard(sandbox, "subagent-stop", {"agent_type": "backend-developer",
                                                "last_assistant_message": msg}).returncode == 0
    assert len(_saved(sandbox)) == 2


# ---------------------------------------------------------------- 보호 폴더 판정 2회차 (RR-0604 검토 지적)

def _denied(sandbox, cases):
    """(도구, 명령) 목록이 전부 차단되는지 본다. 한 건씩 멈추지 않고 놓친 것을 모아 보여 준다."""
    missed = []
    for tool, cmd in cases:
        p = pre(sandbox, tool, command=cmd)
        if p.returncode != 2 or "잠금" not in p.stderr:
            missed.append(f"{tool}: {cmd}")
    assert not missed, "막지 못했다:\n" + "\n".join(missed)


def _allowed(sandbox, cases):
    false_hits = []
    for tool, cmd in cases:
        p = pre(sandbox, tool, command=cmd)
        if p.returncode != 0:
            false_hits.append(f"{tool}: {cmd} / {p.stderr.strip()[:80]}")
    assert not false_hits, "오탐:\n" + "\n".join(false_hits)


def _bash(*cmds):
    return [("Bash", c) for c in cmds]


def _ps(*cmds):
    return [("PowerShell", c) for c in cmds]


def _msys(path):
    """C:\\x 를 Git Bash 표기 /c/x 로 바꾼다."""
    p = path.replace("\\", "/")
    return "/" + p[0].lower() + p[2:] if re.match(r"^[A-Za-z]:", p) else p


def test_save_run_survives_file_vanishing_during_sort(sandbox):
    """RV-0604-1: glob 과 정렬 사이에 파일이 사라져도 이번 블록은 저장된다."""
    d = os.path.join(sandbox.ws, "reports", "agent-results")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "old.json"), "w", encoding="utf-8") as f:
        json.dump({"n": 1}, f)
    code = ("import glob, sys\n"
            "sys.path[:0] = ['tools/hooks', 'tools']\n"
            "import guard\n"
            "real = glob.glob\n"
            "guard.glob.glob = lambda p: real(p) + [p.replace('*.json', 'gone.json')]\n"
            "guard.save_run('backend-developer', {'schema': 1, 'result': 'blocked', 'stage': 2, 'slice': 'x'})\n")
    p = subprocess.run([sys.executable, "-c", code], cwd=sandbox.root, capture_output=True, text=True,
                       encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    assert p.returncode == 0, p.stderr
    assert "저장 실패" not in p.stderr
    assert len(_saved(sandbox)) == 2, _saved(sandbox)


def test_same_result_is_saved_again_after_compare_window(sandbox):
    """RV-0604-12: 같은 내용 비교는 최근 10분 파일만 본다. 며칠 뒤의 재실행은 새 파일로 남는다."""
    _agents(sandbox)
    stop = {"agent_type": "backend-developer", "last_assistant_message": GOOD_BLOCK}
    assert guard(sandbox, "subagent-stop", stop).returncode == 0
    assert guard(sandbox, "subagent-stop", stop).returncode == 0
    assert len(_saved(sandbox)) == 1                     # 인계와 SubagentStop 의 이중 저장은 계속 막는다
    d = os.path.join(sandbox.ws, "reports", "agent-results")
    old = os.path.join(d, _saved(sandbox)[0])
    t = os.path.getmtime(old) - 11 * 60
    os.utime(old, (t, t))
    assert guard(sandbox, "subagent-stop", stop).returncode == 0
    assert len(_saved(sandbox)) == 2


def test_git_clean_with_ignored_files_is_denied(sandbox):
    """RV-0604-2: -x·-X 는 gitignore 대상인 workspace 를 지운다."""
    _denied(sandbox, _bash("git clean -fdx",
                           "git clean -xdf",
                           "git clean -fdX",
                           "git clean -fdX workspace",
                           "git clean -f -d -x",
                           "git clean -fdx .",
                           "git clean -fdx -e keep.txt",
                           "git clean -fdx workspace/t/reports",
                           "git clean -fdx work*",
                           "git -C . clean -fdx",
                           "sudo git clean -fdx",
                           "echo a; git clean -fx",
                           "git clean -fdx 2>/dev/null",
                           "git clean -fdx > /tmp/clean.log") +
            _ps("git clean -fdx", "git clean -fdX workspace", "git -C . clean -fdx"))
    _allowed(sandbox, _bash("git clean -fd",
                            "git clean -fd workspace/t/reports",
                            "git clean -n -dx",
                            "git clean -ndx",
                            "git clean --dry-run -x",
                            "git clean -fdx target/classes",
                            "git clean -e xyz -fd",
                            "echo 'git clean -fdx'",
                            "git log --grep 'clean -fdx'") +
             _ps("git clean -fd", "git clean -ndx", "Write-Output 'git clean -fdx'"))


def test_git_rm_cached_is_allowed(sandbox):
    """RV-0604-10: 추적 해제는 작업 트리를 지우지 않는다."""
    _allowed(sandbox, _bash("git rm --cached -r workspace/t/specs",
                            "git rm -r --cached workspace",
                            "git -C . rm --cached -r workspace/t") +
             _ps("git rm --cached -r workspace/t/specs"))
    _denied(sandbox, _bash("git rm -r workspace/t/specs", "git rm -rf workspace", "git rm -r workspace/t") +
            _ps("git rm -r workspace/t/specs", "git rm -rf workspace"))


def test_mv_destination_is_judged_apart_from_source(sandbox):
    """RV-0604-11: 프로젝트 폴더로 넣는 이동은 통과, specs·visual 안 목적지는 차단. PowerShell 과 같은 판정."""
    _allowed(sandbox, _bash("mv report.md workspace/t/",
                            "mv report.md workspace/t",
                            "mv report.md workspace",
                            "mv a.md b.md workspace/t/reports/",
                            "mv -f report.md workspace/t/",
                            "mv -t workspace/t a.md b.md",
                            "git mv a.md workspace/t/") +
             _ps("Move-Item report.md workspace/t/", "Move-Item report.md workspace/t",
                 "Move-Item -Path a.md -Destination workspace/t", "Move-Item report.md workspace"))
    _denied(sandbox, _bash("mv x workspace/t/specs",
                           "mv x workspace/t/specs/",
                           "mv x workspace/t/visual/a.png",
                           "mv a.md b.md workspace/t/specs/",
                           "mv -t workspace/t/specs a.md",
                           "mv -t /tmp workspace/t/specs",
                           "mv workspace/t /tmp/old",
                           "mv workspace/t workspace/t2",
                           "git mv x workspace/t/specs/") +
            _ps("Move-Item x workspace/t/specs/", "Move-Item x workspace/t/visual/a.png",
                "Move-Item -Path x -Destination workspace/t/specs", "Move-Item workspace/t C:/tmp/old"))


def test_heredoc_with_backslash_delimiter_is_not_read_as_commands(sandbox):
    """RV-0604-17: 역슬래시 구분자 본문은 문서다. 본문 뒤 실제 명령은 그대로 본다."""
    body = "a; rm -rf workspace/t/specs\nmv workspace/t/visual /tmp\n"
    _allowed(sandbox, _bash("cat > /tmp/n.md <<\\E\n" + body + "E\necho 끝",
                            "cat > /tmp/n.md <<-\\E\n" + body + "E\n",
                            "cat > /tmp/n.md <<'E-1'\n" + body + "E-1\n",
                            "cat > /tmp/n.md <<\"E\"\n" + body + "E\n",
                            "cat > /tmp/n.md <<E\n" + body + "E\n"))
    _denied(sandbox, _bash("cat > /tmp/n.md <<\\E\nx\nE\nrm -rf workspace/t/specs"))


def test_glob_patterns_on_protected_names_are_denied(sandbox):
    """RV-0604-4: 글자 패턴이 보호 이름에 맞으면 막는다."""
    _denied(sandbox, _bash("rm -rf workspace/t/spec*",
                           "rm -rf workspace/t/[sv]*",
                           "rm -rf workspace/t/s?ecs",
                           "rm -rf workspace/t/*s",
                           "rm -rf work*/t/specs",
                           "rm -rf work*",
                           "rm -rf w?rkspace/t",
                           "rm -rf workspace/t*",
                           "rm -rf workspace/t/*/",
                           "rm -f workspace/t/spec*/a.json") +
            _ps("Remove-Item workspace/t/spec* -Recurse", "Remove-Item -Recurse work*/t/specs",
                "Remove-Item -Recurse workspace/t/[sv]*"))
    _allowed(sandbox, _bash("rm -f workspace/t/*.tmp",
                            "rm -f workspace/*.txt",
                            "rm -f workspace/t/s*.md",
                            "rm -f workspace/t/reports/*spec*",
                            "rm -f workspace/*/reports/old.md",
                            "rm -rf server/*/target",
                            "rm -rf */target",
                            "rm -f *.log",
                            "rm -rf build*") +
             _ps("Remove-Item workspace/t/*.tmp", "Remove-Item -Recurse build*"))


def test_non_literal_removal_targets_see_parent_folders(sandbox):
    """RV-0604-5: 변수·파이프 입력·쉼표 목록·-LP 도 상위 폴더까지 본다."""
    _denied(sandbox, _ps("$d='workspace/t'; Remove-Item -Recurse $d",
                         "$d = 'workspace/t'; Remove-Item -Recurse $d",
                         "$D = 'workspace'; Remove-Item -Recurse $d",
                         "$p='workspace/t'; Remove-Item -Recurse \"$p/specs\"",
                         "Remove-Item -Recurse \"$PWD\\workspace\\t\"",
                         "Get-ChildItem workspace/t | Remove-Item -Recurse",
                         "Get-ChildItem workspace | Remove-Item -Recurse",
                         "Get-ChildItem workspace/t | Where-Object { $_.Name -ne 'a' } | Remove-Item -Recurse",
                         "Get-ChildItem workspace/t | ForEach-Object { Remove-Item $_.FullName -Recurse }",
                         "Remove-Item -Recurse (Join-Path $root 'workspace/t')",
                         "Remove-Item -LP workspace/t -Recurse",
                         "Remove-Item -Cf workspace/t -Recurse",
                         "Remove-Item -ea SilentlyContinue workspace/t -Recurse",
                         "Remove-Item a,workspace -Recurse",
                         "Remove-Item 'a','workspace/t' -Recurse",
                         "Remove-Item a, workspace/t -Recurse") +
            _bash("echo workspace/t | xargs rm -rf",
                  "echo workspace | xargs -0 rm -rf",
                  "rm 2>/dev/null -rf workspace/t",
                  "rm > /dev/null -rf workspace/t"))
    _allowed(sandbox, _ps("Remove-Item $tmp; Get-Content workspace/t/a.md",
                          "Write-Output workspace/t; Remove-Item $x",
                          "Get-ChildItem workspace/t/reports | Remove-Item",
                          "Get-ChildItem workspace/t/reports/*.tmp | Remove-Item",
                          "$f='workspace/t/reports/a.md'; Remove-Item $f",
                          "$f = Join-Path $root 'workspace/t/reports'; Remove-Item \"$f/a.md\"",
                          "Remove-Item a.txt,b.txt",
                          "Remove-Item -LP workspace/t/reports/a.md",
                          "Get-ChildItem workspace/t") +
             _bash("ls workspace/t; rm -f $TMPFILE",
                   "cat list.txt | xargs rm -f",
                   "echo workspace/t/reports/a.md | xargs rm",
                   "rm 2>/dev/null -rf /tmp/x"))


def test_bash_target_forms_with_git_find_and_prefixes(sandbox):
    """RV-0604-6: git -C, find -name, xargs, 앞붙이의 통상 형태."""
    _denied(sandbox, _bash("git -C . rm -r workspace/t/specs",
                           "git -C workspace rm -r t/specs",
                           "git -c core.quotepath=off rm -r workspace/t/specs",
                           "git --no-pager rm -r workspace/t",
                           "find . -type d -name specs -exec rm -rf {} +",
                           "find . -name visual -exec rm -rf {} \\;",
                           "find . -name 'spec*' -delete",
                           "find -L . -name specs -delete",
                           "find . -path '*/specs/*' -delete",
                           "find . -name workspace -exec rm -rf {} +",
                           "find workspace -name visual | xargs rm -rf",
                           "find . -name specs | xargs rm -rf",
                           "export D=workspace/t/specs; rm -rf $D",
                           "declare -x D=workspace/t; rm -rf \"$D\"",
                           "for d in workspace/t/specs; do rm -rf \"$d\"; done",
                           "for d in a workspace/t; do rm -rf \"$d\"; done",
                           "for d in specs visual; do rm -rf workspace/t/$d; done",
                           "sudo -n rm -rf workspace/t/specs",
                           "sudo -u root rm -rf workspace/t",
                           "timeout 5 rm -rf workspace/t/specs",
                           "timeout -k 3 5 rm -rf workspace/t/specs",
                           "nice -n 5 rm -rf workspace/t/specs",
                           "env -u X rm -rf workspace/t",
                           "env A=1 rm -rf workspace/t/specs"))
    _allowed(sandbox, _bash("git -C /tmp/x rm -r a",
                            "git -C workspace/t status",
                            "git -C . log --oneline",
                            "find /tmp/x -name specs -exec rm -rf {} +",
                            "find . -name '*.tmp' -delete",
                            "find . -name specs",
                            "find . -name specs -prune -o -name '*.tmp' -delete",
                            "find . ! -name specs -name '*.tmp' -delete",
                            "find src -name specs -delete",
                            "find . -name '*.tmp' | xargs rm -f",
                            "timeout 5 python x.py workspace/t",
                            "sudo ls workspace/t/specs",
                            "nice -n 5 ls workspace",
                            "export D=/tmp/x; rm -rf $D",
                            "export D=workspace/t/specs; ls $D",
                            "for d in a b; do rm -rf \"/tmp/$d\"; done",
                            "for f in workspace/t/reports/*.tmp; do rm \"$f\"; done",
                            "command -v rm"))


def test_locked_parent_check_folds_case_and_compares_absolute(sandbox):
    """RV-0604-9: 대소문자를 접고, 절대 경로는 target_dir 기준으로 본다. 저장소 루트도 막는다."""
    _lock_manifest(sandbox, SPEC_REL)
    t, root = sandbox.target.replace("\\", "/"), sandbox.root.replace("\\", "/")
    q = lambda p: '"' + p + '"'        # 실제 경로에 공백이 들어갈 수 있다
    _denied(sandbox, _bash("rm -rf SERVER/USER",
                           "rm -rf Server",
                           "rm -rf " + q(t + "/server"),
                           "rm -rf " + q(_msys(t) + "/server"),
                           "rm -rf " + q(_msys(t) + "/SERVER/user"),
                           "rm -rf " + q(t),
                           "rm -rf " + q(_msys(t)),
                           "rm -rf " + q(root),
                           "rm -rf " + q(_msys(root)),
                           "mv " + q(t + "/server") + " /tmp/x") +
            _ps("Remove-Item -Recurse " + q(t + "/server"),
                "Remove-Item -Recurse " + q(_msys(t) + "/server"),
                "Remove-Item -Recurse SERVER/USER",
                "Remove-Item -Recurse " + q(t),
                "Remove-Item -Recurse " + q(root)))
    _allowed(sandbox, _bash("rm -rf /tmp/server",
                            "rm -rf " + q(t + "/build"),
                            "rm -rf " + q(t + "/server/user/target"),
                            "rm -rf " + q(root + "/tools/__pycache__"),
                            "rm -rf " + q(root + "2")) +
             _ps("Remove-Item -Recurse " + q(t + "/build"), "Remove-Item -Recurse C:/tmp/server"))


# ---------------------------------------------------------------- 보호 폴더 판정 3회차 (RR-0604 재검토 지적)

def test_xargs_judges_only_the_command_it_runs(sandbox):
    """R2-1: xargs 는 옵션과 값을 건너뛴 첫 명령 낱말로 판정한다. 인자의 rm 낱말이나 추적 해제는 삭제가 아니다."""
    _allowed(sandbox, _bash("ls workspace/t | xargs grep -l rm",
                            "ls workspace/t | xargs -n 1 grep rm",
                            "ls workspace/t | xargs -I X grep -l rm X",
                            "git ls-files workspace | xargs git rm --cached",
                            "git ls-files workspace | xargs -0 git rm --cached",
                            "git ls-files workspace | xargs git log --oneline",
                            "ls workspace/t/reports | xargs -n 1 rm"))
    _denied(sandbox, _bash("ls workspace/t | xargs -n 1 rm",
                           "ls workspace/t | xargs -n1 rm",
                           "ls workspace/t | xargs -I X rm X",
                           "ls workspace/t | xargs -0 -P 4 rm -rf",
                           "ls workspace/t | xargs --max-args 1 rm",
                           "ls workspace/t | xargs sudo rm",
                           "ls workspace/t | xargs 2>/dev/null rm",
                           "git ls-files workspace | xargs -0 git rm -r",
                           "git ls-files workspace/t | xargs git rm",
                           "ls workspace/t | xargs git -C . rm",
                           "ls workspace/t | xargs git mv -t /tmp",
                           "echo x | xargs git clean -fdx"))


def test_braced_variable_without_quotes_is_expanded(sandbox):
    """R2-2: 따옴표 없는 ${D} 도 $D 와 같이 펼친다. 큰따옴표 판정은 그대로다."""
    _denied(sandbox, _bash("D=workspace/t/specs; rm -rf ${D}",
                           "D=workspace/t; rm -rf ${D}/specs",
                           "D=workspace/t; rm -rf ${D}",
                           "D=workspace/t/specs; rm -rf \"${D}\"",
                           "D=workspace/t/specs; rm -rf $D",
                           "for d in workspace/t/specs; do rm -rf ${d}; done") +
            _ps("$d='workspace/t'; Remove-Item -Recurse ${d}",
                "$d='workspace/t'; Remove-Item -Recurse ${d}/specs",
                "$d='workspace/t'; Remove-Item -Recurse \"${d}\""))
    _allowed(sandbox, _bash("D=/tmp/x; rm -rf ${D}",
                            "rm -f ${TMPFILE}",
                            "D=workspace/t/reports; rm -f ${D}/a.md",
                            "S=server/user; rm -f ${S}/target/a.log",
                            "echo ${D}; ls workspace/t/specs",
                            "if [ -n ${A} ]; then echo 끝; fi") +
             _ps("$f='workspace/t/reports/a.md'; Remove-Item ${f}", "Write-Output ${x}"))


def test_git_clean_base_folder_must_be_literally_outside(sandbox):
    """git -C 도 같은 기준이다. 절대 경로만 통과하고 .. 로 시작하면 어디인지 몰라 막는다."""
    _denied(sandbox, _bash("git -C ../wt clean -fdx", "git -C workspace clean -fdx", "git clean -fdx -e workspace"))
    _allowed(sandbox, _bash("git -C /tmp/x clean -fdx"))


def test_documented_limits_stay_as_written(sandbox):
    """16-hooks.md 한계 절의 예시를 고정한다. 판정이 바뀌면 문서도 같이 고친다."""
    _allowed(sandbox, _bash("sudo --user root rm -rf workspace/t/specs",                       # 삭제 자체를 못 본다
                            "find workspace/t/specs \\( -name a -o -name b \\) -delete",
                            "ls workspace/t/specs | while read f; do rm -f \"$f\"; done",
                            "rm -rf */*/specs",                                               # 패턴이 앞 구간을 가린다
                            "rm -rf **/specs",
                            "rm -rf /",                                                       # 판정 제외
                            "rm -rf /*") +
             _ps("Get-ChildItem workspace/t | ForEach-Object {\nRemove-Item $_\n}",           # 상위 폴더까지 못 본다
                 "$d='workspace/t'; [IO.Directory]::Delete($d, $true)"))
    _denied(sandbox, _ps("Get-ChildItem workspace/t/specs | ForEach-Object {\nRemove-Item $_\n}",
                         "$d='workspace/t/specs'; [IO.Directory]::Delete($d, $true)"))
