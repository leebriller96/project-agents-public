---
name: stage5-integration-test
description: 5단계 통합 테스트 — slice별 통합 테스트 시나리오(없으면 작성)를 근거로 FE↔BE↔DB 연동을 실행·검증하고, 결함을 리팩토링 요구서(RR)로 도출하는 방법론. /stage5 수행 시 사용.
---

# 5단계 통합 테스트 방법론

목표: FE 와 BE 가 **계약대로 실제로 연결되는지**를 시나리오 기반으로 검증하고, 결함을 RR 로 남긴다. 이 단계는 코드를 고치지 않는다.

## 1. 시나리오 문서

`<target_dir>/docs/test/<slice>-scenario.md` 가 없으면 `templates/test-scenario.md` 형식으로 **먼저 작성**한다. 근거:
- `slices.yaml` 의 requirements → 요구사항마다 정상 1 + 예외/경계 1 이상
- `docs/screens/<slice>.md` 의 버튼→API 매핑 → 화면 조작 경로
- `docs/api/<slice>.yaml` 의 에러 응답 → 에러 노출 시나리오
- depends_on slice 와의 연동(예: 인증 후 주문) → 교차 slice 시나리오 (`ITS-<slice>-x<3자리>`)

이미 있으면 새 요구사항·API 가 반영됐는지 확인해 보강한다. 사람이 쓴 시나리오는 지우지 않는다.
- **앞 단계가 남긴 숙제를 먼저 읽는다**: `python tools/gate.py oi list --status open --target 5 [--slice <id>]`.
  2·3·4단계 reviewer 가 `test_hint` 와 함께 넘긴 `unverified`·`risk` 항목은 **시나리오로 편입해야 닫힌다**(`ITS-<slice>-o<3자리>`).
  실측으로 확인되면 `python tools/gate.py oi set <id> resolved --note "<시나리오 ID·결과>"`,
  결함이면 RR 로 전환(`oi set <id> converted --rr RR-xxxx`), 이번에도 못 하면 레포트 `pa-meta.open_items` 에 그대로 다시 싣는다.
  (2단계 단위테스트로는 도달 불가한 것 — 서블릿 한도·파서 예외·브라우저 렌더 — 이 여기서 닫힌다는 것이 실측된 패턴이다.)
- **판단 재검증 (`pipeline-core §21`)**: `python tools/judgment.py list --verify-stage 5 --slice <id>` 로 앞 단계가 판단으로 정한 것
  (대체 매핑·`불필요:` 판정·의미 차이 수용·범위 제외·해석·지시와 다른 결정)을 받아, 판단마다 시나리오를 하나 이상 둔다(`ITS-<slice>-j<3자리>`, 판단 기록의 `check` 가 출발점).
  기준은 판단 기록의 `criterion` — migration 은 **AS-IS 기능이 손실 없이 동작하고 요구사항에 맞게 온전히 개발돼 있는가**(AS-IS 원본과 같은 입력으로 결과·부수효과 대조 + 요구사항 충족),
  신규 개발은 **요구사항에 맞게 온전히 개발돼 있는가**. 판단을 전제로 쓴 2단계 spec 을 다시 돌리는 것은 확인이 아니다.
  확인되면 `judgment.py verify <JD> --slice <id> --result verified --req-evidence "<시나리오 ID·결과>" [--asis-evidence "<AS-IS 대조>"]`,
  판단이 틀렸거나 기능이 빠졌으면 RR 을 만들고 `--result failed --rr RR-xxxx`. 이 slice 로 확인할 수 없으면 `judgment.py set <JD> --verify-stage 7 --note "<사유>"` 로 넘긴다.
  결과가 없는 판단이 남으면 게이트가 막는다.
- **migration 모드 — 특성화 시나리오**: `ASIS_FUNCTION_CONTRACTS.md` 의 행마다 시나리오 1개 이상(`ITS-<slice>-a<3자리>`, "AS-IS 동작 기준"): 입력 → 기대 출력은 AS-IS 계약에서, 실행은 TO-BE 에. 동작 차이가 §12 근거인 곳은 시나리오에 "의도된 차이 + 근거" 표기. `<slice>-function-mapping.md` 의 특성화 테스트 ID 열을 이 시나리오로 채운다.
- **SQL 등가성**(`migration-sql` §4): `<slice>-sql-mapping.md` 의 의미차이 항목마다 경계값 시나리오(`ITS-<slice>-q<3자리>`), 인벤토리 A 항목이 실행되는 커버리지 보고.

## 2. 실행 환경

우선순위: (1) testcontainers/도커로 MySQL 기동 + BE 기동 + FE 빌드 → E2E, (2) 도커 없음 → BE 는 H2 MySQL 모드로 기동, FE 는 실제 BE 를 바라보게, (3) 기동 불가 → 계약 기반 정적 검증만 (아래 §4) 하고 미실행 사유 기록.

