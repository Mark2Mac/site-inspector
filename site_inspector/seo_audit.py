from __future__ import annotations

from typing import Any, Dict, List

from .utils import clean_url, host_from_url


def _collapse_ws(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


def _norm_title(value: str | None) -> str:
    return _collapse_ws(value).casefold()


def _example_urls(urls: List[str], limit: int = 5) -> List[str]:
    return [u for u in urls[:limit] if u]


def _issue(code: str, severity: str, count: int, examples: List[str], label: str) -> Dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "label": label,
        "count": int(count),
        "examples": _example_urls(examples),
    }


def audit_seo(crawl: Dict[str, Any] | None, posture: Dict[str, Any] | None = None) -> Dict[str, Any]:
    crawl = crawl or {}
    pages = list(crawl.get("pages") or [])
    target_url = clean_url(crawl.get("target_url") or "") or (clean_url((posture or {}).get("target_url") or "") if posture else "")

    page_urls: List[str] = []
    page_by_url: Dict[str, Dict[str, Any]] = {}
    for page in pages:
        url = clean_url(page.get("url") or "")
        if not url:
            continue
        page_urls.append(url)
        page_by_url[url] = page

    known = set(page_urls)
    inbound = {u: 0 for u in page_urls}
    for src in page_urls:
        page = page_by_url[src]
        for raw_dst in (page.get("outgoing_internal_links") or []):
            dst = clean_url(raw_dst or "")
            if not dst or dst == src:
                continue
            if dst in inbound:
                inbound[dst] += 1

    missing_title = []
    title_too_long = []
    missing_meta_description = []
    missing_h1 = []
    multiple_h1 = []
    missing_canonical = []
    non_self_canonical = []
    cross_host_canonical = []
    non_200 = []
    redirected = []
    zero_outlinks = []
    zero_inlinks = []

    titles: Dict[str, List[str]] = {}
    for url in page_urls:
        page = page_by_url[url]
        title = _collapse_ws(page.get("title"))
        if not title:
            missing_title.append(url)
        else:
            if len(title) > 60:
                title_too_long.append(url)
            titles.setdefault(_norm_title(title), []).append(url)

        if not _collapse_ws(page.get("meta_description")):
            missing_meta_description.append(url)

        h1_count = int(page.get("h1_count") or 0)
        if h1_count <= 0:
            missing_h1.append(url)
        elif h1_count > 1:
            multiple_h1.append(url)

        canonical = _collapse_ws(page.get("canonical"))
        if not canonical:
            missing_canonical.append(url)
        else:
            canon_clean = clean_url(canonical) or canonical
            if canon_clean != url and canon_clean != clean_url(page.get("final_url") or ""):
                try:
                    if host_from_url(canon_clean) == host_from_url(url):
                        non_self_canonical.append(url)
                    else:
                        cross_host_canonical.append(url)
                except Exception:
                    non_self_canonical.append(url)

        status = page.get("status_code")
        if status not in (None, 200):
            non_200.append(url)

        redirect_count = int(page.get("redirect_count") or 0)
        final_url = clean_url(page.get("final_url") or "")
        if redirect_count > 0 or (final_url and final_url != url):
            redirected.append(url)

        if int(page.get("internal_link_count") or len(page.get("outgoing_internal_links") or [])) <= 0:
            zero_outlinks.append(url)

        if url != target_url and inbound.get(url, 0) <= 0:
            zero_inlinks.append(url)

    duplicate_title_groups = []
    for norm_title, urls in titles.items():
        if norm_title and len(urls) > 1:
            raw_title = _collapse_ws(page_by_url[urls[0]].get("title"))
            duplicate_title_groups.append({
                "title": raw_title,
                "count": len(urls),
                "urls": urls[:10],
            })
    duplicate_title_groups.sort(key=lambda item: (-item["count"], item["title"]))

    issues = [
        _issue("missing_title", "high", len(missing_title), missing_title, "Missing title tags"),
        _issue("duplicate_titles", "medium", len(duplicate_title_groups), [g["urls"][0] for g in duplicate_title_groups], "Duplicate page titles"),
        _issue("missing_meta_description", "medium", len(missing_meta_description), missing_meta_description, "Missing meta descriptions"),
        _issue("missing_h1", "medium", len(missing_h1), missing_h1, "Missing H1"),
        _issue("multiple_h1", "low", len(multiple_h1), multiple_h1, "Multiple H1s"),
        _issue("missing_canonical", "medium", len(missing_canonical), missing_canonical, "Missing canonicals"),
        _issue("non_self_canonical", "medium", len(non_self_canonical), non_self_canonical, "Canonical points elsewhere"),
        _issue("cross_host_canonical", "high", len(cross_host_canonical), cross_host_canonical, "Cross-host canonicals"),
        _issue("non_200_pages", "high", len(non_200), non_200, "Non-200 pages in crawl"),
        _issue("redirected_pages", "low", len(redirected), redirected, "Redirected pages discovered"),
        _issue("zero_inlinks", "medium", len(zero_inlinks), zero_inlinks, "Zero internal inlinks"),
        _issue("zero_outlinks", "low", len(zero_outlinks), zero_outlinks, "Zero internal outlinks"),
        _issue("title_too_long", "low", len(title_too_long), title_too_long, "Long page titles (>60 chars)"),
    ]
    issues = [i for i in issues if i["count"] > 0]
    sev_rank = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda item: (sev_rank.get(item["severity"], 99), -item["count"], item["code"]))

    return {
        "pages_analyzed": len(page_urls),
        "metadata": {
            "missing_title": {"count": len(missing_title), "examples": _example_urls(missing_title)},
            "duplicate_title_groups": {"count": len(duplicate_title_groups), "groups": duplicate_title_groups[:10]},
            "title_too_long": {"count": len(title_too_long), "examples": _example_urls(title_too_long)},
            "missing_meta_description": {"count": len(missing_meta_description), "examples": _example_urls(missing_meta_description)},
            "missing_h1": {"count": len(missing_h1), "examples": _example_urls(missing_h1)},
            "multiple_h1": {"count": len(multiple_h1), "examples": _example_urls(multiple_h1)},
        },
        "canonicals": {
            "missing": {"count": len(missing_canonical), "examples": _example_urls(missing_canonical)},
            "non_self": {"count": len(non_self_canonical), "examples": _example_urls(non_self_canonical)},
            "cross_host": {"count": len(cross_host_canonical), "examples": _example_urls(cross_host_canonical)},
        },
        "status": {
            "non_200": {"count": len(non_200), "examples": _example_urls(non_200)},
            "redirected": {"count": len(redirected), "examples": _example_urls(redirected)},
        },
        "internal_linking": {
            "zero_inlinks": {"count": len(zero_inlinks), "examples": _example_urls(zero_inlinks)},
            "zero_outlinks": {"count": len(zero_outlinks), "examples": _example_urls(zero_outlinks)},
        },
        "issues": issues[:12],
    }
