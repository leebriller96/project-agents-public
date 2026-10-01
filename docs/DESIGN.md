# 설계 문서 (DESIGN)

> 최초 구상(사용자)과 그에 대한 제안을 함께 기록한다. "제안" 표시가 붙은 항목은 아직 확정되지 않았다.

## 1. 최초 구상

| 단계 | 내용 |
|---|---|
| 0 | 정적 문서 투입 — 환경, AS-IS 소스, 요구사항, RFP, 설계/분석 산출물 |
| 1 | 업무별 분류 (초기에 애매하면 건너뛰고 나중에 나눠도 됨) |
| 2 | Backend 개발 — 0단계 문서 근거, slice별 진행 |
| 3 | 공통 소스 추출·리팩토링 (1~3 반복) |
| 4 | Frontend 개발 — 피그마/스토리보드 근거, slice별 진행 |
| 5 | 단위테스트 (시나리오 없으면 먼저 작성) → FE·BE 연결 확인 → 리팩토링 요구서 |
| 6 | 보안취약점 검사 (code-security-auditor) → 리팩토링 요구서 |
| 7 | QA 자동 테스트 (qa-automation) → 리팩토링 요구서 |
| 8 | 산출물 작성 |

## 2. 제안 사항

### 2-1. 단계 간 계약(contract)을 파일로 고정 — **가장 중요**
각 단계의 출력이 다음 단계의 입력이 되므로, 출력을 사람이 읽는 문서가 아니라 **기계가 읽을 수 있는 고정 형식**으로 둔다.

| 산출물 | 위치 | 생산 | 소비 |
|---|---|---|---|
| `PROJECT_BRIEF.md` | workspace/<project>/knowledge/ | 0 | 전 단계 |
| `slices.yaml` | workspace/<project>/slices/ | 1 | 2·4·5, /refactor |
| OpenAPI 계약 (slice별) | target_dir/docs/api/<slice>.yaml | 2 | 4·5·8 |
| `RR-xxxx.yaml` 리팩토링 요구서 | workspace/<project>/refactor-requests/ | 5·6·7 | /refactor → 1~4 |
| `state.yaml` | workspace/<project>/ | 전 단계 | /status, 재개 |

특히 **리팩토링 요구서를 단일 스키마**(`templates/refactor-request.yaml`)로 통일하면 5·6·7단계가 같은 형식을 뱉고,
`/refactor`가 `target_stage`·`slice` 기준으로 묶어 정확한 곳만 다시 돌릴 수 있다.

### 2-2. 0단계에 "요약(Ingest)" 에이전트 추가
문서를 넣어두는 것만으로는 이후 단계에서 컨텍스트가 넘친다. 0단계에서 문서 전체를 읽어
`PROJECT_BRIEF.md`(기술스택·컨벤션·용어집·엔티티 목록·화면 목록·API 후보·비기능 요구)로 압축하고,
이후 단계 에이전트는 brief + 자기 slice 관련 원문만 읽는다. 원문 참조는 `문서명#절` 형태로 남겨 추적 가능하게 한다.

### 2-3. 1단계 승인 게이트
슬라이스 분류는 이후 모든 단계의 축이므로 사람이 `slices.yaml`을 확인·수정한 뒤 진행한다.
차세대라면 AS-IS 패키지/화면/테이블 → slice 매핑표를 함께 만든다.

### 2-4. 2단계 안에 "골격(scaffold) 1회" + 계층 순서 고정
- 최초 1회: 빌드 설정, 공통 응답/에러/로깅/인증 뼈대, 코드 컨벤션을 먼저 만든다.
  → 첫 slice부터 공통 뼈대 위에서 작업하므로 3단계 공통화 부담이 크게 준다.
- slice별 순서: **Migration(DDL) → Mapper/Repository → Service → API → OpenAPI 계약 → 단위테스트**.
  구상의 계층 목록(Mapper·Migration)이 여기 들어간다.
- 차세대일 때 Migration 단계는 AS-IS→TO-BE 테이블·컬럼 매핑표를 산출한다.

### 2-5. 5단계 이름: 단위테스트 → **통합 테스트**
FE·BE 연결 확인은 통합/E2E 성격이다. 단위테스트는 2·4단계의 완료 조건(Definition of Done)으로 넣고,
5단계는 시나리오 기반 통합 테스트에 집중한다. (7단계 qa-automation도 통합 테스트 중심이므로
5단계는 "우리가 쓴 시나리오", 7단계는 "도구가 자동 도출한 시나리오"로 역할을 구분한다.)

### 2-6. developer / reviewer 분리 + 게이트
각 단계에 생성 에이전트와 검토 에이전트를 따로 둔다. 검토는 brief·slices·계약과의 정합성, 컨벤션, 테스트 존재 여부를 본다.
2·3·4단계는 빌드+단위테스트 통과가 완료 조건이며, 실패 시 `state.yaml`에 `blocked`로 기록한다.

### 2-7. 되먹임 경로를 "1단계로 복귀"가 아니라 "target_stage로 라우팅"
요구서마다 `target_stage`·`target_layer`·`slice`가 있으므로 `/refactor`가 그 단계·slice만 다시 실행한다.
slice 재분류가 필요한 경우만 1단계로 간다. 반복 회차(`iteration`)를 올려 같은 요구서가 재적용되지 않게 한다.

### 2-8. 외부 도구 연동 방식
`code-security-auditor`, `qa-automation`은 별도 repo이고 슬래시 명령은 repo 밖에서 호출할 수 없다.
→ `config/tools.yaml`에 경로를 두고, 6·7단계 에이전트가 해당 repo의 `SKILL.md`를 읽어 방법론대로 수행한 뒤,
레포트를 `workspace/<project>/reports/`로 가져와 `tools/report_to_rr.py`(예정)로 요구서로 변환한다.
(대안: 두 repo를 Claude Code 플러그인으로 묶기 — 추후 검토)

