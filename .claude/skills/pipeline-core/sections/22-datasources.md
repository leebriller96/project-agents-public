<!-- pipeline-core §22 — 핵심(SKILL.md)의 절 목록에서 가리키는 절. 필요한 작업일 때만 읽는다. -->

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
