# sources.md — provenance of every claim

## A. Primary sources (the repository itself)

Cloned 2026-10-13 to `workspace/repo/MD.Viewer`, commit `85d3f54`, branch `main`.

| Source | Used for |
|---|---|
| `README.md` (v2.11.3, 26 614 B) | Feature claims, `.md.ini` key table, updater modes, machine-API envelope, security table, tracked-file list, install instructions, Nginx sample |
| `md.php` header docblock (lines 1–450) | Release-by-release rationale for v2.9.0 → v2.18.0; the project's own security reasoning |
| `md.php:322–328` | Doubled-slash 301 normalisation |
| `md.php:380–505` | `.md.ini` load/create/append, `ALLOW_*` defines, `BROWSE_DIR` resolution |
| `md.php:512–559` | `feat()` and the 18 feature toggles |
| `md.php:562–566` | `MAX_FILE_PARAM_LENGTH` 255, `MAX_SCAN_DEPTH` 3, `MAX_FILES_SCAN` 10000 |
| `md.php:568–580` | `SORT_DEFAULT_KEY = 'modified'`, `SORT_DEFAULT_DIR = 'desc'` |
| `md.php:585–621` | Raw-download branch and its response headers |
| `md.php:632–651` | `MDV_PER_DIR_KEYS`, `MDV_INSTALL_KEYS`, `MDV_FLAG_DEFAULTS`, effective-flag defines |
| `md.php:661–760` | `validateRequestedFile()` — all 14 layers |
| `md.php:785–980` | `mdvInsideRoot`, `mdvDirSegments`, `mdvReadDirIni`, `mdvEffectiveFlags`, `mdvRequestedDir` |
| `md.php:1120–1220` | `scanMarkdownFiles()` — skip rules, depth, symlink containment |
| `md.php:1240–1336` | `renderFilesTable()` — columns, data attributes, download link |
| `md.php:1337–1340` | `e()` = `htmlspecialchars(ENT_QUOTES\|ENT_SUBSTITUTE, 'UTF-8')` |
| `md.php:1543–1573` | `parseSources()` and the sources regex |
| `md.php:1594+` | `hasManualNumbering()` and its documented match/non-match cases |
| `md.php:1810–1886` | `parseUniversalPattern()` incl. the v2.16.0 infinite-loop fix |
| `md.php:1915–1924` | `emojiMap()` — the complete 16-entry shortcode list |
| `md.php:1956–2220` | `inlineMarkdown()` — the whole 14-step inline pipeline, placeholder code points, and the raw-HTML capture/restore at 2041 and 2176 |
| `md.php:2267–2400` | `collectHeadings()`, `assignHeadingNumbers()`, `renderTOC()` (incl. the `count < 2` early return) |
| `md.php:2588–2624` | `expandGlossaryAliases()` — the `Base term (ALIAS)` syntax |
| `md.php:2626–2723` | `parseGlossaryTables()` — the "any table with a non-empty first header" heuristic |
| `md.php:2724–2819` | `applyGlossaryTooltipsToHtml()` — protected tag list, longest-first term sort, `data-gc="1"` guard |
| `md.php:2912–3318` | `renderMarkdown()` block loop; fence regex at 3139 |
| `md.php:3449–3474` | `removeSourcesSection()` — the four accepted heading names |
| `md.php:3476–3595` | Main dispatch: clipboard POST, `?file=`, default file, mode decision, render pipeline |
| `md.php:3596–4010` | HTML template: `<html lang="ru">`, Tailwind CDN, Google Fonts, `MDV_CONFIG`, hero, TOC slot, footer |
| `md.php:4019–4600` | Settings panel markup: section titles, `data-sp-width`, `data-sp-para`, `data-toolbar`, conditional sections |
| `updater.php` header docblock (lines 1–108) | Detection model, endpoint list, rules, and the v3.0.0 → v3.12.0 changelog |
| `updater.php:110–136` | `RAW_BASE`, `TRACKED_FILES` (11), `CONFLICT_SCAN_SKIP_DIRS`, `CONFLICT_SCAN_MAX_FILES` |
| `updater.php:149–425` | `RawFileUpdater`: `localHash`, `check`, `apply`, `backupTo`, `conditionalGet` (cURL options), `loadState`/`saveState`, `atomicReplace` |
| `updater.php:436–452` | `docRoot()` — the v3.10.1 subdirectory rule |
| `updater.php:543–566` | `requireAllowUpdate` / `requireAllowRestore` / `requireAllowIndexLink` |
| `updater.php:714–728` | Per-directory key constants and limits |
| `updater.php:1090–1160` | `jsonError`, `generateApiKey`, `apiKeyFromRequest`, `jsonApiRequested`, `apiParam`, `isTruthy`, `mdViewerVersion` |
| `updater.php:1170–1360` | `isManagedFile`, `writeBlockedReason`, `indexTargetFileNames`, `detectInstallConflicts`, `conflictCounts`, `conflictSummary`, `installDecision` |
| `updater.php:1399–1960` | `jsonApiSend`, `handleJsonApi`, `jsonApiDispatch`, `jsonApiStatus`, `jsonApiConflicts`, `jsonApiInstall`, two-phase bootstrap |
| `updater.php:2087–2208` | `hostFromUrl`, `requestHost`, `sameOriginViolation`, `requireSameOrigin` |
| `updater.php:2209–2490` | `doVersion`, `doBackups`, `doCheck`, `doApply`, `doRestore`, index-link actions |
| `updater.php:2491–2660` | `doUploadMd()` (field `md_file`, all filename rules, `.bak` rename) and `doSaveClipboard()` |
| `js/md/md.js:129–340` | Mermaid lazy-load from jsDelivr, `securityLevel: 'loose'`, `htmlLabels: true`, auto-repair, diagnostics |
| `js/md/settings.js` | The 17 rendered feature-toggle labels; cookie names |
| `LICENSE` | MIT text + the attribution clause requiring the copyright notice, permission notice and repository link in all copies |
| `.gitignore` | `.ragf/` local index exclusion |
| `git log` (157 commits) | Release cadence and the decision history behind each version |

