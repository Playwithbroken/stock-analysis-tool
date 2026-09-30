import React, { useEffect, useState } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";
import {
  Sparkles,
  TrendingUp,
  Coins,
  ShieldCheck,
  RefreshCw,
  Sliders,
  CheckCircle2,
  Lock,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { useCurrency } from "../context/CurrencyContext";
import MeasuredChartFrame from "./MeasuredChartFrame";

interface ForecastTimelineEntry {
  year: number;
  portfolio_value: number;
  total_contributed: number;
  gross_dividend_yearly: number;
  net_dividend_yearly: number;
  net_dividend_monthly: number;
  taxes_paid: number;
  tax_saved: number;
  tax_free_allowance_used: number;
  reinvested_amount: number;
}

interface Milestone {
  id: string;
  title: string;
  icon: string;
  target_monthly: number;
  current_monthly_net: number;
  current_coverage_pct: number;
  forecast_monthly_net: number;
  forecast_coverage_pct: number;
  is_reached_now: boolean;
  is_reached_forecast: boolean;
  required_portfolio_value: number;
}

interface ForecastResponse {
  portfolio_id: string;
  portfolio_name: string;
  parameters: {
    years: number;
    monthly_contribution: number;
    reinvest_dividends: boolean;
    dividend_growth_rate: number;
    capital_growth_rate: number;
    tax_allowance: number;
  };
  initial_status: {
    initial_value: number;
    initial_annual_gross_dividend: number;
    initial_dividend_yield_pct: number;
    current_monthly_net: number;
    allowance_used_pct: number;
    allowance_remaining: number;
    taxes_paid_now: number;
  };
  timeline: ForecastTimelineEntry[];
  summary: {
    end_portfolio_value: number;
    end_annual_gross_dividend: number;
    end_annual_net_dividend: number;
    end_monthly_net_dividend: number;
    total_contributed: number;
    total_dividends_earned: number;
    total_taxes_paid: number;
    total_taxes_saved: number;
  };
  milestones: Milestone[];
  message?: string;
}

interface DividendForecastSimulatorProps {
  portfolioId: string;
  portfolioName?: string;
}

export default function DividendForecastSimulator({
  portfolioId,
  portfolioName = "Mein Portfolio",
}: DividendForecastSimulatorProps) {
  const { formatPrice } = useCurrency();

  // Control state
  const [years, setYears] = useState<number>(15);
  const [monthlyContribution, setMonthlyContribution] = useState<number>(250);
  const [reinvest, setReinvest] = useState<boolean>(true);
  const [taxAllowance, setTaxAllowance] = useState<number>(1000);
  const [divGrowthRate, setDivGrowthRate] = useState<number>(5.0);
  const [capGrowthRate, setCapGrowthRate] = useState<number>(4.0);
  const [showAdvanced, setShowAdvanced] = useState<boolean>(false);

  const [data, setData] = useState<ForecastResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchForecast = async () => {
    if (!portfolioId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/portfolio/${portfolioId}/dividend-forecast`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          years,
          monthly_contribution: monthlyContribution,
          reinvest_dividends: reinvest,
          dividend_growth_rate: divGrowthRate,
          capital_growth_rate: capGrowthRate,
          tax_allowance: taxAllowance,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: ForecastResponse = await res.json();
      setData(json);
    } catch (err: any) {
      setError(err?.message || "Fehler bei der Berechnung der Dividenden-Projektion.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchForecast();
  }, [portfolioId, years, monthlyContribution, reinvest, taxAllowance, divGrowthRate, capGrowthRate]);

  const summary = data?.summary;
  const initial = data?.initial_status;

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const entry = payload[0]?.payload as ForecastTimelineEntry;
      return (
        <div className="rounded-xl border border-black/10 bg-white/95 p-3.5 shadow-xl backdrop-blur-md dark:border-white/10 dark:bg-slate-900/95">
          <div className="mb-2 text-xs font-black uppercase tracking-wider text-slate-500">
            Jahr {entry.year} (in {entry.year} Jahren)
          </div>
          <div className="space-y-1 text-xs">
            <div className="flex justify-between gap-4 font-bold text-teal-600 dark:text-teal-400">
              <span>Portfoliowert:</span>
              <span>{formatPrice(entry.portfolio_value)}</span>
            </div>
            <div className="flex justify-between gap-4 text-slate-500 dark:text-slate-400">
              <span>Eingezahltes Eigenkapital:</span>
              <span>{formatPrice(entry.total_contributed)}</span>
            </div>
            <div className="border-t border-slate-200 dark:border-slate-800 pt-1 mt-1">
              <div className="flex justify-between gap-4 font-extrabold text-indigo-600 dark:text-indigo-400">
                <span>Netto-Dividende / Monat:</span>
                <span>{formatPrice(entry.net_dividend_monthly)}/Mo</span>
              </div>
              <div className="flex justify-between gap-4 text-slate-500">
                <span>Netto-Dividende / Jahr:</span>
                <span>{formatPrice(entry.net_dividend_yearly)}</span>
              </div>
              <div className="flex justify-between gap-4 text-[11px] text-rose-500">
                <span>Gezahlte Steuern im Jahr:</span>
                <span>{formatPrice(entry.taxes_paid)}</span>
              </div>
            </div>
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <section className="surface-panel rounded-[2rem] p-6 lg:p-7 space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-teal-600 dark:text-teal-400">
            <Coins className="h-4 w-4" />
            <span className="text-xs font-extrabold uppercase tracking-[0.2em]">
              Dividenden-Schneeball & Sparerpauschbetrag
            </span>
          </div>
          <h3 className="mt-1 text-xl font-extrabold tracking-tight text-slate-900 dark:text-white">
            Zukunftsprojektion & Passives Einkommen
          </h3>
        </div>

        <button
          onClick={fetchForecast}
          disabled={loading}
          className="flex items-center gap-2 self-start rounded-xl border border-black/8 bg-black/[0.03] px-3.5 py-2 text-xs font-bold text-slate-700 transition hover:bg-black/[0.06] dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:hover:bg-white/10 lg:self-auto"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin text-teal-600" : ""}`} />
          Aktualisieren
        </button>
      </div>

      {/* Interactive Controls Bar */}
      <div className="rounded-2xl border border-black/8 bg-black/[0.02] p-5 dark:border-white/10 dark:bg-white/5 space-y-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {/* Zeithorizont */}
          <div>
            <label className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Anlagehorizont: {years} Jahre
            </label>
            <div className="mt-2 flex items-center gap-1.5">
              {[5, 10, 15, 20, 30].map((y) => (
                <button
                  key={y}
                  onClick={() => setYears(y)}
                  className={`rounded-lg px-2.5 py-1 text-xs font-bold transition ${
                    years === y
                      ? "bg-[var(--accent)] text-white shadow-sm"
                      : "bg-black/[0.04] text-slate-600 hover:bg-black/[0.08] dark:bg-white/10 dark:text-slate-300"
                  }`}
                >
                  {y}J
                </button>
              ))}
            </div>
          </div>

          {/* Sparrate */}
          <div>
            <label className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Monatliche Sparrate: {monthlyContribution} €
            </label>
            <div className="mt-2 flex items-center gap-1.5">
              {[0, 150, 250, 500, 1000].map((amt) => (
                <button
                  key={amt}
                  onClick={() => setMonthlyContribution(amt)}
                  className={`rounded-lg px-2 py-1 text-xs font-bold transition ${
                    monthlyContribution === amt
                      ? "bg-indigo-600 text-white shadow-sm"
                      : "bg-black/[0.04] text-slate-600 hover:bg-black/[0.08] dark:bg-white/10 dark:text-slate-300"
                  }`}
                >
                  {amt}€
                </button>
              ))}
            </div>
          </div>

          {/* DRIP Reinvest Toggle */}
          <div>
            <label className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Wiederanlage (DRIP)
            </label>
            <div className="mt-2 flex items-center">
              <button
                onClick={() => setReinvest(!reinvest)}
                className={`flex items-center gap-2 rounded-xl px-3.5 py-1.5 text-xs font-bold transition ${
                  reinvest
                    ? "bg-emerald-600 text-white shadow-sm shadow-emerald-500/20"
                    : "bg-black/[0.05] text-slate-600 dark:bg-white/10 dark:text-slate-400"
                }`}
              >
                <Sparkles className="h-3.5 w-3.5" />
                {reinvest ? "DRIP Aktiv (Schneeball)" : "Auszahlung (Kein Zinseszins)"}
              </button>
            </div>
          </div>

          {/* Sparerpauschbetrag Switcher */}
          <div>
            <label className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Sparerpauschbetrag
            </label>
            <div className="mt-2 flex items-center gap-1.5">
              <button
                onClick={() => setTaxAllowance(1000)}
                className={`rounded-lg px-2.5 py-1 text-xs font-bold transition ${
                  taxAllowance === 1000
                    ? "bg-[var(--accent)] text-white shadow-sm"
                    : "bg-black/[0.04] text-slate-600 dark:bg-white/10 dark:text-slate-300"
                }`}
              >
                1.000 € (Single)
              </button>
              <button
                onClick={() => setTaxAllowance(2000)}
                className={`rounded-lg px-2.5 py-1 text-xs font-bold transition ${
                  taxAllowance === 2000
                    ? "bg-[var(--accent)] text-white shadow-sm"
                    : "bg-black/[0.04] text-slate-600 dark:bg-white/10 dark:text-slate-300"
                }`}
              >
                2.000 € (Ehepaar)
              </button>
            </div>
          </div>
        </div>

        {/* Advanced Accordion Toggle */}
        <div>
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-1.5 text-xs font-bold text-slate-500 hover:text-slate-800 dark:hover:text-white"
          >
            <Sliders className="h-3.5 w-3.5" />
            Erweiterte Wachstumsannahmen
            {showAdvanced ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>

          {showAdvanced && (
            <div className="mt-3 grid gap-4 sm:grid-cols-2 pt-3 border-t border-black/6 dark:border-white/8">
              <div>
                <label className="text-xs text-slate-600 dark:text-slate-400 font-medium">
                  Jährliches Dividendenwachstum: {divGrowthRate}% p.a.
                </label>
                <input
                  type="range"
                  min="0"
                  max="12"
                  step="0.5"
                  value={divGrowthRate}
                  onChange={(e) => setDivGrowthRate(Number(e.target.value))}
                  className="w-full mt-1 accent-teal-600"
                />
              </div>
              <div>
                <label className="text-xs text-slate-600 dark:text-slate-400 font-medium">
                  Jährliche Kursrendite (Kapitalwachstum): {capGrowthRate}% p.a.
                </label>
                <input
                  type="range"
                  min="0"
                  max="10"
                  step="0.5"
                  value={capGrowthRate}
                  onChange={(e) => setCapGrowthRate(Number(e.target.value))}
                  className="w-full mt-1 accent-indigo-600"
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* KPI Cards Grid */}
      {summary && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {/* End Portfolio Value */}
          <div className="rounded-2xl border border-black/8 bg-black/[0.02] p-4 dark:border-white/10 dark:bg-white/5">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-teal-600 dark:text-teal-400">
              Depotwert in {years}J
            </div>
            <div className="mt-1 text-xl font-black text-slate-900 dark:text-white">
              {formatPrice(summary.end_portfolio_value)}
            </div>
            <div className="mt-1 text-[11px] text-slate-500">
              Eingezahlt: {formatPrice(summary.total_contributed)}
            </div>
          </div>

          {/* Monthly Net Dividend */}
          <div className="rounded-2xl border border-teal-500/20 bg-teal-500/[0.05] p-4 dark:border-teal-500/30">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-teal-600 dark:text-teal-400">
              Monats-Netto in {years}J
            </div>
            <div className="mt-1 text-xl font-black text-teal-600 dark:text-teal-400">
              {formatPrice(summary.end_monthly_net_dividend)}/Mo
            </div>
            <div className="mt-1 text-[11px] text-teal-600/80 font-semibold">
              Passives Gehalt
            </div>
          </div>

          {/* Yearly Net Dividend */}
          <div className="rounded-2xl border border-black/8 bg-black/[0.02] p-4 dark:border-white/10 dark:bg-white/5">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Jahres-Netto in {years}J
            </div>
            <div className="mt-1 text-xl font-black text-slate-900 dark:text-white">
              {formatPrice(summary.end_annual_net_dividend)}/J
            </div>
            <div className="mt-1 text-[11px] text-slate-500">
              Brutto: {formatPrice(summary.end_annual_gross_dividend)}
            </div>
          </div>

          {/* Total Dividends Earned */}
          <div className="rounded-2xl border border-black/8 bg-black/[0.02] p-4 dark:border-white/10 dark:bg-white/5">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-indigo-600 dark:text-indigo-400">
              Dividenden gesamt
            </div>
            <div className="mt-1 text-xl font-black text-indigo-600 dark:text-indigo-400">
              {formatPrice(summary.total_dividends_earned)}
            </div>
            <div className="mt-1 text-[11px] text-slate-500">
              Über {years} Jahre generiert
            </div>
          </div>

          {/* Tax Savings by Allowance */}
          <div className="col-span-2 sm:col-span-1 rounded-2xl border border-emerald-500/20 bg-emerald-500/[0.05] p-4 dark:border-emerald-500/30">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
              Gesparte Steuern
            </div>
            <div className="mt-1 text-xl font-black text-emerald-600 dark:text-emerald-400">
              {formatPrice(summary.total_taxes_saved)}
            </div>
            <div className="mt-1 text-[11px] text-emerald-600/80 font-semibold">
              Durch Freibetrag
            </div>
          </div>
        </div>
      )}

      {/* Current Year Sparerpauschbetrag Tracker Banner */}
      {initial && (
        <div className="rounded-2xl border border-black/8 bg-black/[0.02] p-4.5 dark:border-white/10 dark:bg-white/5 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-emerald-500/15 p-2.5 text-emerald-600 dark:text-emerald-400">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <div className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Sparerpauschbetrag-Auslastung (Aktuelles Jahr)
              </div>
              <div className="text-sm font-extrabold text-slate-900 dark:text-white mt-0.5">
                {formatPrice(initial.initial_annual_gross_dividend)} von {formatPrice(taxAllowance)} genutzt ({initial.allowance_used_pct.toFixed(0)}%)
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4 w-full md:w-auto">
            <div className="flex-1 md:w-48 h-2.5 rounded-full bg-black/[0.08] dark:bg-white/10 overflow-hidden">
              <div
                className={`h-full rounded-full ${
                  initial.allowance_used_pct >= 100 ? "bg-amber-500" : "bg-emerald-500"
                }`}
                style={{ width: `${Math.min(100, initial.allowance_used_pct)}%` }}
              />
            </div>
            <div className="text-xs font-semibold text-slate-600 dark:text-slate-300 whitespace-nowrap">
              {initial.allowance_remaining > 0 ? (
                <span className="text-emerald-600 dark:text-emerald-400">
                  +{formatPrice(initial.allowance_remaining)} noch steuerfrei
                </span>
              ) : (
                <span className="text-amber-600 dark:text-amber-400">
                  Voll ausgeschöpft
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Snowball Chart */}
      <div className="relative">
        <MeasuredChartFrame
          className="h-[320px] w-full"
          minHeight={320}
          fallback={
            <div className="flex h-[320px] w-full flex-col items-center justify-center space-y-3 rounded-2xl border border-black/8 bg-black/[0.02]">
              <div className="h-9 w-9 animate-spin rounded-full border-3 border-teal-500/20 border-t-teal-500" />
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Berechne Zinseszins-Schneeball...
              </span>
            </div>
          }
        >
          {loading ? (
            <div className="flex h-[320px] w-full flex-col items-center justify-center space-y-3 rounded-2xl border border-black/8 bg-black/[0.02]">
              <div className="h-9 w-9 animate-spin rounded-full border-3 border-teal-500/20 border-t-teal-500" />
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Simuliere Dividenden-Schneeball...
              </span>
            </div>
          ) : error ? (
            <div className="flex h-[320px] w-full flex-col items-center justify-center space-y-2 rounded-2xl border border-dashed border-rose-300 p-6 text-center">
              <p className="text-sm font-semibold text-rose-600">{error}</p>
            </div>
          ) : !data?.timeline || data.timeline.length === 0 ? (
            <div className="flex h-[320px] w-full flex-col items-center justify-center space-y-2 rounded-2xl border border-dashed border-black/10 p-6 text-center">
              <p className="text-sm text-slate-500">Keine Daten verfügbar.</p>
            </div>
          ) : (
            <AreaChart data={data.timeline} margin={{ top: 10, right: 15, left: -10, bottom: 0 }}>
              <defs>
                <linearGradient id="portfolioGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#0f766e" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#0f766e" stopOpacity={0.0} />
                </linearGradient>
                <linearGradient id="contributionsGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#64748b" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#64748b" stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" opacity={0.5} />
              <XAxis
                dataKey="year"
                tickFormatter={(val) => `J${val}`}
                tick={{ fontSize: 11, fill: "#64748b" }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                tickFormatter={(val) => `${(val / 1000).toFixed(0)}k€`}
                tick={{ fontSize: 11, fill: "#64748b" }}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend
                wrapperStyle={{ paddingTop: "12px" }}
                formatter={(val) => (
                  <span className="text-xs font-bold text-slate-700 dark:text-slate-300">
                    {val === "portfolio_value" ? "Gesamter Portfoliowert (inkl. Zinseszins)" : "Eingezahltes Eigenkapital"}
                  </span>
                )}
              />
              <Area
                type="monotone"
                dataKey="portfolio_value"
                name="portfolio_value"
                stroke="#0f766e"
                strokeWidth={2.5}
                fillOpacity={1}
                fill="url(#portfolioGrad)"
              />
              <Area
                type="monotone"
                dataKey="total_contributed"
                name="total_contributed"
                stroke="#64748b"
                strokeWidth={1.5}
                strokeDasharray="4 4"
                fillOpacity={1}
                fill="url(#contributionsGrad)"
              />
            </AreaChart>
          )}
        </MeasuredChartFrame>
      </div>

      {/* Living Cost Milestones (Freiheits-Barometer) */}
      {data && data.milestones.length > 0 && (
        <div className="space-y-3 pt-2">
          <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            <Sparkles className="h-4 w-4 text-amber-500" />
            Freiheits-Barometer: Welche Fixkosten zahlt dein Depot passiv?
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.milestones.map((m) => {
              const isReached = m.is_reached_now;
              const willReach = m.is_reached_forecast;
              return (
                <div
                  key={m.id}
                  className={`rounded-2xl border p-4.5 transition-all ${
                    isReached
                      ? "border-emerald-500/30 bg-emerald-500/[0.04] dark:border-emerald-500/20 dark:bg-emerald-950/10"
                      : willReach
                      ? "border-indigo-500/30 bg-indigo-500/[0.03] dark:border-indigo-500/20 dark:bg-indigo-950/10"
                      : "border-black/8 bg-black/[0.02] dark:border-white/8 dark:bg-white/[0.03]"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-xl">{m.icon}</span>
                      <div>
                        <div className="font-extrabold text-xs text-slate-900 dark:text-white">
                          {m.title}
                        </div>
                        <div className="text-[11px] text-slate-500 font-mono">
                          {formatPrice(m.target_monthly)}/Monat
                        </div>
                      </div>
                    </div>
                    {isReached ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-[10px] font-extrabold text-emerald-700 dark:text-emerald-400">
                        <CheckCircle2 className="h-3 w-3" />
                        Aktiv gedeckt
                      </span>
                    ) : willReach ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-indigo-500/15 px-2.5 py-0.5 text-[10px] font-extrabold text-indigo-700 dark:text-indigo-400">
                        In {years}J erreicht
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-black/5 dark:bg-white/10 px-2.5 py-0.5 text-[10px] font-extrabold text-slate-500">
                        Im Aufbau
                      </span>
                    )}
                  </div>

                  {/* Progress Bar */}
                  <div className="mt-3">
                    <div className="flex justify-between text-[11px] font-semibold text-slate-500 mb-1">
                      <span>Heute: {m.current_coverage_pct.toFixed(0)}%</span>
                      <span>In {years}J: {m.forecast_coverage_pct.toFixed(0)}%</span>
                    </div>
                    <div className="h-2 rounded-full bg-black/[0.06] dark:bg-white/10 overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${
                          isReached ? "bg-emerald-500" : willReach ? "bg-indigo-500" : "bg-teal-500"
                        }`}
                        style={{ width: `${Math.min(100, isReached ? m.current_coverage_pct : m.forecast_coverage_pct)}%` }}
                      />
                    </div>
                  </div>

                  <div className="mt-2 text-[10px] text-slate-500">
                    Benötigtes Depotkapital: ~{formatPrice(m.required_portfolio_value)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
