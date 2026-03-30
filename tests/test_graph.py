"""Tests for site_inspector.graph — link-graph analysis layer."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from site_inspector.graph import (
    analyze_graph,
    build_graph,
    _orphan_pages,
    _dead_ends,
    _unreachable,
    _strongly_connected_components,
    _articulation_points,
    _pagerank,
    _crawl_depth_bfs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pages(*links: tuple[str, list[str]]) -> list[dict]:
    """Build a minimal pages list: (url, [outgoing_url, ...]) → page dicts."""
    return [
        {
            "url": url,
            "title": url.split("/")[-1] or "root",
            "status_code": 200,
            "outgoing_internal_links": outs,
        }
        for url, outs in links
    ]


def _crawl(target: str, pages: list[dict]) -> dict:
    return {"target_url": target, "pages": pages}


# ---------------------------------------------------------------------------
# build_graph
# ---------------------------------------------------------------------------

class TestBuildGraph:
    def test_empty_crawl(self):
        g = build_graph({"pages": []})
        assert g.number_of_nodes() == 0
        assert g.number_of_edges() == 0

    def test_single_page(self):
        pages = _pages(("https://x.com/", []))
        g = build_graph({"pages": pages})
        assert g.number_of_nodes() == 1
        assert g.number_of_edges() == 0

    def test_simple_chain(self):
        pages = _pages(
            ("https://x.com/", ["https://x.com/about"]),
            ("https://x.com/about", ["https://x.com/contact"]),
            ("https://x.com/contact", []),
        )
        g = build_graph({"pages": pages})
        assert g.number_of_nodes() == 3
        assert g.number_of_edges() == 2

    def test_no_self_loops(self):
        pages = _pages(("https://x.com/", ["https://x.com/"]))
        g = build_graph({"pages": pages})
        assert g.number_of_edges() == 0

    def test_external_links_excluded(self):
        pages = _pages(
            ("https://x.com/", ["https://x.com/about", "https://external.com/page"]),
            ("https://x.com/about", []),
        )
        g = build_graph({"pages": pages})
        # external.com is not a crawled node → edge not added
        assert g.number_of_edges() == 1


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

class TestOrphanPages:
    def test_no_orphans(self):
        pages = _pages(
            ("https://x.com/", ["https://x.com/about"]),
            ("https://x.com/about", []),
        )
        g = build_graph({"pages": pages})
        assert _orphan_pages(g, "https://x.com/") == []

    def test_detects_orphan(self):
        pages = _pages(
            ("https://x.com/", ["https://x.com/about"]),
            ("https://x.com/about", []),
            ("https://x.com/orphan", []),
        )
        g = build_graph({"pages": pages})
        assert "https://x.com/orphan" in _orphan_pages(g, "https://x.com/")

    def test_root_not_flagged_as_orphan(self):
        pages = _pages(("https://x.com/", []))
        g = build_graph({"pages": pages})
        orphans = _orphan_pages(g, "https://x.com/")
        assert "https://x.com/" not in orphans


class TestDeadEnds:
    def test_no_dead_ends(self):
        pages = _pages(
            ("https://x.com/", ["https://x.com/about"]),
            ("https://x.com/about", ["https://x.com/"]),
        )
        g = build_graph({"pages": pages})
        assert _dead_ends(g) == []

    def test_detects_dead_end(self):
        pages = _pages(
            ("https://x.com/", ["https://x.com/leaf"]),
            ("https://x.com/leaf", []),
        )
        g = build_graph({"pages": pages})
        assert "https://x.com/leaf" in _dead_ends(g)


class TestUnreachable:
    def test_all_reachable(self):
        pages = _pages(
            ("https://x.com/", ["https://x.com/a", "https://x.com/b"]),
            ("https://x.com/a", []),
            ("https://x.com/b", []),
        )
        g = build_graph({"pages": pages})
        assert _unreachable(g, "https://x.com/") == []

    def test_orphan_is_unreachable(self):
        pages = _pages(
            ("https://x.com/", ["https://x.com/a"]),
            ("https://x.com/a", []),
            ("https://x.com/orphan", []),
        )
        g = build_graph({"pages": pages})
        u = _unreachable(g, "https://x.com/")
        assert "https://x.com/orphan" in u
        assert "https://x.com/a" not in u


class TestSCC:
    def test_no_scc_in_dag(self):
        pages = _pages(
            ("https://x.com/", ["https://x.com/a"]),
            ("https://x.com/a", ["https://x.com/b"]),
            ("https://x.com/b", []),
        )
        g = build_graph({"pages": pages})
        assert _strongly_connected_components(g) == []

    def test_detects_scc(self):
        pages = _pages(
            ("https://x.com/", ["https://x.com/a"]),
            ("https://x.com/a", ["https://x.com/"]),  # cycle
            ("https://x.com/b", []),
        )
        g = build_graph({"pages": pages})
        sccs = _strongly_connected_components(g)
        assert len(sccs) == 1
        scc_urls = set(sccs[0])
        assert "https://x.com/" in scc_urls
        assert "https://x.com/a" in scc_urls


class TestPageRank:
    def test_pagerank_keys(self):
        pages = _pages(
            ("https://x.com/", ["https://x.com/a"]),
            ("https://x.com/a", ["https://x.com/"]),
        )
        g = build_graph({"pages": pages})
        pr = _pagerank(g)
        assert set(pr.keys()) == {"https://x.com/", "https://x.com/a"}

    def test_pagerank_well_linked_page_ranks_higher(self):
        # hub points to b and c; only b points back to hub
        pages = _pages(
            ("https://x.com/", ["https://x.com/a", "https://x.com/b"]),
            ("https://x.com/a", ["https://x.com/"]),
            ("https://x.com/b", []),
            ("https://x.com/orphan", []),
        )
        g = build_graph({"pages": pages})
        pr = _pagerank(g)
        # root is linked back from /a — should outrank orphan
        assert pr["https://x.com/"] > pr["https://x.com/orphan"]

    def test_empty_graph(self):
        g = build_graph({"pages": []})
        pr = _pagerank(g)
        assert pr == {}


class TestCrawlDepth:
    def test_root_depth_zero(self):
        pages = _pages(
            ("https://x.com/", ["https://x.com/a"]),
            ("https://x.com/a", []),
        )
        g = build_graph({"pages": pages})
        depths = _crawl_depth_bfs(g, "https://x.com/")
        assert depths["https://x.com/"] == 0
        assert depths["https://x.com/a"] == 1

    def test_missing_root_returns_empty(self):
        pages = _pages(("https://x.com/a", []))
        g = build_graph({"pages": pages})
        depths = _crawl_depth_bfs(g, "https://x.com/")
        assert depths == {}


# ---------------------------------------------------------------------------
# analyze_graph (integration)
# ---------------------------------------------------------------------------

class TestAnalyzeGraph:
    def test_empty_crawl_returns_zero_nodes(self):
        result = analyze_graph({"target_url": "https://x.com/", "pages": []})
        assert result["nodes"] == 0
        assert result["edges"] == 0

    def test_single_page_no_issues(self):
        crawl = _crawl("https://x.com/", _pages(("https://x.com/", [])))
        result = analyze_graph(crawl)
        assert result["nodes"] == 1
        assert result["edges"] == 0
        assert result["orphan_pages"]["count"] == 0
        assert result["dead_ends"]["count"] == 1  # single page with no outbound

    def test_full_graph_has_expected_keys(self):
        pages = _pages(
            ("https://x.com/", ["https://x.com/a", "https://x.com/b"]),
            ("https://x.com/a", ["https://x.com/"]),
            ("https://x.com/b", []),
            ("https://x.com/orphan", []),
        )
        crawl = _crawl("https://x.com/", pages)
        result = analyze_graph(crawl)

        for key in ("nodes", "edges", "density", "avg_depth", "max_depth",
                    "depth_distribution", "pagerank", "hits",
                    "orphan_pages", "dead_ends", "deep_pages",
                    "unreachable", "strongly_connected_components",
                    "articulation_points", "issues"):
            assert key in result, f"Missing key: {key}"

    def test_orphan_flagged_as_issue(self):
        pages = _pages(
            ("https://x.com/", ["https://x.com/a"]),
            ("https://x.com/a", []),
            ("https://x.com/orphan", []),
        )
        crawl = _crawl("https://x.com/", pages)
        result = analyze_graph(crawl)
        issue_codes = {i["code"] for i in result["issues"]}
        assert "orphan_pages" in issue_codes

    def test_circular_links_detected_as_scc(self):
        pages = _pages(
            ("https://x.com/", ["https://x.com/a"]),
            ("https://x.com/a", ["https://x.com/"]),
        )
        crawl = _crawl("https://x.com/", pages)
        result = analyze_graph(crawl)
        assert result["strongly_connected_components"]["count"] >= 1
        assert result["strongly_connected_components"]["largest_size"] == 2

    def test_pagerank_top_is_sorted_descending(self):
        pages = _pages(
            ("https://x.com/", ["https://x.com/a", "https://x.com/b", "https://x.com/c"]),
            ("https://x.com/a", ["https://x.com/"]),
            ("https://x.com/b", ["https://x.com/"]),
            ("https://x.com/c", []),
        )
        crawl = _crawl("https://x.com/", pages)
        result = analyze_graph(crawl)
        top = result["pagerank"]["top"]
        scores = [e["score"] for e in top]
        assert scores == sorted(scores, reverse=True)

    def test_depth_distribution_keys_are_ints(self):
        pages = _pages(
            ("https://x.com/", ["https://x.com/a"]),
            ("https://x.com/a", ["https://x.com/b"]),
            ("https://x.com/b", []),
        )
        crawl = _crawl("https://x.com/", pages)
        result = analyze_graph(crawl)
        for k in result["depth_distribution"]:
            assert isinstance(k, int), f"Expected int key, got {type(k)}: {k}"
