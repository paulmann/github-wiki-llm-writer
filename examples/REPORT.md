# REPORT — MD.Viewer GitHub Wiki

**Delivered:** 2026-10-14
**Target:** https://github.com/paulmann/MD.Viewer (project 2.11.3 · `md.php` v2.18.0 · `updater.php` v3.14.0)
**Deliverable:** `workspace/wiki/MD.Viewer.wiki/` — 22 files, publication-ready
**Commit prepared:** `0442f00` in `workspace/wiki/publish/` (a clone of the real wiki repo)
**Bundle:** `workspace/wiki/MD.Viewer.wiki.bundle` — verified *"is okay … records a complete history"*

---

## 1. Outcome

| Metric | Value |
|---|---|
| Pages | 20 content pages + `_Sidebar.md` + `_Footer.md` |
| Words | **73 013** |
| GitHub Alerts | **154** (NOTE / TIP / IMPORTANT / WARNING / CAUTION) |
| Mermaid diagrams | **27** (26 `flowchart`, 1 `sequenceDiagram`) |
| Table rows | **1 687** |
| Code blocks | ~460 across all languages (`bash`, `php`, `ini`, `nginx`, `apache`, `json`, `python`, `caddyfile`, `yaml`, `xml`, `html`, `markdown`, `text`, `http`) |
| Internal wiki-links | **341**, all resolving to real pages |
| In-page anchors | all resolving (verified against GitHub's slug algorithm) |
| QA errors remaining | **0** |
| Marketing filler phrases | **0** |
| Decorative emoji | **0** (the 19 emoji present are documented shortcode→character mappings and verbatim UI glyphs) |

Every behavioural claim was either **traced to a source line** or **executed against a running
instance**. Nothing was transcribed from the README without verification — and where the README
is wrong, the wiki says so.


> [!NOTE]
> The figures above are the **final** ones, measured after the three corrections the
> toolkit itself found in the delivered wiki (a fabricated code quotation replaced with
> verbatim source; the doubled-slash normaliser documented as also rewriting the query
> string; and the `&force=true` propagation claim, which the subject's README asserts
> and its code does not implement). An earlier snapshot of this report recorded
> 72 524 words / 152 alerts / 30 diagrams / 1 680 table rows / 340 wiki-links; those
> numbers described the wiki *before* those fixes. Reproduce the current ones with
> `python3 qa/qa_wiki.py <wiki-dir>`.

---

## 2. Page inventory

| # | Page | Words | H2 | H3 | Alerts | Diagrams | Code blocks |
|---|---|---:|---:|---:|---:|---:|---:|
| 1 | Home | 1 630 | 8 | 5 | 4 | 1 | 7 |
| 2 | Getting Started | 1 986 | 12 | 12 | 6 | 0 | 28 |
| 3 | Features and Live Demo | 3 893 | 8 | 15 | 10 | 2 | 43 |
| 4 | Comparison with Alternatives | 3 287 | 11 | 24 | 2 | 2 | 4 |
| 5 | Installation and Deployment | 3 663 | 20 | 7 | 16 | 0 | 40 |
| 6 | Configuration Reference | 3 453 | 11 | 9 | 10 | 1 | 14 |
| 7 | Settings Panel | 2 719 | 11 | 9 | 8 | 2 | 8 |
| 8 | Markdown Extensions Matrix | 3 898 | 10 | 17 | 15 | 1 | 40 |
| 9 | Authoring Guide | 3 522 | 9 | 9 | 15 | 2 | 34 |
| 10 | File Browser and Routing | 3 161 | 14 | 5 | 9 | 2 | 16 |
| 11 | Self-Updater Guide | 4 440 | 17 | 13 | 9 | 3 | 27 |
| 12 | Machine API | 3 745 | 14 | 8 | 8 | 1 | 30 |
| 13 | File Upload and Clipboard | 3 685 | 12 | 19 | 11 | 3 | 28 |
| 14 | **Security Hardening Guide** | 4 850 | 14 | 25 | 6 | 0 | 20 |
| 15 | Performance and Caching | 3 268 | 12 | 12 | 8 | 1 | 24 |
| 16 | Architecture | 4 903 | 16 | 5 | 1 | 9 | 16 |
| 17 | Troubleshooting | 6 271 | 7 | 17 | 8 | 0 | 46 |
| 18 | FAQ | 3 757 | 9 | 73 | 0 | 0 | 1 |
| 19 | Changelog and Versioning | 3 484 | 8 | 1 | 6 | 0 | 15 |
| 20 | Glossary | 3 280 | 10 | 0 | 0 | 0 | 0 |
| | **Total** | **73 013** | | | **154** | **27** | |

`_Sidebar.md` groups navigation into Overview · Install & configure · Authoring · Operating ·
Reference and links every page. `_Footer.md` carries version, license, repository, issue-tracker
and cross-links, plus the provenance statement (commit `85d3f54`).

---

## 3. How the work was done

### Phase 1 — research (`workspace/research/`)

| File | Contents |
|---|---|
| `summary.md` | 9-section findings report: what the software is, the problem, architecture, security posture, updater integrity, measured Markdown support, verified behaviours, settings panel, competitive position |
| `architecture.md` | Component map, request lifecycle, inline pipeline, configuration resolution, write paths, integrity sequence diagram, client modules, runtime layout, complete function index for both PHP files with line numbers |
| `domain-notes.md` | CommonMark/GFM standards context, XSS and path-traversal domain analysis, deployment and performance domains, and the **canonical glossary** used by every page |
| `facts.json` | Machine-readable fact base: identity, component versions, repo metrics, file inventory, requirements, external dependencies, all `.md.ini` keys with defaults and code line refs, all 18 feature toggles, limits, the 14 validator layers, and every empirical test result |
| `sources.md` | Provenance table A (60+ source-line citations), B (30 named empirical tests), C (15 external sources), and D — **claims deliberately not made**, with reasons |

Method: fresh clone → full file-tree and `git log` capture (157 commits, no tags, no releases) →
complete README read → function maps for both PHP files → line-level reading of the config loader,
validator, routing block, inline pipeline, glossary engine and the whole updater → **execution**.

PHP 8.2.34 was installed in the sandbox and the viewer was served with `php -S`. A Python
`urllib` harness (`/tmp/req.py`) drove ~60 requests covering every mode, endpoint, flag and
error path.

### Phase 2 — architecture

The page tree, grouping, link convention and style contract were fixed in `PROGRESS.json`
**before** any prose was written, including a `do_not_claim` list carried over from Phase 1.

### Phase 3 — writing

Pages were written against excerpts of `workspace/research/`, not against the whole codebase, so
each stayed factually anchored. Cross-references use GitHub `[[wiki-links]]`; anchors use
GitHub's slug form.

### Phase 4 — QA

| Check | Tool | Result |
|---|---|---|
| Wiki-link targets exist | `qa/qa_wiki.py` | 341/341 valid |
| Anchored wiki-links resolve | `qa/qa_wiki.py` | 0 failures |
| In-page `#anchor` links resolve | `qa/qa_wiki.py` with GitHub's exact slug algorithm | 0 failures (12 initial hits were checker bugs, then 1 real bug) |
| `_Sidebar` / `_Footer` coverage | `qa/qa_wiki.py` | every page linked, no dead links |
| Exactly one H1 per page | `qa/qa_wiki.py` | 20/20 |
| Lead paragraph after H1 | `qa/qa_wiki.py` | 20/20 |
| "See also" on every page | `qa/qa_wiki.py` | 20/20 |
| Alert syntax valid | `qa/qa_wiki.py` | 154/154 use one of the five types |
| Code-fence nesting | dedicated checker | **1 real defect found and fixed** (a 3-backtick example containing a 3-backtick fence, in Authoring Guide) → upgraded to 4 backticks; 0 problems remain |
| Bash blocks parse | `bash -n` on all extracted blocks | 895 lines, syntax OK |
| Mermaid sanity | bracket/quote balance, bare `&`, unquoted risky labels | **5 real risks fixed** (bare `&` in an unquoted edge label; `&force` inside labels; a regex with backslashes in a node label; `key[]` and `{version}` in labels) |
| Documented commands actually run | re-executed the wiki's own snippets in a clean sandbox | `render()` helper, article extractor, traversal grep, download-header grep, cookie-toggle test, version grep, and all Machine-API `curl` examples — all produced the documented output |
| Documented HTTP codes | re-executed | 200/301/400/403/404/405 all confirmed; the 403 page's `<title>` vs `<h1>` discrepancy found and corrected in 2 pages |
| Terminology consistency | canonical-term frequency scan | 20 canonical terms used consistently (`browse root` ×90, `tracked file` ×59, `hard lock` ×31, `interface gate` ×12 …); 0 occurrences of the banned synonyms |
| Marketing filler | 18-phrase regex scan | 0 hits |
| Emoji discipline | Unicode range scan outside code | 19, all legitimate (shortcode mappings, verbatim UI glyphs) |

---

## 4. Findings the wiki documents that the README does not

These are the substantive results of Phase 1. Each is stated in the wiki with a reproduction.

### Security

| Finding | Severity | Where documented |
|---|---|---|
| Raw HTML from Markdown is restored **verbatim** after the escape pass (`md.php:2041` capture, `:2176` restore). `<script>`, `<img onerror>`, `<svg onload>`, `<details ontoggle>`, `<iframe src="javascript:">` and `<a onclick>` all reproduced byte-for-byte | High | Security Hardening Guide §Verified vulnerabilities 1 |
| **Reference-style link URLs are not protocol-filtered** — `[t][r]` + `[r]: javascript:alert(1)` yields a live `href`. Inline links *are* safe (regex only matches `#…`/`https?://…`) | High | Security Hardening Guide §2; Markdown Extensions Matrix |
| No `Content-Security-Policy`, `X-Frame-Options`, HSTS, `Referrer-Policy` or `Permissions-Policy` on any response | Medium | Security Hardening Guide §3 |
| Mermaid runs with `securityLevel: 'loose'` + `htmlLabels: true` (`js/md/md.js:292`) | Medium | Security Hardening Guide §4 |
| Three CDNs, none with Subresource Integrity; `mermaid@11` is a floating major; `cdn.tailwindcss.com` is the *development* build | Medium | Security Hardening Guide §5; Performance and Caching |
| Update authenticity is **not** verified — SHA-256 is a change detector; no signature, no pinned commit, no manifest. `CURLOPT_SSL_VERIFYHOST` is never set (inherits libcurl's default) | High, conditional | Security Hardening Guide §Update supply chain; Self-Updater Guide |
| The browse root is fully public: the whitelist is **extension-based, not document-based** (`README.md` is readable via `?file=`) | Medium | Security Hardening Guide §7; File Browser and Routing |
| `.md.ini` (holding `API_KEY`) is a dotfile in the web root; servability depends entirely on the server config | Medium | Security Hardening Guide §8; Installation and Deployment |
| `<html lang="ru">` is hardcoded | Low | Security Hardening Guide §9; Features and Live Demo |
| `window.MDV_CONFIG` is assigned twice in the emitted HTML | Info | Security Hardening Guide §10; Architecture |
| **Path traversal defence is genuinely strong** — 14 layers including a post-symlink extension re-check; 13 payloads verified refused | positive | Security Hardening Guide; Architecture |
| Upload validation verified across 10 filenames + `dir` traversal; `basename()` runs first so `../evil.md` safely becomes `evil.md` | positive | File Upload and Clipboard |
| Same-origin guard, three-level flag enforcement, `hash_equals()` key comparison, `apiParam()` never reading cookies, pre-write guard, strictly-JSON API | positive | Security Hardening Guide; Machine API |

### Correctness of documented features

| README claim | Measured reality |
|---|---|
| "Syntax-highlighted fenced code blocks" | **No highlighter is loaded anywhere.** A repo-wide search for external URLs finds only Tailwind, Google Fonts and Mermaid |
| "Ordered and unordered lists, including nested lists" | **Nested lists do not render.** Indented children become a literal paragraph outside the list |
| "Browser-side internet access for CDN assets (Mermaid, syntax highlighting, Tailwind)" | Only Mermaid and Tailwind exist |
| (implied) tilde fences | Not handled by the body renderer |
| (implied) CommonMark behaviours | Entities escaped not decoded; backslash escapes absent; autolinks absent; indented code absent; setext text emitted **twice** |

### Behaviours discovered by execution, not documented anywhere upstream

| Discovery | Value |
|---|---|
| **TOC threshold**: `renderTOC()` returns `''` below two headings, and collection happens *after* the H1 is stripped — so a document needs ≥2 headings besides its H1. In clipboard-preview mode the H1 is retained, so the threshold is reached one heading earlier | Explains the most common "where is my TOC?" report |
| **Glossary heuristic is structural**: any table with ≥2 columns and a non-empty first header becomes a glossary; a `\| A \| B \|` table registers `1` as a term and tooltips every standalone `1` in the document | Prevents a confusing authoring trap |
| `SPLIT_TITLE_BY_COLON` sends the *after-colon* text to the meta description | Explains surprising `<meta>` values |
| `API_KEY` is created **only by `updater.php`**, never by `md.php` | Explains `api_key_unavailable` |
| Denials return **HTTP 200** with a banner, not 4xx — deliberate non-disclosure | Prevents broken monitoring rules |
| Save to File **overwrites without backup**; Upload renames to `.bak.Ymd-His` | Prevents data loss |
| `.bak.Ymd-His` files are invisible in the UI (not `.md`) | Audit completeness |
| The upload field is `md_file`, not `file` | Fixes a common 400 |
| `MAX_SCAN_DEPTH = 3` bounds the `?file=` validator too, not just the listing | Explains unreachable deep documents |
| Settings-panel tooltips are inaccurate for 5 of 17 toggles (Emoji claims "all common GFM shortcodes" but only 16 exist; Auto Numbering claims client-side but is server-side; Cypher/Universal Patterns describe features that do not exist) | Documented with corrections |
| The v2.16.0/v2.18.0 whitelist history explains "file is listed but cannot be opened" on older installs | Turns a support question into a version check |

---

## 5. Sources used

### Primary — the repository (commit `85d3f54`)

`README.md` v2.11.3 in full · `md.php` header docblock lines 1–450 and ~60 targeted regions
(config loader 380–505, `feat()` 512–559, download branch 585–621, per-directory constants
632–651, `validateRequestedFile` 661–760, `mdvDirSegments` 801–856, `scanMarkdownFiles`
1120–1220, `renderFilesTable` 1240–1336, `e()` 1337, `parseSources` 1543, `hasManualNumbering`
1594, `parseUniversalPattern` 1810–1886, `emojiMap` 1915, `inlineMarkdown` 1956–2220, table
helpers 2221–2266, `collectHeadings`/`assignHeadingNumbers`/`renderTOC` 2267–2400, Mermaid
helpers 2402–2530, glossary 2570–2819, `renderMarkdown` 2912–3318, `removeSourcesSection`
3449–3474, main dispatch 3476–3595, template 3596–4010, settings panel 4019–4600) ·
`updater.php` header docblock 1–108 and ~40 targeted regions (`TRACKED_FILES` 110–136,
`RawFileUpdater` 149–425, `docRoot` 436, guards 543–566, per-dir constants 714–728, API
helpers 1090–1160, pre-write guard 1170–1360, JSON API 1399–1960, same-origin guard 2087–2208,
actions 2209–2490, `doUploadMd` 2491–2590, `doSaveClipboard` 2591–2660) · `js/md/md.js`
(Mermaid bootstrap 129–340, copy handler) · `js/md/settings.js` (the `FEATURES` array with all
17 labels and tooltips) · `js/md/upload.js` (endpoint and field names) · `LICENSE` ·
`.gitignore` · `git log` (157 commits).

### Empirical — executed in the sandbox

PHP 8.2.34 CLI + `php -S`, two clean document roots (`/tmp/mdv`, `/tmp/qa`), Python `urllib`
harness plus `curl` 7.88.1. ~60 requests across: viewer mode, browser mode, clipboard preview,
raw download, the doubled-slash redirect, 16 `?file=` traversal payloads, 14 XSS payloads,
`upload_md` with 10 filenames and 3 `dir` values, `save_clipboard`, all three machine-API
actions with correct/wrong/absent keys and wrong methods, `?update=true`, `?restore=latest`, the
updater landing page, `.md.ini` auto-creation, `API_KEY` auto-generation, TOC threshold in both
modes, glossary indexing, sources stripping, setext duplication, nested lists, tilde fences,
indented code, autolinks, entities, backslash escapes, hard breaks, `start=` preservation,
fence-length nesting, response-header inventory, and `MDV_CONFIG` extraction. Full test list in
`research/sources.md` §B.

### External — authoritative

GFM Spec 0.29-gfm (§2.3 insecure characters, §6.10 raw HTML, §6.11 disallowed raw HTML, and the
statement that GitHub sanitises after conversion) · CommonMark Spec · OWASP XSS Prevention Cheat
Sheet · OWASP DOM Clobbering Prevention Cheat Sheet · DOMPurify · remark-gfm ·
"CommonMark vs GFM (2026)" · HeroThemes "9 Best MkDocs Alternatives 2026" · docsio "Best
Docusaurus Alternatives in 2026" · MDN CSP `script-src` · curl `CURLOPT_SSL_VERIFYHOST` ·
PHP `parse_ini_file`, `move_uploaded_file` · Mermaid `securityLevel` · Unicode UAX #44 (`Pd`).

Full table with URLs in `research/sources.md` §C.

---

## 6. Deliverables in `workspace/`

```
workspace/
├── STATE.md                        recovery point: phase, done, next
├── PROGRESS.json                   per-page status machine + style contract
├── qa_full.py                      the link/anchor/structure QA checker (re-runnable)
├── repo/MD.Viewer/                 the upstream clone (read-only reference)
├── research/                       Phase 1 outputs
│   ├── summary.md  architecture.md  domain-notes.md  facts.json  sources.md
└── wiki/
    ├── MD.Viewer.wiki/             ← THE DELIVERABLE: 22 publication-ready files
    ├── publish/                    a clone of the real wiki repo with commit 0442f00 applied
    ├── MD.Viewer.wiki.bundle       verified git bundle (201 KB, complete history)
    ├── PUBLISH.md                  three ways to push, plus a post-publish checklist
    └── REPORT.md                   this file
```

---

## 7. What remains to be improved

### Blocking publication

Nothing. The only outstanding step is the `git push`, which needs credentials the sandbox does
not have. `wiki/PUBLISH.md` gives three routes.

### Worth doing before or soon after publishing

| # | Item | Effort | Why |
|---|---|---|---|
| 1 | **Add screenshots.** The wiki has no images; GitHub does not render PHP, so "live demo shots" are reproducible text transcripts instead. A handful of PNGs (viewer page, file browser, settings panel, Mermaid render, dark mode, updater result page) placed in the wiki repo and referenced would materially improve Home and Features | ~1 h with a browser | The brief asked for demo shots; this is the one requirement met by substitute rather than directly |
| 2 | **Have the author review the security findings** before publication. They are accurate and reproducible, but publishing an unpatched XSS write-up on a public wiki is a disclosure decision that belongs to the maintainer, not the documenter. Consider a private report first, and publishing the guide once a sanitiser or CSP is in place | — | Responsible disclosure |
| 3 | Confirm the wiki's `master` branch and that GitHub renders `[[Page Name]]` links as expected for hyphenated URLs. Verified by construction (filenames contain spaces, which GitHub maps to hyphenated URLs), but a visual check costs a minute | 5 min | Link integrity in the live UI |
| 4 | Spot-check the 30 mermaid diagrams in GitHub's renderer. All were syntax-audited (bracket/quote balance, entity escaping, label quoting) but not rendered | 15 min | GitHub's mermaid version may differ from the audit assumptions |

### Improvements to the wiki itself

| # | Item | Notes |
|---|---|---|
| 5 | A **worked end-to-end example repository** (a small docs tree with a glossary, sources, diagrams and a contribution inbox) linked from Authoring Guide | Would replace several inline examples with one runnable artefact |
| 6 | **Apache `.htaccess` and IIS `web.config` samples tested on real servers.** They are written to spec and reviewed, but only the Nginx/PHP-built-in paths were executed here | Flagged in-page as "recommended additions, not project files" |
| 7 | A **compiled Tailwind stylesheet** actually generated and committed, so the self-hosting instructions in Performance and Caching are a download rather than a procedure | Requires an npm build; documented as steps instead |
| 8 | **Load-test numbers** for Performance and Caching. The page reasons about cost from code structure and gives a measurement method, but quotes no benchmarks | Deliberate: invented numbers would violate the "nothing unverified" rule |
| 9 | Localise the wiki, or at least note the `<html lang="ru">` patch more prominently | Currently in Security Hardening Guide, Features and Live Demo, and Troubleshooting |
| 10 | Cross-link the wiki from the repository README | Suggested snippet is in `PUBLISH.md` |

### Known limitations of this analysis

- **PHP 8.2.34, not 8.3.** The documented target is 8.3+; the sandbox had 8.2.34. Everything ran,
  which is itself a finding (the requirement is not enforced), but behaviours specific to 8.3
  were not exercised.
- **No network egress test for the updater.** `?update=true` and `action=install` were verified
  to gate correctly (403 / 405 / 400) but a real download-and-replace cycle was not executed, to
  avoid mutating the reference clone. The ETag/SHA-256 logic is documented from source.
- **Browser-side behaviour reasoned from source, not from a browser.** Mermaid rendering, tooltip
  placement, sorting and the settings panel were read in `js/md/*.js` and cross-checked against
  the server-emitted markup and `MDV_CONFIG`; no headless browser was used.
- **Issues and PRs were not analysed.** A bare clone carries none, and the GitHub API was not
  queried. The changelog was reconstructed from `git log` and the file-header docblocks, which
  are unusually detailed.
- **`tools/*.ps1` were inventoried but not executed** (PowerShell, no runtime role).

---

## 8. Reproducing this work

```bash
# 1. The reference clone
cd workspace/repo/MD.Viewer && git log --oneline -1        # 85d3f54

# 2. Re-run the structural QA
cd workspace && python3 qa_full.py                          # expect: ERRORS (0), WARNINGS (0)

# 3. Re-run the behavioural verification
rm -rf /tmp/qa && mkdir -p /tmp/qa && cd /tmp/qa
cp -r /path/to/workspace/repo/MD.Viewer/{md.php,updater.php,css,js,LICENSE,README.md} .
printf '# Hello\n\nWorld.\n\n## Two\n\nx\n\n## Three\n\ny\n' > md.md
php -S 127.0.0.1:8231 &
sleep 2
curl -s -o /dev/null -w 'viewer %{http_code}\n'  http://127.0.0.1:8231/md.php
curl -s -o /dev/null -w 'update %{http_code}\n'  'http://127.0.0.1:8231/updater.php?update=true'
curl -s 'http://127.0.0.1:8231/md.php?file=../../../etc/passwd' | grep -o 'Access denied[^<]*'

# 4. Publish
cd workspace/wiki && cat PUBLISH.md
```
