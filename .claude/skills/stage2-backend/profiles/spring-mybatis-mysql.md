# Backend 프로필: spring-mybatis-mysql

`config/project.yaml → stack.backend.profile: spring-mybatis-mysql` 일 때 적용한다. 버전은 config 값을 우선한다.

## 기본 의존성 (Gradle 기준)
- 버전 기준: Spring Boot **3.4.x**(OSS 지원 중인 라인) + springdoc **2.8.x** + `springdoc.api-docs.version: openapi_3_0`(2.8 기본 3.1 은 계약 형식을 바꿈) + `dependencyLocking { lockAllConfigurations() }` 와 `gradle.lockfile` 커밋. Boot 3.4 부터 `@MockBean` 대신 `@MockitoBean`.
- 인증·회원 상태처럼 항상 현재 값이어야 하는 조회는 Mapper XML 에 `flushCache="true" useCache="false"` — MyBatis 1차 캐시가 트랜잭션 안에서 stale 행을 돌려준다(테스트에서 재현).
- `X-Forwarded-For` 는 신뢰 프록시 홉 수 기준 **마지막 값**(1홉이면 last) 을 쓴다. 첫 값은 클라이언트가 임의로 넣을 수 있다(`$proxy_add_x_forwarded_for` 는 뒤에 덧붙임).
- 골격 기본: HikariCP `data-source-properties.{connectTimeout=5000,socketTimeout=12000}`(URL 파라미터가 아니라 프로퍼티 — `@DynamicPropertySource` 로 URL 을 바꿔도 적용되게), `validation-timeout=3000`, MyBatis `default-statement-timeout=10`. 실측: DB 무응답 시 요청 실패까지 ≈ `socketTimeout × 2`(Connector/J 재시도) — 10초 이내 목표면 socket ≤5초가 필요해 정상 쿼리와 충돌하므로 12초(≈24초 상한)를 방어값으로. statement timeout 은 무응답에는 무효(KILL QUERY 용 2차 커넥션도 막힘). MyBatis-Spring 예외 변환기의 `SQLErrorCodesFactory` 를 기동 시 선적재(첫 예외 때 메타데이터 커넥션 대기 방지) — DB 응답 정지 시 요청 스레드 무기한 대기 방지. `ErrorController` 를 구현해 컨테이너 오류 디스패치(`/error`, 요청 방화벽 거부)도 `ApiResponse` JSON 으로. `Auditable.markCreated/markUpdated` 는 `Clock` 빈에서 시각을 받는다(`LocalDateTime.now()` 금지).
- 보안 골격 기본 포함: 인증 필터의 회원 상태 조회(비활성·잠금 즉시 401), 로그인 IP rate limit(설정으로 on/off — 통합 테스트 환경은 off), 상태 변경 요청 Origin/Referer 검증(nginx `proxy_set_header Host $host` 필수 — 배포 가이드), 페이징 `page` 상한.
- spring-boot-starter-web, -validation, -security(인증 골격), -actuator
- mybatis-spring-boot-starter, mysql-connector-j, flyway-core + flyway-mysql
- springdoc-openapi-starter-webmvc-ui (계약 생성·확인용)
- 테스트: spring-boot-starter-test, mybatis-spring-boot-starter-test, testcontainers(mysql) — 도커가 없으면 H2 `MODE=MySQL` 로 폴백하고 레포트에 명시
  - **Docker Engine 29+ (API 1.55) 는 testcontainers ≥ 1.21.4 필요.** Boot 3.3 BOM 의 1.19.x 는 `NpipeSocketClientProviderStrategy ... Status 400` 으로 실패 → `gradle.properties` 또는 `ext["testcontainers.version"]="1.21.4"` 로 상향
  - 기본 실행은 H2(빠름), `-Pmysql` 프로퍼티로 testcontainers 프로파일 전환하는 구성을 권장
- lombok (선택, brief 컨벤션에 따름)

- 골격 `build.gradle` test 태스크: `systemProperty 'file.encoding','UTF-8'`, `'stdout.encoding','UTF-8'`, `jvmArgs '-Dsun.stdout.encoding=UTF-8'` — Windows 에서 테스트 로그·XML 의 한글이 깨지지 않게.

