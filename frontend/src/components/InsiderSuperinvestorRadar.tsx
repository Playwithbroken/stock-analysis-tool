import React, { useState } from 'react';
import {
  Users,
  Briefcase,
  TrendingUp,
  TrendingDown,
  Building2,
  Award,
  Sparkles,
  ShieldCheck,
  ChevronRight,
  UserCheck
} from 'lucide-react';

export interface SuperinvestorMatch {
  investor_id: string;
  investor_name: string;
  firm: string;
  style: string;
  avatar: string;
  weight_pct: number;
  action: 'BOUGHT' | 'REDUCED' | 'NEW' | 'MAINTAINED' | string;
  shares: number;
  comment: string;
}

export interface InsiderTransaction {
  date: string;
  insider: string;
  position: string;
  transaction_type: string;
  is_purchase: boolean;
  badge_color: 'emerald' | 'rose' | 'slate' | 'indigo' | string;
  shares: number;
  value: number;
  price_per_share: number | null;
  text?: string;
}

export interface InsiderSummary {
  sentiment: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  sentiment_label: string;
  sentiment_color: string;
  buy_count: number;
  sell_count: number;
  total_buy_value: number;
  total_sell_value: number;
  recent_activity: boolean;
}

export interface InstitutionalHolder {
  holder: string;
  shares: number;
  value: number;
  pct_held: number;
  pct_change: number;
}

export interface InsiderRadarData {
  transactions: InsiderTransaction[];
  summary: InsiderSummary;
  institutional_holders: InstitutionalHolder[];
  superinvestors: SuperinvestorMatch[];
  superinvestors_count: number;
}

interface InsiderSuperinvestorRadarProps {
  data?: InsiderRadarData | null;
  ticker: string;
  companyName?: string;
  currency?: string;
}

