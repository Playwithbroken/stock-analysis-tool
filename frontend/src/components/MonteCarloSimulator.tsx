import React, { useEffect, useState, useMemo } from "react";
import {
  AreaChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from "recharts";
import {
  TrendingUp,
  ShieldCheck,
  RefreshCw,
  Sliders,
  Target,
  AlertTriangle,
  Flame,
  Clock,
  ArrowDownRight,
  Info,
  Layers,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { useCurrency } from "../context/CurrencyContext";
import MeasuredChartFrame from "./MeasuredChartFrame";

interface TrajectoryEntry {
  year: number;
  nominal: {
    p10: number;
    p25: number;
    p50: number;
    p75: number;
    p90: number;
    mean: number;
  };
  real: {
    p10: number;
    p25: number;
    p50: number;
    p75: number;
    p90: number;
    mean: number;
  };
  survival_rate: number;
}

interface MonteCarloResponse {
  portfolio_id?: string;
  portfolio_name?: string;
  parameters: {
    initial_wealth: number;
    annual_return: number;
    annual_volatility: number;
    monthly_savings: number;
    monthly_withdrawal: number;
    horizon_years: number;
    inflation_rate: number;
    target_wealth: number;
    num_simulations: number;
    withdrawal_inflation_adjusted: boolean;
  };
  summary: {
    median_final_wealth: number;
    real_median_final_wealth: number;
    p10_final_wealth: number;
    p25_final_wealth: number;
    p75_final_wealth: number;
    p90_final_wealth: number;
    target_probability: number;
    target_ever_reached_probability: number;
    ruin_probability: number;
    survival_probability: number;
    total_contributions: number;
    total_withdrawals: number;
    median_net_profit: number;
    safe_withdrawal_rate_pct: number;
    safe_monthly_withdrawal: number;
  };
  annual_trajectories: TrajectoryEntry[];
  stress_tests: {
    early_crash_final_wealth: number;
    deterministic_linear_wealth: number;
    sorr_risk_delta: number;
  };
  inferred_profile?: {
    expected_return: number;
    volatility: number;
    total_value: number;
  };
}

interface Props {
  portfolioId?: string;
  initialCapital?: number;
  onClose?: () => void;
}

export default function MonteCarloSimulator({
  portfolioId,
  initialCapital,
  onClose,
}: Props) {
  const { currency } = useCurrency();

  // Simulation Parameters
  const [horizonYears, setHorizonYears] = useState<number>(20);
  const [monthlySavings, setMonthlySavings] = useState<number>(500);
  const [monthlyWithdrawal, setMonthlyWithdrawal] = useState<number>(0);
  const [targetWealth, setTargetWealth] = useState<number>(1000000);
  const [inflationRate, setInflationRate] = useState<number>(0.02);
  const [expectedReturn, setExpectedReturn] = useState<number>(0.08);
  const [volatility, setVolatility] = useState<number>(0.16);
  const [numSimulations, setNumSimulations] = useState<number>(2000);
  const [isRealMode, setIsRealMode] = useState<boolean>(false); // Real (inflation-adjusted) vs Nominal
  const [showTable, setShowTable] = useState<boolean>(false);

  // State
  const [data, setData] = useState<MonteCarloResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSimulation = async () => {
    setLoading(true);
    setError(null);
    try {
      let res;
      if (portfolioId) {
        res = await fetch(`/api/portfolio/${portfolioId}/monte-carlo`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            horizon_years: horizonYears,
            monthly_savings: monthlySavings,
            monthly_withdrawal: monthlyWithdrawal,
            target_wealth: targetWealth,
            inflation_rate: inflationRate,
            annual_return: expectedReturn,
            annual_volatility: volatility,
            num_simulations: numSimulations,
          }),
        });
      } else {
        res = await fetch("/api/monte-carlo/simulate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            initial_wealth: initialCapital ?? 50000,
            horizon_years: horizonYears,
            monthly_savings: monthlySavings,
            monthly_withdrawal: monthlyWithdrawal,
            target_wealth: targetWealth,
            inflation_rate: inflationRate,
            annual_return: expectedReturn,
            annual_volatility: volatility,
            num_simulations: numSimulations,
          }),
        });
      }

      if (!res.ok) {
        throw new Error(`Fehler bei der Monte-Carlo-Simulation (${res.status})`);
      }
      const json: MonteCarloResponse = await res.json();
      setData(json);

      // If inferred profile returned, sync return and vol
      if (json.inferred_profile && expectedReturn === 0.08) {
        setExpectedReturn(json.inferred_profile.expected_return);
        setVolatility(json.inferred_profile.volatility);
      }
    } catch (err: any) {
      setError(err?.message || "Simulation fehlgeschlagen");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSimulation();
  }, [portfolioId]);

  const formatMoney = (val: number) => {
    const symbol = currency === "USD" ? "$" : "€";
    if (val >= 1000000) {
      return `${(val / 1000000).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} Mio. ${symbol}`;
    }
    return `${val.toLocaleString("de-DE", { maximumFractionDigits: 0 })} ${symbol}`;
  };

  // Prepare chart data: transform percentiles into stacked ribbon areas
  // Area 1: 0 to P10 (transparent base)
  // Area 2: P10 to P25
  // Area 3: P25 to P50
  // Area 4: P50 to P75
  // Area 5: P75 to P90
  const chartData = useMemo(() => {
    if (!data?.annual_trajectories) return [];
    return data.annual_trajectories.map((entry) => {
      const p = isRealMode ? entry.real : entry.nominal;
      return {
        year: `J. ${entry.year}`,
        rawYear: entry.year,
        p10: p.p10,
        p25: p.p25,
        p50: p.p50,
        p75: p.p75,
        p90: p.p90,
        mean: p.mean,
        target: targetWealth,
        // Relative band heights for smooth AreaChart shading
        band_p10_p25: Math.max(0, p.p25 - p.p10),
        band_p25_p50: Math.max(0, p.p50 - p.p25),
        band_p50_p75: Math.max(0, p.p75 - p.p50),
        band_p75_p90: Math.max(0, p.p90 - p.p75),
      };
    });
  }, [data, isRealMode, targetWealth]);

  return (
    <div className="surface-panel overflow-hidden rounded-[2.2rem] border border-black/8 bg-white/80 p-5 shadow-xl backdrop-blur-md dark:border-white/10 dark:bg-[#12141c]/90 sm:p-7">
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-black/6 pb-5 dark:border-white/8">
        <div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.2em] text-sky-500 dark:text-sky-400">
              <Layers size={13} className="text-sky-500" />
              10.000 Pfade Stochastik
            </span>
            <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-emerald-600 dark:text-emerald-400">
              FIRE / Ruhestand
            </span>
          </div>
          <h2 className="mt-2 text-2xl font-black tracking-tight text-slate-900 dark:text-white sm:text-3xl">
            Monte-Carlo-Vermögenssimulator
          </h2>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 sm:text-sm">
            Stochastische Vermögenspfade (Geometric Brownian Motion) mit Inflationsbereinigung,
            Sequence-of-Returns-Risiko und Ruin-Wahrscheinlichkeit.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Mode Switcher: Nominal vs Real */}
          <div className="inline-flex rounded-xl border border-black/8 bg-slate-100 p-1 dark:border-white/10 dark:bg-black/40">
            <button
              onClick={() => setIsRealMode(false)}
              className={`rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
                !isRealMode
                  ? "bg-white text-slate-900 shadow-sm dark:bg-white/15 dark:text-white"
                  : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-white"
              }`}
            >
              Nominal
            </button>
            <button
              onClick={() => setIsRealMode(true)}
              className={`rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
                isRealMode
                  ? "bg-white text-slate-900 shadow-sm dark:bg-white/15 dark:text-white"
                  : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-white"
              }`}
            >
              Realkaufkraft (-{Math.round(inflationRate * 100)}% Inflation)
            </button>
          </div>

          <button
            onClick={fetchSimulation}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-xl border border-black/10 bg-black/5 px-3 py-2 text-xs font-bold text-slate-700 hover:bg-black/10 dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:hover:bg-white/10"
          >
            <RefreshCw size={13} className={loading ? "animate-spin text-emerald-500" : ""} />
            Neu rechnen
          </button>

          {onClose && (
            <button
              onClick={onClose}
              className="rounded-xl border border-black/10 px-3 py-2 text-xs font-bold text-slate-600 hover:bg-black/5 dark:border-white/10 dark:text-slate-300 dark:hover:bg-white/10"
            >
              Schließen
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="mt-4 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3.5 text-xs font-semibold text-rose-300">
          {error}
        </div>
      )}

      {/* KPI Highlight Scorecards */}
      {data && (
        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {/* Target Wealth Probability */}
          <div className="rounded-2xl border border-black/6 bg-white/70 p-4 dark:border-white/8 dark:bg-white/[0.04]">
            <div className="flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
              <Target size={13} className="text-emerald-500" />
              Zielerreichung
            </div>
            <div className="mt-2 text-2xl font-black text-slate-900 dark:text-white">
              {data.summary.target_probability} %
            </div>
            <div className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
              Ziel: {formatMoney(targetWealth)}
            </div>
          </div>

          {/* Median Final Wealth */}
          <div className="rounded-2xl border border-black/6 bg-white/70 p-4 dark:border-white/8 dark:bg-white/[0.04]">
            <div className="flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
              <TrendingUp size={13} className="text-sky-500" />
              Median ({isRealMode ? "Real" : "Nominal"})
            </div>
            <div className="mt-2 text-xl font-black text-sky-600 dark:text-sky-400">
              {formatMoney(isRealMode ? data.summary.real_median_final_wealth : data.summary.median_final_wealth)}
            </div>
            <div className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
              50. Perzentil nach {horizonYears} J.
            </div>
          </div>

          {/* Bear Case P10 */}
          <div className="rounded-2xl border border-black/6 bg-white/70 p-4 dark:border-white/8 dark:bg-white/[0.04]">
            <div className="flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
              <ArrowDownRight size={13} className="text-amber-500" />
              Bärenmarkt (P10)
            </div>
            <div className="mt-2 text-xl font-black text-amber-600 dark:text-amber-400">
              {formatMoney(data.summary.p10_final_wealth)}
            </div>
            <div className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
              90% Wahrscheinlichkeit höher
            </div>
          </div>

          {/* Bull Case P90 */}
          <div className="rounded-2xl border border-black/6 bg-white/70 p-4 dark:border-white/8 dark:bg-white/[0.04]">
            <div className="flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
              <Flame size={13} className="text-purple-500" />
              Bullenmarkt (P90)
            </div>
            <div className="mt-2 text-xl font-black text-purple-600 dark:text-purple-400">
              {formatMoney(data.summary.p90_final_wealth)}
            </div>
            <div className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
              Top 10 % Renditepfade
            </div>
          </div>

          {/* Ruin Probability */}
          <div className="rounded-2xl border border-black/6 bg-white/70 p-4 dark:border-white/8 dark:bg-white/[0.04]">
            <div className="flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
              <AlertTriangle size={13} className={data.summary.ruin_probability > 5 ? "text-rose-500" : "text-emerald-500"} />
              Ruin-Wahrscheinlichkeit
            </div>
            <div className={`mt-2 text-2xl font-black ${data.summary.ruin_probability > 5 ? "text-rose-600 dark:text-rose-400" : "text-emerald-600 dark:text-emerald-400"}`}>
              {data.summary.ruin_probability} %
            </div>
            <div className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
              {data.summary.ruin_probability === 0 ? "Kein Ausfallrisiko" : "Kapitalerschöpfung"}
            </div>
          </div>

          {/* Safe Monthly Withdrawal (SWR) */}
          <div className="rounded-2xl border border-black/6 bg-white/70 p-4 dark:border-white/8 dark:bg-white/[0.04]">
            <div className="flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
              <ShieldCheck size={13} className="text-emerald-500" />
              Sichere Rente (SWR)
            </div>
            <div className="mt-2 text-xl font-black text-emerald-600 dark:text-emerald-400">
              {formatMoney(data.summary.safe_monthly_withdrawal)}/M
            </div>
            <div className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
              {data.summary.safe_withdrawal_rate_pct}% p.a. Entnahmerate
            </div>
          </div>
        </div>
      )}

      {/* Main Grid: Chart + Simulation Controls */}
      <div className="mt-6 grid gap-6 lg:grid-cols-[1.8fr_1fr]">
        {/* Fan Chart View */}
        <div className="rounded-2xl border border-black/6 bg-white/60 p-4 dark:border-white/8 dark:bg-white/[0.02]">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            <div className="text-xs font-extrabold uppercase tracking-wider text-slate-600 dark:text-slate-300">
              Konfidenzbänder (10. bis 90. Perzentil)
            </div>
            <div className="flex items-center gap-3 text-[11px]">
              <span className="flex items-center gap-1">
                <span className="h-2.5 w-2.5 rounded-full bg-sky-500" />
                <span className="text-slate-600 dark:text-slate-300 font-semibold">Median (P50)</span>
              </span>
              <span className="flex items-center gap-1">
                <span className="h-2.5 w-2.5 rounded-sm bg-sky-500/25" />
                <span className="text-slate-500 dark:text-slate-400">80% Spanne (P10–P90)</span>
              </span>
              <span className="flex items-center gap-1">
                <span className="h-0.5 w-3 bg-rose-500 border-dashed" />
                <span className="text-slate-500 dark:text-slate-400">Ziel</span>
              </span>
            </div>
          </div>

          <MeasuredChartFrame className="h-[340px] w-full" minHeight={340}>
            {({ w, h }) => (
              <AreaChart data={chartData} width={w} height={h} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                <defs>
                  <linearGradient id="mcGradWide" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#0ea5e9" stopOpacity={0.25} />
                    <stop offset="100%" stopColor="#0ea5e9" stopOpacity={0.05} />
                  </linearGradient>
                  <linearGradient id="mcGradCore" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#38bdf8" stopOpacity={0.15} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" opacity={0.15} vertical={false} />
                <XAxis
                  dataKey="year"
                  stroke="#94a3b8"
                  fontSize={11}
                  tickLine={false}
                  axisLine={{ stroke: "rgba(148, 163, 184, 0.2)" }}
                />
                <YAxis
                  stroke="#94a3b8"
                  fontSize={11}
                  tickLine={false}
                  axisLine={{ stroke: "rgba(148, 163, 184, 0.2)" }}
                  tickFormatter={(val) => {
                    if (val >= 1000000) return `${(val / 1000000).toFixed(1)}M`;
                    if (val >= 1000) return `${(val / 1000).toFixed(0)}k`;
                    return String(val);
                  }}
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload || !payload.length) return null;
                    const item: any = payload[0]?.payload;
                    if (!item) return null;
                    return (
                      <div className="rounded-xl border border-black/10 bg-white/95 p-3 text-xs shadow-xl backdrop-blur-md dark:border-white/10 dark:bg-slate-900/95 dark:text-white">
                        <div className="font-bold border-b border-black/8 pb-1 mb-2 dark:border-white/10">
                          {label} (Jahr {item.rawYear})
                        </div>
                        <div className="space-y-1">
                          <div className="flex justify-between gap-4 text-purple-600 dark:text-purple-400 font-semibold">
                            <span>Bullenmarkt (P90):</span>
                            <span>{formatMoney(item.p90)}</span>
                          </div>
                          <div className="flex justify-between gap-4 text-sky-500 font-bold">
                            <span>Median (P50):</span>
                            <span>{formatMoney(item.p50)}</span>
                          </div>
                          <div className="flex justify-between gap-4 text-amber-600 dark:text-amber-400 font-semibold">
                            <span>Bärenmarkt (P10):</span>
                            <span>{formatMoney(item.p10)}</span>
                          </div>
                          <div className="flex justify-between gap-4 text-slate-500 dark:text-slate-400 pt-1 border-t border-black/6 dark:border-white/6">
                            <span>Zielwert:</span>
                            <span>{formatMoney(item.target)}</span>
                          </div>
                        </div>
                      </div>
                    );
                  }}
                />
                {/* Confidence band P90 */}
                <Area type="monotone" dataKey="p90" stroke="none" fill="url(#mcGradWide)" />
                {/* Confidence band P75 */}
                <Area type="monotone" dataKey="p75" stroke="none" fill="url(#mcGradCore)" />
                {/* Target line */}
                <ReferenceLine y={targetWealth} stroke="#ef4444" strokeDasharray="5 5" strokeWidth={1.5} />
                {/* Median Line */}
                <Line
                  type="monotone"
                  dataKey="p50"
                  stroke="#0284c7"
                  strokeWidth={2.5}
                  dot={false}
                  activeDot={{ r: 5, fill: "#0284c7" }}
                />
                {/* Bear line P10 */}
                <Line
                  type="monotone"
                  dataKey="p10"
                  stroke="#f59e0b"
                  strokeWidth={1.5}
                  strokeDasharray="3 3"
                  dot={false}
                />
              </AreaChart>
            )}
          </MeasuredChartFrame>

          {/* Sequence of Returns Risk Insight Box */}
          {data?.stress_tests && (
            <div className="mt-4 rounded-xl border border-amber-500/20 bg-amber-500/[0.06] p-3.5 text-xs text-slate-700 dark:text-slate-300">
              <div className="flex items-center gap-2 font-bold text-amber-600 dark:text-amber-400">
                <Info size={14} />
                Sequence of Returns Risk (SORR-Stresstest):
              </div>
              <p className="mt-1 leading-relaxed">
                Ein Kursrutsch von -30 % direkt im ersten Jahr würde das Endvermögen von linear{" "}
                <span className="font-bold">{formatMoney(data.stress_tests.deterministic_linear_wealth)}</span> auf{" "}
                <span className="font-bold text-amber-600 dark:text-amber-400">{formatMoney(data.stress_tests.early_crash_final_wealth)}</span> reduzieren
                (Delta: {formatMoney(data.stress_tests.sorr_risk_delta)}). Dies verdeutlicht, warum eine Liquiditätsreserve vor Markteinbrüchen schützt.
              </p>
            </div>
          )}
        </div>

        {/* Interactive Simulation Controls */}
        <div className="space-y-4 rounded-2xl border border-black/6 bg-white/60 p-5 dark:border-white/8 dark:bg-white/[0.02]">
          <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider text-slate-600 dark:text-slate-300">
            <Sliders size={14} className="text-sky-500" />
            Parameter anpassen
          </div>

          {/* Horizon Years */}
          <div>
            <div className="flex justify-between text-xs font-semibold text-slate-700 dark:text-slate-300">
              <span>Anlagehorizont</span>
              <span className="font-bold text-sky-600 dark:text-sky-400">{horizonYears} Jahre</span>
            </div>
            <input
              type="range"
              min={1}
              max={40}
              step={1}
              value={horizonYears}
              onChange={(e) => setHorizonYears(Number(e.target.value))}
              className="mt-1.5 w-full accent-sky-500 cursor-pointer"
            />
          </div>

          {/* Monthly Savings */}
          <div>
            <div className="flex justify-between text-xs font-semibold text-slate-700 dark:text-slate-300">
              <span>Monatliche Sparrate</span>
              <span className="font-bold text-emerald-600 dark:text-emerald-400">{monthlySavings.toLocaleString("de-DE")} €/M</span>
            </div>
            <input
              type="range"
              min={0}
              max={5000}
              step={50}
              value={monthlySavings}
              onChange={(e) => setMonthlySavings(Number(e.target.value))}
              className="mt-1.5 w-full accent-emerald-500 cursor-pointer"
            />
          </div>

          {/* Monthly Withdrawal */}
          <div>
            <div className="flex justify-between text-xs font-semibold text-slate-700 dark:text-slate-300">
              <span>Monatliche Entnahme (Ruhestand)</span>
              <span className="font-bold text-rose-600 dark:text-rose-400">{monthlyWithdrawal.toLocaleString("de-DE")} €/M</span>
            </div>
            <input
              type="range"
              min={0}
              max={8000}
              step={100}
              value={monthlyWithdrawal}
              onChange={(e) => setMonthlyWithdrawal(Number(e.target.value))}
              className="mt-1.5 w-full accent-rose-500 cursor-pointer"
            />
          </div>

          {/* Target Wealth Input */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Zielvermögen
            </label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                step={50000}
                value={targetWealth}
                onChange={(e) => setTargetWealth(Number(e.target.value))}
                className="w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-xs font-bold text-slate-800 dark:border-white/10 dark:bg-black/30 dark:text-white"
              />
              <div className="flex gap-1 shrink-0">
                {[500000, 1000000, 2000000].map((quick) => (
                  <button
                    key={quick}
                    onClick={() => setTargetWealth(quick)}
                    className="rounded-lg border border-black/8 px-2 py-1 text-[10px] font-bold text-slate-600 hover:bg-black/5 dark:border-white/10 dark:text-slate-300 dark:hover:bg-white/10"
                  >
                    {quick / 1000000}M
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Advanced Accordion: Return, Volatility, Inflation */}
          <div className="pt-2 border-t border-black/6 dark:border-white/8 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Rendite p.a.
                </label>
                <input
                  type="number"
                  step={0.5}
                  value={Math.round(expectedReturn * 1000) / 10}
                  onChange={(e) => setExpectedReturn(Number(e.target.value) / 100)}
                  className="mt-1 w-full rounded-lg border border-black/10 bg-white px-2.5 py-1.5 text-xs font-bold dark:border-white/10 dark:bg-black/30 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Volatilität p.a.
                </label>
                <input
                  type="number"
                  step={0.5}
                  value={Math.round(volatility * 1000) / 10}
                  onChange={(e) => setVolatility(Number(e.target.value) / 100)}
                  className="mt-1 w-full rounded-lg border border-black/10 bg-white px-2.5 py-1.5 text-xs font-bold dark:border-white/10 dark:bg-black/30 dark:text-white"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Inflation p.a.
                </label>
                <input
                  type="number"
                  step={0.1}
                  value={Math.round(inflationRate * 1000) / 10}
                  onChange={(e) => setInflationRate(Number(e.target.value) / 100)}
                  className="mt-1 w-full rounded-lg border border-black/10 bg-white px-2.5 py-1.5 text-xs font-bold dark:border-white/10 dark:bg-black/30 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Simulationspfade
                </label>
                <select
                  value={numSimulations}
                  onChange={(e) => setNumSimulations(Number(e.target.value))}
                  className="mt-1 w-full rounded-lg border border-black/10 bg-white px-2.5 py-1.5 text-xs font-bold dark:border-white/10 dark:bg-black/30 dark:text-white"
                >
                  <option value={1000}>1.000 Pfade</option>
                  <option value={2000}>2.000 Pfade (Standard)</option>
                  <option value={5000}>5.000 Pfade</option>
                  <option value={10000}>10.000 Pfade (Max)</option>
                </select>
              </div>
            </div>
          </div>

          <button
            onClick={fetchSimulation}
            disabled={loading}
            className="w-full mt-3 rounded-xl bg-sky-500 py-3 text-xs font-extrabold uppercase tracking-wider text-white shadow-md transition-all hover:bg-sky-400 active:scale-[0.99] disabled:opacity-50"
          >
            {loading ? "Berechne 10.000 Pfade..." : "Simulation aktualisieren"}
          </button>
        </div>
      </div>

      {/* Trajectory Table Toggle */}
      <div className="mt-6 border-t border-black/6 pt-4 dark:border-white/8">
        <button
          onClick={() => setShowTable(!showTable)}
          className="flex items-center gap-2 text-xs font-bold text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
        >
          {showTable ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          {showTable ? "Perzentil-Jahrestabelle einklappen" : "Detaillierte Perzentil-Jahrestabelle anzeigen"}
        </button>

        {showTable && data?.annual_trajectories && (
          <div className="mt-4 overflow-x-auto rounded-xl border border-black/6 dark:border-white/8">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-black/6 bg-black/[0.02] text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:border-white/8 dark:bg-white/[0.02] dark:text-slate-400">
                <tr>
                  <th className="p-3">Jahr</th>
                  <th className="p-3 text-right">P10 (Bär)</th>
                  <th className="p-3 text-right">P25</th>
                  <th className="p-3 text-right text-sky-600 dark:text-sky-400 font-black">P50 (Median)</th>
                  <th className="p-3 text-right">P75</th>
                  <th className="p-3 text-right text-purple-600 dark:text-purple-400 font-bold">P90 (Bull)</th>
                  <th className="p-3 text-right">Überlebensrate</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/6 dark:divide-white/6 font-mono">
                {data.annual_trajectories
                  .filter((t) => t.year % 5 === 0 || t.year === horizonYears)
                  .map((t) => {
                    const p = isRealMode ? t.real : t.nominal;
                    return (
                      <tr key={t.year} className="hover:bg-black/[0.02] dark:hover:bg-white/[0.02]">
                        <td className="p-3 font-sans font-bold text-slate-800 dark:text-slate-200">Jahr {t.year}</td>
                        <td className="p-3 text-right text-amber-600 dark:text-amber-400">{formatMoney(p.p10)}</td>
                        <td className="p-3 text-right text-slate-600 dark:text-slate-300">{formatMoney(p.p25)}</td>
                        <td className="p-3 text-right font-black text-sky-600 dark:text-sky-400">{formatMoney(p.p50)}</td>
                        <td className="p-3 text-right text-slate-600 dark:text-slate-300">{formatMoney(p.p75)}</td>
                        <td className="p-3 text-right font-bold text-purple-600 dark:text-purple-400">{formatMoney(p.p90)}</td>
                        <td className="p-3 text-right font-sans font-semibold text-emerald-600 dark:text-emerald-400">{t.survival_rate} %</td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
