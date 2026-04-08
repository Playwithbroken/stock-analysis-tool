import React from "react";

interface TradingIntelligencePanelProps {
  data: any;
  onAnalyze: (ticker: string) => void;
}

export default function TradingIntelligencePanel({ data, onAnalyze }: TradingIntelligencePanelProps) {
  if (!data) return null;

  const indicators = data.indicators || [];
  const rules = data.rules || {};

  return (
    <section className="space-y-6">
      <div className="surface-panel rounded-[2.5rem] p-6 sm:p-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Trading Intelligence
            </div>
            <h2 className="mt-2 text-3xl text-slate-900">Core indicators and execution rules</h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
              RSI, ATR, EMA structure, VWAP, gap context, premarket levels and breakout state for the names that currently matter most.
            </p>
          </div>
        </div>

        <div className="mt-6 grid gap-4 xl:grid-cols-2">
          {indicators.map((item: any) => (
            <div key={item.ticker} className="rounded-[1.5rem] border border-black/8 bg-white/75 p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-lg font-black text-slate-900">{item.ticker}</div>
                  <div className="mt-1 text-xs text-slate-500">
                    {item.signal === "long" ? "Long bias" : item.signal === "short" ? "Short bias" : "Neutral"}
                  </div>
                </div>
                <button
                  onClick={() => onAnalyze(item.ticker)}
                  className="rounded-xl border border-black/8 bg-white px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-700"
                >
                  Analyze
                </button>
              </div>

              <div className="mt-4 grid grid-cols-3 gap-2 text-xs">
                <div className="rounded-xl border border-black/8 bg-white p-3 text-slate-600">
                  <div className="font-bold uppercase tracking-[0.14em] text-slate-500">RSI 14</div>
                  <div className="mt-1 text-base font-black text-slate-900">{item.rsi_14}</div>
                </div>
                <div className="rounded-xl border border-black/8 bg-white p-3 text-slate-600">
                  <div className="font-bold uppercase tracking-[0.14em] text-slate-500">ATR 14</div>
                  <div className="mt-1 text-base font-black text-slate-900">{item.atr_14}</div>
                </div>
                <div className="rounded-xl border border-black/8 bg-white p-3 text-slate-600">
                  <div className="font-bold uppercase tracking-[0.14em] text-slate-500">RVOL</div>
                  <div className="mt-1 text-base font-black text-slate-900">{item.volume_ratio}</div>
                </div>
                <div className="rounded-xl border border-black/8 bg-white p-3 text-slate-600">
                  <div className="font-bold uppercase tracking-[0.14em] text-slate-500">VWAP</div>
                  <div className="mt-1 text-base font-black text-slate-900">{item.vwap ?? "N/A"}</div>
                </div>
                <div className="rounded-xl border border-black/8 bg-white p-3 text-slate-600">
                  <div className="font-bold uppercase tracking-[0.14em] text-slate-500">Gap</div>
                  <div className="mt-1 text-base font-black text-slate-900">
                    {item.gap_pct >= 0 ? "+" : ""}{item.gap_pct}%
                  </div>
                </div>
                <div className="rounded-xl border border-black/8 bg-white p-3 text-slate-600">
                  <div className="font-bold uppercase tracking-[0.14em] text-slate-500">EMA 20</div>
                  <div className="mt-1 text-base font-black text-slate-900">{item.ema_20}</div>
                </div>
                <div className="rounded-xl border border-black/8 bg-white p-3 text-slate-600">
                  <div className="font-bold uppercase tracking-[0.14em] text-slate-500">EMA 50</div>
                  <div className="mt-1 text-base font-black text-slate-900">{item.ema_50}</div>
                </div>
                <div className="rounded-xl border border-black/8 bg-white p-3 text-slate-600">
                  <div className="font-bold uppercase tracking-[0.14em] text-slate-500">EMA 200</div>
                  <div className="mt-1 text-base font-black text-slate-900">{item.ema_200}</div>
                </div>
              </div>

              <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-500">
                <span className="rounded-full border border-black/8 bg-white px-3 py-1">1W {item.change_1w >= 0 ? "+" : ""}{item.change_1w}%</span>
                <span className="rounded-full border border-black/8 bg-white px-3 py-1">PM high {item.premarket_high ?? "N/A"}</span>
                <span className="rounded-full border border-black/8 bg-white px-3 py-1">PM low {item.premarket_low ?? "N/A"}</span>
                <span className="rounded-full border border-black/8 bg-white px-3 py-1">{item.breakout_label}</span>
                <span className="rounded-full border border-black/8 bg-white px-3 py-1">S {item.support_level}</span>
                <span className="rounded-full border border-black/8 bg-white px-3 py-1">R {item.resistance_level}</span>
                <span className="rounded-full border border-black/8 bg-white px-3 py-1">52W high {item.from_52w_high}%</span>
                <span className="rounded-full border border-black/8 bg-white px-3 py-1">52W low {item.from_52w_low}%</span>
              </div>

              <div className="mt-4 space-y-2 text-sm text-slate-700">
                {(item.rationale || []).map((reason: string) => (
                  <div key={reason} className="rounded-xl border border-black/8 bg-white p-3">
                    {reason}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        {[
          ["Long Rules", rules.long_rules || []],
          ["Short Rules", rules.short_rules || []],
          ["Risk Rules", rules.risk_rules || []],
        ].map(([title, items]) => (
          <div key={title} className="surface-panel rounded-[2rem] p-5">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">{title}</div>
            <div className="mt-4 space-y-3">
              {(items as string[]).map((rule) => (
                <div key={rule} className="rounded-[1.2rem] border border-black/8 bg-white/75 p-4 text-sm leading-6 text-slate-700">
                  {rule}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
