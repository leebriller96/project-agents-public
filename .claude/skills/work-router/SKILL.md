---
name: work-router
description: 사용자가 /명령 이름 없이 하고 싶은 일을 말로 요청할 때 가장 먼저 읽는 진입점. 요청을 의도로 분류해 알맞은 작업 조합(combo — 기존 /stageN·/run·/rerun·/refactor·/status 와 서브에이전트의 실행 순서)을 고르고, 사람 확인 지점과 게이트를 지키며 진행한다. 예 "3차 범위 들어왔어", "요구사항정의서 새 버전 반영해줘", "처음부터 시작하자", "이 화면 버그 있어", "고객이 오류 제보했어", "테이블 정의서 뽑아줘", "산출물 만들어줘", "진행 상황 알려줘", "주간보고 준비", "오픈 전 점검", "보안 점검 돌려줘", "컬럼 추가해야 해", "이 업무만 다시". 사용자가 /stageN 같은 명령을 직접 입력했거나 파이프라인과 무관한 일반 질문이면 쓰지 않는다.
---

# 작업 라우터 (work-router)

사용자는 명령 이름을 외우지 않는다. "3차 범위가 들어왔다", "고객이 버그를 제보했다" 처럼 **상황**을 말한다.
이 스킬은 그 상황을 이 저장소에 이미 있는 절차의 **조합(combo)** 으로 바꿔 실행한다.

원칙: **새 방법론을 만들지 않는다.** 각 단계의 방법은 해당 `/stageN` 명령·스킬·에이전트가 원본이고, 이 문서는 "어떤 순서로 무엇을 부르는가" 만 정한다.
`CLAUDE.md` 와 `pipeline-core` 의 전역 규칙이 이 문서보다 우선한다.

## 1. 절차

1. **상태 실측**: `config/project.yaml` 존재 여부, `python tools/status.py`, 열린 RR(`python tools/rr.py list --status open`)·확인 필요 항목(`python tools/gate.py oi list --status open`)을 본다.
   상태를 모르고 조합을 고르면 선행 조건이 안 맞는 단계를 부른다.
2. **의도 분류**: §2 표에서 사용자 말과 상태에 맞는 조합 하나를 고른다. 두 조합이 똑같이 맞으면 **한 문장으로 한 번만** 묻는다
   (예: "새 차수 범위인가요, 지금 차수 요구사항의 개정판인가요?"). 한쪽이 분명하면 묻지 않는다.
3. **계획 제시**: 고른 조합 이름, 고른 이유 한 줄, 실행할 단계 순서, **멈출 지점**을 3~6줄로 보여 준다.
   두 단계 이상을 이어 돌리면 `python tools/gate.py plan --to <N> --max <n>` 결과(선행 조건·웨이브·멈춤)를 함께 보여 준다(`/run --dry` 와 같은 계산).
   6·7단계, 전 slice 대상 재실행처럼 비용이 큰 단계가 들어 있으면 시작 전에 확인을 받는다. 그 밖에는 바로 시작한다.
4. **실행**: 조합의 각 단계는 해당 명령 파일(`.claude/commands/*.md`)의 절차를 그대로 수행한다. 완료 처리(`pa-meta`·`gate.py check`·state 갱신)도 그 명령의 규칙을 따른다.
5. **멈춤**: `/run` 의 "반드시 멈추는 지점" 표와 `pipeline-core §10` 사람 확인 지점에서 멈춘다. 멈출 때는 (1) 왜 멈췄는지 (2) 사람이 무엇을 정해야 하는지 (3) 정한 뒤 이어 갈 말(명령)을 보여 준다.
6. **보고**: 수행한 단계, 게이트 결과 요약, 새로 생긴 RR·확인 필요 항목, 다음에 할 일 하나.

## 2. 의도 → 조합

| 사용자 말의 신호 | 상태 조건 | 조합 |
|---|---|---|
| 처음 시작, 새 프로젝트, 문서 넣었어 | brief 없음 | C1 신규 착수 |
| N차 범위, N차 오픈, 추가 개발, 다음 차수, 신규 요구사항 묶음 | brief 있음 | C2 차수 추가 |
| 요구사항정의서 새 버전·개정, 고객이 요건 바꿈, 변경 요청 | brief 있음 | C3 요구사항 변경 |
| 버그, 오류, 안 돼요, 장애, 고객 제보, 화면이 깨짐 | 해당 slice stage2 이상 `done` | C4 결함 처리 |
| 산출물, 정의서, 명세서, 결과서, 추적표, 납품 문서 | — | C5 산출물 |
| 진행 상황, 어디까지, 주간보고, 현황, 남은 것 | — | C6 현황 보고 |
| 오픈 전, 배포 전, 검수 전, 보안 점검, QA | stage5 `done` slice 1개 이상 | C7 오픈 전 점검 |
| 테이블·컬럼 추가·변경, 인덱스, 스키마 | — | C8 DB 변경 |
| 이 업무만 다시, 공통만 다시, 이 계층만 다시 | — | `/rerun` 그대로 (인자는 말에서 뽑고 사유를 받는다) |
| 남은 요구서 처리, RR 반영 | 열린 RR 있음 | `/refactor` 그대로 |

