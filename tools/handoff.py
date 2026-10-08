#!/usr/bin/env python3
"""HANDOFF.md 에 진행 기록 한 줄을 KST 실측 시각과 함께 넣는다 — CLAUDE.md '세션 인계는 HANDOFF.md 로'.

사용:
  python tools/handoff.py note "공통 port 완료 - 전 모듈 새 실패 0" [--section "자율 진행"] [--file <HANDOFF.md>]

- 줄 모양: `- YYYY-MM-DD HH:MM: <내용>` (시각은 tools/kst_now.py 와 같은 KST 실측)
- 넣는 자리: --section 에 준 글자가 든 첫 `## ` 절의 끝(다음 `## ` 바로 앞, 빈 줄 앞). 없으면 첫 `## ` 절의 끝.
- 파일 머리의 `- 마지막 갱신:` 줄이 있으면 같은 시각으로 고친다.
- 이모지가 든 내용은 거부한다(판정 기준 tools/_emoji.py).

배경(실측): 오케스트레이터가 인계 기록 시각을 짐작으로 적어 실제보다 30분 앞선 줄이 쌓였다.
같은 실수가 교훈으로 적힌 뒤에도 되풀이됐다 - 사람 기억이 아니라 도구가 시각을 찍는다.
"""
import argparse
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import fix_console_encoding, workspace  # noqa: E402
from _emoji import find_emoji  # noqa: E402

KST = datetime.timezone(datetime.timedelta(hours=9))


def kst_full(now=None):
    return (now or datetime.datetime.now(KST)).strftime("%Y-%m-%d %H:%M")


def insert_note(text, note, section=None, stamp=None):
    """HANDOFF 본문 text 에 note 한 줄을 넣은 새 본문을 돌려준다."""
    stamp = stamp or kst_full()
    lines = text.split("\n")
    heads = [i for i, l in enumerate(lines) if l.startswith("## ")]
    if not heads:
        raise ValueError("'## ' 절이 없다")
    start = heads[0]
    if section:
        hit = [i for i in heads if section in lines[i]]
        if not hit:
            raise ValueError(f"절을 찾지 못했다: {section}")
        start = hit[0]
    later = [i for i in heads if i > start]
    end = later[0] if later else len(lines)
    pos = end
    while pos > start + 1 and lines[pos - 1].strip() == "":
        pos -= 1
    lines.insert(pos, f"- {stamp}: {note}")
    out = "\n".join(lines)
    out = re.sub(r"^- 마지막 갱신: .*$", f"- 마지막 갱신: {stamp}", out, count=1, flags=re.M)
    return out


def main(argv=None):
    fix_console_encoding()
    ap = argparse.ArgumentParser(description="HANDOFF.md 에 KST 실측 시각과 함께 진행 기록 한 줄을 넣는다")
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("note", help="진행 기록 한 줄 추가")
    n.add_argument("text")
    n.add_argument("--section", help="넣을 절 제목의 일부(기본: 첫 '## ' 절)")
    n.add_argument("--file", help="HANDOFF.md 경로(기본: workspace/<project>/HANDOFF.md)")
    a = ap.parse_args(argv)
    if find_emoji(a.text):
        print("[handoff] 이모지가 든 내용은 넣지 않는다 - 텍스트로 고친다", file=sys.stderr)
        return 2
    path = a.file or os.path.join(workspace(), "HANDOFF.md")
    if not os.path.exists(path):
        print(f"[handoff] 파일이 없다: {path} (templates/HANDOFF.md 로 먼저 만든다)", file=sys.stderr)
        return 2
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        out = insert_note(text, a.text, a.section)
    except ValueError as e:
        print(f"[handoff] {e}", file=sys.stderr)
        return 2
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    print(f"[handoff] {kst_full()} 기록 -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
