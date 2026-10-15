<!-- pipeline-core §19 — 핵심(SKILL.md)의 절 목록에서 가리키는 절. 필요한 작업일 때만 읽는다. -->

## 19. 브라우저 화면 검증 — 실행·판정은 기계, AI 는 고른 이미지만

단위테스트마다 스크린샷을 AI 가 판정하면 비용이 크고(이미지 1장 약 1~1.6천 토큰, 큰 이미지는 약 1.15 메가픽셀로 축소돼 장당 약 1,600 토큰 상한)
같은 화면도 회차마다 판단이 흔들린다(비결정적). 그래서 역할을 나눈다:

| 무엇 | 누가 | 토큰 |
|---|---|---|
| 화면 테스트 작성 (DOM 단언·콘솔 오류 0·네트워크 오류 0·`toHaveScreenshot`) | frontend-developer (spec 은 behavior-spec-writer) | 작성 시 1회 |
| 실행 — 로컬에서 BE·FE 기동(Playwright `webServer`) + 헤드리스 브라우저 | Playwright | 0 |
| 모양 비교 — 기준 이미지와 픽셀 비교 | Playwright | 0 |
| 볼 이미지 고르기 + 토큰 추정 | `python tools/visual.py pending` | 0 |
| 새·변경 기준 이미지 최초 승인, 실패 diff 판정 | ui-verifier (config `approver: human` 이면 사람) | 고른 이미지만 |

- 통과한 테스트의 스크린샷은 보지 않는다. 기준 이미지는 화면·상태마다 한 번 승인하면 해시로 고정되고, 바뀌면 다시 검토 대상이 된다.
- 기준 이미지 갱신(`--update-snapshots`)은 새 화면을 처음 만들 때와 **근거 있는 의도한 변경**일 때만 한다. 실패를 없애려고 갱신하지 않는다.
- 예산: `verification.visual.review_budget_images`(기본 60장). 넘으면 우선순위(실패 diff → 변경 → 신규)로 나눠 본다.
- gate `visual`(config `verification.visual.enabled: true`): 4단계 slice·5단계에서 미승인·변경 기준 이미지나 실패 diff 가 있으면 FAIL.
- 결정적인 스크린샷이 전제다 — 고정 뷰포트·시간대·로케일·폰트, 애니메이션 끔, 동적 영역(날짜·시각·난수) 마스킹(프론트 프로필 "Playwright 화면 검증").
