---
name: stage7-qa
description: 7단계 QA 자동화 — external/qa-automation(subtree) 의 test-automation 스킬 방법론(인벤토리→생성→실행→triage→결함/위험)으로 target_dir 의 통합 테스트를 자동 생성·실행하고 확정 결함/위험을 리팩토링 요구서(RR)로 변환하는 방법론. /stage7 수행 시 사용.
---

# 7단계 QA 자동화 방법론

목표: `qa-automation` 의 방법론으로 **도구가 스스로 도출한** 통합 테스트를 생성·실행하고, triage 로 확정된 결함과 위험을 RR 로 넘긴다. 5단계(우리가 쓴 시나리오)와 보완 관계다. 서비스 코드는 고치지 않는다.

## 1. 외부 스킬 로드 (항상 최신 것을 읽는다)
1. `config/tools.yaml → qa_automation.path` 를 읽는다. 없으면 안내 후 중단.
2. `<path>/.claude/skills/test-automation/SKILL.md` 와 그 `references/` 전부, `<path>/CLAUDE.md`, `<path>/templates/report_template.md` 를 읽고
   **그 방법론과 등급 체계를 그대로 따른다.** 이 문서는 project-agents 에 맞춘 차이점만 적는다 — 두 문서가 충돌하면 외부 스킬의 절차가 우선하고, 경로·산출물 위치는 이 문서가 우선한다.
3. 모드: 인자 `full|generate-only|run-only`. 기본 full. 러너가 하나도 실행되지 않으면 외부 스킬 규칙대로 generate-only 폴백 + 사유 기록.

## 2. 대상과 경로 차이
- 대상은 `<target_dir>` 전체 (외부 도구의 `input/` 대신). 복사하지 않는다. 외부 도구의 `/qa full <대상경로>` 와 같은 의미.
- 실행: `bash <path>/tools/run_tests.sh <target_dir 절대경로> [--timeout 초] [--keep]`
  (Windows 는 Git Bash). 결과는 **`external/qa-automation/reports/.tests/`**(gitignore) 에 생긴다 → 실행 후 `summary.json`·`summary.md`·`cases.json`·`runs.tsv` 를
  `workspace/<project>/reports/.tests/stage7/` 로 복사해 둔다. 레포트 수치는 반드시 `summary.json` 에서 가져온다 (직접 세지 않는다).
- 집계만 다시 하려면 `python <path>/tools/summarize_results.py <path>/reports/.tests --target <target_dir>`.
- 생성한 테스트는 `<target_dir>/tests/qa/<서비스>/` 에 둔다 (5단계의 `tests/integration/` 과 분리). 외부 스킬의 "생성 테스트 회수 안내" 는 불필요 — target_dir 이 곧 원본 저장소다.
- full 모드는 기존 테스트(2·4단계 단위테스트, 5단계 통합테스트)도 함께 실행된다. 기존 테스트 실패도 결함 근거가 된다.

- **러너 실측(2026-09-22, sample2)**: subtree `run_tests.sh` 가 Maven **멀티모듈**(하위 모듈 `*/target/surefire-reports`)과 **pnpm 워크스페이스**(루트 `pnpm -r test` 는 기계판독 결과 없음)를 집계하지 못해 295·366건이 0 으로 잡혔다 → upstream 수정(`375f125`): 하위 모듈 glob, `packageManager` → corepack 실행, 워크스페이스는 `-r exec vitest run --outputFile=.qa-junit.xml` 로 패키지별 junit, `CI=1`. **오케스트레이터는 stage7 착수 전 러너를 1회 돌려 집계가 0 이 아닌지 확인**하고, 0 이면 도구를 먼저 고친다(에이전트가 우회 집계하면 수치 출처가 흐려진다).
- Playwright 스위트(`tests/integration`·`tests/qa`)는 서버 기동이 필요해 러너 단독 실행에서는 exit=1(환경 문제) — QA 에이전트가 `env-up.sh` 로 따로 돌리고 레포트에 출처를 명시한다.

