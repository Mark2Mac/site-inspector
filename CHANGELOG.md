# Changelog

## Unreleased

### Added
- public packaging and release validation in the local workflow
- release checklist documentation in `RELEASING.md`
- production hardening roadmap with 4 focused iterations
- metadata regression coverage for packaging cleanup

### Changed
- packaging metadata aligned with the current project state
- project license metadata moved to a string-based form compatible with newer packaging guidance
- `.gitignore` and manifest patterns tightened to keep local artifacts out of builds
- README updated to reflect the actual capabilities and current hardening phase

## 0.7.0
- packaging metadata via `pyproject.toml`
- `python -m site_inspector` module entrypoint
- console script metadata for `site-inspector`
- duplicate detection validation layer
- crawl guardrails (URL normalization, query-shape cap, path-depth cap)
- SEO auditing layer
- AI crawler readiness layer
- polished run/diff reporting
- Windows-first regression and smoke workflow
