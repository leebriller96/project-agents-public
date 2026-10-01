# _javasrc.py — Java 소스 경량 구조 분석 (외부 의존성 없음)
#
# 목적: AS-IS 공통 클래스를 "어느 업무가 어떤 메서드를 쓰는가" 로 쪼개 보려면 호출 관계가 필요하다.
#       완전한 컴파일러 수준 해석(오버로드 타입 추론·람다·리플렉션)은 하지 않는다. 대신 레거시 코드에서
#       흔한 패턴 — 정적 호출(Util.m), 필드·지역변수·파라미터 타입을 통한 호출(dao.m), 상속 메서드의
#       무한정 호출(m(), this.m(), super.m()), 인자 개수로 오버로드 구분, SqlSession 문자열 id — 를 결정적으로 읽는다.
#       해석하지 못한 호출(동적 SQL id 등)은 버리지 않고 unresolved 로 돌려준다(추측 금지).

import re

KEYWORDS = {"if", "for", "while", "switch", "catch", "synchronized", "return", "new", "throw", "super",
            "this", "else", "do", "try", "finally", "case", "assert", "instanceof", "class", "interface"}
MODIFIERS = r"(?:public|protected|private|static|final|abstract|synchronized|native|default|transient|volatile|strictfp)"
SQL_METHODS = {"selectOne", "selectList", "selectMap", "selectCursor", "insert", "update", "delete",
               "queryForObject", "queryForList", "queryForMap", "queryForPaginatedList"}

TYPE_DECL_RE = re.compile(r"\b(class|interface|enum|record)\s+(\w+)([^{;]*)\{")
ANNOT_RE = re.compile(r"@[\w.]+(\s*\([^()]*(\([^()]*\)[^()]*)*\))?")
IDENT_CALL_RE = re.compile(r"(?<![\w.$])([A-Za-z_$][\w$]*)\s*\(")
QUAL_CALL_RE = re.compile(r"(?<![\w$])([A-Za-z_$][\w$]*)\s*\.\s*([A-Za-z_$][\w$]*)\s*\(")
LOCAL_DECL_RE = re.compile(r"(?<![\w.$])([A-Z][\w$]*(?:\s*<[^;(){}]*?>)?(?:\s*\[\s*\])*)\s+([a-z_$][\w$]*)\s*(?==|;|:|,|\))")


def mask(text):
    """주석은 공백으로, 문자열·문자 리터럴의 내용은 '_' 로 바꾼다. 길이·줄 위치는 원문과 같다."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = " "
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        elif c in "\"'":
            if text.startswith('"""', i):   # 텍스트 블록
                j = text.find('"""', i + 3)
                j = n if j < 0 else j + 3
                for k in range(i + 3, max(i + 3, j - 3)):
                    if out[k] != "\n":
                        out[k] = "_"
                i = j
                continue
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            for k in range(i + 1, min(j, n)):
                out[k] = "_"
            i = j + 1
        else:
            i += 1
    return "".join(out)


def match_close(s, i, open_ch="(", close_ch=")"):
    """s[i] 가 여는 괄호일 때 짝이 되는 닫는 괄호 위치."""
    depth = 0
    for j in range(i, len(s)):
        if s[j] == open_ch:
            depth += 1
        elif s[j] == close_ch:
            depth -= 1
            if depth == 0:
                return j
    return len(s) - 1


def split_top(s, sep=","):
    """괄호·꺾쇠 바깥의 구분자로 나눈다."""
    parts, depth, cur = [], 0, ""
    for ch in s:
        if ch in "(<[{":
            depth += 1
        elif ch in ")>]}":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return parts


def base_type(t):
    """'List<Map<String,Object>>' → 'List', 'com.x.Foo[]' → 'com.x.Foo'"""
    t = re.sub(r"<.*>", "", t or "").replace("[]", "").replace("...", "").strip()
    t = re.sub(r"\b(final)\b", "", t).strip()
    return t.split()[-1] if t.split() else ""


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