- BE: 테스트 프로파일로 기동, 시나리오 사전조건은 SQL 픽스처(`docs/test/fixtures/<slice>.sql`)로 세팅.
- 화면 모양 검증은 pipeline-core §19 방식(픽셀 비교 + `tools/visual.py` 가 고른 이미지만 ui-verifier 검토)으로 한다. 시나리오 판정에 스크린샷을 AI 가 매번 읽지 않는다.
- FE: Playwright(설치돼 있거나 설치 가능하면) 로 화면 조작. 불가하면 API 레벨(REST 호출)로 시나리오를 실행하고 FE 는 정적 검증.
- 테스트 코드는 `<target_dir>/tests/integration/<slice>/` 에 저장 (재실행 가능해야 함).
- **첫 slice 가 환경을 만든다**: `tests/integration/env-up.sh [--with-fe] [--skip-build]` / `env-down.sh` / `env.sh`(포트·계정) + `docs/test/README.md`. 이후 slice 는 README 대로 재사용. Playwright 는 `tests/integration/package.json` 에 격리 설치(프론트 `package.json` 은 공용 파일).
- 포트는 개발 PC 의 8080/5173 이 점유될 수 있으므로 18080/5174 같은 대체값을 기본으로. Windows Git Bash 에서 기동 스크립트를 파이프(`| tee`)에 물리면 백그라운드 java 가 핸들을 물어 끝나지 않는다 — 파일 리다이렉트 + health 폴링.
- **migration·Maven 멀티모듈 실측(2026-09-22)**: (a) surefire `-Dtest` 패키지 필터는 **슬래시 표기**(`com/example/secu/notice/**/*Test`) — 점 표기는 0건 매칭인데 BUILD SUCCESS 로 조용히 지나가므로 "Tests run: N" 을 반드시 확인. (b) `-pl <모듈> -am` 은 common 테스트까지 실행 → 공유 DB 에 붙이면 common 테스트의 `DELETE FROM tb_user` 가 데이터를 파괴한다 — slice 패키지로 제한하고 실행 후 `COUNT(*)` 로 확인. (c) `SPRING_DATASOURCE_URL/USERNAME/PASSWORD` 환경변수가 `jdbc:tc:` 를 덮으므로 같은 `-Pmysql` 프로파일로 env 컨테이너에 붙여 Mapper 특성화 테스트를 실 DB 에서 재실행할 수 있다. (d) Windows Python 기본 개행 CRLF → expected diff 전부 실패: `newline='
'`/`printf`. (e) 설정값 증명: root 로 `performance_schema.variables_by_thread` 를 조회하면 앱 Hikari 커넥션의 `connection-init-sql`·세션 TZ 를 직접 증명; Boot 4 는 `taskScheduler` INFO 로그가 없어 `jcmd <pid> Thread.print | grep scheduling-` 로; DB 무응답 규칙은 `docker pause/unpause`; ShedLock 은 cron 을 `*/20` 으로 덮고 인스턴스 2개로 실측. (f) 정적 검증 오탐(Javadoc 인용·파생 테이블 별칭)은 주석 제거·서브쿼리 별칭 대조로 제거.
- **E2E 실측(2026-09-22, notice)**: (a) 개발 PC 의 5173 이 다른 프로젝트에 점유되면 죽이지 말고 `FE_USER_PORT` 같은 env 변수로 포트를 바꾼다(env.sh 가 포트를 변수로 받도록). (b) 로그인 계정이 README·Flyway seed 에 없으면 fixture 로 기존 사용자 행에 BCrypt 해시를 UPDATE(python `bcrypt` 부재 → Java 한 줄로 생성) 하고 사유 기록 — 골격은 테스트 계정 seed 를 test 프로파일에 두는 것이 낫다(2단계 골격 후보). (c) Security `csrf.spa()` 는 `/auth/csrf` 본문 토큰이 XOR 마스킹 값이라 API 헬퍼는 **쿠키 raw 값**을 헤더로 보낸다. (d) fixture 날짜는 `CURDATE()` 상대값으로. (e) `yaml.safe_load` 는 계약의 date 예시값을 date 객체로 바꿔 diff 가 어긋남 → 문자열로 정규화.
- **E2E 실측(2026-09-22, notice-admin)**: (a) FE dev 에서 크래시가 나면 `vite preview`(운영 빌드) 로도 재현해 severity 를 판정(dev 전용 StrictMode 이중 렌더 vs 운영 결함). (b) multipart 파일명은 percent-encoding 하지 말고 Chrome 처럼 raw UTF-8; Playwright `request.post({multipart})` 는 같은 이름 파트 반복 불가 → 본문 직접 조립. (c) DB 실패 경로(보상 삭제·실패 메일)는 root 로 `SIGNAL` 트리거를 걸어 재현하고 `finally`/`--cleanup` 에서 제거. (d) 배치는 cron 을 `*/20` 으로 덮은 두 번째 인스턴스(`LOG_PATH` 분리 필수)로 관측 — `batch-run.sh` 로 스크립트화. (e) Git Bash `curl -F` 한글 본문은 불발(000) → Python urllib; `cat > "$미정의변수/…"` 는 stdin 대기로 타임아웃.
- **r2 실측(2026-09-22)**: 세션 변수 원복처럼 테스트 JVM 종료 후 볼 수 없는 것은 mvn 실행 동안 `general_log`(TABLE) 를 켜 스레드별 SQL 로 증명. 러너에 `Tests run: 0` → FAIL 판정, mvn 전후 잔존 COUNT 비교를 넣는다. 300s 넘는 관측은 백그라운드 스크립트 + 마커 파일 폴링. 문서 치환 시 파일별 개행(CRLF/LF)을 따른다. 골격 seed 는 check-then-insert 라 다중 인스턴스 동시 기동 시 경쟁(RR-0036) — README 에 순차 기동 명시.
- 인메모리 상태(스로틀·백오프)는 fixture 재적재로 초기화되지 않는다 → 시나리오마다 열람자(세션·IP)를 바꾸거나 재기동을 명시. `internal-proxies` 를 러너 주소(127.0.0.1)로 두면 러너의 XFF 가 신뢰돼 "위조 무시" 검증이 성립하지 않는다 — 신뢰/비신뢰 양쪽을 다른 주소(`[::1]`)로 대조. Playwright `--reporter=list,junit` CLI 조합은 junit XML 을 stdout 으로 보낸다(`PLAYWRIGHT_JUNIT_OUTPUT_NAME` 또는 config reporter 사용).
- 5단계는 open RR 중 "환경에서 확인 후 처리" 로 미룬 것(예: MySQL 한정 잠금 문제)을 **실측**해 severity 를 조정하고 evidence 를 보강한다.

