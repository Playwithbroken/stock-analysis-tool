import React, { useEffect, useState } from "react";
import {
  Calendar,
  CalendarDays,
  AlertTriangle,
  Flame,
  Download,
  RefreshCw,
  Clock,
  TrendingUp,
  CheckCircle2,
  XCircle,
  MinusCircle,
  BellRing,
  ExternalLink,
} from "lucide-react";

interface RecentQuarter {
  period: string;
  eps_estimate: number | null;
  reported_eps: number | null;
  eps_surprise_pct: number | null;
  status: "beat" | "miss" | "inline" | string;
}

interface UpcomingEvent {
  ticker: string;
  name: string;
  weight_pct: number;
  date: string;
  timing: string;
  days_until: number;
  eps_estimate: number | null;
  is_urgent: boolean;
  beat_rate_pct: number | null;
  recent_quarters: RecentQuarter[];
}

interface HoldingTrackRecord {
  ticker: string;
  name: string;
  weight_pct: number;
  beat_rate_pct: number | null;
  beat_count: number;
  miss_count: number;
  reported_count: number;
  recent_quarters: RecentQuarter[];
}

interface EarningsRadarResponse {
  portfolio_id: string;
  portfolio_name: string;
  upcoming_events: UpcomingEvent[];
  urgent_events: UpcomingEvent[];
  track_records: HoldingTrackRecord[];
  summary: {
    total_holdings: number;
    holdings_with_dates: number;
    urgent_count: number;
    overall_beat_rate_pct: number;
  };
  message?: string;
}

interface EarningsRadarProps {
  portfolioId: string;
  portfolioName?: string;
}

