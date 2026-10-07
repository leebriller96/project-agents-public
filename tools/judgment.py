#!/usr/bin/env python3
# judgment.py — 판단 기록(JD) 관리. pipeline-core §21.
#
# 자동 변환(카탈로그 등가 구문·계약대로의 계승 이동·프로필 규칙)으로 정해진 것이 아니라
# 사람이나 에이전트가 **판단**해서 정한 것(대안 중 선택·대체 매핑·'불필요' 판정·의미 차이 수용·범위 제외·
# 지시와 다른 결정)은 그 단계의 테스트가 통과해도 판단 자체가 옳았는지는 증명되지 않는다.
# 그래서 판단을 workspace/<project>/judgments.yaml 에 채번해 두고, 검증 단계(기본 5, 필요 시 7)가
# 영향 slice 마다 다시 확인한다. 확인 기준:
#   - migration(차세대): AS-IS 기능이 손실 없이 동작하고, 요구사항에 맞게 온전히 개발돼 있다 (증거 2개)
#   - 그 밖(신규 개발): 요구사항에 맞게 온전히 개발돼 있다 (증거 1개)
#
# 사용법:
#   python tools/judgment.py new --stage 2 --slice common-port --kind substitution --by "사람:검토자" \
#          --summary "..." --rationale "..." --source "reports/<레포트>#4-3" --check "무엇을 어떻게 확인하나" \
#          [--affects CC-0025 --affects CC-0026] [--verify-slices notice,member] [--verify-stage 5] [--oi OI-0101]
#   python tools/judgment.py import --report <레포트> --write     # pa-meta 의 judgments 일괄 채번
#   python tools/judgment.py list [--status pending] [--slice notice] [--verify-stage 5]
#   python tools/judgment.py verify JD-0003 --slice notice --result verified \
#          --req-evidence "통합 시나리오 IT-FW-07 통과(reports/...)" --asis-evidence "AS-IS 대조 표 3행(reports/...)"
#   python tools/judgment.py verify JD-0003 --slice notice --result failed --rr RR-0051
#   python tools/judgment.py set JD-0003 --verify-stage 7 --note "..."          # 검증 단계 재예약
#   python tools/judgment.py set JD-0003 --waive --approved-by 검토자 --note "..." # 사람만: 재검증 면제
#
# 종료 코드: 0 정상 · 1 대조 실패(list --strict) · 2 입력 오류
# 의존성: pyyaml

import argparse
import datetime
import json
import os
import re
import sys

from _common import (ROOT, config, dump_yaml, file_lock, fix_console_encoding, load_yaml,  # noqa: E402
                     numbering_start, workspace)

fix_console_encoding()

KST = datetime.timezone(datetime.timedelta(hours=9), name="KST")
META_START = "<!-- pa-meta:start"
META_END = "pa-meta:end -->"

WS = workspace()
JD_FILE = os.path.join(WS, "judgments.yaml")
RR_DIR = os.path.join(WS, "refactor-requests")

# 판단 종류 — 무엇을 근거로 무엇을 골랐나
JD_KINDS = (
    "decision",        # 사람 결정 (decision open item 의 해소, 승인·위임 판단)
    "substitution",    # 대체 매핑: AS-IS 기능을 다른(2차·공통·프레임워크) 구현으로 대신함, '불필요:' 판정 포함
    "semantic",        # 의미 차이를 수용·보정함 (AS-IS 결함 값 유지, 타입·정렬·절단 등)
    "scope",           # 범위 제외·폐기(discard)·보류(hold)·이관 안 함
    "interpretation",  # 근거가 모호·부족한 상태에서 해석을 골라 구현함
    "design",          # 대안이 있는 설계 선택 (배치·이름·설정 방식 등)
    "deviation",       # 지시·계약·규약과 다르게 결정함 (pa-agent-result.deviations)
)
JD_STATUSES = ("pending", "verified", "failed", "waived")
VERIFY_RESULTS = ("verified", "failed")
VERIFY_STAGES = (5, 6, 7)


