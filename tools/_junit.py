# _junit.py — JUnit XML(테스트 결과 파일) 집계. 외부 의존성 없음.
#
# 목적: 게이트의 테스트 개수·실패 수를 에이전트가 적은 값이 아니라 실제 결과 파일에서 센다.
#       JUnit XML 은 Gradle(build/test-results)·Maven surefire/failsafe·vitest(--reporter=junit)·
#       Playwright(junit reporter)·Jest(jest-junit) 가 모두 내는 공통 형식이다.
# 집계 기준: <testcase> 요소 수. (<testsuite tests=""> 속성은 @Nested·파라미터라이즈에서 실제와 어긋난 실측이 있다)

import glob
import os
import xml.etree.ElementTree as ET


def resolve(patterns, base):
    """glob 패턴(문자열 또는 목록)을 base 기준으로 풀어 정렬된 파일 목록으로 돌려준다."""
    if isinstance(patterns, str):
        patterns = [patterns]
    files = set()
    for pat in patterns or []:
        if not isinstance(pat, str) or not pat.strip():
            continue
        p = pat if os.path.isabs(pat) else os.path.join(base, pat)
        for f in glob.glob(p, recursive=True):
            if os.path.isfile(f):
                files.add(os.path.normpath(f))
    return sorted(files)


def summarize(files):
    """결과 파일들을 집계한다.

    반환: {"files": n, "tests": n, "failures": n, "errors": n, "skipped": n,
           "oldest_mtime": float|None, "newest_mtime": float|None, "parse_errors": [경로…],
           "failed_names": ["<단순 클래스 이름>.<메서드>", …]}
    failures 는 <failure>, errors 는 <error> 가 달린 testcase 수다.
    failed_names 는 기준선(기존 실패 목록) 대조용이다 — 클래스는 패키지·중첩($) 없이 단순 이름.
    """
    out = {"files": 0, "tests": 0, "failures": 0, "errors": 0, "skipped": 0,
           "oldest_mtime": None, "newest_mtime": None, "parse_errors": [], "failed_names": []}
    for f in files:
        try:
            root = ET.parse(f).getroot()
        except (ET.ParseError, OSError):
            out["parse_errors"].append(f)
            continue
        out["files"] += 1
        mt = os.path.getmtime(f)
        out["oldest_mtime"] = mt if out["oldest_mtime"] is None else min(out["oldest_mtime"], mt)
        out["newest_mtime"] = mt if out["newest_mtime"] is None else max(out["newest_mtime"], mt)
        cases = list(root.iter("testcase"))
        if not cases:
            # testcase 없이 testsuite 속성만 있는 형식(드묾)
            for ts in root.iter("testsuite"):
                if ts.find("testsuite") is not None:
                    continue
                out["tests"] += int(ts.get("tests", 0) or 0)
                out["failures"] += int(ts.get("failures", 0) or 0)
                out["errors"] += int(ts.get("errors", 0) or 0)
                out["skipped"] += int(ts.get("skipped", 0) or 0)
            continue
        for c in cases:
            out["tests"] += 1
            bad = c.find("failure") is not None or c.find("error") is not None
            if c.find("failure") is not None:
                out["failures"] += 1
            elif c.find("error") is not None:
                out["errors"] += 1
            elif c.find("skipped") is not None:
                out["skipped"] += 1
            if bad:
                cls = (c.get("classname") or "").split(".")[-1].split("$")[0]
                out["failed_names"].append(f"{cls}.{c.get('name') or ''}")
    return out


def load_baseline(path):
    """기존 실패 목록(기준선) 파일을 읽는다. 한 줄에 하나 — `클래스.메서드` 또는 `클래스`(그 클래스 전체).

    `#` 뒤는 주석, 빈 줄은 무시한다. 클래스는 패키지 없이 단순 이름으로 적는다.
    path 가 폴더면 그 안의 JUnit XML(기준선 실행의 결과 사본)에서 실패한 testcase 이름을 기준선으로 쓴다
    (실측: 에이전트가 기준선으로 결과 사본 폴더를 적어 게이트가 PermissionError 로 멈췄다).
    """
    if os.path.isdir(path):
        files = sorted(glob.glob(os.path.join(path, "**", "*.xml"), recursive=True))
        return sorted(set(summarize(files)["failed_names"]))
    entries = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            s = line.split("#", 1)[0].strip()
            if s:
                entries.append(s)
    return entries


def outside_baseline(failed_names, entries):
    """기준선으로 설명되지 않는 실패 이름 목록. 항목이 `클래스` 면 그 클래스 전체,
    `클래스.메서드` 면 그 메서드(파라미터 표기 `메서드(…)`·`메서드[1]` 포함)를 덮는다."""
    classes = {e for e in entries if "." not in e}
    methods = [e for e in entries if "." in e]
    out = []
    for n in failed_names:
        cls = n.split(".", 1)[0]
        if cls in classes:
            continue
        if any(n == m or n.startswith(m + "(") or n.startswith(m + "[") for m in methods):
            continue
        out.append(n)
    return out
