from __future__ import annotations

import shutil
import threading
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import xml.etree.ElementTree as ET

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


# Crawl: sitemap first, then concurrent BFS
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


def discover_pages(
    target_url: str,
    *,
    max_pages: int,
    timeout_s: int,
    out_dir: Path,
    workers: int = 8,
    **_ignored: object,
) -> Dict[str, Any]:
    """
    Discover internal HTML pages.
    Scale-A version: concurrent link discovery with bounded worker pool.
    """
    host = host_from_url(target_url)

    # Clamp workers (this still spawns subprocesses; don't go insane)
    cw = max(1, min(32, int(workers)))

    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    pages: List[Dict[str, Any]] = []
    discovered: List[str] = []

    tmp_root, py, pip = make_temp_venv()

    # Install deps once (shared by all workers)
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

    # Seed posture: try to read sitemap
    base_posture = run_inner(py, tmp_root, "posture", target_url, timeout_s, raw_dir, "posture_seed")
    sitemap_text = None
    sm = (base_posture.get("sitemap_xml") or {})
    if isinstance(sm, dict):
        sitemap_text = sm.get("text")

    if sitemap_text:
        for u in parse_sitemap_xml(sitemap_text):
            u = clean_url(u)
            if is_same_host(u, host) and looks_like_html_path(u):
                discovered.append(u)

    # Concurrent BFS
    visited: Set[str] = set(discovered)
    q: deque[str] = deque()

    # Always include target first
    if target_url not in visited:
        visited.add(target_url)
        discovered.insert(0, target_url)
    q.append(target_url)

    lock = threading.Lock()
    counter = {"i": 0}

    def _next_tag() -> str:
        with lock:
            counter["i"] += 1
            return f"links_{counter['i']:05d}"

    def _fetch_links(url: str) -> Tuple[str, List[str]]:
        tag = _next_tag()
        data = run_inner(py, tmp_root, "links", url, timeout_s, raw_dir, tag)
        out_links = data.get("links") or []
        cleaned: List[str] = []
        for u in out_links:
            u = clean_url(u)
            if not u:
                continue
            cleaned.append(u)
        return url, cleaned

    in_flight = set()
    futures = {}

    try:
        with ThreadPoolExecutor(max_workers=cw) as ex:
            # Prime workers from queue
            while q and len(discovered) < max_pages and len(futures) < cw:
                u = q.popleft()
                if u in in_flight:
                    continue
                in_flight.add(u)
                fut = ex.submit(_fetch_links, u)
                futures[fut] = u

            while futures and len(discovered) < max_pages:
                done, _ = wait(list(futures.keys()), return_when=FIRST_COMPLETED)
                for fut in done:
                    src = futures.pop(fut, None)
                    if src:
                        in_flight.discard(src)

                    try:
                        _, links = fut.result()
                    except Exception:
                        # If one page fails, continue (scalability-friendly)
                        links = []

                    # Add new candidates
                    for u in links:
                        if len(discovered) >= max_pages:
                            break
                        if not is_same_host(u, host):
                            continue
                        if not looks_like_html_path(u):
                            continue
                        with lock:
                            if u in visited:
                                continue
                            visited.add(u)
                            discovered.append(u)
                            q.append(u)

                # Refill workers
                while q and len(discovered) < max_pages and len(futures) < cw:
                    u = q.popleft()
                    if u in in_flight:
                        continue
                    in_flight.add(u)
                    fut = ex.submit(_fetch_links, u)
                    futures[fut] = u

    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    for u in discovered[:max_pages]:
        pages.append({"url": u})

    return {
        "target_url": target_url,
        "host": host,
        "generated_at": now_iso(),
        "method": {
            "sitemap_used": bool(sitemap_text),
            "concurrent_bfs": True,
            "max_pages": max_pages,
            "workers": cw,
        },
        "pages": pages,
    }