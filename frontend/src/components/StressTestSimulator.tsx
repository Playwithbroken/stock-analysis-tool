import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  ShieldAlert,
  ShieldCheck,
  TrendingDown,
  Activity,
  Sliders,
  Flame,
  Zap,
  RefreshCw,
  Lightbulb,
  ArrowDownRight,
  ArrowUpRight,
  Lock,
} from "lucide-react";
import { useCurrency } from "../context/CurrencyContext";

interface SimulatedHolding {
  ticker: string;
  name: string;
  shares: number;
  current_price: number;
  current_value: number;
  simulated_value: number;
  loss_eur: number;
  shock_pct: number;
  sector: string;
  beta: number;
}

interface StressTestSummary {
  initial_value: number;
  simulated_value: number;
  loss_eur: number;
  loss_pct: number;
  risk_rating: string;
  weighted_beta: number;
}

interface StressTestResponse {
  portfolio_id: string;
  portfolio_name: string;
  scenario: string;
  scenario_name: string;
  scenario_description: string;
  summary: StressTestSummary;
  holdings: SimulatedHolding[];
  vulnerable_assets: SimulatedHolding[];
  resilient_assets: SimulatedHolding[];
  recommendations: string[];
}

interface StressTestSimulatorProps {
  portfolioId: string;
  portfolioName?: string;
}

const SCENARIOS = [
  {
    id: "financial_crisis_2008",
    title: "2008 Finanzkrise",
    subtitle: "Banken & Liquiditätsklemme",
    icon: ShieldAlert,
    color: "from-rose-500/20 to-red-600/10 border-rose-500/30",
  },
  {
    id: "covid_crash_2020",
    title: "2020 Corona Flash Crash",
    subtitle: "Schlagartiger Lockdown-Schock",
    icon: Flame,
    color: "from-orange-500/20 to-amber-600/10 border-orange-500/30",
  },
  {
    id: "rate_shock_2022",
    title: "2022 Zinsschock",
    subtitle: "Tech-Bärenmarkt & Rohstoffrally",
    icon: Zap,
    color: "from-blue-500/20 to-indigo-600/10 border-blue-500/30",
  },
  {
    id: "stagflation",
    title: "Stagflations-Schock",
    subtitle: "Ölschock & Margendruck",
    icon: Activity,
    color: "from-purple-500/20 to-pink-600/10 border-purple-500/30",
  },
  {
    id: "custom",
    title: "Individueller Schock",
    subtitle: "Frei wählbarer Marktrücksetzer",
    icon: Sliders,
    color: "from-slate-500/20 to-zinc-600/10 border-slate-500/30",
  },
];

