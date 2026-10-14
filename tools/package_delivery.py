#!/usr/bin/env python3
# package_delivery.py - 고객사 납품용 소스 패키지를 만든다 (8단계 마지막 작업, stage8-deliverables §4)
#
# 배경(2026-10-12): 납품은 "소스만" 이다. 개발 중 쓰던 md 문서와 파이프라인 흔적(판단 기록 번호, 의미 차이 표지,
#       AS-IS 파일:줄 참조, 에이전트 용어)이 주석에 수천 건 남아 있는데, 공유 저장소에서 지우면 개발자끼리 쓰는 문서와
#       근거가 사라진다. 그래서 저장소는 그대로 두고 «커밋된 소스를 꺼내 별도 폴더에 정리본을 만드는» 방식으로 한다.
#
# 하는 일 (규칙: config/delivery/rules.yaml + 프로젝트별 workspace/<project>/delivery.yaml)
#   1. target 저장소의 ref 를 git archive 로 읽는다 - 커밋 안 한 변경·git 이력·커밋 메시지는 나가지 않는다
#   2. exclude 경로를 뺀다(keep 이 앞선다)
#   3. 언어별 주석 구간만 찾아 그 안의 scrub 표지를 지운다. 문자열·코드는 바꾸지 않는다.
#      표지를 지운 뒤 내용이 남지 않는 주석은 통째로, 그 때문에 빈 줄이 된 줄은 줄째 지운다.
#      passthrough 경로(예: 납품 뒤 CICD 가 빼는 docs·시험)는 그대로 넣고 정리·금지어 검사를 하지 않는다.
#      git 계정명(accounts)과 그 앞뒤 날짜·커밋 문맥, 커밋 해시, 이모지도 주석에서 지운다.
#   4. 규칙으로 안 되는 긴 주석(DDL COMMENT 긴 설명, 근거 서술 위주의 긴 블록 주석)은 다듬기 대상으로 고른다.
#      --cache(jsonl) 에 다듬은 글이 있으면 그것으로 바꾸고, 없으면 <out>.polish.jsonl 로 내보낸다(comment-polisher 가 채운다).
#   5. 코드 불변 검증: 원본과 패키지에서 주석(과 DDL COMMENT 값)을 걷어낸 나머지가 같아야 한다. 다르면 종료 코드 4
#   6. 결과 전체(문자열 포함, passthrough 제외)를 deny·이모지로 검사한다 - 1건이라도 남으면 아무것도 쓰지 않고 종료 코드 2
#   7. --out 폴더에 패키지를 쓰고, 바뀐 주석 전부(<out>.changes.txt)·요약(<out>.summary.json, 바뀐 Flyway 파일 목록 포함)을 남긴다
#      --branch/--worktree 면 그 작업 트리의 고아 브랜치에 스냅샷 커밋 1개로 쓴다(push 하지 않는다)
#   8. (--verify 가 있으면) 패키지 폴더에서 그 명령(빌드 등)을 돌려 종료 코드를 확인한다
#
# 사용법:
#   python tools/package_delivery.py --target <저장소> --ref <브랜치|커밋> --check            # 검사만
#   python tools/package_delivery.py --target <저장소> --ref <브랜치|커밋> --out <빈 폴더>
#        [--rules <추가 규칙 yaml>] [--cache <jsonl>] [--require-polish] [--verify "<명령>"]
#   python tools/package_delivery.py --target <저장소> --ref <기준> --branch <고아 브랜치> --worktree <작업 트리 폴더> [...]
# 종료 코드: 0 정상 · 1 사용·환경 오류 · 2 금지어 남음 · 3 검증 명령 실패 · 4 코드 불변 검증 실패 · 5 다듬기 미처리(--require-polish)
# 의존성: pyyaml

import argparse
import datetime
import fnmatch
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, fix_console_encoding, load_yaml  # noqa: E402
from _emoji import EMOJI_RE  # noqa: E402

DEFAULT_RULES = os.path.join(ROOT, "config", "delivery", "rules.yaml")

C_LIKE = {".java", ".kt", ".groovy", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".css", ".scss", ".less"}
JS_LIKE = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
HASH_LIKE = {".yml", ".yaml", ".properties", ".sh", ".py", ".toml", ".conf", ".cfg"}
SQL_LIKE = {".sql"}
XML_LIKE = {".xml", ".html", ".htm", ".ftl", ".jsp", ".vue"}


