#!/usr/bin/env python3
# runtime_config.py — (차세대) AS-IS 실행 자원 설정 인벤토리: 스레드·연결 풀·시간 제한·업로드·세션 값을 뽑아 TO-BE 대응을 판정한다
#
# 배경(실측): AS-IS 스케줄러 설정 XML 에 작업군마다 task:scheduler pool-size="10" 이 있었는데, 0단계는 설정 XML 에서
#       "빈·job 목록" 만 보고 값은 보지 않았다. TO-BE 배치에는 풀 설정 키가 아예 없어 프레임워크 기본값(스케줄러 스레드 1개)이
#       조용히 AS-IS 를 대체했고, 외부 DB 무응답 한 건이 모든 배치를 멈추는 결함이 7단계 실프로세스 시험에서야 나왔다.
#       같은 종류로 업로드 메모리 경계(AS-IS maxInMemorySize)·DB 풀 크기도 대조 없이 정해졌다.
#       키가 "없는" 차이는 diff·리뷰에 보이지 않는다 - 그래서 AS-IS 쪽에서 값을 전수로 뽑고, 항목마다 TO-BE 대응을 적게 한다.
#
# 사용법:
#   python tools/runtime_config.py scan --asis <AS-IS 폴더> [--exclude "<glob>" ...] [--out <yaml>]
#       설정 파일(xml·properties·yml)에서 실행 자원 키를 뽑아 RC-NNNN 항목으로 쓴다. 다시 돌리면 (파일, 키, 같은 키 순번) 기준으로
#       이전 판정을 이어받는다. 기본 out: workspace/<project>/knowledge/ASIS_RUNTIME_CONFIG.yaml (요약표 .md 도 같이 쓴다)
#       --exclude 는 AS-IS 기준 상대경로 glob(예: "profile/dev*/*") - 운영 프로필만 남겨 중복을 줄인다.
#   python tools/runtime_config.py set [RC-0001 ...] [--key <키 glob>] [--file <파일 glob>] --verdict <판정> [--tobe "<TO-BE 파일:키=값>"]
#       [--default "<프레임워크 기본값>"] [--note "<근거>"] [--out <yaml>]
#   python tools/runtime_config.py check [--out <yaml>]   - 미판정·근거 누락이 있으면 종료 1
#
# 판정(verdict):
#   same        TO-BE 에 같은 값을 설정했다 (--tobe 필수)
#   changed     TO-BE 에 다른 값을 설정했다 (--tobe 필수, note 에 JD-번호 필수 - 판단이므로)
#   default-ok  TO-BE 에 키가 없고 프레임워크 기본값으로 충분하다 (--default 필수, 값이 다르면 note 에 JD-번호 필수)
#   n/a         TO-BE 에 해당 구성 요소가 없다 (note 필수 - 무엇이 대체했나)
#   pending     아직 안 봤다 (check 실패)
import argparse
import fnmatch
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import dump_yaml, fix_console_encoding, load_yaml, workspace  # noqa: E402

VERDICTS = ("pending", "same", "changed", "default-ok", "n/a")
SKIP_DIRS = {"target", ".git", ".settings", "node_modules", "build", "dist", ".idea", "test", "tests"}
EXTS = {".xml", ".properties", ".yml", ".yaml"}

# 분류 -> 키 이름(소문자, 구분자 - _ . 제거 후 비교). 이름 끝이 이 중 하나면 잡는다.
CATEGORIES = {
    "thread": ["poolsize", "corepoolsize", "maxpoolsize", "queuecapacity", "threadcount", "maxthreads",
               "minsparethreads", "concurrency", "concurrentconsumers", "maxconcurrentconsumers"],
    "db-pool": ["maxactive", "maxtotal", "maxidle", "minidle", "initialsize", "maxwait", "maxwaitmillis",
                "maximumpoolsize", "minimumidle", "validationquery", "testonborrow", "timebetweenevictionrunsmillis"],
    "timeout": ["defaultstatementtimeout", "statementtimeout", "querytimeout", "sockettimeout", "connecttimeout",
                "connectiontimeout", "readtimeout", "idletimeout", "maxlifetime", "transactiontimeout",
                "removeabandonedtimeout", "logintimeout", "timeout"],
    "upload": ["maxuploadsize", "maxuploadsizeperfile", "maxinmemorysize", "maxfilesize", "maxrequestsize",
               "filesizethreshold", "maxswallowsize", "maxpostsize"],
    "session": ["sessiontimeout", "maxinactiveinterval"],
}
KEY2CAT = {k: c for c, ks in CATEGORIES.items() for k in ks}
ATTR_RE = re.compile(r"([A-Za-z][\w.:-]*)\s*=\s*\"([^\"]*)\"")
PROP_TAG_RE = re.compile(r"<property\b[^>]*\bname\s*=\s*\"([^\"]+)\"[^>]*\bvalue\s*=\s*\"([^\"]*)\"")
ELEM_RE = re.compile(r"<([A-Za-z][\w.:-]*)>\s*([^<\s][^<]*?)\s*</\1>")
KV_RE = re.compile(r"^\s*([A-Za-z][\w.\-\[\]]*)\s*[=:]\s*(.+?)\s*$")
TAG_RE = re.compile(r"<([A-Za-z][\w.:-]*)")


