---
name: pipeline-core
description: project-agents 파이프라인의 공통 규칙 — 설정·상태·slice·리팩토링 요구서 파일 형식, 게이트, 병렬 실행, 레포트 규칙. 모든 /stageN·/refactor·/status 명령이 가장 먼저 읽는다.
---

# 파이프라인 공통 규칙 (pipeline-core)

모든 단계 명령과 에이전트는 이 문서를 먼저 읽고 따른다.

## 1. 시작 절차 (모든 명령 공통)

0. `workspace/<project>/HANDOFF.md` 를 읽는다(없으면 `templates/HANDOFF.md` 로 만든다). 사용자 원칙·브랜치·업로드 규칙·세션 시작 루틴이 여기 있다 - 거기 적힌 세션 시작 루틴(예: 기준 브랜치 최신화)을 먼저 수행한다.
   HANDOFF.md 의 진행·결정 절은 **자주** 갱신한다 — 단계 끝·사람 결정, 작업 단위 하나의 끝(서브에이전트 결과 수신·커밋·게이트 판정·RR/OI/JD 생성),
   긴 작업(서브에이전트·전체 빌드·테스트) 시작 전, 사용자에게 응답을 마치기 전. "현재 작업 / 다음 순서" 와 "마지막 갱신" 시각을 같이 고친다.
   세션 대화 기록은 언제든 사라질 수 있으므로, 지금 세션이 끊겨도 새 세션이 HANDOFF·state.yaml 만 읽고 이어 갈 수 있는 상태를 유지한다.
   여러 개발자가 함께 올리는 **공유 통합 브랜치**가 있으면(HANDOFF 에 적는다) 세션 시작·긴 작업 착수 전·긴 작업 중간·push 직전에 받아
   다른 개발자 변경을 분석한다(공통 파일·공통 계약 tobe·잠긴 spec 대상·업무 겹침·2차 파일·외부 테이블 CREATE·비밀값). 리스크를 사용자에게 짧게 보고하고
   로컬 작업 브랜치·업로드 브랜치에 머지한 뒤 빌드·전체 테스트·잠긴 spec 을 돌린다. 다른 개발자가 바꾼 공통·의존 소스는 그쪽을 받아 쓴다.
   공유 브랜치 push 는 직전에 다시 받아 빨리감기로만 한다(강제 push 금지).
   **업로드 권한은 HANDOFF 의 업로드 절과 target_dir 지침이 함께 정한다** — 둘이 다르면 올리지 않고 사용자에게 먼저 묻는다.
   한쪽을 고쳤으면 같은 회차에 다른 쪽도 고친다(실측: target_dir 규약을 push 허용으로 바꾸고 HANDOFF 를 두고 와 확인 필요 항목이 하나 생겼다).
1. `config/project.yaml` 을 읽는다. 없으면 "config/project.yaml.example 을 복사해 config/project.yaml 을 만들어 주세요" 안내 후 **중단**.
2. `config/tools.yaml` 을 읽는다 (6·7단계만 필수).
3. `workspace/<project>/state.yaml` 을 읽는다. 없으면 `templates/state.yaml` 을 복사해 project·mode 를 채우고 slices 는 비워 둔다.
4. 선행 단계 조건을 확인한다 (아래 §4). 미충족이면 무엇을 먼저 실행해야 하는지 안내 후 중단.
5. 시작 시 `state.yaml` 의 해당 항목을 `in_progress` 로 바꾸고 `log` 에 한 줄 남긴다.
6. 끝나면 결과(`done` | `blocked`)와 `updated_at` 을 갱신하고, 레포트를 `workspace/<project>/reports/` 에 남긴다.
7. 서브에이전트를 호출할 때 프롬프트에 **§15 이모지 금지**를 명시한다(에이전트 파일에도 있지만 프롬프트가 먼저 읽힌다).

## 2. 경로

- `target_dir`: `config/project.yaml → project.target_dir`. 이 repo 기준 상대경로면 절대경로로 바꿔 쓴다.
  없으면 만든다. **생성되는 서비스 소스는 반드시 target_dir 안에만 쓴다.** 이 repo 안에는 소스를 두지 않는다.
- target_dir 안의 표준 배치:
  ```
  <target_dir>/
  ├── backend/            # 2·3단계
  ├── frontend/           # 4단계
  ├── db/migration/       # Flyway 등 마이그레이션 (2단계)
  ├── docs/api/<slice>.yaml   # OpenAPI 계약 (2단계 산출, 4단계 소비)
  ├── docs/test/<slice>-scenario.md   # 통합 테스트 시나리오 (5단계)
  └── docs/deliverables/  # 8단계 산출물
  ```
- 파이프라인 메타(brief, slices, 요구서, 레포트, 상태)는 항상 이 repo 의 **`workspace/<project>/`** 에 둔다 (`<project>` = `config/project.yaml → project.name`). 프로젝트가 바뀌면 config 만 바꾸면 되고 이전 프로젝트의 workspace 는 그대로 남는다. `tools/rr.py`·`status.py` 는 config 에서 프로젝트명을 읽어 경로를 정한다. 에이전트에게는 항상 **절대경로**로 전달한다.

## 3. 파일 형식

| 파일 | 형식 | 템플릿 |
|---|---|---|
| `workspace/<project>/state.yaml` | 파이프라인 상태 | `templates/state.yaml` |
| `workspace/<project>/knowledge/PROJECT_BRIEF.md` | 프로젝트 요약 지식 | `templates/PROJECT_BRIEF.md` |
| `workspace/<project>/slices/slices.yaml` | 업무 분류 | `templates/slices.yaml` |
| `workspace/<project>/refactor-requests/RR-NNNN.yaml` | 리팩토링 요구서 | `templates/refactor-request.yaml` |
| `workspace/<project>/open-items.yaml` | 확인 필요 항목(§11) | `templates/open-items.yaml` |
| `workspace/<project>/knowledge/DATASOURCES.yaml` | (migration) 데이터소스 지도(§22) | `templates/DATASOURCES.yaml` |
| `workspace/<project>/reports/*.md` 끝의 `pa-meta` 블록 | 레포트 게이트 메타(§9) | `templates/report-meta.md` |
| `<target_dir>/docs/test/<slice>-scenario.md` | 통합 테스트 시나리오 | `templates/test-scenario.md` |

템플릿의 키를 빼거나 이름을 바꾸지 않는다. 값이 없으면 빈 값으로 둔다.

## 4. 선행 조건 (게이트)

| 명령 | 선행 조건 |
|---|---|
| /stage0 | `workspace/<project>/00_inputs/` 에 파일이 1개 이상 |
| /stage1 | stage0 `done` |
| /stage2 `<slice>` | stage1 `done` **and** `slices.yaml → approved: true`; 골격(stage2_scaffold) 미완료면 먼저 골격 수행; `depends_on` slice 의 stage2 가 `done`; **(migration) 공통 계약 승인 + `stage2_common_port: done`** (§17) |
| /stage2 common-port | (migration) 골격 `done` **and** 공통 계약 `approved: true` |
| /stage2 `<slice>:<unit>` | 위 slice 조건 **and** 그 unit 의 `depends_on` unit 이 `done` (§20). slice 에 `units` 가 있으면 slice 는 unit 순서대로만 진행한다 |
| /stage3 | stage2 가 `done` 인 slice 가 1개 이상 |
| /stage4 `<slice>` | 해당 slice 의 stage2 `done` (OpenAPI 계약 존재); `depends_on` slice 의 stage4 `done` |
| /stage5 | 해당 slice 의 stage2·stage4 `done` |
| /stage6, /stage7 | stage5 가 `done` 인 slice 가 1개 이상 (전체 완료 권장) |
| /stage8 | stage5 `done`; 6·7은 권장 |
| /refactor | open 요구서 1개 이상 |

**착수 보류(hold)**: slices.yaml 에서 `hold: true`(사유는 `hold_reason`)인 slice 는 근거가 모자라 착수를 미룬 것이다.
slices 승인과 공통 사용 행렬·공통 계약 계산에는 포함되지만(그 slice 가 쓸 공통도 미리 확정한다), /stage2·/stage4·/run 의 착수 대상에서는 빠진다.
그 slice 에 `depends_on` 으로 (전이적으로) 걸린 slice 도 함께 빠진다. `gate.py plan` 은 이들을 "근거 대기 hold" 로 따로 보여 주고
멈춤 사유로 세지 않는다(나머지는 진행). hold slice 의 2·4단계 완료 기록은 gate `slice-scope` 가 차단한다. hold 해제는 근거를 확보한 뒤 사람이 slices.yaml 을 고쳐 승인한다.

**완료 조건 (2·3·4단계)**: `pipeline.gate` 설정에 따라 빌드·단위테스트가 통과해야 `done`. 실패하면 `blocked` + `blocked_reason` 기록.
게이트 통과 여부는 **말이 아니라 증거로 남긴다** — 레포트 `pa-meta` 의 `gates[]` 에 명령·종료 코드·테스트 개수를 적고
`python tools/gate.py check --stage <N> [--slice <id>]` 가 통과해야 단계를 `done` 으로 기록한다 (§9).
테스트 개수 0 은 통과가 아니다 — 필터가 아무것도 매칭하지 않아도 종료 코드는 0 이 나온다(실측 2회).
통과시키려고 테스트를 지우거나 `@Disabled`/`skip` 하지 않는다.
예외: 환경 조건부 실행(예: Docker 필요한 동시성 테스트 `@EnabledIfSystemProperty`)은 조건·사유가 어노테이션에 있고, 해당 환경(`-Pmysql` 등)에서 실제 실행·통과한 기록이 레포트에 있으면 허용한다.
이런 테스트가 어떤 RR 의 유일한 회귀 근거라면 **그 환경에서의 1회 실행이 게이트에 포함**된다 — 오케스트레이터가 웨이브 종료 시 `-Pmysql` 등으로 실행하고 state log 에 남긴다. 5단계 시나리오에도 같은 조건을 적는다.

## 5. slice 인자 해석

- `/stage2 order` → 해당 slice 하나.
- `/stage2 order,member` → 나열된 slice.
- `/stage2 all` 또는 인자 없음 → `slices.yaml` 의 모든 slice 중 아직 `done` 이 아닌 것.
- 존재하지 않는 id 면 slices.yaml 의 id 목록을 보여주고 중단.
- `/stage2 claim:review` → slice `claim` 의 unit `review` 하나 (§20). `claim` 처럼 unit 을 지정하지 않으면 그 slice 의 남은 unit 을
  `python tools/slice_units.py order --slice claim` 순서대로 전부 돈 뒤 slice 통합(흐름 테스트·전수 대조)까지 한다.

## 6. 병렬 실행

`pipeline.parallel: true` 일 때 2·4단계에서 여러 slice 를 처리하면:

1. `depends_on` 으로 위상 정렬하여 **웨이브(wave)** 를 만든다. 같은 웨이브의 slice 는 서로 의존이 없다.
2. 웨이브 안에서 `max_parallel` 개까지 developer 서브에이전트를 **동시에** 실행한다 (Agent 도구를 한 메시지에서 여러 개 호출).
3. 웨이브가 끝나면 각 slice 에 reviewer 를 돌린 뒤 다음 웨이브로 간다.
4. **충돌 방지 규칙** — 병렬 중인 developer 는:
   - 자기 slice 패키지/디렉토리(`backend/.../<slice>/`, `frontend/src/features/<slice>/`, `db/migration/V<n>__<slice>_*.sql`)와
     자기 계약 파일(`docs/api/<slice>.yaml`)만 쓴다.
   - 공용 파일(빌드 설정, common 패키지, 라우터 루트, 공용 타입)은 **수정하지 않는다.**
     필요한 공용 변경은 `workspace/<project>/reports/common-candidates.md` 에 "무엇이·왜 필요한지" 를 적고 slice 안에 임시 구현한다. 3단계가 이를 흡수한다.
     **단, 공통 계약이 있으면(migration, §17) 임시 구현을 금지한다** — 공통을 업무 안에 임시로 만들면 공통 클래스가 업무별로 쪼개지고
     private 복제가 생긴다(실측). 계약에 있는 공통은 그 TO-BE 를 호출하고, 없는 것은 `python tools/common_contract.py request` 로 공통 요청(CR)을
     남긴 뒤 그 기능만 `blocked` 로 보고한다. gate 의 `common-integrity` 가 공통 복제·공통 영역 수정을 차단한다.
     병렬 에이전트는 **스크래치패드를 공유**하므로 임시 스크립트·파일명에 slice 접두어를 붙인다(`<slice>_patch.py`) — 다른 developer 의 패치가 덮어써진 실측.
     에이전트가 API 서버 오류(5xx)로 중단되면 새 에이전트를 띄우지 말고 같은 에이전트를 **재개**(`SendMessage`)한다 — "작업 트리 상태(`git status`·파일 목록)를 먼저 확인하고 중단 지점부터" 를 지시. 컨텍스트가 보존돼 산출물 손실 없이 이어진다(실측 2회).
     오케스트레이터는 developer 프롬프트에 포트·라이브러리 동작·정제 결과 같은 **사실을 단정해 적지 않는다** — "실측할 파일 경로" 와 기대 결과만 준다(틀린 단정 3회 실측: 포트·jsoup·swagger-core).
     병렬 웨이브에서는 오케스트레이터가 slice 마다 C-번호 대역(예 A: C-10~19, B: C-20~29)을 프롬프트로 배정해 번호 충돌을 막는다.
     빌드 의존성 추가도 공용 변경이다 — slice 는 대안 구현(예: xlsx 대신 CSV) 또는 인터페이스만 만들고 후보로 남긴다.
   - **마이그레이션 버전에 slice 고유 번호를 넣는다**: `V<대역><slice번호2자리>_<yyMMddHHmmss>__<slice>_<설명>.sql`
     (대역 규약이 없으면 `V<slice번호2자리>_<yyMMddHHmmss>__…`). slice 번호는 오케스트레이터가 웨이브 프롬프트로 배정한다.
     **분 단위 타임스탬프만으로는 충돌을 막지 못한다** — 동시 3개 웨이브에서 두 slice 가 같은 분에 파일을 만들어
     `Found more than one migration with version …` 로 **무관한 모듈까지 컨텍스트 생성이 실패했다**(실측, 3개 slice 게이트가 동시에 멈춤).
     `db/migration` 은 모든 모듈이 공유하므로 한 slice 의 버전 충돌이 웨이브 전체를 막는다.
   - 웨이브 착수 전과 종료 후 오케스트레이터가 **버전 중복을 검사한다**:
     `ls <target_dir>/db/migration/*/ | grep -oE '^V[0-9_]+' | sort | uniq -d` 가 비어 있어야 한다.
   - 파일명을 고친 뒤에도 **빌드 산출물의 옛 복사본이 충돌을 남긴다**(`copy-resources` 는 삭제를 전파하지 않는다).
     이름을 바꿨는데 같은 오류가 계속되면 `target/*/test-classes/db/migration` 의 잔존 파일을 지운다(골격이 정리 스크립트를 제공하는 것이 낫다).
