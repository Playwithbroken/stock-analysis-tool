import React, { useEffect, useRef, useState } from "react";
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

interface ScreenerRow {
  ticker: string;
  name: string;
  sector?: string;
  price?: number;
  market_cap?: number;
  rsi_14?: number;
  high52_proximity?: number;
  low52_proximity?: number;
}

const DiscoveryPanel: React.FC<DiscoveryPanelProps> = ({ onAnalyze: onAnalyzeRaw }) => {
  const { formatPrice } = useCurrency();
  const [marketView, setMarketView] = useState<"movers" | "explorer">("explorer");
  const [activeTab, setActiveTab] = useState<
    "overview" | "signals" | "ai" | "movers" | "screener" | "alternative" | "etf" | "internals"
  >("signals");
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
  const [selectedEtfDetail, setSelectedEtfDetail] = useState<any | null>(null);
  const [selectedEtfs, setSelectedEtfs] = useState<any[]>([]);
  const [isComparing, setIsComparing] = useState(false);
  const [highRiskOpps, setHighRiskOpps] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [internals, setInternals] = useState<any>(null);
  const [internalsLoading, setInternalsLoading] = useState(false);
  const [screenerRows, setScreenerRows] = useState<ScreenerRow[]>([]);
  const [screenerLoading, setScreenerLoading] = useState(false);
  const [screenerSector, setScreenerSector] = useState("");
  const [screenerRsi, setScreenerRsi] = useState("30");
  const [screenerHigh52, setScreenerHigh52] = useState("");
  const [screenerLow52, setScreenerLow52] = useState("");
  const [screenerSortBy, setScreenerSortBy] = useState<"rsi_14" | "market_cap" | "high52_proximity" | "low52_proximity">("rsi_14");
  const [screenerSortDirection, setScreenerSortDirection] = useState<"asc" | "desc">("asc");
  const [selectedMarketDetail, setSelectedMarketDetail] = useState<DiscoveryStock | null>(null);
  const [selectedMarketDetailScope, setSelectedMarketDetailScope] = useState<"movers" | "ai" | "alternative" | null>(null);
  const analyzeEnabledAtRef = useRef(0);

  const onAnalyze = (ticker: string) => {
    const symbol = (ticker || "").trim().toUpperCase();
    if (!symbol) return;
    if (Date.now() < analyzeEnabledAtRef.current) return;
    onAnalyzeRaw(symbol);
  };

  const openMarketDetails = (
    stock: DiscoveryStock,
    scope: "movers" | "ai" | "alternative" = "movers",
  ) => {
    if (!stock?.ticker) return;
    setSelectedMarketDetail(stock);
    setSelectedMarketDetailScope(scope);
  };

  const toggleEtfCompare = (etf: any) => {
    const isSelected = selectedEtfs.some((s) => s.ticker === etf.ticker);
    if (isSelected) {
      setSelectedEtfs(selectedEtfs.filter((s) => s.ticker !== etf.ticker));
      return;
    }
    if (selectedEtfs.length < 3) {
      setSelectedEtfs([...selectedEtfs, etf]);
    }
  };

  useEffect(() => {
    const fetchAll = async () => {
      setLoading(true);

      const safeFetch = <T,>(url: string) =>
        withTimeout(fetchJsonWithRetry<T>(url, undefined, { retries: 1, retryDelayMs: 800 }));

      const results = await Promise.allSettled([
        safeFetch<StarAssets>("/api/discovery/stars"),
        safeFetch<PublicSignalsData>("/api/discovery/public-signals"),
        safeFetch<SignalWatchlistData>("/api/signals/watchlist"),
        safeFetch<DiscoveryStock[]>("/api/discovery/trending"),
        safeFetch<DiscoveryStock[]>("/api/discovery/gainers"),
        safeFetch<DiscoveryStock[]>("/api/discovery/losers"),
        safeFetch<DiscoveryStock[]>("/api/discovery/rebounds"),
        safeFetch<DiscoveryStock[]>("/api/discovery/small-caps"),
        safeFetch<DiscoveryStock[]>("/api/discovery/moonshots"),
        safeFetch<DiscoveryStock[]>("/api/discovery/cryptos"),
        safeFetch<DiscoveryStock[]>("/api/discovery/commodities"),
        safeFetch<any[]>("/api/discovery/high-risk-opportunities"),
        safeFetch<any[]>("/api/discovery/etfs"),
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

  // Lazy-load market internals when tab selected
  useEffect(() => {
    if (activeTab !== "internals" || internals) return;
    let cancelled = false;
    (async () => {
      setInternalsLoading(true);
      try {
        const data = await fetchJsonWithRetry<any>("/api/market/internals", undefined, { retries: 1, retryDelayMs: 800 });
        if (!cancelled) setInternals(data);
      } catch { /* ignore */ }
      if (!cancelled) setInternalsLoading(false);
    })();
    return () => { cancelled = true; };
  }, [activeTab, internals]);

  const runScreener = async () => {
    setScreenerLoading(true);
    try {
      const params = new URLSearchParams();
      if (screenerRsi.trim()) params.set("rsi_max", screenerRsi.trim());
      if (screenerSector.trim()) params.set("sector", screenerSector.trim());
      if (screenerHigh52.trim()) params.set("high52_proximity", screenerHigh52.trim());
      if (screenerLow52.trim()) params.set("low52_proximity", screenerLow52.trim());
      params.set("limit", "40");
      const rows = await fetchJsonWithRetry<ScreenerRow[]>(`/api/screener?${params.toString()}`);
      setScreenerRows(Array.isArray(rows) ? rows : []);
    } catch {
      setScreenerRows([]);
    } finally {
      setScreenerLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab !== "screener") return;
    if (screenerRows.length > 0) return;
    runScreener();
  }, [activeTab]);

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
    { id: "signals", label: "Signals", icon: "SG", view: "explorer" as const },
    { id: "overview", label: "Markt-Puls", icon: "MP", view: "movers" as const },
    { id: "ai", label: "AI Chancen", icon: "AI", view: "movers" as const },
    { id: "movers", label: "Top/Flop", icon: "TF", view: "movers" as const },
    { id: "screener", label: "Screener", icon: "SC", view: "explorer" as const },
    { id: "etf", label: "ETF Welt", icon: "ETF", view: "explorer" as const },
    { id: "alternative", label: "Alternativ", icon: "ALT", view: "movers" as const },
    { id: "internals", label: "Internals", icon: "⚖", view: "explorer" as const },
  ] as const;
  const visibleTabs = tabs.filter((tab) => tab.view === marketView);

  useEffect(() => {
    const activeVisible = visibleTabs.some((tab) => tab.id === activeTab);
    if (!activeVisible) {
      setActiveTab(visibleTabs[0]?.id ?? "overview");
    }
  }, [activeTab, marketView, visibleTabs]);

  useEffect(() => {
    // Defensive click-through guard when switching discovery modes/tabs.
    analyzeEnabledAtRef.current = Date.now() + 1200;
    if (activeTab !== "etf") {
      setSelectedEtfDetail(null);
    }
    if (activeTab !== "movers" && activeTab !== "ai" && activeTab !== "alternative") {
      setSelectedMarketDetail(null);
      setSelectedMarketDetailScope(null);
      return;
    }
    if (selectedMarketDetailScope && selectedMarketDetailScope !== activeTab) {
      setSelectedMarketDetail(null);
      setSelectedMarketDetailScope(null);
    }
  }, [activeTab, marketView, selectedMarketDetailScope]);

  const sortedScreenerRows = [...screenerRows].sort((a, b) => {
    const aValue = Number(a?.[screenerSortBy] ?? 0);
    const bValue = Number(b?.[screenerSortBy] ?? 0);
    if (screenerSortDirection === "asc") {
      return aValue - bValue;
    }
    return bValue - aValue;
  });

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
      <div className="surface-panel flex flex-wrap items-center justify-between gap-3 rounded-2xl p-3">
        <div className="text-[11px] font-extrabold uppercase tracking-[0.2em] text-slate-500">
          Discovery Mode
        </div>
        <div className="rounded-full border border-black/8 bg-white/75 p-1">
          <button
            type="button"
            onClick={() => setMarketView("movers")}
            className={`rounded-full px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.14em] transition-colors ${
              marketView === "movers" ? "bg-[#101114] text-white" : "text-slate-500 hover:text-slate-900"
            }`}
          >
            Top Movers
          </button>
          <button
            type="button"
            onClick={() => setMarketView("explorer")}
            className={`rounded-full px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.14em] transition-colors ${
              marketView === "explorer" ? "bg-[#101114] text-white" : "text-slate-500 hover:text-slate-900"
            }`}
          >
            Market Explorer
          </button>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="no-scrollbar sticky top-16 z-40 -mx-1 overflow-x-auto px-1 md:top-20">
        <div className="surface-panel inline-flex min-w-max items-center gap-2 rounded-2xl p-1.5">
          {visibleTabs.map((tab) => (
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
        <div className="surface-panel flex flex-col gap-4 rounded-2xl p-4 animate-in fade-in slide-in-from-top-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-4 sm:items-center">
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
          <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:items-center">
            {selectedEtfs.length > 0 && (
              <button
                onClick={() => setSelectedEtfs([])}
                className="text-left text-xs font-bold text-slate-500 transition-colors hover:text-slate-900 sm:text-right"
              >
                Auswahl leeren
              </button>
            )}
            <button
              onClick={() => setIsComparing(!isComparing)}
              disabled={selectedEtfs.length < 2 && !isComparing}
              className={`w-full rounded-xl px-6 py-2.5 text-sm font-bold transition-all sm:w-auto ${
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
        <div className="relative w-full max-w-2xl lg:mx-0">
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
                  <div className="surface-panel group relative rounded-3xl p-6 transition-all hover:-translate-y-1 hover:border-green-500/20">
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
                    {stars.day_winner?.ticker ? (
                      <button
                        type="button"
                        onClick={() => onAnalyze(stars.day_winner!.ticker)}
                        className="mt-4 rounded-full border border-black/10 bg-white px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-700 transition-colors hover:border-[var(--accent)]/30 hover:text-[var(--accent)]"
                      >
                        Analyze
                      </button>
                    ) : null}
                  </div>

                  {/* Week Winner */}
                  <div className="surface-panel group relative rounded-3xl p-6 transition-all hover:-translate-y-1 hover:border-[var(--accent)]/20">
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
                    {stars.week_winner?.ticker ? (
                      <button
                        type="button"
                        onClick={() => onAnalyze(stars.week_winner!.ticker)}
                        className="mt-4 rounded-full border border-black/10 bg-white px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-700 transition-colors hover:border-[var(--accent)]/30 hover:text-[var(--accent)]"
                      >
                        Analyze
                      </button>
                    ) : null}
                  </div>

                  {/* Personalized picks */}
                  {stars.for_you?.length ? (
                    stars.for_you.slice(0, 2).map((stock, idx) => (
                      <div
                        key={stock.ticker || idx}
                        className="surface-panel group relative rounded-3xl p-6 transition-all hover:-translate-y-1 hover:border-sky-500/20"
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
                        {stock.ticker ? (
                          <button
                            type="button"
                            onClick={() => onAnalyze(stock.ticker)}
                            className="mt-4 rounded-full border border-black/10 bg-white px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-700 transition-colors hover:border-[var(--accent)]/30 hover:text-[var(--accent)]"
                          >
                            Analyze
                          </button>
                        ) : null}
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
            {selectedMarketDetail && selectedMarketDetailScope === "ai" ? (
              <section className="surface-panel rounded-[1.8rem] p-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                      AI Details
                    </div>
                    <div className="mt-2 text-3xl font-black text-slate-900">
                      {selectedMarketDetail.ticker}
                    </div>
                    <div className="mt-1 text-sm text-slate-500">
                      {selectedMarketDetail.name}
                    </div>
                    <div className={`mt-3 text-xl font-black ${(selectedMarketDetail.change || 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                      {(selectedMarketDetail.change || 0) >= 0 ? "+" : ""}
                      {(selectedMarketDetail.change || 0).toFixed(2)}%
                    </div>
                    <div className="mt-2 text-xs text-slate-500">
                      {selectedMarketDetail.trend_context || selectedMarketDetail.reason || "No additional context"}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedMarketDetail(null);
                        setSelectedMarketDetailScope(null);
                      }}
                      className="rounded-full border border-black/8 bg-white px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-600"
                    >
                      Close
                    </button>
                    <button
                      type="button"
                      onClick={() => onAnalyze(selectedMarketDetail.ticker)}
                      className="rounded-full bg-[var(--accent)] px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-white"
                    >
                      Analyze
                    </button>
                  </div>
                </div>
              </section>
            ) : null}

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
                    onClick={() =>
                      openMarketDetails(
                        {
                          ticker: opp.ticker,
                          name: opp.name || opp.ticker,
                          change: typeof opp.change === "number" ? opp.change : 0,
                          score: typeof opp.opportunity_score === "number" ? opp.opportunity_score : undefined,
                          trend_context: opp.recommendation || "AI opportunity setup",
                          reason: Array.isArray(opp.reasons) ? opp.reasons.slice(0, 2).join(" | ") : undefined,
                        },
                        "ai",
                      )
                    }
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
                    onClick={() => openMarketDetails(stock, "ai")}
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
            {selectedMarketDetail && selectedMarketDetailScope === "movers" ? (
              <section className="surface-panel rounded-[1.8rem] p-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                      Market Details
                    </div>
                    <div className="mt-2 text-3xl font-black text-slate-900">
                      {selectedMarketDetail.ticker}
                    </div>
                    <div className="mt-1 text-sm text-slate-500">
                      {selectedMarketDetail.name}
                    </div>
                    <div className={`mt-3 text-xl font-black ${(selectedMarketDetail.change || 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                      {(selectedMarketDetail.change || 0) >= 0 ? "+" : ""}
                      {(selectedMarketDetail.change || 0).toFixed(2)}%
                    </div>
                    <div className="mt-2 text-xs text-slate-500">
                      {selectedMarketDetail.trend_context || selectedMarketDetail.reason || "No additional context"}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedMarketDetail(null);
                        setSelectedMarketDetailScope(null);
                      }}
                      className="rounded-full border border-black/8 bg-white px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-600"
                    >
                      Close
                    </button>
                    <button
                      type="button"
                      onClick={() => onAnalyze(selectedMarketDetail.ticker)}
                      className="rounded-full bg-[var(--accent)] px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-white"
                    >
                      Analyze
                    </button>
                  </div>
                </div>
              </section>
            ) : null}

            <section className="space-y-6">
              <h2 className="flex items-center gap-3 text-2xl font-black italic text-slate-900">
                <span className="text-emerald-700">Up</span> MARKET GAINERS
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {gainers.map((stock) => (
                  <div
                    key={stock.ticker}
                    onClick={() => openMarketDetails(stock)}
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
                    onClick={() => openMarketDetails(stock)}
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
                {selectedEtfDetail ? (
                  <div className="surface-panel rounded-[1.8rem] p-5">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div>
                        <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                          ETF Details
                        </div>
                        <div className="mt-2 text-3xl font-black text-slate-900">
                          {selectedEtfDetail.ticker}
                        </div>
                        <div className="mt-1 text-sm text-slate-500">
                          {selectedEtfDetail.name}
                        </div>
                        <div className={`mt-3 text-xl font-black ${(selectedEtfDetail.change || 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                          {(selectedEtfDetail.change || 0) >= 0 ? "+" : ""}
                          {(selectedEtfDetail.change || 0).toFixed(2)}%
                        </div>
                        <div className="mt-2 text-xs text-slate-500">
                          Category: {selectedEtfDetail.category || "Diverse"} · TER: {selectedEtfDetail.ter ? `${selectedEtfDetail.ter.toFixed(2)}%` : "N/A"}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => setSelectedEtfDetail(null)}
                          className="rounded-full border border-black/8 bg-white px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-600"
                        >
                          Close
                        </button>
                        <button
                          type="button"
                          onClick={() => toggleEtfCompare(selectedEtfDetail)}
                          className="rounded-full border border-black/8 bg-white px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-700"
                        >
                          {selectedEtfs.some((s) => s.ticker === selectedEtfDetail.ticker) ? "Remove Compare" : "Add Compare"}
                        </button>
                        <button
                          type="button"
                          onClick={() => onAnalyze(selectedEtfDetail.ticker)}
                          className="rounded-full bg-[var(--accent)] px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-white"
                        >
                          Analyze
                        </button>
                      </div>
                    </div>
                  </div>
                ) : null}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {etfs.map((etf) => {
                    const isSelected = selectedEtfs.some(
                      (s) => s.ticker === etf.ticker,
                    );
                    return (
                      <div
                        key={etf.ticker}
                        onClick={() => setSelectedEtfDetail(etf)}
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
                        <div className="mt-4 flex items-center gap-2">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleEtfCompare(etf);
                            }}
                            className="rounded-full border border-black/8 bg-white px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-700"
                          >
                            {isSelected ? "Remove Compare" : "Add Compare"}
                          </button>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              onAnalyze(etf.ticker);
                            }}
                            className="rounded-full bg-[var(--accent)] px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.14em] text-white"
                          >
                            Analyze
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            )}
          </div>
        )}

        {activeTab === "screener" && (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4">
            <section className="surface-panel rounded-[2rem] p-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                    Screener
                  </div>
                  <h3 className="mt-2 text-2xl text-slate-900">
                    RSI, Sector und 52W Filter
                  </h3>
                </div>
                <div className="rounded-full border border-black/8 bg-white px-3 py-1 text-xs font-bold text-slate-500">
                  {sortedScreenerRows.length} Treffer
                </div>
              </div>

              <div className="mt-4 grid gap-3 md:grid-cols-5">
                <input
                  value={screenerRsi}
                  onChange={(e) => setScreenerRsi(e.target.value)}
                  placeholder="RSI max (z.B. 30)"
                  className="rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800"
                />
                <input
                  value={screenerSector}
                  onChange={(e) => setScreenerSector(e.target.value)}
                  placeholder="Sector (z.B. Technology)"
                  className="rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800"
                />
                <input
                  value={screenerHigh52}
                  onChange={(e) => setScreenerHigh52(e.target.value)}
                  placeholder="Nahe 52W High <= %"
                  className="rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800"
                />
                <input
                  value={screenerLow52}
                  onChange={(e) => setScreenerLow52(e.target.value)}
                  placeholder="Nahe 52W Low <= %"
                  className="rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800"
                />
                <button
                  onClick={runScreener}
                  disabled={screenerLoading}
                  className="rounded-xl bg-[var(--accent)] px-4 py-3 text-xs font-extrabold uppercase tracking-[0.16em] text-white disabled:opacity-60"
                >
                  {screenerLoading ? "Lade..." : "Scan"}
                </button>
              </div>
            </section>

            <section className="surface-panel overflow-hidden rounded-[2rem] p-0">
              <div className="border-b border-black/6 px-6 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                    Filter-Ergebnisse
                  </div>
                  <div className="flex gap-2">
                    <select
                      value={screenerSortBy}
                      onChange={(e) =>
                        setScreenerSortBy(
                          e.target.value as "rsi_14" | "market_cap" | "high52_proximity" | "low52_proximity",
                        )
                      }
                      className="rounded-lg border border-black/8 bg-white px-3 py-1.5 text-xs font-bold text-slate-700"
                    >
                      <option value="rsi_14">Sort: RSI</option>
                      <option value="market_cap">Sort: Market Cap</option>
                      <option value="high52_proximity">Sort: 52W High Dist.</option>
                      <option value="low52_proximity">Sort: 52W Low Dist.</option>
                    </select>
                    <button
                      onClick={() =>
                        setScreenerSortDirection((prev) => (prev === "asc" ? "desc" : "asc"))
                      }
                      className="rounded-lg border border-black/8 bg-white px-3 py-1.5 text-xs font-bold text-slate-700"
                    >
                      {screenerSortDirection === "asc" ? "Asc" : "Desc"}
                    </button>
                  </div>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-[860px] text-sm">
                  <thead>
                    <tr className="border-b border-black/6 bg-black/[0.02] text-left text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                      <th className="px-5 py-3">Ticker</th>
                      <th className="px-4 py-3">Name</th>
                      <th className="px-4 py-3">Sector</th>
                      <th className="px-4 py-3 text-right">Price</th>
                      <th className="px-4 py-3 text-right">RSI</th>
                      <th className="px-4 py-3 text-right">MCap</th>
                      <th className="px-4 py-3 text-right">Dist. 52W High</th>
                      <th className="px-4 py-3 text-right">Dist. 52W Low</th>
                      <th className="px-5 py-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {screenerLoading ? (
                      <tr>
                        <td colSpan={9} className="px-5 py-5 text-sm text-slate-500">
                          Screener wird geladen...
                        </td>
                      </tr>
                    ) : sortedScreenerRows.length === 0 ? (
                      <tr>
                        <td colSpan={9} className="px-5 py-5 text-sm text-slate-500">
                          Keine Ergebnisse fuer die aktuellen Filter.
                        </td>
                      </tr>
                    ) : (
                      sortedScreenerRows.map((row) => (
                        <tr key={row.ticker} className="border-b border-black/6 last:border-b-0">
                          <td className="px-5 py-4 text-sm font-extrabold text-slate-900">{row.ticker}</td>
                          <td className="px-4 py-4 text-sm text-slate-600">{row.name}</td>
                          <td className="px-4 py-4 text-sm text-slate-600">{row.sector || "-"}</td>
                          <td className="px-4 py-4 text-right text-sm font-semibold text-slate-700">
                            {row.price != null ? formatPrice(row.price) : "-"}
                          </td>
                          <td className="px-4 py-4 text-right text-sm font-semibold text-slate-700">
                            {row.rsi_14 != null ? row.rsi_14.toFixed(1) : "-"}
                          </td>
                          <td className="px-4 py-4 text-right text-sm font-semibold text-slate-700">
                            {row.market_cap != null ? `${(row.market_cap / 1e9).toFixed(1)}B` : "-"}
                          </td>
                          <td className="px-4 py-4 text-right text-sm font-semibold text-slate-700">
                            {row.high52_proximity != null ? `${row.high52_proximity.toFixed(1)}%` : "-"}
                          </td>
                          <td className="px-4 py-4 text-right text-sm font-semibold text-slate-700">
                            {row.low52_proximity != null ? `${row.low52_proximity.toFixed(1)}%` : "-"}
                          </td>
                          <td className="px-5 py-4 text-right">
                            <button
                              onClick={() => onAnalyze(row.ticker)}
                              className="rounded-lg border border-black/8 bg-white px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-slate-700"
                            >
                              Analyze
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        )}

        {activeTab === "alternative" && (
          <div className="space-y-12 animate-in fade-in slide-in-from-bottom-4">
            {selectedMarketDetail && selectedMarketDetailScope === "alternative" ? (
              <section className="surface-panel rounded-[1.8rem] p-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                      Alternative Details
                    </div>
                    <div className="mt-2 text-3xl font-black text-slate-900">
                      {selectedMarketDetail.ticker}
                    </div>
                    <div className="mt-1 text-sm text-slate-500">
                      {selectedMarketDetail.name}
                    </div>
                    <div className={`mt-3 text-xl font-black ${(selectedMarketDetail.change || 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                      {(selectedMarketDetail.change || 0) >= 0 ? "+" : ""}
                      {(selectedMarketDetail.change || 0).toFixed(2)}%
                    </div>
                    <div className="mt-2 text-xs text-slate-500">
                      {selectedMarketDetail.trend_context || selectedMarketDetail.reason || "No additional context"}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedMarketDetail(null);
                        setSelectedMarketDetailScope(null);
                      }}
                      className="rounded-full border border-black/8 bg-white px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-600"
                    >
                      Close
                    </button>
                    <button
                      type="button"
                      onClick={() => onAnalyze(selectedMarketDetail.ticker)}
                      className="rounded-full bg-[var(--accent)] px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-white"
                    >
                      Analyze
                    </button>
                  </div>
                </div>
              </section>
            ) : null}

            <section className="space-y-6">
              <h2 className="flex items-center gap-3 text-2xl font-black italic text-slate-900">
                <span className="text-amber-600">Alt</span> CRYPTO ASSETS
              </h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {cryptos.map((coin) => (
                  <div
                    key={coin.ticker}
                    onClick={() => openMarketDetails(coin, "alternative")}
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
                    onClick={() => openMarketDetails(item, "alternative")}
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
        {activeTab === "internals" && (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4">
            {internalsLoading ? (
              <div className="grid gap-4 md:grid-cols-2">
                {[1,2,3,4].map(i => (
                  <div key={i} className="h-40 rounded-2xl border border-black/8 bg-white/75 animate-pulse" />
                ))}
              </div>
            ) : internals ? (
              <>
                {/* VIX & Term Structure */}
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                  {internals.vix && (
                    <div className="surface-panel rounded-[1.6rem] p-5">
                      <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">VIX</div>
                      <div className={`mt-2 text-3xl font-black ${(internals.vix.current || 0) > 25 ? "text-red-700" : (internals.vix.current || 0) > 18 ? "text-amber-700" : "text-emerald-700"}`}>
                        {internals.vix.current ?? "N/A"}
                      </div>
                      <div className="mt-2 flex items-center gap-2">
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${
                          internals.vix.term_structure === "contango" ? "bg-emerald-500/10 text-emerald-700" : "bg-red-500/10 text-red-700"
                        }`}>
                          {internals.vix.term_structure}
                        </span>
                        {internals.vix.contango_pct != null && (
                          <span className="text-xs text-slate-500">{internals.vix.contango_pct > 0 ? "+" : ""}{internals.vix.contango_pct}%</span>
                        )}
                      </div>
                      {internals.vix.vix3m && (
                        <div className="mt-2 text-xs text-slate-500">VIX3M: {internals.vix.vix3m}</div>
                      )}
                      {internals.vix.history_5d?.length > 0 && (
                        <div className="mt-3 flex items-end gap-1 h-8">
                          {internals.vix.history_5d.map((v: number, i: number) => {
                            const max = Math.max(...internals.vix.history_5d);
                            const min = Math.min(...internals.vix.history_5d);
                            const range = max - min || 1;
                            const h = 20 + ((v - min) / range) * 80;
                            return (
                              <div key={i} className={`w-full rounded-sm ${v > 25 ? "bg-red-400" : v > 18 ? "bg-amber-400" : "bg-emerald-400"}`} style={{ height: `${h}%` }} />
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}
                  {internals.fear_greed && internals.fear_greed[0] && (
                    <div className="surface-panel rounded-[1.6rem] p-5">
                      <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">Fear & Greed</div>
                      <div className={`mt-2 text-3xl font-black ${
                        internals.fear_greed[0].value > 60 ? "text-emerald-700" : internals.fear_greed[0].value < 40 ? "text-red-700" : "text-amber-700"
                      }`}>
                        {internals.fear_greed[0].value}
                      </div>
                      <div className="mt-1 text-xs font-bold uppercase text-slate-500">{internals.fear_greed[0].label}</div>
                      <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
                        <div
                          className={`h-full rounded-full transition-all ${
                            internals.fear_greed[0].value > 60 ? "bg-emerald-500" : internals.fear_greed[0].value < 40 ? "bg-red-500" : "bg-amber-400"
                          }`}
                          style={{ width: `${internals.fear_greed[0].value}%` }}
                        />
                      </div>
                      <div className="mt-3 flex items-end gap-1 h-8">
                        {internals.fear_greed.slice(0, 7).reverse().map((d: any, i: number) => (
                          <div key={i} className={`w-full rounded-sm ${d.value > 60 ? "bg-emerald-400" : d.value < 40 ? "bg-red-400" : "bg-amber-300"}`} style={{ height: `${20 + d.value * 0.8}%` }} />
                        ))}
                      </div>
                    </div>
                  )}
                  {internals.put_call_ratio != null && (
                    <div className="surface-panel rounded-[1.6rem] p-5">
                      <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">Put/Call Ratio</div>
                      <div className={`mt-2 text-3xl font-black ${
                        internals.put_call_ratio > 1.2 ? "text-red-700" : internals.put_call_ratio < 0.7 ? "text-emerald-700" : "text-amber-700"
                      }`}>
                        {internals.put_call_ratio}
                      </div>
                      <div className="mt-2 text-xs text-slate-500">
                        {internals.put_call_ratio > 1.2 ? "Bearish bias — more puts" : internals.put_call_ratio < 0.7 ? "Bullish bias — more calls" : "Neutral positioning"}
                      </div>
                    </div>
                  )}
                  {internals.yield_spread && (
                    <div className="surface-panel rounded-[1.6rem] p-5">
                      <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">Yield Spread</div>
                      <div className={`mt-2 text-3xl font-black ${
                        internals.yield_spread.inverted ? "text-red-700" : "text-emerald-700"
                      }`}>
                        {internals.yield_spread.spread != null ? `${internals.yield_spread.spread > 0 ? "+" : ""}${internals.yield_spread.spread}%` : "N/A"}
                      </div>
                      <div className={`mt-1 rounded-full inline-flex px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${
                        internals.yield_spread.inverted ? "bg-red-500/10 text-red-700" : "bg-emerald-500/10 text-emerald-700"
                      }`}>
                        {internals.yield_spread.inverted ? "⚠ Inverted" : "Normal"}
                      </div>
                      <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-slate-500">
                        <div>13W: {internals.yield_spread.t13w ?? "N/A"}%</div>
                        <div>10Y: {internals.yield_spread.t10y ?? "N/A"}%</div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Sector Breadth Heatmap */}
                {internals.breadth && (
                  <div className="surface-panel rounded-[2rem] p-5">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                        Sector Breadth
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-bold text-emerald-700">
                          ▲ {internals.breadth.advancing_sectors}
                        </span>
                        <span className="rounded-full bg-red-500/10 px-2 py-0.5 text-[10px] font-bold text-red-700">
                          ▼ {internals.breadth.declining_sectors}
                        </span>
                        <span className="text-[10px] font-bold text-slate-500">
                          A/D {internals.breadth.ratio}
                        </span>
                      </div>
                    </div>
                    <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
                      {(internals.breadth.sectors || []).map((s: any) => (
                        <button
                          key={s.symbol}
                          onClick={() => onAnalyze(s.symbol)}
                          className="rounded-[1.2rem] border border-black/8 bg-white/70 p-3 text-left transition-colors hover:bg-white"
                        >
                          <div className="text-xs font-black text-slate-900">{s.symbol}</div>
                          <div className={`mt-1 text-lg font-black ${(s.change_1d || 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                            {(s.change_1d || 0) >= 0 ? "+" : ""}{s.change_1d?.toFixed(2)}%
                          </div>
                          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
                            <div
                              className={`h-full rounded-full ${(s.change_1d || 0) >= 0 ? "bg-emerald-500" : "bg-red-500"}`}
                              style={{ width: `${Math.min(Math.abs(s.change_1d || 0) * 20, 100)}%` }}
                            />
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="surface-panel rounded-[2rem] p-8 text-center text-sm text-slate-500">
                Market Internals konnten nicht geladen werden.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default DiscoveryPanel;
