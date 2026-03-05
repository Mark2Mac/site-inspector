from __future__ import annotations

import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from urllib.parse import urlparse

from .utils import _run, pct01_to_pct, safe_write, slugify_url_for_filename, which, now_iso


# -----------------------------
# Quality (Lighthouse)
# -----------------------------

DEFAULT_BUDGET: Dict[str, Any] = {
    "categories": {
        "performance": {"min_score": 0.80},
        "seo": {"min_score": 0.90},
        "accessibility": {"min_score": 0.80},
        "best-practices": {"min_score": 0.80},
    },
    "audits": {
        "largest-contentful-paint": {"max_ms": 2500},
        "cumulative-layout-shift": {"max_numeric": 0.10},
        "total-blocking-time": {"max_ms": 300},
        "speed-index": {"max_ms": 4000},
        "first-contentful-paint": {"max_ms": 2000},
    }
}


def ensure_npx_available() -> None:
    if which("npx") is None and which("npx.cmd") is None:
        raise RuntimeError(
            "npx not found in PATH. Install Node.js (includes npm/npx) and restart your terminal. "
            "Tip: in PowerShell run `where npx` to verify."
        )


def _build_windows_cmd_for_exe(exe_path: str, args: List[str]) -> List[str]:
    """Build a subprocess command that works on Windows for .cmd/.bat wrappers."""
    low = exe_path.lower()
    if low.endswith(".cmd") or low.endswith(".bat"):
        # cmd.exe is required for wrapper scripts when shell=False
        return ["cmd", "/c", exe_path, *args]
    return [exe_path, *args]


