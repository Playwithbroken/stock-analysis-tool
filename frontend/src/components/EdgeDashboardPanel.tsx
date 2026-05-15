import { Activity, AlertTriangle, ArrowRight, Ban, BarChart3, CheckCircle2, Eye, ShieldAlert, Target, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";
import type { Portfolio } from "../hooks/usePortfolios";

type EdgeTone = "action" | "watch" | "avoid";

interface EdgeDashboardPanelProps {
  signalScore: any;
  learning: any;
  tradingEdge: any;
  globalBrief: any;
  portfolios: Portfolio[];
  quotes: Record<string, any>;
  loading?: boolean;
  onAnalyzeTicker: (ticker: string) => void;
  onOpenPortfolio: () => void;
  onOpenMarkets: () => void;
}

interface DecisionRow {
  key: string;
  ticker: string;
  label: string;
  headline: string;
  score: number | null;
  source: string;
  nextAction: string;
  tone: EdgeTone;
}

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value.replace("%", "").replace(",", "."));
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function formatNumber(value: number | null | undefined, digits = 0) {
  if (value == null || !Number.isFinite(value)) return "n/a";
  return value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function normalizeTicker(value: unknown) {
  return String(value || "")
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9.-]/g, "");
}

function classify(score: number | null, text: string): EdgeTone {
  const lower = text.toLowerCase();
  if (lower.includes("avoid") || lower.includes("risk") || lower.includes("wait")) return "avoid";
  if (score != null && score >= 78) return "action";
  if (score != null && score < 50) return "avoid";
  return "watch";
}

function toneClasses(tone: EdgeTone) {
  if (tone === "action") return "border-emerald-500/20 bg-emerald-500/10 text-emerald-800";
  if (tone === "avoid") return "border-red-500/20 bg-red-500/10 text-red-800";
  return "border-amber-500/20 bg-amber-500/10 text-amber-800";
}

function toneLabel(tone: EdgeTone) {
  if (tone === "action") return "Action";
  if (tone === "avoid") return "Avoid";
  return "Watch";
}

function buildScoreRows(signalScore: any): DecisionRow[] {
  const ideas = Array.isArray(signalScore?.top_ideas) ? signalScore.top_ideas : [];
  return ideas.slice(0, 8).map((item: any, index: number) => {
    const ticker = normalizeTicker(item?.ticker || item?.symbol || item?.label);
    const score = toNumber(item?.conviction_score ?? item?.total_score ?? item?.score);
    const label = String(item?.label || item?.headline || ticker || "Signal").trim();
    const headline = String(item?.headline || item?.detail || item?.next_action || "High-conviction signal").trim();
    const nextAction = String(item?.next_action || "Analyse oeffnen und Trigger pruefen").trim();
    const source = String(item?.source_label || item?.bucket || "Scoreboard").trim();
    const text = `${label} ${headline} ${nextAction}`;
    return {
      key: `score-${ticker || index}-${index}`,
      ticker,
      label,
      headline,
      score,
      source,
      nextAction,
      tone: classify(score, text),
    };
  });
}

function buildBriefRows(globalBrief: any): DecisionRow[] {
  const setups = [
    ...(Array.isArray(globalBrief?.trade_setups) ? globalBrief.trade_setups : []),
    ...(Array.isArray(globalBrief?.prediction_signals) ? globalBrief.prediction_signals : []),
  ];
  return setups.slice(0, 8).map((item: any, index: number) => {
    const ticker = normalizeTicker(item?.ticker || item?.symbol || item?.asset || item?.label);
    const score = toNumber(item?.confidence ?? item?.score ?? item?.total_score ?? item?.conviction);
    const label = String(item?.label || item?.setup || item?.title || ticker || "Brief setup").trim();
    const headline = String(item?.thesis || item?.summary || item?.reason || item?.trigger || "Morning Brief setup").trim();
    const nextAction = String(item?.next_action || item?.trigger || "Trigger und Risiko pruefen").trim();
    const source = String(item?.source || item?.category || "Morning Brief").trim();
    const text = `${label} ${headline} ${nextAction}`;
    return {
      key: `brief-${ticker || index}-${index}`,
      ticker,
      label,
      headline,
      score,
      source,
      nextAction,
      tone: classify(score, text),
    };
  });
}

