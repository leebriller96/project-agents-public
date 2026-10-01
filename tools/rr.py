#!/usr/bin/env python3
# rr.py — 리팩토링 요구서(RR) 관리 도구
#
# 사용법:
#   python tools/rr.py new                       # 다음 RR id 를 출력하고 템플릿 복사본 생성 (RR-0001.yaml ...)
#   python tools/rr.py new --title "..." --slice order --source 5 --target 2 --layer backend/service --severity high
#   python tools/rr.py list [--status open] [--slice order] [--stage 2]   # 표 출력
#   python tools/rr.py set RR-0001 done [--note "..."]                    # 상태 변경 (open|in_progress|done|rejected)
#   python tools/rr.py stats                     # 상태별 건수 (state.yaml 의 refactor_requests 에 그대로 반영)
#   python tools/rr.py validate                  # 필수 키·값 검사
#
# 의존성: pyyaml

import argparse
import datetime
import glob
import os
import sys

from _common import ROOT, create_numbered_file, dump_yaml, file_lock, fix_console_encoding, load_yaml, workspace

# Windows 콘솔(cp949)에서도 한글이 깨지지 않도록 출력 인코딩을 고정한다
fix_console_encoding()

import yaml  # _common 이 설치 여부를 이미 확인했다

WS = workspace()
RR_DIR = os.path.join(WS, "refactor-requests")
TEMPLATE = os.path.join(ROOT, "templates", "refactor-request.yaml")
STATE = os.path.join(WS, "state.yaml")

KST = datetime.timezone(datetime.timedelta(hours=9), name="KST")
STATUSES = ("open", "in_progress", "done", "rejected")
SEVERITIES = ("blocker", "high", "medium", "low")
SEV_ORDER = {s: i for i, s in enumerate(SEVERITIES)}
REQUIRED = ("id", "title", "source_stage", "slice", "target_stage", "target_layer",
            "severity", "evidence", "description", "status", "iteration")


def now_kst() -> str:
    return datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")


def rr_files():
    return sorted(glob.glob(os.path.join(RR_DIR, "RR-*.yaml")))


load = load_yaml
dump = dump_yaml


def current_iteration() -> int:
    if os.path.exists(STATE):
        try:
            return int(load(STATE).get("iteration", 1))
        except Exception:
            pass
    return 1


def cmd_new(args):
    # 병렬 에이전트가 동시에 호출해도 번호가 겹치거나 덮어쓰지 않도록 배타적으로 파일을 만든다
    rid, path = create_numbered_file(RR_DIR, "RR")
    data = load(TEMPLATE)
    data.update({
        "id": rid,
        "title": args.title or "",
        "source_stage": args.source if args.source is not None else "",
        "found_at": now_kst(),
        "slice": args.slice or "",
        "target_stage": args.target if args.target is not None else "",
        "target_layer": args.layer or "",
        "severity": args.severity or "",
        "evidence": list(args.evidence or []),
        "description": args.description or "",
        "suggested_fix": args.fix or "",
        "status": "open",
        "iteration": current_iteration(),
        "resolved_at": None,
        "resolution_note": None,
    })
    dump(path, data)
    print(rid)
    print(path)


def matches(d, args) -> bool:
    if args.status and d.get("status") != args.status:
        return False
    if args.slice and d.get("slice") != args.slice:
        return False
    if args.stage is not None and str(d.get("target_stage")) != str(args.stage):
        return False
    if getattr(args, "layer", None) and not str(d.get("target_layer", "")).startswith(args.layer):
        return False
    return True


def cmd_list(args):
    rows = []
    for p in rr_files():
        d = load(p)
        if matches(d, args):
            rows.append(d)
    rows.sort(key=lambda d: (SEV_ORDER.get(d.get("severity"), 99), d.get("id", "")))
    if not rows:
        print("(해당하는 RR 없음)")
        return
    print("| id | severity | status | slice | src→tgt | layer | title |")
    print("|---|---|---|---|---|---|---|")
    for d in rows:
        print(f"| {d.get('id')} | {d.get('severity')} | {d.get('status')} | {d.get('slice')} | "
              f"{d.get('source_stage')}→{d.get('target_stage')} | {d.get('target_layer')} | {d.get('title')} |")


