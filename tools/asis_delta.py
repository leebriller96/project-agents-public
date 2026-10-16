#!/usr/bin/env python3
# asis_delta.py — AS-IS 현행화: 옛 AS-IS 와 새(현행화) AS-IS 를 의미 단위로 비교해 업무(slice)와 TO-BE 파일에 이어 붙인다
#
# 배경: 차세대 변환 도중 고객이 "최신 운영 소스" 를 다시 주는 일이 있다(실측: 변환 기준 AS-IS 가 운영본보다 낡았다).
#       파일 단위 diff 를 사람이 읽고 TO-BE 를 뒤지면 놓치고 느리다. 그래서
#       (1) 인코딩(EUC-KR/UTF-8)·줄바꿈·줄끝 공백·BOM 차이는 먼저 걸러 내고,
#       (2) 경로만 바뀐 파일(같은 파일명·내용 유사)은 이동으로 묶고,
#       (3) Java 는 메서드 단위, MyBatis Mapper 는 statement id 단위, 그 밖은 파일 단위로 바뀐 곳(단위)을 뽑고,
#       (4) 단위마다 slices.yaml(asis.programs·namespaces)과 TO-BE 소스 검색으로 영향 slice·TO-BE 파일 후보를 붙인다.
#       판정(이미 반영됨 / 반영 필요 / 대상 아님)은 사람·분석 에이전트가 단위마다 채운다 - 이 도구는 판정하지 않는다.
#
# 사용법:
#   python tools/asis_delta.py --old <옛 AS-IS> --new <새 AS-IS> [--target <TO-BE>] [--out <폴더>]
#   결과: <out>/asis_delta.yaml (단위 목록), <out>/ASIS_DELTA.md (요약표), <out>/diffs/AD-NNNN.diff (단위별 diff)
#   기본 out: workspace/<project>/knowledge/asis_delta
import argparse
import difflib
import fnmatch
import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import dump_yaml, fix_console_encoding, load_yaml, target_dir, workspace  # noqa: E402
import _javasrc  # noqa: E402

SKIP_DIRS = {"target", ".git", ".settings", "node_modules", "build", "dist", ".idea"}
SKIP_FILES = [".classpath", ".project", ".DS_Store", "*.class"]
CODE_EXT = {".java", ".xml", ".jsp", ".ftl", ".js", ".properties", ".htm", ".html", ".sql", ".css", ".yml", ".yaml"}
SEARCH_EXT = {".java", ".xml", ".ts", ".tsx", ".vue", ".js", ".sql"}
# TO-BE 후보는 코드에서만 찾는다 - 분석 문서(docs/)는 AS-IS 이름을 다 담고 있어 후보가 문서로 가득 찬다(실측)
SEARCH_SKIP_TOP = {"docs", "doc"}
STMT_RE = re.compile(r"<(select|insert|update|delete|sql)\b([^>]*)>(.*?)</\1\s*>", re.S | re.I)
ID_RE = re.compile(r"\bid\s*=\s*\"([^\"]+)\"")
NS_RE = re.compile(r"<mapper\b[^>]*\bnamespace\s*=\s*\"([^\"]+)\"")


def decode(raw):
    for enc in ("utf-8", "cp949"):
        try:
            return raw.decode(enc).lstrip("﻿")
        except UnicodeDecodeError:
            pass
    return None


def norm_lines(text):
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return lines


def squash(text):
    """공백 차이만 있는 변경을 같은 것으로 본다."""
    return re.sub(r"\s+", " ", text).strip()


def walk(root):
    out = {}
    for d, ds, fs in os.walk(root):
        ds[:] = [x for x in ds if x not in SKIP_DIRS]
        for f in fs:
            if any(fnmatch.fnmatch(f, p) for p in SKIP_FILES):
                continue
            p = os.path.join(d, f)
            out[os.path.relpath(p, root).replace("\\", "/")] = p
    return out


class Src:
    def __init__(self, path):
        raw = open(path, "rb").read()
        self.text = decode(raw)
        self.binary = self.text is None
        self.digest = hashlib.sha256(raw if self.binary else "\n".join(norm_lines(self.text)).encode()).hexdigest()


