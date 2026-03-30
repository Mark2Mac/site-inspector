"""Tests for site_inspector.html_report — self-contained HTML report generation."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from site_inspector.html_report import build_run_html, build_diff_html

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

CRAWL_PAGES = [
    {"url": "https://example.com/", "title": "Home", "status_code": 200, "redirect_count": 0, "h1_count": 1, "internal_link_count": 8, "outgoing_internal_links": ["https://example.com/about", "https://example.com/blog"], "dom_fingerprint": "abc"},
    {"url": "https://example.com/about", "title": "About", "status_code": 200, "redirect_count": 0, "h1_count": 1, "internal_link_count": 3, "outgoing_internal_links": ["https://example.com/"], "dom_fingerprint": "def"},
    {"url": "https://example.com/blog", "title": "Blog", "status_code": 200, "redirect_count": 0, "h1_count": 1, "internal_link_count": 5, "outgoing_internal_links": ["https://example.com/blog/post1"], "dom_fingerprint": "ghi"},
    {"url": "https://example.com/blog/post1", "title": None, "status_code": 200, "redirect_count": 0, "h1_count": 0, "internal_link_count": 0, "outgoing_internal_links": [], "dom_fingerprint": "jkl"},
    {"url": "https://example.com/orphan", "title": "Orphan", "status_code": 200, "redirect_count": 0, "h1_count": 0, "internal_link_count": 0, "outgoing_internal_links": [], "dom_fingerprint": "mno"},
]

RUN_OBJ = {
    "version": "0.8.0",
    "generated_at": "2026-03-30T10:00:00Z",
    "target_url": "https://example.com/",
    "host": "example.com",
    "crawl": {
        "target_url": "https://example.com/",
        "pages": CRAWL_PAGES,
        "errors": [{"url": "https://example.com/broken", "status_code": 404, "error": "Not found", "stage": "links"}],
    },
    "posture": {
        "tls": {"protocol": "TLSv1.3", "cipher": ["ECDHE-RSA-AES256-GCM-SHA384", 256]},
        "http": {"url_final": "https://example.com/", "status_code": 200},
        "fingerprinting": {
            "third_party_domains": ["google-analytics.com", "fonts.googleapis.com"],
            "tech": {"wappalyzer": {"Nginx": "1.20", "Bootstrap": "5.0"}, "builtwith": {}},
        },
    },
    "quality": {
        "pages_tested": 2,
        "pages_failed": 1,
        "passed": False,
        "results": [
            {"url": "https://example.com/", "scores": {"performance": 0.92, "seo": 0.88, "accessibility": 0.79, "best-practices": 0.95}, "budget_eval": {"passed": True}},
            {"url": "https://example.com/blog", "scores": {"performance": 0.55, "seo": 0.71, "accessibility": 0.62, "best-practices": 0.80}, "budget_eval": {"passed": False}},
        ],
    },
    "playwright": None,
    "timings": {"crawl_s": 12.3, "posture_s": 1.1, "lighthouse_s": 45.2, "playwright_s": 0, "total_s": 58.6},
    "duplicates": {
        "duplicate_groups": [{"key": "dom:abc", "count": 2, "method": "dom", "confidence": 0.9, "confidence_bucket": "high", "notes": "", "titles": ["Home", "Home copy"], "page_ids": [0, 1]}],
        "duplicate_group_count": 1, "duplicate_url_count": 2,
        "confidence_buckets": {"high": 1, "medium": 0, "low": 0, "ignored": 0},
        "validation": {"actionable_groups": 1, "manual_review_groups": 0, "manual_review_keys": []},
    },
    "seo": {
        "pages_analyzed": 5,
        "metadata": {"missing_title": {"count": 2}, "duplicate_title_groups": {"count": 0}, "missing_meta_description": {"count": 3}},
        "canonicals": {"missing": {"count": 2}},
        "status": {"non_200": {"count": 0}},
        "internal_linking": {"zero_inlinks": {"count": 1}},
        "issues": [
            {"code": "missing_title", "severity": "high", "label": "Missing title tags", "count": 2, "examples": ["https://example.com/blog/post1"]},
            {"code": "zero_inlinks", "severity": "medium", "label": "Zero internal inlinks", "count": 1, "examples": ["https://example.com/orphan"]},
        ],
    },
    "ai": {
        "pages_analyzed": 5,
        "robots": {"present": True},
        "sitemap": {"present": True, "url_count": 12},
        "js_accessibility": {"pages_js_disabled_readable": 0, "pages_checked": 0},
        "meta_robots": {"noindex_pages": {"count": 0}},
        "issues": [],
    },
    "graph": {
        "nodes": 5, "edges": 4, "density": 0.2, "avg_depth": 1.0, "max_depth": 2,
        "depth_distribution": {0: 1, 1: 2, 2: 1},
        "pagerank": {"top": [
            {"url": "https://example.com/", "score": 0.257347},
            {"url": "https://example.com/about", "score": 0.198226},
            {"url": "https://example.com/blog", "score": 0.198226},
            {"url": "https://example.com/blog/post1", "score": 0.257347},
            {"url": "https://example.com/orphan", "score": 0.088854},
        ]},
        "hits": {
            "top_hubs": [{"url": "https://example.com/", "score": 1.0}],
            "top_authorities": [{"url": "https://example.com/about", "score": 0.5}],
        },
        "orphan_pages": {"count": 1, "urls": ["https://example.com/orphan"]},
        "dead_ends": {"count": 2, "urls": ["https://example.com/blog/post1", "https://example.com/orphan"]},
        "deep_pages": {"count": 0, "threshold_clicks": 3, "urls": []},
        "unreachable": {"count": 1, "urls": ["https://example.com/orphan"]},
        "articulation_points": {"count": 2, "urls": ["https://example.com/", "https://example.com/blog"]},
        "strongly_connected_components": {"count": 1, "largest_size": 2, "components": [["https://example.com/", "https://example.com/about"]]},
        "issues": [
            {"code": "unreachable_pages", "severity": "high", "label": "Pages unreachable from homepage", "count": 1, "examples": ["https://example.com/orphan"]},
            {"code": "orphan_pages", "severity": "high", "label": "Orphan pages (zero inbound internal links)", "count": 1, "examples": ["https://example.com/orphan"]},
            {"code": "dead_end_pages", "severity": "medium", "label": "Dead-end pages", "count": 2, "examples": ["https://example.com/blog/post1"]},
        ],
    },
}

DIFF_OBJ = {
    "version": "0.8.0",
    "generated_at": "2026-03-30T11:00:00Z",
    "runA": {"dir": "runs/runA", "generated_at": "2026-03-29T10:00:00Z", "target_url": "https://example.com/"},
    "runB": {"dir": "runs/runB", "generated_at": "2026-03-30T10:00:00Z", "target_url": "https://example.com/"},
    "passed": False,
    "fail_reasons": ["Quality regression on 1 page"],
    "pages": {"added": ["https://example.com/new-page"], "removed": ["https://example.com/old-page"], "unchanged": ["https://example.com/"]},
    "quality": {
        "available": True,
        "summary": {"runA_passed": True, "runB_passed": False, "runA_pages_failed": 0, "runB_pages_failed": 1},
        "per_page": [],
        "regressions": [{"url": "https://example.com/blog", "reasons": ["performance<0.80"], "deltas": {"performance": -0.37, "seo": 0.0, "accessibility": -0.17, "best-practices": -0.15}}],
    },
    "tech": {
        "wappalyzer": {"added": ["React"], "removed": ["jQuery"], "unchanged": ["Nginx"]},
        "builtwith": {"added": [], "removed": [], "unchanged": []},
    },
    "third_parties": {"added": ["newrelic.com"], "removed": [], "unchanged": ["google-analytics.com"]},
    "extractability": None,
}


# ---------------------------------------------------------------------------
# run HTML
# ---------------------------------------------------------------------------

class TestBuildRunHtml:
    def test_valid_doctype(self):
        html = build_run_html(RUN_OBJ)
        assert html.startswith("<!DOCTYPE html>") or "<!DOCTYPE html>" in html[:50]

    def test_target_host_present(self):
        html = build_run_html(RUN_OBJ)
        assert "example.com" in html

    def test_section_link_graph(self):
        html = build_run_html(RUN_OBJ)
        assert "Link Graph" in html

    def test_section_lighthouse(self):
        html = build_run_html(RUN_OBJ)
        assert "Lighthouse" in html

    def test_section_seo(self):
        html = build_run_html(RUN_OBJ)
        assert "SEO" in html

    def test_section_priority_findings(self):
        html = build_run_html(RUN_OBJ)
        assert "Priority" in html

    def test_branding_footer(self):
        html = build_run_html(RUN_OBJ)
        assert "dedicatodesign.com" in html

    def test_minimum_size(self):
        html = build_run_html(RUN_OBJ)
        assert len(html) > 10_000, f"Expected >10KB, got {len(html)}"

    def test_self_contained_no_external_scripts(self):
        html = build_run_html(RUN_OBJ)
        # Should not reference CDNs for scripts/styles
        for cdn in ("cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com"):
            assert cdn not in html, f"Found external CDN reference: {cdn}"

    def test_seo_issue_labels_present(self):
        html = build_run_html(RUN_OBJ)
        assert "Missing title" in html

    def test_pagerank_scores_present(self):
        html = build_run_html(RUN_OBJ)
        assert "0.257347" in html or "PageRank" in html


# ---------------------------------------------------------------------------
# diff HTML
# ---------------------------------------------------------------------------

class TestBuildDiffHtml:
    def test_valid_doctype(self):
        html = build_diff_html(DIFF_OBJ)
        assert "<!DOCTYPE html>" in html

    def test_diff_report_heading(self):
        html = build_diff_html(DIFF_OBJ)
        assert "Diff" in html

    def test_quality_regressions_section(self):
        html = build_diff_html(DIFF_OBJ)
        assert "Regression" in html or "regression" in html

    def test_page_changes_section(self):
        html = build_diff_html(DIFF_OBJ)
        assert "Page" in html

    def test_branding_footer(self):
        html = build_diff_html(DIFF_OBJ)
        assert "dedicatodesign.com" in html

    def test_minimum_size(self):
        html = build_diff_html(DIFF_OBJ)
        assert len(html) > 3_000, f"Expected >3KB, got {len(html)}"

    def test_added_page_present(self):
        html = build_diff_html(DIFF_OBJ)
        assert "new-page" in html

    def test_removed_page_present(self):
        html = build_diff_html(DIFF_OBJ)
        assert "old-page" in html


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_run(self):
        minimal = {
            "version": "0.8.0",
            "generated_at": "2026-03-30T10:00:00Z",
            "target_url": "https://example.com/",
            "host": "example.com",
            "crawl": {"pages": [], "errors": []},
        }
        html = build_run_html(minimal)
        assert "<!DOCTYPE html>" in html

    def test_none_quality(self):
        run = {**RUN_OBJ, "quality": None}
        html = build_run_html(run)
        assert "<!DOCTYPE html>" in html

    def test_none_graph(self):
        run = {**RUN_OBJ, "graph": None}
        html = build_run_html(run)
        assert "<!DOCTYPE html>" in html

    def test_minimal_diff(self):
        diff = {
            "version": "0.8.0",
            "generated_at": "2026-03-30T11:00:00Z",
            "runA": {"target_url": "https://example.com/"},
            "runB": {"target_url": "https://example.com/"},
            "passed": True,
            "fail_reasons": [],
            "pages": {"added": [], "removed": [], "unchanged": []},
        }
        html = build_diff_html(diff)
        assert "<!DOCTYPE html>" in html
