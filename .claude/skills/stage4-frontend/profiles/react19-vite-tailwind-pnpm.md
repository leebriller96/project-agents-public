# Frontend 프로필: react19-vite-tailwind-pnpm

`config/project.yaml → stack.frontend.profile: react19-vite-tailwind-pnpm`. 차세대(migration) 프로젝트용 — React 19 / Vite 7 / TypeScript 5.9 / Tailwind 3 / **pnpm 워크스페이스**(user·admin 앱 분리) / 세션+CSRF 인증 / Tiptap·마크다운 에디터 / SSE.
`react-ts.md` 의 규칙(라우트 자동 등록·등록 훅·zod 전수 테스트·URL 정규화·gcTime 0+reset·비밀번호 refine·vitest/jsdom 알려진 문제·무거운 라이브러리 lazy)은 **그대로 상속**하고, 아래는 차이점만.

## 기본 구조 (pnpm 워크스페이스)
```
<target_dir>/apps/
├── pnpm-workspace.yaml          packages: ["user", "admin", "shared"]
├── package.json                 루트 스크립트: pnpm -r lint/typecheck/test/build, gen:api
├── shared/                      공용 패키지 (@app/shared): api 클라이언트·CSRF·UI 컴포넌트(Figma 기준)·hooks·types(생성)
├── user/                        사용자 앱 (Vite) — src/app, src/features/<slice>
└── admin/                       관리자 앱 (Vite) — src/app, src/features/<slice>
```
- slice 는 backend 소유 모듈과 같은 앱(user 또는 admin)에만 화면을 둔다. 양쪽에 화면이 있으면 slice 를 나눈다.
- 계약 타입: `pnpm gen:api -- <slice>` → `shared/src/api/types/<slice>.d.ts` (앱이 공유).
- 명령: `pnpm install --frozen-lockfile`, `pnpm -r lint`, `pnpm -r typecheck`, `pnpm -r test --run`, `pnpm -r build`, 앱 단위는 `pnpm --filter @app/user test --run src/features/<slice>` (**`--` 금지** — pnpm 이 `--` 를 vitest 인자로 넘겨 경로 필터가 무효화되고 전체가 실행됨, 실측 F-17).

## 규약 차이
- **인증**: 세션 쿠키(JSESSIONID, httpOnly) + **CSRF**: `shared/api/client.ts` 인터셉터가 `XSRF-TOKEN` 쿠키를 읽어 상태 변경 요청에 `X-CSRF-TOKEN` 헤더 부착. 403 CSRF 실패는 토큰 재요청 후 1회 재시도. 토큰을 JS 에서 다루지만 인증 토큰이 아니라 CSRF 토큰(설계상 허용).
- **메뉴 권한**: 서버가 `/api/v1/auth/me` 에 허용 메뉴 코드 목록을 내려주고, 사이드 메뉴·라우트 가드(`RequireMenu('MENU_CD')`)가 그 목록으로 판단. 롤만으로 판단하지 않는다(사번 허용 목록 포함).
- **스타일**: Tailwind 3 + 자체 공용 컴포넌트(`shared/ui` — Figma 기준). MUI 안 씀. 디자인 토큰은 `tailwind.config` theme 에. 화면 근거가 ftl(서버 렌더링 템플릿)이면 **ftl 의 필드·버튼·검증·조건 분기를 화면 근거로 추출**(`docs/screens/<slice>.md` 에 ftl 파일:라인 근거).
- **에디터**: 리치텍스트는 Tiptap(허용 마크 화이트리스트 = 서버 `HtmlContentValidator` 와 동일), 마크다운은 별도 에디터 컴포넌트. AS-IS CKEditor/SmartEditor2 HTML 은 서버가 정제해 내려주고 FE 는 `dangerouslySetInnerHTML` **금지** — 정제된 HTML 도 `shared/ui/SafeHtml`(DOMPurify) 로만 렌더.
- **SSE**: 소스가 들어온 경우만 — `shared/api/sse.ts`(EventSource + 재연결 + AbortController), 테스트는 msw `http.get` 스트림 응답.
- **jQuery 제거**: AS-IS 인라인 스크립트(dataTables·AUIGrid·FusionCharts·dtree)는 화면 근거로만 읽고 **동일 기능을 React 컴포넌트로**(표 = 공용 DataTable, 차트 = recharts, 트리 = 공용 Tree). 라이브러리 이름이 아니라 **동작**(정렬·필터·페이징·행 선택·차트 종류)을 매핑표에 적는다.
- **폼 전송 → REST**: AS-IS `<form method=post action=…>` 는 계약의 JSON API 로. 파일 업로드는 `multipart/form-data` 단일 요청(2단계 temp 업로드 폐기).
- **레거시 URL**: AS-IS `.do`/`.jsp` 스타일 URL 은 라우트 표에 "AS-IS URL → TO-BE 라우트" 대응을 남긴다(북마크·외부 링크 대비, 리다이렉트는 nginx — 소스 없으면 범위 외).