5. `state.yaml` 갱신은 오케스트레이터(명령 본문)가 웨이브 종료 시점에 한 번에 한다. 서브에이전트는 state.yaml 을 직접 쓰지 않고 결과를 보고한다.
6. **단계가 다른 작업 환경에서 끝났으면 `done_elsewhere`** 로 적고 `elsewhere.<키>` 선언을 함께 둔다.
   실측된 공백(BG-01): 공통 선행 변환을 다른 PC 에서 끝낸 뒤 이 환경에는 레포트·`pa-meta`·잠금 매니페스트가 없었다.
   상태 값에 그 개념이 없어 `skipped`(하지 않았다)나 `blocked`(막혔다)를 골라야 했는데 **둘 다 사실이 아니고**,
   어느 쪽도 "이 환경에서 무엇을 확인하지 못했나" 를 남기지 못했다.

   ```yaml
   stages:
     stage2_common_port: done_elsewhere
   elsewhere:
     stage2_common_port:
       where: 다른 작업 환경 (브랜치 dev3 · 커밋 fd0f5f76)
       evidence: target_dir docs/pipeline/BRANCH_NOTE.md 완료 내역 표
       not_verified_here: 레포트·pa-meta 부재 · 잠금 매니페스트 부재(spec 파일 101개는 target 에 있다)
       declared_by: '사람:<이름>'
       declared_at: 2026-10-06 03:30
   ```
   - **사람만 선언한다.** `declared_by` 가 `사람:` 으로 시작하지 않으면 게이트가 차단한다 —
     증거 없이 완료로 보는 것은 에이전트가 정할 수 없다(공통 계약 `status: external` 과 같은 규칙).
   - 네 칸이 모두 필요하다. 비면 선언으로 보지 않는다. 특히 `not_verified_here` 는 **통과의 대가를 적는 칸**이다.
   - 효과: gate `state-consistency` 가 통과시키고 확인하지 못한 것을 INFO 로 남긴다.
     `spec-lock` 은 "매니페스트가 이 환경에 없다" 를 FAIL 에서 **WARN** 으로 내린다(숨기지 않고 선언을 가리킨다).
     선언이 없으면 그대로 차단한다 — 상태 값만 바꿔 통과시킬 수 없다.
6. 병렬 developer 는 앱 기동이 필요할 때(계약 생성 등) **서로 다른 포트**를 쓴다 (오케스트레이터가 slice 마다 지정, 예: 18081/18082). 같은 `build/` 디렉토리를 공유하므로 전체 테스트(`gradlew test`)는 **웨이브 종료 후 오케스트레이터(또는 reviewer)가 1회만** 실행한다. developer 는 자기 slice 테스트(`--tests "<pkg>.<slice>.*"`)까지만 게이트로 삼는다.
   웨이브가 끝나면 **오케스트레이터가 전체 테스트를 1회 직접 실행**해 실패가 있으면 reviewer 를 부르기 전에 developer 재작업으로 돌린다 (reviewer 의 시간을 게이트 실패 확인에 쓰지 않는다).
   프론트도 같다: `node_modules`·`dist` 공유 → `build` 는 마지막 1회(실패 시 30초 후 재시도), vitest 는 파일 단위(`npm run test --run src/features/<slice>`)로 먼저, 전체는 마지막 1회.
   **규약 검사(ArchUnit·소스 스캔류)도 전체 테스트와 같이 다룬다** — 오케스트레이터가 웨이브 종료 후 1회 돌린다.
   소스 스캔은 커밋하지 않은 남의 작업 트리까지 보므로 병렬 중에는 남의 미완성 코드가 반드시 걸리고, developer 는 그것을 고칠 수 없다(실측).
   대신 오케스트레이터가 웨이브 프롬프트에 **규약 요약(금지 목록)** 을 실어 사전 예방한다 — 위반 복제가 그 웨이브 범위로 제한된다.
   **검토·검증 에이전트도 같은 작업 트리에서 빌드하면 동시에 띄우지 않는다.** reviewer 와 equivalence-verifier 는 코드를 고치지 않지만
   둘 다 같은 `target/`(·`build/`)에서 테스트를 돌린다. 한쪽의 `clean` 이 다른 쪽 실행 도중 결과 파일을 지워 결과 출처를 가릴 수 없게 된 실측이 있다.
   순서대로 부르거나, 한쪽은 별도 git worktree(짧은 경로, `git -c core.longpaths=true`)에서 돌리게 지시한다. 어느 쪽이든 프롬프트에 "같은 작업 트리에서 다른 Maven/Gradle 실행이 없는지" 를 적는다.
   **병렬 작업 트리에서는 로컬 Maven 저장소에 설치하지 않는다(`install` 금지).** 한 트리의 공통 산출물이 저장소에 올라가면 다른 트리가 `-pl <모듈>` 만으로 빌드할 때 그 jar 를 쓴다(실측). 빌드는 `-pl <모듈> -am` 또는 전 모듈로 한다.
7. **target repo 커밋**: 골격 완료 시 오케스트레이터가 `git init` + 첫 커밋, 이후 웨이브가 `done` 될 때마다 `stage2(<slice>): ...` 형식으로 커밋한다. reviewer 가 `git status/diff` 로 공용 파일 변경을 판별할 수 있어야 한다. 서브에이전트는 커밋하지 않는다.

`parallel: false` 면 priority → depends_on 순으로 순차 실행한다.

## 7. developer → reviewer

2·3·4단계는 developer 서브에이전트가 만든 뒤 reviewer 서브에이전트가 검토한다.
- reviewer 는 코드를 고치지 않고 지적 목록을 돌려준다. 지적 한 건의 고정 형식:

  | 필드 | 규칙 |
  |---|---|
  | `id` | `<축약어>-<번호>` (예: `BR-03`) |
  | `severity` | `blocker` \| `high` \| `medium` \| `low` |
  | `confidence` | `confirmed`(실행·대조로 증명) \| `high` \| `medium` \| `low`(정황) — **근거 없이 severity 만 높이지 않는다** |
  | `evidence` | `파일:라인` 또는 실행한 명령·출력. 없으면 지적으로 만들지 않는다 |
  | `impact` | 사용자·데이터·운영에 실제로 무엇이 잘못되는가 |
  | `fix` | 구체적 수정안 |
  | `test_hint` | 이 지적을 닫으려면 **5단계가 무엇을 실측해야 하는가**. `medium`·`low` 로 넘기는 지적에는 필수 |

  `confidence: low` 인데 `severity: blocker` 면 오케스트레이터는 재작업 대신 확인 필요 항목(§11)으로 돌린다.
  `test_hint` 는 5단계 시나리오·7단계 인벤토리의 입력이다 — 여기서 끊기면 "확인 필요" 가 증발한다(실측: notice-admin §8 미인계).
- 오케스트레이터는 `blocker`·`high` 지적을 developer 에게 다시 넘겨 같은 단계 안에서 고친다 (최대 2회).
- 2회 후에도 남으면 `blocked` 로 기록하고 사람에게 보고한다.
- `medium`·`low` 지적 처리: 코드 수정이 필요한 것은 RR(`source_stage` = 현재 단계)로 남기고, 공용 파일·컨벤션 문서 변경은 `common-candidates.md` 로 넘긴다. 같은 단계에서 바로 고치지 않는다 (병렬 slice 와의 충돌·회귀 방지).
- 뒤따르는 slice 에 적용할 교훈(예: `@Pattern` 앵커)은 오케스트레이터가 다음 developer 호출 프롬프트에 명시한다.
- 우선순위: **brief §12 결정 > 골격 `CONVENTIONS.md` > 프로필 > 오케스트레이터 프롬프트의 구현 세부**. 프롬프트가 규약과 충돌하면 developer 는 규약을 따르고 보고에 "지시와 다른 결정" 으로 명시한다.

## 8. 리팩토링 요구서 (RR)

- 5·6·7단계와 reviewer 가 다음 단계로 넘길 결함은 **반드시** RR 파일로 남긴다.
- ID 채번: `python tools/rr.py new --title … --slice … --layer … --source N --target N --severity … --evidence "파일:라인" [--evidence …] --description "…" --fix "…"` (기존 최대 번호 +1, 본문까지 한 번에 — 생성 후 YAML 을 정규식·문자열 치환으로 고치지 말 것: 백틱·콜론이 YAML 을 깨뜨림. 고쳐야 하면 yaml 로드→수정→dump). 목록: `python tools/rr.py list [--status open]`.
- `evidence` 는 필수. 근거 없는 요구서는 만들지 않는다.
- 한 요구서에는 한 가지 결함만 담는다. `target_stage`·`target_layer`·`slice` 를 반드시 채운다.
- 상태 전이: `open → in_progress → done | rejected`. `rejected` 는 사람만 지정한다.

## 9. 레포트

- 위치: `workspace/<project>/reports/`, 파일명 `yymmddhhmm_stage<N>_<slice|all>_<설명>.md` (KST).
  unit 레포트는 `yymmddhhmm_stage<N>_<slice>_unit-<unit>_<설명>.md` 이고 pa-meta 에 `unit`·`asis_covered` 를 적는다 (§20).
- HTML 변환: `python tools/build_report.py <md파일>`.
- 타임스탬프는 항상 `python tools/kst_now.py` (파일명용 `yyMMddHHmm`; `--full` 은 본문용 `YYYY-MM-DD HH:MM`). bash `TZ=... date` 는 Windows Git Bash 에서 틀린다. HANDOFF 진행 기록은 `python tools/handoff.py note "<내용>"` 이 실측 시각을 붙여 넣는다.
- 레포트에는 항상 포함: 대상·입력 근거·수행 내용·게이트 결과(빌드/테스트 명령과 출력 요약)·미완료/근거 부족 항목·다음 단계 안내.
- 실행하지 못한 것은 "실행하지 못함 + 이유" 로 쓴다. 통과한 것처럼 쓰지 않는다.
- **레포트 끝에 `pa-meta` 블록을 붙인다** (형식·필드: `templates/report-meta.md`).
  골격: `python tools/gate.py template --stage <N> --slice <id> --agent <이름>`.
  본문의 서술과 별개로 이 블록이 기계 대조 대상이다 — `gates[]`(명령·종료 코드·테스트 개수),
  `repo`(git HEAD·브랜치·dirty·변경 파일), `open_items[]`, `rr_ids[]`, `not_executed[]`.
- **레포트를 쓴 직후 `python tools/gate.py check --stage <N> [--slice <id>]` 를 실행하고 결과를 본문에 남긴다.**
  FAIL 이면 그 단계를 `done` 으로 기록하지 않는다. 검사 항목:
  실패한 게이트를 통과로 적기 · 테스트 0건 통과 · git 실측과 다른 기재 ·
  high 이상 확인 필요 항목의 무단 종료 · state.yaml 과의 모순 · 레포트의 자격증명/개인정보 노출 ·
  (2·3·4단계) 바뀐 소스의 상품화 품질(`tools/quality.py` 규칙: Javadoc·로거·traceId·Mapper 주석·콘솔 출력·민감정보 로깅·이모지) ·
  테스트 수·실패 수 ↔ 실제 결과 파일(`gates[].results` 의 JUnit XML) 불일치 · 단계 시작 전 결과 파일 재사용 · 레포트의 이모지 ·
  (migration) 외부 데이터소스 테이블의 CREATE·데이터소스 지도의 비밀정보(§22) ·
  (migration) **AS-IS 원본이 실제로 있는가**(`asis-source` — 없으면 `state.yaml` 의 `asis_source` 선언이 필요하다, §24 배경) ·
  (2·4단계) **slice 가 소비하는 공통을 적었고 그것이 실제로 있는가**(`consumes-integrity` — 적지 않은 공통을 쓰면 WARN, §17).
  (도구가 잡아낸 것은 사람이 다시 읽어 확인하지 않아도 되고, 도구가 못 보는 것만 사람이 본다.)
- 레포트·산출물에 비밀번호·토큰·키·주민번호·연락처 **원문을 적지 않는다.** 값은 `***` 로 가리고 경로·변수명만 남긴다.
  별도 스캔: `python tools/gate.py secrets workspace/<project>/reports`.

## 10. 사람 확인 지점

| 시점 | 내용 |
|---|---|
| stage0 종료 | PROJECT_BRIEF.md 의 "근거 부족·모순" 표를 사용자에게 보여주고 확인 요청 (차단 아님) |
| stage1 종료 | `slices.yaml` 을 보여주고 **`approved: true` 로 바꿔 달라고 요청**. 승인 전 stage2 진행 불가 |
| stage2 골격 종료 | 골격 구조·컨벤션 요약을 보여주고 확인 요청 (차단 아님) |
| reviewer 2회 후 잔여 지적 | 사람에게 보고, `blocked` |
| RR `rejected` | 사람만 가능 |
| 확인 필요 항목 `accepted` (§11) | 사람만 가능 — 승인자·만료일 기록 |

