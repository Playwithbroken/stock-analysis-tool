import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const TARGET_URL = process.env.QA_TARGET_URL || "https://web-production-8546b.up.railway.app/";
const ACCESS_CODE = process.env.QA_ACCESS_CODE || "100363";
const OUT_DIR = path.resolve("qa-artifacts");
const TICKERS = (process.env.QA_TICKERS || "AAPL,PFE,BTC-USD")
  .split(",")
  .map((item) => item.trim().toUpperCase())
  .filter(Boolean);
const MARKETS_STRESS_COUNT = Number(process.env.QA_MARKETS_STRESS_COUNT || "20");
const VIEWPORTS = [
  { name: "1366x768", width: 1366, height: 768 },
  { name: "1536x960", width: 1536, height: 960 },
  { name: "1920x1080", width: 1920, height: 1080 },
];

fs.mkdirSync(OUT_DIR, { recursive: true });

function stamp() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

const runId = stamp();
const runDir = path.join(OUT_DIR, runId);
fs.mkdirSync(runDir, { recursive: true });

const summary = {
  runId,
  target: TARGET_URL,
  at: new Date().toISOString(),
  inputs: {
    tickers: TICKERS,
    marketsStressCount: MARKETS_STRESS_COUNT,
    viewports: VIEWPORTS,
  },
  events: [],
  issues: [],
  metrics: {
    requestFailedAborted: 0,
    requestFailedNonAborted: 0,
    http404: 0,
    http5xx: 0,
    marketsStressRuns: 0,
    marketsUnexpectedAnalyze: 0,
    chartStillLoading: 0,
    tickerRuns: 0,
  },
  perViewport: {},
  screenshotDir: runDir,
};

function pushIssue(issue) {
  summary.issues.push(issue);
}

function pushEvent(message) {
  summary.events.push(message);
}

async function findTabButton(page, patterns) {
  for (const pattern of patterns) {
    const locator = page.getByRole("button", { name: pattern });
    const count = await locator.count();
    for (let i = 0; i < count; i += 1) {
      const candidate = locator.nth(i);
      if (await candidate.isVisible()) {
        return candidate;
      }
    }
  }
  return null;
}

async function waitForNavigationShell(page, timeoutMs = 12000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const hasAnalyzer = await page.getByRole("button", { name: /Analyzer|Analyze/i }).count();
    const hasMarkets = await page.getByRole("button", { name: /Markets/i }).count();
    const hasPortfolio = await page.getByRole("button", { name: /Portfolio/i }).count();
    if (hasAnalyzer || hasMarkets || hasPortfolio) return true;
    await page.waitForTimeout(250);
  }
  return false;
}

function attachPageObservers(page, viewportName) {
  page.on("console", (msg) => {
    const type = msg.type();
    const text = msg.text();
    if (type === "error" || /width\(-1\)|height\(-1\)|dynamically imported module|Failed to fetch/i.test(text)) {
      pushIssue({ kind: "console", viewport: viewportName, type, text });
    }
  });

  page.on("pageerror", (error) => {
    pushIssue({ kind: "pageerror", viewport: viewportName, text: String(error) });
  });

  page.on("requestfailed", (req) => {
    const failureText = req.failure()?.errorText || "unknown";
    if (/ERR_ABORTED/i.test(failureText)) {
      summary.metrics.requestFailedAborted += 1;
      return;
    }
    summary.metrics.requestFailedNonAborted += 1;
    pushIssue({
      kind: "requestfailed",
      viewport: viewportName,
      url: req.url(),
      method: req.method(),
      resourceType: req.resourceType(),
      failure: failureText,
    });
  });

  page.on("response", (res) => {
    const status = res.status();
    if (status < 400) return;
    const req = res.request();
    if (status === 404) summary.metrics.http404 += 1;
    if (status >= 500) summary.metrics.http5xx += 1;
    pushIssue({
      kind: "http",
      viewport: viewportName,
      status,
      url: res.url(),
      method: req.method(),
      resourceType: req.resourceType(),
    });
  });
}

async function ensureLoggedIn(page, viewportName) {
  const passwordInput = page.getByLabel("6-digit workspace access code");
  if (await passwordInput.count()) {
    await passwordInput.fill(ACCESS_CODE);
    await page.getByRole("button", { name: /unlock/i }).click();
    await page.waitForTimeout(2200);
    pushEvent(`[${viewportName}] Login submitted`);
  }
}

async function runMarketsStress(page, viewportName) {
  const marketsTab = await findTabButton(page, [/^Markets$/i]);
  const analyzerTab = await findTabButton(page, [/^Analyzer$/i, /^Analyze$/i]);
  if (!marketsTab) {
    pushIssue({ kind: "ui", viewport: viewportName, text: "Markets tab not found" });
    return;
  }

  for (let i = 0; i < MARKETS_STRESS_COUNT; i += 1) {
    await marketsTab.click();
    await page.waitForTimeout(220);
    summary.metrics.marketsStressRuns += 1;

    const marketsActive = await marketsTab.evaluate((el) => el.className.includes("bg-[#101114]"));
    const analyzerActive = analyzerTab
      ? await analyzerTab.evaluate((el) => el.className.includes("bg-[#101114]"))
      : false;
    if (!marketsActive || analyzerActive) {
      summary.metrics.marketsUnexpectedAnalyze += 1;
      pushIssue({
        kind: "ux",
        viewport: viewportName,
        text: `Markets stress iteration ${i + 1}: unexpected tab state (marketsActive=${marketsActive}, analyzerActive=${analyzerActive})`,
      });
    }
    await page.waitForTimeout(150);
  }
  pushEvent(`[${viewportName}] Markets stress completed (${MARKETS_STRESS_COUNT}x)`);
}

