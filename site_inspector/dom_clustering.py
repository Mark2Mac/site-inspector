from __future__ import annotations

from typing import Dict, List, Any, Optional


def cluster_by_dom_fingerprint(pages: List[dict]) -> Dict[str, List[str]]:
    """Cluster page URLs by dom_fingerprint (sha1). Pages without fingerprint are ignored."""
    clusters: Dict[str, List[str]] = {}
    for p in pages or []:
        fp = p.get("dom_fingerprint")
        url = p.get("url")
        if not fp or not url:
            continue
        clusters.setdefault(fp, []).append(url)
    return clusters


def summarize_dom_clusters(clusters: Dict[str, List[str]], *, sample_n: int = 3) -> List[Dict[str, Any]]:
    """Return a stable, compact summary list sorted by descending size."""
    out: List[Dict[str, Any]] = []
    for fp, urls in sorted(clusters.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        out.append(
            {
                "dom_fingerprint": fp,
                "pages": len(urls),
                "examples": urls[:sample_n],
            }
        )
    return out
