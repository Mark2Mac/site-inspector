from __future__ import annotations

import shutil
from collections import deque
from pathlib import Path
from typing import Any, Dict, List

from .inner_collectors import make_temp_venv, run_inner
from .utils import (
    _run,
    clean_url,
    host_from_url,
    is_same_host,
    looks_like_html_path,
    now_iso,
    safe_write,
)
import xml.etree.ElementTree as ET


# Crawl: sitemap first, then fallback BFS
# -----------------------------

def parse_sitemap_xml(xml_text: str) -> List[str]:
    urls: List[str] = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return urls

    def strip_ns(tag: str) -> str:
        return tag.split("}", 1)[-1] if "}" in tag else tag

    rtag = strip_ns(root.tag)

    if rtag == "urlset":
        for child in root:
            if strip_ns(child.tag) != "url":
                continue
            loc = None
            for node in child:
                if strip_ns(node.tag) == "loc":
                    loc = (node.text or "").strip()
                    break
            if loc:
                urls.append(loc)
        return urls

    if rtag == "sitemapindex":
        for child in root:
            if strip_ns(child.tag) != "sitemap":
                continue
            loc = None
            for node in child:
                if strip_ns(node.tag) == "loc":
                    loc = (node.text or "").strip()
                    break
            if loc:
                urls.append(loc)
        return urls

    return urls


def discover_pages(target_url: str, *, max_pages: int, timeout_s: int, out_dir: Path) -> Dict[str, Any]:
    host = host_from_url(target_url)

    pages: List[Dict[str, Any]] = []
    discovered: List[str] = []

    tmp_root, py, pip = make_temp_venv()
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    deps = [
        "requests>=2.31.0",
        "beautifulsoup4>=4.12.0",
        "lxml>=5.0.0",
        "python-Wappalyzer>=0.3.1",
        "builtwith>=1.3.4",
    ]
    rc, so, se = _run([str(pip), "install", "--quiet", "--disable-pip-version-check"] + deps, timeout=900)
    safe_write(raw_dir / "pip_install.stdout.txt", so)
    safe_write(raw_dir / "pip_install.stderr.txt", se)

    base_posture = run_inner(py, tmp_root, "posture", target_url, timeout_s, raw_dir, "posture_seed")
    sitemap_text = None
    sm = (base_posture.get("sitemap_xml") or {})
    if sm and isinstance(sm, dict):
        sitemap_text = sm.get("text")

    if sitemap_text:
        sitemap_urls = parse_sitemap_xml(sitemap_text)
        for u in sitemap_urls:
            u = clean_url(u)
            if is_same_host(u, host) and looks_like_html_path(u):
                discovered.append(u)

    visited = set(discovered)
    q = deque([target_url])
    if target_url not in visited:
        visited.add(target_url)
        discovered.insert(0, target_url)

    while q and len(discovered) < max_pages:
        current = q.popleft()
        links_data = run_inner(py, tmp_root, "links", current, timeout_s, raw_dir, f"links_{len(discovered):03d}")
        out_links = links_data.get("links") or []
        for u in out_links:
            u = clean_url(u)
            if u in visited:
                continue
            if not is_same_host(u, host):
                continue
            if not looks_like_html_path(u):
                continue
            visited.add(u)
            discovered.append(u)
            q.append(u)
            if len(discovered) >= max_pages:
                break

    for u in discovered[:max_pages]:
        pages.append({"url": u})

    shutil.rmtree(tmp_root, ignore_errors=True)

    return {
        "target_url": target_url,
        "host": host,
        "generated_at": now_iso(),
        "method": {
            "sitemap_used": bool(sitemap_text),
            "fallback_bfs": True,
            "max_pages": max_pages,
        },
        "pages": pages,
    }
