# Contributing to Site Inspector

Thank you for your interest in contributing. This document covers how to set up a development environment, run tests, and contribute code or fixes.

---

## Setup

```bash
git clone https://github.com/Mark2Mac/site-inspector.git
cd site-inspector

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

For MCP server development:

```bash
pip install -e ".[dev,mcp]"
```

---

## Running tests

```bash
# All tests (fast, no network, no browser)
pytest -q

# With verbose output
pytest -vv

# Specific module
pytest tests/test_graph.py -v
pytest tests/test_html_report.py -v
pytest tests/test_mcp_tools.py -v
```

The test suite is designed to run offline. No network requests are made during normal test runs. Lighthouse and Playwright tests require the full dependency stack and are controlled by the CLI.

---

## Project structure

Key modules:

| File | Responsibility |
|---|---|
| `cli.py` | Entry point, command dispatch, output assembly |
| `crawl.py` | Concurrent BFS crawler, robots.txt compliance |
| `graph.py` | Link graph analysis (PageRank, HITS, orphans, SCCs) |
| `html_report.py` | Self-contained HTML report generation |
| `mcp_server.py` | MCP server — AI assistant tool exposure |
| `diffing.py` | Before/after run comparison |
| `seo_audit.py` | SEO signal extraction |
| `ai_audit.py` | AI crawler readiness |
| `duplicates.py` | DOM fingerprint clustering |
| `reporting.py` | Markdown report generation |

---

## Adding a new analysis layer

Site Inspector is structured around independent audit layers that each produce a dict, which is assembled into `run_obj` at the end of `cmd_run`.

To add a new layer:

1. Create `site_inspector/my_layer.py` with a function `analyze_my_thing(crawl, posture) -> Dict[str, Any]`
2. The return dict should include an `"issues"` list — each issue has `code`, `severity` (`high`/`medium`/`low`), `label`, `count`, `examples`
3. Import and call it in `cli.py:cmd_run`, store under `run_obj["my_layer"]`
4. Feed `run_obj["my_layer"]` into `_build_priority_findings()` in `reporting.py`
5. Add a section in `build_run_md()` and `build_run_html()` to render it
6. Write tests in `tests/test_my_layer.py`

Issues in the `"issues"` list are automatically picked up by the priority findings section of every report.

---

## Commit style

- Short imperative subject line: `Add graph diff to diffing module`
- No ticket prefixes required
- Keep commits focused — one logical change per commit
- Do not amend published commits

---

## Pull requests

- Open against `main`
- Include a brief description of what changed and why
- All tests must pass: `pytest -q`
- New features should include new tests

---

## Git identity for public repos

Use a no-reply GitHub email for public contributions:
`YourUsername@users.noreply.github.com`

Configure locally:

```bash
git config user.email "YourUsername@users.noreply.github.com"
```
