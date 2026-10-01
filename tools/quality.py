#!/usr/bin/env python3
# quality.py — 생성 소스(target_dir)의 상품화 품질 정적 점검: 문서화 주석·로깅·Mapper 주석
#
# 목적: 빌드·테스트가 통과해도 "납품 가능한 코드" 인지는 따로 봐야 한다.
#       클래스 Javadoc·공개 메서드 Javadoc·서비스 로거·traceId(MDC)·Mapper XML 주석·콘솔 출력 금지 같은
#       규칙은 에이전트마다, 회차마다 들쭉날쭉해지기 쉬우므로 문장 대신 도구로 같은 기준을 매번 적용한다.
#       같은 입력이면 항상 같은 결과(정렬된 JSON)를 낸다 — 회차 간 비교(diff)가 가능하다.
#
# 사용법:
#   python tools/quality.py                              # config 의 target_dir 전체 점검
#   python tools/quality.py <target_dir>                 # 경로 지정
#   python tools/quality.py <target_dir> --files a.java b.xml   # 지정 파일만 (gate 가 changed_files 로 호출)
#   python tools/quality.py --format json                # 기계용 출력 (회차 간 diff 용)
#   python tools/quality.py --strict                     # major 도 차단(종료 코드 1)
#   python tools/quality.py --rules                      # 규칙 목록
#
# 종료 코드: 0 통과 · 1 차단(critical, --strict 면 major 포함) · 2 입력 오류
# 의존성: 없음 (정규식 기반 정적 점검. 파서가 아니므로 오탐 시 규칙 예외는 `quality:ignore <규칙ID>` 주석으로 표시)

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from _emoji import find_emoji  # noqa: E402

SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2}

# 이모지 금지 규칙을 적용하는 텍스트 파일 확장자 — 코드·Mapper·설정(yml·properties)·DDL·문서·화면 전부
EMOJI_EXTS = (".java", ".kt", ".kts", ".groovy", ".gradle", ".xml", ".yml", ".yaml", ".properties", ".sql",
              ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".css", ".scss", ".html", ".md", ".json",
              ".sh", ".ftl", ".jsp", ".txt", ".env", ".conf", ".toml", ".ini")

