#!/usr/bin/env python3
# export_findings.py — Markdown 레포트의 발견 항목을 기계 판독 형식(JSON / SARIF 2.1.0)으로 내보낸다.
#
# 사용법:
#   python tools/export_findings.py reports/2606291651_security_report.md            # → .findings.json
#   python tools/export_findings.py reports/2606291651_security_report.md --sarif    # → .sarif 도 생성
#
# 레포트 Markdown 이 단일 원본이다. templates/report_template.md 의 구조
#   ### [F-001] 제목
#   - **심각도**: Critical
#   - **확신도**: 확실
#   - **분류**: CWE-89, OWASP A05:2025 ...
#   - **위치**: `app.py:32`, `config.py:2-5`
#   - **탐지 출처**: ...
#   - **CVSS(추정)**: 9.8 / AV:N/...
# 를 파싱하므로, 이 형식을 지키면 별도 JSON 을 손으로 쓸 필요가 없다.
#
# 용도: CI 게이트(심각도별 건수 판정), GitHub Code Scanning 업로드(SARIF), 레포트 간 비교(report_diff.py).

import datetime
import json
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SEVERITIES = ["Critical", "High", "Medium", "Low", "Info"]
SARIF_LEVEL = {"Critical": "error", "High": "error", "Medium": "warning", "Low": "note", "Info": "note"}
# SARIF security-severity (GitHub 가 심각도 표시에 사용, CVSS 스케일)
SARIF_SEC_SEVERITY = {"Critical": "9.5", "High": "7.5", "Medium": "5.0", "Low": "2.5", "Info": "0.5"}

FINDING_HEAD = re.compile(r"^###\s+\[(F-\d+)\]\s+(.+?)\s*$", re.M)
FIELD = re.compile(r"^-\s+\*\*(.+?)\*\*\s*:\s*(.+?)\s*$", re.M)
LOCATION = re.compile(r"`([^`\s:]+(?:\.[A-Za-z0-9]+)?(?::\d+(?:-\d+)?)?)`")
CWE = re.compile(r"CWE-\d+")
OWASP = re.compile(r"A\d{2}:\d{4}")
CVSS_SCORE = re.compile(r"(\d+(?:\.\d+)?)\s*/")
CVSS_VECTOR = re.compile(r"AV:[NALP]/AC:[LH]/PR:[NLH]/UI:[NR]/S:[UC]/C:[NLH]/I:[NLH]/A:[NLH]")


def parse_locations(text: str):
    locs = []
    for m in LOCATION.finditer(text):
        token = m.group(1)
        file, _, rng = token.partition(":")
        start = end = None
        if rng:
            a, _, b = rng.partition("-")
            start = int(a)
            end = int(b) if b else start
        locs.append({"file": file.replace("\\", "/"), "start_line": start, "end_line": end})
    return locs


def parse_report(md_text: str):
    """레포트 전체에서 메타데이터와 발견 항목 목록을 뽑는다."""
    meta = {}
    for key in ("대상", "분석 일시(KST)", "분석 모드", "분석 도구"):
        m = re.search(rf"^-\s+\*\*{re.escape(key)}\*\*\s*:\s*(.+?)\s*$", md_text, re.M)
        if m:
            val = m.group(1).strip()
            code = re.match(r"`([^`]+)`", val)   # `값` (부연) 형태면 코드 스팬만 취한다
            meta[key] = code.group(1) if code else val
    title_m = re.search(r"^#\s+(.+?)\s*$", md_text, re.M)
    meta["title"] = title_m.group(1) if title_m else ""

    heads = list(FINDING_HEAD.finditer(md_text))
    findings = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(md_text)
        block = md_text[h.end():end]
        # 다음 ## 섹션이 시작되면 거기까지만
        sec = re.search(r"^##\s", block, re.M)
        if sec:
            block = block[:sec.start()]
        fields = {k.strip(): v.strip() for k, v in FIELD.findall(block)}

        sev_raw = fields.get("심각도", "")
        severity = next((s for s in SEVERITIES if s.lower() in sev_raw.lower()), "")
        cvss = fields.get("CVSS(추정)", "")
        score_m, vec_m = CVSS_SCORE.search(cvss), CVSS_VECTOR.search(cvss)
        desc_m = re.search(r"\*\*설명\*\*\s*\n(.+?)(?:\n\s*\n|\Z)", block, re.S)

        findings.append({
            "id": h.group(1),
            "title": h.group(2).strip(),
            "severity": severity,
            # 확신도는 필드 값의 **첫 토큰**으로 판정한다 — "높음 (… 확실히 …)" 처럼 설명 문구에 다른 등급 단어가 섞여도 오인하지 않게.
            "confidence": next((c for c in ("확실", "높음", "추정")
                                if re.match(rf"^\s*\*{{0,2}}{c}", fields.get("확신도", ""))), "") or
                          next((c for c in ("확실", "높음", "추정") if c in fields.get("확신도", "")), ""),
            "cwe": CWE.findall(fields.get("분류", "")),
            # "A05:2025 (구 A03:2021)" 처럼 병기된 경우 최신 판(2025) ID 만 남긴다
            "owasp": [o for o in OWASP.findall(fields.get("분류", "")) if o.endswith(":2025")]
                     or OWASP.findall(fields.get("분류", "")),
            "locations": parse_locations(fields.get("위치", "")),
            "source": fields.get("탐지 출처", ""),
            "cvss_score": float(score_m.group(1)) if score_m else None,
            "cvss_vector": vec_m.group(0) if vec_m else None,
            "description": " ".join(desc_m.group(1).split()) if desc_m else "",
        })
    return meta, findings


