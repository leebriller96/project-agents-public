# tools/hooks/pre-commit·tools/install_hooks.py — 하네스 밖 커밋에서도 이모지·커밋 금지 경로를 막는지 (RR-0600)
#
# 임시 git 저장소(Sandbox 복사본 + git init)에 훅을 설치하고 실제 git commit 으로 확인한다.
import os
import subprocess
import sys

import pytest

SMILE = chr(0x1F600)   # 이모지 문자는 코드포인트로만 만든다
CHECK = chr(0x2705)


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8")


def install(root, *args):
    return subprocess.run([sys.executable, os.path.join(root, "tools", "install_hooks.py"), *args],
                          cwd=root, capture_output=True, text=True, encoding="utf-8")


def hook_file(root):
    hook = git(root, "rev-parse", "--git-path", "hooks/pre-commit").stdout.strip()
    return hook if os.path.isabs(hook) else os.path.join(root, hook)


@pytest.fixture
def repo(sandbox):
    root = sandbox.root
    assert git(root, "init", "-q").returncode == 0
    git(root, "config", "user.name", "tester")
    git(root, "config", "user.email", "tester@example.com")
    git(root, "config", "core.autocrlf", "false")
    p = install(root)
    assert p.returncode == 0, p.stderr
    return root


def write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def commit(root, *paths, msg="시험"):
    assert git(root, "add", "-f", *paths).returncode == 0
    return git(root, "commit", "-q", "-m", msg)


def head(root):
    return git(root, "rev-parse", "-q", "--verify", "HEAD").stdout.strip()


def test_clean_commit_passes(repo):
    write(repo, "docs/note.md", "# 정상 문서\n완료 - 화살표 -> 가운뎃점 · 는 이모지가 아니다\n")
    write(repo, "tools/x.py", "# 주석\nprint('ok')\n")
    p = commit(repo, "docs/note.md", "tools/x.py")
    assert p.returncode == 0, p.stderr
    assert head(repo)


@pytest.mark.parametrize("rel", ["docs/bad.md", "tools/bad.py", "config/bad.yaml", "noext"])
def test_emoji_file_is_rejected(repo, rel):
    """quality.py 가 보는 확장자(.md·.yaml)와 보지 않는 확장자(.py·확장자 없음) 모두 막는다."""
    write(repo, rel, f"제목\n완료 {CHECK} 표시 {SMILE}\n")
    p = commit(repo, rel)
    assert p.returncode != 0
    assert "이모지" in p.stderr and rel in p.stderr and "NO-EMOJI" in p.stderr
    assert not head(repo)


def test_staged_content_is_checked_not_working_tree(repo):
    """스테이지된 내용에 이모지가 있으면 작업 트리에서 지웠어도 막는다 (커밋되는 것은 스테이지 내용이다)."""
    write(repo, "a.md", f"x {SMILE}\n")
    git(repo, "add", "a.md")
    write(repo, "a.md", "x\n")
    p = git(repo, "commit", "-q", "-m", "x")
    assert p.returncode != 0 and "a.md" in p.stderr


@pytest.mark.parametrize("rel", ["workspace/t/state.yaml", "docs/samples/x.md", "config/project.yaml"])
def test_forbidden_path_is_rejected(repo, rel):
    write(repo, rel, "a: 1\n")
    p = commit(repo, rel)
    assert p.returncode != 0
    assert "커밋 금지 경로" in p.stderr and rel in p.stderr
    assert not head(repo)


def test_untracking_forbidden_path_is_allowed(repo):
    """잘못 올라간 파일을 추적 해제하는 커밋은 막지 않는다 (삭제는 검사 대상이 아니다)."""
    write(repo, "workspace/t/x.md", "x\n")
    write(repo, "ok.md", "x\n")
    # 훅이 생기기 전에 올라간 상태를 흉내 낸다 - 훅을 잠시 치우고 커밋한 뒤 되돌린다
    hook = hook_file(repo)
    os.rename(hook, hook + ".off")
    assert commit(repo, "workspace/t/x.md", "ok.md").returncode == 0
    os.rename(hook + ".off", hook)
    assert git(repo, "rm", "-q", "--cached", "workspace/t/x.md").returncode == 0
    p = git(repo, "commit", "-q", "-m", "추적 해제")
    assert p.returncode == 0, p.stderr


