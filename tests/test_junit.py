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


def test_class_key_vitest_path_is_file_stem():
    # vitest classname 은 파일 경로다 - 확장자(tsx)로 묶이면 기준선 한 줄이 vitest 실패 전부를 덮는다(실측)
    assert _junit.class_key("src/layouts/Gnb.test.tsx") == "Gnb"
    assert _junit.class_key(r"src\features\x\ui\Screens.test.tsx") == "Screens"
    assert _junit.class_key("user/sample/real-backend-r1.spec.ts") == "real-backend-r1"
    assert _junit.class_key("sample-03-form.test.tsx") == "sample-03-form"
    # Java 는 종전대로
    assert _junit.class_key("com.example.user.FooTest") == "FooTest"
    assert _junit.class_key("p.B$In") == "B"


def test_vitest_failures_not_hidden_by_extension_entry(tmp_path):
    f = tmp_path / "v.xml"
    f.write_text('<testsuites><testsuite><testcase classname="src/a/A.test.tsx" name="x"><failure/></testcase>'
                 '<testcase classname="src/b/B.test.tsx" name="y"><failure/></testcase></testsuite></testsuites>',
                 encoding="utf-8")
    names = _junit.summarize([str(f)])["failed_names"]
    assert names == ["A.x", "B.y"]
    assert _junit.outside_baseline(names, ["tsx"]) == ["A.x", "B.y"]
    assert _junit.outside_baseline(names, ["A"]) == ["B.y"]
