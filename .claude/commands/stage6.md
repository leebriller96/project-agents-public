---
description: 6단계 보안 점검 — code-security-auditor 의 방법론으로 target_dir 을 점검하고 취약점을 리팩토링 요구서로 만듭니다. 재점검 시 이전 레포트와 비교해 해결 여부를 검증합니다.
argument-hint: "[all|<slice-id>] [hybrid|claude-only|sast-only] (기본 all hybrid)"
---

# /stage6 — 보안 점검

인자: `$ARGUMENTS` (대상, 모드)

## 절차
1. `.claude/skills/pipeline-core/SKILL.md` §1·§6·§8. 선행: `stage5_integration: done` 인 slice 1개 이상(`/refactor` 되돌림으로 pending 이면 경고만 하고 진행하되 사용자에게 "stage5 재실행 필요" 를 표시). `config/tools.yaml → security_auditor.path` 존재 확인 (없으면 안내 후 종료).
2. 모드 결정: 인자 없으면 hybrid. `python <path>/tools/run_sast.py --help` 등으로 도구 존재를 확인하고, SAST 가 하나도 없으면 claude-only 로 폴백하고 알린다.
3. 재점검 여부: `workspace/<project>/reports/` 에 이전 `*_stage6_all_security.md` 가 있으면 그 경로를 에이전트에 넘긴다.
4. `stages.stage6_security: in_progress`.
5. **규모 판단**: 대상 소스 파일 수(제외 디렉토리 빼고)를 센다.
   - 150개 이하 또는 인자가 slice 하나 → `security-auditor` 를 `scan all`(또는 `scan <slice>`) 로 1회 호출.
   - 150개 초과이고 대상이 all → `slices.yaml` 의 slice 마다 `security-auditor` 를 `scan <slice>` 로 **병렬** 호출(`max_parallel` 준수, common 은 첫 slice 에 포함) → 모두 끝나면 `security-auditor` 를 `merge <slice 레포트 경로들>` 로 1회 호출. RR 은 merge 에서만 만든다.
   전달: target_dir 절대경로, 모드, 외부 스킬 경로, 이전 레포트 경로(있으면).
6. 보고를 받아 `state.yaml` 갱신 (`done`), RR 집계 갱신(`python tools/rr.py stats --write`). blocker/high 가 있으면 log 에 "재점검 필요".
7. 사용자에게: 모드와 도구 실행/실패/건너뜀, 심각도×확신도 건수, **RR 표**, 중복 제외 건수, (재점검) 신규/잔존/해결 수와 되돌린 RR, `.auditignore` 제안 줄(사람이 추가), 우선 조치 Top 3, 레포트(md/html/findings.json) 경로.
8. RR 중 **사양 결정이 필요한 것**(요구사항에 없는 기능 추가·정책 변경 — 예: 비밀번호 변경 기능, 토큰 폐기 정책, TLS)은 brief §12 결정 요청으로 사용자에게 옵션과 함께 제시하고, 결정 전에는 `/refactor` 에서 착수하지 않는다(RR description 에 "사업 결정 선행" 표시).
9. 안내: RR 이 있으면 `/refactor` 후 `/stage6` 재실행(diff 검증), 없으면 `/stage7`.

## 완료 처리 (공통 · pipeline-core §9·§11·§12)

1. 서브에이전트 보고의 `pa-agent-result` 블록에서 게이트·변경 파일·확인 필요 항목을 그대로 가져온다.
   `changed_files` 에 소유 밖 파일이 있으면 되돌리고 공통 후보로 돌린다.
2. 확인 필요 항목은 `python tools/gate.py oi new --stage 6 --slice <id> --kind <kind> --severity <sev> --summary "…" --evidence "…" --target <닫을 단계>` 로 채번한다.
   `blocker`·`high` 는 RR 전환(`oi set <id> converted --rr RR-xxxx`) 또는 사람 승인(`accepted`) 없이 남기지 않는다.
3. 레포트 끝에 `pa-meta` 블록을 붙인다 (`python tools/gate.py template --stage 6 --slice <id> --agent orchestrator` 로 골격 생성 후 실제 값으로 채움).
4. `python tools/gate.py check --stage 6 [--slice <id>]` 를 실행한다. **FAIL 이면 그 단계를 `done` 으로 기록하지 않는다.**
   검사 결과(통과 / FAIL 항목)를 사용자 보고에 한 줄로 포함한다.

## 공통 금지 — 이모지

서브에이전트 프롬프트에 "이모지 금지(pipeline-core §15)" 를 명시하고, 레포트·보고·생성 소스 어디에도 이모지를 쓰지 않는다. 훅이 차단하면 텍스트로 고친다.