def to_sarif(meta, findings, report_path: Path):
    rules, results = {}, []
    for f in findings:
        rule_id = f["cwe"][0] if f["cwe"] else f["id"]
        rules.setdefault(rule_id, {
            "id": rule_id,
            "name": f["title"],
            "shortDescription": {"text": f["title"]},
            "helpUri": f"https://cwe.mitre.org/data/definitions/{rule_id.split('-')[1]}.html" if f["cwe"] else None,
            "properties": {"security-severity": SARIF_SEC_SEVERITY.get(f["severity"], "5.0"),
                           "tags": ["security"] + f["cwe"] + f["owasp"]},
        })
        locations = [{
            "physicalLocation": {
                "artifactLocation": {"uri": loc["file"]},
                **({"region": {"startLine": loc["start_line"], "endLine": loc["end_line"]}} if loc["start_line"] else {}),
            }
        } for loc in f["locations"]] or [{"physicalLocation": {"artifactLocation": {"uri": "."}}}]
        results.append({
            "ruleId": rule_id,
            "level": SARIF_LEVEL.get(f["severity"], "warning"),
            "message": {"text": f"[{f['id']}] {f['title']}" + (f"\n\n{f['description']}" if f["description"] else "")},
            "locations": locations,
            "partialFingerprints": {"auditorFindingId/v1": f["id"]},
            "properties": {"severity": f["severity"], "confidence": f["confidence"],
                           "cvss_score": f["cvss_score"], "cvss_vector": f["cvss_vector"], "source": f["source"]},
        })
    for r in rules.values():
        if r["helpUri"] is None:
            del r["helpUri"]
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": "code-security-auditor", "informationUri": "https://github.com/",
                                "rules": list(rules.values())}},
            "invocations": [{"executionSuccessful": True,
                             "properties": {"mode": meta.get("분석 모드"), "tools": meta.get("분석 도구"),
                                            "analyzed_at_kst": meta.get("분석 일시(KST)"),
                                            "report": report_path.name}}],
            "results": results,
        }],
    }


def main():
    args = sys.argv[1:]
    paths = [a for a in args if not a.startswith("--")]
    if not paths:
        sys.exit("사용법: python tools/export_findings.py <레포트.md> [--sarif]")
    md_path = Path(paths[0])
    if not md_path.is_file():
        sys.exit(f"[export_findings] 파일을 찾을 수 없습니다: {md_path}")

    meta, findings = parse_report(md_path.read_text(encoding="utf-8"))
    if not findings:
        sys.exit("[export_findings] 발견 항목(### [F-NNN] ...)을 찾지 못했습니다. 템플릿 형식을 확인하세요.")

    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITIES}
    payload = {
        "report": md_path.name,
        "generated_at": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST"),
        "meta": meta,
        "summary": {"total": len(findings), **counts},
        "findings": findings,
    }
    base = md_path.with_suffix("")
    json_path = Path(str(base) + ".findings.json")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[export_findings] JSON 생성: {json_path.as_posix()}  ({len(findings)}건: "
          + ", ".join(f"{s} {n}" for s, n in counts.items() if n) + ")")

    unparsed = [f["id"] for f in findings if not f["severity"] or not f["locations"]]
    if unparsed:
        print(f"[export_findings] 경고: 심각도 또는 위치를 읽지 못한 항목: {', '.join(unparsed)} — 템플릿 필드 형식을 확인하세요.")

    if "--sarif" in args:
        sarif_path = Path(str(base) + ".sarif")
        sarif_path.write_text(json.dumps(to_sarif(meta, findings, md_path), ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[export_findings] SARIF 생성: {sarif_path.as_posix()}")


if __name__ == "__main__":
    main()
