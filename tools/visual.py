#!/usr/bin/env python3
# visual.py — 브라우저 화면 검증의 "AI 가 볼 것만 고르기" 와 기준 이미지 승인 관리
#
# 원칙: 화면 검증은 Playwright 가 헤드리스로 실행하고, 모양 비교는 toHaveScreenshot 의 픽셀 비교가 한다(토큰 0).
#       AI(또는 사람)가 이미지를 직접 보는 것은 두 경우뿐이다 —
#         (1) 새로 생긴·바뀐 기준 이미지(baseline)를 처음 승인할 때 (화면·상태마다 1회)
#         (2) 픽셀 비교가 실패해 diff 이미지가 생겼을 때
#       통과한 테스트의 스크린샷은 보지 않는다. 이 도구가 볼 대상을 고르고, 이미지 입력 토큰을 미리 추정해 예산을 넘으면 알린다.
#       단위테스트마다 캡처해 AI 가 판정하면 비용이 크고(이미지 1장 약 1~1.6천 토큰) 회차마다 판단이 흔들린다(비결정적).
#
# 사용법 (target_dir 기준 경로):
#   python tools/visual.py pending [--slice <id>] [--format json]   # 검토 대상(미승인·변경 기준 이미지, 실패 diff) + 토큰 추정
#   python tools/visual.py approve --files <png…> --by <검토자> [--note "…"]   # 기준 이미지 승인(해시 기록)
#   python tools/visual.py verify [--slice <id>]                     # 미승인·변경 기준 이미지나 실패 diff 가 있으면 종료 코드 1
#
# config (verification.visual):
#   enabled: true            gate 의 visual 훅을 켠다
#   approver: agent | human  human 이면 approve 는 사람만(훅이 에이전트 실행을 막는다)
#   review_budget_images: 60 한 번에 AI 가 볼 이미지 상한 (넘으면 pending 이 경고)
#   baseline_globs / diff_globs  기준 이미지·실패 diff 위치
# 의존성: pyyaml (config 읽기)

import argparse
import datetime
import glob
import hashlib
import json
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import atomic_write_text, config, safe_relpath, file_lock, fix_console_encoding, target_dir, workspace  # noqa: E402

fix_console_encoding()

KST = datetime.timezone(datetime.timedelta(hours=9), name="KST")
DEFAULT_BASELINE_GLOBS = ["**/__screenshots__/**/*.png", "**/*-snapshots/*.png"]
DEFAULT_DIFF_GLOBS = ["**/test-results/**/*-diff.png"]
SKIP = ("/node_modules/", "/.git/")
MAX_EDGE = 1568          # 이미지 입력은 긴 변이 이 크기를 넘으면 축소된다
MAX_PIXELS = 1_150_000   # 그리고 약 1.15 메가픽셀을 넘지 않게 축소된다 → 장당 최대 약 1,600 토큰
PIXELS_PER_TOKEN = 750   # 이미지 입력 토큰 ≈ 가로 × 세로 / 750 (대략값)


def vcfg():
    return (config().get("verification") or {}).get("visual") or {}


def manifest_path():
    return os.path.join(workspace(), "visual", "approved.json")


def rel(p, base):
    return safe_relpath(p, base)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def png_size(path):
    """PNG 헤더(IHDR)에서 (가로, 세로). 읽지 못하면 (0, 0)."""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
            return 0, 0
        return struct.unpack(">II", head[16:24])
    except OSError:
        return 0, 0


def image_tokens(w, h):
    if not w or not h:
        return 1600   # 크기를 모르면 상한으로 본다
    s = min(1.0, MAX_EDGE / max(w, h), math.sqrt(MAX_PIXELS / (w * h)))
    return int(math.ceil((w * s) * (h * s) / PIXELS_PER_TOKEN))


def in_slice(r, slice_id):
    """경로가 slice 에 속하는가: 경로 구간이 slice id 이거나(e2e/<slice>/), 구간이 '<slice>-' 로 시작(Playwright test-results 폴더명)."""
    parts = r.split("/")
    return slice_id in parts or any(p.startswith(slice_id + "-") for p in parts[:-1])


