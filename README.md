# project-agents

대규모 서비스 개발(풀스택·차세대 등)을 **단계(stage) × 업무(slice) × 계층(layer)** 으로 쪼개어
에이전트가 선형 파이프라인으로 수행하고, 검증 단계에서 나온 결함을 **리팩토링 요구서**로 되먹임하여
반복할수록 완성도가 높아지도록 설계한 Claude Code repo입니다.

```
0 준비 ─> 1 업무분류 ─> 2 Backend ─> 3 공통화 ─> 4 Frontend ─> 5 통합테스트 ─> 6 보안 ─> 7 QA ─> 8 산출물
                ^                                                  │           │        │
                └──────────────── 리팩토링 요구서 (refactor-requests) <──────────┴────────┘
```

## 단계 개요

| 단계 | 이름 | 입력 | 출력 | 게이트 |
|---|---|---|---|---|
| 0 | 준비 (Ingest) | RFP·요구사항·설계/분석 산출물·피그마/스토리보드·환경 정보·(차세대) AS-IS 소스 | `workspace/<project>/knowledge/PROJECT_BRIEF.md` — 기술스택·컨벤션·용어집·엔티티/화면/API 목록 요약 | 사람 확인 |
| 1 | 업무 분류 (Slicing) | 0단계 + AS-IS | `workspace/<project>/slices/slices.yaml` — 슬라이스 목록·의존관계·우선순위 (+ 데이터 모델 초안) | **사람 승인** |
| 2 | Backend | brief + slice | (최초 1회) 프로젝트 골격 → slice별 Migration → Mapper → Service → API + **OpenAPI 계약** + 단위테스트 | 빌드·테스트 통과 |
| 3 | 공통화 리팩토링 | 2단계 결과 전체 | common 모듈 추출, 중복 제거, 컨벤션 정렬 | 빌드·테스트 통과 |
| 4 | Frontend | 피그마/스토리보드 + OpenAPI 계약 | slice별 화면·컴포넌트·API 클라이언트 + 단위테스트 | 빌드·테스트 통과 |
| 5 | 통합 테스트 | FE + BE | 테스트 시나리오 문서(없으면 생성) → 실행 → **리팩토링 요구서** | — |
| 6 | 보안 점검 | 전체 소스 | `code-security-auditor` 실행 → **리팩토링 요구서** | — |
| 7 | QA 자동화 | 전체 소스 | `qa-automation` 실행 → **리팩토링 요구서** | — |
| 8 | 산출물 | 전체 | 설계서·API 명세·테이블 정의서·테스트 결과서 등 | — |

- 1~4단계는 slice 단위로 반복하고, 5~7단계에서 나온 요구서는 `target_stage`/`target_layer`가 지정되어
  해당 단계·계층만 다시 돈다 (무조건 1단계부터 되돌아가지 않음).
- 각 단계는 **developer 에이전트 → reviewer 에이전트** 순으로 실행되며, 게이트(빌드·테스트)를 통과해야 다음 단계로 넘어간다.
- 게이트 통과는 문장이 아니라 **증거**로 판정한다. 레포트 끝의 `pa-meta` 블록(실행 명령·종료 코드·테스트 개수·git HEAD·확인 필요 항목)을
  `python tools/gate.py check --stage <N> [--slice <id>]` 가 실제 git·파일과 대조한다 (`templates/report-meta.md`).
- 결함은 리팩토링 요구서(RR), **아직 확인되지 않은 것**은 확인 필요 항목(`open-items.yaml`)으로 남아 다음 단계가 닫는다.
- 단계를 늘려도 **같은 축**에서만 검증하면 새 결함은 나오지 않는다. 1단계가 slice 마다 `traits` 를 정하고,
  그것이 요구하는 검증 축(`unit`·`module`·`real-db`·`real-server`·`browser`·`concurrency`·`security-static`)이
  닫혔는지를 `gate.py` 가 대조한다 (pipeline-core §14).
- `/run` 은 게이트 판정으로 다음 단계를 자동 진행하고, 사람 승인 지점·FAIL 에서만 멈춘다.
- 핵심 원칙은 지침만이 아니라 **훅이 도구 호출 시점에 강제**한다(`.claude/settings.json`): 게이트를 통과하지 못한 단계를 `done` 으로
  기록하는 편집, `pa-agent-result` 없이 끝나는 서브에이전트, 이모지가 든 쓰기를 막는다. 훅은 `python` 이 PATH 에 있어야 동작한다.
