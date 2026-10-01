# 통합 테스트 시나리오 — <slice id> (<slice명>)

> 5단계에서 slice별로 작성한다. 시나리오 ID는 `ITS-<slice>-<3자리>`.

| ID | 시나리오 | 사전조건 | 절차 (FE 조작 → API → DB) | 기대 결과 | 관련 요구사항 | 관련 API | 자동화 | 결과 |
|---|---|---|---|---|---|---|---|---|
| ITS-order-001 | 주문 생성 정상 | 로그인 상태, 재고 10 | 주문 화면에서 수량 2 입력·저장 → POST /orders → tb_order insert | 201, 재고 8 | REQ-010 | POST /orders | Y | |
| ITS-order-002 | 재고 부족 시 주문 실패 | 재고 1 | 수량 2 → POST /orders | 409 + 오류 메시지 노출 | REQ-011 | POST /orders | Y | |

## 실행 환경
- 실행 방법 / 사용한 DB(테스트 컨테이너 등) / 미실행 시나리오와 사유
