import React, { useEffect, useState } from "react";
import { TrendingUp, TrendingDown, Activity } from "lucide-react";
import { useCurrency } from "../context/CurrencyContext";
import { fetchJsonWithRetry } from "../lib/api";

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
    fetchJsonWithRetry<HeatmapItem[]>("/api/discovery/sentiment-heatmap", undefined, {
      retries: 1,
      retryDelayMs: 800,
    })
      .then((data) => setHeatmap(data ?? []))
      .catch(() => setHeatmap([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="surface-panel h-56 animate-pulse rounded-[2rem]" />;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[11px] font-extrabold uppercase tracking-[0.24em] text-slate-500">
            Macro overview
          </div>
          <h2 className="mt-2 text-4xl text-slate-900">Global Market Pulse</h2>
        </div>
        <div className="hidden rounded-full border border-black/8 bg-white/70 px-4 py-2 text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500 md:block">
          Sector heatmap
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
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
                className="surface-panel group relative overflow-hidden rounded-[2rem] p-5 transition-transform duration-200 hover:-translate-y-1"
              >
                <div
                  className={`absolute inset-x-0 top-0 h-1 ${
                    isBullish ? "bg-emerald-600/70" : "bg-red-600/70"
                  }`}
                />
                <div className="flex items-start justify-between">
                  <div>
                    <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                      {item.sector}
                    </div>
                    <div
                      className={`mt-3 inline-flex items-center gap-2 rounded-full px-3 py-1 text-[11px] font-extrabold uppercase tracking-[0.16em] ${
                        isBullish
                          ? "bg-emerald-500/10 text-emerald-700"
                          : "bg-red-500/10 text-red-700"
                      }`}
                    >
                      {isBullish ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                      {item.status}
                    </div>
                  </div>
                  <div className="rounded-2xl bg-black/[0.03] p-2 text-slate-500">
                    <Activity size={16} />
                  </div>
                </div>

                <div className="mt-6">
                  <div className="flex items-center justify-between text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
                    <span>Strength</span>
                    <span>{item.strength.toFixed(0)}%</span>
                  </div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-black/[0.06]">
                    <div
                      className={`h-full rounded-full ${
                        isBullish ? "bg-emerald-600" : "bg-red-600"
                      }`}
                      style={{ width: `${item.strength}%` }}
                    />
                  </div>
                </div>

                {sortedStocks.length > 0 && (
                  <div className="mt-6 space-y-2">
                    <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                      Leading names
                    </div>
                    {sortedStocks.slice(0, 3).map((stock) => (
                      <button
                        key={stock.ticker}
                        onClick={() => onAnalyze?.(stock.ticker)}
                        className="flex w-full items-center justify-between rounded-[1.2rem] border border-black/6 bg-white/70 px-3 py-3 text-left transition-colors hover:bg-white"
                      >
                        <div>
                          <div className="text-sm font-extrabold text-slate-900">
                            {stock.ticker}
                          </div>
                          <div className="max-w-[140px] truncate text-xs text-slate-500">
                            {stock.name}
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="text-xs font-bold text-slate-700">
                            {formatPrice(stock.price)}
                          </div>
                          <div
                            className={`text-xs font-extrabold ${
                              stock.change_1w >= 0 ? "text-emerald-700" : "text-red-700"
                            }`}
                          >
                            {stock.change_1w >= 0 ? "+" : ""}
                            {stock.change_1w.toFixed(1)}%
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
      </div>
    </div>
  );
}
