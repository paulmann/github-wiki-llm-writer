# REWORK-PLAN — remaining items from the MD.Scribe field report

**Status: COMPLETE.** P0 landed in v1.1.0 (`5c40f21`); every P1 and P2 item below
landed in v1.2.0 (`835608e`). This file is kept as the specification and evidence
trail for what was implemented and why — see `CHANGELOG.md` 1.1.0/1.2.0. Source of every item: `DEVELOPER-REPORT.md` §A1–A10 and the
priority plan in §F, from a full run of this kit against `paulmann/MD.Scribe` 3.1.0
(23 pages, 41 623 words, 0 QA errors, 249 empirical checks, 14 verified findings).

The reporter's ready-made code for several items was extracted from `UNPACK.MD` into
`workspace/skill/incoming/` (8 files, all syntax-checked, 0 CRLF). **Use those files;
do not rewrite them.**

## Done (v1.1.0)

| Item | Evidence |
|---|---|
| **P0-1** `qa/fix_toc.py` | `--self-test` **8/8** in place, including the accident fixture (lead/badge/alert survive); idempotent |
| **P0-2** `lib/session.py` (`SessionClient`, `csrf_from_html`) | **live self-test 8/8 on PHP 8.2.34**: token extraction, 401 before login, 403 without token, 401 wrong password, observable 302, authed action, session regeneration survival, token stability |
| **P0-3** `setup/snapshot.sh` + `templates/REWORK-STATE.md.tmpl` | `bash -n` OK; template carries the four sections §D.5 asks for |
| **§E** `PITFALLS.md` B9, B10, B11, D8, C8 + snapshots | trap count 26 → **31**, order verified |
| Docs | `README.md`, `SKILL.md`, `AGENTS.md` tool tables list all four new files |

Full CI gate re-run after integration: python 3.8-syntax 8/8 · shell 3/3 · JSON 4/4 ·
`--help` 7/7 · `qa_wiki.py --self-test` **15/15** · `fix_toc.py --self-test` **8/8** ·
`session.py` live **8/8** · scaffold round-trip 2/2.

---

## P1 — done

### P1-4  ✅ DONE · Runtime floor check (§A1, §A2)

`bootstrap.sh` installs the **distro's** PHP (bookworm → 8.2) while the subject
required ≥8.3 (`json_validate()` in 9 files, typed class constants). On 8.2 the
subject does not boot at all, so **every probe measures a corpse** — a
silently-wrong-results class A trap. The reporter hand-installed sury 8.3.

- Minimum viable: a step in `repo_scan.py --brief` comparing the declared runtime
  (`composer.json → require.php`, `package.json → engines`, `go.mod`) against the
  installed one, printing a red `MISMATCH — probing will fail`. `repo_scan.py`
  already parses manifests and already prints the constraint; only the comparison
  and the shout are missing.
- Better: `bootstrap.sh --subject <dir|url>` installing a matching runtime (the sury
  recipe is already in `PITFALLS.md` §B10).
- Also: install `unzip zip` unconditionally, and offer `--with-composer`. Without
  `unzip`, `composer install` prints a package-download warning followed by the
  **full usage screen**, which reads exactly like "you passed a wrong flag" (§B9).

**Acceptance:** on bookworm with a subject declaring `php: >=8.3`, either the
runtime is brought into line or further steps are blocked by an explicit red line;
`composer install` in a PHP subject succeeds with no manual steps.

### P1-5  ✅ DONE · QA false positives from substring matching (§A6) — highest-value P1

Two QA cycles produced **10 errors, none of them real**. Every hit was legitimate
text:

| Hit | Legitimate context |
|---|---|
| ban `GPG` | "There is **no** GPG or sigstore verification" — a negation |
| ban `double-gated` | a quote of the subject's own docs **being refuted** |
| ban `bypass the reader` | "docs claim X. Measured: they do not" |
| ban `renders as literal text` | a correct statement about escaped raw HTML |
| ban `multi-user` ×4 | describing **competitors** (BookStack, Wiki.js), not the subject |
| avoid `security validator` | the subject's **verbatim 404 message** in a Troubleshooting table |
| avoid `MDScribe` ×3 | a GitHub anchor slug (`#mdscribe-extensions` — the slugger drops the dot) and a probe filename |
| fluff `unlock` | "delete the line to **unlock** a hard lock" — exact domain terminology |
| fluff `magic` | "`PK` **magic** bytes" — a standard term |

Five mechanisms requested, in order of value:

1. **Contextual skips for `avoid` patterns** — do not count hits inside inline code,
   fenced blocks, `[[wiki-links]]`, `](#…)` anchors, or filenames matching
   `\S+\.(py|md|php|js|json)`. This alone removes the slug/filename/verbatim-quote
   class. Note `qa_wiki.py` already computes a code-masked view (`mask_code`) — reuse it.
