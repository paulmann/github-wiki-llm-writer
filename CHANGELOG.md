# Changelog

## 1.0.0 — initial public release

Extracted from a completed run that produced a 22-file, 73 013-word GitHub Wiki
for [paulmann/MD.Viewer](https://github.com/paulmann/MD.Viewer) with zero
outstanding QA errors.

### Added

- `SKILL.md` — agent entry point with the four-phase workflow.
- `AGENTS.md` — phase-to-tool mapping and the tool reference table.
- `PROMPT.md` — a ready-to-paste task prompt; only the header block changes.
- `setup/bootstrap.sh` — idempotent environment setup with a capability and
  network-egress report.
- `setup/PITFALLS.md` — 27 traps encountered in the reference run, ordered by
  time wasted, with the three that produce silently wrong results first.
- `scan/repo_scan.py` — whole-repository inventory to JSON plus a two-minute
  brief. Symbol extraction for PHP, JS/TS, Python, Go, Ruby, Java, C#, PowerShell
  and shell; manifest detection for eight ecosystems; external-host, version-marker
  and security-signal extraction.
- `lib/req.py` — dependency-free HTTP client returning status, headers and body
  for every outcome including 4xx/5xx, with form and multipart helpers and a CLI.
- `lib/serve.py` — `ServedApp`: stages a clean copy of the subject on a
  verified-free port, waits for readiness, probes once over HTTP, and kills its own
  process group. Fixture helpers `write` / `mkdir` / `set_ini` / `ls` / `read`.
- `probe/webapp_probe.py` — declarative batteries (modes, 20 traversal payloads,
  26 injection payloads, config-flag gating, upload matrices, API status codes,
  header inventory, disk side-effects) emitting evidence as JSON and Markdown.
- `qa/qa_wiki.py` — the full wiki audit with `--self-test`, `--strict`, `--json`,
  `--terms` and `--ban`.
- `scaffold/new_page.py` — QA-clean wiki skeleton or single page.
- `publish/publish.sh` — QA gate, clone of the `.wiki.git` repository, commit,
  verified git bundle, and three publishing paths. Never prompts, never
  force-pushes.
- `templates/` — `terms.json`, `ban.json`, `STATE.md.tmpl`, `PROGRESS.json.tmpl`.
- `examples/` — research artefacts and sample pages from the reference run.
- CI workflow running the QA self-test, syntax checks and a scaffold round-trip.

### Bugs found and fixed while extracting the kit

Nine defects were found in the tools themselves during extraction. All were
caught by running them, not by reading them — which is the point of the kit.

1. `qa_wiki.py`: `name, text = p.name, texts[name]` — Python evaluates the whole
   right-hand side with the **old** `name`, so every page was audited against the
   previous page's text. Produced 235 phantom errors.
2. `qa_wiki.py`: code-block bodies were never accumulated (missing `buf.append`),
   so the mermaid and shell checks ran vacuously and always passed.
3. `qa_wiki.py`: the bracket-in-label check fired on quoted labels and on the
   mermaid cylinder shape `[(...)]`.
4. `qa_wiki.py`: the `subgraph`/`end` balance check was applied to
   `sequenceDiagram`, where `end` closes `alt`/`opt`/`loop` instead.
5. `qa_wiki.py`: the lead-paragraph regex was too strict, producing four false
   warnings on pages whose lead is followed by an alert or a table.
6. `new_page.py`: `_Footer.md` and `Home.md` hardcoded page names
   (`[[Glossary]]`, `[[Changelog and Versioning]]`, `[[Getting Started]]`), so any
   other page list produced dead links — and the footer renders on every page.
   Now derived from the page list actually being created.
7. `publish.sh`: a relative `WIKI_DIR` stopped resolving after the script `cd`'d
   into the clone (`cp: cannot stat '.scratch/wiki/*.md'`). Now absolutised up front.
8. `publish.sh`: an interactive `read` prompt aborted in a sandbox with no
   controlling terminal, and it gated on a filename heuristic that false-positives
   on legitimate titles such as `Self-Updater Guide.md`. Now non-blocking and
   non-interactive; the authoritative check is the QA step.
9. `templates/terms.json`: two over-broad `avoid` patterns (`base director`,
   `config file`) fired on correct prose. Narrowed to four high-confidence
   patterns, with a tuning warning added.

### Corrections the tools found in the delivered wiki

Worth recording because it demonstrates the value of phase 4 step 3 (re-running
what you documented):

1. `Architecture.md` quoted **fabricated** code for the doubled-slash normaliser
   (`parse_url(..., PHP_URL_PATH)`). Replaced with the verbatim source.
2. The normaliser was documented as path-only; it also rewrites the **query
   string** (verified: `?file=docs//sub/a.md` → 301 → `?file=docs/sub/a.md`).
3. The claim that `&force=true` propagates from update phase 1 to phase 2 was
   transcribed from the subject's README; the code builds a literal query string
   and drops it. Corrected, with the discrepancy documented.
