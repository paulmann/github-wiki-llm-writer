# PITFALLS — read this before you write a single tool

Every item below was hit for real during a completed repo→wiki run and cost
between two minutes and half an hour. They are ordered by how much time they
wasted. The first three are the ones that produce **silently wrong results**,
which is worse than a crash.

---

## A. Traps that give you WRONG answers while looking fine

### A1. Port already in use → your tests hit a stale instance 🔴 worst offender

```bash
cd /tmp/app && php -S 127.0.0.1:8080 &      # prints "Address already in use", dies
sleep 2 && curl http://127.0.0.1:8080/md.php # ← talks to the OLD server
```

The old server has the **old document root and old state files**. You will
conclude that `.md.ini` "was not created", that a flag "did not take effect",
that a file "is missing" — all false.

**Fix:** never hand-roll this. Use `lib/serve.py`:

```python
from serve import ServedApp
with ServedApp(repo, copy=['md.php','css','js']) as app:   # fresh temp docroot
    app.write('md.md', '# Hi\n')
    r = app.get('/md.php')
```

It picks a verified-free port, stages a **clean copy** in a temp dir, waits for
the socket, does one HTTP probe to confirm the interpreter is not dying on every
request, and kills what it started. If you must do it by hand, at minimum:

```bash
python3 -c "import socket;s=socket.socket();
try: s.bind(('127.0.0.1',8080)); print('FREE')
except OSError: print('BUSY — do not proceed')"
```

### A2. Never name a file `http.py` (or `json.py`, `re.py`, `test.py`) 🔴

I saved an HTTP helper as `/tmp/http.py` and ran it from `/tmp`. Python put the
directory on `sys.path`, my file shadowed the stdlib `http` package, and
*every* `urllib.request` call died with:

```
ModuleNotFoundError: No module named 'http.client'; 'http' is not a package
```

The error names `http.client`, so you go looking for a broken stdlib. It is your
file. Same class of bug: `json.py`, `re.py`, `queue.py`, `types.py`, `email.py`,
`csv.py`, `random.py`, `copy.py`, `tokenize.py`.

**Fix:** `lib/req.py` is already named safely. Keep helper modules in
`lib/` with names that cannot collide.

### A3. Files outside `/home/user` do not persist 🔴

Everything I built under `/tmp` — the HTTP helper, the XSS battery, the
traversal battery — was **gone** at the end of the session. Only
`/home/user/**` is snapshotted.

Also excluded from snapshots: `.arena .cache .mypy_cache .next .nox .npm .nuxt
.output .parcel-cache .pytest_cache .ruff_cache .svelte-kit .tox .turbo .venv
.vite __pycache__ build coverage dist node_modules out target`, plus
`.git/config`, `.git/credentials`, `.git-credentials`, `.netrc`.

Two consequences that bite:
- **Never put the deliverable in `dist/`, `build/` or `out/`.** It vanishes.
- **A prepared git clone loses `.git/config`**, so its `origin` remote is gone
  on reload. Recreate it, or ship a `git bundle` instead of relying on the
  clone's config:
  ```bash
  cat > publish/.git/config <<'EOF'
  [remote "origin"]
  	url = https://github.com/OWNER/REPO.wiki.git
  	fetch = +refs/heads/*:refs/remotes/origin/*
  [branch "master"]
  	remote = origin
  	merge = refs/heads/master
  EOF
  ```

### A4. The README lies. Verify, do not transcribe.

In the run this toolkit came from, the subject's README claimed **"syntax
highlighting"** and **"nested lists"**. Neither existed. A repo-wide search for
external asset URLs found three CDNs and no highlighter; nested lists rendered
as literal text. Had I transcribed the README, the wiki would have shipped two
false claims — and a reader would have found them in minutes.

**Rule:** a claim enters the wiki only if it is (a) traced to a source line, or
(b) reproduced by execution. Keep a `do_not_claim` list in `PROGRESS.json` and
re-check it in QA.

---

## B. Sandbox environment quirks

### B1. `apt-get install` fails until you `apt-get update`

```
E: Unable to locate package php-cli
```

A fresh sandbox has empty package lists. Always:

```bash
apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends php-cli php-mbstring php-curl curl
```

`setup/bootstrap.sh` does this for you and prints a capability report.

### B2. `curl` may be absent at session start

Check before writing curl-based examples you intend to test:

```bash
command -v curl || apt-get install -y curl
```