## B. Empirical tests run in the sandbox

Environment: Debian bookworm, **PHP 8.2.34** CLI, `php -S 127.0.0.1:8123`, document root
`/tmp/mdv` (a copy of the repository plus generated test documents). Client: Python
`urllib` via `/tmp/req.py`. Date: 2026-10-13/14.

| Test id | What was exercised | Outcome |
|---|---|---|
| `test:viewer_mode` | `md.md` present → `GET /md.php` | 200, 47 119 B, `<title>` from first H1 |
| `test:ini_autocreate` | first request to `md.php` | `.md.ini` created with 6 keys + commented `BROWSE_DIR`; **no `API_KEY`** |
| `test:api_key_autogen` | first request to `updater.php` | `API_KEY = mdv_` + 48 hex appended |
| `test:browser_mode` | `md.md` removed | 200, file table with `data-sort-default="modified"`, search box, Upload/Clipboard buttons |
| `test:machine_api` | `status`, `conflicts`, wrong key, `install` via GET, unknown action, no key | 200 / 200 / **403** / **405** / **400** / **403** |
| `test:flags_off_by_default` | `?update=true`, `?restore=latest`, landing page | 403 / 403 / 200 + `nosniff` |
| `test:path_traversal` | 16 `?file=` payloads | 13 refused with the browser page + banner; `docs/sub/nested.md`, `docs/root.md`, `README.md` allowed |
| `test:download_endpoint` | `?file=…&download=1` | `application/octet-stream`, `nosniff`, `Content-Disposition` with ASCII + `filename*=UTF-8''`, `no-store` |
| `test:xss` | 14 payloads via clipboard POST | 9 passed through verbatim; 4 blocked; 1 escaped |
| `test:headers_absent` | response header inspection | no CSP, X-Frame-Options, HSTS, Referrer-Policy, Permissions-Policy |
| `test:mermaid_config` | `js/md/md.js:292` | `securityLevel: 'loose'`, `htmlLabels: true` |
| `test:features_full` | one document exercising ~25 constructs | confirmed working set and the divergences in summary.md §6 |
| `test:toc_threshold` | 1 vs 2+ headings | TOC only when `count($headings) >= 2` |
| `test:glossary_index` | glossary table alone, and after a normal table | `data-gterm="tbl-N:row:cols"`, ids `gd-tbl-N-row-col`; short first-column terms leak tooltips into other tables |
| `test:upload` | `md_file` with 10 filenames, `dir` param | `.md`-only, `.MD`→`.md`, `basename()` strips traversal, leading dot / `<>:"|?*` / >200 chars rejected, `dir=../../etc` and `dir=/tmp` → 400, duplicate → `.bak.Ymd-His` |
| `test:upload_disabled` | `DISABLE_UPLOAD = true` | 403 with a precise JSON error |
| `test:save_clipboard_disabled` | `DISABLE_SAVE_CLIPBOARD_TO_FILE = true` | 403 with a precise JSON error |
| `test:nested_lists` | 2-space and 4-space nested bullets | not nested — child rendered as a literal paragraph |
| `test:tilde_fence` | `~~~js` | not rendered as a code block |
| `test:indented_code` | 4-space code block | rendered as a paragraph |
| `test:autolink` | bare URL and `<https://…>` | literal text, no anchor |
| `test:entities` | `&amp;`, `&#169;` | double-escaped |
| `test:backslash` | `\*not emphasis\*` | escapes not honoured |
| `test:setext` | `Title\n---` | text duplicated as `<p>` and `<h2>` |
| `test:fence_length` | 4-backtick fence wrapping a 3-backtick fence | handled correctly (length-aware) |
| `test:list_start` | `5. five` | `<ol start="5">` preserved |
| `test:blockquote` | lazy continuation + second paragraph | merged into one `<p>`, two `<p>`s in the quote, copy button added |

