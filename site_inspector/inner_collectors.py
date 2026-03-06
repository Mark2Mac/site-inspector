from __future__ import annotations

import json
import platform
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .utils import _run, safe_write


# -----------------------------
# Inner collector (runs in temp venv) — posture + link extraction
# -----------------------------

INNER_SCRIPT = r"""
import argparse
import json
import re
import urllib.parse
from collections import defaultdict

import requests
from bs4 import BeautifulSoup
import hashlib

def dom_fingerprint_from_soup(soup: BeautifulSoup, *, max_nodes: int = 600, max_depth: int = 6):
    # Lightweight structural DOM fingerprint (tags + depth, limited)
    body = soup.body or soup
    items = []
    n = 0
    for el in body.descendants:
        # BeautifulSoup Tag has name attribute; NavigableString doesn't.
        name = getattr(el, "name", None)
        if not name:
            continue
        # Depth (walk parents until body)
        depth = 0
        p = el.parent
        while p is not None and p is not body and depth < max_depth:
            if getattr(p, "name", None):
                depth += 1
            p = getattr(p, "parent", None)
        items.append(f"{depth}:{name}")
        n += 1
        if n >= max_nodes:
            break
    raw = "\n".join(items).encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest(), len(items)
import time
import random

try:
    from Wappalyzer import Wappalyzer, WebPage
except Exception:
    Wappalyzer = None
    WebPage = None

try:
    import builtwith
except Exception:
    builtwith = None

UA = "inspect/0.4 (+passive-tech-audit)"

def normalize_url(url: str) -> str:
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        url = "https://" + url
    p = urllib.parse.urlparse(url)
    return p._replace(fragment="").geturl()

def get_base(url: str) -> str:
    p = urllib.parse.urlparse(url)
    return f"{p.scheme}://{p.netloc}"

def host_from_url(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.split("@")[-1].split(":")[0]

def fetch(url: str, timeout: int = 20, *, attempts: int = 3):
    # HTTP GET with small retry/backoff to reduce flakiness on 429/5xx/timeouts.
    last_exc = None
    for i in range(max(1, int(attempts))):
        try:
            r = requests.get(
                url,
                timeout=timeout,
                headers={
                    "User-Agent": UA,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
                allow_redirects=True,
            )
            # Retry on transient statuses
            if r.status_code in (429, 500, 502, 503, 504) and i < attempts - 1:
                # Respect Retry-After if present
                ra = r.headers.get("Retry-After")
                sleep_s = None
                if ra:
                    try:
                        sleep_s = float(ra.strip())
                    except Exception:
                        sleep_s = None
                if sleep_s is None:
                    sleep_s = (0.5 * (2 ** i)) + random.random() * 0.25
                time.sleep(min(8.0, max(0.0, sleep_s)))
                continue
            return r
        except Exception as e:
            last_exc = e
            if i < attempts - 1:
                sleep_s = (0.5 * (2 ** i)) + random.random() * 0.25
                time.sleep(min(8.0, max(0.0, sleep_s)))
                continue
            raise
    # should never hit
    raise last_exc

def extract_third_party_domains(soup: BeautifulSoup, base_host: str):
    domains = set()
    def add(u):
        try:
            p = urllib.parse.urlparse(u)
            if p.netloc and p.netloc != base_host:
                domains.add(p.netloc)
        except Exception:
            pass

    for tag in soup.find_all(["script", "link", "img", "iframe", "source"]):
        for attr in ["src", "href"]:
            if tag.has_attr(attr):
                add(tag.get(attr))
    return sorted(domains)

def extract_same_host_links(soup: BeautifulSoup, base_url: str, base_host: str):
    out = set()
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href:
            continue
        u = urllib.parse.urljoin(base_url, href)
        u = urllib.parse.urlparse(u)._replace(fragment="").geturl()
        try:
            if host_from_url(u) == base_host:
                out.add(u)
        except Exception:
            pass
    return sorted(out)

def collect_posture(url: str, timeout: int = 20):
    out = {
        "url_input": url,
        "url_final": None,
        "status_code": None,
        "history": [],
        "headers": {},
        "html_meta": {},
        "links": {},
        "assets": {},
        "third_party_domains": [],
        "robots_txt": None,
        "sitemap_xml": None,
        "tech": {"wappalyzer": None, "builtwith": None},
        "errors": []
    }

    url = normalize_url(url)
    base = get_base(url)
    base_host = host_from_url(url)

    try:
        r = fetch(url, timeout=timeout)
        out["url_final"] = r.url
        out["status_code"] = r.status_code
        out["headers"] = dict(r.headers)
        out["history"] = [{"status": h.status_code, "url": h.url, "headers": dict(h.headers)} for h in r.history]
        html = r.text or ""
    except Exception as e:
        out["errors"].append(f"fetch_main: {e}")
        return out

    soup = BeautifulSoup(html, "html.parser")

    meta = {}
    for m in soup.find_all("meta"):
        name = m.get("name") or m.get("property") or m.get("http-equiv")
        content = m.get("content")
        if name and content:
            meta[name] = content
    title = (soup.title.string.strip() if soup.title and soup.title.string else None)
    out["html_meta"] = {"title": title, "meta": meta}

    links = defaultdict(list)
    for l in soup.find_all("link"):
        rel = " ".join(l.get("rel", [])) if isinstance(l.get("rel"), list) else (l.get("rel") or "")
        href = l.get("href")
        if rel and href:
            links[rel].append(href)
    out["links"] = dict(links)

    scripts = []
    for s in soup.find_all("script"):
        if s.get("src"):
            scripts.append(s.get("src"))
    styles = []
    for l in soup.find_all("link"):
        if (l.get("rel") and "stylesheet" in l.get("rel")) and l.get("href"):
            styles.append(l.get("href"))
    out["assets"] = {"scripts": scripts, "stylesheets": styles}

    out["third_party_domains"] = extract_third_party_domains(soup, base_host)

    try:
        rr = fetch(base + "/robots.txt", timeout=timeout)
        if rr.status_code < 500:
            out["robots_txt"] = {"status": rr.status_code, "text": rr.text[:200000]}
    except Exception as e:
        out["errors"].append(f"robots: {e}")

    try:
        sm = fetch(base + "/sitemap.xml", timeout=timeout)
        if sm.status_code < 500 and ("<urlset" in sm.text or "<sitemapindex" in sm.text):
            out["sitemap_xml"] = {"status": sm.status_code, "text": sm.text[:200000]}
    except Exception as e:
        out["errors"].append(f"sitemap: {e}")

    if Wappalyzer and WebPage:
        try:
            w = Wappalyzer.latest()
            webpage = WebPage.new_from_url(out["url_final"] or url)
            out["tech"]["wappalyzer"] = w.analyze_with_versions_and_categories(webpage)
        except Exception as e:
            out["errors"].append(f"wappalyzer: {e}")

    if builtwith:
        try:
            out["tech"]["builtwith"] = builtwith.parse(out["url_final"] or url)
        except Exception as e:
            out["errors"].append(f"builtwith: {e}")

    return out

def collect_links(url: str, timeout: int = 20):
    url = normalize_url(url)
    base_host = host_from_url(url)
    try:
        r = fetch(url, timeout=timeout)
        html = r.text or ""
        soup = BeautifulSoup(html, "html.parser")
        links = extract_same_host_links(soup, r.url, base_host)

        title = (soup.title.string.strip() if soup.title and soup.title.string else None)
        meta_description = None
        meta_robots = None
        for m in soup.find_all("meta"):
            name = (m.get("name") or "").strip().lower()
            if name == "description" and not meta_description:
                meta_description = (m.get("content") or "").strip() or None
            if name == "robots" and not meta_robots:
                meta_robots = (m.get("content") or "").strip() or None

        canonical = None
        for l in soup.find_all("link"):
            rel = l.get("rel") or []
            rels = [str(x).strip().lower() for x in (rel if isinstance(rel, list) else [rel])]
            if "canonical" in rels and l.get("href"):
                canonical = urllib.parse.urljoin(r.url, l.get("href")).strip()
                break

        h1_texts = []
        for h1 in soup.find_all("h1"):
            txt = " ".join(h1.get_text(" ", strip=True).split()).strip()
            if txt:
                h1_texts.append(txt)

        fp = None
        fp_nodes = None
        # Best-effort fingerprint only for HTML-ish content.
        try:
            fp, fp_nodes = dom_fingerprint_from_soup(soup)
        except Exception:
            fp = None
            fp_nodes = None

        return {
            "url_final": r.url,
            "status_code": r.status_code,
            "redirect_count": len(r.history or []),
            "links": links,
            "internal_link_count": len(links),
            "title": title,
            "meta_description": meta_description,
            "meta_robots": meta_robots,
            "canonical": canonical,
            "h1_count": len(h1_texts),
            "h1_texts": h1_texts[:3],
            "dom_fingerprint": fp,
            "dom_fingerprint_nodes": fp_nodes,
            "error": None,
        }
    except Exception as e:
        return {
            "url_final": None,
            "status_code": None,
            "redirect_count": 0,
            "links": [],
            "internal_link_count": 0,
            "title": None,
            "meta_description": None,
            "meta_robots": None,
            "canonical": None,
            "h1_count": 0,
            "h1_texts": [],
            "dom_fingerprint": None,
            "dom_fingerprint_nodes": None,
            "error": str(e),
        }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["posture", "links"])
    ap.add_argument("url")
    ap.add_argument("--timeout", type=int, default=20)
    args = ap.parse_args()

    if args.mode == "posture":
        data = collect_posture(args.url, timeout=args.timeout)
    else:
        data = collect_links(args.url, timeout=args.timeout)

    print(json.dumps(data, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
"""


