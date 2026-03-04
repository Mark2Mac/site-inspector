# Site Inspector Roadmap (Verbose)

This document describes the evolution plan of the project.

---

# Phase 1 — Stable CLI Audit Tool

Status: COMPLETE

Goals achieved:

- Modular architecture
- CLI commands for crawl, posture, lighthouse, playwright, diff
- Windows-compatible subprocess execution
- Reproducible run artifacts
- Markdown reports
- Diff analysis between runs

The system now works end-to-end.

---

# Phase 2 — Scalability (Target: ~500 pages)

Current focus.

Objectives:

1. Parallel crawl workers
2. URL normalization and deduplication
3. Host-based throttling
4. Worker queue architecture
5. Lighthouse concurrency limits
6. Resumeable runs via artifact caching

Expected benefits:

- 3x–6x speed improvement
- stable memory usage
- ability to audit medium-size websites

---

# Phase 3 — Large Site Support (~5000 pages)

Future milestone.

Planned improvements:

Distributed crawling architecture

Task queue abstraction

Smart sampling for Lighthouse

Template detection (group pages by layout)

Playwright heuristics to detect JS-heavy pages

Advanced tech fingerprinting datasets

---

# Phase 4 — AI Crawler Optimization

Long-term vision.

Add analysis specifically designed for:

- ChatGPT
- Gemini
- Claude
- other LLM crawlers

Possible checks:

structured data completeness

semantic HTML structure

content accessibility

LLM-friendly metadata

---

# Phase 5 — Distributed Architecture

Ultimate scalability goal.

Possible features:

multi-machine crawl workers

shared task queue

remote artifact storage

CI integration for regression monitoring