## 11. 확인 필요 항목 (open item)

RR 은 "고쳐야 할 결함"이고, open item 은 **"아직 확인·결정되지 않은 것"** 이다.
레포트 산문에만 적힌 "확인 필요" 는 다음 단계로 넘어가면서 사라진다(실측: notice-admin §8, F-306).
그래서 다음 다섯 가지는 반드시 `workspace/<project>/open-items.yaml` 에 채번해 남긴다.

| kind | 예 |
|---|---|
| `evidence_gap` | brief §11 근거 부족이 그 단계에서 결정을 막은 것 |
| `decision` | 사람 결정이 필요한 것 (brief §12 후보) |
| `unverified` | 구현은 했으나 그 단계의 테스트로는 도달·증명 불가 (MockMvc 로는 못 보는 서블릿 경로 등) |
| `risk` | 지금은 괜찮지만 조건이 바뀌면 깨지는 것 |
| `deferred` | 뒤 단계로 의도적으로 미룬 것 |

- 채번: `python tools/gate.py oi new --stage <N> --slice <id> --kind <kind> --severity <sev> --summary "…" --evidence "파일:라인" --target <닫을 단계> [--axis <축>] [--owner <에이전트>]`
- **항목이 여러 건이면** 서브에이전트 보고를 레포트 `pa-meta.open_items` 에 그대로 옮긴 뒤
  `python tools/gate.py oi import --report <레포트> --write` 로 **일괄 채번**한다 (레포트의 id 까지 도구가 채운다).
  0단계에서 51건이 나온 실측 — 한 건씩 부르는 것은 규모에서 불가능하다.
- 레포트 `pa-meta.open_items[]` 에 같은 id 로 싣는다. 도구가 파일과 대조한다.
- **RR 전환을 요구하는 것은 `unverified`·`risk` 이고 단계가 2 이상일 때뿐이다.** RR 은 "이미 있는 코드의 결함" 을 고치라는 요구이므로
  0·1단계에는 만들 대상이 없다. `blocker`·`high` 라도 `decision`·`evidence_gap`·`deferred` 는
  **`target_stage` 로 예약**되어 있으면 열린 채 넘어갈 수 있다(도구가 WARN 으로 추적한다).
  2단계 이후의 `unverified`·`risk` 가 `blocker`·`high` 면 RR 전환(`oi set <id> converted --rr RR-xxxx`) 또는
  사람 승인(`accepted`) 없이 그 단계를 `done` 으로 끝낼 수 없다.
  게이트는 통과했지만 미확인이 남았으면 레포트 `result` 는 `done_with_gaps` 다.
- `target_stage` 가 자기 단계인 항목은 착수 시 `oi list --target <N>` 으로 확인하고, 처리하면 `resolved`,
  못 했으면 레포트에 다시 싣는다 (도구가 누락을 WARN 으로 알린다).
- `accepted` 는 사람만 지정하고 `approved_by`·`expiry`(YYYY-MM-DD)가 필요하다. 만료된 승인은 FAIL 이다.
- `decision` 항목을 `resolved` 로 닫을 때는 그 결정을 판단 기록으로 남기고 연결한다: `oi set <id> resolved --jd JD-xxxx` (§21). 연결 없이는 도구가 거부한다.

## 12. 에이전트 결과 계약 (Agent Result)

서브에이전트의 보고가 산문뿐이면 오케스트레이터가 집계·인계에서 항목을 흘린다(실측: RR-0023 admin 몫 증발).
**모든 서브에이전트는 보고의 마지막을 아래 블록으로 끝낸다.** 오케스트레이터는 이 블록만으로
state 갱신·다음 호출 프롬프트·레포트 `pa-meta` 를 만들 수 있어야 한다.

````markdown
```json pa-agent-result
{
  "schema": 1,
  "agent": "backend-developer",
  "stage": 2,
  "slice": "notice",
  "attempt": 1,
  "result": "done",
  "gates": [
    {"kind": "build", "command": "…", "exit_code": 0, "executed_at": "2026-09-23 00:20"},
    {"kind": "test", "command": "…", "exit_code": 0, "executed_at": "2026-09-23 00:35",
     "test_count": 226, "failures": 0, "skipped": 0,
     "results": ["server/domain-notice/target/surefire-reports/TEST-*.xml"]}
  ],
  // gates[].kind 는 build·test·lint·typecheck·smoke·scan·other 만 쓴다(그 밖 - static·browser·quality·spec-lock 등 - 은 gate 가 거부).
  //   test·smoke·scan 은 test_count 와 results(JUnit XML 경로)가 있어야 한다. 개수·XML 이 없는 확인(정적 대조·셸 검사·잠금 확인)은 other 로 적고 note 에 결과를 쓴다.
  //   결과 JSON 파일을 따로 저장하면 이 블록과 똑같이 쓴다(open_items·judgments 를 빼지 않는다).
  "changed_files": ["server/domain-notice/src/main/java/…"],
  "open_items": [{"kind": "unverified", "severity": "high", "axis": "real-server",
                  "summary": "…", "evidence": "…", "target_stage": 5}],
  "rr_ids": [],
  "common_candidates": ["C-21"],
  "not_executed": ["…"],
  "risk_surface": [{"what": "이 변경이 깨뜨릴 수 있는 것", "axis": "concurrency",
                    "covered_by": "테스트명 또는 '미검증'"}],
  "cost": {"duration_min": 40, "tool_calls": 96},
  "deviations": ["오케스트레이터 지시와 다르게 결정한 것 + 근거"],
  "judgments": [{"kind": "substitution",                      // decision·substitution·semantic·scope·interpretation·design·deviation 중 하나 (§21)
                 "summary": "무엇을 정했나", "rationale": "왜",
                 "source": "레포트#절", "check": "검증 단계에서 무엇을 어떻게 확인하나",
                 "affects": ["CC-0025"], "verify_slices": ["notice"], "verify_stage": 5}],
  "next_action": "reviewer 검토 요청"
}
```
````

- `result`: `done` | `done_with_gaps` | `blocked` | `failed`.
- `open_items` 는 id 없이 보고해도 된다 — 채번은 오케스트레이터가 `gate.py oi new` 로 한다.
- `changed_files` 는 실제로 고친 파일 전부. 오케스트레이터가 `git status`·`diff` 로 대조하고,
  **자기 소유 밖의 파일(공용 설정·common·다른 slice)** 이 있으면 되돌린 뒤 공통 후보로 돌린다(§6-4).
- 실행하지 못한 검증은 `not_executed` 에 이유와 함께 적는다. 비워 두고 통과로 보고하지 않는다.
- `risk_surface` 는 **이 변경이 무엇을 깨뜨릴 수 있는가**를 스스로 선언하는 칸이다(§14). `covered_by` 가 "미검증" 이면 확인 필요 항목으로 올린다.
  RR 을 반영하는 작업에서는 비워 둘 수 없다 — 리팩토링이 더 큰 결함을 낳은 실측(RR-0041: 락 축소 목적의 `REQUIRES_NEW` 가 커넥션 2중 점유를 만듦) 때문이다.
- **수치를 주장하면 그 수치를 낸 명령을 함께 적는다.** `risk_surface`·`deviations`·`not_executed`·산문 어디에서든
  "N건" · "최댓값 X" · "전부/하나도" 같은 주장을 하면 그것을 낸 명령(또는 파일:라인)을 같은 문장에 둔다.
  실측: 서브에이전트가 `risk_surface` 에 "새 마이그레이션 번호가 **전역 최댓값 1.0.840** 보다 낮다" 고 적고
  그에 맞춰 플래그 추가를 권했는데, **1.0.840 은 존재하지 않았고** 실제 최댓값은 1.0.800 이어서 결론이 거꾸로였다.
  근거 명령을 함께 적게 하면 쓰는 쪽이 한 번 더 돌려 보게 되고, 읽는 쪽이 재현할 수 있다.
  **집계 방식도 적는다** — 예: 테스트 개수는 surefire XML 의 `<testcase>` 개수(`tests` 속성은 `@Nested` 에서 틀린다).
  **변경 전 수치를 주장하면 어떻게 그 상태를 만들었는지도 적는다**(예: `git stash push -u -- <파일>` 후 같은 명령·같은 DB).
- `judgments` 는 **자동 변환이 아니라 판단으로 정한 것**이다(§21). `deviations` 에 적은 것은 전부 판단이므로 `judgments` 에도 싣는다.
  id 없이 보고하면 오케스트레이터가 레포트 `pa-meta.judgments` 로 옮겨 `python tools/judgment.py import --report <레포트> --write` 로 채번한다.
- reviewer 는 같은 블록에 `findings[]`(§7 형식)를 함께 싣는다.
- **옮기기는 기계로 한다.** 오케스트레이터는 서브에이전트 프롬프트에 "같은 JSON 을 `workspace/<project>/reports/agent-results/<이름>.json` 에도 저장" 을 넣고,
  받은 뒤 `python tools/ingest_result.py --json <그 파일> --stage <N> --slice <id> [--unit <u>] --name <설명> [--body <본문.md>]` 로
  open_items 채번(OI) → 레포트(`pa-meta` 포함, repo 는 git 실측) → judgments 채번(JD)을 한 번에 한다.
  실측: 손으로 옮기면 judgments·open_items 를 빠뜨리거나 문구를 줄인다. 결과 블록이 정본이고 레포트는 그 사본이다.
  **다음 단계가 쓸 산출(동작 계약 행 FC·시그니처 목록·대조표)은 JSON 필드(`fc_map`·`signatures` 등)로 저장하게 하고**, 산문 보고에만 있으면
  보고 본문을 파일로 떠서 `--body` 로 넘긴다(실측: 계약 단계가 산문으로만 낸 FC 25행이 어디에도 남지 않아 spec 작성자가 다시 매겼다).
- **테스트 실행 명령은 클래스를 나열한다.** Maven `-Dtest='패키지.*'` 패턴은 0건을 실행하고 종료 코드 0 이다 - 지시·게이트 명령에 쓰지 않는다(실측).
- **사람이 만든 자료는 참고이고 정본은 원본 소스다(migration).** 분석 문서·산출물·공유 브랜치에 올라온 계약·spec·소스는 사람(또는 원본 없는 환경의 에이전트)이 만든 것이라
  오류가 섞인다. 동작·규칙·SQL 의 근거는 AS-IS 원본의 파일:라인으로 대고, 참고 자료는 원본과 대조한 뒤에만 쓴다. 어긋나면 원본을 따르고 `deviations` 에 적는다.
  오케스트레이터는 모든 서브에이전트 프롬프트에 이 원칙을 적는다.
- **AS-IS 운영 동작을 그대로 옮긴다 - 개선·정상화하지 않는다(migration).** 의미 없거나 문제가 많아 보이는 코드·쿼리·권한 공백·결함도 에이전트 판단으로 고치지 않고 AS-IS 대로 이관한다.
  개선은 테스트 단계(5·6·7)에서 사람이 요청하면 RR 로 고친다. 예외는 셋뿐이다: 대상 DB 방언 등가 보정(같은 결과를 내기 위한 변환), 사람이 승인한 TO-BE 규약, 사람 결정.
  발견한 결함·위험은 고치는 대신 확인 필요 항목(OI)으로 올리고 해당 검증 단계에 예약한다(실측: 에이전트가 권한 결함을 '정상화' 해 AS-IS 와 다른 동작을 잠갔다가 되돌렸다).
  **이전 차수(이미 만든 TO-BE)에서 사람이 고친 동작도 사람 결정이다** - AS-IS 와 다르다는 이유로 AS-IS 로 되돌리지 않는다. 공통·SQL 을 이전 차수 코드에서
  가져왔으면 그 코드의 주석·커밋·결정 기록에서 "AS-IS 와 다르게 바꾼 이유" 를 먼저 찾고, 있으면 그대로 둔다(실측: 2차가 사람 판단으로 LEFT JOIN 으로 바꾼 코드 목록 SQL 을
  3차 공통 작업이 AS-IS 내부 조인으로 되돌렸다가 사용자 지적으로 취소했다).
- **AS-IS 운영에서 실제로 실행되지 않던 코드는 살리지 않고 주석으로 옮긴다(migration).** 상수·설정으로 꺼진 분기, 실행하면 항상 오류인 SQL·코드와
  그 오류 때문에 매번 뒤가 돌지 않던 줄, 호출 경로가 없는 메서드·statement 는 TO-BE 에서 실행 코드로 옮기면 AS-IS 운영에 없던 동작(특히 외부 시스템 쓰기)을 새로 만든다.
  원문은 TO-BE 파일 안에 전체 주석 블록으로 남기고 머리에 AS-IS 파일:라인·실행되지 않던 이유·판단 JD 를 적는다. "실행됐는가" 는 설정·상수·예외 흐름까지 따라가 판정한다.

## 13. 모델 배정

`.claude/agents/*.md` 는 `model: inherit` 이다. 오케스트레이터가 Agent 호출 시 아래 기준으로 상위/중급을 고른다.
전부 최상위는 낭비이고, 전부 중급은 공용·경계에서 사고가 난다.

| 상위 모델을 쓰는 곳 | 이유 |
|---|---|
| 골격(scaffold)·3단계 공통화·계약 설계 | 실수가 모든 slice 로 전파된다 |
| 분기·상태 조합이 많은 slice (권한·결재·파일·외부연동) | 경우의 수를 놓치면 5·6단계에서 크게 돌아온다 |
| 5·6·7단계 검증과 reviewer | 결함의 원인 계층을 정확히 지목해야 재작업이 라우팅된다 |
| AS-IS 추적(sql-migrator·ingest) | 근거 해석이 틀리면 뒤 단계가 전부 틀린다 |

계약이 정해진 CRUD slice, 확정 스키마의 기계적 작성, 산출물 재가공(8단계)은 중급으로 충분하다.
**상향 규칙**: 같은 문제로 developer 가 2회 이상 막히면(reviewer 재작업 2회 소진 직전) 그 에이전트만 상위 모델로 재실행하고,
사유를 레포트에 남긴다.

