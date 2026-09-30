import React, { useEffect, useState } from "react";
import {
  Sparkles,
  TrendingUp,
  TrendingDown,
  Activity,
  Award,
  BarChart3,
  Sliders,
  Info,
  RefreshCw,
  X,
  Target,
  ShieldCheck,
  Percent,
  Layers,
  ArrowRight
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  Legend,
  ReferenceLine
} from "recharts";
import MeasuredChartFrame from "./MeasuredChartFrame";

interface HoldingRatioItem {
  ticker: string;
  name: string;
  value_eur: number;
  weight_pct: number;
  return_pct: number;
  volatility_pct: number;
  downside_deviation_pct: number;
  max_drawdown_pct: number;
  beta: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
}

interface PortfolioRatios {
  annual_return_pct: number;
  annual_volatility_pct: number;
  downside_deviation_pct: number;
  max_drawdown_pct: number;
  beta: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  treynor_ratio: number;
  information_ratio: number;
  tracking_error_pct: number;
  omega_ratio: number;
  pain_index: number;
  pain_ratio: number;
  rating_badge: {
    label: string;
    tone: string;
  };
}

interface BenchmarkProfile {
  name: string;
  return_pct: number;
  volatility_pct: number;
  downside_dev_pct: number;
  max_drawdown_pct: number;
  beta: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  omega_ratio: number;
  pain_index: number;
}

interface RiskRatiosData {
  valid: boolean;
  error?: string;
  portfolio_value_eur: number;
  benchmark_key: string;
  ratios: PortfolioRatios;
  benchmark: BenchmarkProfile;
  risk_free_rate_pct: number;
  holdings: HoldingRatioItem[];
}

interface RiskRatiosTerminalProps {
  portfolioId: string;
  onAnalyzeStock?: (ticker: string) => void;
  onClose?: () => void;
}

