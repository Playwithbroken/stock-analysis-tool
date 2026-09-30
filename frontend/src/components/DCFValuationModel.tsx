import React, { useState, useMemo } from 'react';
import {
  Calculator,
  TrendingUp,
  TrendingDown,
  ShieldCheck,
  Sparkles,
  Sliders,
  ChevronDown,
  ChevronUp,
  Layers,
  RotateCcw
} from 'lucide-react';

export interface DCFValuationData {
  ticker: string;
  currency: string;
  current_price: number;
  fair_value: number;
  target_buy_price: number;
  margin_of_safety_pct: number;
  upside_pct: number;
  evaluation: string;
  action_badge: string;
  color: string;
  implied_growth_rate: number | null;
  inputs: {
    base_fcf: number;
    base_fcf_source: string;
    fcf_is_estimated: boolean;
    fcf_growth_rate: number;
    discount_rate: number;
    terminal_growth_rate: number;
    projection_years: number;
    shares_outstanding: number;
    cash: number;
    debt: number;
    net_debt: number;
  };
  enterprise_value: number;
  equity_value: number;
  projections: Array<{
    year: number;
    fcf: number;
    pv: number;
    discount_factor: number;
  }>;
  scenarios: {
    bear: ScenarioItem;
    base: ScenarioItem;
    bull: ScenarioItem;
  };
  sensitivity_matrix: {
    wacc_axis: number[];
    growth_axis: number[];
    matrix: Array<Array<MatrixCell>>;
  };
}

export interface ScenarioItem {
  name: string;
  icon: string;
  growth: number;
  wacc: number;
  terminal_growth: number;
  fair_value: number;
  target_price: number;
  upside_pct: number;
}

export interface MatrixCell {
  wacc: number;
  growth: number;
  fair_value: number;
  upside_pct: number;
  verdict: 'undervalued' | 'fair' | 'overvalued';
}

interface DCFValuationModelProps {
  initialData?: DCFValuationData | null;
  ticker: string;
  companyName?: string;
  currentPrice?: number;
  currency?: string;
}

function formatLargeMoney(val: number, curr: string = 'USD'): string {
  const abs = Math.abs(val);
  const sign = val < 0 ? '-' : '';
  if (abs >= 1e12) return `${sign}${(abs / 1e12).toFixed(2)} Bio. ${curr}`;
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(2)} Mrd. ${curr}`;
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(1)} Mio. ${curr}`;
  return `${sign}${abs.toFixed(0)} ${curr}`;
}