말에 차수·날짜·문서명·업무명이 있으면 그대로 인자로 쓴다. 업무명은 `slices.yaml` 의 id·이름과 대조해 slice id 로 바꾸고, 못 찾으면 후보 id 목록을 보여 준다.

## 3. 조합 정의

각 조합은 "순서 / 멈춤 / 끝났을 때 보고" 로 적는다. 순서의 `/명령` 은 그 명령 파일의 절차를 수행한다는 뜻이다.

### C1 신규 착수
- 순서: `config/project.yaml` 없으면 `.example` 복사를 안내하고 멈춤 → `workspace/<project>/00_inputs/` 파일 확인 → `/stage0` → `/stage1` → (migration) 공통 계약 검토 요청 → 승인 대기 → `/run --to 5`
- 멈춤: stage0 끝(§11 근거 부족 표 확인), stage1 끝(`slices.yaml` 승인·공통 계약 승인은 **사람만**), stage2 골격 끝.
- 보고: brief 경로, slice 표, 승인 방법.

### C2 차수 추가 (예: 2차 운영 중 3차 범위 착수)
처음부터 다시 돌리면 끝난 slice 의 근거 ID 와 추적 체인이 흔들린다. **대조로 넣고, 새 것만 만들고, 닿은 것만 다시 돈다.**
- 순서:
  1. 새 차수 문서를 `workspace/<project>/00_inputs/<차수>/`(예 `phase3/`)에 둔다. 같은 문서의 판이 여럿이면(내부용·고객전달용·작성중) **기준 판을 사용자에게 확인**한다.
  2. `/stage0` 갱신 모드 (`.claude/skills/stage0-ingest/SKILL.md` §6) → `SCOPE_DELTA.md`(신규·변경·삭제·유지)와 `done` slice 영향 항목.
  3. `/stage1 reslice` — 끝난 slice id 는 그대로 두고 신규 요구사항을 기존 slice 에 붙이거나 새 slice 를 만든다(`slice-planner` 재분류 모드).
  4. 승인 대기 (`slices.yaml` `approved: true` 는 사람만).
  5. 변경·삭제가 닿은 `done` slice: `/rerun slice:<id>` — 사유에 `<차수> <요구사항 ID> 반영` 을 적는다. 끝나면 해당 확인 필요 항목을 `python tools/gate.py oi set <id> resolved` 로 닫는다.
  6. 새 slice: `/stage2 <새 id 목록>` → `/stage3`(공통 후보가 생겼으면) → `/stage4 <새 id 목록>` → `/stage5 <새 id 목록>`. 쉼표로 여러 개를 준다(`pipeline-core §5`).
  7. `/stage8 requirements_traceability` 로 추적표를 갱신해 차수별 반영을 확인한다(stage5 `done` 인 경우).
- 멈춤: 판 판정 불가, stage0 §11 신규 모순, stage1 승인, 기존 결정(§12)과 충돌하는 새 요구.
- 보고: 신규·변경·삭제 건수, 새 slice 와 다시 돈 slice, 남은 확인 필요 항목.

### C3 요구사항 변경 (같은 차수 안의 개정판)
- 순서: 개정판을 새 파일로 추가 → `/stage0` 갱신 모드 → 영향 slice 확인 → 새 요구사항이 생겼으면 `/stage1 reslice` + 승인 → 영향 slice 마다 `/rerun slice:<id>` (사유에 요구사항 ID) → `/stage8 requirements_traceability`.
- 영향 slice 가 아직 stage2 전이면 다시 돌릴 것이 없다 — brief 갱신만으로 끝난다.
- 멈춤: 변경이 끝난 slice 의 API 계약을 바꾸는데 다른 slice 가 그 계약을 소비하는 경우 — 영향 범위를 보여 주고 확인받는다.

### C4 결함 처리 (버그·장애·고객 제보)
**코드를 바로 고치지 않는다.** 결함은 요구서(RR)로만 되먹임한다(`CLAUDE.md` 되먹임 원칙).
- 순서:
  1. 증상에서 slice·계층을 특정한다(화면 경로·API 경로·오류 메시지 → `slices.yaml`·`docs/api/<slice>.yaml`).
  2. 재현한다 — 실패하는 명령·테스트·요청과 그 출력이 근거다. 로그·스택트레이스를 받았으면 `파일:라인` 까지 좁힌다.
  3. 재현했으면 `python tools/rr.py new --title "…" --slice <id> --layer <계층> --source 5 --target <2|3|4> --severity <sev> --evidence "파일:라인" --description "…" --fix "…"`.
     재현하지 못했으면 RR 을 만들지 않고 `python tools/gate.py oi new --kind unverified …` 로 남기고 무엇이 더 필요한지(재현 절차·로그·계정 조건) 사용자에게 묻는다.
  4. `/refactor <RR-id>` → 영향 slice `/stage5 <slice>` 로 회귀 확인.
