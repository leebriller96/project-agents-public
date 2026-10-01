# Frontend 프로필: react-ts

`config/project.yaml → stack.frontend.profile: react-ts` 일 때 적용한다. `stack.frontend.state`·`ui` 값이 있으면 그것을 우선한다.

## 기본 도구
- Vite + React 18 + TypeScript(strict)
- 라우팅: react-router v6
- 서버 상태: @tanstack/react-query / 클라이언트 상태: zustand (config `state` 값 우선)
- 폼: react-hook-form + zod
- UI: config `ui` 값 (기본 MUI). 디자인 근거가 커스텀이면 CSS Modules 또는 Tailwind 로 구현
- HTTP: axios 인스턴스 (`src/shared/api/client.ts`)
- 타입 생성: `openapi-typescript` — `npm run gen:api -- <slice>` 로 `docs/api/<slice>.yaml` → `src/shared/api/types/<slice>.d.ts`
- 테스트: vitest + @testing-library/react + msw
- 린트: eslint(typescript, react-hooks, import 순서) + prettier

## 디렉토리
```
frontend/src/
├── app/            main.tsx, router.tsx(slice 라우트 등록), providers.tsx, layout/
├── shared/
│   ├── api/        client.ts(공통 응답 언래핑·에러 매핑·인증 헤더), types/<slice>.d.ts (생성)
│   ├── ui/         공통 컴포넌트 (DataTable, FormField, Pagination, ConfirmDialog, PageHeader)
│   ├── auth/       인증 상태·가드
│   ├── hooks/ lib/ utils/
└── features/<slice>/
    ├── api/        <slice>Api.ts (axios 호출 + react-query 훅)
    ├── pages/      <ScreenName>Page.tsx  (화면ID 주석)
    ├── components/
    ├── model/      zod 스키마·로컬 타입·상수
    ├── routes.tsx
    └── __tests__/
```

## 골격 설계 메모 (병렬 개발 친화)
- **라우트 자동 등록**: `app/router.tsx` 가 `import.meta.glob('../features/*/routes.tsx', { eager: true })` 로 각 slice 의 `routes`/`publicRoutes` export 를 수집한다. slice 는 공용 파일을 한 줄도 수정하지 않는다.
- 로그아웃·세션 복원처럼 골격이 자리만 만들고 slice 가 구현하는 것은 `registerLogoutHandler(fn)` 같은 **등록 훅**으로 연결한다.
- `ApiError` 에 `fieldErrorMap()`(필드 오류 → react-hook-form `setError` 용), `api.download()`(첨부 파일 수신) 를 골격이 제공.

## 알려진 문제 (vitest + jsdom)
- react-router 데이터 라우터가 jsdom 의 `AbortSignal` 과 충돌 → 커스텀 환경(`src/test/jsdomEnvironment.ts`) 에서 Node 원본 `AbortController/AbortSignal` 유지.
- jsdom `Blob` 에 `text()` 없음·`instanceof` 불일치 → 클라이언트에서 덕 타이핑 + `FileReader` 폴백.
- `vitest/config` 는 `loadEnv` 를 재export 하지 않음 → `vite` 에서 import.
- recharts: jsdom 에 `ResizeObserver` 없음 → `<ResponsiveContainer initialDimension={{width, height}}>` 로 목 없이 SVG 렌더 검증. 0건 막대는 생성되지 않고 눈금 텍스트는 빈 문자열 — 데이터 변환 함수 테스트로 보완.
- `vi.stubGlobal('URL', {...})` 은 `new URL()` 을 깨뜨린다 → `Object.defineProperty(URL, 'createObjectURL', ...)` 로 메서드만 추가.
- 테스트용 QueryClient 는 `retry: false`, `gcTime: 0` (5xx 재시도가 실패 토스트 테스트를 수 초 지연시킨다) — 골격 `createTestQueryClient()` 가 보장.

- 무거운 라이브러리(차트·에디터·xlsx 파서)를 쓰는 화면은 라우트 `lazy()` + `build.rollupOptions.output.manualChunks` 로 분리 — 골격이 기본 설정을 둔다 (500 kB 청크 경고를 F-후보로 미루지 않는다).

