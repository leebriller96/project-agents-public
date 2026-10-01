#!/usr/bin/env bash
# push-external.sh — external/ 아래 subtree 에서 고친 내용을 각 upstream repo 로 push 한다.
#   bash tools/push-external.sh qa         # external/qa-automation → leebriller96/qa-automation main
#   bash tools/push-external.sh security   # external/code-security-auditor → leebriller96/code-security-auditor main
#   bash tools/push-external.sh all
# 먼저 project-agents 에 커밋되어 있어야 한다(subtree push 는 커밋된 내용만 분리한다).
set -euo pipefail
cd "$(dirname "$0")/.."
push() {
  local prefix="$1" url="$2"
  echo "[push-external] $prefix -> $url (main)"
  git subtree push --prefix="$prefix" "$url" main
}
target="${1:-all}"
[[ "$target" == all || "$target" == qa ]]       && push external/qa-automation https://github.com/leebriller96/qa-automation.git
[[ "$target" == all || "$target" == security ]] && push external/code-security-auditor https://github.com/leebriller96/code-security-auditor.git
echo "[push-external] 완료."
