# Changelog

## Unreleased
- Packaging metadata via `pyproject.toml`
- `python -m site_inspector` module entrypoint
- Console script metadata for `site-inspector`
- Separate worker pools (net vs heavy)
- Host throttling + retries
- Resumeable runs via per-page caching
- URL normalization guardrails
- Smarter Lighthouse sampling

## 0.5 (current)
- Modular architecture stabilized on Windows
- End-to-end pipeline verified: run → playwright → diff
- Crawl worker concurrency control (`--crawl-workers`)
- Lighthouse concurrency control (`--lighthouse-workers`)
- Windows subprocess handling hardened (npx.cmd) + UTF-8 output capture
- API hardening for CLI/module compatibility (arg aliases + safe defaults)
