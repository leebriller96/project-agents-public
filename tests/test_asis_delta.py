# asis_delta.py — AS-IS 현행화 차이를 의미 단위(메서드·statement·파일)로 뽑고, 형식만 다른 것과 경로 이동을 거르는지
import os

import yaml


def _w(root, rel, text, enc="utf-8"):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding=enc, newline="") as f:
        f.write(text)


JAVA_OLD = """package a.b;

public class FooService {
    private int n;

    public String keep(String s) {
        return s;
    }

    public String change(String s) {
        return s + "1";
    }
}
"""

JAVA_NEW = """package a.b;

public class FooService {
    private int n;

    public String keep(String s) {
        return s;
    }

    public String change(String s) {
        return s + "2";
    }

    public void added() {
    }
}
"""

MAPPER_OLD = """<mapper namespace="foo">
  <select id="list">SELECT A FROM T</select>
  <select id="same">SELECT 1 FROM DUAL</select>
</mapper>
"""

MAPPER_NEW = """<mapper namespace="foo">
  <select id="list">SELECT A, B FROM T</select>
  <select id="same">SELECT 1   FROM DUAL</select>
</mapper>
"""


def test_units_moves_and_format_only(sandbox, tmp_path):
    old, new, tobe = str(tmp_path / "old"), str(tmp_path / "new"), str(tmp_path / "tobe")
    _w(old, "src/a/b/FooService.java", JAVA_OLD)
    _w(new, "src/a/b/FooService.java", JAVA_NEW)
    _w(old, "src/m/foo.xml", MAPPER_OLD)
    _w(new, "src/m/foo.xml", MAPPER_NEW)
    # 인코딩·줄바꿈만 다른 파일은 차이가 아니다
    _w(old, "web/view.ftl", "<p>안녕</p>\n", enc="cp949")
    _w(new, "web/view.ftl", "<p>안녕</p>\r\n")
    # 패키지 경로만 바뀐 파일은 이동으로 묶는다
    body = "public class Ctl {\n    public void a() {\n        int x = 1;\n    }\n}\n"
    _w(old, "src/old/pkg/Ctl.java", "package old.pkg;\n\n" + body)
    _w(new, "src/pkg/Ctl.java", "package pkg;\n\n" + body)
    _w(tobe, "server/FooTobe.java", "class X { void change() { FooService f; } }\n")
    _w(tobe, "docs/analysis.md", "FooService change\n")
    _w(sandbox.root, "slices.yaml", yaml.safe_dump({"slices": [
        {"id": "foo-slice", "asis": {"programs": ["FooService.java"], "namespaces": ["foo"]}}]}))
    out = str(tmp_path / "out")
    sandbox.run("asis_delta.py", "--old", old, "--new", new, "--target", tobe,
                "--slices", os.path.join(sandbox.root, "slices.yaml"), "--out", out, check=0)
    data = yaml.safe_load(open(os.path.join(out, "asis_delta.yaml"), encoding="utf-8"))
    f = data["summary"]["files"]
    assert f["format_only"] == 1 and f["moved"] == 1 and f["modified"] == 2
    units = {(u["file"], u["unit"]): u for u in data["units"]}
    assert ("src/a/b/FooService.java", "FooService#change(String)") in units
    assert ("src/a/b/FooService.java", "FooService#added()") in units
    assert ("src/a/b/FooService.java", "FooService#keep(String)") not in units
    assert ("src/m/foo.xml", "foo.list") in units
    assert ("src/m/foo.xml", "foo.same") not in units          # 공백만 다른 statement
    ch = units[("src/a/b/FooService.java", "FooService#change(String)")]
    assert ch["slices"] == ["foo-slice"] and ch["tobe_hits"] == ["server/FooTobe.java"]   # docs/ 는 후보에서 뺀다
    assert units[("src/m/foo.xml", "foo.list")]["slices"] == ["foo-slice"]
    moved = [u for u in data["units"] if u["file"] == "src/pkg/Ctl.java"]
    assert moved and all(u["change"] == "moved" for u in moved)
    assert os.path.isfile(os.path.join(out, "ASIS_DELTA.md"))


def test_set_verdict_and_carry_on_regenerate(sandbox, tmp_path):
    old, new, out = str(tmp_path / "old"), str(tmp_path / "new"), str(tmp_path / "out")
    _w(old, "src/m/foo.xml", MAPPER_OLD)
    _w(new, "src/m/foo.xml", MAPPER_NEW)
    _w(sandbox.root, "slices.yaml", yaml.safe_dump({"slices": []}))
    args = ("asis_delta.py", "--old", old, "--new", new, "--target", str(tmp_path),
            "--slices", os.path.join(sandbox.root, "slices.yaml"), "--out", out)
    sandbox.run(*args, check=0)
    path = os.path.join(out, "asis_delta.yaml")
    uid = next(u["id"] for u in yaml.safe_load(open(path, encoding="utf-8"))["units"] if u["unit"] == "foo.list")
    sandbox.run("asis_delta.py", "set", uid, "--verdict", "applied", "--note", "근거 커밋", "--out", out, check=0)
    sandbox.run("asis_delta.py", "set", "AD-9999", "--verdict", "applied", "--out", out, check=1)
    # 판정 값은 정해진 것만 받는다
    sandbox.run("asis_delta.py", "set", uid, "--verdict", "done", "--out", out, check=2)
    assert "| applied |" in open(os.path.join(out, "ASIS_DELTA.md"), encoding="utf-8").read()
    # 다시 생성해도 (파일, 단위) 기준으로 판정·메모를 이어받는다
    sandbox.run(*args, check=0)
    u = next(u for u in yaml.safe_load(open(path, encoding="utf-8"))["units"] if u["unit"] == "foo.list")
    assert u["verdict"] == "applied" and u["note"] == "근거 커밋"
