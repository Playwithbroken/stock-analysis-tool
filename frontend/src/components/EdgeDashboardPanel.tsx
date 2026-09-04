import { Activity, AlertTriangle, ArrowRight, Ban, BarChart3, CheckCircle2, Eye, Globe2, Send, ShieldAlert, Smartphone, Target, TrendingUp, Zap } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { Portfolio } from "../hooks/usePortfolios";
import { localizeLearningMessage, localizeMarketRegime, normalizeGermanDisplayText } from "../lib/displayText";

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

interface SuitabilitySummary {
  decision: string;
  status: string;
  suitability_score: number;
  reasons?: string[];
  risk_flags?: string[];
}

interface MacroPlaybookRow {
  key: string;
  title: string;
  region: string;
  type: string;
  action: string;
  impactScore: number | null;
  assets: string[];
  trigger: string;
  invalidation: string;
  whyNow: string;
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
  if (tone === "action") return "border-emerald-500/20 bg-emerald-50/80 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-500/30";
  if (tone === "avoid") return "border-rose-500/20 bg-rose-50/80 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-500/30";
  return "border-black/8 bg-slate-100/70 text-slate-700 dark:bg-white/10 dark:text-slate-300 dark:border-white/10";
}

function toneLabel(tone: EdgeTone) {
  if (tone === "action") return "Handeln";
  if (tone === "avoid") return "Meiden";
  return "Beobachten";
}

function inferAssetClass(ticker: string) {
  const symbol = normalizeTicker(ticker);
  if (symbol.endsWith("-USD")) return "crypto";
  if (["SPY", "QQQ", "VOO", "VTI", "SCHD", "SOXX", "IBIT", "FBTC", "DIA", "IWM", "URTH", "GLD", "TLT", "XLE", "USO"].includes(symbol)) {
    return "etf";
  }
  return "equity";
}

function advisoryAction(tone: EdgeTone) {
  if (tone === "action") return "setup";
  if (tone === "avoid") return "watch";
  return "watch";
}

function advisoryRiskLevel(row: DecisionRow) {
  if (row.tone === "avoid") return "high";
  if ((row.score ?? 0) >= 88) return "high";
  if (inferAssetClass(row.ticker) === "crypto") return "speculative";
  return "medium";
}

function suitabilityBadge(summary?: SuitabilitySummary | null) {
  if (!summary) {
    return {
      label: "Profil wird geprüft",
      classes: "border-slate-300 bg-white/70 text-slate-500",
    };
  }
  if (summary.decision === "blocked" || summary.decision === "needs_profile") {
    return {
      label: summary.decision === "needs_profile" ? "Profil fehlt" : "Blockiert",
      classes: "border-red-500/20 bg-red-500/10 text-red-800",
    };
  }
  if (summary.decision === "action_requires_review") {
    return {
      label: "Profil: prüfen",
      classes: "border-amber-500/25 bg-amber-500/10 text-amber-800",
    };
  }
  return {
    label: summary.decision === "setup_allowed" ? "Profil: passt" : "Profil: watch",
    classes: "border-emerald-500/20 bg-emerald-500/10 text-emerald-800",
  };
}

function actionTone(value: unknown, impactScore: number | null): EdgeTone {
  const text = String(value || "").toLowerCase();
  if (
    text.includes("avoid") ||
    text.includes("risk") ||
    text.includes("hedge") ||
    text.includes("stand_down") ||
    text.includes("stand down")
  ) {
    return "avoid";
  }
  if (
    text.includes("act") ||
    text.includes("action") ||
    text.includes("constructive") ||
    text.includes("watch_for_long") ||
    (impactScore != null && impactScore >= 88)
  ) {
    return "action";
  }
  return "watch";
}

