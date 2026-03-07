from __future__ import annotations

from site_inspector.diffing import render_diff_md
from site_inspector.reporting import build_run_md


def test_build_run_md_contains_polished_sections() -> None:
    run = {
        "version": "0.7.0",
        "generated_at": "2026-03-07T00:00:00Z",
        "target_url": "https://example.com",
        "host": "example.com",
        "crawl": {"pages": [{"url": "https://example.com/"}], "method": {"sitemap_used": False, "max_pages": 5}, "errors": []},
        "quality": {"pages_tested": 1, "pages_failed": 0, "passed": True, "results": []},
        "duplicates": {"duplicate_group_count": 1, "validation": {"actionable_groups": 1}},
        "seo": {"pages_analyzed": 1, "issues": [{"label": "Missing title tags", "severity": "high", "count": 1, "examples": ["https://example.com/"]}]},
        "ai": {"pages_analyzed": 1, "issues": [{"label": "Missing robots.txt", "severity": "high", "count": 1, "examples": ["https://example.com/"]}]},
        "timings": {"crawl_s": 0.1, "posture_s": 0.1, "lighthouse_s": 0.1, "total_s": 0.3},
    }

    md = build_run_md(run)
    assert "## Executive summary" in md
    assert "## Priority findings" in md
    assert "## Artifacts" in md


def test_render_diff_md_contains_executive_summary() -> None:
    diff = {
        "version": "0.7.0",
        "generated_at": "2026-03-07T00:00:00Z",
        "passed": True,
        "fail_reasons": [],
        "runA": {"dir": "runs/a", "generated_at": "2026-03-07T00:00:00Z", "target_url": "https://example.com"},
        "runB": {"dir": "runs/b", "generated_at": "2026-03-07T00:01:00Z", "target_url": "https://example.com"},
        "pages": {"added": ["https://example.com/new"], "removed": [], "unchanged": []},
        "third_parties": {"added": [], "removed": [], "allowlist_used": False},
        "tech": {"wappalyzer": {"added": [], "removed": []}, "builtwith": {"added": [], "removed": []}},
        "quality": {"available": True, "summary": {"runA_passed": True, "runB_passed": True, "runA_pages_failed": 0, "runB_pages_failed": 0}, "regressions": []},
        "extractability": None,
    }

    md = render_diff_md(diff)
    assert "## Executive summary" in md
