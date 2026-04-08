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

const initialForm = { kind: "ticker", value: "" };
const quickIdeas = [
  { kind: "ticker", value: "AAPL" },
  { kind: "ticker", value: "NVDA" },
  { kind: "ticker", value: "AMZN" },
  { kind: "politician", value: "Nancy Pelosi" },
  { kind: "politician", value: "Scott Peters" },
];

export default function SignalWatchlistPanel({
  data,
  onAnalyze,
  onRefresh,
}: SignalWatchlistPanelProps) {
  const [form, setForm] = useState(initialForm);
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<string>("");
  const [notificationStatus, setNotificationStatus] = useState<any>(null);

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
      await fetch("/api/signals/watchlist/items", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      setForm(initialForm);
      await onRefresh();
      setStatus("Watch item hinzugefuegt.");
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
    } finally {
      setSubmitting(false);
    }
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
              Hinzufuegen
            </button>
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
                Email
              </div>
              <div className="mt-2 text-sm font-black text-slate-900">
                {notificationStatus.email?.configured ? "Configured" : "Not configured"}
              </div>
              <div className="mt-1 text-xs text-slate-500">
                {notificationStatus.email?.to || "No recipient"}
              </div>
            </div>
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
                Bot token + chat id required
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
                EU {notificationStatus.schedule?.europe_open} • US {notificationStatus.schedule?.us_open}
              </div>
            </div>
          </div>
        )}

        <div className="mt-5 flex flex-wrap gap-2">
          {[...groupedItems.ticker, ...groupedItems.politician].map((item) => (
            <button
              key={`${item.kind}:${item.value}`}
              onClick={() => removeItem(item.kind, item.value)}
              className="rounded-full border border-black/8 bg-white px-3 py-2 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-700"
            >
              {item.kind === "ticker" ? "Ticker" : "House"}: {item.value} ×
            </button>
          ))}
        </div>

        {!items.length && (
          <div className="mt-5">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Quick start
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {quickIdeas.map((idea) => (
                <button
                  key={`${idea.kind}:${idea.value}`}
                  onClick={() => setForm(idea)}
                  className="rounded-full border border-black/8 bg-white px-3 py-2 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-700"
                >
                  {idea.kind === "ticker" ? "Ticker" : "House"}: {idea.value}
                </button>
              ))}
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
            {tickerSignals.map((signal) => (
              <div key={signal.ticker} className="surface-panel rounded-[1.8rem] p-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="text-2xl font-black text-slate-900">{signal.ticker}</div>
                    <div className="text-sm text-slate-500">{signal.title}</div>
                  </div>
                  <button
                    onClick={() => onAnalyze(signal.ticker)}
                    className="rounded-xl bg-[var(--accent)] px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-white transition-colors hover:bg-[var(--accent-strong)]"
                  >
                    Analyze
                  </button>
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
                          {event.owner_title || "Insider"} • {event.trade_date} • filed {event.filed_date}
                        </div>
                        <div className="mt-2 text-sm text-slate-700">
                          {event.shares?.toLocaleString("de-DE")} Aktien
                          {event.value_label ? ` • ${event.value_label}` : ""}
                          {typeof event.delay_days === "number"
                            ? ` • delay ${event.delay_days}d`
                            : ""}
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
            ))}
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
                <div className="text-2xl font-black text-slate-900">{signal.name}</div>
                <div className="mt-1 text-sm text-slate-500">
                  Offizielle House PTR-Suche
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
                          {trade.trade_date} • filed {trade.notification_date} • delay {trade.delay_days}d
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