export default function RiskRatiosTerminal({
  portfolioId,
  onAnalyzeStock,
  onClose
}: RiskRatiosTerminalProps) {
  const [data, setData] = useState<RiskRatiosData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [benchmark, setBenchmark] = useState<string>("msci_world");
  const [activeTab, setActiveTab] = useState<"comparison" | "holdings" | "handbook">("comparison");

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/portfolio/${portfolioId}/risk-ratios?benchmark=${benchmark}`, {
        credentials: "same-origin"
      });
      if (!res.ok) {
        throw new Error(`HTTP Fehler ${res.status}: Risk-Ratios konnten nicht geladen werden.`);
      }
      const json: RiskRatiosData = await res.json();
      if (!json.valid) {
        throw new Error(json.error || "Ungültige Ratio-Daten erhalten.");
      }
      setData(json);
    } catch (err: any) {
      setError(err.message || "Unerwarteter Fehler bei der Performance-Ratio-Berechnung.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (portfolioId) {
      fetchData();
    }
  }, [portfolioId, benchmark]);

  const barComparisonData = data ? [
    {
      ratio: "Sharpe Ratio",
      Portfolio: data.ratios.sharpe_ratio,
      Benchmark: data.benchmark.sharpe_ratio,
    },
    {
      ratio: "Sortino Ratio",
      Portfolio: data.ratios.sortino_ratio,
      Benchmark: data.benchmark.sortino_ratio,
    },
    {
      ratio: "Calmar Ratio",
      Portfolio: data.ratios.calmar_ratio,
      Benchmark: data.benchmark.calmar_ratio,
    },
    {
      ratio: "Omega Ratio",
      Portfolio: data.ratios.omega_ratio,
      Benchmark: data.benchmark.omega_ratio,
    }
  ] : [];

  return (
    <section className="mt-8 rounded-[2rem] border border-violet-500/20 bg-gradient-to-b from-violet-950/[0.04] to-transparent p-6 dark:border-violet-500/30 dark:bg-slate-900/60 shadow-xl backdrop-blur-md">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-black/10 pb-5 dark:border-white/10">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-500/15 text-violet-700 dark:text-violet-400 border border-violet-500/30 shadow-inner">
            <BarChart3 size={24} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-black tracking-tight text-slate-900 dark:text-white">
                Institutional Risk-Adjusted Performance &amp; Ratio Terminal
              </h2>
              <span className="rounded-md border border-violet-500/30 bg-violet-500/15 px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider text-violet-800 dark:text-violet-300">
                Sortino &amp; Calmar
              </span>
            </div>
            <p className="text-xs font-semibold text-slate-600 dark:text-slate-400">
              Sharpe, Sortino (Downside Deviation), Calmar, Treynor, Information Ratio &amp; Pain Index vs. globale Benchmarks
            </p>
          </div>
        </div>

        {/* Global Controls */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 rounded-xl border border-black/10 bg-white/90 px-3 py-1.5 dark:border-white/10 dark:bg-slate-800 shadow-sm">
            <Target size={14} className="text-slate-500 dark:text-slate-400" />
            <span className="text-xs font-extrabold text-slate-700 dark:text-slate-300">Benchmark:</span>
            <select
              value={benchmark}
              onChange={(e) => setBenchmark(e.target.value)}
              className="rounded-lg bg-transparent text-xs font-black text-violet-700 dark:text-violet-400 outline-none cursor-pointer"
            >
              <option value="msci_world">MSCI World Net TR</option>
              <option value="sp500">S&amp;P 500 Total Return</option>
              <option value="dax">DAX 40 Performance</option>
            </select>
          </div>

          <button
            onClick={fetchData}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-xl border border-black/10 bg-white px-3 py-2 text-xs font-bold text-slate-700 hover:bg-black/5 dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:hover:bg-white/10"
            title="Aktualisieren"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            Aktualisieren
          </button>

          {onClose && (
            <button
              onClick={onClose}
              className="rounded-xl border border-black/10 bg-white p-2 text-slate-500 hover:text-slate-800 dark:border-white/10 dark:bg-white/5 dark:text-slate-400 dark:hover:text-white"
            >
              <X size={16} />
            </button>
          )}
        </div>
      </div>

      {loading && (
        <div className="flex flex-col items-center justify-center py-20">
          <RefreshCw size={36} className="animate-spin text-violet-600 dark:text-violet-400" />
          <p className="mt-4 text-sm font-bold text-slate-700 dark:text-slate-300">
            Berechne risikobereinigte Kennzahlen &amp; Downside Deviation...
          </p>
        </div>
      )}

      {error && (
        <div className="my-6 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-5 text-rose-800 dark:text-rose-300">
          <div className="flex items-center gap-2 font-black">
            <Info size={18} />
            Fehler bei der Kennzahlenberechnung
          </div>
          <p className="mt-1 text-xs">{error}</p>
        </div>
      )}

      {!loading && !error && data && (
        <div className="mt-6 space-y-6">
          {/* 4 Scorecards */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {/* Card 1: Sortino Ratio */}
            <div className="rounded-2xl border border-black/10 bg-white/90 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Sortino Ratio (Downside-Alpha)
                </span>
                <Award size={16} className="text-violet-600 dark:text-violet-400" />
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-black text-slate-900 dark:text-white">
                  {data.ratios.sortino_ratio.toFixed(2)}
                </span>
                <span className="text-xs font-bold text-slate-500">vs. {data.benchmark.sortino_ratio.toFixed(2)} Bench</span>
              </div>
              <div className="mt-2">
                <span className={`rounded-md border px-2 py-0.5 text-[10px] font-black uppercase ${data.ratios.rating_badge.tone}`}>
                  {data.ratios.rating_badge.label}
                </span>
              </div>
            </div>

            {/* Card 2: Sharpe Ratio */}
            <div className="rounded-2xl border border-black/10 bg-white/90 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Sharpe Ratio (Rf: {data.risk_free_rate_pct.toFixed(2)}%)
                </span>
                <Percent size={16} className="text-emerald-600 dark:text-emerald-400" />
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-black text-emerald-700 dark:text-emerald-400">
                  {data.ratios.sharpe_ratio.toFixed(2)}
                </span>
                <span className="text-xs font-bold text-slate-500">vs. {data.benchmark.sharpe_ratio.toFixed(2)} Bench</span>
              </div>
              <div className="mt-2 text-xs font-medium text-slate-500 dark:text-slate-400">
                Volatilität: <strong className="text-slate-900 dark:text-white">{data.ratios.annual_volatility_pct.toFixed(1)}%</strong> vs. Downside: <strong className="text-slate-900 dark:text-white">{data.ratios.downside_deviation_pct.toFixed(1)}%</strong>
              </div>
            </div>

            {/* Card 3: Calmar Ratio */}
            <div className="rounded-2xl border border-black/10 bg-white/90 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Calmar Ratio (Drawdown-Effizienz)
                </span>
                <ShieldCheck size={16} className="text-violet-600 dark:text-violet-400" />
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-black text-violet-700 dark:text-violet-400">
                  {data.ratios.calmar_ratio.toFixed(2)}
                </span>
                <span className="text-xs font-bold text-slate-500">vs. {data.benchmark.calmar_ratio.toFixed(2)} Bench</span>
              </div>
              <div className="mt-2 text-xs font-medium text-slate-500 dark:text-slate-400">
                Rendite / Max Drawdown ({data.ratios.max_drawdown_pct.toFixed(1)}%)
              </div>
            </div>

            {/* Card 4: Information Ratio */}
            <div className="rounded-2xl border border-black/10 bg-white/90 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Information Ratio (Alpha)
                </span>
                <Sparkles size={16} className="text-violet-600 dark:text-violet-400" />
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className={`text-3xl font-black ${data.ratios.information_ratio >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"}`}>
                  {data.ratios.information_ratio >= 0 ? `+${data.ratios.information_ratio.toFixed(2)}` : data.ratios.information_ratio.toFixed(2)}
                </span>
              </div>
              <div className="mt-2 text-xs font-medium text-slate-500 dark:text-slate-400">
                Tracking Error: <strong className="text-slate-900 dark:text-white">{data.ratios.tracking_error_pct.toFixed(1)}%</strong>
              </div>
            </div>
          </div>

          {/* Comparison Bar Chart */}
          <div className="rounded-2xl border border-black/10 bg-white/80 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/80">
            <h3 className="text-sm font-black text-slate-900 dark:text-white">
              Risk-Adjusted Ratios: Portfolio vs. {data.benchmark.name}
            </h3>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Direkter institutioneller Effizienzvergleich auf Risikobasis
            </p>

            <MeasuredChartFrame className="mt-4 w-full" minHeight={220}>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={barComparisonData} margin={{ top: 20, right: 30, left: 10, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                  <XAxis dataKey="ratio" tick={{ fontSize: 11, fontWeight: 700 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip
                    formatter={(val: any, name: any) => [`${Number(val).toFixed(2)}`, name]}
                    contentStyle={{ backgroundColor: "#0f172a", borderRadius: "12px", border: "none", color: "#fff" }}
                  />
                  <Legend wrapperStyle={{ fontSize: 12, fontWeight: 700 }} />
                  <Bar dataKey="Portfolio" fill="#8b5cf6" radius={[6, 6, 0, 0]} />
                  <Bar dataKey="Benchmark" fill="#64748b" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </MeasuredChartFrame>
          </div>

          {/* Navigation Tabs */}
          <div className="flex gap-2 border-b border-black/10 dark:border-white/10">
            <button
              onClick={() => setActiveTab("comparison")}
              className={`flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-black uppercase tracking-wider transition-all ${
                activeTab === "comparison"
                  ? "border-violet-500 text-violet-800 dark:text-violet-300"
                  : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              <BarChart3 size={15} />
              Multi-Ratio Benchmark-Vergleich
            </button>

            <button
              onClick={() => setActiveTab("holdings")}
              className={`flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-black uppercase tracking-wider transition-all ${
                activeTab === "holdings"
                  ? "border-violet-500 text-violet-800 dark:text-violet-300"
                  : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              <Layers size={15} />
              Holdings Ratio-Tabelle ({data.holdings.length})
            </button>

            <button
              onClick={() => setActiveTab("handbook")}
              className={`flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-black uppercase tracking-wider transition-all ${
                activeTab === "handbook"
                  ? "border-violet-500 text-violet-800 dark:text-violet-300"
                  : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              <Info size={15} />
              CFA Formelhandbuch
            </button>
          </div>

          {/* TAB 1: Comparison Matrix */}
          {activeTab === "comparison" && (
            <div className="overflow-x-auto rounded-2xl border border-black/10 bg-white/90 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-black/10 bg-slate-100/75 dark:border-white/10 dark:bg-slate-700/50 text-[10px] font-black uppercase tracking-wider text-slate-500 dark:text-slate-400">
                    <th className="p-3.5">Metrik</th>
                    <th className="p-3.5 text-right font-black text-violet-700 dark:text-violet-400">Portfolio</th>
                    <th className="p-3.5 text-right font-bold text-slate-600 dark:text-slate-400">{data.benchmark.name}</th>
                    <th className="p-3.5 text-right">Delta / Alpha</th>
                    <th className="p-3.5">Institutionelle Bedeutung</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/5 dark:divide-white/5 font-semibold text-slate-800 dark:text-slate-200">
                  <tr className="hover:bg-violet-500/5 transition-colors">
                    <td className="p-3.5 font-bold">Annualisierte Rendite</td>
                    <td className="p-3.5 text-right font-mono font-black">{data.ratios.annual_return_pct.toFixed(2)}%</td>
                    <td className="p-3.5 text-right font-mono text-slate-500">{data.benchmark.return_pct.toFixed(2)}%</td>
                    <td className={`p-3.5 text-right font-mono font-bold ${data.ratios.annual_return_pct >= data.benchmark.return_pct ? "text-emerald-600" : "text-rose-600"}`}>
                      {(data.ratios.annual_return_pct - data.benchmark.return_pct) >= 0 ? `+${(data.ratios.annual_return_pct - data.benchmark.return_pct).toFixed(2)}%` : `${(data.ratios.annual_return_pct - data.benchmark.return_pct).toFixed(2)}%`}
                    </td>
                    <td className="p-3.5 text-slate-500">Gesamtrendite p.a.</td>
                  </tr>

                  <tr className="hover:bg-violet-500/5 transition-colors">
                    <td className="p-3.5 font-bold">Sortino Ratio</td>
                    <td className="p-3.5 text-right font-mono font-black text-violet-700 dark:text-violet-400">{data.ratios.sortino_ratio.toFixed(2)}</td>
                    <td className="p-3.5 text-right font-mono text-slate-500">{data.benchmark.sortino_ratio.toFixed(2)}</td>
                    <td className={`p-3.5 text-right font-mono font-bold ${data.ratios.sortino_ratio >= data.benchmark.sortino_ratio ? "text-emerald-600" : "text-rose-600"}`}>
                      {(data.ratios.sortino_ratio - data.benchmark.sortino_ratio) >= 0 ? `+${(data.ratios.sortino_ratio - data.benchmark.sortino_ratio).toFixed(2)}` : `${(data.ratios.sortino_ratio - data.benchmark.sortino_ratio).toFixed(2)}`}
                    </td>
                    <td className="p-3.5 text-slate-500">Rendite pro Einheit Verlustrisiko (Downside Volatilität)</td>
                  </tr>

                  <tr className="hover:bg-violet-500/5 transition-colors">
                    <td className="p-3.5 font-bold">Sharpe Ratio</td>
                    <td className="p-3.5 text-right font-mono font-black">{data.ratios.sharpe_ratio.toFixed(2)}</td>
                    <td className="p-3.5 text-right font-mono text-slate-500">{data.benchmark.sharpe_ratio.toFixed(2)}</td>
                    <td className={`p-3.5 text-right font-mono font-bold ${data.ratios.sharpe_ratio >= data.benchmark.sharpe_ratio ? "text-emerald-600" : "text-rose-600"}`}>
                      {(data.ratios.sharpe_ratio - data.benchmark.sharpe_ratio) >= 0 ? `+${(data.ratios.sharpe_ratio - data.benchmark.sharpe_ratio).toFixed(2)}` : `${(data.ratios.sharpe_ratio - data.benchmark.sharpe_ratio).toFixed(2)}`}
                    </td>
                    <td className="p-3.5 text-slate-500">Überschussrendite über Rf ({data.risk_free_rate_pct.toFixed(2)}%) pro Einheit Gesamtvolatilität</td>
                  </tr>

                  <tr className="hover:bg-violet-500/5 transition-colors">
                    <td className="p-3.5 font-bold">Calmar Ratio</td>
                    <td className="p-3.5 text-right font-mono font-black">{data.ratios.calmar_ratio.toFixed(2)}</td>
                    <td className="p-3.5 text-right font-mono text-slate-500">{data.benchmark.calmar_ratio.toFixed(2)}</td>
                    <td className={`p-3.5 text-right font-mono font-bold ${data.ratios.calmar_ratio >= data.benchmark.calmar_ratio ? "text-emerald-600" : "text-rose-600"}`}>
                      {(data.ratios.calmar_ratio - data.benchmark.calmar_ratio) >= 0 ? `+${(data.ratios.calmar_ratio - data.benchmark.calmar_ratio).toFixed(2)}` : `${(data.ratios.calmar_ratio - data.benchmark.calmar_ratio).toFixed(2)}`}
                    </td>
                    <td className="p-3.5 text-slate-500">Erholungseffizienz: Jahresrendite geteilt durch maximalen Drawdown</td>
                  </tr>

                  <tr className="hover:bg-violet-500/5 transition-colors">
                    <td className="p-3.5 font-bold">Treynor Ratio</td>
                    <td className="p-3.5 text-right font-mono font-black">{data.ratios.treynor_ratio.toFixed(2)}</td>
                    <td className="p-3.5 text-right font-mono text-slate-500">--</td>
                    <td className="p-3.5 text-right font-mono text-slate-500">--</td>
                    <td className="p-3.5 text-slate-500">Überschussrendite pro Einheit Marktrisiko (Beta: {data.ratios.beta.toFixed(2)})</td>
                  </tr>

                  <tr className="hover:bg-violet-500/5 transition-colors">
                    <td className="p-3.5 font-bold">Omega Ratio</td>
                    <td className="p-3.5 text-right font-mono font-black">{data.ratios.omega_ratio.toFixed(2)}</td>
                    <td className="p-3.5 text-right font-mono text-slate-500">{data.benchmark.omega_ratio.toFixed(2)}</td>
                    <td className={`p-3.5 text-right font-mono font-bold ${data.ratios.omega_ratio >= data.benchmark.omega_ratio ? "text-emerald-600" : "text-rose-600"}`}>
                      {(data.ratios.omega_ratio - data.benchmark.omega_ratio) >= 0 ? `+${(data.ratios.omega_ratio - data.benchmark.omega_ratio).toFixed(2)}` : `${(data.ratios.omega_ratio - data.benchmark.omega_ratio).toFixed(2)}`}
                    </td>
                    <td className="p-3.5 text-slate-500">Wahrscheinlichkeitsverhältnis von Gewinnen zu Verlusten über Rf</td>
                  </tr>

                  <tr className="hover:bg-violet-500/5 transition-colors">
                    <td className="p-3.5 font-bold">Pain Index</td>
                    <td className="p-3.5 text-right font-mono font-black">{data.ratios.pain_index.toFixed(2)}</td>
                    <td className="p-3.5 text-right font-mono text-slate-500">{data.benchmark.pain_index.toFixed(2)}</td>
                    <td className={`p-3.5 text-right font-mono font-bold ${data.ratios.pain_index <= data.benchmark.pain_index ? "text-emerald-600" : "text-rose-600"}`}>
                      {(data.ratios.pain_index - data.benchmark.pain_index) <= 0 ? `${(data.ratios.pain_index - data.benchmark.pain_index).toFixed(2)}` : `+${(data.ratios.pain_index - data.benchmark.pain_index).toFixed(2)}`}
                    </td>
                    <td className="p-3.5 text-slate-500">Mittlere Unterwassertiefe &amp; psychologische Belastung (niedriger ist besser)</td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}

          {/* TAB 2: Holdings Table */}
          {activeTab === "holdings" && (
            <div className="overflow-x-auto rounded-2xl border border-black/10 bg-white/90 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-black/10 bg-slate-100/75 dark:border-white/10 dark:bg-slate-700/50 text-[10px] font-black uppercase tracking-wider text-slate-500 dark:text-slate-400">
                    <th className="p-3.5">Asset</th>
                    <th className="p-3.5 text-right">Gewicht %</th>
                    <th className="p-3.5 text-right">Rendite %</th>
                    <th className="p-3.5 text-right">Volatilität %</th>
                    <th className="p-3.5 text-right">Downside Dev %</th>
                    <th className="p-3.5 text-right">MaxDD %</th>
                    <th className="p-3.5 text-right font-black text-violet-700 dark:text-violet-400">Sortino</th>
                    <th className="p-3.5 text-right">Sharpe</th>
                    <th className="p-3.5 text-right">Calmar</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/5 dark:divide-white/5 font-semibold text-slate-800 dark:text-slate-200">
                  {data.holdings.map((h) => (
                    <tr key={h.ticker} className="hover:bg-violet-500/5 transition-colors">
                      <td className="p-3.5">
                        <button
                          onClick={() => onAnalyzeStock && onAnalyzeStock(h.ticker)}
                          className="font-black text-violet-700 hover:underline dark:text-violet-400 text-left"
                        >
                          {h.ticker}
                        </button>
                        <div className="text-[11px] text-slate-500 truncate max-w-[150px]">{h.name}</div>
                      </td>
                      <td className="p-3.5 text-right font-mono font-bold">{h.weight_pct.toFixed(1)}%</td>
                      <td className="p-3.5 text-right font-mono">{h.return_pct.toFixed(1)}%</td>
                      <td className="p-3.5 text-right font-mono text-slate-500">{h.volatility_pct.toFixed(1)}%</td>
                      <td className="p-3.5 text-right font-mono text-slate-500">{h.downside_deviation_pct.toFixed(1)}%</td>
                      <td className="p-3.5 text-right font-mono text-rose-600">{h.max_drawdown_pct.toFixed(1)}%</td>
                      <td className="p-3.5 text-right font-mono font-black text-violet-700 dark:text-violet-400">
                        {h.sortino_ratio.toFixed(2)}
                      </td>
                      <td className="p-3.5 text-right font-mono font-bold">{h.sharpe_ratio.toFixed(2)}</td>
                      <td className="p-3.5 text-right font-mono">{h.calmar_ratio.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* TAB 3: Handbook */}
          {activeTab === "handbook" && (
            <div className="rounded-2xl border border-black/10 bg-white/80 p-6 shadow-sm dark:border-white/10 dark:bg-slate-800/80 space-y-4 text-xs">
              <h3 className="text-base font-black text-slate-900 dark:text-white">
                CFA Formelhandbuch &amp; Schwellenwerte
              </h3>

              <div className="grid gap-4 md:grid-cols-3">
                <div className="rounded-xl border border-black/10 bg-white p-4 dark:border-white/10 dark:bg-slate-900">
                  <div className="font-black text-violet-700 dark:text-violet-400">Sortino Ratio</div>
                  <div className="mt-1 font-mono text-[11px] text-slate-500">
                    Sortino = (R_p - R_f) / DownsideDev
                  </div>
                  <p className="mt-2 text-slate-600 dark:text-slate-400">
                    Kritisch überlegen zur Sharpe Ratio, da nur Kurseinbrüche unter den risikolosen Zinssatz bestraft werden. Werte &gt; 2.0 gelten als weltklasse.
                  </p>
                </div>

                <div className="rounded-xl border border-black/10 bg-white p-4 dark:border-white/10 dark:bg-slate-900">
                  <div className="font-black text-violet-700 dark:text-violet-400">Calmar Ratio</div>
                  <div className="mt-1 font-mono text-[11px] text-slate-500">
                    Calmar = CAGR / |MaxDrawdown|
                  </div>
                  <p className="mt-2 text-slate-600 dark:text-slate-400">
                    Standardkennzahl im Hedgefonds-Bereich. Ein Calmar &gt; 1.0 bedeutet, dass die Jahresrendite den gesamten historischen Maximaleinbruch übersteigt.
                  </p>
                </div>

                <div className="rounded-xl border border-black/10 bg-white p-4 dark:border-white/10 dark:bg-slate-900">
                  <div className="font-black text-violet-700 dark:text-violet-400">Omega Ratio</div>
                  <div className="mt-1 font-mono text-[11px] text-slate-500">
                    Omega = Integral(Gewinne) / Integral(Verluste)
                  </div>
                  <p className="mt-2 text-slate-600 dark:text-slate-400">
                    Erfasst die vollständige Wahrscheinlichkeitsverteilung inklusive Schiefe (Skewness) und Fat Tails. Werte &gt; 1.4 zeigen klare Übergewichtung profitabler Pfade.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
