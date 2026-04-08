import React, { useMemo, useState } from "react";

interface PaperTradingPanelProps {
  data: any;
  onAnalyze: (ticker: string) => void;
  onRefresh?: () => Promise<void>;
}

function StatTile({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string | number;
  tone?: "default" | "good" | "bad";
}) {
  const toneClass =
    tone === "good" ? "text-emerald-700" : tone === "bad" ? "text-red-700" : "text-slate-900";
  return (
    <div className="rounded-[1.3rem] border border-black/8 bg-white/75 p-4">
      <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">{label}</div>
      <div className={`mt-2 text-2xl font-black ${toneClass}`}>{value}</div>
    </div>
  );
}

export default function PaperTradingPanel({ data, onAnalyze, onRefresh }: PaperTradingPanelProps) {
  const [status, setStatus] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [journalDraft, setJournalDraft] = useState<Record<string, { notes: string; exit_reason: string; lessons_learned: string }>>({});

  const stats = data?.stats || {};
  const playbooks = data?.playbooks || [];
  const openTrades = data?.open_trades || [];
  const closedTrades = data?.closed_trades || [];
  const setupPerformance = data?.setup_performance || [];
  const journal = data?.journal || [];
  const rules = data?.rules || {};

  const openPnLTone = useMemo(() => {
    const value = Number(stats.avg_open_pnl_pct || 0);
    return value > 0 ? "good" : value < 0 ? "bad" : "default";
  }, [stats.avg_open_pnl_pct]);

  const realizedTone = useMemo(() => {
    const value = Number(stats.realized_pnl_pct || 0);
    return value > 0 ? "good" : value < 0 ? "bad" : "default";
  }, [stats.realized_pnl_pct]);

  if (!data) return null;

  const openFromPlaybook = async (playbookId: string, direction: string) => {
    setBusyId(playbookId);
    setStatus("");
    try {
      const response = await fetch("/api/trading/paper-trades/from-playbook", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          playbook_id: playbookId,
          direction,
          quantity: 1,
          leverage: 1,
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Opening trade failed.");
      await onRefresh?.();
      setStatus("Paper trade opened.");
    } catch (error: any) {
      setStatus(error?.message || "Opening trade failed.");
    } finally {
      setBusyId(null);
    }
  };

  const closeTrade = async (tradeId: string) => {
    setBusyId(tradeId);
    setStatus("");
    try {
      const draft = journalDraft[tradeId] || { notes: "", exit_reason: "", lessons_learned: "" };
      const response = await fetch(`/api/trading/paper-trades/${tradeId}/close`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Closing trade failed.");
      await onRefresh?.();
      setStatus("Paper trade closed.");
    } catch (error: any) {
      setStatus(error?.message || "Closing trade failed.");
    } finally {
      setBusyId(null);
    }
  };

  const sendDigest = async () => {
    setBusyId("digest");
    setStatus("");
    try {
      const response = await fetch("/api/signals/alerts/a-setup-digest", { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Digest failed.");
      setStatus(payload.message || "A-Setup digest sent.");
    } catch (error: any) {
      setStatus(error?.message || "Digest failed.");
    } finally {
      setBusyId(null);
    }
  };

  const startEditing = (entry: any) => {
    setEditingId(entry.id);
    setJournalDraft((prev) => ({
      ...prev,
      [entry.id]: {
        notes: entry.notes || "",
        exit_reason: entry.exit_reason || "",
        lessons_learned: entry.lessons_learned || "",
      },
    }));
  };

  const saveJournal = async (tradeId: string) => {
    setBusyId(tradeId);
    setStatus("");
    try {
      const response = await fetch(`/api/trading/paper-trades/${tradeId}/journal`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(journalDraft[tradeId] || {}),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Journal save failed.");
      await onRefresh?.();
      setEditingId(null);
      setStatus("Journal updated.");
    } catch (error: any) {
      setStatus(error?.message || "Journal save failed.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="space-y-6">
      <div className="surface-panel rounded-[2.5rem] p-6 sm:p-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Paper Trading
            </div>
            <h2 className="mt-2 text-3xl text-slate-900">Playbooks, demo entries and learning loop</h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
              Jede Idee bekommt ein sauberes Setup mit Richtung, Stop, Target und späterem Ergebnis. So lernst du,
              welche Signaltypen bei Aktien, ETFs und Crypto wirklich tragen.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={sendDigest}
              disabled={busyId === "digest"}
              className="rounded-xl bg-[var(--accent)] px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-white disabled:opacity-50"
            >
              A-Setup digest
            </button>
            <div className="rounded-full border border-black/8 bg-white/75 px-4 py-2 text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
              {stats.total_trades || 0} tracked trades
            </div>
          </div>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <StatTile label="Win Rate" value={`${stats.win_rate || 0}%`} tone={Number(stats.win_rate || 0) >= 50 ? "good" : "default"} />
          <StatTile label="Open PnL" value={`${Number(stats.avg_open_pnl_pct || 0) >= 0 ? "+" : ""}${Number(stats.avg_open_pnl_pct || 0).toFixed(2)}%`} tone={openPnLTone as any} />
          <StatTile label="Realized" value={`${Number(stats.realized_pnl_pct || 0) >= 0 ? "+" : ""}${Number(stats.realized_pnl_pct || 0).toFixed(2)}%`} tone={realizedTone as any} />
          <StatTile label="Long / Short" value={`${stats.long_short_split?.long || 0} / ${stats.long_short_split?.short || 0}`} />
        </div>

        <div className="mt-4 rounded-[1.6rem] border border-black/8 bg-white/70 p-4 text-xs text-slate-600">
          <div className="font-extrabold uppercase tracking-[0.18em] text-slate-500">Do not trade rules</div>
          <div className="mt-2 grid gap-2 md:grid-cols-2">
            <div>Min score for new trade: {rules.min_score_for_new_trade ?? 78}</div>
            <div>Min score for leverage: {rules.min_score_for_leverage ?? 88}</div>
            <div>Max political delay: {rules.max_political_delay_days ?? 45}d</div>
            <div>Crypto leverage blocked: {String(rules.block_crypto_leverage ?? true)}</div>
          </div>
        </div>

        {status && <div className="mt-4 text-sm text-slate-500">{status}</div>}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="surface-panel rounded-[2rem] p-5">
          <div>
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">Active Playbooks</div>
            <div className="mt-1 text-sm text-slate-500">Long- und Short-Ideen aus den stärksten aktuellen Signalen.</div>
          </div>
          <div className="mt-4 grid gap-3">
            {playbooks.length ? (
              playbooks.map((item: any) => (
                <div key={item.id} className="rounded-[1.4rem] border border-black/8 bg-white/75 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-black text-slate-900">{item.title} {item.ticker ? `· ${item.ticker}` : ""}</div>
                      <div className="mt-1 text-xs text-slate-500">{item.headline}</div>
                    </div>
                    <div className="rounded-full border border-[var(--accent)]/15 bg-[var(--accent-soft)] px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-[var(--accent)]">
                      Score {item.score}
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {(item.tags || []).map((tag: string) => (
                      <span key={tag} className="rounded-full border border-black/8 bg-white px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                        {tag}
                      </span>
                    ))}
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-700">{item.thesis}</p>
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
                    <span>Ref {item.reference_price ? `${item.reference_price}` : "N/A"}</span>
                    <span>RR target {item.reward_buffer_pct}% / risk {item.risk_buffer_pct}%</span>
                  </div>
                  {!!item.do_not_trade_reasons?.length && (
                    <div className="mt-3 rounded-[1rem] border border-red-200 bg-red-50 p-3 text-xs text-red-700">
                      {item.do_not_trade_reasons.map((reason: string) => <div key={reason}>{reason}</div>)}
                    </div>
                  )}
                  {!!item.leverage_warnings?.length && (
                    <div className="mt-3 rounded-[1rem] border border-amber-200 bg-amber-50 p-3 text-xs text-amber-700">
                      {item.leverage_warnings.map((reason: string) => <div key={reason}>{reason}</div>)}
                    </div>
                  )}
                  <div className="mt-4 flex flex-wrap gap-2">
                    {item.ticker && (
                      <button onClick={() => onAnalyze(item.ticker)} className="rounded-xl border border-black/8 bg-white px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-700">
                        Analyze
                      </button>
                    )}
                    <button
                      onClick={() => openFromPlaybook(item.id, "long")}
                      disabled={busyId === item.id || item.tradeable === false}
                      className="rounded-xl bg-[var(--accent)] px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-white transition-colors hover:bg-[var(--accent-strong)] disabled:opacity-50"
                    >
                      Paper long
                    </button>
                    <button
                      onClick={() => openFromPlaybook(item.id, "short")}
                      disabled={busyId === item.id || item.tradeable === false}
                      className="rounded-xl border border-black/8 bg-[var(--secondary-strong)] px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-white disabled:opacity-50"
                    >
                      Paper short
                    </button>
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-[1.2rem] border border-black/8 bg-white/75 p-4 text-sm text-slate-500">
                Noch keine Playbooks verfügbar. Erst Watchlist-Signale und Scoreboard laden.
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <div className="surface-panel rounded-[2rem] p-5">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">Open Trades</div>
            <div className="mt-4 space-y-3">
              {openTrades.length ? (
                openTrades.map((trade: any) => (
                  <div key={trade.id} className="rounded-[1.3rem] border border-black/8 bg-white/75 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-black text-slate-900">{trade.ticker} · {trade.direction}</div>
                        <div className="mt-1 text-xs text-slate-500">{trade.setup_type}</div>
                      </div>
                      <div className={`text-sm font-black ${(trade.unrealized_pnl_pct || 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                        {(trade.unrealized_pnl_pct || 0) >= 0 ? "+" : ""}{trade.unrealized_pnl_pct?.toFixed(2)}%
                      </div>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-500">
                      <div>Entry {trade.entry_price}</div>
                      <div>Now {trade.current_price ?? "N/A"}</div>
                      <div>Stop {trade.stop_price ?? "N/A"}</div>
                      <div>Target {trade.target_price ?? "N/A"}</div>
                      <div>Lev {trade.leverage}x</div>
                      <div>RR {trade.risk_reward || "N/A"}</div>
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <button onClick={() => onAnalyze(trade.ticker)} className="rounded-xl border border-black/8 bg-white px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-700">
                        Analyze
                      </button>
                      <button
                        onClick={() => closeTrade(trade.id)}
                        disabled={busyId === trade.id}
                        className="rounded-xl bg-[var(--accent)] px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-white transition-colors hover:bg-[var(--accent-strong)] disabled:opacity-50"
                      >
                        Close trade
                      </button>
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-[1.2rem] border border-black/8 bg-white/75 p-4 text-sm text-slate-500">
                  Noch keine offenen Paper-Trades.
                </div>
              )}
            </div>
          </div>

          <div className="surface-panel rounded-[2rem] p-5">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">Closed Trades</div>
            <div className="mt-4 space-y-3">
              {closedTrades.length ? (
                closedTrades.slice(0, 6).map((trade: any) => (
                  <div key={trade.id} className="rounded-[1.3rem] border border-black/8 bg-white/75 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-black text-slate-900">{trade.ticker} · {trade.direction}</div>
                        <div className="mt-1 text-xs text-slate-500">{trade.setup_type}</div>
                      </div>
                      <div className={`text-sm font-black ${(trade.realized_pnl_pct || 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                        {(trade.realized_pnl_pct || 0) >= 0 ? "+" : ""}{trade.realized_pnl_pct?.toFixed(2)}%
                      </div>
                    </div>
                    <div className="mt-2 text-xs text-slate-500">
                      Entry {trade.entry_price} · Exit {trade.closed_price} · {trade.closed_at ? new Date(trade.closed_at).toLocaleString() : ""}
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-[1.2rem] border border-black/8 bg-white/75 p-4 text-sm text-slate-500">
                  Noch keine geschlossenen Demo-Trades.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="surface-panel rounded-[2rem] p-5">
          <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">Setup Backtest</div>
          <div className="mt-4 space-y-3">
            {setupPerformance.length ? (
              setupPerformance.map((item: any) => (
                <div key={item.setup_type} className="rounded-[1.3rem] border border-black/8 bg-white/75 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-black text-slate-900">{item.setup_type}</div>
                      <div className="mt-1 text-xs text-slate-500">{item.trades} closed trades</div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-black text-slate-900">{item.win_rate}%</div>
                      <div className="mt-1 text-xs text-slate-500">win rate</div>
                    </div>
                  </div>
                  <div className="mt-3 grid grid-cols-3 gap-2 text-xs text-slate-500">
                    <div>Avg {item.avg_pnl_pct >= 0 ? "+" : ""}{item.avg_pnl_pct}%</div>
                    <div>Best {item.best_pnl_pct >= 0 ? "+" : ""}{item.best_pnl_pct}%</div>
                    <div>Worst {item.worst_pnl_pct >= 0 ? "+" : ""}{item.worst_pnl_pct}%</div>
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-[1.2rem] border border-black/8 bg-white/75 p-4 text-sm text-slate-500">
                Noch keine geschlossenen Trades für Setup-Statistiken.
              </div>
            )}
          </div>
        </div>

        <div className="surface-panel rounded-[2rem] p-5">
          <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">Trade Journal</div>
          <div className="mt-4 space-y-3">
            {journal.length ? (
              journal.slice(0, 8).map((entry: any) => {
                const draft = journalDraft[entry.id] || { notes: entry.notes || "", exit_reason: entry.exit_reason || "", lessons_learned: entry.lessons_learned || "" };
                const editing = editingId === entry.id;
                return (
                  <div key={entry.id} className="rounded-[1.3rem] border border-black/8 bg-white/75 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-black text-slate-900">{entry.ticker} · {entry.direction} · {entry.status}</div>
                        <div className="mt-1 text-xs text-slate-500">{entry.setup_type}</div>
                      </div>
                      <div className={`text-sm font-black ${(entry.pnl_pct || 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                        {(entry.pnl_pct || 0) >= 0 ? "+" : ""}{entry.pnl_pct?.toFixed?.(2) ?? "0.00"}%
                      </div>
                    </div>
                    {editing ? (
                      <div className="mt-3 space-y-3">
                        <textarea
                          value={draft.notes}
                          onChange={(e) => setJournalDraft((prev) => ({ ...prev, [entry.id]: { ...draft, notes: e.target.value } }))}
                          placeholder="Notes"
                          className="min-h-[84px] w-full rounded-xl border border-black/8 bg-white px-3 py-2 text-sm text-slate-900"
                        />
                        <input
                          value={draft.exit_reason}
                          onChange={(e) => setJournalDraft((prev) => ({ ...prev, [entry.id]: { ...draft, exit_reason: e.target.value } }))}
                          placeholder="Exit reason"
                          className="w-full rounded-xl border border-black/8 bg-white px-3 py-2 text-sm text-slate-900"
                        />
                        <textarea
                          value={draft.lessons_learned}
                          onChange={(e) => setJournalDraft((prev) => ({ ...prev, [entry.id]: { ...draft, lessons_learned: e.target.value } }))}
                          placeholder="Lessons learned"
                          className="min-h-[84px] w-full rounded-xl border border-black/8 bg-white px-3 py-2 text-sm text-slate-900"
                        />
                        <div className="flex flex-wrap gap-2">
                          <button
                            onClick={() => saveJournal(entry.id)}
                            disabled={busyId === entry.id}
                            className="rounded-xl bg-[var(--accent)] px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-white disabled:opacity-50"
                          >
                            Save journal
                          </button>
                          <button
                            onClick={() => setEditingId(null)}
                            className="rounded-xl border border-black/8 bg-white px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-700"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        {entry.thesis && <p className="mt-3 text-sm leading-6 text-slate-700">{entry.thesis}</p>}
                        {entry.notes && <div className="mt-3 text-sm text-slate-700"><span className="font-bold">Notes:</span> {entry.notes}</div>}
                        {entry.exit_reason && <div className="mt-2 text-sm text-slate-700"><span className="font-bold">Exit:</span> {entry.exit_reason}</div>}
                        {entry.lessons_learned && <div className="mt-2 text-sm text-slate-700"><span className="font-bold">Lesson:</span> {entry.lessons_learned}</div>}
                        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
                          <span>RR {entry.risk_reward || "N/A"}</span>
                          <span>Confidence {entry.confidence_score ?? "N/A"}</span>
                          <span>{entry.closed_at ? new Date(entry.closed_at).toLocaleDateString() : new Date(entry.opened_at).toLocaleDateString()}</span>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            onClick={() => startEditing(entry)}
                            className="rounded-xl border border-black/8 bg-white px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-700"
                          >
                            Edit journal
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                );
              })
            ) : (
              <div className="rounded-[1.2rem] border border-black/8 bg-white/75 p-4 text-sm text-slate-500">
                Noch kein Journal vorhanden.
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
