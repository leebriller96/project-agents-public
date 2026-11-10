"""백엔드 lint 설정 감지(tools/backend_lint.py)와 2단계 게이트 훅(backend-lint) 시험."""
import os
import sys

from conftest import REPO

sys.path.insert(0, os.path.join(REPO, "tools"))
import backend_lint  # noqa: E402
import gate  # noqa: E402

POM_CHECKSTYLE = """<project><build><plugins>
  <plugin><groupId>org.apache.maven.plugins</groupId><artifactId>maven-checkstyle-plugin</artifactId></plugin>
</plugins></build></project>
"""
POM_COMMENTED = """<project><build><plugins>
  <!-- <plugin><artifactId>maven-pmd-plugin</artifactId></plugin> -->
</plugins></build></project>
"""


def _write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def test_detect_maven_gradle_and_skips(tmp_path):
    root = str(tmp_path)
    assert backend_lint.detect(root) == []
    _write(root, "server/pom.xml", POM_COMMENTED)                     # 주석 안 플러그인은 세지 않는다
    _write(root, "node_modules/x/pom.xml", POM_CHECKSTYLE)            # 건너뛰는 폴더
    assert backend_lint.detect(root) == []
    _write(root, "mvnw", "")
    _write(root, "server/user/pom.xml", POM_CHECKSTYLE)
    _write(root, "server/admin/pom.xml", POM_CHECKSTYLE)              # 같은 도구는 한 번만
    found = backend_lint.detect(root)
    assert [(f["tool"], f["build"], f["command"]) for f in found] == [("checkstyle", "maven", "./mvnw -q checkstyle:check")]
    _write(root, "api/build.gradle.kts", 'plugins {\n  id("com.diffplug.spotless") version "6.25.0"\n  checkstyle\n}\n')
    tools = {(f["tool"], f["build"]) for f in backend_lint.detect(root)}
    assert tools == {("checkstyle", "maven"), ("spotless", "gradle"), ("checkstyle", "gradle")}


def _hook(target_dir, stage=2, gates=None, not_executed=None):
    meta = {"stage": stage, "gates": gates or [], "not_executed": not_executed or []}
    ctx = {"report": "r.md", "meta": meta, "meta_error": None, "stage": stage, "slice": "board", "unit": None,
           "target_dir": target_dir}
    return gate.hook_backend_lint(ctx)


def test_hook_skip_fail_warn_pass(tmp_path):
    root = str(tmp_path)
    assert _hook(root)["result"] == "SKIPPED"                          # 설정 없음
    _write(root, "pom.xml", POM_CHECKSTYLE)
    assert _hook(root, stage=4)["result"] == "SKIPPED"                 # 2단계만 본다
    assert _hook(root)["result"] == "FAIL"                             # 설정 있는데 lint 기록 없음
    build = {"kind": "build", "command": "./mvnw -q verify", "exit_code": 0}
    assert _hook(root, gates=[build])["result"] == "FAIL"
    warned = _hook(root, gates=[build], not_executed=["backend lint - 기존 위반 2천 건, OI-0001"])
    assert warned["result"] == "WARN"
    lint = {"kind": "lint", "command": "mvn -q checkstyle:check", "exit_code": 0}
    assert _hook(root, gates=[build, lint])["result"] == "PASS"
    assert "backend-lint" in gate.PROFILES["dev"]
