import React, { useMemo, useState } from "react";
import PriceChart from "./PriceChart";
import AddHoldingModal from "./AddHoldingModal";
import { Portfolio, Holding } from "../hooks/usePortfolios";
import { Plus, Download, FileText } from "lucide-react";
import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";
import { useCurrency } from "../context/CurrencyContext";
import BrokerChat from "./BrokerChat";
import ETFComparison from "./ETFComparison";
import useRealtimeFeed from "../hooks/useRealtimeFeed";

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
    very_positive: "text-emerald-700",
    positive: "text-emerald-700",
    neutral: "text-amber-700",
    negative: "text-orange-700",
    very_negative: "text-red-700",
  };
  return colors[rating] || "text-slate-500";
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
  const { quotes: realtimeQuotes, connected: realtimeConnected } = useRealtimeFeed([data.ticker], true);

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
  const liveQuote = realtimeQuotes[data.ticker];

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
    <div className="relative flex flex-col gap-6 lg:flex-row">
      {/* Main Analysis Area */}
      <div
        className={`flex-1 transition-all duration-500 ease-in-out ${isPanelOpen ? "lg:mr-96" : ""}`}
      >
        <div className="space-y-6 pb-20">
          {/* Header Info */}
          <div className="surface-panel rounded-[2rem] p-6">
            <div className="mb-5 flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-[var(--accent-soft)] px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-[var(--accent)]">
                Analysis Desk
              </span>
              <span className={`rounded-full px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] ${realtimeConnected ? "bg-emerald-500/10 text-emerald-700" : "border border-black/8 bg-white/70 text-slate-500"}`}>
                {realtimeConnected ? "Live quote" : "Snapshot"}
              </span>
              {fundamentals?.sector ? (
                <span className="rounded-full border border-black/8 bg-white/70 px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                  {fundamentals.sector}
                </span>
              ) : null}
            </div>
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
              <div className="flex items-center gap-4">
                <div className="flex h-16 w-16 items-center justify-center rounded-[1.4rem] bg-[var(--accent)] text-2xl font-bold text-white">
                  {data.ticker?.slice(0, 2)}
                </div>
                <div>
                  <h2 className="text-3xl text-slate-900">
                    {data.company_name}
                  </h2>
                  <div className="flex items-center gap-3 mt-1">
                    <span className="text-slate-500">{data.ticker}</span>
                    <span className="text-gray-600">•</span>
                    <span className="text-slate-500">
                      {fundamentals?.sector}
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex flex-col md:flex-row gap-3">
                <button
                  onClick={exportToPDF}
                  className="flex items-center justify-center gap-2 rounded-xl border border-black/8 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition-all hover:bg-black/[0.03]"
                >
                  <Download size={16} /> Broker-Dossier (PDF)
                </button>
                <div className="text-right flex flex-col items-end gap-3">
                  <div className="flex items-center gap-3">
                    {!isPanelOpen && (
                      <button
                        onClick={() => setIsPanelOpen(true)}
                        className="flex items-center gap-2 rounded-xl bg-[var(--accent)] px-4 py-2 text-xs font-bold text-white transition-all hover:bg-[var(--accent-strong)]"
                      >
                        <FileText size={14} /> Summary einblenden
                      </button>
                    )}
                    <div className="text-right">
                      <div className="text-3xl font-bold text-slate-900">
                        {formatPrice(liveQuote?.price ?? price_data?.current_price)}
                      </div>
                      <div
                        className={`text-lg ${(chartStats?.changePct ?? price_data?.change_1y ?? 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}
                      >
                        {formatPercent(
                          chartStats?.changePct ?? price_data?.change_1y,
                        )}{" "}
                        ({chartStats?.label ?? "1Y"})
                      </div>
                      <div className={`mt-1 text-[10px] font-extrabold uppercase tracking-[0.16em] ${realtimeConnected ? "text-emerald-700" : "text-slate-500"}`}>
                        {realtimeConnected ? "Live quote" : "Snapshot"}
                      </div>
                    </div>
                  </div>
                  {portfolios.length > 0 && (
                    <button
                      onClick={() => setIsModalOpen(true)}
                      className="flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--accent)] px-4 py-2 text-sm font-bold text-white transition-all hover:bg-[var(--accent-strong)] md:w-auto"
                    >
                      <Plus size={16} /> Portfolio hinzufuegen
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
                className={`rounded-2xl border p-6 transition-all ${data.risk_audit.red_flags.length > 0 ? "bg-red-500/5 border-red-500/20 shadow-lg shadow-red-500/5" : "bg-emerald-500/5 border-emerald-500/20"}`}
              >
                <h3 className="mb-4 flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-red-700">
                  <Plus size={14} className="rotate-45" /> Risiko-Audit
                </h3>
                {data.risk_audit.red_flags.length > 0 ? (
                  <div className="space-y-3">
                    {data.risk_audit.red_flags.map((flag: any, i: number) => (
                      <div
                        key={i}
                        className="text-sm font-medium text-slate-700"
                      >
                        ● {flag.flag}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm font-bold text-emerald-700">
                    Keine kritischen Warnsignale gefunden.
                  </div>
                )}
              </div>
              <div className="rounded-2xl border border-sky-500/20 bg-sky-500/5 p-6 shadow-lg shadow-sky-500/5">
                <h3 className="mb-4 flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-sky-700">
                  <Plus size={14} /> Highlights
                </h3>
                <div className="space-y-3 text-sm font-medium text-slate-700">
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
              <div className="glass-card rounded-2xl border-t-4 border-emerald-600/40 p-6">
                <h3 className="text-xl font-bold mb-4 flex items-center gap-2">
                  <span className="text-[var(--accent)]">Potential</span> Growth Potential
                </h3>
                <div className="space-y-4">
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-slate-500">Potential Score</span>
                    <span className="font-bold text-emerald-700">
                      {data.potential.score.toFixed(0)}/100
                    </span>
                  </div>
                  <p className="text-sm italic text-slate-600">
                    "{data.potential.summary}"
                  </p>
                </div>
              </div>
            )}
            {data.rebound && data.rebound.score > 0 && (
              <div className="glass-card rounded-2xl border-t-4 border-amber-600/40 p-6">
                <h3 className="text-xl font-bold mb-4 flex items-center gap-2">
                  <span className="text-amber-700">Rebound</span> Rebound Setup
                </h3>
                <div className="space-y-4">
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-slate-500">Recovery Signal</span>
                    <span className="font-bold text-amber-700">
                      {data.rebound.score.toFixed(0)}/100
                    </span>
                  </div>
                  <p className="text-sm italic text-slate-600">
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
                    className={`rounded-md px-2 py-1 text-xs font-bold ${section.score > 20 ? "bg-emerald-500/10 text-emerald-700" : section.score < -20 ? "bg-red-500/10 text-red-700" : "bg-amber-500/10 text-amber-700"}`}
                  >
                    {section.score.toFixed(0)}
                  </span>
                </div>
                <p className="mb-4 h-10 line-clamp-2 text-sm text-slate-500">
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
                        <span className="text-slate-500">{finding.metric}</span>
                        <span
                          className={`font-medium ${finding.rating?.includes("positive") ? "text-emerald-700" : finding.rating?.includes("negative") ? "text-red-700" : "text-slate-600"}`}
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
                className="surface-panel rounded-xl p-4"
              >
                <div className="text-slate-500 text-[10px] font-bold uppercase tracking-widest mb-1">
                  {item.label}
                </div>
                <div
                  className={`text-xl font-mono font-bold ${(item.value || 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}
                >
                  {formatPercent(item.value)}
                </div>
              </div>
            ))}
          </div>

          <NewsFeed news={news} />

          <div className="surface-panel rounded-xl p-6">
            <p className="text-slate-500 text-sm text-center">
              Die Analyse dient nur zu Informationszwecken und stellt keine
              Anlageberatung dar.
            </p>
          </div>
        </div>
      </div>

      {/* Side Panel */}
      <div
        className={`fixed top-20 right-0 h-[calc(100vh-80px)] border-l border-black/8 bg-[rgba(250,248,244,0.94)] backdrop-blur-3xl transition-all duration-500 ease-in-out z-40 overflow-hidden shadow-[-20px_0_50px_rgba(17,24,39,0.12)] ${isPanelOpen ? "w-full lg:w-96 opacity-100" : "w-0 opacity-0 pointer-events-none"}`}
      >
        <div className="p-8 h-full flex flex-col pt-10">
          <div className="mb-10 flex items-center justify-between text-slate-900">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--accent)] text-white shadow-xl">
                <span className="text-xl font-black">AI</span>
              </div>
              <div>
                <h3 className="text-xl font-black text-slate-900 leading-none tracking-tight">
                  Broker Freund
                </h3>
                <div className="flex items-center gap-2 mt-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse"></span>
                  <p className="text-[10px] text-slate-500 uppercase font-bold tracking-[0.2em]">
                    Live • AI Analysis
                  </p>
                </div>
              </div>
            </div>
            <button
              onClick={() => setIsPanelOpen(false)}
              className="rounded-2xl border border-black/8 p-3 transition-all hover:bg-black/[0.04]"
            >
              <Plus size={24} className="rotate-45 text-slate-500" />
            </button>
          </div>

          <div className="space-y-8 flex-1 overflow-y-auto pr-2 custom-scrollbar pb-10">
            <div className="relative overflow-hidden rounded-3xl border border-black/8 bg-white/80 p-6 text-center group">
              <div className="absolute top-0 left-0 h-1 w-full bg-linear-to-r from-transparent via-emerald-600 to-transparent opacity-40"></div>
              <div className="mb-2 text-6xl font-black tracking-tighter text-slate-900">
                {total_score?.toFixed(0)}
              </div>
              <div className="mb-4 text-[10px] font-bold uppercase tracking-widest text-slate-500">
                Pro Score
              </div>
              <div
                className={`inline-block rounded-full px-4 py-1.5 text-xs font-black uppercase tracking-widest ${total_score > 70 ? "bg-green-500/12 text-green-700" : "bg-red-500/12 text-red-700"}`}
              >
                {recommendation?.action || recommendation}
              </div>
            </div>

            <div className="space-y-4">
              <h4 className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-slate-500">
                <span className="w-2 h-2 rounded-full bg-emerald-600 shadow-[0_0_10px_rgba(5,150,105,0.25)]"></span>
                Meine Einschätzung
              </h4>
              <div className="relative overflow-hidden rounded-3xl border border-black/8 bg-white/80 p-6 shadow-xl">
                <div className="absolute top-0 right-0 w-20 h-20 rounded-full bg-emerald-500/8 blur-3xl"></div>
                <div className="relative z-10 text-sm font-medium leading-relaxed text-slate-700">
                  "{data.verdict}"
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4">
              <div className="flex items-center justify-between rounded-2xl border border-black/8 bg-white/80 p-4">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Technisch
                </span>
                <span className="text-sm font-mono font-bold text-sky-700">
                  {total_score?.toFixed(0)}%
                </span>
              </div>
              <div className="flex items-center justify-between rounded-2xl border border-black/8 bg-white/80 p-4">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Fundament
                </span>
                <span className="text-sm font-mono font-bold text-emerald-700">
                  {total_score?.toFixed(0)}%
                </span>
              </div>
            </div>
          </div>

          <button
            onClick={exportToPDF}
            className="group mt-6 flex w-full items-center justify-center gap-2 rounded-2xl border border-black/8 bg-[var(--accent)] py-4 text-xs font-bold uppercase tracking-widest text-white transition-all hover:bg-[var(--accent-strong)]"
          >
            <Download
              size={16}
              className="text-white/60 transition-colors group-hover:text-white"
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
    <div className="surface-panel rounded-xl p-6">
      <h3 className="mb-6 flex items-center gap-2 text-lg font-bold text-slate-900">
        <FileText size={20} className="text-emerald-700" /> Top News & Sentiment
      </h3>
      <div className="space-y-4">
        {news.slice(0, 5).map((item, i) => (
          <a
            key={i}
            href={item.link}
            target="_blank"
            rel="noopener noreferrer"
            className="block group cursor-pointer rounded-xl border border-black/8 bg-white/70 p-4 transition-all hover:bg-white"
          >
            <h4 className="line-clamp-2 text-sm font-bold text-slate-900 transition-colors group-hover:text-emerald-700">
              {item.title}
            </h4>
            <div className="flex items-center gap-2 mt-2">
              <span className="text-[10px] text-slate-500 font-bold uppercase">
                {item.source || item.publisher}
              </span>
              <span className="text-[10px] text-gray-700 font-bold">•</span>
              <span className="text-[10px] text-slate-500">
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
    <div className="surface-panel relative group rounded-xl p-5 transition-all hover:border-black/12">
      <div className="mb-2 flex items-center justify-between text-[10px] text-slate-500 font-bold uppercase tracking-widest">
        {label}
        {info && (
          <span className="opacity-0 group-hover:opacity-100 transition-opacity">
            ⓘ
          </span>
        )}
      </div>
      <div className="text-xl font-mono font-bold text-slate-900">
        {value ?? "N/A"}
      </div>
      {trend && (
        <div
          className={`mt-2 text-[10px] font-bold ${trend === "up" ? "text-emerald-700" : "text-red-700"}`}
        >
          {trend === "up" ? "↑ Optimiert" : "↓ Unter Bench"}
        </div>
      )}
    </div>
  );
}
