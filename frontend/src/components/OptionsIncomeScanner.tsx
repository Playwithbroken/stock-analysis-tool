import React, { useState, useEffect } from 'react';
import {
  TrendingUp,
  Coins,
  ShieldCheck,
  Zap,
  ArrowRight,
  Sparkles,
  RotateCcw,
  Sliders,
  DollarSign,
  AlertTriangle,
  Clock,
  Info,
  Layers,
  ChevronRight,
  ExternalLink
} from 'lucide-react';

export interface CoveredCallScenario {
  scenario: string;
  badge: string;
  color: 'emerald' | 'cyan' | 'amber';
  ideal_for: string;
  strike: number;
  premium_per_share: number;
  total_premium_eur: number;
  annualized_yield_pct: number;
  downside_buffer_pct: number;
  max_total_return_pct: number;
  pop_pct: number;
  delta: number;
  daily_theta: number;
  break_even: number;
}

export interface CashSecuredPutScenario {
  scenario: string;
  badge: string;
  color: 'emerald' | 'cyan' | 'amber';
  ideal_for: string;
  strike: number;
  premium_per_share: number;
  total_premium_eur: number;
  capital_required_eur: number;
  return_on_capital_pct: number;
  net_entry_price: number;
  discount_to_market_pct: number;
  pop_pct: number;
  delta: number;
  daily_theta: number;
}

export interface StockOptionsData {
  ticker: string;
  current_price: number;
  shares_analyzed: number;
  contracts_count: number;
  dte: number;
  implied_volatility_pct: number;
  risk_free_rate_pct: number;
  covered_calls: CoveredCallScenario[];
  cash_secured_puts: CashSecuredPutScenario[];
}

export interface PortfolioPositionOption {
  ticker: string;
  name: string;
  shares: number;
  current_price: number;
  position_value: number;
  is_full_lot: boolean;
  contracts: number;
  strike: number;
  premium_per_share: number;
  estimated_monthly_income_eur: number;
  annualized_yield_pct: number;
  pop_pct: number;
  downside_buffer_pct: number;
  iv_pct: number;
}

export interface PortfolioOptionsData {
  dte: number;
  total_monthly_cashflow_eur: number;
  total_annual_cashflow_eur: number;
  total_covered_value_eur: number;
  full_lots_count: number;
  positions: PortfolioPositionOption[];
  summary_headline: string;
  portfolio_id?: string;
  portfolio_name?: string;
}

interface OptionsIncomeScannerProps {
  ticker?: string;
  currentPrice?: number;
  portfolioId?: string;
  onAnalyzeStock?: (ticker: string) => void;
}

