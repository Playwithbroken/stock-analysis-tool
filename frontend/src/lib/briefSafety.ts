const BLOCKED_DECISION_FIELDS = [
  "trade_setups",
  "prediction_signals",
  "action_board",
  "event_layer",
  "event_pings",
  "top_news",
  "watchlist_impact",
  "product_catalysts",
  "congress_watch",
  "earnings_results",
  "earnings_calendar",
  "market_movers",
  "contrarian_signals",
  "opening_timeline",
] as const;

export function isBriefDecisionCurrent(brief: any): boolean {
  if (!brief || typeof brief !== "object") return false;
  const quality = brief.quality && typeof brief.quality === "object" ? brief.quality : {};
  return !quality.fallback && quality.freshness !== "stale";
}

export function guardBriefForDecisions(brief: any): any {
  if (!brief || typeof brief !== "object" || isBriefDecisionCurrent(brief)) return brief;

  const guarded = { ...brief };
  BLOCKED_DECISION_FIELDS.forEach((field) => {
    guarded[field] = field === "market_movers" ? { gainers: [], losers: [] } : [];
  });
  guarded.regions = Object.fromEntries(
    Object.entries(brief.regions || {}).map(([key, region]: [string, any]) => [
      key,
      { ...(region || {}), tone: "mixed", avg_change_1d: 0, assets: [] },
    ]),
  );
  guarded.setup_board = { now: [], next: [], avoid: [] };
  guarded.trade_setups_status = "stale_data";
  guarded.decision_gate = {
    allowed: false,
    reason: brief.quality?.fallback ? "fallback_data" : "stale_data",
  };
  return guarded;
}
