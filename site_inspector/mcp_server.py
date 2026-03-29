"""Site Inspector — MCP Server.

Exposes Site Inspector as an MCP tool so any AI assistant (Claude, Cursor,
Windsurf, …) can audit websites directly from a conversation.

Install:
    pip install "site-inspector[mcp]"

Run (stdio transport, for Claude Desktop / claude-code / any MCP client):
    site-inspector-mcp

Claude Desktop config  (~/.claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "site-inspector": {
          "command": "site-inspector-mcp"
        }
      }
    }

Claude Code (add to project or global MCP settings):
    {
      "mcpServers": {
        "site-inspector": {
          "command": "site-inspector-mcp"
        }
      }
    }
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print(
        "[site-inspector] mcp package not found.\n"
        "Install with: pip install 'site-inspector[mcp]'\n"
        "or:           pip install mcp",
        file=sys.stderr,
    )
    sys.exit(1)

from . import __version__
from .crawl import discover_pages
from .posture import collect_posture
from .seo_audit import audit_seo
from .ai_audit import audit_ai_readiness
from .graph import analyze_graph
from .duplicates import detect_duplicate_pages
from .diffing import load_run_dir, diff_runs
from .reporting import build_run_md
from .html_report import build_run_html, build_diff_html
from .utils import normalize_target, host_from_url, safe_write_json, safe_write, now_iso
from .log import get_logger, setup_logging

_log = get_logger("mcp")

mcp = FastMCP(
    "site-inspector",
    instructions=(
        "Site Inspector audits websites: crawl structure, SEO issues, link graph analysis "
        "(PageRank, orphans, dead ends, bottlenecks), AI crawler readiness, Lighthouse quality, "
        "and diff-based change detection between runs.\n\n"
        "Typical workflow:\n"
        "1. inspect_site(url) — full audit, returns findings + output dir path\n"
        "2. diff_site_runs(run_a, run_b) — compare two audits\n"
        "3. load_site_run(run_dir) — reload & summarize an existing run\n"
        "4. site_graph_insights(run_dir) — deep graph metrics from an existing run"
    ),
)


# ------------------------------------------------------------------
# Shared helpers
# ------------------------------------------------------------------

def _auto_out_dir(host: str) -> Path:
    ts = now_iso().replace(":", "").replace("-", "").replace("Z", "")[:15]
    d = Path.cwd() / f"inspect_{host}_{ts}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fmt_issues(issues: List[Dict[str, Any]], label: str) -> str:
    if not issues:
        return f"{label}: none\n"
    lines = [f"{label} ({sum(i.get('count',0) for i in issues)} flagged items):"]
    for i in issues:
        sev = i.get("severity", "?").upper()
        lbl = i.get("label", i.get("code", "issue"))
        cnt = i.get("count", 0)
        ex = i.get("examples") or []
        ex_str = f" — e.g. {', '.join(ex[:3])}" if ex else ""
        lines.append(f"  [{sev}] {lbl} — {cnt} page(s){ex_str}")
    return "\n".join(lines) + "\n"


def _fmt_run_summary(run: Dict[str, Any], out_dir: Path) -> str:
    host = run.get("host") or run.get("target_url") or "?"
    gen = run.get("generated_at") or "?"
    crawl = run.get("crawl") or {}
    pages = crawl.get("pages") or []
    errors = crawl.get("errors") or []
    graph = run.get("graph") or {}
    seo = run.get("seo") or {}
    ai = run.get("ai") or {}
    quality = run.get("quality") or {}
    timings = run.get("timings") or {}

    # Graph metrics
    g_nodes = graph.get("nodes", 0)
    g_edges = graph.get("edges", 0)
    g_density = graph.get("density", 0)
    g_avg_d = graph.get("avg_depth", "?")
    g_max_d = graph.get("max_depth", "?")
    orphans = (graph.get("orphan_pages") or {}).get("count", 0)
    dead = (graph.get("dead_ends") or {}).get("count", 0)
    unreachable = (graph.get("unreachable") or {}).get("count", 0)
    artic = (graph.get("articulation_points") or {}).get("count", 0)

    # Top PageRank pages
    pr_top = (graph.get("pagerank") or {}).get("top") or []
    pr_lines = "\n".join(
        f"  {i+1}. {e['url']} — {e['score']}"
        for i, e in enumerate(pr_top[:5])
    )

    # Lighthouse
    q_results = quality.get("results") or []
    avg_scores: Dict[str, Optional[float]] = {}
    for k in ("performance", "seo", "accessibility", "best-practices"):
        vals = [float(r["scores"][k]) for r in q_results if (r.get("scores") or {}).get(k) is not None]
        avg_scores[k] = round(sum(vals) / len(vals), 2) if vals else None

    def _pct(v: Optional[float]) -> str:
        return f"{round(float(v)*100)}%" if v is not None else "n/a"

    lh_lines = ""
    if q_results:
        lh_lines = (
            f"  Performance: {_pct(avg_scores.get('performance'))} | "
            f"SEO: {_pct(avg_scores.get('seo'))} | "
            f"Accessibility: {_pct(avg_scores.get('accessibility'))} | "
            f"Best Practices: {_pct(avg_scores.get('best-practices'))}\n"
            f"  Pages tested: {quality.get('pages_tested', 0)} | "
            f"Pages failing budget: {quality.get('pages_failed', 0)}\n"
        )
    else:
        lh_lines = "  (not run — use --lighthouse flag or run quality subcommand)\n"

    # AI readiness
    robots = (ai.get("robots") or {}).get("present")
    sitemap = (ai.get("sitemap") or {}).get("present")
    sitemap_urls = (ai.get("sitemap") or {}).get("url_count", 0)

    total_s = timings.get("total_s")
    time_str = f"{total_s:.1f}s" if total_s else "?"

    # All issues combined (for summary score)
    all_issues = (seo.get("issues") or []) + (graph.get("issues") or []) + (ai.get("issues") or [])
    high_count = sum(1 for i in all_issues if i.get("severity") == "high" and i.get("count", 0) > 0)
    med_count = sum(1 for i in all_issues if i.get("severity") == "medium" and i.get("count", 0) > 0)

    status = "✅ No high-severity issues" if high_count == 0 else f"⚠️  {high_count} high-severity issue type(s)"

    out = f"""Site Inspector Report — {host}
