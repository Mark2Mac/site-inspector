#!/usr/bin/env python3
"""
inspect.py (v0.4) — Windows-first Site Inspector
v0.4 adds: PLAYWRIGHT mode (HAR + screenshots + DOM + JS-disabled content check)

Features:
- v0.1: crawl + posture
- v0.2: lighthouse quality + budgets + CI-friendly exit codes
- v0.3: diff between runs (regressions + new third parties allowlist)
- v0.4: playwright artifacts (HAR/screenshot/DOM/text) + basic "extractability" (JS-disabled)

Outputs (in --out dir):
- run.json, run.md
- pages.json
- posture.json, posture.md
- quality_summary.json + lighthouse/*.report.{json,html}
- playwright/{slug}/
    - har.json
    - screenshot.png
    - dom.html
    - text.txt
    - js_disabled_dom.html
    - js_disabled_text.txt
    - playwright_summary.json
- raw/* artifacts
- diff.json, diff.md (diff mode)

Prereqs (Windows):
- Python 3.10+
- Node.js in PATH (npx/node)
- Chrome/Chromium available (Lighthouse launches Chrome)
- Playwright will install Chromium on first use into .cache/playwright

Usage:
  python inspect.py run https://example.com --max-pages 10 --budget budgets.json
  python inspect.py playwright https://example.com --max-pages 10
  python inspect.py diff runs/runA runs/runB

Exit codes:
- run/quality: 0 if passed budgets, 1 otherwise
- diff: 0 if no regressions (and no new disallowed third parties), 1 if regressions found
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import urllib.parse
import xml.etree.ElementTree as ET
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# -----------------------------
# Helpers
# -----------------------------

def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _run(cmd: List[str], *, cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None, timeout: int = 300) -> Tuple[int, str, str]:
    p = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        shell=False,
    )
    return p.returncode, p.stdout, p.stderr


def safe_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def safe_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def safe_write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def load_json_if_exists(path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def normalize_target(target: str) -> str:
    target = target.strip()
    if not target:
        raise ValueError("Empty target")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target):
        target = "https://" + target
    parsed = urllib.parse.urlparse(target)
    if not parsed.netloc:
        raise ValueError(f"Invalid URL: {target}")
    return parsed._replace(fragment="").geturl()


def host_from_url(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.split("@")[-1].split(":")[0]


def base_from_url(url: str) -> str:
    p = urllib.parse.urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def is_same_host(url: str, host: str) -> bool:
    try:
        return host_from_url(url) == host
    except Exception:
        return False


def clean_url(url: str) -> str:
    p = urllib.parse.urlparse(url)
    return p._replace(fragment="").geturl()


def looks_like_html_path(url: str) -> bool:
    p = urllib.parse.urlparse(url)
    path = (p.path or "").lower()
    if path.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
                      ".css", ".js", ".map", ".json", ".xml", ".txt",
                      ".woff", ".woff2", ".ttf", ".eot",
                      ".pdf", ".zip", ".rar", ".7z", ".mp4", ".webm", ".mp3")):
        return False
    return True


def slugify_url_for_filename(url: str) -> str:
    p = urllib.parse.urlparse(url)
    path = p.path.strip("/")
    if not path:
        path = "home"
    slug = f"{p.netloc}_{path}"
    slug = slug.replace("/", "_")
    slug = re.sub(r"[^a-zA-Z0-9_\-.]+", "_", slug)
    if p.query:
        q = re.sub(r"[^a-zA-Z0-9_\-.]+", "_", p.query)
        slug += f"__q_{q}"
    return slug[:180]


def which(exe: str) -> Optional[str]:
    paths = os.environ.get("PATH", "").split(os.pathsep)
    exts = [""] if "." in exe else [".exe", ".cmd", ".bat", ""]
    for d in paths:
        d = d.strip('"')
        if not d:
            continue
        for ext in exts:
            cand = Path(d) / (exe + ext)
            if cand.exists():
                return str(cand)
    return None


def pct01_to_pct(x: Optional[float]) -> Optional[int]:
    if x is None:
        return None
    try:
        return int(round(float(x) * 100))
    except Exception:
        return None


# -----------------------------
# TLS & basic DNS (outer, no deps)
# -----------------------------

def get_tls_info(host: str, port: int = 443, timeout: int = 10) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "host": host,
        "port": port,
        "reachable": False,
        "error": None,
        "protocol": None,
        "cipher": None,
        "san": None,
        "not_before": None,
        "not_after": None,
    }
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                info["reachable"] = True
                info["protocol"] = ssock.version()
                info["cipher"] = ssock.cipher()
                cert = ssock.getpeercert()
                san = []
                for t in cert.get("subjectAltName", []):
                    if len(t) >= 2:
                        san.append({"type": t[0], "value": t[1]})
                info["san"] = san or None
                info["not_before"] = cert.get("notBefore")
                info["not_after"] = cert.get("notAfter")
    except Exception as e:
        info["error"] = str(e)
    return info


def dns_lookup_basic(host: str) -> Dict[str, List[str]]:
    res: Dict[str, List[str]] = {"A": [], "AAAA": []}
    try:
        infos = socket.getaddrinfo(host, None)
        for fam, _, _, _, sockaddr in infos:
            if fam == socket.AF_INET:
                ip = sockaddr[0]
                if ip not in res["A"]:
                    res["A"].append(ip)
            elif fam == socket.AF_INET6:
                ip = sockaddr[0]
                if ip not in res["AAAA"]:
                    res["AAAA"].append(ip)
    except Exception:
        pass
    return res


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

def fetch(url: str, timeout: int = 20):
    return requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
        allow_redirects=True,
    )

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
        return {"url_final": r.url, "status_code": r.status_code, "links": links, "error": None}
    except Exception as e:
        return {"url_final": None, "status_code": None, "links": [], "error": str(e)}

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


def make_temp_venv() -> Tuple[Path, Path, Path]:
    tmp_root = Path(tempfile.mkdtemp(prefix="inspect_venv_"))
    venv_dir = tmp_root / "venv"
    rc, _, se = _run([sys.executable, "-m", "venv", str(venv_dir)])
    if rc != 0:
        raise RuntimeError(f"Failed to create venv: {se}")

    if platform.system().lower().startswith("win"):
        py = venv_dir / "Scripts" / "python.exe"
        pip = venv_dir / "Scripts" / "pip.exe"
    else:
        py = venv_dir / "bin" / "python"
        pip = venv_dir / "bin" / "pip"

    return tmp_root, py, pip


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


# -----------------------------
# Posture
# -----------------------------

def collect_posture(target_url: str, *, timeout_s: int, out_dir: Path) -> Dict[str, Any]:
    host = host_from_url(target_url)

    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    tmp_root, py, pip = make_temp_venv()

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

    inner = run_inner(py, tmp_root, "posture", target_url, timeout_s, raw_dir, "posture")

    dns = dns_lookup_basic(host)
    tls = get_tls_info(host)

    shutil.rmtree(tmp_root, ignore_errors=True)

    return {
        "generated_at": now_iso(),
        "target_url": target_url,
        "host": host,
        "http": {
            "url_final": inner.get("url_final"),
            "status_code": inner.get("status_code"),
            "headers": inner.get("headers"),
            "history": inner.get("history"),
        },
        "dns": dns,
        "tls": tls,
        "fingerprinting": {
            "tech": inner.get("tech") or {},
            "third_party_domains": inner.get("third_party_domains") or [],
            "assets": inner.get("assets") or {},
            "robots_txt": inner.get("robots_txt"),
            "sitemap_xml": inner.get("sitemap_xml"),
            "html_meta": inner.get("html_meta"),
            "links": inner.get("links"),
            "errors": inner.get("errors") or [],
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
        }
    }


# -----------------------------
# Quality (Lighthouse)
# -----------------------------

DEFAULT_BUDGET: Dict[str, Any] = {
    "categories": {
        "performance": {"min_score": 0.80},
        "seo": {"min_score": 0.90},
        "accessibility": {"min_score": 0.80},
        "best-practices": {"min_score": 0.80},
    },
    "audits": {
        "largest-contentful-paint": {"max_ms": 2500},
        "cumulative-layout-shift": {"max_numeric": 0.10},
        "total-blocking-time": {"max_ms": 300},
        "speed-index": {"max_ms": 4000},
        "first-contentful-paint": {"max_ms": 2000},
    }
}


def ensure_npx_available() -> None:
    if which("npx") is None:
        raise RuntimeError("npx not found in PATH. Install Node.js (includes npx) and restart your terminal.")


def run_lighthouse(url: str, *, out_dir: Path, timeout_s: int) -> Dict[str, Any]:
    ensure_npx_available()

    lh_dir = out_dir / "lighthouse"
    lh_dir.mkdir(parents=True, exist_ok=True)

    slug = slugify_url_for_filename(url)
    json_path = lh_dir / f"{slug}.report.json"
    html_path = lh_dir / f"{slug}.report.html"

    chrome_flags = "--headless --disable-gpu --no-sandbox"

    cmd = [
        "npx",
        "--yes",
        "lighthouse",
        url,
        "--quiet",
        "--output=json",
        "--output=html",
        f"--output-path={str(json_path)}",
        f"--chrome-flags={chrome_flags}",
    ]

    rc, so, se = _run(cmd, timeout=max(120, timeout_s * 6))
    safe_write(out_dir / "raw" / f"lighthouse_{slug}.stdout.txt", so)
    safe_write(out_dir / "raw" / f"lighthouse_{slug}.stderr.txt", se)

    if not html_path.exists():
        candidates = sorted(lh_dir.glob(f"*{slug}*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            html_path = candidates[0]

    report: Dict[str, Any] = {"url": url, "rc": rc, "json_path": str(json_path), "html_path": str(html_path) if html_path.exists() else None}
    try:
        if json_path.exists():
            report["lighthouse_json"] = json.loads(json_path.read_text(encoding="utf-8"))
        else:
            report["error"] = f"JSON report not found at {json_path}"
    except Exception as e:
        report["error"] = f"Failed to parse Lighthouse JSON: {e}"
    return report


def extract_lighthouse_scores(lh: Dict[str, Any]) -> Dict[str, Optional[float]]:
    out = {"performance": None, "seo": None, "accessibility": None, "best-practices": None}
    cats = (lh.get("categories") or {})
    for key in out.keys():
        lk = "best-practices" if key == "best-practices" else key
        if lk in cats and isinstance(cats[lk], dict):
            sc = cats[lk].get("score")
            if isinstance(sc, (int, float)):
                out[key] = float(sc)
    return out


def extract_lighthouse_audit_values(lh: Dict[str, Any], audit_id: str) -> Dict[str, Any]:
    audits = lh.get("audits") or {}
    a = audits.get(audit_id) or {}
    return {
        "numericValue": a.get("numericValue"),
        "numericUnit": a.get("numericUnit"),
        "displayValue": a.get("displayValue"),
        "score": a.get("score"),
    }


def evaluate_budget(lh_json: Dict[str, Any], budget: Dict[str, Any]) -> Dict[str, Any]:
    details: Dict[str, Any] = {"passed": True, "categories": {}, "audits": {}}

    scores = extract_lighthouse_scores(lh_json)
    cat_budget = (budget.get("categories") or {})
    for cat, cfg in cat_budget.items():
        min_score = cfg.get("min_score")
        actual = scores.get(cat)
        passed = True
        reason = None
        if min_score is not None:
            if actual is None:
                passed = False
                reason = "missing_score"
            else:
                passed = actual >= float(min_score)
                if not passed:
                    reason = f"score<{min_score}"
        details["categories"][cat] = {"actual": actual, "min_score": min_score, "passed": passed, "reason": reason}
        if not passed:
            details["passed"] = False

    audit_budget = (budget.get("audits") or {})
    for audit_id, cfg in audit_budget.items():
        v = extract_lighthouse_audit_values(lh_json, audit_id)
        numeric_value = v.get("numericValue")
        passed = True
        reason = None

        if numeric_value is None:
            passed = False
            reason = "missing_numericValue"
        else:
            if "max_ms" in cfg:
                max_ms = float(cfg["max_ms"])
                passed = float(numeric_value) <= max_ms
                if not passed:
                    reason = f"value>{max_ms}ms"
            if "max_numeric" in cfg:
                mx = float(cfg["max_numeric"])
                passed = float(numeric_value) <= mx
                if not passed:
                    reason = f"value>{mx}"

        details["audits"][audit_id] = {"value": v, "budget": cfg, "passed": passed, "reason": reason}
        if not passed:
            details["passed"] = False

    return details


def quality_for_urls(urls: List[str], *, out_dir: Path, timeout_s: int, budget: Dict[str, Any], max_pages: int) -> Dict[str, Any]:
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []

    for url in urls[:max_pages]:
        lh_run = run_lighthouse(url, out_dir=out_dir, timeout_s=timeout_s)
        lh_json = lh_run.get("lighthouse_json")

        per_page: Dict[str, Any] = {
            "url": url,
            "artifacts": {
                "json_path": lh_run.get("json_path"),
                "html_path": lh_run.get("html_path"),
            },
            "rc": lh_run.get("rc"),
            "error": lh_run.get("error"),
            "scores": None,
            "budget_eval": None,
        }

        if isinstance(lh_json, dict):
            per_page["scores"] = extract_lighthouse_scores(lh_json)
            per_page["budget_eval"] = evaluate_budget(lh_json, budget)

        results.append(per_page)

        if not per_page.get("budget_eval", {}).get("passed", True):
            failures.append({"url": url, "why": per_page["budget_eval"]})

    summary = {
        "generated_at": now_iso(),
        "pages_tested": len(results),
        "pages_failed": len(failures),
        "passed": len(failures) == 0,
        "budget": budget,
        "results": results,
        "failures": failures,
    }
    return summary


# -----------------------------
# v0.4 Playwright (HAR + screenshot + DOM + JS-disabled extractability)
# -----------------------------

PLAYWRIGHT_NODE_SCRIPT = r"""
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