## 패키지 구조
```
<base_package>/
├── common/
│   ├── response/   ApiResponse<T>, PageResponse<T>
│   ├── exception/  ErrorCode(인터페이스) + CommonErrorCode(enum), BusinessException, GlobalExceptionHandler
│   │               (400 검증·404·405·406 NotAcceptable·415·500 을 모두 공통 포맷으로; 406 을 500 으로 뭉개지 않는다)
│   ├── config/     WebConfig, MyBatisConfig, SecurityConfig, OpenApiConfig, ClockConfig(Clock 빈 — 시간대는 config/환경정보의 값으로 고정, slice 는 이 빈만 주입)
│   ├── security/   JWT 필터·인증 유틸 (brief 에 인증 방식이 있을 때)
│   ├── logging/    요청/응답 로깅 필터, MDC 트레이스 ID
│   └── util/
└── <slice>/
    ├── controller/ <Slice>Controller
    ├── service/    <Slice>Service (인터페이스 없이 클래스 우선; 다른 slice 가 호출할 때만 인터페이스 분리)
    ├── mapper/     <Entity>Mapper (인터페이스) + resources/mapper/<slice>/<Entity>Mapper.xml
    ├── dto/        요청 <Xxx>Request, 응답 <Xxx>Response
    └── domain/     <Entity> (테이블 매핑 POJO)
```
slice id 의 하이픈은 패키지에서 제거한다 (`common-auth` → `commonauth`).

## 문서화·로깅 규약 (stage2-backend §B-7 의 이 스택 구현)
- 골격 `common/logging/`: `TraceIdFilter extends OncePerRequestFilter`(최상위 순서, 요청 헤더 `X-Trace-Id` 가 있으면 이어받고 없으면 UUID, `MDC.put("traceId", …)`, 응답 헤더 설정, `finally { MDC.clear(); }`), `MaskingUtils`(이름·연락처·이메일·계좌 마스킹).
- `src/main/resources/logback-spring.xml`: 패턴 `%d{yyyy-MM-dd HH:mm:ss.SSS} [%X{traceId:-}] %-5level %logger{36} - %msg%n`, `<springProfile name="local,dev">` DEBUG(`<base_package>` 패키지), `<springProfile name="prod">` INFO + `RollingFileAppender`(일 단위·보존 30일). SQL 바인딩 로그는 local/dev 만.
- 로거는 lombok `@Slf4j`(brief 컨벤션이 lombok 금지면 `private static final Logger log = LoggerFactory.getLogger(X.class)`).
- `GlobalExceptionHandler`: `BusinessException` → `log.warn("업무 예외 code={} msg={}", code, msg)`(스택 없음), 그 밖의 예외 → `log.error("처리되지 않은 예외", e)`(스택 포함). 응답 본문에는 스택·SQL 을 싣지 않는다.
- Mapper XML 머리 예:
  ```xml
  <!-- 공지사항 Mapper · 테이블 tb_notice, tb_notice_file · slice notice -->
  <mapper namespace="...NoticeMapper">
      <!-- 공지 목록 검색 (REQ-012: 제목·작성자 부분 일치, 게시 기간 내만) -->
      <select id="searchNotices" ...>
  ```
- Javadoc 은 `@param`·`@return` 을 빠뜨리지 않는다(javadoc 도구 경고 0 이 목표). Controller 메서드 Javadoc 은 `@Operation(summary)` 와 같은 뜻으로 쓴다.

## 규약
- 응답: 성공 `{ "success": true, "data": ..., "error": null }`, 실패 `{ "success": false, "data": null, "error": { "code": "ORDER_001", "message": "..." } }`.
- 에러 코드: `<SLICE>_<3자리>`. `ErrorCode` enum 에 HTTP 상태를 함께 정의.
- 페이징: 요청 `page`(1부터)·`size`, 응답 `PageResponse { items, page, size, total }`.
- 상태 코드: 생성 `POST` 는 **201** 로 통일(`@ResponseStatus(CREATED)`), 행위 동사 경로(`/return`, `/extend`)는 200. slice 마다 달라지지 않도록 CONVENTIONS 에 명시.
- LIKE 검색: 사용자 입력의 `%`·`_`·이스케이프 문자를 이스케이프하고 `LIKE ... ESCAPE '!'` 로 — 골격 `common/util/SqlLike.escape()` 제공, Mapper XML 은 `CONCAT('%', #{kw}, '%')` 에 이스케이프된 값만 바인딩.
  이스케이프 문자는 **`!`** 를 쓴다: 역슬래시는 `ESCAPE '\\'`(두 글자) 가 MySQL 만, `ESCAPE '\'`(한 글자) 가 H2 만 동작해 같은 XML 을 테스트/운영에 쓸 수 없다(실측).
