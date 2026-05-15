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
    return { icon: "↘", bg: "bg-red-500/[0.065]", text: "text-red-700", border: "border-red-500/16" };
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

function newsForecastMeta(item: any) {
  const text = `${item?.title || ""} ${item?.headline || ""} ${item?.event_type || ""} ${item?.direction_hint || ""}`.toLowerCase();
  const impact = String(item?.impact || "").toLowerCase();
  const severity = String(item?.severity || "").toLowerCase();
  const eventType = String(item?.event_type || "").toLowerCase();
  const productDirection = String(item?.product_catalyst?.direction_hint || item?.direction_hint || "").toLowerCase();

  const negative =
    productDirection === "negative" ||
    severity === "critical" ||
    /risk-off|missile|attack|war|sanction|tariff|downgrade|delay|delayed|postpone|cuts guidance|recession|default/.test(text);
  const positive =
    productDirection === "positive_watch" ||
    /risk-on|upgrade|beat|beats|raises guidance|launch|unveil|approval|record high|deal|partnership|stimulus|rate cut/.test(text);

  if (negative && !positive) {
    return {
      direction: "down",
      arrow: "↓",
      label: "Prognose runter",
      short: "Risk-off",
      copy: eventType === "product_catalyst"
        ? "Erste Reaktion eher negativ, bis Produkt-/Preisfolge bestaetigt ist."
        : "Erste Reaktion eher defensiv. Bestaetigung ueber Futures, Renditen und Volumen abwarten.",
      className: "border-red-500/18 bg-red-500/[0.07] text-red-800",
      arrowClass: "bg-red-500 text-white",
    };
  }

  if (positive && !negative) {
    return {
      direction: "up",
      arrow: "↑",
      label: "Prognose hoch",
      short: "Risk-on",
      copy: impact === "high"
        ? "Erste Reaktion konstruktiv, aber nur mit Preis- und Volumenbestaetigung handeln."
        : "Leicht positiver Impuls. Fuer Setup erst Marktbreite und Folge-News pruefen.",
      className: "border-emerald-500/18 bg-emerald-500/[0.075] text-emerald-800",
      arrowClass: "bg-emerald-500 text-white",
    };
  }

  return {
    direction: "neutral",
    arrow: "→",
    label: "Prognose neutral",
    short: "Abwarten",
    copy: "Noch kein sauberer Richtungsvorteil. Erst bestaetigen, dann in Analyzer oder Markets vertiefen.",
    className: "border-slate-300 bg-white/68 text-slate-700",
    arrowClass: "bg-slate-900 text-white",
  };
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

function setupBucketTone(bucket: "now" | "next" | "avoid" | "data_missing") {
  if (bucket === "now") return "border-emerald-500/16 bg-emerald-500/5 text-emerald-700";
  if (bucket === "avoid") return "brief-avoid-soft border-red-500/14 text-red-700";
  if (bucket === "data_missing") return "border-sky-500/15 bg-sky-500/[0.06] text-sky-800";
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

function catalystTypeLabel(type?: string) {
  const t = String(type || "product_news").toLowerCase();
  if (t === "watch_fallback") return "Watch Radar";
  if (t === "launch") return "Launch Watch";
  if (t === "delay") return "Delay Risk";
  return t.replace("_", " ");
}

function catalystStatusCopy(status?: string) {
  const s = String(status || "").toLowerCase();
  if (s === "no_fresh_headline") return "Kein frischer Headline-Trigger. Nur beobachten.";
  if (s === "watch_fallback") return "Makro-/Produkt-Watch, noch kein Trade-Signal.";
  return "";
}

function pingStatusCopy(status?: string) {
  const s = String(status || "").toLowerCase();
  if (s === "watch_fallback") return "Watch-Fallback: kein harter Event-Ping, aber relevanter Markt-Proxy.";
  return "";
}

function sourceLabel(source: string) {
  const labels: Record<string, string> = {
    reddit: "Reddit",
    stocktwits: "Stocktwits",
    polymarket: "Polymarket",
    google_news: "Google News",
    google_news_extra: "Google News",
    earnings_calendar: "Earnings Kalender",
    broad_earnings: "Earnings Kalender",
    earnings_results: "Earnings Results",
    market_movers: "Market Movers",
    deep_social: "Social Deep Scan",
  };
  return labels[source] || source.replace(/_/g, " ");
}

function sourceStateMeta(state: unknown) {
  const text = String(state || "unknown").toLowerCase();
  if (text === "loaded") {
    return {
      label: "geladen",
      detail: "Datenquelle ist aktiv im aktuellen Briefing.",
      className: "border-emerald-500/20 bg-emerald-500/10 text-emerald-700",
    };
  }
  if (text.includes("deferred")) {
    return {
      label: "laedt nach",
      detail: "Fast Mode: Quelle wird nach dem ersten Briefing nachgeladen.",
      className: "border-sky-500/20 bg-sky-500/10 text-sky-700",
    };
  }
  if (text.includes("no_recent")) {
    return {
      label: "keine frischen Treffer",
      detail: "Quelle funktioniert, aber im aktuellen Fenster gab es keinen relevanten Treffer.",
      className: "border-slate-300 bg-white/65 text-slate-500",
    };
  }
  if (text.includes("empty") || text.includes("unavailable")) {
    return {
      label: "leer / nicht verfuegbar",
      detail: "Quelle lieferte gerade keine verwertbaren Daten oder ist temporaer nicht erreichbar.",
      className: "border-amber-500/20 bg-amber-500/10 text-amber-700",
    };
  }
  return {
    label: text.replace(/_/g, " "),
    detail: `Status: ${text.replace(/_/g, " ")}`,
    className: "border-slate-300 bg-white/65 text-slate-500",
  };
}

function extractTickerCandidates(text?: string) {
  if (!text) return [];
  const matches = text.match(/\b[A-Z]{1,5}(?:-[A-Z]{1,5})?\b/g) || [];
  return [...new Set(matches)];
}

function moveLabel(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return "offen";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function openValue(value: unknown, fallback = "offen"): string | number {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value !== "string" && typeof value !== "number") return fallback;
  const text = String(value);
  if (text.toLowerCase() === "n/a" || text.toLowerCase() === "unknown") return fallback;
  return value;
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
  const deferredLayers = Array.isArray(quality?.deferred) ? quality.deferred : [];
  const sourceStates = quality?.sources && typeof quality.sources === "object" ? quality.sources : {};

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
  const futureStars = Array.isArray(brief.future_stars) ? brief.future_stars.slice(0, 5) : [];
  const setupBoard = brief.setup_board || { now: [], next: [], avoid: [] };
  const playbookSummary = brief.playbook_summary || {};
  const dataHealth = brief.data_health || {};
  const missingSignalReasons = Array.isArray(brief.missing_signal_reasons) ? brief.missing_signal_reasons : [];
  const earningsRows = (
    Array.isArray(brief.earnings_calendar) && brief.earnings_calendar.length
      ? brief.earnings_calendar
      : Array.isArray(brief.broad_earnings)
        ? brief.broad_earnings
        : []
  ).slice(0, 6);
  const earningsResultCount = Array.isArray(brief.earnings_results) ? brief.earnings_results.length : 0;
  const upcomingEarningsCount = Array.isArray(brief.broad_earnings) ? brief.broad_earnings.length : 0;
  const watchlistImpactCount = Array.isArray(brief.watchlist_impact) ? brief.watchlist_impact.length : 0;
  const watchedPredictionThemes = Array.isArray(brief.prediction_markets?.watched_themes)
    ? brief.prediction_markets.watched_themes.slice(0, 4)
    : [];
  const hasPredictionSignals = Array.isArray(brief.prediction_signals) && brief.prediction_signals.length > 0;
  const hasPolymarketMarkets = Array.isArray(brief.polymarket) && brief.polymarket.length > 0;
  const predictionStatus = brief.prediction_markets?.status || (hasPolymarketMarkets ? "market-feed" : "fast-mode");
  const predictionMessage =
    brief.prediction_markets?.message ||
    (hasPolymarketMarkets
      ? "Polymarket-Maerkte sind geladen; noch kein Signal hat die Relevanz- und Confidence-Schwelle fuer das Briefing erreicht."
      : "Polymarket-Livefeed wird nachgeladen; relevante Makro-Themen bleiben im Watch-Modus.");
  const watchlistImpactFallback = watchedPredictionThemes.map((theme: any) => ({
    type: "macro watch",
    summary: `${theme.theme}: ${theme.why}`,
  }));

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
                {qualityReady ? "Brief Ready" : "Brief Partial"} / {quality.score}/100
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
                Datenluecken: {quality.missing.slice(0, 3).join(" / ")}
              </div>
            ) : null}
            {deferredLayers.length ? (
              <div className="mt-2 rounded-[0.9rem] border border-sky-500/20 bg-sky-500/8 px-3 py-2 text-[11px] text-sky-800">
                Fast Mode: {deferredLayers.slice(0, 4).join(" / ")} werden nachgeladen.
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

      <section className="surface-panel rounded-[1.6rem] p-4">
        <div className="flex flex-wrap items-center gap-2">
          {[
            {
              label: "Earnings Results",
              value: earningsResultCount,
              status: earningsResultCount ? "loaded" : "no fresh results",
              tone: earningsResultCount ? "text-emerald-700 bg-emerald-500/10" : "text-slate-500 bg-slate-500/10",
            },
            {
              label: "Upcoming Earnings",
              value: upcomingEarningsCount,
              status: upcomingEarningsCount ? "loaded" : "none in focus window",
              tone: upcomingEarningsCount ? "text-emerald-700 bg-emerald-500/10" : "text-slate-500 bg-slate-500/10",
            },
            {
              label: "Watchlist Impact",
              value: watchlistImpactCount,
              status: watchlistImpactCount ? "direct hits" : "no direct hits",
              tone: watchlistImpactCount ? "text-sky-700 bg-sky-500/10" : "text-slate-500 bg-slate-500/10",
            },
            {
              label: "Polymarket",
              value: hasPredictionSignals ? brief.prediction_signals.length : hasPolymarketMarkets ? brief.polymarket.length : 0,
              status: hasPredictionSignals ? "signals passed" : hasPolymarketMarkets ? "confidence gate" : predictionStatus,
              tone: hasPredictionSignals ? "text-emerald-700 bg-emerald-500/10" : hasPolymarketMarkets ? "text-sky-700 bg-sky-500/10" : "text-amber-700 bg-amber-500/10",
            },
          ].map((item) => (
            <div
              key={item.label}
              className="rounded-[1rem] border border-black/8 bg-white/72 px-3 py-2"
            >
              <div className="text-[9px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                {item.label}
              </div>
              <div className="mt-1 flex items-center gap-2">
                <span className="text-sm font-black text-slate-900">{item.value}</span>
                <span className={`rounded-full px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.12em] ${item.tone}`}>
                  {item.status}
                </span>
              </div>
            </div>
          ))}
        </div>
        {Object.keys(sourceStates).length ? (
          <div className="mt-3 rounded-[1.2rem] border border-black/6 bg-white/55 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                Datenquellen Status
              </div>
              <div className="text-[10px] font-semibold text-slate-400">
                zeigt, warum einzelne Sektionen leer oder verzögert sind
              </div>
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
            {Object.entries(sourceStates).slice(0, 8).map(([source, state]) => {
              const meta = sourceStateMeta(state);
              return (
                <span
                  key={source}
                  className={`rounded-full border px-2.5 py-1 text-[9px] font-extrabold uppercase tracking-[0.12em] ${meta.className}`}
                  title={`${sourceLabel(source)}: ${meta.detail}`}
                >
                  {sourceLabel(source)} / {meta.label}
                </span>
              );
            })}
            </div>
            <div className="mt-2 text-[11px] leading-5 text-slate-500">
              Grün bedeutet: im Brief aktiv. Blau bedeutet: Fast-Mode lädt nach. Gelb/Grau bedeutet: Quelle war erreichbar,
              aber ohne verwertbaren Treffer oder temporär leer.
            </div>
          </div>
        ) : null}
      </section>

      {futureStars.length > 0 && (
        <section className="surface-panel rounded-[2rem] p-6">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-emerald-700">
                Future Stars Briefing
              </div>
              <h3 className="mt-2 text-2xl text-slate-900">
                Kleine Werte erst nach News-, Umsatz- und Risiko-Check
              </h3>
            </div>
            <div className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1 text-xs font-bold text-emerald-700">
              {futureStars.filter((item: any) => item.quality_gate === "passed").length} passed
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            {futureStars.map((item: any) => (
              <button
                key={item.ticker}
                onClick={() => item.ticker && onAnalyze(item.ticker)}
                className="rounded-[1.15rem] border border-black/8 bg-white/75 p-4 text-left transition-all hover:-translate-y-0.5"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-lg font-black text-slate-900">{item.ticker}</span>
                  <span className="text-xs font-black text-emerald-700">{item.score}/100</span>
                </div>
                <div className="mt-1 truncate text-xs font-semibold text-slate-500">{item.name}</div>
                <div className="mt-3 text-xs font-bold text-slate-700">
                  {item.revenue_growth != null ? `${Number(item.revenue_growth).toFixed(1)}% Umsatz` : "Umsatz n/a"}
                </div>
                <p className="mt-2 line-clamp-3 text-xs leading-5 text-slate-500">{item.catalyst}</p>
              </button>
            ))}
          </div>
        </section>
      )}

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
              {productCatalysts.length ? productCatalysts.map((item: any) => {
                const statusCopy = catalystStatusCopy(item.source_status);
                return (
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
                      {catalystTypeLabel(item.catalyst_type)}
                    </span>
                  </div>
                  <div className="mt-2 text-sm font-bold text-slate-900">{item.theme}</div>
                  <div className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{item.title}</div>
                  {statusCopy ? (
                    <div className="mt-2 rounded-[0.8rem] border border-amber-500/20 bg-amber-500/8 px-3 py-2 text-[11px] font-semibold text-amber-800">
                      {statusCopy}
                    </div>
                  ) : null}
                  {item.trigger || item.invalidation ? (
                    <div className="mt-2 grid gap-2 text-[11px] leading-5 text-slate-500">
                      {item.trigger ? (
                        <div className="rounded-[0.8rem] border border-black/8 bg-white px-3 py-2">
                          Trigger: {item.trigger}
                        </div>
                      ) : null}
                      {item.invalidation ? (
                        <div className="rounded-[0.8rem] border border-black/8 bg-white px-3 py-2">
                          Invalidierung: {item.invalidation}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
                );
              }) : (
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
                      {asset.ticker}{live?.price != null ? ` / ${live.price}` : ""}
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
              Trading Playbook
            </div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
              {dataHealth.status || "ready"}
            </div>
          </div>
          <div className="mt-2 text-xs leading-5 text-slate-500">
            {playbookSummary.message || "Now, Next, Avoid und Datenluecken zeigen, wo heute echte Edge oder Zurueckhaltung noetig ist."}
          </div>
          <div className="mt-4 grid gap-3">
            {(["now", "next", "avoid", "data_missing"] as const).map((bucket) => {
              const rows = bucket === "data_missing" ? [] : setupBoard[bucket] || [];
              const title = bucket === "now" ? "Now" : bucket === "next" ? "Next" : bucket === "avoid" ? "Avoid" : "Data Missing";
              const tone = bucket === "data_missing" ? "border-sky-500/15 bg-sky-500/[0.06] text-sky-800" : setupBucketTone(bucket);
              return (
                <div key={bucket} className={`rounded-[1.2rem] border p-4 ${tone}`}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-[11px] font-extrabold uppercase tracking-[0.18em]">
                      {title}
                    </div>
                    <div className="text-[10px] font-bold uppercase tracking-[0.14em] opacity-70">
                      {bucket === "data_missing" ? `${missingSignalReasons.length} Hinweise` : `${rows.length} Setups`}
                    </div>
                  </div>
                  <div className="mt-3 space-y-2">
                    {bucket === "data_missing" ? (
                      missingSignalReasons.length ? missingSignalReasons.slice(0, 3).map((reason: string, idx: number) => (
                        <div key={`missing-${idx}`} className="rounded-[1rem] border border-black/8 bg-white/80 p-3 text-sm text-slate-600">
                          {reason}
                        </div>
                      )) : (
                        <div className="rounded-[1rem] border border-black/8 bg-white/80 p-3 text-sm text-slate-500">
                          Keine kritischen Datenluecken im aktuellen Brief.
                        </div>
                      )
                    ) : rows.length ? rows.slice(0, 3).map((item: any, idx: number) => (
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
              Top Setups
            </div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
              Trigger zuerst
            </div>
          </div>
          <div className="mt-2 text-xs leading-5 text-slate-500">
            Erst Einstieg, Ungueltig-wenn und Zeitfenster pruefen. Analyse nur starten, wenn die Kursreaktion dazu passt.
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
                      Score {openValue(setup.rank_score)}
                    </span>
                    <span className="rounded-full border border-black/8 bg-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                      Konfidenz {setup.confidence}
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
                    Learning-Bias {Number(setup.learning_adjustment.score_delta) > 0 ? "+" : ""}
                    {setup.learning_adjustment.score_delta}: {setup.learning_adjustment.reason}
                  </div>
                ) : null}
                <div className="mt-2 grid gap-2 text-xs text-slate-500 sm:grid-cols-2">
                  <div>Einstieg: {setup.trigger}</div>
                  <div>Zeitfenster: {setup.window}</div>
                  <div>Ungueltig wenn: {setup.invalidation}</div>
                  <div>Erwartete Bewegung: {setup.expected_move}</div>
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
                  ? "Keine belastbaren Setups: aktuell fehlt ein klarer Trigger mit genuegend Datenvertrauen."
                  : "Keine belastbaren Setups im aktuellen Feed."}
              </div>
            ) : null}
          </div>
          {(brief.learning_adjustments || []).length ? (
            <div className="mt-4 rounded-[1.2rem] border border-[var(--accent)]/14 bg-[var(--accent-soft)]/60 p-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-[var(--accent)]">
                Learning im Ranking
              </div>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                {(brief.learning_adjustments || []).slice(0, 4).map((item: any, index: number) => (
                  <div key={`${item.axis}-${item.label}-${index}`} className="rounded-[1rem] border border-black/8 bg-white/78 px-3 py-2 text-xs text-slate-700">
                    <div className="font-extrabold uppercase tracking-[0.14em] text-slate-500">
                      {item.axis}: {item.label}
                    </div>
                    <div className="mt-1">
                      Trefferquote {item.hit_rate}% / Ranking {Number(item.score_delta) > 0 ? "+" : ""}
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
              Aktionsboard
            </div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
              Weltlage
            </div>
          </div>
          <div className="mt-2 text-xs leading-5 text-slate-500">
            Makro- und Event-Ideen bleiben Watchlist-Material, bis Preis, Volumen und Datenquelle bestaetigen.
          </div>
          <div className="mt-4 space-y-3">
            {(brief.action_board || []).slice(0, 6).map((item: any, index: number) => (
              <div
                key={`${item.title}-${index}`}
                className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-xs font-extrabold uppercase tracking-[0.18em] text-slate-500">
                    {item.region} / {item.event_type} / {item.impact}
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
                      Hebel {item.leverage}
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
                    <div>Konfidenz {item.event_intelligence.confidence_score}</div>
                    <div>Verfall {item.event_intelligence.decay}</div>
                    <div>Aktion {item.event_intelligence.action}</div>
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
                  <div>Risiko: {item.risk}</div>
                </div>
                {item.event_intelligence?.invalidation ? (
                  <div className="mt-2 text-xs text-slate-500">
                    Ungueltig wenn: {item.event_intelligence.invalidation}
                  </div>
                ) : null}
                {item.event_intelligence?.execution_window ? (
                  <div className="mt-1 text-xs font-bold uppercase tracking-[0.14em] text-slate-500">
                    Zeitfenster: {item.event_intelligence.execution_window}
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
              PTR / verzoegerte offizielle Meldungen
            </div>
          </div>
          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            {(brief.congress_watch || []).length ? (
              (brief.congress_watch || []).slice(0, 5).map((item: any, index: number) => {
                const quality = String(item.setup_quality || "watch_only").toLowerCase();
                const qualityClass =
                  quality === "strong"
                    ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700"
                    : quality === "selective"
                      ? "border-amber-500/20 bg-amber-500/10 text-amber-700"
                      : "border-slate-500/15 bg-slate-500/10 text-slate-600";
                return (
                <div
                  key={`${item.name}-${item.ticker}-${index}`}
                  className="rounded-[1.25rem] border border-[var(--accent)]/16 bg-[linear-gradient(180deg,rgba(15,118,110,0.07),rgba(255,255,255,0.82))] p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                        {item.impact} impact / {item.freshness}
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
                        {openValue(item.confidence)} conf
                      </span>
                      <span className={`rounded-full border px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] ${qualityClass}`}>
                        {quality.replace("_", " ")}
                      </span>
                    </div>
                  </div>
                  <div className="mt-3 grid gap-2 text-xs text-slate-600 sm:grid-cols-2">
                    <div>Action: {item.action || item.setup}</div>
                    <div>Amount: {openValue(item.amount_range)}</div>
                    <div>Trade date: {openValue(item.trade_date)}</div>
                    <div>Delay: {item.delay_days != null ? `${item.delay_days}d` : "offen"} / {openValue(item.delay_bucket)}</div>
                  </div>
                  {item.score_explainer && (
                    <div className="mt-3 rounded-[0.9rem] border border-black/6 bg-white/65 p-2 text-xs leading-5 text-slate-600">
                      {item.score_explainer} {item.amount_note ? `Betrag: ${item.amount_note}.` : ""}
                    </div>
                  )}
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
                );
              })
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
            {(regionNews.length ? regionNews : brief.top_news || []).slice(0, 6).map((item: any, index: number) => {
              const forecast = newsForecastMeta(item);
              return (
                <a
                  key={`${item.title}-${index}`}
                  href={item.link}
                  target="_blank"
                  rel="noreferrer"
                  className="group block overflow-hidden rounded-[1.35rem] border border-black/8 bg-white/72 p-4 shadow-[0_14px_34px_rgba(15,23,42,0.055)] transition-all hover:-translate-y-0.5 hover:bg-white hover:shadow-[0_22px_48px_rgba(15,23,42,0.09)]"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs font-extrabold uppercase tracking-[0.18em] text-slate-500">
                          {item.region} / {item.impact}
                        </span>
                        <span className={`rounded-full border px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.14em] ${forecast.className}`}>
                          {forecast.label}
                        </span>
                      </div>
                      <div className="mt-2 text-sm font-black leading-5 text-slate-950">
                        {item.title}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <div className={`flex h-10 w-10 items-center justify-center rounded-[1rem] text-xl font-black shadow-[0_10px_22px_rgba(15,23,42,0.12)] ${forecast.arrowClass}`}>
                        {forecast.arrow}
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
                  </div>

                  <div className={`mt-3 rounded-[1rem] border px-3 py-2 ${forecast.className}`}>
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] opacity-75">
                        {forecast.short}
                      </div>
                      <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] opacity-65">
                        Top-News Prognose
                      </div>
                    </div>
                    <div className="mt-1 text-xs font-semibold leading-5">
                      {forecast.copy}
                    </div>
                  </div>

                  <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <span>{item.publisher}</span>
                    <span className="rounded-full border border-black/8 bg-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                      {item.source_quality || "trusted"}
                    </span>
                    {item.event_type ? (
                      <span className="rounded-full border border-black/8 bg-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                        {String(item.event_type).replace(/_/g, " ")}
                      </span>
                    ) : null}
                  </div>
                </a>
              );
            })}
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
                        {item.region} / {item.event_type}
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
                        score {openValue(item.social_score)}
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
                        {item.region} / {item.event_type}
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
                        score {openValue(item.crowd_score)}
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
                {pingStatusCopy(ping.source_status) ? (
                  <div className="mt-2 rounded-[0.9rem] border border-amber-500/20 bg-amber-500/8 px-3 py-2 text-xs font-semibold text-amber-800">
                    {pingStatusCopy(ping.source_status)}
                  </div>
                ) : null}
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
                    {item.publisher} / {item.region} / score {item.score}
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
                    {item.region} / {item.category}
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
            {earningsRows.length ? (
              earningsRows.map((item: any, index: number) => (
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
                      {item.session || item.time || "watch"}
                    </div>
                  </div>
                  <div className="mt-2 text-xs text-slate-500">{item.company || item.name || item.ticker}</div>
                  <div className="mt-2 text-xs font-bold uppercase tracking-[0.16em] text-slate-500">
                    {(item.scheduled_for || item.date) ? new Date(item.scheduled_for || item.date).toLocaleDateString() : "Datum offen"} / {item.region || item.importance || "market"}
                  </div>
                  {item.summary ? (
                    <div className="mt-2 text-xs leading-5 text-slate-500">{item.summary}</div>
                  ) : null}
                </div>
              ))
            ) : (
              <div className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4 text-sm text-slate-500">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-bold text-slate-700">Keine priorisierten Earnings im 21-Tage-Filter.</div>
                  <span className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.14em] text-amber-700">
                    no direct watch hit
                  </span>
                </div>
                <div className="mt-2 text-xs leading-5">
                  Ursache: Watchlist/Leitwerte haben aktuell keinen belastbaren Termin oder der Feed liefert nur
                  breite Kalenderdaten. Broad Earnings erscheinen weiter unten, sobald sie verfuegbar sind.
                </div>
                <div className="mt-3 grid gap-2 sm:grid-cols-3">
                  {["Watchlist wird weiter gescannt", "Heute gemeldete Beats/Misses erscheinen separat", "Buddy kann Earnings-Luecken erklaeren"].map((copy) => (
                    <div key={copy} className="rounded-[0.8rem] border border-black/8 bg-white/70 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">
                      {copy}
                    </div>
                  ))}
                </div>
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
          {(brief.watchlist_impact?.length ? brief.watchlist_impact : watchlistImpactFallback).length ? (
            (brief.watchlist_impact?.length ? brief.watchlist_impact : watchlistImpactFallback).map((item: any, index: number) => (
              <div
                key={`${item.ticker || item.type}-${index}`}
                className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4"
              >
                <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                  {item.type}
                </div>
                <div className="mt-2 text-sm font-bold text-slate-900">{item.summary}</div>
              </div>
            ))
          ) : (
            <div className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4 text-sm text-slate-500">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-bold text-slate-700">Kein direkter Watchlist-Treffer.</div>
                <span className="rounded-full border border-slate-300 bg-white px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                  monitoring
                </span>
              </div>
              <div className="mt-2 text-xs leading-5">
                Das bedeutet nicht “keine Risiken”: Makro, Event-Pings und Top-Mover werden weiter beobachtet.
                Sobald ein Event deine Holdings, Watchlist oder Sektoren trifft, erscheint hier ein konkreter Impact.
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                {[
                  "Portfolio-Bezug wird gegen Holdings gematcht",
                  "Event-Pings bleiben priorisiert",
                  "Top-Mover koennen trotzdem Analyse-Trigger liefern",
                ].map((copy) => (
                  <div key={copy} className="rounded-[0.8rem] border border-black/8 bg-white/70 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">
                    {copy}
                  </div>
                ))}
              </div>
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
              WSB / r/stocks / r/investing
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
        {hasPredictionSignals ? (
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {(brief.prediction_signals || []).slice(0, 8).map((pm: any, i: number) => {
              const probabilityRaw = Number(pm.probability);
              const probability = Number.isFinite(probabilityRaw)
                ? (probabilityRaw > 1 ? probabilityRaw / 100 : probabilityRaw)
                : null;
              const prob = probability != null ? Math.round(probability * 100) : null;
              const signalStatus = String(pm.signal_status || "active").toLowerCase();
              const isWatchOnly = signalStatus === "watch";
              const volume = Number(pm.volume_usd);
              const volumeLabel = Number.isFinite(volume) && volume > 0 ? `$${(volume / 1e6).toFixed(1)}M vol` : null;
              return (
                <div
                  key={`pm-signal-${i}`}
                  className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4"
                >
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <span
                      className={`rounded-full border px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.14em] ${
                        isWatchOnly
                          ? "border-amber-500/20 bg-amber-500/10 text-amber-700"
                          : "border-emerald-500/20 bg-emerald-500/10 text-emerald-700"
                      }`}
                    >
                      {isWatchOnly ? "Watch" : "Signal"}
                    </span>
                    {volumeLabel && (
                      <span className="rounded-full border border-black/8 bg-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                        {volumeLabel}
                      </span>
                    )}
                  </div>
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
                      relevance {openValue(pm.relevance)}
                    </span>
                  </div>
                  {pm.why && (
                    <div className="mt-3 rounded-[0.9rem] border border-black/6 bg-white/55 p-2 text-xs leading-5 text-slate-600">
                      {pm.why}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : !hasPolymarketMarkets ? (
          <div className="mt-4 rounded-[1rem] border border-amber-500/20 bg-amber-500/10 p-3 text-sm text-amber-700">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span>{predictionMessage}</span>
              <span className="rounded-full border border-amber-500/20 bg-white/65 px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.14em] text-amber-700">
                {predictionStatus}
              </span>
            </div>
            {watchedPredictionThemes.length ? (
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                {watchedPredictionThemes.map((theme: any, index: number) => (
                  <div key={`${theme.theme}-${index}`} className="rounded-[0.9rem] border border-amber-500/20 bg-white/55 p-3">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-amber-700">
                      {theme.theme}
                    </div>
                    <div className="mt-1 text-xs leading-5 text-amber-800">{theme.why}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-3 rounded-[0.9rem] border border-amber-500/20 bg-white/55 p-3 text-xs leading-5 text-amber-800">
                Fast Mode: Live-Maerkte werden nachgeladen. Bis dahin bewertet das Briefing Makro-Themen,
                News-Cluster und Event-Pings ohne Polymarket-Gewichtung.
              </div>
            )}
          </div>
        ) : (
          <div className="mt-4 rounded-[1rem] border border-sky-500/20 bg-sky-500/10 p-3 text-sm text-sky-700">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span>{predictionMessage}</span>
              <span className="rounded-full border border-sky-500/20 bg-white/65 px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.14em] text-sky-700">
                confidence gate
              </span>
            </div>
            <div className="mt-2 text-xs leading-5 text-sky-800">
              Die Live-Maerkte werden unten angezeigt. Ins Briefing wandern sie erst, wenn Wahrscheinlichkeit,
              Volumen, Themen-Relevanz und Marktbezug zusammen stark genug sind.
            </div>
          </div>
        )}
      </section>

      {hasPolymarketMarkets && !hasPredictionSignals && (
        <section className="surface-panel rounded-[2rem] p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Polymarket Live Watchlist
            </div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
              below signal gate
            </div>
          </div>
          <div className="mt-3 rounded-[1rem] border border-sky-500/20 bg-sky-500/10 p-3 text-xs leading-5 text-sky-800">
            Diese Maerkte sind live geladen, aber noch nicht stark genug fuer ein Trade-Signal. Sie bleiben sichtbar,
            damit du erkennst, was beobachtet wird und warum im Briefing noch kein Polymarket-Setup daraus entsteht.
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
      <section className="surface-panel rounded-[2rem] p-5">
        <div className="flex items-center justify-between gap-3">
          <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
            Earnings Results
          </div>
          <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
            beat / miss / guidance
          </div>
        </div>
        {(brief.earnings_results || []).length > 0 ? (
          <>
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {(brief.earnings_results || []).slice(0, 6).map((item: any, i: number) => (
                <div
                  key={`er-${item.ticker}-${i}`}
                  className={`rounded-[1.2rem] border p-4 ${
                    item.freshness === "stale_reference"
                      ? "border-slate-300 bg-white/55"
                      : "border-black/8 bg-white/70"
                  }`}
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
                  {item.freshness === "stale_reference" ? (
                    <div className="mt-2 inline-flex rounded-full border border-slate-300 bg-white px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                      reference only / {item.days_since}d old
                    </div>
                  ) : item.days_since != null ? (
                    <div className="mt-2 inline-flex rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.14em] text-emerald-700">
                      fresh / {item.days_since}d old
                    </div>
                  ) : null}
                  <div className="mt-1 line-clamp-1 text-xs text-slate-500">{item.company}</div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                    <div className="rounded-xl border border-black/8 bg-white px-3 py-2">
                      EPS {item.reported_eps != null ? item.reported_eps.toFixed(2) : "offen"}
                    </div>
                    <div className="rounded-xl border border-black/8 bg-white px-3 py-2">
                      Est {item.eps_estimate != null ? item.eps_estimate.toFixed(2) : "offen"}
                    </div>
                    <div className="rounded-xl border border-black/8 bg-white px-3 py-2">
                      Surprise {item.eps_surprise_pct != null ? `${item.eps_surprise_pct >= 0 ? "+" : ""}${item.eps_surprise_pct.toFixed(1)}%` : "offen"}
                    </div>
                    <div className="rounded-xl border border-black/8 bg-white px-3 py-2">
                      Revenue {item.revenue_yoy != null ? `${item.revenue_yoy >= 0 ? "+" : ""}${(item.revenue_yoy * 100).toFixed(1)}%` : "offen"}
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
          </>
        ) : (
          <div className="mt-4 rounded-[1.1rem] border border-black/8 bg-white/70 p-4 text-sm leading-6 text-slate-500">
            Keine frischen Beat-/Miss-Daten im aktuellen Briefing-Fenster. Das bedeutet nicht, dass Earnings ignoriert werden: bevorstehende Termine erscheinen unten, sobald Watchlist oder Leitwerte betroffen sind.
          </div>
        )}
      </section>

      <section className="surface-panel rounded-[2rem] p-5">
        <div className="flex items-center justify-between gap-3">
          <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
            Upcoming Earnings
          </div>
          <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400">
            S&P 500 + Watchlist
          </div>
        </div>
        {(brief.broad_earnings || []).length > 0 ? (
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
        ) : (
          <div className="mt-4 rounded-[1.1rem] border border-black/8 bg-white/70 p-4 text-sm text-slate-500">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="font-bold text-slate-700">Keine nahen Earnings mit hoher Relevanz gefunden.</div>
              <span className="rounded-full border border-slate-300 bg-white px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                no calendar hit
              </span>
            </div>
            <div className="mt-2 text-xs leading-5">
              Ursache: Im aktuellen 21-Tage-Fenster gibt es keinen priorisierten Termin aus Watchlist, Portfolio
              oder Leitwerten. Wenn ein relevanter Termin auftaucht, wird er hier mit Erwartung, Session und
              Analyse-Button angezeigt.
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              {["Watchlist + Portfolio werden weiter gescannt", "Beat/Miss-Daten laufen separat ein", "Termine werden im Briefing gewichtet"].map((copy) => (
                <div
                  key={copy}
                  className="rounded-[0.8rem] border border-black/8 bg-white/70 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500"
                >
                  {copy}
                </div>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
