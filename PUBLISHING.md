# Publishing a kit-built wiki

Verified procedure for getting a finished wiki into a GitHub `.wiki.git`
repository, and for publishing the kit itself. Both hit the same two traps, so
both are documented here.

> [!IMPORTANT]
> **Never force-push.** A GitHub repository — including a wiki repository — may
> already contain the owner's commits. `--force` destroys them. Merge instead,
> even when the histories are unrelated.

---

## The two traps

### 1. Unrelated histories

A kit-built repository and an existing GitHub repository have **different root
commits**, so a plain merge is refused:

```console
$ git pull /path/to/kit.bundle main
fatal: refusing to merge unrelated histories
```

The fix is one flag:

```bash
git merge --allow-unrelated-histories --no-edit FETCH_HEAD
```

This preserves both roots. The resulting history is honest: the owner's
`Initial commit` stays reachable, and the kit's history joins it.

### 2. `.gitignore` silently dropping files

GitHub's "New repository" screen offers a `.gitignore` template. The **Python**
template contains a bare `lib/` rule, which excludes any `lib/` directory —
including one that holds real source.

The danger is that it is **silent on the copy path**:

| Publish path | Effect of a `lib/` rule |
|---|---|
| merge from a bundle | files arrive **through history**, already tracked → kept; `git check-ignore` no longer applies |
| copy files then `git add -A` | files are new and untracked → **both silently dropped**; `git add -A` succeeds, the commit is created, and the files are simply not in it |

So a repository can look published and be missing the two modules its CI and its
probe tool both import. Always run the deep check (§ Verify below).

---

## Publishing a wiki

```bash
git clone https://github.com/OWNER/REPO.wiki.git
cd REPO.wiki
git branch --show-current          # GitHub wikis use master, not main
```

If the wiki was initialised through the GitHub UI it contains one commit with a
placeholder `Home.md`. Copy the pages over it:

```bash
cp /path/to/workspace/wiki/OWNER.REPO.wiki/*.md .
git add -A
git status --short                 # confirm nothing unexpected is staged
git diff --cached --diff-filter=D --name-only    # must be EMPTY
git commit -m "docs(wiki): complete wiki for REPO"
git push origin master
```

If the wiki repository does not exist yet, GitHub only creates the `.wiki.git`
remote **after** the wiki has its first commit — open
`https://github.com/OWNER/REPO/wiki`, click *Create the first page*, save, then
clone.

`publish/publish.sh` automates this: QA gate → clone → copy → commit → verified
bundle → printed instructions. It prompts for nothing and needs no credentials.

---

## Publishing the kit into an existing repository

The verified sequence. It assumes the kit exists as a **bundle** (which is what
survives a transfer that strips `.git`):

```bash
git clone https://github.com/OWNER/KIT.git
cd KIT
git log --oneline                                   # note the owner's root commit

git fetch /abs/path/to/kit.bundle main
git merge --allow-unrelated-histories --no-edit FETCH_HEAD
```

Expect add/add conflicts on files both sides created — typically `.gitignore`
and `README.md`. Resolve them in favour of the kit, because the kit's versions
are written for the kit:

```bash
git diff --name-only --diff-filter=U                # list the conflicts
git checkout --theirs .gitignore README.md          # 'theirs' = FETCH_HEAD = the kit
git add .gitignore README.md
```

> [!NOTE]
> During a merge, **ours** = the checked-out branch (the target repository) and
> **theirs** = `FETCH_HEAD` (the kit). That is the opposite of what `--theirs`
> suggests in a rebase, so check before committing.

Then verify **before** committing:

```bash
# no conflict markers anywhere
git grep -nE '^(<<<<<<<|>>>>>>>|=======)$' -- .

# nothing of the owner's is deleted
git diff --cached --diff-filter=D --name-only

# every kit file is present (space-safe — names may contain spaces)
missing=0
while IFS= read -r -d '' f; do
  [ -e "$f" ] || { echo "MISSING: $f"; missing=1; }
done < <(git -C /path/to/kit ls-files -z)
```

Commit with the **owner's** identity, not the agent's:

```bash
git log -1 --format='%an <%ae>'      # read the identity from existing history
env -u GIT_AUTHOR_NAME -u GIT_AUTHOR_EMAIL \
    -u GIT_COMMITTER_NAME -u GIT_COMMITTER_EMAIL \
  git -c user.name="Owner Name" -c user.email="owner@example.com" \
  commit --no-edit -m "Merge kit into the repository"
git log -1 --format='%an <%ae> | %cn <%ce>'    # confirm BOTH sides
```

> [!WARNING]
> `GIT_AUTHOR_*` / `GIT_COMMITTER_*` environment variables **override** both
> `git config user.*` and `-c user.name=…` on the command line. If a session sets
> them, the commit is attributed to that identity no matter what you pass. Unset
> them explicitly, then verify — the attribution error is invisible otherwise.

```bash
git push origin main
```

---

## Verify

Run these after publishing. The first two are the ones that catch silent loss.

```bash
# 1. no tracked file is excluded by .gitignore
fail=0
while IFS= read -r -d '' f; do
  git check-ignore -q "$f" && { echo "IGNORED: $f <- $(git check-ignore -v "$f" | cut -f1)"; fail=1; }
done < <(git ls-files -z)
[ $fail -eq 0 ] && echo "ok: 0 of $(git ls-files | wc -l) tracked files ignored"

# 2. the specific files a generic template would drop
git check-ignore -v lib/req.py lib/serve.py; echo "exit=$? (1 = not ignored)"

# 3. every path the docs promise actually exists
for doc in SKILL.md AGENTS.md README.md; do
  grep -oE '`(setup|scan|lib|probe|qa|scaffold|publish|templates)/[A-Za-z0-9_./-]+`' "$doc" \
    | tr -d '`' | sort -u | while read -r f; do
        [ -e "$f" ] || echo "MISSING $doc -> $f"
      done
done

# 4. the CI gate, locally
python3 qa/qa_wiki.py --self-test
for f in $(git ls-files '*.py'); do python3 -c "import ast,sys;ast.parse(open(sys.argv[1]).read(),feature_version=(3,8))" "$f"; done
for f in $(git ls-files '*.sh'); do bash -n "$f"; done
while IFS= read -r -d '' f; do python3 -c "import json,sys;json.load(open(sys.argv[1]))" "$f"; done < <(git ls-files -z '*.json')
```

---

## Transferring a repository without `.git`

A directory copied out of a sandbox usually arrives **without** `.git`, so
instructions that begin `cd kit && git log` are wrong for the recipient. Two
robust options:

**Bundle** — carries full history in one file:

```bash
git bundle create kit.bundle main
git bundle verify kit.bundle            # "is okay … records a complete history"
```

The recipient applies it with the merge flow above.

> [!WARNING]
> Cloning a bundle **directly** needs an explicit branch:
> ```bash
> git clone -b main kit.bundle outdir
> ```
> Without `-b` it fails with `remote HEAD refers to nonexistent ref, unable to
> checkout` and leaves an **empty working tree** — after which every later check
> passes vacuously. `git pull <bundle> <branch>` inside an existing clone is
> unaffected. See `setup/PITFALLS.md` §B8.

**Archive** — no history, but nothing to mis-clone:

```bash
git archive --format=tar.gz --prefix=kit/ main > kit.tar.gz
```
