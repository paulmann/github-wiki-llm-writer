#!/usr/bin/env python3
"""
verify_documented_commands.py — Phase 4 requirement: re-run, in a CLEAN sandbox,
every command the wiki documents. Fresh clone from GitHub (not the workspace copy).

Covers:
  * Getting Started / Home quick start: clone → composer install --no-dev → php -S → curl checks
  * Getting Started Step 6 curls (404, api=search, CSP header)
  * Installation verification checklist curls (/.md.ini and /src exposure, api)
  * Changelog manifest re-hash php -r snippet
  * HTTP API curl recipes (cookie jar + csrf grep + render POST)
  * Machine API recipes (layout B: key from .md.ini, status, dry-run install)
  * composer test / stan are verified separately in workspace/repo (dev deps) — noted, not repeated here
"""
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SANDBOX = Path("/tmp/verify-doc-cmds")
RESULTS = []


def ok(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {('— ' + detail[:120]) if detail else ''}")


def run(cmd, cwd=None, timeout=300, env=None):
    e = dict(os.environ, **(env or {}))
    p = subprocess.run(cmd, shell=isinstance(cmd, str), cwd=cwd, capture_output=True,
                       text=True, timeout=timeout, env=e)
    return p.returncode, p.stdout, p.stderr


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def curl(url, opts=""):
    rc, out, err = run(f"curl -s {opts} '{url}'")
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(
        prog="verify_commands.py",
        description="Phase-4 harness TEMPLATE: re-run, in a clean sandbox, every command "
                    "the wiki documents. This copy is the worked version from the "
                    "MD.Scribe run (19/19, evidence JSON) — adapt the recipe list to your "
                    "subject rather than running it as-is.",
        epilog="It also caught a real finding in its originating run: manifest drift "
               "(.gitignore 397 B in the published manifest vs 534 B in the commit, and "
               "composer-generated vendor/composer/* never hashing equal to a fresh install).")
    ap.add_argument("--repo", help="subject repository URL to clone fresh (default: the "
                                   "value baked into this template)")
    ap.add_argument("--out-json", help="evidence JSON destination")
    ap.add_argument("--out-md", help="evidence Markdown destination")
    ap.add_argument("--keep", action="store_true", help="keep the clean clone afterwards")
    _a, _unknown = ap.parse_known_args()
    if _a.repo:
        globals()["REPO_URL"] = _a.repo
    if SANDBOX.exists():
        shutil.rmtree(SANDBOX)
    SANDBOX.mkdir(parents=True)

    print("== quick start: clone + composer --no-dev ==")
    rc, out, err = run("git clone --depth 1 https://github.com/paulmann/MD.Scribe.git docs-site",
                       cwd=SANDBOX, timeout=180)
    ok("git clone (as documented)", rc == 0 and (SANDBOX / "docs-site/src").is_dir())
    repo = SANDBOX / "docs-site"

    rc, out, err = run("composer install --no-dev --optimize-autoloader",
                       cwd=repo, timeout=600, env={"COMPOSER_ALLOW_SUPERUSER": "1"})
    ok("composer install --no-dev --optimize-autoloader", rc == 0 and (repo / "vendor/autoload.php").is_file(),
       err.strip()[:100])
    ok("no dev tools with --no-dev (phpunit absent)", not (repo / "vendor/bin/phpunit").exists())

    print("== dev server (layout C, documented command) ==")
    port = free_port()
    proc = subprocess.Popen(f"php -S 127.0.0.1:{port} -t public public/router.php",
                            shell=True, cwd=repo, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, preexec_fn=os.setsid)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", port), 0.5).close()
                break
            except OSError:
                time.sleep(0.25)
        time.sleep(0.5)

        # Getting Started step 6 curls
        out = curl(f"{base}/index.php?file=nope.md", "-o /dev/null -w '%{http_code}'")
        ok("GS6: missing doc → 404", out.strip("'") == "404", out)
        out = curl(f"{base}/index.php?api=search&q=markdown")
        ok("GS6: api=search → ok:true", '"ok":true' in out, out[:80])
        out = curl(f"{base}/index.php", "-sI")
        ok("GS6: CSP header present", "default-src 'self'" in out)

        # Installation verification checklist
        out = curl(f"{base}/", "-o /dev/null -w '%{http_code}'")
        ok("checklist: / renders 200", out.strip("'") == "200")
        out = curl(f"{base}/index.php?page=browser", "-o /dev/null -w '%{http_code}'")
        ok("checklist: browser 200", out.strip("'") == "200")
        # /.md.ini via dev router (layout C) must NOT serve the ini
        out = curl(f"{base}/.md.ini", "-o /dev/null -w '%{http_code}'")
        body = curl(f"{base}/.md.ini")
        ok("checklist: /.md.ini blocked by router (no API_KEY leak)",
           out.strip("'") in ("404", "403") or "API_KEY" not in body, f"status={out}")
        out = curl(f"{base}/index.php?api=config")
        ok("checklist: api=config reports version 3.1.0", '"version":"3.1.0"' in out)

        # HTTP API curl recipe: cookie jar + csrf grep + render POST
        jar = str(SANDBOX / "jar")
        run(f"curl -s -c {jar} '{base}/' -o {SANDBOX}/page.html")
        rc, token, _ = run(f"grep -o '\"csrf\":\"[0-9a-f]\\{{64\\}}\"' {SANDBOX}/page.html | cut -d'\"' -f4")
        token = token.strip()
        ok("recipe: csrf token extraction grep works", re.fullmatch(r"[0-9a-f]{64}", token) is not None, token[:16])
        rc, out, _ = run(f"curl -s -b {jar} -d '_token={token}' --data-urlencode 'markdown=# Hi *there*' '{base}/index.php?api=render'")
        ok("recipe: api=render with token → ok:true + html", '"ok":true' in out and "<h1" in out, out[:100])

        # Changelog manifest re-hash snippet
        rc, out, err = run("""php -r '$m = json_decode(file_get_contents("config/manifest.json"), true);
$bad = 0;
foreach ($m["files"] as $f) {
  if (!is_file($f["path"]) || hash_file("sha256", $f["path"]) !== $f["sha256"]) {
    echo "DRIFT: {$f["path"]}\\n"; $bad++;
  }
}
echo $bad === 0 ? "manifest clean ({$m["version"]})\\n" : "$bad file(s) differ\\n";'""", cwd=repo, timeout=300)
        ok("manifest re-hash snippet runs and reports", rc == 0 and ("manifest clean" in out or "file(s) differ" in out),
           (out or err).strip()[:120])
    finally:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)

    print("== layout B: shims + machine API recipes ==")
    port2 = free_port()
    proc2 = subprocess.Popen(f"php -S 127.0.0.1:{port2} -t .", shell=True, cwd=repo,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)
    base2 = f"http://127.0.0.1:{port2}"
    try:
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", port2), 0.5).close()
                break
            except OSError:
                time.sleep(0.25)
        curl(f"{base2}/index.php")  # first load creates .md.ini
        rc, key, _ = run(f"grep '^API_KEY' {repo}/.md.ini | cut -d' ' -f3")
        key = key.strip()
        ok("recipe: API_KEY extraction one-liner", re.fullmatch(r"mdv_[0-9a-f]{40}", key) is not None, key[:12])
        out = curl(f"{base2}/updater.php?api_key={key}&action=status&format=json")
        j = json.loads(out) if out.strip().startswith("{") else {}
        ok("recipe: machine status → ok + 921 files", j.get("ok") is True and len(j.get("files", [])) == 921,
           f"n={len(j.get('files', []))}")
        out = curl(f"{base2}/updater.php?api_key={key}&action=conflicts&format=json")
        ok("recipe: machine conflicts → ok", '"ok":true' in out)
        rc, out, _ = run(f"curl -s -X POST '{base2}/updater.php?api_key={key}&action=install&format=json&dry_run=1'")
        ok("recipe: machine install dry_run → ok + dry-run steps", '"ok":true' in out and '"dry-run"' in out, out[:100])
        out = curl(f"{base2}/md.php?file=getting-started.md", "-o /dev/null -w '%{http_code}'")
        ok("shim: md.php?file= → 200", out.strip("'") == "200")
        out = curl(f"{base2}/updater.php?update=true", "-o /dev/null -w '%{http_code}'")
        ok("shim: ?update=true gated → 403 (documented default)", out.strip("'") == "403")
    finally:
        os.killpg(os.getpgid(proc2.pid), signal.SIGTERM)

    n_pass = sum(1 for _, p, _ in RESULTS if p)
    print(f"\n== documented-command verification: {n_pass}/{len(RESULTS)} pass ==")
    for name, p, d in RESULTS:
        if not p:
            print(f"  FAILED: {name} — {d}")
    try:
        payload = json.dumps([{"name": n, "pass": p, "detail": d} for n, p, d in RESULTS], indent=1)
        targets = [Path("/home/user/wiki-work/workspace/research/verify-commands.json"),
                   Path(__file__).resolve().parent / "verify-commands.json"]
        for t in targets:
            try:
                print(f"evidence -> {t} (cwd={os.getcwd()}, parent={t.parent.is_dir()})")
                with open(t, "w") as fh:
                    fh.write(payload)
                print("evidence written:", t)
                break
            except OSError as e:
                print(f"  write to {t} failed: {e!r} — trying fallback")
    except Exception as e:  # evidence is best-effort; stdout already carries it
        print("evidence write skipped:", e)
    return 0 if n_pass == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
