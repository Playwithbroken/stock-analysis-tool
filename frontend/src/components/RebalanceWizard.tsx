import React, { useState, useEffect, useMemo } from "react";
import {
  Scale,
  ShieldCheck,
  Sliders,
  DollarSign,
  ArrowRight,
  Copy,
  Check,
  RefreshCw,
  AlertCircle,
  HelpCircle,
  ChevronRight,
  Plus,
  Minus,
  Sparkles,
} from "lucide-react";
import { useCurrency } from "../context/CurrencyContext";

interface RebalanceItem {
  ticker: string;
  name: string;
  current_shares: number;
  current_price: number;
  current_value: number;
  current_weight_pct: number;
  target_weight_pct: number;
  target_value: number;
  delta_value: number;
  delta_shares: number;
  action: "BUY" | "SELL" | "HOLD";
  estimated_order_value: number;
  cash_only_shares: number;
  cash_only_action: "BUY" | "HOLD";
}

interface RebalanceResult {
  portfolio_id: string;
  portfolio_name: string;
  mode: string;
  fresh_cash: number;
  current_total_value: number;
  new_total_value: number;
  items: RebalanceItem[];
  summary: {
    total_buys_value: number;
    total_sells_value: number;
    net_cash_flow: number;
    num_buys: number;
    num_sells: number;
    num_holds: number;
    estimated_fees: number;
    trades_count: number;
  };
}

interface RebalanceWizardProps {
  portfolioId: string;
  portfolioName: string;
  holdingsCount: number;
  maxProfilePositionPct?: number;
  onClose?: () => void;
}

