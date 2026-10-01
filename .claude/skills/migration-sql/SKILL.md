---
name: migration-sql
description: 차세대(migration) 프로젝트의 SQL 이관 방법론 — (1) SqlSession 직접 호출 → Mapper 전환을 위한 SQL 호출 인벤토리 4분류, (2) Oracle → MySQL 8.x 방언 변환 카탈로그(등가 구문·앱 로직 이전·의미 차이 태그), (3) Oracle 인스턴스 없이 정적 카탈로그 + 경계값 fixture 로 하는 등가성 검증. stage0(인벤토리)·stage2(변환)·stage5(검증) 에서 sql-migrator/backend-developer/integration-tester 가 사용.
---

# SQL 이관 방법론 (migration-sql)

전제: AS-IS 쿼리는 전부 Oracle 방언, TO-BE 는 MySQL 8.x + MyBatis Mapper. **Oracle 인스턴스 없음 → 정적 카탈로그 방식.**
원칙: "완벽 변환" 의 기준은 **AS-IS 코드가 그 결과를 어떻게 소비하는가**다. 결과 집합의 형태·순서·NULL 처리가 소비 코드에 영향을 주는지 statement 마다 판정한다.

## 1. SQL 호출 인벤토리 (stage0, `ASIS_SQL_INVENTORY.md`)

AS-IS 가 `sqlSession.selectList("ns.id", param)` 처럼 문자열로 호출하면 없는 id 가 컴파일에 안 잡힌다. Mapper 로 가면 전부 인터페이스 메서드가 되어야 하므로 먼저 전수 조사한다.

1. **호출처 전수**: Java 전체에서 `sqlSession.(selectOne|selectList|selectMap|insert|update|delete)\(` 의 첫 인자를 grep. 리터럴은 `ns.id` 로, **문자열 조합**(`"ns." + type + "List"`, 상수 결합, 변수)은 "동적 id" 로 표시하고 가능한 값 집합을 호출 코드에서 추적(enum·상수·DB 값이면 그 원천).
   `getSqlSession()`·`SqlSessionTemplate`·`SqlMapClient`(iBatis) 등 래퍼도 포함. BaseDAO 류가 namespace 를 접두하는 패턴이면 그 규칙을 먼저 파악.
2. **정의처 전수**: Mapper XML 의 `<mapper namespace>` × `<select|insert|update|delete|sql id>` (`<sql>` fragment 는 별도 표시), `<include refid>` 참조.
3. **4분류 표**:

| 분류 | 의미 | 처리 |
|---|---|---|
| A 호출·정의 | 정상 | Mapper 메서드로 전환 |
| **B 호출·미정의** | 런타임 폭탄(AS-IS 에서도 실행 시 예외 — 죽은 경로이거나 실제 결함) | RR **high** — 호출 경로가 실제로 도달 가능한지 판정 후 폐기/구현 결정 |
| C 정의·미호출 | dead SQL | 매핑표에 "폐기(미호출)", 동적 id 후보인지 확인 후 폐기 |
| D 동적 id | 문자열 조합 | 가능한 값 전부를 A/B 로 전개. 전개 불가면 근거 부족 + 사람 확인 |

4. 산출: `ASIS_SQL_INVENTORY.md` — 통계(namespace 수·statement 수·호출 수·A/B/C/D 건수) + 전체 표(namespace.id, 종류, 호출처 `파일:라인`, 분류, 파라미터 타입, 결과 타입, `${}` 사용, 사용 Oracle 구문 태그 §2). 이 표가 Mapper 인터페이스 설계의 원천이자 8단계 매핑표 원천.
5. **대조 시 놓치기 쉬운 것** (첫 실전 migration 0단계 실측, 2026-09-29):
   - **세션별 적재 매퍼**: 데이터소스가 여럿이면 `SqlSessionFactory.mapperLocations` 로 "세션 → 보이는 namespace" 를 먼저 만든다. id 가 존재해도 호출 세션의 팩토리에 적재되지 않으면 런타임 예외다 — **B-DS** 로 분류한다(실측: 기본 매퍼 폴더의 statement 를 외부 DB 전용 세션으로 호출).
   - **짧은 이름 해석**: namespace 없는 id(`"commonMaxAutoInsert"`)는 MyBatis 가 그 팩토리 안에서 유일하면 해석한다. 유일하면 A, 모호·부재면 B. 이름만 보고 B 로 올리면 오탐이다.
   - **id 전달 래퍼**: `selectList(String arg0, Object arg1)` 처럼 id 를 그대로 넘기는 서비스는 첫 인자가 변수라 D 로 보이지만 호출처 리터럴로 전개하면 A 다(실측: 이걸 놓쳐 namespace 전체가 "호출 없음" 으로 잘못 분류됨).
   - **XML 속성 공백·주석**: `<select id ="x">` 처럼 `=` 앞 공백, XML 주석 안 statement, Java 줄·블록 주석 안 호출을 구분한다(주석 안 호출은 C 의 근거로만 쓴다).
   - **엔진이 statement 가 아니라 세션으로 정해지는 경우**: 같은 매퍼 폴더가 MSSQL·Oracle·MySQL 팩토리에 함께 적재되면 방언 태그는 호출 세션의 엔진 기준으로만 의미가 있다. 인벤토리에 호출 세션·엔진 열을 둔다.
   - **도달 판정의 수신자 타입 한정**: 호출 사슬을 메서드 이름만으로 따라가면 `list`·`insert` 같은 흔한 이름이 다른 서비스와 섞여 도달 불가 B 가 "도달 가능" 으로 오판된다. 필드 타입(인터페이스·구현·상속 필드)으로 수신자를 한정한다.
   - **brownfield(기존 TO-BE 가 있을 때)**: statement 마다 TO-BE 대응 열(이관 동일 id / id 인용 / namespace 부분 이관·id 없음 / 대응 근거 없음)을 둔다. "대응 근거 없음" 은 미이관 증명이 아니다 — 새로 설계한 Mapper 는 1:1 대응이 없다.