2. **`exemptions` in `ban.json`/`terms.json`**:
   `{"phrase": …, "file": "Troubleshooting.md", "quote": "<verbatim fragment>", "reason": …}`
   — reported as INFO ("exempted hit"), never ERROR. Exemptions stay visible in the
   report so they cannot become a rubbish drawer.
3. **Negation heuristic for `ban`** (deliberately cautious): if
   `\b(no|not|never|isn't|doesn't|without|false|myth|claim(s|ed)?)\b` occurs within
   ~6 words **before** the match, downgrade to WARNING "possible negated mention —
   review". Do **not** suppress: "no database" and "uses a database" are different
   claims, and "there is no GPG" is caught precisely this way.
4. **The same exemption mechanism for fluff** (`unlock`, `magic` are domain terms).
5. `templates/ban.json` gains a paragraph: if refuting a doc claim requires quoting
   it, **paraphrase** the quote — substring matching cannot tell a refutation from an
   assertion.

**Acceptance:** on this run's text (all 10 hits known) QA reports 0 errors either
without manual rephrasing or with explicitly recorded exemptions; `--self-test`
gains `negation`, `slug`, and `verbatim-in-code` cases.

> [!WARNING]
> Whatever is changed here, `--self-test` must stay at 15/15 and then grow. The
> reporter's own §D2 lesson applies: verify one hit by hand before believing a mass
> failure — and note that in *their* run all 10 were false, while in *mine* the
> analogous mass failure was a checker bug. Both directions are real.

### P1-6  ✅ DONE · Scaffolder sidebar grouping (§A7)

`new_page.py --init --pages "…21 names…"` grouped pages by its own keyword
heuristic and got it wrong: `Admin Panel Guide` landed under "Authoring / usage",
`Library and Routing` and `Upgrade from MD.Viewer v2` under "Reference". The
reporter rewrote `_Sidebar.md` by hand — but grouping is Phase 2 architecture and
`PROGRESS.json` **already stores it** in `pages[].group`.

Add `--groups "Overview:Home,Getting Started|Install:…"` **or**
`--progress workspace/PROGRESS.json` (derive the tree and groups from there).
Current heuristic stays as the fallback.

**Acceptance:** on a 21-page tree the scaffolder emits the intended 5-group sidebar
with no hand editing; degenerate cases (one page, pages with no group) still work —
this is the §D7 rule that already bit once.

### P1-7  ✅ DONE · `publish.sh` hand-over artefacts (§A8)

Two gaps: (a) the script prints three publishing options to stdout but never
**writes** `workspace/wiki/PUBLISH.md`, which `STATE.md.tmpl` and `PROMPT.md` both
reference — on context loss, stdout is gone and the file is not; (b) when the wiki
repo does not exist yet (401) the script correctly `git init`s on `master`, but
leaves `.git/config` **without** `[remote "origin"]`, which `PITFALLS.md` §A3
predicts and even gives a recipe for.

Make the script (1) always write `PUBLISH.md` — the same text as stdout plus the
actual clone/push status, the commit SHA and the `git bundle verify` result;
(2) configure `origin` itself on a fresh init; (3) print "next: owner runs option
A/B/C".

**Acceptance:** after `publish.sh` there exist a commit, a verified bundle,
`PUBLISH.md`, and a configured remote — hand-over with no manual fix-ups.

---

## P2 — done

### P2-8  ✅ DONE · Phase-4 command-verification harness (§A9)

`SKILL.md`/`PROMPT.md` mandate "re-run the commands your wiki documents" (it caught
two factual errors in the reference run) but ship no harness, so every agent invents
one. Ready-made model: **`incoming/verify_commands_template.py`** (fresh clone →
every documented curl/recipe → **19/19** + evidence JSON). It also caught finding
#14 — manifest drift: `.gitignore` 397 B in the manifest vs 534 B in the commit, and
composer-generated `vendor/composer/*` never hashing equal to a fresh install.

