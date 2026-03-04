from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from .crawl import discover_pages
from .posture import collect_posture
from .lighthouse import quality_for_urls, DEFAULT_BUDGET
from .playwright_audit import playwright_for_urls
from .diffing import load_run_dir, diff_runs, render_diff_md
from .reporting import build_run_md
from .utils import (
    normalize_target,
    host_from_url,
    safe_write_json,
    safe_write,
    load_json_if_exists,
    now_iso,
)


# -----------------------------
# Commands
# -----------------------------

def cmd_crawl(args: argparse.Namespace) -> int:
    target = normalize_target(args.target)
    host = host_from_url(target)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else Path(f"./inspect_{host}_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    crawl = discover_pages(
        target,
        max_pages=args.max_pages,
        timeout_s=args.timeout,
        out_dir=out_dir,
        workers=args.crawl_workers,
    )

    safe_write_json(out_dir / "pages.json", crawl)

    print(f"✅ Crawl saved: {out_dir / 'pages.json'}")
    return 0


def cmd_quality(args: argparse.Namespace) -> int:
    target = normalize_target(args.target)
    host = host_from_url(target)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else Path(f"./inspect_{host}_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    crawl = discover_pages(
        target,
        max_pages=args.max_pages,
        timeout_s=args.timeout,
        out_dir=out_dir,
        workers=args.crawl_workers,
    )

    urls = [p["url"] for p in (crawl.get("pages") or []) if p.get("url")]
    if not urls:
        urls = [target]

    budget = load_json_if_exists(args.budget) or DEFAULT_BUDGET

    quality = quality_for_urls(
        urls,
        out_dir=out_dir,
        timeout_s=args.timeout,
        budget=budget,
        max_pages=args.max_pages,
        workers=args.lighthouse_workers,
    )

    safe_write_json(out_dir / "quality_summary.json", quality)

    print("✅ Quality audit complete")
    print(f"- summary: {out_dir / 'quality_summary.json'}")
    print(f"- lighthouse: {out_dir / 'lighthouse'}")
    return 0


def cmd_playwright(args: argparse.Namespace) -> int:
    target = normalize_target(args.target)
    host = host_from_url(target)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else Path(f"./inspect_{host}_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    urls = [target]

    summary = playwright_for_urls(
        urls,
        out_dir=out_dir,
        timeout_s=args.timeout,
        max_pages=args.max_pages,
    )

    safe_write_json(out_dir / "playwright_summary.json", summary)

    print("✅ Playwright saved:")
    print(f"- {out_dir / 'playwright_summary.json'}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    target = normalize_target(args.target)
    host = host_from_url(target)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else Path(f"./inspect_{host}_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    crawl = discover_pages(
        target,
        max_pages=args.max_pages,
        timeout_s=args.timeout,
        out_dir=out_dir,
        workers=args.crawl_workers,
    )

    safe_write_json(out_dir / "pages.json", crawl)

    urls = [p["url"] for p in (crawl.get("pages") or []) if p.get("url")]
    if not urls:
        urls = [target]

    posture = collect_posture(target, out_dir=out_dir, timeout_s=args.timeout)
    safe_write_json(out_dir / "posture.json", posture)

    budget = load_json_if_exists(args.budget) or DEFAULT_BUDGET

    quality = quality_for_urls(
        urls,
        out_dir=out_dir,
        timeout_s=args.timeout,
        budget=budget,
        max_pages=args.max_pages,
        workers=args.lighthouse_workers,
    )

    playwright_summary = None
    if not args.skip_playwright:
        playwright_summary = playwright_for_urls(
            urls,
            out_dir=out_dir,
            timeout_s=args.timeout,
            max_pages=args.max_pages,
        )

    run_obj = {
        "version": "0.5",
        "generated_at": now_iso(),
        "target_url": target,
        "crawl": crawl,
        "posture": posture,
        "quality": quality,
        "playwright": playwright_summary,
    }

    safe_write_json(out_dir / "run.json", run_obj)

    md = build_run_md(run_obj)
    safe_write(out_dir / "run.md", md)

    print("✅ Run generated:")
    print(f"- {out_dir / 'run.md'}")
    print(f"- {out_dir / 'run.json'}")

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
    p = argparse.ArgumentParser(prog="site_audit.py")

    sub = p.add_subparsers(dest="cmd", required=True)

    # crawl
    sp = sub.add_parser("crawl")
    sp.add_argument("target")
    sp.add_argument("--max-pages", type=int, default=50)
    sp.add_argument("--timeout", type=int, default=30)
    sp.add_argument("--crawl-workers", type=int, default=8)
    sp.add_argument("--out")
    sp.set_defaults(fn=cmd_crawl)

    # quality
    sp = sub.add_parser("quality")
    sp.add_argument("target")
    sp.add_argument("--max-pages", type=int, default=50)
    sp.add_argument("--timeout", type=int, default=30)
    sp.add_argument("--crawl-workers", type=int, default=8)
    sp.add_argument("--lighthouse-workers", type=int, default=2)
    sp.add_argument("--budget")
    sp.add_argument("--out")
    sp.set_defaults(fn=cmd_quality)

    # playwright
    sp = sub.add_parser("playwright")
    sp.add_argument("target")
    sp.add_argument("--max-pages", type=int, default=10)
    sp.add_argument("--timeout", type=int, default=30)
    sp.add_argument("--out")
    sp.set_defaults(fn=cmd_playwright)

    # run
    sp = sub.add_parser("run")
    sp.add_argument("target")
    sp.add_argument("--max-pages", type=int, default=50)
    sp.add_argument("--timeout", type=int, default=30)
    sp.add_argument("--crawl-workers", type=int, default=8)
    sp.add_argument("--lighthouse-workers", type=int, default=2)
    sp.add_argument("--skip-playwright", action="store_true")
    sp.add_argument("--budget")
    sp.add_argument("--out")
    sp.set_defaults(fn=cmd_run)

    # diff
    sp = sub.add_parser("diff")
    sp.add_argument("run_a")
    sp.add_argument("run_b")
    sp.add_argument("--out", required=True)
    sp.add_argument("--score-regression-threshold", type=float, default=0.05)
    sp.set_defaults(fn=cmd_diff)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())