# 규칙 카탈로그: ID → (심각도, 설명, 조치)
RULES = {
    "NO-EMOJI": ("critical", "이모지가 있다 (코드 주석·로그 문구·Mapper 쿼리 주석·yml 주석·DDL COMMENT·문서 포함)",
                 "텍스트로 바꾼다 (예: 완료·주의·[의미차이:태그명]). 테스트·설정 파일도 예외 없음"),
    "JAVA-DOC-TYPE": ("major", "최상위 타입(class·interface·enum·record)에 Javadoc 이 없다",
                      "타입 선언 위에 /** 역할 한 줄 + (해당 시) 요구사항 ID·slice */ 를 단다"),
    "JAVA-DOC-METHOD": ("major", "Controller·Service·Mapper 의 공개 메서드에 Javadoc 이 없다",
                        "/** 동작 요약, @param, @return, (있으면) @throws 와 업무 규칙 ID */ 를 단다. @Override 구현은 인터페이스 문서를 따른다"),
    "JAVA-LOGGER": ("major", "서비스·예외 처리기·배치 클래스에 로거가 없다",
                    "@Slf4j 또는 private static final Logger log = LoggerFactory.getLogger(...) 를 두고 상태 변경·예외를 기록한다"),
    "JAVA-CONSOLE": ("critical", "System.out/err 출력 또는 printStackTrace() 를 쓴다",
                     "로거(log.info/log.error(\"...\", e))로 바꾼다 — 운영 로그 수집·마스킹 경로를 우회한다"),
    "JAVA-LOG-SENSITIVE": ("critical", "로그 인자에 민감정보(비밀번호·토큰·주민번호·카드번호) 변수가 들어간다",
                           "값을 빼거나 마스킹 유틸을 거친다. 식별자는 사번·ID 등 비민감 키만 남긴다"),
    "JAVA-LOG-CONCAT": ("minor", "로그 메시지를 문자열 + 로 조립한다",
                        "log.info(\"처리 완료 id={}\", id) 처럼 {} 자리표시자를 쓴다 (레벨 비활성 시 조립 비용 없음)"),
    "JAVA-EMPTY-CATCH": ("major", "예외를 기록·재던지기 없이 삼키는 빈 catch 블록",
                         "log.warn/error 로 남기거나 도메인 예외로 감싸 던진다. 의도된 무시는 사유 주석을 단다"),
    "JAVA-NO-MDC": ("major", "요청 추적 ID(MDC traceId)를 넣는 곳이 없다",
                    "골격에 요청 필터(OncePerRequestFilter)로 MDC.put(\"traceId\", …) 와 응답 헤더 전달을 둔다"),
    "JAVA-NO-LOGBACK": ("minor", "logback-spring.xml 이 없다 (프로파일별 로그 레벨·파일 롤링·패턴 미정의)",
                        "src/main/resources/logback-spring.xml 에 콘솔/파일 appender·traceId 패턴·프로파일별 레벨을 둔다"),
    "MAPPER-DOC-FILE": ("major", "Mapper XML 파일 머리 주석이 없다",
                        "<mapper> 위에 <!-- 업무명 · 대상 테이블 · slice · (migration) AS-IS 원본 경로 --> 를 둔다"),
    "MAPPER-DOC-STMT": ("major", "Mapper statement(select·insert·update·delete)에 설명 주석이 없다",
                        "각 statement 바로 위에 <!-- 목적 · 요구사항 ID · (migration) AS-IS statement id·의미차이 태그 --> 를 둔다"),
    "TS-CONSOLE": ("major", "프론트엔드 소스에 console.log/debug/info 가 남아 있다",
                   "제거하거나 공통 logger 유틸(운영 빌드에서 비활성)로 바꾼다"),
    "TS-DOC-API": ("minor", "API 클라이언트·훅의 export 함수에 JSDoc 이 없다",
                   "/** 호출 API(operationId)·반환 의미 */ 를 단다"),
    "TS-DOC-PAGE": ("minor", "페이지 컴포넌트 파일 머리에 화면ID·화면명 주석이 없다",
                    "파일 첫 줄에 /** 화면ID SCR-xxx · 화면명 · slice */ 를 둔다"),
}

SKIP_DIRS = {"node_modules", "build", "target", "dist", ".gradle", ".git", ".idea", "out", "bin",
             "coverage", ".next", ".turbo", "generated", "__generated__"}
IGNORE_RE = re.compile(r"quality:ignore\s+([A-Z0-9-]+(?:\s*,\s*[A-Z0-9-]+)*)")

STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])\'')
TYPE_DECL_RE = re.compile(
    r"^(?:(?:public|protected|private|abstract|final|sealed|non-sealed|static|strictfp)\s+)*"
    r"(class|interface|enum|record|@interface)\s+(\w+)")
METHOD_RE = re.compile(
    r"^\s*((?:(?:public|protected|private|static|final|abstract|synchronized|default|native)\s+)*)"
    r"(?:<[^>]+>\s+)?[\w.$]+(?:<[^()]*?>)?(?:\[\])*\s+(\w+)\s*\(")
NOT_METHOD_START = re.compile(r"^\s*(return|new|if|for|while|switch|catch|else|throw|case|do|try)\b")
SENSITIVE_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|rawPassword|secret|clientSecret|token|accessToken|refreshToken|jwt|"
    r"jumin|juminNo|rrn|ssn|residentNo|cardNo|cardNumber|cvc|cvv|accountNo)\b")
LOG_CALL_RE = re.compile(r"\b(?:log|logger|LOG|LOGGER)\s*\.\s*(trace|debug|info|warn|error)\s*\(")


