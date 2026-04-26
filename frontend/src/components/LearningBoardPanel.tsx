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

function qualityTone(hitRate: any) {
  const rate = Number(hitRate);
  if (!Number.isFinite(rate)) return "text-slate-500";
  if (rate >= 60) return "text-emerald-700";
  if (rate <= 35) return "text-red-700";
  return "text-amber-700";
}

function QualityList({ title, rows, empty, showMove = false }: any) {
  return (
    <div className="rounded-[1.8rem] border border-black/8 bg-white/72 p-5">
      <div className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-slate-500">{title}</div>
      <div className="mt-4 space-y-2">
        {rows?.length ? (
          rows.slice(0, 5).map((item: any) => (
            <div
              key={item.label}
              className="flex items-center justify-between gap-3 rounded-[1.1rem] bg-black/[0.025] px-3 py-2 text-sm"
            >
              <span className="font-bold text-slate-800">{item.label}</span>
              <span className={`text-xs font-extrabold ${qualityTone(item.hit_rate)}`}>
                {item.hit_rate}% - {showMove ? formatPct(item.avg_performance_pct) : item.evaluated}
              </span>
            </div>
          ))
        ) : (
          <div className="text-sm text-slate-500">{empty}</div>
        )}
      </div>
    </div>
  );
}

export default function LearningBoardPanel({ data }: LearningBoardPanelProps) {
  const summary = data?.summary || {};
  const setupTypes = data?.by_setup_type || [];
  const sources = data?.by_source || [];
  const weakSetupTypes = data?.weak_setup_types || [];
  const weakSources = data?.weak_sources || [];
  const lessons = data?.lessons || [];
  const pendingByHorizon = data?.pending_by_horizon || [];
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

      <div className="mt-4 grid gap-3 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-[1.8rem] border border-[var(--accent)]/14 bg-[linear-gradient(180deg,rgba(15,118,110,0.08),rgba(255,255,255,0.82))] p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-[var(--accent)]">
              Ranking lessons
            </div>
            <div className="rounded-full border border-black/8 bg-white/70 px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
              auto feedback
            </div>
          </div>
          <div className="mt-4 grid gap-2 md:grid-cols-2">
            {lessons.length ? (
              lessons.map((lesson: any, index: number) => (
                <div
                  key={`${lesson.type}-${lesson.label}-${index}`}
                  className="rounded-[1.2rem] border border-black/8 bg-white/75 p-3 text-sm leading-6 text-slate-700"
                >
                  <div className="mb-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                    {lesson.type?.replaceAll("_", " ") || "lesson"}
                  </div>
                  {lesson.message}
                </div>
              ))
            ) : (
              <div className="rounded-[1.2rem] border border-dashed border-black/10 bg-white/70 p-4 text-sm text-slate-500 md:col-span-2">
                Noch zu wenig ausgewertete Outcomes fuer echte Lessons. Nach den naechsten Briefings
                werden Quellen und Setup-Arten automatisch hoch- oder runtergewichtet.
              </div>
            )}
          </div>
        </div>

        <div className="rounded-[1.8rem] border border-black/8 bg-white/72 p-5">
          <div className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-slate-500">
            Open checks
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {pendingByHorizon.length ? (
              pendingByHorizon.map((item: any) => (
                <span
                  key={item.horizon_hours}
                  className="rounded-full border border-black/8 bg-white px-3 py-1.5 text-[11px] font-extrabold uppercase tracking-[0.14em] text-slate-600"
                >
                  {item.horizon_hours}h - {item.count}
                </span>
              ))
            ) : (
              <span className="text-sm text-slate-500">Keine offenen Outcome-Pruefungen.</span>
            )}
          </div>
          <div className="mt-4 grid grid-cols-3 gap-2 text-center">
            <div className="rounded-[1rem] bg-emerald-500/10 px-2 py-3">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-emerald-700">
                Hits
              </div>
              <div className="mt-1 text-xl font-black text-emerald-800">{summary.hits || 0}</div>
            </div>
            <div className="rounded-[1rem] bg-red-500/10 px-2 py-3">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-red-700">
                Misses
              </div>
              <div className="mt-1 text-xl font-black text-red-800">{summary.misses || 0}</div>
            </div>
            <div className="rounded-[1rem] bg-slate-500/10 px-2 py-3">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-600">
                Neutral
              </div>
              <div className="mt-1 text-xl font-black text-slate-800">{summary.neutral || 0}</div>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-6 grid gap-5 xl:grid-cols-[0.8fr_1.2fr]">
        <div className="space-y-4">
          <QualityList
            title="Best setup types"
            rows={setupTypes}
            empty="Noch keine ausgewerteten Setup-Typen."
          />
          <QualityList
            title="Needs stricter triggers"
            rows={weakSetupTypes}
            empty="Noch keine schwachen Setup-Typen erkannt."
          />
          <QualityList
            title="Source quality"
            rows={sources}
            empty="Quellen werden bewertet, sobald Outcomes faellig sind."
            showMove
          />
          <QualityList
            title="Sources to downgrade"
            rows={weakSources}
            empty="Noch keine schwachen Quellen erkannt."
            showMove
          />
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
                      <span className="rounded-full border border-black/8 bg-white px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.12em] text-slate-500">
                        {item.source_label || item.setup_type || "briefing"}
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
                        {outcome.horizon_hours}h - {outcome.result || outcome.status}
                        {outcome.performance_pct != null ? ` - ${formatPct(outcome.performance_pct)}` : ""}
                      </span>
                    ))}
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-[1.3rem] border border-dashed border-black/10 bg-white/70 p-5 text-sm text-slate-500">
                Sobald das naechste Telegram-Briefing erfolgreich gesendet wird, erscheinen hier die
                gespeicherten Prognosen.
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
