# _junit 집계·기준선 읽기 시험
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import _junit  # noqa: E402


def test_load_baseline_from_results_folder(tmp_path):
    # 기준선으로 결과 사본 폴더를 적어도 그 안의 실패 testcase 이름을 기준선으로 쓴다(실측: 폴더를 열다 PermissionError)
    d = tmp_path / "base"
    (d / "sub").mkdir(parents=True)
    (d / "sub" / "TEST-a.xml").write_text(
        '<testsuite><testcase classname="p.A" name="x"><failure/></testcase>'
        '<testcase classname="p.A" name="y"/><testcase classname="p.B$In" name="z"><error/></testcase></testsuite>',
        encoding="utf-8")
    assert _junit.load_baseline(str(d)) == ["A.x", "B.z"]
