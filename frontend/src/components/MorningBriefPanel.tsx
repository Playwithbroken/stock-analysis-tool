import React, { useMemo, useState } from "react";
import WorldMarketMap from "./WorldMarketMap";

interface MorningBriefPanelProps {
  brief: any;
  onAnalyze: (ticker: string) => void;
}

function fmt(value?: number | null) {
  if (value == null) return "N/A";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export default function MorningBriefPanel({
  brief,
  onAnalyze,
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
      <section className="surface-panel rounded-[2.5rem] p-6 sm:p-8">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-[var(--accent-soft)] px-3 py-1 text-[11px] font-extrabold uppercase tracking-[0.22em] text-[var(--accent)]">
            Morning Brief
          </span>
          <span className="rounded-full border border-black/8 bg-white/70 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
            {brief.macro_regime}
          </span>
        </div>
        <h2 className="mt-5 text-4xl text-slate-900 sm:text-5xl">
          {brief.headline}
        </h2>
        <p className="mt-4 max-w-3xl text-base leading-7 text-slate-600">
          {brief.opening_bias}
        </p>

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
        openingTimeline={brief.opening_timeline || []}
        onAnalyze={onAnalyze}
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
              {region.assets?.map((asset: any) => (
                <div
                  key={asset.ticker}
                  className="flex items-center justify-between rounded-[1.2rem] border border-black/8 bg-white/70 p-3"
                >
                  <div>
                    <div className="text-sm font-bold text-slate-900">{asset.label}</div>
                    <div className="text-xs text-slate-500">{asset.ticker}</div>
                  </div>
                  <div
                    className={`text-sm font-bold ${
                      (asset.change_1d || 0) >= 0 ? "text-emerald-700" : "text-red-700"
                    }`}
                  >
                    {fmt(asset.change_1d)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </section>

      <section className="grid gap-4 xl:grid-cols-[1fr_1fr]">
        <div className="surface-panel rounded-[2rem] p-5">
          <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
            Macro Assets
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {brief.macro_assets?.map((asset: any) => (
              <div
                key={asset.ticker}
                className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4"
              >
                <div className="text-sm font-bold text-slate-900">{asset.label}</div>
                <div className="mt-2 text-xs text-slate-500">{asset.ticker}</div>
                <div
                  className={`mt-3 text-lg font-black ${
                    (asset.change_1d || 0) >= 0 ? "text-emerald-700" : "text-red-700"
                  }`}
                >
                  {fmt(asset.change_1d)}
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
              {selectedRegion} focus
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
                    {item.region} • {item.impact}
                  </div>
                  {item.ticker && (
                    <button
                      onClick={(e) => {
                        e.preventDefault();
                        onAnalyze(item.ticker);
                      }}
                      className="rounded-lg bg-[#101114] px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.18em] text-white"
                    >
                      {item.ticker}
                    </button>
                  )}
                </div>
                <div className="mt-2 text-sm font-bold text-slate-900">{item.title}</div>
                <div className="mt-1 text-xs text-slate-500">{item.publisher}</div>
              </a>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-[1fr_1fr]">
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
                    {item.region} • {item.category}
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
                    {new Date(item.scheduled_for).toLocaleDateString()} • {item.region}
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
