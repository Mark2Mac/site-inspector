# CrawlLens

CrawlLens is a Windows-first CLI for website crawling, technical inspection, structural clustering, lightweight QA, and run-to-run comparison.

It is designed to answer a practical question:

**How is this site built, how stable is it, how is it structured, and what changed between two inspections?**

---

## Current project status

The project is currently in a **working MVP+ state**.

Based on the latest validated runs, the following commands are working end-to-end:

```bash
python site_audit.py run https://www.dedicatodesign.com --max-pages 5 --skip-playwright
python site_audit.py playwright https://www.dedicatodesign.com --max-pages 3
python site_audit.py run https://www.dedicatodesign.com --skip-playwright --out runs\runA
python site_audit.py run https://www.dedicatodesign.com --skip-playwright --out runs\runB
python site_audit.py diff runs\runA runs\runB --out diffs\runA_vs_runB
```

That means the current baseline is stable enough for:

- crawl execution
- Playwright snapshot/audit execution
- repeatable run generation
- diff generation between runs
- structural reporting at run level

---

## What is already implemented

### Phase A — Crawl stability
- Basic crawl pipeline
- Host throttling
- Retry handling for transient failures
- Split worker pools for network-bound vs heavy tasks
- Resume support
- Per-page cache structure
- URL normalization guardrails
- Smarter Lighthouse targeting / sampling

### Phase B — Structure intelligence
- URL-based template clustering
- DOM fingerprint clustering
- Template-aware Lighthouse sampling
- Initial duplicate candidate detection

### Reporting and workflow
- `run.md` and `run.json`
- `diff.md` and `diff.json`
- Playwright summary output
- Re-runnable local workflow
- Patch-based iterative delivery

---

## What is still missing

The project works, but it is **not finished**.

### High-priority missing pieces
- Stronger automated validation after each patch
- Safer integration discipline for CLI/reporting changes
- Unit tests for core helper modules
- Golden tests for `run.json`, `run.md`, and `diff.json`
- Better duplicate detection precision
- Better DOM clustering quality controls
- More reliable large-site performance baselines
- Cleaner packaging and install flow

### Product-level missing pieces
- Internal link graph
- Structured data extraction
- SEO issue scoring
- AI crawler readiness analysis
- Template-level performance rollups
- HTML report export
- Config profiles
- Public package/release flow

---

## Current architecture direction

CrawlLens is evolving from:

**crawler + report generator**

into:

**site intelligence CLI**

The key shift is that the tool is no longer only collecting URLs.  
It is starting to infer:

- page types
- shared templates
- duplicate candidates
- change sets between runs
- likely representative pages

That is the right direction.  
But the codebase still needs more guardrails before it is ready for public release.

---

## Honest audit of the current state

### What is solid
- The command surface is simple
- The current workflow is reproducible
- Output artifacts are understandable
- The roadmap sequencing has mostly been correct
- Stability first was the right call

### What is fragile
- Some recent steps introduced regressions in `cli.py`
- Some commits were valid conceptually but unsafe operationally
- The project currently depends too much on manual smoke testing
- The reporting layer is becoming more coupled to feature delivery
- Patch quality needs stricter acceptance checks before shipping

### Bottom line
The project is **past prototype**, but **not yet production-grade**.

A fair label would be:

**working experimental CLI with stable core flow and partially hardened analysis layers**

---

## Recommended next focus

Before adding many new features, the smartest next move is:

1. stabilize B3 properly
2. add regression tests for CLI entrypoints and report generation
3. freeze interfaces for `run.json` / `diff.json`
4. then move into SEO / AI audit layers

This matters because new features on top of unstable interfaces create fake progress.

---

## Future collaboration protocol with ChatGPT

For future iterations, ChatGPT should interact with this project in a **strict patch workflow**.

### Required mode
ChatGPT should provide only:
- a short audit of the current state
- the exact next step to implement
- a generated download archive containing only the modified files
- the commit title

### Avoid
ChatGPT should **not**:
- dump full rewritten project code into chat
- rename files unless explicitly requested
- redesign the whole repo without need
- mix multiple unrelated steps into one patch
- claim a patch is safe without respecting the current working baseline

### Expected output format
Each implementation iteration should follow this style:

1. **Commit title**
2. **Download link to `.zip`**
3. Only the files that must overwrite existing project files
4. File names preserved exactly
5. Patch scoped to one step only

### Default operating rule
When uncertain, prefer:
- audit first
- smallest safe patch second

This repository should evolve through **incremental, overwrite-ready patch zips**.

---

## Suggested repository identity

Recommended public-facing name:

**CrawlLens**

Recommended positioning:

**Windows-first site inspection CLI for crawl, structure, diff, and technical audit workflows**

---

## Outputs

Typical outputs:

- `run.md`
- `run.json`
- `diff.md`
- `diff.json`
- `playwright_summary.json`

---

## Current maturity summary

| Area | Status |
|---|---|
| Crawl baseline | Good |
| Retry / throttling | Good |
| Resume / cache | Good |
| Diff workflow | Good |
| Template clustering | Good |
| DOM clustering | Promising but still needs validation |
| Duplicate detection | Early / needs hardening |
| Test coverage | Weak |
| Packaging | Incomplete |
| Public release readiness | Not ready yet |

---

## Near-term goal

Move from:

**working manually validated tool**

to:

**tested, regression-resistant local CLI**

That is the real milestone before public release.
