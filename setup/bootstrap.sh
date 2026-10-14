#!/usr/bin/env bash
# bootstrap.sh — bring a fresh sandbox up to a working state for repo→wiki work.
#
# Idempotent: safe to run twice. Prints a capability report at the end so you
# know exactly what you have before you start writing tools around it.
#
# Usage:  bash setup/bootstrap.sh [--with-node] [--with-php83]
#
# WHY EACH STEP EXISTS
#   apt-get update  — a fresh sandbox has empty package lists; `apt-get install`
#                     fails with "Unable to locate package" until you update.
#                     This is the single most common first-command failure.
#   php-cli         — lets you actually RUN the subject instead of reading it.
#                     Reading code tells you what it intends; running it tells
#                     you what it does. The gap between those two was where
#                     every interesting finding lived.
#   curl            — absent at session start in some sandboxes, and the wiki
#                     you write will contain curl commands that must be tested.
#   git, jq, sqlite — cheap, frequently needed.
set -uo pipefail

WITH_NODE=0; WITH_PHP83=0
for a in "$@"; do
  case "$a" in
    --with-node)  WITH_NODE=1 ;;
    --with-php83) WITH_PHP83=1 ;;
    -h|--help)    sed -n '2,20p' "$0"; exit 0 ;;
  esac
done

log() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

log "0. Identity and package manager"
id -un; echo "cwd: $(pwd)"
if have apt-get; then PM=apt; elif have dnf; then PM=dnf; elif have apk; then PM=apk; else PM=none; fi
echo "package manager: $PM"

if [ "$PM" = apt ]; then
  log "1. apt-get update (required before any install)"
  DEBIAN_FRONTEND=noninteractive apt-get update -qq >/tmp/apt-update.log 2>&1 \
    && echo "ok" || { echo "FAILED — see /tmp/apt-update.log"; tail -5 /tmp/apt-update.log; }
fi

install() {  # install <label> <apt-name>...
  local label=$1; shift
  if have "$label"; then echo "  already present: $label"; return 0; fi
  case "$PM" in
    apt) DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends "$@" >/tmp/apt-$label.log 2>&1 ;;
    dnf) dnf install -y -q "$@" >/tmp/apt-$label.log 2>&1 ;;
    apk) apk add --no-cache "$@" >/tmp/apt-$label.log 2>&1 ;;
    *)   echo "  no package manager"; return 1 ;;
  esac
  have "$label" && echo "  installed: $label" || { echo "  FAILED: $label (see /tmp/apt-$label.log)"; tail -3 /tmp/apt-$label.log; }
}

log "2. Core tools"
install git git
install curl curl
install jq jq
install python3 python3
install rg ripgrep || echo "  (ripgrep optional — grep works)"
install shellcheck shellcheck || echo "  (shellcheck optional)"

log "3. Language runtimes for the subject under test"
install php php-cli php-mbstring php-curl || true
have php && { php -v | head -1; php -m | tr '\n' ' ' | grep -oE 'mbstring|curl|json|openssl' | tr '\n' ' '; echo; }

if [ "$WITH_PHP83" = 1 ] && have php && ! php -r 'exit(PHP_VERSION_ID >= 80300 ? 0 : 1);'; then
  echo "  PHP is $(php -r 'echo PHP_VERSION;') but the subject documents 8.3+."
  echo "  Try the Sury repo (Debian/Ubuntu):"
  echo "    apt-get install -y lsb-release ca-certificates apt-transport-https software-properties-common"
  echo "    curl -sSLo /usr/share/keyrings/deb.sury.org-php.gpg https://packages.sury.org/php/apt.gpg"
  echo "    echo \"deb [signed-by=/usr/share/keyrings/deb.sury.org-php.gpg] https://packages.sury.org/php/ \$(lsb_release -sc) main\" > /etc/apt/sources.list.d/php.list"
  echo "    apt-get update && apt-get install -y php8.3-cli php8.3-mbstring php8.3-curl"
  echo "  NOTE: a lower version is usually FINE for verification. Record the version you"
  echo "  actually used in the report — 'verified on PHP 8.2.34, documented target 8.3+'"
  echo "  is an honest and useful statement, not a defect."
fi

if [ "$WITH_NODE" = 1 ]; then
  log "4. Node (only if you need mermaid-cli, npm builds, or JS subjects)"
  install node nodejs npm || true
  have node && node -v
fi

log "5. Capability report"
for t in git curl jq python3 rg php node npm shellcheck pandoc libreoffice; do
  if have $t; then printf '  %-12s %s\n' "$t" "$($t --version 2>&1 | head -1 | cut -c1-60)"; else printf '  %-12s ABSENT\n' "$t"; fi
done
echo "  python3 modules:"
python3 - <<'PY'
import importlib
for m in ('json','re','urllib.request','sqlite3','xml.etree.ElementTree','hashlib','subprocess','shutil'):
    try: importlib.import_module(m); print(f"    ok      {m}")
    except Exception as e: print(f"    MISSING {m}: {e}")
PY

log "6. Network egress"
for u in https://github.com https://raw.githubusercontent.com https://api.github.com; do
  if have curl; then code=$(curl -s -o /dev/null -m 8 -w '%{http_code}' "$u" || echo ERR)
  else code=$(python3 -c "
import urllib.request
try: print(urllib.request.urlopen('$u',timeout=8).status)
except Exception as e: print(getattr(e,'code','ERR'))")
  fi
  printf '  %-38s %s\n' "$u" "$code"
done

cat <<'EOF'

──────────────────────────────────────────────────────────────────────────────
 Bootstrap done. Next steps:
   1. git clone <subject> into workspace/repo/
   2. bash scan/repo_scan.py --brief
   3. read setup/PITFALLS.md before writing any probe
   4. probe the running app with probe/webapp_probe.py
──────────────────────────────────────────────────────────────────────────────
EOF
