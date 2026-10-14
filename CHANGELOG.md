# Changelog

## 1.2.2 — the scaffold wrote an incomplete skeleton on the explicit-grouping path

Found by running the kit against itself: the wiki for this very project was scaffolded
with `--progress`, and the run produced 21 files where 22 had been announced.

### Fixed

- **`scaffold/new_page.py` omitted `_Footer.md` whenever a grouping was given.**
  The explicit-grouping branch (`--progress` or `--groups`) wrote `Home.md`,
  `_Sidebar.md` and every page stub, then `return`ed — and the footer was only
  written further down, on the heuristic path that the branch never reached. Because
  `_Footer.md` renders on **every** page, the delivered wiki silently shipped without
  its footer, the version/commit line and the trust anchor. The footer write is now a
  shared helper both branches call, and the CLI no longer claims more files than it
  wrote: the count is taken from what `write()` actually did (it also now accounts
  for files skipped by an existing target instead of counting them as written).
- **CI could not have caught it.** The round-trip step drove only the heuristic path,
  and a missing `_Footer.md` is a warning rather than an error, so `--strict` stayed
  green. The step now exercises all three grouping sources — `--pages`, `--groups`
  and `--progress` — and asserts that `Home.md`, `_Sidebar.md` and `_Footer.md` exist
  in each, so a regression on either branch fails the build.

### Verified

- All three grouping paths plus the degenerate one-page case produce `_Footer.md`,
  and each scaffolded tree audits at 0 errors / 0 warnings under `--strict`.
- Reported file counts now equal the files actually on disk (5 / 9 / 5 / 3).
- Negative controls: deleting the footer call from the explicit branch fails the CI
  step (`FAIL --groups scaffold lacks _Footer.md`), and deleting it from the
  heuristic branch fails it too. Both were confirmed on Windows and on a real
  GNU/Linux host (Debian 12, bash 5.2.15, Python 3.11.2) under
  `bash --noprofile --norc -eo pipefail` — the full eleven-step gate is green there.

## 1.2.1 — restore the runnable CI gate, and stop the template banning itself

Two things happened at once before this release: the work published as `92f1ce5`
(which made the `--ban`/`--terms` and documented-paths steps actually runnable) was
not carried into the 1.1.0/1.2.0 line, and the new inline-code masking turned the
restored `--ban` step into a no-op. Both are fixed here, and both are now covered
by checks that were verified to fail when the defect is reintroduced.

### Fixed

