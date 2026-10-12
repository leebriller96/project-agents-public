# package_delivery.py - 납품 패키지가 문서·파이프라인 흔적만 걷어내고 코드·문자열은 그대로 두는지
import os
import subprocess
import sys

from conftest import REPO

sys.path.insert(0, os.path.join(REPO, "tools"))
import package_delivery as pd  # noqa: E402

SC = pd.Scrubber(pd.load_rules())


def scrub(path, text):
    return pd.scrub_file(path, text, SC)[0]


def test_java_comment_markers_removed_but_strings_kept():
    src = ('class A {\n'
           '  String s = "JD-1141 // 문자열"; // 신청자 조건 (JD-1141, RR-0347)\n'
           '  // RR-0376\n'
           '  int x = 1;\n'
           '}\n')
    out = scrub("A.java", src)
    assert '"JD-1141 // 문자열"' in out                    # 문자열은 그대로
    assert "// 신청자 조건\n" in out                         # 업무 설명은 남는다
    assert "RR-0376" not in out and "  // \n" not in out     # 표지만 있던 줄은 줄째 지운다
    assert "int x = 1;" in out


def test_javadoc_lines_and_file_line_refs():
    src = ('/**\n'
           ' * 삭제 - AS-IS {@code t} (PolicyAnyChangeController.java:479-486).\n'
           ' * 근거: JD-1141 · RR-0347 · F-002\n'
           ' * [의미차이:AUTHZ_OWNER] 로그인 사번 조건.\n'
           ' * slice: docsecu-manage\n'
           ' * svc SKIP (AU-D-13).\n'
           ' */\n')
    out = scrub("A.java", src)
    assert "* 삭제 - AS-IS {@code t}.\n" in out
    assert "근거" not in out and "slice" not in out
    assert "* 로그인 사번 조건." in out
    assert "AU-D-13" in out                                  # 남의 번호 안쪽은 건드리지 않는다


def test_comment_with_only_markers_removed_entirely():
    out = scrub("A.java", "int a;\n/** JD-1230 · RR-0347 */\nint b;\n")
    assert out == "int a;\nint b;\n"


def test_xml_and_sql_comments():
    xml = ('<select id="a"> <!-- 미회수 판정 (JD-1273, AuthRevokedMapper.xml:904-908) -->\n'
           "  SELECT 'JD-1' FROM t -- [의미차이:CATCH_UP] 종료일 조건\n"
           '  /* RR-0376 */\n'
           '</select>\n')
    out = scrub("m.xml", xml)
    assert "<!-- 미회수 판정 -->" in out
    assert "'JD-1'" in out                                   # SQL 문자열은 그대로
    assert "-- 종료일 조건" in out
    assert "RR-0376" not in out


def test_yaml_comments_and_quoted_hash():
    out = scrub("a.yml", 'a: b # 비밀값 (JD-1151)\n# JD-1151\nc: "x # JD-1"\n')
    assert out == 'a: b # 비밀값\nc: "x # JD-1"\n'


def test_scrub_strings_keeps_code_punctuation():
    text = "  COMMENT '권한 회수 처리 일시 (D-9 JD-1148 - 마친 시각)';\n"
    new, _ = pd.scrub_file("V1.sql", text, SC, whole=True)
    assert new == "  COMMENT '권한 회수 처리 일시 (마친 시각)';\n"   # 문장 끝 ';' 는 남는다


def _repo(tmp_path, files):
    root = tmp_path / "src"
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"]):
        subprocess.run(["git", *args], cwd=root, check=True)
    return root


def test_package_excludes_docs_and_tests_and_writes_changes(tmp_path):
    root = _repo(tmp_path, {
        "README.md": "# 문서\n",
        "docs/api/a.yaml": "x: 1\n",
        "server/user/src/main/java/A.java": "class A { // 설명 (JD-1)\n}\n",
        "server/user/src/test/java/ATest.java": "class ATest {}\n",
    })
    out = tmp_path / "pkg"
    assert pd.main(["--target", str(root), "--out", str(out)]) == 0
    assert (out / "server/user/src/main/java/A.java").read_text(encoding="utf-8") == "class A { // 설명\n}\n"
    assert not (out / "README.md").exists() and not (out / "docs").exists()
    assert not (out / "server/user/src/test").exists()
    assert (tmp_path / "pkg.changes.txt").exists()


def test_package_refuses_when_marker_left_in_code_string(tmp_path):
    root = _repo(tmp_path, {"A.java": 'class A { String m = "실패(RR-0358)"; }\n'})
    out = tmp_path / "pkg"
    assert pd.main(["--target", str(root), "--out", str(out)]) == 2
    assert not out.exists()
