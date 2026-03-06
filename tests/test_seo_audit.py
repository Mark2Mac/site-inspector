from __future__ import annotations

from site_inspector.seo_audit import audit_seo


def test_audit_seo_summarizes_metadata_status_and_links() -> None:
    crawl = {
        "target_url": "https://example.com/",
        "pages": [
            {
                "url": "https://example.com/",
                "status_code": 200,
                "title": "Home",
                "meta_description": "Welcome home",
                "canonical": "https://example.com/",
                "h1_count": 1,
                "internal_link_count": 2,
                "outgoing_internal_links": ["https://example.com/about", "https://example.com/contact"],
            },
            {
                "url": "https://example.com/about",
                "status_code": 200,
                "title": "About",
                "meta_description": None,
                "canonical": None,
                "h1_count": 0,
                "internal_link_count": 0,
                "outgoing_internal_links": [],
            },
            {
                "url": "https://example.com/contact",
                "status_code": 301,
                "title": "About",
                "meta_description": "Contact us",
                "canonical": "https://other.example/contact",
                "h1_count": 2,
                "redirect_count": 1,
                "internal_link_count": 0,
                "outgoing_internal_links": [],
            },
        ],
    }

    result = audit_seo(crawl)

    assert result["pages_analyzed"] == 3
    assert result["metadata"]["missing_meta_description"]["count"] == 1
    assert result["metadata"]["missing_h1"]["count"] == 1
    assert result["metadata"]["multiple_h1"]["count"] == 1
    assert result["metadata"]["duplicate_title_groups"]["count"] == 1
    assert result["canonicals"]["missing"]["count"] == 1
    assert result["canonicals"]["cross_host"]["count"] == 1
    assert result["status"]["non_200"]["count"] == 1
    assert result["status"]["redirected"]["count"] == 1
    assert result["internal_linking"]["zero_inlinks"]["count"] == 0
    assert result["internal_linking"]["zero_outlinks"]["count"] == 2
    assert any(issue["code"] == "missing_meta_description" for issue in result["issues"])
