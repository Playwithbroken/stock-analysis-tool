import React, { useMemo, useState } from "react";
import WorldMarketMap from "./WorldMarketMap";

interface MorningBriefPanelProps {
  brief: any;
  onAnalyze: (ticker: string) => void;
  realtimeQuotes?: Record<string, any>;
  realtimeConnected?: boolean;
}

function fmt(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return "N/A";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export default function MorningBriefPanel({
  brief,
  onAnalyze,
  realtimeQuotes = {},
  realtimeConnected = false,
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
          <span className="rounded-full border border-black/8 bg-white/70 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
            {brief.macro_regime}
          </span>
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
              <button
                onClick={() => setSelectedRegion(region.label)}
                className="text-xs font-bold uppercase text-slate-600"
              >
                {region.tone}
              </button>
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
                {item.event_intelligence?.affected_sectors?.length ? (
                  <div className="mt-2 text-xs text-slate-500">
                    Sectors: {item.event_intelligence.affected_sectors.join(" | ")}
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
                    <div className="mt-2 text-xs text-slate-500">
                      {(item.titles || []).slice(0, 2).join(" | ") || "Live social pulse"}
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4 text-sm text-slate-500">
                  Kein relevantes X-/Social-Signal im aktuellen Brief.
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
                    <div className="mt-2 text-xs text-slate-500">
                      {(item.titles || []).slice(0, 2).join(" | ") || "Crowd cluster"}
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4 text-sm text-slate-500">
                  Kein relevantes Reddit-/Crowd-Cluster im aktuellen Brief.
                </div>
              )}
            </div>
          </div>
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
                Keine kontraeren Medien-Signale mit technischer Bestaetigung.
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
    </div>
  );
}


