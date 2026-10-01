#!/usr/bin/env python3
# summarize_sast.py — run_sast.py 가 모은 도구별 JSON(semgrep/bandit/gitleaks/pip-audit/npm-audit/osv-scanner,
# 스키마가 제각각)을 하나의 컴팩트한 표로 정규화한다.
#
# 사용법:
#   python tools/summarize_sast.py                 # reports/.sast/ 를 읽어 Markdown 표를 stdout 에 출력
#   python tools/summarize_sast.py --full          # 메시지를 자르지 않고 전부 출력
#   python tools/summarize_sast.py --max 80        # 상위 N건만 출력 (심각도 순)
#   python tools/summarize_sast.py --show-suppressed  # .auditignore 로 억제된 항목도 표에 표시
#
# 출력:
#   stdout                         도구별/심각도별 집계 + 항목 표 (Claude 가 읽기 위한 형식)
#   reports/.sast/normalized.json  정규화된 전체 항목 (도구, 룰, 심각도, 파일, 라인, 메시지, CWE, 억제 사유)
#
# .auditignore: 이미 검토해 제외한 항목이 재스캔 때 반복 보고되지 않도록 억제한다.
#   <대상경로>/.auditignore 와 repo 루트 .auditignore 를 모두 읽는다. 형식은 templates/auditignore.example 참고.
#
# 왜 필요한가: Semgrep JSON 은 수 MB 가 되기도 하고 도구마다 필드명이 달라, 원본을 그대로 읽으면
# 컨텍스트를 낭비하고 누락이 생긴다. 여기서 (도구, 룰, 심각도, 파일:라인, 메시지) 로 통일한다.
#
# 원칙: 비밀값 탐지 결과의 실제 시크릿 문자열은 출력에 포함하지 않는다.
#   gitleaks 는 Secret/Match 필드를 버리고, bandit B105 등 메시지에 인용된 값은 앞 4자만 남기고 마스킹한다.

import fnmatch
import json
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
SAST_DIR = REPO_ROOT / "reports" / ".sast"

SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Info": 4, "미정": 5}
MSG_LIMIT = 140


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def rel(path_str: str, target: Path) -> str:
    # 도구가 절대경로로 보고한 파일을 대상 기준 상대경로로 바꾼다.
    try:
        p = Path(path_str)
        if p.is_absolute():
            return p.resolve().relative_to(target).as_posix()
        return p.as_posix()
    except Exception:
        return path_str.replace("\\", "/")


SECRET_RULE_HINT = re.compile(r"hardcoded|secret|password|credential|token|api[-_]?key", re.I)


def mask_secrets(message: str) -> str:
    # 비밀값 탐지 룰의 메시지에 인용된 값('...' 또는 "...")은 앞 4자만 남기고 마스킹한다.
    def _mask(m):
        q, val = m.group(1), m.group(2)
        return f"{q}{val[:4]}****{q}" if len(val) > 4 else f"{q}****{q}"
    return re.sub(r"""(['"])([^'"]{1,200})\1""", _mask, message)


def row(tool, rule, severity, file, line, message, cwe="", confidence=""):
    message = " ".join(str(message).split())
    if SECRET_RULE_HINT.search(rule):
        message = mask_secrets(message)
    return {"tool": tool, "rule": rule, "severity": severity, "file": file, "line": line,
            "message": message, "cwe": cwe, "confidence": confidence}


def cwe_str(value) -> str:
    # "CWE-89: ..." 형태의 문자열/리스트에서 CWE 번호만 뽑는다.
    if not value:
        return ""
    items = value if isinstance(value, list) else [value]
    out = []
    for v in items:
        s = str(v)
        if s.upper().startswith("CWE-"):
            s = s.split(":")[0].strip()
        out.append(s)
    return ", ".join(out)


# ---------------------------------------------------------------- 도구별 파서