## 14. 검증 축 (axis)

단계를 늘려도 **같은 축**에서만 검증하면 새 결함은 나오지 않는다.
sample2 최종 채점에서 파이프라인이 스스로 만든 결함 7건은 전부 앞 단계가 **보지 못하는 축**에서만 잡혔다.

| 축 | 무엇을 볼 수 있나 | 실측으로 여기서만 잡힌 것 |
|---|---|---|
| `unit` | 로직 분기 | — |
| `module` | 스프링 컨텍스트·H2 | — |
| `real-db` | 실제 DB 방언·타입·인덱스 | H2 URL override, `Timestamp` 캐스트 |
| `real-server` | 서블릿·필터·파서·프록시 (`RANDOM_PORT`) | multipart NUL 500, 413 순서, XFF 위조 허용 |
| `browser` | 실제 렌더·타이머·번들 | Tiptap 로드 즉시 크래시 (jsdom 122 tests 통과) |
| `concurrency` | 경합·풀·교착 | `REQUIRES_NEW` 커넥션 2중 점유 |
| `security-static` | 소스 전역 sink 추적 | 정제기 우회, 로그 인젝션 |

운영 규칙:

1. 1단계가 slice 마다 `traits` 를 정하고, 그것이 **요구 축**을 결정한다(`stage1-slicing §4-1`). 모든 slice 는 기본으로 `unit` 을 요구하고, 그 위의 축은 traits 가 요구할 때만 본다.
   축에는 포함 관계가 있다 — `real-server`·`real-db` 는 `module`·`unit` 을, `module` 은 `unit` 을 이미 지난다. 같은 실행을 여러 축으로 중복해 적지 않는다.
2. 게이트를 실행할 때마다 `pa-meta.gates[].axis` 에 어느 축을 닫았는지 적는다.
3. 이번 단계가 닫을 수 없는 축은 **확인 필요 항목으로 예약**한다: `gate.py oi new … --axis <축> --target <닫을 단계>`.
4. `gate.py` 의 `coverage-axis` 훅이 대조한다 — 요구 축 중 닫히지도 예약되지도 않은 것이 있으면
   2·4단계에서는 WARN, 그 축을 닫아야 할 단계(5·6·7)에서는 FAIL.
5. **판별력 없는 테스트는 축을 닫지 않는다.** 그 축에서 결함을 재현하지 못하는 테스트(수정 전에도 통과하는 테스트)는
   축 충족으로 세지 말고, 재현→수정→통과를 레포트에 남긴다(실측: jsdom 프로브로 재현 불가를 먼저 증명한 뒤 Chromium 스모크 채택).
   증명 방법은 두 가지다 — **수정 전 재현**(테스트를 먼저 넣고 실패를 확인) 또는 **mutation**(구현에 결함을 주입해 테스트가 잡는지 확인).
6. **판별력 증거는 `pa-meta.discrimination[]` 에 기록한다**(형식: `templates/report-meta.md`).
   `target`·`method`·**`scope`**·`failures`·`evidence`(실패 실행의 surefire XML 사본)·`restored`.
   - **실행 범위를 반드시 적는다.** 한 클래스만 돌린 결과를 모듈 전체로 일반화한 오보가 실측됐다
     (mutation 을 한 클래스에서 돌려 "기존 테스트 전부 통과" 로 보고했으나, 같은 모듈의 통합 테스트는 그 변이를 이미 잡고 있었다).
     **기준은 모듈 전체 1회 실행**이다.
   - 실패 실행을 `gates[]` 에 싣지 않는다 — `gate-proof` 가 "실패한 게이트를 통과로 기재" 로 읽는다. 그래서 별도 칸이다.
   - 최종 실행이 surefire XML 을 덮어쓰므로 **실패 실행의 XML 사본**을 `reports/discrimination/<slice>_<회차>/` 에 남긴다.
     사본이 없으면 판별력 증거가 산문뿐이어서 검증할 수 없다(실측).
   - **수정 전에는 판별 수단(메서드·오류 코드)이 없어 단언을 쓸 수조차 없는 경우**가 있다(`method: absent_pre_fix`).
     이때는 `failures: 0` 이 정상이지만 **면제가 아니라 의무가 바뀐다** — 해악이 실재함을 증명하는 통과 단언(`harm_evidence`)과
     수정 후 결함을 주입해 새 테스트가 잡는지 확인한 기록(`mutation`)을 **둘 다** 남긴다.
     (실측: "컴파일이 안 돼 재현 불가" 를 `failures: 1` 로 적어 규격의 정수 검사를 통과시킨 사례가 reviewer 에게 적발됐다.)
7. **축은 양방향으로 닫는다 — 막는 것과 통과시키는 것은 다른 테스트다.**
   실측(sample3 `common-file`): 위조 `X-Forwarded-For` 가 무시되는 것은 `real-server` 로 증명했으나
   **신뢰 프록시에서 온 XFF 가 실제로 반영되는가** 는 repo 전체에 단언이 없었다. 그쪽이 요구사항(이력 IP)의 본체였다.
   운영 설정이 실제 프록시를 빠뜨리면 **모든 이력 IP 가 LB 주소 하나**가 되는데 어떤 게이트도 잡지 못한다.
   보안·인가·필터 설정은 "거부 방향" 만 닫고 끝내지 않는다.
8. **테스트가 운영 설정값을 교체하면 그 축은 운영 값을 검증하지 않는다.**
   `application-test.yml` 이 값을 전용 값으로 바꿔 놓고 "그 설정을 실측했다" 고 적으면 거짓이다.
   확인 필요 항목을 닫을 때는 그 항목의 **`evidence` 가 지목한 대상**을 테스트가 실제로 덮었는지 대조한다.
   남의 slice 소유 항목을 자기 실측으로 닫는 것은 더 위험하다 — 범위를 좁게 읽는다.
9. **`method: harm_evidence`** — 이번 회차가 고친 것이 운영 코드가 아니라 **규약·호출 순서**여서 변이시킬 구현이 없는 경우.
   규약을 어긴 형태를 실행해 해악을 직접 재현하되(positive control), 변이 자리가 테스트 픽스처이므로
   "테스트가 자기 픽스처를 검증한다" 는 순환이다. 그래서 `mutation` 으로 적지 말고 `harm_evidence` 로 적고
   **`enforced_by` 에 그 규약을 실제로 강제하는 수단**(규약 검사·게이트)을 밝힌다. `gate.py` 가 그 필드를 요구한다.
   (실측: `REQUIRES_NEW` 호출 순서를 고친 회차가 픽스처 변이를 `mutation` 으로 적어 정수 검사를 통과했다.)
   `absent_pre_fix` 가 요구하는 **`harm_evidence` 필드**와 헷갈리지 않는다 — 이쪽은 `method` 값이다.
   `absent_pre_fix` = 판별 수단이 없었다(통과 단언 + 사후 `mutation` 둘 다) · `harm_evidence` = 변이시킬 구현이 없다(해악 재현 + `enforced_by`).
10. **새로 만든 기계 검사는 프로브까지가 한 단위다. 통과는 규칙이 맞다는 증거가 아니다.**
    위반 코드를 심어 **검출되는 것을 확인**하고, **정당한 코드가 걸리지 않는 것도 확인**한 뒤, 프로브를 제거하고 재통과시킨다.
    실패 실행의 XML 을 `reports/discrimination/<검사>_probe/` 에 남긴다.
    실측(sample3, 규약 검사 6규칙 소급 프로브): **두 규칙이 틀려 있었다.**
    하나는 정당한 코드를 막았고(메서드 이름만 보고 무관한 `assignable` 선언을 위반으로 잡았다),
    하나는 가장 흔한 형태를 놓쳤다(클래스 레벨 `@Transactional` 을 보지 않았다).
    **오검출은 검출 실패보다 위험하다** — slice 는 규약 문서를 고칠 수 없어 스스로 예외를 낼 수 없고, 오케스트레이터 개입 없이 막힌다.
    검사를 만든 회차에 프로브하지 않으면 그 항목은 "미검증" 으로 계속 이월된다(실측: 두 항목이 3회차를 이월하다 프로브 1회로 닫혔다).

11. **통과 실행의 증거도 사본으로 남긴다** — `reports/gate-evidence/<slice>_r<회차>_<축>/`.
    판별력 사본은 **실패** 실행만 남기는 규칙이라, 축을 닫은 **통과** 실행의 surefire XML 은 그 뒤 최종 실행이 덮는다.
    실측(웨이브2): `-Pmysql` 통과 실행을 오케스트레이터의 H2 전체 테스트가 덮어써서
    reviewer 가 `mtime`·`spring.profiles.active` 로 **축 실행을 독립 검증할 수 없었다.**
    "이 축을 닫았다" 고 적을 때 사본이 없으면 그 주장은 회차가 넘어가는 순간 검증 불가가 된다.
12. **같은 변이를 두 축에서 돌리면 축의 값이 수치로 증명된다.**
    실측: 감사 호출을 `readOnly` 안으로 옮긴 같은 변이가 **H2 1건 / MySQL 4건** 실패했다(`Connection is read-only` 3건 차이).
    `real-db`·`real-server` 를 요구하는 slice 는 핵심 변이를 **두 축에서** 기록한다 — 축을 늘린 판단의 근거가 된다.
13. **21개 slice 가 같은 패턴을 쓰는 규약은 문장이 아니라 검사여야 한다.**
    실측: `§5-2`·`§5-5`(DB 충돌은 409)가 이미 규약으로 있었는데도 한 slice 가 400 으로 내보냈고 **어떤 검사도 잡지 못했다**
    (같은 slice 안의 다른 세 코드는 409 였다). "규약에 적혀 있다" 는 다음 slice 가 그 줄을 읽었다는 뜻이 아니다.
    규약을 검사로 바꿀 때는 §14-10 대로 **프로브까지** 한다.
14. **공용 화이트리스트에 slice 가 항목을 추가해야 하는 구조는 함정이다.**
    등록을 잊었을 때 **무엇이 조용히 실패하는가**를 먼저 묻는다. 실측: CORS `exposedHeaders` 열거 때문에
    slice 가 만든 응답 헤더가 cross-origin 에서 가려져, "조용한 잘림" 을 고친 수정이 브라우저에서 무력화됐다.
    slice 는 공용 파일을 고칠 수 없으므로 이 부류는 **오케스트레이터가 구조를 바꿔야** 닫힌다.

## 15. 이모지 금지 (전역 · 예외 없음)

- 대상: 생성 소스 전부(코드 주석·Javadoc·로그 문구·예외 메시지·Mapper XML 쿼리 주석·yml/properties 주석·DDL `COMMENT`·
  Flyway 스크립트 주석·테스트 코드와 `@DisplayName`·화면 문구·i18n 리소스), target repo 커밋 메시지, 레포트·산출물·매핑표,
  에이전트 보고(`pa-agent-result` 포함), 이 저장소의 지침·템플릿·도구 출력.
- 대체 표기: 완료/통과 → `완료`, 실패 → `실패`, 주의 → `주의`, 의미 차이 → `[의미차이:태그명]`, 진행 상태 → `[v] [>] [x] [ ]`.
  화살표(→)·가운뎃점(·)·수학 기호(≥ ≠)·괘선은 이모지가 아니므로 쓸 수 있다. 판정 기준은 `tools/_emoji.py` 하나다.
- 테스트에서 이모지 입력 처리를 검증해야 하면 문자를 직접 쓰지 않고 escape(`"\uD83D\uDE00"`, `"\U0001F600"`)로 만든다.
- 외부 도구(external/) 템플릿이나 AS-IS 소스에서 가져온 문구에 이모지가 있으면 텍스트로 바꿔 옮긴다.
  AS-IS 원문 인용이 꼭 필요하면 코드포인트(`U+2705`)로 적는다.
- 강제 장치(어느 한 곳이 뚫려도 다음 단계가 잡는다):
  1. `tools/hooks/guard.py`(PreToolUse) — Write·Edit·MultiEdit·NotebookEdit·Bash 의 새 내용에 이모지가 있으면 **쓰기 자체를 차단**.
     SubagentStop 에서 에이전트 보고의 이모지도 차단.
  2. `tools/quality.py` `NO-EMOJI`(critical) — target 의 코드·설정·SQL·문서 전부. 테스트·리소스도 예외 없고 `quality:ignore` 로도 끌 수 없다.
  3. `gate.py check` `no-emoji` — 모든 단계 레포트. FAIL 이면 단계 완료 불가.
  4. `tools/selfcheck.py`·CI — 이 저장소의 모든 파일, 그리고 모든 에이전트·스킬·명령 파일에 이 조항이 들어 있는지.

## 16. 훅에 의한 강제 (`.claude/settings.json`)

지침은 읽히지 않거나 잊힐 수 있으므로 핵심 원칙은 훅이 도구 호출 시점에 막는다. 훅이 막으면 우회하지 말고 원인을 고친다.

| 훅 | 막는 것 | 대응 |
|---|---|---|
| PreToolUse (쓰기·Bash) | 이모지가 든 쓰기 | 텍스트로 바꿔 다시 쓴다 |
| PreToolUse (쓰기) | **공개본 금지어가 든 쓰기** — 이 저장소의 git 에 올라가는 파일에 고객 식별 문자열 (`config/publish-public/rules.yaml` 의 `deny`). gitignore 대상·저장소 밖·규칙 파일 자신은 보지 않는다 | 일반화해서 다시 쓴다(프로젝트명 `demo`·패키지 `com.example`·시스템명은 유형). 실제 이름은 `workspace/` 에만 둔다 |
| PreToolUse (state.yaml) | 게이트를 통과하지 못한 단계·slice 를 `done` 으로 바꾸는 편집 | 레포트·`pa-meta` 를 고쳐 `gate.py check` 통과 후 기록, 아니면 `blocked` |
| PreToolUse (Bash) | Bash 로 state.yaml 에 쓰기(sed·리다이렉션·python 쓰기) | Edit/Write 도구로 고친다 |
| SubagentStop | 파이프라인 에이전트가 `pa-agent-result` 블록 없이·깨진 JSON·필수 키 누락·이모지 포함으로 끝내기 | 블록을 보완해 다시 끝낸다 |

