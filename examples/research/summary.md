# summary.md — Phase 1 findings, MD.Viewer

Analysed 2026-10-13/14 from a fresh clone of `https://github.com/paulmann/MD.Viewer`
(commit `85d3f54`, branch `main`, 157 commits, first commit 2026-06-16, **no tags, no releases, no issues/PR metadata in the clone**).
All behavioural claims marked **[tested]** were executed against `php -S 127.0.0.1:8123`
on PHP 8.2.34 in the sandbox.

## 1. What the software is

MD.Viewer is a **self-hosted, single-entry-point Markdown viewer written in plain PHP**.
It has no build step, no database, no framework and no Composer dependencies. Two PHP
files do all the work:

| File | Version | Lines | Role |
|---|---|---|---|
| `md.php` | 2.18.0 | 4709 | Viewer + recursive file browser + Markdown→HTML renderer |
| `updater.php` | 3.14.0 | 2799 | Self-updater, backup/restore, upload, clipboard save, machine JSON API |

Supporting assets: 3 CSS files (`css/md/`), 4 JS files (`js/md/`), `README.md` v2.11.3,
`LICENSE` v1.0.0 (MIT with an attribution clause). Project version = **2.11.3**
(the README's version); component versions are tracked independently.

Author: **Mikhail Deynekin** (`Mikhail@Deynekin.com`, https://Deynekin.com).
Copyright (c) 2026.

There is also a `tools/` directory with three PowerShell scripts
(`Invoke-ProjectDoctrine.ps1`, `Test-DoctrineFalsifiability.ps1`,
`Test-ViewerRobustness.ps1`) — an engineering-process harness, not part of the runtime.
They are **not** in `TRACKED_FILES`, so the updater never touches them.

## 2. The problem it solves

Publishing a folder of `.md` files as readable documentation normally requires either a
static-site generator (build step, toolchain, deploy pipeline) or a database-backed CMS.
MD.Viewer's proposition is: drop two PHP files next to your `.md` files and open
`md.php`. The distinctive mechanics:

- **Naming-convention routing.** `md.php` renders `md.md`; `docs.php` renders `docs.md`
  (`pathinfo(__FILE__, PATHINFO_FILENAME) . '.md'`). Copy the script under a new name to
  create another independent instance in the same tree — no router config.
- **Graceful mode switch.** If the matching `.md` does not exist, the same URL becomes a
  recursive Markdown file browser instead of a 404.
- **Server-side config without a DB.** `.md.ini` next to the script, auto-created on
  first request, auto-appended with any missing keys on every load, so upgrades never
  require manual edits.

## 3. Architecture in one paragraph

A request enters `md.php`, which (1) 301-normalises a doubled slash in `REQUEST_URI`,
(2) loads/creates `.md.ini` and appends missing keys, (3) resolves 18 feature toggles
through `feat()` with precedence *ini override → cookie `mdv_feat_*` → compiled default*,
(4) short-circuits `?download=1` into an `application/octet-stream` attachment,
(5) computes the effective per-directory `DISABLE_*` flags, (6) handles a
`POST md_preview=1` clipboard render, (7) resolves the document via
`validateRequestedFile()` or falls back to `<scriptname>.md`, and (8) runs the render
pipeline (`normalizeMarkdown` → `extractMeta` → H1 strip → `parseSources` →
`parseGlossaryTables` → `removeSourcesSection` → `collectHeadings` →
`assignHeadingNumbers` → `renderTOC` → `renderMarkdown` → `applyGlossaryTooltipsToHtml` →
`renderSourcesList`) into a Tailwind-based HTML template. `updater.php` is a separate
entry point that talks to `raw.githubusercontent.com` over cURL and maintains
`md.backup/{version}/` plus `md.backup/.state/{slug}.json`.

## 4. Security posture — the central finding

**Path traversal defence is genuinely strong.** `validateRequestedFile()` implements 14
ordered layers (length, NUL, control chars, url-decode re-test, absolute-path rejection,
separator normalisation + `..` rejection, Unicode character whitelist, depth limit,
extension check, base realpath, target realpath, containment prefix, `is_file`,
post-symlink extension re-check). **[tested]** All of `../etc/passwd`,
`..%2f..%2fetc%2fpasswd`, `/etc/passwd`, `docs/../md.php`, `....//....//etc/passwd`,
`..\..\windows\win.ini`, `md.md%00.png`, `.md.ini`, and a 260-char name were refused.
Denial returns **HTTP 200** with the browser page carrying
`Access denied or file not found. Path validation failed.` — not a 4xx.

**Raw-HTML handling is the weak point.** `inlineMarkdown()` captures every
`/<\/?[a-zA-Z][^>]*>/u` match into `$rawHtmlSpans` (md.php:2041) and restores it
**verbatim after** the `e()` escape pass (md.php:2176). **[tested]** These payloads were
reproduced byte-for-byte inside `<article class="markdown-body">`:

```
<script>alert(1)</script>          <img src=x onerror=alert(1)>
<details open ontoggle=alert(1)>   <svg onload=alert(1)>
<a href="x" onclick="alert(1)">    <iframe src="javascript:alert(1)"></iframe>
[click][r] + [r]: javascript:alert(1)   → <a href="javascript:alert(1)">
```

Correctly blocked **[tested]**: `[click](javascript:…)` (inline-link regexes only accept
`#…` or `https?://…`), `data:` links, and `![x](y.png" onerror="…)` (attribute injection
escaped to `&quot;`).

No `Content-Security-Policy`, `X-Frame-Options`, `Strict-Transport-Security`,
`Referrer-Policy` or `Permissions-Policy` header is sent by `md.php` **[tested]**.
GFM 0.29 §6.11 defines a "Disallowed Raw HTML" extension for exactly this case and
GitHub additionally sanitises after conversion; MD.Viewer implements neither.
**Conclusion: MD.Viewer is safe for documents the operator trusts, and unsafe for
documents an untrusted third party can write.** That is the single most important
sentence in the whole wiki.

Mitigations that *do* exist and work: `DISABLE_UPLOAD = true` by default; upload
filename validation **[tested]**; three-level flag enforcement (`.md.ini` + PHP guard +
UI suppression); same-origin guard on every mutating `updater.php` action (v3.11.0);
`API_KEY`-gated machine JSON API; `writeBlockedReason()` refusing to overwrite files that
lack the ` * Version: X.Y.Z` marker.

## 5. Updater integrity model — precise statement

Detection is a two-layer scheme: conditional GET with a stored ETag (`If-None-Match`),
then on HTTP 200 a `hash_equals()` SHA-256 comparison of the payload against the local
file. State lives in `md.backup/.state/{slug}.json` as `{etag, hash, updated_at}`.
Writes are atomic (`tempnam` → `LOCK_EX` write → `rename` → `chmod 0644`), and every
replacement is preceded by a copy into `md.backup/{localVersion}/`.

**SHA-256 here is a change detector, not an authenticity proof.** There is no signature,
no pinned commit SHA, no out-of-band checksum manifest. `CURLOPT_SSL_VERIFYPEER` is
`true`; `CURLOPT_SSL_VERIFYHOST` is **not set explicitly** and therefore inherits the
libcurl default (2 since libcurl 7.10.0, 2002) — worth setting explicitly for defence in
depth. The trust anchor is TLS to `raw.githubusercontent.com` plus write access to
`refs/heads/main` of the repository. Anyone who can push to `main` can push code that
every `ALLOW_UPDATE = true` installation will execute.

## 6. Markdown feature support — measured, not claimed

**[tested]** Working: ATX headings h1–h6 with slug + dedupe (`-2`, `-3`) · automatic
hierarchical numbering that skips manually-numbered headings · paragraphs, `**strong**`,
`__strong__`, `*em*`, `_em_`, `~~del~~`, `==mark==`, `~sub~`, `^sup^` · fenced code with
backticks (length-aware: a 4-backtick fence correctly wraps a 3-backtick one) ·
`mermaid`/`mmd` info strings → `<pre class="mermaid">` · tables with `:---`/`:---:`/`---:`
alignment · task lists (unchecked enabled, checked `disabled`) · ordered lists with
`start` preserved · blockquotes with a copy button · thematic breaks `-`/`*`/`_` ·
footnotes with `title` preview + backlink · reference links with optional titles ·
source citations `[[1,2]]` · 16 emoji shortcodes · images with lazy loading and a
graceful fallback span · "universal patterns" inside inline code
(`(User)-[auth]->(Server)` → a `.pattern-chain` visual) · glossary tooltips from ordinary
Markdown tables.

**[tested]** Not supported / divergent from CommonMark:

| Input | Expected (CommonMark/GFM) | Actual |
|---|---|---|
| `- top` + indented `- child` | nested `<ul>` | child becomes a literal `<p>- child<br><br> …</p>` **outside** the list |
| 4-space indented code block | `<pre><code>` | plain `<p>` |
| `~~~` fence | fenced code | literal paragraph text (only `` ` `` fences are handled by the renderer at md.php:3139) |
| Bare `https://example.com` | GFM autolink literal | literal text |
| `<https://example.org>` | CommonMark autolink | literal text |
| `&amp;` / `&#169;` | decoded entity | double-escaped to `&amp;amp;` / `&amp;#169;` |
| `\*not emphasis\*` | literal `*not emphasis*` | renders `<em>not emphasis\</em>` — backslash escapes not honoured |
| Setext `Title\n---` | one `<h2>` | text appears **twice**: `<p>Setext H2</p>` then `<h2>Setext H2</h2>` |
| Trailing-two-space hard break | single `<br>` | `<br><br>` under the default `PARAGRAPH_BREAK_STYLE=double-br` |

README claims "nested lists" and "syntax-highlighted code blocks". **Neither is present**:
nested lists break as shown above, and a repo-wide grep for `cdn|unpkg|jsdelivr|cdnjs|highlight`
finds only three external URLs — Tailwind, Google Fonts, Mermaid. No highlighter is loaded;
code is emitted as `<pre><code class="language-XXX">` and styled by `md.css` alone.
The wiki must not repeat those two claims.

## 7. Other verified behaviours worth documenting

- **TOC threshold.** `renderTOC()` returns `''` when `count($headings) < 2`. Because
  viewer mode strips the first H1 *before* collecting headings, a document needs
  **at least two headings in addition to its H1** for a TOC to appear. **[tested]**
- **`SPLIT_TITLE_BY_COLON`.** `# Main Title: Subtitle Part` → `<title>Main Title</title>`
  and the subtitle becomes the hero paragraph / meta description. **[tested]**
- **Meta description** is derived from document content, and the first H1 is removed from
  the body and re-rendered by the template as a hero `<h1>`.
- **Glossary heuristic.** *Any* table with ≥2 columns and a non-empty first-column header
  is treated as a glossary; every first-column cell value becomes a tooltip term matched
  across the whole document (outside `a`, `code`, `pre`, `script`, `style`, `th` and
  first-column cells). Short or numeric terms therefore produce surprising tooltips —
  **[tested]** a table `| A | B |` made the cell `1` in another table a "glossary term".
  Alias syntax: `Base term (ALIAS)` registers both.
- **Sources.** A `## Sources` / `## Sources List` / `## Источники` / `## Список источников`
  section (H1 or H2, optional manual-number prefix) is stripped from the body and
  re-rendered as a styled list when entries match
  `N. **Title**` newline `- URL: https://…`. Inline citations use `[[1,2,3]]`. **[tested]**
- **File browser.** Columns `File · Dir · Created · Modified · Size` (+ a non-sortable
  download column when `FEATURE_DOWNLOAD_ICON`), `data-sort-default="modified"`
  `data-sort-dir-default="desc"`, client-side search box, scan limits depth ≤ 3 and
  ≤ 10 000 files, skips dotfiles and anything under a dot-directory, and re-checks
  symlink containment per file.
- **Clipboard preview.** `POST md_preview=1&content=…`, 2 MB cap, 403 when
  `DISABLE_CLIPBOARD`, 400 when empty, nothing written to disk.
- **Machine API.** **[tested]** `action=status` → 200 JSON (11 files, per-file versions,
  `counts`, `ini` block); `action=conflicts` → 200 JSON; wrong key → **403**;
  `install` over GET → **405**; unknown action → **400**. Key format
  `mdv_` + 48 hex chars from `random_bytes(24)`, generated by `updater.php` only —
  `md.php` does not create it.
- **Flags off by default.** **[tested]** `?update=true` → 403, `?restore=latest` → 403,
  while the `updater.php` landing page itself is public (200) and sends
  `X-Content-Type-Options: nosniff`.
- **Upload.** **[tested]** field name is `md_file`; `.md` only (`.MD` normalised to `.md`);
  `basename()` applied first, so `../evil.md` lands safely as `evil.md`; rejects leading
  dot, `<>:"|?*`, control chars, > 200 chars, > 2 MB; `dir` traversal or absolute → 400
  `Invalid dir parameter.`; an existing target is renamed to `<name>.bak.Ymd-His`;
  Unicode filenames accepted.
- **Quirk:** `<html lang="ru">` is hardcoded in the template even for English documents.
- **Quirk:** `window.MDV_CONFIG` is assigned twice in the emitted HTML (a minimal object,
  then the full one). Harmless, redundant.
- **Quirk:** the README's `.md.ini` sample shows `API_KEY`, but the file `md.php` creates
  does not contain it; only `updater.php` writes it.

## 8. Settings panel (client-side, cookie/localStorage persisted)

Sections: Font Size · Line Spacing · Page Width (`reading` / `article` / `wide`) ·
Header Toolbar (per device type; `data-toolbar="width"|"font"`) · File Browser Sort ·
Features ("reload to apply") · Paragraph Break (`double-br` / `single-space` / `margin`) ·
Storage · Index File · Updates · Backup & Restore. The last three are conditional on
`ALLOW_CREATE_INDEX_PHP_LINK`, `ALLOW_UPDATE`, `ALLOW_RESTORE`.
17 feature toggles are surfaced with labels: Auto Numbering, Auto TOC, Footnote Links,
Double Line Breaks, Cypher Patterns, Universal Patterns, Images, Ref Links, Task Lists,
Footnotes, Sub / Sup, Emoji, Split Title, Glossary Tooltips, File List: Show Download Icon,
File: Show Download Button, File: Show Copy Button.

## 9. Competitive position

| | MD.Viewer | docsify | MkDocs (+ Material) | Docusaurus |
|---|---|---|---|---|
| Build step | none | none | `mkdocs build` | `npm run build` |
| Runtime | PHP 8.3+ on any LAMP host | static files + browser JS | Python | Node/React |
| Database | none | none | none | none |
| Server-side rendering | **yes** — HTML arrives complete | no — client-side fetch+render | yes, at build time | yes, at build time |
| Search | client-side filter over a scanned file table | client-side full-text plugin | built-in / lunr | Algolia or local plugin |
| Self-update from GitHub | **built in** (`updater.php`) | no | no | no |
| Versioned backups + rollback | **built in** | no | no | no |
| Machine JSON API for installers | **built in** | no | no | no |
| Per-directory config overrides | **built in** | no | `nav` in one YAML | sidebars JS |
| SEO / no-JS readability | good (server-rendered) | poor (empty shell without JS) | excellent | excellent |
| HTML sanitisation of source | **none** | marked + no raw HTML by default | Python-Markdown, raw HTML escaped by default | MDX — raw HTML is JSX, escapes are explicit |
| Best fit | trusted internal docs on an existing PHP host | quick client-side docs site | versioned public docs | large product docs |

MD.Viewer's real differentiators are the three things no competitor ships: a
**self-updater with backups and rollback**, a **machine JSON API** so a control panel can
drive installation, and **per-directory `.md.ini` overrides**. Its real gap is
sanitisation.
