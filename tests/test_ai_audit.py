from __future__ import annotations

from site_inspector.ai_audit import audit_ai_readiness


def test_audit_ai_readiness_summarizes_robots_sitemap_and_js_accessibility() -> None:
    crawl = {
        "target_url": "https://example.com/",
        "pages": [
            {"url": "https://example.com/", "meta_robots": "index,follow"},
            {"url": "https://example.com/about", "meta_robots": "noindex,follow"},
            {"url": "https://example.com/contact", "meta_robots": "index,nofollow"},
        ],
    }
    posture = {
        "target_url": "https://example.com/",
        "fingerprinting": {
            "robots_txt": {
                "status": 200,
                "text": "User-agent: *\nAllow: /\nSitemap: https://example.com/sitemap.xml\n",
            },
            "sitemap_xml": {
                "status": 200,
                "text": "<urlset><url><loc>https://example.com/</loc></url><url><loc>https://example.com/about</loc></url><url><loc>https://cdn.example.net/other</loc></url></urlset>",
            },
        },
    }
    playwright = {
        "extractability_rollup": {
            "pages_checked": 3,
            "pages_js_disabled_readable": 2,
            "pages_js_disabled_not_readable": 1,
            "details": [
                {"url": "https://example.com/", "disabledStillReadable": True},
                {"url": "https://example.com/about", "disabledStillReadable": True},
                {"url": "https://example.com/contact", "disabledStillReadable": False},
            ],
        }
    }

    result = audit_ai_readiness(crawl, posture, playwright)

    assert result["pages_analyzed"] == 3
    assert result["robots"]["present"] is True
    assert result["robots"]["has_user_agent_star"] is True
    assert result["sitemap"]["present"] is True
    assert result["sitemap"]["url_count"] == 3
    assert result["sitemap"]["cross_host_url_count"] == 1
    assert result["meta_robots"]["noindex_pages"]["count"] == 1
    assert result["meta_robots"]["nofollow_pages"]["count"] == 1
    assert result["js_accessibility"]["pages_js_disabled_not_readable"] == 1
    assert any(issue["code"] == "js_required_for_content" for issue in result["issues"])