def test_external_subtree_is_skipped(repo):
    write(repo, "external/tool/README.md", f"upstream {SMILE}\n")
    assert commit(repo, "external/tool/README.md").returncode == 0


def test_install_is_idempotent_and_check_reports(repo):
    hook = hook_file(repo)
    with open(hook, encoding="utf-8") as f:
        first = f.read()
    p = install(repo)
    assert p.returncode == 0 and "이미 설치됨" in p.stdout
    with open(hook, encoding="utf-8") as f:
        assert f.read() == first
    assert install(repo, "--check").returncode == 0
    # 이 도구가 설치한 옛 내용은 갱신한다
    with open(hook, "a", encoding="utf-8") as f:
        f.write("# 옛 줄\n")
    assert install(repo, "--check").returncode == 1
    p = install(repo)
    assert p.returncode == 0 and "갱신" in p.stdout
    with open(hook, encoding="utf-8") as f:
        assert f.read() == first


def test_install_does_not_overwrite_foreign_hook(sandbox):
    root = sandbox.root
    git(root, "init", "-q")
    hook = hook_file(root)
    os.makedirs(os.path.dirname(hook), exist_ok=True)
    with open(hook, "w", encoding="utf-8", newline="\n") as f:
        f.write("#!/bin/sh\necho 다른 훅\n")
    p = install(root)
    assert p.returncode == 1 and "덮어쓰지 않았다" in p.stderr
    with open(hook, encoding="utf-8") as f:
        assert f.read() == "#!/bin/sh\necho 다른 훅\n"
    assert install(root, "--check").returncode == 1


@pytest.mark.parametrize("rel", ["Workspace/t/x.md", "WORKSPACE/x.md", "Docs/Samples/x.md", "config/Project.yaml"])
def test_forbidden_path_case_variants_are_rejected(repo, rel):
    """RV-0600-1: Windows(core.ignorecase)에서는 대소문자만 다른 경로도 같은 실제 폴더다."""
    # sandbox 가 만든 config/project.yaml 이 있으면 대소문자 무시 파일 시스템에서 같은 파일이 되어
    # 다른 이름으로 스테이지되지 않는다 - 지우고 새 이름으로 만든다
    if rel.lower() == "config/project.yaml":
        os.remove(os.path.join(repo, "config", "project.yaml"))
    write(repo, rel, "a: 1\n")
    p = commit(repo, rel)
    assert p.returncode != 0 and "커밋 금지 경로" in p.stderr
    assert not head(repo)


def test_rename_into_forbidden_path_is_rejected(repo):
    write(repo, "ok.md", "x\n")
    assert commit(repo, "ok.md").returncode == 0
    os.makedirs(os.path.join(repo, "workspace", "t"), exist_ok=True)
    assert git(repo, "mv", "ok.md", "workspace/t/ok.md").returncode == 0
    p = git(repo, "commit", "-q", "-m", "옮기기")
    assert p.returncode != 0 and "workspace/t/ok.md" in p.stderr


def test_checker_error_blocks_commit(repo):
    """RV-0600-7·8: 검사 본체가 오류로 끝나면 통과로 보지 않고 막는다."""
    with open(os.path.join(repo, "tools", "quality.py"), "w", encoding="utf-8") as f:
        f.write("raise RuntimeError('깨진 검사기')\n")
    write(repo, "a.md", "정상\n")
    p = commit(repo, "a.md")
    assert p.returncode != 0 and "검사 본체 오류" in p.stderr


def test_broken_emoji_module_blocks_with_guidance_not_traceback(repo):
    """RV-0600-r2-2: 판정 모듈이 깨져도 안내 문구로 막는다 (모듈 최상위 import 는 run() 의 예외 처리 밖이었다)."""
    with open(os.path.join(repo, "tools", "_emoji.py"), "w", encoding="utf-8") as f:
        f.write("def 깨진(:\n")
    write(repo, "a.md", "정상\n")
    p = commit(repo, "a.md")
    assert p.returncode != 0
    assert "검사 본체 오류" in p.stderr and "Traceback" not in p.stderr
    assert not head(repo)


