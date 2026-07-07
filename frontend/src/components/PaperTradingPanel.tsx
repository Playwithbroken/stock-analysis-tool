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

const money = (value: any, currency = "EUR") =>
  new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(Number(value || 0));

const toFiniteNumber = (value: unknown): number | null => {
  const number = typeof value === "number" ? value : Number(value);
  return Number.isFinite(number) ? number : null;
};

const moneyOrNA = (value: any, currency = "EUR") => {
  const number = toFiniteNumber(value);
  return number == null ? "N/A" : money(number, currency);
};

const formatPct = (value: unknown, digits = 2, fallback = "offen") => {
  const number = toFiniteNumber(value);
  if (number == null) return fallback;
  return `${number >= 0 ? "+" : ""}${number.toFixed(digits)}%`;
};

const clampPct = (value: unknown) => {
  const number = toFiniteNumber(value);
  if (number == null) return 0;
  return Math.max(0, Math.min(100, number));
};

const DEFAULT_DEMO_CAPITAL = 500000;

const germanStatus = (value: unknown, fallback = "Lernen") => {
  const key = String(value || "").trim().toLowerCase();
  const labels: Record<string, string> = {
    action_required: "Aktion nötig",
    active_learning: "aktives Lernen",
    ahead: "im Plus",
    behind: "im Minus",
    building_evidence: "Beweise sammeln",
    blocked: "geblockt",
    collect_evidence: "Beweise sammeln",
    downgrade: "herabstufen",
    flat: "neutral",
    hit: "Treffer",
    hold: "halten",
    hold_with_plan: "mit Plan halten",
    learning: "Lernen",
    manual_review_ready: "manuelle Prüfung bereit",
    miss: "Fehlschlag",
    monitor: "überwachen",
    needs_journal: "Journal fehlt",
    no_open_trades: "keine offenen Trades",
    not_started: "noch nicht gestartet",
    ok: "ok",
    open: "offen",
    paper_only: "nur Paper",
    partial: "teilweise",
    pending: "wartet",
    promising: "vielversprechend",
    protect_profit: "Gewinn schützen",
    reduce_risk: "Risiko senken",
    review: "prüfen",
    risk_review: "Risiko prüfen",
    watch: "beobachten",
  };
  return labels[key] || (key ? key.replace(/_/g, " ") : fallback);
};

