#!/usr/bin/env bash
# publish.sh — take a finished wiki directory and make it pushable.
#
# Handles everything that went wrong or nearly went wrong in the reference run:
#   * the wiki repo's default branch is `master`, not `main`
#   * the wiki repo may already exist with a placeholder Home.md — never force-push
#   * filenames must contain SPACES (GitHub maps them to hyphenated URLs), so a
#     `Security Hardening Guide.md` is what makes [[Security Hardening Guide]] work
#   * the sandbox usually has no credentials, so the deliverable is a COMMIT plus a
#     verified BUNDLE plus printed instructions — not a push that fails
#
# Usage:
#   bash publish/publish.sh <wiki-dir> <owner>/<repo> [--push]
#
#   bash publish/publish.sh workspace/wiki/MD.Viewer.wiki paulmann/MD.Viewer
#   bash publish/publish.sh workspace/wiki/MD.Viewer.wiki paulmann/MD.Viewer --push
set -euo pipefail

WIKI_DIR_ARG=${1:?usage: publish.sh <wiki-dir> <owner>/<repo> [--push]}
SLUG=${2:?usage: publish.sh <wiki-dir> <owner>/<repo> [--push]}
DO_PUSH=${3:-}
OWNER=${SLUG%%/*}; REPO=${SLUG##*/}
WIKI_URL="https://github.com/${OWNER}/${REPO}.wiki.git"

# Absolutise NOW. The script cd's into the clone later, and a relative
# WIKI_DIR silently stops resolving there (`cp: cannot stat '.scratch/wiki/*.md'`).
[ -d "$WIKI_DIR_ARG" ] || { echo "no such dir: $WIKI_DIR_ARG"; exit 1; }
WIKI_DIR="$(cd "$WIKI_DIR_ARG" && pwd)"
PARENT="$(dirname "$WIKI_DIR")"
OUT="${PUBLISH_OUT:-$PARENT/publish}"
BUNDLE="${PUBLISH_BUNDLE:-$PARENT/${REPO}.wiki.bundle}"

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

say "0. Pre-flight"
echo "  wiki dir : $WIKI_DIR"
echo "  output   : $OUT"
n=$(find "$WIKI_DIR" -maxdepth 1 -name '*.md' | wc -l)
echo "  $n markdown files in $WIKI_DIR"
[ "$n" -ge 1 ] || { echo "nothing to publish"; exit 1; }

# Informational only: a hyphen in a filename is *usually* a mistake, because
# [[Page Name]] resolves to the hyphenated URL only when the FILE has spaces.
# But it is not always a mistake ("Self-Updater Guide.md" is a real title).
# The authoritative check is qa_wiki.py in step 1, which validates every
# [[link]] against the actual filenames — so do not prompt here, and never
# block on a heuristic. (Also: the sandbox has no controlling terminal, so an
# interactive `read` silently takes the default and aborts the script.)
hy=$(find "$WIKI_DIR" -maxdepth 1 -name '*.md' ! -name '_*' -print0 \
      | xargs -0 -n1 basename 2>/dev/null | grep -- '-' || true)
if [ -n "$hy" ]; then
  echo "  note: these filenames contain hyphens:"
  echo "$hy" | sed 's/^/      /'
  echo "    fine if the page title really has a hyphen; a mistake if they were"
  echo "    meant to be spaces. Step 1 decides — it validates every [[link]]."
fi

say "1. Run QA — do not publish a wiki with dead links"
if [ -f "$(dirname "$0")/../qa/qa_wiki.py" ]; then
  python3 "$(dirname "$0")/../qa/qa_wiki.py" "$WIKI_DIR" --strict || {
    echo; echo "QA failed. Fix the errors above, then re-run."; exit 1; }
else
  echo "  (qa_wiki.py not found next to this script — skipping; run it manually)"
fi

say "2. Clone the wiki repository"
rm -rf "$OUT"
if git clone -q "$WIKI_URL" "$OUT" 2>/dev/null; then
  cd "$OUT"
  branch=$(git branch --show-current)
  echo "  cloned; default branch is '$branch' (GitHub wikis use master, not main)"
  echo "  existing history:"
  git log --oneline | head -5 | sed 's/^/    /'
  existing=$(find . -maxdepth 1 -name '*.md' ! -name '_*' | wc -l)
  echo "  existing content pages: $existing"
