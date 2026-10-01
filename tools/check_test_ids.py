# 산출물 문서(4분류표·기능 추적표 등)에 인용된 테스트 ID(`클래스.메서드`) 가 실재하는지 전수 대조
# 사용: python tools/check_test_ids.py <target_dir> <문서 경로(상대)> [-v]
#   예: python tools/check_test_ids.py C:/sample2 docs/deliverables/common-inheritance.md
#   Java(surefire) 기준. JS/TS 테스트 대조는 별도.
import re, sys, pathlib
sys.stdout.reconfigure(encoding="utf-8")
args = [a for a in sys.argv[1:] if not a.startswith("-")]
if len(args) < 2:
    print(__doc__ or "인자: <target_dir> <문서 경로>"); sys.exit(2)
ROOT = pathlib.Path(args[0])
DOC = ROOT / args[1]
TEST_DIRS = list(ROOT.glob("server/*/src/test/java")) or list(ROOT.glob("backend/src/test/java"))

# 테스트 클래스 → (모듈, 메서드 집합)
classes = {}
for d in TEST_DIRS:
    module = d.parts[len(ROOT.parts) + 1]
    for f in d.rglob("*Test.java"):
        src = f.read_text(encoding="utf-8")
        methods = set(re.findall(r"void\s+(\w+)\s*\(", src)) | set(re.findall(r"class\s+(\w+)\s*\{", src))  # @Nested 클래스명도 허용
        classes.setdefault(f.stem, []).append((module, methods, f))

MODULE_ALIAS = {"dn": "domain-notice", "common": "common", "user": "user", "admin": "admin"}

full_re = re.compile(r"^(\*?[A-Za-z]\w*Test)((?:\.\w+)*)\.(\w+\*?|\*)$")   # Test[.Nested…].method
short_re = re.compile(r"^\.(\w+\*?|\*)$")

DOC_TEXT = DOC.read_text(encoding="utf-8")
# 문서 범례 "테스트(약어): `SvcT` = `…/NoticeAdminServiceTest.java`" → 약어 → 클래스명
ALIAS = {}
for m in re.finditer(r"`(\w+)`\s*=\s*`[^`]*?(\w+Test)\.java`", DOC_TEXT):
    ALIAS[m.group(1)] = m.group(2)
# 다른 범례 형식: "`service/NoticeServiceTest`(이하 `SvcT`)"
for m in re.finditer(r"`[^`]*?(\w+Test)`\s*\(이하\s*`(\w+)`", DOC_TEXT):
    ALIAS[m.group(2)] = m.group(1)
if ALIAS:
    print("범례 약어:", ", ".join(f"{k}={v}" for k, v in ALIAS.items()))

def expand_alias(tok: str) -> str:
    head = tok.split(".", 1)[0].lstrip("*")
    if head in ALIAS:
        return ALIAS[head] + tok[len(head):] if not tok.startswith("*") else "*" + ALIAS[head] + tok[len(head)+1:]
    return tok

results = []  # (line, token, resolved_id, status, detail)
for ln, line in enumerate(DOC_TEXT.splitlines(), 1):
    if not line.startswith("|"):
        continue
    cells = line.split("|")
    for cell in cells:
        prev_cls = None
        # 토큰 앞의 모듈 접두어(dn/common/user/admin) 추출용
        for m in re.finditer(r"(?:(?P<mod>\b(?:dn|common|user|admin)\b)\s+)?`(?P<tok>[^`]+)`", cell):
            tok = expand_alias(m.group("tok"))
            mod = m.group("mod")
            fm = full_re.match(tok)
            sm = short_re.match(tok)
            if fm:
                cls, nested, meth = fm.group(1), fm.group(2), fm.group(3)
                prev_cls = cls  # 중첩 클래스 경로는 대조에서 생략(메서드 실재만 확인)
                cur_mod = mod
            elif sm and prev_cls:
                cls, meth = prev_cls, sm.group(1)
            else:
                continue
            rid = f"{cls}.{meth}"
            # 클래스 실재
            if cls.startswith("*"):
                cands = [(c, v) for c, v in classes.items() if c.endswith(cls[1:])]
                if not cands:
                    results.append((ln, tok, rid, "MISSING_CLASS", "")); continue
                if meth.endswith("*"):
                    pre = meth[:-1]
                    ok = all(any(mm.startswith(pre) for mm in ms) for c, v in cands for (_, ms, _) in v)
                    results.append((ln, tok, rid, "OK" if ok else "MISSING_METHOD", ",".join(c for c, _ in cands)))
                continue
            if cls not in classes:
                results.append((ln, tok, rid, "MISSING_CLASS", "")); continue
            if meth == "*":
                results.append((ln, tok, rid, "OK", "wildcard")); continue
            if meth.endswith("*"):
                pre = meth[:-1]
                found = [(module, f) for (module, ms, f) in classes[cls] if any(mm.startswith(pre) for mm in ms)]
                results.append((ln, tok, rid, "OK" if found else "MISSING_METHOD", "prefix")); continue
            found = [(module, f) for (module, ms, f) in classes[cls] if meth in ms]
            if not found:
                results.append((ln, tok, rid, "MISSING_METHOD", ""))
            else:
                results.append((ln, tok, rid, "OK", found[0][0]))

ok = [r for r in results if r[3] == "OK"]
bad = [r for r in results if r[3] != "OK"]
uniq = {r[2] for r in results}
print(f"인용 토큰 {len(results)}건 (고유 ID {len(uniq)}건), OK {len(ok)}, 불일치 {len(bad)}")
for r in bad:
    print(f"  L{r[0]}  {r[2]}  {r[3]}  token=`{r[1]}`")
if "-v" in sys.argv:
    for r in ok:
        print(f"  L{r[0]}  {r[2]}  {r[4]}")
