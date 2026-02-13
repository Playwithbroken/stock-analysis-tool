import { useState, useEffect } from "react";
import SearchBar from "./components/SearchBar";
import AnalysisResult from "./components/AnalysisResult";
import LoadingState from "./components/LoadingState";
import PortfolioView from "./components/PortfolioView";
import DiscoveryPanel from "./components/DiscoveryPanel";
import BrokerChat from "./components/BrokerChat";
import { usePortfolios } from "./hooks/usePortfolios";
import { CurrencyProvider, useCurrency } from "./context/CurrencyContext";

interface AnalysisData {
  ticker: string;
  company_name: string;
  [key: string]: any;
}

type Tab = "analyze" | "discovery" | "portfolio";

function AppContent() {
  const [activeTab, setActiveTab] = useState<Tab>(() => {
    return (localStorage.getItem("activeTab") as Tab) || "analyze";
  });
  const [analysis, setAnalysis] = useState<AnalysisData | null>(() => {
    const saved = localStorage.getItem("lastAnalysis");
    return saved ? JSON.parse(saved) : null;
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isChatOpen, setIsChatOpen] = useState(false);

  useEffect(() => {
    localStorage.setItem("activeTab", activeTab);
  }, [activeTab]);

  useEffect(() => {
    if (analysis) {
      localStorage.setItem("lastAnalysis", JSON.stringify(analysis));
    }
  }, [analysis]);

  const {
    portfolios,
    createPortfolio,
    deletePortfolio,
    addHolding,
    removeHolding,
  } = usePortfolios();

  const { currency, setCurrency } = useCurrency();

  const handleSearch = async (ticker: string) => {
    setLoading(true);
    setError(null);
    setAnalysis(null);
    setActiveTab("analyze");

    try {
      const response = await fetch(`/api/analyze/${ticker}`);

      if (!response.ok) {
        let errorMsg = "Failed to fetch analysis";
        try {
          const errData = await response.json();
          errorMsg = errData.detail || errorMsg;
        } catch (e) {
          // Check if response is text (e.g. HTML error page)
          const text = await response.text();
          console.error("Non-JSON error response:", text);
          errorMsg = `Server Error: ${response.status} ${response.statusText}`;
        }
        throw new Error(errorMsg);
      }

      const data = await response.json();
      setAnalysis(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-black text-gray-200">
      {/* Header */}
      <header className="border-b border-white/5 bg-black/80 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-linear-to-br from-indigo-600 to-purple-600 rounded-xl flex items-center justify-center shadow-lg shadow-purple-500/20">
                <svg
                  className="w-6 h-6 text-white"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"
                  />
                </svg>
              </div>
              <div className="hidden sm:block">
                <h1 className="text-xl font-bold text-white leading-tight">
                  Broker Freund
                </h1>
                <p className="text-[10px] text-purple-400 uppercase tracking-widest font-bold">
                  Top Investment-Berater
                </p>
              </div>
            </div>

            {/* Middle: Tab Navigation */}
            <div className="flex items-center gap-1 bg-[#050507] backdrop-blur rounded-xl p-1.5 border border-white/5 shadow-inner">
              {[
                {
                  id: "analyze",
                  icon: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z",
                  label: "Analyze",
                },
                {
                  id: "discovery",
                  icon: "M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z",
                  label: "Discovery",
                },
                {
                  id: "portfolio",
                  icon: "M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10",
                  label: "Portfolio",
                },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as Tab)}
                  className={`px-5 py-2.5 rounded-xl text-sm font-bold transition-all duration-300 flex items-center gap-2.5 ${
                    activeTab === tab.id
                      ? "bg-purple-600 shadow-[0_0_20px_rgba(147,51,234,0.3)] text-white scale-105"
                      : "text-gray-400 hover:text-white hover:bg-white/5"
                  }`}
                >
                  <svg
                    className={`w-4 h-4 ${activeTab === tab.id ? "text-white" : "text-gray-500 group-hover:text-white"}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d={tab.icon}
                    />
                  </svg>
                  <span className="hidden md:inline">{tab.label}</span>
                </button>
              ))}
            </div>

            {/* Right: Currency Toggle */}
            <div className="flex bg-[#050507] rounded-xl p-1 border border-white/5 shadow-inner">
              <button
                onClick={() => setCurrency("USD")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-black transition-all ${
                  currency === "USD"
                    ? "bg-purple-600 text-white shadow-lg shadow-purple-500/20"
                    : "text-gray-500 hover:text-gray-300"
                }`}
              >
                <span>$</span>
                <span className="hidden lg:inline">USD</span>
              </button>
              <button
                onClick={() => setCurrency("EUR")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-black transition-all ${
                  currency === "EUR"
                    ? "bg-purple-600 text-white shadow-lg shadow-purple-500/20"
                    : "text-gray-500 hover:text-gray-300"
                }`}
              >
                <span>€</span>
                <span className="hidden lg:inline">EUR</span>
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main
        className={`max-w-7xl mx-auto px-4 py-8 pt-24 transition-all duration-300 ease-in-out ${isChatOpen ? "mr-[480px]" : ""}`}
      >
        {activeTab === "analyze" ? (
          <>
            {/* Search Section */}
            <div className="mb-12 max-w-2xl mx-auto">
              <h2 className="text-4xl font-bold text-center mb-8 drop-shadow-sm">
                Analyze any Stock
              </h2>
              <SearchBar onSearch={handleSearch} loading={loading} />
            </div>
            {/* Error State */}
            {error && (
              <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 mb-8 glass-card">
                <div className="flex items-center gap-3">
                  <svg
                    className="w-5 h-5 text-red-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                    />
                  </svg>
                  <span className="text-red-400">{error}</span>
                </div>
              </div>
            )}

            {/* Loading State */}
            {loading && <LoadingState />}

            {/* Results */}
            {analysis && !loading && (
              <AnalysisResult
                data={analysis}
                portfolios={portfolios}
                onAddHolding={addHolding}
                onOpenChat={() => setIsChatOpen(true)}
                onSelectTicker={handleSearch}
              />
            )}

            {!analysis && !loading && !error && (
              <div className="text-center py-20">
                <div className="w-24 h-24 mx-auto mb-6 bg-gray-900/50 glass-card rounded-full flex items-center justify-center">
                  <svg
                    className="w-12 h-12 text-gray-700"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1.5}
                      d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                    />
                  </svg>
                </div>
                <h2 className="text-3xl font-bold text-white mb-2 font-serif">
                  Search for a Stock
                </h2>
                <p className="text-gray-500 max-w-sm mx-auto mb-10">
                  Enter a ticker symbol like AAPL, NVDA, or MSTR to get a
                  professional data-driven analysis.
                </p>

                <div className="flex flex-wrap justify-center gap-3">
                  {["NVDA", "MSTR", "PLTR", "TSLA", "ARM", "SMCI"].map(
                    (ticker) => (
                      <button
                        key={ticker}
                        onClick={() => handleSearch(ticker)}
                        className="px-6 py-3 bg-[#0a0a0c] hover:bg-purple-600/10 text-gray-400 hover:text-purple-300 rounded-xl transition-all text-sm border border-white/5 hover:border-purple-500/30 hover:scale-105"
                      >
                        {ticker}
                      </button>
                    ),
                  )}
                </div>

                <div className="mt-16 border-t border-white/5 pt-8 max-w-lg mx-auto">
                  <h3 className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-4">
                    Trending Now
                  </h3>
                  <div className="flex justify-center gap-6 opacity-60 hover:opacity-100 transition-opacity">
                    <div className="text-center">
                      <span className="block text-2xl mb-1">🔥</span>
                      <span className="text-[10px] text-gray-400 font-bold">
                        Hot Tech
                      </span>
                    </div>
                    <div className="text-center">
                      <span className="block text-2xl mb-1">🚀</span>
                      <span className="text-[10px] text-gray-400 font-bold">
                        Moonshots
                      </span>
                    </div>
                    <div className="text-center">
                      <span className="block text-2xl mb-1">💎</span>
                      <span className="text-[10px] text-gray-400 font-bold">
                        Value
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </>
        ) : activeTab === "discovery" ? (
          <DiscoveryPanel onAnalyze={handleSearch} />
        ) : (
          <PortfolioView
            portfolios={portfolios}
            onCreatePortfolio={createPortfolio}
            onDeletePortfolio={deletePortfolio}
            onAddHolding={addHolding}
            onRemoveHolding={removeHolding}
            onAnalyzeStock={(ticker) => {
              setActiveTab("analyze");
              handleSearch(ticker);
            }}
          />
        )}
      </main>

      <footer className="border-t border-white/5 mt-auto bg-black">
        <div className="max-w-7xl mx-auto px-4 py-6">
          <p className="text-center text-gray-400 text-sm">
            Data provided for informational purposes only. Not financial advice.
          </p>
        </div>
      </footer>
      <BrokerChat
        currentTicker={analysis?.ticker}
        isOpen={isChatOpen}
        setIsOpen={setIsChatOpen}
      />
    </div>
  );
}

export default function App() {
  return (
    <CurrencyProvider>
      <AppContent />
    </CurrencyProvider>
  );
}