def rel(path, root):
    try:
        return os.path.relpath(path, root).replace(os.sep, "/")
    except ValueError:   # Windows 에서 드라이브가 다르면 상대경로가 없다
        return os.path.abspath(path).replace(os.sep, "/")


def ignored(lines, idx, rule):
    """해당 줄 또는 바로 윗줄에 `quality:ignore <규칙>` 주석이 있으면 예외 처리."""
    for j in (idx, idx - 1):
        if 0 <= j < len(lines):
            m = IGNORE_RE.search(lines[j])
            if m and rule in [r.strip() for r in m.group(1).split(",")]:
                return True
    return False


def ignored_emoji(lines, idx):
    """이모지는 예외를 허용하지 않는다 — quality:ignore 주석도 무시한다. (규칙 일관성을 위해 함수로 남겨 둔다)"""
    return False


def iter_files(root, files=None):
    """점검 대상 파일 목록(정렬). files 가 주어지면 그 파일만."""
    if files:
        out = []
        for f in files:
            p = f if os.path.isabs(f) else os.path.join(root, f)
            if os.path.isfile(p):
                out.append(os.path.normpath(p))
        return sorted(set(out))
    out = []
    for dp, dns, fns in os.walk(root):
        dns[:] = sorted(d for d in dns if d not in SKIP_DIRS and not d.startswith("."))
        for fn in fns:
            out.append(os.path.join(dp, fn))
    return sorted(out)


def is_test_path(rs):
    """target 기준 상대경로(앞에 / 를 붙인 형태)가 테스트 코드인가."""
    return ("/src/test/" in rs or "/__tests__/" in rs or "/tests/" in rs or "/e2e/" in rs
            or re.search(r"\.(test|spec)\.[jt]sx?$", rs) is not None)


# ---------------------------------------------------------------- Java

def java_code_lines(text):
    """주석·문자열을 걷어낸 코드 줄 목록과, 각 줄 시작 시점의 중괄호 깊이를 돌려준다."""
    lines = text.split("\n")
    code, depth_at = [], []
    in_block = False
    depth = 0
    for line in lines:
        depth_at.append(depth)
        s = line
        buf = ""
        i = 0
        while i < len(s):
            if in_block:
                end = s.find("*/", i)
                if end < 0:
                    i = len(s)
                    continue
                in_block = False
                i = end + 2
                continue
            if s.startswith("/*", i):
                in_block = True
                i += 2
                continue
            if s.startswith("//", i):
                break
            if s[i] == '"':
                m = STRING_RE.match(s, i)
                if m:
                    buf += '""'
                    i = m.end()
                    continue
            if s[i] == "'":
                m = STRING_RE.match(s, i)
                if m:
                    buf += "''"
                    i = m.end()
                    continue
            buf += s[i]
            i += 1
        code.append(buf)
        depth += buf.count("{") - buf.count("}")
    return lines, code, depth_at


def has_javadoc(lines, idx):
    """idx 줄 선언 바로 위(어노테이션·빈 줄 건너뜀)에 /** ... */ 가 있는가."""
    j = idx - 1
    paren = 0
    while j >= 0:
        s = lines[j].strip()
        if not s:
            j -= 1
            continue
        if s.endswith("*/"):
            k = j
            while k >= 0 and "/*" not in lines[k]:
                k -= 1
            return k >= 0 and "/**" in lines[k]
        # 여러 줄 어노테이션(@Operation(...)) 안쪽 줄은 건너뛴다
        paren += s.count(")") - s.count("(")
        if s.startswith("@") or paren > 0:
            if s.startswith("@"):
                paren = max(paren, 0)
            j -= 1
            continue
        return False
    return False


def ann(name):
    """어노테이션 정규식 — 단순명(@Service)과 완전 한정명(@org.springframework.stereotype.Service) 모두."""
    return re.compile(r"@(?:[\w$]+\.)*" + name + r"\b")


