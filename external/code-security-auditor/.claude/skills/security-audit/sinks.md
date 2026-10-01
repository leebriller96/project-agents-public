# 언어별 Source / Sink 치트시트

데이터 흐름 추적의 출발점(source)과 도착점(sink)을 언어·프레임워크별로 정리한 목록입니다.
코드를 정독할 때 아래 식별자를 먼저 검색(grep)하고, 각 sink 에 도달하는 입력이 어디서 오는지 역추적합니다.
(`grep -rn` 으로 빠르게 후보를 뽑되, **발견은 반드시 흐름을 확인한 뒤** 보고합니다.)

표기: `sink` 옆의 CWE 는 그 sink 에 외부 입력이 검증 없이 도달했을 때의 대표 분류입니다.

---

## Python

### Source (외부 입력)
| 프레임워크 | 식별자 |
|-----------|--------|
| Flask | `request.args`, `request.form`, `request.json`, `request.get_json()`, `request.data`, `request.files`, `request.headers`, `request.cookies`, `request.values`, URL 변수(`<name>`) |
| Django | `request.GET`, `request.POST`, `request.body`, `request.FILES`, `request.META`, `request.COOKIES`, URL kwargs, `Form.cleaned_data` 이전 값 |
| FastAPI | 경로/쿼리 파라미터 함수 인자, `Body`, `Header`, `Cookie`, `Request.json()`, `UploadFile` |
| 공통 | `sys.argv`, `os.environ`, `input()`, `socket.recv`, 파일 읽기(`open().read()`), 외부 API 응답(`requests.get().json()`), 메시지 큐 컨슈머 페이로드, DB 에서 읽은 값(저장형 공격 시) |

### Sink
| 분류 | 식별자 | CWE |
|------|--------|-----|
| SQL | `cursor.execute(f"..."/"..."+x/"...".format)`, `cursor.executescript`, SQLAlchemy `text()`, `session.execute(str)`, Django `.raw()`, `.extra()`, `RawSQL`, `connection.cursor().execute` | 89 |
| NoSQL | pymongo `find({"$where": x})`, 외부 JSON 을 그대로 쿼리 dict 로 | 943 |
| OS 명령 | `os.system`, `os.popen`, `subprocess.*(shell=True)`, `subprocess.*([...])` 에 인자 미검증, `commands.*`, `pexpect.spawn` | 78 |
| 코드 실행 | `eval`, `exec`, `compile`, `__import__`, `importlib.import_module`, `getattr(obj, user)` 로 메서드 호출 | 94/95 |
| 역직렬화 | `pickle.load(s)`, `cPickle`, `shelve`, `marshal.loads`, `yaml.load` (Loader 미지정/`FullLoader`/`UnsafeLoader`), `jsonpickle.decode`, `dill` | 502 |
| 템플릿 | `render_template_string(user)`, `Template(user)` (Jinja2/Mako/Django `Template`), `Markup(user)`, `\|safe` 필터, `autoescape=False` | 1336 / 79 |
| 파일 경로 | `open()`, `os.path.join(base, user)` (절대경로·`..` 미차단), `send_file`, `shutil.*`, `os.remove`, `zipfile.extractall` (Zip Slip), `tarfile.extractall` | 22 |
| SSRF | `requests.*`, `urllib.request.urlopen`, `httpx`, `aiohttp` 의 URL 에 외부 입력 | 918 |
| 리다이렉트 | `redirect(user)`, `HttpResponseRedirect(user)`, `RedirectResponse(user)` | 601 |
| XML | `xml.etree`, `lxml.etree.parse` (resolve_entities 기본 True), `xml.dom.minidom`, `xml.sax` — `defusedxml` 미사용 | 611 |
| 암호 | `hashlib.md5/sha1` 로 비밀번호, `random.*` 로 토큰/세션, `AES.MODE_ECB`, 고정 IV/솔트, `verify=False`, `ssl._create_unverified_context` | 327/328/330/295 |
| 로깅 | `logging.*(f"{password}")`, 예외 메시지에 자격증명, `print(request.headers)` | 532 |
| 정규식 | `re.match(user_pattern, ...)`, 중첩 수량자 패턴에 긴 외부 입력 | 1333 |
| 설정 | `app.run(debug=True)`, `DEBUG = True`, `ALLOWED_HOSTS = ['*']`, `SECRET_KEY = "..."`, `CORS(app, origins="*", supports_credentials=True)` | 489/942/798 |
| 인가 | 라우트에 `@login_required` 만 있고 객체 소유권 검사 없음, `Model.objects.get(id=request.GET['id'])` | 639/862 |
| Mass Assignment | `Model(**request.json)`, `obj.__dict__.update(request.json)`, Django `ModelForm` 에 `fields = '__all__'` | 915 |

