"""Site link-graph analysis powered by networkx.

Builds a directed graph from crawl data and computes structural metrics:
PageRank, HITS hub/authority, orphan pages, dead ends, crawl depth,
strongly connected components, and articulation points.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx  # type: ignore[import-untyped]

from .utils import clean_url
from .log import get_logger

_log = get_logger("graph")


# ------------------------------------------------------------------
# Graph construction
# ------------------------------------------------------------------

def build_graph(crawl: Dict[str, Any]) -> nx.DiGraph:
    """Build a directed graph from crawl pages data.

    Nodes = crawled pages (keyed by cleaned URL).
    Edges = internal links (source → destination).
    """
    g = nx.DiGraph()
    pages = crawl.get("pages") or []

    for page in pages:
        url = clean_url(page.get("url") or "")
        if not url:
            continue
        g.add_node(url, **{
            "title": page.get("title"),
            "status_code": page.get("status_code"),
            "redirect_count": page.get("redirect_count", 0),
            "h1_count": page.get("h1_count", 0),
            "dom_fingerprint": page.get("dom_fingerprint"),
        })

    crawled_urls = set(g.nodes)
    for page in pages:
        src = clean_url(page.get("url") or "")
        if not src or src not in crawled_urls:
            continue
        for raw_dst in (page.get("outgoing_internal_links") or []):
            dst = clean_url(raw_dst or "")
            if not dst or dst == src:
                continue
            if dst in crawled_urls:
                g.add_edge(src, dst)

    return g


# ------------------------------------------------------------------
# Metrics
# ------------------------------------------------------------------

def _pagerank(g: nx.DiGraph) -> Dict[str, float]:
    if g.number_of_nodes() == 0:
        return {}
    try:
        return nx.pagerank(g, max_iter=200)
    except nx.PowerIterationFailedConvergence:
        _log.debug("PageRank did not converge; returning uniform scores")
        n = g.number_of_nodes()
        return {node: 1.0 / n for node in g.nodes}


def _hits(g: nx.DiGraph) -> Tuple[Dict[str, float], Dict[str, float]]:
    if g.number_of_nodes() < 2:
        uniform = {node: 1.0 for node in g.nodes}
        return uniform, uniform
    try:
        hubs, authorities = nx.hits(g, max_iter=200)
        return hubs, authorities
    except nx.PowerIterationFailedConvergence:
        _log.debug("HITS did not converge; returning uniform scores")
        n = g.number_of_nodes()
        uniform = {node: 1.0 / n for node in g.nodes}
        return uniform, uniform


def _crawl_depth_bfs(g: nx.DiGraph, root: str) -> Dict[str, int]:
    """BFS shortest-path distance from root (homepage)."""
    if root not in g:
        return {}
    return nx.single_source_shortest_path_length(g, root)


def _orphan_pages(g: nx.DiGraph, root: str) -> List[str]:
    """Pages with zero inbound links (except root)."""
    return sorted(
        n for n in g.nodes
        if n != root and g.in_degree(n) == 0
    )


def _dead_ends(g: nx.DiGraph) -> List[str]:
    """Pages with zero outgoing internal links."""
    return sorted(n for n in g.nodes if g.out_degree(n) == 0)


def _deep_pages(depths: Dict[str, int], threshold: int = 3) -> List[str]:
    """Pages deeper than *threshold* clicks from root."""
    return sorted(u for u, d in depths.items() if d > threshold)


def _unreachable(g: nx.DiGraph, root: str) -> List[str]:
    """Pages that cannot be reached from root at all."""
    if root not in g:
        return sorted(g.nodes)
    reachable = nx.descendants(g, root) | {root}
    return sorted(set(g.nodes) - reachable)


def _strongly_connected_components(g: nx.DiGraph) -> List[List[str]]:
    """Non-trivial SCCs (size > 1) — link silos."""
    return sorted(
        [sorted(c) for c in nx.strongly_connected_components(g) if len(c) > 1],
        key=lambda c: -len(c),
    )


def _articulation_points(g: nx.DiGraph) -> List[str]:
    """Nodes whose removal would disconnect the undirected projection.

    These are single points of failure in the site navigation.
    """
    ug = g.to_undirected()
    return sorted(nx.articulation_points(ug))


# ------------------------------------------------------------------
# Top-N ranking helpers
# ------------------------------------------------------------------

def _top_n(scores: Dict[str, float], n: int = 10) -> List[Dict[str, Any]]:
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:n]
    return [{"url": url, "score": round(score, 6)} for url, score in ranked]


def _bottom_n(scores: Dict[str, float], n: int = 10) -> List[Dict[str, Any]]:
    ranked = sorted(scores.items(), key=lambda kv: kv[1])[:n]
    return [{"url": url, "score": round(score, 6)} for url, score in ranked]


# ------------------------------------------------------------------
# Depth distribution
# ------------------------------------------------------------------

def _depth_distribution(depths: Dict[str, int]) -> Dict[int, int]:
    dist: Dict[int, int] = {}
    for d in depths.values():
        dist[d] = dist.get(d, 0) + 1
    return dict(sorted(dist.items()))


# ------------------------------------------------------------------
# Serialisation
# ------------------------------------------------------------------

def serialize_graph(g: nx.DiGraph) -> Dict[str, Any]:
    """Serialise a DiGraph to a JSON-safe node-link dict."""
    return nx.node_link_data(g, edges="links")


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def analyze_graph(crawl: Dict[str, Any]) -> Dict[str, Any]:
    """Full graph analysis from crawl data.

    Returns a dict ready to embed in run_obj["graph"].
    """
    target_url = clean_url(crawl.get("target_url") or "")
    g = build_graph(crawl)

    n_nodes = g.number_of_nodes()
    n_edges = g.number_of_edges()

    if n_nodes == 0:
        return {
            "nodes": 0,
            "edges": 0,
            "density": 0.0,
            "note": "No pages in crawl — graph analysis skipped.",
        }

    density = nx.density(g)

    # Core algorithms
    pr = _pagerank(g)
    hubs, authorities = _hits(g)
    depths = _crawl_depth_bfs(g, target_url)
    orphans = _orphan_pages(g, target_url)
    dead = _dead_ends(g)
    deep = _deep_pages(depths, threshold=3)
    unreachable = _unreachable(g, target_url)
    sccs = _strongly_connected_components(g)
    artic = _articulation_points(g)
    depth_dist = _depth_distribution(depths)

    avg_depth: Optional[float] = None
    if depths:
        avg_depth = round(sum(depths.values()) / len(depths), 2)

    max_depth: Optional[int] = max(depths.values()) if depths else None

    return {
        "nodes": n_nodes,
        "edges": n_edges,
        "density": round(density, 4),
        "avg_depth": avg_depth,
        "max_depth": max_depth,
        "depth_distribution": depth_dist,

        "pagerank": {
            "top": _top_n(pr),
            "bottom": _bottom_n(pr),
        },
        "hits": {
            "top_hubs": _top_n(hubs),
            "top_authorities": _top_n(authorities),
        },

        "orphan_pages": {
            "count": len(orphans),
            "urls": orphans[:30],
        },
        "dead_ends": {
            "count": len(dead),
            "urls": dead[:30],
        },
        "deep_pages": {
            "count": len(deep),
            "threshold_clicks": 3,
            "urls": deep[:30],
        },
        "unreachable": {
            "count": len(unreachable),
            "urls": unreachable[:30],
        },

        "strongly_connected_components": {
            "count": len(sccs),
            "largest_size": len(sccs[0]) if sccs else 0,
            "components": sccs[:10],
        },
        "articulation_points": {
            "count": len(artic),
            "urls": artic[:20],
        },

        "issues": _build_graph_issues(
            orphans=orphans,
            dead=dead,
            deep=deep,
            unreachable=unreachable,
            artic=artic,
            sccs=sccs,
            max_depth=max_depth,
        ),
    }


# ------------------------------------------------------------------
# Issue generation (feeds into priority findings)
# ------------------------------------------------------------------

def _example_urls(urls: List[str], limit: int = 5) -> List[str]:
    return urls[:limit]


def _issue(code: str, severity: str, count: int, examples: List[str], label: str) -> Dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "label": label,
        "count": count,
        "examples": _example_urls(examples),
    }


def _build_graph_issues(
    *,
    orphans: List[str],
    dead: List[str],
    deep: List[str],
    unreachable: List[str],
    artic: List[str],
    sccs: List[List[str]],
    max_depth: Optional[int],
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []

    if unreachable:
        issues.append(_issue(
            "unreachable_pages", "high", len(unreachable), unreachable,
            "Pages unreachable from homepage",
        ))

    if orphans:
        issues.append(_issue(
            "orphan_pages", "high", len(orphans), orphans,
            "Orphan pages (zero inbound internal links)",
        ))

    if deep:
        issues.append(_issue(
            "deep_pages", "medium", len(deep), deep,
            "Pages deeper than 3 clicks from homepage",
        ))

    if dead:
        issues.append(_issue(
            "dead_end_pages", "medium", len(dead), dead,
            "Dead-end pages (zero outgoing internal links)",
        ))

    if artic:
        issues.append(_issue(
            "articulation_points", "medium", len(artic), artic,
            "Navigation bottlenecks (single points of failure)",
        ))

    sev_rank = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: (sev_rank.get(i["severity"], 99), -i["count"]))
    return issues