## 2. Oracle → MySQL 8.x 변환 카탈로그

statement 마다 사용된 구문을 태깅하고 아래 규칙으로 변환한다. **의미 차이 태그**([의미차이])가 붙은 구문은 5단계 경계값 검증 대상. 카탈로그에 없는 구문은 이 표에 **추가**한다(프로젝트 누적).

### 2-1. 문법 등가 변환 (기계적)
| Oracle | MySQL 8.x | 비고 |
|---|---|---|
| `FROM DUAL` | 생략 또는 `FROM DUAL`(허용) | |
| `NVL(a,b)` | `IFNULL(a,b)` / `COALESCE` | [의미차이] 빈 문자열: Oracle 은 `''`=NULL 이라 `NVL('',b)`=b, MySQL 은 `''` 유지 |
| `NVL(x, '')` | 제거(원문이 no-op) 또는 `IFNULL(x,'')` | [의미차이] Oracle 은 `''`=NULL 이라 `NVL(x,'')`=x(NULL 유지). MySQL `IFNULL(x,'')` 는 `''` 반환 → 소비 코드가 NULL 체크(`??`)하면 결과 달라짐. 소비 없으면 제거 |
| `NVL2(a,b,c)` | `IF(a IS NOT NULL, b, c)` | [의미차이] 동일 |
| `DECODE(x, v1, r1, v2, r2, d)` | `CASE x WHEN v1 THEN r1 WHEN v2 THEN r2 ELSE d END` | [의미차이] `DECODE(x, NULL, r)` 는 NULL 매칭됨 → `CASE WHEN x IS NULL` |
| `a \|\| b` | `CONCAT(a, b)` | [의미차이] Oracle 은 NULL\|\|'x'='x', MySQL `CONCAT(NULL,'x')`=NULL → `CONCAT_WS('', …)` 또는 `IFNULL` |
| `SYSDATE` / `SYSTIMESTAMP` | `NOW()` / `NOW(6)` | [의미차이] 세션 TZ(JDBC `connectionTimeZone`) |
| `TO_CHAR(d, 'YYYYMMDD')` | `DATE_FORMAT(d, '%Y%m%d')` | 형식 문자 매핑표: YYYY→%Y, MM→%m, DD→%d, HH24→%H, MI→%i, SS→%s, DAY→%W |
| `TO_DATE(s, 'YYYYMMDD')` | `STR_TO_DATE(s, '%Y%m%d')` | [의미차이] 잘못된 문자열: Oracle 예외, MySQL NULL(strict 모드 아니면) |
| `TO_DATE('', fmt)` (빈 문자열 바인드) | `STR_TO_DATE(NULLIF(s,''), fmt)` 또는 앱에서 `''`→null 후 `LocalDate` 바인드 | [의미차이] `EMPTY_NULL` — Oracle 은 `''`=NULL 이라 조용히 NULL 저장. MySQL `STR_TO_DATE('')` 는 NULL + 경고(1411) 이며 strict 모드 INSERT 에서 오류가 될 수 있음. "종료일 없음=무기한" 처럼 `''` 가 정상 입력인 경로에서 필수 |
| `TO_NUMBER(s)` | `CAST(s AS DECIMAL)` / 암묵 | [의미차이] 비숫자 문자열 |
| `TRUNC(d)` | `DATE(d)` | `TRUNC(d,'MM')` → `DATE_FORMAT(d,'%Y-%m-01')` |
| `ADD_MONTHS(d, n)` | `DATE_ADD(d, INTERVAL n MONTH)` | [의미차이] 월말 처리 동일(둘 다 말일 유지) |
| `MONTHS_BETWEEN(a,b)` | `TIMESTAMPDIFF(MONTH, b, a)` + 일수 보정 | [의미차이] 소수부 의미 다름 — 소비 코드가 정수만 쓰면 OK |
| `d + 1` (일 산술) | `DATE_ADD(d, INTERVAL 1 DAY)` | |
| `SUBSTR(s, 0, n)` | `SUBSTR(s, 1, n)` | [의미차이] Oracle 은 0 을 1 로 취급, MySQL 은 빈 문자열 |
| `INSTR(s, sub, pos, nth)` | 3·4번째 인자 없음 → `LOCATE(sub, s, pos)` (nth 는 앱 로직) | [의미차이] |
| `LENGTH` / `LENGTHB` | `CHAR_LENGTH` / `LENGTH`(바이트) | [의미차이] MySQL `LENGTH` 는 바이트 |
| `ROWNUM <= n` | `LIMIT n` | [의미차이] ORDER BY 없는 ROWNUM 은 순서 미정 — AS-IS 도 미정이었음을 기록 |
| ROWNUM 페이징 (3중 서브쿼리) | `ORDER BY … LIMIT #{size} OFFSET #{offset}` | [의미차이] 정렬 키 동순위 시 순서 불안정 → tie-breaker(PK) 추가 여부를 소비 코드로 판정 |
| `ROWNUM AS RNUM` 을 결과 컬럼으로 노출(화면 번호) | `ROW_NUMBER() OVER (ORDER BY …) AS rnum` 또는 앱에서 `offset + index` | [의미차이] `TIE_ORDER` — ORDER BY 가 조건부(`<if>`)면 무정렬 시 번호 의미 없음. 정렬 키가 없는 경로는 기본 정렬을 사람 확인 |
| `<if>` 로 감싼 조건부 `ORDER BY` (없으면 무정렬 + 힌트 인덱스 순 의존) | 기본 정렬 키를 **명시**(PK DESC 등) | [의미차이] `TIE_ORDER` — AS-IS 는 "운영에서 그렇게 보임" 수준의 미정 순서. 기본 정렬 결정은 근거 부족으로 기록 후 사람 확인 |
| `ROW_NUMBER() OVER (…)` 등 분석 함수 | 동일(MySQL 8 윈도우 함수) | |
| `LISTAGG(x, ',') WITHIN GROUP (ORDER BY y)` | `GROUP_CONCAT(x ORDER BY y SEPARATOR ',')` | [의미차이] `group_concat_max_len` 기본 1024 **바이트** → 설정. Oracle `VARCHAR2(n BYTE)` 컬럼이 MySQL `VARCHAR(n)`(문자) 로 넓어지면 한글은 3배 → AS-IS 에서 여유였던 길이도 초과함(sample2 실측: 300자×2 절단). 세션 상향은 `spring.datasource.hikari.connection-init-sql: SET SESSION group_concat_max_len = 4096`. H2 는 상한 없음이라 **MySQL 테스트로만 검출** |
| `SYSDATE`/`TRUNC(SYSDATE)` 를 조건·저장 값으로 쓰는 statement | DB `NOW()`/`CURRENT_DATE` 대신 서비스가 `Clock` 으로 잡은 `#{baseDate}`/`#{regDt}`/`#{modDt}` 바인드. **null 폴백(`<choose>` … `CURRENT_DATE`) 은 두지 않는다 — fail-fast 권장**: 검색 DTO 에 `getBaseDateRequired()`(null 이면 `IllegalStateException`) 를 두고 XML 은 그것만 바인드 | [의미차이] `SESSION_TZ` 일원화(앱 Clock = JDBC TZ) + 고정 Clock 으로 경계값 fixture 를 결정적으로 검증 가능. 폴백을 두면 서비스가 Clock 바인드를 빠뜨려도 DB 시계로 조용히 통과해 테스트가 못 잡고(`start_dt <= NULL` 류는 조용한 결과 누락), 고정 Clock 규약을 무력화한다(sample2 검토 지적). 테스트는 "고정 기준일 경로" 와 "null 이면 예외" 를 **별도 메서드**로(DB 시계 경로를 섞지 않는다). MyBatis 동일 세션 재조회는 로컬 캐시에 잡히므로 테스트에서 세션 변수 변경 후 재조회할 때는 쓰기 statement 로 캐시를 비운다 |
| 겸용 상태 컬럼(`USE_YN` = 삭제+만료) 을 `del_yn` + `use_yn` 으로 분리 변환 | 기본 조회는 `del_yn='N'` fragment. 삭제 행을 옵션(`includeDeleted`) 으로 포함하는 목록은 **행 DTO 에 `delYn` 을 함께 반환**(`use_yn` 만 주면 소비 측이 AS-IS `USE_YN<>'Y'` 표시 규칙을 복원할 수 없다). 재귀 CTE 로 계층을 펼칠 때는 **앵커·재귀부 모두** `del_yn='N'` | [의미차이] 분리 후 AS-IS 의 "미사용" 표시(`USE_YN != 'Y'`) = `useYn='N' \|\| delYn='Y'` 로 복원 가능해야 함. 이관(800) 은 `UPD_ID='BATCH'` 만료 판정 + 배치 만료 후 사용자 삭제로 `UPD_ID` 가 덮인 행(`END_DT < 이관일`) 을 `use_yn='N'` 으로 보정하는 규칙까지 적는다(sample2) |
| `WM_CONCAT` | `GROUP_CONCAT` | |
| `MINUS` | `EXCEPT` (8.0.31+) | |
| `INTERSECT` | 동일(8.0.31+) | |
| `NULLS FIRST / LAST` | `ORDER BY (col IS NULL), col` 등 | [의미차이] MySQL 기본: ASC 는 NULL 먼저, DESC 는 NULL 나중 — Oracle 기본과 **반대**(Oracle ASC 는 NULL 나중) |
| `(+)` 외부 조인 | `LEFT/RIGHT JOIN … ON` | [의미차이] `(+)` 가 WHERE 조건에 섞이면 조인 조건 vs 필터 조건 분리 필요 |
| `CONNECT BY PRIOR … START WITH` | `WITH RECURSIVE` CTE | `LEVEL`→깊이 컬럼, `SYS_CONNECT_BY_PATH`→경로 누적, `ORDER SIBLINGS BY`→CTE 안 정렬 키 |
| `ORDER SIBLINGS BY sort_no` | CTE 에 경로 정렬키 누적: `CONCAT(p.path_key, LPAD(c.sort_no, 5, '0'), LPAD(c.id, 10, '0'))` 후 `ORDER BY path_key` | [의미차이] `TIE_ORDER` — 형제 SORT_NO 동순위는 Oracle 도 미정. PK 를 경로키에 덧붙여 고정 |
| 재귀 CTE 안의 문자열 누적 컬럼(경로키·`SYS_CONNECT_BY_PATH`) | 앵커에서 `RPAD(CONCAT(…), 240, ' ')` 로 폭을 고정하고 재귀부는 `RPAD(CONCAT(RTRIM(t.path_key), …), 240, ' ')`. CTE 는 `WITH RECURSIVE t (col, …) AS (` 컬럼 목록 명시 | MySQL 은 **앵커 컬럼의 길이로 CTE 컬럼 타입을 정해** 재귀부에서 길어진 값을 절단(strict 면 오류). `CAST(… AS CHAR(n))` 은 H2 가 공백 패딩이라 양쪽 공용 불가 → RPAD/RTRIM. H2 는 CTE 컬럼 목록이 없으면 구문 오류 (sample2 실측) |
| 숫자 → `LPAD` 인자 | `LPAD(CONCAT('', n), 5, '0')` | H2 `LPAD` 는 문자열 인자만 받으므로 `CONCAT('', n)` 으로 문자열화(양쪽 공용) |
| `CONNECT_BY_ISLEAF` | 외부 SELECT 에서 `NOT EXISTS (SELECT 1 FROM t c WHERE c.parent_id = n.id)` → 1/0 | 소비 코드가 `'1'` 문자열 비교(ftl `?string == '1'`)면 반환 타입(정수) 유지 |
| `LPAD(' ', (LEVEL-1)*2, ' ') \|\| name` (들여쓰기) | `CONCAT(REPEAT(' ', (depth-1)*2), name)` | [의미차이] `CONCAT_NULL` — Oracle `LPAD(x, 0)` 은 NULL 이지만 `NULL \|\| name` = name 이라 결과 동일. MySQL `REPEAT(' ',0)` = `''` → 동일. 판정 "동작 동일" |
| `MERGE INTO … WHEN MATCHED/NOT MATCHED` | `INSERT … ON DUPLICATE KEY UPDATE` | [의미차이] UNIQUE 키가 조인 조건과 같아야 함. 아니면 앱 로직(조회 후 분기) |
| `seq.NEXTVAL` / `CURRVAL` | `AUTO_INCREMENT` + `useGeneratedKeys` / `LAST_INSERT_ID()` | [의미차이] 채번을 먼저 하고 여러 테이블에 쓰는 패턴은 시퀀스 테이블 또는 앱 채번 |
| `DELETE FROM t WHERE …` 서브쿼리 자기참조 | MySQL 은 같은 테이블 서브쿼리 금지 → 파생 테이블로 감싸기 | |
| `UPDATE t SET (a,b) = (SELECT …)` | `UPDATE t JOIN (SELECT …) s ON … SET t.a=s.a` | |
| `REGEXP_LIKE(s, p)` | `s REGEXP p` | [의미차이] 정규식 방언(POSIX 클래스) |
| `TRIM(LEADING '0' FROM s)` | 동일 | |
| `RPAD/LPAD` | 동일 | [의미차이] 길이 0: Oracle NULL, MySQL `''`. 단독 소비(NULL 체크) 시 차이 |
| `col LIKE '%' \|\| #{kw} \|\| '%'` / 문자열 `ORDER BY` / `=` 비교 | `col LIKE CONCAT('%', #{kw}, '%')` | [의미차이] `COLLATION` — Oracle 기본(BINARY) 은 대소문자·악센트 구분, MySQL 8 기본 `utf8mb4_0900_ai_ci` 는 무시. 검색 결과 집합·정렬 순서가 달라질 수 있음 → 컬럼/DB collation 을 brief §12 에서 결정 |
| `GREATEST/LEAST` | 동일 | [의미차이] NULL 인자: Oracle NULL, MySQL NULL — 동일 |
| `EXTRACT(YEAR FROM d)` | 동일 | |
| `TO_CHAR(n, 'FM999,999')` | `FORMAT(n, 0)` | 로케일 |
| `CASE WHEN … THEN 'Y' ELSE 'N'` | 동일 | |
| 힌트 `/*+ INDEX(…) */` | 제거 (필요 시 `USE INDEX`) | 성능 근거 부족으로 기록 |
| `DBMS_LOB.SUBSTR` | `SUBSTR` (TEXT) | |
| `EMPTY_CLOB()` / `EMPTY_BLOB()` | `''` | |
| 바인드 `:name` (iBatis) | `#{name}` | |
| PL/SQL 블록·`BEGIN … END;` in mapper | **앱 로직으로 이전**(서비스 메서드 + 트랜잭션) | 매핑표에 로직 기술 |
| 저장 프로시저 `{call …}` | 앱 로직 또는 MySQL 프로시저(근거 있을 때만) | |
| `FOR UPDATE NOWAIT / SKIP LOCKED` | `FOR UPDATE NOWAIT / SKIP LOCKED` (8.0+) | |
| `RETURNING … INTO` | `useGeneratedKeys` 또는 후속 SELECT | |
| `SELECT … INTO` | 앱 로직 | |
| 식별자 대문자·따옴표 | MySQL 은 `lower_case_table_names` 설정 의존 → 전부 소문자 스네이크로 통일 | [의미차이] |
| `TO_TIMESTAMP(s, 'YYYY-MM-DD HH24:MI:SS')` | `STR_TO_DATE(s, '%Y-%m-%d %H:%i:%s')` 또는 앱에서 `LocalDateTime` 바인드 | [의미차이] `EMPTY_NULL`·`DATE_TRUNC` — 잘못된·빈 문자열은 `TO_DATE` 와 같다. 기간 검색(`sDatetime`~`eDatetime`) 경계 fixture (실측 21건) |
| `SUBSTR(XMLAGG(XMLELEMENT(A, ',' \|\| x) ORDER BY y).EXTRACT('//text()'), 2)` (LISTAGG 4000바이트 우회, 앞 콤마 제거) | `GROUP_CONCAT(x ORDER BY y SEPARATOR ',')` | [의미차이] `GROUP_CONCAT_LEN` — XMLAGG 는 원래 길이 상한 회피용이라 MySQL 에서는 `group_concat_max_len` 상향이 **필수**. XML 이스케이프(`&amp;`)가 결과에 섞였는지 소비 코드 확인 |
| `MAX(x) KEEP (DENSE_RANK FIRST/LAST ORDER BY y)` | `ROW_NUMBER() OVER (PARTITION BY … ORDER BY y)` 서브쿼리에서 `rn = 1` | [의미차이] `TIE_ORDER` — y 동순위면 Oracle 은 집계(MAX), ROW_NUMBER 는 임의 1행. 동순위 시 원래 집계식을 유지할지 판정 |
| `INSERT ALL INTO t1 … INTO t2 … SELECT … FROM DUAL` | 테이블별 INSERT 분리(서비스 트랜잭션) 또는 같은 테이블이면 다중 VALUES | 여러 테이블이면 앱 로직 이전. 채번이 섞이면 `SEQ` |
| `CONNECT_BY_ROOT col` | 재귀 CTE 앵커에서 `col AS root_col` 을 만들어 재귀부에 그대로 전달 | |
| `CHR(n)` (예 `CHR(10)` 줄바꿈) | `CHAR(n USING utf8mb4)` 또는 리터럴 `'\n'` | 코드 13·10 결합(`CHR(13)\|\|CHR(10)`)은 `CONCAT` 과 함께 `CONCAT_NULL` 확인 |
| `TO_CLOB(x)` | 제거(TEXT 컬럼에 그대로) | |
| `WITH x AS (…)` (비재귀 CTE) | 동일(MySQL 8) | 재귀면 `WITH RECURSIVE` 필요 |
| 사용자 정의 DB 함수 호출 `F_xxx(…)`·`FN_xxx(…)` | TO-BE 에 같은 이름 함수가 이관돼 있으면 유지, 아니면 앱 로직 또는 조인으로 | 함수 본문의 방언도 같은 카탈로그로 판정. 이관 여부는 Flyway 함수 DDL 로 확인 |
| `CAST(x AS VARCHAR2(n))`·`NUMBER(p,s)` 타입명 | `CAST(x AS CHAR(n))`·`DECIMAL(p,s)` | [의미차이] `LENGTH_UNIT` — VARCHAR2 는 바이트 길이일 수 있다 |
| `statementType="CALLABLE"` + `{call p(…)}` | 저장 프로시저 행과 같다 — 호출 세션이 외부 솔루션 DB 면 그 시스템의 인터페이스이므로 변환하지 않고 연계 방침(brief)을 따른다 | |
| 숫자 컬럼 = 문자 바인드(`order_id = #{seq}` 에 `'123G'`) | 그대로 두되 sql_mode 를 판정 근거로 적는다 | [의미차이] `IMPLICIT_CAST` — Oracle 은 변환 오류. MySQL 8.4 `STRICT_TRANS_TABLES` 에서는 **UPDATE·DELETE·INSERT 조건의 잘린 숫자 변환도 오류**(`Truncated incorrect DOUBLE value`, 실전 실측)라 동작 동일, **SELECT 는 경고 + 앞 숫자(123)로 비교**라 다른 행이 잡힌다. 가드(`REGEXP` 조건)를 덧대면 오히려 오류가 0건으로 바뀐다 — 쓰기 문장은 그대로, 조회 문장만 판정 |
| `REGEXP_LIKE(s, '…\.…')` (역슬래시 이스케이프) | `s REGEXP '…[.]…'` | [의미차이] `REGEX_DIALECT` — MySQL 문자열 리터럴은 `\.` 의 역슬래시를 먹어 `.`(아무 글자)이 된다(`NO_BACKSLASH_ESCAPES` 가 아니면). 문자 클래스 `[.]` 는 양쪽 공용. fixture 에 점 대신 다른 글자(`10x9x1x3`) 를 넣어 불일치를 확인 |
| 따옴표 대문자 별칭 `AS "RANK"`·예약어 컬럼(`USAGE`) | `` AS `rank` ``·`` t.`usage` `` | [의미차이] `CASE_ID` — MySQL 8 은 `RANK`·`ROW_NUMBER`·`USAGE`·`GROUPS` 등이 예약어라 소문자로 바꾸면 구문 오류. 역따옴표 필수 |
| 스칼라 서브쿼리의 `AND ROWNUM = 1` | `… LIMIT 1` (상관 서브쿼리에서도 허용) | [의미차이] `TIE_ORDER` — 정렬 없는 ROWNUM=1 은 AS-IS 도 임의 1행. 결과가 여럿일 수 있는 조회(대역 겹침 등)는 PK `ORDER BY` 를 붙여 고정하고 기록 |
| `SELECT LAST_NUMBER FROM USER_SEQUENCES WHERE SEQUENCE_NAME = 'X_SEQ'` | `SELECT IFNULL(MAX(pk), 0) + 1 FROM t` | [의미차이] `SEQ` — `information_schema.TABLES.AUTO_INCREMENT` 는 통계 캐시(`information_schema_stats_expiry` 기본 86400초)라 오래된 값이 나온다. 동시 저장 충돌은 AS-IS(캐시된 LAST_NUMBER)와 같은 수준으로 기록 |
| `<selectKey> SELECT MAX(id) + 1 FROM t </selectKey>` + INSERT (PK 가 AUTO_INCREMENT 아님) | `INSERT INTO t (id, …) SELECT IFNULL(MAX(h.id), 0) + 1, … FROM t h` | [의미차이] `SEQ` — MySQL 은 같은 테이블 INSERT … SELECT 를 허용. AS-IS 는 빈 테이블이면 NULL+1=NULL 로 저장 실패했다 — IFNULL 로 1 부터(차이 기록) |
| INSERT 값에 채번 결과를 섞은 파생값(`#{seq}\|\|'G'`) | AUTO_INCREMENT 저장 후 같은 트랜잭션의 보조 UPDATE(`SET col = CONCAT(pk, 'G') WHERE pk = #{id} AND col IS NULL`) | [의미차이] `SEQ` — INSERT 전에는 키를 모른다. 보조 문장은 AS-IS id 가 없으므로 매핑표에 "앱 로직 이전 보조" 로 적고, 서비스 호출 순서를 보고에 명시 |
| `LISTAGG(x, ',') WITHIN GROUP (ORDER BY <상수 또는 조건 컬럼>)` | `GROUP_CONCAT(x ORDER BY <PK·사번> SEPARATOR ',')` | [의미차이] `TIE_ORDER` — 정렬 키가 WHERE 로 고정된 컬럼(예 업무구분 숫자 코드)이면 AS-IS 순서도 미정. 결정 키를 명시하고 기록 |
| `SELECT *` (사용자·계정 테이블) | 컬럼 명시, 비밀 컬럼(`pwd`·`otp_secretkey`·`regno`) 제외 | AS-IS 소비 코드가 읽지 않는 비밀 컬럼을 TO-BE DTO 로 새지 않게 한다(판정 근거에 소비 코드 확인 기록) |
| 테이블·컬럼명 치환 채번(`<selectKey> SELECT MAX(${seqName})+1 FROM ${tableName}` + `INSERT INTO ${tableName} VALUES(#{seq})`) | 도달 호출의 인자를 전수 추적해 테이블이 하나면 그 테이블로 고정하고 `INSERT INTO t (pk) VALUES (NULL)` + `useGeneratedKeys`(PK 가 AUTO_INCREMENT 일 때). 범위 밖 호출(다른 테이블)은 매핑표에 적고 지원하지 않는다 | [의미차이:SEQ] `${}` 잔존 0 이 게이트다. MAX+1 은 동시 저장에서 PK 충돌이 났다 - AUTO_INCREMENT 는 충돌이 없고 삭제된 끝 번호를 재사용하지 않는다(소비 코드가 새 ID 만 쓰면 동작 동일). 주석에도 `${` 를 쓰지 않는다(잔존 grep 오탐) |
| `col IN ( #{x} )` 에 서비스가 따옴표 목록 문자열(`"'01','1'"`)을 바인드 | `<foreach>` 목록 파라미터로 바꾸고, 무엇을 넘길지(AS-IS 값 그대로 = 항상 불일치, 또는 코드 목록)는 서비스 결정으로 남긴다 | AS-IS 결함 - 바인드 값 하나가 따옴표 포함 문자열이라 어떤 행과도 맞지 않는다(중복 검사가 항상 0 → 중복 저장). 두 동작을 모두 실제 DB 테스트로 보이고 decision 항목으로 올린다 |
| 서브쿼리 안의 비한정 컬럼이 그 서브쿼리 테이블에 없는 경우(`... FROM WF_BOARD WHERE ... AND IS_DELETED IS NULL`, WF_BOARD 에 IS_DELETED 없음) | 바깥 쿼리의 어느 테이블로 풀리는지 AS-IS 스키마로 확인하고 그 별칭을 명시(`fi2.is_deleted`) | 두 DB 모두 가장 가까운 바깥 범위로 상관 참조를 푼다 - 결과는 같지만 TO-BE 스키마에 같은 이름 컬럼이 생기면 조용히 바뀌므로 명시한다. 해석이므로 매핑표·판단 기록에 남긴다 |
| `col != 'Y'`·`col <> 'Y'` (NULL 은 빠짐) | `NULLIF(col, '') <> 'Y'` | [의미차이:EMPTY_NULL] Oracle 은 `''` 도 NULL 이라 빠졌다. MySQL 은 `''` 가 `<> 'Y'` 로 참이 되어 들어온다 |
| 단건·검증 조회의 `col = #{x}` 에 `''` 가 바인드될 수 있는 경로(다운로드 UUID·메뉴 URI·결재자 사번) | `col = NULLIF(#{x}, '')` | [의미차이:EMPTY_NULL] Oracle 은 `= ''` 가 `= NULL` 이라 0건. MySQL 은 `''` 저장 행과 맞는다. 접근 검증 키(UUID 등)는 이 차이가 권한 우회가 될 수 있어 반드시 맞춘다 |
| `ORDER BY X` 에서 X 가 SELECT 의 `TO_CHAR(col) AS X` 별칭과 같은 이름 | 원 컬럼(`t.col`)과 PK 로 정렬. NULL 위치는 `NULL_ORDER` 규칙 | [의미차이:TIE_ORDER] Oracle 은 ORDER BY 이름을 SELECT 별칭으로 먼저 풀어 초 단위 문자열로 정렬했다 - 같은 초 순서 미정. MySQL 도 별칭을 먼저 풀므로 테이블 별칭을 붙여 원 컬럼임을 명시 |
| `current_timestamp`·`SYSDATE` 를 문자 컬럼(VARCHAR2/TEXT)에 저장 | `NOW(6)` 그대로(문자열 `YYYY-MM-DD HH:MM:SS.ffffff` 로 저장) 또는 `DATE_FORMAT` 으로 형식 고정 | [의미차이:IMPLICIT_CAST] Oracle 은 NLS 형식(`01-OCT-26 11.00.00.123456 AM +09:00` 류) 문자열이었다. 그 컬럼을 읽는 화면·코드가 있는지 grep 으로 확인해 판정한다(없으면 동작 동일) |
| 소비 코드가 목록을 돌며 같은 키를 맵에 덮어쓰는(`map.put(key+code, v)`, "뒤 행이 이김") 무정렬 조회 | PK(채번 순번) 오름차순을 명시해 "나중 저장 행이 이김" 으로 고정 | [의미차이:TIE_ORDER] AS-IS 는 저장(힙) 순서에 기댔다. 중복 키가 실제 데이터에 있으면 결과값이 정렬로 갈린다 - 판단 기록으로 남기고 실데이터 중복 여부를 확인한다 |

