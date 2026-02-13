import React, { useState, useEffect } from "react";
import { Portfolio, Holding } from "../hooks/usePortfolios";
import { useCurrency } from "../context/CurrencyContext";

interface AddHoldingModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAdd: (portfolioId: string, holding: Holding) => void;
  portfolios: Portfolio[];
  initialTicker?: string;
  initialPrice?: number;
}

export default function AddHoldingModal({
  isOpen,
  onClose,
  onAdd,
  portfolios,
  initialTicker = "",
  initialPrice,
}: AddHoldingModalProps) {
  const { currency, exchangeRate, convert } = useCurrency();
  const [ticker, setTicker] = useState(initialTicker);
  const [shares, setShares] = useState("1");
  const [buyPrice, setBuyPrice] = useState("");
  const [selectedPortfolioId, setSelectedPortfolioId] = useState(
    portfolios[0]?.id || "",
  );

  useEffect(() => {
    if (initialTicker) setTicker(initialTicker);

    // Convert initialPrice (assumed USD) to active currency for display
    if (initialPrice) {
      const displayPrice = convert(initialPrice, "USD");
      setBuyPrice(displayPrice.toFixed(2));
    } else {
      setBuyPrice("");
    }

    if (portfolios.length > 0 && !selectedPortfolioId) {
      setSelectedPortfolioId(portfolios[0].id);
    }
  }, [initialTicker, initialPrice, portfolios, selectedPortfolioId, currency]); // Add currency to deps

  if (!isOpen) return null;

  const handleAdd = () => {
    if (!ticker || !shares || !selectedPortfolioId) return;

    let priceInUSD = buyPrice ? parseFloat(buyPrice) : undefined;

    // If user is in EUR mode, convert the input (EUR) back to USD
    if (priceInUSD !== undefined && currency === "EUR") {
      priceInUSD = priceInUSD / exchangeRate;
    }

    onAdd(selectedPortfolioId, {
      ticker: ticker.toUpperCase(),
      shares: parseFloat(shares),
      buyPrice: priceInUSD,
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-[#050507] rounded-2xl p-6 w-full max-w-md border border-white/10 shadow-2xl">
        <h3 className="text-xl font-bold text-white mb-6 flex items-center gap-2">
          <span className="w-8 h-8 bg-blue-500/20 rounded-lg flex items-center justify-center text-blue-400">
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 6v6m0 0v6m0-6h6m-6 0H6"
              />
            </svg>
          </span>
          Asset zum Portfolio hinzufügen
        </h3>

        <div className="space-y-4">
          <div>
            <label className="block text-gray-400 text-xs font-bold uppercase tracking-widest mb-2">
              Portfolio wählen
            </label>
            <select
              value={selectedPortfolioId}
              onChange={(e) => setSelectedPortfolioId(e.target.value)}
              className="w-full px-4 py-3 bg-black border border-white/10 rounded-xl text-white focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 appearance-none cursor-pointer"
            >
              {portfolios.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-gray-400 text-xs font-bold uppercase tracking-widest mb-2">
                Ticker
              </label>
              <input
                type="text"
                value={ticker}
                onChange={(e) => setTicker(e.target.value.toUpperCase())}
                placeholder="AAPL"
                className="w-full px-4 py-3 bg-black border border-white/10 rounded-xl text-white placeholder-gray-600 focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20"
              />
            </div>
            <div>
              <label className="block text-gray-400 text-xs font-bold uppercase tracking-widest mb-2">
                Anzahl
              </label>
              <input
                type="number"
                value={shares}
                onChange={(e) => setShares(e.target.value)}
                placeholder="10"
                className="w-full px-4 py-3 bg-black border border-white/10 rounded-xl text-white placeholder-gray-600 focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20"
              />
            </div>
          </div>

          <div>
            <label className="block text-gray-400 text-xs font-bold uppercase tracking-widest mb-2">
              Kaufpreis ({currency === "EUR" ? "€" : "$"})
            </label>
            <input
              type="number"
              value={buyPrice}
              onChange={(e) => setBuyPrice(e.target.value)}
              placeholder="0.00"
              className="w-full px-4 py-3 bg-black border border-white/10 rounded-xl text-white placeholder-gray-600 focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20"
            />
          </div>
        </div>

        <div className="flex gap-3 justify-end mt-8">
          <button
            onClick={onClose}
            className="px-6 py-2.5 bg-[#0a0a0c] hover:bg-white/5 text-gray-400 hover:text-white rounded-xl transition-all border border-white/5 font-bold text-sm"
          >
            Abbrechen
          </button>
          <button
            onClick={handleAdd}
            disabled={!ticker || !shares || !selectedPortfolioId}
            className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-bold text-sm shadow-lg shadow-blue-600/20 transition-all disabled:opacity-50"
          >
            Hinzufügen
          </button>
        </div>
      </div>
    </div>
  );
}
