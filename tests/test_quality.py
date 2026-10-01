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
