#!/usr/bin/env python3
# report_diff.py — 두 레포트(이전/현재)의 발견 항목을 비교해 신규 / 잔존 / 해결 을 표로 정리한다.
#
# 사용법:
#   python tools/report_diff.py reports/2606291651_security_report.md reports/2607011020_security_report.md
#   python tools/report_diff.py <이전.md> <현재.md> --out reports/<타임스탬프>_diff.md
#
# 매칭 기준 (같은 취약점으로 간주):
#   1) CWE 가 하나 이상 겹치고, 같은 파일의 라인이 ±LINE_TOLERANCE 안에 있음   (코드가 조금 밀려도 추적)
#   2) 또는 제목이 동일
# 매칭되지 않은 이전 항목은 "해결(또는 미재현)", 현재 항목은 "신규" 로 분류한다.
# 잔존 항목은 심각도 변화도 함께 표시한다.
#
# 재스캔 결과를 레포트에 붙일 때 이 출력을 "이전 감사 대비 변화" 섹션으로 그대로 넣으면 된다.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_findings import parse_report, SEVERITIES  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

LINE_TOLERANCE = 20


def loc_str(f):
    return ", ".join(
        f"{l['file']}:{l['start_line']}" if l["start_line"] else l["file"] for l in f["locations"]
    ) or "-"


def same_place(a, b) -> bool:
    for la in a["locations"]:
        for lb in b["locations"]:
            if la["file"] != lb["file"]:
                continue
            if la["start_line"] is None or lb["start_line"] is None:
                return True
            if abs(la["start_line"] - lb["start_line"]) <= LINE_TOLERANCE:
                return True
    return False


def match(old, new):
    """(잔존 [(old, new)], 해결 [old], 신규 [new]) 를 돌려준다."""
    remaining_old = list(old)
    persisted, added = [], []
    for n in new:
        hit = None
        for o in remaining_old:
            cwe_overlap = set(o["cwe"]) & set(n["cwe"])
            if (cwe_overlap and same_place(o, n)) or o["title"] == n["title"]:
                hit = o
                break
        if hit:
            remaining_old.remove(hit)
            persisted.append((hit, n))
        else:
            added.append(n)
    return persisted, remaining_old, added


def sev_rank(s):
    return SEVERITIES.index(s) if s in SEVERITIES else len(SEVERITIES)


def render(old_meta, new_meta, old_path, new_path, persisted, resolved, added) -> str:
    lines = []
    lines.append("## 이전 감사 대비 변화")
    lines.append("")
    lines.append(f"- **이전**: `{old_path.name}` ({old_meta.get('분석 일시(KST)', '?')}, {old_meta.get('분석 모드', '?')})")
    lines.append(f"- **현재**: `{new_path.name}` ({new_meta.get('분석 일시(KST)', '?')}, {new_meta.get('분석 모드', '?')})")
    lines.append(f"- **신규 {len(added)}건 · 잔존 {len(persisted)}건 · 해결 {len(resolved)}건**")
    lines.append("")

    def table(title, rows, header):
        lines.append(f"### {title} ({len(rows)}건)")
        lines.append("")
        if not rows:
            lines.append("_없음_")
            lines.append("")
            return
        lines.append(header)
        lines.append("|" + "|".join("---" for _ in header.split("|")[1:-1]) + "|")
        lines.extend(rows)
        lines.append("")

    added_rows = [
        f"| {f['id']} | {f['severity']} | {f['title']} | `{loc_str(f)}` | {', '.join(f['cwe'])} |"
        for f in sorted(added, key=lambda f: sev_rank(f["severity"]))
    ]
    table("신규", added_rows, "| ID | 심각도 | 제목 | 위치 | CWE |")

    persisted_rows = []
    for o, n in sorted(persisted, key=lambda p: sev_rank(p[1]["severity"])):
        change = "" if o["severity"] == n["severity"] else f" (이전 {o['severity']} → **{n['severity']}**)"
        persisted_rows.append(
            f"| {o['id']} → {n['id']} | {n['severity']}{change} | {n['title']} | `{loc_str(n)}` |"
        )
    table("잔존 (미조치)", persisted_rows, "| 이전 → 현재 ID | 심각도 | 제목 | 현재 위치 |")

    resolved_rows = [
        f"| {f['id']} | {f['severity']} | {f['title']} | `{loc_str(f)}` |"
        for f in sorted(resolved, key=lambda f: sev_rank(f["severity"]))
    ]
    table("해결 (또는 미재현)", resolved_rows, "| 이전 ID | 심각도 | 제목 | 이전 위치 |")

    if resolved:
        lines.append("> \"해결\" 은 현재 레포트에서 같은 항목이 보고되지 않았다는 뜻입니다. 코드가 실제로 수정됐는지, "
                     "분석 범위에서 빠졌는지, 또는 이번 분석이 놓쳤는지는 이전 위치를 직접 확인해 구분하세요.")
        lines.append("")
    return "\n".join(lines)


def main():
    args = sys.argv[1:]
    out_path = None
    if "--out" in args:
        i = args.index("--out")
        try:
            out_path = Path(args[i + 1])
        except IndexError:
            sys.exit("사용법: python tools/report_diff.py <이전.md> <현재.md> [--out <결과.md>]")
        del args[i:i + 2]
    if len(args) != 2:
        sys.exit("사용법: python tools/report_diff.py <이전.md> <현재.md> [--out <결과.md>]")
    old_path, new_path = Path(args[0]), Path(args[1])
    for p in (old_path, new_path):
        if not p.is_file():
            sys.exit(f"[report_diff] 파일을 찾을 수 없습니다: {p}")

    old_meta, old = parse_report(old_path.read_text(encoding="utf-8"))
    new_meta, new = parse_report(new_path.read_text(encoding="utf-8"))
    persisted, resolved, added = match(old, new)
    text = render(old_meta, new_meta, old_path, new_path, persisted, resolved, added)

    if out_path:
        out_path.write_text(text + "\n", encoding="utf-8")
        print(f"[report_diff] 생성: {out_path.as_posix()}  (신규 {len(added)} · 잔존 {len(persisted)} · 해결 {len(resolved)})")
    else:
        print(text)


if __name__ == "__main__":
    main()
