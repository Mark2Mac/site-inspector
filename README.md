# Site Inspector

**Crawl a site. Audit it. Rebuild it. Diff the difference.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.8.0-informational.svg)](CHANGELOG.md)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)

---

Site Inspector is a cross-platform CLI for **technical website auditing**, with a strong focus on **before/after rebuild analysis**, **SEO and AI-crawler readiness**, and **structured regression checks**.

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
| **Link Graph** | Internal PageRank, HITS hub/authority, orphan pages, dead ends, articulation points, SCCs |
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

site-inspector run https://example.com --max-pages 50
```

Typical output lands in an auto-named directory such as:

```text
run.html                 ← interactive report (open in browser)
run.md                   ← human-readable markdown
run.json                 ← structured output for automation
graph.json               ← node-link graph for external tools
pages.json               ← per-page crawl data
posture.json             ← TLS, tech stack, third parties
quality_summary.json     ← Lighthouse scores
```

`run.html` is a self-contained interactive report with SVG charts, link graph metrics, and collapsible sections — works fully offline.
`run.json` is the structured output for automation and diffing.

---

## MCP Server (AI assistant integration)

Site Inspector ships an [MCP](https://modelcontextprotocol.io) server so any AI assistant can audit websites directly from a conversation — no terminal needed.

```bash
pip install "site-inspector[mcp]"
```

Configure in Claude Desktop (`~/.claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "site-inspector": {
      "command": "site-inspector-mcp"
    }
  }
}
```

Configure in Claude Code (global or project MCP settings):

```json
{
  "mcpServers": {
    "site-inspector": {
      "command": "site-inspector-mcp"
    }
  }
}
```

### Available MCP tools

| Tool | Description |
|---|---|
| `inspect_site(url, max_pages)` | Full audit — crawl, SEO, link graph, AI readiness |
| `diff_site_runs(run_a, run_b)` | Compare two audit runs, report regressions |
| `load_site_run(run_dir)` | Summarize an existing run from disk |
| `site_graph_insights(run_dir)` | Deep link graph analysis (PageRank, HITS, bottlenecks) |

Once configured, you can ask Claude:

> "Audit https://example.com and tell me the top SEO issues"
> "Which pages have zero inbound links?"
> "Compare the run from yesterday to today's run"

---

## Core use cases

### Before / after a site rebuild

```bash
# Audit the current site
site-inspector run https://example.com --skip-playwright --out runs/before

# Rebuild the site, then audit again
site-inspector run https://example.com --skip-playwright --out runs/after

# Compare the two
site-inspector diff runs/before runs/after --out diffs/rebuild
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
site-inspector <command> [options]
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
site-inspector run https://example.com --out runs/my-audit

# Second run: reuse cached outputs where possible
site-inspector run https://example.com --out runs/my-audit --resume
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

Deterministic test suite (all platforms):

```bash
pytest -q
pytest -vv
```

Extended smoke tests:

```bash
# Mac / Linux
bash run_tests.sh

# Windows
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

---

## Project structure

```text
site_inspector/
├── cli.py
├── crawl.py
├── posture.py
├── inner_collectors.py
├── seo_audit.py
├── ai_audit.py
├── lighthouse.py
├── playwright_audit.py
├── diffing.py
├── duplicates.py
├── reporting.py
├── log.py
├── utils.py
└── scripts/
    ├── inner_collector.py
    └── playwright_runner.cjs

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
site-inspector --help
python -m site_inspector --help
```

---

## Current strengths

- deterministic CLI workflow
- useful before/after diffing
- crawl normalization guardrails
- link graph analysis: PageRank, HITS, orphan/dead-end detection, articulation points
- duplicate/template-aware analysis
- AI-crawler readiness checks (robots.txt, sitemap.xml, JS-disabled readability)
- structured reporting: HTML, Markdown, JSON, `graph.json`
- MCP server for AI assistant integration
- packaging and release verification
- test suite with contract validation and regression coverage

---

## Near-term roadmap

- stronger validation semantics for duplicate / template signals
- deeper structured-data and discoverability checks
- additional pipeline-friendly output formats

See `ROADMAP.md` for planning details.

---

## Built with

- Requests — HTTP client
- Beautiful Soup — HTML parsing
- NetworkX — link graph analysis and graph metrics
- Lighthouse — web quality auditing
- Playwright — browser automation and rendered-page checks
- pytest — test framework

---

## Example

Site Inspector was originally built to audit [dedicatodesign.com](https://www.dedicatodesign.com)
during a full site rebuild. The before/after diffing workflow was designed around that
real-world use case.

---

## License

MIT — see `LICENSE`.

## Release notes

See `CHANGELOG.md`.
