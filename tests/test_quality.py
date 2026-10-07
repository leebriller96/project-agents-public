# quality.py — 상품화 품질 규칙이 정확히(오탐·누락 없이) 그리고 결정적으로 동작하는지
import json
import os
import shutil
import subprocess
import sys

from conftest import FIXTURES, REPO

sys.path.insert(0, os.path.join(REPO, "tools"))
import quality  # noqa: E402

GOOD = os.path.join(FIXTURES, "quality", "good")
BAD = os.path.join(FIXTURES, "quality", "bad")


def run(*args, cwd=REPO):
    return subprocess.run([sys.executable, os.path.join(REPO, "tools", "quality.py"), *args], cwd=cwd,
                          capture_output=True, text=True, encoding="utf-8",
                          env=dict(os.environ, PYTHONIOENCODING="utf-8"))


def test_good_fixture_has_no_findings():
    res = quality.scan(GOOD)
    assert res["findings"] == [], res["findings"]
    assert all(v == 100.0 for v in res["coverage"].values()), res["coverage"]
    assert run(GOOD, "--strict").returncode == 0


def test_bad_fixture_hits_every_rule_exactly_once():
    res = quality.scan(BAD)
    # 이모지는 저장소 파일에 둘 수 없으므로(이모지 금지 원칙) 별도 테스트에서 실행 시점에 만든다
    expected = {rule: 1 for rule in sorted(quality.RULES) if rule != "NO-EMOJI"}
    assert res["by_rule"] == expected, res["by_rule"]
    assert res["counts"] == {"critical": 2, "major": 8, "minor": 4}
    assert run(BAD).returncode == 1


def test_output_is_deterministic_regardless_of_cwd(tmp_path):
    a = run(BAD, "--format", "json").stdout
    b = run(BAD, "--format", "json").stdout
    c = run(os.path.relpath(BAD, REPO), "--format", "json").stdout
    d = run(BAD, "--format", "json", cwd=str(tmp_path)).stdout
    assert a == b
    # 경로 표기가 달라도 결과(발견 목록·통계)는 같다
    assert json.loads(a)["findings"] == json.loads(c)["findings"] == json.loads(d)["findings"]


def test_files_mode_checks_only_given_files_and_skips_project_rules():
    res = quality.scan(BAD, ["backend/src/main/resources/mapper/NoticeMapper.xml"])
    assert res["mode"] == "files"
    assert sorted(res["by_rule"]) == ["MAPPER-DOC-FILE", "MAPPER-DOC-STMT"]


def test_ignore_comment_suppresses_rule(tmp_path):
    shutil.copytree(BAD, tmp_path / "p")
    svc = tmp_path / "p/backend/src/main/java/com/ex/notice/NoticeService.java"
    text = svc.read_text(encoding="utf-8").replace(
        '        System.out.println("등록: " + id);',
        '        System.out.println("등록: " + id); // quality:ignore JAVA-CONSOLE — 로컬 진단용')
    svc.write_text(text, encoding="utf-8")
    assert "JAVA-CONSOLE" not in quality.scan(str(tmp_path / "p"))["by_rule"]


def test_multiline_annotation_and_signature_are_understood(tmp_path):
    src = tmp_path / "p/src/main/java/x/OrderService.java"
    src.parent.mkdir(parents=True)
    src.write_text('''package x;

/** 주문 서비스. */
@org.springframework.stereotype.Service
@lombok.extern.slf4j.Slf4j
public class OrderService {

    /**
     * 주문한다.
     *
     * @param a 수량
     */
    @org.springframework.transaction.annotation.Transactional(
            readOnly = false,
            timeout = 3)
    public void order(
            int a) {
        log.info("주문 수량={}", a);
    }

    public String name() { return "x"; }
}
''', encoding="utf-8")
    res = quality.scan(str(tmp_path / "p"), [str(src)])
    assert [(f["rule"], f["detail"]) for f in res["findings"]] == [("JAVA-DOC-METHOD", "OrderService.name()")]


def test_sensitive_word_inside_message_text_is_not_flagged(tmp_path):
    src = tmp_path / "p/src/main/java/x/AuthService.java"
    src.parent.mkdir(parents=True)
    src.write_text('''package x;

/** 인증 서비스. */
@lombok.extern.slf4j.Slf4j
public class AuthService {

    /** 로그인. @param userId 사용자 */
    public void login(String userId) {
        log.warn("password 불일치 userId={}", userId);
    }
}
''', encoding="utf-8")
    assert quality.scan(str(tmp_path / "p"), [str(src)])["findings"] == []


def test_rules_listing_covers_catalog():
    out = run("--rules").stdout
    for rule in quality.RULES:
        assert rule in out


