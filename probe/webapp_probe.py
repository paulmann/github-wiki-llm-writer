#!/usr/bin/env python3
"""
webapp_probe.py — run a declarative battery of requests against a running app
and emit evidence you can paste straight into research notes.

This is the "verify, don't transcribe" tool. Point it at an entry point and it
answers the questions a wiki has to get right:

  * which request shapes does the app accept, and what does each return?
  * which status codes exist, and for what?
  * what response headers are sent (and which security headers are MISSING)?
  * does the path/file validator actually hold? (traversal battery)
  * does output escaping actually hold? (injection battery)
  * which config flags gate which endpoints? (flag battery)
  * what does the app write to disk as a side effect?

Every result records the request, the status, selected headers and an excerpt —
so a claim in the wiki can be traced to a reproduced observation instead of to
the project's own README.

    # against a staged throwaway instance (recommended)
    python3 probe/webapp_probe.py --repo workspace/repo/SUBJECT \
            --copy 'md.php,updater.php,css,js' --entry /md.php \
            --suite php-mdviewer -o workspace/research/probe.json

    # against something already running
    python3 probe/webapp_probe.py --base-url http://127.0.0.1:8080 \
            --entry /md.php --suite generic -o workspace/research/probe.json

Suites
  generic        headers, status codes, 404/405 behaviour, robots, common paths
  injection      XSS/SSTI/header-injection payloads through any POST body or GET param
  traversal      path-traversal battery through a file-ish parameter
  php-mdviewer   the full MD.Viewer battery (modes, flags, machine API, upload)

Write your own: a suite is just a list of Probe dicts. See SUITES at the bottom.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from req import Response, get, post_form, post_multipart, req  # noqa: E402
from serve import ServedApp  # noqa: E402

SECURITY_HEADERS = [
    "Content-Security-Policy", "X-Content-Type-Options", "X-Frame-Options",
    "Strict-Transport-Security", "Referrer-Policy", "Permissions-Policy",
    "Cross-Origin-Opener-Policy", "Cross-Origin-Resource-Policy",
    "Cross-Origin-Embedder-Policy", "Cache-Control",
]
LEAK_HEADERS = ["X-Powered-By", "Server", "X-AspNet-Version", "X-Generator"]

TRAVERSAL_PAYLOADS = [
    "../../../etc/passwd", "..\\..\\..\\windows\\win.ini", "/etc/passwd",
    "C:\\windows\\win.ini", "//etc/passwd",
    "..%2f..%2f..%2fetc%2fpasswd", "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "....//....//....//etc/passwd", "..%252f..%252fetc%252fpasswd",
    "%c0%ae%c0%ae/etc/passwd", "..%c0%af..%c0%afetc/passwd",
    "valid/../../../etc/passwd", "./../../etc/passwd",
    "/proc/self/environ", "..%00/..%00/etc/passwd", "etc/passwd%00.png",
    ".." * 40, "a/" * 60 + "b", "\x00", "../../" + "x" * 300,
]

INJECTION_PAYLOADS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "<svg onload=alert(1)>",
    "<iframe src=\"javascript:alert(1)\"></iframe>",
    "<details open ontoggle=alert(1)>x</details>",
    "<a href=\"x\" onclick=\"alert(1)\">y</a>",
    "<body onload=alert(1)>",
    "<input onfocus=alert(1) autofocus>",
    "<form id=x><input name=y>",                       # DOM clobbering probe
    "\"'><script>alert(1)</script>",                   # attribute breakout
    "javascript:alert(1)",
    "{{7*7}}", "${7*7}", "<%= 7*7 %>", "#{7*7}",        # SSTI probes
    "$(id)", "`id`", ";id;", "|id",                    # command injection probes
    "' OR '1'='1", "1; DROP TABLE users--",            # SQLi probes
    "%0d%0aX-Injected: yes", "a\r\nb",                 # header/CRLF injection
    "<!-- comment -->", "<plaintext>", "<noscript>x",
]


def excerpt(body: bytes, n: int = 180) -> str:
    t = body.decode("utf-8", "replace")
    t = re.sub(r"\s+", " ", t).strip()
    return t[:n]


def classify_injection(payload: str, body: bytes) -> str:
    """Did the payload survive into the response unescaped?"""
    t = body.decode("utf-8", "replace")
    p = payload.strip()
    if p and p in t:
        return "REFLECTED-VERBATIM"          # ← the finding that matters
    esc = p.replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    if esc and esc in t:
        return "escaped"
    if p and p.lower() in t.lower():
        return "reflected-case-changed"
    # partial: the tag name survived even if the whole payload did not
    m = re.match(r"<(\w+)", p)
    if m and re.search(rf"<{m.group(1)}[\s>]", t, re.I):
        return "TAG-SURVIVED"
    if "{{7*7}}" in p and "49" in t:
        return "SSTI-49"
    if not t:
        return "empty-body"
    return "not-reflected"


class Probe:
    def __init__(self, base_url: str, app: ServedApp | None = None):
        self.base_url = base_url.rstrip("/")
        self.app = app
        self.results: list[dict] = []

    def url(self, path: str) -> str:
        return path if path.startswith("http") else self.base_url + (path if path.startswith("/") else "/" + path)

    def run(self, name: str, path: str, *, method: str = "GET", fields: dict | None = None,
            files: dict | None = None, headers: dict | None = None, raw: bytes | None = None,
            expect: Any = None, note: str = "", group: str = "general") -> dict:
        t0 = time.time()
        if files:
            r = post_multipart(self.url(path), fields=fields or {}, files=files, headers=headers)
        elif fields is not None:
            r = post_form(self.url(path), fields, headers=headers)
        elif raw is not None:
            r = req(self.url(path), method, raw, headers)
        else:
            r = req(self.url(path), method, headers=headers)
        rec = {
            "group": group, "name": name, "method": method if not fields and not files else "POST",
            "path": path, "status": r.status, "ms": round((time.time() - t0) * 1000),
            "bytes": len(r.body),
            "headers": {k: v for k, v in r.headers.items()},
            "excerpt": excerpt(r.body),
            "note": note,
        }
        if expect is not None:
            exp = expect if isinstance(expect, (list, tuple, set)) else {expect}
            rec["expected"] = sorted(str(e) for e in exp)
            rec["matches_expectation"] = str(r.status) in {str(e) for e in exp}
        self.results.append(rec)
        return rec

    # ── batteries ────────────────────────────────────────────────────────────
    def battery_headers(self, paths: list[str]) -> dict:
        """Which security headers are sent, and which leak stack info."""
        out = {}
        for p in paths:
            r = get(self.url(p))
            hl = {k.lower(): v for k, v in r.headers.items()}
            out[p] = {
                "status": r.status,
                "present": {h: hl[h.lower()] for h in SECURITY_HEADERS if h.lower() in hl},
                "MISSING": [h for h in SECURITY_HEADERS if h.lower() not in hl],
                "leaks": {h: hl[h.lower()] for h in LEAK_HEADERS if h.lower() in hl},
                "cookies": r.header("Set-Cookie"),
            }
        return out

    def battery_traversal(self, param_paths: list[str], ok_marker: str | None = None,
                          deny_markers: list[str] | None = None) -> list[dict]:
        """Send every traversal payload through each parameterised path.

        deny_markers: substrings that indicate a refusal. IMPORTANT: a refusal
        may well be HTTP 200 (deliberate non-disclosure), so classify on the
        BODY, not the status.
        """
        deny_markers = deny_markers or ["access denied", "not found", "denied", "invalid", "forbidden"]
        rows = []
        for tmpl in param_paths:
            for payload in TRAVERSAL_PAYLOADS:
                path = tmpl.replace("{PAYLOAD}", payload)
                r = get(self.url(path))
                t = r.body.decode("utf-8", "replace").lower()
                denied = any(m in t for m in deny_markers)
                leaked = any(s in r.body.decode("utf-8", "replace") for s in
                             ("root:x:0:0", "[boot loader]", "DB_PASSWORD", "BEGIN RSA PRIVATE KEY"))
                rows.append({
                    "template": tmpl, "payload": payload, "status": r.status, "bytes": len(r.body),
                    "denied": denied, "LEAKED-SENSITIVE-CONTENT": leaked,
                    "marker": next((m for m in deny_markers if m in t), None),
                })
        return rows

    def battery_injection(self, sinks: list[dict]) -> list[dict]:
        """sinks: [{'name':…, 'path':…, 'field':…, 'via': 'post'|'get'|'raw'}]"""
        rows = []
        for sink in sinks:
            for payload in INJECTION_PAYLOADS:
                if sink.get("via") == "post":
                    r = post_form(self.url(sink["path"]), {sink["field"]: payload, **sink.get("extra", {})})
                elif sink.get("via") == "get":
                    r = get(self.url(sink["path"].replace("{PAYLOAD}", payload)))
                else:
                    r = req(self.url(sink["path"]), sink.get("method", "POST"), payload.encode(),
                            sink.get("headers", {"Content-Type": "text/plain"}))
                rows.append({
                    "sink": sink["name"], "payload": payload, "status": r.status,
                    "verdict": classify_injection(payload, r.body),
                    "excerpt": excerpt(r.body, 140),
                })
        return rows

    def battery_flags(self, cases: list[dict]) -> list[dict]:
        """cases: [{'name','path','ini':{…},'expect':status}] — flip config, re-request."""
        rows = []
        if not self.app:
            return [{"error": "battery_flags needs --repo (a staged instance) to mutate config"}]
        for c in cases:
            if c.get("ini"):
                self.app.set_ini(c["ini"])
            r = req(self.url(c["path"]), c.get("method", "GET"))
            rows.append({
                "name": c["name"], "ini": c.get("ini"), "path": c["path"],
                "status": r.status, "expected": c.get("expect"),
                "matches": (str(r.status) == str(c["expect"]) if c.get("expect") is not None else None),
                "excerpt": excerpt(r.body, 140),
            })
        return rows

    def battery_disk(self) -> list[str]:
        return self.app.ls() if self.app else []

    def report_md(self, title: str = "Probe report") -> str:
        """Markdown summary, ready to paste into research/summary.md."""
        L = [f"# {title}", ""]
        by_group: dict[str, list] = {}
        for r in self.results:
            by_group.setdefault(r["group"], []).append(r)
        for g, rows in by_group.items():
            L += [f"## {g}", "", "| request | status | bytes | ms | expected | ok |",
                  "|---|---|---|---|---|---|"]
            for r in rows:
                exp = ",".join(r.get("expected", [])) or "—"
                ok = {True: "✅", False: "❌"}.get(r.get("matches_expectation"), "—")
                L.append(f"| `{r['method']} {r['path'][:64]}` | **{r['status']}** | {r['bytes']} | {r['ms']} | {exp} | {ok} |")
            L.append("")
        return "\n".join(L)


# ──────────────────────────────────────────────────────────────────────────────
# Suites
# ──────────────────────────────────────────────────────────────────────────────
def suite_generic(probe: Probe, entry: str) -> dict:
    out: dict[str, Any] = {}
    for p in [entry, "/", "/index.html", "/nonexistent-xyz", "/robots.txt", "/favicon.ico",
              "/.git/config", "/.env", "/.htaccess", "/wp-login.php", "/admin"]:
        probe.run(f"GET {p}", p, expect=None, group="reachability")
    for m in ("POST", "PUT", "DELETE", "PATCH", "OPTIONS"):
        probe.run(f"{m} {entry}", entry, method=m, group="methods")
    out["headers"] = probe.battery_headers([entry, "/"])
    return out


def suite_php_mdviewer(probe: Probe, entry: str) -> dict:
    """Full battery for MD.Viewer-shaped apps: naming-routed PHP viewer + updater."""
    out: dict[str, Any] = {}
    app = probe.app
    assert app is not None, "php-mdviewer suite requires --repo (staged instance)"

    # ── modes ────────────────────────────────────────────────────────────────
    app.write("md.md", "# Title: Sub\n\nIntro paragraph.\n\n## One\n\nx\n\n## Two\n\ny\n")
    probe.run("viewer mode (md.md exists)", entry, expect=200, group="modes")
    r = probe.results[-1]
    out["title_tag"] = (re.search(r"<title>(.*?)</title>", r["excerpt"]) or [None, None])[1]
    out["ini_created_by_viewer"] = ".md.ini" in app.ls()
    out["ini_keys_after_viewer"] = sorted(re.findall(r"(?m)^([A-Z_]+)\s*=", app.read(".md.ini"))) \
        if out["ini_created_by_viewer"] else []
    out["api_key_after_viewer_only"] = "API_KEY" in (app.read(".md.ini") if out["ini_created_by_viewer"] else "")

    app.write("docs/sub/deep.md", "# Deep\n\nbody\n")
    probe.run("viewer ?file= (nested)", entry + "?file=docs/sub/deep.md", expect=200, group="modes")
    probe.run("raw download", entry + "?file=md.md&download=1", expect=200, group="modes")
    out["download_headers"] = {k: v for k, v in probe.results[-1]["headers"].items()
                               if k.lower() in ("content-type", "x-content-type-options",
                                                "content-disposition", "cache-control")}
    probe.run("raw download, bad path", entry + "?file=../nope.md&download=1", expect=404, group="modes")
    probe.run("browser mode (no md.md)", entry, expect=200, group="modes",
              note="after removing md.md")
    (app.root / "md.md").rename(app.root / "md.md.off")
    probe.run("browser mode", entry, expect=200, group="modes")
    out["browser_markers"] = [m for m in ("files-table", "files-search", "btn-upload-md",
                                         "btn-clipboard-preview", "data-sort-default")
                              if m in probe.results[-1]["excerpt"]]
    (app.root / "md.md.off").rename(app.root / "md.md")

    probe.run("clipboard preview", entry, method="POST",
              fields={"md_preview": "1", "content": "# Clip\n\nbody"}, expect=200, group="modes")
    probe.run("clipboard preview, empty", entry, method="POST",
              fields={"md_preview": "1", "content": "   "}, expect=400, group="modes")
    probe.run("double slash 301", "//docs/x", expect=301, group="modes")

    # ── traversal ────────────────────────────────────────────────────────────
    out["traversal"] = probe.battery_traversal(
        [entry + "?file={PAYLOAD}"],
        deny_markers=["access denied or file not found", "path validation failed", "not found"])
    bad = [t for t in out["traversal"] if not t["denied"] or t["LEAKED-SENSITIVE-CONTENT"]]
    out["traversal_failures"] = bad

    # ── injection ────────────────────────────────────────────────────────────
    out["injection"] = probe.battery_injection([
        {"name": "clipboard-preview", "path": entry, "field": "content", "via": "post",
         "extra": {"md_preview": "1"}},
    ])
    out["injection_verbatim"] = [i for i in out["injection"] if i["verdict"].startswith(("REFLECTED", "TAG-", "SSTI"))]

    # ── flags ────────────────────────────────────────────────────────────────
    out["flags_default"] = probe.battery_flags([
        {"name": "update locked", "path": "/updater.php?update=true", "expect": 403},
        {"name": "restore locked", "path": "/updater.php?restore=latest", "expect": 403},
        {"name": "updater landing", "path": "/updater.php", "expect": 200},
        {"name": "upload locked", "path": "/updater.php?action=upload_md", "method": "POST", "expect": 403},
        {"name": "save locked", "path": "/updater.php?action=save_clipboard", "method": "POST", "expect": 403},
        {"name": "api no key", "path": "/updater.php?action=status&format=json", "expect": 403},
        {"name": "api bad key", "path": "/updater.php?api_key=mdv_nope&action=status&format=json", "expect": 403},
        {"name": "api unknown action", "path": "/updater.php?action=bogus&format=json", "expect": 400},
        {"name": "api install via GET", "path": "/updater.php?action=install&format=json", "expect": 405},
    ])
    key = re.search(r"(?m)^API_KEY = (\S+)", app.read(".md.ini"))
    if key:
        K = key.group(1)
        out["api_key_format"] = {"value_prefix": K[:8] + "…", "hex_len": len(K) - 4,
                                 "shape_ok": bool(re.fullmatch(r"mdv_[0-9a-f]{48}", K))}
        for act, meth, exp in (("status", "GET", 200), ("conflicts", "GET", 200)):
            r = req(probe.url(f"/updater.php?api_key={K}&action={act}&format=json"), meth)
            out[f"api_{act}"] = {"status": r.status, "expected": exp, "ok": r.status == exp}
            if r.status == 200:
                try:
                    d = r.json()
                    out[f"api_{act}"]["envelope_keys"] = sorted(d.keys())
                    out[f"api_{act}"]["counts"] = d.get("counts")
                    out[f"api_{act}"]["ini"] = d.get("ini")
                except Exception as e:
                    out[f"api_{act}"]["json_error"] = str(e)

    out["flags_enabled"] = probe.battery_flags([
        {"name": "upload enabled", "ini": {"DISABLE_UPLOAD": "false"},
         "path": "/updater.php?action=upload_md", "method": "POST", "expect": 400},
        {"name": "clipboard disabled", "ini": {"DISABLE_CLIPBOARD": "true"},
         "path": entry, "method": "POST", "expect": 403},
    ])
    # clipboard disabled → POST md_preview should 403
    r = post_form(probe.url(entry), {"md_preview": "1", "content": "x"})
    out["clipboard_disabled_status"] = r.status
    app.set_ini({"DISABLE_CLIPBOARD": "false"})

    # ── upload validation ────────────────────────────────────────────────────
    app.set_ini({"DISABLE_UPLOAD": "false"})
    up = []
    for fn in ["ok.md", "OK.MD", "bad.php", ".hidden.md", "../evil.md", "a/b.md",
               "na<me>.md", 'a"b.md', "a|b.md", "a?b.md", "a*b.md", "a:b.md",
               "x" * 201 + ".md", "with space.md", "док.md", "em—dash.md"]:
        r = post_multipart(probe.url("/updater.php?action=upload_md"),
                           fields={}, files={"md_file": (fn, b"# t\n")})
        up.append({"filename": fn, "status": r.status, "body": excerpt(r.body, 90)})
    out["upload_matrix"] = up
    r = post_multipart(probe.url("/updater.php?action=upload_md"),
                       fields={}, files={"file": ("ok.md", b"# t\n")})
    out["upload_wrong_field_name"] = {"status": r.status, "body": excerpt(r.body, 90)}
    for d in ["docs", "../../etc", "/tmp", "a/b/c/d/e"]:
        r = post_multipart(probe.url("/updater.php?action=upload_md"),
                           fields={"dir": d}, files={"md_file": ("dirtest.md", b"# t\n")})
        out.setdefault("upload_dir_matrix", []).append({"dir": d, "status": r.status, "body": excerpt(r.body, 90)})

    # ── side effects ─────────────────────────────────────────────────────────
    out["files_written"] = probe.battery_disk()
    out["headers"] = probe.battery_headers([entry, "/updater.php"])
    return out


SUITES: dict[str, Callable[[Probe, str], dict]] = {
    "generic": suite_generic,
    "php-mdviewer": suite_php_mdviewer,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--repo", help="stage a fresh copy of this directory and serve it")
    src.add_argument("--base-url", help="probe an already-running instance")
    ap.add_argument("--copy", help="comma-separated names to stage from --repo")
    ap.add_argument("--serve-cmd", default=ServedApp.DEFAULT_CMD)
    ap.add_argument("--entry", default="/", help="entry path, e.g. /md.php")
    ap.add_argument("--suite", default="generic", choices=sorted(SUITES))
    ap.add_argument("-o", "--out", help="write JSON here")
    ap.add_argument("--md", help="also write a Markdown summary here")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    def run(probe):
        extra = SUITES[a.suite](probe, a.entry)
        return {"suite": a.suite, "entry": a.entry, "base_url": probe.base_url,
                "requests": probe.results, "extra": extra}

    if a.base_url:
        probe = Probe(a.base_url)
        report = run(probe)
    else:
        copy = [c.strip() for c in a.copy.split(",")] if a.copy else None
        with ServedApp(a.repo, copy=copy, serve_cmd=a.serve_cmd, keep=a.keep, quiet=False) as app:
            probe = Probe(app.base_url, app)
            report = run(probe)
            report["staged_docroot"] = str(app.root)
            report["server_log_tail"] = app.server_log(25)

    # console summary
    print("\n" + "=" * 78)
    print(f"SUITE {a.suite}  ·  {len(report['requests'])} requests")
    print("=" * 78)
    mism = [r for r in report["requests"] if r.get("matches_expectation") is False]
    for r in report["requests"]:
        flag = "" if r.get("matches_expectation", True) else "  ❌ EXPECTED " + ",".join(r.get("expected", []))
        print(f"  {str(r['status']):>5}  {r['method']:<5} {r['path'][:58]:<58}{flag}")
    if mism:
        print(f"\n{len(mism)} request(s) did not match the documented expectation — investigate.")
    ex = report.get("extra", {})
    if "traversal" in ex:
        t = ex["traversal"]
        print(f"\ntraversal : {sum(1 for x in t if x['denied'])}/{len(t)} denied, "
              f"{sum(1 for x in t if x['LEAKED-SENSITIVE-CONTENT'])} leaked sensitive content")
    if "injection" in ex:
        v = ex["injection_verbatim"]
        print(f"injection : {len(v)}/{len(ex['injection'])} payloads survived into the response")
        for x in v[:8]:
            print(f"    {x['verdict']:22} {x['payload'][:56]}")
    for hk, hv in (ex.get("headers") or {}).items():
        if hv.get("MISSING"):
            print(f"headers   : {hk} missing → {', '.join(hv['MISSING'][:6])}")
        if hv.get("leaks"):
            print(f"headers   : {hk} leaks → {hv['leaks']}")

    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
        print(f"\nwrote {a.out} ({Path(a.out).stat().st_size//1024} KB)")
    if a.md:
        p2 = Probe(a.base_url or "")
        p2.results = report["requests"]
        Path(a.md).write_text(p2.report_md(f"Probe report — {a.suite} on {a.entry}"))
        print(f"wrote {a.md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
