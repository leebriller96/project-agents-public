# package_delivery.py - 납품 패키지가 문서·파이프라인 흔적만 걷어내고 코드·문자열은 그대로 두는지
import json
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


# ---------------------------------------------------------------------------
# 확장: 계정·날짜·해시·이모지, passthrough, 다듬기 캐시, 코드 불변 검증, 고아 브랜치
# ---------------------------------------------------------------------------
def _sc(**more):
    rules = pd.load_rules()
    rules.update(more)
    return pd.Scrubber(rules)


def test_account_date_commit_phrase_removed():
    sc = _sc(accounts=["devuser01"])
    src = "class A {\n  // 10/12 devuser01 이 commit 한 소스에 의거 - 조회 조건 추가\n}\n"
    out = pd.scrub_file("A.java", src, sc)[0]
    assert "devuser01" not in out and "commit" not in out
    assert out == "class A {\n  // 조회 조건 추가\n}\n"


def test_commit_hash_and_emoji_in_comment_removed():
    out = pd.scrub_file("A.java", "int a; // 기준 커밋 a1b2c3d4 \u2705 확인\n", _sc())[0]
    assert "a1b2c3d4" not in out and "\u2705" not in out
    assert "int a;" in out


def test_uuid_and_hex_literal_left_alone():
    out = pd.scrub_file("A.java", "// id 550e8400-e29b-41d4 와 0x1f2e3d4c\nint a;\n", _sc())[0]
    assert "550e8400-e29b-41d4" in out and "0x1f2e3d4c" in out


def test_account_left_in_string_is_denied(tmp_path):
    root = _repo(tmp_path, {"A.java": 'class A { String w = "devuser01"; }\n'})
    extra = tmp_path / "d.yaml"
    extra.write_text("accounts: [devuser01]\n", encoding="utf-8")
    assert pd.main(["--target", str(root), "--rules", str(extra), "--check"]) == 2


def test_emoji_in_code_string_is_denied(tmp_path):
    root = _repo(tmp_path, {"A.java": 'class A { String w = "ok \u2705"; }\n'})
    assert pd.main(["--target", str(root), "--check"]) == 2


def test_passthrough_kept_as_is_and_not_checked(tmp_path):
    root = _repo(tmp_path, {
        "docs/a.md": "# JD-1234 문서\n",
        "server/src/test/java/ATest.java": 'class ATest { String s = "RR-0001"; } // JD-1\n',
        "server/src/main/java/A.java": "class A {} // JD-1\n",
    })
    extra = tmp_path / "d.yaml"
    extra.write_text('keep: ["docs/*", "*/src/test/*"]\npassthrough: ["docs/*", "*/src/test/*"]\n', encoding="utf-8")
    out = tmp_path / "pkg"
    assert pd.main(["--target", str(root), "--rules", str(extra), "--out", str(out)]) == 0
    assert (out / "docs/a.md").read_text(encoding="utf-8") == "# JD-1234 문서\n"
    assert "JD-1" in (out / "server/src/test/java/ATest.java").read_text(encoding="utf-8")
    assert (out / "server/src/main/java/A.java").read_text(encoding="utf-8") == "class A {}\n"


def test_invariant_detects_code_change():
    files = {"A.java": (b"class A { int x = 1; } // a\n", False)}
    same = {"A.java": (b"class A { int x = 1; }\n", False)}
    diff = {"A.java": (b"class A { int x = 2; }\n", False)}
    assert pd.verify_invariant(files, same) == []
    assert pd.verify_invariant(files, diff) == ["A.java"]


def test_invariant_allows_only_ddl_comment_value_in_sql():
    orig = "CREATE TABLE t (a INT COMMENT '긴 설명 JD-1 입니다. 두 번째 문장.');\nINSERT INTO t VALUES ('x');\n"
    ok = "CREATE TABLE t (a INT COMMENT '짧은 설명');\nINSERT INTO t VALUES ('x');\n"
    bad = "CREATE TABLE t (a INT COMMENT '짧은 설명');\nINSERT INTO t VALUES ('y');\n"
    enc = lambda t: (t.encode("utf-8"), False)  # noqa: E731
    files = {"V1.sql": enc(orig)}
    assert pd.verify_invariant(files, {"V1.sql": enc(ok)}) == []
    assert pd.verify_invariant(files, {"V1.sql": enc(bad)}) == ["V1.sql"]