def parse_semgrep(data, target):
    sev_map = {"ERROR": "High", "WARNING": "Medium", "INFO": "Low"}
    impact_map = {"HIGH": "High", "MEDIUM": "Medium", "LOW": "Low"}
    rows = []
    for r in data.get("results", []):
        extra = r.get("extra", {})
        meta = extra.get("metadata", {}) or {}
        impact = str(meta.get("impact", "")).upper()
        likelihood = str(meta.get("likelihood", "")).upper()
        if impact == "HIGH" and likelihood == "HIGH":
            sev = "Critical"
        else:
            sev = impact_map.get(impact) or sev_map.get(str(extra.get("severity", "")).upper(), "Medium")
        rule = r.get("check_id", "")
        rule_short = rule.split(".")[-1] if "." in rule else rule
        rows.append(row("semgrep", rule_short, sev, rel(r.get("path", ""), target),
                        r.get("start", {}).get("line"), extra.get("message", ""),
                        cwe_str(meta.get("cwe")), str(meta.get("confidence", "")).lower()))
    return rows


def parse_bandit(data, target):
    sev_map = {"HIGH": "High", "MEDIUM": "Medium", "LOW": "Low"}
    rows = []
    for r in data.get("results", []):
        cwe = r.get("issue_cwe", {}) or {}
        rows.append(row("bandit", f"{r.get('test_id', '')} {r.get('test_name', '')}".strip(),
                        sev_map.get(str(r.get("issue_severity", "")).upper(), "Medium"),
                        rel(r.get("filename", ""), target), r.get("line_number"),
                        r.get("issue_text", ""),
                        f"CWE-{cwe['id']}" if cwe.get("id") else "",
                        str(r.get("issue_confidence", "")).lower()))
    return rows


def parse_gitleaks(data, target):
    rows = []
    for r in data or []:
        # 시크릿 원문(Secret/Match)은 절대 포함하지 않는다.
        rows.append(row("gitleaks", r.get("RuleID", ""), "High", rel(r.get("File", ""), target),
                        r.get("StartLine"), f"{r.get('Description', '')} (시크릿 원문은 마스킹됨)", "CWE-798"))
    return rows


def parse_pip_audit(data, target, source_file):
    rows = []
    for dep in data.get("dependencies", []):
        seen = set()
        for v in dep.get("vulns", []):
            # OSV 가 같은 취약점을 PYSEC/GHSA 레코드로 각각 돌려주므로 CVE 별칭 기준으로 중복을 합친다.
            ids = [v.get("id", "")] + list(v.get("aliases", []))
            key = next((i for i in ids if i.startswith("CVE-")), ids[0])
            if key in seen:
                continue
            seen.add(key)
            fix = ", ".join(v.get("fix_versions", [])) or "없음"
            aliases = ", ".join(v.get("aliases", [])[:2])
            ident = v.get("id", "")
            if aliases:
                ident = f"{ident} ({aliases})"
            rows.append(row("pip-audit", ident, "미정", source_file, None,
                            f"{dep.get('name')}=={dep.get('version')} · 수정 버전: {fix} · {v.get('description', '')}",
                            "CWE-1395"))
    return rows


def parse_npm_audit(data, target, source_file):
    sev_map = {"critical": "Critical", "high": "High", "moderate": "Medium", "low": "Low", "info": "Info"}
    rows = []
    for name, v in (data.get("vulnerabilities") or {}).items():
        titles, cwes = [], []
        for via in v.get("via", []):
            if isinstance(via, dict):
                titles.append(via.get("title", ""))
                cwes.extend(via.get("cwe", []) or [])
            else:
                titles.append(f"{via} 를 통해 전이")
        fix = v.get("fixAvailable")
        fix_txt = "수정 가능" if fix else "수정 불가"
        if isinstance(fix, dict):
            fix_txt = f"수정: {fix.get('name')}@{fix.get('version')}"
        rows.append(row("npm-audit", name, sev_map.get(str(v.get("severity", "")).lower(), "미정"),
                        source_file, None,
                        f"{name}@{v.get('range', '')} · {fix_txt} · {'; '.join(t for t in titles if t)}",
                        cwe_str(sorted(set(cwes)))))
    # npm v6 / pnpm audit 형식: advisories{id: {module_name, severity, title, cwe, vulnerable_versions, patched_versions, findings[{version, paths, dev}]}}
    for _id, adv in (data.get("advisories") or {}).items():
        name = adv.get("module_name", "")
        versions = sorted({f.get("version", "") for f in adv.get("findings", []) if f.get("version")})
        dev = all(f.get("dev") for f in adv.get("findings", [])) if adv.get("findings") else False
        cwe = adv.get("cwe") or []
        if isinstance(cwe, str):
            cwe = [cwe]
        rows.append(row("npm-audit", name, sev_map.get(str(adv.get("severity", "")).lower(), "미정"),
                        source_file, None,
                        f"{name}@{','.join(versions)} (취약 {adv.get('vulnerable_versions', '')}, 패치 {adv.get('patched_versions', '')})"
                        f"{' · devDependency' if dev else ''} · {adv.get('title', '')} · {adv.get('url', '')}",
                        cwe_str(sorted(set(cwe)))))
    return rows


