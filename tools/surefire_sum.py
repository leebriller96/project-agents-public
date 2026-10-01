# surefire XML 집계 — <testcase> 개수 기준(@Nested·파라미터라이즈에서 tests 속성과 어긋남)
# 사용: python tools/surefire_sum.py <target_dir>
import glob, sys, collections, xml.etree.ElementTree as ET
sys.stdout.reconfigure(encoding="utf-8")
root = sys.argv[1] if len(sys.argv) > 1 else "."
tot = collections.Counter()
for f in glob.glob(f"{root}/server/*/target/surefire-reports/TEST-*.xml") or glob.glob(f"{root}/**/target/surefire-reports/TEST-*.xml", recursive=True):
    r = ET.parse(f).getroot()
    parts = f.replace(chr(92), "/").split("/")
    m = parts[parts.index("target") - 1] if "target" in parts else "?"
    cases = r.findall(".//testcase")
    tot[(m, "tests")] += len(cases)
    for c in cases:
        for k, tag in (("failures", "failure"), ("errors", "error"), ("skipped", "skipped")):
            if c.find(tag) is not None:
                tot[(m, k)] += 1
mods = sorted({m for m, _ in tot})
for m in mods:
    print(m, {k: tot[(m, k)] for k in ("tests", "failures", "errors", "skipped")})
print("TOTAL", {k: sum(tot[(m, k)] for m in mods) for k in ("tests", "failures", "errors", "skipped")})
