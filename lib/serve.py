#!/usr/bin/env python3
"""
serve.py — start a throwaway instance of the app under test, SAFELY.

WHY THIS EXISTS — READ THIS, IT COST A DEBUG CYCLE
    The obvious way to test a PHP app is:

        cd /tmp/app && php -S 127.0.0.1:8080 &

    If port 8080 is ALREADY bound by an older instance from an earlier
    experiment, the new server prints "Address already in use", dies, and the
    shell happily continues. Every subsequent request then hits the OLD
    instance — with its OLD document root and its OLD state files. Results look
    plausible and are wrong. This actually happened: a `.md.ini` "was not
    created" in a directory that had in fact never been served.

    This module makes that impossible:
      * it picks a FREE port (or verifies the requested one is free),
      * it waits for the socket to actually accept connections,
      * it fails loudly instead of continuing,
      * it stages a CLEAN copy of the app in a temp dir, so state files created
        by a previous run cannot contaminate the test,
      * and it kills what it started.

USAGE AS A MODULE
    import sys; sys.path.insert(0, '/path/to/github-wiki-llm-writer/lib')
    from serve import ServedApp

    with ServedApp('/path/to/repo', copy=['md.php', 'css', 'js']) as app:
        print(app.url('/md.php'))
        r = app.get('/md.php')
        print(r.status, r.header('Content-Type'))
        app.write('md.md', '# Hello\\n\\nWorld\\n')      # stage a fixture document
        app.set_ini({'DISABLE_UPLOAD': 'false'})          # flip a config flag
        print(app.ls())                                   # what did the app write?

USAGE AS A CLI (foreground, Ctrl-C to stop)
    python3 serve.py /path/to/repo --copy 'md.php,css,js' --serve-cmd 'php -S {host}:{port}'
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
from req import Response, get, post_form, post_multipart, req  # noqa: E402


def free_port(preferred: int | None = None, host: str = "127.0.0.1") -> int:
    """Return a port that is genuinely free right now.

    If `preferred` is given and busy, this RAISES rather than silently picking
    another one — because a test that assumes a fixed port must not run against
    a different server.
    """
    if preferred is not None:
        with socket.socket() as s:
            try:
                s.bind((host, preferred))
                return preferred
            except OSError as e:
                raise RuntimeError(
                    f"port {preferred} on {host} is already in use ({e}). "
                    "Something is already listening — kill it, or pass --port 0 "
                    "to let the OS choose. Do NOT proceed: requests would hit "
                    "the other server."
                ) from e
    with socket.socket() as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def wait_ready(host: str, port: int, timeout: float = 20.0) -> float:
    """Block until the port accepts TCP connections. Returns seconds waited."""
    t0 = time.time()
    deadline = t0 + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            s.settimeout(0.5)
            try:
                s.connect((host, port))
                return time.time() - t0
            except OSError:
                time.sleep(0.15)
    raise TimeoutError(f"server on {host}:{port} did not become ready in {timeout}s")


class ServedApp:
    """A staged copy of an app, served by a throwaway process.

    Parameters
    ----------
    source      : directory containing the app (e.g. a fresh git clone)
    copy        : names to stage. None = everything except VCS dirs.
    serve_cmd   : command template; {host} {port} {root} are substituted.
                  Default targets the PHP built-in server.
    port        : fixed port, or None/0 to auto-pick a free one.
    keep        : do not delete the staged directory on exit (for post-mortems).
    """

    DEFAULT_CMD = "php -S {host}:{port} -t {root}"
    VCS_SKIP = {".git", ".svn", ".hg", "node_modules", "__pycache__", ".ragraf"}

    def __init__(
        self,
        source: str | Path,
        copy: Sequence[str] | None = None,
        serve_cmd: str | None = None,
        port: int | None = None,
        host: str = "127.0.0.1",
        keep: bool = False,
        quiet: bool = True,
    ) -> None:
        self.source = Path(source).resolve()
        if not self.source.is_dir():
            raise FileNotFoundError(f"source is not a directory: {self.source}")
        self.serve_cmd = serve_cmd or self.DEFAULT_CMD
        self.host = host
        self.keep = keep
        self.quiet = quiet
        self._copy = copy
        self._requested_port = port
        self.root: Path | None = None
        self.proc: subprocess.Popen | None = None
        self.port: int = 0
        self.log: Path | None = None

    # ── lifecycle ────────────────────────────────────────────────────────────
    def __enter__(self) -> "ServedApp":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def start(self) -> "ServedApp":
        self.root = Path(tempfile.mkdtemp(prefix="probe-app-"))
        self._stage()
        self.port = free_port(self._requested_port, self.host)
        self.log = self.root.parent / f"{self.root.name}.server.log"
        cmd = self.serve_cmd.format(host=self.host, port=self.port, root=self.root)
        self._log(f"$ {cmd}   (docroot {self.root})")
        with open(self.log, "wb") as lf:
            self.proc = subprocess.Popen(
                cmd.split(),
                cwd=str(self.root),
                stdout=lf,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid if hasattr(os, "setsid") else None,
            )
        try:
            waited = wait_ready(self.host, self.port)
        except Exception:
            self._dump_log()
            self.stop()
            raise
        # Belt and braces: the port may be open while the interpreter is still
        # failing on every request (missing extension, parse error).
        probe = get(self.base_url + "/", timeout=10)
        if probe.status == "ERR":
            self._dump_log()
            self.stop()
            raise RuntimeError(f"server accepted TCP but no HTTP response: {probe.text}")
        self._log(f"ready in {waited:.2f}s → {self.base_url}")
        return self

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                if hasattr(os, "killpg"):
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
                else:
                    self.proc.terminate()
                self.proc.wait(timeout=8)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None
        if self.root and not self.keep:
            shutil.rmtree(self.root, ignore_errors=True)
            if self.log and self.log.exists():
                self.log.unlink(missing_ok=True)
            self.root = None

    def _stage(self) -> None:
        names = self._copy
        if names is None:
            names = [p.name for p in self.source.iterdir() if p.name not in self.VCS_SKIP]
        for name in names:
            src = self.source / name
            dst = self.root / name
            if not src.exists():
                self._log(f"  (skip, absent in source: {name})")
                continue
            if src.is_dir():
                shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
        self._log(f"  staged {len(names)} entr{'y' if len(names) == 1 else 'ies'}")

    # ── fixtures ─────────────────────────────────────────────────────────────
    def write(self, relpath: str, content: str | bytes, mode: int | None = None) -> Path:
        """Create/overwrite a file inside the staged docroot (parents auto-made)."""
        p = self.root / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content.encode() if isinstance(content, str) else content)
        if mode is not None:
            p.chmod(mode)
        return p

    def mkdir(self, relpath: str, mode: int = 0o755) -> Path:
        p = self.root / relpath
        p.mkdir(parents=True, exist_ok=True)
        p.chmod(mode)
        return p

    def set_ini(self, values: dict, path: str = ".md.ini") -> None:
        """Merge key=value pairs into an INI-ish config file, creating it if absent."""
        p = self.root / path
        text = p.read_text() if p.exists() else ""
        for k, v in values.items():
            v = str(v)
            if f"\n{k} " in text or text.startswith(f"{k} "):
                import re
                text = re.sub(rf"(?m)^;?\s*{re.escape(k)}\s*=.*$", f"{k} = {v}", text)
            else:
                text = text.rstrip("\n") + f"\n{k} = {v}\n"
        p.write_text(text)

    def ls(self, pattern: str = "**/*") -> list[str]:
        """Relative paths of everything the app has written into the docroot."""
        out = []
        for p in sorted(self.root.glob(pattern)):
            if p.is_file():
                out.append(str(p.relative_to(self.root)))
        return out

    def read(self, relpath: str) -> str:
        return (self.root / relpath).read_text(errors="replace")

    # ── requests ─────────────────────────────────────────────────────────────
    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def url(self, path: str = "/") -> str:
        if path.startswith(("http://", "https://")):
            return path
        return self.base_url + (path if path.startswith("/") else "/" + path)

    def get(self, path: str, **kw) -> Response:
        return get(self.url(path), **kw)

    def post(self, path: str, fields: dict, **kw) -> Response:
        return post_form(self.url(path), fields, **kw)

    def upload(self, path: str, field: str, filename: str, content: str | bytes,
               fields: dict | None = None, **kw) -> Response:
        return post_multipart(self.url(path), fields=fields or {},
                              files={field: (filename, content)}, **kw)

    def request(self, path: str, method: str = "GET", **kw) -> Response:
        return req(self.url(path), method, **kw)

    # ── diagnostics ──────────────────────────────────────────────────────────
    def server_log(self, tail: int = 40) -> str:
        if not self.log or not self.log.exists():
            return "(no server log)"
        return "\n".join(self.log.read_text(errors="replace").splitlines()[-tail:])

    def _dump_log(self) -> None:
        sys.stderr.write("\n--- server log ---\n" + self.server_log(60) + "\n------------------\n")

    def _log(self, msg: str) -> None:
        if not self.quiet:
            print(f"[serve] {msg}", file=sys.stderr)


# ──────────────────────────────────────────────────────────────────────────────
def _main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Serve a staged copy of an app on a verified-free port.")
    p.add_argument("source", help="directory containing the app")
    p.add_argument("--copy", help="comma-separated names to stage (default: all but VCS dirs)")
    p.add_argument("--serve-cmd", default=ServedApp.DEFAULT_CMD,
                   help="command template with {host} {port} {root}")
    p.add_argument("--port", type=int, default=None, help="fixed port (fails loudly if busy)")
    p.add_argument("--keep", action="store_true", help="keep the staged dir for inspection")
    p.add_argument("--check", default=None, help="path to GET once ready (e.g. /md.php)")
    a = p.parse_args(argv)

    copy = [c.strip() for c in a.copy.split(",")] if a.copy else None
    with ServedApp(a.source, copy=copy, serve_cmd=a.serve_cmd, port=a.port,
                   keep=a.keep, quiet=False) as app:
        print(f"docroot : {app.root}")
        print(f"url     : {app.base_url}")
        print(f"log     : {app.log}")
        if a.check:
            r = app.get(a.check)
            print(f"GET {a.check} → HTTP {r.status}, {len(r.body)} bytes")
        print("\nPress Ctrl-C to stop.")
        try:
            while True:
                time.sleep(0.5)
                if app.proc and app.proc.poll() is not None:
                    print(f"server exited with code {app.proc.returncode}", file=sys.stderr)
                    print(app.server_log(40), file=sys.stderr)
                    return 1
        except KeyboardInterrupt:
            print("\nstopping")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