### 2-2. 의미 차이 태그 ([의미차이]) — 반드시 소비 코드로 판정
| 태그 | 차이 | 판정 방법 |
|---|---|---|
| `EMPTY_NULL` | Oracle `''` = NULL, MySQL 은 구분 | 해당 컬럼에 `''` 가 저장/비교되는 경로가 있는가. 있으면 저장 시 `NULLIF(x,'')` 또는 비교 시 `COALESCE(x,'')=''` 로 통일하고 매핑표에 결정 |
| `NULL_ORDER` | ASC 시 NULL 위치 반대 | ORDER BY 컬럼이 NULL 가능하고 화면 순서가 의미 있으면 명시 정렬 |
| `TIE_ORDER` | 동순위 정렬·ROWNUM 순서 미정 | 페이징 화면이면 PK tie-breaker 추가(AS-IS 도 미정이었음을 기록) |
| `SUBSTR0` | `SUBSTR(s,0,n)` | 인자 0 을 1 로 |
| `DATE_TRUNC` | 날짜 절단·산술 | 경계값(자정·월말) fixture |
| `CONCAT_NULL` | `\|\|` NULL 전파 | `CONCAT_WS`/`IFNULL` |
| `IMPLICIT_CAST` | 문자↔숫자 암묵 변환 | 타입 명시 |
| `CHAR_PAD` | `CHAR(n)` 공백 패딩 비교 | MySQL 은 후행 공백 무시 비교(PAD SPACE) — 대체로 동일, `VARCHAR` 전환 시 확인 |
| `CASE_ID` | 식별자 대소문자 | 소문자 통일 |
| `SEQ` | 채번 시점·다중 테이블 | 앱 채번 결정 |
| `MERGE_KEY` | MERGE 조인 키 ≠ UNIQUE | 앱 로직 |
| `GROUP_CONCAT_LEN` | 길이 상한 | 설정 + 상한 검증 |
| `COLLATION` | 문자열 비교·LIKE·ORDER BY 의 대소문자/악센트 구분 (Oracle BINARY vs MySQL `_ai_ci`) | 검색 키워드·정렬 컬럼이 영문/혼합이면 결과 집합·순서 차이. `_bin` 또는 `_as_cs` collation 지정 여부를 brief §12 로 결정하고 fixture(대소문자 혼합) 로 검증 |
| `SESSION_TZ` | `SYSDATE`/`NOW()`·날짜 비교의 세션 타임존 | JDBC `connectionTimeZone`/`serverTimezone` 을 Asia/Seoul 로 고정, 배치 실행 시각(예: 00:10) 과 `CURDATE()` 경계 fixture |
| `LENGTH_UNIT` | `LENGTH`/`LENGTHB`/`VARCHAR2(n BYTE)` 의 문자·바이트 단위 | MySQL `LENGTH` 는 바이트, `CHAR_LENGTH` 는 문자. 한글이 든 값의 길이 검증·절단 경로면 fixture(한글 경계 길이) |
| `REGEX_DIALECT` | `REGEXP_LIKE`·`REGEXP_SUBSTR` 등 정규식 방언 | MySQL 8 ICU 정규식과 POSIX 클래스·역참조·플래그 차이. 패턴마다 일치/불일치 fixture |


