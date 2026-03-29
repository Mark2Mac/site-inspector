from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .log import get_logger, setup_logging
from .crawl import discover_pages
from .posture import collect_posture
from .lighthouse import quality_for_urls, DEFAULT_BUDGET, select_lighthouse_targets
from .playwright_audit import playwright_for_urls
from .diffing import load_run_dir, diff_runs, render_diff_md
from .reporting import build_run_md
from .duplicates import detect_duplicate_pages, render_duplicate_summary_md
from .template_clustering import cluster_urls, summarize_clusters
from .dom_clustering import cluster_by_dom_fingerprint, summarize_dom_clusters
from .seo_audit import audit_seo
from .ai_audit import audit_ai_readiness
from .graph import analyze_graph
from .html_report import build_run_html, build_diff_html
from .utils import (
    normalize_target,
    host_from_url,
    safe_write_json,
    safe_write,
    load_json_if_exists,
    now_iso,
)


_log = get_logger("cli")


def _safe_console_print(message: str) -> None:
    try:
        print(message)
        return
    except UnicodeEncodeError:
        pass

    stream = getattr(sys, "stdout", None)
    encoding = getattr(stream, "encoding", None) or "utf-8"
    fallback = message.encode(encoding, errors="replace").decode(encoding, errors="replace")
    print(fallback)


def _print_generated_block(label: str, paths: list[Path]) -> None:
    _safe_console_print(f"✅ {label}:")
    for path in paths:
        _safe_console_print(f"- {path}")


def _maybe_show_first_run_tip() -> None:
    marker = Path(tempfile.gettempdir()) / "site_inspector_runtime" / ".first_run_tip"
    if marker.exists():
        return
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(now_iso(), encoding="utf-8")
    except OSError:
        return
    _safe_console_print("")
    _safe_console_print(
        "Tip: Site Inspector was originally built to audit dedicatodesign.com"
        " \u2014 a design studio in Milan."
    )


def _safe_console_error_print(message: str) -> None:
    try:
        print(message, file=sys.stderr)
        return
    except UnicodeEncodeError:
        pass

    stream = getattr(sys, "stderr", None)
    encoding = getattr(stream, "encoding", None) or "utf-8"
    fallback = message.encode(encoding, errors="replace").decode(encoding, errors="replace")
    print(fallback, file=sys.stderr)


def _load_lighthouse_include_urls(path: str | None) -> list[str] | None:
    if not path:
        return None
    try:
        return [
            ln.strip()
            for ln in Path(path).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
    except Exception:
        return None


def _build_lighthouse_group_map(crawl: dict | None) -> dict[str, str] | None:
    try:
        pages_list = (crawl or {}).get("pages") or []
        gm: dict[str, str] = {}
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
        return gm or None
    except Exception:
        return None


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

    _print_generated_block("Crawl saved", [out_dir / "pages.json"])
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
    except Exception as e:
        # Best-effort; never fail the run for clustering.
        _log.warning("Template clustering failed: %s", e)
    # Persist crawl for later reuse.
    safe_write_json(out_dir / "pages.json", crawl)

    # Resume-friendly: reuse existing quality summary when present.
    if args.resume and (out_dir / "quality_summary.json").exists():
        quality = load_json_if_exists(str(out_dir / "quality_summary.json")) or {}
    else:
        budget = load_json_if_exists(args.budget) or DEFAULT_BUDGET

        # A6: smarter Lighthouse targeting (sampling)
        always_include = _load_lighthouse_include_urls(args.lighthouse_include)

        if args.lighthouse_sample is not None:
            group_map = _build_lighthouse_group_map(crawl)
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
        except Exception as e:
            _log.warning("Failed to attach selection metadata: %s", e)

        safe_write_json(out_dir / "quality_summary.json", quality)

    _print_generated_block("Quality audit complete", [out_dir / "quality_summary.json", out_dir / "lighthouse"])
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

    _print_generated_block("Playwright saved", [out_dir / "playwright_summary.json"])
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
        always_include = _load_lighthouse_include_urls(args.lighthouse_include)

        if args.lighthouse_sample is not None:
            group_map = _build_lighthouse_group_map(crawl)
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
        except Exception as e:
            _log.warning("Failed to attach selection metadata: %s", e)

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
        "version": __version__,
        "generated_at": now_iso(),
        "target_url": target,
        "host": host,
        "crawl": crawl,
        "posture": posture,
        "quality": quality,
        "playwright": playwright_summary,
        "timings": {**timings, "total_s": round(time.perf_counter() - t0_total, 3)},
    }

    # B3: duplicate candidates (DOM fingerprint preferred; fallback to normalized path)
    try:
        dup = detect_duplicate_pages((crawl or {}).get("pages") or [])
    except Exception as e:
        _log.warning("Duplicate detection failed: %s", e)
        dup = {"duplicate_groups": [], "duplicate_group_count": 0, "duplicate_url_count": 0}
    run_obj["duplicates"] = dup

    # Milestone 3: first SEO auditing layer
    try:
        run_obj["seo"] = audit_seo(crawl, posture)
    except Exception as e:
        _log.warning("SEO audit failed: %s", e)
        run_obj["seo"] = {"pages_analyzed": 0, "issues": []}

    # Milestone 4: AI crawler optimization layer
    try:
        run_obj["ai"] = audit_ai_readiness(crawl, posture, playwright_summary)
    except Exception as e:
        _log.warning("AI audit failed: %s", e)
        run_obj["ai"] = {"pages_analyzed": 0, "issues": []}

    # Graph analysis layer
    try:
        run_obj["graph"] = analyze_graph(crawl)
    except Exception as e:
        _log.warning("Graph analysis failed: %s", e)
        run_obj["graph"] = {"nodes": 0, "edges": 0, "note": f"Graph analysis failed: {e}"}

    safe_write_json(out_dir / "run.json", run_obj)

    md = build_run_md(run_obj)

    try:
        md = md.rstrip() + "\n\n" + render_duplicate_summary_md(run_obj.get("duplicates") or {})
    except Exception as e:
        _log.warning("Failed to render duplicate summary: %s", e)
    safe_write(out_dir / "run.md", md)

    try:
        safe_write(out_dir / "run.html", build_run_html(run_obj))
    except Exception as e:
        _log.warning("HTML report generation failed: %s", e)

    _print_generated_block("Run generated", [out_dir / "run.html", out_dir / "run.md", out_dir / "run.json"])
    _maybe_show_first_run_tip()

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

    try:
        safe_write(out_dir / "diff.html", build_diff_html(diff))
    except Exception as e:
        _log.warning("HTML diff report generation failed: %s", e)

    _print_generated_block("Diff generated", [out_dir / "diff.html", out_dir / "diff.md", out_dir / "diff.json"])

    return 0


# -----------------------------
# CLI
# -----------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="site_audit.py")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

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
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except (FileNotFoundError, ValueError) as exc:
        if os.environ.get("SITE_INSPECTOR_DEBUG"):
            traceback.print_exc()
        else:
            _safe_console_error_print(str(exc))
        return 2
    except KeyboardInterrupt:
        _safe_console_error_print("Interrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())