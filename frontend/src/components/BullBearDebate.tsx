import React from "react";
import {
  TrendingUp,
  TrendingDown,
  Scale,
  Sparkles,
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
} from "lucide-react";

export interface DebatePoint {
  title: string;
  detail: string;
  metric?: string;
  conviction?: "high" | "medium" | "moderate" | string;
}

export interface BullBearDebateData {
  bull_pct: number;
  bear_pct: number;
  bull_score: number;
  bear_score: number;
  verdict_headline: string;
  summary: string;
  key_battleground: string;
  bull_thesis: DebatePoint[];
  bear_thesis: DebatePoint[];
  bull_catalysts: string[];
  invalidation_triggers: string[];
}

interface BullBearDebateProps {
  debate?: BullBearDebateData | null;
  ticker?: string;
  companyName?: string;
}

export default function BullBearDebate({
  debate,
  ticker,
  companyName,
}: BullBearDebateProps) {
  if (!debate) {
    return null;
  }

  const {
    bull_pct = 50,
    bear_pct = 50,
    verdict_headline,
    summary,
    key_battleground,
    bull_thesis = [],
    bear_thesis = [],
    bull_catalysts = [],
    invalidation_triggers = [],
  } = debate;

  const isBullAdvantage = bull_pct >= 54;
  const isBearAdvantage = bear_pct >= 54;

  return (
    <section
      aria-labelledby="bull-bear-debate-title"
      className="surface-panel relative overflow-hidden rounded-[2rem] p-6 shadow-sm transition-all duration-300 sm:p-8"
    >
      {/* Background Ambience Gradient */}
      <div
        className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-emerald-500/5 blur-3xl dark:bg-emerald-500/10"
        aria-hidden="true"
      />
      <div
        className="pointer-events-none absolute -bottom-20 -left-20 h-64 w-64 rounded-full bg-rose-500/5 blur-3xl dark:bg-rose-500/10"
        aria-hidden="true"
      />

      {/* Header Section */}
      <div className="relative flex flex-col justify-between gap-4 border-b border-slate-200/80 pb-6 dark:border-slate-800 md:flex-row md:items-center">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-indigo-500/10 text-indigo-600 dark:bg-indigo-400/15 dark:text-indigo-300">
              <Scale className="h-4 w-4" />
            </span>
            <span className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-indigo-600 dark:text-indigo-400">
              Dialektische Analyse • Devil's Advocate
            </span>
          </div>
          <h3
            id="bull-bear-debate-title"
            className="mt-1 text-2xl font-bold tracking-tight text-slate-900 dark:text-white"
          >
            Bull vs. Bear Duell {ticker ? `(${ticker})` : ""}
          </h3>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Gegenüberstellung von Wachstumskatalysatoren und substanziellen Gegenargumenten für {companyName || ticker || "diesen Wert"}.
          </p>
        </div>

        {/* Verdict Badge */}
        <div className="flex flex-col items-start md:items-end">
          <div
            className={`inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-bold shadow-sm ${
              isBullAdvantage
                ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-300 dark:bg-emerald-950/40 dark:text-emerald-300 dark:ring-emerald-700/50"
                : isBearAdvantage
                  ? "bg-rose-50 text-rose-700 ring-1 ring-rose-300 dark:bg-rose-950/40 dark:text-rose-300 dark:ring-rose-700/50"
                  : "bg-slate-100 text-slate-700 ring-1 ring-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700"
            }`}
          >
            {isBullAdvantage ? (
              <TrendingUp className="h-4 w-4" />
            ) : isBearAdvantage ? (
              <TrendingDown className="h-4 w-4" />
            ) : (
              <Scale className="h-4 w-4" />
            )}
            <span>{verdict_headline}</span>
          </div>
          <p className="mt-1.5 max-w-sm text-xs text-slate-500 dark:text-slate-400 md:text-right">
            {summary}
          </p>
        </div>
      </div>

      {/* Duel Meter Bar */}
      <div className="my-6">
        <div className="mb-2 flex items-center justify-between text-xs font-bold tracking-wide">
          <div className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400">
            <TrendingUp className="h-4 w-4" />
            <span>BULLEN-THESE ({bull_pct}%)</span>
          </div>
          <div className="text-[10px] uppercase tracking-wider text-slate-400">
            Kräfteverhältnis
          </div>
          <div className="flex items-center gap-1.5 text-rose-600 dark:text-rose-400">
            <span>BÄREN-THESE ({bear_pct}%)</span>
            <TrendingDown className="h-4 w-4" />
          </div>
        </div>

        {/* Meter Visual */}
        <div className="relative h-3 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
          <div
            className="absolute left-0 top-0 h-full bg-gradient-to-r from-emerald-600 to-emerald-400 transition-all duration-700 ease-out"
            style={{ width: `${bull_pct}%` }}
          />
          <div
            className="absolute right-0 top-0 h-full bg-gradient-to-l from-rose-600 to-rose-400 transition-all duration-700 ease-out"
            style={{ width: `${bear_pct}%` }}
          />
          {/* Dividing Marker */}
          <div
            className="absolute top-0 h-full w-1 -translate-x-1/2 bg-white shadow dark:bg-slate-950"
            style={{ left: `${bull_pct}%` }}
          />
        </div>
      </div>

      {/* Key Battleground Banner */}
      {key_battleground && (
        <div className="mb-8 rounded-2xl border border-amber-200/80 bg-amber-50/70 p-4 dark:border-amber-900/50 dark:bg-amber-950/20">
          <div className="flex items-start gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-amber-500/20 text-amber-700 dark:text-amber-300">
              <Sparkles className="h-3.5 w-3.5" />
            </span>
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wider text-amber-800 dark:text-amber-300">
                Zentrales Schlachtfeld (Key Battleground)
              </div>
              <p className="mt-0.5 text-sm font-semibold text-slate-900 dark:text-amber-100">
                {key_battleground}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Dual Debate Columns */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Left Column: Bull Thesis */}
        <div className="flex flex-col rounded-2xl border border-emerald-200/70 bg-emerald-50/30 p-5 dark:border-emerald-900/40 dark:bg-emerald-950/10">
          <div className="mb-4 flex items-center justify-between border-b border-emerald-200/50 pb-3 dark:border-emerald-900/40">
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-700 dark:text-emerald-300">
                <TrendingUp className="h-3.5 w-3.5" />
              </span>
              <h4 className="text-base font-bold text-slate-900 dark:text-white">
                Bullen-Argumente
              </h4>
            </div>
            <span className="text-[11px] font-semibold text-emerald-700 dark:text-emerald-400">
              {bull_thesis.length} Katalysatoren
            </span>
          </div>

          <div className="space-y-3">
            {bull_thesis.map((point, idx) => (
              <div
                key={idx}
                className="rounded-xl border border-emerald-200/60 bg-white/80 p-3.5 shadow-sm transition-hover hover:border-emerald-300 dark:border-emerald-800/40 dark:bg-slate-900/80"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="font-semibold text-slate-900 dark:text-white">
                    {point.title}
                  </div>
                  {point.metric && (
                    <span className="shrink-0 rounded-md bg-emerald-100 px-2 py-0.5 text-[11px] font-bold text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-200">
                      {point.metric}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                  {point.detail}
                </p>
              </div>
            ))}
          </div>

          {/* Confirmation Catalysts Sub-block */}
          {bull_catalysts.length > 0 && (
            <div className="mt-5 rounded-xl border border-emerald-200/40 bg-emerald-100/40 p-3.5 dark:border-emerald-800/30 dark:bg-emerald-950/30">
              <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-emerald-800 dark:text-emerald-300">
                <CheckCircle2 className="h-3.5 w-3.5" />
                <span>Bestätigende Katalysatoren</span>
              </div>
              <ul className="mt-2 space-y-1.5 text-xs text-slate-700 dark:text-slate-300">
                {bull_catalysts.map((cat, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
                    <span>{cat}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Right Column: Bear Thesis */}
        <div className="flex flex-col rounded-2xl border border-rose-200/70 bg-rose-50/30 p-5 dark:border-rose-900/40 dark:bg-rose-950/10">
          <div className="mb-4 flex items-center justify-between border-b border-rose-200/50 pb-3 dark:border-rose-900/40">
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-rose-500/20 text-rose-700 dark:text-rose-300">
                <TrendingDown className="h-3.5 w-3.5" />
              </span>
              <h4 className="text-base font-bold text-slate-900 dark:text-white">
                Bären-Gegenargumente
              </h4>
            </div>
            <span className="text-[11px] font-semibold text-rose-700 dark:text-rose-400">
              {bear_thesis.length} Risikofaktoren
            </span>
          </div>

          <div className="space-y-3">
            {bear_thesis.map((point, idx) => (
              <div
                key={idx}
                className="rounded-xl border border-rose-200/60 bg-white/80 p-3.5 shadow-sm transition-hover hover:border-rose-300 dark:border-rose-800/40 dark:bg-slate-900/80"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="font-semibold text-slate-900 dark:text-white">
                    {point.title}
                  </div>
                  {point.metric && (
                    <span className="shrink-0 rounded-md bg-rose-100 px-2 py-0.5 text-[11px] font-bold text-rose-800 dark:bg-rose-900/60 dark:text-rose-200">
                      {point.metric}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                  {point.detail}
                </p>
              </div>
            ))}
          </div>

          {/* Invalidation Triggers Sub-block */}
          {invalidation_triggers.length > 0 && (
            <div className="mt-5 rounded-xl border border-rose-200/40 bg-rose-100/40 p-3.5 dark:border-rose-800/30 dark:bg-rose-950/30">
              <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-rose-800 dark:text-rose-300">
                <AlertTriangle className="h-3.5 w-3.5" />
                <span>Invalidierungs-Trigger (These kippt wenn...)</span>
              </div>
              <ul className="mt-2 space-y-1.5 text-xs text-slate-700 dark:text-slate-300">
                {invalidation_triggers.map((trig, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-rose-500" />
                    <span>{trig}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      {/* Disciplinary Footer Note */}
      <div className="mt-6 flex items-center gap-2 rounded-xl bg-slate-100/70 px-4 py-2.5 text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-400">
        <HelpCircle className="h-4 w-4 shrink-0 text-slate-400" />
        <span>
          <strong>Disziplin-Prinzip:</strong> Die Gegenüberstellung von Bulle und Bär erzwingt das bewusste Hinterfragen der eigenen Anlagethese vor einem Trade, um Bestätigungsfehler (Confirmation Bias) systematisch auszuschalten.
        </span>
      </div>
    </section>
  );
}
