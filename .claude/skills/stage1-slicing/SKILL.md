---
name: stage1-slicing
description: 1단계 업무 분류 — PROJECT_BRIEF(및 AS-IS 인벤토리)를 바탕으로 업무 slice 를 나누고 의존관계·우선순위·AS-IS 매핑을 slices.yaml 로 만드는 방법론. /stage1 수행 시 사용.
---

# 1단계 업무 분류 (Slicing) 방법론

목표: 이후 2·4·5단계가 독립적으로 돌 수 있는 **업무 단위(slice)** 로 프로젝트를 나눈다.

## 1. 입력

- `workspace/<project>/knowledge/PROJECT_BRIEF.md` (엔티티·화면·API·요구사항 목록)
- `workspace/<project>/knowledge/ASIS_INVENTORY.md` (migration)
- 기존 `workspace/<project>/slices/slices.yaml` 이 있으면 **재분류 모드**: 이미 `done` 인 slice 는 id 를 바꾸지 않는다.

## 2. 분류 기준

1. **엔티티 응집도**: 같이 변경되는 엔티티(주문·주문상품)는 한 slice. 여러 slice 가 쓰는 엔티티(사용자·코드)는 소유 slice 를 하나 정하고 나머지는 `depends_on`.
2. **화면 흐름**: 하나의 사용자 여정(메뉴 트리 한 갈래)이 한 slice 에 들어가도록.
3. **AS-IS 경계**(migration): AS-IS 패키지/메뉴 구조를 1차 후보로 쓰되, 응집도 기준으로 재조정한다. slice 의 `asis` 항목에 **프로그램(컨트롤러·ftl)·테이블·SQL namespace·공통 클래스 사용** 을 전부 적고, `ASIS_FUNCTION_CONTRACTS.md` 의 모든 행이 어느 slice 에 들어갔는지 검증한다(못 넣은 행은 unassigned). TO-BE 가 user/admin 앱을 분리하면 slice 마다 **소유 앱**을 `module` 키로 명시한다(§2-1, config `project.modules`). 앱이 분리되면 한 앱의 화면이 다른 앱의 API 를 쓸 수 없으므로, 첨부 표시·다운로드처럼 **양쪽 화면에 같이 있는 부수 기능은 각 slice 의 apis 에 각각** 넣는다(admin 상세 첨부 다운로드 누락 사례).
4. **크기**: slice 하나가 API 5~20개, 화면 3~10개 정도. 크기는 `python tools/slice_units.py measure` 로 잰다(§7). 넘으면 둘 중 하나로 나눈다.
   - **하위 slice**(`order-basic`, `order-return`): 소유 엔티티·테이블이 갈리고 상태 전이를 공유하지 않을 때. 각각 계약·소유를 갖는 독립 slice 다.
   - **slice 안의 unit**(§7): 하나의 엔티티 상태 전이(업무 프로세스)를 여러 단계가 공유할 때 — 보험금 청구의 접수·심사·지급처럼. 계약·도메인은 slice 하나로 두고 실행만 나눈다.
   경험치: API 11개 slice 가 2단계에서 테스트 포함 파일 30개·에이전트 24분이었다. API 15개를 넘기면 순환 의존이 없는 한 분할을 우선 검토한다.
5. **공통 slice**: 인증/권한, 공통코드, 파일, 알림처럼 모두가 쓰는 것은 `common-*` 접두어로 만들고 priority 를 가장 낮은 번호로 둔다.
   단, 소비자가 하나뿐이거나 DDL/seed 를 골격 baseline 이 담당해 slice 가 가질 것이 API 1~2개뿐이면 분리하지 않고 소비 slice 에 넣는다 (레포트에 사유).
6. **순환 회피 우선**: 두 엔티티가 서로의 테이블을 읽어야 하면(예: 도서 목록의 "대여 가능 권수" 가 대여 테이블을 집계) 나누지 말고 한 slice 로 묶는다. 크기 상한을 넘으면 하위 slice(`order-basic`/`order-return`)로 나누되 소유 테이블은 상위가 갖는다.

## 2-1. 차수·모듈·보류 — 기존 TO-BE 위에 다음 차수를 얹을 때 (brownfield)

`templates/slices.yaml` 의 아래 키로 적는다. 임의 키를 만들지 않는다.