export default function EarningsRadar({
  portfolioId,
  portfolioName = "Mein Portfolio",
}: EarningsRadarProps) {
  const [data, setData] = useState<EarningsRadarResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchEarningsRadar = async () => {
    if (!portfolioId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/portfolio/${portfolioId}/earnings-radar`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: EarningsRadarResponse = await res.json();
      setData(json);
    } catch (err: any) {
      setError(err?.message || "Fehler beim Laden des Earnings-Radars.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEarningsRadar();
  }, [portfolioId]);

  const handleExportICS = () => {
    if (!portfolioId) return;
    window.open(`/api/portfolio/${portfolioId}/earnings/export/ics`, "_blank");
  };

  const summary = data?.summary;
  const urgent = data?.urgent_events || [];
  const upcoming = data?.upcoming_events || [];
  const tracks = data?.track_records || [];

  return (
    <section className="surface-panel rounded-[2rem] p-6 lg:p-7 space-y-6">
      {/* Header with Export & Refresh */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-indigo-600 dark:text-indigo-400">
            <CalendarDays className="h-4 w-4" />
            <span className="text-xs font-extrabold uppercase tracking-[0.2em]">
              Earnings & Event-Radar
            </span>
          </div>
          <h3 className="mt-1 text-xl font-extrabold tracking-tight text-slate-900 dark:text-white">
            Quartalszahlen-Kalender für {portfolioName}
          </h3>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleExportICS}
            disabled={upcoming.length === 0}
            className="flex items-center gap-2 rounded-xl border border-black/8 bg-indigo-600 px-3.5 py-2 text-xs font-bold text-white shadow-sm shadow-indigo-500/20 transition hover:bg-indigo-700 disabled:opacity-50"
            title="Termine in Google/Apple/Outlook Kalender exportieren"
          >
            <Download className="h-3.5 w-3.5" />
            Kalender exportieren (.ics)
          </button>

          <button
            onClick={fetchEarningsRadar}
            disabled={loading}
            className="rounded-xl border border-black/8 bg-black/[0.03] p-2 text-slate-600 hover:bg-black/[0.06] hover:text-slate-900 dark:border-white/10 dark:bg-white/5 dark:text-slate-400 dark:hover:text-white"
            title="Aktualisieren"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin text-indigo-600" : ""}`} />
          </button>
        </div>
      </div>

      {/* Urgent Warning Banner (if events in <= 7 days) */}
      {urgent.length > 0 && (
        <div className="flex items-start gap-3.5 rounded-2xl border border-rose-500/30 bg-rose-500/[0.06] p-4.5 dark:bg-rose-950/20">
          <div className="rounded-xl bg-rose-500/15 p-2 text-rose-600 dark:text-rose-400 mt-0.5">
            <Flame className="h-5 w-5 animate-pulse" />
          </div>
          <div>
            <div className="text-xs font-black uppercase tracking-wider text-rose-600 dark:text-rose-400">
              High-Volatility Window ({urgent.length} Position{urgent.length > 1 ? "en" : ""})
            </div>
            <p className="mt-1 text-xs leading-relaxed text-slate-700 dark:text-slate-200">
              In den nächsten 7 Tagen melden{" "}
              <span className="font-extrabold">
                {urgent.map((u) => `${u.ticker} (in ${u.days_until}d)`).join(", ")}
              </span>{" "}
              Quartalszahlen. Erhöhte Kursschwankungen von typischerweise ±5% bis ±15% erwartet. Prüfe ggf. deine Absicherung.
            </p>
          </div>
        </div>
      )}

      {/* KPI Cards Grid */}
      {summary && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-2xl border border-black/8 bg-black/[0.02] p-4 dark:border-white/10 dark:bg-white/5">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Anstehende Termine
            </div>
            <div className="mt-1 text-xl font-black text-slate-900 dark:text-white">
              {upcoming.length} Events
            </div>
            <div className="mt-1 text-[11px] text-slate-500">
              Nächste 90 Tage
            </div>
          </div>

          <div className="rounded-2xl border border-black/8 bg-black/[0.02] p-4 dark:border-white/10 dark:bg-white/5">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-rose-600 dark:text-rose-400">
              Dringend (≤ 7 Tage)
            </div>
            <div className="mt-1 text-xl font-black text-rose-600 dark:text-rose-400">
              {summary.urgent_count}
            </div>
            <div className="mt-1 text-[11px] text-slate-500">
              Im Volatilitätsfokus
            </div>
          </div>

          <div className="rounded-2xl border border-black/8 bg-black/[0.02] p-4 dark:border-white/10 dark:bg-white/5">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
              Depot-Beat-Quote
            </div>
            <div className="mt-1 text-xl font-black text-emerald-600 dark:text-emerald-400">
              {summary.overall_beat_rate_pct.toFixed(0)}%
            </div>
            <div className="mt-1 text-[11px] text-slate-500">
              Schätzungen übertroffen
            </div>
          </div>

          <div className="rounded-2xl border border-black/8 bg-black/[0.02] p-4 dark:border-white/10 dark:bg-white/5">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-indigo-600 dark:text-indigo-400">
              Nächster Termin
            </div>
            <div className="mt-1 text-xl font-black text-slate-900 dark:text-white truncate">
              {upcoming[0]?.ticker || "—"}
            </div>
            <div className="mt-1 text-[11px] text-slate-500">
              {upcoming[0] ? `in ${upcoming[0].days_until} Tagen (${upcoming[0].date})` : "Keine Termine"}
            </div>
          </div>
        </div>
      )}

      {/* Chronological Upcoming Events Cards */}
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
          <Clock className="h-4 w-4 text-indigo-500" />
          Chronologische Veröffentlichungstermine
        </div>

        {loading ? (
          <div className="flex h-36 w-full flex-col items-center justify-center space-y-2 rounded-2xl border border-black/8 bg-black/[0.02]">
            <div className="h-7 w-7 animate-spin rounded-full border-2 border-indigo-500/20 border-t-indigo-500" />
            <span className="text-xs text-slate-500 font-bold uppercase tracking-wider">
              Earnings-Kalender wird synchronisiert...
            </span>
          </div>
        ) : upcoming.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-black/10 p-6 text-center text-xs text-slate-500">
            Aktuell sind für deine Depotpositionen keine anstehenden Quartalszahlen im 90-Tage-Fenster gemeldet.
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {upcoming.map((ev) => (
              <div
                key={ev.ticker}
                className={`rounded-2xl border p-4.5 transition-all ${
                  ev.is_urgent
                    ? "border-rose-500/40 bg-rose-500/[0.03] shadow-sm shadow-rose-500/10 dark:border-rose-500/30 dark:bg-rose-950/10"
                    : "border-black/8 bg-black/[0.015] hover:bg-black/[0.03] dark:border-white/8 dark:bg-white/[0.02] dark:hover:bg-white/[0.04]"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-black text-base text-slate-900 dark:text-white">
                        {ev.ticker}
                      </span>
                      <span className="rounded-md bg-black/5 dark:bg-white/10 px-1.5 py-0.5 text-[10px] font-bold text-slate-600 dark:text-slate-300">
                        {ev.weight_pct}% Depot
                      </span>
                    </div>
                    <div className="text-xs text-slate-500 truncate max-w-[170px]">
                      {ev.name}
                    </div>
                  </div>

                  {/* Countdown Badge */}
                  <div
                    className={`rounded-xl px-2.5 py-1 text-right ${
                      ev.is_urgent
                        ? "bg-rose-500 text-white font-black"
                        : "bg-black/5 dark:bg-white/10 text-slate-700 dark:text-slate-200 font-bold"
                    }`}
                  >
                    <div className="text-xs">
                      {ev.days_until === 0
                        ? "Heute!"
                        : ev.days_until === 1
                        ? "Morgen!"
                        : `in ${ev.days_until} Tagen`}
                    </div>
                  </div>
                </div>

                {/* Event Details */}
                <div className="mt-3.5 space-y-1 text-xs">
                  <div className="flex justify-between text-slate-600 dark:text-slate-300">
                    <span className="text-slate-500">Datum:</span>
                    <span className="font-bold">{ev.date}</span>
                  </div>
                  <div className="flex justify-between text-slate-600 dark:text-slate-300">
                    <span className="text-slate-500">Timing:</span>
                    <span className="font-semibold">{ev.timing}</span>
                  </div>
                  {ev.eps_estimate !== null && (
                    <div className="flex justify-between text-slate-600 dark:text-slate-300">
                      <span className="text-slate-500">EPS-Konsens:</span>
                      <span className="font-mono font-bold">{ev.eps_estimate.toFixed(2)} $</span>
                    </div>
                  )}
                  {ev.beat_rate_pct !== null && (
                    <div className="flex justify-between text-slate-600 dark:text-slate-300">
                      <span className="text-slate-500">Beat-Rate:</span>
                      <span className="font-bold text-emerald-600 dark:text-emerald-400">
                        {ev.beat_rate_pct.toFixed(0)}% Beats
                      </span>
                    </div>
                  )}
                </div>

                {/* Mini Quarters History */}
                {ev.recent_quarters && ev.recent_quarters.length > 0 && (
                  <div className="mt-3 pt-2.5 border-t border-black/6 dark:border-white/8 flex items-center gap-1.5">
                    <span className="text-[10px] text-slate-400 uppercase font-bold">Trend:</span>
                    {ev.recent_quarters.map((q, idx) => (
                      <span
                        key={idx}
                        className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-bold ${
                          q.status === "beat"
                            ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
                            : q.status === "miss"
                            ? "bg-rose-500/15 text-rose-700 dark:text-rose-400"
                            : "bg-slate-200 text-slate-600 dark:bg-white/10 dark:text-slate-300"
                        }`}
                        title={`${q.period}: ${q.status.toUpperCase()} (${q.eps_surprise_pct ? (q.eps_surprise_pct > 0 ? `+${q.eps_surprise_pct.toFixed(1)}%` : `${q.eps_surprise_pct.toFixed(1)}%`) : "in line"})`}
                      >
                        {q.status === "beat" ? "✓" : q.status === "miss" ? "✕" : "—"}{" "}
                        {q.eps_surprise_pct ? `${q.eps_surprise_pct > 0 ? "+" : ""}${q.eps_surprise_pct.toFixed(0)}%` : ""}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Track Record Table */}
      {tracks.length > 0 && (
        <div className="space-y-3 pt-2">
          <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            <TrendingUp className="h-4 w-4 text-emerald-500" />
            Historischer Beat/Miss-Track-Record
          </div>

          <div className="overflow-x-auto rounded-2xl border border-black/8 bg-black/[0.01] dark:border-white/10 dark:bg-white/[0.02]">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-black/6 bg-black/[0.02] text-slate-500 dark:border-white/8 dark:bg-white/[0.03]">
                  <th className="p-3.5 font-extrabold uppercase tracking-wider">Aktie</th>
                  <th className="p-3.5 font-extrabold uppercase tracking-wider text-right">Depotanteil</th>
                  <th className="p-3.5 font-extrabold uppercase tracking-wider text-right">Beat-Rate</th>
                  <th className="p-3.5 font-extrabold uppercase tracking-wider text-right">Beats / Misses</th>
                  <th className="p-3.5 font-extrabold uppercase tracking-wider">Letzte 4 Quartale</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/6 dark:divide-white/8">
                {tracks.map((t) => (
                  <tr key={t.ticker} className="hover:bg-black/[0.02] dark:hover:bg-white/[0.03]">
                    <td className="p-3.5">
                      <span className="font-black text-slate-900 dark:text-white">{t.ticker}</span>{" "}
                      <span className="text-[11px] text-slate-500 truncate max-w-[120px]">{t.name}</span>
                    </td>
                    <td className="p-3.5 text-right font-mono font-bold text-slate-700 dark:text-slate-300">
                      {t.weight_pct}%
                    </td>
                    <td className="p-3.5 text-right font-mono font-extrabold">
                      {t.beat_rate_pct !== null ? (
                        <span
                          className={
                            t.beat_rate_pct >= 75
                              ? "text-emerald-600 dark:text-emerald-400"
                              : t.beat_rate_pct >= 50
                              ? "text-amber-600 dark:text-amber-400"
                              : "text-rose-600 dark:text-rose-400"
                          }
                        >
                          {t.beat_rate_pct.toFixed(0)}%
                        </span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                    <td className="p-3.5 text-right font-mono text-slate-600 dark:text-slate-400">
                      {t.beat_count}W / {t.miss_count}L
                    </td>
                    <td className="p-3.5">
                      <div className="flex items-center gap-1.5">
                        {t.recent_quarters.map((q, idx) => (
                          <span
                            key={idx}
                            className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-bold ${
                              q.status === "beat"
                                ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
                                : q.status === "miss"
                                ? "bg-rose-500/15 text-rose-700 dark:text-rose-400"
                                : "bg-slate-200 text-slate-600 dark:bg-white/10 dark:text-slate-300"
                            }`}
                            title={`${q.period}: ${q.status.toUpperCase()} (${q.eps_surprise_pct ? (q.eps_surprise_pct > 0 ? `+${q.eps_surprise_pct.toFixed(1)}%` : `${q.eps_surprise_pct.toFixed(1)}%`) : "in line"})`}
                          >
                            {q.status === "beat" ? "✓ Beat" : q.status === "miss" ? "✕ Miss" : "— Line"}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