ADVICE_RE = ann(r"(?:Rest)?ControllerAdvice")
CONTROLLER_RE = ann(r"(?:Rest)?Controller")
MAPPER_ANN_RE = ann("Mapper")
SERVICE_RE = ann("Service")
SCHEDULED_RE = ann("Scheduled")
EXCEPTION_HANDLER_RE = ann("ExceptionHandler")
LOMBOK_LOG_RE = ann(r"(?:Slf4j|Log4j2|CommonsLog|Log|XSlf4j)")


def java_role(text, type_kind, type_name):
    """클래스 역할 판정: controller|service|mapper|advice|batch|None"""
    if ADVICE_RE.search(text) or EXCEPTION_HANDLER_RE.search(text):
        return "advice"
    if CONTROLLER_RE.search(text) or type_name.endswith("Controller"):
        return "controller"
    if MAPPER_ANN_RE.search(text) or (type_kind == "interface" and type_name.endswith("Mapper")):
        return "mapper"
    if SERVICE_RE.search(text) or re.search(r"Service(Impl)?$", type_name):
        return "service"
    if re.search(r"(Scheduler|Job|Batch|Listener|Consumer|Tasklet)$", type_name) or SCHEDULED_RE.search(text):
        return "batch"
    return None


def check_java(path, text, root, out, stats):
    lines, code, depth_at = java_code_lines(text)
    r = rel(path, root)
    type_kind = type_name = None
    type_idx = None
    for i, c in enumerate(code):
        if depth_at[i] == 0:
            m = TYPE_DECL_RE.match(c.strip())
            if m:
                type_kind, type_name, type_idx = m.group(1), m.group(2), i
                break
    if type_idx is None:
        return
    stats["java_types"] += 1
    if has_javadoc(lines, type_idx):
        stats["java_types_documented"] += 1
    elif not ignored(lines, type_idx, "JAVA-DOC-TYPE"):
        out.append(mk("JAVA-DOC-TYPE", r, type_idx + 1, f"{type_kind} {type_name}"))

    # 역할·로거 판정은 주석·문자열을 걷어낸 코드로 한다 (로그 문구 "annotated with @Mapper" 로 Mapper 판정된 오탐 사례)
    code_text = "\n".join(code)
    role = java_role(code_text, type_kind, type_name)
    is_interface = type_kind == "interface"

    # 공개 메서드 Javadoc (Controller·Service·Mapper)
    if role in ("controller", "service", "mapper"):
        for i, c in enumerate(code):
            if depth_at[i] != 1:
                continue
            s = c.strip()
            if not s or s.startswith("@") or NOT_METHOD_START.match(s) or TYPE_DECL_RE.match(s):
                continue
            m = METHOD_RE.match(c)
            if not m:
                continue
            head = c[:c.find("(")]
            if "=" in head:
                continue   # 필드 초기화식
            mods = m.group(1) or ""
            public = ("public" in mods) or (is_interface and "private" not in mods)
            if not public:
                continue
            # @Override 구현은 인터페이스 문서를 따른다
            prev = "\n".join(lines[max(0, i - 4):i])
            if "@Override" in prev:
                continue
            stats["public_methods"] += 1
            if has_javadoc(lines, i):
                stats["public_methods_documented"] += 1
            elif not ignored(lines, i, "JAVA-DOC-METHOD"):
                out.append(mk("JAVA-DOC-METHOD", r, i + 1, f"{type_name}.{m.group(2)}()"))

    # 로거
    if role in ("service", "advice", "batch") and not is_interface:
        has_logger = (LOMBOK_LOG_RE.search(code_text) or "LoggerFactory.getLogger" in code_text
                      or re.search(r"\bLogger\s+\w+\s*=", code_text))
        if not has_logger and not ignored(lines, type_idx, "JAVA-LOGGER"):
            out.append(mk("JAVA-LOGGER", r, type_idx + 1, f"{type_name} ({role})"))

    for i, c in enumerate(code):
        if re.search(r"\bSystem\s*\.\s*(out|err)\s*\.\s*print", c) or re.search(r"\.printStackTrace\s*\(", c):
            if not ignored(lines, i, "JAVA-CONSOLE"):
                out.append(mk("JAVA-CONSOLE", r, i + 1, lines[i].strip()[:100]))
        lm = LOG_CALL_RE.search(c)
        if lm:
            # 호출이 여러 줄에 걸치면 닫는 괄호까지 모은다
            call = c[lm.start():]
            k = i
            while call.count("(") > call.count(")") and k + 1 < len(code) and k - i < 6:
                k += 1
                call += " " + code[k]
            args_part = call[call.find("(") + 1:]
            sm = SENSITIVE_RE.search(args_part)
            if sm and not ignored(lines, i, "JAVA-LOG-SENSITIVE"):
                out.append(mk("JAVA-LOG-SENSITIVE", r, i + 1, f"인자 '{sm.group(1)}': {lines[i].strip()[:90]}"))
            raw_call = "\n".join(lines[i:k + 1])
            if re.search(r'\(\s*"(?:\\.|[^"\\])*"\s*\+', raw_call) and not ignored(lines, i, "JAVA-LOG-CONCAT"):
                out.append(mk("JAVA-LOG-CONCAT", r, i + 1, lines[i].strip()[:100]))

    joined = code_text
    for m in re.finditer(r"catch\s*\([^)]*\)\s*\{\s*\}", joined):
        ln = joined.count("\n", 0, m.start())
        # 원문에 사유 주석이 있으면(주석은 code 에서 지워졌으므로 원문으로 확인) 의도된 무시로 본다
        end_ln = joined.count("\n", 0, m.end())
        raw = "\n".join(lines[ln:end_ln + 1])
        if ("//" in raw or "/*" in raw) or ignored(lines, ln, "JAVA-EMPTY-CATCH"):
            continue
        out.append(mk("JAVA-EMPTY-CATCH", r, ln + 1, lines[ln].strip()[:100]))

    if "MDC.put" in code_text:
        stats["mdc_put"] += 1


