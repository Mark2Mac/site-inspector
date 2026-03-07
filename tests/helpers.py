from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def run_cli(args: Iterable[str]) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "site_audit.py", *list(args)]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        cmd,
        cwd=str(repo_root()),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def seed_resume_run(out_dir: Path, base_url: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = [
        {"url": f"{base_url}/index.html", "status_code": 200, "dom_fingerprint": "fp-home", "dom_fingerprint_nodes": 12, "title": "Home"},
        {"url": f"{base_url}/dup-a.html", "status_code": 200, "dom_fingerprint": "fp-dup", "dom_fingerprint_nodes": 10, "title": "Same layout"},
        {"url": f"{base_url}/dup-b.html", "status_code": 200, "dom_fingerprint": "fp-dup", "dom_fingerprint_nodes": 10, "title": "Same layout"},
    ]
    crawl = {"generated_at": "2026-03-06T00:00:00Z", "target_url": f"{base_url}/index.html", "host": "127.0.0.1", "method": {"sitemap_used": False, "max_pages": 10}, "pages": pages, "errors": []}
    posture = {"generated_at": "2026-03-06T00:00:00Z", "target_url": f"{base_url}/index.html", "host": "127.0.0.1", "http": {"url_final": f"{base_url}/index.html", "status_code": 200, "headers": {}, "history": []}, "dns": {}, "tls": {"protocol": None}, "fingerprinting": {"tech": {}, "third_party_domains": [], "assets": {}, "robots_txt": None, "sitemap_xml": None, "html_meta": {"title": "Fixture site", "meta": {}}, "links": {}, "errors": []}, "environment": {}}
    quality = {"generated_at": "2026-03-06T00:00:00Z", "pages_tested": 0, "pages_failed": 0, "passed": True, "budget": {"categories": {}, "audits": {}}, "lighthouse_workers": 1, "results": [], "failures": [], "selection": {"mode": "all", "sample_total": None, "per_group": None, "always_include": []}, "selected_urls": []}
    (out_dir / "pages.json").write_text(json.dumps(crawl, indent=2), encoding="utf-8")
    (out_dir / "posture.json").write_text(json.dumps(posture, indent=2), encoding="utf-8")
    (out_dir / "quality_summary.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")
