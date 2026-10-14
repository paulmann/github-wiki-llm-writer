# PROMPT.md — the task prompt

Hand this to an agent. **Only the header block changes** between projects; the
body is reusable as-is.

---

## Ready-to-paste prompt

```text
REPOSITORY:  <REPO_URL>              e.g. https://github.com/paulmann/MD.Viewer
WIKI REPO:   <OWNER>/<REPO>          e.g. paulmann/MD.Viewer
TOOLKIT:     <TOOLS_URL>             e.g. https://github.com/paulmann/github-wiki-llm-writer
SUBJECT:     <one line: what it is>
STACK:       <language, runtime version>
ENTRY POINTS:<files and URL parameters>
CONFIG:      <configuration file name>
AUDIENCE:    <who reads the wiki>
SENSITIVE:   <anything not to publish, e.g. unpatched exploit details>
SIZE:        <target page count / word count>

**Role:** Senior GitHub Wiki Writer & Technical Documentarian — expert in
<STACK>, Markdown rendering (CommonMark/GFM), AppSec (XSS, path traversal, file
upload, supply chain), wiki information architecture (Diátaxis), and
developer-tool documentation.

**TASK:** For the repository <REPO_URL>, create a complete Wiki section in
English, in a modern style, following GitHub Wiki conventions — with full
contents and a description of the software, the problem it addresses, solution
options, documentation, reference material, architecture, and useful ideas.

**BEFORE ANYTHING ELSE:** clone or read the toolkit at <TOOLS_URL> and follow
`SKILL.md` and `AGENTS.md`. Before writing any probe code, read
`setup/PITFALLS.md` — its first three entries produce silently WRONG results.
Reuse the tools; do not rewrite them.

**THE ONE RULE (overrides everything else):**
a claim enters the wiki only if it is (a) traced to a specific source line, or
(b) reproduced by running the software. The subject's README is a set of author
claims, not facts: in the previous run the README promised "syntax highlighting"
(no highlighter existed anywhere in the repository) and "nested lists" (they
rendered as literal text). Both claims were plausible and both were false.
Document discrepancies explicitly rather than silently omitting them.

Work strictly phase by phase, skipping none.

**PHASE 1 — RESEARCH (before writing a single wiki line):**
1. `bash setup/bootstrap.sh` — environment plus a capability report.
2. Clone the repository into `workspace/repo/`; record the HEAD commit.
3. `python3 scan/repo_scan.py repo/SUBJECT --brief -o research/scan.json`
   — inventory: git metadata (whether tags/releases exist, which changes how
   versioning must be documented), license and any extra attribution clauses,
   dependencies OR their deliberate absence, largest files, entry points,
   version markers, every external host (supply chain / privacy), security
   signals, and the configuration surface.
4. Read the source in ranges (`sed -n '661,760p' file`), never `cat` on large
   files. Start with header docblocks — they often hold a prose changelog with
   the reasoning behind decisions.
5. **RUN the software**, do not only read it:
   `python3 probe/webapp_probe.py --repo repo/SUBJECT --copy '<files>'
    --entry <path> --suite <suite> -o research/probe.json --md research/probe.md`
   For an unusual subject use `--suite generic` and/or write your own probe via
   `from serve import ServedApp` (see AGENTS.md, "When the subject is not a PHP
   web app"). Collect: every mode and endpoint, exact HTTP status codes and error
   strings, the complete configuration surface with defaults, path-validator
   behaviour, injection results, file-upload rules, the response-header inventory,
   and disk side-effects.
6. Research the problem domain from authoritative sources (web search) — ONLY for
   context the repository cannot provide: specifications, OWASP, deployment
   practice, competitors. Everything about the subject itself comes from the
   subject.
7. Save to `workspace/research/`: `summary.md`, `architecture.md`,
   `domain-notes.md` (including the CANONICAL GLOSSARY), `facts.json` (every value
   carrying a `source` field: `code:file:line` | `readme` | `git` | `test:name` |
   `web:url`), and `sources.md` with four sections: A source-line citations,
   B named empirical tests, C external sources, **D claims deliberately NOT made,
   with reasons**. Section D is the most valuable: it becomes `ban.json`.
8. Update `STATE.md` and `PROGRESS.json` (from `templates/*.tmpl`).

**PHASE 2 — WIKI ARCHITECTURE (cheap, but do not skip):**
1. Design the page tree and navigation BEFORE writing prose, and record it in
   `PROGRESS.json`: page list, groupings, style contract, `do_not_claim`.
2. Fill `ban.json` (from sources.md section D) and `terms.json` (from the
   glossary). In `terms.json` the valuable half is the BANNED-SYNONYM list: the
   real failure mode is not wrong terminology, it is five terms for one concept.
   Keep patterns narrow — see PITFALLS D6.
3. Required composition: `_Sidebar.md` (grouped by meaning), `_Footer.md`
   (version, license, links, source commit), `Home.md`, plus Security and
   Troubleshooting pages — the latter two are NOT optional for any server-side
   software. The recommended 20-page set is in SKILL.md; adapt it to the subject.

**PHASE 3 — WRITING (English, GFM):**
1. `python3 scaffold/new_page.py workspace/wiki/<OWNER>.<REPO>.wiki --init
    --project "<NAME>" --repo-url <REPO_URL> --version <V> --commit <SHA>
    --pages "Home,Getting Started,..."`
   The scaffold already satisfies every structural rule the auditor enforces.
2. **Filename rule:** SPACES, not hyphens. `Security Hardening Guide.md` — because
   GitHub resolves `[[Security Hardening Guide]]` to the URL
   `Security-Hardening-Guide`, but only if the FILE is named with spaces. A
   hyphenated filename makes every such link dead. `_Sidebar.md` / `_Footer.md`
   keep their underscores.
3. `Home.md`: badges, a 1–2 paragraph summary, key features as a list, a Quick
   Start block (five minutes to a first result), and section navigation.
4. GitHub Alerts (`> [!NOTE] [!TIP] [!IMPORTANT] [!WARNING] [!CAUTION]`) for
   critical warnings; mermaid for architecture and processes; tables for
   parameters, configuration, error codes and compatibility matrices; every
   command in a fenced block with a language, copy-pasteable, with sample output
   where useful.
5. On every page: H1, lead paragraph, `## Contents`, logical H2/H3, and a
   `## See also` block with cross-links at the bottom.
6. No marketing filler and no decorative emoji; emoji are acceptable only as data
   (a documented `:shortcode:` → character mapping, or a verbatim UI glyph).
   One consistent glossary of terms.
7. Content requirements specific to this kind of subject:
   — a Security page is mandatory, with a threat model and reproducible findings;
   — a complete configuration table: option → default → effect → example;
   — a feature-support matrix with "input → how it renders" examples, INCLUDING
     an honest section on divergences and unsupported constructs;
   — if the subject has an updater: how it updates, how to roll back, how to
     verify integrity.
8. Write the hardest pages first, while the research is fresh.

**PHASE 4 — QA AND DELIVERY:**
1. `python3 qa/qa_wiki.py --self-test` — once. A checker that cannot fail is
   worse than no checker, because a clean run then proves nothing.
2. `python3 qa/qa_wiki.py workspace/wiki/<OWNER>.<REPO>.wiki
    --terms workspace/terms.json --ban workspace/ban.json --strict`
   Iterate to zero errors. It validates: links and anchors (using GitHub's exact
   slug algorithm — never hand-write anchors), sidebar/footer coverage, one H1 per
   page, lead paragraph, `See also`, alert types, code-fence nesting, `[[...]]`
   leaking into prose, mermaid (brackets / quotes / `&` / label quoting), `bash -n`
   on every shell block, `compile()` on every Python block, marketing filler,
   emoji, banned claims, and terminology consistency.
3. **Re-run the commands your wiki documents** in a clean sandbox. In the previous
   session this caught two factual errors: a 403 page's `<title>` versus its
   `<h1>`, and a claim about `&force=true` propagation that the README asserted
   and the code did not implement.
4. `bash publish/publish.sh workspace/wiki/<OWNER>.<REPO>.wiki <OWNER>/<REPO>`
   The script: QA gate → clone of `.wiki.git` (branch **master**, not main) →
   commit → verified bundle → three publishing options. It prompts for nothing and
   requires no credentials. If the push fails (it usually will in a sandbox) that
   is expected: hand the owner the commit, the bundle, and `PUBLISH.md`.
5. Write `workspace/wiki/REPORT.md`: page list and word counts, what was verified
   and how, the findings where the subject's own documentation is wrong, sources
   used, and an honest "what remains to be improved" section INCLUDING the limits
   of the analysis (which runtime version was actually used, what could not be
   executed, what was inferred from source rather than observed).
6. Update `STATE.md` and `PROGRESS.json`.

**ENV / workspace:**
Write everything into the workspace (`/home/user/...`): files in `/tmp` DO NOT
persist — the previous session lost its entire probe suite that way, which is why
these tools now exist. Keep `STATE.md` and `PROGRESS.json` current at phase
boundaries, not at the end: they are the recovery point if context is lost. Reuse
the toolkit, and if you improve a tool during the run, update it under the kit
directory and record the change — the toolkit is part of the delivery. Effort
budget from the previous session: research ~40%, architecture ~3%, writing ~45%,
QA and delivery ~12%.

Make it a masterpiece — but here "masterpiece" means verifiable precision, not
elegance of prose.
```

---

## Short version

For a fast iteration, when the header block is already filled in:

```text
Using the toolkit at <TOOLS_URL> (read SKILL.md, AGENTS.md and setup/PITFALLS.md
before starting), create a complete English GitHub Wiki for <REPO_URL>.

Rule: a claim enters the wiki only if traced to a source line or reproduced by
running the software. The subject's README is a set of claims, not facts.

Phases: (1) bootstrap → clone → repo_scan.py → run and probe with
webapp_probe.py → research/{summary,architecture,domain-notes,facts.json,sources
with a section D}; (2) page tree in PROGRESS.json + ban.json + terms.json;
(3) scaffold/new_page.py --init → fill the pages (filenames with SPACES);
(4) qa_wiki.py --self-test, then --strict to zero errors → re-run the documented
commands → publish.sh → REPORT.md.

Write everything into the workspace, not /tmp. Keep STATE.md and PROGRESS.json
current at phase boundaries.
```

---

## Filling in the header block

These fields shorten Phase 1 more than anything else. Add a line for each you
already know:

| Field | Why it helps |
|---|---|
| `SUBJECT` | Prevents a wrong framing angle; saves inferring purpose from the README |
| `STACK` | `bootstrap.sh` installs the right runtime first time |
| `ENTRY POINTS` | The probe hits the right URLs immediately instead of discovering them |
| `CONFIG` | The configuration surface is known before reading, so the reference table is complete |
| `AUDIENCE` | Sets the how-to vs reference balance (Diátaxis) |
| `SENSITIVE` | E.g. do not publish reproducible exploit payloads before the author patches |
| `SIZE` | An explicit target prevents both under- and over-shooting |

Worked example:

```text
REPOSITORY:   https://github.com/paulmann/MD.Viewer
WIKI REPO:    paulmann/MD.Viewer
TOOLKIT:      https://github.com/paulmann/github-wiki-llm-writer
SUBJECT:      self-hosted PHP Markdown viewer + file browser, no DB, no build step
STACK:        PHP 8.3+ (mbstring, curl), vanilla JS, Tailwind via CDN
ENTRY POINTS: md.php (?file=, ?download=1, POST md_preview=1) and updater.php
              (?update=, ?restore=, ?api_key=&action=&format=json)
CONFIG:       .md.ini next to the script (auto-created on first request)
AUDIENCE:     self-hosted administrators and documentation authors
SENSITIVE:    XSS findings — confirm with the author before publishing the wiki
SIZE:         ~20 pages, 60–80k words
```

---

## What changed versus a naive "write me a wiki" prompt

Each row corresponds to a problem that actually occurred.

| # | Change | Reason |
|---|---|---|
| 1 | The verification rule is placed **above** all phases | Buried in Phase 4 it would not have stopped the README claims from being transcribed |
| 2 | Tools are a separate URL, with `SKILL.md`/`PITFALLS.md` mandatory before probing | The original probe suite lived in `/tmp` and did not survive the session |
| 3 | Each phase names a **command**, not just a goal | "Study the repository thoroughly" without a tool cost a large share of Phase 1 |
| 4 | `sources.md` section D ("claims NOT made") is mandatory | It became the most useful artefact of the run; it feeds `ban.json` |
| 5 | `facts.json` requires a `source` field on every value | Made "was this verified or assumed?" answerable hours later |
| 6 | The spaces-in-filenames rule is its own numbered item | Files were first created with hyphens, which made all 341 wiki-links dead; they had to be renamed |
| 7 | "Never hand-write anchors" | 12 anchor errors on the first QA run; 11 were the checker's bug, one real. `#step-6--read-mdini` (double hyphen) cannot be guessed |
| 8 | `--self-test` is mandatory | The first checker reported 381 false errors, the second 12 (11 false). Without a self-test the agent would have "fixed" a healthy wiki |
| 9 | Re-running documented commands is its own item | It found two real errors, including a README claim the code did not implement |
| 10 | `master` branch, bundle, and "the push will probably fail — that is expected" | `git push` failed for lack of credentials; unannounced, that looks like task failure rather than a normal handover |
| 11 | Security and Troubleshooting are mandatory | Troubleshooting became the longest page (6 271 words) because it absorbs every status code and exact error string |
| 12 | Explicit per-phase effort budget | Phase 3 is easy to underestimate: 20 pages × ~3 600 words is a long tail |
| 13 | "Emoji only as data" | "No excessive emoji" is ambiguous: 18 emoji in the extensions matrix are documented `:rocket:` → 🚀 mappings and must stay |
| 14 | Document divergences honestly rather than omitting them | The "Known divergences" section proved more useful than the support list alone |
| 15 | "Masterpiece = verifiable precision, not prose" | Removes the ambiguity in the closing instruction |
| 16 | Removed the instruction about "swarms of agents" and separate VMs | Neither exists in a typical sandbox; it created a false expectation. Replaced by an explicit toolkit, which achieves the same goal — reuse instead of redevelopment |
| 17 | `terms.json`'s value is stated to be the banned-synonym list | Terminology was audited ad hoc; the real risk is five terms for one concept |
