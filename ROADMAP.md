# Site Inspector – Development Roadmap

## Milestone 0 – Stability

Goal: protect the CLI from regressions without introducing flaky tests.

### Acceptance criteria
- pytest passes on Windows
- tests do not depend on live sites
- tests validate `run` and `diff`
- `run.json` top-level schema is checked
- duplicate summary block remains present in run output

### Notes
For stability, the first test layer uses cached resume artifacts instead of full
network collection. Full live-site checks remain manual smoke tests.