export default function DCFValuationModel({
  initialData,
  ticker,
  companyName,
  currentPrice = 0,
  currency = 'USD',
}: DCFValuationModelProps) {
  if (!initialData) return null;

  const rawInputs = initialData.inputs;
  const effectivePrice = initialData.current_price || currentPrice;
  const effectiveCurrency = initialData.currency || currency;

  // Interactive slider states initialized from initialData
  const [growthRate, setGrowthRate] = useState<number>(rawInputs.fcf_growth_rate);
  const [discountRate, setDiscountRate] = useState<number>(rawInputs.discount_rate);
  const [terminalGrowth, setTerminalGrowth] = useState<number>(rawInputs.terminal_growth_rate);
  const [marginOfSafety, setMarginOfSafety] = useState<number>(initialData.margin_of_safety_pct / 100);
  const [projectionYears, setProjectionYears] = useState<number>(rawInputs.projection_years || 5);
  const [activeScenario, setActiveScenario] = useState<'bear' | 'base' | 'bull' | 'custom'>('base');
  const [showProjections, setShowProjections] = useState<boolean>(false);

  // Client-side instant recalculation
  const calculatedModel = useMemo(() => {
    const baseFcf = rawInputs.base_fcf;
    const shares = rawInputs.shares_outstanding;
    const cash = rawInputs.cash;
    const debt = rawInputs.debt;

    const r = discountRate;
    const g = growthRate;
    const gt = Math.min(terminalGrowth, r - 0.005);
    const mos = marginOfSafety;

    // Projection calculation
    const projs = [];
    let curFcf = baseFcf;
    let totalPv = 0;
    for (let t = 1; t <= projectionYears; t++) {
      curFcf *= 1.0 + g;
      const pv = curFcf / Math.pow(1.0 + r, t);
      totalPv += pv;
      projs.push({
        year: t,
        fcf: Math.round(curFcf),
        pv: Math.round(pv),
        discount_factor: Number((1.0 / Math.pow(1.0 + r, t)).toFixed(4)),
      });
    }

    const tv = (curFcf * (1.0 + gt)) / (r - gt);
    const pvTv = tv / Math.pow(1.0 + r, projectionYears);
    const ev = totalPv + pvTv;
    const equity = Math.max(0, ev + cash - debt);
    const fairValue = shares > 0 ? equity / shares : 0;
    const targetBuyPrice = fairValue * (1.0 - mos);
    const upsidePct = effectivePrice > 0 ? ((fairValue / effectivePrice) - 1.0) * 100 : 0;

    // Reverse DCF bisection
    let impliedGrowth: number | null = null;
    if (baseFcf > 0 && effectivePrice > 0 && shares > 0) {
      const targetEq = effectivePrice * shares;
      const targetEv = Math.max(0, targetEq - cash + debt);

      const evForG = (gCand: number) => {
        let fcfC = baseFcf;
        let pvSum = 0;
        for (let t = 1; t <= projectionYears; t++) {
          fcfC *= 1.0 + gCand;
          pvSum += fcfC / Math.pow(1.0 + r, t);
        }
        const tvC = (fcfC * (1.0 + gt)) / (r - gt);
        return pvSum + tvC / Math.pow(1.0 + r, projectionYears);
      };

      let low = -0.4;
      let high = 1.5;
      if (targetEv >= evForG(high)) {
        high = 2.5;
      }
      for (let step = 0; step < 30; step++) {
        const mid = (low + high) / 2;
        if (evForG(mid) < targetEv) low = mid;
        else high = mid;
      }
      impliedGrowth = Number(((low + high) / 2 * 100).toFixed(1));
    }

    // Sensitivity matrix centered around current (r, g)
    const waccSteps = [
      Math.max(gt + 0.008, Number((r - 0.02).toFixed(3))),
      Math.max(gt + 0.008, Number((r - 0.01).toFixed(3))),
      Number(r.toFixed(3)),
      Number((r + 0.01).toFixed(3)),
      Number((r + 0.02).toFixed(3)),
    ];
    const growthSteps = [
      Number((g - 0.04).toFixed(3)),
      Number((g - 0.02).toFixed(3)),
      Number(g.toFixed(3)),
      Number((g + 0.02).toFixed(3)),
      Number((g + 0.04).toFixed(3)),
    ];

    const matrix: MatrixCell[][] = waccSteps.map((wVal) => {
      return growthSteps.map((gVal) => {
        let cF = baseFcf;
        let pSum = 0;
        for (let t = 1; t <= projectionYears; t++) {
          cF *= 1.0 + gVal;
          pSum += cF / Math.pow(1.0 + wVal, t);
        }
        const wGt = Math.min(gt, wVal - 0.005);
        const tVal = (cF * (1.0 + wGt)) / (wVal - wGt);
        const pTv = tVal / Math.pow(1.0 + wVal, projectionYears);
        const eVal = Math.max(0, pSum + pTv + cash - debt);
        const fVal = shares > 0 ? eVal / shares : 0;
        const upPct = effectivePrice > 0 ? ((fVal / effectivePrice) - 1.0) * 100 : 0;
        let verdict: 'undervalued' | 'fair' | 'overvalued' = 'overvalued';
        if (upPct >= mos * 100) verdict = 'undervalued';
        else if (upPct >= -5) verdict = 'fair';
        return {
          wacc: wVal,
          growth: gVal,
          fair_value: Number(fVal.toFixed(2)),
          upside_pct: Number(upPct.toFixed(1)),
          verdict,
        };
      });
    });

    let verdictText = 'Fair bewertet';
    let badgeColor = 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30';
    let actionBadge = 'HOLD';
    if (upsidePct >= mos * 100) {
      verdictText = 'Unterbewertet (Sicherheitsmarge erfüllt)';
      badgeColor = 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30';
      actionBadge = 'BUY';
    } else if (upsidePct < 0) {
      verdictText = 'Überbewertet';
      badgeColor = 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/30';
      actionBadge = 'REDUCE';
    }

    return {
      fairValue: Number(fairValue.toFixed(2)),
      targetBuyPrice: Number(targetBuyPrice.toFixed(2)),
      upsidePct: Number(upsidePct.toFixed(1)),
      verdictText,
      badgeColor,
      actionBadge,
      enterpriseValue: ev,
      equityValue: equity,
      projections: projs,
      terminalValue: tv,
      pvTerminalValue: pvTv,
      impliedGrowth,
      sensitivityMatrix: {
        waccAxis: waccSteps,
        growthAxis: growthSteps,
        grid: matrix,
      },
    };
  }, [
    rawInputs,
    effectivePrice,
    growthRate,
    discountRate,
    terminalGrowth,
    marginOfSafety,
    projectionYears,
  ]);

  const applyScenario = (type: 'bear' | 'base' | 'bull') => {
    setActiveScenario(type);
    const sc = initialData.scenarios[type];
    if (sc) {
      setGrowthRate(sc.growth);
      setDiscountRate(sc.wacc);
      setTerminalGrowth(sc.terminal_growth);
    }
  };

  const resetDefaults = () => {
    setActiveScenario('base');
    setGrowthRate(rawInputs.fcf_growth_rate);
    setDiscountRate(rawInputs.discount_rate);
    setTerminalGrowth(rawInputs.terminal_growth_rate);
    setMarginOfSafety(initialData.margin_of_safety_pct / 100);
    setProjectionYears(rawInputs.projection_years || 5);
  };

  return (
    <section className="surface-panel rounded-[2rem] p-5 sm:p-7">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-500/10 text-emerald-500">
            <Calculator className="h-6 w-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500 dark:text-neutral-400">
                DCF & Fair-Value Rechner
              </span>
              <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-bold text-emerald-600 dark:text-emerald-400">
                Reverse-DCF
              </span>
            </div>
            <h3 className="text-2xl font-bold text-slate-900 dark:text-white">
              Innerer Wert & Sicherheitsmarge
            </h3>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-xl bg-slate-100 p-1 dark:bg-neutral-800">
            <button
              onClick={() => applyScenario('bear')}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
                activeScenario === 'bear'
                  ? 'bg-white text-slate-900 shadow-sm dark:bg-neutral-700 dark:text-white'
                  : 'text-slate-500 hover:text-slate-900 dark:text-neutral-400'
              }`}
            >
              <span>🐻</span> Bär
            </button>
            <button
              onClick={() => applyScenario('base')}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
                activeScenario === 'base'
                  ? 'bg-white text-slate-900 shadow-sm dark:bg-neutral-700 dark:text-white'
                  : 'text-slate-500 hover:text-slate-900 dark:text-neutral-400'
              }`}
            >
              <span>⚖️</span> Basis
            </button>
            <button
              onClick={() => applyScenario('bull')}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
                activeScenario === 'bull'
                  ? 'bg-white text-slate-900 shadow-sm dark:bg-neutral-700 dark:text-white'
                  : 'text-slate-500 hover:text-slate-900 dark:text-neutral-400'
              }`}
            >
              <span>🐂</span> Bulle
            </button>
          </div>

          <button
            onClick={resetDefaults}
            title="Auf Standardwerte zurücksetzen"
            className="rounded-xl border border-slate-200 p-2 text-slate-500 transition-colors hover:bg-slate-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
          >
            <RotateCcw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Main KPI Hero Cards */}
      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* Fair Value */}
        <div className="rounded-2xl border border-slate-200/80 bg-slate-50/70 p-4 dark:border-neutral-800 dark:bg-neutral-800/40">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-neutral-400">
            Fairer Wert je Aktie
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-slate-900 dark:text-white">
              {calculatedModel.fairValue.toFixed(2)} {effectiveCurrency}
            </span>
          </div>
          <div className="mt-1 flex items-center gap-1.5 text-xs font-semibold">
            {calculatedModel.upsidePct >= 0 ? (
              <span className="flex items-center text-emerald-600 dark:text-emerald-400">
                <TrendingUp className="mr-1 h-3.5 w-3.5" />+{calculatedModel.upsidePct}% Upside
              </span>
            ) : (
              <span className="flex items-center text-rose-600 dark:text-rose-400">
                <TrendingDown className="mr-1 h-3.5 w-3.5" />{calculatedModel.upsidePct}% Downside
              </span>
            )}
            <span className="text-slate-400">(Aktuell: {effectivePrice.toFixed(2)} {effectiveCurrency})</span>
          </div>
        </div>

        {/* Target Price with Margin of Safety */}
        <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-4 dark:border-emerald-500/30 dark:bg-emerald-500/10">
          <div className="flex items-center justify-between text-[11px] font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-300">
            <span>Kauf-Limit (Margin of Safety)</span>
            <ShieldCheck className="h-4 w-4 text-emerald-500" />
          </div>
          <div className="mt-2 text-3xl font-extrabold text-emerald-900 dark:text-emerald-200">
            {calculatedModel.targetBuyPrice.toFixed(2)} {effectiveCurrency}
          </div>
          <div className="mt-1 text-xs text-emerald-700/80 dark:text-emerald-300/80">
            Inkl. {(marginOfSafety * 100).toFixed(0)}% Sicherheitsabstand zum fairen Wert
          </div>
        </div>

        {/* Reverse-DCF Implied Growth */}
        <div className="rounded-2xl border border-indigo-500/20 bg-indigo-500/5 p-4 dark:border-indigo-500/30 dark:bg-indigo-500/10">
          <div className="flex items-center justify-between text-[11px] font-bold uppercase tracking-wider text-indigo-700 dark:text-indigo-300">
            <span>Markterwartung (Reverse-DCF)</span>
            <Sparkles className="h-4 w-4 text-indigo-500" />
          </div>
          <div className="mt-2 text-3xl font-extrabold text-indigo-900 dark:text-indigo-200">
            {calculatedModel.impliedGrowth !== null ? `${calculatedModel.impliedGrowth > 0 ? '+' : ''}${calculatedModel.impliedGrowth}%` : 'N/A'}
          </div>
          <div className="mt-1 text-xs text-indigo-700/80 dark:text-indigo-300/80">
            Jährl. FCF-Wachstum, das der Markt aktuell einpreist
          </div>
        </div>

        {/* Valuation Assessment Badge */}
        <div className={`flex flex-col justify-between rounded-2xl border p-4 ${calculatedModel.badgeColor}`}>
          <div className="text-[11px] font-bold uppercase tracking-wider">
            Gesamtbewertung
          </div>
          <div className="my-1">
            <div className="text-2xl font-black">{calculatedModel.actionBadge}</div>
            <div className="text-xs font-medium opacity-90">{calculatedModel.verdictText}</div>
          </div>
          <div className="text-[11px] opacity-75">
            Modell: 5-Jahres FCF-Projektion + Gordon Growth
          </div>
        </div>
      </div>

      {/* Interactive Sliders Section */}
      <div className="mt-6 rounded-2xl border border-slate-200/80 bg-white/50 p-5 dark:border-neutral-800 dark:bg-neutral-900/40">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-neutral-800">
          <div className="flex items-center gap-2 text-sm font-bold text-slate-900 dark:text-white">
            <Sliders className="h-4 w-4 text-emerald-500" />
            <span>Modell-Parameter interaktiv anpassen</span>
          </div>
          <span className="text-xs text-slate-500 dark:text-neutral-400">
            Basis-FCF: {formatLargeMoney(rawInputs.base_fcf, effectiveCurrency)} ({rawInputs.base_fcf_source})
          </span>
        </div>

        <div className="mt-4 grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          {/* Slider: Growth Rate */}
          <div className="space-y-2">
            <div className="flex justify-between text-xs font-semibold text-slate-700 dark:text-neutral-300">
              <span>FCF-Wachstum (g)</span>
              <span className="font-mono font-bold text-emerald-600 dark:text-emerald-400">
                {(growthRate * 100).toFixed(1)}% p.a.
              </span>
            </div>
            <input
              type="range"
              min="-10"
              max="35"
              step="0.5"
              value={growthRate * 100}
              onChange={(e) => {
                setGrowthRate(Number(e.target.value) / 100);
                setActiveScenario('custom');
              }}
              className="w-full accent-emerald-500"
            />
            <div className="flex justify-between text-[10px] text-slate-400">
              <span>-10%</span>
              <span>10%</span>
              <span>+35%</span>
            </div>
          </div>

          {/* Slider: Discount Rate / WACC */}
          <div className="space-y-2">
            <div className="flex justify-between text-xs font-semibold text-slate-700 dark:text-neutral-300">
              <span>Abzinsung (WACC)</span>
              <span className="font-mono font-bold text-indigo-600 dark:text-indigo-400">
                {(discountRate * 100).toFixed(1)}%
              </span>
            </div>
            <input
              type="range"
              min="5"
              max="16"
              step="0.2"
              value={discountRate * 100}
              onChange={(e) => {
                setDiscountRate(Number(e.target.value) / 100);
                setActiveScenario('custom');
              }}
              className="w-full accent-indigo-500"
            />
            <div className="flex justify-between text-[10px] text-slate-400">
              <span>5.0%</span>
              <span>10.0%</span>
              <span>16.0%</span>
            </div>
          </div>

          {/* Slider: Terminal Growth */}
          <div className="space-y-2">
            <div className="flex justify-between text-xs font-semibold text-slate-700 dark:text-neutral-300">
              <span>Ewige Rente (Terminal)</span>
              <span className="font-mono font-bold text-slate-800 dark:text-neutral-200">
                {(terminalGrowth * 100).toFixed(1)}%
              </span>
            </div>
            <input
              type="range"
              min="0.5"
              max="4.0"
              step="0.1"
              value={terminalGrowth * 100}
              onChange={(e) => {
                setTerminalGrowth(Number(e.target.value) / 100);
                setActiveScenario('custom');
              }}
              className="w-full accent-slate-600 dark:accent-neutral-400"
            />
            <div className="flex justify-between text-[10px] text-slate-400">
              <span>0.5% (Konservativ)</span>
              <span>2.5% (BIP)</span>
              <span>4.0%</span>
            </div>
          </div>

          {/* Slider: Margin of Safety */}
          <div className="space-y-2">
            <div className="flex justify-between text-xs font-semibold text-slate-700 dark:text-neutral-300">
              <span>Sicherheitsmarge</span>
              <span className="font-mono font-bold text-amber-600 dark:text-amber-400">
                {(marginOfSafety * 100).toFixed(0)}%
              </span>
            </div>
            <input
              type="range"
              min="5"
              max="50"
              step="5"
              value={marginOfSafety * 100}
              onChange={(e) => {
                setMarginOfSafety(Number(e.target.value) / 100);
                setActiveScenario('custom');
              }}
              className="w-full accent-amber-500"
            />
            <div className="flex justify-between text-[10px] text-slate-400">
              <span>5%</span>
              <span>25%</span>
              <span>50% (Buffett)</span>
            </div>
          </div>
        </div>
      </div>

      {/* 2D Sensitivity Matrix */}
      <div className="mt-6 rounded-2xl border border-slate-200/80 bg-slate-50/50 p-5 dark:border-neutral-800 dark:bg-neutral-800/20">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h4 className="text-sm font-bold text-slate-900 dark:text-white">
              2D-Sensitivitätsmatrix (Fair Value je Aktie)
            </h4>
            <p className="text-xs text-slate-500 dark:text-neutral-400">
              Matrix aus Abzinsungssatz (WACC, Zeilen) und jährlichem FCF-Wachstum (Spalten). Klicke eine Zelle, um diese Parameter zu laden.
            </p>
          </div>
          <div className="flex items-center gap-3 text-[11px]">
            <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-medium">
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-500"></span> Unterbewertet
            </span>
            <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400 font-medium">
              <span className="h-2.5 w-2.5 rounded-full bg-amber-500"></span> Fair
            </span>
            <span className="flex items-center gap-1 text-rose-600 dark:text-rose-400 font-medium">
              <span className="h-2.5 w-2.5 rounded-full bg-rose-500"></span> Überbewertet
            </span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-center text-xs">
            <thead>
              <tr className="border-b border-slate-200 dark:border-neutral-700">
                <th className="p-2 text-left text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  WACC / Wachst.
                </th>
                {calculatedModel.sensitivityMatrix.growthAxis.map((gVal, idx) => (
                  <th
                    key={idx}
                    className={`p-2 font-mono font-bold ${
                      Math.abs(gVal - growthRate) < 0.005 ? 'text-emerald-500' : 'text-slate-600 dark:text-neutral-300'
                    }`}
                  >
                    {(gVal * 100).toFixed(1)}%
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {calculatedModel.sensitivityMatrix.grid.map((row, rIdx) => {
                const wVal = calculatedModel.sensitivityMatrix.waccAxis[rIdx];
                const isCurrentWacc = Math.abs(wVal - discountRate) < 0.005;
                return (
                  <tr key={rIdx} className="border-b border-slate-100 dark:border-neutral-800/60">
                    <td className={`p-2 text-left font-mono font-bold ${isCurrentWacc ? 'text-indigo-500' : 'text-slate-600 dark:text-neutral-400'}`}>
                      {(wVal * 100).toFixed(1)}%
                    </td>
                    {row.map((cell, cIdx) => {
                      const isCurrentGrowth = Math.abs(cell.growth - growthRate) < 0.005;
                      const isCenter = isCurrentWacc && isCurrentGrowth;

                      let cellBg = 'bg-rose-500/10 text-rose-700 dark:text-rose-300';
                      if (cell.verdict === 'undervalued') {
                        cellBg = 'bg-emerald-500/15 text-emerald-800 dark:text-emerald-300 font-bold';
                      } else if (cell.verdict === 'fair') {
                        cellBg = 'bg-amber-500/10 text-amber-800 dark:text-amber-300';
                      }

                      return (
                        <td key={cIdx} className="p-1">
                          <button
                            onClick={() => {
                              setDiscountRate(cell.wacc);
                              setGrowthRate(cell.growth);
                              setActiveScenario('custom');
                            }}
                            className={`w-full rounded-lg p-2 font-mono transition-all hover:scale-105 ${cellBg} ${
                              isCenter ? 'ring-2 ring-emerald-500 ring-offset-1 dark:ring-offset-neutral-900 shadow-sm' : ''
                            }`}
                          >
                            <div className="text-xs font-extrabold">{cell.fair_value.toFixed(0)}</div>
                            <div className="text-[9px] opacity-80">
                              {cell.upside_pct > 0 ? '+' : ''}{cell.upside_pct}%
                            </div>
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Detailed Cashflow Projection Waterfall Accordion */}
      <div className="mt-4">
        <button
          onClick={() => setShowProjections(!showProjections)}
          className="flex w-full items-center justify-between rounded-xl bg-slate-100/80 px-4 py-2.5 text-xs font-bold text-slate-700 transition-colors hover:bg-slate-200/80 dark:bg-neutral-800/80 dark:text-neutral-300 dark:hover:bg-neutral-800"
        >
          <span className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-slate-500" />
            <span>Cashflow-Projektionen & Unternehmenswert-Herleitung ansehen</span>
          </span>
          {showProjections ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>

        {showProjections && (
          <div className="mt-3 space-y-4 rounded-2xl border border-slate-200/80 bg-white/70 p-4 dark:border-neutral-800 dark:bg-neutral-900/40">
            {/* Year-by-Year Table */}
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-400 dark:border-neutral-700">
                    <th className="pb-2">Projektionsjahr</th>
                    <th className="pb-2">Geschätzter FCF</th>
                    <th className="pb-2">Abzinsungsfaktor</th>
                    <th className="pb-2 text-right">Barwert (PV)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-neutral-800">
                  {calculatedModel.projections.map((p) => (
                    <tr key={p.year}>
                      <td className="py-2 font-semibold text-slate-700 dark:text-neutral-200">
                        Jahr {p.year} (t + {p.year})
                      </td>
                      <td className="py-2 font-mono text-slate-900 dark:text-white">
                        {formatLargeMoney(p.fcf, effectiveCurrency)}
                      </td>
                      <td className="py-2 font-mono text-slate-500">
                        {p.discount_factor.toFixed(4)}
                      </td>
                      <td className="py-2 text-right font-mono font-bold text-emerald-600 dark:text-emerald-400">
                        {formatLargeMoney(p.pv, effectiveCurrency)}
                      </td>
                    </tr>
                  ))}
                  <tr className="bg-slate-50/50 font-bold dark:bg-neutral-800/30">
                    <td className="py-2">Terminal Value (Ewige Rente)</td>
                    <td className="py-2 font-mono">
                      {formatLargeMoney(calculatedModel.terminalValue, effectiveCurrency)}
                    </td>
                    <td className="py-2 font-mono text-slate-500">
                      {Number((1.0 / Math.pow(1.0 + discountRate, projectionYears)).toFixed(4))}
                    </td>
                    <td className="py-2 text-right font-mono text-emerald-600 dark:text-emerald-400">
                      {formatLargeMoney(calculatedModel.pvTerminalValue, effectiveCurrency)}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Waterfall Value Reconciliation */}
            <div className="grid gap-2 border-t border-slate-200 pt-3 text-xs sm:grid-cols-2 md:grid-cols-4 dark:border-neutral-700">
              <div className="rounded-lg bg-slate-50 p-2.5 dark:bg-neutral-800/50">
                <div className="text-slate-500 dark:text-neutral-400">Enterprise Value (EV)</div>
                <div className="font-mono font-bold text-slate-900 dark:text-white">
                  {formatLargeMoney(calculatedModel.enterpriseValue, effectiveCurrency)}
                </div>
              </div>
              <div className="rounded-lg bg-slate-50 p-2.5 dark:bg-neutral-800/50">
                <div className="text-slate-500 dark:text-neutral-400">Netto-Finanzschulden</div>
                <div className="font-mono font-bold text-slate-900 dark:text-white">
                  {formatLargeMoney(rawInputs.net_debt, effectiveCurrency)}
                </div>
              </div>
              <div className="rounded-lg bg-slate-50 p-2.5 dark:bg-neutral-800/50">
                <div className="text-slate-500 dark:text-neutral-400">Equity Value (Eigenkapital)</div>
                <div className="font-mono font-bold text-slate-900 dark:text-white">
                  {formatLargeMoney(calculatedModel.equityValue, effectiveCurrency)}
                </div>
              </div>
              <div className="rounded-lg bg-emerald-500/10 p-2.5 text-emerald-800 dark:text-emerald-300">
                <div>Aktienanzahl (Shares)</div>
                <div className="font-mono font-bold">
                  {(rawInputs.shares_outstanding / 1e6).toFixed(1)} Mio. Stück
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
