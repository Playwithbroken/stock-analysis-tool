import React, { useEffect, useState } from "react";
import {
  ShieldAlert,
  AlertOctagon,
  TrendingDown,
  Info,
  RefreshCw,
  Maximize2,
  Minimize2,
  Calendar,
  Layers,
  Flame,
  Scale,
  Sparkles,
  ArrowDownRight,
  Activity
} from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine
} from "recharts";
import MeasuredChartFrame from "./MeasuredChartFrame";

interface DistributionStats {
  mean_daily_pct: number;
  volatility_daily_pct: number;
  annualized_return_pct: number;
  annualized_volatility_pct: number;
  skewness: number;
  excess_kurtosis: number;
  is_fat_tailed: boolean;
}

interface VaRMatrix {
  parametric_var_95_pct: number;
  parametric_var_99_pct: number;
  historical_var_95_pct: number;
  historical_var_99_pct: number;
  cornish_fisher_var_95_pct: number;
  cornish_fisher_var_99_pct: number;
  expected_shortfall_95_pct: number;
  expected_shortfall_99_pct: number;
  cvar_10d_99_pct: number;
}

interface EuroStressLosses {
  loss_1d_95_eur: number;
  loss_1d_99_eur: number;
  cvar_1d_99_eur: number;
  cvar_10d_99_eur: number;
}

interface DrawdownStats {
  max_drawdown_pct: number;
  max_drawdown_date: string;
  current_drawdown_pct: number;
  ulcer_index: number;
  calmar_ratio: number;
  is_at_all_time_high: boolean;
}

interface UnderwaterPoint {
  date: string;
  drawdown_pct: number;
  high_water_mark_pct: number;
}

interface ComponentVaRItem {
  ticker: string;
  name: string;
  weight_pct: number;
  asset_beta_to_portfolio: number;
  tail_risk_contribution_pct: number;
  loss_contribution_eur: number;
}

interface TailRiskResponse {
  valid: boolean;
  timeframe: string;
  portfolio_value_eur: number;
  observations_count: number;
  distribution: DistributionStats;
  var_matrix: VaRMatrix;
  euro_stress_losses: EuroStressLosses;
  drawdown: DrawdownStats;
  underwater_chart: UnderwaterPoint[];
  component_var: ComponentVaRItem[];
  error?: string;
}

interface TailRiskTerminalProps {
  portfolioId: string;
  onAnalyzeStock?: (ticker: string) => void;
  onClose?: () => void;
}