Generated: {gen}  |  Version: {__version__}  |  Run time: {time_str}
Output dir: {out_dir}
Status: {status}  ({med_count} medium)

CRAWL
  Pages crawled: {len(pages)}  |  Errors: {len(errors)}

LINK GRAPH
  Nodes: {g_nodes}  |  Edges: {g_edges}  |  Density: {g_density}
  Avg depth from homepage: {g_avg_d} clicks  |  Max depth: {g_max_d} clicks
  Orphan pages (zero inbound): {orphans}
  Dead-end pages (zero outbound): {dead}
  Unreachable from homepage: {unreachable}
  Navigation bottlenecks (articulation points): {artic}

TOP PAGES BY INTERNAL PAGERANK
{pr_lines if pr_lines else "  (no data)"}

LIGHTHOUSE QUALITY
{lh_lines}
AI CRAWLER READINESS
  robots.txt: {"present" if robots else "MISSING"}  |  sitemap.xml: {"present" if sitemap else "MISSING"} ({sitemap_urls} URLs)

"""

    out += _fmt_issues(seo.get("issues") or [], "SEO ISSUES")
    out += "\n"
    out += _fmt_issues(graph.get("issues") or [], "GRAPH ISSUES")
    out += "\n"
    out += _fmt_issues(ai.get("issues") or [], "AI CRAWLER ISSUES")

    out += f"""
REPORTS GENERATED
  HTML (interactive): {out_dir / "run.html"}
  JSON (machine-readable): {out_dir / "run.json"}
  Markdown: {out_dir / "run.md"}
"""
    return out.strip()


def _fmt_diff_summary(diff: Dict[str, Any], out_dir: Path) -> str:
    run_a = diff.get("runA") or {}
    run_b = diff.get("runB") or {}
    passed = diff.get("passed", True)
    fail_reasons = diff.get("fail_reasons") or []
    pages = diff.get("pages") or {}
    quality = diff.get("quality") or {}
    tech = diff.get("tech") or {}
    tp = diff.get("third_parties") or {}

    regressions = quality.get("regressions") or []
    reg_lines = ""
    for r in regressions[:10]:
        url = r.get("url", "?")
        reasons = ", ".join(r.get("reasons") or [])
        deltas = r.get("deltas") or {}
        delta_str = "  ".join(
            f"{k[:4].upper()}:{'+' if float(v)>=0 else ''}{round(float(v)*100)}%"
            for k, v in deltas.items() if v
        )
        reg_lines += f"  {url}\n    {reasons}  [{delta_str}]\n"

    wapp = tech.get("wappalyzer") or {}
    bw = tech.get("builtwith") or {}
    tech_added = list(dict.fromkeys((wapp.get("added") or []) + (bw.get("added") or [])))
    tech_removed = list(dict.fromkeys((wapp.get("removed") or []) + (bw.get("removed") or [])))

    status = "✅ PASS" if passed else "❌ FAIL"
    fail_str = "\n  ".join(fail_reasons) if fail_reasons else "none"

    return f"""Site Inspector Diff Report
{status}
Fail reasons: {fail_str}

