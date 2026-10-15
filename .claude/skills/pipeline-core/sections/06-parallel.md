<!-- pipeline-core §6 — 핵심(SKILL.md)의 절 목록에서 가리키는 절. 필요한 작업일 때만 읽는다. -->

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