훅은 `python`(또는 `python3`)이 PATH 에 있어야 동작한다. 훅 자체 오류는 작업을 막지 않으며, 게이트·selfcheck·CI 가 2차 방어선이다.

## 17. 공통 계약 — 공통을 먼저 확정하고 업무는 소비만 한다 (migration)

실측된 문제: 업무 단위로 변환하면 업무 에이전트가 자기가 쓰는 공통 메서드만 보고 판단해 ① 공통 클래스를 업무별로 부분 이관하고
② 한 메서드만 쓰면 private 으로 복제했다. 그 뒤 "공통만 변환" 을 따로 돌리면 업무 코드와 어긋나 "업무 변환 → 공통 변환 → 다시 짝지어 검사"
라는 중복 공정이 생겼다. Mapper statement 도 같았다. 원인은 공통 코드의 **소유자와 확정 시점**이 없었던 것이다.

흐름(1단계 승인 직후 → 2단계 업무 slice 전):

| 순서 | 무엇 | 누가 | 산출물 |
|---|---|---|---|
| 1 | 공통 사용 행렬 — 어느 업무가 공통의 **어느 메서드·statement** 를 어떤 경로(direct·inherited·via)로 쓰는가 | `python tools/common_usage.py` (정적 분석, 결정적) | `knowledge/COMMON_USAGE.yaml`·`.md` |
| 2 | 공통 계약 초안 — 항목마다 owner·decision 제안 | `python tools/common_contract.py init` | `contracts/common-contract.yaml` |
| 3 | 검토·결정 — `review` 항목(slice 소유 미사용), 업무로 내릴 항목, 업무 간 교차, 여러 모듈 항목의 module(복사 또는 전 모듈 공통), 이관 안 함 목록(동적 호출 의심만 훑어봄) | 사람 (slice-planner 가 근거 정리) | 계약의 owner·decision·module·decided_by |
| 4 | 승인 | **사람만** — `! python tools/common_contract.py approve --by <이름>` (에이전트 실행은 훅이 차단) | `approved: true` |
| 5 | 공통 선행 변환 | `/stage2 common-port` → (sql-migrator `convert common-port`) → `common-porter` | TO-BE 공통 모듈·공유 Mapper, 계약 `tobe`·`status: ported` |
| 6 | 업무 slice 변환 | backend-developer — 계약을 **소비만** 한다 | 업무 코드 |

규칙:
- 한 업무만 쓰는 공통 메서드도 기본은 **공통 유지**다(owner: common). 업무로 내리는 것(`slice:<id>`)은 사람이 결정하고 `decided_by` 를 남긴다.
  다른 업무도 쓰는 항목은 내릴 수 없다(validate 가 거부).
- **미사용 일괄 규칙**: 어느 slice(hold 포함 전체)에서도 도달 경로가 없는 공통 메서드·공통 namespace statement 는 개별 `review` 로 올리지 않고
  `owner: none`·`status: not_migrated`(이관 안 함)로 일괄 판정해 계약 옆 목록 파일(`contracts/common-contract-not-migrated.yaml`)에만 남긴다.
  계약에는 `summary`(review 건수·일괄 규칙 전 기준 건수·이관 안 함 건수·범위 제외 건수)만 남는다. 실측: 초안 4천여 항목 중 사람 검토 2,500여 건의
  대부분이 미사용이어서 한 건씩 판단할 수 없었다. 폐기(discard)가 아니라 "이번에 옮기지 않음" 이므로, 동적 호출·리플렉션으로 쓰이는 항목은
  목록 파일에서 사람이 owner 를 `common`·`slice:<id>`·`discard` 로 바꾸고 `decided_by` 를 적으면 다음 `init` 이 계약 항목으로 올린다(승인 해제).
  **개별 review 로 남기는 것**(진짜 판단이 필요한 것): slice 소유 namespace 의 미사용 statement, slice 소유 클래스 중 다른 클래스가 부르는 클래스(서비스·DAO)의
  미사용 public 메서드. 프레임워크 진입점(@Bean·핸들러 등)은 종전대로 공통 유지이고, 접근자는 그 클래스를 어느 slice 가 쓸 때만 진입점으로 본다.
- **범위 제외(brownfield)**: slices.yaml 의 `unassigned.asis`(이번 차수 범위 외 — 분류 `out_of_scope`)와 `pre_pipeline`(이전 차수에 이미 이관 — 분류 `pre_pipeline`)에
  적힌 프로그램·패키지·namespace 는 "소유 slice 없음" 이어도 공통이 아니다. 행렬은 이들을 `excluded_classes`·statement `scope` 로 집계만 하고,
  그 코드에서 출발하는 호출은 slice 사용으로 세지 않으며 slice 가 그 코드를 부르면 그 앞에서 멈춘다(TO-BE 에 이미 있거나 이번에 옮기지 않는다).
  그래서 그 코드만 쓰는 공통 메서드는 공통 선행 변환 대상이 되지 않는다. 계약에는 항목으로 올라가지 않고 `summary.excluded` 건수만 남는다.
- **모듈 차원**: TO-BE 가 모듈(앱)로 나뉘고 config `project.modules` 가 있으면 행렬이 공통 항목마다 사용 slice 의 모듈 집합(`modules`)을 계산하고,
  계약의 owner=common 항목에 `module` 을 붙인다.

  | 사용 모듈 | 기본 제안 | 의미 |
  |---|---|---|
  | 한 모듈의 slice 들만 | `module: <모듈>` | 그 모듈의 공통. 같은 모듈의 다른 slice 는 호출만 한다 |
  | 여러 모듈 | `module: [모듈…]`·`copy: true` | 모듈별 복사본(모듈 간 공유 금지 규약). `tobe` 는 `{모듈: TO-BE}` 로 적는다 |
  | 전 모듈 기반(인증·권한 등) | 사람이 `module: <project.common_module>` 로 바꾸고 copy 를 지운다 | 전 모듈 공통 |

  validate 는 "여러 모듈이 쓰는데 한 모듈 공통", "목록인데 copy 없음", "쓰는 모듈의 복사본 누락" 을 거부한다. 사람이 바꾼 module 은 `init` 을 다시 돌려도 보존된다.
  modules 가 없으면 module·copy 필드를 만들지 않는다(종전 동작).
- 공통 모듈(`tobe.common_module`·`tobe.common_package`·`tobe.shared_mapper_dir`)은 `common-porter` 만 쓴다(3단계 공통화는 예외).
- 업무 slice 는 공통을 복제하지 않는다. 계약에 없는 공통이 필요하면 공통 요청(CR)을 남기고 그 기능만 `blocked` 로 보고한다.
  오케스트레이터는 웨이브 사이에 열린 CR 을 `common-porter cr` 로 묶어 처리한다. 새 공통 항목은 계약 개정(사람 승인) 후 반영한다.
- 강제: gate `common-integrity` — 업무 slice 의 공통 영역 수정·공통 메서드 복제(본문 유사도, 변수명 바꾼 private 복제 포함)·공유 Mapper statement
  복제는 FAIL, common-port 는 owner=common 전부가 TO-BE 에 있어야 통과. 계약 미승인 상태의 완료도 FAIL.
  migration 인데 계약이 없으면 경고(`pipeline.gate.common_contract: strict` 면 FAIL).
  모듈 차원: 계약에서 `copy: true` 로 승인된 항목의 **그 slice 모듈 복사본**은 복제로 보지 않는다. 같은 모듈 안에 복사본이 이미 있으면
  (`project.module_paths` 의 그 모듈 경로를 찾아본다. 매핑이 없으면 이번 변경 파일끼리만 대조) 업무 slice 간 복제로 FAIL 이다.
  한 모듈 공통·전 모듈 공통 항목의 복제는 종전대로 FAIL. 계약 `tobe.module_common`({모듈: 경로})을 적으면 그 경로도 common-porter 만 쓴다.
  gate `slice-scope` 는 slice 의 `module` 과 `project.module_paths` 가 있으면 2·4단계 변경 파일이 자기 모듈 경로·승인된 공통 경로·`existing_code` 밖일 때 WARN 이다.
- AS-IS 가 바뀌면(추가 입력) 행렬과 계약을 다시 만든다 — `init` 은 사람 결정·id 를 보존하고, 항목이 바뀌면 승인을 해제한다.
- **공통 선행 변환이 이 파이프라인 밖에서 이미 끝났으면 계약을 새로 만들지 않는다** (이전 차수·다른 작업 환경).
  새로 만들면 그쪽이 쓴 번호 체계(`CC-xxxx`)가 갈리고 완료된 결과와 어긋난다. 대신 **외부 확정**으로 선언한다:
  `python tools/common_contract.py external --source <정본 문서·절> --numbering <이미 쓴 번호 대역> --evidence <완료 근거> --by '사람:<이름>'`
  → `status: external` · `items: []`. 승인은 평소대로 사람이 `approve` 로 한다.
  `gate.py plan` 은 외부 확정 본문에 대해서는 common-port 단계를 넣지 않고, `common-integrity` 는
  **항목 단위 검사(공통 복제·영역 침범·이행)를 하지 않았다는 것을 INFO 로 남긴다** — 통과로 넘기지 않는다.
  그 방어가 빠지므로 **reviewer 가 slice 코드와 정본 문서의 공통 대응표를 직접 대조**한다.
- **외부가 확정한 공통에 없는 수단이 필요하면 `additions` 로 더한다** (외부 확정 계약에만 있는 자리).
  실측된 공백: `status: external` 은 항목을 두지 않으므로, 업무 slice 를 만들다 **그쪽에 없던 공통 수단**이 필요해지면
  (사번으로 이름·부서를 얻는 수단이 공통에 없었다) 등록할 자리가 없었다. 그러면 "공통을 업무 안에 임시 구현하지 않는다" 를
  지키려 해도 **그 공통이 어디에 있어야 하는지 계약이 말해 주지 못한다.**

  ```
  python tools/common_contract.py addition --cr CR-xxxx --owner common --decision 개선       --target <업무가 호출할 TO-BE 시그니처> --evidence <필요하다는 근거> --judgment JD-xxxx
  ```
  - 외부 확정 본문(`items`)은 그대로 비워 둔다. 더한 것은 **`CC-A001` 대역**으로 따로 센다 — 그쪽 번호와 섞지 않는다.
  - **공통 요청(CR)을 거친 것만** 더할 수 있고, 판단(`JD`) 또는 사람 결정(`decided_by: 사람:…`)이 있어야 한다.
    외부가 확정한 경계를 넓히는 것은 자동 변환이 아니라 판단이다(21절).
  - 더한 것은 **우리가 만든 것이므로 검사한다**: `gate.py plan` 이 미이행 건이 있으면 common-port 단계를 넣고,
    `common-integrity` 가 미이행을 WARN·`ported` 인데 target 에 없으면 FAIL 로 잡는다.
    "외부 확정이라 검사 못 한다" 와 섞지 않는다 — 섞으면 우리가 더한 공통의 미이행이 가려진다.
  - 이행은 `common-porter` 만 한다. 끝나면 `python tools/common_contract.py addition-done --id CC-A001`.
  - **먼저 따져 볼 것**: 정본 문서가 그 **클래스**를 이미 공통으로 매핑했고 빠진 것이 **메서드 하나**뿐이면
    경계를 넓히는 것이 아니라 계약 항목의 누락 보완이므로 `additions` 가 아니다(실측 사례: 암복호 유틸의 짝 메서드).
    `additions` 는 정본에 **없는** 수단을 더할 때 쓴다.
- **slice 는 "이미 있는 공통에서 무엇을 소비하는가" 를 `slices.yaml` 의 `consumes` 에 적는다** (brownfield).
  greenfield 는 공통 사용 행렬이 "누가 무엇을 쓰나" 를 계산하지만, brownfield 는 **공통이 먼저 있고 slice 가 나중에 와서
  방향이 반대**다 — 계산할 수 없다. 적히지 않으면 ① developer 가 공통에 있는 기능을 업무 안에 다시 만들고(실측된 사고)
  ② 공통을 고칠 때 영향 slice 를 역추적할 수 없고 ③ 8단계 공통 명세에 "어느 업무가 어느 공통을 쓰나" 가 빈다.
  **주석으로 적지 않는다 — 도구가 읽지 못한다**(실측: 소비 10종이 전부 YAML 주석에만 있었다).

  ```yaml
  consumes:
    - item: com.example.user.common.util.AESUtil   # FQCN · FQCN#method · Mapper statement
      kind: class                                  # class·method·mapper·statement·service
      source: CONVENTIONS.md#5-4                   # 계약 id 또는 정본 문서#절
      note: AES 암호화 (decrypt 는 CR-0005)          # (선택) 아직 호출하지 않는 것은 그렇게 적는다
  ```
  gate `consumes-integrity`(2·4단계):
  - 적었는데 target 에 **없으면 FAIL** — "공통에 있다고 적기만 하면 통과" 를 막는다. 없으면 공통 요청(CR)이다.
  - **적지 않은 공통을 쓰면 WARN** (변경 파일의 import 를 본다. 공통 접두어는 `project.tobe_common_packages`,
    없으면 `base_package` 에서 `<base>.<common_module>`·`<base>.<module>.common` 으로 유도한다).
    `asis.common_packages` 와 **다른 키**다 — 그쪽은 AS-IS 쪽 설정이고 공통 사용 행렬이 쓴다.
  - 계약이 **외부 확정인데 `consumes` 가 비어 있으면 WARN** — 그때는 이것이 유일한 연결 수단이다.
  - `consumes` 가 없고 계약이 외부 확정도 아니면 INFO (행렬로 계산한다. 뒤로 호환).
  - `existing_code` 와 다르다: `existing_code` 는 이 slice 가 **고칠** 기존 코드, `consumes` 는 **호출만** 할 공통이다.
    공통은 slice 가 고칠 수 없다(`common-integrity` 가 FAIL).

