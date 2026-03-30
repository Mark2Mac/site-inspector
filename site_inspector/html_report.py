"""Interactive self-contained HTML report generator.

Produces a single .html file with embedded CSS, SVG charts, and data.
Zero external dependencies — works fully offline.
"""

from __future__ import annotations

import html
import json
import math
from typing import Any, Dict, List, Optional

from . import __version__


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _esc(s: Any) -> str:
    return html.escape(str(s) if s is not None else "")


def _score_color(v: Optional[float]) -> str:
    if v is None:
        return "#94a3b8"
    if v >= 0.90:
        return "#22c55e"
    if v >= 0.50:
        return "#f59e0b"
    return "#ef4444"


def _score_label(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    if v >= 0.90:
        return "Good"
    if v >= 0.50:
        return "Needs work"
    return "Poor"


def _sev_color(sev: str) -> str:
    return {"high": "#ef4444", "medium": "#f59e0b", "low": "#3b82f6"}.get(sev, "#94a3b8")


def _sev_bg(sev: str) -> str:
    return {"high": "#fef2f2", "medium": "#fffbeb", "low": "#eff6ff"}.get(sev, "#f8fafc")


def _pct(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    try:
        return f"{round(float(v) * 100)}%"
    except Exception:
        return "n/a"


def _num(v: Any, fallback: str = "—") -> str:
    if v is None:
        return fallback
    try:
        return str(int(v))
    except Exception:
        return str(v)


# ------------------------------------------------------------------
# SVG Charts
# ------------------------------------------------------------------

def _svg_radar(scores: Dict[str, Optional[float]]) -> str:
    """Generate a Lighthouse radar chart as inline SVG."""
    cx, cy, r = 130, 130, 90
    W, H = 260, 260

    cats = ["performance", "seo", "accessibility", "best-practices"]
    labels = ["Performance", "SEO", "Accessibility", "Best Practices"]
    angles = [-math.pi / 2, 0, math.pi / 2, math.pi]

    parts: List[str] = [f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg">']

    # Background grid rings
    for pct in [0.25, 0.5, 0.75, 1.0]:
        pts = " ".join(
            f"{cx + pct * r * math.cos(a):.1f},{cy + pct * r * math.sin(a):.1f}"
            for a in angles
        )
        parts.append(f'<polygon points="{pts}" fill="none" stroke="#e2e8f0" stroke-width="1"/>')
        # Ring label
        lx = cx + pct * r * math.cos(-math.pi / 2)
        ly = cy + pct * r * math.sin(-math.pi / 2) - 4
        parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" font-size="8" fill="#94a3b8">{round(pct*100)}%</text>')

    # Axis lines
    for a in angles:
        parts.append(
            f'<line x1="{cx}" y1="{cy}" x2="{cx + r * math.cos(a):.1f}" y2="{cy + r * math.sin(a):.1f}"'
            f' stroke="#e2e8f0" stroke-width="1"/>'
        )

    # Data polygon
    vals = [max(0.0, min(1.0, float(scores.get(k) or 0.0))) for k in cats]
    data_pts = " ".join(
        f"{cx + v * r * math.cos(a):.1f},{cy + v * r * math.sin(a):.1f}"
        for v, a in zip(vals, angles)
    )
    parts.append(f'<polygon points="{data_pts}" fill="rgba(59,130,246,0.15)" stroke="#3b82f6" stroke-width="2"/>')

    # Data dots + labels
    lr = r + 26
    for label, k, a, v in zip(labels, cats, angles, vals):
        dx = cx + v * r * math.cos(a)
        dy = cy + v * r * math.sin(a)
        color = _score_color(v)
        parts.append(f'<circle cx="{dx:.1f}" cy="{dy:.1f}" r="5" fill="{color}" stroke="white" stroke-width="2"/>')

        lx = cx + lr * math.cos(a)
        ly = cy + lr * math.sin(a)
        anchor = "middle"
        if abs(a) < 0.1:
            anchor = "start"
            lx += 4
        elif abs(abs(a) - math.pi) < 0.1:
            anchor = "end"
            lx -= 4
        parts.append(
            f'<text x="{lx:.1f}" y="{ly - 6:.1f}" text-anchor="{anchor}" font-size="9"'
            f' font-family="system-ui,sans-serif" fill="#475569">{_esc(label)}</text>'
        )
        parts.append(
            f'<text x="{lx:.1f}" y="{ly + 7:.1f}" text-anchor="{anchor}" font-size="11"'
            f' font-weight="700" font-family="system-ui,sans-serif" fill="{color}">{_pct(v)}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def _svg_depth_bars(dist: Dict[int, int]) -> str:
    """Generate a horizontal bar chart for crawl depth distribution."""
    if not dist:
        return "<p class='muted'>No depth data.</p>"

    max_count = max(dist.values()) or 1
    bar_h = 22
    gap = 6
    label_w = 60
    bar_max_w = 240
    W = label_w + bar_max_w + 60
    H = len(dist) * (bar_h + gap) + 20

    parts: List[str] = [f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg">']

    for i, (depth, count) in enumerate(sorted(dist.items())):
        y = i * (bar_h + gap) + 10
        bar_w = max(4, int(bar_max_w * count / max_count))
        depth_color = "#22c55e" if depth <= 1 else "#f59e0b" if depth <= 3 else "#ef4444"
        label = f"Depth {depth}"
        parts.append(
            f'<rect x="{label_w}" y="{y}" width="{bar_w}" height="{bar_h}"'
            f' rx="4" fill="{depth_color}" opacity="0.85"/>'
        )
        parts.append(
            f'<text x="{label_w - 6}" y="{y + bar_h//2 + 1}" text-anchor="end"'
            f' dominant-baseline="middle" font-size="11" font-family="system-ui,sans-serif" fill="#475569">{_esc(label)}</text>'
        )
        parts.append(
            f'<text x="{label_w + bar_w + 6}" y="{y + bar_h//2 + 1}"'
            f' dominant-baseline="middle" font-size="11" font-weight="600" font-family="system-ui,sans-serif" fill="#1e293b">{count}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


# ------------------------------------------------------------------
# CSS
# ------------------------------------------------------------------

def _css() -> str:
    return """
:root {
  --bg: #f8fafc;
  --card: #ffffff;
  --border: #e2e8f0;
  --text: #0f172a;
  --muted: #64748b;
  --primary: #3b82f6;
  --header-bg: #1e293b;
  --header-text: #f8fafc;
  --good: #22c55e;
  --warn: #f59e0b;
  --danger: #ef4444;
  --radius: 10px;
  --shadow: 0 1px 4px rgba(0,0,0,.07), 0 4px 12px rgba(0,0,0,.05);
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: system-ui, -apple-system, sans-serif;
  background: var(--bg);
  color: var(--text);
  font-size: 14px;
  line-height: 1.6;
}
a { color: var(--primary); text-decoration: none; }
a:hover { text-decoration: underline; }
code { background: #f1f5f9; border-radius: 4px; padding: 1px 5px; font-size: 12px; font-family: ui-monospace, monospace; }

/* Header */
.report-header {
  background: var(--header-bg);
  color: var(--header-text);
  padding: 28px 36px 22px;
}
.report-header h1 { font-size: 22px; font-weight: 700; margin-bottom: 4px; }
.report-header .meta { color: #94a3b8; font-size: 13px; display: flex; gap: 20px; flex-wrap: wrap; margin-top: 8px; }
.badge {
  display: inline-block; padding: 2px 10px; border-radius: 20px;
  font-size: 12px; font-weight: 600; letter-spacing: .3px;
}
.badge-pass { background: #dcfce7; color: #15803d; }
.badge-fail { background: #fee2e2; color: #b91c1c; }
.badge-neutral { background: #f1f5f9; color: #475569; }

/* Main layout */
.report-main { max-width: 1100px; margin: 0 auto; padding: 28px 24px 48px; display: flex; flex-direction: column; gap: 22px; }

/* Cards */
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  overflow: hidden;
}
.card-header {
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 10px;
  background: #fcfcfd;
}
.card-header h2 { font-size: 15px; font-weight: 700; }
.card-header .card-count { margin-left: auto; font-size: 12px; color: var(--muted); }
.card-body { padding: 18px 20px; }

/* Metric grid */
.metric-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 14px; }
.metric-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  box-shadow: var(--shadow);
  border-top: 3px solid var(--primary);
}
.metric-card.good { border-top-color: var(--good); }
.metric-card.warn { border-top-color: var(--warn); }
.metric-card.danger { border-top-color: var(--danger); }
.metric-card .label { font-size: 11px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .5px; }
.metric-card .value { font-size: 28px; font-weight: 800; color: var(--text); line-height: 1.2; margin-top: 4px; }
.metric-card .note { font-size: 11px; color: var(--muted); margin-top: 3px; }

/* Issues list */
.issues-list { list-style: none; display: flex; flex-direction: column; gap: 8px; }
.issue-item {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 10px 14px; border-radius: 8px;
}
.sev-badge {
  min-width: 56px; text-align: center; padding: 2px 8px;
  border-radius: 12px; font-size: 10px; font-weight: 700;
  text-transform: uppercase; letter-spacing: .4px; flex-shrink: 0;
}
.issue-label { font-weight: 600; font-size: 13px; }
.issue-count { font-size: 12px; color: var(--muted); }
.issue-examples { font-size: 11px; color: var(--muted); margin-top: 2px; }
.issue-examples code { font-size: 10px; word-break: break-all; }

/* Scores row */
.scores-row { display: flex; flex-wrap: wrap; gap: 20px; align-items: flex-start; }
.score-circle {
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  min-width: 70px;
}
.score-ring {
  position: relative; width: 64px; height: 64px;
}
.score-ring svg { transform: rotate(-90deg); }
.score-ring .score-text {
  position: absolute; inset: 0; display: flex;
  align-items: center; justify-content: center;
  font-size: 15px; font-weight: 800;
}
.score-label { font-size: 11px; color: var(--muted); font-weight: 600; text-align: center; }

/* Collapsed details */
details summary {
  cursor: pointer; list-style: none; padding: 12px 20px;
  font-weight: 600; font-size: 13px; color: var(--muted);
  border-top: 1px solid var(--border); user-select: none;
}
details summary::-webkit-details-marker { display: none; }
details summary::before { content: "▶ "; font-size: 10px; }
details[open] summary::before { content: "▼ "; }
details .details-body { padding: 0 20px 18px; }

/* Table */
.data-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.data-table th { background: #f8fafc; padding: 8px 10px; text-align: left; font-weight: 600; color: var(--muted); border-bottom: 1px solid var(--border); }
.data-table td { padding: 7px 10px; border-bottom: 1px solid #f1f5f9; vertical-align: top; }
.data-table tr:last-child td { border-bottom: none; }
.data-table tr:hover td { background: #f8fafc; }
.status-ok { color: var(--good); font-weight: 700; }
.status-err { color: var(--danger); font-weight: 700; }
.status-redir { color: var(--warn); font-weight: 700; }
.truncate { max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Graph section */
.graph-split { display: flex; flex-wrap: wrap; gap: 24px; align-items: flex-start; }
.graph-metrics { flex: 1; min-width: 200px; display: flex; flex-direction: column; gap: 8px; }
.graph-metric-row { display: flex; justify-content: space-between; padding: 7px 0; border-bottom: 1px solid var(--border); font-size: 13px; }
.graph-metric-row:last-child { border-bottom: none; }
.graph-metric-label { color: var(--muted); }
.graph-metric-value { font-weight: 700; }

/* Diff specifics */
.diff-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.diff-tag { display: inline-block; padding: 1px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; margin-right: 4px; }
.diff-added { background: #dcfce7; color: #15803d; }
.diff-removed { background: #fee2e2; color: #b91c1c; }
.diff-unchanged { background: #f1f5f9; color: #475569; }
.delta-bar { display: inline-block; height: 10px; border-radius: 3px; min-width: 4px; vertical-align: middle; }

/* Footer */
.report-footer {
  background: var(--header-bg); color: #94a3b8;
  text-align: center; padding: 18px 24px;
  font-size: 12px; margin-top: 40px;
}
.report-footer a { color: #cbd5e1; }
.muted { color: var(--muted); font-size: 12px; }

@media (max-width: 600px) {
  .report-header { padding: 18px 16px; }
  .report-main { padding: 16px 12px 40px; }
  .metric-grid { grid-template-columns: 1fr 1fr; }
  .diff-cols { grid-template-columns: 1fr; }
}
@media print {
  body { background: white; }
  .card { box-shadow: none; border: 1px solid #ddd; }
  details { display: block; }
  details summary { display: none; }
  details .details-body { display: block; padding-top: 0; }
}
"""


# ------------------------------------------------------------------
# Component builders
# ------------------------------------------------------------------

def _score_ring(score: Optional[float], label: str) -> str:
    v = float(score) if score is not None else 0.0
    color = _score_color(score)
    pct_text = _pct(score)
    circumference = 2 * math.pi * 26
    dash = circumference * v
    return f"""
<div class="score-circle">
  <div class="score-ring">
    <svg width="64" height="64" viewBox="0 0 64 64">
      <circle cx="32" cy="32" r="26" fill="none" stroke="#e2e8f0" stroke-width="6"/>
      <circle cx="32" cy="32" r="26" fill="none" stroke="{color}" stroke-width="6"
        stroke-dasharray="{dash:.2f} {circumference:.2f}" stroke-linecap="round"/>
    </svg>
    <div class="score-text" style="color:{color}">{pct_text}</div>
  </div>
  <div class="score-label">{_esc(label)}</div>
</div>"""


def _metric_card(label: str, value: Any, note: str = "", accent: str = "") -> str:
    cls = f"metric-card {accent}" if accent else "metric-card"
    note_html = f'<div class="note">{_esc(note)}</div>' if note else ""
    return f"""
<div class="{cls}">
  <div class="label">{_esc(label)}</div>
  <div class="value">{_esc(str(value))}</div>
  {note_html}
</div>"""


def _issue_item(issue: Dict[str, Any], show_source: bool = False) -> str:
    sev = (issue.get("severity") or "low").lower()
    color = _sev_color(sev)
    bg = _sev_bg(sev)
    label = issue.get("label") or issue.get("code") or "Issue"
    count = issue.get("count", 0)
    source = f' <span class="muted">({_esc(issue.get("source",""))})</span>' if show_source and issue.get("source") else ""
    examples = issue.get("examples") or []
    ex_html = ""
    if examples:
        ex_html = '<div class="issue-examples">' + " ".join(
            f"<code>{_esc(e)}</code>" for e in examples[:4]
        ) + "</div>"
    return f"""
<li class="issue-item" style="background:{bg}">
  <span class="sev-badge" style="background:{color}22;color:{color}">{_esc(sev)}</span>
  <div>
    <div class="issue-label">{_esc(label)}{source}</div>
    <div class="issue-count">{count} page(s)</div>
    {ex_html}
  </div>
</li>"""


# ------------------------------------------------------------------
# Run report sections
# ------------------------------------------------------------------

def _section_header(run: Dict[str, Any]) -> str:
    host = _esc(run.get("host") or run.get("target_url") or "")
    target = _esc(run.get("target_url") or "")
    gen = _esc(run.get("generated_at") or "")
    v = _esc(run.get("version") or __version__)
    pages = len((run.get("crawl") or {}).get("pages") or [])

    # Count all issues
    total_issues = sum(
        len([i for i in (run.get(k) or {}).get("issues", []) if i.get("count", 0) > 0])
        for k in ("seo", "ai", "graph")
    )
    status_class = "badge-pass" if total_issues == 0 else "badge-fail"
    status_text = "No issues" if total_issues == 0 else f"{total_issues} issue type(s)"

    return f"""
<header class="report-header">
  <h1>Site Inspector — {host}</h1>
  <div style="margin-top:8px">
    <a href="{target}" style="color:#93c5fd;font-size:13px">{target}</a>
  </div>
  <div class="meta">
    <span>Generated {gen}</span>
    <span>Site Inspector v{v}</span>
    <span>{pages} pages crawled</span>
    <span class="badge {status_class}">{status_text}</span>
  </div>
</header>"""


def _section_summary(run: Dict[str, Any]) -> str:
    crawl = run.get("crawl") or {}
    pages = crawl.get("pages") or []
    errors = crawl.get("errors") or []
    graph = run.get("graph") or {}
    seo = run.get("seo") or {}
    quality = run.get("quality") or {}
    timings = run.get("timings") or {}

    n_pages = len(pages)
    n_errors = len(errors)
    n_orphans = (graph.get("orphan_pages") or {}).get("count", 0)
    n_seo_issues = sum(i.get("count", 0) for i in (seo.get("issues") or []))
    q_results = quality.get("results") or []
    avg_perf = None
    if q_results:
        perfs = [float(r["scores"]["performance"]) for r in q_results if (r.get("scores") or {}).get("performance") is not None]
        if perfs:
            avg_perf = sum(perfs) / len(perfs)

    total_s = timings.get("total_s")
    time_str = f"{total_s:.1f}s" if total_s else "—"

    orphan_accent = "danger" if n_orphans > 0 else "good"
    error_accent = "danger" if n_errors > 0 else "good"
    seo_accent = "danger" if n_seo_issues > 5 else "warn" if n_seo_issues > 0 else "good"

    perf_accent = "good" if avg_perf and avg_perf >= 0.9 else "warn" if avg_perf and avg_perf >= 0.5 else "danger" if avg_perf else ""

    return f"""
<div class="metric-grid">
  {_metric_card("Pages Crawled", n_pages, "")}
  {_metric_card("Crawl Errors", n_errors, "", error_accent)}
  {_metric_card("SEO Issues", n_seo_issues, "total flagged items", seo_accent)}
  {_metric_card("Orphan Pages", n_orphans, "zero inbound links", orphan_accent)}
  {_metric_card("Avg Performance", _pct(avg_perf), "Lighthouse", perf_accent)}
  {_metric_card("Run Time", time_str, "")}
</div>"""


def _section_priority_findings(run: Dict[str, Any]) -> str:
    findings: List[Dict[str, Any]] = []
    sev_rank = {"high": 0, "medium": 1, "low": 2}

    dup = run.get("duplicates") or {}
    actionable = int((dup.get("validation") or {}).get("actionable_groups") or 0)
    if actionable:
        findings.append({"severity": "medium", "source": "Duplicates", "label": "Actionable duplicate groups", "count": actionable, "examples": []})

    for source, key in (("SEO", "seo"), ("AI", "ai"), ("Graph", "graph")):
        for issue in ((run.get(key) or {}).get("issues") or []):
            if int(issue.get("count") or 0) > 0:
                findings.append({**issue, "source": source})

    findings.sort(key=lambda i: (sev_rank.get(i.get("severity", "low"), 99), -(i.get("count") or 0)))

    if not findings:
        return '<div class="card"><div class="card-body" style="color:var(--good);font-weight:600">✓ No priority findings detected.</div></div>'

    items = "\n".join(_issue_item(f, show_source=True) for f in findings[:12])
    return f"""
<div class="card">
  <div class="card-header">
    <h2>Priority Findings</h2>
    <span class="card-count">{len(findings)} issue type(s)</span>
  </div>
  <div class="card-body">
    <ul class="issues-list">{items}</ul>
  </div>
</div>"""


def _section_lighthouse(run: Dict[str, Any]) -> str:
    quality = run.get("quality") or {}
    results = quality.get("results") or []

    if not results:
        return ""

    # Aggregate scores across all tested pages
    agg: Dict[str, List[float]] = {"performance": [], "seo": [], "accessibility": [], "best-practices": []}
    for r in results:
        scores = r.get("scores") or {}
        for k in agg:
            v = scores.get(k)
            if v is not None:
                agg[k].append(float(v))

    avg_scores = {k: (sum(vs) / len(vs) if vs else None) for k, vs in agg.items()}

    radar_svg = _svg_radar(avg_scores)
    rings = "".join(
        _score_ring(avg_scores.get(k), lbl)
        for k, lbl in [("performance", "Perf"), ("seo", "SEO"), ("accessibility", "A11y"), ("best-practices", "Best Pract.")]
    )

    # Per-page table (inside details)
    rows = ""
    for r in results[:50]:
        url = r.get("url") or ""
        sc = r.get("scores") or {}
        budget = r.get("budget_eval") or {}
        passed = budget.get("passed", True)
        status = '<span class="badge badge-pass">pass</span>' if passed else '<span class="badge badge-fail">fail</span>'
        rows += f"""
<tr>
  <td class="truncate"><a href="{_esc(url)}">{_esc(url)}</a></td>
  <td style="color:{_score_color(sc.get('performance'))}">{_pct(sc.get('performance'))}</td>
  <td style="color:{_score_color(sc.get('seo'))}">{_pct(sc.get('seo'))}</td>
  <td style="color:{_score_color(sc.get('accessibility'))}">{_pct(sc.get('accessibility'))}</td>
  <td style="color:{_score_color(sc.get('best-practices'))}">{_pct(sc.get('best-practices'))}</td>
  <td>{status}</td>
</tr>"""

    tested = quality.get("pages_tested", 0)
    failed = quality.get("pages_failed", 0)
    overall = "badge-pass" if failed == 0 else "badge-fail"
    overall_text = "All pass" if failed == 0 else f"{failed} failing"

    return f"""
<div class="card">
  <div class="card-header">
    <h2>Lighthouse Quality</h2>
    <span class="badge {overall}">{overall_text}</span>
    <span class="card-count">{tested} page(s) tested</span>
  </div>
  <div class="card-body">
    <div class="scores-row" style="justify-content:space-between;align-items:center;flex-wrap:wrap;gap:24px">
      <div>{radar_svg}</div>
      <div style="display:flex;flex-wrap:wrap;gap:16px">{rings}</div>
    </div>
  </div>
  <details>
    <summary>Per-page results ({len(results)})</summary>
    <div class="details-body">
      <table class="data-table">
        <thead><tr><th>URL</th><th>Perf</th><th>SEO</th><th>A11y</th><th>Best Pract.</th><th>Budget</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  </details>
</div>"""


def _section_graph(run: Dict[str, Any]) -> str:
    graph = run.get("graph") or {}
    if not graph.get("nodes"):
        return ""

    depth_dist = graph.get("depth_distribution") or {}
    depth_svg = _svg_depth_bars({int(k): v for k, v in depth_dist.items()})

    metrics = [
        ("Pages (nodes)", _num(graph.get("nodes"))),
        ("Internal links (edges)", _num(graph.get("edges"))),
        ("Graph density", str(graph.get("density", "—"))),
        ("Avg depth from homepage", f"{graph.get('avg_depth', '—')} clicks"),
        ("Max depth", f"{graph.get('max_depth', '—')} clicks"),
        ("Orphan pages", _num((graph.get("orphan_pages") or {}).get("count"))),
        ("Dead-end pages", _num((graph.get("dead_ends") or {}).get("count"))),
        ("Pages > 3 clicks deep", _num((graph.get("deep_pages") or {}).get("count"))),
        ("Unreachable from homepage", _num((graph.get("unreachable") or {}).get("count"))),
        ("Navigation bottlenecks", _num((graph.get("articulation_points") or {}).get("count"))),
        ("Link silos (SCCs)", _num((graph.get("strongly_connected_components") or {}).get("count"))),
    ]
    metrics_html = "\n".join(
        f'<div class="graph-metric-row"><span class="graph-metric-label">{_esc(l)}</span><span class="graph-metric-value">{_esc(v)}</span></div>'
        for l, v in metrics
    )

    # Top PageRank table
    pr_top = (graph.get("pagerank") or {}).get("top") or []
    pr_rows = "".join(
        f'<tr><td class="truncate"><a href="{_esc(e["url"])}">{_esc(e["url"])}</a></td>'
        f'<td style="font-family:monospace;font-size:11px">{e["score"]}</td></tr>'
        for e in pr_top[:10]
    )
    pr_table = f"""
<table class="data-table" style="margin-top:12px">
  <thead><tr><th>URL</th><th>PageRank</th></tr></thead>
  <tbody>{pr_rows}</tbody>
</table>""" if pr_rows else ""

    # Top Hub scores
    hubs = (graph.get("hits") or {}).get("top_hubs") or []
    hub_rows = "".join(
        f'<tr><td class="truncate"><a href="{_esc(e["url"])}">{_esc(e["url"])}</a></td>'
        f'<td style="font-family:monospace;font-size:11px">{e["score"]}</td></tr>'
        for e in hubs[:8] if e.get("score", 0) > 0
    )
    hub_table = f"""
<table class="data-table">
  <thead><tr><th>Hub URL</th><th>Hub Score</th></tr></thead>
  <tbody>{hub_rows}</tbody>
</table>""" if hub_rows else ""

    graph_issues = graph.get("issues") or []
    issues_html = ""
    if graph_issues:
        items = "\n".join(_issue_item(i) for i in graph_issues)
        issues_html = f'<ul class="issues-list" style="margin-top:16px">{items}</ul>'

    return f"""
<div class="card">
  <div class="card-header">
    <h2>Link Graph</h2>
    <span class="card-count">{_num(graph.get('nodes'))} nodes · {_num(graph.get('edges'))} edges</span>
  </div>
  <div class="card-body">
    <div class="graph-split">
      <div class="graph-metrics">{metrics_html}</div>
      <div>{depth_svg}</div>
    </div>
    {issues_html}
  </div>
  <details>
    <summary>Top pages by internal PageRank</summary>
    <div class="details-body">{pr_table}</div>
  </details>
  <details>
    <summary>Top hub pages (navigation quality)</summary>
    <div class="details-body">{hub_table}</div>
  </details>
</div>"""


def _section_seo(run: Dict[str, Any]) -> str:
    seo = run.get("seo") or {}
    issues = seo.get("issues") or []
    if not issues:
        return ""

    items = "\n".join(_issue_item(i) for i in issues)
    n = seo.get("pages_analyzed", 0)

    return f"""
<div class="card">
  <div class="card-header">
    <h2>SEO Audit</h2>
    <span class="card-count">{n} pages analyzed</span>
  </div>
  <div class="card-body">
    <ul class="issues-list">{items}</ul>
  </div>
</div>"""


def _section_ai(run: Dict[str, Any]) -> str:
    ai = run.get("ai") or {}
    issues = ai.get("issues") or []
    robots = ai.get("robots") or {}
    sitemap = ai.get("sitemap") or {}

    r_ok = robots.get("present")
    s_ok = sitemap.get("present")
    s_count = sitemap.get("url_count", 0)

    meta_html = f"""
<div style="display:flex;gap:20px;flex-wrap:wrap;margin-bottom:14px;font-size:13px">
  <span>robots.txt: <strong style="color:{'var(--good)' if r_ok else 'var(--danger)'}">{('present' if r_ok else 'missing')}</strong></span>
  <span>sitemap: <strong style="color:{'var(--good)' if s_ok else 'var(--danger)'}">{('present' if s_ok else 'missing')}</strong></span>
  {f'<span>sitemap URLs: <strong>{s_count}</strong></span>' if s_ok else ''}
</div>"""

    issues_html = ""
    if issues:
        items = "\n".join(_issue_item(i) for i in issues)
        issues_html = f'<ul class="issues-list">{items}</ul>'
    else:
        issues_html = '<p class="muted">No AI crawler issues detected.</p>'

    n = ai.get("pages_analyzed", 0)
    return f"""
<div class="card">
  <div class="card-header">
    <h2>AI Crawler Readiness</h2>
    <span class="card-count">{n} pages analyzed</span>
  </div>
  <div class="card-body">
    {meta_html}
    {issues_html}
  </div>
</div>"""


def _section_duplicates(run: Dict[str, Any]) -> str:
    dup = run.get("duplicates") or {}
    groups = dup.get("duplicate_groups") or []
    validation = dup.get("validation") or {}
    actionable = validation.get("actionable_groups", 0)
    if not groups:
        return ""

    buckets = dup.get("confidence_buckets") or {}
    bucket_html = " &nbsp;".join(
        f'<span class="badge badge-neutral">{k.capitalize()}: {v}</span>'
        for k, v in buckets.items() if v
    )

    rows = ""
    for g in groups[:30]:
        conf = g.get("confidence_bucket", "—")
        cnt = g.get("count", 0)
        method = g.get("method", "—")
        titles = ", ".join(_esc(t) for t in (g.get("titles") or [])[:2])
        examples = (g.get("page_ids") or [])
        rows += f"""
<tr>
  <td><span class="badge badge-neutral">{_esc(conf)}</span></td>
  <td>{cnt}</td>
  <td>{_esc(method)}</td>
  <td class="truncate" title="{titles}">{titles}</td>
</tr>"""

    return f"""
<div class="card">
  <div class="card-header">
    <h2>Duplicate Detection</h2>
    <span class="card-count">{len(groups)} groups · {actionable} actionable</span>
  </div>
  <div class="card-body">
    <div style="margin-bottom:12px">{bucket_html}</div>
  </div>
  <details>
    <summary>Duplicate groups ({len(groups)})</summary>
    <div class="details-body">
      <table class="data-table">
        <thead><tr><th>Confidence</th><th>Pages</th><th>Method</th><th>Titles</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  </details>
</div>"""


def _section_crawl(run: Dict[str, Any]) -> str:
    crawl = run.get("crawl") or {}
    pages = crawl.get("pages") or []
    errors = crawl.get("errors") or []
    graph = run.get("graph") or {}

    # Build pagerank index for enriching table
    pr_index: Dict[str, float] = {}
    for entry in ((graph.get("pagerank") or {}).get("top") or []):
        pr_index[entry["url"]] = entry["score"]

    rows = ""
    for p in pages[:100]:
        url = p.get("url") or ""
        status = p.get("status_code")
        title = p.get("title") or ""
        rc = int(p.get("redirect_count") or 0)
        inlinks = p.get("internal_link_count") or 0
        pr = pr_index.get(url)
        status_cls = "status-ok" if status == 200 else "status-redir" if rc > 0 else "status-err"
        rows += f"""
<tr>
  <td class="truncate"><a href="{_esc(url)}">{_esc(url)}</a></td>
  <td class="{status_cls}">{_esc(str(status) if status else '—')}</td>
  <td class="truncate">{_esc(title)}</td>
  <td>{inlinks}</td>
  <td>{f"{pr:.5f}" if pr else "—"}</td>
</tr>"""

    error_rows = ""
    for e in errors[:20]:
        error_rows += f"""
<tr>
  <td class="truncate"><a href="{_esc(e.get('url',''))}">{_esc(e.get('url',''))}</a></td>
  <td class="status-err">{_esc(str(e.get('status_code') or '—'))}</td>
  <td>{_esc(e.get('error',''))}</td>
</tr>"""

    error_section = f"""
  <details>
    <summary style="color:var(--danger)">Crawl errors ({len(errors)})</summary>
    <div class="details-body">
      <table class="data-table">
        <thead><tr><th>URL</th><th>Status</th><th>Error</th></tr></thead>
        <tbody>{error_rows}</tbody>
      </table>
    </div>
  </details>""" if errors else ""

    return f"""
<div class="card">
  <div class="card-header">
    <h2>Crawl Details</h2>
    <span class="card-count">{len(pages)} pages</span>
  </div>
  <details>
    <summary>All crawled pages ({min(len(pages), 100)} shown)</summary>
    <div class="details-body">
      <table class="data-table">
        <thead><tr><th>URL</th><th>Status</th><th>Title</th><th>Inlinks</th><th>PageRank</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  </details>
  {error_section}
</div>"""


def _section_posture(run: Dict[str, Any]) -> str:
    posture = run.get("posture") or {}
    fp = posture.get("fingerprinting") or {}
    tls = posture.get("tls") or {}
    http = posture.get("http") or {}

    tls_html = ""
    if tls:
        protocol = tls.get("protocol") or "—"
        cipher = tls.get("cipher")
        cipher_str = f"{cipher[0]} ({cipher[1]} bit)" if cipher and len(cipher) >= 2 else "—"
        tls_html = f'<p style="font-size:13px;margin-bottom:10px">TLS: <strong>{_esc(protocol)}</strong> · Cipher: <code>{_esc(cipher_str)}</code></p>'

    third_parties = fp.get("third_party_domains") or []
    tp_html = ""
    if third_parties:
        tp_html = "<div style='margin-top:8px'><strong style='font-size:12px'>Third-party domains:</strong><br>" + \
            " ".join(f"<code>{_esc(d)}</code>" for d in third_parties[:30]) + "</div>"

    wapp = (fp.get("tech") or {}).get("wappalyzer") or {}
    bw = (fp.get("tech") or {}).get("builtwith") or {}
    tech_items = list(wapp.keys()) if isinstance(wapp, dict) else []
    for cat, items in (bw.items() if isinstance(bw, dict) else []):
        tech_items.extend(items if isinstance(items, list) else [])
    tech_items = list(dict.fromkeys(tech_items))  # dedupe preserving order

    tech_html = ""
    if tech_items:
        tech_html = "<div style='margin-top:12px'><strong style='font-size:12px'>Detected technologies:</strong><br>" + \
            " ".join(f"<span class='badge badge-neutral'>{_esc(t)}</span>" for t in tech_items[:40]) + "</div>"

    return f"""
<div class="card">
  <div class="card-header"><h2>Posture &amp; Tech Stack</h2></div>
  <div class="card-body">
    {tls_html}
    {tech_html}
    {tp_html}
  </div>
</div>"""


# ------------------------------------------------------------------
# Diff report sections
# ------------------------------------------------------------------

def _diff_summary_row(label: str, a: int, b: int) -> str:
    delta = b - a
    delta_str = f"+{delta}" if delta > 0 else str(delta)
    delta_color = "var(--good)" if delta < 0 else "var(--danger)" if delta > 0 else "var(--muted)"
    return f"""
<tr>
  <td>{_esc(label)}</td>
  <td>{a}</td>
  <td>{b}</td>
  <td style="font-weight:700;color:{delta_color}">{delta_str}</td>
</tr>"""


def _build_diff_html(diff: Dict[str, Any]) -> str:
    run_a = diff.get("runA") or {}
    run_b = diff.get("runB") or {}
    passed = diff.get("passed", True)
    fail_reasons = diff.get("fail_reasons") or []
    pages = diff.get("pages") or {}
    quality = diff.get("quality") or {}
    tech = diff.get("tech") or {}
    tp = diff.get("third_parties") or {}
    gen = _esc(diff.get("generated_at") or "")
    v = _esc(diff.get("version") or __version__)

    a_target = _esc(run_a.get("target_url") or "Run A")
    b_target = _esc(run_b.get("target_url") or "Run B")
    a_ts = _esc(run_a.get("generated_at") or "—")
    b_ts = _esc(run_b.get("generated_at") or "—")

    status_cls = "badge-pass" if passed else "badge-fail"
    status_text = "PASS" if passed else "FAIL"

    # Quality regressions
    regressions = quality.get("regressions") or []
    reg_rows = ""
    for reg in regressions[:20]:
        url = reg.get("url") or ""
        deltas = reg.get("deltas") or {}
        reasons = ", ".join(reg.get("reasons") or [])
        delta_cells = "".join(
            f'<td style="color:{"var(--good)" if float(v)>=0 else "var(--danger)"}">{("+" if float(v)>=0 else "")}{round(float(v)*100)}%</td>'
            for v in [deltas.get(k, 0) for k in ["performance", "seo", "accessibility", "best-practices"]]
        )
        reg_rows += f"<tr><td class='truncate'><a href='{_esc(url)}'>{_esc(url)}</a></td>{delta_cells}<td>{_esc(reasons)}</td></tr>"

    reg_section = ""
    if regressions:
        reg_section = f"""
<div class="card" style="margin-top:22px">
  <div class="card-header"><h2>Quality Regressions</h2><span class="card-count">{len(regressions)}</span></div>
  <div class="card-body">
    <table class="data-table">
      <thead><tr><th>URL</th><th>Perf Δ</th><th>SEO Δ</th><th>A11y Δ</th><th>Best Pract. Δ</th><th>Reasons</th></tr></thead>
      <tbody>{reg_rows}</tbody>
    </table>
  </div>
</div>"""

    # Pages added/removed
    pages_added = pages.get("added") or []
    pages_removed = pages.get("removed") or []

    def _url_list(urls: List[str], tag_class: str, tag_text: str, limit: int = 30) -> str:
        if not urls:
            return '<p class="muted">None</p>'
        items = "".join(
            f'<div style="padding:4px 0;border-bottom:1px solid var(--border);font-size:12px">'
            f'<span class="diff-tag {tag_class}">{tag_text}</span>'
            f'<a href="{_esc(u)}">{_esc(u)}</a></div>'
            for u in urls[:limit]
        )
        more = f'<p class="muted" style="margin-top:6px">… and {len(urls)-limit} more</p>' if len(urls) > limit else ""
        return items + more

    pages_section = f"""
<div class="card" style="margin-top:22px">
  <div class="card-header"><h2>Page Changes</h2></div>
  <div class="card-body">
    <div class="diff-cols">
      <div>
        <div style="font-weight:700;margin-bottom:8px;color:var(--good)">Added ({len(pages_added)})</div>
        {_url_list(pages_added, 'diff-added', '+')}
      </div>
      <div>
        <div style="font-weight:700;margin-bottom:8px;color:var(--danger)">Removed ({len(pages_removed)})</div>
        {_url_list(pages_removed, 'diff-removed', '−')}
      </div>
    </div>
  </div>
</div>"""

    # Tech changes
    wapp = tech.get("wappalyzer") or {}
    bw = tech.get("builtwith") or {}
    tech_added = list(dict.fromkeys((wapp.get("added") or []) + (bw.get("added") or [])))
    tech_removed = list(dict.fromkeys((wapp.get("removed") or []) + (bw.get("removed") or [])))
    tech_section = ""
    if tech_added or tech_removed:
        ta = " ".join(f'<span class="badge diff-added">+{_esc(t)}</span>' for t in tech_added)
        tr = " ".join(f'<span class="badge diff-removed">−{_esc(t)}</span>' for t in tech_removed)
        tech_section = f"""
<div class="card" style="margin-top:22px">
  <div class="card-header"><h2>Tech Stack Changes</h2></div>
  <div class="card-body">
    {f'<div style="margin-bottom:8px">{ta}</div>' if ta else ''}
    {tr}
  </div>
</div>"""

    # Graph changes section
    gd = diff.get("graph") or {}
    graph_section = ""
    if gd:
        na, nb = gd.get("node_count_a"), gd.get("node_count_b")
        ea, eb = gd.get("edge_count_a"), gd.get("edge_count_b")
        dda, ddb, ddd = gd.get("avg_depth_a"), gd.get("avg_depth_b"), gd.get("avg_depth_delta")
        orphans_added = gd.get("orphans_added") or []
        orphans_removed = gd.get("orphans_removed") or []
        dead_added = gd.get("dead_ends_added") or []
        dead_removed = gd.get("dead_ends_removed") or []
        pr_shifts = gd.get("pagerank_shifts") or []
        depth_delta_html = f" (Δ {ddd:+.2f})" if ddd is not None else ""
        pr_rows = "".join(
            f'<tr><td class="truncate"><a href="{_esc(s["url"])}">{_esc(s["url"])}</a></td>'
            f'<td style="color:{("var(--good)" if s["delta"]>=0 else "var(--danger)")}">{s["delta"]:+.4f}</td></tr>'
            for s in pr_shifts[:10]
        )
        graph_section = f"""
<div class="card" style="margin-top:22px">
  <div class="card-header"><h2>Graph Changes</h2></div>
  <div class="card-body">
    <table class="data-table" style="margin-bottom:12px">
      <thead><tr><th>Metric</th><th>Run A</th><th>Run B</th></tr></thead>
      <tbody>
        {_diff_summary_row("Nodes", na or 0, nb or 0)}
        {_diff_summary_row("Edges", ea or 0, eb or 0)}
        <tr><td>Avg depth</td><td>{dda}</td><td>{ddb}{depth_delta_html}</td></tr>
        {_diff_summary_row("Orphans added", 0, len(orphans_added))}
        {_diff_summary_row("Dead ends added", 0, len(dead_added))}
      </tbody>
    </table>
    {f'<div style="margin-top:8px"><strong>PageRank shifts:</strong><table class="data-table"><thead><tr><th>URL</th><th>Δ score</th></tr></thead><tbody>{pr_rows}</tbody></table></div>' if pr_rows else ''}
  </div>
</div>"""

    fail_html = ""
    if fail_reasons:
        fail_html = "<ul style='margin:8px 0 0 18px;font-size:13px'>" + "".join(f"<li>{_esc(r)}</li>" for r in fail_reasons) + "</ul>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Site Inspector Diff — {a_target} vs {b_target}</title>
<style>{_css()}</style>
</head>
<body>
<header class="report-header">
  <h1>Site Inspector — Diff Report</h1>
  <div style="margin-top:6px;font-size:13px;color:#93c5fd">
    {a_target} &nbsp;→&nbsp; {b_target}
  </div>
  <div class="meta">
    <span>Generated {gen}</span>
    <span>Site Inspector v{v}</span>
    <span class="badge {status_cls}">{status_text}</span>
  </div>
  {fail_html}
</header>
<main class="report-main">
  <div class="card">
    <div class="card-header"><h2>Run Comparison</h2></div>
    <div class="card-body">
      <table class="data-table">
        <thead><tr><th></th><th>Run A</th><th>Run B</th><th>Δ</th></tr></thead>
        <tbody>
          <tr><td>Target</td><td class="truncate">{a_target}</td><td class="truncate">{b_target}</td><td>—</td></tr>
          <tr><td>Generated</td><td>{a_ts}</td><td>{b_ts}</td><td>—</td></tr>
          {_diff_summary_row("Pages added", 0, len(pages_added))}
          {_diff_summary_row("Pages removed", len(pages_removed), 0)}
          {_diff_summary_row("Quality regressions", 0, len(regressions))}
          {_diff_summary_row("New third-party domains", 0, len(tp.get('added') or []))}
        </tbody>
      </table>
    </div>
  </div>
  {reg_section}
  {pages_section}
  {graph_section}
  {tech_section}
</main>
{_footer_html()}
</body>
</html>"""


def _footer_html() -> str:
    return (
        '<footer class="report-footer">'
        'Generated by <a href="https://github.com/Mark2Mac/site-inspector">Site Inspector</a>'
        ' &nbsp;·&nbsp; '
        'Built to audit <a href="https://www.dedicatodesign.com">dedicatodesign.com</a>'
        '</footer>'
    )


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def build_run_html(run_obj: Dict[str, Any]) -> str:
    """Build a self-contained HTML run report."""
    host = _esc(run_obj.get("host") or run_obj.get("target_url") or "report")
    sections = "\n".join(filter(None, [
        _section_summary(run_obj),
        _section_priority_findings(run_obj),
        _section_lighthouse(run_obj),
        _section_graph(run_obj),
        _section_seo(run_obj),
        _section_ai(run_obj),
        _section_duplicates(run_obj),
        _section_crawl(run_obj),
        _section_posture(run_obj),
    ]))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Site Inspector — {host}</title>
<style>{_css()}</style>
</head>
<body>
{_section_header(run_obj)}
<main class="report-main">
{sections}
</main>
{_footer_html()}
</body>
</html>"""


def build_diff_html(diff_obj: Dict[str, Any]) -> str:
    """Build a self-contained HTML diff report."""
    return _build_diff_html(diff_obj)
