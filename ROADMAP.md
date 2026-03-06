# Site Inspector -- Development Roadmap

## Completed

-   A1--A6: Core crawler foundation
-   B0--B2: Analysis pipeline
-   B3: Duplicate detection (initial version)

## Current Focus

### Milestone 2 -- Crawl Quality

Improve crawl robustness without breaking the stabilized CLI:
- stronger URL normalization guardrails
- query-shape caps per path to reduce crawl explosion
- cleaner expected-failure handling in the PowerShell runner

## Milestones

### Milestone 0 -- Stability

H1: CLI regression tests\
H2: Golden output tests

### Milestone 1 -- Duplicate Detection

B3 hardening\
B3 validation pass\
B3 reporting refinement

### Milestone 2 -- Crawl Quality

URL normalization improvements\
Retry/timeout handling\
Crawl stability

### Milestone 3 -- SEO Auditing

Metadata checks\
Status code & redirect analysis\
Internal linking signals

### Milestone 4 -- AI Crawler Optimization

Robots.txt analysis\
Sitemap health checks\
JS accessibility signals

### Milestone 5 -- Reporting & Developer Experience

Report layout improvements\
CLI usability improvements\
Packaging and versioning

## Target Outcome

A Windows‑first CLI tool capable of:

-   crawling and analyzing websites
-   detecting structural SEO issues
-   identifying duplicate content clusters
-   evaluating AI crawler accessibility
-   generating structured audit reports
