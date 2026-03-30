"""Tests for site_inspector.mcp_server — MCP tool functions.

Tests exercise the data-formatting and file-loading helpers without
making real network requests or running a real MCP server.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# Skip entire module if `mcp` package is not installed
pytest.importorskip("mcp", reason="mcp package not installed; install with: pip install 'site-inspector[mcp]'")

from site_inspector.mcp_server import (
    _fmt_run_summary,
    _fmt_diff_summary,
    load_site_run,
    site_graph_insights,
    diff_site_runs,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

MINIMAL_RUN = {
    "version": "0.8.0",
    "generated_at": "2026-03-30T10:00:00Z",
    "target_url": "https://example.com/",
    "host": "example.com",
    "crawl": {
        "target_url": "https://example.com/",
        "pages": [
            {"url": "https://example.com/", "title": "Home", "status_code": 200, "outgoing_internal_links": ["https://example.com/about"]},
            {"url": "https://example.com/about", "title": "About", "status_code": 200, "outgoing_internal_links": []},
            {"url": "https://example.com/orphan", "title": "Orphan", "status_code": 200, "outgoing_internal_links": []},
        ],
        "errors": [],
    },
    "posture": {
        "http": {"url_final": "https://example.com/", "status_code": 200},
        "tls": {"protocol": "TLSv1.3"},
        "fingerprinting": {"third_party_domains": [], "tech": {}},
    },
    "quality": {"pages_tested": 0, "pages_failed": 0, "passed": True, "results": []},
    "seo": {
        "pages_analyzed": 3,
        "issues": [{"code": "missing_title", "severity": "high", "label": "Missing titles", "count": 1, "examples": ["https://example.com/orphan"]}],
    },
    "ai": {"pages_analyzed": 3, "robots": {"present": True}, "sitemap": {"present": False, "url_count": 0}, "issues": []},
    "graph": {
        "nodes": 3, "edges": 1, "density": 0.17, "avg_depth": 0.67, "max_depth": 1,
        "depth_distribution": {0: 1, 1: 1},
        "pagerank": {"top": [{"url": "https://example.com/", "score": 0.4}, {"url": "https://example.com/about", "score": 0.3}]},
        "hits": {"top_hubs": [], "top_authorities": []},
        "orphan_pages": {"count": 1, "urls": ["https://example.com/orphan"]},
        "dead_ends": {"count": 2, "urls": ["https://example.com/about", "https://example.com/orphan"]},
        "unreachable": {"count": 1, "urls": ["https://example.com/orphan"]},
        "articulation_points": {"count": 0, "urls": []},
        "strongly_connected_components": {"count": 0, "largest_size": 0, "components": []},
        "deep_pages": {"count": 0, "threshold_clicks": 3, "urls": []},
        "issues": [
            {"code": "orphan_pages", "severity": "high", "label": "Orphan pages", "count": 1, "examples": ["https://example.com/orphan"]},
        ],
    },
    "duplicates": {"duplicate_group_count": 0, "validation": {"actionable_groups": 0}},
    "timings": {"total_s": 5.2},
}

MINIMAL_DIFF = {
    "version": "0.8.0",
    "generated_at": "2026-03-30T11:00:00Z",
    "runA": {"target_url": "https://example.com/", "generated_at": "2026-03-29T10:00:00Z"},
    "runB": {"target_url": "https://example.com/", "generated_at": "2026-03-30T10:00:00Z"},
    "passed": True,
    "fail_reasons": [],
    "pages": {"added": ["https://example.com/new"], "removed": [], "unchanged": ["https://example.com/"]},
    "quality": {"available": True, "regressions": [], "summary": {}},
    "tech": {"wappalyzer": {"added": [], "removed": [], "unchanged": []}, "builtwith": {"added": [], "removed": [], "unchanged": []}},
    "third_parties": {"added": [], "removed": [], "unchanged": []},
}


# ---------------------------------------------------------------------------
# _fmt_run_summary
# ---------------------------------------------------------------------------

class TestFmtRunSummary:
    def test_contains_host(self, tmp_path):
        out = _fmt_run_summary(MINIMAL_RUN, tmp_path)
        assert "example.com" in out

    def test_contains_crawl_section(self, tmp_path):
        out = _fmt_run_summary(MINIMAL_RUN, tmp_path)
        assert "CRAWL" in out

    def test_contains_graph_section(self, tmp_path):
        out = _fmt_run_summary(MINIMAL_RUN, tmp_path)
        assert "LINK GRAPH" in out or "GRAPH" in out

    def test_contains_issue_summary(self, tmp_path):
        out = _fmt_run_summary(MINIMAL_RUN, tmp_path)
        assert "SEO" in out or "ISSUE" in out

    def test_contains_output_paths(self, tmp_path):
        out = _fmt_run_summary(MINIMAL_RUN, tmp_path)
        assert "run.html" in out or str(tmp_path) in out

    def test_status_no_high_issues(self, tmp_path):
        run = {**MINIMAL_RUN, "seo": {"pages_analyzed": 3, "issues": []}, "graph": {**MINIMAL_RUN["graph"], "issues": []}}
        out = _fmt_run_summary(run, tmp_path)
        assert "No high-severity" in out or "✅" in out

    def test_status_with_high_issues(self, tmp_path):
        out = _fmt_run_summary(MINIMAL_RUN, tmp_path)
        # Fixture has high-severity SEO and graph issues
        assert "⚠" in out or "high-severity" in out


# ---------------------------------------------------------------------------
# _fmt_diff_summary
# ---------------------------------------------------------------------------

class TestFmtDiffSummary:
    def test_contains_pass_status(self, tmp_path):
        out = _fmt_diff_summary(MINIMAL_DIFF, tmp_path)
        assert "PASS" in out

    def test_contains_fail_status_on_failure(self, tmp_path):
        diff = {**MINIMAL_DIFF, "passed": False, "fail_reasons": ["Quality regression on 1 page"]}
        out = _fmt_diff_summary(diff, tmp_path)
        assert "FAIL" in out

    def test_page_changes_counts(self, tmp_path):
        out = _fmt_diff_summary(MINIMAL_DIFF, tmp_path)
        assert "Added: 1" in out

    def test_contains_reports_generated(self, tmp_path):
        out = _fmt_diff_summary(MINIMAL_DIFF, tmp_path)
        assert "diff.html" in out or "diff.json" in out


# ---------------------------------------------------------------------------
# load_site_run (file I/O)
# ---------------------------------------------------------------------------

class TestLoadSiteRun:
    def test_loads_run_json(self, tmp_path):
        run_json = tmp_path / "run.json"
        run_json.write_text(json.dumps(MINIMAL_RUN), encoding="utf-8")
        result = load_site_run(str(tmp_path))
        assert "example.com" in result
        assert "CRAWL" in result

    def test_missing_dir_returns_error(self, tmp_path):
        result = load_site_run(str(tmp_path / "nonexistent"))
        assert "Error" in result or "error" in result.lower()

    def test_accepts_run_json_path_directly(self, tmp_path):
        run_json = tmp_path / "run.json"
        run_json.write_text(json.dumps(MINIMAL_RUN), encoding="utf-8")
        result = load_site_run(str(run_json))
        assert "example.com" in result


# ---------------------------------------------------------------------------
# site_graph_insights (file I/O)
# ---------------------------------------------------------------------------

class TestSiteGraphInsights:
    def test_structure_section_present(self, tmp_path):
        run_json = tmp_path / "run.json"
        run_json.write_text(json.dumps(MINIMAL_RUN), encoding="utf-8")
        result = site_graph_insights(str(tmp_path))
        assert "STRUCTURE" in result

    def test_orphan_section_present_when_orphans_exist(self, tmp_path):
        run_json = tmp_path / "run.json"
        run_json.write_text(json.dumps(MINIMAL_RUN), encoding="utf-8")
        result = site_graph_insights(str(tmp_path))
        assert "ORPHAN" in result

    def test_pagerank_section_present(self, tmp_path):
        run_json = tmp_path / "run.json"
        run_json.write_text(json.dumps(MINIMAL_RUN), encoding="utf-8")
        result = site_graph_insights(str(tmp_path))
        assert "PAGERANK" in result

    def test_recomputes_graph_if_missing(self, tmp_path):
        run = {**MINIMAL_RUN}
        del run["graph"]  # type: ignore[misc]
        run_json = tmp_path / "run.json"
        run_json.write_text(json.dumps(run), encoding="utf-8")
        result = site_graph_insights(str(tmp_path))
        # Should still work by re-computing from crawl data
        assert "STRUCTURE" in result

    def test_missing_dir_returns_error(self, tmp_path):
        result = site_graph_insights(str(tmp_path / "nonexistent"))
        assert "Error" in result or "error" in result.lower()


# ---------------------------------------------------------------------------
# diff_site_runs (file I/O)
# ---------------------------------------------------------------------------

class TestDiffSiteRuns:
    def test_diff_pass(self, tmp_path):
        run_a = tmp_path / "run_a"
        run_b = tmp_path / "run_b"
        run_a.mkdir()
        run_b.mkdir()
        (run_a / "run.json").write_text(json.dumps(MINIMAL_RUN), encoding="utf-8")
        (run_b / "run.json").write_text(json.dumps(MINIMAL_RUN), encoding="utf-8")
        out = tmp_path / "diff_out"
        result = diff_site_runs(str(run_a), str(run_b), out_dir=str(out))
        assert "PASS" in result or "Page" in result

    def test_diff_writes_files(self, tmp_path):
        run_a = tmp_path / "run_a"
        run_b = tmp_path / "run_b"
        run_a.mkdir()
        run_b.mkdir()
        (run_a / "run.json").write_text(json.dumps(MINIMAL_RUN), encoding="utf-8")
        (run_b / "run.json").write_text(json.dumps(MINIMAL_RUN), encoding="utf-8")
        out = tmp_path / "diff_out"
        diff_site_runs(str(run_a), str(run_b), out_dir=str(out))
        assert (out / "diff.json").exists()
        assert (out / "diff.md").exists()

    def test_diff_missing_run_returns_error(self, tmp_path):
        result = diff_site_runs(
            str(tmp_path / "nonexistent_a"),
            str(tmp_path / "nonexistent_b"),
        )
        assert "Error" in result or "error" in result.lower()
