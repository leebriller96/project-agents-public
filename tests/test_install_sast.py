"""tools/install_sast.py - 네트워크 없이 확인되는 부분만 시험한다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import install_sast as m  # noqa: E402


def test_os_arch_names_match_release_assets():
    osname, arch = m._os_arch()
    assert osname in ("windows", "darwin", "linux")
    assert arch in ("amd64", "arm64")


def test_version_returns_none_for_missing_tool():
    assert m._version(["no-such-tool-for-install-sast-test", "--version"]) is None


def test_check_reports_all_three_tools(monkeypatch):
    monkeypatch.setattr(m, "_version", lambda cmd: None)
    monkeypatch.setattr(m.shutil, "which", lambda name: None)
    assert m.check() == {"semgrep": None, "gitleaks": None, "osv-scanner": None}