def now_kst():
    return datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")


def project_mode():
    return str((config().get("project") or {}).get("mode") or "greenfield")


def criterion(mode=None):
    """검증 기준 문구. 판단마다 기록해 두어 검증자가 기준을 따로 찾지 않게 한다."""
    if (mode or project_mode()) == "migration":
        return "AS-IS 기능이 손실 없이 동작하고, 요구사항에 맞게 온전히 개발돼 있다"
    return "요구사항에 맞게 온전히 개발돼 있다"


def load_judgments():
    if not os.path.exists(JD_FILE):
        return {"items": []}
    data = load_yaml(JD_FILE)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return {"items": []}
    return data


def next_jd_id(items):
    nums = [int(m.group(1)) for i in items
            for m in [re.match(r"JD-(\d{4})$", str(i.get("id", "")))] if m]
    nxt = (max(nums) + 1) if nums else 1
    return f"JD-{max(nxt, numbering_start('JD')):04d}"


def as_list(v):
    if v is None or v == "":
        return []
    if isinstance(v, str):
        return [s.strip() for s in v.split(",") if s.strip()]
    return [str(s).strip() for s in v if str(s).strip()]


def verify_slices_of(rec):
    """이 판단을 재검증할 slice 목록. 비어 있으면 판단이 나온 slice 하나."""
    vs = as_list(rec.get("verify_slices"))
    return vs or ([rec["slice"]] if rec.get("slice") else [])


def overall_status(rec):
    """slice 별 확인 결과로 전체 상태를 정한다. waived 는 사람이 정한 값이라 그대로 둔다."""
    if rec.get("status") == "waived":
        return "waived"
    ver = rec.get("verifications") or {}
    if any((v or {}).get("result") == "failed" for v in ver.values()):
        return "failed"
    slices = verify_slices_of(rec)
    if slices and all((ver.get(s) or {}).get("result") == "verified" for s in slices):
        return "verified"
    return "pending"


def pending_for(items, stage, slice_id):
    """이 단계·이 slice 가 확인해야 하는데 아직 확인 결과가 없는 판단."""
    out = []
    for rec in items:
        if not isinstance(rec, dict) or rec.get("status") == "waived":
            continue
        if int(rec.get("verify_stage") or 5) != int(stage):
            continue
        slices = verify_slices_of(rec)
        if slice_id in (None, "", "all"):
            todo = [s for s in slices if not ((rec.get("verifications") or {}).get(s) or {}).get("result")]
            if todo:
                out.append((rec, todo))
        elif slice_id in slices and not ((rec.get("verifications") or {}).get(slice_id) or {}).get("result"):
            out.append((rec, [slice_id]))
    return out


def make_record(items, *, stage, slice_id, kind, by, summary, rationale, source, check,
                affects=None, verify_slices=None, verify_stage=5, oi=None, alternatives=None):
    if kind not in JD_KINDS:
        raise ValueError(f"kind 는 {'|'.join(JD_KINDS)} 중 하나여야 한다")
    if int(verify_stage) not in VERIFY_STAGES:
        raise ValueError(f"verify_stage 는 {'|'.join(map(str, VERIFY_STAGES))} 중 하나여야 한다")
    for name, val in (("by", by), ("summary", summary), ("rationale", rationale),
                      ("source", source), ("check", check)):
        if not str(val or "").strip():
            raise ValueError(f"{name} 가 비었다 — 판단은 누가·무엇을·왜·어디서·어떻게 확인할지가 모두 있어야 한다")
    return {
        "id": next_jd_id(items), "made_at": now_kst(), "stage": stage, "slice": slice_id or "",
        "kind": kind, "decided_by": by, "summary": summary, "rationale": rationale,
        "alternatives": alternatives or "", "source": source, "affects": as_list(affects),
        "verify_slices": as_list(verify_slices), "verify_stage": int(verify_stage),
        "criterion": criterion(), "check": check, "oi_id": oi or "",
        "status": "pending", "verifications": {}, "approved_by": "", "note": "",
    }