def run_lighthouse(url: str, *, out_dir: Path, timeout_s: int) -> Dict[str, Any]:
    ensure_npx_available()

    lh_dir = out_dir / "lighthouse"
    lh_dir.mkdir(parents=True, exist_ok=True)

    slug = slugify_url_for_filename(url)
    json_path = lh_dir / f"{slug}.report.json"
    html_path = lh_dir / f"{slug}.report.html"

    chrome_flags = "--headless --disable-gpu --no-sandbox"

    npx_path = which("npx") or which("npx.cmd") or which("npx.exe")
    if not npx_path:
        raise RuntimeError("npx not found in PATH. Install Node.js (includes npm/npx) and restart your terminal.")

    cmd = _build_windows_cmd_for_exe(npx_path, [
        "--yes",
        "lighthouse",
        url,
        "--quiet",
        "--output=json",
        "--output=html",
        f"--output-path={str(json_path)}",
        f"--chrome-flags={chrome_flags}",
    ])

    rc, so, se = _run(cmd, timeout=max(120, timeout_s * 6))
    safe_write(out_dir / "raw" / f"lighthouse_{slug}.stdout.txt", so)
    safe_write(out_dir / "raw" / f"lighthouse_{slug}.stderr.txt", se)

    if not html_path.exists():
        candidates = sorted(lh_dir.glob(f"*{slug}*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            html_path = candidates[0]

    report: Dict[str, Any] = {"url": url, "rc": rc, "json_path": str(json_path), "html_path": str(html_path) if html_path.exists() else None}
    try:
        if json_path.exists():
            report["lighthouse_json"] = json.loads(json_path.read_text(encoding="utf-8"))
        else:
            report["error"] = f"JSON report not found at {json_path}"
    except Exception as e:
        report["error"] = f"Failed to parse Lighthouse JSON: {e}"
    return report


def extract_lighthouse_scores(lh: Dict[str, Any]) -> Dict[str, Optional[float]]:
    out = {"performance": None, "seo": None, "accessibility": None, "best-practices": None}
    cats = (lh.get("categories") or {})
    for key in out.keys():
        lk = "best-practices" if key == "best-practices" else key
        if lk in cats and isinstance(cats[lk], dict):
            sc = cats[lk].get("score")
            if isinstance(sc, (int, float)):
                out[key] = float(sc)
    return out


def extract_lighthouse_audit_values(lh: Dict[str, Any], audit_id: str) -> Dict[str, Any]:
    audits = lh.get("audits") or {}
    a = audits.get(audit_id) or {}
    return {
        "numericValue": a.get("numericValue"),
        "numericUnit": a.get("numericUnit"),
        "displayValue": a.get("displayValue"),
        "score": a.get("score"),
    }


def evaluate_budget(lh_json: Dict[str, Any], budget: Dict[str, Any]) -> Dict[str, Any]:
    details: Dict[str, Any] = {"passed": True, "categories": {}, "audits": {}}

    scores = extract_lighthouse_scores(lh_json)
    cat_budget = (budget.get("categories") or {})
    for cat, cfg in cat_budget.items():
        min_score = cfg.get("min_score")
        actual = scores.get(cat)
        passed = True
        reason = None
        if min_score is not None:
            if actual is None:
                passed = False
                reason = "missing_score"
            else:
                passed = actual >= float(min_score)
                if not passed:
                    reason = f"score<{min_score}"
        details["categories"][cat] = {"actual": actual, "min_score": min_score, "passed": passed, "reason": reason}
        if not passed:
            details["passed"] = False

    audit_budget = (budget.get("audits") or {})
    for audit_id, cfg in audit_budget.items():
        v = extract_lighthouse_audit_values(lh_json, audit_id)
        numeric_value = v.get("numericValue")
        passed = True
        reason = None

        if numeric_value is None:
            passed = False
            reason = "missing_numericValue"
        else:
            if "max_ms" in cfg:
                max_ms = float(cfg["max_ms"])
                passed = float(numeric_value) <= max_ms
                if not passed:
                    reason = f"value>{max_ms}ms"
            if "max_numeric" in cfg:
                mx = float(cfg["max_numeric"])
                passed = float(numeric_value) <= mx
                if not passed:
                    reason = f"value>{mx}"

        details["audits"][audit_id] = {"value": v, "budget": cfg, "passed": passed, "reason": reason}
        if not passed:
            details["passed"] = False

    return details


def quality_for_urls(
    urls: List[str],
    *,
    out_dir: Path,
    timeout_s: int,
    budget: Dict[str, Any],
    max_pages: int,
    lighthouse_workers: int = 2,
    workers: int | None = None,
    **_ignored: object,
) -> Dict[str, Any]:
    if workers is not None:
        lighthouse_workers = workers
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []

    work_urls = urls[:max_pages]

    def one(url: str) -> Dict[str, Any]:
        lh_run = run_lighthouse(url, out_dir=out_dir, timeout_s=timeout_s)
        lh_json = lh_run.get("lighthouse_json")

        per_page: Dict[str, Any] = {
            "url": url,
            "artifacts": {
                "json_path": lh_run.get("json_path"),
                "html_path": lh_run.get("html_path"),
            },
            "rc": lh_run.get("rc"),
            "error": lh_run.get("error"),
            "scores": None,
            "budget_eval": None,
        }

        if isinstance(lh_json, dict):
            per_page["scores"] = extract_lighthouse_scores(lh_json)
            per_page["budget_eval"] = evaluate_budget(lh_json, budget)

        return per_page

    lw = max(1, int(lighthouse_workers))
    lw = min(lw, 4)  # Lighthouse is heavy; keep concurrency low.

    if lw == 1 or len(work_urls) <= 1:
        for url in work_urls:
            results.append(one(url))
    else:
        with ThreadPoolExecutor(max_workers=lw) as ex:
            futs = {ex.submit(one, u): u for u in work_urls}
            by_url: Dict[str, Dict[str, Any]] = {}
            for fut, u in list(futs.items()):
                try:
                    by_url[u] = fut.result()
                except Exception as e:
                    by_url[u] = {
                        "url": u,
                        "artifacts": {"json_path": None, "html_path": None},
                        "rc": None,
                        "error": f"Lighthouse worker failed: {e}",
                        "scores": None,
                        "budget_eval": None,
                    }
            for u in work_urls:
                results.append(by_url[u])

    for per_page in results:
        budget_eval = per_page.get("budget_eval") or {}
        if not budget_eval.get("passed", True):
            failures.append({"url": per_page.get("url"), "why": per_page.get("budget_eval")})

    summary = {
        "generated_at": now_iso(),
        "pages_tested": len(results),
        "pages_failed": len(failures),
        "passed": len(failures) == 0,
        "budget": budget,
        "lighthouse_workers": lw,
        "results": results,
        "failures": failures,
    }
    return summary


# -----------------------------
# Lighthouse targeting (sampling)
# -----------------------------

def _group_key_for_url(u: str) -> str:
    """Cheap heuristic to group similar pages.

    We group by first path segment ("/products/..." => "products").
    This keeps sampling stable and avoids template inference complexity.
    """
    try:
        p = urlparse(u)
        path = (p.path or "/").strip("/")
        if not path:
            return "root"
        return path.split("/")[0].lower() or "root"
    except Exception:
        return "root"


def select_lighthouse_targets(
    urls: List[str],
    *,
    target_url: str,
    sample_total: int,
    per_group: int = 1,
    always_include: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Select a stable subset of URLs for Lighthouse.

    - Always includes the target_url (typically the homepage)
    - Optionally always includes URLs from an external list
    - Samples deterministically per group to keep diffs stable
    """
    per_group = max(1, int(per_group))
    sample_total = max(1, int(sample_total))

    # Stable ordering
    uniq: List[str] = []
    seen = set()
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            uniq.append(u)

    must: List[str] = []
    for u in [target_url, *(always_include or [])]:
        if u and u not in seen:
            seen.add(u)
            uniq.append(u)
        if u and u not in must:
            must.append(u)

    selected: List[str] = []

    def _add(u: str) -> None:
        if u and u not in selected:
            selected.append(u)

    # Always include must-have URLs first
    for u in must:
        _add(u)
        if len(selected) >= sample_total:
            return {
                "selected_urls": selected[:sample_total],
                "selection": {
                    "mode": "sampled",
                    "sample_total": sample_total,
                    "per_group": per_group,
                    "groups": {},
                    "always_include": must,
                },
            }

    # Group remaining URLs and pick first K per group
    groups: Dict[str, List[str]] = {}
    for u in uniq:
        if u in selected:
            continue
        k = _group_key_for_url(u)
        groups.setdefault(k, []).append(u)

    # Deterministic: group names sorted, URLs within group sorted
    picked_by_group: Dict[str, int] = {}
    for g in sorted(groups.keys()):
        for u in sorted(groups[g]):
            if picked_by_group.get(g, 0) >= per_group:
                continue
            _add(u)
            picked_by_group[g] = picked_by_group.get(g, 0) + 1
            if len(selected) >= sample_total:
                break
        if len(selected) >= sample_total:
            break

    return {
        "selected_urls": selected[:sample_total],
        "selection": {
            "mode": "sampled",
            "sample_total": sample_total,
            "per_group": per_group,
            "groups": picked_by_group,
            "always_include": must,
        },
    }
