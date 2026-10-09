# 실행 이력·교훈 로그 (LESSONS)

실제 프로젝트를 돌리며 드러난 문제와 파이프라인에 반영한 조치를 누적한다. 형식: 날짜 · 단계 · 현상 → 조치(반영 파일).

## 2026-09-20 — library-sample (샘플 검증, greenfield)

| 단계 | 현상 | 조치 |
|---|---|---|
| stage0 | 문서 5개(요구 22·화면 8·테이블 4)에서 §11 근거 부족 20건 도출. 의도적으로 심은 모순 4건 전부 탐지 + 실제 설계 결함(복합 PK FK 불가, 논리 삭제 필요, 동시성) 추가 발견 | 방법론 유효. 변경 없음 |
| stage0→1 | §11 항목 중 골격·마이그레이션에 필요한 결정(JWT 전달 방식, 코드 seed, 초기 계정)이 승인 없이는 2단계를 막음 | brief 에 **§12 결정 사항** 절을 두고 사용자 승인 결정을 기록하는 관례 도입 → `templates/PROJECT_BRIEF.md`·`stage1` 명령에 반영 예정 |
| stage1 | slice-planner 가 Book+Loan 을 한 slice 로 묶음(순환 의존 회피). 방법론 §2.5 "공통코드는 common-* slice" 와 달리 분리하지 않음 — 소비자 1개뿐이라 타당 | `stage1-slicing` §2.5 에 "소비자가 1개면 분리하지 않는다" 예외 추가 예정 |
| stage2 준비 | config `stack.backend.version: "17"` 이나 설치 JDK 는 21뿐. gradle CLI 없음(wrapper 캐시 8.10.2 만 존재). `mysql` CLI 없음, Docker 데몬은 실행 중 | config 를 21 로 갱신. **골격 전 환경 점검 절차**(JDK·빌드 도구·Docker·Node 확인 후 config 와 불일치 시 보고) 를 `stage2-backend` §A 와 `/stage2` 명령에 추가 예정 |
| 도구 | `tools/*.py` 출력이 Windows 콘솔(cp949)에서 깨짐; slices 템플릿의 `{id}` 가 YAML flow 시퀀스 파싱 오류 | `sys.stdout.reconfigure(utf-8)`, 템플릿 값 따옴표 처리 (반영 완료) |
| 도구 | Bash 도구로 10KB 넘는 다중 heredoc 명령이 통째로 실패 | 긴 파일은 Write 도구로 작성 (메모리 기록) |
| stage2 골격 | testcontainers 1.19.8(Boot 3.3 BOM) 이 Docker Desktop 29.7(API 1.55) 을 못 붙음(`Npipe ... Status 400`). DOCKER_HOST/API_VERSION 변경 무효 → **1.21.4 상향**으로 해결 | 프로필에 버전 요구 명시 |
| stage2 골격 | `@MybatisTest` 임베디드 DB 교체 → `spring.test.database.replace: none`; `@WebMvcTest` 가 SecurityConfig 미스캔 → `@Import` + `JwtTestSupport`; JWT 필터 @Component 시 중복 등록 | 프로필 단위테스트 규약에 추가 |
| stage2 골격 | 에이전트도 Bash heredoc 다중 파일 작성 실패 겪음 | 프로필·에이전트 지시에 "소스는 Write 도구" 명시 |
| stage2 골격 | 에이전트가 `ErrorCode` 를 인터페이스 + slice 별 enum 으로 설계 (공용 enum 병렬 수정 충돌 회피) — 프로필 기본(단일 enum)보다 나음 | 프로필 "골격 설계 메모" 로 채택 |
| stage2 골격 | 게이트 4개 명령 전부 실제 실행·통과(25 tests, H2 + testcontainers). 소요 약 24분, 84 tool call | 정상. 골격은 1회성이라 허용 |
| stage2 common-auth | 계약(OpenAPI) 생성에 앱 기동이 필요해 임시 MySQL 컨테이너(33061)+포트 18080 을 썼고 `servers.url` 이 18080 으로 찍힘 | 프로필에 "계약 생성은 test 프로파일(H2)로 기동하거나 springdoc 의 `servers` 를 상대경로로 고정" 추가 예정 |
| stage2 common-auth | 골격에 `Clock` 빈이 없어 시간 의존 로직(잠금 30분) 테스트가 어려움 → 에이전트가 생성자 주입으로 우회, common-candidates C-1 기록 | 프로필 골격 항목에 `Clock` 빈 추가 예정 |
| stage2 common-auth | 실패 횟수 UPDATE 가 BusinessException 롤백에 묻힘 → `noRollbackFor` | 프로필 규약에 "카운터성 갱신은 noRollbackFor 또는 REQUIRES_NEW" 메모 |
| stage2 common-auth | jjwt 가 키 길이로 알고리즘 자동 선택(HS384) → 명시 고정 필요 | 프로필 JWT 항목에 명시 |
| stage2 common-auth | developer 가 게이트 외에 실제 MySQL 기동 + curl 시나리오까지 자체 검증 (약 17분, 69 tool call) | 좋은 관행이나 5단계 통합테스트와 중복. "smoke 검증은 선택, 레포트에 구분 표기" 로 정리 예정 |
| stage2 common-auth 검토 | reviewer PASS, medium 1(실패 횟수 읽기-덮어쓰기 경합)·low 4. 게이트 재실행으로 보고 일치 확인. target repo 에 커밋이 없어 `git status` 로 공용 파일 변경 판별 불가 → 수정시각으로 대체 | pipeline-core §6-7 **target repo 커밋 규칙** 신설(골격·웨이브마다 오케스트레이터가 커밋). §7 에 medium/low → RR 또는 common-candidates 규칙 명문화 |
| stage2 common-auth 검토 | `@Pattern` 앵커 누락 → OpenAPI pattern 부분 일치 (FE/BE 검증 불일치 위험) | 프로필 검증 규칙에 앵커 필수. W2 developer 프롬프트에 교훈 전달 |
| stage2 W2 | 병렬 developer 2개가 계약 생성 기동 시 포트 충돌 가능, 전체 `gradlew test` 가 상대 컴파일 중 실패 가능 | pipeline-core §6-6: 포트 분리·자기 slice 테스트 우선·전체는 마지막 1회 |
| stage2 member | 병렬 실행 성공: member 가 전체 115 tests 통과(상대 slice 의 진행 중 테스트 9개 포함), 공용 파일 충돌 없음. 계약 생성 포트 분리(18082) 유효 | 정상 |
| stage2 member | H2 가 `testRuntimeOnly` 라 `bootRun` 으로 test 프로파일 기동 불가 → 프로젝트 밖 Gradle init 스크립트로 우회 (C-9) | 프로필 골격 항목에 **계약 생성용 `openApiDump` 태스크**(test 클래스패스 JavaExec 로 기동 → `/v3/api-docs.yaml/<group>` 저장 → `servers` 후처리) 추가 예정. 골격이 만들면 slice 마다 우회 불필요 |
| stage2 member | springdoc: 검색 조건 객체는 `@ParameterObject` 필요, boolean 파라미터는 `@Schema` 아닌 `@Parameter` 로 문서화해야 타입 유지. common-auth 와 다른 slice 의 Mapper 빈 이름 충돌(`MemberMapper`) → `MemberAdminMapper` | 프로필에 springdoc 메모·Mapper 명명 규칙(`<Slice><Entity>Mapper` 또는 slice 접두어) 추가 |
| stage2 book-loan | 가장 큰 slice(API 11, 테스트 88). 274k 토큰·83 tool call·24분. 병렬 member 와 Gradle 동시 실행 충돌 없음, 전체 194 tests 통과 | slice 크기 상한(API 5~20) 안이지만 상단. `stage1-slicing` 크기 기준에 "테스트 포함 예상 파일 30개 초과면 하위 slice 분할 고려" 메모 예정 |
| stage2 book-loan | member 와 동일하게 `bootRun` 계약 생성 우회(init 스크립트) 반복, `operationId` 자동 번호(`search_1`) 발생 → 11개 전부 명시 | 프로필: `@Operation(operationId=...)` 명시 규칙 추가. openApiDump 태스크는 골격 항목으로 이미 반영 |
| stage2 book-loan | 타 slice 테이블(tb_member) 테스트 데이터를 각 slice 가 JDBC fixture 로 따로 삽입 (C-17) | 프로필 테스트 규약에 "골격이 `src/test/resources/fixtures/<table>.sql` 공용 fixture 제공" 추가 예정 (3단계 C-17) |
| stage2 book-loan 검토 | reviewer PASS, medium 1(회원 단위 직렬화 없어 동시 대여 시 3권 초과 가능)·low 3. §12 결정(도서 행 잠금)만으로는 REQ-020 이 안 지켜짐 — 결정 사항이 요구를 완전히 덮는지 reviewer 가 잡아냄 | 프로필 동시성 규칙에 "한도(N권·N회) 검증은 한도의 주체(회원) 행을 잠근다" 추가 |
| stage2 W3 준비 | 의존성 추가(POI)가 필요한 기능이 slice 에 있으면 `build.gradle` 수정 금지 규칙과 충돌 | pipeline-core §6 충돌 방지에 "의존성 추가는 common-candidates 로 요청하고 slice 는 대안 구현 또는 인터페이스만" 명문화. 골격 단계에서 brief 를 훑어 **예상 의존성(엑셀·PDF·메일 등)을 미리 build.gradle 에 넣는** 절차 추가 |
| stage2 stats | `GlobalExceptionHandler` 가 `HttpMediaTypeNotAcceptableException`(406) 을 500 으로 변환 → 파일 다운로드 엔드포인트가 `produces=ALL_VALUE` 로 우회 (C-19). Clock 시간대가 slice 마다 다름(systemDefault vs Asia/Seoul, C-20) | 프로필 골격 항목: GlobalExceptionHandler 에 406/415 핸들러 포함, `ClockConfig` 는 config 의 시간대(환경정보)로 고정 |
| stage2 전체 | 4 slice 모두 reviewer PASS(blocker/high 0), medium 2·low 9 → RR 7건 + common-candidates 24건. 총 225 tests. 전체 소요 약 2시간 20분, 에이전트 9회 호출 | 정상. common-candidates 가 24건이면 3단계 부담이 큼 → 골격 체크리스트에 이번 회차 C-1/C-9/C-19/C-20 을 기본 포함시켜 다음 프로젝트에서 재발 방지 |
| stage2 stats 검토 | reviewer 가 `./gradlew test` 만 돌리면 Gradle 캐시로 `UP-TO-DATE/FROM-CACHE` 가 되어 실제 실행이 안 됨 → `cleanTest test --no-build-cache` 필요. developer 보고의 테스트 내역(Service 10/Controller 11)이 실제(9/12)와 달랐음(합계는 일치) | 프로필 명령 표에 reviewer 용 `cleanTest --no-build-cache` 추가, backend-reviewer 에이전트 지시에 명시. developer 는 테스트 수를 XML 결과에서 읽도록 |
| stage2 stats 검토 | operationId 프로필 규칙(`<slice>_<동작>`)이 실제 관행(`getBook`)과 어긋남 — 문서가 코드보다 늦게 쓰였고 검증 안 됨 | 프로필 규칙을 실제 관행(`<동사><명사>`, 그룹 내 유일)으로 수정 (C-26) |

## 2026-09-21 — library-sample (계속)

| 단계 | 현상 | 조치 |
|---|---|---|
| stage3 기준선 | **시간 폭탄 테스트**: common-auth 테스트 3건이 "고정 시각(17:00)으로 발급한 1시간 토큰을 시스템 시계 파서로 검증" → 18시 이후 항상 실패. stage2 검토 시점(17시대)엔 통과했으므로 developer·reviewer 모두 놓침. 3단계 refactorer 가 원칙대로 테스트를 안 고치고 RR-0008(high)로 남김 → stage3 `blocked` | 프로필 테스트 규약: "시각 고정 테스트는 발급·검증 양쪽이 같은 Clock 을 본다. 시스템 시계를 쓰는 파서/검증기는 고정 시각과 섞지 않는다". reviewer 체크리스트 §D-5 에 "고정 시각 + 시스템 시계 조합" 항목 추가. 골격 `JwtTokenParser` 에 Clock 주입 |
| stage3 | 27건 중 24건 처리, 3건 보류(추상화 과잉·요구 근거 없음·배포 항목). xlsx 전환은 §12 결정에 따른 동작 변경으로 §3 원칙 예외 명시. 계약 4개 재생성 diff 가 의도한 변경만인지 검증함 | 정상. `stage3-common` §3 에 "brief §12 결정에 따른 기능 전환은 동작 변경 예외로 허용하되 레포트에 명시" 추가 |
| stage3 | `-Pgroup` 이 Gradle 내장 `project.group` 과 충돌 → `startParameter.projectProperties` 로 읽음 | 프로필 openApiDump 설명에 `-PapiGroup=` 으로 이름 변경 권장 |
| /refactor | stage3 가 blocked 인 채로 /refactor 를 먼저 돌림(RR-0008 이 게이트를 막으므로). 순서: stage3 변경 커밋 → refactor 병렬(common-auth 4건 ‖ book-loan 3건) → member 1건 → stage3 게이트 재확인 | `/refactor` 명령에 "blocked 단계의 원인 RR 이 있으면 그것을 첫 묶음으로" 규칙 추가 |
| /refactor book-loan | RR-0005 동시성 결함이 testcontainers 로 **실제 재현**(잠금 제거 시 2건 성공) 후 수정 검증. `-Pmysql` 전용 테스트는 H2 에서 `@EnabledIfSystemProperty` 로 skip — "skip 금지" 규칙의 환경 조건부 예외 | pipeline-core §4 에 "환경 조건부 skip(도커 필요 등)은 조건과 사유가 어노테이션에 명시되고 해당 환경에서 실제 실행된 기록이 레포트에 있으면 허용" 예외 명문화 |
| /refactor | Docker Desktop 이 꺼져 있어 에이전트가 직접 기동. bash `TZ=Asia/Seoul date` 가 Windows Git Bash 에서 시스템(KST) 을 UTC 로 오인해 타임스탬프 오류 | 모든 스킬의 타임스탬프 명령을 **python 한 줄**(`tools/kst_now.py` 신설) 로 통일. 환경 점검에 `docker info` 결과가 "실행 중" 이 아니면 기동 시도 |
| /refactor common-auth | RR-0008 B안(파서 Clock 주입)은 골격에 생성자가 없어 불가 — 프로필 문서(내가 방금 추가)와 실제 골격 코드가 불일치 | 교훈 반영 시 "다음 프로젝트 골격" 과 "현재 프로젝트 후보(C-31)" 를 구분해 적어야 함. 프로필 변경은 현재 target 에 소급되지 않음 |
| /refactor | 병렬 developer 2개가 같은 `build/test-results` 를 써서 `cleanTest` 잠금 충돌 2회 → 폴링 후 성공 | pipeline-core §6-6 에 "Gradle 은 `--project-cache-dir`/별도 `build` 디렉토리를 쓰거나, 전체 테스트는 웨이브 종료 후 오케스트레이터가 1회만" 으로 조정 |
| /refactor book-loan 검토 | reviewer **FAIL(high)**: 새로 만든 동시성 테스트가 또 시간 폭탄(seed 고정 날짜 + 시스템 Clock 빈) — 방금 추가한 §D-5 체크리스트 항목이 잡아냄. 12일 뒤 LOAN_002 대신 LOAN_003 으로 오진될 결함. developer 재작업(1회차) 지시 | 체크리스트 되먹임이 작동. 추가로 프로필 테스트 규약에 "`@SpringBootTest` 통합 테스트는 `@TestConfiguration` 으로 `Clock.fixed` 를 override 하고 seed 날짜는 그 Clock 기준 상대값" 명문화 |
| /refactor book-loan 검토 | `-Pmysql` 전용 테스트가 RR-0005 의 유일한 회귀 근거인데 기본 게이트(H2)에서는 skip → 회귀가 조용히 재발 가능 | 5단계 시나리오와 stage state 에 "`-Pmysql` 동시성 테스트 1회 실행" 조건 명시. pipeline-core §4 게이트에 "환경 조건부 테스트는 그 환경에서 1회 실행이 게이트에 포함" 추가 |
| /refactor member | **InnoDB REPEATABLE READ 스냅숏**: "행 잠금 → 일반 COUNT" 는 잠금 전 스냅숏을 읽어 상대 커밋을 못 봄 → MySQL 에서 여전히 2건 성공(실측). 판정은 잠금 조회(current read)가 돌려준 결과로 해야 함. 내가 RR 수정안에 쓴 "잠금 후 count" 도 이 함정에 걸림 | 프로필 동시성 규칙: "잠금 뒤 판정은 `FOR UPDATE` 조회가 반환한 행/집계로만. 잠금 전에 읽은 값·잠금 없는 COUNT 는 스냅숏이라 쓰지 않는다". RR-0001(common-auth) 도 같은 패턴인지 5단계에서 확인 |
| /refactor member | 집합 불변식(활성 ADMIN ≥ 1)은 집합 전체를 PK 순 잠금. `(role, active)` 인덱스 없어 전체 스캔 잠금 (C-34) | 프로필: "집합 불변식은 집합 전체 PK 순 잠금 + 그 조건의 인덱스 필수" |
| stage4 골격 | 68 파일, 게이트 4개 통과(36 tests). 26분·106 tool call. 에이전트가 프로필보다 나은 설계: **라우트 자동 등록**(`import.meta.glob` 으로 `features/*/routes.tsx` 수집 → slice 가 router.tsx 를 안 건드림), `ApiError.fieldErrorMap()`, `api.download()` | 프로필 `react-ts.md` 에 자동 등록 패턴·`registerLogoutHandler` 훅 패턴 채택 |
| stage4 골격 | vitest jsdom + react-router 데이터 라우터의 `AbortSignal` 충돌(jsdom vs undici) → 커스텀 환경 파일. jsdom `Blob.text()` 없음 → 폴백. `vitest/config` 가 `loadEnv` 미재export | 프로필 "알려진 문제" 절 신설 |
| stage4 골격 | 생성 타입이 응답 스키마 `required` 부재로 전부 optional (F-4) — backend 계약 품질 문제 | stage2 프로필 OpenAPI 항목에 "응답 DTO 는 `@Schema(requiredMode=REQUIRED)` 또는 Java record + `@NotNull` 로 required 명시" 추가. 현재 프로젝트는 common-candidates |
| stage4 common-auth | reviewer PASS, low 4. developer 가 오케스트레이터 지시("/me 재호출")보다 골격 CONVENTIONS(login 응답으로 setUser)를 우선함 — reviewer 도 타당 판정 | pipeline-core §7 에 "골격 CONVENTIONS > 오케스트레이터 프롬프트. 충돌 시 developer 는 규약을 따르고 보고에 명시" 명문화 |
| stage4 common-auth | react-query mutation variables 에 비밀번호가 gcTime(5분) 동안 잔존 (RR-0010) | `react-ts.md` 규약: "자격증명을 보내는 mutation 은 `gcTime: 0`" |
| stage4 W2 | 프론트 병렬 developer 는 `node_modules`·`dist` 공유 → build 는 마지막 1회. vitest 는 파일 단위라 동시 실행 가능 | pipeline-core §6-6 에 프론트 버전 추가 |
| stage4 member 검토 | reviewer medium: zod 스키마 max 길이 규칙에 테스트 없음 — "검증 규칙마다 테스트 1건" 을 developer 가 일부만 지킴. URL 복원 파라미터 길이 미검증 | `react-ts.md` 테스트 규약에 "zod 스키마의 모든 규칙(required/min/max/pattern/format)을 표로 뽑아 각 1건, 붙여넣기 경로(maxlength 제거)로 검증" + "URL 에서 복원한 검색 조건도 스키마로 정규화" 추가 |
| stage4 book-loan 검토 | reviewer PASS, medium 2 — member 와 **같은 종류**(URL 검색 조건 미정규화, zod max 규칙 1건 테스트 누락). 프로필 규칙은 member 검토 후 추가됐으나 book-loan developer 는 그 전에 시작해 못 봄(병렬 웨이브) | 같은 웨이브에서 발견된 교훈은 다음 웨이브부터 적용됨을 인정. `/stage4`·`/stage2` 명령: 웨이브 종료 후 reviewer 지적 중 "규칙 부재로 인한 것" 은 **같은 웨이브의 다른 slice 에도 해당하는지 오케스트레이터가 grep 으로 확인**해 RR 을 묶어 만든다 |
| stage4 book-loan | 화면 5개·API 11개·테스트 77, 290k 토큰·23분. RR 없이 계약만으로 완결 — 2단계 계약 우선 원칙의 효과 | 정상 |
| stage4 stats | 최신 규칙(URL 정규화·zod 전수 테스트)을 프롬프트에 명시하니 developer 가 선반영 — 같은 종류 지적 재발 없음(reviewer 확인 예정). recharts 는 jsdom 에서 `ResponsiveContainer initialDimension` 으로 목 없이 렌더 검증 가능 | `react-ts.md` 알려진 문제에 recharts 항목 추가. 번들 1.1MB(recharts) → 골격 항목에 "차트/에디터 등 무거운 라이브러리는 라우트 lazy + manualChunks 기본" 추가 |
| stage4 stats | `vi.stubGlobal('URL', {...})` 이 `new URL()` 을 깨뜨림 → `defineProperty` 로 메서드만 추가. 골격 queryClient 의 5xx 재시도가 실패 토스트 테스트를 4초 지연 | 프로필: 테스트 QueryClient 는 `retry: false`(골격 `createTestQueryClient` 가 보장) |
| /refactor FE | react-query `gcTime: 0` 은 observer 분리 후에만 작동 — 로그인 실패 시 폼이 남아 비밀번호 variables 잔존. developer 가 소스를 읽고 `reset()` 추가 + 역검증(gcTime 제거 시 테스트 실패 확인) | 프로필 규약 보강 |
| /refactor FE | 3 slice 가 URL 정규화를 "필드 단위 safeParse, 실패 필드만 기본값" 으로 일관 구현 — stats 선반영 패턴을 참고 지시한 효과 | 3단계 2회차에서 `shared/` 헬퍼로 승격(F 후보) |

## 2026-09-21 (오전) — stage5 통합 테스트

| 단계 | 현상 | 조치 |
|---|---|---|
| stage5 common-auth | 첫 slice 가 환경(MySQL 컨테이너·BE jar·vite preview·Playwright 격리)을 구성하고 `env-up.sh/env-down.sh` + `docs/test/README.md` 로 남김 → 이후 slice 재사용. 29분 소요 | `stage5-integration-test` §2 에 "첫 slice 가 환경 스크립트를 만들고 README 로 남긴다, Playwright 는 `tests/integration/package.json` 격리" 명문화 |
| stage5 common-auth | 개발 PC 의 8080·5173 이 다른 프로세스에 점유 → 18080/5174 기본값. Git Bash 에서 `env-up.sh | tee` 하면 백그라운드 java 가 파이프 핸들을 물어 안 끝남 | 스킬 §2 에 포트 회피·파이프 금지 주의 추가 |
| stage5 common-auth | **RR-0009 갭 잠금 실측**: 미존재 사번 로그인 워커 8개 부하 중 회원 등록 INSERT 가 1538ms(단독 68ms, 22.6배), 3s 부하면 기아. `performance_schema.data_locks` 로 X,GAP 459건 관측 → severity low→medium | 5단계가 "RR 의 실제 심각도 측정" 역할을 함을 확인. 프로필 동시성 규칙에 "미존재 키 `FOR UPDATE` 는 갭 잠금 → 존재 확인 후 잠금" 추가 |
| stage5 common-auth | 정적 검증에서 FE zod `min(1)` 이 공백만 통과, BE `@NotBlank` 400 → FE 느슨(RR-0014). JDBC 세션 TZ 미고정으로 seed `NOW()` 와 앱 Clock 9시간 차(RR-0015, C-4 재확인) | `react-ts.md`: 문자열 필수 검증은 `.trim().min(1)`; 프로필 골격: JDBC URL 에 `serverTimezone=Asia/Seoul`(또는 `connectionTimeZone`) 고정 + Flyway seed 는 `CURRENT_TIMESTAMP` 대신 앱 시간대 명시 |
| stage5 book-loan | API 43 + UI 5 전부 통과, 동시성 2종 5라운드 회귀 없음. RR 3건 모두 low — 2·4단계 계약 우선·reviewer 게이트의 효과. 발견: 생성 상태코드 slice 간 불일치(200 vs 201), LIKE `%`/`_` 미이스케이프, 역직렬화 실패 시 fieldErrors 비어 있음 | 프로필: "생성은 201 통일" 을 골격 CONVENTIONS 규약에, MyBatis LIKE 는 `ESCAPE` + 이스케이프 유틸(골격 common/util), GlobalExceptionHandler 가 `HttpMessageNotReadableException` 의 경로를 fieldErrors 로 변환 |
| stage5 book-loan | 정적 검증에서 기동 BE 의 `/v3/api-docs` 와 계약 파일 diff, `gen:api` 재생성 diff 를 함께 확인 — 계약 드리프트 0 | `stage5-integration-test` §4 에 "기동 BE 의 api-docs ↔ 계약 파일 diff" 항목 추가 |
| stage5 member | API 22 + UI 5 통과, RR-0004 동시성 5라운드 회귀 없음. RR-0017 LIKE 횡전개 **재현**(새 RR 대신 evidence 보강 — 횡전개 규칙 작동). 신규 low 2: 검색 DTO trim 불일치(book-loan 은 trim, member 는 미trim), 검증 실패 메시지가 Spring 영문 내부 메시지 노출 | 프로필: 검색 DTO 문자열은 골격 `@TrimmedString`(또는 setter trim) 으로 통일; GlobalExceptionHandler 가 타입 변환 실패(`MethodArgumentTypeMismatch`) 메시지를 한글 규격 문구로 변환 |
| stage5 member | C-3(비활성 계정의 기존 토큰이 만료까지 유효) 현 동작 기록 — 요구 근거 없어 RR 아님. 6단계 보안 점검에서 판단될 항목 | 정상. stage6 프롬프트에 "C-3 현 동작" 을 점검 포인트로 전달 |
| stage5 stats | API 18/19(Content-Type charset 1건 실패 → RR-0021), UI 5/5. xlsx 를 의존성 없이 zip+XML 로 직접 파싱해 검증. **RR-0015 월 경계 실측**: 실행이 KST 08:55(UTC 전날) 창에 걸려 같은 분에 API 대여는 09-21, SQL `CURDATE()` 대여는 09-20 으로 기록됨 — 앱 경로는 정확, 영향은 SQL `NOW()` 로 만든 행(seed·이관·배치)에 한정 | 시각 의존 결함은 "재현 창" 을 시나리오에 명시. 골격 규칙(JDBC TZ 고정) 유지, 이관 계획 시 medium 상향 조건 기록 |
| stage5 전체 | 4 slice API 101/102 + UI 19/19. RR 9건 중 medium 2·low 7 — **blocker/high 0**. 2·4단계 reviewer 게이트 + 계약 우선이 통합 단계 결함을 낮은 등급으로 눌렀음. 소요 약 1시간 40분 | 정상. `/refactor` 순서를 3(common 기반) → 2(slice) → 4(FE) 로 조정: LIKE 유틸·trim 등 공용 기반이 먼저 있어야 slice RR 이 깔끔 |
| /refactor 순서 | 규칙은 target_stage 1→2→3→4 이지만, 이번엔 stage 2 RR(LIKE·trim)이 stage 3 공용 유틸에 의존 → 3 을 먼저 | `/refactor` 명령: "stage 2 RR 이 공용 기반을 필요로 하면(suggested_fix 에 common/ 언급) stage 3 묶음을 먼저" 규칙 추가 |
| /refactor iter4 common | RR 4건 + 공용 기반 처리, **RR-0019 가 공용 trim advice 로 자동 해결**(slice 코드 무변경). LIKE 이스케이프 문자 `\` 는 H2/MySQL 에서 서로 다르게 동작해 `!` 로 결정(실측) — 내가 프로필에 쓴 `\` 규칙이 틀림 | 프로필 LIKE 규칙 `!` 로 정정. "공용 기반이 slice RR 을 자동 해결하면 developer 호출 없이 done 처리(테스트로 증명)" 를 `/refactor` 에 명시 |
| /refactor iter4 common | 명명 TZ 강제(`connectionTimeZone=Asia/Seoul`)는 시간대 테이블 없으면 접속 실패 — 조용한 드리프트 대신 즉시 실패가 낫다는 판단 | 배포 가이드 항목으로 8단계에 전달 |
| /refactor iter4 common-auth | RR-0009 갭 잠금: 존재 확인 후 잠금으로 부하 중 INSERT **1540ms → 82ms(1.1배)**. 수정 전 코드로 되돌려 같은 테스트가 실패함을 확인(5단계 실측 1538ms 와 일치) — 결함 재현·수정·회귀 테스트가 한 사이클로 닫힘 | 정상. 테스트 JVM stdout cp949 로 한글 로그 깨짐 → C-37(`stdout.encoding=UTF-8`), 프로필 골격 build.gradle 항목에 추가 |
| /refactor iter4 FE | RR-0014: 내 지시 `.trim().min(1)` 은 비밀번호 값을 변환해 전송하는 문제 — developer 가 RR evidence("BE 는 trim 없이 BCrypt")를 근거로 `refine` 선택. 규약 우선순위(evidence·근거 > 프롬프트 세부)가 작동 | 프로필: 비밀번호류는 `refine` |
| /refactor iter4 FE | 201 후속: 통합 테스트 기대값 변경이 지시(2곳)보다 많음(18곳) — developer 가 grep 으로 전수 수정. 통합 테스트 실제 재실행은 안 함 | 6·7단계 전에 5단계 재실행 필요 항목으로 기록. `/refactor` 명령 7항에 "stage 2 반영 → 그 slice 의 stage5 pending" 규칙대로 book-loan·member·common-auth stage5 를 pending 으로 되돌림 |

## 2026-09-21 (오전) — stage6 보안 점검

| 단계 | 현상 | 조치 |
|---|---|---|
| stage6 준비 | SAST 4종(semgrep/bandit/gitleaks/osv-scanner) 전부 미설치 → claude-only 폴백. 소스 284개 > 150 → slice 병렬 scan + merge | 환경 점검 절차에 "6단계 전 SAST 설치 여부 확인·설치 권고(WSL/도커)" 추가. 골격 단계 환경 점검 표에 SAST 항목 포함 |
| stage6 book-loan | 외부 `export_findings.py` 가 `### [F-<숫자>]` 만 인식 → `F-BL-###` 접두어 불가. slice 별 **번호 대역**(F-2xx/F-3xx/F-4xx)으로 대체 | `stage6-security` §2 대규모 절차에 "slice 별 F-번호 대역 배정(오케스트레이터가 지정), merge 시 그대로 유지" 명시 |
| stage6 book-loan | Low 3·Info 2, Critical/High/Medium 0. 발견의 질: ISBN 중복 경합이 500(member 는 409 — slice 간 불일치), 비활성 계정 토큰으로 대여 가능(C-3 연계), 상태 변경 POST 가 SameSite 단일 방어 | 프로필 골격: `DataIntegrityViolationException` 공용 409 변환, 인증 필터에서 비활성 계정 즉시 거부(DB 조회 1회 또는 캐시), 상태 변경 요청에 커스텀 헤더 요구 — 6단계 merge 후 RR 로 |
| stage6 merge | 병렬 4 scan 24건 → 병합 20건(통합 5·신규 1). 같은 근본 원인(초기 비밀번호·비활성 토큰·PageParam)이 3 slice 에서 각각 잡혀 merge 가 하나로 묶음. 경계 흐름 5개 중 확정 3·부분 1·기각 1(잠금 순환 없음) | merge 방식 유효. `stage6-security` §5 merge 규칙에 "통합 시 근본 원인 위치를 대표로, sink 는 evidence 로" 예시 추가 |
| stage6 결과 | High 2건 모두 **0단계 §11 근거 부족(11-08 초기 비밀번호)** 에서 이미 표시됐던 사양 문제. 코드 결함이 아니라 요구사항 결정 부재 → RR 은 만들되 "사업 결정 선행" 표시 | `/stage6` 명령: RR 중 "사양 결정 필요" 는 brief §12 결정 요청으로 사용자에게 올리고 `/refactor` 에서 결정 전 착수 금지. `/stage1` 8항(2단계 전 결정 필요 항목)에 "보안 관련 §11 항목(초기 비밀번호·토큰 폐기·TLS)은 반드시 포함" 추가 — 6단계까지 미루지 않도록 |
| stage6 | 6단계 실행 시간 약 1시간 10분(scan 4 병렬 2웨이브 + merge). 토큰 약 900k | 정상. hybrid 였다면 SAST 결과 검증 시간이 더 필요 |

## 2026-09-21 (오후) — refactor iteration 5 (보안 RR)

