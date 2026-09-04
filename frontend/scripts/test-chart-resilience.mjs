import assert from "node:assert/strict";
import { chromium } from "playwright";
import { createServer } from "vite";
import tailwindcss from "@tailwindcss/vite";
import { tmpdir } from "node:os";
import path from "node:path";

// Real chart component, isolated test browser, deterministic provider responses.
// No login, user portfolio, external API or running application server is used.
const fixture = `
  import React from "react";
  import { createRoot } from "react-dom/client";
  import PriceChart from "/src/components/PriceChart.tsx";
  import { CurrencyProvider } from "/src/context/CurrencyContext.tsx";
  import "/src/index.css";
  createRoot(document.getElementById("root")).render(
    React.createElement(CurrencyProvider, null, React.createElement(PriceChart, {
      ticker:"TEST",
      onStatsUpdate: (stats, period) => { document.documentElement.dataset.chartStats = JSON.stringify({ ...stats, period }); }
    }))
  );
`;
const server = await createServer({
  configFile: false,
  logLevel: "error",
  esbuild: { jsx: "automatic" },
  plugins: [tailwindcss(), {
    name: "isolated-chart-fixture",
    resolveId(id) { if (id === "/@chart-fixture") return id; },
    load(id) { if (id === "/@chart-fixture") return fixture; },
  }],
  optimizeDeps: { include: ["react", "react-dom/client", "recharts", "lucide-react"] },
  server: { host: "127.0.0.1", port: 0 },
});
let browser;
try {
  await server.listen();
  const base = `http://127.0.0.1:${server.httpServer.address().port}`;
  browser = await chromium.launch({ headless: true, channel: process.env.QA_BROWSER_CHANNEL || "chrome" });
  for (const width of [320, 390, 768, 1440]) {
    const context = await browser.newContext({ viewport: { width, height: 900 }, hasTouch: width < 600, isMobile: width < 600, serviceWorkers: "block" });
    await context.addInitScript(() => localStorage.setItem("brokerfreund:ws-unavailable-until", String(Date.now() + 3600000)));
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    let mode = "live";
    const liveQuotePrice = width < 600 ? 205 : 80;
    const requests = [];
    await page.route("**/api/**", async route => {
      const url = new URL(route.request().url());
      if (!url.pathname.startsWith("/api/history/")) {
        await route.fulfill({ json: { quotes: [{ symbol: "TEST", price: liveQuotePrice }], connection_state: "snapshot" } });
        return;
      }
      const period = url.searchParams.get("period");
      const interval = url.searchParams.get("interval");
      requests.push({ period, interval });
      const responseMode = mode;
      if (responseMode === "slow") await new Promise(resolve => setTimeout(resolve, 1200));
      await route.fulfill({ json: {
        items: responseMode === "invalid" ? [
          { time: "2026-08-25", price: null }, { time: "2026-08-31", price: "" },
        ] : responseMode === "unavailable" ? [] : [
          ...(responseMode === "partial" ? [null, "", false, [], {}].map(price => ({ time: "2026-08-24", price })) : []),
          { time: period === "5d" ? "14:00" : "2026-08-25", full_date: "2026-08-25T14:00:00Z", price: 100, volume: 1000 },
          { time: period === "5d" ? "14:00" : "2026-08-31", full_date: "2026-08-31T14:00:00Z", price: responseMode === "declining" ? 95 : 105, volume: 1200 },
        ],
        meta: {
          mode: responseMode === "mismatch" ? "fallback" : ["slow", "declining", "partial", "invalid"].includes(responseMode) ? "live" : responseMode,
          stale: responseMode === "stale", source: "qa_fixture", points: responseMode === "unavailable" ? 0 : 2,
          period: responseMode === "mismatch" ? "1mo" : period, interval,
          fallback_reason: responseMode === "unavailable" ? "no_history_available" : undefined,
        },
      }});
    });
    await page.route(`${base}/__chart-test`, route => route.fulfill({
      contentType: "text/html",
      body: '<!doctype html><html lang="de" data-theme="dark"><meta name="viewport" content="width=device-width, initial-scale=1"><div id="root" style="padding:12px"></div><script type="module" src="/@chart-fixture"></script></html>',
    }));
    await page.goto(`${base}/__chart-test`);
    await page.getByText("Historie geladen", { exact: true }).waitFor({ timeout: 30000 });
    for (const viewportWidth of [320, 390, 768, 1024, 1440]) {
      await page.setViewportSize({ width: viewportWidth, height: 900 });
      const selector = page.getByRole("group", { name: "Zeitraum für den Kursverlauf" });
      const bounds = await selector.boundingBox();
      assert.ok(await selector.evaluate(el => el.scrollWidth <= el.clientWidth + 1), `All six periods must fit without hidden horizontal scrolling at ${viewportWidth}px`);
      for (const button of await selector.getByRole("button").all()) {
        const box = await button.boundingBox();
        assert.ok(box.width >= 40 && box.height >= 40, "Period buttons need a stable touch target");
        assert.ok(box.x >= bounds.x && box.x + box.width <= bounds.x + bounds.width + 1, "Every period must be fully visible");
        if (viewportWidth === 320) {
          const response = page.waitForResponse(r => r.url().includes("/api/history/"));
          await button.click();
          await response;
          await page.getByText("Historie geladen", { exact: true }).waitFor();
          assert.equal(await button.getAttribute("aria-pressed"), "true");
        }
      }
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      if (viewportWidth === 320) {
        await page.evaluate(() => scrollTo(0, 0));
        await page.screenshot({ path: path.join(tmpdir(), `broker-chart-periods-320-${width}.png`) });
      }
    }
    await page.setViewportSize({ width, height: 900 });
    assert.equal(await page.getByText("Live", { exact: true }).count(), 0, "A successful snapshot request is not a live stream");
    await page.getByText("Snapshot", { exact: true }).waitFor();
    assert.equal(await page.getByText("Live-Feed", { exact: true }).count(), 0);
    assert.equal(await page.getByText("Quelle: qa_fixture", { exact: true }).count(), 1);
    for (const title of ["1 Tag", "5 Tage", "1 Monat", "1 Jahr", "5 Jahre", "Gesamter Zeitraum"]) {
      const button = page.getByRole("button", { name: `${title} im Kursverlauf anzeigen`, exact: true });
      const response = page.waitForResponse(r => r.url().includes("/api/history/"));
      await button.click();
      await response;
      await page.getByText("Historie geladen", { exact: true }).waitFor();
      assert.equal(await button.getAttribute("aria-pressed"), "true");
      const intervalLabels = { "1 Tag": "5-Minuten-Kurse", "5 Tage": "15-Minuten-Kurse", "1 Monat": "Tageskurse", "1 Jahr": "Wochenkurse", "5 Jahre": "Monatskurse", "Gesamter Zeitraum": "Monatskurse" };
      assert.equal(await page.getByText(intervalLabels[title], { exact: true }).count(), 1);
      const expectedChange = 5;
      await page.getByText(`${expectedChange >= 0 ? "+" : ""}${expectedChange.toFixed(2)}%`, { exact: true }).waitFor({ timeout: 3000 });
      const reportedStats = await page.evaluate(() => JSON.parse(document.documentElement.dataset.chartStats));
      assert.equal(reportedStats.change, expectedChange);
      assert.ok(Math.abs(reportedStats.changePct - expectedChange) < 1e-9);
      assert.match(await page.getByRole("slider").getAttribute("aria-valuetext"), /31\.08\.2026.*105,00/, "A feed quote must not overwrite the historical point's price under its old date");
      assert.match(await page.getByRole("group", { name: "Separater Feed-Kurs" }).innerText(), new RegExp(`${liveQuotePrice},00`));
      await page.waitForFunction(expected => document.querySelector('.recharts-area-curve')?.getAttribute('stroke') === expected, expectedChange >= 0 ? "var(--chart-up)" : "var(--chart-down)");
    }
    mode = "stale";
    await page.getByRole("button", { name: "5 Tage im Kursverlauf anzeigen", exact: true }).click();
    await page.getByText("gespeicherte Historie", { exact: true }).waitFor();
    await page.getByText("+5.00%", { exact: true }).waitFor();
    const cachedStats = await page.evaluate(() => JSON.parse(document.documentElement.dataset.chartStats));
    assert.equal(cachedStats.change, 5);
    assert.ok(Math.abs(cachedStats.changePct - 5) < 1e-9, "Cached performance must not use the live quote");
    const slider = page.getByRole("slider");
    const marker = page.locator(".recharts-reference-line-line").first();
    await slider.press("Home");
    await page.waitForFunction(() => document.querySelector('input[type="range"]')?.value === "0");
    assert.match(await slider.getAttribute("aria-valuetext"), /25\.08\.2026.*100,00/);
    await marker.waitFor({ state: "attached" });
    const startX = Number(await marker.getAttribute("x1"));
    await slider.press("End");
    await page.waitForFunction(() => document.querySelector('input[type="range"]')?.value === "1");
    assert.match(await slider.getAttribute("aria-valuetext"), /31\.08\.2026.*105,00/);
    assert.ok(Number(await marker.getAttribute("x1")) > startX + 20, "Same clock time on different days must produce distinct marker positions");
    await page.waitForFunction(() => [...document.querySelectorAll('.recharts-xAxis-tick-labels text')].some(node => node.textContent?.includes('25.08')));
    const axisText = (await page.locator(".recharts-xAxis-tick-labels text").allTextContents()).join(" ");
    assert.match(axisText, /25\.08/);
    assert.match(axisText, /31\.08/);
    for (const title of ["5 Tage", "1 Tag", "1 Monat", "1 Jahr", "5 Jahre", "Gesamter Zeitraum"]) {
      if (title !== "5 Tage") {
        await page.getByRole("button", { name: `${title} im Kursverlauf anzeigen`, exact: true }).click();
        await page.getByText("gespeicherte Historie", { exact: true }).waitFor();
        await slider.press("End");
      }
      const chart = page.locator(".recharts-wrapper").first();
      await chart.scrollIntoViewIfNeeded();
      const plot = await marker.evaluate(line => {
        const matrix = line.getScreenCTM();
        const point = new DOMPoint(Number(line.getAttribute("x1")), (Number(line.getAttribute("y1")) + Number(line.getAttribute("y2"))) / 2).matrixTransform(matrix);
        return { right: point.x, y: point.y, scale: matrix.a };
      });
      const left = plot.right - (Number(await marker.getAttribute("x1")) - startX) * plot.scale;
      for (const [x, index, price] of [[left + 4, "0", /100,00/], [plot.right - 4, "1", /105,00/]]) {
        if (width < 600) await page.touchscreen.tap(x, plot.y);
        else await page.mouse.move(x, plot.y);
        await page.waitForFunction(expected => document.querySelector('input[type="range"]')?.value === expected, index);
        assert.match(await slider.getAttribute("aria-valuetext"), price);
        const tooltip = page.locator(".recharts-tooltip-wrapper").first();
        await tooltip.waitFor({ state: "visible" });
        assert.match(await tooltip.innerText(), price);
        assert.match(await tooltip.innerText(), index === "0" ? /25\.08\.2026/ : /31\.08\.2026/);
      }
      if (title === "5 Tage") await page.screenshot({ path: path.join(tmpdir(), `broker-chart-input-${width}.png`) });
      const tooltip = page.locator(".recharts-tooltip-wrapper").first();
      for (const [selectEarlier, selectLater] of [
        [() => page.getByRole("button", { name: "Einen Kurspunkt früher", exact: true }).click(),
          () => page.getByRole("button", { name: "Einen Kurspunkt später", exact: true }).click()],
        [() => slider.press("Home"), () => slider.press("End")],
        [() => page.getByRole("button", { name: "Zum ersten historischen Kurspunkt springen", exact: true }).click(),
          () => page.getByRole("button", { name: "Zum neuesten Kurspunkt springen", exact: true }).click()],
      ]) {
        if (width >= 600) await page.mouse.move(2, 2);
        await chart.scrollIntoViewIfNeeded();
        const lastPoint = await marker.evaluate(line => {
          const point = new DOMPoint(Number(line.getAttribute("x1")), (Number(line.getAttribute("y1")) + Number(line.getAttribute("y2"))) / 2).matrixTransform(line.getScreenCTM());
          return { x: point.x - 4, y: point.y };
        });
        if (width < 600) await page.touchscreen.tap(lastPoint.x, lastPoint.y);
        else await page.mouse.move(lastPoint.x, lastPoint.y);
        await tooltip.waitFor({ state: "visible" });
        assert.match(await tooltip.innerText(), /31\.08\.2026[\s\S]*105,00/);
        await selectEarlier();
        assert.match(await slider.getAttribute("aria-valuetext"), /25\.08\.2026.*100,00/);
        assert.equal(Number(await marker.getAttribute("x1")), startX);
        await tooltip.waitFor({ state: "hidden", timeout: 3000 });
        await selectLater();
        assert.match(await slider.getAttribute("aria-valuetext"), /31\.08\.2026.*105,00/);
        assert.ok(Number(await marker.getAttribute("x1")) > startX + 20);
      }
      if (width >= 600) {
        await page.mouse.move(2, 2);
        assert.match(await slider.getAttribute("aria-valuetext"), /31\.08\.2026.*105,00/);
      }
    }
    const requestsBeforeLayoutChanges = requests.length;
    await slider.press("Home");
    for (const viewport of [{ width: 900, height: 390 }, { width: 320, height: 740 }, { width, height: 900 }]) {
      await page.setViewportSize(viewport);
      await page.waitForFunction(() => {
        const chart = document.querySelector('.recharts-wrapper');
        const bounds = chart?.getBoundingClientRect();
        return bounds && bounds.width > innerWidth * 0.7 && bounds.right <= innerWidth;
      });
      assert.match(await slider.getAttribute("aria-valuetext"), /25\.08\.2026.*100,00/);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    }
    // Simulate a retained tab/panel temporarily hidden by its parent.
    for (let cycle = 0; cycle < 3; cycle += 1) {
      await page.locator("#root").evaluate(root => { root.style.display = "none"; });
      await page.locator(".recharts-wrapper").first().waitFor({ state: "detached" });
      await page.locator("#root").evaluate(root => { root.style.removeProperty("display"); });
      await page.locator(".recharts-wrapper").first().waitFor({ state: "visible", timeout: 3000 });
    }
    assert.match(await slider.getAttribute("aria-valuetext"), /25\.08\.2026.*100,00/);
    assert.equal(requests.length, requestsBeforeLayoutChanges, "Layout changes must not reload history");
    mode = "declining";
    await page.getByRole("button", { name: "5 Jahre im Kursverlauf anzeigen", exact: true }).click();
    await page.getByText("-5.00%", { exact: true }).waitFor();
    assert.match(await slider.getAttribute("aria-valuetext"), /31\.08\.2026.*95,00/);
    const decliningStats = await page.evaluate(() => JSON.parse(document.documentElement.dataset.chartStats));
    assert.equal(decliningStats.change, -5);
    assert.ok(Math.abs(decliningStats.changePct + 5) < 1e-9);
    await page.waitForFunction(() => document.querySelector('.recharts-area-curve')?.getAttribute('stroke') === "var(--chart-down)");
    mode = "slow";
    const periodControls = page.getByRole("group", { name: "Zeitraum für den Kursverlauf" });
    const periodWidths = await periodControls.getByRole("button").evaluateAll(buttons => buttons.map(button => button.getBoundingClientRect().width));
    const slowRequest = page.waitForRequest(r => r.url().includes("period=1y"));
    await page.getByRole("button", { name: "1 Jahr im Kursverlauf anzeigen", exact: true }).click();
    await slowRequest;
    await page.getByText("Lade Kursverlauf...", { exact: true }).waitFor({ state: "visible" });
    assert.deepEqual(await periodControls.getByRole("button").evaluateAll(buttons => buttons.map(button => button.getBoundingClientRect().width)), periodWidths, "Loading indicator must not change period button widths");
    assert.equal(await page.locator(".recharts-area").count(), 0);
    mode = "live";
    await page.getByRole("button", { name: "Gesamter Zeitraum im Kursverlauf anzeigen", exact: true }).click();
    await page.getByText("Historie geladen", { exact: true }).waitFor();
    await page.waitForTimeout(1400);
    assert.equal(await page.getByRole("button", { name: "Gesamter Zeitraum im Kursverlauf anzeigen", exact: true }).getAttribute("aria-pressed"), "true");
    assert.equal(await page.getByText(/Historie: qa_fixture \/ max\/1mo/).count(), 1);
    mode = "partial";
    await page.getByRole("button", { name: "5 Tage im Kursverlauf anzeigen", exact: true }).click();
    await page.getByText("Historie geladen", { exact: true }).waitFor();
    assert.equal(await slider.getAttribute("max"), "1", "Only the two valid prices are selectable");
    await page.getByText("+5.00%", { exact: true }).waitFor();
    assert.equal(await page.getByText(/5 ungültige Kurspunkte ausgelassen/).count(), 1);
    assert.equal(await page.getByText(/Historie: qa_fixture \/ 5d\/15m \/ 2 Punkte/).count(), 1);
    for (const fault of ["unavailable", "mismatch", "snapshot", "invalid"]) {
      mode = fault;
      const count = requests.length;
      await page.getByRole("button", { name: "5 Tage im Kursverlauf anzeigen", exact: true }).click();
      await page.getByText("Kursdaten konnten nicht geladen werden.", { exact: true }).waitFor();
      assert.equal(await page.locator(".recharts-area").count(), 0, "No made-up chart during outage");
      assert.equal(await page.getByRole("slider").isEnabled(), false);
      assert.deepEqual(requests.slice(count), [{ period: "5d", interval: "15m" }], "No silent range fallback");
    }
    mode = "stale";
    await page.getByRole("button", { name: "Erneut laden", exact: true }).click();
    await page.getByText("gespeicherte Historie", { exact: true }).waitFor();
    assert.equal(await page.getByRole("slider").isEnabled(), true);
    assert.match(await page.getByRole("slider").getAttribute("aria-valuetext"), /105,00/, "Cached history must not be overwritten by today's live quote");
    mode = "live";
    await page.getByRole("button", { name: "5 Tage im Kursverlauf anzeigen", exact: true }).click();
    await page.getByText("Historie geladen", { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    const contrastAgainstSurface = async (selector, property = "color") => page.locator(selector).first().evaluate((node, property) => {
      // Canvas normalizes modern CSS colors (oklab/color-mix included) to sRGB.
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 1;
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      const rgba = value => {
        ctx.clearRect(0, 0, 1, 1);
        ctx.fillStyle = value;
        ctx.fillRect(0, 0, 1, 1);
        const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
        return [r, g, b, a / 255];
      };
      const over = (fg, bg) => fg.slice(0, 3).map((v, i) => v * (fg[3] ?? 1) + bg[i] * (1 - (fg[3] ?? 1)));
      const ancestors = [];
      for (let el = node; el; el = el.parentElement) ancestors.unshift(el);
      let background = [255, 255, 255];
      for (const el of ancestors) background = over(rgba(getComputedStyle(el).backgroundColor), background);
      const foreground = over(rgba(getComputedStyle(node)[property]), background);
      const luminance = rgb => rgb.map(v => v / 255).map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4).reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
      const a = luminance(foreground), b = luminance(background);
      return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    }, property);
    for (const theme of ["dark", "light"]) {
      await page.evaluate(theme => { document.documentElement.dataset.theme = theme; }, theme);
      // Allow theme styles and any active color transitions to settle.
      await page.waitForTimeout(250);
      await page.locator(".recharts-area-curve").first().waitFor({ state: "visible" });
      const lineContrast = await contrastAgainstSurface(".recharts-area-curve", "stroke");
      assert.ok(lineContrast >= 3, `${theme}: price line contrast ${lineContrast.toFixed(2)}; stroke ${await page.locator('.recharts-area-curve').first().evaluate(node => getComputedStyle(node).stroke)}`);
      const axisContrast = await contrastAgainstSurface(".recharts-xAxis-tick-labels text", "fill");
      assert.ok(axisContrast >= 4.5, `${theme}: axis text contrast ${axisContrast.toFixed(2)}`);
      for (const pressed of ["true", "false"]) {
        const ratio = await contrastAgainstSurface(`.chart-period-selector button[aria-pressed="${pressed}"]`);
        assert.ok(ratio >= 4.5, `${theme}: period button (selected=${pressed}) contrast ${ratio.toFixed(2)}`);
      }
      for (const label of ["RSI", "MACD", "SMA", "Bollinger", "Volume", "VWAP"]) {
        const toggle = page.getByRole("button", { name: new RegExp(`^${label}:`) });
        if (await toggle.getAttribute("aria-pressed") !== "true") await toggle.click();
        // Let the color transition finish before checking its rendered value.
        await page.waitForTimeout(200);
        const ratio = await contrastAgainstSurface(`button[aria-label^="${label}:"]`);
        assert.ok(ratio >= 4.5, `${theme}: ${label} contrast ${ratio.toFixed(2)}`);
      }
      await page.mouse.move(2, 2);
      if (width < 600) {
        const help = page.locator("details.indicator-mobile-help").first();
        assert.match(await help.locator("summary").innerText(), /6/);
        await help.locator("summary").click();
        assert.equal(await help.locator(".indicator-help-card:visible").count(), 6);
        assert.deepEqual(await help.locator(".indicator-help-label").allTextContents().then(labels => labels.map(label => label.trim())), ["RSI", "MACD", "SMA", "Bollinger", "Volume", "VWAP"]);
        await page.getByRole("button", { name: /^VWAP:/ }).click();
        assert.match(await help.locator("summary").innerText(), /5/);
        assert.equal(await help.locator(".indicator-help-card:visible").count(), 5);
        await page.getByRole("button", { name: /^VWAP:/ }).click();
        await help.locator("summary").click();
        assert.equal(await page.locator(".indicator-hover-help:visible").count(), 0);
      } else {
        const extraHelp = page.locator("details.indicator-extra-help");
        await extraHelp.locator("summary").click();
        assert.equal(await extraHelp.locator(".indicator-help-card:visible").count(), 3);
        assert.deepEqual(await extraHelp.locator(".indicator-help-label").allTextContents(), ["Bollinger", "Volume", "VWAP"]);
        await extraHelp.locator("summary").click();
        for (const label of ["RSI", "VWAP"]) {
          const toggle = page.getByRole("button", { name: new RegExp(`^${label}:`) });
          await toggle.hover();
          const bubble = toggle.locator(".indicator-hover-help");
          await bubble.waitFor({ state: "visible" });
          const bounds = await bubble.boundingBox();
          assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= width, "Indicator hint stays inside the viewport");
        }
      }
      await page.mouse.move(2, 2);
      await page.locator(".price-chart").scrollIntoViewIfNeeded();
      await page.evaluate(() => scrollTo(0, 0));
      await page.screenshot({ path: path.join(tmpdir(), `broker-chart-contrast-${theme}-${width}.png`) });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    }
    assert.deepEqual(errors, []);
    console.log(`chart resilience passed: ${width}px, light/dark contrast, ${width < 600 ? "touch" : "mouse"} selection and tooltip, control handoff and reopening, resize/rotation and panel restoration without refetch, six periods, distinct same-time markers, dated 5-day axis, empty/mismatched/snapshot rejection, stale history and retry`);
    await context.close();
  }
} finally {
  await browser?.close();
  await server.close();
}
