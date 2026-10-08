# handoff.py — 인계 기록 줄에 KST 실측 시각을 도구가 찍는지
import os
import subprocess
import sys

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
sys.path.insert(0, TOOLS)

from handoff import insert_note  # noqa: E402

DOC = """# 인계

- 마지막 갱신: 2026-01-01 09:00

## 0. 현재 진행

- 2026-01-01 09:00: 시작

## 1. 원칙

- 원칙 하나
"""


def test_inserts_at_end_of_first_section_and_updates_last_modified():
    out = insert_note(DOC, "공통 완료", stamp="2026-01-02 10:30")
    assert "- 2026-01-01 09:00: 시작\n- 2026-01-02 10:30: 공통 완료\n\n## 1. 원칙" in out
    assert "- 마지막 갱신: 2026-01-02 10:30" in out


def test_section_option_targets_named_section():
    out = insert_note(DOC, "원칙 추가", section="원칙", stamp="2026-01-02 10:31")
    assert out.rstrip().endswith("- 원칙 하나\n- 2026-01-02 10:31: 원칙 추가")


def test_unknown_section_is_error():
    try:
        insert_note(DOC, "x", section="없는 절", stamp="2026-01-02 10:31")
    except ValueError:
        return
    raise AssertionError("없는 절인데 넣었다")


def test_cli_rejects_emoji(tmp_path):
    p = tmp_path / "HANDOFF.md"
    p.write_text(DOC, encoding="utf-8")
    r = subprocess.run([sys.executable, os.path.join(TOOLS, "handoff.py"), "note", "완료 \U0001F600", "--file", str(p)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 2
    assert p.read_text(encoding="utf-8") == DOC


def test_cli_writes_real_kst_stamp(tmp_path):
    p = tmp_path / "HANDOFF.md"
    p.write_text(DOC, encoding="utf-8")
    r = subprocess.run([sys.executable, os.path.join(TOOLS, "handoff.py"), "note", "기록", "--file", str(p)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    from handoff import kst_full
    text = p.read_text(encoding="utf-8")
    assert f": 기록" in text and kst_full()[:10] in text