| 키 | 위치 | 언제 | 무엇 |
|---|---|---|---|
| `module` | slice | config `project.modules` 가 있으면 **필수**(목록 중 하나), 없으면 생략 | slice 의 TO-BE 소유 모듈(앱). 공통 사용 행렬이 공통 항목마다 사용 모듈을 계산해 계약이 "한 모듈 공통 / 모듈별 복사(copy) / 전 모듈 공통(`project.common_module`)" 을 제안하고, gate 가 변경 파일이 모듈 경로(`project.module_paths`) 밖인지 경고한다 |
| `existing_code` | slice | 이 slice 가 새로 만들지 않고 고칠 기존 TO-BE 가 있을 때 | target_dir 기준 경로 목록. 에이전트는 이 경로를 먼저 읽고 고친다. gate 의 모듈 경로 대조에서 허용 경로로 본다 |
| `consumes` | slice | (brownfield) 공통이 **이미 있고** 이 slice 가 호출만 할 때. 공통 계약이 `status: external` 이면 **필수** | `[{item, kind, source, note}]`. `item` 은 FQCN·`FQCN#method`·Mapper statement, `kind` 는 `class·method·mapper·statement·service`, `source` 는 계약 id 또는 정본 문서#절. **주석으로 적지 않는다 — 도구가 읽지 못한다**(실측: 소비 10종이 전부 YAML 주석에만 있어 gate 가 검사하지 못했다). gate `consumes-integrity` 가 적었는데 target 에 없으면 FAIL, 적지 않은 공통을 쓰면 WARN 이다. `existing_code`(고칠 기존 코드)와 다르다 — 공통은 slice 가 고칠 수 없다 |
| `hold`·`hold_reason` | slice | 근거(요구사항·설계)가 모자라 착수할 수 없을 때 | 승인·공통 계약 계산에는 포함, /stage2·/run 착수에서는 제외(pipeline-core §4). 사유와 기다리는 근거를 적는다 |
| `pre_pipeline` | 최상위 | 이전 차수(파이프라인 밖 포함)에 이미 이관이 끝난 영역이 있을 때 | `{area, module, asis: {packages, programs, namespaces}, tobe: [경로], note}`. 공통 사용 행렬에서 공통이 아니다(분류 `pre_pipeline`) — 이번 slice 가 부르면 TO-BE 의 기존 코드를 쓴다 |
| `unassigned.asis` | unassigned | 이번 차수 범위 밖 AS-IS 컨트롤러·유형·배치·SQL 이 있을 때 | `{program(s)|package(s)|namespace(s), kind, reason}`. 공통 사용 행렬에서 공통이 아니다(분류 `out_of_scope`) |
| `unassigned.apis` | unassigned | 이번 차수 범위 밖 AS-IS API | `{api, reason}` |

- **왜 적어야 하나**: 어느 slice 에도 속하지 않는 AS-IS 코드는 행렬이 "공통" 으로 본다. 범위 외 코드와 이전 차수에 옮긴 코드를 적지 않으면
  그것과 그것만 쓰는 공통 메서드가 공통 선행 변환 대상이 되어 계약이 부풀고(실측: 수천 항목), 이미 있는 TO-BE 를 다시 만들게 된다.
- 범위 외인지 이전 차수인지 모호하면 추측하지 말고 `unassigned.asis` 에 두고 사유에 "확인 필요" 를 적은 뒤 open item 으로 채번한다.
- 모듈 간 규약(예: "모듈 간에는 복사, 전 모듈 기반만 common")은 brief 근거와 함께 레포트에 적는다. 계약의 module 결정은 사람이 한다.

## 3. 초기에 나누기 애매할 때

요구사항이 너무 적거나 경계가 불명확하면 slice 하나(`core`)만 만들고 진행한다. 2단계를 한 번 돌고 나면 재분류가 쉬워진다.
이 경우 `slices.yaml` 상단 주석에 "단일 slice 로 시작, N 회차 이후 재분류 예정" 을 남긴다.

## 4. 의존관계와 우선순위

- `depends_on` 은 **컴파일/실행 의존**만 적는다 (주문이 회원 API 를 호출 → order depends_on member). 화면 이동만 있는 관계는 적지 않는다.
- 순환 의존이 나오면 공통 부분을 떼어 `common-*` slice 로 만든다.
- `priority` 는 depends_on 위상순서를 따르되 같은 레벨에서는 요구사항 우선순위·리스크(외부 연동 등) 높은 것을 먼저.

## 4-1. traits — 검증 축 결정 (필수)

