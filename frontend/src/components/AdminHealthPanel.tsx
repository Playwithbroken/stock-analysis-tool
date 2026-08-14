import React, { useEffect, useState } from "react";

interface AdminHealthPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

function statusTone(status?: string) {
  const value = String(status || "").toLowerCase();
  if (["ok", "live", "ready", "sent", "sendable"].includes(value)) return "bg-emerald-500/10 text-emerald-700 border-emerald-500/20";
  if (["degraded", "partial", "snapshot", "skipped", "missed", "pending"].includes(value)) return "bg-amber-500/10 text-amber-700 border-amber-500/20";
  return "bg-red-500/10 text-red-700 border-red-500/20";
}

function fmtDate(value?: string | null) {
  if (!value) return "offen";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" });
}

function displayValue(value?: string | number | null, fallback = "offen") {
  if (value === null || value === undefined || value === "") return fallback;
  const text = String(value);
  if (text.toLowerCase() === "unknown" || text.toLowerCase() === "n/a") return fallback;
  return value;
}

function formatBytes(value?: number | null) {
  if (!value || value <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function formatMoney(value?: number | null) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "offen";
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPct(value?: number | null) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "offen";
  return `${value.toFixed(2)}%`;
}

function paperPerformanceSummary(performance?: any) {
  if (!performance || typeof performance !== "object") return null;
  const sample = Number(performance.sample_size || 0);
  const minimum = Number(performance.minimum_usable_sample || 30);
  const profitFactor = performance.profit_factor == null ? "offen" : Number(performance.profit_factor).toFixed(2);
  return {
    sample: `${sample}/${minimum}`,
    profitFactor,
    expectancy: formatMoney(Number(performance.expectancy_value || 0)),
    winRate: formatPct(Number(performance.win_rate || 0)),
    evidence: String(performance.evidence_label || "zu wenig Daten"),
  };
}

function previewBlockReasons(preview: any) {
  const blocked = preview?.blocker_summary?.next_best_rejected || {};
  const mode = preview?.mode === "learn" ? "learn" : "strict";
  const reasons =
    mode === "learn"
      ? blocked.learning_block_display_reasons || blocked.display_reasons || blocked.reasons || []
      : blocked.display_reasons || blocked.reasons || [];
  return {
    blocked,
    reasons: Array.isArray(reasons) ? reasons.filter(Boolean).slice(0, 3) : [],
    scoreGap:
      mode === "learn"
        ? Number(blocked.learning_score_gap || 0)
        : Number(blocked.auto_score_gap || 0),
  };
}

function jobStateLabel(job: any) {
  if (job.last_status === "blocked") return "Qualitätsblock"
  if (job.sent_today) return "heute gesendet";
  if (job.due_now) return "jetzt fällig";
  if (job.catchup_available) return "nachholbar";
  if (job.missed_today) return "verpasst";
  return "wartet";
}

function healthProblemInfo(code: string) {
  const map: Record<string, { label: string; action: string; tone: string }> = {
    telegram: { label: "Telegram ist nicht sendbar", action: "Bot, Chat-ID und /start prüfen. Ohne Telegram kommen keine Alerts an.", tone: "red" },
    yfinance: { label: "Marktdatenquelle langsam oder fehlerhaft", action: "Analyzer mit bekanntem Ticker testen und später erneut prüfen.", tone: "amber" },
    schedule_disabled: { label: "Briefing-Scheduler ist deaktiviert", action: "Scheduled Briefs aktivieren, wenn automatische Telegram-Briefings laufen sollen.", tone: "amber" },
    database_missing: { label: "Datenbank fehlt", action: "Volume/Persistenz prüfen, sonst werden Portfolio und Lernen nicht sauber gespeichert.", tone: "red" },
    database_integrity: { label: "Datenbank-Integrität auffällig", action: "Backup ziehen, Logs prüfen und SQLite quick_check ernst nehmen.", tone: "red" },
    database_not_writable: { label: "Datenbank ist nicht beschreibbar", action: "Volume-Rechte prüfen. Neue Portfolios, Trades und Learnings können sonst verloren gehen.", tone: "red" },
    database_volume_missing: { label: "Persistentes Volume fehlt", action: "Railway Volume für /app/data prüfen, damit Redeploys keine Daten verlieren.", tone: "red" },
    backup_missing: { label: "Noch kein automatisches Backup", action: "Backup jetzt ausführen und den Scheduler kontrollieren.", tone: "red" },
    backup_stale: { label: "Datenbank-Backup ist veraltet", action: "Backup sofort ausführen und Backup-Verzeichnis/Volume prüfen.", tone: "red" },
    backup_error: { label: "Datenbank-Backup fehlgeschlagen", action: "Backup-Fehler, freien Speicher und Volume-Rechte prüfen.", tone: "red" },
    restore_test_missing: { label: "Restore wurde noch nicht verifiziert", action: "Restore-Test starten; die Live-Datenbank wird dabei nicht verändert.", tone: "amber" },
    restore_test_error: { label: "Restore-Test fehlgeschlagen", action: "Backup-Integrität und Tabellenvergleich prüfen.", tone: "red" },
    scheduler_error: { label: "Scheduler meldet einen Fehler", action: "Letzten Step-Fehler und Railway Logs prüfen.", tone: "red" },
    scheduler_not_seen: { label: "Scheduler wurde noch nicht gesehen", action: "App-Prozess und Background-Loop prüfen; Briefings starten sonst nicht automatisch.", tone: "amber" },
    scheduler_loop_stale: { label: "Scheduler-Loop ist stale", action: "Railway Logs prüfen und Service neu starten, wenn der Loop hängt.", tone: "red" },
    brief_missed_today: { label: "Briefing wurde heute verpasst", action: "Run Due/Missed oder den passenden Brief-Job manuell senden.", tone: "amber" },
    brief_catchup_available: { label: "Briefing kann noch nachgeholt werden", action: "Jetzt senden, solange die Grace-Zeit offen ist.", tone: "amber" },
    brief_quality_blocked: { label: "Briefing wurde vom Qualitätsgate blockiert", action: "Quellen/News-Qualität prüfen; lieber kein Brief als schlechter Brief.", tone: "amber" },
    paper_autopilot_loop_disabled: { label: "Paper-Autopilot-Loop ist deaktiviert", action: "Forecast/Paper-Learning aktivieren, wenn das Demo-Konto automatisch lernen soll.", tone: "amber" },
    paper_autopilot_not_seen: { label: "Paper-Autopilot wurde noch nicht gesehen", action: "Strict/Lernen prüfen und Background-Loop kontrollieren.", tone: "amber" },
    paper_autopilot_error: { label: "Paper-Autopilot hatte einen Fehler", action: "Letzte Kandidaten, Blockgründe und Logs prüfen, bevor neue Demo-Trades laufen.", tone: "red" },
    paper_autopilot_stale: { label: "Paper-Autopilot ist nicht frisch", action: "Preview starten oder Scheduler/Background-Loop prüfen.", tone: "amber" },
    paper_outcomes_not_seen: { label: "Paper-Outcomes wurden noch nicht ausgewertet", action: "Outcomes prüfen klicken, damit das System aus Treffern und Fehlern lernt.", tone: "amber" },
    paper_outcomes_error: { label: "Paper-Outcome-Auswertung hatte Fehler", action: "Outcome-Fehler und Kursdaten prüfen, bevor du Learnings ernst gewichtest.", tone: "red" },
    paper_outcomes_stale: { label: "Paper-Outcome-Lernen ist veraltet", action: "Outcomes jetzt prüfen; alte Learnings können falsche Signale verstärken.", tone: "amber" },
    paper_outcomes_backlog: { label: "Viele Paper-Outcomes sind offen", action: "Outcomes prüfen und Datenlücken klären, damit Hit-Rate und Fehlerliste stimmen.", tone: "amber" },
  };
  return map[code] || { label: code, action: "Health Center und Logs prüfen.", tone: "amber" };
}

export default function AdminHealthPanel({ isOpen, onClose }: AdminHealthPanelProps) {
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [warming, setWarming] = useState(false);
  const [runningDue, setRunningDue] = useState(false);
  const [sendingSession, setSendingSession] = useState("");
  const [downloadingBackup, setDownloadingBackup] = useState(false);
  const [verifyingRestore, setVerifyingRestore] = useState(false);
  const [runningPaperPreview, setRunningPaperPreview] = useState("");
  const [evaluatingPaperOutcomes, setEvaluatingPaperOutcomes] = useState(false);
  const [sendingPaperAccount, setSendingPaperAccount] = useState(false);
  const [warmupResult, setWarmupResult] = useState<any>(null);
  const [runResult, setRunResult] = useState<any>(null);
  const [paperPreviewResult, setPaperPreviewResult] = useState<any>(null);
  const [paperOutcomeResult, setPaperOutcomeResult] = useState<any>(null);
  const [paperAccountResult, setPaperAccountResult] = useState<any>(null);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/admin/health-center");
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Health center failed");
      setHealth(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Health center failed");
    } finally {
      setLoading(false);
    }
  };

  const warmBrief = async () => {
    setWarming(true);
    setError("");
    setWarmupResult(null);
    try {
      const res = await fetch("/api/admin/warm-brief", { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Brief warmup failed");
      setWarmupResult(data);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Brief warmup failed");
    } finally {
      setWarming(false);
    }
  };

  const runDueBriefs = async () => {
    setRunningDue(true);
    setError("");
    setRunResult(null);
    try {
      const res = await fetch("/api/admin/run-scheduled-briefs?include_missed=true", { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Scheduled brief run failed");
      setRunResult(data);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scheduled brief run failed");
    } finally {
      setRunningDue(false);
    }
  };

  const sendJobBrief = async (job: any) => {
    const jobKey = String(job?.job_key || "").trim();
    if (!jobKey) return;
    setSendingSession(jobKey);
    setError("");
    setRunResult(null);
    try {
      const res = await fetch(`/api/admin/send-brief-job/${encodeURIComponent(jobKey)}`, {
        method: "POST",
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Telegram brief failed");
      setRunResult([
        {
          job: data.label || job?.label || jobKey,
          status: data.status || "ok",
          message: data.message || "Rich Telegram Brief wurde gesendet und als erledigt markiert.",
        },
      ]);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Telegram brief failed");
    } finally {
      setSendingSession("");
    }
  };

  const downloadBackup = async () => {
    setDownloadingBackup(true);
    setError("");
    try {
      const res = await fetch("/api/admin/backup/portfolio-db");
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Backup download failed");
      }
      const blob = await res.blob();
      const disposition = res.headers.get("content-disposition") || "";
      const match = disposition.match(/filename="?([^"]+)"?/i);
      const filename = match?.[1] || `broker-freund-portfolio-backup-${Date.now()}.db`;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backup download failed");
    } finally {
      setDownloadingBackup(false);
    }
  };

  const verifyRestore = async () => {
    setVerifyingRestore(true);
    setError("");
    setRunResult(null);
    try {
      const res = await fetch("/api/admin/backup/verify-restore", { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Restore verification failed");
      setRunResult([{ job: "Restore-Test", status: data.restore_test?.status || data.status, message: "Temporäre Wiederherstellung, Integrität und Tabellenzähler stimmen." }]);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Restore verification failed");
    } finally {
      setVerifyingRestore(false);
    }
  };

  const runPaperPreview = async (mode: "strict" | "learn" = "strict") => {
    setRunningPaperPreview(mode);
    setError("");
    setPaperPreviewResult(null);
    try {
      const res = await fetch("/api/trading/paper-autopilot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ execute: false, max_trades: 3, mode }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Paper autopilot preview failed");
      setPaperPreviewResult(data);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Paper autopilot preview failed");
    } finally {
      setRunningPaperPreview("");
    }
  };

  const evaluatePaperOutcomes = async () => {
    setEvaluatingPaperOutcomes(true);
    setError("");
    setPaperOutcomeResult(null);
    try {
      const res = await fetch("/api/trading/paper-outcomes/evaluate", { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Paper outcome evaluation failed");
      setPaperOutcomeResult(data);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Paper outcome evaluation failed");
    } finally {
      setEvaluatingPaperOutcomes(false);
    }
  };

  const sendPaperAccountStatus = async () => {
    setSendingPaperAccount(true);
    setError("");
    setPaperAccountResult(null);
    try {
      const res = await fetch("/api/admin/send-paper-account-status", { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Paper account Telegram status failed");
      setPaperAccountResult(data);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Paper account Telegram status failed");
    } finally {
      setSendingPaperAccount(false);
    }
  };

  useEffect(() => {
    if (isOpen) load();
  }, [isOpen]);

  if (!isOpen) return null;

  const telegram = health?.telegram || {};
  const macroAlerts = health?.notifications?.macro_alerts || {};
  const paperAutopilot = health?.paper_autopilot || {};
  const paperOutcomes = health?.paper_outcomes || {};
  const feeds = health?.data_feeds || {};
  const appInfo = health?.app || {};
  const database = health?.database || {};
  const backup = health?.backup || {};
  const operationalAlerts = health?.operational_alerts || {};
  const jobs = health?.schedule?.jobs || [];
  const schedule = health?.schedule || {};
  const scheduleSummary = health?.schedule?.summary || {};
  const deliveries = health?.recent_deliveries || [];
  const autopilotPerformance = paperPerformanceSummary(paperAutopilot.demo_account_after?.performance);
  const accountResultPerformance = paperPerformanceSummary(paperAccountResult?.demo_account?.performance);
  const paperPreviewBlock = previewBlockReasons(paperPreviewResult);
  const paperNextCandidate =
    paperAutopilot.next_candidate_summary ||
    (paperAutopilot.next_candidate ? { ticker: paperAutopilot.next_candidate } : null);
  const paperAutopilotReady =
    paperAutopilot.enabled &&
    paperAutopilot.loop_enabled &&
    !paperAutopilot.stale &&
    paperAutopilot.status !== "error";
  const healthProblems = (health?.problems || []).map((code: string) => ({
    code,
    ...healthProblemInfo(code),
  }));
  const criticalHealthProblems = healthProblems.filter((problem: any) => problem.tone === "red");
  const warningHealthProblems = healthProblems.filter((problem: any) => problem.tone !== "red");
  const primaryHealthProblem = criticalHealthProblems[0] || warningHealthProblems[0];
  const systemReadiness = !health
    ? "loading"
    : criticalHealthProblems.length
      ? "critical"
      : warningHealthProblems.length
        ? "attention"
        : "ready";
  const systemReadinessCopy = {
    loading: {
      label: "System wird geprüft",
      detail: "Health-Daten werden geladen und bewertet.",
      tone: "border-slate-300 bg-slate-100 text-slate-700",
    },
    critical: {
      label: "Handlung erforderlich",
      detail: `${criticalHealthProblems.length} kritische ${criticalHealthProblems.length === 1 ? "Störung" : "Störungen"} zuerst beheben.`,
      tone: "border-red-500/25 bg-red-500/10 text-red-800",
    },
    attention: {
      label: "Betrieb mit Einschränkung",
      detail: `${warningHealthProblems.length} ${warningHealthProblems.length === 1 ? "Hinweis" : "Hinweise"} prüfen.`,
      tone: "border-amber-500/25 bg-amber-500/10 text-amber-800",
    },
    ready: {
      label: "System einsatzbereit",
      detail: "Keine aktiven Health-Probleme erkannt.",
      tone: "border-emerald-500/25 bg-emerald-500/10 text-emerald-800",
    },
  }[systemReadiness];
  const nextBriefJob = [...jobs]
    .filter((job: any) => job?.next_due_at)
    .sort((a: any, b: any) => new Date(a.next_due_at).getTime() - new Date(b.next_due_at).getTime())[0];
  const lastSuccessJob = [...jobs]
    .filter((job: any) => job?.last_success_at || job?.last_sent_at)
    .sort(
      (a: any, b: any) =>
        new Date(b.last_success_at || b.last_sent_at).getTime() -
        new Date(a.last_success_at || a.last_sent_at).getTime(),
    )[0];
  const schedulerVerdict = scheduleSummary.last_error
    ? "error"
    : scheduleSummary.loop_state === "stale"
      ? "error"
    : scheduleSummary.missed_count
      ? "missed"
      : scheduleSummary.catchup_count || scheduleSummary.due_now_count
        ? "action"
        : scheduleSummary.last_success_at
          ? "healthy"
          : "unknown";
  const schedulerCopy =
    schedulerVerdict === "error"
      ? scheduleSummary.loop_state === "stale"
        ? `Scheduler-Loop ist stale: letzter Tick vor ${schedule.loop_age_minutes ?? "?"}m. Railway Prozess/Logs prüfen.`
        : `Letzter Fehler bei ${scheduleSummary.last_error_job || "Scheduler"}: ${scheduleSummary.last_error}`
      : schedulerVerdict === "missed"
        ? `${scheduleSummary.missed_count} Brief(s) heute verpasst. Prüfe Telegram, Scheduler-Loop und Railway Logs.`
        : schedulerVerdict === "action"
          ? `${scheduleSummary.catchup_count || scheduleSummary.due_now_count} Brief(s) können jetzt per Run Due/Missed gesendet werden.`
          : schedulerVerdict === "healthy"
            ? `Letzter Versand erfolgreich: ${scheduleSummary.last_success_job || "Brief"} um ${fmtDate(scheduleSummary.last_success_at)}.`
            : "Noch kein erfolgreicher Versand gespeichert. Scheduler und Telegram prüfen.";
  const nextAction =
    schedulerVerdict === "action"
      ? "Run Due/Missed klicken"
      : schedulerVerdict === "missed"
        ? "Brief direkt nachsenden"
        : schedulerVerdict === "error"
          ? "Fehlertext beheben und Health neu laden"
          : "Nächsten Termin abwarten";

  return (
    <div className="fixed inset-0 z-[210] bg-black/45 p-3 backdrop-blur-sm sm:p-6" onClick={onClose}>
      <div
        className="surface-panel ml-auto flex h-full w-full max-w-5xl flex-col overflow-hidden rounded-[2rem]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-black/8 p-5">
          <div>
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Admin Health Center
            </div>
            <h2 className="mt-1 text-3xl text-slate-900">Briefings, Scheduler und Datenfeeds</h2>
          </div>
          <div className="flex w-full min-w-0 max-w-full flex-wrap items-center justify-start gap-2 sm:w-auto sm:justify-end">
            {health?.status ? (
              <span className={`rounded-full border px-3 py-1 text-[11px] font-extrabold uppercase tracking-[0.16em] ${statusTone(health.status)}`}>
                {health.status}
              </span>
            ) : null}
            <button
              type="button"
              onClick={load}
              disabled={loading || warming || runningDue}
              className="rounded-xl border border-black/8 bg-white px-4 py-2 text-xs font-extrabold uppercase tracking-[0.16em] text-slate-700 disabled:opacity-50"
            >
              {loading ? "Lädt" : "Neu laden"}
            </button>
            <button
              type="button"
              onClick={runDueBriefs}
              disabled={loading || warming || runningDue || downloadingBackup}
              className="rounded-xl border border-black/8 bg-white px-4 py-2 text-xs font-extrabold uppercase tracking-[0.16em] text-slate-700 disabled:opacity-50"
            >
              {runningDue ? "Läuft" : "Fällige senden"}
            </button>
            <button
              type="button"
              onClick={downloadBackup}
              disabled={loading || warming || runningDue || downloadingBackup || verifyingRestore || !database.exists}
              className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-2 text-xs font-extrabold uppercase tracking-[0.16em] text-emerald-700 disabled:opacity-50"
            >
              {downloadingBackup ? "Lädt" : "DB Backup"}
            </button>
            <button
              type="button"
              onClick={verifyRestore}
              disabled={loading || warming || runningDue || downloadingBackup || verifyingRestore || !backup.latest_at}
              className="rounded-xl border border-sky-500/20 bg-sky-500/10 px-4 py-2 text-xs font-extrabold uppercase tracking-[0.16em] text-sky-700 disabled:opacity-50"
            >
              {verifyingRestore ? "Prüft" : "Restore testen"}
            </button>
            <button
              type="button"
              onClick={warmBrief}
              disabled={loading || warming || runningDue || downloadingBackup}
              className="rounded-xl border border-[var(--accent)]/20 bg-[var(--accent)] px-4 py-2 text-xs font-extrabold uppercase tracking-[0.16em] text-white disabled:opacity-50"
            >
              {warming ? "Wärmt" : "Brief vorladen"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl bg-[#101114] px-4 py-2 text-xs font-extrabold uppercase tracking-[0.16em] text-white"
            >
              Schließen
            </button>
          </div>
        </div>

        <div className="min-w-0 overflow-x-hidden overflow-y-auto p-4 sm:p-5">
          {error ? (
            <div className="mb-4 rounded-[1.2rem] border border-red-500/20 bg-red-500/10 p-4 text-sm font-semibold text-red-700">
              {error}
            </div>
          ) : null}

          {warmupResult ? (
            <div className="mb-4 rounded-[1.2rem] border border-emerald-500/20 bg-emerald-500/10 p-4 text-sm text-emerald-800">
              <span className="font-extrabold">Brief-Cache vorgeladen.</span>{" "}
              {warmupResult.headline || "Snapshot bereit"} / {warmupResult.elapsed_ms ?? "offen"}ms,
              {warmupResult.snapshot_items ?? 0} signal items, generated {fmtDate(warmupResult.generated_at)}.
            </div>
          ) : null}

          {runResult ? (
            <div className="mb-4 rounded-[1.2rem] border border-sky-500/20 bg-sky-500/10 p-4 text-sm text-sky-800">
              <span className="font-extrabold">Scheduler wurde manuell ausgeführt.</span>{" "}
              {Array.isArray(runResult) && runResult.length
                ? runResult.map((item: any) => `${item.job || "scheduler"}: ${item.status}${item.message ? ` (${item.message})` : ""}`).join(", ")
                : "Kein Brief im aktuellen Grace-Zeitfenster fällig."}
            </div>
          ) : null}

          <section className={`mb-5 rounded-[1.5rem] border p-4 ${systemReadinessCopy.tone}`}>
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] opacity-70">
                  Systemstatus
                </div>
                <div className="mt-1 text-xl font-black text-slate-950">
                  {systemReadinessCopy.label}
                </div>
                <div className="mt-1 text-sm leading-6 text-slate-700">
                  {systemReadinessCopy.detail}
                </div>
              </div>
              <div className="grid shrink-0 grid-cols-2 gap-2">
                <div className="min-w-24 rounded-xl border border-red-500/15 bg-white/75 px-3 py-2 text-center">
                  <div className="text-lg font-black text-red-700">{criticalHealthProblems.length}</div>
                  <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">Kritisch</div>
                </div>
                <div className="min-w-24 rounded-xl border border-amber-500/15 bg-white/75 px-3 py-2 text-center">
                  <div className="text-lg font-black text-amber-700">{warningHealthProblems.length}</div>
                  <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">Hinweise</div>
                </div>
              </div>
            </div>
            <div className="mt-3 rounded-xl border border-black/8 bg-white/75 px-3 py-2 text-sm text-slate-700">
              <span className="font-extrabold text-slate-900">Jetzt wichtig: </span>
              {primaryHealthProblem
                ? `${primaryHealthProblem.label}. ${primaryHealthProblem.action}`
                : "Keine Maßnahme nötig. Nächsten Brief-Termin und Telegram-Zustellung beobachten."}
            </div>
          </section>

          <div className={`mb-5 rounded-[1.5rem] border p-4 ${
            schedulerVerdict === "healthy"
              ? "border-emerald-500/20 bg-emerald-500/10"
              : schedulerVerdict === "action"
                ? "border-sky-500/20 bg-sky-500/10"
                : schedulerVerdict === "missed"
                  ? "border-amber-500/20 bg-amber-500/10"
                  : "border-red-500/20 bg-red-500/10"
          }`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-600">
                  Scheduler-Urteil
                </div>
                <div className="mt-1 text-lg font-black text-slate-900">
                  {schedulerVerdict}
                </div>
                <div className="mt-2 max-w-3xl text-sm leading-6 text-slate-700">
                  {schedulerCopy}
                </div>
              </div>
              <div className="max-w-full whitespace-normal rounded-full border border-black/8 bg-white/75 px-3 py-1 text-right text-[10px] font-extrabold uppercase leading-5 tracking-[0.14em] text-slate-700">
                Nächster Schritt: {nextAction}
              </div>
            </div>
            <div className="mt-3 grid gap-2 text-xs text-slate-600 md:grid-cols-3">
              <div>Nächster Brief: {displayValue(scheduleSummary.next_label)} / {fmtDate(scheduleSummary.next_due_at)}</div>
              <div>Loop: {displayValue(scheduleSummary.loop_state)} / {fmtDate(health?.schedule?.loop_seen_at)}</div>
              <div>
                Loop-Alter: {typeof schedule.loop_age_minutes === "number" ? `${schedule.loop_age_minutes}m` : "offen"}
                {schedule.loop_stale ? ` / stale nach ${schedule.loop_stale_after_minutes ?? "?"}m` : ""}
              </div>
              <div>Telegram: {telegram.sendable ? "sendbar" : "blockiert / fehlt"}</div>
            </div>
          </div>

          <div className="mb-5 grid min-w-0 grid-cols-[minmax(0,1fr)] gap-3 lg:grid-cols-4">
            <div className="rounded-[1.4rem] border border-black/8 bg-white/80 p-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                Nächster Brief
              </div>
              <div className="mt-2 text-lg font-black text-slate-900">
                {displayValue(scheduleSummary.next_label)}
              </div>
              <div className="mt-1 text-xs text-slate-500">{fmtDate(scheduleSummary.next_due_at)}</div>
            </div>
            <div className="rounded-[1.4rem] border border-emerald-500/15 bg-emerald-500/6 p-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-emerald-700">
                Zuletzt gesendet
              </div>
              <div className="mt-2 text-lg font-black text-slate-900">
                {scheduleSummary.last_success_job || "keiner"}
              </div>
              <div className="mt-1 text-xs text-slate-500">{fmtDate(scheduleSummary.last_success_at)}</div>
            </div>
            <div className="rounded-[1.4rem] border border-amber-500/15 bg-amber-500/6 p-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-amber-700">
                Warteschlange
              </div>
              <div className="mt-2 text-lg font-black text-slate-900">
                {scheduleSummary.due_now_count ?? 0} fällig / {scheduleSummary.catchup_count ?? 0} nachholbar / {scheduleSummary.missed_count ?? 0} verpasst
              </div>
              <div className="mt-1 text-xs text-slate-500">
                Loop {displayValue(scheduleSummary.loop_state)} / {fmtDate(health?.schedule?.loop_seen_at)}
              </div>
              {schedule.loop_stale ? (
                <div className="mt-2 rounded-lg border border-red-500/20 bg-red-500/10 px-2 py-1 text-xs font-semibold text-red-800">
                  Scheduler-Loop ist stale: letzter Tick vor {schedule.loop_age_minutes ?? "?"}m,
                  Schwelle {schedule.loop_stale_after_minutes ?? "?"}m. Railway Worker/Logs prüfen.
                </div>
              ) : null}
              {scheduleSummary.needs_manual_run ? (
                <div className="mt-2 rounded-lg border border-amber-500/20 bg-amber-500/10 px-2 py-1 text-xs font-semibold text-amber-800">
                  Run Due/Missed kann jetzt {scheduleSummary.catchup_count || scheduleSummary.due_now_count} Brief(s) nachholen.
                </div>
              ) : null}
            </div>
            <div className={`rounded-[1.4rem] border p-4 ${scheduleSummary.last_error ? "border-red-500/15 bg-red-500/6" : "border-black/8 bg-white/80"}`}>
              <div className={`text-[10px] font-extrabold uppercase tracking-[0.18em] ${scheduleSummary.last_error ? "text-red-700" : "text-slate-500"}`}>
                Letzter Fehler
              </div>
              <div className="mt-2 line-clamp-2 text-sm font-bold text-slate-900">
                {scheduleSummary.last_error || "Kein aktiver Versandfehler"}
              </div>
              <div className="mt-1 text-xs text-slate-500">
                {scheduleSummary.last_error_job ? `${scheduleSummary.last_error_job} / ` : ""}
                {fmtDate(scheduleSummary.last_error_at)}
              </div>
            </div>
          </div>

          <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-3">
            <div className={`min-w-0 rounded-[1.5rem] border p-4 ${database.persistence_ready === false ? "border-red-500/25 bg-red-500/8" : "border-black/8 bg-white/75"}`}>
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">App Release</div>
              <div className="mt-3 flex items-center justify-between gap-2">
                <div className="text-lg font-black text-slate-900">{displayValue(appInfo.version)}</div>
                <span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-[0.14em] ${appInfo.auth_configured ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700" : "border-red-500/20 bg-red-500/10 text-red-700"}`}>
                  {appInfo.auth_configured ? "auth ok" : "auth fehlt"}
                </span>
              </div>
              <div className="mt-2 text-xs leading-5 text-slate-500">
                Env: {displayValue(appInfo.environment)} / Secure cookie: {appInfo.cookie_secure ? "ja" : "nein"}
              </div>
            </div>

            <div className="min-w-0 rounded-[1.5rem] border border-black/8 bg-white/75 p-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">SQLite Datenbank</div>
              <div className="mt-3 flex items-center justify-between gap-2">
                <div className="text-lg font-black text-slate-900">{formatBytes(database.size_bytes)}</div>
                <span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-[0.14em] ${database.exists && database.writable && database.quick_check === "ok" && database.persistence_ready !== false ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700" : "border-red-500/20 bg-red-500/10 text-red-700"}`}>
                  {database.persistence_ready === false ? "Volume fehlt" : database.exists && database.quick_check === "ok" ? "ok" : "prüfen"}
                </span>
              </div>
              <div className="mt-2 truncate text-xs leading-5 text-slate-500" title={database.path || ""}>
                {database.path || "kein Pfad"}
              </div>
              <div className="mt-1 text-xs leading-5 text-slate-500">
                Schreibbar: {database.writable ? "ja" : "nein"} / Quick check: {displayValue(database.quick_check)}
              </div>
              <div className="mt-1 truncate text-xs leading-5 text-slate-500" title={database.identity || ""}>
                DB-ID: {database.identity ? String(database.identity).slice(0, 12) : "noch nicht gesetzt"} / seit {fmtDate(database.initialized_at)}
              </div>
              <div className="mt-1 text-xs leading-5 text-slate-500">
                {database.counts?.portfolios ?? 0} Portfolios / {database.counts?.holdings ?? 0} Positionen / {database.counts?.paper_trades ?? 0} Paper-Trades / {database.counts?.forecasts ?? 0} Forecasts
              </div>
              {database.railway_runtime ? (
                <div className={`mt-2 rounded-lg border px-2.5 py-2 text-xs font-semibold leading-5 ${database.persistence_ready ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-800" : "border-red-500/20 bg-red-500/10 text-red-800"}`}>
                  {database.persistence_ready
                    ? `Volume ${database.volume_name} aktiv unter ${database.volume_mount_path}.`
                    : "Kein passendes Railway Volume erkannt. Volume an diesen Service mit Mount Path /app/data anhängen; sonst gehen Portfolio und Lerndaten beim Deploy verloren."}
                </div>
              ) : null}
            </div>

            <div className={`min-w-0 rounded-[1.5rem] border p-4 ${backup.latest_at && backup.restore_test_last_success_at && !backup.last_error && !backup.restore_test_last_error ? "border-emerald-500/15 bg-emerald-500/6" : "border-amber-500/20 bg-amber-500/8"}`}>
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">Backup & Restore</div>
              <div className="mt-3 flex items-center justify-between gap-2">
                <div className="text-lg font-black text-slate-900">{backup.backup_count ?? 0} Sicherungen</div>
                <span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-[0.14em] ${backup.latest_at && backup.restore_test_last_success_at && !backup.last_error && !backup.restore_test_last_error ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700" : "border-amber-500/20 bg-amber-500/10 text-amber-700"}`}>
                  {backup.restore_test_last_success_at ? "restore ok" : "prüfen"}
                </span>
              </div>
              <div className="mt-2 text-xs leading-5 text-slate-500">
                Letztes Backup: {fmtDate(backup.latest_at)} ({backup.latest_age_hours ?? "–"}h)
              </div>
              <div className="mt-1 text-xs leading-5 text-slate-500">
                Restore-Test: {fmtDate(backup.restore_test_last_success_at)} / Rhythmus {backup.restore_test_interval_days ?? 7} Tage
              </div>
              <div className="mt-1 truncate text-xs leading-5 text-slate-500" title={backup.directory || ""}>
                {backup.directory || "Backup-Verzeichnis fehlt"} / Retention {backup.retention_count ?? 14}
              </div>
              {backup.last_error || backup.restore_test_last_error ? (
                <div className="mt-2 text-xs font-semibold text-red-700">{backup.last_error || backup.restore_test_last_error}</div>
              ) : null}
            </div>

            <div className="min-w-0 rounded-[1.5rem] border border-black/8 bg-white/75 p-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">Telegram</div>
              <div className="mt-3 flex items-center justify-between gap-2">
                <div className="text-lg font-black text-slate-900">{displayValue(telegram.status)}</div>
                <span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-[0.14em] ${statusTone(telegram.status)}`}>
                  {telegram.sendable ? "sendbar" : "blockiert"}
                </span>
              </div>
              <div className="mt-2 text-xs leading-5 text-slate-500">
                Chat: {displayValue(telegram.chat_id, "fehlt")}
              </div>
              {telegram.error ? <div className="mt-2 text-xs text-red-700">{telegram.error}</div> : null}
              <div className="mt-2 text-xs leading-5 text-slate-500">
                Betriebsmonitor: {displayValue(operationalAlerts.status, "noch nicht gelaufen")} / {fmtDate(operationalAlerts.checked_at)}
              </div>
            </div>

            <div className={`min-w-0 rounded-[1.5rem] border p-4 ${
              paperAutopilotReady
                ? "border-emerald-500/15 bg-emerald-500/6"
                : "border-amber-500/20 bg-amber-500/8"
            }`}>
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                Paper Autopilot
              </div>
              <div className="mt-3 flex items-center justify-between gap-2">
                <div className="text-lg font-black text-slate-900">
                  {paperAutopilot.enabled ? displayValue(paperAutopilot.status) : "deaktiviert"}
                </div>
                <span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-[0.14em] ${
                  paperAutopilotReady
                    ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700"
                    : "border-amber-500/20 bg-amber-500/10 text-amber-700"
                }`}>
                  {paperAutopilot.stale ? "überfällig" : paperAutopilot.loop_enabled ? "Loop aktiv" : "Loop aus"}
                </span>
              </div>
              <div className="mt-2 text-xs leading-5 text-slate-500">
                Letzter Lauf {fmtDate(paperAutopilot.checked_at)}
                {typeof paperAutopilot.age_minutes === "number" ? ` / vor ${paperAutopilot.age_minutes}m` : ""}
              </div>
              <div className="mt-1 text-xs leading-5 text-slate-500">
                Nächste Prüfung {fmtDate(paperAutopilot.next_check_at)} / Cooldown {paperAutopilot.cooldown_minutes ?? "?"}m
              </div>
              <div className="mt-1 text-xs leading-5 text-slate-500">
                Zuletzt {paperAutopilot.opened_count ?? 0} eröffnet / {paperAutopilot.selected_count ?? 0} ausgewählt
              </div>
              {paperAutopilot.demo_account_after?.equity_value ? (
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  <div className="rounded-lg border border-black/8 bg-white/70 px-2.5 py-2 text-xs leading-5 text-slate-600">
                    Equity <span className="font-extrabold text-slate-900">{formatMoney(paperAutopilot.demo_account_after.equity_value)}</span>
                  </div>
                  <div className="rounded-lg border border-black/8 bg-white/70 px-2.5 py-2 text-xs leading-5 text-slate-600">
                    Frei <span className="font-extrabold text-slate-900">{formatMoney(paperAutopilot.demo_account_after.cash_available_value)}</span>
                  </div>
                  <div className="rounded-lg border border-black/8 bg-white/70 px-2.5 py-2 text-xs leading-5 text-slate-600">
                    Investiert <span className="font-extrabold text-slate-900">{formatMoney(paperAutopilot.demo_account_after.open_exposure_value)}</span>
                  </div>
                  <div className="rounded-lg border border-black/8 bg-white/70 px-2.5 py-2 text-xs leading-5 text-slate-600">
                    P/L <span className={`font-extrabold ${Number(paperAutopilot.demo_account_after.net_pnl_value || 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                      {formatMoney(paperAutopilot.demo_account_after.net_pnl_value)}
                    </span>
                  </div>
                  {autopilotPerformance ? (
                    <div className="rounded-lg border border-black/8 bg-white/70 px-2.5 py-2 text-xs leading-5 text-slate-600 sm:col-span-2">
                      Lernqualität <span className="font-extrabold text-slate-900">{autopilotPerformance.sample}</span>
                      {" / "}PF <span className="font-extrabold text-slate-900">{autopilotPerformance.profitFactor}</span>
                      {" / "}Erwartung <span className="font-extrabold text-slate-900">{autopilotPerformance.expectancy}</span>
                      {" / "}{autopilotPerformance.evidence}
                    </div>
                  ) : null}
                </div>
              ) : null}
              {paperAutopilot.last_opened?.length ? (
                <div className="mt-2 rounded-lg border border-emerald-500/15 bg-white/70 px-2.5 py-2 text-xs leading-5 text-slate-700">
                  <div className="font-extrabold uppercase tracking-[0.12em] text-emerald-700">Zuletzt geöffnet</div>
                  <div className="mt-1 space-y-1">
                    {paperAutopilot.last_opened.slice(0, 3).map((item: any) => (
                      <div key={`${item.ticker}-${item.direction}`} className="grid gap-1 rounded-md border border-black/5 bg-white/60 px-2 py-1.5 sm:grid-cols-[1fr_auto] sm:items-center">
                        <span className="font-bold text-slate-900">
                          {item.ticker} / {item.direction || "long"}
                          {item.setup_type ? <span className="ml-1 font-semibold text-slate-500">/{item.setup_type}</span> : null}
                        </span>
                        <span className="font-semibold text-slate-600">
                          {formatMoney(item.notional_value)}
                          {item.score ? ` / Score ${item.score}` : ""}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
              {paperAutopilot.last_selected?.length && !paperAutopilot.last_opened?.length ? (
                <div className="mt-2 rounded-lg border border-sky-500/15 bg-white/70 px-2.5 py-2 text-xs leading-5 text-slate-700">
                  <div className="font-extrabold uppercase tracking-[0.12em] text-sky-700">Letzte Kandidaten</div>
                  <div className="mt-1 space-y-1">
                    {paperAutopilot.last_selected.slice(0, 3).map((item: any) => (
                      <div key={`${item.ticker}-${item.direction}`} className="grid gap-1 rounded-md border border-black/5 bg-white/60 px-2 py-1.5 sm:grid-cols-[1fr_auto] sm:items-center">
                        <span className="font-bold text-slate-900">
                          {item.ticker} / {item.direction || "long"}
                          {item.setup_type ? <span className="ml-1 font-semibold text-slate-500">/{item.setup_type}</span> : null}
                        </span>
                        <span className="font-semibold text-slate-600">
                          {item.score ? `Score ${item.score}` : formatMoney(item.notional_value)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
              {paperAutopilot.message ? (
                <div className="mt-2 line-clamp-3 text-xs font-semibold leading-5 text-slate-700">
                  {paperAutopilot.message}
                </div>
              ) : null}
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                <button
                  type="button"
                  onClick={() => runPaperPreview("strict")}
                  disabled={loading || !!runningPaperPreview || sendingPaperAccount}
                  className="rounded-xl border border-black/8 bg-white px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-700 disabled:opacity-50"
                >
                  {runningPaperPreview === "strict" ? "Prüft" : "Strict prüfen"}
                </button>
                <button
                  type="button"
                  onClick={() => runPaperPreview("learn")}
                  disabled={loading || !!runningPaperPreview || sendingPaperAccount}
                  className="rounded-xl border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-amber-800 disabled:opacity-50"
                >
                  {runningPaperPreview === "learn" ? "Prüft" : "Lernen prüfen"}
                </button>
                <button
                  type="button"
                  onClick={sendPaperAccountStatus}
                  disabled={loading || !!runningPaperPreview || sendingPaperAccount}
                  className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-emerald-800 disabled:opacity-50 sm:col-span-2"
                >
                  {sendingPaperAccount ? "Sendet" : "Kontostand per Telegram"}
                </button>
              </div>
              {paperAccountResult ? (
                <div className="mt-3 rounded-[1rem] border border-emerald-500/15 bg-emerald-500/10 p-3 text-xs leading-5 text-slate-700">
                  <div className="font-extrabold text-slate-900">
                    Telegram-Kontostand: {paperAccountResult.status || "ok"}
                  </div>
                  <div>
                    Equity {formatMoney(paperAccountResult.demo_account?.equity)} /
                    P/L {formatMoney(paperAccountResult.demo_account?.net_pnl_value)} /
                    offen {paperAccountResult.demo_account?.open_trade_count ?? 0}
                  </div>
                  {accountResultPerformance ? (
                    <div className="mt-1 font-semibold text-slate-700">
                      Lernqualität: {accountResultPerformance.sample} / PF {accountResultPerformance.profitFactor} /
                      Erwartung {accountResultPerformance.expectancy} / Treffer {accountResultPerformance.winRate}
                    </div>
                  ) : null}
                  {paperAccountResult.demo_account?.day_action ? (
                    <div className="mt-1 font-semibold text-emerald-800">
                      Tagesaktion: {paperAccountResult.demo_account.day_action}
                    </div>
                  ) : null}
                </div>
              ) : null}
              {paperPreviewResult ? (
                <div className="mt-3 rounded-[1rem] border border-sky-500/15 bg-sky-500/10 p-3 text-xs leading-5 text-slate-700">
                  <div className="mb-2 inline-flex rounded-full border border-black/8 bg-white/75 px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                    {paperPreviewResult.mode === "learn" ? "Learning Preview" : "Strict Preview"} / keine Ausführung
                  </div>
                  <div className="font-extrabold text-slate-900">
                    {paperPreviewResult.selected?.length
                      ? `${paperPreviewResult.selected.length} Kandidat(en) paper-ready`
                      : "Kein Kandidat paper-ready"}
                  </div>
                  <div className="mt-1">
                    {paperPreviewResult.message || "Preview abgeschlossen."}
                  </div>
                  {paperPreviewResult.selected_capital ? (
                    <div className="mt-2 rounded-lg border border-black/8 bg-white/70 px-2 py-1">
                      Kapital: {formatMoney(paperPreviewResult.selected_capital.notional_value)} geplant /
                      Risiko {formatMoney(paperPreviewResult.selected_capital.max_loss_value)}
                    </div>
                  ) : null}
                  {paperPreviewResult.selected?.[0]?.ticker ? (
                    <div className="mt-2 rounded-lg border border-emerald-500/15 bg-white/70 px-2 py-1">
                      Top: <span className="font-extrabold">{paperPreviewResult.selected[0].ticker}</span>
                      {paperPreviewResult.selected[0].score ? ` / Score ${paperPreviewResult.selected[0].score}` : ""}
                    </div>
                  ) : null}
                  {paperPreviewResult.blocker_summary?.next_best_rejected?.ticker ? (
                    <div className="mt-2 rounded-lg border border-amber-500/15 bg-white/70 px-2.5 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <span>
                          Geblockt: <span className="font-extrabold">{paperPreviewBlock.blocked.ticker}</span>
                        </span>
                        {paperPreviewBlock.blocked.score ? (
                          <span className="rounded-full border border-black/8 bg-white px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.12em] text-slate-500">
                            Score {paperPreviewBlock.blocked.score}
                          </span>
                        ) : null}
                      </div>
                      {paperPreviewBlock.reasons.length ? (
                        <div className="mt-2 space-y-1">
                          {paperPreviewBlock.reasons.map((reason: string) => (
                            <div key={reason} className="rounded-md border border-amber-500/10 bg-amber-500/8 px-2 py-1 text-amber-900">
                              {reason}
                            </div>
                          ))}
                        </div>
                      ) : null}
                      {paperPreviewBlock.blocked.missing_to_trade ? (
                        <div className="mt-2 font-semibold text-amber-900">
                          Fehlt: {paperPreviewBlock.blocked.missing_to_trade}
                        </div>
                      ) : null}
                      {paperPreviewBlock.scoreGap > 0 ? (
                        <div className="mt-1 text-slate-600">
                          Score-Lücke: {paperPreviewBlock.scoreGap.toFixed(1)} Punkte bis{" "}
                          {paperPreviewResult.mode === "learn" ? "Lerntrade" : "Strict-Trade"}.
                        </div>
                      ) : null}
                      {paperPreviewBlock.blocked.next_action ? (
                        <div className="mt-2 rounded-md border border-black/8 bg-white px-2 py-1 font-semibold text-slate-800">
                          Nächster Schritt: {paperPreviewBlock.blocked.next_action}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              ) : null}
              {paperNextCandidate ? (
                <div className="mt-2 rounded-lg border border-amber-500/15 bg-white/75 px-2.5 py-2 text-xs leading-5 text-slate-700">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="font-extrabold uppercase tracking-[0.12em] text-amber-800">
                      Nächster prüfbarer Kandidat
                    </div>
                    {paperNextCandidate.score ? (
                      <span className="rounded-full border border-black/8 bg-white px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.12em] text-slate-500">
                        Score {paperNextCandidate.score}
                      </span>
                    ) : null}
                  </div>
                  <div className="mt-1 font-extrabold text-slate-950">
                    {paperNextCandidate.ticker}
                    {paperNextCandidate.direction ? ` / ${paperNextCandidate.direction}` : ""}
                    {paperNextCandidate.setup_type ? ` / ${paperNextCandidate.setup_type}` : ""}
                  </div>
                  <div className="mt-1 text-slate-600">
                    Geplant {formatMoney(paperNextCandidate.notional_value)} /
                    Max. Paper-Risiko {formatMoney(paperNextCandidate.max_loss_value)}
                  </div>
                  {paperNextCandidate.thesis ? (
                    <div className="mt-1 line-clamp-2 font-semibold text-slate-700">
                      These: {paperNextCandidate.thesis}
                    </div>
                  ) : null}
                  {paperAutopilot.block_reasons?.length ? (
                    <div className="mt-2 space-y-1">
                      {paperAutopilot.block_reasons.map((reason: string) => (
                        <div key={reason} className="rounded-md border border-amber-500/10 bg-amber-500/8 px-2 py-1 text-amber-900">
                          Block: {reason}
                        </div>
                      ))}
                    </div>
                  ) : null}
                  <div className="mt-2 rounded-md border border-black/8 bg-white px-2 py-1 font-semibold text-slate-800">
                    Nur Paper: erst Trigger, Stop, Ziel, Positionsgröße und Outcome-Lernen prüfen.
                  </div>
                </div>
              ) : null}
            </div>

            <div className="min-w-0 rounded-[1.5rem] border border-black/8 bg-white/75 p-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                Paper Outcome Lernen
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <div className="rounded-lg border border-black/8 bg-white/70 px-2.5 py-2">
                  <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">Geprüft</div>
                  <div className="mt-1 text-lg font-black text-slate-900">{paperOutcomes.summary?.evaluated ?? 0}</div>
                </div>
                <div className="rounded-lg border border-black/8 bg-white/70 px-2.5 py-2">
                  <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">Offen</div>
                  <div className="mt-1 text-lg font-black text-slate-900">{paperOutcomes.summary?.pending ?? 0}</div>
                </div>
                <div className="rounded-lg border border-black/8 bg-white/70 px-2.5 py-2">
                  <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">Treffer</div>
                  <div className="mt-1 text-lg font-black text-slate-900">{paperOutcomes.summary?.hit_rate ?? 0}%</div>
                </div>
                <div className="rounded-lg border border-black/8 bg-white/70 px-2.5 py-2">
                  <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">Misses</div>
                  <div className="mt-1 text-lg font-black text-slate-900">{paperOutcomes.summary?.misses ?? 0}</div>
                </div>
              </div>
              <div className="mt-2 text-xs leading-5 text-slate-500">
                Letzter Check {fmtDate(paperOutcomes.last_run?.checked_at)} /
                Status {displayValue(paperOutcomes.last_run?.status)}
                {paperOutcomes.last_run?.due != null ? ` / fällig ${paperOutcomes.last_run.due}` : ""}
              </div>
              {paperOutcomes.status && paperOutcomes.status !== "ok" ? (
                <div className="mt-2 rounded-lg border border-amber-500/15 bg-amber-500/10 px-2.5 py-2 text-xs leading-5 text-amber-900">
                  <div className="font-extrabold">Outcome-Lernen braucht Aufmerksamkeit: {paperOutcomes.status}</div>
                  <div>
                    Offen {paperOutcomes.summary?.pending ?? 0}
                    {paperOutcomes.age_minutes != null ? ` / letzter Check vor ${paperOutcomes.age_minutes} Min.` : " / noch kein Check"}
                    {paperOutcomes.stale_after_minutes ? ` / Limit ${paperOutcomes.stale_after_minutes} Min.` : ""}
                  </div>
                </div>
              ) : null}
              {paperOutcomes.last_run?.pending_data ? (
                <div className="mt-2 rounded-lg border border-amber-500/15 bg-amber-500/10 px-2.5 py-2 text-xs font-semibold text-amber-800">
                  {paperOutcomes.last_run.pending_data} Outcome(s) warten auf Kursdaten. Diese Trades noch nicht bewerten.
                </div>
              ) : null}
              <button
                type="button"
                onClick={evaluatePaperOutcomes}
                disabled={loading || evaluatingPaperOutcomes}
                className="mt-3 w-full rounded-xl border border-black/8 bg-white px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-700 disabled:opacity-50"
              >
                {evaluatingPaperOutcomes ? "Prüft" : "Outcomes prüfen"}
              </button>
              {paperOutcomeResult ? (
                <div className="mt-2 rounded-lg border border-sky-500/15 bg-sky-500/10 px-2.5 py-2 text-xs leading-5 text-slate-700">
                  <div className="font-extrabold text-slate-900">
                    Outcome-Check: {paperOutcomeResult.status || "ok"}
                  </div>
                  <div>
                    Fällig {paperOutcomeResult.due ?? 0} / ausgewertet {paperOutcomeResult.evaluated ?? 0} /
                    Daten offen {paperOutcomeResult.pending_data ?? 0}
                  </div>
                  {paperOutcomeResult.paper_learning_alerts?.status ? (
                    <div className="mt-1 text-slate-500">
                      Telegram Learning: {paperOutcomeResult.paper_learning_alerts.status}
                    </div>
                  ) : null}
                </div>
              ) : null}
              {paperOutcomes.top_errors?.length ? (
                <div className="mt-2 space-y-1">
                  {paperOutcomes.top_errors.slice(0, 3).map((item: any) => (
                    <div key={item.error_tag} className="flex items-center justify-between gap-2 rounded-lg border border-red-500/10 bg-red-500/6 px-2.5 py-1 text-xs text-red-800">
                      <span>{item.error_tag}</span>
                      <span className="font-extrabold">{item.count}</span>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>

            <div className="min-w-0 rounded-[1.5rem] border border-black/8 bg-white/75 p-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">Macro Alert Audit</div>
              <div className="mt-3 text-sm font-black text-slate-900">
                {macroAlerts.last_audit?.eligible ?? 0} freigegeben / {macroAlerts.last_audit?.quality_passed ?? 0} Gate bestanden
              </div>
              <div className="mt-2 text-xs leading-5 text-slate-500">
                {macroAlerts.last_audit?.candidates ?? 0} Kandidaten / {macroAlerts.last_audit?.already_sent ?? 0} bereits gesendet / {macroAlerts.last_audit?.cooldown_blocked ?? 0} Cooldown-blockiert
              </div>
              <div className="mt-1 text-xs text-slate-500">
                Letzter Scan {fmtDate(macroAlerts.last_audit?.scanned_at)}
              </div>
            </div>

            {Object.entries(feeds).map(([key, feed]: [string, any]) => (
              <div key={key} className="min-w-0 rounded-[1.5rem] border border-black/8 bg-white/75 p-4">
                <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                  {key.replace("_", " ")}
                </div>
                <div className="mt-3 flex items-center justify-between gap-2">
                  <div className="text-lg font-black text-slate-900">{displayValue(feed.status)}</div>
                  <span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-[0.14em] ${statusTone(feed.status)}`}>
                    {displayValue(feed.status)}
                  </span>
                </div>
                <div className="mt-2 text-xs leading-5 text-slate-500">
                  {feed.generated_at ? `Generated ${fmtDate(feed.generated_at)}` : null}
                  {feed.sample ? `${feed.sample} ${feed.price ?? ""}` : null}
                  {feed.quotes != null ? `${feed.quotes} quotes` : null}
                  {feed.error ? feed.error : null}
                </div>
              </div>
            ))}
          </div>

          <div className="mt-5 grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
            <section className="min-w-0 rounded-[1.6rem] border border-black/8 bg-white/75 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">Scheduled Briefs</div>
                  <div className="mt-1 text-sm text-slate-500">
                    Timezone {health?.timezone || "Europe/Berlin"} / {health?.schedule?.weekdays}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    Last check {fmtDate(health?.schedule?.last_checked_at)} / loop {fmtDate(health?.schedule?.loop_seen_at)} / grace {health?.schedule?.delivery_grace_minutes ?? "offen"}m
                  </div>
                  {health?.schedule?.loop_error ? (
                    <div className="mt-1 text-xs font-semibold text-red-700">
                      Scheduler error: {health.schedule.loop_error}
                    </div>
                  ) : null}
                </div>
                <span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-[0.14em] ${health?.schedule?.enabled ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700" : "border-red-500/20 bg-red-500/10 text-red-700"}`}>
                  {health?.schedule?.enabled ? "enabled" : "disabled"}
                </span>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <div className="rounded-[1.1rem] border border-emerald-500/15 bg-emerald-500/10 p-3">
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-emerald-700">
                    Letzter erfolgreicher Brief
                  </div>
                  <div className="mt-1 text-sm font-black text-slate-900">
                    {lastSuccessJob?.label || scheduleSummary.last_success_job || "Noch keiner"}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    {fmtDate(lastSuccessJob?.last_success_at || lastSuccessJob?.last_sent_at || scheduleSummary.last_success_at)}
                  </div>
                </div>
                <div className="rounded-[1.1rem] border border-sky-500/15 bg-sky-500/10 p-3">
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-sky-700">
                    Nächster geplanter Brief
                  </div>
                  <div className="mt-1 text-sm font-black text-slate-900">
                    {nextBriefJob?.label || "offen"}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    {nextBriefJob ? `${fmtDate(nextBriefJob.next_due_at)} / Plan ${nextBriefJob.time}` : "Keine nächste Ausführung berechnet"}
                  </div>
                </div>
              </div>
              <div className="mt-4 grid gap-2 md:grid-cols-2">
                {jobs.map((job: any) => (
                  <div key={job.job_key} className="rounded-[1.1rem] border border-black/8 bg-white p-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="font-extrabold text-slate-900">{job.label}</div>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${
                        job.last_status === "blocked"
                          ? "bg-red-500/10 text-red-700"
                          : job.sent_today
                          ? "bg-emerald-500/10 text-emerald-700"
                          : job.due_now
                            ? "bg-amber-500/10 text-amber-700"
                            : job.catchup_available
                              ? "bg-sky-500/10 text-sky-700"
                            : job.missed_today
                              ? "bg-red-500/10 text-red-700"
                              : "bg-slate-500/10 text-slate-500"
                      }`}>
                        {jobStateLabel(job)}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-slate-500">Plan {job.time} / nächster Termin {fmtDate(job.next_due_at)}</div>
                    <div className="mt-1 text-xs text-slate-500">Heute fällig {fmtDate(job.scheduled_at_today)} / Grace bis {fmtDate(job.grace_until)}</div>
                    {job.minutes_late != null ? (
                      <div className="mt-1 text-xs text-slate-500">{job.minutes_late} Minuten verspätet</div>
                    ) : null}
                    {job.catchup_available ? (
                      <div className="mt-2 rounded-lg border border-sky-500/15 bg-sky-500/10 px-2 py-1 text-xs font-semibold text-sky-700">
                        Noch in Grace-Zeit: automatisch oder per Run Due/Missed nachsendbar.
                      </div>
                    ) : null}
                    <div className="mt-1 text-xs text-slate-500">
                      Letzter Erfolg {fmtDate(job.last_success_at || job.last_sent_at)}
                    </div>
                    {job.last_status ? (
                      <div className="mt-1 text-xs text-slate-500">
                        Letzter Status {job.last_status} / {fmtDate(job.last_status_updated_at)}
                      </div>
                    ) : null}
                    {job.last_message ? (
                      <div className="mt-2 rounded-lg border border-black/8 bg-white/75 px-2 py-1 text-xs font-semibold text-slate-700">
                        {job.last_message}
                      </div>
                    ) : null}
                    {job.last_error ? (
                      <div className="mt-2 rounded-lg border border-red-500/15 bg-red-500/10 px-2 py-1 text-xs font-semibold text-red-700">
                        {job.last_error}
                      </div>
                    ) : null}
                    <div className="mt-3 flex justify-end">
                      <button
                        type="button"
                        onClick={() => sendJobBrief(job)}
                        disabled={loading || warming || runningDue || downloadingBackup || !!sendingSession}
                        className="rounded-full border border-black/8 bg-[#101114] px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.14em] text-white disabled:opacity-50"
                      >
                        {sendingSession === job.job_key ? "Sendet" : "Jetzt senden"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="min-w-0 rounded-[1.6rem] border border-black/8 bg-white/75 p-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                Letzte Zustellungen
              </div>
              <div className="mt-4 space-y-2">
                {deliveries.length ? deliveries.map((item: any) => (
                  <div key={item.event_key} className="rounded-[1rem] border border-black/8 bg-white p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="text-sm font-bold text-slate-900">{item.title}</div>
                      {item.metadata?.impact_score != null ? (
                        <span className="shrink-0 rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-[10px] font-extrabold text-amber-700">
                          Impact {item.metadata.impact_score}
                        </span>
                      ) : null}
                    </div>
                    <div className="mt-1 text-xs text-slate-500">{item.category} / {fmtDate(item.sent_at)}</div>
                    {item.metadata?.source_label || item.metadata?.source_quality ? (
                      <div className="mt-1 text-xs text-slate-500">
                        Quelle: {item.metadata.source_label || "offen"}
                        {item.metadata.source_quality ? ` / ${item.metadata.source_quality}` : ""}
                      </div>
                    ) : null}
                    {item.metadata?.affected_assets?.length ? (
                      <div className="mt-1 truncate text-xs text-slate-500" title={item.metadata.affected_assets.join(", ")}>
                        Betroffen: {item.metadata.affected_assets.join(", ")}
                      </div>
                    ) : null}
                  </div>
                )) : (
                  <div className="rounded-[1rem] border border-black/8 bg-white p-3 text-sm text-slate-500">
                    Noch keine Zustellungen gespeichert.
                  </div>
                )}
              </div>
            </section>
          </div>

          {healthProblems.length ? (
            <div className="mt-5 rounded-[1.4rem] border border-amber-500/20 bg-amber-500/10 p-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-amber-800">
                Health Aufmerksamkeit
              </div>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                {healthProblems.map((problem: any) => (
                  <div
                    key={problem.code}
                    className={`rounded-[1rem] border bg-white/80 p-3 text-sm ${
                      problem.tone === "red"
                        ? "border-red-500/15 text-red-800"
                        : "border-amber-500/15 text-amber-800"
                    }`}
                  >
                    <div className="font-extrabold">{problem.label}</div>
                    <div className="mt-1 text-xs leading-5 text-slate-600">{problem.action}</div>
                    <div className="mt-2 inline-flex rounded-full border border-black/8 bg-white px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.12em] text-slate-500">
                      {problem.code}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