function formatLargeMoney(val: number, curr: string = 'USD'): string {
  const abs = Math.abs(val);
  const sign = val < 0 ? '-' : '';
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(2)} Mrd. ${curr}`;
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(1)} Mio. ${curr}`;
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(0)} Tsd. ${curr}`;
  return `${sign}${abs.toFixed(0)} ${curr}`;
}

export default function InsiderSuperinvestorRadar({
  data,
  ticker,
  companyName,
  currency = 'USD',
}: InsiderSuperinvestorRadarProps) {
  const [activeTab, setActiveTab] = useState<'superinvestors' | 'insiders' | 'institutions'>('superinvestors');

  if (!data) return null;

  const {
    superinvestors = [],
    transactions = [],
    summary = {
      sentiment: 'NEUTRAL',
      sentiment_label: 'Keine Daten',
      sentiment_color: 'slate',
      buy_count: 0,
      sell_count: 0,
      total_buy_value: 0,
      total_sell_value: 0,
      recent_activity: false,
    },
    institutional_holders = [],
  } = data;

  const getActionBadge = (action: string) => {
    switch (action) {
      case 'BOUGHT':
        return <span className="rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-[10px] font-bold text-emerald-700 dark:text-emerald-300">Aufgestockt</span>;
      case 'NEW':
        return <span className="rounded-full bg-indigo-500/15 px-2.5 py-0.5 text-[10px] font-bold text-indigo-700 dark:text-indigo-300">Neuaufnahme</span>;
      case 'REDUCED':
        return <span className="rounded-full bg-amber-500/15 px-2.5 py-0.5 text-[10px] font-bold text-amber-700 dark:text-amber-300">Teilverkauf</span>;
      default:
        return <span className="rounded-full bg-slate-200/70 px-2.5 py-0.5 text-[10px] font-bold text-slate-700 dark:bg-neutral-700 dark:text-neutral-300">Unverändert</span>;
    }
  };

  return (
    <section className="surface-panel rounded-[2rem] p-5 sm:p-7">
      {/* Section Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-500/10 text-indigo-500">
            <Users className="h-6 w-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500 dark:text-neutral-400">
                Smart Money Tracking
              </span>
              <span className="rounded-full border border-indigo-500/20 bg-indigo-500/10 px-2 py-0.5 text-[10px] font-bold text-indigo-600 dark:text-indigo-400">
                13F & Form 4
              </span>
            </div>
            <h3 className="text-2xl font-bold text-slate-900 dark:text-white">
              Insider- & Superinvestoren-Radar
            </h3>
          </div>
        </div>

        {/* Tab Switcher */}
        <div className="flex rounded-xl bg-slate-100 p-1 dark:bg-neutral-800">
          <button
            onClick={() => setActiveTab('superinvestors')}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
              activeTab === 'superinvestors'
                ? 'bg-white text-slate-900 shadow-sm dark:bg-neutral-700 dark:text-white'
                : 'text-slate-500 hover:text-slate-900 dark:text-neutral-400'
            }`}
          >
            <Sparkles className="h-3.5 w-3.5 text-indigo-500" />
            Superinvestoren ({superinvestors.length})
          </button>
          <button
            onClick={() => setActiveTab('insiders')}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
              activeTab === 'insiders'
                ? 'bg-white text-slate-900 shadow-sm dark:bg-neutral-700 dark:text-white'
                : 'text-slate-500 hover:text-slate-900 dark:text-neutral-400'
            }`}
          >
            <Briefcase className="h-3.5 w-3.5 text-emerald-500" />
            Form 4 Insider ({transactions.length})
          </button>
          <button
            onClick={() => setActiveTab('institutions')}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
              activeTab === 'institutions'
                ? 'bg-white text-slate-900 shadow-sm dark:bg-neutral-700 dark:text-white'
                : 'text-slate-500 hover:text-slate-900 dark:text-neutral-400'
            }`}
          >
            <Building2 className="h-3.5 w-3.5 text-blue-500" />
            Institutionelle ({institutional_holders.length})
          </button>
        </div>
      </div>

      {/* Tab 1: Superinvestoren (13F) */}
      {activeTab === 'superinvestors' && (
        <div className="mt-6">
          {superinvestors.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-2">
              {superinvestors.map((inv) => (
                <div
                  key={inv.investor_id}
                  className="relative overflow-hidden rounded-2xl border border-slate-200/80 bg-white/70 p-5 transition-all hover:shadow-md dark:border-neutral-800 dark:bg-neutral-850/50"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <img
                        src={inv.avatar}
                        alt={inv.investor_name}
                        className="h-12 w-12 rounded-full object-cover ring-2 ring-indigo-500/20"
                      />
                      <div>
                        <h4 className="text-base font-bold text-slate-900 dark:text-white">
                          {inv.investor_name}
                        </h4>
                        <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-neutral-400">
                          <Building2 className="h-3.5 w-3.5" />
                          <span>{inv.firm}</span>
                        </div>
                      </div>
                    </div>
                    {getActionBadge(inv.action)}
                  </div>

                  <div className="mt-4 grid grid-cols-2 gap-2 rounded-xl bg-slate-50 p-3 text-xs dark:bg-neutral-800/40">
                    <div>
                      <span className="text-slate-500 dark:text-neutral-400">Portfolio-Gewicht:</span>
                      <div className="font-mono text-base font-extrabold text-indigo-600 dark:text-indigo-400">
                        {inv.weight_pct.toFixed(1)}%
                      </div>
                    </div>
                    <div>
                      <span className="text-slate-500 dark:text-neutral-400">Haltebestand:</span>
                      <div className="font-mono text-base font-extrabold text-slate-800 dark:text-neutral-200">
                        {(inv.shares / 1e6).toFixed(1)} Mio. Stk
                      </div>
                    </div>
                  </div>

                  <div className="mt-3 text-xs leading-relaxed text-slate-600 dark:text-neutral-300">
                    <span className="font-semibold text-slate-800 dark:text-neutral-200">These: </span>
                    {inv.comment}
                  </div>

                  <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-2.5 text-[11px] text-slate-400 dark:border-neutral-800">
                    <span>Stil: {inv.style}</span>
                    <span className="flex items-center gap-1 text-indigo-500 font-semibold">
                      Verifizierter 13F-Report <ShieldCheck className="h-3.5 w-3.5" />
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-slate-200 p-8 text-center dark:border-neutral-800">
              <Sparkles className="mx-auto h-8 w-8 text-slate-400" />
              <h4 className="mt-2 text-sm font-bold text-slate-700 dark:text-neutral-300">
                Keine direkten Superinvestor-13F-Positionen
              </h4>
              <p className="mt-1 text-xs text-slate-500 dark:text-neutral-400">
                Aktuell hält keiner der 8 getrackten Superinvestoren (Buffett, Burry, Ackman, Li Lu & Co.) eine meldepflichtige Position in {ticker}.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Tab 2: SEC Form 4 Insider-Transaktionen */}
      {activeTab === 'insiders' && (
        <div className="mt-6 space-y-4">
          {/* Sentiment KPI Summary */}
          <div className="grid gap-3 sm:grid-cols-3">
            <div className={`rounded-2xl border p-4 ${
              summary.sentiment === 'BULLISH'
                ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-900 dark:text-emerald-200'
                : summary.sentiment === 'BEARISH'
                ? 'border-amber-500/20 bg-amber-500/10 text-amber-900 dark:text-amber-200'
                : 'border-slate-200 bg-slate-50 text-slate-900 dark:border-neutral-800 dark:bg-neutral-800/40 dark:text-white'
            }`}>
              <div className="text-[11px] font-bold uppercase tracking-wider opacity-80">
                Insider-Sentiment (6M)
              </div>
              <div className="mt-1 text-xl font-extrabold flex items-center gap-2">
                {summary.sentiment === 'BULLISH' && <TrendingUp className="h-5 w-5 text-emerald-500" />}
                {summary.sentiment === 'BEARISH' && <TrendingDown className="h-5 w-5 text-amber-500" />}
                <span>{summary.sentiment_label}</span>
              </div>
            </div>

            <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-4 dark:border-emerald-500/30 dark:bg-emerald-500/10">
              <div className="text-[11px] font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-300">
                Käufe durch Vorstand ({summary.buy_count} Deals)
              </div>
              <div className="mt-1 text-xl font-extrabold text-emerald-900 dark:text-emerald-200">
                +{formatLargeMoney(summary.total_buy_value, currency)}
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200/80 bg-slate-50/70 p-4 dark:border-neutral-800 dark:bg-neutral-800/40">
              <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-neutral-400">
                Verkäufe ({summary.sell_count} Deals)
              </div>
              <div className="mt-1 text-xl font-extrabold text-slate-900 dark:text-white">
                -{formatLargeMoney(summary.total_sell_value, currency)}
              </div>
            </div>
          </div>

          {/* Transactions Table */}
          {transactions.length > 0 ? (
            <div className="overflow-x-auto rounded-2xl border border-slate-200/80 bg-white/60 dark:border-neutral-800 dark:bg-neutral-900/30">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50/70 text-slate-500 dark:border-neutral-800 dark:bg-neutral-800/50">
                    <th className="p-3">Datum</th>
                    <th className="p-3">Insider & Position</th>
                    <th className="p-3">Typ</th>
                    <th className="p-3 text-right">Stück</th>
                    <th className="p-3 text-right">Kurs</th>
                    <th className="p-3 text-right">Gesamtwert</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-neutral-800/60">
                  {transactions.slice(0, 10).map((t, idx) => (
                    <tr key={idx} className="transition-colors hover:bg-slate-50/80 dark:hover:bg-neutral-800/30">
                      <td className="p-3 font-mono text-slate-500">{t.date || 'k.A.'}</td>
                      <td className="p-3">
                        <div className="font-bold text-slate-900 dark:text-white">{t.insider}</div>
                        <div className="text-[11px] text-slate-500 dark:text-neutral-400">{t.position}</div>
                      </td>
                      <td className="p-3">
                        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold ${
                          t.is_purchase
                            ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                            : t.transaction_type === 'Verkauf'
                            ? 'bg-rose-500/15 text-rose-700 dark:text-rose-300'
                            : 'bg-slate-200/60 text-slate-700 dark:bg-neutral-700 dark:text-neutral-300'
                        }`}>
                          {t.transaction_type}
                        </span>
                      </td>
                      <td className="p-3 text-right font-mono font-semibold text-slate-800 dark:text-neutral-200">
                        {t.shares > 0 ? t.shares.toLocaleString('de-DE') : '-'}
                      </td>
                      <td className="p-3 text-right font-mono text-slate-600 dark:text-neutral-400">
                        {t.price_per_share ? `${t.price_per_share.toFixed(2)} ${currency}` : '-'}
                      </td>
                      <td className={`p-3 text-right font-mono font-bold ${
                        t.is_purchase
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : t.transaction_type === 'Verkauf'
                          ? 'text-slate-800 dark:text-neutral-200'
                          : 'text-slate-500'
                      }`}>
                        {t.value > 0 ? `${formatLargeMoney(t.value, currency)}` : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-slate-200 p-8 text-center text-xs text-slate-500 dark:border-neutral-800">
              Keine gemeldeten Form 4 Insider-Transaktionen im letzten Erfassungszeitraum.
            </div>
          )}
        </div>
      )}

      {/* Tab 3: Institutionelle Großanleger */}
      {activeTab === 'institutions' && (
        <div className="mt-6">
          {institutional_holders.length > 0 ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {institutional_holders.map((inst, idx) => (
                <div
                  key={idx}
                  className="rounded-2xl border border-slate-200/80 bg-white/70 p-4 dark:border-neutral-800 dark:bg-neutral-850/50"
                >
                  <div className="flex items-center gap-2">
                    <Building2 className="h-4 w-4 text-slate-400" />
                    <h4 className="text-sm font-bold text-slate-900 dark:text-white truncate">
                      {inst.holder}
                    </h4>
                  </div>

                  <div className="mt-3 flex items-baseline justify-between">
                    <span className="text-xs text-slate-500 dark:text-neutral-400">Anteil am Freefloat:</span>
                    <span className="font-mono text-lg font-extrabold text-blue-600 dark:text-blue-400">
                      {inst.pct_held.toFixed(2)}%
                    </span>
                  </div>

                  <div className="mt-1 flex items-baseline justify-between text-xs">
                    <span className="text-slate-500 dark:text-neutral-400">Gegenwert:</span>
                    <span className="font-mono font-semibold text-slate-800 dark:text-neutral-200">
                      {formatLargeMoney(inst.value, currency)}
                    </span>
                  </div>

                  <div className="mt-2 flex items-center justify-between border-t border-slate-100 pt-2 text-[11px] text-slate-500 dark:border-neutral-800">
                    <span>Gehaltene Aktien:</span>
                    <span className="font-mono">{(inst.shares / 1e6).toFixed(2)} Mio.</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-slate-200 p-8 text-center text-xs text-slate-500 dark:border-neutral-800">
              Keine institutionellen Halterdaten verfügbar.
            </div>
          )}
        </div>
      )}
    </section>
  );
}