## 18. 기대 동작 테스트 — 코드 작성자와 다른 에이전트가 먼저 쓰고 잠근다

실측된 한계: 특성화 테스트를 코드를 만든 developer 가 직접 썼다. 자기가 이해한 대로 코드를 만들고 같은 이해로 테스트를 쓰면
이해가 틀려도 테스트가 통과한다(자기 확인 편향). 5단계 통합 테스트는 사후라 되돌리는 비용이 크다.

slice(및 common-port) 흐름 — `verification.locked_spec` 이 `required`(migration 권장) 또는 `optional` 일 때:

| 순서 | 무엇 | 누가 |
|---|---|---|
| 1 | **계약 선행**: OpenAPI 계약 + 컨트롤러·서비스·DTO 시그니처 + 본문 없는 스텁 (common-port 는 계약 항목의 `tobe_signature` 스텁) | backend-developer `contract <slice>` (common-porter `signatures`) |
| 2 | **기대 동작 테스트 작성**: AS-IS 동작 계약·요구사항·인터페이스만 보고. 스텁 대상 실행 시 실패해야 한다(판별력) | behavior-spec-writer |
| 3 | **잠금**: `python tools/spec_lock.py lock --slice <id>` | 오케스트레이터 |
| 4 | **구현**: 잠긴 spec + 자기 단위테스트 통과까지 | backend-developer `implement <slice>` (common-porter `port`) |
| 5 | 검토 | backend-reviewer |
| 6 | **동등성 검증**: spec 독립 재실행 + 별도 작업 트리에서 결함 주입 표본(판별력) → 불일치는 RR | equivalence-verifier |

규칙:
- spec 위치: backend `…/src/test/java/**/spec/<slice 패키지명>/`, frontend `**/__spec__/<slice>/` (config `verification.spec_globs` 로 변경).
- 잠긴 spec 은 누구도 도구로 고칠 수 없다(훅: 편집·Bash 수정·매니페스트 직접 편집 차단). 테스트가 틀렸다고 판단되면 근거를 RR·deviations 로 남기고,
  잠금 해제는 **사람만**: `! python tools/spec_lock.py unlock --slice <id> --by <이름> --reason "…"` → behavior-spec-writer 수정 → 다시 lock.
- **위임(선택)**: 사용자가 프로젝트 설정 `approvals.delegate_to_agent: true`(`delegated_by: <이름>`)로 위임하면 사람 전용 명령 셋
  (공통 계약 승인·spec 잠금 해제·기준 이미지 승인)을 오케스트레이터가 실행한다. 이때도 규칙은 같다:
  (1) 해제·승인 사유는 AS-IS 원본 근거(파일:라인)로 적는다, (2) `--by <위임자>(위임)` 으로 기록한다,
  (3) 실행할 때마다 사용자에게 한 줄로 보고하고 최종 보고서에 목록으로 남긴다, (4) 서브에이전트는 실행하지 않는다(오케스트레이터만).
  배경(실측): 사용자가 모바일 원격제어로 진행하면 `!` 셸 명령을 칠 수 없어 진행이 멈췄다. 기본값은 위임 없음(사람만).
- 레포트 `pa-meta.gates[]` 에 `suite: "spec"` 인 test 게이트(결과 파일 포함)를 적는다. gate `spec-lock` 이 해시 대조·전체 실행(잠긴 테스트 수 이상)·실패 0 을 검사한다.
- 비용: slice 당 에이전트 호출 +2(spec-writer·verifier). 표본 결함 주입은 기본 3개로 제한한다. 5단계에서 같은 동작을 다시 사후 검증하는 비용과 재작업이 줄어드는 것으로 상쇄한다.

## 19. 브라우저 화면 검증 — 실행·판정은 기계, AI 는 고른 이미지만

단위테스트마다 스크린샷을 AI 가 판정하면 비용이 크고(이미지 1장 약 1~1.6천 토큰, 큰 이미지는 약 1.15 메가픽셀로 축소돼 장당 약 1,600 토큰 상한)
같은 화면도 회차마다 판단이 흔들린다(비결정적). 그래서 역할을 나눈다:

| 무엇 | 누가 | 토큰 |
|---|---|---|
| 화면 테스트 작성 (DOM 단언·콘솔 오류 0·네트워크 오류 0·`toHaveScreenshot`) | frontend-developer (spec 은 behavior-spec-writer) | 작성 시 1회 |
| 실행 — 로컬에서 BE·FE 기동(Playwright `webServer`) + 헤드리스 브라우저 | Playwright | 0 |
| 모양 비교 — 기준 이미지와 픽셀 비교 | Playwright | 0 |
| 볼 이미지 고르기 + 토큰 추정 | `python tools/visual.py pending` | 0 |
| 새·변경 기준 이미지 최초 승인, 실패 diff 판정 | ui-verifier (config `approver: human` 이면 사람) | 고른 이미지만 |

- 통과한 테스트의 스크린샷은 보지 않는다. 기준 이미지는 화면·상태마다 한 번 승인하면 해시로 고정되고, 바뀌면 다시 검토 대상이 된다.
- 기준 이미지 갱신(`--update-snapshots`)은 새 화면을 처음 만들 때와 **근거 있는 의도한 변경**일 때만 한다. 실패를 없애려고 갱신하지 않는다.
- 예산: `verification.visual.review_budget_images`(기본 60장). 넘으면 우선순위(실패 diff → 변경 → 신규)로 나눠 본다.
- gate `visual`(config `verification.visual.enabled: true`): 4단계 slice·5단계에서 미승인·변경 기준 이미지나 실패 diff 가 있으면 FAIL.
- 결정적인 스크린샷이 전제다 — 고정 뷰포트·시간대·로케일·폰트, 애니메이션 끔, 동적 영역(날짜·시각·난수) 마스킹(프론트 프로필 "Playwright 화면 검증").

## 20. 큰 slice 의 unit 분할 — 필요할 때만, 업무 프로세스 기준으로

실측된 한계: slice 크기는 고르지 않다. '이벤트' 는 API 1~2개지만 '보험금 청구' 는 접수·심사·지급·부지급·이의·조회가 얽힌 작은 프로젝트급이다.
에이전트 한 번이 정확히 다룰 수 있는 양을 넘으면 ① 뒤로 갈수록 AS-IS 원문을 다시 읽지 않아 분기·statement 가 빠지고 ② 비슷한 분기를
하나로 합쳐 업무 규칙이 사라지며 ③ reviewer·spec 도 대표 경로만 본다. 전부 빌드·단위테스트는 통과하므로 게이트에 드러나지 않는다.

구분: **slice 는 계약·소유·검증의 단위로 남고, unit 은 에이전트 1회 실행의 단위다.** OpenAPI 계약·도메인 모델·상태 전이는 slice 하나로 유지한다.
(서로 다른 엔티티를 소유하고 상태 전이를 공유하지 않는 부분은 unit 이 아니라 하위 slice 로 나눈다 — `stage1-slicing §2-4`.)

| 순서 | 무엇 | 누가 | 도구·산출물 |
|---|---|---|---|
| 1 | 크기 측정 — AS-IS 입력 토큰 추정·API·화면·statement·메서드·상태 전이 수. 기준(`config slicing.size`)을 넘는 slice 만 분할 후보, 아주 작은 slice 는 묶기 후보 | `python tools/slice_units.py measure` | 1단계 레포트 |
| 2 | 업무 프로세스 정의 — slice 의 `process.states`·`transitions`(`이전상태 -> 다음상태`) | slice-planner | slices.yaml |
| 3 | unit 정의 — `core`(첫 unit, 여러 unit 이 쓰는 엔티티·상태·서비스·SQL), `step`(상태 전이 소유), `query`(상태를 바꾸지 않는 조회), `flows`(unit 을 가로지르는 흐름) | slice-planner | slices.yaml `units`·`flows` |
| 4 | slice 내부 사용 행렬 — 각 클래스(컨트롤러·서비스 구현체는 메서드)·statement 를 어느 unit 이 쓰는가. 2개 이상이 쓰면 core, 하나만 쓰면 그 unit 으로 자동 배정 | `python tools/slice_units.py matrix --slice <id>` (migration) | `knowledge/units/<slice>.yaml` |
| 5 | 검증 — 구조·전이 소유·API/화면/요구사항 분배·core·흐름·크기 | `python tools/slice_units.py validate` | FAIL 이면 승인 요청 전에 고친다 |
| 6 | 승인 — slices.yaml 승인에 포함 | 사람 | `approved: true` |
| 7 | 실행 — unit 순서대로(`order`) 각 unit 이 developer → spec → reviewer → verifier 를 돈다. core 가 먼저다 | `/stage2 <slice>`·`/stage4 <slice>` | unit 레포트 |
| 8 | slice 통합 — 모든 unit 완료 + 흐름 테스트(`suite: flow`, flow id 인용) + AS-IS 전수 대조 | 오케스트레이터 + reviewer | slice 레포트 |

규칙:
- **나누는 기준은 업무 프로세스(상태 전이)다.** 계층(Mapper·Service·API)으로 나누지 않는다 — 계층 분리는 이미 파이프라인이 하고, 계층으로 자르면 업무 규칙이 조각난다.
  상태 전이 하나는 step unit 하나가 소유하고, process 의 모든 전이가 어느 unit 에 있어야 한다. 조회는 query unit 으로 뺀다.
- **core 가 먼저, 공유 클래스는 통째로.** 여러 unit 이 함께 쓰는 유틸·상위 클래스·DAO 를 각 unit 이 자기 쓰는 메서드만 옮기면 §17 의 공통 클래스 분해가
  slice 안에서 똑같이 생긴다. 이런 클래스는 core 의 `asis.programs` 에 선언해야 한다(선언 없으면 FAIL). core 는 API·화면·상태 전이를 갖지 않고 기반만 만든다.
- **진입점 클래스와 업무 서비스 구현체는 메서드 단위로 배정한다.** 실측: 레거시의 컨트롤러·서비스 구현체는 수천 줄에 모든 단계의 메서드가 몰려 있어,
  클래스 통째로 배정하면 모든 unit 이 그 클래스를 함께 써 전부 core 로 올라갔다(core 가 unit 상한의 1~3배, step·query unit 배정 0).
  그런 core 는 에이전트 1회 실행이 원문을 다 읽지 못하므로 금지한다. 이 두 종류는 메서드 경계가 곧 업무 단계 경계이므로 분해 금지 대상이 아니다.
  | 구분 | 판정 (`slice_units.split_kind`) | 배정 |
  |---|---|---|
  | 진입점 클래스 | `@Controller`·`@RestController`·`@RequestMapping` 이 붙었거나 이름이 `*Controller`·`*Action` | 메서드 단위 |
  | 업무 서비스 구현체 | 이름이 `*ServiceImpl` 이거나 `@Service` | 메서드 단위 |
  | 그 밖 전부 — 공용 유틸·상위 클래스(slice 안 다른 클래스가 상속)·추상 클래스·인터페이스·DAO·Mapper·도우미 | - | 클래스 통째 (종전) |
  - 메서드는 그 메서드를 (전이적으로) 쓰는 unit 이 하나면 그 unit, 둘 이상이면 core. core 메서드가 부르는 메서드도 core 다(core 가 먼저 변환되므로).
    private 헬퍼도 같다. 선언부·필드·생성자(`File.java#<decl>`)는 그 클래스 메서드가 2개 이상 unit 에 걸치면 core — core 가 TO-BE 클래스 뼈대를 만들고
    다른 unit 은 그 클래스에 자기 메서드만 추가한다(core 의 필드·메서드는 바꾸지 않는다).
  - 메서드 단위 대상이라도 unit 의 `asis.programs` 에 적으면 그 unit 에 클래스 통째다(작은 진입점 클래스가 한 unit 전용일 때).
  - **진입 메서드 찾기**: unit 의 `apis`(요청 경로)를 컨트롤러 메서드의 요청 매핑(클래스 레벨 + 메서드 레벨 결합)과 대조해 자동으로 찾는다.
    대조 규칙: `POST ` 같은 메서드 접두어 제거, `.do` 확장자 유무 무시, `/api` 접두어 유무 무시, 경로 변수 이름 무시(`{no}` = `{claimNo}`), 끝 `/` 무시.
    같은 경로가 여럿이면 HTTP 메서드로 좁힌다. 대응하지 않는 API 는 WARN — 경로가 다르거나 매핑이 없는 메서드는 `asis.methods: ["OrderController#cancel"]`
    (오버로드는 `#cancel/2`) 로 적는다. 어느 unit 도 쓰지 않는 메서드는 FAIL(폐기면 `asis.discard` 에 `File.java#메서드`).
  - statement 는 호출하는 **메서드**를 따라간다: core 메서드가 호출하거나 2개 이상 unit 이 쓰면 core, 한 unit 만 쓰면 그 unit.
  - 행렬 형식(`knowledge/units/<slice>.yaml`, schema 2): `assignment.<unit>` 에 `programs`(클래스 통째 배정 파일명)·`methods`(`File.java#메서드`·`File.java#<decl>`)·
    `statements`. `methods` 가 없는 옛 행렬(schema 1)도 validate·게이트가 그대로 읽는다. unit 레포트의 `asis_covered` 에는 메서드도 적는다(`.java` 유무는 같게 본다).
  - 크기: unit 토큰 추정은 클래스 통째 파일 전체 + 배정 메서드 본문(+ 선언부는 배정 unit 에 한 번) + statement 로 센다.
    core 가 여전히 `unit_max` 를 넘으면 WARN 과 함께 core 에 올라간 큰 메서드 상위 5개를 보여 준다 — 그 호출을 정리하거나 전이를 다시 나눌 곳이다. 다른 unit 은 core 를 **소비만** 하고 고치지 않는다 — 필요하면 unit 을 멈추고
  오케스트레이터에게 core 보강을 요청한다(core 재실행 → 끝난 unit 의 테스트 재실행).
