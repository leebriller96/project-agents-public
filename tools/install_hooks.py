#!/usr/bin/env python3
# install_hooks.py — 이 저장소의 git 훅(pre-commit)을 설치한다
#
# 설치 위치: `git rev-parse --git-path hooks/pre-commit` (core.hooksPath·작업 트리를 따른다. 보통 .git/hooks/pre-commit)
# 설치 내용: 저장소가 추적하는 tools/hooks/pre-commit 을 부르는 작은 훅. 원본이 바뀌어도 다시 설치할 필요가 없다.
#
# 다시 실행해도 결과가 같다 - 이미 같은 내용이면 손대지 않는다. 이 도구가 설치한 훅(표지 줄로 구분)만 갱신하고,
# 다른 훅이 이미 있으면 덮어쓰지 않고 알린다(종료 코드 1). 그 훅에서 tools/hooks/pre-commit 을 부르도록 사람이 합친다.
#
# 사용법: python tools/install_hooks.py [--check]
#   --check  설치하지 않고 상태만 본다 (0 설치됨 · 1 없음·다른 훅 · selfcheck 가 쓴다)
# 종료 코드: 0 설치됨(또는 이미 설치됨) · 1 다른 훅이 있어 설치하지 않음·설치 안 됨(--check) · 2 git 저장소 아님

import argparse
import os
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

MARKER = "# project-agents pre-commit (tools/install_hooks.py 가 설치)"
STUB = f"""#!/bin/sh
{MARKER}
# 저장소가 추적하는 원본(tools/hooks/pre-commit)을 부른다. 지우거나 바꾸려면 python tools/install_hooks.py 를 다시 본다.
ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
[ -f "$ROOT/tools/hooks/pre-commit" ] || exit 0
exec sh "$ROOT/tools/hooks/pre-commit" "$@"
"""


def hook_path(cwd):
    p = subprocess.run(["git", "rev-parse", "--git-path", "hooks/pre-commit"], cwd=cwd,
                       capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        return None
    path = p.stdout.strip()
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(cwd, path))


def repo_root(cwd):
    p = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd,
                       capture_output=True, text=True, encoding="utf-8")
    return p.stdout.strip() if p.returncode == 0 else None


def status(path):
    """'installed' · 'outdated'(이 도구가 설치했지만 내용이 다름) · 'foreign'(다른 훅) · 'missing'."""
    if not os.path.exists(path):
        return "missing"
    try:
        with open(path, encoding="utf-8", errors="replace", newline="") as fh:
            text = fh.read()
    except OSError:
        return "foreign"
    if MARKER not in text:
        return "foreign"
    return "installed" if text.replace("\r\n", "\n") == STUB else "outdated"


def main(argv=None):
    ap = argparse.ArgumentParser(description="git pre-commit 훅 설치")
    ap.add_argument("--check", action="store_true", help="설치하지 않고 상태만 본다")
    ap.add_argument("--repo", default=None, help="대상 저장소 (기본: 이 도구가 있는 저장소)")
    args = ap.parse_args(argv)
    cwd = args.repo or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root = repo_root(cwd)
    path = hook_path(cwd) if root else None
    if not path:
        print(f"[install_hooks] git 저장소가 아니다: {cwd}", file=sys.stderr)
        return 2
    st = status(path)
    if args.check:
        msg = {"installed": "설치됨", "outdated": "설치됐으나 옛 내용 - python tools/install_hooks.py 로 갱신",
               "foreign": "다른 pre-commit 훅이 있다 - tools/hooks/pre-commit 을 부르는지 사람이 확인",
               "missing": "설치 안 됨 - python tools/install_hooks.py"}[st]
        print(f"pre-commit 훅: {msg} ({path})")
        return 0 if st == "installed" else 1
    if st == "installed":
        print(f"pre-commit 훅: 이미 설치됨 - 바꾸지 않았다 ({path})")
        return 0
    if st == "foreign":
        print(f"pre-commit 훅: 다른 훅이 이미 있어 덮어쓰지 않았다 ({path}).\n"
              "그 훅 안에서 다음 줄로 이 저장소의 검사를 부르도록 합친다:\n"
              '  sh "$(git rev-parse --show-toplevel)/tools/hooks/pre-commit" || exit 1', file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(STUB)
    try:
        os.chmod(path, 0o755)
    except OSError:
        pass
    print(f"pre-commit 훅: {'갱신' if st == 'outdated' else '설치'}했다 ({path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