## 테스트 규약 차이
- 워크스페이스라 앱별 vitest 설정. `shared` 의 클라이언트·CSRF 인터셉터·SafeHtml 은 shared 에서 테스트.
- CSRF 재시도(403 → 토큰 갱신 → 1회 재시도) 테스트 필수. 메뉴 가드는 허용 목록 유무 각 1건.
- ftl 근거 화면은 **ftl 의 조건 분기(`<#if>`) 마다** 렌더 테스트 1건(AS-IS 동작 보존의 FE 측 근거).

## 알려진 주의 (실측 2026-09-22, sample2 골격)
- 실측 조합: React 19.3 / react-router 7.18 / TanStack Query 5.103 / RHF 7.88 + zod 4.6 / zustand 5 / axios 1.20 / DOMPurify 3.4(`Config` named import) / Vite 7.3 + plugin-react 5.2(6 은 Vite 8 전용) / TS 5.9 / Tailwind 3.4 / vitest 4.1(3.2.7 은 @vitest/mocker GHSA-82fw-gwwq-j7x9 — 4.1.11+ 로, sample2 회차 4 실측: 커스텀 jsdom 환경만 `vitest/runtime` + `viteEnvironment` 로 바꾸면 3 → 4 이행에 테스트 변경 0) + jsdom 26 + msw 2.15 / ESLint 9 + typescript-eslint 8.70 / openapi-typescript 7.13 / pnpm 12.5. 최신 메이저(react-router 8·Vite 8·vitest 5·TS 7·Tailwind 4·ESLint 10)는 지정 메이저를 넘으므로 **지정 메이저 내 최신**으로 고정하고 `pnpm-workspace.yaml` `catalog:` 로 단일 관리.
- **pnpm 12**: `minimumReleaseAge`(기본 24h) 가 갓 배포된 버전을 거부하고 제외 목록을 yaml 에 자동 기록 → 직전 버전으로 내리고 하위 의존은 `overrides` 고정. `allowBuilds` 없으면 esbuild·msw postinstall 차단(`ERR_PNPM_IGNORED_BUILDS`) → 명시 승인. `corepack enable` 이 EPERM 이면 `corepack pnpm …` 직접 호출. 루트 스크립트에 `--` 를 넘기면 스크립트 인자로 들어가므로 gen:api 스크립트가 `--` 를 무시하게.
- Vite dev 프록시 포트는 지시가 아니라 `server/*/src/main/resources/application-local.yml` 실측값(예 18090/18091).
- react-refresh 규칙: 순수 함수·상수는 컴포넌트 파일에서 분리. Windows 는 파일명 대소문자만 다른 두 파일이 충돌(`ClockContext.tsx`/`clockContext.ts`) → 이름을 다르게.
- **RHF 체크박스**: `<input type="checkbox" value="Y">` 는 RHF 값이 boolean 이 아니게 되어 zod 가 조용히 실패 → value 속성 없이 boolean 으로 두고 전송 시 `Y/N` 변환. **zod 4** 객체 `refine`(종료≥시작 등)은 필드 오류가 있으면 평가되지 않음 → 교차 검증 테스트는 필드가 전부 유효한 입력으로. **date input** 은 `user.type` 이 무효 → `fireEvent.change`.
- **msw + jsdom FormData**: jsdom 의 `FormData` 를 msw 가 multipart 로 못 읽음 → 테스트 setup 에서 Node `FormData/Blob/File` 로 스텁(골격 `shared/test` 헬퍼로). jsdom 에 `Range` 없음(Tiptap) → 폴리필.
- react-hooks 7 규칙: `use` 로 시작하는 순수 함수명은 hooks 규칙에 걸림(`useYnLabel`→`usageLabel`), `set-state-in-effect` 는 `key` 재마운트로 회피.
- **리치텍스트 허용 마크는 3자 동일**(서버 정제기 = FE SafeHtml = 에디터 확장) — 하나라도 다르면 "저장은 되는데 표시가 지워지는" 결함(예: `style` 정렬). 에디터 확장을 넣기 전에 SafeHtml 이 그 속성을 통과시키는지 실측.
- **msw 핸들러는 선등록 우선** — `/notices/:noticeId` 패턴이 `/notices/top` 을 가로챈다 → 고정 경로 핸들러를 파라미터 경로보다 먼저 등록.
- user-event `click` 은 `element.click()` 을 거치므로 앵커 click 을 전역 목으로 막으면 onClick 이 안 발화 → `download` 속성 앵커만 가로채기.
- **Write 도구도** ` ` 이스케이프를 실제 문자로 저장해 `no-irregular-whitespace` lint 에 걸림(실측 2회) — 유니코드 이스케이프가 든 파일은 Edit 로 부분 수정하거나 `String.fromCharCode` 사용. zod 4 `max().refine()` 은 max 실패 시에도 refine 평가(객체 refine 과 다름). Tiptap 3 링크 출력은 `rel="noopener noreferrer nofollow"`, `ol[start]` 는 start≠1 일 때만.
- Write/heredoc 의 ` ` 류 이스케이프가 도구에서 실제 문자로 바뀌어 저장될 수 있음 → 특수 문자는 `String.fromCharCode(0xa0)` 로 명시.
- 운영 QueryClient `retry: 1` 은 404 도 재시도(약 1초 지연) → AS-IS 가 즉시 오류 화면인 단건 조회는 `retry: (n, e) => e.status !== 404 && n < 1`.
- AS-IS 인라인 스크립트가 `form.submit()` 이면 "폼 전체 값 전송" 이 동작의 일부 — 분류 change·정렬·페이지 콜백이 URL 값만 merge 하면 입력 중 값이 유실된다. 화면 문서의 스크립트 동작 표에 **전송 필드 범위** 열을 둔다.
- **Tiptap `useEditor` 크래시(원인 확정)**: `@tiptap/react` `EditorInstanceManager` 가 `immediatelyRender`(기본 true)로 렌더 중 editor 를 만들고 `scheduleDestroy()`(1ms) 를 예약 → passive effect 가 늦으면 `destroy()`+`setEditor(null)` 되고 같은 커밋의 value 동기화 effect 가 파괴된 editor 로 `getHTML()`. 수정: `immediatelyRender: false` + effect 마다 `isDestroyed` 가드 + 값 전달은 `onUpdate` 콜백만 + extensions/editorProps 마운트당 고정. **jsdom 은 이 경합을 재현 못 함**(act 밖 `createRoot` 로도) → 판별력 없는 테스트는 만들지 않고 Chromium 스모크(`apps/<app>/tests/browser/*.smoke.spec.ts`, `test:browser` 스크립트, BE 없이 `page.route` 목, dev + `vite preview` 양쪽)로 게이트. Playwright 는 `tests/integration` 격리 설치 재사용 시 tsconfig `paths` 를 `@playwright/test/index.mjs` 로(`.js` 는 CJS).
- `immediatelyRender:false` 부작용: `useEditorState` 스냅샷이 첫 transaction 까지 `editor:null` → `onCreate` 에서 transaction 1회. 브라우저 스모크 spec 은 **typecheck 게이트에 포함**(별도 `tsc -p tests/browser/tsconfig.json --noEmit` 또는 Playwright 를 앱 devDependency 로 — `paths`→`index.mjs` 우회는 선언 파일이 없어 typecheck 이 통째로 빠짐). `webServer.command` 는 `node node_modules/vite/bin/vite.js` 직접 호출(`pnpm exec` 는 재링크를 유발). CSRF 쿠키 우선은 스모크에서 요청 헤더 값 단언으로 증명.
- **수정 전 판별력 검증**은 `git worktree` + 별도 `pnpm install`(store 공유)로. node_modules 를 junction 으로 공유하면 `pnpm exec` 가 실제 repo 의 링크 94개를 worktree 경로로 바꿔 놓는다(실측·복구함).
- (구 기록) 로드 직후 `Cannot read properties of null (reading 'cached')` at `Editor.getHTML` — `useEditor` 의 1ms 파괴 예약과 passive effect(`getHTML` 호출) 경합. jsdom 테스트는 통과하고 실제 브라우저(dev·preview)에서만 재현 → 에디터 인스턴스 접근은 `editor?.isDestroyed` 확인 + `onUpdate` 콜백으로 값 전달, `immediatelyRender`/StrictMode 조합 실측. Chromium 렌더 스모크 필수(§C).
- DOMPurify `ALLOWED_URI_REGEXP` 는 `URI_SAFE_ATTRIBUTES` 밖 **모든** 속성 값에 적용(`start="3"`·`target` 까지 제거) → 비-URI 속성을 `ADD_URI_SAFE_ATTR` 로 등록해 `href`/`src` 로 한정.
- Tiptap 테스트에서 `editor.commands.*` 를 직접 호출할 때는 `await act(() => …)` 로 감싼다(act 경고).
- 골격이 만드는 `features/sample` 은 첫 slice 가 들어오면 삭제(공통 후보 F-05).

## 알려진 주의
- React 19: `forwardRef` 불필요, `use()`·Actions 는 팀 규약 확정 전엔 안 씀(근거 부족). react-router 7(데이터 라우터) 기본.
- Vite 7 + vitest 4: `react-ts.md` 의 jsdom 문제 동일(커스텀 환경은 `vitest/runtime` 의 `builtinEnvironments`, `viteEnvironment: 'client'`). pnpm 은 `shamefully-hoist` 없이 워크스페이스 의존 명시.
- Tailwind 3 → 4 는 breaking(설정 방식) — config 가 3 이면 3 으로 고정.

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
