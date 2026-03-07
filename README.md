# Site Inspector

Site Inspector is a **Windows‑first CLI tool for technical website
auditing**.

The project focuses on:

-   structural website analysis
-   duplicate content detection
-   SEO signal auditing
-   AI crawler accessibility evaluation

## Example Usage

Run a crawl:

    python site_audit.py run https://example.com --max-pages 5

Run Playwright analysis:

    python site_audit.py playwright https://example.com

Compare two crawls:

    python site_audit.py diff runs/runA runs/runB

## Output

Each run generates:

-   `run.json` -- machine‑readable report
-   `run.md` -- human‑readable audit

Diff runs generate:

-   `diff.json`
-   `diff.md`

## Development Model

The project follows a **milestone‑based roadmap** to avoid fragmented
development.

Key priorities:

1.  reliability of crawling
2.  duplicate detection accuracy
3.  SEO signal analysis
4.  AI crawler optimization

See:

`ROADMAP.md` for development plan\
`AI_INSTRUCTIONS.md` for AI collaboration rules


## Testing

Use deterministic CLI regression tests on Windows:

```powershell
py -m pytest -q
py -m pytest -vv
```

For manual smoke checks:

```powershell
py site_audit.py run https://www.dedicatodesign.com --max-pages 5 --skip-playwright --out runs\golden
py site_audit.py run https://www.dedicatodesign.com --max-pages 5 --skip-playwright --out runs\candidate
py site_audit.py diff runs\golden runs\candidate --out diffs\golden_vs_candidate
```

`diff` now accepts either a run directory containing `run.json` or the `run.json` file directly, and returns a clearer error when the path is wrong.

## Diagnostics

By default, common CLI failures are rendered as short human-readable errors instead of Python tracebacks.

Set `SITE_INSPECTOR_DEBUG=1` to keep full tracebacks during local debugging.

