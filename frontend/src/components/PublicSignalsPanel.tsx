import React from "react";

interface SignalHighlight {
  ticker?: string | null;
  issuer_name?: string;
  status?: string;
  shares_now?: number;
  delta_shares?: number;
  value_now?: number;
  delta_value?: number;
  value_label?: string;
  delta_value_label?: string;
  title?: string;
  detail?: string;
}

interface SignalLink {
  label: string;
  url: string;
}

interface SignalTracker {
  id: string;
  title: string;
  subtitle: string;
  source_label: string;
  source_url: string;
  lag_note: string;
  signal_quality: string;
  report_period?: string;
  filing_date?: string;
  staleness_days?: number | null;
  filed_days_ago?: number | null;
  filing_page?: string;
  compliance_note?: string;
  highlights: SignalHighlight[];
  latest_filings?: Array<{ form: string; filed_at: string; url: string }>;
  official_links?: SignalLink[];
  why_better?: string[];
  error?: string;
}

interface PublicSignalsPanelProps {
  data: { trackers: SignalTracker[] } | null;
  onAnalyze: (ticker: string) => void;
}

const statusLabel: Record<string, string> = {
  new: "Neu",
  increased: "Aufgestockt",
  reduced: "Reduziert",
};

const numberFormat = new Intl.NumberFormat("de-DE");