---

## JavaScript / TypeScript (Node.js, 브라우저)

### Source
| 환경 | 식별자 |
|------|--------|
| Express/Koa/Fastify | `req.query`, `req.params`, `req.body`, `req.headers`, `req.cookies`, `req.files`, `ctx.request.*`, `request.query` |
| Next.js/Nuxt | `searchParams`, `params`, `req.body`(API route), `getServerSideProps` 의 `context.query`, Server Action 인자 |
| 브라우저 | `location.*`(`hash`, `search`), `document.referrer`, `postMessage` 의 `event.data`, `localStorage`, `window.name`, `fetch()` 응답 |
| 공통 | `process.argv`, `process.env`, `fs.readFile` 결과, WebSocket 메시지, DB 값(저장형) |

### Sink
| 분류 | 식별자 | CWE |
|------|--------|-----|
| SQL | `connection.query("..." + x)`, `` `...${x}` `` 템플릿 리터럴 쿼리, Sequelize `sequelize.query(str)`, `literal()`, Knex `.raw(str)`, TypeORM `.query(str)`, Prisma `$queryRawUnsafe` | 89 |
| NoSQL | Mongoose/MongoDB `find(req.body)`, `find({ $where: x })`, 쿼리 객체에 사용자 JSON 그대로 (`{ $gt: "" }` 연산자 주입) | 943 |
| OS 명령 | `child_process.exec`, `execSync`, `spawn(cmd, {shell:true})`, `execFile` 에 인자 미검증 | 78 |
| 코드 실행 | `eval`, `new Function`, `vm.runInContext`/`runInNewContext`, `setTimeout(string)`, 동적 `require(user)`/`import(user)` | 94/95 |
| XSS (서버) | `res.send(html + user)`, `res.write`, EJS `<%- %>`, Pug `!{}`, Handlebars `{{{ }}}`, React `dangerouslySetInnerHTML`, Vue `v-html`, Angular `bypassSecurityTrust*` | 79 |
| XSS (DOM) | `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `$(...).html()`, `location.href = user` (`javascript:`), `eval` | 79 |
| 역직렬화 | `node-serialize` `unserialize`, `js-yaml` `load` (< 4.0 기본 unsafe), `JSON.parse` 결과를 deep merge/`Object.assign` 으로 병합 | 502 / 1321 |
| Prototype Pollution | 재귀 merge/extend/clone 함수에 외부 객체, `obj[key] = value` 에 `__proto__`·`constructor` 키 미차단, `lodash.merge` (< 4.17.12) | 1321 |
| 파일 경로 | `fs.readFile(path.join(base, user))`, `res.sendFile(user)`, `express.static` 옵션 오설정, `fs.createReadStream`, `unzip`/`tar` 추출 (Zip Slip) | 22 |
| SSRF | `fetch(user)`, `axios.get(user)`, `http.request(user)`, `got(user)`, `node-fetch` | 918 |
| 리다이렉트 | `res.redirect(user)`, `res.location(user)`, `router.push(user)` (프로토콜 상대 `//evil` 주의) | 601 |
| JWT | `jwt.verify(token, secret, { algorithms 미지정 })`, `jwt.decode()` 만 쓰고 verify 없음, 약한/하드코딩 secret, `alg: none` 허용 | 347 |
| 암호 | `crypto.createHash('md5'/'sha1')` 비밀번호, `Math.random()` 토큰, `crypto.createCipher` (deprecated), `rejectUnauthorized: false`, `NODE_TLS_REJECT_UNAUTHORIZED=0` | 327/330/295 |
| 정규식 | `new RegExp(user)`, 중첩 수량자 `(a+)+`, `(.*a){n}` 패턴에 긴 입력 | 1333 |
| 쿠키/세션 | `res.cookie(name, v, { httpOnly/secure/sameSite 미설정 })`, `express-session` `secret: "keyboard cat"`, `cookie: { secure: false }` | 614/1004 |
| CORS | `cors({ origin: true, credentials: true })`, `origin: req.headers.origin` 반사, `Access-Control-Allow-Origin: *` + credentials | 942 |
| Mass Assignment | `Model.create(req.body)`, `Object.assign(user, req.body)`, `User.update(req.body)` | 915 |
| 로깅 | `console.log(req.body)`(비밀번호 포함), `winston`/`pino` 에 토큰 | 532 |

