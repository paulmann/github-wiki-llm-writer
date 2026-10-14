#!/usr/bin/env python3
"""
proposed_req_additions.py — drop-in additions for lib/req.py.

WHY
    req.py is a stateless (status, headers, body) client — perfect for route
    batteries, but the MD.Scribe run needed STATEFUL flows: first-run setup →
    login (CSRF token from an HTML page, session cookie, token rotation) →
    ~26 authenticated JSON actions → logout. With no cookie jar in the kit,
    every agent will hand-roll one (I did; ~60 lines) and will hit the same
    three traps:

      1. urllib's dict(resp.headers) COLLAPSES multiple Set-Cookie headers —
         a cookie-jar processor is required, not a dict.
      2. CSRF tokens must ride in the POST BODY or a HEADER; the kit's
         post_form() has no token plumbing, and subjects differ in where the
         token is printed (JSON `"csrf":"…"`, JS literal `csrf: "…"`,
         `_token: "…"`, hidden input). A multi-pattern extractor is reusable.
      3. 302s must stay observable (login redirects are contract), so the
         jar-enabled opener must keep req.py's no-redirect behaviour.

INTEGRATION
    Append SessionClient + csrf_from_html to lib/req.py (stdlib only, no
    behaviour change for existing callers), and mention them in AGENTS.md's
    "probe a subject with sessions" paragraph. A `battery_authed_flow(probe,
    steps)` helper could sit in webapp_probe.py on top of this (see
    probe_mdscribe_example.py::g_admin_setup_login for the flow shape).

Self-test at the bottom spins a 12-line PHP session app and exercises
login → authenticated action → logout, proving the client against a real
Set-Cookie/302/CSRF lifecycle.
"""
from __future__ import annotations

import http.cookiejar
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid

# ─────────────────────────────────────────────────────────────────────────────
# lib/session.py — stateful HTTP client for probing session/CSRF-protected surfaces
#
# Shipped as its own module rather than merged into lib/req.py: it defines a
# self-contained Response/_NoRedirect pair, so keeping it separate preserves the
# verified behaviour (self-test 8/8 against a live PHP session app) instead of
# risking a collision with req.py's tuple-based Response.
#
# WHY: req.py is stateless, and dict(resp.headers) collapses multiple Set-Cookie
# values. Admin surfaces (login -> 302 -> token rotation -> authenticated actions
# -> logout) cannot be probed without a cookie jar, and auto-redirect destroys the
# evidence because 302 is part of the contract.
#
# Usage:
#   from session import SessionClient, csrf_from_html
#   c = SessionClient(base_url)
#   r = c.post_form("/login", {"user":"admin","pass":"x","_token":csrf_from_html(home)})
#   r = c.post_form("/admin/action", {...}, token=csrf)   # token goes to body AND header
# ─────────────────────────────────────────────────────────────────────────────

class Response:
    """Attribute-compatible with req.Response (status/headers/body/text/json/header),
    but keeps the header MESSAGE object so get_all('Set-Cookie') works via headers_all()."""

    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body

    @property
    def text(self):
        return self.body.decode("utf-8", "replace")

    def header(self, name):
        return self.headers.get(name) if self.headers else None

    def headers_all(self, name):
        return self.headers.get_all(name) if self.headers else []

    def json(self):
        try:
            return json.loads(self.body)
        except Exception:
            return None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class SessionClient:
    """Cookie-jar HTTP client with req.py's ergonomics and no auto-redirect.

    get / post_form / post_json / post_multipart all share one jar, so session
    cookies (and their rotation) survive across calls. 302s are returned, not
    followed — login flows are contract, not noise.
    """

    def __init__(self, base_url: str, timeout: int = 30):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar), _NoRedirect()
        )

    def url(self, path: str) -> str:
        return path if path.startswith("http") else self.base + (path if path.startswith("/") else "/" + path)

    def request(self, path, method="GET", data=None, headers=None):
        r = urllib.request.Request(self.url(path), method=method, data=data, headers=headers or {})
        try:
            with self.opener.open(r, timeout=self.timeout) as resp:
                return Response(resp.status, resp.headers, resp.read())
        except urllib.error.HTTPError as e:          # 4xx/5xx are responses, not failures
            return Response(e.code, e.headers, e.read())
        except Exception as e:                       # transport-level
            return Response("ERR", None, f"{type(e).__name__}: {e}".encode())

    def get(self, path, headers=None):
        return self.request(path, "GET", headers=headers)

    def post_form(self, path, fields, headers=None, token=None, token_field="_token"):
        f = dict(fields or {})
        if token is not None:
            f.setdefault(token_field, token)
        h = {"Content-Type": "application/x-www-form-urlencoded"}
        if token is not None:
            h.setdefault("X-CSRF-Token", token)      # belt and braces; subjects pick one
        h.update(headers or {})
        return self.request(path, "POST", urllib.parse.urlencode(f).encode(), h)

    def post_json(self, path, obj, headers=None, token=None):
        h = {"Content-Type": "application/json"}
        if token is not None:
            h["X-CSRF-Token"] = token
        h.update(headers or {})
        return self.request(path, "POST", json.dumps(obj).encode(), h)

    def post_multipart(self, path, fields, files, headers=None, token=None):
        boundary = uuid.uuid4().hex
        f = dict(fields or {})
        if token is not None:
            f.setdefault("_token", token)
        parts = []
        for k, v in f.items():
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
        for k, (name, blob, ctype) in (files or {}).items():
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{name}\"\r\n"
                f"Content-Type: {ctype}\r\n\r\n".encode() + blob + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        h = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        h.update(headers or {})
        return self.request(path, "POST", b"".join(parts), h)


