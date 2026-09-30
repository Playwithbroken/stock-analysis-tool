import React, { useEffect, useState } from "react";
import {
  Landmark,
  TrendingDown,
  TrendingUp,
  AlertTriangle,
  RefreshCw,
  X,
  Sliders,
  ShieldCheck,
  Percent,
  Clock,
  Layers,
  Info,
  DollarSign,
  Activity
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

interface BondHolding {
  ticker: string;
  name: string;
  type: string;
  value_eur: number;
  weight_pct: number;
  shares: number;
  price: number;
  ytm_pct: number;
  macaulay_duration: number;
  modified_duration: number;
  convexity: number;
  dv01_eur: number;
  rating: string;
  credit_spread_bps: number;
}

interface YieldScenario {
  id: string;
  name: string;
  description: string;
  shift_bps: number;
  price_change_pct: number;
  delta_eur: number;
}

interface RatingBucket {
  rating: string;
  value_eur: number;
  weight_pct: number;
}

interface FixedIncomeData {
  valid: boolean;
  error?: string;
  portfolio_value_eur: number;
  fixed_income_sleeve_pct: number;
  summary: {
    modified_duration: number;
    macaulay_duration: number;
    convexity: number;
    dv01_eur: number;
    ytm_pct: number;
    average_credit_spread_bps: number;
    duration_badge: {
      label: string;
      tone: string;
    };
  };
  scenarios: YieldScenario[];
  rating_distribution: RatingBucket[];
  holdings: BondHolding[];
}

interface FixedIncomeTerminalProps {
  portfolioId: string;
  onAnalyzeStock?: (ticker: string) => void;
  onClose?: () => void;
}

export default function FixedIncomeTerminal({
  portfolioId,
  onAnalyzeStock,
  onClose
}: FixedIncomeTerminalProps) {
  const [data, setData] = useState<FixedIncomeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"scenarios" | "holdings" | "ratings">("scenarios");

  // Interactive slider state for custom shift (in bps)
  const [customShiftBps, setCustomShiftBps] = useState<number>(0);
  const [simulatedResult, setSimulatedResult] = useState<{
    price_change_pct: number;
    delta_eur: number;
  } | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/portfolio/${portfolioId}/fixed-income`, {
        credentials: "same-origin"
      });
      if (!res.ok) {
        throw new Error(`HTTP Fehler ${res.status}: Fixed Income Analyse fehlgeschlagen.`);
      }
      const json: FixedIncomeData = await res.json();
      if (!json.valid) {
        throw new Error(json.error || "Ungültige Rentendaten erhalten.");
      }
      setData(json);
    } catch (err: any) {
      setError(err.message || "Unerwarteter Fehler bei der Rentenrisiko-Analyse.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (portfolioId) {
      fetchData();
    }
  }, [portfolioId]);

  // Dynamic Taylor series calculation on slider change
  useEffect(() => {
    if (!data) return;
    const dy = customShiftBps / 10000.0;
    const modD = data.summary.modified_duration;
    const conv = data.summary.convexity;
    const pctChange = (-modD * dy + 0.5 * conv * (dy * dy)) * 100.0;
    const deltaEur = data.portfolio_value_eur * (pctChange / 100.0);
    setSimulatedResult({
      price_change_pct: Math.round(pctChange * 1000) / 1000,
      delta_eur: Math.round(deltaEur * 100) / 100
    });
  }, [customShiftBps, data]);

  const scenarioChartData = data ? data.scenarios.map((sc) => ({
    name: sc.name.split("(")[0].trim(),
    shift_bps: sc.shift_bps,
    price_change_pct: sc.price_change_pct,
    delta_eur: sc.delta_eur,
    color: sc.price_change_pct >= 0 ? "#10b981" : "#f43f5e"
  })) : [];

  return (
    <section className="mt-8 rounded-[2rem] border border-amber-500/20 bg-gradient-to-b from-amber-950/[0.04] to-transparent p-6 dark:border-amber-500/30 dark:bg-slate-900/60 shadow-xl backdrop-blur-md">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-black/10 pb-5 dark:border-white/10">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-500/15 text-amber-700 dark:text-amber-400 border border-amber-500/30 shadow-inner">
            <Landmark size={24} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-black tracking-tight text-slate-900 dark:text-white">
                Fixed Income &amp; Bond Yield Curve Analytics Terminal
              </h2>
              <span className="rounded-md border border-amber-500/30 bg-amber-500/15 px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider text-amber-800 dark:text-amber-300">
                DV01 &amp; Duration
              </span>
            </div>
            <p className="text-xs font-semibold text-slate-600 dark:text-slate-400">
              Zinsänderungsrisiko, Modified Duration, Convexity, DV01 &amp; Zinskurven-Stresstest
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
          <RefreshCw size={36} className="animate-spin text-amber-600 dark:text-amber-400" />
          <p className="mt-4 text-sm font-bold text-slate-700 dark:text-slate-300">
            Berechne Portfolio-Duration, Konvexität &amp; Zinskurven-Sensitivität...
          </p>
        </div>
      )}

      {error && (
        <div className="my-6 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-5 text-rose-800 dark:text-rose-300">
          <div className="flex items-center gap-2 font-black">
            <AlertTriangle size={18} />
            Fehler bei der Rentenrisiko-Analyse
          </div>
          <p className="mt-1 text-xs">{error}</p>
        </div>
      )}

      {!loading && !error && data && (
        <div className="mt-6 space-y-6">
          {/* 4 Scorecards */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {/* Card 1: Modified Duration */}
            <div className="rounded-2xl border border-black/10 bg-white/90 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Modified Duration
                </span>
                <Clock size={16} className="text-amber-600 dark:text-amber-400" />
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-black text-slate-900 dark:text-white">
                  {data.summary.modified_duration.toFixed(2)}
                </span>
                <span className="text-xs font-bold text-slate-500">Jahre</span>
              </div>
              <div className="mt-2">
                <span className={`rounded-md border px-2 py-0.5 text-[10px] font-black uppercase ${data.summary.duration_badge.tone}`}>
                  {data.summary.duration_badge.label}
                </span>
              </div>
            </div>

            {/* Card 2: DV01 */}
            <div className="rounded-2xl border border-black/10 bg-white/90 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Portfolio DV01 (PV01)
                </span>
                <Activity size={16} className="text-rose-600 dark:text-rose-400" />
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-black text-rose-700 dark:text-rose-400">
                  {data.summary.dv01_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}
                </span>
                <span className="text-xs font-bold text-slate-500">/ 1 bp</span>
              </div>
              <div className="mt-2 text-xs font-medium text-slate-500 dark:text-slate-400">
                Euro-Verlust bei +0,01% Zinsanstieg
              </div>
            </div>

            {/* Card 3: YTM */}
            <div className="rounded-2xl border border-black/10 bg-white/90 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Effektive Rendite (YTM)
                </span>
                <Percent size={16} className="text-emerald-600 dark:text-emerald-400" />
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-black text-emerald-700 dark:text-emerald-400">
                  {data.summary.ytm_pct.toFixed(2)}%
                </span>
                <span className="text-xs font-bold text-slate-500">p.a.</span>
              </div>
              <div className="mt-2 text-xs font-medium text-slate-500 dark:text-slate-400">
                Ø Credit Spread: <strong className="text-slate-800 dark:text-slate-200">+{data.summary.average_credit_spread_bps} bps</strong>
              </div>
            </div>

            {/* Card 4: Convexity */}
            <div className="rounded-2xl border border-black/10 bg-white/90 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Portfolio-Konvexität
                </span>
                <ShieldCheck size={16} className="text-amber-600 dark:text-amber-400" />
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-black text-slate-900 dark:text-white">
                  {data.summary.convexity.toFixed(2)}
                </span>
              </div>
              <div className="mt-2 text-xs font-medium text-slate-500 dark:text-slate-400">
                MacAulay Duration: <strong className="text-slate-800 dark:text-slate-200">{data.summary.macaulay_duration.toFixed(2)} Jahre</strong>
              </div>
            </div>
          </div>

          {/* Scenario Chart */}
          <div className="rounded-2xl border border-black/10 bg-white/80 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/80">
            <h3 className="text-sm font-black text-slate-900 dark:text-white">
              Zinskurven-Szenarien &amp; Preissensitivität
            </h3>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Auswirkung von EZB- und Fed-Zinsänderungen auf den Portfoliowert (inklusive Konvexitäts-Schutz)
            </p>

            <MeasuredChartFrame className="mt-4 w-full" minHeight={200}>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={scenarioChartData} margin={{ top: 20, right: 30, left: 10, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fontWeight: 700 }} />
                  <YAxis unit="%" tick={{ fontSize: 11 }} />
                  <ReferenceLine y={0} stroke="#94a3b8" />
                  <Tooltip
                    formatter={(value: any, name: any, item: any) => [
                      `${Number(value) >= 0 ? "+" : ""}${Number(value).toFixed(2)}% (${item.payload.delta_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })})`,
                      "Effekt"
                    ]}
                    contentStyle={{ backgroundColor: "#0f172a", borderRadius: "12px", border: "none", color: "#fff" }}
                  />
                  <Bar dataKey="price_change_pct" radius={[6, 6, 0, 0]}>
                    {scenarioChartData.map((entry, index) => (
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
              onClick={() => setActiveTab("scenarios")}
              className={`flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-black uppercase tracking-wider transition-all ${
                activeTab === "scenarios"
                  ? "border-amber-500 text-amber-800 dark:text-amber-300"
                  : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              <Sliders size={15} />
              Interaktiver Zins-Stresstest
            </button>

            <button
              onClick={() => setActiveTab("holdings")}
              className={`flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-black uppercase tracking-wider transition-all ${
                activeTab === "holdings"
                  ? "border-amber-500 text-amber-800 dark:text-amber-300"
                  : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              <Layers size={15} />
              Holdings Zins- &amp; Durationstabelle ({data.holdings.length})
            </button>

            <button
              onClick={() => setActiveTab("ratings")}
              className={`flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-black uppercase tracking-wider transition-all ${
                activeTab === "ratings"
                  ? "border-amber-500 text-amber-800 dark:text-amber-300"
                  : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              <ShieldCheck size={15} />
              Credit-Rating &amp; Spread-Radar
            </button>
          </div>

          {/* TAB 1: Interactive Yield Shift Slider */}
          {activeTab === "scenarios" && (
            <div className="rounded-2xl border border-black/10 bg-white/80 p-6 shadow-sm dark:border-white/10 dark:bg-slate-800/80">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h3 className="text-base font-black text-slate-900 dark:text-white flex items-center gap-2">
                    <Sliders size={18} className="text-amber-600 dark:text-amber-400" />
                    Zinskurven-Verschiebung (Parallel Yield Shift)
                  </h3>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                    Verschiebe das Marktzinsniveau (in Basispunkten) und simuliere den exakten Portfolio-Gewinn oder -Verlust nach Taylor 2. Ordnung.
                  </p>
                </div>

                {simulatedResult && (
                  <div className="rounded-xl border border-black/10 bg-white p-3.5 text-right dark:border-white/10 dark:bg-slate-900 shadow-sm">
                    <div className="text-[10px] font-bold text-slate-500">Simulierter Zinseffekt</div>
                    <div className={`text-xl font-black ${simulatedResult.delta_eur >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"}`}>
                      {simulatedResult.delta_eur >= 0 ? `+${simulatedResult.delta_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}` : simulatedResult.delta_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}
                    </div>
                    <div className={`text-xs font-bold ${simulatedResult.price_change_pct >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"}`}>
                      {simulatedResult.price_change_pct >= 0 ? `+${simulatedResult.price_change_pct.toFixed(2)}%` : `${simulatedResult.price_change_pct.toFixed(2)}%`}
                    </div>
                  </div>
                )}
              </div>

              <div className="mt-6 rounded-xl border border-black/10 bg-white/50 p-5 dark:border-white/10 dark:bg-slate-900/50">
                <div className="flex justify-between items-center text-xs font-black">
                  <span className="text-slate-700 dark:text-slate-300">Zinsänderung (Δy):</span>
                  <span className={customShiftBps >= 0 ? "text-rose-600 dark:text-rose-400 font-black text-sm" : "text-emerald-600 dark:text-emerald-400 font-black text-sm"}>
                    {customShiftBps >= 0 ? `+${customShiftBps} bps (+${(customShiftBps / 100).toFixed(2)}%)` : `${customShiftBps} bps (${(customShiftBps / 100).toFixed(2)}%)`}
                  </span>
                </div>
                <input
                  type="range"
                  min="-300"
                  max="300"
                  step="5"
                  value={customShiftBps}
                  onChange={(e) => setCustomShiftBps(parseInt(e.target.value))}
                  className="mt-4 w-full cursor-pointer accent-amber-600"
                />
                <div className="mt-2 flex justify-between text-[10px] text-slate-400 font-semibold">
                  <span>-300 bps (Extremer Zinssturz)</span>
                  <span>0 bps (Status Quo)</span>
                  <span>+300 bps (Historischer Zinsschock)</span>
                </div>
              </div>

              <div className="mt-4 flex justify-end">
                <button
                  onClick={() => setCustomShiftBps(0)}
                  className="text-xs font-bold text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 underline"
                >
                  Schieberegler auf 0 bps zurücksetzen
                </button>
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
                    <th className="p-3.5">Typ</th>
                    <th className="p-3.5 text-right">Gewicht %</th>
                    <th className="p-3.5 text-right">Positionswert</th>
                    <th className="p-3.5 text-right">YTM %</th>
                    <th className="p-3.5 text-right">Mod. Duration</th>
                    <th className="p-3.5 text-right">Konvexität</th>
                    <th className="p-3.5 text-right">DV01 (€)</th>
                    <th className="p-3.5 text-center">Rating</th>
                    <th className="p-3.5 text-right">Spread</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/5 dark:divide-white/5 font-semibold text-slate-800 dark:text-slate-200">
                  {data.holdings.map((h) => (
                    <tr key={h.ticker} className="hover:bg-amber-500/5 transition-colors">
                      <td className="p-3.5">
                        <button
                          onClick={() => onAnalyzeStock && onAnalyzeStock(h.ticker)}
                          className="font-black text-amber-700 hover:underline dark:text-amber-400 text-left"
                        >
                          {h.ticker}
                        </button>
                        <div className="text-[11px] text-slate-500 truncate max-w-[150px]">{h.name}</div>
                      </td>
                      <td className="p-3.5">
                        <span className="rounded-md border border-black/10 bg-black/5 px-2 py-0.5 text-[11px] font-bold text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">
                          {h.type}
                        </span>
                      </td>
                      <td className="p-3.5 text-right font-mono font-bold">{h.weight_pct.toFixed(1)}%</td>
                      <td className="p-3.5 text-right font-bold">
                        {h.value_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}
                      </td>
                      <td className="p-3.5 text-right font-mono text-emerald-700 dark:text-emerald-400 font-bold">
                        {h.ytm_pct.toFixed(2)}%
                      </td>
                      <td className="p-3.5 text-right font-mono font-bold text-amber-700 dark:text-amber-400">
                        {h.modified_duration.toFixed(1)} y
                      </td>
                      <td className="p-3.5 text-right font-mono">{h.convexity.toFixed(2)}</td>
                      <td className="p-3.5 text-right font-mono text-rose-700 dark:text-rose-400 font-bold">
                        {h.dv01_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}
                      </td>
                      <td className="p-3.5 text-center">
                        <span className="rounded-md border border-black/10 px-2 py-0.5 font-black text-[10px] uppercase">
                          {h.rating}
                        </span>
                      </td>
                      <td className="p-3.5 text-right font-mono text-slate-500">
                        +{h.credit_spread_bps} bps
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* TAB 3: Credit Rating Radar */}
          {activeTab === "ratings" && (
            <div className="grid gap-6 lg:grid-cols-12">
              <div className="lg:col-span-6 space-y-3">
                <h3 className="text-sm font-black text-slate-900 dark:text-white">
                  Bonitäts- und Rating-Verteilung
                </h3>
                <p className="text-xs text-slate-500">
                  Aufteilung des Portfolios nach Kreditwürdigkeit (Investment Grade vs. High Yield)
                </p>

                <div className="mt-3 space-y-2.5">
                  {data.rating_distribution.map((rb) => (
                    <div
                      key={rb.rating}
                      className="flex items-center justify-between rounded-xl border border-black/10 bg-white/80 p-3.5 dark:border-white/10 dark:bg-slate-800/80"
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-black text-sm text-slate-900 dark:text-white">{rb.rating}</span>
                      </div>
                      <div className="text-right">
                        <div className="text-sm font-black text-slate-900 dark:text-white">
                          {rb.weight_pct.toFixed(1)}%
                        </div>
                        <div className="text-[11px] text-slate-500">
                          {rb.value_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="lg:col-span-6">
                <div className="rounded-2xl border border-black/10 bg-white/80 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/80 space-y-3 text-xs">
                  <h3 className="text-sm font-black text-slate-900 dark:text-white">
                    Institutionelle Fixed-Income Formeln &amp; Leitfaden
                  </h3>
                  <div className="space-y-2 text-slate-600 dark:text-slate-300">
                    <p>
                      <strong>Modified Duration (ModD):</strong> Misst den prozentualen Kursverlust bei einem Zinsanstieg um 100 bps (+1%). Berechnet als MacAulay-Duration geteilt durch (1 + YTM).
                    </p>
                    <p>
                      <strong>DV01 (Dollar Value of a 01):</strong> Der absolute Euro-Betrag, den das Portfolio gewinnt oder verliert, wenn die Zinskurve sich um exakt 1 Basispunkt (0,01%) verschiebt.
                    </p>
                    <p>
                      <strong>Konvexitäts-Schutz:</strong> Die Krümmung der Anleihenkurve bewirkt, dass bei Zinssenkungen die Kursgewinne größer sind als die Kursverluste bei Zinsanstiegen gleicher Höhe.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