---

## Java / Kotlin (Spring, Servlet, Android)

### Source
| 환경 | 식별자 |
|------|--------|
| Spring MVC/WebFlux | `@RequestParam`, `@PathVariable`, `@RequestBody`, `@RequestHeader`, `@CookieValue`, `@ModelAttribute`, `HttpServletRequest.getParameter/getHeader/getInputStream/getCookies` |
| Servlet/JAX-RS | `request.getParameter*`, `@QueryParam`, `@FormParam`, `@HeaderParam`, `MultipartFile` |
| Android | `Intent.getExtras/getStringExtra`, `Uri.getQueryParameter`, `ContentProvider` 인자, `WebView` `addJavascriptInterface`, `BroadcastReceiver` |
| 공통 | `main(String[] args)`, `System.getenv`, 파일/소켓 입력, JMS/Kafka 메시지, DB 값(저장형) |

### Sink
| 분류 | 식별자 | CWE |
|------|--------|-----|
| SQL | `Statement.execute*(str)`, `createStatement()`, `PreparedStatement` 에 문자열 연결 후 바인딩 없음, JPA `createQuery("..."+x)`, `createNativeQuery`, MyBatis `${}` (`#{}` 는 안전), Spring `JdbcTemplate.query(str+x)`, Hibernate HQL 연결 | 89 |
| LDAP | `DirContext.search(filter+x)`, `LdapTemplate.search(str)` | 90 |
| OS 명령 | `Runtime.exec(str)`, `ProcessBuilder(cmd)` 에 `sh -c`, Apache `CommandLine.parse` | 78 |
| 코드 실행 | `ScriptEngine.eval`, `GroovyShell.evaluate`, SpEL `ExpressionParser.parseExpression(user)`, OGNL, `Class.forName(user)`, `Method.invoke` 에 사용자 이름 | 94/917 |
| 역직렬화 | `ObjectInputStream.readObject`, `XMLDecoder.readObject`, XStream `fromXML`, Jackson `enableDefaultTyping`/`@JsonTypeInfo` + 다형성, Fastjson `parseObject` (autoType), SnakeYAML `new Yaml().load` (< 2.0), Kryo, Hessian, `readUnshared` | 502 |
| 템플릿/SSTI | Thymeleaf `__${...}__` 전처리, FreeMarker `new()` 내장, Velocity, Pebble 에 사용자 템플릿 문자열 | 1336 |
| XSS | JSP `<%= %>`, `${}` (escapeXml=false), Thymeleaf `th:utext`, `Html.raw`, `response.getWriter().print(user)` | 79 |
| 파일 경로 | `new File(base, user)`, `Paths.get(user)`, `FileInputStream`, `ResourceLoader.getResource("file:"+user)`, `ZipInputStream` 엔트리 이름 그대로 (Zip Slip), `MultipartFile.transferTo(new File(originalFilename))` | 22 |
| SSRF | `new URL(user).openConnection()`, `RestTemplate.getForObject(user)`, `WebClient.get().uri(user)`, `HttpClient.send`, `OkHttp` | 918 |
| 리다이렉트 | `response.sendRedirect(user)`, `"redirect:" + user`, `RedirectView(user)` | 601 |
| XML | `DocumentBuilderFactory` / `SAXParserFactory` / `XMLInputFactory` / `TransformerFactory` / `SchemaFactory` 에서 `FEATURE_SECURE_PROCESSING`·`disallow-doctype-decl` 미설정, `Unmarshaller` (JAXB) | 611 |
| 암호 | `MessageDigest.getInstance("MD5"/"SHA-1")` 비밀번호, `Cipher.getInstance("AES")`(기본 ECB) / `"AES/ECB/..."`, `new Random()`/`Math.random()` 토큰, 고정 IV, `TrustManager` 전부 신뢰, `HostnameVerifier` 항상 true, `SSLContext("SSL")` | 327/328/330/295 |
| JWT | `Jwts.parser().parse(token)` (서명 미검증 `parse` vs `parseClaimsJws`), `JWT.decode` 만 사용, 하드코딩 secret, `alg: none` 허용 | 347 |
| 인가 | `@PreAuthorize` 누락, `SecurityConfig` 의 `permitAll()` 범위, 서비스 계층에서 소유권 미검사 `repository.findById(id)`, Actuator 엔드포인트 노출 | 639/862/284 |
| Mass Assignment | `@RequestBody User user` → 그대로 `save()` (role/isAdmin 필드 포함), `BeanUtils.copyProperties(request, entity)`, `@ModelAttribute` 에 `setAllowedFields` 없음 | 915 |
| 로깅 | `log.info("login " + password)`, 예외 스택에 자격증명, `printStackTrace()` 응답 출력 | 532/209 |
| 설정 | `spring.h2.console.enabled=true`, `server.error.include-stacktrace=always`, `csrf().disable()` (세션 인증에서), `cors().allowedOrigins("*")` + credentials, `management.endpoints.web.exposure.include=*` | 489/352/942 |
| Android | `WebView.setJavaScriptEnabled(true)` + `addJavascriptInterface`, `MODE_WORLD_READABLE`, 내보내기된(`exported=true`) 컴포넌트에 인가 없음, `SharedPreferences` 평문 토큰, `allowBackup=true` | 749/276/312 |

