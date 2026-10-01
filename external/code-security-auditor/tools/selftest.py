#!/usr/bin/env python3
# selftest.py — tools/ 스크립트들이 정상 동작하는지 몇 초 안에 확인하는 회귀 테스트.
#
# 사용법:
#   python tools/selftest.py
#
# 외부 SAST 도구 설치 여부와 무관하게 동작한다 (정규화기는 픽스처 JSON 으로 검사).
# 스크립트나 템플릿을 고친 뒤, 커밋 전에 실행한다. 방법론(SKILL.md) 자체의 검증은
# examples/vulnerable-flask/EXPECTED.md 절차로 따로 한다.

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"
SAMPLE = REPO / "examples" / "vulnerable-flask" / "sample_report.md"
SAST_DIR = REPO / "reports" / ".sast"
PY = sys.executable
ENV = {**os.environ, "PYTHONUTF8": "1"}

failures = []


def check(name, cond, detail=""):
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def run(*args, cwd=None):
    proc = subprocess.run([PY, *args], cwd=cwd or REPO, env=ENV, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    return proc.returncode, proc.stdout + proc.stderr


def main():
    tmp = Path(tempfile.mkdtemp(prefix="auditor-selftest-"))
    saved_sast = None
    try:
        print("1) kst_now.py")
        rc, out = run(TOOLS / "kst_now.py")
        check("yymmddHHMM 형식", rc == 0 and len(out.strip()) == 10 and out.strip().isdigit(), out)
        rc, out = run(TOOLS / "kst_now.py", "--full")
        check("--full 형식", rc == 0 and len(out.strip()) == 16, out)

        print("2) build_report.py (샘플 레포트)")
        md = tmp / "2601010000_security_report.md"
        shutil.copy(SAMPLE, md)
        rc, out = run(TOOLS / "build_report.py", md)
        html = md.with_suffix(".html")
        check("HTML 생성", rc == 0 and html.exists(), out)
        if html.exists():
            h = html.read_text(encoding="utf-8")
            check("H1 이 <title> 로", "<title>보안 취약점 감사 레포트" in h)
            check("심각도 배지 적용", h.count('class="sev sev-') >= 10)
            check("목차 생성", '<details class="toc"' in h)
            check("코드 블록 렌더링", 'class="codehilite"' in h)
            check("시크릿 원문 없음", "AKIAIOSFODNN7EXAMPLE" not in h and "wJalrXUtnFEMI" not in h)
            import re as _re
            blocks = _re.findall(r'<details class="finding" data-sev="(\w+)".*?</details>', h, _re.S)
            check("발견 항목 13개가 접이식으로 래핑", len(blocks) == 13, str(len(blocks)))
            check("필터 바 1개", h.count('id="filterbar"') == 1)
            check("항목 래핑이 h2 섹션을 삼키지 않음",
                  all("<h2" not in b for b in _re.findall(r'<details class="finding".*?</details>', h, _re.S)))

        print("3) export_findings.py")
        rc, out = run(TOOLS / "export_findings.py", md, "--sarif")
        fj = Path(str(md.with_suffix("")) + ".findings.json")
        sarif = Path(str(md.with_suffix("")) + ".sarif")
        check("JSON/SARIF 생성", rc == 0 and fj.exists() and sarif.exists(), out)
        check("파싱 경고 없음", "경고" not in out, out)
        if fj.exists():
            d = json.loads(fj.read_text(encoding="utf-8"))
            check("13건 추출", d["summary"]["total"] == 13, str(d["summary"]))
            check("모든 항목에 심각도·위치", all(f["severity"] and f["locations"] for f in d["findings"]))
            check("OWASP 2025 ID 만", all(o.endswith(":2025") for f in d["findings"] for o in f["owasp"]))
        if sarif.exists():
            s = json.loads(sarif.read_text(encoding="utf-8"))
            check("SARIF 구조", s["version"] == "2.1.0" and len(s["runs"][0]["results"]) == 13)

        print("4) report_diff.py")
        newer = tmp / "2601020000_security_report.md"
        text = md.read_text(encoding="utf-8")
        # F-001 제거, F-005 라인 이동 → 해결 1, 잔존 12, 신규 0 이어야 함
        import re
        text = re.sub(r"### \[F-001\].*?(?=\n### \[)", "", text, flags=re.S)
        text = text.replace("- **위치**: `app.py:63`", "- **위치**: `app.py:70`")
        newer.write_text(text, encoding="utf-8")
        rc, out = run(TOOLS / "report_diff.py", md, newer)
        check("diff 실행", rc == 0, out)
        check("신규 0 · 잔존 12 · 해결 1", "신규 0건 · 잔존 12건 · 해결 1건" in out, out[:300])
        check("라인 이동 추적", "app.py:70" in out and "F-005 → F-005" in out)

        print("5) summarize_sast.py (픽스처)")
        if SAST_DIR.exists():
            saved_sast = tmp / "sast_backup"
            shutil.move(str(SAST_DIR), str(saved_sast))
        SAST_DIR.mkdir(parents=True)
        target = tmp / "target"
        target.mkdir()
        (target / ".auditignore").write_text("app.py:5 B403 # 테스트 억제\n", encoding="utf-8")
        (SAST_DIR / "bandit.json").write_text(json.dumps({"results": [
            {"test_id": "B105", "test_name": "hardcoded_password_string", "filename": str(target / "config.py"),
             "line_number": 2, "issue_text": "Possible hardcoded password: 'super-secret-value'",
             "issue_severity": "LOW", "issue_confidence": "MEDIUM", "issue_cwe": {"id": 259}},
            {"test_id": "B403", "test_name": "blacklist", "filename": str(target / "app.py"),
             "line_number": 5, "issue_text": "pickle import", "issue_severity": "LOW",
             "issue_confidence": "HIGH", "issue_cwe": {"id": 502}},
        ]}), encoding="utf-8")
        (SAST_DIR / "gitleaks.json").write_text(json.dumps([
            {"RuleID": "aws-access-token", "Description": "AWS Access Token", "File": str(target / "config.py"),
             "StartLine": 4, "Secret": "AKIA_SHOULD_NOT_APPEAR", "Match": "AKIA_SHOULD_NOT_APPEAR"}
        ]), encoding="utf-8")
        (SAST_DIR / "osv-scanner.json").write_text(json.dumps({"results": [{"packages": [
            {"package": {"name": "org.apache.logging.log4j:log4j-core", "version": "2.14.1"}, "vulnerabilities": [
                {"id": "GHSA-jfh8-c2jp-5v3q", "aliases": ["CVE-2021-44228"], "summary": "Log4Shell",
                 "database_specific": {"severity": "CRITICAL", "cwe_ids": ["CWE-917"]},
                 "affected": [{"ranges": [{"events": [{"introduced": "2.0"}, {"fixed": "2.15.0"}]}]}]},
                {"id": "PYSEC-DUP", "aliases": ["CVE-2021-44228"], "summary": "dup", "database_specific": {}, "affected": []},
            ]}]}]}), encoding="utf-8")
        (SAST_DIR / "summary.json").write_text(json.dumps({"target": str(target), "results": [
            {"tool": "bandit", "status": "실행", "reason": "", "output": "reports/.sast/bandit.json", "findings": 2},
            {"tool": "gitleaks", "status": "실행", "reason": "", "output": "reports/.sast/gitleaks.json", "findings": 1},
            {"tool": "osv-scanner", "status": "실행", "reason": "", "output": "reports/.sast/osv-scanner.json", "findings": 2, "file": "pom.xml"},
            {"tool": "semgrep", "status": "미설치", "reason": "x", "output": None, "findings": None},
        ]}, ensure_ascii=False), encoding="utf-8")
        rc, out = run(TOOLS / "summarize_sast.py", "--show-suppressed")
        check("정규화 실행", rc == 0, out)
        check("총 4건 (osv 중복 병합)", "총 4건" in out)
        check("osv Log4Shell Critical", "| Critical | osv-scanner | GHSA-jfh8-c2jp-5v3q (CVE-2021-44228) | `pom.xml` | CWE-917" in out)
        check("B105 값 마스킹", "'supe****'" in out and "super-secret-value" not in out)
        check("gitleaks 시크릿 제거", "AKIA_SHOULD_NOT_APPEAR" not in out)
        check(".auditignore 억제", "억제**: 1건" in out and "[억제: 테스트 억제" in out)
        norm = SAST_DIR / "normalized.json"
        check("normalized.json 에 시크릿 없음",
              norm.exists() and "AKIA_SHOULD_NOT_APPEAR" not in norm.read_text(encoding="utf-8")
              and "super-secret-value" not in norm.read_text(encoding="utf-8"))

        print("6) run_sast.py (도구 없는 경로)")
        empty = tmp / "empty"
        empty.mkdir()
        rc, out = run(TOOLS / "run_sast.py", empty)
        check("도구 미설치/건너뜀이면 exit 2 또는 실행 시 0", rc in (0, 2), out[-300:])
        check("summary.json 생성", (SAST_DIR / "summary.json").exists())
    finally:
        if SAST_DIR.exists():
            shutil.rmtree(SAST_DIR, ignore_errors=True)
        if saved_sast and saved_sast.exists():
            shutil.move(str(saved_sast), str(SAST_DIR))
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failures:
        print(f"[selftest] 실패 {len(failures)}건: " + ", ".join(failures))
        sys.exit(1)
    print("[selftest] 전부 통과")


if __name__ == "__main__":
    main()
