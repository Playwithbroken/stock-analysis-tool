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
import { Clock, TrendingUp } from "lucide-react";
import { useCurrency } from "../context/CurrencyContext";
import MeasuredChartFrame from "./MeasuredChartFrame";

interface PerformanceItem {
  time: string;
  price: number;
}

interface PortfolioPerformanceProps {
  portfolioId: string;
  refreshKey?: number;
}

const PERIODS = [
  { id: "1d", label: "1D" },
  { id: "1mo", label: "1M" },
  { id: "1y", label: "1Y" },
  { id: "max", label: "MAX" },
];

export default function PortfolioPerformance({
  portfolioId,
  refreshKey = 0,
}: PortfolioPerformanceProps) {
  const { formatPrice } = useCurrency();
  const [data, setData] = useState<PerformanceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState(PERIODS[1]);
  const [stats, setStats] = useState({ change: 0, changePct: 0 });

  useEffect(() => {
    const fetchHistory = async () => {
      setLoading(true);
      try {
        const response = await fetch(
          `/api/portfolio/${portfolioId}/history?period=${period.id}`,
        );
        const histData = await response.json();
        setData(histData);

        if (histData.length > 1) {
          const first = histData[0].price;
          const last = histData[histData.length - 1].price;
          const change = last - first;
          const changePct = (change / first) * 100;
          setStats({ change, changePct });
        }
      } catch (err) {
        console.error("Failed to fetch portfolio performance", err);
      } finally {
        setLoading(false);
      }
    };

    if (portfolioId) fetchHistory();
  }, [portfolioId, period, refreshKey]);

  const isPositive = stats.changePct >= 0;

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="rounded-xl border border-black/8 bg-white/92 p-3 shadow-[0_18px_36px_rgba(17,24,39,0.1)]">
          <p className="mb-1 text-xs uppercase tracking-[0.18em] text-slate-500">
            {payload[0].payload.time}
          </p>
          <p className="text-lg font-bold text-slate-900">
            {formatPrice(payload[0].value)}
          </p>
          <div className="mt-1 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--accent)]">
            Market Value
          </div>
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
            <span className="text-sm font-medium uppercase tracking-[0.18em]">
              Portfolio Performance
            </span>
          </div>
          <div className="flex items-baseline gap-3">
            <div
              className={`text-2xl font-bold ${
                isPositive ? "text-emerald-700" : "text-red-700"
              }`}
            >
              {isPositive ? "+" : ""}
              {stats.changePct.toFixed(2)}%
            </div>
            <div className="text-sm font-mono text-slate-500">
              {isPositive ? "+" : ""}
              {formatPrice(stats.change)}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1 rounded-xl border border-black/8 bg-white/80 p-1">
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
      </div>

      <MeasuredChartFrame
        className="h-[250px] w-full"
        minHeight={250}
        fallback={
          <div className="flex h-full w-full flex-col items-center justify-center space-y-4 rounded-xl border border-black/8 bg-white/70">
            <div className="h-12 w-12 animate-spin rounded-full border-4 border-[var(--accent)]/15 border-t-[var(--accent)]" />
            <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
              Calculating NAV
            </span>
          </div>
        }
      >
        {loading ? (
          <div className="flex h-full w-full flex-col items-center justify-center space-y-4 rounded-xl border border-black/8 bg-white/70">
            <div className="h-12 w-12 animate-spin rounded-full border-4 border-[var(--accent)]/15 border-t-[var(--accent)]" />
            <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
              Calculating NAV
            </span>
          </div>
        ) : data.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={220}>
            <AreaChart data={data}>
              <defs>
                <linearGradient id="portfolioValue" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#0f766e" stopOpacity={0.26} />
                  <stop offset="95%" stopColor="#0f766e" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(22,28,36,0.08)"
                vertical={false}
              />
              <XAxis dataKey="time" hide />
              <YAxis hide domain={["auto", "auto"]} />
              <Tooltip
                content={<CustomTooltip />}
                cursor={{ stroke: "rgba(22,28,36,0.2)", strokeWidth: 1 }}
              />
              <Area
                type="monotone"
                dataKey="price"
                stroke="#0f766e"
                strokeWidth={3}
                fillOpacity={1}
                fill="url(#portfolioValue)"
                animationDuration={1400}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center rounded-2xl border border-dashed border-black/8 bg-white/70 text-slate-500">
            <TrendingUp size={32} className="mb-2 opacity-20" />
            <p className="text-sm font-medium">Add holdings to track performance</p>
          </div>
        )}
      </MeasuredChartFrame>

      <div className="mt-4 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
        <Clock size={10} />
        Aggregated Portfolio Intelligence
      </div>
    </div>
  );
}