export default function OptionsIncomeScanner({
  ticker,
  currentPrice,
  portfolioId,
  onAnalyzeStock,
}: OptionsIncomeScannerProps) {
  // Mode: Single stock vs. Portfolio
  const isSingleStock = Boolean(ticker);

  // Single Stock State
  const [stockData, setStockData] = useState<StockOptionsData | null>(null);
  const [activeStrategy, setActiveStrategy] = useState<'cc' | 'csp'>('cc');
  const [dte, setDte] = useState<number>(30);
  const [shares, setShares] = useState<number>(100);

  // Portfolio State
  const [portfolioData, setPortfolioData] = useState<PortfolioOptionsData | null>(null);
  const [selectedHoldingTicker, setSelectedHoldingTicker] = useState<string | null>(null);

  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch Single Stock Options Suite
  const fetchSingleStock = async (curDte: number = dte, curShares: number = shares) => {
    if (!ticker) return;
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`/api/options/${ticker}?dte=${curDte}&shares=${curShares}`);
      if (!res.ok) throw new Error('Fehler beim Abruf der Optionsdaten');
      const json = await res.json();
      setStockData(json);
    } catch (err: any) {
      setError(err.message || 'Verbindung fehlgeschlagen');
    } finally {
      setLoading(false);
    }
  };

  // Fetch Portfolio Options Income
  const fetchPortfolioOptions = async (curDte: number = dte) => {
    if (!portfolioId) return;
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`/api/portfolio/${portfolioId}/options-income?dte=${curDte}`);
      if (!res.ok) throw new Error('Fehler beim Abruf der Portfolio-Optionsdaten');
      const json = await res.json();
      setPortfolioData(json);
    } catch (err: any) {
      setError(err.message || 'Verbindung fehlgeschlagen');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isSingleStock) {
      fetchSingleStock(dte, shares);
    } else if (portfolioId) {
      fetchPortfolioOptions(dte);
    }
  }, [ticker, portfolioId]);

  if (loading && !stockData && !portfolioData) {
    return (
      <div className="flex flex-col items-center justify-center p-12 bg-slate-900/40 rounded-2xl border border-slate-800/80 backdrop-blur-md">
        <div className="w-10 h-10 border-4 border-amber-500 border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-slate-300 font-medium animate-pulse">
          Berechne Black-Scholes Optionsprämien, Greeks &amp; Cashflow-Potenzial...
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8 bg-rose-950/20 border border-rose-800/50 rounded-2xl text-center">
        <AlertTriangle className="w-10 h-10 text-rose-400 mx-auto mb-3" />
        <h3 className="text-lg font-bold text-rose-200 mb-1">Optionsanalyse fehlgeschlagen</h3>
        <p className="text-sm text-rose-300/80 mb-4">{error}</p>
        <button
          onClick={() => (isSingleStock ? fetchSingleStock() : fetchPortfolioOptions())}
          className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white text-sm font-semibold rounded-lg transition"
        >
          Erneut versuchen
        </button>
      </div>
    );
  }

  // --- RENDERING 1: SINGLE STOCK MODE ---
  if (isSingleStock && stockData) {
    return (
      <div className="space-y-6">
        {/* Header Hero Card */}
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-900 via-slate-900/90 to-slate-950 border border-slate-800/90 p-6 shadow-xl backdrop-blur-xl">
          <div className="absolute top-0 right-0 w-80 h-80 bg-gradient-to-bl from-amber-500/10 via-cyan-500/5 to-transparent rounded-full blur-3xl pointer-events-none" />

          <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-amber-500/10 text-amber-400 border border-amber-500/20 flex items-center gap-1.5">
                  <Coins className="w-3.5 h-3.5" />
                  Stillhalter-Cashflow
                </span>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                  Black-Scholes-Merton Modell
                </span>
              </div>

              <h2 className="text-2xl font-black text-white tracking-tight flex items-center gap-3">
                Options- &amp; Stillhalter-Rechner ({stockData.ticker})
              </h2>
              <p className="text-sm text-slate-400 max-w-2xl">
                Aktueller Kurs: <strong className="text-white font-mono">{stockData.current_price.toFixed(2)} €</strong> &bull; Implizite Volatilität: <strong className="text-amber-400 font-mono">{stockData.implied_volatility_pct}%</strong>
              </p>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={() => fetchSingleStock(dte, shares)}
                disabled={loading}
                className="p-2.5 bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700 rounded-xl text-slate-300 hover:text-white transition shadow-sm"
                title="Aktualisieren"
              >
                <RotateCcw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>

          {/* Strategy Tabs */}
          <div className="flex items-center gap-3 mt-6 pt-4 border-t border-slate-800/80">
            <button
              onClick={() => setActiveStrategy('cc')}
              className={`flex-1 py-2.5 px-4 rounded-xl text-xs sm:text-sm font-bold transition flex items-center justify-center gap-2 ${
                activeStrategy === 'cc'
                  ? 'bg-gradient-to-r from-amber-500/20 to-orange-500/20 text-amber-300 border border-amber-500/40 shadow-sm'
                  : 'bg-slate-950/60 text-slate-400 border border-slate-800 hover:text-white'
              }`}
            >
              <TrendingUp className="w-4 h-4" />
              Covered Call ("Aktien vermieten" &bull; Zusatzrendite)
            </button>
            <button
              onClick={() => setActiveStrategy('csp')}
              className={`flex-1 py-2.5 px-4 rounded-xl text-xs sm:text-sm font-bold transition flex items-center justify-center gap-2 ${
                activeStrategy === 'csp'
                  ? 'bg-gradient-to-r from-cyan-500/20 to-blue-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                  : 'bg-slate-950/60 text-slate-400 border border-slate-800 hover:text-white'
              }`}
            >
              <ShieldCheck className="w-4 h-4" />
              Cash-Secured Put ("Rabatt-Kauf mit Prämie")
            </button>
          </div>
        </div>

        {/* Interactive Parameter Sliders */}
        <div className="p-5 bg-slate-900/60 rounded-2xl border border-slate-800/80 backdrop-blur-md">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            <div>
              <div className="flex justify-between text-xs font-semibold mb-1">
                <span className="text-slate-300">Restlaufzeit (DTE):</span>
                <span className="text-amber-400 font-mono font-bold">{dte} Tage</span>
              </div>
              <input
                type="range"
                min="7"
                max="90"
                step="7"
                value={dte}
                onChange={(e) => {
                  const val = Number(e.target.value);
                  setDte(val);
                  fetchSingleStock(val, shares);
                }}
                className="w-full accent-amber-500"
              />
              <div className="flex justify-between text-[10px] text-slate-500 mt-1">
                <span>1 Woche</span>
                <span>30 Tage (Standard)</span>
                <span>60 Tage</span>
                <span>90 Tage</span>
              </div>
            </div>

            <div>
              <div className="flex justify-between text-xs font-semibold mb-1">
                <span className="text-slate-300">Anzahl gehaltener Aktien:</span>
                <span className="text-cyan-400 font-mono font-bold">
                  {shares} Stk. ({stockData.contracts_count} {stockData.contracts_count === 1 ? 'Kontrakt' : 'Kontrakte'})
                </span>
              </div>
              <input
                type="range"
                min="100"
                max="1000"
                step="100"
                value={shares}
                onChange={(e) => {
                  const val = Number(e.target.value);
                  setShares(val);
                  fetchSingleStock(dte, val);
                }}
                className="w-full accent-cyan-500"
              />
              <div className="flex justify-between text-[10px] text-slate-500 mt-1">
                <span>100 (1 Kontrakt)</span>
                <span>300</span>
                <span>500</span>
                <span>1.000</span>
              </div>
            </div>
          </div>
        </div>

        {/* 3 Strategy Scenario Cards */}
        {activeStrategy === 'cc' ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {stockData.covered_calls.map((cc) => (
              <div
                key={cc.scenario}
                className="relative overflow-hidden p-5 bg-gradient-to-b from-slate-900 to-slate-950 rounded-2xl border border-slate-800/80 shadow-lg flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-base font-black text-white">{cc.scenario}</span>
                    <span
                      className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                        cc.color === 'emerald'
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                          : cc.color === 'cyan'
                          ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                          : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                      }`}
                    >
                      {cc.badge}
                    </span>
                  </div>

                  <p className="text-xs text-slate-400 mb-4">{cc.ideal_for}</p>

                  <div className="space-y-2 py-3 border-y border-slate-800/80 text-xs">
                    <div className="flex justify-between">
                      <span className="text-slate-400">Ausübungskurs (Strike):</span>
                      <span className="font-mono font-bold text-white text-sm">{cc.strike.toFixed(2)} €</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Prämie pro Aktie:</span>
                      <span className="font-mono font-bold text-amber-400">+{cc.premium_per_share.toFixed(2)} €</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Sofort-Cashflow ({shares} Stk.):</span>
                      <span className="font-mono font-black text-emerald-400 text-sm">
                        +{cc.total_premium_eur.toFixed(2)} €
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Annualisierte Zusatzrendite:</span>
                      <span className="font-mono font-bold text-cyan-400">+{cc.annualized_yield_pct.toFixed(1)} % p.a.</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Downside-Puffer:</span>
                      <span className="font-mono text-slate-300">-{cc.downside_buffer_pct.toFixed(1)} %</span>
                    </div>
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-slate-800/50 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-1.5 text-slate-400">
                    <ShieldCheck className="w-4 h-4 text-emerald-400" />
                    <span>Chance, Aktie zu behalten:</span>
                  </div>
                  <span className="font-mono font-black text-emerald-400">{cc.pop_pct}%</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {stockData.cash_secured_puts.map((csp) => (
              <div
                key={csp.scenario}
                className="relative overflow-hidden p-5 bg-gradient-to-b from-slate-900 to-slate-950 rounded-2xl border border-slate-800/80 shadow-lg flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-base font-black text-white">{csp.scenario}</span>
                    <span
                      className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                        csp.color === 'emerald'
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                          : csp.color === 'cyan'
                          ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                          : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                      }`}
                    >
                      {csp.badge}
                    </span>
                  </div>

                  <p className="text-xs text-slate-400 mb-4">{csp.ideal_for}</p>

                  <div className="space-y-2 py-3 border-y border-slate-800/80 text-xs">
                    <div className="flex justify-between">
                      <span className="text-slate-400">Kauflimit (Put-Strike):</span>
                      <span className="font-mono font-bold text-white text-sm">{csp.strike.toFixed(2)} €</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Effektiver Kaufpreis:</span>
                      <span className="font-mono font-bold text-emerald-400">
                        {csp.net_entry_price.toFixed(2)} € (-{csp.discount_to_market_pct}%)
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Vereinnahmte Prämie:</span>
                      <span className="font-mono font-black text-amber-400 text-sm">
                        +{csp.total_premium_eur.toFixed(2)} €
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Rendite auf Cash-Puffer:</span>
                      <span className="font-mono font-bold text-cyan-400">+{csp.return_on_capital_pct.toFixed(1)} % p.a.</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Hinterlegtes Barkapital:</span>
                      <span className="font-mono text-slate-300">{csp.capital_required_eur.toLocaleString('de-DE')} €</span>
                    </div>
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-slate-800/50 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-1.5 text-slate-400">
                    <Coins className="w-4 h-4 text-cyan-400" />
                    <span>Chance, Prämie ohne Kauf zu behalten:</span>
                  </div>
                  <span className="font-mono font-black text-cyan-400">{csp.pop_pct}%</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // --- RENDERING 2: PORTFOLIO MODE ---
  if (!isSingleStock && portfolioData) {
    return (
      <div className="space-y-6">
        {/* Header Hero Card */}
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-900 via-slate-900/90 to-slate-950 border border-slate-800/90 p-6 shadow-xl backdrop-blur-xl">
          <div className="absolute top-0 right-0 w-80 h-80 bg-gradient-to-bl from-amber-500/10 via-emerald-500/5 to-transparent rounded-full blur-3xl pointer-events-none" />

          <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-amber-500/10 text-amber-400 border border-amber-500/20 flex items-center gap-1.5">
                  <Coins className="w-3.5 h-3.5" />
                  Portfolio Stillhalter-Scanner
                </span>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  Monatlicher Cashflow
                </span>
              </div>

              <h2 className="text-2xl font-black text-white tracking-tight flex items-center gap-3">
                Covered-Call Cashflow-Radar
              </h2>
              <p className="text-sm text-slate-400 max-w-2xl">{portfolioData.summary_headline}</p>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={() => fetchPortfolioOptions(dte)}
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
              <p className="text-xs text-slate-400 font-medium">Monatlicher Cashflow</p>
              <p className="text-xl font-black text-emerald-400 mt-1">
                +{portfolioData.total_monthly_cashflow_eur.toLocaleString('de-DE', { minimumFractionDigits: 0 })} €
              </p>
              <p className="text-[11px] text-slate-500 mt-0.5">aus vollen 100er-Positionen</p>
            </div>

            <div className="p-3.5 bg-slate-950/50 rounded-xl border border-slate-800/60">
              <p className="text-xs text-slate-400 font-medium">Jährlicher Cashflow</p>
              <p className="text-xl font-black text-amber-400 mt-1">
                +{portfolioData.total_annual_cashflow_eur.toLocaleString('de-DE', { minimumFractionDigits: 0 })} €
              </p>
              <p className="text-[11px] text-slate-500 mt-0.5">p.a. Zusatzertrag</p>
            </div>

            <div className="p-3.5 bg-slate-950/50 rounded-xl border border-slate-800/60">
              <p className="text-xs text-slate-400 font-medium">100er-Positionen</p>
              <p className="text-xl font-black text-white mt-1">
                {portfolioData.full_lots_count} / {portfolioData.positions.length}
              </p>
              <p className="text-[11px] text-slate-500 mt-0.5">sofort kontraktfähig</p>
            </div>

            <div className="p-3.5 bg-slate-950/50 rounded-xl border border-slate-800/60">
              <p className="text-xs text-slate-400 font-medium">Standard-Laufzeit</p>
              <p className="text-xl font-black text-cyan-400 mt-1">{portfolioData.dte} Tage</p>
              <p className="text-[11px] text-slate-500 mt-0.5">monatlicher Rollzyklus</p>
            </div>
          </div>
        </div>

        {/* Positions Table */}
        <div className="p-5 bg-slate-900/60 rounded-2xl border border-slate-800/80 backdrop-blur-md">
          <h3 className="text-base font-bold text-white mb-1 flex items-center gap-2">
            <Layers className="w-5 h-5 text-amber-400" />
            Covered-Call Potenzial nach Positionen (Ausgewogenes Szenario)
          </h3>
          <p className="text-xs text-slate-400 mb-4">
            Berechnet auf Basis des aktuellen Marktkurses und der historischen impliziten Volatilität.
          </p>

          <div className="space-y-3">
            {portfolioData.positions.map((pos) => (
              <div
                key={pos.ticker}
                className={`p-4 rounded-xl border transition flex flex-col lg:flex-row lg:items-center justify-between gap-4 ${
                  pos.is_full_lot
                    ? 'bg-slate-950/60 border-slate-800/90 hover:border-slate-700'
                    : 'bg-slate-950/30 border-slate-800/40 opacity-75'
                }`}
              >
                <div className="space-y-1 min-w-[180px]">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-base text-white">{pos.ticker}</span>
                    <span className="text-xs text-slate-400 truncate max-w-[140px]">({pos.name})</span>
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        pos.is_full_lot
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                          : 'bg-slate-800 text-slate-400'
                      }`}
                    >
                      {pos.is_full_lot ? `${pos.contracts} Kontrakt(e)` : `${pos.shares} Stk.`}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400">
                    Kurs: {pos.current_price.toFixed(2)} € &bull; Depotwert: {pos.position_value.toLocaleString('de-DE')} €
                  </p>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
                  <div>
                    <span className="text-slate-500 block text-[10px]">Empfohlener Strike</span>
                    <span className="font-mono font-bold text-white text-sm">{pos.strike.toFixed(2)} €</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">Prämie / Aktie</span>
                    <span className="font-mono font-bold text-amber-400">+{pos.premium_per_share.toFixed(2)} €</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">Monats-Ertrag</span>
                    <span
                      className={`font-mono font-black text-sm ${
                        pos.is_full_lot ? 'text-emerald-400' : 'text-slate-400'
                      }`}
                    >
                      +{pos.estimated_monthly_income_eur.toFixed(0)} €
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">Zusatzrendite p.a.</span>
                    <span className="font-mono font-bold text-cyan-400">+{pos.annualized_yield_pct.toFixed(1)}%</span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {onAnalyzeStock && (
                    <button
                      onClick={() => onAnalyzeStock(pos.ticker)}
                      className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded-lg border border-slate-700 text-xs font-semibold flex items-center gap-1 transition"
                    >
                      Rechner öffnen
                      <ChevronRight className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return null;
}