slice 마다 `traits` 를 채운다. 이것이 **그 slice 를 어느 축에서 검증해야 하는지**를 정하고,
`tools/gate.py` 의 `coverage-axis` 훅이 2·4·5단계에서 그 축이 닫혔는지 대조한다.
근거: 파이프라인이 스스로 만든 결함 7건은 전부 "앞 단계가 보지 못한 축"에서만 잡혔다(sample2 최종 채점).

| brief·AS-IS 에서 이런 게 보이면 | trait | 닫아야 할 축 |
|---|---|---|
| 첨부·업로드·다운로드 | `file-upload` | `real-server` (서블릿·파서가 서비스보다 먼저 갈린다) |
| 여러 테이블 갱신·보상·배치 | `transaction` / `batch` | `real-db` (H2 로는 방언·캐스트가 안 보인다) |
| 조회수·채번·재고처럼 경합하는 값 | `counter` / `concurrency-sensitive` | `concurrency` |
| 에디터·차트·트리 등 DOM/타이머 의존 화면 | `rich-text` / `dom-heavy` | `browser` (jsdom 은 로드 크래시를 못 잡는다) |
| 로그인·권한·프록시 헤더·세션 | `auth` / `proxy-header` | `real-server` |
| 메일·외부 API·파일시스템 | `external-io` | `real-server` |
| (migration) 외부 데이터소스(주 데이터소스가 아닌 DB) statement 를 실행 — `knowledge/DATASOURCES.yaml` 의 external | `external-db` | `real-server` (로컬 DB 로는 원래 방언 실행을 증명할 수 없다. 2단계는 정적 원문 대조·XML 적재까지, 실제 접속은 5·7단계로 예약 — pipeline-core §22) |
| HTML 정제·XSS 방어 | `sanitizer` | `security-static` |

- 해당 없으면 빈 배열로 둔다. 추측으로 붙이지 말고 근거(brief 절·AS-IS 파일)를 SLICE_MAP 에 적는다.
- 새 trait 이 필요하면 `config/project.yaml → verification.trait_axes` 에 매핑을 추가하고 그 이유를 레포트에 남긴다.

## 5. 검증

- brief 의 엔티티·화면·요구사항이 모두 어느 slice 에 들어갔는지 확인한다. 못 넣은 것은 `unassigned` 에 적는다.
- 모든 slice 에 `traits` 키가 있는지 확인한다(빈 배열이라도). 없으면 축 검사가 건너뛰어진다.
- id 는 `^[a-z][a-z0-9-]*$`. 패키지명·디렉토리명으로 쓰이므로 예약어를 피한다.
- `depends_on` 이 존재하는 id 만 가리키는지, 순환이 없는지 확인한다.
- config 에 `project.modules` 가 있으면 모든 slice 에 `module` 이 있고 그 목록 안의 값인지 확인한다(`common_usage.py` 출력의 "module 없는 slice" 가 비어야 한다).
- `hold: true` slice 는 `hold_reason` 이 있는지, 그 slice 에 의존하는 slice 가 함께 보류되는 것을 레포트에 적었는지 확인한다.

## 6. 산출물 및 상태

- `workspace/<project>/slices/slices.yaml` (`approved: false`)
- `workspace/<project>/knowledge/SLICE_MAP.md`: slice ↔ 엔티티 ↔ 화면 ↔ API ↔ 요구사항 ↔ AS-IS 매트릭스 (8단계 추적표의 원천)
- 레포트 `workspace/<project>/reports/<ts>_stage1_all_slicing.md` — 분류 근거, 애매했던 판단, unassigned 목록
- `state.yaml → stages.stage1_slicing: done`, `slices` 에 각 slice 항목을 `pending` 으로 추가
- 사용자에게 slices.yaml 을 보여주고 **`approved: true` 로 바꿔 달라고 요청**한다. (재분류 모드면 approved 를 false 로 되돌린다)

## 7. 큰 slice 의 unit 분할 — 필요할 때만, 업무 프로세스 기준 (pipeline-core §20)

1. **측정**: `python tools/slice_units.py measure`. 기준(`config slicing.size`) 중 하나라도 넘으면 분할 후보, 모두 작으면 묶기 후보(제안만).
   AS-IS 입력 토큰 추정은 "에이전트가 원문 전체를 요약 없이 읽을 수 있는가" 의 직접 지표다.