# ---------------------------------------------------------------- 명령

def cmd_new(args):
    os.makedirs(WS, exist_ok=True)
    with file_lock(JD_FILE):
        data = load_judgments()
        try:
            rec = make_record(data["items"], stage=args.stage, slice_id=args.slice, kind=args.kind, by=args.by,
                              summary=args.summary, rationale=args.rationale, source=args.source,
                              check=args.check, affects=args.affects, verify_slices=args.verify_slices,
                              verify_stage=args.verify_stage, oi=args.oi, alternatives=args.alternatives)
        except ValueError as ex:
            sys.exit(f"[judgment] {ex}")
        data["items"].append(rec)
        dump_yaml(JD_FILE, data)
    print(rec["id"])
    print(JD_FILE)
    return 0


def extract_meta(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    s, e = text.find(META_START), text.find(META_END)
    if s < 0 or e < 0:
        return None, text
    try:
        return json.loads(text[s + len(META_START):e]), text
    except ValueError:
        return None, text


def cmd_import(args):
    """레포트 pa-meta 의 judgments[](id 없는 객체)를 일괄 채번하고 id 를 써넣는다."""
    report = args.report if os.path.isabs(args.report) else os.path.normpath(os.path.join(ROOT, args.report))
    meta, text = extract_meta(report)
    if meta is None:
        sys.exit("[judgment] pa-meta 블록을 읽지 못했다")
    items = meta.get("judgments")
    if not isinstance(items, list):
        sys.exit("[judgment] pa-meta.judgments 가 배열이 아니다")
    os.makedirs(WS, exist_ok=True)
    added, skipped = [], 0
    with file_lock(JD_FILE):
        data = load_judgments()
        store = data["items"]
        known = {i.get("id") for i in store if isinstance(i, dict)}
        for idx, it in enumerate(items):
            if isinstance(it, str):
                skipped += 1
                continue
            if not isinstance(it, dict):
                sys.exit(f"[judgment] judgments[{idx}] 는 객체나 JD id 문자열이어야 한다")
            if it.get("id") and it["id"] in known:
                skipped += 1
                continue
            try:
                rec = make_record(store, stage=meta.get("stage"), slice_id=it.get("slice") or meta.get("slice"),
                                  kind=it.get("kind"), by=it.get("decided_by") or f"에이전트:{meta.get('agent', '')}",
                                  summary=it.get("summary"), rationale=it.get("rationale"),
                                  source=it.get("source") or os.path.basename(report), check=it.get("check"),
                                  affects=it.get("affects"), verify_slices=it.get("verify_slices"),
                                  verify_stage=it.get("verify_stage") or 5, oi=it.get("oi_id"),
                                  alternatives=it.get("alternatives"))
            except ValueError as ex:
                sys.exit(f"[judgment] judgments[{idx}]: {ex}")
            store.append(rec)
            known.add(rec["id"])
            it["id"] = rec["id"]
            added.append(rec)
        dump_yaml(JD_FILE, data)
    if args.write:
        s, e = text.find(META_START), text.find(META_END)
        new = text[:s] + META_START + "\n" + json.dumps(meta, ensure_ascii=False, indent=2) + "\n" + text[e:]
        with open(report, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new)
    print(f"채번 {len(added)}건 (기존 {skipped}건 건너뜀) → {JD_FILE}")
    for rec in added:
        print(f"  {rec['id']} {rec['kind']:<14} →stage{rec['verify_stage']}  {str(rec['summary'])[:60]}")
    if not args.write:
        print("레포트에 id 를 써넣으려면 --write 를 붙인다")
    return 0


def cmd_list(args):
    items = [i for i in load_judgments()["items"] if isinstance(i, dict)]
    rows = []
    for i in items:
        st = overall_status(i)
        if args.status and st != args.status:
            continue
        if args.slice and args.slice != i.get("slice") and args.slice not in verify_slices_of(i):
            continue
        if args.verify_stage is not None and int(i.get("verify_stage") or 5) != args.verify_stage:
            continue
        rows.append((i, st))
    if args.format == "json":
        print(json.dumps([dict(i, status=st) for i, st in rows], ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("해당 판단 없음")
        return 0
    print(f"{'ID':<8} {'kind':<14} {'검증':<6} {'상태':<9} 확인 slice / 요약")
    for i, st in rows:
        ver = i.get("verifications") or {}
        sl = verify_slices_of(i)
        done = sum(1 for s in sl if (ver.get(s) or {}).get("result"))
        print(f"{i.get('id', ''):<8} {i.get('kind', ''):<14} stage{i.get('verify_stage', 5):<1} {st:<9} "
              f"{done}/{len(sl)} / {str(i.get('summary', ''))[:60]}")
    print(f"총 {len(rows)}건")
    return 1 if args.strict and any(st in ("pending", "failed") for _, st in rows) else 0


def cmd_verify(args):
    """slice 하나의 재검증 결과를 기록한다. 검증 단계(5·6·7)의 에이전트가 쓴다."""
    if args.result == "failed" and not args.rr:
        sys.exit("[judgment] failed 는 --rr RR-xxxx 가 필요하다 (판단이 틀렸으면 요구서로 고친다)")
    if args.rr and not os.path.exists(os.path.join(RR_DIR, f"{args.rr}.yaml")):
        sys.exit(f"[judgment] {args.rr} 파일이 없다: {RR_DIR}")
    if args.result == "verified":
        if not str(args.req_evidence or "").strip():
            sys.exit("[judgment] verified 는 --req-evidence(요구사항 충족 증거: 테스트·시나리오·레포트 절)가 필요하다")
        if project_mode() == "migration" and not str(args.asis_evidence or "").strip():
            sys.exit("[judgment] migration 프로젝트의 verified 는 --asis-evidence"
                     "(AS-IS 기능이 손실 없이 동작한다는 대조 증거)도 필요하다")
    with file_lock(JD_FILE):
        data = load_judgments()
        for rec in data["items"]:
            if rec.get("id") != args.id:
                continue
            slices = verify_slices_of(rec)
            if args.slice not in slices:
                sys.exit(f"[judgment] {args.id} 의 확인 slice 가 아니다: {args.slice} (대상: {', '.join(slices)})")
            rec.setdefault("verifications", {})[args.slice] = {
                "result": args.result, "at": now_kst(), "by": args.by or "",
                "stage": int(args.stage) if args.stage is not None else int(rec.get("verify_stage") or 5),
                "req_evidence": args.req_evidence or "", "asis_evidence": args.asis_evidence or "",
                "rr_id": args.rr or "", "note": args.note or ""}
            rec["status"] = overall_status(rec)
            rec["updated_at"] = now_kst()
            dump_yaml(JD_FILE, data)
            print(f"{args.id} [{args.slice}] → {args.result} (전체 {rec['status']})")
            return 0
    sys.exit(f"[judgment] {args.id} 를 찾지 못했다")


def cmd_set(args):
    """검증 단계 재예약·확인 slice 변경·사람의 재검증 면제."""
    if args.waive and not args.approved_by:
        sys.exit("[judgment] 면제(--waive)는 사람만 할 수 있고 --approved-by 가 필요하다")
    if args.waive and not args.note:
        sys.exit("[judgment] 면제(--waive)는 사유(--note)가 필요하다")
    if args.verify_stage is not None and args.verify_stage not in VERIFY_STAGES:
        sys.exit(f"[judgment] verify_stage 는 {'|'.join(map(str, VERIFY_STAGES))}")
    with file_lock(JD_FILE):
        data = load_judgments()
        for rec in data["items"]:
            if rec.get("id") != args.id:
                continue
            notes = [rec.get("note")] if rec.get("note") else []
            if args.verify_stage is not None:
                notes.append(f"[재예약 stage{rec.get('verify_stage')}→stage{args.verify_stage}]")
                rec["verify_stage"] = args.verify_stage
            if args.verify_slices is not None:
                notes.append(f"[확인 slice 변경 {','.join(verify_slices_of(rec))}→{args.verify_slices}]")
                rec["verify_slices"] = as_list(args.verify_slices)
            if args.waive:
                rec["status"] = "waived"
                rec["approved_by"] = args.approved_by
            if args.note:
                notes.append(args.note)
            rec["note"] = " ".join(notes)
            if not args.waive:
                rec["status"] = overall_status(rec)
            rec["updated_at"] = now_kst()
            dump_yaml(JD_FILE, data)
            print(f"{args.id} → {rec['status']}")
            return 0
    sys.exit(f"[judgment] {args.id} 를 찾지 못했다")


# ---------------------------------------------------------------- gate 훅이 쓰는 판정

def meta_findings(meta):
    """레포트 pa-meta 의 judgments 를 대조해 (심각도, 필드, 메시지, 조치) 목록을 돌려준다.

    - judgments[] 의 id 는 judgments.yaml 에 있어야 한다 (산문에만 있는 판단은 다음 단계에서 사라진다)
    - 2·3·4단계: deviations 가 있는데 judgments 가 비었으면 경고 (지시와 다른 결정은 곧 판단이다)
    - 5·6·7단계: 이 단계·이 slice 가 확인하기로 한 판단에 확인 결과가 없으면 차단
    - 8단계: 아직 확인되지 않은 판단이 남았으면 경고 (산출물이 검증 안 된 판단을 싣는다)
    """
    out = []
    stage, sl = meta.get("stage"), meta.get("slice")
    store = {i.get("id"): i for i in load_judgments()["items"] if isinstance(i, dict)}
    items = meta.get("judgments")
    if items is not None and not isinstance(items, list):
        return [("FAIL", "judgments", "judgments 는 배열이어야 한다", "")]
    for idx, it in enumerate(items or []):
        jid = it if isinstance(it, str) else (it.get("id") if isinstance(it, dict) else None)
        if not jid:
            out.append(("FAIL", f"judgments[{idx}].id", "JD id 가 없다",
                        "python tools/judgment.py import --report <이 레포트> --write 로 채번한다"))
        elif jid not in store:
            out.append(("FAIL", f"judgments[{idx}].id", f"{jid} 가 judgments.yaml 에 없다",
                        "judgment.py new 또는 import 로 먼저 채번한다"))
    if stage in (2, 3, 4) and meta.get("deviations") and not items:
        out.append(("WARN", "judgments", "deviations 가 있는데 judgments 가 비었다 — 지시·계약과 다르게 정한 것은 판단이다",
                    "판단마다 judgments[] 에 싣고 judgment.py import 로 채번한다 (pipeline-core §21)"))
    if stage in VERIFY_STAGES:
        todo = pending_for(list(store.values()), stage, sl)
        if todo:
            ids = ", ".join(f"{r['id']}({'/'.join(s)})" for r, s in todo[:12]) + (" …" if len(todo) > 12 else "")
            out.append(("FAIL", "judgments", f"이 단계가 재검증하기로 한 판단 {len(todo)}건에 확인 결과가 없다: {ids}",
                        f"python tools/judgment.py list --verify-stage {stage}"
                        f"{' --slice ' + sl if sl and sl != 'all' else ''} 로 받아 verify 로 기록한다 (pipeline-core §21)"))
        for r in store.values():
            for s, v in (r.get("verifications") or {}).items():
                if (v or {}).get("result") == "failed" and v.get("rr_id") and \
                        not os.path.exists(os.path.join(RR_DIR, f"{v['rr_id']}.yaml")):
                    out.append(("FAIL", "judgments", f"{r['id']}[{s}] 의 {v['rr_id']} 파일이 없다", ""))
    if stage == 8:
        left = [r for r in store.values() if overall_status(r) in ("pending", "failed")]
        if left:
            out.append(("WARN", "judgments", f"재검증이 끝나지 않은 판단 {len(left)}건이 남아 있다",
                        "python tools/judgment.py list --status pending 로 확인하고 산출물에 미검증으로 표시한다"))
    return out


def build_parser():
    p = argparse.ArgumentParser(description="판단 기록(JD) 관리 — pipeline-core §21")
    sub = p.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new", help="판단 1건 채번")
    n.add_argument("--stage", type=int, required=True, help="판단한 단계")
    n.add_argument("--slice", help="판단이 나온 slice (공통은 common-port 등)")
    n.add_argument("--kind", required=True, choices=JD_KINDS)
    n.add_argument("--by", required=True, help="판단 주체: '사람:<이름>' 또는 '에이전트:<이름>'")
    n.add_argument("--summary", required=True, help="무엇을 정했나")
    n.add_argument("--rationale", required=True, help="왜 그렇게 정했나 (근거)")
    n.add_argument("--alternatives", help="고르지 않은 대안")
    n.add_argument("--source", required=True, help="판단이 적힌 곳 (레포트#절·계약 id·OI)")
    n.add_argument("--check", required=True, help="재검증 때 무엇을 어떻게 확인하나 (시나리오 수준으로 구체적으로)")
    n.add_argument("--affects", action="append", help="영향 항목 (계약 id·statement·파일, 반복 지정)")
    n.add_argument("--verify-slices", dest="verify_slices", help="재검증할 slice (쉼표 구분, 기본은 --slice)")
    n.add_argument("--verify-stage", dest="verify_stage", type=int, default=5, choices=VERIFY_STAGES)
    n.add_argument("--oi", help="이 판단으로 해소한 decision open item")
    n.set_defaults(fn=cmd_new)

    im = sub.add_parser("import", help="레포트 pa-meta 의 judgments 일괄 채번")
    im.add_argument("--report", required=True)
    im.add_argument("--write", action="store_true")
    im.set_defaults(fn=cmd_import)

    ls = sub.add_parser("list")
    ls.add_argument("--status", choices=JD_STATUSES)
    ls.add_argument("--slice")
    ls.add_argument("--verify-stage", dest="verify_stage", type=int)
    ls.add_argument("--format", choices=["human", "json"], default="human")
    ls.add_argument("--strict", action="store_true", help="pending·failed 가 있으면 종료 코드 1")
    ls.set_defaults(fn=cmd_list)

    v = sub.add_parser("verify", help="slice 하나의 재검증 결과 기록")
    v.add_argument("id")
    v.add_argument("--slice", required=True)
    v.add_argument("--result", required=True, choices=VERIFY_RESULTS)
    v.add_argument("--req-evidence", dest="req_evidence", help="요구사항 충족 증거")
    v.add_argument("--asis-evidence", dest="asis_evidence", help="(migration) AS-IS 기능 무손실 증거")
    v.add_argument("--rr", help="failed 일 때 만든 RR")
    v.add_argument("--stage", type=int, help="확인한 단계 (기본 verify_stage)")
    v.add_argument("--by", help="확인한 에이전트")
    v.add_argument("--note")
    v.set_defaults(fn=cmd_verify)

    s = sub.add_parser("set", help="재예약·확인 slice 변경·사람의 면제")
    s.add_argument("id")
    s.add_argument("--verify-stage", dest="verify_stage", type=int)
    s.add_argument("--verify-slices", dest="verify_slices")
    s.add_argument("--waive", action="store_true", help="재검증 면제 (사람만)")
    s.add_argument("--approved-by", dest="approved_by")
    s.add_argument("--note")
    s.set_defaults(fn=cmd_set)
    return p


def main():
    args = build_parser().parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
