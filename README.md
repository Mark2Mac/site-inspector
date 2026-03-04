# Site Inspector

Windows-first CLI tool to audit websites and generate reproducible artifacts:

- **crawl**: page discovery (sitemap + internal links)
- **posture**: headers / TLS / DNS / tech fingerprinting / third parties
- **quality**: Lighthouse + budgets
- **playwright**: JS-rendered artifacts (DOM/screenshot/network)
- **run**: orchestrates crawl → posture → quality → (optional) playwright
- **diff**: compare two runs and report regressions

## Status (today)

✅ End-to-end pipeline verified on Windows:

- `run` generates `run.json` + `run.md`
- `playwright` generates `playwright_summary.json`
- `diff` generates `diff.json` + `diff.md`

✅ Scale-A groundwork implemented:

- Concurrent crawl worker support (`--crawl-workers`)
- Lighthouse concurrency control (`--lighthouse-workers`)
- Windows-safe subprocess execution for Node wrappers (npx.cmd)
- UTF-8 safe subprocess output capture
- CLI/module arg compatibility hardening (aliases + safe defaults)

## Quick start

### Full run
```powershell
python site_audit.py run https://example.com
```

### Fast crawl (up to ~500 pages)
```powershell
python site_audit.py crawl https://example.com --max-pages 300 --crawl-workers 16
```

### Quality audit (heavy — keep workers low)
```powershell
python site_audit.py quality https://example.com --max-pages 30 --crawl-workers 16 --lighthouse-workers 2
```

### JS rendering (Playwright)
```powershell
python site_audit.py playwright https://example.com --max-pages 10
```

### Diff two runs
```powershell
python site_audit.py run https://example.com --skip-playwright --out runs\runA
python site_audit.py run https://example.com --skip-playwright --out runs\runB
python site_audit.py diff runs\runA runs\runB --out diffs\runA_vs_runB
```

## Output structure

A run produces:

```
inspect_<host>_<timestamp>/
  run.json
  run.md
  pages.json
  posture.json
  lighthouse/
  playwright/
  raw/
```

Diff produces:

```
diffs/<name>/
  diff.json
  diff.md
```

## Architecture

`site_audit.py` is the stable entrypoint.

Modules live in `site_inspector/`:

- `cli.py` – CLI + commands
- `crawl.py` – page discovery (concurrent)
- `posture.py` – posture collection
- `lighthouse.py` – Lighthouse runner + budget eval (worker cap + arg alias)
- `playwright_audit.py` – Playwright artifacts
- `diffing.py` – diff engine + Markdown renderer
- `reporting.py` – run report generation
- `utils.py` – shared helpers
- `inner_collectors.py` – isolated venv runner for collectors

## Roadmap

See **ROADMAP_VERBOSE.md** for the detailed plan and next steps.
