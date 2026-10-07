# tools/hooks/guard.py — 훅이 원칙(이모지 금지·게이트 없는 완료 금지·결과 블록 필수)을 실제로 막는지
import json
import os
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