# ---------------------------------------------------------------- Mapper XML

STMT_RE = re.compile(r"<(select|insert|update|delete)\b[^>]*?\bid\s*=\s*\"([^\"]+)\"", re.S)


def check_mapper(path, text, root, out, stats):
    r = rel(path, root)
    lines = text.split("\n")
    mpos = text.find("<mapper")
    stats["mapper_files"] += 1
    if "<!--" in text[:mpos]:
        stats["mapper_files_documented"] += 1
    else:
        ln = text.count("\n", 0, mpos)
        if not ignored(lines, ln, "MAPPER-DOC-FILE"):
            out.append(mk("MAPPER-DOC-FILE", r, ln + 1, "<mapper> 앞 머리 주석 없음"))
    for m in STMT_RE.finditer(text):
        stats["mapper_statements"] += 1
        before = text[:m.start()].rstrip()
        if before.endswith("-->"):
            stats["mapper_statements_documented"] += 1
            continue
        ln = text.count("\n", 0, m.start())
        if not ignored(lines, ln, "MAPPER-DOC-STMT"):
            out.append(mk("MAPPER-DOC-STMT", r, ln + 1, f"<{m.group(1)} id=\"{m.group(2)}\">"))


# ---------------------------------------------------------------- TypeScript

TS_EXPORT_FN_RE = re.compile(r"^export\s+(?:async\s+)?function\s+(\w+)|^export\s+const\s+(\w+)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\(|function|<)")