function ensureDir(p) { fs.mkdirSync(p, { recursive: true }); }
function writeText(p, s) { fs.writeFileSync(p, s ?? "", { encoding: "utf-8" }); }

async function grab(url, outDir, timeoutMs, jsEnabled) {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    javaScriptEnabled: jsEnabled,
    acceptDownloads: false,
    ignoreHTTPSErrors: true,
    viewport: { width: 1365, height: 768 },
  });

  const page = await context.newPage();

  // HAR only for JS-enabled run (meaningful network)
  let harPath = null;
  if (jsEnabled) {
    harPath = path.join(outDir, "har.json");
    await context.tracing.start({ screenshots: false, snapshots: false });
    await context.route("**/*", route => route.continue());
  }

  const started = Date.now();
  let result = {
    url,
    jsEnabled,
    finalUrl: null,
    status: null,
    timings: { totalMs: null },
    errors: [],
    textLen: 0,
    hasMeaningfulText: false,
    files: {}
  };

  try {
    const resp = await page.goto(url, { waitUntil: "domcontentloaded", timeout: timeoutMs });
    result.finalUrl = page.url();
    result.status = resp ? resp.status() : null;

    // best-effort wait for network to settle (only when JS enabled)
    if (jsEnabled) {
      try {
        await page.waitForLoadState("networkidle", { timeout: Math.min(15000, timeoutMs) });
      } catch (e) {
        // not fatal
      }
    }

    // screenshot
    const screenshotPath = path.join(outDir, jsEnabled ? "screenshot.png" : "js_disabled_screenshot.png");
    await page.screenshot({ path: screenshotPath, fullPage: true });
    result.files.screenshot = screenshotPath;

    // DOM
    const html = await page.content();
    const domPath = path.join(outDir, jsEnabled ? "dom.html" : "js_disabled_dom.html");
    writeText(domPath, html);
    result.files.dom = domPath;

    // Text extract
    const text = await page.evaluate(() => {
      const t = document?.body?.innerText || "";
      return t.replace(/\s+/g, " ").trim();
    });
    const textPath = path.join(outDir, jsEnabled ? "text.txt" : "js_disabled_text.txt");
    writeText(textPath, text);
    result.files.text = textPath;

    result.textLen = (text || "").length;
    result.hasMeaningfulText = result.textLen >= 200; // heuristic threshold

    // Save HAR for JS-enabled by using Playwright's built-in har recorder pattern:
    // Playwright's context.newContext({ recordHar: { path }}) is supported; we use it by re-creating context.
  } catch (e) {
    result.errors.push(String(e && e.message ? e.message : e));
  } finally {
    result.timings.totalMs = Date.now() - started;

    // If JS enabled and we want HAR, easiest is to use recordHar in a second short run:
    // (Yes it's extra time; keeps script dependency-light and stable across Playwright versions.)
    await browser.close();
  }

  // HAR run (JS enabled only) — short & focused
  if (jsEnabled) {
    const browser2 = await chromium.launch({ headless: true });
    const context2 = await browser2.newContext({
      javaScriptEnabled: true,
      ignoreHTTPSErrors: true,
      recordHar: { path: path.join(outDir, "har.json"), content: "omit" },
      viewport: { width: 1365, height: 768 },
    });
    const page2 = await context2.newPage();
    try {
      await page2.goto(url, { waitUntil: "networkidle", timeout: timeoutMs });
    } catch (e) {
      result.errors.push("har_run: " + String(e && e.message ? e.message : e));
    } finally {
      await context2.close();
      await browser2.close();
      result.files.har = path.join(outDir, "har.json");
    }
  }

  return result;
}