## 3. 중복·특화 점검
- 5단계 시나리오·결과(`docs/test/*-scenario.md`)와 open RR 을 먼저 읽어 **이미 알려진 결함은 중복 RR 을 만들지 않는다** (레포트에 "기존 RR-xxxx 와 동일" 표시).
- 이 프로젝트에서 특히 볼 것: slice 간 호출 경계, 트랜잭션 경계(부분 실패·미롤백), 페이징·정렬 경계값, 동시성(재고 차감 등), 마이그레이션 재실행, 공통 응답 포맷 계약 불일치.

## 4. triage → RR 변환
외부 스킬 §6 triage 를 거친 뒤에만 RR 을 만든다.

| triage 결과 | 처리 |
|---|---|
| 서비스 결함 (재실행으로 확정) | RR 필수 |
| 결함 추정(미확정) | RR 만들지 않음. 레포트에 "미확정 + 확정에 필요한 정보" |
| 테스트 결함 | 테스트를 고쳐 재실행 (외부 규칙). RR 없음, 수정 이력 한 줄 |
| 환경 문제 | RR 없음. 레포트 "실행 불가 사유" |
| 플래키 | Risk 로 분류 (아래) |

등급 매핑 (외부 CLAUDE.md 등급 → RR severity):

| 외부 등급 | RR severity | RR 생성 |
|---|---|---|
| Blocker | blocker | 필수 |
| Critical | high | 필수 |
| Major | medium | 필수 |
| Minor | low | 필수 |
| Risk (잠재 위험) | low | `파일:라인` 근거가 있는 것만 (노출된 자격증명·트랜잭션 경계·계약 불일치·플래키). 나머지는 레포트에만 |

- `source_stage: 7`, `evidence` 에 실패 테스트명 + `파일:라인` + summary.json 의 케이스 id. `target_stage/layer` 는 추정 원인 위치로.
- ID 채번은 `python tools/rr.py new ...`.

## 4-1. 판단 재검증 (`pipeline-core §21`)
- `python tools/judgment.py list --verify-stage 7` 로 7단계가 확인하기로 한 판단(여러 slice 를 가로지르는 흐름·운영 설정·외부 연동 등, 5단계에서 넘어온 것 포함)을 받는다.
- 판단마다 테스트를 하나 이상 생성·실행하고, 판단 기록의 `criterion` 기준(migration: AS-IS 기능 무손실 + 요구사항 충족, 신규: 요구사항 충족)으로 확인한다.
- `judgment.py verify <JD> --slice <각 확인 slice> --result verified --req-evidence … [--asis-evidence …]`, 틀렸으면 RR 후 `--result failed --rr RR-xxxx`.
- 7단계 착수 시 `judgment.py list --status pending` 에 5단계 몫이 남아 있으면 레포트에 적고 사용자에게 알린다(5단계가 끝나지 않은 slice 다).

## 5. 산출물 및 상태
- 레포트: 외부 `templates/report_template.md` 구조로 `workspace/<project>/reports/<ts>_stage7_all_qa.md` + `python tools/build_report.py` 로 html (생성 여부 확인).
- 외부 스킬 §11 품질 자가 점검을 레포트 제출 전에 수행한다.
- `workspace/<project>/reports/.tests/stage7/` (summary 복사본), `<target_dir>/tests/qa/`, RR 파일들
- `state.yaml → stages.stage7_qa: done`
- 사용자에게 두괄식 보고: 서비스 수, 생성/실행 테스트 수(summary.json 기준), 통과·실패·에러, 확정 결함 수(+미확정 수), RR 목록, 중복 제외 건수, Top 3 우선 조치, 커버리지 공백, 레포트 경로, `/refactor` 안내

## 공통 금지 — 이모지 (전역 규칙 · 예외 없음)

이 방법론으로 만드는 모든 산출물(소스 주석·로그 문구·Mapper 쿼리 주석·yml 주석·DDL `COMMENT`·테스트 이름·레포트·매핑표)에 이모지를 쓰지 않는다.
규칙 전문과 강제 장치는 `pipeline-core §15`. 이 문서의 규칙과 충돌하면 전역 규칙이 우선한다.
