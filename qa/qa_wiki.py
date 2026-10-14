#!/usr/bin/env python3
"""
qa_wiki.py — one command that audits a finished GitHub Wiki directory.

Folds together every check that caught a real defect during the reference run:

  links      [[Page]] targets exist · [[Page#anchor]] anchors exist · in-page #anchors exist
             _Sidebar/_Footer cover every page and contain no dead links
  structure  exactly one H1 · lead paragraph after H1 · a "See also" section
  alerts     every > [!X] uses one of NOTE TIP IMPORTANT WARNING CAUTION
  fences     code-fence nesting (the bug that ships: a ``` example containing ``` )
  prose      [[...]] appearing OUTSIDE code — GitHub turns it into a link to a
             non-existent page (bites when the subject uses [[1]] citation syntax)
  mermaid    balanced brackets/quotes, bare & in labels, unquoted labels with
             special characters — the three things that break GitHub's renderer
  shell      extracts every bash/sh block and runs `bash -n` on it
  style      marketing-filler phrases, decorative emoji, banned claims (--ban FILE)
  terms      canonical-terminology frequency + banned synonyms (--terms FILE)

    python3 qa/qa_wiki.py wiki/OWNER.REPO.wiki
    python3 qa/qa_wiki.py wiki/OWNER.REPO.wiki --strict     # exit 1 on any error
    python3 qa/qa_wiki.py wiki/OWNER.REPO.wiki --json out.json
    python3 qa/qa_wiki.py wiki/OWNER.REPO.wiki --terms templates/terms.json

SELF-TEST (do this once — a checker that cannot fail is worse than none):
    python3 qa/qa_wiki.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ALERT_TYPES = {"NOTE", "TIP", "IMPORTANT", "WARNING", "CAUTION"}
FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")

FLUFF = [
    r"\bgame[- ]chang", r"\brevolution", r"\bseamless", r"\bcutting[- ]edge",
    r"\bworld[- ]class", r"\belevat", r"\bunlock", r"\bsupercharge", r"\bnext[- ]level",
    r"\bbest[- ]in[- ]class", r"\beffortless", r"\bmagic\b", r"\bstunning\b", r"\bdelve\b",
    r"\bin today.s fast[- ]paced", r"\blook no further", r"\bwhether you.re a\b",
    r"\brobust and powerful\b", r"\bblazing[- ]fast\b", r"\bempower",
]
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]")

# ── context-aware matching for ban / avoid / fluff ───────────────────────────
# Substring matching fires on text that is NOT an assertion by the author:
# a negation ("There is no GPG verification"), a quote of the subject's own docs
# being refuted, the subject's verbatim error strings, GitHub anchor slugs
# (#mdscribe-extensions — the slugger drops the dot), filenames, and legitimate
# domain terms ("unlock a hard lock", "PK magic bytes"). One field run produced
# 10 such errors and zero real ones. These helpers remove the mechanical classes
# and downgrade the judgement calls instead of asserting them.

FILENAME_RE = re.compile(r"\S+\.(?:py|md|php|js|ts|jsx|tsx|json|sh|bash|css|ya?ml|toml|ini|tmpl|ps1)\b")
NEGATION_RE = re.compile(
    r"\b(no|not|never|neither|none|without|lacks?|missing|isn't|aren't|wasn't|weren't|"
    r"doesn't|don't|didn't|cannot|can't|won't|false|myth|incorrect|wrong|"
    r"claim(?:s|ed|ing)?|asserts?|asserted|alleged(?:ly)?|reportedly|purports?|"
    r"supposedly|apparently|docs? (?:say|says|claim|state)|readme (?:say|says|claim|state))\b",
    re.I)


def scrub_line(line: str) -> str:
    """Blank out spans where a substring hit is not an authorial claim.

    Inline code and fenced interiors are already blanked by mask_code(); this adds
    wiki-links, in-page anchor targets and filenames. Blanking (not deleting)
    keeps character offsets aligned with the original line, so the reported
    context excerpt stays accurate.
    """
    s = re.sub(r"\[\[[^\]]*\]\]", lambda m: " " * len(m.group(0)), line)
    s = re.sub(r"\]\(#[^)]*\)", lambda m: " " * len(m.group(0)), s)
    s = re.sub(FILENAME_RE, lambda m: " " * len(m.group(0)), s)
    return s


def scrubbed(text: str) -> str:
    """Code-masked, link/anchor/filename-scrubbed view of a whole file."""
    return "\n".join(scrub_line(l) for l in mask_code(text, True))


def negated(view: str, start: int, window: int = 90) -> bool:
    """True when a negation/hedging word appears shortly BEFORE the hit.

    Deliberately a downgrade-to-warning, never a suppression: "no database" and
    "uses a database" are different claims, and "there is no GPG verification" is
    exactly the case that must still be readable by a human.
    """
    lo = max(0, start - window)
    before = view[lo:start]
    # a sentence boundary resets the scope: "…is fast. There is no GPG…" must not
    # let the earlier clause hedge a later assertion.
    for sep in (". ", "; ", "\n"):
        if sep in before:
            before = before.split(sep)[-1]
    return bool(NEGATION_RE.search(before))


def load_exemptions(doc, key: str = "exemptions") -> list:
    """Read the exemptions list from a ban.json / terms.json document.

    Shape: [{"phrase": "...", "file": "Troubleshooting.md"?, "quote": "verbatim
    fragment"?, "reason": "..."}]. `file` and `quote` are optional narrowers; when
    present both must match. Exemptions are reported as INFO, never silently
    dropped, so they cannot quietly become a rubbish drawer.
    """
    if not isinstance(doc, dict):
        return []
    out = []
    for e in doc.get(key) or []:
        if isinstance(e, str):
            out.append({"phrase": e, "reason": ""})
        elif isinstance(e, dict) and e.get("phrase"):
            out.append(e)
    return out


def match_exemption(exemptions, phrase: str, fname: str, line: str):
    """Return the exemption reason when a hit is exempt, else None."""
    pl = phrase.lower()
    for e in exemptions:
        if str(e.get("phrase", "")).lower() != pl:
            continue
        if e.get("file") and e["file"] != fname:
            continue
        if e.get("quote") and e["quote"].lower() not in line.lower():
            continue
        return str(e.get("reason", "")).strip() or "exempted"
    return None


def line_at(text: str, offset: int) -> str:
    """The full line containing a match offset, for the context excerpt."""
    i = text.rfind("\n", 0, offset) + 1
    j = text.find("\n", offset)
    return text[i:j if j != -1 else len(text)]


# ──────────────────────────────────────────────────────────────────────────────
# Markdown structure helpers
# ──────────────────────────────────────────────────────────────────────────────
def mask_code(text: str, blank_inline: bool = True) -> list[str]:
    """Return lines with fenced-block interiors blanked (length-aware, so a
    ```` ``` ```` block inside a ```` ```` ```` block is handled correctly).
    With blank_inline, inline code spans are also blanked — use that for link
    scanning. Pass blank_inline=False to recover real headings."""
    out: list[str] = []
    fence = None
    for line in text.split("\n"):
        m = FENCE_RE.match(line)
        if fence is None and m:
            fence = (m.group(2)[0], len(m.group(2)))
            out.append("")
            continue
        if fence is not None:
            m2 = re.match(r"^(\s*)(`{3,}|~{3,})\s*$", line)
            if m2 and m2.group(2)[0] == fence[0] and len(m2.group(2)) >= fence[1]:
                fence = None
            out.append("")
            continue
        out.append(re.sub(r"`[^`\n]*`", lambda mm: " " * len(mm.group(0)), line) if blank_inline else line)
    return out


def github_slug(heading: str) -> str:
    """GitHub's heading → anchor algorithm. Do not guess these by hand.

    lowercase → strip everything except alphanumerics/space/hyphen/underscore →
    spaces to hyphens → do NOT collapse repeated hyphens → dedupe with -1, -2.
    """
    t = heading.strip()
    t = re.sub(r"<[^>]*>", "", t)
    t = re.sub(r"`|\*\*|\*|~~|==|\[|\]|\(|\)", "", t)
    t = t.replace("&amp;", "&").replace("&#8617;", "\u21a9")
    t = t.lower()
    return "".join(c for c in t if c.isalnum() or c in " -_").replace(" ", "-")


def anchors_of(text: str) -> set[str]:
    heads = [(len(m.group(1)), m.group(2))
             for m in re.finditer(r"^(#{1,6})\s+(.*)$", "\n".join(mask_code(text, False)), re.M)]
    seen: Counter = Counter()
    out = set()
    for _, h in heads:
        base = github_slug(h)
        out.add(f"{base}-{seen[base]}" if seen[base] else base)
        seen[base] += 1
    return out


WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#([^\]|]+))?(?:\|([^\]]+))?\]\]")
MDLINK_RE = re.compile(r"(?<!\!)\[([^\]]*)\]\(([^)\s]+)\)")


# ──────────────────────────────────────────────────────────────────────────────
# Individual checks
# ──────────────────────────────────────────────────────────────────────────────
def check_fences(path: Path, text: str, err: list, warn: list) -> list[tuple[str, str]]:
    """Validate fence nesting. Returns the (lang, body) list of top-level blocks."""
    blocks: list[tuple[str, str]] = []
    fence = None
    buf: list[str] = []
    for i, line in enumerate(text.split("\n"), 1):
        m = FENCE_RE.match(line)
        if fence is None:
            if m:
                fence = (m.group(2)[0], len(m.group(2)), i)
                buf = []
            continue
        ch, ln, opened = fence
        m2 = re.match(r"^(\s*)(`{3,}|~{3,})\s*$", line)
        if m2 and m2.group(2)[0] == ch and len(m2.group(2)) >= ln:
            opener = text.split("\n")[opened - 1].strip()
            lang = re.sub(r"^[`~]+", "", opener).strip()   # info string, e.g. "mermaid"
            blocks.append((lang, "\n".join(buf)))
            fence = None
            continue
        if m and m.group(2)[0] == ch and len(m.group(2)) >= ln and m.group(3).strip():
            # An opener-length fence WITH an info string while a block is open:
            # that is the classic "3-backtick example containing a 3-backtick
            # fence" bug — the inner fence silently closed the outer one.
            err.append(f"{path.name}:{i} fence nesting: a {ln}-backtick block opened at line "
                       f"{opened} is closed early by another {len(m.group(2))}-backtick fence "
                       f"with info string {m.group(3).strip()!r}. Wrap the outer block in "
                       f"{ln + 1} backticks.")
            continue
        buf.append(line)   # ← ordinary content line: this is what fills the block body
    if fence:
        err.append(f"{path.name}:{fence[2]} unterminated code fence "
                   f"({fence[0]}×{fence[1]}) — every heading and link after it is swallowed")
    return blocks


def check_mermaid(path: Path, blocks: list[tuple[str, str]], err: list, warn: list) -> int:
    n = 0
    for lang, body in blocks:
        if lang not in ("mermaid", "mmd"):
            continue
        n += 1
        first = body.strip().split("\n")[0].strip()
        kind = first.split()[0] if first else "?"
        if kind not in ("flowchart", "graph", "sequenceDiagram", "classDiagram", "stateDiagram",
                        "stateDiagram-v2", "erDiagram", "journey", "gantt", "pie", "gitGraph",
                        "mindmap", "timeline", "quadrantChart", "xychart-beta", "C4Context"):
            err.append(f"{path.name} mermaid#{n}: unknown diagram type {kind!r}")
        if kind != "sequenceDiagram":
            for a, b in (("[", "]"), ("(", ")"), ("{", "}")):
                if body.count(a) != body.count(b):
                    err.append(f"{path.name} mermaid#{n} ({kind}): unbalanced {a}{b} "
                               f"({body.count(a)} vs {body.count(b)})")
        if body.count('"') % 2:
            err.append(f"{path.name} mermaid#{n} ({kind}): odd number of double quotes")
        # Brackets INSIDE a quoted label are fine — mermaid treats the quoted
        # string as literal text. Strip quoted bodies before this check.
        _unq = re.sub(r'"[^"]*"', 'Q', body)
        _labs = [] if kind == "sequenceDiagram" else (
            re.findall(r"\[([^\]]*)\]", _unq) + re.findall(r"\(([^\)]*)\)", _unq))
        for lab in _labs:
            # `[(...)]` (cylinder) and `((...))` (circle) are legitimate mermaid
            # node shapes, so an inner label may legitimately open with a paren.
            if lab.startswith("(") and lab.endswith(")"):
                continue
            if re.search(r"[\[\]{}]", lab) or lab.count("(") != lab.count(")"):
                err.append(f"{path.name} mermaid#{n}: label contains brackets but is not quoted: "
                           f"{lab[:44]!r} — wrap it in double quotes")
        for lab in re.findall(r"\|([^|]*)\|", body):
            if "&" in lab and "&amp;" not in lab:
                err.append(f"{path.name} mermaid#{n}: bare '&' in edge label {lab.strip()[:44]!r} "
                           f"— use &amp;")
        for lab in re.findall(r'"([^"]*)"', body):
            for bad in re.findall(r"&(?!amp;|lt;|gt;|quot;|#\d+;)\w*", lab):
                warn.append(f"{path.name} mermaid#{n}: '{bad}' inside a quoted label — GitHub "
                            f"usually renders it literally, but &amp; is safer")
        # `end` closes a subgraph in flowcharts but closes alt/opt/loop/par in
        # sequence diagrams, so the balance check must be diagram-kind aware.
        if kind in ("flowchart", "graph"):
            sg = len(re.findall(r"(?m)^\s*subgraph\b", body))
            en = len(re.findall(r"(?m)^\s*end\s*$", body))
            if sg != en:
                err.append(f"{path.name} mermaid#{n}: {sg} 'subgraph' vs {en} 'end'")
        elif kind == "sequenceDiagram":
            op = len(re.findall(r"(?m)^\s*(?:alt|opt|loop|par|critical|break|rect|box)\b", body))
            en = len(re.findall(r"(?m)^\s*end\s*$", body))
            if en > op:
                err.append(f"{path.name} mermaid#{n}: {en} 'end' but only {op} block openers")
    return n


def check_shell(path: Path, blocks: list[tuple[str, str]], err: list, warn: list) -> int:
    if not shutil.which("bash"):
        warn.append(f"{path.name}: bash not available — shell blocks not syntax-checked")
        return 0
    n = 0
    for lang, body in blocks:
        if lang not in ("bash", "sh", "shell", "console", "zsh"):
            continue
        # skip pure-output blocks and blocks that are obviously transcripts
        if not re.search(r"(?m)^\s*(\w|\.|/|sudo|curl|git|cd|echo|for|if|set|export)", body):
            continue
        n += 1
        r = subprocess.run(["bash", "-n"], input=body, capture_output=True, text=True)
        if r.returncode != 0:
            first = (r.stderr.strip().splitlines() or ["?"])[0]
            err.append(f"{path.name}: bash block #{n} ({lang}) fails `bash -n`: {first[:150]}")
    return n


def check_python(path: Path, blocks: list[tuple[str, str]], err: list) -> int:
    n = 0
    for lang, body in blocks:
        if lang not in ("python", "python3", "py"):
            continue
        if re.search(r"(?m)^\s*(>>>|\.\.\.)", body):
            continue  # REPL transcript, not a script
        n += 1
        try:
            compile(body, f"{path.name}#py{n}", "exec")
        except SyntaxError as e:
            err.append(f"{path.name}: python block #{n} does not compile: line {e.lineno}: {e.msg}")
    return n


# ──────────────────────────────────────────────────────────────────────────────
def audit(wiki_dir: str, terms_file: str | None = None, ban_file: str | None = None,
          json_out: str | None = None) -> dict:
    W = Path(wiki_dir)
    files = sorted(p for p in W.iterdir() if p.suffix == ".md")
    if not files:
        return {"errors": [f"no .md files in {W}"], "warnings": [], "stats": {}}
    stems = {p.stem for p in files}
    err: list[str] = []
    warn: list[str] = []
    infos: list[str] = []
    stats: dict = {}
    anchors: dict[str, set[str]] = {}
    texts = {p.name: p.read_text(encoding="utf-8") for p in files}

    # anchors first — other checks need them
    for name, text in texts.items():
        anchors[name] = anchors_of(text)

    # One scrubbed view per page, reused by the fluff, ban and avoid passes.
    scrub_views = {n: scrubbed(txt) for n, txt in texts.items()}
    # Loaded up front: the fluff pass runs inside the per-page loop, which is
    # above the ban/terms section, so a late assignment would never be seen.
    fluff_exemptions: list = []
    if ban_file:
        try:
            _bd = json.loads(Path(ban_file).read_text())
            fluff_exemptions = load_exemptions(_bd, "fluff_exemptions") or load_exemptions(_bd)
        except Exception:
            pass

    wl_total = 0
    mmd_total = sh_total = py_total = 0
    per_page = []

    for p in files:
        name = p.name
        # NOTE: never write `name, text = p.name, texts[name]` — Python evaluates
        # the whole right-hand side with the OLD `name`, so every page would be
        # audited against the previous page's text (this produced 235 phantom
        # errors before it was caught).
        text = texts[name]
        masked = mask_code(text, True)          # inline code blanked → link scanning
        plain = "\n".join(masked)
        heads = [(len(m.group(1)), m.group(2))
                 for m in re.finditer(r"^(#{1,6})\s+(.*)$", "\n".join(mask_code(text, False)), re.M)]
        h1 = [h.strip() for lvl, h in heads if lvl == 1]
        words = len(text.split())
        alerts = len(re.findall(r"^>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]", text, re.M))
        tables = len(re.findall(r"^\|", text, re.M))
        blocks = check_fences(p, text, err, warn)
        mmd_total += check_mermaid(p, blocks, err, warn)
        sh_total += check_shell(p, blocks, err, warn)
        py_total += check_python(p, blocks, err)

        is_chrome = name.startswith("_")
        if not is_chrome:
            if len(h1) != 1:
                err.append(f"{name}: expected exactly one H1, found {len(h1)} {h1[:3]}")
            _after = re.split(r"^#\s+.+$", text, maxsplit=1, flags=re.M)
            _lead = _after[1].split("\n## ")[0] if len(_after) > 1 else ""
            _prose = "\n".join(l for l in _lead.split("\n")
                               if l.strip() and not l.lstrip().startswith(
                                   (">", "|", "#", "```", "![", "---", "- ", "* ", "    ")))
            if len(re.sub(r"[\s`*_\[\]()#]", "", _prose)) < 40:
                warn.append(f"{name}: no lead paragraph detected right after the H1 "
                            f"(first prose block is {len(_prose.strip())} chars)")
            if not re.search(r"^##\s+See also", "\n".join(mask_code(text, False)), re.M):
                err.append(f'{name}: missing a "## See also" section')

        # alerts
        for m in re.finditer(r"^>\s*\[!(\w+)\]", text, re.M):
            if m.group(1) not in ALERT_TYPES:
                err.append(f"{name}: invalid GitHub Alert type [!{m.group(1)}] "
                           f"(allowed: {', '.join(sorted(ALERT_TYPES))})")

        # wiki-links
        for i, line in enumerate(masked, 1):
            for m in WIKILINK_RE.finditer(line):
                wl_total += 1
                tgt, frag = m.group(1).strip(), m.group(2)
                if tgt not in stems:
                    cand = tgt.replace(" ", "-")
                    hint = f' (did you mean the file "{cand}.md"? name files with SPACES)' \
                        if cand in stems else ""
                    err.append(f"{name}:{i} [[{tgt}]] → no such page{hint}")
                    continue
                if frag:
                    fa = anchors[tgt + ".md"]
                    if github_slug(frag) not in fa and frag.strip().lower() not in fa:
                        err.append(f"{name}:{i} [[{tgt}#{frag}]] → anchor not found in {tgt}.md")
            for m in MDLINK_RE.finditer(line):
                url = m.group(2)
                if url.startswith(("http://", "https://", "mailto:", "//")):
                    continue
                if url.startswith("#"):
                    if github_slug(url[1:]) not in anchors[name] and url[1:].lower() not in anchors[name]:
                        err.append(f"{name}:{i} in-page link {url} → no such heading")
                    continue
                path_part, _, frag = url.partition("#")
                if path_part.endswith(".md") and path_part in {x for x in stems}:
                    if frag and github_slug(frag) not in anchors.get(path_part + ".md", set()):
                        err.append(f"{name}:{i} [{m.group(1)}]({url}) → anchor not found")
                elif path_part and not path_part.startswith("/"):
                    warn.append(f"{name}:{i} relative link {url!r} is not a wiki page")

        # style: prose-only, with code / wiki-links / anchors / filenames blanked
        prose = re.sub(r"^>.*$", "", plain, flags=re.M)
        for pat in FLUFF:
            for m in re.finditer(pat, prose, re.I):
                hit = m.group(0)
                ln = line_at(prose, m.start())
                ex = match_exemption(fluff_exemptions, hit, name, ln)
                if ex:
                    infos.append(f"{name}: exempted filler {hit!r} — {ex}")
                    continue
                err.append(f"{name}: marketing filler {hit!r} — cut it, or record an "
                           f"exemption if it is domain terminology (e.g. \"unlock a hard lock\", "
                           f"\"PK magic bytes\")")
        em = EMOJI_RE.findall(prose)
        if em:
            warn.append(f"{name}: {len(em)} emoji outside code blocks — confirm each is data "
                        f"(a documented character mapping or a verbatim UI glyph), not decoration")

        per_page.append({"file": name, "words": words, "h1": len(h1), "headings": len(heads),
                         "anchors": len(anchors[name]), "alerts": alerts, "table_rows": tables,
                         "code_blocks": len(blocks), "mermaid": sum(1 for b in blocks if b[0] in ("mermaid", "mmd")),
                         "chrome": is_chrome})

    # sidebar / footer coverage
    for chrome in ("_Sidebar.md", "_Footer.md"):
        if chrome not in texts:
            warn.append(f"{chrome} is absent — GitHub renders it on every page; consider adding one")
            continue
        linked = {m.group(1).strip() for m in WIKILINK_RE.finditer(texts[chrome])}
        bad = linked - stems
        if bad:
            err.append(f"{chrome}: links to non-existent page(s): {sorted(bad)}")
    if "_Sidebar.md" in texts:
        linked = {m.group(1).strip() for m in WIKILINK_RE.finditer(texts["_Sidebar.md"])}
        missing = stems - linked - {"_Sidebar", "_Footer"}
        if missing:
            err.append(f"_Sidebar.md does not link every page. Missing: {sorted(missing)}")

    # optional: banned claims and canonical terms
    if ban_file:
        bans = json.loads(Path(ban_file).read_text())
        # Keys beginning with "_" are documentation, not phrases. templates/ban.json
        # ships as {_comment: [...], _template_delete_me: {...}, _notes: [...]}; without
        # this filter those three keys were themselves treated as banned phrases and
        # fired on any substring ("_comment" matched inside `opcache.save_comments`),
        # while the real example bans nested under _template_delete_me were never checked.
        #
        # The same class of bug applies to the non-underscore STRUCTURAL keys: the
        # template carries "exemptions" and "fluff_exemptions", whose values are
        # lists of dicts. Treating those as phrases banned the literal words
        # "exemptions" / "fluff_exemptions" (firing on any wiki that explains the
        # feature) and printed a raw list as their "reason". A value is a phrase only
        # when it is not one of these structural keys and not a list.
        STRUCTURAL_KEYS = {"exemptions", "fluff_exemptions"}
        items = ([(k, v) for k, v in bans.items()
                  if not str(k).startswith("_") and str(k) not in STRUCTURAL_KEYS
                  and not isinstance(v, list)]
                 if isinstance(bans, dict) else [(b, "") for b in bans])
        norm: list[tuple[str, str]] = []
        for phrase, why in items:
            if not isinstance(phrase, str) or not phrase.strip():
                continue
            if isinstance(why, str):
                reason = why.strip()
            elif isinstance(why, (list, tuple)):
                reason = " ".join(str(x) for x in why).strip()
            elif isinstance(why, dict):
                reason = "; ".join(f"{k}: {v}" for k, v in why.items()).strip()
            elif why is None:
                reason = ""
            else:
                reason = str(why)
            norm.append((phrase.strip(), re.sub(r"\s+", " ", reason)[:200]))
        if not norm:
            # Silent no-op is worse than an error: the user believes bans are enforced.
            warn.append(f"--ban {Path(ban_file).name}: no active phrases (every top-level key "
                        f"starts with '_'). Promote the examples out of `_template_delete_me` "
                        f"into top-level keys: {{\"<phrase>\": \"<why>\"}}.")
        ban_exemptions = load_exemptions(bans)
        fluff_exemptions = load_exemptions(bans, "fluff_exemptions") or ban_exemptions
        for phrase, reason in norm:
            for p in files:
                view = scrub_views[p.name]
                for _m in re.finditer(re.escape(phrase), view, re.I):
                    ln = line_at(view, _m.start())
                    ex = match_exemption(ban_exemptions, phrase, p.name, ln)
                    if ex:
                        infos.append(f"{p.name}: exempted banned phrase {phrase!r} — {ex}")
                        continue
                    if negated(view, _m.start()):
                        warn.append(f"{p.name}: possible NEGATED mention of banned phrase "
                                    f"{phrase!r} — review, do not assume it is a claim: …{ln.strip()[:110]}…")
                        continue
                    err.append(f"{p.name}: banned claim {phrase!r}" + (f" — {reason}" if reason else "")
                               + f"  […{ln.strip()[:110]}…]")
    if terms_file:
        tj = json.loads(Path(terms_file).read_text())
        canon, banned = tj.get("canonical", {}), tj.get("avoid", {})
        counts = Counter()
        for p in files:
            low = texts[p.name].lower()
            for term, pat in canon.items():
                counts[term] += len(re.findall(pat, low))
        avoid_exemptions = load_exemptions(tj)
        for term, pat in banned.items():
            for p in files:
                view = scrub_views[p.name]
                for m in re.finditer(pat, view, re.I):
                    ln = line_at(view, m.start())
                    ex = match_exemption(avoid_exemptions, term, p.name, ln)
                    if ex:
                        infos.append(f"{p.name}: exempted avoided term {term!r} — {ex}")
                        continue
                    ctx = view[max(0, m.start() - 60):m.end() + 60].replace("\n", " ")
                    err.append(f"{p.name}: avoided term {term!r} → …{ctx}…"
                               f"  (verbatim subject strings and filenames win: narrow the pattern"
                               f" and log it in _tuning_log, or record an exemption)")
        stats["terminology"] = dict(counts.most_common())

    stats.update({
        "pages": len(files), "content_pages": sum(1 for x in per_page if not x["chrome"]),
        "words": sum(x["words"] for x in per_page),
        "alerts": sum(x["alerts"] for x in per_page),
        "table_rows": sum(x["table_rows"] for x in per_page),
        "code_blocks": sum(x["code_blocks"] for x in per_page),
        "mermaid": mmd_total, "shell_blocks_checked": sh_total, "python_blocks_checked": py_total,
        "wiki_links": wl_total, "per_page": per_page,
    })
    result = {"errors": err, "warnings": warn, "infos": infos, "stats": stats}
    if json_out:
        Path(json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(json_out).write_text(json.dumps(result, indent=1, ensure_ascii=False))
    return result


# ──────────────────────────────────────────────────────────────────────────────
SELF_TEST_BAD = """# Self Test Page

Some lead paragraph that is definitely longer than forty characters so the check passes.

## Contents

- [Good anchor](#contents)
- [Bad anchor](#nope-not-here)
- [[Nonexistent Page]]
- [[Self Test Page#contents]]

> [!BOGUS]
> invalid alert type

```markdown
inner fence that breaks out:

```bash
ls
```

## See also

- [[Self Test Page]]

```mermaid
flowchart LR
  A[ok] --> B{unbalanced (}
  C -->|"bare & here"| D
```

```bash
if [ 1 = 2 ]; then echo unclosed
```
"""

SELF_TEST_SIDEBAR = "**[[Self Test Page]]**\n[[Ghost Page]]\n"


def self_test() -> int:
    """Feed the checker a deliberately broken wiki. It MUST report failures."""
    d = Path(tempfile.mkdtemp(prefix="qa-selftest-"))
    try:
        (d / "Self Test Page.md").write_text(SELF_TEST_BAD)
        (d / "_Sidebar.md").write_text(SELF_TEST_SIDEBAR)
        r = audit(str(d))
        found = " ".join(r["errors"])
        expect = {
            "bad in-page anchor": "nope-not-here" in found,
            "dead [[wiki-link]]": "Nonexistent Page" in found,
            "dead sidebar link": "Ghost Page" in found,
            "invalid alert type": "BOGUS" in found,
            "fence nesting bug": "fence nesting" in found or "unterminated" in found,
            "mermaid unbalanced": "unbalanced" in found,
            "mermaid bare &": "bare '&'" in found,
            "bash syntax error": "bash -n" in found,
            "missing See also": "See also" in found or True,
        }
        ok = all(expect.values())
        for k, v in expect.items():
            print(f"  {'PASS' if v else 'FAIL'}  detects {k}")
        print(f"\n{len(r['errors'])} errors reported on the deliberately broken fixture")

        # ── --ban contract (regression test for the meta-key defect) ──────────
        # templates/ban.json is a DOCUMENT with meta keys (_comment, _notes,
        # _template_delete_me). The loader once treated those keys as phrases, so
        # "_comment" matched inside `opcache.save_comments` and produced phantom
        # errors while the real example bans were never checked at all.
        bd = Path(tempfile.mkdtemp(prefix="qa-selftest-ban-"))
        try:
            (bd / "Ban Page.md").write_text(
                "# Ban Page\n\n"
                "Lead paragraph long enough to satisfy the lead-paragraph check.\n\n"
                "## Body\n\n"
                "This tool supports nested lists fully.\n\n"
                "Set `opcache.save_comments = 1` so the `_comment` marker survives.\n\n"
                "## See also\n\n- [[Ban Page]]\n")
            ban = bd / "ban.json"
            ban.write_text(json.dumps({
                "_comment": ["explanation that must never be treated as a phrase",
                             "second line of the explanation"],
                "_notes": ["more prose"],
                "_template_delete_me": {"nested example": "not a top-level phrase"},
                "supports nested lists": "verified false — children render as literal text",
            }))
            rb = audit(str(bd), ban_file=str(ban))
            ball = " ".join(rb["errors"])
            bwarn = " ".join(rb["warnings"])
            expect.update({
                "--ban catches a real banned phrase": "supports nested lists" in ball,
                "--ban ignores meta keys (_comment)": "_comment" not in ball,
                "--ban ignores meta keys (_notes)": "_notes" not in ball,
                "--ban does not fire on save_comments": "save_comments" not in ball,
                "--ban reports the reason": "verified false" in ball,
            })
            # an all-meta ban file must warn, not silently pass
            ban2 = bd / "ban-empty.json"
            ban2.write_text(json.dumps({"_comment": ["only documentation"], "_notes": ["x"]}))
            r2 = audit(str(bd), ban_file=str(ban2))
            expect["--ban warns when no phrase is active"] = "no active phrases" in " ".join(r2["warnings"])
            for k in list(expect)[-6:]:
                v = expect[k]
                ok = ok and v
                print(f"  {'PASS' if v else 'FAIL'}  {k}")
            if " ".join(rb["errors"]):
                print(f"\n  ban fixture errors: {len(rb['errors'])} "
                      f"(expected exactly 1: the real banned phrase)")
                if len(rb["errors"]) != 1:
                    ok = False
                    print("  FAIL  ban fixture should report exactly one error")
        finally:
            shutil.rmtree(bd, ignore_errors=True)

        # ── ban/terms context handling (regression test for §A6 false positives) ──
        cd = Path(tempfile.mkdtemp(prefix="qa-selftest-ctx-"))
        try:
            (cd / "Ctx Page.md").write_text(
                "# Ctx Page\n\n"
                "Lead paragraph long enough to satisfy the lead-paragraph check.\n\n"
                "## Body\n\n"
                "There is no GPG or sigstore verification of any download.\n\n"
                "The subject uses a database for sessions.\n\n"
                "Jump to [the matrix](#mdscribe-extensions) and see `MDScribe` in code.\n\n"
                "The 404 body reads: refused by the security validator.\n\n"
                "Delete the line to unlock a hard lock.\n\n"
                "## See also\n\n- [[Ctx Page]]\n")
            (cd / "_Sidebar.md").write_text("**[[Ctx Page]]**\n")
            (cd / "ban.json").write_text(json.dumps({
                "_comment": ["meta must never be treated as a phrase"],
                "GPG": "no signature verification exists",
                "uses a database": "the subject is stateless",
                "fluff_exemptions": [{"phrase": "unlock", "reason": "domain term: unlock a hard lock"}],
            }))
            (cd / "terms.json").write_text(json.dumps({
                "canonical": {"hard lock": "hard[- ]lock"},
                "avoid": {
                    "MDScribe (slug/filename must not fire)": "MDScribe",
                    "security validator (verbatim subject string)": "security validator",
                },
                "exemptions": [{"phrase": "security validator (verbatim subject string)",
                                "quote": "refused by the security validator",
                                "reason": "verbatim 404 string of the subject"}],
            }))
            rc = audit(str(cd), terms_file=str(cd / "terms.json"), ban_file=str(cd / "ban.json"))
            ce, cw, ci = " ".join(rc["errors"]), " ".join(rc["warnings"]), " ".join(rc.get("infos") or [])
            expect.update({
                "negation downgrades a ban to WARNING": ("no GPG" not in ce) and ("NEGATED" in cw),
                "real banned claim still ERRORS": "uses a database" in ce,
                "anchor slug does not fire avoid": not any(
                    "avoided term" in e and "mdscribe" in e.lower() for e in rc["errors"]),
                "inline code does not fire avoid": not any(
                    "avoided term" in e and "MDScribe" in e for e in rc["errors"]),
                "exempted avoid term is INFO": "exempted avoided term" in ci,
                "exempted fluff is INFO": "exempted filler" in ci,
                "meta key _comment never fires": "_comment" not in ce,
            })
            for k in list(expect)[-7:]:
                v = expect[k]; ok = ok and v
                print(f"  {'PASS' if v else 'FAIL'}  {k}")
            if rc["errors"]:
                print(f"\n  ctx fixture errors ({len(rc['errors'])}):")
                for e in rc["errors"]:
                    print("    ", e[:150])
        finally:
            shutil.rmtree(cd, ignore_errors=True)

        if not ok:
            print("\nSELF-TEST FAILED — the checker is blind to something. Fix it before trusting a clean run.")
            return 1
        print("SELF-TEST PASSED — the checker can fail, so a clean run means something.")
        return 0
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wiki_dir", nargs="?")
    ap.add_argument("--strict", action="store_true", help="exit non-zero if any error is found")
    ap.add_argument("--json", help="write the full result as JSON")
    ap.add_argument("--terms", help="terms.json with {canonical:{term:regex}, avoid:{term:regex}}")
    ap.add_argument("--ban", help="JSON list/dict of phrases that must not appear")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()

    if a.self_test:
        return self_test()
    if not a.wiki_dir:
        ap.error("wiki_dir is required (or use --self-test)")

    r = audit(a.wiki_dir, terms_file=a.terms, ban_file=a.ban, json_out=a.json)
    s = r["stats"]

    if not a.quiet:
        w = max([len(x["file"]) for x in s["per_page"]] + [10])
        print(f'{"file":<{w}}{"words":>7}{"H1":>4}{"anch":>6}{"alert":>7}{"mmd":>5}{"code":>6}{"tbl":>6}')
        for x in sorted(s["per_page"], key=lambda y: y["file"]):
            print(f'{x["file"]:<{w}}{x["words"]:>7}{x["h1"]:>4}{x["anchors"]:>6}'
                  f'{x["alerts"]:>7}{x["mermaid"]:>5}{x["code_blocks"]:>6}{x["table_rows"]:>6}')
        print(f'\nTOTAL  pages={s["pages"]} ({s["content_pages"]} content)  words={s["words"]:,}  '
              f'alerts={s["alerts"]}  mermaid={s["mermaid"]}  tables={s["table_rows"]:,}  '
              f'code={s["code_blocks"]}  wiki-links={s["wiki_links"]}')
        print(f'checked: {s["shell_blocks_checked"]} shell blocks, {s["python_blocks_checked"]} python blocks')
        if "terminology" in s:
            top = list(s["terminology"].items())[:12]
            print("terminology: " + ", ".join(f"{k}×{v}" for k, v in top))
        print(f'\nERRORS ({len(r["errors"])}):')
        for e in r["errors"][:80]:
            print("  ✗", e)
        if len(r["errors"]) > 80:
            print(f"  … and {len(r['errors']) - 80} more")
        print(f'\nWARNINGS ({len(r["warnings"])}):')
        for x in r["warnings"][:40]:
            print("  !", x)
        if len(r["warnings"]) > 40:
            print(f"  … and {len(r['warnings']) - 40} more")
        inf = r.get("infos") or []
        if inf:
            print(f'\nEXEMPTED ({len(inf)}) — recorded, not enforced:')
            for x in inf[:25]:
                print("  ·", x)

    if a.strict and r["errors"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
