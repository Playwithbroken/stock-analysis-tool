import React, { useState, useEffect } from 'react';
import {
  Users,
  Building2,
  Sparkles,
  ShieldCheck,
  RotateCcw,
  ExternalLink,
  Award,
  CheckCircle2
} from 'lucide-react';
import { SuperinvestorMatch } from './InsiderSuperinvestorRadar';

export interface PortfolioEndorsedHolding {
  ticker: string;
  name: string;
  superinvestors: SuperinvestorMatch[];
  superinvestors_count: number;
}

export interface PortfolioSuperinvestorData {
  total_holdings: number;
  endorsed_holdings_count: number;
  smart_money_percentage: number;
  superinvestors_involved: string[];
  superinvestors_count: number;
  endorsed_holdings: PortfolioEndorsedHolding[];
  headline: string;
  portfolio_name?: string;
}

interface PortfolioSuperinvestorRadarProps {
  portfolioId: string;
  onSelectTicker?: (ticker: string) => void;
}

export default function PortfolioSuperinvestorRadar({
  portfolioId,
  onSelectTicker,
}: PortfolioSuperinvestorRadarProps) {
  const [data, setData] = useState<PortfolioSuperinvestorData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRadar = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`/api/portfolio/${portfolioId}/superinvestors`);
      if (!res.ok) {
        throw new Error('Fehler beim Abruf der Superinvestoren-Daten');
      }
      const json = await res.json();
      setData(json);
    } catch (err: any) {
      setError(err.message || 'Unbekannter Fehler');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (portfolioId) {
      fetchRadar();
    }
  }, [portfolioId]);

  if (loading) {
    return (
      <div className="surface-panel rounded-[2rem] p-6 text-center">
        <div className="flex items-center justify-center gap-2 text-sm text-slate-500">
          <RotateCcw className="h-4 w-4 animate-spin text-indigo-500" />
          <span>Analysiere 13F-Positionen der Superinvestoren für dein Depot...</span>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="surface-panel rounded-[2rem] p-6 text-center">
        <p className="text-sm text-rose-500">{error || 'Keine Daten verfügbar'}</p>
        <button
          onClick={fetchRadar}
          className="mt-3 rounded-xl border border-slate-200 px-4 py-2 text-xs font-bold hover:bg-slate-50 dark:border-neutral-700"
        >
          Erneut versuchen
        </button>
      </div>
    );
  }

  const {
    total_holdings = 0,
    endorsed_holdings_count = 0,
    smart_money_percentage = 0,
    superinvestors_involved = [],
    endorsed_holdings = [],
    headline,
  } = data;

  const getActionBadge = (action: string) => {
    switch (action) {
      case 'BOUGHT':
        return <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold text-emerald-700 dark:text-emerald-300">Aufgestockt</span>;
      case 'NEW':
        return <span className="rounded-full bg-indigo-500/15 px-2 py-0.5 text-[10px] font-bold text-indigo-700 dark:text-indigo-300">Neuaufnahme</span>;
      case 'REDUCED':
        return <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold text-amber-700 dark:text-amber-300">Teilverkauf</span>;
      default:
        return <span className="rounded-full bg-slate-200/70 px-2 py-0.5 text-[10px] font-bold text-slate-700 dark:bg-neutral-700 dark:text-neutral-300">Halteposition</span>;
    }
  };

  return (
    <div className="surface-panel rounded-[2rem] p-5 sm:p-7">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-500/10 text-indigo-500">
            <Award className="h-6 w-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500 dark:text-neutral-400">
                Depot-Check
              </span>
              <span className="rounded-full border border-indigo-500/20 bg-indigo-500/10 px-2 py-0.5 text-[10px] font-bold text-indigo-600 dark:text-indigo-400">
                13F Smart Money
              </span>
            </div>
            <h3 className="text-2xl font-bold text-slate-900 dark:text-white">
              Superinvestoren-Radar
            </h3>
          </div>
        </div>

        <button
          onClick={fetchRadar}
          title="Aktualisieren"
          className="rounded-xl border border-slate-200 p-2 text-slate-500 transition-colors hover:bg-slate-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
        >
          <RotateCcw className="h-4 w-4" />
        </button>
      </div>

      {/* Hero Banner */}
      <div className="mt-6 rounded-2xl border border-indigo-500/20 bg-gradient-to-br from-indigo-500/10 via-purple-500/5 to-transparent p-5 dark:border-indigo-500/30">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="text-xs font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-400">
              Smart-Money-Overlap
            </div>
            <div className="text-xl font-extrabold text-slate-900 dark:text-white">
              {headline}
            </div>
            <p className="text-xs text-slate-600 dark:text-neutral-300">
              Vergleicht dein gesamtes Depot mit den offiziellen SEC 13F-Berichten der weltbesten Fondsmanager.
            </p>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right">
              <div className="text-[11px] font-bold text-slate-500 dark:text-neutral-400">
                Depot-Abdeckung
              </div>
              <div className="font-mono text-3xl font-black text-indigo-600 dark:text-indigo-400">
                {smart_money_percentage}%
              </div>
            </div>
            <div className="h-10 w-px bg-slate-200 dark:bg-neutral-700" />
            <div>
              <div className="text-[11px] font-bold text-slate-500 dark:text-neutral-400">
                Superinvestoren
              </div>
              <div className="font-mono text-3xl font-black text-slate-900 dark:text-white">
                {superinvestors_involved.length}
              </div>
            </div>
          </div>
        </div>

        {/* Involved Superinvestors Pills */}
        {superinvestors_involved.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-indigo-500/15 pt-3">
            <span className="text-xs font-bold text-slate-600 dark:text-neutral-300">Beteiligte Legenden:</span>
            {superinvestors_involved.map((name, idx) => (
              <span
                key={idx}
                className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1 text-xs font-bold text-slate-800 shadow-sm dark:bg-neutral-800 dark:text-neutral-200"
              >
                <Sparkles className="h-3 w-3 text-indigo-500" />
                {name}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Endorsed Holdings Cards */}
      <div className="mt-6">
        <div className="mb-3 text-sm font-bold text-slate-900 dark:text-white">
          Aktien in deinem Depot mit Superinvestor-Beteiligung ({endorsed_holdings.length})
        </div>

        {endorsed_holdings.length > 0 ? (
          <div className="grid gap-4 md:grid-cols-2">
            {endorsed_holdings.map((h) => (
              <div
                key={h.ticker}
                className="rounded-2xl border border-slate-200/80 bg-white/70 p-5 dark:border-neutral-800 dark:bg-neutral-850/50"
              >
                <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-neutral-800">
                  <div>
                    <button
                      onClick={() => onSelectTicker && onSelectTicker(h.ticker)}
                      className="group flex items-center gap-2 text-left"
                    >
                      <span className="text-lg font-extrabold text-slate-900 group-hover:text-indigo-600 dark:text-white dark:group-hover:text-indigo-400">
                        {h.ticker}
                      </span>
                      <span className="text-xs text-slate-500 truncate max-w-[160px]">{h.name}</span>
                      <ExternalLink className="h-3.5 w-3.5 opacity-0 group-hover:opacity-100 transition-opacity text-indigo-500" />
                    </button>
                  </div>
                  <span className="rounded-full bg-indigo-500/10 px-2.5 py-0.5 text-xs font-bold text-indigo-600 dark:text-indigo-400">
                    {h.superinvestors_count} {h.superinvestors_count === 1 ? 'Superinvestor' : 'Superinvestoren'}
                  </span>
                </div>

                <div className="mt-3 space-y-3">
                  {h.superinvestors.map((inv) => (
                    <div
                      key={inv.investor_id}
                      className="flex items-start justify-between gap-3 rounded-xl bg-slate-50 p-3 dark:bg-neutral-800/40"
                    >
                      <div className="flex items-center gap-2.5">
                        <img
                          src={inv.avatar}
                          alt={inv.investor_name}
                          className="h-9 w-9 rounded-full object-cover ring-1 ring-slate-200 dark:ring-neutral-700"
                        />
                        <div>
                          <div className="text-xs font-bold text-slate-900 dark:text-white">
                            {inv.investor_name}
                          </div>
                          <div className="text-[10px] text-slate-500 dark:text-neutral-400">
                            {inv.firm} • {inv.weight_pct.toFixed(1)}% Portfolioanteil
                          </div>
                        </div>
                      </div>
                      {getActionBadge(inv.action)}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-2xl border border-dashed border-slate-200 p-8 text-center text-xs text-slate-500 dark:border-neutral-800">
            Aktuell hält keiner der 8 Superinvestoren Aktien, die in diesem Depot enthalten sind.
          </div>
        )}
      </div>
    </div>
  );
}
