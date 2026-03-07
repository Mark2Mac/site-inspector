# Changelog

All notable changes to this project will be documented in this file.

The format is intentionally simple and human-readable.
Version numbers reflect public project milestones rather than every internal iteration.

## Unreleased

### Planned
- Stronger validation semantics for duplicate/content-quality checks
- Graph intelligence for internal linking and structural analysis
- Broader structured data and discoverability auditing
- Additional pipeline-friendly outputs for automation workflows

---

## 0.7.0

### Added
- Public-facing project packaging with `pyproject.toml`, build checks, and release validation
- Module entrypoint support via `python -m site_inspector`
- Public release workflow support for exporting a clean publishing snapshot
- Output contract validation for `run.json`, `quality_summary.json`, and `diff.json`
- Local validation corpus coverage for robots, sitemap, nested pages, and duplicate scenarios
- Regression coverage for CLI error handling and debug-mode traceback behavior

### Improved
- README positioning around the real core workflow: **before/after rebuild auditing**
- Stronger reporting layout for `run.md` and `diff.md`
- Cleaner CLI behavior and more stable public project metadata
- Better packaging alignment for public distribution and GitHub presentation

### Fixed
- Fixed the `group_map` regression in `cmd_run` when using `--lighthouse-sample`
- Fixed multiple Windows/PowerShell workflow issues in the test and release path
- Fixed contract drift between generated outputs and expected schemas
- Fixed public export issues related to fingerprint scrubbing and verification

---

## 0.6.x

### Added
- SEO audit layer covering titles, meta descriptions, H1 presence, canonicals, status awareness, and internal-link summaries
- AI crawler readiness audit covering `robots.txt`, sitemap presence/health, noindex signals, and JS-disabled readability
- Duplicate detection and validation reporting using DOM fingerprint clustering
- Smart Lighthouse sampling controls:
  - `--lighthouse-sample`
  - `--lighthouse-per-group`
  - `--lighthouse-max-pages`
  - `--lighthouse-include`
- Resume mode for reusing cached stage outputs across interrupted runs
- Golden schema checks and regression-oriented CLI tests

### Improved
- Diff workflow for comparing two runs as structured before/after snapshots
- Markdown reporting clarity and executive-summary style output
- Crawl normalization and guardrails for more stable repeated runs

### Fixed
- Multiple Windows-specific CLI/test issues
- Encoding and BOM handling for JSON budget/config files
- Human-readable error paths when diff inputs are missing or invalid

---

## 0.5

### Added
- Initial multi-command CLI structure:
  - `crawl`
  - `quality`
  - `playwright`
  - `run`
  - `diff`
- JSON and Markdown output generation for full audit runs
- Lighthouse-backed quality reporting
- Playwright-based rendered-page checks
- Baseline diffing support for comparing two site runs

### Established
- Windows-first workflow
- Deterministic local testing strategy
- Project direction around technical website auditing rather than generic crawling

---

## Notes

This changelog is meant to describe externally meaningful project evolution:
- new audit capabilities
- reporting changes
- workflow and packaging improvements
- important bug fixes and regressions

It is not intended to mirror every internal patch or private iteration.