from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .crawl import discover_pages
from .posture import collect_posture
from .lighthouse import quality_for_urls, DEFAULT_BUDGET, select_lighthouse_targets
from .playwright_audit import playwright_for_urls
from .diffing import load_run_dir, diff_runs, render_diff_md
from .reporting import build_run_md
from .template_clustering import cluster_urls, summarize_clusters
from .dom_clustering import cluster_by_dom_fingerprint, summarize_dom_clusters
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

    if args.net_workers is not None:
        args.crawl_workers = args.net_workers

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else Path(f"./inspect_{host}_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    t0_total = time.perf_counter()
    timings = {}

    t0 = time.perf_counter()
    crawl = discover_pages(
        target,
        max_pages=args.max_pages,
        timeout_s=args.timeout,
        out_dir=out_dir,
        workers=args.crawl_workers,
        resume=bool(args.resume),
    )

    safe_write_json(out_dir / "pages.json", crawl)

    print(f"✅ Crawl saved: {out_dir / 'pages.json'}")
    return 0


def cmd_quality(args: argparse.Namespace) -> int:
    target = normalize_target(args.target)
    host = host_from_url(target)

    if args.net_workers is not None:
        args.crawl_workers = args.net_workers

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else Path(f"./inspect_{host}_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    t0_total = time.perf_counter()
    timings = {}

    t0 = time.perf_counter()
    # Resume-friendly: reuse existing pages.json when present.
    if args.resume and (out_dir / "pages.json").exists():
        crawl = load_json_if_exists(str(out_dir / "pages.json")) or {}
    else:
        crawl = discover_pages(
            target,
            max_pages=args.max_pages,
            timeout_s=args.timeout,
            out_dir=out_dir,
            workers=args.crawl_workers,
            resume=bool(args.resume),
        )

    urls = [p["url"] for p in (crawl.get("pages") or []) if p.get("url")]
    if not urls:
        urls = [target]

    

    # Template clustering (URL + DOM fingerprint)
    try:
        pages_list = crawl.get("pages") or []
        url_clusters = cluster_urls([p.get("url") for p in pages_list if p.get("url")])
        dom_clusters = cluster_by_dom_fingerprint(pages_list)

        crawl["templates"] = {
            "url": {
                "summary": summarize_clusters(url_clusters),
            },
            "dom": {
                "summary": summarize_dom_clusters(dom_clusters),
            },
        }
    except Exception:
        # Best-effort; never fail the run for clustering.
        pass
# Persist crawl for later reuse.
    safe_write_json(out_dir / "pages.json", crawl)

    # Resume-friendly: reuse existing quality summary when present.
    if args.resume and (out_dir / "quality_summary.json").exists():
        quality = load_json_if_exists(str(out_dir / "quality_summary.json")) or {}
    else:
        budget = load_json_if_exists(args.budget) or DEFAULT_BUDGET

        # A6: smarter Lighthouse targeting (sampling)
        always_include = None
        if args.lighthouse_include:
            try:
                always_include = [
                    ln.strip()
                    for ln in Path(args.lighthouse_include).read_text(encoding="utf-8").splitlines()
                    if ln.strip() and not ln.strip().startswith("#")
                ]
            except Exception:
                always_include = None

        if args.lighthouse_sample is not None:

# B2: template-aware grouping for sampling (DOM fingerprint if available, else URL template)
group_map = None
try:
    pages_list = crawl.get("pages") or []
    gm = {}
    has_fp = False
    for p in pages_list:
        u = p.get("url")
        if not u:
            continue
        fp = p.get("dom_fingerprint")
        if fp:
            gm[u] = f"dom:{fp}"
            has_fp = True
    if not has_fp:
        from .template_clustering import url_to_template
        for p in pages_list:
            u = p.get("url")
            if not u:
                continue
            gm[u] = f"url:{url_to_template(u)}"
    if gm:
        group_map = gm
except Exception:
    group_map = None

            sel = select_lighthouse_targets(
                urls,
                target_url=target,
                sample_total=int(args.lighthouse_sample),
                per_group=int(args.lighthouse_per_group),
                always_include=always_include,
                group_map=group_map,
            )
            urls_for_lh = sel.get("selected_urls") or urls
            selection_meta = sel.get("selection")
        else:
            urls_for_lh = urls
            selection_meta = {"mode": "all", "sample_total": None, "per_group": None, "always_include": []}

        t0 = time.perf_counter()
        quality = quality_for_urls(
            urls_for_lh,
            out_dir=out_dir,
            timeout_s=args.timeout,
            budget=budget,
            max_pages=args.lighthouse_max_pages if args.lighthouse_max_pages is not None else args.max_pages,
            workers=args.lighthouse_workers,
        )

        # Persist selection info for reporting/diffing.
        try:
            quality["selection"] = selection_meta
            quality["selected_urls"] = urls_for_lh
        except Exception:
            pass

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

    # Resume-friendly: reuse existing summary when present.
    if args.resume and (out_dir / "playwright_summary.json").exists():
        summary = load_json_if_exists(str(out_dir / "playwright_summary.json")) or {}
    else:
        summary = playwright_for_urls(
            urls,
            out_dir=out_dir,
            timeout_s=args.timeout,
            max_pages=args.max_pages,
            workers=args.playwright_workers,
        )

    safe_write_json(out_dir / "playwright_summary.json", summary)

    print("✅ Playwright saved:")
    print(f"- {out_dir / 'playwright_summary.json'}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    target = normalize_target(args.target)
    host = host_from_url(target)

    if args.net_workers is not None:
        args.crawl_workers = args.net_workers

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else Path(f"./inspect_{host}_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    t0_total = time.perf_counter()
    timings = {}

    # Resume-friendly: reuse existing pages.json when present.
    if args.resume and (out_dir / "pages.json").exists():
        crawl = load_json_if_exists(str(out_dir / "pages.json")) or {}
        timings["crawl_s"] = 0.0
    else:
        t0 = time.perf_counter()
        crawl = discover_pages(
            target,
            max_pages=args.max_pages,
            timeout_s=args.timeout,
            out_dir=out_dir,
            workers=args.crawl_workers,
            resume=bool(args.resume),
        )

        safe_write_json(out_dir / "pages.json", crawl)
        timings["crawl_s"] = round(time.perf_counter() - t0, 3)

    urls = [p["url"] for p in (crawl.get("pages") or []) if p.get("url")]
    if not urls:
        urls = [target]

    if args.resume and (out_dir / "posture.json").exists():
        posture = load_json_if_exists(str(out_dir / "posture.json")) or {}
        timings["posture_s"] = 0.0
    else:
        t0 = time.perf_counter()
        posture = collect_posture(target, out_dir=out_dir, timeout_s=args.timeout)
        safe_write_json(out_dir / "posture.json", posture)
        timings["posture_s"] = round(time.perf_counter() - t0, 3)

    budget = load_json_if_exists(args.budget) or DEFAULT_BUDGET

    if args.resume and (out_dir / "quality_summary.json").exists():
        quality = load_json_if_exists(str(out_dir / "quality_summary.json")) or {}
        timings["lighthouse_s"] = 0.0
    else:
        # A6: smarter Lighthouse targeting (sampling)
        always_include = None
        if args.lighthouse_include:
            try:
                always_include = [
                    ln.strip()
                    for ln in Path(args.lighthouse_include).read_text(encoding="utf-8").splitlines()
                    if ln.strip() and not ln.strip().startswith("#")
                ]
            except Exception:
                always_include = None

        if args.lighthouse_sample is not None:
            sel = select_lighthouse_targets(
                urls,
                target_url=target,
                sample_total=int(args.lighthouse_sample),
                per_group=int(args.lighthouse_per_group),
                always_include=always_include,
                group_map=group_map,
            )
            urls_for_lh = sel.get("selected_urls") or urls
            selection_meta = sel.get("selection")
        else:
            urls_for_lh = urls
            selection_meta = {"mode": "all", "sample_total": None, "per_group": None, "always_include": []}

        t0 = time.perf_counter()
        quality = quality_for_urls(
            urls_for_lh,
            out_dir=out_dir,
            timeout_s=args.timeout,
            budget=budget,
            max_pages=args.lighthouse_max_pages if args.lighthouse_max_pages is not None else args.max_pages,
            workers=args.lighthouse_workers,
        )
        timings["lighthouse_s"] = round(time.perf_counter() - t0, 3)

        try:
            quality["selection"] = selection_meta
            quality["selected_urls"] = urls_for_lh
        except Exception:
            pass

        # Keep an explicit cache file so --resume works consistently.
        safe_write_json(out_dir / "quality_summary.json", quality)

    playwright_summary = None
    if not args.skip_playwright:
        if args.resume and (out_dir / "playwright_summary.json").exists():
            playwright_summary = load_json_if_exists(str(out_dir / "playwright_summary.json")) or {}
            timings["playwright_s"] = 0.0
        else:
            t0 = time.perf_counter()
            playwright_summary = playwright_for_urls(
                urls,
                out_dir=out_dir,
                timeout_s=args.timeout,
                max_pages=args.max_pages,
                workers=args.playwright_workers,
            )
            timings["playwright_s"] = round(time.perf_counter() - t0, 3)

    run_obj = {
        "version": "0.6",
        "generated_at": now_iso(),
        "target_url": target,
        "host": host,
        "crawl": crawl,
        "posture": posture,
        "quality": quality,
        "playwright": playwright_summary,
        "timings": {**timings, "total_s": round(time.perf_counter() - t0_total, 3)},
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
    sp.add_argument("--net-workers", type=int, default=None, help="Alias for --crawl-workers; overrides when set")
    sp.add_argument("--resume", action="store_true", help="Reuse cached artifacts in --out directory when present")
    sp.add_argument("--out")
    sp.set_defaults(fn=cmd_crawl)

    # quality
    sp = sub.add_parser("quality")
    sp.add_argument("target")
    sp.add_argument("--max-pages", type=int, default=50)
    sp.add_argument("--timeout", type=int, default=30)
    sp.add_argument("--crawl-workers", type=int, default=8)
    sp.add_argument("--net-workers", type=int, default=None, help="Alias for --crawl-workers; overrides when set")
    sp.add_argument("--lighthouse-workers", type=int, default=2)
    sp.add_argument("--lighthouse-sample", type=int, default=None, help="Run Lighthouse on a sampled subset of pages (max N). Default: all pages")
    sp.add_argument("--lighthouse-per-group", type=int, default=1, help="When sampling, pick up to K pages per top-level path group")
    sp.add_argument("--lighthouse-max-pages", type=int, default=None, help="Hard cap for Lighthouse pages (defaults to --max-pages)")
    sp.add_argument("--lighthouse-include", default=None, help="Path to a .txt file with URLs to always include (one per line; # comments allowed)")
    sp.add_argument("--budget")
    sp.add_argument("--resume", action="store_true", help="Reuse cached artifacts in --out directory when present")
    sp.add_argument("--out")
    sp.set_defaults(fn=cmd_quality)

    # playwright
    sp = sub.add_parser("playwright")
    sp.add_argument("target")
    sp.add_argument("--max-pages", type=int, default=10)
    sp.add_argument("--timeout", type=int, default=30)
    sp.add_argument("--playwright-workers", type=int, default=1)
    sp.add_argument("--resume", action="store_true", help="Reuse cached artifacts in --out directory when present")
    sp.add_argument("--out")
    sp.set_defaults(fn=cmd_playwright)

    # run
    sp = sub.add_parser("run")
    sp.add_argument("target")
    sp.add_argument("--max-pages", type=int, default=50)
    sp.add_argument("--timeout", type=int, default=30)
    sp.add_argument("--crawl-workers", type=int, default=8)
    sp.add_argument("--net-workers", type=int, default=None, help="Alias for --crawl-workers; overrides when set")
    sp.add_argument("--lighthouse-workers", type=int, default=2)
    sp.add_argument("--lighthouse-sample", type=int, default=None, help="Run Lighthouse on a sampled subset of pages (max N). Default: all pages")
    sp.add_argument("--lighthouse-per-group", type=int, default=1, help="When sampling, pick up to K pages per top-level path group")
    sp.add_argument("--lighthouse-max-pages", type=int, default=None, help="Hard cap for Lighthouse pages (defaults to --max-pages)")
    sp.add_argument("--lighthouse-include", default=None, help="Path to a .txt file with URLs to always include (one per line; # comments allowed)")
    sp.add_argument("--playwright-workers", type=int, default=1)
    sp.add_argument("--skip-playwright", action="store_true")
    sp.add_argument("--budget")
    sp.add_argument("--resume", action="store_true", help="Reuse cached artifacts in --out directory when present")
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