### 2-3. Mapper XML 구조 실측 규칙 (2026-09-22 추가)
- **namespace 간 `<include>` 의 중첩 refid 는 FQ 로**: A 네임스페이스의 fragment 안에 `<include refid="notDeleted"/>` 가 있으면 B 에서 include 할 때 B 네임스페이스로 풀린다 — 같은 id 가 B 에 있으면 다른 별칭의 fragment 로 **조용히** 바뀐다. 공유 fragment 의 중첩 refid 는 `com.x.NoticeMapper.notDeleted` 처럼 FQ 로 쓴다.
- `@Param` 단건 statement 의 fail-fast(필수 파라미터 null 검사)는 `<bind value="@FQCN@requireX(x)"/>` OGNL 정적 호출로(`${}` 는 잔존 검사에 걸림).
- 테이블당 Mapper 1개 원칙: 다른 테이블을 갱신하는 연쇄(삭제 시 첨부 del_yn)는 그 테이블 Mapper 의 statement 로 분리하고 트랜잭션 경계는 서비스가 갖는다(다중 테이블 UPDATE 는 H2 게이트 불가).
- **파라미터 DTO 필드명에 "소문자 한 글자 + 대문자" 로 시작하는 이름(`sDatetime`·`mFlag`·`eDate`)을 쓰지 않는다** (2026-09-29 실전 common-port 실측): 게터 `getSDatetime()` 의 MyBatis 속성명은 `SDatetime` 이라
  `#{sDatetime}`·`<if test="sDatetime != null">` 가 "There is no getter" 로 실행 시에만 깨진다(빌드·XML 파싱은 통과). 결과 매핑은 대소문자 무시라 괜찮다 — 문제는 **파라미터 쪽**뿐.
  `regStartDatetime`·`messageFlag` 처럼 이름을 바꾸고 AS-IS 키는 필드 주석에 남긴다. `@Param("sDate")` 로 Map 에 넣는 것은 괜찮다.
