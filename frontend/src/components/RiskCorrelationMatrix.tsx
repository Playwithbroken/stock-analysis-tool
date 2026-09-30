import React, { useEffect, useState } from "react";
import {
  ShieldAlert,
  Info,
  Layers,
  RefreshCw,
  Maximize2,
  Minimize2,
  Sparkles,
  AlertTriangle,
  CheckCircle2,
  Scale
} from "lucide-react";

interface CorrelationPair {
  ticker_a: string;
  name_a: string;
  ticker_b: string;
  name_b: string;
  correlation: number;
}

interface RiskCluster {
  cluster_id: number;
  size: number;
  tickers: string[];
  names: string[];
  avg_inner_correlation: number;
  is_tight_cluster: boolean;
}

interface RiskParityWeight {
  ticker: string;
  name: string;
  current_weight_pct: number;
  risk_parity_weight_pct: number;
  delta_pct: number;
  annual_volatility_pct: number;
}

interface CorrelationResponse {
  timeframe: string;
  labels: string[];
  names: string[];
  matrix: number[][];
  diversification_score: number;
  average_correlation: number;
  effective_bets: number;
  total_assets: number;
  top_correlation_pairs?: CorrelationPair[];
  best_diversifiers?: CorrelationPair[];
  risk_clusters?: RiskCluster[];
  risk_parity_weights?: RiskParityWeight[];
  error?: string;
}

interface RiskMatrixProps {
  portfolioId: string;
}

