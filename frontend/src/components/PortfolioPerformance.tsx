import React, { useState, useEffect } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { TrendingUp, TrendingDown, Clock } from "lucide-react";
import { useCurrency } from "../context/CurrencyContext";

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
  const [period, setPeriod] = useState(PERIODS[1]); // Default 1M
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

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-[#0a0a0c] border border-white/10 p-3 rounded-xl shadow-2xl backdrop-blur-md">
          <p className="text-gray-400 text-xs mb-1 uppercase tracking-widest">
            {payload[0].payload.time}
          </p>
          <p className="text-white font-bold text-lg">
            {formatPrice(payload[0].value)}
          </p>
          <div className="text-[10px] text-purple-400 mt-1 uppercase font-bold">
            Market Value
          </div>
        </div>
      );
    }
    return null;
  };

  const isPositive = stats.changePct >= 0;

  return (
    <div className="bg-[#050507] rounded-2xl p-6 border border-white/5 shadow-inner">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-2 text-gray-400 mb-1">
            <TrendingUp
              size={16}
              className={isPositive ? "text-green-500" : "text-red-500"}
            />
            <span className="text-sm font-medium uppercase tracking-wider">
              Portfolio Performance
            </span>
          </div>
          <div className="flex items-baseline gap-3">
            <div
              className={`text-2xl font-bold ${isPositive ? "text-green-400" : "text-red-400"}`}
            >
              {isPositive ? "+" : ""}
              {stats.changePct.toFixed(2)}%
            </div>
            <div className="text-gray-500 text-sm font-mono">
              {isPositive ? "+" : ""}
              {formatPrice(stats.change)}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1 bg-black/40 p-1 rounded-xl border border-white/5">
          {PERIODS.map((p) => (
            <button
              key={p.id}
              onClick={() => setPeriod(p)}
              className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${
                period.id === p.id
                  ? "bg-purple-600 text-white shadow-lg shadow-purple-500/20"
                  : "text-gray-500 hover:text-white hover:bg-white/5"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div className="h-[250px] w-full">
        {loading ? (
          <div className="w-full h-full flex flex-col items-center justify-center bg-black/20 rounded-xl animate-pulse space-y-4">
            <div className="w-12 h-12 border-4 border-purple-500/20 border-t-purple-500 rounded-full animate-spin"></div>
            <span className="text-gray-600 text-[10px] uppercase font-bold tracking-widest">
              Calculating NAV...
            </span>
          </div>
        ) : data.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data}>
              <defs>
                <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#222"
                vertical={false}
                strokeOpacity={0.2}
              />
              <XAxis dataKey="time" hide />
              <YAxis hide domain={["auto", "auto"]} />
              <Tooltip
                content={<CustomTooltip />}
                cursor={{ stroke: "#333", strokeWidth: 1 }}
              />
              <Area
                type="monotone"
                dataKey="price"
                stroke="#a78bfa"
                strokeWidth={3}
                fillOpacity={1}
                fill="url(#colorValue)"
                animationDuration={2000}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center text-gray-700 border border-dashed border-white/5 rounded-2xl">
            <TrendingUp size={32} className="mb-2 opacity-10" />
            <p className="text-sm font-medium">
              Add holdings to track performance
            </p>
          </div>
        )}
      </div>

      <div className="mt-4 flex items-center gap-2 text-[10px] text-gray-600 uppercase tracking-widest font-bold">
        <Clock size={10} />
        Aggregated Real-Time Intelligence
      </div>
    </div>
  );
}
