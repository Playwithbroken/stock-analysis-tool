import React, { useMemo, useState } from "react";
import WorldMarketMap from "./WorldMarketMap";

interface MorningBriefPanelProps {
  brief: any;
  onAnalyze: (ticker: string) => void;
  realtimeQuotes?: Record<string, any>;
  realtimeConnected?: boolean;
  hideMap?: boolean;
}

function fmt(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return "N/A";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function regimeStyle(regime?: string) {
  const r = (regime || "").toLowerCase();
  if (r.includes("risk-on") || r.includes("on"))
    return { icon: "↗", bg: "bg-emerald-500/10", text: "text-emerald-700", border: "border-emerald-500/20" };
  if (r.includes("risk-off") || r.includes("off"))
    return { icon: "↘", bg: "bg-red-500/10", text: "text-red-700", border: "border-red-500/20" };
  return { icon: "⚖", bg: "bg-amber-500/10", text: "text-amber-700", border: "border-amber-500/20" };
}

function formatRegimeLabel(regime?: string) {
  return String(regime || "mixed").replace("-", " ");
}

function toneBadge(tone?: string) {
  const t = (tone || "").toLowerCase();
  if (t.includes("bullish") || t.includes("risk-on") || t.includes("on"))
    return { icon: "▲", color: "text-emerald-700 bg-emerald-500/10" };
  if (t.includes("bearish") || t.includes("risk-off") || t.includes("off"))
    return { icon: "▼", color: "text-red-700 bg-red-500/10" };
  return { icon: "◆", color: "text-amber-700 bg-amber-500/10" };
}

function actionTone(action?: string) {
  if (action === "hedge") return "bg-sky-500/10 text-sky-700";
  if (action === "reduce") return "bg-red-500/10 text-red-700";
  if (action === "add") return "bg-emerald-500/10 text-emerald-700";
  return "bg-amber-500/10 text-amber-700";
}

function exposureTone(value?: string) {
  if (value === "high") return "bg-red-500/10 text-red-700";
  if (value === "medium") return "bg-amber-500/10 text-amber-700";
  return "bg-emerald-500/10 text-emerald-700";
}

function decisionTone(value?: string) {
  if (value === "high conviction") return "bg-emerald-500/10 text-emerald-700";
  if (value === "selective") return "bg-sky-500/10 text-sky-700";
  if (value === "tactical only") return "bg-amber-500/10 text-amber-700";
  return "bg-slate-500/10 text-slate-600";
}

function setupBucketTone(bucket: "now" | "next" | "avoid") {
  if (bucket === "now") return "border-emerald-500/16 bg-emerald-500/5 text-emerald-700";
  if (bucket === "avoid") return "border-red-500/16 bg-red-500/5 text-red-700";
  return "border-amber-500/16 bg-amber-500/5 text-amber-700";
}

function sectorHeatProfile(sector: string, action?: string) {
  const sectorKey = sector.toLowerCase();
  const longish = action === "long";
  const hedgeish = action === "hedge";
  const shortish = action === "short";

  let level = 52;
  if (/(energy|defense|gold)/.test(sectorKey)) level = hedgeish || longish ? 88 : 68;
  else if (/(airlines|transport|consumer|growth|reits)/.test(sectorKey)) level = shortish ? 82 : 58;
  else if (/(financial|banks|utilities|industrials|semis|autos)/.test(sectorKey)) level = 72;

  const toneClass =
    hedgeish || longish
      ? "bg-emerald-500"
      : shortish
        ? "bg-red-500"
        : "bg-sky-500";

  return { level, toneClass };
}

type PingFilter = "all" | "conflict" | "central_bank" | "energy" | "election" | "policy" | "disaster" | "macro";

function pingSeverityTone(severity?: string) {
  const s = (severity || "").toLowerCase();
  if (s === "critical") return "bg-red-500/10 text-red-700";
  if (s === "elevated") return "bg-amber-500/10 text-amber-700";
  return "bg-slate-500/10 text-slate-600";
}

function pingTypeLabel(type?: string) {
  const t = String(type || "macro").toLowerCase();
  const labels: Record<string, string> = {
    conflict: "War/Conflict",
    central_bank: "Central Bank",
    energy: "Energy",
    election: "Vote/Election",
    policy: "Policy",
    disaster: "Natural Event",
    macro: "Macro",
  };
  return labels[t] || t.replace("_", " ");
}

function extractTickerCandidates(text?: string) {
  if (!text) return [];
  const matches = text.match(/\b[A-Z]{1,5}(?:-[A-Z]{1,5})?\b/g) || [];
  return [...new Set(matches)];
}

function moveLabel(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return "n/a";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export default function MorningBriefPanel({
  brief,
  onAnalyze,
  realtimeQuotes = {},
  realtimeConnected = false,
  hideMap = false,
}: MorningBriefPanelProps) {
  if (!brief) return null;
  const quality = brief.quality || null;
  const qualityReady = quality?.status === "ready";

  const regions = [
    brief.regions?.asia,
    brief.regions?.europe,
    brief.regions?.usa,
  ].filter(Boolean);

  const [selectedRegion, setSelectedRegion] = useState<string>(
    brief.regions?.europe?.label || regions[0]?.label || "USA",
  );
  const [pingFilter, setPingFilter] = useState<PingFilter>("all");

  const regionNews = useMemo(() => {
    const keywords: Record<string, string[]> = {
      USA: ["usa", "u.s.", "us ", "federal reserve", "fed", "wall street"],
      Europe: ["europe", "eu", "ecb", "germany", "france", "uk", "britain"],
      Asia: ["asia", "china", "japan", "hong kong", "taiwan", "india", "korea"],
    };
    const terms = keywords[selectedRegion] || [];
    return (brief.top_news || []).filter((item: any) => {
      const haystack = `${item.region || ""} ${item.title || ""}`.toLowerCase();
      return terms.some((term) => haystack.includes(term));
    });
  }, [brief.top_news, selectedRegion]);

  const eventPingQueue = useMemo(() => {
    const source = Array.isArray(brief.event_pings) ? brief.event_pings : [];
    const severityWeight: Record<string, number> = { critical: 100, elevated: 70, normal: 45 };
    const typeWeight: Record<string, number> = {
      conflict: 28,
      central_bank: 24,
      energy: 22,
      election: 18,
      policy: 16,
      disaster: 14,
      macro: 10,
    };

    const rows = source.map((ping: any, idx: number) => {
      const type = String(ping?.type || "macro").toLowerCase();
      const severity = String(ping?.severity || "normal").toLowerCase();
      const confidence = Number.isFinite(Number(ping?.confidence)) ? Number(ping.confidence) : 50;
      const startedAt = ping?.started_at ? Date.parse(ping.started_at) : NaN;
      const ageMinutes = Number.isFinite(startedAt) ? Math.max(0, Math.round((Date.now() - startedAt) / 60000)) : 120;
      const recencyScore = ageMinutes <= 30 ? 25 : ageMinutes <= 120 ? 14 : 6;
      const symbols = (Array.isArray(ping?.trade_impact?.symbols) && ping.trade_impact.symbols.length
        ? ping.trade_impact.symbols
        : ping?.symbols || []).filter(Boolean);
      const hedgeCandidates = extractTickerCandidates(ping?.trade_impact?.hedge_idea);
      const score =
        (severityWeight[severity] || severityWeight.normal) +
        (typeWeight[type] || typeWeight.macro) +
        confidence * 0.45 +
        recencyScore;
      return {
        ...ping,
        type,
        severity,
        confidence,
        symbols,
        hedgeCandidates,
        ageMinutes,
        priorityScore: Math.round(score),
        rankKey: `${type}-${severity}-${idx}`,
      };
    });

    const filtered: any[] = pingFilter === "all" ? rows : rows.filter((row: any) => row.type === pingFilter);
    return filtered
      .sort((a: any, b: any) => b.priorityScore - a.priorityScore || a.ageMinutes - b.ageMinutes)
      .slice(0, 8);
  }, [brief.event_pings, pingFilter]);

  const marketMovers = brief.market_movers || {};
  const topGainers = Array.isArray(marketMovers.gainers) ? marketMovers.gainers.slice(0, 4) : [];
  const topLosers = Array.isArray(marketMovers.losers) ? marketMovers.losers.slice(0, 4) : [];
  const productCatalysts = Array.isArray(brief.product_catalysts) ? brief.product_catalysts.slice(0, 4) : [];
  const setupBoard = brief.setup_board || { now: [], next: [], avoid: [] };

  return (
    <div className="space-y-6">
      <section className="surface-panel relative overflow-hidden rounded-[2.5rem] p-6 sm:p-8">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-32 bg-[radial-gradient(circle_at_top_left,rgba(15,118,110,0.12),transparent_60%)]" />
        <div className="pointer-events-none absolute right-0 top-0 h-48 w-48 rounded-full bg-[radial-gradient(circle,rgba(22,28,36,0.06),transparent_72%)]" />

        <div className="relative flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-[var(--accent-soft)] px-3 py-1 text-[11px] font-extrabold uppercase tracking-[0.22em] text-[var(--accent)]">
            Morning Brief
          </span>
          {(() => {
            const rs = regimeStyle(brief.macro_regime);
            return (
              <span className={`rounded-full border ${rs.border} ${rs.bg} px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] ${rs.text}`}>
                {rs.icon} {formatRegimeLabel(brief.macro_regime)}
              </span>
            );
          })()}
          <span className="rounded-full border border-black/8 bg-white/70 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
            Focus {selectedRegion}
          </span>
        </div>
        <div className="relative mt-5 grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
          <div>
            <h2 className="text-4xl text-slate-900 sm:text-5xl">
              {brief.headline}
            </h2>
            <p className="mt-4 max-w-3xl text-base leading-7 text-slate-600">
              {brief.opening_bias}
            </p>
          </div>
          <div className="rounded-[1.8rem] border border-black/8 bg-white/78 p-5">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Opening Read
            </div>
            {quality ? (
              <div className={`mt-3 inline-flex rounded-full px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] ${qualityReady ? "bg-emerald-500/10 text-emerald-700" : "bg-amber-500/10 text-amber-700"}`}>
                {qualityReady ? "Brief Ready" : "Brief Partial"} · {quality.score}/100
              </div>
            ) : null}
            <div className="mt-3 text-sm leading-7 text-slate-700">
              {brief.headline}
            </div>
            <div className="mt-4 rounded-[1rem] border border-black/8 bg-[var(--accent-soft)] px-3 py-2 text-[11px] font-bold uppercase tracking-[0.14em] text-[var(--accent)]">
              {brief.opening_bias}
            </div>
            {quality?.missing?.length ? (
              <div className="mt-3 rounded-[0.9rem] border border-amber-500/20 bg-amber-500/6 px-3 py-2 text-[11px] text-amber-800">
                Missing: {quality.missing.slice(0, 3).join(" · ")}
              </div>
            ) : null}
          </div>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-3">
          <div className="rounded-[1.6rem] border border-black/8 bg-white/80 p-5">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Macro Score
            </div>
            <div className="mt-2 text-3xl font-black text-slate-900">
              {brief.macro_score}
            </div>
          </div>
          <div className="rounded-[1.6rem] border border-black/8 bg-white/80 p-5">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Regime
            </div>
            <div className="mt-3">
              {(() => {
                const rs = regimeStyle(brief.macro_regime);
                return (
                  <span className={`inline-flex rounded-full border ${rs.border} ${rs.bg} px-3 py-1.5 text-[11px] font-extrabold uppercase tracking-[0.16em] ${rs.text}`}>
                    {rs.icon} {formatRegimeLabel(brief.macro_regime)}
                  </span>
                );
              })()}
            </div>
          </div>
          <div className="rounded-[1.6rem] border border-black/8 bg-white/80 p-5">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Generated
            </div>
            <div className="mt-2 text-lg font-black text-slate-900">
              {new Date(brief.generated_at).toLocaleTimeString()}
            </div>
            {quality?.age_minutes != null ? (
              <div className="mt-1 text-[11px] font-semibold text-slate-500">
                age {quality.age_minutes}m
              </div>
            ) : null}
            <div className={`mt-2 inline-flex rounded-full px-2 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] ${realtimeConnected ? "bg-emerald-500/10 text-emerald-700" : "bg-slate-500/10 text-slate-500"}`}>
              {realtimeConnected ? "Live stream on" : "Snapshot mode"}
            </div>
          </div>
        </div>
      </section>

      {!hideMap && (
        <WorldMarketMap
          regions={regions}
          selectedRegion={selectedRegion}
          onSelectRegion={setSelectedRegion}
          news={brief.top_news || []}
          eventLayer={brief.event_layer || []}
          eventPings={brief.event_pings || []}
          watchlistImpact={brief.watchlist_impact || []}
          contrarianSignals={brief.contrarian_signals || []}
          openingTimeline={brief.opening_timeline || []}
          onAnalyze={onAnalyze}
          focusTicker={brief.watchlist_impact?.[0]?.ticker}
        />
      )}

      {(topGainers.length || topLosers.length || productCatalysts.length) ? (
        <section className="grid gap-4 xl:grid-cols-[1fr_0.9fr]">
          <div className="surface-panel rounded-[2rem] p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                  Biggest Winners / Losers
                </div>
                <div className="mt-1 text-sm text-slate-500">
                  Broad universe, not only mega caps.
                </div>
              </div>
              <span className="rounded-full bg-[var(--accent-soft)] px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-[var(--accent)]">
                movers
              </span>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-emerald-700">
                  Winners
                </div>
                {topGainers.map((item: any) => {
                  const chg = typeof item.change_1d === "number" ? item.change_1d : item.change_1w;
                  return (
                    <button
                      key={`gainer-${item.ticker}`}
                      type="button"
                      onClick={() => item.ticker && onAnalyze(item.ticker)}
                      className="w-full rounded-[1.1rem] border border-emerald-500/10 bg-emerald-500/[0.06] p-3 text-left transition-colors hover:bg-emerald-500/10"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-extrabold text-slate-900">{item.ticker}</span>
                        <span className="text-sm font-bold text-emerald-700">{moveLabel(chg)}</span>
                      </div>
                      <div className="mt-1 truncate text-xs text-slate-500">{item.name || item.sector || "Market mover"}</div>
                    </button>
                  );
                })}
              </div>
              <div className="space-y-2">
                <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-red-700">
                  Losers
                </div>
                {topLosers.map((item: any) => {
                  const chg = typeof item.change_1d === "number" ? item.change_1d : item.change_1w;
                  return (
                    <button
                      key={`loser-${item.ticker}`}
                      type="button"
                      onClick={() => item.ticker && onAnalyze(item.ticker)}
                      className="w-full rounded-[1.1rem] border border-red-500/10 bg-red-500/[0.06] p-3 text-left transition-colors hover:bg-red-500/10"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-extrabold text-slate-900">{item.ticker}</span>
                        <span className="text-sm font-bold text-red-700">{moveLabel(chg)}</span>
                      </div>
                      <div className="mt-1 truncate text-xs text-slate-500">{item.name || item.sector || "Market mover"}</div>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="surface-panel rounded-[2rem] p-5">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Product Catalyst Radar
            </div>
            <div className="mt-1 text-sm text-slate-500">
              Launches, delays, GPUs, iPhone, autos, games.
            </div>
            <div className="mt-4 space-y-3">
              {productCatalysts.length ? productCatalysts.map((item: any) => (
                <div key={`${item.ticker}-${item.title}`} className="rounded-[1.1rem] border border-black/8 bg-white/70 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <button
                      type="button"
                      onClick={() => item.ticker && onAnalyze(item.ticker)}
                      className="rounded-full bg-[var(--accent)] px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.14em] text-white"
                    >
                      {item.ticker}
                    </button>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.14em] ${
                      item.direction_hint === "negative"
                        ? "bg-red-500/10 text-red-700"
                        : item.direction_hint === "positive_watch"
                          ? "bg-emerald-500/10 text-emerald-700"
                          : "bg-amber-500/10 text-amber-700"
                    }`}>
                      {item.catalyst_type || "product"}
                    </span>
                  </div>
                  <div className="mt-2 text-sm font-bold text-slate-900">{item.theme}</div>
                  <div className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{item.title}</div>
                </div>
              )) : (
                <div className="rounded-[1.1rem] border border-black/8 bg-white/70 p-3 text-sm text-slate-500">
                  No strong product catalyst in the current trusted feed.
                </div>
              )}
            </div>
          </div>
        </section>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-3">
        {regions.map((region: any) => (
          <div
            key={region.label}
            className={`surface-panel rounded-[2rem] p-5 transition-all ${
              selectedRegion === region.label ? "ring-1 ring-black/10" : ""
            }`}
          >
            <div className="flex items-center justify-between">
              <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                {region.label}
              </div>
              {(() => {
                const tb = toneBadge(region.tone);
                return (
                  <button
                    onClick={() => setSelectedRegion(region.label)}
                    className={`rounded-full px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.14em] ${tb.color}`}
                  >
                    {tb.icon} {region.tone}
                  </button>
                );
              })()}
            </div>
            <div className="mt-2 text-2xl font-black text-slate-900">
              {fmt(region.avg_change_1d)}
            </div>
            <div className="mt-4 space-y-3">
              {region.assets?.map((asset: any) => {
                const live = realtimeQuotes[asset.ticker];
                return (
                <div
                  key={asset.ticker}
                  className="flex items-center justify-between rounded-[1.2rem] border border-black/8 bg-white/70 p-3"
                >
                  <div>
                    <div className="text-sm font-bold text-slate-900">{asset.label}</div>
                    <div className="text-xs text-slate-500">
                      {asset.ticker}{live?.price != null ? ` · ${live.price}` : ""}
                    </div>
                  </div>
                  <div
                    className={`text-sm font-bold ${
                      ((live?.change_1w ?? asset.change_1d) || 0) >= 0 ? "text-emerald-700" : "text-red-700"
                    }`}
                  >
                    {fmt(live?.change_1w ?? asset.change_1d)}
                  </div>
                </div>
              )})}
            </div>
          </div>
        ))}
      </section>

      <section className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
        <div className="surface-panel rounded-[2rem] p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Top Now / Next / Avoid
            </div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
              compressed brief
            </div>
          </div>
          <div className="mt-4 grid gap-3">
            {(["now", "next", "avoid"] as const).map((bucket) => {
              const rows = setupBoard[bucket] || [];
              const title = bucket === "now" ? "Now" : bucket === "next" ? "Next" : "Avoid";
              const tone = setupBucketTone(bucket);
              return (
                <div key={bucket} className={`rounded-[1.2rem] border p-4 ${tone}`}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-[11px] font-extrabold uppercase tracking-[0.18em]">
                      {title}
                    </div>
                    <div className="text-[10px] font-bold uppercase tracking-[0.14em] opacity-70">
                      {rows.length} setups
                    </div>
                  </div>
                  <div className="mt-3 space-y-2">
                    {rows.length ? rows.slice(0, 3).map((item: any, idx: number) => (
                      <div key={`${bucket}-${item.symbol}-${idx}`} className="rounded-[1rem] border border-black/8 bg-white/80 p-3 text-sm">
                        <div className="flex items-center justify-between gap-2">
                          <button
                            onClick={() => item.symbol && onAnalyze(item.symbol)}
                            className="font-black text-slate-900"
                          >
                            {item.symbol}
                          </button>
                          <span className={`rounded-full px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.14em] ${decisionTone(item.decision_quality)}`}>
                            {item.decision_quality || "setup"}
                          </span>
                        </div>
                        <div className="mt-1 text-xs leading-6 text-slate-600">{item.thesis}</div>
                        <div className="mt-2 flex flex-wrap gap-2 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                          {item.confidence != null ? (
                            <span className="rounded-full border border-black/8 bg-white px-2 py-0.5">
                              {item.confidence}% conf
                            </span>
                          ) : null}
                          {item.size_guidance ? (
                            <span className="rounded-full border border-black/8 bg-white px-2 py-0.5">
                              {item.size_guidance}
                            </span>
                          ) : null}
                          {item.expected_move ? (
                            <span className="rounded-full border border-black/8 bg-white px-2 py-0.5">
                              move {item.expected_move}
                            </span>
                          ) : null}
                        </div>
                      </div>
                    )) : (
                      <div className="rounded-[1rem] border border-black/8 bg-white/80 p-3 text-sm text-slate-500">
                        Keine klaren {title.toLowerCase()}-Setups.
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="surface-panel rounded-[2rem] p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Top 5 Trade Setups
            </div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
              trader-first
            </div>
          </div>
          <div className="mt-4 space-y-3">
            {(brief.trade_setups || []).slice(0, 5).map((setup: any, idx: number) => (
              <div
                key={`${setup.symbol}-${idx}`}
                className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="rounded-full border border-black/8 bg-white px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                      #{setup.rank ?? idx + 1}
                    </span>
                    <button
                      onClick={() => setup.symbol && onAnalyze(setup.symbol)}
                      className="rounded-full bg-[var(--accent)] px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-white"
                    >
                      {setup.symbol}
                    </button>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="rounded-full border border-black/8 bg-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                      score {setup.rank_score ?? "n/a"}
                    </span>
                    <span className="rounded-full border border-black/8 bg-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                      confidence {setup.confidence}
                    </span>
                  </div>
                </div>
                <div className="mt-2 text-sm font-bold text-slate-900">{setup.thesis}</div>
                {Number(setup.learning_adjustment?.score_delta || 0) !== 0 ? (
                  <div className={`mt-2 rounded-[0.9rem] border px-3 py-2 text-[11px] font-bold ${
                    Number(setup.learning_adjustment.score_delta) > 0
                      ? "border-emerald-500/20 bg-emerald-500/8 text-emerald-800"
                      : "border-red-500/20 bg-red-500/8 text-red-800"
                  }`}>
                    Learning bias {Number(setup.learning_adjustment.score_delta) > 0 ? "+" : ""}
                    {setup.learning_adjustment.score_delta}: {setup.learning_adjustment.reason}
                  </div>
                ) : null}
                <div className="mt-2 grid gap-2 text-xs text-slate-500 sm:grid-cols-2">
                  <div>Trigger: {setup.trigger}</div>
                  <div>Window: {setup.window}</div>
                  <div>Invalidation: {setup.invalidation}</div>
                  <div>Expected move: {setup.expected_move}</div>
                </div>
                {setup.catalysts?.length ? (
                  <div className="mt-2 flex flex-wrap gap-2 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                    {setup.catalysts.slice(0, 3).map((c: string) => (
                      <span key={c} className="rounded-full border border-black/8 bg-white px-2 py-0.5">
                        {c}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
            {!(brief.trade_setups || []).length ? (
              <div className="rounded-[1rem] border border-black/8 bg-white/75 p-3 text-sm text-slate-500">
                {brief.trade_setups_status === "insufficient_signal"
                  ? "Insufficient signal: aktuell keine belastbaren Setups."
                  : "Keine belastbaren Setups im aktuellen Feed."}
              </div>
            ) : null}
          </div>
          {(brief.learning_adjustments || []).length ? (
            <div className="mt-4 rounded-[1.2rem] border border-[var(--accent)]/14 bg-[var(--accent-soft)]/60 p-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-[var(--accent)]">
                Learning applied to ranking
              </div>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                {(brief.learning_adjustments || []).slice(0, 4).map((item: any, index: number) => (
                  <div key={`${item.axis}-${item.label}-${index}`} className="rounded-[1rem] border border-black/8 bg-white/78 px-3 py-2 text-xs text-slate-700">
                    <div className="font-extrabold uppercase tracking-[0.14em] text-slate-500">
                      {item.axis}: {item.label}
                    </div>
                    <div className="mt-1">
                      hit {item.hit_rate}% - ranking {Number(item.score_delta) > 0 ? "+" : ""}
                      {item.score_delta}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <div className="surface-panel rounded-[2rem] p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Action Board
            </div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
              world watch
            </div>
          </div>
          <div className="mt-4 space-y-3">
            {(brief.action_board || []).slice(0, 6).map((item: any, index: number) => (
              <div
                key={`${item.title}-${index}`}
                className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-xs font-extrabold uppercase tracking-[0.18em] text-slate-500">
                    {item.region} · {item.event_type} · {item.impact}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${
                      item.setup === "long"
                        ? "bg-emerald-500/10 text-emerald-700"
                        : item.setup === "short" || item.setup === "watch-short"
                          ? "bg-red-500/10 text-red-700"
                          : item.setup === "hedge"
                            ? "bg-sky-500/10 text-sky-700"
                            : "bg-amber-500/10 text-amber-700"
                    }`}>
                      {item.setup}
                    </span>
                    <span className="rounded-full border border-black/8 bg-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                      leverage {item.leverage}
                    </span>
                    {item.ticker && (
                      <button
                        onClick={() => onAnalyze(item.ticker)}
                        className="rounded-full bg-[var(--accent)] px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-white"
                      >
                        {item.ticker}
                      </button>
                    )}
                  </div>
                </div>
                <div className="mt-2 text-sm font-bold text-slate-900">{item.title}</div>
                <div className="mt-2 text-sm text-slate-600">{item.thesis}</div>
                {item.event_intelligence ? (
                  <div className="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-2">
                    <div>Impact {item.event_intelligence.impact_score}</div>
                    <div>Confidence {item.event_intelligence.confidence_score}</div>
                    <div>Decay {item.event_intelligence.decay}</div>
                    <div>Action {item.event_intelligence.action}</div>
                  </div>
                ) : null}
                {item.event_intelligence?.decision_quality ? (
                  <div className="mt-2 flex flex-wrap gap-2 text-[10px] font-bold uppercase tracking-[0.14em]">
                    <span className={`rounded-full px-2 py-1 ${decisionTone(item.event_intelligence.decision_quality)}`}>
                      {item.event_intelligence.decision_quality}
                    </span>
                    {item.event_intelligence.size_guidance ? (
                      <span className="rounded-full border border-black/8 bg-white px-2 py-1 text-slate-500">
                        {item.event_intelligence.size_guidance}
                      </span>
                    ) : null}
                    {item.event_intelligence.execution_bias ? (
                      <span className="rounded-full border border-black/8 bg-white px-2 py-1 text-slate-500">
                        {item.event_intelligence.execution_bias}
                      </span>
                    ) : null}
                  </div>
                ) : null}
                {item.event_intelligence?.affected_sectors?.length ? (
                  <div className="mt-3 grid gap-2">
                    {item.event_intelligence.affected_sectors.slice(0, 3).map((sector: string) => {
                      const heat = sectorHeatProfile(sector, item.event_intelligence?.action);
                      return (
                        <div
                          key={sector}
                          className="rounded-[0.95rem] border border-black/8 bg-white px-3 py-2"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-700">
                              {sector}
                            </span>
                            <span className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                              {heat.level}
                            </span>
                          </div>
                          <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                            <div
                              className={`h-full rounded-full ${heat.toneClass}`}
                              style={{ width: `${heat.level}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : null}
                {item.portfolio_exposure?.note ? (
                  <div className="mt-2 rounded-[0.9rem] border border-black/8 bg-[var(--accent-soft)] px-3 py-2 text-xs text-slate-700">
                    {item.portfolio_exposure.note}
                  </div>
                ) : null}
                <div className="mt-2 grid gap-2 text-xs text-slate-500 sm:grid-cols-2">
                  <div>Trigger: {item.trigger}</div>
                  <div>Risk: {item.risk}</div>
                </div>
                {item.event_intelligence?.invalidation ? (
                  <div className="mt-2 text-xs text-slate-500">
                    Invalidation: {item.event_intelligence.invalidation}
                  </div>
                ) : null}
                {item.event_intelligence?.execution_window ? (
                  <div className="mt-1 text-xs font-bold uppercase tracking-[0.14em] text-slate-500">
                    Window: {item.event_intelligence.execution_window}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>

        <div className="surface-panel rounded-[2rem] p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Congress Watch
            </div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
              PTR · delayed official filings
            </div>
          </div>
          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            {(brief.congress_watch || []).length ? (
              (brief.congress_watch || []).slice(0, 5).map((item: any, index: number) => (
                <div
                  key={`${item.name}-${item.ticker}-${index}`}
                  className="rounded-[1.25rem] border border-[var(--accent)]/16 bg-[linear-gradient(180deg,rgba(15,118,110,0.07),rgba(255,255,255,0.82))] p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                        {item.impact} impact · {item.freshness}
                      </div>
                      <div className="mt-1 text-sm font-black text-slate-900">{item.name}</div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {item.ticker ? (
                        <button
                          onClick={() => onAnalyze(item.ticker)}
                          className="rounded-full bg-[var(--accent)] px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-white"
                        >
                          {item.ticker}
                        </button>
                      ) : null}
                      <span className="rounded-full border border-black/8 bg-white px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-600">
                        {item.confidence || "n/a"} conf
                      </span>
                    </div>
                  </div>
                  <div className="mt-3 grid gap-2 text-xs text-slate-600 sm:grid-cols-2">
                    <div>Action: {item.action || item.setup}</div>
                    <div>Amount: {item.amount_range || "n/a"}</div>
                    <div>Trade date: {item.trade_date || "n/a"}</div>
                    <div>Delay: {item.delay_days != null ? `${item.delay_days}d` : "n/a"}</div>
                  </div>
                  <div className="mt-3 text-sm font-semibold text-slate-800">{item.thesis}</div>
                  <div className="mt-3 grid gap-2 text-xs text-slate-500">
                    <div>Trigger: {item.trigger}</div>
                    <div>Invalidierung: {item.invalidation}</div>
                  </div>
                  {item.cluster?.length ? (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {item.cluster.slice(0, 5).map((ticker: string) => (
                        <span
                          key={ticker}
                          className="rounded-full border border-black/8 bg-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500"
                        >
                          {ticker}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  <div className="mt-3 rounded-[0.9rem] border border-black/8 bg-white/70 p-3 text-[11px] leading-5 text-slate-500">
                    {item.compliance_note}
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4 text-sm text-slate-500">
                Keine priorisierten Congress-PTR-Signale im aktuellen Brief.
              </div>
            )}
          </div>
        </div>

        <div className="surface-panel rounded-[2rem] p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Top News
            </div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
              Trusted only
            </div>
          </div>
          <div className="mt-4 space-y-3">
            {(regionNews.length ? regionNews : brief.top_news || []).slice(0, 6).map((item: any, index: number) => (
              <a
                key={`${item.title}-${index}`}
                href={item.link}
                target="_blank"
                rel="noreferrer"
                className="block rounded-[1.2rem] border border-black/8 bg-white/70 p-4 transition-colors hover:bg-white"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="text-xs font-extrabold uppercase tracking-[0.18em] text-slate-500">
                    {item.region} · {item.impact}
                  </div>
                  {item.ticker && (
                    <button
                      onClick={(e) => {
                        e.preventDefault();
                        onAnalyze(item.ticker);
                      }}
                      className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.18em] text-white"
                    >
                      {item.ticker}
                    </button>
                  )}
                </div>
                <div className="mt-2 text-sm font-bold text-slate-900">{item.title}</div>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <span>{item.publisher}</span>
                  <span className="rounded-full border border-black/8 bg-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                    {item.source_quality || "trusted"}
                  </span>
                </div>
              </a>
            ))}
          </div>
        </div>

        <div className="space-y-4">
          <div className="surface-panel rounded-[2rem] p-5">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Source Policy
            </div>
            <div className="mt-4 rounded-[1.2rem] border border-black/8 bg-white/70 p-4 text-sm leading-7 text-slate-600">
              {brief.source_policy?.note ||
                "Top News zeigt nur serioese Quellen. Social wird ausgeschlossen."}
            </div>
          </div>

          <div className="surface-panel rounded-[2rem] p-5">
            <div className="flex items-center justify-between gap-3">
              <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                Social Radar
              </div>
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
                X / Reddit / Crowd
              </div>
            </div>
            <div className="mt-4 space-y-3">
              {(brief.social_signals || []).length ? (
                (brief.social_signals || []).slice(0, 4).map((item: any, index: number) => (
                  <div
                    key={`${item.ticker || item.publisher || item.event_type}-${index}`}
                    className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-xs font-extrabold uppercase tracking-[0.18em] text-slate-500">
                        {item.region} · {item.event_type}
                      </div>
                      <div className="rounded-full border border-sky-500/20 bg-sky-500/8 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-sky-700">
                        {item.publisher || "Social"}
                      </div>
                    </div>
                    <div className="mt-2 text-sm font-bold text-slate-900">
                      {(item.ticker || "Macro")} with {item.mentions} social mentions
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                      <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                        score {item.social_score ?? "n/a"}
                      </span>
                      <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                        {item.social_style || "social pulse"}
                      </span>
                      <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                        {item.social_bias || "watch"}
                      </span>
                      <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                        {item.social_intensity || "low"}
                      </span>
                    </div>
                    <div className="mt-2 text-xs text-slate-600">
                      Action: {item.social_action || "monitor"} | Risk: {item.social_risk || "needs confirmation"}
                    </div>
                    <div className="mt-2 text-xs text-slate-500">
                      {(item.titles || []).slice(0, 2).join(" | ") || "Live social pulse"}
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4 text-sm text-slate-500">
                  Kein relevantes X-/Social-Signal im aktuellen Brief. Das spricht eher fuer wenig akuten Retail- oder Narrative-Druck.
                </div>
              )}
              {(brief.crowd_signals || []).length ? (
                (brief.crowd_signals || []).slice(0, 3).map((item: any, index: number) => (
                  <div
                    key={`${item.ticker || item.event_type}-crowd-${index}`}
                    className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-xs font-extrabold uppercase tracking-[0.18em] text-slate-500">
                        {item.region} · {item.event_type}
                      </div>
                      <div className="rounded-full border border-amber-500/20 bg-amber-500/8 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-amber-700">
                        Reddit / Crowd
                      </div>
                    </div>
                    <div className="mt-2 text-sm font-bold text-slate-900">
                      {(item.ticker || "Macro")} with {item.mentions} matching mentions
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                      <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                        score {item.crowd_score ?? "n/a"}
                      </span>
                      <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                        {item.crowd_style || "crowd pressure"}
                      </span>
                      <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                        {item.crowd_bias || "watch"}
                      </span>
                      <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                        {item.crowd_intensity || "low"}
                      </span>
                    </div>
                    <div className="mt-2 text-xs text-slate-600">
                      Action: {item.crowd_action || "track only"} | Risk: {item.crowd_risk || "needs tape confirmation"}
                    </div>
                    <div className="mt-2 text-xs text-slate-500">
                      {(item.titles || []).slice(0, 2).join(" | ") || "Crowd cluster"}
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4 text-sm text-slate-500">
                  Kein relevantes Reddit-/Crowd-Cluster im aktuellen Brief. Im Moment ist also kein sichtbarer Meme- oder Crowd-Schub dominant.
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      <section className="surface-panel rounded-[2rem] p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
            Event Ping Inbox
          </div>
          <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
            Priority queue
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {(
            [
              { key: "all", label: "All" },
              { key: "conflict", label: "War" },
              { key: "central_bank", label: "CB" },
              { key: "energy", label: "Oil" },
              { key: "election", label: "Vote" },
              { key: "policy", label: "Policy" },
            ] as Array<{ key: PingFilter; label: string }>
          ).map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setPingFilter(item.key)}
              className={`rounded-full px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] ${
                pingFilter === item.key
                  ? "bg-[#101114] text-white"
                  : "border border-black/8 bg-white text-slate-600"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="mt-4 grid gap-3 xl:grid-cols-2">
          {eventPingQueue.length ? (
            eventPingQueue.map((ping: any, idx: number) => (
              <div
                key={ping.id || ping.rankKey}
                className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="rounded-full border border-black/8 bg-white px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                      #{idx + 1}
                    </span>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${pingSeverityTone(ping.severity)}`}>
                      {ping.severity}
                    </span>
                    <span className="rounded-full border border-black/8 bg-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                      {pingTypeLabel(ping.type)}
                    </span>
                  </div>
                  <span className="rounded-full border border-black/8 bg-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                    score {ping.priorityScore}
                  </span>
                </div>
                <div className="mt-2 text-sm font-bold text-slate-900">
                  {ping.title || "Event signal"}
                </div>
                <div className="mt-2 grid gap-2 text-xs text-slate-500 sm:grid-cols-2">
                  <div>Region: {ping.region || "global"}</div>
                  <div>Confidence: {ping.confidence}</div>
                  <div>Age: {ping.ageMinutes}m</div>
                  <div>Window: {ping?.trade_impact?.window || "open+60m"}</div>
                </div>
                {ping?.trade_impact?.baseline_scenario ? (
                  <div className="mt-3 rounded-[0.9rem] border border-black/8 bg-white px-3 py-2 text-xs leading-6 text-slate-700">
                    {ping.trade_impact.baseline_scenario}
                  </div>
                ) : null}
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  {ping?.trade_impact?.action ? (
                    <span className={`rounded-full px-2 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] ${actionTone(ping.trade_impact.action)}`}>
                      {ping.trade_impact.action}
                    </span>
                  ) : null}
                  {ping.symbols?.slice(0, 3).map((symbol: string) => (
                    <button
                      key={symbol}
                      onClick={() => onAnalyze(symbol)}
                      className="rounded-full border border-[var(--accent)]/20 bg-[var(--accent-soft)] px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-[var(--accent)]"
                    >
                      Analyze {symbol}
                    </button>
                  ))}
                  {ping.hedgeCandidates?.[0] ? (
                    <button
                      onClick={() => onAnalyze(ping.hedgeCandidates[0])}
                      className="rounded-full border border-black/8 bg-white px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-700"
                    >
                      Hedge {ping.hedgeCandidates[0]}
                    </button>
                  ) : null}
                </div>
                {ping?.trade_impact?.trigger || ping?.trade_impact?.invalidation ? (
                  <div className="mt-3 space-y-2 text-xs text-slate-500">
                    {ping.trade_impact?.trigger ? (
                      <div className="rounded-[0.9rem] border border-black/8 bg-white px-3 py-2">
                        Trigger: {ping.trade_impact.trigger}
                      </div>
                    ) : null}
                    {ping.trade_impact?.invalidation ? (
                      <div className="rounded-[0.9rem] border border-black/8 bg-white px-3 py-2">
                        Invalidation: {ping.trade_impact.invalidation}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ))
          ) : (
            <div className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4 text-sm text-slate-500 xl:col-span-2">
              Keine Event-Pings im aktuellen Filter.
            </div>
          )}
        </div>
      </section>

      <section className="surface-panel rounded-[2rem] p-5">
        <div className="flex items-center justify-between gap-3">
          <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
            Portfolio Brain
          </div>
          <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
            personal exposure
          </div>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <div className="rounded-[1.2rem] border border-red-500/10 bg-red-500/5 p-4">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
              At Risk
            </div>
            <div className="mt-2 text-2xl font-black text-slate-900">
              {brief.portfolio_brain?.summary?.at_risk || 0}
            </div>
          </div>
          <div className="rounded-[1.2rem] border border-emerald-500/10 bg-emerald-500/5 p-4">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
              Beneficiaries
            </div>
            <div className="mt-2 text-2xl font-black text-slate-900">
              {brief.portfolio_brain?.summary?.beneficiaries || 0}
            </div>
          </div>
          <div className="rounded-[1.2rem] border border-sky-500/10 bg-sky-500/5 p-4">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
              Hedge Ideas
            </div>
            <div className="mt-2 text-2xl font-black text-slate-900">
              {brief.portfolio_brain?.summary?.hedges || 0}
            </div>
          </div>
        </div>
        <div className="mt-4 grid gap-3 xl:grid-cols-2">
          {(brief.portfolio_brain?.actions || []).length ? (
            (brief.portfolio_brain.actions || []).map((item: any, index: number) => (
              <div
                key={`${item.ticker}-${item.title}-${index}`}
                className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <button
                    onClick={() => onAnalyze(item.ticker)}
                    className="text-sm font-black text-slate-900"
                  >
                    {item.ticker}
                  </button>
                  <div className="flex flex-wrap gap-2">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${actionTone(item.portfolio_action)}`}>
                      {item.portfolio_action}
                    </span>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${exposureTone(item.exposure_strength)}`}>
                      {item.exposure_strength || "watch"}
                    </span>
                  </div>
                </div>
                <div className="mt-2 text-sm font-bold text-slate-900">{item.title}</div>
                <div className="mt-2 text-sm text-slate-600">{item.reason}</div>
                {item.trigger ? (
                  <div className="mt-2 text-xs text-slate-500">
                    Trigger: {item.trigger}
                  </div>
                ) : null}
                {(item.hedge_candidates || []).length ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {(item.hedge_candidates || []).slice(0, 3).map((hedge: any, hedgeIndex: number) => (
                      <button
                        key={`${item.ticker}-hedge-${hedge.ticker || hedgeIndex}`}
                        onClick={() => hedge.ticker && onAnalyze(hedge.ticker)}
                        className="rounded-full border border-black/8 bg-white px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-600"
                      >
                        {hedge.ticker} - {hedge.label}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            ))
          ) : (
            <div className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4 text-sm text-slate-500 xl:col-span-2">
              Noch kein direkter Portfolio-Bezug aus dem aktuellen Brief. Sobald ein Event echte Holdings oder Held-Sektoren trifft, erscheinen hier konkrete `add`, `reduce` oder `hedge`-Hinweise.
            </div>
          )}
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-[1fr_1fr]">
        <div className="surface-panel rounded-[2rem] p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Contrarian Signals
            </div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
              media fade
            </div>
          </div>
          <div className="mt-4 space-y-3">
            {(brief.contrarian_signals || []).length ? (
              (brief.contrarian_signals || []).slice(0, 6).map((item: any, index: number) => (
                <div
                  key={`${item.ticker}-${index}`}
                  className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4"
                >
                  <div className="flex items-center justify-between gap-3">
                    <button
                      onClick={() => item.ticker && onAnalyze(item.ticker)}
                      className="text-sm font-black text-slate-900"
                    >
                      {item.ticker}
                    </button>
                    <div
                      className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${
                        item.contrarian_bias === "long"
                          ? "bg-emerald-500/10 text-emerald-700"
                          : "bg-red-500/10 text-red-700"
                      }`}
                    >
                      inverse {item.contrarian_bias}
                    </div>
                  </div>
                  <div className="mt-2 text-xs text-slate-500">
                    {item.publisher} · {item.region} · score {item.score}
                  </div>
                  <div className="mt-2 text-sm font-bold text-slate-900">{item.title}</div>
                  <div className="mt-2 text-sm text-slate-600">{item.reason}</div>
                </div>
              ))
            ) : (
              <div className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4 text-sm text-slate-500">
                Keine kontraeren Medien-Signale mit technischer Bestaetigung. Aktuell gibt es also keinen sauberen Fade- oder Inverse-Media-Trigger.
              </div>
            )}
          </div>
        </div>

        <div className="surface-panel rounded-[2rem] p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Economic Calendar
            </div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
              Today
            </div>
          </div>
          <div className="mt-4 space-y-3">
            {(brief.economic_calendar || []).slice(0, 6).map((item: any, index: number) => (
              <div
                key={`${item.title}-${index}`}
                className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="text-xs font-extrabold uppercase tracking-[0.18em] text-slate-500">
                    {item.region} · {item.category}
                  </div>
                  <div className="text-[11px] font-bold text-slate-500">
                    {new Date(item.scheduled_for).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </div>
                </div>
                <div className="mt-2 text-sm font-bold text-slate-900">{item.title}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="surface-panel rounded-[2rem] p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Earnings Calendar
            </div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
              21 days
            </div>
          </div>
          <div className="mt-4 space-y-3">
            {(brief.earnings_calendar || []).length ? (
              (brief.earnings_calendar || []).slice(0, 6).map((item: any, index: number) => (
                <div
                  key={`${item.ticker}-${index}`}
                  className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4"
                >
                  <div className="flex items-center justify-between gap-3">
                    <button
                      onClick={() => onAnalyze(item.ticker)}
                      className="text-sm font-black text-slate-900"
                    >
                      {item.ticker}
                    </button>
                    <div className="text-[11px] font-bold uppercase text-slate-500">
                      {item.session}
                    </div>
                  </div>
                  <div className="mt-2 text-xs text-slate-500">{item.company}</div>
                  <div className="mt-2 text-xs font-bold uppercase tracking-[0.16em] text-slate-500">
                    {new Date(item.scheduled_for).toLocaleDateString()} · {item.region}
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4 text-sm text-slate-500">
                Keine nahen Earnings aus Watchlist und Leitwerten gefunden.
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="surface-panel rounded-[2rem] p-5">
        <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
          Watchlist Impact
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {brief.watchlist_impact?.length ? (
            brief.watchlist_impact.map((item: any, index: number) => (
              <div
                key={`${item.ticker}-${index}`}
                className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4"
              >
                <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                  {item.type}
                </div>
                <div className="mt-2 text-sm font-bold text-slate-900">{item.summary}</div>
              </div>
            ))
          ) : (
            <div className="text-sm text-slate-500">
              Keine direkten Watchlist-Auswirkungen im aktuellen Brief.
            </div>
          )}
        </div>
      </section>
      {/* ── Reddit Hot Posts ─────────────────────────────────────────── */}
      {(brief.reddit_posts || []).length > 0 && (
        <section className="surface-panel rounded-[2rem] p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Reddit Pulse
            </div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
              WSB · r/stocks · r/investing
            </div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {(brief.reddit_posts || []).slice(0, 8).map((post: any, i: number) => {
              const sentimentColor =
                post.sentiment === "bullish"
                  ? "bg-emerald-500/10 text-emerald-700"
                  : post.sentiment === "bearish"
                    ? "bg-red-500/10 text-red-700"
                    : "bg-slate-500/10 text-slate-600";
              return (
                <a
                  key={`reddit-${i}`}
                  href={post.url}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4 transition-colors hover:bg-white"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                      {post.subreddit}
                    </span>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${sentimentColor}`}>
                      {post.sentiment || "neutral"}
                    </span>
                  </div>
                  <div className="mt-2 text-sm font-bold text-slate-900 line-clamp-2">
                    {post.title}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-500">
                    <span>⬆ {post.score}</span>
                    <span>💬 {post.num_comments}</span>
                    {(post.ticker_matches || []).length > 0 && (
                      <span className="font-bold text-slate-700">
                        ${(post.ticker_matches || []).slice(0, 3).join(" $")}
                      </span>
                    )}
                  </div>
                </a>
              );
            })}
          </div>
        </section>
      )}

      {/* ── Stocktwits Sentiment ──────────────────────────────────────── */}
      {(brief.stocktwits || []).length > 0 && (
        <section className="surface-panel rounded-[2rem] p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Stocktwits Sentiment
            </div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
              Retail flow
            </div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {(brief.stocktwits || []).map((st: any, i: number) => {
              const bull = st.bull_ratio || 50;
              const barColor =
                bull >= 60
                  ? "bg-emerald-500"
                  : bull <= 40
                    ? "bg-red-500"
                    : "bg-amber-400";
              return (
                <div
                  key={`st-${st.ticker || i}`}
                  className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4"
                >
                  <div className="flex items-center justify-between gap-2">
                    <button
                      onClick={() => st.ticker && onAnalyze(st.ticker)}
                      className="text-sm font-black text-slate-900"
                    >
                      {st.ticker}
                    </button>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${
                      st.sentiment_label === "bullish"
                        ? "bg-emerald-500/10 text-emerald-700"
                        : st.sentiment_label === "bearish"
                          ? "bg-red-500/10 text-red-700"
                          : "bg-slate-500/10 text-slate-600"
                    }`}>
                      {st.sentiment_label || "neutral"}
                    </span>
                  </div>
                  <div className="mt-3">
                    <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                      <span>🐻 {st.bearish_count || 0}</span>
                      <span>{bull}% bull</span>
                      <span>🐂 {st.bullish_count || 0}</span>
                    </div>
                    <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-100">
                      <div className={`h-full rounded-full ${barColor}`} style={{ width: `${bull}%` }} />
                    </div>
                  </div>
                  <div className="mt-2 text-[10px] text-slate-500">
                    {st.message_count || 0} messages
                  </div>
                  {(st.top_messages || []).slice(0, 1).map((msg: any, mi: number) => (
                    <div key={mi} className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-xs italic text-slate-600 line-clamp-2">
                      {msg.text}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* ── Polymarket Prediction Markets ─────────────────────────────── */}
      <section className="surface-panel rounded-[2rem] p-5">
        <div className="flex items-center justify-between gap-3">
          <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
            Prediction Markets
          </div>
          <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
            Polymarket
          </div>
        </div>
        {(brief.prediction_signals || []).length > 0 ? (
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {(brief.prediction_signals || []).slice(0, 8).map((pm: any, i: number) => {
              const probabilityRaw = Number(pm.probability);
              const probability = Number.isFinite(probabilityRaw)
                ? (probabilityRaw > 1 ? probabilityRaw / 100 : probabilityRaw)
                : null;
              const prob = probability != null ? Math.round(probability * 100) : null;
              return (
                <div
                  key={`pm-signal-${i}`}
                  className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4"
                >
                  <div className="text-sm font-bold text-slate-900 line-clamp-2">
                    {pm.market}
                  </div>
                  <div className="mt-3 flex items-center gap-3">
                    {prob != null && (
                      <div className="flex items-center gap-2">
                        <div className="h-2 w-16 overflow-hidden rounded-full bg-slate-100">
                          <div
                            className={`h-full rounded-full ${prob >= 70 ? "bg-emerald-500" : prob <= 30 ? "bg-red-500" : "bg-amber-400"}`}
                            style={{ width: `${prob}%` }}
                          />
                        </div>
                        <span className="text-sm font-black text-slate-900">{prob}%</span>
                      </div>
                    )}
                    <span className="rounded-full border border-black/8 bg-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                      relevance {pm.relevance ?? "n/a"}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="mt-4 rounded-[1rem] border border-amber-500/20 bg-amber-500/10 p-3 text-sm text-amber-700">
            Polymarket-Daten aktuell verzoegert. Abschnitt bleibt sichtbar und wird automatisch wieder aktualisiert.
          </div>
        )}
      </section>

      {(brief.polymarket || []).length > 0 && (
        <section className="surface-panel rounded-[2rem] p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Prediction Markets
            </div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
              Polymarket
            </div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {(brief.polymarket || []).slice(0, 8).map((pm: any, i: number) => {
              const probabilityRaw = Number(pm.probability_yes);
              const probability = Number.isFinite(probabilityRaw)
                ? (probabilityRaw > 1 ? probabilityRaw / 100 : probabilityRaw)
                : null;
              const prob = probability != null ? Math.round(probability * 100) : null;
              const vol = pm.volume_usd ? `$${(pm.volume_usd / 1e6).toFixed(1)}M` : null;
              return (
                <a
                  key={`pm-${i}`}
                  href={pm.url}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4 transition-colors hover:bg-white"
                >
                  <div className="text-sm font-bold text-slate-900 line-clamp-2">
                    {pm.question}
                  </div>
                  <div className="mt-3 flex items-center gap-3">
                    {prob != null && (
                      <div className="flex items-center gap-2">
                        <div className="h-2 w-16 overflow-hidden rounded-full bg-slate-100">
                          <div
                            className={`h-full rounded-full ${prob >= 70 ? "bg-emerald-500" : prob <= 30 ? "bg-red-500" : "bg-amber-400"}`}
                            style={{ width: `${prob}%` }}
                          />
                        </div>
                        <span className="text-sm font-black text-slate-900">{prob}%</span>
                      </div>
                    )}
                    {vol && (
                      <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                        Vol {vol}
                      </span>
                    )}
                  </div>
                  {pm.end_date && (
                    <div className="mt-2 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                      Ends {pm.end_date}
                    </div>
                  )}
                </a>
              );
            })}
          </div>
        </section>
      )}

      {/* ── Google News Extra ─────────────────────────────────────────── */}
      {(brief.google_news_extra || []).length > 0 && (
        <section className="surface-panel rounded-[2rem] p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Google News
            </div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
              Watchlist + Macro
            </div>
          </div>
          <div className="mt-4 space-y-3">
            {(brief.google_news_extra || []).slice(0, 8).map((item: any, i: number) => (
              <a
                key={`gn-${i}`}
                href={item.link}
                target="_blank"
                rel="noreferrer"
                className="flex items-center justify-between rounded-[1.2rem] border border-black/8 bg-white/70 p-4 transition-colors hover:bg-white"
              >
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-bold text-slate-900 line-clamp-1">
                    {item.title}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-2 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                    {item.publisher && <span>{item.publisher}</span>}
                    {item.query && (
                      <span className="rounded-full border border-black/8 bg-white px-2 py-0.5">
                        {item.query}
                      </span>
                    )}
                  </div>
                </div>
                {item.age_hours != null && (
                  <div className="ml-3 shrink-0 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">
                    {item.age_hours < 1 ? "< 1h" : `${Math.round(item.age_hours)}h ago`}
                  </div>
                )}
              </a>
            ))}
          </div>
        </section>
      )}

      {/* ── Broad Earnings Calendar ───────────────────────────────────── */}
      {(brief.earnings_results || []).length > 0 && (
        <section className="surface-panel rounded-[2rem] p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Earnings Results
            </div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
              beat / miss / guidance
            </div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {(brief.earnings_results || []).slice(0, 6).map((item: any, i: number) => (
              <div
                key={`er-${item.ticker}-${i}`}
                className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4"
              >
                <div className="flex items-center justify-between gap-2">
                  <button
                    onClick={() => onAnalyze(item.ticker)}
                    className="text-sm font-black text-slate-900"
                  >
                    {item.ticker}
                  </button>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${
                    item.status === "beat"
                      ? "bg-emerald-500/10 text-emerald-700"
                      : item.status === "miss"
                        ? "bg-red-500/10 text-red-700"
                        : "bg-amber-500/10 text-amber-700"
                  }`}>
                    {item.status}
                  </span>
                </div>
                <div className="mt-1 line-clamp-1 text-xs text-slate-500">{item.company}</div>
                <div className="mt-3 grid grid-cols-2 gap-2 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                  <div className="rounded-xl border border-black/8 bg-white px-3 py-2">
                    EPS {item.reported_eps != null ? item.reported_eps.toFixed(2) : "n/a"}
                  </div>
                  <div className="rounded-xl border border-black/8 bg-white px-3 py-2">
                    Est {item.eps_estimate != null ? item.eps_estimate.toFixed(2) : "n/a"}
                  </div>
                  <div className="rounded-xl border border-black/8 bg-white px-3 py-2">
                    Surprise {item.eps_surprise_pct != null ? `${item.eps_surprise_pct >= 0 ? "+" : ""}${item.eps_surprise_pct.toFixed(1)}%` : "n/a"}
                  </div>
                  <div className="rounded-xl border border-black/8 bg-white px-3 py-2">
                    Revenue {item.revenue_yoy != null ? `${item.revenue_yoy >= 0 ? "+" : ""}${(item.revenue_yoy * 100).toFixed(1)}%` : "n/a"}
                  </div>
                </div>
                {item.guidance_label && (
                  <div className={`mt-3 rounded-[0.95rem] border px-3 py-2 text-[11px] font-bold ${
                    item.guidance_sentiment === "positive"
                      ? "border-emerald-500/20 bg-emerald-500/8 text-emerald-700"
                      : item.guidance_sentiment === "negative"
                        ? "border-red-500/20 bg-red-500/8 text-red-700"
                        : "border-black/8 bg-white text-slate-600"
                  }`}>
                    {item.guidance_label}
                  </div>
                )}
                <div className="mt-3 text-xs leading-6 text-slate-600">{item.summary}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {(brief.broad_earnings || []).length > 0 && (
        <section className="surface-panel rounded-[2rem] p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Upcoming Earnings
            </div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
              S&P 500 + Watchlist
            </div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {(brief.broad_earnings || []).slice(0, 12).map((item: any, i: number) => (
              <div
                key={`be-${item.ticker}-${i}`}
                className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4"
              >
                <div className="flex items-center justify-between gap-2">
                  <button
                    onClick={() => onAnalyze(item.ticker)}
                    className="text-sm font-black text-slate-900"
                  >
                    {item.ticker}
                  </button>
                  <div className="flex gap-2">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${
                      item.importance === "watchlist"
                        ? "bg-sky-500/10 text-sky-700"
                        : "bg-slate-500/10 text-slate-600"
                    }`}>
                      {item.importance}
                    </span>
                    <span className="rounded-full border border-black/8 bg-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                      {item.session}
                    </span>
                  </div>
                </div>
                <div className="mt-2 text-xs text-slate-500 line-clamp-1">{item.company}</div>
                <div className="mt-2 flex items-center justify-between text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                  <span>{item.date ? new Date(item.date).toLocaleDateString() : ""}</span>
                  {item.days_until != null && (
                    <span className={item.days_until <= 2 ? "text-amber-700" : ""}>
                      {item.days_until === 0 ? "Today" : item.days_until === 1 ? "Tomorrow" : `in ${item.days_until}d`}
                    </span>
                  )}
                </div>
                {item.eps_estimate != null && (
                  <div className="mt-1 text-[10px] text-slate-500">
                    EPS est. {item.eps_estimate.toFixed(2)}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
