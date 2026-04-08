import React from "react";
import {
  AlertTriangle,
  ArrowRight,
  Info,
  Layers,
  Shield,
  Target,
  TrendingUp,
} from "lucide-react";
import {
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
} from "recharts";
import MeasuredChartFrame from "./MeasuredChartFrame";

interface Holding {
  symbol: string;
  name: string;
  weight: number;
}

interface Alternative {
  ticker: string;
  name: string;
  ter: number;
  reason: string;
}

interface ETFAnalysis {
  ter: number | null;
  category: string;
  is_best_in_class: boolean;
  alternatives: Alternative[];
  holdings: Holding[];
  total_assets: number | null;
}

interface ETFComparisonProps {
  analysis: ETFAnalysis;
  onSelectTicker?: (ticker: string) => void;
}

const COLORS = [
  "#0f766e",
  "#0d9488",
  "#14b8a6",
  "#5eead4",
  "#1d4ed8",
  "#3b82f6",
  "#93c5fd",
  "#475569",
  "#64748b",
  "#94a3b8",
];

export default function ETFComparison({
  analysis,
  onSelectTicker,
}: ETFComparisonProps) {
  const formatCurrency = (value: number) => {
    if (value >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
    if (value >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
    if (value >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
    return `$${value.toLocaleString()}`;
  };

  const pieData = analysis.holdings.map((h) => ({
    name: h.symbol,
    value: h.weight,
    fullName: h.name,
  }));

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <InfoCard
          icon={<Shield className="h-3 w-3" />}
          label="Kosten (TER)"
          value={analysis.ter !== null ? `${analysis.ter.toFixed(2)}%` : "N/A"}
          tone={analysis.is_best_in_class ? "emerald" : "amber"}
          detail={
            analysis.is_best_in_class
              ? "Best-in-Class Gebuehren"
              : "Ueberdurchschnittliche Kosten"
          }
        />
        <InfoCard
          icon={<Layers className="h-3 w-3" />}
          label="Fondsvolumen"
          value={analysis.total_assets ? formatCurrency(analysis.total_assets) : "N/A"}
          tone="blue"
          detail="AUM (verwaltetes Vermoegen)"
        />
        <InfoCard
          icon={<TrendingUp className="h-3 w-3" />}
          label="Kategorie"
          value={analysis.category || "N/A"}
          tone="slate"
          detail="Asset-Klasse"
        />
      </div>

      {analysis.alternatives.length > 0 && (
        <div className="surface-panel rounded-[1.8rem] p-5">
          <div className="mb-4 flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-600" />
            <h3 className="text-lg font-bold text-slate-900">
              Optimierungspotenzial gefunden
            </h3>
          </div>
          <div className="space-y-4">
            {analysis.alternatives.map((alt) => (
              <div
                key={alt.ticker}
                onClick={() => onSelectTicker?.(alt.ticker)}
                className="group flex cursor-pointer flex-col justify-between gap-4 rounded-[1.2rem] border border-black/8 bg-white/78 p-4 transition-all hover:border-amber-500/25 hover:bg-white md:flex-row md:items-center"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold tracking-tight text-amber-700">
                      {alt.ticker}
                    </span>
                    <span className="font-medium text-slate-900">{alt.name}</span>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">{alt.reason}</p>
                </div>
                <div className="flex shrink-0 items-center gap-4">
                  <div className="text-right">
                    <div className="text-xs text-slate-500">TER</div>
                    <div className="font-bold text-emerald-700">
                      {alt.ter.toFixed(2)}%
                    </div>
                  </div>
                  <div className="rounded-full bg-amber-500/10 p-2 transition-colors group-hover:bg-amber-500/16">
                    <ArrowRight className="h-4 w-4 text-amber-700" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="surface-panel rounded-[1.8rem] p-5">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-lg font-bold text-slate-900">
              <Layers className="h-5 w-5 text-[var(--accent)]" /> Top 10 Holdings
            </h3>
            <span className="text-xs text-slate-500">Nach Gewichtung</span>
          </div>

          <div className="space-y-2">
            {analysis.holdings.length > 0 ? (
              analysis.holdings.map((holding) => (
                <div
                  key={holding.symbol}
                  className="group relative flex cursor-help items-center justify-between rounded-xl border border-black/8 bg-white/78 p-3 transition-all hover:border-[var(--accent)]/20 hover:bg-white"
                >
                  <div className="min-w-0">
                    <span className="block truncate font-mono text-sm font-bold text-slate-900">
                      {holding.symbol}
                    </span>
                    <span className="block truncate text-[10px] text-slate-500">
                      {holding.name}
                    </span>
                  </div>
                  <div className="ml-4 shrink-0 text-sm font-bold text-[var(--accent)]">
                    {holding.weight.toFixed(2)}%
                  </div>

                  <div className="invisible absolute left-full top-0 z-50 ml-4 w-64 translate-x-2 rounded-xl border border-black/8 bg-white p-4 opacity-0 shadow-[0_20px_40px_rgba(17,24,39,0.12)] transition-all delay-150 group-hover:visible group-hover:translate-x-0 group-hover:opacity-100">
                    <div className="mb-2 flex items-center gap-2">
                      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--accent-soft)]">
                        <Target className="h-4 w-4 text-[var(--accent)]" />
                      </div>
                      <div className="truncate text-sm font-bold text-slate-900">
                        {holding.symbol}
                      </div>
                    </div>
                    <div className="mb-3 text-xs font-medium text-slate-600">
                      {holding.name}
                    </div>
                    <div className="border-t border-black/8 pt-2">
                      <div className="mb-2 flex items-center justify-between">
                        <span className="text-[10px] uppercase tracking-[0.16em] text-slate-500">
                          Gewichtung
                        </span>
                        <span className="text-xs font-bold text-slate-900">
                          {holding.weight.toFixed(2)}%
                        </span>
                      </div>
                      <div className="h-1.5 w-full overflow-hidden rounded-full bg-black/[0.06]">
                        <div
                          className="h-full rounded-full bg-[var(--accent)]"
                          style={{ width: `${Math.min(100, holding.weight * 5)}%` }}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-xl border border-dashed border-black/8 bg-white/70 py-8 text-center text-slate-500">
                <Info className="mx-auto mb-2 h-8 w-8 opacity-25" />
                Keine Holdings-Daten verfuegbar
              </div>
            )}
          </div>
        </div>

        <div className="surface-panel flex min-h-[300px] flex-col items-center justify-center rounded-[1.8rem] p-5">
          <h3 className="mb-6 self-start text-sm font-bold uppercase tracking-[0.18em] text-slate-500">
            Visualisierung der Allokation
          </h3>
          {analysis.holdings.length > 0 ? (
            <MeasuredChartFrame className="h-64 w-full" minHeight={256}>
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={220}>
                <PieChart>
                  <RechartsTooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        return (
                          <div className="rounded-lg border border-black/8 bg-white p-3 shadow-[0_18px_36px_rgba(17,24,39,0.1)]">
                            <div className="font-bold text-[var(--accent)]">
                              {payload[0].name}
                            </div>
                            <div className="mb-1 text-[10px] text-slate-500">
                              {payload[0].payload.fullName}
                            </div>
                            <div className="text-xs font-bold text-slate-900">
                              {Number(payload[0].value).toFixed(2)}%
                            </div>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  <Pie
                    data={pieData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={58}
                    outerRadius={92}
                    paddingAngle={2}
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={`${entry.name}-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
            </MeasuredChartFrame>
          ) : (
            <div className="text-sm text-slate-500">Keine Allokationsdaten vorhanden.</div>
          )}
        </div>
      </div>
    </div>
  );
}

function InfoCard({
  icon,
  label,
  value,
  detail,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  detail: string;
  tone: "emerald" | "amber" | "blue" | "slate";
}) {
  const toneClass =
    tone === "emerald"
      ? "bg-emerald-500/7 border-emerald-500/14 text-emerald-700"
      : tone === "amber"
        ? "bg-amber-500/7 border-amber-500/14 text-amber-700"
        : tone === "blue"
          ? "bg-sky-500/7 border-sky-500/14 text-sky-700"
          : "bg-slate-500/7 border-slate-500/14 text-slate-700";

  return (
    <div className={`rounded-xl border p-4 ${toneClass}`}>
      <div className="mb-1 flex items-center gap-1 text-xs">
        {icon}
        {label}
      </div>
      <div className="truncate text-xl font-bold text-slate-900">{value}</div>
      <div className="mt-1 text-xs text-slate-500">{detail}</div>
    </div>
  );
}
