---
name: stage4-frontend
description: 4단계 Frontend 개발 — 화면 근거(피그마/스토리보드, migration 이면 레거시 화면 템플릿)와 slice 의 OpenAPI 계약만을 근거로 slice별 화면·컴포넌트·API 클라이언트·단위테스트를 개발하는 방법론. /stage4 수행 시 사용. 스택별 규칙은 profiles/ 참조.
---

# 4단계 Frontend 방법론

목표: slice 의 화면을 **화면 근거(피그마/스토리보드 - migration 이면 레거시 화면 템플릿 포함, §B-0)와 OpenAPI 계약만으로** 완성한다. Backend 소스는 읽지 않는다 — 계약이 부족하면 RR 로 남긴다.
스택별 규칙은 `profiles/<stack.frontend.profile>.md`.

## A-0. 기존 앱 위에 얹을 때 (brownfield)

target_dir 에 파이프라인 밖에서 만든 프론트 앱(예: 모노레포 `apps/<앱>`)이 이미 있으면 `frontend/` 를 새로 만들지 않는다. 골격은 **그 앱에 빠진 것만 더하는 작업**이다.
- 먼저 실측한다: 빌드·타입체크·린트·테스트 스크립트와 도구 유무, 디렉터리 관례, API 클라이언트·인증·공용 컴포넌트, logger. 있는 것은 규약 문서에 "기존 것을 따른다" 로 적고 다시 만들지 않는다.
- 빠진 테스트·린트·Playwright·계약 타입 생성은 devDependencies·설정·스크립트 추가로만 넣는다(기존 기능 동작 무변경). 린트를 기존 코드 전체에 강제하면 기존 개발 흐름이 막히므로,
  파이프라인이 만드는 경로에 엄격 적용하고 기존 코드 범위는 실측 결과로 정한다(근거를 레포트에).
- slice 마다 격리 하네스(slice 폴더 안 별도 package.json)로 테스트를 돌리는 우회는 쓰지 않는다 — 골격 없이 slice 를 시작하면 이 우회가 slice 마다 복제된다(실측 2026-10-07).

## A. 골격 (scaffold) — 최초 1회

`<target_dir>/frontend/` 가 없으면 만든다 (`state.yaml → stages.stage4_scaffold` 항목을 추가해 기록).
1. 빌드·린트·테스트 설정 (프로필 기본값).
2. 디렉토리: `src/app/`(라우터·프로바이더), `src/shared/`(공통 UI·API 클라이언트 베이스·유틸·타입), `src/features/<slice>/`.
3. 공통: API 클라이언트(공통 응답 포맷 해석, 인증 헤더, 에러 → 토스트/리다이렉트), 레이아웃, 인증 가드, 공통 컴포넌트(테이블·폼·페이징·확인 모달).
4. `frontend/CONVENTIONS.md`: 디렉토리·네이밍·상태 관리·스타일·테스트 규약, 문서화 주석 규약(§B-5).
   골격은 `shared/lib/logger.ts`(운영 빌드에서 debug/info 비활성, 오류는 공통 수집 지점으로) 와 ESLint `no-console: ["error", { allow: ["warn", "error"] }]` 을 둔다.
5. 게이트: 빌드 + 린트 + 샘플 테스트 통과. 레포트 이름은 `<ts>_stage4_scaffold-fe_<설명>.md`, pa-meta `slice` 는 `scaffold-fe` 다
   (`gate.py check --stage 4 --slice scaffold-fe` 와 state 기록 훅이 이 이름으로 찾는다 - `_stage4_scaffold.md` 로 쓰면 done 기록이 막힌다).
6. (migration·리치텍스트) 골격의 SafeHtml 허용 태그·속성을 **골격 단계에서** 서버 정제기(`HtmlContentValidator` 류)와 같게 맞춘다 — slice 로 미루면 에디터 기능(정렬 등)을 빼야 한다.

## B. slice 개발

입력: `slices.yaml` 의 `screens`, brief §6 화면 목록이 가리키는 피그마/스토리보드 원문, (migration) 그 화면의 레거시 화면 템플릿, `<target_dir>/docs/api/<slice>.yaml`(+ depends_on 계약), `frontend/CONVENTIONS.md`.

