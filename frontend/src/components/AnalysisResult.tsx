import React from "react";
import PriceChart from "./PriceChart";
import AddHoldingModal from "./AddHoldingModal";
import { Portfolio, Holding } from "../hooks/usePortfolios";
import { Plus, Download, FileText } from "lucide-react";
// jsPDF and autoTable are dynamically imported inside exportToPDF to keep the initial bundle small
import { useCurrency } from "../context/CurrencyContext";
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

const clampScore = (value: number | null | undefined): number => {
  if (value == null || !Number.isFinite(value)) return 0;
  return Math.max(-100, Math.min(100, value));
};

export default function AnalysisResult({
  data,
  portfolios,
  onAddHolding,
  onOpenChat,
  onSelectTicker,
}: AnalysisResultProps) {
  const [isModalOpen, setIsModalOpen] = React.useState(false);
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
  const scoreValue = clampScore(total_score);
  const verdictTone =
    scoreValue >= 70
      ? "bg-emerald-500/12 text-emerald-700"
      : scoreValue <= -20
        ? "bg-red-500/12 text-red-700"
        : "bg-amber-500/12 text-amber-700";
  const technicalScore = clampScore(analysis?.technical?.score ?? total_score);
  const fundamentalScore = clampScore(analysis?.fundamental?.score ?? total_score);

  const exportToPDF = async () => {
    const { default: jsPDF } = await import("jspdf");
    const { default: autoTable } = await import("jspdf-autotable");
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
    doc.text("Broker-Freund Einschaetzung", 14, 55);
    doc.setFontSize(11);
    doc.text(
      `Hey! Hier ist meine Analyse fuer dich: ${data.verdict || "Kein Verdict verfuegbar."}`,
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
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_19.5rem] 2xl:grid-cols-[minmax(0,1fr)_21rem] 2xl:gap-8">
      <div className="min-w-0">
        <div className="space-y-6 pb-20">
          {/* Header Info */}
          <div className="surface-panel rounded-[2.4rem] p-6 sm:p-8">
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
            <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(18rem,22rem)] xl:items-center">
              <div className="flex min-w-0 items-center gap-4">
                <div className="flex h-16 w-16 items-center justify-center rounded-[1.4rem] bg-[var(--accent)] text-2xl font-bold text-white">
                  {data.ticker?.slice(0, 2)}
                </div>
                <div className="min-w-0">
                  <h2 className="truncate text-3xl text-slate-900">
                    {data.company_name}
                  </h2>
                  <div className="mt-1 flex flex-wrap items-center gap-3">
                    <span className="text-slate-500">{data.ticker}</span>
                    <span className="text-gray-600">·</span>
                    <span className="text-slate-500">
                      {fundamentals?.sector}
                    </span>
                  </div>
                </div>
              </div>
              <div className="grid gap-4 rounded-[1.8rem] border border-black/8 bg-white/72 p-5">
                <button
                  onClick={exportToPDF}
                  className="flex min-h-[5.6rem] items-center justify-center gap-2 rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-bold text-slate-700 transition-all hover:bg-black/[0.03]"
                >
                  <Download size={16} /> Broker-Dossier (PDF)
                </button>
                <div className="text-right">
                  <div className="text-3xl font-bold text-slate-900">
                    {formatPrice(liveQuote?.price ?? price_data?.current_price)}
                  </div>
                  <div
                    className={`text-lg ${(chartStats?.changePct ?? price_data?.change_1y ?? 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}
                  >
                    {formatPercent(chartStats?.changePct ?? price_data?.change_1y)} ({chartStats?.label ?? "1Y"})
                  </div>
                  <div className={`mt-1 text-[10px] font-extrabold uppercase tracking-[0.16em] ${realtimeConnected ? "text-emerald-700" : "text-slate-500"}`}>
                    {realtimeConnected ? "Live quote" : "Snapshot"}
                  </div>
                </div>
                <div className="flex flex-wrap gap-3">
                  {portfolios.length > 0 && (
                    <button
                      onClick={() => setIsModalOpen(true)}
                      className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-[var(--accent)] px-4 py-3 text-sm font-bold text-white transition-all hover:bg-[var(--accent-strong)]"
                    >
                      <Plus size={16} /> Portfolio hinzufuegen
                    </button>
                  )}
                  <button
                    onClick={onOpenChat}
                    className="flex items-center justify-center gap-2 rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-bold text-slate-700 transition-all hover:bg-black/[0.03]"
                  >
                    <FileText size={14} /> AI Desk
                  </button>
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
                        - {flag.flag}
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
                      <div key={i}>+ {s.signal}</div>
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
              info="Boersenwert"
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

      <aside className="min-w-0 xl:sticky xl:top-[7.25rem] xl:w-full xl:max-w-[21rem] xl:self-start xl:justify-self-end">
        <div className="surface-panel rounded-[2.2rem] p-6 sm:p-7">
          <div className="mb-8 flex items-center gap-4 text-slate-900">
            <div className="flex h-14 w-14 items-center justify-center rounded-[1.35rem] bg-[linear-gradient(145deg,var(--accent),#0f766e)] text-white shadow-[0_18px_40px_rgba(15,118,110,0.24)]">
              <svg
                className="h-7 w-7"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.9"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M4 15.5 8.5 11l3.2 3.2L20 6" />
                <path d="M16 6h4v4" />
                <path d="M5 19h14" opacity="0.55" />
              </svg>
            </div>
            <div>
              <h3 className="text-xl font-black leading-none tracking-tight text-slate-900">
                Broker Freund
              </h3>
              <div className="mt-2 flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse"></span>
                <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">
                  Live | Market Briefing
                </p>
              </div>
            </div>
          </div>

          <div className="space-y-5">
            <div className="relative overflow-hidden rounded-[2rem] border border-black/8 bg-white/80 p-6 text-center">
              <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-transparent via-emerald-600 to-transparent opacity-40"></div>
              <div className="mb-2 text-6xl font-black tracking-tighter text-slate-900">
                {scoreValue.toFixed(0)}
              </div>
              <div className="mb-4 text-[10px] font-bold uppercase tracking-widest text-slate-500">
                Pro Score
              </div>
              <div className={`inline-block rounded-full px-4 py-1.5 text-xs font-black uppercase tracking-widest ${verdictTone}`}>
                {recommendation?.action || recommendation}
              </div>
            </div>

            <div className="rounded-[1.7rem] border border-black/8 bg-white/80 p-5">
              <h4 className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-slate-500">
                <span className="h-2 w-2 rounded-full bg-emerald-600 shadow-[0_0_10px_rgba(5,150,105,0.25)]"></span>
                Meine Einschaetzung
              </h4>
              <div className="mt-4 text-sm font-medium leading-7 text-slate-700">
                "{data.verdict}"
              </div>
            </div>

            <div className="grid gap-3">
              <div className="flex items-center justify-between rounded-[1.4rem] border border-black/8 bg-white/80 p-4">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Technisch
                </span>
                <span className="text-sm font-mono font-bold text-sky-700">
                  {technicalScore.toFixed(0)}%
                </span>
              </div>
              <div className="flex items-center justify-between rounded-[1.4rem] border border-black/8 bg-white/80 p-4">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Fundament
                </span>
                <span className="text-sm font-mono font-bold text-emerald-700">
                  {fundamentalScore.toFixed(0)}%
                </span>
              </div>
            </div>

            <button
              onClick={exportToPDF}
              className="group flex w-full items-center justify-center gap-2 rounded-[1.4rem] border border-black/8 bg-[var(--accent)] py-4 text-xs font-bold uppercase tracking-widest text-white transition-all hover:bg-[var(--accent-strong)]"
            >
              <Download
                size={16}
                className="text-white/60 transition-colors group-hover:text-white"
              />
              Dossier Exportieren
            </button>
          </div>
        </div>
      </aside>
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
              <span className="text-[10px] text-gray-700 font-bold">·</span>
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
          <span className="opacity-0 transition-opacity group-hover:opacity-100">
            i
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


