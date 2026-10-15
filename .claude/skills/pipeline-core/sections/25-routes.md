<!-- pipeline-core §25 — 핵심(SKILL.md)의 절 목록에서 가리키는 절. 필요한 작업일 때만 읽는다. -->

## 25. 화면 주소 — 0단계에 규칙을 정하고, slices.yaml routes 를 따른다 (기본값 금지)

화면 주소(프론트 라우트)·메뉴 주소는 사용자가 보는 이름이다. 정하는 단계가 없으면 slice 마다 developer 가 따로 정하고,
프로필 기본값 `/<slice>/...` 이 조용히 쓰여 파이프라인 내부 이름(slice id)이 사용자 주소로 새어 나간다(실측: 이미 반영된 화면을 RR 로 되돌렸다).

- **0단계**: 주소·경로·이름 규칙을 결정 항목(`decision`)으로 올리고 사람이 정한다. brownfield 면 기존 코드의 라우트·메뉴 주소 컬럼·API 경로·배치 규칙을
  `knowledge/TOBE_CONVENTIONS.md` 에 실측해 근거로 쓴다. 결과는 brief §3-1 (stage0-ingest §3-1).
- **1단계**: slice 마다 `routes`(화면 ID -> 주소, 사용자·관리 구분, `menu_path`)를 그 규칙으로 정해 **slice 승인 때 함께 승인받는다** (stage1-slicing §2-2).
  slice 가 다른 세션·작업 트리에서 진행되면 전체 주소를 한눈에 보는 단계는 여기뿐이다.
- **4단계**: 라우트·메뉴 시드(`menu_uri`)·화면 정의서·잠긴 spec 의 주소는 `routes` 에서만 가져온다. 없으면 지어내지 않고 확인 필요 항목으로 올린다.
  프로필에는 주소 기본값이 없다. slice id 는 주소에 쓰지 않는다. 종전 주소를 바꾸면 `replaces` 와 흡수 라우트를 둔다.
- 강제: gate `routes-match`(4단계) — `routes` 의 주소가 프론트 소스(시험 제외)에 문자열로 없으면 FAIL, 이번 변경 메뉴 시드의 `menu_uri` 가 어느 slice 의 routes 에도 없으면
  FAIL(`repo.base` 가 없어 추가 줄을 가를 수 없으면 WARN), `menu_path` 가 있는 화면이 메뉴 시드에 없거나 흡수 라우트가 없거나 slice id 로 시작하는 주소가 새로 생기면 WARN.
  `routes` 가 없으면 건너뛰고(화면이 있는 slice 면 경고) — 기존 slices.yaml 을 깨지 않는다. 설정: `conventions.menu_uri_columns`·`conventions.route_globs`.