### B-0. (migration) 레거시 화면 템플릿을 화면 근거로 쓴다
AS-IS 화면 템플릿(FTL·JSP·Thymeleaf 등)과 그 안의 스크립트는 화면 근거다. 이관 화면의 필드·검증 문구·버튼·행 이동 분기·화면 간 차이는 대부분 템플릿에만 있다
(실측 2026-10-07: 템플릿 근거 변환이 판정 가능 항목의 약 90% 를 재현, 템플릿 없이 서버 응답에 이동 주소를 맡긴 다른 변환본은 약 50%).
- 근거 우선순위: 확정된 디자인(피그마·스토리보드) > 레거시 화면 템플릿 > 계약. 디자인이 레이아웃만 바꾸면 항목·검증·분기는 템플릿을 따른다. 둘이 충돌하면 판단 기록(JD)으로 남긴다.
- 템플릿 전수: include 조각(위치·페이징 등), 템플릿 안 `<script>` 의 검증 문구(글자 그대로)·이벤트·행 이동 함수, 서버가 템플릿을 고르는 분기(컨트롤러의 화면 이름 결정만 - 서비스 로직은 읽지 않는다).
- 화면 하나의 템플릿을 여러 화면이 공유하거나(유형 코드별 분기) 한 화면이 템플릿 여럿으로 갈리면, 화면 정의서에 "화면 ↔ 템플릿 ↔ 진입 코드" 대응표를 둔다.
- 도달하지 못하는 템플릿(허용 코드 밖에서만 고르는 시안, 고정 문구·빈 선택지·목록에 없는 열)은 근거로 쓰지 않고 판단 기록에 "도달 불가 시안" 으로 남긴다. 그 화면은 근거 부족이다.
- 템플릿 스크립트의 결함(문법 오류로 안 붙는 링크, 정의되지 않은 함수 호출, 잘못된 선택자로 비는 값)도 동작이다. 차세대 원칙(AS-IS 그대로, 개선 금지)에 따라 재현하고 판단 기록에 `semantic` 으로 남긴다. 개선은 RR 로만.
- 템플릿에는 있는데 계약에 없는 값·호출(선택지 조회 ajax, 세션 속성 등)은 B-1 규칙대로 RR + 목.
- 기대 동작 spec(§B-4-1)을 쓰는 에이전트에게도 같은 템플릿을 근거로 준다. 화면별 항목표(위치·안내 문구·검색 필드·검증 문구·목록 열·행 이동·페이징·빈 목록·버튼·권한별 차이·화면 간 차이)를 먼저 만들면 spec·검토·5단계 화면 대조가 같은 기준을 쓴다.

### B-1. 화면 분석
- 화면마다: 화면ID, 라우트, 구성 요소(목록/폼/상세/모달), 입력 필드와 검증 규칙, 버튼→API 매핑, 상태(로딩/빈/에러), 권한.
- 결과를 `<target_dir>/docs/screens/<slice>.md` 에 표로 남긴다 (8단계 화면정의서 원천).
- 디자인 근거에는 있는데 계약에 API 가 없으면 → RR (`target_stage: 2, target_layer: backend/api`). 화면을 막지 말고 해당 부분만 TODO 주석 + 목 응답으로 두고 진행.

### B-2. API 클라이언트·타입
- 계약에서 타입을 **생성**한다 (프로필의 생성 도구). 손으로 타입을 옮겨 적지 않는다.
- slice 의 API 함수는 `features/<slice>/api/` 에. 공통 클라이언트를 거친다.

### B-3. 화면·컴포넌트
- 라우트는 `features/<slice>/routes.tsx` 에 정의하고 `app/router` 에서 **slice 등록 한 줄**만 추가한다 (병렬 충돌 최소화. 등록 줄 추가는 공용 파일 예외로 허용).
- 폼 검증 규칙은 계약의 스키마 제약(required/min/max/pattern)과 화면 근거를 합친다.
- 상태: 서버 상태와 클라이언트 상태를 분리(프로필). 전역 상태는 인증·레이아웃 정도만.
- 접근성·반응형은 디자인 근거가 요구하는 수준까지.

