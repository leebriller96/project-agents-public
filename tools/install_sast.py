#!/usr/bin/env python3
"""6단계 SAST 도구 설치·확인 - semgrep · gitleaks · osv-scanner.

external/code-security-auditor/tools/run_sast.py 가 부르는 도구를 6단계 전에 미리 설치한다.
도구는 이 PC 에만 설치되고 target_dir·이 저장소에는 아무것도 더하지 않는다(결과는 reports/.sast/ 에만 남는다).

  python tools/install_sast.py --check          # 설치 여부·버전만 본다(네트워크 없음)
  python tools/install_sast.py                  # 없는 도구만 설치
  python tools/install_sast.py --force          # 다시 설치(최신 릴리스로 교체)
  python tools/install_sast.py --bin-dir <경로>  # 실행 파일 위치(기본 ~/.local/bin - PATH 에 있어야 한다)

설치 방법
  semgrep      : python -m pip install --user semgrep (Windows 네이티브 1.177 동작 확인, stage6-security §2)
  gitleaks     : GitHub 릴리스(gitleaks/gitleaks) 의 OS·CPU 에 맞는 압축 파일을 받아 실행 파일만 꺼낸다
  osv-scanner  : GitHub 릴리스(google/osv-scanner) 의 OS·CPU 에 맞는 단일 실행 파일을 받는다
받은 파일은 임시 폴더에서만 풀고, 실행 파일 하나만 bin 폴더로 옮긴다(압축 안 다른 파일은 실행하지 않는다).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

GITHUB_API = "https://api.github.com/repos/{repo}/releases/latest"
UA = {"User-Agent": "project-agents-install-sast", "Accept": "application/vnd.github+json"}


def _os_arch() -> tuple[str, str]:
    """릴리스 파일 이름에 쓰이는 OS·CPU 표기."""
    osname = {"Windows": "windows", "Darwin": "darwin", "Linux": "linux"}.get(platform.system(), "linux")
    mach = platform.machine().lower()
    arch = "arm64" if mach in ("arm64", "aarch64") else "amd64"
    return osname, arch


def _exe(name: str) -> str:
    return name + (".exe" if platform.system() == "Windows" else "")


def _version(cmd: list[str]) -> str | None:
    """도구가 PATH 에 있으면 버전 첫 줄, 없으면 None."""
    exe = shutil.which(cmd[0])
    if not exe:
        return None
    try:
        p = subprocess.run([exe] + cmd[1:], capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
        out = (p.stdout or p.stderr).strip().splitlines()
        return out[0] if out else "버전 확인 실패"
    except Exception as e:  # noqa: BLE001 - 확인용
        return f"실행 실패: {e}"


SEMGREP_IMAGE = os.environ.get("SEMGREP_IMAGE", "semgrep/semgrep:latest")


def _semgrep_version() -> str | None:
    """PC 에서 바로 돌면 그 버전, 정책 등으로 막히면 Docker 이미지 버전(run_sast.py 가 같은 순서로 고른다)."""
    v = _version(["semgrep", "--version"])
    if v and v[:1].isdigit():
        return v
    if shutil.which("docker"):
        dv = _version(["docker", "run", "--rm", SEMGREP_IMAGE, "semgrep", "--version"])
        if dv and dv[:1].isdigit():
            return f"{dv} (docker {SEMGREP_IMAGE} - PC 에서는 실행 불가)"
    return None


def install_semgrep_docker() -> None:
    """애플리케이션 제어 정책이 pip 판 semgrep 을 막는 PC 용 - 보안 정책은 바꾸지 않고 이미지를 받는다."""
    if not shutil.which("docker"):
        print("[install_sast] semgrep 이 PC 에서 실행되지 않고 docker 도 없다 - WSL 또는 Docker 설치를 권한다(stage6-security §2)")
        return
    subprocess.run(["docker", "pull", SEMGREP_IMAGE], check=True)


def check() -> dict[str, str | None]:
    return {
        "semgrep": _semgrep_version(),
        "gitleaks": _version(["gitleaks", "version"]),
        "osv-scanner": _version(["osv-scanner", "--version"]),
    }


def _latest_asset(repo: str, want) -> tuple[str, str]:
    """최신 릴리스에서 조건에 맞는 첫 파일의 (이름, 내려받기 주소)."""
    req = urllib.request.Request(GITHUB_API.format(repo=repo), headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        rel = json.load(r)
    for a in rel.get("assets", []):
        if want(a["name"].lower()):
            return a["name"], a["browser_download_url"]
    raise RuntimeError(f"{repo} 최신 릴리스({rel.get('tag_name')})에서 맞는 파일을 찾지 못했다")


def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def install_semgrep(bin_dir: Path) -> None:
    subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--upgrade", "semgrep"], check=True)
    if shutil.which("semgrep"):
        return
    # pip --user 의 Scripts 폴더는 PATH 에 없는 경우가 많다(stage6-security §2) - 시스템 PATH 를 바꾸지 않고
    # bin 폴더에 그 실행 파일을 부르는 연결 파일(Windows .cmd, 그 밖은 셸 스크립트)을 둔다.
    import sysconfig
    scheme = "nt_user" if os.name == "nt" else "posix_user"
    exe = Path(sysconfig.get_path("scripts", scheme)) / _exe("semgrep")
    if not exe.exists():
        print(f"[install_sast] 주의: semgrep 실행 파일을 찾지 못했다({exe})")
        return
    if os.name == "nt":
        (bin_dir / "semgrep.cmd").write_text(f'@"{exe}" %*\r\n', encoding="ascii")
    else:
        shim = bin_dir / "semgrep"
        shim.write_text(f'#!/bin/sh\nexec "{exe}" "$@"\n', encoding="utf-8")
        os.chmod(shim, 0o755)
    print(f"[install_sast] semgrep 연결 파일을 {bin_dir} 에 두었다 -> {exe}")


def install_gitleaks(bin_dir: Path) -> None:
    osname, arch = _os_arch()
    arch_tag = "x64" if arch == "amd64" else "arm64"
    name, url = _latest_asset("gitleaks/gitleaks",
                              lambda n: f"_{osname}_{arch_tag}." in n and (n.endswith(".zip") or n.endswith(".tar.gz")))
    print(f"[install_sast] gitleaks 받기: {name}")
    data = _download(url)
    target = _exe("gitleaks")
    with tempfile.TemporaryDirectory() as tmp:
        if name.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                member = next(m for m in z.namelist() if Path(m).name == target)
                z.extract(member, tmp)
        else:
            with tarfile.open(fileobj=io.BytesIO(data)) as t:
                member = next(m for m in t.getnames() if Path(m).name == target)
                t.extract(member, tmp, filter="data")
        shutil.copy2(Path(tmp) / member, bin_dir / target)
    os.chmod(bin_dir / target, 0o755)


def install_osv(bin_dir: Path) -> None:
    osname, arch = _os_arch()
    suffix = f"_{osname}_{arch}" + (".exe" if osname == "windows" else "")
    name, url = _latest_asset("google/osv-scanner", lambda n: n.startswith("osv-scanner") and n.endswith(suffix))
    print(f"[install_sast] osv-scanner 받기: {name}")
    (bin_dir / _exe("osv-scanner")).write_bytes(_download(url))
    os.chmod(bin_dir / _exe("osv-scanner"), 0o755)


def main() -> int:
    ap = argparse.ArgumentParser(description="6단계 SAST 도구(semgrep·gitleaks·osv-scanner) 설치·확인")
    ap.add_argument("--check", action="store_true", help="설치 여부만 확인")
    ap.add_argument("--force", action="store_true", help="이미 있어도 다시 설치")
    ap.add_argument("--bin-dir", default=str(Path.home() / ".local" / "bin"), help="gitleaks·osv-scanner 실행 파일 위치")
    a = ap.parse_args()

    before = check()
    if not a.check:
        bin_dir = Path(a.bin_dir).expanduser()
        bin_dir.mkdir(parents=True, exist_ok=True)
        steps = {"semgrep": lambda: install_semgrep(bin_dir), "gitleaks": lambda: install_gitleaks(bin_dir), "osv-scanner": lambda: install_osv(bin_dir)}
        for tool, fn in steps.items():
            if before[tool] and not a.force:
                continue
            try:
                fn()
            except Exception as e:  # noqa: BLE001 - 도구별로 계속 진행
                print(f"[install_sast] {tool} 설치 실패: {e}")
        if not _semgrep_version():
            try:
                install_semgrep_docker()
            except Exception as e:  # noqa: BLE001
                print(f"[install_sast] semgrep docker 이미지 받기 실패: {e}")
        if str(bin_dir) not in os.environ.get("PATH", "").split(os.pathsep):
            print(f"[install_sast] 주의: {bin_dir} 가 PATH 에 없다 - 더해야 run_sast.py 가 찾는다")
    result = check()
    for tool, v in result.items():
        print(f"  {tool:12s} {v or '미설치'}")
    return 0 if all(result.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
