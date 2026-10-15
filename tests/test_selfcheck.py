# 저장소 문서 ↔ 실제 파일 정합성 — README·설정·스킬이 서로 어긋나면 CI 에서 실패한다
import os
import subprocess
import sys

from conftest import REPO


def test_repository_is_consistent():
    p = subprocess.run([sys.executable, os.path.join(REPO, "tools", "selfcheck.py")], cwd=REPO,
                       capture_output=True, text=True, encoding="utf-8",
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    assert p.returncode == 0, p.stdout + p.stderr


def test_missing_pipeline_core_section_reference_is_caught(tmp_path):
    import shutil
    root = tmp_path / "repo"
    shutil.copytree(REPO, root, ignore=shutil.ignore_patterns(".git", "workspace", "__pycache__"))
    agent = root / ".claude" / "agents" / "backend-developer.md"
    agent.write_text(agent.read_text(encoding="utf-8") + "\n규칙은 pipeline-core §99 를 따른다.\n", encoding="utf-8")
    (root / ".claude" / "skills" / "pipeline-core" / "sections" / "18-locked-spec.md").unlink()
    p = subprocess.run([sys.executable, str(root / "tools" / "selfcheck.py")], cwd=root, capture_output=True,
                       text=True, encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    assert p.returncode == 1
    assert "§99" in p.stdout and "sections/18-locked-spec.md" in p.stdout
