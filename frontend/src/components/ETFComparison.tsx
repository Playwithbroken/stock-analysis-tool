import React from "react";
import {
  Shield,
  TrendingUp,
  Info,
  AlertTriangle,
  Layers,
  ArrowRight,
  Target,
} from "lucide-react";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
} from "recharts";

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

const ETFComparison: React.FC<ETFComparisonProps> = ({
  analysis,
  onSelectTicker,
}) => {
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

  const COLORS = [
    "#6366f1",
    "#818cf8",
    "#a5b4fc",
    "#c7d2fe",
    "#4f46e5",
    "#4338ca",
    "#3730a3",
    "#312e81",
    "#1e1b4b",
    "#4338ca",
  ];

  return (
    <div className="space-y-6">
      {/* Header Info */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-indigo-500/5 border border-indigo-500/10 rounded-xl p-4">
          <div className="text-xs text-slate-400 mb-1 flex items-center gap-1">
            <Shield className="w-3 h-3" /> Kosten (TER)
          </div>
          <div className="text-xl font-bold text-white">
            {analysis.ter !== null ? `${analysis.ter.toFixed(2)}%` : "N/A"}
          </div>
          <div
            className={`text-xs mt-1 ${analysis.is_best_in_class ? "text-emerald-400" : "text-amber-400"}`}
          >
            {analysis.is_best_in_class
              ? "Best-in-Class Gebühren"
              : "Überdurchschnittliche Kosten"}
          </div>
        </div>

        <div className="bg-blue-500/5 border border-blue-500/10 rounded-xl p-4">
          <div className="text-xs text-slate-400 mb-1 flex items-center gap-1">
            <Layers className="w-3 h-3" /> Fondsvolumen
          </div>
          <div className="text-xl font-bold text-white">
            {analysis.total_assets
              ? formatCurrency(analysis.total_assets)
              : "N/A"}
          </div>
          <div className="text-xs text-slate-500 mt-1">
            AUM (Verwaltetes Vermögen)
          </div>
        </div>

        <div className="bg-emerald-500/5 border border-emerald-500/10 rounded-xl p-4">
          <div className="text-xs text-slate-400 mb-1 flex items-center gap-1">
            <TrendingUp className="w-3 h-3" /> Kategorie
          </div>
          <div
            className="text-xl font-bold text-white truncate"
            title={analysis.category}
          >
            {analysis.category || "N/A"}
          </div>
          <div className="text-xs text-slate-500 mt-1 font-mono uppercase tracking-wider">
            Asset Klasse
          </div>
        </div>
      </div>

      {/* Alternatives */}
      {analysis.alternatives.length > 0 && (
        <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <AlertTriangle className="w-5 h-5 text-amber-500" />
            <h3 className="text-lg font-bold text-white">
              Optimierungspotenzial gefunden
            </h3>
          </div>
          <div className="space-y-4">
            {analysis.alternatives.map((alt) => (
              <div
                key={alt.ticker}
                onClick={() => onSelectTicker?.(alt.ticker)}
                className="group flex flex-col md:flex-row md:items-center justify-between gap-4 p-4 bg-slate-800/50 border border-slate-700/50 rounded-lg hover:border-amber-500/50 transition-all cursor-pointer"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-amber-400 font-bold font-mono tracking-tighter">
                      {alt.ticker}
                    </span>
                    <span className="text-slate-200 font-medium">
                      {alt.name}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-1">{alt.reason}</p>
                </div>
                <div className="flex items-center gap-4 shrink-0">
                  <div className="text-right">
                    <div className="text-xs text-slate-500">TER</div>
                    <div className="text-emerald-400 font-bold">
                      {alt.ter.toFixed(2)}%
                    </div>
                  </div>
                  <div className="bg-amber-500/10 p-2 rounded-full group-hover:bg-amber-500/20 transition-colors">
                    <ArrowRight className="w-4 h-4 text-amber-500" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Top Holdings & Visualization */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: List */}
        <div className="bg-slate-800/30 border border-slate-700/50 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <Layers className="w-5 h-5 text-indigo-400" /> Top 10 Holdings
            </h3>
            <span className="text-xs text-slate-500">Nach Gewichtung</span>
          </div>

          <div className="space-y-2">
            {analysis.holdings.length > 0 ? (
              analysis.holdings.map((holding) => (
                <div
                  key={holding.symbol}
                  className="group relative flex items-center justify-between p-3 bg-slate-900/40 rounded-lg border border-slate-700/30 hover:border-indigo-500/50 hover:bg-slate-900/60 transition-all cursor-help"
                >
                  <div className="flex flex-col min-w-0">
                    <span className="text-slate-200 font-bold font-mono text-sm truncate">
                      {holding.symbol}
                    </span>
                    <span className="text-[10px] text-slate-500 truncate group-hover:text-slate-400 transition-colors">
                      {holding.name}
                    </span>
                  </div>
                  <div className="flex flex-col items-end shrink-0 ml-4">
                    <span className="text-indigo-400 font-bold text-sm">
                      {holding.weight.toFixed(2)}%
                    </span>
                  </div>

                  {/* Enhanced Hover Card (Tooltip replacement) */}
                  <div className="absolute left-full top-0 ml-4 z-50 w-64 p-4 bg-slate-800 border border-slate-700 rounded-xl shadow-2xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all delay-150 transform translate-x-2 group-hover:translate-x-0">
                    <div className="flex items-center gap-2 mb-2">
                      <div className="w-8 h-8 rounded-lg bg-indigo-500/20 flex items-center justify-center">
                        <Target className="w-4 h-4 text-indigo-400" />
                      </div>
                      <div className="font-bold text-white text-sm truncate">
                        {holding.symbol}
                      </div>
                    </div>
                    <div className="text-xs text-slate-300 font-medium mb-3">
                      {holding.name}
                    </div>
                    <div className="grid grid-cols-1 gap-2 border-t border-slate-700/50 pt-2">
                      <div className="flex justify-between items-center">
                        <span className="text-[10px] text-slate-500 uppercase tracking-tighter">
                          Gewichtung
                        </span>
                        <span className="text-xs font-bold text-white">
                          {holding.weight.toFixed(2)}%
                        </span>
                      </div>
                      <div className="w-full h-1.5 bg-slate-700 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-indigo-500 rounded-full"
                          style={{
                            width: `${Math.min(100, holding.weight * 5)}%`,
                          }}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-center py-8 text-slate-500 bg-slate-900/20 rounded-xl border border-dashed border-slate-700">
                <Info className="w-8 h-8 mx-auto mb-2 opacity-20" />
                Keine Holdings-Daten verfügbar
              </div>
            )}
          </div>
        </div>

        {/* Right: Pie Chart */}
        <div className="bg-slate-800/30 border border-slate-700/50 rounded-xl p-5 flex flex-col items-center justify-center min-h-[300px]">
          <h3 className="text-sm font-bold text-slate-500 uppercase tracking-widest mb-6 self-start">
            Visualisierung der Allokation
          </h3>
          {analysis.holdings.length > 0 ? (
            <div className="w-full h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <RechartsTooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        return (
                          <div className="bg-slate-900 border border-slate-700 p-3 rounded-lg shadow-xl">
                            <div className="text-indigo-400 font-bold">
                              {payload[0].name}
                            </div>
                            <div className="text-[10px] text-slate-400 mb-1">
                              {payload[0].payload.fullName}
                            </div>
                            <div className="text-xs font-bold text-white">
                              {payload[0].value.toFixed(2)}%
                            </div>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={5}
                    dataKey="value"
                  >
                    {pieData.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={COLORS[index % COLORS.length]}
                      />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
              <div className="grid grid-cols-5 gap-2 mt-4 px-2">
                {pieData.slice(0, 5).map((entry, index) => (
                  <div key={entry.name} className="flex flex-col items-center">
                    <div
                      className="w-2 h-2 rounded-full mb-1"
                      style={{ backgroundColor: COLORS[index] }}
                    />
                    <span className="text-[8px] font-bold text-slate-500">
                      {entry.name}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-slate-600 italic text-sm">
              Keine Grafik verfügbar
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ETFComparison;
