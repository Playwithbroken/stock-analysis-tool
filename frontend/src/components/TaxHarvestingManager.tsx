import React, { useState, useEffect } from 'react';
import {
  Scissors,
  ShieldCheck,
  AlertTriangle,
  Calendar,
  Sparkles,
  RotateCcw,
  ExternalLink,
  ArrowRight,
  TrendingDown,
  Building2,
  Info,
  CheckCircle2,
  Percent,
  Coins
} from 'lucide-react';

export interface SubstituteInfo {
  substitute_ticker: string;
  substitute_name: string;
  correlation: number;
  reason: string;
}

export interface LossCandidate {
  ticker: string;
  name: string;
  shares: number;
  buy_price: number;
  current_price: number;
  cost_basis: number;
  current_value: number;
  gain_loss_eur: number;
  gain_loss_pct: number;
  is_etf: boolean;
  loss_pot: 'Aktien-Verlusttopf' | 'Allgemeiner Verlusttopf';
  potential_tax_shield_eur: number;
  substitute: SubstituteInfo;
}

export interface BrokerSplit {
  broker: string;
  percentage: number;
  recommended_fsa_eur: number;
}

export interface TaxHarvestingResponse {
  effective_tax_rate_pct: number;
  effective_tax_rate_decimal: number;
  church_tax_type: string;
  days_until_year_end: number;
  total_potential_tax_shield_eur: number;
  stock_tax_shield_eur: number;
  general_tax_shield_eur: number;
  total_unrealized_stock_loss_eur: number;
  total_unrealized_general_loss_eur: number;
  total_unrealized_losses_eur: number;
  total_unrealized_gains_eur: number;
  strategy_headline: string;
  urgency: 'HIGH' | 'MEDIUM' | 'LOW';
  loss_candidates_stocks: LossCandidate[];
  loss_candidates_general: LossCandidate[];
  gain_positions_count: number;
  fsa: {
    total_allowance: number;
    used_amount: number;
    remaining_amount: number;
    used_percentage: number;
    recommended_splits: BrokerSplit[];
    warning: string | null;
  };
  portfolio_id?: string;
  portfolio_name?: string;
}

interface TaxHarvestingManagerProps {
  portfolioId: string;
  onAnalyzeStock?: (ticker: string) => void;
}

