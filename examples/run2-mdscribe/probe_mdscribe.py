#!/usr/bin/env python3
"""
probe_mdscribe_example.py — EXAMPLE for github-wiki-llm-writer: a full 249-check
empirical battery for a stateful PHP web app (MD.Scribe 3.1.0), demonstrating:

  * two staged deployment layouts in one run (ServedApp x2, custom serve_cmd);
  * stateful admin flows: first-run setup -> login -> CSRF rotation -> ~26
    authenticated JSON actions -> logout (the shape proposed for a probe
    "flow" primitive);
  * traversal / injection / flag-gating / render-matrix / machine-API /
    disk-side-effect batteries with pass-fail-observation records;
  * findings recorded as observations with FINDING notes (14 of them);
  * evidence as JSON + Markdown tables (kit convention).

Verified result on 2026-10-14 (PHP 8.3.35): 234 pass / 0 fail / 15 obs of 249.

PORTABILITY (env overrides):
  MDS_TOOLS_LIB  directory with the toolkit's serve.py/req.py
  MDS_REPO       subject clone WITH vendor/ installed (composer install)
  MDS_OUT_JSON / MDS_OUT_MD   evidence output paths

AGGREGATION SAFETY: this file contains NO literal triple-backtick sequences —
markdown fixtures carry code fences via the "@@F@@" placeholder expanded with
BT3 = chr(96)*3 at import. Reason: naive triple-backtick documentation
aggregators truncate sources containing literal fences (this file lost 74,557
of 74,558 bytes in the 2026-10-14 test run). See DEVELOPER-REPORT.md A11.

Original run location: wiki-work/workspace/probe/probe_mdscribe.py
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from html import unescape as html_unescape
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent            # run workspace when executed in place

# Portable locations (env overrides let this file run from anywhere):
#   MDS_TOOLS_LIB  — dir containing the toolkit's serve.py/req.py
#   MDS_REPO       — subject clone WITH vendor/ installed (composer install)
#   MDS_OUT_JSON / MDS_OUT_MD — evidence outputs
_TOOLS_LIB_CANDIDATES = [
    os.environ.get("MDS_TOOLS_LIB", ""),
    str(ROOT / "tools" / "lib"),
    str(Path.home() / "wiki-work" / "tools" / "lib"),
]
for _cand in _TOOLS_LIB_CANDIDATES:
    if _cand and Path(_cand, "serve.py").is_file():
        sys.path.insert(0, _cand)
        break
else:
    raise SystemExit("toolkit lib (serve.py) not found — set MDS_TOOLS_LIB")
from serve import ServedApp           # noqa: E402

REPO = os.environ.get("MDS_REPO") or str(ROOT / "workspace" / "repo" / "MD.Scribe")
OUT_JSON = Path(os.environ.get("MDS_OUT_JSON") or str(ROOT / "workspace" / "research" / "probe.json"))
OUT_MD = Path(os.environ.get("MDS_OUT_MD") or str(ROOT / "workspace" / "research" / "probe.md"))

CMD_A = "php -S {host}:{port} -t {root}/public {root}/public/router.php"   # layout A/C
CMD_B = "php -S {host}:{port} -t {root}"                                   # layout B (root docroot)

RECORDS: list[dict] = []
META = {"php": "", "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


# ─────────────────────────────────────────────────────────────────────────────
# HTTP client with cookie jar (no auto-redirect, so 302s are observable)
# ─────────────────────────────────────────────────────────────────────────────
class Resp:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers            # email.message.Message (get_all works)
        self.body = body

    @property
    def text(self):
        return self.body.decode("utf-8", "replace")

    def header(self, name):
        v = self.headers.get(name) if self.headers else None
        return v

    def headers_all(self, name):
        return self.headers.get_all(name) if self.headers else []

    def json(self):
        try:
            return json.loads(self.body)
        except Exception:
            return None


class Client:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            _NoRedirect(),
        )

    def req(self, path, method="GET", data=None, headers=None, timeout=30):
        url = path if path.startswith("http") else self.base + path
        r = urllib.request.Request(url, method=method, data=data, headers=headers or {})
        try:
            with self.opener.open(r, timeout=timeout) as resp:
                return Resp(resp.status, resp.headers, resp.read())
        except urllib.error.HTTPError as e:
            return Resp(e.code, e.headers, e.read())
        except Exception as e:
            return Resp("ERR", None, f"{type(e).__name__}: {e}".encode())

    def get(self, path, headers=None):
        return self.req(path, "GET", headers=headers)

    def post_form(self, path, fields, headers=None):
        h = {"Content-Type": "application/x-www-form-urlencoded"}
        h.update(headers or {})
        return self.req(path, "POST", urllib.parse.urlencode(fields).encode(), h)

    def post_json(self, path, obj, headers=None):
        h = {"Content-Type": "application/json"}
        h.update(headers or {})
        return self.req(path, "POST", json.dumps(obj).encode(), h)

    def post_multipart(self, path, fields, files, headers=None):
        boundary = uuid.uuid4().hex
        parts = []
        for k, v in (fields or {}).items():
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
        for k, (name, blob, ctype) in (files or {}).items():
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{name}\"\r\n"
                f"Content-Type: {ctype}\r\n\r\n".encode() + blob + b"\r\n"
            )
        parts.append(f"--{boundary}--\r\n".encode())
        h = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        h.update(headers or {})
        return self.req(path, "POST", b"".join(parts), h)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Evidence helpers
# ─────────────────────────────────────────────────────────────────────────────
def rec(group, name, *, req="", status=None, expect=None, markers=None,
        passed=None, note="", headers=None, excerpt=""):
    r = {
        "group": group, "name": name, "request": req,
        "status": str(status) if status is not None else None,
        "expect": expect, "markers": markers or {}, "passed": passed,
        "note": note, "headers": headers or {}, "excerpt": excerpt[:300],
    }
    RECORDS.append(r)
    flag = {True: "PASS", False: "FAIL", None: "obs"}[passed]
    print(f"  [{flag}] {group}: {name} -> {r['status']}")
    return r


def markers_in(text, needles: dict) -> dict:
    return {label: (n in text if isinstance(n, str) else bool(re.search(n, text)))
            for label, n in needles.items()}


def all_true(d: dict) -> bool:
    return all(bool(v) for v in d.values())


def csrf_from(html: str) -> str:
    for pat in (r'"csrf"\s*:\s*"([0-9a-f]{64})"',
                r'csrf\s*:\s*"([0-9a-f]{64})"',
                r'_token\s*:\s*"([0-9a-f]{64})"',
                r'name="_token"\s+value="([0-9a-f]{64})"'):
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return ""


def ini_get(path: Path, key: str) -> str:
    if not path.is_file():
        return ""
    for line in path.read_text().splitlines():
        m = re.match(rf"^{key}\s*=\s*(.*)$", line.strip())
        if m:
            return m.group(1).strip()
    return ""


PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)

# ─────────────────────────────────────────────────────────────────────────────
# Fixture documents
# ─────────────────────────────────────────────────────────────────────────────
FIXTURES = {
    "content/matrix.md": """---
title: Matrix Doc
description: Fixture for the render matrix
tags: [test, fixture]
author: Probe
draft: false
toc: true
numbering: true
---

# Matrix: Fixture

Intro paragraph with **bold**, *italic*, ***both***, ~~strike~~, `code`,
==marked==, H~2~O, E=mc^2^, :rocket: :tada: :unknown_code_xyz:, 12:30:45.

## Lists

- item one
- item two
  - nested child
  - another child
    - deep child

1. first
2. second
   1. nested ordered

- [ ] open task
- [x] done task

## Code

@@F@@php
<?php echo "hi";
@@F@@

@@F@@unknownlangxyz
plain fallback
@@F@@

@@F@@mermaid
graph TD
    A(Start) --> B{Decision}
    B -->|Yes| C(Finish (x))
@@F@@

Inline math $e^{i\\pi}+1=0$ and currency $5 and $10 stay prose.

$$\\int_{-\\infty}^{\\infty} e^{-x^2}\\,dx = \\sqrt{\\pi}$$

> [!NOTE]
> Note body.

> [!TIP]
> Tip body.

> [!IMPORTANT]
> Important body.

> [!WARNING]
> Warning body.

> [!CAUTION]
> Caution body.

> plain quote

Footnote ref[^1] and inline^[inline note] forms.

[^1]: footnote definition

Term One
: Definition of term one.

## Tables {#custom-id}

| Left | Center | Right |
|:-----|:------:|-------:|
| a    | b      | c      |

| Term | Definition |
| ---- | ---------- |
| CSP (Content Security Policy) | A browser policy header. |

![local image](img/pic.png "Caption text")

