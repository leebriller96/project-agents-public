# tools/backup.py — git 에 없는 프로젝트 자산을 잃지 않고 되살릴 수 있는지
import json
import os
import zipfile


def _seed(sandbox):
    for rel, text in [("state.yaml", "project: t\n"),
                      ("knowledge/PROJECT_BRIEF.md", "# 요약\n## 12. 결정 사항\n"),
                      ("00_inputs/요구사항.txt", "원문\n"),
                      ("open-items.yaml.lock", "123")]:
        p = os.path.join(sandbox.ws, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)


def _dest(tmp_path, name="bk"):
    # sandbox 루트가 tmp_path 자체이므로 그 바깥(형제 폴더)을 백업 위치로 쓴다
    return str(tmp_path.parent / f"{tmp_path.name}-{name}")


def _only_zip(dest):
    d = os.path.join(dest, "t")
    files = [f for f in os.listdir(d) if f.endswith(".zip")]
    assert len(files) == 1, files
    return os.path.join(d, files[0])


def test_create_verify_restore_roundtrip(sandbox, tmp_path):
    _seed(sandbox)
    dest = _dest(tmp_path)
    sandbox.run("backup.py", "create", "--dest", dest, check=0)
    z = _only_zip(dest)
    with zipfile.ZipFile(z) as zf:
        names = set(zf.namelist())
    assert "config/project.yaml" in names
    assert "workspace/t/knowledge/PROJECT_BRIEF.md" in names
    assert "workspace/t/00_inputs/요구사항.txt" in names
    assert not any(n.endswith(".lock") for n in names)   # 잠금 파일은 백업하지 않는다
    sandbox.run("backup.py", "verify", z, check=0)

    # 잃어버린 뒤 복원
    brief = os.path.join(sandbox.ws, "knowledge", "PROJECT_BRIEF.md")
    os.remove(brief)
    sandbox.run("backup.py", "restore", z, check=0)
    with open(brief, encoding="utf-8") as f:
        assert "결정 사항" in f.read()


def test_no_inputs_and_keep(sandbox, tmp_path):
    _seed(sandbox)
    dest = _dest(tmp_path)
    sandbox.run("backup.py", "create", "--dest", dest, "--no-inputs", "--keep", "1", check=0)
    sandbox.run("backup.py", "create", "--dest", dest, "--no-inputs", "--keep", "1", check=0)
    z = _only_zip(dest)   # 두 번째 생성에서 첫 백업이 정리된다
    with zipfile.ZipFile(z) as zf:
        assert not any("00_inputs" in n for n in zf.namelist())


def test_dest_inside_repo_is_refused(sandbox):
    _seed(sandbox)
    p = sandbox.run("backup.py", "create", "--dest", os.path.join(sandbox.root, "backups"))
    assert p.returncode == 2
    assert "저장소 안" in p.stderr


def test_dest_from_config(sandbox, tmp_path):
    _seed(sandbox)
    dest = _dest(tmp_path, "cfg").replace("\\", "/")
    sandbox.write_config(f"backup:\n  dir: {dest}\n")
    sandbox.run("backup.py", "create", check=0)
    assert _only_zip(dest)


def test_tampered_backup_fails_verify_and_restore(sandbox, tmp_path):
    _seed(sandbox)
    dest = _dest(tmp_path)
    sandbox.run("backup.py", "create", "--dest", dest, check=0)
    z = _only_zip(dest)
    bad = _dest(tmp_path, "bad.zip")
    with zipfile.ZipFile(z) as src, zipfile.ZipFile(bad, "w") as out:
        for n in src.namelist():
            data = src.read(n)
            if n.endswith("state.yaml"):
                data = b"project: changed\n"
            out.writestr(n, data)
    assert sandbox.run("backup.py", "verify", bad).returncode == 1
    assert sandbox.run("backup.py", "restore", bad).returncode == 1


def test_restore_does_not_overwrite_changed_files_without_force(sandbox, tmp_path):
    _seed(sandbox)
    dest = _dest(tmp_path)
    sandbox.run("backup.py", "create", "--dest", dest, check=0)
    z = _only_zip(dest)
    state = os.path.join(sandbox.ws, "state.yaml")
    with open(state, "w", encoding="utf-8") as f:
        f.write("project: t\niteration: 2\n")
    p = sandbox.run("backup.py", "restore", z)
    assert p.returncode == 1 and "state.yaml" in p.stdout
    with open(state, encoding="utf-8") as f:
        assert "iteration: 2" in f.read()   # 그대로다
    sandbox.run("backup.py", "restore", z, "--force", check=0)
    with open(state, encoding="utf-8") as f:
        assert f.read() == "project: t\n"


def test_restore_rejects_path_outside_repo(sandbox, tmp_path):
    evil = _dest(tmp_path, "evil.zip")
    payload = b"x"
    import hashlib
    manifest = {"project": "t", "files": [{"path": "../outside.txt", "size": 1,
                                           "sha256": hashlib.sha256(payload).hexdigest()}]}
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("../outside.txt", payload)
        z.writestr("MANIFEST.json", json.dumps(manifest))
    p = sandbox.run("backup.py", "restore", evil)
    assert p.returncode == 1
    assert not os.path.exists(os.path.join(os.path.dirname(sandbox.root), "outside.txt"))