### B-4. 단위테스트
- 컴포넌트: 렌더·입력 검증·버튼 클릭 시 API 호출(목) — 화면당 최소 1개, 검증 규칙마다 1개.
- API 함수: 응답 매핑·에러 처리.
- 계약 기반 목 서버(프로필: msw)를 써서 실제 응답 스키마로 테스트한다.

### B-4-1. 잠긴 기대 동작 테스트 (pipeline-core §18, 선택)
- `verification.locked_spec` 이 `off` 가 아니면 behavior-spec-writer 가 화면 정의·스토리보드·OpenAPI 계약만 보고 `src/features/<slice>/__spec__/<slice>/` 에
  화면 동작 테스트(입력 검증·버튼 동작·오류 표시 위치·권한별 노출)를 먼저 쓰고 잠근다. frontend-developer 는 spec 을 읽기만 한다.

### B-6. 화면 검증 — Playwright (pipeline-core §19, config `verification.visual.enabled`)
- 화면·상태(빈 목록·데이터 있음·검증 오류·권한 없음·로딩 실패)마다 `e2e/<slice>/*.spec.ts` 에 테스트 1개:
  DOM 단언(필드·버튼·문구) → 콘솔 오류 0 → 네트워크 4xx/5xx 0(의도한 오류 시나리오 제외) → `await expect(page).toHaveScreenshot('<slice>-<화면>-<상태>.png')`.
- 기준 이미지는 새 화면일 때 한 번만 만든다. 이후 실패는 ui-verifier 가 판정한다. developer 가 실패를 없애려고 기준 이미지를 갱신하지 않는다.

### B-5. 상품화 품질 — 문서화 주석·콘솔 (`tools/quality.py` 가 같은 기준으로 점검)
- TS-DOC-PAGE: 페이지 컴포넌트(`pages/*Page.tsx`) 파일 첫 줄에 `/** 화면ID SCR-xxx · 화면명 · slice <id> */`.
- TS-DOC-API: `api/`·`hooks/`·`use*.ts` 의 export 함수에 `/** 호출 API(operationId) · 반환 의미 · 오류 처리 방식 */`.
- TS-CONSOLE: `console.log/debug/info` 를 남기지 않는다. 필요하면 골격 `logger` 를 쓴다.
- NO-EMOJI(critical): 화면 문구·i18n 리소스·주석·테스트 이름에 이모지 금지. 아이콘이 필요하면 디자인 근거의 아이콘 컴포넌트(SVG)를 쓴다 (pipeline-core §15).
- 주석은 한글로, 화면 근거(화면정의서·스토리보드의 ID)와 계약 operationId 를 연결하는 데 쓴다.
- 보고 전에 `python tools/quality.py <target_dir> --files <바꾼 파일…>` 로 점검한다.

## C. 게이트 및 산출물
- 상품화 품질: `gate.py check` 의 `productization` 훅이 바꾼 파일을 §B-5 규칙으로 점검한다(critical 차단, major 는 strict 설정 시 차단).
- **실제 브라우저 렌더 게이트**: 리치텍스트 에디터·차트·트리처럼 DOM/타이머에 의존하는 서드파티 컴포넌트를 쓰는 화면은 jsdom 단위 테스트만으로 통과시키지 않는다. slice 게이트에 Playwright(Chromium) 렌더 스모크 1건(화면 로드 → 콘솔 에러 0 → 핵심 요소 표시)을 포함한다 — jsdom 이 못 잡은 Tiptap 로드 즉시 크래시(RR-0017, 운영 빌드도 재현) 사례. Playwright 는 `tests/integration/package.json` 격리 설치(5단계와 공유) 또는 앱 devDependency. 스모크 spec 은 typecheck 게이트에 포함(선언 파일이 해석되는 설치 경로 필수).
- 빌드 + 린트 + 타입체크 + 단위테스트. 실패하면 고치고 재실행. 못 고치면 `blocked`.
- 공용 파일 변경 필요 사항은 `workspace/<project>/reports/common-candidates.md` 에 (frontend 섹션).
- 레포트 `workspace/<project>/reports/<ts>_stage4_<slice>_frontend.md`: 화면 표, 컴포넌트 목록, 사용한 API, 테스트 결과, 계약 부족(RR 목록), 근거 부족.
  끝에 `pa-meta` 블록을 붙이고 `python tools/gate.py check --stage 4 --slice <id>` 를 통과시킨다 (pipeline-core §9).
  `gates[]` 에 build·lint·typecheck·test 와 (해당되면) 브라우저 스모크를 각각 명령·종료 코드·개수로 적는다.
  테스트는 JUnit XML 을 남기도록 실행하고(vitest: `--reporter=default --reporter=junit --outputFile.junit=reports/junit.xml`,
  Playwright: `--reporter=junit`) 그 경로를 `results` 에 적는다 — `gate.py` 가 결과 파일로 개수를 대조한다.
