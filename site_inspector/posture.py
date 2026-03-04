from __future__ import annotations

import platform
import shutil
import sys
from pathlib import Path
from typing import Any, Dict

from .inner_collectors import make_temp_venv, run_inner
from .utils import _run, dns_lookup_basic, get_tls_info, host_from_url, now_iso, safe_write


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