- 검색 조건 DTO 의 문자열 필드는 골격이 제공하는 trim 처리(예: `@InitBinder` `StringTrimmerEditor` 또는 DTO setter)로 **전 slice 동일**하게 앞뒤 공백을 제거한다 — slice 마다 다르면 5단계에서 불일치로 잡힌다.
- `GlobalExceptionHandler` 는 타입 변환 실패(`MethodArgumentTypeMismatchException`, `page=abc`)와 enum 외 값도 한글 규격 문구(`"올바른 값이 아닙니다"`) 로 변환한다. Spring 내부 영문 메시지를 그대로 내보내지 않는다.
- `GlobalExceptionHandler` 는 `HttpMessageNotReadableException`(역직렬화 실패: 잘못된 날짜·숫자) 의 JSON 경로를 `fieldErrors[].field` 로 변환한다 — 빈 fieldErrors 로 400 을 내지 않는다.
- 감사 컬럼: `created_at, created_by, updated_at, updated_by` 를 모든 테이블에. MyBatis 인터셉터 또는 서비스에서 세팅.
- 네이밍: 테이블·컬럼 `snake_case`, Java `camelCase`, `map-underscore-to-camel-case: true`.
- MyBatis: XML 매퍼 사용. `#{}` 만 사용, `${}` 는 정렬 컬럼 화이트리스트 검증 후에만. `<if>/<choose>` 동적 SQL 허용.
- 트랜잭션: 서비스 메서드에 `@Transactional`, 조회는 `readOnly = true`.
- 검증: DTO 에 `jakarta.validation` 어노테이션. 검증 실패는 GlobalExceptionHandler 가 `COMMON_400` 으로 변환.
  `@Pattern` 은 반드시 `^...$` 앵커를 명시 — Java 는 전체 일치지만 생성된 OpenAPI `pattern` 은 부분 일치로 해석되어 FE 검증과 어긋난다.
- 카운터 갱신(실패 횟수·재고 등)은 읽기→덮어쓰기 금지. `SET col = col + 1` 원자 증가 또는 `SELECT ... FOR UPDATE` 후 갱신.
- 한도 검증(1인 N권, N회 실패 등)은 **한도의 주체 행**(회원)을 `FOR UPDATE` 로 잠근 뒤 count 한다. 자원 행(도서)만 잠그면 같은 주체의 동시 요청이 한도를 넘는다.
- 미존재 키에 대한 `FOR UPDATE` 는 InnoDB **갭 잠금**을 걸어 그 범위의 INSERT 를 막는다(실측: 미존재 사번 로그인 부하 중 회원 등록 22배 지연). 존재 여부를 먼저 일반 조회로 확인하고, 존재할 때만 잠금 조회한다.
- JDBC URL 에 세션 시간대를 고정한다(`connectionTimeZone=Asia/Seoul&forceConnectionTimeZoneToSession=true`). 명명 TZ 는 MySQL 시간대 테이블이 없으면 접속이 실패하므로 배포 가이드에 `mysql_tzinfo_to_sql` 적재를 명시(공식 이미지는 기본 적재).
- 쿼리 파라미터 trim 은 골격 `@ControllerAdvice` + `StringTrimmerEditor(false)` 로 전 slice 자동 적용. Flyway seed 의 `NOW()` 는 서버 TZ 를 따르므로 앱 `Clock` 과 어긋날 수 있다 — 감사 컬럼 seed 는 명시 값 또는 `CONVERT_TZ`.
- **REPEATABLE READ 스냅숏 주의**: 잠금 뒤의 판정은 `FOR UPDATE` 조회가 **반환한** 행/집계(current read)로만 한다. 잠금 전에 읽은 값이나 잠금 없는 `COUNT(*)` 는 트랜잭션 시작 시점 스냅숏이라 상대 커밋을 못 본다 (MySQL 에서 실측: 잠금 → 일반 COUNT 는 여전히 경합 통과). 트랜잭션의 **첫 문장**을 잠금 조회로 두면 스냅숏이 잠금 이후에 잡혀 안전하다.
- 집합 불변식(활성 관리자 ≥ 1 등)은 집합 전체를 **PK 순** `FOR UPDATE` 로 잠그고, 그 조건 컬럼에 인덱스를 둔다(없으면 전체 스캔 잠금).
- 존재하지 않는 계정의 로그인도 더미 해시로 `matches` 를 1회 수행해 타이밍 채널을 없앤다.
- 설정: `application.yml` + `application-local.yml`, 비밀값은 환경변수 참조 (`${DB_PASSWORD}`), 파일에 직접 쓰지 않는다.
- Flyway: `db/migration` 을 `spring.flyway.locations` 로 지정. 골격 `V0001__baseline.sql`, slice 는 `V<yyMMddHHmm>__<slice>_*.sql`.
- OpenAPI: springdoc 으로 `/v3/api-docs` 생성 → `docs/api/<slice>.yaml` 로 저장(태그 = slice). 손으로 보완한 설명은 코드의 `@Operation/@Schema` 에 넣어 재생성해도 유지되게 한다.
  계약 생성용 기동은 **test 프로파일(H2)** 로 하고(MySQL 불필요), `OpenApiConfig` 의 `servers` 는 상대경로 `/` 로 고정해 포트가 yaml 에 남지 않게 한다.
  H2 가 `testRuntimeOnly` 면 `bootRun` 으로는 못 띄우므로 **골격이 `openApiDump` Gradle 태스크**(test 런타임 클래스패스 JavaExec 로 기동 → `/v3/api-docs.yaml/<group>` 저장, `-Pport=`·`-Pgroup=` 인자)를 제공한다. slice 는 `./gradlew openApiDump -PapiGroup=<slice> -Pport=1808N` 만 실행 (`-Pgroup` 은 Gradle 내장 `project.group` 과 충돌).
  springdoc 메모: 검색 조건 DTO 는 `@ParameterObject` 로 개별 query 파라미터 전개, query 파라미터 타입·설명은 `@Parameter`(필드의 `@Schema` 는 boolean 이 string 으로 나옴).
  응답 DTO 는 필수 필드에 `@Schema(requiredMode = REQUIRED)`(또는 Java record + `@NotNull`)를 붙여 계약의 `required` 가 채워지게 한다 — 없으면 4단계 생성 타입이 전부 optional 이 되어 FE 코드가 `?.` 투성이가 된다.
  모든 엔드포인트에 `@Operation(operationId = "<동사><명사>")` (예: `getBook`, `searchLoans`, `login`) 을 명시하고 springdoc 그룹 안에서 유일하게 — 자동 번호(`search_1`)는 4단계 타입 생성 시 이름이 불안정해진다.
