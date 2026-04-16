import { type FC } from "react";

interface SqueezeItem {
  ticker: string;
  score: number;
  short_pct_float: number;
  days_to_cover: number;
  rsi: number;
}
interface InsiderItem {
  ticker: string;
  insider: string;
  title: string;
  value: string;
  date: string;
}
interface OptionsItem {
  ticker: string;
  expiry: string;
  pc_ratio: number;
  calls_vol: number;
  puts_vol: number;
  sentiment: "bullish" | "bearish" | "neutral";
}
interface AnalystAction {
  date: string;
  firm: string;
  to: string;
  from: string;
  action: string;
}
interface AnalystItem {
  ticker: string;
  actions: AnalystAction[];
}
interface RegimePayload {
  vix?: { value: number; change: number; regime: string };
  crypto_fng?: { value: number; label: string };
}
interface SectorItem {
  ticker: string;
  name: string;
  change_1d: number;
  change_5d: number;
}
interface PreMover {
  ticker: string;
  pre: number;
  prev_close: number;
  change_pct: number;
}
interface YieldCurve {
  us10y?: number;
  us5y?: number;
  us30y?: number;
  spread_10y_5y?: number;
  inverted?: boolean;
}
interface TradingEdge {
  squeeze?: SqueezeItem[];
  insider?: InsiderItem[];
  options?: OptionsItem[];
  analyst?: AnalystItem[];
  regime?: RegimePayload;
  premarket?: PreMover[];
  sectors?: SectorItem[];
  yield_curve?: YieldCurve;
}

interface Props {
  edge: TradingEdge | null | undefined;
  loading?: boolean;
  onSelectTicker?: (ticker: string) => void;
}

const tickerBtn = (cb?: (t: string) => void, t?: string) => ({
  className: "font-mono font-bold text-teal-700 hover:underline cursor-pointer",
  onClick: () => t && cb?.(t),
});

const arrow = (n: number) => (n > 0 ? "▲" : n < 0 ? "▼" : "▶");
const colorPct = (n: number) =>
  n > 0 ? "text-emerald-600" : n < 0 ? "text-rose-600" : "text-slate-500";

