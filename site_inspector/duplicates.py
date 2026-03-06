from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Any
from urllib.parse import urlparse


def _normalized_text(value: str) -> str:
    return " ".join((value or "").split()).strip().lower()


def _url_path_key(url: str) -> str:
    try:
        parsed = urlparse(url)
        path = parsed.path or "/"
        return path.rstrip("/") or "/"
    except Exception:
        return url


def detect_duplicate_pages(pages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Detect duplicate candidates by DOM fingerprint if available, else normalized path."""
    by_key: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for page in pages or []:
        url = page.get("url")
        if not url:
            continue

        fp = page.get("dom_fingerprint")
        if fp:
            key = f"dom:{fp}"
        else:
            key = f"path:{_normalized_text(_url_path_key(url))}"

        by_key[key].append(
            {
                "url": url,
                "page_id": page.get("page_id"),
                "dom_fingerprint": fp,
            }
        )

    groups = []
    for key, items in by_key.items():
        if len(items) < 2:
            continue
        groups.append(
            {
                "key": key,
                "count": len(items),
                "urls": [item["url"] for item in items],
                "page_ids": [item.get("page_id") for item in items if item.get("page_id")],
                "method": "dom_fingerprint" if key.startswith("dom:") else "normalized_path",
            }
        )

    groups.sort(key=lambda g: (-g["count"], g["key"]))

    return {
        "duplicate_groups": groups,
        "duplicate_group_count": len(groups),
        "duplicate_url_count": sum(group["count"] for group in groups),
    }


def render_duplicate_summary_md(dup: Dict[str, Any]) -> str:
    groups = dup.get("duplicate_groups") or []
    if not groups:
        return "## Duplicate candidates\n\nNo duplicate candidates detected.\n"

    lines = [
        "## Duplicate candidates",
        "",
        f"- Duplicate groups: **{dup.get('duplicate_group_count', 0)}**",
        f"- URLs in duplicate groups: **{dup.get('duplicate_url_count', 0)}**",
        "",
    ]

    for group in groups[:20]:
        lines.append(f"- **{group['count']} pages** via `{group['method']}` ({group['key']})")
        for url in group["urls"][:5]:
            lines.append(f"  - {url}")
        if len(group["urls"]) > 5:
            lines.append(f"  - … +{len(group['urls']) - 5} more")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
