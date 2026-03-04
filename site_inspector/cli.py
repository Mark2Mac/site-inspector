from __future__ import annotations

import argparse
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from .crawl import discover_pages
from .diffing import diff_runs, load_run_dir, render_diff_md
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

    posture = collect_posture(target, out_dir=out_dir, timeout_s=args.timeout)
    safe_write_json(out_dir / "posture.json", posture)

    print(f"✅ Posture saved: {out_dir / 'posture.json'}")
    return 0


def cmd_playwright(args: argparse.Namespace) -> int:
    target = normalize_target(args.target)
    host = host_from_url(target)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else Path(f"./inspect_{host}_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    urls = [target]
    summary = playwright_for_urls(urls, out_dir=out_dir, timeout_s=args.timeout, max_pages=args.max_pages)

    safe_write_json(out_dir / "playwright_summary.json", summary)

    print("✅ Playwright saved:")
    print(f"- {out_dir / 'playwright_summary.json'}")
    print(f"- playwright: {out_dir / 'playwright'}")
    print(f"- raw: {out_dir / 'raw'}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    target = normalize_target(args.target)
    host = host_from_url(target)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else Path(f"./inspect_{host}_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Crawl
    crawl = discover_pages(target, max_pages=args.max_pages, timeout_s=args.timeout, out_dir=out_dir)
    safe_write_json(out_dir / "pages.json", crawl)

    urls = [p["url"] for p in (crawl.get("pages") or []) if p.get("url")]
    if not urls:
        urls = [target]

    # Posture
    posture = collect_posture(target, out_dir=out_dir, timeout_s=args.timeout)
    safe_write_json(out_dir / "posture.json", posture)

    # Budget
    budget = load_json_if_exists(args.budget) or DEFAULT_BUDGET

    # Lighthouse quality
    quality = quality_for_urls(urls, out_dir=out_dir, timeout_s=args.timeout, budget=budget, max_pages=args.max_pages)

    # Playwright (optional)
    playwright_summary = None
    if not args.skip_playwright:
        playwright_summary = playwright_for_urls(urls, out_dir=out_dir, timeout_s=args.timeout, max_pages=args.max_pages)
        safe_write_json(out_dir / "playwright_summary.json", playwright_summary)

    # Build run.json
    run_obj = {
        "version": "0.4",
        "generated_at": now_iso(),
        "target_url": target,
        "crawl": crawl,
        "posture": posture,
        "quality": quality,
        "playwright": playwright_summary,
        "summary": {
            "pages_count": len(urls),
        },
    }

    safe_write_json(out_dir / "run.json", run_obj)
    md = build_run_md(run_obj)
    safe_write(out_dir / "run.md", md)

    print("✅ Run generated:")
    print(f"- {out_dir / 'run.md'}")
    print(f"- {out_dir / 'run.json'}")
    print(f"- pages: {out_dir / 'pages.json'}")
    print(f"- posture: {out_dir / 'posture.json'}")
    print(f"- lighthouse: {out_dir / 'lighthouse'}")
    print(f"- playwright: {out_dir / 'playwright'}")
    print(f"- raw: {out_dir / 'raw'}")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    run_a_dir = Path(args.run_a)
    run_b_dir = Path(args.run_b)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    run_a = load_run_dir(run_a_dir)
    run_b = load_run_dir(run_b_dir)

    diff = diff_runs(
        run_a,
        run_b,
        allow_new_third_parties=args.allow_new_third_parties,
        fail_on_new_third_parties=args.fail_on_new_third_parties,
        score_regression_threshold=args.score_regression_threshold,
    )

    safe_write_json(out_dir / "diff.json", diff)
    safe_write(out_dir / "diff.md", render_diff_md(diff))

    print("✅ Diff generated:")
    print(f"- {out_dir / 'diff.md'}")
    print(f"- {out_dir / 'diff.json'}")
    return 0


# -----------------------------
# CLI
# -----------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="site_audit.py", description="Site Inspector (Windows-first)")

    sub = p.add_subparsers(dest="cmd", required=True)

    # crawl
    sp = sub.add_parser("crawl", help="Discover pages (crawl)")
    sp.add_argument("target", help="Target URL")
    sp.add_argument("--max-pages", type=int, default=50)
    sp.add_argument("--timeout", type=int, default=30)
    sp.add_argument("--out", type=str, default=None)
    sp.set_defaults(fn=cmd_crawl)

    # posture
    sp = sub.add_parser("posture", help="Collect posture / tech / headers")
    sp.add_argument("target", help="Target URL")
    sp.add_argument("--timeout", type=int, default=30)
    sp.add_argument("--out", type=str, default=None)
    sp.set_defaults(fn=cmd_posture)

    # playwright
    sp = sub.add_parser("playwright", help="Render + collect artifacts with Playwright")
    sp.add_argument("target", help="Target URL")
    sp.add_argument("--max-pages", type=int, default=10)
    sp.add_argument("--timeout", type=int, default=30)
    sp.add_argument("--out", type=str, default=None)
    sp.set_defaults(fn=cmd_playwright)

    # run
    sp = sub.add_parser("run", help="Full run (crawl + posture + lighthouse + optional playwright)")
    sp.add_argument("target", help="Target URL")
    sp.add_argument("--max-pages", type=int, default=50)
    sp.add_argument("--timeout", type=int, default=30)
    sp.add_argument("--out", type=str, default=None)
    sp.add_argument("--skip-playwright", action="store_true", default=False)
    sp.add_argument("--budget", type=str, default=None)
    sp.set_defaults(fn=cmd_run)

    # diff
    sp = sub.add_parser("diff", help="Diff two runs")
    sp.add_argument("run_a", help="Path to run A dir (contains run.json)")
    sp.add_argument("run_b", help="Path to run B dir (contains run.json)")
    sp.add_argument("--out", required=True, help="Output directory for diff artifacts")
    sp.add_argument("--allow-new-third-parties", nargs="*", default=None)
    sp.add_argument("--fail-on-new-third-parties", action="store_true", default=False)
    sp.add_argument("--score-regression-threshold", type=float, default=0.05)
    sp.set_defaults(fn=cmd_diff)

    return p


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())