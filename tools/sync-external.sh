#!/usr/bin/env bash
# sync-external.sh — external/ 아래 subtree 로 편입된 도구 repo 를 upstream 최신으로 갱신한다.
#   bash tools/sync-external.sh            # 둘 다
#   bash tools/sync-external.sh qa         # qa-automation 만
#   bash tools/sync-external.sh security   # code-security-auditor 만
# 실행 전 작업 트리가 clean 해야 한다 (git subtree pull 은 merge 커밋을 만든다).
set -euo pipefail
cd "$(dirname "$0")/.."
sync() {
  local prefix="$1" url="$2"
  echo "[sync-external] $prefix <- $url"
  git subtree pull --prefix="$prefix" "$url" main --squash -m "external: $prefix 갱신"
}
target="${1:-all}"
[[ "$target" == all || "$target" == qa ]]       && sync external/qa-automation https://github.com/leebriller96/qa-automation.git
[[ "$target" == all || "$target" == security ]] && sync external/code-security-auditor https://github.com/leebriller96/code-security-auditor.git
echo "[sync-external] 완료. 도구의 경로·모드·등급 체계가 바뀌었는지 .claude/skills/stage6-security, stage7-qa 와 대조하세요."
