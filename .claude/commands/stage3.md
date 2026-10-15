---
description: 3단계 공통화 리팩토링 — 완료된 slice 들에서 공통 코드를 common 모듈로 추출하고 컨벤션을 정렬합니다. 동작(테스트 결과)은 보존합니다.
argument-hint: "(인자 없음)"
---

# /stage3 — 공통화 리팩토링

## 절차
1. `.claude/skills/pipeline-core/SKILL.md`(핵심)과 절 파일 §1·§7 (선행: `stage2_backend: done` 인 slice 1개 이상).
2. `stages.stage3_common: in_progress`, log 에 회차(iteration) 기록.
3. `common-refactorer` 호출. 전달: target_dir, 프로필, `done` slice 목록, `workspace/<project>/reports/common-candidates.md` 경로.
4. 보고 후 `backend-reviewer` 를 `common` 대상으로 호출. FAIL 이면 지적 목록·대상 파일을 주고 `common-refactorer` 를 새로 호출 (최대 2회, pipeline-core §26) → 잔여 시 `blocked`.
5. `state.yaml` 갱신 (`done`|`blocked`). 보류된 후보 중 향후 필요한 것은 RR(`source_stage: 3`) 로 남긴다.
6. 사용자에게: 추출 목록, 보류 목록과 사유, 기준선 대비 테스트 결과, `common-module-spec.md` 경로.
7. 안내: `/stage4 <slice>` 또는 새 slice 가 있으면 `/stage2 <slice>`.

## 완료 처리 (공통 · pipeline-core §9·§11·§12·§26·§26)

1. 서브에이전트 결과 블록은 훅이 `workspace/<project>/reports/agent-results/<시각>_<에이전트>_3_<slice>.json` 에 저장해 둔다 — 에이전트에게 JSON 을 따로 저장시키지 않고, 값을 손으로 옮겨 적지 않는다.
   `changed_files` 에 소유 밖 파일이 있으면 되돌리고 공통 후보로 돌린다.
2. `python tools/ingest_result.py --json <그 파일> --stage 3 --slice <id> --name <설명> [--body <본문.md>]` — 확인 필요 항목 채번(OI) → 레포트(`pa-meta`, repo 는 git 실측) → 판단 채번(JD).
   본문에는 판단·미완료·다음 단계만 쓰고, 상세는 에이전트 `report_file` 경로로 대신한다.
3. `python tools/gate.py finalize --stage 3 [--slice <id>]` — 게이트 검사(문제만 출력). **FAIL 이면 그 단계를 `done` 으로 기록하지 않는다.**
   `blocker`·`high` 확인 필요 항목은 RR 전환(`oi set <id> converted --rr RR-xxxx`) 또는 사람 승인(`accepted`) 없이 남기지 않는다.
   검사 결과 한 줄을 사용자 보고에 포함한다.

## 공통 금지 — 이모지

서브에이전트 프롬프트에 "이모지 금지(pipeline-core §15)" 를 명시하고, 레포트·보고·생성 소스 어디에도 이모지를 쓰지 않는다. 훅이 차단하면 텍스트로 고친다.
