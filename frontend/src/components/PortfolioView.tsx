import { useState, useEffect } from "react";
import PortfolioPerformance from "./PortfolioPerformance";
import PortfolioHeatmap from "./PortfolioHeatmap";
import DividendDashboard from "./DividendDashboard";
import RiskCorrelationMatrix from "./RiskCorrelationMatrix";
import AssetSuggestions from "./AssetSuggestions";
import AddHoldingModal from "./AddHoldingModal";
import { Plus, Download, LayoutGrid, RefreshCw, Trash2 } from "lucide-react";
import { Portfolio, Holding } from "../hooks/usePortfolios";
import { useCurrency } from "../context/CurrencyContext";

interface PortfolioViewProps {
  portfolios: Portfolio[];
  onCreatePortfolio: (name: string) => void;
  onDeletePortfolio: (id: string) => void;
  onAddHolding: (portfolioId: string, holding: Holding) => void;
  onRemoveHolding: (portfolioId: string, ticker: string) => void;
  onAnalyzeStock: (ticker: string) => void;
}

interface PortfolioAnalysis {
  holdings: any[];
  summary: {
    total_value: number;
    total_cost: number;
    gain_loss: number;
    gain_loss_pct: number;
    num_holdings: number;
    avg_score: number;
    sector_allocation: Record<string, number>;
  };
}

const formatPercent = (value: number): string => {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
};

