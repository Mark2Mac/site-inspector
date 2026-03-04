from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .utils import now_iso


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
    out: List[str] = []
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
        names: List[str] = []
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
        "same": sorted(sa & sb),
    }


def diff_pages(run_a: Dict[str, Any], run_b: Dict[str, Any]) -> Dict[str, Any]:
    a_pages = list_pages_from_run(run_a)
    b_pages = list_pages_from_run(run_b)
    pages_diff = diff_sets(a_pages, b_pages)
    return {
        **pages_diff,
        "count": {
            "runA": len(a_pages),
            "runB": len(b_pages),
        },
    }


def diff_third_parties(run_a: Dict[str, Any], run_b: Dict[str, Any]) -> Dict[str, Any]:
    a = third_parties_from_run(run_a)
    b = third_parties_from_run(run_b)
    return diff_sets(a, b)


def diff_tech(run_a: Dict[str, Any], run_b: Dict[str, Any]) -> Dict[str, Any]:
    a = tech_names_from_run(run_a)
    b = tech_names_from_run(run_b)

    out: Dict[str, Any] = {}
    for k in sorted(set(a.keys()) | set(b.keys())):
        out[k] = diff_sets(a.get(k, []), b.get(k, []))
    return out


def summarize_quality_by_url(run: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    by_url = quality_index_by_url(run)
    out: Dict[str, Dict[str, Any]] = {}
    for url, r in by_url.items():
        cats = r.get("categories") or {}
        out[url] = {
            "performance": cats.get("performance"),
            "accessibility": cats.get("accessibility"),
            "best_practices": cats.get("best-practices") or cats.get("best_practices"),
            "seo": cats.get("seo"),
            "pwa": cats.get("pwa"),
            "passed": (r.get("budget_eval") or {}).get("passed"),
            "failed_rules": (r.get("budget_eval") or {}).get("failed") or [],
        }
    return out


def diff_quality(run_a: Dict[str, Any], run_b: Dict[str, Any]) -> Dict[str, Any]:
    qa = summarize_quality_by_url(run_a)
    qb = summarize_quality_by_url(run_b)

    urls = sorted(set(qa.keys()) | set(qb.keys()))
    rows: List[Dict[str, Any]] = []
    for u in urls:
        rows.append({"url": u, "a": qa.get(u), "b": qb.get(u)})

    return {
        "count": {"runA": len(qa), "runB": len(qb)},
        "rows": rows,
    }


def _score_delta(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    try:
        return float(b) - float(a)
    except Exception:
        return None


def _regressions_from_quality_rows(
    rows: List[Dict[str, Any]],
    score_regression_threshold: float = 0.05,
) -> Dict[str, Any]:
    regressions: List[Dict[str, Any]] = []

    for row in rows:
        a = row.get("a") or {}
        b = row.get("b") or {}
        url = row.get("url")

        for k in ["performance", "accessibility", "best_practices", "seo", "pwa"]:
            d = _score_delta(a.get(k), b.get(k))
            if d is None:
                continue
            if d < -abs(score_regression_threshold):
                regressions.append(
                    {
                        "url": url,
                        "metric": k,
                        "runA": a.get(k),
                        "runB": b.get(k),
                        "delta": d,
                    }
                )

        a_pass = row["a"]["passed"] if row["a"] else None
        b_pass = row["b"]["passed"] if row["b"] else None
        if a_pass is True and b_pass is False:
            regressions.append(
                {
                    "url": url,
                    "metric": "budget_passed",
                    "runA": True,
                    "runB": False,
                    "delta": None,
                }
            )

    regressions = sorted(
        regressions,
        key=lambda x: (x.get("metric") or "", x.get("delta") if x.get("delta") is not None else 0),
    )
    return {"count": len(regressions), "items": regressions}


def diff_runs(
    run_a: Dict[str, Any],
    run_b: Dict[str, Any],
    allow_new_third_parties: Optional[List[str]] = None,
    fail_on_new_third_parties: bool = False,
    score_regression_threshold: float = 0.05,
) -> Dict[str, Any]:
    pages_diff = diff_pages(run_a, run_b)
    tps_diff = diff_third_parties(run_a, run_b)
    tech_diff = diff_tech(run_a, run_b)
    quality_diff = diff_quality(run_a, run_b)

    regressions = _regressions_from_quality_rows(
        quality_diff.get("rows") or [],
        score_regression_threshold=score_regression_threshold,
    )

    passed = True
    reasons: List[str] = []

    # Optional gate: new third parties
    if fail_on_new_third_parties:
        allow = set(allow_new_third_parties or [])
        added = set(tps_diff.get("added") or [])
        disallowed = sorted([x for x in added if x not in allow])
        if disallowed:
            passed = False
            reasons.append(f"New third-party domains detected: {', '.join(disallowed)}")

    # Optional gate: score regressions
    if regressions.get("count", 0) > 0:
        passed = False
        reasons.append(f"Detected {regressions.get('count')} score regressions >= {score_regression_threshold}")

    # Some run-level convenience stats (if present)
    sa = run_a.get("summary") or {}
    sb = run_b.get("summary") or {}
    extra = {
        "runA_pages_count": sa.get("pages_count"),
        "runB_pages_count": sb.get("pages_count"),
        "runA_js_disabled_not_readable": sa.get("pages_js_disabled_not_readable"),
        "runB_js_disabled_not_readable": sb.get("pages_js_disabled_not_readable"),
    }

    out = {
        "version": "0.4",
        "generated_at": now_iso(),
        "runA": {
            "dir": run_a.get("_run_dir"),
            "generated_at": run_a.get("generated_at"),
            "target_url": run_a.get("target_url"),
        },
        "runB": {
            "dir": run_b.get("_run_dir"),
            "generated_at": run_b.get("generated_at"),
            "target_url": run_b.get("target_url"),
        },
        "passed": passed,
        "fail_reasons": reasons,
        "pages": pages_diff,
        "third_parties": {
            **tps_diff,
            "allowlist_used": allow_new_third_parties is not None,
            "allowlist": sorted(list(set(allow_new_third_parties or []))) if allow_new_third_parties is not None else None,
            "disallowed_added": (
                sorted([x for x in (tps_diff.get("added") or []) if x not in set(allow_new_third_parties or [])])
                if allow_new_third_parties is not None
                else None
            ),
        },
        "tech": tech_diff,
        "quality": quality_diff,
        "regressions": regressions,
        "extra": extra,
    }
    return out


def render_diff_md(diff: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Diff report")
    lines.append("")
    lines.append(f"- generated_at: `{diff.get('generated_at')}`")
    lines.append(f"- passed: **{diff.get('passed')}**")
    if diff.get("fail_reasons"):
        lines.append("")
        lines.append("## Fail reasons")
        for r in diff.get("fail_reasons") or []:
            lines.append(f"- {r}")

    lines.append("")
    lines.append("## Runs")
    ra = diff.get("runA") or {}
    rb = diff.get("runB") or {}
    lines.append(f"- runA: `{ra.get('dir')}` ({ra.get('generated_at')}) target={ra.get('target_url')}")
    lines.append(f"- runB: `{rb.get('dir')}` ({rb.get('generated_at')}) target={rb.get('target_url')}")

    # Pages
    lines.append("")
    lines.append("## Pages")
    pages = diff.get("pages") or {}
    lines.append(f"- runA: {((pages.get('count') or {}).get('runA'))} pages")
    lines.append(f"- runB: {((pages.get('count') or {}).get('runB'))} pages")
    lines.append(f"- added: {len(pages.get('added') or [])}")
    lines.append(f"- removed: {len(pages.get('removed') or [])}")

    # Third parties
    lines.append("")
    lines.append("## Third-party domains")
    tps = diff.get("third_parties") or {}
    lines.append(f"- added: {len(tps.get('added') or [])}")
    lines.append(f"- removed: {len(tps.get('removed') or [])}")
    if tps.get("allowlist_used"):
        dis = tps.get("disallowed_added") or []
        lines.append(f"- allowlist used; disallowed added: {len(dis)}")

    # Regressions
    lines.append("")
    lines.append("## Regressions")
    reg = diff.get("regressions") or {}
    items = reg.get("items") or []
    lines.append(f"- count: {reg.get('count', 0)}")
    for it in items[:50]:
        lines.append(
            f"- `{it.get('metric')}` {it.get('url')} : {it.get('runA')} → {it.get('runB')} (delta={it.get('delta')})"
        )
    if len(items) > 50:
        lines.append(f"- ...and {len(items) - 50} more")

    return "\n".join(lines)