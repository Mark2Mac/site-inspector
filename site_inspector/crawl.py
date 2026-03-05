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
    safe_write_json,
    load_json_if_exists,
    stable_page_id,
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
    resume: bool = False,
    **_ignored: object,
) -> Dict[str, Any]:
    """
    Discover internal HTML pages.
    Scale-A version: concurrent link discovery with bounded worker pool.
    """
    host = host_from_url(target_url)

    # Clamp workers (this still spawns subprocesses; don't go insane)
    cw = max(1, min(32, int(workers)))

    
    # Per-host in-flight limiter (prevents self-inflicted 429s when crawl-workers is high)
    host_inflight_limit = max(1, min(8, cw // 2 or 1))
    host_sem = threading.Semaphore(host_inflight_limit)

    crawl_errors: List[Dict[str, Any]] = []
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    pages_cache_dir = raw_dir / "pages"
    pages_cache_dir.mkdir(parents=True, exist_ok=True)

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

    def _fetch_links(url: str) -> Tuple[str, List[str], int | None, str | None]:
        tag = _next_tag()

        # Per-page cache: if present, skip network work.
        pid = stable_page_id(url)
        page_dir = pages_cache_dir / pid
        cache_path = page_dir / "links.json"
        if resume and cache_path.exists():
            cached = load_json_if_exists(str(cache_path)) or {}
            out_links = cached.get("links") or []
            status = cached.get("status_code")
            err = cached.get("error") or None
            cleaned: List[str] = []
            for u in out_links:
                u = clean_url(u)
                if u:
                    cleaned.append(u)
            return url, cleaned, status, err

        host_sem.acquire()
        try:
            data = run_inner(py, tmp_root, "links", url, timeout_s, raw_dir, tag)
        finally:
            host_sem.release()

        out_links = data.get("links") or []
        cleaned: List[str] = []
        for u in out_links:
            u = clean_url(u)
            if not u:
                continue
            cleaned.append(u)

        status = data.get("status_code")
        err = data.get("error") or None
        fp = data.get("dom_fingerprint")
        fp_nodes = data.get("dom_fingerprint_nodes")

        # Persist per-page cache.
        try:
            page_dir.mkdir(parents=True, exist_ok=True)
            safe_write_json(
                cache_path,
                {
                    "url": url,
                    "fetched_at": now_iso(),
                    "status_code": status,
                    "error": err,
                    "links": cleaned,
                    "dom_fingerprint": fp,
                    "dom_fingerprint_nodes": fp_nodes,
                },
            )
        except Exception:
            # Cache is best-effort; never fail the crawl for it.
            pass

        return url, cleaned, status, err

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
                        _, links, status, err = fut.result()
                        if err:
                            crawl_errors.append({"url": src or "", "stage": "links", "error": err, "status_code": status})
                    except Exception as e:
                        # If one page fails, continue (scalability-friendly)
                        crawl_errors.append({"url": src or "", "stage": "links", "error": str(e), "status_code": None})
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
        pid = stable_page_id(u)
        fp = None
        try:
            cache_path = out_dir / "raw" / "pages" / pid / "links.json"
            cached = load_json_if_exists(str(cache_path)) or {}
            fp = cached.get("dom_fingerprint")
        except Exception:
            fp = None
        pages.append({"url": u, "page_id": pid, "dom_fingerprint": fp})

    return {
        "target_url": target_url,
        "host": host,
        "generated_at": now_iso(),
        "method": {
            "sitemap_used": bool(sitemap_text),
            "concurrent_bfs": True,
            "max_pages": max_pages,
            "workers": cw,
            "host_inflight_limit": host_inflight_limit,
            "resume": bool(resume),
        },
        "errors": crawl_errors,
        "pages": pages,
    }