def cmd_set(args):
    if args.new_status not in STATUSES:
        sys.exit(f"[rr] 상태는 {STATUSES} 중 하나여야 합니다.")
    path = os.path.join(RR_DIR, f"{args.id}.yaml")
    if not os.path.exists(path):
        sys.exit(f"[rr] {path} 없음")
    with file_lock(path):
        d = load(path)
        d["status"] = args.new_status
        if args.new_status in ("done", "rejected"):
            d["resolved_at"] = now_kst()
        if args.note:
            d["resolution_note"] = args.note
        dump(path, d)
    print(f"{args.id} → {args.new_status}")
    # 상태가 바뀌면 state.yaml 의 집계도 함께 갱신한다 (오케스트레이터가 stats --write 를 빠뜨려도 stale 되지 않게)
    if os.path.exists(STATE):
        with file_lock(STATE):
            counts = count_statuses()
            st = load(STATE)
            st["refactor_requests"] = counts
            dump(STATE, st)


def count_statuses():
    counts = {s: 0 for s in STATUSES}
    for p in rr_files():
        s = load(p).get("status", "open")
        counts[s if s in counts else "open"] += 1
    return counts


def cmd_stats(args):
    counts = count_statuses()
    print(yaml.safe_dump({"refactor_requests": counts}, allow_unicode=True, sort_keys=False).strip())
    if args.write and os.path.exists(STATE):
        with file_lock(STATE):
            st = load(STATE)
            st["refactor_requests"] = counts
            st["updated_at"] = now_kst()
            dump(STATE, st)
        print(f"(state.yaml 반영: {STATE})")


def cmd_validate(args):
    bad = 0
    for p in rr_files():
        d = load(p)
        errs = [k for k in REQUIRED if k not in d or d[k] in (None, "", [])]
        if d.get("status") not in STATUSES:
            errs.append(f"status={d.get('status')}")
        if d.get("severity") not in SEVERITIES:
            errs.append(f"severity={d.get('severity')}")
        if os.path.basename(p) != f"{d.get('id')}.yaml":
            errs.append("id≠파일명")
        if errs:
            bad += 1
            print(f"{os.path.basename(p)}: {', '.join(errs)}")
    print(f"검사 완료: {len(rr_files())}건 중 문제 {bad}건")
    sys.exit(1 if bad else 0)


def main():
    ap = argparse.ArgumentParser(description="리팩토링 요구서(RR) 관리")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("new")
    p.add_argument("--title"); p.add_argument("--slice"); p.add_argument("--layer")
    p.add_argument("--source", type=int); p.add_argument("--target", type=int)
    p.add_argument("--severity", choices=SEVERITIES)
    p.add_argument("--evidence", action="append", help="근거(파일:라인). 반복 지정")
    p.add_argument("--description", help="현상 설명")
    p.add_argument("--fix", help="수정 제안")
    p.set_defaults(fn=cmd_new)

    p = sub.add_parser("list")
    p.add_argument("--status", choices=STATUSES); p.add_argument("--slice"); p.add_argument("--stage", type=int)
    p.add_argument("--layer", help="target_layer 접두어 필터 (예: backend/mapper, frontend, common)")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("set")
    p.add_argument("id"); p.add_argument("new_status"); p.add_argument("--note")
    p.set_defaults(fn=cmd_set)

    p = sub.add_parser("stats")
    p.add_argument("--write", action="store_true", help="state.yaml 의 refactor_requests 갱신")
    p.set_defaults(fn=cmd_stats)

    p = sub.add_parser("validate")
    p.set_defaults(fn=cmd_validate)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
