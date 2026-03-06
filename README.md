# Site Inspector

Site Inspector is a Windows-first CLI tool for technical website auditing.

## Testing

Milestone 0 regression tests are intentionally lightweight and deterministic.

They:
- use a local fixture site served by Python's built-in HTTP server
- seed cached `pages.json`, `posture.json`, and `quality_summary.json`
- execute `run --resume --skip-playwright` so tests validate CLI/report generation
  without depending on external network, Lighthouse, or Playwright

Run:

```powershell
py -m pytest
```
