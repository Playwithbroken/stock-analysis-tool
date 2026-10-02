import React, { useMemo, useState } from "react";

interface WatchItem {
  id?: string;
  kind: string;
  value: string;
}

interface TickerEvent {
  ticker?: string;
  owner_name?: string;
  owner_title?: string;
  trade_date?: string;
  filed_date?: string;
  action?: string;
  shares?: number;
  value_label?: string;
  delay_days?: number;
  source_url?: string;
}

interface TickerSignal {
  ticker: string;
  title: string;
  source_url?: string;
  note?: string;
  error?: string;
  events: TickerEvent[];
}

interface PoliticianTrade {
  asset?: string;
  ticker?: string | null;
  action?: string;
  trade_date?: string;
  notification_date?: string;
  amount_range?: string;
  delay_days?: number;
  source_url?: string;
}

interface PoliticianSignal {
  name: string;
  source_url?: string;
  error?: string;
  trades: PoliticianTrade[];
  reports?: Array<Record<string, any>>;
  summary?: {
    report_count?: number;
    trade_count?: number;
    buy_count?: number;
    sell_count?: number;
    latest_trade_date?: string | null;
    avg_delay_days?: number | null;
  };
  playbook?: {
    setup?: string;
    leverage?: string;
    signal_grade?: string;
    freshness?: string;
    confidence?: number;
    estimated_exposure_label?: string;
    top_tickers?: string[];
    thesis?: string;
    trigger?: string;
    next_action?: string;
    invalidation?: string;
    compliance_note?: string;
    copy_text?: string;
  } | null;
}

interface WatchlistData {
  items: WatchItem[];
  ticker_signals: TickerSignal[];
  politician_signals: PoliticianSignal[];
}

interface SignalWatchlistPanelProps {
  data: WatchlistData | null;
  onAnalyze: (ticker: string) => void;
  onRefresh: () => Promise<void>;
}

export function getTickerBadge(ticker: string) {
  const sym = String(ticker || "").toUpperCase().trim();
  if (sym.endsWith(".DE") || sym.endsWith(".F")) return { flag: "🇩🇪", region: "DAX / Deutschland", currency: "EUR" };
  if (sym.endsWith(".AS")) return { flag: "🇳🇱", region: "AEX / Niederlande", currency: "EUR" };
  if (sym.endsWith(".PA")) return { flag: "🇫🇷", region: "CAC / Frankreich", currency: "EUR" };
  if (sym.endsWith(".MI")) return { flag: "🇮🇹", region: "MIB / Italien", currency: "EUR" };
  if (sym.endsWith(".MC")) return { flag: "🇪🇸", region: "IBEX / Spanien", currency: "EUR" };
  if (sym.endsWith(".L")) return { flag: "🇬🇧", region: "LSE / UK", currency: "GBP" };
  if (sym.endsWith("-USD")) return { flag: "🪙", region: "Crypto", currency: "USD" };
  return { flag: "🇺🇸", region: "US Markt", currency: "USD" };
}

const initialForm = { kind: "ticker", value: "" };
const quickIdeas = [
  { kind: "ticker", value: "SAP.DE" },
  { kind: "ticker", value: "RHM.DE" },
  { kind: "ticker", value: "ASML.AS" },
  { kind: "ticker", value: "SIE.DE" },
  { kind: "ticker", value: "NVDA" },
  { kind: "ticker", value: "PLTR" },
  { kind: "ticker", value: "AAPL" },
  { kind: "ticker", value: "MSFT" },
  { kind: "politician", value: "Nancy Pelosi" },
  { kind: "politician", value: "Scott Peters" },
];

function formatLine(parts: Array<string | number | null | undefined>) {
  return parts
    .filter((part) => part !== null && part !== undefined && `${part}`.trim() !== "")
    .join(" | ");
}

