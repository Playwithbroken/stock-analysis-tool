import React, { useState, useEffect } from 'react';
import {
  PieChart,
  Layers,
  AlertTriangle,
  Flame,
  CheckCircle2,
  TrendingDown,
  ExternalLink,
  RotateCcw,
  Sparkles,
  Info,
  DollarSign,
  ArrowRight,
  ShieldCheck,
  Search
} from 'lucide-react';

export interface LookThroughCluster {
  ticker: string;
  effective_portfolio_weight_pct: number;
  is_mega_cluster: boolean;
}

export interface OverlapMatrixCell {
  etf_a: string;
  etf_b: string;
  overlap_pct: number;
  is_self: boolean;
}

export interface FeeSimulation {
  years: number;
  projected_portfolio_value: number;
  benchmark_value: number;
  lost_to_fees: number;
  fee_drag_pct: number;
}

export interface ExpensivePosition {
  ticker: string;
  name: string;
  ter_pct: number;
  weight_pct: number;
  annual_cost_eur: number;
  cheaper_alternative: string;
}

export interface ETFOverlapResponse {
  total_portfolio_value: number;
  etf_count: number;
  single_stock_count: number;
  weighted_ter_pct: number;
  fee_score: 'CHAMPION' | 'MODERATE' | 'VAMPIRE';
  fee_headline: string;
  fee_badge_color: 'emerald' | 'amber' | 'rose';
  top_look_through_clusters: LookThroughCluster[];
  top_3_concentration_pct: number;
  cluster_warning: string | null;
  etf_overlap_matrix: OverlapMatrixCell[][];
  etf_list: Array<{ ticker: string; name: string; ter: number; weight: number }>;
  fee_simulations: FeeSimulation[];
  expensive_positions: ExpensivePosition[];
  monthly_savings_input: number;
  portfolio_id?: string;
  portfolio_name?: string;
}

export interface PairwiseCompareResult {
  etf_a: { ticker: string; name: string; ter: number; holdings_count: number };
  etf_b: { ticker: string; name: string; ter: number; holdings_count: number };
  overlap_percentage: number;
  overlap_headline: string;
  shared_holdings_count: number;
  shared_holdings: Array<{
    ticker: string;
    weight_in_a: number;
    weight_in_b: number;
    overlap_contribution: number;
  }>;
}

interface ETFOverlapFeeDetectorProps {
  portfolioId: string;
  onAnalyzeStock?: (ticker: string) => void;
}

