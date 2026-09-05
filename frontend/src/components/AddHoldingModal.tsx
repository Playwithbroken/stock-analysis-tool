import React, { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { Portfolio, Holding } from "../hooks/usePortfolios";
import { useCurrency } from "../context/CurrencyContext";
import useAccessibleDialog from "../hooks/useAccessibleDialog";

interface AddHoldingModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAdd: (portfolioId: string, holding: Holding) => Promise<void> | void;
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
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useAccessibleDialog<HTMLDivElement>(isOpen, onClose, "input, select, button");

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
    if (isOpen) {
      setError(null);
      setSaving(false);
    }
  }, [initialTicker, initialPrice, portfolios, selectedPortfolioId, currency, convert, isOpen]);

  if (!isOpen) return null;

  // No portfolios exist yet — show helpful message
  if (portfolios.length === 0) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-md dark:bg-black/65" role="presentation">
        <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="no-portfolio-title" tabIndex={-1} className="surface-panel w-full max-w-sm rounded-2xl border border-black/8 p-8 text-center dark:border-white/10 dark:bg-[#1c1c1e]">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-black/[0.04] text-[#1d1d1f] dark:bg-white/10 dark:text-white">
            <Plus size={24} />
          </div>
          <h3 id="no-portfolio-title" className="text-xl font-bold tracking-tight text-slate-900 dark:text-white">Noch kein Portfolio</h3>
          <p className="mt-3 text-sm leading-6 text-slate-500 dark:text-slate-400">
            Erstelle zuerst ein Portfolio im <strong className="font-semibold text-slate-700 dark:text-slate-200">Portfolio-Tab</strong>, dann kannst du
            Aktien direkt aus der Analyse hinzufügen.
          </p>
          <button
            onClick={onClose}
            className="mt-6 w-full rounded-xl bg-[#1d1d1f] py-3 text-xs font-bold uppercase tracking-[0.14em] text-white hover:bg-black dark:bg-white dark:text-black dark:hover:bg-white/90"
          >
            Verstanden
          </button>
        </div>
      </div>
    );
  }

  const handleAdd = async () => {
    if (saving) return;
    const cleanTicker = ticker.trim().toUpperCase();
    const parsedShares = Number(shares);
    if (!cleanTicker || !Number.isFinite(parsedShares) || parsedShares <= 0 || !selectedPortfolioId) {
      setError("Bitte Ticker und eine gueltige Anzahl eintragen.");
      return;
    }

    let priceInUSD = buyPrice ? parseFloat(buyPrice) : undefined;
    if (priceInUSD !== undefined && (!Number.isFinite(priceInUSD) || priceInUSD <= 0)) {
      setError("Der Kaufpreis muss groesser als 0 sein.");
      return;
    }
    if (priceInUSD !== undefined && currency === "EUR") {
      priceInUSD = priceInUSD / exchangeRate;
    }

    setSaving(true);
    setError(null);
    try {
      await onAdd(selectedPortfolioId, {
        ticker: cleanTicker,
        shares: parsedShares,
        buyPrice: priceInUSD,
        purchaseDate: purchaseDate || undefined,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Position konnte nicht gespeichert werden.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-md dark:bg-black/65" role="presentation">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="add-holding-title" aria-describedby={error ? "add-holding-error" : undefined} tabIndex={-1} className="surface-panel w-full max-w-md rounded-2xl border border-black/8 p-6 sm:p-7 dark:border-white/10 dark:bg-[#1c1c1e]">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-black/[0.04] text-[#1d1d1f] dark:bg-white/10 dark:text-white">
            <Plus size={18} />
          </div>
          <div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
              Portfolio
            </div>
            <h3 id="add-holding-title" className="mt-0.5 text-xl font-bold tracking-tight text-slate-900 dark:text-white">
              Asset hinzufügen
            </h3>
          </div>
        </div>

        <div className="space-y-4">
          <Field label="Portfolio">
            <select
              value={selectedPortfolioId}
              onChange={(e) => setSelectedPortfolioId(e.target.value)}
              disabled={saving}
              className="w-full appearance-none rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800 outline-none transition-all focus:ring-2 focus:ring-black/10 dark:border-white/10 dark:bg-white/5 dark:text-white dark:focus:ring-white/20"
            >
              {portfolios.map((p) => (
                <option key={p.id} value={p.id} className="bg-white text-slate-900 dark:bg-[#1c1c1e] dark:text-white">
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
                onChange={(e) => {
                  setTicker(e.target.value.toUpperCase());
                  setError(null);
                }}
                placeholder="AAPL"
                disabled={saving}
                className="w-full rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800 outline-none transition-all placeholder:text-slate-400 focus:ring-2 focus:ring-black/10 dark:border-white/10 dark:bg-white/5 dark:text-white dark:placeholder:text-slate-500 dark:focus:ring-white/20"
              />
            </Field>
            <Field label="Anzahl">
              <input
                type="number"
                value={shares}
                onChange={(e) => {
                  setShares(e.target.value);
                  setError(null);
                }}
                placeholder="10"
                disabled={saving}
                className="w-full rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800 outline-none transition-all placeholder:text-slate-400 focus:ring-2 focus:ring-black/10 dark:border-white/10 dark:bg-white/5 dark:text-white dark:placeholder:text-slate-500 dark:focus:ring-white/20"
              />
            </Field>
          </div>

          <Field label={`Kaufpreis (${currency === "EUR" ? "EUR" : "USD"})`}>
            <input
              type="number"
              value={buyPrice}
              onChange={(e) => {
                setBuyPrice(e.target.value);
                setError(null);
              }}
              placeholder="0.00"
              disabled={saving}
              className="w-full rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800 outline-none transition-all placeholder:text-slate-400 focus:ring-2 focus:ring-black/10 dark:border-white/10 dark:bg-white/5 dark:text-white dark:placeholder:text-slate-500 dark:focus:ring-white/20"
            />
          </Field>

          <Field label="Kaufdatum">
            <input
              type="date"
              value={purchaseDate}
              onChange={(e) => setPurchaseDate(e.target.value)}
              disabled={saving}
              className="w-full rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800 outline-none transition-all focus:ring-2 focus:ring-black/10 dark:border-white/10 dark:bg-white/5 dark:text-white dark:focus:ring-white/20"
            />
          </Field>
        </div>

        {error ? (
          <div id="add-holding-error" role="alert" className="mt-5 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-xs font-bold text-red-600 dark:text-red-400">
            {error}
          </div>
        ) : null}

        <div className="mt-8 flex justify-end gap-3">
          <button
            onClick={onClose}
            disabled={saving}
            className="rounded-xl border border-black/8 bg-white px-5 py-2.5 text-xs font-bold uppercase tracking-[0.14em] text-slate-700 transition-colors hover:bg-black/[0.03] dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:bg-white/10"
          >
            Abbrechen
          </button>
          <button
            onClick={handleAdd}
            disabled={saving || !ticker || !shares || !selectedPortfolioId}
            className="rounded-xl bg-[#1d1d1f] px-5 py-2.5 text-xs font-bold uppercase tracking-[0.14em] text-white transition-colors hover:bg-black dark:bg-white dark:text-black dark:hover:bg-white/90 disabled:opacity-50"
          >
            {saving ? "Speichert..." : "Hinzufügen"}
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
      <div className="mb-2 text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
        {label}
      </div>
      {children}
    </label>
  );
}
