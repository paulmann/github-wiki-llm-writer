#!/usr/bin/env python3
"""
fix_toc.py — regenerate the "## Contents" block of wiki pages from their actual
headings, using GitHub's exact slug algorithm (imported from qa_wiki.py).

WHY THIS EXISTS
    AGENTS.md/PITFALLS C5 say "never hand-write anchors — the checker computes
    them". But the checker only VERIFIES; after a page is rewritten with new
    headings, the scaffolded Contents block is stale and every TOC anchor fails
    QA. In the MD.Scribe run this tool removed that whole class of errors.

THE BUG THIS VERSION GUARDS AGAINST (it happened for real)
    The first implementation replaced everything between "## Contents" and the
    next "---"/"## " — on a page without a "---" separator it ATE the lead
    paragraph, badges and an alert block between the TOC and the first H2.
    The page had to be rebuilt from memory. Therefore this version:
      * replaces ONLY the TOC list block (heading + contiguous list lines),
      * verifies word-count sanity after every edit (aborts the file on loss),
      * supports --bak (write "<file>.bak" before touching a page),
      * ships a --self-test with a fixture reproducing the original accident.

USAGE
    python3 qa/fix_toc.py <wiki-dir> [--bak] [--self-test] [--dry-run]

INTEGRATION SUGGESTION
    Ship as qa/fix_toc.py, or fold into the auditor as `qa_wiki.py --fix-toc`.
    Either way, add to AGENTS.md Phase 3: "after filling a page, run fix_toc —
    do not hand-write the Contents block".
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    from qa_wiki import github_slug, mask_code   # when shipped inside qa/
except ImportError:                             # standalone fallback: inline slugger
    # NOTE: this file is deliberately FREE of literal triple-backtick sequences
    # (the fence is built as chr(96)*3). Reason: documentation aggregators that
    # embed sources into Markdown with naive triple-backtick fences truncate any
    # file that contains a literal fence — happened for real in the 2026-10-14 test
    # run (2,356 of 6,999 bytes survived). See DEVELOPER-REPORT.md §A11.
    _FENCE3 = chr(96) * 3

    def github_slug(heading: str) -> str:
        t = re.sub(r"<[^>]*>", "", heading.strip())
        t = re.sub(r"`|\*\*|\*|~~|==|\[|\]|\(|\)", "", t)
        t = t.replace("&amp;", "&").replace("&#8617;", "\u21a9")
        t = t.lower()
        return "".join(c for c in t if c.isalnum() or c in " -_").replace(" ", "-")

    def mask_code(text: str, _keep: bool = False) -> list[str]:
        out, in_fence = [], False
        for line in text.splitlines():
            if line.lstrip().startswith(_FENCE3):
                in_fence = not in_fence
                out.append("")
                continue
            out.append("" if in_fence else line)
        return out


TOC_LIST_RE = re.compile(
    r"(?P<head>## Contents\n\n)(?P<list>(?:[ \t]*(?:-|\*|\d+\.)[^\n]*\n)+)"
)


def headings_with_slugs(text: str) -> list[tuple[int, str, str]]:
    """H2/H3 headings of the masked text, with GitHub slugs and -1/-2 dedupe."""
    body = "\n".join(mask_code(text, False))
    seen: Counter = Counter()
    out = []
    for m in re.finditer(r"^(#{2,3})\s+(.*)$", body, re.M):
        raw = m.group(2).strip()
        slug = github_slug(raw)
        if slug in seen:
            seen[slug] += 1
            slug = f"{slug}-{seen[slug]}"
        else:
            seen[slug] = 0
        out.append((len(m.group(1)), raw, slug))
    return out


def build_toc(text: str) -> str:
    lines = []
    for level, raw, slug in headings_with_slugs(text):
        if slug == "contents":
            continue
        indent = "  " if level == 3 else ""
        lines.append(f"{indent}- [{raw.replace('`', '')}](#{slug})")
    return "\n".join(lines) + "\n"


def fix_page(path: Path, bak: bool = False, dry: bool = False) -> str:
    """Returns 'changed' | 'same' | 'skipped:<reason>'."""
    text = path.read_text()
    if "## Contents" not in text:
        return "skipped:no-contents-block"          # never guess an insertion point
    toc = build_toc(text)

    def repl(m: re.Match) -> str:
        return m.group("head") + toc

    new, n = TOC_LIST_RE.subn(repl, text, count=1)
    if n == 0:
        return "skipped:contents-block-not-in-list-shape"
    # sanity: a TOC edit may only change the list block — word count must not collapse
    if len(new.split()) < len(text.split()) - len(toc.split()) - 8:
        return "skipped:SAFETY-word-count-collapsed"
    if new == text:
        return "same"
    if not dry:
        if bak:
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        path.write_text(new)
    return "changed"


SELF_TEST_FIXTURE = """# Accident Page

Lead paragraph that must survive any TOC edit — it is long enough to matter.

![badge](https://img.shields.io/badge/x-y-blue)

> [!NOTE]
> An alert block between the TOC and the first section. It must survive too.

## Contents

- [Stale entry](#stale-entry)

## Real section one

Text.

### Sub section

More text.

## Real section two

Tail.

## See also

- [[Home]]
"""


def self_test() -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "Accident Page.md"
        p.write_text(SELF_TEST_FIXTURE)
        status = fix_page(p)
        out = p.read_text()
        checks = {
            "status changed": status == "changed",
            "lead survived": "Lead paragraph that must survive" in out,
            "badge survived": "![badge](" in out,
            "alert survived": "> [!NOTE]" in out and "must survive too" in out,
            "stale entry gone": "Stale entry" not in out,
            "new anchors present": "(#real-section-one)" in out and "  - [Sub section](#sub-section)" in out,
            "see also kept": "[[Home]]" in out,
        }
        # idempotence: second run changes nothing
        checks["idempotent"] = fix_page(p) == "same"
        bad = [k for k, v in checks.items() if not v]
        for k, v in checks.items():
            print(f"  [{'ok ' if v else 'FAIL'}] {k}")
        if bad:
            print(f"SELF-TEST FAILED: {bad}")
            return 1
        print("SELF-TEST PASSED — the fixer cannot eat surrounding prose.")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("wiki_dir", nargs="?", help="directory of *.md wiki pages")
    ap.add_argument("--bak", action="store_true", help="write <file>.bak before editing")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not a.wiki_dir:
        ap.error("wiki_dir required (or use --self-test)")
    changed = 0
    for p in sorted(Path(a.wiki_dir).glob("*.md")):
        if p.name.startswith("_"):
            continue
        st = fix_page(p, bak=a.bak, dry=a.dry_run)
        if st.startswith("skipped"):
            print(f"  {p.name}: {st}")
        elif st == "changed":
            changed += 1
            print(f"  toc fixed: {p.name}")
    print(f"{changed} page(s) {'would be ' if a.dry_run else ''}updated in {a.wiki_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
