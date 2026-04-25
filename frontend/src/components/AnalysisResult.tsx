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

const formatRatioPercent = (value: number | null | undefined): string => {
  if (value == null || !Number.isFinite(value)) return "N/A";
  const percent = Math.abs(value) <= 1 ? value * 100 : value;
  const sign = percent >= 0 ? "+" : "";
  return `${sign}${percent.toFixed(1)}%`;
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

const scoreTone = (value: number | null | undefined): string => {
  const score = clampScore(value);
  if (score >= 65) return "border-emerald-500/20 bg-emerald-500/10 text-emerald-800";
  if (score <= 35) return "border-red-500/20 bg-red-500/10 text-red-800";
  return "border-amber-500/20 bg-amber-500/10 text-amber-800";
};

const metricTone = (value: number | null | undefined, positiveAbove = 0): string => {
  if (value == null || !Number.isFinite(value)) return "text-slate-500";
  return value >= positiveAbove ? "text-emerald-700" : "text-red-700";
};

export default function AnalysisResult({
  data,
  portfolios,
  onAddHolding,
  onOpenChat,
  onSelectTicker,
}: AnalysisResultProps) {
  const [isModalOpen, setIsModalOpen] = React.useState(false);
  const [alertModalOpen, setAlertModalOpen] = React.useState(false);
  const [alertDirection, setAlertDirection] = React.useState<"above" | "below">("above");
  const [alertTarget, setAlertTarget] = React.useState("");
  const [alertBusy, setAlertBusy] = React.useState(false);
  const [alertStatus, setAlertStatus] = React.useState<string | null>(null);
  const [isInWatchlist, setIsInWatchlist] = React.useState(false);
  const [watchlistBusy, setWatchlistBusy] = React.useState(false);
  const [chartStats, setChartStats] = React.useState<{
    changePct: number;
    label: string;
  } | null>(null);
  const { formatPrice } = useCurrency();
  const { quotes: realtimeQuotes, connected: realtimeConnected } = useRealtimeFeed([data.ticker], true);

  const handleStatsUpdate = React.useCallback((
    stats: { change: number; changePct: number },
    label: string,
  ) => {
    setChartStats({ changePct: stats.changePct, label });
  }, []);

  const {
    price_data,
    fundamentals,
    analysis,
    recommendation,
    valuation,
    total_score,
    news,
    earnings_history,
    guidance_signal,
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
  const financialStatements = fundamentals?.financial_statements || {};
  const annualFinancials = Array.isArray(financialStatements?.annual)
    ? financialStatements.annual
    : [];
  const financialTrends = financialStatements?.trends || {};
  const latestAnnual = annualFinancials[0] || {};
  const earningsHistory = Array.isArray(earnings_history) ? earnings_history : [];
  const latestEarnings = earningsHistory[0] || null;
  const guidanceSignal = guidance_signal || {};
  const quarterlyRevenueYoY = financialTrends?.quarterly_revenue_yoy;
  const analystData = data.analyst_data || {};
  const shortInterest = data.short_interest || {};
  const currentPrice = Number(liveQuote?.price ?? price_data?.current_price ?? 0);
  const targetMeanPrice = Number(analystData?.target_mean_price ?? analystData?.targetMeanPrice ?? 0);
  const analystUpside =
    currentPrice > 0 && targetMeanPrice > 0 ? ((targetMeanPrice / currentPrice) - 1) * 100 : null;
  const netDebt = latestAnnual?.net_debt;
  const freeCashflow = latestAnnual?.free_cashflow ?? fundamentals?.free_cashflow;
  const fcfYield =
    fundamentals?.market_cap && freeCashflow ? (Number(freeCashflow) / Number(fundamentals.market_cap)) * 100 : null;
  const qualityScore = Math.round(
    [
      fundamentals?.profit_margin != null && fundamentals.profit_margin > 0 ? 18 : 0,
      fundamentals?.revenue_growth != null && fundamentals.revenue_growth > 0 ? 18 : 0,
      fundamentals?.free_cashflow != null && fundamentals.free_cashflow > 0 ? 18 : 0,
      financialTrends?.revenue_cagr != null && financialTrends.revenue_cagr > 0 ? 16 : 0,
      fundamentals?.debt_to_equity != null && fundamentals.debt_to_equity < 120 ? 14 : 0,
      latestEarnings?.status === "beat" ? 16 : latestEarnings?.status === "miss" ? -10 : 0,
    ].reduce((sum, value) => sum + value, 10),
  );
  const valuationPressure = [
    fundamentals?.pe_ratio && fundamentals.pe_ratio > 35 ? "P/E hoch, Bewertung braucht Wachstum." : null,
    fundamentals?.ps_ratio && fundamentals.ps_ratio > 8 ? "Sales-Multiple hoch, Umsatz muss liefern." : null,
    fundamentals?.peg_ratio && fundamentals.peg_ratio > 2 ? "PEG deutet auf teure Wachstumserwartung." : null,
  ].filter(Boolean);
  const dossierCatalysts = [
    latestEarnings
      ? `Letzte Earnings: ${latestEarnings.status || "n/a"} (${formatPercent(latestEarnings.eps_surprise_pct)} EPS surprise).`
      : null,
    guidanceSignal?.label && guidanceSignal.label !== "No signal"
      ? `Guidance: ${guidanceSignal.label}.`
      : null,
    quarterlyRevenueYoY != null ? `Quartalsumsatz YoY: ${formatRatioPercent(quarterlyRevenueYoY)}.` : null,
    analystUpside != null ? `Analysten-Upside zum Mittelziel: ${formatPercent(analystUpside)}.` : null,
    news?.[0]?.title ? `Top-News: ${news[0].title}` : null,
  ].filter(Boolean);
  const dossierRisks = [
    valuationPressure[0],
    financialTrends?.revenue_yoy != null && financialTrends.revenue_yoy < 0 ? "Jahresumsatz ruecklaeufig." : null,
    fundamentals?.earnings_growth != null && fundamentals.earnings_growth < 0 ? "Gewinnwachstum negativ." : null,
    latestEarnings?.status === "miss" ? "Letzte Earnings lagen unter Erwartung." : null,
    shortInterest?.short_percent_float != null && shortInterest.short_percent_float > 8
      ? "Erhoehtes Short Interest kann Volatilitaet treiben."
      : null,
  ].filter(Boolean);
  const dossierQuestions = [
    "Wachsen Umsatz und Margen gleichzeitig oder nur eines von beiden?",
    "Ist der naechste Kursimpuls earnings-, produkt- oder makrogetrieben?",
    "Rechtfertigt die Bewertung das aktuelle Wachstumstempo?",
    "Wo liegt die technische Invalidierung, falls der Markt gegen das Setup dreht?",
  ];

  React.useEffect(() => {
    let cancelled = false;
    const loadWatchlistState = async () => {
      try {
        const response = await fetch("/api/signals/watchlist");
        if (!response.ok) return;
        const payload = await response.json();
        const items = Array.isArray(payload?.items) ? payload.items : [];
        const exists = items.some(
          (item: any) =>
            String(item?.kind || "").toLowerCase() === "ticker" &&
            String(item?.value || "").toUpperCase() === String(data.ticker || "").toUpperCase(),
        );
        if (!cancelled) setIsInWatchlist(exists);
      } catch {
        if (!cancelled) setIsInWatchlist(false);
      }
    };
    loadWatchlistState();
    return () => {
      cancelled = true;
    };
  }, [data.ticker]);

  const toggleWatchlist = async () => {
    if (watchlistBusy) return;
    setWatchlistBusy(true);
    setAlertStatus(null);
    try {
      if (isInWatchlist) {
        const params = new URLSearchParams({
          kind: "ticker",
          value: data.ticker,
        });
        const response = await fetch(`/api/signals/watchlist/items?${params.toString()}`, {
          method: "DELETE",
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        setIsInWatchlist(false);
        setAlertStatus(`${data.ticker} aus Watchlist entfernt.`);
      } else {
        const response = await fetch("/api/signals/watchlist/items", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kind: "ticker", value: data.ticker }),
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        setIsInWatchlist(true);
        setAlertStatus(`${data.ticker} zur Watchlist hinzugefuegt.`);
      }
    } catch {
      setAlertStatus("Watchlist konnte nicht aktualisiert werden.");
    } finally {
      setWatchlistBusy(false);
    }
  };

  const openAlertModal = () => {
    const livePrice = Number(liveQuote?.price ?? price_data?.current_price ?? 0);
    if (Number.isFinite(livePrice) && livePrice > 0) {
      const base = alertDirection === "above" ? livePrice * 1.01 : livePrice * 0.99;
      setAlertTarget(base.toFixed(2));
    }
    setAlertModalOpen(true);
  };

  const createPriceAlert = async () => {
    if (alertBusy) return;
    const target = Number(alertTarget);
    if (!Number.isFinite(target) || target <= 0) {
      setAlertStatus("Bitte ein gueltiges Alert-Level eingeben.");
      return;
    }
    setAlertBusy(true);
    try {
      const response = await fetch("/api/alerts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: data.ticker,
          direction: alertDirection,
          target_price: target,
          enabled: true,
          cooldown_minutes: 5,
        }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setAlertModalOpen(false);
      setAlertStatus(`Alert gesetzt: ${data.ticker} ${alertDirection} ${target.toFixed(2)}`);
    } catch {
      setAlertStatus("Price Alert konnte nicht erstellt werden.");
    } finally {
      setAlertBusy(false);
    }
  };

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
          formatRatioPercent(fundamentals?.revenue_growth),
          fundamentals?.revenue_growth > 0.15 ? "High Growth" : "Moderate",
        ],
        [
          "Profit Margin",
          formatRatioPercent(fundamentals?.profit_margin),
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
          <div className="surface-panel overflow-hidden rounded-[2.4rem] p-5 sm:p-8">
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
            <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,22rem)] lg:items-center">
              <div className="flex min-w-0 items-start gap-3 sm:items-center sm:gap-4">
                <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-[1.2rem] bg-[var(--accent)] text-xl font-bold text-white sm:h-16 sm:w-16 sm:rounded-[1.4rem] sm:text-2xl">
                  {data.ticker?.slice(0, 2)}
                </div>
                <div className="min-w-0">
                  <h2 className="truncate text-2xl text-slate-900 sm:text-3xl">
                    {data.company_name}
                  </h2>
                  <div className="mt-1 flex flex-wrap items-center gap-2 sm:gap-3">
                    <span className="text-slate-500">{data.ticker}</span>
                    <span className="text-gray-600">·</span>
                    <span className="text-slate-500">
                      {fundamentals?.sector}
                    </span>
                  </div>
                </div>
              </div>
              <div className="grid gap-4 rounded-[1.8rem] border border-black/8 bg-white/72 p-4 sm:p-5">
                <button
                  onClick={exportToPDF}
                  className="flex min-h-[4.5rem] items-center justify-center gap-2 rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-bold text-slate-700 transition-all hover:bg-black/[0.03] sm:min-h-[5.6rem]"
                >
                  <Download size={16} /> Broker-Dossier (PDF)
                </button>
                <div className="text-left sm:text-right">
                  <div className="text-2xl font-bold text-slate-900 sm:text-3xl">
                    {formatPrice(liveQuote?.price ?? price_data?.current_price)}
                  </div>
                  <div
                    className={`text-base sm:text-lg ${(chartStats?.changePct ?? price_data?.change_1y ?? 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}
                  >
                    {formatPercent(chartStats?.changePct ?? price_data?.change_1y)} ({chartStats?.label ?? "1Y"})
                  </div>
                  <div className={`mt-1 text-[10px] font-extrabold uppercase tracking-[0.16em] ${realtimeConnected ? "text-emerald-700" : "text-slate-500"}`}>
                    {realtimeConnected ? "Live quote" : "Snapshot"}
                  </div>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <button
                    onClick={() => setIsModalOpen(true)}
                    className="flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--accent)] px-4 py-3 text-sm font-bold text-white transition-all hover:bg-[var(--accent-strong)]"
                  >
                    <Plus size={16} /> Portfolio hinzufügen
                  </button>
                  <button
                    onClick={toggleWatchlist}
                    disabled={watchlistBusy}
                    className={`flex w-full items-center justify-center gap-2 rounded-xl border px-4 py-3 text-sm font-bold transition-all ${
                      isInWatchlist
                        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                        : "border-black/8 bg-white text-slate-700 hover:bg-black/[0.03]"
                    }`}
                  >
                    <Plus size={14} />
                    {isInWatchlist ? "Watchlist entfernen" : "Zur Watchlist"}
                  </button>
                  <button
                    onClick={openAlertModal}
                    className="flex w-full items-center justify-center gap-2 rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-bold text-slate-700 transition-all hover:bg-black/[0.03]"
                  >
                    Alert setzen
                  </button>
                  <button
                    onClick={onOpenChat}
                    className="flex w-full items-center justify-center gap-2 rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-bold text-slate-700 transition-all hover:bg-black/[0.03]"
                  >
                    <FileText size={14} /> AI Desk
                  </button>
                </div>
                {alertStatus ? (
                  <div className="rounded-xl border border-black/8 bg-white/70 px-3 py-2 text-xs font-semibold text-slate-600">
                    {alertStatus}
                  </div>
                ) : null}
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

          {alertModalOpen ? (
            <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 px-4">
              <div className="surface-panel w-full max-w-md rounded-[1.6rem] p-6">
                <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                  Price Alert
                </div>
                <h3 className="mt-2 text-2xl text-slate-900">{data.ticker} Alert setzen</h3>
                <div className="mt-5 grid gap-3 sm:grid-cols-2">
                  <button
                    onClick={() => setAlertDirection("above")}
                    className={`rounded-xl border px-4 py-3 text-sm font-bold ${
                      alertDirection === "above"
                        ? "border-emerald-300 bg-emerald-50 text-emerald-700"
                        : "border-black/8 bg-white text-slate-600"
                    }`}
                  >
                    Above
                  </button>
                  <button
                    onClick={() => setAlertDirection("below")}
                    className={`rounded-xl border px-4 py-3 text-sm font-bold ${
                      alertDirection === "below"
                        ? "border-red-300 bg-red-50 text-red-700"
                        : "border-black/8 bg-white text-slate-600"
                    }`}
                  >
                    Below
                  </button>
                </div>
                <div className="mt-4">
                  <label className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
                    Target Price
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={alertTarget}
                    onChange={(e) => setAlertTarget(e.target.value)}
                    className="mt-2 w-full rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-900"
                  />
                </div>
                <div className="mt-5 flex justify-end gap-3">
                  <button
                    onClick={() => setAlertModalOpen(false)}
                    className="rounded-xl border border-black/8 bg-white px-4 py-2.5 text-xs font-extrabold uppercase tracking-[0.14em] text-slate-700"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={createPriceAlert}
                    disabled={alertBusy}
                    className="rounded-xl bg-[var(--accent)] px-4 py-2.5 text-xs font-extrabold uppercase tracking-[0.14em] text-white disabled:opacity-50"
                  >
                    {alertBusy ? "Speichert..." : "Alert speichern"}
                  </button>
                </div>
              </div>
            </div>
          ) : null}

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

          <section className="surface-panel rounded-[2rem] p-5 sm:p-7">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                  Dossier Intelligence
                </div>
                <h3 className="mt-2 text-3xl text-slate-900">
                  Was fuer diese Aktie wirklich wichtig ist
                </h3>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                  Kompakte Investment-Story aus Fundamentaldaten, Earnings, Bewertung, Analysten, News und Risiko.
                  Keine Kaufempfehlung, sondern ein besserer Entscheidungsrahmen.
                </p>
              </div>
              <div className={`rounded-full border px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.16em] ${scoreTone(qualityScore)}`}>
                Quality {Math.max(0, Math.min(100, qualityScore))}/100
              </div>
            </div>

            <div className="mt-6 grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
              <div className="grid gap-4 md:grid-cols-3">
                <div className="rounded-[1.5rem] border border-emerald-500/16 bg-emerald-500/8 p-4">
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-emerald-700">
                    Bull Case
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-700">
                    {fundamentals?.revenue_growth && fundamentals.revenue_growth > 0
                      ? `Wachstum bleibt sichtbar (${formatRatioPercent(fundamentals.revenue_growth)} Revenue Growth), dazu spricht positive Kurs-/Score-Struktur fuer selektive Staerke.`
                      : "Bull Case braucht frische Umsatz- oder Margenbestaetigung, sonst bleibt das Setup nur taktisch."}
                  </p>
                </div>
                <div className="rounded-[1.5rem] border border-amber-500/16 bg-amber-500/8 p-4">
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-amber-700">
                    Base Case
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-700">
                    {recommendation?.action
                      ? `Aktueller App-Case: ${recommendation.action}. Entscheidend ist, ob Trigger und naechster Earnings-/News-Impuls zusammenpassen.`
                      : "Neutraler Case: erst Preisreaktion und Datenbestaetigung abwarten."}
                  </p>
                </div>
                <div className="rounded-[1.5rem] border border-red-500/16 bg-red-500/8 p-4">
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-red-700">
                    Bear Case
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-700">
                    {dossierRisks.length
                      ? dossierRisks.slice(0, 2).join(" ")
                      : "Bear Case entsteht vor allem bei schwacher Anschlussdynamik, negativer Guidance oder breitem Risk-off."}
                  </p>
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <MetricCard label="Revenue Growth" value={formatRatioPercent(fundamentals?.revenue_growth)} trend={(fundamentals?.revenue_growth || 0) >= 0 ? "up" : "down"} />
                <MetricCard label="FCF Yield" value={formatPercent(fcfYield)} trend={(fcfYield || 0) >= 0 ? "up" : "down"} />
                <MetricCard label="Analyst Upside" value={formatPercent(analystUpside)} trend={(analystUpside || 0) >= 0 ? "up" : "down"} />
                <MetricCard label="Net Debt" value={formatBigNumber(netDebt, formatPrice)} />
              </div>
            </div>

            <div className="mt-6 grid gap-4 lg:grid-cols-3">
              <div className="rounded-[1.5rem] border border-black/8 bg-white/74 p-4">
                <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                  Katalysatoren
                </div>
                <div className="mt-3 space-y-2">
                  {dossierCatalysts.length ? dossierCatalysts.slice(0, 5).map((item: any, index: number) => (
                    <div key={`${item}-${index}`} className="rounded-xl bg-black/[0.025] px-3 py-2 text-sm leading-6 text-slate-700">
                      {item}
                    </div>
                  )) : (
                    <div className="text-sm text-slate-500">Keine starken Katalysatoren im aktuellen Datenpaket.</div>
                  )}
                </div>
              </div>
              <div className="rounded-[1.5rem] border border-black/8 bg-white/74 p-4">
                <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                  Risiken / Red Flags
                </div>
                <div className="mt-3 space-y-2">
                  {dossierRisks.length ? dossierRisks.slice(0, 5).map((item: any, index: number) => (
                    <div key={`${item}-${index}`} className="rounded-xl bg-red-500/7 px-3 py-2 text-sm leading-6 text-slate-700">
                      {item}
                    </div>
                  )) : (
                    <div className="text-sm text-slate-500">Keine harten Red Flags aus den Kernkennzahlen erkannt.</div>
                  )}
                </div>
              </div>
              <div className="rounded-[1.5rem] border border-black/8 bg-white/74 p-4">
                <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                  Fragen vor Trade / Kauf
                </div>
                <div className="mt-3 space-y-2">
                  {dossierQuestions.map((item) => (
                    <div key={item} className="rounded-xl bg-[var(--accent-soft)] px-3 py-2 text-sm leading-6 text-slate-700">
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>

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
              value={formatRatioPercent(fundamentals?.revenue_growth)}
              trend="up"
            />
            <MetricCard
              label="Margin"
              value={formatRatioPercent(fundamentals?.profit_margin)}
              trend="up"
            />
          </div>

          {earningsHistory.length > 0 && (
            <section className="surface-panel rounded-[1.6rem] p-5">
              <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                    Earnings vs Erwartung
                  </div>
                  <h3 className="mt-2 text-2xl font-black text-slate-900">
                    Ergebnis, Schätzung und Surprise
                  </h3>
                </div>
                <div
                  className={`rounded-full border px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] ${
                    latestEarnings?.status === "beat"
                      ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700"
                      : latestEarnings?.status === "miss"
                        ? "border-red-500/20 bg-red-500/10 text-red-700"
                        : "border-amber-500/20 bg-amber-500/10 text-amber-700"
                  }`}
                >
                  {latestEarnings?.status === "beat"
                    ? "Beat"
                    : latestEarnings?.status === "miss"
                      ? "Miss"
                      : "In line"}
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <MetricCard
                  label="Reported EPS"
                  value={latestEarnings?.reported_eps != null ? latestEarnings.reported_eps.toFixed(2) : "N/A"}
                  info={latestEarnings?.period}
                />
                <MetricCard
                  label="EPS Estimate"
                  value={latestEarnings?.eps_estimate != null ? latestEarnings.eps_estimate.toFixed(2) : "N/A"}
                />
                <MetricCard
                  label="EPS Surprise"
                  value={formatPercent(latestEarnings?.eps_surprise_pct)}
                  trend={(latestEarnings?.eps_surprise_pct || 0) >= 0 ? "up" : "down"}
                />
                <MetricCard
                  label="4Q Pattern"
                  value={`${earningsHistory.filter((item: any) => item.status === "beat").length} Beat / ${earningsHistory.filter((item: any) => item.status === "miss").length} Miss`}
                />
                <MetricCard
                  label="Revenue YoY"
                  value={formatRatioPercent(quarterlyRevenueYoY)}
                  trend={(quarterlyRevenueYoY || 0) >= 0 ? "up" : "down"}
                />
                <MetricCard
                  label="Forward EPS"
                  value={fundamentals?.forward_eps != null ? fundamentals.forward_eps.toFixed(2) : "N/A"}
                />
                <div className="surface-panel rounded-xl p-5">
                  <div className="mb-2 text-[10px] font-bold uppercase tracking-widest text-slate-500">
                    Guidance
                  </div>
                  <div className="text-sm font-bold text-slate-900">
                    {guidanceSignal?.label || "No signal"}
                  </div>
                  {guidanceSignal?.sentiment === "positive" ? (
                    <div className="mt-2 text-[10px] font-bold text-emerald-700">↑ konstruktiv</div>
                  ) : guidanceSignal?.sentiment === "negative" ? (
                    <div className="mt-2 text-[10px] font-bold text-red-700">↓ Vorsicht</div>
                  ) : null}
                </div>
              </div>

              <div className="mt-4 rounded-[1.2rem] border border-black/8 bg-white/72 p-4 text-sm leading-7 text-slate-600">
                {guidanceSignal?.summary
                  ? guidanceSignal.summary
                  : "Kein klares Guidance-Signal aus den juengsten Headline-Quellen. Deshalb EPS immer zusammen mit Umsatztrend und Preisreaktion lesen."}
              </div>
            </section>
          )}

          {annualFinancials.length > 0 && (
            <section className="surface-panel rounded-[1.6rem] p-5">
              <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                    Financial Statement Intelligence
                  </div>
                  <h3 className="mt-2 text-2xl font-black text-slate-900">
                    Umsatz, Margen und Cashflow
                  </h3>
                </div>
                <div className="rounded-full border border-black/8 bg-white/70 px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                  {financialStatements?.coverage?.annual_periods || annualFinancials.length} Jahresperioden
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
                <MetricCard
                  label="Umsatz"
                  value={formatBigNumber(latestAnnual?.revenue, formatPrice)}
                  info={latestAnnual?.period}
                />
                <MetricCard
                  label="Umsatz YoY"
                  value={formatRatioPercent(financialTrends?.revenue_yoy)}
                  trend={(financialTrends?.revenue_yoy || 0) >= 0 ? "up" : "down"}
                />
                <MetricCard
                  label="Umsatz CAGR"
                  value={formatRatioPercent(financialTrends?.revenue_cagr)}
                  trend={(financialTrends?.revenue_cagr || 0) >= 0 ? "up" : "down"}
                />
                <MetricCard
                  label="Quartal YoY"
                  value={formatRatioPercent(financialTrends?.quarterly_revenue_yoy)}
                  trend={(financialTrends?.quarterly_revenue_yoy || 0) >= 0 ? "up" : "down"}
                />
                <MetricCard
                  label="FCF-Marge"
                  value={formatRatioPercent(latestAnnual?.fcf_margin)}
                  trend={(latestAnnual?.fcf_margin || 0) >= 0 ? "up" : "down"}
                />
                <MetricCard
                  label="Op. Marge"
                  value={formatRatioPercent(latestAnnual?.operating_margin)}
                  trend={(latestAnnual?.operating_margin || 0) >= 0 ? "up" : "down"}
                />
              </div>

              <div className="mt-5 overflow-x-auto">
                <table className="w-full min-w-[680px] text-left text-xs sm:min-w-[760px] sm:text-sm">
                  <thead>
                    <tr className="border-b border-black/8 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                      <th className="py-2 pr-4">Periode</th>
                      <th className="py-2 pr-4">Umsatz</th>
                      <th className="py-2 pr-4">Bruttomarge</th>
                      <th className="py-2 pr-4">Op. Marge</th>
                      <th className="py-2 pr-4">Nettoergebnis</th>
                      <th className="py-2 pr-4">Free Cashflow</th>
                      <th className="py-2 pr-4">Net Debt</th>
                    </tr>
                  </thead>
                  <tbody>
                    {annualFinancials.slice(0, 5).map((row: any) => (
                      <tr key={row.period} className="border-b border-black/5 text-slate-700">
                        <td className="py-3 pr-4 font-bold text-slate-900">{row.period}</td>
                        <td className="py-3 pr-4 font-mono">{formatBigNumber(row.revenue, formatPrice)}</td>
                        <td className="py-3 pr-4 font-mono">{formatRatioPercent(row.gross_margin)}</td>
                        <td className="py-3 pr-4 font-mono">{formatRatioPercent(row.operating_margin)}</td>
                        <td className="py-3 pr-4 font-mono">{formatBigNumber(row.net_income, formatPrice)}</td>
                        <td className="py-3 pr-4 font-mono">{formatBigNumber(row.free_cashflow, formatPrice)}</td>
                        <td className="py-3 pr-4 font-mono">{formatBigNumber(row.net_debt, formatPrice)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

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


