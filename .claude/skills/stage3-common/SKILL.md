---
name: stage3-common
description: 3단계 공통화 리팩토링 — 완료된 slice 들에서 중복·공통 속성 코드를 common 모듈로 추출하고 컨벤션을 정렬하는 방법론. /stage3 수행 시 사용.
---

# 3단계 공통화 리팩토링 방법론

목표: slice 들이 각자 임시로 만든 공통성 코드를 **한 곳으로 모으고**, 동작은 바꾸지 않는다.

## 1. 입력
- `workspace/<project>/reports/common-candidates.md` (2단계 developer 들이 남긴 공용 변경 요청)
- `stage2_backend: done` 인 slice 들의 소스
- `<target_dir>/backend/CONVENTIONS.md`

## 2. 후보 탐지
1. common-candidates 항목을 먼저 처리한다.
2. 그 외 탐지 기준 — 둘 이상의 slice 에서:
   - 같은 시그니처/유사 본문의 유틸·변환·검증 로직
   - 같은 형태의 DTO(페이징, 코드값, 기간 조건), 같은 에러 처리 패턴
   - 같은 SQL 조각(공통코드 조인, 감사 컬럼 세팅, soft delete 조건)
   - 같은 외부 연동 클라이언트 초기화
3. 후보마다 표로 정리: 위치들, 공통화 방식(유틸/베이스 클래스/인터셉터/공통 SQL fragment), 영향 slice, 리스크.

## 3. 원칙
- **동작 보존**: 기존 단위테스트가 그대로 통과해야 한다. 테스트를 고쳐야 통과한다면 그건 공통화가 아니라 변경이므로 하지 않고 RR 로 남긴다.
  예외: brief §12 결정에 따라 slice 가 임시 구현으로 남겨둔 기능 전환(예: CSV→xlsx, 의존성 추가 후) 은 허용하되 레포트에 "동작 변경(§12 근거)" 로 명시하고 관련 테스트를 함께 갱신한다.
  기준선 측정에서 이미 실패하는 테스트가 있으면 고치지 말고 RR(high, 원인 slice) 로 남기고 `blocked` 보고 — 오케스트레이터가 `/refactor` 로 먼저 처리한다.
- **한 번에 하나**: 후보 하나 추출 → 빌드·전체 테스트 → 다음 후보. 실패하면 되돌린다.
- **추상화 과잉 금지**: 두 곳에서만 쓰이고 앞으로 늘어날 근거가 없으면 추출하지 않는다 (레포트에 "보류" 로 기록).
- 공용 범위는 backend `common` 만이 아니라 **FE 공용 패키지(`apps/shared`)·루트 설정·골격 문서**도 포함한다 — slice 가 F-nn 으로 올린 FE 공용 변경도 이 단계가 흡수한다.
- 공통 모듈에는 slice 의존이 들어가면 안 된다 (`common` → `<slice>` import 금지).
- 컨벤션 위반(네이밍, 패키지 위치)은 이 단계에서 일괄 정렬한다.
- **상품화 품질 정렬**: 전체 스캔 `python tools/quality.py <target_dir>` 결과(문서화 비율·규칙별 건수)를 기준선으로 레포트에 싣고, 남은 major(Javadoc·로거·Mapper 주석 누락)를 이 단계에서 일괄 보완한다 — 주석·로거 추가는 동작을 바꾸지 않으므로 §3 동작 보존과 충돌하지 않는다. 추출한 공통 코드에도 Javadoc 을 단다(공통 모듈 명세의 원천). 종료 시 같은 명령으로 다시 재어 전후 비율을 비교한다.
- 2단계 reviewer 가 RR 로 남긴 지적 중 **공용 코드 변경이 필요한 것**(예: 공용 `MailMessage` 의 다수 수신자)은 이 단계가 유일하게 공용을 고칠 수 있는 자리이므로 여기서 흡수하고, 해당 RR 은 `/refactor` 에서 slice 측 잔여(추적표 등)만 처리하도록 보고에 명시한다.
- 후보에 "사람 결정 대기" 항목(§11 근거 부족·§12 확인 요청)은 코드 변경 없이 현 상태를 유지하고 레포트에 절을 따로 두어 사용자에게 올린다 — RR 로 만들지 않는다.

## 3-1. migration 모드 — 공통 클래스 4분류표

