# CrawlLens Roadmap

## Status legend
- Done
- In progress
- Planned
- Needs hardening

---

## Phase A — Crawl stability

### A1 — Basic crawl engine
**Status:** Done

### A2 — Split worker pools
**Status:** Done

### A3 — Host throttling + retries
**Status:** Done

### A4 — Resume + per-page cache
**Status:** Done

### A5 — URL normalization guardrails
**Status:** Done  
**Note:** implemented, previously caused regression, now stabilized

### A6 — Smarter Lighthouse targeting / sampling
**Status:** Done

---

## Phase B — Site structure intelligence

### B0 — URL-based template clustering
**Status:** Done

### B1 — DOM fingerprint clustering
**Status:** Done  
**Status note:** working, but still needs quality validation on broader sites

### B2 — Template-aware Lighthouse sampling
**Status:** Done  
**Status note:** working after CLI integration fix

### B3 — Duplicate candidate detection
**Status:** Needs hardening  
**Reason:** concept added, but integration quality and confidence are not yet strong enough to treat as fully complete

---

## Phase B.5 — Hardening layer

### H1 — CLI regression tests
**Status:** Planned

### H2 — Golden file tests for `run.json`, `run.md`, `diff.json`, `diff.md`
**Status:** Planned

### H3 — Safer report integration boundaries
**Status:** Planned

### H4 — Feature flags for experimental analysis blocks
**Status:** Planned

### H5 — Duplicate detection validation pass
**Status:** Planned

### H6 — DOM clustering validation pass
**Status:** Planned

---

## Phase C — SEO + AI analysis

### C1 — Structured data extraction
**Status:** Planned

### C2 — Core SEO issue summary
**Status:** Planned

### C3 — Heading hierarchy and semantic structure checks
**Status:** Planned

### C4 — Canonical / indexability / robots consistency checks
**Status:** Planned

### C5 — AI crawler readiness layer
**Status:** Planned

### C6 — LLM discoverability / machine-readable site signals
**Status:** Planned

---

## Phase D — Graph and template intelligence

### D1 — Internal link graph
**Status:** Planned

### D2 — Crawl depth analysis
**Status:** Planned

### D3 — Template-level rollups
**Status:** Planned

### D4 — Representative-page scoring
**Status:** Planned

### D5 — Better duplicate / near-duplicate classification
**Status:** Planned

---

## Phase E — Productization

### E1 — Installable package / entrypoint cleanup
**Status:** Planned

### E2 — Config files / profiles
**Status:** Planned

### E3 — HTML report output
**Status:** Planned

### E4 — Public repo hardening
**Status:** Planned

### E5 — Release workflow
**Status:** Planned

---

## Recommended next step

The next step should **not** be another major feature by default.

The best next step is:

### H1 — CLI regression tests
Why:
- recent regressions came from integration, not from idea quality
- the current working baseline must be protected
- future patches will be safer and faster once a regression net exists

---

## Completion summary

### Done
- A1
- A2
- A3
- A4
- A5
- A6
- B0
- B1
- B2

### Partially done / needs hardening
- B3

### Not started
- H1+
- C1+
- D1+
- E1+

---

## Strategic note

The project should now prioritize:

**hardening > expansion**

Adding more intelligence before protecting the working CLI will likely create unstable progress.