export default function TaxHarvestingManager({
  portfolioId,
  onAnalyzeStock,
}: TaxHarvestingManagerProps) {
  const [data, setData] = useState<TaxHarvestingResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Tabs
  const [activeTab, setActiveTab] = useState<'harvesting' | 'fsa'>('harvesting');

  // Interactive Tax Parameters
  const [churchTax, setChurchTax] = useState<'none' | '8%' | '9%'>('none');
  const [fsaAllowance, setFsaAllowance] = useState<number>(1000);
  const [fsaUsed, setFsaUsed] = useState<number>(0);
  const [isUpdating, setIsUpdating] = useState<boolean>(false);

  const fetchTaxData = async (
    ct: string = churchTax,
    fsa: number = fsaAllowance,
    used: number = fsaUsed
  ) => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(
        `/api/portfolio/${portfolioId}/tax-harvesting?church_tax=${encodeURIComponent(ct)}&fsa_allowance=${fsa}&fsa_used=${used}`
      );
      if (!res.ok) {
        throw new Error('Fehler beim Abruf der Steueroptimierungs-Daten');
      }
      const json = await res.json();
      setData(json);
    } catch (err: any) {
      setError(err.message || 'Verbindung fehlgeschlagen');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTaxData(churchTax, fsaAllowance, fsaUsed);
  }, [portfolioId]);

  const handleRecalculate = async () => {
    try {
      setIsUpdating(true);
      const res = await fetch(`/api/portfolio/${portfolioId}/tax-harvesting`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          church_tax_type: churchTax,
          fsa_allowance: Number(fsaAllowance),
          fsa_used: Number(fsaUsed),
        }),
      });
      if (res.ok) {
        const json = await res.json();
        setData(json);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsUpdating(false);
    }
  };

  if (loading && !data) {
    return (
      <div className="flex flex-col items-center justify-center p-12 bg-slate-900/40 rounded-2xl border border-slate-800/80 backdrop-blur-md">
        <div className="w-10 h-10 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-slate-300 font-medium animate-pulse">
          Analysiere deutsches Steuer-Verlusttopf-Modell (§ 20 EStG)...
        </p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-8 bg-rose-950/20 border border-rose-800/50 rounded-2xl text-center">
        <AlertTriangle className="w-10 h-10 text-rose-400 mx-auto mb-3" />
        <h3 className="text-lg font-bold text-rose-200 mb-1">Steueranalyse fehlgeschlagen</h3>
        <p className="text-sm text-rose-300/80 mb-4">{error || 'Keine Daten vorhanden'}</p>
        <button
          onClick={() => fetchTaxData()}
          className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white text-sm font-semibold rounded-lg transition"
        >
          Erneut versuchen
        </button>
      </div>
    );
  }

  const allLossCandidates = [
    ...data.loss_candidates_stocks,
    ...data.loss_candidates_general,
  ];

  return (
    <div className="space-y-6">
      {/* 1. Header Overview Card */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-900 via-slate-900/90 to-slate-950 border border-slate-800/90 p-6 shadow-xl backdrop-blur-xl">
        <div className="absolute top-0 right-0 w-80 h-80 bg-gradient-to-bl from-emerald-500/10 via-cyan-500/5 to-transparent rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1.5">
                <Scissors className="w-3.5 h-3.5" />
                § 20 EStG Steuer-Shield
              </span>
              <span
                className={`px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider border ${
                  data.urgency === 'HIGH'
                    ? 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                    : data.urgency === 'MEDIUM'
                    ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                    : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                }`}
              >
                {data.urgency === 'HIGH'
                  ? 'Hohes Sparpotenzial'
                  : data.urgency === 'MEDIUM'
                  ? 'Empfohlen vor 31.12.'
                  : 'Portfolio steuer-effizient'}
              </span>
            </div>

            <h2 className="text-2xl font-black text-white tracking-tight flex items-center gap-3">
              Smart Tax Loss Harvesting &amp; Freistellungsauftrag
            </h2>
            <p className="text-sm text-slate-400 max-w-2xl">{data.strategy_headline}</p>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-950/70 border border-slate-800 rounded-xl text-xs text-slate-300">
              <Calendar className="w-4 h-4 text-cyan-400" />
              <span>
                Noch <strong className="text-white font-mono">{data.days_until_year_end} Tage</strong> bis 31.12.
              </span>
            </div>
            <button
              onClick={() => fetchTaxData()}
              disabled={loading}
              className="p-2.5 bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700 rounded-xl text-slate-300 hover:text-white transition shadow-sm"
              title="Aktualisieren"
            >
              <RotateCcw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* Top KPIs Row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6">
          <div className="p-3.5 bg-slate-950/50 rounded-xl border border-slate-800/60">
            <p className="text-xs text-slate-400 font-medium">Realisierbare Steuerersparnis</p>
            <p className="text-xl font-black text-emerald-400 mt-1">
              +{data.total_potential_tax_shield_eur.toLocaleString('de-DE', { minimumFractionDigits: 2 })} €
            </p>
            <p className="text-[11px] text-slate-500 mt-0.5">
              aus {data.total_unrealized_losses_eur.toLocaleString('de-DE', { maximumFractionDigits: 0 })} € Verlusten
            </p>
          </div>

          <div className="p-3.5 bg-slate-950/50 rounded-xl border border-slate-800/60">
            <p className="text-xs text-slate-400 font-medium">Aktien-Verlusttopf</p>
            <p className="text-xl font-black text-cyan-400 mt-1">
              -{data.total_unrealized_stock_loss_eur.toLocaleString('de-DE', { minimumFractionDigits: 0 })} €
            </p>
            <p className="text-[11px] text-slate-500 mt-0.5">
              Schild: +{data.stock_tax_shield_eur.toFixed(2)} €
            </p>
          </div>

          <div className="p-3.5 bg-slate-950/50 rounded-xl border border-slate-800/60">
            <p className="text-xs text-slate-400 font-medium">Allg. Verlusttopf (ETFs)</p>
            <p className="text-xl font-black text-purple-400 mt-1">
              -{data.total_unrealized_general_loss_eur.toLocaleString('de-DE', { minimumFractionDigits: 0 })} €
            </p>
            <p className="text-[11px] text-slate-500 mt-0.5">
              Schild: +{data.general_tax_shield_eur.toFixed(2)} €
            </p>
          </div>

          <div className="p-3.5 bg-slate-950/50 rounded-xl border border-slate-800/60">
            <p className="text-xs text-slate-400 font-medium">FSA-Restbetrag</p>
            <p
              className={`text-xl font-black mt-1 ${
                data.fsa.remaining_amount > 100 ? 'text-amber-400' : 'text-emerald-400'
              }`}
            >
              {data.fsa.remaining_amount.toLocaleString('de-DE', { maximumFractionDigits: 0 })} €
            </p>
            <p className="text-[11px] text-slate-500 mt-0.5">
              von {data.fsa.total_allowance} € frei
            </p>
          </div>
        </div>

        {/* Warning if FSA will expire */}
        {data.fsa.warning && (
          <div className="mt-4 p-3.5 bg-amber-500/10 border border-amber-500/30 rounded-xl flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
            <span className="text-xs sm:text-sm font-medium text-amber-200">
              {data.fsa.warning}
            </span>
          </div>
        )}
      </div>

      {/* 2. Interactive Tax Settings Panel */}
      <div className="p-4 bg-slate-900/60 rounded-xl border border-slate-800/80 backdrop-blur-md">
        <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 flex-1">
            <div>
              <label className="text-xs font-semibold text-slate-400 block mb-1">
                Kirchensteuer:
              </label>
              <select
                value={churchTax}
                onChange={(e) => setChurchTax(e.target.value as any)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-emerald-500"
              >
                <option value="none">Keine (26,375 % Abgeltungsteuer + Soli)</option>
                <option value="8%">8 % in BW &amp; Bayern (27,819 % effektiv)</option>
                <option value="9%">9 % in übrigen Bundesländern (27,995 %)</option>
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-400 block mb-1">
                Freibetrag (FSA):
              </label>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setFsaAllowance(1000)}
                  className={`flex-1 py-1.5 text-xs font-bold rounded-lg border transition ${
                    fsaAllowance === 1000
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                      : 'bg-slate-950 text-slate-400 border-slate-700'
                  }`}
                >
                  1.000 € (Single)
                </button>
                <button
                  type="button"
                  onClick={() => setFsaAllowance(2000)}
                  className={`flex-1 py-1.5 text-xs font-bold rounded-lg border transition ${
                    fsaAllowance === 2000
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                      : 'bg-slate-950 text-slate-400 border-slate-700'
                  }`}
                >
                  2.000 € (Paar)
                </button>
              </div>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-400 block mb-1">
                Bereits verbrauchter FSA (€):
                <span className="text-emerald-400 font-mono font-bold ml-1.5">{fsaUsed} €</span>
              </label>
              <input
                type="range"
                min="0"
                max={fsaAllowance}
                step="50"
                value={fsaUsed}
                onChange={(e) => setFsaUsed(Number(e.target.value))}
                className="w-full accent-emerald-500"
              />
            </div>
          </div>

          <div>
            <button
              onClick={handleRecalculate}
              disabled={isUpdating}
              className="w-full lg:w-auto px-4 py-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold text-xs rounded-lg transition shadow flex items-center justify-center gap-2"
            >
              {isUpdating ? <RotateCcw className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
              Neu Berechnen
            </button>
          </div>
        </div>
      </div>

      {/* 3. Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
        <button
          onClick={() => setActiveTab('harvesting')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold transition ${
            activeTab === 'harvesting'
              ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 shadow-sm'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
          }`}
        >
          <Scissors className="w-4 h-4" />
          Verlust-Harvesting &amp; Ersatzkauf
          <span className="px-2 py-0.5 text-[11px] rounded-full bg-slate-800 font-mono text-slate-300">
            {allLossCandidates.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab('fsa')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold transition ${
            activeTab === 'fsa'
              ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 shadow-sm'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
          }`}
        >
          <Coins className="w-4 h-4" />
          Freistellungsauftrag (FSA) Allokator
        </button>
      </div>

      {/* 4. Tab 1: Tax Loss Harvesting Candidates */}
      {activeTab === 'harvesting' && (
        <div className="space-y-6">
          {allLossCandidates.length === 0 ? (
            <div className="p-8 bg-slate-900/40 rounded-2xl border border-slate-800 text-center">
              <CheckCircle2 className="w-10 h-10 text-emerald-400 mx-auto mb-2" />
              <h4 className="text-base font-bold text-white mb-1">Keine realisierbaren Buchverluste</h4>
              <p className="text-xs text-slate-400 max-w-md mx-auto">
                Alle deine Positionen liegen im Plus oder weisen keine signifikanten steuerlichen Verluste auf.
                Dein Portfolio performt solide und erfordert derzeit kein Tax Loss Harvesting.
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Section 1: Aktien-Verlusttopf */}
              {data.loss_candidates_stocks.length > 0 && (
                <div className="p-5 bg-slate-900/60 rounded-2xl border border-slate-800/80 backdrop-blur-md">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h3 className="text-base font-bold text-white flex items-center gap-2">
                        <span className="w-2.5 h-2.5 rounded-full bg-cyan-400" />
                        Aktien-Verlusttopf (§ 20 Abs. 6 Satz 4 EStG)
                      </h3>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Verluste aus diesen Aktien können nach deutschem Recht <strong>ausschließlich mit Gewinnen aus anderen Aktien</strong> verrechnet werden.
                      </p>
                    </div>
                    <span className="text-xs font-mono font-bold text-cyan-400 bg-cyan-500/10 px-2.5 py-1 rounded-lg border border-cyan-500/20">
                      Schild: +{data.stock_tax_shield_eur.toFixed(2)} €
                    </span>
                  </div>

                  <div className="space-y-3">
                    {data.loss_candidates_stocks.map((item) => (
                      <LossCandidateCard
                        key={item.ticker}
                        item={item}
                        onAnalyzeStock={onAnalyzeStock}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Section 2: Allgemeiner Verlusttopf */}
              {data.loss_candidates_general.length > 0 && (
                <div className="p-5 bg-slate-900/60 rounded-2xl border border-slate-800/80 backdrop-blur-md">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h3 className="text-base font-bold text-white flex items-center gap-2">
                        <span className="w-2.5 h-2.5 rounded-full bg-purple-400" />
                        Allgemeiner Verlusttopf (ETFs, Fonds, Derivate, Dividenden)
                      </h3>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Verluste aus diesen ETFs können flexibel gegen <strong>Ausschüttungen, ETF-Gewinne, Anleihezinsen und Dividenden</strong> gerechnet werden.
                      </p>
                    </div>
                    <span className="text-xs font-mono font-bold text-purple-400 bg-purple-500/10 px-2.5 py-1 rounded-lg border border-purple-500/20">
                      Schild: +{data.general_tax_shield_eur.toFixed(2)} €
                    </span>
                  </div>

                  <div className="space-y-3">
                    {data.loss_candidates_general.map((item) => (
                      <LossCandidateCard
                        key={item.ticker}
                        item={item}
                        onAnalyzeStock={onAnalyzeStock}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Educational Tax Callout */}
          <div className="p-4 bg-slate-950/60 rounded-xl border border-slate-800/80 flex items-start gap-3 text-xs text-slate-300">
            <Info className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
            <div>
              <strong className="text-white block mb-1">
                Wie funktioniert das steueroptimierte Re-Investment?
              </strong>
              Wenn du eine Verlustposition verkaufst, wird der Verlust sofort in deinen Verrechnungstopf bei der Bank
              gebucht. Um nicht aus dem Markt auszusteigen und spätere Kursgewinne zu verpassen, kaufst du zeitgleich
              das empfohlene Ersatz-Asset (z. B. <em>iShares Core MSCI World</em> gegen <em>Vanguard FTSE All-World</em>).
              So sicherst du dir die Steuergutschrift und bleibst nahtlos am Markt investiert!
            </div>
          </div>
        </div>
      )}

      {/* 5. Tab 2: Freistellungsauftrag (FSA) Multi-Broker Allocator */}
      {activeTab === 'fsa' && (
        <div className="space-y-6">
          <div className="p-5 bg-slate-900/60 rounded-2xl border border-slate-800/80 backdrop-blur-md">
            <h3 className="text-base font-bold text-white mb-2 flex items-center gap-2">
              <Coins className="w-5 h-5 text-emerald-400" />
              FSA-Nutzung &amp; Multi-Broker Verteilungs-Simulator
            </h3>
            <p className="text-xs text-slate-400 mb-6">
              Teile deinen jährlichen Freibetrag ({data.fsa.total_allowance} €) optimal auf deine Depots auf,
              sodass nirgendwo unnötig Abgeltungsteuer einbehalten wird.
            </p>

            {/* Progress Bar */}
            <div className="mb-6 p-4 bg-slate-950/60 rounded-xl border border-slate-800/80">
              <div className="flex justify-between text-xs font-semibold mb-2">
                <span className="text-slate-300">
                  Verbrauchter Freibetrag: {data.fsa.used_amount.toLocaleString('de-DE')} € ({data.fsa.used_percentage}%)
                </span>
                <span className="text-emerald-400">
                  Noch frei: {data.fsa.remaining_amount.toLocaleString('de-DE')} €
                </span>
              </div>
              <div className="w-full h-3 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-teal-400 transition-all duration-500"
                  style={{ width: `${Math.min(100, data.fsa.used_percentage)}%` }}
                />
              </div>
            </div>

            {/* Broker Split Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {data.fsa.recommended_splits.map((split, idx) => (
                <div
                  key={idx}
                  className="p-4 bg-slate-950/60 rounded-xl border border-slate-800 flex items-center justify-between"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-slate-800 text-emerald-400 flex items-center justify-center">
                      <Building2 className="w-5 h-5" />
                    </div>
                    <div>
                      <p className="text-sm font-bold text-white">{split.broker}</p>
                      <p className="text-xs text-slate-400">{split.percentage} % Allokation</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-black text-emerald-400 font-mono">
                      {split.recommended_fsa_eur.toLocaleString('de-DE')} €
                    </p>
                    <p className="text-[10px] text-slate-500">Empfohlener FSA</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Stichtags-Hinweis */}
          <div className="p-4 bg-slate-950/60 rounded-xl border border-slate-800/80 flex items-start gap-3 text-xs text-slate-300">
            <Calendar className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
            <div>
              <strong className="text-white block mb-1">
                Wichtig für den 15. Dezember (Verlustbescheinigung):
              </strong>
              Möchtest du Verluste bei Broker A mit Gewinnen bei Broker B über die Einkommensteuererklärung
              verrechnen, musst du bis spätestens <strong>15. Dezember</strong> bei deiner Bank eine
              <em>„Verlustbescheinigung nach § 43a Abs. 3 Satz 4 EStG“</em> beantragen. Andernfalls wird der
              Verlusttopf automatisch ins Folgejahr übertragen.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Subcomponent for individual loss card
function LossCandidateCard({
  item,
  onAnalyzeStock,
}: {
  item: LossCandidate;
  onAnalyzeStock?: (ticker: string) => void;
}) {
  return (
    <div className="p-4 bg-slate-950/60 rounded-xl border border-slate-800/80 hover:border-slate-700 transition flex flex-col lg:flex-row lg:items-center justify-between gap-4">
      {/* Left: Position Details */}
      <div className="space-y-1 min-w-[200px]">
        <div className="flex items-center gap-2">
          <span className="font-bold text-base text-white">{item.ticker}</span>
          <span className="text-xs text-slate-400 truncate max-w-[160px]">({item.name})</span>
          <span
            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
              item.is_etf
                ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                : 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
            }`}
          >
            {item.loss_pot}
          </span>
        </div>
        <p className="text-xs text-slate-400">
          Kauf: {item.buy_price.toFixed(2)} € &bull; Aktuell: {item.current_price.toFixed(2)} € ({item.shares} Stk.)
        </p>
      </div>

      {/* Middle: Loss & Tax Shield */}
      <div className="flex items-center gap-6">
        <div>
          <span className="text-[11px] text-slate-500 block">Buchverlust</span>
          <span className="text-sm font-bold font-mono text-rose-400">
            {item.gain_loss_eur.toFixed(2)} € ({item.gain_loss_pct.toFixed(1)}%)
          </span>
        </div>

        <div>
          <span className="text-[11px] text-slate-500 block">Steuer-Rückerstattung</span>
          <span className="text-base font-black font-mono text-emerald-400">
            +{item.potential_tax_shield_eur.toFixed(2)} €
          </span>
        </div>
      </div>

      {/* Right: Recommended Substitute */}
      <div className="bg-slate-900/90 p-3 rounded-lg border border-slate-800 flex-1 max-w-md">
        <div className="flex items-center justify-between text-xs mb-1">
          <span className="text-emerald-400 font-bold flex items-center gap-1">
            <ArrowRight className="w-3.5 h-3.5" />
            Ersatzkauf: {item.substitute.substitute_ticker}
          </span>
          <span className="text-slate-400 font-mono text-[10px]">
            {Math.round(item.substitute.correlation * 100)}% Korrelation
          </span>
        </div>
        <p className="text-[11px] text-slate-400 line-clamp-1">{item.substitute.reason}</p>
      </div>

      {/* Action */}
      {onAnalyzeStock && (
        <div>
          <button
            onClick={() => onAnalyzeStock(item.ticker)}
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded-lg border border-slate-700 text-xs font-semibold flex items-center gap-1.5 transition"
          >
            Analyse
            <ExternalLink className="w-3 h-3" />
          </button>
        </div>
      )}
    </div>
  );
}
