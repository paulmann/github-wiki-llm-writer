#!/usr/bin/env python3
"""
repo_scan.py — Phase 1 in one command: inventory any repository into facts.

Produces the raw material for research/summary.md, research/architecture.md and
research/facts.json without you grepping by hand. Language-aware but never
language-dependent: unknown layouts still yield a useful inventory.

    python3 scan/repo_scan.py workspace/repo/SUBJECT -o workspace/research/scan.json
    python3 scan/repo_scan.py workspace/repo/SUBJECT --brief     # human summary

What it extracts
  * git: HEAD sha, branch, commit count, first/last commit dates, tags,
         releases, remote URL, and a classified commit log
  * tree: every file with size and line count, grouped by extension,
         plus the largest files (where the logic usually lives)
  * entry points: files that look executable/served (index.*, main.*, app.*,
         *.php at root, bin/*, package.json scripts, Makefile targets)
  * symbols: functions/methods/classes/constants with line numbers, for
         PHP, JS/TS, Python, Go, Ruby, Java/C#
  * config surface: define()/const/`os.environ`/`process.env`/getenv/INI keys,
         env-var names, CLI flags, default values
  * network: every external URL (CDNs, APIs, update feeds) — this is where
         supply-chain and privacy facts come from
  * deps: composer.json / package.json / requirements.txt / go.mod / Cargo.toml /
         Gemfile / pom.xml — or the notable ABSENCE of them
  * security signals: escaping/sanitising calls, auth checks, path validation,
         exec/shell/eval, SQL, crypto, TLS options, header emission
  * docs: README(s), LICENSE + license type, CONTRIBUTING, SECURITY, docs/ tree
  * version strings: `Version: X.Y.Z`-style markers anywhere in the tree

The --brief output is designed to be read in two minutes and then drive the
research notes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

SKIP_DIRS = {
    ".git", ".svn", ".hg", "node_modules", "vendor", "bower_components",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox",
    ".venv", "venv", ".next", ".nuxt", ".output", "dist", "build", "out",
    "target", "coverage", ".cache", ".parcel-cache", ".turbo", ".svelte-kit",
    ".vite", ".nox", ".npm", ".ragraf", ".arena",
}
MAX_FILE_BYTES = 4_000_000
BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tiff", ".pdf",
    ".zip", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".woff", ".woff2",
    ".ttf", ".eot", ".otf", ".mp3", ".mp4", ".mov", ".avi", ".webm", ".wasm",
    ".so", ".dll", ".dylib", ".exe", ".class", ".jar", ".pyc", ".lock",
}

SYMBOL_PATTERNS = {
    ".php": [
        (r"^\s*(?:final\s+|abstract\s+)?function\s+([A-Za-z_]\w*)\s*\(", "function"),
        (r"^\s*(?:final\s+|abstract\s+)?class\s+([A-Za-z_]\w*)", "class"),
        (r"^\s*interface\s+([A-Za-z_]\w*)", "interface"),
        (r"^\s*trait\s+([A-Za-z_]\w*)", "trait"),
    ],
    ".js": [
        (r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", "function"),
        (r"^\s*(?:export\s+)?(?:default\s+)?class\s+([A-Za-z_$][\w$]*)", "class"),
        (r"^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>", "arrow"),
    ],
    ".ts": [
        (r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", "function"),
        (r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)", "class"),
        (r"^\s*(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)", "interface"),
        (r"^\s*(?:export\s+)?type\s+([A-Za-z_$][\w$]*)\s*=", "type"),
    ],
    ".py": [
        (r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(", "function"),
        (r"^\s*class\s+([A-Za-z_]\w*)", "class"),
    ],
    ".go": [
        (r"^func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\(", "function"),
        (r"^type\s+([A-Za-z_]\w*)\s+(?:struct|interface)", "type"),
    ],
    ".rb": [
        (r"^\s*def\s+([A-Za-z_]\w*!?=?)", "function"),
        (r"^\s*(?:class|module)\s+([A-Za-z_]\w*)", "class"),
    ],
    ".java": [(r"^\s*(?:public|private|protected)?\s*(?:static\s+)?[\w<>\[\]]+\s+([A-Za-z_]\w*)\s*\(", "method"),
              (r"^\s*(?:public\s+)?(?:abstract\s+|final\s+)?(?:class|interface|enum)\s+([A-Za-z_]\w*)", "class")],
    ".cs":  [(r"^\s*(?:public|private|protected|internal)?\s*(?:static\s+)?[\w<>\[\]]+\s+([A-Za-z_]\w*)\s*\(", "method"),
             (r"^\s*(?:public\s+)?(?:abstract\s+|sealed\s+)?(?:class|interface|struct|enum)\s+([A-Za-z_]\w*)", "class")],
    ".ps1": [(r"^\s*function\s+([A-Za-z_][\w-]*)", "function")],
    ".sh":  [(r"^\s*([A-Za-z_]\w*)\s*\(\s*\)\s*\{", "function")],
}

CONFIG_PATTERNS = [
    (r"\bdefine\(\s*['\"]([A-Z_][A-Z0-9_]*)['\"]", "php-define"),
    (r"^\s*const\s+([A-Z_][A-Z0-9_]*)\s*=", "const"),
    (r"^\s*(?:export\s+)?const\s+([A-Z_][A-Z0-9_]*)\s*=", "js-const"),
    (r"os\.environ(?:\.get)?\(\s*['\"]([A-Z_][A-Z0-9_]*)['\"]", "env"),
    (r"getenv\(\s*['\"]([A-Z_][A-Z0-9_]*)['\"]", "env"),
    (r"process\.env\.([A-Z_][A-Z0-9_]*)", "env"),
    (r"\$_(?:GET|POST|REQUEST|COOKIE|FILES|SERVER)\[\s*['\"]([A-Za-z_][\w]*)['\"]", "superglobal"),
    (r"^\s*([A-Z][A-Z0-9_]{2,})\s*=\s*(.+?)\s*$", "ini-key"),
]

URL_RE = re.compile(
    r"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%\-]+", re.IGNORECASE)
URL_IGNORE_HOSTS = ("w3.org", "schemas.", "example.com", "example.org", "localhost")

SECURITY_SIGNALS = {
    "output-escaping": r"htmlspecialchars|html\.escape|escapeHtml|e\(\s*\$|sanitize|purify|bleach|DOMPurify|template\.html|htmlEscape",
    "raw-html-passthrough": r"Markup\(|safe_join|\|\s*safe\b|dangerouslySetInnerHTML|v-html|innerHTML\s*=|\{!!|unescaped|raw_html|noescape",
    "path-validation": r"realpath|abspath|resolve\(\)|\.\.|basename\(|os\.path\.commonpath|path_traversal|traversal|startswith\(\s*root|is_relative_to",
    "exec-shell": r"\bexec\(|\beval\(|system\(|passthru\(|shell_exec\(|popen\(|proc_open\(|subprocess\.|child_process|os\.system|Runtime\.getRuntime",
    "sql": r"SELECT\s.+FROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|prepare\(|bindParam|mysqli_|pg_query",
    "crypto": r"hash\(|hash_file\(|hash_equals|random_bytes|openssl_|sodium_|bcrypt|argon2|pbkdf2|sha256|sha1|md5\(|hmac",
    "tls-options": r"CURLOPT_SSL_VERIFY|SSL_VERIFY|verify\s*=\s*False|rejectUnauthorized|InsecureSkipVerify|NODE_TLS_REJECT",
    "auth": r"password_verify|session_start|authenticate|authorize|login|csrf|token|api_key|API_KEY|Bearer|Authorization",
    "security-headers": r"Content-Security-Policy|X-Frame-Options|X-Content-Type-Options|Strict-Transport-Security|Referrer-Policy|Permissions-Policy",
    "file-upload": r"move_uploaded_file|UPLOAD_ERR|multipart|request\.files|multer|busboy|FormData",
    "signature-verify": r"verify_signature|gpg|signify|minisign|ed25519|signature|detached-sig|cosign",
}

VERSION_RE = re.compile(r"(?:Version|VERSION|version|@version)\s*[:=]\s*['\"]?v?(\d+\.\d+(?:\.\d+)?)")


def sh(args: list[str], cwd: Path) -> str:
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception:
        return ""


def git_info(root: Path) -> dict:
    if not (root / ".git").exists():
        return {"available": False}
    log = sh(["git", "log", "--format=%H|%ad|%s", "--date=short"], root)
    commits = [l.split("|", 2) for l in log.splitlines() if l.count("|") >= 2]
    classified = Counter()
    for _, _, subj in commits:
        m = re.match(r"^(feat|fix|docs|chore|refactor|test|perf|style|build|ci|revert)(\([^)]*\))?!?:", subj)
        classified[m.group(1) if m else ("version-bump" if re.match(r"^v?\d+\.\d+", subj) else "other")] += 1
    tags = [t for t in sh(["git", "tag"], root).splitlines() if t]
    return {
        "available": True,
        "head": sh(["git", "rev-parse", "--short", "HEAD"], root),
        "head_full": sh(["git", "rev-parse", "HEAD"], root),
        "branch": sh(["git", "rev-parse", "--abbrev-ref", "HEAD"], root),
        "remote": sh(["git", "remote", "get-url", "origin"], root),
        "commit_count": len(commits),
        "first_commit": commits[-1][1] if commits else None,
        "last_commit": commits[0][1] if commits else None,
        "tags": tags,
        "tag_count": len(tags),
        "commit_kinds": dict(classified),
        "recent_commits": [{"date": d, "subject": s} for _, d, s in commits[:40]],
        "authors": sh(["git", "shortlog", "-sne", "--all"], root).splitlines()[:10],
    }


def walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info")]
        for fn in filenames:
            yield Path(dirpath) / fn


def scan_file(p: Path, rel: str) -> dict:
    info = {"path": rel, "bytes": p.stat().st_size, "ext": p.suffix.lower()}
    if p.suffix.lower() in BINARY_EXT or info["bytes"] > MAX_FILE_BYTES:
        info["binary"] = True
        return info
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        info["unreadable"] = str(e)
        return info
    lines = text.splitlines()
    info["lines"] = len(lines)
    info["sha256_16"] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]

    pats = SYMBOL_PATTERNS.get(p.suffix.lower(), [])
    syms = []
    for i, line in enumerate(lines, 1):
        for pat, kind in pats:
            m = re.match(pat, line)
            if m:
                syms.append({"line": i, "kind": kind, "name": m.group(1)})
                break
    if syms:
        info["symbols"] = syms

    cfg = []
    for i, line in enumerate(lines, 1):
        for pat, kind in CONFIG_PATTERNS:
            m = re.search(pat, line)
            if m:
                key = m.group(1)
                if kind == "ini-key" and len(key) > 48:
                    continue
                val = (m.group(2).strip()[:60] if m.lastindex and m.lastindex >= 2 else None)
                cfg.append({"line": i, "kind": kind, "key": key, "value": val})
    if cfg:
        info["config"] = cfg[:200]

    urls = sorted({u.rstrip(").,;:'\"") for u in URL_RE.findall(text)
                   if not any(h in u for h in URL_IGNORE_HOSTS)})
    if urls:
        info["urls"] = urls[:60]

    sec = {k: len(re.findall(v, text)) for k, v in SECURITY_SIGNALS.items()}
    sec = {k: v for k, v in sec.items() if v}
    if sec:
        info["security_signals"] = sec

    vs = VERSION_RE.findall(text[:4000])
    if vs:
        info["version_marker"] = vs[0]

    return info


def detect_deps(root: Path, files: list[dict]) -> dict:
    manifests = {
        "composer.json": "php/composer", "package.json": "node/npm",
        "requirements.txt": "python/pip", "pyproject.toml": "python",
        "setup.py": "python", "Pipfile": "python/pipenv", "poetry.lock": "python/poetry",
        "go.mod": "go", "Cargo.toml": "rust", "Gemfile": "ruby/bundler",
        "pom.xml": "java/maven", "build.gradle": "java/gradle", "build.gradle.kts": "java/gradle",
        "CMakeLists.txt": "c/cmake", "Makefile": "make", "*.csproj": "dotnet",
        "composer.lock": "php/composer-lock", "package-lock.json": "node/lock",
        "yarn.lock": "node/lock", "pnpm-lock.yaml": "node/lock",
    }
    found = {}
    names = {Path(f["path"]).name for f in files}
    for m, eco in manifests.items():
        if m in names:
            found[m] = eco
    declared = []
    for man in ("composer.json", "package.json"):
        p = root / man
        if p.exists():
            try:
                d = json.loads(p.read_text())
                declared += [{"manifest": man, "section": s, "name": k, "constraint": v}
                             for s in ("require", "require-dev", "dependencies", "devDependencies")
                             for k, v in (d.get(s) or {}).items()]
            except Exception:
                pass
    req = root / "requirements.txt"
    if req.exists():
        declared += [{"manifest": "requirements.txt", "name": l.split("=")[0].split(">")[0].split("<")[0].strip()}
                     for l in req.read_text().splitlines() if l.strip() and not l.startswith(("#", "-"))]
    return {"manifests_found": found, "no_manifest": not found, "declared": declared}


def license_type(root: Path) -> dict:
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING"):
        p = root / name
        if p.exists():
            t = p.read_text(errors="replace")
            head = t[:2000].lower()
            kind = "unknown"
            for k, pat in (("MIT", "permission is hereby granted, free of charge"),
                           ("Apache-2.0", "apache license"),
                           ("GPL-3.0", "gnu general public license"),
                           ("GPL-2.0", "gnu general public license"),
                           ("BSD-3", "redistributions of source code"),
                           ("BSD-2", "redistribution and use in source"),
                           ("MPL-2.0", "mozilla public license"),
                           ("Unlicense", "this is free and unencumbered software"),
                           ("AGPL-3.0", "gnu affero general public license")):
                if pat in head:
                    kind = k
                    break
            cr = re.search(r"Copyright\s*(?:\(c\))?\s*(\d{4})?\s*([^\n]{0,60})", t, re.I)
            extra = [l.strip() for l in t.splitlines()[:40]
                     if re.search(r"attribut|shall be included|repository", l, re.I)]
            return {"file": name, "type": kind,
                    "copyright": cr.group(0).strip() if cr else None,
                    "extra_clauses": extra[:5], "bytes": len(t)}
    return {"file": None, "type": "none"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Inventory a repository into research facts.")
    ap.add_argument("root")
    ap.add_argument("-o", "--out", help="write JSON here (default: stdout if --brief is off)")
    ap.add_argument("--brief", action="store_true", help="print a human-readable summary instead of JSON")
    ap.add_argument("--max-files", type=int, default=4000)
    a = ap.parse_args()

    root = Path(a.root).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr); return 2

    all_files = []
    for p in walk(root):
        rel = str(p.relative_to(root))
        all_files.append(scan_file(p, rel))
        if len(all_files) >= a.max_files:
            break

    by_ext = Counter()
    lines_by_ext = Counter()
    for f in all_files:
        by_ext[f["ext"] or "(none)"] += 1
        lines_by_ext[f["ext"] or "(none)"] += f.get("lines", 0)

    code_exts = {".php", ".js", ".ts", ".jsx", ".tsx", ".py", ".go", ".rb", ".java", ".cs",
                 ".c", ".h", ".cpp", ".rs", ".sh", ".ps1", ".pl", ".lua", ".swift", ".kt"}
    code = [f for f in all_files if f["ext"] in code_exts and not f.get("binary")]
    # Entry points: conventional names, script dirs, AND any server-side script
    # sitting at the repository root (a root-level .php/.py/.rb/.js is almost
    # always a request handler — e.g. md.php, updater.php, index.cgi).
    ENTRY_NAME = re.compile(r"(^|/)(index|main|app|server|cli|run|bootstrap|manage|wsgi|asgi|__main__|handler|lambda_function)\.")
    SERVER_EXT = {".php", ".py", ".rb", ".pl", ".cgi", ".asp", ".aspx", ".jsp"}
    entryish = [f for f in all_files
                if ENTRY_NAME.search(f["path"])
                or f["path"].startswith(("bin/", "scripts/", "cmd/", "public/", "www/", "htdocs/"))
                or (f["ext"] in SERVER_EXT and "/" not in f["path"])]

    urls = defaultdict(list)
    for f in all_files:
        for u in f.get("urls", []):
            host = re.sub(r"^https?://", "", u).split("/")[0]
            urls[host].append({"url": u, "in": f["path"]})

    sec = defaultdict(int)
    sec_where = defaultdict(set)
    for f in all_files:
        for k, v in (f.get("security_signals") or {}).items():
            sec[k] += v
            sec_where[k].add(f["path"])

    versions = [{"path": f["path"], "version": f["version_marker"]}
                for f in all_files if f.get("version_marker")]

    cfg_keys = Counter()
    for f in all_files:
        for c in f.get("config", []):
            cfg_keys[(c["kind"], c["key"])] += 1

    docs = [f["path"] for f in all_files
            if re.search(r"(^|/)(README|CHANGELOG|CONTRIBUTING|SECURITY|CODE_OF_CONDUCT|AUTHORS|ARCHITECTURE|docs?/)", f["path"], re.I)]

    out = {
        "root": str(root),
        "scanned_files": len(all_files),
        "git": git_info(root),
        "license": license_type(root),
        "dependencies": detect_deps(root, all_files),
        "totals": {
            "files": len(all_files),
            "bytes": sum(f["bytes"] for f in all_files),
            "code_files": len(code),
            "code_lines": sum(f.get("lines", 0) for f in code),
            "by_extension": dict(by_ext.most_common(30)),
            "lines_by_extension": dict(lines_by_ext.most_common(20)),
        },
        "largest_files": sorted(
            [{"path": f["path"], "bytes": f["bytes"], "lines": f.get("lines")}
             for f in all_files if not f.get("binary")],
            key=lambda x: -(x["lines"] or 0))[:25],
        "entry_points": [f["path"] for f in entryish][:40],
        "docs": docs[:40],
        "version_markers": versions[:60],
        "external_hosts": {h: v[:6] for h, v in sorted(urls.items(), key=lambda kv: -len(kv[1]))},
        "security_signals": {k: {"count": v, "files": sorted(sec_where[k])[:8]}
                             for k, v in sorted(sec.items(), key=lambda kv: -kv[1])},
        "config_keys": [{"kind": k, "key": n, "occurrences": c}
                        for (k, n), c in cfg_keys.most_common(120)],
        "symbols_by_file": {f["path"]: f["symbols"] for f in all_files if f.get("symbols")},
        "files": [{k: v for k, v in f.items() if k not in ("config", "symbols")} for f in all_files],
    }

    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
        print(f"wrote {a.out} ({Path(a.out).stat().st_size//1024} KB)")

    if a.brief or not a.out:
        g, t = out["git"], out["totals"]
        print("=" * 78)
        print(f"REPO  {root.name}")
        print("=" * 78)
        if g.get("available"):
            print(f"git      : {g['branch']} @ {g['head']} · {g['commit_count']} commits · "
                  f"{g['first_commit']} → {g['last_commit']}")
            print(f"           remote: {g['remote']}")
            print(f"           tags: {g['tag_count']}{'  ← NO TAGS: versioning is by file marker' if g['tag_count']==0 else ''}")
            print(f"           kinds: {g['commit_kinds']}")
        lic = out["license"]
        print(f"license  : {lic['type']} ({lic['file']})" + (f" — extra clauses: {lic['extra_clauses']}" if lic.get("extra_clauses") else ""))
        d = out["dependencies"]
        print(f"deps     : {d['manifests_found'] or 'NO MANIFEST — zero declared dependencies'}")
        if d["declared"]:
            for x in d["declared"][:12]:
                print(f"           {x.get('name')} {x.get('constraint','')}")
        print(f"size     : {t['files']} files · {t['bytes']//1024} KB · "
              f"{t['code_files']} code files · {t['code_lines']:,} code lines")
        print(f"by ext   : {dict(list(t['by_extension'].items())[:12])}")
        print("\nlargest (where the logic lives):")
        for f in out["largest_files"][:10]:
            print(f"  {f['lines'] or 0:7,} lines  {f['bytes']//1024:5} KB  {f['path']}")
        print(f"\nentry points : {out['entry_points'][:12]}")
        print(f"docs         : {out['docs'][:12]}")
        if out["version_markers"]:
            print("\nversion markers:")
            for v in out["version_markers"][:14]:
                print(f"  {v['version']:12} {v['path']}")
        print("\nexternal hosts (supply chain / privacy):")
        for h, hits in list(out["external_hosts"].items())[:14]:
            print(f"  {len(hits):3}×  {h}")
            for x in hits[:2]:
                print(f"         {x['url'][:96]}   [{x['in']}]")
        print("\nsecurity signals:")
        for k, v in out["security_signals"].items():
            print(f"  {v['count']:5}  {k:24} {v['files'][:3]}")
        print("\nconfig keys (top):")
        for c in out["config_keys"][:25]:
            print(f"  {c['occurrences']:4}×  [{c['kind']}] {c['key']}")
        print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
