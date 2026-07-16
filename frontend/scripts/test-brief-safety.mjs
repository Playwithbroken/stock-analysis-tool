import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import ts from "typescript";

const source = await readFile(path.resolve("src/lib/briefSafety.ts"), "utf8");
const transpiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
});
const tempDir = await mkdtemp(path.join(tmpdir(), "broker-brief-safety-"));
const modulePath = path.join(tempDir, "briefSafety.mjs");

try {
  await writeFile(modulePath, transpiled.outputText, "utf8");
  const { getBriefLoadState, guardBriefForDecisions, isBriefDecisionCurrent } = await import(
    `file://${modulePath.replace(/\\/g, "/")}`
  );
  const active = {
    quality: { freshness: "fresh" },
    trade_setups: [{ symbol: "AAPL" }],
    event_pings: [{ title: "Fed" }],
  };
  assert.equal(isBriefDecisionCurrent(active), true);
  assert.deepEqual(getBriefLoadState(active), { displayable: true, current: true });
  assert.equal(guardBriefForDecisions(active), active);

  const stale = {
    quality: { freshness: "stale" },
    trade_setups: [{ symbol: "AAPL" }],
    prediction_signals: [{ symbol: "BTC-USD" }],
    event_pings: [{ title: "Fed" }],
    top_news: [{ title: "Old headline" }],
    market_movers: { gainers: [{ symbol: "AAPL" }], losers: [] },
    regions: { usa: { label: "USA", tone: "risk-on", avg_change_1d: 2, assets: [{ ticker: "SPY" }] } },
    setup_board: { now: [{ symbol: "AAPL" }], next: [], avoid: [] },
  };
  const guardedStale = guardBriefForDecisions(stale);
  assert.equal(isBriefDecisionCurrent(stale), false);
  assert.deepEqual(getBriefLoadState(stale), { displayable: true, current: false });
  assert.deepEqual(guardedStale.trade_setups, []);
  assert.deepEqual(guardedStale.event_pings, []);
  assert.deepEqual(guardedStale.top_news, []);
  assert.deepEqual(guardedStale.market_movers, { gainers: [], losers: [] });
  assert.deepEqual(guardedStale.regions.usa.assets, []);
  assert.equal(guardedStale.regions.usa.tone, "mixed");
  assert.deepEqual(guardedStale.setup_board, { now: [], next: [], avoid: [] });
  assert.equal(guardedStale.trade_setups_status, "stale_data");
  assert.equal(guardedStale.decision_gate.allowed, false);

  const fallback = guardBriefForDecisions({
    quality: { freshness: "fresh", fallback: "timeout" },
    action_board: [{ ticker: "NVDA" }],
  });
  assert.deepEqual(fallback.action_board, []);
  assert.equal(fallback.decision_gate.reason, "fallback_data");
  assert.deepEqual(getBriefLoadState({ quality: { fallback: "timeout" } }), {
    displayable: false,
    current: false,
  });
  console.log("briefSafety tests passed");
} finally {
  await rm(tempDir, { recursive: true, force: true });
}
