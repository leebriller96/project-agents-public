# 테스트 공용 픽스처 — 저장소의 tools/·templates/ 를 임시 폴더에 복사한 격리 환경(sandbox)을 만든다.
# 도구들은 import 시점에 config/project.yaml 을 읽어 경로를 정하므로, 실제 저장소를 건드리지 않도록
# 매 테스트마다 별도 복사본에서 명령행으로 실행한다.
import json
import os
import shutil
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(REPO, "tests", "fixtures")


class Sandbox:
    """격리된 project-agents 복사본."""

    def __init__(self, root, project="t"):
        self.root = str(root)
        self.project = project
        shutil.copytree(os.path.join(REPO, "tools"), os.path.join(self.root, "tools"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(os.path.join(REPO, "templates"), os.path.join(self.root, "templates"))
        os.makedirs(os.path.join(self.root, "config"))
        self.target = os.path.join(self.root, "target")
        os.makedirs(self.target)
        self.write_config()

    def write_config(self, extra=""):
        with open(os.path.join(self.root, "config", "project.yaml"), "w", encoding="utf-8") as f:
            f.write(f"project:\n  name: {self.project}\n  target_dir: target\n{extra}")

    @property
    def ws(self):
        return os.path.join(self.root, "workspace", self.project)

    def cmd(self, tool, *args):
        return [sys.executable, os.path.join(self.root, "tools", tool), *args]

    def run(self, tool, *args, check=None):
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        p = subprocess.run(self.cmd(tool, *args), cwd=self.root, capture_output=True, text=True,
                           encoding="utf-8", env=env)
        if check is not None:
            assert p.returncode == check, f"exit={p.returncode}\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}"
        return p

    def popen(self, tool, *args):
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        return subprocess.Popen(self.cmd(tool, *args), cwd=self.root, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env)

    def write_report(self, name, meta, body="# 레포트\n"):
        d = os.path.join(self.ws, "reports")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body + "\n<!-- pa-meta:start\n" + json.dumps(meta, ensure_ascii=False, indent=2)
                    + "\npa-meta:end -->\n")
        return path


@pytest.fixture
def sandbox(tmp_path):
    return Sandbox(tmp_path)


def dev_meta(**over):
    """2단계 완료 레포트의 최소 pa-meta."""
    meta = {
        "schema": 1, "stage": 2, "slice": "notice", "iteration": 1, "agent": "backend-developer",
        "result": "done", "started_at": "2026-09-28 10:00", "finished_at": "2026-09-28 11:00",
        "repo": {"dir": "target", "branch": "main", "head": "abcdef1", "base": "", "dirty": False,
                 "changed_files": []},
        "gates": [
            {"kind": "build", "command": "./gradlew build", "exit_code": 0, "executed_at": "2026-09-28 10:50"},
            {"kind": "test", "command": "./gradlew test", "exit_code": 0, "executed_at": "2026-09-28 10:55",
             "axis": "unit", "test_count": 12, "failures": 0, "skipped": 0},
        ],
        "open_items": [], "rr_ids": [], "common_candidates": [], "not_executed": [], "risk_surface": [],
        "cost": {"duration_min": 60, "tool_calls": 40, "tokens_k": 100},
    }
    meta.update(over)
    return meta
