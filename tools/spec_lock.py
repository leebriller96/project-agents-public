#!/usr/bin/env python3
# spec_lock.py — 기대 동작 테스트(spec)를 잠근다: 코드를 만드는 에이전트가 테스트를 고쳐 통과시키지 못하게
#
# 배경: 지금까지 특성화 테스트는 코드를 만든 developer 가 직접 썼다. 자기가 이해한 대로 코드를 만들고 같은 이해로
#       테스트를 쓰니, 이해가 틀려도 테스트는 통과한다(자기 확인 편향). 그래서 기대 동작 테스트는 behavior-spec-writer 가
#       AS-IS 동작 계약만 보고 구현 전에 쓰고, 여기서 해시로 잠근다. 잠긴 파일의 수정은 훅이 막고, gate 가 해시를 대조한다.
#       잠금 해제는 사람만 한다(에이전트가 실행하면 훅이 막는다).
#
# 사용법:
#   python tools/spec_lock.py lock --slice <id> [--files <경로…>] [--by <주체>]   # spec 파일 해시·테스트 수 기록 (추가만 가능)
#   python tools/spec_lock.py verify [--slice <id>]                               # 해시 대조 (종료 코드 1 = 변경됨)
#   python tools/spec_lock.py list
#   python tools/spec_lock.py unlock --slice <id> --by <이름> --reason "…"       # 사람만. 매니페스트를 이력으로 옮긴다
#
# spec 파일 위치(기본, config verification.spec_globs 로 바꿀 수 있다; target_dir 기준):
#   backend : **/src/test/java/**/spec/<slice 패키지명>/**    (예: …/spec/loan/LoanSpecTest.java)
#   frontend: **/__spec__/<slice>/**
# 의존성: pyyaml (config 읽기)

import argparse
import datetime
import glob
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import atomic_write_text, config, safe_relpath, file_lock, fix_console_encoding, target_dir, workspace  # noqa: E402

fix_console_encoding()

KST = datetime.timezone(datetime.timedelta(hours=9), name="KST")
DEFAULT_GLOBS = ["**/src/test/java/**/spec/{pkg}/**/*", "**/src/test/resources/spec/{pkg}/**/*",
                 "**/__spec__/{slice}/**/*"]
# 단순명(@Test)과 완전 한정명(@org.junit.jupiter.api.Test) 모두
JAVA_TEST_RE = re.compile(r"@(?:[\w$]+\.)*(?:Test|ParameterizedTest|RepeatedTest|TestFactory|TestTemplate)\b")
TS_TEST_RE = re.compile(r"(?<![\w.])(?:it|test)(?:\.each\s*\([^)]*\)\s*)?\s*\(\s*['\"`]")


def now():
    return datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")


def spec_dir():
    return os.path.join(workspace(), "specs")


def manifest_path(slice_id):
    return os.path.join(spec_dir(), f"{slice_id}.lock.json")


def rel(p, base):
    return safe_relpath(p, base)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_eol_variants(path):
    """줄끝만 다른 같은 내용의 해시들 - 원본·LF 로 맞춘 것·CRLF 로 맞춘 것.

    실측: 같은 커밋을 .gitattributes eol=lf 로 꺼낸 검증 작업 트리에서 CRLF 로 잠근 파일이 '수정됨' 으로 나왔다.
    내용은 같고 줄끝만 다른 경우는 잠금 위반이 아니다.
    """
    with open(path, "rb") as f:
        raw = f.read()
    lf = raw.replace(b"\r\n", b"\n")
    crlf = lf.replace(b"\n", b"\r\n")
    return {hashlib.sha256(b).hexdigest() for b in (raw, lf, crlf)}


def count_tests(path):
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return 0
    if path.endswith(".java") or path.endswith(".kt"):
        return len(JAVA_TEST_RE.findall(text))
    if re.search(r"\.(test|spec)\.[jt]sx?$", path) or "__spec__" in path.replace(os.sep, "/"):
        return len(TS_TEST_RE.findall(text))
    return 0


def slice_globs(slice_id):
    pkg = slice_id.replace("-", "")
    globs = (config().get("verification") or {}).get("spec_globs") or DEFAULT_GLOBS
    return [g.format(slice=slice_id, pkg=pkg) for g in globs]


def discover(td, slice_id):
    out = set()
    for g in slice_globs(slice_id):
        for p in glob.glob(os.path.join(td, g), recursive=True):
            if os.path.isfile(p) and "/node_modules/" not in p.replace(os.sep, "/"):
                out.add(os.path.normpath(p))
    return sorted(out)


def load_manifest(slice_id):
    p = manifest_path(slice_id)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def all_manifests():
    out = {}
    for p in sorted(glob.glob(os.path.join(spec_dir(), "*.lock.json"))):
        try:
            with open(p, encoding="utf-8") as f:
                m = json.load(f)
            out[m["slice"]] = m
        except (OSError, ValueError, KeyError):
            continue
    return out


def locked_slice_of(path, td=None):
    """path(절대·상대)가 잠긴 spec 파일이면 그 slice id."""
    td = td or target_dir()
    if not td:
        return None
    ap = os.path.abspath(path if os.path.isabs(path) else os.path.join(td, path))
    try:
        r = rel(ap, td)
    except ValueError:
        return None
    for sl, m in all_manifests().items():
        if r in (m.get("files") or {}):
            return sl
    return None


