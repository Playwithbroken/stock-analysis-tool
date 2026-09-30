import React, { useEffect, useState } from "react";
import {
  TrendingUp,
  Shield,
  Target,
  Sliders,
  Sparkles,
  Info,
  RefreshCw,
  Maximize2,
  Minimize2,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  Scale,
  Zap,
  SlidersHorizontal
} from "lucide-react";
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Line,
  ComposedChart,
  ReferenceLine
} from "recharts";
import MeasuredChartFrame from "./MeasuredChartFrame";

interface PortfolioPoint {
  name: string;
  volatility_pct: number;
  expected_return_pct: number;
  sharpe_ratio: number;
  risk_reduction_pct?: number;
  sharpe_gain?: number;
  has_custom_views?: boolean;
}

interface FrontierPoint {
  volatility_pct: number;
  expected_return_pct: number;
  sharpe_ratio: number;
}

interface AllocationRow {
  ticker: string;
  name: string;
  annual_return_pct: number;
  annual_volatility_pct: number;
  current_weight_pct: number;
  min_vol_weight_pct: number;
  max_sharpe_weight_pct: number;
  equal_weight_pct: number;
  black_litterman_weight_pct: number;
  delta_max_sharpe_pct: number;
  delta_black_litterman_pct: number;
}

interface OptimizationResponse {
  valid: boolean;
  timeframe: string;
  risk_free_rate_pct: number;
  efficiency_score: number;
  tickers: string[];
  names: string[];
  current_portfolio: PortfolioPoint;
  min_volatility_portfolio: PortfolioPoint;
  max_sharpe_portfolio: PortfolioPoint;
  black_litterman_portfolio: PortfolioPoint;
  equal_weight_portfolio: PortfolioPoint;
  efficient_frontier: FrontierPoint[];
  simulated_cloud: FrontierPoint[];
  allocations: AllocationRow[];
  error?: string;
}

interface TacticalView {
  ticker: string;
  expected_excess_return_pct: number;
  confidence: number;
}

interface EfficientFrontierOptimizerProps {
  portfolioId: string;
  onApplyTargets?: (targets: Record<string, number>, strategyName: string) => void;
  onClose?: () => void;
}