def find(td, globs, slice_id=None):
    out = set()
    for g in globs:
        for p in glob.glob(os.path.join(td, g), recursive=True):
            r = rel(p, td)
            if any(x in "/" + r for x in SKIP) or not os.path.isfile(p):
                continue
            if slice_id and not in_slice(r, slice_id):
                continue
            out.add(r)
    return sorted(out)


def load_manifest():
    p = manifest_path()
    if not os.path.exists(p):
        return {"approved": {}}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def pending(td, slice_id=None):
    """검토 대상 목록과 토큰 추정."""
    c = vcfg()
    baselines = find(td, c.get("baseline_globs") or DEFAULT_BASELINE_GLOBS, slice_id)
    diffs = find(td, c.get("diff_globs") or DEFAULT_DIFF_GLOBS, slice_id)
    approved = load_manifest().get("approved", {})
    items = []
    for r in baselines:
        rec = approved.get(r)
        h = sha256(os.path.join(td, r))
        if not rec:
            reason = "new-baseline"
        elif rec.get("sha256") != h:
            reason = "changed-baseline"
        else:
            continue
        w, hgt = png_size(os.path.join(td, r))
        items.append({"file": r, "reason": reason, "width": w, "height": hgt, "tokens": image_tokens(w, hgt)})
    for r in diffs:
        w, hgt = png_size(os.path.join(td, r))
        items.append({"file": r, "reason": "failed-diff", "width": w, "height": hgt, "tokens": image_tokens(w, hgt)})
    budget = int(c.get("review_budget_images") or 60)
    total = sum(i["tokens"] for i in items)
    return {"baselines": len(baselines), "approved": len(baselines) - sum(1 for i in items if i["reason"] != "failed-diff"),
            "items": items, "images": len(items), "estimated_tokens": total, "budget_images": budget,
            "over_budget": len(items) > budget}


def cmd_pending(args):
    td = args.target or target_dir()
    r = pending(td, args.slice)
    if args.format == "json":
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    print(f"기준 이미지 {r['baselines']} (승인 {r['approved']}) · 검토 대상 {r['images']}장 · 이미지 입력 약 {r['estimated_tokens']:,} 토큰")
    for i in r["items"]:
        print(f"- [{i['reason']}] {i['file']} ({i['width']}x{i['height']}, 약 {i['tokens']} 토큰)")
    if r["over_budget"]:
        print(f"주의: 검토 대상이 예산({r['budget_images']}장)을 넘는다 — 화면 단위로 나눠 검토하거나 기준 이미지 해상도를 줄인다")
    return 0


def cmd_approve(args):
    td = args.target or target_dir()
    path = manifest_path()
    with file_lock(path):
        m = load_manifest()
        stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
        for f in args.files:
            r = rel(os.path.abspath(f if os.path.isabs(f) else os.path.join(td, f)), td)
            p = os.path.join(td, r)
            if not os.path.isfile(p):
                sys.exit(f"[visual] 파일이 없다: {r}")
            if r.endswith("-diff.png") or "/test-results/" in "/" + r:
                sys.exit(f"[visual] 실패 diff 는 승인 대상이 아니다: {r} — 결함이면 RR, 의도한 변경이면 기준 이미지를 갱신(--update-snapshots) 후 승인")
            w, h = png_size(p)
            m["approved"][r] = {"sha256": sha256(p), "approved_by": args.by, "approved_at": stamp,
                                "note": args.note or "", "width": w, "height": h}
        atomic_write_text(path, json.dumps(m, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(f"승인 {len(args.files)}장 ({args.by}) → {path}")
    return 0


def cmd_verify(args):
    td = args.target or target_dir()
    r = pending(td, args.slice)
    for i in r["items"]:
        print(f"- [{i['reason']}] {i['file']}")
    print(f"결과: {'통과' if not r['items'] else '검토 필요 ' + str(r['images']) + '장'}")
    return 1 if r["items"] else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="브라우저 화면 검증 — AI 검토 대상 선별·기준 이미지 승인")
    ap.add_argument("--target", help="target_dir (기본: config)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pending")
    p.add_argument("--slice")
    p.add_argument("--format", choices=["human", "json"], default="human")
    p.set_defaults(fn=cmd_pending)
    p = sub.add_parser("approve")
    p.add_argument("--files", nargs="+", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--note")
    p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("verify")
    p.add_argument("--slice")
    p.set_defaults(fn=cmd_verify)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
