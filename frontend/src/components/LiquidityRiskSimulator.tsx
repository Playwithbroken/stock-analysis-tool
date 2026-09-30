import React, { useEffect, useState } from "react";
import {
  Droplets,
  AlertTriangle,
  Info,
  RefreshCw,
  X,
  Clock,
  Flame,
  ShieldCheck,
  TrendingDown,
  Layers,
  ArrowRight,
  Sliders,
  CheckCircle2,
  DollarSign
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

interface HoldingLiquidity {
  ticker: string;
  name: string;
  shares: number;
  price: number;
  value_eur: number;
  weight_pct: number;
  adv_shares: number;
  daily_turnover_eur: number;
  spread_pct: number;
  days_to_liquidate: number;
  tier: number;
  tier_label: string;
  normal_slippage_pct: number;
  normal_slippage_eur: number;
  fire_sale_slippage_pct: number;
  fire_sale_slippage_eur: number;
  recommended_strategy: string;
  strategy_description: string;
}

interface TierDistribution {
  tier_1_pct: number;
  tier_2_pct: number;
  tier_3_pct: number;
  tier_4_pct: number;
}

interface ExecutionCosts {
  normal_slippage_pct: number;
  normal_slippage_eur: number;
  fire_sale_slippage_pct: number;
  fire_sale_slippage_eur: number;
  panic_cost_delta_eur: number;
}

interface LiquidityAnalysisData {
  valid: boolean;
  error?: string;
  portfolio_id?: string;
  portfolio_name?: string;
  portfolio_value_eur: number;
  participation_rate_pct: number;
  liquidity_health_score: number;
  liquidity_badge: {
    label: string;
    tone: string;
  };
  portfolio_days_to_liquidate: number;
  max_position_dtl: number;
  tier_distribution: TierDistribution;
  execution_costs: ExecutionCosts;
  holdings: HoldingLiquidity[];
}

interface OrderSimResult {
  ticker: string;
  order_value_eur: number;
  order_shares: number;
  adv_shares: number;
  order_pct_of_adv: number;
  spread_cost_pct: number;
  market_impact_pct: number;
  total_slippage_pct: number;
  total_slippage_eur: number;
}

interface LiquidityRiskSimulatorProps {
  portfolioId: string;
  onAnalyzeStock?: (ticker: string) => void;
  onClose?: () => void;
}

export default function LiquidityRiskSimulator({
  portfolioId,
  onAnalyzeStock,
  onClose
}: LiquidityRiskSimulatorProps) {
  const [data, setData] = useState<LiquidityAnalysisData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [participationRate, setParticipationRate] = useState<number>(0.10);
  const [activeTab, setActiveTab] = useState<"tiers" | "holdings" | "simulator">("tiers");

  // Simulator tab state
  const [simTicker, setSimTicker] = useState<string>("");
  const [simOrderValue, setSimOrderValue] = useState<number>(50000);
  const [simPrice, setSimPrice] = useState<number>(100);
  const [simResult, setSimResult] = useState<OrderSimResult | null>(null);
  const [simLoading, setSimLoading] = useState<boolean>(false);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/portfolio/${portfolioId}/liquidity?participation_rate=${participationRate}`,
        { credentials: "same-origin" }
      );
      if (!res.ok) {
        throw new Error(`HTTP Fehler ${res.status}: Liquiditätsanalyse fehlgeschlagen.`);
      }
      const json: LiquidityAnalysisData = await res.json();
      if (!json.valid) {
        throw new Error(json.error || "Ungültige Antwort vom Liquiditätsdienst.");
      }
      setData(json);
      if (json.holdings && json.holdings.length > 0 && !simTicker) {
        setSimTicker(json.holdings[0].ticker);
        setSimPrice(json.holdings[0].price);
      }
    } catch (err: any) {
      setError(err.message || "Unerwarteter Fehler beim Laden der Liquiditätsdaten.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (portfolioId) {
      fetchData();
    }
  }, [portfolioId, participationRate]);

  const handleRunSimulation = async () => {
    if (!simTicker || simOrderValue <= 0) return;
    setSimLoading(true);
    try {
      const res = await fetch("/api/portfolio/liquidity/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({
          ticker: simTicker.toUpperCase().trim(),
          order_value_eur: simOrderValue,
          current_price: simPrice
        })
      });
      if (!res.ok) throw new Error("Fehler bei der Order-Simulation.");
      const json: OrderSimResult = await res.json();
      setSimResult(json);
    } catch (e: any) {
      console.error(e);
    } finally {
      setSimLoading(false);
    }
  };

  const getTierTone = (tier: number) => {
    switch (tier) {
      case 1:
        return "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400";
      case 2:
        return "border-teal-500/30 bg-teal-500/10 text-teal-700 dark:text-teal-400";
      case 3:
        return "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400";
      default:
        return "border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-400";
    }
  };

  const costComparisonData = data ? [
    {
      name: "Geordnet (Normal)",
      cost_pct: data.execution_costs.normal_slippage_pct,
      cost_eur: data.execution_costs.normal_slippage_eur,
      color: "#0d9488" // teal-600
    },
    {
      name: "1-Tag Notverkauf (Fire-Sale)",
      cost_pct: data.execution_costs.fire_sale_slippage_pct,
      cost_eur: data.execution_costs.fire_sale_slippage_eur,
      color: "#e11d48" // rose-600
    }
  ] : [];

  return (
    <section className="mt-8 rounded-[2rem] border border-cyan-500/20 bg-gradient-to-b from-cyan-950/[0.04] to-transparent p-6 dark:border-cyan-500/30 dark:bg-slate-900/60 shadow-xl backdrop-blur-md">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-black/10 pb-5 dark:border-white/10">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-500/15 text-cyan-700 dark:text-cyan-400 border border-cyan-500/30 shadow-inner">
            <Droplets size={24} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-black tracking-tight text-slate-900 dark:text-white">
                Institutional Liquidity Risk & Market Impact Simulator
              </h2>
              <span className="rounded-md border border-cyan-500/30 bg-cyan-500/15 px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider text-cyan-800 dark:text-cyan-300">
                Almgren-Chriss (2000)
              </span>
            </div>
            <p className="text-xs font-semibold text-slate-600 dark:text-slate-400">
              Days-to-Liquidate (DTL), SEC Rule 22e-4 / UCITS Tier-Klassifizierung &amp; Notverkauf-Stresstest
            </p>
          </div>
        </div>

        {/* Global Controls */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 rounded-xl border border-black/10 bg-white/90 px-3 py-1.5 dark:border-white/10 dark:bg-slate-800 shadow-sm">
            <Sliders size={14} className="text-slate-500 dark:text-slate-400" />
            <span className="text-xs font-extrabold text-slate-700 dark:text-slate-300">Partizipationsrate:</span>
            <select
              value={participationRate}
              onChange={(e) => setParticipationRate(parseFloat(e.target.value))}
              className="rounded-lg bg-transparent text-xs font-black text-cyan-700 dark:text-cyan-400 outline-none cursor-pointer"
            >
              <option value="0.05">5% ADV (Sehr konservativ)</option>
              <option value="0.10">10% ADV (Institutioneller Standard)</option>
              <option value="0.15">15% ADV (Moderat aktiv)</option>
              <option value="0.20">20% ADV (Aggressiv)</option>
              <option value="0.30">30% ADV (Hoher Impact)</option>
            </select>
          </div>

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
          <RefreshCw size={36} className="animate-spin text-cyan-600 dark:text-cyan-400" />
          <p className="mt-4 text-sm font-bold text-slate-700 dark:text-slate-300">
            Berechne Almgren-Chriss Marktimpact &amp; Liquiditäts-Tiers...
          </p>
        </div>
      )}

      {error && (
        <div className="my-6 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-5 text-rose-800 dark:text-rose-300">
          <div className="flex items-center gap-2 font-black">
            <AlertTriangle size={18} />
            Fehler bei der Liquiditätsanalyse
          </div>
          <p className="mt-1 text-xs">{error}</p>
        </div>
      )}

      {!loading && !error && data && (
        <div className="mt-6 space-y-6">
          {/* 4 Scorecards */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {/* Card 1: DTL */}
            <div className="rounded-2xl border border-black/10 bg-white/90 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Days-to-Liquidate (DTL)
                </span>
                <Clock size={16} className="text-cyan-600 dark:text-cyan-400" />
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-black text-slate-900 dark:text-white">
                  {data.portfolio_days_to_liquidate}
                </span>
                <span className="text-xs font-bold text-slate-600 dark:text-slate-400">Tage</span>
              </div>
              <div className="mt-2 text-xs font-medium text-slate-500 dark:text-slate-400">
                Max Einzelposition: <span className="font-bold text-slate-800 dark:text-slate-200">{data.max_position_dtl} Tage</span> bei {data.participation_rate_pct}% ADV
              </div>
            </div>

            {/* Card 2: Normal Slippage */}
            <div className="rounded-2xl border border-black/10 bg-white/90 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Geordnete Ausführung
                </span>
                <ShieldCheck size={16} className="text-teal-600 dark:text-teal-400" />
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-black text-teal-700 dark:text-teal-400">
                  {data.execution_costs.normal_slippage_pct.toFixed(2)}%
                </span>
                <span className="text-xs font-bold text-slate-600 dark:text-slate-400">
                  ({data.execution_costs.normal_slippage_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })})
                </span>
              </div>
              <div className="mt-2 text-xs font-medium text-slate-500 dark:text-slate-400">
                Spread + Almgren-Chriss Impact über DTL-Tage
              </div>
            </div>

            {/* Card 3: Fire-Sale Slippage */}
            <div className="rounded-2xl border border-black/10 bg-white/90 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  1-Tag Notverkauf (Fire-Sale)
                </span>
                <Flame size={16} className="text-rose-600 dark:text-rose-400" />
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-black text-rose-700 dark:text-rose-400">
                  {data.execution_costs.fire_sale_slippage_pct.toFixed(2)}%
                </span>
                <span className="text-xs font-bold text-slate-600 dark:text-slate-400">
                  ({data.execution_costs.fire_sale_slippage_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })})
                </span>
              </div>
              <div className="mt-2 text-xs font-medium text-rose-600 dark:text-rose-400 font-bold">
                +{data.execution_costs.panic_cost_delta_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })} Panik-Prämie
              </div>
            </div>

            {/* Card 4: Health Score */}
            <div className="rounded-2xl border border-black/10 bg-white/90 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/90">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Liquiditäts-Health-Score
                </span>
                <span className={`rounded-md border px-2 py-0.5 text-[10px] font-black uppercase ${data.liquidity_badge.tone}`}>
                  {data.liquidity_badge.label}
                </span>
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-black text-slate-900 dark:text-white">
                  {data.liquidity_health_score.toFixed(1)}
                </span>
                <span className="text-xs font-bold text-slate-500">/ 100</span>
              </div>
              <div className="mt-2 text-xs font-medium text-slate-500 dark:text-slate-400">
                SEC 22e-4 Konformität &amp; Slippage-Resilienz
              </div>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="flex gap-2 border-b border-black/10 dark:border-white/10">
            <button
              onClick={() => setActiveTab("tiers")}
              className={`flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-black uppercase tracking-wider transition-all ${
                activeTab === "tiers"
                  ? "border-cyan-500 text-cyan-800 dark:text-cyan-300"
                  : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              <Layers size={15} />
              SEC 22e-4 Tiers &amp; Notverkauf-Vergleich
            </button>

            <button
              onClick={() => setActiveTab("holdings")}
              className={`flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-black uppercase tracking-wider transition-all ${
                activeTab === "holdings"
                  ? "border-cyan-500 text-cyan-800 dark:text-cyan-300"
                  : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              <Clock size={15} />
              Holdings Liquiditäts-Tabelle ({data.holdings.length})
            </button>

            <button
              onClick={() => setActiveTab("simulator")}
              className={`flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-black uppercase tracking-wider transition-all ${
                activeTab === "simulator"
                  ? "border-cyan-500 text-cyan-800 dark:text-cyan-300"
                  : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              <Sliders size={15} />
              Order-Impact &amp; Slippage Simulator
            </button>
          </div>

          {/* TAB 1: SEC 22e-4 Tiers & Comparison */}
          {activeTab === "tiers" && (
            <div className="grid gap-6 lg:grid-cols-12">
              {/* Tier Breakdown Cards */}
              <div className="lg:col-span-7 space-y-4">
                <div className="rounded-2xl border border-black/10 bg-white/80 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/80">
                  <h3 className="text-sm font-black text-slate-900 dark:text-white">
                    SEC Rule 22e-4 &amp; UCITS Liquiditäts-Klassen
                  </h3>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                    Regulatorische Portfolio-Segmentierung nach Liquidierungsdauer bei {data.participation_rate_pct}% ADV
                  </p>

                  <div className="mt-5 space-y-3">
                    {/* Tier 1 */}
                    <div className="flex items-center justify-between rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3">
                      <div>
                        <div className="text-xs font-black text-emerald-800 dark:text-emerald-300">
                          Tier 1: Hochliquide (≤ 1 Handelstag)
                        </div>
                        <div className="text-[11px] font-medium text-slate-600 dark:text-slate-400">
                          Kann sofort innerhalb von 24h ohne signifikanten Marktimpact liquidiert werden
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-base font-black text-emerald-700 dark:text-emerald-400">
                          {data.tier_distribution.tier_1_pct.toFixed(1)}%
                        </div>
                      </div>
                    </div>

                    {/* Tier 2 */}
                    <div className="flex items-center justify-between rounded-xl border border-teal-500/20 bg-teal-500/5 p-3">
                      <div>
                        <div className="text-xs font-black text-teal-800 dark:text-teal-300">
                          Tier 2: Moderat liquide (2 bis 5 Handelstage)
                        </div>
                        <div className="text-[11px] font-medium text-slate-600 dark:text-slate-400">
                          Liquidation über VWAP / TWAP innerhalb einer Handelswoche
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-base font-black text-teal-700 dark:text-teal-400">
                          {data.tier_distribution.tier_2_pct.toFixed(1)}%
                        </div>
                      </div>
                    </div>

                    {/* Tier 3 */}
                    <div className="flex items-center justify-between rounded-xl border border-amber-500/20 bg-amber-500/5 p-3">
                      <div>
                        <div className="text-xs font-black text-amber-800 dark:text-amber-300">
                          Tier 3: Eingeschränkt liquide (6 bis 15 Handelstage)
                        </div>
                        <div className="text-[11px] font-medium text-slate-600 dark:text-slate-400">
                          Erfordert Block-Trading / Dark Pool Order-Routing zur Impact-Vermeidung
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-base font-black text-amber-700 dark:text-amber-400">
                          {data.tier_distribution.tier_3_pct.toFixed(1)}%
                        </div>
                      </div>
                    </div>

                    {/* Tier 4 */}
                    <div className="flex items-center justify-between rounded-xl border border-rose-500/20 bg-rose-500/5 p-3">
                      <div>
                        <div className="text-xs font-black text-rose-800 dark:text-rose-300">
                          Tier 4: Illiquide (&gt; 15 Handelstage)
                        </div>
                        <div className="text-[11px] font-medium text-slate-600 dark:text-slate-400">
                          SEC 22e-4 Obergrenze max. 15% des Fondsvermögens (Notfall-Liquiditätsrisiko)
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-base font-black text-rose-700 dark:text-rose-400">
                          {data.tier_distribution.tier_4_pct.toFixed(1)}%
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Cost Comparison Chart */}
              <div className="lg:col-span-5">
                <div className="rounded-2xl border border-black/10 bg-white/80 p-5 shadow-sm dark:border-white/10 dark:bg-slate-800/80">
                  <h3 className="text-sm font-black text-slate-900 dark:text-white">
                    Kostenvergleich: Geordnet vs. Notverkauf
                  </h3>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                    Almgren-Chriss Slippage bei Multi-Day TWAP vs. 1-Tag Sofortverkauf
                  </p>

                  <MeasuredChartFrame className="mt-4 w-full" minHeight={220}>
                    <ResponsiveContainer width="100%" height={220}>
                      <BarChart data={costComparisonData} margin={{ top: 20, right: 30, left: 10, bottom: 20 }}>
                        <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                        <XAxis dataKey="name" tick={{ fontSize: 11, fontWeight: 700 }} />
                        <YAxis unit="%" tick={{ fontSize: 11 }} />
                        <Tooltip
                          formatter={(value: any, name: any, item: any) => [
                            `${Number(value).toFixed(2)}% (${item.payload.cost_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })})`,
                            "Slippage"
                          ]}
                          contentStyle={{ backgroundColor: "#0f172a", borderRadius: "12px", border: "none", color: "#fff" }}
                        />
                        <Bar dataKey="cost_pct" radius={[8, 8, 0, 0]}>
                          {costComparisonData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </MeasuredChartFrame>

                  <div className="mt-3 rounded-xl border border-rose-500/20 bg-rose-500/5 p-3 text-xs text-rose-800 dark:text-rose-300">
                    <strong>Panik-Exit Warnung:</strong> Bei erzwungener 1-Tages-Liquidierung verliert das Portfolio voraussichtlich zusätzlich{" "}
                    <strong>{data.execution_costs.panic_cost_delta_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}</strong> durch Orderbuch-Überlastung.
                  </div>
                </div>
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
                    <th className="p-3.5 text-right">Gewicht</th>
                    <th className="p-3.5 text-right">Positionswert</th>
                    <th className="p-3.5 text-right">ADV (Shares)</th>
                    <th className="p-3.5 text-right">Bid-Ask Spread</th>
                    <th className="p-3.5 text-right">DTL ({data.participation_rate_pct}%)</th>
                    <th className="p-3.5 text-center">SEC Tier</th>
                    <th className="p-3.5 text-right">Geordnete Slippage</th>
                    <th className="p-3.5 text-right">Notverkauf Slippage</th>
                    <th className="p-3.5">Empfohlene Strategie</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/5 dark:divide-white/5 font-semibold text-slate-800 dark:text-slate-200">
                  {data.holdings.map((h) => (
                    <tr key={h.ticker} className="hover:bg-cyan-500/5 transition-colors">
                      <td className="p-3.5">
                        <button
                          onClick={() => onAnalyzeStock && onAnalyzeStock(h.ticker)}
                          className="font-black text-cyan-700 hover:underline dark:text-cyan-400 text-left"
                        >
                          {h.ticker}
                        </button>
                        <div className="text-[11px] text-slate-500 truncate max-w-[140px]">{h.name}</div>
                      </td>
                      <td className="p-3.5 text-right font-bold">{h.weight_pct.toFixed(1)}%</td>
                      <td className="p-3.5 text-right font-bold">
                        {h.value_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}
                      </td>
                      <td className="p-3.5 text-right font-mono text-[11px]">
                        {h.adv_shares.toLocaleString("de-DE")}
                      </td>
                      <td className="p-3.5 text-right font-mono text-[11px]">{h.spread_pct.toFixed(2)}%</td>
                      <td className="p-3.5 text-right font-black">
                        <span className={h.days_to_liquidate > 5 ? "text-amber-600 dark:text-amber-400" : ""}>
                          {h.days_to_liquidate} d
                        </span>
                      </td>
                      <td className="p-3.5 text-center">
                        <span className={`inline-block rounded-md border px-2 py-0.5 text-[10px] font-black uppercase ${getTierTone(h.tier)}`}>
                          Tier {h.tier}
                        </span>
                      </td>
                      <td className="p-3.5 text-right font-bold text-teal-700 dark:text-teal-400">
                        {h.normal_slippage_pct.toFixed(2)}%
                        <div className="text-[10px] text-slate-500 font-normal">
                          {h.normal_slippage_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}
                        </div>
                      </td>
                      <td className="p-3.5 text-right font-bold text-rose-700 dark:text-rose-400">
                        {h.fire_sale_slippage_pct.toFixed(2)}%
                        <div className="text-[10px] text-slate-500 font-normal">
                          {h.fire_sale_slippage_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}
                        </div>
                      </td>
                      <td className="p-3.5">
                        <span className="rounded-md border border-black/10 bg-black/5 px-2 py-1 text-[11px] font-extrabold text-slate-800 dark:border-white/10 dark:bg-white/5 dark:text-slate-200">
                          {h.recommended_strategy}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* TAB 3: Order-Impact Simulator */}
          {activeTab === "simulator" && (
            <div className="rounded-2xl border border-black/10 bg-white/80 p-6 shadow-sm dark:border-white/10 dark:bg-slate-800/80">
              <h3 className="text-base font-black text-slate-900 dark:text-white flex items-center gap-2">
                <Sliders size={18} className="text-cyan-600 dark:text-cyan-400" />
                Single Order Impact &amp; Slippage Calculator
              </h3>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                Simuliere den sofortigen Marktimpact und die Ausführungskosten einer großen Kauf- oder Verkaufsorder gemäß Almgren-Chriss (2000).
              </p>

              <div className="mt-6 grid gap-6 md:grid-cols-3">
                {/* Input 1: Ticker */}
                <div>
                  <label className="text-[11px] font-black uppercase tracking-wider text-slate-600 dark:text-slate-400">
                    Ticker-Symbol
                  </label>
                  <input
                    type="text"
                    value={simTicker}
                    onChange={(e) => setSimTicker(e.target.value.toUpperCase())}
                    placeholder="z.B. AAPL oder MSFT"
                    className="mt-1.5 w-full rounded-xl border border-black/15 bg-white px-3.5 py-2.5 text-sm font-bold text-slate-900 focus:border-cyan-500 focus:outline-none dark:border-white/15 dark:bg-slate-900 dark:text-white"
                  />
                </div>

                {/* Input 2: Order Value */}
                <div>
                  <label className="text-[11px] font-black uppercase tracking-wider text-slate-600 dark:text-slate-400">
                    Order-Volumen (€)
                  </label>
                  <input
                    type="number"
                    step="5000"
                    value={simOrderValue}
                    onChange={(e) => setSimOrderValue(parseFloat(e.target.value) || 0)}
                    className="mt-1.5 w-full rounded-xl border border-black/15 bg-white px-3.5 py-2.5 text-sm font-bold text-slate-900 focus:border-cyan-500 focus:outline-none dark:border-white/15 dark:bg-slate-900 dark:text-white"
                  />
                </div>

                {/* Input 3: Reference Price */}
                <div>
                  <label className="text-[11px] font-black uppercase tracking-wider text-slate-600 dark:text-slate-400">
                    Aktueller Kurs (€)
                  </label>
                  <input
                    type="number"
                    step="1"
                    value={simPrice}
                    onChange={(e) => setSimPrice(parseFloat(e.target.value) || 100)}
                    className="mt-1.5 w-full rounded-xl border border-black/15 bg-white px-3.5 py-2.5 text-sm font-bold text-slate-900 focus:border-cyan-500 focus:outline-none dark:border-white/15 dark:bg-slate-900 dark:text-white"
                  />
                </div>
              </div>

              <div className="mt-5 flex justify-end">
                <button
                  onClick={handleRunSimulation}
                  disabled={simLoading || !simTicker}
                  className="rounded-xl bg-cyan-600 px-6 py-2.5 text-xs font-black uppercase tracking-wider text-white shadow-md hover:bg-cyan-700 disabled:opacity-50 transition-colors"
                >
                  {simLoading ? "Berechne Impact..." : "Marktimpact Simulieren"}
                </button>
              </div>

              {simResult && (
                <div className="mt-6 rounded-2xl border border-cyan-500/30 bg-cyan-500/5 p-5">
                  <h4 className="text-xs font-black uppercase tracking-wider text-cyan-800 dark:text-cyan-300">
                    Simulationsergebnis für {simResult.ticker} ({simResult.order_shares.toLocaleString("de-DE")} Shares / {simResult.order_value_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })})
                  </h4>

                  <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    <div className="rounded-xl border border-black/10 bg-white/90 p-3.5 dark:border-white/10 dark:bg-slate-800">
                      <div className="text-[10px] font-bold text-slate-500">Order-Anteil am ADV</div>
                      <div className="mt-1 text-xl font-black text-slate-900 dark:text-white">
                        {simResult.order_pct_of_adv.toFixed(2)}%
                      </div>
                      <div className="text-[10px] text-slate-500">ADV: {simResult.adv_shares.toLocaleString("de-DE")}</div>
                    </div>

                    <div className="rounded-xl border border-black/10 bg-white/90 p-3.5 dark:border-white/10 dark:bg-slate-800">
                      <div className="text-[10px] font-bold text-slate-500">Halber Spread (Geld/Brief)</div>
                      <div className="mt-1 text-xl font-black text-slate-900 dark:text-white">
                        {simResult.spread_cost_pct.toFixed(3)}%
                      </div>
                    </div>

                    <div className="rounded-xl border border-black/10 bg-white/90 p-3.5 dark:border-white/10 dark:bg-slate-800">
                      <div className="text-[10px] font-bold text-slate-500">Almgren-Chriss Impact</div>
                      <div className="mt-1 text-xl font-black text-rose-600 dark:text-rose-400">
                        +{simResult.market_impact_pct.toFixed(3)}%
                      </div>
                    </div>

                    <div className="rounded-xl border border-black/10 bg-white/90 p-3.5 dark:border-white/10 dark:bg-slate-800">
                      <div className="text-[10px] font-bold text-slate-500">Gesamte Slippage &amp; Kosten</div>
                      <div className="mt-1 text-xl font-black text-cyan-700 dark:text-cyan-300">
                        {simResult.total_slippage_pct.toFixed(3)}%
                      </div>
                      <div className="text-[11px] font-bold text-slate-700 dark:text-slate-300">
                        ≈ {simResult.total_slippage_eur.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
