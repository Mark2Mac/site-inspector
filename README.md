# Site Inspector

**Crawl a site. Audit it. Rebuild it. Diff the difference.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.7.0-informational.svg)](CHANGELOG.md)

---

Site Inspector is a Windows-first CLI for **technical website auditing**, with a strong focus on **before/after rebuild analysis**, **SEO and AI-crawler readiness**, and **structured regression checks**.

The core workflow is simple:

1. audit the current site  
2. rebuild or regenerate it  
3. audit the new version  
4. diff the two runs and inspect what changed  

That makes the tool especially useful for:
- site rebuilds and migrations
- QA for AI-generated sites
- regression checks before production releases
- repeatable audits for sites deployed on GitHub, Vercel, or DigitalOcean

---

## What it does

Site Inspector combines multiple audit layers into one CLI workflow:

| Layer | What gets audited |
|---|---|
| **Crawl** | Page discovery, normalized URLs, redirect-aware inventory, guardrails |
| **SEO** | Titles, meta descriptions, H1s, canonicals, status-code issues, internal linking |
| **AI crawler readiness** | `robots.txt`, `sitemap.xml`, `noindex`, JS-disabled readability |
| **Quality** | Lighthouse scores, budgets, grouped sampling |
| **Duplicates** | DOM fingerprint clustering and near-template detection |
| **Diff** | Added/removed pages, regressions, new third parties, tech changes |

---

## Why it exists

Most audit tools are good at one of these things:

- crawling
- Lighthouse scoring
- SEO linting
- browser rendering checks

Very few are good at answering the practical question that matters during a rebuild:

**What got better, what got worse, and what changed between the old site and the rebuilt one?**

Site Inspector is built around that exact use case.

---

## Quick start

```bash
pip install -e .

# Full audit
python site_audit.py run https://example.com --max-pages 50

# Or use the installed entry point
site-inspector run https://example.com --max-pages 50
```

Typical output lands in an auto-named directory such as:

```text
run.md
run.json
pages.json
posture.json
quality_summary.json
playwright_summary.json
```

`run.md` is the human-readable report.  
`run.json` is the structured output for automation and diffing.

---

## Core use cases

### Before / after a site rebuild

```bash
# Audit the current site
python site_audit.py run https://example.com --skip-playwright --out runs/before

# Rebuild the site, then audit again
python site_audit.py run https://example.com --skip-playwright --out runs/after

# Compare the two
python site_audit.py diff runs/before runs/after --out diffs/rebuild
```

`diff.md` gives you an executive summary.  
`diff.json` gives you structured data for CI, pipelines, or further analysis.

The diff tracks signals such as:
- pages added or removed
- Lighthouse regressions
- new third-party domains
- tech stack changes
- shifts in JS-disabled readability

### AI-generated site QA

If you generate sites automatically, you need automatic validation too.

Site Inspector helps answer questions like:
- Is `robots.txt` present and sane?
- Does `sitemap.xml` exist and point to real pages?
- Is content still understandable without JavaScript?
- Did the generator accidentally create duplicate templates?
- Are key SEO signals present before deploy?

That makes it useful for high-throughput publishing workflows where manual review is too slow or too inconsistent.

---

## Commands

```text
python site_audit.py <command> [options]
```

| Command | What it does |
|---|---|
| `run` | Full pipeline: crawl → posture → Lighthouse → Playwright → report |
| `crawl` | Discover pages only, save `pages.json` |
| `quality` | Crawl + Lighthouse scores + budget evaluation |
| `playwright` | HAR capture, screenshots, JS-disabled readability |
| `diff` | Compare two completed run outputs |

### Common options

```text
--max-pages N             Stop crawling after N pages
--out PATH                Output directory
--resume                  Reuse cached artifacts
--skip-playwright         Skip browser capture
--crawl-workers N         Concurrent crawl workers
--lighthouse-sample N     Run Lighthouse on a sampled subset
--lighthouse-per-group N  Pick up to N pages per template group
--budget PATH             JSON file with score thresholds
```

---

## Resume mode

If a run is interrupted, or if you want to regenerate only the later stages, you can reuse prior artifacts with `--resume`.

```bash
# First run
python site_audit.py run https://example.com --out runs/my-audit

# Second run: reuse cached outputs where possible
python site_audit.py run https://example.com --out runs/my-audit --resume
```

This is especially helpful when iterating on reports or validating large sites with sampled quality checks.

---

## Output format

### `run.json`
Machine-readable consolidated audit output.

### `run.md`
Human-readable report with summary sections and interpretation.

### `diff.json`
Structured regression/change output.

### `diff.md`
Executive summary of the differences between two runs.

The JSON outputs are validated in tests against contract files to reduce accidental schema drift.

---

## Prerequisites

| Dependency | Required for |
|---|---|
| Python 3.11+ | Everything |
| Node.js + `npx` | Lighthouse-based quality checks |
| Chromium / Chrome | Lighthouse and Playwright |
| Playwright browsers | `playwright` command |

Install dev dependencies:

```bash
pip install -e ".[dev]"
```

---

## Testing

Deterministic test suite:

```bash
pytest -q
pytest -vv
```

Windows smoke and workflow checks:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_tests.ps1 -All
```

The test suite covers:
- CLI behavior
- output contracts
- reporting layout
- crawl guardrails
- diff error handling
- validation corpus behavior
- packaging metadata
- public export checks

---

## Project structure

```text
site_inspector/
├── cli.py
├── crawl.py
├── seo_audit.py
├── ai_audit.py
├── lighthouse.py
├── playwright_audit.py
├── diffing.py
├── duplicates.py
├── reporting.py
├── posture.py
└── utils.py

tests/
├── fixtures/
├── golden/
└── test_*.py
```

---

## Packaging

Build locally:

```bash
python -m build --sdist --wheel
```

Validate distributions:

```bash
python -m twine check dist/*
```

CLI entry points are available through:

```bash
python site_audit.py --help
python -m site_inspector --help
site-inspector --help
```

---

## Development model

This project is designed to support a **private development repo** and a **clean public export** flow.

That allows:
- full iteration and experimentation in private
- curated, fingerprint-scrubbed public snapshots
- cleaner presentation on GitHub
- safer release hygiene

---

## Current strengths

- deterministic CLI workflow
- useful before/after diffing
- crawl normalization guardrails
- duplicate/template-aware analysis
- AI-crawler readiness checks
- structured reporting and output contracts
- packaging and release verification
- validation corpus coverage

---

## Near-term roadmap

- stronger validation semantics for duplicate / template signals
- graph intelligence and richer site structure analysis
- deeper structured-data and discoverability checks
- continued hardening of the public export workflow

See `ROADMAP.md` for planning details.

---

## License

MIT — see `LICENSE`.

## Release notes

See `CHANGELOG.md`.