export default function RiskCorrelationMatrix({ portfolioId }: RiskMatrixProps) {
  const [data, setData] = useState<CorrelationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [timeframe, setTimeframe] = useState<"30d" | "90d" | "1y" | "3y">("1y");
  const [activeTab, setActiveTab] = useState<"matrix" | "clusters" | "parity">("matrix");
  const [hoveredCell, setHoveredCell] = useState<{ row: number; col: number } | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);

  const fetchData = async (tf: string) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/portfolio/${portfolioId}/correlation?timeframe=${tf}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
    } catch (e) {
      console.error("Failed to load correlation data:", e);
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (portfolioId) {
      fetchData(timeframe);
    }
  }, [portfolioId, timeframe]);

  if (loading && !data) {
    return (
      <div className="surface-panel rounded-[2rem] p-6 text-center">
        <div className="flex flex-col items-center justify-center gap-3 py-10">
          <RefreshCw className="h-6 w-6 animate-spin text-cyan-600 dark:text-cyan-400" />
          <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">
            Berechne institutionelle Korrelationsmatrix & Risikocluster...
          </p>
        </div>
      </div>
    );
  }

  if (!data || data.error || !data.labels || data.labels.length < 2) {
    return (
      <div className="surface-panel rounded-[2rem] p-6 text-center text-xs font-medium text-slate-700 dark:text-slate-300">
        <ShieldAlert size={28} className="mx-auto mb-2 text-amber-500" />
        Füge mindestens zwei unterschiedliche Assets hinzu, um die Cross-Asset Korrelation und
        Klumpenrisiken zu berechnen.
      </div>
    );
  }

  const getScoreBadge = (score: number) => {
    if (score >= 75) {
      return {
        label: "Sehr hoch",
        color: "text-emerald-700 dark:text-emerald-400 bg-emerald-500/15 border-emerald-500/30",
        icon: CheckCircle2,
      };
    }
    if (score >= 50) {
      return {
        label: "Solide",
        color: "text-blue-700 dark:text-blue-400 bg-blue-500/15 border-blue-500/30",
        icon: CheckCircle2,
      };
    }
    if (score >= 35) {
      return {
        label: "Moderat",
        color: "text-amber-700 dark:text-amber-400 bg-amber-500/15 border-amber-500/30",
        icon: AlertTriangle,
      };
    }
    return {
      label: "Klumpenrisiko",
      color: "text-red-700 dark:text-red-400 bg-red-500/15 border-red-500/30",
      icon: ShieldAlert,
    };
  };

  const getCellClass = (val: number, isDiag: boolean) => {
    if (isDiag) {
      return "bg-slate-200/80 dark:bg-slate-700/60 text-slate-600 dark:text-slate-300 font-bold";
    }
    if (val >= 0.70) {
      return "bg-rose-500/25 text-rose-900 dark:bg-rose-500/30 dark:text-rose-200 font-bold border border-rose-500/40";
    }
    if (val >= 0.45) {
      return "bg-amber-500/20 text-amber-900 dark:bg-amber-500/25 dark:text-amber-200 font-semibold border border-amber-500/30";
    }
    if (val >= 0.15) {
      return "bg-slate-100 text-slate-800 dark:bg-slate-800/80 dark:text-slate-200 border border-slate-200 dark:border-slate-700";
    }
    if (val >= 0.0) {
      return "bg-teal-500/15 text-teal-900 dark:bg-teal-500/20 dark:text-teal-200 font-semibold border border-teal-500/25";
    }
    return "bg-emerald-500/25 text-emerald-900 dark:bg-emerald-500/30 dark:text-emerald-200 font-bold border border-emerald-500/40";
  };

  const scoreBadge = getScoreBadge(data.diversification_score);
  const ScoreIcon = scoreBadge.icon;

  return (
    <div
      className={`surface-panel rounded-[2rem] p-6 transition-all duration-300 ${
        isExpanded ? "fixed inset-4 z-50 overflow-y-auto bg-slate-900/95 shadow-2xl backdrop-blur-xl" : ""
      }`}
    >
      {/* Header & Controls */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-black/8 pb-4 dark:border-white/10">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-cyan-500/10 p-2.5 text-cyan-600 dark:bg-cyan-500/20 dark:text-cyan-400">
            <Layers size={20} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold text-slate-900 dark:text-white">
                Cross-Asset Korrelation & Risikocluster
              </h3>
              <span className="rounded-full bg-cyan-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-cyan-700 dark:text-cyan-300">
                Risk Engine
              </span>
            </div>
            <p className="text-xs text-slate-600 dark:text-slate-400">
              Klumpenrisiko-Erkennung, effektive Portfolio-Wetten und Risk-Parity Allokation
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Timeframe Switcher */}
          <div className="flex rounded-xl border border-black/10 bg-slate-100 p-1 dark:border-white/10 dark:bg-slate-800">
            {(["30d", "90d", "1y", "3y"] as const).map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition-all ${
                  timeframe === tf
                    ? "bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-white"
                    : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
                }`}
              >
                {tf === "30d" ? "30T" : tf === "90d" ? "90T" : tf === "1y" ? "1J" : "3J"}
              </button>
            ))}
          </div>

          {/* Expand / Minimize Button */}
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
        <div className="rounded-2xl border border-black/8 bg-white/70 p-3.5 shadow-sm dark:border-white/10 dark:bg-slate-800/60">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Diversifikations-Score
          </div>
          <div className="mt-1.5 flex items-baseline gap-2">
            <span className="text-2xl font-black text-slate-900 dark:text-white">
              {data.diversification_score}
            </span>
            <span className="text-xs text-slate-500">/ 100</span>
          </div>
          <div className="mt-2 flex items-center gap-1.5">
            <span
              className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold ${scoreBadge.color}`}
            >
              <ScoreIcon size={11} />
              {scoreBadge.label}
            </span>
          </div>
        </div>

        <div className="rounded-2xl border border-black/8 bg-white/70 p-3.5 shadow-sm dark:border-white/10 dark:bg-slate-800/60">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Ø Korrelation (ρ)
          </div>
          <div className="mt-1.5 flex items-baseline gap-1">
            <span
              className={`text-2xl font-black ${
                data.average_correlation >= 0.65
                  ? "text-rose-600 dark:text-rose-400"
                  : data.average_correlation >= 0.40
                  ? "text-amber-600 dark:text-amber-400"
                  : "text-emerald-600 dark:text-emerald-400"
              }`}
            >
              {data.average_correlation > 0 ? `+${data.average_correlation.toFixed(2)}` : data.average_correlation.toFixed(2)}
            </span>
          </div>
          <p className="mt-2 text-[10px] text-slate-500 dark:text-slate-400">
            {data.average_correlation >= 0.65
              ? "Hohe Gleichförmigkeit"
              : data.average_correlation >= 0.40
              ? "Typischer Marktdurchschnitt"
              : "Exzellente Unabhängigkeit"}
          </p>
        </div>

        <div className="rounded-2xl border border-black/8 bg-white/70 p-3.5 shadow-sm dark:border-white/10 dark:bg-slate-800/60">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Effektive Wetten (N_eff)
          </div>
          <div className="mt-1.5 flex items-baseline gap-1.5">
            <span className="text-2xl font-black text-cyan-600 dark:text-cyan-400">
              {data.effective_bets.toFixed(1)}
            </span>
            <span className="text-xs text-slate-500">von {data.total_assets}</span>
          </div>
          <p className="mt-2 text-[10px] text-slate-500 dark:text-slate-400">
            Reale risikotragende Einheiten
          </p>
        </div>

        <div className="rounded-2xl border border-black/8 bg-white/70 p-3.5 shadow-sm dark:border-white/10 dark:bg-slate-800/60">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Stärkstes Paar
          </div>
          {data.top_correlation_pairs && data.top_correlation_pairs.length > 0 ? (
            <div>
              <div className="mt-1 text-xs font-bold text-slate-900 dark:text-white">
                {data.top_correlation_pairs[0].ticker_a} ↔ {data.top_correlation_pairs[0].ticker_b}
              </div>
              <div className="mt-1.5 flex items-center gap-1">
                <span className="rounded-full bg-rose-500/20 px-2 py-0.5 text-[11px] font-bold text-rose-700 dark:text-rose-300">
                  ρ = +{data.top_correlation_pairs[0].correlation.toFixed(2)}
                </span>
                <span className="text-[10px] text-slate-500">Klumpen</span>
              </div>
            </div>
          ) : (
            <p className="mt-2 text-xs text-slate-500">Keine Daten verfügbar</p>
          )}
        </div>
      </div>

      {/* Navigation Sub-Tabs */}
      <div className="mb-5 flex gap-2 border-b border-black/6 pb-2 dark:border-white/10">
        <button
          onClick={() => setActiveTab("matrix")}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
            activeTab === "matrix"
              ? "bg-cyan-500/15 text-cyan-700 dark:bg-cyan-500/25 dark:text-cyan-300"
              : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
          }`}
        >
          <Layers size={14} />
          Korrelations-Matrix
        </button>

        <button
          onClick={() => setActiveTab("clusters")}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
            activeTab === "clusters"
              ? "bg-cyan-500/15 text-cyan-700 dark:bg-cyan-500/25 dark:text-cyan-300"
              : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
          }`}
        >
          <Sparkles size={14} />
          Risiko-Cluster ({data.risk_clusters?.length || 0})
        </button>

        <button
          onClick={() => setActiveTab("parity")}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
            activeTab === "parity"
              ? "bg-cyan-500/15 text-cyan-700 dark:bg-cyan-500/25 dark:text-cyan-300"
              : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
          }`}
        >
          <Scale size={14} />
          Risk-Parity Rebalancer
        </button>
      </div>

      {/* Tab 1: Heatmap Matrix */}
      {activeTab === "matrix" && (
        <div>
          <div className="overflow-x-auto rounded-2xl border border-black/8 bg-white/40 p-4 dark:border-white/10 dark:bg-slate-900/40">
            <table className="w-full border-separate border-spacing-1.5 text-center">
              <thead>
                <tr>
                  <th className="p-2 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                    Asset
                  </th>
                  {data.labels.map((label, cIdx) => (
                    <th
                      key={label}
                      className={`p-2 text-[11px] font-bold uppercase tracking-wider transition-colors ${
                        hoveredCell?.col === cIdx
                          ? "rounded-lg bg-cyan-500/20 text-cyan-700 dark:text-cyan-300"
                          : "text-slate-700 dark:text-slate-300"
                      }`}
                    >
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.labels.map((rowLabel, rIdx) => (
                  <tr key={rowLabel}>
                    <td
                      className={`whitespace-nowrap p-2 text-left text-xs font-bold transition-colors ${
                        hoveredCell?.row === rIdx
                          ? "rounded-lg bg-cyan-500/20 text-cyan-700 dark:text-cyan-300"
                          : "text-slate-800 dark:text-slate-200"
                      }`}
                    >
                      {rowLabel}
                    </td>
                    {data.matrix[rIdx].map((val, cIdx) => {
                      const isDiag = rIdx === cIdx;
                      return (
                        <td
                          key={cIdx}
                          onMouseEnter={() => setHoveredCell({ row: rIdx, col: cIdx })}
                          onMouseLeave={() => setHoveredCell(null)}
                          className={`group relative cursor-pointer rounded-xl p-3 text-xs font-mono transition-transform hover:z-10 hover:scale-110 shadow-xs ${getCellClass(
                            val,
                            isDiag
                          )}`}
                          title={`${rowLabel} ↔ ${data.labels[cIdx]}: ${val.toFixed(2)}`}
                        >
                          {isDiag ? "1.00" : val > 0 ? `+${val.toFixed(2)}` : val.toFixed(2)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Color Scale Legend */}
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-black/8 bg-white/60 px-4 py-2.5 dark:border-white/10 dark:bg-slate-800/40">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Korrelations-Skala:
            </span>
            <div className="flex flex-wrap items-center gap-3 text-xs font-semibold">
              <span className="flex items-center gap-1.5">
                <span className="h-3 w-3 rounded-sm bg-emerald-500" />
                <span className="text-slate-700 dark:text-slate-300">&lt; 0.0 (Negativ)</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-3 w-3 rounded-sm bg-teal-500" />
                <span className="text-slate-700 dark:text-slate-300">0.0 - 0.2 (Unkorreliert)</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-3 w-3 rounded-sm bg-amber-500" />
                <span className="text-slate-700 dark:text-slate-300">0.45 - 0.7 (Moderat)</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-3 w-3 rounded-sm bg-rose-500" />
                <span className="text-slate-700 dark:text-slate-300">&gt; 0.7 (Klumpenrisiko)</span>
              </span>
            </div>
          </div>

          {/* Top Duplicates & Best Diversifiers Grid */}
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            {/* Top Duplicates */}
            <div className="rounded-2xl border border-rose-500/20 bg-rose-500/5 p-4 dark:border-rose-500/30 dark:bg-rose-500/10">
              <h4 className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-rose-800 dark:text-rose-300">
                <ShieldAlert size={15} />
                Höchste Korrelations-Paare (Redundanz)
              </h4>
              {data.top_correlation_pairs && data.top_correlation_pairs.length > 0 ? (
                <div className="space-y-2">
                  {data.top_correlation_pairs.slice(0, 3).map((pair, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between rounded-xl bg-white/70 px-3 py-2 text-xs dark:bg-slate-800/70"
                    >
                      <div>
                        <span className="font-bold text-slate-900 dark:text-white">
                          {pair.ticker_a}
                        </span>
                        <span className="mx-1.5 text-slate-400">↔</span>
                        <span className="font-bold text-slate-900 dark:text-white">
                          {pair.ticker_b}
                        </span>
                      </div>
                      <span className="rounded-md bg-rose-500/20 px-2 py-0.5 font-mono font-bold text-rose-800 dark:text-rose-300">
                        +{pair.correlation.toFixed(2)}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Keine auffällig hohen Korrelations-Paare (&gt; 0.65) gefunden.
                </p>
              )}
            </div>

            {/* Best Diversifiers */}
            <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-4 dark:border-emerald-500/30 dark:bg-emerald-500/10">
              <h4 className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-emerald-800 dark:text-emerald-300">
                <Sparkles size={15} />
                Beste Diversifizierer (Geringe Kopplung)
              </h4>
              {data.best_diversifiers && data.best_diversifiers.length > 0 ? (
                <div className="space-y-2">
                  {data.best_diversifiers.slice(0, 3).map((pair, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between rounded-xl bg-white/70 px-3 py-2 text-xs dark:bg-slate-800/70"
                    >
                      <div>
                        <span className="font-bold text-slate-900 dark:text-white">
                          {pair.ticker_a}
                        </span>
                        <span className="mx-1.5 text-slate-400">↔</span>
                        <span className="font-bold text-slate-900 dark:text-white">
                          {pair.ticker_b}
                        </span>
                      </div>
                      <span className="rounded-md bg-emerald-500/20 px-2 py-0.5 font-mono font-bold text-emerald-800 dark:text-emerald-300">
                        {pair.correlation > 0 ? `+${pair.correlation.toFixed(2)}` : pair.correlation.toFixed(2)}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Alle Positionen weisen mittlere bis hohe Korrelation auf.
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Risk Clusters */}
      {activeTab === "clusters" && (
        <div className="space-y-4">
          <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 p-4 text-xs text-blue-900 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-200">
            <div className="flex items-start gap-2.5">
              <Info size={16} className="mt-0.5 shrink-0 text-blue-600 dark:text-blue-400" />
              <p>
                <strong>Hierarchische Risikocluster</strong> gruppieren Assets, die in Stressphasen
                gemeinsam fallen. Ein gesundes Portfolio verteilt das Kapital auf mehrere unabhängige
                Cluster statt nur auf einen großen Block.
              </p>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {data.risk_clusters && data.risk_clusters.length > 0 ? (
              data.risk_clusters.map((cluster) => (
                <div
                  key={cluster.cluster_id}
                  className={`rounded-2xl border p-4 shadow-sm transition-all ${
                    cluster.is_tight_cluster
                      ? "border-rose-500/30 bg-rose-500/5 dark:border-rose-500/40 dark:bg-rose-500/10"
                      : "border-black/8 bg-white/70 dark:border-white/10 dark:bg-slate-800/60"
                  }`}
                >
                  <div className="flex items-center justify-between border-b border-black/6 pb-2.5 dark:border-white/10">
                    <div className="flex items-center gap-2">
                      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-cyan-500/20 text-xs font-black text-cyan-700 dark:text-cyan-300">
                        #{cluster.cluster_id}
                      </span>
                      <span className="text-xs font-bold text-slate-900 dark:text-white">
                        Risiko-Gruppe ({cluster.size} {cluster.size === 1 ? "Asset" : "Assets"})
                      </span>
                    </div>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                        cluster.is_tight_cluster
                          ? "bg-rose-500/20 text-rose-800 dark:text-rose-300"
                          : "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300"
                      }`}
                    >
                      Ø ρ = +{cluster.avg_inner_correlation.toFixed(2)}
                    </span>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    {cluster.tickers.map((t, idx) => (
                      <span
                        key={t}
                        className="inline-flex items-center gap-1 rounded-lg border border-black/10 bg-white px-2.5 py-1 text-xs font-semibold text-slate-800 shadow-2xs dark:border-white/10 dark:bg-slate-700 dark:text-slate-200"
                      >
                        <span className="font-bold">{t}</span>
                        {cluster.names[idx] && cluster.names[idx] !== t && (
                          <span className="text-[10px] text-slate-600 dark:text-slate-400">
                            ({cluster.names[idx].slice(0, 14)})
                          </span>
                        )}
                      </span>
                    ))}
                  </div>

                  {cluster.is_tight_cluster && (
                    <div className="mt-3 flex items-center gap-1.5 text-[11px] font-semibold text-rose-700 dark:text-rose-300">
                      <AlertTriangle size={13} />
                      Hohes Gleichlauf-Risiko (Cluster bewegt sich homogen)
                    </div>
                  )}
                </div>
              ))
            ) : (
              <p className="text-xs text-slate-500">Keine Cluster identifiziert.</p>
            )}
          </div>
        </div>
      )}

      {/* Tab 3: Risk-Parity Allocation */}
      {activeTab === "parity" && (
        <div className="space-y-4">
          <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4 text-xs text-emerald-900 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200">
            <div className="flex items-start gap-2.5">
              <Scale size={16} className="mt-0.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
              <p>
                <strong>Risk-Parity (Inverse Volatilitätsgewichtung):</strong> Gleicht den
                Risikobeitrag jedes Titels an, sodass volatile Positionen gedrosselt und stabile
                Werte gestärkt werden. Dies minimiert historische Drawdowns signifikant.
              </p>
            </div>
          </div>

          <div className="overflow-x-auto rounded-2xl border border-black/8 bg-white/70 shadow-xs dark:border-white/10 dark:bg-slate-900/60">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-black/8 bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:border-white/10 dark:bg-slate-800/60 dark:text-slate-400">
                  <th className="p-3">Asset</th>
                  <th className="p-3 text-right">Volatilität p.a.</th>
                  <th className="p-3 text-right">Aktuelles Gewicht</th>
                  <th className="p-3 text-right">Risk-Parity Ziel</th>
                  <th className="p-3 text-right">Delta / Anpassung</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/6 dark:divide-white/6">
                {data.risk_parity_weights && data.risk_parity_weights.length > 0 ? (
                  data.risk_parity_weights.map((row) => (
                    <tr key={row.ticker} className="hover:bg-black/[0.02] dark:hover:bg-white/[0.02]">
                      <td className="p-3">
                        <div className="font-bold text-slate-900 dark:text-white">{row.ticker}</div>
                        <div className="text-[10px] text-slate-600 dark:text-slate-400">{row.name}</div>
                      </td>
                      <td className="p-3 text-right font-mono font-semibold text-slate-700 dark:text-slate-300">
                        {row.annual_volatility_pct.toFixed(1)}%
                      </td>
                      <td className="p-3 text-right font-mono font-bold text-slate-900 dark:text-white">
                        {row.current_weight_pct.toFixed(1)}%
                      </td>
                      <td className="p-3 text-right font-mono font-bold text-cyan-600 dark:text-cyan-400">
                        {row.risk_parity_weight_pct.toFixed(1)}%
                      </td>
                      <td className="p-3 text-right font-mono font-bold">
                        <span
                          className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs ${
                            row.delta_pct > 0.5
                              ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
                              : row.delta_pct < -0.5
                              ? "bg-rose-500/15 text-rose-700 dark:text-rose-400"
                              : "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300"
                          }`}
                        >
                          {row.delta_pct > 0 ? `+${row.delta_pct.toFixed(1)}%` : `${row.delta_pct.toFixed(1)}%`}
                        </span>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="p-4 text-center text-slate-500">
                      Keine Daten verfügbar
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Footer Info Box */}
      <div className="mt-6 flex items-center gap-3 rounded-xl border border-black/8 bg-white/70 p-3.5 text-xs text-slate-700 dark:border-white/10 dark:bg-slate-800/60 dark:text-slate-300">
        <Info size={16} className="shrink-0 text-cyan-600 dark:text-cyan-400" />
        <p className="text-[11px] leading-relaxed">
          <strong className="text-slate-900 dark:text-white">Institutionelle Faustregel:</strong> Ein
          starkes Portfolio erzielt einen Diversifikations-Score von{" "}
          <span className="font-bold text-emerald-700 dark:text-emerald-400">&gt; 65</span> und eine
          durchschnittliche Korrelation von{" "}
          <span className="font-bold text-cyan-700 dark:text-cyan-400">&lt; 0.50</span>. Assets mit
          Korrelationen über 0.70 bieten kaum zusätzliche Streuung im Portfolio.
        </p>
      </div>
    </div>
  );
}