async function main() {
  const url = process.argv[2];
  const outDir = process.argv[3];
  const timeoutMs = Number(process.argv[4] || "30000");

  ensureDir(outDir);

  const enabled = await grab(url, outDir, timeoutMs, true);
  const disabled = await grab(url, outDir, timeoutMs, false);

  const summary = {
    url,
    generatedAt: new Date().toISOString(),
    jsEnabled: enabled,
    jsDisabled: disabled,
    extractability: {
      enabledTextLen: enabled.textLen,
      disabledTextLen: disabled.textLen,
      disabledStillReadable: disabled.hasMeaningfulText,
      notes: disabled.hasMeaningfulText
        ? "Content remains readable without JavaScript (good for conservative crawlers)."
        : "Content largely requires JavaScript (may reduce extractability for some crawlers)."
    }
  };

  const summaryPath = path.join(outDir, "playwright_summary.json");
  writeText(summaryPath, JSON.stringify(summary, null, 2));
  console.log(JSON.stringify(summary, null, 2));
}

main().catch((e) => {
  console.error(String(e && e.stack ? e.stack : e));
  process.exit(2);
});
"""


def ensure_node_available() -> None:
    if which("node") is None:
        raise RuntimeError("node not found in PATH. Install Node.js and restart your terminal.")
    ensure_npx_available()


def ensure_playwright_chromium_installed(cache_dir: Path, out_dir: Path) -> Dict[str, Any]:
    """
    Installs Playwright Chromium into cache_dir (PLAYWRIGHT_BROWSERS_PATH) once.
    Returns install metadata.
    """
    ensure_node_available()

    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    cache_dir.mkdir(parents=True, exist_ok=True)
    marker = cache_dir / ".chromium_installed"

    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(cache_dir)

    if marker.exists():
        return {"installed": True, "cached": True, "cache_dir": str(cache_dir)}

    cmd = ["npx", "--yes", "playwright", "install", "chromium"]
    rc, so, se = _run(cmd, env=env, timeout=1800)
    safe_write(raw_dir / "playwright_install.stdout.txt", so)
    safe_write(raw_dir / "playwright_install.stderr.txt", se)

    if rc != 0:
        raise RuntimeError("Playwright install chromium failed. See raw/playwright_install.stderr.txt")

    safe_write(marker, now_iso())
    return {"installed": True, "cached": False, "cache_dir": str(cache_dir)}


def run_playwright_for_url(url: str, *, out_dir: Path, timeout_s: int, cache_dir: Path) -> Dict[str, Any]:
    """
    Runs a Node script via npx with playwright dependency.
    Writes artifacts under out_dir/playwright/{slug}/
    """
    ensure_node_available()

    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Ensure browser exists (once)
    install_meta = ensure_playwright_chromium_installed(cache_dir, out_dir)

    pw_root = out_dir / "playwright"
    pw_root.mkdir(parents=True, exist_ok=True)

    slug = slugify_url_for_filename(url)
    page_dir = pw_root / slug
    page_dir.mkdir(parents=True, exist_ok=True)

    # Write JS runner into out_dir/raw (stable path, debuggable)
    js_path = raw_dir / "playwright_runner_v04.cjs"
    if not js_path.exists():
        safe_write(js_path, PLAYWRIGHT_NODE_SCRIPT)

    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(cache_dir)

    # Use npx to provide playwright package temporarily:
    # npx -p playwright node script.cjs <url> <outDir> <timeoutMs>
    cmd = [
        "npx", "--yes",
        "-p", "playwright",
        "node", str(js_path),
        url, str(page_dir), str(int(timeout_s * 1000))
    ]

    rc, so, se = _run(cmd, env=env, timeout=max(180, timeout_s * 12))
    safe_write(raw_dir / f"playwright_{slug}.stdout.json", so)
    safe_write(raw_dir / f"playwright_{slug}.stderr.txt", se)

    summary = {"url": url, "slug": slug, "dir": str(page_dir), "rc": rc, "install": install_meta}
    try:
        if so.strip().startswith("{"):
            summary["playwright_summary"] = json.loads(so)
        else:
            summary["error"] = "Playwright runner returned non-JSON stdout."
    except Exception as e:
        summary["error"] = f"Failed parsing Playwright JSON: {e}"

    # Also ensure the per-page summary is referenced
    per_page_summary_path = page_dir / "playwright_summary.json"
    if per_page_summary_path.exists():
        summary["artifacts"] = {
            "summary_json": str(per_page_summary_path),
            "har": str(page_dir / "har.json") if (page_dir / "har.json").exists() else None,
            "screenshot": str(page_dir / "screenshot.png") if (page_dir / "screenshot.png").exists() else None,
            "dom": str(page_dir / "dom.html") if (page_dir / "dom.html").exists() else None,
            "text": str(page_dir / "text.txt") if (page_dir / "text.txt").exists() else None,
            "js_disabled_dom": str(page_dir / "js_disabled_dom.html") if (page_dir / "js_disabled_dom.html").exists() else None,
            "js_disabled_text": str(page_dir / "js_disabled_text.txt") if (page_dir / "js_disabled_text.txt").exists() else None,
        }

    return summary


def playwright_for_urls(urls: List[str], *, out_dir: Path, timeout_s: int, max_pages: int) -> Dict[str, Any]:
    cache_dir = out_dir / ".cache" / "playwright"
    results: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []

    for url in urls[:max_pages]:
        r = run_playwright_for_url(url, out_dir=out_dir, timeout_s=timeout_s, cache_dir=cache_dir)
        results.append(r)
        if r.get("rc") not in (0, None) or r.get("error"):
            failures.append({"url": url, "error": r.get("error"), "rc": r.get("rc")})

    # Extractability rollup
    extract = {
        "pages_checked": len(results),
        "pages_js_disabled_readable": 0,
        "pages_js_disabled_not_readable": 0,
        "details": []
    }
    for r in results:
        ps = (r.get("playwright_summary") or {})
        ex = (ps.get("extractability") or {})
        readable = ex.get("disabledStillReadable")
        if readable is True:
            extract["pages_js_disabled_readable"] += 1
        elif readable is False:
            extract["pages_js_disabled_not_readable"] += 1
        extract["details"].append({
            "url": r.get("url"),
            "disabledStillReadable": readable,
            "enabledTextLen": ex.get("enabledTextLen"),
            "disabledTextLen": ex.get("disabledTextLen"),
        })

    summary = {
        "generated_at": now_iso(),
        "pages_tested": len(results),
        "pages_failed": len(failures),
        "passed": len(failures) == 0,
        "results": results,
        "failures": failures,
        "extractability_rollup": extract,
    }
    return summary


# -----------------------------
# v0.3 DIFF
# -----------------------------

def load_run_dir(run_dir: Path) -> Dict[str, Any]:
    run_path = run_dir / "run.json"
    if not run_path.exists():
        raise FileNotFoundError(f"run.json not found in: {run_dir}")
    run = json.loads(run_path.read_text(encoding="utf-8"))
    run["_run_dir"] = str(run_dir)
    return run


def list_pages_from_run(run: Dict[str, Any]) -> List[str]:
    pages = (run.get("crawl") or {}).get("pages") or []
    out = []
    for p in pages:
        u = p.get("url")
        if u:
            out.append(u)
    return out


def third_parties_from_run(run: Dict[str, Any]) -> List[str]:
    fp = (run.get("posture") or {}).get("fingerprinting") or {}
    tps = fp.get("third_party_domains") or []
    return sorted({str(x) for x in tps if x})


def tech_names_from_run(run: Dict[str, Any]) -> Dict[str, List[str]]:
    fp = (run.get("posture") or {}).get("fingerprinting") or {}
    tech = fp.get("tech") or {}
    out: Dict[str, List[str]] = {"wappalyzer": [], "builtwith": []}

    w = tech.get("wappalyzer")
    if isinstance(w, dict):
        out["wappalyzer"] = sorted(w.keys())

    b = tech.get("builtwith")
    if isinstance(b, dict):
        names = []
        for _, items in b.items():
            if isinstance(items, list):
                for it in items:
                    names.append(str(it))
        out["builtwith"] = sorted(set(names))

    return out


def quality_index_by_url(run: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    q = run.get("quality") or {}
    res = q.get("results") or []
    out: Dict[str, Dict[str, Any]] = {}
    for r in res:
        u = r.get("url")
        if u:
            out[u] = r
    return out


def diff_sets(a: List[str], b: List[str]) -> Dict[str, List[str]]:
    sa, sb = set(a), set(b)
    return {
        "added": sorted(sb - sa),
        "removed": sorted(sa - sb),
        "unchanged": sorted(sa & sb),
    }


def diff_quality(run_a: Dict[str, Any], run_b: Dict[str, Any], *, score_regression_threshold: float) -> Dict[str, Any]:
    qa = run_a.get("quality")
    qb = run_b.get("quality")
    out: Dict[str, Any] = {
        "available": bool(qa) and bool(qb),
        "summary": {},
        "per_page": [],
        "regressions": [],
    }
    if not qa or not qb:
        out["summary"] = {"note": "One or both runs missing 'quality' block"}
        return out

    idx_a = quality_index_by_url(run_a)
    idx_b = quality_index_by_url(run_b)

    urls = sorted(set(idx_a.keys()) | set(idx_b.keys()))
    regressions = []

    out["summary"] = {
        "runA_passed": qa.get("passed"),
        "runB_passed": qb.get("passed"),
        "runA_pages_failed": qa.get("pages_failed"),
        "runB_pages_failed": qb.get("pages_failed"),
    }

    for u in urls:
        ra = idx_a.get(u)
        rb = idx_b.get(u)
        row: Dict[str, Any] = {"url": u, "a": None, "b": None, "deltas": {}, "regression": False, "reasons": []}

        if ra:
            row["a"] = {
                "scores": ra.get("scores"),
                "passed": (ra.get("budget_eval") or {}).get("passed"),
            }
        if rb:
            row["b"] = {
                "scores": rb.get("scores"),
                "passed": (rb.get("budget_eval") or {}).get("passed"),
            }

        a_pass = row["a"]["passed"] if row["a"] else None
        b_pass = row["b"]["passed"] if row["b"] else None
        if a_pass is True and b_pass is False:
            row["regression"] = True
            row["reasons"].append("budget_regression_pass_to_fail")

        a_scores = (row["a"] or {}).get("scores") or {}
        b_scores = (row["b"] or {}).get("scores") or {}
        for cat in ["performance", "seo", "accessibility", "best-practices"]:
            av = a_scores.get(cat)
            bv = b_scores.get(cat)
            if isinstance(av, (int, float)) and isinstance(bv, (int, float)):
                delta = float(bv) - float(av)
                row["deltas"][cat] = delta
                if delta < -abs(score_regression_threshold):
                    row["regression"] = True
                    row["reasons"].append(f"score_drop_{cat}_{delta:.3f}")

        out["per_page"].append(row)
        if row["regression"]:
            regressions.append({"url": u, "reasons": row["reasons"], "deltas": row["deltas"]})

    out["regressions"] = regressions
    return out


def diff_runs(run_a: Dict[str, Any], run_b: Dict[str, Any], *, allow_new_third_parties: Optional[List[str]], score_regression_threshold: float) -> Dict[str, Any]:
    pages_a = list_pages_from_run(run_a)
    pages_b = list_pages_from_run(run_b)

    tps_a = third_parties_from_run(run_a)
    tps_b = third_parties_from_run(run_b)

    tech_a = tech_names_from_run(run_a)
    tech_b = tech_names_from_run(run_b)

    pages_diff = diff_sets(pages_a, pages_b)
    tps_diff = diff_sets(tps_a, tps_b)

    allow = set(allow_new_third_parties or [])
    new_tps = tps_diff["added"]
    disallowed_new_tps = [d for d in new_tps if d not in allow] if allow_new_third_parties is not None else []

    quality_diff = diff_quality(run_a, run_b, score_regression_threshold=score_regression_threshold)

    passed = True
    reasons: List[str] = []

    if quality_diff.get("available") and quality_diff.get("regressions"):
        passed = False
        reasons.append("quality_regressions")

    if allow_new_third_parties is not None and disallowed_new_tps:
        passed = False
        reasons.append("new_third_parties_not_allowed")

    qa = (run_a.get("quality") or {}).get("passed")
    qb = (run_b.get("quality") or {}).get("passed")
    if qa is True and qb is False:
        passed = False
        reasons.append("overall_budget_pass_to_fail")

    # v0.4: include extractability (if present) as informational (not gating by default)
    pwa = run_a.get("playwright") or {}
    pwb = run_b.get("playwright") or {}
    extract_diff = None
    if pwa and pwb:
        ea = (pwa.get("extractability_rollup") or {})
        eb = (pwb.get("extractability_rollup") or {})
        extract_diff = {
            "runA_js_disabled_readable": ea.get("pages_js_disabled_readable"),
            "runB_js_disabled_readable": eb.get("pages_js_disabled_readable"),
            "runA_js_disabled_not_readable": ea.get("pages_js_disabled_not_readable"),
            "runB_js_disabled_not_readable": eb.get("pages_js_disabled_not_readable"),
        }

    out = {
        "version": "0.4",
        "generated_at": now_iso(),
        "runA": {"dir": run_a.get("_run_dir"), "generated_at": run_a.get("generated_at"), "target_url": run_a.get("target_url")},
        "runB": {"dir": run_b.get("_run_dir"), "generated_at": run_b.get("generated_at"), "target_url": run_b.get("target_url")},
        "passed": passed,
        "fail_reasons": reasons,
        "pages": pages_diff,
        "third_parties": {
            **tps_diff,
            "allowlist_used": allow_new_third_parties is not None,
            "allowlist": sorted(list(allow)) if allow_new_third_parties is not None else None,
            "disallowed_added": disallowed_new_tps if allow_new_third_parties is not None else None,
        },
        "tech": {
            "wappalyzer": diff_sets(tech_a.get("wappalyzer", []), tech_b.get("wappalyzer", [])),
            "builtwith": diff_sets(tech_a.get("builtwith", []), tech_b.get("builtwith", [])),
        },
        "quality": quality_diff,
        "extractability": extract_diff,
    }
    return out


def render_diff_md(diff: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Inspector Diff (v0.4)\n")
    lines.append(f"- Generated: **{diff.get('generated_at')}**")
    lines.append(f"- Passed: **{diff.get('passed')}**")
    if not diff.get("passed"):
        lines.append(f"- Fail reasons: `{', '.join(diff.get('fail_reasons') or [])}`")
    lines.append("")

    a = diff.get("runA") or {}
    b = diff.get("runB") or {}
    lines.append("## Runs\n")
    lines.append(f"- Run A: `{a.get('dir')}` — `{a.get('generated_at')}` — `{a.get('target_url')}`")
    lines.append(f"- Run B: `{b.get('dir')}` — `{b.get('generated_at')}` — `{b.get('target_url')}`\n")

    q = diff.get("quality") or {}
    lines.append("## Quality\n")
    if not q.get("available"):
        lines.append("_Quality diff not available (missing quality in one run)._")
        lines.append("")
    else:
        summ = q.get("summary") or {}
        lines.append(f"- RunA passed: `{summ.get('runA_passed')}` (failed pages: {summ.get('runA_pages_failed')})")
        lines.append(f"- RunB passed: `{summ.get('runB_passed')}` (failed pages: {summ.get('runB_pages_failed')})")
        regs = q.get("regressions") or []
        lines.append(f"- Regressions: **{len(regs)}**")
        if regs:
            for r in regs[:25]:
                lines.append(f"  - {r.get('url')}: {', '.join(r.get('reasons') or [])}")
            if len(regs) > 25:
                lines.append("  - … (truncated)")
        lines.append("")

    ex = diff.get("extractability")
    if ex:
        lines.append("## Extractability (JS disabled)\n")
        lines.append(f"- RunA readable pages: `{ex.get('runA_js_disabled_readable')}`; not readable: `{ex.get('runA_js_disabled_not_readable')}`")
        lines.append(f"- RunB readable pages: `{ex.get('runB_js_disabled_readable')}`; not readable: `{ex.get('runB_js_disabled_not_readable')}`")
        lines.append("")

    tp = diff.get("third_parties") or {}
    lines.append("## Third-party domains\n")
    added = tp.get("added") or []
    removed = tp.get("removed") or []
    lines.append(f"- Added: **{len(added)}**")
    for d in added[:30]:
        lines.append(f"  - {d}")
    if len(added) > 30:
        lines.append("  - … (truncated)")
    lines.append(f"- Removed: **{len(removed)}**")
    for d in removed[:30]:
        lines.append(f"  - {d}")
    if len(removed) > 30:
        lines.append("  - … (truncated)")
    if tp.get("allowlist_used"):
        dis = tp.get("disallowed_added") or []
        lines.append(f"- Allowlist used: `true` (disallowed new: {len(dis)})")
    lines.append("")

    tech = diff.get("tech") or {}
    lines.append("## Tech changes\n")
    for src in ["wappalyzer", "builtwith"]:
        t = tech.get(src) or {}
        lines.append(f"### {src}")
        lines.append(f"- Added: {len(t.get('added') or [])}")
        for x in (t.get("added") or [])[:30]:
            lines.append(f"  - {x}")
        if len(t.get("added") or []) > 30:
            lines.append("  - … (truncated)")
        lines.append(f"- Removed: {len(t.get('removed') or [])}")
        for x in (t.get("removed") or [])[:30]:
            lines.append(f"  - {x}")
        if len(t.get("removed") or []) > 30:
            lines.append("  - … (truncated)")
        lines.append("")

    pages = diff.get("pages") or {}
    lines.append("## Pages\n")
    lines.append(f"- Added: {len(pages.get('added') or [])}")
    for u in (pages.get("added") or [])[:30]:
        lines.append(f"  - {u}")
    if len(pages.get("added") or []) > 30:
        lines.append("  - … (truncated)")
    lines.append(f"- Removed: {len(pages.get('removed') or [])}")
    for u in (pages.get("removed") or [])[:30]:
        lines.append(f"  - {u}")
    if len(pages.get("removed") or []) > 30:
        lines.append("  - … (truncated)")

    lines.append("")
    return "\n".join(lines)


# -----------------------------
# Reporting (Run)
# -----------------------------

def build_run_md(run: Dict[str, Any]) -> str:
    url = run.get("target_url")
    host = run.get("host")

    lines: List[str] = []
    lines.append("# Inspector Run (v0.4)\n")
    lines.append(f"- Target: **{url}**")
    lines.append(f"- Host: **{host}**")
    lines.append(f"- Generated: **{run.get('generated_at')}**\n")

    crawl = run.get("crawl")
    if crawl:
        lines.append("## Crawl\n")
        pages = crawl.get("pages") or []
        method = crawl.get("method") or {}
        lines.append(f"- Pages discovered: **{len(pages)}**")
        lines.append(f"- Used sitemap: `{method.get('sitemap_used')}`")
        lines.append(f"- Max pages: `{method.get('max_pages')}`\n")
        for p in pages[:50]:
            lines.append(f"- {p.get('url')}")
        if len(pages) > 50:
            lines.append("- … (truncated)")
        lines.append("")

    posture = run.get("posture")
    if posture:
        http = posture.get("http") or {}
        tls = posture.get("tls") or {}
        fp = posture.get("fingerprinting") or {}

        lines.append("## Posture Summary\n")
        lines.append(f"- Final URL: `{http.get('url_final')}`")
        lines.append(f"- HTTP status: `{http.get('status_code')}`")
        lines.append(f"- TLS protocol: `{tls.get('protocol')}`")
        if tls.get("cipher"):
            c = tls["cipher"]
            lines.append(f"- TLS cipher: `{c[0]}` ({c[1]} bits)")
        lines.append("")

        lines.append("## Third-party Domains\n")
        tps = fp.get("third_party_domains") or []
        if tps:
            for d in tps:
                lines.append(f"- {d}")
        else:
            lines.append("_None detected from HTML tags (scripts/links/img/iframes)._")
        lines.append("")

    quality = run.get("quality")
    if quality:
        lines.append("## Quality (Lighthouse)\n")
        lines.append(f"- Pages tested: **{quality.get('pages_tested')}**")
        lines.append(f"- Pages failed: **{quality.get('pages_failed')}**")
        lines.append(f"- Passed: **{quality.get('passed')}**\n")

        for r in (quality.get("results") or [])[:20]:
            u = r.get("url")
            scores = r.get("scores") or {}
            be = (r.get("budget_eval") or {})
            passed = be.get("passed", True)
            lines.append(f"### {u}")
            lines.append(f"- Passed budgets: `{passed}`")
            if scores:
                lines.append(
                    f"- Scores: perf {pct01_to_pct(scores.get('performance'))}, "
                    f"seo {pct01_to_pct(scores.get('seo'))}, "
                    f"a11y {pct01_to_pct(scores.get('accessibility'))}, "
                    f"bp {pct01_to_pct(scores.get('best-practices'))}"
                )
            arts = r.get("artifacts") or {}
            if arts.get("html_path"):
                lines.append(f"- Lighthouse HTML: `{arts.get('html_path')}`")
            lines.append("")
        if len(quality.get("results") or []) > 20:
            lines.append("_More pages omitted from summary; see quality_summary.json._\n")

    pw = run.get("playwright")
    if pw:
        ex = pw.get("extractability_rollup") or {}
        lines.append("## Playwright (HAR + screenshot + extractability)\n")
        lines.append(f"- Pages tested: **{pw.get('pages_tested')}**")
        lines.append(f"- Pages failed: **{pw.get('pages_failed')}**")
        lines.append(f"- JS-disabled readable pages: **{ex.get('pages_js_disabled_readable')}**")
        lines.append(f"- JS-disabled NOT readable pages: **{ex.get('pages_js_disabled_not_readable')}**\n")
        lines.append("Artifacts are under `playwright/`.\n")

    lines.append("## Next steps\n")
    lines.append("- v0.5: AI readiness checks (llms.txt, JSON-LD validation, citations friendliness).")
    lines.append("- Optional gating: fail CI if too many pages are unreadable with JS disabled.\n")

    return "\n".join(lines)


# -----------------------------
# Commands
# -----------------------------

def cmd_crawl(args: argparse.Namespace) -> int:
    target = normalize_target(args.target)
    host = host_from_url(target)

    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else Path(f"./inspect_{host}_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    crawl = discover_pages(target, max_pages=args.max_pages, timeout_s=args.timeout, out_dir=out_dir)
    safe_write_json(out_dir / "pages.json", crawl)

    print(f"✅ Crawl saved: {out_dir / 'pages.json'}")
    return 0


def cmd_posture(args: argparse.Namespace) -> int:
    target = normalize_target(args.target)
    host = host_from_url(target)

    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else Path(f"./inspect_{host}_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    posture = collect_posture(target, timeout_s=args.timeout, out_dir=out_dir)
    safe_write_json(out_dir / "posture.json", posture)

    run = {"generated_at": now_iso(), "target_url": target, "host": host, "posture": posture}
    safe_write(out_dir / "posture.md", build_run_md(run))

    print(f"✅ Posture saved:\n- {out_dir / 'posture.json'}\n- {out_dir / 'posture.md'}\n- raw: {out_dir / 'raw'}")
    return 0


def cmd_quality(args: argparse.Namespace) -> int:
    target = normalize_target(args.target)
    host = host_from_url(target)

    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else Path(f"./inspect_{host}_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)

    budget = load_json_if_exists(args.budget) or DEFAULT_BUDGET

    crawl = discover_pages(target, max_pages=args.max_pages, timeout_s=args.timeout, out_dir=out_dir)
    urls = [p["url"] for p in (crawl.get("pages") or [])]

    summary = quality_for_urls(urls, out_dir=out_dir, timeout_s=args.timeout, budget=budget, max_pages=args.max_pages)
    safe_write_json(out_dir / "quality_summary.json", summary)
    safe_write_json(out_dir / "pages.json", crawl)

    print(f"✅ Quality saved:\n- {out_dir / 'quality_summary.json'}\n- lighthouse: {out_dir / 'lighthouse'}\n- raw: {out_dir / 'raw'}")
    return 0 if summary.get("passed") else 1


def cmd_playwright(args: argparse.Namespace) -> int:
    target = normalize_target(args.target)
    host = host_from_url(target)

    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else Path(f"./inspect_{host}_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)

    crawl = discover_pages(target, max_pages=args.max_pages, timeout_s=args.timeout, out_dir=out_dir)
    urls = [p["url"] for p in (crawl.get("pages") or [])]

    summary = playwright_for_urls(urls, out_dir=out_dir, timeout_s=args.timeout, max_pages=args.max_pages)
    safe_write_json(out_dir / "playwright_summary.json", summary)
    safe_write_json(out_dir / "pages.json", crawl)

    print(f"✅ Playwright saved:\n- {out_dir / 'playwright_summary.json'}\n- playwright: {out_dir / 'playwright'}\n- raw: {out_dir / 'raw'}")
    return 0 if summary.get("passed") else 1


def cmd_run(args: argparse.Namespace) -> int:
    target = normalize_target(args.target)
    host = host_from_url(target)

    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else Path(f"./inspect_{host}_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)

    budget = load_json_if_exists(args.budget) or DEFAULT_BUDGET

    crawl = discover_pages(target, max_pages=args.max_pages, timeout_s=args.timeout, out_dir=out_dir)
    posture = collect_posture(target, timeout_s=args.timeout, out_dir=out_dir)

    quality = None
    quality_exit = 0
    if not args.skip_quality:
        urls = [p["url"] for p in (crawl.get("pages") or [])]
        quality = quality_for_urls(urls, out_dir=out_dir, timeout_s=args.timeout, budget=budget, max_pages=args.max_pages)
        safe_write_json(out_dir / "quality_summary.json", quality)
        quality_exit = 0 if quality.get("passed") else 1

    pw = None
    pw_exit = 0
    if not args.skip_playwright:
        urls = [p["url"] for p in (crawl.get("pages") or [])]
        pw = playwright_for_urls(urls, out_dir=out_dir, timeout_s=args.timeout, max_pages=args.max_pages)
        safe_write_json(out_dir / "playwright_summary.json", pw)
        pw_exit = 0 if pw.get("passed") else 1

    run = {
        "version": "0.4",
        "generated_at": now_iso(),
        "target_url": target,
        "host": host,
        "crawl": crawl,
        "posture": posture,
        "quality": quality,
        "playwright": pw,
    }

    safe_write_json(out_dir / "run.json", run)
    safe_write(out_dir / "run.md", build_run_md(run))
    safe_write_json(out_dir / "pages.json", crawl)
    safe_write_json(out_dir / "posture.json", posture)

    print(f"✅ Run generated:\n- {out_dir / 'run.md'}\n- {out_dir / 'run.json'}\n- pages: {out_dir / 'pages.json'}\n- posture: {out_dir / 'posture.json'}\n- lighthouse: {out_dir / 'lighthouse'}\n- playwright: {out_dir / 'playwright'}\n- raw: {out_dir / 'raw'}")

    # Keep hero feature gating: budgets first; playwright failure is also meaningful but optional.
    # We return "worst" exit code among enabled checks.
    return 1 if (quality_exit == 1 or pw_exit == 1) else 0


def cmd_diff(args: argparse.Namespace) -> int:
    run_a_dir = Path(args.run_a).resolve()
    run_b_dir = Path(args.run_b).resolve()

    run_a = load_run_dir(run_a_dir)
    run_b = load_run_dir(run_b_dir)

    if args.out:
        out_dir = Path(args.out)
    else:
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        out_dir = Path(f"./diff_{run_a_dir.name}_vs_{run_b_dir.name}_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    allowlist = None
    if args.allow_new_third_parties is not None:
        allowlist = [x.strip() for x in args.allow_new_third_parties.split(",") if x.strip()]

    diff = diff_runs(
        run_a,
        run_b,
        allow_new_third_parties=allowlist,
        score_regression_threshold=args.score_regression_threshold,
    )

    safe_write_json(out_dir / "diff.json", diff)
    safe_write(out_dir / "diff.md", render_diff_md(diff))

    print(f"✅ Diff generated:\n- {out_dir / 'diff.md'}\n- {out_dir / 'diff.json'}")
    return 0 if diff.get("passed") else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="inspect", description="Site Inspector v0.4 (crawl + posture + lighthouse + diff + playwright)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_crawl = sub.add_parser("crawl", help="Discover pages via sitemap + fallback internal link crawl")
    ap_crawl.add_argument("target")
    ap_crawl.add_argument("--out", default=None)
    ap_crawl.add_argument("--max-pages", type=int, default=50)
    ap_crawl.add_argument("--timeout", type=int, default=20)
    ap_crawl.set_defaults(fn=cmd_crawl)

    ap_posture = sub.add_parser("posture", help="Collect posture/tech/headers/TLS/DNS/meta/third parties for a URL")
    ap_posture.add_argument("target")
    ap_posture.add_argument("--out", default=None)
    ap_posture.add_argument("--timeout", type=int, default=20)
    ap_posture.set_defaults(fn=cmd_posture)

    ap_quality = sub.add_parser("quality", help="Run Lighthouse on discovered pages and apply budgets (exit 1 on fail)")
    ap_quality.add_argument("target")
    ap_quality.add_argument("--out", default=None)
    ap_quality.add_argument("--max-pages", type=int, default=20, help="Max pages to test with Lighthouse (default 20)")
    ap_quality.add_argument("--timeout", type=int, default=20)
    ap_quality.add_argument("--budget", default=None, help="Path to budgets.json (default: built-in)")
    ap_quality.set_defaults(fn=cmd_quality)

    ap_pw = sub.add_parser("playwright", help="Collect HAR + screenshot + DOM + JS-disabled extractability for discovered pages")
    ap_pw.add_argument("target")
    ap_pw.add_argument("--out", default=None)
    ap_pw.add_argument("--max-pages", type=int, default=10, help="Max pages to capture with Playwright (default 10)")
    ap_pw.add_argument("--timeout", type=int, default=30, help="Per-page timeout seconds (default 30)")
    ap_pw.set_defaults(fn=cmd_playwright)

    ap_run = sub.add_parser("run", help="Run crawl + posture + (optional) lighthouse + (optional) playwright and produce run.json/run.md")
    ap_run.add_argument("target")
    ap_run.add_argument("--out", default=None)
    ap_run.add_argument("--max-pages", type=int, default=20)
    ap_run.add_argument("--timeout", type=int, default=30)
    ap_run.add_argument("--budget", default=None, help="Path to budgets.json (default: built-in)")
    ap_run.add_argument("--skip-quality", action="store_true", help="Skip Lighthouse quality step")
    ap_run.add_argument("--skip-playwright", action="store_true", help="Skip Playwright artifacts step")
    ap_run.set_defaults(fn=cmd_run)

    ap_diff = sub.add_parser("diff", help="Diff two run folders (run.json) and detect regressions (exit 1 on fail)")
    ap_diff.add_argument("run_a", help="Path to run A folder (contains run.json)")
    ap_diff.add_argument("run_b", help="Path to run B folder (contains run.json)")
    ap_diff.add_argument("--out", default=None, help="Output directory for diff.{json,md}")
    ap_diff.add_argument(
        "--allow-new-third-parties",
        default=None,
        help="Comma-separated allowlist for NEW third-party domains (if set, new domains not in list cause failure).",
    )
    ap_diff.add_argument(
        "--score-regression-threshold",
        type=float,
        default=0.02,
        help="Score drop threshold (0..1). Default 0.02 (~2 points).",
    )
    ap_diff.set_defaults(fn=cmd_diff)

    return ap


def main() -> int:
    if not platform.system().lower().startswith("win"):
        print("⚠️ This build is optimized for Windows. It may still work elsewhere, but is not the target.", file=sys.stderr)

    ap = build_parser()
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())