def check_ts(path, text, root, out, stats):
    r = rel(path, root)
    head = text[:400]
    if re.search(r"(?i)auto-?generated|@generated|do not (edit|make direct changes)", head):
        return
    lines = text.split("\n")
    in_block = False
    for i, line in enumerate(lines):
        s = line.strip()
        if in_block:
            if "*/" in s:
                in_block = False
            continue
        if s.startswith("/*") and "*/" not in s:
            in_block = True
            continue
        if s.startswith("//") or s.startswith("*"):
            continue
        if re.search(r"\bconsole\s*\.\s*(log|debug|info)\s*\(", line) and not ignored(lines, i, "TS-CONSOLE"):
            out.append(mk("TS-CONSOLE", r, i + 1, s[:100]))
    parts = r.split("/")
    base = parts[-1]
    in_api = any(p in ("api", "apis", "hooks") for p in parts[:-1]) or re.match(r"use[A-Z]\w*\.tsx?$", base)
    if in_api:
        for i, line in enumerate(lines):
            m = TS_EXPORT_FN_RE.match(line)
            if not m:
                continue
            stats["ts_exports"] += 1
            j = i - 1
            while j >= 0 and not lines[j].strip():
                j -= 1
            if j >= 0 and lines[j].strip().endswith("*/"):
                stats["ts_exports_documented"] += 1
            elif not ignored(lines, i, "TS-DOC-API"):
                out.append(mk("TS-DOC-API", r, i + 1, m.group(1) or m.group(2)))
    if "pages" in parts[:-1] and re.search(r"Page\.tsx$", base):
        stats["ts_pages"] += 1
        first = next((ln.strip() for ln in lines if ln.strip()), "")
        if first.startswith("/**") or first.startswith("//"):
            stats["ts_pages_documented"] += 1
        elif not ignored(lines, 0, "TS-DOC-PAGE"):
            out.append(mk("TS-DOC-PAGE", r, 1, base))


# ---------------------------------------------------------------- 실행

def mk(rule, file, line, detail):
    sev = RULES[rule][0]
    return {"rule": rule, "severity": sev, "file": file, "line": line, "detail": detail}


def empty_stats():
    return {k: 0 for k in ("java_types", "java_types_documented", "public_methods", "public_methods_documented",
                           "mapper_files", "mapper_files_documented", "mapper_statements",
                           "mapper_statements_documented", "ts_exports", "ts_exports_documented",
                           "ts_pages", "ts_pages_documented", "mdc_put", "logback_config")}


def ratio(a, b):
    return None if b == 0 else round(100.0 * a / b, 1)


def scan(root, files=None):
    """점검 실행. 결과 dict (결정적: 같은 입력이면 같은 출력)."""
    root = os.path.abspath(root)
    out, stats = [], empty_stats()
    full = not files
    has_java_main = False
    for p in iter_files(root, files):
        # 판정은 target 기준 상대경로로 한다 (target 이 build/·out/ 같은 이름의 폴더 아래 있어도 오판하지 않게)
        s = "/" + rel(p, root)
        if any(f"/{d}/" in s for d in SKIP_DIRS):
            continue
        if s.endswith("/logback-spring.xml") or s.endswith("/logback.xml"):
            stats["logback_config"] += 1
        text = None
        if s.lower().endswith(EMOJI_EXTS) or os.path.basename(s).startswith(".env"):
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            # 이모지 금지는 테스트 코드·리소스까지 예외 없이 본다
            for no, col, ch, cp in find_emoji(text):
                lines = text.split("\n")
                if not ignored_emoji(lines, no - 1):
                    out.append(mk("NO-EMOJI", rel(p, root), no, f"{cp} ({col}열): {lines[no - 1].strip()[:80]}"))
        if is_test_path(s):
            continue
        if text is None:
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
        if s.endswith(".java") and "/src/main/" in s:
            has_java_main = True
            if not s.endswith("/package-info.java") and not s.endswith("/module-info.java"):
                check_java(p, text, root, out, stats)
        elif s.endswith(".xml") and "<mapper" in text and "mybatis" in text.lower():
            check_mapper(p, text, root, out, stats)
        elif re.search(r"\.tsx?$", s) and not s.endswith(".d.ts") and "/src/" in s:
            check_ts(p, text, root, out, stats)
    # 프로젝트 단위 점검은 전체 스캔일 때만 (변경 파일만 볼 때는 판단할 수 없다)
    if full and has_java_main:
        if stats["mdc_put"] == 0:
            out.append(mk("JAVA-NO-MDC", ".", 0, "src/main 전체에서 MDC.put 을 찾지 못함"))
        if stats["logback_config"] == 0:
            out.append(mk("JAVA-NO-LOGBACK", ".", 0, "logback-spring.xml 없음"))
    out.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], f["rule"], f["file"], f["line"], f["detail"]))
    counts = {"critical": 0, "major": 0, "minor": 0}
    by_rule = {}
    for f in out:
        counts[f["severity"]] += 1
        by_rule[f["rule"]] = by_rule.get(f["rule"], 0) + 1
    coverage = {
        "java_type_javadoc_pct": ratio(stats["java_types_documented"], stats["java_types"]),
        "public_method_javadoc_pct": ratio(stats["public_methods_documented"], stats["public_methods"]),
        "mapper_file_comment_pct": ratio(stats["mapper_files_documented"], stats["mapper_files"]),
        "mapper_statement_comment_pct": ratio(stats["mapper_statements_documented"], stats["mapper_statements"]),
        "ts_api_jsdoc_pct": ratio(stats["ts_exports_documented"], stats["ts_exports"]),
        "ts_page_header_pct": ratio(stats["ts_pages_documented"], stats["ts_pages"]),
    }
    return {"schema": 1, "mode": "full" if full else "files", "counts": counts,
            "by_rule": dict(sorted(by_rule.items())), "coverage": coverage, "stats": stats, "findings": out}


