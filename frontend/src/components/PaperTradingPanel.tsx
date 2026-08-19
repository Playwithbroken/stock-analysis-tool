import React, { useEffect, useMemo, useState } from "react";

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

const priceOrNA = (value: unknown) => {
  const number = toFiniteNumber(value);
  return number == null
    ? "N/A"
    : new Intl.NumberFormat("de-DE", { maximumFractionDigits: 4 }).format(number);
};

const formatPct = (value: unknown, digits = 2, fallback = "offen") => {
  const number = toFiniteNumber(value);
  if (number == null) return fallback;
  return `${number >= 0 ? "+" : ""}${number.toFixed(digits)}%`;
};

const unsignedPct = (value: unknown, digits = 2, fallback = "offen") => {
  const number = toFiniteNumber(value);
  return number == null ? fallback : `${Math.max(0, number).toFixed(digits)}%`;
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
    building: "im Aufbau",
    blocked: "geblockt",
    collect_evidence: "Beweise sammeln",
    downgrade: "herabstufen",
    flat: "neutral",
    hit: "Treffer",
    hold: "halten",
    hold_with_plan: "mit Plan halten",
    holding_period_expired: "maximale Haltedauer erreicht",
    insufficient_sample: "zu wenig Daten",
    insufficient: "zu wenig Daten",
    learning: "Lernen",
    manual_review_ready: "manuelle Prüfung bereit",
    miss: "Fehlschlag",
    monitor: "überwachen",
    needs_journal: "Journal fehlt",
    no_open_trades: "keine offenen Trades",
    news_reaction_failed: "News-Reaktion gebrochen",
    news_momentum_stalled: "News-Momentum stockt",
    not_started: "noch nicht gestartet",
    ok: "ok",
    open: "offen",
    paper_only: "nur Paper",
    partial: "teilweise",
    price_and_close_review: "Preis erfassen und schließen",
    price_contradicted: "Preis widerspricht",
    paused: "pausiert",
    pending: "wartet",
    promising: "vielversprechend",
    protect_profit: "Gewinn schützen",
    reduce_risk: "Risiko senken",
    review: "prüfen",
    ready: "bereit",
    reduced_risk: "reduziertes Risiko",
    risk_halt: "Trading pausiert",
    risk_review: "Risiko prüfen",
    strict_gate_confirmed: "striktes Gate bestätigt",
    verified_unconfirmed: "Quelle bestätigt, Preis offen",
    directional_headline: "Richtungs-Headline",
    usable: "nutzbare Stichprobe",
    net_long: "netto long",
    net_short: "netto short",
    balanced: "ausgeglichen",
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

const entrySourceLabel = (item: any) => {
  const ticket = item?.trade_ticket && typeof item.trade_ticket === "object" ? item.trade_ticket : {};
  return String(ticket.entry_source_label || item?.entry_source_label || "Paper-Autopilot");
};

function OptionContractEvidence({ item }: { item: any }) {
  if (String(item?.asset_class || "").toLowerCase() !== "option") return null;
  const contract = item?.option_contract && typeof item.option_contract === "object"
    ? item.option_contract
    : item?.trade_ticket?.option_contract && typeof item.trade_ticket.option_contract === "object"
      ? item.trade_ticket.option_contract
      : {};
  const available = contract.status === "available";
  const asOf = contract.data_as_of || item?.data_as_of;

  if (!available) {
    return (
      <div data-testid="option-contract-evidence" className="mt-3 rounded-[1.1rem] border border-red-200 bg-red-50/90 p-3 text-xs text-red-900">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="font-extrabold uppercase tracking-[0.14em]">Optionsdaten nicht verifizierbar</div>
          <span className="rounded-full border border-red-200 bg-white px-2.5 py-1 text-[9px] font-extrabold uppercase tracking-[0.12em] text-red-700">
            kein Kontrakt
          </span>
        </div>
        <div className="mt-2 font-semibold leading-5">
          Kein verifizierbarer Kontrakt-Snapshot ({String(contract.reason || "Optionskette nicht verfügbar").replace(/_/g, " ")}).
          Die angezeigte Prämie ist nur eine Schätzung und keine ausführbare Quote.
        </div>
        <div className="mt-2 font-bold">Paper-Einstieg bleibt gesperrt, bis Strike, Verfall und eine beidseitige Quote belastbar vorliegen.</div>
      </div>
    );
  }

  const quoteQuality = String(contract.quote_quality || "delayed_snapshot_not_executable");
  const realtimeBrokerReference = contract.broker_quote_reference === true && contract.realtime === true;
  const greeks = contract.greeks && typeof contract.greeks === "object" ? contract.greeks : {};
  const hasProviderGreeks = contract.greeks_status === "provider_supplied" || contract.greeks_status === "provider_partial";
  return (
    <div data-testid="option-contract-evidence" className="mt-3 rounded-[1.1rem] border border-violet-200 bg-violet-50/85 p-3 text-xs text-violet-950">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-extrabold uppercase tracking-[0.14em]">Konkreter Optionskontrakt</div>
        <span className={`rounded-full border px-2.5 py-1 text-[9px] font-extrabold uppercase tracking-[0.12em] ${realtimeBrokerReference ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-800"}`}>
          {realtimeBrokerReference ? "Broker-Echtzeit · kein Fill-Versprechen" : "Delayed Research · nicht ausführbar"}
        </span>
      </div>
      <div className="mt-2 break-all font-black text-violet-950">
        {contract.contract_symbol || "Symbol offen"} · {String(contract.option_type || item.option_type || item.direction || "option").toUpperCase()}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-3 sm:grid-cols-4">
        {[
          ["Strike", priceOrNA(contract.strike)],
          ["Verfall", contract.expiry || "N/A"],
          ["Restlaufzeit", contract.days_to_expiry != null ? `${contract.days_to_expiry} Tage` : "N/A"],
          ["Underlying", priceOrNA(contract.underlying_price || item.underlying_reference_price)],
          ["Bid", priceOrNA(contract.bid)],
          ["Ask", priceOrNA(contract.ask)],
          ["Spread", unsignedPct(contract.spread_pct)],
          ["Implizite Volatilität", unsignedPct(contract.implied_volatility_pct)],
          ["Volumen", contract.volume ?? 0],
          ["Open Interest", contract.open_interest ?? 0],
          ["Moneyness", formatPct(contract.moneyness_pct)],
          ["Break-even", priceOrNA(contract.break_even)],
          ["Abstand Break-even", formatPct(contract.distance_to_break_even_pct)],
          ["Max. Prämienverlust", contract.max_loss_per_contract != null ? `${priceOrNA(contract.max_loss_per_contract)} je Kontrakt · Quote-Währung` : "N/A"],
        ].map(([label, value]) => (
          <div key={String(label)} className="min-w-0">
            <div className="text-[9px] font-extrabold uppercase tracking-[0.11em] text-violet-500">{label}</div>
            <div className="mt-1 break-words font-black text-violet-950">{String(value)}</div>
          </div>
        ))}
      </div>
      {hasProviderGreeks ? (
        <div className="mt-3 grid grid-cols-2 gap-3 rounded-xl border border-violet-200 bg-white/70 p-3 sm:grid-cols-4">
          {[
            ["Delta", greeks.delta],
            ["Gamma", greeks.gamma],
            ["Theta", greeks.theta],
            ["Vega", greeks.vega],
          ].map(([label, value]) => (
            <div key={String(label)}>
              <div className="text-[9px] font-extrabold uppercase tracking-[0.11em] text-violet-500">{label}</div>
              <div className="mt-1 font-black text-violet-950">{value != null ? Number(value).toFixed(4) : "N/A"}</div>
            </div>
          ))}
          <div className="col-span-2 text-[10px] font-semibold leading-4 text-violet-700 sm:col-span-4">
            Greeks: {contract.greeks_source || "Anbieter"} · {contract.greeks_model || "Anbietermodell"} · {contract.greeks_status === "provider_partial" ? "teilweise verfügbar" : "vollständig geliefert"}
          </div>
        </div>
      ) : null}
      <div className="mt-3 rounded-xl border border-violet-200 bg-white/70 px-3 py-2 leading-5 text-violet-800">
        <div><span className="font-extrabold">Quelle:</span> {contract.source_label || contract.source || "unbekannt"} · Datenstand {asOf ? new Date(asOf).toLocaleString("de-DE") : "offen"}</div>
        <div><span className="font-extrabold">Datenqualität:</span> {quoteQuality.replace(/_/g, " ")} · {realtimeBrokerReference ? "Marktdatenreferenz, Ausführungspreis nicht garantiert" : "keine verifizierte Broker-Ausführungsquote"}</div>
        {contract.selection_basis ? <div><span className="font-extrabold">Auswahl:</span> {contract.selection_basis}</div> : null}
      </div>
      <div className="mt-2 font-bold text-red-700">{hasProviderGreeks ? "Greeks vom Anbieter, nicht von Broker Freund berechnet" : "Greeks nicht verifiziert"} · Echtgeld und automatische Ausführung gesperrt.</div>
    </div>
  );
}

export default function PaperTradingPanel({ data, onAnalyze, onRefresh }: PaperTradingPanelProps) {
  const [status, setStatus] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [lastAutopilotResult, setLastAutopilotResult] = useState<any | null>(null);
  const [autopilotSettings, setAutopilotSettings] = useState<any>(data?.paper_autopilot_settings || data?.auto_selection?.settings || {});
  const [journalDraft, setJournalDraft] = useState<Record<string, { notes: string; exit_reason: string; lessons_learned: string }>>({});
  const [productDrafts, setProductDrafts] = useState<Record<string, any>>({});
  const [productChecks, setProductChecks] = useState<Record<string, any>>({});

  const stats = data?.stats || {};
  const playbooks = data?.playbooks || [];
  const openTrades = data?.open_trades || [];
  const closedTrades = data?.closed_trades || [];
  const setupPerformance = data?.setup_performance || [];
  const entrySourcePerformance = data?.entry_source_performance || [];
  const newsEvidencePerformance = data?.news_evidence_performance || {};
  const newsEvidenceSummary = newsEvidencePerformance.summary || {};
  const newsSourcePerformance = newsEvidencePerformance.sources || [];
  const newsEventPerformance = newsEvidencePerformance.event_types || [];
  const newsShadowLab = data?.news_shadow_lab || {};
  const newsShadowSummary = newsShadowLab.summary || {};
  const newsShadowCohorts = newsShadowLab.quality_cohorts || [];
  const newsShadowEvents = newsShadowLab.event_types || [];
  const learningContextPerformance = data?.learning_context_performance || [];
  const marketRegimePerformance = data?.market_regime_performance || {};
  const marketRegimeRows = marketRegimePerformance.rows || [];
  const strategyDimensionPerformance = data?.strategy_dimension_performance || {};
  const strategyDimensionRows = strategyDimensionPerformance.rows || [];
  const journal = data?.journal || [];
  const outcomes = data?.outcomes || {};
  const outcomeLearning = data?.outcome_learning || {};
  const autoSelection = data?.auto_selection || {};
  const newsGateMonitor = data?.news_gate_monitor || {};
  const autopilotProfile = data?.paper_autopilot_profile || {};
  const autoLearnStatus = data?.auto_learn_status || {};
  const strategyReadiness = data?.strategy_readiness || [];
  const evidenceCampaign = data?.evidence_campaign || {};
  const optionReadiness = outcomeLearning.option_readiness || {};
  const learningSummary = outcomeLearning.learning_summary || {};
  const setupAdjustments = Object.values(outcomeLearning.setup_adjustments || {});
  const reviewFocus = learningSummary.review_focus || [];
  const manualReviewChecklist = learningSummary.manual_review_checklist || [];
  const topLearningErrors = outcomeLearning.top_error_tags || [];
  const rules = data?.rules || {};
  const demoAccount = data?.demo_account || {};
  const capitalFlow = demoAccount.capital_flow || {};
  const executionCostCalibration = demoAccount.execution_cost_calibration || {};
  const executionCostRows = executionCostCalibration.rows || [];
  const exposureProfile = demoAccount.exposure_profile || {};
  const exposureBuckets = exposureProfile.buckets || [];
  const assetClassLimits = Object.entries(demoAccount.asset_class_limits || {}) as Array<[string, any]>;
  const correlationAnalysis = demoAccount.correlation_analysis || {};
  const highCorrelationPairs = correlationAnalysis.high_correlation_pairs || [];
  const tradeActionQueue = demoAccount.trade_action_queue || {};
  const tradeActionItems = tradeActionQueue.items || [];
  const riskCircuit = demoAccount.risk_circuit || {};
  const learningFeedback = demoAccount.learning_feedback || {};
  const currency = demoAccount.currency || "EUR";
  const nextStrictCandidate = autoSelection.selected?.[0] || null;
  const nextLearningCandidate = autoSelection.exploration?.[0] || null;
  const nextRejectedCandidate = autoSelection.blocker_summary?.next_best_rejected || autoSelection.rejected?.[0] || null;
  const nextPaperDecision = nextStrictCandidate || nextLearningCandidate || nextRejectedCandidate || null;
  const nextPaperDecisionMode = nextStrictCandidate
    ? "strict"
    : nextLearningCandidate
      ? "learning"
      : nextRejectedCandidate
        ? "blocked"
        : "waiting";
  const lastAutopilotSelected = lastAutopilotResult?.selected?.[0] || null;
  const lastAutopilotBlocked =
    lastAutopilotResult?.blocker_summary?.next_best_rejected || lastAutopilotResult?.rejected?.[0] || null;
  const lastAutopilotFocus = lastAutopilotSelected || lastAutopilotBlocked;
  const lastAutopilotReasons = (
    lastAutopilotBlocked?.display_reasons ||
    lastAutopilotBlocked?.reasons ||
    lastAutopilotBlocked?.learning_block_display_reasons ||
    []
  ).slice(0, 2);

  useEffect(() => {
    const nextSettings = data?.paper_autopilot_settings || data?.auto_selection?.settings;
    if (nextSettings) setAutopilotSettings(nextSettings);
  }, [data?.paper_autopilot_settings, data?.auto_selection?.settings]);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/trading/paper-autopilot/settings")
      .then((response) => (response.ok ? response.json() : null))
      .then((payload) => {
        if (!cancelled && payload) setAutopilotSettings(payload);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const performance = stats.performance || {};
  const profitFactor = toFiniteNumber(performance.profit_factor);

  const accountTone = useMemo(() => {
    const value = Number(capitalFlow.net_pnl_value ?? demoAccount.net_pnl_value ?? 0);
    return value > 0 ? "good" : value < 0 ? "bad" : "default";
  }, [capitalFlow.net_pnl_value, demoAccount.net_pnl_value]);
  const grossExposureUsagePct =
    Number(demoAccount.max_gross_exposure_value || 0) > 0
      ? (Number(demoAccount.open_exposure_value || 0) / Number(demoAccount.max_gross_exposure_value)) * 100
      : 0;

  const activePaperDecisions = useMemo(() => {
    return [...openTrades]
      .sort((a: any, b: any) => Math.abs(Number(b.result_value_delta || 0)) - Math.abs(Number(a.result_value_delta || 0)));
  }, [openTrades]);

  const interestingNow = useMemo(() => {
    const rows = [
      ...(autoSelection.interesting_now || []),
      ...(autoSelection.selected || []),
      ...(autoSelection.exploration || []),
      ...(autoSelection.aggressive_exploration || []),
    ];
    const seen = new Set<string>();
    return rows
      .filter((item: any) => {
        const key = String(item?.ticker || "").toUpperCase();
        if (!key || seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .slice(0, 6);
  }, [autoSelection]);

  const configuredRun = useMemo(() => {
    const mode = String(autopilotSettings?.mode || "aggressive_learning");
    const source =
      mode === "strict"
        ? autoSelection.selected
        : mode === "learn"
          ? autoSelection.exploration
          : autoSelection.aggressive_exploration;
    const candidates = Array.isArray(source) ? source : [];
    const maxTrades = Math.max(1, Math.min(8, Number(autopilotSettings?.max_trades || 3)));
    const selected = candidates.slice(0, maxTrades);
    const notional = selected.reduce((sum: number, item: any) => sum + Number(item?.suggested_notional_value || 0), 0);
    const maxLoss = selected.reduce((sum: number, item: any) => sum + Number(item?.suggested_max_loss_value || 0), 0);
    const label =
      mode === "strict"
        ? "Strict"
        : mode === "learn"
          ? "Learning"
          : "Aggressive Learning";
    const intent =
      mode === "strict"
        ? "nur die saubersten A-Setups"
        : mode === "learn"
          ? "kleine Testpositionen zum Beweise sammeln"
          : "mehr Kandidaten, aber weiterhin Paper-only und risikogedeckelt";
    return {
      mode,
      label,
      intent,
      candidates,
      selected,
      lead: selected[0] || candidates[0] || null,
      count: selected.length,
      notional,
      maxLoss,
    };
  }, [autopilotSettings?.mode, autopilotSettings?.max_trades, autoSelection]);

  if (!data) return null;

  const updateProductDraft = (playbookId: string, key: string, value: any) => {
    setProductDrafts((prev) => ({
      ...prev,
      [playbookId]: {
        ...(prev[playbookId] || {}),
        [key]: value,
      },
    }));
    setProductChecks((prev) => {
      const next = { ...prev };
      delete next[playbookId];
      return next;
    });
  };

  const validateProductDraft = async (playbookId: string) => {
    setBusyId(`${playbookId}-product-check`);
    setStatus("");
    try {
      const response = await fetch("/api/trading/leverage-product/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product_data: productDrafts[playbookId] || {} }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Produktpr?fung fehlgeschlagen.");
      setProductChecks((prev) => ({ ...prev, [playbookId]: payload }));
      setStatus(payload.message || "Produktdaten geprüft.");
    } catch (error: any) {
      setStatus(error?.message || "Produktpr?fung fehlgeschlagen.");
    } finally {
      setBusyId(null);
    }
  };

  const openFromPlaybook = async (
    playbookId: string,
    direction: string,
    productData: any = undefined,
    leverage = 1,
  ) => {
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
          leverage,
          product_data: productData || {},
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Paper-Trade konnte nicht geöffnet werden.");
      await onRefresh?.();
      setStatus(`Paper-Trade eröffnet${leverage > 1 ? ` · Hebel ${leverage}x` : ""}.`);
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

  const updateAutopilotSetting = (key: string, value: any) => {
    setAutopilotSettings((prev: any) => ({ ...(prev || {}), [key]: value }));
  };

  const saveAutopilotSettings = async () => {
    setBusyId("save-autopilot-settings");
    setStatus("");
    try {
      const response = await fetch("/api/trading/paper-autopilot/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(autopilotSettings || {}),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Autopilot-Settings konnten nicht gespeichert werden.");
      setAutopilotSettings(payload);
      await onRefresh?.();
      setStatus("Autopilot-Settings gespeichert.");
    } catch (error: any) {
      setStatus(error?.message || "Autopilot-Settings konnten nicht gespeichert werden.");
    } finally {
      setBusyId(null);
    }
  };

  const runAutopilot = async (execute: boolean, mode: "strict" | "learn" | "aggressive_learning" = "strict") => {
    setBusyId(`${mode}-${execute ? "autopilot-execute" : "autopilot-preview"}`);
    setStatus("");
    try {
      const response = await fetch("/api/trading/paper-autopilot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          execute,
          max_trades: Number(autopilotSettings?.max_trades || (mode === "aggressive_learning" ? 5 : 3)),
          mode,
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Paper-Autopilot fehlgeschlagen.");
      await onRefresh?.();
      setLastAutopilotResult(payload);
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

  const runConfiguredAutopilot = async (execute: boolean) => {
    const mode = String(autopilotSettings?.mode || "aggressive_learning") as "strict" | "learn" | "aggressive_learning";
    await runAutopilot(execute, mode);
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
      <div data-testid="decision-scope-paper" className="rounded-[1.35rem] border border-amber-300 bg-amber-50/95 px-4 py-3 text-sm text-amber-950">
        <div className="font-extrabold uppercase tracking-[0.16em]">Paper-only · simuliertes Kapital</div>
        <div className="mt-1 leading-6">
          {data?.decision_scope?.description || "Simuliertes Lernen ohne Brokerorder oder Echtgeldwirkung."}
          {" "}Kein Button in diesem Bereich darf eine Echtgeldorder erzeugen.
        </div>
      </div>
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
            <button
              onClick={() => runAutopilot(false, "aggressive_learning")}
              disabled={busyId === "aggressive_learning-autopilot-preview"}
              className="rounded-xl border border-red-200 bg-red-50 px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-red-800 disabled:opacity-50"
            >
              Aggro prüfen
            </button>
            <button
              onClick={() => runAutopilot(true, "aggressive_learning")}
              disabled={busyId === "aggressive_learning-autopilot-execute"}
              className="rounded-xl bg-red-600 px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-white disabled:opacity-50"
            >
              Aggro Paper öffnen
            </button>
            <div className="rounded-full border border-black/8 bg-white/75 px-4 py-2 text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
              {stats.total_trades || 0} getrackte Trades
            </div>
          </div>
        </div>

        <div className="mt-5 grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
          <div className="rounded-[1.6rem] border border-black/8 bg-white/80 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                  Autopilot Steuerung
                </div>
                <div className="mt-1 text-sm font-bold text-slate-900">
                  Wie stark soll das Demo-Konto lernen?
                </div>
              </div>
              <button
                onClick={saveAutopilotSettings}
                disabled={busyId === "save-autopilot-settings"}
                className="rounded-xl bg-[#101114] px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-white disabled:opacity-50"
              >
                Speichern
              </button>
            </div>
            <div className={`mt-4 rounded-[1.35rem] border p-4 ${
              autopilotProfile.tone === "aggressive"
                ? "border-red-200 bg-red-50/70"
                : autopilotProfile.tone === "balanced"
                  ? "border-amber-200 bg-amber-50/70"
                  : "border-emerald-200 bg-emerald-50/70"
            }`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                    Aktives Risiko-Profil
                  </div>
                  <div className="mt-1 text-lg font-black text-slate-950">
                    {autopilotProfile.label || "Aggressive Learning"}
                  </div>
                  <div className="mt-1 max-w-2xl text-xs font-semibold leading-5 text-slate-600">
                    {autopilotProfile.description || "Paper-only: schneller lernen, ohne Echtgeld auszuführen."}
                  </div>
                </div>
                <div className="rounded-full border border-black/8 bg-white px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-700">
                  {autopilotProfile.protection_active ? "Schutz aktiv" : "Paper-only"}
                </div>
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                <div className="rounded-2xl border border-black/8 bg-white/80 p-3">
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">Score-Gate</div>
                  <div className="mt-1 text-lg font-black text-slate-950">{Number(autopilotProfile.min_score || 0).toFixed(0)}</div>
                </div>
                <div className="rounded-2xl border border-black/8 bg-white/80 p-3">
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">Risiko pro Trade</div>
                  <div className="mt-1 text-lg font-black text-slate-950">{moneyOrNA(autopilotProfile.per_trade_risk_value, currency)}</div>
                </div>
                <div className="rounded-2xl border border-black/8 bg-white/80 p-3">
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">Max. Lauf-Risiko</div>
                  <div className="mt-1 text-lg font-black text-slate-950">{moneyOrNA(autopilotProfile.planned_run_risk_value, currency)}</div>
                </div>
              </div>
              <div className="mt-3 rounded-xl border border-black/8 bg-white/70 px-3 py-2 text-xs font-semibold leading-5 text-slate-600">
                {autopilotProfile.summary || "Profil prüfen, bevor neue Paper-Trades geöffnet werden."}
              </div>
              {autopilotProfile.recommendation ? (
                <div className={`mt-2 rounded-xl border px-3 py-2 text-xs font-bold leading-5 ${
                  autopilotProfile.recommendation_tone === "block"
                    ? "border-red-200 bg-red-100/70 text-red-800"
                    : autopilotProfile.recommendation_tone === "warning"
                      ? "border-amber-200 bg-amber-100/70 text-amber-800"
                      : "border-emerald-200 bg-emerald-100/70 text-emerald-800"
                }`}>
                  Empfehlung: {autopilotProfile.recommendation}
                </div>
              ) : null}
              {Array.isArray(autopilotProfile.guardrails) && autopilotProfile.guardrails.length ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  {autopilotProfile.guardrails.slice(0, 3).map((item: string) => (
                    <span key={item} className="rounded-full border border-black/8 bg-white/80 px-3 py-1 text-[10px] font-bold text-slate-600">
                      {item}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
            <div className="mt-4 rounded-[1.45rem] border border-sky-500/20 bg-sky-50/80 p-4 text-sky-950">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-sky-700">
                    Nächster Profil-Lauf
                  </div>
                  <div className="mt-1 text-sm font-black text-slate-950">
                    {configuredRun.label}: {configuredRun.intent}
                  </div>
                </div>
                <div className="rounded-full border border-sky-200 bg-white px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-sky-800">
                  {configuredRun.count} von {configuredRun.candidates.length} Kandidaten
                </div>
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                <div className="rounded-xl border border-sky-200 bg-white/85 px-3 py-2">
                  <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-sky-700">Demo-Kapital</div>
                  <div className="mt-1 text-sm font-black text-slate-950">{money(configuredRun.notional, currency)}</div>
                </div>
                <div className="rounded-xl border border-sky-200 bg-white/85 px-3 py-2">
                  <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-sky-700">Max. Verlust</div>
                  <div className="mt-1 text-sm font-black text-slate-950">{money(configuredRun.maxLoss, currency)}</div>
                </div>
                <div className="rounded-xl border border-sky-200 bg-white/85 px-3 py-2">
                  <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-sky-700">Ausführung</div>
                  <div className="mt-1 text-sm font-black text-slate-950">Preview oder Paper + Telegram</div>
                </div>
              </div>
              {configuredRun.lead ? (
                <div className="mt-3 rounded-xl border border-sky-200 bg-white/90 px-3 py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-black text-slate-950">{configuredRun.lead.ticker || "Setup"}</span>
                        <span className="rounded-full border border-black/8 bg-slate-50 px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.12em] text-slate-600">
                          {configuredRun.lead.direction || "watch"} / Score {Number(configuredRun.lead.score || 0).toFixed(0)}
                        </span>
                      </div>
                      <div className="mt-1 line-clamp-2 text-xs font-semibold leading-5 text-slate-600">
                        Trigger: {configuredRun.lead.trigger || configuredRun.lead.thesis || "erst nach bestätigtem Signal handeln"}
                      </div>
                    </div>
                    {configuredRun.lead.ticker ? (
                      <button
                        type="button"
                        onClick={() => onAnalyze(configuredRun.lead.ticker)}
                        className="shrink-0 rounded-full border border-sky-200 bg-white px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.14em] text-sky-800"
                      >
                        Dossier prüfen
                      </button>
                    ) : null}
                  </div>
                </div>
              ) : (
                <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-bold leading-5 text-amber-800">
                  Kein Kandidat erfüllt dieses Profil. Erst Preview nutzen oder Score/Risiko bewusst anpassen.
                </div>
              )}
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <label className="block rounded-2xl border border-black/8 bg-slate-50 p-3">
                <span className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">Profil</span>
                <select
                  value={autopilotSettings?.mode || "aggressive_learning"}
                  onChange={(event) => updateAutopilotSetting("mode", event.target.value)}
                  className="mt-2 w-full rounded-xl border border-black/8 bg-white px-3 py-2 text-sm font-bold text-slate-900"
                >
                  <option value="strict">Strict: nur Top-Setups</option>
                  <option value="learn">Learn: mehr Tests, klein</option>
                  <option value="aggressive_learning">Aggressive Learning: schneller lernen</option>
                </select>
              </label>
              <label className="block rounded-2xl border border-black/8 bg-slate-50 p-3">
                <span className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">Max. Trades pro Lauf</span>
                <input
                  type="range"
                  min={1}
                  max={8}
                  value={Number(autopilotSettings?.max_trades || 3)}
                  onChange={(event) => updateAutopilotSetting("max_trades", Number(event.target.value))}
                  className="mt-3 w-full"
                />
                <div className="mt-1 text-sm font-black text-slate-900">{Number(autopilotSettings?.max_trades || 3)} Paper-Trades</div>
              </label>
              <label className="block rounded-2xl border border-black/8 bg-slate-50 p-3">
                <span className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">Aggro Mindestscore</span>
                <input
                  type="range"
                  min={35}
                  max={90}
                  value={Number(autopilotSettings?.aggressive_min_score || autoSelection.aggressive_learning_min_score || 52)}
                  onChange={(event) => updateAutopilotSetting("aggressive_min_score", Number(event.target.value))}
                  className="mt-3 w-full"
                />
                <div className="mt-1 text-sm font-black text-slate-900">{Number(autopilotSettings?.aggressive_min_score || 52).toFixed(0)} Score</div>
              </label>
              <label className="block rounded-2xl border border-black/8 bg-slate-50 p-3">
                <span className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">Aggro Risiko-Größe</span>
                <input
                  type="range"
                  min={3}
                  max={65}
                  value={Math.round(Number(autopilotSettings?.aggressive_risk_multiplier || autoSelection.aggressive_learning_risk_multiplier || 0.25) * 100)}
                  onChange={(event) => updateAutopilotSetting("aggressive_risk_multiplier", Number(event.target.value) / 100)}
                  className="mt-3 w-full"
                />
                <div className="mt-1 text-sm font-black text-slate-900">
                  {Math.round(Number(autopilotSettings?.aggressive_risk_multiplier || 0.25) * 100)}% der normalen Paper-Größe
                </div>
              </label>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                onClick={() => runConfiguredAutopilot(false)}
                disabled={busyId?.includes("autopilot-preview")}
                className="rounded-xl border border-black/8 bg-white px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-700 disabled:opacity-50"
              >
                Profil prüfen
              </button>
              <button
                onClick={() => runConfiguredAutopilot(true)}
                disabled={busyId?.includes("autopilot-execute")}
                className="rounded-xl bg-[var(--accent)] px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-white disabled:opacity-50"
              >
                Profil Paper traden
              </button>
            </div>
          </div>

          <div className="rounded-[1.6rem] border border-emerald-500/15 bg-emerald-50/55 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-emerald-700">
                  Gerade interessant
                </div>
                <div className="mt-1 text-sm font-bold text-slate-900">
                  Vorschlaege aus Strict, Learn und Aggro-Pool
                </div>
              </div>
              <div className="rounded-full border border-emerald-200 bg-white px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-emerald-800">
                {interestingNow.length} Ideen
              </div>
            </div>
            <div className="mt-4 grid gap-2 sm:grid-cols-2">
              {interestingNow.length ? (
                interestingNow.map((item: any) => (
                  <button
                    key={`${item.ticker}-${item.source || item.setup_type || "idea"}`}
                    onClick={() => onAnalyze(item.ticker)}
                    className="rounded-2xl border border-black/8 bg-white/85 p-3 text-left transition hover:border-emerald-300 hover:bg-white"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="font-black text-slate-950">{item.ticker}</div>
                      <div className="rounded-full border border-black/8 bg-slate-50 px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.12em] text-slate-600">
                        Score {Number(item.score || 0).toFixed(0)}
                      </div>
                    </div>
                    <div className="mt-1 text-xs font-bold uppercase tracking-[0.12em] text-emerald-700">
                      {item.source || "watch"} / {item.direction || "watch"}
                    </div>
                    <div className="mt-2 line-clamp-2 text-xs leading-5 text-slate-600">
                      {item.trigger || item.title || "Analyse öffnen und Trigger prüfen."}
                    </div>
                  </button>
                ))
              ) : (
                <div className="rounded-2xl border border-dashed border-emerald-300 bg-white/70 p-4 text-sm font-semibold text-slate-600 sm:col-span-2">
                  Noch keine saubere Idee. Erst Daten, Trigger und Risiko bestätigen lassen.
                </div>
              )}
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
                Demo-Konto startet mit {money(capitalFlow.starting_capital_value ?? demoAccount.starting_capital ?? DEFAULT_DEMO_CAPITAL, currency)}.
                Aktuell sind {money(capitalFlow.open_exposure_value ?? demoAccount.open_exposure_value, currency)} investiert und{" "}
                {money(capitalFlow.cash_available_value ?? demoAccount.cash_available_value, currency)} frei. Ergebnis seit Start:{" "}
                <span className={`font-black ${Number(capitalFlow.net_pnl_value ?? demoAccount.net_pnl_value ?? 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                  {money(capitalFlow.net_pnl_value ?? demoAccount.net_pnl_value, currency)} / {formatPct(capitalFlow.net_pnl_pct ?? demoAccount.net_pnl_pct, 2, "0.00%")}
                </span>
                .
              </div>
              <div className="mt-2 text-xs font-semibold leading-5 text-slate-500">
                Realisiert: {money(capitalFlow.realized_pnl_value ?? demoAccount.realized_pnl_value, currency)} · Offen:
                {" "}{money(capitalFlow.unrealized_pnl_value ?? demoAccount.unrealized_pnl_value, currency)}
              </div>
              <div className="mt-3 rounded-[1rem] border border-black/8 bg-slate-50 px-3 py-2 text-sm font-semibold leading-6 text-slate-700">
                Heute: {demoAccount.day_action || "Auf ein klares Setup mit Trigger warten."}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <div className={`rounded-full px-3 py-1 text-[11px] font-extrabold uppercase tracking-[0.16em] ${
                (capitalFlow.capital_status || demoAccount.capital_status) === "ahead"
                  ? "bg-emerald-50 text-emerald-700"
                  : (capitalFlow.capital_status || demoAccount.capital_status) === "behind"
                    ? "bg-red-50 text-red-700"
                    : "border border-black/8 bg-white text-slate-500"
              }`}>
                {germanStatus(capitalFlow.capital_status || demoAccount.capital_status, "neutral")}
              </div>
              <div className={`rounded-full px-3 py-1 text-[11px] font-extrabold uppercase tracking-[0.16em] ${
                demoAccount.day_status === "action_required" || demoAccount.day_status === "risk_halt"
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
            <StatTile label="Startkapital" value={money(capitalFlow.starting_capital_value ?? demoAccount.starting_capital ?? DEFAULT_DEMO_CAPITAL, currency)} />
            <StatTile label="Jetzt investiert" value={money(capitalFlow.open_exposure_value ?? demoAccount.open_exposure_value, currency)} />
            <StatTile label="Realisiert" value={money(capitalFlow.realized_pnl_value ?? demoAccount.realized_pnl_value, currency)} tone={(Number(capitalFlow.realized_pnl_value ?? demoAccount.realized_pnl_value ?? 0) > 0 ? "good" : Number(capitalFlow.realized_pnl_value ?? demoAccount.realized_pnl_value ?? 0) < 0 ? "bad" : "default") as any} />
            <StatTile label="Netto-Ergebnis" value={`${money(capitalFlow.net_pnl_value ?? demoAccount.net_pnl_value, currency)} / ${formatPct(capitalFlow.net_pnl_pct ?? demoAccount.net_pnl_pct, 2, "0.00%")}`} tone={accountTone as any} />
          </div>
          <div data-testid="execution-cost-calibration" className="mt-4 rounded-[1.4rem] border border-sky-200 bg-sky-50/65 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-sky-700">Spread-, Slippage- und Gebührenkalibrierung</div>
                <div className="mt-1 text-sm font-semibold leading-6 text-sky-950">
                  Rollierende {executionCostCalibration.lookback_days || 90} Tage · mindestens die halbe beobachtete Bid/Ask-Spanne je Seite · Gebühren separat im Fill berücksichtigt.
                </div>
              </div>
              <div className="rounded-full border border-sky-200 bg-white px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-sky-800">
                {executionCostCalibration.calibrated_asset_classes || 0} / {executionCostRows.length || 4} kalibriert
              </div>
            </div>
            <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
              {executionCostRows.map((row: any) => (
                <div key={row.asset_class} className="rounded-2xl border border-sky-200 bg-white/85 p-3 text-xs text-sky-950">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-extrabold uppercase tracking-[0.13em]">{row.asset_class}</div>
                    <span className={`rounded-full px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.1em] ${row.status === "calibrated" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
                      {row.status === "calibrated" ? "kalibriert" : "vorläufig"}
                    </span>
                  </div>
                  <div className="mt-2 font-semibold leading-5">
                    Spread-Median {row.median_observed_spread_pct != null ? `${Number(row.median_observed_spread_pct).toFixed(2)}%` : "noch keine Quote"}
                  </div>
                  <div className="text-sky-700">
                    Slippage {row.median_slippage_bps ?? row.policy_fallback_bps ?? "?"} bps · Gebühren {row.median_fee_bps ?? "Policy"} bps
                  </div>
                  <div className="mt-1 text-[10px] font-bold text-sky-600">
                    {row.spread_samples || 0}/{row.minimum_spread_samples || 5} Spread-Beobachtungen
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-3 text-[10px] font-semibold leading-5 text-sky-700">
              Modell {executionCostCalibration.model_version || "spread_calibration_v1"} · ohne ausreichende Stichprobe gilt weiterhin der konservative Assetklassen-Fallback.
            </div>
          </div>
          <div className="mt-4 rounded-[1.4rem] border border-black/8 bg-white/90 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                  Trader-Konto auf einen Blick
                </div>
                <div className="mt-1 text-sm font-semibold leading-6 text-slate-700">
                  {germanStatus(exposureProfile.net_direction, "ausgeglichen")} mit {exposureProfile.open_trade_count || 0} offenen Trades.
                  Hebel/Options-Paper bindet {money(exposureProfile.leveraged_notional_value, currency)}.
                </div>
              </div>
              <div className={`rounded-full px-3 py-1 text-[11px] font-extrabold uppercase tracking-[0.16em] ${
                Number(exposureProfile.open_pnl_value || 0) >= 0
                  ? "bg-emerald-50 text-emerald-700"
                  : "bg-red-50 text-red-700"
              }`}>
                offen {money(exposureProfile.open_pnl_value, currency)}
              </div>
            </div>
            <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
              {exposureBuckets.map((bucket: any) => (
                <div key={bucket.key} className="rounded-2xl border border-black/8 bg-slate-50/80 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">{bucket.label}</div>
                    <div className="rounded-full border border-black/8 bg-white px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.12em] text-slate-500">
                      {bucket.count || 0}
                    </div>
                  </div>
                  <div className="mt-2 text-lg font-black text-slate-950">{money(bucket.notional_value, currency)}</div>
                  <div className={`mt-1 text-xs font-bold ${Number(bucket.pnl_value || 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                    P/L {money(bucket.pnl_value, currency)} / {formatPct(bucket.pnl_pct_of_notional, 2, "0.00%")}
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-3 rounded-xl border border-black/8 bg-slate-50 px-3 py-2 text-xs font-semibold leading-5 text-slate-600">
              Groesstes Einzelrisiko:{" "}
              <span className="font-extrabold text-slate-900">
                {exposureProfile.biggest_open_risk?.ticker || "kein Trade"}
              </span>{" "}
              {exposureProfile.biggest_open_risk?.direction ? `/${String(exposureProfile.biggest_open_risk.direction).toUpperCase()}` : ""} / Risiko{" "}
              {money(exposureProfile.biggest_open_risk?.risk_value, currency)} / Kapital{" "}
              {money(exposureProfile.biggest_open_risk?.notional_value, currency)}
            </div>
          </div>
          <div className="mt-4 rounded-[1.4rem] border border-black/8 bg-white/90 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                  Was jetzt zuerst prüfen?
                </div>
                <div className="mt-1 text-sm font-semibold leading-6 text-slate-700">
                  {tradeActionQueue.message || "Keine offenen Paper-Trades. Erst neues Setup mit Trigger und Risiko prüfen."}
                </div>
              </div>
              <div className={`rounded-full px-3 py-1 text-[11px] font-extrabold uppercase tracking-[0.16em] ${
                tradeActionQueue.status === "exit"
                  ? "bg-red-50 text-red-700"
                  : tradeActionQueue.status === "review"
                    ? "bg-amber-50 text-amber-700"
                    : tradeActionQueue.status === "protect"
                      ? "bg-emerald-50 text-emerald-700"
                      : "border border-black/8 bg-slate-50 text-slate-600"
              }`}>
                {germanStatus(tradeActionQueue.status, "bereit")}
              </div>
            </div>
            {tradeActionItems.length ? (
              <div className="mt-4 grid gap-2 lg:grid-cols-2">
                {tradeActionItems.slice(0, 4).map((item: any) => (
                  <button
                    key={item.id || `${item.ticker}-${item.direction}`}
                    onClick={() => item.ticker && onAnalyze(item.ticker)}
                    className="rounded-2xl border border-black/8 bg-slate-50/80 p-3 text-left transition hover:border-[var(--accent)]/30 hover:bg-white"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-black text-slate-950">
                          {item.ticker} / {String(item.direction || "").toUpperCase()}
                        </div>
                        <div className="mt-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                          {item.priority_label} / {germanStatus(item.management_status, "monitor")}
                        </div>
                      </div>
                      <div className={`rounded-full px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.12em] ${
                        Number(item.unrealized_pnl_value || 0) >= 0 ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"
                      }`}>
                        {money(item.unrealized_pnl_value, currency)}
                      </div>
                    </div>
                    <div className="mt-2 line-clamp-2 text-xs font-semibold leading-5 text-slate-600">
                      {germanText(item.summary, "Paper-Plan prüfen.")}
                    </div>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          <div className={`mt-4 rounded-[1.4rem] border p-4 ${
            riskCircuit.active
              ? "border-red-200 bg-red-50/90 text-red-900"
              : riskCircuit.status === "reduced_risk"
                ? "border-amber-200 bg-amber-50/90 text-amber-900"
                : "border-emerald-200 bg-emerald-50/70 text-emerald-900"
          }`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] opacity-70">Risk Circuit</div>
                <div className="mt-1 text-base font-black">
                  {riskCircuit.active
                    ? "Neue Paper-Entries pausiert"
                    : riskCircuit.status === "reduced_risk"
                      ? "Drawdown-Modus: nur 25 % Risiko"
                      : "Risikobudget freigegeben"}
                </div>
                {(riskCircuit.display_reasons || riskCircuit.reasons)?.length ? (
                  <div className="mt-2 text-sm font-semibold leading-6">{(riskCircuit.display_reasons || riskCircuit.reasons).join(" / ")}</div>
                ) : null}
              </div>
              <div className="rounded-full border border-current/15 bg-white/60 px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em]">
                {germanStatus(riskCircuit.status, "bereit")}
              </div>
            </div>
            <div className="mt-4 grid gap-2 text-xs font-semibold sm:grid-cols-2 xl:grid-cols-4">
              <div>Heute {money(riskCircuit.daily_realized_pnl_value, currency)} / Limit -{money(riskCircuit.daily_loss_limit_value, currency)}</div>
              <div>Drawdown {unsignedPct(riskCircuit.current_drawdown_pct, 2, "0.00%")} / Limit {unsignedPct(riskCircuit.drawdown_limit_pct, 2, "0.00%")}</div>
              <div>Verlustserie {riskCircuit.consecutive_losses || 0} / {riskCircuit.max_consecutive_losses || 0}</div>
              <div>
                {riskCircuit.cooldown_until
                  ? `Pause bis ${new Date(riskCircuit.cooldown_until).toLocaleString("de-DE")}`
                  : `Risiko-Faktor ${Math.round(Number(riskCircuit.risk_multiplier || 1) * 100)}%`}
              </div>
            </div>
          </div>
          <div className="mt-4 rounded-[1.4rem] border border-black/8 bg-slate-50/80 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                  Kapitalaufteilung
                </div>
                <div className="mt-1 text-sm font-semibold text-slate-700">
                  {formatPct(demoAccount.open_exposure_pct, 2, "0.00%")} vom Konto investiert ·{" "}
                  {formatPct(grossExposureUsagePct, 1, "0.0%")} des Exposure-Limits genutzt ·{" "}
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
                style={{ width: `${clampPct(grossExposureUsagePct)}%` }}
              />
            </div>
            <div className="mt-3 grid gap-2 text-xs font-semibold text-slate-600 sm:grid-cols-2 xl:grid-cols-4">
              <div>
                <span className="font-extrabold text-slate-900">{money(demoAccount.open_exposure_value, currency)}</span>
                {" "}von {money(demoAccount.max_gross_exposure_value, currency)} Exposure
              </div>
              <div>
                <span className="font-extrabold text-slate-900">{money(demoAccount.cash_available_value, currency)}</span>
                {" "}frei
              </div>
              <div>
                <span className="font-extrabold text-slate-900">{money(demoAccount.remaining_risk_value, currency)}</span>
                {" "}Risikobudget frei
              </div>
              <div>
                <span className="font-extrabold text-slate-900">
                  {demoAccount.top_ticker_exposure?.ticker || "Kein Ticker"}
                </span>
                {" "}{money(demoAccount.top_ticker_exposure?.value, currency)} / Optionen {money(demoAccount.option_premium_exposure_value, currency)}
              </div>
            </div>
            <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
              {assetClassLimits.map(([assetClass, limit]: [string, any]) => (
                <div
                  key={assetClass}
                  className={`rounded-xl border px-3 py-2 text-xs ${
                    limit.over_limit ? "border-red-200 bg-red-50 text-red-800" : "border-black/8 bg-white text-slate-700"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 font-extrabold uppercase tracking-[0.12em]">
                    <span>{assetClass}</span>
                    <span>{Number(limit.used_pct || 0).toFixed(1)} / {Number(limit.limit_pct || 0).toFixed(0)}%</span>
                  </div>
                  <div className="mt-1">Frei: {money(limit.remaining_value, currency)}</div>
                  {limit.over_limit ? <div className="mt-1 font-bold">Über Limit · keine neue Position</div> : null}
                </div>
              ))}
            </div>
            <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              Cashreserve: {money(demoAccount.cash_available_value, currency)} vorhanden · Ziel {money(demoAccount.cash_reserve_target_value, currency)}
              {Number(demoAccount.cash_reserve_gap_value || 0) > 0
                ? ` · ${money(demoAccount.cash_reserve_gap_value, currency)} fehlen bis zur Reserve`
                : " · Reserve erfüllt"}
            </div>
          </div>
          <div className="mt-4 rounded-[1.4rem] border border-black/8 bg-white/90 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                  Naechste Paper-Entscheidung
                </div>
                {nextPaperDecision ? (
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <span className="text-lg font-black text-slate-900">
                      {nextPaperDecision.ticker || "Setup"} / {String(nextPaperDecision.direction || "long").toUpperCase()}
                    </span>
                    <span className="rounded-full border border-black/8 bg-slate-50 px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-600">
                      Score {nextPaperDecision.score ?? "offen"}
                    </span>
                    <span
                      className={`rounded-full px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] ${
                        nextPaperDecisionMode === "strict"
                          ? "bg-emerald-50 text-emerald-700"
                          : nextPaperDecisionMode === "learning"
                            ? "bg-amber-50 text-amber-700"
                            : "bg-red-50 text-red-700"
                      }`}
                    >
                      {nextPaperDecisionMode === "strict"
                        ? "Paper kaufbar"
                        : nextPaperDecisionMode === "learning"
                          ? "nur Lerntrade"
                          : "noch blockiert"}
                    </span>
                    {nextPaperDecision.blocker_label ? (
                      <span className="rounded-full border border-red-200 bg-white px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-red-700">
                        {nextPaperDecision.blocker_label}
                      </span>
                    ) : null}
                  </div>
                ) : (
                  <div className="mt-2 text-sm font-semibold text-slate-700">
                    Kein valides Setup. Erst auf Signal, Trigger, Invalidierung und freies Risiko warten.
                  </div>
                )}
              </div>
              {nextPaperDecision?.ticker ? (
                <button
                  onClick={() => onAnalyze(nextPaperDecision.ticker)}
                  className="rounded-xl border border-black/8 bg-white px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-700 transition hover:border-[var(--accent)]/30 hover:bg-[var(--accent-soft)]/35"
                >
                  Analyse öffnen
                </button>
              ) : null}
            </div>
            {nextPaperDecision ? (
              <div className="mt-4 grid gap-3 lg:grid-cols-3">
                <div className="rounded-xl border border-black/8 bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-700">
                  <div className="font-extrabold uppercase tracking-[0.14em] text-slate-500">Geld / Risiko</div>
                  <div className="mt-1 font-semibold">
                    Position {money(nextPaperDecision.suggested_notional_value, currency)} / max. Verlust{" "}
                    {money(nextPaperDecision.suggested_max_loss_value, currency)}
                  </div>
                </div>
                <div className="rounded-xl border border-black/8 bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-700">
                  <div className="font-extrabold uppercase tracking-[0.14em] text-slate-500">Trigger</div>
                  <div className="mt-1 font-semibold">
                    {nextPaperDecision.trigger || nextPaperDecision.decision_framework?.entry_trigger || "Noch keine saubere Bestätigung."}
                  </div>
                </div>
                <div className="rounded-xl border border-black/8 bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-700">
                  <div className="font-extrabold uppercase tracking-[0.14em] text-slate-500">Invalidierung</div>
                  <div className="mt-1 font-semibold">
                    {nextPaperDecision.invalidation || nextPaperDecision.decision_framework?.invalidation || "Stop, These oder Newsqualitaet muss vor Einstieg klar sein."}
                  </div>
                </div>
              </div>
            ) : null}
            {nextPaperDecisionMode === "blocked" && nextPaperDecision ? (
              <div className="mt-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold leading-5 text-red-800">
                Kein Kauf: {(nextPaperDecision.display_reasons || nextPaperDecision.reasons || ["Quality-Gate noch nicht erfüllt"]).slice(0, 3).join(" / ")}.
                {nextPaperDecision.missing_to_trade ? (
                  <span className="block pt-1 text-red-900">Fehlt bis Paper-Kauf: {nextPaperDecision.missing_to_trade}.</span>
                ) : null}
                {Number(nextPaperDecision.auto_score_gap || 0) > 0 ? (
                  <span className="block pt-1 text-red-900">
                    Score-Luecke: {Number(nextPaperDecision.auto_score_gap).toFixed(1)} Punkte bis Strict-Trade
                    {Number(nextPaperDecision.learning_score_gap || 0) > 0
                      ? ` / ${Number(nextPaperDecision.learning_score_gap).toFixed(1)} Punkte bis Lerntrade`
                      : " / Lernscore erreicht"}
                    .
                  </span>
                ) : null}
                {nextPaperDecision.learning_block_display_reasons?.length ? (
                  <span className="block pt-1 text-red-900">
                    Warum kein Lerntrade: {nextPaperDecision.learning_block_display_reasons.slice(0, 2).join(" / ")}.
                  </span>
                ) : null}
                {nextPaperDecision.next_action ? (
                  <span className="block pt-1 text-red-900">Naechster Schritt: {nextPaperDecision.next_action}</span>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>

        <div className="mt-4 rounded-[1.8rem] border border-black/8 bg-white/75 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                Offene Paper-Positionen
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
            <div className="mt-4 grid gap-3 xl:grid-cols-2">
              {activePaperDecisions.map((trade: any) => {
                const management = trade.management_plan || {};
                const pnlValue = Number(trade.result_value_delta || 0);
                const entryExecution = trade.trade_ticket?.execution_model?.entry || null;
                const exitExecution = trade.estimated_exit_execution || null;
                const newsEvidence = trade.trade_ticket?.news_evidence || null;
                const entryRegime = trade.trade_ticket?.entry_market_regime || null;
                return (
                  <div
                    key={`decision-${trade.id}`}
                    className="rounded-[1.2rem] border border-black/8 bg-white px-4 py-3"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-sm font-black text-slate-900">
                          {trade.ticker} / {String(trade.direction || "").toUpperCase()}
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                          <span>{trade.setup_type || "paper setup"}</span>
                          <span className="rounded-full border border-black/8 bg-slate-50 px-2 py-0.5 text-[9px] tracking-[0.12em]">
                            {entrySourceLabel(trade)}
                          </span>
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
                    <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-600 sm:grid-cols-3">
                      <div>
                        <div className="font-extrabold uppercase tracking-[0.12em] text-slate-400">Investiert</div>
                        <div className="mt-1 font-bold text-slate-900">{moneyOrNA(trade.invested_value, currency)}</div>
                      </div>
                      <div>
                        <div className="font-extrabold uppercase tracking-[0.12em] text-slate-400">Aktueller Wert</div>
                        <div className="mt-1 font-bold text-slate-900">{moneyOrNA(trade.current_value, currency)}</div>
                      </div>
                      <div>
                        <div className="font-extrabold uppercase tracking-[0.12em] text-slate-400">Offene P/L</div>
                        <div className={`mt-1 font-bold ${pnlValue >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                          {formatPct(trade.unrealized_pnl_pct, 2, "0.00%")}
                        </div>
                      </div>
                    </div>
                    {entryExecution ? (
                      <div className="mt-3 rounded-xl border border-sky-200 bg-sky-50/70 px-3 py-2 text-[11px] font-semibold leading-5 text-sky-900">
                        <span className="font-extrabold">Ausführung:</span>{" "}
                        Referenz {priceOrNA(entryExecution.reference_price)} → Fill {priceOrNA(entryExecution.fill_price)} ·{" "}
                        {entryExecution.cost_bps ?? "?"} bps gesamt · Slippage {entryExecution.slippage_bps ?? "?"} bps · Gebühren {entryExecution.fee_equivalent_bps ?? "?"} bps · Einstiegskosten {moneyOrNA(entryExecution.estimated_cost_value, currency)}
                        {exitExecution ? (
                          <span className="block text-sky-800">
                            Verkauf jetzt geschätzt: Referenz {priceOrNA(exitExecution.reference_price)} → Fill {priceOrNA(exitExecution.fill_price)}
                          </span>
                        ) : null}
                      </div>
                    ) : null}
                    {newsEvidence ? (
                      <div className="mt-3 rounded-xl border border-violet-200 bg-violet-50/80 px-3 py-3 text-[11px] leading-5 text-violet-950">
                        <div className="flex flex-wrap items-center gap-2 font-extrabold uppercase tracking-[0.12em] text-violet-700">
                          <span>News-Evidenz beim Entry</span>
                          <span className="rounded-full border border-violet-200 bg-white px-2 py-0.5">
                            {newsEvidence.market_confirmation?.status || "offen"}
                          </span>
                          {newsEvidence.original_document_verified ? (
                            <span className="rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-blue-700">Primärdokument</span>
                          ) : null}
                        </div>
                        <a
                          href={newsEvidence.source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-1 block font-bold underline-offset-4 hover:underline"
                        >
                          {newsEvidence.publisher || "Tier-1-Quelle"} · {newsEvidence.title}
                        </a>
                        <div className="mt-1 text-violet-800">
                          Relative Reaktion {newsEvidence.market_confirmation?.relative_move_since_publication ?? "?"}% · Faktenbasis {newsEvidence.fact_basis || "offen"} · Kausalität nicht bewiesen
                        </div>
                        {trade.trade_ticket?.max_holding_days ? (
                          <div className="mt-1 font-bold text-violet-700">
                            Event-Fenster maximal {trade.trade_ticket.max_holding_days} Tage
                            {management.elapsed_hours != null ? ` · bisher ${Number(management.elapsed_hours).toFixed(1)} Stunden` : ""}
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                    {entryRegime ? (
                      <div className="mt-3 rounded-xl border border-cyan-200 bg-cyan-50/80 px-3 py-3 text-[11px] leading-5 text-cyan-950">
                        <div className="font-extrabold uppercase tracking-[0.12em] text-cyan-700">Marktregime beim Entry · eingefroren</div>
                        <div className="mt-1 font-bold">
                          {entryRegime.risk_appetite?.label || "unbekannt"} · Trend {entryRegime.trend?.label || "unbekannt"} · Volatilität {entryRegime.volatility?.label || "unbekannt"} (Proxy)
                        </div>
                        <div className="text-cyan-800">
                          Breite {entryRegime.breadth?.label || "unbekannt"} (Proxy) · US10Y {entryRegime.rates?.label || "unbekannt"} · Dollar {entryRegime.dollar?.label || "unbekannt"}
                        </div>
                        <div className="text-cyan-700">
                          Stand {entryRegime.data_as_of ? new Date(entryRegime.data_as_of).toLocaleString() : "nicht verfügbar"} · Qualität {entryRegime.quality?.status || "partial"}
                        </div>
                      </div>
                    ) : null}
                    <div className="mt-3 flex flex-wrap gap-2 text-[11px] font-bold text-slate-600">
                      <span className="rounded-full border border-black/8 bg-slate-50 px-3 py-1">Einstieg {trade.entry_price ?? "N/A"}</span>
                      <span className="rounded-full border border-black/8 bg-slate-50 px-3 py-1">Kurs {trade.current_price ?? "N/A"}</span>
                      <span className="rounded-full border border-red-200 bg-red-50 px-3 py-1 text-red-700">Stop {trade.stop_price ?? "N/A"}</span>
                      <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-emerald-700">Ziel {trade.target_price ?? "N/A"}</span>
                      <span className="rounded-full border border-black/8 bg-slate-50 px-3 py-1">Hebel {trade.leverage ?? 1}x</span>
                      <span className="rounded-full border border-black/8 bg-slate-50 px-3 py-1">CRV {trade.risk_reward || "N/A"}</span>
                      {management.risk_distance_pct != null ? (
                        <span className="rounded-full border border-black/8 bg-slate-50 px-3 py-1">
                          Stop-Abstand {formatPct(management.risk_distance_pct, 2, "0.00%")}
                        </span>
                      ) : null}
                      {management.target_progress_pct != null ? (
                        <span className="rounded-full border border-black/8 bg-slate-50 px-3 py-1">
                          Ziel-Fortschritt {Number(management.target_progress_pct).toFixed(1)}%
                        </span>
                      ) : null}
                    </div>
                    <div className="mt-3 rounded-xl border border-black/8 bg-slate-50 px-3 py-2 text-xs font-semibold leading-5 text-slate-600">
                      {germanText(management.summary, "Paper-Position halten, solange der Trigger gültig bleibt.")}
                    </div>
                    <div className="mt-2 text-xs font-bold leading-5 text-slate-700">
                      Nächste Prüfung: {germanText(management.next_check, "Trigger, Stop und Ziel erneut prüfen, bevor der Plan geändert wird.")}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        onClick={() => trade.ticker && onAnalyze(trade.ticker)}
                        className="rounded-xl border border-black/8 bg-white px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-700"
                      >
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
              {autoSelection.selected?.length || 0} streng / {autoSelection.exploration?.length || 0} lernen / {autoSelection.aggressive_exploration?.length || 0} aggro
            </div>
          </div>
          <div className="mt-3 rounded-[1rem] border border-black/8 bg-white/70 px-3 py-2 text-slate-600">
            <span className="font-extrabold uppercase tracking-[0.14em] text-slate-500">Geplanter Lernlauf:</span>{" "}
            <span className="font-bold text-slate-800">{germanStatus(autoLearnStatus.status, "noch nicht gestartet")}</span>
            {autoLearnStatus.opened?.length ? ` · geöffnet ${autoLearnStatus.opened.length}` : ""}
            {autoLearnStatus.next_allowed_at ? ` · nächster Lauf ${new Date(autoLearnStatus.next_allowed_at).toLocaleString()}` : ""}
            {autoLearnStatus.message ? ` · ${autoLearnStatus.message}` : ""}
          </div>
          {newsGateMonitor.status ? (
            <div className={`mt-3 rounded-[1.1rem] border p-3 ${
              newsGateMonitor.status === "ready"
                ? "border-emerald-500/20 bg-emerald-50/80 text-emerald-950"
                : newsGateMonitor.status === "account_blocked"
                  ? "border-red-500/20 bg-red-50/80 text-red-950"
                  : "border-violet-500/20 bg-violet-50/80 text-violet-950"
            }`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="font-extrabold uppercase tracking-[0.18em]">News-Entry-Gate Monitor</div>
                  <div className="mt-1 font-semibold leading-5">{newsGateMonitor.message}</div>
                  {newsGateMonitor.brief_generated_at ? (
                    <div className="mt-1 text-[10px] font-bold uppercase tracking-[0.12em] opacity-70">
                      Brief-Stand {new Date(newsGateMonitor.brief_generated_at).toLocaleString()}
                    </div>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-2 text-[10px] font-extrabold uppercase tracking-[0.12em]">
                  <span className="rounded-full border border-current/15 bg-white/80 px-2.5 py-1">
                    {newsGateMonitor.checked_count || 0} geprüft
                  </span>
                  <span className="rounded-full border border-current/15 bg-white/80 px-2.5 py-1">
                    {newsGateMonitor.eligible_count || 0} News-Gate
                  </span>
                  <span className="rounded-full border border-current/15 bg-white/80 px-2.5 py-1">
                    {newsGateMonitor.autopilot_qualified_count || 0} Auto-qualifiziert
                  </span>
                </div>
              </div>
              {newsGateMonitor.account_blocked ? (
                <div className="mt-3 rounded-xl border border-red-300 bg-white/80 px-3 py-2 font-bold text-red-800">
                  Konto-Gate blockiert · Status {germanStatus(newsGateMonitor.account_day_status, "prüfen")}. Erst Risiko-Review abschließen; keine neue Exposure.
                </div>
              ) : null}
              {newsGateMonitor.top_reasons?.length ? (
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  {newsGateMonitor.top_reasons.slice(0, 4).map((item: any) => (
                    <div key={item.reason} className="rounded-xl border border-current/10 bg-white/75 px-3 py-2">
                      <span className="font-black">{item.count}×</span> {item.display_reason}
                    </div>
                  ))}
                </div>
              ) : null}
              {newsGateMonitor.next_best_rejected ? (
                <div className="mt-3 rounded-xl border border-current/10 bg-white/80 px-3 py-3">
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] opacity-70">Nächste beinahe qualifizierte Meldung</div>
                  {newsGateMonitor.next_best_rejected.source_url ? (
                    <a
                      href={newsGateMonitor.next_best_rejected.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-1 block font-black underline-offset-4 hover:underline"
                    >
                      {newsGateMonitor.next_best_rejected.ticker ? `${newsGateMonitor.next_best_rejected.ticker} · ` : ""}
                      {newsGateMonitor.next_best_rejected.publisher || "Quelle"} · {newsGateMonitor.next_best_rejected.title}
                    </a>
                  ) : (
                    <div className="mt-1 font-black">{newsGateMonitor.next_best_rejected.title}</div>
                  )}
                  <div className="mt-1 font-semibold opacity-80">
                    Fehlt: {(newsGateMonitor.next_best_rejected.display_reasons || []).join(" · ")}
                  </div>
                </div>
              ) : null}
              <div className="mt-2 text-[10px] font-bold uppercase tracking-[0.12em] opacity-65">
                Diagnose-only · eröffnet selbst keinen Trade · Echtgeld gesperrt
              </div>
            </div>
          ) : null}
          {lastAutopilotResult ? (
            <div className="mt-3 rounded-[1.1rem] border border-sky-500/20 bg-sky-50/80 p-3 text-sky-900">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="font-extrabold uppercase tracking-[0.18em] text-sky-700">
                    Letzter Autopilot-Check
                  </div>
                  <div className="mt-1 font-semibold leading-5">
                    {lastAutopilotResult.message || "Autopilot-Check abgeschlossen."}
                  </div>
                </div>
                <div className="rounded-full border border-sky-200 bg-white px-3 py-1 font-extrabold uppercase tracking-[0.12em] text-sky-800">
                  {lastAutopilotResult.mode || "strict"} / {lastAutopilotResult.execute ? "execute" : "preview"}
                </div>
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                <div className="rounded-xl border border-sky-200 bg-white/80 px-3 py-2">
                  <div className="font-black text-slate-900">{lastAutopilotResult.selected_capital?.count ?? lastAutopilotResult.selected?.length ?? 0}</div>
                  <div className="text-sky-700">Kandidaten</div>
                </div>
                <div className="rounded-xl border border-sky-200 bg-white/80 px-3 py-2">
                  <div className="font-black text-slate-900">{money(lastAutopilotResult.selected_capital?.notional_value, currency)}</div>
                  <div className="text-sky-700">Demo-Kapital</div>
                </div>
                <div className="rounded-xl border border-sky-200 bg-white/80 px-3 py-2">
                  <div className="font-black text-slate-900">{money(lastAutopilotResult.selected_capital?.max_loss_value, currency)}</div>
                  <div className="text-sky-700">max. Paper-Risiko</div>
                </div>
              </div>
              {lastAutopilotFocus ? (
                <div className="mt-3 rounded-xl border border-sky-200 bg-white/85 px-3 py-3">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-sky-700">
                        Nächster Fokus
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-sm font-black text-slate-950">
                        <span>{lastAutopilotFocus.ticker || "Setup"}</span>
                        {lastAutopilotFocus.score != null ? (
                          <span className="rounded-full border border-black/8 bg-slate-50 px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.12em] text-slate-600">
                            Score {Number(lastAutopilotFocus.score).toFixed(0)}
                          </span>
                        ) : null}
                        {lastAutopilotBlocked ? (
                          <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.12em] text-amber-800">
                            geblockt
                          </span>
                        ) : (
                          <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.12em] text-emerald-800">
                            kaufbar im Paper-Gate
                          </span>
                        )}
                      </div>
                      {lastAutopilotBlocked ? (
                        <div className="mt-1 text-xs font-semibold leading-5 text-slate-600">
                          {lastAutopilotReasons.length ? `Blocker: ${lastAutopilotReasons.join(" / ")}.` : "Blocker: Gate noch nicht sauber."}
                          {Number(lastAutopilotBlocked.auto_score_gap || 0) > 0
                            ? ` Fehlt: ${Number(lastAutopilotBlocked.auto_score_gap).toFixed(1)} Score-Punkte bis Strict.`
                            : ""}
                        </div>
                      ) : null}
                    </div>
                    {lastAutopilotFocus.ticker ? (
                      <button
                        type="button"
                        onClick={() => onAnalyze(lastAutopilotFocus.ticker)}
                        className="shrink-0 rounded-full bg-sky-900 px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-white"
                      >
                        Analyse öffnen
                      </button>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
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
              {autoSelection.blocker_summary.blocker_groups?.length ? (
                <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
                  {autoSelection.blocker_summary.blocker_groups.map((item: any) => (
                    <div key={item.category} className="rounded-xl border border-black/8 bg-white/80 px-3 py-2 text-slate-700">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-black text-slate-900">{item.label}</span>
                        <span className="rounded-full bg-amber-50 px-2 py-0.5 font-black text-amber-800">{item.count}</span>
                      </div>
                      <div className="mt-1 text-[11px] leading-4 text-slate-500">
                        {(item.reasons || []).slice(0, 2).join(" / ")}
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
              {autoSelection.blocker_summary.next_best_rejected?.reasons?.length ? (
                <div className="mt-3 rounded-xl border border-black/8 bg-white/80 px-3 py-2 text-slate-700">
                  <span className="font-extrabold uppercase tracking-[0.14em] text-slate-500">Nächster Kandidat:</span>{" "}
                  {autoSelection.blocker_summary.next_best_rejected.ticker} wird geblockt durch{" "}
                  {(autoSelection.blocker_summary.next_best_rejected.display_reasons || autoSelection.blocker_summary.next_best_rejected.reasons).join(" / ")}.
                  {autoSelection.blocker_summary.next_best_rejected.missing_to_trade ? (
                    <div className="mt-2 font-bold text-slate-900">
                      Fehlt bis Paper-Kauf: {autoSelection.blocker_summary.next_best_rejected.missing_to_trade}
                    </div>
                  ) : null}
                  {Number(autoSelection.blocker_summary.next_best_rejected.auto_score_gap || 0) > 0 ? (
                    <div className="mt-2 font-bold text-slate-900">
                      Score-Luecke: {Number(autoSelection.blocker_summary.next_best_rejected.auto_score_gap).toFixed(1)} Punkte bis Strict-Trade
                      {Number(autoSelection.blocker_summary.next_best_rejected.learning_score_gap || 0) > 0
                        ? ` / ${Number(autoSelection.blocker_summary.next_best_rejected.learning_score_gap).toFixed(1)} Punkte bis Lerntrade`
                        : " / Lernscore erreicht"}
                    </div>
                  ) : null}
                  {autoSelection.blocker_summary.next_best_rejected.learning_block_display_reasons?.length ? (
                    <div className="mt-2 font-bold text-slate-900">
                      Warum kein Lerntrade: {autoSelection.blocker_summary.next_best_rejected.learning_block_display_reasons.slice(0, 2).join(" / ")}
                    </div>
                  ) : null}
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
          <div data-testid="paper-evidence-campaign" className="mt-4 rounded-[1.25rem] border border-violet-200 bg-violet-50/80 p-4 text-violet-950">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="font-extrabold uppercase tracking-[0.16em]">Echte Evidenzkampagne</div>
              <div className="rounded-full border border-violet-200 bg-white px-3 py-1 font-black">
                {evidenceCampaign.strategies_ready || 0}/{evidenceCampaign.strategy_count || strategyReadiness.length} Strategien reif
              </div>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl border border-violet-200 bg-white/80 p-3">
                <div className="text-[10px] font-extrabold uppercase tracking-[0.13em] text-violet-500">Geschlossene Trades</div>
                <div className="mt-1 text-xl font-black">{evidenceCampaign.closed_trades_total || 0}/{evidenceCampaign.required_closed_trades_total || 180}</div>
              </div>
              <div className="rounded-xl border border-violet-200 bg-white/80 p-3">
                <div className="text-[10px] font-extrabold uppercase tracking-[0.13em] text-violet-500">Entscheidende Outcomes</div>
                <div className="mt-1 text-xl font-black">{evidenceCampaign.decisive_outcomes_total || 0}/{evidenceCampaign.global_outcome_target || 100}</div>
              </div>
              <div className="rounded-xl border border-violet-200 bg-white/80 p-3">
                <div className="text-[10px] font-extrabold uppercase tracking-[0.13em] text-violet-500">Nächster Fokus</div>
                <div className="mt-1 font-black">{evidenceCampaign.next_priority?.label || "Erste echte Stichprobe sammeln"}</div>
                <div className="mt-1 text-violet-700">{evidenceCampaign.next_priority?.progress_pct || 0}% erreicht</div>
              </div>
            </div>
            <div className="mt-3 font-semibold leading-5 text-violet-800">
              {evidenceCampaign.policy || "Nur echte, zeitlich fällige Paper-Outcomes zählen; keine synthetischen Abschlüsse."}
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
                <div className="mt-2 grid grid-cols-2 gap-2 text-slate-500">
                  <div>
                    <div className={`font-black ${(item.performance?.profit_factor ?? 1.2) >= 1.2 ? "text-emerald-700" : "text-red-700"}`}>
                      {item.performance?.profit_factor == null ? "offen" : Number(item.performance.profit_factor).toFixed(2)}
                    </div>
                    <div>Profit Factor</div>
                  </div>
                  <div>
                    <div className={`font-black ${Number(item.performance?.expectancy_value || 0) > 0 ? "text-emerald-700" : Number(item.performance?.expectancy_value || 0) < 0 ? "text-red-700" : "text-slate-900"}`}>
                      {money(item.performance?.expectancy_value, currency)}
                    </div>
                    <div>Erwartung / Trade</div>
                  </div>
                </div>
                <div className="mt-2 rounded-xl border border-black/8 bg-white px-3 py-2 text-slate-600">
                  Beweislage: <span className="font-bold text-slate-900">{item.performance?.sample_size || 0}/{item.performance?.minimum_usable_sample || 30}</span>{" "}
                  · {germanText(item.performance?.evidence_label, "zu wenig Daten")}
                </div>
                {!!item.readiness_gaps?.length && (
                  <div className="mt-2 rounded-xl border border-amber-500/20 bg-amber-50 px-3 py-2 text-amber-800">
                    <div className="font-extrabold uppercase tracking-[0.12em]">Noch nicht reif</div>
                    <div className="mt-1 space-y-1">
                      {item.readiness_gaps.slice(0, 3).map((gap: string) => (
                        <div key={gap}>{gap}</div>
                      ))}
                    </div>
                  </div>
                )}
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

        <div className="mt-6 grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="rounded-[1.6rem] border border-emerald-500/20 bg-emerald-50/80 p-4 text-xs text-emerald-900">
            <div className="font-extrabold uppercase tracking-[0.18em] text-emerald-700">Demo-Konto Leitplanken</div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <div>Startkapital: {money(demoAccount.starting_capital || DEFAULT_DEMO_CAPITAL, currency)}</div>
              <div>Max. Position: {money(demoAccount.max_position_value, currency)} / Idee</div>
              <div>Max. Gesamt-Exposure: {money(demoAccount.max_gross_exposure_value, currency)}</div>
              <div>Cashreserve-Ziel: {money(demoAccount.cash_reserve_target_value, currency)}</div>
              <div>Freie Gesamt-Exposure: {money(demoAccount.remaining_gross_exposure_value, currency)}</div>
              <div>Max. pro Ticker: {money(demoAccount.max_ticker_exposure_value, currency)}</div>
              <div>Max. offenes Risiko: {money(demoAccount.max_open_risk_value, currency)}</div>
              <div>Freies Risiko: {money(demoAccount.remaining_risk_value, currency)}</div>
              <div>Optionsrisiko/Trade: {money(demoAccount.risk_budget_per_option_trade_value, currency)}</div>
              <div>Max. Optionsprämie: {money(demoAccount.max_option_premium_value, currency)}</div>
              <div>Offene Optionsprämie: {money(demoAccount.option_premium_exposure_value, currency)} / {money(demoAccount.max_open_option_premium_value, currency)}</div>
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

        <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatTile label="Trefferquote" value={formatPct(stats.win_rate, 0, "0%").replace("+", "")} tone={Number(stats.win_rate || 0) >= 50 ? "good" : "default"} />
          <StatTile label="Profit Factor" value={profitFactor == null ? "offen" : profitFactor.toFixed(2)} tone={profitFactor != null && profitFactor >= 1.2 ? "good" : profitFactor != null && profitFactor < 1 ? "bad" : "default"} />
          <StatTile label="Erwartung / Trade" value={money(performance.expectancy_value, currency)} tone={Number(performance.expectancy_value || 0) > 0 ? "good" : Number(performance.expectancy_value || 0) < 0 ? "bad" : "default"} />
          <StatTile label="Beweislage" value={`${performance.sample_size || 0} / ${performance.minimum_usable_sample || 30}`} />
        </div>

        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 px-1 text-xs text-slate-500">
          <span>Realisiert {formatPct(stats.realized_pnl_pct, 2, "+0.00%")} ({money(stats.realized_pnl_value, currency)})</span>
          <span>Offene PnL {formatPct(stats.avg_open_pnl_pct, 2, "+0.00%")}</span>
          <span>Gewinn {money(performance.avg_win_value, currency)} / Verlust {money(performance.avg_loss_value, currency)} im Durchschnitt</span>
          <span>{performance.evidence_label || "zu wenig Daten"}</span>
        </div>

        {!!entrySourcePerformance.length && (
          <div className="mt-4 rounded-[1.6rem] border border-black/8 bg-white/70 p-4 text-xs text-slate-600">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="font-extrabold uppercase tracking-[0.18em] text-slate-500">Entry-Quelle lernen</div>
                <div className="mt-1 text-slate-500">Autopilot und manuelle Playbook-Entries getrennt bewerten.</div>
              </div>
              <div className="text-right font-semibold text-slate-500">
                {entrySourcePerformance.reduce((sum: number, item: any) => sum + Number(item.trades || 0), 0)} geschlossene Trades
              </div>
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {entrySourcePerformance.slice(0, 4).map((item: any) => {
                const sourcePerformance = item.performance || {};
                const sourceExpectancy = Number(sourcePerformance.expectancy_value || 0);
                const sourceProfitFactor = toFiniteNumber(sourcePerformance.profit_factor);
                return (
                  <div key={item.entry_source_label} className="rounded-[1.15rem] border border-black/8 bg-white px-4 py-3">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <div className="font-black text-slate-900">{item.entry_source_label}</div>
                        <div className="mt-1 text-slate-500">{item.trades || 0} geschlossene Paper-Trades</div>
                      </div>
                      <div className={`font-black ${sourceExpectancy > 0 ? "text-emerald-700" : sourceExpectancy < 0 ? "text-red-700" : "text-slate-900"}`}>
                        {money(sourcePerformance.expectancy_value, currency)}
                      </div>
                    </div>
                    <div className="mt-3 grid grid-cols-3 gap-2 text-slate-500">
                      <div>
                        <div className="font-black text-slate-900">{formatPct(sourcePerformance.win_rate, 1, "0.0%").replace("+", "")}</div>
                        <div>Treffer</div>
                      </div>
                      <div>
                        <div className={`font-black ${sourceProfitFactor != null && sourceProfitFactor >= 1.2 ? "text-emerald-700" : sourceProfitFactor != null && sourceProfitFactor < 1 ? "text-red-700" : "text-slate-900"}`}>
                          {sourceProfitFactor == null ? "offen" : sourceProfitFactor.toFixed(2)}
                        </div>
                        <div>PF</div>
                      </div>
                      <div>
                        <div className="font-black text-slate-900">{sourcePerformance.sample_size || 0}/{sourcePerformance.minimum_usable_sample || 30}</div>
                        <div>Beweise</div>
                      </div>
                    </div>
                    <div className="mt-3 rounded-xl border border-black/8 bg-slate-50 px-3 py-2 text-slate-600">
                      {item.summary}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <div className="mt-4 rounded-[1.6rem] border border-sky-500/20 bg-sky-50/60 p-4 text-xs text-slate-600">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="font-extrabold uppercase tracking-[0.18em] text-sky-700">News Shadow Lab · 24 Stunden</div>
              <div className="mt-1 max-w-3xl text-slate-600">
                Jede Meldung zählt genau einmal. So werden 1h-, 24h-, 72h- und 120h-Ergebnisse derselben Headline nicht als vier unabhängige Signale ausgegeben.
              </div>
            </div>
            <div className="rounded-full border border-sky-500/20 bg-white px-3 py-1 font-black text-sky-800">
              {newsShadowSummary.forecasts || 0} beobachtet · {newsShadowSummary.pending_24h || 0} offen
            </div>
          </div>

          <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-xl border border-black/8 bg-white/85 px-3 py-3">
              <div className="font-black text-slate-900">{newsShadowSummary.evaluated_24h || 0}</div>
              <div className="mt-1 text-slate-500">einmalig ausgewertet</div>
            </div>
            <div className="rounded-xl border border-black/8 bg-white/85 px-3 py-3">
              <div className="font-black text-slate-900">{Number(newsShadowSummary.hit_rate || 0).toFixed(1)}%</div>
              <div className="mt-1 text-slate-500">Treffer bei klaren Fällen</div>
            </div>
            <div className="rounded-xl border border-black/8 bg-white/85 px-3 py-3">
              <div className={`font-black ${Number(newsShadowSummary.avg_directional_move_pct || 0) > 0 ? "text-emerald-700" : Number(newsShadowSummary.avg_directional_move_pct || 0) < 0 ? "text-red-700" : "text-slate-900"}`}>
                {formatPct(newsShadowSummary.avg_directional_move_pct, 2, "offen")}
              </div>
              <div className="mt-1 text-slate-500">Ø Richtungsbewegung</div>
            </div>
            <div className="rounded-xl border border-black/8 bg-white/85 px-3 py-3">
              <div className={`font-black ${Number(newsShadowSummary.strict_gate_lift_pct_points || 0) > 0 ? "text-emerald-700" : Number(newsShadowSummary.strict_gate_lift_pct_points || 0) < 0 ? "text-red-700" : "text-slate-900"}`}>
                {newsShadowSummary.strict_gate_lift_pct_points == null ? "noch offen" : `${Number(newsShadowSummary.strict_gate_lift_pct_points) >= 0 ? "+" : ""}${Number(newsShadowSummary.strict_gate_lift_pct_points).toFixed(1)} PP`}
              </div>
              <div className="mt-1 text-slate-500">Mehrwert des strikten Gates</div>
            </div>
          </div>

          {newsShadowCohorts.length ? (
            <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
              {newsShadowCohorts.slice(0, 4).map((item: any) => (
                <div key={item.label} className="rounded-xl border border-black/8 bg-white/85 px-3 py-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="font-black text-slate-900">{germanStatus(item.label, item.label)}</div>
                    <div className="font-black text-sky-800">{item.hit_rate || 0}%</div>
                  </div>
                  <div className="mt-2 text-slate-500">
                    {item.evaluated || 0} Meldungen · {item.decisive || 0} klar · Ø {formatPct(item.avg_directional_move_pct, 2, "0.00%")}
                  </div>
                  <div className="mt-1 font-semibold text-slate-700">{germanStatus(item.evidence_status, "zu wenig Daten")}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-3 rounded-xl border border-dashed border-sky-500/25 bg-white/75 px-4 py-3">
              Noch keine kanonischen 24-Stunden-News-Ergebnisse vorhanden.
            </div>
          )}

          {newsShadowEvents.some((item: any) => Number(item.paper_prior_score_delta || 0) !== 0) ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {newsShadowEvents
                .filter((item: any) => Number(item.paper_prior_score_delta || 0) !== 0)
                .slice(0, 4)
                .map((item: any) => {
                  const delta = Number(item.paper_prior_score_delta || 0);
                  return (
                    <div key={`prior-${item.label}`} className={`rounded-full border px-3 py-1 font-black ${delta > 0 ? "border-emerald-500/20 bg-emerald-50 text-emerald-800" : "border-red-500/20 bg-red-50 text-red-800"}`}>
                      Event-Prior {String(item.label || "unknown").replace(/_/g, " ")} {delta > 0 ? "+" : ""}{delta} · {item.evaluated} Meldungen
                    </div>
                  );
                })}
            </div>
          ) : null}

          <div className="mt-3 font-semibold text-sky-900">
            {newsShadowSummary.sample_unit || "Eine Meldung mit genau einem 24-Stunden-Ergebnis."} {newsShadowSummary.policy || "Shadow-Studie ohne Position oder Echtgeldwirkung."}
          </div>
        </div>

        <div className="mt-4 rounded-[1.6rem] border border-violet-500/20 bg-violet-50/70 p-4 text-xs text-violet-950">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="font-extrabold uppercase tracking-[0.18em] text-violet-700">Quantitative Korrelation</div>
              <div className="mt-1">{correlationAnalysis.message || "Renditekorrelation wird geladen; statische Risikobuckets bleiben aktiv."}</div>
            </div>
            <div className="rounded-full border border-violet-500/20 bg-white px-3 py-1 font-black">
              {correlationAnalysis.status || "unavailable"}
            </div>
          </div>
          <div className="mt-2 text-violet-800">
            Methode: {correlationAnalysis.method || "6-Monats-Tagesrenditen"} · Block ab {Number(correlationAnalysis.threshold || 0.88).toFixed(2)} bei mindestens {correlationAnalysis.minimum_observations || 40} Beobachtungen.
          </div>
          {!!highCorrelationPairs.length && (
            <div className="mt-3 flex flex-wrap gap-2">
              {highCorrelationPairs.slice(0, 8).map((pair: any) => (
                <span key={`${pair.candidate}-${pair.existing_ticker}`} className="rounded-full border border-violet-200 bg-white px-3 py-1 font-bold">
                  {pair.candidate}/{pair.existing_ticker}: {Number(pair.correlation || 0).toFixed(2)} ({pair.observations}d)
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="mt-4 rounded-[1.6rem] border border-violet-500/20 bg-violet-50/55 p-4 text-xs text-slate-600">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="font-extrabold uppercase tracking-[0.18em] text-violet-700">News-Beweiskarte</div>
              <div className="mt-1 max-w-3xl text-slate-600">
                Misst realisierten Follow-through getrennt nach echter Quelle und Eventtyp. Erst ab {newsEvidenceSummary.minimum_adjustment_sample || 10} Abschlüssen wird der News-Score angepasst.
              </div>
            </div>
            <div className="rounded-full border border-violet-500/20 bg-white px-3 py-1 font-black text-violet-800">
              {newsEvidenceSummary.closed_news_trades || 0} geschlossene News-Trades
            </div>
          </div>

          {newsSourcePerformance.length || newsEventPerformance.length ? (
            <div className="mt-4 grid gap-4 xl:grid-cols-2">
              {[
                { title: "Quellen", rows: newsSourcePerformance },
                { title: "Eventtypen", rows: newsEventPerformance },
              ].map((group: any) => (
                <div key={group.title} className="rounded-[1.2rem] border border-black/8 bg-white/85 p-3">
                  <div className="font-black uppercase tracking-[0.14em] text-slate-500">{group.title}</div>
                  <div className="mt-3 space-y-2">
                    {group.rows.slice(0, 4).map((item: any) => {
                      const evidence = item.performance || {};
                      const scoreDelta = Number(item.score_delta || 0);
                      return (
                        <div key={`${group.title}-${item.label}`} className="rounded-xl border border-black/8 bg-slate-50 px-3 py-3">
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <div>
                              <div className="font-black text-slate-900">{String(item.label || "unbekannt").replace(/_/g, " ")}</div>
                              <div className="mt-1 text-slate-500">{item.trades || 0} Abschlüsse · Reaktionsbruch {item.reaction_failure_rate || 0}%</div>
                            </div>
                            <div className={`font-black ${scoreDelta > 0 ? "text-emerald-700" : scoreDelta < 0 ? "text-red-700" : "text-slate-600"}`}>
                              {scoreDelta > 0 ? `Score +${scoreDelta}` : scoreDelta < 0 ? `Score ${scoreDelta}` : germanStatus(item.quality_status, "beobachten")}
                            </div>
                          </div>
                          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-slate-600">
                            <span>Treffer {evidence.win_rate || 0}%</span>
                            <span>Erwartung {formatPct(evidence.expectancy_pct, 2, "0.00%")}</span>
                            <span>PF {evidence.profit_factor == null ? "offen" : Number(evidence.profit_factor).toFixed(2)}</span>
                          </div>
                          <div className="mt-2 font-semibold text-slate-700">{item.next_action}</div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-4 rounded-[1.1rem] border border-dashed border-violet-500/25 bg-white/75 px-4 py-3 text-slate-600">
              Noch keine geschlossenen bestätigten News-Trades. Quellen bleiben deshalb ungewichtet.
            </div>
          )}

          <div className="mt-3 rounded-xl border border-violet-500/15 bg-white/75 px-3 py-2 font-semibold text-violet-900">
            {newsEvidenceSummary.causality_note || "Zeitlicher Follow-through beweist keine Kausalität der Meldung."} Echtgeld bleibt gesperrt.
          </div>
        </div>

        {!!learningContextPerformance.length && (
          <div className="mt-4 rounded-[1.6rem] border border-black/8 bg-white/70 p-4 text-xs text-slate-600">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="font-extrabold uppercase tracking-[0.18em] text-slate-500">Lernkontext bewerten</div>
                <div className="mt-1 text-slate-500">Zeigt, ob Lerntrades in Konto-Zustaenden wie Gewinnschutz wirklich helfen.</div>
              </div>
              <div className="text-right font-semibold text-slate-500">
                {learningContextPerformance.reduce((sum: number, item: any) => sum + Number(item.trades || 0), 0)} Kontext-Trades
              </div>
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {learningContextPerformance.slice(0, 4).map((item: any) => {
                const contextPerformance = item.performance || {};
                const expectancy = Number(contextPerformance.expectancy_value || 0);
                const profitFactor = toFiniteNumber(contextPerformance.profit_factor);
                return (
                  <div key={item.key} className="rounded-[1.15rem] border border-black/8 bg-white px-4 py-3">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <div className="font-black text-slate-900">
                          {germanStatus(item.account_day_status, item.account_day_status)} / {germanStatus(item.account_queue_status, item.account_queue_status)}
                        </div>
                        <div className="mt-1 text-slate-500">{item.autopilot_mode} · Risiko x{Number(item.avg_risk_multiplier || 0).toFixed(2)}</div>
                      </div>
                      <div className={`font-black ${expectancy > 0 ? "text-emerald-700" : expectancy < 0 ? "text-red-700" : "text-slate-900"}`}>
                        {money(contextPerformance.expectancy_value, currency)}
                      </div>
                    </div>
                    <div className="mt-3 grid grid-cols-3 gap-2 text-slate-500">
                      <div>
                        <div className="font-black text-slate-900">{formatPct(contextPerformance.win_rate, 1, "0.0%").replace("+", "")}</div>
                        <div>Treffer</div>
                      </div>
                      <div>
                        <div className={`font-black ${profitFactor != null && profitFactor >= 1.2 ? "text-emerald-700" : profitFactor != null && profitFactor < 1 ? "text-red-700" : "text-slate-900"}`}>
                          {profitFactor == null ? "offen" : profitFactor.toFixed(2)}
                        </div>
                        <div>PF</div>
                      </div>
                      <div>
                        <div className="font-black text-slate-900">{contextPerformance.sample_size || 0}/{contextPerformance.minimum_usable_sample || 30}</div>
                        <div>Beweise</div>
                      </div>
                    </div>
                    <div className="mt-3 rounded-xl border border-black/8 bg-slate-50 px-3 py-2 text-slate-600">
                      {item.summary}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <div className="mt-4 rounded-[1.6rem] border border-cyan-500/20 bg-cyan-50/60 p-4 text-xs text-cyan-950">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="font-extrabold uppercase tracking-[0.18em] text-cyan-700">Performance nach Entry-Marktregime</div>
              <div className="mt-1 text-cyan-800">Trend, Volatilitäts-Proxy, Zinsen, Dollar, Risikoappetit und Breiten-Proxy werden beim Einstieg unveränderlich gespeichert.</div>
            </div>
            <div className="rounded-full border border-cyan-500/20 bg-white px-3 py-1 font-black text-cyan-800">
              Abdeckung {Number(marketRegimePerformance.coverage_pct || 0).toFixed(1)}%
            </div>
          </div>
          {marketRegimeRows.length ? (
            <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {marketRegimeRows.slice(0, 12).map((item: any) => {
                const performance = item.performance || {};
                return (
                  <div key={`${item.dimension}-${item.label}`} className="rounded-[1.1rem] border border-cyan-500/15 bg-white px-3 py-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-cyan-600">{String(item.dimension).replace(/_/g, " ")}</div>
                        <div className="mt-1 font-black text-slate-900">{String(item.label).replace(/_/g, " ")}</div>
                      </div>
                      <div className="font-black text-cyan-800">{item.trades || 0}/30</div>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-slate-600">
                      <span>Treffer {Number(performance.win_rate || 0).toFixed(1)}%</span>
                      <span>PF {performance.profit_factor == null ? "offen" : Number(performance.profit_factor).toFixed(2)}</span>
                      <span>Erwartung {money(performance.expectancy_value, currency)}</span>
                    </div>
                    <div className="mt-2 font-semibold text-cyan-800">{germanStatus(item.readiness, item.readiness)}</div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="mt-3 rounded-xl border border-dashed border-cyan-500/25 bg-white/75 px-3 py-3 text-cyan-800">
              Neue Trades speichern das Entry-Regime ab jetzt. Bestehende historische Trades werden nicht rückwirkend geschätzt.
            </div>
          )}
          <div className="mt-3 font-semibold text-cyan-900">{marketRegimePerformance.policy || "Belastbare Bewertung erst ab 30 geschlossenen Trades je Regime."}</div>
        </div>

        <div className="mt-4 rounded-[1.6rem] border border-indigo-500/20 bg-indigo-50/60 p-4 text-xs text-indigo-950">
          <div className="font-extrabold uppercase tracking-[0.18em] text-indigo-700">Strategie-Auswertung nach Dimension</div>
          <div className="mt-1 text-indigo-800">Setup, Marktregime, Quelle, Scoreband und Risikobucket werden getrennt ausgewertet.</div>
          {strategyDimensionRows.length ? (
            <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
              {strategyDimensionRows.slice(0, 18).map((item: any) => (
                <div key={`${item.dimension}-${item.label}`} className="rounded-xl border border-indigo-200 bg-white px-3 py-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="text-[10px] font-extrabold uppercase tracking-[0.12em] text-indigo-600">{String(item.dimension).replace(/_/g, " ")}</div>
                      <div className="mt-1 font-black text-slate-900">{String(item.label).replace(/_/g, " ")}</div>
                    </div>
                    <div className="font-black">{item.trades || 0}/30</div>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-slate-600">
                    <span>Treffer {Number(item.performance?.win_rate || 0).toFixed(1)}%</span>
                    <span>PF {item.performance?.profit_factor == null ? "offen" : Number(item.performance.profit_factor).toFixed(2)}</span>
                    <span>Erwartung {money(item.performance?.expectancy_value, currency)}</span>
                    <span>Drawdown {Number(item.performance?.max_drawdown_pct || 0).toFixed(2)}%</span>
                  </div>
                  <div className="mt-2 font-semibold text-indigo-800">{germanStatus(item.readiness, item.readiness)}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-3 rounded-xl border border-dashed border-indigo-300 bg-white px-3 py-3">Noch keine geschlossenen Trades für die Segmentauswertung.</div>
          )}
          <div className="mt-3 font-semibold">{strategyDimensionPerformance.policy}</div>
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
                  <OptionContractEvidence item={item} />
                  {item.news_evidence ? (
                    <div className="mt-3 rounded-[1.1rem] border border-violet-200 bg-violet-50/80 p-3 text-xs leading-5 text-violet-950">
                      <div className="flex flex-wrap items-center gap-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-violet-700">
                        <span>Verifizierter News-Trigger</span>
                        <span className="rounded-full border border-violet-200 bg-white px-2 py-0.5">
                          Preisreaktion bestätigt
                        </span>
                        {item.news_evidence.original_document_verified ? (
                          <span className="rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-blue-700">Primärdokument geprüft</span>
                        ) : null}
                      </div>
                      <a
                        href={item.news_evidence.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-2 block font-black underline-offset-4 hover:underline"
                      >
                        {item.news_evidence.publisher || "Tier-1-Quelle"} · {item.news_evidence.headline || item.headline}
                      </a>
                      <div className="mt-1 text-violet-800">
                        Veröffentlicht {item.news_evidence.published_at ? new Date(item.news_evidence.published_at).toLocaleString() : "offen"} · relative Reaktion {item.news_evidence.market_confirmation?.relative_move_since_publication ?? "?"}% · Faktenbasis {item.news_evidence.fact_basis || "offen"}
                      </div>
                      <div className="mt-1 font-semibold text-violet-700">
                        Event-Fenster maximal {item.max_holding_days || 3} Tage · zeitliche Bestätigung ist kein Kausalitätsbeweis. Echtgeld bleibt gesperrt.
                      </div>
                    </div>
                  ) : null}
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
                  {item.trade_ticket && (
                    <div className="mt-4 border-t border-black/8 pt-4">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                          Trade Ticket v{item.trade_ticket.schema_version}
                        </div>
                        <span className={`rounded-full border px-2.5 py-1 text-[9px] font-extrabold uppercase tracking-[0.12em] ${
                          item.trade_ticket.paper_ready
                            ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700"
                            : "border-amber-500/20 bg-amber-500/10 text-amber-700"
                        }`}>
                          {item.trade_ticket.status}
                        </span>
                      </div>
                      <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-3 text-xs sm:grid-cols-4">
                        {[
                          ["Entry", item.trade_ticket.entry_price ?? "N/A"],
                          ["Stop", item.trade_ticket.stop_price ?? "N/A"],
                          ["Ziel 1", item.trade_ticket.target_1 ?? "N/A"],
                          ["Ziel 2", item.trade_ticket.target_2 ?? "N/A"],
                          ["Menge", item.trade_ticket.quantity ?? "N/A"],
                          ["Risiko", `${item.trade_ticket.account_risk_pct ?? "N/A"}%`],
                          ["CRV", item.trade_ticket.risk_reward ?? "N/A"],
                          ["Horizont", item.trade_ticket.horizon || "offen"],
                        ].map(([label, value]) => (
                          <div key={String(label)} className="min-w-0">
                            <div className="text-[9px] font-extrabold uppercase tracking-[0.12em] text-slate-400">{label}</div>
                            <div className="mt-1 break-words font-black text-slate-900">{String(value)}</div>
                          </div>
                        ))}
                      </div>
                      {(item.trade_ticket.validation?.warnings || []).length ? (
                        <div className="mt-3 text-[11px] font-semibold leading-5 text-amber-700">
                          Offene Checks: {item.trade_ticket.validation.warnings.join(" · ")}
                        </div>
                      ) : null}
                      <div className="mt-2 text-[10px] font-bold uppercase tracking-[0.12em] text-red-700">
                        Echtgeld: gesperrt
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
                  {item.news_learning_adjustment && (
                    <div className="mt-3 rounded-[1rem] border border-violet-200 bg-violet-50 p-3 text-xs text-violet-900">
                      <div className="font-extrabold uppercase tracking-[0.14em]">News-Evidenz lernen</div>
                      <div className="mt-1 font-black">
                        Score {Number(item.news_learning_adjustment.score_delta || 0) >= 0 ? "+" : ""}
                        {item.news_learning_adjustment.score_delta || 0} · Mindeststichprobe {item.news_learning_adjustment.minimum_sample || 10}
                      </div>
                      {(item.news_learning_adjustment.notes || []).map((note: string) => (
                        <div key={note} className="mt-1">{note}</div>
                      ))}
                      <div className="mt-2 font-bold text-red-700">Echtgeld bleibt gesperrt.</div>
                    </div>
                  )}
                  {item.news_shadow_prior && (
                    <div className="mt-3 rounded-[1rem] border border-sky-200 bg-sky-50 p-3 text-xs text-sky-900">
                      <div className="font-extrabold uppercase tracking-[0.14em]">24h-Event-Prior</div>
                      <div className="mt-1 font-black">
                        {String(item.news_shadow_prior.event_type || "unknown").replace(/_/g, " ")} · {item.news_shadow_prior.evaluated_24h || 0} Meldungen · {item.news_shadow_prior.decisive_24h || 0} klar
                      </div>
                      <div className="mt-1">
                        Treffer {item.news_shadow_prior.hit_rate || 0}% · Ø {formatPct(item.news_shadow_prior.avg_directional_move_pct, 2, "offen")} · angewendet {Number(item.news_shadow_prior.applied_score_delta || 0) > 0 ? "+" : ""}{item.news_shadow_prior.applied_score_delta || 0}
                      </div>
                      <div className="mt-1 font-semibold">{item.news_shadow_prior.note}</div>
                      <div className="mt-2 font-bold text-red-700">Sekundärer Paper-Prior · kein Kausalitätsbeweis · Echtgeld gesperrt.</div>
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
                    <div>Risikobucket: {item.risk_bucket || "offen"}</div>
                    <div>Assetklasse frei: {money(item.remaining_asset_class_capacity_value, currency)}</div>
                  </div>
                  {item.correlation_check && item.correlation_check.status !== "not_applicable" ? (
                    <div className={`mt-3 rounded-xl border px-3 py-2 text-xs ${
                      item.correlation_check.blocked
                        ? "border-red-200 bg-red-50 text-red-800"
                        : "border-violet-200 bg-violet-50 text-violet-900"
                    }`}>
                      <div className="font-extrabold uppercase tracking-[0.12em]">Korrelationscheck</div>
                      <div className="mt-1">{item.correlation_check.reason || item.correlation_check.status}</div>
                    </div>
                  ) : null}
                  {item.leverage_assessment && (
                    <div className={`mt-3 rounded-[1rem] border p-3 text-xs ${
                      item.leverage_assessment.eligible
                        ? "border-violet-300 bg-violet-50 text-violet-900"
                        : "border-slate-200 bg-slate-50 text-slate-700"
                    }`}>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="font-extrabold uppercase tracking-[0.14em]">Paper-Hebel-Gate</div>
                        <div className="rounded-full border border-current/15 bg-white/70 px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.12em]">
                          {item.leverage_assessment.eligible
                            ? `${item.leverage_assessment.recommended_leverage}x sinnvoll`
                            : "Hebel gesperrt"}
                        </div>
                      </div>
                      <div className="mt-2 font-semibold">{item.leverage_assessment.risk_policy}</div>
                      {item.leverage_assessment.eligible && item.leverage_assessment.recommended_sizing ? (
                        <div className="mt-2 grid gap-1 sm:grid-cols-3">
                          <div>Menge: {item.leverage_assessment.recommended_sizing.suggested_quantity}</div>
                          <div>Exposure: {money(item.leverage_assessment.recommended_sizing.suggested_notional_value, currency)}</div>
                          <div>Max. Verlust: {money(item.leverage_assessment.recommended_sizing.suggested_max_loss_value, currency)}</div>
                        </div>
                      ) : null}
                      {item.trade_ticket.entry_market_regime ? (
                        <div className="mt-3 rounded-xl border border-cyan-200 bg-cyan-50 px-3 py-2 text-[11px] font-semibold leading-5 text-cyan-900">
                          Entry-Regime: {item.trade_ticket.entry_market_regime.risk_appetite?.label || "unbekannt"} · Trend {item.trade_ticket.entry_market_regime.trend?.label || "unbekannt"} · Volatilität {item.trade_ticket.entry_market_regime.volatility?.label || "unbekannt"} (Proxy) · Breite {item.trade_ticket.entry_market_regime.breadth?.label || "unbekannt"} (Proxy)
                        </div>
                      ) : null}
                      {!!item.leverage_assessment.blockers?.length && (
                        <div className="mt-2 leading-5">Blocker: {item.leverage_assessment.blockers.slice(0, 4).join(" · ")}</div>
                      )}
                      <div className="mt-2 font-bold text-red-700">Nur Demokonto · Echtgeld gesperrt</div>
                    </div>
                  )}
                  {item.leverage_product_type && (
                    <div className="mt-3 rounded-[1rem] border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
                      <div className="font-extrabold uppercase tracking-[0.14em]">Hebel-Proxy</div>
                      <div className="mt-1 leading-5">
                        {item.underlying_asset || item.ticker} ueber {item.underlying_proxy || item.ticker}. Echter Optionsschein/Knockout erst mit Strike, Laufzeit, Spread, Emittent und Knockout-Abstand.
                      </div>
                    </div>
                  )}
                  {!!item.product_data_required?.length && (
                    <div className="mt-3 rounded-[1rem] border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
                      <div className="font-extrabold uppercase tracking-[0.14em]">Produktdaten fehlen</div>
                      <div className="mt-1 leading-5">{item.product_data_required.slice(0, 5).join(" · ")}</div>
                    </div>
                  )}
                  {item.leverage_product_type && (
                    <div className="mt-3 rounded-[1rem] border border-black/8 bg-white/80 p-3 text-xs text-slate-700">
                      <div className="font-extrabold uppercase tracking-[0.14em] text-slate-500">Produktdaten-Gate</div>
                      <label className="mt-2 block">
                        <span className="font-bold text-slate-500">Typ</span>
                        <select
                          value={productDrafts[item.id]?.product_type || "option_certificate"}
                          onChange={(event) => updateProductDraft(item.id, "product_type", event.target.value)}
                          className="mt-1 w-full rounded-lg border border-black/8 bg-white px-2 py-1.5 text-xs font-bold text-slate-900"
                        >
                          <option value="option_certificate">Optionsschein</option>
                          <option value="knockout">Knockout/Turbo</option>
                        </select>
                      </label>
                      <div className="mt-2 grid gap-2 sm:grid-cols-3">
                        {[
                          ["issuer", "Emittent"],
                          ["strike_or_knockout_level", "Strike/KO"],
                          ["expiry", "Laufzeit"],
                          ["bid", "Bid"],
                          ["ask", "Ask"],
                          ["offered_leverage", "Anbieter-Hebel"],
                          ["contract_multiplier", "Bezugsverhältnis/Multiplikator"],
                          ["distance_to_knockout_pct", "KO-Abstand %"],
                        ].map(([key, label]) => (
                          <label key={key} className="block">
                            <span className="font-bold text-slate-500">{label}</span>
                            <input
                              type={key === "expiry" ? "date" : key === "issuer" ? "text" : "number"}
                              step={key === "contract_multiplier" ? "0.0001" : "0.01"}
                              value={productDrafts[item.id]?.[key] || ""}
                              onChange={(event) => updateProductDraft(item.id, key, event.target.value)}
                              className="mt-1 w-full rounded-lg border border-black/8 bg-white px-2 py-1.5 text-xs font-bold text-slate-900"
                            />
                          </label>
                        ))}
                      </div>
                      <label className="mt-2 flex items-center gap-2 text-xs font-bold text-slate-700">
                        <input
                          type="checkbox"
                          checked={Boolean(productDrafts[item.id]?.overnight_risk_ack)}
                          onChange={(event) => updateProductDraft(item.id, "overnight_risk_ack", event.target.checked)}
                        />
                        Overnight-, Spread- und Emittentenrisiko verstanden
                      </label>
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          onClick={() => validateProductDraft(item.id)}
                          disabled={busyId === `${item.id}-product-check`}
                          className="rounded-xl border border-black/8 bg-white px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-700 disabled:opacity-50"
                        >
                          Produkt prüfen
                        </button>
                        {productChecks[item.id] ? (
                          <span
                            className={`rounded-full px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] ${
                              productChecks[item.id].valid
                                ? "bg-emerald-50 text-emerald-700"
                                : "bg-red-50 text-red-700"
                            }`}
                          >
                            {productChecks[item.id].valid ? "bereit" : "blockiert"}
                          </span>
                        ) : null}
                      </div>
                      {productChecks[item.id]?.errors?.length ? (
                        <div className="mt-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-red-700">
                          {productChecks[item.id].errors.slice(0, 4).join(" · ")}
                        </div>
                      ) : null}
                      {productChecks[item.id]?.warnings?.length ? (
                        <div className="mt-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-amber-800">
                          {productChecks[item.id].warnings.slice(0, 3).join(" · ")}
                        </div>
                      ) : null}
                      {productChecks[item.id]?.valid && productChecks[item.id]?.data?.offered_leverage ? (
                        <div className="mt-2 rounded-xl border border-violet-200 bg-violet-50 px-3 py-2 font-bold text-violet-800">
                          Anbieterhebel {Number(productChecks[item.id].data.offered_leverage).toFixed(1)}x und Produktmultiplikator {Number(productChecks[item.id].data.contract_multiplier).toFixed(4)} werden exakt übernommen; der Hebel wird nicht nochmals auf Produktkurs oder P&amp;L gerechnet.
                        </div>
                      ) : null}
                    </div>
                  )}
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
                    {item.setup_type === "confirmed_news_event" ? (
                      <button
                        onClick={() => openFromPlaybook(item.id, item.direction)}
                        disabled={busyId === item.id || item.tradeable === false || item.demo_tradeable === false}
                        className="rounded-xl bg-violet-700 px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-white transition-colors hover:bg-violet-800 disabled:opacity-50"
                      >
                        Paper {item.direction} · News bestätigt
                      </button>
                    ) : item.asset_class === "option" ? (
                      <button
                        onClick={() => openFromPlaybook(
                          item.id,
                          item.direction,
                          productDrafts[item.id],
                          Number(productDrafts[item.id]?.offered_leverage || 1),
                        )}
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
                    {item.leverage_assessment?.eligible && Number(item.recommended_leverage || 1) > 1 && (
                      <button
                        onClick={() => openFromPlaybook(
                          item.id,
                          item.direction,
                          undefined,
                          Number(item.recommended_leverage),
                        )}
                        disabled={busyId === item.id || item.tradeable === false || item.demo_tradeable === false}
                        className="rounded-xl bg-violet-700 px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-white transition-colors hover:bg-violet-800 disabled:opacity-50"
                      >
                        Paper {item.direction} · Hebel {item.recommended_leverage}x
                      </button>
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
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">Geschlossene Trades</div>
            <div className="mt-4 space-y-3">
              {closedTrades.length ? (
                closedTrades.slice(0, 6).map((trade: any) => (
                  <div key={trade.id} className="rounded-[1.3rem] border border-black/8 bg-white/75 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-black text-slate-900">{trade.ticker} · {trade.direction}</div>
                        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                          <span>{trade.setup_type}</span>
                          <span className="rounded-full border border-black/8 bg-slate-50 px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.12em] text-slate-500">
                            {entrySourceLabel(trade)}
                          </span>
                        </div>
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
                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-500 sm:grid-cols-3">
                    <div>Ø {item.avg_pnl_pct >= 0 ? "+" : ""}{item.avg_pnl_pct}%</div>
                    <div>PF {item.performance?.profit_factor == null ? "offen" : Number(item.performance.profit_factor).toFixed(2)}</div>
                    <div>{money(item.performance?.expectancy_value, currency)} / Trade</div>
                    <div>Bestwert {item.best_pnl_pct >= 0 ? "+" : ""}{item.best_pnl_pct}%</div>
                    <div>Schlecht {item.worst_pnl_pct >= 0 ? "+" : ""}{item.worst_pnl_pct}%</div>
                    <div>{germanText(item.performance?.evidence_label, "zu wenig Daten")}</div>
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
                        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                          <span>{entry.setup_type}</span>
                          <span className="rounded-full border border-black/8 bg-slate-50 px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.12em] text-slate-500">
                            {entrySourceLabel(entry)}
                          </span>
                        </div>
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
