#!/usr/bin/env python3
# run_sast.py — 대상 경로의 언어를 감지해 설치된 SAST 도구를 실행하고 결과를 JSON으로 모은다.
#
# 사용법:
#   python tools/run_sast.py [대상경로]        # 기본값: input
#
# 출력:
#   reports/.sast/<도구>.json   각 도구의 원본 결과
#   reports/.sast/<도구>.log    각 도구의 stderr (실패 원인 확인용)
#   reports/.sast/summary.json  도구별 실행 상태/발견 건수 요약
#   stdout                      사람이 읽을 요약 표
#
# 종료 코드: 0 = 하나 이상 실행됨, 2 = 실행 가능한 도구가 없음 (claude-only 모드로 진행)
#
# 원칙:
#   - 분석 대상 코드는 신뢰하지 않는다. 대상 코드를 실행하거나 의존성을 설치/빌드하는 동작은 하지 않는다.
#     (pip-audit 는 --no-deps --disable-pip 로 의존성 해석을 끈다. npm audit 는 lifecycle 스크립트를 실행하지 않는다.)
#   - 매 실행 전 출력 디렉토리를 비워 이전 스캔 결과가 섞이지 않게 한다.
#   - 도구가 실패해도 조용히 넘어가지 않고 상태/사유를 남긴다.
#   - Java/Kotlin 의존성은 osv-scanner 로 감사한다 (pom.xml 등). pip-audit/npm 이 없을 때의 대체 수단이기도 하다.

import json
import os
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

# 윈도우 콘솔(cp949)에서 한글 출력이 깨지지 않도록 UTF-8로 고정한다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "reports" / ".sast"

# 분석 가치가 없고 노이즈만 만드는 디렉토리 (의존성, 빌드 산출물, VCS 메타데이터)
EXCLUDE_DIRS = [
    "node_modules", ".venv", "venv", ".git", "dist", "build", "vendor",
    "__pycache__", ".tox", ".mypy_cache", ".pytest_cache", "target", ".idea", ".vscode",
]
TOOL_TIMEOUT_SEC = 900

# 파이썬 기반 도구(bandit, pip-audit, semgrep)가 한글 주석이 든 파일을 로케일 인코딩(cp949)으로 읽다
# 실패하지 않도록 자식 프로세스를 UTF-8 모드로 실행한다.
CHILD_ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}

results = []  # 도구별 실행 결과 레코드


def record(tool, status, *, reason="", output=None, findings=None, extra=None):
    row = {"tool": tool, "status": status, "reason": reason,
           "output": output.relative_to(REPO_ROOT).as_posix() if output else None,
           "findings": findings}
    if extra:
        row.update(extra)
    results.append(row)
    return row


def have(cmd):
    return shutil.which(cmd)


def is_excluded(path: Path) -> bool:
    return any(part in EXCLUDE_DIRS for part in path.parts)


def find_files(target: Path, pattern: str):
    return [p for p in target.rglob(pattern) if not is_excluded(p.relative_to(target))]


def run(cmd, log_path: Path, cwd=None):
    """도구를 실행하고 (returncode, stdout) 을 돌려준다. stderr 는 로그 파일로 남긴다."""
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, env=CHILD_ENV, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=TOOL_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        log_path.write_text(f"TIMEOUT ({TOOL_TIMEOUT_SEC}s): {' '.join(map(str, cmd))}\n", encoding="utf-8")
        return None, ""
    except OSError as exc:
        log_path.write_text(f"실행 실패: {exc}\n명령: {' '.join(map(str, cmd))}\n", encoding="utf-8")
        return None, ""
    log_path.write_text(
        f"$ {' '.join(map(str, cmd))}\n[exit={proc.returncode}]\n{proc.stderr}", encoding="utf-8"
    )
    return proc.returncode, proc.stdout


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_json_stdout(stdout: str, path: Path):
    """stdout 이 유효한 JSON 이면 파일로 저장하고 파싱 결과를 돌려준다."""
    try:
        data = json.loads(stdout)
    except Exception:
        return None
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


# ---------------------------------------------------------------- 도구별 실행

