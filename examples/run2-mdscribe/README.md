# examples/run2-mdscribe — a second reference run, with an admin surface

The first reference run ([`../`](../), MD.Viewer) covered a read-mostly viewer:
one entry point, one deployment layout, no authentication. This second run covers
the shape that broke the kit's assumptions — **`paulmann/MD.Scribe` 3.1.0**, a
PHP application with an admin panel, sessions, CSRF, rate limiting and **two**
deployment layouts.

Delivered by that run: 23 wiki pages, 41 623 words, 28 alerts, 9 mermaid
diagrams, 786 table rows, 252 wiki-links, **0 QA errors**, 249 empirical checks
(234 pass / 0 fail / 15 findings), 14 verified doc-vs-code discrepancies.

## Files

| File | What it is |
|---|---|
| `probe_mdscribe.py` | The complete probe battery: 249 checks across two staged instances — traversal, injection, config flags, render matrix, an ordered stateful admin flow, machine API, v2 shims, and disk side-effects. **1571 lines.** This is the model for a `suite_*` that needs ordered, session-bearing steps. |

## The four patterns worth copying

### 1. Two layouts = two `ServedApp` instances in one run

The subject ships two deployment shapes: docroot at `public/` with a front
controller, and docroot at the repository root for the v2 compatibility shims
(`md.php`, `updater.php` + machine API). The shims are **physically unreachable**
in the first layout, so one staged server cannot cover the contract.

```python
with ServedApp(repo, copy=['public','src','vendor'], serve_cmd='php -S {host}:{port} -t {root}/public router.php') as A, \
     ServedApp(repo, copy=['md.php','updater.php','src','vendor'], serve_cmd='php -S {host}:{port} -t {root}') as B:
    ...
```

`ServedApp` supports this; the `webapp_probe.py` CLI assumes one `--entry`, which
is why this battery is a standalone driver. Use `--serve-cmd` on the CLI for a
single non-PHL default, or write a driver like this one for two.

### 2. Never trust a 200 without a body marker

The first "successful" `GET /md.php` in layout A returned **200** — it was the
router's fall-through to the home page, not the shim. The status code was
correct and the result was meaningless. Every check in this battery asserts on a
**body marker**, not on the status:

```python
def check(name, resp, marker=None, status=None):
    ok = (status is None or resp.status == status) and (marker is None or marker in resp.text)
    ...
```

This is the single most transferable lesson in the file.

### 3. One bad CSRF regex cascades

The subject printed its CSRF token in **three different shapes** on three
different pages — JSON `"csrf":"…"`, a JS literal `csrf: "…"`, and a JS field
`_token: "…"`. A single-pattern extractor missed the setup page, and the whole
admin branch (60+ checks) failed as a cascade of 403s. That is why
`lib/session.py` ships `csrf_from_html` with six patterns, and why
`setup/PITFALLS.md` §D2 says: **verify one case by hand before fixing a mass
failure.**

### 4. Token placement is part of the contract

The subject's `Csrf::validate` reads only the body field and a header — a token
in the **query string is rejected**. Sending `_token` in the URL yields 403 with
no hint why. `SessionClient(...).post_form(path, fields, token=tok)` therefore
places the token in both the body field and a header, never in the URL.

## Reproducing

```bash
export MDS_TOOLS_LIB=<kit>/lib                 # for serve.py / req.py / session.py
export MDS_REPO=<MD.Scribe clone WITH vendor/> # composer install first — see PITFALLS B9/B10
export MDS_OUT_JSON=/tmp/probe.json
export MDS_OUT_MD=/tmp/probe.md
python3 probe_mdscribe.py                      # -> 234 pass / 0 fail / 15 findings of 249
```

The 15 "findings" are not failures: they are observations the battery records
without asserting (for example manifest drift — `.gitignore` 397 B in the
published manifest vs 534 B in the commit, and composer-generated
`vendor/composer/*` never hashing equal to a fresh install).

> [!NOTE]
> The subject requires PHP >= 8.3 (`json_validate()`, typed class constants). On
> the distro default of 8.2 it does not boot at all, so every probe measures a
> corpse — see `setup/PITFALLS.md` §B10 for the sury recipe.
