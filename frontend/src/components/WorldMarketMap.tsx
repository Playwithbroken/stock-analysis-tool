import React, { useMemo } from "react";
import worldMapSvg from "../assets/world-map-wikimedia.svg";

interface RegionAsset {
  ticker: string;
  label: string;
  change_1d?: number | null;
}

interface RegionSummary {
  label: string;
  tone: string;
  avg_change_1d: number;
  assets?: RegionAsset[];
}

interface MapNewsItem {
  title: string;
  region?: string;
  impact?: string;
  publisher?: string;
  link?: string;
  ticker?: string;
}

interface WatchlistImpactItem {
  ticker?: string;
  type?: string;
  summary?: string;
}

interface ContrarianSignalItem {
  ticker?: string;
  title?: string;
  publisher?: string;
  region?: string;
  media_bias?: string;
  contrarian_bias?: string;
  score?: number;
  rsi_14?: number;
  volume_ratio?: number;
  reason?: string;
  link?: string;
}

interface WorldMarketMapProps {
  regions: RegionSummary[];
  selectedRegion: string;
  onSelectRegion: (regionLabel: string) => void;
  news?: MapNewsItem[];
  eventLayer?: MapNewsItem[];
  watchlistImpact?: WatchlistImpactItem[];
  contrarianSignals?: ContrarianSignalItem[];
  openingTimeline?: Array<{
    stage: string;
    label: string;
    tone: string;
    move: number;
    driver: string;
    catalysts?: string[];
    earnings?: string[];
  }>;
  onAnalyze: (ticker: string) => void;
}

interface GeoEvent extends MapNewsItem {
  markerLabel: string;
  markerTone: "red" | "amber" | "blue" | "slate";
  markerPosition: { left: string; top: string };
}

const positions: Record<string, { x: number; y: number; align: "left" | "right" }> = {
  USA: { x: 29, y: 40, align: "left" },
  Europe: { x: 51, y: 31, align: "right" },
  Asia: { x: 74, y: 38, align: "right" },
};

const regionKeywords: Record<string, string[]> = {
  USA: ["usa", "u.s.", "us ", "federal reserve", "fed", "washington", "wall street"],
  Europe: ["europe", "eu", "ecb", "france", "germany", "uk", "britain", "italy"],
  Asia: ["asia", "china", "japan", "hong kong", "taiwan", "korea", "india"],
};

const markerLayout = {
  USA: { left: "24%", top: "50%" },
  Europe: { left: "49%", top: "35%" },
  Asia: { left: "69%", top: "41%" },
  Global: { left: "58%", top: "57%" },
};

