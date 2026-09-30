import React, { useEffect, useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";
import {
  TrendingUp,
  TrendingDown,
  Award,
  BarChart3,
  Activity,
  ShieldAlert,
  Percent,
  RefreshCw,
} from "lucide-react";
import MeasuredChartFrame from "./MeasuredChartFrame";

interface BenchmarkChartPoint {
  time: string;
  portfolio_pct: number;
  benchmark_pct: number;
  portfolio_value: number;
  benchmark_value: number;
}

interface BenchmarkMetrics {
  total_return_portfolio_pct: number;
  total_return_benchmark_pct: number;
  alpha_excess_pct: number;
  beta: number;
  correlation: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown_portfolio_pct: number;
  max_drawdown_benchmark_pct: number;
}

interface BenchmarkResponse {
  portfolio_id: string;
  portfolio_name: string;
  benchmark_symbol: string;
  benchmark_name: string;
  period: string;
  chart_data: BenchmarkChartPoint[];
  metrics: BenchmarkMetrics;
  verdict: string;
}

interface BenchmarkComparisonProps {
  portfolioId: string;
  portfolioName?: string;
}

const BENCHMARKS = [
  { id: "URTH", label: "MSCI World", ticker: "URTH" },
  { id: "SPY", label: "S&P 500", ticker: "SPY" },
  { id: "QQQ", label: "Nasdaq 100", ticker: "QQQ" },
  { id: "DAX", label: "DAX 40", ticker: "DAX" },
];

const PERIODS = [
  { id: "1mo", label: "1M" },
  { id: "3mo", label: "3M" },
  { id: "1y", label: "1J" },
  { id: "max", label: "GESAMT" },
];

export default function BenchmarkComparison({
  portfolioId,
  portfolioName = "Mein Portfolio",
}: BenchmarkComparisonProps) {
  const [selectedBm, setSelectedBm] = useState<string>("URTH");
  const [selectedPeriod, setSelectedPeriod] = useState<string>("1y");
  const [data, setData] = useState<BenchmarkResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchBenchmarkData = async () => {
    if (!portfolioId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/portfolio/${portfolioId}/benchmark?benchmark=${selectedBm}&period=${selectedPeriod}`
      );
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const json: BenchmarkResponse = await res.json();
      setData(json);
    } catch (err: any) {
      setError(err?.message || "Fehler beim Laden des Benchmark-Vergleichs");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBenchmarkData();
  }, [portfolioId, selectedBm, selectedPeriod]);

  const metrics = data?.metrics;
  const isAlphaPositive = (metrics?.alpha_excess_pct ?? 0) >= 0;

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const pVal = payload.find((p: any) => p.dataKey === "portfolio_pct")?.value;
      const bVal = payload.find((p: any) => p.dataKey === "benchmark_pct")?.value;
      const diff = pVal !== undefined && bVal !== undefined ? pVal - bVal : null;

      return (
        <div className="rounded-xl border border-black/10 bg-white/95 p-3 shadow-xl backdrop-blur-md dark:border-white/10 dark:bg-slate-900/95">
          <div className="mb-2 text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            {label}
          </div>
          <div className="space-y-1.5 text-xs">
            <div className="flex items-center justify-between gap-4 font-bold text-teal-600 dark:text-teal-400">
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-teal-500 inline-block" />
                {portfolioName}:
              </span>
              <span>{pVal >= 0 ? `+${pVal.toFixed(2)}%` : `${pVal.toFixed(2)}%`}</span>
            </div>
            <div className="flex items-center justify-between gap-4 font-bold text-indigo-600 dark:text-indigo-400">
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-indigo-500 inline-block" />
                {data?.benchmark_name || selectedBm}:
              </span>
              <span>{bVal >= 0 ? `+${bVal.toFixed(2)}%` : `${bVal.toFixed(2)}%`}</span>
            </div>
            {diff !== null && (
              <div className="mt-1 border-t border-slate-200 pt-1.5 text-[11px] font-semibold text-slate-600 dark:border-slate-800 dark:text-slate-300">
                Alpha (Delta):{" "}
                <span className={diff >= 0 ? "text-emerald-600 font-bold" : "text-rose-600 font-bold"}>
                  {diff >= 0 ? `+${diff.toFixed(2)}%` : `${diff.toFixed(2)}%`}
                </span>
              </div>
            )}
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <section className="surface-panel rounded-[2rem] p-6 lg:p-7 space-y-6">
      {/* Header with Benchmark & Period Selectors */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400">
            <Award className="h-4 w-4 text-[var(--accent)]" />
            <span className="text-xs font-bold uppercase tracking-[0.2em]">
              Benchmark Alpha & Marktvergleich
            </span>
          </div>
          <h3 className="mt-1 text-xl font-extrabold tracking-tight text-slate-900 dark:text-white">
            Performance vs. {data?.benchmark_name || selectedBm}
          </h3>
        </div>

        {/* Controls */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Benchmark Selection */}
          <div className="flex items-center rounded-xl border border-black/8 bg-black/[0.03] p-1 dark:border-white/10 dark:bg-white/5">
            {BENCHMARKS.map((bm) => (
              <button
                key={bm.id}
                onClick={() => setSelectedBm(bm.id)}
                className={`rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
                  selectedBm === bm.id
                    ? "bg-indigo-600 text-white shadow-md shadow-indigo-500/20"
                    : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
                }`}
              >
                {bm.label}
              </button>
            ))}
          </div>

          {/* Period Selection */}
          <div className="flex items-center rounded-xl border border-black/8 bg-black/[0.03] p-1 dark:border-white/10 dark:bg-white/5">
            {PERIODS.map((p) => (
              <button
                key={p.id}
                onClick={() => setSelectedPeriod(p.id)}
                className={`rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
                  selectedPeriod === p.id
                    ? "bg-[var(--accent)] text-white shadow-md"
                    : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          <button
            onClick={fetchBenchmarkData}
            disabled={loading}
            className="rounded-xl border border-black/8 bg-black/[0.03] p-2 text-slate-600 hover:bg-black/[0.06] hover:text-slate-900 dark:border-white/10 dark:bg-white/5 dark:text-slate-400 dark:hover:text-white"
            title="Neu laden"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin text-teal-600" : ""}`} />
          </button>
        </div>
      </div>

      {/* KPI Cards Grid */}
      {metrics && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {/* Alpha Card */}
          <div className="rounded-2xl border border-black/8 bg-black/[0.02] p-4 dark:border-white/10 dark:bg-white/5">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Alpha (Überrendite)
            </div>
            <div
              className={`mt-1 text-xl font-black ${
                isAlphaPositive
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-rose-600 dark:text-rose-400"
              }`}
            >
              {metrics.alpha_excess_pct >= 0
                ? `+${metrics.alpha_excess_pct.toFixed(2)}%`
                : `${metrics.alpha_excess_pct.toFixed(2)}%`}
            </div>
            <div className="mt-1 text-[11px] font-semibold text-slate-500 dark:text-slate-400">
              vs. {selectedBm}
            </div>
          </div>

          {/* Portfolio Return */}
          <div className="rounded-2xl border border-black/8 bg-black/[0.02] p-4 dark:border-white/10 dark:bg-white/5">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-teal-600 dark:text-teal-400">
              Portfolio Rendite
            </div>
            <div
              className={`mt-1 text-xl font-black ${
                metrics.total_return_portfolio_pct >= 0
                  ? "text-teal-600 dark:text-teal-400"
                  : "text-rose-600 dark:text-rose-400"
              }`}
            >
              {metrics.total_return_portfolio_pct >= 0
                ? `+${metrics.total_return_portfolio_pct.toFixed(2)}%`
                : `${metrics.total_return_portfolio_pct.toFixed(2)}%`}
            </div>
            <div className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
              Im Zeitraum {selectedPeriod.toUpperCase()}
            </div>
          </div>

          {/* Benchmark Return */}
          <div className="rounded-2xl border border-black/8 bg-black/[0.02] p-4 dark:border-white/10 dark:bg-white/5">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-indigo-600 dark:text-indigo-400">
              Index Rendite
            </div>
            <div
              className={`mt-1 text-xl font-black ${
                metrics.total_return_benchmark_pct >= 0
                  ? "text-indigo-600 dark:text-indigo-400"
                  : "text-rose-600 dark:text-rose-400"
              }`}
            >
              {metrics.total_return_benchmark_pct >= 0
                ? `+${metrics.total_return_benchmark_pct.toFixed(2)}%`
                : `${metrics.total_return_benchmark_pct.toFixed(2)}%`}
            </div>
            <div className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
              {selectedBm} gesamt
            </div>
          </div>

          {/* Beta */}
          <div className="rounded-2xl border border-black/8 bg-black/[0.02] p-4 dark:border-white/10 dark:bg-white/5">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Beta (Marktsensitivität)
            </div>
            <div className="mt-1 text-xl font-black text-slate-900 dark:text-white">
              {metrics.beta.toFixed(2)}
            </div>
            <div className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
              {metrics.beta > 1.15
                ? "Offensiv / Zyklisch"
                : metrics.beta < 0.85
                ? "Defensiv / Stabil"
                : "Marktneutral"}
            </div>
          </div>

          {/* Sharpe Ratio */}
          <div className="rounded-2xl border border-black/8 bg-black/[0.02] p-4 dark:border-white/10 dark:bg-white/5">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Sharpe Ratio
            </div>
            <div
              className={`mt-1 text-xl font-black ${
                metrics.sharpe_ratio >= 1.0
                  ? "text-emerald-600 dark:text-emerald-400"
                  : metrics.sharpe_ratio >= 0
                  ? "text-slate-900 dark:text-white"
                  : "text-rose-600 dark:text-rose-400"
              }`}
            >
              {metrics.sharpe_ratio.toFixed(2)}
            </div>
            <div className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
              Risikoadjustiert (Rf=3%)
            </div>
          </div>

          {/* Max Drawdown */}
          <div className="rounded-2xl border border-black/8 bg-black/[0.02] p-4 dark:border-white/10 dark:bg-white/5">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Max Drawdown
            </div>
            <div className="mt-1 text-xl font-black text-rose-600 dark:text-rose-400">
              -{metrics.max_drawdown_portfolio_pct.toFixed(1)}%
            </div>
            <div className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
              Index: -{metrics.max_drawdown_benchmark_pct.toFixed(1)}%
            </div>
          </div>
        </div>
      )}

      {/* Chart Section */}
      <div className="relative">
        <MeasuredChartFrame
          className="h-[300px] w-full"
          minHeight={300}
          fallback={
            <div className="flex h-[300px] w-full flex-col items-center justify-center space-y-3 rounded-2xl border border-black/8 bg-black/[0.02] dark:border-white/10 dark:bg-white/5">
              <div className="h-9 w-9 animate-spin rounded-full border-3 border-teal-500/20 border-t-teal-500" />
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Benchmark-Zeitreihen werden synchronisiert...
              </span>
            </div>
          }
        >
          {loading ? (
            <div className="flex h-[300px] w-full flex-col items-center justify-center space-y-3 rounded-2xl border border-black/8 bg-black/[0.02] dark:border-white/10 dark:bg-white/5">
              <div className="h-9 w-9 animate-spin rounded-full border-3 border-teal-500/20 border-t-teal-500" />
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Berechne Benchmark-Kennzahlen...
              </span>
            </div>
          ) : error ? (
            <div className="flex h-[300px] w-full flex-col items-center justify-center space-y-2 rounded-2xl border border-dashed border-rose-300 bg-rose-50/50 p-6 text-center dark:border-rose-900/50 dark:bg-rose-950/20">
              <ShieldAlert className="h-8 w-8 text-rose-500" />
              <p className="text-sm font-semibold text-rose-700 dark:text-rose-400">{error}</p>
            </div>
          ) : !data?.chart_data || data.chart_data.length < 2 ? (
            <div className="flex h-[300px] w-full flex-col items-center justify-center space-y-2 rounded-2xl border border-dashed border-black/10 bg-black/[0.02] p-6 text-center dark:border-white/10 dark:bg-white/5">
              <BarChart3 className="h-8 w-8 text-slate-400" />
              <p className="text-sm font-semibold text-slate-600 dark:text-slate-300">
                {data?.verdict || "Zu wenige historische Kurse für diesen Zeitraum verfügbar."}
              </p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={data.chart_data} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" opacity={0.5} />
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 11, fill: "#64748b" }}
                  tickLine={false}
                  axisLine={false}
                  dy={8}
                />
                <YAxis
                  tickFormatter={(val) => `${val >= 0 ? "+" : ""}${val.toFixed(0)}%`}
                  tick={{ fontSize: 11, fill: "#64748b" }}
                  tickLine={false}
                  axisLine={false}
                  dx={-4}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend
                  wrapperStyle={{ paddingTop: "12px" }}
                  formatter={(value) => (
                    <span className="text-xs font-bold text-slate-700 dark:text-slate-300">
                      {value === "portfolio_pct" ? portfolioName : (data.benchmark_name || selectedBm)}
                    </span>
                  )}
                />
                <Line
                  type="monotone"
                  dataKey="portfolio_pct"
                  name="portfolio_pct"
                  stroke="#0f766e"
                  strokeWidth={2.5}
                  dot={false}
                  activeDot={{ r: 5, fill: "#0f766e", stroke: "#ffffff", strokeWidth: 2 }}
                />
                <Line
                  type="monotone"
                  dataKey="benchmark_pct"
                  name="benchmark_pct"
                  stroke="#6366f1"
                  strokeWidth={2}
                  strokeDasharray="4 4"
                  dot={false}
                  activeDot={{ r: 4, fill: "#6366f1", stroke: "#ffffff", strokeWidth: 2 }}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </MeasuredChartFrame>
      </div>

      {/* Smart Verdict Card */}
      {data?.verdict && (
        <div
          className={`flex items-start gap-3 rounded-2xl border p-4.5 ${
            isAlphaPositive
              ? "border-emerald-500/20 bg-emerald-500/[0.06] text-emerald-950 dark:text-emerald-200"
              : "border-slate-500/20 bg-slate-500/[0.05] text-slate-800 dark:text-slate-200"
          }`}
        >
          <div className="mt-0.5 rounded-lg bg-emerald-500/15 p-1.5 text-emerald-600 dark:text-emerald-400">
            {isAlphaPositive ? <TrendingUp className="h-5 w-5" /> : <Activity className="h-5 w-5" />}
          </div>
          <div className="flex-1 text-sm leading-relaxed">
            <span className="font-extrabold tracking-wide">Markt-Fazit: </span>
            {data.verdict}
          </div>
        </div>
      )}
    </section>
  );
}
