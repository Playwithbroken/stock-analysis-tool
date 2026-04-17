import { useState } from "react";

interface OnboardingWizardProps {
  isOpen: boolean;
  onCreatePortfolio: (name: string) => Promise<any> | any;
  onComplete: () => void;
  onDismiss: () => void;
}

export default function OnboardingWizard({
  isOpen,
  onCreatePortfolio,
  onComplete,
  onDismiss,
}: OnboardingWizardProps) {
  const [step, setStep] = useState(1);
  const [watchTicker, setWatchTicker] = useState("");
  const [portfolioName, setPortfolioName] = useState("Main Portfolio");
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  if (!isOpen) return null;

  const saveWatchTicker = async () => {
    const symbol = watchTicker.trim().toUpperCase();
    if (!symbol) return;
    try {
      await fetch("/api/signals/watchlist/items", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind: "ticker", value: symbol }),
      });
    } catch {
      // keep flow non-blocking
    }
  };

  const finish = async () => {
    setSaving(true);
    setStatus(null);
    try {
      if (portfolioName.trim()) {
        await onCreatePortfolio(portfolioName.trim());
      }
      await fetch("/api/settings/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ onboarding_done: true }),
      });
      onComplete();
    } catch {
      setStatus("Onboarding konnte nicht gespeichert werden.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[180] flex items-center justify-center bg-black/45 px-4">
      <div className="surface-panel w-full max-w-2xl rounded-[2rem] p-6 sm:p-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              First Run
            </div>
            <h2 className="mt-2 text-3xl text-slate-900">Workspace Setup</h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onDismiss}
              className="rounded-full border border-black/8 bg-white px-3 py-1 text-xs font-extrabold uppercase tracking-[0.14em] text-slate-500"
            >
              Spaeter
            </button>
            <div className="rounded-full border border-black/8 bg-white px-3 py-1 text-xs font-bold text-slate-500">
              Schritt {step}/3
            </div>
          </div>
        </div>

        {step === 1 ? (
          <div className="space-y-4">
            <div className="text-lg font-bold text-slate-900">1) Watchlist starten</div>
            <p className="text-sm text-slate-600">
              Lege direkt einen ersten Ticker an, damit Signals und Briefings kontextbezogen starten.
            </p>
            <input
              value={watchTicker}
              onChange={(e) => setWatchTicker(e.target.value.toUpperCase())}
              placeholder="z.B. AAPL"
              className="w-full rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800"
            />
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setStep(2)}
                className="rounded-xl border border-black/8 bg-white px-4 py-2.5 text-xs font-extrabold uppercase tracking-[0.14em] text-slate-700"
              >
                Skip
              </button>
              <button
                onClick={async () => {
                  await saveWatchTicker();
                  setStep(2);
                }}
                className="rounded-xl bg-[var(--accent)] px-4 py-2.5 text-xs font-extrabold uppercase tracking-[0.14em] text-white"
              >
                Weiter
              </button>
            </div>
          </div>
        ) : null}

        {step === 2 ? (
          <div className="space-y-4">
            <div className="text-lg font-bold text-slate-900">2) Telegram verbinden</div>
            <p className="text-sm text-slate-600">
              Telegram Alerts laufen, sobald Bot Token und Chat ID in Railway gesetzt sind. Danach kommen Signale und Alerts automatisch.
            </p>
            <div className="rounded-xl border border-black/8 bg-white/70 p-4 text-sm text-slate-600">
              ENV: <span className="font-semibold">TELEGRAM_BOT_TOKEN</span>,{" "}
              <span className="font-semibold">TELEGRAM_CHAT_ID</span>,{" "}
              <span className="font-semibold">TELEGRAM_ALERTS_ENABLED=true</span>
            </div>
            <div className="flex justify-between gap-3">
              <button
                onClick={() => setStep(1)}
                className="rounded-xl border border-black/8 bg-white px-4 py-2.5 text-xs font-extrabold uppercase tracking-[0.14em] text-slate-700"
              >
                Zurueck
              </button>
              <button
                onClick={() => setStep(3)}
                className="rounded-xl bg-[var(--accent)] px-4 py-2.5 text-xs font-extrabold uppercase tracking-[0.14em] text-white"
              >
                Weiter
              </button>
            </div>
          </div>
        ) : null}

        {step === 3 ? (
          <div className="space-y-4">
            <div className="text-lg font-bold text-slate-900">3) Erstes Portfolio</div>
            <p className="text-sm text-slate-600">
              Das erste Portfolio wird direkt erstellt, damit P&amp;L und Alerts ohne leere Ansicht starten.
            </p>
            <input
              value={portfolioName}
              onChange={(e) => setPortfolioName(e.target.value)}
              placeholder="Portfolio Name"
              className="w-full rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800"
            />
            {status ? (
              <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700">
                {status}
              </div>
            ) : null}
            <div className="flex justify-between gap-3">
              <button
                onClick={() => setStep(2)}
                className="rounded-xl border border-black/8 bg-white px-4 py-2.5 text-xs font-extrabold uppercase tracking-[0.14em] text-slate-700"
              >
                Zurueck
              </button>
              <button
                onClick={finish}
                disabled={saving}
                className="rounded-xl bg-[var(--accent)] px-4 py-2.5 text-xs font-extrabold uppercase tracking-[0.14em] text-white disabled:opacity-50"
              >
                {saving ? "Speichert..." : "Setup abschliessen"}
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
