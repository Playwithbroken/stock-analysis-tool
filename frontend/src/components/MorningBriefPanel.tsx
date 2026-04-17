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

export default function MorningBriefPanel({
  brief,
  onAnalyze,
  realtimeQuotes = {},
  realtimeConnected = false,
  hideMap = false,
}: MorningBriefPanelProps) {
  if (!brief) return null;

  const regions = [
    brief.regions?.asia,
    brief.regions?.europe,
    brief.regions?.usa,
  ].filter(Boolean);

  const [selectedRegion, setSelectedRegion] = useState<string>(
    brief.regions?.europe?.label || regions[0]?.label || "USA",
  );

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
              <span className={`rounded-full border ${rs.border} ${rs.bg} px-3 py-1 text-[11px] font-extrabold uppercase tracking-[0.18em] ${rs.text}`}>
                {rs.icon} {brief.macro_regime}
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
            <div className="mt-3 text-sm leading-7 text-slate-700">
              {brief.headline}
            </div>
            <div className="mt-4 rounded-[1rem] border border-black/8 bg-[var(--accent-soft)] px-3 py-2 text-[11px] font-bold uppercase tracking-[0.14em] text-[var(--accent)]">
              {brief.opening_bias}
            </div>
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
            <div className="mt-2 text-3xl font-black text-slate-900">
              {brief.macro_regime}
            </div>
          </div>
          <div className="rounded-[1.6rem] border border-black/8 bg-white/80 p-5">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Generated
            </div>
            <div className="mt-2 text-lg font-black text-slate-900">
              {new Date(brief.generated_at).toLocaleTimeString()}
            </div>
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
          watchlistImpact={brief.watchlist_impact || []}
          contrarianSignals={brief.contrarian_signals || []}
          openingTimeline={brief.opening_timeline || []}
          onAnalyze={onAnalyze}
          focusTicker={brief.watchlist_impact?.[0]?.ticker}
        />
      )}

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

      <section className="grid gap-4 xl:grid-cols-[1fr_1fr]">
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
              const prob = pm.probability_yes != null ? Math.round(pm.probability_yes * 100) : null;
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