export default function RebalanceWizard({
  portfolioId,
  portfolioName,
  holdingsCount,
  maxProfilePositionPct = 20,
  onClose,
}: RebalanceWizardProps) {
  const { formatPrice } = useCurrency();
  const [mode, setMode] = useState<"equal" | "cap" | "custom">("equal");
  const [maxPositionPct, setMaxPositionPct] = useState<number>(maxProfilePositionPct);
  const [freshCash, setFreshCash] = useState<string>("");
  const [customWeights, setCustomWeights] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RebalanceResult | null>(null);
  const [copied, setCopied] = useState<boolean>(false);
  const [showTaxEfficient, setShowTaxEfficient] = useState<boolean>(false);

  const fetchCalculation = async () => {
    if (!portfolioId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/portfolio/${portfolioId}/rebalance`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode,
          fresh_cash: parseFloat(freshCash) || 0.0,
          max_position_pct: maxPositionPct,
          target_weights: mode === "custom" ? customWeights : undefined,
          fee_per_trade: 1.0,
        }),
      });
      if (!res.ok) {
        throw new Error(`Berechnung fehlgeschlagen (HTTP ${res.status})`);
      }
      const data: RebalanceResult = await res.json();
      setResult(data);

      // Initialize custom weights if empty
      if (mode === "custom" && Object.keys(customWeights).length === 0 && data.items) {
        const initial: Record<string, number> = {};
        data.items.forEach((item) => {
          initial[item.ticker] = item.target_weight_pct;
        });
        setCustomWeights(initial);
      }
    } catch (err: any) {
      setError(err?.message || "Fehler beim Berechnen des Rebalancings.");
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCalculation();
  }, [portfolioId, mode, maxPositionPct]);

  const handleCustomWeightChange = (ticker: string, val: number) => {
    setCustomWeights((prev) => ({
      ...prev,
      [ticker]: Math.max(0, Math.min(100, val)),
    }));
  };

  const copyOrderChecklist = () => {
    if (!result || !result.items) return;
    const lines = [
      `📋 Rebalancing-Plan für ${portfolioName}`,
      `Modus: ${mode.toUpperCase()} | Stand: ${new Date().toLocaleDateString()}`,
      `Gesamtwert: ${formatPrice(result.current_total_value)} -> Neu: ${formatPrice(result.new_total_value)}`,
      "",
      "--- ORDER-CHECKLISTE ---",
    ];

    const activeList = showTaxEfficient
      ? result.items.filter((i) => i.cash_only_action === "BUY")
      : result.items.filter((i) => i.action !== "HOLD");

    if (activeList.length === 0) {
      lines.push("Keine Transaktionen erforderlich. Portfolio ist im Zielkorridor.");
    } else {
      activeList.forEach((item) => {
        if (showTaxEfficient) {
          lines.push(
            `[ ] KAUFEN: ${item.cash_only_shares}x ${item.ticker} (${item.name}) ~ ${formatPrice(item.cash_only_shares * item.current_price)}`,
          );
        } else {
          lines.push(
            `[ ] ${item.action}: ${Math.abs(item.delta_shares)}x ${item.ticker} (${item.name}) ~ ${formatPrice(item.estimated_order_value)} (Soll: ${item.target_weight_pct}%)`,
          );
        }
      });
    }

    if (!showTaxEfficient) {
      lines.push("");
      lines.push(`Geschätzte Gebühren (~1 €/Order): ${formatPrice(result.summary.estimated_fees)}`);
      lines.push(`Netto Cashflow: ${formatPrice(result.summary.net_cash_flow)}`);
    }

    navigator.clipboard.writeText(lines.join("\n"));
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  const hasFreshCash = parseFloat(freshCash) > 0;

  return (
    <section className="surface-panel relative overflow-hidden rounded-[2.2rem] p-6 shadow-sm transition-all sm:p-8">
      {/* Header */}
      <div className="flex flex-col justify-between gap-4 border-b border-black/8 pb-6 dark:border-white/10 md:flex-row md:items-center">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-teal-500/10 text-teal-600 dark:bg-teal-400/15 dark:text-teal-300">
              <Scale className="h-4 w-4" />
            </span>
            <span className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-teal-600 dark:text-teal-400">
              Portfolio Brain • Rebalancing-Wizard
            </span>
          </div>
          <h3 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-3xl">
            1-Klick-Rebalancing-Kalkulator
          </h3>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Berechnet exakte Kauf- und Verkaufsmengen zur Wiederherstellung deiner Zielallokation für{" "}
            <span className="font-semibold text-slate-800 dark:text-slate-200">{portfolioName}</span>.
          </p>
        </div>

        {onClose && (
          <button
            onClick={onClose}
            className="self-start rounded-xl border border-black/8 px-4 py-2 text-xs font-bold text-slate-600 hover:bg-black/5 dark:border-white/10 dark:text-slate-300 md:self-auto"
          >
            Schließen
          </button>
        )}
      </div>

      {/* Mode Selector & Cash Controls */}
      <div className="my-6 grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        {/* Mode Buttons */}
        <div className="rounded-2xl border border-black/8 bg-black/[0.02] p-4 dark:border-white/10 dark:bg-white/5">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Rebalancing-Strategie wählen
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            <button
              onClick={() => setMode("equal")}
              className={`flex flex-col items-start rounded-xl border p-3 text-left transition-all ${
                mode === "equal"
                  ? "border-teal-500/30 bg-teal-500/10 text-teal-900 dark:text-teal-200 shadow-sm"
                  : "border-black/8 bg-white text-slate-700 hover:bg-black/[0.02] dark:border-white/10 dark:bg-slate-900 dark:text-slate-300"
              }`}
            >
              <div className="flex items-center gap-1.5 font-bold text-xs">
                <Scale className="h-3.5 w-3.5" />
                Gleichgewichtung
              </div>
              <div className="mt-1 text-[11px] opacity-75">
                Alle Positionen gleich groß (~{(100 / Math.max(1, holdingsCount)).toFixed(1)}%)
              </div>
            </button>

            <button
              onClick={() => setMode("cap")}
              className={`flex flex-col items-start rounded-xl border p-3 text-left transition-all ${
                mode === "cap"
                  ? "border-teal-500/30 bg-teal-500/10 text-teal-900 dark:text-teal-200 shadow-sm"
                  : "border-black/8 bg-white text-slate-700 hover:bg-black/[0.02] dark:border-white/10 dark:bg-slate-900 dark:text-slate-300"
              }`}
            >
              <div className="flex items-center gap-1.5 font-bold text-xs">
                <ShieldCheck className="h-3.5 w-3.5" />
                Risikodeckel
              </div>
              <div className="mt-1 text-[11px] opacity-75">
                Max. {maxPositionPct}% je Einzelwert
              </div>
            </button>

            <button
              onClick={() => setMode("custom")}
              className={`flex flex-col items-start rounded-xl border p-3 text-left transition-all ${
                mode === "custom"
                  ? "border-teal-500/30 bg-teal-500/10 text-teal-900 dark:text-teal-200 shadow-sm"
                  : "border-black/8 bg-white text-slate-700 hover:bg-black/[0.02] dark:border-white/10 dark:bg-slate-900 dark:text-slate-300"
              }`}
            >
              <div className="flex items-center gap-1.5 font-bold text-xs">
                <Sliders className="h-3.5 w-3.5" />
                Individuell
              </div>
              <div className="mt-1 text-[11px] opacity-75">
                Eigene %-Zielgewichte je Aktie
              </div>
            </button>
          </div>

          {mode === "cap" && (
            <div className="mt-4 flex items-center gap-3">
              <label className="text-xs font-semibold text-slate-600 dark:text-slate-400">
                Maximales Einzelpositionslimit:
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="range"
                  min="10"
                  max="40"
                  step="1"
                  value={maxPositionPct}
                  onChange={(e) => setMaxPositionPct(Number(e.target.value))}
                  className="h-1.5 w-32 accent-teal-600"
                />
                <span className="rounded-md bg-black/5 px-2 py-0.5 text-xs font-bold text-slate-800 dark:bg-white/10 dark:text-white">
                  {maxPositionPct}%
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Fresh Cash & Tax-Efficiency */}
        <div className="rounded-2xl border border-black/8 bg-black/[0.02] p-4 dark:border-white/10 dark:bg-white/5">
          <div className="flex items-center justify-between">
            <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Steueroptimiertes Cash-Rebalancing
            </div>
            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
              Sparplan
            </span>
          </div>
          <div className="mt-2 text-xs text-slate-600 dark:text-slate-400">
            Zahle frisches Kapital ein, um untergewichtete Werte aufzustocken – ohne Verkäufe und Steuerabzug.
          </div>
          <div className="mt-3 flex gap-2">
            <div className="relative flex-1">
              <span className="absolute left-3 top-2.5 text-slate-400 text-sm font-bold">€</span>
              <input
                type="number"
                min="0"
                step="50"
                placeholder="z.B. 500"
                value={freshCash}
                onChange={(e) => setFreshCash(e.target.value)}
                className="w-full rounded-xl border border-black/8 bg-white pl-8 pr-4 py-2 text-sm font-bold text-slate-900 dark:border-white/10 dark:bg-slate-900 dark:text-white"
              />
            </div>
            <button
              onClick={fetchCalculation}
              disabled={loading}
              className="rounded-xl bg-teal-600 px-4 py-2 text-xs font-bold text-white hover:bg-teal-700 disabled:opacity-50"
            >
              Berechnen
            </button>
          </div>
        </div>
      </div>

      {/* Summary KPI Bar */}
      {result && result.summary && (
        <div className="my-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-2xl border border-black/8 bg-white/80 p-4 dark:border-white/10 dark:bg-white/5">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">
              Portfoliowert (Vorher / Nachher)
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-xl font-black text-slate-900 dark:text-white">
                {formatPrice(result.new_total_value)}
              </span>
              {hasFreshCash && (
                <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400">
                  (+{formatPrice(result.fresh_cash)})
                </span>
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-black/8 bg-white/80 p-4 dark:border-white/10 dark:bg-white/5">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">
              Transaktionen nötig
            </div>
            <div className="mt-1 flex items-center gap-2 text-xl font-black text-slate-900 dark:text-white">
              <span>{result.summary.trades_count} Orders</span>
              <span className="text-xs font-bold text-slate-500">
                ({result.summary.num_buys}x Kauf, {result.summary.num_sells}x Verkauf)
              </span>
            </div>
          </div>

          <div className="rounded-2xl border border-black/8 bg-white/80 p-4 dark:border-white/10 dark:bg-white/5">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">
              Netto-Cashflow
            </div>
            <div className="mt-1 text-xl font-black text-slate-900 dark:text-white">
              {formatPrice(result.summary.net_cash_flow)}
            </div>
          </div>

          <div className="rounded-2xl border border-black/8 bg-white/80 p-4 dark:border-white/10 dark:bg-white/5">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">
              Geschätzte Ordergebühren
            </div>
            <div className="mt-1 text-xl font-black text-slate-700 dark:text-slate-300">
              ~{formatPrice(result.summary.estimated_fees)}
            </div>
          </div>
        </div>
      )}

      {/* Tax-Efficient Toggle if fresh cash is added */}
      {hasFreshCash && result && (
        <div className="mb-4 flex items-center justify-between rounded-xl bg-emerald-50/70 p-3.5 border border-emerald-200/60 dark:bg-emerald-950/20 dark:border-emerald-800/40">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
            <span className="text-xs font-bold text-emerald-900 dark:text-emerald-200">
              Reines Zukauf-Rebalancing aktivieren (Keine Verkäufe / Keine Steuern)
            </span>
          </div>
          <button
            onClick={() => setShowTaxEfficient(!showTaxEfficient)}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
              showTaxEfficient
                ? "bg-emerald-600 text-white shadow"
                : "bg-white text-slate-700 border border-black/8 dark:bg-slate-900 dark:text-slate-200"
            }`}
          >
            {showTaxEfficient ? "Aktiv: Nur Nachkäufe" : "Vollständiges Rebalancing"}
          </button>
        </div>
      )}

      {/* Orders Table */}
      {result && result.items && result.items.length > 0 && (
        <div className="overflow-hidden rounded-2xl border border-black/8 bg-white dark:border-white/10 dark:bg-slate-900/60">
          <div className="flex items-center justify-between border-b border-black/6 px-5 py-4 dark:border-white/8">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Ausführungsplan ({result.items.length} Positionen)
            </div>
            <button
              onClick={copyOrderChecklist}
              className="inline-flex items-center gap-1.5 rounded-xl border border-black/8 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 hover:bg-black/5 dark:border-white/10 dark:bg-white/10 dark:text-slate-200"
            >
              {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
              {copied ? "Kopiert!" : "Plan kopieren"}
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-black/6 bg-black/[0.01] text-[11px] font-extrabold uppercase tracking-wider text-slate-500 dark:border-white/8 dark:bg-white/[0.02] dark:text-slate-400">
                <tr>
                  <th className="px-5 py-3">Ticker / Name</th>
                  <th className="px-4 py-3 text-right">Kurs</th>
                  <th className="px-4 py-3 text-right">Ist-Gewicht</th>
                  <th className="px-4 py-3 text-right">Soll-Gewicht</th>
                  <th className="px-4 py-3 text-center">Aktion</th>
                  <th className="px-5 py-3 text-right">Orderwert</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/6 dark:divide-white/8 font-medium">
                {result.items.map((item) => {
                  const isCashOnly = showTaxEfficient;
                  const activeAction = isCashOnly ? item.cash_only_action : item.action;
                  const activeShares = isCashOnly ? item.cash_only_shares : Math.abs(item.delta_shares);
                  const activeOrderVal = isCashOnly
                    ? item.cash_only_shares * item.current_price
                    : item.estimated_order_value;

                  return (
                    <tr key={item.ticker} className="hover:bg-black/[0.01] dark:hover:bg-white/[0.02]">
                      <td className="px-5 py-3.5">
                        <div className="font-bold text-slate-900 dark:text-white">{item.ticker}</div>
                        <div className="text-xs text-slate-500 dark:text-slate-400 truncate max-w-[180px]">
                          {item.name}
                        </div>
                      </td>

                      <td className="px-4 py-3.5 text-right text-slate-700 dark:text-slate-300 font-mono text-xs">
                        {formatPrice(item.current_price)}
                      </td>

                      <td className="px-4 py-3.5 text-right font-mono text-xs text-slate-600 dark:text-slate-400">
                        {item.current_weight_pct.toFixed(1)}%
                      </td>

                      <td className="px-4 py-3.5 text-right font-mono text-xs">
                        {mode === "custom" ? (
                          <input
                            type="number"
                            min="0"
                            max="100"
                            step="1"
                            value={customWeights[item.ticker] ?? item.target_weight_pct}
                            onChange={(e) => handleCustomWeightChange(item.ticker, Number(e.target.value))}
                            className="w-16 rounded-md border border-black/10 bg-white px-1.5 py-1 text-right text-xs font-bold text-slate-900 dark:border-white/10 dark:bg-slate-800 dark:text-white"
                          />
                        ) : (
                          <span className="font-bold text-slate-900 dark:text-white">
                            {item.target_weight_pct.toFixed(1)}%
                          </span>
                        )}
                      </td>

                      <td className="px-4 py-3.5 text-center">
                        {activeAction === "BUY" ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-extrabold text-emerald-700 ring-1 ring-emerald-300 dark:bg-emerald-950/40 dark:text-emerald-300 dark:ring-emerald-700/50">
                            <Plus className="h-3 w-3" />
                            KAUFEN {activeShares} Stk
                          </span>
                        ) : activeAction === "SELL" ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2.5 py-1 text-[11px] font-extrabold text-rose-700 ring-1 ring-rose-300 dark:bg-rose-950/40 dark:text-rose-300 dark:ring-rose-700/50">
                            <Minus className="h-3 w-3" />
                            VERKAUFEN {activeShares} Stk
                          </span>
                        ) : (
                          <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-400">
                            HALTEN
                          </span>
                        )}
                      </td>

                      <td className="px-5 py-3.5 text-right font-mono text-xs font-bold text-slate-900 dark:text-white">
                        {activeAction !== "HOLD" ? `~${formatPrice(activeOrderVal)}` : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Footer Info */}
      <div className="mt-5 flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
        <HelpCircle className="h-4 w-4 shrink-0 text-slate-400" />
        <span>
          <strong>Hinweis:</strong> Stückzahlen werden auf ganze Anteile gerundet. Orders werden als
          unverbindliche Handlungsvorschläge berechnet und nicht automatisch an einen Broker gesendet.
        </span>
      </div>
    </section>
  );
}
