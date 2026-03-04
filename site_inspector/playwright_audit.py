from __future__ import annotations

import json
import os
import platform
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .utils import _run, safe_write, safe_write_json, slugify_url_for_filename, which, now_iso


# -----------------------------
# v0.4 Playwright (HAR + screenshot + DOM + JS-disabled extractability)
# -----------------------------

PLAYWRIGHT_NODE_SCRIPT = r"""
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

function ensureDir(p) { fs.mkdirSync(p, { recursive: true }); }
function writeText(p, s) { fs.writeFileSync(p, s ?? "", { encoding: "utf-8" }); }

async function grab(url, outDir, timeoutMs, jsEnabled) {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    javaScriptEnabled: jsEnabled,
    acceptDownloads: false,
    ignoreHTTPSErrors: true,
    viewport: { width: 1365, height: 768 },
  });

  const page = await context.newPage();

  // HAR only for JS-enabled run (meaningful network)
  let harPath = null;
  if (jsEnabled) {
    harPath = path.join(outDir, "har.json");
    await context.tracing.start({ screenshots: false, snapshots: false });
    await context.route("**/*", route => route.continue());
  }

  const started = Date.now();
  let result = {
    url,
    jsEnabled,
    finalUrl: null,
    status: null,
    timings: { totalMs: null },
    errors: [],
    textLen: 0,
    hasMeaningfulText: false,
    files: {}
  };

  try {
    const resp = await page.goto(url, { waitUntil: "domcontentloaded", timeout: timeoutMs });
    result.finalUrl = page.url();
    result.status = resp ? resp.status() : null;

    // best-effort wait for network to settle (only when JS enabled)
    if (jsEnabled) {
      try {
        await page.waitForLoadState("networkidle", { timeout: Math.min(15000, timeoutMs) });
      } catch (e) {
        // not fatal
      }
    }

    // screenshot
    const screenshotPath = path.join(outDir, jsEnabled ? "screenshot.png" : "js_disabled_screenshot.png");
    await page.screenshot({ path: screenshotPath, fullPage: true });
    result.files.screenshot = screenshotPath;

    // DOM
    const html = await page.content();
    const domPath = path.join(outDir, jsEnabled ? "dom.html" : "js_disabled_dom.html");
    writeText(domPath, html);
    result.files.dom = domPath;

    // Text extract
    const text = await page.evaluate(() => {
      const t = document?.body?.innerText || "";
      return t.replace(/\s+/g, " ").trim();
    });
    const textPath = path.join(outDir, jsEnabled ? "text.txt" : "js_disabled_text.txt");
    writeText(textPath, text);
    result.files.text = textPath;

    result.textLen = (text || "").length;
    result.hasMeaningfulText = result.textLen >= 200; // heuristic threshold

    // Save HAR for JS-enabled by using Playwright's built-in har recorder pattern:
    // Playwright's context.newContext({ recordHar: { path }}) is supported; we use it by re-creating context.
  } catch (e) {
    result.errors.push(String(e && e.message ? e.message : e));
  } finally {
    result.timings.totalMs = Date.now() - started;

    // If JS enabled and we want HAR, easiest is to use recordHar in a second short run:
    // (Yes it's extra time; keeps script dependency-light and stable across Playwright versions.)
    await browser.close();
  }

  // HAR run (JS enabled only) — short & focused
  if (jsEnabled) {
    const browser2 = await chromium.launch({ headless: true });
    const context2 = await browser2.newContext({
      javaScriptEnabled: true,
      ignoreHTTPSErrors: true,
      recordHar: { path: path.join(outDir, "har.json"), content: "omit" },
      viewport: { width: 1365, height: 768 },
    });
    const page2 = await context2.newPage();
    try {
      await page2.goto(url, { waitUntil: "networkidle", timeout: timeoutMs });
    } catch (e) {
      result.errors.push("har_run: " + String(e && e.message ? e.message : e));
    } finally {
      await context2.close();
      await browser2.close();
      result.files.har = path.join(outDir, "har.json");
    }
  }

  return result;
}

async function main() {
  const url = process.argv[2];
  const outDir = process.argv[3];
  const timeoutMs = Number(process.argv[4] || "30000");

  ensureDir(outDir);

  const enabled = await grab(url, outDir, timeoutMs, true);
  const disabled = await grab(url, outDir, timeoutMs, false);

  const summary = {
    url,
    generatedAt: new Date().toISOString(),
    jsEnabled: enabled,
    jsDisabled: disabled,
    extractability: {
      enabledTextLen: enabled.textLen,
      disabledTextLen: disabled.textLen,
      disabledStillReadable: disabled.hasMeaningfulText,
      notes: disabled.hasMeaningfulText
        ? "Content remains readable without JavaScript (good for conservative crawlers)."
        : "Content largely requires JavaScript (may reduce extractability for some crawlers)."
    }
  };

  const summaryPath = path.join(outDir, "playwright_summary.json");
  writeText(summaryPath, JSON.stringify(summary, null, 2));
  console.log(JSON.stringify(summary, null, 2));
}

main().catch((e) => {
  console.error(String(e && e.stack ? e.stack : e));
  process.exit(2);
});
"""


def ensure_npx_available() -> None:
    """Ensure npx is available on PATH (Windows-friendly)."""
    if (which("npx") or which("npx.cmd") or which("npx.exe")) is None:
        raise RuntimeError("npx not found in PATH. Install Node.js (includes npm/npx) and restart your terminal.")



def _build_windows_cmd_for_exe(exe_path: str, args: List[str]) -> List[str]:
    """Build a subprocess command that works on Windows for .cmd/.bat wrappers."""
    exe_lower = exe_path.lower()
    if platform.system().lower().startswith('win') and (exe_lower.endswith('.cmd') or exe_lower.endswith('.bat')):
        # Use cmd.exe to execute batch wrappers reliably with shell=False
        return ["cmd", "/c", exe_path, *args]
    return [exe_path, *args]

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
        safe_write(js_path, PLAYWRIGHT_NODE_SCRIPT)

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


def playwright_for_urls(urls: List[str], *, out_dir: Path, timeout_s: int, max_pages: int) -> Dict[str, Any]:
    cache_dir = out_dir / ".cache" / "playwright"
    results: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []

    for url in urls[:max_pages]:
        r = run_playwright_for_url(url, out_dir=out_dir, timeout_s=timeout_s, cache_dir=cache_dir)
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