## 3. 검증 항목 (시나리오별)
- HTTP 상태·응답 스키마가 계약과 일치
- DB 상태 변화가 기대 결과와 일치
- FE 가 응답을 올바르게 표시(성공 메시지/에러 메시지/목록 갱신)
- 인증·권한: 미인증·권한 없음 시나리오

## 4. 정적 검증 (항상 수행)
- FE 의 API 호출 목록(`features/<slice>/api/`) ↔ 계약 ↔ BE 컨트롤러 경로·메서드·필드명 3자 대조. 불일치는 즉시 RR.
- 계약 드리프트: 기동한 BE 의 `/v3/api-docs.yaml/<slice>` 를 정규화(키 순서 무시)해 `docs/api/<slice>.yaml` 과 diff, FE `gen:api` 재생성 diff 도 확인. 둘 중 하나라도 다르면 RR.
- slice 간 규약 일관성(생성 상태코드, 에러 포맷, 페이징) 도 대조한다 — 단일 slice 안에서는 일치해도 slice 간에 다를 수 있다.
- FE 폼 검증 규칙 ↔ BE DTO 검증 규칙 대조 (FE 가 더 느슨하면 medium, BE 가 더 느슨하면 high).

- 시각 의존 결함(월 경계·자정·UTC/KST 창)은 "재현 창(시각 범위)" 을 시나리오·README 에 명시한다. 자동 실행이 창 밖이면 통과해도 결함이 없는 게 아니다.
- 과거 이력처럼 API 로 만들 수 없는 fixture 는 타 slice 소유 테이블에 SQL INSERT 를 허용하되 fixture 파일·시나리오에 사유를 적는다.

- **재실행(rN)**: 시나리오 문서에 이전 결과를 병기하고, 기대값이 바뀐 건수·신규 건수를 레포트에 명시한다. 이전 RR 의 resolution_note 를 근거로 기대값을 갱신하며, 갱신 없이 통과한 항목은 회귀 확인으로 기록.
- 시각 의존 시나리오가 재현 창 밖이면 간접 증거(커넥션 세션 TZ, seed 컬럼 값, 세션 TZ 지정 SQL 결과)로 대체하고 "창 안 재확인 필요" 를 남긴다.

## 5. RR 도출
- 실패 시나리오·불일치마다 RR 1개. `source_stage: 5`, `evidence` 에 시나리오 ID + 실패 로그/파일:라인.
- `target_stage`/`target_layer` 판단: 응답·DB 문제 → 2/backend/*, 표시·검증 문제 → 4/frontend/*, 공통 포맷 문제 → 3/common, 계약 자체 문제 → 2/backend/api.
- 환경 문제(기동 실패 등)는 RR 이 아니라 레포트 "실행 불가" 항목.

## 6. 산출물 및 상태
- 시나리오 문서(결과 열 채움), `tests/integration/<slice>/`, RR 파일들
- 레포트 `workspace/<project>/reports/<ts>_stage5_<slice>_integration.md`: 실행 환경, 시나리오 통과/실패/미실행 수, RR 목록, 정적 검증 결과
- `state.yaml → slices.<slice>.stage5_integration: done` (실패 시나리오가 있어도 RR 로 남겼으면 done; 환경 부재로 아무것도 못 돌렸으면 blocked)
- 사용자에게 RR 요약을 보여주고 `/refactor` 안내

## 공통 금지 — 이모지 (전역 규칙 · 예외 없음)

이 방법론으로 만드는 모든 산출물(소스 주석·로그 문구·Mapper 쿼리 주석·yml 주석·DDL `COMMENT`·테스트 이름·레포트·매핑표)에 이모지를 쓰지 않는다.
규칙 전문과 강제 장치는 `pipeline-core §15`. 이 문서의 규칙과 충돌하면 전역 규칙이 우선한다.
