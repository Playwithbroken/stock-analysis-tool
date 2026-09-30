import React, { useEffect, useState } from "react";
import {
  Coins,
  Globe,
  TrendingDown,
  TrendingUp,
  AlertTriangle,
  RefreshCw,
  X,
  ShieldCheck,
  ShieldAlert,
  Percent,
  Sliders,
  DollarSign,
  Euro,
  ArrowRight,
  Layers,
  Info
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell
} from "recharts";
import MeasuredChartFrame from "./MeasuredChartFrame";

interface CurrencyBreakdownItem {
  currency: string;
  value_eur: number;
  weight_pct: number;
  spot_rate: number;
  forward_rate_1y: number;
  annual_volatility_pct: number;
  annual_cost_pct: number;
  annual_cost_eur: number;
  optimal_hedge_ratio_pct: number;
  recommended_hedge_eur: number;
  fx_var_95_1y_eur: number;
  fx_var_99_1y_eur: number;
  carry_status: string;
  interpretation: string;
}

interface MacroScenario {
  id: string;
  name: string;
  description: string;
  shock_pct: number;
  loss_eur: number;
  loss_pct: number;
}

interface HoldingFXItem {
  ticker: string;
  name: string;
  shares: number;
  price: number;
  value_eur: number;
  currency: string;
  annual_hedging_cost_pct: number;
  annual_hedging_cost_eur: number;
  optimal_hedge_ratio_pct: number;
  recommended_hedge_amount_eur: number;
}

interface FXAnalysisData {
  valid: boolean;
  error?: string;
  portfolio_value_eur: number;
  summary: {
    foreign_currency_pct: number;
    home_currency_pct: number;
    total_foreign_value_eur: number;
    portfolio_fx_volatility_pct: number;
    risk_badge: {
      label: string;
      tone: string;
    };
    total_recommended_hedge_eur: number;
    total_annual_hedging_cost_eur: number;
    total_annual_hedging_cost_pct: number;
  };
  fx_var: {
    var_95_1y_eur: number;
    var_95_1y_pct: number;
    var_99_1y_eur: number;
    var_99_1y_pct: number;
    var_95_1d_eur: number;
    var_99_1d_eur: number;
  };
  currency_breakdown: CurrencyBreakdownItem[];
  macro_scenarios: MacroScenario[];
  holdings: HoldingFXItem[];
}

interface CurrencyHedgingTerminalProps {
  portfolioId: string;
  onAnalyzeStock?: (ticker: string) => void;
  onClose?: () => void;
}