# ---------------------------------------------------------------------------
# 규칙
# ---------------------------------------------------------------------------
def load_rules(extra=None):
    base = load_yaml(DEFAULT_RULES) or {}
    if extra:
        more = load_yaml(extra) or {}
        for k, v in more.items():
            if isinstance(v, list):
                base[k] = list(base.get(k) or []) + v
            else:
                base[k] = v
    return base


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, p) for p in patterns or [])


# 계정명 앞뒤로 붙는 날짜·커밋 문맥("10/12 leebriller96 이 commit 한 소스에 의거")을 계정명과 함께 지운다
DATE_PART = r"(?:\d{2,4}[-/.]\d{1,2}(?:[-/.]\d{1,2})?(?:\s+\d{1,2}:\d{2})?\s*)"
COMMIT_TAIL = (r"(?:\s*(?:님)?\s*(?:이|가|의)?\s*(?:commit|커밋|push|푸시|머지|병합)\s*(?:한|했던|된)?"
               r"\s*(?:소스|코드|내용|버전)?\s*(?:에\s*의거(?:하여|해|함)?|기준(?:으로)?|참고)?)?")


def account_pattern(accounts):
    accts = [a for a in accounts or [] if a]
    if not accts:
        return None
    return DATE_PART + r"?\b(?:" + "|".join(re.escape(a) for a in accts) + r")\b" + COMMIT_TAIL


class Scrubber:
    def __init__(self, rules):
        self.scrub = [re.compile(p, re.MULTILINE) for p in rules.get("scrub") or []]
        self.deny = [(p, re.compile(p)) for p in rules.get("deny") or []]
        acc = account_pattern(rules.get("accounts"))
        if acc:
            self.scrub.insert(0, re.compile(acc, re.MULTILINE | re.IGNORECASE))
            names = r"\b(?:" + "|".join(re.escape(a) for a in rules["accounts"] if a) + r")\b"
            self.deny.append(("accounts", re.compile(names, re.IGNORECASE)))
        self.drop = [re.compile(r"^(?:" + p + r")$") for p in rules.get("drop_if_only") or []]
        self.scrub_emoji = rules.get("scrub_emoji", True)
        self.deny_emoji = rules.get("deny_emoji", True)

    def clean_text(self, s, light=False):
        """주석 본문 한 줄에서 표지를 지우고 남은 구분자·빈 괄호를 정리한다.
        light: 문자열까지 고치는 줄(scrub_strings)용 - 줄 끝·줄 머리 정리를 하지 않는다(문장 끝 ';' 같은 코드 글자를 지우면 깨진다)."""
        orig = s
        for rx in self.scrub:
            s = rx.sub("", s)
        if self.scrub_emoji:
            s = EMOJI_RE.sub("", s)
        if s == orig:
            return s
        for _ in range(3):
            s = re.sub(r"\{@(?:code|link|linkplain|literal)\s*\}", "", s)     # 참조를 지워 빈 Javadoc 태그
            s = re.sub(r"[(\[]\s*[·,/;:~\-]*\s*[)\]]", "", s)            # 빈 괄호
            s = re.sub(r"\s*[·,/]\s*(?=[·,/)\]])", "", s)                 # 겹친 구분자
            s = re.sub(r"([(\[])\s*[·,/\-]\s*", r"\1", s)                 # 괄호 뒤 구분자
            s = re.sub(r"\s*[·,/\-]\s*([)\]])", r"\1", s)                 # 괄호 앞 구분자
        if light:
            return re.sub(r"[ \t]+([)\]])", r"\1", s)
        s = re.sub(r"[ \t]+([.,)\]])", r"\1", s)                          # 지운 자리 앞 공백
        s = re.sub(r"[ \t]{2,}", " ", s)
        s = re.sub(r"[ \t]*[·,/;]+[ \t]*$", "", s)                         # 끝 구분자
        s = re.sub(r"^([ \t]*)[·,/;]+[ \t]*", r"\1", s)                    # 앞 구분자
        if not orig.lstrip().startswith("-"):
            s = re.sub(r"^([ \t]*)-[ \t]+", r"\1", s)                      # 지운 머리말 뒤 남은 '- ' (원래 목록 기호는 둔다)
        s = re.sub(r"[ \t]+$", "", s)
        return s

    def empty(self, s):
        t = s.strip()
        return t == "" or any(rx.match(t) for rx in self.drop)