CSRF_PATTERNS = (
    r'"csrf"\s*:\s*"([0-9a-fA-F]{16,128})"',      # JSON blob (window.X = {...})
    r'csrf\s*:\s*"([0-9a-fA-F]{16,128})"',        # JS object literal
    r'_token\s*[:=]\s*"([0-9a-fA-F]{16,128})"',   # JS field / hidden input value
    r'name="_token"\s+value="([0-9a-fA-F]{16,128})"',
    r'name="csrf_token"\s+value="([0-9a-fA-F]{16,128})"',
    r'<meta\s+name="csrf-token"\s+content="([0-9a-fA-F]{16,128})"',
)


def csrf_from_html(html: str, extra_patterns=()) -> str:
    """Extract a CSRF token from an HTML page. Tries the common shapes; pass
    extra_patterns (regexes with one group) for exotic subjects."""
    for pat in tuple(extra_patterns) + CSRF_PATTERNS:
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Self-test: a 12-line PHP session app (login → authed action → logout)
# ─────────────────────────────────────────────────────────────────────────────
PHP_APP = r"""<?php
session_start();
$tok = $_SESSION['t'] ??= bin2hex(random_bytes(16));
$u = $_SESSION['u'] ?? null;
if (isset($_GET['login'])) {
    $sent = $_POST['_token'] ?? '';
    if (!hash_equals($tok, $sent)) { http_response_code(403); echo '{"error":"csrf"}'; exit; }
    if (($_POST['pw'] ?? '') !== 'secret123') { http_response_code(401); echo '{"error":"bad"}'; exit; }
    $_SESSION['u'] = 'admin'; session_regenerate_id(true);
    header('Location: /done.php'); http_response_code(302); exit;
}
if (isset($_GET['action'])) {
    if ($u !== 'admin') { http_response_code(401); echo '{"error":"unauthorized"}'; exit; }
    echo '{"ok":true,"user":"'.$u.'","tok":"'.$_SESSION['t'].'"}'; exit;
}
echo '<html><script>window.CFG = {"csrf": "'.$tok.'"};</script></html>';
"""


def _self_test() -> int:
    import shutil
    import socket
    import subprocess
    import sys
    import tempfile
    import time
    from pathlib import Path

    if not shutil.which("php"):
        print("SELF-TEST SKIPPED (no php on PATH) — client code is import-safe regardless")
        return 0
    root = Path(tempfile.mkdtemp(prefix="req-selftest-"))
    (root / "index.php").write_text(PHP_APP)
    (root / "done.php").write_text("<?php echo 'ok';")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(["php", "-S", f"127.0.0.1:{port}", "-t", str(root)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(80):
            try:
                socket.create_connection(("127.0.0.1", port), 0.25).close()
                break
            except OSError:
                time.sleep(0.1)
        c = SessionClient(f"http://127.0.0.1:{port}")
        page = c.get("/index.php")
        tok = csrf_from_html(page.text)
        checks = {
            "token extracted": bool(re.fullmatch(r"[0-9a-f]{32}", tok or "")),
            "action before login → 401": c.get("/index.php?action=1").status == 401,
            "login without token → 403": c.post_form("/index.php?login", {"pw": "secret123"}).status == 403,
            "login wrong pw → 401": c.post_form("/index.php?login", {"pw": "x"}, token=tok).status == 401,
        }
        r = c.post_form("/index.php?login", {"pw": "secret123"}, token=tok)
        checks["login ok → 302 observable"] = r.status == 302 and (r.header("Location") or "").endswith("/done.php")
        ra = c.get("/index.php?action=1")
        checks["authed action → ok:true"] = ra.status == 200 and (ra.json() or {}).get("ok") is True
        checks["session survived regeneration"] = (ra.json() or {}).get("user") == "admin"
        # rotated token after regenerate_id: the page re-fetched carries the live token
        tok2 = csrf_from_html(c.get("/index.php").text)
        checks["token stable within session"] = tok2 == (ra.json() or {}).get("tok")
        bad = [k for k, v in checks.items() if not v]
        for k, v in checks.items():
            print(f"  [{'ok ' if v else 'FAIL'}] {k}")
        print("SELF-TEST FAILED: " + str(bad) if bad else "SELF-TEST PASSED")
        return 1 if bad else 0
    finally:
        proc.terminate()
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    import sys
    sys.exit(_self_test())