export default function CurrencyHedgingTerminal({
  portfolioId,
  onAnalyzeStock,
  onClose
}: CurrencyHedgingTerminalProps) {
  const [data, setData] = useState<FXAnalysisData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"exposure" | "holdings" | "stresstest">("exposure");

  // Interactive slider shocks for stresstest tab
  const [usdShock, setUsdShock] = useState<number>(0);
  const [chfShock, setChfShock] = useState<number>(0);
  const [gbpShock, setGbpShock] = useState<number>(0);

  const [simulatedDelta, setSimulatedDelta] = useState<{
    total_delta_eur: number;
    total_delta_pct: number;
  } | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/portfolio/${portfolioId}/currency-hedging`, {
        credentials: "same-origin"
      });
      if (!res.ok) {
        throw new Error(`HTTP Fehler ${res.status}: Währungsanalyse nicht abrufbar.`);
      }
      const json: FXAnalysisData = await res.json();
      if (!json.valid) {
        throw new Error(json.error || "Ungültige Währungsdaten erhalten.");
      }
      setData(json);
    } catch (err: any) {
      setError(err.message || "Unerwarteter Fehler bei der Währungsrisiko-Analyse.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (portfolioId) {
      fetchData();
    }
  }, [portfolioId]);

  // Dynamic simulation on slider movement
  useEffect(() => {
    if (!data) return;
    let deltaEur = 0;
    for (const b of data.currency_breakdown) {
      let shock = 0;
      if (b.currency === "USD") shock = usdShock;
      else if (b.currency === "CHF") shock = chfShock;
      else if (b.currency === "GBP") shock = gbpShock;
      deltaEur += b.value_eur * (shock / 100.0);
    }
    const deltaPct = data.portfolio_value_eur > 0 ? (deltaEur / data.portfolio_value_eur * 100.0) : 0;
    setSimulatedDelta({
      total_delta_eur: round(deltaEur, 2),
      total_delta_pct: round(deltaPct, 2)
    });
  }, [usdShock, chfShock, gbpShock, data]);

  const round = (val: number, decimals: number) => {
    const factor = Math.pow(10, decimals);
    return Math.round(val * factor) / factor;
  };

  const getCurrencyColor = (curr: string) => {
    switch (curr) {
      case "EUR": return "#059669"; // emerald-600
      case "USD": return "#0284c7"; // sky-600
      case "CHF": return "#d97706"; // amber-600
      case "GBP": return "#7c3aed"; // violet-600
      case "JPY": return "#e11d48"; // rose-600
      default: return "#64748b";    // slate-500
    }
  };

  return (
    <section className="mt-8 rounded-[2rem] border border-sky-500/20 bg-gradient-to-b from-sky-950/[0.04] to-transparent p-6 dark:border-sky-500/30 dark:bg-slate-900/60 shadow-xl backdrop-blur-md">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-black/10 pb-5 dark:border-white/10">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-sky-500/15 text-sky-700 dark:text-sky-400 border border-sky-500/30 shadow-inner">
            <Coins size={24} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-black tracking-tight text-slate-900 dark:text-white">
                Multi-Currency FX Exposure &amp; Currency Hedging Terminal
              </h2>
              <span className="rounded-md border border-sky-500/30 bg-sky-500/15 px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider text-sky-800 dark:text-sky-300">
                CIP Forward &amp; FX-VaR
              </span>
            </div>
            <p className="text-xs font-semibold text-slate-600 dark:text-slate-400">
              Look-Through Währungsallokation, Covered Interest Parity Terminkosten &amp; Minimum-Variance-Absicherung
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
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
          <RefreshCw size={36} className="animate-spin text-sky-600 dark:text-sky-400" />
          <p className="mt-4 text-sm font-bold text-slate-700 dark:text-slate-300">
            Analysiere Währungs-Exposure, Devisenterminkurse &amp; FX-VaR...
          </p>
        </div>
      )}

      {error && (
        <div className="my-6 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-5 text-rose-800 dark:text-rose-300">
          <div className="flex items-center gap-2 font-black">
            <AlertTriangle size={18} />
            Fehler bei der Währungsanalyse
          </div>
          <p className="mt-1 text-xs">{error}</p>
        </div>
      )}

      {!loading && !error && data && (
        <div className="mt-6 space-y-6">
          {/* 4 Scorecards */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {/* Card 1: Foreign Currency Exposure */}
            <div className="rounded-2xl border border-black/10 bg-white/90 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Fremdwährungs-Quote
                </span>
                <Globe size={16} className="text-sky-600 dark:text-sky-400" />
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-black text-slate-900 dark:text-white">
                  {data.summary.foreign_currency_pct.toFixed(1)}%
                </span>
                <span className="text-xs font-bold text-slate-600 dark:text-slate-400">
                  ({data.summary.total_foreign_value_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })})
                </span>
              </div>
              <div className="mt-2 flex items-center gap-2">
                <span className={`rounded-md border px-2 py-0.5 text-[10px] font-black uppercase ${data.summary.risk_badge.tone}`}>
                  {data.summary.risk_badge.label}
                </span>
                <span className="text-[11px] text-slate-500">Heimatwährung: {data.summary.home_currency_pct.toFixed(1)}% EUR</span>
              </div>
            </div>

            {/* Card 2: FX VaR (95% 1Y) */}
            <div className="rounded-2xl border border-black/10 bg-white/90 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  FX Value-at-Risk (1J, 95%)
                </span>
                <TrendingDown size={16} className="text-rose-600 dark:text-rose-400" />
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-black text-rose-700 dark:text-rose-400">
                  {data.fx_var.var_95_1y_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}
                </span>
                <span className="text-xs font-bold text-slate-600 dark:text-slate-400">
                  ({data.fx_var.var_95_1y_pct.toFixed(1)}%)
                </span>
              </div>
              <div className="mt-2 text-xs font-medium text-slate-500 dark:text-slate-400">
                1-Tag FX-VaR (99%): <span className="font-bold text-slate-800 dark:text-slate-200">{data.fx_var.var_99_1d_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}</span>
              </div>
            </div>

            {/* Card 3: Recommended Hedge Amount */}
            <div className="rounded-2xl border border-black/10 bg-white/90 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Optimale Absicherung
                </span>
                <ShieldCheck size={16} className="text-emerald-600 dark:text-emerald-400" />
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-black text-emerald-700 dark:text-emerald-400">
                  {data.summary.total_recommended_hedge_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}
                </span>
              </div>
              <div className="mt-2 text-xs font-medium text-slate-500 dark:text-slate-400">
                Minimum-Variance Hedge Ratio (MVHR)
              </div>
            </div>

            {/* Card 4: Forward Carry Cost */}
            <div className="rounded-2xl border border-black/10 bg-white/90 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Hedging Carry-Kosten
                </span>
                <Percent size={16} className="text-sky-600 dark:text-sky-400" />
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-black text-slate-900 dark:text-white">
                  {data.summary.total_annual_hedging_cost_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}
                </span>
                <span className="text-xs font-bold text-slate-500">
                  ({data.summary.total_annual_hedging_cost_pct.toFixed(2)}% p.a.)
                </span>
              </div>
              <div className="mt-2 text-xs font-medium text-slate-500 dark:text-slate-400">
                Basierend auf Zinsdifferenzen (CIP)
              </div>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="flex gap-2 border-b border-black/10 dark:border-white/10">
            <button
              onClick={() => setActiveTab("exposure")}
              className={`flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-black uppercase tracking-wider transition-all ${
                activeTab === "exposure"
                  ? "border-sky-500 text-sky-800 dark:text-sky-300"
                  : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              <Globe size={15} />
              Währungsallokation &amp; Zinsdifferenzen
            </button>

            <button
              onClick={() => setActiveTab("holdings")}
              className={`flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-black uppercase tracking-wider transition-all ${
                activeTab === "holdings"
                  ? "border-sky-500 text-sky-800 dark:text-sky-300"
                  : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              <Layers size={15} />
              Holdings FX-Attribution ({data.holdings.length})
            </button>

            <button
              onClick={() => setActiveTab("stresstest")}
              className={`flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-black uppercase tracking-wider transition-all ${
                activeTab === "stresstest"
                  ? "border-sky-500 text-sky-800 dark:text-sky-300"
                  : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              <Sliders size={15} />
              Interaktiver FX-Stresstest
            </button>
          </div>

          {/* TAB 1: Exposure & Central Bank Carry */}
          {activeTab === "exposure" && (
            <div className="grid gap-6 lg:grid-cols-12">
              {/* Exposure Chart */}
              <div className="lg:col-span-5">
                <div className="rounded-2xl border border-black/10 bg-white/80 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/80">
                  <h3 className="text-sm font-black text-slate-900 dark:text-white">
                    Netto-Währungsaufteilung
                  </h3>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                    Gewichtung der einzelnen Währungen im Portfolio
                  </p>

                  <MeasuredChartFrame className="mt-4 w-full" minHeight={220}>
                    <ResponsiveContainer width="100%" height={220}>
                      <BarChart data={data.currency_breakdown} margin={{ top: 20, right: 30, left: 0, bottom: 10 }}>
                        <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                        <XAxis dataKey="currency" tick={{ fontSize: 11, fontWeight: 700 }} />
                        <YAxis unit="%" tick={{ fontSize: 11 }} />
                        <Tooltip
                          formatter={(value: any, name: any, item: any) => [
                            `${Number(value).toFixed(1)}% (${item.payload.value_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })})`,
                            "Allokation"
                          ]}
                          contentStyle={{ backgroundColor: "#0f172a", borderRadius: "12px", border: "none", color: "#fff" }}
                        />
                        <Bar dataKey="weight_pct" radius={[8, 8, 0, 0]}>
                          {data.currency_breakdown.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={getCurrencyColor(entry.currency)} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </MeasuredChartFrame>

                  <div className="mt-3 rounded-xl border border-sky-500/20 bg-sky-500/5 p-3 text-xs text-sky-900 dark:text-sky-300">
                    <strong>Institutionelle Faustregel:</strong> Fremdwährungsanteile über 50% sollten ab einem Anlagehorizont unter 5 Jahren teilgesichert werden, um Drawdowns zu dämpfen.
                  </div>
                </div>
              </div>

              {/* Currency Rate Cards */}
              <div className="lg:col-span-7 space-y-3">
                {data.currency_breakdown.map((curr) => (
                  <div
                    key={curr.currency}
                    className="rounded-2xl border border-black/10 bg-white/90 p-4 shadow-sm dark:border-white/10 dark:bg-slate-800/90"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-black/5 pb-2 dark:border-white/5">
                      <div className="flex items-center gap-2">
                        <span
                          className="h-3 w-3 rounded-full"
                          style={{ backgroundColor: getCurrencyColor(curr.currency) }}
                        />
                        <span className="text-base font-black text-slate-900 dark:text-white">
                          {curr.currency}
                        </span>
                        <span className="text-xs font-bold text-slate-500">
                          {curr.weight_pct.toFixed(1)}% ({curr.value_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })})
                        </span>
                      </div>

                      <span className="text-xs font-bold text-slate-600 dark:text-slate-300">
                        Spot: <strong className="text-slate-900 dark:text-white">{curr.spot_rate}</strong> | 1J Forward: <strong className="text-slate-900 dark:text-white">{curr.forward_rate_1y}</strong>
                      </span>
                    </div>

                    <div className="mt-3 grid gap-3 sm:grid-cols-3 text-xs">
                      <div>
                        <div className="text-[10px] font-bold text-slate-500">Forward Carry Status</div>
                        <div className={`mt-0.5 font-black ${curr.annual_cost_pct > 0 ? "text-amber-700 dark:text-amber-400" : curr.annual_cost_pct < 0 ? "text-emerald-700 dark:text-emerald-400" : "text-slate-700 dark:text-slate-300"}`}>
                          {curr.carry_status}
                        </div>
                      </div>

                      <div>
                        <div className="text-[10px] font-bold text-slate-500">Hedging-Kosten p.a.</div>
                        <div className="mt-0.5 font-black text-slate-900 dark:text-white">
                          {curr.annual_cost_pct > 0 ? `+${curr.annual_cost_pct.toFixed(2)}%` : `${curr.annual_cost_pct.toFixed(2)}%`} ({curr.annual_cost_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })})
                        </div>
                      </div>

                      <div>
                        <div className="text-[10px] font-bold text-slate-500">Opt. Absicherungsquote (MVHR)</div>
                        <div className="mt-0.5 font-black text-sky-700 dark:text-sky-400">
                          {curr.optimal_hedge_ratio_pct.toFixed(0)}% ({curr.recommended_hedge_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })})
                        </div>
                      </div>
                    </div>

                    <div className="mt-2 text-[11px] text-slate-500 dark:text-slate-400 italic">
                      {curr.interpretation}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 2: Holdings Table */}
          {activeTab === "holdings" && (
            <div className="overflow-x-auto rounded-2xl border border-black/10 bg-white/90 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-black/10 bg-slate-100/75 dark:border-white/10 dark:bg-slate-700/50 text-[10px] font-black uppercase tracking-wider text-slate-500 dark:text-slate-400">
                    <th className="p-3.5">Asset</th>
                    <th className="p-3.5">Währung</th>
                    <th className="p-3.5 text-right">Positionswert</th>
                    <th className="p-3.5 text-right">1J Hedging-Kosten %</th>
                    <th className="p-3.5 text-right">Kosten (€ / Jahr)</th>
                    <th className="p-3.5 text-right">Empf. Quote (MVHR)</th>
                    <th className="p-3.5 text-right">Absicherung (€)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/5 dark:divide-white/5 font-semibold text-slate-800 dark:text-slate-200">
                  {data.holdings.map((h) => (
                    <tr key={h.ticker} className="hover:bg-sky-500/5 transition-colors">
                      <td className="p-3.5">
                        <button
                          onClick={() => onAnalyzeStock && onAnalyzeStock(h.ticker)}
                          className="font-black text-sky-700 hover:underline dark:text-sky-400 text-left"
                        >
                          {h.ticker}
                        </button>
                        <div className="text-[11px] text-slate-500 truncate max-w-[150px]">{h.name}</div>
                      </td>
                      <td className="p-3.5">
                        <span className="rounded-md border border-black/10 px-2 py-0.5 font-bold text-slate-800 dark:border-white/10 dark:text-white" style={{ borderColor: getCurrencyColor(h.currency) }}>
                          {h.currency}
                        </span>
                      </td>
                      <td className="p-3.5 text-right font-bold">
                        {h.value_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}
                      </td>
                      <td className="p-3.5 text-right font-mono">
                        {h.annual_hedging_cost_pct > 0 ? `+${h.annual_hedging_cost_pct.toFixed(2)}%` : `${h.annual_hedging_cost_pct.toFixed(2)}%`}
                      </td>
                      <td className="p-3.5 text-right font-mono">
                        {h.annual_hedging_cost_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}
                      </td>
                      <td className="p-3.5 text-right font-black text-sky-700 dark:text-sky-400">
                        {h.optimal_hedge_ratio_pct.toFixed(0)}%
                      </td>
                      <td className="p-3.5 text-right font-black">
                        {h.recommended_hedge_amount_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* TAB 3: Interactive FX Stress Test */}
          {activeTab === "stresstest" && (
            <div className="space-y-6">
              {/* Preset Macro Scenarios */}
              <div className="rounded-2xl border border-black/10 bg-white/80 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/80">
                <h3 className="text-sm font-black text-slate-900 dark:text-white">
                  Historische &amp; Geopolitische FX-Szenarien
                </h3>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  Erwartete Wertveränderung des Portfolios in Euro bei extremen Devisenmarktbewegungen
                </p>

                <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  {data.macro_scenarios.map((scen) => (
                    <div
                      key={scen.id}
                      className="rounded-xl border border-black/10 bg-white/90 p-4 dark:border-white/10 dark:bg-slate-800"
                    >
                      <div className="text-xs font-black text-slate-900 dark:text-white">{scen.name}</div>
                      <div className="mt-1 text-[11px] text-slate-500">{scen.description}</div>
                      <div className={`mt-3 text-lg font-black ${scen.loss_eur >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"}`}>
                        {scen.loss_eur >= 0 ? `+${scen.loss_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}` : scen.loss_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}
                      </div>
                      <div className={`text-xs font-bold ${scen.loss_pct >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"}`}>
                        {scen.loss_pct >= 0 ? `+${scen.loss_pct.toFixed(2)}%` : `${scen.loss_pct.toFixed(2)}%`}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Interactive Sliders */}
              <div className="rounded-2xl border border-black/10 bg-white/80 p-6 shadow-sm dark:border-white/10 dark:bg-slate-800/80">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <h3 className="text-base font-black text-slate-900 dark:text-white flex items-center gap-2">
                      <Sliders size={18} className="text-sky-600 dark:text-sky-400" />
                      Echtzeit Währungsschock-Simulator
                    </h3>
                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                      Verschiebe die Wechselkursänderungen und beobachte die unmittelbare Auswirkung auf das Gesamtportfolio in Euro.
                    </p>
                  </div>

                  {simulatedDelta && (
                    <div className="rounded-xl border border-black/10 bg-white p-3.5 text-right dark:border-white/10 dark:bg-slate-900 shadow-sm">
                      <div className="text-[10px] font-bold text-slate-500">Simulierter Portfolio-Effekt</div>
                      <div className={`text-xl font-black ${simulatedDelta.total_delta_eur >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"}`}>
                        {simulatedDelta.total_delta_eur >= 0 ? `+${simulatedDelta.total_delta_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}` : simulatedDelta.total_delta_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}
                      </div>
                      <div className={`text-xs font-bold ${simulatedDelta.total_delta_pct >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"}`}>
                        {simulatedDelta.total_delta_pct >= 0 ? `+${simulatedDelta.total_delta_pct.toFixed(2)}%` : `${simulatedDelta.total_delta_pct.toFixed(2)}%`}
                      </div>
                    </div>
                  )}
                </div>

                <div className="mt-6 grid gap-6 md:grid-cols-3">
                  {/* Slider USD */}
                  <div className="rounded-xl border border-black/10 bg-white/50 p-4 dark:border-white/10 dark:bg-slate-900/50">
                    <div className="flex justify-between items-center text-xs font-black">
                      <span className="text-sky-700 dark:text-sky-400">US-Dollar (USD)</span>
                      <span className={usdShock >= 0 ? "text-emerald-600" : "text-rose-600"}>
                        {usdShock >= 0 ? `+${usdShock}%` : `${usdShock}%`}
                      </span>
                    </div>
                    <input
                      type="range"
                      min="-20"
                      max="20"
                      step="1"
                      value={usdShock}
                      onChange={(e) => setUsdShock(parseInt(e.target.value))}
                      className="mt-3 w-full cursor-pointer accent-sky-600"
                    />
                    <div className="mt-1 flex justify-between text-[10px] text-slate-400">
                      <span>-20% (EUR-Rallye)</span>
                      <span>0%</span>
                      <span>+20% (USD-Rallye)</span>
                    </div>
                  </div>

                  {/* Slider CHF */}
                  <div className="rounded-xl border border-black/10 bg-white/50 p-4 dark:border-white/10 dark:bg-slate-900/50">
                    <div className="flex justify-between items-center text-xs font-black">
                      <span className="text-amber-700 dark:text-amber-400">Schweizer Franken (CHF)</span>
                      <span className={chfShock >= 0 ? "text-emerald-600" : "text-rose-600"}>
                        {chfShock >= 0 ? `+${chfShock}%` : `${chfShock}%`}
                      </span>
                    </div>
                    <input
                      type="range"
                      min="-20"
                      max="20"
                      step="1"
                      value={chfShock}
                      onChange={(e) => setChfShock(parseInt(e.target.value))}
                      className="mt-3 w-full cursor-pointer accent-amber-600"
                    />
                    <div className="mt-1 flex justify-between text-[10px] text-slate-400">
                      <span>-20%</span>
                      <span>0%</span>
                      <span>+20%</span>
                    </div>
                  </div>

                  {/* Slider GBP */}
                  <div className="rounded-xl border border-black/10 bg-white/50 p-4 dark:border-white/10 dark:bg-slate-900/50">
                    <div className="flex justify-between items-center text-xs font-black">
                      <span className="text-violet-700 dark:text-violet-400">Britisches Pfund (GBP)</span>
                      <span className={gbpShock >= 0 ? "text-emerald-600" : "text-rose-600"}>
                        {gbpShock >= 0 ? `+${gbpShock}%` : `${gbpShock}%`}
                      </span>
                    </div>
                    <input
                      type="range"
                      min="-20"
                      max="20"
                      step="1"
                      value={gbpShock}
                      onChange={(e) => setGbpShock(parseInt(e.target.value))}
                      className="mt-3 w-full cursor-pointer accent-violet-600"
                    />
                    <div className="mt-1 flex justify-between text-[10px] text-slate-400">
                      <span>-20%</span>
                      <span>0%</span>
                      <span>+20%</span>
                    </div>
                  </div>
                </div>

                <div className="mt-4 flex justify-end">
                  <button
                    onClick={() => {
                      setUsdShock(0);
                      setChfShock(0);
                      setGbpShock(0);
                    }}
                    className="text-xs font-bold text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 underline"
                  >
                    Schieberegler auf 0% zurücksetzen
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
