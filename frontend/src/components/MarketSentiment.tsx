import React, { useEffect, useState } from "react";
import { Zap, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { useCurrency } from "../context/CurrencyContext";

interface HeatmapItem {
  sector: string;
  sentiment_score: number;
  status: string;
  strength: number;
  hot_stocks?: {
    ticker: string;
    price: number;
    change_1w: number;
    name: string;
  }[];
}

interface MarketSentimentProps {
  onAnalyze?: (ticker: string) => void;
}

export default function MarketSentiment({ onAnalyze }: MarketSentimentProps) {
  const { formatPrice } = useCurrency();
  const [heatmap, setHeatmap] = useState<HeatmapItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/discovery/sentiment-heatmap")
      .then((res) => res.json())
      .then((data) => setHeatmap(data))
      .catch((err) => console.error("Heatmap fetch error:", err))
      .finally(() => setLoading(false));
  }, []);

  if (loading)
    return <div className="h-48 glass-card animate-pulse rounded-2xl"></div>;

  return (
    <div className="space-y-6">
      <h2 className="text-3xl font-bold text-white flex items-center gap-3">
        <span className="text-pink-500">🌍</span> Global Market Pulse
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {heatmap
          .sort((a, b) => b.strength - a.strength)
          .map((item) => {
            const isBullish = item.sentiment_score > 0;
            const sortedStocks = [...(item.hot_stocks || [])].sort(
              (a, b) => b.change_1w - a.change_1w,
            );

            return (
              <div
                key={item.sector}
                className={`p-5 rounded-2xl border transition-all duration-300 hover:scale-[1.02] group relative ${
                  isBullish
                    ? "bg-linear-to-br from-green-500/10 to-transparent border-green-500/20 hover:border-green-500/50"
                    : "bg-linear-to-br from-red-500/10 to-transparent border-red-500/20 hover:border-red-500/50"
                } hover:z-50`}
              >
                {/* Glow background */}
                <div
                  className={`absolute -inset-1 opacity-0 group-hover:opacity-10 transition-opacity blur-2xl rounded-2xl ${isBullish ? "bg-green-500" : "bg-red-500"}`}
                ></div>

                <div className="relative z-10">
                  <div className="flex justify-between items-start mb-4">
                    <h4 className="text-[10px] font-bold uppercase tracking-[0.2em] text-gray-400">
                      {item.sector}
                    </h4>
                    {isBullish ? (
                      <TrendingUp size={14} className="text-green-400" />
                    ) : (
                      <TrendingDown size={14} className="text-red-400" />
                    )}
                  </div>

                  <div className="flex items-baseline gap-2 mb-1">
                    <span
                      className={`text-2xl font-black italic tracking-tighter ${isBullish ? "text-green-400" : "text-red-400"}`}
                    >
                      {item.status}
                    </span>
                  </div>

                  <div className="mt-4 h-1 w-full bg-white/5 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-1000 ${isBullish ? "bg-green-500 shadow-[0_0_12px_rgba(34,197,94,0.6)]" : "bg-red-500 shadow-[0_0_12px_rgba(239,68,68,0.6)]"}`}
                      style={{ width: `${item.strength}%` }}
                    ></div>
                  </div>

                  <div className="flex justify-between items-center mt-2">
                    <span className="text-[10px] text-gray-500 font-bold uppercase tracking-widest">
                      Verfassung
                    </span>
                    <span
                      className={`text-[10px] font-mono font-bold ${isBullish ? "text-green-400" : "text-red-400"}`}
                    >
                      {item.strength.toFixed(0)}%
                    </span>
                  </div>

                  {/* Hot Stocks Popover on Hover */}
                  {sortedStocks.length > 0 && (
                    <div className="absolute top-[85%] left-0 right-0 opacity-0 group-hover:opacity-100 pointer-events-none group-hover:pointer-events-auto transition-all duration-300 z-100 transform translate-y-4 group-hover:translate-y-2">
                      <div className="bg-black/95 border border-white/10 rounded-xl p-3 shadow-2xl shadow-black backdrop-blur-md ring-1 ring-white/5">
                        <div className="text-[9px] font-bold text-gray-400 uppercase tracking-[0.3em] mb-3 pb-2 border-b border-white/5 flex items-center gap-2">
                          <Zap
                            size={10}
                            className="text-yellow-400 fill-yellow-400"
                          />
                          Hot Assets
                        </div>
                        <div className="space-y-1">
                          {sortedStocks.map((stock) => (
                            <div
                              key={stock.ticker}
                              onClick={() => onAnalyze?.(stock.ticker)}
                              className="flex items-center justify-between p-2 hover:bg-white/5 rounded-lg transition-all cursor-pointer group/stock"
                            >
                              <div className="flex flex-col">
                                <span className="text-white text-xs font-bold group-hover/stock:text-pink-400 transition-colors">
                                  {stock.ticker}
                                </span>
                                <span className="text-[8px] text-gray-500 truncate max-w-[70px]">
                                  {stock.name}
                                </span>
                              </div>
                              <div className="text-right">
                                <div className="text-white text-[10px] font-mono font-medium">
                                  {formatPrice(stock.price)}
                                </div>
                                <div
                                  className={`text-[9px] font-black ${stock.change_1w >= 0 ? "text-green-400" : "text-red-400"}`}
                                >
                                  {stock.change_1w >= 0 ? "+" : ""}
                                  {stock.change_1w?.toFixed(1)}%
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
      </div>
    </div>
  );
}