def run_semgrep(target: Path):
    tool = "semgrep"
    if not have("semgrep"):
        return record(tool, "미설치", reason="설치: pip install semgrep (윈도우 네이티브 동작 확인: 1.177)")
    print(f"[run_sast] Semgrep 실행 중... (룰셋을 네트워크에서 받으므로 시간이 걸릴 수 있음)")
    out, log = OUT_DIR / "semgrep.json", OUT_DIR / "semgrep.log"
    # 기본 룰셋 3종. 세 샘플 앱 벤치(2026-09): p/secrets·p/jwt·p/cwe-top-25·p/xss 등은 추가 탐지 0건이라 제외,
    # p/default 는 CSRF 미들웨어·eval 등 +5건. 바꾸려면 SEMGREP_CONFIGS="p/a,p/b" (쉼표 구분).
    configs = [c.strip() for c in os.environ.get("SEMGREP_CONFIGS", "p/security-audit,p/owasp-top-ten,p/default").split(",") if c.strip()]
    cmd = ["semgrep", "--json", "--quiet", "--metrics=off"]
    for c in configs:
        cmd += ["--config", c]
    for d in EXCLUDE_DIRS:
        cmd += ["--exclude", d]
    cmd.append(str(target))
    rc, stdout = run(cmd, log)
    data = save_json_stdout(stdout, out) if stdout else None
    if data is None:
        hint = "존재하지 않는 룰셋 이름 또는 네트워크 오류 가능"
        return record(tool, "실패", reason=f"JSON 결과 없음 (exit={rc}). {log.name} 확인 ({hint})")
    n = len(data.get("results", []))
    errs = data.get("errors", [])
    # 룰셋 로딩 실패는 결과가 0건으로 조용히 끝나므로 오류 목록에서 골라내 명시한다.
    cfg_errs = [e for e in errs if "configuration" in str(e.get("message", "")).lower()
                or "config" in str(e.get("type", "")).lower()]
    if cfg_errs:
        msg = str(cfg_errs[0].get("message") or cfg_errs[0].get("long_msg") or cfg_errs[0])[:150]
        return record(tool, "실패", reason=f"룰셋 오류: {msg}")
    return record(tool, "실행", output=out, findings=n, extra={"configs": configs},
                  reason=f"내부 오류 {len(errs)}건 (파싱 실패 파일 등)" if errs else "")


def run_bandit(target: Path):
    tool = "bandit"
    if not find_files(target, "*.py"):
        return record(tool, "건너뜀", reason="Python 파일 없음")
    if not have("bandit"):
        return record(tool, "미설치", reason="설치: pip install bandit")
    print("[run_sast] Bandit(Python) 실행 중...")
    out, log = OUT_DIR / "bandit.json", OUT_DIR / "bandit.log"
    exclude = ",".join(f"*/{d}/*" for d in EXCLUDE_DIRS)
    cmd = ["bandit", "-r", str(target), "-f", "json", "-o", str(out), "-q", "-x", exclude]
    rc, _ = run(cmd, log)
    data = load_json(out) if out.exists() else None
    if data is None:
        return record(tool, "실패", reason=f"JSON 결과 없음 (exit={rc}). {log.name} 확인")
    return record(tool, "실행", output=out, findings=len(data.get("results", [])))


def run_gitleaks(target: Path):
    tool = "gitleaks"
    if not have("gitleaks"):
        return record(tool, "미설치", reason="설치: https://github.com/gitleaks/gitleaks/releases (zip 풀어 PATH 에 추가, 8.30 확인)")
    print("[run_sast] Gitleaks(비밀값) 실행 중...")
    out, log = OUT_DIR / "gitleaks.json", OUT_DIR / "gitleaks.log"
    common = ["--report-format", "json", "--report-path", str(out), "--exit-code", "0", "--no-banner"]
    # 8.19+ 는 `gitleaks dir`, 그 이전은 `detect --no-git`. 신형 명령을 먼저 시도한다.
    rc, _ = run(["gitleaks", "dir", str(target)] + common, log)
    if rc != 0 and "unknown command" in log.read_text(encoding="utf-8"):
        rc, _ = run(["gitleaks", "detect", "--no-git", "--source", str(target)] + common, log)
    if rc != 0:
        return record(tool, "실패", reason=f"exit={rc}. {log.name} 확인")
    data = load_json(out) if out.exists() else []
    if data is None:
        return record(tool, "실패", reason=f"결과 JSON 파싱 실패. {log.name} 확인")
    return record(tool, "실행", output=out, findings=len(data))


def run_pip_audit(target: Path):
    tool = "pip-audit"
    req_files = find_files(target, "requirements*.txt")
    if not req_files:
        return record(tool, "건너뜀", reason="requirements*.txt 없음")
    if not have("pip-audit"):
        return record(tool, "미설치", reason="설치: pip install pip-audit")
    for i, req in enumerate(req_files):
        rel = req.relative_to(target)
        print(f"[run_sast] pip-audit(의존성) 실행 중... {rel}")
        suffix = "" if i == 0 else f"_{i}"
        out, log = OUT_DIR / f"pip-audit{suffix}.json", OUT_DIR / f"pip-audit{suffix}.log"
        # --no-deps --disable-pip: 의존성 해석/빌드를 하지 않는다 (대상 코드의 setup.py 실행 방지).
        # 대신 버전이 == 로 고정되지 않은 항목이 있으면 도구가 거부한다.
        cmd = ["pip-audit", "-r", str(req), "-f", "json", "--no-deps", "--disable-pip",
               "--progress-spinner", "off"]
        rc, stdout = run(cmd, log)
        data = save_json_stdout(stdout, out) if stdout else None
        if data is not None and "dependencies" not in data:
            out.unlink(missing_ok=True)
            data = None
        if data is None:
            record(tool, "실패", extra={"file": str(rel)},
                   reason=f"exit={rc}. {log.name} 확인 (버전이 == 로 고정되지 않은 의존성은 감사 불가 — "
                          f"대상 코드 실행 방지를 위해 의존성 해석을 하지 않음)")
            continue
        n = sum(len(d.get("vulns", [])) for d in data.get("dependencies", []))
        record(tool, "실행", output=out, findings=n, extra={"file": str(rel)})


