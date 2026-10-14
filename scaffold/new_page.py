#!/usr/bin/env python3
"""
new_page.py — scaffold a wiki page (or a whole wiki skeleton) that already
satisfies every structural rule qa_wiki.py enforces.

    # one page
    python3 scaffold/new_page.py wiki/OWNER.REPO.wiki "Security Hardening Guide"

    # the whole skeleton: Home, _Sidebar, _Footer + one stub per planned page
    python3 scaffold/new_page.py wiki/OWNER.REPO.wiki --init \
        --pages "Home,Getting Started,Installation and Deployment,Configuration Reference"

WHY
    Structure is free if you scaffold it; it is expensive if you retrofit it.
    Every page starts with an H1, a lead paragraph, a Contents block, and a
    "See also" section — so the QA pass is about content, not about remembering
    to add a section you forgot.

NAMING RULE (do not get this wrong)
    GitHub maps SPACES in a wiki filename to HYPHENS in the URL, and resolves
    [[Page Name]] against that. So the file must be `Security Hardening Guide.md`
    (spaces) for `[[Security Hardening Guide]]` to work. A file named
    `Security-Hardening-Guide.md` makes every such link dead.
"""
from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

PAGE_TMPL = """# {title}

{lead}

## Contents

{contents}

---

{body}

---

## See also

{seealso}
"""

HOME_TMPL = """# {project}

{badges}

{summary}

> [!IMPORTANT]
> One thing every reader must know before they deploy. Replace this with the
> single highest-stakes fact about the project — a security property, a hard
> requirement, or a limitation that changes the deployment decision.

---

## Contents

- [Key features](#key-features)
- [Quick start — five minutes](#quick-start--five-minutes)
- [How it is put together](#how-it-is-put-together)
- [Requirements](#requirements)
- [Wiki navigation](#wiki-navigation)
- [Project facts](#project-facts)

---

## Key features

- Feature one — state what it does, not that it is great.
- Feature two.

## Quick start — five minutes

```bash
# 1. get it
# 2. configure it
# 3. run it
# 4. open it
```

Every command must be copy-pasteable and must have been executed. Show the
expected output in a following block.

## How it is put together

```mermaid
flowchart LR
    A[Input] --> B[Thing]
```

## Requirements

| Requirement | Detail |
|---|---|
| Runtime | |
| Dependencies | |

## Wiki navigation

| Page | What it covers |
|---|---|
{nav}

## Project facts

| | |
|---|---|
| Repository | {repo_url} |
| Version | |
| License | |

---

## See also

{seealso}
"""

SIDEBAR_TMPL = """### Overview

**[[Home]]**
{overview}

### Install & configure

{install}

### Authoring / usage

{usage}

### Operating

{operating}

### Reference

{reference}

---

{version_line}
"""

FOOTER_TMPL = """{project} **{version}** · {license} · [Repository]({repo_url}) ·
[Report an issue]({repo_url}/issues) · {links}

Facts in this wiki are verified against the source at commit `{commit}`{changelog_ref}.
"""


def slug(title: str) -> str:
    return title.strip()


def contents_for(sections: list[str]) -> str:
    out = []
    for s in sections:
        a = re.sub(r"[^\w\s-]", "", s.lower()).strip().replace(" ", "-")
        a = re.sub(r"-{2,}", "-", a)
        out.append(f"- [{s}](#{a})")
    return "\n".join(out) if out else "- [Overview](#overview)"


