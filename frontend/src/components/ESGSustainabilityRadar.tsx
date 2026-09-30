import React, { useEffect, useState } from "react";
import {
  Leaf,
  ShieldCheck,
  ShieldAlert,
  Flame,
  AlertTriangle,
  Info,
  RefreshCw,
  Maximize2,
  Minimize2,
  CheckCircle2,
  Sparkles,
  Award,
  Globe,
  Users,
  Building2,
  TreePine
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Cell
} from "recharts";
import MeasuredChartFrame from "./MeasuredChartFrame";

interface ESGPillars {
  environmental: number;
  social: number;
  governance: number;
}

interface CarbonIntensity {
  portfolio_waci: number;
  benchmark_waci: number;
  relative_carbon_delta_pct: number;
  is_cleaner_than_benchmark: boolean;
}

interface SFDRInfo {
  classification: string;
  badge: string;
  tone: string;
  description: string;
  article_8_coverage_pct: number;
  article_9_coverage_pct: number;
}

interface ExclusionItem {
  ticker: string;
  name: string;
  weight_pct: number;
  reasons: string[];
}

interface ExclusionsInfo {
  has_violations: boolean;
  violations_count: number;
  violations: ExclusionItem[];
}

interface ControversyItem {
  ticker: string;
  name: string;
  weight_pct: number;
  level: number;
  descriptions: string[];
}

interface HoldingESGAttribution {
  ticker: string;
  name: string;
  sector: string;
  weight_pct: number;
  esg_score: number;
  esg_rating: string;
  e_score: number;
  s_score: number;
  g_score: number;
  carbon_intensity: number;
  controversy_level: number;
  has_exclusion: boolean;
  sfdr_eligible_art8: boolean;
}

interface ESGResponse {
  valid: boolean;
  portfolio_esg_score: number;
  portfolio_esg_rating: string;
  pillars: ESGPillars;
  carbon_intensity: CarbonIntensity;
  sfdr: SFDRInfo;
  exclusions: ExclusionsInfo;
  controversies: ControversyItem[];
  holdings: HoldingESGAttribution[];
  error?: string;
}

interface ESGSustainabilityRadarProps {
  portfolioId: string;
  onAnalyzeStock?: (ticker: string) => void;
  onClose?: () => void;
}

