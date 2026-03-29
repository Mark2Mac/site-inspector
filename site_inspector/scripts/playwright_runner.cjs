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
