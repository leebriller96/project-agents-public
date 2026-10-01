# Backend 프로필: spring-boot4-mybatis-maven-multimodule

`config/project.yaml → stack.backend.profile: spring-boot4-mybatis-maven-multimodule`. 차세대(migration) 프로젝트용 — Java 21 / Spring Boot 4.0.x / Maven Wrapper 멀티모듈 / MyBatis / MySQL 8.4 / Flyway / **Spring Security 세션 + CSRF**.
`spring-mybatis-mysql.md` 의 규칙(REPEATABLE READ·갭 잠금·LIKE `!`·타임아웃 실측·Clock·시간 폭탄·계약 required 등)은 **그대로 상속**하고, 아래는 차이점만 적는다.

## 기본 구조 (Maven 멀티모듈 + 모노레포)
```
<target_dir>/
├── pom.xml                      부모 POM (Boot 4.0.x parent, dependencyManagement, 모듈 3개)
├── mvnw, mvnw.cmd, .mvn/
├── server/
│   ├── common/                  공용: 응답·예외·보안·감사·유틸·표준 감사 컬럼 매핑. slice 코드 없음
│   ├── user/                    사용자 앱 (jar, main 클래스) — 사용자 slice 패키지
│   └── admin/                   관리자 앱 (jar, main 클래스) — 관리자 slice 패키지
├── db/migration/                Flyway: V1_0_<대역><번호>__<slice>_<설명>.sql (대역 100~800, §Flyway)
├── docs/api/<slice>.yaml        계약 (springdoc, 그룹 = slice, user/admin 앱 각각에서 dump)
└── apps/                        프론트 pnpm 워크스페이스 (react19-vite-tailwind-pnpm 프로필)
```
- slice 는 `user` 또는 `admin` 모듈 중 **소유 모듈 하나**에만 코드를 둔다(양쪽에 걸치면 slice 를 나눈다). 두 앱이 공유하는 도메인 코드는 `common` 이 아니라 **`server/domain-<slice>`** 모듈로 분리(common 은 업무 지식이 없어야 함).
- 패키지: `<base_package>.<slice>.{controller,service,mapper,dto,domain,exception}` (하이픈 제거). Mapper XML 은 모듈의 `src/main/resources/mapper/<slice>/`.
- 빌드·테스트 명령:
  ```
  ./mvnw -q -pl server/common,server/user,server/admin -am verify -DskipTests   # 빌드
  ./mvnw -q -pl server/user test -Dtest='com.example.**.<slice>.*'             # slice 테스트
  ./mvnw -q test                                                               # 전체 (surefire: target/surefire-reports/TEST-*.xml)
  ./mvnw -q test -Pmysql                                                       # testcontainers 프로파일
  ```
  reviewer 는 `-Dsurefire.useFile=false` 없이 XML 합계로 판정. Maven 은 UP-TO-DATE 가 없으므로 `cleanTest` 불필요.

