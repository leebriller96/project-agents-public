# tools/lessons.py — LESSONS.md 를 읽지 않고 덧붙이기·찾기
import os

CHECK = chr(0x2705)   # 이모지 문자는 코드포인트로만 만든다


def _lessons(sandbox):
    d = os.path.join(sandbox.root, "docs")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "LESSONS.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write("# 로그\n\n## 2026-10-01 — 예전\n\n| 영역 | 현상 | 조치 |\n|---|---|---|\n| a | b | c |\n")
    return p


def test_add_appends_to_same_section_or_creates_new(sandbox):
    p = _lessons(sandbox)
    sandbox.run("lessons.py", "add", "--title", "2026-10-01 — 예전", "--row", "훅|출력 \\| 길다|축약", check=0)
    sandbox.run("lessons.py", "add", "--title", "2026-10-14 — 토큰", "--row", "계측|원인 모름|cost_probe", check=0)
    text = open(p, encoding="utf-8").read()
    assert text.count("## 2026-10-01 — 예전") == 1
    assert "| 훅 | 출력 \\| 길다 | 축약 |\n\n## 2026-10-14 — 토큰" in text
    assert text.endswith("| 계측 | 원인 모름 | cost_probe |\n")
    assert "2026-10-14 — 토큰" in sandbox.run("lessons.py", "headings", check=0).stdout
    g = sandbox.run("lessons.py", "grep", "cost_probe", check=0).stdout
    assert g.startswith("[2026-10-14 — 토큰]")


def test_add_rejects_bad_row_and_emoji(sandbox):
    _lessons(sandbox)
    assert sandbox.run("lessons.py", "add", "--title", "t", "--row", "두칸|만").returncode != 0
    assert sandbox.run("lessons.py", "add", "--title", "t", "--row", "a|b|완료 " + CHECK).returncode != 0
