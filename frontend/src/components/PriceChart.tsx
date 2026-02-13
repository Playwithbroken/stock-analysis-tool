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
import { Calendar, Clock, TrendingUp, TrendingDown } from "lucide-react";
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
  const { formatPrice, convert, currency } = useCurrency();
  const [data, setData] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState(PERIODS[2]); // Default 1M
  const [stats, setStats] = useState({ change: 0, changePct: 0 });
  const [showRSI, setShowRSI] = useState(false);
  const [showMACD, setShowMACD] = useState(false);
  const [indicators, setIndicators] = useState<{
    rsi: number[];
    macd: number[];
  }>({ rsi: [], macd: [] });

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
          if (onStatsUpdate) {
            onStatsUpdate({ change, changePct }, period.label);
          }
        }

        // Simple RSI/MACD Simulation for visuals (Real calc would use talib or similar)
        const rsi = histData.map(
          (_: any, i: number) =>
            30 + Math.sin(i * 0.2) * 20 + Math.random() * 10,
        );
        const macd = histData.map((_: any, i: number) => Math.sin(i * 0.1) * 5);
        setIndicators({ rsi, macd });
      } catch (err) {
        console.error("Failed to fetch history", err);
      } finally {
        setLoading(false);
      }
    };

    fetchHistory();
  }, [ticker, period]);

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-[#0a0a0c] border border-white/10 p-3 rounded-xl shadow-2xl backdrop-blur-md">
          <p className="text-gray-400 text-xs mb-1">
            {payload[0].payload.full_date}
          </p>
          <p className="text-white font-bold text-lg">
            {formatPrice(payload[0].value)}
          </p>
          {payload[0].payload.volume > 0 && (
            <p className="text-gray-500 text-[10px] mt-1">
              Vol: {payload[0].payload.volume.toLocaleString()}
            </p>
          )}
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
            <span className="text-sm font-medium">
              Price History ({period.label})
            </span>
          </div>
          <div className="flex items-baseline gap-3">
            <div
              className={`text-xl font-bold ${isPositive ? "text-green-400" : "text-red-400"}`}
            >
              {isPositive ? "+" : ""}
              {stats.changePct.toFixed(2)}%
            </div>
            <div className="text-gray-500 text-sm">
              ({isPositive ? "+" : ""}
              {formatPrice(stats.change)})
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1 bg-black/40 p-1 rounded-xl border border-white/5">
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

        <div className="flex gap-2">
          <button
            onClick={() => setShowRSI(!showRSI)}
            className={`px-3 py-1.5 rounded-lg text-[10px] font-bold border transition-all ${showRSI ? "bg-orange-500/20 border-orange-500/50 text-orange-400" : "bg-white/5 border-white/10 text-gray-500"}`}
          >
            RSI
          </button>
          <button
            onClick={() => setShowMACD(!showMACD)}
            className={`px-3 py-1.5 rounded-lg text-[10px] font-bold border transition-all ${showMACD ? "bg-blue-500/20 border-blue-500/50 text-blue-400" : "bg-white/5 border-white/10 text-gray-500"}`}
          >
            MACD
          </button>
        </div>
      </div>

      <div className="h-[300px] w-full">
        {loading ? (
          <div className="w-full h-full flex items-center justify-center bg-black/20 rounded-xl animate-pulse">
            <span className="text-gray-600 text-sm">
              Loading market points...
            </span>
          </div>
        ) : data.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data}>
              <defs>
                <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                  <stop
                    offset="5%"
                    stopColor={isPositive ? "#4ade80" : "#f87171"}
                    stopOpacity={0.3}
                  />
                  <stop
                    offset="95%"
                    stopColor={isPositive ? "#4ade80" : "#f87171"}
                    stopOpacity={0}
                  />
                </linearGradient>
                <linearGradient id="purpleGlow" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#9d4edd" stopOpacity={0.1} />
                  <stop offset="95%" stopColor="#7b2cbf" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#111"
                vertical={false}
              />
              <XAxis
                dataKey="time"
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#444", fontSize: 10 }}
                minTickGap={30}
              />
              <YAxis hide domain={["auto", "auto"]} />
              <Tooltip
                content={<CustomTooltip />}
                cursor={{ stroke: "#333", strokeWidth: 1 }}
              />
              <Area
                type="monotone"
                dataKey="price"
                stroke={isPositive ? "#4ade80" : "#f87171"}
                strokeWidth={2}
                fillOpacity={1}
                fill="url(#colorPrice)"
                animationDuration={1500}
              />
              {showRSI && (
                <Area
                  type="monotone"
                  data={data.map((d, i) => ({ ...d, rsi: indicators.rsi[i] }))}
                  dataKey="rsi"
                  stroke="#fb923c"
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
                  stroke="#3b82f6"
                  fill="transparent"
                  strokeWidth={1}
                />
              )}
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center text-gray-600 border border-dashed border-white/5 rounded-2xl">
            <Calendar size={32} className="mb-2 opacity-20" />
            <p className="text-sm">
              No historical data available for this range
            </p>
          </div>
        )}
      </div>

      <div className="mt-4 flex items-center justify-between text-[10px] text-gray-600 uppercase tracking-widest font-bold">
        <div className="flex items-center gap-1">
          <Clock size={10} />
          {period.id === "1d"
            ? "Intraday Minute Data"
            : "Historical Market Data"}
        </div>
        <div>YFinance-Engine v2.0</div>
      </div>
    </div>
  );
}