## 규약 차이
- **인증**: Spring Security **세션**(JSESSIONID, `SessionCreationPolicy.IF_REQUIRED`) + **CSRF 활성**(`CookieCsrfTokenRepository.withHttpOnlyFalse()`, 헤더 `X-CSRF-TOKEN`). JWT 쿠키 골격은 쓰지 않는다. 로그인은 `/api/v1/auth/login` JSON(폼 로그인 아님) → 세션 생성 + CSRF 토큰 쿠키 갱신. 로그아웃은 세션 무효화. 비활성·잠금 즉시 반영은 세션 저장소에서 사용자 상태 재조회(요청당 1회) 또는 `SessionRegistry` 로 세션 만료.
- **메뉴 권한**: 롤 ∪ 사번 허용 목록 — `common` 에 `MenuAuthorizationManager`(메뉴 코드 ↔ URL 패턴 ↔ 롤/사번 표, DB 코드마스터) 를 두고 `@PreAuthorize("@menuAuth.allowed('MENU_CD')")` 로 쓴다. 롤만으로 부족한 요구가 AS-IS 에 있으면 사번 허용 목록을 유지한다.
- **표준 감사 컬럼**: 모든 테이블 `use_yn CHAR(1) DEFAULT 'Y'`, `del_yn CHAR(1) DEFAULT 'N'`, `reg_id VARCHAR(20)`, `reg_dt DATETIME`, `mod_id`, `mod_dt`. `Auditable` 은 이 이름으로 매핑(`created_*` 아님). AS-IS 의 제각각 감사 컬럼은 매핑표에서 표준 컬럼으로 **이름 변환**하고 값은 이관 규칙 명시.
- **논리 삭제**: `del_yn='Y'`. 모든 조회는 `del_yn='N'` 조건 (Mapper `<sql id="notDeleted">` fragment).
- **코드마스터**: 업무 구분 숫자 코드(AS-IS 업무구분 숫자 코드)는 코드마스터 `<GROUP>_CD` 로 치환. 매핑표에 숫자→코드 대응.
- **Flyway 대역**: `db/migration/<대역>/V1_0_<대역><NNN>__<slice>_<설명>.sql` — 100 공통/코드마스터, 200 사용자·인증, 300~700 업무 slice(slices.yaml 의 순서대로 배정), 800 데이터 이관·보정(번호는 **FK 참조 순 — 부모 테이블 먼저** 로 골격이 매기고, slice 규칙 문서가 골격 README 와 다르면 "지시와 다른 결정" 으로 명시). `flyway.locations` 에 폴더 전부 나열. 대역은 slice 마다 하나씩 고정해 병렬 충돌을 없앤다.
- **외부 연동**: `RestClient` 빈(공용 `RestClientConfig`: 타임아웃·로깅 인터셉터·traceId 전파). AS-IS Axis/Jersey/httpclient3 호출은 **소스가 들어온 것만** RestClient 로 치환하고, WSDL 기반 SOAP 은 `spring-ws` 또는 최소 XML 템플릿으로(매핑표에 결정 기록).
- **메일**: 소스가 들어오면 `MailPort` 인터페이스 + 구현(사내 메일 API)로 치환, 템플릿은 DB 테이블. 소스 없으면 범위 외.
- **파일 업로드**: 1단계 저장 `{base}/{구획}/yyyy/MM/dd/FILE_<yyyyMMddHHmmssSSS>_<8hex>.<ext>`, 웹 문서루트 밖, 원본 파일명은 DB 에만. AS-IS 2단계(temp→renameTo) 경로·업무구분 숫자 코드 폴더는 매핑표에 "폐기, 파일 이관 규칙".
- **XSS**: AS-IS XSS 필터는 **대체** — 응답은 React 가 이스케이프, 저장 시 서버 검증기(`HtmlContentValidator`: 허용 태그 화이트리스트, jsoup Safelist). 리치텍스트 필드에만 적용.
- **문서화·로깅 규약**: `stage2-backend §B-7` 과 `spring-mybatis-mysql.md` "문서화·로깅 규약" 절을 그대로 따른다(traceId 필터·logback-spring.xml·Mapper XML 머리/statement 주석·공개 메서드 Javadoc). 모듈이 나뉘어 있으므로 traceId 필터·마스킹 유틸은 공통 모듈에 둔다.
- **로깅**: Boot 로깅 + p6spy(SQL 바인딩 로그, `local`/`dev` 만) + traceId(MDC) + 외부 연동 호출 로그(요청/응답 요약, 민감정보 마스킹) + 파일 롤링(logback-spring).
- **스케줄러**: 소스가 들어온 것만 `@Scheduled(cron = "${app.schedule.<name>}")` + `@SchedulerLock`(ShedLock, 다중 인스턴스 대비) 로 치환. XML 스케줄러 설정은 매핑표에 job 단위로.
- **프로파일**: `local`·`dev`·`prd`. 비밀값은 환경변수. AS-IS `profile/` 폴더·개인 폴더는 매핑표에 "폐기".
- **테스트**: JUnit 5 + Mockito + `@MybatisTest`(H2 MODE=MySQL) + testcontainers(mysql:8.4, `-Pmysql`) + `@WebMvcTest` + `@SpringBootTest`. 목표 커버리지는 근거 없으면 강제하지 않되 **AS-IS 특성화 테스트**(migration-sql·기능 추적표) 는 게이트.

## MyBatis (migration 핵심)
- **SqlSession 직접 호출 금지** — 모든 SQL 은 Mapper 인터페이스 메서드. AS-IS `sqlSession.selectList("ns.id")` 는 인벤토리(`migration-sql` 스킬)로 전수 치환하고, 미정의 id 는 RR(high).
- Mapper XML `namespace` = 인터페이스 FQCN, statement id = 메서드명. `resultType` 은 DTO(record 허용), 컬럼 매핑은 `map-underscore-to-camel-case` + Oracle 대문자 컬럼 별칭 제거.
- Oracle 방언은 `migration-sql` 카탈로그대로 변환하고 statement 마다 매핑표에 "사용 구문 → 변환 → 의미 차이 태그" 기록.
- `${}` 금지(정렬 화이트리스트 예외), LIKE `ESCAPE '!'`, 페이징은 `LIMIT #{size} OFFSET #{offset}`(ROWNUM 이중 서브쿼리 폐기), 시퀀스는 AUTO_INCREMENT(`useGeneratedKeys`) 또는 시퀀스 테이블(멀티 인스턴스 채번이 필요할 때만).

