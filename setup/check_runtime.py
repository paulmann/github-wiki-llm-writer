#!/usr/bin/env python3
"""
check_runtime.py — refuse to probe a subject the installed runtime cannot boot.

WHY THIS EXISTS
    `bootstrap.sh` installs the DISTRO's runtime. On Debian bookworm that is PHP
    8.2 — and a subject that requires 8.3 (`json_validate()`, typed class
    constants) does not boot at all. Every request then returns a 500, and an
    agent that does not check will happily record "the application is broken" or,
    worse, document the error page as behaviour. This is a PITFALLS class-A trap:
    silently wrong results.

    A field run hit exactly this and had to hand-install sury PHP 8.3.

WHAT IT DOES
    Reads the subject's declared runtime floor — `composer.json` → `require.php`,
    `package.json` → `engines.node`, or `go.mod` → `go X.Y` — compares it with the
    installed runtime, and exits **2** on a mismatch so the caller can stop.

    It also reports whether dependencies are installed (`vendor/autoload.php`,
    `node_modules`), because `composer install` failing for want of `unzip` prints
    a usage dump that reads like "you passed a wrong flag" (PITFALLS B9).

USAGE
    python3 setup/check_runtime.py <subject-dir> [--quiet]
    exit 0 = fine or nothing declared · exit 2 = mismatch · exit 1 = bad argument
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def sh(cmd: str) -> str:
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        return ""


def declared_floor(subj: Path):
    """Return (constraint_string, source_description) or (None, None)."""
    cj = subj / "composer.json"
    if cj.exists():
        try:
            req = (json.loads(cj.read_text(encoding="utf-8")).get("require") or {}).get("php")
            if req:
                return req, "composer.json require.php"
        except Exception:
            pass
    pj = subj / "package.json"
    if pj.exists():
        try:
            eng = (json.loads(pj.read_text(encoding="utf-8")).get("engines") or {}).get("node")
            if eng:
                return eng, "package.json engines.node"
        except Exception:
            pass
    gm = subj / "go.mod"
    if gm.exists():
        m = re.search(r"(?m)^go\s+(\d+\.\d+)", gm.read_text(encoding="utf-8", errors="replace"))
        if m:
            return m.group(1), "go.mod"
    # a bare README/docs claim is worth surfacing even though it is not machine-readable
    for name in ("README.md", "readme.md"):
        rd = subj / name
        if rd.exists():
            m = re.search(r"(?i)\bphp\s*(?:>=|version)?\s*(\d+\.\d+(?:\.\d+)?)\s*\+", rd.read_text(errors="replace"))
            if m:
                return ">=" + m.group(1), f"{name} (prose, not machine-readable)"
    return None, None


def installed_version(prog: str) -> str:
    flag = {"php": "-r 'echo PHP_VERSION;'", "node": "--version", "go": "version"}.get(prog, "--version")
    out = sh(f"{prog} {flag} 2>/dev/null")
    m = re.search(r"(\d+)\.(\d+)", out)
    return out.splitlines()[0] if out else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("subject", help="directory containing the cloned subject")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    subj = Path(a.subject)
    if not subj.is_dir():
        print(f"not a directory: {subj}", file=sys.stderr)
        return 1

    constraint, source = declared_floor(subj)
    if not constraint:
        if not a.quiet:
            print("  runtime floor: none declared — nothing to compare")
        return 0

    m = re.search(r"(\d+)\.(\d+)", constraint)
    need = (int(m.group(1)), int(m.group(2))) if m else None
    print(f"  declared : {constraint}   ({source})")

    prog = "php" if (subj / "composer.json").exists() else ("node" if (subj / "package.json").exists()
                                                            else ("go" if (subj / "go.mod").exists() else "php"))
    ver = installed_version(prog)
    if not ver:
        print(f"  installed: {prog} NOT FOUND — install it before probing")
        return 2
    mm = re.search(r"(\d+)\.(\d+)", ver)
    have = (int(mm.group(1)), int(mm.group(2))) if mm else None
    bad = bool(need and have and have < need)
    print(f"  installed: {prog} {ver}   -> {'MISMATCH' if bad else 'OK'}")

    # dependency state (informational, but it is the next thing that fails)
    if prog == "php" and (subj / "composer.json").exists():
        if not (subj / "vendor" / "autoload.php").exists():
            print("  deps     : vendor/ MISSING — run `composer install --no-dev`")
            if not shutil.which("unzip"):
                print("             and install `unzip` first, or composer prints a "
                      "usage dump instead of an error (PITFALLS B9)")
        else:
            print("  deps     : vendor/ present")
    if prog == "node" and not (subj / "node_modules").exists():
        print("  deps     : node_modules/ MISSING — run `npm ci` or `npm install`")

    if bad:
        bar = "█" * 64
        print(f"\n  {bar}")
        print(f"  █ RUNTIME MISMATCH: the subject needs {constraint}; found {prog} {ver}.")
        print("  █ It will NOT BOOT, so every probe would measure a corpse and every")
        print("  █ 'finding' would be fiction. Fix the runtime BEFORE probing.")
        print("  █ PHP on Debian bookworm: see setup/PITFALLS.md §B10 for the sury recipe.")
        print(f"  {bar}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