- **(차세대) 공통을 먼저 확정한다**: 1단계 승인 직후 `common_usage.py` 가 "어느 업무가 공통의 어느 메서드·SQL 을 쓰는가" 를 정적 분석으로 계산하고,
  `common_contract.py` 로 공통 계약을 만들어 **사람이 승인**한다. `/stage2 common-port` 에서 `common-porter` 가 공통을 클래스 단위로 먼저 변환하고,
  업무 slice 는 계약을 소비만 한다(복제·공통 수정은 gate 가 차단, 없는 공통은 공통 요청 CR). 공통 클래스가 업무별로 쪼개지거나 private 으로 복제되는 문제를 막는다 (pipeline-core §17).
- **기대 동작 테스트는 코드 작성자가 아닌 에이전트가 먼저 쓰고 잠근다**: 계약 선행(시그니처·스텁) → `behavior-spec-writer` 가 AS-IS 동작 계약만 보고 spec 작성 →
  `spec_lock.py` 로 해시 잠금 → 구현 → `equivalence-verifier` 가 독립 재실행·결함 주입 표본으로 판별력 확인. 잠금 해제는 사람만 (pipeline-core §18).
- **화면 검증은 기계가 실행·판정하고 AI 는 고른 이미지만 본다**: Playwright 가 로컬에서 BE·FE 를 띄워 DOM·콘솔·네트워크·픽셀 비교를 하고,
  `visual.py` 가 새·변경 기준 이미지와 실패 diff 만 골라 토큰을 추정한다. `ui-verifier` 는 그것만 검토·승인한다 (pipeline-core §19).
- **큰 slice 는 필요할 때만 업무 프로세스 기준 unit 으로 나눈다**: `slice_units.py measure` 가 AS-IS 입력 토큰 추정·API·화면·SQL·상태 전이 수로
  분할 후보를 고르고, 분할한 slice 는 `core`(여러 unit 이 쓰는 코드를 먼저 — 공용 클래스는 통째로, 컨트롤러·서비스 구현체는 공유 메서드만) → 상태 전이를 나눠 가진 `step` → 조회 `query` 순으로 돈다.
  slice 는 계약·소유·검증의 단위로 남고, 완료는 모든 unit 완료 + unit 을 가로지르는 흐름 테스트 + AS-IS 전수 대조를 통과해야 한다 (pipeline-core §20).
- **이모지 금지(예외 없음)**: 생성 소스(주석·Mapper 쿼리 주석·yml 주석·DDL COMMENT)·레포트·지침 어디에도 쓰지 않는다 (pipeline-core §15).

## 디렉토리 구조

```
project-agents/
├── CLAUDE.md                 # 파이프라인 운영 원칙 (Claude Code가 자동 인식)
├── README.md
├── docs/DESIGN.md            # 상세 설계 · 열린 질문
├── docs/LESSONS.md           # 실행 이력·교훈 (재실행마다 누적)
├── config/
│   ├── project.yaml.example  # 프로젝트 설정 (스택·모드·대상 repo 경로)
│   └── tools.yaml            # 외부 도구 경로 (external/ 상대경로)
├── .claude/
│   ├── settings.json         # 훅: 이모지 쓰기·게이트 미통과 done 기록·결과 블록 없는 에이전트 종료를 차단 (pipeline-core §16)
│   ├── commands/             # /stage0 … /stage8, /run, /refactor, /rerun, /status (오케스트레이터)
│   ├── agents/               # 서브에이전트 16개 (ingest-analyst, slice-planner, backend-developer, backend-reviewer,
│   │                         #   sql-migrator, common-porter, behavior-spec-writer, equivalence-verifier,
│   │                         #   common-refactorer, frontend-developer, frontend-reviewer, ui-verifier,
│   │                         #   integration-tester, security-auditor, qa-runner, deliverable-writer)
│   └── skills/               # pipeline-core(공통 규칙) + work-router(말 → 작업 조합) + 단계별 방법론 + 스택 프로필
├── templates/                # state·slices·PROJECT_BRIEF·리팩토링 요구서·테스트 시나리오 템플릿
├── tools/                    # rr.py(요구서 관리), gate.py(게이트 검증·확인필요 항목·비밀정보 스캔),
│                             #   quality.py(상품화 품질 점검), selfcheck.py(저장소 정합성), status.py(상태 요약),
│                             #   build_report.py(md→html), surefire_sum.py, sync-external.sh, _common.py(공통 유틸),
│                             #   _emoji.py(이모지 판정 기준), _junit.py(테스트 결과 집계), hooks/guard.py(훅),
│                             #   common_usage.py(공통 사용 행렬), common_contract.py(공통 계약·공통 요청·복제 검사),
│                             #   _javasrc.py(Java 구조 분석), spec_lock.py(기대 동작 테스트 잠금), visual.py(화면 검증 대상 선별),
│                             #   slice_units.py(큰 slice 의 크기 측정·unit 분할 검증·실행 순서),
│                             #   backup.py(git 에 없는 config·workspace/<project>/ 백업·검증·복원)
├── tests/                    # tools/ 회귀 테스트 (pytest) — CI(.github/workflows/tools-ci.yml)가 push 마다 실행
├── external/                 # git subtree: qa-automation, code-security-auditor
└── workspace/<project>/      # 프로젝트별 작업 공간 (커밋하지 않음, <project> = config 의 project.name)
    ├── 00_inputs/            # 0단계 정적 문서·AS-IS 소스
    ├── knowledge/            # PROJECT_BRIEF.md 등 요약 지식
    ├── slices/               # slices.yaml
    ├── refactor-requests/    # RR-0001.yaml …
    ├── open-items.yaml       # 확인 필요 항목(미검증·결정 대기·근거 부족)
    ├── reports/              # 단계별 실행 레포트
    ├── deliverables/         # 8단계 산출물
    └── state.yaml            # 파이프라인 상태 (slice × stage 진행도, 반복 횟수)
```