def similarity(a, b):
    if a.binary or b.binary:
        return 1.0 if a.digest == b.digest else 0.0
    return difflib.SequenceMatcher(None, squash(a.text), squash(b.text), autojunk=False).quick_ratio()


def java_units(text):
    """{단위키: 원문} - 메서드별, 그리고 메서드를 뺀 클래스 나머지(필드·어노테이션·import)."""
    units = {}
    try:
        classes = _javasrc.parse_file("", text)
    except Exception:
        return {"<file>": text}
    head_end = classes[0].head_start if classes else len(text)
    units["<imports>"] = text[:head_end]
    for c in classes:
        rest, last = [], c.head_start
        for m in sorted(c.methods, key=lambda x: x.start):
            if m.body_end is None and not m.sig:
                continue
            s, e = m.span
            key = f"{c.name}#{m.name}({','.join(p[0] if isinstance(p, (tuple, list)) else str(p) for p in m.params)})"
            units[key] = text[s:e]
            rest.append(text[last:s])
            last = e
        rest.append(text[last:c.end])
        units[f"{c.name}#<class>"] = "".join(rest)
    return units


def mapper_units(text):
    ns = NS_RE.search(text)
    ns = ns.group(1) if ns else ""
    units = {}
    for m in STMT_RE.finditer(text):
        i = ID_RE.search(m.group(2))
        units[f"{ns}.{i.group(1) if i else '?'}"] = m.group(0)
    if not units:
        units["<file>"] = text
    return units


def units_of(path, text):
    if path.endswith(".java"):
        return "java-method", java_units(text)
    if path.endswith(".xml") and NS_RE.search(text):
        return "mapper-statement", mapper_units(text)
    return "file", {"<file>": text}


def diff_text(a, b, fa, fb):
    return "".join(difflib.unified_diff([x + "\n" for x in norm_lines(a or "")], [x + "\n" for x in norm_lines(b or "")],
                                        fromfile=fa, tofile=fb, n=3))


def slice_index(slices_path):
    """basename·namespace → slice id 목록."""
    idx = {}
    try:
        data = load_yaml(slices_path) or {}
    except Exception:
        return idx
    items = data.get("slices") if isinstance(data, dict) else data
    for s in items or []:
        if not isinstance(s, dict):
            continue
        a = s.get("asis") or {}
        for p in (a.get("programs") or []) + (a.get("namespaces") or []):
            idx.setdefault(str(p).split("/")[-1].strip(), set()).add(s.get("id"))
    return idx


def slices_for(idx, path, unit):
    base = path.split("/")[-1]
    hits = set(idx.get(base, ()))
    if unit.count(".") and not unit.startswith("<"):
        hits |= idx.get(unit.rsplit(".", 1)[0].split(".")[-1], set())
        hits |= idx.get(unit.rsplit(".", 1)[0], set())
    stem = os.path.splitext(base)[0]
    for k, v in idx.items():
        if os.path.splitext(k)[0] == stem:
            hits |= v
    return sorted(h for h in hits if h)


class ToBeIndex:
    def __init__(self, root):
        self.files = []
        if not root or not os.path.isdir(root):
            return
        for d, ds, fs in os.walk(root):
            ds[:] = [x for x in ds if x not in SKIP_DIRS and not (d == root and x in SEARCH_SKIP_TOP)]
            for f in fs:
                if os.path.splitext(f)[1].lower() in SEARCH_EXT:
                    p = os.path.join(d, f)
                    try:
                        t = decode(open(p, "rb").read())
                    except OSError:
                        continue
                    if t:
                        self.files.append((os.path.relpath(p, root).replace("\\", "/"), t))

    def hits(self, tokens, limit=8):
        """모든 토큰을 담은 TO-BE 파일(테스트 제외 우선)."""
        tokens = [t for t in tokens if t and len(t) > 2]
        if not tokens:
            return []
        found = [p for p, t in self.files if all(re.search(rf"\b{re.escape(k)}\b", t) for k in tokens)]
        found.sort(key=lambda p: ("/test/" in p or "spec" in p.lower(), p))
        return found[:limit]