async function runTickerChecks(page, viewportName) {
  const analyzerTab = await findTabButton(page, [/^Analyzer$/i, /^Analyze$/i]);
  if (analyzerTab) {
    await analyzerTab.click();
    await page.waitForTimeout(1000);
  }

  const searchInput = page.locator('input[aria-label="Search for a stock, ETF, or crypto ticker"]').first();
  if (!(await searchInput.count())) {
    pushIssue({ kind: "ui", viewport: viewportName, text: "Analyzer search input not found" });
    return;
  }

  const waitSearchReady = async (ticker) => {
    const started = Date.now();
    while (Date.now() - started < 35000) {
      const exists = await searchInput.count();
      if (!exists) {
        await page.waitForTimeout(250);
        continue;
      }
      const disabled = await searchInput.isDisabled();
      if (!disabled) return true;
      await page.waitForTimeout(250);
    }
    pushIssue({
      kind: "ui",
      viewport: viewportName,
      text: `Search input remained disabled before ${ticker}`,
    });
    return false;
  };

  const hasVisibleChartLoading = async () => {
    const loadingTexts = page.getByText(/Lade Kursverlauf|Chart-Layout wird vorbereitet/i);
    const count = await loadingTexts.count();
    for (let i = 0; i < count; i += 1) {
      if (await loadingTexts.nth(i).isVisible()) return true;
    }
    return false;
  };

  for (const ticker of TICKERS) {
    const ready = await waitSearchReady(ticker);
    if (!ready) continue;
    await searchInput.fill(ticker);
    await page.keyboard.press("Enter");
    await page.waitForTimeout(5200);
    summary.metrics.tickerRuns += 1;

    let loadingChartVisible = await hasVisibleChartLoading();
    if (loadingChartVisible) {
      // one extra grace window to avoid false positives from transient redraws
      await page.waitForTimeout(3000);
      loadingChartVisible = await hasVisibleChartLoading();
    }
    if (loadingChartVisible) {
      summary.metrics.chartStillLoading += 1;
      pushIssue({
        kind: "ui",
        viewport: viewportName,
        text: `Chart still loading after wait window for ${ticker}`,
      });
    }

    await page.screenshot({
      path: path.join(runDir, `${viewportName}-analyzer-${ticker}.png`),
      fullPage: true,
    });
    pushEvent(`[${viewportName}] Analyzer ticker checked: ${ticker}`);
  }
}

async function runViewportScenario(browser, viewport) {
  const viewportName = viewport.name;
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
  });
  const page = await context.newPage();
  attachPageObservers(page, viewportName);

  const local = {
    blankRoot: false,
    issuesBefore: summary.issues.length,
  };

  try {
    await page.goto(TARGET_URL, { waitUntil: "domcontentloaded", timeout: 45000 });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(runDir, `${viewportName}-landing.png`), fullPage: true });

    const hasBlankRoot = await page.evaluate(() => {
      const root = document.getElementById("root");
      if (!root) return true;
      const text = (root.textContent || "").trim();
      const rect = root.getBoundingClientRect();
      return text.length === 0 && rect.height < 20;
    });
    if (hasBlankRoot) {
      local.blankRoot = true;
      pushIssue({ kind: "ui", viewport: viewportName, text: "Root appears blank on initial load" });
    }

    await ensureLoggedIn(page, viewportName);
    await page.waitForTimeout(1600);
    const navReady = await waitForNavigationShell(page, 14000);
    if (!navReady) {
      pushIssue({ kind: "ui", viewport: viewportName, text: "Navigation shell did not appear after login window" });
      return;
    }

    const navTargets = [
      { name: "Analyzer", file: `${viewportName}-tab-analyzer.png` },
      { name: "Markets", file: `${viewportName}-tab-markets.png` },
      { name: "Portfolio", file: `${viewportName}-tab-portfolio.png` },
      { name: "Dashboard", file: `${viewportName}-tab-dashboard.png` },
    ];
    for (const target of navTargets) {
      const patterns = target.name === "Analyzer"
        ? [/^Analyzer$/i, /^Analyze$/i]
        : target.name === "Dashboard"
          ? [/^Dashboard$/i, /^Home$/i]
          : [new RegExp(`^${target.name}$`, "i")];
      const tab = await findTabButton(page, patterns);
      if (tab) {
        await tab.click();
        await page.waitForTimeout(1200);
        await page.screenshot({ path: path.join(runDir, target.file), fullPage: true });
      } else {
        pushIssue({ kind: "ui", viewport: viewportName, text: `Tab not found: ${target.name}` });
      }
    }

    await runMarketsStress(page, viewportName);
    await runTickerChecks(page, viewportName);
  } finally {
    summary.perViewport[viewportName] = {
      blankRoot: local.blankRoot,
      issuesAdded: summary.issues.length - local.issuesBefore,
    };
    await context.close();
  }
}

const browser = await chromium.launch({ headless: true });
try {
  for (const viewport of VIEWPORTS) {
    await runViewportScenario(browser, viewport);
  }
} finally {
  await browser.close();
  fs.writeFileSync(path.join(runDir, "summary.json"), JSON.stringify(summary, null, 2), "utf-8");
}