def verify(slice_id, td):
    """[(문제 종류, 파일, 설명)] — 빈 목록이면 잠금 그대로."""
    m = load_manifest(slice_id)
    if not m:
        return [("no-lock", "", f"{slice_id} 의 잠금 매니페스트가 없다")]
    out = []
    for r, h in sorted((m.get("files") or {}).items()):
        p = os.path.join(td, r)
        if not os.path.exists(p):
            out.append(("deleted", r, "잠긴 spec 파일이 삭제됐다"))
        elif h not in sha256_eol_variants(p):
            out.append(("modified", r, "잠긴 spec 파일이 수정됐다"))
    return out


def cmd_lock(args):
    td = args.target or target_dir()
    if not td or not os.path.isdir(td):
        sys.exit(f"[spec_lock] target_dir 이 없다: {td}")
    files = [os.path.abspath(f if os.path.isabs(f) else os.path.join(td, f)) for f in args.files] if args.files \
        else discover(td, args.slice)
    if not files:
        sys.exit(f"[spec_lock] {args.slice} 의 spec 파일을 찾지 못했다. 위치: {', '.join(slice_globs(args.slice))}")
    os.makedirs(spec_dir(), exist_ok=True)
    path = manifest_path(args.slice)
    with file_lock(path):
        m = load_manifest(args.slice) or {"slice": args.slice, "files": {}, "tests": {}, "history": []}
        added, changed = [], []
        for f in files:
            r = rel(f, td)
            h = sha256(f)
            if r in m["files"]:
                # verify 와 같은 기준 - 줄바꿈(CRLF/LF)만 다른 것은 같은 파일이다
                # (실측: 같은 커밋을 다른 작업 트리로 꺼내자 autocrlf 차이로 잠긴 파일 11개가 '바뀌었다' 로 막혔다)
                if m["files"][r] not in sha256_eol_variants(f):
                    changed.append(r)
                continue
            m["files"][r] = h
            m["tests"][r] = count_tests(f)
            added.append(r)
        if changed:
            sys.exit("[spec_lock] 이미 잠긴 파일이 바뀌었다 — 잠금은 추가만 가능하다. 사람이 unlock 후 다시 잠근다:\n  "
                     + "\n  ".join(changed))
        m["test_count"] = sum(m["tests"].values())
        m["locked_at"] = m.get("locked_at") or now()
        m["updated_at"] = now()
        m["locked_by"] = args.by or m.get("locked_by") or "orchestrator"
        # 병렬 작업 트리에서는 잠근 트리가 기본 target_dir 과 다를 수 있다 - verify 가 다른 트리와 비교하는 것을 알린다
        m["locked_target"] = os.path.abspath(td)
        atomic_write_text(path, json.dumps(m, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(f"{args.slice}: 잠금 {len(m['files'])}개 파일 (신규 {len(added)}) · 테스트 {m['test_count']}건 → {path}")
    return 0


def cmd_verify(args):
    td = args.target or target_dir()
    targets = [args.slice] if args.slice else sorted(all_manifests())
    bad = 0
    for sl in targets:
        probs = verify(sl, td)
        for kind, r, msg in probs:
            print(f"- [{sl}] {kind} {r}: {msg}")
        lt = (load_manifest(sl) or {}).get("locked_target")
        if probs and not args.target and lt and os.path.normcase(os.path.abspath(lt)) != os.path.normcase(os.path.abspath(td)):
            print(f"  주의: [{sl}] 는 다른 작업 트리({lt})에서 잠갔다 - 그 트리를 보려면 --target 을 준다 (지금 비교: {td})")
        bad += len(probs)
        if not probs:
            print(f"[{sl}] 잠금 그대로")
    return 1 if bad else 0


def cmd_list(args):
    ms = all_manifests()
    if not ms:
        print("잠긴 spec 없음")
    for sl, m in ms.items():
        print(f"{sl:<20} 파일 {len(m.get('files') or {}):>3} · 테스트 {m.get('test_count', 0):>4} · 잠금 {m.get('locked_at')} ({m.get('locked_by')})")
    return 0


def cmd_unlock(args):
    path = manifest_path(args.slice)
    with file_lock(path):
        m = load_manifest(args.slice)
        if not m:
            sys.exit(f"[spec_lock] {args.slice} 는 잠겨 있지 않다")
        hist_dir = os.path.join(spec_dir(), "history")
        os.makedirs(hist_dir, exist_ok=True)
        m["unlocked_at"], m["unlocked_by"], m["unlock_reason"] = now(), args.by, args.reason
        stamp = datetime.datetime.now(KST).strftime("%y%m%d%H%M%S")
        atomic_write_text(os.path.join(hist_dir, f"{args.slice}.{stamp}.json"),
                          json.dumps(m, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        os.remove(path)
    print(f"{args.slice}: 잠금 해제 ({args.by}: {args.reason}) — 수정 후 다시 lock 한다")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="기대 동작 테스트(spec) 잠금")
    ap.add_argument("--target", help="target_dir (기본: config)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("lock")
    p.add_argument("--slice", required=True)
    p.add_argument("--files", nargs="*")
    p.add_argument("--by")
    p.set_defaults(fn=cmd_lock)
    p = sub.add_parser("verify")
    p.add_argument("--slice")
    p.set_defaults(fn=cmd_verify)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    p = sub.add_parser("unlock")
    p.add_argument("--slice", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(fn=cmd_unlock)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