- **The `--ban`/`--terms` CI step had become vacuous.** It asserted nothing: the
  banned phrase in its fixture sat inside inline code, and `qa_wiki.py` now blanks
  inline code before matching (that blanking is correct — it is what removed the
  field report's ten false positives), so the command that was supposed to fail
  exited 0 and `set -e` never tripped. The step now uses a fixture where one phrase
  is in PROSE and must fire, while a second appears only inside inline code and must
  stay silent; the empty-template warning is asserted too.
- **`.gitignore` silently dropped the `lib/` tree on the copy path**, which had
  already been fixed once in `92f1ce5` and was lost in the merge. Restored.
- **The documented-paths step failed on `pipefail` alone.** `grep` exits 1 when a
  pattern does not occur, and under `bash -eo pipefail` that aborted the step with
  nothing missing. It passed only because the docs happened to gain local links;
  the collection and the existence check are now separated so it cannot regress.
- **`templates/ban.json` banned its own structural keys.** The loader treated every
  non-underscore top-level key as a phrase, so the template's `exemptions` and
  `fluff_exemptions` lists became banned phrases: any wiki explaining those features
  got `banned claim 'exemptions'`, with a raw list printed as the reason. This is the
  same class of defect as the original 1.0.1 bug, one level further out. Values are
  now treated as phrases only when the key is structural neither by `_` prefix, nor
  by name, nor by being a list.
- **Six tools added in 1.1.0/1.2.0 were invisible to CI.** `qa/fix_toc.py`,
  `lib/session.py`, `lib/evidence.py`, `qa/verify_commands.py`,
  `setup/check_runtime.py` and `setup/snapshot.sh` were documented but never
  executed, and the `--help` step still listed six tools. The step now covers all
  eleven Python tools and warns when a `.py` in the kit is neither exercised nor
  excused; a new step runs the self-tests of the added tools.

### Added

- **A CI step that refuses to publish a run workspace.** A `v3.2/` directory
  (184 files, 4.4 MB: the subject's uploads, a scratch copy of the kit and bundles)
  sat at the repository root untracked but *not* ignored, so a `git add -A` would
  have pushed it into the public kit. `.gitignore` now covers `v3.*/`, `uploads/`,
  `incoming/` and `workspace-fallback/`, and the step fails if such a directory is
  present, unignored, or tracked.

### Verified

- All eleven steps pass on a real GNU/Linux host (Debian 12, bash 5.2.15,
  Python 3.11.2) under `bash --noprofile --norc -eo pipefail`, and also under
  `bash -e` and `sh -e` on Windows — so the result does not depend on which shell
  the runner picks.
- Negative controls: a dead ban loader, a reverted structural-key filter, a deleted
  documented file, an unignored `v3.2/`, and a tool with a broken `--help` each make
  the corresponding step exit non-zero.
- `README.md` said `PITFALLS.md` documents 26 traps; it documents 31. Corrected.
- `lib/evidence.py --self-test` used `/proc/definitely-not-writable/...` as its
  unwritable destination. That is unwritable on Linux but resolves to `C:\proc\…`
  on Windows, which **is** creatable — so the self-test reported FAILED for every
  Windows user while CI (ubuntu) stayed green. It now blocks on a path whose parent
  is a regular file, which is unwritable on every platform, and passes on both.

## 1.2.0 — the remaining field-report items (P1-4…P1-7, P2-8…P2-11)

Completes the plan in `REWORK-PLAN.md`, which came from a full run of this kit
against `paulmann/MD.Scribe` 3.1.0 (23 pages, 41 623 words, 0 QA errors, 249
empirical checks). Every item below was verified by execution, not by reading.

### P1-5 · QA stopped firing on legitimate text (the highest-value fix)

One field run produced **10 QA errors and zero real problems**: a ban phrase
inside a negation ("There is **no** GPG verification"), a quote of the subject's
own docs being *refuted*, the subject's verbatim 404 string, a GitHub anchor slug
(`#mdscribe-extensions` — the slugger drops the dot), a probe filename, and two
domain terms ("**unlock** a hard lock", "PK **magic** bytes").

`qa_wiki.py` now matches ban / avoid / fluff patterns against a **scrubbed view**
of each page: fenced code, inline code, `[[wiki-links]]`, `](#anchor)` targets and
filenames (`\S+\.(py|md|php|js|json|…)`) are blanked first, with offsets preserved
so reported context stays accurate. On top of that:

- **`exemptions`** in `ban.json` / `terms.json` — `{phrase, file?, quote?, reason}`;
  a matched exemption is reported as **INFO**, never silently dropped, so the list
  cannot become a rubbish drawer. `fluff_exemptions` uses the same mechanism.
- **Negation heuristic** for bans: a negating or hedging word within ~90 characters
  *before* the hit, in the same sentence, downgrades it to a **WARNING** — never a
  suppression, because "no database" and "uses a database" are different claims and
  "there is no GPG" must stay visible to a human.
- `--self-test` grew from 15 to **22 detections**, covering negation, anchor slug,
  inline code, exempted avoid term, exempted filler, and "a real banned claim still
  errors".

Verified: the 22-page reference wiki stays at **0 errors** with
`--ban templates/ban.json --terms templates/terms.json`.

### P1-4 · Runtime floor check

`setup/check_runtime.py` reads the subject's declared floor (`composer.json →
require.php`, `package.json → engines.node`, `go.mod`, or a prose `README` claim),
compares it with the installed runtime, reports dependency state, and **exits 2** on
a mismatch. `bootstrap.sh` gains `--subject DIR` (which refuses to continue on
mismatch), `--with-composer`, and unconditional `unzip`/`zip` — without `unzip`,
`composer install` prints a package warning followed by the full usage screen, which
reads exactly like "you passed a wrong flag".

Verified: against a stub declaring `php: >=8.3` with PHP 8.2.34 installed it prints
the mismatch banner and exits 2; with `>=8.1` it exits 0.

### P1-6 · Sidebar grouping is no longer a guess

`new_page.py` gains `--groups "Overview:Home,X|Install:Y"` and
`--progress workspace/PROGRESS.json` (which reads the page tree *and*
`pages[].group` that Phase 2 already decided). Precedence: `--progress` >
`--groups` > the old keyword heuristic, which is kept as a fallback. Pages named in
a grouping but missing from the page list are created, so the scaffold stays
self-consistent.

Verified at **0 QA errors** across four paths: `--groups`, `--progress`, the
degenerate single-page case, and the heuristic fallback.

### P1-7 · `publish.sh` produces a real hand-over

It now **writes** `PUBLISH.md` next to the wiki directory (prepared clone path,
branch, commit SHA, remote, bundle path, file count, push and bundle-apply
commands, the no-force-push rule, and post-publish checks) instead of only printing
options to stdout — stdout is gone after a context loss, a file is not. On a fresh
`git init` it also configures `[remote "origin"]`, which PITFALLS A3 previously
only gave a recipe for.

### P2-8 · Phase-4 command harness

`qa/verify_commands.py` — the field run's harness as a worked template: fresh clone
from GitHub (not the workspace copy), dependency install, dev server started with
the documented command, then every documented curl/recipe including a cookie-jar
CSRF flow and a one-liner `API_KEY` extraction, ending in evidence JSON. In its
originating run it scored **19/19** and caught a real finding: manifest drift
(`.gitignore` 397 B in the published manifest vs 534 B in the commit, and
composer-generated `vendor/composer/*` never hashing equal to a fresh install).

### P2-9 · Multi-layout and stateful probing

`AGENTS.md` gains a section with four rules: never trust a 200 without a body
marker (a front controller's fall-through returned 200 for a path that did not
exist as a shim); two deployment layouts means two `ServedApp` instances in one run
(`--serve-cmd` is exposed on the probe CLI); ordered session-bearing flows use
`lib/session.py`; and evidence writes go through `lib/evidence.write_evidence()`.

### P2-10 · `examples/run2-mdscribe/`

The second reference run as a worked example — a 1571-line battery covering two
layouts and a stateful admin flow, with a README explaining the four transferable
patterns and how to reproduce it (`MDS_TOOLS_LIB` / `MDS_REPO` / `MDS_OUT_*`).
Valuable precisely because its subject shape differs from MD.Viewer's: admin panel,
sessions, CSRF, rate limiting, two docroot layouts.

### P2-11 · `lib/evidence.py`

`write_evidence(dest, payload)` creates parents, retries, and on `OSError` falls
back to `<kit>/workspace-fallback/<name>` with a printed diagnosis, returning the
path actually used. It exists because a field run lost its final evidence file to a
`FileNotFoundError` while `parent.is_dir()` printed `False` in-process and the shell
wrote the same directory fine a second later (PITFALLS B11). `--self-test` 3/3,
including the fallback path.

### Also

- `templates/ban.json` and `templates/terms.json` document the exemptions and
  negation mechanisms, and carry the rule that a verbatim string belonging to the
  *subject* always wins over terminology purity.
- The `PITFALLS.md` §E entries added in 1.1.0 are now cross-referenced from the
  tools that implement them.

## 1.1.0 — field-report hardening (P0 items)

Implemented from an independent field report: a full run of this kit against
`paulmann/MD.Scribe` 3.1.0 that delivered 23 wiki pages / 41 623 words / 0 QA
errors / 249 empirical checks, and reported ten concrete gaps. This release covers
the three P0 items; P1/P2 are tracked in `REWORK-PLAN.md`.

### Added

- **`qa/fix_toc.py`** — rebuilds a page's `## Contents` block from its actual
  H2/H3 headings using `qa_wiki.py`'s own `github_slug`, so anchors are never
  hand-written. QA could *verify* anchors but nothing could *repair* a Contents
  block after a page was rewritten. The reporter's first version of such a tool
  used a greedy "from `## Contents` to the next `---`" replacement and silently ate
  a page's lead paragraph, badges and an alert block (~200 words) on a page that
  had no `---` after the TOC. This version replaces **only the anchored list
  block**, asserts a word-count bound, supports `--bak` and `--dry-run`, and its
  `--self-test` uses that exact accident as its fixture — verified **8/8**, and
  idempotent.
- **`lib/session.py`** — `SessionClient` (cookie jar, no auto-redirect, form/JSON/
  multipart, a `token=` argument that places the CSRF token in both the body field
  and a header) and `csrf_from_html` (six token patterns). `req.py` is stateless
  and `dict(resp.headers)` collapses multiple `Set-Cookie` values, so admin
  surfaces — login, 429 rate limits, token rotation, ~26 authenticated actions,
  logout — could not be probed with kit tools at all. Shipped as a separate module
  rather than merged into `req.py` because it carries its own `Response`/
  `_NoRedirect` pair; keeping it separate preserves verified behaviour instead of
  risking a collision with `req.py`'s tuple-based `Response`. **Live self-test
  verified here against PHP 8.2.34: 8/8** — token extraction, 401 before login,
  403 without a token, 401 on a wrong password, observable 302 on login, an
  authenticated action, session survival across regeneration, and token stability.
- **`setup/snapshot.sh`** — git-snapshots the workspace at phase boundaries. A hard
  session interruption mid-Phase-4 cost the reporter zero work *because* the state
  files were current, but the TOC accident above was recoverable only from memory.
  Snapshots make that class of loss recoverable in seconds.
- **`templates/REWORK-STATE.md.tmpl`** — the recovery artefact that survived that
  interruption: how to resume, exact environment-rebuild commands, key paths,
  sandbox quirks learned, a checklist, and an append-only log.
- **`setup/PITFALLS.md` §E** — five field-report entries, raising the count from 26
  to **31**: `B9` composer needs `unzip` (it prints a usage dump that reads like a
  wrong flag), `B10` the distro runtime may sit below the subject's floor
  (bookworm ships PHP 8.2; subjects needing 8.3 do not boot at all, so every probe
  measures a corpse — with the sury recipe), `B11` long-running probe scripts can
  lose visibility of part of the workspace filesystem (write evidence
  defensively), `D8` bulk regex rewrites of pages are destructive, and `C8`
  ban/avoid/fluff matching is substring-based so quotes, negations, anchor slugs,
  filenames and domain terms all fire.

### Notes

- `lib/session.py`'s live self-test requires `php` on PATH; it skips cleanly and
  stays import-safe without it.
- The field report's §A11 re-attributes an earlier packaging incident: the bytes of
  all delivered files were in fact intact, and the apparent truncation was the
  reporter's own naive fence extractor. The lesson is recorded in `PITFALLS.md`
  and was re-confirmed here — extracting the delivered code from the report's
  aggregate needed CommonMark fence rules (pure closing line, same character,
  rank ≥ opener). A first attempt that measured rank as the length of the whole
  opener line (`​```sha256` → 9) swallowed the rest of the document.

## 1.0.1 — publication-readiness fixes

Found by an independent pre-publication audit. Every item below was reproduced by
execution before being fixed, and every fix is covered by a check that now runs in CI.

### Fixed

- **`qa/qa_wiki.py --ban` was broken against its own template.** The loader treated
  every top-level key of the ban file as a phrase, so the documentation keys in
  `templates/ban.json` (`_comment`, `_notes`, `_template_delete_me`) became banned
  phrases. `"_comment"` matched inside `opcache.save_comments = 1` and produced three
  phantom errors on the reference wiki, while the real example bans nested under
  `_template_delete_me` were never checked at all — a fixture containing a genuinely
  banned claim reported `ERRORS (0)`. Meta keys (leading `_`) are now skipped, `why`
  is normalised to a single short string instead of dumping a 16-element list into
  the message, and an all-meta ban file now emits a warning rather than silently
  enforcing nothing. The template itself is unchanged: its explanatory structure is
  the reason it exists.
- **`--self-test` did not cover `--ban`.** Added six scenarios reproducing the defect
  from both sides: a real banned phrase is caught, `_comment`/`_notes` are ignored,
  `save_comments` does not fire, the reason is reported, and an all-meta file warns.
  Self-test is now 15 detections (was 9).
- **CI never exercised the documented audit command.** `SKILL.md`, `AGENTS.md` and
  `PROMPT.md` all instruct running `--terms` and `--ban`, but the workflow mentioned
  neither, so the defect above was unreachable by CI. Added three steps: a
  `--ban`/`--terms` fixture run, a check that every path referenced by `SKILL.md`,
  `AGENTS.md` and `README.md` exists, and a check that no tracked file is excluded by
  `.gitignore`. The second and third exist because a `lib/` rule in the target
  repository's `.gitignore` was silently dropping `lib/req.py` and `lib/serve.py` —
  two files the CI `--help` step and `probe/webapp_probe.py` both depend on.
- **`setup/PITFALLS.md` miscounted and mis-ordered.** It documents 26 traps, not 27;
  `README.md` and `CHANGELOG.md` claimed 27. The `### B8` section also sat after
  `### D7`, splitting group B; it is now in place, giving
  A1–A4, B1–B8, C1–C7, D1–D7.
- **`examples/REPORT.md` carried stale figures.** It described the wiki before the
  three corrections the toolkit found in it. Reconciled to the measured values —
  73 013 words, 154 alerts, 27 mermaid diagrams (26 `flowchart`, 1
  `sequenceDiagram`), 1 687 table rows, 341 wiki-links — with a note recording the
  earlier snapshot and how to reproduce the current one. Ten references to the
  pre-extraction checker name `qa_full.py` now read `qa/qa_wiki.py`.
- **`.gitignore` was missing `.ragraf/`**, a machine-local agent index that must never
  be committed.
- **`PUBLISH.md` described a state that does not exist and a flow that does not
  work.** It claimed a local committed repository in a directory that ships without
  `.git`; its Option B (`git pull <bundle> main`) fails with `refusing to merge
  unrelated histories` because the kit and the target repository have different root
  commits; and its Option C contained a non-command line
  (`rm -rf .git/..?  # keep .git…`). Rewritten around a verified
  `fetch` + `merge --allow-unrelated-histories` flow, including the two add/add
  conflicts it produces and how to resolve them, and an explicit prohibition on
  force-push (the target repository contains the owner's `Initial commit`).
- **`publish/publish.sh`** now documents that cloning a bundle directly requires an
  explicit branch (`git clone -b main file.bundle`), because without it the clone
  fails with `remote HEAD refers to nonexistent ref` and leaves an empty working tree
  — after which every later check passes vacuously. Recorded as `PITFALLS.md` §B8.

## 1.0.0 — initial public release

Extracted from a completed run that produced a 22-file, 73 013-word GitHub Wiki
for [paulmann/MD.Viewer](https://github.com/paulmann/MD.Viewer) with zero
outstanding QA errors.

### Added

- `SKILL.md` — agent entry point with the four-phase workflow.
- `AGENTS.md` — phase-to-tool mapping and the tool reference table.
- `PROMPT.md` — a ready-to-paste task prompt; only the header block changes.
- `setup/bootstrap.sh` — idempotent environment setup with a capability and
  network-egress report.
- `setup/PITFALLS.md` — 26 traps encountered in the reference run, ordered by
  time wasted, with the three that produce silently wrong results first.
- `scan/repo_scan.py` — whole-repository inventory to JSON plus a two-minute
  brief. Symbol extraction for PHP, JS/TS, Python, Go, Ruby, Java, C#, PowerShell
  and shell; manifest detection for eight ecosystems; external-host, version-marker
  and security-signal extraction.
- `lib/req.py` — dependency-free HTTP client returning status, headers and body
  for every outcome including 4xx/5xx, with form and multipart helpers and a CLI.
- `lib/serve.py` — `ServedApp`: stages a clean copy of the subject on a
  verified-free port, waits for readiness, probes once over HTTP, and kills its own
  process group. Fixture helpers `write` / `mkdir` / `set_ini` / `ls` / `read`.
- `probe/webapp_probe.py` — declarative batteries (modes, 20 traversal payloads,
  26 injection payloads, config-flag gating, upload matrices, API status codes,
  header inventory, disk side-effects) emitting evidence as JSON and Markdown.
- `qa/qa_wiki.py` — the full wiki audit with `--self-test`, `--strict`, `--json`,
  `--terms` and `--ban`.
- `scaffold/new_page.py` — QA-clean wiki skeleton or single page.
- `publish/publish.sh` — QA gate, clone of the `.wiki.git` repository, commit,
  verified git bundle, and three publishing paths. Never prompts, never
  force-pushes.
- `templates/` — `terms.json`, `ban.json`, `STATE.md.tmpl`, `PROGRESS.json.tmpl`.
- `examples/` — research artefacts and sample pages from the reference run.
- CI workflow running the QA self-test, syntax checks and a scaffold round-trip.

### Bugs found and fixed while extracting the kit

Nine defects were found in the tools themselves during extraction. All were
caught by running them, not by reading them — which is the point of the kit.

1. `qa_wiki.py`: `name, text = p.name, texts[name]` — Python evaluates the whole
   right-hand side with the **old** `name`, so every page was audited against the
   previous page's text. Produced 235 phantom errors.
2. `qa_wiki.py`: code-block bodies were never accumulated (missing `buf.append`),
   so the mermaid and shell checks ran vacuously and always passed.
3. `qa_wiki.py`: the bracket-in-label check fired on quoted labels and on the
   mermaid cylinder shape `[(...)]`.
4. `qa_wiki.py`: the `subgraph`/`end` balance check was applied to
   `sequenceDiagram`, where `end` closes `alt`/`opt`/`loop` instead.
5. `qa_wiki.py`: the lead-paragraph regex was too strict, producing four false
   warnings on pages whose lead is followed by an alert or a table.
6. `new_page.py`: `_Footer.md` and `Home.md` hardcoded page names
   (`[[Glossary]]`, `[[Changelog and Versioning]]`, `[[Getting Started]]`), so any
   other page list produced dead links — and the footer renders on every page.
   Now derived from the page list actually being created.
7. `publish.sh`: a relative `WIKI_DIR` stopped resolving after the script `cd`'d
   into the clone (`cp: cannot stat '.scratch/wiki/*.md'`). Now absolutised up front.
8. `publish.sh`: an interactive `read` prompt aborted in a sandbox with no
   controlling terminal, and it gated on a filename heuristic that false-positives
   on legitimate titles such as `Self-Updater Guide.md`. Now non-blocking and
   non-interactive; the authoritative check is the QA step.
9. `templates/terms.json`: two over-broad `avoid` patterns (`base director`,
   `config file`) fired on correct prose. Narrowed to four high-confidence
   patterns, with a tuning warning added.

### Corrections the tools found in the delivered wiki

Worth recording because it demonstrates the value of phase 4 step 3 (re-running
what you documented):

1. `Architecture.md` quoted **fabricated** code for the doubled-slash normaliser
   (`parse_url(..., PHP_URL_PATH)`). Replaced with the verbatim source.
2. The normaliser was documented as path-only; it also rewrites the **query
   string** (verified: `?file=docs//sub/a.md` → 301 → `?file=docs/sub/a.md`).
3. The claim that `&force=true` propagates from update phase 1 to phase 2 was
   transcribed from the subject's README; the code builds a literal query string
   and drops it. Corrected, with the discrepancy documented.
