import React, { useEffect, useState } from "react";
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Tooltip,
} from "recharts";
import {
  Sparkles,
  ShieldCheck,
  AlertTriangle,
  Flame,
  Info,
  Layers,
  RefreshCw,
  Sliders,
  CheckCircle2,
  TrendingUp,
  Compass,
  ArrowRight,
  ExternalLink,
} from "lucide-react";
import MeasuredChartFrame from "./MeasuredChartFrame";

interface FactorDetail {
  score: number;
  z_score: number;
  benchmark_score: number;
  delta: number;
  label: string;
}

interface PositionFactor {
  ticker: string;
  name: string;
  weight_pct: number;
  position_value: number;
  factors: {
    value: { score: number; z_score: number };
    quality: { score: number; z_score: number };
    momentum: { score: number; z_score: number };
    low_volatility: { score: number; z_score: number };
    size: { score: number; raw: { tier: string } };
    shareholder_yield: { score: number };
  };
  style_box: {
    cell: string;
    size_category: string;
    value_category: string;
  };
}

interface FactorAnalysisResponse {
  holdings_count: number;
  total_value: number;
  portfolio_factors: Record<string, FactorDetail>;
  benchmark_factors: Record<string, number>;
  style_box_grid: Record<string, number>;
  dominant_style: string;
  radar_data: Array<{
    factor: string;
    key: string;
    portfolio: number;
    benchmark: number;
    fullMark: number;
  }>;
  positions: PositionFactor[];
  regime_risks: Array<{
    type: "positive" | "warning" | "caution";
    title: string;
    description: string;
  }>;
  insights: string[];
}

interface Props {
  portfolioId: string;
  onAnalyzeStock?: (ticker: string) => void;
  onClose?: () => void;
}

