#!/usr/bin/env bash
# snapshot.sh — commit the whole workspace so any accident is recoverable.
set -euo pipefail
WS="${1:-workspace}"
cd "$WS"
[ -d .git ] || git init -q -b snapshot
git add -A
git -c user.name=wiki-agent -c user.email=agent@localhost \
    commit -qm "snapshot: ${2:-$(date -u +%FT%TZ)}" || echo "nothing to snapshot"
git log --oneline -1
