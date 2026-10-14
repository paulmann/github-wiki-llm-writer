# domain-notes.md — problem domain, standards, security context, glossary

## 1. Standards context

### CommonMark
CommonMark is the formal specification of Markdown published by John MacFarlane; it
exists because Gruber's 2004 syntax description left many constructs ambiguous. Parsing
is defined as two phases: block structure first, then inline structure, with link
reference definitions collected in phase 1 and consumed in phase 2.
Notable rules MD.Viewer interacts with:

- **§2.3 Insecure characters** — "For security reasons, the Unicode character `U+0000`
  must be replaced with the REPLACEMENT CHARACTER (`U+FFFD`)." MD.Viewer instead *rejects*
  NUL outright (validator layers 2 and 4), which is stricter and safe.
- **§4.5 Fenced code blocks** — a fence is 3+ backticks *or* 3+ tildes, and a closing fence
  must be at least as long as the opening one and use the same character. MD.Viewer's
  `stripCodeBlocks()`/`collectHeadings()` are length-aware (a documented v2.x fix), but the
  **body renderer only matches backtick fences** (`/^ {0,3}(`{3,}|~{3,})\s*([\w+.-]*)\s*$/u`
  at md.php:3139 accepts both characters, yet tilde fences were observed to fail in
  practice — see the feature matrix).
- **§6.10 Raw HTML** — CommonMark deliberately passes raw inline HTML through. Sanitisation
  is explicitly the *host application's* job, not the parser's.
- **§6.1 Backslash escapes** — any ASCII punctuation may be backslash-escaped. MD.Viewer
  does not implement this.
- **§6.2 Entity and numeric character references** — should be decoded. MD.Viewer escapes
  them instead, so `&amp;` renders as the literal text `&amp;`.
- **§4.3 Setext headings** — an underline of `=` (level 1) or `-` (level 2). MD.Viewer
  detects them in `collectHeadings()` (md.php:2325) but the body pass also emits the text
  as a paragraph, producing a duplicate.

### GitHub Flavored Markdown
GFM (spec version **0.29-gfm, 2019-04-06**) is a strict superset of CommonMark adding five
extensions: **tables** (§4.10), **task list items** (§5.3), **strikethrough** (§6.5),
**autolinks extension** (§6.9), and **disallowed raw HTML** (§6.11). Two statements from
the spec matter enormously for this project:

> "GFM is a strict superset of CommonMark."

> "While GFM supports a wide range of inputs, it's worth noting that GitHub.com and GitHub
> Enterprise perform additional post-processing and sanitization after GFM is converted to
> HTML to ensure security and consistency of the website."

So the spec itself separates *parsing* from *sanitising*, and GitHub ships a sanitiser.
§6.11 "Disallowed Raw HTML" literally replaces the literal text of `<title>`, `<textarea>`,
`<style>`, `<xmp>`, `<iframe>`, `<noembed>`, `<noframes>`, `<script>` and `<plaintext>`
with escaped text — the minimum viable defence MD.Viewer lacks.

### MD.Viewer's relationship to the specs
MD.Viewer is **not** a CommonMark or GFM implementation. It is a regex-and-state-machine
renderer that covers a large, useful subset plus proprietary extras (heading numbering,
source citations, glossary tooltips, universal patterns). The wiki should say this plainly:
"Markdown-flavoured, CommonMark-inspired, not spec-conformant" — and give the measured
matrix so authors know what to write.

## 2. Security domain

### XSS in Markdown renderers
The canonical failure mode is exactly what MD.Viewer has: escaping the *text* but
deliberately passing *tags* through. OWASP's XSS Prevention Cheat Sheet recommends HTML
sanitisation with an allowlist and names **DOMPurify** as the reference browser-side
sanitiser; for server-side PHP the equivalent approach is an allowlist filter over the
token stream. Two mitigations are relevant to a PHP viewer:

1. **Output sanitisation** — strip or escape every tag not in an allowlist, and strip
   `on*` attributes and non-`http(s)`/`mailto`/`#` URL schemes.