## OpenAPI
- springdoc 3.x(Boot 4 호환) — `springdoc.api-docs.version: openapi_3_0` 고정, 그룹 = slice, user/admin 앱 각각 `openApiDump` 태스크(Maven exec plugin). operationId `<동사><명사>`, 응답 DTO `requiredMode=REQUIRED`.

## 알려진 주의 (Boot 4.0.8 실전, 2026-09-21)
- 실측 버전 조합: Boot 4.0.8 / Spring 7.0 / Security 7.0 / **Jackson 3**(`tools.jackson.*`, `JacksonException.getPath()`) / Flyway 11 / Testcontainers **2.x**(`testcontainers-mysql` 아티팩트) / springdoc **3.0.x**(3.1 은 Boot 4.1) / mybatis-spring-boot 4.0.x / p6spy starter 2.0 / ShedLock 7.
- 패키지 이동: `ErrorController` → `org.springframework.boot.webmvc.error`, `@WebMvcTest` 등 → `org.springframework.boot.webmvc.test.autoconfigure` + 모듈형 테스트 스타터, `RestClientCustomizer` → `org.springframework.boot.restclient`.
- **Security 7 CSRF**: `csrf.spa()` 는 헤더를 원문 토큰으로 비교 → 테스트에서 `csrf().asHeader()`(XOR 마스킹) 는 403. 실제 쿠키/헤더 왕복(`realCsrf()` 패턴)으로 테스트. 로그인 후 재발급 CSRF 쿠키는 지연 생성이라 컨트롤러에서 `getToken()` 1회 호출.
- `SpringApplicationBuilder.properties()` 는 yml 에 덮인다 → 포트는 `--server.port` 명령행 인자.
- 계약 yaml 한글 깨짐 → 바이트로 저장 + `springdoc.default-produces-media-type`. 계약 생성: `./mvnw -q -pl server/<app> -am -DskipTests test-compile exec:exec@openApiDump -DapiGroup=<slice> -Dport=1809N`.
- `mvn` CLI 없으면 Maven 바이너리를 `C:/tools/apache-maven` 에 받아 `mvn -N wrapper:wrapper` 로 `mvnw` 생성(이후 `./mvnw` 만). 첫 골격은 의존성 다운로드 포함 **약 50분** — 예산에 반영.
- `JdbcTemplate.queryForMap` 의 DATETIME 은 H2=`Timestamp`, Connector/J=`LocalDateTime` → 테스트는 `queryForObject(sql, LocalDateTime.class)` 로 읽는다(캐스트 금지). developer 가 "MySQL 전용 구문 없음" 을 이유로 `-Pmysql` 을 건너뛰어도 reviewer 는 그 slice 의 `@SpringBootTest` 를 `-Pmysql -Dtest=<IT> -Dsurefire.failIfNoSpecifiedTests=false` 로 1회 돌린다 — SQL 이식성과 테스트 이식성은 별개.
- 테스트 클래스의 `properties="spring.datasource.url=…"` override 금지(`test-mysql` 프로파일을 덮어 MySQL 게이트가 깨짐). fixture 격리는 `cleanup.sql` + `@Sql(AFTER_TEST_METHOD)`.
- 원자성 REQ(공지+첨부 한 트랜잭션 류)는 목 예외→보상 테스트만으로 부족 — 실제 DB 에서 두 번째 INSERT 를 실패시켜(컬럼 길이 초과 등) 롤백을 증명한다.
- **Boot 4 SPI 이동**: `EnvironmentPostProcessor` 등 SPI 는 `org.springframework.boot.*` 새 패키지(구 `org.springframework.boot.env.*` 는 `@Deprecated(forRemoval)` 호환 경로로만 로드) — `spring.factories` 키도 새 FQCN. "컴파일·기동 성공" 만으로는 deprecated 경로를 못 잡으므로 developer 는 `javap -v` 로 `Deprecated/forRemoval` 확인. `spring.factories`/`.imports` 등록 컴포넌트는 **배선 테스트**(SpringApplication 기동 실패 단언)를 게이트로.
- 프로파일 가드는 `ApplicationRunner` 가 아니라 빈 생성 시점(리스닝·Flyway 전)에. seed 사번(`SEED*`)과 테스트 fixture 사번은 대역을 분리.
- surefire `-Dtest='패키지.*'` 는 아무것도 매칭하지 않고 EXIT 0 — 클래스명 나열 또는 슬래시 경로 패턴(`com/x/**/*Test`)으로, 실행 후 XML 타임스탬프/`Tests run` 확인. MyBatis Mapper 는 JDK 프록시라 `@MockitoSpyBean`+`callRealMethod` 불가 → 실패 주입은 `@TestConfiguration @Primary` 위임 프록시로.
- multipart 파일명 NUL 은 **Tomcat 파서**(`InvalidFileNameException`)가 서비스 정규화 전에 던진다 → 공통 핸들러에서 400 으로 매핑해야 500 이 아님. `MockMultipartFile` 테스트는 파서 단계를 건너뛰므로 실서버(RANDOM_PORT/IT) 케이스 필요.
- 업로드 파일명 정규화(실측 순서): 경로 제거 → NFC → `\p{Cc}\p{Cf}`(NUL·RTLO) 제거 → 끝 점·공백 제거(Windows 저장 규칙 우회 차단) → 길이 1~300 → 마지막 확장자 거부 목록(대소문자 무시) → 크기 → 매직바이트(MZ·ELF·`#!`·PK+META-INF·`<html`/`<script`). Tika 는 공용 pom 결정 후.
- **`server.forward-headers-strategy: native` 는 "프록시 뒤" 가 아니라 "내부 대역(10/8·172.16/12·192.168/16·127/8)에서 온 모든 요청" 의 XFF 를 신뢰**한다(Tomcat RemoteIpValve 기본 `internal-proxies`). 사내망 서비스는 클라이언트가 그 대역이라 XFF 위조로 `remoteAddr` 이 바뀜 → IP rate limit·IP 키 스로틀 전부 우회. 켤 때는 `server.tomcat.remoteip.internal-proxies` 를 실제 프록시 주소로 고정(env 필수, fail-fast) + `@SpringBootTest(RANDOM_PORT)` 실 컨테이너로 위조 XFF 가 remoteAddr 를 못 바꾸는 것을 단언(MockMvc 는 valve 를 안 거침).
- 매직바이트 검사는 **선두 바이트 앵커링**(`contains` 금지). zip 판정에 `META-INF/` 를 쓰면 OCF(hwpx·epub·odt)가 jar 로 오탐 — 첫 로컬 헤더 파일명만 보거나 확장자 거부로 대체. HTML 은 BOM·공백·주석 뒤 선두만.
- Boot 4 `@LocalServerPort` 는 `org.springframework.boot.test.web.server`(`boot.web.server.test` 패키지 없음). 병렬 developer 의 `-am` 빌드는 상대가 편집 중인 파일을 읽어 일시 컴파일 실패할 수 있음 — 수 초 뒤 재실행.
- 쿠키 속성 테스트: `MockHttpServletResponse` 는 `SameSite` 를 헤더에 쓰지 않음 → `Cookie.getAttribute("SameSite")` 로 검증. 새 `LoggerContext` 로 `%X{}` 포맷 시 NPE → 실제 `ILoggerFactory` 컨텍스트로 logback 패턴 테스트. `.gitignore` 의 `!예외` 줄 뒤 인라인 주석은 패턴에 포함돼 무효.
- **필수 환경변수 fail-fast**: Boot 바인더는 미해석 `${DB_PASSWORD}` 를 예외 없이 리터럴로 넘긴다(`environment.getProperty` 는 예외를 내지만 DataSource 바인딩은 아님) → `EnvironmentPostProcessor`(`META-INF/spring.factories`) 로 원본 값의 `${…}` 잔존을 정규식 검사해 명확한 메시지로 종료. 골격 기본.
- **테스트 계정 seed**: `TestAccountSeeder` + `app.security.test-accounts`(`local` 만 활성, `test` 는 허용 목록만 — `test` 에 켜면 골격의 "tb_user 0건" 단언이 깨짐; 다른 프로파일이면 기동 실패).
- **`/auth/csrf` 본문 토큰은 XOR 마스킹**(`csrf.spa()`) — 헤더 값은 `XSRF-TOKEN` 쿠키. 계약 description 과 FE `fetchCsrfToken` 은 쿠키 우선. msw 는 `Set-Cookie` 를 `document.cookie` 에 반영하지 않으므로 테스트 핸들러가 쿠키를 직접 쓴다.
- `@WebMvcTest` 는 `@Import({SecurityConfig, MenuAuthorizationManager})` + `authentication(LoginUser)`; DTO 는 record 그대로 `resultType`.