# ---------------------------------------------------------------------------
# 주석 구간 찾기 - [(시작, 끝, 종류)] 종류: line | block
# ---------------------------------------------------------------------------
def spans_c_like(text, ext):
    out, i, n = [], 0, len(text)
    js = ext in JS_LIKE
    while i < n:
        c = text[i]
        if text.startswith('"""', i) and not js:                          # 자바 텍스트 블록
            j = text.find('"""', i + 3)
            i = n if j < 0 else j + 3
            continue
        if c in "\"'" or (js and c == "`"):
            q, i = c, i + 1
            while i < n and text[i] != q:
                if text[i] == "\\":
                    i += 1
                elif text[i] == "\n" and q != "`":
                    break
                i += 1
            i += 1
            continue
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append((i, j, "line"))
            i = j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append((i, j, "block"))
            i = j
            continue
        if js and c == "/" and regex_allowed(text, i):
            i = skip_regex(text, i)
            continue
        i += 1
    return out


REGEX_PREV = set("(,=:[!&|?{};+-*%<>~^")
REGEX_KEYWORDS = ("return", "typeof", "case", "do", "else", "in", "of", "void", "yield", "await", "delete", "throw", "new")


def regex_allowed(text, i):
    """JS 에서 i 의 '/' 가 정규식 리터럴의 시작일 수 있는 자리인가(앞의 의미 있는 글자로 판정).
    정규식 안의 따옴표·백틱을 문자열 시작으로 읽으면 뒤쪽 주석을 통째로 놓친다(실측: /^(`{3,})/ 뒤 주석 전부)."""
    k = i - 1
    while k >= 0 and text[k] in " \t\r\n":
        k -= 1
    if k < 0 or text[k] in REGEX_PREV:
        return True
    m = re.search(r"([A-Za-z_$][\w$]*)$", text[:k + 1])
    return bool(m) and m.group(1) in REGEX_KEYWORDS


def skip_regex(text, i):
    """정규식 리터럴 끝(플래그 포함) 다음 위치. 줄 끝까지 닫히지 않으면 정규식이 아니라고 보고 한 글자만 넘긴다."""
    j, n, cls = i + 1, len(text), False
    while j < n and text[j] != "\n":
        ch = text[j]
        if ch == "\\":
            j += 2
            continue
        if ch == "[":
            cls = True
        elif ch == "]":
            cls = False
        elif ch == "/" and not cls:
            j += 1
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            return j
        j += 1
    return i + 1