- Mapper 인터페이스 이름은 slice 간 빈 이름 충돌을 피해 `<Entity>Mapper` 는 테이블 소유 slice 만 쓰고, 다른 slice 가 같은 테이블을 읽으면 `<Slice><Entity>Mapper`(예: `MemberAdminMapper`).
- JWT(jjwt 0.12+): 알고리즘을 `Jwts.SIG.HS256` 으로 **명시** (키 길이에 따라 HS384/512 로 자동 선택됨). 골격은 `Clock` 빈을 제공해 시간 의존 로직(잠금·만료)을 테스트에서 고정할 수 있게 한다.
- 실패 카운터처럼 예외를 던지면서도 남겨야 하는 갱신은 `@Transactional(noRollbackFor = BusinessException.class)` 또는 `REQUIRES_NEW`.
- developer 의 게이트는 빌드+단위테스트까지. 실제 DB 기동 + curl smoke 는 선택이며 레포트에 "게이트 외 검증" 으로 구분 표기 (5단계와 중복 방지).

## 빌드·테스트 명령
```
cd <target_dir>/backend
./gradlew build -x test     # 빌드 (Windows: gradlew.bat)
./gradlew test              # 단위테스트
./gradlew test --tests "<base_package>.<slice>.*"   # slice 만
./gradlew cleanTest test --no-build-cache            # reviewer 검증용 — 캐시(UP-TO-DATE/FROM-CACHE) 를 피해 실제 실행
```
테스트 수 보고는 `build/test-results/test/*.xml` 의 `tests`/`failures`/`skipped` 합계로 한다 (기억으로 세지 않는다).
Maven 이면 `./mvnw -q verify`, `-Dtest=...`.

## 단위테스트 규약
- Service: Mockito 로 Mapper 를 목킹. `@DisplayName("REQ-011 재고 부족 시 주문 불가")`.
- Mapper: `@MybatisTest` + testcontainers(mysql) 또는 H2 MySQL 모드. Flyway 로 스키마 적용.
  다른 slice 소유 테이블의 테스트 데이터는 각 slice 가 JDBC 로 넣지 말고, 테이블 소유 slice 가 `src/test/resources/fixtures/<table>.sql` 을 제공하고 소비 slice 는 `@Sql` 로 읽는다.
  `@MybatisTest` 는 DataSource 를 임베디드로 교체하므로 `application-test.yml` 에 `spring.test.database.replace: none` 필수.