def blocking(result, strict=False):
    c = result["counts"]
    return c["critical"] > 0 or (strict and c["major"] > 0)


def print_human(result, root, limit):
    print(f"대상: {root} ({'전체' if result['mode'] == 'full' else '지정 파일'})")
    c = result["counts"]
    print(f"발견: critical {c['critical']} · major {c['major']} · minor {c['minor']}")
    print("문서화·주석 비율(%):")
    for k, v in result["coverage"].items():
        print(f"  {k:<32} {'-' if v is None else v}")
    if result["by_rule"]:
        print("규칙별:")
        for rule, n in result["by_rule"].items():
            print(f"  {rule:<20} {n:>4}  {RULES[rule][1]}")
    for f in result["findings"][:limit]:
        print(f"- [{f['severity']}] {f['rule']} {f['file']}:{f['line']}  {f['detail']}")
    rest = len(result["findings"]) - limit
    if rest > 0:
        print(f"  … 외 {rest}건 (--limit 또는 --format json 으로 전체 확인)")


def main(argv=None):
    ap = argparse.ArgumentParser(description="생성 소스의 상품화 품질(문서화·로깅·Mapper 주석) 정적 점검")
    ap.add_argument("target", nargs="?", help="점검할 디렉토리 (생략 시 config 의 target_dir)")
    ap.add_argument("--files", nargs="+", help="이 파일들만 점검 (target 기준 상대경로 가능)")
    ap.add_argument("--format", choices=["human", "json"], default="human")
    ap.add_argument("--strict", action="store_true", help="major 도 차단")
    ap.add_argument("--limit", type=int, default=50, help="human 출력 시 상세 표시 건수")
    ap.add_argument("--rules", action="store_true", help="규칙 목록 출력")
    args = ap.parse_args(argv)
    if args.rules:
        for rid, (sev, desc, fix) in RULES.items():
            print(f"{rid:<20} [{sev}] {desc}\n{'':<20}  → {fix}")
        return 0
    root = args.target
    if not root:
        from _common import target_dir
        root = target_dir()
    if not root or not os.path.isdir(root):
        print(f"[quality] 점검 대상 디렉토리가 없다: {root}", file=sys.stderr)
        return 2
    result = scan(root, args.files)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_human(result, root, args.limit)
        print("결과: " + ("차단" if blocking(result, args.strict) else "통과"))
    return 1 if blocking(result, args.strict) else 0


if __name__ == "__main__":
    raise SystemExit(main())
