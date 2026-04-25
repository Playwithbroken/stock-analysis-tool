import React from "react";

interface LearningBoardPanelProps {
  data: any;
}

function formatPct(value: any, digits = 1) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "n/a";
  return `${number >= 0 ? "+" : ""}${number.toFixed(digits)}%`;
}

function resultClass(result?: string) {
  if (result === "hit") return "bg-emerald-500/10 text-emerald-700";
  if (result === "miss") return "bg-red-500/10 text-red-700";
  if (result === "neutral") return "bg-slate-500/10 text-slate-600";
  return "border border-black/8 bg-white text-slate-500";
}

export default function LearningBoardPanel({ data }: LearningBoardPanelProps) {
  const summary = data?.summary || {};
  const setupTypes = data?.by_setup_type || [];
  const sources = data?.by_source || [];
  const recent = data?.recent_forecasts || [];

  return (
    <section className="surface-panel rounded-[2.5rem] p-6 sm:p-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
            Learning Board
          </div>
          <h2 className="mt-2 text-3xl text-slate-900">Signal-Qualitaet wird messbar.</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            Jedes gesendete Briefing-Setup wird als Prognose gespeichert und nach 1h, 1d, 3d und 5d
            gegen echte Kursdaten bewertet.
          </p>
        </div>
        <div className="rounded-full border border-black/8 bg-white/75 px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
          {summary.pending || 0} pending checks
        </div>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-4">
        {[
          ["Forecasts", summary.forecasts || 0],
          ["Evaluated", summary.evaluated || 0],
          ["Hit rate", `${Number(summary.hit_rate || 0).toFixed(1)}%`],
          ["Avg move", formatPct(summary.avg_performance_pct)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-[1.5rem] border border-black/8 bg-white/75 p-4">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">{label}</div>
            <div className="mt-2 text-2xl font-black text-slate-900">{value}</div>
          </div>
        ))}
      </div>

      <div className="mt-6 grid gap-5 xl:grid-cols-[0.8fr_1.2fr]">
        <div className="space-y-4">
          <div className="rounded-[1.8rem] border border-black/8 bg-white/72 p-5">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-slate-500">
              Best setup types
            </div>
            <div className="mt-4 space-y-2">
              {setupTypes.length ? (
                setupTypes.slice(0, 5).map((item: any) => (
                  <div key={item.label} className="flex items-center justify-between gap-3 rounded-[1.1rem] bg-black/[0.025] px-3 py-2 text-sm">
                    <span className="font-bold text-slate-800">{item.label}</span>
                    <span className="text-xs font-extrabold text-[var(--accent)]">
                      {item.hit_rate}% · {item.evaluated}
                    </span>
                  </div>
                ))
              ) : (
                <div className="text-sm text-slate-500">Noch keine ausgewerteten Setup-Typen.</div>
              )}
            </div>
          </div>

          <div className="rounded-[1.8rem] border border-black/8 bg-white/72 p-5">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-slate-500">
              Source quality
            </div>
            <div className="mt-4 space-y-2">
              {sources.length ? (
                sources.slice(0, 5).map((item: any) => (
                  <div key={item.label} className="flex items-center justify-between gap-3 rounded-[1.1rem] bg-black/[0.025] px-3 py-2 text-sm">
                    <span className="font-bold text-slate-800">{item.label}</span>
                    <span className="text-xs font-extrabold text-[var(--accent)]">
                      {item.hit_rate}% · {formatPct(item.avg_performance_pct)}
                    </span>
                  </div>
                ))
              ) : (
                <div className="text-sm text-slate-500">Quellen werden bewertet, sobald Outcomes faellig sind.</div>
              )}
            </div>
          </div>
        </div>

        <div className="rounded-[1.8rem] border border-black/8 bg-white/72 p-5">
          <div className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-slate-500">
            Recent briefing forecasts
          </div>
          <div className="mt-4 space-y-3">
            {recent.length ? (
              recent.map((item: any) => (
                <div key={item.id} className="rounded-[1.3rem] border border-black/8 bg-white p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-black uppercase tracking-[0.14em] text-slate-900">
                        {item.symbol}
                      </span>
                      <span className="rounded-full bg-[var(--accent-soft)] px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.14em] text-[var(--accent)]">
                        {item.direction || "watch"}
                      </span>
                    </div>
                    <div className="text-[11px] font-bold text-slate-500">
                      {item.confidence ? `${Math.round(Number(item.confidence))}% conf` : "confidence n/a"}
                    </div>
                  </div>
                  <div className="mt-2 line-clamp-2 text-sm leading-6 text-slate-600">{item.thesis}</div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {(item.outcomes || []).map((outcome: any) => (
                      <span
                        key={`${item.id}-${outcome.horizon_hours}`}
                        className={`rounded-full px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.12em] ${resultClass(outcome.result)}`}
                      >
                        {outcome.horizon_hours}h · {outcome.result || outcome.status}
                        {outcome.performance_pct != null ? ` · ${formatPct(outcome.performance_pct)}` : ""}
                      </span>
                    ))}
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-[1.3rem] border border-dashed border-black/10 bg-white/70 p-5 text-sm text-slate-500">
                Sobald das naechste Telegram-Briefing erfolgreich gesendet wird, erscheinen hier die gespeicherten Prognosen.
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
