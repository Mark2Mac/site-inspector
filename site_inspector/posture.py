from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Any, Dict

from .inner_collectors import ensure_inner_deps, get_or_create_inner_venv, run_inner
from .utils import dns_lookup_basic, get_tls_info, host_from_url, now_iso


# -----------------------------
# Posture
# -----------------------------

def collect_posture(target_url: str, *, timeout_s: int, out_dir: Path) -> Dict[str, Any]:
    host = host_from_url(target_url)

    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    venv_dir, py, pip = get_or_create_inner_venv()
    ensure_inner_deps(pip, venv_dir, raw_dir)

    inner = run_inner(py, venv_dir, "posture", target_url, timeout_s, raw_dir, "posture")

    dns = dns_lookup_basic(host)
    tls = get_tls_info(host)

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
