from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List
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


def _cleanish_url(url: str) -> str:
    """A 'mostly-stable' URL identity used only for duplicate heuristics.

    - lowercases scheme + host
    - strips default ports
    - strips fragment
    - strips trailing slash on path
    - keeps query *out* (queries often represent real page variants)
    """
    try:
        p = urlparse(url)
        scheme = (p.scheme or "").lower()
        host = (p.hostname or "").lower()
        port = p.port
        # Remove default ports.
        if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
            port = None
        netloc = host if not port else f"{host}:{port}"
        path = (p.path or "/").rstrip("/") or "/"
        return f"{scheme}://{netloc}{path}"
    except Exception:
        return url


def detect_duplicate_pages(pages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Detect duplicate *candidates*.

    Heuristics:
    - Prefer DOM fingerprint groups (high confidence).
    - Fallback to normalized path groups only when it looks like superficial URL variance
      (e.g., trailing slash / casing) and *avoid* query-driven 'duplicates' unless the
      group is large (queries are commonly real variants).
    """

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

    groups: List[Dict[str, Any]] = []
    stats = {"high": 0, "medium": 0, "low": 0, "ignored": 0}

    for key, items in by_key.items():
        if len(items) < 2:
            continue

        urls = [it["url"] for it in items]
        page_ids = [it.get("page_id") for it in items if it.get("page_id")]

        method = "dom_fingerprint" if key.startswith("dom:") else "normalized_path"

        confidence = 0.0
        notes: List[str] = []

        if method == "dom_fingerprint":
            confidence = 0.9
            notes.append("same DOM fingerprint")
        else:
            # Path-only groups are risky: queries often represent real variants.
            has_query = any("?" in (u or "") for u in urls)
            cleanish = {_cleanish_url(u) for u in urls}
            distinct_full = len(set(urls))

            # If URLs collapse to the same cleanish identity, it's more likely superficial.
            if len(cleanish) == 1 and distinct_full > 1:
                if has_query:
                    confidence = 0.35
                    notes.append("same path but queries vary")
                else:
                    confidence = 0.65
                    notes.append("same path; superficial URL variance")
            else:
                # Different cleanish identities => probably not duplicates.
                confidence = 0.2
                notes.append("path match only (weak signal)")

            # Hardening: ignore tiny, query-driven groups (too many false positives).
            if has_query and len(urls) < 3:
                stats["ignored"] += 1
                continue

        bucket = "high" if confidence >= 0.8 else "medium" if confidence >= 0.5 else "low"
        stats[bucket] += 1

        groups.append(
            {
                "key": key,
                "count": len(items),
                "urls": urls,
                "page_ids": page_ids,
                "method": method,
                "confidence": round(confidence, 2),
                "notes": notes,
            }
        )

    groups.sort(key=lambda g: (-g["confidence"], -g["count"], g["key"]))

    return {
        "duplicate_groups": groups,
        "duplicate_group_count": len(groups),
        "duplicate_url_count": sum(group["count"] for group in groups),
        "confidence_buckets": stats,
    }


def render_duplicate_summary_md(dup: Dict[str, Any]) -> str:
    groups = dup.get("duplicate_groups") or []
    if not groups:
        return "## Duplicate candidates\n\nNo duplicate candidates detected.\n"

    buckets = dup.get("confidence_buckets") or {}
    hi = int(buckets.get("high", 0) or 0)
    med = int(buckets.get("medium", 0) or 0)
    lo = int(buckets.get("low", 0) or 0)
    ign = int(buckets.get("ignored", 0) or 0)

    lines = [
        "## Duplicate candidates",
        "",
        f"- Duplicate groups: **{dup.get('duplicate_group_count', 0)}**",
        f"- URLs in duplicate groups: **{dup.get('duplicate_url_count', 0)}**",
        f"- Confidence buckets: **high {hi}**, **medium {med}**, **low {lo}**" + (f" (ignored {ign} noisy groups)" if ign else ""),
        "",
    ]

    def render_group(group: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        out.append(
            f"- **{group['count']} pages** via `{group['method']}` — confidence **{group.get('confidence', 0)}** ({group['key']})"
        )
        notes = group.get("notes") or []
        if notes:
            out.append(f"  - _Notes:_ {'; '.join(notes)}")
        for url in (group.get("urls") or [])[:5]:
            out.append(f"  - {url}")
        if len(group.get("urls") or []) > 5:
            out.append(f"  - … +{len(group['urls']) - 5} more")
        out.append("")
        return out

    # Show high+medium first (most actionable)
    shown = 0
    for g in groups:
        if (g.get("confidence") or 0) < 0.5:
            continue
        lines.extend(render_group(g))
        shown += 1
        if shown >= 20:
            break

    # Low confidence section (still useful, but don't overwhelm)
    low_groups = [g for g in groups if (g.get("confidence") or 0) < 0.5]
    if low_groups:
        lines.append("### Low confidence (review manually)")
        lines.append("")
        for g in low_groups[:10]:
            lines.extend(render_group(g))

    return "\n".join(lines).rstrip() + "\n"