function dedupeRows(rows: DecisionRow[]) {
  const seen = new Set<string>();
  return rows.filter((row) => {
    const key = `${row.ticker || row.label}:${row.source}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function portfolioSnapshot(portfolios: Portfolio[], quotes: Record<string, any>) {
  const holdings = portfolios.flatMap((portfolio) =>
    (portfolio.holdings || []).map((holding) => {
      const ticker = normalizeTicker(holding.ticker);
      const shares = toNumber(holding.shares) || 0;
      const quotePrice = toNumber(quotes?.[ticker]?.price);
      const buyPrice = toNumber(holding.buyPrice);
      const price = quotePrice ?? buyPrice ?? 0;
      const value = shares * price;
      return {
        ticker,
        value,
        shares,
        hasQuote: quotePrice != null,
        portfolio: portfolio.name,
      };
    }),
  );
  const totalValue = holdings.reduce((sum, item) => sum + item.value, 0);
  const sorted = [...holdings].sort((a, b) => b.value - a.value);
  const top = sorted[0];
  const concentration = totalValue > 0 && top ? (top.value / totalValue) * 100 : null;
  const missingQuotes = holdings.filter((item) => !item.hasQuote).length;
  const uniqueTickers = new Set(holdings.map((item) => item.ticker).filter(Boolean)).size;
  return { holdings, totalValue, top, concentration, missingQuotes, uniqueTickers };
}

export default function EdgeDashboardPanel({
  signalScore,
  learning,
  tradingEdge,
  globalBrief,
  portfolios,
  quotes,
  loading,
  onAnalyzeTicker,
  onOpenPortfolio,
  onOpenMarkets,
}: EdgeDashboardPanelProps) {
  const rows = dedupeRows([...buildScoreRows(signalScore), ...buildBriefRows(globalBrief)])
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
    .slice(0, 8);
  const actionRows = rows.filter((row) => row.tone === "action").slice(0, 3);
  const watchRows = rows.filter((row) => row.tone === "watch").slice(0, 3);
  const avoidRows = rows.filter((row) => row.tone === "avoid").slice(0, 3);
  const snapshot = portfolioSnapshot(portfolios, quotes);
  const hitRate = toNumber(learning?.summary?.hit_rate ?? learning?.summary?.accuracy);
  const evaluated = toNumber(learning?.summary?.evaluated ?? learning?.summary?.evaluated_forecasts);
  const topNewsSummary = learning?.top_news?.summary || {};
  const topNewsHitRate = toNumber(topNewsSummary.hit_rate);
  const topNewsPending = toNumber(topNewsSummary.pending);
  const topNewsEvaluated = toNumber(topNewsSummary.evaluated);
  const topNewsLesson = String(
    learning?.top_news?.lesson ||
      "Top-News-Lernen startet, sobald tickerbezogene Telegram-News als Forecasts gespeichert werden.",
  );
  const weakSetups = Array.isArray(learning?.weak_setup_types) ? learning.weak_setup_types : [];
  const weakSources = Array.isArray(learning?.weak_sources) ? learning.weak_sources : [];
  const lessons = Array.isArray(learning?.lessons) ? learning.lessons : [];
  const vix = tradingEdge?.regime?.vix || tradingEdge?.vix || null;
  const vixLevel = toNumber(vix?.value ?? vix?.level);
  const regime = String(globalBrief?.macro_regime || tradingEdge?.regime?.label || vix?.regime || "Neutral").trim();
  const eventCount = Array.isArray(globalBrief?.event_pings) ? globalBrief.event_pings.length : 0;
  const briefQuality = globalBrief?.quality?.fallback ? "Fallback" : globalBrief ? "Live" : "Loading";
  const portfolioRisk =
    snapshot.holdings.length === 0
      ? "No portfolio"
      : snapshot.concentration != null && snapshot.concentration > 35
        ? "Concentration"
        : snapshot.uniqueTickers < 5
          ? "Diversification"
          : snapshot.missingQuotes > 0
            ? "Quote gaps"
            : "Balanced";
  const blockers = [
    snapshot.concentration != null && snapshot.concentration > 35
      ? `Top position ${snapshot.top?.ticker || ""} is ${formatNumber(snapshot.concentration, 0)}% of tracked value.`
      : null,
    snapshot.uniqueTickers > 0 && snapshot.uniqueTickers < 5
      ? `Only ${snapshot.uniqueTickers} unique tickers are tracked.`
      : null,
    snapshot.missingQuotes > 0 ? `${snapshot.missingQuotes} holdings use buy price fallback instead of live quotes.` : null,
    weakSetups[0]?.setup_type ? `Weak setup type: ${weakSetups[0].setup_type}.` : null,
    weakSources[0]?.source ? `Weak source: ${weakSources[0].source}.` : null,
  ].filter(Boolean) as string[];

  const kpis = [
    {
      label: "Action candidates",
      value: String(actionRows.length),
      detail: rows.length ? `${rows.length} ranked signals` : loading ? "Signals loading" : "No ranked signal yet",
      icon: Target,
    },
    {
      label: "Portfolio risk",
      value: portfolioRisk,
      detail:
        snapshot.concentration != null
          ? `${formatNumber(snapshot.concentration, 0)}% top position`
          : `${snapshot.holdings.length} holdings tracked`,
      icon: ShieldAlert,
    },
    {
      label: "Learning hit rate",
      value: hitRate != null ? `${formatNumber(hitRate, 0)}%` : "n/a",
      detail: evaluated != null ? `${formatNumber(evaluated, 0)} forecasts evaluated` : "Need more closed forecasts",
      icon: BarChart3,
    },
    {
      label: "Market regime",
      value: regime,
      detail: vixLevel != null ? `VIX ${formatNumber(vixLevel, 1)} / ${eventCount} events` : `${briefQuality} brief / ${eventCount} events`,
      icon: Activity,
    },
  ];

  const renderRow = (row: DecisionRow) => (
    <div key={row.key} className="rounded-[1.1rem] border border-black/8 bg-white/78 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-full border px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.13em] ${toneClasses(row.tone)}`}>
              {toneLabel(row.tone)}
            </span>
            {row.ticker ? (
              <button
                type="button"
                onClick={() => onAnalyzeTicker(row.ticker)}
                className="text-xs font-black uppercase tracking-[0.12em] text-slate-950 hover:text-[var(--accent)]"
              >
                {row.ticker}
              </button>
            ) : null}
            <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">{row.source}</span>
          </div>
          <div className="mt-2 line-clamp-1 text-sm font-bold text-slate-900">{row.label}</div>
          <div className="mt-1 line-clamp-2 text-xs leading-5 text-slate-600">{row.headline}</div>
        </div>
        <div className="text-right">
          <div className="text-xl font-black text-slate-950">{row.score != null ? formatNumber(row.score, 0) : "n/a"}</div>
          <div className="text-[9px] font-extrabold uppercase tracking-[0.12em] text-slate-400">score</div>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-black/6 pt-3">
        <div className="line-clamp-1 text-xs font-semibold text-slate-600">{row.nextAction}</div>
        {row.ticker ? (
          <button
            type="button"
            onClick={() => onAnalyzeTicker(row.ticker)}
            className="inline-flex items-center gap-1 rounded-full border border-black/10 bg-white px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.12em] text-slate-800"
          >
            Analyze <ArrowRight size={12} />
          </button>
        ) : null}
      </div>
    </div>
  );

  return (
    <section className="surface-panel rounded-[2rem] p-5 sm:p-7">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
        <div className="max-w-3xl">
          <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
            Edge Dashboard
          </div>
          <h2 className="mt-2 text-2xl text-slate-950 sm:text-3xl">
            Was jetzt handeln, beobachten oder meiden?
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Scoreboard, Morning Brief, Portfolio, Lernkurve und Marktregime werden hier zu einer
            priorisierten Arbeitsliste verdichtet.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onOpenMarkets}
            className="inline-flex items-center gap-2 rounded-[0.95rem] border border-black/10 bg-white px-3 py-2 text-xs font-extrabold uppercase tracking-[0.14em] text-slate-800"
          >
            <TrendingUp size={14} /> Markets
          </button>
          <button
            type="button"
            onClick={onOpenPortfolio}
            className="inline-flex items-center gap-2 rounded-[0.95rem] bg-[#101114] px-3 py-2 text-xs font-extrabold uppercase tracking-[0.14em] text-white"
          >
            <ShieldAlert size={14} /> Portfolio
          </button>
        </div>
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {kpis.map((item) => {
          const Icon = item.icon;
          return (
            <div key={item.label} className="rounded-[1.25rem] border border-black/8 bg-white/72 p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">{item.label}</div>
                <Icon size={16} className="text-slate-500" />
              </div>
              <div className="mt-3 truncate text-2xl font-black text-slate-950">{item.value}</div>
              <div className="mt-1 truncate text-xs font-semibold text-slate-500">{item.detail}</div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 rounded-[1.25rem] border border-[var(--accent)]/18 bg-[linear-gradient(135deg,rgba(20,184,166,0.11),rgba(255,255,255,0.76))] p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-[var(--accent)]">
              Top-News Forecast Learning
            </div>
            <div className="mt-1 line-clamp-2 text-sm font-semibold leading-6 text-slate-700">
              {topNewsLesson}
            </div>
          </div>
          <div className="grid shrink-0 grid-cols-3 gap-2 text-center">
            <div className="rounded-[0.95rem] border border-black/8 bg-white/75 px-3 py-2">
              <div className="text-[9px] font-extrabold uppercase tracking-[0.12em] text-slate-500">Hit</div>
              <div className="mt-1 text-base font-black text-slate-950">
                {topNewsHitRate != null ? `${formatNumber(topNewsHitRate, 0)}%` : "n/a"}
              </div>
            </div>
            <div className="rounded-[0.95rem] border border-black/8 bg-white/75 px-3 py-2">
              <div className="text-[9px] font-extrabold uppercase tracking-[0.12em] text-slate-500">Check</div>
              <div className="mt-1 text-base font-black text-slate-950">{formatNumber(topNewsEvaluated, 0)}</div>
            </div>
            <div className="rounded-[0.95rem] border border-black/8 bg-white/75 px-3 py-2">
              <div className="text-[9px] font-extrabold uppercase tracking-[0.12em] text-slate-500">Open</div>
              <div className="mt-1 text-base font-black text-slate-950">{formatNumber(topNewsPending, 0)}</div>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-5 grid gap-4 xl:grid-cols-3">
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-[0.16em] text-emerald-700">
            <CheckCircle2 size={15} /> Action
          </div>
          {actionRows.length ? (
            actionRows.map(renderRow)
          ) : (
            <EmptyDecision
              icon={<Target size={18} />}
              title="Kein sofortiger A-Setup"
              body={loading ? "Signalquellen laden noch." : "Kein Score ist aktuell stark genug fuer eine harte Action."}
            />
          )}
        </div>

        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-[0.16em] text-amber-700">
            <Eye size={15} /> Watch
          </div>
          {watchRows.length ? (
            watchRows.map(renderRow)
          ) : (
            <EmptyDecision
              icon={<Eye size={18} />}
              title="Watchlist leer"
              body="Sobald Morning Brief oder Scoreboard Setups liefern, erscheinen sie hier."
            />
          )}
        </div>

        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-[0.16em] text-red-700">
            <Ban size={15} /> Avoid / Risk
          </div>
          {avoidRows.length ? avoidRows.map(renderRow) : null}
          {blockers.length ? (
            <div className="rounded-[1.1rem] border border-red-500/15 bg-red-500/8 p-3">
              <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.14em] text-red-800">
                <AlertTriangle size={15} /> Blockers
              </div>
              <div className="mt-3 space-y-2">
                {blockers.slice(0, 4).map((item) => (
                  <div key={item} className="text-xs font-semibold leading-5 text-red-900/80">
                    {item}
                  </div>
                ))}
              </div>
            </div>
          ) : !avoidRows.length ? (
            <EmptyDecision
              icon={<Ban size={18} />}
              title="Keine harte Bremse"
              body="Keine klare Avoid-Liste aus Scoreboard, Portfolio oder Lernkurve."
            />
          ) : null}
          {lessons[0] ? (
            <div className="rounded-[1.1rem] border border-black/8 bg-white/72 p-3">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                Lernsignal
              </div>
              <div className="mt-2 line-clamp-3 text-xs font-semibold leading-5 text-slate-700">
                {String(lessons[0]?.message || lessons[0]?.lesson || lessons[0]?.text || lessons[0])}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function EmptyDecision({ icon, title, body }: { icon: ReactNode; title: string; body: string }) {
  return (
    <div className="rounded-[1.1rem] border border-dashed border-black/12 bg-white/52 p-4">
      <div className="flex items-center gap-2 text-sm font-bold text-slate-800">
        <span className="text-slate-500">{icon}</span>
        {title}
      </div>
      <div className="mt-2 text-xs leading-5 text-slate-500">{body}</div>
    </div>
  );
}
