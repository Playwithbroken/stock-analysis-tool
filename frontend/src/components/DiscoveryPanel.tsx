import React, { useEffect, useState } from "react";
import MarketSentiment from "./MarketSentiment";
import { useCurrency } from "../context/CurrencyContext";

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

const DiscoveryPanel: React.FC<DiscoveryPanelProps> = ({ onAnalyze }) => {
  const { formatPrice } = useCurrency();
  const [activeTab, setActiveTab] = useState<
    "overview" | "ai" | "movers" | "alternative" | "etf"
  >("overview");
  const [stars, setStars] = useState<StarAssets | null>(null);
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
      try {
        const [s, t, g, l, r, sc, m, cur, com, hr, e] = await Promise.all([
          fetch("/api/discovery/stars").then((r) => r.json()),
          fetch("/api/discovery/trending").then((r) => r.json()),
          fetch("/api/discovery/gainers").then((r) => r.json()),
          fetch("/api/discovery/losers").then((r) => r.json()),
          fetch("/api/discovery/rebounds").then((r) => r.json()),
          fetch("/api/discovery/small-caps").then((r) => r.json()),
          fetch("/api/discovery/moonshots").then((r) => r.json()),
          fetch("/api/discovery/cryptos").then((r) => r.json()),
          fetch("/api/discovery/commodities").then((r) => r.json()),
          fetch("/api/discovery/high-risk-opportunities").then((r) => r.json()),
          fetch("/api/discovery/etfs").then((r) => r.json()),
        ]);
        setStars(s);
        setTrending(t);
        setGainers(g);
        setLosers(l);
        setRebounds(r);
        setSmallCaps(sc);
        setMoonshots(m);
        setCryptos(cur);
        setCommodities(com);
        setHighRiskOpps(hr);
        setEtfs(e);
      } catch (e) {
        console.error("Discovery fetch failed", e);
      } finally {
        setLoading(false);
      }
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
      const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
      const data = await res.json();
      setSearchResults(data);
    } catch (e) {
      console.error("Search failed", e);
    } finally {
      setIsSearching(false);
    }
  };

  const addSearchedEtf = async (res: any) => {
    // Show loading state or similar if needed
    try {
      // We could use the existing etf discovery logic or a dedicated endpoint
      const response = await fetch(`/api/analysis/basic?ticker=${res.ticker}`);
      const data = await response.json();

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
    } catch (e) {
      console.error("Failed to fetch ETF details", e);
      // Fallback
      if (selectedEtfs.length < 3) {
        setSelectedEtfs([...selectedEtfs, { ...res, ter: 0, change: 0 }]);
      }
    }
    setSearchQuery("");
    setSearchResults([]);
  };

  const tabs = [
    { id: "overview", label: "Markt-Puls", icon: "🌍" },
    { id: "ai", label: "AI Chancen", icon: "🤖" },
    { id: "movers", label: "Top/Flop", icon: "📊" },
    { id: "etf", label: "ETF Welt", icon: "🏢" },
    { id: "alternative", label: "Alternativ", icon: "🪙" },
  ] as const;

  if (loading && !stars) {
    return (
      <div className="space-y-8 p-4 max-w-7xl mx-auto">
        {/* Banner Skeleton */}
        <div className="h-48 w-full bg-linear-to-r from-gray-900 to-black rounded-3xl animate-pulse border border-white/5 relative overflow-hidden">
          <div className="absolute inset-0 bg-white/5 -translate-x-full animate-[shimmer_2s_infinite]"></div>
        </div>

        {/* Grid Skeleton */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="h-40 rounded-3xl bg-[#0a0a0c] border border-white/5 animate-pulse relative overflow-hidden"
            >
              <div className="absolute inset-0 bg-white/5 -translate-x-full animate-[shimmer_2s_infinite]"></div>
            </div>
          ))}
        </div>

        {/* List Skeleton */}
        <div className="space-y-4">
          <div className="h-8 w-48 bg-gray-900 rounded-lg animate-pulse"></div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-32 bg-[#0a0a0c] rounded-2xl border border-white/5 animate-pulse"
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
      <div className="sticky top-20 z-40 flex items-center gap-2 p-1.5 bg-[#0a0a0c]/80 backdrop-blur-xl border border-white/5 rounded-2xl w-fit mx-auto lg:mx-0">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-bold transition-all ${
              activeTab === tab.id
                ? "bg-purple-600 text-white shadow-lg shadow-purple-500/20"
                : "text-gray-400 hover:text-white hover:bg-white/5"
            }`}
          >
            <span>{tab.icon}</span>
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      {activeTab === "etf" && (
        <div className="flex items-center justify-between bg-indigo-500/5 border border-indigo-500/10 rounded-2xl p-4 animate-in fade-in slide-in-from-top-4">
          <div className="flex items-center gap-4">
            <div
              className={`w-10 h-10 rounded-xl flex items-center justify-center transition-colors ${isComparing ? "bg-indigo-500 text-white" : "bg-slate-800 text-slate-500"}`}
            >
              <span className="text-xl font-bold">{selectedEtfs.length}</span>
            </div>
            <div>
              <h4 className="text-sm font-bold text-white">
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
                className="text-xs font-bold text-slate-400 hover:text-white transition-colors"
              >
                Auswahl leeren
              </button>
            )}
            <button
              onClick={() => setIsComparing(!isComparing)}
              disabled={selectedEtfs.length < 2 && !isComparing}
              className={`px-6 py-2.5 rounded-xl text-sm font-bold transition-all ${
                isComparing
                  ? "bg-slate-800 text-white"
                  : selectedEtfs.length >= 2
                    ? "bg-indigo-600 text-white shadow-lg shadow-indigo-500/20"
                    : "bg-slate-800/50 text-slate-600 cursor-not-allowed"
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
            className="w-full bg-slate-800/50 border border-white/5 rounded-2xl py-4 pl-12 pr-4 text-white placeholder-slate-500 focus:outline-hidden focus:ring-2 focus:ring-indigo-500/50 transition-all font-medium"
          />

          {/* Search Results Overlay */}
          {searchQuery.length >= 2 && (
            <div className="absolute top-full left-0 right-0 mt-2 p-2 bg-slate-900 border border-white/10 rounded-2xl shadow-2xl z-50 max-h-96 overflow-y-auto backdrop-blur-xl">
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
                        className="flex items-center justify-between p-3 rounded-xl hover:bg-white/5 cursor-pointer transition-colors group"
                      >
                        <div className="flex items-center gap-4">
                          <div className="w-10 h-10 rounded-lg bg-indigo-500/10 flex items-center justify-center text-indigo-400 font-black text-xs">
                            {res.ticker.slice(0, 2)}
                          </div>
                          <div>
                            <div className="text-sm font-bold text-white group-hover:text-indigo-400 transition-colors">
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
                  <h2 className="text-2xl font-black text-white flex items-center gap-3 italic">
                    <span className="text-yellow-500">⭐</span> STAR SPOTLIGHT
                  </h2>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  {/* Day Winner */}
                  <div
                    onClick={() =>
                      stars.day_winner && onAnalyze(stars.day_winner.ticker)
                    }
                    className="group relative p-6 rounded-3xl bg-linear-to-br from-green-500/10 to-transparent border border-green-500/20 hover:border-green-500/50 cursor-pointer transition-all hover:-translate-y-1 hover:shadow-lg hover:shadow-green-500/10"
                  >
                    <div className="text-[10px] font-bold text-green-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse"></span>
                      Day Winner
                    </div>
                    <div className="text-3xl font-black text-white group-hover:text-green-300 mb-1 transition-colors">
                      {stars.day_winner?.ticker || "N/A"}
                    </div>
                    <div className="text-sm text-gray-500 mb-4 truncate">
                      {stars.day_winner?.name || "No data"}
                    </div>
                    <div className="text-2xl font-mono font-bold text-green-400">
                      +{stars.day_winner?.change?.toFixed(2) || "0.00"}%
                    </div>
                  </div>

                  {/* Week Winner */}
                  <div
                    onClick={() =>
                      stars.week_winner && onAnalyze(stars.week_winner.ticker)
                    }
                    className="group relative p-6 rounded-3xl bg-linear-to-br from-purple-500/10 to-transparent border border-purple-500/20 hover:border-purple-500/50 cursor-pointer transition-all hover:-translate-y-1 hover:shadow-lg hover:shadow-purple-500/10"
                  >
                    <div className="text-[10px] font-bold text-purple-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-purple-500 animate-pulse"></span>
                      Week Winner
                    </div>
                    <div className="text-3xl font-black text-white group-hover:text-purple-300 mb-1 transition-colors">
                      {stars.week_winner?.ticker || "N/A"}
                    </div>
                    <div className="text-sm text-gray-500 mb-4 truncate">
                      {stars.week_winner?.name || "No data"}
                    </div>
                    <div className="text-2xl font-mono font-bold text-purple-400">
                      +{stars.week_winner?.change?.toFixed(2) || "0.00"}%
                    </div>
                  </div>

                  {/* Personalized picks */}
                  {stars.for_you?.length ? (
                    stars.for_you.slice(0, 2).map((stock, idx) => (
                      <div
                        key={stock.ticker || idx}
                        onClick={() => onAnalyze(stock.ticker)}
                        className="group relative p-6 rounded-3xl bg-[#0a0a0c] border border-white/5 hover:border-blue-500/50 cursor-pointer transition-all hover:-translate-y-1"
                      >
                        <div className="text-[10px] font-bold text-blue-400 uppercase tracking-widest mb-4">
                          Picked for you
                        </div>
                        <div className="text-3xl font-black text-white group-hover:text-blue-300 mb-1 transition-colors">
                          {stock.ticker}
                        </div>
                        <div className="text-sm text-gray-500 mb-4 truncate">
                          {stock.name}
                        </div>
                        <div
                          className={`text-2xl font-mono font-bold ${stock.change && stock.change > 0 ? "text-green-400" : "text-red-400"}`}
                        >
                          {stock.change && stock.change > 0 ? "+" : ""}
                          {stock.change?.toFixed(2)}%
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="col-span-2 flex items-center justify-center p-6 rounded-3xl bg-white/5 border border-dashed border-white/10 text-gray-500 text-sm">
                      No personalized picks available yet.
                    </div>
                  )}
                </div>
              </section>
            ) : (
              <div className="text-center py-10 text-gray-500 bg-white/5 rounded-3xl">
                Failed to load market stars.
              </div>
            )}
          </div>
        )}

        {activeTab === "ai" && (
          <div className="space-y-12 animate-in fade-in slide-in-from-bottom-4">
            {/* High-Risk Opps */}
            <section className="space-y-6">
              <h2 className="text-2xl font-black text-white flex items-center gap-3 italic">
                <span className="text-red-500">⚠️</span> HIGH-RISK RADAR
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {highRiskOpps.map((opp: any) => (
                  <div
                    key={opp.ticker}
                    onClick={() => onAnalyze(opp.ticker)}
                    className="p-6 rounded-3xl bg-linear-to-b from-[#111] to-black border border-white/5 hover:border-red-500/30 cursor-pointer transition-all group"
                  >
                    <div className="flex justify-between items-start mb-6">
                      <div>
                        <div className="text-3xl font-black text-white mb-1">
                          {opp.ticker}
                        </div>
                        <div className="text-sm text-gray-500 truncate max-w-[180px]">
                          {opp.name}
                        </div>
                      </div>
                      <div className="bg-red-500/10 px-3 py-1 rounded-full text-[10px] font-bold text-red-400 border border-red-500/20">
                        OPPORTUNITY
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-3 mb-6">
                      {[
                        {
                          label: "Risk",
                          val: opp.risk_score,
                          color: "text-red-400",
                        },
                        {
                          label: "Reward",
                          val: opp.reward_score,
                          color: "text-green-400",
                        },
                        {
                          label: "Score",
                          val: opp.opportunity_score,
                          color: "text-purple-400",
                        },
                      ].map((stat) => (
                        <div
                          key={stat.label}
                          className="text-center p-2 rounded-2xl bg-white/5 border border-white/5"
                        >
                          <div className="text-[8px] font-bold text-gray-500 uppercase mb-1">
                            {stat.label}
                          </div>
                          <div className={`text-lg font-black ${stat.color}`}>
                            {stat.val}
                          </div>
                        </div>
                      ))}
                    </div>

                    <div className="p-4 bg-purple-500/5 border border-purple-500/20 rounded-2xl">
                      <div className="text-[10px] font-bold text-purple-400 uppercase tracking-widest mb-1">
                        AI Recommendation
                      </div>
                      <div className="text-sm font-bold text-white mb-2">
                        {opp.recommendation}
                      </div>
                      <div className="flex gap-2 flex-wrap">
                        {opp.reasons
                          ?.slice(0, 2)
                          .map((r: string, i: number) => (
                            <span
                              key={i}
                              className="text-[9px] text-gray-400 bg-white/5 px-2 py-0.5 rounded-full"
                            >
                              • {r}
                            </span>
                          ))}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {/* Moonshots */}
            <section className="space-y-6">
              <h2 className="text-2xl font-black text-white flex items-center gap-3 italic">
                <span className="text-indigo-500">🚀</span> MOONSHOT SCANNER
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {(moonshots.length > 0 ? moonshots : []).map((stock) => (
                  <div
                    key={stock.ticker}
                    onClick={() => onAnalyze(stock.ticker)}
                    className="p-6 rounded-3xl bg-linear-to-br from-indigo-500/10 to-transparent border border-white/5 hover:border-indigo-500/30 cursor-pointer transition-all"
                  >
                    <div className="flex justify-between items-start mb-6">
                      <div>
                        <div className="text-3xl font-black text-white mb-1">
                          {stock.ticker}
                        </div>
                        <div className="text-sm text-gray-500">
                          {stock.name}
                        </div>
                      </div>
                      <div className="text-[10px] font-bold text-indigo-400 bg-indigo-400/10 px-2 py-1 rounded-lg">
                        GROWTH
                      </div>
                    </div>
                    <div className="space-y-4">
                      <div className="flex justify-between items-center text-xs font-bold">
                        <span className="text-gray-500 uppercase tracking-widest">
                          Potential
                        </span>
                        <span className="text-indigo-400">
                          {stock.score || 85}%
                        </span>
                      </div>
                      <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-indigo-500 rounded-full"
                          style={{ width: `${stock.score || 85}%` }}
                        ></div>
                      </div>
                      <p className="text-[10px] text-gray-400 italic">
                        “{stock.trend_context}”
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
              <h2 className="text-2xl font-black text-white flex items-center gap-3 italic">
                <span className="text-green-500">📈</span> MARKET GAINERS
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {gainers.map((stock) => (
                  <div
                    key={stock.ticker}
                    onClick={() => onAnalyze(stock.ticker)}
                    className="p-5 rounded-2xl bg-green-500/5 border border-green-500/10 hover:border-green-500/40 cursor-pointer transition-all flex items-center justify-between"
                  >
                    <div>
                      <div className="font-black text-white">
                        {stock.ticker}
                      </div>
                      <div className="text-[10px] text-gray-500 truncate max-w-[100px]">
                        {stock.name}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-bold text-green-400">
                        +{stock.change?.toFixed(2)}%
                      </div>
                      <div className="text-[8px] text-gray-600 uppercase font-black">
                        {stock.trend_context}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="space-y-6">
              <h2 className="text-2xl font-black text-white flex items-center gap-3 italic">
                <span className="text-red-500">📉</span> MAJOR DRAWDOWNS
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {losers.map((stock) => (
                  <div
                    key={stock.ticker}
                    onClick={() => onAnalyze(stock.ticker)}
                    className="p-5 rounded-2xl bg-red-500/5 border border-red-500/10 hover:border-red-500/40 cursor-pointer transition-all flex items-center justify-between"
                  >
                    <div>
                      <div className="font-black text-white">
                        {stock.ticker}
                      </div>
                      <div className="text-[10px] text-gray-500 truncate max-w-[100px]">
                        {stock.name}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-bold text-red-400">
                        {stock.change?.toFixed(2)}%
                      </div>
                      <div className="text-[8px] text-gray-600 uppercase font-black">
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
                <h2 className="text-2xl font-black text-white flex items-center gap-3 italic">
                  <span className="text-indigo-500">🏢</span> ETF COMPARISON
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {selectedEtfs.map((etf) => (
                    <div
                      key={etf.ticker}
                      className="p-8 rounded-3xl bg-slate-900 border-2 border-indigo-500/50 relative overflow-hidden"
                    >
                      <div className="absolute top-0 right-0 p-4">
                        <span className="text-xs font-black text-indigo-400 opacity-20">
                          {etf.ticker}
                        </span>
                      </div>
                      <div className="mb-8">
                        <h3 className="text-3xl font-black text-white mb-2">
                          {etf.ticker}
                        </h3>
                        <p className="text-sm text-slate-400 line-clamp-1">
                          {etf.name}
                        </p>
                      </div>

                      <div className="space-y-6">
                        <div className="p-4 bg-white/5 rounded-2xl border border-white/5">
                          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block mb-2">
                            Jährliche Kosten (TER)
                          </span>
                          <div className="text-2xl font-black text-emerald-400">
                            {etf.ter?.toFixed(2)}%
                          </div>
                        </div>

                        <div className="p-4 bg-white/5 rounded-2xl border border-white/5">
                          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block mb-2">
                            Performance (1 Woche)
                          </span>
                          <div
                            className={`text-2xl font-black ${(etf.change || 0) >= 0 ? "text-green-400" : "text-red-400"}`}
                          >
                            {(etf.change || 0) >= 0 ? "+" : ""}
                            {etf.change?.toFixed(2)}%
                          </div>
                        </div>

                        <div className="p-4 bg-white/5 rounded-2xl border border-white/5">
                          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block mb-2">
                            Anlagewelt
                          </span>
                          <div className="text-sm font-bold text-white">
                            {etf.category || "Diverse"}
                          </div>
                        </div>

                        <button
                          onClick={() => onAnalyze(etf.ticker)}
                          className="w-full py-4 bg-indigo-600 hover:bg-indigo-500 text-white rounded-2xl text-xs font-black uppercase tracking-widest transition-all shadow-xl shadow-indigo-600/20"
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
                <h2 className="text-2xl font-black text-white flex items-center gap-3 italic">
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
                            ? "bg-indigo-500/20 border-indigo-500 animate-pulse-slow"
                            : "bg-linear-to-br from-indigo-500/10 to-transparent border-white/5 hover:border-indigo-500/30"
                        }`}
                      >
                        {isSelected && (
                          <div className="absolute -top-2 -right-2 w-8 h-8 bg-indigo-500 rounded-full flex items-center justify-center border-4 border-black shadow-lg">
                            <span className="text-white text-xs font-black">
                              {selectedEtfs.findIndex(
                                (s) => s.ticker === etf.ticker,
                              ) + 1}
                            </span>
                          </div>
                        )}
                        <div className="flex justify-between items-start mb-6">
                          <div className="min-w-0">
                            <div className="text-3xl font-black text-white mb-1">
                              {etf.ticker}
                            </div>
                            <div className="text-sm text-gray-500 truncate">
                              {etf.name}
                            </div>
                          </div>
                          <div className="bg-indigo-500/10 px-3 py-1 rounded-full text-[10px] font-bold text-indigo-400 border border-indigo-500/20 shrink-0">
                            ETF
                          </div>
                        </div>

                        <div className="grid grid-cols-2 gap-3 mb-6">
                          <div className="p-3 rounded-2xl bg-white/5 border border-white/5">
                            <div className="text-[8px] font-bold text-gray-500 uppercase mb-1">
                              Kosten (TER)
                            </div>
                            <div className="text-lg font-black text-emerald-400">
                              {etf.ter ? `${etf.ter.toFixed(2)}%` : "N/A"}
                            </div>
                          </div>
                          <div className="p-3 rounded-2xl bg-white/5 border border-white/5">
                            <div className="text-[8px] font-bold text-gray-500 uppercase mb-1">
                              Performance (1W)
                            </div>
                            <div
                              className={`text-lg font-black ${(etf.change || 0) >= 0 ? "text-green-400" : "text-red-400"}`}
                            >
                              {(etf.change || 0) >= 0 ? "+" : ""}
                              {etf.change?.toFixed(2)}%
                            </div>
                          </div>
                        </div>

                        <div className="p-4 bg-white/5 border border-white/5 rounded-2xl">
                          <div className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-1">
                            Kategorie
                          </div>
                          <div className="text-sm font-bold text-white truncate">
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
              <h2 className="text-2xl font-black text-white flex items-center gap-3 italic">
                <span className="text-orange-500">🪙</span> CRYPTO ASSETS
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {cryptos.map((coin) => (
                  <div
                    key={coin.ticker}
                    onClick={() => onAnalyze(coin.ticker)}
                    className="p-6 rounded-3xl bg-linear-to-br from-orange-500/10 to-transparent border border-orange-500/10 hover:border-orange-500/40 cursor-pointer transition-all"
                  >
                    <div className="text-2xl font-black text-white mb-1">
                      {coin.ticker.replace("-USD", "")}
                    </div>
                    <div className="text-[10px] text-orange-400 font-bold uppercase mb-4 tracking-widest">
                      Digital Asset
                    </div>
                    <div className="flex justify-between items-baseline">
                      <div className="text-xl font-mono text-white">
                        {formatPrice(coin.price || 0)}
                      </div>
                      <div
                        className={`text-xs font-bold ${coin.change && coin.change > 0 ? "text-green-400" : "text-red-400"}`}
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
              <h2 className="text-2xl font-black text-white flex items-center gap-3 italic">
                <span className="text-yellow-500">🔥</span> COMMODITIES
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {commodities.map((item) => (
                  <div
                    key={item.ticker}
                    onClick={() => onAnalyze(item.ticker)}
                    className="p-6 rounded-3xl bg-linear-to-br from-yellow-500/10 to-transparent border border-yellow-500/10 hover:border-yellow-500/40 cursor-pointer transition-all"
                  >
                    <div className="text-2xl font-black text-white mb-1">
                      {item.ticker === "GC=F"
                        ? "GOLD"
                        : item.ticker === "CL=F"
                          ? "OIL"
                          : item.ticker === "SI=F"
                            ? "SILVER"
                            : item.ticker}
                    </div>
                    <div className="text-[10px] text-yellow-500 font-bold uppercase mb-4 tracking-widest">
                      Market Hedge
                    </div>
                    <div className="flex justify-between items-baseline">
                      <div className="text-xl font-mono text-white">
                        {formatPrice(item.price || 0)}
                      </div>
                      <div
                        className={`text-xs font-bold ${item.change && item.change > 0 ? "text-green-400" : "text-red-400"}`}
                      >
                        {item.change && item.change > 0 ? "+" : ""}
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