export default function SignalWatchlistPanel({
  data,
  onAnalyze,
  onRefresh,
}: SignalWatchlistPanelProps) {
  const [form, setForm] = useState(initialForm);
  const [editingItem, setEditingItem] = useState<WatchItem | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<string>("");
  const [notificationStatus, setNotificationStatus] = useState<any>(null);

  // Institutional 360° Check & Structural Stops Radar State
  const [selectedRadarTicker, setSelectedRadarTicker] = useState<string>("SAP.DE");
  const [radarData, setRadarData] = useState<any>(null);
  const [radarLoading, setRadarLoading] = useState<boolean>(false);
  const [radarError, setRadarError] = useState<string | null>(null);

  const [scannerData, setScannerData] = useState<any>(null);
  const [scannerLoading, setScannerLoading] = useState<boolean>(false);
  const [showScannerResults, setShowScannerResults] = useState<boolean>(false);

  const [orbScannerData, setOrbScannerData] = useState<any>(null);
  const [orbScannerLoading, setOrbScannerLoading] = useState<boolean>(false);
  const [showOrbResults, setShowOrbResults] = useState<boolean>(false);
  const [tickerOrbData, setTickerOrbData] = useState<any>(null);

  const [matrixData, setMatrixData] = useState<any>(null);
  const [matrixLoading, setMatrixLoading] = useState<boolean>(false);
  const [showMatrix, setShowMatrix] = useState<boolean>(false);

  const [sizingCapital, setSizingCapital] = useState<number>(50000);
  const [sizingRiskPct, setSizingRiskPct] = useState<number>(0.75);
  const [sizingData, setSizingData] = useState<any>(null);
  const [sizingLoading, setSizingLoading] = useState<boolean>(false);

  const [breadthData, setBreadthData] = useState<any>(null);
  const [breadthLoading, setBreadthLoading] = useState<boolean>(false);
  const [showBreadth, setShowBreadth] = useState<boolean>(false);

  const [tradeActionMessage, setTradeActionMessage] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<boolean>(false);

  const items = data?.items || [];
  const tickerSignals = data?.ticker_signals || [];
  const politicianSignals = data?.politician_signals || [];

  const groupedItems = useMemo(
    () => ({
      ticker: items.filter((item) => item.kind === "ticker"),
      politician: items.filter((item) => item.kind === "politician"),
    }),
    [items],
  );

  React.useEffect(() => {
    if ((!selectedRadarTicker || selectedRadarTicker === "SAP.DE") && groupedItems.ticker.length > 0) {
      // Pick first ticker if available
      const first = groupedItems.ticker[0].value;
      if (first) setSelectedRadarTicker(first);
    }
  }, [groupedItems.ticker]);

  const loadRadar = React.useCallback(async (ticker: string) => {
    if (!ticker) return;
    setRadarLoading(true);
    setRadarError(null);
    try {
      const res = await fetch(`/api/trading/radar/${encodeURIComponent(ticker)}`);
      if (!res.ok) {
        throw new Error(`Fehler ${res.status}`);
      }
      const json = await res.json();
      setRadarData(json);
    } catch (err: any) {
      setRadarError(err.message || "Fehler beim Laden des 360°-Radars.");
      setRadarData(null);
    } finally {
      setRadarLoading(false);
    }
  }, []);

  const loadOrbForTicker = React.useCallback(async (ticker: string) => {
    if (!ticker) return;
    try {
      const res = await fetch(`/api/trading/orb/${encodeURIComponent(ticker)}?or_minutes=30`);
      if (res.ok) {
        const j = await res.json();
        setTickerOrbData(j);
      } else {
        setTickerOrbData(null);
      }
    } catch {
      setTickerOrbData(null);
    }
  }, []);

  const loadSizingForTicker = React.useCallback(async (ticker: string, cap: number, rPct: number) => {
    if (!ticker) return;
    setSizingLoading(true);
    try {
      const res = await fetch(`/api/trading/sizing-calculator/${encodeURIComponent(ticker)}?capital=${cap}&risk_pct=${rPct}`);
      if (res.ok) {
        const j = await res.json();
        setSizingData(j);
      } else {
        setSizingData(null);
      }
    } catch {
      setSizingData(null);
    } finally {
      setSizingLoading(false);
    }
  }, []);

  React.useEffect(() => {
    if (selectedRadarTicker) {
      loadRadar(selectedRadarTicker);
      loadOrbForTicker(selectedRadarTicker);
      loadSizingForTicker(selectedRadarTicker, sizingCapital, sizingRiskPct);
    }
  }, [selectedRadarTicker, loadRadar, loadOrbForTicker, loadSizingForTicker, sizingCapital, sizingRiskPct]);

  const runCombinedScan = async () => {
    setScannerLoading(true);
    setShowScannerResults(true);
    try {
      const res = await fetch("/api/trading/combined-scanner");
      if (res.ok) {
        const json = await res.json();
        setScannerData(json);
      }
    } catch (err) {
      console.error("Scanner error:", err);
    } finally {
      setScannerLoading(false);
    }
  };

  const runOrbScan = async () => {
    setOrbScannerLoading(true);
    setShowOrbResults(true);
    try {
      const res = await fetch("/api/trading/orb-scan?or_minutes=30");
      if (res.ok) {
        const json = await res.json();
        setOrbScannerData(json);
      }
    } catch (err) {
      console.error("ORB scan error:", err);
    } finally {
      setOrbScannerLoading(false);
    }
  };

  const runMatrixFetch = async () => {
    setMatrixLoading(true);
    setShowMatrix(true);
    try {
      const res = await fetch("/api/trading/correlation-matrix");
      if (res.ok) {
        const json = await res.json();
        setMatrixData(json);
      }
    } catch (err) {
      console.error("Matrix error:", err);
    } finally {
      setMatrixLoading(false);
    }
  };

  const loadMarketBreadth = async () => {
    setBreadthLoading(true);
    setShowBreadth(true);
    try {
      const res = await fetch("/api/trading/market-breadth");
      if (res.ok) {
        const json = await res.json();
        setBreadthData(json);
      }
    } catch (err) {
      console.error("Market breadth fetch error:", err);
    } finally {
      setBreadthLoading(false);
    }
  };

  const handleScaleOut = async (ticker: string) => {
    setActionLoading(true);
    setTradeActionMessage(null);
    try {
      const res = await fetch(`/api/trading/scale-out/${encodeURIComponent(ticker)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fraction: 0.50, notes: "Web Radar 50% Scale-Out" }),
      });
      const resData = await res.json();
      if (res.ok) {
        setTradeActionMessage(`✂️ 50% Teilverkauf für ${ticker} gebucht! Restposition auf Break-Even gesichert.`);
        if (onRefresh) onRefresh();
        if (selectedRadarTicker) loadRadar(selectedRadarTicker);
      } else {
        setTradeActionMessage(`❌ ${resData.detail || "Scale-Out fehlgeschlagen."}`);
      }
    } catch (e: any) {
      setTradeActionMessage(`❌ Fehler: ${e.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleOpenPaperTrade = async (ticker: string, quantity?: number) => {
    setActionLoading(true);
    setTradeActionMessage(null);
    try {
      const res = await fetch("/api/trading/open-edge-paper-trade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker, quantity: quantity && quantity > 0 ? quantity : undefined }),
      });
      const resData = await res.json();
      if (res.ok) {
        setTradeActionMessage(`✅ ${resData.message || `Paper Trade für ${ticker} gebucht!`}`);
        if (onRefresh) onRefresh();
      } else {
        setTradeActionMessage(`❌ ${resData.detail || "Fehler beim Buchen."}`);
      }
    } catch (e: any) {
      setTradeActionMessage(`❌ Fehler: ${e.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleSendTelegram = async (ticker: string) => {
    setActionLoading(true);
    setTradeActionMessage(null);
    try {
      const res = await fetch("/api/trading/telegram/send-edge-setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker, force: true }),
      });
      const resData = await res.json();
      if (res.ok) {
        setTradeActionMessage(`📲 Setup für ${ticker} direkt an dein Smartphone gesendet!`);
      } else {
        setTradeActionMessage(`❌ ${resData.detail || "Telegram-Versand fehlgeschlagen."}`);
      }
    } catch (e: any) {
      setTradeActionMessage(`❌ Fehler: ${e.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  React.useEffect(() => {
    const loadStatus = async () => {
      try {
        const res = await fetch("/api/notifications/status");
        const payload = await res.json();
        setNotificationStatus(payload);
      } catch {
        setNotificationStatus(null);
      }
    };
    loadStatus();
  }, []);

  const submitItem = async () => {
    if (!form.value.trim()) return;
    setSubmitting(true);
    try {
      if (editingItem) {
        await fetch(
          `/api/signals/watchlist/items?kind=${encodeURIComponent(editingItem.kind)}&value=${encodeURIComponent(editingItem.value)}`,
          { method: "DELETE" },
        );
      }
      await fetch("/api/signals/watchlist/items", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      setForm(initialForm);
      setEditingItem(null);
      await onRefresh();
      setStatus(editingItem ? "Watch item aktualisiert." : "Watch item hinzugefuegt.");
    } finally {
      setSubmitting(false);
    }
  };

  const removeItem = async (kind: string, value: string) => {
    setSubmitting(true);
    try {
      await fetch(
        `/api/signals/watchlist/items?kind=${encodeURIComponent(kind)}&value=${encodeURIComponent(value)}`,
        { method: "DELETE" },
      );
      await onRefresh();
      setStatus("Watch item entfernt.");
      if (editingItem?.kind === kind && editingItem?.value === value) {
        setEditingItem(null);
        setForm(initialForm);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const startEditing = (item: WatchItem) => {
    setEditingItem(item);
    setForm({ kind: item.kind, value: item.value });
    setStatus("");
  };

  const cancelEditing = () => {
    setEditingItem(null);
    setForm(initialForm);
    setStatus("");
  };

  const triggerAlertCheck = async (
    mode: "check" | "test" | "brief" | "morning" | "europe" | "usa",
  ) => {
    setSubmitting(true);
    try {
      const endpoint =
        mode === "check"
          ? "/api/signals/alerts/check"
          : mode === "test"
            ? "/api/signals/alerts/test"
            : mode === "brief"
              ? "/api/signals/alerts/daily-brief"
              : mode === "morning"
                ? "/api/signals/alerts/morning-brief"
                : `/api/signals/alerts/open-brief/${mode}`;
      const res = await fetch(endpoint, { method: "POST" });
      const payload = await res.json();
      setStatus(payload.message || "Aktion ausgefuehrt.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <section className="surface-panel rounded-[2rem] p-6">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="text-[11px] font-extrabold uppercase tracking-[0.24em] text-slate-500">
              Personal radar
            </div>
            <h2 className="mt-2 text-4xl text-slate-900">Follow what matters to you.</h2>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-600">
              Beobachte konkrete Ticker ueber SEC Form 4 und House-Mitglieder ueber offizielle PTR-Filings.
            </p>
          </div>

          <div className="flex w-full flex-col gap-3 lg:max-w-xl lg:flex-row">
            <select
              value={form.kind}
              onChange={(e) => setForm((prev) => ({ ...prev, kind: e.target.value }))}
              className="rounded-2xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800"
            >
              <option value="ticker">Ticker</option>
              <option value="politician">Politiker (House)</option>
            </select>
            <input
              value={form.value}
              onChange={(e) => setForm((prev) => ({ ...prev, value: e.target.value }))}
              placeholder={form.kind === "ticker" ? "AAPL, NVDA, SAP" : "Nancy Pelosi"}
              className="flex-1 rounded-2xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800 placeholder:text-slate-400"
            />
            <button
              onClick={submitItem}
              disabled={submitting || !form.value.trim()}
              className="rounded-2xl bg-[var(--accent)] px-5 py-3 text-xs font-extrabold uppercase tracking-[0.18em] text-white transition-colors hover:bg-[var(--accent-strong)] disabled:opacity-50"
            >
              {editingItem ? "Speichern" : "Hinzufuegen"}
            </button>
            {editingItem ? (
              <button
                onClick={cancelEditing}
                disabled={submitting}
                className="rounded-2xl border border-black/8 bg-white px-5 py-3 text-xs font-extrabold uppercase tracking-[0.18em] text-slate-700 disabled:opacity-50"
              >
                Abbrechen
              </button>
            ) : null}
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            onClick={() => triggerAlertCheck("check")}
            disabled={submitting}
            className="rounded-xl border border-black/8 bg-white px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-700 disabled:opacity-50"
          >
            Check now
          </button>
          <button
            onClick={() => triggerAlertCheck("test")}
            disabled={submitting}
            className="rounded-xl bg-[var(--accent)] px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-white transition-colors hover:bg-[var(--accent-strong)] disabled:opacity-50"
          >
            Test alerts
          </button>
          <button
            onClick={() => triggerAlertCheck("brief")}
            disabled={submitting}
            className="rounded-xl border border-black/8 bg-white px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-700 disabled:opacity-50"
          >
            Daily brief
          </button>
          <button
            onClick={() => triggerAlertCheck("morning")}
            disabled={submitting}
            className="rounded-xl border border-black/8 bg-white px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-700 disabled:opacity-50"
          >
            Morning brief
          </button>
          <button
            onClick={() => triggerAlertCheck("europe")}
            disabled={submitting}
            className="rounded-xl border border-black/8 bg-white px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-700 disabled:opacity-50"
          >
            Europe open
          </button>
          <button
            onClick={() => triggerAlertCheck("usa")}
            disabled={submitting}
            className="rounded-xl border border-black/8 bg-white px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-700 disabled:opacity-50"
          >
            US open
          </button>
          {status ? (
            <div className="flex items-center text-xs font-semibold text-slate-500">
              {status}
            </div>
          ) : null}
        </div>

        {notificationStatus && (
          <div className="mt-5 grid gap-3 md:grid-cols-3">
            <div className="rounded-[1.3rem] border border-black/8 bg-white/70 p-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                Telegram
              </div>
              <div className="mt-2 text-sm font-black text-slate-900">
                {notificationStatus.telegram?.configured
                  ? notificationStatus.telegram?.enabled
                    ? "Live"
                    : "Configured, disabled"
                  : "Bot missing"}
              </div>
              <div className="mt-1 text-xs text-slate-500">
                Sofort-Alerts und Briefings laufen nur ueber Telegram.
              </div>
            </div>
            <div className="rounded-[1.3rem] border border-black/8 bg-white/70 p-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                Weitere Push-Kanäle
              </div>
              <div className="mt-2 text-sm font-black text-slate-900">
                Aus
              </div>
              <div className="mt-1 text-xs text-slate-500">
                Email und Browser-Push sind aus. Telegram bleibt der einzige aktive Alert-Kanal.
              </div>
            </div>
            <div className="rounded-[1.3rem] border border-black/8 bg-white/70 p-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                Open schedule
              </div>
              <div className="mt-2 text-sm font-black text-slate-900">
                {notificationStatus.schedule?.timezone}
              </div>
              <div className="mt-1 text-xs text-slate-500">
                EU {notificationStatus.schedule?.europe_open} | US {notificationStatus.schedule?.us_open}
              </div>
            </div>
          </div>
        )}

        <div className="mt-5 flex flex-wrap gap-3">
          {[...groupedItems.ticker, ...groupedItems.politician].map((item) => {
            const badge = item.kind === "ticker" ? getTickerBadge(item.value) : null;
            return (
              <div
                key={`${item.kind}:${item.value}`}
                className="flex items-center gap-2 rounded-full border border-black/8 bg-white px-3 py-2 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-700 shadow-sm"
              >
                <span>
                  {item.kind === "ticker"
                    ? `${badge?.flag} ${item.value}`
                    : `🏛️ House: ${item.value}`}
                </span>
                {badge ? (
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[9px] font-semibold text-slate-500 lowercase">
                    {badge.currency}
                  </span>
                ) : null}
                {item.kind === "ticker" && (
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedRadarTicker(item.value);
                      const el = document.getElementById("institutional-radar-section");
                      if (el) el.scrollIntoView({ behavior: "smooth" });
                    }}
                    className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-1 text-[10px] font-extrabold text-emerald-800 transition-colors hover:bg-emerald-500/20"
                    title="360° Check & Stop Levels"
                  >
                    360° &amp; Stops
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => startEditing(item)}
                  className="rounded-full border border-black/8 bg-black/[0.02] px-2 py-1 text-[10px] font-extrabold text-slate-600 transition-colors hover:border-[var(--accent)]/25 hover:text-[var(--accent)]"
                >
                  Edit
                </button>
                <button
                  type="button"
                  onClick={() => removeItem(item.kind, item.value)}
                  className="rounded-full border border-red-500/20 bg-red-500/10 px-2 py-1 text-[10px] font-extrabold text-red-700 transition-colors hover:bg-red-500/15"
                >
                  Remove
                </button>
              </div>
            );
          })}
        </div>

        {!items.length && (
          <div className="mt-5">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Quick start
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {quickIdeas.map((idea) => {
                const badge = idea.kind === "ticker" ? getTickerBadge(idea.value) : null;
                return (
                  <button
                    key={`${idea.kind}:${idea.value}`}
                    onClick={() => setForm(idea)}
                    className="rounded-full border border-black/8 bg-white px-3 py-2 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-700 hover:border-[var(--accent)]/30 hover:bg-slate-50 transition-colors"
                  >
                    {idea.kind === "ticker" ? `${badge?.flag} ${idea.value}` : `🏛️ House: ${idea.value}`}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </section>

      {/* INSTITUTIONAL 360° CHECK & STRUCTURAL STOP RADAR */}
      <section id="institutional-radar-section" className="surface-panel rounded-[2rem] p-6 space-y-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="flex h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              <div className="text-[11px] font-extrabold uppercase tracking-[0.24em] text-emerald-700">
                Institutional Radar &amp; Stop-Loss Rechner
              </div>
            </div>
            <h3 className="mt-1 text-2xl font-black text-slate-900">
              360° Multi-Faktor Check &amp; Strukturelle Stops
            </h3>
            <p className="mt-1 text-xs text-slate-500">
              Echtzeit-Synchronisation mit dem Telegram-Bot (@Playwithaktien_bot). VAL, POC, Options GEX, AVWAP und Stop-Berechnung auf Knopfdruck.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <a
              href="/api/trading/journal/export?format=csv"
              download="trading_journal.csv"
              className="rounded-xl border border-black/8 bg-white px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-700 shadow-sm transition-colors hover:bg-slate-50 flex items-center gap-1.5"
              title="Vollständiges Journal als CSV herunterladen"
            >
              📥 Journal (CSV)
            </a>
            <a
              href="/api/trading/journal/export?format=markdown"
              download="trading_journal.md"
              className="rounded-xl border border-black/8 bg-white px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-700 shadow-sm transition-colors hover:bg-slate-50 flex items-center gap-1.5"
              title="Vollständiges Journal als Markdown herunterladen"
            >
              📖 Journal (MD)
            </a>
            <button
              onClick={runOrbScan}
              disabled={orbScannerLoading}
              className="rounded-xl border border-amber-500/20 bg-amber-500/10 px-3.5 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-amber-900 shadow-sm transition-colors hover:bg-amber-500/20 disabled:opacity-50"
            >
              {orbScannerLoading ? "Scanne ORB..." : "⚡ ORB Scanner (15m/30m)"}
            </button>
            <button
              onClick={runMatrixFetch}
              disabled={matrixLoading}
              className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-3.5 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-emerald-900 shadow-sm transition-colors hover:bg-emerald-500/20 disabled:opacity-50"
            >
              {matrixLoading ? "Berechne..." : "🌐 Korrelations-Matrix"}
            </button>
            <button
              onClick={loadMarketBreadth}
              disabled={breadthLoading}
              className="rounded-xl border border-indigo-500/20 bg-indigo-500/10 px-3.5 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-indigo-900 shadow-sm transition-colors hover:bg-indigo-500/20 disabled:opacity-50"
            >
              {breadthLoading ? "Lade Internals..." : "📊 Marktbreite & Internals"}
            </button>
            <button
              onClick={runCombinedScan}
              disabled={scannerLoading}
              className="rounded-xl border border-black/8 bg-white px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-700 shadow-sm transition-colors hover:bg-slate-50 disabled:opacity-50"
            >
              {scannerLoading ? "Scanne Watchlist..." : "🔍 Multi-Asset Scanner (FVG + POC)"}
            </button>
            <button
              onClick={() => loadRadar(selectedRadarTicker)}
              disabled={radarLoading}
              className="rounded-xl bg-slate-900 px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-white transition-colors hover:bg-slate-800 disabled:opacity-50"
            >
              {radarLoading ? "Aktualisiere..." : "🔄 Refresh"}
            </button>
          </div>
        </div>

        {/* Ticker Selector Pills */}
        <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-black/5">
          <span className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-400 mr-1">
            Ticker wählen:
          </span>
          {groupedItems.ticker.map((item) => {
            const b = getTickerBadge(item.value);
            const isSelected = selectedRadarTicker === item.value;
            return (
              <button
                key={`radar-sel-${item.value}`}
                onClick={() => setSelectedRadarTicker(item.value)}
                className={`flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-black transition-all ${
                  isSelected
                    ? "bg-[var(--accent)] text-white shadow-md scale-105"
                    : "border border-black/8 bg-white text-slate-700 hover:border-black/20"
                }`}
              >
                <span>{b.flag}</span>
                <span>{item.value}</span>
              </button>
            );
          })}
        </div>

        {/* Scanner Results Drawer */}
        {showScannerResults && scannerData && (
          <div className="rounded-2xl border border-black/8 bg-slate-50 p-4 space-y-4 animate-in fade-in">
            <div className="flex items-center justify-between">
              <div className="text-[11px] font-extrabold uppercase tracking-[0.2em] text-slate-700">
                🔍 Multi-Asset Radar Ergebnis ({scannerData.scanned_count} Titel analysiert)
              </div>
              <button
                onClick={() => setShowScannerResults(false)}
                className="text-xs font-bold text-slate-500 hover:text-slate-800"
              >
                Schließen ✕
              </button>
            </div>

            {/* Doppel-Konfluenz */}
            {scannerData.confluence_matches?.length ? (
              <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-3">
                <div className="text-xs font-black text-amber-900">
                  🎯 Doppel-Konfluenz Treffer (FVG + Volume Profile):
                </div>
                <div className="mt-1 space-y-1">
                  {scannerData.confluence_matches.map((c: any, idx: number) => (
                    <div key={idx} className="flex items-center justify-between text-xs text-amber-950">
                      <span className="font-extrabold">{c.ticker}:</span>
                      <span>{c.vp?.description} + {c.fvg?.description}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="grid gap-3 md:grid-cols-2">
              {/* Volume Profile Retests */}
              <div className="rounded-xl border border-black/5 bg-white p-3">
                <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                  📊 Volume Profile Retests (POC / VAH / VAL)
                </div>
                <div className="mt-2 space-y-1 text-xs">
                  {scannerData.volume_profile_matches?.length ? (
                    scannerData.volume_profile_matches.slice(0, 5).map((v: any, idx: number) => (
                      <div key={idx} className="flex items-center justify-between py-0.5 border-b border-black/5 last:border-0">
                        <span className="font-extrabold text-slate-900">{v.ticker}</span>
                        <span className="text-slate-600">{v.description}</span>
                        <span className="text-[10px] font-bold text-emerald-700">{v.dist_pct > 0 ? `+${v.dist_pct}%` : `${v.dist_pct}%`}</span>
                      </div>
                    ))
                  ) : (
                    <div className="text-slate-500 italic">Keine aktuellen Boundary-Retests.</div>
                  )}
                </div>
              </div>

              {/* Fair Value Gaps */}
              <div className="rounded-xl border border-black/5 bg-white p-3">
                <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                  🕳️ Fair Value Gaps (Smart Money Zonen)
                </div>
                <div className="mt-2 space-y-1 text-xs">
                  {scannerData.fvg_matches?.length ? (
                    scannerData.fvg_matches.slice(0, 5).map((f: any, idx: number) => (
                      <div key={idx} className="flex items-center justify-between py-0.5 border-b border-black/5 last:border-0">
                        <span className="font-extrabold text-slate-900">{f.ticker}</span>
                        <span className="text-slate-600">{f.description}</span>
                      </div>
                    ))
                  ) : (
                    <div className="text-slate-500 italic">Keine aktiven Gaps in unmittelbarer Kursnähe.</div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ORB Scanner Results Drawer */}
        {showOrbResults && orbScannerData && (
          <div className="rounded-2xl border border-amber-500/20 bg-amber-50/50 p-4 space-y-4 animate-in fade-in">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-lg">⚡</span>
                <div className="text-[11px] font-extrabold uppercase tracking-[0.2em] text-amber-900">
                  Intraday ORB Scanner ({orbScannerData.or_minutes}m Eröffnungs-Range)
                </div>
              </div>
              <button
                onClick={() => setShowOrbResults(false)}
                className="text-xs font-bold text-slate-500 hover:text-slate-800"
              >
                Schließen ✕
              </button>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl border border-black/5 bg-white p-3 text-center">
                <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">Gescannte Titel</div>
                <div className="text-base font-black text-slate-900">{orbScannerData.scanned_count}</div>
              </div>
              <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3 text-center">
                <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-emerald-800">Bullische Ausbrüche (&gt; High)</div>
                <div className="text-base font-black text-emerald-950">{orbScannerData.breakouts_count}</div>
              </div>
              <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-center">
                <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-red-800">Bärische Breakdowns (&lt; Low)</div>
                <div className="text-base font-black text-red-950">{orbScannerData.breakdowns_count}</div>
              </div>
            </div>

            {orbScannerData.breakouts?.length ? (
              <div className="rounded-xl border border-emerald-500/20 bg-white p-3 space-y-2">
                <div className="text-xs font-black text-emerald-900">
                  🚀 Aktive Bullische Ausbrüche (Momentum Long):
                </div>
                <div className="grid gap-2 md:grid-cols-2">
                  {orbScannerData.breakouts.map((b: any, idx: number) => (
                    <div key={idx} className="flex items-center justify-between rounded-xl border border-black/5 bg-slate-50 p-2.5 text-xs">
                      <div>
                        <div className="flex items-center gap-1.5 font-black text-slate-900">
                          <span>{b.ticker}</span>
                          <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 text-[9px] font-bold text-emerald-900">
                            +{b.distance_pct}%
                          </span>
                          {b.volume_confirmed && (
                            <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[9px] font-bold text-amber-900">
                              🔥 RV: {b.relative_volume}x
                            </span>
                          )}
                        </div>
                        <div className="mt-0.5 text-[10px] text-slate-500">
                          Kurs: {b.currency_symbol}{b.spot_price?.toFixed(2)} | High: {b.currency_symbol}{b.orb_high?.toFixed(2)} | Stop: {b.currency_symbol}{b.invalidation_stop?.toFixed(2)}
                        </div>
                      </div>
                      <button
                        onClick={() => {
                          setSelectedRadarTicker(b.ticker);
                          handleOpenPaperTrade(b.ticker);
                        }}
                        className="rounded-lg bg-emerald-600 px-3 py-1.5 text-[10px] font-black text-white hover:bg-emerald-700 transition-colors"
                      >
                        Buchen
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {orbScannerData.breakdowns?.length ? (
              <div className="rounded-xl border border-red-500/20 bg-white p-3 space-y-2">
                <div className="text-xs font-black text-red-900">
                  ⚡ Aktive Bärische Breakdowns (Short / Risk-Off):
                </div>
                <div className="grid gap-2 md:grid-cols-2">
                  {orbScannerData.breakdowns.map((b: any, idx: number) => (
                    <div key={idx} className="flex items-center justify-between rounded-xl border border-black/5 bg-slate-50 p-2.5 text-xs">
                      <div>
                        <div className="flex items-center gap-1.5 font-black text-slate-900">
                          <span>{b.ticker}</span>
                          <span className="rounded bg-red-500/20 px-1.5 py-0.5 text-[9px] font-bold text-red-900">
                            -{b.distance_pct}%
                          </span>
                        </div>
                        <div className="mt-0.5 text-[10px] text-slate-500">
                          Kurs: {b.currency_symbol}{b.spot_price?.toFixed(2)} | Low: {b.currency_symbol}{b.orb_low?.toFixed(2)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        )}

        {/* Correlation Matrix Heatmap Drawer */}
        {showMatrix && matrixData && (
          <div className="rounded-2xl border border-black/8 bg-white p-4 space-y-4 animate-in fade-in overflow-hidden">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[11px] font-extrabold uppercase tracking-[0.2em] text-slate-700">
                  🌐 Watchlist &amp; Portfolio Korrelations-Matrix (90 Tage Pearson r)
                </div>
                <div className="text-xs text-slate-500">
                  Identifiziert Cluster-Risiken &amp; zeitgleiche Drawdown-Gefahr zwischen deinen offenen Positionen.
                </div>
              </div>
              <button
                onClick={() => setShowMatrix(false)}
                className="text-xs font-bold text-slate-500 hover:text-slate-800"
              >
                Schließen ✕
              </button>
            </div>

            {matrixData.high_correlation_pairs?.length ? (
              <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 space-y-1.5">
                <div className="text-xs font-black text-amber-900">
                  ⚠️ Stark korrelierende Cluster-Paare (r ≥ 0.70):
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                  {matrixData.high_correlation_pairs.slice(0, 6).map((p: any, idx: number) => (
                    <span key={idx} className="rounded-lg bg-white px-2.5 py-1 border border-black/5 font-extrabold text-slate-800">
                      {p.ticker_a} ↔ {p.ticker_b}: <b className="text-amber-900 font-black">r = {p.correlation}</b> ({p.cluster_level})
                    </span>
                  ))}
                </div>
              </div>
            ) : null}

            {/* Matrix Table */}
            <div className="overflow-x-auto max-h-96 border border-black/5 rounded-xl">
              <table className="w-full text-center text-[10px] border-collapse">
                <thead>
                  <tr className="bg-slate-100 border-b border-black/5">
                    <th className="p-2 font-extrabold text-slate-600 sticky left-0 bg-slate-100 z-10">Symbol</th>
                    {matrixData.tickers?.map((sym: string) => (
                      <th key={`th-${sym}`} className="p-2 font-extrabold text-slate-700 min-w-14">
                        {sym.replace(".DE", "")}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {matrixData.tickers?.map((rowSym: string) => (
                    <tr key={`tr-${rowSym}`} className="border-b border-black/5">
                      <td className="p-2 font-black text-slate-900 sticky left-0 bg-white text-left">
                        {rowSym}
                      </td>
                      {matrixData.tickers?.map((colSym: string) => {
                        const val = matrixData.matrix?.[rowSym]?.[colSym];
                        if (val === undefined) return <td key={`${rowSym}-${colSym}`} className="p-1 text-slate-400">-</td>;
                        const isDiag = rowSym === colSym;
                        let cellClass = "bg-slate-50 text-slate-600";
                        if (!isDiag) {
                          if (val >= 0.85) cellClass = "bg-red-500 text-white font-black";
                          else if (val >= 0.70) cellClass = "bg-amber-400 text-slate-900 font-bold";
                          else if (val >= 0.30) cellClass = "bg-amber-50 text-slate-700";
                          else if (val >= 0.0) cellClass = "bg-emerald-50 text-emerald-800";
                          else cellClass = "bg-emerald-500 text-white font-black";
                        }
                        return (
                          <td
                            key={`${rowSym}-${colSym}`}
                            className={`p-1 font-bold ${cellClass}`}
                            title={`${rowSym} ↔ ${colSym}: r = ${val}`}
                          >
                            {isDiag ? "1.00" : val?.toFixed(2)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Matrix Legend */}
            <div className="flex flex-wrap items-center gap-3 pt-1 text-[10px] font-bold text-slate-500">
              <span>Legende:</span>
              <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded bg-emerald-500 inline-block" /> Diversifikation (&lt; 0.0)</span>
              <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded bg-emerald-100 inline-block" /> Schwach (0.0 - 0.3)</span>
              <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded bg-amber-50 inline-block" /> Moderat (0.3 - 0.7)</span>
              <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded bg-amber-400 inline-block" /> Hohes Cluster (0.7 - 0.85)</span>
              <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded bg-red-500 inline-block" /> Kritisches Cluster (≥ 0.85)</span>
            </div>
          </div>
        )}

        {/* Market Breadth & Internals Drawer */}
        {showBreadth && breadthData && (
          <div className="rounded-2xl border border-indigo-500/20 bg-indigo-50/40 p-4 space-y-4 animate-in fade-in">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[11px] font-extrabold uppercase tracking-[0.2em] text-indigo-900">
                  📊 Institutionelle Marktbreite &amp; Internals (/breadth)
                </div>
                <div className="text-xs text-slate-500">
                  Übergeordnete Gesundheit der 18 Watchlist-Titel: Moving Average Durchdringung, A/D Ratio &amp; Composite Score.
                </div>
              </div>
              <button
                onClick={() => setShowBreadth(false)}
                className="text-xs font-bold text-slate-500 hover:text-slate-800"
              >
                Schließen ✕
              </button>
            </div>

            {/* Top Score Banner */}
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-indigo-500/20 bg-white p-3.5 shadow-sm">
              <div className="flex items-center gap-3">
                <span className="text-2xl">
                  {breadthData.composite_score >= 70 ? "🟢" : breadthData.composite_score <= 40 ? "🔴" : "⚪"}
                </span>
                <div>
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                    Composite Market Breadth Score
                  </div>
                  <div className="text-base font-black text-slate-900">
                    {breadthData.status_badge || `${breadthData.composite_score}/100`}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="rounded-xl border border-black/5 bg-slate-50 px-3 py-1.5 text-center">
                  <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">Regime</div>
                  <div className="text-xs font-black text-indigo-950">{breadthData.regime}</div>
                </div>
                <div className="rounded-xl border border-black/5 bg-slate-50 px-3 py-1.5 text-center">
                  <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">A/D Ratio</div>
                  <div className="text-xs font-black text-slate-900">
                    {breadthData.advancing_count} 🟢 / {breadthData.declining_count} 🔴 ({breadthData.ad_ratio?.toFixed(2)})
                  </div>
                </div>
              </div>
            </div>

            {/* Metrics 4-Grid */}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-xl border border-black/5 bg-white p-3 text-center">
                <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                  % &gt; 20 EMA (Kurzfristig)
                </div>
                <div className="text-xl font-black text-slate-900">
                  {breadthData.pct_above_20_ema?.toFixed(1)}%
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">
                  {breadthData.pct_above_20_ema >= 60 ? "Starkes Momentum" : breadthData.pct_above_20_ema <= 40 ? "Kurzfristige Schwäche" : "Neutraler Drift"}
                </div>
              </div>

              <div className="rounded-xl border border-black/5 bg-white p-3 text-center">
                <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                  % &gt; 50 SMA (Mittelfristig)
                </div>
                <div className="text-xl font-black text-slate-900">
                  {breadthData.pct_above_50_sma?.toFixed(1)}%
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">
                  {breadthData.pct_above_50_sma >= 60 ? "Gesunder Swing-Trend" : "Verteilungsphase"}
                </div>
              </div>

              <div className="rounded-xl border border-black/5 bg-white p-3 text-center">
                <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                  % &gt; 200 SMA (Strukturell)
                </div>
                <div className="text-xl font-black text-slate-900">
                  {breadthData.pct_above_200_sma?.toFixed(1)}%
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">
                  {breadthData.pct_above_200_sma >= 60 ? "Institutioneller Bullenmarkt" : "Bärenmarkt-Gefahr"}
                </div>
              </div>

              <div className="rounded-xl border border-black/5 bg-white p-3 text-center">
                <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                  Ø 52W-High / Low Abstand
                </div>
                <div className="text-sm font-black text-slate-900 mt-1">
                  Hoch: <span className="text-red-700">{breadthData.avg_distance_to_52w_high_pct}%</span> | Tief: <span className="text-emerald-700">+{breadthData.avg_distance_to_52w_low_pct}%</span>
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">
                  {breadthData.scanned_count} Titel synchronisiert
                </div>
              </div>
            </div>

            {/* Constituents Table */}
            {breadthData.constituents?.length ? (
              <div className="overflow-x-auto max-h-64 border border-black/5 rounded-xl bg-white">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-slate-100 border-b border-black/5 text-[10px] uppercase font-extrabold text-slate-600">
                      <th className="p-2">Ticker</th>
                      <th className="p-2 text-right">Kurs</th>
                      <th className="p-2 text-right">Änderung</th>
                      <th className="p-2 text-center">&gt; 20 EMA</th>
                      <th className="p-2 text-center">&gt; 50 SMA</th>
                      <th className="p-2 text-center">&gt; 200 SMA</th>
                      <th className="p-2 text-right">Abstand 52W High</th>
                      <th className="p-2 text-center">Aktion</th>
                    </tr>
                  </thead>
                  <tbody>
                    {breadthData.constituents.map((c: any) => (
                      <tr key={c.ticker} className="border-b border-black/5 hover:bg-slate-50">
                        <td className="p-2 font-black text-slate-900">{c.ticker}</td>
                        <td className="p-2 text-right font-semibold">{c.price?.toFixed(2)}</td>
                        <td className={`p-2 text-right font-black ${c.change_pct >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                          {c.change_pct >= 0 ? `+${c.change_pct}%` : `${c.change_pct}%`}
                        </td>
                        <td className="p-2 text-center font-bold">
                          {c.above_20_ema ? "🟢" : "🔴"}
                        </td>
                        <td className="p-2 text-center font-bold">
                          {c.above_50_sma ? "🟢" : "🔴"}
                        </td>
                        <td className="p-2 text-center font-bold">
                          {c.above_200_sma ? "🟢" : "🔴"}
                        </td>
                        <td className="p-2 text-right text-[11px] text-slate-600">
                          {c.distance_52w_high_pct}%
                        </td>
                        <td className="p-2 text-center">
                          <button
                            onClick={() => {
                              setSelectedRadarTicker(c.ticker);
                              setShowBreadth(false);
                            }}
                            className="rounded px-2 py-0.5 text-[10px] font-bold bg-indigo-500/10 text-indigo-900 hover:bg-indigo-500/20"
                          >
                            Radar
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        )}

        {/* Loading state */}
        {radarLoading && (
          <div className="flex items-center justify-center p-12 text-slate-500 gap-3">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-[var(--accent)] border-t-transparent" />
            <span className="text-sm font-bold">Lade 360°-Check &amp; Struktur-Stops für {selectedRadarTicker}...</span>
          </div>
        )}

        {/* Error state */}
        {!radarLoading && radarError && (
          <div className="rounded-2xl border border-red-500/20 bg-red-500/10 p-4 text-center text-sm font-bold text-red-700">
            {radarError}
            <button
              onClick={() => loadRadar(selectedRadarTicker)}
              className="ml-3 underline hover:text-red-900"
            >
              Erneut versuchen
            </button>
          </div>
        )}

        {/* Loaded Radar Content */}
        {!radarLoading && !radarError && radarData && (
          <div className="space-y-4">
            {/* Header info bar */}
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-black/8 bg-white p-4">
              <div className="flex items-center gap-3">
                <span className="text-3xl">{getTickerBadge(selectedRadarTicker).flag}</span>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-2xl font-black text-slate-900">{selectedRadarTicker}</span>
                    <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-bold text-slate-600">
                      {radarData.check?.currency || "EUR"}
                    </span>
                  </div>
                  <div className="text-xs text-slate-500">
                    Aktueller Kurs: <b className="text-slate-900 text-sm">{radarData.check?.currency_symbol || "€"}{radarData.check?.spot?.toFixed(2)}</b>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-center">
                  <div className="text-[9px] font-extrabold uppercase tracking-[0.16em] text-emerald-800">
                    Confluence Score
                  </div>
                  <div className="text-lg font-black text-emerald-950">
                    {radarData.check?.confluence_score || 50}/100
                  </div>
                </div>

                <div className="rounded-xl border border-[var(--accent)]/20 bg-[var(--accent)]/10 px-3 py-2 text-center">
                  <div className="text-[9px] font-extrabold uppercase tracking-[0.16em] text-[var(--accent-strong)]">
                    Setup Grade
                  </div>
                  <div className="text-lg font-black text-slate-900">
                    {radarData.check?.grade_badge || "Grade A"}
                  </div>
                </div>
              </div>
            </div>

            {/* Two Column Grid: 360° Check vs Structural Stops */}
            <div className="grid gap-4 lg:grid-cols-2">
              {/* Card 1: 360° Institutional Check */}
              <div className="rounded-2xl border border-black/8 bg-white p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.2em] text-slate-600">
                    🔍 360° Institutional Check (/check)
                  </div>
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600">
                    6-Faktor-Matrix
                  </span>
                </div>

                <div className="space-y-3">
                  {/* Volume Profile */}
                  <div className="rounded-xl border border-black/5 bg-slate-50 p-3">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                      1. Volume Profile (70% Value Area)
                    </div>
                    <div className="mt-1 text-xs font-black text-slate-900">
                      {radarData.check?.volume_profile?.location_label || "Inside Value Area"}
                    </div>
                    <div className="mt-1 flex items-center gap-3 text-[11px] text-slate-600">
                      <span>POC: <b>{radarData.check?.currency_symbol}{radarData.check?.volume_profile?.poc?.toFixed(2)}</b></span>
                      <span>VAH: <b>{radarData.check?.currency_symbol}{radarData.check?.volume_profile?.vah?.toFixed(2)}</b></span>
                      <span>VAL: <b>{radarData.check?.currency_symbol}{radarData.check?.volume_profile?.val?.toFixed(2)}</b></span>
                    </div>
                  </div>

                  {/* Options GEX */}
                  <div className="rounded-xl border border-black/5 bg-slate-50 p-3">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                      2. Market Maker Options Gamma (GEX)
                    </div>
                    <div className="mt-1 text-xs font-black text-slate-900">
                      {radarData.check?.options_gex?.regime === "positive_gamma"
                        ? "🟢 Positives Gamma (Dämpfend / Kursstabilisierend)"
                        : radarData.check?.options_gex?.regime === "negative_gamma"
                        ? "⚡ Negatives Gamma (Hohe Richtungsdynamik)"
                        : "⚪ Reiner Aktienhandel (keine US-Optionen)"}
                    </div>
                    {radarData.check?.options_gex?.put_wall ? (
                      <div className="mt-1 flex items-center gap-3 text-[11px] text-slate-600">
                        <span>Put Wall: <b>{radarData.check?.currency_symbol}{radarData.check?.options_gex?.put_wall?.toFixed(2)}</b></span>
                        <span>Call Wall: <b>{radarData.check?.currency_symbol}{radarData.check?.options_gex?.call_wall?.toFixed(2)}</b></span>
                      </div>
                    ) : null}
                  </div>

                  {/* Relative Strength & AVWAP */}
                  <div className="grid gap-2 sm:grid-cols-2">
                    <div className="rounded-xl border border-black/5 bg-slate-50 p-3">
                      <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                        3. Relative Stärke (vs SPY)
                      </div>
                      <div className="mt-1 text-xs font-black text-slate-900">
                        {radarData.check?.relative_strength?.bias === "OUTPERFORMER"
                          ? `🟢 Outperformer (+${radarData.check?.relative_strength?.mansfield_rs?.toFixed(1)}%)`
                          : `🔴 Underperformer (${radarData.check?.relative_strength?.mansfield_rs?.toFixed(1)}%)`}
                      </div>
                    </div>

                    <div className="rounded-xl border border-black/5 bg-slate-50 p-3">
                      <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                        4. Institutional AVWAP
                      </div>
                      <div className="mt-1 text-xs font-black text-slate-900">
                        {radarData.check?.anchored_vwap?.bias?.includes("BULLISH")
                          ? "🟢 Bullish (> YTD VWAP)"
                          : "🔴 Bearish (< YTD VWAP)"}
                      </div>
                      {radarData.check?.anchored_vwap?.ytd ? (
                        <div className="mt-0.5 text-[10px] text-slate-500">
                          YTD: {radarData.check?.currency_symbol}{radarData.check?.anchored_vwap?.ytd?.toFixed(2)}
                        </div>
                      ) : null}
                    </div>
                  </div>

                  {/* Whale Flow & Earnings Shield */}
                  <div className="grid gap-2 sm:grid-cols-2">
                    <div className="rounded-xl border border-black/5 bg-slate-50 p-3">
                      <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                        5. Whale &amp; Dark Pool Flow
                      </div>
                      <div className="mt-1 text-xs font-black text-slate-900">
                        🐋 {radarData.check?.whale_flow?.bias || "Neutral"}
                      </div>
                    </div>

                    <div className="rounded-xl border border-black/5 bg-slate-50 p-3">
                      <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                        6. Earnings Shield
                      </div>
                      <div className="mt-1 text-xs font-black text-slate-900">
                        {radarData.check?.earnings_shield?.safe
                          ? "🟢 Safe (Keine Termine &lt;5 Tage)"
                          : `⚠️ ${radarData.check?.earnings_shield?.warning || "Earnings anstehend!"}`}
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Card 2: Multi-Struktureller Stop-Rechner */}
              <div className="rounded-2xl border border-black/8 bg-white p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.2em] text-slate-600">
                    🛡️ Multi-Struktur Stops (/stop)
                  </div>
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600">
                    4 Schutz-Ebenen
                  </span>
                </div>

                <div className="space-y-2.5">
                  {/* Stop 1: Invalidation */}
                  <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-3">
                    <div className="flex items-center justify-between">
                      <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-red-700">
                        1. Empfohlener Edge Stop (Invalidation)
                      </div>
                      <span className="rounded bg-red-500/10 px-2 py-0.5 text-[10px] font-black text-red-700">
                        -{radarData.stops?.invalidation_stop?.distance_pct}%
                      </span>
                    </div>
                    <div className="mt-1 text-base font-black text-red-950">
                      {radarData.stops?.currency_symbol}{radarData.stops?.invalidation_stop?.price?.toFixed(2)}
                    </div>
                    <div className="mt-0.5 text-[11px] text-slate-600">
                      {radarData.stops?.invalidation_stop?.description}
                    </div>
                  </div>

                  {/* Stop 2: Volume Profile Stop */}
                  <div className="rounded-xl border border-black/5 bg-slate-50 p-3">
                    <div className="flex items-center justify-between">
                      <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                        2. Volume Profile Stop (Unterhalb VAL)
                      </div>
                      <span className="rounded bg-slate-200 px-2 py-0.5 text-[10px] font-black text-slate-700">
                        -{radarData.stops?.volume_profile_stop?.distance_pct}%
                      </span>
                    </div>
                    <div className="mt-1 text-base font-black text-slate-900">
                      {radarData.stops?.currency_symbol}{radarData.stops?.volume_profile_stop?.price?.toFixed(2)}
                    </div>
                    <div className="mt-0.5 text-[11px] text-slate-600">
                      {radarData.stops?.volume_profile_stop?.description}
                    </div>
                  </div>

                  {/* Stop 3: Put Wall Stop (if available) */}
                  {radarData.stops?.options_put_wall_stop ? (
                    <div className="rounded-xl border border-black/5 bg-slate-50 p-3">
                      <div className="flex items-center justify-between">
                        <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                          3. Options Put Wall Stop (MM Support Boden)
                        </div>
                        <span className="rounded bg-slate-200 px-2 py-0.5 text-[10px] font-black text-slate-700">
                          -{radarData.stops?.options_put_wall_stop?.distance_pct}%
                        </span>
                      </div>
                      <div className="mt-1 text-base font-black text-slate-900">
                        {radarData.stops?.currency_symbol}{radarData.stops?.options_put_wall_stop?.price?.toFixed(2)}
                      </div>
                      <div className="mt-0.5 text-[11px] text-slate-600">
                        {radarData.stops?.options_put_wall_stop?.description}
                      </div>
                    </div>
                  ) : null}

                  {/* Stop 4: AVWAP Stop (if available) */}
                  {radarData.stops?.ytd_avwap_stop ? (
                    <div className="rounded-xl border border-black/5 bg-slate-50 p-3">
                      <div className="flex items-center justify-between">
                        <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                          4. YTD AVWAP Stop (Fonds-Benchmark)
                        </div>
                        <span className="rounded bg-slate-200 px-2 py-0.5 text-[10px] font-black text-slate-700">
                          -{radarData.stops?.ytd_avwap_stop?.distance_pct}%
                        </span>
                      </div>
                      <div className="mt-1 text-base font-black text-slate-900">
                        {radarData.stops?.currency_symbol}{radarData.stops?.ytd_avwap_stop?.price?.toFixed(2)}
                      </div>
                      <div className="mt-0.5 text-[11px] text-slate-600">
                        {radarData.stops?.ytd_avwap_stop?.description}
                      </div>
                    </div>
                  ) : null}

                  {/* Trailing Breakeven Level */}
                  <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3">
                    <div className="flex items-center justify-between">
                      <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-emerald-800">
                        🛡️ Trailing Stop Breakeven Level
                      </div>
                      <span className="rounded bg-emerald-500/10 px-2 py-0.5 text-[10px] font-black text-emerald-800">
                        0.0% Risiko
                      </span>
                    </div>
                    <div className="mt-1 text-base font-black text-emerald-950">
                      {radarData.stops?.currency_symbol}{radarData.stops?.breakeven_stop?.toFixed(2)}
                    </div>
                    <div className="mt-0.5 text-[11px] text-slate-600">
                      Wird automatisch risikofrei nachgezogen, sobald Ziel 1 (2.0R) erreicht ist.
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Pre-Flight Risk & Portfolio Heat Card */}
            {radarData.preflight ? (
              <div className={`rounded-2xl border p-4 space-y-3 ${
                radarData.preflight.status === "CRITICAL"
                  ? "border-red-500/30 bg-red-500/10"
                  : radarData.preflight.status === "WARNING"
                  ? "border-amber-500/30 bg-amber-500/10"
                  : "border-emerald-500/20 bg-emerald-500/5"
              }`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-lg">
                      {radarData.preflight.status === "CRITICAL" ? "🔴" : radarData.preflight.status === "WARNING" ? "⚠️" : "🟢"}
                    </span>
                    <div>
                      <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                        Pre-Flight Risikocheck &amp; Portfolio Heat Shield
                      </div>
                      <div className="text-sm font-black text-slate-900">
                        {radarData.preflight.status === "CRITICAL"
                          ? "Trade abgelehnt: Portfolio Heat Limit überschritten"
                          : radarData.preflight.status === "WARNING"
                          ? "Erhöhtes Cluster-Risiko: Stark korrelierende Positionen aktiv"
                          : "Freigabe erteilt (Clear): Portfolio Heat & Korrelation im grünen Bereich"}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <div className="rounded-xl border border-black/5 bg-white px-3 py-1.5 text-center">
                      <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                        Heat Status
                      </div>
                      <div className="text-xs font-black text-slate-900">
                        {radarData.preflight.current_heat_pct?.toFixed(2)}% ➔ {radarData.preflight.projected_heat_pct?.toFixed(2)}%
                      </div>
                    </div>
                    <div className="rounded-xl border border-black/5 bg-white px-3 py-1.5 text-center">
                      <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                        Max Heat
                      </div>
                      <div className="text-xs font-black text-slate-900">
                        {radarData.preflight.max_heat_pct?.toFixed(2)}%
                      </div>
                    </div>
                  </div>
                </div>

                {radarData.preflight.correlated_positions?.length ? (
                  <div className="rounded-xl border border-black/5 bg-white p-3 space-y-1.5">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-amber-800">
                      🔗 Stark korrelierende aktive Positionen (Klumpenrisiko):
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {radarData.preflight.correlated_positions.map((cp: any, idx: number) => (
                        <div key={idx} className="flex items-center justify-between text-xs rounded-lg bg-amber-500/10 px-2.5 py-1.5">
                          <span className="font-extrabold text-amber-950">{cp.open_ticker}</span>
                          <span className="font-black text-amber-900">r = {cp.correlation?.toFixed(2)} ({cp.cluster_risk})</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}

                {radarData.preflight.warnings?.length ? (
                  <div className="space-y-1 text-xs font-semibold text-slate-700">
                    {radarData.preflight.warnings.map((w: string, idx: number) => (
                      <div key={idx} className="flex items-center gap-1.5">
                        <span>•</span>
                        <span>{w}</span>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}

            {/* Intraday Opening Range Breakout (ORB) Card */}
            {tickerOrbData ? (
              <div className="rounded-2xl border border-black/8 bg-white p-4 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xl">⚡</span>
                    <div>
                      <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                        Intraday Opening Range Breakout (30m Session Range)
                      </div>
                      <div className="text-sm font-black text-slate-900 flex items-center gap-2">
                        <span>{tickerOrbData.ticker}</span>
                        <span className={`rounded-md px-2 py-0.5 text-xs font-black ${
                          tickerOrbData.state === "BULLISH_BREAKOUT"
                            ? "bg-emerald-500 text-white animate-pulse"
                            : tickerOrbData.state === "BEARISH_BREAKDOWN"
                            ? "bg-red-500 text-white animate-pulse"
                            : "bg-slate-100 text-slate-700"
                        }`}>
                          {tickerOrbData.badge}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <div className="rounded-xl border border-black/5 bg-slate-50 px-3 py-1.5 text-center">
                      <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                        Relatives Volumen
                      </div>
                      <div className="text-xs font-black text-slate-900">
                        {tickerOrbData.relative_volume}x {tickerOrbData.volume_confirmed ? "🔥" : "⚪"}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="grid gap-2 sm:grid-cols-4 text-center">
                  <div className="rounded-xl border border-black/5 bg-slate-50 p-2">
                    <div className="text-[9px] font-extrabold uppercase tracking-[0.12em] text-slate-500">ORB High</div>
                    <div className="text-sm font-black text-slate-900">{tickerOrbData.currency_symbol}{tickerOrbData.orb_high?.toFixed(2)}</div>
                  </div>
                  <div className="rounded-xl border border-black/5 bg-slate-50 p-2">
                    <div className="text-[9px] font-extrabold uppercase tracking-[0.12em] text-slate-500">ORB Mid (Stop)</div>
                    <div className="text-sm font-black text-slate-900">{tickerOrbData.currency_symbol}{tickerOrbData.orb_mid?.toFixed(2)}</div>
                  </div>
                  <div className="rounded-xl border border-black/5 bg-slate-50 p-2">
                    <div className="text-[9px] font-extrabold uppercase tracking-[0.12em] text-slate-500">ORB Low</div>
                    <div className="text-sm font-black text-slate-900">{tickerOrbData.currency_symbol}{tickerOrbData.orb_low?.toFixed(2)}</div>
                  </div>
                  <div className="rounded-xl border border-black/5 bg-slate-50 p-2">
                    <div className="text-[9px] font-extrabold uppercase tracking-[0.12em] text-slate-500">Range-Spanne</div>
                    <div className="text-sm font-black text-slate-900">
                      {tickerOrbData.currency_symbol}{tickerOrbData.orb_range?.toFixed(2)} ({tickerOrbData.orb_range_pct}%)
                    </div>
                  </div>
                </div>
              </div>
            ) : null}

            {/* Interactive Position Sizing & Kelly Calculator Card */}
            <div className="rounded-2xl border border-black/8 bg-white p-5 space-y-4 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-xl">🧮</span>
                  <div>
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                      Institutionelle Risikosteuerung &amp; Kelly-Kriterium
                    </div>
                    <div className="text-base font-black text-slate-900">
                      Interaktiver Position Sizing Rechner ({selectedRadarTicker})
                    </div>
                  </div>
                </div>

                {sizingData?.kelly_analysis ? (
                  <span className={`rounded-xl px-3 py-1 text-xs font-black border ${
                    sizingData.kelly_analysis.verdict?.includes("ÜBER")
                      ? "border-amber-500/30 bg-amber-500/10 text-amber-900"
                      : "border-emerald-500/30 bg-emerald-500/10 text-emerald-900"
                  }`}>
                    Half-Kelly: {sizingData.kelly_analysis.half_kelly_pct}% ({sizingData.kelly_analysis.verdict})
                  </span>
                ) : null}
              </div>

              {/* Sliders Grid */}
              <div className="grid gap-4 md:grid-cols-2 bg-slate-50 p-4 rounded-xl border border-black/5">
                <div>
                  <div className="flex items-center justify-between text-xs font-bold text-slate-700 mb-1">
                    <span>Depotkapital:</span>
                    <span className="font-black text-slate-900">{sizingCapital.toLocaleString("de-DE")} €</span>
                  </div>
                  <input
                    type="range"
                    min="10000"
                    max="250000"
                    step="5000"
                    value={sizingCapital}
                    onChange={(e) => setSizingCapital(Number(e.target.value))}
                    className="w-full accent-[var(--accent)] cursor-pointer"
                  />
                  <div className="flex justify-between text-[9px] text-slate-400 mt-0.5">
                    <span>10.000 €</span>
                    <span>100.000 €</span>
                    <span>250.000 €</span>
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between text-xs font-bold text-slate-700 mb-1">
                    <span>Risiko pro Trade:</span>
                    <span className="font-black text-[var(--accent-strong)]">{sizingRiskPct.toFixed(2)}%</span>
                  </div>
                  <input
                    type="range"
                    min="0.25"
                    max="2.50"
                    step="0.05"
                    value={sizingRiskPct}
                    onChange={(e) => setSizingRiskPct(Number(e.target.value))}
                    className="w-full accent-[var(--accent)] cursor-pointer"
                  />
                  <div className="flex justify-between text-[9px] text-slate-400 mt-0.5">
                    <span>0.25% (Sehr konservativ)</span>
                    <span>1.0% (Standard)</span>
                    <span>2.5% (Max Limit)</span>
                  </div>
                </div>
              </div>

              {/* Sizing Results */}
              {sizingData && (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <div className="rounded-xl border border-black/5 bg-slate-50 p-3 text-center">
                    <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                      Empfohlene Stückzahl
                    </div>
                    <div className="text-xl font-black text-slate-900">
                      {sizingData.recommended_shares} Stk.
                    </div>
                    <div className="text-[10px] text-slate-500 mt-0.5">
                      Volumen: {sizingData.currency_symbol}{sizingData.position_value?.toLocaleString("de-DE")} ({sizingData.capital_allocation_pct}% Depot)
                    </div>
                  </div>

                  <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-3 text-center">
                    <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-red-700">
                      Maximales Risiko (Stop-Out)
                    </div>
                    <div className="text-xl font-black text-red-950">
                      -{sizingData.currency_symbol}{sizingData.max_risk_amount?.toFixed(2)}
                    </div>
                    <div className="text-[10px] text-red-700 mt-0.5">
                      -{sizingData.actual_risk_pct}% des Depotkapitals
                    </div>
                  </div>

                  <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3 text-center">
                    <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-emerald-800">
                      Ziel 1 Netto-Ertrag (2.0R)
                    </div>
                    <div className="text-xl font-black text-emerald-950">
                      +{sizingData.currency_symbol}{sizingData.target_1_profit_net?.toFixed(2)}
                    </div>
                    <div className="text-[10px] text-slate-500 mt-0.5">
                      Brutto: +{sizingData.currency_symbol}{sizingData.target_1_profit_gross?.toFixed(2)}
                    </div>
                  </div>

                  <div className="rounded-xl border border-black/5 bg-slate-50 p-3 text-center">
                    <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                      Reibung (Spread &amp; Slippage)
                    </div>
                    <div className="text-xl font-black text-slate-700">
                      -{sizingData.currency_symbol}{sizingData.friction_cost_est?.toFixed(2)}
                    </div>
                    <div className="text-[10px] text-slate-500 mt-0.5">
                      Spread {sizingData.friction_breakdown?.spread_pct}% + Slip {sizingData.friction_breakdown?.slippage_pct}%
                    </div>
                  </div>
                </div>
              )}

              {/* Direct Booking with Sizing */}
              {sizingData && (
                <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-black/5">
                  <div className="text-xs text-slate-500">
                    💡 <i>Berechnet mit Stop @ {sizingData.currency_symbol}{sizingData.stop_price?.toFixed(2)} und Ziel 1 @ {sizingData.currency_symbol}{sizingData.target_1?.toFixed(2)}.</i>
                  </div>
                  <button
                    onClick={() => handleOpenPaperTrade(selectedRadarTicker, sizingData.recommended_shares)}
                    disabled={actionLoading}
                    className="rounded-xl bg-emerald-700 px-4 py-2 text-xs font-black uppercase tracking-[0.16em] text-white shadow-sm transition-colors hover:bg-emerald-800 disabled:opacity-50"
                  >
                    📝 Mit dieser Stückzahl buchen ({sizingData.recommended_shares} Stk.)
                  </button>
                </div>
              )}
            </div>

            {/* Action Bar */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => handleOpenPaperTrade(selectedRadarTicker)}
                  disabled={actionLoading}
                  className="rounded-xl bg-emerald-600 px-5 py-2.5 text-xs font-black uppercase tracking-[0.16em] text-white shadow-sm transition-colors hover:bg-emerald-700 disabled:opacity-50"
                >
                  📝 In Paper Trader buchen
                </button>
                <button
                  onClick={() => handleScaleOut(selectedRadarTicker)}
                  disabled={actionLoading}
                  className="rounded-xl border border-amber-500/30 bg-amber-500/15 px-4 py-2.5 text-xs font-black uppercase tracking-[0.16em] text-amber-950 shadow-sm transition-colors hover:bg-amber-500/25 disabled:opacity-50"
                  title="50% Teilverkauf buchen & Stop automatisch risikofrei auf Break-Even ziehen"
                >
                  ✂️ 50% Scale-Out (BE Stop)
                </button>
                <button
                  onClick={() => handleSendTelegram(selectedRadarTicker)}
                  disabled={actionLoading}
                  className="rounded-xl bg-[var(--accent)] px-5 py-2.5 text-xs font-black uppercase tracking-[0.16em] text-white shadow-sm transition-colors hover:bg-[var(--accent-strong)] disabled:opacity-50"
                >
                  📲 An Telegram senden
                </button>
                <button
                  onClick={() => onAnalyze(selectedRadarTicker)}
                  className="rounded-xl border border-black/8 bg-white px-5 py-2.5 text-xs font-black uppercase tracking-[0.16em] text-slate-800 transition-colors hover:bg-slate-50"
                >
                  🚀 Vollständige Chart-Analyse
                </button>
              </div>

              {tradeActionMessage ? (
                <div className="text-xs font-extrabold text-slate-800 bg-slate-100 px-3 py-1.5 rounded-lg border border-black/5 animate-in fade-in">
                  {tradeActionMessage}
                </div>
              ) : null}
            </div>
          </div>
        )}
      </section>

      {!!tickerSignals.length && (
        <section className="space-y-4">
          <div className="text-[11px] font-extrabold uppercase tracking-[0.24em] text-slate-500">
            Form 4 Radar
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            {tickerSignals.map((signal) => {
              const badge = getTickerBadge(signal.ticker);
              return (
              <div key={signal.ticker} className="surface-panel rounded-[1.8rem] p-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xl" title={badge.region}>{badge.flag}</span>
                      <div className="text-2xl font-black text-slate-900">{signal.ticker}</div>
                      <span className="rounded-md border border-black/5 bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600">
                        {badge.currency}
                      </span>
                    </div>
                    <div className="text-sm text-slate-500">{signal.title}</div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => onAnalyze(signal.ticker)}
                      className="rounded-xl bg-[var(--accent)] px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-white transition-colors hover:bg-[var(--accent-strong)]"
                    >
                      Analyze
                    </button>
                    <button
                      onClick={() => {
                        setSelectedRadarTicker(signal.ticker);
                        const el = document.getElementById("institutional-radar-section");
                        if (el) el.scrollIntoView({ behavior: "smooth" });
                      }}
                      className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-emerald-800 transition-colors hover:bg-emerald-500/20"
                    >
                      360° &amp; Stops
                    </button>
                    <button
                      onClick={() => startEditing({ kind: "ticker", value: signal.ticker })}
                      className="rounded-xl border border-black/8 bg-white px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-700"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => removeItem("ticker", signal.ticker)}
                      className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-red-700"
                    >
                      Remove
                    </button>
                  </div>
                </div>

                {signal.error ? (
                  <div className="mt-4 text-sm text-red-700">{signal.error}</div>
                ) : signal.events.length ? (
                  <div className="mt-4 space-y-3">
                    {signal.events.slice(0, 4).map((event, index) => (
                      <a
                        key={`${signal.ticker}-${index}`}
                        href={event.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="block rounded-2xl border border-black/8 bg-white/80 p-4"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="text-sm font-bold text-slate-900">
                            {event.owner_name}
                          </div>
                          <div
                            className={`rounded-full px-2 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] ${
                              event.action === "buy"
                                ? "bg-emerald-500/10 text-emerald-700"
                                : "bg-red-500/10 text-red-700"
                            }`}
                          >
                            {event.action}
                          </div>
                        </div>
                        <div className="mt-1 text-xs text-slate-500">
                          {formatLine([event.owner_title || "Insider", event.trade_date, `filed ${event.filed_date}`])}
                        </div>
                        <div className="mt-2 text-sm text-slate-700">
                          {formatLine([
                            event.shares?.toLocaleString("de-DE")
                              ? `${event.shares?.toLocaleString("de-DE")} Aktien`
                              : null,
                            event.value_label,
                            typeof event.delay_days === "number" ? `delay ${event.delay_days}d` : null,
                          ])}
                        </div>
                      </a>
                    ))}
                  </div>
                ) : (
                  <div className="mt-4 text-sm text-slate-500">
                    Keine juengsten Form-4-Signale gefunden.
                  </div>
                )}
              </div>
            );
          })}
          </div>
        </section>
      )}

      {!!politicianSignals.length && (
        <section className="space-y-4">
          <div className="text-[11px] font-extrabold uppercase tracking-[0.24em] text-slate-500">
            House PTR Watch
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            {politicianSignals.map((signal) => (
              <div key={signal.name} className="surface-panel rounded-[1.8rem] p-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="text-2xl font-black text-slate-900">{signal.name}</div>
                    <div className="mt-1 text-sm text-slate-500">
                      Offizielle House PTR-Suche
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => startEditing({ kind: "politician", value: signal.name })}
                      className="rounded-xl border border-black/8 bg-white px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-700"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => removeItem("politician", signal.name)}
                      className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-red-700"
                    >
                      Remove
                    </button>
                  </div>
                </div>

                <div className="mt-4 grid gap-3 sm:grid-cols-3">
                  <div className="rounded-[1.2rem] border border-black/8 bg-white/75 p-3">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                      Trades
                    </div>
                    <div className="mt-1 text-lg font-black text-slate-900">
                      {signal.summary?.trade_count ?? signal.trades.length}
                    </div>
                  </div>
                  <div className="rounded-[1.2rem] border border-black/8 bg-white/75 p-3">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                      Buys / Sells
                    </div>
                    <div className="mt-1 text-lg font-black text-slate-900">
                      {signal.summary?.buy_count ?? 0} / {signal.summary?.sell_count ?? 0}
                    </div>
                  </div>
                  <div className="rounded-[1.2rem] border border-black/8 bg-white/75 p-3">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                      Avg Delay
                    </div>
                    <div className="mt-1 text-lg font-black text-slate-900">
                      {signal.summary?.avg_delay_days != null ? `${signal.summary.avg_delay_days}d` : "N/A"}
                    </div>
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                  <span>{signal.summary?.report_count ?? signal.reports?.length ?? 0} reports</span>
                  <span>latest {signal.summary?.latest_trade_date || "N/A"}</span>
                  <span className="rounded-full border border-black/8 bg-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                    official house ptr
                  </span>
                </div>

                {signal.playbook ? (
                  <div className="mt-4 rounded-[1.2rem] border border-black/8 bg-white/75 p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                        Congress playbook
                      </span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${
                          signal.playbook.setup?.includes("long")
                            ? "bg-emerald-500/10 text-emerald-700"
                            : signal.playbook.setup?.includes("short")
                              ? "bg-red-500/10 text-red-700"
                              : "bg-amber-500/10 text-amber-700"
                        }`}
                      >
                        {signal.playbook.setup}
                      </span>
                      <span className="rounded-full border border-black/8 bg-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                        leverage {signal.playbook.leverage}
                      </span>
                      {signal.playbook.signal_grade ? (
                        <span className="rounded-full border border-[var(--accent)]/15 bg-[var(--accent-soft)] px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--accent)]">
                          {signal.playbook.signal_grade.replace(/_/g, " ")}
                        </span>
                      ) : null}
                      {signal.playbook.confidence != null ? (
                        <span className="rounded-full border border-black/8 bg-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                          {signal.playbook.confidence}% conf
                        </span>
                      ) : null}
                    </div>
                    <div className="mt-3 text-sm font-bold text-slate-900">{signal.playbook.thesis}</div>
                    <div className="mt-2 text-sm text-slate-600">{signal.playbook.trigger}</div>
                    {signal.playbook.next_action ? (
                      <div className="mt-3 rounded-xl border border-[var(--accent)]/12 bg-[var(--accent-soft)] p-3 text-xs font-semibold text-[var(--accent)]">
                        Next: {signal.playbook.next_action}
                      </div>
                    ) : null}
                    <div className="mt-3 flex flex-wrap gap-2">
                      {signal.playbook.estimated_exposure_label ? (
                        <span className="rounded-full border border-black/8 bg-white px-2 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                          exposure {signal.playbook.estimated_exposure_label}
                        </span>
                      ) : null}
                      {(signal.playbook.top_tickers || []).slice(0, 4).map((ticker) => (
                        <button
                          key={ticker}
                          type="button"
                          onClick={() => onAnalyze(ticker)}
                          className="rounded-full border border-black/8 bg-white px-2 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-700"
                        >
                          {ticker}
                        </button>
                      ))}
                    </div>
                    <div className="mt-3 rounded-xl border border-black/8 bg-white p-3 text-xs text-slate-600">
                      {signal.playbook.copy_text}
                    </div>
                    {signal.playbook.compliance_note ? (
                      <div className="mt-2 text-[11px] leading-5 text-slate-500">
                        {signal.playbook.compliance_note}
                      </div>
                    ) : null}
                  </div>
                ) : signal.trades.length ? (
                  <div className="mt-4 rounded-[1.2rem] border border-black/8 bg-white/75 p-4">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                      Congress playbook
                    </div>
                    <div className="mt-3 text-sm font-bold text-slate-900">
                      Noch kein klares Copy-Setup. Nutze den Feed als Themen- und Delay-Hinweis.
                    </div>
                    <div className="mt-2 text-sm text-slate-600">
                      Pruefe Trade-Datum, Delay, Asset und ob die Richtung technisch ueberhaupt noch bestaetigt wird.
                    </div>
                  </div>
                ) : (
                  <div className="mt-4 rounded-[1.2rem] border border-dashed border-black/8 bg-white/65 p-4">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                      Congress playbook
                    </div>
                    <div className="mt-3 text-sm text-slate-500">
                      Noch keine auswertbaren PTR-Trades im aktuellen Suchfenster.
                    </div>
                  </div>
                )}

                {signal.error ? (
                  <div className="mt-4 text-sm text-red-700">{signal.error}</div>
                ) : signal.trades.length ? (
                  <div className="mt-4 space-y-3">
                    {signal.trades.slice(0, 5).map((trade, index) => (
                      <div
                        key={`${signal.name}-${index}`}
                        className="rounded-2xl border border-black/8 bg-white/80 p-4"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="text-sm font-bold text-slate-900">
                            {trade.ticker || trade.asset}
                          </div>
                          <div
                            className={`rounded-full px-2 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] ${
                              trade.action === "buy"
                                ? "bg-emerald-500/10 text-emerald-700"
                                : "bg-red-500/10 text-red-700"
                            }`}
                          >
                            {trade.action}
                          </div>
                        </div>
                        <div className="mt-1 text-xs text-slate-500">
                          {formatLine([
                            trade.trade_date,
                            `filed ${trade.notification_date}`,
                            trade.delay_days != null ? `delay ${trade.delay_days}d` : null,
                          ])}
                        </div>
                        <div className="mt-2 text-sm text-slate-700">{trade.amount_range}</div>
                        <div className="mt-2 flex items-center gap-3">
                          {trade.ticker && (
                            <button
                              onClick={() => onAnalyze(trade.ticker!)}
                              className="rounded-xl bg-[var(--accent)] px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-white transition-colors hover:bg-[var(--accent-strong)]"
                            >
                              Analyze
                            </button>
                          )}
                          {trade.source_url && (
                            <a
                              href={trade.source_url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-[11px] font-bold uppercase tracking-[0.16em] text-slate-600"
                            >
                              Filing oeffnen
                            </a>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-4 text-sm text-slate-500">
                    Keine PTR-Trades im aktuellen Suchfenster gefunden.
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