def run_npm_audit(target: Path):
    tool = "npm-audit"
    pkg_files = find_files(target, "package.json")
    if not pkg_files:
        return record(tool, "건너뜀", reason="package.json 없음")
    if not have("npm"):
        return record(tool, "미설치", reason="설치: https://nodejs.org")
    # pnpm 워크스페이스: 락파일은 워크스페이스 루트(pnpm-lock.yaml)에만 있고 하위 패키지에는 없다.
    # → 루트에서 `pnpm audit --json` 1회(워크스페이스 전체), 하위 패키지는 "루트에서 감사됨" 으로 표시.
    pnpm_roots = {lock.parent for lock in find_files(target, "pnpm-lock.yaml")}
    pnpm_cmd = have("pnpm") or (have("corepack") and [have("corepack"), "pnpm"])
    for i, pkg in enumerate(pkg_files):
        rel = pkg.relative_to(target)
        pkg_dir = pkg.parent
        covered = next((r for r in pnpm_roots if pkg_dir != r and r in pkg_dir.parents), None)
        if covered is not None:
            record(tool, "건너뜀", extra={"file": str(rel)},
                   reason=f"pnpm 워크스페이스 루트({covered.relative_to(target)}/pnpm-lock.yaml)에서 감사됨")
            continue
        if pkg_dir in pnpm_roots:
            if not pnpm_cmd:
                record(tool, "미설치", extra={"file": str(rel)}, reason="pnpm-lock.yaml 있으나 pnpm/corepack 없음")
                continue
            print(f"[run_sast] pnpm audit(의존성, 워크스페이스) 실행 중... {rel}")
            suffix = "" if i == 0 else f"_{i}"
            out, log = OUT_DIR / f"npm-audit{suffix}.json", OUT_DIR / f"npm-audit{suffix}.log"
            cmd = (pnpm_cmd if isinstance(pnpm_cmd, list) else [pnpm_cmd]) + ["audit", "--json"]
            rc, stdout = run(cmd, log, cwd=pkg_dir)
            data = save_json_stdout(stdout, out) if stdout else None
            if data is None:
                record(tool, "실패", extra={"file": str(rel)}, reason=f"exit={rc}. {log.name} 확인")
                continue
            # pnpm audit --json 은 npm v6 형식(advisories/metadata.vulnerabilities)
            advisories = data.get("advisories") or {}
            record(tool, "실행", output=out, findings=len(advisories),
                   extra={"file": str(rel), "runner": "pnpm audit"})
            continue
        if not any((pkg_dir / lock).exists() for lock in ("package-lock.json", "npm-shrinkwrap.json")):
            record(tool, "건너뜀", extra={"file": str(rel)},
                   reason="락파일(package-lock.json) 없음 — npm audit 는 락파일이 필요함")
            continue
        print(f"[run_sast] npm audit(의존성) 실행 중... {rel}")
        suffix = "" if i == 0 else f"_{i}"
        out, log = OUT_DIR / f"npm-audit{suffix}.json", OUT_DIR / f"npm-audit{suffix}.log"
        # npm audit 는 install 과 달리 lifecycle 스크립트를 실행하지 않는다.
        rc, stdout = run([have("npm"), "audit", "--json", "--ignore-scripts"], log, cwd=pkg_dir)
        data = save_json_stdout(stdout, out) if stdout else None
        if data is None:
            record(tool, "실패", extra={"file": str(rel)}, reason=f"exit={rc}. {log.name} 확인")
            continue
        # 레지스트리 오류(503 등)도 JSON 으로 오므로 결과 스키마를 확인한다.
        if "vulnerabilities" not in data:
            msg = str(data.get("message") or data.get("error") or "결과 스키마 불일치")[:120]
            out.unlink(missing_ok=True)
            record(tool, "실패", extra={"file": str(rel)}, reason=f"npm 레지스트리/감사 오류: {msg}")
            continue
        record(tool, "실행", output=out, findings=len(data.get("vulnerabilities", {})),
               extra={"file": str(rel)})


