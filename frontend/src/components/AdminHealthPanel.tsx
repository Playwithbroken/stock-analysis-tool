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

function jobStateLabel(job: any) {
  if (job.sent_today) return "heute gesendet";
  if (job.due_now) return "jetzt faellig";
  if (job.catchup_available) return "nachholbar";
  if (job.missed_today) return "verpasst";
  return "wartet";
}

export default function AdminHealthPanel({ isOpen, onClose }: AdminHealthPanelProps) {
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [warming, setWarming] = useState(false);
  const [runningDue, setRunningDue] = useState(false);
  const [warmupResult, setWarmupResult] = useState<any>(null);
  const [runResult, setRunResult] = useState<any>(null);
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

  useEffect(() => {
    if (isOpen) load();
  }, [isOpen]);

  if (!isOpen) return null;

  const telegram = health?.telegram || {};
  const feeds = health?.data_feeds || {};
  const jobs = health?.schedule?.jobs || [];
  const schedule = health?.schedule || {};
  const scheduleSummary = health?.schedule?.summary || {};
  const deliveries = health?.recent_deliveries || [];
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
        ? `Scheduler-Loop ist stale: letzter Tick vor ${schedule.loop_age_minutes ?? "?"}m. Railway Prozess/Logs pruefen.`
        : `Letzter Fehler bei ${scheduleSummary.last_error_job || "Scheduler"}: ${scheduleSummary.last_error}`
      : schedulerVerdict === "missed"
        ? `${scheduleSummary.missed_count} Brief(s) heute verpasst. Pruefe Telegram, Scheduler-Loop und Railway Logs.`
        : schedulerVerdict === "action"
          ? `${scheduleSummary.catchup_count || scheduleSummary.due_now_count} Brief(s) koennen jetzt per Run Due/Missed gesendet werden.`
          : schedulerVerdict === "healthy"
            ? `Letzter Versand erfolgreich: ${scheduleSummary.last_success_job || "Brief"} um ${fmtDate(scheduleSummary.last_success_at)}.`
            : "Noch kein erfolgreicher Versand gespeichert. Scheduler und Telegram pruefen.";
  const nextAction =
    schedulerVerdict === "action"
      ? "Run Due/Missed klicken"
      : schedulerVerdict === "missed"
        ? "Warm Brief Now, danach manuell senden"
        : schedulerVerdict === "error"
          ? "Fehlertext beheben und Health neu laden"
          : "Naechsten Termin abwarten";

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
          <div className="flex items-center gap-2">
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
              {loading ? "Laedt" : "Neu laden"}
            </button>
            <button
              type="button"
              onClick={runDueBriefs}
              disabled={loading || warming || runningDue}
              className="rounded-xl border border-black/8 bg-white px-4 py-2 text-xs font-extrabold uppercase tracking-[0.16em] text-slate-700 disabled:opacity-50"
            >
              {runningDue ? "Laeuft" : "Faellige senden"}
            </button>
            <button
              type="button"
              onClick={warmBrief}
              disabled={loading || warming || runningDue}
              className="rounded-xl border border-[var(--accent)]/20 bg-[var(--accent)] px-4 py-2 text-xs font-extrabold uppercase tracking-[0.16em] text-white disabled:opacity-50"
            >
              {warming ? "Waermt" : "Brief vorladen"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl bg-[#101114] px-4 py-2 text-xs font-extrabold uppercase tracking-[0.16em] text-white"
            >
              Schliessen
            </button>
          </div>
        </div>

        <div className="overflow-y-auto p-5">
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
              <span className="font-extrabold">Scheduler wurde manuell ausgefuehrt.</span>{" "}
              {Array.isArray(runResult) && runResult.length
                ? runResult.map((item: any) => `${item.job || "scheduler"}: ${item.status}${item.message ? ` (${item.message})` : ""}`).join(", ")
                : "Kein Brief im aktuellen Grace-Zeitfenster faellig."}
            </div>
          ) : null}

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
              <div className="rounded-full border border-black/8 bg-white/75 px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-700">
                Naechster Schritt: {nextAction}
              </div>
            </div>
            <div className="mt-3 grid gap-2 text-xs text-slate-600 md:grid-cols-3">
              <div>Naechster Brief: {displayValue(scheduleSummary.next_label)} / {fmtDate(scheduleSummary.next_due_at)}</div>
              <div>Loop: {displayValue(scheduleSummary.loop_state)} / {fmtDate(health?.schedule?.loop_seen_at)}</div>
              <div>
                Loop-Alter: {typeof schedule.loop_age_minutes === "number" ? `${schedule.loop_age_minutes}m` : "offen"}
                {schedule.loop_stale ? ` / stale nach ${schedule.loop_stale_after_minutes ?? "?"}m` : ""}
              </div>
              <div>Telegram: {telegram.sendable ? "sendbar" : "blockiert / fehlt"}</div>
            </div>
          </div>

          <div className="mb-5 grid gap-3 lg:grid-cols-4">
            <div className="rounded-[1.4rem] border border-black/8 bg-white/80 p-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                Naechster Brief
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
                {scheduleSummary.due_now_count ?? 0} faellig / {scheduleSummary.catchup_count ?? 0} nachholbar / {scheduleSummary.missed_count ?? 0} verpasst
              </div>
              <div className="mt-1 text-xs text-slate-500">
                Loop {displayValue(scheduleSummary.loop_state)} / {fmtDate(health?.schedule?.loop_seen_at)}
              </div>
              {schedule.loop_stale ? (
                <div className="mt-2 rounded-lg border border-red-500/20 bg-red-500/10 px-2 py-1 text-xs font-semibold text-red-800">
                  Scheduler-Loop ist stale: letzter Tick vor {schedule.loop_age_minutes ?? "?"}m,
                  Schwelle {schedule.loop_stale_after_minutes ?? "?"}m. Railway Worker/Logs pruefen.
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

          <div className="grid gap-4 lg:grid-cols-3">
            <div className="rounded-[1.5rem] border border-black/8 bg-white/75 p-4">
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
            </div>

            {Object.entries(feeds).map(([key, feed]: [string, any]) => (
              <div key={key} className="rounded-[1.5rem] border border-black/8 bg-white/75 p-4">
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

          <div className="mt-5 grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
            <section className="rounded-[1.6rem] border border-black/8 bg-white/75 p-4">
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
                    Naechster geplanter Brief
                  </div>
                  <div className="mt-1 text-sm font-black text-slate-900">
                    {nextBriefJob?.label || "offen"}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    {nextBriefJob ? `${fmtDate(nextBriefJob.next_due_at)} / Plan ${nextBriefJob.time}` : "Keine naechste Ausfuehrung berechnet"}
                  </div>
                </div>
              </div>
              <div className="mt-4 grid gap-2 md:grid-cols-2">
                {jobs.map((job: any) => (
                  <div key={job.job_key} className="rounded-[1.1rem] border border-black/8 bg-white p-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="font-extrabold text-slate-900">{job.label}</div>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${
                        job.sent_today
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
                    <div className="mt-1 text-xs text-slate-500">Plan {job.time} / naechster Termin {fmtDate(job.next_due_at)}</div>
                    <div className="mt-1 text-xs text-slate-500">Heute faellig {fmtDate(job.scheduled_at_today)} / Grace bis {fmtDate(job.grace_until)}</div>
                    {job.minutes_late != null ? (
                      <div className="mt-1 text-xs text-slate-500">{job.minutes_late} Minuten verspaetet</div>
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
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-[1.6rem] border border-black/8 bg-white/75 p-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                Letzte Zustellungen
              </div>
              <div className="mt-4 space-y-2">
                {deliveries.length ? deliveries.map((item: any) => (
                  <div key={item.event_key} className="rounded-[1rem] border border-black/8 bg-white p-3">
                    <div className="text-sm font-bold text-slate-900">{item.title}</div>
                    <div className="mt-1 text-xs text-slate-500">{item.category} / {fmtDate(item.sent_at)}</div>
                  </div>
                )) : (
                  <div className="rounded-[1rem] border border-black/8 bg-white p-3 text-sm text-slate-500">
                    Noch keine Zustellungen gespeichert.
                  </div>
                )}
              </div>
            </section>
          </div>

          {health?.problems?.length ? (
            <div className="mt-5 rounded-[1.4rem] border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-800">
              Probleme: {health.problems.join(", ")}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
