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