Ship as `qa/verify_commands.py` plus a marking convention in wiki pages
(``` ```bash verify ``` or `<!-- verify: clean-clone -->`); the harness extracts
those blocks, substitutes placeholders (`$SITE` → the local instance), runs them and
compares the documented expected output (the line after `# →`).

**Acceptance:** on the reporter's wiki the harness runs ≥15 blocks with no manual
preparation and catches a substituted expected output in at least one synthetic case.

### P2-9  ✅ DONE · Multi-layout probing and a `flow` primitive (§A4)

`webapp_probe.py` assumes one instance and one `--entry`. MD.Scribe has **two**
deployment layouts (docroot `public/` with a router vs docroot at root for the v2
shims), needing two staged servers in one run; `ServedApp` allows this, the CLI does
not. Worse, the first "successful" 200 on `/md.php` in layout A was the **router's
fall-through to the home page** — a classic silently-wrong result caught only by
response size.

Admin flows are also strictly ordered (setup → login → dashboard token → actions),
while the batteries are order-independent, so the reporter wrote an imperative
driver: **`incoming/probe_mdscribe_example.py`** (1571 lines, 249 checks, 2 layouts,
JSON+MD evidence — the kit's evidence shape preserved).

Ship: (1) an `AGENTS.md` pattern — "multi-layout subject: probe each layout as its
own `ServedApp`; **never trust a 200 without a body marker**"; (2) optionally a
`probe.flow([...steps])` primitive sharing one `SessionClient` with end-to-end
evidence; (3) expose `--serve-cmd` on the `webapp_probe.py` CLI (today it is only
reachable via the module API).

**Acceptance:** documented pattern + worked example; `--new-suite NAME` scaffolds a
skeleton including a flow section.

### P2-10  ✅ DONE · `examples/run2-mdscribe/` (§F item 10)

The MD.Scribe artefacts as a **second** reference run — valuable precisely because it
is a different subject shape (admin panel, two layouts, sessions/CSRF) from
MD.Viewer. Contents: research files, probe evidence, and three sample pages
(Security Hardening Guide, Markdown Extensions Matrix, Troubleshooting). Source
material: `incoming/probe_mdscribe_example.py` and the reporter's workspace layout
described in `README.md` §"Как воспроизвести".

### P2-11  ✅ DONE · `write_evidence` helper (§A10)

Final evidence write raised `FileNotFoundError` while in-process `parent.is_dir()`
printed `False`, yet the shell saw and wrote the same directory in the same second.
Reproducible inside one long script after a series of spawn/kill cycles
(`setsid` + `killpg`); a minimal repro outside the script works. Cause unknown
(sandbox FS layer). Recorded as `PITFALLS.md` §B11.

Add a `write_evidence(path, payload)` helper used by every kit tool: on `OSError`
retry into `<kit>/workspace-fallback/`, print the diagnosis, and never let the last
line of a long probe be the only write of its evidence.

---

## Items explicitly NOT to change (§B of the report)

The reporter verified these worked under fire — do not "improve" them:

`PITFALLS` A1–A3 (no stale port, no lost file; `.git/config` rebuilt by recipe) ·
C1 spaces-in-filenames (252 wiki-links, 0 broken) · C5 + the QA slugger (0 anchor
errors; `github_slug` imported into `fix_toc`, so anchors were never hand-written) ·
C6/C7 (QA caught a `&action` in a mermaid label; no nested-fence failures even with
4-backtick examples) · `--self-test` (proved the checker could fail before the first
clean run, which is what made "0 errors" meaningful) · `repo_scan.py --brief`
(two minutes to orientation; tags/license/extra-clauses, deps, entry points, external
hosts, security signals, ini keys — all used verbatim) · `publish.sh` under a 401
(behaved exactly as documented) · `templates` ban/terms + §D6 (caught 10 real
drafting problems; `_tuning_log` in `terms.json` is the right pattern) ·
STATE/PROGRESS/research discipline (survived a hard interrupt) · `PROMPT.md` item 16
(the honest "no swarm of agents" wording).

---

## Readiness criterion for the whole package (§F, verbatim intent)

> The next agent, on a PHP subject with an admin panel and two deployment layouts,
> completes Phase 1 **without hand-writing an HTTP client or installers**, Phase 3
> **without hand-written anchors and with git snapshots at phase boundaries**,
> Phase 4 **with a harness**, and QA **without rephrasing legitimate quotes and
> negations**.

After v1.1.0 the Phase 1 and Phase 3 halves are satisfied. P1-4 closes the installer
gap, P1-5 the QA-rephrasing gap, P2-8 the Phase 4 harness, P2-9 the multi-layout
pattern.

---

## Working notes for whoever continues

- **Extract code from `UNPACK.MD` with CommonMark fence rules** — pure closing line,
  same character, rank ≥ opener. A first attempt that measured rank as the length of
  the whole opener line (```` ```sha256 ```` → 9) swallowed the rest of the document.
  This is the same class of bug `qa_wiki.py` checks for in wiki pages.
- The extracted sources are in `workspace/skill/incoming/`: `aggregate_sources.py`,
  `fix_toc.py` (already shipped), `probe_mdscribe_example.py`,
  `proposed_req_additions.py` (already shipped as `lib/session.py`),
  `verify_commands_template.py`, `mirror.sh`, `MANIFEST.sha256`, `_correct_report.py`.
- **`.git` can vanish between commands in this sandbox.** It did, mid-session, after
  successful commits. Recovery that preserves history and the working tree:
  ```bash
  git init -q -b main
  git fetch -q ../github-wiki-llm-writer.bundle main
  git reset -q --soft FETCH_HEAD      # HEAD moves, working tree and index untouched
  git add -A && git commit
  ```
  Keep the bundle fresh after every commit — it is the only thing that made this
  recoverable. Run `setup/snapshot.sh` at phase boundaries for the same reason.
- Commits must be authored as `Mikhail Deynekin <Mikhail@Deynekin.com>`, with
  `GIT_AUTHOR_*`/`GIT_COMMITTER_*` unset via `env -u` (they override `-c user.name`),
  and verified afterwards with `git log -1 --format='%an <%ae> | %cn <%ce>'`.
