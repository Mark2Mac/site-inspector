from __future__ import annotations

import json
from pathlib import Path
from urllib.request import urlopen

from tests.helpers import fixture_root, run_cli


def test_fixture_corpus_serves_dynamic_robots_and_sitemap(fixture_corpus_url: str) -> None:
    robots = urlopen(f"{fixture_corpus_url}/robots.txt").read().decode("utf-8")
    sitemap = urlopen(f"{fixture_corpus_url}/sitemap.xml").read().decode("utf-8")

    assert "User-agent: *" in robots
    assert f"Sitemap: {fixture_corpus_url}/sitemap.xml" in robots
    assert "<urlset" in sitemap
    assert f"{fixture_corpus_url}/blog/post-1.html" in sitemap


def test_fixture_corpus_contains_nested_and_duplicate_pages() -> None:
    root = fixture_root("corpus_site")
    assert (root / "index.html").exists()
    assert (root / "blog" / "post-1.html").exists()
    assert (root / "resources" / "guide.html").exists()
    assert (root / "dup-a.html").exists()
    assert (root / "dup-b.html").exists()
    assert (root / "noindex.html").exists()


def test_run_fixture_corpus_resume_path_keeps_sections(tmp_path: Path, fixture_corpus_url: str) -> None:
    out_dir = tmp_path / "run"
    crawl_payload = {
        "generated_at": "2026-03-07T00:00:00Z",
        "target_url": f"{fixture_corpus_url}/index.html",
        "host": "127.0.0.1",
        "method": {"sitemap_used": True, "max_pages": 10},
        "pages": [
            {"url": f"{fixture_corpus_url}/index.html", "status_code": 200, "dom_fingerprint": "fp-home", "dom_fingerprint_nodes": 12, "title": "Corpus Home"},
            {"url": f"{fixture_corpus_url}/about.html", "status_code": 200, "dom_fingerprint": "fp-about", "dom_fingerprint_nodes": 10, "title": "About"},
            {"url": f"{fixture_corpus_url}/dup-a.html", "status_code": 200, "dom_fingerprint": "fp-dup", "dom_fingerprint_nodes": 9, "title": "Duplicate"},
            {"url": f"{fixture_corpus_url}/dup-b.html", "status_code": 200, "dom_fingerprint": "fp-dup", "dom_fingerprint_nodes": 9, "title": "Duplicate"},
            {"url": f"{fixture_corpus_url}/blog/post-1.html", "status_code": 200, "dom_fingerprint": "fp-blog", "dom_fingerprint_nodes": 15, "title": "Blog post"},
            {"url": f"{fixture_corpus_url}/resources/guide.html", "status_code": 200, "dom_fingerprint": "fp-guide", "dom_fingerprint_nodes": 14, "title": "Guide"},
            {"url": f"{fixture_corpus_url}/noindex.html", "status_code": 200, "dom_fingerprint": "fp-noindex", "dom_fingerprint_nodes": 8, "title": "Noindex"},
        ],
        "errors": [],
    }
    posture_payload = {
        "generated_at": "2026-03-07T00:00:00Z",
        "target_url": f"{fixture_corpus_url}/index.html",
        "host": "127.0.0.1",
        "http": {"url_final": f"{fixture_corpus_url}/index.html", "status_code": 200, "headers": {}, "history": []},
        "dns": {},
        "tls": {"protocol": None},
        "fingerprinting": {
            "tech": {},
            "third_party_domains": [],
            "assets": {},
            "robots_txt": {"status_code": 200},
            "sitemap_xml": {"status_code": 200},
            "html_meta": {"title": "Corpus Home", "meta": {}},
            "links": {},
            "errors": [],
        },
        "environment": {},
    }
    quality_payload = {
        "generated_at": "2026-03-07T00:00:00Z",
        "pages_tested": 0,
        "pages_failed": 0,
        "passed": True,
        "budget": {"categories": {}, "audits": {}},
        "lighthouse_workers": 1,
        "results": [],
        "failures": [],
        "selection": {"mode": "all", "sample_total": None, "per_group": None, "always_include": []},
        "selected_urls": [],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pages.json").write_text(json.dumps(crawl_payload, indent=2), encoding="utf-8")
    (out_dir / "posture.json").write_text(json.dumps(posture_payload, indent=2), encoding="utf-8")
    (out_dir / "quality_summary.json").write_text(json.dumps(quality_payload, indent=2), encoding="utf-8")

    result = run_cli([
        "run",
        f"{fixture_corpus_url}/index.html",
        "--resume",
        "--skip-playwright",
        "--out",
        str(out_dir),
    ])

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
    assert "seo" in payload
    assert "ai" in payload
    assert payload["duplicates"]["duplicate_group_count"] >= 1
    assert payload["target_url"].endswith("/index.html")
