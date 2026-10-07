#!/usr/bin/env python3
"""서브에이전트 결과 블록(pa-agent-result JSON)을 단계 레포트로 옮긴다 — pipeline-core §9·§11·§12·§21.

오케스트레이터가 매 보고마다 손으로 하던 일을 한 번에 한다:
  1. open_items 중 id 가 없는 것을 `gate.py oi new` 와 같은 규칙으로 채번한다(open-items.yaml).
  2. 레포트 `<ts>_stage<N>_<slice>[_unit-<u>]_<설명>.md` 를 만든다 — 본문(선택) + 결과 요약 + pa-meta 블록.
     pa-meta 의 repo 는 target_dir 의 git 실측(branch·head·dirty)으로 채운다.
  3. judgments 를 `judgment.py import --write` 로 채번하고 id 를 레포트에 써넣는다.

사용:
  python tools/ingest_result.py --json <결과.json> --stage 2 --slice common-file --name backend_contract \
      [--unit core] [--body <본문.md>] [--started "2026-10-06 09:10"] [--dry-run]

배경(실측): 결과 블록을 손으로 옮기면 judgments·open_items 를 빠뜨리거나 문구를 줄여 버린다.
결과 블록이 정본이고 레포트는 그 사본이므로 기계로 옮긴다.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, fix_console_encoding, target_dir, workspace  # noqa: E402

META_START = "<!-- pa-meta:start"
META_END = "pa-meta:end -->"
KST = datetime.timezone(datetime.timedelta(hours=9))


def now_kst():
    return datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")


def ts_kst():
    return datetime.datetime.now(KST).strftime("%y%m%d%H%M")


def git(repo, *args):
    """target 저장소 git 실측. 실패하면 빈 문자열."""
    try:
        out = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                             encoding="utf-8", timeout=60)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def repo_info(changed):
    """pa-meta repo 블록 — branch·head·dirty 는 실측, changed_files 는 결과 블록 그대로."""
    repo = target_dir()
    status = git(repo, "status", "--porcelain")
    return {"dir": repo, "branch": git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
            "head": git(repo, "rev-parse", "--short", "HEAD"), "base": "",
            "dirty": bool(status), "changed_files": list(changed or [])}


def assign_oi(items, stage, slice_id, dry_run):
    """id 없는 open_item 을 채번한다. gate.py 의 oi new 를 그대로 불러 규칙(번호·검증)을 한곳에 둔다."""
    out = []
    for it in items or []:
        if not isinstance(it, dict) or it.get("id"):
            out.append(it)
            continue
        if dry_run:
            out.append(dict(it, id="OI-(dry-run)"))
            continue
        cmd = [sys.executable, os.path.join(ROOT, "tools", "gate.py"), "oi", "new",
               "--stage", str(stage), "--slice", slice_id or "",
               "--kind", it.get("kind", "unverified"), "--severity", it.get("severity", "low"),
               "--summary", it.get("summary", ""), "--evidence", it.get("evidence", ""),
               "--target", str(it.get("target_stage", "") or "")]
        if it.get("axis"):
            cmd += ["--axis", it["axis"]]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
        if res.returncode != 0:
            sys.exit(f"[ingest] oi new 실패: {res.stderr.strip() or res.stdout.strip()}")
        oid = res.stdout.strip().splitlines()[0]
        out.append(dict(it, id=oid))
    return out


OI_KINDS = ("evidence_gap", "decision", "unverified", "risk", "deferred")
OI_SEVERITIES = ("blocker", "high", "medium", "low")
JD_KINDS = ("decision", "substitution", "semantic", "scope", "interpretation", "design", "deviation")


def validate(res):
    """채번 전에 결과 블록의 형식을 검사한다(gate.py oi new·judgment.py 와 같은 규칙)."""
    out = []
    for i, it in enumerate(res.get("open_items") or []):
        if not isinstance(it, dict):
            out.append(f"open_items[{i}] 는 객체여야 한다")
            continue
        if it.get("id"):
            continue
        if it.get("kind") not in OI_KINDS:
            out.append(f"open_items[{i}].kind={it.get('kind')!r} - {'|'.join(OI_KINDS)} 중 하나")
        if it.get("severity") not in OI_SEVERITIES:
            out.append(f"open_items[{i}].severity={it.get('severity')!r}")
    for i, j in enumerate(res.get("judgments") or []):
        if not isinstance(j, dict) or j.get("id"):
            continue
        if j.get("kind") not in JD_KINDS:
            out.append(f"judgments[{i}].kind={j.get('kind')!r} - {'|'.join(JD_KINDS)} 중 하나")
        if j.get("verify_stage") not in (None, 5, 6, 7):
            out.append(f"judgments[{i}].verify_stage={j.get('verify_stage')!r} - 5|6|7")
        if not j.get("check"):
            out.append(f"judgments[{i}].check 가 비었다")
    return out


RESULTS = ("done", "done_with_gaps", "blocked", "failed")
VERDICT_RESULT = {"PASS": "done", "FAIL": "failed"}


def normalize_result(res):
    """검토 에이전트가 result 에 판정(PASS·FAIL)을 적으면 verdict 로 옮기고 result 를 단계 결과 값으로 바꾼다
    (실측: result=PASS 가 그대로 레포트에 들어가 gate report-meta 가 막았다)."""
    r = res.get("result", "done")
    if r in VERDICT_RESULT:
        res.setdefault("verdict", r)
        res["result"] = VERDICT_RESULT[r]
    return res


def build_meta(res, args, open_items):
    started = args.started or now_kst()
    meta = {
        "schema": 1, "stage": args.stage, "slice": args.slice, "iteration": res.get("attempt", 1),
        "agent": res.get("agent", "orchestrator"), "result": res.get("result", "done"),
        "started_at": started, "finished_at": now_kst(),
        "repo": repo_info(res.get("changed_files")),
        "gates": res.get("gates") or [],
        "open_items": open_items,
        "judgments": res.get("judgments") or [],
        "rr_ids": res.get("rr_ids") or [],
        "common_candidates": res.get("common_candidates") or [],
        "not_executed": res.get("not_executed") or [],
        "risk_surface": res.get("risk_surface") or [],
        "deviations": res.get("deviations") or [],
        "cost": res.get("cost") or {"duration_min": 0, "tool_calls": 0, "tokens_k": 0},
    }
    if args.unit:
        meta["unit"] = args.unit
    for key in ("asis_covered", "spec", "discrimination", "verdict"):
        if key in res:
            meta[key] = res[key]
    return meta


def summary_md(res, open_items):
    lines = [f"- 결과: `{res.get('result', '')}` (에이전트 {res.get('agent', '')}, 회차 {res.get('attempt', 1)})"]
    for g in res.get("gates") or []:
        extra = f", 테스트 {g['test_count']}건 실패 {g.get('failures', 0)}" if "test_count" in g else ""
        lines.append(f"- 게이트 {g.get('kind')}{('/' + g['suite']) if g.get('suite') else ''}: "
                     f"종료 코드 {g.get('exit_code')}{extra} - `{g.get('command', '')}`")
    if open_items:
        lines.append("- 확인 필요: " + ", ".join(f"{i.get('id')}({i.get('severity')})" for i in open_items))
    if res.get("not_executed"):
        lines.append("- 실행하지 못한 것: " + " / ".join(res["not_executed"]))
    if res.get("deviations"):
        lines.append("- 지시와 다르게 정한 것: " + " / ".join(res["deviations"]))
    return "\n".join(lines)


def main():
    fix_console_encoding()
    ap = argparse.ArgumentParser(description="pa-agent-result JSON → 단계 레포트·OI·JD")
    ap.add_argument("--json", required=True, help="결과 블록 JSON 파일")
    ap.add_argument("--stage", type=int, required=True)
    ap.add_argument("--slice", default=None)
    ap.add_argument("--unit", default=None)
    ap.add_argument("--name", required=True, help="레포트 이름의 설명 부분(예: backend_contract)")
    ap.add_argument("--body", default=None, help="레포트 본문 markdown 파일(선택)")
    ap.add_argument("--title", default=None)
    ap.add_argument("--started", default=None, help="단계 시작 시각 KST 'YYYY-MM-DD HH:MM'")
    ap.add_argument("--dry-run", action="store_true", help="채번·쓰기 없이 레포트 내용만 출력")
    args = ap.parse_args()

    with open(args.json, encoding="utf-8") as fh:
        res = json.load(fh)
    res = normalize_result(res)
    problems = validate(res)
    if res.get("result") not in RESULTS:
        problems.append(f"result={res.get('result')!r} - {'|'.join(RESULTS)} 중 하나(판정 PASS·FAIL 은 verdict)")
    if problems:
        # 채번(OI·JD)을 하나라도 하기 전에 막는다 - 중간에 실패하면 OI 만 채번되고 레포트가 없는 반쪽 상태가 남는다(실측)
        sys.exit("[ingest] 결과 블록을 먼저 고친다:\n  - " + "\n  - ".join(problems))
    open_items = assign_oi(res.get("open_items"), args.stage, args.slice, args.dry_run)
    meta = build_meta(res, args, open_items)

    parts = [p for p in (args.slice, f"unit-{args.unit}" if args.unit else None, args.name) if p]
    fname = f"{ts_kst()}_stage{args.stage}_{'_'.join(parts)}.md"
    title = args.title or f"{args.stage}단계 {args.slice or ''} {args.name}".strip()
    body = ""
    if args.body:
        with open(args.body, encoding="utf-8") as fh:
            body = fh.read().strip() + "\n\n"
    text = (f"# {title}\n\n{body}## 결과 요약\n\n{summary_md(res, open_items)}\n\n"
            f"{META_START}\n{json.dumps(meta, ensure_ascii=False, indent=2)}\n{META_END}\n")
    if args.dry_run:
        print(fname)
        print(text)
        return 0
    path = os.path.join(workspace(), "reports", fname)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    if meta["judgments"]:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "judgment.py"), "import",
                            "--report", path, "--write"], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
        print(r.stdout.strip())
        if r.returncode != 0:
            sys.exit(f"[ingest] judgment import 실패: {r.stderr.strip()}")
    print(f"레포트: {path}")
    print("OI: " + ", ".join(str(i.get("id")) for i in open_items))
    return 0


if __name__ == "__main__":
    sys.exit(main())
