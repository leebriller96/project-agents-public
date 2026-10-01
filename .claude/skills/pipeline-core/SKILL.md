---
name: pipeline-core
description: project-agents 파이프라인의 공통 규칙 — 설정·상태·slice·리팩토링 요구서 파일 형식, 게이트, 병렬 실행, 레포트 규칙. 모든 /stageN·/refactor·/status 명령이 가장 먼저 읽는다.
---

# 파이프라인 공통 규칙 (pipeline-core)

모든 단계 명령과 에이전트는 이 문서를 먼저 읽고 따른다.

## 1. 시작 절차 (모든 명령 공통)

0. `workspace/<project>/HANDOFF.md` 를 읽는다(없으면 `templates/HANDOFF.md` 로 만든다). 사용자 원칙·브랜치·업로드 규칙·세션 시작 루틴이 여기 있다 - 거기 적힌 세션 시작 루틴(예: 기준 브랜치 최신화)을 먼저 수행한다.
   단계가 끝나거나 사람 결정이 나오면 HANDOFF.md 의 진행·결정 절을 갱신한다.
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
6. 병렬 developer 는 앱 기동이 필요할 때(계약 생성 등) **서로 다른 포트**를 쓴다 (오케스트레이터가 slice 마다 지정, 예: 18081/18082). 같은 `build/` 디렉토리를 공유하므로 전체 테스트(`gradlew test`)는 **웨이브 종료 후 오케스트레이터(또는 reviewer)가 1회만** 실행한다. developer 는 자기 slice 테스트(`--tests "<pkg>.<slice>.*"`)까지만 게이트로 삼는다.
   웨이브가 끝나면 **오케스트레이터가 전체 테스트를 1회 직접 실행**해 실패가 있으면 reviewer 를 부르기 전에 developer 재작업으로 돌린다 (reviewer 의 시간을 게이트 실패 확인에 쓰지 않는다).
   프론트도 같다: `node_modules`·`dist` 공유 → `build` 는 마지막 1회(실패 시 30초 후 재시도), vitest 는 파일 단위(`npm run test --run src/features/<slice>`)로 먼저, 전체는 마지막 1회.
   **검토·검증 에이전트도 같은 작업 트리에서 빌드하면 동시에 띄우지 않는다.** reviewer 와 equivalence-verifier 는 코드를 고치지 않지만
   둘 다 같은 `target/`(·`build/`)에서 테스트를 돌린다. 한쪽의 `clean` 이 다른 쪽 실행 도중 결과 파일을 지워 결과 출처를 가릴 수 없게 된 실측이 있다.
   순서대로 부르거나, 한쪽은 별도 git worktree(짧은 경로, `git -c core.longpaths=true`)에서 돌리게 지시한다. 어느 쪽이든 프롬프트에 "같은 작업 트리에서 다른 Maven/Gradle 실행이 없는지" 를 적는다.
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
- 타임스탬프는 항상 `python tools/kst_now.py` (파일명용 `yyMMddHHmm`; `--full` 은 본문용 `YYYY-MM-DD HH:MM`). bash `TZ=... date` 는 Windows Git Bash 에서 틀린다.
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
  테스트 수·실패 수 ↔ 실제 결과 파일(`gates[].results` 의 JUnit XML) 불일치 · 단계 시작 전 결과 파일 재사용 · 레포트의 이모지.
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
  "judgments": [{"kind": "substitution", "summary": "무엇을 정했나", "rationale": "왜",
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
- `judgments` 는 **자동 변환이 아니라 판단으로 정한 것**이다(§21). `deviations` 에 적은 것은 전부 판단이므로 `judgments` 에도 싣는다.
  id 없이 보고하면 오케스트레이터가 레포트 `pa-meta.judgments` 로 옮겨 `python tools/judgment.py import --report <레포트> --write` 로 채번한다.
- reviewer 는 같은 블록에 `findings[]`(§7 형식)를 함께 싣는다.

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
- **필요할 때만 나눈다.** 기준 이하 slice 에 units 가 있으면 과분할 경고다(unit 마다 에이전트 호출 4~5회가 추가된다). 기준 초과인데 나누지 않으면 근거를 1단계 레포트에 남긴다.
  기준값은 초기 추정치다 — 에이전트가 원문을 다시 읽지 않고 요약하기 시작한 크기를 실측하면 `config slicing` 을 고치고 `docs/LESSONS.md` 에 근거를 적는다.
- 강제: gate `unit-scope`(선행 unit 미완료·unit AS-IS 누락·slice 통합 조건), 훅(unit·slice 의 done 전환 시 게이트 실행 — 새 state 로 판정),
  `gate.py plan`(구조 오류면 멈춤, 분할 후보 알림), `status.py`(unit 진행 표).

## 21. 판단 기록 — 판단으로 정한 것은 검증 단계에서 다시 확인한다

실측된 한계: 2·3·4단계 게이트는 "만든 것이 빌드·테스트를 통과하는가" 만 본다. 그런데 사람이나 에이전트가 **판단**으로 정한 것
(대체 매핑, `불필요:` 판정, 폐기·범위 제외, AS-IS 결함 값을 유지할지, 근거가 모호한 곳의 해석, 지시와 다른 결정)은
그 판단 위에서 쓴 테스트도 같은 판단을 전제하므로, 판단이 틀렸으면 테스트까지 함께 틀리고 게이트는 통과한다.
판단은 레포트 산문(`deviations`·"결정" 절)에만 남아 다음 단계로 넘어가면서 사라진다. 그래서 판단은 채번해 두고, 검증 단계가 다시 확인한다.

**무엇이 판단인가**

| 판단 (기록한다) | 자동 변환 (기록하지 않는다) |
|---|---|
| 사람 결정 — decision open item 의 해소, 위임 판단, 승인 시 조건 | 카탈로그(`migration-sql`)의 등가 구문 치환 |
| 대체 매핑 — AS-IS 기능을 2차·공통·프레임워크의 다른 구현으로 대신함, `불필요:` 판정 | 공통 계약대로의 계승(패키지·시그니처 정리만) |
| 의미 차이 — 차이를 수용하거나 보정함(AS-IS 결함 값 유지·정상화, 절단·정렬·타입) | 프로필·`CONVENTIONS.md` 규칙을 그대로 적용한 것 |
| 범위 — 폐기(discard)·보류(hold)·이관 안 함·범위 제외 | 근거 문서에 명시된 동작을 그대로 구현한 것 |
| 해석 — 근거가 모호·부족한 곳에서 한쪽을 골라 구현함 | |
| 설계 선택 — 대안이 있는 배치·이름·설정 방식 | |
| 지시·계약·규약과 다르게 정한 것(`deviations`) | |

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

