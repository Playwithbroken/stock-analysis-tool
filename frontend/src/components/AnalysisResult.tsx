import React, { useMemo, useState } from "react";
import PriceChart from "./PriceChart";
import AddHoldingModal from "./AddHoldingModal";
import { Portfolio, Holding } from "../hooks/usePortfolios";
import { Plus, Download, FileText, ShieldCheck } from "lucide-react";
import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";
import { useCurrency } from "../context/CurrencyContext";
import BrokerChat from "./BrokerChat";
import ETFComparison from "./ETFComparison";

interface AnalysisResultProps {
  data: any;
  portfolios: Portfolio[];
  onAddHolding: (portfolioId: string, holding: Holding) => void;
  onOpenChat: () => void;
  onSelectTicker?: (ticker: string) => void;
}

// Helper functions
const formatBigNumber = (
  value: number | null | undefined,
  currencyHelper: (val: number) => string,
): string => {
  if (value == null) return "N/A";
  if (Math.abs(value) >= 1e12) return `${(value / 1e12).toFixed(2)}T`;
  if (Math.abs(value) >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (Math.abs(value) >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  return currencyHelper(value);
};

const formatPercent = (value: number | null | undefined): string => {
  if (value == null) return "N/A";
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
};

const getRatingColor = (rating: string): string => {
  const colors: Record<string, string> = {
    very_positive: "text-emerald-400",
    positive: "text-green-400",
    neutral: "text-yellow-400",
    negative: "text-orange-400",
    very_negative: "text-red-400",
  };
  return colors[rating] || "text-gray-400";
};

export default function AnalysisResult({
  data,
  portfolios,
  onAddHolding,
  onOpenChat,
  onSelectTicker,
}: AnalysisResultProps) {
  const [isModalOpen, setIsModalOpen] = React.useState(false);
  const [isPanelOpen, setIsPanelOpen] = React.useState(true);
  const [chartStats, setChartStats] = React.useState<{
    changePct: number;
    label: string;
  } | null>(null);
  const { formatPrice } = useCurrency();

  const handleStatsUpdate = (
    stats: { change: number; changePct: number },
    label: string,
  ) => {
    setChartStats({ changePct: stats.changePct, label });
  };

  const {
    price_data,
    fundamentals,
    analysis,
    recommendation,
    valuation,
    total_score,
    news,
  } = data;

  const exportToPDF = () => {
    const doc = new jsPDF();
    const pageWidth = doc.internal.pageSize.getWidth();

    // Header
    doc.setFillColor(123, 44, 191);
    doc.rect(0, 0, pageWidth, 40, "F");
    doc.setFontSize(24);
    doc.setTextColor(255, 255, 255);
    doc.text(`Broker-Dossier: ${data.ticker}`, 14, 25);
    doc.setFontSize(10);
    doc.text(
      `Vorbereitet am ${new Date().toLocaleDateString()} von deinem Broker Freund`,
      14,
      32,
    );

    // Executive Verdict
    doc.setTextColor(0, 0, 0);
    doc.setFontSize(18);
    doc.text("Broker-Freund Einschätzung", 14, 55);
    doc.setFontSize(11);
    doc.text(
      `Hey! Hier ist meine Analyse für dich: ${data.verdict || "Kein Verdict verfügbar."}`,
      14,
      62,
      { maxWidth: pageWidth - 28 },
    );

    // Summary Box
    doc.setFillColor(245, 245, 248);
    doc.rect(14, 75, pageWidth - 28, 30, "F");
    doc.setFontSize(12);
    doc.text(`Performance Score: ${total_score?.toFixed(1)} / 100`, 20, 85);
    doc.text(`Market Valuation: ${valuation || "N/A"}`, 20, 92);
    doc.text(
      `Action Recommendation: ${recommendation?.action || "N/A"}`,
      20,
      99,
    );

    // Fundamentals Table
    autoTable(doc, {
      startY: 115,
      head: [["Metric", "Value", "Benchmark Status"]],
      body: [
        [
          "Market Cap",
          formatBigNumber(fundamentals?.market_cap, formatPrice),
          fundamentals?.market_cap > 100e9 ? "Mega Cap" : "Mainstream",
        ],
        [
          "P/E Ratio",
          fundamentals?.pe_ratio?.toFixed(2) || "N/A",
          fundamentals?.pe_ratio < 20 ? "Undervalued" : "Premium",
        ],
        [
          "Rev Growth",
          formatPercent(fundamentals?.revenue_growth),
          fundamentals?.revenue_growth > 0.15 ? "High Growth" : "Moderate",
        ],
        [
          "Profit Margin",
          formatPercent(fundamentals?.profit_margin),
          fundamentals?.profit_margin > 0.1 ? "Efficient" : "Thin",
        ],
      ],
      theme: "grid",
      headStyles: { fillColor: [123, 44, 191] },
    });

    doc.save(`${data.ticker}_Research_Dossier.pdf`);
  };

  return (
    <div className="flex flex-col lg:flex-row gap-6 relative">
      {/* Main Analysis Area */}
      <div
        className={`flex-1 transition-all duration-500 ease-in-out ${isPanelOpen ? "lg:mr-96" : ""}`}
      >
        <div className="space-y-6 pb-20">
          {/* Header Info */}
          <div className="bg-linear-to-r from-[#0a0a0c] to-black rounded-2xl p-6 border border-white/5">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
              <div className="flex items-center gap-4">
                <div className="w-16 h-16 bg-linear-to-br from-purple-500 to-indigo-600 rounded-xl flex items-center justify-center text-2xl font-bold text-white shadow-lg shadow-purple-500/20">
                  {data.ticker?.slice(0, 2)}
                </div>
                <div>
                  <h2 className="text-2xl font-bold text-white">
                    {data.company_name}
                  </h2>
                  <div className="flex items-center gap-3 mt-1">
                    <span className="text-gray-400">{data.ticker}</span>
                    <span className="text-gray-600">•</span>
                    <span className="text-gray-400">
                      {fundamentals?.sector}
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex flex-col md:flex-row gap-3">
                <button
                  onClick={exportToPDF}
                  className="px-4 py-2 bg-white/5 hover:bg-white/10 text-gray-300 rounded-xl text-sm font-bold transition-all flex items-center justify-center gap-2 border border-white/10"
                >
                  <Download size={16} /> Broker-Dossier (PDF)
                </button>
                <div className="text-right flex flex-col items-end gap-3">
                  <div className="flex items-center gap-3">
                    {!isPanelOpen && (
                      <button
                        onClick={() => setIsPanelOpen(true)}
                        className="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-xl text-xs font-bold transition-all shadow-lg shadow-purple-500/20 flex items-center gap-2"
                      >
                        <FileText size={14} /> Summary einblenden
                      </button>
                    )}
                    <div className="text-right">
                      <div className="text-3xl font-bold text-white">
                        {formatPrice(price_data?.current_price)}
                      </div>
                      <div
                        className={`text-lg ${(chartStats?.changePct ?? price_data?.change_1y ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}
                      >
                        {formatPercent(
                          chartStats?.changePct ?? price_data?.change_1y,
                        )}{" "}
                        ({chartStats?.label ?? "1Y"})
                      </div>
                    </div>
                  </div>
                  {portfolios.length > 0 && (
                    <button
                      onClick={() => setIsModalOpen(true)}
                      className="w-full md:w-auto px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-xl text-sm font-bold transition-all flex items-center justify-center gap-2 shadow-lg shadow-purple-500/20"
                    >
                      <Plus size={16} /> Portfolio hinzufügen
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>

          <AddHoldingModal
            isOpen={isModalOpen}
            onClose={() => setIsModalOpen(false)}
            onAdd={onAddHolding}
            portfolios={portfolios}
            initialTicker={data.ticker}
            initialPrice={price_data?.current_price}
          />

          {/* Risk Audit */}
          {data.risk_audit && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div
                className={`rounded-2xl p-6 border transition-all ${data.risk_audit.red_flags.length > 0 ? "bg-red-500/5 border-red-500/20 shadow-lg shadow-red-500/5" : "bg-green-500/5 border-green-500/20"}`}
              >
                <h3 className="text-xs font-bold uppercase tracking-widest mb-4 flex items-center gap-2 text-red-400">
                  <Plus size={14} className="rotate-45" /> Risiko-Audit
                </h3>
                {data.risk_audit.red_flags.length > 0 ? (
                  <div className="space-y-3">
                    {data.risk_audit.red_flags.map((flag: any, i: number) => (
                      <div
                        key={i}
                        className="text-sm font-medium text-gray-300"
                      >
                        ● {flag.flag}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm text-green-400 font-bold">
                    Keine kritischen Warnsignale gefunden.
                  </div>
                )}
              </div>
              <div className="bg-blue-500/5 rounded-2xl p-6 border border-blue-500/20 shadow-lg shadow-blue-500/5">
                <h3 className="text-xs font-bold uppercase tracking-widest mb-4 flex items-center gap-2 text-blue-400">
                  <Plus size={14} /> Highlights
                </h3>
                <div className="space-y-3 font-medium text-gray-300 text-sm">
                  {data.risk_audit.positive_signals?.map(
                    (s: any, i: number) => (
                      <div key={i}>★ {s.signal}</div>
                    ),
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Price Chart */}
          <PriceChart ticker={data.ticker} onStatsUpdate={handleStatsUpdate} />

          {/* ETF Analysis Section */}
          {data.etf_analysis && (
            <ETFComparison
              analysis={data.etf_analysis}
              onSelectTicker={onSelectTicker}
            />
          )}

          {/* Metrics Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MetricCard
              label="Market Cap"
              value={formatBigNumber(fundamentals?.market_cap, formatPrice)}
              info="Börsenwert"
            />
            <MetricCard
              label="P/E Ratio"
              value={fundamentals?.pe_ratio?.toFixed(2)}
              trend={fundamentals?.pe_ratio < 20 ? "up" : "down"}
            />
            <MetricCard
              label="Rev Growth"
              value={formatPercent(fundamentals?.revenue_growth)}
              trend="up"
            />
            <MetricCard
              label="Margin"
              value={formatPercent(fundamentals?.profit_margin)}
              trend="up"
            />
          </div>

          {/* Specialized Analysis (Potential & Rebound) */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {data.potential && (
              <div className="glass-card rounded-2xl p-6 border-t-4 border-purple-500/50">
                <h3 className="text-xl font-bold mb-4 flex items-center gap-2">
                  <span className="text-purple-400">🚀</span> Growth Potential
                </h3>
                <div className="space-y-4">
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-gray-400">Potential Score</span>
                    <span className="font-bold text-purple-400">
                      {data.potential.score.toFixed(0)}/100
                    </span>
                  </div>
                  <p className="text-sm text-gray-300 italic">
                    "{data.potential.summary}"
                  </p>
                </div>
              </div>
            )}
            {data.rebound && data.rebound.score > 0 && (
              <div className="glass-card rounded-2xl p-6 border-t-4 border-orange-500/50">
                <h3 className="text-xl font-bold mb-4 flex items-center gap-2">
                  <span className="text-orange-400">📈</span> Rebound Setup
                </h3>
                <div className="space-y-4">
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-gray-400">Recovery Signal</span>
                    <span className="font-bold text-orange-400">
                      {data.rebound.score.toFixed(0)}/100
                    </span>
                  </div>
                  <p className="text-sm text-gray-300 italic">
                    "{data.rebound.summary}"
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Detailed Analysis Blocks */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {Object.entries(analysis).map(([key, section]: [string, any]) => (
              <div
                key={key}
                className="glass-card rounded-2xl p-6 transition-transform hover:scale-[1.01]"
              >
                <div className="flex justify-between items-center mb-4">
                  <h3 className="text-lg font-bold">{section.category}</h3>
                  <span
                    className={`text-xs font-bold px-2 py-1 rounded-md ${section.score > 20 ? "bg-green-500/10 text-green-400" : section.score < -20 ? "bg-red-500/10 text-red-400" : "bg-yellow-500/10 text-yellow-400"}`}
                  >
                    {section.score.toFixed(0)}
                  </span>
                </div>
                <p className="text-sm text-gray-400 mb-4 h-10 line-clamp-2">
                  {section.summary}
                </p>
                <div className="space-y-3">
                  {section.findings
                    ?.slice(0, 3)
                    .map((finding: any, idx: number) => (
                      <div
                        key={idx}
                        className="flex justify-between items-center text-xs"
                      >
                        <span className="text-gray-500">{finding.metric}</span>
                        <span
                          className={`font-medium ${finding.rating?.includes("positive") ? "text-green-400" : finding.rating?.includes("negative") ? "text-red-400" : "text-gray-300"}`}
                        >
                          {finding.value}
                        </span>
                      </div>
                    ))}
                </div>
              </div>
            ))}
          </div>

          {/* Performance Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: "1 Woche", value: price_data?.change_1w },
              { label: "1 Monat", value: price_data?.change_1m },
              { label: "6 Monate", value: price_data?.change_6m },
              { label: "1 Jahr", value: price_data?.change_1y },
            ].map((item) => (
              <div
                key={item.label}
                className="bg-[#050507] rounded-xl p-4 border border-white/5"
              >
                <div className="text-gray-400 text-[10px] font-bold uppercase tracking-widest mb-1">
                  {item.label}
                </div>
                <div
                  className={`text-xl font-mono font-bold ${(item.value || 0) >= 0 ? "text-green-400" : "text-red-400"}`}
                >
                  {formatPercent(item.value)}
                </div>
              </div>
            ))}
          </div>

          <NewsFeed news={news} />

          <div className="bg-[#050507] rounded-xl p-6 border border-white/5">
            <p className="text-gray-500 text-sm text-center">
              Die Analyse dient nur zu Informationszwecken und stellt keine
              Anlageberatung dar.
            </p>
          </div>
        </div>
      </div>

      {/* Side Panel */}
      <div
        className={`fixed top-20 right-0 h-[calc(100vh-80px)] bg-black/95 backdrop-blur-3xl border-l border-white/10 transition-all duration-500 ease-in-out z-40 overflow-hidden shadow-[-20px_0_50px_rgba(0,0,0,0.5)] ${isPanelOpen ? "w-full lg:w-96 opacity-100" : "w-0 opacity-0 pointer-events-none"}`}
      >
        <div className="p-8 h-full flex flex-col pt-10">
          <div className="flex justify-between items-center mb-10 text-white">
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 bg-linear-to-br from-indigo-500 to-purple-600 rounded-2xl flex items-center justify-center border border-white/10 shadow-2xl">
                <span className="text-3xl">🤖</span>
              </div>
              <div>
                <h3 className="text-xl font-black text-white leading-none tracking-tight">
                  Broker Freund
                </h3>
                <div className="flex items-center gap-2 mt-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse"></span>
                  <p className="text-[10px] text-purple-400 uppercase font-bold tracking-[0.2em]">
                    Live • AI Analysis
                  </p>
                </div>
              </div>
            </div>
            <button
              onClick={() => setIsPanelOpen(false)}
              className="p-3 hover:bg-white/5 rounded-2xl transition-all border border-white/10"
            >
              <Plus size={24} className="rotate-45 text-gray-500" />
            </button>
          </div>

          <div className="space-y-8 flex-1 overflow-y-auto pr-2 custom-scrollbar pb-10">
            <div className="bg-white/2 rounded-3xl p-6 border border-white/5 text-center relative overflow-hidden group">
              <div className="absolute top-0 left-0 w-full h-1 bg-linear-to-r from-transparent via-purple-500 to-transparent opacity-50"></div>
              <div className="text-6xl font-black text-white mb-2 tracking-tighter">
                {total_score?.toFixed(0)}
              </div>
              <div className="text-[10px] text-gray-500 font-bold uppercase tracking-widest mb-4">
                Pro Score
              </div>
              <div
                className={`inline-block px-4 py-1.5 rounded-full text-xs font-black uppercase tracking-widest ${total_score > 70 ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"}`}
              >
                {recommendation?.action || recommendation}
              </div>
            </div>

            <div className="space-y-4">
              <h4 className="text-[10px] font-black text-gray-500 uppercase tracking-widest flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-purple-500 shadow-[0_0_10px_rgba(168,85,247,0.5)]"></span>
                Meine Einschätzung
              </h4>
              <div className="bg-linear-to-br from-[#121214] to-[#0a0a0c] border border-purple-500/20 rounded-3xl p-6 shadow-xl relative overflow-hidden">
                <div className="absolute top-0 right-0 w-20 h-20 bg-purple-500/10 blur-3xl rounded-full"></div>
                <div className="text-sm text-gray-200 leading-relaxed font-medium relative z-10">
                  "{data.verdict}"
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4">
              <div className="bg-white/2 border border-white/5 rounded-2xl p-4 flex items-center justify-between">
                <span className="text-xs font-bold text-white uppercase tracking-wider">
                  Technisch
                </span>
                <span className="text-sm font-mono font-bold text-blue-400">
                  {total_score?.toFixed(0)}%
                </span>
              </div>
              <div className="bg-white/2 border border-white/5 rounded-2xl p-4 flex items-center justify-between">
                <span className="text-xs font-bold text-white uppercase tracking-wider">
                  Fundament
                </span>
                <span className="text-sm font-mono font-bold text-indigo-400">
                  {total_score?.toFixed(0)}%
                </span>
              </div>
            </div>
          </div>

          <button
            onClick={exportToPDF}
            className="mt-6 w-full py-4 bg-white/5 hover:bg-white/10 border border-white/10 text-white rounded-2xl text-xs font-bold uppercase tracking-widest transition-all hover:border-purple-500/30 flex items-center justify-center gap-2 group"
          >
            <Download
              size={16}
              className="text-gray-400 group-hover:text-purple-400 transition-colors"
            />
            Dossier Exportieren
          </button>
        </div>
      </div>
    </div>
  );
}

function NewsFeed({ news }: { news: any[] }) {
  if (!news || news.length === 0) return null;
  return (
    <div className="bg-[#050507] rounded-xl p-6 border border-white/5">
      <h3 className="text-lg font-bold text-white mb-6 flex items-center gap-2">
        <FileText size={20} className="text-purple-400" /> Top News & Sentiment
      </h3>
      <div className="space-y-4">
        {news.slice(0, 5).map((item, i) => (
          <a
            key={i}
            href={item.link}
            target="_blank"
            rel="noopener noreferrer"
            className="block group p-4 rounded-xl border border-white/5 hover:border-purple-500/30 bg-white/2 hover:bg-white/5 transition-all cursor-pointer"
          >
            <h4 className="text-sm font-bold text-gray-100 group-hover:text-purple-300 transition-colors line-clamp-2">
              {item.title}
            </h4>
            <div className="flex items-center gap-2 mt-2">
              <span className="text-[10px] text-gray-500 font-bold uppercase">
                {item.source || item.publisher}
              </span>
              <span className="text-[10px] text-gray-700 font-bold">•</span>
              <span className="text-[10px] text-gray-500">
                {item.time || item.published}
              </span>
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  trend,
  info,
}: {
  label: string;
  value: any;
  trend?: "up" | "down";
  info?: string;
}) {
  return (
    <div className="bg-[#050507] rounded-xl p-5 border border-white/5 relative group hover:border-white/10 transition-all">
      <div className="text-[10px] text-gray-500 font-bold uppercase tracking-widest mb-2 flex items-center justify-between">
        {label}
        {info && (
          <span className="opacity-0 group-hover:opacity-100 transition-opacity">
            ⓘ
          </span>
        )}
      </div>
      <div className="text-xl font-mono font-bold text-white">
        {value ?? "N/A"}
      </div>
      {trend && (
        <div
          className={`mt-2 text-[10px] font-bold ${trend === "up" ? "text-green-500" : "text-red-500"}`}
        >
          {trend === "up" ? "↑ Optimiert" : "↓ Unter Bench"}
        </div>
      )}
    </div>
  );
}
