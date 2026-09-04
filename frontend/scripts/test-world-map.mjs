import assert from "node:assert/strict";
import { chromium } from "playwright";
import { createServer } from "vite";
import tailwindcss from "@tailwindcss/vite";
import { tmpdir } from "node:os";
import path from "node:path";

const fixture = `
  import React, { useState } from "react";
  import { createRoot } from "react-dom/client";
  import WorldMarketMap from "/src/components/WorldMarketMap.tsx";
  import "/src/index.css";
  const regions = [
    { label: "Asia", tone: "risk-on", avg_change_1d: 0.82, assets: [{ ticker: "^N225", label: "Nikkei 225", change_1d: 0.82 }] },
    { label: "Europe", tone: "mixed", avg_change_1d: 0.12, assets: [{ ticker: "^GDAXI", label: "DAX", change_1d: 0.12 }] },
    { label: "USA", tone: "risk-off", avg_change_1d: -0.31, assets: [{ ticker: "SPY", label: "S&P 500", change_1d: -0.31 }] },
  ];
  const news = [{ title: "Tokyo market event", region: "Asia", impact: "high", event_type: "central_bank", geo: { lat: 35.68, lon: 139.69, place: "Tokio", country: "Japan" } }];
  function Fixture() {
    const [selected, setSelected] = useState("Europe");
    return <WorldMarketMap regions={regions} selectedRegion={selected} onSelectRegion={setSelected} news={news} eventLayer={news} onAnalyze={() => {}} />;
  }
  createRoot(document.getElementById("root")).render(<Fixture />);
`;

const server = await createServer({
  configFile: false, logLevel: "error", esbuild: { jsx: "automatic" },
  plugins: [tailwindcss(), {
    name: "world-map-fixture",
    resolveId(id) { if (id === "/@world-map.tsx") return id; },
    load(id) { if (id === "/@world-map.tsx") return fixture; },
  }],
  server: { host: "127.0.0.1", port: 0 },
});

let browser;
try {
  await server.listen();
  const base = `http://127.0.0.1:${server.httpServer.address().port}`;
  browser = await chromium.launch({ channel: "chrome", headless: true });
  for (const width of [320, 390, 768, 1440]) {
    const context = await browser.newContext({ viewport: { width, height: 900 }, hasTouch: width < 600, reducedMotion: "reduce" });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.route(`${base}/map-test`, route => route.fulfill({ contentType: "text/html", body: '<!doctype html><html lang="de" data-theme="dark"><meta name="viewport" content="width=device-width, initial-scale=1"><div id="root" style="padding:12px"></div><script type="module" src="/@world-map.tsx"></script></html>' }));
    await page.goto(`${base}/map-test`);
    await page.locator(".world-map-canvas:visible svg.world-map-inline").waitFor({ timeout: 10000 });
    const regions = page.getByRole("group", { name: "Weltmarktregion auswählen" });
    const asia = regions.getByRole("button", { name: "Asien auswählen" });
    await asia.click();
    assert.equal(await asia.getAttribute("aria-pressed"), "true");
    assert.equal(await regions.getByRole("button", { name: "Europa auswählen" }).getAttribute("aria-pressed"), "false");
    const eventFilters = page.getByRole("group", { name: "Ereignistyp filtern" });
    const centralBank = eventFilters.getByRole("button", { name: "Zentralbank" });
    await centralBank.click();
    assert.equal(await centralBank.getAttribute("aria-pressed"), "true");
    await page.getByRole("group", { name: "Ereignisse sortieren" }).getByText("1 Ereignisse", { exact: true }).waitFor();
    for (const groupName of ["Ereignistyp filtern", "Ereignisse sortieren", "Kartenzeitraum und Ebenen"]) {
      const group = page.getByRole("group", { name: groupName });
      if (width < 640) {
        for (const button of await group.getByRole("button").all()) {
          assert.ok((await button.boundingBox()).height >= 40, `${groupName}: mobile controls need a reliable touch height`);
        }
        await group.evaluate(el => { el.scrollLeft = el.scrollWidth; });
        assert.ok(await group.evaluate(el => el.scrollWidth <= el.clientWidth || el.scrollLeft > 0));
        await group.evaluate(el => { el.scrollLeft = 0; });
      }
    }
    const canvas = page.locator(".world-map-canvas:visible").first();
    const eventMarker = canvas.getByRole("button", { name: "Tokyo market event öffnen" });
    await eventMarker.waitFor();
    const [canvasBounds, markerBounds] = await Promise.all([canvas.boundingBox(), eventMarker.boundingBox()]);
    assert.ok(markerBounds.x >= canvasBounds.x && markerBounds.x + markerBounds.width <= canvasBounds.x + canvasBounds.width + 1, "Asian event marker must stay inside the visible map");
    if (width >= 768) {
      const legendToggle = canvas.getByRole("button", { name: "Legende", exact: true });
      const [toggleBounds, focusBounds] = await Promise.all([legendToggle.boundingBox(), canvas.locator(".map-event-focus").boundingBox()]);
      assert.ok(toggleBounds.x + toggleBounds.width < focusBounds.x, "Event focus card must not cover the map layer controls");
      await legendToggle.click();
      assert.equal(await legendToggle.getAttribute("aria-pressed"), "true");
    } else {
      await eventMarker.click();
      const drawer = page.getByRole("dialog", { name: /Zentralbankwechsel/i });
      await drawer.waitFor();
      assert.match(await drawer.evaluate(node => getComputedStyle(node).backgroundColor), /rgba?\(10, 18, 31/);
      assert.equal(await page.evaluate(() => document.body.style.overflow), "hidden");
      await drawer.getByRole("button", { name: "Schließen", exact: true }).waitFor();
      assert.equal(await drawer.getByRole("button", { name: "Schließen", exact: true }).evaluate(node => document.activeElement === node), true);
      await page.screenshot({ path: path.join(tmpdir(), `broker-world-map-drawer-${width}-dark.png`), fullPage: false });
      await drawer.getByRole("button", { name: "Schließen", exact: true }).click();
      await drawer.waitFor({ state: "detached" });
      assert.equal(await page.evaluate(() => document.body.style.overflow), "");
    }
    const plus = canvas.getByRole("button", { name: "Kartenzoom +" });
    await plus.click();
    const zoomHint = canvas.locator(".world-map-gesture-hint");
    await page.waitForTimeout(200);
    assert.match(await zoomHint.innerText(), /118%/);
    await canvas.getByRole("button", { name: "Kartenzoom 1x" }).click();
    await page.waitForFunction(() => [...document.querySelectorAll('.world-map-canvas .world-map-gesture-hint')].some(node => node.getBoundingClientRect().width > 0 && node.textContent?.includes("100%")));
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    for (const theme of ["dark", "light"]) {
      await page.evaluate(theme => { document.documentElement.dataset.theme = theme; }, theme);
      await page.screenshot({ path: path.join(tmpdir(), `broker-world-map-${width}-${theme}.png`), fullPage: false });
    }
    assert.deepEqual(errors, []);
    console.log(`world map passed: ${width}px, Asia selection, filters, SVG, zoom, light/dark`);
    await context.close();
  }
} finally {
  await browser?.close();
  await server.close();
}
