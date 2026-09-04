import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { chromium } from "playwright";
import { createServer } from "vite";
import tailwindcss from "@tailwindcss/vite";

// Exercise the actual App header markup without login, portfolio or provider calls.
const app = await readFile("src/App.tsx", "utf8");
const start = app.indexOf("  const moversTape =");
const end = app.indexOf("  const mobileMarketTape =", start);
assert.ok(start >= 0 && end > start);
const helpersStart = app.indexOf("interface TapeMover {");
const helpersEnd = app.indexOf("interface AuthState {", helpersStart);
assert.ok(helpersStart >= 0 && helpersEnd > helpersStart);
const fixture = `
  import React, { useState } from "react";
  import { createRoot } from "react-dom/client";
  import { ArrowUpRight, ArrowDownRight } from "lucide-react";
  import "/src/index.css";
  import useMarketMovers from "/src/hooks/useMarketMovers";
  type MoversWindow = "1d" | "1w" | "1m";
  ${app.slice(helpersStart, helpersEnd)}
  function Fixture() {
    const [marketMoversWindow, setMarketMoversWindow] = useState<MoversWindow>("1w");
    const { items: tapeMovers, status: marketMoversStatus, retry: retryMarketMovers } = useMarketMovers(marketMoversWindow, true, marketMoversToTape);
    const formatPrice = value => new Intl.NumberFormat("de-DE", { style: "currency", currency: "USD" }).format(value);
    ${app.slice(start, end)}
    return innerWidth < 1024
      ? <div className="mobile-market-tape"><div><div className="mt-2">{moversTape}</div></div></div>
      : <div className="desktop-movers-tape">{moversTape}</div>;
  }
  createRoot(document.getElementById("root")).render(<Fixture />);
`;
const server = await createServer({
  configFile: false, logLevel: "error", esbuild: { jsx: "automatic" },
  plugins: [tailwindcss(), {
    name: "market-tape-fixture",
    resolveId(id) { if (id === "/@market-tape.tsx") return id; },
    load(id) { if (id === "/@market-tape.tsx") return fixture; },
  }],
  server: { host: "127.0.0.1", port: 0 },
});
let browser;
try {
  await server.listen();
  const base = `http://127.0.0.1:${server.httpServer.address().port}`;
  browser = await chromium.launch({ channel: "chrome", headless: true });
  for (const width of [320, 390, 768, 1280, 1440]) {
    const context = await browser.newContext({ viewport: { width, height: 900 }, hasTouch: width < 1024, reducedMotion: "reduce" });
    const page = await context.newPage();
    await page.clock.install();
    const errors = [];
    let scenario = "ready";
    const delayed = [];
    let notifyDelayed;
    const delayedStarted = new Promise(resolve => { notifyDelayed = resolve; });
    page.on("pageerror", error => errors.push(error.message));
    await page.route(`${base}/api/discovery/**`, async route => {
      const url = new URL(route.request().url());
      const period = url.searchParams.get("window");
      const loser = url.pathname.endsWith("losers");
      const body = JSON.stringify(Array.from({ length: 6 }, (_, i) => ({
        ticker: `${period.toUpperCase()}${loser ? "L" : "G"}${i}`, change: loser ? -3.14 : 5.67, price: 123.45,
      })));
      if (scenario === "slow" && period === "1d") {
        delayed.push(() => route.fulfill({ contentType: "application/json", body }).catch(() => {}));
        if (delayed.length === 2) notifyDelayed();
        return;
      }
      if (scenario === "error") return route.fulfill({ status: 503, body: "Unavailable" });
      if (scenario === "malformed" && loser) return route.fulfill({ json: { error: "Invalid payload" } });
      return route.fulfill({ contentType: "application/json", body: scenario === "empty" ? "[]" : body });
    });
    await page.route(`${base}/test`, route => route.fulfill({ contentType: "text/html", body: '<!doctype html><html data-theme="dark"><meta name="viewport" content="width=device-width, initial-scale=1"><div id="root" style="padding:12px"></div><script type="module" src="/@market-tape.tsx"></script></html>' }));
    await page.goto(`${base}/test`);
    const controls = page.getByRole("group", { name: "Zeitraum der Marktbewegungen" });
    await controls.waitFor({ timeout: 5000 });
    const scroll = page.getByRole("region", { name: "Gewinner und Verlierer" });
    const settled = () => page.waitForFunction(() => document.querySelector('.header-movers-scroll')?.getAttribute('aria-busy') === 'false');
    await settled();
    for (const [title, period] of [["1 Tag", "1D"], ["1 Woche", "1W"], ["1 Monat", "1M"]]) {
      const button = controls.getByRole("button", { name: `${title}: Marktbewegungen anzeigen` });
      await button.click();
      await settled();
      assert.ok((await scroll.innerText()).includes(`${period}G0`));
      for (const other of ["1D", "1W", "1M"].filter(value => value !== period)) assert.ok(!(await scroll.innerText()).includes(`${other}G0`));
      assert.equal(await button.getAttribute("aria-pressed"), "true");
      const box = await button.boundingBox();
      assert.ok(box.height >= (width < 640 ? 40 : 32));
      assert.ok(box.x >= 0 && box.x + box.width <= width);
    }
    const before = await controls.boundingBox();
    const title = await page.getByText("Marktbewegungen", { exact: true }).boundingBox();
    assert.ok(title.x + title.width + 4 <= before.x, "Heading and period controls must not overlap");
    const tapeBounds = await page.locator('.header-movers-tape').boundingBox();
    const clipBounds = await page.locator('.header-movers-tape').evaluate(el => {
      const parent = el.parentElement.getBoundingClientRect(); return { bottom: parent.bottom };
    });
    assert.ok(tapeBounds.y + tapeBounds.height <= clipBounds.bottom + 1, "Mobile wrapper must not clip the market tape");
    await scroll.evaluate(el => { el.scrollLeft = el.scrollWidth; });
    assert.ok(await scroll.evaluate(el => el.scrollLeft > 0));
    const after = await controls.boundingBox();
    assert.equal(after.x, before.x, "Scrolling quotes must not move the period controls");
    assert.equal(await page.locator('.ticker-marquee-duplicate:visible').count(), 0);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    for (const theme of ["dark", "light"]) {
      await page.evaluate(theme => { document.documentElement.dataset.theme = theme; }, theme);
      await page.screenshot({ path: path.join(tmpdir(), `broker-market-tape-${width}-${theme}.png`) });
    }
    scenario = "slow";
    await controls.getByRole("button", { name: "1 Tag: Marktbewegungen anzeigen" }).click();
    await page.waitForFunction(() => document.querySelector('.header-movers-scroll')?.getAttribute('aria-busy') === 'true');
    assert.ok(!(await scroll.innerText()).includes("1MG0"), "Pending period must hide previous prices");
    await delayedStarted;
    assert.equal(delayed.length, 2);
    await controls.getByRole("button", { name: "1 Monat: Marktbewegungen anzeigen" }).click();
    await settled();
    await Promise.all(delayed.map(release => release()));
    assert.ok((await scroll.innerText()).includes("1MG0"));
    assert.ok(!(await scroll.innerText()).includes("1DG0"));
    for (const failure of ["error", "malformed", "empty"]) {
      scenario = failure;
      await controls.getByRole("button", { name: "1 Tag: Marktbewegungen anzeigen" }).click();
      await settled();
      assert.ok(!(await scroll.innerText()).includes("G0"), "Failure must not display previous or partial results");
      assert.equal(await controls.getByRole("button").count(), 3);
      assert.ok((await scroll.getByRole("status").innerText()).includes(failure === "empty" ? "Keine Marktbewegungen" : "nicht geladen"));
      scenario = "ready";
      await page.getByRole("button", { name: "Marktbewegungen erneut laden" }).click();
      await settled();
      assert.ok((await scroll.innerText()).includes("1DG0"));
      await controls.getByRole("button", { name: "1 Monat: Marktbewegungen anzeigen" }).click();
      await settled();
    }
    scenario = "error";
    await page.clock.fastForward(60000);
    await settled();
    assert.ok((await scroll.innerText()).includes("1MG0"));
    assert.ok((await scroll.getByRole("status").innerText()).includes("Gespeicherte Werte dieses Zeitraums"));
    await page.screenshot({ path: path.join(tmpdir(), `broker-market-tape-${width}-stale.png`) });
    assert.deepEqual(errors, []);
    console.log(`market tape passed: ${width}px, period data, races, failure/empty/retry/stale, independent scrolling, light/dark`);
    await context.close();
  }
} finally {
  await browser?.close();
  await server.close();
}
