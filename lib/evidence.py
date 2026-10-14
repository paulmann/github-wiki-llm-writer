#!/usr/bin/env python3
"""
evidence.py — write probe evidence so that a filesystem hiccup cannot lose it.

WHY THIS EXISTS
    A field run hit this: the final line of a long probe script did
    `Path(""$ARENA_WORKSPACE"/.../research/verify-commands.json").write_text(...)` and
    raised FileNotFoundError, while in the SAME process `parent.is_dir()` printed
    False and the shell — a second later — saw and wrote that directory fine. It
    reproduced inside one long script after a series of spawn/kill cycles
    (`preexec_fn=os.setsid` + `os.killpg`); a minimal repro outside the script
    worked. Cause unknown; suspected sandbox filesystem layer. See
    setup/PITFALLS.md §B11.

    Losing the evidence file in Phase 4 is the worst possible moment to lose it:
    the probes already ran, the servers are gone, and re-running costs minutes to
    hours. So every kit tool that produces evidence writes it through here.

BEHAVIOUR
    1. Try the requested path (creating parents).
    2. On OSError, retry a fallback next to this module
       (`<kit>/workspace-fallback/<name>`), print a diagnosis to stderr, and
       return the path actually used.
    3. Never raise for a write failure — return None and say so loudly.

USAGE
    from evidence import write_evidence
    path = write_evidence("research/probe.json", payload)      # dict/list -> JSON
    path = write_evidence("research/probe.md", markdown_text)  # str -> text
    print(f"evidence: {path}")
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

FALLBACK_DIR = Path(__file__).resolve().parents[1] / "workspace-fallback"


def _dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, (dict, list)):
        path.write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=str),
                        encoding="utf-8")
    elif isinstance(payload, (bytes, bytearray)):
        path.write_bytes(bytes(payload))
    else:
        path.write_text(str(payload), encoding="utf-8")


def write_evidence(dest: str | Path, payload: Any, *, retries: int = 2,
                   quiet: bool = False) -> Path | None:
    """Write `payload` to `dest`; on OSError fall back next to the kit.

    Returns the Path actually written, or None if every attempt failed.
    """
    dest = Path(dest)
    attempts = [dest]
    if not dest.is_absolute():
        attempts.insert(0, Path.cwd() / dest)
    attempts.append(FALLBACK_DIR / dest.name)

    last_err: Exception | None = None
    for target in attempts[: 1 + retries + 1]:
        try:
            _dump(target, payload)
            if target != dest and not quiet:
                print(f"[evidence] NOTE: wrote to fallback {target} "
                      f"(requested {dest}): {last_err}", file=sys.stderr)
            elif not quiet and target != attempts[0]:
                pass
            return target
        except OSError as e:
            last_err = e
            time.sleep(0.2)

    print(f"[evidence] FAILED to write {dest} after {len(attempts)} attempts: {last_err}\n"
          f"[evidence] payload summary: {type(payload).__name__}, "
          f"{len(payload) if hasattr(payload, '__len__') else '?'} items.\n"
          f"[evidence] Do NOT let this be the only copy — re-run the probe, or paste "
          f"the payload into the log by hand.", file=sys.stderr)
    return None


def diagnose(dest: str | Path) -> str:
    """A printable description of why `dest` may be unwritable (for probe logs)."""
    d = Path(dest)
    parts = [f"dest={d}", f"abs={d.is_absolute()}", f"cwd={os.getcwd()}"]
    par = d.parent
    parts.append(f"parent={par}")
    parts.append(f"parent.is_dir={par.is_dir()}")
    parts.append(f"parent.exists={par.exists()}")
    try:
        parts.append(f"parent.stat.mode={oct(par.stat().st_mode)}")
    except OSError as e:
        parts.append(f"parent.stat=ERR:{e}")
    parts.append(f"writable={os.access(par, os.W_OK)}")
    return " ".join(parts)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Self-test for write_evidence.")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        import tempfile
        ok = True
        with tempfile.TemporaryDirectory() as td:
            p = write_evidence(Path(td) / "sub" / "a.json", {"x": 1}, quiet=True)
            ok &= p is not None and json.loads(p.read_text()) == {"x": 1}
            print(f"  [{'ok ' if ok else 'FAIL'}] nested JSON write")
            p2 = write_evidence(Path(td) / "b.md", "# hi\n", quiet=True)
            ok &= p2 is not None and p2.read_text() == "# hi\n"
            print(f"  [{'ok ' if p2 else 'FAIL'}] text write")
        # an unwritable destination must fall back, not raise
        p3 = write_evidence("/proc/definitely-not-writable/x.json", {"y": 2}, quiet=True)
        ok &= p3 is not None and p3.parent == FALLBACK_DIR
        print(f"  [{'ok ' if p3 and p3.parent == FALLBACK_DIR else 'FAIL'}] fallback on unwritable dest")
        if p3:
            p3.unlink(missing_ok=True)
        print("SELF-TEST PASSED" if ok else "SELF-TEST FAILED")
        raise SystemExit(0 if ok else 1)
    ap.print_help()
