import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import ts from "typescript";

const source = await readFile(path.resolve("src/lib/chartTooltip.ts"), "utf8");
const transpiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
});
const tempDir = await mkdtemp(path.join(tmpdir(), "broker-chart-tooltip-"));
const modulePath = path.join(tempDir, "chartTooltip.mjs");

try {
  await writeFile(modulePath, transpiled.outputText, "utf8");
  const { calculateChartChangePct, describeChartFeed, formatChartAxisDate, formatChartTooltipDate, resolveChartPointIndex, resolveChartTooltipPoint } = await import(
    `file://${modulePath.replace(/\\/g, "/")}`
  );

  const point = { time: "2024-06-15", full_date: "2024-06-15T12:30:00Z", price: 182.25 };
  const stream = { connected: true, connectionState: "live", transportMode: "ws", streaming: true };
  assert.equal(describeChartFeed(stream), "Live-Feed");
  assert.equal(describeChartFeed({ ...stream, connected: false }), "Feed offline");
  assert.equal(describeChartFeed({ ...stream, connectionState: "degraded" }), "Feed verzögert");
  assert.equal(describeChartFeed({ ...stream, connectionState: "snapshot" }), "Snapshot");
  assert.equal(describeChartFeed({ ...stream, transportMode: "snapshot" }), "Snapshot");
  assert.equal(describeChartFeed({ ...stream, streaming: false }), "Snapshot");
  assert.equal(describeChartFeed({ ...stream, streaming: undefined }), "Snapshot");
  const payload = [
    { dataKey: "_sma20", value: 180, payload: point },
    { dataKey: "price", value: 182.25, payload: point },
  ];
  assert.deepEqual(resolveChartTooltipPoint(payload), point);
  assert.equal(resolveChartPointIndex(0, 2), 0);
  assert.equal(resolveChartPointIndex("1", 2), 1);
  for (const value of [null, undefined, "", " ", false, true, {}, [], -1, 2, 0.5, NaN, Infinity]) {
    assert.equal(resolveChartPointIndex(value, 2), null);
  }
  assert.equal(resolveChartPointIndex(0, 0), null);
  assert.equal(resolveChartTooltipPoint([]), null);
  for (const price of [null, undefined, "", " ", false, true, [], {}, Infinity, NaN]) {
    assert.equal(resolveChartTooltipPoint([{ dataKey: "price", payload: { ...point, price } }]), null);
    assert.equal(calculateChartChangePct(100, price), null);
  }
  assert.equal(calculateChartChangePct(100, 0), -100, "An explicit zero must remain distinct from missing data");
  assert.equal(resolveChartTooltipPoint([{ dataKey: "price", payload: { price: "bad" } }]), null);
  assert.match(formatChartTooltipDate(point, "5y"), /15\.06\.2024/);
  assert.match(formatChartTooltipDate(point, "1d"), /15\.06\.2024/);
  assert.equal(formatChartTooltipDate({ time: "unbekannt", price: 1 }, "max"), "unbekannt");
  assert.equal(formatChartAxisDate(undefined, "5d"), "");
  assert.equal(formatChartAxisDate({ time: "unbekannt", price: 1 }, "max"), "unbekannt");
  const clockTime = formatChartAxisDate(point, "1d");
  assert.match(clockTime, /^\d{2}:\d{2}$/);
  assert.ok(formatChartTooltipDate(point, "5d").includes(clockTime));
  assert.match(formatChartAxisDate(point, "5d"), /15\.06/);
  assert.ok(formatChartAxisDate(point, "5d").includes(clockTime));
  assert.equal(formatChartAxisDate(point, "1mo"), "15.06.");
  for (const period of ["1y", "5y", "max"]) {
    assert.equal(formatChartAxisDate(point, period), "06.24");
  }
  assert.equal(calculateChartChangePct(100, 125), 25);
  assert.ok(Math.abs(calculateChartChangePct(100, 80) - (-20)) < 1e-9);
  assert.equal(calculateChartChangePct(0, 80), null);
  assert.equal(calculateChartChangePct("bad", 80), null);
  console.log("chart tooltip tests passed");
} finally {
  await rm(tempDir, { recursive: true, force: true });
}