- **unit 은 순차 실행이 기본이다.** 같은 slice 의 unit 은 계약 파일·도메인 패키지를 공유하므로 병렬이면 충돌한다(`slicing.unit_parallel: false`).
  서로 다른 slice 의 unit 은 §6 웨이브 규칙대로 병렬 가능하다.
- **API 계약은 slice 에 하나다.** 각 unit 은 자기 API 를 `docs/api/<slice>.yaml` 에 추가하고, 앞 unit 이 쓴 경로는 바꾸지 않는다.
- **기대 동작 테스트(§18)는 unit 마다 쓰고 slice 에 잠근다** — `spec_lock.py lock --slice <slice>` 는 추가만 하므로 unit 이 끝날 때마다 잠근다.
  unit 게이트는 slice 의 잠긴 spec 전체를 다시 돌린다(앞 unit 이 깨지지 않았는지).
- **이음매는 흐름 테스트로 닫는다.** 나누면 새로 생기는 위험은 unit 사이 상태 인계다(심사가 남긴 상태를 지급이 다르게 해석).
  모든 step·query unit 은 flow 에 한 번 이상 들어가고, 2단계 slice 통합 레포트는 `suite: flow` 게이트와 flow id 를 인용한 테스트가 있어야 통과한다. 5단계도 flow 를 시나리오로 쓴다.
- **누락은 전수 대조로 막는다.** unit 레포트의 `asis_covered` 가 그 unit 배정을 빠짐없이 덮어야 하고, slice 통합 시 모든 unit 레포트의 합이 배정 전체를 덮어야 한다.
  어느 unit 도 쓰지 않는 AS-IS 는 배정하거나 `asis.discard`(근거는 레포트)에 적는다 — 조용히 빠지지 않는다.
- **상태 전이가 0인 조회 전용 slice 는 데이터 원천 축으로 나눈다.** step unit 은 상태 전이를 소유하는 단위이므로 전이가 없으면 처방이 성립하지 않는다.
  그때는 `query` unit 을 **소유 테이블·데이터소스** 축으로 나누고(한 unit = 한 원천 묶음 + 그것을 읽는 화면), 여러 unit 이 함께 쓰는
  조회·집계·권한 코드는 `core` 가 먼저 만든다. **원천을 특정할 수 없으면 나누지 않는다** — 그 상태로 나누면 경계가 임의가 되고
  나중에 전부 다시 나눠야 한다. `no_split_reason` 에 그 사실과 **다시 측정할 시점**을 적는다.
- **화면 수의 단위는 라우트(화면 경로) 하나다.** 한 화면 안의 패널·지표·탭·모달은 세지 않는다.
  실측: 같은 범위를 한 문서는 3행(라우트), 다른 문서는 14행(지표 패널)으로 적어 **분할 판정이 갈렸다**(14 > 10 이면 split, 3 이면 ok).
  문서가 패널 단위면 라우트로 묶어 세고 그 환산을 1단계 레포트에 적는다. 한 화면이 유난히 무거우면(패널마다 독립 조회)
  그 무게는 `apis` 에 나타난다 — `screens` 를 부풀려 표현하지 않는다.
- **필요할 때만 나눈다.** 기준 이하 slice 에 units 가 있으면 과분할 경고다(unit 마다 에이전트 호출 4~5회가 추가된다).
  기준 초과인데 나누지 않으면 **`slices.yaml` 의 `no_split_reason`**(20자 이상)에 근거를 적는다 — 레포트 산문이 아니다.
  산문은 도구가 읽지 못해 다음 회차가 "나눠야 하는데 왜 안 나눴나" 를 다시 조사한다.
  `slice_units.py validate` 는 근거가 없으면 WARN(전이가 0이면 조회 전용 처방을 함께 안내), 있으면 INFO 로 그 근거를 보여 준다.
  기준값은 초기 추정치다 — 에이전트가 원문을 다시 읽지 않고 요약하기 시작한 크기를 실측하면 `config slicing` 을 고치고 `docs/LESSONS.md` 에 근거를 적는다.
- 강제: gate `unit-scope`(선행 unit 미완료·unit AS-IS 누락·slice 통합 조건), 훅(unit·slice 의 done 전환 시 게이트 실행 — 새 state 로 판정),
  `gate.py plan`(구조 오류면 멈춤, 분할 후보 알림), `status.py`(unit 진행 표).

## 21. 판단 기록 — 판단으로 정한 것은 검증 단계에서 다시 확인한다

실측된 한계: 2·3·4단계 게이트는 "만든 것이 빌드·테스트를 통과하는가" 만 본다. 그런데 사람이나 에이전트가 **판단**으로 정한 것
(대체 매핑, `불필요:` 판정, 폐기·범위 제외, AS-IS 결함 값을 유지할지, 근거가 모호한 곳의 해석, 지시와 다른 결정)은
그 판단 위에서 쓴 테스트도 같은 판단을 전제하므로, 판단이 틀렸으면 테스트까지 함께 틀리고 게이트는 통과한다.
판단은 레포트 산문(`deviations`·"결정" 절)에만 남아 다음 단계로 넘어가면서 사라진다. 그래서 판단은 채번해 두고, 검증 단계가 다시 확인한다.

**무엇이 판단인가**

`kind` 는 **아래 7개 값만** 쓴다. 다른 이름을 쓰면 `judgment.py` 가 거부한다
(실측: 오케스트레이터와 서브에이전트가 각각 `alternative-mapping`·`semantic_diff`·`design_choice` 를 써서 채번이 막혔다 —
표에 뜻만 있고 **값이 없었던 것이 원인**이다).

| `kind` | 판단 (기록한다) | 자동 변환 (기록하지 않는다) |
|---|---|---|
| `decision` | 사람 결정 — decision open item 의 해소, 위임 판단, 승인 시 조건 | 카탈로그(`migration-sql`)의 등가 구문 치환 |
| `substitution` | 대체 매핑 — AS-IS 기능을 2차·공통·프레임워크의 다른 구현으로 대신함, `불필요:` 판정 | 공통 계약대로의 계승(패키지·시그니처 정리만) |
| `semantic` | 의미 차이 — 차이를 수용하거나 보정함(AS-IS 결함 값 유지·정상화, 절단·정렬·타입) | 프로필·`CONVENTIONS.md` 규칙을 그대로 적용한 것 |
| `scope` | 범위 — 폐기(discard)·보류(hold)·이관 안 함·범위 제외 | 근거 문서에 명시된 동작을 그대로 구현한 것 |
| `interpretation` | 해석 — 근거가 모호·부족한 곳에서 한쪽을 골라 구현함 | |
| `design` | 설계 선택 — 대안이 있는 배치·이름·설정 방식 | |
| `deviation` | 지시·계약·규약과 다르게 정한 것(`deviations`) | |

판단인지 애매하면 기록한다. 같은 근거로 같은 결정을 여러 항목에 적용했으면 한 건에 `affects` 로 묶는다.

**흐름**

1. **판단한 단계(0~4)가 기록한다.** 서브에이전트는 `pa-agent-result.judgments[]` 로 보고하고(§12), 오케스트레이터는 레포트 `pa-meta.judgments` 로 옮겨
   `python tools/judgment.py import --report <레포트> --write` 로 채번한다. 사람 결정은 오케스트레이터가 `judgment.py new … --by "사람:<이름>" --oi <OI>` 로
   채번하고 해당 decision open item 을 `oi set <id> resolved --jd <JD>` 로 닫는다.
   - 필수: 누가(`--by`), 무엇을(`summary`), 왜(`rationale`), 어디 적혔나(`source`), **어떻게 다시 확인하나**(`check` — 시나리오 수준으로 구체적으로).
   - `verify_slices`: 판단의 영향을 받는 slice. 공통(common-port)의 판단은 그것을 소비하는 업무 slice 를 적는다 — 소비하는 곳에서 확인해야 한다.
   - `verify_stage`: 기본 5. 단일 slice 의 통합 테스트로 확인할 수 없는 것(여러 slice 를 가로지르는 흐름·운영 설정·외부 연동)은 7.
2. **검증 단계(5·7)가 slice 마다 다시 확인한다.** 착수 시 `python tools/judgment.py list --verify-stage <N> --slice <id>` 로 받아
   판단마다 시나리오를 하나 이상 둔다(5단계 `ITS-<slice>-j<3자리>`). 판단을 믿고 쓴 2단계 spec 을 다시 돌리는 것은 확인이 아니다 —
   **AS-IS 원본과 요구사항을 기준으로** 새로 본다.
3. **기준**(판단 기록의 `criterion` 에 자동으로 적힌다):
   - migration(차세대): AS-IS 기능이 손실 없이 동작하고, 요구사항에 맞게 온전히 개발돼 있다. 증거 2개 — `--asis-evidence`(AS-IS 대조: 같은 입력에 같은 결과·같은 부수효과, 의도된 차이는 brief §12 근거)와 `--req-evidence`(요구사항 충족).
   - 신규 개발: 요구사항에 맞게 온전히 개발돼 있다. 증거 `--req-evidence`.
4. **기록**: `judgment.py verify <JD> --slice <id> --result verified --req-evidence … [--asis-evidence …]`.
   판단이 틀렸거나 기능이 빠졌으면 RR 을 만들고 `--result failed --rr RR-xxxx`. 판단을 고칠 결정이 필요하면 decision open item 도 함께 연다.
5. **면제**는 사람만 한다: `judgment.py set <JD> --waive --approved-by <이름> --note "<사유>"`. 검증 단계를 옮길 때는 `--verify-stage`.

강제: gate `judgments` — 레포트 `judgments[]` 의 id 가 `judgments.yaml` 에 없으면 FAIL, 2·3·4단계에서 `deviations` 가 있는데 `judgments` 가 비었으면 WARN,
**5·6·7단계에서 그 단계·그 slice 가 확인하기로 한 판단에 결과가 없으면 FAIL**, 8단계에서 미검증 판단이 남았으면 WARN.
`status.py` 가 미검증 판단 수를 보여 준다.

## 22. 여러 데이터소스 — 실행 데이터소스로 판정하고, 외부 테이블은 만들지 않는다 (migration)

실측된 한계: AS-IS 매퍼가 여러 데이터소스(서로 다른 DB 엔진)를 쓰고, 한 매퍼 파일·한 매퍼 폴더가 여러 팩토리에 적재돼 statement 가 섞였으며,
외부 데이터소스 쿼리가 이관 대상 테이블과 **같은 이름**의 테이블을 쓰고 있었다. "이관 대상 DB 에 있는 테이블이면 이관" 한 축만 쓰면
외부 쿼리를 대상 DB 방언으로 잘못 바꾸고(같은 이름 테이블 15건 실측), 외부 테이블을 우리 DB 에 CREATE 하는 데까지 이어진다.
또 데이터소스의 엔진이 개발 프로필과 운영 프로필에서 달랐다(개발 설정이 외부 DB 를 주 DB 로 돌려 놓음).

**데이터소스 지도** `workspace/<project>/knowledge/DATASOURCES.yaml` (견본 `templates/DATASOURCES.yaml`, 도구 `tools/datasources.py`):
데이터소스 id → 운영 엔진·용도·이관 여부(`main` | `external` | `out_of_scope`)·소속 테이블, main 의 이관 대상 테이블(목록 또는 근거 DDL `tables_from`),
수신 테이블(`inbound_tables`)·합친 테이블(`merged_tables`), 데이터소스를 확정 못한 외부 테이블(`unresolved_tables`).
접속 URL·호스트·계정·비밀번호는 넣지 않는다(`validate` 가 키 이름부터 거부한다). 0단계 sql-migrator `inventory` 가 만들고 사람이 role 을 확인한다.

**판정 — 두 축** (`python tools/datasources.py judge --datasource <id> --tables T1,T2`):

| 실행 데이터소스 (호출 세션·팩토리 기준) | 대상 테이블 | 처리 |
|---|---|---|
| main | 전부 이관 대상 | 대상 DB 방언으로 변환 (`convert`) |
| main | 이관 대상에 없는 테이블이 있다 | 이관 안 함 + 근거 부족 기록 (`not_migrated`). 외부 테이블과 이름이 같으면 실행 세션을 다시 확인 |
| external | 무엇이든(이관 대상과 같은 이름이어도) | **원래 방언 그대로** 그 데이터소스 연결로 실행 (`keep_dialect`). 바꿔도 되는 것은 파라미터 문법(`:x`→`#{x}`)과 비밀값 파라미터화뿐 |
| out_of_scope | - | 이번 차수에 구성하지 않는다 (`out_of_scope`) |

규칙:
- **실행 데이터소스는 매퍼 파일 위치가 아니라 호출 경로로 정한다.** 같은 매퍼 폴더가 여러 팩토리에 적재되면 statement 의 엔진은 Java 호출 세션이 정한다.
  한 statement 를 환경에 따라 다른 세션이 부르면 둘 다 적고 decision 으로 올린다.
- **"원래 방언" 은 운영 프로필의 엔진이다.** 개발 프로필 엔진이 다르면 `dev_engine` 에 따로 적고 판정에는 쓰지 않는다. SQL 본문의 방언과 운영 엔진이 어긋나면(AS-IS 운영에서도 실패했을 가능성) 그대로 옮기지 말고 decision 항목으로 올린다.
- **외부·범위 밖 데이터소스 테이블은 우리 쪽에서 절대 CREATE 하지 않는다** — Flyway·DDL·스키마 파일·테스트 시드·테스트 코드 문자열 어디서도 TABLE·VIEW·SYNONYM 을 만들지 않는다.
  외부 statement 를 로컬에서 돌리려고 외부 테이블을 우리 DB 에 만드는 것도 금지다. 이 테이블이 정말 우리 DB 소유라면(아래 수신·합침) 지도의 main 에 근거와 함께 올리는 것이 먼저다(사람 결정).
  예외는 하나뿐이다: 기존 코드(brownfield)에 이미 있는 **로컬 시험 대체물**(로컬 프로필에서만 실행되는 시험 데이터 경로의 파일)을 사람이 지도의
  `local_stubs`(table·파일 glob·근거·`decided_by: 사람:`)로 올린 경우에만 검사가 warn 으로 보여 준다. 에이전트는 이 예외를 만들거나 넓히지 않고, 새 대체물도 만들지 않는다.