const germanText = (value: unknown, fallback = "") => {
  const text = String(value || "").trim();
  if (!text) return fallback;
  const labels: Record<string, string> = {
    "Collect more paper evidence before changing risk.": "Mehr Paper-Beweise sammeln, bevor Risiko verändert wird.",
    "Decision support only: no automatic real-money execution.": "Nur Entscheidungsrahmen: keine automatische Echtgeld-Ausführung.",
    "Hold paper position while plan remains valid.": "Paper-Position halten, solange der Plan gültig bleibt.",
    "Hold paper position while trigger remains valid.": "Paper-Position halten, solange der Trigger gültig bleibt.",
    "No option learning data yet.": "Noch keine Options-Lerndaten vorhanden.",
    "No options learning evidence yet.": "Noch keine belastbaren Optionsdaten vorhanden.",
    "Paper only": "nur Paper",
    "Re-check trigger, stop and target before changing the plan.": "Trigger, Stop und Ziel erneut prüfen, bevor der Plan geändert wird.",
  };
  return labels[text] || text;
};

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
  const outcomes = data?.outcomes || {};
  const outcomeLearning = data?.outcome_learning || {};
  const autoSelection = data?.auto_selection || {};
  const autoLearnStatus = data?.auto_learn_status || {};
  const strategyReadiness = data?.strategy_readiness || [];
  const optionReadiness = outcomeLearning.option_readiness || {};
  const learningSummary = outcomeLearning.learning_summary || {};
  const setupAdjustments = Object.values(outcomeLearning.setup_adjustments || {});
  const reviewFocus = learningSummary.review_focus || [];
  const manualReviewChecklist = learningSummary.manual_review_checklist || [];
  const topLearningErrors = outcomeLearning.top_error_tags || [];
  const rules = data?.rules || {};
  const demoAccount = data?.demo_account || {};
  const learningFeedback = demoAccount.learning_feedback || {};
  const currency = demoAccount.currency || "EUR";

  const openPnLTone = useMemo(() => {
    const value = Number(stats.avg_open_pnl_pct || 0);
    return value > 0 ? "good" : value < 0 ? "bad" : "default";
  }, [stats.avg_open_pnl_pct]);

  const realizedTone = useMemo(() => {
    const value = Number(stats.realized_pnl_pct || 0);
    return value > 0 ? "good" : value < 0 ? "bad" : "default";
  }, [stats.realized_pnl_pct]);

  const accountTone = useMemo(() => {
    const value = Number(demoAccount.net_pnl_value || 0);
    return value > 0 ? "good" : value < 0 ? "bad" : "default";
  }, [demoAccount.net_pnl_value]);

  const activePaperDecisions = useMemo(() => {
    return [...openTrades]
      .sort((a: any, b: any) => Math.abs(Number(b.result_value_delta || 0)) - Math.abs(Number(a.result_value_delta || 0)))
      .slice(0, 4);
  }, [openTrades]);

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
          quantity: 0,
          leverage: 1,
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Paper-Trade konnte nicht geöffnet werden.");
      await onRefresh?.();
      setStatus("Paper-Trade eröffnet.");
    } catch (error: any) {
      setStatus(error?.message || "Paper-Trade konnte nicht geöffnet werden.");
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
      if (!response.ok) throw new Error(payload.detail || "Paper-Trade konnte nicht geschlossen werden.");
      await onRefresh?.();
      const alertStatus = payload.telegram_alerts?.status ? ` · Telegram ${payload.telegram_alerts.status}` : "";
      setStatus(`Paper-Trade geschlossen${alertStatus}.`);
    } catch (error: any) {
      setStatus(error?.message || "Paper-Trade konnte nicht geschlossen werden.");
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
      if (!response.ok) throw new Error(payload.detail || "Digest konnte nicht gesendet werden.");
      setStatus(payload.message || "A-Setup-Digest gesendet.");
    } catch (error: any) {
      setStatus(error?.message || "Digest konnte nicht gesendet werden.");
    } finally {
      setBusyId(null);
    }
  };

  const evaluateOutcomes = async () => {
    setBusyId("evaluate-outcomes");
    setStatus("");
    try {
      const response = await fetch("/api/trading/paper-outcomes/evaluate", { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Outcome-Auswertung fehlgeschlagen.");
      await onRefresh?.();
      const alertStatus = payload.paper_learning_alerts?.status ? ` · Telegram ${payload.paper_learning_alerts.status}` : "";
      setStatus(`Outcomes geprüft: ${payload.evaluated || 0}, wartende Daten ${payload.pending_data || 0}${alertStatus}.`);
    } catch (error: any) {
      setStatus(error?.message || "Outcome-Auswertung fehlgeschlagen.");
    } finally {
      setBusyId(null);
    }
  };

  const runAutopilot = async (execute: boolean, mode: "strict" | "learn" = "strict") => {
    setBusyId(`${mode}-${execute ? "autopilot-execute" : "autopilot-preview"}`);
    setStatus("");
    try {
      const response = await fetch("/api/trading/paper-autopilot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ execute, max_trades: 3, mode }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Paper-Autopilot fehlgeschlagen.");
      await onRefresh?.();
      setStatus(
        execute
          ? payload.message || `${payload.opened?.length || 0} Paper-Trades eröffnet.`
          : payload.message || `${payload.selected?.length || 0} Kandidaten erfüllen die Gates.`,
      );
    } catch (error: any) {
      setStatus(error?.message || "Paper-Autopilot fehlgeschlagen.");
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
      setStatus(error?.message || "Journal konnte nicht gespeichert werden.");
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
              Paper-Trading
            </div>
            <h2 className="mt-2 text-3xl text-slate-900">Playbooks, Demo-Trades und Lernschleife</h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
              Jede Idee bekommt ein sauberes Setup mit Richtung, Stop, Ziel und späterem Ergebnis. So lernst du,
              welche Signaltypen bei Aktien, ETFs und Crypto wirklich tragen.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={sendDigest}
              disabled={busyId === "digest"}
              className="rounded-xl bg-[var(--accent)] px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-white disabled:opacity-50"
            >
              A-Setup senden
            </button>
            <button
              onClick={evaluateOutcomes}
              disabled={busyId === "evaluate-outcomes"}
              className="rounded-xl border border-black/8 bg-white px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-700 disabled:opacity-50"
            >
              Outcomes prüfen
            </button>
            <button
              onClick={() => runAutopilot(false, "strict")}
              disabled={busyId === "strict-autopilot-preview"}
              className="rounded-xl border border-black/8 bg-white px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-700 disabled:opacity-50"
            >
              Auto prüfen
            </button>
            <button
              onClick={() => runAutopilot(true, "strict")}
              disabled={busyId === "strict-autopilot-execute"}
              className="rounded-xl bg-[#101114] px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-white disabled:opacity-50"
            >
              Auto Paper öffnen
            </button>
            <button
              onClick={() => runAutopilot(false, "learn")}
              disabled={busyId === "learn-autopilot-preview"}
              className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-amber-800 disabled:opacity-50"
            >
              Lernen prüfen
            </button>
            <button
              onClick={() => runAutopilot(true, "learn")}
              disabled={busyId === "learn-autopilot-execute"}
              className="rounded-xl bg-amber-600 px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-white disabled:opacity-50"
            >
              Lerntrade öffnen
            </button>
            <div className="rounded-full border border-black/8 bg-white/75 px-4 py-2 text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
              {stats.total_trades || 0} getrackte Trades
            </div>
          </div>
        </div>

        <div className="mt-5 rounded-[1.8rem] border border-black/8 bg-white/80 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                Paper-Konto Geldfluss
              </div>
              <div className="mt-2 text-sm leading-6 text-slate-600">
                Demo-Konto startet mit {money(demoAccount.starting_capital || DEFAULT_DEMO_CAPITAL, currency)}.
                Aktuell sind {money(demoAccount.open_exposure_value, currency)} investiert und{" "}
                {money(demoAccount.cash_available_value, currency)} frei. Ergebnis seit Start:{" "}
                <span className={`font-black ${Number(demoAccount.net_pnl_value || 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                  {money(demoAccount.net_pnl_value, currency)} / {formatPct(demoAccount.net_pnl_pct, 2, "0.00%")}
                </span>
                .
              </div>
              <div className="mt-3 rounded-[1rem] border border-black/8 bg-slate-50 px-3 py-2 text-sm font-semibold leading-6 text-slate-700">
                Heute: {demoAccount.day_action || "Auf ein klares Setup mit Trigger warten."}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <div className={`rounded-full px-3 py-1 text-[11px] font-extrabold uppercase tracking-[0.16em] ${
                demoAccount.capital_status === "ahead"
                  ? "bg-emerald-50 text-emerald-700"
                  : demoAccount.capital_status === "behind"
                    ? "bg-red-50 text-red-700"
                    : "border border-black/8 bg-white text-slate-500"
              }`}>
                {germanStatus(demoAccount.capital_status, "neutral")}
              </div>
              <div className={`rounded-full px-3 py-1 text-[11px] font-extrabold uppercase tracking-[0.16em] ${
                demoAccount.day_status === "action_required"
                  ? "bg-red-50 text-red-700"
                  : demoAccount.day_status === "risk_review"
                    ? "bg-amber-50 text-amber-700"
                    : demoAccount.day_status === "protect_profit"
                      ? "bg-sky-50 text-sky-700"
                      : "border border-black/8 bg-white text-slate-500"
              }`}>
                {germanStatus(demoAccount.day_status, "überwachen")}
              </div>
            </div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <StatTile label="Startkapital" value={money(demoAccount.starting_capital || DEFAULT_DEMO_CAPITAL, currency)} />
            <StatTile label="Jetzt investiert" value={money(demoAccount.open_exposure_value, currency)} />
            <StatTile label="Freies Demo-Cash" value={money(demoAccount.cash_available_value, currency)} />
            <StatTile label="Netto-Ergebnis" value={`${money(demoAccount.net_pnl_value, currency)} / ${formatPct(demoAccount.net_pnl_pct, 2, "0.00%")}`} tone={accountTone as any} />
          </div>
          <div className="mt-4 rounded-[1.4rem] border border-black/8 bg-slate-50/80 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                  Kapitalaufteilung
                </div>
                <div className="mt-1 text-sm font-semibold text-slate-700">
                  {formatPct(demoAccount.open_exposure_pct, 2, "0.00%")} investiert ·{" "}
                  {formatPct(demoAccount.open_risk_pct, 2, "0.00%")} echtes Risiko offen ·{" "}
                  {demoAccount.open_trade_count || 0} offene Trades
                </div>
              </div>
              <div className={`rounded-full px-3 py-1 text-[11px] font-extrabold uppercase tracking-[0.16em] ${
                Number(demoAccount.net_pnl_value || 0) >= 0
                  ? "bg-emerald-50 text-emerald-700"
                  : "bg-red-50 text-red-700"
              }`}>
                {money(demoAccount.net_pnl_value, currency)} seit Start
              </div>
            </div>
            <div className="mt-4 h-3 overflow-hidden rounded-full bg-white ring-1 ring-black/8">
              <div
                className="h-full rounded-full bg-[var(--accent)]"
                style={{ width: `${clampPct(demoAccount.open_exposure_pct)}%` }}
              />
            </div>
            <div className="mt-3 grid gap-2 text-xs font-semibold text-slate-600 sm:grid-cols-3">
              <div>
                <span className="font-extrabold text-slate-900">{money(demoAccount.open_exposure_value, currency)}</span>
                {" "}im Markt
              </div>
              <div>
                <span className="font-extrabold text-slate-900">{money(demoAccount.cash_available_value, currency)}</span>
                {" "}frei
              </div>
              <div>
                <span className="font-extrabold text-slate-900">{money(demoAccount.remaining_risk_value, currency)}</span>
                {" "}Risikobudget frei
              </div>
            </div>
          </div>
        </div>

        <div className="mt-4 rounded-[1.8rem] border border-black/8 bg-white/75 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                Active Paper Decisions
              </div>
              <div className="mt-1 text-sm text-slate-600">
                Was gerade im Demo-Konto läuft, wie viel gebunden ist und was als Nächstes zu tun ist.
              </div>
            </div>
            <div className="rounded-full border border-black/8 bg-white px-3 py-1 text-[11px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
              {activePaperDecisions.length} offen
            </div>
          </div>
          {activePaperDecisions.length ? (
            <div className="mt-4 grid gap-3 lg:grid-cols-2 xl:grid-cols-4">
              {activePaperDecisions.map((trade: any) => {
                const management = trade.management_plan || {};
                const pnlValue = Number(trade.result_value_delta || 0);
                return (
                  <button
                    key={`decision-${trade.id}`}
                    onClick={() => trade.ticker && onAnalyze(trade.ticker)}
                    className="rounded-[1.2rem] border border-black/8 bg-white px-4 py-3 text-left transition hover:border-[var(--accent)]/30 hover:bg-[var(--accent-soft)]/35"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-sm font-black text-slate-900">
                          {trade.ticker} / {String(trade.direction || "").toUpperCase()}
                        </div>
                        <div className="mt-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                          {trade.setup_type || "paper setup"}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className={`text-sm font-black ${pnlValue >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                          {moneyOrNA(trade.result_value_delta, currency)}
                        </div>
                        <div className="mt-1 rounded-full border border-black/8 bg-white px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.12em] text-slate-500">
                          {germanStatus(management.decision_grade, "halten")}
                        </div>
                      </div>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-600">
                      <div>
                        <div className="font-extrabold uppercase tracking-[0.12em] text-slate-400">Investiert</div>
                        <div className="mt-1 font-bold text-slate-900">{moneyOrNA(trade.invested_value, currency)}</div>
                      </div>
                      <div>
                        <div className="font-extrabold uppercase tracking-[0.12em] text-slate-400">Plan</div>
                        <div className="mt-1 font-bold text-slate-900">{germanStatus(management.action, "halten")}</div>
                      </div>
                    </div>
                    <div className="mt-3 rounded-xl border border-black/8 bg-slate-50 px-3 py-2 text-xs font-semibold leading-5 text-slate-600">
                      {germanText(management.summary, "Paper-Position halten, solange der Trigger gültig bleibt.")}
                    </div>
                    <div className="mt-2 text-xs font-bold leading-5 text-slate-700">
                      Nächste Prüfung: {germanText(management.next_check, "Trigger, Stop und Ziel erneut prüfen, bevor der Plan geändert wird.")}
                    </div>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="mt-4 rounded-[1.2rem] border border-black/8 bg-slate-50 px-4 py-3 text-sm text-slate-500">
              Keine offenen Demo-Trades. Der Autopilot wartet auf ein Setup mit sauberem Trigger, Risiko und freiem Slot.
            </div>
          )}
        </div>

        <div className="mt-4 rounded-[1.6rem] border border-black/8 bg-white/75 p-4 text-xs text-slate-700">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="font-extrabold uppercase tracking-[0.18em] text-slate-500">Demo-Autopilot Auswahl</div>
              <div className="mt-2 max-w-3xl leading-5">
                Wählt nur Paper-Trades mit Score &gt;= {autoSelection.min_score || 88}, voller These, Trigger,
                Invalidation, freiem Risikobudget und ohne offene Duplikate. Lernmodus testet ab Score &gt;= {autoSelection.exploration_min_score || 60}
                mit sehr kleinem Demo-Risiko ({Math.round(Number(autoSelection.exploration_risk_multiplier || 0.1) * 100)}%). Keine Echtgeld-Ausführung.
              </div>
            </div>
            <div className="rounded-full border border-black/8 bg-white px-3 py-1 font-extrabold uppercase tracking-[0.14em] text-slate-600">
              {autoSelection.selected?.length || 0} streng / {autoSelection.exploration?.length || 0} lernen
            </div>
          </div>
          <div className="mt-3 rounded-[1rem] border border-black/8 bg-white/70 px-3 py-2 text-slate-600">
            <span className="font-extrabold uppercase tracking-[0.14em] text-slate-500">Geplanter Lernlauf:</span>{" "}
            <span className="font-bold text-slate-800">{germanStatus(autoLearnStatus.status, "noch nicht gestartet")}</span>
            {autoLearnStatus.opened?.length ? ` · geöffnet ${autoLearnStatus.opened.length}` : ""}
            {autoLearnStatus.next_allowed_at ? ` · nächster Lauf ${new Date(autoLearnStatus.next_allowed_at).toLocaleString()}` : ""}
            {autoLearnStatus.message ? ` · ${autoLearnStatus.message}` : ""}
          </div>
          {autoSelection.blocker_summary?.top_reasons?.length ? (
            <div className="mt-3 rounded-[1.1rem] border border-amber-500/20 bg-amber-50/80 p-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="font-extrabold uppercase tracking-[0.18em] text-amber-800">Warum kein Strict Trade?</div>
                  <div className="mt-1 text-slate-700">
                    {autoSelection.rejected_count || autoSelection.blocker_summary.checked || 0} Kandidaten wurden geblockt, weil die Gates noch nicht sauber genug sind.
                    {autoSelection.blocker_summary.duplicate_blocked_count ? ` ${autoSelection.blocker_summary.duplicate_blocked_count} davon laufen bereits als Paper-Trade.` : ""}
                  </div>
                </div>
                {autoSelection.blocker_summary.next_best_rejected ? (
                  <div className="rounded-full border border-amber-200 bg-white px-3 py-1 font-extrabold uppercase tracking-[0.12em] text-amber-800">
                    {autoSelection.blocker_summary.next_best_rejected.source === "best_fixable" ? "fixbar" : "nächster"}: {autoSelection.blocker_summary.next_best_rejected.ticker} / {autoSelection.blocker_summary.next_best_rejected.score}
                  </div>
                ) : null}
              </div>
              <div className="mt-3 grid gap-2 lg:grid-cols-2">
                {autoSelection.blocker_summary.top_reasons.slice(0, 4).map((item: any) => (
                  <div key={item.reason} className="rounded-xl border border-black/8 bg-white/80 px-3 py-2 text-slate-700">
                    <span className="font-black text-amber-800">{item.count}x</span> {item.display_reason || item.reason}
                  </div>
                ))}
              </div>
              {autoSelection.blocker_summary.next_best_rejected?.reasons?.length ? (
                <div className="mt-3 rounded-xl border border-black/8 bg-white/80 px-3 py-2 text-slate-700">
                  <span className="font-extrabold uppercase tracking-[0.14em] text-slate-500">Nächster Kandidat:</span>{" "}
                  {autoSelection.blocker_summary.next_best_rejected.ticker} wird geblockt durch{" "}
                  {(autoSelection.blocker_summary.next_best_rejected.display_reasons || autoSelection.blocker_summary.next_best_rejected.reasons).join(" / ")}.
                  {autoSelection.blocker_summary.next_best_rejected.next_action ? (
                    <div className="mt-2 font-bold text-slate-900">
                      Nächster Schritt: {autoSelection.blocker_summary.next_best_rejected.next_action}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}
          {autoSelection.selected?.length ? (
            <div className="mt-3 grid gap-3 lg:grid-cols-3">
              {autoSelection.selected.slice(0, 3).map((item: any) => (
                <div key={item.id} className="rounded-[1.1rem] border border-emerald-500/20 bg-emerald-50/80 p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="font-black text-slate-900">{item.ticker} · {item.direction}</div>
                    <div className="font-black text-emerald-700">{item.score}</div>
                  </div>
                  <div className="mt-1 text-slate-500">{item.setup_type}</div>
                  <div className="mt-2 text-slate-700">Max. Verlust {money(item.suggested_max_loss_value, currency)}</div>
                  {item.trigger ? <div className="mt-2 text-emerald-900">Trigger: {item.trigger}</div> : null}
                  {item.invalidation ? <div className="mt-1 text-emerald-800">Invalidation: {item.invalidation}</div> : null}
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-3 rounded-[1rem] border border-amber-500/20 bg-amber-50 px-3 py-2 font-semibold text-amber-800">
              Noch kein Setup erfüllt alle Auto-Gates. Das ist korrekt: kein Paper-Trade ohne sauberen Trigger.
            </div>
          )}
          {autoSelection.exploration?.length ? (
            <div className="mt-3">
              <div className="font-extrabold uppercase tracking-[0.18em] text-amber-700">Lernkandidaten</div>
              <div className="mt-2 grid gap-3 lg:grid-cols-3">
                {autoSelection.exploration.slice(0, 3).map((item: any) => (
                  <div key={item.id} className="rounded-[1.1rem] border border-amber-500/20 bg-amber-50/80 p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="font-black text-slate-900">{item.ticker} · {item.direction}</div>
                      <div className="font-black text-amber-700">{item.score}</div>
                    </div>
                    <div className="mt-1 text-slate-500">{item.strategy_label || item.setup_type}</div>
                    <div className="mt-2 text-slate-700">Kleines Demo-Risiko {money(item.suggested_max_loss_value, currency)}</div>
                    <div className="mt-2 text-amber-900">Nur zum Lernen: kleine Position, gleiche These, gleiche Invalidierung.</div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {autoSelection.rejected?.length ? (
            <div className="mt-3 grid gap-3 lg:grid-cols-2">
              {autoSelection.rejected.slice(0, 4).map((item: any) => (
                <div key={item.id} className="rounded-[1.1rem] border border-red-500/15 bg-red-50/80 p-3">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <div className="font-black text-slate-900">{item.ticker} · {item.direction}</div>
                      <div className="mt-1 text-slate-500">{item.setup_type} · Score {item.score}</div>
                    </div>
                    <div className="rounded-full border border-red-200 bg-white px-2 py-1 font-extrabold uppercase tracking-[0.12em] text-red-700">
                      kein Trade
                    </div>
                  </div>
                  <div className="mt-2 grid gap-1 text-red-800">
                    {(item.display_reasons || item.reasons || []).slice(0, 3).map((reason: string) => (
                      <div key={reason}>Block: {reason}</div>
                    ))}
                  </div>
                  {item.next_action ? (
                    <div className="mt-2 rounded-xl border border-black/8 bg-white px-3 py-2 font-semibold leading-5 text-slate-700">
                      Nächster Schritt: {item.next_action}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
        </div>

        <div className="mt-4 rounded-[1.6rem] border border-black/8 bg-white/75 p-4 text-xs text-slate-700">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="font-extrabold uppercase tracking-[0.18em] text-slate-500">Strategie-Bibliothek</div>
              <div className="mt-2 max-w-3xl leading-5">
                Jede Strategie hat eigene Gates, Paper-Mindestdaten und einen Real-World-Review-Status. Echtgeld bleibt
                manuell, bis die Demo-Daten einen wiederholbaren Vorteil zeigen.
              </div>
            </div>
            <div className="rounded-full border border-black/8 bg-white px-3 py-1 font-extrabold uppercase tracking-[0.14em] text-slate-600">
              {strategyReadiness.filter((item: any) => item.real_world_ready).length} prüfbereit
            </div>
          </div>
          <div className="mt-3 grid gap-3 lg:grid-cols-3">
            {strategyReadiness.slice(0, 6).map((item: any) => (
              <div key={item.id} className="rounded-[1.1rem] border border-black/8 bg-white/80 p-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-black text-slate-900">{item.label}</div>
                    <div className="mt-1 text-slate-500">{item.horizon}</div>
                  </div>
                  <span
                    className={`rounded-full px-2.5 py-1 font-extrabold uppercase tracking-[0.12em] ${
                      item.real_world_ready
                        ? "bg-emerald-50 text-emerald-700"
                        : item.status === "learning" || item.status === "active_learning"
                          ? "bg-amber-50 text-amber-700"
                          : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {germanStatus(item.status, "Lernen")}
                  </span>
                </div>
                <p className="mt-3 leading-5 text-slate-600">{item.objective}</p>
                <div className="mt-3 grid grid-cols-3 gap-2 text-slate-500">
                  <div>
                    <div className="font-black text-slate-900">{item.decisive_checks || 0}</div>
                    <div>Prüfungen</div>
                  </div>
                  <div>
                    <div className="font-black text-slate-900">{item.hit_rate || 0}%</div>
                    <div>Treffer</div>
                  </div>
                  <div>
                    <div className="font-black text-slate-900">{item.open_trades || 0}</div>
                    <div>Offen</div>
                  </div>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2 text-slate-500">
                  <div>
                    <div className="font-black text-slate-900">{formatPct(item.avg_closed_pnl_pct, 2, "0.00%")}</div>
                    <div>Ø geschlossen</div>
                  </div>
                  <div>
                    <div className="font-black text-slate-900">{formatPct(item.avg_open_pnl_pct, 2, "0.00%")}</div>
                    <div>Ø offen</div>
                  </div>
                </div>
                <div className="mt-3 rounded-xl border border-black/8 bg-slate-50 px-3 py-2 font-semibold text-slate-700">
                  {item.next_step}
                </div>
                <div className="mt-2 rounded-xl border border-black/8 bg-white px-3 py-2 text-slate-600">
                  Empfehlung: <span className="font-bold text-slate-900">{germanStatus(item.recommendation, "Beweise sammeln")}</span>
                </div>
                {item.last_closed && (
                  <div className="mt-2 rounded-xl border border-black/8 bg-white px-3 py-2 text-slate-600">
                    Letzter Abschluss: <span className="font-bold text-slate-900">{item.last_closed.ticker}</span>{" "}
                    {formatPct(item.last_closed.realized_pnl_pct, 2, "0.00%")} · {item.last_closed.exit_reason || "Paper-Exit"}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="mt-4 grid gap-3 text-xs lg:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-[1.6rem] border border-sky-200 bg-sky-50/80 p-4 text-sky-900">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="font-extrabold uppercase tracking-[0.18em] text-sky-700">Nächster Prüf-Fokus</div>
              <span
                className={`rounded-full px-3 py-1 font-extrabold uppercase tracking-[0.14em] ${
                  optionReadiness.real_money_ready
                    ? "bg-emerald-50 text-emerald-700"
                    : optionReadiness.status === "building_evidence"
                      ? "bg-amber-50 text-amber-700"
                      : "bg-white/80 text-slate-600"
                }`}
              >
                {germanText(optionReadiness.label, "nur Paper")}
              </span>
            </div>
            <div className="mt-3 grid gap-2">
              {reviewFocus.map((item: string) => (
                <div key={item}>{item}</div>
              ))}
            </div>
            {!!topLearningErrors.length && (
              <div className="mt-3 flex flex-wrap gap-2">
                {topLearningErrors.slice(0, 4).map((item: any) => (
                  <span key={item.error_tag} className="rounded-full border border-sky-200 bg-white/80 px-3 py-1 font-bold text-sky-800">
                    {item.error_tag}: {item.count}
                  </span>
                ))}
              </div>
            )}
            <div className="mt-3 text-sky-800">
              Optionen brauchen {optionReadiness.required_decisive || 20} klare Prüfungen und {optionReadiness.required_hit_rate || 55}% Trefferquote.
              {!optionReadiness.real_money_ready && optionReadiness.checks_remaining != null
                ? ` ${optionReadiness.checks_remaining} Prüfungen fehlen noch.`
                : ""}
            </div>
          </div>
          <div className="rounded-[1.6rem] border border-black/8 bg-white/75 p-4 text-slate-700">
            <div className="font-extrabold uppercase tracking-[0.18em] text-slate-500">Manuelles Echtgeld-Gate</div>
            <div className="mt-3 grid gap-2">
              {manualReviewChecklist.map((item: string) => (
                <div key={item}>{item}</div>
              ))}
            </div>
            <div className="mt-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 font-bold text-red-700">
              {germanText(learningSummary.real_money_policy, "Nur Entscheidungsrahmen: keine automatische Echtgeld-Ausführung.")}
            </div>
          </div>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <StatTile label="Demo-Kapital" value={money(demoAccount.equity || demoAccount.starting_capital || DEFAULT_DEMO_CAPITAL, currency)} />
          <StatTile label="Risiko / Trade" value={money(demoAccount.risk_budget_per_trade_value, currency)} />
          <StatTile label="Offenes Risiko" value={`${money(demoAccount.open_risk_value, currency)} · ${demoAccount.open_risk_pct || 0}%`} />
          <StatTile label="Offene Exposure" value={`${money(demoAccount.open_exposure_value, currency)} · ${demoAccount.open_exposure_pct || 0}%`} />
        </div>

        <div className="mt-4 grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="rounded-[1.6rem] border border-emerald-500/20 bg-emerald-50/80 p-4 text-xs text-emerald-900">
            <div className="font-extrabold uppercase tracking-[0.18em] text-emerald-700">Demo-Konto Leitplanken</div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <div>Startkapital: {money(demoAccount.starting_capital || DEFAULT_DEMO_CAPITAL, currency)}</div>
              <div>Max. Position: {money(demoAccount.max_position_value, currency)} / Idee</div>
              <div>Max. offenes Risiko: {money(demoAccount.max_open_risk_value, currency)}</div>
              <div>Freies Risiko: {money(demoAccount.remaining_risk_value, currency)}</div>
              <div>Optionsrisiko/Trade: {money(demoAccount.risk_budget_per_option_trade_value, currency)}</div>
              <div>Max. Optionsprämie: {money(demoAccount.max_option_premium_value, currency)}</div>
              <div>Freie Slots: {demoAccount.open_trade_slots ?? 0}</div>
              <div>Modus: nur Paper-Lernen</div>
            </div>
          </div>
          <div className="rounded-[1.6rem] border border-black/8 bg-white/70 p-4 text-xs text-slate-600">
            <div className="font-extrabold uppercase tracking-[0.18em] text-slate-500">Lernregeln</div>
            <div className="mt-3 grid gap-2">
              {(demoAccount.guardrails || []).map((rule: string) => (
                <div key={rule}>{rule}</div>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-4 rounded-[1.6rem] border border-black/8 bg-white/70 p-4 text-xs text-slate-600">
          <div className="font-extrabold uppercase tracking-[0.18em] text-slate-500">Fehlerlernen</div>
          <div className="mt-3 grid gap-3 lg:grid-cols-[0.8fr_1.2fr]">
            <div className="grid gap-2 sm:grid-cols-3">
              <div>Geschlossen: {learningFeedback.closed_trades || 0}</div>
              <div>Optionen: {learningFeedback.option_closed_trades || 0}</div>
              <div>Options-Treffer: {learningFeedback.option_win_rate || 0}%</div>
              <div>Journal: {learningFeedback.journal_completion_rate ?? 100}%</div>
              <div>Fehlende Learnings: {learningFeedback.missing_journal_count || 0}</div>
            </div>
            <div className="font-semibold text-slate-800">{germanText(learningFeedback.next_rule, "Noch keine Options-Lerndaten vorhanden.")}</div>
          </div>
          {!!learningFeedback.missing_journal_trades?.length && (
            <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-amber-800">
              <div className="font-extrabold uppercase tracking-[0.16em]">Offene Lernnotizen</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {learningFeedback.missing_journal_trades.map((item: any) => (
                  <span key={item.id} className="rounded-full border border-amber-200 bg-white/75 px-3 py-1 font-bold">
                    {item.ticker} {formatPct(item.realized_pnl_pct, 2, "0.00%")}
                  </span>
                ))}
              </div>
            </div>
          )}
          {!!learningFeedback.top_mistakes?.length && (
            <div className="mt-3 flex flex-wrap gap-2">
              {learningFeedback.top_mistakes.map((item: any) => (
                <span key={item.reason} className="rounded-full border border-red-200 bg-red-50 px-3 py-1 font-bold text-red-700">
                  {item.reason}: {item.count}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="mt-4 rounded-[1.6rem] border border-black/8 bg-white/70 p-4 text-xs text-slate-600">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
          <div className="font-extrabold uppercase tracking-[0.18em] text-slate-500">Automatische Outcome-Prüfungen</div>
              <div className="mt-2 text-slate-700">
                Treffer {outcomes.summary?.hit_rate || 0}% · geprüft {outcomes.summary?.evaluated || 0} · offen {outcomes.summary?.pending || 0}
              </div>
            </div>
            {!!outcomes.top_errors?.length && (
              <div className="flex max-w-xl flex-wrap gap-2">
                {outcomes.top_errors.map((item: any) => (
                  <span key={item.error_tag} className="rounded-full border border-red-200 bg-red-50 px-3 py-1 font-bold text-red-700">
                    {item.error_tag}: {item.count}
                  </span>
                ))}
              </div>
            )}
          </div>
          {!!outcomes.recent?.length && (
            <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
              {outcomes.recent.slice(0, 6).map((item: any) => (
                <div key={item.id} className="rounded-[1rem] border border-black/8 bg-white px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-black text-slate-900">{item.ticker} · {item.horizon_hours}h</span>
                    <span className="font-bold uppercase text-slate-500">{germanStatus(item.result || item.status, "wartet")}</span>
                  </div>
                  <div className="mt-1 text-slate-500">
                    {item.performance_pct != null ? `Edge ${Number(item.performance_pct).toFixed(2)}%` : "Wartet auf Prüfung"} {item.error_tag ? `· ${item.error_tag}` : ""}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="mt-4 rounded-[1.6rem] border border-black/8 bg-white/70 p-4 text-xs text-slate-600">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
          <div className="font-extrabold uppercase tracking-[0.18em] text-slate-500">Lernkontrolle</div>
              <div className="mt-2 font-semibold text-slate-800">
                Optionen: {optionReadiness.decisive || 0} klare Prüfungen · {optionReadiness.hit_rate || 0}% Treffer ·{" "}
                {optionReadiness.real_money_ready ? "manuelle Prüfung bereit" : "nur Paper"}
              </div>
              <div className="mt-1 text-slate-500">{germanText(optionReadiness.reason, "Noch keine belastbaren Optionsdaten vorhanden.")}</div>
            </div>
            {!!setupAdjustments.length && (
              <div className="grid w-full gap-2 lg:max-w-3xl lg:grid-cols-2">
                {setupAdjustments.slice(0, 4).map((item: any) => (
                  <div key={item.setup_type} className="rounded-[1rem] border border-black/8 bg-white px-3 py-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-black text-slate-900">{item.setup_type}</span>
                      <span className={item.block ? "font-bold text-red-700" : item.score_delta < 0 ? "font-bold text-amber-700" : "font-bold text-emerald-700"}>
                        {item.block ? "geblockt" : item.score_delta > 0 ? `+${item.score_delta}` : item.score_delta}
                      </span>
                    </div>
                    <div className="mt-1 text-slate-500">Treffer {item.hit_rate}% · {item.decisive} Prüfungen</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <StatTile label="Trefferquote" value={formatPct(stats.win_rate, 0, "0%").replace("+", "")} tone={Number(stats.win_rate || 0) >= 50 ? "good" : "default"} />
          <StatTile label="Offene PnL" value={formatPct(stats.avg_open_pnl_pct, 2, "+0.00%")} tone={openPnLTone as any} />
          <StatTile label="Realisiert" value={formatPct(stats.realized_pnl_pct, 2, "+0.00%")} tone={realizedTone as any} />
          <StatTile label="Long / Short" value={`${stats.long_short_split?.long || 0} / ${stats.long_short_split?.short || 0}`} />
        </div>

        <div className="mt-4 rounded-[1.6rem] border border-black/8 bg-white/70 p-4 text-xs text-slate-600">
          <div className="font-extrabold uppercase tracking-[0.18em] text-slate-500">Nicht-handeln-Regeln</div>
          <div className="mt-2 grid gap-2 md:grid-cols-2">
            <div>Mindestscore für neuen Trade: {rules.min_score_for_new_trade ?? 78}</div>
            <div>Mindestscore für Hebel: {rules.min_score_for_leverage ?? 88}</div>
            <div>Max. politischer Delay: {rules.max_political_delay_days ?? 45}d</div>
            <div>Crypto-Hebel geblockt: {String(rules.block_crypto_leverage ?? true)}</div>
          </div>
        </div>

        {status && <div className="mt-4 text-sm text-slate-500">{status}</div>}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="surface-panel rounded-[2rem] p-5">
          <div>
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">Aktive Playbooks</div>
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
                  {item.decision_framework && (
                    <div className="mt-3 grid gap-2 rounded-[1.1rem] border border-slate-200 bg-slate-50/90 p-3 text-xs text-slate-700 lg:grid-cols-3">
                      <div>
                        <div className="font-extrabold uppercase tracking-[0.14em] text-slate-500">Trigger</div>
                        <div className="mt-1 leading-5">{item.decision_framework.entry_trigger}</div>
                      </div>
                      <div>
                        <div className="font-extrabold uppercase tracking-[0.14em] text-slate-500">Invalidation</div>
                        <div className="mt-1 leading-5">{item.decision_framework.invalidation}</div>
                      </div>
                      <div>
                        <div className="font-extrabold uppercase tracking-[0.14em] text-slate-500">Risiko</div>
                        <div className="mt-1 leading-5">{item.decision_framework.risk_plan}</div>
                      </div>
                      <div className="lg:col-span-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded-full border border-black/8 bg-white px-2.5 py-1 font-extrabold uppercase tracking-[0.14em] text-slate-600">
                            {item.decision_framework.evidence_level}
                          </span>
                          {(item.decision_framework.review_questions || []).slice(0, 2).map((question: string) => (
                            <span key={question} className="rounded-full border border-slate-200 bg-white px-2.5 py-1 font-semibold text-slate-600">
                              {question}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                  {item.learning_adjustment && (
                    <div className="mt-3 rounded-[1rem] border border-sky-200 bg-sky-50 p-3 text-xs text-sky-800">
                      <div className="font-extrabold uppercase tracking-[0.14em]">Outcome-Lernen</div>
                      <div className="mt-1">
                        Score {Number(item.learning_adjustment.score_delta || 0) >= 0 ? "+" : ""}
                        {item.learning_adjustment.score_delta || 0}
                        {item.raw_score != null ? ` · roh ${item.raw_score}` : ""}
                      </div>
                      {(item.learning_adjustment.notes || []).map((note: string) => (
                        <div key={note} className="mt-1">{note}</div>
                      ))}
                    </div>
                  )}
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
                    <span>Referenz {item.reference_price ? `${item.reference_price}` : "N/A"}</span>
                    <span>CRV-Ziel {item.reward_buffer_pct}% / Risiko {item.risk_buffer_pct}%</span>
                  </div>
                  <div className="mt-3 grid gap-2 rounded-[1.1rem] border border-emerald-500/15 bg-emerald-50/70 p-3 text-xs text-emerald-900 sm:grid-cols-2">
                    <div className="font-bold">Demo-Größe: {item.suggested_quantity || 0}</div>
                    <div>Nominalwert: {money(item.suggested_notional_value, currency)}</div>
                    <div>Max. Verlust: {money(item.suggested_max_loss_value, currency)}</div>
                    <div>Konto/Risiko: {item.suggested_account_pct || 0}% / {item.suggested_risk_pct || 0}%</div>
                    {item.asset_class === "option" && <div>Kontrakt: x{item.contract_multiplier || 100} · {item.option_type?.toUpperCase?.()}</div>}
                    {item.asset_class === "option" && <div>Max. Haltedauer: {item.max_holding_days || 10}d</div>}
                  </div>
                  {!!item.do_not_trade_reasons?.length && (
                    <div className="mt-3 rounded-[1rem] border border-red-200 bg-red-50 p-3 text-xs text-red-700">
                      {item.do_not_trade_reasons.map((reason: string) => <div key={reason}>{reason}</div>)}
                    </div>
                  )}
                  {!!item.demo_block_reasons?.length && (
                    <div className="mt-3 rounded-[1rem] border border-red-200 bg-red-50 p-3 text-xs text-red-700">
                      {item.demo_block_reasons.map((reason: string) => <div key={reason}>{reason}</div>)}
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
                        Analysieren
                      </button>
                    )}
                    {item.asset_class === "option" ? (
                      <button
                        onClick={() => openFromPlaybook(item.id, item.direction)}
                        disabled={busyId === item.id || item.tradeable === false || item.demo_tradeable === false}
                        className="rounded-xl bg-[var(--accent)] px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-white transition-colors hover:bg-[var(--accent-strong)] disabled:opacity-50"
                      >
                        Paper {item.direction}
                      </button>
                    ) : (
                      <>
                        <button
                          onClick={() => openFromPlaybook(item.id, "long")}
                          disabled={busyId === item.id || item.tradeable === false || item.demo_tradeable === false}
                          className="rounded-xl bg-[var(--accent)] px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-white transition-colors hover:bg-[var(--accent-strong)] disabled:opacity-50"
                        >
                          Paper long
                        </button>
                        <button
                          onClick={() => openFromPlaybook(item.id, "short")}
                          disabled={busyId === item.id || item.tradeable === false || item.demo_tradeable === false}
                          className="rounded-xl border border-black/8 bg-[var(--secondary-strong)] px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-white disabled:opacity-50"
                        >
                          Paper short
                        </button>
                      </>
                    )}
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
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">Offene Trades</div>
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
                        {formatPct(trade.unrealized_pnl_pct, 2, "+0.00%")}
                      </div>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-500">
                      <div>Einstieg {trade.entry_price}</div>
                      <div>Jetzt {trade.current_price ?? "N/A"}</div>
                      <div>Stop {trade.stop_price ?? "N/A"}</div>
                      <div>Ziel {trade.target_price ?? "N/A"}</div>
                      <div>Hebel {trade.leverage}x</div>
                      <div>RR {trade.risk_reward || "N/A"}</div>
                    </div>
                    <div className="mt-3 grid gap-2 rounded-[1rem] border border-black/8 bg-white px-3 py-2 text-xs text-slate-700 sm:grid-cols-3">
                      <div>
                        <div className="font-extrabold uppercase tracking-[0.12em] text-slate-500">Investiert</div>
                        <div className="mt-1 font-black text-slate-900">{moneyOrNA(trade.invested_value, currency)}</div>
                      </div>
                      <div>
                        <div className="font-extrabold uppercase tracking-[0.12em] text-slate-500">Jetzt</div>
                        <div className="mt-1 font-black text-slate-900">{moneyOrNA(trade.current_value, currency)}</div>
                      </div>
                      <div>
                        <div className="font-extrabold uppercase tracking-[0.12em] text-slate-500">Offene P/L</div>
                        <div className={`mt-1 font-black ${(trade.result_value_delta || 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                          {moneyOrNA(trade.result_value_delta, currency)} / {germanStatus(trade.result_label, "neutral")}
                        </div>
                      </div>
                    </div>
                    {trade.management_plan && (
                      <div className="mt-3 rounded-[1rem] border border-black/8 bg-slate-50 px-3 py-2 text-xs text-slate-700">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-extrabold uppercase tracking-[0.14em] text-slate-500">
                            {germanStatus(trade.management_plan.status, "überwachen")}
                          </span>
                          <span className="font-bold text-slate-900">{germanStatus(trade.management_plan.action, "halten")}</span>
                        </div>
                        <div className="mt-1 leading-5">
                          {germanText(trade.management_plan.summary, "Paper-Position halten, solange der Plan gültig bleibt.")}
                        </div>
                        <div className="mt-2 rounded-xl border border-black/8 bg-white px-3 py-2 font-semibold leading-5 text-slate-700">
                          Nächste Prüfung: {germanText(trade.management_plan.next_check, "Trigger, Stop und Ziel erneut prüfen, bevor der Plan geändert wird.")}
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2 text-slate-500">
                          {trade.management_plan.decision_grade ? (
                            <span>Stufe {germanStatus(trade.management_plan.decision_grade)}</span>
                          ) : null}
                          {trade.management_plan.risk_distance_pct != null ? (
                            <span>Stop-Abstand {formatPct(trade.management_plan.risk_distance_pct, 2, "0.00%")}</span>
                          ) : null}
                          {trade.management_plan.target_progress_pct != null ? (
                            <span>Ziel-Fortschritt {Number(trade.management_plan.target_progress_pct).toFixed(1)}%</span>
                          ) : null}
                        </div>
                      </div>
                    )}
                    <div className="mt-4 flex flex-wrap gap-2">
                      <button onClick={() => onAnalyze(trade.ticker)} className="rounded-xl border border-black/8 bg-white px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-700">
                        Analysieren
                      </button>
                      <button
                        onClick={() => closeTrade(trade.id)}
                        disabled={busyId === trade.id}
                        className="rounded-xl bg-[var(--accent)] px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-white transition-colors hover:bg-[var(--accent-strong)] disabled:opacity-50"
                      >
                        Trade schließen
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
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">Geschlossene Trades</div>
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
                        {formatPct(trade.realized_pnl_pct, 2, "+0.00%")}
                      </div>
                    </div>
                    <div className="mt-2 text-xs text-slate-500">
                      Einstieg {trade.entry_price} · Exit {trade.closed_price} · {trade.closed_at ? new Date(trade.closed_at).toLocaleString() : ""}
                    </div>
                    <div className="mt-3 grid gap-2 rounded-[1rem] border border-black/8 bg-white px-3 py-2 text-xs text-slate-700 sm:grid-cols-3">
                      <div>
                        <div className="font-extrabold uppercase tracking-[0.12em] text-slate-500">Investiert</div>
                        <div className="mt-1 font-black text-slate-900">{moneyOrNA(trade.invested_value, currency)}</div>
                      </div>
                      <div>
                        <div className="font-extrabold uppercase tracking-[0.12em] text-slate-500">Schlusswert</div>
                        <div className="mt-1 font-black text-slate-900">{moneyOrNA(trade.final_value, currency)}</div>
                      </div>
                      <div>
                        <div className="font-extrabold uppercase tracking-[0.12em] text-slate-500">Ergebnis</div>
                        <div className={`mt-1 font-black ${(trade.realized_pnl_value || 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                          {moneyOrNA(trade.realized_pnl_value, currency)} / {germanStatus(trade.result_label, "neutral")}
                        </div>
                      </div>
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
          <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">Setup-Rücktest</div>
          <div className="mt-4 space-y-3">
            {setupPerformance.length ? (
              setupPerformance.map((item: any) => (
                <div key={item.setup_type} className="rounded-[1.3rem] border border-black/8 bg-white/75 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-black text-slate-900">{item.setup_type}</div>
                      <div className="mt-1 text-xs text-slate-500">{item.trades} geschlossene Trades · Journal {item.journal_completion_rate ?? 100}%</div>
                      <div
                        className={`mt-2 inline-flex rounded-full px-2 py-1 text-[10px] font-black uppercase tracking-[0.14em] ${
                          item.quality_status === "promising"
                            ? "bg-emerald-500/10 text-emerald-700"
                            : item.quality_status === "downgrade"
                              ? "bg-red-500/10 text-red-700"
                              : item.quality_status === "needs_journal"
                                ? "bg-amber-500/10 text-amber-700"
                                : "bg-slate-500/10 text-slate-600"
                        }`}
                      >
                        {germanStatus(item.quality_status, "Beweise sammeln")}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-black text-slate-900">{item.win_rate}%</div>
                      <div className="mt-1 text-xs text-slate-500">Trefferquote</div>
                    </div>
                  </div>
                  <div className="mt-3 grid grid-cols-3 gap-2 text-xs text-slate-500">
                    <div>Ø {item.avg_pnl_pct >= 0 ? "+" : ""}{item.avg_pnl_pct}%</div>
                    <div>Bestwert {item.best_pnl_pct >= 0 ? "+" : ""}{item.best_pnl_pct}%</div>
                    <div>Schlecht {item.worst_pnl_pct >= 0 ? "+" : ""}{item.worst_pnl_pct}%</div>
                  </div>
                  <div className="mt-3 rounded-xl border border-black/8 bg-white/80 px-3 py-2 text-xs font-semibold text-slate-700">
                    {germanText(item.next_action, "Mehr Paper-Beweise sammeln, bevor Risiko verändert wird.")}
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
          <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">Trade-Journal</div>
          <div className="mt-4 space-y-3">
            {journal.length ? (
              journal.slice(0, 8).map((entry: any) => {
                const draft = journalDraft[entry.id] || { notes: entry.notes || "", exit_reason: entry.exit_reason || "", lessons_learned: entry.lessons_learned || "" };
                const editing = editingId === entry.id;
                return (
                  <div key={entry.id} className="rounded-[1.3rem] border border-black/8 bg-white/75 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-black text-slate-900">{entry.ticker} · {entry.direction} · {germanStatus(entry.status, "offen")}</div>
                        <div className="mt-1 text-xs text-slate-500">{entry.setup_type}</div>
                      </div>
                      <div className={`text-sm font-black ${(entry.pnl_pct || 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                        {formatPct(entry.pnl_pct, 2, "+0.00%")}
                      </div>
                    </div>
                    {editing ? (
                      <div className="mt-3 space-y-3">
                        <textarea
                          value={draft.notes}
                          onChange={(e) => setJournalDraft((prev) => ({ ...prev, [entry.id]: { ...draft, notes: e.target.value } }))}
                          placeholder="Notizen"
                          className="min-h-[84px] w-full rounded-xl border border-black/8 bg-white px-3 py-2 text-sm text-slate-900"
                        />
                        <input
                          value={draft.exit_reason}
                          onChange={(e) => setJournalDraft((prev) => ({ ...prev, [entry.id]: { ...draft, exit_reason: e.target.value } }))}
                          placeholder="Exit-Grund"
                          className="w-full rounded-xl border border-black/8 bg-white px-3 py-2 text-sm text-slate-900"
                        />
                        <textarea
                          value={draft.lessons_learned}
                          onChange={(e) => setJournalDraft((prev) => ({ ...prev, [entry.id]: { ...draft, lessons_learned: e.target.value } }))}
                          placeholder="Gelernte Lektion"
                          className="min-h-[84px] w-full rounded-xl border border-black/8 bg-white px-3 py-2 text-sm text-slate-900"
                        />
                        <div className="flex flex-wrap gap-2">
                          <button
                            onClick={() => saveJournal(entry.id)}
                            disabled={busyId === entry.id}
                            className="rounded-xl bg-[var(--accent)] px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-white disabled:opacity-50"
                          >
                            Journal speichern
                          </button>
                          <button
                            onClick={() => setEditingId(null)}
                            className="rounded-xl border border-black/8 bg-white px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-700"
                          >
                            Abbrechen
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        {entry.thesis && <p className="mt-3 text-sm leading-6 text-slate-700">{entry.thesis}</p>}
                        {entry.notes && <div className="mt-3 text-sm text-slate-700"><span className="font-bold">Notizen:</span> {entry.notes}</div>}
                        {entry.exit_reason && <div className="mt-2 text-sm text-slate-700"><span className="font-bold">Exit:</span> {entry.exit_reason}</div>}
                        {entry.lessons_learned && <div className="mt-2 text-sm text-slate-700"><span className="font-bold">Lektion:</span> {entry.lessons_learned}</div>}
                        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
                          <span>RR {entry.risk_reward || "N/A"}</span>
                          <span>Vertrauen {entry.confidence_score ?? "N/A"}</span>
                          <span>{entry.closed_at ? new Date(entry.closed_at).toLocaleDateString() : new Date(entry.opened_at).toLocaleDateString()}</span>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            onClick={() => startEditing(entry)}
                            className="rounded-xl border border-black/8 bg-white px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-700"
                          >
                            Journal bearbeiten
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