- **DB 테스트의 MyBatis 1차 캐시**: 같은 트랜잭션에서 `JdbcTemplate` 으로 데이터를 바꾼 뒤 같은 Mapper 조회(같은 인자)를 다시 부르면 캐시 값이 나온다. 기준값은 `JdbcTemplate` 으로 재거나, 바꾸는 쪽을 Mapper 쓰기 문장으로 한다.
- 인터페이스 ↔ XML 일치는 DB 없이 `XMLMapperBuilder` 로 `classpath*:mapper/common/*.xml` 을 파싱해 `Configuration.getMappedStatements()`(짧은 이름 `Ambiguity` 항목은 걸러낸다)와 인터페이스 메서드를 비교한다 — resultType 오타·잘못된 include 도 기본 `./mvnw test` 에서 걸린다.

## 3. 변환 절차 (stage2 B-2, sql-migrator)

statement 하나마다:
1. 인벤토리 행을 읽고 **소비 코드**(호출처 Java + 그 결과를 쓰는 서비스/ftl) 를 연다.
2. Oracle 구문 태깅 → §2-1 로 변환 초안 → 의미차이 태그마다 §2-2 판정(소비 코드 근거 `파일:라인`).
3. Mapper 인터페이스 메서드 시그니처 결정(파라미터 DTO/`@Param`, 반환 DTO). `resultMap` 이 Oracle 대문자 컬럼을 쓰면 소문자 별칭으로.
4. `<sql>` fragment·`<include>` 는 유지하되 방언 변환 적용.
5. **매핑표 행 작성** (`docs/deliverables/mapping/<slice>-sql-mapping.md`): AS-IS `ns.id` → TO-BE `Mapper#method` | 사용 구문 태그 | 변환 규칙 | [의미차이] 판정·근거 | 검증 fixture 종류 | 상태(변환/앱로직이전/폐기/근거부족).
6. 변환 후 **H2 MODE=MySQL 이 아닌 실제 MySQL(testcontainers)** 로 실행 가능한지 Mapper 테스트 1건 이상(의미차이 항목은 경계값 fixture 포함).

