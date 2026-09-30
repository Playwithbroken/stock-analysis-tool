import React, { useEffect, useMemo, useState } from "react";
import {
  AlertOctagon,
  Flame,
  ShieldAlert,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  Activity,
  Calendar,
  Layers,
  Sliders,
  RefreshCw,
  X,
  ExternalLink,
  Info,
  DollarSign,
  Compass,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine,
} from "recharts";
import MeasuredChartFrame from "./MeasuredChartFrame";

interface CrisisScenarioTerminalProps {
  portfolioId: string;
  onAnalyzeStock?: (ticker: string) => void;
  onClose?: () => void;
}

interface ScenarioTrajectoryPoint {
  label: string;
  month: number;
  portfolio_pct: number;
  market_pct: number;
  portfolio_value: number;
  market_value: number;
}

interface HoldingCrisisImpact {
  ticker: string;
  name: string;
  value: number;
  weight_pct: number;
  sector: string;
  asset_class: string;
  beta: number;
  projected_loss_pct: number;
  projected_loss_eur: number;
  resilience_label: string;
  resilience_tone: "green" | "blue" | "amber" | "red";
}

interface CrisisScenarioData {
  id: string;
  name: string;
  period: string;
  category: string;
  description: string;
  benchmark_name: string;
  benchmark_drawdown: number;
  recovery_months: number;
  volatility_spike: number;
  portfolio_drawdown_pct: number;
  portfolio_loss_eur: number;
  alpha_in_crisis: number;
  outperformed_benchmark: boolean;
  trajectory: ScenarioTrajectoryPoint[];
  top_vulnerable: HoldingCrisisImpact[];
  top_resilient: HoldingCrisisImpact[];
  holdings: HoldingCrisisImpact[];
}

interface PlaybookRecommendation {
  title: string;
  type: string;
  priority: string;
  description: string;
}

interface CrisisAnalysisResult {
  portfolio_value: number;
  safe_haven_pct: number;
  resilience_score: number;
  resilience_rating: string;
  resilience_badge: string;
  worst_drawdown_pct: number;
  worst_drawdown_eur: number;
  worst_crisis_name: string;
  avg_recovery_months: number;
  scenarios: Record<string, CrisisScenarioData>;
  playbook: PlaybookRecommendation[];
  holdings_count: number;
}

