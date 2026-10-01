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
           "oldest_mtime": float|None, "newest_mtime": float|None, "parse_errors": [경로…]}
    failures 는 <failure>, errors 는 <error> 가 달린 testcase 수다.
    """
    out = {"files": 0, "tests": 0, "failures": 0, "errors": 0, "skipped": 0,
           "oldest_mtime": None, "newest_mtime": None, "parse_errors": []}
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
            if c.find("failure") is not None:
                out["failures"] += 1
            elif c.find("error") is not None:
                out["errors"] += 1
            elif c.find("skipped") is not None:
                out["skipped"] += 1
    return out