export const TradingEdgePanel: FC<Props> = ({ edge, loading, onSelectTicker }) => {
  if (loading) {
    return (
      <section
        aria-label="Trading Edge loading"
        aria-busy="true"
        className="surface-panel rounded-[2rem] p-6 space-y-4"
      >
        <div>
          <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
            Trading Edge
          </div>
          <h2 className="mt-1 text-xl font-bold text-slate-900">
            Loading live signals…
          </h2>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-20 animate-pulse rounded-2xl bg-slate-100"
            />
          ))}
        </div>
        <div className="space-y-2">
          {[0, 1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-9 animate-pulse rounded-xl bg-slate-100"
            />
          ))}
        </div>
      </section>
    );
  }
  if (!edge || Object.keys(edge).length === 0) return null;

  const {
    squeeze = [],
    insider = [],
    options = [],
    analyst = [],
    regime = {},
    premarket = [],
    sectors = [],
    yield_curve = {},
  } = edge;

  const empty =
    !squeeze.length &&
    !insider.length &&
    !options.length &&
    !analyst.length &&
    !premarket.length &&
    !sectors.length &&
    !regime.vix &&
    !yield_curve.us10y;

  if (empty) return null;

  return (
    <section
      aria-label="Trading Edge"
      className="surface-panel rounded-[2rem] p-6 space-y-6"
    >
      <header className="flex items-center justify-between">
        <div>
          <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
            Trading Edge
          </div>
          <h2 className="mt-1 text-xl font-bold text-slate-900">
            Live signals — squeeze, insider, options, regime
          </h2>
        </div>
      </header>

      {/* Regime bar */}
      <div className="grid gap-3 sm:grid-cols-3">
        {regime.vix && (
          <div className="rounded-2xl bg-slate-50 p-4">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">
              VIX
            </div>
            <div className="flex items-baseline gap-2">
              <div className="text-2xl font-bold text-slate-900">
                {regime.vix.value}
              </div>
              <div className={`text-sm font-semibold ${colorPct(regime.vix.change)}`}>
                {arrow(regime.vix.change)} {regime.vix.change.toFixed(2)}
              </div>
            </div>
            <div className="text-xs text-slate-600 mt-1 capitalize">
              regime: {regime.vix.regime}
            </div>
          </div>
        )}
        {regime.crypto_fng && (
          <div className="rounded-2xl bg-slate-50 p-4">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">
              Crypto Fear &amp; Greed
            </div>
            <div className="text-2xl font-bold text-slate-900">
              {regime.crypto_fng.value}
            </div>
            <div className="text-xs text-slate-600 mt-1">
              {regime.crypto_fng.label}
            </div>
          </div>
        )}
        {yield_curve.us10y && (
          <div className="rounded-2xl bg-slate-50 p-4">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">
              US Yields
            </div>
            <div className="text-sm font-semibold text-slate-900">
              10Y {yield_curve.us10y}% · 5Y {yield_curve.us5y}% · 30Y {yield_curve.us30y}%
            </div>
            <div
              className={`text-xs mt-1 font-bold ${
                yield_curve.inverted ? "text-rose-600" : "text-emerald-600"
              }`}
            >
              {yield_curve.inverted ? "⚠ INVERTED" : "Normal"} (10-5 spread{" "}
              {yield_curve.spread_10y_5y?.toFixed(2)}pp)
            </div>
          </div>
        )}
      </div>

      {/* Sectors */}
      {sectors.length > 0 && (
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2">
            Sector Rotation (5d)
          </div>
          <div className="flex flex-wrap gap-2">
            {sectors.map((s) => (
              <div
                key={s.ticker}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                  s.change_5d > 0
                    ? "bg-emerald-50 text-emerald-700"
                    : "bg-rose-50 text-rose-700"
                }`}
                title={`${s.name} 1d ${s.change_1d}%`}
              >
                <span className="font-mono">{s.ticker}</span> {s.change_5d > 0 ? "+" : ""}
                {s.change_5d}%
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Pre-market movers */}
      {premarket.length > 0 && (
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2">
            Pre-Market Movers
          </div>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {premarket.map((m) => (
              <div
                key={m.ticker}
                className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2"
              >
                <span {...tickerBtn(onSelectTicker, m.ticker)}>{m.ticker}</span>
                <div className={`text-sm font-semibold ${colorPct(m.change_pct)}`}>
                  {arrow(m.change_pct)} {m.change_pct > 0 ? "+" : ""}
                  {m.change_pct}% @ ${m.pre}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Squeeze watch */}
      {squeeze.length > 0 && (
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2">
            Short-Squeeze Watch
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] uppercase tracking-wider text-slate-500">
                  <th className="text-left py-1">Ticker</th>
                  <th className="text-right">Score</th>
                  <th className="text-right">Short %</th>
                  <th className="text-right">DTC</th>
                  <th className="text-right">RSI</th>
                </tr>
              </thead>
              <tbody>
                {squeeze.map((s) => (
                  <tr key={s.ticker} className="border-t border-slate-100">
                    <td className="py-1.5">
                      <span {...tickerBtn(onSelectTicker, s.ticker)}>{s.ticker}</span>
                    </td>
                    <td className="text-right font-bold text-slate-900">{s.score}</td>
                    <td className="text-right">{s.short_pct_float}%</td>
                    <td className="text-right">{s.days_to_cover}</td>
                    <td className="text-right">{s.rsi}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Unusual options */}
      {options.length > 0 && (
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2">
            Unusual Options
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {options.map((o) => (
              <div
                key={o.ticker}
                className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2"
              >
                <div>
                  <span {...tickerBtn(onSelectTicker, o.ticker)}>{o.ticker}</span>{" "}
                  <span
                    className={`ml-1 text-xs font-bold ${
                      o.sentiment === "bullish"
                        ? "text-emerald-600"
                        : o.sentiment === "bearish"
                        ? "text-rose-600"
                        : "text-slate-500"
                    }`}
                  >
                    {o.sentiment}
                  </span>
                </div>
                <div className="text-xs text-slate-600">
                  P/C {o.pc_ratio} · C {o.calls_vol.toLocaleString()} / P{" "}
                  {o.puts_vol.toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Analyst actions */}
      {analyst.length > 0 && (
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2">
            Analyst Actions
          </div>
          <div className="space-y-2">
            {analyst.flatMap((a) =>
              a.actions.slice(-2).map((act, i) => (
                <div
                  key={`${a.ticker}-${i}`}
                  className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 text-sm"
                >
                  <div>
                    <span {...tickerBtn(onSelectTicker, a.ticker)}>{a.ticker}</span>{" "}
                    <span className="text-slate-600">{act.firm}</span>
                  </div>
                  <div className="text-xs">
                    <span className="text-slate-500">{act.from || "—"}</span>
                    {" → "}
                    <span className="font-bold text-slate-900">{act.to || act.action}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Insider buys */}
      {insider.length > 0 && (
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2">
            Insider Cluster Buys (7d)
          </div>
          <div className="space-y-1.5">
            {insider.map((i, idx) => (
              <div
                key={`${i.ticker}-${idx}`}
                className="flex items-center justify-between text-sm"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span {...tickerBtn(onSelectTicker, i.ticker)}>{i.ticker}</span>
                  <span className="text-xs text-slate-500 truncate">{i.title}</span>
                </div>
                <div className="text-xs font-semibold text-emerald-700 whitespace-nowrap">
                  {i.value}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
};

export default TradingEdgePanel;
