import React, { useEffect, useState } from "react";
import {
  Award,
  TrendingUp,
  TrendingDown,
  Layers,
  Info,
  RefreshCw,
  X,
  PieChart,
  Target,
  Sliders,
  CheckCircle2,
  AlertCircle,
  BarChart3
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
  ReferenceLine
} from "recharts";
import MeasuredChartFrame from "./MeasuredChartFrame";

interface SectorAttributionRow {
  sector: string;
  portfolio_weight_pct: number;
  benchmark_weight_pct: number;
  active_weight_pct: number;
  portfolio_return_pct: number;
  benchmark_return_pct: number;
  allocation_effect_pct: number;
  selection_effect_pct: number;
  interaction_effect_pct: number;
  total_effect_pct: number;
}

interface StockAlphaHighlight {
  ticker: string;
  name: string;
  sector: string;
  weight_pct: number;
  return_pct: number;
  benchmark_sector_return_pct: number;
  excess_alpha_pct: number;
  alpha_contribution_pct: number;
}

interface AttributionData {
  valid: boolean;
  error?: string;
  benchmark_key: string;
  benchmark_name: string;
  summary: {
    portfolio_return_pct: number;
    benchmark_return_pct: number;
    active_return_pct: number;
    allocation_effect_pct: number;
    selection_effect_pct: number;
    interaction_effect_pct: number;
    active_share_pct: number;
    style_badge: {
      label: string;
      tone: string;
    };
  };
  sectors: SectorAttributionRow[];
  stock_highlights: StockAlphaHighlight[];
}

interface BrinsonAttributionTerminalProps {
  portfolioId: string;
  onAnalyzeStock?: (ticker: string) => void;
  onClose?: () => void;
}