def parse_osv(data, target, source_file):
    sev_map = {"CRITICAL": "Critical", "HIGH": "High", "MODERATE": "Medium", "MEDIUM": "Medium", "LOW": "Low"}
    rows = []
    for r in data.get("results", []):
        for pk in r.get("packages", []):
            name, ver = pk["package"].get("name", ""), pk["package"].get("version", "")
            seen = set()
            for v in pk.get("vulnerabilities", []):
                ids = [v.get("id", "")] + list(v.get("aliases", []))
                key = next((i for i in ids if i.startswith("CVE-")), ids[0])
                if key in seen:
                    continue
                seen.add(key)
                sev = sev_map.get(str((v.get("database_specific") or {}).get("severity", "")).upper(), "미정")
                fixed = sorted({e["fixed"] for a in v.get("affected", []) for rg in a.get("ranges", [])
                                for e in rg.get("events", []) if "fixed" in e})
                # 여러 메이저 브랜치의 수정 버전이 섞여 오므로 현재 버전과 같은 메이저를 우선 보여준다.
                major = ver.split(".")[0]
                same = [f for f in fixed if f.split(".")[0] == major]
                fixed = same or fixed
                cwes = cwe_str((v.get("database_specific") or {}).get("cwe_ids") or [])
                ident = v.get("id", "")
                if key != ident:
                    ident = f"{ident} ({key})"
                rows.append(row("osv-scanner", ident, sev, source_file, None,
                                f"{name}@{ver} · 수정 버전: {', '.join(fixed) or '없음'} · {v.get('summary', '')}",
                                cwes or "CWE-1395"))
    return rows


# ---------------------------------------------------------------- .auditignore

def load_auditignore(target: Path):
    """억제 규칙 목록을 돌려준다: (파일 glob, 라인 또는 None, 룰/CWE/*, 사유, 출처파일)"""
    rules = []
    for path in (target / ".auditignore", REPO_ROOT / ".auditignore"):
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line, _, comment = raw.partition("#")
            parts = line.split()
            if not parts:
                continue
            loc = parts[0]
            rule = parts[1] if len(parts) > 1 else "*"
            file_glob, _, line_no = loc.partition(":")
            rules.append((file_glob, int(line_no) if line_no.isdigit() else None,
                          rule, comment.strip(), path.name))
    return rules


def suppression_reason(row, rules):
    for file_glob, line_no, rule, reason, src in rules:
        if not fnmatch.fnmatch(row["file"], file_glob):
            continue
        if line_no is not None and row["line"] != line_no:
            continue
        if rule != "*":
            r = rule.upper()
            matched = (row["rule"].upper().startswith(r)
                       or (r.startswith("CWE-") and r in row["cwe"].upper()))
            if not matched:
                continue
        return f"{reason or '사유 미기재'} ({src})"
    return ""


# ---------------------------------------------------------------- 메인

