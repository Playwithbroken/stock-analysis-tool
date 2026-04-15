import React, { useEffect, useState } from "react";
import MarketSentiment from "./MarketSentiment";
import PublicSignalsPanel from "./PublicSignalsPanel";
import SignalWatchlistPanel from "./SignalWatchlistPanel";
import NotificationSettingsPanel from "./NotificationSettingsPanel";
import { useCurrency } from "../context/CurrencyContext";
import { fetchJsonWithRetry } from "../lib/api";

/** Wraps a promise with a timeout — resolves null instead of hanging forever */
function withTimeout<T>(promise: Promise<T>, ms = 12000): Promise<T | null> {
  return Promise.race([
    promise,
    new Promise<null>((resolve) => setTimeout(() => resolve(null), ms)),
  ]);
}

interface DiscoveryStock {
  ticker: string;
  name: string;
  price?: number;
  change?: number;
  drawdown?: number;
  market_cap?: number;
  growth?: number;
  score?: number;
  trend_context?: string;
  reason?: string;
}

interface DiscoveryPanelProps {
  onAnalyze: (ticker: string) => void;
}

interface StarAssets {
  day_winner?: DiscoveryStock;
  week_winner?: DiscoveryStock;
  day_loser?: DiscoveryStock;
  week_loser?: DiscoveryStock;
  for_you?: DiscoveryStock[];
}

interface PublicSignalsData {
  trackers: any[];
}

interface SignalWatchlistData {
  items: any[];
  ticker_signals: any[];
  politician_signals: any[];
}

