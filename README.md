
# CrawlLens

CrawlLens is a CLI tool for crawling websites and generating technical audit reports.

## Features

- Concurrent crawler
- Host throttling + retries
- Resume runs
- URL normalization
- Lighthouse sampling
- Playwright analysis
- Run diffing
- Template clustering

## Commands

Run crawl

python site_audit.py run https://example.com

Run playwright audit

python site_audit.py playwright https://example.com

Diff runs

python site_audit.py diff runs/runA runs/runB

## Template Clustering

Pages are grouped by URL structure.

Example

/blog/post-1
/blog/post-2

→ template

/blog/*

This helps large-site analysis and sampling.