class Method:
    def __init__(self, name, params, start, body_start, body_end, sig, is_static, is_ctor, annotations=()):
        self.annotations = sorted(set(annotations))
        self.name, self.params, self.start = name, params, start
        self.body_start, self.body_end = body_start, body_end
        self.sig, self.is_static, self.is_ctor = sig, is_static, is_ctor

    @property
    def arity(self):
        return len(self.params)

    @property
    def key(self):
        return f"{self.name}/{self.arity}"

    @property
    def span(self):
        """원문에서 이 메서드가 차지하는 범위 [시작, 끝) — 앞 주석·어노테이션·시그니처·본문을 포함한다.
        본문 없는 메서드(interface·abstract)는 시그니처 끝(';' 앞)까지다."""
        if self.body_end is not None:
            return self.start, self.body_end + 1
        return self.start, self.start + len(self.sig)


class JavaClass:
    def __init__(self, file, package, imports, kind, name, extends, implements):
        self.file, self.package, self.imports = file, package, imports
        self.kind, self.name = kind, name
        self.extends, self.implements = extends, implements
        self.annotations = []  # 클래스 어노테이션(단순명)
        self.fields = {}      # 필드명 → 타입(단순명)
        self.methods = []     # Method
        self.text = ""
        self.masked = ""
        self.head_start = 0   # 클래스 선언부(앞 주석·어노테이션 포함) 시작 위치
        self.body_open = 0    # 클래스 본문 여는 중괄호 위치
        self.end = 0          # 클래스 본문 닫는 중괄호 다음 위치

    @property
    def span(self):
        """원문에서 이 타입이 차지하는 범위 [시작, 끝)."""
        return self.head_start, self.end

    @property
    def fqn(self):
        return f"{self.package}.{self.name}" if self.package else self.name


def annotations_of(seg):
    """선언 앞 어노테이션의 단순명 목록 (@org.x.Foo → Foo)."""
    return [a.rsplit(".", 1)[-1] for a in re.findall(r"@([\w.]+)", seg) if a != "interface"]


def parse_params(s):
    out = []
    for p in split_top(s):
        p = ANNOT_RE.sub(" ", p).strip()
        p = re.sub(r"\bfinal\b", "", p).strip()
        if not p:
            continue
        toks = p.split()
        if len(toks) < 2:
            continue
        out.append((" ".join(toks[:-1]), toks[-1]))
    return out