const DiscoveryPanel: React.FC<DiscoveryPanelProps> = ({ onAnalyze }) => {
  const { formatPrice } = useCurrency();
  const [activeTab, setActiveTab] = useState<
    "overview" | "signals" | "ai" | "movers" | "alternative" | "etf"
  >("overview");
  const [stars, setStars] = useState<StarAssets | null>(null);
  const [publicSignals, setPublicSignals] = useState<PublicSignalsData | null>(
    null,
  );
  const [signalWatchlist, setSignalWatchlist] =
    useState<SignalWatchlistData | null>(null);
  const [trending, setTrending] = useState<DiscoveryStock[]>([]);
  const [gainers, setGainers] = useState<DiscoveryStock[]>([]);
  const [losers, setLosers] = useState<DiscoveryStock[]>([]);
  const [rebounds, setRebounds] = useState<DiscoveryStock[]>([]);
  const [smallCaps, setSmallCaps] = useState<DiscoveryStock[]>([]);
  const [moonshots, setMoonshots] = useState<DiscoveryStock[]>([]);
  const [cryptos, setCryptos] = useState<DiscoveryStock[]>([]);
  const [commodities, setCommodities] = useState<DiscoveryStock[]>([]);
  const [etfs, setEtfs] = useState<any[]>([]);
  const [selectedEtfs, setSelectedEtfs] = useState<any[]>([]);
  const [isComparing, setIsComparing] = useState(false);
  const [highRiskOpps, setHighRiskOpps] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);

  useEffect(() => {
    const fetchAll = async () => {
      setLoading(true);

      const safeFetch = <T,>(url: string) =>
        withTimeout(fetchJsonWithRetry<T>(url, undefined, { retries: 1, retryDelayMs: 800 }));

      const results = await Promise.allSettled([
        safeFetch("/api/discovery/stars"),
        safeFetch("/api/discovery/public-signals"),
        safeFetch("/api/signals/watchlist"),
        safeFetch<DiscoveryStock[]>("/api/discovery/trending"),
        safeFetch<DiscoveryStock[]>("/api/discovery/gainers"),
        safeFetch<DiscoveryStock[]>("/api/discovery/losers"),
        safeFetch<DiscoveryStock[]>("/api/discovery/rebounds"),
        safeFetch<DiscoveryStock[]>("/api/discovery/small-caps"),
        safeFetch<DiscoveryStock[]>("/api/discovery/moonshots"),
        safeFetch<DiscoveryStock[]>("/api/discovery/cryptos"),
        safeFetch<DiscoveryStock[]>("/api/discovery/commodities"),
        safeFetch("/api/discovery/high-risk-opportunities"),
        safeFetch("/api/discovery/etfs"),
      ]);

      const val = <T,>(r: PromiseSettledResult<T | null>, fallback: T): T =>
        r.status === "fulfilled" && r.value != null ? r.value : fallback;

      const [s, ps, sw, t, g, l, r, sc, m, cur, com, hr, e] = results;

      setStars(val(s, null));
      setPublicSignals(val(ps, null));
      setSignalWatchlist(val(sw, null));
      setTrending(val(t, []));
      setGainers(val(g, []));
      setLosers(val(l, []));
      setRebounds(val(r, []));
      setSmallCaps(val(sc, []));
      setMoonshots(val(m, []));
      setCryptos(val(cur, []));
      setCommodities(val(com, []));
      setHighRiskOpps(val(hr, []));
      setEtfs(val(e, []));

      setLoading(false);
    };
    fetchAll();
  }, []);

  const handleSearch = async (query: string) => {
    setSearchQuery(query);
    if (query.length < 2) {
      setSearchResults([]);
      return;
    }
    setIsSearching(true);
    try {
      const data = await fetchJsonWithRetry<any[]>(
        `/api/search?q=${encodeURIComponent(query)}`,
        undefined,
        { retries: 1, retryDelayMs: 800 },
      );
      setSearchResults(data ?? []);
    } catch {
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  const refreshSignalWatchlist = async () => {
    try {
      const data = await fetchJsonWithRetry<SignalWatchlistData>("/api/signals/watchlist");
      setSignalWatchlist(data);
    } catch {
      // silently keep existing state
    }
  };

  const addSearchedEtf = async (res: any) => {
    try {
      const data = await fetchJsonWithRetry<any>(
        `/api/analysis/basic?ticker=${res.ticker}`,
        undefined,
        { retries: 1, retryDelayMs: 800 },
      );

      const newEtf = {
        ticker: res.ticker,
        name: res.name,
        ter: data.etf_analysis?.ter || 0,
        change: data.price_data?.change_1w || 0,
        category: data.etf_analysis?.category || "Diverse",
      };

      if (selectedEtfs.length < 3) {
        setSelectedEtfs([...selectedEtfs, newEtf]);
      }
    } catch {
      // Fallback with basic info
      if (selectedEtfs.length < 3) {
        setSelectedEtfs([...selectedEtfs, { ...res, ter: 0, change: 0 }]);
      }
    }
    setSearchQuery("");
    setSearchResults([]);
  };

  const tabs = [
    { id: "signals", label: "Signals", icon: "SG" },
    { id: "overview", label: "Markt-Puls", icon: "MP" },
    { id: "ai", label: "AI Chancen", icon: "AI" },
    { id: "movers", label: "Top/Flop", icon: "TF" },
    { id: "etf", label: "ETF Welt", icon: "ETF" },
    { id: "alternative", label: "Alternativ", icon: "ALT" },
  ] as const;

  if (loading && !stars) {
    return (
      <div className="content-shell space-y-8 p-4 xl:px-2">
        {/* Banner Skeleton */}
        <div className="relative h-48 w-full overflow-hidden rounded-3xl border border-black/8 bg-white/80 animate-pulse">
          <div className="absolute inset-0 -translate-x-full animate-[shimmer_2s_infinite] bg-white/40"></div>
        </div>

        {/* Grid Skeleton */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="relative h-40 overflow-hidden rounded-3xl border border-black/8 bg-white/75 animate-pulse"
            >
              <div className="absolute inset-0 -translate-x-full animate-[shimmer_2s_infinite] bg-white/40"></div>
            </div>
          ))}
        </div>

        {/* List Skeleton */}
        <div className="space-y-4">
          <div className="h-8 w-48 rounded-lg bg-[var(--bg-soft)] animate-pulse"></div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-32 rounded-2xl border border-black/8 bg-white/75 animate-pulse"
              ></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8 pb-20">
      {/* Tab Navigation */}
      <div className="no-scrollbar sticky top-20 z-40 -mx-1 overflow-x-auto px-1">
        <div className="surface-panel mx-auto flex w-max min-w-full items-center gap-2 rounded-2xl p-1.5 lg:mx-0 lg:min-w-0">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex shrink-0 items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-bold transition-all sm:px-6 ${
                activeTab === tab.id
                  ? "bg-[var(--accent)] text-white shadow-[0_10px_30px_rgba(15,118,110,0.18)]"
                  : "text-slate-500 hover:text-slate-900 hover:bg-black/[0.04]"
              }`}
            >
              <span className="inline-flex min-w-[1.2rem] justify-center text-xs font-extrabold uppercase tracking-[0.14em]">
                {tab.icon}
              </span>
              <span>{tab.label}</span>
            </button>
          ))}
        </div>
      </div>

      {activeTab === "etf" && (
        <div className="surface-panel flex items-center justify-between rounded-2xl p-4 animate-in fade-in slide-in-from-top-4">
          <div className="flex items-center gap-4">
            <div
              className={`w-10 h-10 rounded-xl flex items-center justify-center transition-colors ${isComparing ? "bg-[var(--accent)] text-white" : "bg-[var(--bg-soft)] text-slate-500"}`}
            >
              <span className="text-xl font-bold">{selectedEtfs.length}</span>
            </div>
            <div>
              <h4 className="text-sm font-bold text-slate-900">
                Multi-Vergleich Modus
              </h4>
              <p className="text-xs text-slate-500">
                Wähle bis zu 3 ETFs aus, um sie direkt zu vergleichen.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {selectedEtfs.length > 0 && (
              <button
                onClick={() => setSelectedEtfs([])}
                className="text-xs font-bold text-slate-500 hover:text-slate-900 transition-colors"
              >
                Auswahl leeren
              </button>
            )}
            <button
              onClick={() => setIsComparing(!isComparing)}
              disabled={selectedEtfs.length < 2 && !isComparing}
              className={`px-6 py-2.5 rounded-xl text-sm font-bold transition-all ${
                isComparing
                  ? "bg-[var(--accent)] text-white"
                  : selectedEtfs.length >= 2
                    ? "bg-[var(--accent)] text-white shadow-[0_10px_30px_rgba(15,118,110,0.18)]"
                    : "bg-[var(--bg-soft)] text-slate-400 cursor-not-allowed"
              }`}
            >
              {isComparing ? "Vergleich schließen" : "Jetzt vergleichen"}
            </button>
          </div>
        </div>
      )}

      {activeTab === "etf" && !isComparing && (
        <div className="relative max-w-2xl mx-auto lg:mx-0">
          <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
            <span className="text-slate-500">🔍</span>
          </div>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="ETF suchen (z.B. MSCI World, S&P 500, Automation...)"
            className="w-full rounded-2xl border border-black/8 bg-white py-4 pl-12 pr-4 font-medium text-slate-900 placeholder:text-slate-400 transition-all focus:outline-hidden focus:ring-2 focus:ring-[var(--accent)]/20"
          />

          {/* Search Results Overlay */}
          {searchQuery.length >= 2 && (
            <div className="absolute top-full left-0 right-0 z-50 mt-2 max-h-96 overflow-y-auto rounded-2xl border border-black/8 bg-[rgba(255,255,255,0.96)] p-2 shadow-[0_24px_80px_rgba(17,24,39,0.12)] backdrop-blur-xl">
              {isSearching ? (
                <div className="p-4 text-center text-slate-500 animate-pulse font-bold">
                  Wird gescannt...
                </div>
              ) : searchResults.length > 0 ? (
                <div className="grid grid-cols-1 gap-1">
                  {searchResults.map((res) => {
                    const isSelected = selectedEtfs.some(
                      (s) => s.ticker === res.ticker,
                    );
                    return (
                      <div
                        key={res.ticker}
                        onClick={() => {
                          if (!isSelected) {
                            addSearchedEtf(res);
                          } else {
                            setSearchQuery("");
                            setSearchResults([]);
                          }
                        }}
                        className="group flex cursor-pointer items-center justify-between rounded-xl p-3 transition-colors hover:bg-black/[0.03]"
                      >
                        <div className="flex items-center gap-4">
                          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--accent-soft)] text-[var(--accent)] font-black text-xs">
                            {res.ticker.slice(0, 2)}
                          </div>
                          <div>
                            <div className="text-sm font-bold text-slate-900 transition-colors group-hover:text-[var(--accent)]">
                              {res.ticker}
                            </div>
                            <div className="text-[10px] text-slate-500 truncate max-w-[200px]">
                              {res.name}
                            </div>
                          </div>
                        </div>
                        <div className="text-[10px] font-black text-slate-600 uppercase tracking-widest">
                          {res.exchange}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="p-4 text-center text-slate-500">
                  Keine ETFs gefunden
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div className="pt-4 transition-all duration-500">
        {activeTab === "overview" && (
          <div className="space-y-12 animate-in fade-in slide-in-from-bottom-4">
            <MarketSentiment onAnalyze={onAnalyze} />

            {stars ? (
              <section className="space-y-6">
                <div className="flex items-center justify-between">
                  <h2 className="flex items-center gap-3 text-2xl font-black italic text-slate-900">
                    <span className="text-yellow-600">Star</span> Spotlight
                  </h2>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  {/* Day Winner */}
                  <div
                    onClick={() =>
                      stars.day_winner && onAnalyze(stars.day_winner.ticker)
                    }
                    className="surface-panel group relative cursor-pointer rounded-3xl p-6 transition-all hover:-translate-y-1 hover:border-green-500/20"
                  >
                    <div className="mb-4 flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-emerald-700">
                      <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse"></span>
                      Day Winner
                    </div>
                    <div className="mb-1 text-3xl font-black text-slate-900 transition-colors group-hover:text-green-700">
                      {stars.day_winner?.ticker || "N/A"}
                    </div>
                    <div className="mb-4 truncate text-sm text-slate-500">
                      {stars.day_winner?.name || "No data"}
                    </div>
                    <div className="text-2xl font-mono font-bold text-emerald-700">
                      +{stars.day_winner?.change?.toFixed(2) || "0.00"}%
                    </div>
                  </div>

                  {/* Week Winner */}
                  <div
                    onClick={() =>
                      stars.week_winner && onAnalyze(stars.week_winner.ticker)
                    }
                    className="surface-panel group relative cursor-pointer rounded-3xl p-6 transition-all hover:-translate-y-1 hover:border-[var(--accent)]/20"
                  >
                    <div className="mb-4 flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-[var(--accent)]">
                      <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] animate-pulse"></span>
                      Week Winner
                    </div>
                    <div className="mb-1 text-3xl font-black text-slate-900 transition-colors group-hover:text-[var(--accent)]">
                      {stars.week_winner?.ticker || "N/A"}
                    </div>
                    <div className="mb-4 truncate text-sm text-slate-500">
                      {stars.week_winner?.name || "No data"}
                    </div>
                    <div className="text-2xl font-mono font-bold text-[var(--accent)]">
                      +{stars.week_winner?.change?.toFixed(2) || "0.00"}%
                    </div>
                  </div>

                  {/* Personalized picks */}
                  {stars.for_you?.length ? (
                    stars.for_you.slice(0, 2).map((stock, idx) => (
                      <div
                        key={stock.ticker || idx}
                        onClick={() => onAnalyze(stock.ticker)}
                        className="surface-panel group relative cursor-pointer rounded-3xl p-6 transition-all hover:-translate-y-1 hover:border-sky-500/20"
                      >
                        <div className="mb-4 text-[10px] font-bold uppercase tracking-widest text-sky-700">
                          Picked for you
                        </div>
                        <div className="mb-1 text-3xl font-black text-slate-900 transition-colors group-hover:text-sky-700">
                          {stock.ticker}
                        </div>
                        <div className="mb-4 truncate text-sm text-slate-500">
                          {stock.name}
                        </div>
                        <div
                          className={`text-2xl font-mono font-bold ${stock.change && stock.change > 0 ? "text-emerald-700" : "text-red-700"}`}
                        >
                          {stock.change && stock.change > 0 ? "+" : ""}
                          {stock.change?.toFixed(2)}%
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="col-span-2 flex items-center justify-center rounded-3xl border border-dashed border-black/8 bg-white/72 p-6 text-sm text-slate-500">
                      No personalized picks available yet.
                    </div>
                  )}
                </div>
              </section>
            ) : (
              <div className="rounded-3xl border border-dashed border-black/8 bg-white/72 py-10 text-center text-slate-500">
                Failed to load market stars.
              </div>
            )}
          </div>
        )}

        {activeTab === "signals" && (
          <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4">
            <PublicSignalsPanel data={publicSignals} onAnalyze={onAnalyze} />
            <NotificationSettingsPanel />
            <SignalWatchlistPanel
              data={signalWatchlist}
              onAnalyze={onAnalyze}
              onRefresh={refreshSignalWatchlist}
            />
          </div>
        )}

        {activeTab === "ai" && (
          <div className="space-y-12 animate-in fade-in slide-in-from-bottom-4">
            <section className="space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.24em] text-slate-500">
                    AI Chancen
                  </div>
                  <h2 className="mt-2 text-3xl font-black text-slate-900">
                    High-Risk Radar
                  </h2>
                </div>
                <div className="rounded-full border border-red-500/15 bg-red-500/6 px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-red-700">
                  Opportunistisch
                </div>
              </div>

              <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
                {highRiskOpps.map((opp: any) => (
                  <div
                    key={opp.ticker}
                    onClick={() => onAnalyze(opp.ticker)}
                    className="surface-panel group cursor-pointer rounded-[2rem] p-6 transition-all duration-200 hover:-translate-y-1 hover:border-red-500/18"
                  >
                    <div className="mb-6 flex items-start justify-between gap-4">
                      <div>
                        <div className="mb-1 text-3xl font-black text-slate-900">
                          {opp.ticker}
                        </div>
                        <div className="max-w-[180px] truncate text-sm text-slate-500">
                          {opp.name}
                        </div>
                      </div>
                      <div className="rounded-full border border-red-500/15 bg-red-500/8 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.16em] text-red-700">
                        Opportunity
                      </div>
                    </div>

                    <div className="mb-6 grid grid-cols-3 gap-3">
                      {[
                        {
                          label: "Risk",
                          val: opp.risk_score,
                          color: "text-red-700",
                        },
                        {
                          label: "Reward",
                          val: opp.reward_score,
                          color: "text-emerald-700",
                        },
                        {
                          label: "Score",
                          val: opp.opportunity_score,
                          color: "text-indigo-700",
                        },
                      ].map((stat) => (
                        <div
                          key={stat.label}
                          className="rounded-[1.1rem] border border-black/8 bg-[rgba(255,255,255,0.82)] p-3 text-center"
                        >
                          <div className="mb-1 text-[8px] font-bold uppercase tracking-[0.18em] text-slate-500">
                            {stat.label}
                          </div>
                          <div className={`text-lg font-black ${stat.color}`}>
                            {stat.val}
                          </div>
                        </div>
                      ))}
                    </div>

                    <div className="rounded-[1.4rem] border border-indigo-500/15 bg-indigo-500/6 p-4">
                      <div className="mb-1 text-[10px] font-bold uppercase tracking-[0.18em] text-indigo-700">
                        AI Recommendation
                      </div>
                      <div className="mb-2 text-sm font-bold text-slate-900">
                        {opp.recommendation}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {opp.reasons?.slice(0, 2).map((r: string, i: number) => (
                          <span
                            key={i}
                            className="rounded-full border border-black/8 bg-white/78 px-2 py-0.5 text-[9px] text-slate-600"
                          >
                            {r}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.24em] text-slate-500">
                    AI Chancen
                  </div>
                  <h2 className="mt-2 text-3xl font-black text-slate-900">
                    Moonshot Scanner
                  </h2>
                </div>
                <div className="rounded-full border border-indigo-500/15 bg-indigo-500/6 px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-indigo-700">
                  Growth Bias
                </div>
              </div>

              <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
                {(moonshots.length > 0 ? moonshots : []).map((stock) => (
                  <div
                    key={stock.ticker}
                    onClick={() => onAnalyze(stock.ticker)}
                    className="surface-panel cursor-pointer rounded-[2rem] p-6 transition-all duration-200 hover:-translate-y-1 hover:border-indigo-500/18"
                  >
                    <div className="mb-6 flex items-start justify-between gap-4">
                      <div>
                        <div className="mb-1 text-3xl font-black text-slate-900">
                          {stock.ticker}
                        </div>
                        <div className="text-sm text-slate-500">{stock.name}</div>
                      </div>
                      <div className="rounded-lg border border-indigo-500/15 bg-indigo-500/8 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.16em] text-indigo-700">
                        Growth
                      </div>
                    </div>
                    <div className="space-y-4">
                      <div className="flex items-center justify-between text-xs font-bold">
                        <span className="text-slate-500 uppercase tracking-widest">
                          Potential
                        </span>
                        <span className="text-indigo-700">{stock.score || 85}%</span>
                      </div>
                      <div className="h-1.5 w-full overflow-hidden rounded-full bg-black/[0.06]">
                        <div
                          className="h-full rounded-full bg-indigo-500"
                          style={{ width: `${stock.score || 85}%` }}
                        ></div>
                      </div>
                      <p className="text-[10px] italic text-slate-500">
                        "{stock.trend_context}"
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </div>
        )}

        {activeTab === "movers" && (
          <div className="space-y-12 animate-in fade-in slide-in-from-bottom-4">
            <section className="space-y-6">
              <h2 className="flex items-center gap-3 text-2xl font-black italic text-slate-900">
                <span className="text-emerald-700">Up</span> MARKET GAINERS
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {gainers.map((stock) => (
                  <div
                    key={stock.ticker}
                    onClick={() => onAnalyze(stock.ticker)}
                    className="surface-panel flex cursor-pointer items-center justify-between rounded-3xl p-5 transition-all hover:-translate-y-1 hover:border-emerald-500/20"
                  >
                    <div>
                      <div className="font-black text-slate-900">
                        {stock.ticker}
                      </div>
                      <div className="max-w-[100px] truncate text-[10px] text-slate-500">
                        {stock.name}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-bold text-emerald-700">
                        +{stock.change?.toFixed(2)}%
                      </div>
                      <div className="text-[8px] font-black uppercase text-slate-500">
                        {stock.trend_context}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="space-y-6">
              <h2 className="flex items-center gap-3 text-2xl font-black italic text-slate-900">
                <span className="text-red-500">📉</span> MAJOR DRAWDOWNS
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {losers.map((stock) => (
                  <div
                    key={stock.ticker}
                    onClick={() => onAnalyze(stock.ticker)}
                    className="surface-panel flex cursor-pointer items-center justify-between rounded-3xl p-5 transition-all hover:-translate-y-1 hover:border-red-500/20"
                  >
                    <div>
                      <div className="font-black text-slate-900">
                        {stock.ticker}
                      </div>
                      <div className="max-w-[100px] truncate text-[10px] text-slate-500">
                        {stock.name}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-bold text-red-700">
                        {stock.change?.toFixed(2)}%
                      </div>
                      <div className="text-[8px] font-black uppercase text-slate-500">
                        Pullback
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </div>
        )}

        {activeTab === "etf" && (
          <div className="space-y-12 animate-in fade-in slide-in-from-bottom-4">
            {isComparing ? (
              <section className="space-y-6">
                <h2 className="flex items-center gap-3 text-2xl font-black italic text-slate-900">
                  <span className="text-indigo-500">🏢</span> ETF COMPARISON
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {selectedEtfs.map((etf) => (
                    <div
                      key={etf.ticker}
                      className="surface-panel relative overflow-hidden rounded-3xl border border-[var(--accent)]/18 p-8"
                    >
                      <div className="absolute top-0 right-0 p-4">
                        <span className="text-xs font-black text-[var(--accent)] opacity-20">
                          {etf.ticker}
                        </span>
                      </div>
                      <div className="mb-8">
                        <h3 className="mb-2 text-3xl font-black text-slate-900">
                          {etf.ticker}
                        </h3>
                        <p className="line-clamp-1 text-sm text-slate-500">
                          {etf.name}
                        </p>
                      </div>

                      <div className="space-y-6">
                        <div className="rounded-2xl border border-black/8 bg-white/75 p-4">
                          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block mb-2">
                            Jährliche Kosten (TER)
                          </span>
                            <div className="text-2xl font-black text-emerald-700">
                            {etf.ter?.toFixed(2)}%
                          </div>
                        </div>

                        <div className="rounded-2xl border border-black/8 bg-white/75 p-4">
                          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block mb-2">
                            Performance (1 Woche)
                          </span>
                          <div
                            className={`text-2xl font-black ${(etf.change || 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}
                          >
                            {(etf.change || 0) >= 0 ? "+" : ""}
                            {etf.change?.toFixed(2)}%
                          </div>
                        </div>

                        <div className="rounded-2xl border border-black/8 bg-white/75 p-4">
                          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block mb-2">
                            Anlagewelt
                          </span>
                          <div className="text-sm font-bold text-slate-900">
                            {etf.category || "Diverse"}
                          </div>
                        </div>

                        <button
                          onClick={() => onAnalyze(etf.ticker)}
                          className="w-full rounded-2xl bg-[var(--accent)] py-4 text-xs font-black uppercase tracking-widest text-white transition-all hover:bg-[var(--accent-strong)]"
                        >
                          Deep Scan Analyse
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            ) : (
              <section className="space-y-6">
                <h2 className="flex items-center gap-3 text-2xl font-black italic text-slate-900">
                  <span className="text-indigo-500">🏢</span> ETF EXPLORER
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {etfs.map((etf) => {
                    const isSelected = selectedEtfs.some(
                      (s) => s.ticker === etf.ticker,
                    );
                    return (
                      <div
                        key={etf.ticker}
                        onClick={() => {
                          if (isSelected) {
                            setSelectedEtfs(
                              selectedEtfs.filter(
                                (s) => s.ticker !== etf.ticker,
                              ),
                            );
                          } else if (selectedEtfs.length < 3) {
                            setSelectedEtfs([...selectedEtfs, etf]);
                          }
                        }}
                        className={`p-6 rounded-3xl border transition-all group relative cursor-pointer ${
                          isSelected
                            ? "bg-[var(--accent-soft)] border-[var(--accent)] animate-pulse-slow"
                            : "bg-white/75 border-black/8 hover:border-[var(--accent)]/25"
                        }`}
                      >
                        {isSelected && (
                          <div className="absolute -top-2 -right-2 flex h-8 w-8 items-center justify-center rounded-full border-4 border-white bg-[var(--accent)] shadow-lg">
                            <span className="text-white text-xs font-black">
                              {selectedEtfs.findIndex(
                                (s) => s.ticker === etf.ticker,
                              ) + 1}
                            </span>
                          </div>
                        )}
                        <div className="flex justify-between items-start mb-6">
                          <div className="min-w-0">
                            <div className="mb-1 text-3xl font-black text-slate-900">
                              {etf.ticker}
                            </div>
                            <div className="truncate text-sm text-slate-500">
                              {etf.name}
                            </div>
                          </div>
                          <div className="shrink-0 rounded-full border border-[var(--accent)]/15 bg-[var(--accent-soft)] px-3 py-1 text-[10px] font-bold text-[var(--accent)]">
                            ETF
                          </div>
                        </div>

                        <div className="grid grid-cols-2 gap-3 mb-6">
                          <div className="rounded-2xl border border-black/8 bg-white/75 p-3">
                            <div className="mb-1 text-[8px] font-bold uppercase text-slate-500">
                              Kosten (TER)
                            </div>
                            <div className="text-lg font-black text-emerald-700">
                              {etf.ter ? `${etf.ter.toFixed(2)}%` : "N/A"}
                            </div>
                          </div>
                          <div className="rounded-2xl border border-black/8 bg-white/75 p-3">
                            <div className="mb-1 text-[8px] font-bold uppercase text-slate-500">
                              Performance (1W)
                            </div>
                            <div
                              className={`text-lg font-black ${(etf.change || 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}
                            >
                              {(etf.change || 0) >= 0 ? "+" : ""}
                              {etf.change?.toFixed(2)}%
                            </div>
                          </div>
                        </div>

                        <div className="rounded-2xl border border-black/8 bg-white/75 p-4">
                          <div className="mb-1 text-[10px] font-bold uppercase tracking-widest text-slate-500">
                            Kategorie
                          </div>
                          <div className="truncate text-sm font-bold text-slate-900">
                            {etf.category || "Diverse"}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            )}
          </div>
        )}

        {activeTab === "alternative" && (
          <div className="space-y-12 animate-in fade-in slide-in-from-bottom-4">
            <section className="space-y-6">
              <h2 className="flex items-center gap-3 text-2xl font-black italic text-slate-900">
                <span className="text-amber-600">Alt</span> CRYPTO ASSETS
              </h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {cryptos.map((coin) => (
                  <div
                    key={coin.ticker}
                    onClick={() => onAnalyze(coin.ticker)}
                    className="surface-panel cursor-pointer rounded-3xl p-6 transition-all hover:border-amber-500/20"
                  >
                    <div className="mb-1 text-2xl font-black text-slate-900">
                      {coin.ticker.replace("-USD", "")}
                    </div>
                    <div className="mb-4 text-[10px] font-bold uppercase tracking-widest text-amber-700">
                      Digital Asset
                    </div>
                    <div className="flex items-baseline justify-between">
                      <div className="text-xl font-mono text-slate-900">
                        {formatPrice(coin.price || 0)}
                      </div>
                      <div
                        className={`text-xs font-bold ${coin.change && coin.change > 0 ? "text-emerald-700" : "text-red-700"}`}
                      >
                        {coin.change && coin.change > 0 ? "+" : ""}
                        {coin.change?.toFixed(2)}%
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="space-y-6">
              <h2 className="flex items-center gap-3 text-2xl font-black italic text-slate-900">
                <span className="text-yellow-600">Hedge</span> COMMODITIES
              </h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {commodities.map((item) => (
                  <div
                    key={item.ticker}
                    onClick={() => onAnalyze(item.ticker)}
                    className="surface-panel cursor-pointer rounded-3xl p-6 transition-all hover:border-yellow-500/20"
                  >
                    <div className="mb-1 text-2xl font-black text-slate-900">
                      {item.ticker === "GC=F"
                        ? "GOLD"
                        : item.ticker === "CL=F"
                          ? "OIL"
                          : item.ticker === "SI=F"
                            ? "SILVER"
                            : item.ticker}
                    </div>
                    <div className="mb-4 text-[10px] font-bold uppercase tracking-widest text-yellow-700">
                      Market Hedge
                    </div>
                    <div className="flex items-baseline justify-between">
                      <div className="text-xl font-mono text-slate-900">
                        {formatPrice(item.price || 0)}
                      </div>
                      <div
                        className={`text-xs font-bold ${(item.change || 0) > 0 ? "text-emerald-700" : "text-red-700"}`}
                      >
                        {(item.change || 0) > 0 ? "+" : ""}
                        {item.change?.toFixed(2)}%
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
};

export default DiscoveryPanel;
