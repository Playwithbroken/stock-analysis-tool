import { useState, useEffect } from "react";
import { usePortfolios, Portfolio, Holding } from "../hooks/usePortfolios";
import PortfolioPerformance from "./PortfolioPerformance";
import PortfolioHeatmap from "./PortfolioHeatmap";
import DividendDashboard from "./DividendDashboard";
import RiskCorrelationMatrix from "./RiskCorrelationMatrix";
import AssetSuggestions from "./AssetSuggestions";
import AddHoldingModal from "./AddHoldingModal";
import {
  Plus,
  Trash2,
  Search,
  TrendingUp,
  DollarSign,
  LayoutGrid,
  ShieldAlert,
} from "lucide-react";

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

import { useCurrency } from "../context/CurrencyContext";

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
  const { formatPrice, convert } = useCurrency();
  const [selectedPortfolio, setSelectedPortfolio] = useState<string | null>(
    null,
  );
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

  // Analyze portfolio when selected or holdings change
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
      const data = await res.json();
      setPortfolioVerdict(data.verdict);
    } catch (e) {
      console.error("Failed to fetch verdict", e);
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
    } catch (err) {
      console.error("Failed to analyze portfolio:", err);
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

  const handleAddHolding = () => {
    if (selectedPortfolio && newHolding.ticker && newHolding.shares) {
      onAddHolding(selectedPortfolio, {
        ticker: newHolding.ticker.toUpperCase(),
        shares: parseFloat(newHolding.shares),
        buyPrice: newHolding.buyPrice
          ? parseFloat(newHolding.buyPrice)
          : undefined,
      });
      setNewHolding({ ticker: "", shares: "", buyPrice: "" });
      setShowAddHoldingModal(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Portfolio Selector */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          {portfolios.map((portfolio) => (
            <button
              key={portfolio.id}
              onClick={() => setSelectedPortfolio(portfolio.id)}
              className={`px-4 py-2 rounded-lg transition-all ${
                selectedPortfolio === portfolio.id
                  ? "bg-purple-600 text-white shadow-lg shadow-purple-500/20"
                  : "bg-[#0a0a0c] text-gray-400 hover:bg-[#121215]"
              }`}
            >
              {portfolio.name}
              <span className="ml-2 text-xs opacity-70">
                ({portfolio.holdings.length})
              </span>
            </button>
          ))}
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="px-4 py-2 bg-[#0a0a0c] hover:bg-[#121215] text-gray-400 rounded-lg transition-all flex items-center gap-2 border border-white/5"
        >
          <svg
            className="w-4 h-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 4v16m8-8H4"
            />
          </svg>
          New Portfolio
        </button>
      </div>

      {/* Portfolio Content */}
      {currentPortfolio ? (
        <div className="space-y-6">
          {/* Portfolio Header */}
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold text-white">
                {currentPortfolio.name}
              </h2>
              <p className="text-gray-400 text-sm">
                {currentPortfolio.holdings.length} holdings
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setShowAddHoldingModal(true)}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-all flex items-center gap-2"
              >
                <svg
                  className="w-4 h-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 4v16m8-8H4"
                  />
                </svg>
                Add Stock
              </button>
              <button
                onClick={() =>
                  currentPortfolio && analyzePortfolio(currentPortfolio)
                }
                disabled={loading || currentPortfolio.holdings.length === 0}
                className="px-4 py-2 bg-[#0a0a0c] hover:bg-[#121215] text-white rounded-lg transition-all disabled:opacity-50 border border-white/5"
              >
                {loading ? "Analyzing..." : "Refresh"}
              </button>
              <button
                onClick={() => {
                  if (confirm("Delete this portfolio?")) {
                    onDeletePortfolio(currentPortfolio.id);
                    setSelectedPortfolio(null);
                  }
                }}
                className="px-4 py-2 bg-red-950/20 hover:bg-red-900/30 text-red-500 rounded-lg transition-all border border-red-900/20"
              >
                Delete
              </button>
            </div>
          </div>

          {/* Portfolio Summary */}
          {analysis && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-[#050507] rounded-xl p-4 border border-white/5 shadow-inner">
                <div className="text-gray-400 text-sm mb-1">Total Value</div>
                <div className="text-2xl font-bold text-white">
                  {formatPrice(analysis.summary.total_value)}
                </div>
              </div>
              <div className="bg-[#050507] rounded-xl p-4 border border-white/5 shadow-inner">
                <div className="text-gray-400 text-sm mb-1">
                  Total Gain/Loss
                </div>
                <div
                  className={`text-2xl font-bold ${analysis.summary.gain_loss >= 0 ? "text-green-400" : "text-red-400"}`}
                >
                  {formatPrice(analysis.summary.gain_loss)}
                </div>
                <div
                  className={`text-sm ${analysis.summary.gain_loss_pct >= 0 ? "text-green-400" : "text-red-400"}`}
                >
                  {formatPercent(analysis.summary.gain_loss_pct)}
                </div>
              </div>
              <div className="bg-[#050507] rounded-xl p-4 border border-white/5 shadow-inner">
                <div className="text-gray-400 text-sm mb-1">
                  Portfolio Score
                </div>
                <div
                  className={`text-2xl font-bold ${
                    analysis.summary.avg_score > 10
                      ? "text-green-400"
                      : analysis.summary.avg_score < -10
                        ? "text-red-400"
                        : "text-yellow-400"
                  }`}
                >
                  {analysis.summary.avg_score.toFixed(1)}
                </div>
              </div>
              <div className="bg-[#050507] rounded-xl p-4 border border-white/5 shadow-inner">
                <div className="text-gray-400 text-sm mb-1">Holdings</div>
                <div className="text-2xl font-bold text-white">
                  {analysis.summary.num_holdings}
                </div>
              </div>
            </div>
          )}

          {/* AI Portfolio Verdict */}
          {portfolioVerdict && (
            <div className="bg-linear-to-r from-indigo-900/40 to-black border border-indigo-500/20 rounded-2xl p-6 mb-8 flex items-center gap-4">
              <div className="w-12 h-12 bg-indigo-500/10 rounded-full flex items-center justify-center border border-indigo-500/20 shrink-0">
                <LayoutGrid className="text-indigo-400" size={24} />
              </div>
              <p className="text-gray-200 text-lg italic">
                “{portfolioVerdict}”
              </p>
            </div>
          )}

          {/* New Workstation Components */}
          {analysis && analysis.holdings.length > 0 && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
              <PortfolioPerformance portfolioId={selectedPortfolio!} />
              <PortfolioHeatmap holdings={analysis.holdings} />
            </div>
          )}

          {/* Risk & Dividend Workstation */}
          {analysis && analysis.holdings.length > 0 && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
              <DividendDashboard portfolioId={selectedPortfolio!} />
              <RiskCorrelationMatrix portfolioId={selectedPortfolio!} />
            </div>
          )}

          {/* Asset Suggestions */}
          {selectedPortfolio && (
            <div className="mb-8">
              <AssetSuggestions
                portfolioId={selectedPortfolio}
                onAdd={(ticker: string) => {
                  setNewHolding({ ticker, shares: "1", buyPrice: "" });
                  setShowAddHoldingModal(true);
                }}
              />
            </div>
          )}

          {/* Sector Allocation */}
          {analysis &&
            Object.keys(analysis.summary.sector_allocation).length > 0 && (
              <div className="bg-[#050507] rounded-xl p-5 border border-white/5">
                <h3 className="text-lg font-semibold text-white mb-4">
                  Sector Allocation
                </h3>
                <div className="space-y-2">
                  {Object.entries(analysis.summary.sector_allocation)
                    .sort((a, b) => b[1] - a[1])
                    .map(([sector, pct]) => (
                      <div key={sector} className="flex items-center gap-3">
                        <div className="w-32 text-gray-300 text-sm truncate">
                          {sector}
                        </div>
                        <div className="flex-1 h-2 bg-black rounded-full overflow-hidden">
                          <div
                            className="h-full bg-linear-to-r from-purple-500 to-indigo-500 rounded-full"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <div className="w-16 text-right text-gray-400 text-sm">
                          {pct.toFixed(1)}%
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            )}

          {/* Holdings Table */}
          {analysis && analysis.holdings.length > 0 && (
            <div className="bg-[#050507] rounded-xl border border-white/5 overflow-hidden shadow-inner">
              <table className="w-full">
                <thead className="bg-[#0a0a0c]">
                  <tr>
                    <th className="text-left p-4 text-gray-400 font-medium">
                      Stock
                    </th>
                    <th className="text-right p-4 text-gray-400 font-medium">
                      Shares
                    </th>
                    <th className="text-right p-4 text-gray-400 font-medium">
                      Price
                    </th>
                    <th className="text-right p-4 text-gray-400 font-medium">
                      Value
                    </th>
                    <th className="text-right p-4 text-gray-400 font-medium">
                      Gain/Loss
                    </th>
                    <th className="text-right p-4 text-gray-400 font-medium">
                      Score
                    </th>
                    <th className="text-center p-4 text-gray-400 font-medium">
                      Action
                    </th>
                    <th className="p-4"></th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.holdings.map((holding) => (
                    <tr
                      key={holding.ticker}
                      className="border-t border-white/5 hover:bg-white/2"
                    >
                      <td className="p-4">
                        <div className="font-medium text-white">
                          {holding.ticker}
                        </div>
                        <div className="text-gray-500 text-sm truncate max-w-[150px]">
                          {holding.name}
                        </div>
                      </td>
                      <td className="p-4 text-right text-gray-300">
                        {holding.shares}
                      </td>
                      <td className="p-4 text-right text-gray-300">
                        {formatPrice(holding.current_price || 0)}
                      </td>
                      <td className="p-4 text-right text-white font-medium">
                        {formatPrice(holding.position_value || 0)}
                      </td>
                      <td className="p-4 text-right">
                        <div
                          className={
                            holding.gain_loss >= 0
                              ? "text-green-400"
                              : "text-red-400"
                          }
                        >
                          {formatPrice(holding.gain_loss || 0)}
                        </div>
                        <div
                          className={`text-sm ${holding.gain_loss_pct >= 0 ? "text-green-400" : "text-red-400"}`}
                        >
                          {formatPercent(holding.gain_loss_pct || 0)}
                        </div>
                      </td>
                      <td className="p-4 text-right">
                        <span
                          className={`px-2 py-1 rounded text-sm ${
                            (holding.score || 0) > 10
                              ? "bg-green-500/20 text-green-400"
                              : (holding.score || 0) < -10
                                ? "bg-red-500/20 text-red-400"
                                : "bg-yellow-500/20 text-yellow-400"
                          }`}
                        >
                          {(holding.score || 0).toFixed(0)}
                        </span>
                      </td>
                      <td className="p-4 text-center">
                        <span
                          className={`px-2 py-1 rounded text-xs font-medium ${
                            holding.recommendation?.includes("BUY")
                              ? "bg-green-500/20 text-green-400"
                              : holding.recommendation?.includes("SELL") ||
                                  holding.recommendation?.includes("AVOID")
                                ? "bg-red-500/20 text-red-400"
                                : "bg-yellow-500/20 text-yellow-400"
                          }`}
                        >
                          {holding.recommendation}
                        </span>
                      </td>
                      <td className="p-4">
                        <div className="flex gap-1">
                          <button
                            onClick={() => onAnalyzeStock(holding.ticker)}
                            className="p-2 hover:bg-[#121215] rounded-lg transition-colors border border-transparent hover:border-white/5"
                            title="View Analysis"
                          >
                            <svg
                              className="w-4 h-4 text-gray-400"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                              />
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                              />
                            </svg>
                          </button>
                          <button
                            onClick={() =>
                              onRemoveHolding(
                                currentPortfolio.id,
                                holding.ticker,
                              )
                            }
                            className="p-2 hover:bg-red-500/20 rounded-lg transition-colors"
                            title="Remove"
                          >
                            <svg
                              className="w-4 h-4 text-red-400"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                              />
                            </svg>
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Empty State */}
          {currentPortfolio.holdings.length === 0 && (
            <div className="text-center py-12 bg-[#050507] rounded-xl border border-white/5">
              <div className="w-16 h-16 mx-auto mb-4 bg-black rounded-full flex items-center justify-center border border-white/5">
                <svg
                  className="w-8 h-8 text-gray-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M12 6v6m0 0v6m0-6h6m-6 0H6"
                  />
                </svg>
              </div>
              <h3 className="text-lg font-medium text-gray-400 mb-2">
                No holdings yet
              </h3>
              <p className="text-gray-500 mb-4">
                Add stocks to your portfolio to start tracking
              </p>
              <div className="flex items-center gap-2 justify-center">
                <button
                  onClick={() =>
                    window.open(
                      `/api/portfolio/${selectedPortfolio}/export/csv`,
                    )
                  }
                  className="px-4 py-2 bg-white/5 hover:bg-white/10 text-gray-300 rounded-lg text-sm font-medium transition-all flex items-center gap-2 border border-white/5"
                >
                  <TrendingUp size={16} /> Export CSV
                </button>
                <button
                  onClick={() => setShowAddHoldingModal(true)}
                  className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm font-bold transition-all flex items-center gap-2 shadow-lg shadow-purple-500/20"
                >
                  <Plus size={18} /> Add Stock
                </button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="text-center py-20 bg-[#0a0a0c] rounded-3xl border border-white/5 relative overflow-hidden group">
          <div className="absolute inset-0 bg-linear-to-b from-purple-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
          <div className="relative z-10 max-w-md mx-auto">
            <div className="w-20 h-20 mx-auto mb-6 bg-linear-to-br from-gray-800 to-black rounded-3xl flex items-center justify-center shadow-2xl border border-white/10 group-hover:scale-110 transition-transform duration-500">
              <svg
                className="w-10 h-10 text-gray-500 group-hover:text-purple-400 transition-colors"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
                />
              </svg>
            </div>
            <h3 className="text-2xl font-black text-white mb-3">
              {portfolios.length === 0
                ? "Start Your Investment Journey"
                : "Select a Portfolio"}
            </h3>
            <p className="text-gray-500 mb-8 leading-relaxed">
              {portfolios.length === 0
                ? "Create your first portfolio to track your assets, analyze performance, and get AI-powered insights."
                : "Choose a portfolio from above to view detailed performance metrics and holdins."}
            </p>
            {portfolios.length === 0 && (
              <button
                onClick={() => setShowCreateModal(true)}
                className="px-8 py-4 bg-purple-600 hover:bg-purple-500 text-white rounded-2xl transition-all shadow-xl shadow-purple-600/30 font-bold text-sm uppercase tracking-widest hover:-translate-y-1"
              >
                Create First Portfolio
              </button>
            )}
          </div>
        </div>
      )}

      {/* Create Portfolio Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-[#050507] rounded-xl p-6 w-full max-w-md border border-white/10 shadow-2xl">
            <h3 className="text-xl font-bold text-white mb-4">
              Create Portfolio
            </h3>
            <input
              type="text"
              value={newPortfolioName}
              onChange={(e) => setNewPortfolioName(e.target.value)}
              placeholder="Portfolio name"
              className="w-full px-4 py-3 bg-black border border-white/10 rounded-lg text-white placeholder-gray-600 focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 mb-4"
              autoFocus
            />
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setShowCreateModal(false)}
                className="px-4 py-2 bg-[#0a0a0c] hover:bg-[#121215] text-white rounded-lg transition-all border border-white/5"
              >
                Cancel
              </button>
              <button
                onClick={handleCreatePortfolio}
                disabled={!newPortfolioName.trim()}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-all disabled:opacity-50"
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add Holding Modal */}
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