function formatPct(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function tonePillClass(tone: string) {
  if (tone === "risk-on") return "bg-emerald-500/10 text-emerald-700";
  if (tone === "risk-off") return "bg-red-500/10 text-red-700";
  return "bg-amber-500/10 text-amber-700";
}

function toneDotClass(tone: string) {
  if (tone === "risk-on") return "bg-emerald-600";
  if (tone === "risk-off") return "bg-red-600";
  return "bg-amber-600";
}

function textToneClass(tone: string) {
  if (tone === "risk-on") return "text-emerald-700";
  if (tone === "risk-off") return "text-red-700";
  return "text-amber-700";
}

function markerClass(tone: GeoEvent["markerTone"]) {
  if (tone === "red") return "border-red-500/20 bg-red-500/10 text-red-700";
  if (tone === "amber") return "border-amber-500/20 bg-amber-500/10 text-amber-700";
  if (tone === "blue") return "border-blue-500/20 bg-blue-500/10 text-blue-700";
  return "border-slate-400/20 bg-slate-500/10 text-slate-700";
}

function getRegionNews(news: MapNewsItem[], region: string) {
  const keywords = regionKeywords[region] || [];
  return news.filter((item) => {
    const haystack = `${item.region || ""} ${item.title || ""}`.toLowerCase();
    return keywords.some((keyword) => haystack.includes(keyword));
  });
}

function classifyGeoEvent(item: MapNewsItem): GeoEvent | null {
  const haystack = `${item.title || ""} ${item.impact || ""} ${item.region || ""}`.toLowerCase();

  if (/(war|missile|attack|iran|israel|russia|ukraine)/.test(haystack)) {
    return {
      ...item,
      markerLabel: "Conflict",
      markerTone: "red",
      markerPosition: markerLayout[item.region === "europe" ? "Europe" : item.region === "asia" ? "Asia" : "Global"],
    };
  }
  if (/(fed|ecb|boj|central bank|rate|yield)/.test(haystack)) {
    return {
      ...item,
      markerLabel: "Central Bank",
      markerTone: "blue",
      markerPosition: markerLayout[item.region === "europe" ? "Europe" : item.region === "asia" ? "Asia" : "USA"],
    };
  }
  if (/(oil|opec|crude|gas)/.test(haystack)) {
    return {
      ...item,
      markerLabel: "Energy",
      markerTone: "amber",
      markerPosition: markerLayout.Global,
    };
  }
  if (/(tariff|sanction|trade|policy|regulation)/.test(haystack)) {
    return {
      ...item,
      markerLabel: "Policy",
      markerTone: "slate",
      markerPosition: markerLayout[item.region === "asia" ? "Asia" : item.region === "europe" ? "Europe" : "USA"],
    };
  }
  return null;
}

function buildTimeline(regions: RegionSummary[], activeRegionNews: MapNewsItem[]) {
  const lookup = Object.fromEntries(regions.map((region) => [region.label, region]));
  const order = ["Asia", "Europe", "USA"];
  return order
    .filter((label) => lookup[label])
    .map((label, index) => {
      const region = lookup[label];
      const localNews = activeRegionNews.filter((item) => item.region?.toLowerCase() === label.toLowerCase());
      const driver =
        localNews[0]?.title ||
        region.assets?.[0]?.label ||
        (region.tone === "risk-on"
          ? "buyers in control"
          : region.tone === "risk-off"
            ? "defensive rotation"
            : "cross-asset confirmation needed");
      return {
        key: label,
        stage: index === 0 ? "Asia close" : index === 1 ? "Europe handoff" : "US open",
        label,
        tone: region.tone,
        move: region.avg_change_1d,
        driver,
      };
    });
}

export default function WorldMarketMap({
  regions,
  selectedRegion,
  onSelectRegion,
  news = [],
  eventLayer = [],
  watchlistImpact = [],
  contrarianSignals = [],
  openingTimeline = [],
  onAnalyze,
}: WorldMarketMapProps) {
  const activeRegion =
    regions.find((region) => region.label === selectedRegion) || regions[0] || null;

  const activeRegionNews = useMemo(
    () => (activeRegion ? getRegionNews(news, activeRegion.label).slice(0, 4) : []),
    [activeRegion, news],
  );

  const geoSignals = useMemo(
    () =>
      (eventLayer.length ? eventLayer : news)
        .map(classifyGeoEvent)
        .filter(Boolean)
        .slice(0, 4) as GeoEvent[],
    [eventLayer, news],
  );

  const timeline = useMemo(
    () =>
      openingTimeline.length
        ? openingTimeline
        : buildTimeline(regions, news),
    [openingTimeline, regions, news],
  );

  const regionalContrarian = useMemo(
    () =>
      contrarianSignals.filter((item) =>
        activeRegion ? (item.region || "").toLowerCase() === activeRegion.label.toLowerCase() : true,
      ),
    [contrarianSignals, activeRegion],
  );

  return (
    <section className="surface-panel relative overflow-hidden rounded-[2.5rem] p-6 sm:p-8">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(15,118,110,0.08),transparent_30%),radial-gradient(circle_at_bottom_right,rgba(37,99,235,0.06),transparent_26%)]" />

      <div className="relative space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="text-[11px] font-extrabold uppercase tracking-[0.24em] text-slate-500">
              Market Map
            </div>
            <h3 className="mt-2 text-4xl text-slate-900">Overnight world flow</h3>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">
              Regionen, Makro-Ton, geopolitische Events und der Hand-off bis zur US-Eröffnung
              in einer kompakten Macro-Ansicht.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {regions.map((region) => (
              <button
                key={region.label}
                onClick={() => onSelectRegion(region.label)}
                className={`rounded-full px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] transition-all ${
                  selectedRegion === region.label
                    ? "bg-[var(--accent)] text-white shadow-[0_16px_34px_rgba(15,118,110,0.18)]"
                    : "border border-black/8 bg-white/70 text-slate-500"
                }`}
              >
                {region.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.35fr_0.65fr]">
          <div className="relative min-h-[420px] overflow-hidden rounded-[2rem] border border-black/8 bg-[linear-gradient(180deg,rgba(255,255,255,0.92),rgba(244,240,232,0.95))] p-4 sm:p-6">
            <div className="absolute inset-0 overflow-hidden opacity-55">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.84),transparent_34%),radial-gradient(circle_at_bottom_right,rgba(239,233,223,0.78),transparent_30%)]" />
              <img
                src={worldMapSvg}
                alt="World map"
                className="h-full w-full scale-[1.08] object-cover object-center"
                draggable={false}
              />
            </div>

            <div className="absolute bottom-3 right-4 rounded-full border border-black/8 bg-white/88 px-3 py-1 text-[9px] font-bold uppercase tracking-[0.18em] text-slate-500">
              Wikimedia map base
            </div>

            <div className="absolute inset-x-10 top-[60%] hidden h-px bg-[linear-gradient(90deg,rgba(15,23,42,0),rgba(15,23,42,0.35),rgba(15,23,42,0))] lg:block" />

            {regions.map((region) => {
              const pos = positions[region.label];
              if (!pos) return null;
              const isActive = region.label === selectedRegion;

              return (
                <button
                  key={region.label}
                  type="button"
                  onClick={() => onSelectRegion(region.label)}
                  className="absolute text-left"
                  style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
                >
                  <div className="relative">
                    <div className="absolute -left-5 -top-5">
                      <div
                        className={`rounded-full ${toneDotClass(region.tone)} ${isActive ? "h-10 w-10 opacity-20 blur-md" : "h-8 w-8 opacity-15 blur-sm"}`}
                      />
                    </div>
                    <div
                      className={`h-3.5 w-3.5 rounded-full ${toneDotClass(region.tone)} ring-4 ring-white/80 shadow-[0_6px_24px_rgba(15,23,42,0.18)] ${isActive ? "scale-125" : ""}`}
                    />
                    <div
                      className="absolute top-1/2 h-px w-16 bg-slate-400/70"
                      style={pos.align === "left" ? { left: 16 } : { right: 16 }}
                    />
                    <div
                      className={`absolute top-1/2 w-44 -translate-y-1/2 rounded-[1.2rem] border p-3 backdrop-blur transition-all ${
                        isActive
                          ? "border-black/12 bg-white/94 shadow-[0_20px_40px_rgba(15,23,42,0.12)]"
                          : "border-black/8 bg-white/82 shadow-[0_14px_34px_rgba(15,23,42,0.08)]"
                      }`}
                      style={pos.align === "left" ? { left: 88 } : { right: 88 }}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-slate-500">
                          {region.label}
                        </div>
                        <div
                          className={`rounded-full px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.16em] ${tonePillClass(region.tone)}`}
                        >
                          {region.tone}
                        </div>
                      </div>
                      <div className={`mt-2 text-lg font-black ${textToneClass(region.tone)}`}>
                        {formatPct(region.avg_change_1d)}
                      </div>
                      <div className="mt-2 text-[11px] text-slate-500">
                        {(region.assets || []).slice(0, 2).map((asset) => asset.label).join(" • ") || "Macro mix"}
                      </div>
                    </div>
                  </div>
                </button>
              );
            })}

            {geoSignals.map((item, index) => (
              <div
                key={`${item.title}-${index}`}
                className="absolute"
                style={item.markerPosition}
              >
                <div
                  className={`rounded-full border px-2 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] ${markerClass(item.markerTone)}`}
                >
                  {item.markerLabel}
                </div>
              </div>
            ))}
          </div>

          <div className="space-y-4">
            {activeRegion && (
              <div className="rounded-[1.7rem] border border-black/8 bg-white/85 p-5">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                      Region Focus
                    </div>
                    <div className="mt-2 text-2xl font-black text-slate-900">
                      {activeRegion.label}
                    </div>
                  </div>
                  <div
                    className={`rounded-full px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] ${tonePillClass(activeRegion.tone)}`}
                  >
                    {activeRegion.tone}
                  </div>
                </div>
                <div className={`mt-4 text-3xl font-black ${textToneClass(activeRegion.tone)}`}>
                  {formatPct(activeRegion.avg_change_1d)}
                </div>
                <div className="mt-4 space-y-2">
                  {(activeRegion.assets || []).slice(0, 3).map((asset) => (
                    <div
                      key={asset.ticker}
                      className="flex items-center justify-between rounded-[1rem] border border-black/8 bg-white/75 px-3 py-2"
                    >
                      <div>
                        <div className="text-sm font-bold text-slate-900">{asset.label}</div>
                        <div className="text-[11px] text-slate-500">{asset.ticker}</div>
                      </div>
                      <div
                        className={`text-sm font-bold ${
                          (asset.change_1d || 0) >= 0 ? "text-emerald-700" : "text-red-700"
                        }`}
                      >
                        {formatPct(asset.change_1d || 0)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="rounded-[1.7rem] border border-black/8 bg-white/85 p-5">
              <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                Event Layer
              </div>
              <div className="mt-4 space-y-3">
                {geoSignals.length ? (
                  geoSignals.map((item, index) => (
                    <a
                      key={`${item.title}-${index}`}
                      href={item.link}
                      target="_blank"
                      rel="noreferrer"
                      className="block rounded-[1rem] border border-black/8 bg-white/75 p-3 transition-colors hover:bg-white"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div
                          className={`rounded-full border px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.16em] ${markerClass(item.markerTone)}`}
                        >
                          {item.markerLabel}
                        </div>
                        <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                          {item.region || "Global"} • {item.impact || "macro"}
                        </div>
                      </div>
                      <div className="mt-2 text-sm font-bold text-slate-900">{item.title}</div>
                    </a>
                  ))
                ) : (
                  <div className="rounded-[1rem] border border-black/8 bg-white/75 p-3 text-sm text-slate-500">
                    Keine dominanten geopolitischen Schocks im aktuellen Brief.
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-[1.7rem] border border-black/8 bg-white/85 p-5">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                  Contrarian Radar
                </div>
                <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-400">
                  media fade
                </div>
              </div>
              <div className="mt-4 space-y-3">
                {regionalContrarian.length ? (
                  regionalContrarian.slice(0, 4).map((item, index) => (
                    <div
                      key={`${item.ticker}-${index}`}
                      className="rounded-[1rem] border border-black/8 bg-white/75 p-3"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <button
                          onClick={() => item.ticker && onAnalyze(item.ticker)}
                          className="text-sm font-black text-slate-900"
                        >
                          {item.ticker}
                        </button>
                        <div
                          className={`rounded-full px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.16em] ${
                            item.contrarian_bias === "long"
                              ? "bg-emerald-500/10 text-emerald-700"
                              : "bg-red-500/10 text-red-700"
                          }`}
                        >
                          inverse {item.contrarian_bias}
                        </div>
                      </div>
                      <div className="mt-2 text-xs text-slate-500">
                        {item.publisher} · score {item.score} · RSI {item.rsi_14} · RVOL {item.volume_ratio}
                      </div>
                      <div className="mt-2 text-sm text-slate-700">{item.reason}</div>
                    </div>
                  ))
                ) : (
                  <div className="rounded-[1rem] border border-black/8 bg-white/75 p-3 text-sm text-slate-500">
                    Keine konträren Medien-Setups mit technischer Bestätigung in dieser Region.
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-[1.8rem] border border-black/8 bg-white/80 p-5">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Opening Timeline
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              {timeline.map((item) => (
                <button
                  key={item.label}
                  onClick={() => onSelectRegion(item.label)}
                  className={`rounded-[1.3rem] border p-4 text-left transition-all ${
                    selectedRegion === item.label
                      ? "border-black/12 bg-white shadow-[0_16px_34px_rgba(15,23,42,0.08)]"
                      : "border-black/8 bg-white/65"
                  }`}
                >
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                    {item.stage}
                  </div>
                  <div className="mt-2 flex items-center justify-between gap-3">
                    <div className="text-lg font-black text-slate-900">{item.label}</div>
                    <div
                      className={`rounded-full px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.16em] ${tonePillClass(item.tone)}`}
                    >
                      {item.tone}
                    </div>
                  </div>
                  <div className={`mt-3 text-2xl font-black ${textToneClass(item.tone)}`}>
                    {formatPct(item.move)}
                  </div>
                  <div className="mt-3 text-sm leading-6 text-slate-600">
                    {item.driver}
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-[1.8rem] border border-black/8 bg-white/80 p-5">
            <div className="flex items-center justify-between gap-3">
              <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                Watchlist In Play
              </div>
              <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-400">
                {(watchlistImpact || []).length} live items
              </div>
            </div>
            <div className="mt-4 space-y-3">
              {(watchlistImpact || []).slice(0, 4).map((item, index) => (
                <div
                  key={`${item.ticker || item.summary}-${index}`}
                  className="rounded-[1rem] border border-black/8 bg-white/75 p-3"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                      {item.type || "signal"}
                    </div>
                    {item.ticker && (
                      <button
                        onClick={() => onAnalyze(item.ticker!)}
                        className="rounded-full bg-[var(--accent)] px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.16em] text-white"
                      >
                        {item.ticker}
                      </button>
                    )}
                  </div>
                  <div className="mt-2 text-sm font-bold text-slate-900">
                    {item.summary}
                  </div>
                </div>
              ))}
              {!watchlistImpact?.length && (
                <div className="rounded-[1rem] border border-black/8 bg-white/75 p-3 text-sm text-slate-500">
                  Aktuell keine direkten Watchlist-Signale in der Opening-Lage.
                </div>
              )}
            </div>
          </div>
        </div>

        {activeRegionNews.length > 0 && (
          <div className="rounded-[1.8rem] border border-black/8 bg-white/80 p-5">
            <div className="flex items-center justify-between gap-3">
              <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                Regional Drivers
              </div>
              <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-400">
                {activeRegion?.label} focus
              </div>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {activeRegionNews.map((item, index) => (
                <a
                  key={`${item.title}-${index}`}
                  href={item.link}
                  target="_blank"
                  rel="noreferrer"
                  className="block rounded-[1rem] border border-black/8 bg-white/75 p-4 transition-colors hover:bg-white"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                      {item.publisher || activeRegion?.label}
                    </div>
                    {item.ticker && (
                      <button
                        onClick={(event) => {
                          event.preventDefault();
                          onAnalyze(item.ticker!);
                        }}
                        className="rounded-full border border-black/8 bg-white px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.16em] text-slate-700"
                      >
                        {item.ticker}
                      </button>
                    )}
                  </div>
                  <div className="mt-2 text-sm font-bold text-slate-900">{item.title}</div>
                </a>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