## 규약
- 공통 응답 `{ success, data, error }` 는 `client.ts` 가 언래핑해 `data` 만 반환, 실패는 `ApiError { code, message, status }` 로 throw.
- 자격증명(비밀번호 등)을 보내는 mutation 은 `gcTime: 0` **+ 제출 완료(`finally`) 시 `mutation.reset()`** — `gcTime: 0` 은 observer 가 떨어진 뒤에만 작동하므로 실패 후 폼이 남아 있으면 variables 가 잔존한다. 테스트는 `queryClient.getMutationCache().getAll()` 이 빈 배열인지로 검증.
- 인증: 토큰 저장 위치는 brief 의 인증 방식에 따름. 기본은 httpOnly 쿠키(백엔드 발급). localStorage 저장은 brief 근거가 있을 때만.
- 라우트: `/<slice>/...`. 페이지 컴포넌트 상단 주석에 화면ID·화면명.
- 네이밍: 컴포넌트 PascalCase, 훅 `useXxx`, 파일은 컴포넌트명과 동일.
- 폼 검증: zod 스키마를 `model/` 에 두고 react-hook-form 과 연결. 메시지는 한글. 문자열 필수는 `.trim().min(1)` — `min(1)` 만 쓰면 공백만 통과해 BE `@NotBlank` 보다 느슨해진다. 단 **비밀번호처럼 값을 변환하면 안 되는 필드**는 `.refine(v => v.trim().length > 0)` 로 검사만 하고 원문을 보낸다(BE 는 trim 없이 해시 비교).
- 상태: 서버 데이터는 react-query 로만. 전역 zustand 는 인증·레이아웃(사이드바 등)만.
- 에러: `ApiError` → 공통 토스트. 401 은 로그인으로, 403 은 권한 안내 페이지.
- 스타일: UI 라이브러리 테마 토큰 사용. 인라인 스타일 지양.

## 명령
```
cd <target_dir>/frontend
npm ci
npm run gen:api -- <slice>   # 계약 → 타입
npm run lint && npm run typecheck
npm run test -- --run         # vitest
npm run build
```

## 테스트 규약
- msw 핸들러는 `features/<slice>/__tests__/handlers.ts` 에 계약 예시(example) 값으로 작성.
- 페이지 테스트: 렌더 → 필드 입력 → 제출 → 요청 바디/호출 여부 검증. 에러 응답 시 메시지 노출 검증.
- 폼 검증 테스트는 zod 스키마의 **모든 규칙**(required/min/max/pattern/format)을 표로 뽑아 각 1건. `maxLength` 속성이 막는 경우는 `removeAttribute('maxlength')` 후 붙여넣기 경로로 검증.
- URL(search params)에서 복원한 검색 조건도 같은 zod 스키마로 정규화한다(길이·enum). 입력 필드의 `maxLength` 는 UX 용이지 검증이 아니다.
- `it.skip`/`describe.skip` 금지. 못 만드는 테스트는 레포트에 사유.

## Playwright 화면 검증 (pipeline-core §19)
- 골격이 `frontend/playwright.config.ts` 를 만든다. 로컬 기동은 `webServer` 배열로: BE(test 프로파일·고정 포트, 헬스체크 URL) + FE(`vite preview` 운영 빌드).
  `reuseExistingServer: !process.env.CI`. 포트는 config·환경변수로 받는다(병렬 slice 충돌 방지).
- 결정적 스크린샷: `use: { viewport: { width: 1280, height: 800 }, locale: 'ko-KR', timezoneId: 'Asia/Seoul', colorScheme: 'light' }`,
  `expect.toHaveScreenshot: { animations: 'disabled', caret: 'hide', maxDiffPixelRatio: 0.01 }`, 폰트는 로컬 번들(웹폰트 지연 로드 금지),
  날짜·시각·난수 영역은 `mask: [page.getByTestId('now')]` 로 가린다. 서버 데이터는 fixture(시드)로 고정한다.
- 경로: `snapshotPathTemplate: '{testDir}/__screenshots__/{testFileDir}/{testFileName}/{arg}{ext}'` — 기준 이미지 경로에 slice 폴더가 들어가
  `tools/visual.py --slice` 가 slice 별로 고른다. 결과 파일: `reporter: [['list'], ['junit', { outputFile: 'reports/e2e-junit.xml' }]]`.
- 콘솔·네트워크 감시는 공용 fixture(`e2e/fixtures.ts`)로: `page.on('console')` 의 error, `page.on('response')` 의 4xx/5xx 를 모아 테스트 끝에 0 건 단언.
- 실행: `npx playwright test e2e/<slice>` (기준 이미지 최초 생성만 `--update-snapshots`). Chromium 은 설치본을 쓰고 다운로드하지 않는다.