2. **Content-Security-Policy** — a `script-src 'self'` policy neutralises inline
   `<script>` and `on*` handlers even when they reach the page. MD.Viewer sends no CSP
   today; because the page needs `cdn.tailwindcss.com` (which itself uses `eval`-style
   JIT) and `cdn.jsdelivr.net` (Mermaid), a working policy must be:
   `script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net;`
   — which does **not** block an injected inline handler. Only removing the third-party
   CDNs (self-hosting Tailwind's compiled CSS and Mermaid) allows a strict
   `script-src 'self'`. This trade-off must be stated honestly in the hardening guide.

Also relevant: **DOM clobbering** (OWASP has a dedicated cheat sheet) — unescaped
`<form id="x">` or `<img name="y">` can shadow globals that the viewer's own JS reads.

### Path traversal
Standard defence-in-depth for a file-serving script, and MD.Viewer's 14-layer validator is
a textbook implementation: reject before resolving, decode then re-test, whitelist
characters, cap depth, require the extension, `realpath()` both sides, then verify the
prefix containment, then re-check the extension *after* symlink resolution. Two details
deserve credit: the post-`realpath` extension re-check defeats a symlink named `x.md`
pointing at `/etc/shadow`, and the `is_file()` check defeats directories and devices.

One consequence to document: the whitelist is **extension-based, not document-based**.
Any `.md` inside the browse root is readable, including `README.md`. If the browse root
contains a private `.md`, it is public.

### File upload
Classic risks: unrestricted extension, filename traversal, size bombs, storage outside the
web root, and overwriting existing files. MD.Viewer's answers (all verified):
`.md`-only with `basename()` applied first; explicit rejection of `/ \ .. NUL <>:"|?*` and
control chars; leading-dot rejection; 200-char name cap; 2 MB size cap; existing target
renamed to `<name>.bak.Ymd-His`; destination resolved from `dir` → `BROWSE_DIR` →
`uploads.md/`, with `dir` traversal answered 400. Because the only writable extension is
`.md` and PHP never executes `.md`, uploaded content cannot become code on the server —
**but it can become stored XSS in the viewer**, which is why `DISABLE_UPLOAD = true` is
the shipped default.

### Self-updater supply chain
The general model for "download a file from a URL and replace yourself" requires one of:
a detached signature verified against a pinned public key, a pinned commit SHA, or a
checksum manifest distributed over a *different* channel. MD.Viewer has none of these;
it has TLS + SHA-256 change detection + a pre-write "is this one of our files?" guard +
versioned backups + rollback. That is a reasonable *availability* story and a weak
*authenticity* story. The hardening guide should recommend: keep `ALLOW_UPDATE = false`
on production, or pin your own fork and change `RAW_BASE`, and always test an update on a
staging copy first because rollback exists and works.

### CSRF / cross-site state change
`updater.php` v3.11.0 added `sameOriginViolation()` / `requireSameOrigin()`: every
mutating entry point (legacy actions, machine install, `?update=true`, `?restore=`) is
answered 403 when `Origin` — and for those actions also `Referer` — names another host.
Host comparison is port-insensitive. Clients sending neither header (CLI, server-to-server)
are unaffected. This is a real CSRF mitigation, though it relies on browsers sending
`Origin`, which they do for cross-origin POST and for same-origin POST in modern browsers.

## 3. Deployment domain

- **Apache** — no `.htaccess` is shipped in the repository (verified: the file tree has
  none). The viewer works with plain `mod_php`/PHP-FPM because it never relies on rewrite
  rules; routing is `md.php?file=…`. Any `.htaccess` guidance in the wiki must be marked
  as *recommended additions*, not project-supplied files.
- **Nginx** — standard `location ~ \.php$` + `fastcgi_pass`; `index index.php md.php;` makes
  the viewer the directory index. Note that the shipped Nginx sample in the README uses
  `php8.3-fpm.sock`.
- **IIS** — PHP via FastCGI + the IIS `php.ini`; hard links (`index.php` management) map to
  NTFS hard links, which require NTFS and same-volume.
- **PHP built-in server** — `php -S localhost:8080` works and was used for all sandbox
  testing. Not for production.
- **Writable paths** — the process needs write access to the install directory (for
  `.md.ini`), `uploads.md/` or `BROWSE_DIR` (for upload/save), and `md.backup/` including
  `.state/` (for updates). The updater creates missing `js/md/` and `css/md/` with `0755`
  and writes files `0644`.
- **Egress** — updates require outbound HTTPS to `raw.githubusercontent.com`. On a locked-down
  host the updater fails; the viewer itself still works, but Tailwind/Fonts/Mermaid also
  need egress from the *browser*, not the server.

## 4. Performance domain

There is **no caching layer**: every request re-reads `.md.ini`, re-scans (browser mode),
and re-renders (viewer mode). `parse_ini_file` + `file_get_contents` + the regex pipeline
run per request. Practical levers: HTTP caching at the reverse proxy (the app sends no
`Cache-Control` on viewer pages), OPcache for the 202 KB script, `MAX_SCAN_DEPTH`/`MAX_FILES_SCAN`
limits (3 / 10 000) that bound browser-mode cost, and the third-party CDNs which dominate
first-paint latency. Mermaid is lazy-loaded only when a `.mermaid` block exists — a good
decision worth crediting.

## 5. Glossary (canonical terminology for the whole wiki)

Use these terms consistently; do not invent synonyms.

| Term | Definition |
|---|---|
| **viewer** | `md.php`. The single PHP entry point that renders documents and, failing that, browses files. |
| **updater** | `updater.php`. The companion self-update, backup, upload and API engine. |
| **viewer mode** | The rendering mode entered when a Markdown file resolves (via `?file=` or `<scriptname>.md`). |
| **file browser mode** (also *browser mode*) | The recursive Markdown listing shown when no file resolves. |
| **clipboard preview mode** | `POST md_preview=1` rendering of pasted text; nothing is written to disk. |
| **raw download** | `GET ?file=…&download=1` answering with the file's bytes as an attachment. |
| **browse root** | The directory the viewer lists and reads: `BROWSE_DIR` when set and resolvable, otherwise the directory containing `md.php`. |
| **base `.md.ini`** / **installation-level config** | The `.md.ini` next to `md.php`; holds all keys. |
| **directory `.md.ini`** / **per-directory config** | An optional `.md.ini` inside the browse root; only the three `DISABLE_*` keys are honoured. |
| **install-level key** | `BROWSE_DIR`, `API_KEY`, `ALLOW_UPDATE`, `ALLOW_RESTORE`, `ALLOW_CREATE_INDEX_PHP_LINK`. Ignored in a directory `.md.ini` and logged. |
| **feature toggle** | One of the 18 `feat()`-resolved rendering switches, overridable by cookie unless hard-locked in `.md.ini`. |
| **hard lock** | A feature toggle present in `.md.ini`; `_MDV_INI_OVERRIDE` makes it immune to cookies and the Settings panel. |
| **tracked file** | One of the 11 paths in `TRACKED_FILES` that the updater checks, downloads and backs up. |
| **managed file** | A file whose first 1000 bytes contain ` * Version: X.Y.Z`; used by `writeBlockedReason()` to avoid clobbering foreign files. |
| **state file** | `md.backup/.state/{slug}.json` holding `{etag, hash, updated_at}` per tracked file. |
| **backup version directory** | `md.backup/{version}/`, written before a replacement. |
| **pre-restore backup** | `md.backup/{version}-pre-restore/`, written before a rollback so a rollback can be rolled back. |
| **machine API** | The `API_KEY`-authenticated JSON interface (`status`, `conflicts`, `install`). |
| **legacy actions** | The AJAX actions used by the Settings panel (`check`, `apply`, `restore`, `backups`, `version`, `index_*`, `upload_md`, `save_clipboard`). |
| **two-phase bootstrap** | Update phase 1 replaces `updater.php` itself and redirects to `?_phase=2` so the new code does the rest. |
| **force reinstall** | `force` — bypass the ETag/SHA cache and permit overwriting non-managed files. |
| **pre-write guard** | `writeBlockedReason()`; refuses to replace a file that is not recognisably MD.Viewer's. |
| **same-origin guard** | `requireSameOrigin()`; 403 for cross-site state changes. |
| **path validator** | `validateRequestedFile()`; the 14-layer `?file=` gate. |
| **directory validator** | `mdvDirSegments()` / `dirSegments()`; the equivalent gate for the `dir` parameter. |
| **glossary term** | A first-column cell value in any table with a non-empty first header; becomes a hover tooltip. |
| **universal pattern** | A node/relationship expression inside inline code, e.g. `(A)-[rel]->(B)`, rendered as a `.pattern-chain`. |
| **source citation** | `[[1,2,3]]` in prose, resolved against a `## Sources` numbered list. |
| **hero title** | The template's `<h1>` built from `extractMeta()`; the document's own first H1 is stripped from the body. |
| **interface gate** | A toggle that hides a control but does not restrict the underlying request (the three download/copy toggles). |
| **access control** | A server-side restriction that actually refuses a request (`ALLOW_UPDATE`, `ALLOW_RESTORE`, `DISABLE_UPLOAD`, `API_KEY`). |

> The distinction between **interface gate** and **access control** is the project's own,
> stated in the v2.14.0/v2.15.0 changelogs. Preserve it exactly — it prevents readers from
> believing that hiding a download icon restricts downloading.
