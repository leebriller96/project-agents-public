---
description: 7단계 QA 자동화 — qa-automation 의 방법론으로 target_dir 의 통합 테스트를 자동 생성·실행하고 결함/위험을 리팩토링 요구서로 만듭니다.
argument-hint: "[full|generate-only|run-only] (기본 full)"
---

# /stage7 — QA 자동화

인자: `$ARGUMENTS` (모드)

## 절차
1. `.claude/skills/pipeline-core/SKILL.md` §1·§8. 선행: `stage5_integration: done` 인 slice 1개 이상. `config/tools.yaml → qa_automation.path` 존재 확인.
2. `stages.stage7_qa: in_progress` → `qa-runner` 호출. 전달: target_dir 절대경로, 모드, 프로필들, 외부 스킬 경로(`config/tools.yaml → qa_automation`), 5단계 시나리오 경로.
3. 보고를 받아 `state.yaml` 갱신 (`done`), RR 집계 갱신.
4. 사용자에게: 모드(폴백 여부), 생성/실행/통과/실패/에러 수(summary.json 기준), 확정 결함 수(+미확정 수), **RR 표**, 중복 제외 건수, Top 3 우선 조치, 커버리지 공백 요약, 레포트 경로.
5. 안내: RR 이 있으면 `/refactor` 후 `/stage5`→`/stage7` 재확인, 없으면 `/stage8`.

## 완료 처리 (공통 · pipeline-core §9·§11·§12)

1. 서브에이전트 보고의 `pa-agent-result` 블록에서 게이트·변경 파일·확인 필요 항목을 그대로 가져온다.
   `changed_files` 에 소유 밖 파일이 있으면 되돌리고 공통 후보로 돌린다.
2. 확인 필요 항목은 `python tools/gate.py oi new --stage 7 --slice <id> --kind <kind> --severity <sev> --summary "…" --evidence "…" --target <닫을 단계>` 로 채번한다.
   `blocker`·`high` 는 RR 전환(`oi set <id> converted --rr RR-xxxx`) 또는 사람 승인(`accepted`) 없이 남기지 않는다.
3. 레포트 끝에 `pa-meta` 블록을 붙인다 (`python tools/gate.py template --stage 7 --slice <id> --agent orchestrator` 로 골격 생성 후 실제 값으로 채움).
4. `python tools/gate.py check --stage 7 [--slice <id>]` 를 실행한다. **FAIL 이면 그 단계를 `done` 으로 기록하지 않는다.**
   검사 결과(통과 / FAIL 항목)를 사용자 보고에 한 줄로 포함한다.

## 공통 금지 — 이모지

서브에이전트 프롬프트에 "이모지 금지(pipeline-core §15)" 를 명시하고, 레포트·보고·생성 소스 어디에도 이모지를 쓰지 않는다. 훅이 차단하면 텍스트로 고친다.