export default function CrisisScenarioTerminal({
  portfolioId,
  onAnalyzeStock,
  onClose,
}: CrisisScenarioTerminalProps) {
  const [data, setData] = useState<CrisisAnalysisResult | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedScenarioKey, setSelectedScenarioKey] = useState<string>("gfc_lehman_2008");
  const [activeTab, setActiveTab] = useState<"scenarios" | "holdings" | "simulator" | "playbook">("scenarios");

  // Custom simulator states
  const [equityShock, setEquityShock] = useState<number>(-25);
  const [rateShock, setRateShock] = useState<number>(100);
  const [oilShock, setOilShock] = useState<number>(40);
  const [creditSpread, setCreditSpread] = useState<number>(150);
  const [simResult, setSimResult] = useState<any | null>(null);
  const [simLoading, setSimLoading] = useState<boolean>(false);

  const fetchCrisisData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/portfolio/${portfolioId}/crisis-scenarios`);
      if (!res.ok) {
        throw new Error(`Fehler beim Abrufen der Krisenszenarien (${res.status})`);
      }
      const json: CrisisAnalysisResult = await res.json();
      setData(json);
    } catch (err: any) {
      setError(err.message || "Unerwarteter Fehler beim Laden der Krisenanalyse");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCrisisData();
  }, [portfolioId]);

  const handleSimulateCustom = async () => {
    setSimLoading(true);
    try {
      const res = await fetch("/api/portfolio/crisis-scenarios/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          portfolio_id: portfolioId,
          equity_shock_pct: equityShock,
          rate_shock_bps: rateShock,
          oil_shock_pct: oilShock,
          credit_spread_bps: creditSpread,
        }),
      });
      if (res.ok) {
        const json = await res.json();
        setSimResult(json);
      }
    } catch {
      // ignore
    } finally {
      setSimLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === "simulator" && !simResult) {
      handleSimulateCustom();
    }
  }, [activeTab]);

  const currentScenario = useMemo(() => {
    if (!data?.scenarios) return null;
    return data.scenarios[selectedScenarioKey] || Object.values(data.scenarios)[0];
  }, [data, selectedScenarioKey]);

  const formatEur = (val?: number) => {
    if (val == null || isNaN(val)) return "0 €";
    return new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(val);
  };

  const formatPct = (val?: number) => {
    if (val == null || isNaN(val)) return "0.0%";
    const sign = val > 0 ? "+" : "";
    return `${sign}${val.toFixed(1)}%`;
  };

  if (loading) {
    return (
      <div className="surface-panel rounded-[2rem] border border-black/10 dark:border-white/10 bg-white/95 dark:bg-[#14161c]/95 p-8 shadow-xl">
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <RefreshCw className="h-8 w-8 animate-spin text-amber-600 dark:text-amber-400" />
          <h3 className="mt-4 text-base font-black uppercase tracking-[0.16em] text-slate-800 dark:text-slate-100">
            Historische Krisen & Geopolitische Schocks werden simuliert …
          </h3>
          <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">
            Berechne Drawdown-Trajektorien, Sektor-Transmissionen und Resilienz-Scores gegen 7 Makro-Krisen.
          </p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="surface-panel rounded-[2rem] border border-red-500/20 bg-red-50/20 p-8 text-center dark:border-red-500/20 dark:bg-red-950/20">
        <AlertOctagon className="mx-auto h-8 w-8 text-red-600 dark:text-red-400" />
        <h3 className="mt-3 text-sm font-black uppercase tracking-[0.16em] text-red-900 dark:text-red-200">
          Fehler beim Laden des Krisen-Terminals
        </h3>
        <p className="mt-1 text-xs text-red-700 dark:text-red-300">{error || "Keine Daten verfügbar"}</p>
        <button
          onClick={fetchCrisisData}
          className="mt-4 rounded-xl bg-red-600 px-4 py-2 text-xs font-bold text-white hover:bg-red-700"
        >
          Erneut versuchen
        </button>
      </div>
    );
  }

  return (
    <div className="surface-panel rounded-[2rem] border border-black/10 dark:border-white/10 bg-white/95 dark:bg-[#14161c]/95 p-6 shadow-2xl transition-all sm:p-8">
      {/* Header */}
      <div className="flex flex-col gap-4 border-b border-black/8 pb-6 dark:border-white/10 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-amber-500/15 text-amber-600 dark:bg-amber-500/20 dark:text-amber-400">
            <Flame className="h-6 w-6" />
          </span>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-black tracking-tight text-slate-900 dark:text-white sm:text-2xl">
                Krisen-Replay & Geopolitischer Schock-Simulator
              </h2>
              <span className="rounded-full border border-amber-500/30 bg-amber-500/15 px-2.5 py-0.5 text-[10px] font-black uppercase tracking-[0.14em] text-amber-900 dark:text-amber-200">
                Institutional Macro Stress Test
              </span>
            </div>
            <p className="text-xs text-slate-600 dark:text-slate-300">
              Historische Zeitreisen-Stresstests (1987–2024), Tag-für-Tag-Pfaderholung und asymmetrische Schocksensitivität.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={fetchCrisisData}
            title="Neu berechnen"
            className="rounded-xl border border-black/8 bg-black/5 p-2.5 text-slate-700 transition hover:bg-black/10 dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:hover:bg-white/10"
          >
            <RefreshCw size={15} />
          </button>
          {onClose && (
            <button
              onClick={onClose}
              title="Terminal schließen"
              className="rounded-xl border border-black/8 bg-black/5 p-2.5 text-slate-700 transition hover:bg-black/10 dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:hover:bg-white/10"
            >
              <X size={15} />
            </button>
          )}
        </div>
      </div>

      {/* 4 Institutional KPI Summary Cards */}
      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-black/[0.02] dark:bg-[#181a20] p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-600 dark:text-slate-300">
              Maximaler Krisen-Drawdown
            </span>
            <TrendingDown className="h-4 w-4 text-red-500" />
          </div>
          <div className="mt-2 text-2xl font-black text-red-600 dark:text-red-400">
            {formatPct(data.worst_drawdown_pct)}
          </div>
          <div className="mt-1 flex items-center justify-between text-xs text-slate-600 dark:text-slate-300">
            <span>{formatEur(data.worst_drawdown_eur)}</span>
            <span className="truncate font-semibold text-slate-800 dark:text-slate-200">{data.worst_crisis_name}</span>
          </div>
        </div>

        <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-black/[0.02] dark:bg-[#181a20] p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-600 dark:text-slate-300">
              Krisen-Resilienz-Score
            </span>
            <ShieldCheck className="h-4 w-4 text-emerald-500" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-black text-slate-900 dark:text-white">
              {data.resilience_score}
            </span>
            <span className="text-xs font-bold text-slate-500 dark:text-slate-400">/ 100</span>
          </div>
          <div className="mt-1 text-xs font-semibold text-emerald-700 dark:text-emerald-300">
            {data.resilience_badge} · {data.resilience_rating}
          </div>
        </div>

        <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-black/[0.02] dark:bg-[#181a20] p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-600 dark:text-slate-300">
              Safe-Haven & Schutzquote
            </span>
            <ShieldAlert className="h-4 w-4 text-sky-500" />
          </div>
          <div className="mt-2 text-2xl font-black text-sky-700 dark:text-sky-300">
            {data.safe_haven_pct.toFixed(1)}%
          </div>
          <div className="mt-1 text-xs text-slate-600 dark:text-slate-300">
            Gold, Geldmarkt & defensive Basistitel
          </div>
        </div>

        <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-black/[0.02] dark:bg-[#181a20] p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-600 dark:text-slate-300">
              Mittlere Erholungsdauer
            </span>
            <Calendar className="h-4 w-4 text-amber-500" />
          </div>
          <div className="mt-2 text-2xl font-black text-slate-900 dark:text-white">
            {data.avg_recovery_months} Monate
          </div>
          <div className="mt-1 text-xs text-slate-600 dark:text-slate-300">
            Bis zur vollständigen Kapitalerholung (Tiefpunkt bis Vor-Crash-Niveau)
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="mt-6 flex flex-wrap gap-2 border-b border-black/8 pb-3 dark:border-white/10">
        {[
          { key: "scenarios", label: "Historische Krisenszenarien", icon: Flame },
          { key: "holdings", label: "Holdings Krisen-Sensitivität", icon: Layers },
          { key: "simulator", label: "Interaktiver Schock-Simulator", icon: Sliders },
          { key: "playbook", label: "Institutional Crisis Playbook", icon: Compass },
        ].map((t) => {
          const Icon = t.icon;
          const active = activeTab === t.key;
          return (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key as any)}
              className={`inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-black uppercase tracking-[0.14em] transition ${
                active
                  ? "border border-amber-500/30 bg-amber-500/15 text-amber-900 dark:text-amber-200"
                  : "border border-transparent text-slate-600 hover:bg-black/5 dark:text-slate-300 dark:hover:bg-white/5"
              }`}
            >
              <Icon size={14} />
              {t.label}
            </button>
          );
        })}
      </div>

      {/* Tab 1: Historical Scenarios Replay */}
      {activeTab === "scenarios" && currentScenario && (
        <div className="mt-6 space-y-6">
          {/* Scenario Selector Pills */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
            {Object.entries(data.scenarios).map(([key, sc]) => {
              const selected = selectedScenarioKey === key;
              return (
                <button
                  key={key}
                  onClick={() => setSelectedScenarioKey(key)}
                  className={`flex flex-col items-start rounded-xl border p-3 text-left transition ${
                    selected
                      ? "border-amber-500 bg-amber-500/15 text-slate-900 dark:text-white"
                      : "border-black/8 bg-black/[0.02] hover:bg-black/5 dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10"
                  }`}
                >
                  <span className="text-[10px] font-bold text-slate-500 dark:text-slate-400 truncate w-full">{sc.period}</span>
                  <span className="mt-1 text-xs font-black truncate w-full text-slate-900 dark:text-white">{sc.name.split(" ")[0]} {sc.name.split(" ")[1]}</span>
                  <span className={`mt-2 text-xs font-black ${sc.portfolio_drawdown_pct < -30 ? "text-red-600 dark:text-red-400" : "text-amber-600 dark:text-amber-400"}`}>
                    {formatPct(sc.portfolio_drawdown_pct)}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Selected Scenario Spotlight Box */}
          <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-black/[0.02] dark:bg-[#181a20] p-6 shadow-sm">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="rounded-md bg-amber-500/15 px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.14em] text-amber-900 dark:text-amber-200">
                    {currentScenario.category}
                  </span>
                  <span className="text-xs text-slate-500 dark:text-slate-400">{currentScenario.period}</span>
                </div>
                <h3 className="mt-2 text-xl font-black text-slate-900 dark:text-white">
                  {currentScenario.name}
                </h3>
                <p className="mt-1 max-w-3xl text-xs leading-relaxed text-slate-600 dark:text-slate-300">
                  {currentScenario.description}
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-4">
                <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 p-3 text-center min-w-[110px]">
                  <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">Portfolio Drawdown</div>
                  <div className="mt-1 text-base font-black text-red-600 dark:text-red-400">{formatPct(currentScenario.portfolio_drawdown_pct)}</div>
                  <div className="text-[10px] text-slate-500">{formatEur(currentScenario.portfolio_loss_eur)}</div>
                </div>
                <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 p-3 text-center min-w-[110px]">
                  <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">{currentScenario.benchmark_name}</div>
                  <div className="mt-1 text-base font-black text-slate-700 dark:text-slate-300">{formatPct(currentScenario.benchmark_drawdown)}</div>
                  <div className="text-[10px] text-slate-500">Benchmark-Tief</div>
                </div>
                <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 p-3 text-center min-w-[110px]">
                  <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">Alpha in Krise</div>
                  <div className={`mt-1 text-base font-black ${currentScenario.alpha_in_crisis >= 0 ? "text-emerald-700 dark:text-emerald-300" : "text-red-600 dark:text-red-400"}`}>
                    {formatPct(currentScenario.alpha_in_crisis)}
                  </div>
                  <div className="text-[10px] text-slate-500">{currentScenario.outperformed_benchmark ? "Outperformance" : "Underperformance"}</div>
                </div>
              </div>
            </div>

            {/* Trajectory Chart */}
            <div className="mt-6">
              <div className="mb-2 text-xs font-black uppercase tracking-[0.16em] text-slate-700 dark:text-slate-300">
                Krisenverlauf & Erholungs-Trajektorie (Replay in % vom Ausgangsvermögen)
              </div>
              <MeasuredChartFrame minHeight={300} className="w-full">
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={currentScenario.trajectory} margin={{ top: 10, right: 20, left: 0, bottom: 25 }}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                    <XAxis
                      dataKey="label"
                      tick={{ fill: "#888888", fontSize: 10 }}
                      interval={0}
                      angle={-15}
                      textAnchor="end"
                    />
                    <YAxis
                      tick={{ fill: "#888888", fontSize: 10 }}
                      tickFormatter={(val) => `${val}%`}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#181a20",
                        borderColor: "#333",
                        borderRadius: "0.75rem",
                        color: "#fff",
                        fontSize: "12px",
                      }}
                      formatter={(val: any) => [`${Number(val).toFixed(1)}%`]}
                    />
                    <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "10px" }} />
                    <ReferenceLine y={0} stroke="#666" strokeDasharray="3 3" />
                    <Line
                      type="monotone"
                      dataKey="portfolio_pct"
                      name="Aktuelles Portfolio (Replay)"
                      stroke="#f59e0b"
                      strokeWidth={3}
                      dot={{ r: 4, fill: "#f59e0b" }}
                    />
                    <Line
                      type="monotone"
                      dataKey="market_pct"
                      name={`Markt Benchmark (${currentScenario.benchmark_name})`}
                      stroke="#94a3b8"
                      strokeWidth={2}
                      strokeDasharray="4 4"
                      dot={{ r: 3, fill: "#94a3b8" }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </MeasuredChartFrame>
            </div>

            {/* Top Vulnerable vs. Resilient Positions */}
            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4">
                <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.14em] text-red-900 dark:text-red-300">
                  <TrendingDown size={15} />
                  Größte Krisen-Verlierer im Szenario
                </div>
                <div className="mt-3 space-y-2">
                  {currentScenario.top_vulnerable.map((pos) => (
                    <div key={pos.ticker} className="flex items-center justify-between text-xs">
                      <div>
                        <button
                          onClick={() => onAnalyzeStock && onAnalyzeStock(pos.ticker)}
                          className="font-black text-slate-900 hover:underline dark:text-white"
                        >
                          {pos.ticker}
                        </button>
                        <span className="ml-2 text-[10px] text-slate-500">({pos.sector})</span>
                      </div>
                      <div className="text-right">
                        <span className="font-bold text-red-600 dark:text-red-400">{formatPct(pos.projected_loss_pct)}</span>
                        <span className="ml-2 text-[11px] text-slate-500">{formatEur(pos.projected_loss_eur)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4">
                <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.14em] text-emerald-900 dark:text-emerald-300">
                  <TrendingUp size={15} />
                  Resistente Puffer & Krisen-Hedges
                </div>
                <div className="mt-3 space-y-2">
                  {currentScenario.top_resilient.map((pos) => (
                    <div key={pos.ticker} className="flex items-center justify-between text-xs">
                      <div>
                        <button
                          onClick={() => onAnalyzeStock && onAnalyzeStock(pos.ticker)}
                          className="font-black text-slate-900 hover:underline dark:text-white"
                        >
                          {pos.ticker}
                        </button>
                        <span className="ml-2 text-[10px] text-slate-500">({pos.asset_class})</span>
                      </div>
                      <div className="text-right">
                        <span className={`font-bold ${pos.projected_loss_pct >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-slate-700 dark:text-slate-300"}`}>
                          {formatPct(pos.projected_loss_pct)}
                        </span>
                        <span className="ml-2 text-[11px] text-slate-500">{formatEur(pos.projected_loss_eur)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Holdings Sensitivity Matrix */}
      {activeTab === "holdings" && currentScenario && (
        <div className="mt-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-black uppercase tracking-[0.16em] text-slate-800 dark:text-slate-200">
              Holdings-Aufschlüsselung im Szenario: {currentScenario.name}
            </h3>
            <span className="text-xs text-slate-500">
              Sortiert nach Verlusthöhe (stärkste Betroffenheit zuerst)
            </span>
          </div>

          <div className="overflow-x-auto rounded-2xl border border-black/10 dark:border-white/10 bg-black/[0.02] dark:bg-[#181a20]">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-black/8 bg-black/5 dark:border-white/10 dark:bg-white/5 text-[10px] font-black uppercase tracking-[0.14em] text-slate-600 dark:text-slate-300">
                <tr>
                  <th className="p-3.5">Ticker / Name</th>
                  <th className="p-3.5">Klasse & Sektor</th>
                  <th className="p-3.5 text-right">Gewicht %</th>
                  <th className="p-3.5 text-right">Positionswert</th>
                  <th className="p-3.5 text-right">Beta</th>
                  <th className="p-3.5 text-right">Projizierter Verlust %</th>
                  <th className="p-3.5 text-right">Verlust in Euro</th>
                  <th className="p-3.5 text-center">Resilienz-Klassifizierung</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/6 dark:divide-white/5">
                {currentScenario.holdings.map((h) => (
                  <tr key={h.ticker} className="hover:bg-black/[0.03] dark:hover:bg-white/[0.03] transition">
                    <td className="p-3.5">
                      <button
                        onClick={() => onAnalyzeStock && onAnalyzeStock(h.ticker)}
                        className="font-black text-slate-900 hover:underline dark:text-white flex items-center gap-1.5"
                      >
                        {h.ticker}
                        <ExternalLink size={11} className="opacity-50" />
                      </button>
                      <div className="text-[11px] text-slate-500 truncate max-w-[160px]">{h.name}</div>
                    </td>
                    <td className="p-3.5">
                      <span className="rounded bg-black/5 dark:bg-white/10 px-1.5 py-0.5 text-[10px] font-bold text-slate-700 dark:text-slate-200">
                        {h.asset_class}
                      </span>
                      <div className="mt-0.5 text-[10px] text-slate-500">{h.sector}</div>
                    </td>
                    <td className="p-3.5 text-right font-semibold">{h.weight_pct.toFixed(1)}%</td>
                    <td className="p-3.5 text-right font-medium">{formatEur(h.value)}</td>
                    <td className="p-3.5 text-right font-bold text-slate-700 dark:text-slate-300">{h.beta.toFixed(2)}</td>
                    <td className="p-3.5 text-right font-black text-red-600 dark:text-red-400">
                      {formatPct(h.projected_loss_pct)}
                    </td>
                    <td className="p-3.5 text-right font-bold text-red-600 dark:text-red-400">
                      {formatEur(h.projected_loss_eur)}
                    </td>
                    <td className="p-3.5 text-center">
                      <span
                        className={`inline-block rounded-full border px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.1em] ${
                          h.resilience_tone === "green"
                            ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-950 dark:text-emerald-300"
                            : h.resilience_tone === "blue"
                            ? "border-sky-500/30 bg-sky-500/15 text-sky-950 dark:text-sky-300"
                            : h.resilience_tone === "amber"
                            ? "border-amber-500/30 bg-amber-500/15 text-amber-950 dark:text-amber-300"
                            : "border-red-500/30 bg-red-500/15 text-red-950 dark:text-red-300"
                        }`}
                      >
                        {h.resilience_label}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 3: Interactive Macro Shock Simulator */}
      {activeTab === "simulator" && (
        <div className="mt-6 space-y-6">
          <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-black/[0.02] dark:bg-[#181a20] p-6 shadow-sm">
            <h3 className="text-sm font-black uppercase tracking-[0.16em] text-slate-800 dark:text-slate-200">
              Parametrischer Makro-Stresstest Simulator
            </h3>
            <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
              Konfigurieren Sie eigene Stress-Faktoren über Aktien-, Zins-, Rohstoff- und Credit-Märkte zur Echtzeitberechnung des Portfolio-Verlusts.
            </p>

            <div className="mt-6 grid gap-6 md:grid-cols-2 lg:grid-cols-4">
              <div>
                <div className="flex justify-between text-xs font-bold">
                  <span className="text-slate-700 dark:text-slate-300">Aktienindex-Schock</span>
                  <span className="font-black text-red-600 dark:text-red-400">{equityShock}%</span>
                </div>
                <input
                  type="range"
                  min={-60}
                  max={-5}
                  step={5}
                  value={equityShock}
                  onChange={(e) => setEquityShock(Number(e.target.value))}
                  className="mt-2 w-full accent-amber-500"
                />
                <div className="mt-1 flex justify-between text-[9px] text-slate-400">
                  <span>-60% (Crash)</span>
                  <span>-5% (Korrektur)</span>
                </div>
              </div>

              <div>
                <div className="flex justify-between text-xs font-bold">
                  <span className="text-slate-700 dark:text-slate-300">Zinskurven-Schock</span>
                  <span className="font-black text-amber-600 dark:text-amber-400">{rateShock > 0 ? `+${rateShock}` : rateShock} bps</span>
                </div>
                <input
                  type="range"
                  min={-150}
                  max={300}
                  step={25}
                  value={rateShock}
                  onChange={(e) => setRateShock(Number(e.target.value))}
                  className="mt-2 w-full accent-amber-500"
                />
                <div className="mt-1 flex justify-between text-[9px] text-slate-400">
                  <span>-150 bps</span>
                  <span>+300 bps (Zinsschock)</span>
                </div>
              </div>

              <div>
                <div className="flex justify-between text-xs font-bold">
                  <span className="text-slate-700 dark:text-slate-300">Rohölpreis-Schock</span>
                  <span className="font-black text-orange-600 dark:text-orange-400">{oilShock > 0 ? `+${oilShock}` : oilShock}%</span>
                </div>
                <input
                  type="range"
                  min={-40}
                  max={100}
                  step={10}
                  value={oilShock}
                  onChange={(e) => setOilShock(Number(e.target.value))}
                  className="mt-2 w-full accent-amber-500"
                />
                <div className="mt-1 flex justify-between text-[9px] text-slate-400">
                  <span>-40% (Deflation)</span>
                  <span>+100% (Energieschock)</span>
                </div>
              </div>

              <div>
                <div className="flex justify-between text-xs font-bold">
                  <span className="text-slate-700 dark:text-slate-300">Credit Spread Widening</span>
                  <span className="font-black text-purple-600 dark:text-purple-400">+{creditSpread} bps</span>
                </div>
                <input
                  type="range"
                  min={50}
                  max={500}
                  step={25}
                  value={creditSpread}
                  onChange={(e) => setCreditSpread(Number(e.target.value))}
                  className="mt-2 w-full accent-amber-500"
                />
                <div className="mt-1 flex justify-between text-[9px] text-slate-400">
                  <span>+50 bps</span>
                  <span>+500 bps (Kreditkrise)</span>
                </div>
              </div>
            </div>

            <div className="mt-6 flex justify-end">
              <button
                onClick={handleSimulateCustom}
                disabled={simLoading}
                className="rounded-xl bg-amber-600 px-5 py-2.5 text-xs font-black uppercase tracking-[0.14em] text-white transition hover:bg-amber-700 disabled:opacity-50"
              >
                {simLoading ? "Simuliere …" : "Schock berechnen"}
              </button>
            </div>

            {simResult && (
              <div className="mt-6 border-t border-black/8 pt-6 dark:border-white/10">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                  <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 p-4 text-center">
                    <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">Projizierter Portfolio-Verlust</div>
                    <div className="mt-1 text-2xl font-black text-red-600 dark:text-red-400">{formatPct(simResult.total_loss_pct)}</div>
                  </div>
                  <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 p-4 text-center">
                    <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">Euro-Kapitalabzug</div>
                    <div className="mt-1 text-2xl font-black text-red-600 dark:text-red-400">{formatEur(simResult.total_loss_eur)}</div>
                  </div>
                  <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 p-4 text-center">
                    <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">Verbleibender Depotwert</div>
                    <div className="mt-1 text-2xl font-black text-slate-900 dark:text-white">{formatEur(simResult.resulting_value)}</div>
                  </div>
                </div>

                <div className="mt-6">
                  <div className="text-xs font-black uppercase tracking-[0.14em] text-slate-700 dark:text-slate-300">
                    Positions-Auswirkungen des Schocks
                  </div>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                    {simResult.holdings.slice(0, 8).map((h: any) => (
                      <div key={h.ticker} className="rounded-xl border border-black/8 dark:border-white/10 bg-black/[0.02] dark:bg-white/5 p-3">
                        <div className="flex justify-between items-center">
                          <span className="font-black text-slate-900 dark:text-white">{h.ticker}</span>
                          <span className="font-bold text-red-600 dark:text-red-400">{formatPct(h.loss_pct)}</span>
                        </div>
                        <div className="mt-1 flex justify-between text-[11px] text-slate-500">
                          <span>{h.sector}</span>
                          <span>{formatEur(h.loss_eur)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab 4: Institutional Crisis Playbook */}
      {activeTab === "playbook" && (
        <div className="mt-6 space-y-4">
          <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-black/[0.02] dark:bg-[#181a20] p-6 shadow-sm">
            <h3 className="text-sm font-black uppercase tracking-[0.16em] text-slate-800 dark:text-slate-200">
              Institutional Crisis Playbook & Kapitalerhaltungs-Leitfaden
            </h3>
            <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
              Konkrete Handlungsempfehlungen nach CFA- und Aladdin-Standards zur Minderung von Extremrisiken (Fat-Tail Protection).
            </p>

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              {data.playbook.map((item, idx) => (
                <div key={idx} className="rounded-xl border border-black/8 dark:border-white/10 bg-white/70 dark:bg-white/5 p-4 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-black uppercase tracking-[0.14em] text-amber-700 dark:text-amber-400">
                      {item.type} · Priorität {item.priority}
                    </span>
                    <span className="rounded-full bg-black/5 px-2 py-0.5 text-[9px] font-bold text-slate-600 dark:bg-white/10 dark:text-slate-300">
                      #0{idx + 1}
                    </span>
                  </div>
                  <h4 className="mt-2 text-sm font-bold text-slate-900 dark:text-white">
                    {item.title}
                  </h4>
                  <p className="mt-1 text-xs leading-relaxed text-slate-600 dark:text-slate-300">
                    {item.description}
                  </p>
                </div>
              ))}
            </div>

            <div className="mt-6 rounded-xl border border-amber-500/20 bg-amber-500/10 p-4">
              <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.14em] text-amber-950 dark:text-amber-200">
                <Info size={16} />
                Regulatorischer Hinweis zu Krisen-Stresstests (EBA / BaFin / Solvency II)
              </div>
              <p className="mt-1 text-xs leading-relaxed text-slate-700 dark:text-slate-300">
                Historische Stresstests simulieren das Portfolieverhalten unter der Annahme, dass Korrelationen in Stressphasen gegen 1 konvergieren (Korrelationszusammenbruch).
                Liquidität in Mid- und Small-Caps kann in Schockphasen um 80–90% austrocknen. Die ausgewiesenen Erholungszeiten basieren auf realen historischen Zyklen vor Transaktionskosten und Steuern.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