| 단계 | 현상 | 조치 |
|---|---|---|
| iter5 common | RR 5건 + A안 공용 기반. Boot 3.3.5→**3.4.13** 상향 성공(springdoc 2.8 동반, `@MockBean→@MockitoBean`), lockfile 도입. 306 tests(+39), `-Pmysql` 전체 통과. 31분·114 tool call | 프로필: 골격 기본 버전을 Boot 3.4.x + springdoc 2.8 + `springdoc.api-docs.version=openapi_3_0` 고정(2.8 기본 3.1 이 계약 형식을 흔듦), `dependencyLocking` 기본 |
| iter5 common | 인메모리 rate limit 이 통합 테스트(한 IP 수백 회 로그인)를 막음 → env-up.sh 에 `..._ENABLED=false` | 프로필: "보안 필터는 설정으로 끌 수 있게, 통합 테스트 환경은 rate limit 비활성" |
| iter5 common | OriginCheck 는 nginx `proxy_set_header Host $host` 없으면 전부 403 — 배포 가이드 필수 항목 | 8단계 배포 가이드 체크리스트에 추가 |
| iter5 BE 검토 | reviewer **FAIL(high 2)**: ① `@Primary` provider 가 MyBatis 세션이라 `@Transactional` 테스트 안에서 **1차 캐시** 로 stale 상태 반환 → 공용 회귀 테스트 실패(developer 는 slice 부분 실행만 해서 못 봄, 오케스트레이터가 고친 C-47 단언도 이 실패는 못 잡음). ② rate limit 이 `X-Forwarded-For` **첫 값**을 키로 — nginx 표준은 클라이언트 값 뒤에 실 IP 를 덧붙이므로 스푸핑 가능 → 내 프롬프트 지시("첫 값 사용")가 틀렸음 | 프로필: "인증/상태 조회 Mapper 는 `flushCache=true useCache=false`", "XFF 는 신뢰 프록시 홉 수 기준 **마지막 값**". 병렬 웨이브 후 전체 테스트를 reviewer 전에 오케스트레이터가 1회 돌려 먼저 잡는 게 낫다 — pipeline-core §6-6 에 "웨이브 종료 시 오케스트레이터가 전체 테스트 1회, 실패면 reviewer 전에 developer 재작업" 명시 |
| stage6 재점검 | `report_diff`: 해결 10·잔존 10·신규 1. 해결 10건 전부 코드로 실확인, 놓친 것 0. 신규 코드(비밀번호 변경 API·필터 3종·runner)를 새 공격면으로 점검 → Low/추정 1건뿐. 되돌린 RR 0 | 재점검 절차(§5) 유효. 남은 것은 운영 배포 전 확정 항목(TLS·ADMIN_INITIAL_PASSWORD·XFF 신뢰 설정) → 8단계 배포 가이드 체크리스트로 |
| 구조 | 사용자 지시: 외부 도구를 별도 clone 하지 않고 project-agents 하나만 받아 쓰게 → **git subtree** 로 `external/` 편입 (submodule 은 `--recursive` 필요라 제외). 경로는 tools.yaml 상대경로, `tools/sync-external.sh` 로 upstream 갱신 | 도구의 `reports/.sast`·`.tests` 산출물은 gitignore. 도구 안의 `.claude/`·`CLAUDE.md` 는 루트가 아니라 자동 로드되지 않음(의도) |

## 2026-09-21 (오후) — stage5 재실행(r2)·refactor iter7

| 단계 | 현상 | 조치 |
|---|---|---|
| stage5 r2 | 4 slice **API 126/126, UI 24/24**(r1 101/102·19/19). 재실행이 refactor 4·5 의 효과를 전부 실측으로 확인: 갭 잠금 22.6배→1.3배, 비활성 토큰 200→401, Content-Type 통과, ISBN 동시 등록 201+409, export 상한 10k, A안 흐름. 신규 RR 5건 전부 low(문서·타입 stale) | 재실행 = 회귀 게이트로 유효. `stage5-integration-test` 에 "재실행(rN) 은 이전 결과 병기, 기대값 변경 건수 보고" 규칙 추가 |
| stage5 r2 | 첫 slice 가 만든 `provisionChanged()`(A안 초기 상태 해제) 헬퍼를 나머지 3 slice 가 import 로 재사용 — 헬퍼 인계 규칙이 작동 | 정상 |
| stage5 r2 | RR 5건 중 3건이 **계약/타입 stale**(BE 계약 재생성 후 FE `gen:api` 미실행, 계약 설명이 정책 변경 미반영). `/refactor` 가 BE 계약을 바꾸면 FE 타입 재생성을 자동으로 붙여야 함 | `/refactor` 7항에 "target_stage 2 반영으로 `docs/api/*.yaml` 이 바뀌면 같은 회차에 FE `gen:api` 재생성 작업을 자동 추가" 규칙. 계약 설명 문구도 정책 결정(§12) 변경 시 grep 대상 |
| stage5 r2 | TZ 재현 창(00~09 KST) 밖 실행이라 SQL `CURDATE()` 케이스 직접 재확인 불가 → 커넥션 time_zone·seed 값·세션 CURDATE 로 간접 확인 | 시각 의존 시나리오는 "재현 창 밖이면 간접 증거 3종" 패턴을 스킬에 예시로 |

## 2026-09-21 (오후) — stage7 QA

| 단계 | 현상 | 조치 |
|---|---|---|
| stage7 | external/qa-automation 첫 사용(subtree). 1,351건 실행(BE 368·FE 341·통합 153·생성 53). 확정 결함 2 + 플래키 1 — **DB 응답 정지 시 무기한 대기**(JDBC socketTimeout 미설정, 30초 재현), `/error` 디스패치 비-ApiResponse, `Auditable.markUpdated` 가 Clock 빈 미사용 | 프로필 골격: datasource `connectTimeout/socketTimeout` + MyBatis `defaultStatementTimeout`, `ErrorController` 를 ApiResponse 로, `Auditable` 은 Clock 주입. 셋 다 첫 샘플 골격 결함 → 다음 골격 체크리스트 |
| stage7 | **외부 도구 버그**: `run_tests.sh` 가 Windows(cygpath)에서 Gradle 결과 glob `*` 를 제거해 0건 집계, `./gradlew test` UP-TO-DATE 를 ran 으로 기록. 에이전트가 `cleanTest` + runs.tsv 보정으로 우회 | **upstream 수정 후보** → qa-automation repo 이슈로: (1) Windows glob 처리, (2) Gradle 은 `cleanTest test` 강제, (3) `-Pmysql` 같은 프로파일 인자 전달 옵션. 수정되면 `tools/sync-external.sh` 로 가져옴 |
| stage7 | 러너가 `tests/integration` 을 설정 없이 Playwright 로 실행해 에러 5·스킵 19 → 환경 문제로 분류(정상 환경 24/24) | qa-automation 에 "환경 기동 훅(pre-run 스크립트) 지정" 옵션 upstream 후보. 파이프라인: `docs/test/README.md` 의 env-up 을 7단계 프롬프트에 명시(이미 함) |
| stage7 | 소요 48분·421k 토큰·128 tool call — 단일 단계 최대. 1,351건 실행 + 우회 작업 | 대규모면 7단계도 "기존 테스트 실행" 과 "신규 생성·triage" 를 두 에이전트로 분할 검토 |
| refactor iter8 | RR-0041: 내 지시 "URL socketTimeout=30000, 10초 내" 가 실측과 어긋남 — (1) URL 파라미터는 테스트가 URL 을 통째로 바꾸면 무효 → Hikari 프로퍼티, (2) 실패까지 ≈ socketTimeout×2(5회 실측), (3) statement timeout 은 무응답에 무효, (4) MyBatis-Spring 예외 변환기가 첫 예외 때 메타데이터 커넥션을 새로 얻어 +12초 → 선적재. developer 가 전부 실측으로 잡음 | 프로필 정정. "타임아웃 값은 반드시 정지 시나리오로 실측해 결정" 규칙 |
| 외부 도구 | qa-automation `run_tests.sh` 버그 3종을 project-agents 에서 고쳐 **subtree push 로 upstream 반영**(`39f351e`). 이후 upstream 은 `sync-external.sh` 로 | 마스터 repo 워크플로 확립: 도구 버그 → external/ 수정 → `tools/push-external.sh` |

## 2026-09-21 (오후) — stage8·library-sample 완료

