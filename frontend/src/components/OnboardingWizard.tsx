import { useState } from "react";
import useAccessibleDialog from "../hooks/useAccessibleDialog";

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
  const dialogRef = useAccessibleDialog<HTMLDivElement>(isOpen, onDismiss, "input, button");

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
    <div className="fixed inset-0 z-[180] flex items-center justify-center bg-black/40 px-4 backdrop-blur-md dark:bg-black/65" role="presentation">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="onboarding-title" tabIndex={-1} className="surface-panel w-full max-w-2xl rounded-2xl border border-black/8 p-6 sm:p-8 dark:border-white/10 dark:bg-[#1c1c1e]">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">
              Erster Start
            </div>
            <h2 id="onboarding-title" className="mt-1 text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Arbeitsbereich einrichten
            </h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onDismiss}
              className="rounded-full border border-black/8 bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-slate-600 transition-colors hover:bg-black/[0.03] dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:bg-white/10"
            >
              Später
            </button>
            <div className="rounded-full border border-black/8 bg-black/[0.03] px-3 py-1 text-xs font-semibold text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">
              Schritt {step}/3
            </div>
          </div>
        </div>

        {step === 1 ? (
          <div className="space-y-4">
            <div className="text-base font-bold text-slate-900 dark:text-white">1) Watchlist starten</div>
            <p className="text-sm leading-6 text-slate-500 dark:text-slate-400">
              Lege direkt einen ersten Ticker an, damit Signale und Briefings kontextbezogen starten.
            </p>
            <input
              value={watchTicker}
              onChange={(e) => setWatchTicker(e.target.value.toUpperCase())}
              aria-label="Erster Watchlist-Ticker"
              placeholder="z. B. AAPL"
              className="w-full rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800 outline-none transition-all placeholder:text-slate-400 focus:ring-2 focus:ring-black/10 dark:border-white/10 dark:bg-white/5 dark:text-white dark:placeholder:text-slate-500 dark:focus:ring-white/20"
            />
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setStep(2)}
                className="rounded-xl border border-black/8 bg-white px-4 py-2.5 text-xs font-bold uppercase tracking-[0.14em] text-slate-700 transition-colors hover:bg-black/[0.03] dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:bg-white/10"
              >
                Überspringen
              </button>
              <button
                onClick={async () => {
                  await saveWatchTicker();
                  setStep(2);
                }}
                className="rounded-xl bg-[#1d1d1f] px-5 py-2.5 text-xs font-bold uppercase tracking-[0.14em] text-white transition-colors hover:bg-black dark:bg-white dark:text-black dark:hover:bg-white/90"
              >
                Weiter
              </button>
            </div>
          </div>
        ) : null}

        {step === 2 ? (
          <div className="space-y-4">
            <div className="text-base font-bold text-slate-900 dark:text-white">2) Telegram verbinden</div>
            <p className="text-sm leading-6 text-slate-500 dark:text-slate-400">
              Telegram-Benachrichtigungen laufen, sobald Bot-Token und Chat-ID in Railway gesetzt sind. Danach kommen Signale und Hinweise automatisch.
            </p>
            <div className="rounded-xl border border-black/8 bg-black/[0.02] p-4 text-xs font-mono text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">
              ENV: <span className="font-semibold text-slate-800 dark:text-white">TELEGRAM_BOT_TOKEN</span>,{" "}
              <span className="font-semibold text-slate-800 dark:text-white">TELEGRAM_CHAT_ID</span>,{" "}
              <span className="font-semibold text-slate-800 dark:text-white">TELEGRAM_ALERTS_ENABLED=true</span>
            </div>
            <div className="flex justify-between gap-3">
              <button
                onClick={() => setStep(1)}
                className="rounded-xl border border-black/8 bg-white px-4 py-2.5 text-xs font-bold uppercase tracking-[0.14em] text-slate-700 transition-colors hover:bg-black/[0.03] dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:bg-white/10"
              >
                Zurück
              </button>
              <button
                onClick={() => setStep(3)}
                className="rounded-xl bg-[#1d1d1f] px-5 py-2.5 text-xs font-bold uppercase tracking-[0.14em] text-white transition-colors hover:bg-black dark:bg-white dark:text-black dark:hover:bg-white/90"
              >
                Weiter
              </button>
            </div>
          </div>
        ) : null}

        {step === 3 ? (
          <div className="space-y-4">
            <div className="text-base font-bold text-slate-900 dark:text-white">3) Erstes Portfolio</div>
            <p className="text-sm leading-6 text-slate-500 dark:text-slate-400">
              Das erste Portfolio wird direkt erstellt, damit P&amp;L und Alerts ohne leere Ansicht starten.
            </p>
            <input
              value={portfolioName}
              onChange={(e) => setPortfolioName(e.target.value)}
              aria-label="Name des ersten Portfolios"
              placeholder="Portfolio-Name"
              className="w-full rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800 outline-none transition-all placeholder:text-slate-400 focus:ring-2 focus:ring-black/10 dark:border-white/10 dark:bg-white/5 dark:text-white dark:placeholder:text-slate-500 dark:focus:ring-white/20"
            />
            {status ? (
              <div role="alert" className="rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs font-semibold text-red-600 dark:text-red-400">
                {status}
              </div>
            ) : null}
            <div className="flex justify-between gap-3">
              <button
                onClick={() => setStep(2)}
                className="rounded-xl border border-black/8 bg-white px-4 py-2.5 text-xs font-bold uppercase tracking-[0.14em] text-slate-700 transition-colors hover:bg-black/[0.03] dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:bg-white/10"
              >
                Zurück
              </button>
              <button
                onClick={finish}
                disabled={saving}
                className="rounded-xl bg-[#1d1d1f] px-5 py-2.5 text-xs font-bold uppercase tracking-[0.14em] text-white transition-colors hover:bg-black dark:bg-white dark:text-black dark:hover:bg-white/90 disabled:opacity-50"
              >
                {saving ? "Wird gespeichert..." : "Einrichtung abschließen"}
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