export default function StressTestSimulator({
  portfolioId,
  portfolioName = "Mein Portfolio",
}: StressTestSimulatorProps) {
  const { formatPrice } = useCurrency();
  const [selectedScenario, setSelectedScenario] = useState<string>("financial_crisis_2008");
  const [customDropPct, setCustomDropPct] = useState<number>(25);
  const [data, setData] = useState<StressTestResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const runStressTest = async () => {
    if (!portfolioId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/portfolio/${portfolioId}/stress-test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario: selectedScenario,
          custom_market_drop_pct: customDropPct,
        }),
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const json: StressTestResponse = await res.json();
      setData(json);
    } catch (err: any) {
      setError(err?.message || "Fehler bei der Durchführung des Stresstests.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    runStressTest();
  }, [portfolioId, selectedScenario, customDropPct]);

  const summary = data?.summary;
  const isCritical = summary?.risk_rating === "Kritisch";
  const isWarning = summary?.risk_rating === "Erhoeht" || summary?.risk_rating === "Erhöht";

  return (
    <section className="surface-panel rounded-[2rem] p-6 lg:p-7 space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-rose-600 dark:text-rose-400">
            <ShieldAlert className="h-4 w-4" />
            <span className="text-xs font-extrabold uppercase tracking-[0.2em]">
              Krisen-Simulation & Stress-Testing
            </span>
          </div>
          <h3 className="mt-1 text-xl font-extrabold tracking-tight text-slate-900 dark:text-white">
            Wie krisensicher ist {portfolioName}?
          </h3>
        </div>

        <button
          onClick={runStressTest}
          disabled={loading}
          className="flex items-center gap-2 self-start rounded-xl border border-black/8 bg-black/[0.03] px-3.5 py-2 text-xs font-bold text-slate-700 transition hover:bg-black/[0.06] dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:hover:bg-white/10 lg:self-auto"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin text-rose-500" : ""}`} />
          Neu simulieren
        </button>
      </div>

      {/* Scenario Tiles */}
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-5">
        {SCENARIOS.map((sc) => {
          const Icon = sc.icon;
          const isSelected = selectedScenario === sc.id;
          return (
            <button
              key={sc.id}
              onClick={() => setSelectedScenario(sc.id)}
              className={`flex flex-col items-start rounded-2xl border p-3.5 text-left transition-all ${
                isSelected
                  ? `border-rose-500 bg-rose-500/[0.08] shadow-md shadow-rose-500/10 dark:border-rose-400 dark:bg-rose-500/[0.12]`
                  : "border-black/8 bg-black/[0.02] hover:bg-black/[0.04] dark:border-white/8 dark:bg-white/[0.03] dark:hover:bg-white/[0.06]"
              }`}
            >
              <div
                className={`rounded-xl p-2 mb-2 ${
                  isSelected
                    ? "bg-rose-500 text-white"
                    : "bg-black/[0.05] text-slate-600 dark:bg-white/10 dark:text-slate-300"
                }`}
              >
                <Icon className="h-4 w-4" />
              </div>
              <div className="text-xs font-extrabold text-slate-900 dark:text-white line-clamp-1">
                {sc.title}
              </div>
              <div className="mt-0.5 text-[10px] text-slate-500 dark:text-slate-400 line-clamp-1">
                {sc.subtitle}
              </div>
            </button>
          );
        })}
      </div>

      {/* Custom Slider (only when custom scenario selected) */}
      {selectedScenario === "custom" && (
        <div className="rounded-2xl border border-black/8 bg-black/[0.02] p-4 dark:border-white/10 dark:bg-white/5 flex flex-col sm:flex-row items-center gap-4 justify-between">
          <div className="flex items-center gap-3">
            <Sliders className="h-5 w-5 text-indigo-500" />
            <div>
              <div className="text-xs font-bold text-slate-900 dark:text-white">
                Simulierter Markteinbruch: -{customDropPct}%
              </div>
              <div className="text-[11px] text-slate-500">
                Wird gewichtet nach dem individuellen Beta jeder Aktie berechnet
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3 w-full sm:w-64">
            <span className="text-xs font-mono text-slate-400">-10%</span>
            <input
              type="range"
              min="10"
              max="50"
              step="5"
              value={customDropPct}
              onChange={(e) => setCustomDropPct(Number(e.target.value))}
              className="w-full accent-rose-600"
            />
            <span className="text-xs font-mono text-slate-400">-50%</span>
          </div>
        </div>
      )}

      {/* KPI Crash Summary Banner */}
      {summary && summary.initial_value > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-5">
          {/* Initial vs Simulated Value */}
          <div className="rounded-2xl border border-black/8 bg-black/[0.02] p-4 dark:border-white/10 dark:bg-white/5">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Simulierter Depotwert
            </div>
            <div className="mt-1 text-xl font-black text-slate-900 dark:text-white">
              {formatPrice(summary.simulated_value)}
            </div>
            <div className="mt-1 text-[11px] text-slate-500 line-through">
              {formatPrice(summary.initial_value)}
            </div>
          </div>

          {/* Loss EUR */}
          <div className="rounded-2xl border border-rose-500/20 bg-rose-500/[0.05] p-4 dark:border-rose-500/30">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-rose-600 dark:text-rose-400">
              Simulierter Verlust (€)
            </div>
            <div className="mt-1 text-xl font-black text-rose-600 dark:text-rose-400">
              -{formatPrice(summary.loss_eur)}
            </div>
            <div className="mt-1 text-[11px] text-rose-600/80 font-semibold">
              Maximaler Stress-Drawdown
            </div>
          </div>

          {/* Loss % */}
          <div className="rounded-2xl border border-rose-500/20 bg-rose-500/[0.05] p-4 dark:border-rose-500/30">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-rose-600 dark:text-rose-400">
              Depot-Verlust (%)
            </div>
            <div className="mt-1 text-xl font-black text-rose-600 dark:text-rose-400">
              {summary.loss_pct.toFixed(1)}%
            </div>
            <div className="mt-1 text-[11px] text-rose-600/80 font-semibold">
              Gesamtrücksetzer
            </div>
          </div>

          {/* Risk Rating Badge */}
          <div className="rounded-2xl border border-black/8 bg-black/[0.02] p-4 dark:border-white/10 dark:bg-white/5">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Risikoeinstufung
            </div>
            <div className="mt-1 flex items-center gap-1.5">
              {isCritical ? (
                <ShieldAlert className="h-5 w-5 text-rose-600 dark:text-rose-400" />
              ) : isWarning ? (
                <AlertTriangle className="h-5 w-5 text-amber-500" />
              ) : (
                <ShieldCheck className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
              )}
              <span
                className={`text-lg font-black ${
                  isCritical
                    ? "text-rose-600 dark:text-rose-400"
                    : isWarning
                    ? "text-amber-600 dark:text-amber-400"
                    : "text-emerald-600 dark:text-emerald-400"
                }`}
              >
                {summary.risk_rating}
              </span>
            </div>
            <div className="mt-1 text-[11px] text-slate-500">
              {isCritical ? "Hohes Klumpenrisiko" : isWarning ? "Mittlere Volatilität" : "Hohe Resilienz"}
            </div>
          </div>

          {/* Portfolio Beta */}
          <div className="col-span-2 sm:col-span-1 rounded-2xl border border-black/8 bg-black/[0.02] p-4 dark:border-white/10 dark:bg-white/5">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Gewichtetes Beta (β)
            </div>
            <div className="mt-1 text-xl font-black text-slate-900 dark:text-white">
              {summary.weighted_beta.toFixed(2)}
            </div>
            <div className="mt-1 text-[11px] text-slate-500">
              {summary.weighted_beta > 1.15
                ? "Offensiv / High Beta"
                : summary.weighted_beta < 0.85
                ? "Defensiv gepuffert"
                : "Marktsynchron"}
            </div>
          </div>
        </div>
      )}

      {/* Two Columns: Vulnerable Drivers vs Resilient Stabilizers */}
      {data && data.holdings.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2">
          {/* Top Vulnerable Assets */}
          <div className="rounded-2xl border border-rose-500/20 bg-rose-500/[0.03] p-5 dark:border-rose-500/20 dark:bg-rose-950/10">
            <div className="flex items-center gap-2 text-rose-600 dark:text-rose-400 font-extrabold text-xs uppercase tracking-wider mb-3">
              <TrendingDown className="h-4 w-4" />
              Größte Verlusttreiber (Vulnerable)
            </div>
            <div className="space-y-2.5">
              {data.vulnerable_assets.map((h) => (
                <div
                  key={h.ticker}
                  className="flex items-center justify-between rounded-xl bg-white/70 p-3 shadow-sm dark:bg-black/30"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-black text-sm text-slate-900 dark:text-white">
                        {h.ticker}
                      </span>
                      <span className="text-xs text-slate-500 truncate max-w-[120px]">
                        {h.name}
                      </span>
                    </div>
                    <div className="text-[11px] text-slate-500 dark:text-slate-400">
                      {h.sector} • β {h.beta.toFixed(2)}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-extrabold text-sm text-rose-600 dark:text-rose-400">
                      {h.shock_pct >= 0 ? `+${h.shock_pct.toFixed(1)}%` : `${h.shock_pct.toFixed(1)}%`}
                    </div>
                    <div className="text-[11px] text-slate-500">
                      -{formatPrice(h.loss_eur)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Top Resilient Assets */}
          <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/[0.03] p-5 dark:border-emerald-500/20 dark:bg-emerald-950/10">
            <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400 font-extrabold text-xs uppercase tracking-wider mb-3">
              <ShieldCheck className="h-4 w-4" />
              Beste Stabilisatoren & Puffer (Resilient)
            </div>
            <div className="space-y-2.5">
              {data.resilient_assets.map((h) => (
                <div
                  key={h.ticker}
                  className="flex items-center justify-between rounded-xl bg-white/70 p-3 shadow-sm dark:bg-black/30"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-black text-sm text-slate-900 dark:text-white">
                        {h.ticker}
                      </span>
                      <span className="text-xs text-slate-500 truncate max-w-[120px]">
                        {h.name}
                      </span>
                    </div>
                    <div className="text-[11px] text-slate-500 dark:text-slate-400">
                      {h.sector} • β {h.beta.toFixed(2)}
                    </div>
                  </div>
                  <div className="text-right">
                    <div
                      className={`font-extrabold text-sm ${
                        h.shock_pct >= 0
                          ? "text-emerald-600 dark:text-emerald-400"
                          : "text-slate-700 dark:text-slate-300"
                      }`}
                    >
                      {h.shock_pct >= 0 ? `+${h.shock_pct.toFixed(1)}%` : `${h.shock_pct.toFixed(1)}%`}
                    </div>
                    <div className="text-[11px] text-slate-500">
                      {h.loss_eur <= 0 ? `+${formatPrice(-h.loss_eur)}` : `-${formatPrice(h.loss_eur)}`}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Holdings Breakdown Table */}
      {data && data.holdings.length > 0 && (
        <div className="overflow-x-auto rounded-2xl border border-black/8 bg-black/[0.01] dark:border-white/10 dark:bg-white/[0.02]">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-black/6 bg-black/[0.02] text-slate-500 dark:border-white/8 dark:bg-white/[0.03]">
                <th className="p-3.5 font-extrabold uppercase tracking-wider">Aktie / Position</th>
                <th className="p-3.5 font-extrabold uppercase tracking-wider">Sektor</th>
                <th className="p-3.5 font-extrabold uppercase tracking-wider text-right">Beta (β)</th>
                <th className="p-3.5 font-extrabold uppercase tracking-wider text-right">Vor Krise</th>
                <th className="p-3.5 font-extrabold uppercase tracking-wider text-right">Im Crash</th>
                <th className="p-3.5 font-extrabold uppercase tracking-wider text-right">Verlust (€)</th>
                <th className="p-3.5 font-extrabold uppercase tracking-wider text-right">Drawdown</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-black/6 dark:divide-white/8">
              {data.holdings.map((h) => (
                <tr key={h.ticker} className="hover:bg-black/[0.02] dark:hover:bg-white/[0.03]">
                  <td className="p-3.5">
                    <div className="font-black text-slate-900 dark:text-white">{h.ticker}</div>
                    <div className="text-[11px] text-slate-500 truncate max-w-[150px]">{h.name}</div>
                  </td>
                  <td className="p-3.5 text-slate-600 dark:text-slate-300 font-medium">{h.sector}</td>
                  <td className="p-3.5 text-right font-mono font-bold text-slate-700 dark:text-slate-300">
                    {h.beta.toFixed(2)}
                  </td>
                  <td className="p-3.5 text-right font-mono text-slate-700 dark:text-slate-300">
                    {formatPrice(h.current_value)}
                  </td>
                  <td className="p-3.5 text-right font-mono font-bold text-slate-900 dark:text-white">
                    {formatPrice(h.simulated_value)}
                  </td>
                  <td className="p-3.5 text-right font-mono font-extrabold text-rose-600 dark:text-rose-400">
                    {h.loss_eur > 0 ? `-${formatPrice(h.loss_eur)}` : `+${formatPrice(-h.loss_eur)}`}
                  </td>
                  <td className="p-3.5 text-right font-mono font-extrabold">
                    <span
                      className={`inline-block rounded-lg px-2 py-0.5 ${
                        h.shock_pct > 0
                          ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
                          : h.shock_pct < -40
                          ? "bg-rose-500/15 text-rose-700 dark:text-rose-400"
                          : "bg-amber-500/15 text-amber-700 dark:text-amber-400"
                      }`}
                    >
                      {h.shock_pct >= 0 ? `+${h.shock_pct.toFixed(1)}%` : `${h.shock_pct.toFixed(1)}%`}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Actionable Hedging Recommendations */}
      {data && data.recommendations.length > 0 && (
        <div className="rounded-2xl border border-black/8 bg-black/[0.02] p-5 dark:border-white/10 dark:bg-white/5 space-y-2.5">
          <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider text-slate-600 dark:text-slate-300">
            <Lightbulb className="h-4 w-4 text-amber-500" />
            Strategische Handlungsempfehlungen zur Absicherung
          </div>
          <ul className="space-y-2 text-xs leading-relaxed text-slate-600 dark:text-slate-300">
            {data.recommendations.map((rec, idx) => (
              <li key={idx} className="flex items-start gap-2">
                <span className="mt-1 h-1.5 w-1.5 rounded-full bg-rose-500 flex-shrink-0" />
                <span>{rec}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
