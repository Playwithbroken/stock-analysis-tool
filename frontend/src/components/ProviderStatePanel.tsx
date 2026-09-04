import { useEffect, useState } from "react";
import { Activity, AlertTriangle, Database, RefreshCw } from "lucide-react";

export type ProviderState = "loading" | "slow" | "empty" | "error" | "degraded";

interface ProviderStatePanelProps {
  view: string;
  state: ProviderState;
  title: string;
  description: string;
  source?: string;
  onRetry?: () => void;
  retryLabel?: string;
  compact?: boolean;
}

const stateMeta: Record<ProviderState, { label: string; tone: string; icon: typeof Activity }> = {
  loading: {
    label: "Daten werden geladen",
    tone: "border-sky-500/20 bg-sky-50/75 text-sky-900",
    icon: Activity,
  },
  slow: {
    label: "Provider antwortet langsam",
    tone: "border-amber-500/25 bg-amber-50/80 text-amber-900",
    icon: Activity,
  },
  empty: {
    label: "Noch keine Daten",
    tone: "border-slate-300 bg-white/80 text-slate-800",
    icon: Database,
  },
  error: {
    label: "Provider nicht erreichbar",
    tone: "border-red-500/25 bg-red-50/80 text-red-900",
    icon: AlertTriangle,
  },
  degraded: {
    label: "Fallback-Daten aktiv",
    tone: "border-amber-500/25 bg-amber-50/80 text-amber-900",
    icon: Database,
  },
};

export function useSlowProviderState(active: boolean, delayMs = 6000) {
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    if (!active) {
      setSlow(false);
      return;
    }
    const timer = window.setTimeout(() => setSlow(true), delayMs);
    return () => window.clearTimeout(timer);
  }, [active, delayMs]);

  return slow;
}

export default function ProviderStatePanel({
  view,
  state,
  title,
  description,
  source,
  onRetry,
  retryLabel = "Erneut laden",
  compact = false,
}: ProviderStatePanelProps) {
  const meta = stateMeta[state];
  const Icon = meta.icon;
  const isPending = state === "loading" || state === "slow";

  return (
    <section
      data-testid={`provider-state-${view}`}
      data-provider-state={state}
      role={state === "error" ? "alert" : "status"}
      aria-live={state === "error" ? "assertive" : "polite"}
      className={`provider-state-panel min-w-0 rounded-[1.5rem] border ${compact ? "p-4" : "p-5 sm:p-6"} ${meta.tone}`}
    >
      <div className="flex min-w-0 flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-current/10 bg-white/60">
            <Icon className={isPending ? "h-5 w-5 animate-pulse" : "h-5 w-5"} aria-hidden="true" />
          </span>
          <div className="min-w-0 [overflow-wrap:anywhere]">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] opacity-70">
              {meta.label}{source ? ` · ${source}` : ""}
            </div>
            <h3 className={`${compact ? "mt-1 text-base" : "mt-2 text-lg"} font-black`}>{title}</h3>
            <p className="mt-1 max-w-3xl text-sm leading-6 opacity-80">{description}</p>
          </div>
        </div>
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            disabled={state === "loading"}
            className="inline-flex shrink-0 items-center justify-center gap-2 rounded-[0.95rem] border border-current/15 bg-white/75 px-4 py-2.5 text-[10px] font-extrabold uppercase tracking-[0.14em] transition-colors hover:bg-white disabled:cursor-wait disabled:opacity-60"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${state === "loading" ? "animate-spin" : ""}`} aria-hidden="true" />
            {retryLabel}
          </button>
        ) : null}
      </div>
    </section>
  );
}
