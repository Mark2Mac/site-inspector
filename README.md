# Site Inspector

Site Inspector is a Windows-first CLI tool to audit websites and generate structured artifacts and reports:

- Crawl (page discovery)
- Posture (headers / TLS / DNS / tech fingerprinting / third parties)
- Quality (Lighthouse + budgets)
- JS Rendering (Playwright artifacts)
- Diff (regressions between two runs)

## Quick start

### Full run
```powershell
python site_audit.py run https://example.com
```

### Crawl only (now concurrent)
```powershell
python site_audit.py crawl https://example.com --max-pages 200 --crawl-workers 16
```

### Lighthouse quality (heavy; keep workers low)
```powershell
python site_audit.py quality https://example.com --max-pages 50 --lighthouse-workers 2
```

### Playwright artifacts
```powershell
python site_audit.py playwright https://example.com --max-pages 10
```

### Diff two runs
```powershell
python site_audit.py diff runs\\runA runs\\runB --out diffs\\runA_vs_runB
```

## Outputs

A run produces:

```
inspect_<host>_<timestamp>/
  run.json
  run.md
  pages.json
  posture.json
  quality_summary.json (when quality enabled)
  lighthouse/
  playwright/
  raw/
```

## Architecture

`site_audit.py` is the stable entrypoint.

Modules live in `site_inspector/`:

- `cli.py` – argparse + commands
- `crawl.py` – sitemap + internal link discovery (**now concurrent**)
- `posture.py` – tech/headers/TLS/DNS/meta/third parties
- `lighthouse.py` – Lighthouse runner + budgets (**now supports worker cap**)
- `playwright_audit.py` – Playwright artifacts
- `diffing.py` – run diff + regression detection + Markdown renderer
- `reporting.py` – Markdown report generation
- `utils.py` – helpers (safe I/O, subprocess, URL utils)

## Scalability roadmap

See `ROADMAP_VERBOSE.md`.
