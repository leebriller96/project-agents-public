---
description: 5단계 통합 테스트 — slice 별 통합 테스트 시나리오(없으면 작성)를 근거로 FE↔BE↔DB 연동을 실행·검증하고 결함을 리팩토링 요구서로 만듭니다.
argument-hint: "<slice-id>[,<slice-id>...] | all"
---

# /stage5 — 통합 테스트

인자: `$ARGUMENTS`

## 절차
1. `.claude/skills/pipeline-core/SKILL.md`(핵심)과 절 파일 §1·§4·§5·§8. 선행: 대상 slice 의 `stage2_backend`·`stage4_frontend` 모두 `done`.
2. 대상 slice 결정 (§5). 미충족 slice 는 제외·안내.
3. slice 마다 `stage5_integration: in_progress` → `integration-tester` 호출 (환경 충돌을 피하기 위해 **순차** 실행; 포트·DB 를 공유하므로 병렬 금지). 전달: slice id, target_dir 절대경로, 프로필들.
4. 보고를 받아 `state.yaml` 갱신 (`done`|`blocked`), `refactor_requests` 집계를 `python tools/rr.py stats` 로 다시 계산해 기록.
5. 모든 대상이 끝나면 `stages.stage5_integration` 을 갱신 (전 slice done 이면 done).
6. 사용자에게: slice 별 통과/실패/미실행 수, 실행 환경, 정적 검증 불일치, **생성된 RR 표(id·severity·target_stage/layer·제목)**, 레포트 경로.
7. 안내: RR 이 있으면 `/refactor`, 없으면 `/stage6`.

## 완료 처리 (공통 · pipeline-core §9·§11·§12·§26·§26)

1. 서브에이전트 결과 블록은 훅이 `workspace/<project>/reports/agent-results/<시각>_<에이전트>_5_<slice>.json` 에 저장해 둔다 — 에이전트에게 JSON 을 따로 저장시키지 않고, 값을 손으로 옮겨 적지 않는다.
   `changed_files` 에 소유 밖 파일이 있으면 되돌리고 공통 후보로 돌린다.
2. `python tools/ingest_result.py --json <그 파일> --stage 5 --slice <id> --name <설명> [--body <본문.md>]` — 확인 필요 항목 채번(OI) → 레포트(`pa-meta`, repo 는 git 실측) → 판단 채번(JD).
   본문에는 판단·미완료·다음 단계만 쓰고, 상세는 에이전트 `report_file` 경로로 대신한다.
3. `python tools/gate.py finalize --stage 5 [--slice <id>]` — 게이트 검사(문제만 출력). **FAIL 이면 그 단계를 `done` 으로 기록하지 않는다.**
   `blocker`·`high` 확인 필요 항목은 RR 전환(`oi set <id> converted --rr RR-xxxx`) 또는 사람 승인(`accepted`) 없이 남기지 않는다.
   검사 결과 한 줄을 사용자 보고에 포함한다.

## 공통 금지 — 이모지

서브에이전트 프롬프트에 "이모지 금지(pipeline-core §15)" 를 명시하고, 레포트·보고·생성 소스 어디에도 이모지를 쓰지 않는다. 훅이 차단하면 텍스트로 고친다.