else
  echo "  clone failed (private repo, no network, or the wiki has never been"
  echo "  initialised). Initialise it first: open"
  echo "    https://github.com/${OWNER}/${REPO}/wiki"
  echo "  and click 'Create the first page' — GitHub only creates the .wiki.git"
  echo "  remote once the wiki has at least one commit."
  echo
  echo "  Falling back to a plain git repo you can push manually."
  mkdir -p "$OUT"; cd "$OUT"; git init -q; git checkout -q -b master
fi

say "3. Copy the pages in"
cp "$WIKI_DIR"/*.md .
git add -A
echo "  staged:"
git status --short | sed 's/^/    /' | head -30

say "4. Commit"
if git diff --cached --quiet; then
  echo "  nothing changed — the wiki already matches"
else
  git -c user.name="${GIT_AUTHOR_NAME:-wiki-bot}" \
      -c user.email="${GIT_AUTHOR_EMAIL:-wiki-bot@localhost}" \
      commit -q -F - <<MSG
docs(wiki): ${WIKI_COMMIT_SUBJECT:-complete wiki for ${REPO}}

$(python3 - "$WIKI_DIR" <<'PY'
import sys, pathlib
d = pathlib.Path(sys.argv[1])
files = sorted(p for p in d.glob('*.md'))
words = sum(len(p.read_text(encoding='utf-8').split()) for p in files)
print(f"{len(files)} files, {words:,} words.")
print("Pages: " + ", ".join(p.stem for p in files if not p.stem.startswith('_')) + ".")
PY
)
MSG
  echo "  committed $(git rev-parse --short HEAD)"
fi

say "5. Make a bundle (works without credentials)"
cd ..
git -C "$OUT" bundle create "$BUNDLE" master >/dev/null 2>&1 || \
  git -C "$OUT" bundle create "$BUNDLE" --all >/dev/null
git -C "$OUT" bundle verify "$BUNDLE" 2>&1 | head -4 | sed 's/^/  /'
echo "  bundle: $BUNDLE ($(du -h "$BUNDLE" | cut -f1))"

say "6. Push"
if [ "$DO_PUSH" = "--push" ]; then
  cd "$OUT"
  if git push -q origin master 2>/dev/null; then
    echo "  ✅ pushed to $WIKI_URL (master)"
    echo "  → https://github.com/${OWNER}/${REPO}/wiki"
  else
    echo "  ❌ push failed — almost always missing credentials."
    echo "     The commit and the bundle are ready; run this where you have access:"
    echo "       cd $OUT && git push origin master"
    echo "     or:"
    echo "       git clone $WIKI_URL && cd ${REPO}.wiki"
    echo "       git pull $BUNDLE master && git push origin master"
  fi
else
  echo "  skipped (pass --push to attempt it)."
  echo
  cat <<EOF
  The commit is ready in:  $OUT
  A verified bundle is at: $BUNDLE

  To publish, on a machine with GitHub access:

    # option A — push the prepared clone
    cd $OUT
    git remote -v          # should show $WIKI_URL
    git push origin master

    # option B — apply the bundle to a fresh clone
    git clone $WIKI_URL
    cd ${REPO}.wiki
    git pull $BUNDLE master
    git push origin master
    #
    # Cloning a bundle DIRECTLY (git clone file.bundle) needs an explicit
    # branch: without -b it fails with "remote HEAD refers to nonexistent ref,
    # unable to checkout" because a bundle carries no HEAD symref. Use:
    #   git clone -b master $BUNDLE outdir

    # option C — just copy the files
    git clone $WIKI_URL && cd ${REPO}.wiki
    cp $WIKI_DIR/*.md .
    git add -A && git commit -m "docs(wiki): complete wiki" && git push origin master

  Then verify at https://github.com/${OWNER}/${REPO}/wiki :
    - the sidebar renders on every page
    - [[wiki-links]] resolve (hyphenated URLs)
    - mermaid diagrams render
    - > [!NOTE] alerts render as coloured callouts
EOF
fi
