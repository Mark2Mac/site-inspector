from __future__ import annotations

import json
import concurrent.futures
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .utils import _run, safe_write, slugify_url_for_filename, which, now_iso, ensure_npx_available, _build_windows_cmd_for_exe


# -----------------------------
# v0.4 Playwright (HAR + screenshot + DOM + JS-disabled extractability)
# -----------------------------

def _get_playwright_script_text() -> str:
    script_path = Path(__file__).parent / "scripts" / "playwright_runner.cjs"
    try:
        return script_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RuntimeError(
            f"Playwright runner script not found at {script_path}. "
            "This usually means the package was installed without the scripts/ directory. "
            "Reinstall with: pip install -e ."
        ) from None


def ensure_node_available() -> None:
    if which("node") is None:
        raise RuntimeError("node not found in PATH. Install Node.js and restart your terminal.")
    ensure_npx_available()


def ensure_playwright_chromium_installed(cache_dir: Path, out_dir: Path) -> Dict[str, Any]:
    """
    Installs Playwright Chromium into cache_dir (PLAYWRIGHT_BROWSERS_PATH) once.
    Returns install metadata.
    """
    ensure_node_available()

    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    cache_dir.mkdir(parents=True, exist_ok=True)
    marker = cache_dir / ".chromium_installed"

    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(cache_dir)

    if marker.exists():
        return {"installed": True, "cached": True, "cache_dir": str(cache_dir)}

    npx_path = which("npx") or which("npx.cmd") or which("npx.exe")
    if not npx_path:
        raise RuntimeError("npx not found in PATH. Install Node.js and restart your terminal.")

    cmd = _build_windows_cmd_for_exe(npx_path, ["--yes", "playwright", "install", "chromium"])
    rc, so, se = _run(cmd, env=env, timeout=1800)
    safe_write(raw_dir / "playwright_install.stdout.txt", so)
    safe_write(raw_dir / "playwright_install.stderr.txt", se)

    if rc != 0:
        raise RuntimeError("Playwright install chromium failed. See raw/playwright_install.stderr.txt")

    safe_write(marker, now_iso())
    return {"installed": True, "cached": False, "cache_dir": str(cache_dir)}


def run_playwright_for_url(url: str, *, out_dir: Path, timeout_s: int, cache_dir: Path) -> Dict[str, Any]:
    """
    Runs a Node script via npx with playwright dependency.
    Writes artifacts under out_dir/playwright/{slug}/
    """
    ensure_node_available()

    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Ensure browser exists (once)
    install_meta = ensure_playwright_chromium_installed(cache_dir, out_dir)

    pw_root = out_dir / "playwright"
    pw_root.mkdir(parents=True, exist_ok=True)

    slug = slugify_url_for_filename(url)
    page_dir = pw_root / slug
    page_dir.mkdir(parents=True, exist_ok=True)

    # Write JS runner into out_dir/raw (stable path, debuggable)
    js_path = raw_dir / "playwright_runner_v04.cjs"
    if not js_path.exists():
        safe_write(js_path, _get_playwright_script_text())

    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(cache_dir)

    # Use npx to provide playwright package temporarily:
    # npx -p playwright node script.cjs <url> <outDir> <timeoutMs>
    npx_path = which("npx") or which("npx.cmd") or which("npx.exe")
    if not npx_path:
        raise RuntimeError("npx not found in PATH. Install Node.js and restart your terminal.")

    cmd = _build_windows_cmd_for_exe(
        npx_path,
        [
            "--yes",
            "-p", "playwright",
            "node", str(js_path),
            url, str(page_dir), str(int(timeout_s * 1000)),
        ],
    )

    rc, so, se = _run(cmd, env=env, timeout=max(180, timeout_s * 12))
    safe_write(raw_dir / f"playwright_{slug}.stdout.json", so)
    safe_write(raw_dir / f"playwright_{slug}.stderr.txt", se)

    summary = {"url": url, "slug": slug, "dir": str(page_dir), "rc": rc, "install": install_meta}
    try:
        if so.strip().startswith("{"):
            summary["playwright_summary"] = json.loads(so)
        else:
            summary["error"] = "Playwright runner returned non-JSON stdout."
    except Exception as e:
        summary["error"] = f"Failed parsing Playwright JSON: {e}"

    # Also ensure the per-page summary is referenced
    per_page_summary_path = page_dir / "playwright_summary.json"
    if per_page_summary_path.exists():
        summary["artifacts"] = {
            "summary_json": str(per_page_summary_path),
            "har": str(page_dir / "har.json") if (page_dir / "har.json").exists() else None,
            "screenshot": str(page_dir / "screenshot.png") if (page_dir / "screenshot.png").exists() else None,
            "dom": str(page_dir / "dom.html") if (page_dir / "dom.html").exists() else None,
            "text": str(page_dir / "text.txt") if (page_dir / "text.txt").exists() else None,
            "js_disabled_dom": str(page_dir / "js_disabled_dom.html") if (page_dir / "js_disabled_dom.html").exists() else None,
            "js_disabled_text": str(page_dir / "js_disabled_text.txt") if (page_dir / "js_disabled_text.txt").exists() else None,
        }

    return summary


def playwright_for_urls(urls: List[str], *, out_dir: Path, timeout_s: int, max_pages: int, workers: int = 1) -> Dict[str, Any]:
    cache_dir = out_dir / ".cache" / "playwright"
    results: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []

    work_urls = urls[:max_pages]

    if workers is None or workers < 1:
        workers = 1

    if workers == 1 or len(work_urls) <= 1:
        for url in work_urls:
            r = run_playwright_for_url(url, out_dir=out_dir, timeout_s=timeout_s, cache_dir=cache_dir)
            results.append(r)
            if r.get("rc") not in (0, None) or r.get("error"):
                failures.append({"url": url, "error": r.get("error"), "rc": r.get("rc")})
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {
                ex.submit(run_playwright_for_url, url, out_dir=out_dir, timeout_s=timeout_s, cache_dir=cache_dir): url
                for url in work_urls
            }
            for fut in concurrent.futures.as_completed(futs):
                url = futs[fut]
                try:
                    r = fut.result()
                except Exception as e:
                    r = {"url": url, "error": str(e), "rc": 1}
                results.append(r)
                if r.get("rc") not in (0, None) or r.get("error"):
                    failures.append({"url": url, "error": r.get("error"), "rc": r.get("rc")})

    # Extractability rollup
    extract = {
        "pages_checked": len(results),
        "pages_js_disabled_readable": 0,
        "pages_js_disabled_not_readable": 0,
        "details": []
    }
    for r in results:
        ps = (r.get("playwright_summary") or {})
        ex = (ps.get("extractability") or {})
        readable = ex.get("disabledStillReadable")
        if readable is True:
            extract["pages_js_disabled_readable"] += 1
        elif readable is False:
            extract["pages_js_disabled_not_readable"] += 1
        extract["details"].append({
            "url": r.get("url"),
            "disabledStillReadable": readable,
            "enabledTextLen": ex.get("enabledTextLen"),
            "disabledTextLen": ex.get("disabledTextLen"),
        })

    summary = {
        "generated_at": now_iso(),
        "pages_tested": len(results),
        "pages_failed": len(failures),
        "passed": len(failures) == 0,
        "results": results,
        "failures": failures,
        "extractability_rollup": extract,
    }
    return summary