생성되는 실제 서비스 소스는 `config/project.yaml`의 `target_dir`(별도 repo)에 쓴다.

## 빠른 시작

```bash
git clone https://github.com/leebriller96/project-agents.git
cd project-agents
python -m pip install -r tools/requirements.txt      # pyyaml, markdown
cp config/project.yaml.example config/project.yaml   # 프로젝트명·모드·target_dir·스택 수정
```

`workspace/<project>/00_inputs/` 에 문서(RFP·요구사항·설계 산출물·피그마 export·스토리보드)와 (차세대라면) `asis/` 소스를 넣은 뒤,
이 디렉토리에서 Claude Code 를 열고:

```text
/stage0                 # 준비: PROJECT_BRIEF.md 생성 → 근거 부족·모순 표 확인
/stage1                 # 업무 분류 → workspace/<project>/slices/slices.yaml 검토 후 approved: true 로 변경
/stage2 common-port     # (차세대) 공통 계약 승인 후 공통 선행 변환 — 업무 slice 보다 먼저
/stage2 all             # Backend: 골격 1회 + slice 별(계약 선행 → 잠긴 기대 동작 테스트 → 구현 → 검토 → 동등성 검증)
/stage3                 # 공통화 리팩토링
/stage4 all             # Frontend: 골격 1회 + slice 별 개발·검토·게이트
/stage5 all             # 통합 테스트 → 리팩토링 요구서(RR)
/refactor               # 열린 RR 을 target_stage·slice 별로 반영 → 후속 단계 상태 되돌림
/stage6                 # 보안 점검 (code-security-auditor 방법론) → RR
/stage7                 # QA 자동화 (qa-automation 방법론) → RR
/stage8                 # 산출물 생성
/status                 # 진행 상태 + 다음 실행 가능한 명령
/rerun slice:<id>       # 특정 업무만 다시 (stage2→4→5), /rerun common (공통만), /rerun layer:backend/mapper slice:<id> (한 계층만)
```

### 도구 점검

```bash
python tools/quality.py [target_dir]     # 생성 소스의 상품화 품질: Javadoc·로거·traceId·Mapper 주석·콘솔 출력·민감정보 로깅
python tools/quality.py --rules          # 규칙 목록 (2·3·4단계 gate 의 productization 훅이 같은 규칙을 쓴다)
python tools/selfcheck.py                # 이 저장소의 문서 ↔ 파일 정합성 (에이전트·스킬·도구·템플릿 참조, 옛 경로)
python tools/backup.py create            # config·workspace/<project>/ 를 저장소 밖(backup.dir)에 zip 백업 (list·verify·restore)
python -m pip install pytest && python -m pytest -q   # tools/ 회귀 테스트 (CI: .github/workflows/tools-ci.yml, Linux·Windows)
```