def tokens_for(kind, path, unit):
    if kind == "mapper-statement" and not unit.startswith("<"):
        return [unit.rsplit(".", 1)[-1]]
    if kind == "java-method" and "#" in unit:
        cls, rest = unit.split("#", 1)
        meth = rest.split("(")[0]
        return [cls] if meth.startswith("<") else [cls, meth]
    stem = os.path.splitext(path.split("/")[-1])[0]
    return [stem] if len(stem) > 3 else []


def pair_moves(deleted, added, old, new):
    """같은 파일명·내용 유사도 0.6 이상인 삭제·추가 쌍을 이동으로 묶는다."""
    moves = []
    by_base = {}
    for a in added:
        by_base.setdefault(a.split("/")[-1], []).append(a)
    for d in list(deleted):
        cands = by_base.get(d.split("/")[-1], [])
        best, score = None, 0.0
        for a in cands:
            s = similarity(old[d], new[a])
            if s > score:
                best, score = a, s
        if best and score >= 0.6:
            moves.append((d, best))
            cands.remove(best)
            deleted.remove(d)
            added.remove(best)
    return moves


def build(args):
    old_files, new_files = walk(args.old), walk(args.new)
    old = {k: Src(v) for k, v in old_files.items()}
    new = {k: Src(v) for k, v in new_files.items()}
    deleted = sorted(set(old) - set(new))
    added = sorted(set(new) - set(old))
    common = sorted(set(old) & set(new))
    stats = {"identical": 0, "format_only": 0}
    pairs = []   # (old_path, new_path, change)
    for k in common:
        if old[k].digest == new[k].digest:
            if open(old_files[k], "rb").read() == open(new_files[k], "rb").read():
                stats["identical"] += 1
            else:
                stats["format_only"] += 1
            continue
        pairs.append((k, k, "modified"))
    for d, a in pair_moves(deleted, added, old, new):
        pairs.append((d, a, "moved"))
    pairs += [(d, None, "deleted") for d in deleted]
    pairs += [(None, a, "added") for a in added]

    idx = slice_index(args.slices)
    tobe = ToBeIndex(args.target)
    os.makedirs(os.path.join(args.out, "diffs"), exist_ok=True)
    units, n = [], 0
    for op, np_, change in sorted(pairs, key=lambda x: (x[1] or x[0])):
        path = np_ or op
        a, b = (old.get(op) if op else None), (new.get(np_) if np_ else None)
        if (a and a.binary) or (b and b.binary) or os.path.splitext(path)[1].lower() not in CODE_EXT:
            n += 1
            units.append({"id": f"AD-{n:04d}", "file": path, "old_path": op, "kind": "asset", "unit": "<file>",
                          "change": change, "slices": slices_for(idx, path, "<file>"), "tobe_hits": [],
                          "verdict": "pending"})
            continue
        kind, ua = units_of(path, a.text) if a else (None, {})
        kind_b, ub = units_of(path, b.text) if b else (None, {})
        kind = kind or kind_b
        keys = sorted(set(ua) | set(ub))
        moved_same = change == "moved"
        for key in keys:
            ta, tb = ua.get(key), ub.get(key)
            if ta is not None and tb is not None and squash(ta) == squash(tb):
                continue
            uc = "added" if ta is None else "deleted" if tb is None else "modified"
            if key in ("<imports>",) and uc == "modified" and moved_same:
                uc = "moved"
            n += 1
            uid = f"AD-{n:04d}"
            dpath = os.path.join(args.out, "diffs", f"{uid}.diff")
            with open(dpath, "w", encoding="utf-8", newline="\n") as f:
                f.write(diff_text(ta, tb, f"old/{op or '-'}::{key}", f"new/{np_ or '-'}::{key}"))
            added_l = removed_l = 0
            for ln in open(dpath, encoding="utf-8"):
                if ln.startswith("+") and not ln.startswith("+++"):
                    added_l += 1
                elif ln.startswith("-") and not ln.startswith("---"):
                    removed_l += 1
            units.append({"id": uid, "file": path, "old_path": op if op != path else None, "kind": kind,
                          "unit": key, "change": uc, "file_change": change, "lines": f"+{added_l}/-{removed_l}",
                          "slices": slices_for(idx, path, key),
                          "tobe_hits": tobe.hits(tokens_for(kind, path, key)),
                          "diff": os.path.relpath(dpath, args.out).replace("\\", "/"),
                          "verdict": "pending", "note": ""})
    summary = {"old": os.path.abspath(args.old), "new": os.path.abspath(args.new),
               "target": os.path.abspath(args.target) if args.target else None,
               "files": {"identical": stats["identical"], "format_only": stats["format_only"],
                         "modified": sum(1 for p in pairs if p[2] == "modified"),
                         "moved": sum(1 for p in pairs if p[2] == "moved"),
                         "deleted": sum(1 for p in pairs if p[2] == "deleted"),
                         "added": sum(1 for p in pairs if p[2] == "added")},
               "units": len(units)}
    return summary, units