def parse_file(path, text):
    """파일의 최상위 타입들을 JavaClass 목록으로."""
    m = mask(text)
    pkg = re.search(r"^\s*package\s+([\w.]+)\s*;", m, re.M)
    package = pkg.group(1) if pkg else ""
    imports = re.findall(r"^\s*import\s+(?:static\s+)?([\w.*]+)\s*;", m, re.M)
    classes = []
    # 깊이 0 에서 타입 선언을 찾는다
    depth, i = 0, 0
    while i < len(m):
        ch = m[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif depth == 0:
            dm = TYPE_DECL_RE.match(m, i) if m[i].isalpha() and (i == 0 or not (m[i - 1].isalnum() or m[i - 1] in "_$")) else None
            if dm:
                header = dm.group(3)
                ext = re.search(r"\bextends\s+([\w.<>, ]+?)(?:\bimplements\b|$)", header)
                imp = re.search(r"\bimplements\s+([\w.<>, ]+)$", header.strip())
                extends = [base_type(x) for x in split_top(ext.group(1))] if ext else []
                implements = [base_type(x) for x in split_top(imp.group(1))] if imp else []
                c = JavaClass(path, package, imports, dm.group(1), dm.group(2), extends, implements)
                head_start = max(m.rfind(";", 0, i), m.rfind("}", 0, i)) + 1
                c.annotations = annotations_of(m[head_start:i])
                c.text, c.masked = text, m
                open_pos = dm.end() - 1
                close_pos = match_close(m, open_pos, "{", "}")
                c.head_start, c.body_open, c.end = head_start, open_pos, close_pos + 1
                parse_members(c, m, open_pos + 1, close_pos)
                if dm.group(1) == "record":
                    add_record_accessors(c, header, dm.start())
                classes.append(c)
                i = close_pos + 1
                continue
        i += 1
    return classes


def add_record_accessors(c, header, pos):
    """record 구성요소(`record Meta(String userId, long ts)`)는 같은 이름의 무인자 접근자를 암묵적으로 갖는다.
    본문에 명시적으로 다시 선언한 접근자는 그대로 두고, 없는 것만 추가한다
    (실측: 대체 대응으로 적은 record 접근자 7건을 계약 이행 검사가 '없다' 로 판정)."""
    if "(" not in header:
        return
    inner = header[header.index("(") + 1:]
    depth, close = 0, None
    for k, ch in enumerate(inner):
        if ch in "(<":
            depth += 1
        elif ch in ")>":
            if ch == ")" and depth == 0:
                close = k
                break
            depth -= 1
    if close is None:
        return
    declared = {(mt.name, mt.arity) for mt in c.methods}
    for comp in split_top(inner[:close]):
        toks = re.sub(r"@\w+(\([^)]*\))?", " ", comp).split()
        if len(toks) < 2:
            continue
        name = toks[-1]
        if (name, 0) in declared:
            continue
        c.methods.append(Method(name, [], pos, None, None, f"{' '.join(toks[:-1])} {name}()", False, False))


def parse_members(c, m, start, end):
    """클래스 본문(깊이 1)의 필드·메서드·생성자."""
    seg_start = start
    i = start
    while i < end:
        ch = m[i]
        if ch == ";":
            seg = m[seg_start:i]
            decl = ANNOT_RE.sub(" ", seg).strip()
            am = re.match(rf"^(?:{MODIFIERS}\s+)*(?:<[^>]*>\s*)?([\w.<>\[\],? ]+?)\s+(\w+)\s*\((.*)\)\s*(?:throws\s+[\w.,\s]+)?$", decl, re.S)
            if am and "=" not in decl.split("(")[0]:
                # 본문 없는 메서드(interface·abstract)
                c.methods.append(Method(am.group(2), parse_params(am.group(3)), seg_start + (len(seg) - len(seg.lstrip())),
                                        None, None, " ".join(decl.split()), "static" in decl.split("(")[0], False,
                                        annotations_of(seg)))
            else:
                fm = re.match(rf"^(?:{MODIFIERS}\s+)*([\w.<>\[\],? ]+?)\s+(\w+)\s*(?:=.*)?$", decl, re.S)
                if fm and "(" not in fm.group(1):
                    c.fields[fm.group(2)] = base_type(fm.group(1))
            seg_start = i + 1
            i += 1
            continue
        if ch == "{":
            seg = m[seg_start:i]
            close = match_close(m, i, "{", "}")
            if seg.count("(") > seg.count(")"):
                # 어노테이션 인자 안의 배열 초기화(@RequestMapping(value={"/a.do", "/b.do"})) — 멤버 본문이 아니다.
                # 본문으로 읽으면 그 뒤 첫 ';'(다음 메서드 본문 안)까지 건너뛰어 메서드가 통째로 빠진다(실측: 실전 AS-IS 12개 파일).
                i = close + 1
                continue
            decl = ANNOT_RE.sub(" ", seg).strip()
            if TYPE_DECL_RE.search(seg + "{"):
                pass   # 내부 클래스: 호출 분석 대상에서 제외(최상위 멤버만)
            else:
                mm = re.match(rf"^(?:{MODIFIERS}\s+)*(?:<[^>]*>\s*)?(?:([\w.<>\[\],? ]+?)\s+)?(\w+)\s*\((.*)\)\s*(?:throws\s+[\w.,\s]+)?$", decl, re.S)
                if mm:
                    name = mm.group(2)
                    is_ctor = mm.group(1) is None and name == c.name
                    if mm.group(1) is not None or is_ctor:
                        c.methods.append(Method("<init>" if is_ctor else name, parse_params(mm.group(3)),
                                                seg_start + (len(seg) - len(seg.lstrip())), i, close,
                                                " ".join(decl.split()), "static" in decl.split("(")[0], is_ctor,
                                                annotations_of(seg)))
                elif re.match(r"^(static)?$", decl):
                    pass   # 초기화 블록
                else:
                    # 필드 초기화에 익명 클래스·배열 초기화가 붙은 경우
                    fm = re.match(rf"^(?:{MODIFIERS}\s+)*([\w.<>\[\],? ]+?)\s+(\w+)\s*=", decl, re.S)
                    if fm:
                        c.fields[fm.group(2)] = base_type(fm.group(1))
                    semi = m.find(";", close)
                    close = semi if semi >= 0 else close
            seg_start = close + 1
            i = close + 1
            continue
        i += 1


def body_calls(c, meth):
    """메서드 본문의 호출 목록.

    반환: [(kind, receiver, name, arity, pos, extra)]
      kind = "qual"(receiver.name(...)) | "bare"(name(...)) | "this" | "super"
      extra = SQL 메서드면 첫 인자 원문(문자열 리터럴이면 따옴표 포함)
    """
    if meth.body_start is None:
        return [], {}
    m, t = c.masked, c.text
    s, e = meth.body_start, meth.body_end
    body = m[s:e]
    local_types = {n: base_type(ty) for ty, n in meth.params}
    for lm in LOCAL_DECL_RE.finditer(body):
        local_types.setdefault(lm.group(2), base_type(lm.group(1)))
    calls = []
    taken = set()
    for qm in QUAL_CALL_RE.finditer(body):
        recv, name = qm.group(1), qm.group(2)
        open_pos = s + qm.end() - 1
        close = match_close(m, open_pos)
        args = split_top(m[open_pos + 1:close])
        arity = len(args)
        extra = None
        if name in SQL_METHODS and args:
            a0 = m[open_pos + 1:close]
            first = split_top(a0)[0]
            off = open_pos + 1 + (len(first) - len(first.lstrip()))
            extra = t[off:off + len(first.strip())]
        kind = "this" if recv == "this" else "super" if recv == "super" else "qual"
        calls.append((kind, recv, name, arity, open_pos, extra))
        taken.add(s + qm.start(2))
    for bm in IDENT_CALL_RE.finditer(body):
        name = bm.group(1)
        pos = s + bm.start(1)
        if pos in taken or name in KEYWORDS:
            continue
        # new X(...) 생성자 호출과 a.b(...) 한정 호출(위에서 처리)은 제외한다
        prev = m[s:pos].rstrip()
        if re.search(r"(?<![\w$])new$", prev) or prev.endswith("."):
            continue
        open_pos = s + bm.end() - 1
        close = match_close(m, open_pos)
        calls.append(("bare", None, name, len(split_top(m[open_pos + 1:close])), open_pos, None))
    return calls, local_types


# ---------------------------------------------------------------- 요청 매핑 (컨트롤러 진입점)

MAPPING_ANNOTATIONS = {"RequestMapping": None, "GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT",
                       "DeleteMapping": "DELETE", "PatchMapping": "PATCH"}
MAPPING_RE = re.compile(r"@(?:[\w]+\.)*(" + "|".join(MAPPING_ANNOTATIONS) + r")(?![\w$])")
HTTP_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS")


def _split_offsets(s):
    """괄호 바깥 쉼표로 나눈 (시작, 끝) 목록. s 는 마스킹된 문자열(문자열 안 쉼표가 없다)."""
    out, depth, cur = [], 0, 0
    for i, ch in enumerate(s):
        if ch in "({[":
            depth += 1
        elif ch in ")}]":
            depth -= 1
        elif ch == "," and depth == 0:
            out.append((cur, i))
            cur = i + 1
    if s[cur:].strip():
        out.append((cur, len(s)))
    return out


def request_mappings(text, masked, start, end):
    """text[start:end] 에 붙은 요청 매핑 어노테이션을 읽는다.

    반환: [(http 메서드 목록, 경로 목록)] — 경로가 없으면 [""], http 메서드 지정이 없으면 [].
    문자열 상수 참조(@RequestMapping(PATH)) 처럼 리터럴이 아닌 경로는 읽지 않는다(추측 금지).
    """
    out = []
    for am in MAPPING_RE.finditer(masked, start, end):
        fixed = MAPPING_ANNOTATIONS[am.group(1)]
        j = am.end()
        while j < end and masked[j].isspace():
            j += 1
        paths, methods = [], []
        if j < end and masked[j] == "(":
            close = match_close(masked, j)
            am_m, am_t = masked[j + 1:close], text[j + 1:close]
            for a, b in _split_offsets(am_m):
                part_m, part_t = am_m[a:b], am_t[a:b]
                nm = re.match(r"^\s*(\w+)\s*=", part_m)
                name = nm.group(1) if nm else "value"
                if name in ("value", "path"):
                    paths.extend(re.findall(r'"([^"]*)"', part_t))
                elif name == "method":
                    methods.extend(x for x in re.findall(r"(?<![\w$])([A-Z]+)(?![\w$])", part_m) if x in HTTP_METHODS)
        if fixed:
            methods = [fixed]
        out.append((sorted(set(methods)), paths or [""]))
    return out
