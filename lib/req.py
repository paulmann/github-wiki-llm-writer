#!/usr/bin/env python3
"""
req.py — dependency-free HTTP client for probing a local (or remote) app.

WHY THIS EXISTS
    The sandbox often has no `curl` at the start of a session, and installing it
    costs a minute. This module uses only the Python standard library, so it
    works from second zero. It is also the *correct* tool for capturing exact
    response headers and bodies, which is what a wiki needs when it documents
    HTTP status codes verbatim.

USAGE AS A MODULE
    import sys; sys.path.insert(0, '/path/to/github-wiki-llm-writer/lib')
    from req import req, post_form, post_multipart

    status, headers, body = req('http://127.0.0.1:8080/md.php')
    status, headers, body = post_form(url, {'md_preview': '1', 'content': '# Hi'})
    status, headers, body = post_multipart(url, fields={'dir': 'docs'},
                                          files={'md_file': ('a.md', b'# a')})

USAGE AS A CLI
    python3 req.py GET  http://127.0.0.1:8080/md.php
    python3 req.py GET  http://127.0.0.1:8080/md.php -o page.html
    python3 req.py POST http://127.0.0.1:8080/md.php -d md_preview=1 -d 'content=# Hi'
    python3 req.py HEAD http://127.0.0.1:8080/md.php --headers-only
    python3 req.py GET  http://127.0.0.1:8080/x.php -H 'X-API-Key: mdv_abc'

GOTCHAS LEARNED THE HARD WAY
  * Do NOT save a file called `http.py` anywhere on sys.path. Python's stdlib
    `http.client` will fail to import with "No module named 'http.client';
    'http' is not a package" and every urllib call dies. This cost a full
    debug cycle once.
  * HTTPError is a *response*, not a failure: 4xx/5xx must be caught and
    returned, or a probe suite silently loses exactly the cases it exists to
    document.
  * `body` is bytes. Decode with errors='replace' — the app under test may emit
    invalid UTF-8 while you are feeding it hostile payloads.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Iterable

DEFAULT_TIMEOUT = 30


class Response(tuple):
    """(status, headers, body) tuple with named access, so old code keeps working."""

    def __new__(cls, status: Any, headers: dict, body: bytes):
        return super().__new__(cls, (status, headers, body))

    @property
    def status(self) -> Any:
        return self[0]

    @property
    def headers(self) -> dict:
        return self[1]

    @property
    def body(self) -> bytes:
        return self[2]

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "replace")

    def json(self) -> Any:
        return json.loads(self.body)

    def header(self, name: str) -> str | None:
        """Case-insensitive header lookup."""
        low = name.lower()
        for k, v in self.headers.items():
            if k.lower() == low:
                return v
        return None

    def ok(self) -> bool:
        return isinstance(self.status, int) and 200 <= self.status < 300


def req(
    url: str,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    allow_redirects: bool = False,
) -> Response:
    """Perform one request. Never raises on HTTP status; returns ('ERR', {}, msg) on transport failure."""

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener_args: list[Any] = []
    if not allow_redirects:
        opener_args.append(_NoRedirect())
    opener = urllib.request.build_opener(*opener_args)

    r = urllib.request.Request(url, method=method.upper(), data=data, headers=headers or {})
    try:
        with opener.open(r, timeout=timeout) as resp:
            return Response(resp.status, dict(resp.headers), resp.read())
    except urllib.error.HTTPError as e:
        # A 4xx/5xx is a legitimate, documentable response — return it.
        return Response(e.code, dict(e.headers or {}), e.read())
    except Exception as e:  # connection refused, DNS, timeout, TLS
        return Response("ERR", {}, f"{type(e).__name__}: {e}".encode())


def get(url: str, **kw) -> Response:
    return req(url, "GET", **kw)


def post_form(url: str, fields: dict, headers: dict | None = None, **kw) -> Response:
    """POST application/x-www-form-urlencoded."""
    h = {"Content-Type": "application/x-www-form-urlencoded"}
    h.update(headers or {})
    return req(url, "POST", urllib.parse.urlencode(fields).encode(), h, **kw)


def post_multipart(
    url: str,
    fields: dict | None = None,
    files: dict | None = None,
    headers: dict | None = None,
    **kw,
) -> Response:
    """POST multipart/form-data.

    files: {field_name: (filename, bytes_or_str, content_type?)}
    NOTE: the field name matters. Getting it wrong usually yields a 400 whose
    message says "no file received", which looks like a server bug and is not.
    """
    boundary = "----probe" + uuid.uuid4().hex
    parts: list[bytes] = []
    for k, v in (fields or {}).items():
        parts += [
            f"--{boundary}".encode(),
            f'Content-Disposition: form-data; name="{k}"'.encode(),
            b"",
            str(v).encode(),
        ]
    for k, spec in (files or {}).items():
        fname, content = spec[0], spec[1]
        ctype = spec[2] if len(spec) > 2 else "application/octet-stream"
        if isinstance(content, str):
            content = content.encode()
        parts += [
            f"--{boundary}".encode(),
            f'Content-Disposition: form-data; name="{k}"; filename="{fname}"'.encode(),
            f"Content-Type: {ctype}".encode(),
            b"",
            content,
        ]
    parts += [f"--{boundary}--".encode(), b""]
    h = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    h.update(headers or {})
    return req(url, "POST", b"\r\n".join(parts), h, **kw)


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────
def _main(argv: Iterable[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Minimal stdlib HTTP client for probing an app.")
    p.add_argument("method", nargs="?", default="GET")
    p.add_argument("url")
    p.add_argument("-d", "--data", action="append", default=[],
                   help="form field key=value (repeatable); switches to POST form")
    p.add_argument("--raw", help="send this string as the raw body")
    p.add_argument("-H", "--header", action="append", default=[], help="Name: value (repeatable)")
    p.add_argument("-F", "--file", action="append", default=[],
                   help="field=@path[:content-type] — multipart upload")
    p.add_argument("-o", "--out", help="write body to this file")
    p.add_argument("--headers-only", action="store_true")
    p.add_argument("--grep", help="print only body lines matching this substring")
    p.add_argument("--follow", action="store_true", help="follow redirects")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    a = p.parse_args(list(argv) if argv is not None else None)

    headers = {}
    for h in a.header:
        k, _, v = h.partition(":")
        headers[k.strip()] = v.strip()

    method = a.method.upper()
    files = {}
    for spec in a.file:
        field, _, rest = spec.partition("=@")
        path, _, ctype = rest.partition(":")
        with open(path, "rb") as fh:
            files[field] = (path.rsplit("/", 1)[-1], fh.read(), ctype or "application/octet-stream")

    if files:
        r = post_multipart(a.url, fields=dict(x.split("=", 1) for x in a.data),
                           files=files, headers=headers, timeout=a.timeout,
                           allow_redirects=a.follow)
    elif a.data:
        r = post_form(a.url, dict(x.split("=", 1) for x in a.data),
                      headers=headers, timeout=a.timeout, allow_redirects=a.follow)
    elif a.raw is not None:
        r = req(a.url, method, a.raw.encode(), headers, a.timeout, a.follow)
    else:
        r = req(a.url, method, headers=headers, timeout=a.timeout, allow_redirects=a.follow)

    print(f"HTTP {r.status}  ({len(r.body)} bytes)")
    for k, v in r.headers.items():
        print(f"  {k}: {v}")
    if a.headers_only:
        return 0
    if a.out:
        with open(a.out, "wb") as fh:
            fh.write(r.body)
        print(f"  → wrote {a.out}")
    elif a.grep:
        for line in r.text.splitlines():
            if a.grep in line:
                print("  " + line.strip()[:300])
    else:
        print(r.text[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
