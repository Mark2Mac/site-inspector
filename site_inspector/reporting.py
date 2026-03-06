from __future__ import annotations

from typing import Any, Dict, List, Optional


# -----------------------------
# Reporting (Run)
# -----------------------------

def build_run_md(run: Dict[str, Any]) -> str:
    url = run.get("target_url")
    host = run.get("host")

    lines: List[str] = []
    lines.append("# Inspector Run\n")
    if run.get("version"):
        lines.append(f"- Version: **{run.get('version')}**")
    lines.append(f"- Target: **{url}**")
    lines.append(f"- Host: **{host}**")
    lines.append(f"- Generated: **{run.get('generated_at')}**\n")

    timings = run.get("timings") or {}
    if timings:
        lines.append("## Timing\n")
        # keep order
        for k, label in [
            ("crawl_s", "Crawl"),
            ("posture_s", "Posture"),
            ("lighthouse_s", "Lighthouse"),
            ("playwright_s", "Playwright"),
            ("total_s", "Total"),
        ]:
            if k in timings and timings.get(k) is not None:
                lines.append(f"- {label}: **{timings.get(k)}s**")
        lines.append("")

    crawl = run.get("crawl")
    if crawl:
        lines.append("## Crawl\n")
        pages = crawl.get("pages") or []
        method = crawl.get("method") or {}
        lines.append(f"- Pages discovered: **{len(pages)}**")
        lines.append(f"- Used sitemap: `{method.get('sitemap_used')}`")
        lines.append(f"- Max pages: `{method.get('max_pages')}`\n")
        errs = crawl.get("errors") or []
        lines.append(f"- Crawl errors: **{len(errs)}**\n")
        for p in pages[:50]:
            lines.append(f"- {p.get('url')}")
        if len(pages) > 50:
            lines.append("- … (truncated)")
        lines.append("")
        errs = crawl.get("errors") or []
        if errs:
            lines.append("### Crawl errors (first 20)\n")
            for e in errs[:20]:
                u = e.get("url")
                sc = e.get("status_code")
                msg = e.get("error")
                lines.append(f"- `{sc}` {u} — {msg}")
            if len(errs) > 20:
                lines.append("- … (truncated)")
            lines.append("")


    # Templates (URL + DOM)
    try:
        templates = (crawl or {}).get("templates") or {}
        url_t = (templates.get("url") or {}).get("summary") or []
        dom_t = (templates.get("dom") or {}).get("summary") or []

        if url_t or dom_t:
            lines.append("## Templates\n")

        if url_t:
            lines.append("### URL templates (top 15)\n")
            for item in url_t[:15]:
                lines.append(f"- `{item.get('template')}` — **{item.get('pages')} pages**")
            lines.append("")

        if dom_t:
            lines.append("### DOM templates (top 15)\n")
            for item in dom_t[:15]:
                fp = item.get("dom_fingerprint")
                pages_n = item.get("pages")
                ex = item.get("examples") or []
                ex_s = ", ".join(ex)
                if ex_s:
                    lines.append(f"- `{fp}` — **{pages_n} pages** (e.g. {ex_s})")
                else:
                    lines.append(f"- `{fp}` — **{pages_n} pages**")
            lines.append("")
    except Exception:
        pass

    posture = run.get("posture")
    if posture:
        http = posture.get("http") or {}
        tls = posture.get("tls") or {}
        fp = posture.get("fingerprinting") or {}

        lines.append("## Posture Summary\n")
        lines.append(f"- Final URL: `{http.get('url_final')}`")
        lines.append(f"- HTTP status: `{http.get('status_code')}`")
        lines.append(f"- TLS protocol: `{tls.get('protocol')}`")
        if tls.get("cipher"):
            c = tls["cipher"]
            lines.append(f"- TLS cipher: `{c[0]}` ({c[1]} bits)")
        lines.append("")

        lines.append("## Third-party Domains\n")
        tps = fp.get("third_party_domains") or []
        if tps:
            for d in tps:
                lines.append(f"- {d}")
        else:
            lines.append("_None detected from HTML tags (scripts/links/img/iframes)._")
        lines.append("")

    quality = run.get("quality")
    if quality:
        lines.append("## Quality (Lighthouse)\n")
        lines.append(f"- Pages tested: **{quality.get('pages_tested')}**")
        lines.append(f"- Pages failed: **{quality.get('pages_failed')}**")
        lines.append(f"- Passed: **{quality.get('passed')}**\n")

        for r in (quality.get("results") or [])[:20]:
            u = r.get("url")
            scores = r.get("scores") or {}
            be = (r.get("budget_eval") or {})
            passed = be.get("passed", True)
            lines.append(f"### {u}")
            lines.append(f"- Passed budgets: `{passed}`")
            if scores:
                lines.append(
                    f"- Scores: perf {pct01_to_pct(scores.get('performance'))}, "
                    f"seo {pct01_to_pct(scores.get('seo'))}, "
                    f"a11y {pct01_to_pct(scores.get('accessibility'))}, "
                    f"bp {pct01_to_pct(scores.get('best-practices'))}"
                )
            arts = r.get("artifacts") or {}
            if arts.get("html_path"):
                lines.append(f"- Lighthouse HTML: `{arts.get('html_path')}`")
            lines.append("")
        if len(quality.get("results") or []) > 20:
            lines.append("_More pages omitted from summary; see quality_summary.json._\n")

    pw = run.get("playwright")
    if pw:
        ex = pw.get("extractability_rollup") or {}
        lines.append("## Playwright (HAR + screenshot + extractability)\n")
        lines.append(f"- Pages tested: **{pw.get('pages_tested')}**")
        lines.append(f"- Pages failed: **{pw.get('pages_failed')}**")
        lines.append(f"- JS-disabled readable pages: **{ex.get('pages_js_disabled_readable')}**")
        lines.append(f"- JS-disabled NOT readable pages: **{ex.get('pages_js_disabled_not_readable')}**\n")
        lines.append("Artifacts are under `playwright/`.\n")

    seo = run.get("seo")
    if seo:
        lines.append("## SEO Auditing\n")
        lines.append(f"- Pages analyzed: **{seo.get('pages_analyzed')}**")

        meta = seo.get("metadata") or {}
        canon = seo.get("canonicals") or {}
        status = seo.get("status") or {}
        links = seo.get("internal_linking") or {}
        lines.append(f"- Missing titles: **{((meta.get('missing_title') or {}).get('count', 0))}**")
        lines.append(f"- Duplicate title groups: **{((meta.get('duplicate_title_groups') or {}).get('count', 0))}**")
        lines.append(f"- Missing meta descriptions: **{((meta.get('missing_meta_description') or {}).get('count', 0))}**")
        lines.append(f"- Missing canonicals: **{((canon.get('missing') or {}).get('count', 0))}**")
        lines.append(f"- Non-200 pages: **{((status.get('non_200') or {}).get('count', 0))}**")
        lines.append(f"- Zero internal inlinks: **{((links.get('zero_inlinks') or {}).get('count', 0))}**\n")

        issues = seo.get("issues") or []
        if issues:
            lines.append("### Top SEO issues\n")
            for issue in issues[:8]:
                examples = issue.get("examples") or []
                ex_s = ", ".join(examples[:3])
                if ex_s:
                    lines.append(f"- **{issue.get('label')}** ({issue.get('severity')}) — {issue.get('count')} page(s) e.g. {ex_s}")
                else:
                    lines.append(f"- **{issue.get('label')}** ({issue.get('severity')}) — {issue.get('count')} page(s)")
            lines.append("")

    ai = run.get("ai")
    if ai:
        lines.append("## AI Crawler Optimization\n")
        lines.append(f"- Pages analyzed: **{ai.get('pages_analyzed')}**")

        robots = ai.get("robots") or {}
        sitemap = ai.get("sitemap") or {}
        js = ai.get("js_accessibility") or {}
        mr = ai.get("meta_robots") or {}
        lines.append(f"- robots.txt present: **{robots.get('present')}**")
        lines.append(f"- Sitemap present: **{sitemap.get('present')}**")
        lines.append(f"- Sitemap URLs: **{sitemap.get('url_count', 0)}**")
        lines.append(f"- JS-disabled readable pages: **{js.get('pages_js_disabled_readable', 0)} / {js.get('pages_checked', 0)}**")
        lines.append(f"- Pages with noindex: **{((mr.get('noindex_pages') or {}).get('count', 0))}**\n")

        issues = ai.get("issues") or []
        if issues:
            lines.append("### Top AI crawler issues\n")
            for issue in issues[:8]:
                examples = issue.get("examples") or []
                ex_s = ", ".join(examples[:3])
                if ex_s:
                    lines.append(f"- **{issue.get('label')}** ({issue.get('severity')}) — {issue.get('count')} page(s) e.g. {ex_s}")
                else:
                    lines.append(f"- **{issue.get('label')}** ({issue.get('severity')}) — {issue.get('count')} item(s)")
            lines.append("")

    lines.append("## Next steps\n")
    lines.append("- v0.7: reporting polish, CLI UX improvements, and packaging/versioning.")
    lines.append("- Optional gating: fail CI if too many pages are unreadable with JS disabled.\n")

    return "\n".join(lines)