def spans_sql(text, xml=False):
    """SQL·XML: 따옴표 문자열을 건너뛰며 -- 줄 주석, /* */, (xml 이면) <!-- --> 를 찾는다."""
    out, i, n = [], 0, len(text)
    in_tag = False
    while i < n:
        if xml and text.startswith("<!--", i):
            j = text.find("-->", i + 4)
            j = n if j < 0 else j + 3
            out.append((i, j, "block"))
            i = j
            continue
        if xml and text.startswith("<![CDATA[", i):
            i += 9
            continue
        c = text[i]
        if xml and c == "<":
            in_tag = True
        elif xml and c == ">":
            in_tag = False
        if c == "'" or (c == '"' and in_tag):
            q, i = c, i + 1
            while i < n and text[i] != q:
                i += 1
            i += 1
            continue
        if text.startswith("--", i) and not text.startswith("-->", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append((i, j, "line"))
            i = j
            continue
        if text.startswith("/*", i) and not in_tag:
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append((i, j, "block"))
            i = j
            continue
        i += 1
    return out


def spans_hash(text, ext):
    """yml·properties·sh: 줄머리 # (properties 는 ! 도), 또는 따옴표 밖 공백 뒤 # 부터 줄 끝."""
    out, pos = [], 0
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        idx = None
        stripped = body.lstrip()
        if stripped.startswith("#") or (ext == ".properties" and stripped.startswith("!")):
            idx = len(body) - len(stripped)
        elif ext in {".yml", ".yaml", ".sh", ".py", ".toml"}:
            q = None
            for k, ch in enumerate(body):
                if q:
                    if ch == q:
                        q = None
                elif ch in "\"'":
                    q = ch
                elif ch == "#" and k > 0 and body[k - 1] in " \t":
                    idx = k
                    break
        if idx is not None:
            out.append((pos + idx, pos + len(body), "line"))
        pos += len(line)
    return out


HASH_NAMES = {".gitignore", ".gitattributes", ".dockerignore", ".npmrc", ".env.example", "dockerfile"}


def comment_spans(path, text):
    ext = os.path.splitext(path)[1].lower()
    if os.path.basename(path).lower() in HASH_NAMES:                    # 확장자 없는 줄머리 # 주석 파일
        return spans_hash(text, ".properties")
    if ext in C_LIKE:
        return spans_c_like(text, ext)
    if ext in SQL_LIKE:
        return spans_sql(text)
    if ext in XML_LIKE:
        return spans_sql(text, xml=True)
    if ext in HASH_LIKE:
        return spans_hash(text, ext)
    return None


# ---------------------------------------------------------------------------
# 주석 고치기
# ---------------------------------------------------------------------------
def fix_comment(seg, kind, sc):
    """주석 하나 → 새 글자(빈 문자열이면 주석을 지운다)."""
    if kind == "line":
        m = re.match(r"^(//+|--|#+|!)(\s?)(.*)$", seg, re.S)
        if not m:
            return seg
        lead, sp, body = m.groups()
        new = sc.clean_text(body)
        if new == body:
            return seg
        return "" if sc.empty(new) else lead + sp + new.lstrip() if sp else lead + new
    # block: /* */, /** */, <!-- -->
    if seg.startswith("<!--"):
        opener, closer = "<!--", "-->"
    elif seg.startswith("/**"):
        opener, closer = "/**", "*/"
    else:
        opener, closer = "/*", "*/"
    inner = seg[len(opener):-len(closer)] if seg.endswith(closer) else seg[len(opener):]
    lines = inner.split("\n")
    changed, kept = False, []
    for ln in lines:
        m = re.match(r"^(\s*\*?\s?)(.*?)(\r?)$", ln, re.S)
        pre, body, cr = m.groups()
        tail = body[len(body.rstrip(" 	")):]
        new = sc.clean_text(body)
        if new != body:
            changed = True
            if sc.empty(new):
                continue                                                  # 내용 없는 줄은 줄째 지운다
            kept.append(pre + new.lstrip() + tail + cr)
        else:
            kept.append(ln)
    if not changed:
        return seg
    if all(sc.empty(re.sub(r"^\s*\*?", "", k).strip("\r")) for k in kept):
        return ""                                                         # 내용이 하나도 안 남은 주석
    # 연속된 빈 별표 줄은 하나로
    out = []
    for k in kept:
        blank = re.sub(r"^\s*\*?\s*", "", k).strip("\r") == ""
        if blank and out and re.sub(r"^\s*\*?\s*", "", out[-1]).strip("\r") == "" and len(out) > 1:
            continue
        out.append(k)
    return opener + "\n".join(out) + closer


def scrub_whole(text, sc):
    """scrub_strings 경로: DDL COMMENT '...' 값 안의 표지를 지운다.
    값 밖(INSERT 시드 값 등)은 데이터라 건드리지 않는다 - 줄 전체를 고치던 종전 방식은 시드의 메일 주소·이모지까지 바꿨다(실측)."""
    parts, changes, last = [], [], 0
    for m in DDL_COMMENT_RX.finditer(text):
        v = m.group(2)
        new = sc.clean_text(v, light=True).strip()
        if new == v:
            continue
        line = text.count("\n", 0, m.start()) + 1
        changes.append((line, m.group(0), m.group(1) + new + m.group(3)))
        parts.append(text[last:m.start(2)])
        parts.append(new)
        last = m.end(2)
    parts.append(text[last:])
    return "".join(parts), changes


def scrub_file(path, text, sc, whole=False):
    """주석 안 표지를 지운 텍스트와 바뀐 목록 [(줄, 전, 후)] 을 돌려준다. 주석을 모르는 형식이면 그대로."""
    if whole:
        text, ch1 = scrub_file(path, text, sc)
        text, ch2 = scrub_whole(text, sc)
        return text, ch1 + ch2
    spans = comment_spans(path, text)
    if not spans:
        return text, []
    parts, changes, last = [], [], 0
    for s, e, kind in spans:
        seg = text[s:e]
        new = fix_comment(seg, kind, sc)
        if new == seg:
            continue
        line_no = text.count("\n", 0, s) + 1
        changes.append((line_no, seg, new))
        parts.append(text[last:s])
        if new == "":
            # 주석만 있던 줄이면 줄째 지운다(앞 들여쓰기와 줄바꿈까지)
            ls = text.rfind("\n", 0, s) + 1
            le = text.find("\n", e)
            le = len(text) if le < 0 else le + 1
            if text[ls:s].strip() == "" and text[e:le].strip() == "":
                parts[-1] = text[last:ls]
                last = le
                continue
            # 코드 뒤 꼬리 주석이면 주석 앞 공백까지
            prefix = parts[-1]
            parts[-1] = prefix.rstrip(" \t")
        else:
            parts.append(new)
        last = e
    parts.append(text[last:])
    return "".join(parts), changes


# ---------------------------------------------------------------------------
# 다듬기(규칙으로 안 되는 주석) - 대상 고르기와 캐시 적용
#   대상: (1) DDL COMMENT 값이 길거나 여러 문장 (2) 근거·결정 서술 위주의 긴 블록 주석
#   캐시(jsonl): {"path", "kind": "ddl"|"comment", "sha1": <규칙 처리 뒤 원문 해시>, "new": <다듬은 글>}
#   열쇠가 규칙 처리 뒤 원문이라 원문이 안 바뀌면 다음 패키징에서 그대로 다시 쓴다.
# ---------------------------------------------------------------------------
DDL_COMMENT_RX = re.compile(r"(\bCOMMENT\s*(?:=\s*)?')((?:[^']|'')*)(')", re.IGNORECASE)


def sha1(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def load_cache(path):
    cache = {}
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                e = json.loads(ln)
                if e.get("new") is not None:
                    cache[(e["path"], e["kind"], e["sha1"])] = e["new"]
                    # 경로가 바뀌어도(모듈 이동·파일 이름 변경) 원문이 같으면 같은 글을 쓴다 - 처음 나온 것을 둔다
                    cache.setdefault((None, e["kind"], e["sha1"]), e["new"])
    return cache


def cache_get(cache, key):
    """(경로, 종류, 해시) 로 찾고, 없으면 경로 없이 (종류, 해시) 로 찾는다."""
    new = cache.get(key)
    return new if new is not None else cache.get((None, key[1], key[2]))


class Polisher:
    def __init__(self, rules, cache_path=None):
        cfg = rules.get("polish") or {}
        self.enabled = cfg.get("enabled", True)
        self.ddl_paths = cfg.get("ddl_paths") or ["*.sql"]
        self.ddl_max = int(cfg.get("ddl_max_chars", 40))
        self.block_paths = cfg.get("block_paths") or ["*"]
        self.block_lines = int(cfg.get("block_max_lines", 8))
        self.block_kw = [re.compile(p) for p in cfg.get("block_keywords") or []]
        self.block_kw_min = int(cfg.get("block_keyword_min", 2))
        self.cache = load_cache(cache_path)
        self.candidates, self.hits, self.invalid = [], 0, []

    def ddl_needs(self, v):
        sentences = len(re.findall(r"[.。](?:\s|$)", v.strip()))
        return len(v) > self.ddl_max or "\n" in v or sentences > 1

    def block_needs(self, seg):
        if seg.count("\n") + 1 <= self.block_lines:
            return False
        return sum(1 for rx in self.block_kw if rx.search(seg)) >= self.block_kw_min

    def valid_comment(self, old, new):
        for opener, closer in (("<!--", "-->"), ("/**", "*/"), ("/*", "*/")):
            if old.startswith(opener):
                inner = new[len(opener):-len(closer)] if new.endswith(closer) else None
                return new.startswith(opener) and inner is not None and closer not in inner
        return False

    def apply(self, path, text, sc):
        """다듬기를 적용한 텍스트와 바뀐 목록. 캐시에 없는 대상은 candidates 에 쌓는다."""
        if not self.enabled:
            return text, []
        edits = []                                             # (시작, 끝, 새 글)
        if matches(path, self.ddl_paths):
            for m in DDL_COMMENT_RX.finditer(text):
                v = m.group(2).replace("''", "'")
                if not self.ddl_needs(v):
                    continue
                key = (path, "ddl", sha1(v))
                line = text.count("\n", 0, m.start()) + 1
                new = cache_get(self.cache, key)
                if new is None:
                    self.candidates.append({"path": path, "kind": "ddl", "sha1": key[2], "line": line, "original": v})
                elif "\n" in new or EMOJI_RE.search(new) or any(rx.search(new) for _p, rx in sc.deny):
                    self.invalid.append((path, line, "ddl"))
                else:
                    self.hits += 1
                    edits.append((m.start(2), m.end(2), new.replace("'", "''")))
        if matches(path, self.block_paths):
            for s, e, kind in comment_spans(path, text) or []:
                seg = text[s:e]
                if kind != "block" or not self.block_needs(seg):
                    continue
                key = (path, "comment", sha1(seg))
                line = text.count("\n", 0, s) + 1
                new = cache_get(self.cache, key)
                if new is None:
                    self.candidates.append({"path": path, "kind": "comment", "sha1": key[2], "line": line, "original": seg})
                elif not self.valid_comment(seg, new) or EMOJI_RE.search(new) or any(rx.search(new) for _p, rx in sc.deny):
                    self.invalid.append((path, line, "comment"))
                else:
                    self.hits += 1
                    edits.append((s, e, new))
        changes = []
        for s, e, new in sorted(edits, reverse=True):
            changes.append((text.count("\n", 0, s) + 1, text[s:e], new))
            text = text[:s] + new + text[e:]
        return text, sorted(changes)


# ---------------------------------------------------------------------------
# 코드 불변 검증 - 주석(과 SQL 의 COMMENT 값)을 걷어낸 나머지가 원본과 같아야 한다
# ---------------------------------------------------------------------------
def code_view(path, text):
    spans = comment_spans(path, text)
    if spans is None:
        return text
    parts, last = [], 0
    for s, e, _k in spans:
        parts.append(text[last:s])
        parts.append(" ")
        last = e
    parts.append(text[last:])
    t = "".join(parts)
    if os.path.splitext(path)[1].lower() in SQL_LIKE:
        t = DDL_COMMENT_RX.sub(lambda m: m.group(1) + m.group(3), t)
    return " ".join(t.split())


def verify_invariant(files, out):
    """패키지 파일 중 원본과 주석 밖이 달라진 경로 목록."""
    bad = []
    for path, (data, _e) in out.items():
        orig = files[path][0]
        if data == orig:
            continue
        ot, nt = as_text(orig), as_text(data)
        if ot is None or nt is None or code_view(path, ot) != code_view(path, nt):
            bad.append(path)
    return bad


# ---------------------------------------------------------------------------
# 고아 브랜치 스냅샷 커밋 - 원본 이력과 이어지지 않는 납품 브랜치에 패키징 1회 = 커밋 1개
# ---------------------------------------------------------------------------
PROTECTED_BRANCHES = {"main", "master", "dev", "develop"}


def git(args, cwd, check=True):
    r = subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "core.safecrlf=false", *args], cwd=cwd,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise SystemExit(f"[package] git {' '.join(args)} 실패:\n{r.stderr}")
    return r


def commit_snapshot(target, ref, worktree, branch, files, message):
    """worktree 의 branch(없으면 고아로 만든다)를 files 로 통째 바꾸고 커밋한다. 새 커밋 sha(바뀐 것이 없으면 None)."""
    wt, tgt = os.path.abspath(worktree), os.path.abspath(target)
    if branch in PROTECTED_BRANCHES or branch == ref:
        raise SystemExit(f"[package] 납품 브랜치로 쓸 수 없는 이름: {branch}")
    if os.path.normcase(wt).startswith(os.path.normcase(tgt) + os.sep) or os.path.normcase(wt) == os.path.normcase(tgt):
        raise SystemExit(f"[package] 작업 트리는 원본 저장소 밖이어야 한다: {wt}")
    if not os.path.exists(os.path.join(wt, ".git")):
        if os.path.exists(wt) and os.listdir(wt):
            raise SystemExit(f"[package] 작업 트리 폴더가 git 작업 트리가 아니고 비어 있지도 않다: {wt}")
        git(["worktree", "add", "--detach", wt, ref], tgt)
    if git(["rev-parse", "--verify", "-q", "refs/heads/" + branch], wt, check=False).returncode == 0:
        git(["checkout", "-q", "-f", branch], wt)
    else:
        git(["checkout", "-q", "--orphan", branch], wt)
    git(["rm", "-r", "-q", "-f", "--ignore-unmatch", "."], wt)
    git(["clean", "-f", "-d", "-x", "-q"], wt)
    write_out(files, wt)
    git(["add", "-A", "-f", "."], wt)
    if git(["diff", "--cached", "--quiet"], wt, check=False).returncode == 0 and \
            git(["rev-parse", "--verify", "-q", "HEAD"], wt, check=False).returncode == 0:
        return None
    git(["commit", "-q", "-m", message], wt)
    return git(["rev-parse", "HEAD"], wt).stdout.strip()


# ---------------------------------------------------------------------------
# 읽기·쓰기
# ---------------------------------------------------------------------------
def read_tree(target, ref):
    raw = subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "core.eol=lf", "archive", "--format=tar", ref],
                         cwd=target, capture_output=True)
    if raw.returncode != 0:
        raise SystemExit(f"[package] git archive {ref} 실패:\n{raw.stderr.decode('utf-8', 'replace')}")
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw.stdout)) as tar:
        for m in tar.getmembers():
            if m.isfile():
                files[m.name] = (tar.extractfile(m).read(), bool(m.mode & 0o111))
    return files


