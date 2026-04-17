import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Calendar, Clock, TrendingUp } from "lucide-react";
import { useCurrency } from "../context/CurrencyContext";
import { fetchJsonWithRetry } from "../lib/api";
import MeasuredChartFrame from "./MeasuredChartFrame";
import useRealtimeFeed from "../hooks/useRealtimeFeed";

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
  const { quotes, connected, lastUpdated } = useRealtimeFeed([ticker], true);
  const realtimeQuote = quotes[ticker.toUpperCase()];

  useEffect(() => {
    const fetchHistory = async () => {
      setLoading(true);
      try {
        const histData = await fetchJsonWithRetry<HistoryItem[]>(
          `/api/history/${ticker}?period=${period.id}&interval=${period.interval}`,
          undefined,
          { retries: 1, retryDelayMs: 800 },
        );
        setData(histData ?? []);

        if (histData.length > 1) {
          const first = histData[0].price;
          const last = histData[histData.length - 1].price;
          const change = last - first;
          const changePct = (change / first) * 100;
          setStats({ change, changePct });
          onStatsUpdate?.({ change, changePct }, period.label);
        }

        // Real RSI (14-period)
        const prices = histData.map((d: HistoryItem) => d.price);
        const rsiPeriod = 14;
        const rsiValues: number[] = new Array(prices.length).fill(50);
        if (prices.length > rsiPeriod) {
          let avgGain = 0, avgLoss = 0;
          for (let j = 1; j <= rsiPeriod; j++) {
            const diff = prices[j] - prices[j - 1];
            if (diff > 0) avgGain += diff; else avgLoss -= diff;
          }
          avgGain /= rsiPeriod;
          avgLoss /= rsiPeriod;
          rsiValues[rsiPeriod] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
          for (let j = rsiPeriod + 1; j < prices.length; j++) {
            const diff = prices[j] - prices[j - 1];
            avgGain = (avgGain * (rsiPeriod - 1) + (diff > 0 ? diff : 0)) / rsiPeriod;
            avgLoss = (avgLoss * (rsiPeriod - 1) + (diff < 0 ? -diff : 0)) / rsiPeriod;
            rsiValues[j] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
          }
        }
        // Real MACD (12/26/9 EMA)
        const ema = (src: number[], span: number): number[] => {
          const k = 2 / (span + 1);
          const out: number[] = [src[0]];
          for (let j = 1; j < src.length; j++) out.push(src[j] * k + out[j - 1] * (1 - k));
          return out;
        };
        const ema12 = ema(prices, 12);
        const ema26 = ema(prices, 26);
        const macdLine = ema12.map((v, j) => v - ema26[j]);
        const signal = ema(macdLine, 9);
        const macdHist = macdLine.map((v, j) => v - signal[j]);
        setIndicators({ rsi: rsiValues, macd: macdHist });
      } catch {
        setData([]);
      } finally {
        setLoading(false);
      }
    };

    fetchHistory();
  }, [ticker, period, onStatsUpdate]);

  useEffect(() => {
    if (!realtimeQuote?.price || data.length === 0) return;
    setData((prev) => {
      if (!prev.length) return prev;
      const next = [...prev];
      const last = next[next.length - 1];
      next[next.length - 1] = {
        ...last,
        price: realtimeQuote.price,
      };
      return next;
    });
  }, [realtimeQuote?.price]);

  const isPositive = stats.changePct >= 0;

  const chartData = useMemo(() => {
    return data.map((d, i) => ({
      ...d,
      _rsi: indicators.rsi[i],
      _macd: indicators.macd[i],
    }));
  }, [data, indicators]);

  const CustomTooltip = useCallback(({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const d = payload[0].payload;
      return (
        <div className="rounded-xl border border-black/8 bg-white/92 p-3 shadow-[0_18px_36px_rgba(17,24,39,0.1)]">
          <p className="mb-1 text-xs text-slate-500">{d.full_date}</p>
          <p className="text-lg font-bold text-slate-900">{formatPrice(payload[0].value)}</p>
          {d.volume > 0 && (
            <p className="mt-1 text-[10px] text-slate-500">
              Vol: {d.volume.toLocaleString()}
            </p>
          )}
          {d._rsi != null && showRSI && (
            <p className="mt-1 text-[10px] text-amber-600">RSI: {d._rsi.toFixed(1)}</p>
          )}
          {d._macd != null && showMACD && (
            <p className="mt-1 text-[10px] text-sky-600">MACD: {d._macd.toFixed(3)}</p>
          )}
        </div>
      );
    }
    return null;
  }, [formatPrice, showRSI, showMACD]);

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
            <span
              className={`rounded-full px-2 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] ${
                connected ? "bg-emerald-500/10 text-emerald-700" : "bg-slate-500/10 text-slate-500"
              }`}
            >
              {connected ? "Live" : "Polling"}
            </span>
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

      <MeasuredChartFrame
        className={`w-full ${showRSI || showMACD ? "h-[440px]" : "h-[300px]"}`}
        minHeight={showRSI || showMACD ? 440 : 300}
        fallback={
          <div className="flex h-full w-full items-center justify-center rounded-[1.4rem] border border-black/8 bg-white/70">
            <span className="text-sm text-slate-500">Lade Kursverlauf...</span>
          </div>
        }
      >
        {loading ? (
          <div className="flex h-full w-full items-center justify-center rounded-[1.4rem] border border-black/8 bg-white/70">
            <span className="text-sm text-slate-500">Lade Kursverlauf...</span>
          </div>
        ) : chartData.length > 0 ? (
          <div className="flex h-full w-full flex-col gap-1">
            <div className={showRSI || showMACD ? "h-[60%]" : "h-full"}>
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={180}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={isPositive ? "#0f766e" : "#dc2626"} stopOpacity={0.22} />
                      <stop offset="95%" stopColor={isPositive ? "#0f766e" : "#dc2626"} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(22,28,36,0.08)" vertical={false} />
                  <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fill: "#7c848f", fontSize: 10 }} minTickGap={30} />
                  <YAxis hide domain={["auto", "auto"]} />
                  <Tooltip content={<CustomTooltip />} cursor={{ stroke: "rgba(22,28,36,0.2)", strokeWidth: 1 }} />
                  <Area type="monotone" dataKey="price" stroke={isPositive ? "#0f766e" : "#dc2626"} strokeWidth={2.4} fillOpacity={1} fill="url(#colorPrice)" animationDuration={1200} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            {showRSI && (
              <div className="h-[20%] min-h-[60px]">
                <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(22,28,36,0.06)" vertical={false} />
                    <XAxis dataKey="time" hide />
                    <YAxis domain={[0, 100]} hide />
                    <ReferenceLine y={70} stroke="#dc2626" strokeDasharray="4 4" strokeOpacity={0.5} />
                    <ReferenceLine y={30} stroke="#0f766e" strokeDasharray="4 4" strokeOpacity={0.5} />
                    <Line type="monotone" dataKey="_rsi" stroke="#d97706" strokeWidth={1.5} dot={false} animationDuration={800} />
                  </LineChart>
                </ResponsiveContainer>
                <div className="flex justify-between px-2 text-[9px] font-bold uppercase tracking-wider text-slate-400">
                  <span>RSI 14</span>
                  <span className="text-red-400">70</span>
                  <span className="text-emerald-500">30</span>
                </div>
              </div>
            )}
            {showMACD && (
              <div className="h-[20%] min-h-[60px]">
                <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                  <BarChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(22,28,36,0.06)" vertical={false} />
                    <XAxis dataKey="time" hide />
                    <YAxis hide />
                    <ReferenceLine y={0} stroke="rgba(22,28,36,0.15)" />
                    <Bar dataKey="_macd" animationDuration={800}>
                      {chartData.map((entry, idx) => (
                        <Cell key={idx} fill={(entry._macd ?? 0) >= 0 ? "#0f766e" : "#dc2626"} fillOpacity={0.7} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <div className="px-2 text-[9px] font-bold uppercase tracking-wider text-slate-400">
                  MACD Histogram (12/26/9)
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center rounded-[1.4rem] border border-dashed border-black/8 bg-white/70 text-slate-500">
            <Calendar size={32} className="mb-2 opacity-30" />
            <p className="text-sm">Keine historischen Daten fuer diesen Zeitraum.</p>
          </div>
        )}
      </MeasuredChartFrame>

      <div className="mt-4 flex items-center justify-between text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
        <div className="flex items-center gap-1">
          <Clock size={10} />
          {period.id === "1d" ? "Intraday Minute Data" : "Historical Market Data"}
        </div>
        <div>
          {connected && lastUpdated ? `Live ${new Date(lastUpdated).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}` : "YFinance-Engine v2.0"}
        </div>
      </div>
    </div>
  );
}
