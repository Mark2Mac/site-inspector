"""Shared utilities: URL normalization, subprocess helpers, and file I/O."""

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
from typing import Any, Dict, List, Optional, Tuple, Set

import hashlib

from .log import get_logger

_log = get_logger("utils")


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
    # Accept both plain UTF-8 and UTF-8 with BOM to keep CLI budget loading robust on Windows.
    return json.loads(p.read_text(encoding="utf-8-sig"))


def normalize_target(target: str) -> str:
    target = target.strip()
    if not target:
        raise ValueError("Empty target")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target):
        target = "https://" + target
    parsed = urllib.parse.urlparse(target)
    if not parsed.netloc:
        raise ValueError(f"Invalid URL: {target}")
    return clean_url(parsed._replace(fragment="").geturl())


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


# Query params that are almost always tracking and safe to drop for dedupe.
_TRACKING_QUERY_KEYS = {
    "gclid", "fbclid", "msclkid", "dclid", "yclid",
    "_ga", "_gl", "gbraid", "wbraid",
    "mc_cid", "mc_eid",
}

def clean_url(url: str) -> str:
    """Best-effort URL cleanup for crawl dedupe.

    Guardrails:
    - never removes path segments
    - never removes non-tracking query params (keeps functional params like ?page=2)
    - removes fragment
    - strips common tracking params (utm_*, gclid, fbclid, ...)
    - lowercases scheme + host; removes default ports; sorts query params
    """
    try:
        p = urllib.parse.urlparse(url)
    except Exception:
        return url

    if not p.scheme or not p.netloc:
        # likely relative or malformed; return as-is and let upstream handle it
        return url

    # Normalize scheme + host casing
    scheme = (p.scheme or "").lower()

    # netloc may include userinfo and port
    username = p.username or ""
    password = p.password or ""
    hostname = (p.hostname or "").lower()
    port = p.port

    # Remove default ports
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = None

    userinfo = ""
    if username:
        userinfo = username
        if password:
            userinfo += f":{password}"
        userinfo += "@"

    netloc = hostname
    if port:
        netloc = f"{netloc}:{port}"
    netloc = userinfo + netloc

    # Drop fragments
    fragment = ""

    # Filter + sort query params (keep blanks, keep repeats)
    q = []
    try:
        for k, v in urllib.parse.parse_qsl(p.query or "", keep_blank_values=True):
            kl = (k or "").lower()
            if kl.startswith("utm_") or kl in _TRACKING_QUERY_KEYS:
                continue
            q.append((k, v))
        q.sort(key=lambda kv: (kv[0], kv[1]))
        query = urllib.parse.urlencode(q, doseq=True)
    except Exception:
        query = p.query or ""

    return urllib.parse.urlunparse((scheme, netloc, p.path or "", p.params or "", query, fragment)).strip()



def crawl_path_key(url: str) -> str:
    """Normalized path bucket used for crawl guardrails."""
    p = urllib.parse.urlparse(clean_url(url))
    path = p.path or "/"
    if not path.startswith("/"):
        path = "/" + path
    path = re.sub(r"/{2,}", "/", path)
    return path


def crawl_query_shape(url: str) -> Tuple[str, ...]:
    """Stable query-key signature used to cap crawl explosion per path."""
    p = urllib.parse.urlparse(clean_url(url))
    keys: List[str] = []
    for k, _v in urllib.parse.parse_qsl(p.query or "", keep_blank_values=True):
        kl = (k or "").lower()
        if kl.startswith("utm_") or kl in _TRACKING_QUERY_KEYS:
            continue
        keys.append(kl)
    return tuple(sorted(keys))


def crawl_path_depth(url: str) -> int:
    """Normalized path depth used by crawl guardrails.

    Examples:
    - / -> 0
    - /blog -> 1
    - /blog/post -> 2
    """
    path = crawl_path_key(url)
    parts = [p for p in path.split("/") if p]
    return len(parts)


def path_depth_cap_exceeded(url: str, *, max_depth: int) -> bool:
    """Whether *url* exceeds the allowed normalized path depth."""
    return crawl_path_depth(url) > max(0, int(max_depth))


def query_shape_cap_exceeded(
    url: str,
    shapes_by_path: Dict[str, Set[Tuple[str, ...]]],
    *,
    max_shapes_per_path: int,
) -> bool:
    """Whether *url* would exceed the allowed number of query shapes for its path."""
    shape = crawl_query_shape(url)
    if not shape:
        return False
    path_key = crawl_path_key(url)
    shapes = shapes_by_path.get(path_key) or set()
    return shape not in shapes and len(shapes) >= max(1, int(max_shapes_per_path))


def register_query_shape(
    url: str,
    shapes_by_path: Dict[str, Set[Tuple[str, ...]]],
) -> None:
    """Record the query shape of *url* for later guardrail checks."""
    path_key = crawl_path_key(url)
    shape = crawl_query_shape(url)
    bucket = shapes_by_path.setdefault(path_key, set())
    bucket.add(shape)

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


def stable_page_id(url: str) -> str:
    """Deterministic, filesystem-safe id for a page.

    Used for per-page caching under raw/pages/<id>/.
    We hash the *cleaned* URL so tracking params/fragments don't create duplicates.
    """
    u = clean_url(url)
    try:
        b = u.encode("utf-8", errors="ignore")
    except Exception:
        b = str(u).encode("utf-8", errors="ignore")
    return hashlib.sha1(b).hexdigest()[:16]


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
    except Exception as e:
        _log.debug("DNS lookup failed for %s: %s", host, e)
    return res