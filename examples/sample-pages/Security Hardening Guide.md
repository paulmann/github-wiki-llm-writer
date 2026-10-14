# Security Hardening Guide

MD.Viewer renders Markdown that it reads from disk and, optionally, accepts from the
network. That makes its output-encoding decisions the whole of its security posture. This
page states the threat model, reports what was **verified by executing the code**, separates
what is genuinely well defended from what is not, and gives concrete hardening steps with
copy-pasteable configuration.

> [!CAUTION]
> **Headline finding.** MD.Viewer passes raw HTML from Markdown through to the page
> **unescaped**, sends **no `Content-Security-Policy` header**, and does **not filter the
> URL scheme of reference-style links**. A Markdown document containing
> `<script>alert(1)</script>` executes. The application is therefore appropriate for
> documents the operator controls, and **inappropriate for documents that untrusted users
> can write or upload**. Everything else on this page is secondary to that fact.

## Contents

- [Threat model](#threat-model)
- [What is well defended](#what-is-well-defended)
- [Verified vulnerabilities](#verified-vulnerabilities)
- [Update supply chain](#update-supply-chain)
- [Hardening, in priority order](#hardening-in-priority-order)
- [Reverse-proxy hardening](#reverse-proxy-hardening)
- [Web-server hardening](#web-server-hardening)
- [Filesystem and permissions](#filesystem-and-permissions)
- [Detection and logging](#detection-and-logging)
- [Deployment decision matrix](#deployment-decision-matrix)
- [Pre-deployment checklist](#pre-deployment-checklist)
- [Reporting a security issue](#reporting-a-security-issue)
- [See also](#see-also)

---

## Threat model

MD.Viewer has **no authentication and no authorisation**. It has never had either; the
project's own changelog says so when describing the download toggles as "interface gates
rather than access control". Reasoning about its security therefore reduces to one question:

> **Who can write a `.md` file into the browse root, and who can read the rendered page?**

| Actor | Capability | Consequence |
|---|---|---|
| Anonymous reader | Open any URL | Reads **every** `.md` inside the browse root, to depth 3. No path outside it. |
| Anonymous reader | `?file=…&download=1` | Downloads the raw bytes of the same set |
| Anonymous reader | `POST md_preview=1` | Renders arbitrary text they supply, in the page's origin |
| Visitor, when `DISABLE_UPLOAD = false` | `action=upload_md` | Writes a `.md` into the browse root → **stored XSS** against later readers |
| Visitor, when `DISABLE_SAVE_CLIPBOARD_TO_FILE = false` | `action=save_clipboard` | Same |
| Visitor, when `ALLOW_UPDATE = true` | `?update=true` | Replaces all eleven tracked files with upstream `main` → **remote code execution as the web user** |
| Visitor, when `ALLOW_RESTORE = true` | `?restore=X.Y.Z` | Reverts files to a backup version |
| Holder of `API_KEY` | `action=install` | Same as `?update=true`, without needing `ALLOW_UPDATE` |
| Author of an upstream commit to `main` | — | Their code runs on every updating installation |

The four `ALLOW_*`/`DISABLE_*` flags and `API_KEY` are the only real controls. Everything
else is defence in depth around reading files.

---

## What is well defended

Credit where it is due — these were tested, not assumed.

### Path traversal: a 14-layer validator

`validateRequestedFile()` (`md.php`) applies, in order:

| # | Layer | Defeats |
|---|---|---|
| 1 | Non-empty, ≤ 255 bytes | Oversized payloads |
| 2 | No NUL byte | Truncation attacks |
| 3 | No ASCII control characters `[\x00-\x1F\x7F]` | Header/log injection, backspace tricks |
| 4 | `urldecode()`, then re-test layer 3 | Double encoding |
| 5 | Reject leading `/`, `\`, `//`, or `^[A-Za-z]:` | Absolute and UNC paths |
| 6 | Normalise `\` and `//` to `/`; reject `..` as a segment or trailing | Traversal, separator confusion |
| 7 | Strict character whitelist `^[A-Za-z0-9._\-/ \p{L}\p{M}\p{Pd}]+$` | Shell metacharacters, `%`, `?`, `*`, `:`, quotes |
| 8 | Directory depth ≤ 3 | Deep-path DoS |
| 9 | Must end with `.md` (case-insensitive) | Reading `.php`, `.ini`, `.htaccess` |
| 10 | `realpath(baseDir)` must be a directory | Misconfiguration |
| 11 | `realpath(base + path)` must resolve | Non-existent targets |
| 12 | Real path must equal base or start with `base + /` | **Symlink escape** |
| 13 | `is_file()` | Directories, devices, FIFOs |
| 14 | Re-check the extension on the **resolved** path | A symlink named `x.md` → `/etc/shadow` |

**Verified refused** (each returned HTTP 200 with the file browser page and the banner
`Access denied or file not found. Path validation failed.`):

```text
../etc/passwd                       ..%2f..%2fetc%2fpasswd
/etc/passwd                         docs/../md.php
....//....//etc/passwd              %2e%2e%2f%2e%2e%2fetc%2fpasswd
..\..\windows\win.ini               docs/sub/../../../../etc/hosts
md.md%00.png                        .md.ini
../.md.ini                          a 260-character name
```

**Verified allowed:** `docs/sub/nested.md`, `docs/root.md`, `README.md`.

Layer 14 is the one most implementations miss, and layers 3–4 (control characters, then
decode-and-recheck) are the ones that defeat encoding games. The same whitelist is
duplicated in `mdvDirSegments()` and the updater's `dirSegments()`, and the changelog
records that all three were widened together in v2.16.0 (Unicode letters and marks) and
v2.18.0 (the `\p{Pd}` dash category) precisely so the validator and the per-directory
config reader could not disagree.

> [!NOTE]
> Refusals answer **HTTP 200**, not 4xx. This is a deliberate non-disclosure choice: the
> viewer neither confirms nor denies the existence of anything outside the browse root.
> Do not write monitoring rules that expect a 403 here.

### Upload filename validation

`doUploadMd()` in `updater.php` applies `basename()` first, then requires a `.md` suffix
(case-insensitive, normalised to lowercase), then rejects `/`, `\`, `..`, NUL, control
characters, `< > : " | ? *`, and a leading dot; then caps the name at 200 characters and
the payload at 2 MB. An existing target is renamed to `<name>.bak.Ymd-His` rather than
silently overwritten.

**Verified:**

| Filename sent | Result |
|---|---|
| `ok.md` | 200, written |
| `OK.MD` | 200, written as `OK.md` |
| `bad.php` | 400 `Only .md files are allowed.` |
| `.hidden.md` | 400 `Filename contains forbidden characters or patterns.` |
| `na<me>.md` | 400 same |
| 201 chars + `.md` | 400 `Filename too long (max 200 chars).` |
| `../evil.md` | 200, written as `evil.md` — `basename()` stripped the traversal |
| `a/b.md` | 200, written as `b.md` — same |
| `with space.md`, `док.md` | 200, written |
| `dir=../../etc` | 400 `Invalid dir parameter.` |
| `dir=/tmp` | 400 `Invalid dir parameter.` |

Because `.md` is the only writable extension and PHP never executes `.md`, an upload cannot
become server-side code. **It can become stored XSS** — which is why the flag defaults to
disabled.

### Flag enforcement at three levels

Every sensitive capability is guarded by the `.md.ini` flag, a PHP guard, and client-side
UI suppression. Hiding a button is never the only defence:

| Capability | Flag | PHP guard | Verified response when disabled |
|---|---|---|---|
| Update | `ALLOW_UPDATE` | `requireAllowUpdate()` | `?update=true` → **403** |
| Restore | `ALLOW_RESTORE` | `requireAllowRestore()` | `?restore=latest` → **403** |
| List backups | `ALLOW_RESTORE` | `requireAllowRestore()` | guarded (fixed in v3.8.2 to close an information leak) |
| Index link | `ALLOW_CREATE_INDEX_PHP_LINK` | `requireAllowIndexLink()` | `{disabled:true}` |
| Upload | `DISABLE_UPLOAD` | inline check | **403** `{"error":"File upload is disabled by server configuration (DISABLE_UPLOAD=true in .md.ini)."}` |
| Save clipboard | `DISABLE_SAVE_CLIPBOARD_TO_FILE` | inline check | **403** `{"error":"Save to File is disabled by server configuration (DISABLE_SAVE_CLIPBOARD_TO_FILE=true in .md.ini)."}` |
| Clipboard preview | `DISABLE_CLIPBOARD` | inline check in `md.php` | **403** `Clipboard preview is disabled by server configuration.` |
| Machine API | `API_KEY` | `handleJsonApi()` | **403** `unauthorized` / `api_key_unavailable` |

### Same-origin guard on state changes (v3.11.0)

`sameOriginViolation()` / `requireSameOrigin()` reject a request whose `Origin` — and, for
mutating actions, also whose `Referer` — names a different host, answering **403** before
anything is read or written. Host comparison is **port-insensitive** (an earlier version
compared ports and wrongly rejected same-origin requests on non-standard ports). Read-only
requests check `Origin` alone, so a page opened from a link on another site still works.
Clients that send neither header (CLI tools, server-to-server integrations) are unaffected.

This is a genuine CSRF mitigation for the update, restore, upload, save and index actions.

### Pre-write guard

`writeBlockedReason()` refuses to replace a file at a tracked path unless its first
1000 bytes contain a ` * Version: X.Y.Z` marker — i.e. unless it is recognisably an
MD.Viewer file. A foreign file is skipped and reported in `conflicts[]` until `force=1` is
explicitly requested. The updater also **never deletes** local files that are absent from
the remote manifest.

### Machine API discipline

- `install` requires **POST**: a GET answers **405**.
- An unknown action answers **400**.
- `apiParam()` reads only `$_GET` and `$_POST` — **never cookies or the environment** — so a
  stray cookie cannot flip `dry_run` or `force`.
- The response is strictly JSON; PHP notices and warnings are kept out of the body.
- `dry_run=1` stops after the conflict report: nothing is fetched, nothing is written.

---

## Verified vulnerabilities

All of the following were reproduced against a running instance
(`php -S`, PHP 8.2.34) via the clipboard-preview endpoint
(`POST md_preview=1&content=…`), which shares the renderer with every other mode. Anything
that works there works for a `.md` file on disk too.

### 1. Stored and reflected XSS via raw HTML passthrough — **High**

`inlineMarkdown()` captures every match of `/<\/?[a-zA-Z][^>]*>/u` into `$rawHtmlSpans`
before the escape pass, then restores the captured text **verbatim** afterwards. Payloads
reproduced byte-for-byte inside `<article class="markdown-body">`:

```html
<script>alert(1)</script>
<img src=x onerror=alert(1)>
<details open ontoggle=alert(1)>x</details>
<svg onload=alert(1)>
<a href="x" onclick="alert(1)">y</a>
<iframe src="javascript:alert(1)"></iframe>
```

**Impact.** Full script execution in the page's origin for every reader of the document.
Because MD.Viewer has no authentication, the value to an attacker is not session theft from
the app itself — it is the ability to run script on whatever origin you mounted it on. If
MD.Viewer shares an origin with an authenticated application, a cookie-scoped session, or an
admin panel, that application is compromised.

**Also exploitable without any attacker at all:** `<!-- … -->` comments and bare
angle-bracket tokens such as `<T>` pass through and become live HTML nodes, which can
silently swallow following content or clobber DOM globals (see OWASP's DOM Clobbering
cheat sheet). The v2.16.0 changelog records a related class of bug where an inline `<` in
documentation text once hung the parser.

**Root cause.** No sanitisation layer exists. CommonMark §6.10 intentionally passes raw
HTML through and assigns sanitisation to the host application; GFM §6.11 defines a
"Disallowed Raw HTML" extension for precisely this case, and GitHub additionally sanitises
after conversion. MD.Viewer implements neither.

### 2. `javascript:` URLs via reference-style links — **High**

```markdown
[click here][r]

[r]: javascript:alert(1)
```

```html
<a href="javascript:alert(1)" target="_blank" rel="noopener noreferrer" class="…">click here</a>
```

The reference-link pass escapes the URL for attribute context with `e()` but never inspects
the scheme. Inline links `[t](javascript:…)` and `[t](data:…)` are **not** affected, because
those passes only match `#…` or `https?://…` — a good design that the reference-link pass
does not share.

**Impact.** One click executes script in the page's origin.

### 3. No security response headers — **Medium**

Verified absent from every response: `Content-Security-Policy`, `X-Frame-Options` /
`frame-ancestors`, `Strict-Transport-Security`, `Referrer-Policy`, `Permissions-Policy`.
Present: `X-Content-Type-Options: nosniff` on the raw-download and updater landing
responses, and `Cache-Control: no-store` on downloads.

**Impact.** No browser-side backstop against findings 1 and 2; the page can be framed
(clickjacking); no HSTS pinning.

### 4. Mermaid runs with `securityLevel: 'loose'` — **Medium**

`js/md/md.js` initialises Mermaid with:

```js
mermaid.initialize({ startOnLoad: false, theme: …, securityLevel: 'loose',
                     suppressErrorRendering: true,
                     flowchart: { useMaxWidth: true, htmlLabels: true, curve: 'basis' } });
```

`loose` permits HTML in node labels and enables click callbacks. Untrusted diagram source is
therefore an additional script-capable surface, rendered client-side from a CDN module.

### 5. Third-party CDNs without integrity attributes — **Medium**

| Asset | Loaded by | SRI? |
|---|---|---|
| `https://cdn.tailwindcss.com` | `md.php` `<script src>` | **no** |
| `https://fonts.googleapis.com/css2?…` | `md.php` `<link rel=stylesheet>` | n/a for CSS, no `crossorigin` |
| `https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs` | `js/md/md.js` dynamic `import()` | **no**, and `@11` is a floating major version |

**Impact.** Compromise or takeover of any of those origins yields script execution on your
documentation pages, with no `integrity` attribute to detect tampering. `cdn.tailwindcss.com`
is additionally the development build of Tailwind and is documented by its authors as
unsuitable for production.

### 6. Update authenticity is not verified — **High, conditional**

See the next section. Conditional on `ALLOW_UPDATE = true` or a leaked `API_KEY`.

### 7. Information disclosure: the whole browse root is public — **Medium**

The whitelist is **extension-based, not document-based**. Any `.md` within depth 3 of the
browse root is listed and readable by anyone who can reach the URL — verified for
`README.md`. There is no per-document access control and no way to exclude a file other than
moving it out of the browse root or into a dot-directory (which the scanner skips).

### 8. `.md.ini` may be downloadable — **Medium, configuration-dependent**

`.md.ini` is read server-side only and never emitted by the application. But it is a dotfile
sitting in the web root, and whether it is *servable* is entirely up to your web server. If
it is, your `API_KEY` leaks. Block dotfiles — see below.

### 9. Minor: hard-coded `<html lang="ru">` — **Low**

The template emits `lang="ru"` regardless of document language. An accessibility and SEO
defect rather than a security one, but it is a correctness issue worth knowing about.

### 10. Minor: duplicate `MDV_CONFIG` assignment — **Informational**

The emitted HTML assigns `window.MDV_CONFIG` twice — first a minimal object, then the full
one. Harmless; the second wins.

---

## Update supply chain

`updater.php` downloads from a fixed origin and replaces your files:

```php
const RAW_BASE = 'https://raw.githubusercontent.com/paulmann/MD.Viewer/refs/heads/main';
```

Detection is two-layer: a conditional GET with a stored ETag (`If-None-Match`), then on
HTTP 200 a `hash_equals()` SHA-256 comparison of the payload against the local file. State
is kept in `md.backup/.state/{slug}.json` as `{etag, hash, updated_at}`. Writes are atomic
(`tempnam` → `LOCK_EX` write → `rename` → `chmod 0644`), and every replacement is preceded
by a copy into `md.backup/{localVersion}/`.

> [!IMPORTANT]
> **SHA-256 here is a change detector, not an authenticity proof.** There is no detached
> signature, no pinned commit SHA, and no checksum manifest published over a second channel.
> The trust anchors are: TLS to `raw.githubusercontent.com`, the continued availability and
> integrity of the `main` branch, and whoever holds write access to that branch. Anyone who
> can push to `main` can push code that every `ALLOW_UPDATE = true` installation will
> execute as the web-server user.

`CURLOPT_SSL_VERIFYPEER` is explicitly `true`. `CURLOPT_SSL_VERIFYHOST` is **not set** and
therefore inherits the libcurl default (2 since libcurl 7.10.0, released 2002), which is
correct on any modern system — but setting it explicitly costs nothing and removes the
dependency on a library default.

**Practical guidance:**

1. Keep `ALLOW_UPDATE = false` on production. This is the default and should stay that way.
2. Update deliberately from a shell or a staging host, then deploy the result.
3. If you want automatic updates, **fork the repository**, point `RAW_BASE` at your fork,
   and control who can push to it.
4. Test every update on a copy first. `ALLOW_RESTORE = true` plus
   `md.backup/{version}-pre-restore/` makes rollback reliable — verify it once on staging so
   you know it works.
5. Pin your own integrity baseline and compare after an update:

```bash
cd /var/www/html/docs
sha256sum md.php updater.php js/md/*.js css/md/*.css | tee /var/backups/mdviewer.sha256
# later, to verify nothing unexpected changed:
sha256sum -c /var/backups/mdviewer.sha256
```

```text
md.php: OK
updater.php: OK
js/md/md.js: OK
…
```

6. Restrict outbound HTTPS from the web server to `raw.githubusercontent.com` if the host
   does not need general egress. This limits what a compromised updater can fetch.

---

## Hardening, in priority order

### 1. Decide whether the content is trusted

This single decision determines everything else.

| Content source | Verdict |
|---|---|
| You and your team write the `.md` files, deploy via Git or SFTP | **Acceptable.** Apply items 2–6. |
| Anyone on the intranet can upload | **Risky.** Apply everything, add proxy sanitisation, put it on an isolated origin. |
| Anonymous internet users can upload or paste-and-save | **Do not enable upload.** Treat clipboard preview as an XSS generator on your origin. |
| You intend to render Markdown scraped or received from third parties | **Not suitable** without a sanitising proxy in front. |

### 2. Lock the flags

```ini
DISABLE_UPLOAD                 = true
DISABLE_CLIPBOARD              = true
DISABLE_SAVE_CLIPBOARD_TO_FILE = true
ALLOW_UPDATE                   = false
ALLOW_RESTORE                  = false
ALLOW_CREATE_INDEX_PHP_LINK    = false
```

This closes every write path and every maintenance path. `DISABLE_CLIPBOARD = true` also
closes the anonymous reflect-and-render endpoint, which is the easiest way to hand someone a
same-origin script-execution primitive.

```bash
chmod 0640 .md.ini && chown www-data:www-data .md.ini
```

### 3. Put it on its own origin

Because there is no authentication, the strongest mitigation for XSS is to make the origin
worthless to an attacker. Serve documentation from `docs.example.com` with **no cookies in
scope for that origin**, not from a path on `example.com` next to your application.

```nginx
server {
    listen 443 ssl http2;
    server_name docs.example.com;      # isolated origin, no shared cookies
    root /var/www/html/docs;
    index md.php;

    # The app sends no CSP; add one at the edge.
    add_header Content-Security-Policy "default-src 'none'; script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.tailwindcss.com; font-src 'self' https://fonts.gstatic.com; img-src * data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
    add_header Permissions-Policy "geolocation=(), microphone=(), camera=(), interest-cohort=()" always;
}
```

> [!WARNING]
> That CSP contains `'unsafe-inline'` for scripts, and therefore **does not block an
> injected inline `<script>` or `onerror=` handler**. It is forced: `cdn.tailwindcss.com`
> requires it. To get a strict `script-src 'self'` you must self-host a **compiled** Tailwind
> stylesheet and a local copy of Mermaid, then drop both CDN origins and `'unsafe-inline'`:
>
> ```nginx
> add_header Content-Security-Policy "default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src * data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'" always;
> ```
>
> Self-hosting requires editing the `<script src>` in `md.php` and the `import()` URL in
> `js/md/md.js`. Note that both files are tracked, so a `force` update will revert your
> edits — keep a patch and re-apply it, or maintain a fork. See [[Performance and Caching]].

Even a weak CSP still delivers real value: `frame-ancestors 'none'` stops clickjacking,
`connect-src 'self'` limits exfiltration to same-origin requests, and `default-src 'none'`
blocks object/embed/base.

### 4. Sanitise at the edge

If you cannot fork the renderer, sanitise its output in a reverse proxy or with an output
filter. Conceptually:

- Strip or escape every tag not in an allowlist (`p h1-h6 ul ol li blockquote pre code em
  strong del mark sub sup table thead tbody tr th td a img hr span section nav sup input br`).
- Drop every `on*` attribute.
- Allow `href`/`src` schemes `http`, `https`, `mailto`, `#` and relative paths only; drop
  `javascript:`, `data:`, `vbscript:`.
- Drop `id` and `name` attributes you do not need, to blunt DOM clobbering.

For a browser-side belt-and-braces layer you can inject [DOMPurify](https://github.com/cure53/dompurify)
after the article element and re-sanitise it, but that runs *after* the injected script has
already had its chance — it is a mitigation for stored content, not for inline payloads.
Edge sanitisation of the response body is strictly better.

### 5. Add authentication in front

The application has none. If the documents are not public, terminate authentication at the
web server:

```nginx
location / {
    auth_basic "Documentation";
    auth_basic_user_file /etc/nginx/.htpasswd;
    try_files $uri $uri/ /md.php$is_args$args;
}
```

Or use an identity-aware proxy (OAuth2 Proxy, Authelia, Authentik, your CDN's access
controls). This is also the only way to make `DISABLE_UPLOAD = false` defensible.

### 6. Restrict who can write to the browse root

Filesystem permissions are the real access control for content:

```bash
chown -R root:www-data /var/www/markdown
chmod -R 0750 /var/www/markdown
# The web user needs read, not write, when authors deploy via Git/CI:
chown -R ci-user:www-data /var/www/markdown
chmod -R 0770 /var/www/markdown
```

If the web user cannot write, then even a fully enabled upload feature cannot persist
anything.

---

## Reverse-proxy hardening

Beyond headers, an edge proxy is the right place for:

| Control | Why |
|---|---|
| Rate limiting on `POST md_preview=1` | It is a 2 MB render primitive; unlimited use is a cheap DoS |
| Request-body size limit ≤ 2 MB | Matches the application's own clipboard cap |
| Deny `updater.php` entirely | If you never use it, the strongest control is not routing to it |
| Deny `/.md.ini`, `/.state/`, `/md.backup/` | Config, ETag cache and every backed-up source file |
| Deny `/tools/` | PowerShell harness, no reason to serve it |
| Cache rendered pages | The app sends no `Cache-Control` on viewer pages — see [[Performance and Caching]] |

```nginx
# Never expose configuration, state or backups
location ~ /\.(md\.ini|state) { deny all; return 404; }
location ^~ /md.backup/       { deny all; return 404; }
location ^~ /tools/           { deny all; return 404; }

# Remove the updater from the attack surface if you do not use it
location = /updater.php       { deny all; return 404; }

limit_req_zone $binary_remote_addr zone=mdvpost:10m rate=5r/m;
location = /md.php {
    limit_req zone=mdvpost burst=10 nodelay;
    include fastcgi_params;
    fastcgi_pass unix:/run/php/php8.3-fpm.sock;
    fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
    client_max_body_size 2m;
}
```

---

## Web-server hardening

### Block dotfiles (Apache)

The repository ships **no `.htaccess`**; these are recommended additions, not project files.

```apache
# /var/www/html/docs/.htaccess
<FilesMatch "^\.">
    Require all denied
</FilesMatch>

# Never serve the backup tree or the updater state
RedirectMatch 404 ^/.*md\.backup/.*$
RedirectMatch 404 ^/.*\.state/.*$

# If you do not use the updater, remove it from the surface entirely
<Files "updater.php">
    Require all denied
</Files>

# Security headers (mod_headers)
Header always set X-Content-Type-Options "nosniff"
Header always set X-Frame-Options "DENY"
Header always set Referrer-Policy "strict-origin-when-cross-origin"
Header always set Content-Security-Policy "default-src 'none'; script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src * data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"

# Disable directory listing
Options -Indexes
```

### IIS

```xml
<!-- web.config -->
<configuration>
  <system.webServer>
    <security>
      <requestFiltering>
        <hiddenSegments>
          <add segment="md.backup" />
          <add segment=".state" />
          <add segment="tools" />
        </hiddenSegments>
        <fileExtensions>
          <add fileExtension=".ini" allowed="false" />
          <add fileExtension=".bak" allowed="false" />
        </fileExtensions>
        <requestLimits maxAllowedContentLength="2097152" />
      </requestFiltering>
    </security>
    <httpProtocol>
      <customHeaders>
        <add name="X-Content-Type-Options" value="nosniff" />
        <add name="X-Frame-Options" value="DENY" />
        <add name="Referrer-Policy" value="strict-origin-when-cross-origin" />
      </customHeaders>
    </httpProtocol>
  </system.webServer>
</configuration>
```

> [!NOTE]
> The `index.php` hard-link feature uses `link()`, which on Windows requires NTFS and the
> same volume. If you are on IIS with FAT or a cross-volume layout, leave
> `ALLOW_CREATE_INDEX_PHP_LINK = false`.

### PHP itself

```ini
; php.ini / pool config
expose_php = Off                 ; removes X-Powered-By
display_errors = Off             ; the app writes diagnostics to error_log by design
log_errors = On
error_log = /var/log/php/mdviewer-error.log
allow_url_fopen = Off            ; the updater uses cURL, not fopen wrappers
open_basedir = /var/www/html/docs:/var/www/markdown:/tmp
upload_max_filesize = 2M         ; matches the application's own cap
post_max_size = 3M
max_execution_time = 30
session.cookie_httponly = 1      ; irrelevant to the viewer, relevant to anything sharing the host
disable_functions = exec,passthru,shell_exec,system,proc_open,popen
```

`open_basedir` is a worthwhile second containment line behind the path validator: even a
validator bug cannot read outside the two directories the application legitimately needs.

---

## Filesystem and permissions

| Path | Owner | Mode | Needs write? |
|---|---|---|---|
| `md.php`, `updater.php`, `js/`, `css/` | deploy user | `0644` / `0755` | only during an update |
| `.md.ini` | `www-data` | `0640` | yes (auto-append) — and must not be web-readable |
| Browse root (documents) | author/CI user | `0755` | no, unless uploads are enabled |
| `uploads.md/` or `BROWSE_DIR` | `www-data` | `0755` | yes, if uploads are enabled |
| `md.backup/`, `md.backup/.state/` | `www-data` | `0755` | yes, if updates are enabled |

```bash
# Serve documents read-only; let nobody write via the web
chown -R root:www-data /var/www/html/docs
find /var/www/html/docs -type d -exec chmod 0755 {} \;
find /var/www/html/docs -type f -exec chmod 0644 {} \;
chmod 0640 /var/www/html/docs/.md.ini

# Only if you use the updater
chown -R www-data:www-data /var/www/html/docs/md.backup
chmod 0750 /var/www/html/docs/md.backup
```

> [!TIP]
> The updater writes files `0644` and creates directories `0755`. If your deployment user
> is not the web-server user, an update will fail on permissions — run updates as the web
> user, or pre-create the directories with a group both users share.

---

## Detection and logging

The application writes to the PHP error log with a `[MarkdownViewer]` prefix in these
situations — all of them worth alerting on:

| Log line | Meaning |
|---|---|
| `.md.ini BROWSE_DIR "…" cannot be resolved to a readable directory` | Misconfiguration, or an attempt to point the viewer elsewhere |
| `.md.ini BROWSE_DIR ignored: value is too long or contains a null byte` | Malformed or hostile config value |
| Per-directory `.md.ini` contained an install-level key | Someone tried to escalate via a directory file |
| A per-directory `.md.ini` value was unusable | Malformed or hostile value |
| `scanMarkdownFiles: reached max files limit (10000)` | Tree too large, or a scan under way |
| `scanMarkdownFiles: symlink escape detected: …` | **A symlink pointing out of the browse root — investigate immediately** |

Add web-server access-log rules for the paths that should never be requested:

```text
?file=..            ?file=/             ?file=%2e%2e
/md.backup/         /.md.ini            /.state/
?update=true        ?restore=           action=install
```

Note that a refused `?file=` returns **200**, so filter on the query string, not the status.

---

## Deployment decision matrix

| Scenario | Verdict | Required controls |
|---|---|---|
| Personal notes on localhost | Fine | none |
| Internal docs, read-only, trusted authors, isolated origin | **Recommended use** | Locked flags, edge headers, dotfile blocking |
| Internal docs behind SSO, uploads enabled for a known team | Acceptable with care | Authentication proxy, isolated origin, edge sanitisation, monitoring |
| Public documentation, only maintainers can write | Acceptable | Locked flags, CSP, HSTS, dotfile blocking, `ALLOW_UPDATE = false` |
| Public documentation with anonymous uploads | **Not recommended** | Would require forking the renderer to sanitise |
| Multi-tenant / rendering third-party Markdown | **Not suitable** | Not without a sanitising proxy and per-tenant isolation |
| Same origin as an authenticated application | **Not suitable** | Move it to its own hostname first |
| Host with `ALLOW_UPDATE = true` exposed to the internet | **Not acceptable** | Disable it; update from a shell |

---

## Pre-deployment checklist

```text
Content trust
[ ] Decided who can write .md files into the browse root
[ ] Browse root contains no private .md (everything in it is public)
[ ] No sensitive .md within depth 3 of the browse root

Flags
[ ] DISABLE_UPLOAD = true            (or the audience is authenticated and trusted)
[ ] DISABLE_CLIPBOARD = true         (unless you accept an anonymous render endpoint)
[ ] DISABLE_SAVE_CLIPBOARD_TO_FILE = true
[ ] ALLOW_UPDATE = false             on every production host
[ ] ALLOW_RESTORE = false            on every production host
[ ] ALLOW_CREATE_INDEX_PHP_LINK = false unless you use it
[ ] .md.ini is mode 0640 and owned by the web user

Network edge
[ ] Own origin, no cookies shared with any authenticated app
[ ] CSP header present (frame-ancestors 'none' at minimum)
[ ] X-Content-Type-Options: nosniff
[ ] X-Frame-Options: DENY  (or frame-ancestors)
[ ] HSTS on, if TLS
[ ] Referrer-Policy set
[ ] Dotfiles denied
[ ] /md.backup/, /.state/, /tools/ denied
[ ] /updater.php denied, if unused
[ ] Rate limit on POST /md.php
[ ] client_max_body_size / requestLimits ≤ 2 MB
[ ] Authentication in front, if the docs are not public

Host
[ ] expose_php = Off, display_errors = Off, log_errors = On
[ ] open_basedir restricted to the install dir + browse root + temp
[ ] allow_url_fopen = Off
[ ] Web user cannot write to the document tree (unless uploads are enabled)
[ ] Outbound HTTPS restricted, if the host does not need general egress

Updates
[ ] Update procedure documented and tested on staging
[ ] Rollback tested at least once (?restore=latest with ALLOW_RESTORE)
[ ] sha256sum baseline recorded
[ ] Considered forking and pointing RAW_BASE at the fork

Verification
[ ] curl -sI https://host/md.php shows your headers
[ ] curl -s  'https://host/md.php?file=../../etc/passwd' shows the denial banner
[ ] curl -s  'https://host/.md.ini' returns 403/404
[ ] curl -s  'https://host/md.backup/' returns 403/404
[ ] curl -s  'https://host/updater.php?update=true' returns 403
[ ] A test document containing <script> does NOT execute (if you added sanitisation)
```

---

## Reporting a security issue

Do **not** open a public GitHub issue for a security problem. Contact the author directly
at `Mikhail@Deynekin.com` with a minimal reproduction, the affected component versions
(from the ` * Version:` headers), and the configuration in force. The project has no
published security policy or CVE numbering authority; treat disclosure as coordinated and
private by default.

---

## See also

- [[Configuration Reference]] — every flag, its default and its exact effect
- [[File Upload and Clipboard]] — the write paths, and the validation they apply
- [[Self-Updater Guide]] — the update mechanism, backups and rollback in detail
- [[Machine API]] — `API_KEY` handling and the 403/400/405 responses
- [[Installation and Deployment]] — where to put the server-level rules above
- [[Markdown Extensions Matrix]] — the raw-HTML and reference-link behaviour, with examples
- [[Performance and Caching]] — self-hosting Tailwind and Mermaid to enable a strict CSP
- [OWASP Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [OWASP DOM Clobbering Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/DOM_Clobbering_Prevention_Cheat_Sheet.html)
- [GFM Spec §6.10 Raw HTML and §6.11 Disallowed Raw HTML](https://github.github.com/gfm/)
- [Mermaid `securityLevel` documentation](https://mermaid.js.org/config/security.html)
