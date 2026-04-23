import React, { useEffect, useState } from "react";
import { Plus } from "lucide-react";
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
  const [purchaseDate, setPurchaseDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [selectedPortfolioId, setSelectedPortfolioId] = useState(
    portfolios[0]?.id || "",
  );

  useEffect(() => {
    if (initialTicker) setTicker(initialTicker);

    if (initialPrice) {
      const displayPrice = convert(initialPrice, "USD");
      setBuyPrice(displayPrice.toFixed(2));
    } else {
      setBuyPrice("");
    }
    setPurchaseDate(new Date().toISOString().slice(0, 10));

    if (portfolios.length > 0 && !selectedPortfolioId) {
      setSelectedPortfolioId(portfolios[0].id);
    }
  }, [initialTicker, initialPrice, portfolios, selectedPortfolioId, currency, convert]);

  if (!isOpen) return null;

  // No portfolios exist yet — show helpful message
  if (portfolios.length === 0) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(16,17,20,0.42)] p-4 backdrop-blur-sm">
        <div className="surface-panel w-full max-w-sm rounded-[2rem] p-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-[1.2rem] bg-[var(--accent-soft)] text-[var(--accent)]">
            <Plus size={24} />
          </div>
          <h3 className="text-xl font-black text-[var(--text-primary)]">Noch kein Portfolio</h3>
          <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
            Erstelle zuerst ein Portfolio im <strong>Portfolio-Tab</strong>, dann kannst du
            Aktien direkt aus der Analyse hinzufügen.
          </p>
          <button
            onClick={onClose}
            className="mt-6 w-full rounded-[1.2rem] bg-[var(--accent)] py-3 text-sm font-extrabold uppercase tracking-[0.16em] text-white hover:bg-[var(--accent-strong)]"
          >
            Verstanden
          </button>
        </div>
      </div>
    );
  }

  const handleAdd = () => {
    if (!ticker || !shares || !selectedPortfolioId) return;

    let priceInUSD = buyPrice ? parseFloat(buyPrice) : undefined;
    if (priceInUSD !== undefined && currency === "EUR") {
      priceInUSD = priceInUSD / exchangeRate;
    }

    onAdd(selectedPortfolioId, {
      ticker: ticker.toUpperCase(),
      shares: parseFloat(shares),
      buyPrice: priceInUSD,
      purchaseDate: purchaseDate || undefined,
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(16,17,20,0.42)] p-4 backdrop-blur-sm">
      <div className="surface-panel w-full max-w-md rounded-[2rem] p-6 sm:p-7">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-[1rem] bg-[var(--accent-soft)] text-[var(--accent)]">
            <Plus size={18} />
          </div>
          <div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
              Portfolio
            </div>
            <h3 className="mt-1 text-2xl font-black text-slate-900">
              Asset hinzufuegen
            </h3>
          </div>
        </div>

        <div className="space-y-4">
          <Field label="Portfolio">
            <select
              value={selectedPortfolioId}
              onChange={(e) => setSelectedPortfolioId(e.target.value)}
              className="w-full appearance-none rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800 outline-none transition-all focus:ring-2 focus:ring-[var(--accent)]/20"
            >
              {portfolios.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </Field>

          <div className="grid grid-cols-2 gap-4">
            <Field label="Ticker">
              <input
                type="text"
                value={ticker}
                onChange={(e) => setTicker(e.target.value.toUpperCase())}
                placeholder="AAPL"
                className="w-full rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800 outline-none transition-all placeholder:text-slate-400 focus:ring-2 focus:ring-[var(--accent)]/20"
              />
            </Field>
            <Field label="Anzahl">
              <input
                type="number"
                value={shares}
                onChange={(e) => setShares(e.target.value)}
                placeholder="10"
                className="w-full rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800 outline-none transition-all placeholder:text-slate-400 focus:ring-2 focus:ring-[var(--accent)]/20"
              />
            </Field>
          </div>

          <Field label={`Kaufpreis (${currency === "EUR" ? "EUR" : "USD"})`}>
            <input
              type="number"
              value={buyPrice}
              onChange={(e) => setBuyPrice(e.target.value)}
              placeholder="0.00"
              className="w-full rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800 outline-none transition-all placeholder:text-slate-400 focus:ring-2 focus:ring-[var(--accent)]/20"
            />
          </Field>

          <Field label="Kaufdatum">
            <input
              type="date"
              value={purchaseDate}
              onChange={(e) => setPurchaseDate(e.target.value)}
              className="w-full rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800 outline-none transition-all focus:ring-2 focus:ring-[var(--accent)]/20"
            />
          </Field>
        </div>

        <div className="mt-8 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="rounded-xl border border-black/8 bg-white px-5 py-2.5 text-sm font-bold text-slate-700 transition-colors hover:bg-black/[0.03]"
          >
            Abbrechen
          </button>
          <button
            onClick={handleAdd}
            disabled={!ticker || !shares || !selectedPortfolioId}
            className="rounded-xl bg-[var(--accent)] px-5 py-2.5 text-sm font-bold text-white transition-colors hover:bg-[var(--accent-strong)] disabled:opacity-50"
          >
            Hinzufuegen
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <div className="mb-2 text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
        {label}
      </div>
      {children}
    </label>
  );
}
