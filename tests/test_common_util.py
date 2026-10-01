# _common.safe_relpath — Windows 에서 드라이브가 다른 경로(C: 와 D:)도 오류 없이 처리하는지
# 실측: CI(Windows)에서 저장소는 D:, 임시 폴더는 C: 라 os.path.relpath 가 ValueError 를 냈다(공통 계약 init 12건 실패).
import os
import sys

from conftest import REPO

sys.path.insert(0, os.path.join(REPO, "tools"))
import _common  # noqa: E402
import common_contract  # noqa: E402


def _cross_drive(*_a, **_k):
    raise ValueError("path is on mount 'C:', start on mount 'D:'")


def test_safe_relpath_falls_back_to_absolute(monkeypatch, tmp_path):
    p = str(tmp_path / "a" / "b.yaml")
    assert _common.safe_relpath(p, str(tmp_path)) == "a/b.yaml"
    monkeypatch.setattr(os.path, "relpath", _cross_drive)
    assert _common.safe_relpath(p, "D:/repo") == os.path.abspath(p).replace(os.sep, "/")


def test_contract_init_survives_cross_drive_paths(monkeypatch, tmp_path):
    from test_common_contract import usage_file
    usage = usage_file(tmp_path)
    monkeypatch.setattr(os.path, "relpath", _cross_drive)
    out = str(tmp_path / "c.yaml")
    assert common_contract.main(["--contract", out, "init", "--usage", usage, "--out", out]) == 0