export default function ESGSustainabilityRadar({
  portfolioId,
  onAnalyzeStock,
  onClose
}: ESGSustainabilityRadarProps) {
  const [data, setData] = useState<ESGResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"pillars" | "controversies" | "holdings">("pillars");
  const [isExpanded, setIsExpanded] = useState(false);

  const fetchESG = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/portfolio/${portfolioId}/esg`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: ESGResponse = await res.json();
      setData(json);
    } catch (e) {
      console.error("Failed to load ESG data:", e);
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (portfolioId) {
      fetchESG();
    }
  }, [portfolioId]);

  if (loading && !data) {
    return (
      <div className="surface-panel rounded-[2rem] p-6 text-center">
        <div className="flex flex-col items-center justify-center gap-3 py-12">
          <RefreshCw className="h-7 w-7 animate-spin text-emerald-600 dark:text-emerald-400" />
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">
            Berechne EU SFDR Klassifikation, CO2-Intensität & ESG-Säulen...
          </p>
          <p className="text-xs text-slate-500">
            WACI Carbon Footprint, PAI-Ausschluss-Screening und Kontroversen-Radar
          </p>
        </div>
      </div>
    );
  }

  if (!data || !data.valid || !data.holdings || data.holdings.length === 0) {
    return (
      <div className="surface-panel rounded-[2rem] p-6 text-center text-xs font-medium text-slate-700 dark:text-slate-300">
        <AlertTriangle size={32} className="mx-auto mb-2 text-amber-500" />
        Keine Positionen im Portfolio vorhanden, um ein ESG- und Nachhaltigkeitsprofil zu erstellen.
      </div>
    );
  }

  // Rating color badge
  const ratingBadgeClass = (rating: string) => {
    switch (rating) {
      case "AAA":
        return "bg-emerald-500/20 text-emerald-800 dark:text-emerald-300 border-emerald-500/40";
      case "AA":
      case "A":
        return "bg-teal-500/20 text-teal-800 dark:text-teal-300 border-teal-500/40";
      case "BBB":
      case "BB":
        return "bg-amber-500/20 text-amber-800 dark:text-amber-300 border-amber-500/40";
      default:
        return "bg-rose-500/20 text-rose-800 dark:text-rose-300 border-rose-500/40";
    }
  };

  const carbonComparisonData = [
    { name: "Portfolio", waci: data.carbon_intensity.portfolio_waci, fill: "#10b981" },
    { name: "MSCI World", waci: data.carbon_intensity.benchmark_waci, fill: "#94a3b8" }
  ];

  return (
    <div
      className={`surface-panel rounded-[2rem] p-6 transition-all duration-300 ${
        isExpanded ? "fixed inset-4 z-50 overflow-y-auto bg-slate-900/95 shadow-2xl backdrop-blur-xl" : ""
      }`}
    >
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-black/8 pb-4 dark:border-white/10">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-emerald-500/10 p-2.5 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-400">
            <Leaf size={22} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold text-slate-900 dark:text-white">
                ESG & Sustainability Radar
              </h3>
              <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-300">
                EU SFDR & MiFID II
              </span>
            </div>
            <p className="text-xs text-slate-600 dark:text-slate-400">
              Artikel 8/9 Regulatorik, Carbon Intensity (WACI), E-S-G Säulen und Ausschlussprüfung
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Refresh */}
          <button
            onClick={fetchESG}
            className="rounded-xl border border-black/10 bg-white/60 p-2 text-slate-600 hover:bg-white hover:text-slate-900 dark:border-white/10 dark:bg-slate-800/60 dark:text-slate-300 dark:hover:bg-slate-800"
            title="Aktualisieren"
          >
            <RefreshCw size={16} />
          </button>

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
        {/* Overall ESG Score */}
        <div className="rounded-2xl border border-black/8 bg-white/70 p-3.5 shadow-sm dark:border-white/10 dark:bg-slate-800/60">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            ESG-Score & Rating
          </div>
          <div className="mt-1.5 flex items-baseline gap-2">
            <span className="text-2xl font-black text-slate-900 dark:text-white">
              {data.portfolio_esg_score.toFixed(0)}
            </span>
            <span className="text-xs text-slate-500">/ 100</span>
            <span
              className={`ml-auto inline-flex items-center rounded-lg border px-2 py-0.5 text-xs font-black ${ratingBadgeClass(
                data.portfolio_esg_rating
              )}`}
            >
              {data.portfolio_esg_rating}
            </span>
          </div>
          <div className="mt-2 flex items-center gap-1 text-[10px] text-slate-600 dark:text-slate-400">
            <Award size={12} className="text-emerald-600 dark:text-emerald-400" />
            {data.portfolio_esg_score >= 70 ? "ESG Leader (Top Quartil)" : "ESG Average"}
          </div>
        </div>

        {/* Carbon Intensity (WACI) */}
        <div className="rounded-2xl border border-black/8 bg-white/70 p-3.5 shadow-sm dark:border-white/10 dark:bg-slate-800/60">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            CO2-Intensität (WACI)
          </div>
          <div className="mt-1.5 flex items-baseline gap-1.5">
            <span className="text-2xl font-black text-emerald-600 dark:text-emerald-400">
              {data.carbon_intensity.portfolio_waci.toFixed(1)}
            </span>
            <span className="text-xs text-slate-500">t CO2e / $M</span>
          </div>
          <p className="mt-2 text-[10px] font-semibold text-emerald-700 dark:text-emerald-400">
            {data.carbon_intensity.relative_carbon_delta_pct > 0
              ? `+${data.carbon_intensity.relative_carbon_delta_pct.toFixed(0)}% vs. MSCI World`
              : `${data.carbon_intensity.relative_carbon_delta_pct.toFixed(0)}% vs. MSCI World`}
          </p>
        </div>

        {/* SFDR Classification */}
        <div className="rounded-2xl border border-black/8 bg-white/70 p-3.5 shadow-sm dark:border-white/10 dark:bg-slate-800/60">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            EU SFDR Einstufung
          </div>
          <div className="mt-2">
            <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-black ${data.sfdr.tone}`}>
              <ShieldCheck size={13} />
              {data.sfdr.badge}
            </span>
          </div>
          <p className="mt-2 text-[10px] text-slate-500 dark:text-slate-400">
            Art. 8 Abdeckung: <strong>{data.sfdr.article_8_coverage_pct.toFixed(0)}%</strong>
          </p>
        </div>

        {/* Exclusions / Red Flags */}
        <div className="rounded-2xl border border-black/8 bg-white/70 p-3.5 shadow-sm dark:border-white/10 dark:bg-slate-800/60">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Ausschluss-Kriterien (PAI)
          </div>
          <div className="mt-1.5 flex items-baseline gap-2">
            <span
              className={`text-2xl font-black ${
                data.exclusions.has_violations ? "text-rose-600 dark:text-rose-400" : "text-emerald-600 dark:text-emerald-400"
              }`}
            >
              {data.exclusions.violations_count}
            </span>
            <span className="text-xs text-slate-500">Verstöße</span>
          </div>
          <p className="mt-2 text-[10px] text-slate-500 dark:text-slate-400">
            {data.exclusions.has_violations
              ? "Achtung: Titel mit Kohle/Rüstung/Tabak"
              : "100% frei von Kohle, Waffen & Tabak"}
          </p>
        </div>
      </div>

      {/* Navigation Sub-Tabs */}
      <div className="mb-5 flex flex-wrap gap-2 border-b border-black/6 pb-2 dark:border-white/10">
        <button
          onClick={() => setActiveTab("pillars")}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
            activeTab === "pillars"
              ? "bg-emerald-500/15 text-emerald-700 dark:bg-emerald-500/25 dark:text-emerald-300"
              : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
          }`}
        >
          <TreePine size={14} />
          E-S-G Säulen & CO2
        </button>

        <button
          onClick={() => setActiveTab("controversies")}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
            activeTab === "controversies"
              ? "bg-emerald-500/15 text-emerald-700 dark:bg-emerald-500/25 dark:text-emerald-300"
              : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
          }`}
        >
          <AlertTriangle size={14} />
          Kontroversen & Greenwashing ({data.controversies.length})
        </button>

        <button
          onClick={() => setActiveTab("holdings")}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
            activeTab === "holdings"
              ? "bg-emerald-500/15 text-emerald-700 dark:bg-emerald-500/25 dark:text-emerald-300"
              : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
          }`}
        >
          <Users size={14} />
          Holdings ESG-Attribution ({data.holdings.length})
        </button>
      </div>

      {/* Tab 1: E-S-G Pillars & Carbon Comparison */}
      {activeTab === "pillars" && (
        <div className="space-y-6">
          {/* Pillars Progress Bars */}
          <div className="grid gap-4 sm:grid-cols-3">
            {/* Environmental */}
            <div className="rounded-2xl border border-black/8 bg-white/60 p-4 dark:border-white/10 dark:bg-slate-800/60">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-xs font-bold text-slate-900 dark:text-white">
                  <Globe size={16} className="text-emerald-600 dark:text-emerald-400" />
                  Environmental (E)
                </span>
                <span className="font-mono text-base font-black text-emerald-600 dark:text-emerald-400">
                  {data.pillars.environmental.toFixed(0)}/100
                </span>
              </div>
              <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-black/5 dark:bg-white/10">
                <div
                  className="h-full rounded-full bg-emerald-500"
                  style={{ width: `${Math.min(100, data.pillars.environmental)}%` }}
                />
              </div>
              <p className="mt-2 text-[10px] text-slate-500 dark:text-slate-400">
                Klimaschutz, Erneuerbare Energien & Ressourceneffizienz
              </p>
            </div>

            {/* Social */}
            <div className="rounded-2xl border border-black/8 bg-white/60 p-4 dark:border-white/10 dark:bg-slate-800/60">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-xs font-bold text-slate-900 dark:text-white">
                  <Users size={16} className="text-blue-600 dark:text-blue-400" />
                  Social (S)
                </span>
                <span className="font-mono text-base font-black text-blue-600 dark:text-blue-400">
                  {data.pillars.social.toFixed(0)}/100
                </span>
              </div>
              <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-black/5 dark:bg-white/10">
                <div
                  className="h-full rounded-full bg-blue-500"
                  style={{ width: `${Math.min(100, data.pillars.social)}%` }}
                />
              </div>
              <p className="mt-2 text-[10px] text-slate-500 dark:text-slate-400">
                Arbeitsstandards, Gesundheitsschutz & Lieferkettensicherheit
              </p>
            </div>

            {/* Governance */}
            <div className="rounded-2xl border border-black/8 bg-white/60 p-4 dark:border-white/10 dark:bg-slate-800/60">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-xs font-bold text-slate-900 dark:text-white">
                  <Building2 size={16} className="text-purple-600 dark:text-purple-400" />
                  Governance (G)
                </span>
                <span className="font-mono text-base font-black text-purple-600 dark:text-purple-400">
                  {data.pillars.governance.toFixed(0)}/100
                </span>
              </div>
              <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-black/5 dark:bg-white/10">
                <div
                  className="h-full rounded-full bg-purple-500"
                  style={{ width: `${Math.min(100, data.pillars.governance)}%` }}
                />
              </div>
              <p className="mt-2 text-[10px] text-slate-500 dark:text-slate-400">
                Aufsichtsrats-Unabhängigkeit, Anti-Korruption & Aktionärsrechte
              </p>
            </div>
          </div>

          {/* Carbon Comparison Chart */}
          <div className="rounded-2xl border border-black/8 bg-white/40 p-4 dark:border-white/10 dark:bg-slate-900/40">
            <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              CO2-Intensität im Vergleich: Portfolio vs. MSCI World Benchmark (t CO2e / $M Umsatz)
            </h4>
            <MeasuredChartFrame className="h-[220px] w-full" minHeight={220}>
              {({ w, h }) => (
                <BarChart width={w} height={h} data={carbonComparisonData} layout="vertical" margin={{ top: 10, right: 30, left: 40, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                  <XAxis type="number" unit=" t" tick={{ fontSize: 11, fill: "#64748b" }} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fontWeight: 700, fill: "#64748b" }} />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload || !payload.length) return null;
                      const pt = payload[0].payload;
                      return (
                        <div className="rounded-xl border border-black/10 bg-slate-900 p-2.5 text-xs text-white shadow-xl dark:border-white/20">
                          <div className="font-bold">{pt.name}</div>
                          <div className="mt-1 font-mono text-emerald-400 font-bold">
                            {Number(pt.waci).toFixed(1)} t CO2e / $M Umsatz
                          </div>
                        </div>
                      );
                    }}
                  />
                  <Bar dataKey="waci" radius={[0, 8, 8, 0]}>
                    {carbonComparisonData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              )}
            </MeasuredChartFrame>
          </div>
        </div>
      )}

      {/* Tab 2: Controversies & Greenwashing */}
      {activeTab === "controversies" && (
        <div className="space-y-4">
          <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4 text-xs text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
            <div className="flex items-start gap-2.5">
              <Info size={16} className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-400" />
              <p>
                <strong>Kontroversen-Prüfung:</strong> Analysiert Vorfälle in den Bereichen Umwelt,
                Menschenrechte, Arbeitsbedingungen und Compliance. Level 1–2 gelten als moderat,
                ab Level 3 drohen Reputations- und Klagerisiken.
              </p>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {data.controversies && data.controversies.length > 0 ? (
              data.controversies.map((item) => (
                <div
                  key={item.ticker}
                  className="rounded-2xl border border-black/8 bg-white/70 p-4 shadow-sm dark:border-white/10 dark:bg-slate-800/60"
                >
                  <div className="flex items-center justify-between border-b border-black/6 pb-2.5 dark:border-white/10">
                    <div>
                      <span className="font-bold text-slate-900 dark:text-white">{item.ticker}</span>
                      <span className="ml-2 text-xs text-slate-500">({item.name})</span>
                    </div>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                        item.level >= 4
                          ? "bg-rose-500/20 text-rose-800 dark:text-rose-300"
                          : item.level >= 3
                          ? "bg-amber-500/20 text-amber-800 dark:text-amber-300"
                          : "bg-blue-500/20 text-blue-800 dark:text-blue-300"
                      }`}
                    >
                      Kontroversen-Level {item.level} / 5
                    </span>
                  </div>

                  <div className="mt-3 space-y-1.5">
                    {item.descriptions && item.descriptions.length > 0 ? (
                      item.descriptions.map((desc, idx) => (
                        <div key={idx} className="flex items-start gap-2 text-xs text-slate-700 dark:text-slate-300">
                          <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
                          <span>{desc}</span>
                        </div>
                      ))
                    ) : (
                      <p className="text-xs text-slate-500">Keine wesentlichen Vorfälle gemeldet.</p>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <p className="text-xs text-slate-500">Keine Kontroversen im aktuellen Portfolio identifiziert.</p>
            )}
          </div>
        </div>
      )}

      {/* Tab 3: Holdings ESG Attribution Table */}
      {activeTab === "holdings" && (
        <div className="space-y-4">
          <div className="overflow-x-auto rounded-2xl border border-black/8 bg-white/70 shadow-xs dark:border-white/10 dark:bg-slate-900/60">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-black/8 bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:border-white/10 dark:bg-slate-800/60 dark:text-slate-400">
                  <th className="p-3">Asset</th>
                  <th className="p-3 text-right">Gewicht</th>
                  <th className="p-3 text-right">ESG Score</th>
                  <th className="p-3 text-right">Rating</th>
                  <th className="p-3 text-right">E / S / G</th>
                  <th className="p-3 text-right">WACI (CO2)</th>
                  <th className="p-3 text-right">SFDR Art. 8</th>
                  <th className="p-3 text-right">Ausschluss</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/6 dark:divide-white/6">
                {data.holdings.map((row) => (
                  <tr
                    key={row.ticker}
                    onClick={() => onAnalyzeStock && onAnalyzeStock(row.ticker)}
                    className="cursor-pointer hover:bg-black/[0.02] dark:hover:bg-white/[0.02]"
                  >
                    <td className="p-3">
                      <div className="font-bold text-slate-900 dark:text-white">{row.ticker}</div>
                      <div className="text-[10px] text-slate-600 dark:text-slate-400">{row.name}</div>
                    </td>
                    <td className="p-3 text-right font-mono font-bold text-slate-900 dark:text-white">
                      {row.weight_pct.toFixed(1)}%
                    </td>
                    <td className="p-3 text-right font-mono font-bold text-emerald-600 dark:text-emerald-400">
                      {row.esg_score}
                    </td>
                    <td className="p-3 text-right">
                      <span className={`rounded-md border px-2 py-0.5 text-xs font-bold ${ratingBadgeClass(row.esg_rating)}`}>
                        {row.esg_rating}
                      </span>
                    </td>
                    <td className="p-3 text-right font-mono text-slate-600 dark:text-slate-300">
                      {row.e_score} / {row.s_score} / {row.g_score}
                    </td>
                    <td className="p-3 text-right font-mono text-slate-700 dark:text-slate-300">
                      {row.carbon_intensity.toFixed(1)}
                    </td>
                    <td className="p-3 text-right">
                      {row.sfdr_eligible_art8 ? (
                        <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-bold">
                          <CheckCircle2 size={13} /> Ja
                        </span>
                      ) : (
                        <span className="text-slate-400">Nein</span>
                      )}
                    </td>
                    <td className="p-3 text-right">
                      {row.has_exclusion ? (
                        <span className="rounded-md bg-rose-500/20 px-2 py-0.5 text-[10px] font-bold text-rose-700 dark:text-rose-300">
                          Ausschluss
                        </span>
                      ) : (
                        <span className="text-emerald-600 dark:text-emerald-400 font-bold">Konform</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Footer Info Box */}
      <div className="mt-6 flex items-center gap-3 rounded-xl border border-black/8 bg-white/70 p-3.5 text-xs text-slate-700 dark:border-white/10 dark:bg-slate-800/60 dark:text-slate-300">
        <Info size={16} className="shrink-0 text-emerald-600 dark:text-emerald-400" />
        <p className="text-[11px] leading-relaxed">
          <strong className="text-slate-900 dark:text-white">EU SFDR Regulatorik:</strong> Fonds und
          Portfolios nach <em>Artikel 8</em> verpflichten sich zur aktiven Berücksichtigung von ESG-Kriterien
          und zum Ausschluss kontroverser Sektoren. <em>Artikel 9</em> erfordert darüber hinaus ein
          explizit deklariertes Nachhaltigkeitsziel (z. B. Pariser 1,5°C-Klimapfad).
        </p>
      </div>
    </div>
  );
}