export default function EfficientFrontierOptimizer({
  portfolioId,
  onApplyTargets,
  onClose
}: EfficientFrontierOptimizerProps) {
  const [data, setData] = useState<OptimizationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [timeframe, setTimeframe] = useState<"90d" | "1y" | "3y">("1y");
  const [riskFreeRate, setRiskFreeRate] = useState<number>(3.5);
  const [activeTab, setActiveTab] = useState<"frontier" | "allocations" | "views">("frontier");
  const [tacticalViews, setTacticalViews] = useState<Record<string, { ret: number; conf: number }>>({});
  const [optimizingBL, setOptimizingBL] = useState(false);
  const [appliedStrategy, setAppliedStrategy] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);

  const fetchOptimization = async (tf: string, rf: number) => {
    setLoading(true);
    try {
      const res = await fetch(
        `/api/portfolio/${portfolioId}/efficient-frontier?timeframe=${tf}&rf=${(rf / 100).toFixed(4)}`
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: OptimizationResponse = await res.json();
      setData(json);

      // Initialize tactical views from holdings if empty
      if (json.allocations && Object.keys(tacticalViews).length === 0) {
        const initialViews: Record<string, { ret: number; conf: number }> = {};
        json.allocations.forEach((row) => {
          initialViews[row.ticker] = {
            ret: 4.0, // default +4.0% excess return
            conf: 0.70 // default 70% confidence
          };
        });
        setTacticalViews(initialViews);
      }
    } catch (e) {
      console.error("Failed to load efficient frontier data:", e);
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (portfolioId) {
      fetchOptimization(timeframe, riskFreeRate);
    }
  }, [portfolioId, timeframe, riskFreeRate]);

  const handleRunBlackLitterman = async () => {
    if (!data) return;
    setOptimizingBL(true);
    try {
      const viewsPayload: TacticalView[] = Object.entries(tacticalViews).map(([ticker, v]) => ({
        ticker,
        expected_excess_return_pct: v.ret,
        confidence: v.conf
      }));

      const res = await fetch(`/api/portfolio/${portfolioId}/optimize/black-litterman`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          timeframe,
          risk_free_rate: riskFreeRate / 100,
          views: viewsPayload
        })
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: OptimizationResponse = await res.json();
      setData(json);
      setActiveTab("allocations");
    } catch (e) {
      console.error("Failed to optimize Black-Litterman:", e);
    } finally {
      setOptimizingBL(false);
    }
  };

  const handleApply = (strategy: "max_sharpe" | "min_vol" | "black_litterman") => {
    if (!data || !onApplyTargets) return;
    const targetWeights: Record<string, number> = {};

    data.allocations.forEach((row) => {
      if (strategy === "max_sharpe") {
        targetWeights[row.ticker] = row.max_sharpe_weight_pct;
      } else if (strategy === "min_vol") {
        targetWeights[row.ticker] = row.min_vol_weight_pct;
      } else {
        targetWeights[row.ticker] = row.black_litterman_weight_pct;
      }
    });

    const strategyNames = {
      max_sharpe: "Maximum Sharpe Ratio (MSR)",
      min_vol: "Minimum Volatilität (GMV)",
      black_litterman: "Black-Litterman Tactical Tilt"
    };

    onApplyTargets(targetWeights, strategyNames[strategy]);
    setAppliedStrategy(strategyNames[strategy]);
    setTimeout(() => setAppliedStrategy(null), 3500);
  };

  if (loading && !data) {
    return (
      <div className="surface-panel rounded-[2rem] p-6 text-center">
        <div className="flex flex-col items-center justify-center gap-3 py-12">
          <RefreshCw className="h-7 w-7 animate-spin text-cyan-600 dark:text-cyan-400" />
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">
            Berechne Markowitz Effizienzgrenze & Black-Litterman Modell...
          </p>
          <p className="text-xs text-slate-500">
            Kovarianzmatrix, 1.000+ Monte-Carlo-Allokationen und konvexe Optimierung
          </p>
        </div>
      </div>
    );
  }

  if (!data || !data.valid || !data.allocations || data.allocations.length < 2) {
    return (
      <div className="surface-panel rounded-[2rem] p-6 text-center text-xs font-medium text-slate-700 dark:text-slate-300">
        <AlertTriangle size={32} className="mx-auto mb-2 text-amber-500" />
        Füge mindestens zwei Positionen mit Kursdaten hinzu, um die Effizienzgrenze und Black-Litterman
        zu berechnen.
      </div>
    );
  }

  // Formatting helpers
  const efficiencyBadge =
    data.efficiency_score >= 80
      ? { label: "Hocheffizient", color: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30" }
      : data.efficiency_score >= 60
      ? { label: "Gut", color: "bg-blue-500/15 text-blue-700 dark:text-blue-400 border-blue-500/30" }
      : { label: "Suboptimal", color: "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30" };

  return (
    <div
      className={`surface-panel rounded-[2rem] p-6 transition-all duration-300 ${
        isExpanded ? "fixed inset-4 z-50 overflow-y-auto bg-slate-900/95 shadow-2xl backdrop-blur-xl" : ""
      }`}
    >
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-black/8 pb-4 dark:border-white/10">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-cyan-500/10 p-2.5 text-cyan-600 dark:bg-cyan-500/20 dark:text-cyan-400">
            <Target size={22} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold text-slate-900 dark:text-white">
                Efficient Frontier & Black-Litterman Suite
              </h3>
              <span className="rounded-full bg-cyan-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-cyan-700 dark:text-cyan-300">
                Goldman-Sachs MPT
              </span>
            </div>
            <p className="text-xs text-slate-600 dark:text-slate-400">
              Mean-Variance Portfoliotheorie, Max Sharpe Tangency & Bayesianische Taktiksichten
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Timeframe selector */}
          <div className="flex rounded-xl border border-black/10 bg-slate-100 p-1 dark:border-white/10 dark:bg-slate-800">
            {(["90d", "1y", "3y"] as const).map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition-all ${
                  timeframe === tf
                    ? "bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-white"
                    : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
                }`}
              >
                {tf === "90d" ? "90T" : tf === "1y" ? "1J" : "3J"}
              </button>
            ))}
          </div>

          {/* Risk-Free Rate Badge / Control */}
          <div className="flex items-center gap-1.5 rounded-xl border border-black/10 bg-slate-100 px-2.5 py-1 text-xs dark:border-white/10 dark:bg-slate-800">
            <span className="text-[11px] font-bold text-slate-500">R_f:</span>
            <input
              type="number"
              step="0.5"
              min="0"
              max="10"
              value={riskFreeRate}
              onChange={(e) => setRiskFreeRate(parseFloat(e.target.value) || 0)}
              className="w-12 bg-transparent text-right font-mono font-bold text-slate-900 focus:outline-none dark:text-white"
            />
            <span className="text-slate-500">%</span>
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
        {/* Sharpe Ratio */}
        <div className="rounded-2xl border border-black/8 bg-white/70 p-3.5 shadow-sm dark:border-white/10 dark:bg-slate-800/60">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Aktuelle Sharpe Ratio
          </div>
          <div className="mt-1.5 flex items-baseline gap-1.5">
            <span className="text-2xl font-black text-slate-900 dark:text-white">
              {data.current_portfolio.sharpe_ratio.toFixed(2)}
            </span>
            <span className="text-xs text-slate-500">vs. {data.max_sharpe_portfolio.sharpe_ratio.toFixed(2)} MSR</span>
          </div>
          <div className="mt-2 flex items-center gap-1 text-[11px] font-bold text-cyan-600 dark:text-cyan-400">
            <Sparkles size={12} />
            +{(data.max_sharpe_portfolio.sharpe_ratio - data.current_portfolio.sharpe_ratio).toFixed(2)} Steigerung möglich
          </div>
        </div>

        {/* Minimum Volatility */}
        <div className="rounded-2xl border border-black/8 bg-white/70 p-3.5 shadow-sm dark:border-white/10 dark:bg-slate-800/60">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Min. Volatilität (GMV)
          </div>
          <div className="mt-1.5 flex items-baseline gap-1.5">
            <span className="text-2xl font-black text-emerald-600 dark:text-emerald-400">
              {data.min_volatility_portfolio.volatility_pct.toFixed(1)}%
            </span>
            <span className="text-xs text-slate-500">p.a.</span>
          </div>
          <p className="mt-2 text-[10px] text-slate-500 dark:text-slate-400">
            Aktuell: {data.current_portfolio.volatility_pct.toFixed(1)}% (
            {data.min_volatility_portfolio.risk_reduction_pct
              ? `-${data.min_volatility_portfolio.risk_reduction_pct.toFixed(0)}% Risiko`
              : "Minimum"}
            )
          </p>
        </div>

        {/* Expected Return */}
        <div className="rounded-2xl border border-black/8 bg-white/70 p-3.5 shadow-sm dark:border-white/10 dark:bg-slate-800/60">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Max Sharpe Rendite
          </div>
          <div className="mt-1.5 flex items-baseline gap-1.5">
            <span className="text-2xl font-black text-cyan-600 dark:text-cyan-400">
              {data.max_sharpe_portfolio.expected_return_pct.toFixed(1)}%
            </span>
            <span className="text-xs text-slate-500">p.a.</span>
          </div>
          <p className="mt-2 text-[10px] text-slate-500 dark:text-slate-400">
            bei {data.max_sharpe_portfolio.volatility_pct.toFixed(1)}% Volatilität
          </p>
        </div>

        {/* Efficiency Score */}
        <div className="rounded-2xl border border-black/8 bg-white/70 p-3.5 shadow-sm dark:border-white/10 dark:bg-slate-800/60">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Effizienz-Score
          </div>
          <div className="mt-1.5 flex items-baseline gap-2">
            <span className="text-2xl font-black text-slate-900 dark:text-white">
              {data.efficiency_score.toFixed(0)}
            </span>
            <span className="text-xs text-slate-500">/ 100</span>
          </div>
          <div className="mt-2 flex items-center gap-1.5">
            <span
              className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold ${efficiencyBadge.color}`}
            >
              <CheckCircle2 size={11} />
              {efficiencyBadge.label}
            </span>
          </div>
        </div>
      </div>

      {/* Applied Banner */}
      {appliedStrategy && (
        <div className="mb-4 flex items-center justify-between rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs font-bold text-emerald-800 dark:text-emerald-300">
          <span className="flex items-center gap-2">
            <CheckCircle2 size={16} />
            Zielgewichte für „{appliedStrategy}“ wurden erfolgreich an den Rebalance-Manager übergeben!
          </span>
        </div>
      )}

      {/* Navigation Sub-Tabs */}
      <div className="mb-5 flex flex-wrap gap-2 border-b border-black/6 pb-2 dark:border-white/10">
        <button
          onClick={() => setActiveTab("frontier")}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
            activeTab === "frontier"
              ? "bg-cyan-500/15 text-cyan-700 dark:bg-cyan-500/25 dark:text-cyan-300"
              : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
          }`}
        >
          <TrendingUp size={14} />
          Effizienzgrenze & Scatter-Plot
        </button>

        <button
          onClick={() => setActiveTab("allocations")}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
            activeTab === "allocations"
              ? "bg-cyan-500/15 text-cyan-700 dark:bg-cyan-500/25 dark:text-cyan-300"
              : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
          }`}
        >
          <Scale size={14} />
          Allokations-Vergleich
        </button>

        <button
          onClick={() => setActiveTab("views")}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
            activeTab === "views"
              ? "bg-cyan-500/15 text-cyan-700 dark:bg-cyan-500/25 dark:text-cyan-300"
              : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
          }`}
        >
          <SlidersHorizontal size={14} />
          Black-Litterman Taktiksichten
        </button>
      </div>

      {/* Tab 1: Frontier Scatter Plot */}
      {activeTab === "frontier" && (
        <div>
          <div className="rounded-2xl border border-black/8 bg-white/40 p-4 dark:border-white/10 dark:bg-slate-900/40">
            <MeasuredChartFrame className="h-[360px] w-full" minHeight={360}>
              {({ w, h }) => (
                <ComposedChart width={w} height={h} margin={{ top: 15, right: 30, left: 10, bottom: 25 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                  <XAxis
                    type="number"
                    dataKey="volatility_pct"
                    name="Volatilität"
                    unit="%"
                    domain={["dataMin - 1", "dataMax + 2"]}
                    tick={{ fontSize: 11, fill: "#64748b" }}
                    label={{
                      value: "Volatilität p.a. (Risiko σ)",
                      position: "insideBottom",
                      offset: -12,
                      fontSize: 11,
                      fill: "#64748b",
                      fontWeight: 600
                    }}
                  />
                  <YAxis
                    type="number"
                    dataKey="expected_return_pct"
                    name="Erwartete Rendite"
                    unit="%"
                    domain={["auto", "auto"]}
                    tick={{ fontSize: 11, fill: "#64748b" }}
                    label={{
                      value: "Erwartete Rendite p.a. (μ)",
                      angle: -90,
                      position: "insideLeft",
                      offset: 5,
                      fontSize: 11,
                      fill: "#64748b",
                      fontWeight: 600
                    }}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload || !payload.length) return null;
                      const pt = payload[0].payload;
                      return (
                        <div className="rounded-xl border border-black/10 bg-slate-900 p-3 text-xs text-white shadow-xl dark:border-white/20">
                          <div className="font-bold text-cyan-300">{pt.name || "Portfolio-Kombination"}</div>
                          <div className="mt-1 flex justify-between gap-4">
                            <span className="text-slate-400">Erwartete Rendite:</span>
                            <span className="font-mono font-bold text-emerald-400">
                              {Number(pt.expected_return_pct).toFixed(2)}%
                            </span>
                          </div>
                          <div className="flex justify-between gap-4">
                            <span className="text-slate-400">Volatilität:</span>
                            <span className="font-mono font-bold text-amber-400">
                              {Number(pt.volatility_pct).toFixed(2)}%
                            </span>
                          </div>
                          <div className="flex justify-between gap-4">
                            <span className="text-slate-400">Sharpe Ratio:</span>
                            <span className="font-mono font-bold text-cyan-400">
                              {Number(pt.sharpe_ratio).toFixed(2)}
                            </span>
                          </div>
                        </div>
                      );
                    }}
                  />

                  {/* Monte Carlo Cloud */}
                  <Scatter
                    name="Zufällige Portfolios"
                    data={data.simulated_cloud}
                    fill="#38bdf8"
                    opacity={0.25}
                    shape="circle"
                  />

                  {/* Efficient Frontier Curve Line */}
                  <Line
                    type="monotone"
                    dataKey="expected_return_pct"
                    data={data.efficient_frontier}
                    stroke="#06b6d4"
                    strokeWidth={3}
                    dot={false}
                    name="Effizienzgrenze"
                  />

                  {/* Special Markers */}
                  {/* Current Portfolio */}
                  <Scatter
                    name="Aktuelles Portfolio"
                    data={[
                      {
                        name: "📍 Aktuelles Portfolio",
                        volatility_pct: data.current_portfolio.volatility_pct,
                        expected_return_pct: data.current_portfolio.expected_return_pct,
                        sharpe_ratio: data.current_portfolio.sharpe_ratio
                      }
                    ]}
                    fill="#eab308"
                    shape="star"
                  />

                  {/* Max Sharpe Portfolio */}
                  <Scatter
                    name="Maximum Sharpe (MSR)"
                    data={[
                      {
                        name: "🎯 Max Sharpe Portfolio (MSR)",
                        volatility_pct: data.max_sharpe_portfolio.volatility_pct,
                        expected_return_pct: data.max_sharpe_portfolio.expected_return_pct,
                        sharpe_ratio: data.max_sharpe_portfolio.sharpe_ratio
                      }
                    ]}
                    fill="#06b6d4"
                    shape="diamond"
                  />

                  {/* Min Volatility Portfolio */}
                  <Scatter
                    name="Minimum Volatilität (GMV)"
                    data={[
                      {
                        name: "🛡️ Global Min Volatility (GMV)",
                        volatility_pct: data.min_volatility_portfolio.volatility_pct,
                        expected_return_pct: data.min_volatility_portfolio.expected_return_pct,
                        sharpe_ratio: data.min_volatility_portfolio.sharpe_ratio
                      }
                    ]}
                    fill="#10b981"
                    shape="triangle"
                  />

                  {/* Black-Litterman Portfolio */}
                  <Scatter
                    name="Black-Litterman Tilt"
                    data={[
                      {
                        name: "⚖️ Black-Litterman Tactical Tilt",
                        volatility_pct: data.black_litterman_portfolio.volatility_pct,
                        expected_return_pct: data.black_litterman_portfolio.expected_return_pct,
                        sharpe_ratio: data.black_litterman_portfolio.sharpe_ratio
                      }
                    ]}
                    fill="#a855f7"
                    shape="circle"
                  />
                </ComposedChart>
              )}
            </MeasuredChartFrame>
          </div>

          {/* Legend & Strategy Fast Actions */}
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-black/8 bg-white/60 p-3 dark:border-white/10 dark:bg-slate-800/40">
            <div className="flex flex-wrap items-center gap-4 text-xs font-semibold">
              <span className="flex items-center gap-1.5">
                <span className="h-3 w-3 rounded-full bg-yellow-500" />
                <span className="text-slate-800 dark:text-slate-200">Aktuelles Portfolio</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-3 w-3 rotate-45 bg-cyan-500" />
                <span className="text-slate-800 dark:text-slate-200">Max Sharpe (MSR)</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-3 w-3 bg-emerald-500" />
                <span className="text-slate-800 dark:text-slate-200">Min Volatilität (GMV)</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-3 w-3 rounded-full bg-purple-500" />
                <span className="text-slate-800 dark:text-slate-200">Black-Litterman Tilt</span>
              </span>
            </div>

            {onApplyTargets && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleApply("max_sharpe")}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-cyan-600 px-3 py-1.5 text-xs font-bold text-white shadow-sm hover:bg-cyan-500"
                >
                  <Target size={14} />
                  Max Sharpe anwenden
                </button>
                <button
                  onClick={() => handleApply("min_vol")}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white shadow-sm hover:bg-emerald-500"
                >
                  <Shield size={14} />
                  Min Vol anwenden
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab 2: Allocations Table */}
      {activeTab === "allocations" && (
        <div className="space-y-4">
          <div className="overflow-x-auto rounded-2xl border border-black/8 bg-white/70 shadow-xs dark:border-white/10 dark:bg-slate-900/60">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-black/8 bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:border-white/10 dark:bg-slate-800/60 dark:text-slate-400">
                  <th className="p-3">Asset</th>
                  <th className="p-3 text-right">Rendite p.a.</th>
                  <th className="p-3 text-right">Volatilität</th>
                  <th className="p-3 text-right">Ist-Gewicht</th>
                  <th className="p-3 text-right text-emerald-700 dark:text-emerald-400">Min Vol</th>
                  <th className="p-3 text-right text-cyan-700 dark:text-cyan-400">Max Sharpe</th>
                  <th className="p-3 text-right text-purple-700 dark:text-purple-400">Black-Litterman</th>
                  <th className="p-3 text-right">Δ Max Sharpe</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/6 dark:divide-white/6">
                {data.allocations.map((row) => (
                  <tr key={row.ticker} className="hover:bg-black/[0.02] dark:hover:bg-white/[0.02]">
                    <td className="p-3">
                      <div className="font-bold text-slate-900 dark:text-white">{row.ticker}</div>
                      <div className="text-[10px] text-slate-600 dark:text-slate-400">{row.name}</div>
                    </td>
                    <td className="p-3 text-right font-mono font-semibold text-emerald-700 dark:text-emerald-400">
                      {row.annual_return_pct > 0 ? `+${row.annual_return_pct.toFixed(1)}%` : `${row.annual_return_pct.toFixed(1)}%`}
                    </td>
                    <td className="p-3 text-right font-mono font-semibold text-slate-700 dark:text-slate-300">
                      {row.annual_volatility_pct.toFixed(1)}%
                    </td>
                    <td className="p-3 text-right font-mono font-bold text-slate-900 dark:text-white">
                      {row.current_weight_pct.toFixed(1)}%
                    </td>
                    <td className="p-3 text-right font-mono font-bold text-emerald-700 dark:text-emerald-400">
                      {row.min_vol_weight_pct.toFixed(1)}%
                    </td>
                    <td className="p-3 text-right font-mono font-bold text-cyan-700 dark:text-cyan-400">
                      {row.max_sharpe_weight_pct.toFixed(1)}%
                    </td>
                    <td className="p-3 text-right font-mono font-bold text-purple-700 dark:text-purple-400">
                      {row.black_litterman_weight_pct.toFixed(1)}%
                    </td>
                    <td className="p-3 text-right font-mono font-bold">
                      <span
                        className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs ${
                          row.delta_max_sharpe_pct > 0.5
                            ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
                            : row.delta_max_sharpe_pct < -0.5
                            ? "bg-rose-500/15 text-rose-700 dark:text-rose-400"
                            : "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300"
                        }`}
                      >
                        {row.delta_max_sharpe_pct > 0
                          ? `+${row.delta_max_sharpe_pct.toFixed(1)}%`
                          : `${row.delta_max_sharpe_pct.toFixed(1)}%`}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {onApplyTargets && (
            <div className="flex flex-wrap items-center justify-end gap-3 pt-2">
              <button
                onClick={() => handleApply("max_sharpe")}
                className="inline-flex items-center gap-2 rounded-xl bg-cyan-600 px-4 py-2 text-xs font-bold text-white shadow-sm hover:bg-cyan-500"
              >
                <Target size={15} />
                Max-Sharpe-Zielgewichte übernehmen
              </button>
              <button
                onClick={() => handleApply("black_litterman")}
                className="inline-flex items-center gap-2 rounded-xl bg-purple-600 px-4 py-2 text-xs font-bold text-white shadow-sm hover:bg-purple-500"
              >
                <Scale size={15} />
                Black-Litterman-Zielgewichte übernehmen
              </button>
            </div>
          )}
        </div>
      )}

      {/* Tab 3: Tactical Views Builder */}
      {activeTab === "views" && (
        <div className="space-y-4">
          <div className="rounded-xl border border-purple-500/20 bg-purple-500/5 p-4 text-xs text-purple-900 dark:border-purple-500/30 dark:bg-purple-500/10 dark:text-purple-200">
            <div className="flex items-start gap-2.5">
              <Info size={16} className="mt-0.5 shrink-0 text-purple-600 dark:text-purple-400" />
              <p>
                <strong>Black-Litterman Modell (Goldman Sachs):</strong> Kombiniert das unvoreingenommene
                Marktgleichgewicht mit deinen persönlichen Markterwartungen (Views). Je höher die Konfidenz,
                desto stärker neigt sich das Portfolio in deine Lieblingswerte, ohne dabei die
                mathematische Risikokontrolle zu verlieren.
              </p>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {data.allocations.map((row) => {
              const view = tacticalViews[row.ticker] || { ret: 4.0, conf: 0.7 };
              return (
                <div
                  key={row.ticker}
                  className="rounded-2xl border border-black/8 bg-white/70 p-4 shadow-sm dark:border-white/10 dark:bg-slate-800/60"
                >
                  <div className="flex items-center justify-between border-b border-black/6 pb-2 dark:border-white/10">
                    <div>
                      <span className="font-bold text-slate-900 dark:text-white">{row.ticker}</span>
                      <span className="ml-2 text-xs text-slate-500">({row.name})</span>
                    </div>
                    <span className="font-mono text-xs font-bold text-purple-600 dark:text-purple-400">
                      BL-Gewicht: {row.black_litterman_weight_pct.toFixed(1)}%
                    </span>
                  </div>

                  <div className="mt-3 space-y-3">
                    <div>
                      <div className="flex justify-between text-xs">
                        <span className="text-slate-600 dark:text-slate-400">
                          Erwartete Überrendite vs. Markt:
                        </span>
                        <span className="font-mono font-bold text-emerald-600 dark:text-emerald-400">
                          {view.ret > 0 ? `+${view.ret.toFixed(1)}%` : `${view.ret.toFixed(1)}%`} p.a.
                        </span>
                      </div>
                      <input
                        type="range"
                        min="-15"
                        max="25"
                        step="0.5"
                        value={view.ret}
                        onChange={(e) =>
                          setTacticalViews({
                            ...tacticalViews,
                            [row.ticker]: { ...view, ret: parseFloat(e.target.value) }
                          })
                        }
                        className="mt-1.5 h-1.5 w-full cursor-pointer accent-purple-600"
                      />
                    </div>

                    <div>
                      <div className="flex justify-between text-xs">
                        <span className="text-slate-600 dark:text-slate-400">Deine Konfidenz / Überzeugung:</span>
                        <span className="font-mono font-bold text-purple-600 dark:text-purple-400">
                          {Math.round(view.conf * 100)}%
                        </span>
                      </div>
                      <input
                        type="range"
                        min="0.10"
                        max="0.95"
                        step="0.05"
                        value={view.conf}
                        onChange={(e) =>
                          setTacticalViews({
                            ...tacticalViews,
                            [row.ticker]: { ...view, conf: parseFloat(e.target.value) }
                          })
                        }
                        className="mt-1.5 h-1.5 w-full cursor-pointer accent-purple-600"
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              onClick={handleRunBlackLitterman}
              disabled={optimizingBL}
              className="inline-flex items-center gap-2 rounded-xl bg-purple-600 px-5 py-2.5 text-xs font-bold text-white shadow-sm hover:bg-purple-500 disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${optimizingBL ? "animate-spin" : ""}`} />
              Black-Litterman mit Sichten neu berechnen
            </button>
          </div>
        </div>
      )}

      {/* Footer Info Box */}
      <div className="mt-6 flex items-center gap-3 rounded-xl border border-black/8 bg-white/70 p-3.5 text-xs text-slate-700 dark:border-white/10 dark:bg-slate-800/60 dark:text-slate-300">
        <Info size={16} className="shrink-0 text-cyan-600 dark:text-cyan-400" />
        <p className="text-[11px] leading-relaxed">
          <strong className="text-slate-900 dark:text-white">Institutionelle Methodik:</strong> Die
          Effizienzgrenze stellt alle mathematisch optimalen Portfolios dar, die für ein gegebenes
          Risikoniveau die maximale Rendite erzielen. Das <em>Tangency Portfolio (Max Sharpe)</em> bildet
          den Schnittpunkt mit der Capital Allocation Line und maximiert die Sharpe Ratio.
        </p>
      </div>
    </div>
  );
}