## 4. 등가성 검증 (stage5, 정적 카탈로그 방식)

Oracle 을 못 돌리므로 "AS-IS 결과" 는 **AS-IS 코드의 소비 방식 + 카탈로그 의미 규칙**으로 추론한다.
- 의미차이 태그 statement 마다 경계값 fixture: 빈 문자열/NULL 컬럼, 동순위 정렬 키, 월말·자정·윤년 날짜, 대소문자 혼합, `SUBSTR` 경계, 다중 행 MERGE 충돌, GROUP_CONCAT 상한 초과.
- 기대값은 "Oracle 이라면" 의 규칙에서 도출(예: `NVL('',x)` 는 x) — 이 도출 근거를 시나리오에 적는다. 소비 코드가 그 차이에 둔감하면(예: null 체크 후 동일 처리) "동작 동일" 로 판정.
- `${}` 동적 SQL 은 파라미터 조합별로.
- 판정 불가(소비 코드가 없거나 외부 시스템이 소비)는 근거 부족으로 남기고 사람 확인.

## 5. 산출물·게이트
- stage0: `ASIS_SQL_INVENTORY.md`(4분류·통계), B 분류는 RR(high).
- stage2: slice 별 `<slice>-sql-mapping.md` 100% 행 채움(상태 "근거부족" 허용, "미처리" 불가), Mapper ↔ XML ↔ 호출처 3자 일치 테스트(reflection 으로 인터페이스 메서드 ↔ statement id 전수 비교 1건), 의미차이 항목 Mapper 테스트.
- stage5: 의미차이 항목 경계값 시나리오 전수 + 호출처가 도달하는 모든 statement 최소 1회 실행(커버리지: 인벤토리 A 항목 ÷ 실행된 statement).
- reviewer(§D-2/§D-4 확장): 매핑표 행 누락, 의미차이 판정 근거 없음, `${}` 잔존, 대문자 별칭 잔존, `sqlSession` 직접 호출 잔존 grep 0.

## 공통 금지 — 이모지 (전역 규칙 · 예외 없음)

이 방법론으로 만드는 모든 산출물(소스 주석·로그 문구·Mapper 쿼리 주석·yml 주석·DDL `COMMENT`·테스트 이름·레포트·매핑표)에 이모지를 쓰지 않는다.
규칙 전문과 강제 장치는 `pipeline-core §15`. 이 문서의 규칙과 충돌하면 전역 규칙이 우선한다.
