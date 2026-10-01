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