export default function BrinsonAttributionTerminal({
  portfolioId,
  onAnalyzeStock,
  onClose
}: BrinsonAttributionTerminalProps) {
  const [data, setData] = useState<AttributionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [benchmark, setBenchmark] = useState<string>("msci_world");
  const [activeTab, setActiveTab] = useState<"sectors" | "stocks" | "methodology">("sectors");

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/portfolio/${portfolioId}/attribution?benchmark=${benchmark}`, {
        credentials: "same-origin"
      });
      if (!res.ok) {
        throw new Error(`HTTP Fehler ${res.status}: Attributionsdaten konnten nicht geladen werden.`);
      }
      const json: AttributionData = await res.json();
      if (!json.valid) {
        throw new Error(json.error || "Ungültige Attributionsdaten erhalten.");
      }
      setData(json);
    } catch (err: any) {
      setError(err.message || "Fehler beim Berechnen der Brinson-Attribution.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (portfolioId) {
      fetchData();
    }
  }, [portfolioId, benchmark]);

  const waterfallData = data ? [
    {
      name: "Allokation",
      value: data.summary.allocation_effect_pct,
      color: data.summary.allocation_effect_pct >= 0 ? "#10b981" : "#f43f5e"
    },
    {
      name: "Selektion",
      value: data.summary.selection_effect_pct,
      color: data.summary.selection_effect_pct >= 0 ? "#10b981" : "#f43f5e"
    },
    {
      name: "Interaktion",
      value: data.summary.interaction_effect_pct,
      color: data.summary.interaction_effect_pct >= 0 ? "#10b981" : "#f43f5e"
    },
    {
      name: "Aktive Rendite (ΔR)",
      value: data.summary.active_return_pct,
      color: data.summary.active_return_pct >= 0 ? "#6366f1" : "#e11d48"
    }
  ] : [];

  return (
    <section className="mt-8 rounded-[2rem] border border-indigo-500/20 bg-gradient-to-b from-indigo-950/[0.04] to-transparent p-6 dark:border-indigo-500/30 dark:bg-slate-900/60 shadow-xl backdrop-blur-md">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-black/10 pb-5 dark:border-white/10">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-500/15 text-indigo-700 dark:text-indigo-400 border border-indigo-500/30 shadow-inner">
            <Award size={24} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-black tracking-tight text-slate-900 dark:text-white">
                Performance Attribution &amp; Brinson-Fachler Terminal
              </h2>
              <span className="rounded-md border border-indigo-500/30 bg-indigo-500/15 px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider text-indigo-800 dark:text-indigo-300">
                GIPS Standard
              </span>
            </div>
            <p className="text-xs font-semibold text-slate-600 dark:text-slate-400">
              Mathematische Zerlegung der Überrendite in Allokations-Effekt, Selektions-Alpha &amp; Active Share
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
              className="rounded-lg bg-transparent text-xs font-black text-indigo-700 dark:text-indigo-400 outline-none cursor-pointer"
            >
              <option value="msci_world">MSCI World Net TR</option>
              <option value="sp500">S&amp;P 500 Total Return</option>
              <option value="dax">DAX 40 Performance</option>
              <option value="stoxx600">STOXX Europe 600 Net</option>
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
          <RefreshCw size={36} className="animate-spin text-indigo-600 dark:text-indigo-400" />
          <p className="mt-4 text-sm font-bold text-slate-700 dark:text-slate-300">
            Berechne Brinson-Fachler Attributions-Effekte &amp; Active Share...
          </p>
        </div>
      )}

      {error && (
        <div className="my-6 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-5 text-rose-800 dark:text-rose-300">
          <div className="flex items-center gap-2 font-black">
            <AlertCircle size={18} />
            Fehler bei der Performance-Attribution
          </div>
          <p className="mt-1 text-xs">{error}</p>
        </div>
      )}

      {!loading && !error && data && (
        <div className="mt-6 space-y-6">
          {/* 4 Scorecards */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {/* Card 1: Active Return */}
            <div className="rounded-2xl border border-black/10 bg-white/90 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Aktive Überrendite (ΔR)
                </span>
                {data.summary.active_return_pct >= 0 ? (
                  <TrendingUp size={16} className="text-emerald-600 dark:text-emerald-400" />
                ) : (
                  <TrendingDown size={16} className="text-rose-600 dark:text-rose-400" />
                )}
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className={`text-3xl font-black ${data.summary.active_return_pct >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"}`}>
                  {data.summary.active_return_pct >= 0 ? `+${data.summary.active_return_pct.toFixed(2)}%` : `${data.summary.active_return_pct.toFixed(2)}%`}
                </span>
                <span className="text-xs font-bold text-slate-500">vs. Benchmark</span>
              </div>
              <div className="mt-2 text-xs font-medium text-slate-500 dark:text-slate-400">
                Portfolio: <strong className="text-slate-900 dark:text-white">{data.summary.portfolio_return_pct.toFixed(1)}%</strong> vs. {data.benchmark_name}: <strong className="text-slate-900 dark:text-white">{data.summary.benchmark_return_pct.toFixed(1)}%</strong>
              </div>
            </div>

            {/* Card 2: Selection Effect */}
            <div className="rounded-2xl border border-black/10 bg-white/90 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Selektions-Alpha (Stock-Picking)
                </span>
                <Award size={16} className="text-indigo-600 dark:text-indigo-400" />
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className={`text-3xl font-black ${data.summary.selection_effect_pct >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"}`}>
                  {data.summary.selection_effect_pct >= 0 ? `+${data.summary.selection_effect_pct.toFixed(2)}%` : `${data.summary.selection_effect_pct.toFixed(2)}%`}
                </span>
              </div>
              <div className="mt-2 text-xs font-medium text-slate-500 dark:text-slate-400">
                Mehrwert durch überlegene Einzeltitelauswahl je Sektor
              </div>
            </div>

            {/* Card 3: Allocation Effect */}
            <div className="rounded-2xl border border-black/10 bg-white/90 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Allokations-Effekt (Sektor-Timing)
                </span>
                <PieChart size={16} className="text-indigo-600 dark:text-indigo-400" />
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className={`text-3xl font-black ${data.summary.allocation_effect_pct >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"}`}>
                  {data.summary.allocation_effect_pct >= 0 ? `+${data.summary.allocation_effect_pct.toFixed(2)}%` : `${data.summary.allocation_effect_pct.toFixed(2)}%`}
                </span>
              </div>
              <div className="mt-2 text-xs font-medium text-slate-500 dark:text-slate-400">
                Mehrwert durch Über-/Untergewichtung von Sektoren
              </div>
            </div>

            {/* Card 4: Active Share */}
            <div className="rounded-2xl border border-black/10 bg-white/90 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Active Share (GIPS)
                </span>
                <BarChart3 size={16} className="text-indigo-600 dark:text-indigo-400" />
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-black text-slate-900 dark:text-white">
                  {data.summary.active_share_pct.toFixed(1)}%
                </span>
              </div>
              <div className="mt-2">
                <span className={`rounded-md border px-2 py-0.5 text-[10px] font-black uppercase ${data.summary.style_badge.tone}`}>
                  {data.summary.style_badge.label}
                </span>
              </div>
            </div>
          </div>

          {/* Waterfall Chart */}
          <div className="rounded-2xl border border-black/10 bg-white/80 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/80">
            <h3 className="text-sm font-black text-slate-900 dark:text-white">
              Brinson-Fachler Attributions-Zerlegung
            </h3>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Beitrag der einzelnen Alpha-Treiber zur gesamten Überrendite gegenüber {data.benchmark_name}
            </p>

            <MeasuredChartFrame className="mt-4 w-full" minHeight={200}>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={waterfallData} margin={{ top: 20, right: 30, left: 10, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fontWeight: 700 }} />
                  <YAxis unit="%" tick={{ fontSize: 11 }} />
                  <ReferenceLine y={0} stroke="#94a3b8" />
                  <Tooltip
                    formatter={(value: any) => [`${Number(value) >= 0 ? "+" : ""}${Number(value).toFixed(2)}%`, "Effekt"]}
                    contentStyle={{ backgroundColor: "#0f172a", borderRadius: "12px", border: "none", color: "#fff" }}
                  />
                  <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                    {waterfallData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </MeasuredChartFrame>
          </div>

          {/* Navigation Tabs */}
          <div className="flex gap-2 border-b border-black/10 dark:border-white/10">
            <button
              onClick={() => setActiveTab("sectors")}
              className={`flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-black uppercase tracking-wider transition-all ${
                activeTab === "sectors"
                  ? "border-indigo-500 text-indigo-800 dark:text-indigo-300"
                  : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              <PieChart size={15} />
              Sektor-Attributions-Matrix ({data.sectors.length})
            </button>

            <button
              onClick={() => setActiveTab("stocks")}
              className={`flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-black uppercase tracking-wider transition-all ${
                activeTab === "stocks"
                  ? "border-indigo-500 text-indigo-800 dark:text-indigo-300"
                  : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              <Award size={15} />
              Stock-Level Alpha-Treiber ({data.stock_highlights.length})
            </button>

            <button
              onClick={() => setActiveTab("methodology")}
              className={`flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-black uppercase tracking-wider transition-all ${
                activeTab === "methodology"
                  ? "border-indigo-500 text-indigo-800 dark:text-indigo-300"
                  : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              <Info size={15} />
              GIPS Formeln &amp; Methodik
            </button>
          </div>

          {/* TAB 1: Sector Matrix */}
          {activeTab === "sectors" && (
            <div className="overflow-x-auto rounded-2xl border border-black/10 bg-white/90 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-black/10 bg-slate-100/75 dark:border-white/10 dark:bg-slate-700/50 text-[10px] font-black uppercase tracking-wider text-slate-500 dark:text-slate-400">
                    <th className="p-3.5">GICS Sektor</th>
                    <th className="p-3.5 text-right">Portfolio %</th>
                    <th className="p-3.5 text-right">Benchmark %</th>
                    <th className="p-3.5 text-right">Aktiv (Δw)</th>
                    <th className="p-3.5 text-right">Rendite Port %</th>
                    <th className="p-3.5 text-right">Rendite Bench %</th>
                    <th className="p-3.5 text-right">Allokation %</th>
                    <th className="p-3.5 text-right">Selektion %</th>
                    <th className="p-3.5 text-right">Interaktion %</th>
                    <th className="p-3.5 text-right font-black">Gesamteffekt %</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/5 dark:divide-white/5 font-semibold text-slate-800 dark:text-slate-200">
                  {data.sectors.map((s) => (
                    <tr key={s.sector} className="hover:bg-indigo-500/5 transition-colors">
                      <td className="p-3.5 font-bold text-slate-900 dark:text-white">{s.sector}</td>
                      <td className="p-3.5 text-right font-mono">{s.portfolio_weight_pct.toFixed(1)}%</td>
                      <td className="p-3.5 text-right font-mono text-slate-500">{s.benchmark_weight_pct.toFixed(1)}%</td>
                      <td className="p-3.5 text-right font-mono">
                        <span className={s.active_weight_pct > 0 ? "text-indigo-600 dark:text-indigo-400 font-bold" : s.active_weight_pct < 0 ? "text-amber-600 dark:text-amber-400 font-bold" : ""}>
                          {s.active_weight_pct >= 0 ? `+${s.active_weight_pct.toFixed(1)}%` : `${s.active_weight_pct.toFixed(1)}%`}
                        </span>
                      </td>
                      <td className="p-3.5 text-right font-mono">{s.portfolio_return_pct.toFixed(1)}%</td>
                      <td className="p-3.5 text-right font-mono text-slate-500">{s.benchmark_return_pct.toFixed(1)}%</td>
                      <td className={`p-3.5 text-right font-mono ${s.allocation_effect_pct >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"}`}>
                        {s.allocation_effect_pct >= 0 ? `+${s.allocation_effect_pct.toFixed(2)}%` : `${s.allocation_effect_pct.toFixed(2)}%`}
                      </td>
                      <td className={`p-3.5 text-right font-mono ${s.selection_effect_pct >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"}`}>
                        {s.selection_effect_pct >= 0 ? `+${s.selection_effect_pct.toFixed(2)}%` : `${s.selection_effect_pct.toFixed(2)}%`}
                      </td>
                      <td className={`p-3.5 text-right font-mono ${s.interaction_effect_pct >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"}`}>
                        {s.interaction_effect_pct >= 0 ? `+${s.interaction_effect_pct.toFixed(2)}%` : `${s.interaction_effect_pct.toFixed(2)}%`}
                      </td>
                      <td className={`p-3.5 text-right font-black ${s.total_effect_pct >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"}`}>
                        {s.total_effect_pct >= 0 ? `+${s.total_effect_pct.toFixed(2)}%` : `${s.total_effect_pct.toFixed(2)}%`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* TAB 2: Stock Highlights */}
          {activeTab === "stocks" && (
            <div className="overflow-x-auto rounded-2xl border border-black/10 bg-white/90 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-black/10 bg-slate-100/75 dark:border-white/10 dark:bg-slate-700/50 text-[10px] font-black uppercase tracking-wider text-slate-500 dark:text-slate-400">
                    <th className="p-3.5">Asset</th>
                    <th className="p-3.5">Sektor</th>
                    <th className="p-3.5 text-right">Gewicht %</th>
                    <th className="p-3.5 text-right">Asset-Rendite %</th>
                    <th className="p-3.5 text-right">Sektor-Benchmark %</th>
                    <th className="p-3.5 text-right">Excess Alpha (vs Sektor)</th>
                    <th className="p-3.5 text-right font-black">Alpha-Beitrag zum Portfolio</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/5 dark:divide-white/5 font-semibold text-slate-800 dark:text-slate-200">
                  {data.stock_highlights.map((h) => (
                    <tr key={h.ticker} className="hover:bg-indigo-500/5 transition-colors">
                      <td className="p-3.5">
                        <button
                          onClick={() => onAnalyzeStock && onAnalyzeStock(h.ticker)}
                          className="font-black text-indigo-700 hover:underline dark:text-indigo-400 text-left"
                        >
                          {h.ticker}
                        </button>
                        <div className="text-[11px] text-slate-500 truncate max-w-[150px]">{h.name}</div>
                      </td>
                      <td className="p-3.5 text-slate-600 dark:text-slate-300">{h.sector}</td>
                      <td className="p-3.5 text-right font-mono">{h.weight_pct.toFixed(1)}%</td>
                      <td className="p-3.5 text-right font-mono">{h.return_pct.toFixed(1)}%</td>
                      <td className="p-3.5 text-right font-mono text-slate-500">{h.benchmark_sector_return_pct.toFixed(1)}%</td>
                      <td className={`p-3.5 text-right font-mono ${h.excess_alpha_pct >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"}`}>
                        {h.excess_alpha_pct >= 0 ? `+${h.excess_alpha_pct.toFixed(2)}%` : `${h.excess_alpha_pct.toFixed(2)}%`}
                      </td>
                      <td className={`p-3.5 text-right font-black ${h.alpha_contribution_pct >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"}`}>
                        {h.alpha_contribution_pct >= 0 ? `+${h.alpha_contribution_pct.toFixed(3)}%` : `${h.alpha_contribution_pct.toFixed(3)}%`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* TAB 3: Methodology */}
          {activeTab === "methodology" && (
            <div className="rounded-2xl border border-black/10 bg-white/80 p-6 shadow-sm dark:border-white/10 dark:bg-slate-800/80 space-y-4 text-xs">
              <h3 className="text-base font-black text-slate-900 dark:text-white">
                GIPS Brinson-Fachler (1985) Formeln &amp; Interpretation
              </h3>
              <p className="text-slate-600 dark:text-slate-300 leading-relaxed">
                Das Brinson-Fachler-Modell ist der weltweite Standard institutioneller Vermögensverwalter (CFA Institute &amp; GIPS), um die aktive Überrendite ΔR = R(Port) - R(Bench) trennscharf in fundamentale Fähigkeiten zu zerlegen:
              </p>

              <div className="grid gap-4 md:grid-cols-3">
                <div className="rounded-xl border border-black/10 bg-white p-4 dark:border-white/10 dark:bg-slate-900">
                  <div className="font-black text-indigo-700 dark:text-indigo-400">1. Allokations-Effekt (Sektor-Timing)</div>
                  <div className="mt-1 font-mono text-[11px] text-slate-500">
                    A_j = (w_p,j - w_b,j) * (R_b,j - R_b)
                  </div>
                  <p className="mt-2 text-slate-600 dark:text-slate-400">
                    Belohnt Übergewicht in Sektoren, die besser als der gesamte Benchmark-Index abgeschnitten haben, und Untergewicht in schwächeren Sektoren.
                  </p>
                </div>

                <div className="rounded-xl border border-black/10 bg-white p-4 dark:border-white/10 dark:bg-slate-900">
                  <div className="font-black text-indigo-700 dark:text-indigo-400">2. Selektions-Effekt (Stock-Picking)</div>
                  <div className="mt-1 font-mono text-[11px] text-slate-500">
                    S_j = w_b,j * (R_p,j - R_b,j)
                  </div>
                  <p className="mt-2 text-slate-600 dark:text-slate-400">
                    Isoliert die Fähigkeit, innerhalb eines bestimmten Sektors die Gewinneraktien gegenüber dem Sektordurchschnitt ausgewählt zu haben.
                  </p>
                </div>

                <div className="rounded-xl border border-black/10 bg-white p-4 dark:border-white/10 dark:bg-slate-900">
                  <div className="font-black text-indigo-700 dark:text-indigo-400">3. Interaktions-Effekt (Cross-Effekt)</div>
                  <div className="mt-1 font-mono text-[11px] text-slate-500">
                    I_j = (w_p,j - w_b,j) * (R_p,j - R_b,j)
                  </div>
                  <p className="mt-2 text-slate-600 dark:text-slate-400">
                    Kombinierter Effekt aus übergewichteter Allokation und gleichzeitiger Einzeltitelüberrendite im gleichen Sektor.
                  </p>
                </div>
              </div>

              <div className="mt-4 rounded-xl border border-indigo-500/20 bg-indigo-500/5 p-4">
                <div className="font-black text-indigo-900 dark:text-indigo-300">Active Share Definition (Cremers &amp; Petajisto)</div>
                <p className="mt-1 text-slate-700 dark:text-slate-300">
                  Misst den Prozentsatz des Portfolios, der sich von der Benchmark unterscheidet (0% = perfektes Replikat / ETF; &gt;80% = hochaktives Überzeugungsmandat). Portfolios mit Active Share unter 35% gelten als „Closet Indexing“ (versteckte Indexfonds mit zu hohen Gebühren).
                </p>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