Until then, `lib/req.py` (stdlib only) does everything curl does and
returns **headers + status + body as data**, which is what you need when the
wiki documents exact status codes.

### B3. `pkill` / `pgrep` / `lsof` / `ss` are usually absent

To find what holds a port:

```bash
python3 - <<'PY'
import socket
for p in (8080, 8123, 8231):
    s=socket.socket()
    try: s.bind(('127.0.0.1',p)); print(p,'FREE')
    except OSError: print(p,'BUSY')
    finally: s.close()
PY
```

To kill: `serve.py` tracks its own child PID and process group. For strays,
`kill $(ps -eo pid,args | awk '/[p]hp -S/{print $1}')`.

### B4. Absolute paths inside bash heredocs can get mangled

Observed: a heredoc containing `/home/user/workspace/PROGRESS.json` arrived at
Python as `"$ARENA_WORKSPACE"/workspace/PROGRESS.json` and `open()` failed.

**Fixes, in order of preference:**
1. `cd` first and use **relative** paths.
2. Pass paths via **environment variables**: `REPO=../../repo/X python3 - <<'PY' … os.environ['REPO'] … PY`
3. Write the script to a file with `write_file`, then run it.

### B5. Python 3.11 f-strings cannot contain backslashes

```python
print(f"x: {'YES' if b'class=\"toc' in b else 'no'}")   # SyntaxError
```

Hoist the needle:

```python
TOC = b'class="toc'
print(f"x: {'YES' if TOC in b else 'no'}")
```

### B6. There is no controlling terminal; stdin is closed

`sudo` prompts, `git push` credential prompts and interactive `read` all fail.
`git push` will not work — expect it, and ship a **bundle + instructions**
instead of treating the failure as an error.

### B7. Don't `cat` a 200 KB source file

Read in ranges: `sed -n '661,760p' md.php`. Or map first, then read:

```bash
grep -n '^\s*function\s\+[a-zA-Z_]*' md.php        # function index with line numbers
grep -n 'define(\|const ' md.php                    # configuration surface
```

---

### B8. `git clone <file.bundle>` needs an explicit branch

A bundle carries no HEAD symref, so a bare clone fails with:

```
warning: remote HEAD refers to nonexistent ref, unable to checkout
fatal: Needed a single revision
```

and leaves an empty working tree — which then makes every later check "pass"
vacuously. Always pass the branch:

```bash
git clone -b main  repo.bundle outdir      # or -b master for a wiki bundle
```

`git pull <bundle> <branch>` inside an existing clone is unaffected.

## C. GitHub Wiki specifics

### C1. Filename ↔ URL ↔ wiki-link must agree

GitHub maps a wiki file's **spaces to hyphens** in the URL and resolves
`[[Page Name]]` by that rule:

| File in the repo | URL | Working wiki-link |
|---|---|---|
| `Security Hardening Guide.md` | `/wiki/Security-Hardening-Guide` | `[[Security Hardening Guide]]` ✅ |
| `Security-Hardening-Guide.md` | `/wiki/Security-Hardening-Guide` | `[[Security Hardening Guide]]` ❌ broken |

So: **name files with spaces**, link with the same spaces. (Underscores in a
filename become spaces in the title — avoid them except for `_Sidebar`/`_Footer`.)

`_Sidebar.md` and `_Footer.md` are magic: they render on every page and are not
themselves listed. Their names keep the underscore.

### C2. The wiki repo's default branch is `master`, not `main`

```bash
git clone https://github.com/OWNER/REPO.wiki.git
cd REPO.wiki && git branch --show-current     # → master
```

Pushing to `main` creates an orphan branch that GitHub ignores.

### C3. A wiki repo may already exist with a placeholder

The run this came from found `Home.md` containing only
`Welcome to the X wiki!` and one commit, `Initial Home page`. Clone, commit on
top, push — do not force-push over history you did not create.

### C4. `[[...]]` in prose is a live link, even when you mean it literally

If your subject uses `[[1,2]]` citation syntax and you write about it in prose,
GitHub turns it into a link to a non-existent page `1,2`. **Always wrap such
examples in backticks**: `` `[[1,2]]` ``. The QA tool reports these.

### C5. Anchors follow GitHub's slug algorithm

lowercase → strip everything except alphanumerics, spaces, hyphens, underscores
→ spaces to hyphens → **do not collapse repeated hyphens** → dedupe with `-1`,
`-2`.