export default function FactorDecompositionRadar({
  portfolioId,
  onAnalyzeStock,
  onClose,
}: Props) {
  const [data, setData] = useState<FactorAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedHolding, setSelectedHolding] = useState<PositionFactor | null>(null);

  const fetchFactorAnalysis = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/portfolio/${portfolioId}/factor-analysis`);
      if (!res.ok) {
        throw new Error(`Fehler bei der Faktor-Analyse (${res.status})`);
      }
      const json: FactorAnalysisResponse = await res.json();
      setData(json);
      if (json.positions && json.positions.length > 0) {
        setSelectedHolding(json.positions[0]);
      }
    } catch (err: any) {
      setError(err?.message || "Faktor-Attribution konnte nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (portfolioId) {
      fetchFactorAnalysis();
    }
  }, [portfolioId]);

  // Style Box 3x3 Grid Config
  const sizeRows = ["Large", "Mid", "Small"];
  const valueCols = ["Value", "Blend", "Growth"];

  const getZScoreTone = (z: number) => {
    if (z >= 1.0) return "text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/20";
    if (z <= -1.0) return "text-amber-600 dark:text-amber-400 bg-amber-500/10 border-amber-500/20";
    return "text-slate-600 dark:text-slate-300 bg-black/5 dark:bg-white/5 border-black/8 dark:border-white/10";
  };

  return (
    <div className="surface-panel overflow-hidden rounded-[2.2rem] border border-black/8 bg-white/80 p-5 shadow-xl backdrop-blur-md dark:border-white/10 dark:bg-[#12141c]/90 sm:p-7">
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-black/6 pb-5 dark:border-white/8">
        <div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-purple-500/30 bg-purple-500/10 px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.2em] text-purple-600 dark:text-purple-400">
              <Compass size={13} />
              Fama-French & Barra Modell
            </span>
            <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-sky-600 dark:text-sky-400">
              Smart Beta Radar
            </span>
          </div>
          <h2 className="mt-2 text-2xl font-black tracking-tight text-slate-900 dark:text-white sm:text-3xl">
            Faktor-Attribution & Style Box
          </h2>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 sm:text-sm">
            Institutionelle Risikodekomposition in 6 Smart-Beta-Faktoren (Value, Quality, Momentum, Low-Beta, Size, Yield)
            gegen die globale Benchmark (MSCI World).
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={fetchFactorAnalysis}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-xl border border-black/10 bg-black/5 px-3 py-2 text-xs font-bold text-slate-700 hover:bg-black/10 dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:hover:bg-white/10"
          >
            <RefreshCw size={13} className={loading ? "animate-spin text-purple-500" : ""} />
            Aktualisieren
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

      {/* Main Dual Grid: Radar Chart + Morningstar 9-Grid Style Box */}
      {data && (
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          {/* 1. Radar Chart (6-Factor Decomposition) */}
          <div className="rounded-2xl border border-black/6 bg-white/60 p-5 dark:border-white/8 dark:bg-white/[0.02]">
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs font-extrabold uppercase tracking-wider text-slate-700 dark:text-slate-200">
                Faktor-Exposition vs. Benchmark (MSCI World)
              </div>
              <div className="flex items-center gap-3 text-[11px]">
                <span className="flex items-center gap-1">
                  <span className="h-2.5 w-2.5 rounded-full bg-sky-500" />
                  <span className="font-semibold text-slate-700 dark:text-slate-200">Portfolio</span>
                </span>
                <span className="flex items-center gap-1">
                  <span className="h-2.5 w-2.5 rounded-full bg-slate-400" />
                  <span className="text-slate-500 dark:text-slate-400">Benchmark (50)</span>
                </span>
              </div>
            </div>

            <MeasuredChartFrame className="h-[320px] w-full" minHeight={320}>
              {({ w, h }) => (
                <RadarChart data={data.radar_data} width={w} height={h} margin={{ top: 15, right: 25, bottom: 15, left: 25 }}>
                  <PolarGrid stroke="rgba(148, 163, 184, 0.2)" />
                  <PolarAngleAxis
                    dataKey="factor"
                    tick={{ fill: "#94a3b8", fontSize: 11, fontWeight: 700 }}
                  />
                  <PolarRadiusAxis
                    angle={30}
                    domain={[0, 100]}
                    stroke="#94a3b8"
                    tick={{ fill: "#94a3b8", fontSize: 9 }}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload || !payload.length) return null;
                      const item: any = payload[0]?.payload;
                      return (
                        <div className="rounded-xl border border-black/10 bg-white/95 p-3 text-xs shadow-xl backdrop-blur-md dark:border-white/10 dark:bg-slate-900/95 dark:text-white">
                          <div className="font-bold border-b border-black/8 pb-1 mb-2 dark:border-white/10">
                            {item.factor}
                          </div>
                          <div className="space-y-1">
                            <div className="flex justify-between gap-4 text-sky-500 font-bold">
                              <span>Portfolio:</span>
                              <span>{item.portfolio} / 100</span>
                            </div>
                            <div className="flex justify-between gap-4 text-slate-500 dark:text-slate-400">
                              <span>Benchmark:</span>
                              <span>{item.benchmark} / 100</span>
                            </div>
                            <div className="flex justify-between gap-4 text-xs font-semibold pt-1 border-t border-black/6 dark:border-white/6">
                              <span>Abweichung:</span>
                              <span className={item.portfolio >= item.benchmark ? "text-emerald-500" : "text-amber-500"}>
                                {(item.portfolio - item.benchmark > 0 ? "+" : "") + (item.portfolio - item.benchmark).toFixed(1)} Pkt.
                              </span>
                            </div>
                          </div>
                        </div>
                      );
                    }}
                  />
                  {/* Benchmark Outline */}
                  <Radar
                    name="Benchmark"
                    dataKey="benchmark"
                    stroke="#94a3b8"
                    strokeWidth={1.5}
                    strokeDasharray="3 3"
                    fill="#94a3b8"
                    fillOpacity={0.15}
                  />
                  {/* Portfolio Radar */}
                  <Radar
                    name="Portfolio"
                    dataKey="portfolio"
                    stroke="#0284c7"
                    strokeWidth={2.5}
                    fill="#0ea5e9"
                    fillOpacity={0.45}
                  />
                </RadarChart>
              )}
            </MeasuredChartFrame>

            {/* Factor Z-Score Bar Pills */}
            <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
              {Object.entries(data.portfolio_factors).map(([k, factor]) => (
                <div
                  key={k}
                  className="rounded-xl border border-black/6 bg-white/70 p-2.5 dark:border-white/8 dark:bg-white/[0.04]"
                >
                  <div className="truncate text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                    {factor.label}
                  </div>
                  <div className="mt-1 flex items-baseline justify-between">
                    <span className="text-sm font-black text-slate-900 dark:text-white">
                      {factor.score}
                    </span>
                    <span
                      className={`rounded-md border px-1.5 py-0.5 text-[10px] font-extrabold ${getZScoreTone(
                        factor.z_score
                      )}`}
                    >
                      {factor.z_score > 0 ? `+${factor.z_score}` : factor.z_score}σ
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 2. Morningstar 9-Grid Style Box */}
          <div className="rounded-2xl border border-black/6 bg-white/60 p-5 dark:border-white/8 dark:bg-white/[0.02]">
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="text-xs font-extrabold uppercase tracking-wider text-slate-700 dark:text-slate-200">
                  Morningstar 9-Grid Style Box
                </div>
                <div className="text-[11px] text-slate-500 dark:text-slate-400">
                  Dominanter Stil: <span className="font-bold text-sky-600 dark:text-sky-400">{data.dominant_style}</span>
                </div>
              </div>
              <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-2.5 py-1 text-[10px] font-bold text-sky-600 dark:text-sky-400">
                100 % Allokation
              </span>
            </div>

            {/* 3x3 Visual Grid */}
            <div className="grid grid-cols-3 gap-2">
              {sizeRows.map((size) =>
                valueCols.map((val) => {
                  const cellKey = `${size} ${val}`;
                  const pct = data.style_box_grid[cellKey] || 0;
                  const isDominant = data.dominant_style === cellKey;
                  return (
                    <div
                      key={cellKey}
                      className={`relative flex flex-col justify-between rounded-xl border p-3 transition-all ${
                        isDominant
                          ? "border-sky-500/50 bg-sky-500/15 shadow-md shadow-sky-500/10 dark:bg-sky-500/20"
                          : pct > 0
                          ? "border-black/10 bg-white/80 dark:border-white/10 dark:bg-white/5"
                          : "border-black/5 bg-black/[0.01] opacity-50 dark:border-white/5 dark:bg-white/[0.01]"
                      }`}
                    >
                      <div className="flex justify-between items-start">
                        <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                          {size.slice(0, 1)}/{val.slice(0, 1)}
                        </span>
                        {isDominant && (
                          <span className="h-2 w-2 rounded-full bg-sky-500 animate-pulse" />
                        )}
                      </div>
                      <div className="mt-3">
                        <div className="text-base font-black text-slate-900 dark:text-white">
                          {pct}%
                        </div>
                        <div className="text-[9px] font-semibold text-slate-500 dark:text-slate-400 truncate">
                          {size} {val}
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            {/* Regime & Macro Diagnosis Card */}
            <div className="mt-4 space-y-2.5">
              <div className="text-[11px] font-extrabold uppercase tracking-wider text-slate-600 dark:text-slate-400">
                Regime- & Makro-Diagnose
              </div>
              {data.regime_risks.map((risk, i) => (
                <div
                  key={i}
                  className={`rounded-xl border p-3 text-xs ${
                    risk.type === "warning"
                      ? "border-amber-500/30 bg-amber-500/10 text-amber-900 dark:text-amber-200"
                      : risk.type === "caution"
                      ? "border-rose-500/30 bg-rose-500/10 text-rose-900 dark:text-rose-200"
                      : "border-emerald-500/30 bg-emerald-500/10 text-emerald-900 dark:text-emerald-200"
                  }`}
                >
                  <div className="font-bold flex items-center gap-1.5">
                    {risk.type === "warning" || risk.type === "caution" ? (
                      <AlertTriangle size={14} className="shrink-0" />
                    ) : (
                      <ShieldCheck size={14} className="shrink-0" />
                    )}
                    {risk.title}
                  </div>
                  <div className="mt-1 text-[11px] leading-relaxed opacity-90">{risk.description}</div>
                </div>
              ))}

              {data.insights.length > 0 && (
                <div className="rounded-xl border border-sky-500/20 bg-sky-500/[0.06] p-3 text-xs text-sky-950 dark:text-sky-200">
                  <div className="font-bold flex items-center gap-1.5 text-sky-700 dark:text-sky-400">
                    <Sparkles size={14} /> Handlungsimpuls
                  </div>
                  <p className="mt-1 text-[11px] leading-relaxed">{data.insights[0]}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 3. Holdings Factor Attribution Table */}
      {data?.positions && (
        <div className="mt-6 rounded-2xl border border-black/6 bg-white/60 p-5 dark:border-white/8 dark:bg-white/[0.02]">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="text-xs font-extrabold uppercase tracking-wider text-slate-700 dark:text-slate-200">
                Einzelwert-Faktor-Attribution ({data.positions.length} Positionen)
              </div>
              <div className="text-[11px] text-slate-500 dark:text-slate-400">
                Klicke auf einen Wert, um die Detailfaktoren zu analysieren.
              </div>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-black/6 bg-black/[0.02] text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:border-white/8 dark:bg-white/[0.02] dark:text-slate-400">
                <tr>
                  <th className="p-3">Aktie / Asset</th>
                  <th className="p-3 text-right">Gewicht</th>
                  <th className="p-3 text-center">Style Box</th>
                  <th className="p-3 text-right">Value</th>
                  <th className="p-3 text-right">Quality</th>
                  <th className="p-3 text-right">Momentum</th>
                  <th className="p-3 text-right">Defensiv (Low-Beta)</th>
                  <th className="p-3 text-center">Aktion</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/6 dark:divide-white/6">
                {data.positions.map((pos) => {
                  const isSelected = selectedHolding?.ticker === pos.ticker;
                  return (
                    <tr
                      key={pos.ticker}
                      onClick={() => setSelectedHolding(pos)}
                      className={`cursor-pointer transition-colors ${
                        isSelected
                          ? "bg-sky-500/10 dark:bg-sky-500/15"
                          : "hover:bg-black/[0.02] dark:hover:bg-white/[0.02]"
                      }`}
                    >
                      <td className="p-3">
                        <div className="font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
                          {pos.ticker}
                          <span className="text-[10px] font-normal text-slate-500 dark:text-slate-400 truncate max-w-[120px]">
                            {pos.name}
                          </span>
                        </div>
                      </td>
                      <td className="p-3 text-right font-mono font-bold text-slate-800 dark:text-slate-200">
                        {pos.weight_pct}%
                      </td>
                      <td className="p-3 text-center">
                        <span className="rounded-full border border-black/8 bg-black/5 px-2.5 py-0.5 text-[10px] font-extrabold dark:border-white/10 dark:bg-white/10 text-slate-700 dark:text-slate-300">
                          {pos.style_box.cell}
                        </span>
                      </td>
                      <td className="p-3 text-right font-mono font-semibold">
                        <span className={pos.factors.value.score >= 60 ? "text-emerald-600 dark:text-emerald-400 font-bold" : ""}>
                          {pos.factors.value.score}
                        </span>
                      </td>
                      <td className="p-3 text-right font-mono font-semibold">
                        <span className={pos.factors.quality.score >= 70 ? "text-emerald-600 dark:text-emerald-400 font-bold" : ""}>
                          {pos.factors.quality.score}
                        </span>
                      </td>
                      <td className="p-3 text-right font-mono font-semibold">
                        <span className={pos.factors.momentum.score >= 70 ? "text-purple-600 dark:text-purple-400 font-bold" : ""}>
                          {pos.factors.momentum.score}
                        </span>
                      </td>
                      <td className="p-3 text-right font-mono font-semibold">
                        <span className={pos.factors.low_volatility.score >= 70 ? "text-sky-600 dark:text-sky-400 font-bold" : ""}>
                          {pos.factors.low_volatility.score}
                        </span>
                      </td>
                      <td className="p-3 text-center">
                        {onAnalyzeStock && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              onAnalyzeStock(pos.ticker);
                            }}
                            className="inline-flex items-center gap-1 rounded-lg border border-black/8 bg-white px-2 py-1 text-[10px] font-bold text-slate-700 hover:bg-black/5 dark:border-white/10 dark:bg-white/5 dark:text-slate-200"
                          >
                            Analyse <ExternalLink size={10} />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