def run_osv_scanner(target: Path):
    """Java/Kotlin 매니페스트 + (pip-audit/npm 미실행 시) Python/JS 락파일을 OSV 로 감사한다."""
    tool = "osv-scanner"
    java_files = []
    for pat in ("pom.xml", "build.gradle.lockfile", "gradle.lockfile", "gradle/verification-metadata.xml"):
        java_files += find_files(target, pat)
    # pip-audit / npm audit 가 "실행" 되지 못한 매니페스트는 osv-scanner 로 대체한다.
    ran_tools = {r["tool"] for r in results if r["status"] == "실행"}
    fallback = []
    if "pip-audit" not in ran_tools:
        fallback += find_files(target, "requirements*.txt") + find_files(target, "poetry.lock") + find_files(target, "Pipfile.lock")
    if "npm-audit" not in ran_tools:
        fallback += find_files(target, "package-lock.json") + find_files(target, "yarn.lock") + find_files(target, "pnpm-lock.yaml")
    files = java_files + fallback
    if not files:
        return record(tool, "건너뜀", reason="Java 매니페스트(pom.xml 등) 없음, 다른 언어는 전용 도구가 처리")
    if not have("osv-scanner"):
        return record(tool, "미설치", reason="설치: https://github.com/google/osv-scanner/releases (단일 실행파일, PATH 에 추가)")
    # 전이 의존성 해석은 매니페스트에 적힌 저장소로 네트워크 요청을 보내므로 기본은 끈다 (--no-resolve).
    # 신뢰할 수 있는 대상이면 OSV_RESOLVE=1 로 켤 수 있다.
    resolve = os.environ.get("OSV_RESOLVE") == "1"
    for i, f in enumerate(files):
        rel = f.relative_to(target)
        print(f"[run_sast] osv-scanner(의존성) 실행 중... {rel}" + (" (전이 해석 켜짐)" if resolve else ""))
        suffix = "" if i == 0 else f"_{i}"
        out, log = OUT_DIR / f"osv-scanner{suffix}.json", OUT_DIR / f"osv-scanner{suffix}.log"
        cmd = ["osv-scanner", "scan", "source", "--format", "json", "--allow-no-lockfiles"]
        if not resolve:
            cmd.append("--no-resolve")
        cmd += ["-L", str(f)]
        rc, stdout = run(cmd, log)
        data = save_json_stdout(stdout, out) if stdout else None
        # 종료 코드: 0 = 취약점 없음, 1 = 취약점 있음, 그 외 = 오류
        if data is None or rc not in (0, 1):
            record(tool, "실패", extra={"file": rel.as_posix()}, reason=f"exit={rc}. {log.name} 확인")
            continue
        n = sum(len(pk.get("vulnerabilities", [])) for r in data.get("results", []) for pk in r.get("packages", []))
        record(tool, "실행", output=out, findings=n, extra={"file": rel.as_posix()},
               reason="" if resolve else "직접 의존성만 (전이 해석은 OSV_RESOLVE=1)")


# ---------------------------------------------------------------- 메인

def print_summary():
    print("\n[run_sast] 결과 요약")
    print(f"  {'도구':<11}{'상태':<7}{'발견':>5}  비고")
    for r in results:
        n = "-" if r["findings"] is None else str(r["findings"])
        note = r["output"] or ""
        if r.get("file"):
            note = f"{note} ({r['file']})".strip()
        if r["reason"]:
            note = f"{note} · {r['reason']}".strip(" ·")
        print(f"  {r['tool']:<11}{r['status']:<7}{n:>5}  {note}")


def main():
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "input").resolve()
    if not target.is_dir():
        sys.exit(f"[run_sast] 대상 디렉토리를 찾을 수 없습니다: {target}")

    # 이전 스캔 결과가 섞이지 않도록 출력 디렉토리를 비운다.
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)

    print(f"[run_sast] 대상: {target}")
    print(f"[run_sast] 출력: {OUT_DIR.relative_to(REPO_ROOT).as_posix()}")

    run_semgrep(target)
    run_bandit(target)
    run_gitleaks(target)
    run_pip_audit(target)
    run_npm_audit(target)
    run_osv_scanner(target)

    (OUT_DIR / "summary.json").write_text(
        json.dumps({"target": str(target), "results": results}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print_summary()

    ran = [r for r in results if r["status"] == "실행"]
    if not ran:
        print("\n[run_sast] 실행 가능한 SAST 도구가 없습니다. claude-only 모드로 분석을 진행하세요.")
        sys.exit(2)
    print(f"\n[run_sast] 완료. 도구별 stderr 는 {OUT_DIR.relative_to(REPO_ROOT).as_posix()}/<도구>.log 참고")


if __name__ == "__main__":
    main()
