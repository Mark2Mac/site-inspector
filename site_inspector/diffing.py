from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# -----------------------------
# v0.3 DIFF
# -----------------------------

def load_run_dir(run_dir: Path) -> Dict[str, Any]:
    run_path = run_dir / "run.json"
    if not run_path.exists():
        raise FileNotFoundError(f"run.json not found in: {run_dir}")
    run = json.loads(run_path.read_text(encoding="utf-8"))
    run["_run_dir"] = str(run_dir)
    return run


def list_pages_from_run(run: Dict[str, Any]) -> List[str]:
    pages = (run.get("crawl") or {}).get("pages") or []
    out = []
    for p in pages:
        u = p.get("url")
        if u:
            out.append(u)
    return out


def third_parties_from_run(run: Dict[str, Any]) -> List[str]:
    fp = (run.get("posture") or {}).get("fingerprinting") or {}
    tps = fp.get("third_party_domains") or []
    return sorted({str(x) for x in tps if x})


def tech_names_from_run(run: Dict[str, Any]) -> Dict[str, List[str]]:
    fp = (run.get("posture") or {}).get("fingerprinting") or {}
    tech = fp.get("tech") or {}
    out: Dict[str, List[str]] = {"wappalyzer": [], "builtwith": []}

    w = tech.get("wappalyzer")
    if isinstance(w, dict):
        out["wappalyzer"] = sorted(w.keys())

    b = tech.get("builtwith")
    if isinstance(b, dict):
        names = []
        for _, items in b.items():
            if isinstance(items, list):
                for it in items:
                    names.append(str(it))
        out["builtwith"] = sorted(set(names))

    return out