function titleCase(value: unknown) {
  const raw = String(value || "macro").trim().toLowerCase().replace(/[\s-]+/g, "_");
  const labels: Record<string, string> = {
    macro: "Makro",
    conflict: "Konflikt",
    central_bank: "Zentralbank",
    energy: "Energie",
    election: "Wahlen",
    disaster: "Katastrophe",
    policy: "Politik",
    public_figure: "Wichtige Person",
    ipo: "IPO",
    product_catalyst: "Produkt-Katalysator",
    congress_trade: "Kongress-Transaktion",
  };
  if (labels[raw]) return labels[raw];
  return String(value || "Makro")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function compactText(value: unknown, fallback: string) {
  const text = String(value || "").trim();
  return text || fallback;
}

function buildScoreRows(signalScore: any): DecisionRow[] {
  const ideas = Array.isArray(signalScore?.top_ideas) ? signalScore.top_ideas : [];
  return ideas.slice(0, 8).map((item: any, index: number) => {
    const ticker = normalizeTicker(item?.ticker || item?.symbol || item?.label);
    const score = toNumber(item?.conviction_score ?? item?.total_score ?? item?.score);
    const label = String(item?.label || item?.headline || ticker || "Signal").trim();
    const headline = String(item?.headline || item?.detail || item?.next_action || "High-conviction signal").trim();
    const nextAction = String(item?.next_action || "Analyse öffnen und Trigger prüfen").trim();
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
    const nextAction = String(item?.next_action || item?.trigger || "Trigger und Risiko prüfen").trim();
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

function buildMacroPlaybookRows(globalBrief: any): MacroPlaybookRow[] {
  const events = Array.isArray(globalBrief?.event_layer) ? globalBrief.event_layer : [];
  const rows: MacroPlaybookRow[] = events.map((item: any, index: number) => {
    const intelligence = item?.event_intelligence || {};
    const impactScore = toNumber(intelligence?.impact_score ?? item?.impact_score ?? item?.score);
    const action = compactText(intelligence?.action || item?.action, "watch");
    const assets = Array.isArray(intelligence?.affected_assets)
      ? intelligence.affected_assets
      : Array.isArray(item?.affected_assets)
        ? item.affected_assets
        : [];
    const tone = actionTone(action, impactScore);
    return {
      key: `macro-${item?.event_key || item?.title || index}`,
      title: compactText(item?.title || item?.headline, "Macro event"),
      region: titleCase(item?.country || item?.region || item?.geoPlace || "Global"),
      type: titleCase(item?.event_type || item?.type || "macro"),
      action,
      impactScore,
      assets: assets.map((asset: any) => String(asset || "").trim()).filter(Boolean).slice(0, 4),
      trigger: compactText(
        item?.trigger || intelligence?.trigger,
        "Erst handeln, wenn Preis, Volumen und breite Marktreaktion bestaetigen.",
      ),
      invalidation: compactText(
        item?.invalidation || item?.risk || intelligence?.invalidation,
        "These faellt, wenn der erste Impuls komplett dreht oder die Quelle nicht bestaetigt.",
      ),
      whyNow: compactText(intelligence?.why_now || item?.why_it_matters || item?.summary, "Aktiver Macro-Block im Briefing."),
      tone,
    };
  });
  const toneRank: Record<EdgeTone, number> = { action: 3, avoid: 2, watch: 1 };
  return rows
    .sort(
      (a: MacroPlaybookRow, b: MacroPlaybookRow) =>
        (b.impactScore ?? 0) - (a.impactScore ?? 0) || toneRank[b.tone] - toneRank[a.tone],
    )
    .slice(0, 3);
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
  const rows = useMemo(
    () =>
      dedupeRows([...buildScoreRows(signalScore), ...buildBriefRows(globalBrief)])
        .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
        .slice(0, 8),
    [globalBrief, signalScore],
  );
  const suitabilityKey = rows.map((row) => `${row.key}:${row.ticker}:${row.tone}:${row.score ?? "n/a"}`).join("|");
  const [suitabilityByKey, setSuitabilityByKey] = useState<Record<string, SuitabilitySummary>>({});
  const [suitabilityLoading, setSuitabilityLoading] = useState(false);
  const [sendingTelegramTicker, setSendingTelegramTicker] = useState<string | null>(null);
  const [telegramStatusMessage, setTelegramStatusMessage] = useState<string | null>(null);

  async function handleSendEdgeTelegram(ticker: string) {
    setSendingTelegramTicker(ticker);
    setTelegramStatusMessage(null);
    try {
      const res = await fetch("/api/trading/telegram/send-edge-setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker, force: true }),
      });
      const data = await res.json();
      if (res.ok) {
        setTelegramStatusMessage(`✅ Setup für ${ticker} erfolgreich an dein Smartphone (Telegram) gesendet!`);
      } else {
        setTelegramStatusMessage(`❌ Fehler: ${data.detail || "Senden fehlgeschlagen"}`);
      }
    } catch (err: any) {
      setTelegramStatusMessage(`❌ Netzwerkfehler: ${err.message}`);
    } finally {
      setSendingTelegramTicker(null);
    }
  }

  const [openingPaperTicker, setOpeningPaperTicker] = useState<string | null>(null);

  async function handleOpenEdgePaperTrade(ticker: string) {
    setOpeningPaperTicker(ticker);
    setTelegramStatusMessage(null);
    try {
      const res = await fetch("/api/trading/open-edge-paper-trade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker }),
      });
      const data = await res.json();
      if (res.ok) {
        if (data.status === "already_open") {
          setTelegramStatusMessage(`ℹ️ ${data.message || `Trade für ${ticker} ist bereits im Demokonto aktiv.`}`);
        } else {
          setTelegramStatusMessage(`✅ ${data.message || `Paper Trade für ${ticker} erfolgreich eröffnet!`}`);
          loadActiveTradesAndRS();
        }
      } else {
        setTelegramStatusMessage(`❌ Fehler: ${data.detail || "Eröffnung fehlgeschlagen"}`);
      }
    } catch (err: any) {
      setTelegramStatusMessage(`❌ Netzwerkfehler: ${err.message}`);
    } finally {
      setOpeningPaperTicker(null);
    }
  }

  const [activeTrades, setActiveTrades] = useState<any[]>([]);
  const [rsLeaders, setRsLeaders] = useState<any[]>([]);
  const [isScanning, setIsScanning] = useState(false);
  const [scanResult, setScanResult] = useState<string | null>(null);

  async function loadActiveTradesAndRS() {
    try {
      const [tRes, rsRes] = await Promise.all([
        fetch("/api/trading/active-trades"),
        fetch("/api/trading/relative-strength?benchmark=SPY"),
      ]);
      if (tRes.ok) {
        const data = await tRes.json();
        setActiveTrades(data.trades || []);
      }
      if (rsRes.ok) {
        const data = await rsRes.json();
        setRsLeaders(data.leaders || []);
      }
    } catch {
      // optional
    }
  }

  async function handleTriggerScanner() {
    setIsScanning(true);
    setScanResult(null);
    try {
      const res = await fetch("/api/trading/scanner/run-now", { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        const disp = (data.edge_alerts?.dispatched || []).join(", ");
        setScanResult(disp ? `🎯 Neue Setups gepusht: ${disp}` : "✅ Scan beendet. Watchlist ist aktuell.");
        loadActiveTradesAndRS();
      } else {
        setScanResult("❌ Scan fehlgeschlagen");
      }
    } catch (e: any) {
      setScanResult(`❌ Fehler: ${e.message}`);
    } finally {
      setIsScanning(false);
    }
  }

  async function handleEvaluateLifecycle() {
    try {
      await fetch("/api/trading/lifecycle/evaluate-now", { method: "POST" });
      loadActiveTradesAndRS();
    } catch {}
  }

  useEffect(() => {
    loadActiveTradesAndRS();
  }, []);

  useEffect(() => {
    let cancelled = false;
    const checkRows = rows.filter((row) => row.ticker).slice(0, 8);
    if (!checkRows.length) {
      setSuitabilityByKey({});
      setSuitabilityLoading(false);
      return;
    }
    setSuitabilityLoading(true);
    Promise.all(
      checkRows.map(async (row) => {
        try {
          const response = await fetch("/api/advisory/suitability-check", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              symbol: row.ticker,
              asset_class: inferAssetClass(row.ticker),
              action: advisoryAction(row.tone),
              risk_level: advisoryRiskLevel(row),
              position_pct: 0,
              thesis: `${row.label} / ${row.headline} / ${row.nextAction}`,
            }),
          });
          const payload = await response.json().catch(() => null);
          if (!response.ok || !payload) return null;
          return [row.key, payload] as const;
        } catch {
          return null;
        }
      }),
    ).then((items) => {
      if (cancelled) return;
      const next: Record<string, SuitabilitySummary> = {};
      items.forEach((item) => {
        if (item) next[item[0]] = item[1];
      });
      setSuitabilityByKey(next);
      setSuitabilityLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [suitabilityKey]);

  const macroPlaybookRows = buildMacroPlaybookRows(globalBrief);
  const actionRows = rows.filter((row) => row.tone === "action").slice(0, 3);
  const watchRows = rows.filter((row) => row.tone === "watch").slice(0, 3);
  const avoidRows = rows.filter((row) => row.tone === "avoid").slice(0, 3);
  const suitabilityValues = Object.values(suitabilityByKey);
  const profileActionCount = suitabilityValues.filter((item) => item.decision === "setup_allowed").length;
  const profileReviewCount = suitabilityValues.filter((item) =>
    ["blocked", "needs_profile", "action_requires_review"].includes(item.decision),
  ).length;
  const snapshot = portfolioSnapshot(portfolios, quotes);
  const hitRate = toNumber(learning?.summary?.hit_rate ?? learning?.summary?.accuracy);
  const evaluated = toNumber(learning?.summary?.evaluated ?? learning?.summary?.evaluated_forecasts);
  const decisionRate = toNumber(learning?.summary?.decision_rate);
  const neutralCount = toNumber(learning?.summary?.neutral);
  const topNewsSummary = learning?.top_news?.summary || {};
  const topNewsHitRate = toNumber(topNewsSummary.hit_rate);
  const topNewsPending = toNumber(topNewsSummary.pending);
  const topNewsEvaluated = toNumber(topNewsSummary.evaluated);
  const topNewsLesson = localizeLearningMessage(
    learning?.top_news?.lesson ||
      "Top-News-Lernen startet, sobald tickerbezogene Telegram-News als Forecasts gespeichert werden.",
  );
  const weakSetups = Array.isArray(learning?.weak_setup_types) ? learning.weak_setup_types : [];
  const weakSources = Array.isArray(learning?.weak_sources) ? learning.weak_sources : [];
  const lessons = Array.isArray(learning?.lessons) ? learning.lessons : [];
  const vix = tradingEdge?.regime?.vix || tradingEdge?.vix || null;
  const vixLevel = toNumber(vix?.value ?? vix?.level);
  const regime = localizeMarketRegime(globalBrief?.macro_regime || tradingEdge?.regime?.label || vix?.regime || "Neutral");
  const eventCount = Array.isArray(globalBrief?.event_pings) ? globalBrief.event_pings.length : 0;
  const briefDecisionBlocked = globalBrief?.decision_gate?.allowed === false;
  const briefQuality = briefDecisionBlocked
    ? "Gesperrt"
    : globalBrief?.quality?.fallback ? "Ersatzdaten" : globalBrief ? "Live" : "Lädt";
  const portfolioRisk =
    snapshot.holdings.length === 0
      ? "Kein Portfolio"
      : snapshot.concentration != null && snapshot.concentration > 35
        ? "Konzentration"
        : snapshot.uniqueTickers < 5
          ? "Diversifikation"
          : snapshot.missingQuotes > 0
            ? "Kurslücken"
            : "Ausgewogen";
  const blockers = [
    snapshot.concentration != null && snapshot.concentration > 35
      ? `Die größte Position ${snapshot.top?.ticker || ""} umfasst ${formatNumber(snapshot.concentration, 0)}% des erfassten Werts.`
      : null,
    snapshot.uniqueTickers > 0 && snapshot.uniqueTickers < 5
      ? `Es sind nur ${snapshot.uniqueTickers} unterschiedliche Werte erfasst.`
      : null,
    snapshot.missingQuotes > 0 ? `${snapshot.missingQuotes} Positionen nutzen den Kaufpreis statt eines Live-Kurses.` : null,
    weakSetups[0]?.setup_type ? `Schwacher Setup-Typ: ${weakSetups[0].setup_type}.` : null,
    weakSources[0]?.source ? `Schwache Quelle: ${weakSources[0].source}.` : null,
  ].filter(Boolean) as string[];

  const kpis = [
    {
      label: "Handlungskandidaten",
      value: String(profileActionCount || actionRows.length),
      detail: suitabilityLoading
        ? "Profilprüfung läuft"
        : rows.length
          ? `${profileReviewCount} zu prüfen / ${rows.length} bewertet`
          : loading ? "Signale werden geladen" : "Noch kein bewertetes Signal",
      icon: Target,
    },
    {
      label: "Portfoliorisiko",
      value: portfolioRisk,
      detail:
        snapshot.concentration != null
          ? `${formatNumber(snapshot.concentration, 0)}% größte Position`
          : `${snapshot.holdings.length} Positionen erfasst`,
      icon: ShieldAlert,
    },
    {
      label: "Lernnachweis",
      value: decisionRate != null ? `${formatNumber(decisionRate, 0)}%` : "n/a",
      detail: evaluated != null
        ? `${formatNumber(evaluated, 0)} geprüft / ${formatNumber(neutralCount || 0, 0)} neutral / ${formatNumber(hitRate || 0, 0)}% Treffer bei klaren Fällen`
        : "Mehr abgeschlossene Prognosen nötig",
      icon: BarChart3,
    },
    {
      label: "Marktregime",
      value: regime,
      detail: vixLevel != null ? `VIX ${formatNumber(vixLevel, 1)} / ${eventCount} Ereignisse` : `${briefQuality}-Briefing / ${eventCount} Ereignisse`,
      icon: Activity,
    },
  ];

  const renderRow = (row: DecisionRow) => {
    const advisory = suitabilityByKey[row.key];
    const badge = suitabilityBadge(advisory);
    const reason = advisory?.reasons?.[0];
    return (
    <div key={row.key} className="rounded-[1.1rem] border border-black/6 bg-white/80 p-3.5 shadow-xs dark:border-white/10 dark:bg-white/5">
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
                className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-950 hover:text-[var(--accent)]"
              >
                {row.ticker}
              </button>
            ) : null}
            <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">{row.source}</span>
            <span className={`rounded-full border px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.12em] ${badge.classes}`}>
              {suitabilityLoading && !advisory ? "Profil wird geprüft" : badge.label}
            </span>
          </div>
          <div className="mt-2 line-clamp-1 text-sm font-bold text-slate-900">{row.label}</div>
          <div className="mt-1 line-clamp-2 text-xs leading-5 text-slate-600">{row.headline}</div>
          {reason ? (
            <div className="mt-2 line-clamp-1 text-[11px] font-semibold leading-5 text-slate-500">
              Profilprüfung: {normalizeGermanDisplayText(reason)}
            </div>
          ) : null}
        </div>
        <div className="text-right">
          <div className="text-xl font-semibold tracking-tight text-slate-950 dark:text-white">{row.score != null ? formatNumber(row.score, 0) : "n/a"}</div>
          <div className="text-[9px] font-medium uppercase tracking-[0.12em] text-slate-400">Punkte</div>
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
            Analysieren <ArrowRight size={12} />
          </button>
        ) : null}
      </div>
    </div>
    );
  };

  return (
    <section className="surface-panel rounded-[2rem] p-5 sm:p-7">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
        <div className="max-w-3xl">
          <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">
            Edge Dashboard
          </div>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950 dark:text-white sm:text-3xl">
            Was jetzt handeln, beobachten oder meiden?
          </h2>
          <p className="mt-2 text-sm font-normal leading-6 text-slate-600 dark:text-slate-300">
            Scoreboard, Morning Brief, Portfolio, Lernkurve und Marktregime werden hier zu einer
            priorisierten Arbeitsliste verdichtet.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <a
            href="#world-market-map"
            className="inline-flex items-center gap-2 rounded-[0.95rem] border border-black/8 bg-white/80 dark:bg-white/10 dark:border-white/10 px-3 py-2 text-xs font-semibold tracking-wide text-slate-800 dark:text-slate-200"
          >
            <Globe2 size={14} /> Weltkarte
          </a>
          <button
            type="button"
            onClick={onOpenMarkets}
            className="inline-flex items-center gap-2 rounded-[0.95rem] border border-black/8 bg-white/80 dark:bg-white/10 dark:border-white/10 px-3 py-2 text-xs font-semibold tracking-wide text-slate-800 dark:text-slate-200"
          >
            <TrendingUp size={14} /> Märkte
          </button>
          <button
            type="button"
            onClick={onOpenPortfolio}
            className="inline-flex items-center gap-2 rounded-[0.95rem] bg-[#1d1d1f] px-3 py-2 text-xs font-semibold tracking-wide text-white dark:bg-white dark:text-slate-950"
          >
            <ShieldAlert size={14} /> Portfolio
          </button>
        </div>
      </div>

      {briefDecisionBlocked ? (
        <div className="mt-5 flex items-start gap-3 rounded-[1.15rem] border border-red-500/20 bg-red-500/8 p-4 text-red-900">
          <AlertTriangle size={18} className="mt-0.5 shrink-0" />
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.15em]">Briefing für Entscheidungen gesperrt</div>
            <div className="mt-1 text-sm leading-6">
              Der Datenstand ist veraltet oder eingeschränkt. Alte Setups und Ereignisse wurden entfernt; aktuelle Scoreboard- und Portfoliodaten bleiben nutzbar.
            </div>
          </div>
        </div>
      ) : null}

      <div className="mt-5 grid grid-cols-2 gap-3 xl:grid-cols-4">
        {kpis.map((item) => {
          const Icon = item.icon;
          return (
            <div key={item.label} className="rounded-[1.25rem] border border-black/6 bg-white/70 dark:border-white/10 dark:bg-white/5 p-4 shadow-xs">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">{item.label}</div>
                <Icon size={16} className="text-slate-400" />
              </div>
              <div className="mt-2.5 break-words text-2xl font-semibold tracking-tight text-slate-950 dark:text-white">{item.value}</div>
              <div className="mt-1 break-words text-xs font-normal leading-5 text-slate-500 dark:text-slate-400">{item.detail}</div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 hidden rounded-[1.25rem] border border-black/6 bg-white/70 dark:border-white/10 dark:bg-white/5 p-4 sm:block">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
              Lernkontrolle &middot; Top-Nachrichten
            </div>
            <div className="mt-1 text-sm font-medium leading-6 text-slate-700 dark:text-slate-200 sm:line-clamp-2">
              {topNewsLesson}
            </div>
          </div>
          <div className="grid shrink-0 grid-cols-3 gap-2 text-center">
            <div className="rounded-[0.95rem] border border-black/5 bg-white/60 dark:border-white/8 dark:bg-white/5 px-3 py-2">
              <div className="text-[9px] font-semibold uppercase tracking-[0.12em] text-slate-400">Treffer</div>
              <div className="mt-1 text-base font-semibold text-slate-950 dark:text-white">
                {topNewsHitRate != null ? `${formatNumber(topNewsHitRate, 0)}%` : "n/a"}
              </div>
            </div>
            <div className="rounded-[0.95rem] border border-black/5 bg-white/60 dark:border-white/8 dark:bg-white/5 px-3 py-2">
              <div className="text-[9px] font-semibold uppercase tracking-[0.12em] text-slate-400">Geprüft</div>
              <div className="mt-1 text-base font-semibold text-slate-950 dark:text-white">{formatNumber(topNewsEvaluated, 0)}</div>
            </div>
            <div className="rounded-[0.95rem] border border-black/5 bg-white/60 dark:border-white/8 dark:bg-white/5 px-3 py-2">
              <div className="text-[9px] font-semibold uppercase tracking-[0.12em] text-slate-400">Offen</div>
              <div className="mt-1 text-base font-semibold text-slate-950 dark:text-white">{formatNumber(topNewsPending, 0)}</div>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-4 hidden rounded-[1.35rem] border border-black/6 bg-white/70 p-4 dark:border-white/10 dark:bg-white/5 sm:block">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
              Makro-Entscheidungsrahmen
            </div>
            <div className="mt-1 text-base font-semibold tracking-tight text-slate-950 dark:text-white">
              Was bedeutet das für den Markt?
            </div>
          </div>
          <div className="text-xs font-normal text-slate-500 dark:text-slate-400">
            Risiko / Chance / Trigger / Invalidierung
          </div>
        </div>

        {macroPlaybookRows.length ? (
          <div className="mt-4 grid gap-3 lg:grid-cols-3">
            {macroPlaybookRows.map((item) => (
              <div key={item.key} className="rounded-[1.2rem] border border-black/6 bg-white/80 p-4 shadow-xs dark:border-white/10 dark:bg-white/5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`rounded-full border px-2.5 py-0.5 text-[9px] font-semibold tracking-wide ${toneClasses(item.tone)}`}>
                      {toneLabel(item.tone)}
                    </span>
                    <span className="text-[10px] font-medium tracking-wide text-slate-500 dark:text-slate-400">
                      {item.region} / {item.type}
                    </span>
                  </div>
                  <div className="text-sm font-semibold text-slate-900 dark:text-white">
                    {item.impactScore != null ? `${formatNumber(item.impactScore, 0)}` : "n/a"}
                  </div>
                </div>
                <div className="mt-2.5 line-clamp-2 text-sm font-semibold leading-5 text-slate-900 dark:text-white">
                  {item.title}
                </div>
                <div className="mt-1.5 line-clamp-2 text-xs font-normal leading-5 text-slate-600 dark:text-slate-300">
                  {item.whyNow}
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {(item.assets.length ? item.assets : ["Marktkorb"]).slice(0, 4).map((asset) => (
                    <span key={asset} className="rounded-full border border-black/6 bg-slate-50/70 px-2 py-0.5 text-[9px] font-medium text-slate-600 dark:border-white/10 dark:bg-white/6 dark:text-slate-300">
                      {asset}
                    </span>
                  ))}
                </div>
                <div className="mt-3 grid gap-1.5 border-t border-black/6 pt-3 text-[11px] font-normal leading-5 text-slate-600 dark:border-white/10 dark:text-slate-300">
                  <div>
                    <span className="font-semibold text-slate-900 dark:text-white">Trigger:</span> {normalizeGermanDisplayText(item.trigger)}
                  </div>
                  <div>
                    <span className="font-semibold text-slate-900 dark:text-white">Stop:</span> {normalizeGermanDisplayText(item.invalidation)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-4">
            <EmptyDecision
              icon={<Activity size={18} />}
              title="Kein Macro-Playbook aktiv"
              body={loading ? "Briefing wird noch geladen." : "Keine High-Impact-Ereignisse mit Trigger und Invalidierung im aktuellen Brief."}
            />
          </div>
        )}
      </div>

      {/* INSTITUTIONAL TRADING EDGE: GEX, VOLUME PROFILE & ASYMMETRIC SETUPS */}
      {tradingEdge?.asymmetric_setups?.length ? (
        <div className="mt-5 rounded-[1.35rem] border border-black/6 bg-white/70 p-5 shadow-xs dark:border-white/10 dark:bg-white/5">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2.5">
              <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-[#1d1d1f] text-white dark:bg-white dark:text-slate-950">
                <Zap size={16} />
              </span>
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                  Institutionelle Trading Edge
                </div>
                <div className="text-base font-semibold tracking-tight text-slate-950 dark:text-white">
                  Asymmetrische Setups &middot; Min. 2.5:1 R:R &middot; GEX &middot; Volume Profile
                </div>
              </div>
            </div>
            <div className="text-xs font-normal text-slate-500 dark:text-slate-400">
              Struktureller Stop &middot; Feste 0.75% Kontorisiko-Kalibrierung
            </div>
          </div>

          {telegramStatusMessage ? (
            <div className="mt-3 rounded-xl border border-emerald-500/20 bg-emerald-50/80 px-4 py-2 text-xs font-semibold text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300">
              {telegramStatusMessage}
            </div>
          ) : null}

          {tradingEdge?.regime?.stance ? (
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-black/5 bg-white/80 p-3 text-xs shadow-xs dark:border-white/10 dark:bg-white/5">
              <div className="flex items-center gap-2">
                <span className={`h-2.5 w-2.5 rounded-full ${
                  tradingEdge.regime.stance === "RISK_ON" ? "bg-emerald-500 animate-pulse" :
                  tradingEdge.regime.stance === "CAUTIOUS" ? "bg-amber-500" : "bg-rose-500"
                }`} />
                <span className="font-semibold tracking-wide text-slate-800 dark:text-slate-200">
                  Marktumfeld: {tradingEdge.regime.stance === "RISK_ON" ? "Risk-On (Ideale Long-Bedingungen)" :
                                 tradingEdge.regime.stance === "CAUTIOUS" ? "Neutral / Selektiv" : "Risk-Off (Defensiv)"}
                </span>
              </div>
              <div className="flex items-center gap-4 text-[11px] font-medium text-slate-600 dark:text-slate-300">
                {tradingEdge.regime.vix ? (
                  <span>VIX: <strong className="font-semibold text-slate-900 dark:text-white">{tradingEdge.regime.vix.value}</strong></span>
                ) : null}
                {tradingEdge.regime.spy ? (
                  <span>SPY: <strong className="font-semibold text-slate-900 dark:text-white">${tradingEdge.regime.spy.price}</strong> ({tradingEdge.regime.spy.trend})</span>
                ) : null}
                {tradingEdge.regime.qqq ? (
                  <span>QQQ: <strong className="font-semibold text-slate-900 dark:text-white">${tradingEdge.regime.qqq.price}</strong> ({tradingEdge.regime.qqq.trend})</span>
                ) : null}
              </div>
            </div>
          ) : null}

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            {tradingEdge.asymmetric_setups.map((setup: any) => (
              <div
                key={setup.ticker}
                className="flex flex-col justify-between rounded-[1.2rem] border border-black/6 bg-white/90 p-4 shadow-xs transition hover:border-black/15 dark:border-white/10 dark:bg-white/5"
              >
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => onAnalyzeTicker(setup.ticker)}
                        className="text-lg font-semibold tracking-tight text-slate-950 transition hover:text-slate-600 dark:text-white"
                      >
                        {setup.ticker}
                      </button>
                      {setup.grade_badge ? (
                        <span className={`rounded-md px-2 py-0.5 text-[10px] font-medium tracking-wide ${
                          setup.grade === "A+" ? "border border-emerald-500/25 bg-emerald-50/80 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300" :
                          setup.grade === "A" ? "border border-sky-500/25 bg-sky-50/80 text-sky-700 dark:bg-sky-950/40 dark:text-sky-300" :
                          "border border-slate-200 bg-slate-100 text-slate-700 dark:border-white/10 dark:bg-white/10 dark:text-slate-300"
                        }`}>
                          {setup.grade_badge} ({setup.confluence_score}/100)
                        </span>
                      ) : null}
                      <span className="rounded-full bg-slate-100 dark:bg-white/10 px-2.5 py-0.5 text-[10px] font-medium text-slate-700 dark:text-slate-300">
                        {setup.setup_name}
                      </span>
                    </div>
                    <div className="text-right">
                      <span className="rounded-md border border-black/6 bg-slate-50/80 dark:bg-white/10 dark:border-white/10 px-2 py-0.5 text-xs font-semibold text-slate-800 dark:text-slate-200">
                        R:R {setup.risk_reward_ratio}:1
                      </span>
                    </div>
                  </div>

                  <p className="mt-2 text-xs font-normal text-slate-600 dark:text-slate-300">
                    {setup.catalyst_description}
                  </p>

                  {setup.confluence_factors?.length ? (
                    <div className="mt-2.5 flex flex-wrap gap-1">
                      {setup.confluence_factors.map((f: string, idx: number) => (
                        <span key={idx} className="rounded-sm bg-slate-100/80 px-1.5 py-0.5 text-[9px] font-medium text-slate-700 dark:bg-white/10 dark:text-slate-300">
                          ✓ {f}
                        </span>
                      ))}
                    </div>
                  ) : null}

                  <div className="mt-3 grid grid-cols-2 gap-2 rounded-xl bg-slate-50/80 p-2.5 text-[11px] font-medium text-slate-700 dark:bg-white/5 dark:text-slate-300 border border-black/4 dark:border-white/5">
                    <div>
                      <span className="text-slate-400">Einstieg:</span> <span className="font-semibold text-slate-900 dark:text-white">${setup.entry_price}</span>
                    </div>
                    <div>
                      <span className="text-slate-400">Hard Stop:</span> <span className="font-semibold text-rose-600 dark:text-rose-400">${setup.invalidation_price}</span>
                    </div>
                    <div>
                      <span className="text-slate-400">Ziel 1 (2R):</span> <span className="font-semibold text-emerald-600 dark:text-emerald-400">${setup.target_1}</span>
                    </div>
                    <div>
                      <span className="text-slate-400">Ziel 2 (3.5R+):</span> <span className="font-semibold text-emerald-600 dark:text-emerald-400">${setup.target_2}</span>
                    </div>
                  </div>

                  {setup.options_gex ? (
                    <div className="mt-2 text-[10px] font-normal text-slate-500">
                      GEX: <span className="font-semibold text-slate-700 dark:text-slate-200">{setup.options_gex.regime}</span> &middot; Call Wall: ${setup.options_gex.call_wall} &middot; Put Wall: ${setup.options_gex.put_wall}
                    </div>
                  ) : null}
                  {setup.volume_profile ? (
                    <div className="mt-0.5 text-[10px] font-normal text-slate-500">
                      Volume Profile: POC ${setup.volume_profile.poc} &middot; VAH ${setup.volume_profile.vah} &middot; VAL ${setup.volume_profile.val}
                    </div>
                  ) : null}
                  {setup.anchored_vwap ? (
                    <div className="mt-0.5 text-[10px] font-normal text-slate-500">
                      ⚓ AVWAP: {setup.anchored_vwap.ytd ? `YTD $${setup.anchored_vwap.ytd}` : ""}
                      {setup.anchored_vwap.earnings ? ` · Earnings $${setup.anchored_vwap.earnings}` : ""}
                    </div>
                  ) : null}
                  {setup.whale_flow?.badge ? (
                    <div className="mt-1.5 flex items-center gap-1.5 rounded-md bg-slate-100 dark:bg-white/10 px-2 py-0.5 text-[10px] font-medium text-slate-700 dark:text-slate-300">
                      <span>{setup.whale_flow.badge}</span>
                      {setup.whale_flow.volume_ratio ? (
                        <span className="font-semibold text-slate-900 dark:text-white">
                          ({setup.whale_flow.volume_ratio}x Vol)
                        </span>
                      ) : null}
                    </div>
                  ) : null}
                  {setup.liquidity_zones?.zone_label && setup.liquidity_zones.zone_label !== "Neutral" ? (
                    <div className="mt-1 flex items-center gap-1 rounded-md bg-slate-100 dark:bg-white/10 px-2 py-0.5 text-[10px] font-medium text-slate-700 dark:text-slate-300">
                      <span>{setup.liquidity_zones.zone_label}</span>
                    </div>
                  ) : null}
                  {setup.mtf_alignment?.badge ? (
                    <div className="mt-0.5 text-[10px] font-normal text-slate-500">
                      🧭 MTF: <span className="font-semibold text-slate-800 dark:text-slate-200">{setup.mtf_alignment.badge}</span>
                    </div>
                  ) : null}

                  {setup.earnings_info ? (
                    <div className="mt-2 rounded-lg border border-amber-500/25 bg-amber-50/80 p-2 text-[10px] font-medium text-amber-900 dark:bg-amber-950/30 dark:text-amber-300">
                      {setup.earnings_info.warning}
                    </div>
                  ) : null}

                  {setup.trade_management ? (
                    <div className="mt-2 rounded-lg bg-slate-50/80 p-2 text-[10px] text-slate-600 dark:bg-white/5 dark:text-slate-300">
                      <div className="font-semibold text-slate-900 dark:text-white">Trailing-Stop Disziplin:</div>
                      <div>• <strong>2.0R Ziel:</strong> {setup.trade_management.target_1_action}</div>
                      <div>• <strong>3.5R+ Ziel:</strong> {setup.trade_management.target_2_action}</div>
                    </div>
                  ) : null}
                </div>

                <div className="mt-4 flex items-center justify-between border-t border-black/5 pt-3 dark:border-white/5">
                  <div className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
                    Sizing: <span className="font-semibold text-slate-950 dark:text-white">{setup.recommended_shares} Stk</span> (~{setup.total_position_capital?.toLocaleString()}€)
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => onAnalyzeTicker(setup.ticker)}
                      className="rounded-lg border border-black/8 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-50 dark:border-white/10 dark:bg-white/10 dark:text-slate-200"
                    >
                      Chart
                    </button>
                    <button
                      type="button"
                      onClick={() => handleOpenEdgePaperTrade(setup.ticker)}
                      disabled={openingPaperTicker === setup.ticker}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/20 bg-emerald-50/70 px-2.5 py-1.5 text-xs font-semibold text-emerald-800 shadow-2xs transition hover:bg-emerald-100 disabled:opacity-50 dark:border-emerald-500/30 dark:bg-emerald-950/40 dark:text-emerald-300"
                      title="Als Paper Trade im Demokonto eröffnen"
                    >
                      <TrendingUp size={13} className="text-emerald-600 dark:text-emerald-400" />
                      {openingPaperTicker === setup.ticker ? "Eröffne..." : "Paper Trade"}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleSendEdgeTelegram(setup.ticker)}
                      disabled={sendingTelegramTicker === setup.ticker}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-[#1d1d1f] px-3 py-1.5 text-xs font-semibold text-white shadow-xs transition hover:bg-black disabled:opacity-50 dark:bg-white dark:text-slate-950"
                    >
                      <Smartphone size={13} />
                      {sendingTelegramTicker === setup.ticker ? "Sendet..." : "Telegram"}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* LIVE TRADE LIFECYCLE & TRAILING STOP TRACKER */}
      {activeTrades.length > 0 ? (
        <div className="mt-5 rounded-[1.35rem] border border-black/6 bg-white/70 p-5 shadow-xs dark:border-white/10 dark:bg-white/5">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2.5">
              <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-[#1d1d1f] text-white dark:bg-white dark:text-slate-950">
                <Target size={16} />
              </span>
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                  Live Trade-Lifecycle & Trailing Stops
                </div>
                <div className="text-base font-semibold tracking-tight text-slate-950 dark:text-white">
                  Aktive Positionen &middot; Automatische Gewinnmitnahmen &middot; Breakeven-Schutz
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={handleEvaluateLifecycle}
              className="inline-flex items-center gap-1.5 self-start rounded-lg border border-black/8 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs transition hover:bg-slate-50 dark:border-white/10 dark:bg-white/10 dark:text-slate-200"
            >
              <Activity size={13} />
              Jetzt Prüfen
            </button>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {activeTrades.map((t) => {
              const entry = Number(t.entry_price) || 0;
              const last = Number(t.last_price) || entry;
              const t1 = Number(t.target_1) || 0;
              const t2 = Number(t.target_2) || 0;
              const stop = Number(t.trailing_stop) || Number(t.invalidation_price) || 0;
              const risk = Number(t.risk_per_share) || (entry - stop) || 1;
              const rMult = risk > 0 ? ((last - entry) / risk).toFixed(1) : "0.0";
              const isT1Hit = t.status === "TARGET_1_HIT";

              // Progress towards Target 1 (0 to 100%)
              const progressT1 = Math.max(0, Math.min(100, Math.round(((last - entry) / (t1 - entry || 1)) * 100)));

              return (
                <div key={t.ticker} className="rounded-xl border border-black/6 bg-white/90 p-3.5 shadow-xs dark:border-white/10 dark:bg-white/5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">{t.ticker}</span>
                      <span className="rounded-full bg-slate-100 dark:bg-white/10 px-2 py-0.5 text-[9px] font-medium text-slate-700 dark:text-slate-300">
                        {t.grade_badge || "Grade A"}
                      </span>
                    </div>
                    <span className={`text-xs font-semibold ${Number(rMult) >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
                      {Number(rMult) >= 0 ? `+${rMult}R` : `${rMult}R`}
                    </span>
                  </div>

                  <div className="mt-2.5 flex items-baseline justify-between text-xs">
                    <span className="text-slate-500">Kurs: <b className="font-semibold text-slate-900 dark:text-white">${last.toFixed(2)}</b></span>
                    <span className="text-slate-500">Einstieg: ${entry.toFixed(2)}</span>
                  </div>

                  {/* Progress bar to Target 1 */}
                  <div className="mt-2">
                    <div className="flex justify-between text-[10px] font-medium text-slate-500">
                      <span>Ziel 1: ${t1.toFixed(2)}</span>
                      <span>{progressT1}%</span>
                    </div>
                    <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${isT1Hit ? "bg-emerald-500" : "bg-[#1d1d1f] dark:bg-white"}`}
                        style={{ width: `${progressT1}%` }}
                      />
                    </div>
                  </div>

                  <div className="mt-3 flex items-center justify-between border-t border-black/5 pt-2.5 text-[11px] dark:border-white/5">
                    <span className={`rounded-md px-2 py-0.5 font-bold ${
                      isT1Hit
                        ? "bg-emerald-500/15 text-emerald-800 dark:text-emerald-300"
                        : "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                    }`}>
                      {isT1Hit ? `🟢 BE Stop: $${stop.toFixed(2)}` : `🛡️ Stop: $${stop.toFixed(2)}`}
                    </span>
                    <button
                      type="button"
                      onClick={() => onAnalyzeTicker(t.ticker)}
                      className="text-xs font-medium text-slate-600 hover:text-slate-950 dark:text-slate-400 dark:hover:text-white"
                    >
                      Chart &rarr;
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {/* RELATIVE STRENGTH (RS VS SPY) LEADERBOARD & WATCHLIST SCANNER */}
      <div className="mt-5 rounded-[1.35rem] border border-black/8 bg-white/75 p-5 shadow-2xs dark:border-white/10 dark:bg-slate-900/60">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#1d1d1f] text-white dark:bg-white dark:text-slate-950">
              <TrendingUp size={16} />
            </span>
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                Institutional Alpha &amp; Accumulation
              </div>
              <div className="text-base font-semibold tracking-tight text-slate-950 dark:text-white">
                Relative Stärke vs. S&amp;P 500 (Mansfield RS Leaders)
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleTriggerScanner}
              disabled={isScanning}
              className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-black text-white shadow-sm transition hover:bg-slate-800 disabled:opacity-50 dark:bg-white dark:text-slate-900"
            >
              <Zap size={13} />
              {isScanning ? "Scannt Watchlist..." : "Watchlist jetzt scannen"}
            </button>
          </div>
        </div>

        {scanResult ? (
          <div className="mt-3 rounded-xl border border-black/10 bg-slate-50 p-2.5 text-xs font-bold text-slate-800 dark:bg-slate-800 dark:text-slate-200">
            {scanResult}
          </div>
        ) : null}

        {rsLeaders.length > 0 ? (
          <div className="mt-4 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
            {rsLeaders.slice(0, 8).map((leader, i) => (
              <div
                key={leader.ticker}
                onClick={() => onAnalyzeTicker(leader.ticker)}
                className="cursor-pointer rounded-xl border border-black/6 bg-white/90 p-3 transition hover:border-black/20 dark:hover:border-white/20 hover:shadow-sm dark:border-white/8 dark:bg-slate-950/40"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-medium text-slate-400">#{i + 1}</span>
                    <span className="text-sm font-semibold text-slate-900 dark:text-white">{leader.ticker}</span>
                  </div>
                  <span className={`text-xs font-semibold ${leader.mansfield_rs >= 0 ? "text-emerald-600" : "text-red-500"}`}>
                    {leader.mansfield_rs >= 0 ? `+${leader.mansfield_rs.toFixed(1)}%` : `${leader.mansfield_rs.toFixed(1)}%`} RS
                  </span>
                </div>
                <div className="mt-1.5 flex items-center justify-between text-[10px] font-semibold text-slate-500">
                  <span>Alpha 1M: <b>{leader.alpha_1m >= 0 ? `+${leader.alpha_1m.toFixed(1)}%` : `${leader.alpha_1m.toFixed(1)}%`}</b></span>
                  <span>{leader.badge}</span>
                </div>
                {leader.divergent_strength ? (
                  <div className="mt-1.5 rounded-sm bg-slate-100 dark:bg-white/10 px-1.5 py-0.5 text-[9px] font-medium text-slate-700 dark:text-slate-300">
                    ⚡ Stark trotz Markt
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-3 text-xs font-semibold text-slate-500">
            Relative-Stärke-Daten werden beim nächsten Scan automatisch aktualisiert.
          </div>
        )}
      </div>

      <div className="edge-decision-strip mt-5 grid gap-4 xl:grid-cols-3">
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-[0.16em] text-emerald-700">
            <CheckCircle2 size={15} /> Handeln
          </div>
          {actionRows.length ? (
            actionRows.map(renderRow)
          ) : (
            <EmptyDecision
              icon={<Target size={18} />}
              title="Kein sofortiger A-Setup"
              body={loading ? "Signalquellen laden noch." : "Kein Score ist aktuell stark genug für eine direkte Handlung."}
            />
          )}
        </div>

        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-[0.16em] text-amber-700">
            <Eye size={15} /> Beobachten
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
            <Ban size={15} /> Meiden / Risiko
          </div>
          {avoidRows.length ? avoidRows.map(renderRow) : null}
          {blockers.length ? (
            <div className="rounded-[1.1rem] border border-red-500/15 bg-red-500/8 p-3">
              <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.14em] text-red-800">
                <AlertTriangle size={15} /> Risikobremsen
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
              body="Keine klare Meiden-Liste aus Scoreboard, Portfolio oder Lernkurve."
            />
          ) : null}
          {lessons[0] ? (
            <div className="rounded-[1.1rem] border border-black/8 bg-white/72 p-3">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                Lernsignal
              </div>
              <div className="mt-2 line-clamp-3 text-xs font-semibold leading-5 text-slate-700">
                {localizeLearningMessage(lessons[0]?.message || lessons[0]?.lesson || lessons[0]?.text || lessons[0])}
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