def test_role_is_not_inferred_from_strings_or_comments(tmp_path):
    """로그 문구·주석 속 '@Mapper' 로 역할을 오판하지 않는다 (mybatis-spring-boot-starter 실측 오탐)."""
    src = tmp_path / "p/src/main/java/x/AutoConfig.java"
    src.parent.mkdir(parents=True)
    src.write_text('''package x;

/** 자동 설정. {@code @Service} 가 아니다. */
public class AutoConfig {
    private static final org.slf4j.Logger logger = org.slf4j.LoggerFactory.getLogger(AutoConfig.class);

    public void register() {
        logger.debug("Searching for mappers annotated with @Mapper");
    }
}
''', encoding="utf-8")
    assert quality.scan(str(tmp_path / "p"), [str(src)])["findings"] == []


# 이모지 문자는 소스에 직접 쓰지 않고 escape 로 만든다 (이 저장소 파일에도 이모지 금지가 적용된다)
SMILE = "\U0001F600"
CHECK = "\u2705"
WARN = "\u26a0\ufe0f"


def test_emoji_is_critical_everywhere_including_tests_and_config(tmp_path):
    root = tmp_path / "p"
    files = {
        "backend/src/main/java/x/A.java": f"package x;\n/** 서비스 {CHECK} */\npublic class A {{}}\n",
        "backend/src/main/resources/mapper/AMapper.xml":
            f'<?xml version="1.0"?>\n<!-- 머리 -->\n<mapper namespace="x"><!-- mybatis -->\n'
            f'    <!-- 조회 {WARN} -->\n    <select id="a">SELECT 1</select>\n</mapper>\n',
        "backend/src/main/resources/application.yml": f"# 운영 설정 {SMILE}\nserver:\n  port: 8080\n",
        "backend/src/main/resources/db/migration/V1__a.sql":
            f"CREATE TABLE t (id BIGINT COMMENT '아이디 {CHECK}') COMMENT='테이블';\n",
        "backend/src/test/java/x/ATest.java": f"package x;\n/** 테스트 {SMILE} */\nclass ATest {{}}\n",
        "frontend/src/features/a/pages/APage.tsx": f"/** 화면ID SCR-1 {CHECK} */\nexport default function APage() {{ return null; }}\n",
    }
    for rel_path, text in files.items():
        f = root / rel_path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    res = quality.scan(str(root))
    hits = sorted({f["file"] for f in res["findings"] if f["rule"] == "NO-EMOJI"})
    assert hits == sorted(files), hits
    assert all(f["severity"] == "critical" for f in res["findings"] if f["rule"] == "NO-EMOJI")


def test_emoji_cannot_be_ignored(tmp_path):
    src = tmp_path / "p/src/main/java/x/B.java"
    src.parent.mkdir(parents=True)
    src.write_text(f"package x;\n/** B {CHECK} */ // quality:ignore NO-EMOJI\npublic class B {{}}\n", encoding="utf-8")
    assert quality.scan(str(tmp_path / "p"))["by_rule"].get("NO-EMOJI") == 1


def test_normal_symbols_are_not_emoji(tmp_path):
    src = tmp_path / "p/src/main/resources/application.yml"
    src.parent.mkdir(parents=True)
    src.write_text("# 요청 → 응답 · 한도 ≥ 3 ≠ 0 ─ ① © \u2014 \u2026\nserver:\n  port: 8080\n", encoding="utf-8")
    assert "NO-EMOJI" not in quality.scan(str(tmp_path / "p"))["by_rule"]


# ---------------------------------------------------------------- 범위 한정의 대가 (BG-02)

def test_files_mode_records_how_much_was_not_checked():
    """범위를 한정하면 "몇 개를 안 봤는지" 를 함께 낸다 — 전수 통과와 구분되게.

    실측(BG-02): 기존 코드가 많은 저장소에서 전수 검사는 critical 수천 건이 나와 쓸 수 없고,
    변경 파일만 보는 것이 맞는 사용법이다. 그런데 종전에는 `mode: files` 만 적어
    **레포트만 보는 사람이 전수 검사 통과와 구분할 수 없었다.**
    """
    one = "backend/src/main/resources/mapper/NoticeMapper.xml"
    res = quality.scan(BAD, [one])
    sc = res["scope"]
    assert sc["scanned"] == 1
    assert sc["candidates"] > 1
    assert sc["unchecked"] == sc["candidates"] - 1

    # 사람이 읽는 출력에도 나온다
    p = run(BAD, "--files", one)
    assert "검사하지 않은 파일" in p.stdout, p.stdout
    assert "전수 결과와 같은 것으로 보지 않는다" in p.stdout

    # 전수 검사에는 그 칸이 없다 (대가가 없으므로)
    full = quality.scan(BAD)
    assert "scope" not in full and full["mode"] == "full"
    assert "검사하지 않은 파일" not in run(BAD).stdout

    # 전부 지정하면 unchecked 가 0 이다 (경계)
    every = [quality.rel(q, os.path.abspath(BAD)) for q in quality.iter_files(BAD)]
    sc2 = quality.scan(BAD, every)["scope"]
    assert sc2["unchecked"] == 0, sc2