def as_text(data):
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def build(files, rules, polisher=None):
    """패키지 파일·제외 목록·바뀐 주석·금지어 결과. polisher 가 있으면 규칙 처리 뒤 다듬기를 적용한다."""
    sc = Scrubber(rules)
    excl, keep = rules.get("exclude") or [], rules.get("keep") or []
    passthrough = rules.get("passthrough") or []
    whole_paths = rules.get("scrub_strings") or []
    out, dropped, changes, raw = {}, [], {}, set()
    for path, (data, exe) in sorted(files.items()):
        if matches(path, excl) and not matches(path, keep):
            dropped.append(path)
            continue
        if matches(path, passthrough):
            raw.add(path)                                      # 그대로 넣는다(정리·금지어 검사 없음)
            out[path] = (data, exe)
            continue
        text = as_text(data)
        if text is not None:
            new, ch = scrub_file(path, text, sc, whole=matches(path, whole_paths))
            if polisher is not None:
                new, ch2 = polisher.apply(path, new, sc)
                ch = ch + ch2
            if ch:
                changes[path] = ch
                data = new.encode("utf-8")
        out[path] = (data, exe)
    found = []
    deny_skip = rules.get("deny_skip") or []
    for path, (data, _e) in out.items():
        if path in raw or matches(path, deny_skip):
            continue
        text = as_text(data)
        if text is None:
            continue
        for ln, line in enumerate(text.splitlines(), start=1):
            for p, rx in sc.deny:
                m = rx.search(line)
                if m:
                    found.append((path, ln, m.group(0), p))
            if sc.deny_emoji:
                for m in EMOJI_RE.finditer(line):
                    found.append((path, ln, f"U+{ord(m.group(0)):04X}", "emoji"))
    return out, dropped, changes, found


