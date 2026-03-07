from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import __version__


SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


# -----------------------------
# Reporting (Run)
# -----------------------------

def _severity_rank(value: str | None) -> int:
    return SEVERITY_ORDER.get((value or "").lower(), 99)


def _pct01_to_pct(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    try:
        return f"{round(float(v) * 100)}%"
    except Exception:
        return "n/a"


def _issue_line(source: str, issue: Dict[str, Any]) -> str:
    examples = issue.get("examples") or []
    ex_s = ", ".join(examples[:3])
    base = f"- **[{issue.get('severity', 'n/a').upper()}] {source}: {issue.get('label')}** — {issue.get('count', 0)} item(s)"
    if ex_s:
        return base + f" e.g. {ex_s}"
    return base


def _build_priority_findings(run: Dict[str, Any]) -> List[str]:
    findings: List[Dict[str, Any]] = []

    dup = run.get("duplicates") or {}
    validation = dup.get("validation") or {}
    actionable = int(validation.get("actionable_groups") or 0)
    if actionable > 0:
        findings.append(
            {
                "severity": "medium",
                "source": "Duplicates",
                "label": "Actionable duplicate groups",
                "count": actionable,
                "examples": validation.get("manual_review_keys") or [],
            }
        )

    for source, key in (("SEO", "seo"), ("AI", "ai")):
        payload = run.get(key) or {}
        for issue in (payload.get("issues") or []):
            if int(issue.get("count") or 0) > 0:
                findings.append({**issue, "source": source})

    findings.sort(
        key=lambda item: (_severity_rank(item.get("severity")), -(item.get("count") or 0), item.get("label") or "")
    )
    return [_issue_line(item.get("source") or "Report", item) for item in findings[:10]]


def build_run_md(run: Dict[str, Any]) -> str:
    url = run.get("target_url")
    host = run.get("host")

    lines: List[str] = []
    lines.append(f"# Inspector Run ({run.get('version') or __version__})\n")
    lines.append(f"- Target: **{url}**")
    lines.append(f"- Host: **{host}**")
    lines.append(f"- Generated: **{run.get('generated_at')}**\n")

    crawl = run.get("crawl") or {}
    quality = run.get("quality") or {}
    dup = run.get("duplicates") or {}
    seo = run.get("seo") or {}
    ai = run.get("ai") or {}
    pw = run.get("playwright") or {}

    lines.append("## Executive summary\n")
    lines.append(f"- Pages discovered: **{len(crawl.get('pages') or [])}**")
    lines.append(f"- Duplicate groups: **{dup.get('duplicate_group_count', 0)}**")
    lines.append(f"- Actionable duplicate groups: **{((dup.get('validation') or {}).get('actionable_groups', 0))}**")
    lines.append(f"- SEO issues flagged: **{len(seo.get('issues') or [])}**")
    lines.append(f"- AI crawler issues flagged: **{len(ai.get('issues') or [])}**")
    lines.append(f"- Lighthouse pages tested: **{quality.get('pages_tested', 0)}**")
    if pw:
        ex = pw.get("extractability_rollup") or {}
        readable = ex.get("pages_js_disabled_readable")
        checked = (readable or 0) + (ex.get("pages_js_disabled_not_readable") or 0)
        if checked:
            lines.append(f"- JS-disabled readable pages: **{readable} / {checked}**")
    lines.append("")

    findings = _build_priority_findings(run)
    lines.append("## Priority findings\n")
    if findings:
        lines.extend(findings)
    else:
        lines.append("- No high-priority findings detected in this run.")
    lines.append("")

    timings = run.get("timings") or {}
    if timings:
        lines.append("## Timing\n")
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
                    f"- Scores: perf {_pct01_to_pct(scores.get('performance'))}, "
                    f"seo {_pct01_to_pct(scores.get('seo'))}, "
                    f"a11y {_pct01_to_pct(scores.get('accessibility'))}, "
                    f"bp {_pct01_to_pct(scores.get('best-practices'))}"
                )
            arts = r.get("artifacts") or {}
            if arts.get("html_path"):
                lines.append(f"- Lighthouse HTML: `{arts.get('html_path')}`")
            lines.append("")
        if len(quality.get("results") or []) > 20:
            lines.append("_More pages omitted from summary; see quality_summary.json._\n")

    if pw:
        ex = pw.get("extractability_rollup") or {}
        lines.append("## Playwright (HAR + screenshot + extractability)\n")
        lines.append(f"- Pages tested: **{pw.get('pages_tested')}**")
        lines.append(f"- Pages failed: **{pw.get('pages_failed')}**")
        lines.append(f"- JS-disabled readable pages: **{ex.get('pages_js_disabled_readable')}**")
        lines.append(f"- JS-disabled NOT readable pages: **{ex.get('pages_js_disabled_not_readable')}**\n")
        lines.append("Artifacts are under `playwright/`.\n")

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
                    lines.append(
                        f"- **{issue.get('label')}** ({issue.get('severity')}) — {issue.get('count')} page(s) e.g. {ex_s}"
                    )
                else:
                    lines.append(f"- **{issue.get('label')}** ({issue.get('severity')}) — {issue.get('count')} page(s)")
            lines.append("")

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
        lines.append(
            f"- JS-disabled readable pages: **{js.get('pages_js_disabled_readable', 0)} / {js.get('pages_checked', 0)}**"
        )
        lines.append(f"- Pages with noindex: **{((mr.get('noindex_pages') or {}).get('count', 0))}**\n")
        issues = ai.get("issues") or []
        if issues:
            lines.append("### Top AI crawler issues\n")
            for issue in issues[:8]:
                examples = issue.get("examples") or []
                ex_s = ", ".join(examples[:3])
                if ex_s:
                    lines.append(
                        f"- **{issue.get('label')}** ({issue.get('severity')}) — {issue.get('count')} item(s) e.g. {ex_s}"
                    )
                else:
                    lines.append(f"- **{issue.get('label')}** ({issue.get('severity')}) — {issue.get('count')} item(s)")
            lines.append("")

    lines.append("## Artifacts\n")
    lines.append("- `pages.json` — crawl output and per-page metadata")
    lines.append("- `posture.json` — posture / fingerprinting summary")
    lines.append("- `quality_summary.json` — Lighthouse results and budgets")
    if pw:
        lines.append("- `playwright_summary.json` — JS-disabled readability and screenshots/HAR summary")
    lines.append("- `run.json` — machine-readable combined report")
    lines.append("- `run.md` — human-readable combined report\n")

    lines.append("## Next steps\n")
    lines.append("- Prioritize high-severity SEO and AI issues before medium/low findings.")
    lines.append("- Re-run against the same site after fixes and compare with `diff`.")
    lines.append("- Keep `.site_inspector_local/` out of zips and commits for a cleaner handoff.\n")

    return "\n".join(lines)
