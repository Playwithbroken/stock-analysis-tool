import React, { useMemo, useState } from "react";

interface SignalScoreboardPanelProps {
  data: any;
  onAnalyze: (ticker: string) => void;
  onRefresh?: () => Promise<void>;
}

function ScoreCard({
  item,
  onAnalyze,
}: {
  item: any;
  onAnalyze: (ticker: string) => void;
}) {
  const isCongress =
    item.bucket === "politics" ||
    String(item.source_label || "").toLowerCase().includes("house");
  const congressBadges = [
    isCongress ? "Congress Watch" : null,
    item.freshness ? String(item.freshness).replace("_", " ") : null,
    item.delay_days != null ? `delay ${item.delay_days}d` : null,
    item.amount_range || item.estimated_exposure_label,
    item.signal_grade ? String(item.signal_grade).replace(/_/g, " ") : null,
  ].filter(Boolean);

  return (
    <div
      className={`rounded-[1.4rem] border p-4 ${
        isCongress
          ? "border-[var(--accent)]/18 bg-[linear-gradient(180deg,rgba(15,118,110,0.08),rgba(255,255,255,0.86))]"
          : "border-black/8 bg-white/75"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-black text-slate-900">{item.label}</div>
          <div className="mt-1 text-xs text-slate-500">{item.headline}</div>
        </div>
        <div className="rounded-full border border-[var(--accent)]/15 bg-[var(--accent-soft)] px-2 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-[var(--accent)]">
          {item.total_score}
        </div>
      </div>
      {congressBadges.length ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {congressBadges.slice(0, 5).map((badge) => (
            <span
              key={String(badge)}
              className="rounded-full border border-black/8 bg-white/76 px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.12em] text-slate-600"
            >
              {badge}
            </span>
          ))}
        </div>
      ) : null}
      <div className="mt-4 grid grid-cols-3 gap-2">
        <div className="rounded-xl border border-black/8 bg-white p-2">
          <div className="text-[9px] font-bold uppercase tracking-[0.14em] text-slate-500">Source</div>
          <div className="mt-1 text-sm font-black text-slate-900">{item.source_quality}</div>
        </div>
        <div className="rounded-xl border border-black/8 bg-white p-2">
          <div className="text-[9px] font-bold uppercase tracking-[0.14em] text-slate-500">Timing</div>
          <div className="mt-1 text-sm font-black text-slate-900">{item.timing_quality}</div>
        </div>
        <div className="rounded-xl border border-black/8 bg-white p-2">
          <div className="text-[9px] font-bold uppercase tracking-[0.14em] text-slate-500">Conviction</div>
          <div className="mt-1 text-sm font-black text-slate-900">{item.conviction_score}</div>
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between gap-3">
        <div className="min-w-0 text-xs text-slate-500">
          {item.next_action || item.detail}
        </div>
        {item.ticker && (
          <button
            onClick={() => onAnalyze(item.ticker)}
            className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] text-white transition-colors hover:bg-[var(--accent-strong)]"
          >
            Analyze
          </button>
        )}
      </div>
      {isCongress && item.compliance_note ? (
        <div className="mt-3 rounded-xl border border-black/8 bg-white/70 p-3 text-[11px] leading-5 text-slate-500">
          {item.compliance_note}
        </div>
      ) : null}
    </div>
  );
}

export default function SignalScoreboardPanel({
  data,
  onAnalyze,
  onRefresh,
}: SignalScoreboardPanelProps) {
  const [highConvictionOnly, setHighConvictionOnly] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");
  const [settings, setSettings] = useState(() => ({
    weights: {
      source: data?.settings?.weights?.source ?? 0.35,
      timing: data?.settings?.weights?.timing ?? 0.30,
      conviction: data?.settings?.weights?.conviction ?? 0.35,
    },
    high_conviction_min_score: data?.settings?.high_conviction_min_score ?? 75,
  }));
  if (!data) return null;

  React.useEffect(() => {
    setSettings({
      weights: {
        source: data?.settings?.weights?.source ?? 0.35,
        timing: data?.settings?.weights?.timing ?? 0.30,
        conviction: data?.settings?.weights?.conviction ?? 0.35,
      },
      high_conviction_min_score: data?.settings?.high_conviction_min_score ?? 75,
    });
  }, [data]);

  const minScore = settings.high_conviction_min_score || 75;

  const sections = [
    { key: "equities", title: "Equity Signals" },
    { key: "politics", title: "Political Signals" },
    { key: "etfs", title: "ETF Quality" },
    { key: "crypto", title: "Crypto Flow" },
  ];

  const filtered = useMemo(() => {
    if (!highConvictionOnly) return data;
    const filterItems = (items: any[]) =>
      (items || []).filter((item) => (item.total_score || 0) >= minScore);
    return {
      ...data,
      top_ideas: filterItems(data.top_ideas || []),
      equities: filterItems(data.equities || []),
      politics: filterItems(data.politics || []),
      etfs: filterItems(data.etfs || []),
      crypto: filterItems(data.crypto || []),
    };
  }, [data, highConvictionOnly, minScore]);

  const saveSettings = async () => {
    setSaving(true);
    setStatus("");
    try {
      await fetch("/api/settings/signal-score", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      await onRefresh?.();
      setStatus("Score settings updated.");
    } catch {
      setStatus("Saving failed.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="space-y-6">
      <div className="surface-panel rounded-[2.5rem] p-6 sm:p-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Signal Score Engine
            </div>
            <h2 className="mt-2 text-3xl text-slate-900">High conviction scoreboard</h2>
          </div>
          <div className="flex items-center gap-3">
            <div className="rounded-full border border-black/8 bg-white/70 px-4 py-2 text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
              Min score {minScore}
            </div>
            <button
              onClick={() => setHighConvictionOnly((prev) => !prev)}
              className={`rounded-full px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] transition-colors ${
                highConvictionOnly
                  ? "bg-[var(--accent)] text-white"
                  : "border border-black/8 bg-white/70 text-slate-500"
              }`}
            >
              High conviction only
            </button>
          </div>
        </div>

        <div className="mt-6 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-[1.8rem] border border-[var(--accent)]/12 bg-[linear-gradient(180deg,rgba(15,118,110,0.08),rgba(255,255,255,0.9))] p-5">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Top Ideas
            </div>
            <div className="mt-4 grid gap-3">
              {(filtered.top_ideas || []).slice(0, 5).map((item: any, index: number) => (
                <div
                  key={`${item.bucket}-${item.label}-${index}`}
                  className="flex items-center justify-between rounded-[1.2rem] border border-black/8 bg-white/80 p-4"
                >
                  <div>
                    <div className="text-sm font-black text-slate-900">{item.label}</div>
                    <div className="mt-1 text-xs text-slate-500">
                      {item.bucket} · {item.headline}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-black text-slate-900">{item.total_score}</div>
                    {item.ticker && (
                      <button
                        onClick={() => onAnalyze(item.ticker)}
                        className="mt-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-[var(--accent)]"
                      >
                        open
                      </button>
                    )}
                  </div>
                </div>
              ))}
              {!filtered.top_ideas?.length && (
                <div className="rounded-[1.2rem] border border-black/8 bg-white/80 p-4 text-sm text-slate-500">
                  Kein Signal erreicht aktuell den High-Conviction-Schwellenwert.
                </div>
              )}
            </div>
          </div>

          <div className="surface-panel rounded-[1.8rem] p-5">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Post-Signal Performance
            </div>
            <div className="mt-4 space-y-3">
              {(data.performance || []).length ? (
                data.performance.map((item: any, index: number) => (
                  <div
                    key={`${item.kind}-${item.label}-${index}`}
                    className="rounded-[1.2rem] border border-black/8 bg-white/75 p-4"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="text-sm font-black text-slate-900">{item.label}</div>
                        <div className="mt-1 text-xs text-slate-500">{item.headline}</div>
                      </div>
                      <div
                        className={`text-sm font-black ${
                          (item.performance_pct || 0) >= 0 ? "text-emerald-700" : "text-red-700"
                        }`}
                      >
                        {(item.performance_pct || 0) >= 0 ? "+" : ""}
                        {item.performance_pct?.toFixed(2)}%
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-[1.2rem] border border-black/8 bg-white/75 p-4 text-sm text-slate-500">
                  Noch nicht genug Signale mit auswertbarer Historie.
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="mt-4 rounded-[1.8rem] border border-black/8 bg-white/70 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                Score Controls
              </div>
              <div className="mt-1 text-sm text-slate-500">
                Tune source, timing and conviction weights for your ranking model.
              </div>
            </div>
            <button
              onClick={saveSettings}
              disabled={saving}
              className="rounded-xl bg-[var(--accent)] px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-white transition-colors hover:bg-[var(--accent-strong)] disabled:opacity-50"
            >
              {saving ? "Saving" : "Save model"}
            </button>
          </div>
          <div className="mt-4 grid gap-4 md:grid-cols-4">
            {[
              ["source", "Source"],
              ["timing", "Timing"],
              ["conviction", "Conviction"],
            ].map(([key, label]) => (
              <label
                key={key}
                className="rounded-[1.2rem] border border-black/8 bg-white p-4"
              >
                <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                  {label}
                </div>
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.05"
                  value={settings.weights[key as keyof typeof settings.weights]}
                  onChange={(e) =>
                    setSettings((prev) => ({
                      ...prev,
                      weights: {
                        ...prev.weights,
                        [key]: Number(e.target.value),
                      },
                    }))
                  }
                  className="mt-3 w-full rounded-xl border border-black/8 bg-white px-3 py-2 text-sm font-semibold text-slate-900"
                />
              </label>
            ))}
            <label className="rounded-[1.2rem] border border-black/8 bg-white p-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                Min Score
              </div>
              <input
                type="number"
                min="0"
                max="100"
                step="1"
                value={settings.high_conviction_min_score}
                onChange={(e) =>
                  setSettings((prev) => ({
                    ...prev,
                    high_conviction_min_score: Number(e.target.value),
                  }))
                }
                className="mt-3 w-full rounded-xl border border-black/8 bg-white px-3 py-2 text-sm font-semibold text-slate-900"
              />
            </label>
          </div>
          {status && (
            <div className="mt-3 text-sm text-slate-500">{status}</div>
          )}
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        {sections.map((section) => (
          <div key={section.key} className="surface-panel rounded-[2rem] p-5">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              {section.title}
            </div>
            <div className="mt-4 space-y-3">
              {(filtered[section.key] || []).slice(0, 4).map((item: any, index: number) => (
                <ScoreCard
                  key={`${section.key}-${item.label}-${index}`}
                  item={item}
                  onAnalyze={onAnalyze}
                />
              ))}
              {!filtered[section.key]?.length && (
                <div className="rounded-[1.2rem] border border-black/8 bg-white/75 p-4 text-sm text-slate-500">
                  Keine Treffer in diesem Block mit dem aktuellen Filter.
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
