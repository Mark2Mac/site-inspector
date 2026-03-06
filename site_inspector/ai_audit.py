from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, List

from .utils import clean_url, host_from_url


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


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _parse_sitemap_xml(xml_text: str | None) -> Dict[str, Any]:
    result = {"kind": None, "urls": [], "child_sitemaps": []}
    if not xml_text:
        return result
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return result

    kind = _strip_ns(root.tag)
    result["kind"] = kind
    if kind == "urlset":
        urls: List[str] = []
        for child in root:
            if _strip_ns(child.tag) != "url":
                continue
            for node in child:
                if _strip_ns(node.tag) == "loc" and (node.text or "").strip():
                    urls.append((node.text or "").strip())
                    break
        result["urls"] = urls
    elif kind == "sitemapindex":
        sitemaps: List[str] = []
        for child in root:
            if _strip_ns(child.tag) != "sitemap":
                continue
            for node in child:
                if _strip_ns(node.tag) == "loc" and (node.text or "").strip():
                    sitemaps.append((node.text or "").strip())
                    break
        result["child_sitemaps"] = sitemaps
    return result


def _extract_sitemap_hints(robots_text: str | None) -> List[str]:
    hints: List[str] = []
    for line in (robots_text or "").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        if ":" not in raw:
            continue
        k, v = raw.split(":", 1)
        if k.strip().lower() == "sitemap":
            value = v.strip()
            if value:
                hints.append(value)
    return hints


def audit_ai_readiness(
    crawl: Dict[str, Any] | None,
    posture: Dict[str, Any] | None = None,
    playwright: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    crawl = crawl or {}
    posture = posture or {}
    playwright = playwright or {}

    pages = list(crawl.get("pages") or [])
    page_urls = [clean_url(p.get("url") or "") for p in pages]
    page_urls = [u for u in page_urls if u]
    target_url = clean_url(crawl.get("target_url") or posture.get("target_url") or "")
    target_host = host_from_url(target_url) if target_url else None

    fp = posture.get("fingerprinting") or {}
    robots = fp.get("robots_txt") or {}
    sitemap = fp.get("sitemap_xml") or {}
    robots_text = robots.get("text") if isinstance(robots, dict) else None
    sitemap_text = sitemap.get("text") if isinstance(sitemap, dict) else None
    robots_status = robots.get("status") if isinstance(robots, dict) else None
    sitemap_status = sitemap.get("status") if isinstance(sitemap, dict) else None

    robot_lines = [ln.strip() for ln in (robots_text or "").splitlines() if ln.strip()]
    robot_lc = [ln.lower() for ln in robot_lines]
    has_user_agent_star = any(ln.startswith("user-agent:") and ln.split(":", 1)[1].strip() == "*" for ln in robot_lc)
    disallow_root = any(ln.startswith("disallow:") and ln.split(":", 1)[1].strip() == "/" for ln in robot_lc)
    sitemap_hints = _extract_sitemap_hints(robots_text)

    parsed_sitemap = _parse_sitemap_xml(sitemap_text)
    sitemap_kind = parsed_sitemap.get("kind")
    sitemap_urls = [clean_url(u) or u for u in (parsed_sitemap.get("urls") or [])]
    sitemap_urls = [u for u in sitemap_urls if u]
    same_host_sitemap_urls = []
    cross_host_sitemap_urls = []
    for u in sitemap_urls:
        try:
            if target_host and host_from_url(u) == target_host:
                same_host_sitemap_urls.append(u)
            else:
                cross_host_sitemap_urls.append(u)
        except Exception:
            cross_host_sitemap_urls.append(u)

    overlap_with_crawl = len(set(page_urls) & set(same_host_sitemap_urls))

    noindex_pages = []
    nofollow_pages = []
    for page in pages:
        robots_meta = str(page.get("meta_robots") or "").lower()
        url = clean_url(page.get("url") or "")
        if not url:
            continue
        if "noindex" in robots_meta:
            noindex_pages.append(url)
        if "nofollow" in robots_meta:
            nofollow_pages.append(url)

    ex = (playwright.get("extractability_rollup") or {}) if isinstance(playwright, dict) else {}
    pages_checked = int(ex.get("pages_checked") or 0)
    pages_readable = int(ex.get("pages_js_disabled_readable") or 0)
    pages_not_readable = int(ex.get("pages_js_disabled_not_readable") or 0)
    readability_ratio = None
    if pages_checked > 0:
        readability_ratio = round(pages_readable / pages_checked, 3)

    issues = [
        _issue("missing_robots_txt", "medium", 0 if robots_text else 1, [target_url] if target_url and not robots_text else [], "Missing robots.txt"),
        _issue("robots_missing_user_agent_star", "low", 0 if not robots_text or has_user_agent_star else 1, [target_url] if target_url and robots_text and not has_user_agent_star else [], "robots.txt missing User-agent: *"),
        _issue("robots_disallow_root", "high", 1 if disallow_root else 0, [target_url] if target_url and disallow_root else [], "robots.txt disallows root"),
        _issue("missing_sitemap_xml", "medium", 0 if sitemap_text else 1, [target_url] if target_url and not sitemap_text else [], "Missing sitemap.xml"),
        _issue("sitemap_missing_in_robots", "low", 0 if not sitemap_text or sitemap_hints else 1, [target_url] if target_url and sitemap_text and not sitemap_hints else [], "Sitemap not declared in robots.txt"),
        _issue("sitemap_cross_host_urls", "medium", len(cross_host_sitemap_urls), cross_host_sitemap_urls, "Cross-host sitemap URLs"),
        _issue("meta_noindex_pages", "high", len(noindex_pages), noindex_pages, "Pages with noindex robots meta"),
        _issue("meta_nofollow_pages", "medium", len(nofollow_pages), nofollow_pages, "Pages with nofollow robots meta"),
        _issue("js_required_for_content", "high", pages_not_readable, [d.get("url") for d in (ex.get("details") or []) if d.get("disabledStillReadable") is False], "Content largely requires JavaScript"),
    ]
    issues = [i for i in issues if i["count"] > 0]
    sev_rank = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda item: (sev_rank.get(item["severity"], 99), -item["count"], item["code"]))

    return {
        "pages_analyzed": len(page_urls),
        "robots": {
            "present": bool(robots_text),
            "status": robots_status,
            "has_user_agent_star": has_user_agent_star,
            "disallows_root": disallow_root,
            "declared_sitemaps": sitemap_hints[:10],
        },
        "sitemap": {
            "present": bool(sitemap_text),
            "status": sitemap_status,
            "kind": sitemap_kind,
            "url_count": len(sitemap_urls),
            "child_sitemap_count": len(parsed_sitemap.get("child_sitemaps") or []),
            "same_host_url_count": len(same_host_sitemap_urls),
            "cross_host_url_count": len(cross_host_sitemap_urls),
            "overlap_with_crawl": overlap_with_crawl,
        },
        "meta_robots": {
            "noindex_pages": {"count": len(noindex_pages), "examples": _example_urls(noindex_pages)},
            "nofollow_pages": {"count": len(nofollow_pages), "examples": _example_urls(nofollow_pages)},
        },
        "js_accessibility": {
            "available": pages_checked > 0,
            "pages_checked": pages_checked,
            "pages_js_disabled_readable": pages_readable,
            "pages_js_disabled_not_readable": pages_not_readable,
            "readability_ratio": readability_ratio,
        },
        "issues": issues[:12],
    }