def write_out(files, out_dir):
    for path, (data, exe) in files.items():
        full = os.path.join(out_dir, path)
        os.makedirs(os.path.dirname(full) or out_dir, exist_ok=True)
        with open(full, "wb") as f:
            f.write(data)
        if exe and os.name != "nt":
            os.chmod(full, 0o755)


def write_changes(changes, path):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for p in sorted(changes):
            for ln, old, new in changes[p]:
                f.write(f"== {p}:{ln}\n- {old}\n+ {new if new else '(삭제)'}\n")


def write_jsonl(rows, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def kst_now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")


def main(argv=None):
    fix_console_encoding()
    ap = argparse.ArgumentParser(description="고객사 납품용 소스 패키지(문서·파이프라인 흔적 제거)")
    ap.add_argument("--target", required=True, help="소스 저장소 폴더")
    ap.add_argument("--ref", default="HEAD", help="기준 브랜치·커밋 (기본 HEAD)")
    ap.add_argument("--out", help="패키지를 쓸 빈 폴더 (--check·--branch 면 없어도 된다)")
    ap.add_argument("--rules", help="추가 규칙 yaml (예: workspace/<project>/delivery.yaml)")
    ap.add_argument("--check", action="store_true", help="검사만 하고 아무것도 쓰지 않는다")
    ap.add_argument("--verify", help="패키지 폴더에서 돌릴 확인 명령(빌드 등)")
    ap.add_argument("--cache", help="다듬은 주석 캐시 jsonl (예: workspace/<project>/delivery/comment-cache.jsonl)")
    ap.add_argument("--polish-out", help="캐시에 없는 다듬기 대상을 쓸 jsonl (기본 <out>.polish.jsonl)")
    ap.add_argument("--require-polish", action="store_true", help="캐시에 없는 다듬기 대상이 남으면 쓰지 않고 종료 코드 5")
    ap.add_argument("--branch", help="스냅샷을 커밋할 고아 납품 브랜치 이름 (--worktree 필요, push 하지 않는다)")
    ap.add_argument("--worktree", help="납품 브랜치 작업 트리 폴더 (원본 저장소 밖, 없으면 만든다)")
    a = ap.parse_args(argv)

    if bool(a.branch) != bool(a.worktree):
        raise SystemExit("[package] --branch 와 --worktree 는 함께 쓴다")
    if not a.check and not a.out and not a.branch:
        raise SystemExit("[package] --out 또는 --branch 가 필요하다(또는 --check)")
    target = os.path.abspath(a.target)
    rules = load_rules(a.rules)
    sha = subprocess.run(["git", "rev-parse", "--short", a.ref], cwd=target, capture_output=True, text=True).stdout.strip()
    files = read_tree(target, a.ref)
    polisher = Polisher(rules, a.cache)
    out, dropped, changes, found = build(files, rules, polisher)
    n_changes = sum(len(v) for v in changes.values())
    n_removed = sum(1 for v in changes.values() for _l, _o, nw in v if nw == "")
    flyway = sorted(p for p in changes if matches(p, rules.get("flyway_paths") or ["*/db/migration/*"]))
    n_cand = len(polisher.candidates)
    print(f"[package] 기준 {a.ref} ({sha}) · 원본 {len(files)}개 -> 패키지 {len(out)}개 (제외 {len(dropped)}개)")
    print(f"[package] 주석 정리 {n_changes}곳 (통째 삭제 {n_removed}, 고침 {n_changes - n_removed}) · 파일 {len(changes)}개")
    print(f"[package] 다듬기: 캐시 적용 {polisher.hits} · 미처리 {n_cand} · 캐시 무효 {len(polisher.invalid)}")
    print(f"[package] 바뀐 Flyway 마이그레이션 {len(flyway)}개 (이미 원본으로 마이그레이션한 DB 는 배포 전 flyway repair 1회)")
    ext_count = {}
    for p in dropped:
        k = os.path.splitext(p)[1] or "(없음)"
        ext_count[k] = ext_count.get(k, 0) + 1
    print("[package] 제외 확장자: " + ", ".join(f"{k} {v}" for k, v in sorted(ext_count.items(), key=lambda x: -x[1])[:10]))

    base = os.path.abspath(a.out).rstrip("/\\") if a.out else None
    polish_path = a.polish_out or (base + ".polish.jsonl" if base else None)
    if polish_path and polisher.candidates:
        write_jsonl(polisher.candidates, polish_path)
        print(f"[package] 다듬기 대상 목록: {polish_path}")

    bad = verify_invariant(files, out)
    if bad:
        print(f"\n[package] [중단] 코드 불변 검증 실패 {len(bad)}개 - 주석 밖이 바뀌었다. 아무것도 쓰지 않았다:")
        for p in bad[:100]:
            print(f"  {p}")
        return 4
    print("[package] [통과] 코드 불변 검증(주석·DDL COMMENT 밖 동일)")

    if found:
        print(f"\n[package] [중단] 금지어 {len(found)}건이 남았다 - 아무것도 쓰지 않았다. 문자열·코드에 있는 것은 직접 고치거나 규칙을 더한다:")
        for path, ln, text, pat in found[:200]:
            print(f"  {path}:{ln}  «{text}»  <- {pat}")
        if len(found) > 200:
            print(f"  … 외 {len(found) - 200}건")
        if base and changes:
            os.makedirs(os.path.dirname(base) or ".", exist_ok=True)
            write_changes(changes, base + ".changes.txt")
        return 2
    print("[package] [통과] 금지어·이모지 0건")
    if a.check:
        return 0
    if a.require_polish and polisher.candidates:
        print(f"[package] [중단] 다듬기 미처리 {n_cand}건 - comment-polisher 로 캐시를 채운 뒤 다시 만든다")
        return 5

    summary = {"ref": a.ref, "sha": sha, "at_kst": kst_now(), "files": len(out), "excluded": len(dropped),
               "comment_changes": n_changes, "comment_removed": n_removed, "changed_files": len(changes),
               "polish_hits": polisher.hits, "polish_pending": n_cand, "polish_invalid": len(polisher.invalid),
               "flyway_changed": flyway, "invariant": "pass", "deny": 0}
    out_dir = None
    if a.out:
        out_dir = os.path.abspath(a.out)
        if os.path.exists(out_dir) and os.listdir(out_dir):
            raise SystemExit(f"[package] 출력 폴더가 비어 있지 않다: {out_dir}")
        write_out(out, out_dir)
        write_changes(changes, base + ".changes.txt")
        print(f"[package] 패키지: {out_dir}\n[package] 바뀐 주석 검토 목록: {base}.changes.txt")
    if a.branch:
        msg = (f"package: {a.ref} {sha} ({summary['at_kst']})\n\n"
               f"파일 {len(out)}개, 주석 정리 {n_changes}곳, 다듬기 {polisher.hits}곳(미처리 {n_cand}), "
               f"바뀐 마이그레이션 {len(flyway)}개, 코드 불변 검증 통과, 금지어 0건\n")
        new_sha = commit_snapshot(target, a.ref, a.worktree, a.branch, out, msg)
        summary["branch"], summary["commit"] = a.branch, new_sha
        print(f"[package] 납품 브랜치 {a.branch}: " + (f"커밋 {new_sha}" if new_sha else "바뀐 것 없음(커밋 안 함)")
              + f" · 작업 트리 {os.path.abspath(a.worktree)} · push 하지 않았다")
        out_dir = out_dir or os.path.abspath(a.worktree)
    if base:
        with open(base + ".summary.json", "w", encoding="utf-8", newline="\n") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
    if a.verify:
        r = subprocess.run(a.verify, cwd=out_dir, shell=True)
        print(f"[package] 확인 명령 종료 코드 {r.returncode}: {a.verify}")
        if r.returncode != 0:
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