def collect():
    summary = load(SAST_DIR / "summary.json")
    if not summary:
        sys.exit(f"[summarize_sast] {SAST_DIR.as_posix()}/summary.json 이 없습니다. "
                 "먼저 python tools/run_sast.py <대상경로> 를 실행하세요.")
    target = Path(summary["target"])
    rows = []
    for r in summary["results"]:
        if r["status"] != "실행" or not r.get("output"):
            continue
        data = load(REPO_ROOT / r["output"])
        if data is None:
            continue
        tool = r["tool"]
        if tool == "semgrep":
            rows += parse_semgrep(data, target)
        elif tool == "bandit":
            rows += parse_bandit(data, target)
        elif tool == "gitleaks":
            rows += parse_gitleaks(data, target)
        elif tool == "pip-audit":
            rows += parse_pip_audit(data, target, r.get("file", "requirements.txt"))
        elif tool == "npm-audit":
            rows += parse_npm_audit(data, target, r.get("file", "package.json"))
        elif tool == "osv-scanner":
            rows += parse_osv(data, target, r.get("file", "pom.xml"))
    rules = load_auditignore(target)
    for x in rows:
        x["suppressed"] = suppression_reason(x, rules) if rules else ""
    rows.sort(key=lambda x: (SEVERITY_ORDER.get(x["severity"], 9), x["file"], x["line"] or 0, x["tool"]))
    return summary, rows


def md_escape(s: str) -> str:
    return s.replace("|", "\\|")


def main():
    args = sys.argv[1:]
    full = "--full" in args
    show_suppressed = "--show-suppressed" in args
    max_rows = None
    if "--max" in args:
        try:
            max_rows = int(args[args.index("--max") + 1])
        except (IndexError, ValueError):
            sys.exit("사용법: python tools/summarize_sast.py [--full] [--max N] [--show-suppressed]")

    summary, rows = collect()
    (SAST_DIR / "normalized.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"## SAST 정규화 요약 — 총 {len(rows)}건")
    print(f"대상: `{summary['target']}`\n")

    print("**도구 실행 상태**")
    for r in summary["results"]:
        n = "" if r["findings"] is None else f" · {r['findings']}건"
        f = f" ({r['file']})" if r.get("file") else ""
        reason = f" · {r['reason']}" if r["reason"] else ""
        print(f"- {r['tool']}{f}: {r['status']}{n}{reason}")

    suppressed = [x for x in rows if x["suppressed"]]
    active = [x for x in rows if not x["suppressed"]]
    by_sev = {}
    for x in active:
        by_sev[x["severity"]] = by_sev.get(x["severity"], 0) + 1
    print("\n**심각도 분포(도구 보고 기준, 트리아지 전)**: "
          + ", ".join(f"{k} {by_sev[k]}" for k in sorted(by_sev, key=lambda s: SEVERITY_ORDER.get(s, 9))))
    if suppressed:
        print(f"**.auditignore 로 억제**: {len(suppressed)}건"
              + ("" if show_suppressed else " (표시하려면 --show-suppressed)"))

    listed = rows if show_suppressed else active
    shown = listed[:max_rows] if max_rows else listed
    print("\n| # | 심각도 | 도구 | 룰 | 위치 | CWE | 확신도 | 메시지 |")
    print("|---|--------|------|-----|------|-----|--------|--------|")
    for i, x in enumerate(shown, 1):
        loc = f"{x['file']}:{x['line']}" if x["line"] else x["file"]
        msg = x["message"] if full or len(x["message"]) <= MSG_LIMIT else x["message"][:MSG_LIMIT] + "…"
        if x["suppressed"]:
            msg = f"[억제: {x['suppressed']}] {msg}"
        print(f"| {i} | {x['severity']} | {x['tool']} | {md_escape(x['rule'])} | `{loc}` | "
              f"{x['cwe']} | {x['confidence']} | {md_escape(msg)} |")
    if max_rows and len(listed) > max_rows:
        print(f"\n… 외 {len(listed) - max_rows}건 (전체: reports/.sast/normalized.json)")
    print("\n> 위 심각도는 도구가 보고한 값입니다. 각 항목을 코드로 검증한 뒤 CLAUDE.md 기준으로 다시 산정하세요.")
    if suppressed:
        print("> 억제된 항목은 레포트 \"검토 제외\" 섹션에 `.auditignore` 사유와 함께 기록하세요.")


if __name__ == "__main__":
    main()
