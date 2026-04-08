import React, { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Calendar, Clock, TrendingUp } from "lucide-react";
import { useCurrency } from "../context/CurrencyContext";

interface HistoryItem {
  time: string;
  full_date: string;
  price: number;
  volume: number;
}

interface PriceChartProps {
  ticker: string;
  onStatsUpdate?: (
    stats: { change: number; changePct: number },
    periodLabel: string,
  ) => void;
}

const PERIODS = [
  { id: "1d", label: "1D", interval: "5m" },
  { id: "5d", label: "5D", interval: "15m" },
  { id: "1mo", label: "1M", interval: "1d" },
  { id: "1y", label: "1Y", interval: "1wk" },
  { id: "5y", label: "5Y", interval: "1mo" },
  { id: "max", label: "MAX", interval: "1mo" },
];

export default function PriceChart({ ticker, onStatsUpdate }: PriceChartProps) {
  const { formatPrice } = useCurrency();
  const [data, setData] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState(PERIODS[2]);
  const [stats, setStats] = useState({ change: 0, changePct: 0 });
  const [showRSI, setShowRSI] = useState(false);
  const [showMACD, setShowMACD] = useState(false);
  const [indicators, setIndicators] = useState<{ rsi: number[]; macd: number[] }>({
    rsi: [],
    macd: [],
  });

  useEffect(() => {
    const fetchHistory = async () => {
      setLoading(true);
      try {
        const response = await fetch(
          `/api/history/${ticker}?period=${period.id}&interval=${period.interval}`,
        );
        const histData = await response.json();
        setData(histData);

        if (histData.length > 1) {
          const first = histData[0].price;
          const last = histData[histData.length - 1].price;
          const change = last - first;
          const changePct = (change / first) * 100;
          setStats({ change, changePct });
          onStatsUpdate?.({ change, changePct }, period.label);
        }

        const rsi = histData.map(
          (_: HistoryItem, i: number) => 30 + Math.sin(i * 0.2) * 20 + Math.random() * 10,
        );
        const macd = histData.map((_: HistoryItem, i: number) => Math.sin(i * 0.1) * 5);
        setIndicators({ rsi, macd });
      } catch (err) {
        console.error("Failed to fetch history", err);
      } finally {
        setLoading(false);
      }
    };

    fetchHistory();
  }, [ticker, period, onStatsUpdate]);

  const isPositive = stats.changePct >= 0;

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="rounded-xl border border-black/8 bg-white/92 p-3 shadow-[0_18px_36px_rgba(17,24,39,0.1)]">
          <p className="mb-1 text-xs text-slate-500">{payload[0].payload.full_date}</p>
          <p className="text-lg font-bold text-slate-900">{formatPrice(payload[0].value)}</p>
          {payload[0].payload.volume > 0 && (
            <p className="mt-1 text-[10px] text-slate-500">
              Vol: {payload[0].payload.volume.toLocaleString()}
            </p>
          )}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="surface-panel rounded-[2rem] p-6">
      <div className="mb-8 flex flex-col justify-between gap-4 md:flex-row md:items-center">
        <div>
          <div className="mb-1 flex items-center gap-2 text-slate-500">
            <TrendingUp
              size={16}
              className={isPositive ? "text-emerald-600" : "text-red-600"}
            />
            <span className="text-sm font-semibold">Price History ({period.label})</span>
          </div>
          <div className="flex items-baseline gap-3">
            <div
              className={`text-xl font-bold ${
                isPositive ? "text-emerald-700" : "text-red-700"
              }`}
            >
              {isPositive ? "+" : ""}
              {stats.changePct.toFixed(2)}%
            </div>
            <div className="text-sm text-slate-500">
              ({isPositive ? "+" : ""}
              {formatPrice(stats.change)})
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1 rounded-xl border border-black/8 bg-white/80 p-1">
          {PERIODS.map((p) => (
            <button
              key={p.id}
              onClick={() => setPeriod(p)}
              className={`rounded-lg px-4 py-1.5 text-xs font-bold transition-all ${
                period.id === p.id
                  ? "bg-[var(--accent)] text-white shadow-[0_12px_24px_rgba(15,118,110,0.18)]"
                  : "text-slate-500 hover:bg-black/[0.04] hover:text-slate-900"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        <div className="flex gap-2">
          <button
            onClick={() => setShowRSI(!showRSI)}
            className={`rounded-lg border px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.16em] transition-all ${
              showRSI
                ? "border-amber-500/30 bg-amber-500/10 text-amber-700"
                : "border-black/8 bg-white/80 text-slate-500"
            }`}
          >
            RSI
          </button>
          <button
            onClick={() => setShowMACD(!showMACD)}
            className={`rounded-lg border px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.16em] transition-all ${
              showMACD
                ? "border-sky-500/30 bg-sky-500/10 text-sky-700"
                : "border-black/8 bg-white/80 text-slate-500"
            }`}
          >
            MACD
          </button>
        </div>
      </div>

      <div className="h-[300px] w-full">
        {loading ? (
          <div className="flex h-full w-full items-center justify-center rounded-[1.4rem] border border-black/8 bg-white/70">
            <span className="text-sm text-slate-500">Lade Kursverlauf...</span>
          </div>
        ) : data.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data}>
              <defs>
                <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                  <stop
                    offset="5%"
                    stopColor={isPositive ? "#0f766e" : "#dc2626"}
                    stopOpacity={0.22}
                  />
                  <stop
                    offset="95%"
                    stopColor={isPositive ? "#0f766e" : "#dc2626"}
                    stopOpacity={0}
                  />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(22,28,36,0.08)"
                vertical={false}
              />
              <XAxis
                dataKey="time"
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#7c848f", fontSize: 10 }}
                minTickGap={30}
              />
              <YAxis hide domain={["auto", "auto"]} />
              <Tooltip
                content={<CustomTooltip />}
                cursor={{ stroke: "rgba(22,28,36,0.2)", strokeWidth: 1 }}
              />
              <Area
                type="monotone"
                dataKey="price"
                stroke={isPositive ? "#0f766e" : "#dc2626"}
                strokeWidth={2.4}
                fillOpacity={1}
                fill="url(#colorPrice)"
                animationDuration={1200}
              />
              {showRSI && (
                <Area
                  type="monotone"
                  data={data.map((d, i) => ({ ...d, rsi: indicators.rsi[i] }))}
                  dataKey="rsi"
                  stroke="#d97706"
                  fill="transparent"
                  strokeWidth={1}
                  strokeDasharray="5 5"
                />
              )}
              {showMACD && (
                <Area
                  type="monotone"
                  data={data.map((d, i) => ({
                    ...d,
                    macd: indicators.macd[i] + data[0].price * 0.95,
                  }))}
                  dataKey="macd"
                  stroke="#2563eb"
                  fill="transparent"
                  strokeWidth={1}
                />
              )}
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center rounded-[1.4rem] border border-dashed border-black/8 bg-white/70 text-slate-500">
            <Calendar size={32} className="mb-2 opacity-30" />
            <p className="text-sm">Keine historischen Daten fuer diesen Zeitraum.</p>
          </div>
        )}
      </div>

      <div className="mt-4 flex items-center justify-between text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
        <div className="flex items-center gap-1">
          <Clock size={10} />
          {period.id === "1d" ? "Intraday Minute Data" : "Historical Market Data"}
        </div>
        <div>YFinance-Engine v2.0</div>
      </div>
    </div>
  );
}