def seealso_for(title: str, all_pages: list[str]) -> str:
    others = [p for p in all_pages if p != title][:5]
    return "\n".join(f"- [[{p}]]" for p in others) or "- [[Home]]"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wiki_dir")
    ap.add_argument("title", nargs="?", help="page title, e.g. 'Security Hardening Guide'")
    ap.add_argument("--init", action="store_true", help="create Home/_Sidebar/_Footer too")
    ap.add_argument("--pages", help="comma-separated page list (used with --init and for See also)")
    ap.add_argument("--project", default="Project")
    ap.add_argument("--repo-url", default="https://github.com/OWNER/REPO")
    ap.add_argument("--version", default="0.0.0")
    ap.add_argument("--license", default="MIT")
    ap.add_argument("--commit", default="HEAD")
    ap.add_argument("--sections", default="Overview,Details,Examples",
                    help="comma-separated H2 sections for a single page")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    W = Path(a.wiki_dir)
    W.mkdir(parents=True, exist_ok=True)
    pages = [p.strip() for p in (a.pages or "").split(",") if p.strip()]

    def write(name: str, content: str) -> None:
        p = W / name
        if p.exists() and not a.force:
            print(f"  exists, skipped (use --force to overwrite): {name}")
            return
        p.write_text(content, encoding="utf-8")
        print(f"  wrote {name} ({len(content.split())} words)")

    if a.init:
        all_pages = pages or ["Home", "Getting Started", "Configuration Reference",
                              "Architecture", "Troubleshooting", "FAQ", "Glossary"]
        if "Home" not in all_pages:
            all_pages = ["Home"] + all_pages
        # Never fall back to a hardcoded page name: if Home is the only page there
        # is nothing to link, and a dead [[link]] in Home is a QA error.
        _rows = [f"| [[{p}]] | |" for p in all_pages if p != "Home"]
        nav = "\n".join(_rows) if _rows else "| _(add pages, then list them here)_ | |"
        home_seealso = "\n".join(f"- [[{p}]]" for p in all_pages if p != "Home")[:400] or ""
        write("Home.md", HOME_TMPL.format(
            project=a.project, repo_url=a.repo_url, nav=nav, seealso=home_seealso,
            badges="![License](https://img.shields.io/badge/License-{lic}-blue.svg)".format(lic=a.license),
            summary="**One or two paragraphs: what the software is and what problem it solves.**\n"
                    "Facts only. No marketing adjectives — qa_wiki.py rejects them."))
        groups = {"overview": [], "install": [], "usage": [], "operating": [], "reference": []}
        for p in all_pages:
            low = p.lower()
            if p == "Home":
                continue
            if any(k in low for k in ("install", "deploy", "configur", "settings")):
                groups["install"].append(p)
            elif any(k in low for k in ("guide", "author", "usage", "example", "browser", "matrix")):
                groups["usage"].append(p)
            elif any(k in low for k in ("security", "update", "api", "performance", "upload", "operat")):
                groups["operating"].append(p)
            elif any(k in low for k in ("start", "feature", "compar", "overview")):
                groups["overview"].append(p)
            else:
                groups["reference"].append(p)
        write("_Sidebar.md", SIDEBAR_TMPL.format(
            **{k: "\n".join(f"[[{x}]]" for x in v) or "_(none yet)_" for k, v in groups.items()},
            version_line=f"`{a.version}` · {a.license}"))
        # Only reference pages that will actually exist — qa_wiki.py treats a
        # dead link in _Footer.md as an error, and it renders on every page.
        # NEVER hardcode a page name here: _Footer.md renders on every page and
        # qa_wiki.py treats a dead link in it as an error. Derive the links from
        # the page list that is actually being created.
        present = set(all_pages)
        links = " · ".join(f"[[{p}]]" for p in ("Home", "Glossary", "FAQ", "Troubleshooting")
                           if p in present) or "[[Home]]"
        cref = ""
        for cand in ("Changelog and Versioning", "Changelog", "Versioning"):
            if cand in present:
                cref = f"; see [[{cand}]]"
                break
        write("_Footer.md", FOOTER_TMPL.format(project=a.project, version=a.version,
                                               license=a.license, repo_url=a.repo_url,
                                               commit=a.commit, changelog_ref=cref, links=links))
        for p in all_pages:
            if p == "Home":
                continue
            secs = ["Overview", "Details", "Examples"]
            write(f"{slug(p)}.md", PAGE_TMPL.format(
                title=p,
                lead="One or two sentences: what this page covers and when a reader needs it.",
                contents=contents_for(secs + ["See also"]),
                body="\n\n".join(f"## {s}\n\nTODO" for s in secs),
                seealso=seealso_for(p, all_pages)))
        print(f"\nScaffolded {len(all_pages) + 2} files in {W}")
        print("Next: fill the TODOs, then run  python3 qa/qa_wiki.py " + str(W))
        return 0

    if not a.title:
        ap.error("give a page title, or use --init")
    secs = [s.strip() for s in a.sections.split(",") if s.strip()]
    all_pages = pages or [a.title]
    write(f"{slug(a.title)}.md", PAGE_TMPL.format(
        title=a.title,
        lead="One or two sentences: what this page covers and when a reader needs it.",
        contents=contents_for(secs + ["See also"]),
        body="\n\n".join(f"## {s}\n\nTODO" for s in secs),
        seealso=seealso_for(a.title, all_pages)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