export default function TailRiskTerminal({
  portfolioId,
  onAnalyzeStock,
  onClose
}: TailRiskTerminalProps) {
  const [data, setData] = useState<TailRiskResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [timeframe, setTimeframe] = useState<"1y" | "3y" | "5y">("1y");
  const [activeTab, setActiveTab] = useState<"underwater" | "var_matrix" | "attribution">("underwater");
  const [isExpanded, setIsExpanded] = useState(false);

  const fetchTailRisk = async (tf: string) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/portfolio/${portfolioId}/tail-risk?timeframe=${tf}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: TailRiskResponse = await res.json();
      setData(json);
    } catch (e) {
      console.error("Failed to load tail risk data:", e);
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (portfolioId) {
      fetchTailRisk(timeframe);
    }
  }, [portfolioId, timeframe]);

  if (loading && !data) {
    return (
      <div className="surface-panel rounded-[2rem] p-6 text-center">
        <div className="flex flex-col items-center justify-center gap-3 py-12">
          <RefreshCw className="h-7 w-7 animate-spin text-rose-600 dark:text-rose-400" />
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">
            Berechne Tail-Risk, Cornish-Fisher VaR & Expected Shortfall...
          </p>
          <p className="text-xs text-slate-500">
            Underwater-Historie, Ulcer Index und Basel-III 10-Tages-Stresstest
          </p>
        </div>
      </div>
    );
  }

  if (!data || !data.valid || !data.underwater_chart || data.underwater_chart.length === 0) {
    return (
      <div className="surface-panel rounded-[2rem] p-6 text-center text-xs font-medium text-slate-700 dark:text-slate-300">
        <AlertOctagon size={32} className="mx-auto mb-2 text-amber-500" />
        Keine ausreichenden Kursdaten vorhanden, um das Tail-Risk-Profil zu berechnen.
      </div>
    );
  }

  const formatEur = (val: number) => {
    return new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(val);
  };

  const ulcerBadge =
    data.drawdown.ulcer_index <= 3.0
      ? { label: "Gering", color: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30" }
      : data.drawdown.ulcer_index <= 7.0
      ? { label: "Moderat", color: "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30" }
      : { label: "Erhöht", color: "bg-rose-500/15 text-rose-700 dark:text-rose-400 border-rose-500/30" };

  return (
    <div
      className={`surface-panel rounded-[2rem] p-6 transition-all duration-300 ${
        isExpanded ? "fixed inset-4 z-50 overflow-y-auto bg-slate-900/95 shadow-2xl backdrop-blur-xl" : ""
      }`}
    >
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-black/8 pb-4 dark:border-white/10">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-rose-500/10 p-2.5 text-rose-600 dark:bg-rose-500/20 dark:text-rose-400">
            <AlertOctagon size={22} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold text-slate-900 dark:text-white">
                Tail Risk, VaR & Underwater Terminal
              </h3>
              <span className="rounded-full bg-rose-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-rose-700 dark:text-rose-300">
                Basel III / Solvency II
              </span>
            </div>
            <p className="text-xs text-slate-600 dark:text-slate-400">
              Expected Shortfall (CVaR), Cornish-Fisher Fat Tails, Maximum Drawdown & Ulcer Index
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Timeframe selector */}
          <div className="flex rounded-xl border border-black/10 bg-slate-100 p-1 dark:border-white/10 dark:bg-slate-800">
            {(["1y", "3y", "5y"] as const).map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition-all ${
                  timeframe === tf
                    ? "bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-white"
                    : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
                }`}
              >
                {tf === "1y" ? "1J" : tf === "3y" ? "3J" : "5J"}
              </button>
            ))}
          </div>

          {/* Expand / Minimize */}
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="rounded-xl border border-black/10 bg-white/60 p-2 text-slate-600 hover:bg-white hover:text-slate-900 dark:border-white/10 dark:bg-slate-800/60 dark:text-slate-300 dark:hover:bg-slate-800"
            title={isExpanded ? "Minimieren" : "Vollbildansicht"}
          >
            {isExpanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {/* Expected Shortfall CVaR 99% */}
        <div className="rounded-2xl border border-rose-500/20 bg-rose-500/5 p-3.5 shadow-sm dark:border-rose-500/30 dark:bg-rose-500/10">
          <div className="text-[11px] font-bold uppercase tracking-wider text-rose-800 dark:text-rose-300">
            Expected Shortfall (CVaR 99%)
          </div>
          <div className="mt-1.5 flex items-baseline gap-1.5">
            <span className="text-2xl font-black text-rose-600 dark:text-rose-400">
              -{data.var_matrix.expected_shortfall_99_pct.toFixed(2)}%
            </span>
            <span className="text-xs text-rose-700 dark:text-rose-300">1-Tag</span>
          </div>
          <div className="mt-1 font-mono text-xs font-bold text-slate-900 dark:text-white">
            ≈ {formatEur(data.euro_stress_losses.cvar_1d_99_eur)}
          </div>
          <p className="mt-1.5 text-[10px] text-slate-500 dark:text-slate-400">
            Ø Verlust in den schlimmsten 1% der Tage
          </p>
        </div>

        {/* Maximum Drawdown */}
        <div className="rounded-2xl border border-black/8 bg-white/70 p-3.5 shadow-sm dark:border-white/10 dark:bg-slate-800/60">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Max Drawdown (MDD)
          </div>
          <div className="mt-1.5 flex items-baseline gap-1.5">
            <span className="text-2xl font-black text-slate-900 dark:text-white">
              {data.drawdown.max_drawdown_pct.toFixed(1)}%
            </span>
          </div>
          <div className="mt-1 text-[11px] font-semibold text-slate-600 dark:text-slate-400">
            Tiefststand: {data.drawdown.max_drawdown_date || "Historisch"}
          </div>
          <p className="mt-1.5 text-[10px] text-slate-500 dark:text-slate-400">
            Aktueller Abstand zum ATH: {data.drawdown.current_drawdown_pct.toFixed(1)}%
          </p>
        </div>

        {/* Ulcer Index */}
        <div className="rounded-2xl border border-black/8 bg-white/70 p-3.5 shadow-sm dark:border-white/10 dark:bg-slate-800/60">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Ulcer Index (Schmerz-Index)
          </div>
          <div className="mt-1.5 flex items-baseline gap-2">
            <span className="text-2xl font-black text-slate-900 dark:text-white">
              {data.drawdown.ulcer_index.toFixed(1)}
            </span>
            <span
              className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-bold ${ulcerBadge.color}`}
            >
              {ulcerBadge.label}
            </span>
          </div>
          <p className="mt-2 text-[10px] text-slate-500 dark:text-slate-400">
            Gewichtete Tiefe & Dauer aller Drawdowns
          </p>
        </div>

        {/* 10-Day Basel Stress Loss */}
        <div className="rounded-2xl border border-black/8 bg-white/70 p-3.5 shadow-sm dark:border-white/10 dark:bg-slate-800/60">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            10-Tage Basel Stresstest
          </div>
          <div className="mt-1.5 flex items-baseline gap-1.5">
            <span className="text-2xl font-black text-amber-600 dark:text-amber-400">
              -{data.var_matrix.cvar_10d_99_pct.toFixed(1)}%
            </span>
            <span className="text-xs text-slate-500">10T</span>
          </div>
          <div className="mt-1 font-mono text-xs font-bold text-slate-900 dark:text-white">
            ≈ {formatEur(data.euro_stress_losses.cvar_10d_99_eur)}
          </div>
          <p className="mt-1.5 text-[10px] text-slate-500 dark:text-slate-400">
            Calmar Ratio: <strong className="text-slate-900 dark:text-white">{data.drawdown.calmar_ratio.toFixed(2)}</strong>
          </p>
        </div>
      </div>

      {/* Navigation Sub-Tabs */}
      <div className="mb-5 flex flex-wrap gap-2 border-b border-black/6 pb-2 dark:border-white/10">
        <button
          onClick={() => setActiveTab("underwater")}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
            activeTab === "underwater"
              ? "bg-rose-500/15 text-rose-700 dark:bg-rose-500/25 dark:text-rose-300"
              : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
          }`}
        >
          <TrendingDown size={14} />
          Underwater Drawdown Chart
        </button>

        <button
          onClick={() => setActiveTab("var_matrix")}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
            activeTab === "var_matrix"
              ? "bg-rose-500/15 text-rose-700 dark:bg-rose-500/25 dark:text-rose-300"
              : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
          }`}
        >
          <Scale size={14} />
          VaR & Basel-III Matrix
        </button>

        <button
          onClick={() => setActiveTab("attribution")}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
            activeTab === "attribution"
              ? "bg-rose-500/15 text-rose-700 dark:bg-rose-500/25 dark:text-rose-300"
              : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
          }`}
        >
          <Layers size={14} />
          Tail-Risk Attribution ({data.component_var.length})
        </button>
      </div>

      {/* Tab 1: Underwater Area Chart */}
      {activeTab === "underwater" && (
        <div>
          <div className="rounded-2xl border border-black/8 bg-white/40 p-4 dark:border-white/10 dark:bg-slate-900/40">
            <MeasuredChartFrame className="h-[340px] w-full" minHeight={340}>
              {({ w, h }) => (
                <AreaChart width={w} height={h} data={data.underwater_chart} margin={{ top: 10, right: 30, left: 10, bottom: 20 }}>
                  <defs>
                    <linearGradient id="underwaterGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#f43f5e" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11, fill: "#64748b" }}
                    tickFormatter={(val) => val.slice(2, 10)}
                  />
                  <YAxis
                    domain={["auto", 0]}
                    unit="%"
                    tick={{ fontSize: 11, fill: "#64748b" }}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload || !payload.length) return null;
                      const pt = payload[0].payload;
                      return (
                        <div className="rounded-xl border border-black/10 bg-slate-900 p-3 text-xs text-white shadow-xl dark:border-white/20">
                          <div className="font-bold text-slate-300">{pt.date}</div>
                          <div className="mt-1 flex justify-between gap-4">
                            <span className="text-slate-400">Drawdown zum ATH:</span>
                            <span className="font-mono font-bold text-rose-400">
                              {Number(pt.drawdown_pct).toFixed(2)}%
                            </span>
                          </div>
                        </div>
                      );
                    }}
                  />
                  {/* High Water Mark Line at 0% */}
                  <ReferenceLine y={0} stroke="#10b981" strokeWidth={2} label={{ value: "All-Time High (0%)", position: "top", fill: "#10b981", fontSize: 10, fontWeight: 700 }} />
                  {/* Max Drawdown Trough Line */}
                  <ReferenceLine
                    y={data.drawdown.max_drawdown_pct}
                    stroke="#f43f5e"
                    strokeDasharray="4 4"
                    label={{
                      value: `Max Drawdown (${data.drawdown.max_drawdown_pct.toFixed(1)}%)`,
                      position: "bottom",
                      fill: "#f43f5e",
                      fontSize: 10,
                      fontWeight: 700
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="drawdown_pct"
                    stroke="#f43f5e"
                    strokeWidth={2}
                    fillOpacity={1}
                    fill="url(#underwaterGrad)"
                    name="Drawdown %"
                  />
                </AreaChart>
              )}
            </MeasuredChartFrame>
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-black/8 bg-white/60 p-3 dark:border-white/10 dark:bg-slate-800/40">
            <div className="flex items-center gap-2 text-xs text-slate-700 dark:text-slate-300">
              <Activity size={15} className="text-rose-600 dark:text-rose-400" />
              <span>
                Schiefe (Skewness):{" "}
                <strong className="font-mono text-slate-900 dark:text-white">
                  {data.distribution.skewness.toFixed(2)}
                </strong>
                {" · "}
                Wölbung (Kurtosis):{" "}
                <strong className="font-mono text-slate-900 dark:text-white">
                  {data.distribution.excess_kurtosis.toFixed(2)}
                </strong>
              </span>
            </div>
            {data.distribution.is_fat_tailed && (
              <span className="rounded-full bg-rose-500/15 px-2.5 py-0.5 text-[11px] font-bold text-rose-700 dark:text-rose-300">
                ⚠️ Fat Tails erkannt: Crash-Wahrscheinlichkeit höher als bei Normalverteilung
              </span>
            )}
          </div>
        </div>
      )}

      {/* Tab 2: VaR Matrix */}
      {activeTab === "var_matrix" && (
        <div className="space-y-4">
          <div className="rounded-xl border border-rose-500/20 bg-rose-500/5 p-4 text-xs text-rose-900 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
            <div className="flex items-start gap-2.5">
              <Info size={16} className="mt-0.5 shrink-0 text-rose-600 dark:text-rose-400" />
              <p>
                <strong>Methoden-Vergleich:</strong> Der parametrische VaR unterstellt eine ideale
                Normalverteilung. Der <em>Cornish-Fisher VaR</em> und der <em>Expected Shortfall (CVaR)</em>{" "}
                berücksichtigen reale asymmetrische Marktcrashs und verhindern das Unterschätzen von
                Extremverlusten.
              </p>
            </div>
          </div>

          <div className="overflow-x-auto rounded-2xl border border-black/8 bg-white/70 shadow-xs dark:border-white/10 dark:bg-slate-900/60">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-black/8 bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:border-white/10 dark:bg-slate-800/60 dark:text-slate-400">
                  <th className="p-3">Risiko-Methode</th>
                  <th className="p-3 text-right">Konfidenz</th>
                  <th className="p-3 text-right">Zeithorizont</th>
                  <th className="p-3 text-right">Verlust (%)</th>
                  <th className="p-3 text-right">Potenzieller Verlust (€)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/6 dark:divide-white/6">
                <tr>
                  <td className="p-3 font-semibold text-slate-900 dark:text-white">Parametrischer VaR (Gauß)</td>
                  <td className="p-3 text-right font-mono">95%</td>
                  <td className="p-3 text-right">1 Tag</td>
                  <td className="p-3 text-right font-mono text-slate-700 dark:text-slate-300">
                    -{data.var_matrix.parametric_var_95_pct.toFixed(2)}%
                  </td>
                  <td className="p-3 text-right font-mono text-slate-700 dark:text-slate-300">
                    {formatEur((data.var_matrix.parametric_var_95_pct / 100) * data.portfolio_value_eur)}
                  </td>
                </tr>
                <tr>
                  <td className="p-3 font-semibold text-slate-900 dark:text-white">Parametrischer VaR (Gauß)</td>
                  <td className="p-3 text-right font-mono">99%</td>
                  <td className="p-3 text-right">1 Tag</td>
                  <td className="p-3 text-right font-mono text-slate-700 dark:text-slate-300">
                    -{data.var_matrix.parametric_var_99_pct.toFixed(2)}%
                  </td>
                  <td className="p-3 text-right font-mono text-slate-700 dark:text-slate-300">
                    {formatEur((data.var_matrix.parametric_var_99_pct / 100) * data.portfolio_value_eur)}
                  </td>
                </tr>
                <tr className="bg-amber-500/5">
                  <td className="p-3 font-bold text-amber-900 dark:text-amber-200">Historischer VaR (Empirisch)</td>
                  <td className="p-3 text-right font-mono font-bold text-amber-900 dark:text-amber-200">99%</td>
                  <td className="p-3 text-right font-bold text-amber-900 dark:text-amber-200">1 Tag</td>
                  <td className="p-3 text-right font-mono font-bold text-amber-700 dark:text-amber-300">
                    -{data.var_matrix.historical_var_99_pct.toFixed(2)}%
                  </td>
                  <td className="p-3 text-right font-mono font-bold text-amber-700 dark:text-amber-300">
                    {formatEur(data.euro_stress_losses.loss_1d_99_eur)}
                  </td>
                </tr>
                <tr>
                  <td className="p-3 font-semibold text-slate-900 dark:text-white">Cornish-Fisher Modified VaR</td>
                  <td className="p-3 text-right font-mono">99%</td>
                  <td className="p-3 text-right">1 Tag</td>
                  <td className="p-3 text-right font-mono text-slate-700 dark:text-slate-300">
                    -{data.var_matrix.cornish_fisher_var_99_pct.toFixed(2)}%
                  </td>
                  <td className="p-3 text-right font-mono text-slate-700 dark:text-slate-300">
                    {formatEur((data.var_matrix.cornish_fisher_var_99_pct / 100) * data.portfolio_value_eur)}
                  </td>
                </tr>
                <tr className="bg-rose-500/10 font-bold">
                  <td className="p-3 text-rose-900 dark:text-rose-200">Expected Shortfall (CVaR 99%)</td>
                  <td className="p-3 text-right font-mono text-rose-900 dark:text-rose-200">99%</td>
                  <td className="p-3 text-right text-rose-900 dark:text-rose-200">1 Tag</td>
                  <td className="p-3 text-right font-mono text-rose-600 dark:text-rose-400">
                    -{data.var_matrix.expected_shortfall_99_pct.toFixed(2)}%
                  </td>
                  <td className="p-3 text-right font-mono text-rose-600 dark:text-rose-400">
                    {formatEur(data.euro_stress_losses.cvar_1d_99_eur)}
                  </td>
                </tr>
                <tr className="bg-rose-500/15 font-bold">
                  <td className="p-3 text-rose-950 dark:text-rose-100">Basel-III 10-Tage Stresstest (CVaR)</td>
                  <td className="p-3 text-right font-mono text-rose-950 dark:text-rose-100">99%</td>
                  <td className="p-3 text-right text-rose-950 dark:text-rose-100">10 Tage (√10)</td>
                  <td className="p-3 text-right font-mono text-rose-700 dark:text-rose-300">
                    -{data.var_matrix.cvar_10d_99_pct.toFixed(1)}%
                  </td>
                  <td className="p-3 text-right font-mono text-rose-700 dark:text-rose-300">
                    {formatEur(data.euro_stress_losses.cvar_10d_99_eur)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 3: Component Tail-Risk Attribution */}
      {activeTab === "attribution" && (
        <div className="space-y-4">
          <div className="overflow-x-auto rounded-2xl border border-black/8 bg-white/70 shadow-xs dark:border-white/10 dark:bg-slate-900/60">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-black/8 bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:border-white/10 dark:bg-slate-800/60 dark:text-slate-400">
                  <th className="p-3">Asset</th>
                  <th className="p-3 text-right">Depotanteil</th>
                  <th className="p-3 text-right">Beta zum Depot</th>
                  <th className="p-3 text-right">Risiko-Anteil am Crash</th>
                  <th className="p-3 text-right">Verlustbeitrag (99% VaR)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/6 dark:divide-white/6">
                {data.component_var.map((row) => (
                  <tr
                    key={row.ticker}
                    onClick={() => onAnalyzeStock && onAnalyzeStock(row.ticker)}
                    className="cursor-pointer hover:bg-black/[0.02] dark:hover:bg-white/[0.02]"
                  >
                    <td className="p-3">
                      <div className="font-bold text-slate-900 dark:text-white">{row.ticker}</div>
                      <div className="text-[10px] text-slate-600 dark:text-slate-400">{row.name}</div>
                    </td>
                    <td className="p-3 text-right font-mono font-bold text-slate-900 dark:text-white">
                      {row.weight_pct.toFixed(1)}%
                    </td>
                    <td className="p-3 text-right font-mono font-semibold text-slate-700 dark:text-slate-300">
                      β = {row.asset_beta_to_portfolio.toFixed(2)}
                    </td>
                    <td className="p-3 text-right font-mono font-bold">
                      <span
                        className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs ${
                          row.tail_risk_contribution_pct >= 35.0
                            ? "bg-rose-500/15 text-rose-700 dark:text-rose-400"
                            : row.tail_risk_contribution_pct >= 20.0
                            ? "bg-amber-500/15 text-amber-700 dark:text-amber-400"
                            : "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300"
                        }`}
                      >
                        {row.tail_risk_contribution_pct.toFixed(1)}%
                      </span>
                    </td>
                    <td className="p-3 text-right font-mono font-bold text-rose-600 dark:text-rose-400">
                      {formatEur(row.loss_contribution_eur)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Footer Info Box */}
      <div className="mt-6 flex items-center gap-3 rounded-xl border border-black/8 bg-white/70 p-3.5 text-xs text-slate-700 dark:border-white/10 dark:bg-slate-800/60 dark:text-slate-300">
        <Info size={16} className="shrink-0 text-rose-600 dark:text-rose-400" />
        <p className="text-[11px] leading-relaxed">
          <strong className="text-slate-900 dark:text-white">Regulatorischer Kontext:</strong> Die
          europäische Bankenaufsicht (EBA) und Solvency II schreiben für das Risikokapital die
          Berechnung auf Basis von <em>Expected Shortfall (CVaR 99%)</em> über einen 10-Tages-Horizont
          vor, da herkömmliche Standardabweichungen die Häufigkeit extremer Marktverwerfungen drastisch
          unterschätzen.
        </p>
      </div>
    </div>
  );
}
