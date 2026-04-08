import React, { useMemo, useState } from "react";

interface SessionListsPanelProps {
  data: any;
  onAnalyze: (ticker: string) => void;
}

export default function SessionListsPanel({
  data,
  onAnalyze,
}: SessionListsPanelProps) {
  const [region, setRegion] = useState("europe");
  const [phase, setPhase] = useState("pre_open");
  const [sending, setSending] = useState(false);
  const [status, setStatus] = useState("");

  const session = data?.sessions?.[region];
  const current = session?.phases?.[phase];

  const sendCurrent = async () => {
    setSending(true);
    setStatus("");
    try {
      const res = await fetch(`/api/signals/alerts/session-list/${region}/${phase}`, {
        method: "POST",
      });
      const payload = await res.json();
      setStatus(payload.message || "Session list sent.");
    } catch {
      setStatus("Sending failed.");
    } finally {
      setSending(false);
    }
  };

  const regions = useMemo(
    () => [
      { key: "asia", label: "Asia" },
      { key: "europe", label: "Europe" },
      { key: "usa", label: "USA" },
    ],
    [],
  );

  const phases = useMemo(
    () => [
      { key: "pre_open", label: "Pre-Open" },
      { key: "post_open", label: "Post-Open" },
      { key: "end_of_day", label: "End of Day" },
    ],
    [],
  );

  if (!data) return null;

  const renderList = (items: any[], title: string) => (
    <div className="rounded-[1.6rem] border border-black/8 bg-white/70 p-4">
      <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
        {title}
      </div>
      <div className="mt-4 space-y-3">
        {(items || []).map((item, index) => (
          <div
            key={`${title}-${item.ticker}-${index}`}
            className="flex items-center justify-between gap-3 rounded-[1.1rem] border border-black/8 bg-white p-3"
          >
            <div>
              <div className="text-sm font-black text-slate-900">{item.ticker}</div>
              <div className="mt-1 text-xs text-slate-500">
                {item.label} · score {item.phase_score}
              </div>
            </div>
            <div className="text-right">
              <div
                className={`text-sm font-black ${
                  (item.change_1w || 0) >= 0 ? "text-emerald-700" : "text-red-700"
                }`}
              >
                {(item.change_1w || 0) >= 0 ? "+" : ""}
                {item.change_1w?.toFixed(2)}%
              </div>
              <button
                onClick={() => onAnalyze(item.ticker)}
                className="mt-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-[var(--accent)]"
              >
                open
              </button>
            </div>
          </div>
        ))}
        {!items?.length && (
          <div className="rounded-[1.1rem] border border-black/8 bg-white p-3 text-sm text-slate-500">
            Keine Eintraege fuer diesen Block.
          </div>
        )}
      </div>
    </div>
  );

  return (
    <section className="space-y-6">
      <div className="surface-panel rounded-[2.5rem] p-6 sm:p-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Session Lists
            </div>
            <h2 className="mt-2 text-3xl text-slate-900">
              Asia, Europe, USA across the day
            </h2>
          </div>
          <div className="rounded-full border border-black/8 bg-white/70 px-4 py-2 text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
            {session?.label} · {current?.label}
          </div>
        </div>

        <div className="mt-6 flex flex-wrap gap-3">
          {regions.map((item) => (
            <button
              key={item.key}
              onClick={() => setRegion(item.key)}
              className={`rounded-full px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] ${
                region === item.key
                  ? "bg-[var(--accent)] text-white"
                  : "border border-black/8 bg-white/70 text-slate-500"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="mt-3 flex flex-wrap gap-3">
          {phases.map((item) => (
            <button
              key={item.key}
              onClick={() => setPhase(item.key)}
              className={`rounded-full px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] ${
                phase === item.key
                  ? "bg-[var(--accent)] text-white"
                  : "border border-black/8 bg-white/70 text-slate-500"
              }`}
            >
              {item.label}
            </button>
          ))}
          <button
            onClick={sendCurrent}
            disabled={sending}
            className="rounded-full bg-[var(--accent)] px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-white transition-colors hover:bg-[var(--accent-strong)] disabled:opacity-50"
          >
            {sending ? "Sending" : "Send list"}
          </button>
        </div>
        {status && <div className="mt-3 text-sm text-slate-500">{status}</div>}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
        {renderList(current?.equities || [], "Equities")}
        {renderList(current?.etfs || [], "ETFs")}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
        {renderList(current?.crypto || [], "Crypto")}
        <div className="rounded-[1.6rem] border border-black/8 bg-white/70 p-4">
          <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
            News
          </div>
          <div className="mt-4 space-y-3">
            {(current?.news || []).map((item: any, index: number) => (
              <a
                key={`${item.title}-${index}`}
                href={item.link}
                target="_blank"
                rel="noreferrer"
                className="block rounded-[1.1rem] border border-black/8 bg-white p-3"
              >
                <div className="text-sm font-black text-slate-900">{item.title}</div>
                <div className="mt-1 text-xs text-slate-500">
                  {item.publisher} · {item.impact}
                </div>
              </a>
            ))}
            {!current?.news?.length && (
              <div className="rounded-[1.1rem] border border-black/8 bg-white p-3 text-sm text-slate-500">
                Keine priorisierten News fuer diesen Block.
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