## C. External / authoritative sources

| # | Source | URL | Used for |
|---|---|---|---|
| 1 | GitHub Flavored Markdown Spec, v0.29-gfm (2019-04-06) | https://github.github.com/gfm/ | The five GFM extensions; §2.3 insecure characters; §6.10 raw HTML; §6.11 disallowed raw HTML; the statement that GitHub performs additional post-processing and sanitisation |
| 2 | CommonMark Spec | https://spec.commonmark.org/ | Two-phase parsing model; §4.5 fences; §6.1 backslash escapes; §6.2 entities; §4.3 setext headings |
| 3 | OWASP Cross Site Scripting Prevention Cheat Sheet | https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html | Sanitisation guidance; DOMPurify recommendation |
| 4 | OWASP DOM Clobbering Prevention Cheat Sheet | https://cheatsheetseries.owasp.org/cheatsheets/DOM_Clobbering_Prevention_Cheat_Sheet.html | Risk from unescaped `id`/`name` attributes |
| 5 | DOMPurify (cure53) | https://github.com/cure53/dompurify | Reference browser-side sanitiser |
| 6 | remark-gfm | https://github.com/remarkjs/remark-gfm | Confirmation of the GFM extension set (autolink literals, footnotes, tables, strikethrough, task lists) |
| 7 | "CommonMark vs GFM (2026)" | https://formatarc.com/en/blog/commonmark-vs-gfm/ | Corroboration that GFM adds five extensions incl. *disallowed raw HTML* |
| 8 | "9 Best MkDocs Alternatives… 2026" (HeroThemes) | https://herothemes.com/blog/mkdocs-alternatives/ | docsify "does not build static HTML at all" — competitive context |
| 9 | "Best Docusaurus Alternatives in 2026" | https://docsio.co/blog/docusaurus-alternative | MkDocs = Python + plain Markdown, simplest static generator — competitive context |
| 10 | MDN `Content-Security-Policy` / `script-src` | https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/script-src | CSP hardening guidance |
| 11 | cURL `CURLOPT_SSL_VERIFYHOST` | https://curl.se/libcurl/c/CURLOPT_SSL_VERIFYHOST.html | Default value semantics when the option is not set |
| 12 | PHP `parse_ini_file` | https://www.php.net/manual/en/function.parse-ini-file.php | `INI_SCANNER_TYPED` semantics for the `.md.ini` loader |
| 13 | PHP `move_uploaded_file` | https://www.php.net/manual/en/function.move-uploaded-file.php | Why the upload path is only valid for real HTTP uploads (relevant to CLI testing) |
| 14 | Mermaid `securityLevel` configuration | https://mermaid.js.org/config/security.html | What `loose` permits (HTML labels, click callbacks) |
| 15 | Unicode UAX #44 — general category `Pd` | https://www.unicode.org/reports/tr44/ | The 26-character dash-punctuation category added in v2.18.0 |

## D. Claims deliberately NOT made in the wiki

| Tempting claim | Why it is excluded |
|---|---|
| "Syntax highlighting" | No highlighter exists anywhere in the repository; the README's requirements line mentions it but no code loads one. |
| "Nested lists supported" | Falsified by test — indented children render as literal paragraph text. |
| "Tilde fences supported" | `stripCodeBlocks` and `collectHeadings` accept `~{3,}`, but the body renderer did not produce a code block in testing. |
| "CommonMark / GFM compliant" | Entities, backslash escapes, autolinks, indented code and setext headings all diverge. |
| "Signed updates" | No signature or pinned commit; SHA-256 is change detection only. |
| "PHP 8.3 enforced" | No `version_compare`/`PHP_VERSION` guard exists; 8.3+ is documented, and the code ran on 8.2.34. |
| "`.htaccess` provided" | No `.htaccess` in the repository. |
| "Releases / tags" | The repository has none; versioning is by file-header comment and tracked-file list. |
| Issue/PR statistics | Not retrievable from a bare clone and not fetched from the GitHub API. |