- **수신 테이블(`inbound_tables`)은 우리 DB 소유다.** 외부 시스템이 우리 DB 로 적재하는 인터페이스 수신 영역(예: 인사·조직 일 배치)은 외부 DB 테이블과 다르다 — CREATE 해도 되고 CREATE 금지 검사도 막지 않는다.
  단 **우리 코드는 테스트 시드 외에 수신 테이블에 쓰지 않는다**(INSERT·UPDATE·DELETE·MERGE). gate 가 `src/main` 코드·Mapper 의 쓰기를 경고한다.
- **다른 스키마·계정·데이터소스 테이블을 주 DB 로 합친 것(`merged_tables`)은 사람 결정이다.** 근거(`evidence`)·결정자(`decided_by`)를 적고 판단 기록(§21)으로 남긴다.
- 1단계 공통 계약은 주 데이터소스가 아닌 statement 에 `datasource: <id>`·`dialect: <운영 엔진>` 을 적는다. `common_contract.py validate` 가 지도와 대조해
  외부 statement 의 dialect 가 원래 방언이 아니거나, 범위 밖 데이터소스 statement 를 이관 대상으로 둔 것을 거부한다. `init` 은 두 값을 보존한다.
- TO-BE 배치: 외부 데이터소스마다 전용 데이터소스 설정·팩토리·매퍼 경로(예: `mapper-<id>/**`)와 전용 매퍼 스캔을 둔다. 주 팩토리의 매퍼 경로(`mapper/**`)에 외부 방언 XML 을 두지 않는다(주 DB 팩토리에도 적재된다).
  접속 정보는 환경변수로만 두고, 설정이 비면 그 기능만 실패하고 앱 기동은 막지 않게 한다. 외부 쓰기는 주 트랜잭션에 묶이지 않는다 — AS-IS 의 실패 처리(로그 후 진행 등)를 그대로 둘지 decision 으로 남긴다.
- **검증 축**: 외부 데이터소스 statement 는 로컬 DB 로 실행 검증이 안 된다. slice 에 trait `external-db` 를 붙이고(축 `real-server`),
  2단계는 정적 대조(AS-IS 원문과 정규화 비교·XML 적재·statement 존재)까지, 실제 접속 실행은 5·7단계로 `oi new --axis real-server --target 5`(또는 7)로 예약한다.
- **기존 부채 기준선**(brownfield): 지도를 **처음 만든 회차**에 이미 target 안에 있던 외부 테이블 CREATE 는
  파이프라인이 만든 것이 아니고, 그 단계는 고칠 수도(남의 영역) 면제할 수도(`local_stubs` 는 사람 전용·시험 전용) 없다.
  그대로 두면 다음 단계의 첫 업무 slice 가 **자기 변경과 무관한 이유로** 막힌다. 그래서 지도의
  `pre_existing_violations[]`(`table`·`files` glob·`found_at`·`evidence`·**`decision_oi` 필수**)에 등록하고,
  검사는 **등록된 것만 warn(기존 부채)으로 내리고 새로 생긴 것은 critical 로 남긴다**("기준선보다 나빠지지 않았는가" 와 같은 방식).
  `decision_oi` 를 필수로 둔 이유는 부채가 영구 면제가 되지 않게 하는 것이다 — 그 항목을 닫을 때 이 등록도 지운다.
  더는 걸리지 않는 등록은 `check` 가 `stale_baseline` 으로 알린다. 에이전트가 등록할 수 있지만 **범위를 넓히지 않는다**(파일 단위로만).
- 강제: gate `datasource-ddl`(0~7단계) — 지도 규격·비밀정보 오류는 FAIL, target 의 SQL 전부와 이번 변경 코드·설정에서 외부·범위 밖·미확정 외부 테이블의
  CREATE TABLE·VIEW·SYNONYM(이관 대상 목록에 없는 것)은 FAIL, 수신 테이블 쓰기는 WARN. 지도가 없으면 migration 에서 WARN(검사 생략). 전체 점검은 `python tools/datasources.py check`.


## 23. 보고의 정직성 — 실측으로 걸린 형태들

같은 실수가 회차마다 형태만 바꿔 재발했다. 아래는 전부 **실측으로 적발된 것**이고, 규칙은 그 대응이다.

1. **요구서를 닫을 때 그 요구서가 적은 종료 조건과 대조하지 않았다.**
   `RR` 의 `suggested_fix` 에 종료 조건(통과해야 할 테스트 이름)이 적혀 있는데 다른 테스트만 돌리고 `done` 으로 닫았다.
   → `status: done` 으로 바꿀 때 **`suggested_fix` 의 조건을 한 줄씩 증거와 대조**한다.
   `resolution_note` 에는 "무엇을 돌렸는가" 가 아니라 **"종료 조건 각 항이 어떤 증거로 충족됐는가"** 를 적는다.
2. **`gate.py oi set --note` 는 이력이고 `--summary`·`--evidence` 가 정본이다.**
   note 만 붙이고 "정정 완료" 로 보고했더니 `summary` 에는 틀린 내용이 그대로 남아 있었고 reviewer 가 파일을 열어 적발했다.
   → 본문이 틀렸으면 `--summary`·`--evidence` 로 고친다. **`evidence` 는 줄 번호 대신 상수·메서드 이름으로 적는다** — 회차마다 줄이 밀린다.
3. **지적의 `severity` 는 믿고 `fix` 는 검증한다.**
   reviewer 가 낸 처방이 위험을 **전환**한 사례가 있다(권고안대로 고치면 공격 비용이 5건 → 1건으로 **내려갔다**).
   → `fix` 는 누가 냈든 반영 전에 `risk_surface` 를 다시 계산한다. 다르게 고쳤으면 근거를 `deviations` 에 적는다.
4. **주석이 다른 계층의 존재를 전제하면 grep 으로 확인한다.**
   마이그레이션 주석이 "임시 식별자로 올린 뒤 확정하는 흐름" 을 설계 근거로 적었는데 그 연산이 어디에도 없었다.
   주석은 검증받지 않으므로 거짓이 오래 살고, 그 주석을 근거로 완화한 제약(FK 부재)만 남는다.
5. **"근거" 라고 적을 때는 입력 문서의 문장을 인용한다.**
   문서가 "임시저장 **가능**" 이라고만 적은 것을 "기안 폼이 문서 행을 선생성한다" 로 읽고 설계 제약을 6개 slice 에 강제했다.
   → 문서가 말하지 않은 것은 **이 slice 의 설계 판단**으로 적고 `decision` 항목으로 사람 확인을 받는다.
6. **전수 점검은 세는 대상이 빠지면 전수가 아니다.**
   "계약에 401 을 5개 엔드포인트 전부 넣었다" 는 사실이었으나 같은 절이 **403 누락**을 잡지 못했다.
   → 계약의 오류 응답은 **코드가 낼 수 있는 상태 전수**와 대조한다(`ErrorCode` 의 `HttpStatus` 집합 ↔ OpenAPI `responses`).
7. **검사 명령은 규약 문서에 적힌 것을 그대로 쓴다.** 즉석에서 줄여 쓰면 그 순간 다른 검사가 된다
   (Flyway 중복 검사를 `^V[0-9]+_[0-9]+` 로 줄여 쓰다 같은 slice 의 두 파일을 중복으로 오탐했다 — 버전은 타임스탬프까지다).
8. **전체 실행만 하면 순서 의존이 보이지 않는다.**
   같은 JVM 의 다른 `@SpringBootTest` 가 로거 레벨을 올려 준 덕에 통과하던 단언이 있었다(단독 실행 시 실패).
   → 로거·MDC·시스템 프로퍼티를 다루는 테스트는 **그 클래스만 단독 실행**해 확인한다.
9. **`pa-meta` 에 칸이 없으면 산문은 사라진다.** 산문에 적은 "지시와 다른 결정" 6건 중 **5건이 인계 시점에 사라졌다** —
   `deviations` 키가 없었고 도구도 요구하지 않았다. 이제 `report-meta` 가 그 키를 요구한다(벗어난 것이 없으면 **빈 배열로 선언**).
   `next_action`·`risk_surface`·`discrimination` 도 같다 — **칸을 비우는 것과 없는 것은 다르다.**
10. **관용구를 규약에 넣을 때는 그것이 안전한 조건을 함께 적는다.** 조건 없는 예시는 복제된다.
    실측: 골격 seed 의 `INSERT … ON DUPLICATE KEY UPDATE` 는 유니크가 PK 뿐이라 안전했는데, 규약 표가 그 조건을 말하지 않아
    보조 유니크가 있는 개인정보 테이블에 복제됐고 **남의 행을 조용히 덮어썼다**(H2·MySQL 동일, 기능 테스트로는 영원히 초록).

## 24. 기존 코드가 많은 저장소에서 검사를 켜는 법 (brownfield)

실측된 한계: 파이프라인이 만들지 않은 코드에 검사를 켜면 **그 코드가 이미 규약을 위반하고 있다.**
그런데 그 단계는 그것을 고칠 권한도(다른 담당자의 영역) 면제할 수단도 없어 **게이트가 영구히 차단**된다.
실측 사례 셋 — 이모지 검사가 전수에서 critical 9737건(전부 2차 기존 파일), 외부 데이터소스 테이블 CREATE 6건,
테스트 전체 실행 실패 27건. **전수 검사의 결과를 그대로 차단으로 쓰면 안 된다.**

전략은 셋이고, **검사의 성질에 따라 고른다.** 하나로 통일하지 않는다 — 성질이 다르다.

| 전략 | 언제 쓰나 | 어떻게 | 통과의 대가를 어디에 적나 |
|---|---|---|---|
| **범위 한정** | 검사가 **파일 단위**이고 위반이 많을 때 (이모지·주석·명명) | 이번 변경 파일만 본다 (`quality.py --files <changed_files>`) | 결과에 `scope.unchecked` — **검사하지 않은 파일 수**를 함께 낸다 |
| **등록 기준선** | 검사가 **개체 단위**이고 기존 부채가 적을 때 (테이블·파일 몇 개) | 개체마다 등록하고 `warn` 으로 내린다 (`datasources.yaml` 의 `pre_existing_violations`) | 각 항목의 `decision_oi` — **없앨지 말지를 결정할 확인 필요 항목** |
| **수치 기준선** | 검사가 **합계**로 나올 때 (테스트 실패 수) | "이 수보다 나빠지지 않았는가" 로 본다 | 기준선 문서에 **측정 조건**(커밋·환경·명령·집계 방식)과 기존 실패 목록 |

규칙:

- **세 전략 모두 "통과의 대가" 를 적는 칸이 필수다.** 적지 않으면 레포트만 보는 사람이 전수 검사 통과와 구분할 수 없다.
  (`status: external` 의 INFO, `done_elsewhere` 의 `not_verified_here` 도 같은 장치다 — §17·§3.)
- **기준선은 `target_dir` 안에 둔다.** `workspace/` 는 git 에 올라가지 않아 작업 환경이 바뀌면 사라진다(실측).
  판별: "이 파일을 다른 담당자도 봐야 하는가" 가 예면 `target_dir`, 아니면 `workspace`.
- **등록 기준선은 "그때 거기에 있던 것" 만 덮는다.** 같은 위반을 **새로 만드는 것은 여전히 금지**다
  (`datasources.py` 가 등록된 것만 `warn` 으로 내리고 새 파일은 `critical` 로 둔다).
  등록해 둔 항목이 실제로는 더 이상 없으면 `stale_baseline` 으로 드러나야 한다 — 기준선이 낡은 채로 통과시키지 않는다.
- **기준선을 넓히는 것은 사람 결정이다.** 에이전트가 자기 작업을 통과시키려고 항목을 추가하지 않는다.
  등록에는 발견 시점·근거·결정 항목이 필요하다.
- 기존 부채를 실제로 고치거나 새 부채가 생기면 **같은 변경에서 기준선을 갱신한다.**

새 검사를 추가할 때: **"기존 코드가 많은 저장소에서 이 검사를 처음 켜면 몇 건이 나오는가" 를 먼저 재 본다.**
많으면 위 셋 중 하나를 함께 설계한다. 차단만 만들고 전략을 안 만들면 사람이 검사를 끈다.

### 완화는 기존 파일에만 적용한다 — 새로 만드는 파일은 완화하지 않는다

실측된 함정: 기존 부채 때문에 품질 검사를 `warn` 으로 완화했더니 **이번 차수에 새로 만드는 파일도 함께 완화됐다.**
새 파일은 처음부터 규약을 지킬 수 있으므로 완화할 이유가 없다 — 같은 강도로 다루면 **새 코드의 품질이 기존 코드 수준으로 수렴한다.**

- `quality.py --new-files <추가된 파일…>` — 거기의 `major` 는 `--strict` 없이도 차단한다.
  `--files` 에 없어도 점검 대상에 들어간다(새 파일을 빠뜨리지 않게). 출력에 `[신규]` 로 표시한다.
- gate `productization` 은 **`pa-meta.repo.base` 가 있으면 `git diff --name-status <base>...HEAD` 의
  `A` 항목을 스스로 계산**한다 — 레포트에 새 칸을 요구하지 않는다.
  `repo.base` 가 없으면 **구분하지 못했다는 사실을 INFO 로 남긴다**(완화가 신규 파일에도 적용된다).
- 같은 생각을 다른 검사에도 쓴다: 기존 부채를 덮는 완화는 **그때 거기에 있던 것**만 덮는다.