def _stage_gitlink(repo, rel):
    """하위 모듈 항목(mode 160000)을 스테이지에 넣는다. 가리키는 커밋은 이 저장소의 HEAD 를 쓴다."""
    p = git(repo, "update-index", "--add", "--cacheinfo", "160000," + head(repo) + "," + rel)
    assert p.returncode == 0, p.stderr


def _base_commit(repo):
    write(repo, "base.md", "정상\n")
    assert commit(repo, "base.md").returncode == 0


def test_gitlink_is_skipped_by_emoji_check(repo):
    """RV-0600-r2-3: gitlink 는 읽을 내용이 없다 - '이모지 검사를 끝내지 못했다' 로 거부하지 않는다."""
    _base_commit(repo)
    _stage_gitlink(repo, "vendor/sub")
    p = git(repo, "commit", "-q", "-m", "하위 모듈")
    assert p.returncode == 0, p.stderr


def test_gitlink_does_not_hide_other_problems(repo):
    """gitlink 제외가 함께 스테이지된 파일 검사나 커밋 금지 경로 검사를 비우지 않는다."""
    _base_commit(repo)
    _stage_gitlink(repo, "vendor/sub")
    write(repo, "a.md", f"x {SMILE}\n")
    assert git(repo, "add", "a.md").returncode == 0
    p = git(repo, "commit", "-q", "-m", "섞임")
    assert p.returncode != 0 and "a.md" in p.stderr and "이모지" in p.stderr
    assert git(repo, "reset", "-q").returncode == 0
    _stage_gitlink(repo, "workspace/t/sub")
    p = git(repo, "commit", "-q", "-m", "금지 경로")
    assert p.returncode != 0 and "workspace/t/sub" in p.stderr


def test_export_failure_raises_check_error(repo):
    sys.path.insert(0, os.path.join(repo, "tools", "hooks"))
    sys.path.insert(0, os.path.join(repo, "tools"))
    try:
        import importlib
        import pre_commit
        importlib.reload(pre_commit)
        with pytest.raises(pre_commit.CheckError):
            pre_commit.export_staged(repo, ["not-staged.md"], os.path.join(repo, "_out"))
    finally:
        sys.path.remove(os.path.join(repo, "tools", "hooks"))
        sys.path.remove(os.path.join(repo, "tools"))
        sys.modules.pop("pre_commit", None)


def _no_python_path(tmp):
    """git·sh 만 있고 python 은 없는 PATH. 만들 수 없으면 None."""
    import shutil
    gitx, shx = shutil.which("git"), shutil.which("sh")
    if not gitx or not shx:
        return None
    if os.name == "nt":
        path = os.pathsep.join(sorted({os.path.dirname(gitx), os.path.dirname(shx)}))
    else:
        path = os.path.join(tmp, "bin")
        os.makedirs(path, exist_ok=True)
        for x in (gitx, shx):
            os.symlink(x, os.path.join(path, os.path.basename(x)))
    if any(shutil.which(c, path=path) for c in ("py", "python3", "python")):
        return None
    return path, shx


def test_missing_python_warns_and_passes(repo, tmp_path):
    """python 을 못 찾으면 검사 수단이 없으므로 경고만 내고 통과시킨다 (16-hooks.md 의 git 훅 정책)."""
    got = _no_python_path(str(tmp_path))
    if not got:
        pytest.skip("python 없는 PATH 를 만들 수 없다")
    path, shx = got
    write(repo, "a.md", f"x {SMILE}\n")
    git(repo, "add", "a.md")
    env = dict(os.environ, PATH=path)
    p = subprocess.run([shx, os.path.join(repo, "tools", "hooks", "pre-commit")], cwd=repo, env=env,
                       capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 0, p.stderr
    assert "python 을 찾지 못해" in p.stderr


def test_install_check_without_hook_reports_missing(sandbox):
    git(sandbox.root, "init", "-q")
    p = install(sandbox.root, "--check")
    assert p.returncode == 1 and "설치 안 됨" in p.stdout