![external](https://example.com/pic.png)

[internal](getting-started.md) · [missing](definitely-missing.md) ·
[ext](https://example.com) · [anchor](#tables) · [bad](javascript:alert(1))

<https://autolink.example>

Term
: second definition list

Hard break below (two spaces)  
next line.

`<b>raw html escaped</b>`

<script>alert(1)</script>

<b>bold raw</b>

<div onmouseover="alert(1)">hover</div>

[TOC]

`(Client) --> [HTTP/1.1: uses] --> (Server)`
""",
    "content/draftdoc.md": "---\ntitle: Drafty\ndraft: true\n---\n\n# Drafty\n\nsecret draft body XYZZY42.\n",
    "content/cjk.md": "# CJK Doc\n\n中文文档测试内容在这里。日本語テキストもあります。한국어 텍스트.\n",
    "content/links.md": "# Links Doc\n\n[broken](no-such-doc.md)\n\n![missing media](img/nope.png)\n\n[anchor missing](#no-such-heading)\n",
    "content/orphan-candidate.md": "# Orphan\n\nNothing links here.\n",
    "content/unicode dir/документ — em.md": "# Юникод\n\nCyrillic and em dash filename works.\n",
    "content/share/.md.ini": "DISABLE_UPLOAD = false\nSITE_NAME = PWNED\n",
    "content/locked/.md.ini": "DISABLE_CLIPBOARD = true\n",
    "content/img/test.svg": "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1 1'><rect width='1' height='1'/></svg>\n",
    "content/img/notes.txt": "plain text asset\n",
    "content/img/archive.zip": b"PK\x05\x06" + b"\x00" * 18,
    "content/img/fake.exe": b"MZ\x90\x00fake",
}


# Fence-free source rule: the markdown fixtures above contain code fences, but
# this FILE must not contain literal triple-backtick sequences — documentation
# aggregators that embed sources into Markdown with naive fences would truncate
# it (happened for real: 1 byte of 74,558 survived the 2026-10-14 test run).
# "@@F@@" placeholders are expanded to real fences at import time.
BT3 = chr(96) * 3
FIXTURES["content/matrix.md"] = FIXTURES["content/matrix.md"].replace("@@F@@", BT3)


def stage_fixtures(app: ServedApp):
    for rel, body in FIXTURES.items():
        app.write(rel, body)


TRAVERSAL_PAYLOADS = [
    "../../../etc/passwd", "..\\..\\..\\windows\\win.ini", "/etc/passwd",
    "C:\\windows\\win.ini", "//etc/passwd",
    "..%2f..%2f..%2fetc%2fpasswd", "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "....//....//....//etc/passwd", "..%252f..%252fetc%252fpasswd",
    "%c0%ae%c0%ae/etc/passwd", "..%c0%af..%c0%afetc/passwd",
    "valid/../../../etc/passwd", "./../../etc/passwd",
    "/proc/self/environ", "..%00/..%00/etc/passwd", "etc/passwd%00.png",
    ".." * 40, "a/" * 60 + "b", "\x00", "../../" + "x" * 300,
    "../.md.ini", "..%2f.md.ini", "img/../../../.md.ini",
]

XSS_MARKDOWN = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "<svg onload=alert(1)>",
    '<iframe src="javascript:alert(1)"></iframe>',
    "<details open ontoggle=alert(1)>x</details>",
    '<a href="x" onclick="alert(1)">y</a>',
    '<form id=x><input name=y></form>',
    "[click](javascript:alert(1))",
    '[ref]: javascript:alert(2)\n\n[ref click][ref]',
    '<img src="data:text/html,<script>alert(1)</script>">',
    '<a href="&#106;avascript:alert(1)">ent</a>',
    '<div style="background:url(javascript:alert(1))">s</div>',
    "{{7*7}}", "${7*7}", "$(id)", "' OR '1'='1",
]


# ─────────────────────────────────────────────────────────────────────────────
# GROUP RUNNERS — instance A (docroot=public, router.php)
# ─────────────────────────────────────────────────────────────────────────────
def g_modes(c: Client):
    cases = [
        ("/", 200, {"home title": "MD.Scribe: Self-hosted docs, distilled"}),
        ("/index.php", 200, {"home title": "Self-hosted docs, distilled"}),
        ("/index.php?file=getting-started.md", 200, {"doc h1": "md-h1"}),
        ("/index.php?file=nope.md", 404, {"404 page": "Document not found"}),
        ("/index.php?page=browser", 200, {"library": "Library"}),
        ("/index.php?page=browser&dir=docs", 200, {"dir crumb": "docs"}),
        ("/index.php?page=browser&dir=../src", 404, {"refused": "Directory not found"}),
        ("/index.php?page=themes", 200, {"themes": "Themes"}),
        ("/index.php?page=settings", 200, {"settings": "Settings"}),
        ("/index.php?page=search&q=markdown", 200, {"search page": "Search"}),
        ("/index.php?page=bogus", 404, {"404": "Not found"}),
        ("/index.php?page=sitemap", 200, {"urlset": "<urlset"}),
        ("/index.php?page=feed", 200, {"rss": "<rss version=\"2.0\""}),
        ("/index.php?api=search&q=markdown", 200, {"json ok": '"ok":true'}),
        ("/index.php?api=suggest&q=getting", 200, {"json ok": '"ok":true'}),
        ("/index.php?api=toc&file=getting-started.md", 200, {"headings": '"headings"'}),
        ("/index.php?api=toc&file=nope.md", 404, {"not found": '"not found"'}),
        ("/index.php?api=config", 200, {"version": '"version":"3.1.0"'}),
        ("/index.php?api=bogus", 400, {"unknown": "unknown action"}),
        ("/index.php?media=img/pic.png", 200, {}),
        ("/index.php?media=img/nope.png", 404, {"text": "Not found."}),
        ("/nonexistent-pretty-url", 200, {"home (dev-router fallthrough)": "Self-hosted docs"}),
    ]
    for path, exp, needles in cases:
        r = c.get(path)
        m = markers_in(r.text, needles) if needles else {}
        rec("modes", path, req=f"GET {path}", status=r.status,
            expect=str(exp), markers=m,
            passed=(str(r.status) == str(exp) and all_true(m)),
            headers={k: r.header(k) for k in ("Content-Type",) if r.header(k)})


def g_headers(c: Client):
    r = c.get("/index.php?file=getting-started.md")
    want = {
        "Content-Security-Policy": "default-src 'self'",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=()",
        "Cross-Origin-Opener-Policy": "same-origin",
        "X-Powered-By": "MD.Scribe 3.1.0",
        "ETag": '"',
        "Last-Modified": "GMT",
        "Cache-Control": "max-age=3600",
    }
    m = {}
    for h, frag in want.items():
        v = r.header(h) or ""
        m[h] = frag in v
    csp = r.header("Content-Security-Policy") or ""
    m["csp nonce"] = bool(re.search(r"script-src 'self' 'nonce-[A-Za-z0-9+/=]+'", csp))
    m["csp object-none"] = "object-src 'none'" in csp
    m["csp frame-ancestors"] = "frame-ancestors 'self'" in csp
    rec("headers", "document response headers", req="GET /index.php?file=getting-started.md",
        status=r.status, markers=m, passed=all_true(m),
        headers={k: r.header(k) for k in want})

    r2 = c.get("/index.php?media=img/pic.png")
    m2 = markers_in(str(dict(r2.headers)), {"nosniff": "nosniff", "etag": "ETag",
                                             "cache 7d": "max-age=604800", "png": "image/png"})
    rec("headers", "media response headers", req="GET ?media=img/pic.png", status=r2.status,
        markers=m2, passed=all_true(m2))

    r3 = c.get("/index.php?page=browser")
    m3 = {"no-store": "no-store" in (r3.header("Cache-Control") or "")}
    rec("headers", "browser page is no-store", status=r3.status, markers=m3, passed=all_true(m3))

    # ETag → 304 round-trip
    etag = r.header("ETag")
    r4 = c.get("/index.php?file=getting-started.md", headers={"If-None-Match": etag or ""})
    rec("headers", "ETag 304 round-trip", req="GET with If-None-Match", status=r4.status,
        expect="304", passed=str(r4.status) == "304", note=f"etag={etag}")


def g_media_download(c: Client, app: ServedApp):
    cases = [
        ("?media=img/pic.png", 200, {"Content-Type": "image/png"}, "inline image"),
        ("?media=img/test.svg", 200, {"Content-Type": "image/svg+xml",
                                      "Content-Disposition": "attachment"}, "svg forced attachment"),
        ("?media=img/notes.txt", 200, {"Content-Type": "text/plain"}, "txt as text/plain"),
        ("?media=img/archive.zip", 200, {"Content-Type": "application/zip",
                                         "Content-Disposition": "attachment"}, "zip attachment"),
        ("?media=img/fake.exe", 404, {}, "extension outside allowlist"),
        ("?media=../src/Core/App.php", 404, {}, "traversal refused"),
        ("?media=../.md.ini", 404, {}, "ini never served"),
    ]
    for q, exp, hdrs, note in cases:
        r = c.get("/index.php" + q)
        m = {k: (v in (r.header(k) or "")) for k, v in hdrs.items()}
        rec("media", q, req="GET /index.php" + q, status=r.status, expect=str(exp),
            markers=m, passed=str(r.status) == str(exp) and all_true(m), note=note)

    r = c.get("/index.php?file=getting-started.md&download=1")
    cd = r.header("Content-Disposition") or ""
    m = {"octet-stream": r.header("Content-Type") == "application/octet-stream",
         "nosniff": r.header("X-Content-Type-Options") == "nosniff",
         "attachment": cd.startswith("attachment"),
         "rfc5987": "filename*=UTF-8''" in cd,
         "no-store": "no-store" in (r.header("Cache-Control") or "")}
    rec("media", "source download", req="GET ?file=…&download=1", status=r.status,
        markers=m, passed=str(r.status) == "200" and all_true(m),
        headers={"Content-Disposition": cd, "Content-Type": r.header("Content-Type")})

    r = c.get("/index.php?file=nope.md&download=1")
    rec("media", "download missing", req="GET ?file=nope.md&download=1", status=r.status,
        expect="404", excerpt=r.text[:40], passed=str(r.status) == "404" and r.text == "File not found.")


def g_traversal(c: Client):
    for p in TRAVERSAL_PAYLOADS:
        q = urllib.parse.quote(p, safe="")
        for param, exp in (("file", "404"), ("media", "404")):
            r = c.get(f"/index.php?{param}={q}")
            leaked = b"root:" in r.body or b"[extensions]" in r.body or b"API_KEY" in r.body
            rec("traversal", f"?{param}={p[:40]!r}", req=f"GET ?{param}=…", status=r.status,
                expect=exp, markers={"no leak": not leaked},
                passed=str(r.status) == exp and not leaked)
        r = c.get(f"/index.php?page=browser&dir={q}")
        if p == "\x00":
            rec("traversal", "?dir=NUL-only degrades to root listing", status=r.status,
                markers={"root library 200": r.status == 200 and "Library" in r.text}, passed=None,
                note="BrowserController trims the parameter and PHP trim() strips NUL — "
                     "an all-NUL dir becomes the root listing (no traversal); '%00foo' still 404s")
        else:
            rec("traversal", f"?dir={p[:40]!r}", status=r.status, expect="404",
                passed=str(r.status) == "404")


def g_api_post_gates(c: Client):
    home = c.get("/")
    token = csrf_from(home.text)
    rec("api-gates", "csrf token present in MDV_CONFIG", markers={"token": bool(token)},
        passed=bool(token))

    r = c.post_form("/index.php", {"api": ""})
    rec("api-gates", "POST without api", status=r.status, expect="400",
        excerpt=r.text[:80], passed=str(r.status) == "400" and "missing action" in r.text)

    r = c.post_form("/index.php?api=render", {"markdown": "# x"})
    rec("api-gates", "POST render without CSRF", status=r.status, expect="403",
        excerpt=r.text[:80], passed=str(r.status) == "403" and "csrf" in r.text)

    r = c.post_form("/index.php?api=bogus", {"_token": token})
    rec("api-gates", "POST unknown api with CSRF", status=r.status, expect="400",
        excerpt=r.text[:80], passed=str(r.status) == "400" and "unknown action" in r.text)

    r = c.post_form("/index.php?api=render", {"markdown": "# Hello\n\nbody", "_token": token})
    j = r.json() or {}
    rec("api-gates", "POST render with CSRF", status=r.status, expect="200",
        markers={"ok": j.get("ok") is True, "h1": "<h1" in (j.get("html") or "")},
        passed=str(r.status) == "200" and j.get("ok") is True)

    r = c.post_form("/index.php?api=render", {"markdown": "", "_token": token})
    rec("api-gates", "POST render empty", status=r.status, expect="400",
        excerpt=r.text[:90], passed=str(r.status) == "400")

    big = "x" * (4 * 1024 * 1024 + 10)
    r = c.post_form("/index.php?api=render", {"markdown": big, "_token": token})
    rec("api-gates", "POST render oversized (>4MB)", status=r.status, expect="400",
        excerpt=r.text[:90], passed=str(r.status) == "400")


def g_injection(c: Client, app: ServedApp):
    # reflected q in search page
    for payload in ["<script>alert(1)</script>", "\"><img src=x onerror=alert(1)>"]:
        r = c.get("/index.php?page=search&q=" + urllib.parse.quote(payload))
        raw_present = payload in r.text
        esc = payload.replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        rec("injection", f"search q={payload[:32]!r}", status=r.status,
            markers={"raw payload absent": not raw_present, "escaped form shown": esc in r.text},
            passed=(not raw_present), note="reflected into the search input value, escaped")
    for payload, evidence in [("{{7*7}}", "49"), ("${7*7}", "49"), ("$(id)", "uid="),
                              ("' OR '1'='1", "sqlstate"), ("%0d%0aX-Injected: yes", None)]:
        r = c.get("/index.php?page=search&q=" + urllib.parse.quote(payload))
        # Evaluation evidence must be scoped to WHERE the payload is reflected
        # (the search input's value): "49" occurs innocently elsewhere on the
        # page (sizes, timestamps, nonces) — a whole-page search is flaky.
        mv = re.search(r'name="q"[^>]*value="([^"]*)"', r.text)
        reflected = mv.group(1) if mv else ""
        executed = evidence is not None and evidence in reflected
        payload_inert = (payload.replace('"', "&quot;") in reflected) or (payload in html_unescape(reflected))
        hdr_inj = r.header("X-Injected") is not None
        rec("injection", f"search q={payload[:32]!r} (execution probe)", status=r.status,
            markers={"not executed at reflection point": not executed,
                     "payload reflected inert": payload_inert or payload.startswith("%0d"),
                     "no header injection": not hdr_inj},
            passed=(not executed and not hdr_inj), note="benign reflection as escaped text is OK")

    home = c.get("/")
    token = csrf_from(home.text)
    for payload in XSS_MARKDOWN:
        r = c.post_form("/index.php?api=render", {"markdown": payload, "_token": token})
        j = r.json() or {}
        html = j.get("html") or ""
        survived = bool(
            re.search(r"<script[\s>]", html) or re.search(r"<iframe[\s>]", html)
            or re.search(r"<form[\s>]", html) or re.search(r"<[a-z]+[^>]+\son(error|load|toggle|click)\s*=", html)
            or re.search(r'href\s*=\s*"\s*javascript:', html)
            or re.search(r"<[a-z]+[^>]+style\s*=\s\"[^\"]*url\(\s*['\"]?javascript:", html)
        )
        rec("injection", f"render {payload[:40]!r}", status=r.status,
            markers={"dangerous survived": survived}, passed=not survived,
            excerpt=re.sub(r"\s+", " ", html)[:160])

    # q= into JSON api
    r = c.get("/index.php?api=search&q=" + urllib.parse.quote("<script>alert(1)</script>"))
    ct = r.header("Content-Type") or ""
    rec("injection", "api search echoes query inside JSON (not HTML)", status=r.status,
        markers={"json content-type": ct.startswith("application/json"),
                 "nosniff": (r.header("X-Content-Type-Options") or "") == "nosniff"},
        passed=ct.startswith("application/json"),
        note="raw '<' may appear inside JSON strings; JSON CT + nosniff + CSP nonce make it inert")


def g_raw_html_modes(c: Client, app: ServedApp):
    # default: raw escaped
    home = c.get("/")
    token = csrf_from(home.text)
    r = c.post_form("/index.php?api=render", {"markdown": "<b>boldraw</b>", "_token": token})
    html = (r.json() or {}).get("html") or ""
    rec("rawhtml", "ALLOW_RAW_HTML=false escapes author HTML", status=r.status,
        markers={"escaped": "&lt;b&gt;boldraw&lt;/b&gt;" in html}, passed="&lt;b&gt;" in html,
        excerpt=html[:160])

    app.set_ini({"ALLOW_RAW_HTML": "true"})
    home = c.get("/")
    token = csrf_from(home.text)
    payload = ("<b>boldraw</b> <script>alert(1)</script> <img src=x onerror=alert(1)> "
               "<iframe src='https://x'></iframe> <div style='color:red'>s</div> "
               "<form><input></form> <svg><foreignObject>x</foreignObject></svg>")
    r = c.post_form("/index.php?api=render", {"markdown": payload, "_token": token})
    html = (r.json() or {}).get("html") or ""
    m = {"b kept": "<b>boldraw</b>" in html,
         "script dead": "<script" not in html,
         "onerror dead": "onerror" not in html,
         "iframe dead (ALLOW_IFRAMES=false)": "<iframe" not in html,
         "style kept+scrubbed or dropped": "color:red" in html or "style=" not in html,
         "form dead": "<form" not in html,
         "foreignObject dead": "foreignobject" not in html.lower()}
    rec("rawhtml", "ALLOW_RAW_HTML=true keeps+sanitizes", status=r.status, markers=m,
        passed=all_true(m), excerpt=re.sub(r"\s+", " ", html)[:280])

    app.set_ini({"ALLOW_IFRAMES": "true", "ALLOW_RAW_HTML": "true"})
    home = c.get("/")
    token = csrf_from(home.text)
    r = c.post_form("/index.php?api=render",
                    {"markdown": "<video src='v.mp4' controls></video>\n\n<audio src='a.mp3'></audio>\n\n"
                                "<iframe src='https://example.com'></iframe>", "_token": token})
    html = (r.json() or {}).get("html") or ""
    checks = {"video kept": "<video" in html, "audio kept": "<audio" in html,
              "iframe STILL escaped": "&lt;iframe" in html and "<iframe" not in html}
    rec("rawhtml", "ALLOW_RAW_HTML+ALLOW_IFRAMES: video/audio pass, iframe re-escaped", status=r.status,
        markers=checks, passed=all(checks.values()), excerpt=re.sub(r"\s+", " ", html)[:220],
        note="FINDING: league DisallowedRawHtmlExtension (registered whenever ALLOW_RAW_HTML=true) "
             "re-escapes <iframe> before the sanitizer; ALLOW_IFRAMES effectively governs "
             "video/audio/embed + CSP frame-src, never markdown-authored iframes")
    app.set_ini({"ALLOW_RAW_HTML": "false", "ALLOW_IFRAMES": "false"})


def g_matrix(c: Client, app: ServedApp):
    r = c.get("/index.php?file=matrix.md")
    t = r.text
    checks = {
        "status 200": r.status == 200,
        "frontmatter title used": "Matrix Doc" in t or "Fixture" in t,
        "eyebrow split (hero colon)": "md-hero" in t or "Matrix" in t,
        "strike": "<del>" in t or "<s>" in t,
        "mark ==": "<mark>" in t,
        "sub": "<sub>" in t,
        "sup": "<sup>" in t,
        "emoji rocket": "🚀" in t,
        "emoji tada": "🎉" in t,
        "unknown shortcode passthrough": ":unknown_code_xyz:" in t,
        "time passthrough": "12:30:45" in t,
        "nested list": "<ul>" in t and t.count("<ul>") >= 2,
        "task checkbox": 'type="checkbox"' in t,
        "php highlight (hljs)": "hljs" in t,
        "highlight token span": 'class="hljs-' in t,
        "unknown lang fallback": "plain fallback" in t,
        "code bar + copy": "md-code-bar" in t and "md-copy-btn" in t,
        "wrap toggle": "md-wrap-btn" in t,
        "mermaid block": 'class="mermaid"' in t and "data-mermaid-source" in t,
        "mermaid repair ran": "data-mermaid-fixes" in t,
        "math inline": 'mdx-math-inline' in t,
        "math block": 'mdx-math-block' in t,
        "currency safe ($5 ... $10)": "$5 and $10" in t,
        "alert note": "md-alert-note" in t,
        "alert tip": "md-alert-tip" in t,
        "alert important": "md-alert-important" in t,
        "alert warning": "md-alert-warning" in t,
        "alert caution": "md-alert-caution" in t,
        "plain quote + copy": "md-quote" in t,
        "footnote ref": "md-footnote-ref" in t,
        "footnote backref": "md-footnote-backref" in t,
        "inline footnote": "inline note" in t,
        "definition list": "<dl>" in t and "<dt>" in t,
        "table wrap": "md-table-wrap" in t,
        "table alignment": "text-align" in t or 'align=' in t or "md-align" in t or "data-align" in t,
        "glossary annotated": "data-gterm" in t or re.search(r'id="gd-', t),
        "glossary alias expanded": "Content Security Policy" in t,
        "image local via media route": "media=img" in t or "?media=" in t,
        "image lightbox attr": "data-lightbox" in t,
        "figure caption": "<figcaption>" in t,
        "image lazy": 'loading="lazy"' in t,
        "external image allowed by default": "https://example.com/pic.png" in t,
        "internal .md link rewritten": "file=getting-started.md" in t,
        "missing link marker": "md-link-missing" in t,
        "external link new tab": 'target="_blank"' in t and "noopener noreferrer" in t,
        "anchor link": 'href="#tables"' in t or "md-link-anchor" in t,
        "javascript: blocked": "md-link-blocked" in t and "javascript:alert" not in t,
        "autolink": "https://autolink.example" in t,
        "raw script escaped": "&lt;script&gt;" in t or "<script>alert" not in t,
        "raw b escaped (default)": "&lt;b&gt;bold raw&lt;/b&gt;" in t,
        "onmouseover not a live attribute": not re.search(r'<[a-z]+[^>]+onmouseover', t),
        "TOC placeholder inline": "md-toc-inline" in t,
        "TOC sidebar": "md-toc" in t,
        "heading numbers": "md-h-num" in t,
        "heading anchors": "md-anchor" in t,
        "hard break (2 spaces)": "<br>" in t,
        "soft break → br (DOUBLE_LINE_BREAKS)": t.count("<br>") >= 2,
        "universal pattern chain": "pattern-chain" in t and "pattern-node" in t,
        "reading time present": "readingMinutes" in t or "md-readtime" in t or "min read" in t,
    }
    rec("matrix", "matrix.md full render", req="GET ?file=matrix.md", status=r.status,
        markers=checks, passed=all(checks.values()),
        note="failed: " + ", ".join(k for k, v in checks.items() if not v))

    # external images off — first WITHOUT clearing the render cache (staleness finding)
    app.set_ini({"ALLOW_EXTERNAL_IMAGES": "false"})
    r = c.get("/index.php?file=matrix.md&_cb=1")
    stale = "https://example.com/pic.png" in r.text
    rec("matrix", "ALLOW_EXTERNAL_IMAGES=false on a cached doc (no cache clear)", status=r.status,
        markers={"serves stale cached HTML": stale}, passed=None,
        note="FINDING: ALLOW_EXTERNAL_IMAGES/ALLOW_IFRAMES are not part of the render-cache "
             "fingerprint (version+ALLOW_RAW_HTML+feature toggles only) — changes need "
             "cache.clear or a file touch" if stale else "cache missed; behaviour correct")
    cache_dir = Path(app.root) / "storage" / "cache"
    for f in cache_dir.glob("*.json"):
        f.unlink()
    r = c.get("/index.php?file=matrix.md&_cb=2")
    t = r.text
    checks = {"blocked note": "Image blocked by server policy" in t,
              "ext url gone": "https://example.com/pic.png" not in t}
    rec("matrix", "ALLOW_EXTERNAL_IMAGES=false after cache clear", status=r.status,
        markers=checks, passed=all(checks.values()))
    app.set_ini({"ALLOW_EXTERNAL_IMAGES": "true"})
    for f in cache_dir.glob("*.json"):
        f.unlink()

    # draft behaviour
    r = c.get("/index.php?file=draftdoc.md")
    br = c.get("/index.php?page=browser")
    sm = c.get("/index.php?page=sitemap")
    fd = c.get("/index.php?page=feed")
    sr = c.get("/index.php?api=search&q=XYZZY42")
    checks = {"direct ?file= 404": r.status == 404,
              "listed in browser": "draftdoc" in br.text,
              "listed in sitemap": "draftdoc" in sm.text,
              "listed in feed": "draftdoc" in fd.text,
              "found by search": "draftdoc" in sr.text}
    rec("matrix", "draft:true — direct render 404s BUT corpus listings include it",
        markers=checks, passed=None,
        note="FINDING: docs/markdown-features.md claims 'hidden from library/search/feeds'; "
             "3.1.0 filters drafts only in ViewerController::renderDocument — scan()/SearchIndex/"
             "sitemap/feed include them (clicking a listed draft 404s)")

    # unicode filename
    r = c.get("/index.php?file=" + urllib.parse.quote("unicode dir/документ — em.md"))
    rec("matrix", "unicode (cyrillic + em dash) filename", status=r.status, expect="200",
        markers={"rendered": "Юникод" in r.text}, passed=r.status == 200 and "Юникод" in r.text)

    # CJK search
    r = c.get("/index.php?api=search&q=" + urllib.parse.quote("文档"))
    j = r.json() or {}
    paths = [x.get("path") for x in j.get("results", [])]
    rec("matrix", "CJK bigram search", status=r.status,
        markers={"cjk.md found": "cjk.md" in paths}, passed="cjk.md" in paths,
        excerpt=json.dumps(paths)[:120])

    # suggest kinds
    r = c.get("/index.php?api=suggest&q=Matrix")
    j = r.json() or {}
    kinds = {x.get("kind") for x in j.get("results", [])}
    rec("matrix", "suggest returns doc+heading kinds", status=r.status,
        markers={"kinds": bool(kinds)}, passed=bool(j.get("ok")), excerpt=json.dumps(j)[:200])


def g_attributes(c: Client, app: ServedApp):
    md = ("# Attr Test\n\nParagraph with attrs {#para-id .para-class}\n\n"
          "## Heading {#custom-id .extra-class}\n\n![img](img/pic.png){width=300 .fig}\n")
    app.write("content/attr.md", md)
    r = c.get("/index.php?file=attr.md")
    t = r.text
    checks = {
        "paragraph attrs applied": ('id="para-id"' in t and "para-class" in t),
        "heading {#id} OVERRIDDEN by auto-slug": ('id="heading"' in t and "custom-id" not in t),
        "heading {.class} dropped": "extra-class" not in t,
        "image {width} ignored": "width=300" not in t and 'width="300"' not in t,
    }
    rec("attributes", "{#id .class} support per element type", status=r.status, markers=checks,
        passed=None,
        note="FINDING: docs claim attributes on blocks AND images; paragraphs/divs honour them "
             "(ParagraphRenderer), headings get the auto slug instead (HeadingRenderer mdv_id) and "
             "ImageRenderer ignores attribute nodes")


def g_search_api(c: Client):
    r = c.get("/index.php?api=search&q=markdown&limit=2")
    j = r.json() or {}
    checks = {"ok": j.get("ok") is True, "limit respected": len(j.get("results", [])) <= 2,
              "took_ms": "took_ms" in j, "total": "total" in j,
              "snippet has mark or text": all("snippet" in x for x in j.get("results", []))}
    rec("search", "api=search limit=2", status=r.status, markers=checks, passed=all(checks.values()),
        excerpt=json.dumps(j)[:220])

    long_q = "x" * 201
    r = c.get("/index.php?api=search&q=" + long_q)
    j = r.json() or {}
    rec("search", "q > 200 chars → empty", status=r.status,
        markers={"total 0": j.get("total") == 0}, passed=j.get("total") == 0)

    r = c.get("/index.php?api=search&q=")
    j = r.json() or {}
    rec("search", "empty q → empty", markers={"total 0": j.get("total") == 0}, passed=j.get("total") == 0)


def g_flags_hardlock_cookie(c: Client, app: ServedApp):
    # visitor cookie toggle: AUTO_TOC off via cookie
    r = c.get("/index.php?file=getting-started.md", headers={"Cookie": "mdv_feat_AUTO_TOC=0"})
    checks = {"no sidebar toc": 'id="md-toc-sidebar"' not in r.text, "still 200": r.status == 200}
    rec("flags", "cookie mdv_feat_AUTO_TOC=0 hides TOC", status=r.status, markers=checks,
        passed=all(checks.values()), note="visitor-level toggle")

    # hard lock via ini wins over cookie
    app.set_ini({"AUTO_TOC": "false"})
    r = c.get("/index.php?file=getting-started.md", headers={"Cookie": "mdv_feat_AUTO_TOC=1"})
    checks = {"toc still hidden": 'id="md-toc-sidebar"' not in r.text}
    rec("flags", "ini AUTO_TOC=false hard-locks over cookie=1", status=r.status,
        markers=checks, passed=all(checks.values()))
    ini_txt = (Path(app.root) / ".md.ini").read_text()
    rec("flags", "hard-locked key persisted to .md.ini", markers={"AUTO_TOC line": "AUTO_TOC = false" in ini_txt},
        passed="AUTO_TOC = false" in ini_txt)
    app.set_ini({"AUTO_TOC": ""})   # clear value → falsy? parseBool('')=False; better remove line
    ini_p = Path(app.root) / ".md.ini"
    txt = "\n".join(l for l in ini_p.read_text().splitlines() if not l.strip().startswith("AUTO_TOC"))
    ini_p.write_text(txt)

    # search disabled hard lock
    app.set_ini({"FEATURE_SEARCH": "false"})
    r = c.get("/index.php?api=search&q=markdown")
    j = r.json() or {}
    r2 = c.get("/index.php?page=search&q=x")
    checks = {"api 403": r.status == 403, "api error": j.get("error") == "search disabled",
              "page 404": r2.status == 404}
    rec("flags", "FEATURE_SEARCH=false gates API+page", markers=checks, passed=all(checks.values()))
    txt = "\n".join(l for l in ini_p.read_text().splitlines() if not l.strip().startswith("FEATURE_SEARCH"))
    ini_p.write_text(txt)

    # feeds gates
    app.set_ini({"SITEMAP_ENABLED": "false", "RSS_ENABLED": "false"})
    r = c.get("/index.php?page=sitemap")
    r2 = c.get("/index.php?page=feed")
    checks = {"sitemap 404": r.status == 404 and "Sitemap disabled." in r.text,
              "feed 404": r2.status == 404 and "Feed disabled." in r2.text}
    rec("flags", "SITEMAP/RSS_ENABLED=false", markers=checks, passed=all(checks.values()))
    txt = "\n".join(l for l in ini_p.read_text().splitlines()
                    if not (l.strip().startswith("SITEMAP_ENABLED") or l.strip().startswith("RSS_ENABLED")))
    ini_p.write_text(txt)


def g_per_dir_flags(c: Client, app: ServedApp):
    home = c.get("/")
    token = csrf_from(home.text)
    # base DISABLE_UPLOAD default true → root upload refused
    r = c.post_multipart("/index.php?api=upload", {"dir": "", "_token": token},
                         {"file": ("t.md", b"# t\n", "text/markdown")})
    j = r.json() or {}
    rec("perdir", "upload to root refused (DISABLE_UPLOAD=true)", status=r.status, expect="403",
        markers={"error": j.get("error") == "Uploads are disabled for this directory."},
        passed=r.status == 403)

    # share/ has per-dir DISABLE_UPLOAD=false → allowed
    r = c.post_multipart("/index.php?api=upload", {"dir": "share", "_token": token},
                         {"file": ("uploaded doc.md", b"# Uploaded\n\nbody\n", "text/markdown")})
    j = r.json() or {}
    rec("perdir", "upload to share/ allowed by per-dir ini", status=r.status, expect="200",
        markers={"ok": j.get("ok") is True, "path": j.get("path") == "share/uploaded doc.md"},
        passed=j.get("ok") is True, excerpt=json.dumps(j)[:160])

    # collision → -1 suffix
    r = c.post_multipart("/index.php?api=upload", {"dir": "share", "_token": token},
                         {"file": ("uploaded doc.md", b"# second\n", "text/markdown")})
    j = r.json() or {}
    rec("perdir", "collision-safe rename", markers={"-1 suffix": j.get("path") == "share/uploaded doc-1.md"},
        passed=j.get("path") == "share/uploaded doc-1.md", excerpt=json.dumps(j)[:140])

    # bad filenames
    for name, why in [("evil.php", "extension"), (".hidden.md", "dotfile"),
                      ("a" * 300 + ".md", "too long"), ("no-ext", "no .md")]:
        r = c.post_multipart("/index.php?api=upload", {"dir": "share", "_token": token},
                             {"file": (name, b"# x\n", "text/markdown")})
        j = r.json() or {}
        rec("perdir", f"upload refuses {why} ({name[:20]!r})", status=r.status, expect="400",
            markers={"error msg": "Invalid filename" in (j.get("error") or "")},
            passed=r.status == 400, excerpt=(j.get("error") or "")[:100])
    r = c.post_multipart("/index.php?api=upload", {"dir": "share", "_token": token},
                         {"file": ("../evil.md", b"# x\n", "text/markdown")})
    j = r.json() or {}
    landed_inside = (Path(app.root) / "content" / "share" / "evil.md").is_file()
    escaped_root = (Path(app.root) / "content" / "evil.md").is_file() or (Path(app.root) / "evil.md").is_file()
    rec("perdir", "upload filename '../evil.md' (PHP strips the path)", status=r.status,
        markers={"saved inside share/": landed_inside, "nothing outside": not escaped_root},
        passed=landed_inside and not escaped_root,
        note="PHP reduces multipart filenames to a basename before the app sees them; "
             "sanitizeFilename independently refuses any '/' or '\\'", excerpt=json.dumps(j)[:120])

    # unicode filename upload
    r = c.post_multipart("/index.php?api=upload", {"dir": "share", "_token": token},
                         {"file": ("новый док.md", "# Новый\n".encode("utf-8"), "text/markdown")})
    j = r.json() or {}
    rec("perdir", "unicode upload accepted", status=r.status,
        markers={"ok": j.get("ok") is True}, passed=j.get("ok") is True, excerpt=json.dumps(j)[:140])

    # clipboard render gate in locked/
    r = c.post_form("/index.php?api=render", {"markdown": "# x", "dir": "locked", "_token": token})
    j = r.json() or {}
    rec("perdir", "api=render refused in locked/ (DISABLE_CLIPBOARD)", status=r.status, expect="403",
        markers={"error": "disabled for this directory" in (j.get("error") or "")}, passed=r.status == 403)

    # save-to-file gate (DISABLE_SAVE_CLIPBOARD_TO_FILE=true default)
    r = c.post_form("/index.php?api=save",
                    {"content": "# s", "filename": "saved.md", "dir": "share", "_token": token})
    j = r.json() or {}
    rec("perdir", "api=save refused by default flag", status=r.status, expect="403",
        markers={"error": "Saving clipboard content is disabled" in (j.get("error") or "")},
        passed=r.status == 403)

    # per-dir SITE_NAME (installation key) must be ignored
    r = c.get("/index.php?page=browser&dir=share")
    rec("perdir", "installation key in dir ini ignored", markers={"title not PWNED": "PWNED" not in r.text},
        passed="PWNED" not in r.text)


def g_zerocdn(c: Client):
    pages = ["/", "/index.php?page=browser", "/index.php?page=themes",
             "/index.php?file=getting-started.md", "/index.php?page=settings"]
    ext = {}
    res_pats = [
        r'<script[^>]+src="(https?://[^"]+)"',
        r'<link[^>]+rel="stylesheet"[^>]+href="(https?://[^"]+)"',
        r'<link[^>]+href="(https?://[^"]+)"[^>]+rel="stylesheet"',
        r'<img[^>]+src="(https?://[^"]+)"',
        r'<iframe[^>]+src="(https?://[^"]+)"',
        r'<source[^>]+src="(https?://[^"]+)"',
        r'url\(\s*["\']?(https?://[^)\'"]+)',
        r'@import\s+["\']?(https?://[^"\');]+)',
    ]
    for p in pages:
        r = c.get(p)
        for pat in res_pats:
            for m in re.finditer(pat, r.text):
                host = urllib.parse.urlparse(m.group(1)).netloc
                ext.setdefault(host, set()).add(p)
    allowed = {"www.w3.org"}  # XML/SVG namespaces are identifiers, not fetches
    bad = {h: sorted(ps) for h, ps in ext.items() if h not in allowed}
    rec("zerocdn", "no third-party runtime URLs in HTML", markers={"external hosts": json.dumps(bad)[:200]},
        passed=not bad, note="namespaces (www.w3.org) excluded — never fetched")


# ─────────────────────────────────────────────────────────────────────────────
# Admin flows (instance A)
# ─────────────────────────────────────────────────────────────────────────────
def g_admin_setup_login(c: Client, app: ServedApp):
    r = c.get("/admin.php")
    loc = r.header("Location") or ""
    rec("admin", "first visit → 302 setup", status=r.status, expect="302",
        markers={"loc setup": "page=setup" in loc}, passed=r.status == 302 and "setup" in loc,
        headers={"Location": loc})

    r = c.get("/admin.php?page=setup")
    token = csrf_from(r.text)
    rec("admin", "setup page 200 + token", status=r.status, markers={"token": bool(token),
        "localhost allowed": "localhost" in r.text.lower() or token != ""}, passed=r.status == 200 and bool(token))

    r = c.post_form("/admin.php?action=setup", {"password": "short"})
    rec("admin", "setup POST without CSRF → 403", status=r.status, expect="403",
        excerpt=r.text[:80], passed=r.status == 403 and "CSRF" in r.text)

    r = c.post_form("/admin.php?action=setup", {"password": "short", "_token": token})
    j = r.json() or {}
    rec("admin", "setup short password → 400", status=r.status, expect="400",
        markers={"error": "shorter than 10" in (j.get("error") or "")}, passed=r.status == 400)

    setup_log = Path(app.root) / "storage" / "logs" / "setup.log"
    rec("admin", "setup.log NOT created for localhost visits (lazy)", markers={"absent": not setup_log.exists()},
        passed=None,
        note="docs/admin-guide.md says 'written on first visit' — code writes it only when a "
             "NON-localhost setup POST is attempted (AdminAuth::setupCode, called from setup())")
    import subprocess
    cli = subprocess.run(
        ["php", "-r",
         "require 'src/bootstrap.php'; MdViewer\\Core\\Paths::setRoot(getcwd()); "
         "$a = new MdViewer\\Admin\\AdminAuth(MdViewer\\Core\\Config::instance(), "
         "new MdViewer\\Core\\Session(), MdViewer\\Core\\Request::fromGlobals('/x',''), "
         "new MdViewer\\Core\\Logger(), new MdViewer\\Core\\AuditLog()); "
         "echo $a->setupCode();"],
        cwd=str(app.root), capture_output=True, text=True, timeout=30)
    code = cli.stdout.strip()
    mode = oct(setup_log.stat().st_mode & 0o777) if setup_log.exists() else ""
    rec("admin", "setupCode() mechanism via CLI", markers={"32 hex": bool(re.fullmatch(r"[a-f0-9]{32}", code)),
        "mode 0600": mode == "0o600"}, passed=bool(re.fullmatch(r"[a-f0-9]{32}", code or "")) and mode == "0o600",
        note=f"file mode {mode}")
    setup_log.unlink(missing_ok=True)

    # from localhost the code may be omitted
    r = c.post_form("/admin.php?action=setup", {"code": "", "password": "probe-password-123", "_token": token})
    j = r.json() or {}
    rec("admin", "setup from localhost (no code) → ok", status=r.status, expect="200",
        markers={"ok": j.get("ok") is True, "redirect login": "page=login" in (j.get("redirect") or "")},
        passed=j.get("ok") is True, excerpt=json.dumps(j)[:140])
    rec("admin", "setup.log deleted after setup", markers={"gone": not setup_log.exists()},
        passed=not setup_log.exists())

    # already configured
    home = c.get("/admin.php?page=login")
    t2 = csrf_from(home.text)
    r = c.post_form("/admin.php?action=setup", {"code": "", "password": "another-pass-123", "_token": t2})
    rec("admin", "second setup → 409", status=r.status, expect="409", passed=r.status == 409)

    # wrong login
    r = c.post_form("/admin.php?action=login",
                    {"username": "admin", "password": "wrong-password", "_token": t2})
    rec("admin", "login wrong password → 401", status=r.status, expect="401",
        excerpt=r.text[:90], passed=r.status == 401)

    # rate limit: default 10 → exhaust (9 more) then expect 429
    statuses = []
    for i in range(12):
        rr = c.post_form("/admin.php?action=login",
                         {"username": "admin", "password": "wrong-password", "_token": t2})
        statuses.append(rr.status)
        if rr.status == 429:
            jj = rr.json() or {}
            rec("admin", "rate limit → 429 with lock seconds", status=rr.status,
                markers={"locked field": isinstance(jj.get("locked"), int),
                         "error text": "Too many attempts" in (jj.get("error") or "")},
                passed=True, excerpt=rr.text[:120])
            break
    else:
        rec("admin", "rate limit → 429", markers={"statuses": str(statuses)}, passed=False)

    # unlock: remove the state file (simulates window expiry) then login ok
    state = Path(app.root) / "storage" / "state"
    for f in state.glob("login-*.json"):
        f.unlink()
    r = c.post_form("/admin.php?action=login",
                    {"username": "admin", "password": "probe-password-123", "_token": t2})
    j = r.json() or {}
    rec("admin", "login ok → 200 + redirect", status=r.status, expect="200",
        markers={"ok": j.get("ok") is True}, passed=j.get("ok") is True)

    # GET login action → 405
    r = c.get("/admin.php?action=login")
    rec("admin", "login via GET → 405", status=r.status, expect="405", passed=r.status == 405)

    # authenticated page
    r = c.get("/admin.php?page=dashboard")
    rec("admin", "dashboard after login", status=r.status, expect="200",
        markers={"dashboard": "Dashboard" in r.text, "noindex": (r.header("X-Robots-Tag") or "") == "noindex, nofollow",
                 "no-store": "no-store" in (r.header("Cache-Control") or "")},
        passed=r.status == 200 and "Dashboard" in r.text)
    return csrf_from(r.text) or t2


def g_admin_unauth(c2: Client):
    lg = c2.get("/admin.php?page=login")
    tok = csrf_from(lg.text)
    r = c2.post_form("/admin.php?action=index.stats", {"_token": tok})
    rec("admin-unauth", "action with CSRF but no login → 401", status=r.status, expect="401",
        excerpt=r.text[:80], passed=r.status == 401 and "unauthorized" in r.text)
    r = c2.get("/admin.php")
    loc = r.header("Location") or ""
    rec("admin-unauth", "page without session → 302 login", status=r.status,
        markers={"loc login": "page=login" in loc}, passed=r.status == 302)


def g_admin_actions(c: Client, token: str, app: ServedApp):
    H = {"X-CSRF-Token": token}

    def act(action, fields=None, method="post_form", qs="", jbody=None, expect=200, group="admin-actions"):
        url = f"/admin.php?action={action}{qs}"
        if method == "post_form":
            r = c.post_form(url, fields or {}, headers=H)
        elif method == "post_json":
            r = c.post_json(url, jbody or {}, headers=H)
        elif method == "get":
            r = c.get(url, headers=H)
        else:
            r = c.post_multipart(url, (fields or {}), jbody or {}, headers=H)
        return r

    r = act("index.stats", method="get")
    j = r.json() or {}
    rec("admin-actions", "index.stats", status=r.status, markers={"documents": "documents" in j,
        "fresh field": "fresh" in j}, passed=j.get("ok") is True, excerpt=json.dumps(j)[:160])

    r = act("index.rebuild")
    j = r.json() or {}
    rec("admin-actions", "index.rebuild", status=r.status, markers={"took_ms": "took_ms" in j,
        "terms": "terms" in j}, passed=j.get("ok") is True, excerpt=json.dumps(j)[:160])

    r = act("health.run", method="get")
    j = r.json() or {}
    ids = [c_.get("id") for c_ in j.get("checks", [])]
    fails = [c_ for c_ in j.get("checks", []) if c_.get("status") == "fail"]
    rec("admin-actions", "health.run", status=r.status,
        markers={"checks >= 20": len(ids) >= 20, "version": j.get("version") == "3.1.0"},
        passed=j.get("ok") is True and len(ids) >= 20,
        excerpt=f"{len(ids)} checks; ids={','.join(map(str, ids))}; fails={[f.get('id') for f in fails]}")

    r = act("links.check", method="get")
    j = r.json() or {}
    bl = j.get("broken_links", [])
    bm = j.get("broken_media", [])
    orph = j.get("orphans", [])
    checks = {"found broken link": any("no-such-doc.md" in str(x) for x in bl),
              "found broken media": any("nope.png" in str(x) for x in bm),
              "found dead anchor": any("no-such-heading" in str(x) for x in bl),
              "found orphan": any("orphan-candidate" in str(x) for x in orph)}
    rec("admin-actions", "links.check finds all 4 fixture problems", status=r.status,
        markers=checks, passed=all(checks.values()),
        excerpt=json.dumps({"bl": bl[:4], "bm": bm[:2], "orph": orph[:4]})[:280])

    r = act("file.read", qs="&path=getting-started.md", method="get")
    j = r.json() or {}
    h = j.get("hash")
    rec("admin-actions", "file.read → content+hash", markers={"ok": j.get("ok") is True, "sha256": bool(re.fullmatch(r"[a-f0-9]{64}", h or ""))},
        passed=j.get("ok") is True)

    r = act("file.write", {"path": "getting-started.md", "content": "clobber", "hash": "0" * 64})
    rec("admin-actions", "file.write hash mismatch → 409", status=r.status, expect="409",
        excerpt=r.text[:100], passed=r.status == 409 and "changed on disk" in r.text)

    r = act("file.write", {"path": "getting-started.md", "content": "clobber", "hash": h})
    rec("admin-actions", "file.write correct hash → ok", status=r.status,
        markers={"ok": (r.json() or {}).get("ok") is True}, passed=(r.json() or {}).get("ok") is True)
    # restore original content from repo
    orig = (Path(REPO) / "content" / "getting-started.md").read_text()
    r = act("file.read", qs="&path=getting-started.md", method="get")
    h2 = (r.json() or {}).get("hash")
    act("file.write", {"path": "getting-started.md", "content": orig, "hash": h2})

    r = act("file.create", {"path": "probe/new-dir/probe-doc.md", "content": "# Probe\n"})
    rec("admin-actions", "file.create with new folders", markers={"ok": (r.json() or {}).get("ok") is True},
        passed=(r.json() or {}).get("ok") is True, excerpt=r.text[:120])

    r = act("file.rename", {"from": "probe/new-dir/probe-doc.md", "to": "probe/renamed.md"})
    rec("admin-actions", "file.rename", markers={"ok": (r.json() or {}).get("ok") is True},
        passed=(r.json() or {}).get("ok") is True, excerpt=r.text[:120])

    r = act("file.move", {"from": "probe/renamed.md", "to_dir": "probe/sub"})
    rec("admin-actions", "file.move", markers={"ok": (r.json() or {}).get("ok") is True},
        passed=(r.json() or {}).get("ok") is True, excerpt=r.text[:120])

    r = act("file.write", {"path": "probe/evil.md", "content": "x", "hash": None})
    # path traversal via admin API
    r = act("file.read", qs="&path=../../etc/passwd", method="get")
    j = r.json() or {}
    rec("admin-actions", "file.read traversal refused", markers={"not ok": j.get("ok") is not True},
        passed=j.get("ok") is not True, excerpt=r.text[:120])

    r = act("file.delete", {"path": "probe/sub/renamed.md"})
    rec("admin-actions", "file.delete → trash", markers={"ok": (r.json() or {}).get("ok") is True},
        passed=(r.json() or {}).get("ok") is True, excerpt=r.text[:120])
    trash = list((Path(app.root) / "storage" / "backups" / "trash").glob("*"))
    rec("admin-actions", "trash file exists on disk", markers={"count>=1": len(trash) >= 1},
        passed=len(trash) >= 1, note=str([t.name for t in trash]))

    r = act("trash.list", method="get")
    items = (r.json() or {}).get("items", [])
    rec("admin-actions", "trash.list", markers={"items": len(items) >= 1}, passed=len(items) >= 1,
        excerpt=json.dumps(items)[:160])
    if items:
        r = act("trash.restore", {"name": items[0].get("name")})
        rec("admin-actions", "trash.restore", markers={"ok": (r.json() or {}).get("ok") is True},
            passed=(r.json() or {}).get("ok") is True, excerpt=r.text[:140])

    r = act("folder.create", {"path": "probe/empty-folder"})
    rec("admin-actions", "folder.create", markers={"ok": (r.json() or {}).get("ok") is True},
        passed=(r.json() or {}).get("ok") is True)
    r = act("folder.delete", {"path": "probe"})
    j = r.json() or {}
    rec("admin-actions", "folder.delete non-empty refused", markers={"not ok": j.get("ok") is not True},
        passed=j.get("ok") is not True, excerpt=r.text[:120])

    # uploads via admin (bypass DISABLE_UPLOAD=true)
    r = act("upload.md", {"dir": ""}, method="multipart",
            jbody={"file": ("admin upload.md", b"# Admin upload\n", "text/markdown")})
    j = r.json() or {}
    rec("admin-actions", "admin upload.md with DISABLE_UPLOAD=true (default)", status=r.status,
        markers={"refused 403": r.status == 403}, passed=None, excerpt=r.text[:140],
        note="FINDING: AdminKernel comment + docs/admin-guide.md claim admin uploads bypass "
             "DISABLE_UPLOAD; Uploader::saveMarkdown gates them identically (fromClipboard=false)")
    app.set_ini({"DISABLE_UPLOAD": "false"})
    r = act("upload.md", {"dir": ""}, method="multipart",
            jbody={"file": ("admin upload.md", b"# Admin upload\n", "text/markdown")})
    j = r.json() or {}
    rec("admin-actions", "admin upload.md with DISABLE_UPLOAD=false", status=r.status,
        markers={"ok": j.get("ok") is True}, passed=j.get("ok") is True, excerpt=r.text[:140])
    app.set_ini({"DISABLE_UPLOAD": "true"})

    r = act("upload.image", {"dir": "img"}, method="multipart",
            jbody={"file": ("probe.png", PNG_1PX, "image/png")})
    j = r.json() or {}
    rec("admin-actions", "upload.image valid png", status=r.status,
        markers={"ok": j.get("ok") is True, "url_path": bool(j.get("url_path"))},
        passed=j.get("ok") is True, excerpt=r.text[:140])

    svg = b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"
    r = act("upload.image", {"dir": "img"}, method="multipart",
            jbody={"file": ("x.svg", svg, "image/svg+xml")})
    rec("admin-actions", "upload.image svg refused → 415", status=r.status, expect="415",
        excerpt=r.text[:120], passed=r.status == 415)

    r = act("upload.image", {"dir": "img"}, method="multipart",
            jbody={"file": ("fake.png", b"not an image at all", "image/png")})
    rec("admin-actions", "upload.image content-sniff refuses fake → 415", status=r.status, expect="415",
        excerpt=r.text[:120], passed=r.status == 415)

    r = act("preview", {"content": "# Prev\n\n**x**"})
    j = r.json() or {}
    rec("admin-actions", "preview uses real engine", markers={"ok": j.get("ok") is True,
        "strong": "<strong>" in (j.get("html") or "")}, passed=j.get("ok") is True)

    # backups
    r = act("backup.create", {"note": "probe backup"})
    j = r.json() or {}
    bid = j.get("id") or ""
    rec("admin-actions", "backup.create", markers={"ok": j.get("ok") is True, "id format": bool(re.fullmatch(r"content-\d{8}-\d{6}", bid))},
        passed=j.get("ok") is True, excerpt=json.dumps(j)[:180])

    r = act("backup.list", method="get")
    items = (r.json() or {}).get("items", [])
    rec("admin-actions", "backup.list", markers={"contains id": any(i.get("id") == bid for i in items)},
        passed=any(i.get("id") == bid for i in items), excerpt=json.dumps(items)[:180])

    r = c.get(f"/admin.php?action=backup.download&id={bid}", headers=H)
    ct = r.header("Content-Type") or ""
    rec("admin-actions", "backup.download zip", status=r.status,
        markers={"zip ct": "zip" in ct, "PK magic": r.body[:2] == b"PK"},
        passed=r.status == 200 and r.body[:2] == b"PK", headers={"Content-Type": ct})

    # ALLOW_RESTORE=false: does backup.restore still execute? (code-reading says YES, then 403)
    marker_before = (Path(app.root) / "content" / "restore-marker.md").exists()
    (Path(app.root) / "content" / "restore-marker.md").write_text("# marker\n")
    act("index.rebuild")  # fingerprint changes
    r = act("backup.create", {"note": "with marker"})
    bid2 = (r.json() or {}).get("id")
    (Path(app.root) / "content" / "restore-marker.md").unlink()
    r = act("backup.restore", {"id": bid2})
    marker_after = (Path(app.root) / "content" / "restore-marker.md").exists()
    rec("admin-actions", "backup.restore with ALLOW_RESTORE=false", status=r.status,
        markers={"http 403": r.status == 403,
                 "SIDE EFFECT: marker restored anyway": marker_after},
        passed=None, excerpt=r.text[:160],
        note="FINDING CANDIDATE: guard runs after service call; restore executes then answers 403"
             if marker_after and r.status == 403 else "behaviour matches docs")
    # pre-restore snapshot created?
    pre = list((Path(app.root) / "storage" / "backups" / "content").glob("*pre-restore*"))
    rec("admin-actions", "pre-restore snapshot exists", markers={"snapshot": len(pre) >= 1},
        passed=len(pre) >= 1, note=str([p.name for p in pre]))

    # updater actions
    r = act("update.check", qs="&force=1", method="get")
    j = r.json() or {}
    rec("admin-actions", "update.check (network-dependent)", status=r.status,
        markers={"current": j.get("current") == "3.1.0"},
        passed=None, excerpt=json.dumps(j)[:220],
        note="hits api.github.com; ok=false is valid evidence when no GitHub release exists")

    r = act("update.status", method="get")
    j = r.json() or {}
    files = j.get("files", [])
    states = {}
    for f in files:
        states[f.get("status")] = states.get(f.get("status"), 0) + 1
    rec("admin-actions", "update.status (manifest vs disk)", status=r.status,
        markers={"921 tracked": len(files) == 921}, passed=len(files) == 921,
        excerpt=json.dumps(states))

    r = act("update.apply")
    j = r.json() or {}
    rec("admin-actions", "update.apply with ALLOW_UPDATE=false → 403", status=r.status, expect="403",
        markers={"error": "ALLOW_UPDATE is false" in (j.get("error") or "")},
        passed=r.status == 403)

    # settings
    r = act("settings.set", method="post_json", jbody={"SITE_NAME": "Probe Site", "ADMIN_PASSWORD_HASH": "x"})
    j = r.json() or {}
    applied = j.get("applied", [])
    errors = " ".join(j.get("errors", []))
    checks = {"SITE_NAME applied": "SITE_NAME" in applied,
              "HASH refused": "ADMIN_PASSWORD_HASH" in errors and "managed automatically" in errors,
              "ok false due to error": j.get("ok") is False}
    rec("admin-actions", "settings.set applies + refuses HASH", status=r.status, markers=checks,
        passed=all(checks.values()), excerpt=json.dumps(j)[:200])
    r = c.get("/")
    rec("admin-actions", "SITE_NAME change visible on site", markers={"Probe Site": "Probe Site" in r.text},
        passed="Probe Site" in r.text)
    act("settings.set", method="post_json", jbody={"SITE_NAME": "MD.Scribe"})

    r = act("settings.set", method="post_json", jbody={"ADMIN_PASSWORD": "short"})
    rec("admin-actions", "settings.set short password refused", markers={"min 10": "minimum 10" in r.text},
        passed="minimum 10" in r.text, excerpt=r.text[:160])

    r = act("settings.set", method="post_json", jbody={"BOGUS_KEY": "1"})
    rec("admin-actions", "settings.set unknown key refused", markers={"unknown key": "unknown key" in r.text},
        passed="unknown key" in r.text)

    r = act("settings.regenerate-key")
    j = r.json() or {}
    newkey = j.get("api_key") or ""
    rec("admin-actions", "settings.regenerate-key", markers={"mdv_ 44 chars": bool(re.fullmatch(r"mdv_[a-f0-9]{40}", newkey))},
        passed=bool(re.fullmatch(r"mdv_[a-f0-9]{40}", newkey)))

    # themes
    r = act("theme.save", method="post_json",
            jbody={"name": "Probe Accent", "light": {"primary": "#123456"}, "dark": {"primary": "#654321"}})
    j = r.json() or {}
    tid = (j.get("theme") or {}).get("id") or ""
    rec("admin-actions", "theme.save custom", markers={"ok": j.get("ok") is True, "id": bool(tid)},
        passed=j.get("ok") is True, excerpt=json.dumps(j)[:180])
    r = c.get("/index.php?page=themes")
    rec("admin-actions", "custom theme in public catalog", markers={"name shown": "Probe Accent" in r.text},
        passed="Probe Accent" in r.text)
    r = act("theme.delete", {"id": tid})
    rec("admin-actions", "theme.delete", markers={"ok": (r.json() or {}).get("ok") is True},
        passed=(r.json() or {}).get("ok") is True)

    r = act("cache.clear")
    j = r.json() or {}
    rec("admin-actions", "cache.clear", markers={"ok": j.get("ok") is True, "removed field": "removed" in j},
        passed=j.get("ok") is True, excerpt=json.dumps(j)[:120])

    r = act("logs.tail", method="get")
    j = r.json() or {}
    audit = j.get("audit", [])
    actions_seen = {a.get("action") for a in audit}
    want = {"admin.login", "backup.create", "settings.save", "cache.clear", "content.create"}
    rec("admin-actions", "logs.tail + audit trail", markers={"audit entries": len(audit) > 0,
        "actions recorded": str(sorted(actions_seen & want))},
        passed=len(audit) > 0 and len(actions_seen & want) >= 3,
        excerpt=json.dumps(sorted(actions_seen))[:220])
    return newkey


def g_admin_xff_audit(c: Client, token: str, app: ServedApp):
    # spoofed XFF must not be trusted (TRUSTED_PROXIES empty)
    c.post_form("/admin.php?action=logout", {"_token": token}, headers={"X-CSRF-Token": token})
    c.post_form("/admin.php?action=login",
                {"username": "admin", "password": "wrong", "_token": token},
                headers={"X-CSRF-Token": token, "X-Forwarded-For": "9.9.9.9"})
    audit_p = Path(app.root) / "storage" / "logs" / "audit.log"
    audit_lines = audit_p.read_text().splitlines() if audit_p.is_file() else []
    last = json.loads(audit_lines[-1]) if audit_lines else {}
    rec("admin", "spoofed X-Forwarded-For ignored in audit ip",
        markers={"ip is 127.0.0.1": last.get("ip") == "127.0.0.1",
                 "action login_failed": last.get("action") == "admin.login_failed"},
        passed=last.get("ip") == "127.0.0.1", excerpt=json.dumps(last)[:180])


def g_disk(app: ServedApp, tag: str):
    root = Path(app.root)
    files = []
    for dirpath, _dirnames, filenames in os.walk(root / "storage"):
        for fn in filenames:
            files.append(str(Path(dirpath, fn).relative_to(root)))
    files.sort()
    ini = (root / ".md.ini").read_text() if (root / ".md.ini").is_file() else ""
    keys = re.findall(r"(?m)^([A-Z_]+) =", ini)
    rec("disk", f"{tag}: storage side-effects", markers={"files": json.dumps(files[:40])[:400]},
        passed=None, note=f"{len(files)} files under storage/")
    rec("disk", f"{tag}: .md.ini autogenerated keys", markers={"count": len(keys), "keys": ",".join(keys)},
        passed=None)
    cache = list((root / "storage" / "cache").glob("*.json"))
    rec("disk", f"{tag}: render cache populated", markers={"entries": len(cache)},
        passed=None, note="sha256-named JSON entries")


# ─────────────────────────────────────────────────────────────────────────────
# Instance B — root docroot (v2 shim contract)
# ─────────────────────────────────────────────────────────────────────────────
def g_shims(c: Client, app: ServedApp):
    r = c.get("/md.php")
    rec("shims", "/md.php home (no md.md)", status=r.status, expect="200",
        markers={"home doc": "Self-hosted docs" in r.text}, passed=r.status == 200 and "Self-hosted docs" in r.text)

    app.write("content/md.md", "# Shim Home XYZZY\n\nmd.md preferred by the v2 rule.\n")
    r = c.get("/md.php")
    rec("shims", "/md.php prefers md.md when present", status=r.status,
        markers={"md.md rendered": "Shim Home XYZZY" in r.text}, passed="Shim Home XYZZY" in r.text)

    r = c.get("/md.php?file=getting-started.md")
    rec("shims", "/md.php?file= override", status=r.status, expect="200",
        markers={"doc": "md-h1" in r.text or "Getting" in r.text}, passed=r.status == 200)

    r = c.get("/md.php?file=getting-started.md&download=1")
    cd = r.header("Content-Disposition") or ""
    rec("shims", "/md.php?file=&download=1", status=r.status, expect="200",
        markers={"octet-stream": (r.header("Content-Type") or "") == "application/octet-stream",
                 "attachment": "attachment" in cd}, passed=r.status == 200 and "attachment" in cd)

    r = c.get("/md.php?file=../README.md")
    rec("shims", "/md.php traversal refused", status=r.status, expect="404", passed=r.status == 404)

    r = c.get("/updater.php")
    checks = {"landing 200": r.status == 200, "title": "MD.Scribe updater" in r.text,
              "tracked table": "Tracked file" in r.text, "noindex": "noindex,nofollow" in r.text,
              "admin link": "public/admin.php?page=updates" in r.text}
    rec("shims", "/updater.php landing", status=r.status, markers=checks, passed=all(checks.values()))

    r = c.get("/updater.php?update=true")
    rec("shims", "?update=true with ALLOW_UPDATE=false → 403", status=r.status, expect="403",
        markers={"Update disabled": "Update disabled" in r.text}, passed=r.status == 403)

    r = c.get("/updater.php?restore=latest")
    rec("shims", "?restore=latest with ALLOW_RESTORE=false → 403", status=r.status, expect="403",
        markers={"Restore disabled": "Restore disabled" in r.text}, passed=r.status == 403)

    key = ini_get(Path(app.root) / ".md.ini", "API_KEY")
    r = c.get(f"/updater.php?api_key={key}&action=status&format=json")
    j = r.json() or {}
    checks = {"ok": j.get("ok") is True, "action": j.get("action") == "status",
              "version": j.get("version") == "3.1.0", "files": isinstance(j.get("files"), list),
              "envelope keys": all(k in j for k in ("steps", "conflicts", "errors")),
              "no-store": (r.header("Cache-Control") or "") == "no-store",
              "nosniff": (r.header("X-Content-Type-Options") or "") == "nosniff"}
    rec("machine-api", "action=status with key", status=r.status, markers=checks,
        passed=all(checks.values()), excerpt=json.dumps(j)[:200])

    r = c.get("/updater.php?api_key=mdv_wrong&action=status&format=json")
    j = r.json() or {}
    rec("machine-api", "wrong key → 403 unauthorized", status=r.status, expect="403",
        markers={"error": j.get("error") == "unauthorized", "ok false": j.get("ok") is False},
        passed=r.status == 403)

    r = c.get(f"/updater.php?api_key={key}&action=bogus&format=json")
    rec("machine-api", "unknown action → 400", status=r.status, expect="400",
        excerpt=r.text[:100], passed=r.status == 400 and "unknown action" in r.text)

    r = c.get(f"/updater.php?api_key={key}&action=install&format=json")
    rec("machine-api", "install via GET → 405", status=r.status, expect="405",
        excerpt=r.text[:100], passed=r.status == 405 and "POST required" in r.text)

    r = c.post_form(f"/updater.php?api_key={key}&action=install&format=json&dry_run=1", {})
    j = r.json() or {}
    steps = j.get("steps", [])
    rec("machine-api", "install dry_run=1", status=r.status, expect="200",
        markers={"ok": j.get("ok") is True, "dry-run steps": all(s.get("status") == "dry-run" for s in steps)},
        passed=j.get("ok") is True, excerpt=json.dumps(steps[:2])[:200])

    r = c.post_form(f"/updater.php?api_key={key}&action=install&format=json", {})
    j = r.json() or {}
    rec("machine-api", "install (real) with ALLOW_UPDATE=false → HTTP 200, ok=false",
        status=r.status, markers={"ok false": j.get("ok") is False,
                                  "error mentions ALLOW_UPDATE": any("ALLOW_UPDATE" in e for e in j.get("errors", []))},
        passed=j.get("ok") is False and r.status == 200,
        excerpt=json.dumps(j)[:220], note="v2 envelope keeps HTTP 200; ok=false carries the refusal")

    r = c.get(f"/updater.php?api_key={key}&action=conflicts&format=json")
    j = r.json() or {}
    rec("machine-api", "action=conflicts", status=r.status, markers={"ok": j.get("ok") is True,
        "conflicts list": isinstance(j.get("conflicts"), list)}, passed=j.get("ok") is True,
        excerpt=json.dumps(j.get("conflicts", [])[:2])[:200])

    # root index.php (layout B entry)
    r = c.get("/index.php")
    rec("shims", "root /index.php entry (layout B)", status=r.status, expect="200",
        markers={"home": "Self-hosted docs" in r.text, "asset prefix /public": "/public/assets/" in r.text},
        passed=r.status == 200 and "/public/assets/" in r.text)

    # .md.ini served statically? (php -S serves dotfiles? router blocks in mode A; mode B has no router)
    r = c.get("/.md.ini")
    rec("shims", "GET /.md.ini on bare php -S (no .htaccess!)", status=r.status,
        markers={"NOT served": r.status in (403, 404) or "API_KEY" not in r.text},
        passed=None, excerpt=r.text[:100],
        note="dev server has no .htaccess; documents why Apache rules / layout A matter")


def g_mode_b_misc(c: Client, app: ServedApp):
    # HOME_DOC fallback → library
    app.set_ini({"HOME_DOC": "definitely-missing.md"})
    r = c.get("/index.php")
    rec("misc", "HOME_DOC missing → library page at /", status=r.status, expect="200",
        markers={"library": "Library" in r.text}, passed="Library" in r.text)
    ini_p = Path(app.root) / ".md.ini"
    txt = re.sub(r"(?m)^HOME_DOC = .*$", "HOME_DOC = index.md", ini_p.read_text())
    ini_p.write_text(txt)


# ─────────────────────────────────────────────────────────────────────────────
def main():
    META["php"] = os.popen("php -r 'echo PHP_VERSION;'").read().strip()
    print(f"== probing MD.Scribe with PHP {META['php']} ==")

    print("\n[A] instance A: docroot=public + router.php")
    with ServedApp(REPO, serve_cmd=CMD_A, keep=True) as app:
        stage_fixtures(app)
        c = Client(app.base_url)
        META["instance_a"] = {"root": str(app.root), "base": app.base_url, "cmd": CMD_A}
        g_modes(c)
        g_headers(c)
        g_media_download(c, app)
        g_traversal(c)
        g_api_post_gates(c)
        g_injection(c, app)
        g_raw_html_modes(c, app)
        g_matrix(c, app)
        g_attributes(c, app)
        g_search_api(c)
        g_per_dir_flags(c, app)
        g_flags_hardlock_cookie(c, app)
        g_zerocdn(c)
        try:
            token = g_admin_setup_login(c, app)
            g_admin_unauth(Client(app.base_url))
            newkey = g_admin_actions(c, token, app)
            g_admin_xff_audit(c, token, app)
        except Exception as e:
            import traceback; traceback.print_exc()
            rec("admin", "EXCEPTION in admin flow", markers={"error": str(e)}, passed=False)
            newkey = ""
        g_disk(app, "A")
        META["instance_a"]["api_key_after_regenerate"] = newkey

    print("\n[B] instance B: docroot=project root (shims)")
    with ServedApp(REPO, serve_cmd=CMD_B, keep=True) as app:
        stage_fixtures(app)
        c = Client(app.base_url)
        META["instance_b"] = {"root": str(app.root), "base": app.base_url, "cmd": CMD_B}
        g_shims(c, app)
        g_mode_b_misc(c, app)
        g_disk(app, "B")

    # summary
    total = len(RECORDS)
    passed = sum(1 for r in RECORDS if r["passed"] is True)
    failed = [r for r in RECORDS if r["passed"] is False]
    obs = sum(1 for r in RECORDS if r["passed"] is None)
    META["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    META["summary"] = {"total": total, "pass": passed, "fail": len(failed), "observations": obs}

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({"meta": META, "records": RECORDS}, indent=1, ensure_ascii=False))

    # markdown evidence
    md = ["# Probe evidence — MD.Scribe 3.1.0", "",
          f"PHP {META['php']} · {META['started']} → {META['finished']} · "
          f"{total} checks: {passed} pass, {len(failed)} fail, {obs} observations", ""]
    last_g = None
    for r in RECORDS:
        if r["group"] != last_g:
            md.append(f"\n## {r['group']}\n")
            md.append("| Check | Status | Result | Detail |")
            md.append("|---|---|---|---|")
            last_g = r["group"]
        flag = {True: "PASS", False: "**FAIL**", None: "obs"}[r["passed"]]
        failed_markers = [k for k, v in (r["markers"] or {}).items() if v is False]
        detail = r["note"] or ""
        if failed_markers:
            detail = ("failed markers: " + ", ".join(failed_markers) + ". " + detail).strip()
        md.append(f"| `{r['name'][:70]}` | {r['status']} | {flag} | {detail[:120]} |")
    OUT_MD.write_text("\n".join(md))

    print(f"\n== summary: {passed} pass / {len(failed)} fail / {obs} obs of {total} ==")
    for r in failed:
        fm = [k for k, v in (r["markers"] or {}).items() if v is False]
        print(f"  FAIL {r['group']}: {r['name']} [{r['status']}] failed={fm} note={r['note'][:100]}")
    print(f"evidence: {OUT_JSON}\n          {OUT_MD}")
    print(f"kept staged dirs: A={META['instance_a']['root']} B={META['instance_b']['root']}")


if __name__ == "__main__":
    main()
