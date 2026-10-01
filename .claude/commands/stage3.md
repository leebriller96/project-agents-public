---
description: 3단계 공통화 리팩토링 — 완료된 slice 들에서 공통 코드를 common 모듈로 추출하고 컨벤션을 정렬합니다. 동작(테스트 결과)은 보존합니다.
argument-hint: "(인자 없음)"
---

# /stage3 — 공통화 리팩토링

## 절차
1. `.claude/skills/pipeline-core/SKILL.md` §1·§7 (선행: `stage2_backend: done` 인 slice 1개 이상).
2. `stages.stage3_common: in_progress`, log 에 회차(iteration) 기록.
3. `common-refactorer` 호출. 전달: target_dir, 프로필, `done` slice 목록, `workspace/<project>/reports/common-candidates.md` 경로.
4. 보고 후 `backend-reviewer` 를 `common` 대상으로 호출. FAIL 이면 `common-refactorer` 재호출 (최대 2회) → 잔여 시 `blocked`.
5. `state.yaml` 갱신 (`done`|`blocked`). 보류된 후보 중 향후 필요한 것은 RR(`source_stage: 3`) 로 남긴다.
6. 사용자에게: 추출 목록, 보류 목록과 사유, 기준선 대비 테스트 결과, `common-module-spec.md` 경로.
7. 안내: `/stage4 <slice>` 또는 새 slice 가 있으면 `/stage2 <slice>`.

## 완료 처리 (공통 · pipeline-core §9·§11·§12)

1. 서브에이전트 보고의 `pa-agent-result` 블록에서 게이트·변경 파일·확인 필요 항목을 그대로 가져온다.
   `changed_files` 에 소유 밖 파일이 있으면 되돌리고 공통 후보로 돌린다.
2. 확인 필요 항목은 `python tools/gate.py oi new --stage 3 --slice <id> --kind <kind> --severity <sev> --summary "…" --evidence "…" --target <닫을 단계>` 로 채번한다.
   `blocker`·`high` 는 RR 전환(`oi set <id> converted --rr RR-xxxx`) 또는 사람 승인(`accepted`) 없이 남기지 않는다.
3. 레포트 끝에 `pa-meta` 블록을 붙인다 (`python tools/gate.py template --stage 3 --slice <id> --agent orchestrator` 로 골격 생성 후 실제 값으로 채움).
4. `python tools/gate.py check --stage 3 [--slice <id>]` 를 실행한다. **FAIL 이면 그 단계를 `done` 으로 기록하지 않는다.**
   검사 결과(통과 / FAIL 항목)를 사용자 보고에 한 줄로 포함한다.

## 공통 금지 — 이모지

서브에이전트 프롬프트에 "이모지 금지(pipeline-core §15)" 를 명시하고, 레포트·보고·생성 소스 어디에도 이모지를 쓰지 않는다. 훅이 차단하면 텍스트로 고친다.