def quality_index_by_url(run: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    q = run.get("quality") or {}
    res = q.get("results") or []
    out: Dict[str, Dict[str, Any]] = {}
    for r in res:
        u = r.get("url")
        if u:
            out[u] = r
    return out


def diff_sets(a: List[str], b: List[str]) -> Dict[str, List[str]]:
    sa, sb = set(a), set(b)
    return {
        "added": sorted(sb - sa),
        "removed": sorted(sa - sb),
        "unchanged": sorted(sa & sb),
    }


def diff_quality(run_a: Dict[str, Any], run_b: Dict[str, Any], *, score_regression_threshold: float) -> Dict[str, Any]:
    qa = run_a.get("quality")
    qb = run_b.get("quality")
    out: Dict[str, Any] = {
        "available": bool(qa) and bool(qb),
        "summary": {},
        "per_page": [],
        "regressions": [],
    }
    if not qa or not qb:
        out["summary"] = {"note": "One or both runs missing 'quality' block"}
        return out

    idx_a = quality_index_by_url(run_a)
    idx_b = quality_index_by_url(run_b)

    urls = sorted(set(idx_a.keys()) | set(idx_b.keys()))
    regressions = []

    out["summary"] = {
        "runA_passed": qa.get("passed"),
        "runB_passed": qb.get("passed"),
        "runA_pages_failed": qa.get("pages_failed"),
        "runB_pages_failed": qb.get("pages_failed"),
    }

    for u in urls:
        ra = idx_a.get(u)
        rb = idx_b.get(u)
        row: Dict[str, Any] = {"url": u, "a": None, "b": None, "deltas": {}, "regression": False, "reasons": []}

        if ra:
            row["a"] = {
                "scores": ra.get("scores"),
                "passed": (ra.get("budget_eval") or {}).get("passed"),
            }
        if rb:
            row["b"] = {
                "scores": rb.get("scores"),
                "passed": (rb.get("budget_eval") or {}).get("passed"),
            }

        a_pass = row["a"]["passed"] if row["a"] else None
        b_pass = row["b"]["passed"] if row["b"] else None
        if a_pass is True and b_pass is False:
            row["regression"] = True
            row["reasons"].append("budget_regression_pass_to_fail")

        a_scores = (row["a"] or {}).get("scores") or {}
        b_scores = (row["b"] or {}).get("scores") or {}
        for cat in ["performance", "seo", "accessibility", "best-practices"]:
            av = a_scores.get(cat)
            bv = b_scores.get(cat)
            if isinstance(av, (int, float)) and isinstance(bv, (int, float)):
                delta = float(bv) - float(av)
                row["deltas"][cat] = delta
                if delta < -abs(score_regression_threshold):
                    row["regression"] = True
                    row["reasons"].append(f"score_drop_{cat}_{delta:.3f}")

        out["per_page"].append(row)
        if row["regression"]:
            regressions.append({"url": u, "reasons": row["reasons"], "deltas": row["deltas"]})

    out["regressions"] = regressions
    return out


def diff_runs(run_a: Dict[str, Any], run_b: Dict[str, Any], *, allow_new_third_parties: Optional[List[str]], score_regression_threshold: float) -> Dict[str, Any]:
    pages_a = list_pages_from_run(run_a)
    pages_b = list_pages_from_run(run_b)

    tps_a = third_parties_from_run(run_a)
    tps_b = third_parties_from_run(run_b)

    tech_a = tech_names_from_run(run_a)
    tech_b = tech_names_from_run(run_b)

    pages_diff = diff_sets(pages_a, pages_b)
    tps_diff = diff_sets(tps_a, tps_b)

    allow = set(allow_new_third_parties or [])
    new_tps = tps_diff["added"]
    disallowed_new_tps = [d for d in new_tps if d not in allow] if allow_new_third_parties is not None else []

    quality_diff = diff_quality(run_a, run_b, score_regression_threshold=score_regression_threshold)

    passed = True
    reasons: List[str] = []

    if quality_diff.get("available") and quality_diff.get("regressions"):
        passed = False
        reasons.append("quality_regressions")

    if allow_new_third_parties is not None and disallowed_new_tps:
        passed = False
        reasons.append("new_third_parties_not_allowed")

    qa = (run_a.get("quality") or {}).get("passed")
    qb = (run_b.get("quality") or {}).get("passed")
    if qa is True and qb is False:
        passed = False
        reasons.append("overall_budget_pass_to_fail")

    # v0.4: include extractability (if present) as informational (not gating by default)
    pwa = run_a.get("playwright") or {}
    pwb = run_b.get("playwright") or {}
    extract_diff = None
    if pwa and pwb:
        ea = (pwa.get("extractability_rollup") or {})
        eb = (pwb.get("extractability_rollup") or {})
        extract_diff = {
            "runA_js_disabled_readable": ea.get("pages_js_disabled_readable"),
            "runB_js_disabled_readable": eb.get("pages_js_disabled_readable"),
            "runA_js_disabled_not_readable": ea.get("pages_js_disabled_not_readable"),
            "runB_js_disabled_not_readable": eb.get("pages_js_disabled_not_readable"),
        }

    out = {
        "version": "0.4",
        "generated_at": now_iso(),
        "runA": {"dir": run_a.get("_run_dir"), "generated_at": run_a.get("generated_at"), "target_url": run_a.get("target_url")},
        "runB": {"dir": run_b.get("_run_dir"), "generated_at": run_b.get("generated_at"), "target_url": run_b.get("target_url")},
        "passed": passed,
        "fail_reasons": reasons,
        "pages": pages_diff,
        "third_parties": {
            **tps_diff,
            "allowlist_used": allow_new_third_parties is not None,
            "allowlist": sorted(list(allow)) if allow_new_third_parties is not None else None,
            "disallowed_added": disallowed_new_tps if allow_new_third_parties is not None else None,
        },
        "tech": {
            "wappalyzer": diff_sets(tech_a.get("wappalyzer", []), tech_b.get("wappalyzer", [])),
            "builtwith": diff_sets(tech_a.get("builtwith", []), tech_b.get("builtwith", [])),
        },
        "quality": quality_diff,
        "extractability": extract_diff,
    }
    return out


def render_diff_md(diff: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Inspector Diff (v0.4)\n")
    lines.append(f"- Generated: **{diff.get('generated_at')}**")
    lines.append(f"- Passed: **{diff.get('passed')}**")
    if not diff.get("passed"):
        lines.append(f"- Fail reasons: `{', '.join(diff.get('fail_reasons') or [])}`")
    lines.append("")

    a = diff.get("runA") or {}
    b = diff.get("runB") or {}
    lines.append("## Runs\n")
    lines.append(f"- Run A: `{a.get('dir')}` — `{a.get('generated_at')}` — `{a.get('target_url')}`")
    lines.append(f"- Run B: `{b.get('dir')}` — `{b.get('generated_at')}` — `{b.get('target_url')}`\n")

    q = diff.get("quality") or {}
    lines.append("## Quality\n")
    if not q.get("available"):
        lines.append("_Quality diff not available (missing quality in one run)._")
        lines.append("")
    else:
        summ = q.get("summary") or {}
        lines.append(f"- RunA passed: `{summ.get('runA_passed')}` (failed pages: {summ.get('runA_pages_failed')})")
        lines.append(f"- RunB passed: `{summ.get('runB_passed')}` (failed pages: {summ.get('runB_pages_failed')})")
        regs = q.get("regressions") or []
        lines.append(f"- Regressions: **{len(regs)}**")
        if regs:
            for r in regs[:25]:
                lines.append(f"  - {r.get('url')}: {', '.join(r.get('reasons') or [])}")
            if len(regs) > 25:
                lines.append("  - … (truncated)")
        lines.append("")

    ex = diff.get("extractability")
    if ex:
        lines.append("## Extractability (JS disabled)\n")
        lines.append(f"- RunA readable pages: `{ex.get('runA_js_disabled_readable')}`; not readable: `{ex.get('runA_js_disabled_not_readable')}`")
        lines.append(f"- RunB readable pages: `{ex.get('runB_js_disabled_readable')}`; not readable: `{ex.get('runB_js_disabled_not_readable')}`")
        lines.append("")

    tp = diff.get("third_parties") or {}
    lines.append("## Third-party domains\n")
    added = tp.get("added") or []
    removed = tp.get("removed") or []
    lines.append(f"- Added: **{len(added)}**")
    for d in added[:30]:
        lines.append(f"  - {d}")
    if len(added) > 30:
        lines.append("  - … (truncated)")
    lines.append(f"- Removed: **{len(removed)}**")
    for d in removed[:30]:
        lines.append(f"  - {d}")
    if len(removed) > 30:
        lines.append("  - … (truncated)")
    if tp.get("allowlist_used"):
        dis = tp.get("disallowed_added") or []
        lines.append(f"- Allowlist used: `true` (disallowed new: {len(dis)})")
    lines.append("")

    tech = diff.get("tech") or {}
    lines.append("## Tech changes\n")
    for src in ["wappalyzer", "builtwith"]:
        t = tech.get(src) or {}
        lines.append(f"### {src}")
        lines.append(f"- Added: {len(t.get('added') or [])}")
        for x in (t.get("added") or [])[:30]:
            lines.append(f"  - {x}")
        if len(t.get("added") or []) > 30:
            lines.append("  - … (truncated)")
        lines.append(f"- Removed: {len(t.get('removed') or [])}")
        for x in (t.get("removed") or [])[:30]:
            lines.append(f"  - {x}")
        if len(t.get("removed") or []) > 30:
            lines.append("  - … (truncated)")
        lines.append("")

    pages = diff.get("pages") or {}
    lines.append("## Pages\n")
    lines.append(f"- Added: {len(pages.get('added') or [])}")
    for u in (pages.get("added") or [])[:30]:
        lines.append(f"  - {u}")
    if len(pages.get("added") or []) > 30:
        lines.append("  - … (truncated)")
    lines.append(f"- Removed: {len(pages.get('removed') or [])}")
    for u in (pages.get("removed") or [])[:30]:
        lines.append(f"  - {u}")
    if len(pages.get("removed") or []) > 30:
        lines.append("  - … (truncated)")

    lines.append("")
    return "\n".join(lines)