| Heading | Anchor |
|---|---|
| `## Request lifecycle in \`md.php\`` | `#request-lifecycle-in-mdphp` |
| `## Step 6 — Read \`.md.ini\`` | `#step-6--read-mdini` (double hyphen — the em dash is dropped, not collapsed) |
| `## \`action=status\`` | `#actionstatus` |
| `## Notes` (second one) | `#notes-1` |

Guessing these is the #1 source of dead anchors. `qa/qa_wiki.py` computes
them; do not hand-write TOC anchors.

### C6. Mermaid in wikis: two rules that break rendering

1. **`&` must be `&amp;`** inside labels, including quoted ones.
2. **Quote any label containing special characters** — parentheses, brackets,
   braces, colons, regex backslashes:
   ```
   B{"Array value?<br/>(INI key[] syntax)"}      ✅ quoted
   B{Array value? (key[] syntax)}                ❌ parse error
   ```
3. Prefer prose over clever notation in labels: `force flag preserved` beats
   `(&force preserved)`.

### C7. Nested code fences need a longer outer fence

A ```` ```markdown ```` example that itself contains ```` ```bash ```` must be
wrapped in **four** backticks:

`````markdown
````markdown
Some docs with a block:

```bash
ls
```
````
`````

With three on the outside, the inner fence **closes** the block early and the
rest of your page renders as garbage. `qa/qa_wiki.py --fences` catches it.
This bug shipped once and was only caught by the checker.

---

## D. Process traps

### D1. Rebuild derived data after a rename

I renamed 15 wiki files (hyphens → spaces) and then a checker still reported
"no such page" because it had cached the old file list. Any structure you
derive — file lists, stem sets, anchor maps — must be rebuilt, not reused.

### D2. Your own checker will have bugs. Distrust it once.

My first QA run reported 381 link errors. All were false: it compared
`"Page.md"` against a set of stems without the extension. The second run
reported 12 anchor errors; 11 were the checker's slugger dropping backticks in
headings, 1 was real.

**Rule:** when a checker reports a mass failure, verify one case by hand before
believing it. And when it reports *zero* failures, verify it can actually fail
— feed it a deliberately broken link.

### D3. Write the research files before you need them

Context can be compacted mid-task. `STATE.md`, `PROGRESS.json` and
`research/facts.json` exist so a fresh agent resumes without re-deriving
anything. Update them at phase boundaries, not at the end. The `research/`
directory from the original run let me answer "was that verified or assumed?"
for every claim hours later.

### D4. Keep a provenance table

`research/sources.md` had four sections: (A) source-line citations, (B) named
empirical tests, (C) external sources, (D) **claims deliberately not made, with
reasons**. Section D is the most valuable — it is what stops a future you from
"helpfully" re-adding a plausible-but-false statement.

### D5. Budget the writing phase; it is the long one

In the reference run: research ≈ 40% of the effort, writing ≈ 45%, QA ≈ 15%.
20 pages × ~3 600 words is not fast. Scaffold with `scaffold/new_page.py`
so structure is free, and write the two hardest pages first
(usually Security and the reference matrix) while the research is fresh.

### D6. Over-broad `avoid` patterns train you to ignore the QA

A terminology checker whose banned-synonym list fires on *correct* prose is worse
than no checker: after three phantom errors you stop reading the output.

Two patterns had to be removed from the shipped `templates/terms.json` after they
false-positived on a real 73k-word wiki:

- `base director` — legitimate when describing a code function whose job *is* a
  base directory (`docRoot()`), which is a different concept from the domain term
  "browse root".
- `config file` — legitimate generic prose ("without first editing a config
  file"); forcing the literal filename into every mention makes the writing worse.

**Rule:** prefer patterns that match a specific *wrong phrase* over patterns that
match a common noun. Run the list against the finished wiki and read every hit
before trusting it. Keep `canonical` entries broad — they only count usage and
never fail — and use them to spot a glossary term you defined but never used.

### D7. Your own tool templates have bugs too

The scaffold template shipped with a `_Footer.md` that hardcoded
`[[Changelog and Versioning]]` and `[[Glossary]]`, and a `Home.md` that hardcoded
`[[Getting Started]]`. Any page list not containing those names produced dead
links — and `_Footer.md` renders on *every* page, so one bad template line became
a site-wide error. Fixed by deriving all such links from the page list actually
being created.

**Rule:** never hardcode a page name in a template. Derive it, and run the QA
checker over scaffold output for at least three different page lists (including
the degenerate one-page case) before shipping the template.

