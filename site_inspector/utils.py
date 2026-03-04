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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# -----------------------------
# Helpers
# -----------------------------

def now_iso() -> str:
    # timezone-aware UTC timestamp (Python 3.14+ friendly)
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _run(
    cmd: List[str],
    *,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: int = 300,
) -> Tuple[int, str, str]:
    """Run a subprocess and capture output.

    Windows note: Node/Playwright/Lighthouse often emit mixed encodings.
    Using the system default codec (often cp1252) can crash with UnicodeDecodeError.
    Force UTF-8 decoding with replacement to keep the CLI resilient.
    """
    p = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
    )
    so = p.stdout if isinstance(p.stdout, str) else ""
    se = p.stderr if isinstance(p.stderr, str) else ""
    return p.returncode, so, se


def safe_write(path: Path, content: Optional[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content or "", encoding="utf-8")


def safe_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def safe_write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def load_json_if_exists(path: Optional[str]) -> Optional[Dict[str, Any]]:
    """Load JSON from *path* if provided and exists.

    If a path is provided but the file is missing, we warn and return None
    so callers can gracefully fall back to defaults (better CLI UX).
    """
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        print(f"[warn] JSON file not found: {p} — using defaults", file=sys.stderr)
        return None
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
