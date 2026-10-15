#!/usr/bin/env python3
# lessons.py — docs/LESSONS.md 에 교훈을 덧붙이고 찾는다. 파일 전체를 문맥으로 읽지 않기 위한 도구다.
#
# 배경: LESSONS.md 는 회차마다 늘어나 100KB 를 넘었다. Edit 로 한 줄을 덧붙이려 해도 먼저 파일 전체를 읽어야 하고,
#       읽은 내용은 그 세션의 이후 모든 호출에서 캐시 읽기로 다시 비용이 된다 (pipeline-core §26).
#
# 사용법:
#   python tools/lessons.py add --title "2026-10-14 — 토큰 절감" --row "영역|현상|조치" [--row …]
#       제목이 마지막 절과 같으면 그 표에 행을 덧붙이고, 다르면 새 절(| 영역 | 현상 | 조치 | 표)을 만든다.
#       셀 안의 | 는 \| 로 쓴다. --from <파일> 이면 그 파일의 마크다운을 그대로 덧붙인다.
#   python tools/lessons.py headings [--last 10]          # 절 제목만
#   python tools/lessons.py grep <정규식> [--max 30]       # 일치하는 줄만 (절 제목과 함께)
# 의존성: 없음

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, atomic_write_text, fix_console_encoding  # noqa: E402

fix_console_encoding()

LESSONS = os.path.join(ROOT, "docs", "LESSONS.md")
HEADER = "| 영역 | 현상 | 조치 |\n|---|---|---|\n"


def read():
    try:
        with open(LESSONS, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return "# 실행 이력·교훈 로그 (LESSONS)\n"


def split_row(row):
    cells = [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", row)]
    if len(cells) != 3 or not all(cells):
        sys.exit(f"[lessons] 행은 '영역|현상|조치' 세 칸이어야 한다: {row[:60]}")
    return "| " + " | ".join(c.replace("|", "\\|").replace("\n", " ") for c in cells) + " |\n"


def cmd_add(args):
    from _emoji import find_emoji
    text = read()
    if args.from_file:
        with open(args.from_file, encoding="utf-8") as f:
            add = "\n" + f.read().strip("\n") + "\n"
    else:
        if not args.title or not args.row:
            sys.exit("[lessons] --title 과 --row 가 필요하다 (또는 --from)")
        rows = "".join(split_row(r) for r in args.row)
        heads = re.findall(r"^## (.+)$", text, re.M)
        if heads and heads[-1].strip() == args.title.strip():
            add = rows
        else:
            add = f"\n## {args.title.strip()}\n\n" + HEADER + rows
    hits = find_emoji(add)
    if hits:
        sys.exit("[lessons] 이모지는 쓰지 않는다: " + ", ".join(cp for _n, _c, _ch, cp in hits[:5]))
    atomic_write_text(LESSONS, text.rstrip("\n") + "\n" + add)
    print(f"덧붙임: {LESSONS} (+{add.count(chr(10))}줄)")
    return 0


def cmd_headings(args):
    heads = re.findall(r"^## (.+)$", read(), re.M)
    for h in heads[-args.last:]:
        print(h)
    return 0


def cmd_grep(args):
    rx = re.compile(args.pattern)
    section, n = "", 0
    for line in read().split("\n"):
        if line.startswith("## "):
            section = line[3:]
            continue
        if rx.search(line):
            print(f"[{section}] {line[:400]}")
            n += 1
            if n >= args.max:
                print(f"... (상한 {args.max}줄)")
                break
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="docs/LESSONS.md 덧붙이기·찾기 (전체를 읽지 않는다)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--title")
    a.add_argument("--row", action="append")
    a.add_argument("--from", dest="from_file")
    a.set_defaults(fn=cmd_add)
    h = sub.add_parser("headings")
    h.add_argument("--last", type=int, default=10)
    h.set_defaults(fn=cmd_headings)
    g = sub.add_parser("grep")
    g.add_argument("pattern")
    g.add_argument("--max", type=int, default=30)
    g.set_defaults(fn=cmd_grep)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