def norm(key):
    return re.sub(r"[-_.]", "", key.split(":")[-1].split(".")[-1]).lower()


def category(key):
    return KEY2CAT.get(norm(key))


def default_out():
    return os.path.join(workspace(), "knowledge", "ASIS_RUNTIME_CONFIG.yaml")


def read_text(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8", "cp949"):
        try:
            return raw.decode(enc).lstrip("﻿")
        except UnicodeDecodeError:
            pass
    return None


def scan_text(text, ext):
    """(줄 번호, 키, 값, 맥락) 목록. 맥락은 XML 이면 그 줄의 태그 이름(예: task:scheduler)."""
    out = []
    in_comment = False
    for no, line in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        if ext == ".xml":
            work = line
            if in_comment:
                if "-->" not in work:
                    continue
                work = work.split("-->", 1)[1]
                in_comment = False
            work = re.sub(r"<!--.*?-->", "", work)
            if "<!--" in work:
                work = work.split("<!--", 1)[0]
                in_comment = True
            m = TAG_RE.search(work)
            tag = m.group(1) if m else ""
            seen = set()
            for k, v in PROP_TAG_RE.findall(work):
                if category(k):
                    out.append((no, k, v, tag))
                    seen.add(k)
            for k, v in ATTR_RE.findall(work):
                if k in ("name", "value") or k in seen:
                    continue
                if category(k):
                    out.append((no, k, v, tag))
            for k, v in ELEM_RE.findall(work):
                if category(k):
                    out.append((no, k, v.strip(), k))
        else:
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("!"):
                continue
            m = KV_RE.match(line)
            if m and category(m.group(1)) and m.group(2) not in ("", "|", ">"):
                out.append((no, m.group(1), m.group(2).strip().strip("\"'"), ""))
    return out


def walk(asis, exclude=()):
    for root, dirs, files in os.walk(asis):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for f in sorted(files):
            ext = os.path.splitext(f)[1].lower()
            rel = os.path.relpath(os.path.join(root, f), asis).replace("\\", "/")
            if ext in EXTS and not any(fnmatch.fnmatch(rel, g) for g in exclude):
                yield os.path.join(root, f), ext


def scan(asis, prev_items, exclude=()):
    prev = {(i.get("file"), i.get("key"), i.get("seq", 0)): i for i in prev_items}
    items = []
    for path, ext in walk(asis, exclude):
        text = read_text(path)
        if text is None:
            continue
        rel = os.path.relpath(path, asis).replace("\\", "/")
        counter = {}
        for no, key, val, ctx in scan_text(text, ext):
            seq = counter.get(key, 0)
            counter[key] = seq + 1
            it = {"file": rel, "line": no, "key": key, "seq": seq, "value": val, "context": ctx,
                  "category": category(key), "verdict": "pending", "tobe": "", "framework_default": "", "note": ""}
            old = prev.get((rel, key, seq))
            if old:
                for f in ("verdict", "tobe", "framework_default", "note"):
                    it[f] = old.get(f, it[f])
            items.append(it)
    for n, it in enumerate(items, 1):
        it["id"] = f"RC-{n:04d}"
    return [{k: it[k] for k in ("id", "category", "file", "line", "key", "seq", "value", "context",
                                "verdict", "tobe", "framework_default", "note")} for it in items]


def problems(items):
    """판정 규칙 위반 목록 (id, 사유)."""
    out = []
    for it in items:
        v = it.get("verdict")
        note = str(it.get("note") or "")
        if v not in VERDICTS:
            out.append((it["id"], f"알 수 없는 판정 {v}"))
        elif v == "pending":
            out.append((it["id"], "미판정"))
        elif v in ("same", "changed") and not it.get("tobe"):
            out.append((it["id"], f"{v} 인데 TO-BE 위치(tobe)가 없다"))
        elif v == "changed" and not re.search(r"JD-\d+", note):
            out.append((it["id"], "changed 는 판단 기록(JD-번호)이 note 에 있어야 한다"))
        elif v == "default-ok" and not it.get("framework_default"):
            out.append((it["id"], "default-ok 인데 프레임워크 기본값(framework_default)이 없다"))
        elif (v == "default-ok" and str(it.get("framework_default")).strip() != str(it.get("value")).strip()
              and not re.search(r"JD-\d+", note)):
            out.append((it["id"], "기본값이 AS-IS 값과 다르면 note 에 JD-번호가 있어야 한다"))
        elif v == "n/a" and not note:
            out.append((it["id"], "n/a 는 무엇이 대체했는지 note 가 있어야 한다"))
    return out


def write_md(out, items):
    lines = ["# AS-IS 실행 자원 설정 인벤토리", "",
             "도구가 만든 표다. 손으로 고치지 말고 `python tools/runtime_config.py set` 으로 판정한다.", "",
             "| ID | 분류 | 위치 | 키 | AS-IS 값 | 판정 | TO-BE | 기본값 | 비고 |", "|---|---|---|---|---|---|---|---|---|"]
    for it in items:
        cell = [it["id"], it["category"], f"{it['file']}:{it['line']}", f"{it['context']} {it['key']}".strip(),
                it["value"], it["verdict"], it["tobe"], it["framework_default"], it["note"]]
        lines.append("| " + " | ".join(str(c).replace("|", "/") for c in cell) + " |")
    pend = sum(1 for it in items if it["verdict"] == "pending")
    lines += ["", f"전체 {len(items)}건, 미판정 {pend}건."]
    with open(os.path.splitext(out)[0] + ".md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def load(out):
    data = load_yaml(out) if os.path.isfile(out) else {}
    return data.get("items") or []


def save(out, items, asis=None):
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    data = load_yaml(out) if os.path.isfile(out) else {}
    data = {"schema": 1, "asis": asis or data.get("asis", ""), "items": items}
    dump_yaml(out, data)
    write_md(out, items)


def main(argv=None):
    fix_console_encoding()
    ap = argparse.ArgumentParser(description="AS-IS 실행 자원 설정 인벤토리")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--asis", required=True)
    s.add_argument("--exclude", action="append", default=[])
    s.add_argument("--out")
    t = sub.add_parser("set")
    t.add_argument("ids", nargs="*")
    t.add_argument("--key", help="키 이름 glob(대소문자 무시)")
    t.add_argument("--file", help="파일 상대경로 glob")
    t.add_argument("--verdict", required=True, choices=VERDICTS)
    t.add_argument("--tobe")
    t.add_argument("--default", dest="framework_default")
    t.add_argument("--note")
    t.add_argument("--out")
    c = sub.add_parser("check")
    c.add_argument("--out")
    a = ap.parse_args(argv)
    out = a.out or default_out()

    if a.cmd == "scan":
        if not os.path.isdir(a.asis):
            print(f"AS-IS 폴더가 없다: {a.asis}")
            return 2
        items = scan(a.asis, load(out), a.exclude)
        save(out, items, asis=a.asis)
        pend = sum(1 for it in items if it["verdict"] == "pending")
        print(f"{len(items)}건 (미판정 {pend}) -> {out}")
        return 0
    items = load(out)
    if not os.path.isfile(out):
        print(f"인벤토리가 없다: {out} (먼저 scan)")
        return 2
    if a.cmd == "set":
        idx = {it["id"]: it for it in items}
        missing = [i for i in a.ids if i not in idx]
        if missing:
            print(f"없는 항목: {', '.join(missing)}")
            return 2
        if a.key or a.file:
            for it in items:
                if ((not a.key or fnmatch.fnmatch(it["key"].lower(), a.key.lower()))
                        and (not a.file or fnmatch.fnmatch(it["file"], a.file)) and it["id"] not in a.ids):
                    a.ids.append(it["id"])
        if not a.ids:
            print("대상 항목이 없다(ID 나 --key·--file 을 준다)")
            return 2
        for i in a.ids:
            it = idx[i]
            it["verdict"] = a.verdict
            for f in ("tobe", "framework_default", "note"):
                if getattr(a, f) is not None:
                    it[f] = getattr(a, f)
        save(out, items)
        bad = [p for p in problems([idx[i] for i in a.ids]) if p[1] != "미판정"]
        for i, why in bad:
            print(f"주의 {i}: {why}")
        print(f"{len(a.ids)}건 판정 -> {a.verdict}")
        return 0
    bad = problems(items)
    for i, why in bad[:50]:
        print(f"{i}: {why}")
    print(f"전체 {len(items)}건, 문제 {len(bad)}건")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
