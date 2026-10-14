# examples/ — artefacts from the reference run

These are real outputs from the completed run that produced this kit, against
[paulmann/MD.Viewer](https://github.com/paulmann/MD.Viewer) — a self-hosted PHP
Markdown viewer (`md.php` v2.18.0, `updater.php` v3.14.0, MIT, no database, no
build step, no dependencies).

They are here to **calibrate depth and house style**, not to be copied. Read them
in this order:

| File | What it demonstrates |
|---|---|
| [`research/sources.md`](research/sources.md) | The provenance discipline. Section A cites source lines, B names each empirical test, C lists external sources, and **D lists claims deliberately not made, with reasons** — the section that becomes `ban.json` |
| [`research/summary.md`](research/summary.md) | How measured findings are written up: every behavioural claim marked `[tested]`, with the divergences from the subject's own README stated plainly |
| [`research/facts.json`](research/facts.json) | The machine-readable fact base, with a `source` on every value so "was this verified or assumed?" stays answerable |
| [`research/architecture.md`](research/architecture.md) | Component map, request lifecycle, render pipeline, and a function index **with line numbers** |
| [`research/domain-notes.md`](research/domain-notes.md) | Standards and security context, plus the **canonical glossary** that kept terminology consistent across 20 pages |
| [`research/scan.json`](research/scan.json) · [`research/probe.md`](research/probe.md) | Raw `repo_scan.py` and `webapp_probe.py` output |
| [`REPORT.md`](REPORT.md) | The delivery report: page inventory, what was verified and how, the findings where the subject's own docs are wrong, and an honest "what remains" including the limits of the analysis |
| [`sample-pages/`](sample-pages/) | Three delivered pages: `Home.md` (the entry point), `Markdown Extensions Matrix.md` (the measured input → output reference, including an honest divergences section), and `Security Hardening Guide.md` (threat model with reproducible findings) |

## What the run found

The interesting results were all cases where **the software and its documentation
disagreed**, and only execution revealed it:

- The README claimed *syntax highlighting*. A repository-wide search for external
  asset URLs found three CDNs — Tailwind, Google Fonts, Mermaid — and **no
  highlighter**. Code is emitted as `<pre><code class="language-x">` and styled by
  CSS alone.
- The README claimed *nested lists*. Indented children render as a literal
  paragraph containing the text `- child`, outside the list.
- Raw HTML passes through **unescaped**: `<script>`, `<img onerror>`,
  `<svg onload>`, `<iframe src="javascript:">` and `<a onclick>` were all
  reproduced verbatim. Reference-style links are additionally **not
  protocol-filtered**, so `[r]: javascript:alert(1)` yields a live `href` — while
  inline links `[t](javascript:…)` are safe, because those passes only match
  `#…` or `https?://…`.
- The README claimed `&force=true` "propagates automatically from phase 1 to
  phase 2". The code builds a literal query string and drops it.
- Path-traversal defence, by contrast, held completely: 14 layers including a
  post-symlink extension re-check, with 13 payloads verified refused. Denials
  return **HTTP 200** with a banner rather than a 4xx — deliberate
  non-disclosure, which matters if you write monitoring rules for it.
- The table of contents needs **at least two headings after the H1**, because the
  H1 is stripped from the body before headings are collected. The single most
  common "where is my TOC?" report.
- The glossary heuristic is **structural, not semantic**: any table with a
  non-empty first-column header becomes a glossary, so a `| A | B |` data table
  registers `1` as a term and tooltips every standalone `1` in the document.

Final numbers: 22 files, 73 013 words, 154 GitHub Alerts, 27 mermaid diagrams,
1 687 table rows, 341 internal wiki-links, **0 QA errors**, 137 shell blocks
passing `bash -n`.

## Note on the sample pages

`sample-pages/` holds three pages **excerpted from a 22-page wiki**, so their
`[[wiki-links]]` point at pages not present here and would not pass
`qa/qa_wiki.py` as a set. That is expected; the CI workflow does not audit this
directory. Judge them on structure and evidential discipline, not on link
resolution.