2. **업무 프로세스**: 분할 후보 slice 에 `process.states`·`transitions` 를 적는다. 근거는 AS-IS 상태 코드 컬럼·상태 변경 SQL(`UPDATE … SET STATUS`)·화면 흐름·요구사항.
3. **unit 정의**:
   - `core`(반드시 첫 unit): 엔티티·상태 enum·여러 unit 이 쓰는 서비스·공유 SQL. API·화면·상태 전이 없음.
   - `step`: 상태 전이를 소유한다(전이 하나는 unit 하나). 연속된 전이 중 같은 담당·같은 화면 묶음이면 한 unit 으로 둔다.
   - `query`: 상태를 바꾸지 않는 조회·출력.
   - API·화면은 unit 하나씩에 배정하고, 요구사항은 unit 또는 flow 에 둔다. `asis.programs` 에는 unit 의 **진입점 프로그램**만 적는다 — 그것만 쓰는 하위 클래스·statement 는 행렬이 자동 배정한다.
   - 진입점이 여러 unit 이 함께 쓰는 거대 컨트롤러 안의 메서드면 `asis.programs` 에 컨트롤러를 적지 않는다. unit 의 `apis` 에 AS-IS 요청 경로와 대응하는 경로를 적으면
     행렬이 컨트롤러 메서드를 자동으로 찾는다(`.do`·`/api`·`POST ` 접두어·경로 변수 이름은 무시). 경로로 찾을 수 없는 메서드만 `asis.methods: ["OrderController#cancel"]` 로 적는다.
   - 공용 유틸·상위 클래스·DAO 처럼 여러 unit 이 쓰는 클래스는 core 의 `asis.programs` 에 클래스 통째로 적는다. 컨트롤러·서비스 구현체(`*ServiceImpl`·`@Service`)의
     공유 메서드는 적지 않아도 행렬이 core 로 올린다(pipeline-core §20 의 적용 대상·비대상 표).
   - unit 하나가 `slicing.unit_max` 를 넘으면 그 unit 의 전이를 더 나눈다.
   - slice 소유는 클래스 단위다. 한 컨트롤러에 여러 slice 의 엔드포인트가 몰려 있으면(신청 유형 전용 API 등) 그 컨트롤러를 소유한 slice 의 unit 이 계약에 두고,
     다른 slice 는 화면·처리기만 갖는다(다른 slice 의 apis 에 적으면 행렬이 그 메서드를 배정하지 못한다).
   - 행렬의 "어느 unit 도 쓰지 않는" 메서드는 호출자를 거꾸로 따라가 정한다: 다른 slice 가 부르면 core 의 `asis.methods`, 범위 외 코드만 부르거나 정적 호출처가 없으면
     `asis.discard`(호출자·주석 호출 위치를 레포트에). 메서드 하나가 부르는 statement 가 상한을 넘으면 어떤 분할로도 맞출 수 없다 — 원인 메서드와 함께 보고한다.
4. **흐름**: `flows` 에 unit 을 가로지르는 시나리오(정상 흐름·예외 흐름)를 적는다. 모든 step·query unit 이 한 번 이상 들어간다. id 는 `FLOW-<slice>-NN`.
5. **행렬**(migration): `python tools/slice_units.py matrix --slice <id>` — 2개 이상 unit 이 쓰는 클래스는 core 여야 한다(FAIL). core 가 비대하면(한 unit 만 쓰는 클래스가 core 에 있음) 경고.
   컨트롤러·서비스 구현체는 메서드 단위로 배정되어 `assignment.<unit>.methods`(`File.java#메서드`)에 나온다. 대응하지 않는 API 는 경고, 어느 unit 도 쓰지 않는 메서드는 FAIL.
   core 가 `unit_max` 를 넘으면 경고에 나오는 "크기 상위" 메서드부터 본다 — 두 unit 이 함께 부르는 큰 메서드가 core 를 키운다.
6. **검증**: `python tools/slice_units.py validate` 가 통과해야 승인 요청을 한다. 실행 순서는 `python tools/slice_units.py order --slice <id>` 로 보여 준다.
7. 레포트에 측정 표(slice 별 판정·수치), 분할한 slice 의 unit 표·flows·순서, 분할 후보인데 나누지 않은 slice 의 근거를 남긴다.

## 공통 금지 — 이모지 (전역 규칙 · 예외 없음)

이 방법론으로 만드는 모든 산출물(소스 주석·로그 문구·Mapper 쿼리 주석·yml 주석·DDL `COMMENT`·테스트 이름·레포트·매핑표)에 이모지를 쓰지 않는다.
규칙 전문과 강제 장치는 `pipeline-core §15`. 이 문서의 규칙과 충돌하면 전역 규칙이 우선한다.