## 알려진 주의
- Boot 4.0: Jakarta EE 11, Spring Framework 7 — `HttpStatusCode`, `RestClient` 기본, `@MockitoBean`. Boot 3.x 용 서드파티(springdoc 2.x, p6spy-spring-boot-starter 구버전)는 4.x 대응 버전으로.
- **모듈 간 test resources 공유는 test-jar 로 하지 말 것** — `./mvnw test`(package 전) 리액터에서 test-jar 의존은 `target/test-classes` 디렉터리 전체로 해석되어 `includes` 필터가 무력, 소유 모듈의 `@SpringBootConfiguration` 테스트 부트 클래스가 소비 모듈 IT 에 잡힌다(9건 실측). 소비 모듈 pom 에 `maven-resources-plugin` `copy-shared-fixtures`(generate-test-resources 단계, 소유 모듈 `src/test/resources/fixtures` → `target/test-classes/fixtures`) 로 복사. 골격이 이 실행을 user/admin pom 에 미리 넣는다.
- H2 `MODE=MySQL` 은 `SET SESSION <mysql 변수>`(`group_concat_max_len` 등) 를 거부 → `hikari.connection-init-sql` 은 운영 yml 에 두고 `application-test.yml` 에서 `""`(빈 문자열 — HikariCP 7 은 `validate()` 에서 `""`→null 처리, yml `key:` 만 두면 override 안 됨) 로 덮고 `test-mysql` 프로파일이 재설정.
- 공용 클래스 생성자에 인자를 추가할 때 기존 생성자를 남기고 `@Autowired` 를 새 생성자에 두면 slice 테스트 무수정으로 동작 보존.
- Maven 멀티모듈 병렬 developer: 각 slice 는 자기 모듈의 자기 패키지·XML·Flyway 대역만. 부모 POM·common·`mvnw` 는 공용. 전체 `./mvnw test` 는 웨이브 종료 후 1회.