한 바퀴 돌렸다고 끝이 아니다 — 문제가 보이면 `/rerun`·`/refactor` 로 **해당 업무·계층만** 다시 돌리고, 그때마다 드러난 지침을 스킬에 반영한다(`docs/LESSONS.md`).

`/stage2 order,member` 처럼 slice 를 지정할 수 있고, `/stage2 scaffold` 는 골격만 다시 만든다.

### 명령 이름 없이 말로 시키기

명령을 외우지 않아도 된다. 상황을 말하면 `work-router` 스킬이 알맞은 **작업 조합**(기존 명령·에이전트의 실행 순서)을 골라 계획을 보여 주고 진행한다.
사람 승인 지점과 게이트는 그대로 멈춘다. 새 방법론이 아니라 이미 있는 절차를 순서대로 부르는 것이다.

| 이렇게 말하면 | 조합 | 하는 일 |
|---|---|---|
| "문서 넣었어, 시작하자" | C1 신규 착수 | `/stage0` → `/stage1` → 승인 → `/run --to 5` |
| "3차 범위 들어왔어" | C2 차수 추가 | `/stage0` 갱신 모드(요구사항 신규·변경·삭제 대조) → `/stage1 reslice` → 승인 → 닿은 slice `/rerun` + 새 slice 개발 → 추적표 갱신 |
| "요구사항정의서 새 버전 반영해줘" | C3 요구사항 변경 | 갱신 모드 대조 → 영향 slice 만 `/rerun` |
| "고객이 오류 제보했어" | C4 결함 처리 | 재현 → RR 채번 → `/refactor` → `/stage5` 회귀 확인 (코드를 바로 고치지 않는다) |
| "테이블 정의서 뽑아줘" | C5 산출물 | 말을 산출물 키로 바꿔 `/stage8 <키>` |
| "진행 상황 / 주간보고" | C6 현황 보고 | `/status` + RR·추적 체인 요약 (아무것도 바꾸지 않음) |
| "오픈 전 점검" | C7 오픈 전 점검 | `/stage6` → `/stage7` → `/refactor` → `/stage5` → 결과서 |
| "컬럼 추가해야 해" | C8 DB 변경 | 근거 확인 후 C2·C3 또는 소유 slice `/rerun` |

차수 추가·요구사항 변경의 대조 규칙은 `.claude/skills/stage0-ingest/SKILL.md` §6(갱신 모드) 이 원본이다.

## 기술 스택

`config/project.yaml → stack` 이 결정한다. 기본 프로필은 **Java 17 / Spring Boot 3 / MyBatis / MySQL 8 / Flyway** (`spring-mybatis-mysql`) 와
**React 18 / TypeScript / Vite** (`react-ts`) 이며, 규칙은 `.claude/skills/stage2-backend/profiles/`, `stage4-frontend/profiles/` 에 있다.
다른 스택을 쓰려면 프로필 파일을 하나 추가하고 config 의 `profile` 값을 바꾸면 된다. 프로필이 없어도 범용 규칙으로 동작한다.

## 산출물 (8단계)

`config/project.yaml → deliverables.items` 로 선택한다. 기본 목록: 요구사항 추적표(RTM), 아키텍처 정의서, 업무 분류표, 테이블 정의서+ERD,
API 명세서, 화면 정의서, 공통 모듈 명세, 단위/통합/보안/QA 결과서, (차세대) AS-IS/TO-BE 매핑표, 빌드·배포·운영 가이드.
형식은 md 원본 + html (`tools/build_report.py`), 필요 시 docx.

## 외부 도구 (external/ — git subtree)

6·7단계가 쓰는 도구 repo 는 `external/` 아래에 **git subtree** 로 편입되어 있어 이 repo 하나만 clone 하면 된다.

- `external/code-security-auditor` ← [code-security-auditor](https://github.com/leebriller96/code-security-auditor) — 6단계 보안 점검
- `external/qa-automation` ← [qa-automation](https://github.com/leebriller96/qa-automation) — 7단계 QA 자동화

upstream 갱신: `bash tools/sync-external.sh [qa|security]`. 의존성: `python -m pip install -r external/<도구>/tools/requirements.txt`.

상세 설계와 아직 결정되지 않은 사항은 [docs/DESIGN.md](docs/DESIGN.md) 참고.