- jsdom 으로는 판별력이 없다고 확인된 동작(브라우저 렌더·타이머 경합 등)을 스모크로도 덮지 못했으면
  확인 필요 항목으로 넘긴다: `python tools/gate.py oi new --stage 4 --slice <id> --kind unverified --severity <sev> … --target 5` (pipeline-core §11).
- `state.yaml → slices.<slice>.stage4_frontend: done|blocked`.

## D. reviewer 체크리스트 (frontend-reviewer)
0. (migration) 분기→테스트 대응표의 각 행이 **렌더 단언**을 포함하는지(요청 파라미터 검증 ≠ 렌더 검증). 인라인으로 `error.message` 를 표시하는 query/mutation 은 `meta.silent` 여부 대조(이중 알림) — `role="alert"` 를 렌더하는 컴포넌트가 쓰는 query 를 **전수** grep(상세만 보고 목록을 빠뜨린 사례). 골격 SafeHtml 허용 목록 ↔ 서버 정제기 ↔ 에디터 확장 3자 대조 — 테스트는 개수·부정 단언이 아니라 spec 표의 **리터럴 고정**이어야 하고, 렌더 측 훅이 저장값을 변형하는 항목(rel·target·URI 정책)은 표에 "렌더 시 추가 변형" 행으로 명시. 화면 문서 오류 표에 "표시 위치(필드 아래/상단)" 열.
1. 계약 준수: 요청/응답 타입이 생성 타입인가. 손으로 만든 타입·하드코딩 URL 이 없는가.
2. 화면 근거: 디자인의 필드·버튼·상태가 모두 구현됐는가. 근거 없는 UI 가 있는가. (migration) 레거시 템플릿 항목표가 있으면 항목별로 대조하고, 행 이동 분기·검증 문구·화면 간 차이를 우선 본다(§B-0).
3. 경계: 다른 slice 의 내부 컴포넌트/상태를 직접 import 하지 않는가. 공용 파일 수정이 등록 한 줄 외에 없는가.
4. 상태·에러: 로딩/빈/에러 상태 처리, 인증 만료 처리.
5. 테스트: 화면·검증 규칙마다 테스트가 있는가. skip 된 테스트가 없는가.
6. 기본 보안: `dangerouslySetInnerHTML`, 토큰의 localStorage 평문 저장(프로필 규칙과 대조), URL 에 민감정보.
7. `CONVENTIONS.md` 위반.
8. 상품화 품질(§B-5): `python tools/quality.py <target_dir> --files <changed_files>` 결과 확인 + 도구가 못 보는 것(화면ID 가 화면 근거와 맞는가, 주석이 operationId 를 정확히 가리키는가).

## 공통 금지 — 이모지 (전역 규칙 · 예외 없음)

이 방법론으로 만드는 모든 산출물(소스 주석·로그 문구·Mapper 쿼리 주석·yml 주석·DDL `COMMENT`·테스트 이름·레포트·매핑표)에 이모지를 쓰지 않는다.
규칙 전문과 강제 장치는 `pipeline-core §15`. 이 문서의 규칙과 충돌하면 전역 규칙이 우선한다.