| 단계 | 현상 | 조치 |
|---|---|---|
| stage8 | 12종 생성(md 2,688행). 04·05 는 마이그레이션·OpenAPI 를 스크립트 파싱. 08 은 재실행 현재 값. RTM 끊김 6건은 전부 "요구 자체가 범위 밖/비기능"(REQ-025 제외, NFR-001 부하, NFR-005 Edge) — 코드 누락 0 | 정상. `@DisplayName` REQ 표기율 130/378(34%) → 프로필 테스트 규약에 "REQ 를 다루는 테스트는 DisplayName 에 ID 필수" 를 게이트(reviewer §D-5)로 승격 |
| stage8 | `build_report.py` 가 mermaid 미포함 → html 에서 ERD·구성도가 코드로 보임 | `tools/build_report.py` 에 mermaid.js CDN + ```mermaid 블록 변환 추가(아래 반영). 두 subtree 의 build_report.py 도 동일 개선 후보 |
| stage8 | `state.yaml` RR 카운터가 stale(iter7·8 미갱신) — `rr.py stats --write` 를 매 refactor 종료 시 호출하는 걸 빠뜨림 | `/refactor` 8항에 이미 있음 → 오케스트레이터 누락. `rr.py set` 이 done 처리 시 state 카운터를 자동 갱신하도록 도구 개선 |
| 전체 | **library-sample 0~8단계 완료**: iteration 8, RR 42(done 41·rejected 1), BE 375·FE 341·통합 150·QA 53 tests, target 커밋 30개, project-agents 커밋 약 80개, LESSONS 약 90건, 총 에이전트 호출 약 70회 | 두 번째 샘플(차세대) 착수 — `docs/samples/sample2-migration-brief.md` |

## 2026-09-21 (저녁) — sample2 (차세대 migration) 1차 배치

| 단계 | 현상 | 조치 |
|---|---|---|
| stage0 migration | 요구사항 문서 0 → AS-IS 동작 계약에서 REQ 34 채번. 기능 계약 12+분기 44, 공통 인벤토리 73(사용처 0 = 10), SQL 인벤토리 18(A15/B1/C3/D1). **채점표 18/18 포착**, 의미차이 태그로 2단계 함정까지 사전 포착. §11 30건 | 방법론 유효. 두 에이전트 병렬(ingest ‖ sql-migrator) 후 수치 교차 대조가 자연스럽게 됨 — `/stage0` 명령에 "migration 이면 두 에이전트 병렬, 완료 후 statement 수 대조" 명시 |
| stage0 migration | sql-migrator 가 카탈로그에 없는 구문 9개를 스킬에 직접 추가 — "에이전트가 방법론 파일을 갱신" 하는 첫 사례. 위험: 병렬 에이전트가 같은 파일을 고치면 충돌 | 규칙: 스킬 파일 자기 갱신은 `sql-migrator` 의 카탈로그 §2 표에만 허용, append 만, 오케스트레이터가 커밋 |
| stage0 migration | 입력 소스에 운영 DB 비밀번호 평문(운영 프로파일 설정 파일) — 에이전트가 값을 산출물에 복사하지 않고 위치만 기록 | `stage0-ingest` §2 에 "AS-IS 설정의 비밀값은 마스킹, 위치만" 명문화(6단계 규칙을 0단계로 앞당김) |
| stage0 migration | §11 30건 중 slice 구조·접근 통제·인증 범위 결정이 stage1 을 막음 — 첫 샘플의 "2단계 전 결정" 이 migration 에서는 **1단계 전**으로 당겨짐 | `/stage0` 명령: migration 이면 stage0 종료 시 "stage1 전 결정 필요" 목록을 따로 제시 |
| stage2 골격 (sample2) | Boot 4.0.8 골격 51분·434k 토큰·180 tool call — 첫 샘플 골격의 2배. 원인: Maven 설치·wrapper 생성, Boot 4 패키지 이동·Jackson 3·Security 7 CSRF·Testcontainers 2 등 호환 이슈 8건을 전부 실측으로 해결 | 프로필 "알려진 주의" 에 실측 조합·패키지·CSRF 테스트 패턴 기록 → 다음엔 재발 없음. 골격은 1회성이라 허용 |
| stage2 골격 (sample2) | 에이전트가 permitAll 범위를 내 프롬프트(`GET /notices/**`)가 아니라 brief §12-A R11·기능 계약 FC-12(상세·첨부·분류만 공개, 목록은 인증)대로 결정 — 규약 우선순위 작동 | 정상 |

## 2026-09-22 — sample2 stage2 W1 (domain-notice: sql-migrator convert → reviewer)

| 단계 | 현상 | 조치 |
|---|---|---|
| stage2 convert | Oracle 18 statement 변환 첫 실전: 매핑표 20행 100%, 의미차이 16건 전부 `파일:라인` 근거(reviewer 무작위 대조 16건 일치), MySQL 실측으로 GROUP_CONCAT 절단(1024B) 실제 재현. **채점표 2단계 함정 8/8**. 카탈로그 +4행 | 방법론 유효. 실측 후 의미차이 결론이 뒤집힌 곳의 **XML 주석**은 옛 결론 그대로 남음 → sql-migrator 규칙 "실측 후 주석 동기화", reviewer "주석↔매핑표 상충 grep" |
| stage2 convert | API·서비스가 없는 **공유 도메인 slice**(domain-notice) 는 developer 단계가 없어 기능 추적표(FB-07~13) 를 아무도 안 만듦 → reviewer FAIL(high). 산출물 경계가 비면 게이트가 통째로 빠진다 | `sql-migrator` 규칙: 공유 도메인 slice 는 convert 가 function-mapping 까지. reviewer D-4 에 "API 없는 slice 도 추적표" 추가 |
| stage2 convert | `USE_YN` → `use_yn`+`del_yn` 분리 후 옵션(`includeDeleted`) 으로 포함시킨 삭제 행을 목록 DTO 가 구분 못 함(delYn 없음) → 관리자 화면 FB-35/36 재현 불가 | 카탈로그 규칙: 컬럼 분리 변환 시 옵션 포함 행을 구분할 컬럼을 행 DTO 에 함께 반환. reviewer 체크 추가 |
| stage2 convert | `SYSDATE → Clock 바인드` 변환에서 `null → CURRENT_DATE` 폴백을 넣음 → 서비스가 Clock 바인드를 빠뜨려도 조용히 통과(§4 now() 금지 우회 경로). 테스트도 고정 기준일과 DB 시계가 한 메서드에 섞임 | 폴백 제거(fail-fast), 카탈로그 행에 권장 명시. 테스트는 시계 경로별로 분리 |
| stage2 convert | 테스트 `@DisplayName` REQ 번호 오연결 3건(트리→REQ-004 상단고정, 페이징→REQ-002 검색) — 8단계 추적표 원천 오염 | sql-migrator·reviewer 에 "REQ 번호 ↔ brief §8 제목 대조". 후보: `tools/trace_check.py` 기계 대조 |
| stage2 convert | 800 이관 대역 번호가 골격 README(notice→file→class) 와 slice 규칙 문서(class→notice→file, FK 순) 에서 다름. FK 순이 맞음 | 프로필: 800 번호는 FK 참조 순으로 골격이 매김. 골격 README 정정은 C-07(공용 파일) |
| stage2 convert | 근거 부족 S-1(collation) 을 매핑표가 `brief §11 "3"` 으로 인용했으나 brief §11 에 항목 자체가 없었음(실제 출처 SQL 인벤토리 §10) → 사람 확인 누락 위험 | brief §11-31 추가. sql-migrator 규칙: §11 에 없는 근거 부족은 "brief §11 후보" 로 분리 보고, 인용은 실제 출처 |
| stage2 convert | 매핑표 행 수 표기 혼선(보고 19 / 실제 20 = fragment 포함) | 통계 형식 고정 "statement N(정의 n + B m) + fragment k = 행 수" |

## 2026-09-22 — sample2 stage2 W2 (notice user ‖ notice-admin admin)

| 단계 | 현상 | 조치 |
|---|---|---|
| stage2 notice | 다운로드 `Content-Length` 를 DB `file_size` 로 내보냄(AS-IS 는 `realFile.length()`). 통합 테스트가 실물 5B vs fixture 1024 불일치를 만들면서도 헤더를 단언하지 않아 통과 — **테스트가 결함을 재현하고도 못 잡은 사례** | 프로필: `Resource.contentLength()`, 특성화 테스트 "실물 바이트 == Content-Length" 단언 규칙. 추적표에 비기능 세부도 동작 차이로 기록 |
| stage2 notice | 분류 트리 permitAll 을 "근거 부족(N-1)" 으로 올렸으나 brief §12-A R11 이 이미 결정(상태 "확인 요청"). §12-B 만 보고 판단 → 3단계에 불필요한 C-08 | stage2 §B-2-1: 근거 부족 전 §12-A R행(확인 요청 포함) 전부 grep 대조 |
| stage2 notice | 골격 테스트 `UserApplicationTest` 가 "핸들러 없어 404" 를 전제 → slice 가 골격 테스트를 수정하게 됨(공용 규칙 위반 아님이지만 결합) | 골격 §A-8: 빈 상태 전제 금지, "401 아님 + 봉투" 수준 |
| stage2 notice | 한 모듈의 `@SpringBootTest` 2개가 같은 H2 인메모리 DB(`secu_user`) 를 공유해 fixture 누출 → developer 가 IT 의 datasource url 을 `properties` 로 override. **그 override 가 `-Pmysql` 프로파일보다 우선해 웨이브 MySQL 게이트에서 9건 컨텍스트 실패** — 모듈 단위 게이트(H2)만 보고 통과시킨 결함 | 골격 §A-8: URL override 금지, `cleanup.sql` + `@Sql(AFTER_TEST_METHOD)` 패턴. 프로필 "알려진 주의" 에 명시 |
| stage2 병렬 | 두 developer 가 `common-candidates.md` 에 동시에 C-08/09 를 써서 번호 충돌 → admin 이 C-10~13 으로 재번호 | pipeline-core §6: 병렬 웨이브는 C-번호 대역을 프롬프트로 사전 배정 |
| stage2 병렬 | Maven 멀티모듈에서 두 developer 가 각각 `-pl <자기모듈> -am` 으로 common/domain-notice 를 동시 재컴파일 — 이번엔 충돌 없이 통과했으나 `target/classes` 경합 위험 | 관찰 중. 문제 생기면 웨이브 시작 시 오케스트레이터가 `./mvnw -q -pl server/common,server/domain-* install -DskipTests` 후 developer 는 `-am` 없이 || stage2 notice-admin | 통합 테스트의 `(Timestamp) row.get("mod_dt")` 캐스트가 H2 전용 → `-Pmysql` 에서 3/7 error. developer 는 "MySQL 전용 구문 없음" 을 이유로 `-Pmysql` 을 건너뜀 — **SQL 이식성과 테스트 이식성은 별개 축** | 프로필: `queryForObject(sql, LocalDateTime.class)`; reviewer 가 slice IT 를 `-Pmysql` 로 1회 실행. `/stage2` e 항: 게이트에 걸리는 medium 은 같은 단계에서 수정 |
| stage2 notice-admin | 원자성 REQ-020 의 롤백을 목 예외→보상만으로 "증명" — 실제 DB 롤백은 어노테이션 신뢰뿐 | 프로필: 두 번째 INSERT 실제 실패(컬럼 길이 초과) 케이스로 롤백 증명 |
| stage2 도구 | RR 생성 후 본문을 정규식 치환으로 넣다가 백틱이 YAML 을 깨뜨림(`rr.py stats` 전체 실패) | `rr.py new` 에 `--evidence/--description/--fix` 추가, pipeline-core 에 "YAML 문자열 치환 금지" |

## 2026-09-22 — sample2 stage3 (공통화 회차 1)

| 단계 | 현상 | 조치 |
|---|---|---|
| stage3 | 모듈 간 fixture 공유를 `test-jar` 로 하려다 `./mvnw test`(package 전) 리액터에서 test-jar 의존이 `target/test-classes` 디렉터리 전체로 해석 → `DomainNoticeTestApplication` 이 user IT 의 `@SpringBootConfiguration` 으로 잡혀 9건 오류 | 프로필: test-jar 금지, `maven-resources-plugin` 복사(`copy-shared-fixtures`) — 골격이 user/admin pom 에 미리 넣음 |
| stage3 | C-04 `connection-init-sql: SET SESSION group_concat_max_len` 을 H2 MODE=MySQL 이 거부 | 프로필: test 프로파일 `""` 덮기 + test-mysql 재설정 |
| stage3 | 2단계 RR(공용 `MailMessage` 다수 수신자)을 3단계가 흡수 — 공용 변경은 3단계만 가능하므로 자연스러움 | stage3 스킬 §3: 2단계 RR 중 공용 변경 필요분은 3단계가 흡수하고 `/refactor` 는 slice 잔여만 |
| stage3 | 4분류표 74행 중 대체·개선 8건은 증명 테스트 없음(Hikari 풀·ShedLock·세션 타임아웃·logback 등 설정성) | 5단계 특성화 시나리오 입력으로 넘김(레포트 §7) || stage3 검토 | MySQL 세션 변수 테스트가 1024 로 내린 뒤 원복 안 함 → 풀 커넥션 오염(순서 의존). 3단계 이전엔 "올리기만" 해서 무해했던 것이 갱신으로 방향이 생김 | 프로필: `finally` 원복 규칙. RR-0006 |
| stage3 검토 | 4분류표 증명 테스트 ID 72건 중 1건 오기 — reviewer 가 스크립트 전수 대조로 검출 | stage3 reviewer 체크 5 추가. 문서 정합 low 6건은 RR-0007 로 묶음 |
## 2026-09-22 — sample2 /refactor iteration 2 (RR-0002~0007)

| 단계 | 현상 | 조치 |
|---|---|---|
| refactor | 3단계가 공용 `MailMessage` 를 고쳐 RR-0002 는 slice 에서 코드 변경 0(테스트·추적표만) — "공용 변경 RR 은 3단계가 흡수" 규칙이 실제로 동작 | 정상. `/refactor` 6항의 "공용 기반으로 해결" 경로 |
| refactor | 오케스트레이터 지시("`<img src=x>` 만 있는 본문 → 400")가 jsoup 실측(`<img>` 태그는 남음)과 어긋남 → developer 가 지시를 따르지 않고 실측대로 2단 테스트 + C-14 로 보고 | 정상(규약 > 프롬프트). 오케스트레이터는 정제기 동작을 단정하지 말고 "정제 후 빈 본문이면 400" 으로만 지시 |
| refactor | 병렬 3 에이전트(2 developer + common 문서)가 파일 경계를 지켜 충돌 0 — RR-0007 처럼 여러 slice 파일에 걸친 문서 RR 은 오케스트레이터가 **항목을 소유 slice 별로 쪼개 배정** | `/refactor` 5항에 문서 RR 분할 규칙 추가 |
| refactor | reviewer 가 만든 일회성 대조 스크립트를 `tools/check_test_ids.py` 로 편입 — 에이전트가 스크래치에 만든 검증 도구는 재사용 후보 | 규칙: reviewer 보고의 스크립트는 오케스트레이터가 tools/ 편입 여부 판단 || refactor 검토 | RR-0004 처리로 `@Size(min=1)` 을 추가 → `@NotBlank` 와 겹쳐 `title:""` 에 fieldErrors 2건(둘째 문구 오안내) — **계약 강화 목적의 수정이 런타임 동작을 바꿈** | 프로필: 계약 강화는 `@Schema(minLength…)` 문서 수단 먼저; Bean Validation 추가 시 `""`·`"  "`·`null` 세 경계 테스트 필수 |
| refactor 검토 | "GET 3개 401/403 누락" RR 을 처리하면서 같은 계약의 POST/DELETE 401 누락은 그대로 — RR 범위 밖이라도 같은 기준으로 전체를 훑어야 | stage2 §D: 같은 종류 누락은 계약 전체 엔드포인트를 대조 |
| refactor 검토 | `check_test_ids.py` 가 추적표 약어(`SvcT`)·`Test.Nested.method`·`reject*` 를 못 읽어 60건 중 5건만 대조하고 "불일치 0"(공허) | 도구: 범례 2형식 파싱·중첩 경로·접두 와일드카드 지원 → 70/70·87/87. reviewer 는 "인용 토큰 수" 가 문서 인용 수와 비슷한지 먼저 확인 |
| refactor 검토 | RR-0007 을 3 에이전트가 나눠 처리한 뒤 yaml 을 닫지 않음 — 오케스트레이터 누락 | `/refactor` 5항 분할 규칙에 "오케스트레이터가 같은 회차에 닫고 note 기록" 이미 명시. reviewer 체크에 "RR status ↔ 작업 트리" 대조 추가 || refactor 검토 반영 | 지시(`@Size(max)`+`@Schema(minLength=1)`)대로 하니 계약이 `minLength: 0` 으로 회귀 — swagger-core 가 `@Size` 존재 시 `@Schema.minLength` 를 무조건 덮어씀(javap 확인). developer 가 `@Length(max)`(Hibernate) 로 우회 | 프로필에 실측 기록. 오케스트레이터 지시도 라이브러리 동작 단정이었음(재발) |
## 2026-09-22 — sample2 stage4 골격 (pnpm 워크스페이스)

| 단계 | 현상 | 조치 |
|---|---|---|
| stage4 골격 | 36분·329k 토큰·117 tool call. pnpm 12 의 `minimumReleaseAge`·`allowBuilds` 가 설치를 두 번 막음, 최신 메이저가 전부 지정 버전 초과, corepack EPERM, Windows 대소문자 파일명 충돌 | 프로필 "알려진 주의" 에 실측 조합·pnpm 12 규칙 기록 → 다음 골격에서 재발 없음 |
| stage4 골격 | 내 프롬프트의 서버 포트(18080/81)가 틀렸고 에이전트가 yml 실측(18090/91)으로 바로잡음 — 오케스트레이터가 사실을 단정해 지시한 3번째 사례(정제기·swagger·포트) | 규칙: 프롬프트에는 "실측할 파일 경로" 를 주고 값은 단정하지 않는다(pipeline-core §6 developer 프롬프트 규칙) |
| stage4 골격 | auth 계약에 login/me 의 401 응답·문구 미기술 → FE 가 오류 문구를 추정할 수 없어 RR-0008(4→2) | 정상 경로(계약 부족 → RR) |
## 2026-09-22 — sample2 stage4 W1 (notice-admin admin 앱)

| 단계 | 현상 | 조치 |
|---|---|---|
| stage4 notice-admin | 36분·372k 토큰. ftl 분기 21 ↔ 테스트 대응표, 122 tests. 계약 부족 1(관리자 상세 첨부 다운로드 API 없음 → RR-0009 medium) — 2단계가 admin 상세의 첨부 다운로드를 빠뜨린 것을 FE 가 잡음(사용자 앱 API 를 admin 이 못 씀) | 정상 경로. 교훈: slices.yaml 의 apis 가 "첨부 목록" 만 있고 다운로드가 없었음 → stage1 slice-planner 는 첨부 표시가 있는 화면에 다운로드 API 를 자동 포함 |
| stage4 notice-admin | 에디터 TextAlign 이 SafeHtml 에서 `style` 제거로 표시 안 됨(실측) → developer 가 제외하고 F-25 | 프로필: 허용 마크 3자 동일 원칙 + 실측 규칙 |
| stage4 notice-admin | RHF 체크박스 `value="Y"`, zod 4 refine 미평가, msw+jsdom FormData, react-hooks 7 이름 규칙, date input — 실측 5건 | 프로필 "알려진 주의" |
| stage4 병렬 | 두 FE developer 가 `common-candidates.md` frontend 섹션에 F-1x/F-2x 대역으로 충돌 없이 기록 — 대역 배정 규칙 효과 확인 | 정상 || stage4 notice-admin 검토 | 분기→테스트 대응표 21행 중 1행이 요청 파라미터만 검증하고 렌더 단언 없음(대응표는 채워짐) | stage4 §D-0: 행마다 렌더 단언 확인 |
| stage4 notice-admin 검토 | 인라인 오류 표시 + 공통 토스트 이중 알림(`meta.silent` 누락) — 테스트로 안 잡힘 | §D-0 대조 항목 |
| stage4 notice-admin 검토 | 계약이 오류 코드만 싣고 문구가 없어 FE/서버 문구 갈림(007) — "계약만 보고 개발" 원칙의 구멍 | stage2 §B-5: 오류 코드별 문구를 계약 description 에. RR-0010 |
| stage4 notice-admin 검토 | 골격 SafeHtml 이 서버가 허용하는 `style` 을 지워 에디터 정렬 기능을 빼야 했음 — 3자 동일을 골격 시점에 맞추지 않은 결과 | stage4 §A-6 |
## 2026-09-22 — sample2 stage4 W1 (notice user 앱)

| 단계 | 현상 | 조치 |
|---|---|---|
| stage4 notice | developer 가 API 서버 오류(529, 500)로 두 번 중단 → `SendMessage` 재개로 같은 컨텍스트에서 이어 완료(산출물 손실 0). 재개 프롬프트에 "작업 트리 상태를 먼저 확인" 을 넣은 것이 효과 | 규칙(pipeline-core §6): 에이전트가 서버 오류로 끊기면 새 에이전트 대신 **재개**(컨텍스트 보존) + "git status 로 상태 복구 후 이어서" 지시 |
| stage4 notice | 계약 7개로 화면 2개 전부 구현, RR 0 — 2단계 notice 계약이 충분했음(admin 은 다운로드 누락) | — |
| stage4 notice | msw 선등록 우선(`/:id` 가 `/top` 가로챔), user-event 앵커 click 목, 도구의 ` ` 이스케이프 변환 — 실측 3건 | 프로필 "알려진 주의" |
| stage4 notice | 테스트가 실제 결함 1건 발견(react-query `onSuccess` 2번째 인자를 잘못 넘김) | 정상 || stage4 notice 검토 | 분류 change·정렬·페이지 이동이 URL 값만 merge → 입력 중 검색어 유실. AS-IS 는 `form.submit()` 으로 폼 전체 전송 — "스크립트 동작 매핑" 에 **전송 필드 범위**가 빠져 있었음 | 프로필: 매핑표에 전송 필드 범위 열 |
| stage4 notice 검토 | `pnpm test -- --run <경로>` 의 `--` 가 vitest 필터를 무효화(전체 실행) — 프로필·pipeline-core 예시가 틀렸음(F-17 실측 재현) | 모든 pnpm 예시에서 `--` 제거, 프로필에 금지 명시 |
| stage4 notice 검토 | 운영 QueryClient `retry: 1` 이 404 도 재시도 → AS-IS 즉시 오류 화면과 1초 차이 | 프로필: 단건 조회 404 재시도 제외 |
| stage4 notice 검토 | `meta.silent` 누락이 admin(목록)·user(목록) 두 slice 에서 반복 — 상세는 맞고 목록만 빠짐 | §D-0: alert 렌더 컴포넌트의 query 전수 grep |
## 2026-09-22 — sample2 stage5 (domain-notice, 환경 구축)

| 단계 | 현상 | 조치 |
|---|---|---|
| stage5 domain-notice | 31분·277k 토큰·92 tool call: MySQL 8.4 도커 + jar 2개 + Playwright 환경 구축, 시나리오 39(a17/q13/c8+1 미실행) 전부 통과, SQL A 15/15 커버, 4분류표 미증명 9건 중 8건 실측 증명(GROUP_CONCAT 절단·init-sql·세션 TZ·socketTimeout×2·ShedLock 단일 실행·DB_PASSWORD 미설정 exit) | 정상. 환경 스크립트는 다음 slice 가 재사용 |
| stage5 domain-notice | 특성화 테스트를 실 DB 로 돌리려다 `-am` 이 common 테스트를 끌고 와 `tb_user` 를 지움(RR-0013) — 테스트 자체의 데이터 파괴성 | 스킬 §2 실측 (b): slice 패키지 제한 + COUNT 확인. common 테스트 격리는 RR |
| stage5 domain-notice | surefire `-Dtest` 점 표기가 0건 매칭인데 성공으로 지나감 | 스킬 §2 실측 (a) |
| stage5 domain-notice | COLLATION 근거 부족 S-1 이 "검색" 만 다뤘는데 **정렬**(TITLE ORDER BY)도 ai_ci 로 AS-IS BINARY 와 달라짐을 5단계 실측이 발견 → RR-0012 | migration-sql 카탈로그 COLLATION 태그에 "정렬도 영향" 명시 || stage5 notice | 31분·329k 토큰: E2E(Chromium→Vite→jar→MySQL) 58 시나리오 전부 통과, 계약 드리프트 0. 첫 실패 3건은 테스터 기대값 오기(한글 정렬·URL 정규화) | 정상 |
| stage5 notice | 로그인 계정이 seed 어디에도 없어 5단계가 fixture 로 해시를 UPDATE — 골격이 테스트 계정 seed 를 제공했어야 | stage2 골격 §A-8 추가 |
| stage5 notice | `/auth/csrf` 본문 토큰(XOR 마스킹)을 헤더로 보내면 403 — 계약 문구가 실제와 어긋남(RR-0015). 브라우저 경로는 쿠키를 읽어 정상 | 스킬 §2 실측 (c) |
| stage5 notice | 개발 PC 5173 점유 → 포트 변수화로 회피(다른 프로세스 죽이지 않음) | 스킬 §2 실측 (a) || stage5 notice-admin | 90분·471k 토큰·137 tool call(가장 무거운 slice). **등록 화면이 실제 브라우저에서 로드 즉시 크래시**(Tiptap `useEditor` 경합, RR-0017 high, 운영 빌드도 재현) — 4단계 jsdom 단위 테스트 122건이 전부 통과했음에도 | stage4 §C: DOM/타이머 의존 서드파티 컴포넌트는 Chromium 렌더 스모크 게이트. 프로필에 원인·회피 기록 |
| stage5 notice-admin | 서블릿 multipart 한도가 slice 검증(007)보다 먼저 걸려 `COMMON_413` — 2단계 테스트는 서비스 단위라 도달 불가를 못 봄(RR-0018) | stage2: 파일 크기 검증은 서블릿 한도와의 순서를 계약에 명시(어느 코드가 나가는지) |
| stage5 notice-admin | 만료 배치·보상 삭제·실패 메일을 트리거 SIGNAL·cron 덮어쓰기로 실측 — 5단계가 "증명 없음" 항목을 실제로 닫는 방법 확립 | 스킬 §2 실측 (c)(d) |
| stage5 notice-admin | 리치텍스트 3자 정합 실측: 서버는 `style` 보존, user SafeHtml 이 제거 → 관리자가 넣은 정렬이 사용자에겐 안 보임(F-25 실증) | 3단계/골격 후보 유지, stage4 §A-6 |
## 2026-09-22 — sample2 /refactor iteration 3 (stage3 common 묶음)

| 단계 | 현상 | 조치 |
|---|---|---|
| refactor common | 5단계 RR 4건(계정 seed·DB_PASSWORD fail-fast·csrf 마스킹·테스트 데이터 파괴) 이 전부 **골격이 처음부터 갖췄어야 할 것** — 통합 테스트가 골격 결함을 드러냄 | 프로필 "알려진 주의" 에 골격 기본으로 승격(EnvironmentPostProcessor·TestAccountSeeder·csrf 쿠키 우선) |
| refactor common | 3단계가 `apps/shared`(FE 공용)도 수정 — 공용 소유 원칙이 FE 에도 적용됨을 확인 | stage3 스킬: 공용 범위 = `server/common` + `apps/shared` + 루트 설정 |
| refactor common | Boot 바인더가 미해석 플레이스홀더를 리터럴로 넘김(실측) | 프로필 || refactor notice-admin BE | 오류 문구를 계약에 싣는 규칙을 "컴파일 상수 `Msg` 클래스 + 리플렉션 대조" 로 구현해 문구 드리프트를 구조적으로 차단 — 좋은 패턴 | stage2 §B-5 규칙으로 승격 |
| refactor notice-admin BE | 서블릿 multipart 한도가 slice 검증보다 먼저(013→413) — 2단계는 MockMvc 라 못 보고 5단계 실측이 잡음. 계약을 실제대로 정정, yml 상향은 사람 결정(C-15) | 프로필 |
| refactor notice-admin BE | Bash 도구가 `\` 를 한 번 접어 정규식 `\s` 가 깨진 사고 1회 → Edit 도구로 교정 | 메모리 [[bash-heredoc-size-limit]] 와 같은 계열: 백슬래시·특수문자 포함 코드는 Write/Edit || refactor notice-admin FE | RR-0017 원인을 tiptap 소스로 확정(`immediatelyRender` + `scheduleDestroy` 1ms 경합). jsdom 은 재현 불가를 프로브로 실측 → "판별력 없는 테스트는 채택하지 않음" 정직 기록. Chromium 스모크 수정 전 2/2 실패·후 2/2 통과로 판별력 증명 | 프로필 원인·수정·게이트 방법 확정. 공용 후보 F-27(Tree aria-disabled 상속)·F-28(Playwright 공용 설정) |
| refactor iter3 전체 | RR 12건 → 3묶음 순차(3→2→4)로 처리, 전체 게이트 BE 226·FE 314. 3단계 변경(csrf.ts)이 4단계 테스트 1건을 깨뜨림(목 갱신) — 순서 3→2→4 가 맞았음 | `/refactor` 5항 순서 규칙 유효 || refactor iter3 BE 검토 | `EnvironmentPostProcessor` 를 Boot 4 에서 deprecated(forRemoval) 구 패키지로 구현 — 컴파일·jar 실측 모두 성공해 developer 가 못 봄, reviewer 가 javap 로 검출. 배선 테스트도 없어 회귀 시 조용히 꺼짐 | 프로필: SPI 새 패키지·javap 확인·배선 테스트 게이트 |
| refactor iter3 BE 검토 | 오류 문구 상수화가 enum 코드까지만이고 Bean Validation `message=` 5종은 리터럴 3중 복제 — RR-0010 원 결함(문구 갈림)의 잔여 경로 | stage2 §B-5 확장(`Msg.FIELD_*`) || refactor iter3 FE 검토 | 새로 만든 브라우저 스모크가 어떤 typecheck 에도 안 걸림(`paths`→`.mjs` 우회로 선언 파일 없음) — "게이트" 라면서 타입 검사 밖 | 프로필·§C: 스모크 spec typecheck 포함 |
| refactor iter3 FE 검토 | reviewer 가 수정 전 판별력을 검증하려고 worktree 에 node_modules junction → `pnpm exec` 가 실제 repo 링크 94개를 바꿔 놓음(즉시 복구·정직 보고) | 프로필: worktree 는 별도 `pnpm install`(store 공유), junction 금지 |
## 2026-09-22 — sample2 stage6 준비

| 단계 | 현상 | 조치 |
|---|---|---|
| stage6 준비 | semgrep 을 pip 로 설치하니 Scripts 경로가 PATH 밖 → "설치 실패" 로 보임. PATH 추가 후 1.177 정상(9건) | 스킬 §SAST 환경 |
| stage6 준비 | pnpm 워크스페이스라 npm audit 5개 전부 "락파일 없음" 건너뜀 → subtree `run_sast.py` 에 pnpm audit 지원, `summarize_sast.py` 에 npm v6/pnpm advisories 파서 추가 → vitest CWE-22 2건 포착. upstream push `e68d23d` | 마스터 프로젝트 원칙(subtree 버그는 직접 고쳐 push) 적용 3회째 |
| stage6 준비 | 선행 조건(stage5 done)이 refactor 되돌림으로 pending 인 상태에서 사용자 지시 순서대로 stage6 착수 — 보안 점검은 stage5 통과와 독립이라 진행, stage5 r2 는 별도 필요 | `/stage6` 1항: stage5 pending 이면 경고만 하고 진행 가능(재실행 필요 표시) || stage6 scan ×3 | 병렬 3묶음(공용+domain-notice / notice / notice-admin) 합계 21건: Critical/High 0(공용)·High 1(notice 비로그인 다운로드 IDOR)·Medium 4. 가장 큰 발견은 **§12-B "AS-IS 유지" 결정(비로그인 상세·다운로드 permitAll, 공지 상태 무관)이 보안 관점에선 High** — 0단계 결정이 6단계에서 재평가되는 정상 되먹임. 나머지: 확장자 블랙리스트 우회(끝 점·공백), 정제기 `class` 허용, 로그 인젝션, content 길이 상한 없음 | stage0 §12 결정 표에 "보안 재평가 대상" 열을 두어 6단계가 자동 재검토(stage6 스킬 §3) |
| stage6 scan | 에이전트가 exporter 의 확신도 오인(설명 문구에 "확실" 이 섞이면 잘못 판정)을 발견 → subtree 수정·push `85a5d53` | 마스터 프로젝트 원칙 4회째 |
| stage6 scan | AS-IS XSS 필터 → jsoup 대체의 동작 차이(style/class 허용) 가 3단계 4분류표 "대체" 행의 동작 차이로 기록돼 있어 6단계가 바로 sink 로 추적 | 4분류표의 가치 확인 |
## 2026-09-22 — sample2 /refactor iteration 4 (stage6 RR)

| 단계 | 현상 | 조치 |
|---|---|---|
| refactor common | 38분·394k 토큰·160 tool call: 보안 RR 7건(정제기 3자 동일 목록 44태그, 로그 인젝션, Secure 쿠키, 지수 지연, 테스트 자격증명 공용화, vitest 4 이행) 전부 반영, 228→246 tests. vitest 3→4 메이저 이행이 2줄 변경(`vitest/runtime`, `viteEnvironment`)으로 끝남 | 프로필(에이전트가 직접 갱신) |
| refactor common | Bash 도구 heredoc 의 역슬래시 소실로 3회 깨짐(logback·Java·python) — 이번 세션 4번째 | 메모리 규칙 강화: 역슬래시·정규식 포함 편집은 Bash 금지, Edit/Write 만 |
| refactor common | `.gitignore` `!예외` 줄 뒤 주석이 패턴에 포함돼 무효(실측), `MockHttpServletResponse` 는 SameSite 를 헤더에 안 씀 | 프로필 || refactor domain-notice | namespace 간 include 의 중첩 refid 가 포함하는 쪽 namespace 로 풀려 38건 오류 — 같은 id 가 있으면 조용히 별칭이 바뀌는 함정 | migration-sql §2-3 규칙 3건 || refactor notice-admin | 확장자 우회 케이스 7종·매직바이트·파일명 정규화 전부 테스트(84 tests). surefire `-Dtest='패키지.*'` 가 조용히 0건 매칭(EXIT 0) — 이번 세션 2번째 같은 함정(도메인·admin) | 프로필에 명시(슬래시 패턴/클래스명 나열 + Tests run 확인) |
| refactor 병렬 | 두 developer 가 같은 스크래치패드 경로를 써서 패치 스크립트가 덮어써짐 | pipeline-core §6: 임시 파일에 slice 접두어 || refactor notice | RR-0021 지시(비로그인 미게시 첨부 목록 404)가 골격 테스트(200 고정)와 충돌 → developer 가 규약 우선으로 빈 배열 채택. 노출 판별 동등 | 정상. 오케스트레이터가 골격 테스트 전제를 확인 안 한 사례 |
| refactor 병렬 | 두 developer 가 C-16 을 동시에 씀(notice 가 C-17 로 회피) — 오케스트레이터가 프롬프트에 C-번호 대역을 **안 적음**(규칙은 있음) | `/refactor`·`/stage2` 프롬프트 템플릿에 "C-대역: …" 필수 줄 추가 || refactor FE 후속 | 두 slice 를 한 에이전트가 순차 처리(12분) — 계약 후속처럼 작은 변경은 병렬보다 순차 단일 에이전트가 경제적. zod 테스트 29→68(우회 13종). Write 도구 NBSP 저장 문제 2회째 | 프로필 |
| refactor iter4 전체 | 6단계 RR 12 + 파생 1 = 13건, 4묶음(3→2×2→2→4) 순차·부분 병렬, 게이트 BE 285·FE 364·스모크 2. High F-001 은 Mapper(공개용 statement)→서비스(익명 분기)→FE(regId null) 3계층 연쇄 — RR 을 계층별로 쪼갠 6단계 merge 의 판단이 맞았음 | — || refactor iter4 FE 검토 | 화면 문서가 "시그니처 거부 문구가 fieldErrors 로 슬롯 아래 표시" 라 적었으나 서버는 fieldErrors 없이 최상위 message — 계약이 오류 코드별 fieldErrors 유무를 안 적어 developer 가 추정 | stage2 §B-5: fieldErrors 유무 명시. stage4 §D-0: 표시 위치 열 |
| refactor iter4 FE 검토 | "3자 동일" 테스트가 개수(44)·부정 단언뿐 → 태그 교체는 못 잡음. reviewer 가 스크립트로 44/44·18/18 대조 | §D-0: 리터럴 고정 || refactor iter4 BE 검토 | **FAIL(high 2)**: (1) `forward-headers-strategy: native` 가 사내망에서는 XFF 위조를 허용 — RR-0027 옵션 A 가 RR-0028·RR-0023 을 무력화. 단위·MockMvc 테스트가 valve 를 안 거쳐 못 잡음 (2) RR-0023 의 admin 몫(F-306)이 두 developer 사이에서 증발 | 프로필: internal-proxies 고정+RANDOM_PORT 테스트. `/refactor`: 두 slice 걸친 RR 분할, "다른 slice 영향" 절 변환. RR-0035 |
| refactor iter4 BE 검토 | 매직바이트 `contains` 검사가 hwpx/epub·정상 txt 를 거부(테스트가 오탐을 고정) | 프로필: 선두 앵커링·OCF 픽스처 |
| refactor iter4 BE 검토 | 삭제 첨부 연쇄(admin)가 notice 계약 문구("로그인은 상태 무관")를 거짓으로 만듦 — notice-admin 레포트 §8 "확인 필요" 가 인계되지 않음 | `/refactor` 규칙 || refactor iter4 반영 | Boot 4 `@LocalServerPort` 는 `org.springframework.boot.test.web.server`; DOMPurify `ALLOWED_URI_REGEXP` 는 URI_SAFE 밖 모든 속성에 적용(`ADD_URI_SAFE_ATTR` 로 한정); 병렬 developer 편집 중 `-am` 빌드가 남의 과도기 파일을 읽어 컴파일 실패 2회(수 초 뒤 회복) | 프로필 2건. 병렬 -am 은 "재실행으로 해소" 를 규칙에 |
## 2026-09-22 — sample2 stage5 r2 (refactor iter3·4 검증)

| 단계 | 현상 | 조치 |
|---|---|---|
| stage5 r2 domain-notice | 28분: 39→50 시나리오(신규 11·갱신 1·회귀 확인 37), 실패 0. 재실행 규칙(r1/r2 병기·갱신 근거 = RR note)이 잘 동작. 신규 low 2(seed 동시 기동 경쟁, Flyway 가 프로파일 가드보다 먼저) | 스킬 §2 r2 실측 |
| stage5 r2 | `.env.local` 필수화(RR-0029) 후 첫 실행 — 폴백 없음이 실측으로 확인, `APP_PROXY_INTERNAL_IPS` 는 local yml 리터럴로 기동 | — || stage5 r2 notice | 30분: 58→68 시나리오(갱신 11·신규 14·회귀 47), 전부 통과. 초기 실패 5건은 전부 테스터 오류(시나리오 간 조회수 간섭, XFF 신뢰 주소). 서비스 결함 0, RR 1(FE gen 타입 stale) | 스킬 §2: 인메모리 상태·XFF 대조 주소·Playwright reporter || stage5 r2 notice-admin | 33분·408k 토큰: 58→80행(갱신 20·신규 26·회귀 37), **RR-0017 크래시 해소를 dev·lazy·preview 3경로 브라우저 실측**. 새 결함 1: multipart 파일명 NUL 이 Tomcat 파서에서 500(서비스 정규화 미도달, MockMultipartFile 로는 못 봄 → RR-0040) | 프로필: 파서 단계 예외 매핑·실서버 테스트 |
| stage5 r2 전체 | 3 slice r2 합계 198행, 실패 1(RR-0040 low), 서비스 회귀 0. r2 규칙(r1/r2 병기·갱신 근거 = RR note) 이 "기대값 갱신 32건" 을 정직하게 구분 — 5단계 재실행 비용 약 90분 | stage7 착수 조건 충족 |
## 2026-09-22 — sample2 stage7 (QA 자동화)

| 단계 | 현상 | 조치 |
|---|---|---|
| stage7 | 33분·358k 토큰: 생성 테스트 32, 실행 988(도구 집계 + 자체 회귀), **확정 결함 1(Critical → RR-0041)**: 상세 조회 readOnly 트랜잭션이 커넥션을 쥔 채 조회수 `REQUIRES_NEW` 호출 → 동시 요청이 풀 크기에 이르면 교착(10초 지연·조회수 유실, 응답은 200). 5단계·6단계가 못 본 동시성 결함 | QA 단계의 고유 가치 확인. RR-0041 는 /refactor 로 |
| stage7 | subtree 러너가 Maven 멀티모듈·pnpm 워크스페이스를 집계 못 해 295·366건이 0 — 에이전트가 우회 집계로 보고. 오케스트레이터가 도구를 고쳐 재검증(661건 정상 집계) 후 upstream push `375f125` | stage7 스킬: 착수 전 러너 1회 검증, 0 이면 도구부터 수정 |
| stage7 | 5단계 추적표 공백 11행 중 4행을 QA 가 신규 커버(인증 경계·미존재 첨부·관리자 목록·배치 메일 접두어) | 커버리지 공백 추적의 효과 |
## 2026-09-22 — sample2 /refactor iteration 5 (QA RR)

| 단계 | 현상 | 조치 |
|---|---|---|
| refactor RR-0041 | 회차 4 의 `REQUIRES_NEW`(락 점유 축소 목적)가 **커넥션 2배 점유**라는 더 큰 결함을 만듦 — 리팩토링이 새 결함을 낳은 첫 사례. developer 가 수정 전 재현(10.6s·500 5건)→수정 후(202ms·유실 0)로 증명 | 프로필: REQUIRES_NEW 규칙 + 풀 1개 증명법 |
| refactor RR-0041 | `<testsuite tests=…>` 와 `<testcase>` 개수가 `@Nested` 에서 불일치 — 그동안 XML 합계를 tests 속성으로 세어 왔음(수치 신뢰도) | 프로필: testcase 개수 기준 |


## 2026-09-23 — 외부 사례 검토 → 파이프라인 반영

| 대상 | 우리 조치 |
|---|---|
| 게이트 판정 | `tools/gate.py` 신설 + 레포트 `pa-meta` 블록(`templates/report-meta.md`). `gate.py check` 가 stage 별 프로파일(dev/verify/doc)로 6개 훅 실행 |
| 테스트 증명 | `gates[].test_count` 필수 + **0건이면 FAIL**. surefire `-Dtest` 가 0건 매칭인데 EXIT 0 인 함정(이번 세션 2회)을 도구가 막는다 |
| 보고 ↔ 실제 대조 | `repo-consistency` 훅. 레포트가 적은 HEAD·브랜치·dirty·변경 파일을 target_dir 의 git 으로 대조 |
| 미해결 항목 | `open-items.yaml` + `gate.py oi` (kind 5종·status 4종). `blocker`/`high` 는 RR 전환 또는 사람 승인(`accepted`, approved_by·expiry) 없이 단계 종료 불가. 레포트 `result` 에 `done_with_gaps` 추가 |
| 인계 단절 | reviewer 지적에 `confidence`·**`test_hint`** 필드 추가(pipeline-core §7), 5단계 스킬이 `oi list --target 5` 를 먼저 읽고 시나리오로 편입 — "notice-admin §8 확인 필요 미인계", "RR-0023 admin 몫 증발" 의 구조적 원인 |
| 서브에이전트 보고 | `pa-agent-result` JSON 블록(pipeline-core §12)을 12개 에이전트 문서에 의무화. 오케스트레이터는 이 블록만으로 state·`pa-meta` 를 만든다 |
| 증적 위생 | `gate.py` 의 `secret-scan` 훅 + `gate.py secrets <경로>`. 우리는 `.env.local`·테스트 계정·DB 비밀번호를 다루므로 레포트 노출 위험이 실재 |
| 모델 배정 | pipeline-core §13: 상위 모델은 골격·공통화·검증·AS-IS 추적에만, 2회 막히면 그 에이전트만 상향 |
| 미도입 | 단일 오케스트레이터 구조·worktree 사고 실측·비용 대비 효과를 이유로 제외. migration 모드의 화면 증적 비교만 후보로 남김 |

- 도구 검증: 정상/위반 레포트 2건으로 6개 훅 전부 실동작 확인(위반 케이스에서 테스트 0건·HEAD 불일치·브랜치 불일치·OI 미채번·근거 없음·RR 부재·비밀번호 노출 7건 검출, EXIT 1).
- 교훈: 우리 파이프라인의 규칙은 대부분 이미 있었고(공용 파일 금지·정직한 보고·RR 라우팅), **없던 것은 그 규칙을 지켰는지 기계가 확인하는 층**이었다.
  산문 규칙은 에이전트가 성실히 따를 때만 작동하고, 놓친 것은 사람이 레포트를 정독해야 드러났다.

## 2026-09-23 (오후) — 업그레이드 2차: 검증 축·추적 체인·자동 진행

1차(게이트 검증층)에 이어, sample2 최종 채점의 "파이프라인이 스스로 만든 결함 7건" 을 근거로 **무엇을 검사하지 않았는지**를 자산화했다.

| 항목 | 근거(실측) | 조치 |
|---|---|---|
| 검증 축(axis) | 7건 전부가 앞 단계가 보지 못한 축에서만 잡혔다 — 모듈→웨이브(H2 override·Timestamp), jsdom→브라우저(Tiptap), mock→실 파서(multipart NUL), 단위→동시성(REQUIRES_NEW), MockMvc→실 프록시(XFF) | `pipeline-core §14` 신설. slice 의 `traits` → 요구 축 매핑, `gates[].axis` 기록, `gate.py` 의 `coverage-axis` 훅이 대조(닫지도 예약도 안 됐으면 2·4단계 WARN, 해당 축을 닫을 단계에서 FAIL). 축 포함 관계(real-server ⊃ module ⊃ unit)로 중복 기록을 피한다 |
| 추적 체인 | 8단계에서야 "끊긴 추적 11건" 이 드러났다 | `gate.py trace` + `traceability` 훅. 요구사항 ID → 테스트 인용, API slice → 계약 파일 존재를 전수 대조. 2·4단계 WARN, 8단계 FAIL. **실행 즉시 sample2 에서 REQ-025 1건 검출** |
| 회귀 위험 선언 | iteration 4 의 `REQUIRES_NEW` 수정이 iteration 5 에서 더 큰 결함(커넥션 2중 점유 교착)이 됐다 — 리팩토링이 새 결함을 낳은 첫 사례 | `pa-agent-result`·`pa-meta` 에 `risk_surface[]`(무엇을 깨뜨릴 수 있나 / 어느 축 / 무엇으로 덮었나). `/refactor` 11항에서 필수, `covered_by: 미검증` 이면 확인 필요 항목으로 채번 |
| 비용 계측 | 단계별 소요·토큰이 레포트 산문에만 흩어져 회차 비교가 안 됐다 | `pa-meta.cost{duration_min, tool_calls, tokens_k}` + `cost-record` 훅(누락은 경고) |
| 자동 진행 | 게이트 판정이 기계화되자 단계 전환마다 사람이 판단을 대신할 이유가 사라졌다 | `/run [--to N] [--slice] [--max] [--dry]` 신설. 기존 `/stageN` 절차를 그대로 호출하는 얇은 진행자. 승인 지점·FAIL·blocker open item·재작업 2회 초과에서 멈춘다 |
| 다음 샘플 | 두 샘플 모두 slice 3개 — 규모 부하를 한 번도 받지 않았다 | `docs/samples/sample3-plan.md`: slice 12~20 규모 축 기획(가설 6개·측정 지표 7종·규모에서만 드러나는 함정), 대안으로 `mode: brownfield` 설계 |

- sample2 `slices.yaml` 에 traits 를 소급 부여: domain-notice[transaction], notice[counter·auth·file-upload], notice-admin[file-upload·rich-text·batch·auth]. 전부 실측 결함이 난 축과 일치한다.
- 도구 검증: 2단계 레포트에서 browser·real-db·real-server 공백을 WARN 으로, 같은 내용을 5단계로 바꾸면 FAIL 로 판정(의도대로). `trace` 는 실제 프로젝트에서 끊김 1건 검출.
- 남은 것: `/run` 은 아직 실전에서 돌려 보지 않았다. sample3 첫 회차가 `/run --dry` → `/run` 의 첫 실측이 된다.

## 2026-09-23 (오후) — sample3 stage0 (규모 축 첫 회차) + 게이트 층 결함 3건

세 번째 샘플(그룹웨어 전자결재·근태·인사, greenfield, 입력 5문서 33KB) 착수. **게이트 층을 실제 파이프라인에 처음 걸어 본 회차다.**

| 구분 | 현상 | 조치 |
|---|---|---|
| stage0 결과 | 요구 82·화면 42·테이블 39·API 후보 141. §11 **51건**(blocker 2·high 11). 심은 함정 12/12 전부 포착 | 방법론 유효 |
| stage0 확장 | 에이전트가 템플릿에 없는 **§13 공유 지점 15건·§14 순서 의존 17건·§15 검증 축**을 스스로 추가 — 규모에서는 업무별 세로 목록만으로 공유 지점을 못 찾는다는 프롬프트 지시를 따른 것 | `templates/PROJECT_BRIEF.md`·`stage0-ingest` 에 §13~§15 를 정식 절로 승격 검토(다음 회차) |
| **함정보다 큰 것** | 심은 12건보다 **심지 않았는데 나온 39건**이 더 치명적이었다. blocker 2건(지출결의가 1차 범위인데 요구사항·화면·테이블 전무 / 직책 코드 없어 결재선 자동구성 불가)이 모두 후자 | 채점 기준을 "심은 함정 탐지율" 에서 **문서 교차 대조 건수**로 옮긴다 (`docs/samples/sample3-traps.md`) |
| **게이트 G-1** | `open_items[].id` 를 필수로 검사하는데 `pipeline-core §12` 는 "서브에이전트는 id 없이 보고, 채번은 오케스트레이터" 다. stage0 은 에이전트가 레포트까지 쓰므로 채번 전에는 **항상 FAIL** | 51건을 `oi new` 로 51번 부르는 것은 규모에서 불가능 → **`gate.py oi import --report <경로> --write` 신설**: pa-meta 의 open_items 를 일괄 채번하고 레포트에 id 를 써넣는다 |
| **게이트 G-2** | `if not it.get("target_stage")` 가 **`target_stage: 0`(사람 결정)을 누락으로 판정**(0 이 falsy) → 13건이 전부 허위 FAIL | `is None or == ""` 로 수정 |
| **게이트 G-3** | high 이상 open item 에 RR 전환·사람 승인을 요구했는데, 0·1단계에는 **고칠 코드가 없어 RR 을 만들 수 없다.** 구조적으로 통과 불가였다 | RR 전환 요구를 `kind in (unverified, risk)` **이고 stage ≥ 2** 일 때로 한정. `decision`·`evidence_gap`·`deferred` 는 `target_stage` 예약만 있으면 WARN 으로 통과 |
| 에이전트의 정직성 | 도구를 통과시키려 임의 채번하거나 `target_stage` 를 1 로 올리지 않고, FAIL 원인 3건을 코드 라인까지 지목해 보고했다(`deviations`) | `pa-agent-result.deviations` 의 가치 확인 — 이 칸이 없었으면 도구 버그가 "에이전트 실수" 로 묻혔다 |
| 집계 불일치 | 프롬프트가 화면 "SCR-001~056", 테이블 "33종" 이라 안내했으나 실측은 화면 42(결번 5곳)·테이블 39 | 오케스트레이터가 프롬프트에 **수치를 단정하지 않는다**(pipeline-core §6-4 의 "사실을 단정해 적지 않는다" 가 수치에도 적용됨) |
| 비용 | stage0 16분·tool call 15·135k 토큰 (3 slice 샘플의 stage0 과 비슷) | 규모가 커져도 0단계 비용은 문서량에 비례할 뿐 slice 수와 무관 |

교훈: **게이트 층은 그것을 처음 통과시켜 보는 회차에 반드시 깨진다.** 세 결함 모두 "규칙은 맞지만 그 규칙이 적용될 수 없는 단계가 있다" 는 형태였다.
도구를 만들 때 검증한 것은 2·5단계 레포트였고, 0단계(코드 없음·에이전트가 레포트 작성)는 검증하지 않았다.

## 2026-09-23 (오후) — sample3 stage1 + `/run --dry` 첫 실측

| 구분 | 현상 | 조치 |
|---|---|---|
| stage1 결과 | **slice 21개**(1차 18·2차 3), **웨이브 7단**. 테이블 39/39·화면 42/42·API 141/141 전수 배정(중복 소유 0), 요구 80/82. B항 함정 8/8 | 목표 12~20 을 1개 초과했으나 줄일 후보 3개가 모두 "공유 지점 분리" 원칙과 충돌해 유지 — 판단 근거를 레포트에 남겼다 |
| **규모의 첫 비용** | 웨이브 7단 중 **w2·w4 가 slice 1개** (`domain-employee`, `common-authz`) → `max_parallel 3` 이 두 번 놀게 된다. 총 배치 9회. 사슬: 기준정보→인증→권한→결재→업무 4단 구조 | 억지로 줄이지 않고 확인 필요 항목(OI-0054, target 2)으로 올렸다. 기준정보 DDL+seed 를 골격 baseline 으로 올리는 안을 2단계가 판단한다 |
| 공유 지점 처리 | S-1(결재)·S-7(권한)·S-14(사원·부서 2분할)·S-12(배치)는 독립 slice. S-5(엑셀)·S-10(진행표시)·S-13(공통UI)은 §2.5 예외로 공통 후보(C-01~C-03). S-8+S-9 는 API 1~3개라 `common-audit` 하나로 합침 | §2.5("소비자 1개면 분리하지 않는다")가 규모에서는 "API 수가 적으면 합친다" 로도 쓰였다 — 스킬에 반영 검토 |
| 지출결의 | 빈 slice 를 만들지 않고 `unassigned` 에 사유를 남겼다. 근거: 요구ID·화면·테이블·API 가 전부 0 이고 금액 규칙 자체가 모순(O-03) → 빈 slice 는 추측 하드코딩을 유발한다 | 판단 타당. `approval-engine` 에 "문서 종류를 데이터로 추가" 설계 요구를 실었다 |
| trait 확장 | 에이전트가 `pii: [real-db, security-static]` 를 `config` 에 추가(stage1-slicing §4-1 이 명시한 확장 경로). `rich-text`/`sanitizer` 는 O-40 미결이라 **아무 slice 에도 붙이지 않았다** | 근거 없는 축 요구를 만들지 않은 판단이 맞다. 축 요구 집계: real-db 15·concurrency 8·real-server 7·browser 3·security-static 3 slice |
| **게이트 G-1 재발** | stage1 도 같은 이유(OI 미채번)로 FAIL. 두 단계 연속이면 규칙이 아니라 도구 문제다 | `oi import` 로 9건 일괄 채번 후 통과. **에이전트가 레포트를 쓰는 단계에서는 오케스트레이터의 채번이 필수 절차**임을 `/stageN` 완료 처리에 못박았다 |
| **`/run --dry` 가 두 번 깨졌다** | 계획 계산을 애드혹 python 스크립트로 했더니 (1) cp949 인코딩 (2) 잘못된 조건식 문법으로 실패 | **`tools/gate.py plan` 신설** — 선행조건·웨이브·축 요구·멈춤 조건을 도구가 한 곳에서 계산하고 `--format json` 을 준다. `run.md` 는 "직접 계산하지 말고 plan 을 호출" 로 고쳤다 |
| `/run --dry` 결과 | 판정 **멈춤** — `slices.yaml approved=false`. 계획은 4단계(`/stage2 scaffold` → `/stage2 all` → `/stage3` → `/stage4 all`), `/stage5` 는 `--max 4` 초과로 다음 `/run` 으로 미룸 | 의도대로 동작. 승인 게이트에서 멈추고 사람이 할 일과 이어갈 명령을 제시했다 |

교훈: **오케스트레이터 명령에 계산 로직을 산문으로 적으면 매번 재구현된다.** 판정·계획·집계는 도구로 내리고 명령은 그것을 호출해야 한다.
`/run` 의 가치는 자동 진행 자체보다 **"지금 무엇을 어떤 순서로 돌릴 수 있고 어디서 멈추는가" 를 한 번에 보여주는 것**에 있었다 — `--dry` 만으로도 유용하다.

## 2026-09-24 — sample3 stage2 골격 + 웨이브1 배치A (규모 축 첫 개발 회차)

slice 21개 중 골격 + 3 slice(`common-code`·`common-holiday`·`domain-org`, `common-batch` 는 골격 흡수로 skipped).
최종 게이트 **304 tests / 실패 0**, target 커밋 `65456b8`(골격 145파일)·`3b035ce`(배치A 118파일).
목적은 slice 코드가 아니라 **규모에서 먼저 깨지는 규칙**을 찾는 것이었고, 9건이 나왔다.

### A. 규모·병렬에서만 드러난 결함 (sample2 3 slice·동시 2 에서는 나올 수 없던 것)

| 현상 | 조치 |
|---|---|
| **Flyway 분 단위 파일명이 충돌** — 동시 3개가 같은 분에 파일을 만들어 `Found more than one migration with version` → `db/migration` 공유 때문에 **무관한 모듈까지 컨텍스트 생성이 실패**해 3 slice 게이트가 동시에 멈췄다 | `pipeline-core §6-4`: 버전에 **slice 고유 번호**(`V<대역>_<slice번호>_<yyMMddHHmmss>__`) + 웨이브 전후 중복 검사 명령. 프로필 주의 |
| **`copy-resources` 가 삭제를 전파하지 않는다** — rename 후에도 옛 복사본이 충돌을 남긴다. 게다가 복사 경로가 **2개**(app 의 운영 classpath + 부모의 test classpath)였고, 내가 test 만 고쳐 첫 시도가 실패했다 | 골격 POM `prune-stale-migrations`(maven-clean-plugin, `generate-resources`, 양쪽 경로). 프로필 주의 |
| **DDL 대문자 / Mapper 소문자 규약이 Linux MySQL 에서 전 쿼리를 실패시킨다**(`lower_case_table_names=0`) — H2 의 `CASE_INSENSITIVE_IDENTIFIERS` 가 가려 단위·모듈 테스트로는 절대 안 드러난다 | `CONVENTIONS §4` **소문자 통일**. **컬럼은 대소문자 무구분이라 무해함을 함께 명시**(구분을 안 적으면 다음 slice 가 또 헷갈린다) |
| **FK 제약명이 스키마 전역 유일** — 부모 기준 이름(`fk_tb_code_group`)을 뒤 slice 가 같은 이름으로 쓰면 migrate 전체 실패. slice 단독 테스트는 자기 대역만 적용해 못 본다 | 자식 기준 명명 규약(`fk_<자식>__<컬럼>`) 신설 |
| **공용 메뉴 설정이 비어 쓰기 API 전체 403** — slice 는 공용 파일을 고칠 수 없어 각자 공통 후보로 올렸다 | 오케스트레이터가 일괄 반영(C-10·20·30). 프로필 주의 |

### B. 게이트 층이 규칙 위반 자체를 잡은 사례

- **`risk_surface: covered_by 미검증` 인데 확인 필요 항목 미채번**을 reviewer 가 2 slice 에서 지적(CC-05·ORG-05).
  전날 만든 `pipeline-core §12` 규칙이 하루 만에 실제로 2건을 건졌다 — 그대로 두면 "notice-admin §8" 유형으로 증발할 항목이었다.
- reviewer 가 **레포트 문구의 거짓**을 잡았다: "grep 으로 옛 규약 0건" 이 실제 1건(Git Bash 에 백슬래시 경로를 줘 false-negative),
  "REQ-003 DisplayName 9건" 이 실측 19건, "값 목록 4곳→1곳" 이 실제 3종만 단일화.
  **내가 그 문구를 LESSONS 로 옮기면 틀린 근거가 남는다** — reviewer 가 그 점까지 지적해 레포트를 정정했다.

### C. 판별력(§14-5) 이 실제로 작동하고, 규격의 빈칸이 드러났다

- `common-holiday`: **mutation 2건 주입**으로 "새 테스트는 잡고 옛 단언은 못 잡는다" 를 실측. 되돌림까지 확인.
- `domain-org`: **수정 전 재현** — 테스트만 먼저 넣어 `96 tests / 실패 5`(지적별로 정확히 1~2건) → 수정 후 `97 / 0`.
- 그런데 판별력 증거가 **레포트 산문에만** 남아 있었다 → reviewer 제안으로 **`pa-meta.discrimination[]`** 신설
  (`target`·`method`·**`scope`**·`failures`·`evidence`(XML 사본)·`restored`). `gates[]` 에 싣지 않는다 — `gate-proof` 가 "실패를 통과로 기재" 로 읽는다.
- **첫 사용에서 두 번 더 깨졌다**:
  1. mutation 을 **한 클래스**에서만 돌리고 "기존 테스트 전부 통과" 로 일반화 → 같은 모듈 통합 테스트는 이미 그 변이를 잡고 있었다.
     → 규격에 **`scope` 필수**, "기준은 모듈 전체 1회 실행" 을 명문화.
  2. "수정 전에는 단언이 **컴파일조차 안 된다**" 는 형태를 `failures: 1` 로 적어 정수 검사를 통과시켰다(자리끼움).
     → `method: absent_pre_fix` 추가, 이때는 `failures: 0` 을 허용하되 **`harm_evidence`(해악 실재 증명)와 `mutation`(수정 후 주입)을 둘 다 의무화**.
     재현 불가가 판별력 면제로 쓰이면 규격이 숫자를 부른다.

### D. 오케스트레이터(나)가 틀린 것

| 내가 한 것 | 결과 |
|---|---|
| 프롬프트에 `slices.yaml → tobe_module` 필드가 있다고 단정 | 그 필드는 없었다(1단계가 근거 없어 생략). §6-4 "사실을 단정해 적지 않는다" 를 내가 어겼다 |
| 화면 "SCR-001~056", 테이블 "33종" 으로 안내 | 실측 화면 42(결번 5곳)·테이블 39. **수치도 단정 금지 대상**이다 |
| RR-0001 수정에서 test classpath 만 정리 | app 의 운영 classpath 에 옛 복사본이 남아 `gw-app` 10건이 깨졌다. 내 변경도 전체 테스트로만 검증된다 |
| ORG-04 처방에 "적용기 호출 또는 폴백" 을 제시 | developer 가 적용기 호출을 거부했다 — **읽기 경로에서 쓰면 조회-후-INSERT 경합(ORG-11)을 읽기 트래픽만큼 재현**시킨다. 내 지시의 절반이 위험했다 |
| ORG-12 처방에 "CREATE 면 CREATE 유지" 만 지시 | 그대로면 `create→close`(같은 날)에서 **폐지가 조용히 무시**된다. developer 가 409 로 거부하는 해법을 찾았다 |

교훈: **오케스트레이터의 지시는 developer 가 검증할 대상이다.** `deviations` 칸이 그 통로였고, 이번 회차에 4건이 그 칸에서 나왔다.

### E. 비용 (규모 비교 근거)

| 단계 | 소요 | tool call |
|---|---|---|
| 골격 | 48분 | 68 |
| 배치A developer 3 (병렬) | 30·45·41분 | 56·60·52 |
| reviewer 3 (병렬) | 22·22·26분 | 24·16·17 |
| 재작업 2 + 재검토 2 | 20·29·18·26분 | 31·47·13·18 |
| 재작업 3회차 + 최종 재검토 | 28·34분 | 46·18 |

slice 3개에 **재작업 3회·재검토 3회**가 들었다. `domain-org` 혼자 developer 3회(41+29+28분)·reviewer 3회(26+26+34분).
시간축(시점 조회·예약·적용기)을 가진 slice 는 계약이 12개 후행 slice 의 전제라 회차가 늘어난다 — **규모에서는 이런 slice 를 먼저 배치하는 것이 맞다**(웨이브1에 둔 판단은 옳았다).

## 2026-09-24 (오후) — sample3 stage3 공통화 회차 1 (공통 후보 27건 흡수)

3 slice(304 tests)를 만든 뒤 3단계로 전환했다. 근거는 숫자였다 — **3 slice 에서 공통 후보가 27건** 쌓였고,
21 slice 를 다 만든 뒤 한 번에 흡수하는 것은 불가능하다는 것이 그 수로 드러났다. 결과 **320 tests(감소 0)**, RR 3/4 done.

### 반영한 공용 결함 5건 (전부 "21 slice 에 복제될 것" 이었다)

| 결함 | 왜 공통화가 잡아야 했나 |
|---|---|
| 경합 시 PK 위반이 `COMMON_500` | 공용 핸들러 결함이라 **모든 "검사 후 삽입"** 에 복제된다 |
| 조직 개편 도래분 자동 반영 없음 | slice 가 cron 키를 등록할 수 없어 수동 엔드포인트만 있었다 |
| `exists`/`existsPhysical` 양방향 비대칭 | 신설 미반영은 `exists=true`/`physical=false`, **폐지 미반영은 반대**. 저장 경로가 한쪽만 보면 틀린다 |
| `updateSnapshot` 의 CLOSE 가드 | **cron 을 등록한 회차가 만든 구멍** — 같은 회차에 닫았다 |
| `holidaysBetween` javadoc | 2단계에서 한 번 고쳤는데 또 어긋났다(3번째) |

### 이번 회차의 핵심 교훈 — 기계 검사가 규약을 약화시킬 수 있다

"규약 문장만으로는 막히지 않는다" 는 실측이 있어 기계 검사를 만들게 했다. 그런데 **그 검사가 정당한 코드를 오검출했다**:
`server/app` 에 사는 slice 6개(같은 회차가 `§3-2` 에 그렇게 배정했다)의 자기 Mapper import 를 위반으로 잡았다.
slice 는 `CONVENTIONS.md` 를 고칠 수 없으니 스스로 예외도 못 낸다.

reviewer 판정: **오검출하는 검사는 우회 습관을 만들고, 그러면 나머지 4개 규칙의 신뢰까지 무너진다** → high.
수정은 판정 소스를 디렉토리 이름 → `package` 선언으로 바꾸는 것이었고, developer 가 **오검출을 프로브로 먼저 재현**한 뒤 고쳤다.

교훈: **기계 검사를 만들 때는 "진짜 위반을 잡는가" 와 "정당한 코드를 통과시키는가" 를 양방향으로 증명해야 한다.**
전자만 증명하면 규약을 강제하려던 장치가 규약 전체를 무력화한다.

### 판별력 규격이 또 깨졌고, 도구가 그것을 잡게 했다

- 2회차 `discrimination[].scope` 3건이 "모듈 전체 1회 실행" 인데 실제는 **단일 클래스**였다(XML `tests=4/5`, 모듈 전체는 21).
  §14-6 이 `scope` 를 필수로 만든 이유가 정확히 그 오보인데 같은 형태가 재발했다.
- → **`gate.py` 가 `evidence` 의 XML 을 직접 읽어 대조하게 했다**: 선언한 `failures` ≠ XML 실측이면 FAIL,
  `scope` 에 "전체" 라고 적혔는데 XML 테스트 수가 그 숫자와 다르면 WARN.
  도입 직후 **1회차 기록 4건에서 같은 오보를 즉시 검출**했다(13~28건인데 "모듈 전체" 로 적힘).
- 교훈: **자기 보고를 검사하는 필드를 만들면 그 필드도 자기 보고다.** 기계가 원본(XML)을 읽어야 닫힌다.

### 지적에 없던 사실 — 게이트 명령이 애초에 동작하지 않았다

`CONVENTIONS §14` 의 developer 게이트 `./mvnw -B -pl server/<모듈> test` 는 규약 검사 미실행 이전에
**`Could not find artifact gw-common` 으로 빌드가 서지 않는다**(`-am` 누락, `~/.m2` 에 형제 모듈 jar 가 없다).
내가 developer 프롬프트에는 `-am` 을 넣어 줬기 때문에 두 회차 동안 아무도 몰랐다 —
**프롬프트가 규약 문서의 결함을 가려 준 형태다.** 규약만 보고 착수하는 다음 slice 가 처음 만났을 것이다.

### 남은 위험 (열린 채 넘김)

- `-am` 을 넣은 새 게이트가 **병렬 웨이브에서 전체 리액터를 돌린다** → `pipeline-core §6-6`("자기 slice 까지만") 과 충돌.
  웨이브2 착수 전 오케스트레이터 결정 사항.
- 새 기계 검사 2개의 **오검출 표면이 "아직 존재하지 않는 코드" 에만 있어** 현재 테스트로는 영원히 초록이다(reviewer 지적).
- 운영 배치를 켰는데(`app.schedule.enabled: true`) **실패가 로그 외에 관측되지 않는다.** `lockAtMostFor=PT5M` 의 근거도 소요시간이 아니다.

## 2026-09-24 (저녁) — real-db 축 실측 (RR-0003 종료, Docker 기동)

Docker Desktop 을 켜고 `-Pmysql`(mysql:8.4 testcontainers)로 3 slice + 골격을 돌렸다. **299건 전부 통과, 실패 0.**
(domain-org 100 · common-code 66 · common-holiday 65 · 골격 68)

### 이 실행이 증명한 것 — 게이트 층의 값이 여기서 나왔다

| 확인 | 안 고쳤다면 |
|---|---|
| **소문자 식별자 통일**(RR-0002/ORG-06) | Linux MySQL(`lower_case_table_names=0`)에서 **전 쿼리가 `table doesn't exist`** — 299건이 통째로 실패했을 것이다 |
| **FK 제약명 자식 기준**(CC-02) | 스키마 전역 유일 제약 충돌로 migrate 전체 실패 |
| `updateSnapshot` 의 `CASE` 가드(OI-0107) | 3단계가 넣은 CLOSE 가드가 MySQL 에서 작동 |
| 시점 조회 SQL(`MIN`+상관 서브쿼리·`DATE` 비교·`CHAR(1)` 패딩) | reviewer 가 3회차에 걸쳐 잡은 시간축 결함 6건의 수정이 **H2 착시가 아니었다** |
| seed `ON DUPLICATE KEY UPDATE`·utf8mb4 한글 | — |

**두 결함(식별자 대소문자·FK 제약명)은 H2 로는 원리적으로 드러나지 않는다.** `real-db` 축을 축으로 세우고
"닫히지 않았으면 예약" 규칙을 만든 것이 정확히 이 지점을 겨냥한 것이었고, 실측이 그 판단을 확인했다.

### 환경 실측 (다음 회차의 조건)

- `mysql:8.4` 이미지가 이미 캐시돼 있어 pull 불필요 — 없으면 1.12GB 다운로드가 선행된다
- **RAM 여유 0.3GB 에서도 돌았다.** 컨테이너가 테스트 클래스마다 뜨고 내려가는 구조라 순간 점유가 낮다.
  다만 Docker Desktop 자체가 WSL2 로 2.1GB(`vmmemWSL`)를 먹으므로 **게임·브라우저를 닫아야 여유가 생긴다**(실측: MapleStory 1.5GB)
- slice 별 순차 실행(`-pl server/<slice> -am test -Pmysql`)이 안전하다. 전체를 한 번에 돌리면 컨테이너가 겹친다
- `-o`(오프라인)를 붙이면 사내망·느린 네트워크에서 Maven 메타데이터 조회를 건너뛴다
- Docker Desktop 기동은 `Start-Process` 로 되지만 데몬 준비까지 **40~60초** 걸린다. `docker info` 로 폴링해야 한다
  (`com.docker.service` 는 Stopped 로 보여도 데몬은 뜬다 — 서비스 상태로 판단하면 틀린다)

### 남은 미검증 (이 축으로도 닫히지 않는 것)

- **cron 실제 트리거·ShedLock 다중 인스턴스 중복 방지**(OI-0115) — 스케줄 시각을 발생시켜야 한다
- **부하·동시성**(OI-0098·0121) — 부서 500·이력 10만행, `lockAtMostFor` 초과 시나리오
- 배치 실패의 관측 경로(OI-0123)

열린 RR **0건**이 됐다(4/4 done). 확인 필요 항목 99건은 전부 닫을 단계가 예약돼 있다.

## 2026-09-26 — 웨이브1 배치B 검토 (common-file): 축을 닫았다는 주장의 검증

`common-file` 은 `real-server` 축을 **처음으로 실제로 닫은** slice 다. reviewer 가 그 주장을 사본 XML 과
소스로 대조해 **성립을 확인**했다(진짜 `RANDOM_PORT`+`HttpClient` 경로, 413·400 에서 DB 0행·NAS 0건까지 단언,
M1 82건/1실패 — `FileControllerTest` 15건은 전부 통과). 축을 늘린 판단 자체는 값을 냈다.
그런데 **닫는 방식에서 네 가지 새 형태의 결함**이 나왔다. 전부 일반화된다.

### 1. 축을 닫을 때 "거부 방향" 만 닫고 "허용 방향" 을 빠뜨린다

XFF 위조가 무시되는 것은 실측했다. 그런데 **신뢰 프록시에서 온 XFF 가 실제로 반영되는가** 는
repo 전체에 단언이 없다. 이쪽이 REQ 의 본래 요구(이력 IP)다.
`GW_PROXY_INTERNAL_IPS` 가 실제 프록시를 빠뜨리면 **모든 이력 IP 가 LB 주소**가 되는데
어떤 게이트도 잡지 못한다 — 보안 설정은 **막는 것**과 **통과시키는 것**이 다른 테스트다.
→ §14 에 "축을 닫을 때 양방향"을 규칙으로 넣는다.

### 2. 테스트가 운영 설정값을 교체하면 그 축은 운영 값을 검증하지 않는다

`application-test.yml` 이 `internal-proxies` 를 전용 값으로 바꿔 놓고 OI-0062(운영 설정 미검증)를
자기 실측으로 `resolved` 처리했다. **그 항목의 `evidence` 가 가리킨 것은 운영 `application.yml` 이었다.**
→ OI 를 닫을 때 **`evidence` 가 지목한 대상을 테스트가 실제로 덮었는지** 대조한다.
남의 slice 소유 항목을 자기 실측으로 닫는 것은 더 위험하다 — 범위를 좁게 읽는다.

### 3. 계약의 오류 응답 전수 대조가 401 만 세고 403 을 못 셌다

5개 엔드포인트 중 4개에는 403 이 있고 `POST` 에만 없었다. 코드는 403 을 낼 수 있다.
developer 의 자체 점검 절에 "401 을 5개 전부 넣었다" 고 적혀 있었다 — **세는 대상이 빠지면 전수 점검이 아니다.**
→ `ErrorCode` 의 `HttpStatus` 집합 ↔ OpenAPI `responses` 를 기계 대조하는 것이 옳은 형태다(gate.py 후보).

### 4. 주석이 존재하지 않는 흐름을 전제한다

Migration 주석이 "임시 식별자로 올린 뒤 문서 저장 시점에 REF_ID 를 확정" 을 설계 근거로 적었는데
**재지정 연산이 서비스·Mapper·계약 어디에도 없다.** 주석은 검증받지 않으므로 거짓이 오래 살고,
그 주석을 근거로 컬럼 제약을 느슨하게 한(FK 없음) 결정만 남는다.
→ 코드 주석이 **다른 계층의 존재를 전제**하면 그 계층을 grep 으로 확인한다.

### 5. reviewer 의 fix 안도 위험을 전환할 수 있다

CF-04 의 권고("타인 활성 첨부가 있으면 `canAttach`=DENY")를 그대로 반영하면
공격자가 **1건만** 올려도 기안자가 업로드 불가가 된다 — 5건이 필요한 현 상태보다 **더 값싼 가용성 공격**이다.
내가 낸 처방이 반쯤 틀렸던 사례(ORG-04·ORG-12)와 같은 형태가 **검토 쪽에서** 나왔다.
→ `fix` 는 누가 냈든 반영 전에 `risk_surface` 를 다시 계산한다. **지적의 severity 는 믿고, 처방은 검증한다.**
  이번에는 읽기 경로를 "업로더 본인 것만" 으로 바꾸는 쪽을 택했다 — 같은 지적을 해소하면서
  CF-07(`REG_ID IS NULL` 행 무단 다운로드)·CF-14(존재 오라클)까지 함께 닫히고 가용성은 보존된다.

### 부수 확인

- `UploadContentInspector` 의 HTML 선두 판정이 **주석을 건너뛰지 않았다.** 프로필 §알려진 주의가
  "BOM·공백·주석 뒤 선두" 라고 이미 경고한 항목인데 구현이 두 개만 반영했다 — **경고문의 열거를 체크리스트로 쓰지 않으면 새어 나간다.**
- MySQL 의 동일 유니크 키 동시 INSERT 는 즉시 중복키가 아니라 **행 잠금 대기**다. 타임아웃되면
  `CannotAcquireLockException` 이라 409 로 전환하는 분기를 지나치지 않는다. **H2 는 즉시 실패해 이 분기를 볼 수 없다.**

### 6. 요구서를 닫을 때 **요구서 자신이 적은 종료 조건**과 대조하지 않았다 (내 오판)

`RR-0005`(common-audit real-db 미검증)의 `suggested_fix` 는 종료 조건을 명시적으로 적어 뒀다 —
"`-Pmysql` **76건** 통과, 특히 `AuditLogMapperTest#deleteOlderThanIsExclusiveAtBoundary` /
`#deleteOlderThanRespectsLimit` 가 MySQL 에서 통과해야 한다".
나는 `AuditTransactionIntegrationTest` **8건**만 돌리고 `done` 으로 닫았다.
reviewer 가 **surefire XML 의 `mtime` 과 `<property>spring.profiles.active`** 를 읽어
"MySQL 실행은 1개 클래스뿐, 나머지 9개는 전날 H2" 를 실측해 잡아냈다.

- 재실행하니 **76건 전부 MySQL 에서 통과**했다(`AuditLogMapperTest` 소요 H2 2.6초 → MySQL 16.4초).
  결과가 같았어도 **닫을 때 증거가 없었다는 사실은 달라지지 않는다.**
- `gate.py` 의 `coverage-axis` 는 OI 의 **상태만** 보므로 이 부분 종료를 잡지 못한다 — **도구 공백**이다.
- 교훈: **RR 을 `done` 으로 바꿀 때 `suggested_fix` 의 종료 조건을 한 줄씩 증거와 대조한다.**
  `resolution_note` 에는 "무엇을 돌렸는가" 가 아니라 **"종료 조건 각 항이 어떤 증거로 충족됐는가"** 를 적는다.
  기계화 후보: `resolution_note` 가 `suggested_fix` 에 등장하는 테스트 이름을 전부 포함하는지 검사.
- 검증 방법도 교훈이다 — **surefire XML 의 `mtime` + 활성 프로파일**이 "그 축을 정말 그때 돌렸는가" 의 1차 증거다.
  reviewer 체크리스트에 넣을 값이 있다.

### 7. 새 기계 검사는 **프로브 없이는 통과가 무의미하다** (앞 회차 위험이 현실로)

앞 회차에서 "새 기계 검사 2개의 오검출 표면이 아직 존재하지 않는 코드에만 있어 현재 테스트로는 영원히 초록이다" 를
열린 위험으로 남겼다. 이번에 `SharedPortUsageConventionTest` 에 C-52 전파 검사를 추가하고 **프로브를 넣어 보니
규칙의 절반이 동작하지 않았다.**

- 1차 구현은 감사 규칙을 `!text.contains("@Transactional")`(**파일 단위**)로 봤다.
  프로브 클래스가 다른 메서드에 `@Transactional` 을 갖고 있어 **트랜잭션 없는 감사 호출을 통과시켰다.**
  개인정보 규칙(메서드 창 단위)만 걸렸다. → 클래스 레벨 선언만 예외로 두고 **메서드 창**으로 좁혀 둘 다 검출됐다.
- 즉 **통과는 규칙이 맞다는 증거가 아니다.** 프로브 → 검출 확인 → 프로브 제거 → 재통과, 그리고 그 실패 XML 을
  증거로 남기는 것까지가 한 단위다(`discrimination/stage2_c52_convention/probe/`).
- 규약 문장을 검사로 바꾸는 작업은 **그 회차에 프로브까지** 해야 완료다. 스킬에 규칙으로 넣는다.

### 8. 도구 경유 파일 쓰기에서 **백슬래시 한 단계가 벗겨졌다**

python heredoc 으로 Java 정규식 리터럴을 쓸 때 `\\s` 로 적은 것이 파일에는 `\s` 로, `\n` 은 **실제 줄바꿈**으로
들어가 `illegal escape character` · `unclosed string literal` 이 났다. **내가 공용 파일을 깨뜨렸고**,
그 상태를 `common-file` developer 가 먼저 만나 "내 변경이 아니고 공용 파일이라 고칠 수 없다" 며
`open_item` 으로 올리고 우회(`-Dmaven.test.skip=true`)했다 — **경계 규칙이 정확히 의도대로 작동한 사례다.**

- 교훈: 이스케이프가 들어가는 코드는 **원시 문자열**로 쓰거나, 쓰고 난 뒤 **해당 리터럴을 grep 으로 눈으로 확인**한다.
  컴파일까지 돌려야 끝이다 — 나는 파일을 쓴 직후 컴파일하지 않고 다음 작업으로 넘어갔다.
- 부수 효과: developer 가 규약 문서의 표준 계약 생성 명령(§9-3)을 쓸 수 없어 우회했다.
  **공용 파일이 깨지면 남의 게이트가 조용히 우회로 대체된다** — 그 우회는 레포트에 적혀 있었으나 게이트로는 안 걸린다.

### 9. 규약 검사 **6개 규칙을 전부 프로브**하니 하나가 정당한 코드를 막고 있었다

교훈 7 의 규칙("새 기계 검사는 프로브까지가 한 단위")을 **기존 규칙 5개에도 소급 적용**했다.
`server/app` 안 `com.example.gw.hrorder` 패키지에 위반 프로브를 심고 규약 검사만 돌렸다(`-Dtest=…ConventionTest`
— 전체 테스트를 돌리면 프로브 Mapper XML 이 MyBatis 에 잡힌다).

| 규칙 | 결과 |
|---|---|
| C-17 포트 우회(`WorkTimeStandard.COMPANY_DEFAULT`) | 검출 |
| C-24 `holidaysBetween().size()` | 검출 |
| **C-35 `assignable` 재정의** | **오검출 확인 → 규칙 수정 필요** |
| §14 남의 slice Mapper import | 검출 |
| C-33 `tb_dept` 직접 조인 — **`server/app` 안 slice XML** | 검출(OI-0126 닫힘) |
| C-52 감사 포트 전파 | 검출(교훈 7) |

- `OI-0130` 이 **예측했던 오검출이 실제로 있었다**: 부서 기준정보와 아무 관계 없는
  `boolean assignable(String approverEmpNo)`("결재선에 배정 가능한가")가 위반으로 잡혔다. 규칙이 **메서드 이름만** 봤다.
  slice 는 `CONVENTIONS` 를 고칠 수 없으니 **스스로 예외를 낼 수도 없어 오케스트레이터 개입 없이 막힌다**(RV3C-01 과 같은 함정).
  → 규칙을 **"선언 타입(`DeptDirectory`)을 언급하는 파일"** 로 한정했다. 재정의하려면 import·implements·주입 중
  하나로 그 타입이 소스에 나타난다. 수정 후 무관한 선언은 통과하고 `DeptDirectory` 를 주입받아 재정의한 프로브는 검출된다.
- **소급 프로브 1회로 확인 필요 항목 2건(OI-0126·OI-0130)이 증거와 함께 닫혔다.** "미검증" 으로 몇 회차를 끌던 것이
  실제로는 30분 작업이었다 — 검사를 만든 회차에 하지 않으면 그 항목은 계속 미검증으로 이월된다.
- 오검출 방향은 **검출 방향보다 위험하다**: 검출 실패는 결함을 놓치는 것이지만, 오검출은 **정당한 개발을 막고
  slice 가 스스로 풀 수 없다.** 프로브는 양방향 둘 다 해야 한다.

### 10. 검사 명령을 내 손으로 다시 쓰다가 오탐을 만들었다

Flyway 중복 검사를 즉석에서 `grep -oE '^V[0-9]+_[0-9]+'` 로 썼더니 `V100_05` 가 중복으로 나왔다.
실제로는 버전이 `V<대역>_<slice번호>_<타임스탬프>` 라서 **같은 slice 의 두 파일은 앞 두 토막이 당연히 같다.**
정본 패턴(`^V[0-9_]+`, 즉 `__` 앞 전체)으로는 중복 0 이다.

- 교훈: **검사 명령은 규약 문서에 적힌 것을 그대로 쓴다.** 즉석에서 줄여 쓰면 그 순간 다른 검사가 된다.
  나는 앞서 "오케스트레이터 명령은 도구를 호출하고 로직을 재구현하지 않는다" 를 규칙으로 만들어 놓고 같은 실수를 했다.
  `gate.py` 에 Flyway 중복 검사를 넣어 손으로 쓸 일 자체를 없애는 것이 맞다(후보).

## 2026-09-26 (오후) — 웨이브2 `domain-employee`: 기준정보 slice 의 전파력

이 slice 는 뒤 12개가 읽는 기준정보라(§13 S-14) 판단 하나가 넓게 퍼진다. 2회차로 끝났고 reviewer 는
"이 프로젝트에서 본 slice 중 증거 품질이 가장 높다" 고 적었다 — 판별력 4세트의 수치가 XML 과 **정확히** 일치했고
인용한 테스트 이름 27개 중 없는 것이 0건이었다. 그 위에서 나온 교훈들이다.

### 11. 조용히 데이터를 파괴하던 관용구 — 보조 유니크 + `ON DUPLICATE KEY UPDATE`

`tb_emp_privacy` 는 PK(`EMP_NO`) + 보조 유니크(`RRN_HASH`) 인데, 멱등 저장으로 쓴
`INSERT … ON DUPLICATE KEY UPDATE` 는 **어느 제약이 충돌했는지 구분하지 않고 충돌한 행을 갱신**한다.
→ "같은 주민번호 + 다른 사번" 저장이 예외 대신 **남의 개인정보 행을 덮어썼다**(H2·MySQL 동일).

- 발견 경로가 중요하다: **유니크 테스트가 "예외가 나야 한다" 로 실패**해서 드러났다. 기능 테스트로는 영원히 초록이다.
- 위험의 본질은 **골격 seed 가 같은 구문을 쓴다**는 것이었다. 그쪽은 유니크가 PK 뿐이라 안전한데,
  규약 표가 그 **조건**을 말하지 않아 "안전한 관용구" 로 복제될 상태였다 → C-63.
- 교훈: **관용구를 규약에 넣을 때는 그것이 안전한 조건을 함께 적는다.** 조건 없는 예시는 복제된다.

### 12. `real-db` 축의 값이 처음으로 **수치**로 나왔다

감사 호출을 `readOnly` 트랜잭션 안으로 옮긴 **같은 변이**를 두 축에서 돌렸다.

| 축 | 실패 | 무엇이 잡혔나 |
|---|---|---|
| H2 | **1건** | 구조 검사(트랜잭션 경계를 보는 테스트)만 |
| MySQL 8.4 | **4건** | 위 1건 + `Connection is read-only` 3건 |

축을 늘린 판단이 "그럴 것이다" 가 아니라 **3건의 차이**로 확인됐다. 판별력을 두 축에서 각각 기록하면
축의 값을 직접 증명할 수 있다 — 앞으로 `real-db` 를 요구하는 slice 는 이 형태를 쓴다.

### 13. 규약이 있어도 기계 검사가 없으면 반복된다 (C-67)

`§5-2`("충돌 = 409 / 입력 오류 = 400")·`§5-5`("DB 제약 위반은 409")가 **이미 규약으로 있었는데도**
`EMP_008`(이미 등록된 겸직)이 400 으로 나갔다. 같은 slice 안에서 `EMP_004`·`EMP_005`·`EMP_006` 은 409 였다.
**어떤 검사도 잡지 못했고** reviewer 가 표를 손으로 대조해 찾았다.

- → 규약 검사에 7번째 규칙을 넣었다: `catch (DuplicateKeyException …)` 블록이 참조하는 오류 코드의
  **선언 상태를 소스에서 읽어** 409 가 아니면 실패. 프로브로 검출력 실측(`EMP_009`=400 을 던지는 프로브 → 검출 → 제거 → 재통과).
- 교훈: **21개 slice 가 같은 패턴을 쓰는 규약은 문장이 아니라 검사여야 한다.**
  "규약에 적혀 있다" 는 다음 slice 가 그 줄을 읽었다는 뜻이 아니다.

### 14. 열거 방식 화이트리스트는 구조적 함정이다

CORS `exposedHeaders` 가 `X-Trace-Id`·`Content-Disposition` 만 열거해서, `domain-employee` 가 만든
엑셀 잘림 알림 3종이 **cross-origin 에서 가려졌다** — "조용한 잘림" 을 고친 수정이 브라우저에서 무력화됐다.
slice 는 공용 파일을 못 고치므로 **매번 등록을 요청**해야 하고, 잊으면 조용히 실패한다.
→ `*` 로 바꿨다(`allowCredentials=false` 라 허용되고 이 CORS 는 local 전용이다) + `§5-7` 신설(계약에 `headers:` 선언).
- 교훈: 공용 화이트리스트에 slice 가 항목을 추가해야 하는 구조라면, **그 등록을 잊었을 때 무엇이 조용히 실패하는가**를 먼저 묻는다.

### 15. 통과 실행의 증거를 덮어썼다 (내 절차 문제)

developer 의 `-Pmysql` **통과** 실행 XML 을 내가 나중에 돌린 H2 전체 테스트가 덮어써서,
reviewer 가 `mtime`·활성 프로파일로 축 실행을 **독립 검증할 수 없었다**(EMP-09).
판별력 사본은 **실패** 실행만 남기는 규칙이었기 때문이다.
→ 통과 실행도 `reports/gate-evidence/<slice>_r<n>_<축>/` 로 사본을 남긴다. 2회차부터 적용해 15개를 보존했다.
- 교훈: **"그 축을 정말 그때 돌렸는가" 의 증거는 최종 실행이 덮는다.** 축을 닫았다고 적을 때 사본이 없으면
  그 주장은 회차가 넘어가는 순간 검증 불가가 된다.

### 16. `pa-meta` 에 칸이 없으면 산문은 사라진다

developer 가 산문에 적은 "지시와 다른 결정" 6건 중 **5건이 인계 시점에 사라졌다** — `deviations` 키가 없었고
`gate.py` 도 요구하지 않았다. §11 이 "확인 필요는 파일로" 라고 경고한 것과 정확히 같은 형태다.
→ `report-meta` 검사가 `deviations` 키를 요구한다(벗어난 것이 없으면 빈 배열로 **선언**). 적용 즉시 1회차 레포트를 잡았다.
2회차는 6건을 소급해 채웠고 reviewer 가 전부 판정했다(6건 중 5건 정당, 1건 미완).

## 2026-09-28 — 파이프라인 자체 점검 (도구 결함·상품화 품질·정합성)

| 영역 | 현상 | 조치 |
|---|---|---|
| 도구 | **RR·OI 병렬 채번 충돌**: `rr.py new` 는 "최대 번호+1 → 덮어쓰기", `gate.py oi new` 는 `open-items.yaml` 읽기-수정-쓰기에 잠금이 없었다. 6건 동시 실행 시 RR 4건·OI 2건만 남음(재현). `max_parallel: 3` 에서 reviewer·보안 점검이 동시에 RR 을 만들면 결함 기록이 조용히 사라질 수 있었다 | `tools/_common.py` 신설 — O_EXCL 잠금 파일(`file_lock`, Windows·Linux 공통, stale 회수)·배타적 번호 파일 생성(`create_numbered_file`)·원자적 YAML 쓰기. `rr.py new/set/stats`, `gate.py oi new/set/import` 적용. 16건 동시 실행 회귀 테스트(`tests/test_concurrency.py`) |
| 도구 | 왜 처음에 못 잡았나: 도구에 테스트가 없었고, 샘플 회차는 RR 을 오케스트레이터가 웨이브 종료 후 순차로 만든 경우가 대부분이라 경합이 드러나지 않았다 | pytest 25건 + GitHub Actions(Linux·Windows × Python 3.10·3.12). 워크스페이스 경로 계산 3중 복사도 `_common.workspace()` 로 통합 |
| 상품화 품질 | 스킬·프로필에 **Javadoc 규칙이 전혀 없었고**, 로깅 규칙은 Boot4 프로필에만, Mapper XML 주석은 의미차이 태그 용도로만 있었다. 빌드·테스트 게이트는 통과해도 납품 코드 기준(문서화·운영 로그)은 에이전트마다 들쭉날쭉해질 구조 | `stage2-backend §B-7`(규칙 표), 기본 프로필 "문서화·로깅 규약"(traceId 필터·logback-spring.xml·GlobalExceptionHandler 로그 레벨·Mapper 주석 예), `stage4-frontend §B-5`, sql-migrator·stage3·reviewer 체크리스트. **같은 기준을 매번 적용하도록 `tools/quality.py`**(14개 규칙, 결정적 JSON 출력) + gate `productization` 훅(critical 차단, `pipeline.gate.productization: strict` 면 major 도 차단) |
| 상품화 품질 | 검사기 자체 검증: good/bad 예제(규칙마다 정확히 1건) + 실제 오픈소스 2개(spring-petclinic, mybatis-spring-boot-starter)에 실행. 완전 한정명 어노테이션(`@lombok.extern.slf4j.Slf4j`) 미인식, 로그 문구 속 `"@Mapper"` 로 역할 오판 2건 발견 | 어노테이션 정규식을 FQN 허용으로, 역할·로거 판정을 주석·문자열 제거 코드 기준으로 수정. 두 사례를 회귀 테스트로 고정 |
| 문서 | README "서브에이전트 11개"(실제 12, sql-migrator 누락), config 예시 `asis.source_dir` 에 `<project>` 누락, tools.yaml·build_report·status 안내문의 `workspace/` 옛 경로, gate 오류 문구의 `report-meta.json`(실제 `.md`) | 수정. 재발 방지로 `tools/selfcheck.py`(에이전트·스킬·도구·템플릿 참조 실재, frontmatter 이름, README 에이전트 수·목록, 옛 workspace 경로, 외부 도구 경로, 커밋 금지 파일)를 CI 에 넣음 |
| 이력 | 2026-09-20 표의 "추가 예정" 항목 중 Clock 빈·`openApiDump` 태스크·`operationId` 명시 규칙은 `spring-mybatis-mysql.md` 에 이미 반영돼 있음을 확인 | 이 로그는 당시 기록이므로 원문은 고치지 않는다. 반영 여부는 해당 프로필에서 확인한다 |
| 남은 과제 | 게이트의 테스트 수·종료 코드는 여전히 에이전트 자기 기재값(형식만 검사) · 게이트 실행을 훅으로 강제하지 않음 | `docs/DESIGN.md §4` 에 등록 |

## 2026-09-29 — 게이트 증거 실측화·훅 강제·이모지 금지 전역화

| 영역 | 현상 | 조치 |
|---|---|---|
| 게이트 | 테스트 수·실패 수가 에이전트 자기 기재값이었다(형식만 검사). reviewer 가 XML 을 다시 세어 불일치를 잡은 실측이 있었으나 도구는 못 잡았다 | `gates[].results`(JUnit XML glob) 를 `test-evidence` 훅이 `<testcase>` 기준으로 직접 집계해 대조. `started_at` 이전 결과 파일(이전 실행 재사용)은 FAIL. `pipeline.gate.test_evidence: strict` 면 results 누락도 FAIL |
| 게이트 | `gate.py check` 실행과 FAIL 시 done 금지가 지침에만 있었다 | `.claude/settings.json` 훅 신설. state.yaml 을 done 으로 바꾸는 Edit/Write 직전에 해당 단계 gate 를 돌려 FAIL 이면 차단. Bash 로 state.yaml 에 쓰는 우회 차단. SubagentStop 에서 `pa-agent-result` 누락·깨진 JSON·필수 키 누락 차단 |
| 훅 | 첫 적용 직후 오탐: CLAUDE.md 를 고치는 명령의 문구 안에 "state.yaml" 단어와 `.write(` 가 함께 있어 차단됨 | 파이썬 쓰기는 state.yaml 이 실제로 열리는 경로일 때만 판정. 회귀 테스트에 고정 |
| 이모지 | 의미 차이 태그가 경고 기호(U+26A0)였고, sql-migrator 지침이 그 태그를 **Mapper XML 주석과 매핑표에 옮겨 쓰게** 되어 있었다 — 지침의 기호가 산출물로 전파되는 구조. status.py 출력도 그림 문자를 썼다 | 태그를 `[의미차이:태그명]` 텍스트로 전환(67곳). 판정 기준 `tools/_emoji.py` 하나로 훅·quality(NO-EMOJI critical, 테스트·리소스 포함, ignore 불가)·gate(no-emoji)·selfcheck 가 공유. CLAUDE.md·pipeline-core §15 전역 규칙 + 모든 에이전트·스킬·명령 35개 파일에 조항, selfcheck 가 조항 누락을 CI 에서 잡음 |
| 테스트 작성 | 테스트 코드에 escape 로 쓰려던 이모지가 실제 문자로 저장됨 — selfcheck 가 즉시 적발 | 테스트의 이모지는 escape 표기만 쓴다 (pipeline-core §15) |

## 2026-09-29 (오후) — 공통 선행 확정·잠긴 기대 동작 테스트·화면 검증 선별

| 영역 | 현상 (사용자 실측) | 조치 |
|---|---|---|
| 공통 | 업무 단위 변환 중 공통 Util·상위 클래스가 업무마다 쓰는 메서드가 달라 **분해·절단**되고, 한 메서드만 쓰는 업무는 공통을 **private 으로 복제**했다. "공통만 변환" 을 따로 돌리면 업무 단과 어긋나 "업무 변환 → 공통 변환 → 다시 짝지어 검사" 가 반복됐다. Mapper 도 같았다 | 왜 처음에 못 잡았나: pipeline-core §6-4 가 "공용 변경은 slice 안에 임시 구현, 3단계가 흡수" 라고 **지시**하고 있었다 — 공통의 소유자·확정 시점이 없었던 것이 원인. 조치: 공통 사용 행렬(`common_usage.py`, 메서드·statement 단위, 상속·필드 타입·전이 폐포·오버로드·Mapper 인터페이스), 공통 계약(`common_contract.py`, 단일 업무 공통도 기본 공통 유지, 미사용은 사람 판단, 승인은 사람만), `common-porter`(공통 유일 작성자, 클래스 단위 선행 변환), 공통 요청(CR), gate `common-integrity`(본문 3-gram 유사도로 변수명 바꾼 private 복제까지 차단, 공유 Mapper statement 복제 차단, common-port 계약 이행). §6-4 는 migration 에서 임시 구현 금지로 개정 |
| 공통 | 도구 검증: 레거시 예제(대출·예금 × 유틸·상위 클래스·공통 DAO·공유 SQL 조각·교차 SQL·동적 id)의 정답표와 전부 일치. spring-petclinic 에서 프레임워크 진입점(@Bean·@GetMapping·main·접근자)이 미사용으로 잡혀 폐기 후보가 될 뻔함 | 진입점 판정 추가(어노테이션·main·접근자). 로그 문구 속 "@Mapper" 로 역할을 오판한 이전 교훈과 같은 유형 — 판정은 주석·문자열 제거 코드로 |
| 검증 | 특성화 테스트를 코드 작성자가 직접 써 자기 확인 편향 | 계약 선행(시그니처·스텁) → behavior-spec-writer → `spec_lock.py` 해시 잠금(추가만 가능) → 구현 → equivalence-verifier(독립 재실행 + 별도 작업 트리 결함 주입 표본). 훅이 잠긴 파일 편집·Bash 수정·매니페스트 편집 차단, 해제는 사람만. gate `spec-lock` 이 해시·전체 실행·실패 0 검사 |
| 화면 | 스크린샷을 AI 가 매 테스트 판정하면 비용·비결정성 | Playwright 픽셀 비교(토큰 0) + `visual.py` 가 새·변경 기준 이미지와 실패 diff 만 선별·토큰 추정(긴 변 1568·약 1.15MP 축소 반영) + ui-verifier. gate `visual` |
| 훅 | 사람 전용 명령 판정이 안내 문구 속 명령 문자열에도 걸림(실측 오탐 2회) | 명령이 실행 위치(줄 시작·; && | 뒤·$( ·따옴표 안 bash -c)에 있을 때만 판정. 회귀 테스트 고정 |
| 이모지 | 판정 모듈 자신의 예시 주석과 테스트 값에 실제 이모지 문자가 들어가 직전 커밋 CI 실패 | 예시는 U+XXXX, 테스트 값은 escape. selfcheck 가 git 추적 파일 전부를 보므로 새 파일은 커밋 전에 selfcheck |

## 2026-09-29 (저녁) — 큰 slice 의 업무 프로세스 기준 unit 분할

| 영역 | 현상 (사용자 제기) | 조치 |
|---|---|---|
| 분할 | slice 크기가 고르지 않다. '이벤트' 같은 작은 업무와 '보험금 청구' 같은 작은 프로젝트급 업무가 같은 방식(에이전트 1회)으로 돈다. 큰 slice 는 뒤로 갈수록 원문을 다시 읽지 않아 분기·statement 가 빠지고, 비슷한 분기를 합치며, reviewer·spec 도 대표 경로만 본다 — 모두 빌드·테스트는 통과한다 | 왜 처음에 못 잡았나: stage1 의 크기 규칙이 "API 5~20개, 넘으면 하위 slice" 한 줄뿐이었고 측정 도구가 없었다. 하위 slice 는 상태 전이를 공유하는 업무(청구의 접수·심사·지급)를 나누면 계약·도메인이 갈라진다. 조치: `slice_units.py measure`(AS-IS 입력 토큰 추정·API·화면·statement·메서드·상태 전이 → 분할·적정·묶기), slices.yaml `process`·`units`(core·step·query)·`flows`, `matrix`(slice 내부 사용 행렬 — 2개 이상 unit 이 쓰는 클래스는 core 필수, 한 unit 만 쓰는 하위 클래스·statement 자동 배정, 미배정은 FAIL), `validate`(전이 소유 1:1·API/화면 분배·core 선행·흐름 포함), gate `unit-scope`, 훅의 unit 완료 전환 검사, `plan`·`status` 의 unit 표시 |
| 분할 | 나누면 새 위험이 생긴다: slice 안 공유 클래스가 unit 별로 분해되는 것(§17 과 같은 문제의 축소판), unit 사이 상태 인계, 쪼갠 뒤의 누락 | core 선행·클래스 통째로(§17 구조 재사용), 흐름 테스트(`suite: flow`·flow id 인용)를 slice 완료 조건으로, unit 레포트 `asis_covered` 와 배정의 전수 대조 |
| 게이트 | 검증 중 발견: `collect_test_text` 가 빌드 산출물을 거를 때 절대경로에 `/target/` 이 있는지 봤다 — target_dir 이름이 `target` 이면 테스트 파일이 전부 빠져 추적·흐름 검사가 항상 "없음" 이 된다 | target_dir 기준 상대경로로 판정. 흐름 테스트 회귀가 이 경로를 덮는다 |
| 훅 | slice 통합 시 마지막 unit 과 slice 를 한 번에 done 으로 쓰면, 훅이 돌리는 게이트는 아직 쓰기 전 state 를 읽어 "unit 미완료" 로 막는다 | 훅이 기록하려는 새 state 를 임시 파일로 넘기고(`PA_STATE_FILE`) 게이트가 그것으로 판정. unit 전환을 slice 전환보다 먼저 검사 |


## 2026-09-29 (밤) — 말로 시키는 진입점(work-router)·차수 추가 갱신 모드

| 영역 | 현상 (사용자 제기) | 조치 |
|---|---|---|
| 진입 | 파이프라인의 조합(단계 순서)은 이미 `/stageN`·`/run`·`/rerun`·`/refactor` 에 있지만, 사용자는 명령 이름이 아니라 상황("3차 범위 들어왔어", "고객이 오류 제보")으로 말한다. 명령 이름을 모르면 조합이 발동하지 않는다 | `work-router` 스킬 신설 — 상황 → 조합(C1 신규 착수·C2 차수 추가·C3 요구사항 변경·C4 결함 처리·C5 산출물·C6 현황 보고·C7 오픈 전 점검·C8 DB 변경). 새 방법론 없이 기존 명령의 순서만 정한다(체크리스트 §4 원본은 한 곳). `CLAUDE.md` 핵심 원칙 첫 줄에서 가리켜 항상 읽히게 했다. 사람 전용 결정·게이트 멈춤은 조합 안에서도 그대로 |
| 0단계 | `/stage0` 명령은 brief 가 있으면 "갱신 모드" 를 알리라고만 했고, 스킬에 갱신 모드의 정의가 없었다. 운영 중 다음 차수(예: 3차)가 들어오면 처음부터 다시 요약하게 되어 끝난 slice 의 요구사항 ID 가 바뀌고 추적 체인이 끊길 수 있었다. 같은 문서의 판이 여럿(작성중·내부용·고객전달용·v1.1·v1.2)인 실제 입력에서 기준 판 판정 규칙도 없었다 | 왜 처음에 못 잡았나: 샘플 회차가 전부 단일 차수였다. 조치: `stage0-ingest §6` 갱신 모드 — 차수 폴더 입력, 판 판정 근거 기록(판정 불가·동일 날짜 복수 판은 사람 확인), 요구사항 ID 보존, `SCOPE_DELTA.md`(신규·변경·삭제·유지 ↔ 영향 slice·상태), 끝난 slice 에 닿는 변경은 확인 필요 항목(`deferred`, target 2)으로 채번(요구 변경은 결함이 아니므로 RR 아님). brief 템플릿 §8 에 `차수` 칸 추가 |

## 2026-09-29 (실전 1회차) — 0단계: 기존 TO-BE 위에 다음 차수를 얹는 첫 실전 적용

첫 실전 프로젝트는 샘플과 두 가지가 달랐다. (1) Windows 한국어 환경, (2) target_dir 에 파이프라인 밖에서 만든 이전 차수 TO-BE 코드가 이미 있다(brownfield).

| 영역 | 현상 | 조치 |
|---|---|---|
| 훅 | 쓰기 훅이 stdin 을 OS 기본 인코딩(cp949)으로 읽어 한글이 든 state.yaml 쓰기를 "YAML 로 읽히지 않는다" 로 차단했다. 같은 원인으로 이모지 판정도 Windows 에서 틀어질 수 있었다. 왜 처음에 못 잡았나: 훅 테스트가 항상 `PYTHONIOENCODING=utf-8` 을 넣어 실행해 결함을 가렸다 | stdin 을 바이트로 읽어 UTF-8 로 디코딩. 회귀 테스트는 `PYTHONIOENCODING=cp949` 로 실행한다(수정 전 실패 확인) |
| 게이트 | 서브에이전트가 실행 시각을 실측하지 않고 적어 기록 시점보다 30분 뒤의 시각을 보고했다. 게이트는 형식만 보고 통과시켰다 | `gate-proof` 가 현재보다 미래인 `executed_at` 을 FAIL 로 본다(2분 여유). 회귀 테스트 고정 |
| 0단계 | "들어온 소스가 곧 범위"(stage0-ingest §3.10)는 AS-IS 전체가 들어오고 범위는 차수 요구사항이 정할 때 맞지 않다 | 이번 회차는 AS-IS 영역마다 `이전 차수 완료 / 이번 차수 대상 / 범위 외·미정` 분류 표로 우회. brownfield 절 신설 예정 |
| 0단계 | "config stack 최우선"(stage0-ingest §2)은 기존 코드가 있으면 거꾸로다 — config 에 템플릿 기본값이 남아 있었고 실제 코드와 프레임워크 메이저 버전·빌드 도구·DB 버전이 모두 달랐다 | 실측 스택을 brief 에 사실로 쓰고 config 와 다르면 §11 모순으로 올렸다. 규칙 개정 예정(target 에 코드가 있으면 실측 우선) |
| 0단계 | 기존 TO-BE 의 구조·결정 이력(규약)을 읽는 절차와 인벤토리 형식이 없었다. target_dir 자체의 작업 지침(push 금지 브랜치·마이그레이션 번호 대역·DB 표준 컬럼)도 파이프라인이 읽지 않았다 | 프롬프트로 지시해 `TOBE_EXISTING_INVENTORY.md` 를 임의 형식으로 작성. CLAUDE.md 에 "target_dir 지침을 먼저 따른다"·"target_dir 은 스스로 push 하지 않는다" 를 추가 |
| 0단계 | 0단계 서브에이전트는 open item 을 채번하지 않고 보고하는데 `gate.py check` 는 id 없는 항목을 FAIL 로 본다 — 에이전트가 스스로 게이트를 통과할 수 없다 | 오케스트레이터가 `oi import --write` 후 재검사(통과). 에이전트 단계 검사에서 id 없는 항목을 WARN 으로 볼지 검토 예정 |
| SQL | 이미 이관된 statement 를 표시할 상태가 4분류·매핑표에 없다. TO-BE 가 AS-IS id 를 머리 주석에만 남겨 statement 단위 대응은 id 일치·인용으로만 판정 가능했다 | migration-sql §1-5 에 brownfield 대응 열 추가("대응 근거 없음" 은 미이관 증명이 아님). 매핑표에 "기존 이관(재사용·보강)" 상태 정의 예정 |
| SQL | 대조에서 놓치기 쉬운 것 7종(세션별 적재 매퍼 B-DS, 짧은 이름 해석, id 전달 래퍼, 속성 공백, 세션별 엔진, 수신자 타입 한정)이 0단계 분석과 SQL 인벤토리 사이의 불일치로 드러났다 | migration-sql §1-5·§2-1(11행)·§2-2(태그 2) 에 누적 |

남은 과제(brownfield, 다음 단계에서 실측하며 반영): config 에 target 배치(`layout`)·마이그레이션 버전 규칙·브랜치/커밋/push 정책 키, 공통 계약의 기존 복제 baseline, quality 의 기존 코드 baseline(변경 줄만 검사·적용된 마이그레이션 예외), slices 의 `origin: pre-pipeline`, FE 테스트 러너가 없는 프로젝트의 4단계 게이트 전략.

## 2026-09-29 (실전 1회차) — 1단계: 기존 TO-BE 위 slice 분류와 백업 도구

| 영역 | 현상 | 조치 |
|---|---|---|
| slices | 템플릿에 소유 모듈·기존 코드 수정·이전 차수 완료 영역·범위 외 AS-IS 를 적을 키가 없어 에이전트가 `module`·`existing_code`·`pre_pipeline`·`unassigned.asis` 를 임의로 추가했다 | 이번 회차는 임의 키로 진행. 템플릿 정식 키 + gate 대조는 2단계 착수 전 반영 예정 |
| unit 분할 | 수천 줄짜리 컨트롤러·서비스가 모든 unit 의 진입점이면 클래스 단위 배정으로는 전부 core 로 올라가 core 가 상한의 2~3배가 되고 step·query unit 의 배정은 0 이 된다. 도구를 통과시키려고 거대 클래스를 한 unit 에 몰면 다른 unit 의 진입점을 숨기는 거짓 배정이 된다 | WARN 을 그대로 두고 결정 항목으로. 메서드 단위 배정 검토 예정 |
| 크기 측정 | 이전 차수 코드를 확장하는 slice 는 AS-IS 배정이 없어 크기가 0 으로 나오고 "묶기 후보" 로 오판된다. 0 은 "작다" 가 아니라 "근거가 없다" 이다 | 묶지 않음. 수정 대상 TO-BE 코드 측정 옵션 예정 |
| 공통 계약 | 초안 4,180 항목 중 사람 검토(review) 2,548 — 한 건씩 판단할 수 없는 양. 범위 외·이전 차수 완료 코드도 소유 slice 가 없어 공통으로 잡히고, 모듈 간 복사 규약(모듈별 공통)을 표현할 차원이 없다 | 승인 보류. 범위 외·완료 영역 제외, 미사용 일괄 규칙, 모듈 차원을 2단계 전에 반영 예정 |
| open item | 서브에이전트는 기존 항목의 target_stage 를 재예약할 수 없고 `oi import` 도 기존 id 를 건너뛴다 | pa-meta 에 제안값만 남김. import 의 재예약 지원 예정 |
| 공통 계약 (반영) | 위 공통 계약 문제 | 왜 처음에 못 잡았나: 샘플은 단일 차수·단일 앱·전 범위 입력이라 "소유 slice 없음 = 공통" 이 성립했고, 미사용이 몇 건뿐이라 개별 review 가 감당됐다. 조치: slices 템플릿 정식 키(`module`·`existing_code`·`hold`·`pre_pipeline`·`unassigned.asis`·`unassigned.apis`), 행렬의 범위 제외(`out_of_scope`·`pre_pipeline` 는 공통 아님·그 코드에서 출발한 호출은 사용으로 세지 않음), 미사용 일괄 규칙(도달 slice 없음 → `owner: none`·`not_migrated`, 목록 파일만. slice 소유 namespace 의 미사용 statement 와 slice 소유 피호출 클래스의 미사용 public 메서드만 review), 모듈 차원(`project.modules` → 한 모듈 공통 / 여러 모듈 `copy: true` / 사람이 `common_module` 로 승격), gate `common-integrity` 의 모듈 복사본 허용·같은 모듈 복제 차단, gate `slice-scope`(hold 완료 차단·모듈 경로 밖 변경 경고), `gate.py plan` 의 hold 제외. 예제 `tests/fixtures/brownfield` 에서 review 7 → 2 |
| 백업 | 프로젝트 고유 자산(config·workspace)은 git 에서 제외돼 PC 고장 시 복구 수단이 없었다 | `tools/backup.py`(zip + sha256 목록, 저장소 안 위치·저장소 밖 복원 경로 거부, 내용이 다른 파일은 --force 없이 덮어쓰지 않음). 테스트가 보관 개수 정리에서 같은 분 두 번째 백업(`<ts>-2_`)이 이름순으로 앞서 방금 만든 백업을 지우는 결함을 잡았다 — 만든 순서로 정렬, 방금 만든 파일은 삭제 제외 |

## 2026-09-29 (실전 1회차) — 1단계 후속: unit 배정을 메서드 단위로

| 영역 | 현상 | 조치 |
|---|---|---|
| unit 분할 | 클래스 단위 배정에서 수천 줄 컨트롤러·서비스 구현체가 모든 unit 의 진입점이라 전부 core 로 올라갔다. core 가 unit 상한(토큰 40k)의 1.2~3.4배, step·query unit 의 AS-IS 배정은 0. 왜 처음에 못 잡았나: 예제(tests/fixtures/claim)가 unit 마다 진입 클래스가 따로 있는 구조뿐이었고, "공유 클래스는 통째로" 원칙(§17)을 진입점·서비스 구현체에도 그대로 적용했다 | `slice_units.py` 가 진입점 클래스(컨트롤러)·업무 서비스 구현체만 메서드 단위로 배정(공용 유틸·상위 클래스·DAO 는 종전대로 통째). unit 의 `apis` 를 컨트롤러 요청 매핑과 대조해 진입 메서드를 자동으로 찾고, statement 는 호출 메서드를 따라간다. 인터페이스 호출이 구현체 메서드에 닿도록 구현 연결을 추가. 토큰 추정은 배정 메서드 본문 기준, core 초과 경고에 큰 메서드 상위 5개. 행렬 schema 2(`methods`), 옛 행렬 하위 호환. 예제 `tests/fixtures/bigctl` 로 회귀 고정. 반영: pipeline-core §20, stage1-slicing §7, backend-developer, report-meta |

## 2026-09-29 (실전 1회차) — 1단계 재분류: 메서드 단위 배정을 실제 AS-IS 에 적용

| 영역 | 현상 | 조치 |
|---|---|---|
| 파서 | 어노테이션 배열 인자 `@RequestMapping(value={"/a.do", "/b.do"})` 의 `{` 를 멤버 본문으로 읽어 그 뒤 첫 `;`(다음 메서드 본문 안)까지 건너뛰었다. AS-IS 12개 파일에서 메서드가 통째로 빠져(거대 컨트롤러 51개 중 20개만 인식) unit 의 API 경로 대응이 전부 실패했다. 왜 처음에 못 잡았나: 예제(bigctl) 컨트롤러가 단일 경로 매핑뿐이었다 | `_javasrc.parse_members` 가 괄호가 열린 세그먼트 안의 `{` 는 건너뛴다. 회귀 테스트(수정 전 실패 확인) |
| unit 검증 | `validate_structure` 가 slice 의 `asis.programs` 전부를 unit 의 `asis.programs` 에서 찾아 FAIL 로 봤다 — 메서드 단위 배정(§20)과 모순이라 거대 컨트롤러를 다시 core 에 통째로 올리게 만든다 | 행렬의 `methods`·`programs` 나 unit 의 `asis.methods` 가 덮으면 통과. 회귀 테스트 |
| slice 경계 | slice 소유가 클래스 단위라 한 컨트롤러에 있는 유형 전용 엔드포인트(DNS·SSL·퇴직예정자 등 25개)를 유형 slice 로 옮길 수 없다(옮기면 행렬이 그 메서드를 배정하지 못해 FAIL) | 컨트롤러를 소유한 slice 의 unit 이 계약에 두고 유형 slice 는 화면·처리기만. stage1-slicing §7 에 규칙 추가. slice 간 메서드 소유 지원은 검토 예정 |
| unit 크기 | 메서드 하나가 statement 46개를 부르는(유형별 확장 테이블 저장) 경우 statement 상한 40 은 어떤 분할로도 맞출 수 없다. 여러 unit 이 함께 쓰는 상세 조회 메서드(31개)는 core 에 남는다 | 토큰 상한은 전 unit 충족, statement 초과 3건은 원인 메서드와 함께 보고. statement 상한을 토큰과 별개 기준으로 둘지 config 재검토 예정 |
| 공통 계약 | 다른 모듈 slice 가 소유한 서비스 메서드를 부르면(user → 결재선 조회, admin → 신청 공통 설정) statement 사용이 호출 slice 로 전파되지 않아 모듈 간 복사(copy) 항목이 계약에 생기지 않는다. 같은 이름·같은 인자 수 오버로드 47건이 `asis 중복` 으로 init 마다 id 가 바뀐다. AS-IS 루트 밖의 옛 사본(`asis/doc/*.java`)이 같은 FQN 으로 slice 크기에 섞인다 | 레포트·open item 으로 보고(도구 개선 예정) |

## 2026-09-29 (실전 1회차) — 2단계 common-port SQL 이어받기(sql-migrator)

| 영역 | 현상 | 조치 |
|---|---|---|
| 이어받기 | 네트워크 오류로 끊긴 앞 회차가 Mapper 11개·DTO 를 남겼지만 테스트·매핑표·계약 기입이 하나도 없었다. 빌드는 통과했으나 파라미터 DTO 두 개(`mFlag`·`sDatetime`)는 MyBatis 속성명이 `MFlag`·`SDatetime` 이라 실행 시에만 깨지는 결함이었다. 왜 처음에 못 잡았나: 앞 회차는 매퍼를 모두 만든 뒤 테스트를 쓰는 순서였고, 빌드·XML 파싱은 파라미터 속성명을 검사하지 않는다 | 매퍼 하나마다 계약 기입(지시), DB 없이 도는 인터페이스 ↔ XML 파싱 대조 테스트를 기본 빌드에 둠, 필드명 규칙을 migration-sql 2-3 에 추가 |
| 방언 | MySQL 8.4 STRICT_TRANS_TABLES 는 UPDATE 조건의 잘린 숫자 변환('87G')을 오류로 올린다(SELECT 는 경고). 카탈로그가 "MySQL 은 암묵 변환이 관대하다" 로만 적혀 있어 가드를 덧대 오류를 0건으로 바꿀 뻔했다 | 실측으로 되돌리고 migration-sql 2-1 에 쓰기/조회 구분 행 추가. 운영 sql_mode 확인은 확인 필요 항목 |

## 2026-10-01 (실전 1회차) — 2단계 common-port: 판단의 재검증 경로가 없었다

| 영역 | 현상 | 조치 |
|---|---|---|
| 판단 | 공통 선행 변환에서 대체 매핑·`불필요:` 판정·폐기 정정·모듈 복사·설정 방식 선택 같은 **판단**이 레포트 산문(`deviations`·결정 절)과 계약 note 에만 남았다. 2단계 게이트는 빌드·테스트만 보고, 판단을 전제로 쓴 spec 도 같은 판단을 전제하므로 판단이 틀려도 통과한다. 실측: 분석 도구 결함 때문에 사용처 없음으로 나온 공통 4건이 폐기로 판정됐다가 도구 수정 후에야 되돌려졌다 — 판단을 다시 볼 단계가 정해져 있지 않았다 | `pipeline-core §21` 판단 기록 신설. `tools/judgment.py`(JD 채번·slice 별 재검증 기록·사람 면제), gate 훅 `judgments`(5·6·7단계는 그 단계·slice 가 확인할 판단에 결과가 없으면 FAIL, 2·3·4단계는 deviations 만 있고 judgments 가 비면 WARN), decision open item 의 resolved 는 JD 연결 필수. 기준: migration 은 AS-IS 기능 무손실 + 요구사항 충족(증거 2개), 신규는 요구사항 충족. 생성 에이전트 보고에 `judgments`, integration-tester·qa-runner·stage5·stage7 에 재검증 의무 |
| 판단 | 공통에서 내린 판단은 공통을 소비하는 업무에서 드러난다(예: 메시지 후 이동을 FE 몫으로 돌린 판단은 각 업무 화면에서만 확인 가능) | 판단 기록에 `verify_slices`(소비 slice)를 두고 slice 마다 따로 확인 결과를 받는다 |
| 분류 | 레포트가 3차 골격에서 파이프라인이 만든 테스트 설정 파일을 "2차 기존 파일" 로 적어 불필요한 승인 요청이 됐다 | brownfield 승인 요청 전에 `git log --format='%h %an %s' -- <파일>` 로 작성 주체를 확인한다(이 회차 반영, 도구화는 brownfield 모드 정식화 때) |

## 2026-10-01 (실전 1회차) — 2단계 common-port: 검증 단계의 동시 빌드·보강 순서

| 영역 | 현상 | 조치 |
|---|---|---|
| 병렬 | 시간을 줄이려고 reviewer 와 equivalence-verifier 를 동시에 띄웠더니 둘이 같은 작업 트리의 `target/` 에서 Maven 을 돌렸다. verifier 의 `clean` 이 reviewer 실행 도중 결과를 지웠을 수 있어 그 실행 결과를 증거로 쓸 수 없었다(verifier 는 별도 worktree 결과만 근거로 써서 결론은 유지) | `pipeline-core §6-6` 에 "검토·검증도 같은 작업 트리에서 빌드하면 동시에 띄우지 않는다(순서대로 또는 한쪽 worktree)" 추가 |
| 판단 → spec | spec 을 쓴 뒤에 내린 사람 결정(PM 없음 = null, 메일 제목·발신 이스케이프 유지)은 잠긴 spec 에 단언이 없어 판별력 결함 주입에서 생존했다(모듈 전체 검출 0 포함). 판단 기록에는 남아 있었지만 spec 보강으로 이어지지 않았다 | spec 작성 후의 결정은 그 결정을 단언하는 spec 추가(사람 잠금 해제 1회에 묶음)까지를 결정 반영으로 본다. 결정이 여러 건이면 port 전에 한 번에 해제·보강·재잠금한다 |
| 결정 기록 | 오케스트레이터 자신의 절차 결정(중복 테스트 정리)도 decision 항목이라 판단 기록 없이 닫으려다 도구가 막았다 | 의도대로 동작 - 사람 결정이 아닌 판단은 `--by 에이전트:orchestrator` 로 기록 |
| 업로드 | 개인 브랜치의 공통 커밋을 팀 공유 브랜치로 옮길 때, 개인 브랜치가 갈라진 뒤 dev 에 새로 들어온 줄(이모지 주석)이 같은 파일에 섞여 있었다 | 업로드 브랜치에서 다시 이모지·비밀정보·경로 대조를 한다(개인 브랜치 검사로 갈음하지 않는다) |

## 2026-10-02 (실전 1회차) — 2단계 common-port: 여러 데이터소스와 외부 테이블

| 영역 | 현상 | 조치 |
|---|---|---|
| 판정 기준 | AS-IS 가 서로 다른 엔진의 데이터소스 10여 개를 쓰고, 한 매퍼 폴더가 여러 팩토리에 통째로 적재돼 한 파일 안에 여러 방언 statement 가 섞여 있었다. 외부 데이터소스 statement 15건이 이관 대상 DB 와 **같은 이름**의 테이블을 썼다. 지침의 기준이 사실상 "이관 대상 DB 에 있는 테이블이면 이관" 하나여서, 그대로 기계 판정하면 외부 쿼리를 대상 방언으로 바꾼다. 또 공통 계약에 외부 실행 statement 수십 건이 '계승' 으로만 적혀 있어 업무 변환이 대상 방언으로 바꿀 위험이 있었다(코드 위반은 아직 0건 — 감사로 미리 발견). 왜 처음에 못 잡았나: 인벤토리에 호출 세션·엔진 열을 두라는 문장은 있었지만(세션별 적재) **판정** 규칙과 연결되지 않았고, 계약·게이트에 데이터소스 개념이 없었다. 지금까지의 예제·샘플은 데이터소스가 하나뿐이었다 | 판정을 두 축(실행 데이터소스 = 호출 세션 기준 × 대상 테이블이 이관 대상인가)으로 고정: 주 실행 + 이관 대상 → 변환, 외부 실행 → 이름이 같아도 원래 방언 그대로 그 데이터소스로, 주 실행인데 이관 대상 아님 → 이관 안 함(근거 부족). `pipeline-core §22` 신설, `migration-sql §1-1`, sql-migrator·common-porter·backend-developer·slice-planner, 0·1단계 명령 |
| 엔진 | 개발 프로필 설정이 일부 외부 데이터소스를 주 DB 로 돌려 놓아 4개 데이터소스의 엔진이 개발·운영에서 달랐다. 0단계 인벤토리는 개발 설정 기준으로 적었다. SQL 본문 방언과 운영 엔진이 어긋난 statement 도 있었다 | "원래 방언" = 운영 프로필 엔진. 지도에 `engine`(운영)·`dev_engine` 을 따로 두고, 본문 방언과 운영 엔진 불일치는 그대로 옮기지 않고 decision 으로 |
| 외부 테이블 | "외부 쿼리를 로컬에서 돌리려면 테이블이 있어야 한다" 는 유혹으로 외부 테이블을 우리 DB 에 만들 수 있는데, 이를 막는 장치가 없었다(사용자가 가장 강하게 금지한 것). 한편 외부 시스템이 우리 DB 로 일 배치 적재하는 수신 테이블(AS-IS 에서는 같은 서버의 다른 계정 스키마)은 우리 DB 소유라 만들어야 한다 — 이름만으로는 둘을 구분할 수 없다 | 데이터소스 지도 `knowledge/DATASOURCES.yaml`(견본 `templates/DATASOURCES.yaml`): id·운영 엔진·용도·role(main/external/out_of_scope)·소속 테이블, main 의 이관 대상(`tables_from` 근거 DDL)·수신(`inbound_tables`)·합침(`merged_tables`)·미확정 외부(`unresolved_tables`). 접속 정보 키는 거부. `tools/datasources.py`(validate·judge·lookup·check) + gate `datasource-ddl`: target SQL 전부와 변경 코드에서 외부 테이블의 CREATE TABLE·VIEW·SYNONYM 은 FAIL, 수신 테이블을 src/main 이 쓰면 WARN, 지도가 없으면 migration 에서 WARN. 공통 계약에 `datasource`·`dialect`(init 보존, validate 가 지도와 대조). selfcheck 가 견본 규격을 확인 |
| 검증 축 | 외부 DB 는 로컬·CI 에서 접속할 수 없어 외부 statement 를 실행 검증할 수 없다. 같은 축(로컬 DB)에서 "테스트 통과" 를 만들려면 외부 테이블을 만드는 수밖에 없어 위 금지와 충돌한다 | trait `external-db` → 축 `real-server`. 2단계는 원문 정규화 비교·XML 적재까지, 실제 접속은 5·7단계 open item 으로 예약 |

## 2026-10-02 (실전 1회차) — 2단계 common-port: OGNL 정적 유틸 호출을 식으로 바꿀 때 인자 형 변환

| 영역 | 현상 | 조치 |
|---|---|---|
| 의미 동등 | AS-IS `<if test="@유틸@isNotEmpty( x )">`(매개변수 `String`)를 유틸 미이관에 맞춰 `x != null and x.trim() != ''` 로 바꾸고 "같은 판정" 이라 적었다. 문자열 값 시험만 돌려 통과했다. 검토에서 문자열 아닌 값이 지적돼 AS-IS 유틸 원본과 AS-IS·TO-BE MyBatis jar 로 직접 그려 보니, OGNL 은 `String` 매개변수에 Integer·Long·List 등을 문자열로 바꿔 넘겨(배열은 첫 원소) AS-IS 는 정상 판정, 바꾼 식은 `NoSuchMethodException` 이었다. 왜 처음에 못 잡았나: 동등성을 메서드 본문만 보고 판정했고 **호출 경계(OGNL 인자 변환)** 를 보지 않았다. 시험 값도 문자열만 골랐다 | `migration-sql §2-3` 에 규칙 추가: `x != null and x.toString().trim() != ''` 로 바꾸고, 배열 차이는 호출부 근거로 닫고, 애매하면 AS-IS jar 로 `<if>` 를 직접 그려 대조. 동등성 시험에는 문자열 아닌 값(Integer·Long) 사례를 넣는다 |

## 2026-10-02 (실전 1회차) — 2단계 common-port 마무리: 검증 도구·공유 브랜치

| 영역 | 현상 | 조치 |
|---|---|---|
| spec 잠금 | 같은 커밋을 `eol=lf` 로 꺼낸 검증 작업 트리에서 CRLF 로 잠근 파일이 "수정됨" 으로 나왔다. 내용은 같았다 | `spec_lock.py verify` 가 줄끝만 다른 해시(원본·LF·CRLF)를 같은 내용으로 본다. 시험 추가 |
| 결함 주입 | 파일 위치를 옮기는 결함(XML 을 다른 폴더로)을 clean 없이 돌리면 빌드 출력에 옛 사본이 남아 결과가 오염됐다 | 위치를 옮기는 결함은 clean 과 함께 주입한다(equivalence-verifier 운영 규칙) |
| 보호막 | 외부 데이터소스 배선·외부 SQL 을 지키는 시험이 구현자 특성화 시험뿐이었고, 생성 조건 두 개를 지워도 아무 시험이 실패하지 않았다 | 공통 묶음이라도 구현자 시험만 있는 범위는 behavior-spec-writer 의 잠긴 spec 으로 덮는다(18절). 검증이 "보호막이 누구 것인가" 를 먼저 적는다 |
| 게이트 | 기존 코드(brownfield)에 원래 실패하는 시험이 있으면 test-evidence 가 결과 파일의 실패를 그대로 막아, 단계 완료 레포트는 기준선 실패가 섞이지 않은 결과(spec·DB)만 결과로 걸었다. 변경 파일 목록이 비면 productization 이 target 전체(기존 파일 이모지 포함)를 본다 | 기준선 실패 목록을 게이트가 직접 대조하는 기능은 brownfield 모드 과제로 남긴다. 완료 레포트는 단계 기간 커밋이 바꾼 파일을 changed_files 로 적는다 |
| 공유 브랜치 | 여러 개발자가 같은 통합 브랜치에 각자 범위를 올리게 되자, 긴 작업 중 원격 변경을 모르면 공통 계약·잠긴 spec 과 어긋날 수 있었다 | 공유 통합 브랜치가 있으면 세션 시작·긴 작업 착수 전·중간·push 직전에 받아 변경을 분석(공통 파일·계약·잠긴 spec·업무 겹침·외부 CREATE·비밀값)하고 머지한다. push 는 직전 재동기화 뒤 빨리감기로만 |

## 2026-10-05 — 두 PC 에서 같은 규칙을 각자 만들면 설계가 갈린다 (합침 회차)

랩탑 A 에서 푸시하지 않은 커밋 2개가 남은 사이 랩탑 B 가 35 커밋을 올렸고, **둘이 같은 문제를
서로 다른 설계로 고쳤다.** 판별력 증거의 "변이시킬 구현이 없는 경우" 를 A 는 `method: harm_evidence`
(+ `enforced_by`)로, B 는 `method: absent_pre_fix`(+ `harm_evidence` **필드**)로 만들었다.

- 합치는 기준: **B(원격)를 정본으로 두고 A 를 그 위에 얹는다.** 두 설계가 실제로는 다른 상황을 가리켰다 —
  `absent_pre_fix` = 판별 수단이 없었다 · `harm_evidence` = 변이시킬 구현이 없다. 그래서 둘을 **공존**시키고
  헷갈리지 않게 `pipeline-core §14-9` 와 `templates/report-meta.md` 에 구분을 적었다.
- `cherry-pick` 은 4개 파일 전부 충돌했다(절 번호가 밀렸다 - A 의 "보고의 정직성" 은 §15 였는데 B 에서 §15 는
  이모지 금지였다). 번호가 든 문서는 커밋이 갈리면 기계 병합이 안 된다 — **절 번호를 재배치하며 손으로 얹는 쪽**이 빨랐다.
- A 의 새 규칙(`deviations` 키 의무화)이 B 에서 생긴 시험 10건을 깨뜨렸다. 규칙을 뒤늦게 얹으면
  **그 사이에 생긴 픽스처가 전부 위반**이 된다 - 공용 픽스처(`tests/conftest.py: dev_meta`) 한 곳을 고쳐 닫았다.
- 교훈: **§14-10(새 검사는 프로브까지 한 단위)은 합치는 회차에도 적용된다.** 얹은 규칙 4개에
  검출·미검출 양방향 프로브 시험을 같은 회차에 넣었다(`tests/test_gate.py` 4건, 196 → 200건).
- 운영 교훈: **푸시하지 않은 커밋을 다른 PC 에서 이어 받을 길은 없다.** `main` 을 맞추기 전에
  `backup/<날짜>` 브랜치와 태그로 먼저 보존했다. 커밋이 하루 이상 로컬에 남으면 그날 올린다.

## 2026-10-05 (실전 2회차 · 새 작업 환경 1회차) — 0단계: 작업 환경이 바뀌면 드러나는 공백 6개

같은 실전 프로젝트를 **다른 PC** 에서 이어받아 0단계를 돌렸다. 코드는 공유 저장소로 따라오는데
**파이프라인의 기억(workspace)은 따라오지 않는다**. 사용자 결정으로 이전 환경의 workspace 를 옮기지 않기로 했고,
그 상태에서 0단계를 끝까지 돌리니 **구조적 공백 6개**가 한 회차에 전부 드러났다. 전부 brownfield 고유가 아니라
"작업 환경이 둘 이상인 프로젝트" 의 공백이다.

### 1. 증거가 다른 작업 환경에 있는 완료 단계 (BG-01)

앞 환경에서 끝낸 공통 선행 변환이 공유 브랜치에 올라가 있는데 그 회차의 레포트·`pa-meta` 가 이 환경에 없다.
`gate.py check` 는 레포트를 찾아 대조하므로 `done` 을 **확인할 수 없다**. 상태 값 5개(`pending`·`in_progress`·`done`·`blocked`·`skipped`)
어느 것도 이 상황을 말하지 않는다.
- 이번에는 `skipped` + 주석으로 우회하고 확인 필요 항목으로 돌렸다. 그런데 **`skipped` 는 "하지 않았다" 와 "다른 데서 했다" 를 구분하지 않는다** —
  누군가 "필요 없어서 건너뛴 것" 으로 읽으면 공통을 업무 안에 임시 구현한다(§6-4 가 금지하는 바로 그 사고).
- 반영 제안: 상태 값 `done_elsewhere` + 필수 4칸(`evidence_repo`·`evidence_ref`·`evidence_doc`·`verified_by`)과
  `evidence_ref` 가 target 의 git 에 실재하는지 보는 훅. §4 선행 조건에서는 `done` 과 같게 취급한다.
- **훅이 먼저 잡았다**: `state.yaml` 에 `done` 을 쓰려는 순간 완료 전환 게이트가 막았다. 거짓 기재를 도구가 막은 첫 사례다.

### 2. 기존 코드가 규약을 이미 위반하는데 그 단계는 고칠 수도 면제할 수도 없다 (BG-02)

0단계가 데이터소스 지도(§22)를 **처음** 만들자마자 검사가 기존 파일에서 critical 6건을 찾았다 —
외부 데이터소스의 뷰를 우리 DB 에 `CREATE TABLE` 하는 마이그레이션·시드 파일. 파이프라인이 만든 것이 아니다.
0단계는 읽기만 하고, 예외 수단은 사람만 둘 수 있다. 그래서 **발견은 하는데 해결·면제·차단 어느 것도 못 하고 끝난다.**
- 위험: 다음 단계의 첫 업무 slice 가 **자기 변경과 무관한 이유로** 막힌다. 병렬 웨이브면 여러 slice 가 동시에 멈춘다.
  그 파일들이 "손대지 않는다" 로 묶인 영역 안에 있으면 developer 는 손도 못 댄다 — §14-14 의 함정과 같은 형태다.
- 반영 제안: 지도에 `pre_existing_violations` 절(파일·행·발견 회차·`decision_oi` 필수)을 두고,
  검사는 **그 목록과 일치하는 것만 warn, 새로 생긴 것은 critical** 로 둔다. 기준선 개념을 검사에 들여오는 것이다.
  `decision_oi` 가 닫히지 않은 채 다음 회차를 넘기면 FAIL 로 올려 부채가 영구 면제가 되지 않게 한다.
- 같은 구조가 `quality.py`(이미 `productization: warn` 으로 완화)·`common-integrity`·`spec-lock` 에도 생긴다.
  **brownfield 공통 규칙으로 올릴 것**: 검사를 처음 켜는 회차는 기존 위반을 기준선으로 등록한다.

### 3. 이전 회차의 번호 체계가 다른 환경에 있다 (BG-03)

target 의 규약 문서와 소스 주석이 앞 환경의 `OI-xxxx`·`JD-xxxx`·`RR-xxxx`·brief 결정 번호를 **근거로 인용**한다.
그 원문이 없으니 (1) 이 환경에서 1번부터 채번하면 **같은 번호가 다른 뜻**을 갖고, (2) 인용된 번호를 검증할 수 없다.
- 반영 제안: ① `config` 에 `numbering.oi_start`·`jd_start`·`rr_start` 를 두어 "그쪽 최대 번호 + 여유" 부터 채번한다.
  ② **인용 전용 번호** 개념 — 원문이 없고 다른 문서가 인용만 하는 번호는 `knowledge/EXTERNAL_REFS.md` 에
  (번호, 인용 문서, 인용 문장, 원문 소재)로 등록하고 도구는 그것을 "존재하지 않음" 으로 FAIL 하지 않는다.
  ③ 0단계가 ID 를 부여하기 전에 target 소스의 `REQ-\d+`·`OI-\d+`·`JD-\d+` 를 grep 해 기존 체계를 먼저 읽는다.

### 4. 규약이 인용하는 정본이 target 의 gitignore 로 빠져 있다 (BG-04)

규약 문서(611행)가 "근거 문서와 이 문서가 다르면 **근거 문서가 맞다**" 고 선언하는데, 그 근거 문서가
target 저장소의 `.gitignore` 로 제외돼 이 환경에 없다. 이름이 비슷한 대체 후보가 있어서 **인용 대목 4곳을 grep 으로 대조해 보니 다른 문서였다**
(같은 절 번호가 전혀 다른 내용이었다).
- 교훈: **이름이 비슷하다고 대체 근거로 쓰지 않는다.** 인용 대목을 실제로 대조한다. 이번에 대조하지 않았으면 틀린 근거를 믿었다.
- 반영 제안: 0단계 절차에 "target 규약 문서가 인용하는 문서의 실재를 전수 확인(경로 나열 -> `ls`)" 을 넣고,
  없는 것은 brief §11 에 "근거 미확인" 으로 올린다. 대체 후보는 grep 대조 결과를 함께 적는다.

### 5. 선행 조건이 "입력 1개 이상" 뿐이라 AS-IS 원본 부재를 못 걸러낸다 (BG-05)

mode `migration` 인데 `asis.source_dir` 가 **존재하지 않아도** 0단계는 끝까지 돌고 `done` 이 된다.
0단계 산출물 목록은 AS-IS 계약·SQL 인벤토리를 요구하지만 **못 만들었을 때의 처리가 없다**.
- 위험이 구체적이다: §21-3 은 migration 판단의 재검증에 증거 **2개**(AS-IS 대조 + 요구사항 충족)를 요구한다.
  AS-IS 본문이 영구히 없으면 전자를 채울 수 없는데 도구는 그것을 모른다 -> 5단계가 빈 칸으로 넘기거나
  **그럴듯한 문장으로 채울 유인**이 생긴다(§23-5 가 경고한 형태).
- 반영: `state.yaml` 에 `asis_source: present | absent | partial` 를 두고(이번 회차에 실제로 넣었다),
  `absent` 면 `judgment.py verify` 가 AS-IS 증거를 **요구하지 않고** 요구사항 증거만으로 `verified_req_only` 로 기록한다.
  1단계는 AS-IS 본문이 필요한 slice 를 `hold: true` + `hold_reason: asis_source_absent` 로 제안한다.
  0단계 산출물 목록에 "못 만든 산출물과 이유" 표를 필수로 올린다.

### 6. 게이트 비교 기준선이 환경별 workspace 에 있다 (BG-06)

target 의 규약 문서가 게이트 판정 근거로 **파이프라인 repo 의 workspace 파일**(기존 실패 목록)을 가리킨다.
workspace 는 환경마다 다르므로 환경이 바뀌면 그 근거가 사라진다. 수치만 규약 문서에 남아 있었다.
- 기준선이 없으면 "기준선보다 나빠지지 않았는가" 판정이 불가능하고, 전체 테스트 실패를 전부 이번 차수 책임으로 읽거나
  반대로 전부 기존 실패로 넘긴다. 어느 쪽이든 게이트가 판별력을 잃는다(§14-5).
- 반영 제안: **기준선은 target 안에 두고 커밋한다**(`docs/pipeline/BASELINE_FAILURES.md` 같은 자리).
  규약 문서와 같은 저장소에 있어야 환경이 바뀌어도 함께 온다. `gate.py baseline` 로 측정·기록·비교를 한 곳에서 해
  수치를 손으로 옮기지 않게 한다.

### 7. 업로드 권한의 형태가 규칙에 하나 빠져 있었다 (이 회차 반영 완료)

전역 규칙은 target push 를 "사용자가 직접" 또는 "건마다 명시 승인" 둘로만 두었다. 실제로 사용자가 요구한 것은
**브랜치를 한정한 상시 승인**이었다. 그 형태가 규칙에 없어 판단으로 메워야 했다.
- 반영: `CLAUDE.md` 에 세 번째 형태를 추가했다 — 상시 승인은 `HANDOFF.md` 업로드 절과 **target 지침 양쪽에** 적혀야 하고,
  적힌 그 브랜치에만 유효하다. `pipeline-core §1-0` 에 "업로드 권한은 HANDOFF 와 target 지침이 함께 정한다 — 둘이 다르면 올리지 않고 먼저 묻는다" 를 넣었다.
- **실측으로 배운 것**: target 규약을 push 허용으로 바꾸고 `HANDOFF` 를 그대로 두었더니 0단계 에이전트가 두 문서의
  불일치를 확인 필요 항목으로 올렸다(그 사이에 HEAD 가 움직인 것도 실측해 보고했다). **한쪽을 고치면 같은 회차에 다른 쪽도 고친다.**
- 또 하나: 내가 쓴 업로드 7단계 절차를 그대로 적용하면 **문서만 바뀐 커밋도 전체 테스트를 요구**했다.
  규약을 쓰는 회차에 그 규약을 자기 커밋에 적용해 보면 바로 드러난다 — 문서 전용 변경 예외를 같은 편집에서 넣고 생략 이유를 커밋에 적었다.

### 이 회차의 도구·훅 성적

막아 준 것 3건: (1) Bash 로 `state.yaml` 쓰기 차단 -> Write 로, (2) 게이트 미통과 단계의 `done` 기재 차단,
(3) `decision` 확인 필요 항목을 판단 기록 없이 `resolved` 로 바꾸려는 것 차단(`--jd` 요구).
세 건 다 **거짓 기재를 쓰기 시점에 막았다.** 훅이 없으면 세 건 전부 레포트에 남았을 것이다.

## 2026-10-05 (실전 2회차) — 1단계: 공백 두 개를 도구로 닫았다 (외부 확정 계약 · 기존 부채 기준선)

0단계가 적어 둔 brownfield 공백 중 **2단계 착수를 실제로 막는 두 개**를 도구에 넣었다. 둘 다 같은 형태의 문제다 —
**파이프라인이 만들지 않은 것을 파이프라인이 심판하려 들어서** 다음 단계의 첫 업무 slice 가 자기 변경과
무관한 이유로 막힌다. 그리고 그 단계는 고칠 수도(남의 영역) 면제할 수도(예외는 사람 전용) 없다.

### 1. 공통 계약 — `status: external` (BG-07)

공통 선행 변환이 **이전 차수·다른 작업 환경에서 이미 끝난** 경우. 1단계 절차는 migration 이면 공통 사용 행렬 ->
계약 `init` 을 **무조건** 요구하는데, 이 상황에서는 만들면 안 된다:
- AS-IS 원본이 없으면 행렬 자체가 안 나온다(`common_usage.py` 종료 코드 2)
- 만들면 그쪽이 이미 쓴 번호 체계(`CC-xxxx` 수백 개)가 갈리고 **완료된 결과와 어긋난다**

→ `common_contract.py external --source --numbering --evidence --by '사람:<이름>'` 로 **선언만** 한다
(`status: external` · `items: []`). 승인은 평소대로 사람이 `approve` 로 한다(훅이 에이전트를 막는다).
`gate.py plan` 은 common-port 단계를 넣지 않는다.

**중요한 설계 선택**: `common-integrity` 훅을 통과(PASS)로 두되 **"항목 단위 검사(공통 복제·영역 침범·이행)를
하지 않았다" 를 INFO 로 남긴다.** 조용히 통과시키면 §23 이 경고한 "검사한 척" 이 된다. 그 방어가 빠지는 대신
reviewer 가 slice 코드와 정본 문서의 공통 대응표를 직접 대조하는 것으로 바꿨다 — 그 지시를 §17 에 적었다.

필수 4칸(`source`·`numbering`·`evidence`·`decided_by`)을 요구하는 이유: 이 선언은 "검사를 끄는" 선언이다.
무엇이 정본이고 번호가 어디까지 쓰였고 왜 외부 확정으로 보는지, 누가 그렇게 정했는지가 없으면 추적이 끊긴다.
`decided_by` 는 `사람:` 으로 시작해야 한다.

### 2. 데이터소스 지도 — `pre_existing_violations` 기준선 (BG-02)

지도(§22)를 **처음 만든 회차**에 이미 target 안에 있던 외부 테이블 CREATE. 실측에서 critical 6건이 한 번에 나왔고
그중 4건은 "손대지 않는다" 로 묶인 이전 차수 영역, 2건은 시험 데이터였다. `local_stubs` 는 **사람 전용·시험 전용**이라
쓸 수 없고 성격도 다르다.

→ 지도에 `pre_existing_violations[]` 를 둔다. 검사는 **등록된 것만 warn(기존 부채)으로 내리고
새로 생긴 것은 critical 로 남긴다** — 규약의 "기준선보다 나빠지지 않았는가" 를 검사에 들여온 것이다.

부채가 영구 면제가 되지 않게 한 장치 둘:
- **`decision_oi` 필수** — 그 부채를 닫을 확인 필요 항목을 반드시 연결한다. 형식도 검사한다(`OI-0000`).
  그 항목은 **열어 둔다**. 부채 자체가 남아 있기 때문이다.
- **`stale_baseline`** — 등록해 뒀는데 더는 걸리지 않으면 `check` 가 "해소됐으면 지워라" 고 알린다.
  기준선이 썩어서 새 위반을 가리는 것을 막는다. 파일 목록을 준 부분 검사에서는 보지 않는다(안 걸리는 것이 정상이므로).

예외는 **파일 단위 glob 으로만** 준다. 에이전트가 등록할 수 있게 한 것은 `local_stubs` 와 다른 점인데,
그래서 범위를 넓히지 못하게 파일 단위로 묶었다.

### 3. 같은 구조가 다른 검사에도 있다

`quality.py`(이미 `productization: warn` 으로 완화되어 있다)·`common-integrity`·`spec-lock` 도
**검사를 처음 켜는 회차**에 기존 코드가 통째로 걸린다. brownfield 공통 규칙으로 올릴 것:
**검사를 처음 켜는 회차는 기존 위반을 기준선으로 등록하고, 그 뒤부터 "나빠지지 않았는가" 로 본다.**

### 4. 번호 충돌이 예측대로 터졌다 (BG-03 실현)

0단계가 "번호 체계가 갈린다" 고 적어 둔 것이 1단계에서 실제로 났다. `oi import` 의 `max+1` 채번이
target 소스 주석이 인용하는 번호와 **정면 충돌**했다 — 같은 번호가 전혀 다른 뜻을 갖는 상태.
실측으로 target 주석의 번호를 전수 세어(OI 44개·JD 98개·CC 약 450·CR 4·RR 20) 대역을 피해 재배정했다.
- 교훈: **번호 체계는 코드 주석에 박히는 순간 그 저장소의 공용 자원이 된다.** workspace 가 환경 로컬인데
  번호는 공유되는 비대칭이 원인이다. `config` 의 `numbering.*_start` 를 넣는 것이 다음 할 일이다.
- 더 나쁜 것: 0단계가 이미 채번한 일부는 **되돌릴 수 없다**(그 번호로 보고가 나갔다). 충돌을 아는 채로 남겨 두고
  인용 전용 번호를 따로 등록하는 길밖에 없다.

### 5. 조회 전용 slice 는 unit 분할 처방이 없다 (BG-09)

화면 14개로 분할 후보가 된 slice 가 **상태 전이 0**이어서 §20 의 unit 기준(업무 프로세스 상태 전이)을 쓸 수 없었다.
소유 테이블도 특정되지 않아 하위 slice 기준도 없었다. 그리고 그 "화면 14" 는 라우트가 아니라 **지표 패널**이었다 —
`measure` 의 화면 수가 무엇을 세는지 규정이 없다.
→ `query` 종류 unit 분할 기준(조회 축·권한 범위·원천 시스템 중 하나로 나눈다)과 화면 수의 단위 규정,
`measure` 가 분할 후보를 내놓을 때 **처방을 함께 출력**하는 것, 나누지 않을 때 `no_split_reason` 을 필수로 하는 것.

### 6. slice 가 "이미 있는 공통에서 무엇을 소비하는가" 를 적을 칸이 없다 (BG-08)

외부 확정 계약을 쓰면 계약에 항목이 없다. 그러면 slice 가 어떤 공통을 쓸 것인지 **기계가 읽을 수 있는 자리**가 사라진다.
이번에는 YAML 주석에 FQCN·절 번호로 적었다(템플릿에 임의 키 금지). 주석은 도구가 못 읽으므로 대조도 안 된다.
→ `slices.yaml` 에 `consumes[]` 키와 그것을 실제 import·호출과 대조하는 훅.

### 이 회차에 넣은 시험

두 기능 모두 **검출·미검출 양방향 프로브**를 같은 회차에 넣었다(§14-10):
기존 부채는 등록분 warn / 미등록분 critical / 등록했지만 다른 파일이면 critical / 필수 칸 누락 거부 / stale 알림,
외부 확정 계약은 필수 4칸 누락 거부 / `items` 가 있으면 거부 / `decided_by` 가 사람이 아니면 거부 /
미승인이면 plan 이 여전히 멈춤 / 승인되면 common-port 단계 없음 / 훅이 INFO 로 남기고 PASS.
pytest 200 -> **207건**.

## 2026-10-05 (실전 2회차) — 2단계 계약 단계: 비밀값 스캐너 오검출과 Flyway 순서 오판

### 1. 비밀값 스캐너가 OpenAPI 보안 스키마 이름을 비밀값으로 봤다 (고쳤다)

손으로 쓴 OpenAPI 계약의 보안 요구 선언이 `password` 규칙에 걸렸다:

```yaml
security:
  - sessionCookie: []
    csrfToken: []        <- "token 로 보이는 값이 있다" FAIL
```

`password` 규칙은 `(?:password|passwd|pwd|secret|token|api[_-]?key)\s*[:=]\s*(\S+)` 이고
값 `[]` 가 `PLACEHOLDER_RE` 에 없었다. **스키마 이름이 `token`·`secret`·`key` 로 끝나는 것은 흔하다**
(`csrfToken`·`accessToken`·`apiKey`) — 값이 비면 비밀값일 수 없다.
→ `PLACEHOLDER_RE` 에 빈 컬렉션(`[]`·`{}`)·빈 문자열(`""`·`''`)·YAML 빈 값(`-`)을 넣었다.
검출 방향(실제 토큰은 그대로 FAIL)과 오검출 방향 둘 다 프로브 시험으로 고정했다.

**게이트는 이것으로 막히지 않았다** — `hook_secret_scan` 은 레포트 파일만 본다. 손으로 `gate.py secrets <경로>` 를
돌렸을 때만 나온다. 그래도 고친 이유: §14-10 대로 **오검출은 검출 실패보다 위험하다.** 에이전트가 이 FAIL 을 보면
계약을 고치려 들거나(멀쩡한 선언을 지우거나) 스캐너를 피하려 든다.

### 2. 에이전트가 Flyway 순서를 잘못 판정했다 (보고 대조로 잡았다)

서브에이전트가 `risk_surface` 에 **"새 파일 번호가 전역 최댓값(1.0.840)보다 작아 out-of-order 가 된다.
`-Dflyway.outOfOrder=true` 1회 필요"** 라고 적었다. 오케스트레이터가 실측으로 대조하니 둘 다 틀렸다:
- **`1.0.840` 이 어디에도 없다.** 기존 전역 최댓값은 `1.0.800` 이었다(`git ls-files` 로 변경 전 상태 확인)
- 새 파일은 `V1_1_400`·`V1_1_500` = `1.1.400`·`1.1.500` 이고 **`1.1.x > 1.0.x`** 다(두 번째 성분 비교).
  즉 **가장 큰 번호이고 out-of-order 가 아니다.** 불필요한 플래그를 운영에 쓸 뻔했다.

교훈: **버전 비교는 문자열 길이·마지막 숫자가 아니라 성분별 숫자다.** 세 자리 숫자(400·500)가 커 보여
"뒤에 붙었다" 고 읽기 쉽다. 그리고 "전역 최댓값" 같은 수치를 보고에 쓸 때는 **그 값을 실제로 구한 명령**을 함께 적게 해야 한다
— 적었으면 틀린 것이 바로 보였다(§23 의 "검사 명령을 규약대로 쓴다" 의 수치판).
→ 반영: `pa-agent-result.risk_surface` 의 수치 주장에도 근거 명령을 요구할 것(다음 회차 도구 과제).

### 3. 전수 검사의 기준선이 또 필요했다 (BG-02 의 세 번째 사례)

`quality.py` 를 target 전체로 돌리면 **이모지 critical 9737건**이 나온다 — 전부 2차 기존 파일(`.gitlab-ci.yml` 등)이다.
에이전트는 `--files <changed_files>` 로 돌려 critical 0 을 받았고 그것이 맞는 사용법이다.
즉 같은 공백이 데이터소스(BG-02)·품질(이것)·공통 무결성에서 반복된다.
**검사를 처음 켜거나 기존 코드가 많은 저장소에서는 "변경 파일만" 또는 "기준선 대비" 중 하나를 쓴다** 를
brownfield 공통 규칙으로 올릴 것. 지금은 도구마다 방식이 다르다(`quality.py` 는 `--files`,
`datasources.py` 는 `pre_existing_violations`, `gate.py` 훅은 레포트만).

### 4. 서브에이전트가 공용 Python 환경을 건드렸다

계약 규격 검증 수단이 저장소에 없어 에이전트가 `openapi-spec-validator` 를 **공용 환경에 임시 설치**했고,
그것이 `jsonschema` 를 4.26 으로 올려 `semgrep`(6단계)의 핀 `~=4.25.1` 을 깼다. 검증 직후 제거하고 4.25.1 로 되돌렸고
오케스트레이터가 `pip check`(No broken requirements) 와 버전으로 확인했다.
교훈: **에이전트가 도구를 설치하면 다른 단계의 도구를 깰 수 있다.** 계약 규격 검증은 저장소가 제공해야 한다
→ `tools/requirements.txt` 에 넣거나 격리 실행(`--target`/venv)을 쓰게 하는 것이 다음 과제.


---

## 2026-10-06 (3차 신규 개발 · 기준선 측정과 훅 오검출)

### 1. 기준선을 **DB 없이** 재면 115건이 거짓으로 실패한다

2차 테스트 기준선을 재려고 전체 테스트를 돌렸더니 3585건 중 **142건** 실패였다.
docker 를 띄우고 같은 커밋을 다시 돌리니 **27건**이었다 — `admin` 모듈 115건이 전부 사라졌다.
원인: `admin` 의 `*ApiIntegrationTest` 가 `loginAdmin` 에서 실 MySQL 을 탄다(H2 의존성이 없다).
DB 가 없으면 로그인이 500 이라 테스트가 줄줄이 깨진다.

→ 교훈: **"기존 실패 N건" 은 측정 조건 없이는 숫자가 아니다.** 커밋·DB 가동 여부·스키마·명령을 함께 적는다.
   적지 않으면 다음 사람이 전혀 다른 숫자를 보고 "내가 깼다" 고 오판한다.
→ 반영: 기준선 문서에 측정 조건 표를 필수 절로 두고, 조건이 바뀌면 숫자와 함께 갱신하게 했다.
   게이트가 "기준선보다 나빠지지 않았는가" 로 판정하는 모든 프로젝트에 적용된다.

### 2. 규약이 근거로 가리키는 자료가 `workspace/` 에 있으면 환경이 바뀔 때 사라진다

target_dir 의 규약 9절이 기준선 목록으로 project-agents `workspace/<project>/knowledge/` 의 파일을 가리켰다.
그 폴더는 `.gitignore` 로 git 에 올라가지 않으므로 **다른 작업 환경에는 없다.** 새 환경에서 판정이 불가능했다.

→ 교훈: **규약(target_dir)이 근거로 가리키는 자료는 규약과 같은 저장소에 둔다.**
   `workspace/` 는 파이프라인의 작업 공간이지 팀의 공용 기록처가 아니다.
→ 판별 기준: "이 파일을 2차 담당자도 봐야 하는가" 가 예면 target_dir, 아니면 workspace.
   (BG-06 의 일반형. 같은 공백이 기준선·테스트 계정·환경 전제에서 반복된다.)

### 3. 잠금 훅이 `2>&1` 을 "잠긴 테스트 쓰기" 로 봤다 (오검출)

잠긴 spec 을 **근거로 인용**해 RR 을 만드는 명령
(`rr.py new --evidence "<잠긴 spec 경로>:53" 2>&1`)이 훅에 막혔다.
`SPEC_BASH_WRITE_RE` 의 쓰기 판정에 바닥 `>` 가 들어 있어 표준오류 복제 `2>&1` 까지 리다이렉션으로 본 것이다.
파일 이름이 명령문에 보이기만 하면 막히므로, **18절이 정해 둔 유일한 정상 경로(RR 로 남기기)가 막혔다.**

→ 수정: `>` 를 `>(?!&)` 로 좁혔다. `2>&1`·`>&2` 는 통과하고 `> f`·`>> f`·`1>f` 는 그대로 막는다.
→ 교훈: **금지 장치가 그 금지의 정상 우회로까지 막으면 사람이 장치를 끄게 된다.**
   훅을 만들 때 "막아야 하는 것" 과 함께 **"이 금지를 지키면서 해야 하는 일"** 을 양방향 프로브로 고정한다.
   (`§14-10` 의 "새 기계 검사는 양방향으로 찔러본다" 가 훅에도 적용된다.)

### 4. `publish-public --check` 는 HEAD 를 읽는다 — 커밋 전에 돌리면 아무 의미가 없다

비밀값 스캐너 프로브 시험에 넣은 가짜 GitHub 토큰이 공개본 금지어에 걸렸는데,
**전날 검사는 통과했다.** `--check` 가 `git archive` 로 커밋된 내용을 읽기 때문이다.
커밋 **전**에 돌려 "금지어 0건" 을 보고 통과한 것으로 착각했다(실제로는 직전 HEAD 를 검사했다).

→ 교훈: **"쓰기 전 검사" 와 "커밋된 것 검사" 를 구분한다.** 저장소 전체를 보는 검사는 커밋 뒤에 돌린다.
→ 같은 함정: 테스트 픽스처가 보안 검사에 걸린다. 프로브는 "검사가 잡을 만큼 진짜 같되
   다른 검사의 금지어는 아닌" 값으로 만든다.

### 5. 번호 충돌을 설정으로 닫았다 (BG-03 종료)

OI·JD·RR·CR 번호는 target 소스 주석에 박히는 순간 **그 저장소의 공용 자원**이 되는데,
이력이 담긴 `workspace/` 는 환경마다 다르다. 환경을 옮기면 `max+1` 채번이 1 부터 다시 시작해 충돌한다.
종전에는 사람이 손으로 재배정해 우회했다.

→ 반영: `config.numbering.{oi,jd,rr,cr}_start` 를 더했다. `max+1` 과 시작 번호 중 큰 값을 쓰므로
   시작 번호가 뒤로 끌지 않는다. 설정이 없으면 종전대로 1 부터(뒤로 호환).
→ 교훈: **외부 저장소에 박히는 식별자는 "우리 폴더의 최대값 + 1" 로 매기면 안 된다.**

### 6. 외부 확정 계약에 "없던 공통" 을 더할 자리가 없었다 (BG-07 후속)

`status: external`(공통 선행 변환이 파이프라인 밖에서 끝난 경우)은 항목을 두지 않는다 — 그쪽 번호 체계와
갈리지 않게 하려는 설계다. 그런데 업무 slice 를 만들다 보니 **그쪽에 없던 공통 수단**이 필요해졌다
(사번으로 이름·부서를 얻는 수단). 공통 요청(CR)을 올려도 **계약에 남을 자리가 없었다.**
그러면 "공통을 업무 안에 임시 구현·복제하지 않는다"(17절)를 지키려 해도
**그 공통이 어디에 있어야 하는지 계약이 말해 주지 못한다** — 업무가 막히거나 몰래 복제한다.

→ 반영: external 계약에만 `additions` 를 두었다. 외부 확정 본문(`items`)은 그대로 비워 두고
  **이 파이프라인이 더한 것만** `CC-A001` 대역으로 센다. CR 을 거친 것만, 판단(JD) 또는 사람 결정이 있어야 더해진다.
  더한 것은 우리가 만든 것이므로 **검사한다** — `plan` 이 미이행 건에 common-port 를 넣고,
  `common-integrity` 가 미이행을 WARN·`ported` 라고 적었는데 target 에 없으면 FAIL 로 잡는다.

→ 교훈 두 개:
  1. **"검사할 수 없다" 와 "검사하지 않는다" 를 한 덩어리로 묶으면 안 된다.** 외부에서 온 부분은 검사할 수 없지만
     우리가 더한 부분은 검사할 수 있다. 묶으면 우리 쪽 미이행이 외부의 불가검사 뒤에 숨는다.
  2. **금지 규칙에는 그 금지를 지키면서 할 수 있는 길이 함께 있어야 한다.** "업무 안에 공통을 만들지 마라" 만 있고
     "그럼 어디에 만드나" 가 없으면 규칙이 작업을 막는다. (3번의 훅 오검출과 같은 구조의 실패다.)

→ 판별: 정본 문서가 그 **클래스**를 이미 공통으로 매핑했고 빠진 것이 **메서드 하나**뿐이면 경계를 넓히는 것이 아니라
  계약 항목의 누락 보완이므로 `additions` 가 아니다(실측: 암복호 유틸의 짝 메서드).
  `additions` 는 정본에 **없는** 수단을 더할 때 쓴다.

### 7. slice 가 소비하는 공통을 **주석**에 적었더니 도구가 전혀 읽지 못했다 (BG-08)

brownfield 1단계에서 `report-channel` 이 소비할 공통 10종을 `slices.yaml` 의 **YAML 주석**으로 적었다.
`stage1-slicing` 이 "임의 키를 만들지 않는다" 고 적어 새 키를 만들지 않은 것인데, 결과적으로
**그 연결이 기계 판독 불가**가 됐다 — gate 는 복제 여부만 보고 "이 slice 가 선언한 공통만 쓰는가" 를 볼 수 없었다.

왜 greenfield 에서는 문제가 아니었나: 공통 사용 행렬이 AS-IS 를 훑어 "누가 무엇을 쓰나" 를 **계산**한다.
brownfield 는 **공통이 먼저 있고 slice 가 나중에 온다** — 방향이 반대라 계산할 수 없다. slice 가 적어야 한다.

→ 반영: `slices.yaml` 에 `consumes: [{item, kind, source, note}]` 를 정식 키로 두고
  gate 훅 `consumes-integrity` 를 추가했다. 적었는데 target 에 없으면 FAIL("적기만 하면 통과" 를 막는다),
  적지 않은 공통을 import 하면 WARN, 계약이 외부 확정인데 비어 있으면 WARN.
  실측 적용: 주석의 10종을 데이터로 옮기고 11종 전부가 target 에 있는지 확인했다(클래스 1073·메서드 9377 중 누락 0).

→ 교훈: **"도구가 읽을 수 없는 자리에 적은 것은 적지 않은 것이다."**
  규정에 칸이 없어 주석으로 우회했다면 그것은 우회가 아니라 **규정의 공백**이다 — 칸을 만들어야 한다.
  (같은 구조: 기준선을 `workspace/` 에 둔 것(2번), 금지 규칙에 정상 경로가 없던 것(3·6번).)

→ 부수 효과: 실측해 보니 신고채널 코드가 **실제로 import 하는 공통은 3종**뿐이었다(스텁이라 그렇다).
  선언 목록과 실제 사용이 다른 것은 정상이지만, 그 둘을 구분해 적지 않으면 "선언했으니 됐다" 로 착각한다
  → `note` 에 "예정" 을 적어 구분했다.

### 8. 게이트가 "잠기지 않았다" 고 틀린 말을 했다 — 사실은 "검사할 수 없었다"

다른 PC 에서 공통 선행 변환을 끝낸 slice 에 `gate spec-lock` 이
"**기대 동작 테스트가 잠기지 않은 채 완료됐다**" 를 냈다. 그런데 spec 파일 101개가 target 에 **있었다** —
다른 환경에서 잠근 것이고, 없는 것은 잠금 매니페스트뿐이었다.
매니페스트는 `workspace/<project>/specs/` 에 있고 그 폴더는 git 에 올라가지 않는다(2번과 같은 공백).

문구가 틀리면 사람이 **엉뚱한 곳을 고치려 든다**. "spec 을 쓰라" 는 처방을 받았지만
실제로 필요한 것은 "매니페스트를 가져오거나 저장소 안에 둘지 결정" 이었다.

→ 수정: spec 파일이 있는지 먼저 보고 두 경우를 나눠 말한다. 둘 다 FAIL 이지만 **처방이 다르다.**
  - 파일도 없다 → "잠기지 않은 채 완료됐다" · spec 을 쓰고 잠근다
  - 파일은 있고 매니페스트가 없다 → "N개가 target 에 있는데 매니페스트가 이 환경에 없다 — 검사할 수 없다" ·
    매니페스트를 가져오거나, 환경이 둘 이상이면 저장소 안에 둘지 사람이 결정한다

→ 교훈: **검사가 실패할 때 "무엇이 사실인지" 와 "무엇을 확인할 수 없는지" 를 구분해 말한다.**
  통과/차단만 맞으면 된다고 보면 안 된다 — 틀린 진단은 틀린 수정을 부른다.
  (6번의 "검사할 수 없다 와 검사하지 않는다 를 묶지 마라" 의 메시지판이다.)

→ 남은 구조 문제: 잠긴 대상(spec 파일)은 target_dir 에 있는데 그 **매니페스트만 workspace 에 있다.**
  작업 환경이 둘 이상이면 반드시 어긋난다. `verification.spec_lock_dir` 로 저장 위치를 고를 수 있게 하는 것이
  다음 과제다 — 지금은 잠긴 산출물을 무인 상태로 옮기지 않았다(사람 결정 사항).

### 9. "다른 환경에서 끝났다" 를 적을 상태 값이 없었다 (BG-01)

공통 선행 변환을 다른 PC 에서 끝낸 뒤 이 환경에는 레포트·`pa-meta`·잠금 매니페스트가 없었다.
상태 값은 `pending | in_progress | done | blocked | skipped` 뿐이라 **`skipped`(하지 않았다)** 나
**`blocked`(막혔다)** 를 골라야 했는데 **둘 다 사실이 아니다.** 실제로는 끝났고, 증거만 여기에 없다.
그리고 어느 쪽도 **"이 환경에서 무엇을 확인하지 못했나"** 를 남기지 못해 다음 세션이 원인을 다시 조사했다.

→ 반영: `done_elsewhere` + `elsewhere.<키>` 선언(`where`·`evidence`·`not_verified_here`·`declared_by`).
  `status: external`(공통 계약)과 같은 규칙 — **사람만 선언하고, 확인하지 못한 것을 반드시 적는다.**
  선언이 없거나 칸이 비면 게이트가 그대로 차단한다(상태 값만 바꿔 통과시킬 수 없다).
  `spec-lock` 은 선언이 있으면 FAIL 을 WARN 으로 내리되 선언이 적은 미확인 항목을 가리킨다.

→ 교훈: **상태 값에 없는 사실은 거짓으로 기록된다.** 세 가지가 섞여 있었다 —
  "했다" · "안 했다" · **"했는데 여기서 확인할 수 없다"**. 셋째가 가장 흔한데 칸이 없었다.
  칸이 없으면 사람은 가장 가까운 거짓을 고르고, 그 거짓은 다음 세션의 조사 비용으로 돌아온다.

→ 설계 규칙으로: 통과를 허용하는 모든 예외에는 **"통과의 대가를 적는 칸"**(`not_verified_here`)을 필수로 둔다.
  (`status: external` 의 INFO, `pre_existing_violations` 의 `decision_oi`, 이것의 `not_verified_here` 가 같은 장치다.)

### 10. "매칭 0건" 의 7건 중 6건이 거짓이었다 — 이름 표기 하나로만 찾았다

0단계가 외부 시스템 18개를 AS-IS 인벤토리와 대조해 **7개를 "매칭 0건"** 으로 적고 확인 필요 항목(high)으로 올렸다.
영문명·약어·표기 변형을 넣어 다시 찾으니 **1개(APIHub)만 남았다.**

| 틀린 유형 | 문서의 이름 | 소스의 이름 | 종전 판정 | 실제 |
|---|---|---|---|---|
| 영문 풀네임 -> 약어 | `SomeGateway` | `sgw` | 0건 | 1파일 |
| 한글명 -> 영문 약어 | `한국XX인증(ABC)` | `ABC` | 0건 | 6파일 |
| 한글 복합어 -> 그 일부 | `XX정보(DEF)` | `XX정보` | 0건 | 19파일 |
| 한글명 -> 영문 약어 | `XX게이트서비스(GHI)` | `GHI` | 0건 | 11파일 |
| **동음이표기** | `전자결제` | **`전자결재`** (제/재) | 불일치 | 27파일 |

(이름은 일반화했다 — 교훈의 값은 **표기가 갈리는 네 가지 유형**이고 실제 시스템명이 아니다.)

→ 교훈: **문서는 한글명을 쓰고 소스는 영문·약어를 쓴다.** 한 표기로만 찾고 "근거 없음" 을 적으면
  **거짓 근거 부족**이 된다 — 실제로는 근거가 있는데 slice 가 불필요하게 `hold` 되고,
  사람에게 답할 필요 없는 질문을 보낸다. 이것은 "근거 없이 추측하지 않는다" 의 반대 방향 실패다.

→ 같은 회차의 두 번째 사례: 시트 읽기 도구가 긴 셀을 `파…` 에서 잘라 항목 2개를 "도구 표본 한계" 로 미확인 처리했다.
  **같은 파일을 다른 도구(전문 검색의 스니펫)로 다시 읽으니 전체가 나왔다.**

→ 반영: `stage0-ingest §4` 에 **"근거 없음으로 적기 전에 두 가지를 먼저 한다"** 를 넣었다 —
  (1) 이름은 여러 표기로 찾는다 (2) 도구가 자르면 다른 도구로 다시 읽는다.

### 11. 검사 결과를 문구로 판정해 차단된 검사 뒤에 push 가 나갔다

공개본 금지어 검사를 돌리고 바로 push 하는 명령을 이렇게 썼다:

```
python tools/publish-public.py --check 2>&1 | grep -E "통과|중단" && git push origin main
```

검사는 **중단(exit 2)** 이었는데 `grep` 이 "중단" 이라는 글자를 **찾았으므로 종료 코드 0** 을 냈고,
`&&` 가 통과로 보아 **push 가 나갔다.** 파이프는 앞 명령의 종료 코드를 버린다.

→ 교훈: **게이트 판정은 문구가 아니라 종료 코드로 읽는다.** 이 저장소의 원칙("게이트는 증거로")이
  도구에만 적용되고 그 도구를 **부르는 쪽**에는 적용되지 않았다.
```
python tools/publish-public.py --check > /dev/null 2>&1; rc=$?
if [ $rc -eq 0 ]; then git push origin main; else echo "차단 - push 하지 않는다"; fi
```
→ 일반형: 검사 명령을 `|` 로 꾸미는 순간 그 판정을 잃는다. 사람이 읽을 출력과 기계가 읽을 판정을 분리한다
  (출력은 보여 주고, 분기는 종료 코드로 한다). 서브에이전트의 `pa-meta.gates[]` 가 명령과 **`exit_code`** 를
  함께 요구하는 것이 같은 이유다 — 이번엔 오케스트레이터 자신이 그 규칙을 어겼다.

### 12. 분할 판정은 나왔는데 처방이 없었고, 판정의 입력 단위조차 정해져 있지 않았다 (BG-09)

조회 전용 slice 가 **분할 후보**로 판정됐다(화면 14 > 10). 그런데 처방은 **상태 전이 기준 step unit** 하나뿐이고
그 slice 는 조회·출력만이라 **전이가 0** 이었다. 하위 slice 기준(소유 엔티티가 갈린다)도 쓸 수 없었다 —
데이터 원천이 미정이라 소유 테이블을 하나도 특정할 수 없었다. 즉 **"나눠야 한다" 는 판정은 나오는데 나눌 방법이 없었다.**

더 나쁜 것: **판정의 입력인 "화면 수" 의 단위가 문서마다 달랐다.** 같은 범위를 한 문서는 3행(라우트),
다른 문서는 14행(지표 패널)으로 적는다. 14면 split, 3이면 ok — **단위 하나로 판정이 뒤집힌다.**
어느 쪽을 세는지 규정이 없었다.

→ 반영 셋:
1. **조회 전용 처방**: 전이가 0이면 `query` unit 을 **소유 테이블·데이터소스** 축으로 나눈다
   (한 unit = 한 원천 묶음 + 그것을 읽는 화면). 공유 조회·집계·권한 코드는 `core` 가 먼저.
   **원천을 특정할 수 없으면 나누지 않는다** — 그 상태로 나누면 경계가 임의가 되어 나중에 전부 다시 나눈다.
   `validate` 가 전이 0을 보고 이 처방을 안내한다.
2. **화면 수의 단위 = 라우트 하나.** 패널·지표·탭·모달은 세지 않는다. 한 화면이 유난히 무거우면
   그 무게는 `apis` 에 나타난다 — `screens` 를 부풀리지 않는다.
3. **`no_split_reason`**(20자 이상): 기준을 넘는데 나누지 않을 때의 근거를 **`slices.yaml` 의 칸**에 적는다.
   종전 규정은 "레포트에 남긴다" 였는데 산문은 도구가 읽지 못한다(7번과 같은 모양).
   무엇이 넘었나 · 왜 안 나누나 · **다시 측정할 시점**을 적게 하고, 적혀 있으면 WARN 대신 INFO 로 그 근거를 보여 준다.

→ 교훈: **측정 기준을 만들면 (a) 단위의 정의와 (b) 기준을 넘었을 때의 처방을 함께 만든다.**
  둘 중 하나가 없으면 그 기준은 사람에게 "뭔가 잘못됐다" 만 말하고 무엇을 할지는 말해 주지 않는다 —
  그러면 사람은 기준을 무시하기 시작한다. 처방이 없는 경우("나눌 수 없다")도 **정식 결과로 적을 칸**이 있어야 한다.

### 13. 기존 부채를 다루는 방식이 도구마다 달랐다 — 통일이 아니라 "전략 선택 + 대가 기록" 이 답이었다

파이프라인이 만들지 않은 코드에 검사를 켜면 그 코드가 이미 규약을 위반하고 있다. 그런데 그 단계는
고칠 권한도(다른 담당자 영역) 면제할 수단도 없어 **게이트가 영구히 차단**된다. 한 회차에 세 번 걸렸다 —
이모지 전수 critical 9737건(전부 기존 파일) · 외부 데이터소스 테이블 CREATE 6건 · 테스트 전체 실패 27건.
그리고 도구마다 다루는 방식이 달랐다(`--files` 범위 한정 / 등록 기준선 / 레포트만).

처음에는 "셋을 하나로 통일한다" 로 접근했는데 **성질이 달라서 통일하면 안 되는 것**이었다:

| 전략 | 검사의 성질 | 예 |
|---|---|---|
| 범위 한정 | **파일 단위**, 위반이 많다 | 이모지·주석·명명 |
| 등록 기준선 | **개체 단위**, 부채가 적다 | 외부 테이블 CREATE |
| 수치 기준선 | **합계**로 나온다 | 테스트 실패 수 |

통일해야 하는 것은 방식이 아니라 **"통과의 대가를 적는 칸"** 이었다.
- 범위 한정 → `scope.unchecked`(검사하지 않은 파일 수). **종전에는 `mode: files` 만 적어
  레포트만 보는 사람이 전수 통과와 구분할 수 없었다** — 실측해 보니 1개를 보고 **2495개를 안 본** 것이었다
- 등록 기준선 → 항목마다 `decision_oi`(없앨지 결정할 확인 필요 항목)
- 수치 기준선 → 측정 조건(커밋·환경·명령·집계 방식) + 기존 실패 목록

→ 반영: `pipeline-core §24` 에 전략 선택표와 공통 규칙을 적었다(기준선은 `target_dir` 안에 ·
  등록은 "그때 거기 있던 것" 만 덮고 새로 만드는 것은 여전히 금지 · 기준선 확대는 사람 결정 ·
  낡은 등록은 `stale_baseline` 으로 드러난다). `quality.py` 는 `scope.unchecked` 를 낸다.

→ 교훈: **같은 증상이 여러 도구에서 반복되면 "하나로 합쳐라" 가 아니라 "무엇이 공통이고 무엇이 다른가" 를 먼저 가른다.**
  여기서 공통은 *대가를 기록한다* 였고, 다른 것은 *전략* 이었다. 전략을 합치면 각 검사에 맞지 않는 방식이 강요된다.

→ 새 검사를 추가할 때의 규칙: **"기존 코드가 많은 저장소에서 이 검사를 처음 켜면 몇 건이 나오는가" 를 먼저 재 본다.**
  많으면 전략을 함께 설계한다. 차단만 만들고 전략을 안 만들면 사람이 검사를 끈다.

### 14. 0단계가 "AS-IS 원본이 없다" 를 걸러내지 못했다 (BG-05)

`config.asis.source_dir` 이 **없는 경로**를 가리키는데도 0단계가 그대로 돌아,
분석 자료(인벤토리·문서·DDL)만으로 brief 를 만들고 `done` 이 됐다.
"원본이 없다" 는 사실은 **사람이 나중에 알아차렸다** — 그 사이에 1단계가 slice 를 나누고
2단계 계약까지 갔다. 이관 slice 는 원본 없이 시작할 수 없다(업무 로직·SQL 원문·화면 규칙이 거기에만 있다).

`state.yaml` 에 `asis_source: absent` 를 손으로 적어 두긴 했는데 **어떤 도구도 그것을 읽지 않았다** —
7번("도구가 읽을 수 없는 자리에 적은 것은 적지 않은 것이다")의 또 다른 사례다.

→ 반영: gate 훅 `asis-source`(0·2·3·4단계 프로파일).
  - 원본이 있으면 **파일 수를 INFO** 로 남긴다(있다는 것도 증거로 남는다)
  - 없고 선언도 없으면 **FAIL** — `config.asis` 를 아예 빼도 같다("설정을 빼면 통과" 를 막는다)
  - `asis_source: absent|partial` 로 **선언하면 통과**하되, 그 때문에 멈춘 slice 를 WARN 으로 함께 드러낸다
  - 값이 목록 밖이면 선언으로 보지 않는다
  - `gate.py plan` 도 선언 없으면 멈추고, 선언이 있으면 "이관 slice 는 시작할 수 없다" 를 참고로 낸다

→ 교훈: **선행 조건은 "입력이 있다고 적혀 있는가" 가 아니라 "입력이 실제로 있는가" 로 검사한다.**
  설정은 의도를 적는 곳이고 사실을 보증하지 않는다. 경로가 가리키는 곳을 세어 본다.

→ 함께: `mode: migration` 에서 입력이 없을 때 **통과시키되 대가를 적게 하는** 형태를 또 썼다
  (§24 의 세 전략, `status: external`, `done_elsewhere` 와 같은 장치).
  이 저장소에서 반복되는 설계 수단이므로 새 선행 조건을 만들 때 이 형태를 먼저 고려한다.

### 15. 같은 훅이 하루에 세 번 오검출했다 — 원인은 "쓰기 판정" 과 "대상 판정" 을 섞은 것

잠긴 테스트 보호 훅이 **읽기·인용 명령을 세 번 막았다.**

| # | 막힌 명령 | 왜 |
|---|---|---|
| 1 | `rr.py new --evidence "<잠긴 경로>" 2>&1` | `2>&1` 의 `>` 를 리다이렉션으로 봤다 |
| 2 | 위를 고친 뒤 `grep X <잠긴 경로> 2>/dev/null` | `2>/dev/null` 의 `>` 를 리다이렉션으로 봤다 |
| 3 | (오검출 시험 스크립트 자체) | 명령문에 `rm`·`sed -i` 와 잠긴 파일명이 함께 있었다 — **이건 올바른 차단이다** |

1·2를 각각 패치하다 깨달았다 — 패턴을 좁히는 것으로는 끝나지 않는다. **설계가 틀렸다.**
종전 판정: "명령문에 쓰기처럼 보이는 토큰이 있고" **그리고** "파일 이름이 어디든 보이면" 차단.
두 조건이 서로 무관해서 조합이 엉뚱했다.

→ 바로잡은 설계: **경로를 두 갈래로 나눠 본다.**
1. **리다이렉션**은 대상 경로를 뽑아 그것이 잠긴 파일인지 본다. 파일 서술자 복제(`2>&1`·`>&2`)와
   널 장치(`/dev/null`)는 **애초에 대상이 아니다.** `grep X <잠긴 경로> > /tmp/out.txt` 는 통과한다 —
   잠긴 파일을 **읽어서** 다른 곳에 쓰는 것이다.
2. **파일을 인자로 받는 쓰기 명령**(`sed -i`·`rm`·`mv`·`cp`·`tee`·`truncate`·`git checkout`)은
   이름이 보이면 막는다 — 이 명령들은 읽기용으로 쓸 일이 없다.

실측 14가지로 고정했다: 읽기·인용 6가지 통과 · 쓰기 8가지 차단, 전부 기대대로.

→ 교훈: **오검출이 같은 훅에서 두 번 이상 나면 패턴을 좁히지 말고 판정 구조를 다시 본다.**
  "A 처럼 보이고 B 가 보이면 막는다" 는 A 와 B 가 같은 대상을 가리킬 때만 옳다.
  여기서는 `>` 가 가리키는 대상과 명령문에 보이는 이름이 **다른 것**이었다.

→ 덧붙여: 훅이 **제 시험 스크립트를 막은 것**은 올바른 동작이었다. 훅을 시험할 때는
  명령줄에 트리거를 두지 않도록 스크립트 파일로 옮기거나 샌드박스의 다른 잠금 매니페스트를 쓴다.

### 16. 기존 부채 때문에 완화했더니 **새로 만드는 코드까지** 완화됐다 (BG-10)

brownfield 에서 기존 파일이 규약을 이미 위반해 품질 검사를 `productization: warn` 으로 완화했다.
그런데 그 완화는 **이번 차수에 새로 만드는 파일에도 적용된다.** 새 파일은 처음부터 규약을 지킬 수 있으므로
완화할 이유가 없는데, 같은 강도로 다루면 **새 코드의 품질이 기존 코드 수준으로 수렴한다.**
"기존 부채를 덮는 장치" 가 "새 부채를 허용하는 장치" 로 바뀐 것이다.

→ 반영:
- `quality.py --new-files <추가된 파일…>` — 거기의 `major` 는 `--strict` 없이도 차단한다.
  `--files` 에 없어도 점검 대상에 넣는다(새 파일을 빠뜨리지 않게). 출력·JSON 에 `[신규]` 표시와 집계를 남긴다.
- gate `productization` 은 **`pa-meta.repo.base` 로 추가 파일을 스스로 계산**한다
  (`git diff --name-status <base>...HEAD` 의 `A`) — 레포트에 새 칸을 요구하지 않는다.
  `repo.base` 가 없으면 "구분하지 못했다" 를 INFO 로 남긴다.

→ 교훈: **완화 장치를 만들 때 "무엇을 덮는가" 의 경계를 시간으로 못 박는다.**
  "기존 코드" 는 *그때 거기에 있던 것*이고 *앞으로 만들 것* 이 아니다.
  경계를 적지 않은 완화는 반드시 새 코드로 번진다.
  (같은 규칙을 데이터소스 기준선에는 이미 적용했다 — 등록된 것만 `warn`, 새로 만드는 것은 `critical`.
  품질 검사만 빠져 있었다.)

→ 실측: 신고채널 신규 Java 40개를 이 모드로 검사하니 critical 0 · major 0 (Javadoc 100%)이었다.
  즉 지금까지는 운이 좋았던 것이고, 장치가 지켜 준 것이 아니었다.

### 이 회차 16건을 관통한 패턴 넷

16건을 다 읽지 않아도 되게 추린다. **새 장치를 만들 때 이 넷을 먼저 확인한다.**

**(가) 도구가 읽을 수 없는 자리에 적은 것은 적지 않은 것이다** — 7·9·14번
주석(`consumes`) · git 에 없는 폴더(기준선·잠금 매니페스트) · 산문(`no_split_reason`·완료 근거).
규정에 칸이 없어 우회했다면 그것은 우회가 아니라 **규정의 공백**이다. 칸을 만든다.
*확인 질문: 이 사실을 다음 세션의 도구가 읽을 수 있나?*

**(나) 금지 규칙에는 그 금지를 지키면서 할 수 있는 길이 함께 있어야 한다** — 3·6·12·15번
"공통을 업무 안에 만들지 마라" + 등록할 자리 없음 / "잠긴 테스트를 고치지 마라" + RR 쓰는 명령도 차단 /
"나눠야 한다" + 나눌 방법 없음. 길이 없으면 사람이 장치를 끈다.
*확인 질문: 이 규칙을 지키려는 사람이 다음에 할 일이 무엇인가? 그 길이 막혀 있지 않나?*

**(다) "통과했다"·"검사하지 않았다"·"검사할 수 없다" 는 서로 다른 주장이다** — 1·2·8·13번
섞으면 우리 쪽 미이행이 외부의 불가검사 뒤에 숨고, 틀린 진단이 틀린 수정을 부른다.
그래서 통과를 허용하는 모든 예외에 **"통과의 대가를 적는 칸"** 을 둔다 —
`status: external` 의 INFO · `done_elsewhere.not_verified_here` · `pre_existing_violations.decision_oi` ·
`scope.unchecked` · 기준선의 측정 조건.
*확인 질문: 이 예외로 통과했을 때, 레포트만 보는 사람이 전수 통과와 구분할 수 있나?*

**(라) 완화·기준선의 경계는 시간으로 못 박는다** — 16번(그리고 13번)
"기존 코드" 는 *그때 거기에 있던 것*이고 *앞으로 만들 것* 이 아니다.
경계를 적지 않은 완화는 반드시 새 코드로 번진다.
*확인 질문: 이 완화가 내일 만드는 파일에도 적용되나? 그래도 되나?*

**거짓 판정을 다루는 자세** — 10·11·15번
- 오검출은 미검출보다 위험하다(사람이 장치를 끈다). 같은 훅에서 **두 번** 나오면 패턴을 좁히지 말고 **판정 구조**를 다시 본다.
- "근거 없음" 을 적기 전에 다른 표기·다른 도구로 한 번 더 찾아본다 — 이번에 7건이 1건으로 줄었다.
- 검사 판정은 문구가 아니라 **종료 코드**로 읽는다.

### 17. 규칙을 바꿨는데 그 규칙을 따를 에이전트는 모르고 있었다

하루에 파이프라인 장치 9개를 더하고 `pipeline-core`·스킬·템플릿에 적었다. 그런데 확인해 보니
**에이전트 지침 어디에도 새 칸·새 명령이 없었다**(`consumes`·`no_split_reason`·`additions`·`asis_source` 전부 0건).

에이전트가 `pipeline-core` 와 해당 스킬·템플릿을 읽기는 한다. 그래도 **자기 체크리스트에 없으면 산출물에서 빠진다** —
읽는 것과 하는 것은 다르다. 실제로 이번 회차의 slice 목록에서 소비 공통 3건이 빠져 있었다.

→ 반영: 바꾼 규칙을 그 규칙의 **산출자**에게 각각 넣었다.
  `slice-planner`(`consumes`·`no_split_reason`·조회 전용 처방·화면 수 단위) ·
  `common-porter`(`additions` 제안·누락 메서드 판별·수치 근거) ·
  `ingest-analyst`(AS-IS 원본 실측·"근거 없음" 전 두 가지) ·
  `backend-developer`(`consumes` 가 쓸 수 있는 공통의 목록이다·상속도 소비다).

→ 교훈: **규칙을 바꾼 회차에 그 규칙을 지켜야 하는 주체의 지침도 같은 회차에 고친다.**
  "공통 규칙에 적었으니 전달된다" 는 가정이 틀렸다 — 전달은 됐지만 **행동 목록에 없었다.**
  (패턴 (가)의 변형: 읽히는 자리에 있어도 *해야 할 일 목록*에 없으면 하지 않는다.)

→ 점검 방법: 새 칸·새 명령을 더했으면 `grep -rl <이름> .claude/agents/` 가 **비어 있지 않아야 한다.**

### 18. 고객 식별 문자열이 하루에 세 번 tracked 파일로 들어갔다 — 쓰기 시점으로 옮겼다

프로브 시험을 쓸 때 **실측 명령을 그대로 붙여 쓰다가** 고객 식별 문자열이 들어갔다 —
프로젝트명 1회 · 패키지 경로 1회 · 시스템 약어 1회. 세 번 모두 **커밋 뒤에** `publish-public --check` 로 잡혔다.
즉 세 번 모두 **이미 이력에 박힌 뒤**였다(공개본은 HEAD 를 걸러 내므로 공개 자체는 막혔지만, 사설 이력에는 남는다).

왜 반복됐나: 프로브 시험은 "실제로 막혔던 명령" 을 그대로 재현하는 것이 가장 정확하다.
그래서 실측 경로·이름이 함께 따라 들어온다. **방법이 틀린 게 아니라 순서가 틀렸다** — 붙여 쓴 뒤 일반화해야 했다.

→ 반영: 이모지와 같은 성질이므로 **같은 자리(쓰기 시점 훅)** 에서 막는다.
  `guard.py` 가 Write·Edit·MultiEdit 의 새 내용을 `rules.yaml` 의 `deny` 로 검사한다.
  범위를 정확히 좁혔다 — 이 저장소의 **git 에 올라가는** 파일만 본다.
  `workspace/`·`config/project.yaml`(gitignore 대상) · `target_dir`(저장소 밖) · 규칙 파일 자신은
  고객 이름이 있어야 정상이므로 보지 않는다. 규칙 파일이 없는 프로젝트는 검사하지 않는다(뒤로 호환).
  양방향 8가지로 고정했다.

→ 구현 중에 찾은 결함: `git check-ignore` 의 종료 코드를 `!= 0` 으로 봤더니 **git 저장소가 아닌 곳**(128)도
  "추적 대상" 이 되어 모든 쓰기를 막았다. `== 1` 로 바로잡았다 — **모르면 검사하지 않는다.**
  (판정이 세 값(예·아니오·모름)인데 두 값으로 나눈 흔한 실수다.)

→ 교훈: **검사를 뒤로 미루면 "막았다" 와 "이미 들어갔다" 를 구분하지 못한다.**
  되돌릴 수 없는 경계(커밋·push·발행) 앞이 아니라, **쓰는 순간**에 막을 수 있으면 거기서 막는다.

## 2026-10-06 (실전 3회차 · 원본 있는 환경 복귀) — 결과 블록 옮기기와 "사람이 만든 자료" 의 지위

원본(AS-IS) 이 없는 작업 환경에서 공유 브랜치에 올린 계약·spec 을, 원본이 있는 환경에서 이어받는 회차였다.

1. **결과 블록을 손으로 옮기면 빠진다.** 서브에이전트 하나가 판단 8건·확인 필요 4건을 보고했는데,
   오케스트레이터가 레포트를 손으로 쓰면 문구를 줄이거나 항목을 흘린다(§12 의 RR 증발과 같은 성질).
   → 반영: `tools/ingest_result.py` — 결과 JSON 하나로 OI 채번 → 레포트(pa-meta, repo 는 git 실측) → JD 채번을 한 번에 한다.
   서브에이전트는 같은 JSON 을 `reports/agent-results/` 에도 저장한다(pipeline-core §12).
2. **사람이 만든 자료는 참고이고 정본은 원본 소스다.** 공유 브랜치의 계약·spec, 분석 문서 브랜치, 드라이브 산출물은
   사람(또는 원본 없는 환경의 에이전트)이 만든 것이라 오류가 섞인다. 근거는 AS-IS 원본 파일:라인으로 대고,
   참고 자료는 원본과 대조한 뒤에만 쓴다. → 반영: pipeline-core §12 에 원칙을 넣고 오케스트레이터가 모든 프롬프트에 적는다.
3. **파일 이름의 버전·날짜가 더 커 보여도 최신이 아닐 수 있다.** 같은 요구사항 문서가 `v1.2_<9월 28일>` 과 `<9월 23일>(내부용)` 두 개로 왔다.
   이름만 보고 v1.2 를 정본으로 판단했는데(요구사항 29→21건, 시트 3개 없음), 사람이 확인해 보니 **내부용이 최신**이었다
   (내부용은 날짜를 고치지 않고 계속 갱신하는 작업본이었다).
   → 교훈: 같은 문서의 판이 둘 이상이면 이름(버전·날짜)으로 정본을 정하지 않는다. 시트별 셀 비교 결과를 보여 주고 **사람에게 정본을 확인**한다.
   확인 전까지는 기존 정본을 유지하고, 새 판 기준의 범위 변경(요구사항 삭제·번호 변경)을 slice 나 코드에 넣지 않는다.
   → 반영: stage0-ingest 의 개정판 절차에 "정본 확인" 을 넣었다.

## 2026-10-06 (실전 3회차) — 변환 slice 의 새 테이블과 전체 회귀 기준선

1. **레거시 변환은 기존 테이블을 그대로 쓴다(사용자 지시, 가장 비싼 사고).** 같은 용도의 테이블을 다른 이름으로 CREATE 하면
   이관 데이터와 운영 데이터가 갈라지고 다른 업무·이전 차수 코드와 어긋난다. 지침에 "근거: 테이블정의서 > 요구사항 > AS-IS DDL" 만 있어
   새로 설계해도 되는 것처럼 읽혔다. → 반영: stage2-backend B-1·reviewer 4항, migration-sql 3절, gate `asis-table-reuse`
   (AS-IS 테이블 재생성은 언제나 FAIL, AS-IS 가 있는 slice 의 새 테이블은 judgments 에 이름·근거가 없으면 FAIL, 이름이 비슷하면 WARN).
2. **전체 회귀에는 기존 실패가 섞인다.** 이전 차수 실패·구현 보류 spec·작업 환경 실패가 섞인 전체 실행을 test-evidence 가 통째로 막아
   slice 완료를 기록할 수 없었다. → 반영: `gates[].baseline` 기존 실패 목록 대조(새 실패만 FAIL).
3. **작업 환경 실패는 메서드가 아니라 클래스 단위로 적는다.** 환경 원인(loopback 연결 불가)은 클래스 초기화에서 나기도 하고 메서드마다 나기도 해
   메서드 이름 목록이 다음 실행에서 맞지 않았다.

## 2026-10-06 (실전 3회차) — AS-IS 에서 돌지 않던 코드를 살리는 사고

- 외부 문서보안 DB 회수 배치를 옮기면서 (1) 운영 상수로 꺼진 분기를 "상수째" 실행 코드로 옮기고 (2) AS-IS 원문 결함(CDATA 안 foreach, SET 중복)으로
  늘 실패하던 SQL 을 원문 그대로 실행 가능하게 두었다. 사용자 지적: "AS-IS 때부터 닿지 않던 코드는 운영에서도 쓰지 않는다는 뜻 - 살리면 AS-IS 에 없던 것을 살리는 꼴".
- 왜 놓쳤나: "레거시가 정본" 을 "레거시 코드를 빠짐없이 옮긴다" 로 읽었다. 정본은 코드 텍스트가 아니라 **운영에서 실제로 일어나던 동작**이다.
- → 반영: pipeline-core 12절·migration-sql 3절 - 실행되지 않던 코드·statement 는 TO-BE 파일 안 전체 주석으로 옮기고(AS-IS 파일:라인·이유·JD), 실행 여부는 설정·상수·예외 흐름까지 따라가 판정한다.
- 같은 회차 후속(사용자 지시): **판단으로 고친 것도 되돌린다.** 에이전트가 AS-IS 의 삭제·등록 권한 공백을 '결함 정상화' 로 고치고(삭제 작성자 선확인·쓰기 권한 선확인),
  화면 오류(NPE)를 빈 값으로, 코드 목록을 축소해 옮겼다. 사용자: "의미 없고 문제 많은 소스라도 일단 AS-IS 대로 전부 이관하고, 테스트 과정에서 빼거나 개선해 달라고 하면 그때 고친다 -
  차세대 변환 공통 원칙". → 반영: pipeline-core 12절(개선·정상화 금지, 예외는 방언 등가·승인 규약·사람 결정), stage2-backend B-2-1. 결함은 OI 로 올리고 검증 단계에 예약한다.

## 2026-10-06 (실전 3회차) — 기대 동작 테스트가 AS-IS 의 "값이 지나가는 길" 을 놓친 사례 2건

1. **정규식 치환이 값을 바꾼다.** 메일 템플릿을 `String.replaceAll("#키", 값)` 으로 채우는 AS-IS 에서, spec 이 담당자 값 `it's\1` 이 그대로 들어간다고 기대했다.
   실제 AS-IS 결과는 치환 문자열 규칙으로 역슬래시가 빠진 `it's1` 이었다. 구현은 AS-IS 그대로 옮겨 맞았고, 잠긴 spec 이 틀려 사람 잠금 해제가 한 번 더 필요했다.
2. **프레임워크가 입력을 먼저 가공한다.** 편집기 업로드에서 AS-IS 의 구 multipart resolver 는 원래 파일 이름의 마지막 `/`·`\` 앞을 떼었는데,
   새 프레임워크는 떼지 않는다. spec·구현 모두 컨트롤러 소스만 보고 원값을 썼고, Mock 요청 객체는 파싱을 거치지 않아 테스트로도 보이지 않았다(검토자가 라이브러리 소스 대조로 발견).
- 왜 놓쳤나: 기대값을 "소스 한 줄" 에서 가져왔고, 값이 지나가는 치환 함수·프레임워크 계층까지 따라가지 않았다.
- → 반영: behavior-spec-writer 작성 규칙에 "기대값은 AS-IS 가 실제로 내던 결과 - 정규식 치환·프레임워크 가공(resolver·필터·컨버터와 그 라이브러리 버전 소스)까지 확인" 을 넣었다.

## 2026-10-06 (실전 3회차) — 원격(모바일) 진행에서 사람 전용 명령이 진행을 멈춘다

- 사람 전용 명령(공통 계약 승인·spec 잠금 해제·기준 이미지 승인)은 `!` 셸 명령으로만 실행되게 훅이 막아 두었다.
  사용자가 모바일 원격제어로 진행하면 그 명령을 칠 수 없어 작업이 멈췄고, 사용자가 "python 명령을 쳐야 넘어가는 일이 없게" 를 지시했다.
- → 반영: 설정 `approvals.delegate_to_agent`(기본 false). 켜면 훅이 세 명령을 막지 않고, 오케스트레이터가 근거를 적어 실행하며
  `--by <위임자>(위임)` 으로 기록하고 실행할 때마다 사용자에게 보고한다(pipeline-core §18, CLAUDE.md).
- 참고: 이 변경은 Claude Code 자동 모드가 "자기 통제 장치 수정" 으로 막는다. 사용자가 권한 모드를 확인 모드로 바꾼 뒤 진행했다.

## 2026-10-06 (실전 3회차) — 공유 브랜치를 cherry-pick 으로만 받으면 최종 구성과 갈라진다 / 이전 차수 사람 결정을 되돌린 사고

1. **공유 통합 브랜치는 병합으로 받는다.** 다른 작업 환경이 올린 커밋을 cherry-pick 으로만 받아 오자 두 브랜치에 공통 조상 없는 같은 내용이 쌓였고,
   전체 병합 때 add/add 충돌이 20개 나왔다. 환경 이름(pom version·DB 이름·테스트 스키마·실행 설정)도 로컬만 달라 로컬 빌드가 공유 브랜치 최종 구성과 달랐다(사용자 지적).
   → 교훈: 공유 브랜치는 한 번 진짜 병합해 이력을 합치고 이후 병합으로만 동기화한다. 로컬 전용 환경 분리는 추적하지 않는 실행 설정·실행 인자로 두고 저장소 파일은 공유 브랜치와 같게 둔다.
   또 `git fetch origin <branch>` 는 설정에 따라 추적 브랜치를 갱신하지 않으므로 명시 refspec 으로 받고 `ls-remote` 해시와 대조한다(실측: 새 커밋 없음으로 잘못 보고).
2. **이전 차수에서 사람이 고친 동작은 되돌리지 않는다.** "AS-IS 그대로" 를 적용해 2차가 사람 판단으로 LEFT JOIN 으로 바꾼 코드 목록 SQL 을 AS-IS 내부 조인으로 되돌렸다가 취소했다.
   → 반영: pipeline-core 12절 - 이전 차수 사람 결정은 "사람 결정" 예외이고, 이전 차수 코드에서 가져온 공통은 AS-IS 와 다르게 바꾼 이유를 먼저 찾는다.

## 2026-10-06 (실전 3회차) — 병렬 작업 트리·변이 원복·잠금 개수

1. **같은 target 을 두 에이전트가 동시에 빌드하지 않게 작업 트리를 나눈다.** 업무 구현과 공통 이관을 병행하려고 target 에 두 번째 git worktree(별도 브랜치)를 만들고
   DB 테스트 스키마도 따로 썼다(시험 스키마 이름을 정하는 시스템 속성으로 `..._test` 를 트리마다 다르게). 그때 새 트리는 autocrlf 로 줄바꿈만 다른 잠긴 spec 이 되어 `spec_lock lock` 이 막혔다
   → 반영: lock 도 verify 처럼 줄바꿈 차이를 같은 파일로 본다.
2. **변이 원복 뒤 증분 컴파일이 변형을 유지한다.** `cp -p` 로 되돌리자 파일 시각이 과거라 컴파일이 건너뛰어 거짓 실패가 났다 → 반영: equivalence-verifier - 원복 파일 touch 또는 결함마다 새 트리.
3. **잠금 매니페스트의 test_count 는 @Test 메서드 수다.** 매개변수화 테스트는 실행 수가 더 많다(109 대 122). 게이트·보고의 실행 수는 결과 XML testcase 로 센다.

## 2026-10-07 (실전 3회차) — 세션이 통째로 사라져 대화 기억에 기댄 진행이 끊긴다

- 데스크톱 세션이 몇 시간 뒤 "디스크에서 세션을 찾을 수 없음" 으로 사라지는 일이 반복됐다. 확인해 보니 메인 대화 기록 파일(.jsonl)이
  세션 시작부터 디스크에 생기지 않았고(서브에이전트 meta·tool-results 는 생김), 앱이 메모리로만 보여 주다가 재시작·재로드 때 잃었다.
- 왜 문제였나: HANDOFF 는 "단계 끝·사람 결정" 때만 갱신하게 되어 있어, 단계 중간(서브에이전트 진행·미커밋 변경·다음 순서)이 대화에만 있었다.
- → 반영: CLAUDE.md·pipeline-core §1-0·templates/HANDOFF.md - HANDOFF 를 작업 단위 끝·긴 작업 시작 전·응답을 마치기 전마다 갱신하고,
  "현재 작업 / 다음 순서" 에 갱신 시각·진행 중 서브에이전트·미커밋 변경·막힌 이유를 적는다. 세션이 지금 끊겨도 HANDOFF·state.yaml 만으로 이어 가게 둔다.
- 원인 확정(같은 날): 사용자 환경변수 `CLAUDE_CODE_SKIP_PROMPT_HISTORY=1` 이 대화 기록 저장을 끄고 있었다. 지우고 앱을 재시작하자 .jsonl 이 생겼다.
  세션이 사라지는 증상이 보이면 먼저 이 변수와 `~/.claude/projects/<프로젝트>/<세션>.jsonl` 생성 여부를 본다.

## 2026-10-07 (실전 3회차) — 레거시 화면 템플릿이 4단계 근거에서 빠져 있었다 / 기존 앱 위의 4단계 골격

1. **migration 의 4단계 근거가 피그마·스토리보드만이었다.** 이관 화면은 디자인이 아직 없고, 필드·검증 문구·행 이동 분기·화면 간 차이는 레거시 화면 템플릿(FTL)과 그 안 스크립트에만 있었다.
   실험: 같은 목록 4화면을 (가) 템플릿 근거로 변환, (나) 다른 팀이 템플릿 없이 서버가 주는 이동 주소에 맡겨 변환한 판으로 나눠, 템플릿만 읽고 만든 항목표(253항목)로 독립 채점했다.
   판정 가능 항목의 맞음 비율이 (가) 약 90%, (나) 약 50% - 차이는 행 이동 분기·표시 가공·검색 필드에 몰렸다.
   → 반영: stage4-frontend §B-0(템플릿 근거·우선순위·도달 불가 시안·스크립트 결함 보존), §D-2 reviewer 대조, /stage4 전달 항목, frontend-developer·behavior-spec-writer 입력.
   템플릿만 읽은 항목표를 먼저 만들어 spec·검토·5단계 대조가 같은 기준을 쓰게 한다.
2. **기존 앱(brownfield)에 테스트·린트 도구가 없으면 slice 가 격리 하네스로 우회한다.** 골격 없이 slice 를 시작해 slice 폴더 안 별도 package.json 으로 vitest·eslint 를 돌렸다 - slice 마다 복제될 우회다.
   → 반영: stage4-frontend §A-0 - 기존 앱이 있으면 빠진 것만 devDependencies·설정으로 더하는 것이 골격이고, 린트 강제 범위는 실측으로 정한다.
3. **다른 팀 변환본은 재현율보다 결합 비용으로 판정한다.** 화면 수가 많아도 API 규약·응답 봉투가 다르면(이번 실측 호환 0건) 데이터 계층 전부를 다시 써야 한다.
   가져올지 판단할 때 화면 재현 점수와 함께 "현 백엔드에 그대로 붙는 호출 수" 를 먼저 센다. 코드는 대조 자료로 쓰고 순수 로직만 발췌하는 것이 기본값이다.

## 2026-10-07 (실전 3회차) — 공유 브랜치 push 직전 경합·병렬 공통 트리 게이트·개인 로컬 이름 누출

1. **push 직전에 다시 받아도, 검사하는 사이 공유 브랜치가 또 움직인다.** 업로드 브랜치에서 설치·전체 테스트·e2e 를 도는 몇 분 사이 다른 개발자가 공유 브랜치에 커밋해 push 가 빨리감기 거절됐다.
   → 거절되면 강제 push 하지 않고, 백업 브랜치를 남긴 뒤 새 원격 위에 우리 커밋만 다시 cherry-pick 하고, 새로 들어온 커밋이 우리 파일과 겹치지 않으면 3차 확인 후 바로 push 한다(겹치면 게이트 재실행).
2. **병렬 공통 트리에서 돈 서브에이전트 레포트는 `gate.py check` 가 config target_dir(주 작업 트리)을 보고 FAIL 을 낸다**(spec-lock·test-evidence·repo-consistency). spec_lock 은 `--target` 이 있지만 gate check 는 없다.
   → 공통 트리 산출의 게이트는 그 커밋을 주 작업 트리에 병합한 뒤 그 트리에서 다시 돌린다. 도구 개선 후보: gate check `--target`.
3. **개인 로컬 설정 이름(로컬 DB·로컬 실행 구성)이 공유 규약 문서에 들어갔다.** 4단계 골격 에이전트가 실측한 기동 명령을 규약에 그대로 적었다. 업로드 전 로컬 이름 검사가 잡았다.
   → 규약·README 처럼 공유되는 문서에는 `<로컬 DB>` 같은 자리표시로 쓴다. 로컬 이름 검사는 push 전 검사 목록에 계속 둔다.

## 2026-10-07 (실전 3회차) — 공통 계약 재계산이 이관 필드를 지웠다 - 병합 보존 규칙

1. **`common_contract.py init` 재실행(이전 계약 병합)이 이미 이관(ported)된 항목의 필드를 지웠다.** 병합이 정해진 사람 필드 목록(HUMAN_KEYS)만 옮겨서 스키마에 없는 이관 기록(`tobe_location` 등)이 사라졌고,
   도달 slice 가 없는 항목은 새 제안에 module 이 없어 사람이 정한 `module` 도 잃었으며, 같은 note 꼬리말이 재실행마다 한 번씩 더 붙었다. 시험 실행(scratch)에서 필드별 대조로 잡았다.
   → 병합은 "행렬에서 다시 계산되는 필드(used_by·usage·suggestion·modules·suggested_module 등)만 새로 쓰고 나머지는 이전 값을 그대로 둔다" 로 뒤집었다(모르는 필드도 보존).
   module 은 사람이 바꿨거나 이미 이관됐거나 새 제안이 없으면 보존하고, note 꼬리말은 같은 것이 있으면 붙이지 않는다. 회귀 테스트: 같은 init 을 두 번 돌려 필드 보존·꼬리말 1회.
2. **재계산은 실제 파일을 덮기 전에 계약을 백업하고 id 별 필드 대조로 "사람·이관 필드 변경 0" 을 확인한 뒤 승인한다.** 바뀌어도 되는 것은 행렬 파생 필드(사용처·제안)와 신규 항목뿐이다.
   init 을 한 번 더 돌려 내용이 같고 승인이 유지되는지(멱등)도 본다.
3. **범위 밖 처리기를 slice 로 옮기면 그 처리기가 쓰는 외부 데이터소스 statement 가 공통 계약 신규 항목으로 들어온다.** 이때 데이터소스 지도의 role(out_of_scope) 과 계약의 datasource·dialect 표시를 같은 회차에 맞춰야
   업무 변환이 외부 statement 를 대상 DB 방언으로 바꾸지 않는다.

## 2026-10-07 (실전 3회차) — 병렬 작업 트리 병합 뒤 게이트·동시성 시험·판별력 원복

1. **공통 작업 트리를 target_dir 에 병합한 뒤 업무 slice 레포트를 다시 게이트에 넣으면 repo-consistency 가 공통 파일 "누락" 으로 FAIL 했다.** 기재 HEAD 가 현재 HEAD 의 조상(정상 진행)이라고 인정하면서도
   변경 파일 대조는 `base...HEAD` 로 해서, 그 뒤 병합된 다른 트리의 커밋까지 이 단계 변경으로 셌다.
   → 기재 HEAD 이후 커밋이 쌓였으면 대조 끝점을 기재 HEAD 로 둔다(`base...<기재 head>`). 레포트는 쓰인 시점의 변경만 책임진다.
2. **`common_contract.py init` 이 이관 제외 목록에서 owner=common 으로 승격된 항목에 module 을 채우지 않아 validate 가 거부했다.** 사람이 손으로 채웠다 - 도구 보강 후보.
3. **PK 한 건 `SELECT ... FOR UPDATE` 대기는 MySQL 8.4 에서 INNODB_TRX 의 LOCK WAIT 로 보이지 않고 PROCESSLIST state 로만 보일 때가 있다.** 동시성 시험의 "기다리는 중" 단언은 두 곳을 함께 본다.
4. **판별력 확인 뒤 `cp -p` 로 소스를 되돌리면 옛 mtime 때문에 Maven 이 다시 컴파일하지 않아 결함 넣은 클래스로 게이트를 돈다.** 원복은 `git checkout`/`git stash` 로 하거나 원복 뒤 `touch` 하고 다시 빌드한 실행 결과만 게이트 수치로 쓴다.

## 2026-10-08 (실전 3회차) — 공유 브랜치 Flyway 번호 순서·오프라인 빌드의 지운 리소스·PC 재시작 뒤 시험 DB

1. **병렬 작업 트리가 각자 Flyway 번호를 잡으면, 공유 브랜치에 먼저 올라간 큰 번호 뒤로 작은 번호가 늦게 올라가 outOfOrder 없는 수동 migrate 에서 무시된다.** 
   → 공유 브랜치에 올리기 전에 그 브랜치의 최대 번호를 보고, 아직 공유 DB 에 적용되지 않은 자기 트리의 마이그레이션을 그 뒤 번호로 옮긴다(git mv). 시험 스키마 이력은 version·script·checksum 을 함께 고친다.
2. **`mvn -o` 빌드는 소스에서 지운(이름 바꾼) 리소스를 target/classes 에서 지우지 않는다.** 옛 마이그레이션 파일이 classpath 에 남아 시험 스키마에 다시 적용됐다.
   → 마이그레이션·Mapper XML 을 옮기거나 지운 뒤에는 clean 하거나 target 의 옛 파일을 지우고 돌린다. 그 브랜치를 병합한 다른 트리도 같다.
3. **PC 재시작 뒤 Docker 가 꺼져 시험 DB 연결 거부로 전 모듈 회귀가 수백 건 실패했다.** 원인을 보기 전에는 결함처럼 보인다.
   → 세션 시작 루틴과 긴 시험 실행 전에 시험 DB 컨테이너 상태(`docker ps`)를 확인한다. 연결 거부 실패가 섞인 실행은 게이트 근거로 쓰지 않고 다시 돌린다.
4. **에이전트(오케스트레이터)가 시각을 짐작으로 적어 실제보다 1시간 앞선 기록이 쌓였다.** 게이트가 미래 시각으로 막아 드러났다.
   → 기록·레포트 시각은 항상 `tools/kst_now.py` 실측값으로 적는다.

## 2026-10-08 (실전 3회차) — 브라우저 검증의 빌드 시점·시간 의존 테스트·서브에이전트 .md 쓰기

1. **e2e 가 `vite preview`(빌드된 dist)를 띄우면, 병합 뒤 다시 빌드하지 않은 dist 로 화면을 판정한다.** 수정 전 화면이 찍혀 기준 이미지 크기가 달라 실패했다.
   → 병합·수정 뒤 e2e 전에 앱을 다시 빌드한다(ui-verifier·frontend-developer 절차 첫 줄). 실패가 크기 몇 픽셀 차이면 빌드 시각부터 본다.
2. **지연 응답을 고정 시간으로 흉내 낸 단위 테스트가 단독 실행은 통과하고 부하 큰 전체 실행에서 흔들렸다.**
   → 비동기 순서를 확인하는 테스트는 시간 대신 테스트가 직접 푸는 지연 프라미스(deferred)로 순서를 정한다. 전체 실행을 두 번 돌려 확인한다.
3. **서브에이전트가 `.md` 파일(화면 정의서·레포트)을 쓰지 못하는 경우가 있었다**(도구 정책). 본문을 보고에 싣게 하고 오케스트레이터가 저장·커밋한다.
4. **다른 개발자가 같은 AS-IS 엔드포인트를 따로 옮기면 TO-BE 에서 같은 경로가 두 번 매핑돼 기동이 깨진다.** 공유 브랜치 병합 직후 전 모듈 회귀에 경로 충돌 검사가 있어 잡혔다.
   → 업무 slice 를 공유 브랜치에 올리기 전 회귀에 "같은 경로 매핑 0" 검사를 두고, 겹치면 공통 계약 소유자 기준으로 하나만 남긴다(사람 결정·상대 담당 협의).
5. **완료 기록 훅은 그 slice·단계의 가장 최근 레포트로 게이트를 본다.** 완료 레포트 뒤에 `ingest_result` 가 만든 원장 레포트(서브에이전트 게이트 kind 그대로)가 더 최근이면 완료 기록이 막혔다.
   → 완료 레포트는 그 단계의 마지막 원장 레포트보다 뒤에 쓴다(또는 마지막 ingest 뒤 다시 쓴다).

## 2026-10-08 (실전 3회차) — 작업 트리 fetch 설정·결과 JSON 과 보고 블록·기반 브랜치의 프로파일 변경

1. **업로드 작업 트리의 `remote.origin.fetch` 에 공유 브랜치가 빠져 있어 `git fetch` 가 그 브랜치의 원격 추적 참조를 갱신하지 않았다.** "원격보다 앞섬·뒤처짐 0" 으로 보였는데 push 가 거부돼서야 다른 개발자 커밋이 있음을 알았다.
   → push 직전 재동기화는 `git ls-remote origin <브랜치>` 값과 원격 추적 참조를 대조하거나 `git fetch origin +refs/heads/<브랜치>:refs/remotes/origin/<브랜치>` 로 명시해 받는다. 작업 트리를 만들 때 fetch 설정에 공유 브랜치를 넣는다.
2. **서브에이전트가 따로 저장한 결과 JSON 파일에 보고 끝 `pa-agent-result` 블록의 open_items·judgments 가 빠져 있었다.** 그 파일로 `ingest_result` 를 돌리면 확인 필요 항목·판단이 원장에 들어가지 않는다(빈 원장 레포트만 생김).
   → 원장 반영은 보고 끝 블록을 기준으로 한다. 파일을 쓸 때는 블록과 같은지(항목 수) 먼저 비교한다.
3. **기반(유지보수) 브랜치가 기존 프로파일 이름의 뜻을 바꿨다**(로컬 DB 를 가리키던 `local` 이 공용 개발 DB 로, 로컬 DB 는 새 프로파일로). 병합만 하면 개인 실행 구성이 조용히 다른 DB 로 붙는다.
   → 기반 브랜치를 병합할 때 설정 파일(`application-*.yml`·데이터소스 설정) 변경을 따로 보고, 개인 실행 구성(로컬 전용 커밋·무시 파일)을 새 프로파일에 맞춘다. 공유 브랜치에는 올리지 않는다.
4. **단계 사이 인계 내용(다음 에이전트가 확인할 기대 동작 목록)이 앞 에이전트의 보고 본문에만 있고 파일 레포트에는 없었다.** 다음 에이전트에게 "레포트의 목록" 으로 가리켰더니 찾지 못해 계약·판단으로 다시 세웠다.
   → 인계 목록은 오케스트레이터가 다음 프롬프트에 그대로 옮겨 싣는다(파일을 가리킬 때는 그 내용이 실제로 파일에 있는지 먼저 확인한다).
5. **기록 시각을 짐작으로 적는 실수가 교훈으로 적힌 뒤에도 같은 날 되풀이됐다**(인계 기록에 실제보다 30분 앞선 시각). 규칙만으로는 막지 못했다.
   → 인계 기록 줄은 `tools/handoff.py note` 가 KST 실측 시각을 붙여 넣는다. 시각을 사람이 타이핑하는 경로를 없앤다.
6. **긴 회귀 도중 시험 DB 컨테이너가 내려가 수백 건이 연결 실패로 바뀌었다**(PC 재시작이 아니라 세션 중간). 결과만 보면 대량 회귀처럼 보인다.
   → 기준선 대조에서 새 실패가 수십 건 이상 한꺼번에 나오면 먼저 원인 예외(연결 거부·컨텍스트 적재 실패)와 `docker ps` 를 본다. 그 실행은 근거로 쓰지 않고 DB 를 살린 뒤 다시 돌린다.
7. **병렬 작업 트리에서 잠근 spec 을 `--target` 없이 확인해 기본 target_dir(다른 트리)과 비교하는 바람에 "잠긴 spec 이 수정됐다" 는 거짓 경보가 났다.**
   → `spec_lock.py lock` 이 잠근 트리를 매니페스트(`locked_target`)에 적고, `verify` 가 `--target` 없이 다른 트리와 비교해 문제가 나오면 그 사실을 함께 알린다. 서브에이전트 지시에는 항상 `--target <작업 트리>` 를 넣는다.
8. **서브에이전트가 결과 블록의 게이트 kind 를 제멋대로(static·browser·quality·spec-lock) 쓰거나 smoke 에 개수를 빼서, 오케스트레이터가 레포트를 만들 때마다 gate-proof·test-evidence 가 막혔다.**
   → pipeline-core 결과 블록 예시 옆에 허용 kind 와 test·smoke·scan 의 필수 칸(test_count·results), 개수 없는 확인은 other 로 쓴다는 규칙을 적었다.
9. **통합 시험 도구가 개인 작업 트리의 시험 스키마 이름과 공용 DB 주소를 기본값·문서에 박아, 공유 브랜치 업로드 전 검사에서 걸렸다.**
   → integration-tester 지침에 "개인 환경 값은 환경변수로 받고 기본값은 일반 이름" 을 넣었다.
10. **병렬 작업 트리에서 일한 결과를 `ingest_result` 로 옮기자 pa-meta repo 가 기본 target_dir(다른 트리)로 적혀, 검토자가 "증거를 재현할 수 없다" 고 지적했다.**
    → `ingest_result.py` 가 결과 블록의 `repo.dir`·`target_dir` 이나 `--target`/`--base` 로 실제 작업 트리를 적는다. 서브에이전트 결과 블록에 `repo.dir`·`base` 를 넣게 지시한다.
11. **결과 블록의 open_items 하나가 허용되지 않는 axis 값을 가져 `ingest_result` 가 앞 항목만 채번하고 멈췄고, 고쳐 다시 돌리자 같은 확인 필요 항목이 두 번 채번됐다.**
    → `ingest_result` 의 채번 전 형식 검사에 axis 를 넣었다(검사를 통과하지 못하면 아무것도 채번하지 않는다). 이미 채번된 항목은 결과 JSON 에 id 를 적은 뒤 다시 돌린다.
12. **오케스트레이터가 장부(open-items·judgments)를 도구가 아닌 스크립트로 직접 고치는 동안 병렬 에이전트가 같은 파일을 읽어 YAML 해석 오류가 났다.** 도구(gate.py oi·judgment.py·rr.py)는 잠금과 원자적 쓰기를 쓰지만 직접 쓰기는 그렇지 않다.
    → 장부는 도구로만 고친다(상태·메모는 `oi set --note`·`judgment.py set --note`). 도구에 없는 정정이 꼭 필요하면 병렬 에이전트가 없을 때 한다.
13. **(같은 날) standalone MockMvc 단위 시험에서 400 이던 잘못된 입력이 실서버에서는 500 이었다**(공통 예외 처리기가 빠진 구성). 컨트롤러 단위 시험의 오류 상태는 실서버 축에서 다시 본다.
14. **"`mvn install` 금지" 를 지시했는데도 공통 에이전트가 `clean install` 로 전 모듈을 돌려 로컬 Maven 저장소에 한 작업 트리의 공통 산출물이 올라갔다.** 그 뒤 다른 트리에서 `-pl user` 만 주고 빌드하면 저장소의 그 jar 를 공통으로 쓴다(같은 날 한 번 실측).
    → 병렬 작업 트리에서는 항상 `-pl <모듈> -am`(또는 전 모듈)으로 빌드한다. 에이전트 지침의 빌드 명령 예시에 `install` 을 쓰지 않고, 금지 이유(다른 트리 오염)를 함께 적는다.
15. **(10-09) 다른 개발자 slice 를 동등성 검증하자, 잠긴 spec 이 가짜 Mapper 로만 검증해 Mapper XML 에 넣은 결함(조건·정렬·상수) 6건을 하나도 잡지 못했다.** 서비스·컨트롤러 결함 15건은 모두 잡았다. SQL 규칙은 비잠금 DB 테스트만 지켰고, 그 테스트는 DB 시험 옵션이 없으면 건너뛴다. 정렬 결함 1건은 시드의 코드값 순서와 정렬 키 순서가 같아 DB 테스트로도 살아남았다.
    → behavior-spec-writer: SQL 이 정하는 규칙은 테스트 DB spec 으로 쓰고, 정렬 시드는 다른 후보 키 순서와 어긋나게 넣는다. equivalence-verifier: 결함 주입 표본에 영속 계층을 최소 1개 넣는다.
16. **(같은 검증) AS-IS 는 컨트롤러에서 직접 갱신을 실행해 트랜잭션 AOP(서비스 구현체 pointcut) 밖이라 자동 커밋이었는데, TO-BE 는 서비스 `@Transactional` 로 갱신과 이력을 함께 되돌렸다.** 잠긴 spec 이름과 Javadoc 은 "같다" 고 적었지만 가짜 Mapper 라 되돌림을 확인하지도 않았다.
    → behavior-spec-writer: AS-IS 트랜잭션 pointcut 범위를 확인하고, 경계가 바뀌면 `[의미차이:TX_BOUNDARY]` 로 따로 단언한다.
17. **(10-09) 공통 복제 검사가 공유 Mapper 폴더 하나만 보아, 데이터소스별 폴더에 있는 외부 공통 statement 를 업무 Mapper 가 복제해도 잡지 못했다.**
    → `tobe.shared_mapper_dir` 가 목록과 glob(`.../mapper-ds*/common`)을 받는다(`common_contract.shared_mapper_dirs`). gate 의 소유 범위 검사도 같은 값을 쓴다.
18. **(10-09) 병렬 작업 트리에서 만든 레포트를 `gate.py check` 하자 설정의 기본 트리를 검사해, 그 트리에 없는 잠긴 spec 을 "삭제됐다", 정리 전 파일의 이모지를 FAIL 로 냈다.**
    → `gate.py check` 가 `--target` > 레포트 pa-meta `repo.dir`(폴더가 있을 때) > 설정 target_dir 순으로 검사 트리를 정한다.
19. **(같은 날) 회귀 게이트의 `baseline` 에 기준선 결과 사본 폴더를 적자 게이트가 PermissionError 로 멈췄고, 기존 실패 34건 때문에 회귀 게이트를 result=done 으로 적을 수 없었다(gate-proof 가 실패 수만 봄).**
    → `_junit.load_baseline` 이 폴더를 받으면 그 안 XML 의 실패 testcase 이름을 기준선으로 쓴다. gate-proof 는 baseline 이 적힌 게이트의 실패 수를 막지 않고, 기준선 밖 실패 판정은 test-evidence 가 결과 파일로 한다.
20. **(같은 날) 다른 담당자 slice 12개 동등성 검증에서 잠긴 spec 의 SQL 결함 검출이 0/33 이었고, 컨트롤러 -> 서비스 값 전달 결함도 3차까지는 살아남았다. 엑셀 범위(AS-IS 전체 행 vs TO-BE 한 쪽)는 화면마다 AS-IS 가 달랐다.**
    → 15·16항 지침(SQL 규칙은 DB spec, TX 경계 확인) 위에, spec 은 HTTP 계층에서 컨트롤러가 서비스로 넘기는 값까지 단언하고, 엑셀·다운로드는 AS-IS 의 페이지 구간 계산 호출 여부를 직접 대조한다.
21. **(10-09) 결함 주입용 별도 작업 트리를 사용자 임시 폴더 아래에 만들자, 임시 폴더를 허용 루트로 보는 다운로드 경로 spec 이 거짓 실패했다** - 시험의 가드는 toAbsolutePath(8.3 짧은 이름), 구현은 toRealPath(긴 이름)로 비교했다.
    → equivalence-verifier: 별도 작업 트리는 java.io.tmpdir 밖에 만든다. 경로 비교 시험·구현은 같은 정규화(toRealPath)를 쓴다.
22. **(같은 날) 내 slice 자체 점검에서도 다른 담당자와 같은 약점이 나왔다** - 잠긴 spec 의 SQL 결함 검출 report-channel 0/3·dashboard 2/3·my-inquiry 1/3·ext-integration-legacy 0/3·common-file 0/3, 시험이 트랜잭션을 대신 열어(TransactionTemplate·기반 클래스 @Transactional) 트랜잭션 경계 결함도 놓쳤다. 15·16항 지침 이전에 잠근 spec 이다.
    → 지침 개정 이전에 잠근 spec 은 영속 계층·트랜잭션 결함 주입으로 다시 재고, 부족하면 잠금 해제(위임) 뒤 추가만 하는 보강 회차를 둔다. 트랜잭션 경계 spec 은 시험이 트랜잭션을 열지 않는 상태(NOT_SUPPORTED)에서 프록시를 거쳐 부른다.
23. **(10-09) 회귀 실행이 `clean` 단계에서 실패(다른 프로세스가 target 파일을 잡음)했는데 결과 대조 도구가 남아 있던 이전 실행의 결과 파일로 "새 실패 0" 을 냈다.** 실패 수는 그럴듯했고 총건수만 평소보다 적었다.
    → 회귀 결과를 대조하기 전에 빌드 도구의 종료 코드와 BUILD SUCCESS 를 먼저 확인한다(`-Dmaven.test.failure.ignore` 를 써도 빌드 실패는 종료 코드 1). 총건수가 직전 실행과 크게 다르면 대조 결과를 쓰지 않는다. gate 의 결과 파일 시각 검사(started_at)가 이 경우를 잡는다.
