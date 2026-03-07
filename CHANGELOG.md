
## 0.7.0-post-p4

- add deterministic local validation corpus with dynamic robots.txt and sitemap.xml
- add validation corpus tests and fast-vs-live runner modes
- mark production hardening iteration P4 complete

# Changelog

## Unreleased
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

- production hardening p3: human-readable CLI errors by default, optional debug tracebacks via `SITE_INSPECTOR_DEBUG=1`, and tighter diagnostics tests.
