#!/usr/bin/env python3
# status.py — workspace/<project>/state.yaml 과 slices.yaml 을 읽어 진행 상태 요약을 출력한다. (/status 가 사용)
#
# 사용법: python tools/status.py
# 의존성: pyyaml

import os

from _common import ROOT, fix_console_encoding, workspace

# Windows 콘솔(cp949)에서도 한글이 깨지지 않도록 출력 인코딩을 고정한다
fix_console_encoding()

import yaml  # _common 이 설치 여부를 이미 확인했다

WS = workspace()
STATE = os.path.join(WS, "state.yaml")
SLICES = os.path.join(WS, "slices", "slices.yaml")
CONFIG = os.path.join(ROOT, "config", "project.yaml")

# 상태 표시는 ASCII 기호만 쓴다 (이모지 금지 원칙 — CLAUDE.md "이모지 금지")
# [~] = done_elsewhere - 다른 작업 환경에서 끝났다는 사람 선언(증거가 이 환경에 없다. pipeline-core BG-01)
MARK = {"done": "[v]", "in_progress": "[>]", "blocked": "[x]", "pending": "[ ]", "skipped": "[-]",
        "done_elsewhere": "[~]", None: "[ ]", "": "[ ]"}


def load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def main():
    cfg = load(CONFIG)
    st = load(STATE)
    sl = load(SLICES)

    if cfg is None:
        print("config/project.yaml 이 없습니다. config/project.yaml.example 을 복사해 만드세요.")
        return
    if st is None:
        print(f"{os.path.relpath(STATE, ROOT)} 이 없습니다. /stage0 를 실행하면 생성됩니다.")
        return

    print(f"# {st.get('project')}  (mode={st.get('mode')}, iteration={st.get('iteration')}, updated={st.get('updated_at')})")
    print(f"target_dir: {cfg.get('project', {}).get('target_dir')}")
    approved = sl.get("approved") if sl else None
    print(f"slices.yaml 승인: {'예' if approved else '아니오 (approved: true 필요)' if sl else '(없음)'}")
    print()

    print("## 공통 단계")
    print("| 단계 | 상태 |")
    print("|---|---|")
    for k, v in (st.get("stages") or {}).items():
        print(f"| {k} | {MARK.get(v, v)} {v} |")
    print()

    slices = st.get("slices") or {}
    if slices:
        print("## slice × 단계")
        print("| slice | stage2 BE | stage4 FE | stage5 통합 | unit (BE/FE 완료) | blocked 사유 |")
        print("|---|---|---|---|---|---|")
        split = []
        for sid, s in slices.items():
            s = s or {}
            units = s.get("units") if isinstance(s.get("units"), dict) else {}
            ucell = ""
            if units:
                be = sum(1 for u in units.values() if (u or {}).get("stage2_backend") == "done")
                fe = sum(1 for u in units.values() if (u or {}).get("stage4_frontend") == "done")
                ucell = f"{len(units)}개 ({be}/{fe})"
                split.append((sid, units))
            print(f"| {sid} | {MARK.get(s.get('stage2_backend'), '[ ]')} {s.get('stage2_backend', 'pending')} "
                  f"| {MARK.get(s.get('stage4_frontend'), '[ ]')} {s.get('stage4_frontend', 'pending')} "
                  f"| {MARK.get(s.get('stage5_integration'), '[ ]')} {s.get('stage5_integration', 'pending')} "
                  f"| {ucell} | {s.get('blocked_reason') or ''} |")
        print()
        # 큰 slice 를 업무 프로세스 기준으로 나눈 unit 의 진행 (tools/slice_units.py)
        for sid, units in split:
            print(f"### {sid} — unit 진행")
            print("| unit | stage2 BE | stage4 FE | blocked 사유 |")
            print("|---|---|---|---|")
            for uid, u in units.items():
                u = u or {}
                print(f"| {uid} | {MARK.get(u.get('stage2_backend'), '[ ]')} {u.get('stage2_backend', 'pending')} "
                      f"| {MARK.get(u.get('stage4_frontend'), '[ ]')} {u.get('stage4_frontend', 'pending')} "
                      f"| {u.get('blocked_reason') or ''} |")
            print()

    rr = st.get("refactor_requests") or {}
    print(f"## 리팩토링 요구서: open {rr.get('open', 0)} / in_progress {rr.get('in_progress', 0)} "
          f"/ done {rr.get('done', 0)} / rejected {rr.get('rejected', 0)}")
    print()

    # 확인 필요 항목(open item) — pipeline-core §11
    oi = load(os.path.join(WS, "open-items.yaml"))
    items = [i for i in ((oi or {}).get("items") or []) if isinstance(i, dict) and i.get("status") == "open"]
    if items:
        order = {"blocker": 0, "high": 1, "medium": 2, "low": 3}
        items.sort(key=lambda i: (order.get(i.get("severity"), 9), str(i.get("target_stage"))))
        print(f"## 확인 필요 항목 (열림 {len(items)}건)")
        print("| id | severity | kind | slice | 닫을 단계 | 요약 |")
        print("|---|---|---|---|---|---|")
        for i in items:
            print(f"| {i.get('id')} | {i.get('severity')} | {i.get('kind')} | {i.get('slice') or '-'} "
                  f"| stage{i.get('target_stage')} | {str(i.get('summary', ''))[:60]} |")
        blocking = [i for i in items if i.get("severity") in ("blocker", "high")]
        if blocking:
            print(f"\n> `blocker`/`high` {len(blocking)}건은 RR 전환 또는 사람 승인 없이 해당 단계를 done 으로 끝낼 수 없다.")
        print()

    # 판단 기록(JD) — pipeline-core §21. 검증 단계가 다시 확인해야 하는 것
    jd = load(os.path.join(WS, "judgments.yaml"))
    jds = [j for j in ((jd or {}).get("items") or []) if isinstance(j, dict)]
    if jds:
        left = [j for j in jds if j.get("status") in ("pending", "failed")]
        by_stage = {}
        for j in left:
            by_stage[j.get("verify_stage", 5)] = by_stage.get(j.get("verify_stage", 5), 0) + 1
        failed = sum(1 for j in left if j.get("status") == "failed")
        print(f"## 판단 기록: 전체 {len(jds)}건 / 재검증 남음 {len(left)}건"
              + (" (" + ", ".join(f"stage{k} {v}건" for k, v in sorted(by_stage.items())) + ")" if by_stage else "")
              + (f" / 판단 오류(failed) {failed}건" if failed else ""))
        print("> `python tools/judgment.py list --status pending` 로 확인한다. 검증 단계는 결과 없이 done 이 될 수 없다.")
        print()

    log = st.get("log") or []
    if log:
        print("## 최근 기록")
        for e in log[-5:]:
            print(f"- {e.get('at')} [{e.get('stage')}{'/' + str(e.get('slice')) if e.get('slice') else ''}] "
                  f"{e.get('result')} — {e.get('note', '')}")


if __name__ == "__main__":
    main()