RUNS COMPARED
  A: {run_a.get('target_url','?')}  ({run_a.get('generated_at','?')})
  B: {run_b.get('target_url','?')}  ({run_b.get('generated_at','?')})

PAGE CHANGES
  Added: {len(pages.get('added') or [])}
  Removed: {len(pages.get('removed') or [])}
  Unchanged: {len(pages.get('unchanged') or [])}

QUALITY REGRESSIONS ({len(regressions)})
{reg_lines if reg_lines else "  none"}
TECH STACK CHANGES
  Added: {', '.join(tech_added) if tech_added else 'none'}
  Removed: {', '.join(tech_removed) if tech_removed else 'none'}

THIRD-PARTY DOMAINS
  Added: {', '.join(tp.get('added') or []) or 'none'}
  Removed: {', '.join(tp.get('removed') or []) or 'none'}

REPORTS GENERATED
  HTML: {out_dir / "diff.html"}
  JSON: {out_dir / "diff.json"}
  Markdown: {out_dir / "diff.md"}
""".strip()


# ------------------------------------------------------------------
# MCP Tools
# ------------------------------------------------------------------

@mcp.tool()
def inspect_site(
    url: str,
    max_pages: int = 20,
    run_lighthouse: bool = False,
    out_dir: Optional[str] = None,
) -> str:
    """Crawl and audit a website.

    Runs a full technical audit: crawl, posture, SEO, link graph (PageRank,
    orphans, dead ends, bottlenecks), and AI crawler readiness.

    Args:
        url: Target URL to audit (e.g. "https://example.com").
        max_pages: Maximum pages to crawl (default 20, keep low for speed).
        run_lighthouse: Run Lighthouse quality audit (slow, ~30s/page). Default False.
        out_dir: Directory to write output files. Auto-generated if not provided.

    Returns:
        Structured text report with key findings, issue counts, PageRank top pages,
        and paths to the generated run.html / run.json / run.md files.
    """
    try:
        target = normalize_target(url)
    except ValueError as e:
        return f"Error: invalid URL — {e}"

    host = host_from_url(target)

    out = Path(out_dir) if out_dir else _auto_out_dir(host)
    out.mkdir(parents=True, exist_ok=True)

    _log.info("MCP inspect_site: %s → %s", target, out)

    try:
        # 1. Crawl
        crawl = discover_pages(
            target,
            max_pages=max_pages,
            timeout_s=30,
            out_dir=out,
            workers=4,
            resume=False,
        )
        safe_write_json(out / "pages.json", crawl)

        # 2. Posture
        try:
            posture = collect_posture(target, out_dir=out, timeout_s=30)
            safe_write_json(out / "posture.json", posture)
        except Exception as e:
            _log.warning("Posture failed: %s", e)
            posture = {}

        # 3. Lighthouse (optional)
        quality: Dict[str, Any] = {}
        if run_lighthouse:
            try:
                from .lighthouse import quality_for_urls, DEFAULT_BUDGET
                urls = [p["url"] for p in (crawl.get("pages") or [])]
                quality = quality_for_urls(
                    urls, out_dir=out, timeout_s=60,
                    budget=DEFAULT_BUDGET, max_pages=max_pages,
                )
                safe_write_json(out / "quality_summary.json", quality)
            except Exception as e:
                _log.warning("Lighthouse failed: %s", e)
                quality = {"error": str(e)}

        # 4. Assemble run object
        run_obj: Dict[str, Any] = {
            "version": __version__,
            "generated_at": now_iso(),
            "target_url": target,
            "host": host,
            "crawl": crawl,
            "posture": posture,
            "quality": quality,
            "playwright": None,
            "timings": {},
        }

        # 5. Analysis layers
        try:
            run_obj["duplicates"] = detect_duplicate_pages(crawl.get("pages") or [])
        except Exception as e:
            _log.warning("Duplicates failed: %s", e)
            run_obj["duplicates"] = {}

        try:
            run_obj["seo"] = audit_seo(crawl, posture)
        except Exception as e:
            _log.warning("SEO audit failed: %s", e)
            run_obj["seo"] = {"pages_analyzed": 0, "issues": []}

        try:
            run_obj["ai"] = audit_ai_readiness(crawl, posture, None)
        except Exception as e:
            _log.warning("AI audit failed: %s", e)
            run_obj["ai"] = {"pages_analyzed": 0, "issues": []}

        try:
            run_obj["graph"] = analyze_graph(crawl)
        except Exception as e:
            _log.warning("Graph analysis failed: %s", e)
            run_obj["graph"] = {"nodes": 0, "edges": 0}

        # 6. Write outputs
        safe_write_json(out / "run.json", run_obj)

        from .duplicates import render_duplicate_summary_md
        md = build_run_md(run_obj)
        try:
            md = md.rstrip() + "\n\n" + render_duplicate_summary_md(run_obj.get("duplicates") or {})
        except Exception:
            pass
        safe_write(out / "run.md", md)

        try:
            safe_write(out / "run.html", build_run_html(run_obj))
        except Exception as e:
            _log.warning("HTML report failed: %s", e)

        return _fmt_run_summary(run_obj, out)

    except Exception as e:
        _log.error("inspect_site failed: %s", e, exc_info=True)
        return f"Audit failed: {e}"


@mcp.tool()
def diff_site_runs(
    run_a: str,
    run_b: str,
    out_dir: Optional[str] = None,
    score_regression_threshold: float = 0.05,
) -> str:
    """Compare two Site Inspector run directories and report regressions.

    Args:
        run_a: Path to the first (baseline) run directory or its run.json.
        run_b: Path to the second (newer) run directory or its run.json.
        out_dir: Directory to write diff outputs. Defaults to diff_{timestamp}/ in cwd.
        score_regression_threshold: Minimum score drop to flag as a regression (default 0.05 = 5%).

    Returns:
        Structured diff report: page additions/removals, quality regressions with
        score deltas, tech stack changes, new third-party domains, and output file paths.
    """
    try:
        data_a = load_run_dir(Path(run_a))
        data_b = load_run_dir(Path(run_b))
    except FileNotFoundError as e:
        return f"Error loading run: {e}"

    ts = now_iso().replace(":", "").replace("-", "").replace("Z", "")[:15]
    out = Path(out_dir) if out_dir else Path.cwd() / f"diff_{ts}"
    out.mkdir(parents=True, exist_ok=True)

    try:
        diff = diff_runs(data_a, data_b, score_regression_threshold=score_regression_threshold)
        safe_write_json(out / "diff.json", diff)

        from .diffing import render_diff_md
        safe_write(out / "diff.md", render_diff_md(diff))

        try:
            safe_write(out / "diff.html", build_diff_html(diff))
        except Exception as e:
            _log.warning("HTML diff failed: %s", e)

        return _fmt_diff_summary(diff, out)

    except Exception as e:
        _log.error("diff_site_runs failed: %s", e, exc_info=True)
        return f"Diff failed: {e}"


@mcp.tool()
def load_site_run(run_dir: str) -> str:
    """Load and summarize an existing Site Inspector run from disk.

    Useful for re-examining a previously generated audit without re-crawling.

    Args:
        run_dir: Path to a run directory (containing run.json) or the run.json file itself.

    Returns:
        Same structured summary as inspect_site(), loaded from disk.
    """
    try:
        run_obj = load_run_dir(Path(run_dir))
    except FileNotFoundError as e:
        return f"Error: {e}"

    out = Path(run_obj.get("_run_dir", run_dir))
    return _fmt_run_summary(run_obj, out)


@mcp.tool()
def site_graph_insights(run_dir: str) -> str:
    """Return detailed link graph analysis for an existing run.

    Provides PageRank rankings, HITS hub/authority scores, orphan pages,
    dead ends, unreachable pages, navigation bottlenecks (articulation points),
    link silos (strongly connected components), and depth distribution.

    Args:
        run_dir: Path to a run directory or its run.json.

    Returns:
        Full graph metrics formatted for analysis and decision-making.
    """
    try:
        run_obj = load_run_dir(Path(run_dir))
    except FileNotFoundError as e:
        return f"Error: {e}"

    graph = run_obj.get("graph")

    # Re-compute if not present (old run without graph layer)
    if not graph or not graph.get("nodes"):
        crawl = run_obj.get("crawl") or {}
        if not crawl.get("pages"):
            return "No crawl data found in run. Re-run with: inspect_site(url)"
        try:
            graph = analyze_graph(crawl)
        except Exception as e:
            return f"Graph analysis failed: {e}"

    # Format complete graph report
    lines: List[str] = [
        f"Link Graph — {run_obj.get('host') or run_obj.get('target_url') or '?'}",
        f"Run: {run_obj.get('generated_at','?')}",
        "",
        f"STRUCTURE",
        f"  Nodes (pages): {graph.get('nodes')}",
        f"  Edges (internal links): {graph.get('edges')}",
        f"  Graph density: {graph.get('density')}",
        f"  Average depth from homepage: {graph.get('avg_depth')} clicks",
        f"  Maximum depth: {graph.get('max_depth')} clicks",
        "",
        "DEPTH DISTRIBUTION",
    ]
    for depth, count in sorted((graph.get("depth_distribution") or {}).items(), key=lambda x: int(x[0])):
        bar = "█" * min(40, int(count))
        lines.append(f"  depth {depth}: {count:3d}  {bar}")

    lines += ["", "STRUCTURAL ISSUES"]
    for issue in (graph.get("issues") or []):
        sev = issue.get("severity", "?").upper()
        lbl = issue.get("label", "?")
        cnt = issue.get("count", 0)
        ex = issue.get("examples") or []
        ex_str = f"\n    e.g. {', '.join(ex[:5])}" if ex else ""
        lines.append(f"  [{sev}] {lbl} — {cnt} page(s){ex_str}")

    lines += ["", "TOP PAGES BY INTERNAL PAGERANK"]
    for i, e in enumerate((graph.get("pagerank") or {}).get("top") or [])[:10]:
        lines.append(f"  {i+1:2}. {e['url']}  score={e['score']}")

    lines += ["", "TOP HUB PAGES (distribute link equity effectively)"]
    for e in ((graph.get("hits") or {}).get("top_hubs") or [])[:5]:
        if e.get("score", 0) > 0:
            lines.append(f"  {e['url']}  hub={e['score']:.4f}")

    lines += ["", "TOP AUTHORITY PAGES (receive link equity)"]
    for e in ((graph.get("hits") or {}).get("top_authorities") or [])[:5]:
        if e.get("score", 0) > 0:
            lines.append(f"  {e['url']}  authority={e['score']:.4f}")

    orphans = (graph.get("orphan_pages") or {}).get("urls") or []
    if orphans:
        lines += ["", f"ORPHAN PAGES ({len(orphans)} — no inbound links, hard to discover)"]
        for u in orphans[:10]:
            lines.append(f"  {u}")

    dead = (graph.get("dead_ends") or {}).get("urls") or []
    if dead:
        lines += ["", f"DEAD-END PAGES ({len(dead)} — no outbound links, traps users)"]
        for u in dead[:10]:
            lines.append(f"  {u}")

    unreachable = (graph.get("unreachable") or {}).get("urls") or []
    if unreachable:
        lines += ["", f"UNREACHABLE FROM HOMEPAGE ({len(unreachable)})"]
        for u in unreachable[:10]:
            lines.append(f"  {u}")

    artic = (graph.get("articulation_points") or {}).get("urls") or []
    if artic:
        lines += ["", f"NAVIGATION BOTTLENECKS ({len(artic)} articulation points)"]
        lines.append("  (Removing these pages would disconnect parts of the site)")
        for u in artic[:10]:
            lines.append(f"  {u}")

    sccs = (graph.get("strongly_connected_components") or {}).get("components") or []
    if sccs:
        lines += ["", f"LINK SILOS — {len(sccs)} strongly connected component(s)"]
        for i, scc in enumerate(sccs[:5]):
            lines.append(f"  Silo {i+1} ({len(scc)} pages): {', '.join(scc[:4])}" + (" …" if len(scc) > 4 else ""))

    return "\n".join(lines)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main() -> None:
    setup_logging()
    mcp.run()


if __name__ == "__main__":
    main()
