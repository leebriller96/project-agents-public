---
description: 8단계 산출물 — 파이프라인 결과물을 재가공해 config 에 지정된 SI 산출물(요구사항 추적표, 아키텍처·테이블·API·화면 정의서, 테스트/보안/QA 결과서 등)을 생성합니다.
argument-hint: "[all|<산출물 키>[,<키>...]] (기본 all)"
---

# /stage8 — 산출물 작성

인자: `$ARGUMENTS`

## 절차
1. `.claude/skills/pipeline-core/SKILL.md`(핵심)과 절 파일 §1. 선행: `stage5_integration: done`. 6·7 미완료면 경고만 하고 진행(해당 결과서는 "미수행" 표시).
2. `config/project.yaml → deliverables` 에서 대상 목록 결정 (인자로 키를 주면 그것만).
3. `stages.stage8_deliverables: in_progress` → `deliverable-writer` 호출. 전달: target_dir 절대경로, 대상 목록, 형식, iteration.
4. 보고를 받아 `state.yaml` 갱신 (`done`).
5. 사용자에게: 생성 산출물 표(번호·이름·경로), 원천 없음 목록(어느 단계를 돌려야 하는지), 끊긴 추적 항목 수, open RR 수.
6. 안내: open RR 이 남아 있으면 `/refactor` 후 `/stage8` 재생성 권장.

## 납품 소스 패키지는 9단계

납품 패키징(주석·문서 정리, AI 산출물 제거)은 `/stage9` 로 따로 돌린다(`stage9-packaging`). 인자로 `package` 가 오면 `/stage9` 를 안내한다.

## 완료 처리 (공통 · pipeline-core §9·§11·§12·§26·§26)

1. 서브에이전트 결과 블록은 훅이 `workspace/<project>/reports/agent-results/<시각>_<에이전트>_8_<slice>.json` 에 저장해 둔다 — 에이전트에게 JSON 을 따로 저장시키지 않고, 값을 손으로 옮겨 적지 않는다.
   `changed_files` 에 소유 밖 파일이 있으면 되돌리고 공통 후보로 돌린다.
2. `python tools/ingest_result.py --json <그 파일> --stage 8 --slice <id> --name <설명> [--body <본문.md>]` — 확인 필요 항목 채번(OI) → 레포트(`pa-meta`, repo 는 git 실측) → 판단 채번(JD).
   본문에는 판단·미완료·다음 단계만 쓰고, 상세는 에이전트 `report_file` 경로로 대신한다.
3. `python tools/gate.py finalize --stage 8 [--slice <id>]` — 게이트 검사(문제만 출력). **FAIL 이면 그 단계를 `done` 으로 기록하지 않는다.**
   `blocker`·`high` 확인 필요 항목은 RR 전환(`oi set <id> converted --rr RR-xxxx`) 또는 사람 승인(`accepted`) 없이 남기지 않는다.
   검사 결과 한 줄을 사용자 보고에 포함한다.

## 공통 금지 — 이모지

서브에이전트 프롬프트에 "이모지 금지(pipeline-core §15)" 를 명시하고, 레포트·보고·생성 소스 어디에도 이모지를 쓰지 않는다. 훅이 차단하면 텍스트로 고친다.