## 3. 결정 사항 (2026-09-20)

| 항목 | 결정 |
|---|---|
| 구현 형태 | Claude Code repo — `.claude/commands`(오케스트레이터) + `.claude/agents`(서브에이전트) + `.claude/skills`(방법론). 상태는 파일이므로 나중에 Agent SDK 오케스트레이터를 얹을 수 있다 |
| 생성 소스 위치 | `config/project.yaml → project.target_dir` (별도 repo). 이 repo 의 `workspace/` 에는 메타(brief·slices·RR·레포트·state)만 |
| 병렬 실행 | 허용. `pipeline.parallel`·`max_parallel`. depends_on 위상 정렬로 웨이브를 만들고 웨이브 안에서 동시 실행. 충돌 방지 규칙은 `pipeline-core` §6. 5단계(통합 테스트)는 포트·DB 공유 때문에 순차 |
| 기술 스택 | 제한 없음. config 의 `stack.*.profile` 이 프로필 파일을 고른다. 기본 프로필 `spring-mybatis-mysql`(Java 17/Spring Boot 3/MyBatis/MySQL 8/Flyway) + `react-ts`(React 18/TS/Vite). 프로필이 없으면 범용 규칙 |
| 산출물 | SI 관례 기준 13종 (`stage8-deliverables` 원천 표). config `deliverables.items` 로 선택. md+html 기본, docx 선택 |
| 사람 개입 | stage0 brief 확인(비차단), stage1 slices 승인(차단), stage2 골격 확인(비차단), reviewer 2회 후 잔여 지적(blocked), RR rejected 는 사람만 |

## 4. 남은 과제

- 실제 프로젝트로 stage0→stage2 를 한 번 돌려 스킬 문구·게이트 명령이 현실과 맞는지 검증 (첫 실전 후 프로필 보정)
- `tools/report_to_rr.py`(예정): 6·7단계 외부 도구 레포트를 RR 로 자동 변환 (지금은 에이전트가 직접 `rr.py new` 로 생성)
- 다른 스택 프로필 추가 (예: `spring-jpa-postgres`, `node-nest`, `vue-ts`)
- ~~RR·OI 병렬 채번 충돌~~ → 2026-09-28 `tools/_common.py` 잠금·배타 생성으로 해결 (`tests/test_concurrency.py`)
- ~~생성 코드의 상품화 품질(Javadoc·로깅·Mapper 주석) 기준 부재~~ → 2026-09-28 `tools/quality.py` + gate `productization` 훅
- ~~문서 ↔ 파일 어긋남을 사람이 찾아야 함~~ → 2026-09-28 `tools/selfcheck.py` + CI
- ~~게이트의 테스트 수가 에이전트 자기 기재값~~ → 2026-09-29 `gates[].results`(JUnit XML) 를 `test-evidence` 훅이 직접 집계·대조, 단계 시작 전 결과 파일 재사용 거부 (`tools/_junit.py`)
- ~~게이트 실행이 지침에만 의존~~ → 2026-09-29 `.claude/settings.json` 훅(`tools/hooks/guard.py`): 게이트 미통과 단계의 done 기록 차단, 결과 블록 없는 서브에이전트 종료 차단, 이모지 쓰기 차단 (pipeline-core §16)
- ~~(차세대) 공통 클래스·Mapper 가 업무별로 쪼개지고 private 복제·공통 재변환 반복~~ → 2026-09-29 공통 사용 행렬·공통 계약·common-porter·`common-integrity` 게이트 (pipeline-core §17)
- ~~(brownfield) 범위 외·이전 차수 코드가 공통으로 잡히고 미사용 수천 건이 개별 review, 모듈 간 복사 규약을 표현 못 함~~ → 2026-09-29 행렬 범위 제외(`unassigned.asis`·`pre_pipeline`)·미사용 일괄 `not_migrated`·모듈 차원(`copy`)·gate `slice-scope`(hold·모듈 경로) (pipeline-core §4·§17)
- ~~특성화 테스트를 코드 작성자가 직접 씀(자기 확인 편향)~~ → 2026-09-29 behavior-spec-writer·spec 잠금·equivalence-verifier (pipeline-core §18)
- ~~화면 검증 방식 미정(스크린샷 AI 판정 비용)~~ → 2026-09-29 Playwright 픽셀 비교 + `visual.py` 선별 + ui-verifier (pipeline-core §19)
- ~~slice 크기 편차(작은 업무와 작은 프로젝트급 업무가 같은 방식으로 돎)로 큰 slice 에서 누락·균질화~~ → 2026-09-29 `slice_units.py`(크기 측정·업무 프로세스 기준 unit·slice 내부 사용 행렬·core 선행) + gate `unit-scope`(unit 배정 누락·slice 통합 조건) (pipeline-core §20)
- unit 분할 기준값(`config slicing`)은 추정치다 — 실제 프로젝트에서 에이전트가 원문을 요약하기 시작한 크기를 실측해 보정해야 한다
- 공통 사용 행렬은 정적 분석이다 — 리플렉션·문자열 조립 SQL id·Spring 이벤트 등은 `unresolved`·진입점으로만 드러나고 사람 확인이 필요하다
- 종료 코드(`exit_code`)는 여전히 자기 기재값이다 — 결과 파일이 있으면 실패 수로 교차 확인되지만, 빌드 게이트는 로그 파일 대조가 필요하다
- ~~두 외부 도구를 Claude Code 플러그인으로 묶어 경로 설정 없이 쓰는 방안~~ → 2026-09-21 git subtree 로 `external/` 에 편입 (`tools/sync-external.sh` 로 갱신)
