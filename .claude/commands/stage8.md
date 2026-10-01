---
description: 8단계 산출물 — 파이프라인 결과물을 재가공해 config 에 지정된 SI 산출물(요구사항 추적표, 아키텍처·테이블·API·화면 정의서, 테스트/보안/QA 결과서 등)을 생성합니다.
argument-hint: "[all|<산출물 키>[,<키>...]] (기본 all)"
---

# /stage8 — 산출물 작성

인자: `$ARGUMENTS`

## 절차
1. `.claude/skills/pipeline-core/SKILL.md` §1. 선행: `stage5_integration: done`. 6·7 미완료면 경고만 하고 진행(해당 결과서는 "미수행" 표시).
2. `config/project.yaml → deliverables` 에서 대상 목록 결정 (인자로 키를 주면 그것만).
3. `stages.stage8_deliverables: in_progress` → `deliverable-writer` 호출. 전달: target_dir 절대경로, 대상 목록, 형식, iteration.
4. 보고를 받아 `state.yaml` 갱신 (`done`).
5. 사용자에게: 생성 산출물 표(번호·이름·경로), 원천 없음 목록(어느 단계를 돌려야 하는지), 끊긴 추적 항목 수, open RR 수.
6. 안내: open RR 이 남아 있으면 `/refactor` 후 `/stage8` 재생성 권장.

## 완료 처리 (공통 · pipeline-core §9·§11·§12)

1. 서브에이전트 보고의 `pa-agent-result` 블록에서 게이트·변경 파일·확인 필요 항목을 그대로 가져온다.
   `changed_files` 에 소유 밖 파일이 있으면 되돌리고 공통 후보로 돌린다.
2. 확인 필요 항목은 `python tools/gate.py oi new --stage 8 --slice <id> --kind <kind> --severity <sev> --summary "…" --evidence "…" --target <닫을 단계>` 로 채번한다.
   `blocker`·`high` 는 RR 전환(`oi set <id> converted --rr RR-xxxx`) 또는 사람 승인(`accepted`) 없이 남기지 않는다.
3. 레포트 끝에 `pa-meta` 블록을 붙인다 (`python tools/gate.py template --stage 8 --slice <id> --agent orchestrator` 로 골격 생성 후 실제 값으로 채움).
3-1. **추적 체인 전수 대조**: `python tools/gate.py trace --strict` 를 실행한다. 끊긴 연결(요구사항 ID 를 인용한 테스트 부재, 계약 파일 부재)이 있으면
   산출물에 "끊긴 추적" 으로 싣고, 8단계에서 메울 수 있는 것(문서 인용 누락)은 메운다. 코드·테스트가 없어서 끊긴 것은 확인 필요 항목으로 남긴다.
4. `python tools/gate.py check --stage 8 [--slice <id>]` 를 실행한다. **FAIL 이면 그 단계를 `done` 으로 기록하지 않는다.**
   검사 결과(통과 / FAIL 항목)를 사용자 보고에 한 줄로 포함한다.

## 공통 금지 — 이모지

서브에이전트 프롬프트에 "이모지 금지(pipeline-core §15)" 를 명시하고, 레포트·보고·생성 소스 어디에도 이모지를 쓰지 않는다. 훅이 차단하면 텍스트로 고친다.