# ---------------------------------------------------------------- 신규 파일은 완화하지 않는다 (BG-10)

NO_DOC_JAVA = """package com.ex.user.x;

public class Widget {
    public String name() { return "x"; }
}
"""


def _write(tmp_path, rel, body):
    p = tmp_path / "p" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return rel


def test_new_file_major_blocks_without_strict(tmp_path):
    """기존 부채를 완화해도 **이번 차수에 새로 만든 파일**은 완화하지 않는다.

    실측(BG-10): brownfield 에서 기존 파일이 규약을 이미 위반해 전체를 warn 으로 완화했는데,
    그러면 새로 만드는 파일도 함께 완화된다 — 새 코드의 품질이 기존 코드 수준으로 수렴한다.
    """
    rel = _write(tmp_path, "backend/src/main/java/com/ex/user/x/Widget.java", NO_DOC_JAVA)
    root = str(tmp_path / "p")

    # 기존 파일로 보면 major 는 차단하지 않는다 (종전 동작)
    res = quality.scan(root, [rel])
    assert res["counts"]["major"] > 0 and res["counts"]["critical"] == 0
    assert quality.blocking(res) is False
    assert quality.blocking(res, strict=True) is True

    # 신규 파일로 선언하면 --strict 없이도 차단한다
    res2 = quality.scan(root, [rel], [rel])
    assert quality.blocking(res2) is True
    assert res2["new_files"] == {"declared": 1, "critical": 0,
                                 "major": res2["counts"]["major"], "minor": res2["counts"]["minor"]}
    assert all(f.get("new_file") for f in res2["findings"])

    # 다른 파일을 신규로 선언해도 이 파일은 완화된 채다 (표시가 정확한가)
    res3 = quality.scan(root, [rel], ["backend/src/main/java/com/ex/user/x/Other.java"])
    assert quality.blocking(res3) is False
    assert not any(f.get("new_file") for f in res3["findings"])

    # minor 만 있는 신규 파일은 차단하지 않는다 (major 이상만)
    res4 = quality.scan(root, [rel], [rel])
    for f in res4["findings"]:
        f["severity"] = "minor"
    assert quality.blocking(res4) is False


def test_new_files_are_scanned_even_if_not_in_files(tmp_path):
    """--new-files 는 --files 에 없어도 점검 대상에 들어간다 — 새 파일을 빠뜨리지 않게."""
    rel = _write(tmp_path, "backend/src/main/java/com/ex/user/x/Widget.java", NO_DOC_JAVA)
    other = _write(tmp_path, "backend/src/main/java/com/ex/user/x/Kept.java",
                   "package com.ex.user.x;\n/** 유지 */\npublic class Kept {}\n")
    root = str(tmp_path / "p")
    p = run(root, "--files", other, "--new-files", rel)
    assert "신규 파일 1개" in p.stdout, p.stdout
    assert "[신규]" in p.stdout, p.stdout
    assert p.returncode == 1, p.stdout          # 신규 파일의 major 가 차단한다


def test_statements_inside_xml_comments_are_not_counted(tmp_path):
    # AS-IS 에서 실행되지 않던 statement 를 주석으로만 옮긴 경우(pipeline-core 12절) - 실행 statement 로 세지 않는다
    xml = ('<?xml version="1.0"?>\n<!-- 업무 Mapper -->\n<mapper namespace="a.B">\n'
           '<!-- 목적 -->\n<select id="live">SELECT 1</select>\n'
           '<!-- [AS-IS 원문 시작]\n<update id="dead">UPDATE T SET A = 1</update>\n[AS-IS 원문 끝] -->\n</mapper>\n')
    out, stats = [], {"mapper_files": 0, "mapper_files_documented": 0, "mapper_statements": 0, "mapper_statements_documented": 0}
    quality.check_mapper(str(tmp_path / "B.xml"), xml, str(tmp_path), out, stats)
    assert stats["mapper_statements"] == 1 and stats["mapper_statements_documented"] == 1
    assert stats["mapper_statements_commented"] == 1
    assert not [f for f in out if "dead" in str(f)]
