from __future__ import annotations

from typing import Any, Dict, List, Optional


# -----------------------------
# Reporting (Run)
# -----------------------------

def build_run_md(run: Dict[str, Any]) -> str:
    url = run.get("target_url")
    host = run.get("host")

    lines: List[str] = []
    lines.append("# Inspector Run (v0.4)\n")
    lines.append(f"- Target: **{url}**")
    lines.append(f"- Host: **{host}**")
    lines.append(f"- Generated: **{run.get('generated_at')}**\n")

    crawl = run.get("crawl")
    if crawl:
        lines.append("## Crawl\n")
        pages = crawl.get("pages") or []
        method = crawl.get("method") or {}
        lines.append(f"- Pages discovered: **{len(pages)}**")
        lines.append(f"- Used sitemap: `{method.get('sitemap_used')}`")
        lines.append(f"- Max pages: `{method.get('max_pages')}`\n")
        for p in pages[:50]:
            lines.append(f"- {p.get('url')}")
        if len(pages) > 50:
            lines.append("- … (truncated)")
        lines.append("")

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

    lines.append("## Next steps\n")
    lines.append("- v0.5: AI readiness checks (llms.txt, JSON-LD validation, citations friendliness).")
    lines.append("- Optional gating: fail CI if too many pages are unreadable with JS disabled.\n")

    return "\n".join(lines)
