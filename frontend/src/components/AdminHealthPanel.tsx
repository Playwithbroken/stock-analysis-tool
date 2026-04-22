import React, { useEffect, useState } from "react";

interface AdminHealthPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

function statusTone(status?: string) {
  const value = String(status || "").toLowerCase();
  if (["ok", "live", "ready"].includes(value)) return "bg-emerald-500/10 text-emerald-700 border-emerald-500/20";
  if (["degraded", "partial", "snapshot"].includes(value)) return "bg-amber-500/10 text-amber-700 border-amber-500/20";
  return "bg-red-500/10 text-red-700 border-red-500/20";
}

function fmtDate(value?: string | null) {
  if (!value) return "n/a";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" });
}

export default function AdminHealthPanel({ isOpen, onClose }: AdminHealthPanelProps) {
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(false);
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

  useEffect(() => {
    if (isOpen) load();
  }, [isOpen]);

  if (!isOpen) return null;

  const telegram = health?.telegram || {};
  const feeds = health?.data_feeds || {};
  const jobs = health?.schedule?.jobs || [];
  const deliveries = health?.recent_deliveries || [];

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
            <h2 className="mt-1 text-3xl text-slate-900">Delivery, scheduler and data feeds</h2>
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
              disabled={loading}
              className="rounded-xl border border-black/8 bg-white px-4 py-2 text-xs font-extrabold uppercase tracking-[0.16em] text-slate-700 disabled:opacity-50"
            >
              {loading ? "Refreshing" : "Refresh"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl bg-[#101114] px-4 py-2 text-xs font-extrabold uppercase tracking-[0.16em] text-white"
            >
              Close
            </button>
          </div>
        </div>

        <div className="overflow-y-auto p-5">
          {error ? (
            <div className="mb-4 rounded-[1.2rem] border border-red-500/20 bg-red-500/10 p-4 text-sm font-semibold text-red-700">
              {error}
            </div>
          ) : null}

          <div className="grid gap-4 lg:grid-cols-3">
            <div className="rounded-[1.5rem] border border-black/8 bg-white/75 p-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">Telegram</div>
              <div className="mt-3 flex items-center justify-between gap-2">
                <div className="text-lg font-black text-slate-900">{telegram.status || "unknown"}</div>
                <span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-[0.14em] ${statusTone(telegram.status)}`}>
                  {telegram.sendable ? "sendable" : "blocked"}
                </span>
              </div>
              <div className="mt-2 text-xs leading-5 text-slate-500">
                Chat: {telegram.chat_id || "missing"}
              </div>
              {telegram.error ? <div className="mt-2 text-xs text-red-700">{telegram.error}</div> : null}
            </div>

            {Object.entries(feeds).map(([key, feed]: [string, any]) => (
              <div key={key} className="rounded-[1.5rem] border border-black/8 bg-white/75 p-4">
                <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                  {key.replace("_", " ")}
                </div>
                <div className="mt-3 flex items-center justify-between gap-2">
                  <div className="text-lg font-black text-slate-900">{feed.status || "unknown"}</div>
                  <span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-[0.14em] ${statusTone(feed.status)}`}>
                    {feed.status || "n/a"}
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
                    Timezone {health?.timezone || "Europe/Berlin"} · {health?.schedule?.weekdays}
                  </div>
                </div>
                <span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-[0.14em] ${health?.schedule?.enabled ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700" : "border-red-500/20 bg-red-500/10 text-red-700"}`}>
                  {health?.schedule?.enabled ? "enabled" : "disabled"}
                </span>
              </div>
              <div className="mt-4 grid gap-2 md:grid-cols-2">
                {jobs.map((job: any) => (
                  <div key={job.job_key} className="rounded-[1.1rem] border border-black/8 bg-white p-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="font-extrabold text-slate-900">{job.label}</div>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${job.sent_today ? "bg-emerald-500/10 text-emerald-700" : "bg-slate-500/10 text-slate-500"}`}>
                        {job.sent_today ? "sent today" : "pending"}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-slate-500">Plan {job.time} · next {fmtDate(job.next_due_at)}</div>
                    <div className="mt-1 text-xs text-slate-500">Last {fmtDate(job.last_sent_at)}</div>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-[1.6rem] border border-black/8 bg-white/75 p-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                Recent Deliveries
              </div>
              <div className="mt-4 space-y-2">
                {deliveries.length ? deliveries.map((item: any) => (
                  <div key={item.event_key} className="rounded-[1rem] border border-black/8 bg-white p-3">
                    <div className="text-sm font-bold text-slate-900">{item.title}</div>
                    <div className="mt-1 text-xs text-slate-500">{item.category} · {fmtDate(item.sent_at)}</div>
                  </div>
                )) : (
                  <div className="rounded-[1rem] border border-black/8 bg-white p-3 text-sm text-slate-500">
                    No deliveries recorded yet.
                  </div>
                )}
              </div>
            </section>
          </div>

          {health?.problems?.length ? (
            <div className="mt-5 rounded-[1.4rem] border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-800">
              Problems: {health.problems.join(", ")}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
