from __future__ import annotations

from site_inspector.utils import clean_url, crawl_path_key, crawl_query_shape, query_shape_cap_exceeded, register_query_shape


def test_clean_url_normalizes_tracking_default_ports_and_query_order() -> None:
    raw = "HTTPS://Example.com:443/products?id=2&utm_source=x&b=1&a=3#frag"
    cleaned = clean_url(raw)
    assert cleaned == "https://example.com/products?a=3&b=1&id=2"


def test_query_shape_cap_ignores_tracking_keys() -> None:
    shapes = {}
    register_query_shape("https://example.com/search?page=1&utm_source=x", shapes)
    assert not query_shape_cap_exceeded(
        "https://example.com/search?page=2&utm_medium=y",
        shapes,
        max_shapes_per_path=1,
    )
    assert query_shape_cap_exceeded(
        "https://example.com/search?page=2&sort=asc",
        shapes,
        max_shapes_per_path=1,
    )


def test_crawl_path_key_collapses_duplicate_slashes() -> None:
    assert crawl_path_key("https://example.com//blog///post?page=1") == "/blog/post"
    assert crawl_query_shape("https://example.com//blog///post?page=1&sort=asc") == ("page", "sort")
