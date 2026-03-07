# Site Inspector -- Development Roadmap

## Completed

- A1--A6: Core crawler foundation
- B0--B2: Analysis pipeline
- B3: Duplicate detection hardening + validation
- Milestone 0: Stability layer (CLI regression tests + golden schema checks)
- Milestone 1: Duplicate detection reliability
- Milestone 2: Crawl quality guardrails
  - stronger URL normalization
  - query-shape caps per path
  - path-depth caps
  - crawl metadata for guardrail hits

## Current Focus

### Milestone 3 -- SEO Auditing

Integrated initial SEO auditing layer:
- metadata checks (titles, descriptions, H1s)
- canonical checks
- status code and redirect analysis
- internal linking signals (zero inlinks/outlinks)

Current focus now moves to release prep and optional packaging hardening.

## Milestones

### Milestone 0 -- Stability
- H1: CLI regression tests
- H2: Golden output tests

### Milestone 1 -- Duplicate Detection
- B3 hardening
- B3 validation pass
- B3 reporting refinement

### Milestone 2 -- Crawl Quality
- URL normalization improvements
- query-shape caps per path
- path-depth caps
- crawl stability guardrails

### Milestone 3 -- SEO Auditing
- metadata checks
- canonical checks
- status code & redirect analysis
- internal linking signals
- initial SEO reporting layer ✅

### Milestone 4 -- AI Crawler Optimization
- robots.txt analysis ✅
- sitemap health checks ✅
- JS accessibility signals ✅
- initial AI readiness reporting layer ✅

### Milestone 5 -- Reporting & Developer Experience
- report layout improvements ✅
- CLI usability improvements ✅
- packaging/version metadata alignment ✅
- initial reporting polish layer integrated ✅

## Target Outcome

A Windows-first CLI tool capable of:
- crawling and analyzing websites
- detecting structural SEO issues
- identifying duplicate content clusters
- evaluating AI crawler accessibility
- generating structured audit reports


### Milestone 6 -- Packaging & Release Prep
- pyproject.toml packaging metadata ✅
- module entrypoint (`python -m site_inspector`) ✅
- console script metadata (`site-inspector`) ✅
- install documentation ✅


### Milestone 7 -- Public Packaging & Release
- release checklist (`RELEASING.md`) ✅
- build metadata enrichment (`pyproject.toml`) ✅
- source distribution pruning (`MANIFEST.in`) ✅
- package build validation (`python -m build`) ✅
- metadata validation (`twine check`) ✅
- runner packaging checks ✅
