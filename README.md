# Site Inspector

Site Inspector is a CLI tool to audit websites and generate structured reports about:

- Site structure
- Technologies used
- Lighthouse performance metrics
- JavaScript-rendered content (Playwright)
- Differences between site snapshots

The project is currently **Windows-first** and optimized for developer workflows.

---

# Core Commands

Run full audit:

python site_audit.py run https://example.com

Render JS with browser:

python site_audit.py playwright https://example.com

Compare two runs:

python site_audit.py diff runs/runA runs/runB --out diffs/result

---

# Output Structure

inspect_<host>_<timestamp>/

    run.json
    run.md
    pages.json
    posture.json
    lighthouse/
    playwright/
    raw/

---

# Architecture

site_audit.py – CLI entrypoint

site_inspector/

    cli.py
    crawl.py
    posture.py
    lighthouse.py
    playwright_audit.py
    diffing.py
    reporting.py
    utils.py

---

# Verified Pipeline

The following workflow has been validated:

python site_audit.py run
python site_audit.py playwright
python site_audit.py run --out runs/runA
python site_audit.py run --out runs/runB
python site_audit.py diff runs/runA runs/runB

---

# Project Goals

- deterministic runs
- reproducible artifacts
- CI-friendly
- scalable architecture