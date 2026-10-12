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
#   4. 결과 전체(문자열 포함)를 deny 로 검사한다 - 1건이라도 남으면 아무것도 쓰지 않고 종료 코드 2
#   5. --out 폴더에 패키지를 쓰고, 바뀐 주석 전부를 검토용 목록(<out>.changes.txt)으로 남긴다
#   6. (--verify 가 있으면) 패키지 폴더에서 그 명령(빌드 등)을 돌려 종료 코드를 확인한다
#
# 사용법:
#   python tools/package_delivery.py --target <저장소> --ref <브랜치|커밋> --check            # 검사만
#   python tools/package_delivery.py --target <저장소> --ref <브랜치|커밋> --out <빈 폴더>
#        [--rules <추가 규칙 yaml>] [--verify "<명령>"]
# 종료 코드: 0 정상 · 1 사용·환경 오류 · 2 금지어 남음 · 3 검증 명령 실패
# 의존성: pyyaml

import argparse
import fnmatch
import io
import os
import re
import subprocess
import sys
import tarfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, fix_console_encoding, load_yaml  # noqa: E402

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


class Scrubber:
    def __init__(self, rules):
        self.scrub = [re.compile(p, re.MULTILINE) for p in rules.get("scrub") or []]
        self.drop = [re.compile(r"^(?:" + p + r")$") for p in rules.get("drop_if_only") or []]
        self.deny = [(p, re.compile(p)) for p in rules.get("deny") or []]

    def clean_text(self, s, light=False):
        """주석 본문 한 줄에서 표지를 지우고 남은 구분자·빈 괄호를 정리한다.
        light: 문자열까지 고치는 줄(scrub_strings)용 - 줄 끝·줄 머리 정리를 하지 않는다(문장 끝 ';' 같은 코드 글자를 지우면 깨진다)."""
        orig = s
        for rx in self.scrub:
            s = rx.sub("", s)
        if s == orig:
            return s
        for _ in range(3):
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
        i += 1
    return out


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


def comment_spans(path, text):
    ext = os.path.splitext(path)[1].lower()
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
    """scrub_strings 경로: 문자열까지 줄 단위로 표지를 지운다(DDL COMMENT 처럼 설명용 문자열만 있는 파일에 쓴다)."""
    lines, changes = text.split(chr(10)), []
    for i, ln in enumerate(lines):
        new = sc.clean_text(ln, light=True)
        if new != ln:
            changes.append((i + 1, ln, new))
            lines[i] = new
    return chr(10).join(lines), changes


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


def build(files, rules):
    sc = Scrubber(rules)
    excl, keep = rules.get("exclude") or [], rules.get("keep") or []
    whole_paths = rules.get("scrub_strings") or []
    out, dropped, changes = {}, [], {}
    for path, (data, exe) in sorted(files.items()):
        if matches(path, excl) and not matches(path, keep):
            dropped.append(path)
            continue
        text = as_text(data)
        if text is not None:
            new, ch = scrub_file(path, text, sc, whole=matches(path, whole_paths))
            if ch:
                changes[path] = ch
                data = new.encode("utf-8")
        out[path] = (data, exe)
    found = []
    for path, (data, _e) in out.items():
        text = as_text(data)
        if text is None:
            continue
        for ln, line in enumerate(text.splitlines(), start=1):
            for p, rx in sc.deny:
                m = rx.search(line)
                if m:
                    found.append((path, ln, m.group(0), p))
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


def main(argv=None):
    fix_console_encoding()
    ap = argparse.ArgumentParser(description="고객사 납품용 소스 패키지(문서·파이프라인 흔적 제거)")
    ap.add_argument("--target", required=True, help="소스 저장소 폴더")
    ap.add_argument("--ref", default="HEAD", help="기준 브랜치·커밋 (기본 HEAD)")
    ap.add_argument("--out", help="패키지를 쓸 빈 폴더 (--check 면 필요 없다)")
    ap.add_argument("--rules", help="추가 규칙 yaml (예: workspace/<project>/delivery.yaml)")
    ap.add_argument("--check", action="store_true", help="검사만 하고 아무것도 쓰지 않는다")
    ap.add_argument("--verify", help="패키지 폴더에서 돌릴 확인 명령(빌드 등)")
    a = ap.parse_args(argv)

    if not a.check and not a.out:
        raise SystemExit("[package] --out 이 필요하다(또는 --check)")
    target = os.path.abspath(a.target)
    rules = load_rules(a.rules)
    sha = subprocess.run(["git", "rev-parse", "--short", a.ref], cwd=target, capture_output=True, text=True).stdout.strip()
    files = read_tree(target, a.ref)
    out, dropped, changes, found = build(files, rules)
    n_changes = sum(len(v) for v in changes.values())
    n_removed = sum(1 for v in changes.values() for _l, _o, nw in v if nw == "")
    print(f"[package] 기준 {a.ref} ({sha}) · 원본 {len(files)}개 -> 패키지 {len(out)}개 (제외 {len(dropped)}개)")
    print(f"[package] 주석 정리 {n_changes}곳 (통째 삭제 {n_removed}, 고침 {n_changes - n_removed}) · 파일 {len(changes)}개")
    ext_count = {}
    for p in dropped:
        k = os.path.splitext(p)[1] or "(없음)"
        ext_count[k] = ext_count.get(k, 0) + 1
    print("[package] 제외 확장자: " + ", ".join(f"{k} {v}" for k, v in sorted(ext_count.items(), key=lambda x: -x[1])[:10]))

    if found:
        print(f"\n[package] [중단] 금지어 {len(found)}건이 남았다 - 아무것도 쓰지 않았다. 문자열·코드에 있는 것은 직접 고치거나 규칙을 더한다:")
        for path, ln, text, pat in found[:200]:
            print(f"  {path}:{ln}  «{text}»  <- {pat}")
        if len(found) > 200:
            print(f"  … 외 {len(found) - 200}건")
        if a.out and changes:
            os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
            write_changes(changes, os.path.abspath(a.out).rstrip("/\\") + ".changes.txt")
        return 2
    print("[package] [통과] 금지어 0건")
    if a.check:
        return 0

    out_dir = os.path.abspath(a.out)
    if os.path.exists(out_dir) and os.listdir(out_dir):
        raise SystemExit(f"[package] 출력 폴더가 비어 있지 않다: {out_dir}")
    write_out(out, out_dir)
    ch_path = out_dir.rstrip("/\\") + ".changes.txt"
    write_changes(changes, ch_path)
    print(f"[package] 패키지: {out_dir}\n[package] 바뀐 주석 검토 목록: {ch_path}")
    if a.verify:
        r = subprocess.run(a.verify, cwd=out_dir, shell=True)
        print(f"[package] 확인 명령 종료 코드 {r.returncode}: {a.verify}")
        if r.returncode != 0:
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