export default function PortfolioView({
  portfolios,
  onCreatePortfolio,
  onDeletePortfolio,
  onAddHolding,
  onRemoveHolding,
  onAnalyzeStock,
}: PortfolioViewProps) {
  const { formatPrice } = useCurrency();
  const [selectedPortfolio, setSelectedPortfolio] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showAddHoldingModal, setShowAddHoldingModal] = useState(false);
  const [newPortfolioName, setNewPortfolioName] = useState("");
  const [newHolding, setNewHolding] = useState({
    ticker: "",
    shares: "",
    buyPrice: "",
  });
  const [analysis, setAnalysis] = useState<PortfolioAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [portfolioVerdict, setPortfolioVerdict] = useState<string | null>(null);

  const currentPortfolio = Array.isArray(portfolios)
    ? portfolios.find((p) => p.id === selectedPortfolio)
    : undefined;

  useEffect(() => {
    if (!selectedPortfolio && portfolios.length > 0) {
      setSelectedPortfolio(portfolios[0].id);
    }
  }, [portfolios, selectedPortfolio]);

  useEffect(() => {
    if (selectedPortfolio && portfolios && Array.isArray(portfolios)) {
      const portfolio = portfolios.find((p) => p.id === selectedPortfolio);
      if (portfolio && portfolio.holdings && portfolio.holdings.length > 0) {
        analyzePortfolio(portfolio);
        fetchPortfolioVerdict(selectedPortfolio);
      } else {
        setAnalysis(null);
        setPortfolioVerdict(null);
      }
    } else {
      setAnalysis(null);
      setPortfolioVerdict(null);
    }
  }, [selectedPortfolio, portfolios]);

  const fetchPortfolioVerdict = async (id: string) => {
    try {
      const res = await fetch(`/api/portfolio/${id}/verdict`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setPortfolioVerdict(data.verdict ?? null);
    } catch {
      setPortfolioVerdict(null);
    }
  };

  const analyzePortfolio = async (portfolio: Portfolio) => {
    if (portfolio.holdings.length === 0) return;

    setLoading(true);
    try {
      const response = await fetch("/api/portfolio/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          holdings: portfolio.holdings.map((h) => ({
            ticker: h.ticker,
            shares: h.shares,
            buy_price: h.buyPrice,
          })),
        }),
      });

      if (response.ok) {
        const data = await response.json();
        setAnalysis(data);
      }
    } catch {
      setAnalysis(null);
    } finally {
      setLoading(false);
    }
  };

  const handleCreatePortfolio = () => {
    if (newPortfolioName.trim()) {
      onCreatePortfolio(newPortfolioName.trim());
      setNewPortfolioName("");
      setShowCreateModal(false);
    }
  };

  const scoreTone = (score: number) =>
    score > 10 ? "text-emerald-700" : score < -10 ? "text-red-700" : "text-amber-700";

  return (
    <div className="space-y-6">
      <section className="surface-panel rounded-[2.4rem] p-6 sm:p-8">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="text-[11px] font-extrabold uppercase tracking-[0.24em] text-slate-500">
              Portfolio Desk
            </div>
            <h1 className="mt-2 text-4xl text-slate-900 sm:text-5xl">
              Built for conviction, not clutter.
            </h1>
            <p className="mt-4 max-w-3xl text-base leading-7 text-slate-600">
              Saubere Uebersicht ueber Holdings, Risiko, Dividenden und Korrelationen in derselben
              visuellen Sprache wie dein Radar und Morning Brief.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => setShowCreateModal(true)}
              className="rounded-[1.2rem] border border-black/8 bg-white px-5 py-3 text-xs font-extrabold uppercase tracking-[0.18em] text-slate-700"
            >
              New portfolio
            </button>
            {currentPortfolio && (
              <button
                onClick={() => setShowAddHoldingModal(true)}
                className="rounded-[1.2rem] bg-[var(--accent)] px-5 py-3 text-xs font-extrabold uppercase tracking-[0.18em] text-white transition-colors hover:bg-[var(--accent-strong)]"
              >
                Add holding
              </button>
            )}
          </div>
        </div>

        <div className="mt-6 grid gap-4 sm:grid-cols-3">
          <div className="rounded-[1.5rem] border border-black/8 bg-white/75 p-5">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
              Portfolio count
            </div>
            <div className="mt-2 text-3xl font-black text-slate-900">{portfolios.length}</div>
          </div>
          <div className="rounded-[1.5rem] border border-black/8 bg-white/75 p-5">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
              Selected
            </div>
            <div className="mt-2 text-xl font-black text-slate-900">
              {currentPortfolio?.name || "No portfolio"}
            </div>
          </div>
          <div className="rounded-[1.5rem] border border-black/8 bg-white/75 p-5">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
              Active holdings
            </div>
            <div className="mt-2 text-3xl font-black text-slate-900">
              {currentPortfolio?.holdings.length || 0}
            </div>
          </div>
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          {portfolios.map((portfolio) => (
            <button
              key={portfolio.id}
              onClick={() => setSelectedPortfolio(portfolio.id)}
              className={`rounded-full px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.16em] transition-all ${
                selectedPortfolio === portfolio.id
                  ? "bg-[var(--accent)] text-white shadow-[0_14px_30px_rgba(15,118,110,0.16)]"
                  : "border border-black/8 bg-white text-slate-600"
              }`}
            >
              {portfolio.name} ({portfolio.holdings.length})
            </button>
          ))}
        </div>
      </section>

      {currentPortfolio ? (
        <div className="space-y-6">
          <section className="surface-panel rounded-[2.2rem] p-6 sm:p-8">
            <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
              <div>
                <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                  Active Portfolio
                </div>
                <h2 className="mt-2 text-4xl text-slate-900">{currentPortfolio.name}</h2>
                <p className="mt-2 text-sm text-slate-500">
                  {currentPortfolio.holdings.length} holdings in the current workspace.
                </p>
              </div>

              <div className="flex flex-wrap gap-3">
                <button
                  onClick={() => currentPortfolio && analyzePortfolio(currentPortfolio)}
                  disabled={loading || currentPortfolio.holdings.length === 0}
                  className="rounded-[1.1rem] border border-black/8 bg-white px-4 py-2.5 text-xs font-extrabold uppercase tracking-[0.16em] text-slate-700 disabled:opacity-50"
                >
                  <span className="inline-flex items-center gap-2">
                    <RefreshCw size={14} />
                    {loading ? "Refreshing" : "Refresh"}
                  </span>
                </button>
                <button
                  onClick={() => window.open(`/api/portfolio/${selectedPortfolio}/export/csv`)}
                  className="rounded-[1.1rem] border border-black/8 bg-white px-4 py-2.5 text-xs font-extrabold uppercase tracking-[0.16em] text-slate-700"
                >
                  <span className="inline-flex items-center gap-2">
                    <Download size={14} />
                    Export csv
                  </span>
                </button>
                <button
                  onClick={() => {
                    if (confirm("Delete this portfolio?")) {
                      onDeletePortfolio(currentPortfolio.id);
                      setSelectedPortfolio(null);
                    }
                  }}
                  className="rounded-[1.1rem] border border-red-200 bg-red-50 px-4 py-2.5 text-xs font-extrabold uppercase tracking-[0.16em] text-red-700"
                >
                  <span className="inline-flex items-center gap-2">
                    <Trash2 size={14} />
                    Delete
                  </span>
                </button>
              </div>
            </div>

            {analysis && (
              <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-[1.5rem] border border-black/8 bg-white/75 p-5">
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                    Total value
                  </div>
                  <div className="mt-2 text-3xl font-black text-slate-900">
                    {formatPrice(analysis.summary.total_value)}
                  </div>
                </div>
                <div className="rounded-[1.5rem] border border-black/8 bg-white/75 p-5">
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                    Gain / loss
                  </div>
                  <div className={`mt-2 text-3xl font-black ${analysis.summary.gain_loss >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                    {formatPrice(analysis.summary.gain_loss)}
                  </div>
                  <div className={`mt-1 text-sm font-bold ${analysis.summary.gain_loss_pct >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                    {formatPercent(analysis.summary.gain_loss_pct)}
                  </div>
                </div>
                <div className="rounded-[1.5rem] border border-black/8 bg-white/75 p-5">
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                    Portfolio score
                  </div>
                  <div className={`mt-2 text-3xl font-black ${scoreTone(analysis.summary.avg_score)}`}>
                    {analysis.summary.avg_score.toFixed(1)}
                  </div>
                </div>
                <div className="rounded-[1.5rem] border border-black/8 bg-white/75 p-5">
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                    Holdings
                  </div>
                  <div className="mt-2 text-3xl font-black text-slate-900">
                    {analysis.summary.num_holdings}
                  </div>
                </div>
              </div>
            )}

            {portfolioVerdict && (
              <div className="mt-6 flex items-start gap-4 rounded-[1.8rem] border border-[var(--accent)]/12 bg-[linear-gradient(135deg,rgba(240,253,250,0.92),rgba(255,255,255,0.9))] p-6 text-slate-900 shadow-[0_18px_45px_rgba(15,23,42,0.08)]">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-[var(--accent)]">
                  <LayoutGrid size={22} />
                </div>
                <div>
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                    Portfolio Verdict
                  </div>
                  <p className="mt-3 text-base leading-7 text-slate-700">{portfolioVerdict}</p>
                </div>
              </div>
            )}
          </section>

          {analysis && analysis.holdings.length > 0 ? (
            <>
              <div className="grid gap-6 lg:grid-cols-2">
                <PortfolioPerformance portfolioId={selectedPortfolio!} />
                <PortfolioHeatmap holdings={analysis.holdings} />
              </div>

              <div className="grid gap-6 lg:grid-cols-2">
                <DividendDashboard portfolioId={selectedPortfolio!} />
                <RiskCorrelationMatrix portfolioId={selectedPortfolio!} />
              </div>

              {selectedPortfolio && (
                <AssetSuggestions
                  portfolioId={selectedPortfolio}
                  onAdd={(ticker: string) => {
                    setNewHolding({ ticker, shares: "1", buyPrice: "" });
                    setShowAddHoldingModal(true);
                  }}
                />
              )}

              {Object.keys(analysis.summary.sector_allocation).length > 0 && (
                <section className="surface-panel rounded-[2rem] p-6">
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                    Sector Allocation
                  </div>
                  <div className="mt-5 space-y-3">
                    {Object.entries(analysis.summary.sector_allocation)
                      .sort((a, b) => b[1] - a[1])
                      .map(([sector, pct]) => (
                        <div key={sector} className="grid items-center gap-3 md:grid-cols-[180px_1fr_70px]">
                          <div className="text-sm font-bold text-slate-800">{sector}</div>
                          <div className="h-2 overflow-hidden rounded-full bg-black/[0.06]">
                            <div
                              className="h-full rounded-full bg-[linear-gradient(90deg,var(--accent),#244f4a)]"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          <div className="text-right text-sm font-bold text-slate-500">
                            {pct.toFixed(1)}%
                          </div>
                        </div>
                      ))}
                  </div>
                </section>
              )}

              <section className="surface-panel overflow-hidden rounded-[2rem] p-0">
                <div className="border-b border-black/6 px-6 py-5">
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                    Holdings
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full">
                    <thead>
                      <tr className="border-b border-black/6 bg-black/[0.02] text-left text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                        <th className="px-6 py-4">Stock</th>
                        <th className="px-4 py-4 text-right">Shares</th>
                        <th className="px-4 py-4 text-right">Price</th>
                        <th className="px-4 py-4 text-right">Value</th>
                        <th className="px-4 py-4 text-right">Gain/Loss</th>
                        <th className="px-4 py-4 text-right">Score</th>
                        <th className="px-4 py-4 text-center">Action</th>
                        <th className="px-6 py-4 text-right">Manage</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analysis.holdings.map((holding) => (
                        <tr key={holding.ticker} className="border-b border-black/6 last:border-b-0 hover:bg-black/[0.02]">
                          <td className="px-6 py-4">
                            <div className="font-extrabold text-slate-900">{holding.ticker}</div>
                            <div className="max-w-[220px] truncate text-sm text-slate-500">{holding.name}</div>
                          </td>
                          <td className="px-4 py-4 text-right text-sm font-semibold text-slate-700">
                            {holding.shares}
                          </td>
                          <td className="px-4 py-4 text-right text-sm font-semibold text-slate-700">
                            {formatPrice(holding.current_price || 0)}
                          </td>
                          <td className="px-4 py-4 text-right text-sm font-extrabold text-slate-900">
                            {formatPrice(holding.position_value || 0)}
                          </td>
                          <td className="px-4 py-4 text-right">
                            <div className={`text-sm font-extrabold ${holding.gain_loss >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                              {formatPrice(holding.gain_loss || 0)}
                            </div>
                            <div className={`text-xs font-bold ${holding.gain_loss_pct >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                              {formatPercent(holding.gain_loss_pct || 0)}
                            </div>
                          </td>
                          <td className="px-4 py-4 text-right">
                            <span className={`rounded-full px-3 py-1 text-xs font-extrabold ${scoreTone(holding.score || 0)} bg-black/[0.04]`}>
                              {(holding.score || 0).toFixed(0)}
                            </span>
                          </td>
                          <td className="px-4 py-4 text-center">
                            <span
                              className={`rounded-full px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] ${
                                holding.recommendation?.includes("BUY")
                                  ? "bg-emerald-500/10 text-emerald-700"
                                  : holding.recommendation?.includes("SELL") || holding.recommendation?.includes("AVOID")
                                    ? "bg-red-500/10 text-red-700"
                                    : "bg-amber-500/10 text-amber-700"
                              }`}
                            >
                              {holding.recommendation}
                            </span>
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex justify-end gap-2">
                              <button
                                onClick={() => onAnalyzeStock(holding.ticker)}
                                className="rounded-xl border border-black/8 bg-white px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-slate-700"
                              >
                                Analyze
                              </button>
                              <button
                                onClick={() => onRemoveHolding(currentPortfolio.id, holding.ticker)}
                                className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-red-700"
                              >
                                Remove
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          ) : (
            <section className="surface-panel rounded-[2.4rem] p-10 text-center">
              <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-[2rem] bg-black/[0.04]">
                <Plus size={32} className="text-slate-400" />
              </div>
              <h3 className="mt-6 text-2xl text-slate-900">No holdings yet</h3>
              <p className="mx-auto mt-3 max-w-md text-sm leading-7 text-slate-500">
                Add your first position to unlock performance, income, risk and diversification views.
              </p>
              <div className="mt-6 flex flex-wrap justify-center gap-3">
                <button
                  onClick={() => window.open(`/api/portfolio/${selectedPortfolio}/export/csv`)}
                  className="rounded-[1.2rem] border border-black/8 bg-white px-5 py-3 text-xs font-extrabold uppercase tracking-[0.16em] text-slate-700"
                >
                  Export csv
                </button>
                <button
                  onClick={() => setShowAddHoldingModal(true)}
                  className="rounded-[1.2rem] bg-[var(--accent)] px-5 py-3 text-xs font-extrabold uppercase tracking-[0.16em] text-white transition-colors hover:bg-[var(--accent-strong)]"
                >
                  Add stock
                </button>
              </div>
            </section>
          )}
        </div>
      ) : (
        <section className="surface-panel rounded-[2.6rem] p-10 text-center">
          <div className="mx-auto flex h-24 w-24 items-center justify-center rounded-[2rem] bg-black/[0.04]">
            <LayoutGrid size={34} className="text-slate-400" />
          </div>
          <h3 className="mt-6 text-3xl text-slate-900">
            {portfolios.length === 0 ? "Start your first portfolio" : "Select a portfolio"}
          </h3>
          <p className="mx-auto mt-4 max-w-xl text-base leading-7 text-slate-500">
            {portfolios.length === 0
              ? "Create a portfolio to track positions, watch allocation and keep your decision flow in one place."
              : "Choose one of your portfolios above to open the full workstation."}
          </p>
          {portfolios.length === 0 && (
            <button
              onClick={() => setShowCreateModal(true)}
              className="mt-6 rounded-[1.3rem] bg-[var(--accent)] px-6 py-4 text-xs font-extrabold uppercase tracking-[0.18em] text-white transition-colors hover:bg-[var(--accent-strong)]"
            >
              Create first portfolio
            </button>
          )}
        </section>
      )}

      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="surface-panel w-full max-w-md rounded-[2rem] p-6">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              New Portfolio
            </div>
            <h3 className="mt-2 text-2xl text-slate-900">Create workspace bucket</h3>
            <input
              type="text"
              value={newPortfolioName}
              onChange={(e) => setNewPortfolioName(e.target.value)}
              placeholder="Portfolio name"
              className="mt-5 w-full rounded-[1.2rem] border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800"
              autoFocus
            />
            <div className="mt-5 flex justify-end gap-3">
              <button
                onClick={() => setShowCreateModal(false)}
                className="rounded-[1rem] border border-black/8 bg-white px-4 py-2.5 text-xs font-extrabold uppercase tracking-[0.16em] text-slate-700"
              >
                Cancel
              </button>
              <button
                onClick={handleCreatePortfolio}
                disabled={!newPortfolioName.trim()}
                className="rounded-[1rem] bg-[var(--accent)] px-4 py-2.5 text-xs font-extrabold uppercase tracking-[0.16em] text-white transition-colors hover:bg-[var(--accent-strong)] disabled:opacity-50"
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      <AddHoldingModal
        isOpen={showAddHoldingModal}
        onClose={() => setShowAddHoldingModal(false)}
        onAdd={onAddHolding}
        portfolios={portfolios}
        initialTicker={newHolding.ticker}
        initialPrice={parseFloat(newHolding.buyPrice) || undefined}
      />
    </div>
  );
}