- 운영 장애처럼 급하면 1~3 을 먼저 끝내고 사용자에게 RR 과 영향 범위를 보여 준 뒤 4 로 간다.
- 보고: 재현 근거, RR id, 반영 결과, 회귀 테스트 결과, `risk_surface`(이 수정이 무엇을 깨뜨릴 수 있는가).

### C5 산출물
- 순서: 말에서 산출물을 `config/project.yaml → deliverables.items` 키로 바꾼다 → 선행 조건 확인(stage5 `done`) → `/stage8 <키 목록>`.
- 말 → 키: 요구사항 추적표 `requirements_traceability` · 아키텍처 정의서 `architecture` · 업무 분류표 `slice_definition` · 테이블 정의서·ERD `table_definition` ·
  API 명세서·인터페이스 정의서 `api_spec` · 화면 정의서·화면 설계서 `screen_definition` · 공통 모듈 명세 `common_module_spec` ·
  단위테스트 결과서 `unit_test_result` · 통합테스트 결과서 `integration_test_result` · 보안 점검 결과서 `security_result` · QA 결과서 `qa_result` ·
  AS-IS/TO-BE 매핑표 `asis_tobe_mapping` · 배포·운영 가이드 `deploy_guide`.
- 선행 조건이 안 되면 만들지 않고 "무엇이 없어서 못 만드는가, 어느 단계를 돌려야 하는가" 를 보여 준다. 원천 없는 내용을 채워 넣지 않는다.
- 회사·고객 양식(엑셀·워드 서식)이 따로 있으면 양식 파일을 `00_inputs/` 에 두라고 안내하고, 형식은 `deliverables.format` 에 따른다.

### C6 현황 보고
- 순서: `/status` 절차 → `python tools/rr.py stats` → `python tools/gate.py trace` 끊김 수.
- 주간보고 요청이면 대화에 다음 틀로 정리한다: 이번 기간 완료(단계·slice) / 진행 중 / 막힘(blocked 사유·사람 결정 대기) / 열린 결함(RR severity 별) / 다음 기간 계획.
  기간 판단의 근거는 `state.yaml → log` 의 시각이다. 파일로 남기라는 요청이 있을 때만 `workspace/<project>/reports/` 에 KST 접두어로 저장한다.
- 이 조합은 아무것도 실행하거나 바꾸지 않는다.

### C7 오픈 전 점검
- 순서: 열린 RR·`blocker`/`high` 확인 필요 항목 확인 → `/stage6` → `/stage7` → `/refactor` → 영향 slice `/stage5` → `python tools/gate.py trace --strict` → `/stage8 unit_test_result,integration_test_result,security_result,qa_result,deploy_guide`
- 6·7단계는 비용이 크므로 시작 전에 확인을 받는다(`/run` 안전 규칙과 같다).
- 멈춤: `blocker`·`high` 가 열린 채 남으면 오픈 가능 판정을 내리지 않는다 — 남은 항목과 결정할 사람을 보여 준다.

### C8 DB 변경 (테이블·컬럼·인덱스)
- 먼저 근거를 확인한다. 요구사항 변경에서 온 것이면 C3, 새 차수 범위면 C2 로 간다 — 스키마만 따로 바꾸면 추적 체인이 끊긴다.
- 근거가 이미 brief 에 있고 소유 slice 가 분명하면: `/rerun slice:<id> stages:2,5` (마이그레이션은 slice 고유 버전 규칙, `pipeline-core §6`).
  migration 모드면 `sql-migrator` 경로를 탄다(`/rerun layer:backend/mapper slice:<id>`).
- 여러 slice 가 쓰는 테이블이면 공통 계약·공통화 소유다 — `/rerun common` 또는 공통 요청(CR)으로 돌리고 업무 slice 에서 고치지 않는다.
- 끝나면 `/stage8 table_definition` 갱신을 제안한다.

## 4. 하지 않는 것

- 사람 전용 결정을 대신하지 않는다: `slices.yaml` 승인, 공통 계약 `approve`, spec 잠금 해제, RR `rejected`, 확인 필요 항목 `accepted`. 이 명령들은 사용자가 직접 실행하도록 안내만 한다.
- 게이트를 건너뛰거나 테스트를 줄여 조합을 끝내지 않는다. 막히면 멈추는 것이 정상 동작이다.
- 결함을 RR 없이 코드로 바로 고치지 않는다(C4).
- `workspace/<project>/`·`target_dir` 내용을 이 저장소에 커밋하지 않는다.
- 파이프라인과 무관한 질문(일반 개념 설명·코드 조각 질문)에 조합을 억지로 붙이지 않는다 — 그냥 답한다.

## 공통 금지 — 이모지 (전역 규칙 · 예외 없음)

조합을 실행하며 만드는 레포트·보고·서브에이전트 프롬프트·생성 소스 어디에도 이모지를 쓰지 않는다. 서브에이전트 프롬프트에는 "이모지 금지(pipeline-core §15)" 를 명시한다.
규칙 전문과 강제 장치는 `pipeline-core §15`. 이 문서의 규칙과 충돌하면 전역 규칙이 우선한다.