def write_md(path, summary, units):
    f = summary["files"]
    out = ["# AS-IS 현행화 차이 (asis_delta)", "",
           f"- 옛 AS-IS: `{summary['old']}`", f"- 새 AS-IS: `{summary['new']}`", f"- TO-BE: `{summary['target']}`", "",
           f"파일: 같음 {f['identical']} · 형식만 다름(인코딩·줄바꿈·공백) {f['format_only']} · 수정 {f['modified']} · "
           f"이동 {f['moved']} · 삭제 {f['deleted']} · 추가 {f['added']}  /  단위 {summary['units']}건", "",
           "판정(verdict): pending(미판정) · applied(TO-BE 가 이미 새 동작) · needs-change(반영 필요 → RR) · "
           "out-of-scope(변환 대상 아님 → JD) · asset(문서·자산, 반영 없음)", "",
           "| ID | 파일 | 단위 | 변경 | 줄 | slice | TO-BE 후보 | 판정 |", "|---|---|---|---|---|---|---|---|"]
    for u in units:
        hits = "<br>".join(u.get("tobe_hits") or []) or "-"
        out.append(f"| {u['id']} | {u['file']} | {u['unit']} | {u['change']} | {u.get('lines', '-')} | "
                   f"{', '.join(u['slices']) or '-'} | {hits} | {u['verdict']} |")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")


def main():
    fix_console_encoding()
    ap = argparse.ArgumentParser(description="AS-IS 현행화 차이를 의미 단위로 뽑아 slice·TO-BE 에 이어 붙인다")
    ap.add_argument("--old", required=True, help="옛 AS-IS 소스 루트")
    ap.add_argument("--new", required=True, help="새(현행화) AS-IS 소스 루트")
    ap.add_argument("--target", default=None, help="TO-BE 소스 루트(기본: 설정 target_dir)")
    ap.add_argument("--slices", default=None, help="slices.yaml (기본: workspace/<project>/slices/slices.yaml)")
    ap.add_argument("--out", default=None, help="출력 폴더(기본: workspace/<project>/knowledge/asis_delta)")
    args = ap.parse_args()
    for p in (args.old, args.new):
        if not os.path.isdir(p):
            sys.exit(f"[asis_delta] 폴더가 없다: {p}")
    args.target = args.target or target_dir()
    args.slices = args.slices or os.path.join(workspace(), "slices", "slices.yaml")
    args.out = args.out or os.path.join(workspace(), "knowledge", "asis_delta")
    summary, units = build(args)
    dump_yaml(os.path.join(args.out, "asis_delta.yaml"), {"schema": 1, "summary": summary, "units": units})
    write_md(os.path.join(args.out, "ASIS_DELTA.md"), summary, units)
    f = summary["files"]
    print(f"[asis_delta] 파일 수정 {f['modified']} · 이동 {f['moved']} · 삭제 {f['deleted']} · 추가 {f['added']} "
          f"(형식만 다름 {f['format_only']}) → 단위 {summary['units']}건")
    print(f"[asis_delta] {os.path.join(args.out, 'ASIS_DELTA.md')}")


if __name__ == "__main__":
    main()