> 공통 계약(`contracts/common-contract.yaml`, pipeline-core §17)이 있으면 **분류의 원천은 계약**이다. 이 단계는 계약의 결정을 `common-inheritance.md` 로 옮기고,
> 계약 이후 생긴 공통 요청(CR)·업무별 중복을 흡수하며, 계약과 코드가 어긋난 곳을 RR 로 남긴다. 분류를 새로 정하지 않는다.

`ASIS_COMMON_INVENTORY.md` 의 항목마다 `docs/deliverables/common-inheritance.md` 에 확정한다:

| 분류 | 의미 | 조건 |
|---|---|---|
| **계승** | AS-IS 공통을 TO-BE 로 그대로 포팅(패키지·시그니처 정리만) | TO-BE 프레임워크에 대응 기능이 없고 slice 들이 그대로 씀 |
| **대체** | TO-BE 프레임워크/라이브러리 기능으로 교체 | 예: 세션 체크 인터셉터→Spring Security, XSS 필터→서버 검증기, dbcp→Hikari, log4jdbc→p6spy. **동작 차이**(무엇이 달라지는지·slice 영향)를 반드시 명시 |
| **개선** | 요구사항/§12 근거로 동작을 바꿈 | 근거 없으면 개선 불가 → 계승 |
| **폐기** | 사용처 0 또는 TO-BE 에서 불필요 | 미호출 증명(인벤토리 사용처 수 0) 또는 §12 결정 |

- 각 행: AS-IS 클래스 `파일`, 사용처 수, 분류, TO-BE 대응(클래스/설정), 동작 차이, 근거. "대체" 의 동작 차이에는 **검증·처리 시점의 이동**(예: 주소 형식 검증이 라이브러리 → 어댑터로)도 포함한다. 인벤토리의 사용처 0 항목이 상위 행의 서브항목이면 상위 행 분류 아래 "폐기 서브항목" 으로 적고 집계 문구에 그 수를 따로 밝힌다.
- 2단계 추적표가 "RR(low) 후보" 로 적은 항목을 이 단계가 common-candidates 보류로 흡수하면 추적표 문구도 같은 회차에 갱신한다(문서 간 처리 수단 불일치 방지). 대체·개선은 **특성화 테스트**로 AS-IS 동작과의 차이가 의도한 것뿐임을 증명.
- 설정 XML 의 빈·인터셉터·스케줄 job 도 같은 표로(각 job 은 `@Scheduled` 대응 또는 폐기 근거).

## 4. 산출물 및 상태
- `common/` 변경 + 각 slice 의 치환
- `<target_dir>/docs/deliverables/common-module-spec.md`: 공통 모듈 목록·용도·사용법 (8단계 산출물의 원천). 기존 파일이 있으면 갱신.
- `common-candidates.md` 의 처리된 항목은 "처리됨(회차 N)" 표시.
- 게이트: 빌드 + **전체** 단위테스트 통과.
- 레포트 `workspace/<project>/reports/<ts>_stage3_all_common.md`: 추출 목록·보류 목록·테스트 결과.
- `state.yaml → stages.stage3_common: done|blocked` (반복 실행되므로 log 에 회차를 남긴다)

## 5. reviewer 체크리스트
1. 공통화 전후 테스트 결과가 동일한가 (개수·통과).
2. common → slice 역방향 의존이 없는가.
3. 추출된 것이 실제로 둘 이상에서 쓰이는가. 사용처가 모두 치환됐는가(중복이 남아 있지 않은가).
4. `common-module-spec.md` 가 코드와 일치하는가.
4-1. 상품화 품질이 기준선보다 나빠지지 않았는가(`tools/quality.py` 전후 비교). 추출된 공통 클래스·메서드에 Javadoc 이 있는가.
5. (migration) 4분류표의 증명 테스트 ID 를 `python tools/check_test_ids.py <target_dir> docs/deliverables/common-inheritance.md` 로 **전수 대조**(불일치 0 이어야 함) — 손으로 쓴 148건 중 1건 오기 사례. 기능 추적표(`mapping/<slice>-function-mapping.md`)도 같은 도구로.

## 공통 금지 — 이모지 (전역 규칙 · 예외 없음)

이 방법론으로 만드는 모든 산출물(소스 주석·로그 문구·Mapper 쿼리 주석·yml 주석·DDL `COMMENT`·테스트 이름·레포트·매핑표)에 이모지를 쓰지 않는다.
규칙 전문과 강제 장치는 `pipeline-core §15`. 이 문서의 규칙과 충돌하면 전역 규칙이 우선한다.