# -----------------------------
def make_temp_venv() -> Tuple[Path, Path, Path]:
    """Create a reusable inner collector venv.

    Why this exists:
    - creating a brand new venv on every crawl is very slow on Windows
    - users may think the CLI is stuck and interrupt it mid-bootstrap

    We keep a stable per-Python-version venv in the system temp dir.
    """
    cache_root = Path(tempfile.gettempdir()) / "site_inspector_runtime"
    cache_root.mkdir(parents=True, exist_ok=True)
    version_tag = f"py{sys.version_info.major}{sys.version_info.minor}"
    venv_dir = cache_root / f"inner_{version_tag}"

    if not venv_dir.exists():
        rc, _, se = _run([sys.executable, "-m", "venv", str(venv_dir)], timeout=900)
        if rc != 0:
            raise RuntimeError(f"Failed to create venv: {se}")

    if platform.system().lower().startswith("win"):
        py = venv_dir / "Scripts" / "python.exe"
        pip = venv_dir / "Scripts" / "pip.exe"
    else:
        py = venv_dir / "bin" / "python"
        pip = venv_dir / "bin" / "pip"

    if not py.exists() or not pip.exists():
        shutil.rmtree(venv_dir, ignore_errors=True)
        rc, _, se = _run([sys.executable, "-m", "venv", str(venv_dir)], timeout=900)
        if rc != 0:
            raise RuntimeError(f"Failed to recreate venv: {se}")

    return cache_root, py, pip


def run_inner(py: Path, tmp_root: Path, mode: str, url: str, timeout_s: int, out_raw_dir: Path, tag: str) -> Dict[str, Any]:
    inner_path = tmp_root / "inner.py"
    if not inner_path.exists():
        inner_path.write_text(INNER_SCRIPT, encoding="utf-8")

    rc, so, se = _run([str(py), str(inner_path), mode, url, "--timeout", str(timeout_s)], timeout=max(60, timeout_s + 30))
    safe_write(out_raw_dir / f"{tag}.stdout.json", so)
    safe_write(out_raw_dir / f"{tag}.stderr.txt", se)

    try:
        return json.loads(so) if so.strip().startswith("{") else {"errors": ["inner returned non-json"], "raw": so, "rc": rc}
    except Exception:
        return {"errors": ["failed to parse inner json"], "raw": so, "stderr": se, "rc": rc}