export default function ETFOverlapFeeDetector({
  portfolioId,
  onAnalyzeStock
}: ETFOverlapFeeDetectorProps) {
  const [data, setData] = useState<ETFOverlapResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Active Tab
  const [activeTab, setActiveTab] = useState<'clusters' | 'overlap' | 'fees'>('clusters');

  // Interactive Fee Simulation Parameters
  const [monthlySavings, setMonthlySavings] = useState<number>(250);
  const [grossReturn, setGrossReturn] = useState<number>(7.0); // % p.a.
  const [isSimulating, setIsSimulating] = useState<boolean>(false);

  // Standalone Pairwise ETF Compare
  const [compareEtf1, setCompareEtf1] = useState<string>('URTH');
  const [compareEtf2, setCompareEtf2] = useState<string>('QQQ');
  const [compareResult, setCompareResult] = useState<PairwiseCompareResult | null>(null);
  const [compareLoading, setCompareLoading] = useState<boolean>(false);

  // Fetch Portfolio Analysis
  const fetchAnalysis = async (savings: number = monthlySavings, ret: number = grossReturn) => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(
        `/api/portfolio/${portfolioId}/etf-overlap?monthly_savings=${savings}&gross_return=${ret / 100.0}`
      );
      if (!res.ok) {
        throw new Error('Fehler beim Abrufen der ETF-Overlap & Gebührenanalyse');
      }
      const json = await res.json();
      setData(json);
      setMonthlySavings(json.monthly_savings_input || savings);
    } catch (err: any) {
      setError(err.message || 'Verbindung fehlgeschlagen');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalysis(monthlySavings, grossReturn);
  }, [portfolioId]);

  // Handle custom fee recalculation
  const handleRecalculateFees = async () => {
    try {
      setIsSimulating(true);
      const res = await fetch(`/api/portfolio/${portfolioId}/etf-overlap`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          monthly_savings: Number(monthlySavings),
          gross_return: Number(grossReturn) / 100.0
        })
      });
      if (res.ok) {
        const updated = await res.json();
        setData(updated);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsSimulating(false);
    }
  };

  // Run pairwise ETF comparison
  const runPairwiseCompare = async () => {
    if (!compareEtf1 || !compareEtf2) return;
    try {
      setCompareLoading(true);
      const res = await fetch(
        `/api/etf/compare?etf1=${encodeURIComponent(compareEtf1)}&etf2=${encodeURIComponent(compareEtf2)}`
      );
      if (res.ok) {
        const json = await res.json();
        setCompareResult(json);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setCompareLoading(false);
    }
  };

  if (loading && !data) {
    return (
      <div className="flex flex-col items-center justify-center p-12 bg-slate-900/40 rounded-2xl border border-slate-800/80 backdrop-blur-md">
        <div className="w-10 h-10 border-4 border-cyan-500 border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-slate-300 font-medium animate-pulse">
          Berechne Look-Through Holding-Konzentration & Gebühren-Vampir-Modell...
        </p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-8 bg-rose-950/20 border border-rose-800/50 rounded-2xl text-center">
        <AlertTriangle className="w-10 h-10 text-rose-400 mx-auto mb-3" />
        <h3 className="text-lg font-bold text-rose-200 mb-1">Analyse konnte nicht geladen werden</h3>
        <p className="text-sm text-rose-300/80 mb-4">{error || 'Keine Daten vorhanden'}</p>
        <button
          onClick={() => fetchAnalysis()}
          className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white text-sm font-semibold rounded-lg transition"
        >
          Erneut versuchen
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 1. Header Overview & Fee Vampire Health Score */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-900 via-slate-900/90 to-slate-950 border border-slate-800/90 p-6 shadow-xl backdrop-blur-xl">
        <div className="absolute top-0 right-0 w-80 h-80 bg-gradient-to-bl from-cyan-500/10 via-amber-500/5 to-transparent rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 flex items-center gap-1.5">
                <PieChart className="w-3.5 h-3.5" />
                Portfolio X-Ray
              </span>
              <span
                className={`px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider flex items-center gap-1.5 border ${
                  data.fee_score === 'CHAMPION'
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                    : data.fee_score === 'MODERATE'
                    ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                    : 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                }`}
              >
                <Flame className="w-3.5 h-3.5" />
                {data.fee_score === 'CHAMPION'
                  ? 'Kosten-Champion'
                  : data.fee_score === 'MODERATE'
                  ? 'Moderates TER-Niveau'
                  : 'Gebühren-Vampir-Alarm'}
              </span>
            </div>

            <h2 className="text-2xl font-black text-white tracking-tight flex items-center gap-3">
              ETF-Overlap & Gebühren-Vampir-Detektor
            </h2>
            <p className="text-sm text-slate-400 max-w-2xl">{data.fee_headline}</p>
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={() => fetchAnalysis()}
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
            <p className="text-xs text-slate-400 font-medium">Gewichtete TER</p>
            <p
              className={`text-xl font-black mt-1 ${
                data.weighted_ter_pct <= 0.2
                  ? 'text-emerald-400'
                  : data.weighted_ter_pct <= 0.4
                  ? 'text-amber-400'
                  : 'text-rose-400'
              }`}
            >
              {data.weighted_ter_pct.toFixed(2)}% <span className="text-xs font-normal text-slate-500">p.a.</span>
            </p>
            <p className="text-[11px] text-slate-500 mt-0.5">Benchmark: 0.12%</p>
          </div>

          <div className="p-3.5 bg-slate-950/50 rounded-xl border border-slate-800/60">
            <p className="text-xs text-slate-400 font-medium">Portfoliowert</p>
            <p className="text-xl font-black text-white mt-1">
              {data.total_portfolio_value.toLocaleString('de-DE', { maximumFractionDigits: 0 })} €
            </p>
            <p className="text-[11px] text-slate-500 mt-0.5">
              {data.etf_count} {data.etf_count === 1 ? 'ETF' : 'ETFs'} + {data.single_stock_count} Aktien
            </p>
          </div>

          <div className="p-3.5 bg-slate-950/50 rounded-xl border border-slate-800/60">
            <p className="text-xs text-slate-400 font-medium">Top-3 Klumpen</p>
            <p
              className={`text-xl font-black mt-1 ${
                data.top_3_concentration_pct >= 35 ? 'text-amber-400' : 'text-cyan-400'
              }`}
            >
              {data.top_3_concentration_pct.toFixed(1)}%
            </p>
            <p className="text-[11px] text-slate-500 mt-0.5">Look-Through Gewicht</p>
          </div>

          <div className="p-3.5 bg-slate-950/50 rounded-xl border border-slate-800/60">
            <p className="text-xs text-slate-400 font-medium">Verlust 30J (Fees)</p>
            <p className="text-xl font-black text-rose-400 mt-1">
              -
              {(
                data.fee_simulations?.find((s) => s.years === 30)?.lost_to_fees || 0
              ).toLocaleString('de-DE', { maximumFractionDigits: 0 })}{' '}
              €
            </p>
            <p className="text-[11px] text-slate-500 mt-0.5">vs. 0.12% Low-Cost</p>
          </div>
        </div>

        {/* Warning Banner if cluster risk */}
        {data.cluster_warning && (
          <div className="mt-4 p-3.5 bg-amber-500/10 border border-amber-500/30 rounded-xl flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
            <span className="text-xs sm:text-sm font-medium text-amber-200">
              {data.cluster_warning}
            </span>
          </div>
        )}
      </div>

      {/* 2. Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
        <button
          onClick={() => setActiveTab('clusters')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold transition ${
            activeTab === 'clusters'
              ? 'bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 shadow-sm'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
          }`}
        >
          <Layers className="w-4 h-4" />
          Wahre Klumpen (Look-Through)
        </button>

        <button
          onClick={() => setActiveTab('overlap')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold transition ${
            activeTab === 'overlap'
              ? 'bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 shadow-sm'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
          }`}
        >
          <PieChart className="w-4 h-4" />
          ETF-Overlap-Matrix
        </button>

        <button
          onClick={() => setActiveTab('fees')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold transition ${
            activeTab === 'fees'
              ? 'bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 shadow-sm'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
          }`}
        >
          <Flame className="w-4 h-4" />
          Gebühren-Vampir & Zinseszins
        </button>
      </div>

      {/* 3. TAB CONTENT */}

      {/* TAB 1: Wahre Klumpen (Look-Through Concentration) */}
      {activeTab === 'clusters' && (
        <div className="space-y-6">
          <div className="p-5 bg-slate-900/60 rounded-2xl border border-slate-800/80 backdrop-blur-md">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-cyan-400" />
                  Effektive Durchleuchtungs-Gewichtung (Top 10 Positionen)
                </h3>
                <p className="text-xs text-slate-400 mt-1">
                  Kombiniert deine direkten Einzelaktien mit den indirekten Anteilen deiner ETFs für den wahren
                  Klumpenrisiko-Überblick.
                </p>
              </div>
            </div>

            <div className="space-y-3">
              {data.top_look_through_clusters.map((cluster, idx) => (
                <div
                  key={cluster.ticker}
                  className={`p-3.5 rounded-xl border transition flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                    cluster.is_mega_cluster
                      ? 'bg-amber-950/20 border-amber-600/40'
                      : 'bg-slate-950/40 border-slate-800/70 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center gap-3 min-w-[140px]">
                    <span className="w-6 h-6 rounded-md bg-slate-800 text-xs font-mono font-bold text-slate-400 flex items-center justify-center">
                      #{idx + 1}
                    </span>
                    <div>
                      <span className="text-sm font-black text-white">{cluster.ticker}</span>
                      {cluster.is_mega_cluster && (
                        <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                          Klumpen &ge;10%
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Progress Bar */}
                  <div className="flex-1 max-w-md">
                    <div className="flex justify-between text-xs font-semibold mb-1">
                      <span className="text-slate-400">Effektiver Anteil</span>
                      <span
                        className={
                          cluster.effective_portfolio_weight_pct >= 10.0
                            ? 'text-amber-400 font-bold'
                            : 'text-cyan-400 font-bold'
                        }
                      >
                        {cluster.effective_portfolio_weight_pct.toFixed(2)}%
                      </span>
                    </div>
                    <div className="w-full h-2.5 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${
                          cluster.effective_portfolio_weight_pct >= 15.0
                            ? 'bg-rose-500'
                            : cluster.effective_portfolio_weight_pct >= 10.0
                            ? 'bg-amber-400'
                            : 'bg-gradient-to-r from-cyan-500 to-blue-500'
                        }`}
                        style={{
                          width: `${Math.min(100, cluster.effective_portfolio_weight_pct * 3)}%`
                        }}
                      />
                    </div>
                  </div>

                  {/* Action */}
                  <div className="flex items-center gap-2">
                    {onAnalyzeStock && (
                      <button
                        onClick={() => onAnalyzeStock(cluster.ticker)}
                        className="px-2.5 py-1 text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded-lg border border-slate-700 transition flex items-center gap-1"
                      >
                        Analyse
                        <ExternalLink className="w-3 h-3" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: ETF-Overlap Matrix */}
      {activeTab === 'overlap' && (
        <div className="space-y-6">
          {/* Overlap Matrix if >= 2 ETFs in portfolio */}
          {data.etf_overlap_matrix && data.etf_overlap_matrix.length >= 2 ? (
            <div className="p-5 bg-slate-900/60 rounded-2xl border border-slate-800/80 backdrop-blur-md">
              <h3 className="text-lg font-bold text-white mb-1 flex items-center gap-2">
                <PieChart className="w-5 h-5 text-cyan-400" />
                Portfolio ETF-Overlap Matrix
              </h3>
              <p className="text-xs text-slate-400 mb-6">
                Prozentuale Überschneidung der Top-Holdings zwischen deinen Portfolio-ETFs.
              </p>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800 text-xs font-semibold text-slate-400">
                      <th className="p-3">ETF</th>
                      {data.etf_list.map((e) => (
                        <th key={e.ticker} className="p-3 text-center">
                          {e.ticker}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.etf_overlap_matrix.map((row, i) => (
                      <tr key={i} className="border-b border-slate-800/50">
                        <td className="p-3 font-bold text-white">{data.etf_list[i]?.ticker}</td>
                        {row.map((cell, j) => {
                          const pct = cell.overlap_pct;
                          let bg = 'bg-slate-950/40 text-slate-400';
                          if (cell.is_self) {
                            bg = 'bg-slate-800/50 text-slate-500 font-mono';
                          } else if (pct >= 50) {
                            bg = 'bg-rose-500/20 text-rose-300 font-bold border border-rose-500/30';
                          } else if (pct >= 25) {
                            bg = 'bg-amber-500/20 text-amber-300 font-bold border border-amber-500/30';
                          } else if (pct > 0) {
                            bg = 'bg-emerald-500/20 text-emerald-300 font-bold border border-emerald-500/30';
                          }
                          return (
                            <td key={j} className="p-2 text-center">
                              <span className={`inline-block px-3 py-1.5 rounded-lg text-xs ${bg}`}>
                                {pct.toFixed(1)}%
                              </span>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="p-6 bg-slate-900/60 rounded-2xl border border-slate-800/80 text-center">
              <Info className="w-8 h-8 text-cyan-400 mx-auto mb-2" />
              <h4 className="text-base font-bold text-white mb-1">
                {data.etf_count < 2
                  ? 'Nur ein oder kein ETF in diesem Portfolio'
                  : 'Keine Überschneidung gefunden'}
              </h4>
              <p className="text-xs text-slate-400 max-w-md mx-auto mb-4">
                Für eine automatische Portfolio-Matrix werden mindestens zwei ETFs benötigt. Nutze unten
                unseren Direktvergleich für beliebte Index-ETFs!
              </p>
            </div>
          )}

          {/* Standalone Pairwise ETF Compare Tool */}
          <div className="p-5 bg-slate-900/60 rounded-2xl border border-slate-800/80 backdrop-blur-md">
            <h3 className="text-lg font-bold text-white mb-1 flex items-center gap-2">
              <Search className="w-5 h-5 text-cyan-400" />
              Direkter 1-zu-1 ETF-Vergleich
            </h3>
            <p className="text-xs text-slate-400 mb-4">
              Vergleiche zwei beliebige Index-ETFs auf Überschneidungen und doppelte Positionen (z. B. MSCI World vs.
              S&amp;P 500, Nasdaq 100, All-World, DAX).
            </p>

            <div className="flex flex-col sm:flex-row items-center gap-3 mb-6">
              <div className="flex-1 w-full">
                <label className="text-xs font-medium text-slate-400 block mb-1">ETF 1</label>
                <select
                  value={compareEtf1}
                  onChange={(e) => setCompareEtf1(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500"
                >
                  <option value="URTH">iShares MSCI World (URTH / EUNL.DE)</option>
                  <option value="SPY">SPDR S&amp;P 500 (SPY / SXR8.DE)</option>
                  <option value="QQQ">Invesco QQQ / Nasdaq 100 (QQQ)</option>
                  <option value="VWCE.DE">Vanguard FTSE All-World (VWCE.DE)</option>
                  <option value="SMH">VanEck Semiconductor ETF (SMH)</option>
                  <option value="XLK">Technology Select Sector SPDR (XLK)</option>
                  <option value="EEM">iShares MSCI Emerging Markets (EEM / IS3N.DE)</option>
                  <option value="EXS1.DE">iShares Core DAX UCITS ETF (EXS1.DE)</option>
                  <option value="ARKK">ARK Innovation ETF (ARKK)</option>
                </select>
              </div>

              <div className="pt-5 hidden sm:block text-slate-500 font-bold">VS</div>

              <div className="flex-1 w-full">
                <label className="text-xs font-medium text-slate-400 block mb-1">ETF 2</label>
                <select
                  value={compareEtf2}
                  onChange={(e) => setCompareEtf2(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500"
                >
                  <option value="QQQ">Invesco QQQ / Nasdaq 100 (QQQ)</option>
                  <option value="SPY">SPDR S&amp;P 500 (SPY / SXR8.DE)</option>
                  <option value="URTH">iShares MSCI World (URTH / EUNL.DE)</option>
                  <option value="VWCE.DE">Vanguard FTSE All-World (VWCE.DE)</option>
                  <option value="SMH">VanEck Semiconductor ETF (SMH)</option>
                  <option value="XLK">Technology Select Sector SPDR (XLK)</option>
                  <option value="EEM">iShares MSCI Emerging Markets (EEM / IS3N.DE)</option>
                  <option value="EXS1.DE">iShares Core DAX UCITS ETF (EXS1.DE)</option>
                  <option value="ARKK">ARK Innovation ETF (ARKK)</option>
                </select>
              </div>

              <div className="w-full sm:w-auto pt-5">
                <button
                  onClick={runPairwiseCompare}
                  disabled={compareLoading}
                  className="w-full sm:w-auto px-5 py-2 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold text-sm rounded-xl transition shadow-md flex items-center justify-center gap-2"
                >
                  {compareLoading ? <RotateCcw className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                  Vergleichen
                </button>
              </div>
            </div>

            {compareResult && (
              <div className="p-4 bg-slate-950/60 rounded-xl border border-slate-800 space-y-4">
                <div className="flex flex-col sm:flex-row items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
                  <div>
                    <h4 className="text-base font-bold text-white">
                      {compareResult.etf_a.ticker} &times; {compareResult.etf_b.ticker}
                    </h4>
                    <p className="text-xs text-slate-400 mt-0.5">{compareResult.overlap_headline}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-2xl font-black text-cyan-400">
                      {compareResult.overlap_percentage.toFixed(1)}%
                    </span>
                    <span className="text-xs text-slate-400">Gewichtungs-Überschneidung</span>
                  </div>
                </div>

                <div className="space-y-2">
                  <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                    Top gemeinsame Holdings ({compareResult.shared_holdings_count} Schnittmengen)
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                    {compareResult.shared_holdings.map((sh) => (
                      <div
                        key={sh.ticker}
                        className="p-2.5 bg-slate-900/80 rounded-lg border border-slate-800/70 flex items-center justify-between"
                      >
                        <span className="font-bold text-sm text-white">{sh.ticker}</span>
                        <div className="text-right">
                          <span className="text-xs font-mono text-cyan-400 font-semibold">
                            {sh.overlap_contribution.toFixed(1)}% Überlappung
                          </span>
                          <p className="text-[10px] text-slate-500">
                            {sh.weight_in_a.toFixed(1)}% / {sh.weight_in_b.toFixed(1)}%
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 3: Gebühren-Vampir & Zinseszins-Rechner */}
      {activeTab === 'fees' && (
        <div className="space-y-6">
          {/* Interactive Controls Bar */}
          <div className="p-5 bg-slate-900/60 rounded-2xl border border-slate-800/80 backdrop-blur-md">
            <h3 className="text-lg font-bold text-white mb-2 flex items-center gap-2">
              <Flame className="w-5 h-5 text-amber-400" />
              Zinseszins-Kostenverlust-Simulator
            </h3>
            <p className="text-xs text-slate-400 mb-6">
              Simuliere die Auswirkung deiner laufenden Gesamtkostenquote (TER) im Vergleich zu einem Low-Cost
              All-World Core Portfolio (0.12% TER).
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 items-end">
              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">
                  Monatliche Sparrate (€):
                  <span className="text-cyan-400 ml-2 font-mono font-bold">{monthlySavings} €</span>
                </label>
                <input
                  type="range"
                  min="0"
                  max="2000"
                  step="50"
                  value={monthlySavings}
                  onChange={(e) => setMonthlySavings(Number(e.target.value))}
                  className="w-full accent-cyan-500"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">
                  Bruttorendite p.a. (%):
                  <span className="text-cyan-400 ml-2 font-mono font-bold">{grossReturn.toFixed(1)}%</span>
                </label>
                <input
                  type="range"
                  min="3.0"
                  max="12.0"
                  step="0.5"
                  value={grossReturn}
                  onChange={(e) => setGrossReturn(Number(e.target.value))}
                  className="w-full accent-cyan-500"
                />
              </div>

              <div>
                <button
                  onClick={handleRecalculateFees}
                  disabled={isSimulating}
                  className="w-full px-4 py-2.5 bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white font-bold text-sm rounded-xl transition shadow-md flex items-center justify-center gap-2"
                >
                  {isSimulating ? (
                    <RotateCcw className="w-4 h-4 animate-spin" />
                  ) : (
                    <Sparkles className="w-4 h-4" />
                  )}
                  Neu Berechnen
                </button>
              </div>
            </div>
          </div>

          {/* 10y, 20y, 30y Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {data.fee_simulations.map((sim) => (
              <div
                key={sim.years}
                className="relative overflow-hidden p-5 bg-gradient-to-b from-slate-900 to-slate-950 rounded-2xl border border-slate-800/80 shadow-lg"
              >
                <div className="flex items-center justify-between mb-3">
                  <span className="px-3 py-1 bg-slate-800 text-cyan-400 font-black text-xs rounded-full border border-slate-700">
                    {sim.years} Jahre Horizont
                  </span>
                  <span className="text-xs text-rose-400 font-bold flex items-center gap-1">
                    <TrendingDown className="w-3.5 h-3.5" />
                    -{sim.fee_drag_pct.toFixed(1)}% Renditeverlust
                  </span>
                </div>

                <div className="my-4">
                  <p className="text-xs text-slate-400">Verlust durch Gebühren (vs. 0.12%)</p>
                  <p className="text-2xl font-black text-rose-400 mt-1">
                    -{sim.lost_to_fees.toLocaleString('de-DE', { maximumFractionDigits: 0 })} €
                  </p>
                </div>

                <div className="space-y-2 pt-3 border-t border-slate-800/80 text-xs">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Endvermögen (aktuell):</span>
                    <span className="font-mono font-bold text-white">
                      {sim.projected_portfolio_value.toLocaleString('de-DE', { maximumFractionDigits: 0 })} €
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Endvermögen (0.12% Core):</span>
                    <span className="font-mono font-bold text-emerald-400">
                      {sim.benchmark_value.toLocaleString('de-DE', { maximumFractionDigits: 0 })} €
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Expensive Positions & Optimization Opportunities */}
          {data.expensive_positions && data.expensive_positions.length > 0 && (
            <div className="p-5 bg-rose-950/20 rounded-2xl border border-rose-800/50 backdrop-blur-md">
              <h4 className="text-base font-bold text-rose-200 mb-2 flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-rose-400" />
                Kostenoptimierungs-Potenzial (TER &ge; 0.35%)
              </h4>
              <p className="text-xs text-slate-300 mb-4">
                Folgende Positionen weisen eine überdurchschnittliche Kostenquote auf. Ein Austausch gegen
                Standard-Core-Produkte kann über Jahrzehnte tausende Euro Zinseszins sichern.
              </p>

              <div className="space-y-3">
                {data.expensive_positions.map((exp) => (
                  <div
                    key={exp.ticker}
                    className="p-3.5 bg-slate-900/80 rounded-xl border border-rose-900/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-white text-sm">{exp.ticker}</span>
                        <span className="text-xs text-slate-400">({exp.name})</span>
                        <span className="px-2 py-0.5 rounded text-xs font-mono font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30">
                          {exp.ter_pct.toFixed(2)}% TER
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mt-1">
                        Jährliche Kostenlast: ~{exp.annual_cost_eur.toFixed(2)} €/Jahr bei {exp.weight_pct}% Depotanteil
                      </p>
                    </div>

                    <div className="text-xs text-emerald-400 bg-emerald-950/40 px-3 py-1.5 rounded-lg border border-emerald-800/40">
                      <span className="text-slate-400 block text-[10px]">Günstigere Option:</span>
                      {exp.cheaper_alternative}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
