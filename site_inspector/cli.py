from __future__ import annotations

import argparse
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from .crawl import discover_pages
from .diffing import diff_runs, load_run_dir
from .lighthouse import DEFAULT_BUDGET
from .lighthouse import quality_for_urls
from .playwright_audit import playwright_for_urls
from .posture import collect_posture
from .reporting import build_run_md
from .utils import load_json_if_exists, normalize_target, safe_write, safe_write_json, now_iso, host_from_url


# -----------------------------
# Commands
# -----------------------------

def cmd_crawl(args: argparse.Namespace) -> int:
    target = normalize_target(args.target)
    host = host_from_url(target)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else Path(f"./inspect_{host}_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    crawl = discover_pages(target, max_pages=args.max_pages, timeout_s=args.timeout, out_dir=out_dir)
    safe_write_json(out_dir / "pages.json", crawl)

    print(f"✅ Crawl saved: {out_dir / 'pages.json'}")
    return 0


def cmd_posture(args: argparse.Namespace) -> int:
    target = normalize_target(args.target)
    host = host_from_url(target)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else Path(f"./inspect_{host}_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    posture = collect_posture(target, timeout_s=args.timeout, out_dir=out_dir)
    safe_write_json(out_dir / "posture.json", posture)

    run = {"generated_at": now_iso(), "target_url": target, "host": host, "posture": posture}
    safe_write(out_dir / "posture.md", build_run_md(run))

    print(f"✅ Posture saved:\n- {out_dir / 'posture.json'}\n- {out_dir / 'posture.md'}\n- raw: {out_dir / 'raw'}")
    return 0


def cmd_quality(args: argparse.Namespace) -> int:
    target = normalize_target(args.target)
    host = host_from_url(target)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else Path(f"./inspect_{host}_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)

    budget = load_json_if_exists(args.budget) or DEFAULT_BUDGET

    crawl = discover_pages(target, max_pages=args.max_pages, timeout_s=args.timeout, out_dir=out_dir)
    urls = [p["url"] for p in (crawl.get("pages") or [])]

    summary = quality_for_urls(urls, out_dir=out_dir, timeout_s=args.timeout, budget=budget, max_pages=args.max_pages)
    safe_write_json(out_dir / "quality_summary.json", summary)
    safe_write_json(out_dir / "pages.json", crawl)

    print(f"✅ Quality saved:\n- {out_dir / 'quality_summary.json'}\n- lighthouse: {out_dir / 'lighthouse'}\n- raw: {out_dir / 'raw'}")
    return 0 if summary.get("passed") else 1


def cmd_playwright(args: argparse.Namespace) -> int:
    target = normalize_target(args.target)
    host = host_from_url(target)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else Path(f"./inspect_{host}_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)

    crawl = discover_pages(target, max_pages=args.max_pages, timeout_s=args.timeout, out_dir=out_dir)
    urls = [p["url"] for p in (crawl.get("pages") or [])]

    summary = playwright_for_urls(urls, out_dir=out_dir, timeout_s=args.timeout, max_pages=args.max_pages)
    safe_write_json(out_dir / "playwright_summary.json", summary)
    safe_write_json(out_dir / "pages.json", crawl)

    print(f"✅ Playwright saved:\n- {out_dir / 'playwright_summary.json'}\n- playwright: {out_dir / 'playwright'}\n- raw: {out_dir / 'raw'}")
    return 0 if summary.get("passed") else 1


def cmd_run(args: argparse.Namespace) -> int:
    target = normalize_target(args.target)
    host = host_from_url(target)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else Path(f"./inspect_{host}_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)

    budget = load_json_if_exists(args.budget) or DEFAULT_BUDGET

    crawl = discover_pages(target, max_pages=args.max_pages, timeout_s=args.timeout, out_dir=out_dir)
    posture = collect_posture(target, timeout_s=args.timeout, out_dir=out_dir)

    quality = None
    quality_exit = 0
    if not args.skip_quality:
        urls = [p["url"] for p in (crawl.get("pages") or [])]
        quality = quality_for_urls(urls, out_dir=out_dir, timeout_s=args.timeout, budget=budget, max_pages=args.max_pages)
        safe_write_json(out_dir / "quality_summary.json", quality)
        quality_exit = 0 if quality.get("passed") else 1

    pw = None
    pw_exit = 0
    if not args.skip_playwright:
        urls = [p["url"] for p in (crawl.get("pages") or [])]
        pw = playwright_for_urls(urls, out_dir=out_dir, timeout_s=args.timeout, max_pages=args.max_pages)
        safe_write_json(out_dir / "playwright_summary.json", pw)
        pw_exit = 0 if pw.get("passed") else 1

    run = {
        "version": "0.4",
        "generated_at": now_iso(),
        "target_url": target,
        "host": host,
        "crawl": crawl,
        "posture": posture,
        "quality": quality,
        "playwright": pw,
    }

    safe_write_json(out_dir / "run.json", run)
    safe_write(out_dir / "run.md", build_run_md(run))
    safe_write_json(out_dir / "pages.json", crawl)
    safe_write_json(out_dir / "posture.json", posture)

    print(f"✅ Run generated:\n- {out_dir / 'run.md'}\n- {out_dir / 'run.json'}\n- pages: {out_dir / 'pages.json'}\n- posture: {out_dir / 'posture.json'}\n- lighthouse: {out_dir / 'lighthouse'}\n- playwright: {out_dir / 'playwright'}\n- raw: {out_dir / 'raw'}")

    # Keep hero feature gating: budgets first; playwright failure is also meaningful but optional.
    # We return "worst" exit code among enabled checks.
    return 1 if (quality_exit == 1 or pw_exit == 1) else 0


def cmd_diff(args: argparse.Namespace) -> int:
    run_a_dir = Path(args.run_a).resolve()
    run_b_dir = Path(args.run_b).resolve()

    run_a = load_run_dir(run_a_dir)
    run_b = load_run_dir(run_b_dir)

    if args.out:
        out_dir = Path(args.out)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_dir = Path(f"./diff_{run_a_dir.name}_vs_{run_b_dir.name}_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    allowlist = None
    if args.allow_new_third_parties is not None:
        allowlist = [x.strip() for x in args.allow_new_third_parties.split(",") if x.strip()]

    diff = diff_runs(
        run_a,
        run_b,
        allow_new_third_parties=allowlist,
        score_regression_threshold=args.score_regression_threshold,
    )

    safe_write_json(out_dir / "diff.json", diff)
    safe_write(out_dir / "diff.md", render_diff_md(diff))

    print(f"✅ Diff generated:\n- {out_dir / 'diff.md'}\n- {out_dir / 'diff.json'}")
    return 0 if diff.get("passed") else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="inspect", description="Site Inspector v0.4 (crawl + posture + lighthouse + diff + playwright)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_crawl = sub.add_parser("crawl", help="Discover pages via sitemap + fallback internal link crawl")
    ap_crawl.add_argument("target")
    ap_crawl.add_argument("--out", default=None)
    ap_crawl.add_argument("--max-pages", type=int, default=50)
    ap_crawl.add_argument("--timeout", type=int, default=20)
    ap_crawl.set_defaults(fn=cmd_crawl)

    ap_posture = sub.add_parser("posture", help="Collect posture/tech/headers/TLS/DNS/meta/third parties for a URL")
    ap_posture.add_argument("target")
    ap_posture.add_argument("--out", default=None)
    ap_posture.add_argument("--timeout", type=int, default=20)
    ap_posture.set_defaults(fn=cmd_posture)

    ap_quality = sub.add_parser("quality", help="Run Lighthouse on discovered pages and apply budgets (exit 1 on fail)")
    ap_quality.add_argument("target")
    ap_quality.add_argument("--out", default=None)
    ap_quality.add_argument("--max-pages", type=int, default=20, help="Max pages to test with Lighthouse (default 20)")
    ap_quality.add_argument("--timeout", type=int, default=20)
    ap_quality.add_argument("--budget", default=None, help="Path to budgets.json (default: built-in)")
    ap_quality.set_defaults(fn=cmd_quality)

    ap_pw = sub.add_parser("playwright", help="Collect HAR + screenshot + DOM + JS-disabled extractability for discovered pages")
    ap_pw.add_argument("target")
    ap_pw.add_argument("--out", default=None)
    ap_pw.add_argument("--max-pages", type=int, default=10, help="Max pages to capture with Playwright (default 10)")
    ap_pw.add_argument("--timeout", type=int, default=30, help="Per-page timeout seconds (default 30)")
    ap_pw.set_defaults(fn=cmd_playwright)

    ap_run = sub.add_parser("run", help="Run crawl + posture + (optional) lighthouse + (optional) playwright and produce run.json/run.md")
    ap_run.add_argument("target")
    ap_run.add_argument("--out", default=None)
    ap_run.add_argument("--max-pages", type=int, default=20)
    ap_run.add_argument("--timeout", type=int, default=30)
    ap_run.add_argument("--budget", default=None, help="Path to budgets.json (default: built-in)")
    ap_run.add_argument("--skip-quality", action="store_true", help="Skip Lighthouse quality step")
    ap_run.add_argument("--skip-playwright", action="store_true", help="Skip Playwright artifacts step")
    ap_run.set_defaults(fn=cmd_run)

    ap_diff = sub.add_parser("diff", help="Diff two run folders (run.json) and detect regressions (exit 1 on fail)")
    ap_diff.add_argument("run_a", help="Path to run A folder (contains run.json)")
    ap_diff.add_argument("run_b", help="Path to run B folder (contains run.json)")
    ap_diff.add_argument("--out", default=None, help="Output directory for diff.{json,md}")
    ap_diff.add_argument(
        "--allow-new-third-parties",
        default=None,
        help="Comma-separated allowlist for NEW third-party domains (if set, new domains not in list cause failure).",
    )
    ap_diff.add_argument(
        "--score-regression-threshold",
        type=float,
        default=0.02,
        help="Score drop threshold (0..1). Default 0.02 (~2 points).",
    )
    ap_diff.set_defaults(fn=cmd_diff)

    return ap


def main() -> int:
    if not platform.system().lower().startswith("win"):
        print("⚠️ This build is optimized for Windows. It may still work elsewhere, but is not the target.", file=sys.stderr)

    ap = build_parser()
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