## 알려진 주의 (2026-09-23, sample3 규모 축 21 slice 실측)

- **DDL 식별자 대소문자**: DDL 을 대문자(`TB_CODE`)로 쓰고 Mapper SQL 을 소문자(`tb_code`)로 쓰면
  Windows·H2 에서는 통과하지만 **Linux MySQL(`lower_case_table_names=0`)에서 전 slice 쿼리가 실패한다.**
  골격 `CONVENTIONS.md` 에 표기를 한쪽으로 고정하고, 리뷰 시 DDL ↔ Mapper 표기 일치를 대조한다(RR-0002 실측).
- **Flyway 버전 충돌**: 병렬 웨이브에서 분 단위 타임스탬프는 충돌한다. 버전에 slice 고유 번호를 넣는다(pipeline-core §6-4).
  `db/migration` 공유 때문에 한 slice 의 중복 버전이 **무관한 모듈의 스프링 컨텍스트까지 실패**시킨다.
- **`copy-resources` 는 삭제를 전파하지 않는다**: 마이그레이션을 `target/test-classes` 로 복사하는 구성에서
  원본을 rename 하면 옛 복사본이 남아 같은 충돌이 계속된다. 골격이 복사 전 정리(또는 `prune` 스크립트)를 제공한다.
- **공용 메뉴 권한 설정**: 메뉴 기반 인가(`app.security.menus`)를 골격이 쓰면 slice 가 추가한 메뉴 코드가
  운영 설정에 없어 **쓰기 API 전체가 403** 이 된다. slice 는 공용 설정을 고칠 수 없으므로 공통 후보로 올리고
  3단계(또는 오케스트레이터)가 일괄 반영한다.
- **메서드 파라미터 검증**: `@RequestParam` 에 직접 제약을 걸면 Spring 6.1+ 는 `HandlerMethodValidationException` 을 던져
  `BindException` 만 처리하는 핸들러를 지나쳐 500 이 된다. 조건 객체(`@ModelAttribute`)로 받거나 핸들러를 확장한다.
- **성공 상태 코드 규약**: POST 201 / PUT·DELETE 200 처럼 성공 상태를 골격 규약에 미리 적어 두지 않으면 slice 마다 갈린다.
