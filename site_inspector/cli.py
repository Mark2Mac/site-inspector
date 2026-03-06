from .duplicates import detect_duplicate_pages, render_duplicate_summary_md

def apply_duplicate_detection(run_payload: dict, crawl: dict, md_parts: list) -> dict:
    dup_summary = detect_duplicate_pages(crawl.get("pages") or [])
    run_payload["duplicates"] = dup_summary
    md_parts.append(render_duplicate_summary_md(dup_summary))
    return run_payload