def test_polish_candidates_then_cache_applied(tmp_path):
    long_ddl = "신고 확인 비밀번호 해시. 실명과 익명 모두 저장하며 잠금 계수와 함께 쓴다. 평문은 남기지 않는다."
    sql = f"CREATE TABLE t (pw VARCHAR(100) COMMENT '{long_ddl}', b INT COMMENT '사용여부');\n"
    root = _repo(tmp_path, {"server/db/migration/V1__t.sql": sql})
    out1 = tmp_path / "p1"
    assert pd.main(["--target", str(root), "--out", str(out1)]) == 0
    cand = [json.loads(x) for x in (tmp_path / "p1.polish.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(cand) == 1 and cand[0]["kind"] == "ddl" and cand[0]["original"] == long_ddl
    cache = tmp_path / "cache.jsonl"
    cache.write_text(json.dumps({**cand[0], "new": "신고 확인 비밀번호 해시"}, ensure_ascii=False) + "\n", encoding="utf-8")
    out2 = tmp_path / "p2"
    assert pd.main(["--target", str(root), "--out", str(out2), "--cache", str(cache), "--require-polish"]) == 0
    got = (out2 / "server/db/migration/V1__t.sql").read_text(encoding="utf-8")
    assert "COMMENT '신고 확인 비밀번호 해시'" in got and "COMMENT '사용여부'" in got
    summary = json.loads((tmp_path / "p2.summary.json").read_text(encoding="utf-8"))
    assert summary["polish_hits"] == 1 and summary["flyway_changed"] == ["server/db/migration/V1__t.sql"]


def test_require_polish_blocks_when_pending(tmp_path):
    sql = "CREATE TABLE t (a INT COMMENT '" + "가" * 60 + "');\n"
    root = _repo(tmp_path, {"V1.sql": sql})
    assert pd.main(["--target", str(root), "--out", str(tmp_path / "p"), "--require-polish"]) == 5
    assert not (tmp_path / "p").exists()


def test_invalid_cache_comment_not_applied(tmp_path):
    body = "\n".join([" * 근거 서술 AS-IS 원본 결정"] * 10)
    src = f"/**\n{body}\n */\nclass A {{}}\n"
    root = _repo(tmp_path, {"A.java": src})
    out1 = tmp_path / "p1"
    assert pd.main(["--target", str(root), "--out", str(out1)]) == 0
    cand = json.loads((tmp_path / "p1.polish.jsonl").read_text(encoding="utf-8").splitlines()[0])
    cache = tmp_path / "c.jsonl"
    cache.write_text(json.dumps({**cand, "new": "/** 코드 깨짐 */ int x; /* */"}, ensure_ascii=False) + "\n", encoding="utf-8")
    out2 = tmp_path / "p2"
    assert pd.main(["--target", str(root), "--out", str(out2), "--cache", str(cache)]) == 0
    assert "int x" not in (out2 / "A.java").read_text(encoding="utf-8")


def test_orphan_branch_snapshot(tmp_path):
    root = _repo(tmp_path, {"A.java": "class A {} // JD-1\n"})
    wt = tmp_path / "pkg-wt"
    assert pd.main(["--target", str(root), "--branch", "delivery-pkg", "--worktree", str(wt)]) == 0
    log = subprocess.run(["git", "log", "--format=%s", "delivery-pkg"], cwd=root, capture_output=True, text=True,
                         encoding="utf-8").stdout.strip().splitlines()
    assert len(log) == 1 and log[0].startswith("package: HEAD ")
    roots = subprocess.run(["git", "rev-list", "--max-parents=0", "delivery-pkg"], cwd=root, capture_output=True,
                           text=True).stdout.split()
    assert len(roots) == 1                                    # 고아: 원본 이력과 이어지지 않는다
    assert (wt / "A.java").read_text(encoding="utf-8") == "class A {}\n"
    # 두 번째: 바뀐 것이 없으면 커밋하지 않는다
    assert pd.main(["--target", str(root), "--branch", "delivery-pkg", "--worktree", str(wt)]) == 0
    assert subprocess.run(["git", "rev-list", "--count", "delivery-pkg"], cwd=root, capture_output=True,
                          text=True).stdout.strip() == "1"


def test_orphan_branch_refuses_protected_and_inside_target(tmp_path):
    import pytest
    root = _repo(tmp_path, {"A.java": "class A {}\n"})
    with pytest.raises(SystemExit):
        pd.main(["--target", str(root), "--branch", "main", "--worktree", str(tmp_path / "w")])
    with pytest.raises(SystemExit):
        pd.main(["--target", str(root), "--branch", "pkg", "--worktree", str(root / "w")])


def test_gitignore_hash_comment_scrubbed():
    out = pd.scrub_file(".gitignore", "# 빌드 산출물 (JD-1)\n/dist\n", _sc())[0]
    assert out == "# 빌드 산출물\n/dist\n"


def test_deny_skip_exempts_functional_emoji(tmp_path):
    root = _repo(tmp_path, {"src/strip.ts": 'export const RX = /[\u2705]/g;\n'})
    extra = tmp_path / "d.yaml"
    extra.write_text('deny_skip: ["src/strip.ts"]\n', encoding="utf-8")
    assert pd.main(["--target", str(root), "--check"]) == 2
    assert pd.main(["--target", str(root), "--rules", str(extra), "--check"]) == 0


def test_js_regex_literal_with_backtick_does_not_hide_later_comments():
    src = ('const FENCE_RE = /^(`{3,}|~{3,})/;\n'
           'const a = 4 / 2; // 나눗셈 (JD-1)\n'
           '/** 설명 (RR-0001) */\n'
           'const t = `x // 문자열 JD-2`;\n')
    out = pd.scrub_file("a.ts", src, _sc())[0]
    assert "/^(`{3,}|~{3,})/" in out
    assert "// 나눗셈\n" in out and "/** 설명 */" in out
    assert "`x // 문자열 JD-2`" in out                    # 템플릿 문자열은 그대로


def test_empty_javadoc_tag_left_by_ref_removal_is_cleaned():
    out = pd.scrub_file("A.java", "/** 원본 {@code PolicyController.java:12}·{@code a.ftl:3} 와 같다. */\nclass A {}\n", _sc())[0]
    assert "{@code }" not in out and "{@code" not in out
    assert "원본" in out and "같다" in out


def test_cache_reused_when_file_moves(tmp_path):
    long_ddl = "가" * 60
    root = _repo(tmp_path, {"new/db/migration/V1__t.sql": f"CREATE TABLE t (a INT COMMENT '{long_ddl}');\n"})
    cache = tmp_path / "c.jsonl"
    entry = {"path": "old/db/migration/V1__t.sql", "kind": "ddl", "sha1": pd.sha1(long_ddl), "new": "짧은 설명"}
    cache.write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")
    out = tmp_path / "p"
    assert pd.main(["--target", str(root), "--out", str(out), "--cache", str(cache), "--require-polish"]) == 0
    assert "COMMENT '짧은 설명'" in (out / "new/db/migration/V1__t.sql").read_text(encoding="utf-8")
