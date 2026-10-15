<!-- pipeline-core §20 — 핵심(SKILL.md)의 절 목록에서 가리키는 절. 필요한 작업일 때만 읽는다. -->

## 20. 큰 slice 의 unit 분할 — 필요할 때만, 업무 프로세스 기준으로

실측된 한계: slice 크기는 고르지 않다. '이벤트' 는 API 1~2개지만 '보험금 청구' 는 접수·심사·지급·부지급·이의·조회가 얽힌 작은 프로젝트급이다.
에이전트 한 번이 정확히 다룰 수 있는 양을 넘으면 ① 뒤로 갈수록 AS-IS 원문을 다시 읽지 않아 분기·statement 가 빠지고 ② 비슷한 분기를
하나로 합쳐 업무 규칙이 사라지며 ③ reviewer·spec 도 대표 경로만 본다. 전부 빌드·단위테스트는 통과하므로 게이트에 드러나지 않는다.

구분: **slice 는 계약·소유·검증의 단위로 남고, unit 은 에이전트 1회 실행의 단위다.** OpenAPI 계약·도메인 모델·상태 전이는 slice 하나로 유지한다.
(서로 다른 엔티티를 소유하고 상태 전이를 공유하지 않는 부분은 unit 이 아니라 하위 slice 로 나눈다 — `stage1-slicing §2-4`.)

| 순서 | 무엇 | 누가 | 도구·산출물 |
|---|---|---|---|
| 1 | 크기 측정 — AS-IS 입력 토큰 추정·API·화면·statement·메서드·상태 전이·요구사항 수. 기준(`config slicing.size`)을 **완충대(`size_buffer`) 밖으로** 넘는 slice 만 분할 후보, 아주 작은 slice 는 묶기 후보 | `python tools/slice_units.py measure` | 1단계 레포트 |
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
- **경계값은 나누지 않는다 (완충대 `slicing.size_buffer`, 기본 10%).** 기준을 넘되 완충대 안이면 `measure`·`validate` 가 INFO 로만 남기고
  분할 후보로 올리지 않으며 `no_split_reason` 도 요구하지 않는다. 기준값이 작으면 완충대가 생기지 않는다(floor: 8 -> 8, 20 -> 22).
  근거(실측): 신규 개발 13 slice 를 측정했을 때 분할 후보 3건이 **전부 기준을 정확히 1건 초과**였고, 그 경계에서 상태 전이로 나누면
  unit 이 API 1~3개짜리가 된다. unit 하나는 계약·spec 작성·잠금·구현·reviewer·검증 6단을 따로 도므로 과분할은 결함 검출력을 올리지 않고
  단계 비용만 곱한다. **공정을 늘리는 것 자체가 품질이 아니다** — 분할은 "에이전트 1회가 원문을 다 못 읽는 크기" 일 때만 값을 한다.
- **신규 개발(greenfield)에서는 척도 3개가 비어 있음을 전제한다.** `asis_tokens`·`statements`·`methods` 는 AS-IS 원문 척도라 입력이 0 이고,
  판정이 `apis`·`screens`·`transitions` 에만 걸려 1건 차이로 뒤집힌다. 그래서 `requirements`(배정 요구사항 수)를 척도에 함께 둔다.
- **업무 규칙 밀도는 분할 기준이 아니라 검증 축 신호다** (`slicing.density_signal`, 요구사항 + 상태 전이). API·화면 수가 적어도 업무 규칙이
  두꺼운 slice 가 있다(실측: 규칙 밀도가 가장 높은 slice 가 크기로는 '적정' 으로 통과했다). 이때 할 일은 나누는 것이 아니라
  `traits` 에 `real-db`·`concurrency` 같은 축이 필요한지 보는 것이다 — 결함은 단위 테스트 축에서 나오지 않는다 (§14). 필요 없으면 그대로 둔다.
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
- **상태 전이가 0인 조회 전용 slice 는 데이터 원천 축으로 나눈다.** step unit 은 상태 전이를 소유하는 단위이므로 전이가 없으면 처방이 성립하지 않는다.
  그때는 `query` unit 을 **소유 테이블·데이터소스** 축으로 나누고(한 unit = 한 원천 묶음 + 그것을 읽는 화면), 여러 unit 이 함께 쓰는
  조회·집계·권한 코드는 `core` 가 먼저 만든다. **원천을 특정할 수 없으면 나누지 않는다** — 그 상태로 나누면 경계가 임의가 되고
  나중에 전부 다시 나눠야 한다. `no_split_reason` 에 그 사실과 **다시 측정할 시점**을 적는다.
- **화면 수의 단위는 라우트(화면 경로) 하나다.** 한 화면 안의 패널·지표·탭·모달은 세지 않는다.
  실측: 같은 범위를 한 문서는 3행(라우트), 다른 문서는 14행(지표 패널)으로 적어 **분할 판정이 갈렸다**(14 > 10 이면 split, 3 이면 ok).
  문서가 패널 단위면 라우트로 묶어 세고 그 환산을 1단계 레포트에 적는다. 한 화면이 유난히 무거우면(패널마다 독립 조회)
  그 무게는 `apis` 에 나타난다 — `screens` 를 부풀려 표현하지 않는다.
- **필요할 때만 나눈다.** 기준 이하 slice 에 units 가 있으면 과분할 경고다(unit 마다 에이전트 호출 4~5회가 추가된다).
  기준 초과인데 나누지 않으면 **`slices.yaml` 의 `no_split_reason`**(20자 이상)에 근거를 적는다 — 레포트 산문이 아니다.
  산문은 도구가 읽지 못해 다음 회차가 "나눠야 하는데 왜 안 나눴나" 를 다시 조사한다.
  `slice_units.py validate` 는 근거가 없으면 WARN(전이가 0이면 조회 전용 처방을 함께 안내), 있으면 INFO 로 그 근거를 보여 준다.
  기준값은 초기 추정치다 — 에이전트가 원문을 다시 읽지 않고 요약하기 시작한 크기를 실측하면 `config slicing` 을 고치고 `docs/LESSONS.md` 에 근거를 적는다.
- 강제: gate `unit-scope`(선행 unit 미완료·unit AS-IS 누락·slice 통합 조건), 훅(unit·slice 의 done 전환 시 게이트 실행 — 새 state 로 판정),
  `gate.py plan`(구조 오류면 멈춤, 분할 후보 알림), `status.py`(unit 진행 표).