---

## 공통 — 어떤 언어든 확인할 것

- **인증 우회 경로**: 미들웨어/필터가 특정 경로 패턴(`/api/internal`, `/actuator`, `/debug`)을 제외하는지, 대소문자·인코딩·후행 슬래시로 우회되는지.
- **비밀값**: `password`, `passwd`, `secret`, `token`, `api_key`, `apikey`, `private_key`, `BEGIN RSA`, `AKIA`, `ghp_`, `sk_live_`, `xox[bp]-` 패턴을 소스·설정·IaC·CI 파일(`.env`, `docker-compose.yml`, `*.tf`, `.github/workflows`)에서 검색.
- **의존성**: 매니페스트·락파일 버전을 `pip-audit`/`npm audit`/OWASP Dependency-Check 로 조회. 락파일이 없으면 그 자체를 Low 로 보고.
- **에러 처리**: 전역 예외 핸들러 유무, 스택트레이스가 응답에 실리는지, 실패 시 `fail-open` 인지 (예: 권한 조회 예외 → 허용).
- **레이스/논리**: 잔액·재고·쿠폰처럼 "검사 후 갱신"이 트랜잭션/락 없이 두 단계로 나뉘는 곳, 상태 머신 단계 건너뛰기, 음수·오버플로 입력.
