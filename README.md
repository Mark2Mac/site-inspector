# Site Inspector

Site Inspector is a **Windows-first CLI for technical website auditing**.

It has grown from a crawler prototype into a **site intelligence tool** that combines:
- crawl and resumeable site discovery
- Lighthouse quality analysis
- Playwright rendering checks
- duplicate-content and structure clustering
- SEO auditing
- AI crawler readiness auditing
- run-to-run diffing
- Windows-friendly packaging and release flows

## Current status

Current baseline is stable:
- regression suite is green
- packaging builds (`sdist` and `wheel`) pass
- release checks pass via `twine check`
- local artifacts are isolated under `.site_inspector_local/`

The next workstream is **production hardening**, done in a few controlled iterations:
1. packaging cleanup
2. output contracts
3. reliability and diagnostics
4. validation corpus

## Installation

Editable install for development:

```powershell
py -m pip install -e .
```

Install dev tooling:

```powershell
py -m pip install -r requirements-dev.txt
```

Module entrypoint:

```powershell
py -m site_inspector --version
py -m site_inspector run https://example.com --max-pages 5 --skip-playwright
```

Legacy script entrypoint remains supported:

```powershell
py site_audit.py --version
```

## Example usage

Run a crawl:

```powershell
py site_audit.py crawl https://example.com --max-pages 5 --out .site_inspector_local\runs\crawl_demo
```

Run a full audit:

```powershell
py site_audit.py run https://example.com --max-pages 5 --out .site_inspector_local\runs\run_demo
```

Compare two runs:

```powershell
py site_audit.py diff .site_inspector_local\runs\golden .site_inspector_local\runs\candidate --out .site_inspector_local\diffs\golden_vs_candidate
```

## Output model

Each run can produce:
- `pages.json`
- `posture.json`
- `quality_summary.json`
- `playwright_summary.json`
- `run.json`
- `run.md`

Diff runs generate:
- `diff.json`
- `diff.md`

All local test and packaging artifacts should stay under:

```text
.site_inspector_local/
```

## Testing

Fast regression checks:

```powershell
py -m pytest -q
```

Full local validation:

```powershell
.\run_tests.ps1 -All
```

## Packaging and release

Local package build:

```powershell
py -m build --sdist --wheel --outdir .site_inspector_local\dist
py -m twine check .site_inspector_local\dist\*
```

See `RELEASING.md` for the release checklist.

## Docs to keep aligned

- `ROADMAP.md` — current delivery plan
- `CHANGELOG.md` — shipped changes and unreleased work
- `RELEASING.md` — public package / release steps
- `AI_INSTRUCTIONS.md` — AI collaboration protocol