const PublicSignalsPanel: React.FC<PublicSignalsPanelProps> = ({
  data,
  onAnalyze,
}) => {
  if (!data?.trackers?.length) {
    return (
      <div className="surface-panel rounded-3xl p-8 text-sm text-slate-500">
        Keine Public-Signal-Daten geladen.
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {data.trackers.map((tracker) => (
        <section
          key={tracker.id}
          className="surface-panel rounded-[2rem] p-6 md:p-8"
        >
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-3xl space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1 text-[10px] font-black uppercase tracking-[0.25em] text-emerald-300">
                  Public Signals
                </span>
                <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[10px] font-black uppercase tracking-[0.25em] text-slate-400">
                  {tracker.signal_quality}
                </span>
              </div>
              <div>
                <h2 className="text-3xl font-black text-slate-900">{tracker.title}</h2>
                <p className="mt-1 text-sm text-slate-400">{tracker.subtitle}</p>
              </div>
              <div className="flex flex-wrap gap-3 text-xs text-slate-400">
                <a
                  href={tracker.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-xl border border-black/8 bg-white px-3 py-2 font-bold text-slate-700 transition-colors hover:border-emerald-500/30 hover:text-slate-900"
                >
                  Quelle: {tracker.source_label}
                </a>
                {tracker.filing_page && (
                  <a
                    href={tracker.filing_page}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded-xl border border-black/8 bg-white px-3 py-2 font-bold text-slate-700 transition-colors hover:border-emerald-500/30 hover:text-slate-900"
                  >
                    Filing ansehen
                  </a>
                )}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 lg:min-w-[320px]">
              <div className="rounded-2xl border border-white/5 bg-white/5 p-4">
                <div className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-500">
                  Filing Date
                </div>
                <div className="mt-2 text-lg font-black text-slate-900">
                  {tracker.filing_date || "N/A"}
                </div>
                {typeof tracker.filed_days_ago === "number" && (
                  <div className="mt-1 text-xs text-slate-500">
                    vor {tracker.filed_days_ago} Tagen eingereicht
                  </div>
                )}
              </div>
              <div className="rounded-2xl border border-white/5 bg-white/5 p-4">
                <div className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-500">
                  Report Period
                </div>
                <div className="mt-2 text-lg font-black text-slate-900">
                  {tracker.report_period || "N/A"}
                </div>
                {typeof tracker.staleness_days === "number" && (
                  <div className="mt-1 text-xs text-slate-500">
                    Ereignisalter: {tracker.staleness_days} Tage
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="mt-6 grid gap-4 lg:grid-cols-[1.7fr_1fr]">
            <div className="rounded-3xl border border-black/8 bg-white/60 p-5">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-sm font-black uppercase tracking-[0.25em] text-slate-400">
                  Highlights
                </h3>
                <span className="text-xs text-slate-500">{tracker.lag_note}</span>
              </div>

              {tracker.error ? (
                <div className="rounded-2xl border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-300">
                  {tracker.error}
                </div>
              ) : (
                <div className="space-y-3">
                  {tracker.highlights.map((item, index) => {
                    const actionableTicker = item.ticker || null;
                    const isPosition = Boolean(item.issuer_name);

                    return (
                      <div
                        key={`${tracker.id}-${index}`}
                        className="rounded-2xl border border-white/5 bg-white/[0.03] p-4"
                      >
                        {isPosition ? (
                          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                            <div className="space-y-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="text-lg font-black text-slate-900">
                                  {item.issuer_name}
                                </span>
                                <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.2em] text-emerald-300">
                                  {statusLabel[item.status || ""] || item.status}
                                </span>
                                {actionableTicker && (
                                  <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.2em] text-slate-300">
                                    {actionableTicker}
                                  </span>
                                )}
                              </div>
                              <div className="text-sm text-slate-400">
                                Delta {item.delta_value_label} bei{" "}
                                {numberFormat.format(item.delta_shares || 0)} Aktien
                              </div>
                              <div className="text-xs text-slate-500">
                                Position jetzt {item.value_label} und{" "}
                                {numberFormat.format(item.shares_now || 0)} Aktien
                              </div>
                            </div>

                            {actionableTicker && (
                              <button
                                onClick={() => onAnalyze(actionableTicker)}
                                className="rounded-2xl bg-emerald-600 px-5 py-3 text-xs font-black uppercase tracking-[0.2em] text-white transition-colors hover:bg-emerald-500"
                              >
                                Im Analyzer öffnen
                              </button>
                            )}
                          </div>
                        ) : (
                          <div className="space-y-2">
                            <div className="text-base font-black text-slate-900">
                              {item.title}
                            </div>
                            <div className="text-sm text-slate-400">
                              {item.detail}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="space-y-4">
              <div className="rounded-3xl border border-white/5 bg-black/30 p-5">
                <h3 className="text-sm font-black uppercase tracking-[0.25em] text-slate-400">
                  Warum besser
                </h3>
                <div className="mt-4 space-y-2">
                  {(tracker.why_better || []).map((point) => (
                    <div
                      key={point}
                      className="rounded-2xl border border-white/5 bg-white/[0.03] p-3 text-sm text-slate-300"
                    >
                      {point}
                    </div>
                  ))}
                </div>
              </div>

              {tracker.latest_filings?.length ? (
                <div className="rounded-3xl border border-black/8 bg-white/60 p-5">
                  <h3 className="text-sm font-black uppercase tracking-[0.25em] text-slate-400">
                    Letzte Filings
                  </h3>
                  <div className="mt-4 space-y-2">
                    {tracker.latest_filings.map((filing) => (
                      <a
                        key={`${filing.form}-${filing.filed_at}`}
                        href={filing.url}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center justify-between rounded-2xl border border-white/5 bg-white/[0.03] p-3 text-sm transition-colors hover:border-white/15"
                      >
                        <span className="font-bold text-slate-900">{filing.form}</span>
                        <span className="text-slate-500">{filing.filed_at}</span>
                      </a>
                    ))}
                  </div>
                </div>
              ) : null}

              {tracker.official_links?.length ? (
                <div className="rounded-3xl border border-black/8 bg-white/60 p-5">
                  <h3 className="text-sm font-black uppercase tracking-[0.25em] text-slate-400">
                    Offizielle Links
                  </h3>
                  <div className="mt-4 space-y-2">
                    {tracker.official_links.map((link) => (
                      <a
                        key={link.url}
                        href={link.url}
                        target="_blank"
                        rel="noreferrer"
                        className="block rounded-2xl border border-black/8 bg-white p-3 text-sm font-bold text-slate-700 transition-colors hover:border-black/15 hover:text-slate-900"
                      >
                        {link.label}
                      </a>
                    ))}
                  </div>
                </div>
              ) : null}

              {tracker.compliance_note ? (
                <div className="rounded-3xl border border-amber-500/20 bg-amber-500/10 p-5 text-sm text-amber-100">
                  {tracker.compliance_note}
                </div>
              ) : null}
            </div>
          </div>
        </section>
      ))}
    </div>
  );
};

export default PublicSignalsPanel;