- **시각 고정 테스트**: 발급·검증 양쪽이 같은 `Clock` 을 봐야 한다. `@SpringBootTest` 통합 테스트는 `@TestConfiguration` 으로 `Clock.fixed` 빈을 override 하고, seed 데이터의 날짜는 상수가 아니라 그 Clock 기준 상대값(`LocalDate.now(clock).minusDays(n)`)으로 만든다. 고정 시각으로 만든 토큰/만료값을 시스템 시계를 쓰는 파서(`Jwts.parser()`, `new JwtTokenParser()`)로 검증하면 실제 시각이 지난 뒤 실패하는 시간 폭탄이 된다. 골격 `JwtTokenParser` 는 Clock 주입 생성자를 제공한다.
- **`REQUIRES_NEW` 는 활성 트랜잭션 밖에서만 호출한다** — 바깥 트랜잭션이 커넥션을 쥔 채 새 트랜잭션을 열면 요청당 커넥션 2개를 점유해 동시 요청이 풀 크기에 닿는 순간 전원 교착(응답 10초+·부수 갱신 유실, 응답 코드는 200 이라 조용함). 목 기반 단위테스트로는 안 잡히고 QA 동시성 테스트에서만 드러난다. 증명은 **풀을 1개로 좁혀 요청 1건이 완주하는지**(MXBean 폴링은 순간을 놓쳐 거짓 통과).
- Maven 콘솔 합계와 `<testsuite tests=…>` 는 `@Nested`·파라미터라이즈가 있으면 다르다 — **`<testcase>` 개수**로 센다.
- MySQL **세션 변수를 바꾸는 테스트**(`SET SESSION …`)는 `finally` 로 원복 — `@MybatisTest` 롤백은 세션 변수를 되돌리지 않고 그 물리 커넥션이 풀로 돌아가 다른 테스트가 물려받는다(실행 순서 의존).
- 계약 강화(최소 길이 등)는 `@Schema(minLength=…)` 같은 **문서 전용** 수단을 먼저 쓴다. Bean Validation 제약을 추가하면 런타임 동작(중복 fieldErrors·문구)이 바뀌므로 `""`·`"  "`·`null` 세 경계를 컨트롤러 테스트에 넣는다. `@NotBlank` 와 `@Size(min=1)` 을 겹치지 않는다. **swagger-core(springdoc) 는 `@Size` 가 있으면 `@Schema(minLength)` 를 `size.min()`(=0) 으로 무조건 덮어쓴다** → 계약 minLength 를 살리려면 길이 검증을 Hibernate `@Length(max)` 로 두고 `@Schema(minLength=1, maxLength=…)` 로 계약 공급(실측 swagger-core 2.2.47).
- 서블릿 `max-file-size` 는 서비스 검증보다 **먼저** 걸린다(초과 시 `COMMON_413`, slice 코드 도달 불가) — 계약에 순서를 명시하고 MockMvc 는 한도를 강제하지 않으므로 경계 예외 재현으로만 고정(실측은 5단계). Spring 7 `ContentDisposition` 은 ASCII `filename=` 과 `filename*` 을 같이 내보내므로 `containsString` 단언.
- 다운로드 API: `Content-Length` 는 `Resource.contentLength()`(실물), `Content-Disposition` 은 RFC 5987 `filename*=UTF-8''`. 저장소 키 검증 예외(`IllegalArgumentException`) 는 500 이 아니라 404 로 변환.
- Controller: `@WebMvcTest` + MockMvc. 검증 실패·에러 응답 포맷 확인.
  `@WebMvcTest` 는 SecurityConfig 를 자동 스캔하지 않음 → `@Import({SecurityConfig, JwtTokenParser})` 표준 패턴을 골격이 `JwtTestSupport` 로 제공하고 slice 테스트는 그것을 쓴다.
  JWT 필터는 `@Component` 로 두지 말고 SecurityConfig 안에서 직접 생성 (서블릿 필터 중복 등록 방지).

## 골격 설계 메모 (병렬 개발 친화)
- `ErrorCode` 는 **인터페이스**, slice 마다 `enum <Slice>ErrorCode implements ErrorCode` — 공용 enum 을 여러 slice 가 동시에 고치는 충돌을 없앤다.
- springdoc 그룹을 slice 별로 미리 등록해 두면 slice 는 `docs/api/<slice>.yaml` 을 자기 그룹에서 뽑을 수 있다.
- 소스 파일은 Write 도구로 작성 (Bash heredoc 다중 파일은 길이 제한으로 실패).
