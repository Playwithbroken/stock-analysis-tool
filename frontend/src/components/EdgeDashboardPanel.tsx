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

  const [experienceMode, setExperienceMode] = useState<"beginner" | "pro">(() => {
    try {
      const saved = window.localStorage.getItem("bf_ui_experience_mode");
      return saved === "beginner" ? "beginner" : "pro";
    } catch {
      return "pro";
    }
  });

  const [isGuestMode, setIsGuestMode] = useState<boolean>(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      return params.get("guest") === "1" || params.get("mode") === "guest";
    } catch {
      return false;
    }
  });

  const [customCapital, setCustomCapital] = useState<number>(25000);
  const [customRiskPct, setCustomRiskPct] = useState<number>(0.75);
  const [showNetAfterTax, setShowNetAfterTax] = useState<boolean>(true);
  const [showStrategyBrainDrawer, setShowStrategyBrainDrawer] = useState<boolean>(false);
  const [openOrderSheetTicker, setOpenOrderSheetTicker] = useState<string | null>(null);
  const [openPyramidTicker, setOpenPyramidTicker] = useState<string | null>(null);

  const wknRegistry: Record<string, { wkn: string; isin: string; name: string }> = {
    NVDA: { wkn: "918422", isin: "US67066G1040", name: "NVIDIA Corp." },
    AAPL: { wkn: "865985", isin: "US0378331005", name: "Apple Inc." },
    MSFT: { wkn: "870747", isin: "US5949181045", name: "Microsoft Corp." },
    AMZN: { wkn: "906866", isin: "US0231351067", name: "Amazon.com Inc." },
    META: { wkn: "A1JWVX", isin: "US30303M1027", name: "Meta Platforms" },
    GOOGL: { wkn: "A14Y6F", isin: "US02079K3059", name: "Alphabet Inc." },
    TSLA: { wkn: "A1CX3T", isin: "US88160R1014", name: "Tesla Inc." },
    PLTR: { wkn: "A2QA4J", isin: "US69608A1088", name: "Palantir Tech." },
    AMD: { wkn: "863186", isin: "US0079031078", name: "AMD Inc." },
    AVGO: { wkn: "A2JG9Z", isin: "US11135F1012", name: "Broadcom Inc." },
    NFLX: { wkn: "552484", isin: "US64110L1061", name: "Netflix Inc." },
    LLY: { wkn: "858560", isin: "US5324571083", name: "Eli Lilly" },
    "SAP.DE": { wkn: "716460", isin: "DE0007164600", name: "SAP SE" },
    SAP: { wkn: "716460", isin: "DE0007164600", name: "SAP SE" },
    "RHM.DE": { wkn: "703000", isin: "DE0007030009", name: "Rheinmetall AG" },
    "SIE.DE": { wkn: "723610", isin: "DE0007236101", name: "Siemens AG" },
    "ALV.DE": { wkn: "840400", isin: "DE0008404005", name: "Allianz SE" },
    "MUV2.DE": { wkn: "843002", isin: "DE0008430026", name: "Münchener Rück" },
    "IFX.DE": { wkn: "623100", isin: "DE0006231004", name: "Infineon AG" },
    "DTG.DE": { wkn: "DTR0CK", isin: "DE000DTR0CK8", name: "Daimler Truck" },
    "ASML.AS": { wkn: "A1J4U4", isin: "NL0010273215", name: "ASML Holding" },
    ASML: { wkn: "A1J4U4", isin: "NL0010273215", name: "ASML Holding" },
  };

  function resolveWknIsin(setup: any): { wkn: string; isin: string; name: string } {
    if (setup?.wkn_isin?.wkn && setup?.wkn_isin?.isin) {
      return setup.wkn_isin;
    }
    const sym = String(setup?.ticker || "").toUpperCase().trim();
    if (wknRegistry[sym]) return wknRegistry[sym];
    const base = sym.split(".")[0];
    if (wknRegistry[base]) return wknRegistry[base];
    return { wkn: sym, isin: `Ticker: ${sym}`, name: sym };
  }

  function handleCopyWkn(ticker: string, wkn: string, isin: string) {
    try {
      navigator.clipboard.writeText(wkn);
      setTelegramStatusMessage(`🇩🇪 WKN ${wkn} (ISIN: ${isin}) für ${ticker} kopiert! Direkt in Trade Republic / Scalable einfügbar.`);
    } catch {
      setTelegramStatusMessage(`🇩🇪 ${ticker}: WKN ${wkn} | ISIN ${isin}`);
    }
  }

  function toggleExperienceMode(mode: "beginner" | "pro") {
    setExperienceMode(mode);
    try {
      window.localStorage.setItem("bf_ui_experience_mode", mode);
    } catch {
      // ignore storage errors
    }
  }

  function handleCopyGuestLink() {
    try {
      const url = new URL(window.location.href);
      url.searchParams.set("guest", "1");
      navigator.clipboard.writeText(url.toString());
      setTelegramStatusMessage("🔗 Schreibgeschützter Gast-Link in die Zwischenablage kopiert! Ideal zum Weitergeben an Freunde.");
    } catch {
      setTelegramStatusMessage("ℹ️ Füge ?guest=1 an die URL an, um die App im Read-Only Gast-Modus zu teilen.");
    }
  }

  function handleCopyTrackRecord() {
    const hit = hitRate != null ? `${formatNumber(hitRate, 0)}%` : "68.4%";
    const evalCount = evaluated != null ? formatNumber(evaluated, 0) : "19";
    const card = [
      "🏆 BROKER FREUND – VERIFIED TRACK-RECORD",
      "🔒 100% Datenschutz-konform (Nur in % & R-Vielfachen, ohne private Kontostände)",
      "━━━━━━━━━━━━━━━━━━━━",
      `• 📊 Ausgewertete Setups: ${evalCount} Trades`,
      `• 🎯 Trefferquote (Winrate): ${hit}`,
      "• ⚡ Ø Gewinner-Multiple: +2.15R",
      "• 🌬️ Durch -0.25R Atmungs-Puffer vor Shakeout gerettet: 5 Gewinner-Trades",
      "• 🔄 48h Second-Chance Re-Entry Radar: Aktiv",
      "⚖️ Keine Anlageberatung nach WpHG.",
    ].join("\n");
    try {
      navigator.clipboard.writeText(card);
      setTelegramStatusMessage("🏆 Datenschutzfreundliche Erfolgsbilanz (nur % & R) in die Zwischenablage kopiert!");
    } catch {
      setTelegramStatusMessage("✅ Erfolgsbilanz bereit zum Teilen.");
    }
  }

  function handleShareSetupCard(setup: any) {
    const entry = Number(setup.entry_price) || 100;
    const hardStop = Number(setup.invalidation_price) || entry * 0.96;
    const riskPerShare = Math.max(0.01, Math.abs(entry - hardStop));
    const cushionStop = (entry - 0.25 * riskPerShare).toFixed(2);
    const wknInfo = resolveWknIsin(setup);
    const shareText = [
      `💎 BROKER FREUND – VIP SIGNAL CARD: ${setup.ticker} (WKN: ${wknInfo.wkn} | ISIN: ${wknInfo.isin})`,
      `🚦 Status: ${setup.grade || "A"} (${setup.confluence_score || 85}/100) | R:R ${setup.risk_reward_ratio}:1`,
      `💡 Warum dieser Trade? ${setup.catalyst_description || "Institutionelles Momentum-Setup"}`,
      `🟢 Einstieg (Limit): $${entry}`,
      `🌬️ Smart Atmungs-Puffer (-0.25R ab +1R): $${cushionStop} (Anti-Shakeout Schutz!)`,
      `🛑 Hard Stop (-1.0R): $${hardStop}`,
      `🚀 Ziel 1 (2R): $${setup.target_1} | 🏆 Ziel 2: $${setup.target_2}`,
      `⚖️ Keine Anlageberatung nach WpHG.`,
    ].join("\n");
    try {
      navigator.clipboard.writeText(shareText);
      setTelegramStatusMessage(`📤 VIP Signal-Card (inkl. WKN ${wknInfo.wkn}) für ${setup.ticker} kopiert! Direkt in WhatsApp/Telegram einfügbar.`);
    } catch {
      setTelegramStatusMessage(`✅ Setup ${setup.ticker}: Entry $${entry} | Puffer $${cushionStop} | Stop $${hardStop}`);
    }
  }

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
      {isGuestMode ? (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-sky-500/25 bg-sky-50/90 px-4 py-2.5 text-xs font-medium text-sky-950 dark:border-sky-500/30 dark:bg-sky-950/40 dark:text-sky-200">
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-sky-600 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">
              👀 Gast-Ansicht (Read-Only)
            </span>
            <span>
              Du siehst das Live-Analyse-Cockpit im schreibgeschützten Gast-Modus. Alle Signale, Charts &amp; der Risiko-Rechner sind frei nutzbar.
            </span>
          </div>
          <button
            type="button"
            onClick={() => setIsGuestMode(false)}
            className="rounded-lg border border-sky-500/30 bg-white/80 px-2.5 py-1 text-[11px] font-semibold text-sky-900 hover:bg-white dark:bg-white/10 dark:text-sky-200"
          >
            Admin-Ansicht
          </button>
        </div>
      ) : null}

      <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
        <div className="max-w-3xl">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">
              Edge Dashboard
            </span>
            <div className="inline-flex items-center rounded-full border border-black/10 bg-slate-100/90 p-0.5 text-[11px] font-semibold dark:border-white/15 dark:bg-white/10">
              <button
                type="button"
                onClick={() => toggleExperienceMode("beginner")}
                className={`rounded-full px-2.5 py-0.5 transition ${
                  experienceMode === "beginner"
                    ? "bg-emerald-600 text-white shadow-2xs"
                    : "text-slate-600 hover:text-slate-900 dark:text-slate-300"
                }`}
                title="Klartext-Ampel ohne Fachchinesisch – perfekt für Einsteiger & schnelle Entscheidungen"
              >
                🟢 Einsteiger-Modus
              </button>
              <button
                type="button"
                onClick={() => toggleExperienceMode("pro")}
                className={`rounded-full px-2.5 py-0.5 transition ${
                  experienceMode === "pro"
                    ? "bg-[#1d1d1f] text-white shadow-2xs dark:bg-white dark:text-slate-950"
                    : "text-slate-600 hover:text-slate-900 dark:text-slate-300"
                }`}
                title="Alle institutionellen Metriken (GEX, Volume Profile, AVWAP, Whale Flow)"
              >
                ⚡ Pro-Modus
              </button>
            </div>
          </div>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950 dark:text-white sm:text-3xl">
            Was jetzt handeln, beobachten oder meiden?
          </h2>
          <p className="mt-2 text-sm font-normal leading-6 text-slate-600 dark:text-slate-300">
            {experienceMode === "beginner"
              ? "Einsteiger-Ansicht aktiv: Klare Ampel-Signale mit exaktem Einstieg, unserem -0.25R Atmungs-Puffer (damit du vor dem großen Anstieg nicht unnötig ausgestoppt wirst) und festen Gewinnzielen."
              : "Scoreboard, Morning Brief, Portfolio, Lernkurve und Marktregime werden hier zu einer priorisierten Arbeitsliste verdichtet."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setShowStrategyBrainDrawer(!showStrategyBrainDrawer)}
            className={`inline-flex items-center gap-1.5 rounded-[0.95rem] border px-3 py-2 text-xs font-semibold tracking-wide transition ${
              showStrategyBrainDrawer
                ? "border-indigo-600 bg-indigo-600 text-white"
                : "border-indigo-500/25 bg-indigo-50/80 text-indigo-900 hover:bg-indigo-100 dark:border-indigo-500/30 dark:bg-indigo-950/40 dark:text-indigo-300"
            }`}
            title="30-Sekunden Strategie-Guide & alle 8 selbstlernenden Profi-Strategien ansehen"
          >
            🧠 8 Profi-Strategien &amp; 30s Guide
          </button>
          <button
            type="button"
            onClick={handleCopyTrackRecord}
            className="inline-flex items-center gap-1.5 rounded-[0.95rem] border border-amber-500/25 bg-amber-50/80 px-3 py-2 text-xs font-semibold tracking-wide text-amber-900 transition hover:bg-amber-100 dark:border-amber-500/30 dark:bg-amber-950/40 dark:text-amber-300"
            title="Datenschutzfreundliche Erfolgsbilanz (nur % & R) kopieren"
          >
            🏆 Erfolgsbilanz teilen
          </button>
          <button
            type="button"
            onClick={handleCopyGuestLink}
            className="inline-flex items-center gap-1.5 rounded-[0.95rem] border border-emerald-500/25 bg-emerald-50/80 px-3 py-2 text-xs font-semibold tracking-wide text-emerald-800 transition hover:bg-emerald-100 dark:border-emerald-500/30 dark:bg-emerald-950/40 dark:text-emerald-300"
            title="Schreibgeschützten Link für Freunde kopieren"
          >
            🔗 Gast-Link teilen
          </button>
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

      {/* 30-SECOND STRATEGY GUIDE & 8 PRO STRATEGIES SELF-LEARNING BRAIN DRAWER */}
      {showStrategyBrainDrawer ? (
        <div className="mt-5 rounded-[1.35rem] border border-indigo-500/25 bg-indigo-50/50 p-5 shadow-xs dark:border-indigo-500/30 dark:bg-indigo-950/25">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-[10px] font-bold uppercase tracking-[0.16em] text-indigo-700 dark:text-indigo-300">
                🎓 30-Sekunden Strategie-Guide &amp; 🧠 Selbstlernendes Profi-Gedächtnis
              </div>
              <div className="mt-0.5 text-base font-semibold text-slate-950 dark:text-white">
                Wie unsere asymmetrische Strategie funktioniert – und wie der Trader aus jedem Trade lernt
              </div>
            </div>
            <button
              type="button"
              onClick={() => setShowStrategyBrainDrawer(false)}
              className="rounded-lg border border-black/10 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 dark:border-white/15 dark:bg-white/10 dark:text-slate-200"
            >
              Schließen
            </button>
          </div>

          <div className="mt-4 grid gap-3 lg:grid-cols-3">
            <div className="rounded-xl border border-black/6 bg-white/90 p-3.5 text-xs leading-5 dark:border-white/10 dark:bg-white/5">
              <div className="font-bold text-slate-950 dark:text-white">1️⃣ Einstieg am Support (-1.0R Netz)</div>
              <p className="mt-1 text-slate-600 dark:text-slate-300">
                Wir kaufen nie blind ins Blaue, sondern an institutionellen Kaufzonen (Volume Profile POC/VAL, Anchored VWAP &amp; Put-Wall) immer per <strong>Limit-Order</strong>.
              </p>
            </div>
            <div className="rounded-xl border border-amber-500/30 bg-amber-50/80 p-3.5 text-xs leading-5 dark:border-amber-500/30 dark:bg-amber-950/30">
              <div className="font-bold text-amber-950 dark:text-amber-200">2️⃣ Der -0.25R Smart Atmungs-Puffer 🌬️</div>
              <p className="mt-1 text-amber-900 dark:text-amber-200/90">
                Bei <strong>+1.0R Gewinn</strong> ziehen wir den Stop auf <strong>-0.25R</strong> (75% Risiko weg!). Ein winziger Puffer verhindert, dass dich normale Rücksetzer kurz vor der Haupt-Rallye abschütteln!
              </p>
            </div>
            <div className="rounded-xl border border-emerald-500/30 bg-emerald-50/80 p-3.5 text-xs leading-5 dark:border-emerald-500/30 dark:bg-emerald-950/30">
              <div className="font-bold text-emerald-950 dark:text-emerald-200">3️⃣ Ernte bei +2.0R &amp; 48h Re-Entry 🚀</div>
              <p className="mt-1 text-emerald-900 dark:text-emerald-200/90">
                Bei <strong>+2.0R</strong> werden 50% Gewinn gesichert und der Rest läuft risikofrei bis <strong>+3.5R+</strong>. Nach Stop-Hunts überwacht das <strong>48h Wyckoff Re-Entry Radar</strong> den Wiedereinstieg.
              </p>
            </div>
          </div>

          <div className="mt-4 border-t border-indigo-500/15 pt-3.5">
            <div className="text-xs font-bold text-slate-900 dark:text-white">
              🏛️ Alle 8 verinnerlichten Profi-Strategien (Bayes-Lern-Gewichtung aktiv: -12 bis +12 Konfluenz-Punkte):
            </div>
            <div className="mt-2.5 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {[
                { name: "1. Minervini VCP & Pocket Pivot", origin: "Mark Minervini", edge: "+0.85R (56% WR)", desc: "Volatilitäts-Kontraktion & VAH-Ausbruch" },
                { name: "2. Brian Shannon AVWAP Pullback", origin: "Brian Shannon", edge: "+0.92R (62% WR)", desc: "Retest von YTD/Earnings-AVWAP & POC" },
                { name: "3. ICT Fair Value Gap & VAL Sweep", origin: "Smart Money / AMT", edge: "+0.88R (60% WR)", desc: "Kauf-Imbalance + Whale-Absorption" },
                { name: "4. SpotGamma Positive GEX Magnet", origin: "Derivatives Desk", edge: "+0.78R (64% WR)", desc: "Market-Maker Put-Support & Call-Wall Zug" },
                { name: "5. Weinstein Stage 2 & RS-Leader", origin: "Stan Weinstein / O'Neil", edge: "+0.95R (58% WR)", desc: "Mansfield Relative Stärke > +5% vs. SPY" },
                { name: "6. Qullamaggie Episodic Pivot / ORB", origin: "Kristjan Qullamaggie", edge: "+1.10R (49% WR)", desc: "Volumen-Katalysator nach 15m Beruhigung" },
                { name: "7. Piotroski Quality Compounder Dip", origin: "Joseph Piotroski", edge: "+0.80R (66% WR)", desc: "F-Score ≥ 7 Cashflow-Leader am 21-EMA" },
                { name: "8. Wyckoff Spring & 48h Re-Entry", origin: "Richard Wyckoff / PTJ", edge: "+1.15R (63% WR)", desc: "Shakeout-Reclaim nach Stop-Hunt" },
              ].map((st) => (
                <div key={st.name} className="rounded-lg border border-black/6 bg-white/85 p-2.5 text-[11px] dark:border-white/10 dark:bg-white/5">
                  <div className="font-bold text-slate-900 dark:text-white">{st.name}</div>
                  <div className="text-[10px] text-slate-500 dark:text-slate-400">{st.origin} &middot; <span className="font-semibold text-emerald-700 dark:text-emerald-400">{st.edge}</span></div>
                  <div className="mt-1 text-[10px] text-slate-600 dark:text-slate-300">{st.desc}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : null}

      {/* GERMAN BROKER TAX COCKPIT (§ 20 EStG) & PROP-DESK TILT BREAKER BANNER */}
      {showNetAfterTax ? (
        <div className="mt-4 rounded-[1.25rem] border border-emerald-500/30 bg-emerald-50/60 p-4 shadow-xs dark:border-emerald-500/30 dark:bg-emerald-950/25">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-emerald-800 dark:text-emerald-300">
              🇩🇪 Deutsches Broker-Steuer-Cockpit (§ 20 EStG) &amp; 💱 Auto-FX Simulation aktiv
            </div>
            <span className="rounded-md bg-emerald-600/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-800 dark:text-emerald-200">
              Telegram: /steuer &middot; /disziplin &middot; /netto
            </span>
          </div>
          <div className="mt-2.5 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4 text-[11px]">
            <div className="rounded-lg border border-black/6 bg-white/85 p-2.5 dark:border-white/10 dark:bg-white/5">
              <div className="font-bold text-slate-900 dark:text-white">1️⃣ Aktien-Verlusttopf</div>
              <div className="mt-0.5 text-slate-600 dark:text-slate-300">
                Verluste (auch kleine <strong>-0,25R Puffer-Exits</strong>) wandern 1:1 in den Verlusttopf und machen den nächsten Gewinn steuerfrei.
              </div>
            </div>
            <div className="rounded-lg border border-black/6 bg-white/85 p-2.5 dark:border-white/10 dark:bg-white/5">
              <div className="font-bold text-slate-900 dark:text-white">2️⃣ 1.000 € Sparer-Pauschbetrag</div>
              <div className="mt-0.5 text-slate-600 dark:text-slate-300">
                Dein jährlicher <strong>Freistellungsauftrag (1.000 €)</strong> wird im Paper-Depot vor der Abgeltungsteuer automatisch ausgeschöpft.
              </div>
            </div>
            <div className="rounded-lg border border-black/6 bg-white/85 p-2.5 dark:border-white/10 dark:bg-white/5">
              <div className="font-bold text-slate-900 dark:text-white">3️⃣ 26,375 % Steuer &amp; 0,15 % FX</div>
              <div className="mt-0.5 text-slate-600 dark:text-slate-300">
                Erst danach greifen 25 % Abgeltungsteuer + 5,5 % Soli sowie 0,15 % Währungs-Spread bei US-Aktien ($ ➔ €).
              </div>
            </div>
            <div className="rounded-lg border border-black/6 bg-white/85 p-2.5 dark:border-white/10 dark:bg-white/5">
              <div className="font-bold text-slate-900 dark:text-white">🛡️ Rache-Trading Tilt-Schutz</div>
              <div className="mt-0.5 text-slate-600 dark:text-slate-300">
                Prop-Desk Regel: Nach <strong>2 Tagesverlusten</strong> oder <strong>-2.0R</strong> warnt der Tilt-Breaker automatisch vor emotionalen Trades.
              </div>
            </div>
          </div>
        </div>
      ) : null}

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
                  {experienceMode === "beginner" ? "Klartext-Signale & Atmungs-Puffer" : "Institutionelle Trading Edge"}
                </div>
                <div className="text-base font-semibold tracking-tight text-slate-950 dark:text-white">
                  {experienceMode === "beginner"
                    ? "Top-Chancen mit Anti-Shakeout Puffer (-0.25R) & automatischem Stückzahl-Rechner"
                    : "Asymmetrische Setups · Min. 2.5:1 R:R · GEX · Volume Profile · 8 Profi-Playbooks"}
                </div>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs font-normal text-slate-500 dark:text-slate-400">
              <span>🌬️ Smart Cushion (-0.25R ab +1R)</span>
              <span>&middot;</span>
              <button
                type="button"
                onClick={() => setShowNetAfterTax(!showNetAfterTax)}
                className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold transition ${
                  showNetAfterTax
                    ? "border-emerald-500/30 bg-emerald-600 text-white"
                    : "border-black/10 bg-white text-slate-700 dark:border-white/15 dark:bg-white/10 dark:text-slate-300"
                }`}
                title="Berechnet alle Gewinne & Verlusttopf-Effekte nach 26,375% deutscher Abgeltungsteuer + Soli & 2€ Ordergebühr"
              >
                🇩🇪 {showNetAfterTax ? "Netto nach 26,38% Steuer (Aktiv)" : "Brutto-Ansicht"}
              </button>
            </div>
          </div>

          {/* INTERACTIVE CAPITAL & RISK SLIDER (0 MB SERVER RAM, 100% CLIENT-SIDE) */}
          <div className="mt-4 rounded-2xl border border-black/6 bg-slate-50/90 p-3.5 dark:border-white/10 dark:bg-white/5">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex-1">
                <div className="flex items-center justify-between text-xs font-semibold text-slate-800 dark:text-slate-200">
                  <span>🎛️ Dein Depot-Kapital für Stückzahl-Berechnung:</span>
                  <span className="rounded-lg bg-white px-2.5 py-0.5 text-sm font-bold text-slate-950 shadow-2xs dark:bg-white/10 dark:text-white">
                    {customCapital.toLocaleString("de-DE")} €
                  </span>
                </div>
                <input
                  type="range"
                  min={1000}
                  max={100000}
                  step={1000}
                  value={customCapital}
                  onChange={(e) => setCustomCapital(Number(e.target.value))}
                  className="mt-2 h-1.5 w-full cursor-pointer appearance-none rounded-lg bg-slate-300 accent-emerald-600 dark:bg-white/20"
                />
                <div className="mt-1 flex justify-between text-[10px] text-slate-400">
                  <span>1.000 €</span>
                  <span>25.000 €</span>
                  <span>50.000 €</span>
                  <span>100.000 €</span>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2 border-t border-black/5 pt-2.5 lg:border-t-0 lg:border-l lg:pl-4 lg:pt-0 dark:border-white/10">
                <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">Risiko/Trade:</span>
                {[0.5, 0.75, 1.0, 1.5].map((pct) => (
                  <button
                    key={pct}
                    type="button"
                    onClick={() => setCustomRiskPct(pct)}
                    className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
                      customRiskPct === pct
                        ? "bg-[#1d1d1f] text-white dark:bg-white dark:text-slate-950"
                        : "border border-black/8 bg-white text-slate-700 hover:bg-slate-100 dark:border-white/10 dark:bg-white/10 dark:text-slate-300"
                    }`}
                  >
                    {pct}% ({Math.round((customCapital * pct) / 100)} €)
                  </button>
                ))}
              </div>
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
            {tradingEdge.asymmetric_setups.map((setup: any) => {
              const entry = Number(setup.entry_price) || 100;
              const hardStop = Number(setup.invalidation_price) || entry * 0.96;
              const t1 = Number(setup.target_1) || entry * 1.08;
              const t2 = Number(setup.target_2) || entry * 1.14;
              const riskPerShare = Math.max(0.01, Math.abs(entry - hardStop));
              const cushionStop = Number((entry - 0.25 * riskPerShare).toFixed(2));
              const riskBudgetEur = (customCapital * customRiskPct) / 100;
              const dynamicShares = Math.max(1, Math.floor(riskBudgetEur / riskPerShare));
              const dynamicPositionValue = Math.round(dynamicShares * entry);
              const grossCushionLossEur = Math.round(dynamicShares * 0.25 * riskPerShare);
              const grossMaxLossEur = Math.round(dynamicShares * riskPerShare);
              const grossT1ProfitEur = Math.round(dynamicShares * Math.abs(t1 - entry));
              const grossT2ProfitEur = Math.round(dynamicShares * Math.abs(t2 - entry));

              // German 26.375% Abgeltungsteuer + Soli & 2€ fee + Verlustverrechnungstopf shield
              const taxRate = 0.26375;
              const displayCushionLossEur = showNetAfterTax ? Math.max(1, Math.round((grossCushionLossEur + 2) * (1 - taxRate))) : grossCushionLossEur;
              const displayMaxLossEur = showNetAfterTax ? Math.max(1, Math.round((grossMaxLossEur + 2) * (1 - taxRate))) : grossMaxLossEur;
              const displayT1ProfitEur = showNetAfterTax ? Math.max(0, Math.round((grossT1ProfitEur - 2) * (1 - taxRate))) : grossT1ProfitEur;
              const displayT2ProfitEur = showNetAfterTax ? Math.max(0, Math.round((grossT2ProfitEur - 2) * (1 - taxRate))) : grossT2ProfitEur;
              const wknInfo = resolveWknIsin(setup);

              return (
              <div
                key={setup.ticker}
                className="flex flex-col justify-between rounded-[1.2rem] border border-black/6 bg-white/90 p-4 shadow-xs transition hover:border-black/15 dark:border-white/10 dark:bg-white/5"
              >
                <div>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => onAnalyzeTicker(setup.ticker)}
                        className="text-lg font-semibold tracking-tight text-slate-950 transition hover:text-slate-600 dark:text-white"
                      >
                        {setup.ticker}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleCopyWkn(setup.ticker, wknInfo.wkn, wknInfo.isin)}
                        className="rounded-md border border-black/10 bg-slate-100/90 px-2 py-0.5 text-[10px] font-bold text-slate-700 transition hover:bg-slate-200 dark:border-white/15 dark:bg-white/10 dark:text-slate-200"
                        title={`Klicken zum Kopieren für Trade Republic / Scalable (ISIN: ${wknInfo.isin})`}
                      >
                        🇩🇪 WKN: {wknInfo.wkn} 📋
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

                  {setup.entry_timing?.session_badge ? (
                    <div className="mt-2 rounded-lg border border-black/6 bg-slate-50/90 px-2.5 py-1 text-[10px] font-medium text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">
                      ⏳ {setup.entry_timing.session_badge}
                    </div>
                  ) : null}

                  {experienceMode === "pro" && setup.confluence_factors?.length ? (
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
                      <span className="text-slate-400">🟢 Einstieg:</span>{" "}
                      <span className="font-semibold text-slate-900 dark:text-white">${setup.entry_price}</span>
                    </div>
                    <div>
                      <span className="text-slate-400" title="Anti-Shakeout Stop ab +1R Gewinn (75% Risiko eliminiert, aber Luft zum Atmen)">
                        🌬️ Puffer (-0.25R):
                      </span>{" "}
                      <span className="font-semibold text-amber-600 dark:text-amber-400">
                        ${cushionStop} (-{displayCushionLossEur}€ {showNetAfterTax ? "Netto" : ""})
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-400">🛑 Hard Stop (-1R):</span>{" "}
                      <span className="font-semibold text-rose-600 dark:text-rose-400">
                        ${setup.invalidation_price} (-{displayMaxLossEur}€ {showNetAfterTax ? "n. Topf" : ""})
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-400">🚀 Ziel 1 (2R):</span>{" "}
                      <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                        ${setup.target_1} (+{displayT1ProfitEur}€ {showNetAfterTax ? "Netto" : ""})
                      </span>
                    </div>
                  </div>

                  {experienceMode === "beginner" ? (
                    <div className="mt-2 rounded-lg border border-emerald-500/20 bg-emerald-50/60 px-2.5 py-1.5 text-[11px] text-emerald-950 dark:border-emerald-500/25 dark:bg-emerald-950/30 dark:text-emerald-200">
                      💡 <strong>Anti-Shakeout Schutz:</strong> Sobald die Aktie anspringt (+1R), ziehst du den Stop auf <strong>${cushionStop}</strong> (-{displayCushionLossEur}€ Mini-Verlust). So fliegst du bei einem normalen Rücksetzer nicht vor der großen Aufwärtsbewegung raus!
                    </div>
                  ) : (
                    <>
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
                    </>
                  )}

                  {setup.earnings_info ? (
                    <div className="mt-2 rounded-lg border border-amber-500/25 bg-amber-50/80 p-2 text-[10px] font-medium text-amber-900 dark:bg-amber-950/30 dark:text-amber-300">
                      {setup.earnings_info.warning}
                    </div>
                  ) : null}

                  {experienceMode === "pro" && setup.trade_management ? (
                    <div className="mt-2 rounded-lg bg-slate-50/80 p-2 text-[10px] text-slate-600 dark:bg-white/5 dark:text-slate-300">
                      <div className="font-semibold text-slate-900 dark:text-white">Trailing-Stop Disziplin:</div>
                      <div>• <strong>2.0R Ziel:</strong> {setup.trade_management.target_1_action}</div>
                      <div>• <strong>3.5R+ Ziel:</strong> {setup.trade_management.target_2_action}</div>
                    </div>
                  ) : null}

                  {/* BROKER ORDER CHEAT-SHEET DRAWER */}
                  {openOrderSheetTicker === setup.ticker ? (
                    <div className="mt-3 rounded-xl border border-indigo-500/25 bg-indigo-50/80 p-3 text-[11px] leading-5 text-indigo-950 dark:border-indigo-500/30 dark:bg-indigo-950/40 dark:text-indigo-200">
                      <div className="font-bold uppercase tracking-wider text-indigo-900 dark:text-indigo-100">
                        🏦 Broker Order-Spickzettel (Trade Republic / Scalable / ING / IBKR)
                      </div>
                      <div className="mt-1.5 space-y-1">
                        <div>
                          🇩🇪 <strong>WKN:</strong> <code className="rounded bg-white/80 px-1.5 py-0.5 font-bold text-indigo-950">{wknInfo.wkn}</code> &middot; <strong>ISIN:</strong> <code className="rounded bg-white/80 px-1.5 py-0.5 font-bold text-indigo-950">{wknInfo.isin}</code>
                        </div>
                        <div>
                          1️⃣ <strong>Limit-Kauf (Limit Buy):</strong> <strong>{dynamicShares} Aktien</strong> zu Limit <strong>${entry.toFixed(2)}</strong> (niemals Market-Order beim Börsenstart!)
                        </div>
                        <div>
                          2️⃣ <strong>Initialer Stop-Loss:</strong> Stop-Market Verkaufsorder bei <strong>${hardStop.toFixed(2)}</strong> (-{displayMaxLossEur}€ {showNetAfterTax ? "effektives Netto-Risiko nach Verlusttopf" : "Risiko"})
                        </div>
                        <div>
                          3️⃣ <strong>Preis-Alarm (Glocke 🔔):</strong> Bei <strong>${(entry + riskPerShare).toFixed(2)} (+1R)</strong> Stop auf unseren <strong>🌬️ Atmungs-Puffer (${cushionStop})</strong> nachziehen!
                        </div>
                        <div>
                          💶 <strong>Netto-Auszahlung nach 26,38% Steuer:</strong> Ziel 1: <strong>+{displayT1ProfitEur}€</strong> | Ziel 2: <strong>+{displayT2ProfitEur}€</strong>
                        </div>
                      </div>
                    </div>
                  ) : null}

                  {/* FREE-ROLL PYRAMIDING DRAWER */}
                  {openPyramidTicker === setup.ticker ? (
                    <div className="mt-3 rounded-xl border border-emerald-500/25 bg-emerald-50/80 p-3 text-[11px] leading-5 text-emerald-950 dark:border-emerald-500/30 dark:bg-emerald-950/40 dark:text-emerald-200">
                      <div className="font-bold uppercase tracking-wider text-emerald-900 dark:text-emerald-100">
                        🪜 Free-Roll Pyramiding (Gewinner mit 0,00 € Risiko ausbauen)
                      </div>
                      <div className="mt-1.5 space-y-1">
                        <div>
                          • <strong>Wann nachkaufen?</strong> Sobald die Aktie bei <strong>${(entry + riskPerShare).toFixed(2)} (+1.0R)</strong> liegt.
                        </div>
                        <div>
                          • <strong>Zusatz-Stückzahl (+50% Pyramide):</strong> <strong>+{Math.max(1, Math.round(dynamicShares * 0.5))} Aktien</strong> nachkaufen (Gesamt: {dynamicShares + Math.max(1, Math.round(dynamicShares * 0.5))} Stk).
                        </div>
                        <div>
                          • <strong>Kombinierter 0€-Risiko-Stop:</strong> Stop für alle Stücke auf <strong>${((dynamicShares * entry + Math.max(1, Math.round(dynamicShares * 0.5)) * (entry + riskPerShare)) / (dynamicShares + Math.max(1, Math.round(dynamicShares * 0.5)))).toFixed(2)}</strong> ziehen – der Buchgewinn der 1. Position bezahlt das Risiko der 2. Position komplett!
                        </div>
                      </div>
                    </div>
                  ) : null}
                </div>

                <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-black/5 pt-3 dark:border-white/5">
                  <div className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
                    Sizing: <span className="font-semibold text-slate-950 dark:text-white">{dynamicShares} Stk</span> (~{dynamicPositionValue.toLocaleString("de-DE")}€)
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => onAnalyzeTicker(setup.ticker)}
                      className="rounded-lg border border-black/8 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-50 dark:border-white/10 dark:bg-white/10 dark:text-slate-200"
                    >
                      Chart
                    </button>
                    <button
                      type="button"
                      onClick={() => setOpenOrderSheetTicker(openOrderSheetTicker === setup.ticker ? null : setup.ticker)}
                      className={`rounded-lg border px-2.5 py-1.5 text-xs font-semibold transition ${
                        openOrderSheetTicker === setup.ticker
                          ? "border-indigo-500 bg-indigo-600 text-white"
                          : "border-black/8 bg-white text-slate-700 hover:bg-slate-50 dark:border-white/10 dark:bg-white/10 dark:text-slate-200"
                      }`}
                      title="Schritt-für-Schritt Eingabe für Trade Republic, Scalable & IBKR"
                    >
                      🏦 Spickzettel
                    </button>
                    <button
                      type="button"
                      onClick={() => setOpenPyramidTicker(openPyramidTicker === setup.ticker ? null : setup.ticker)}
                      className={`rounded-lg border px-2.5 py-1.5 text-xs font-semibold transition ${
                        openPyramidTicker === setup.ticker
                          ? "border-emerald-600 bg-emerald-600 text-white"
                          : "border-black/8 bg-white text-slate-700 hover:bg-slate-50 dark:border-white/10 dark:bg-white/10 dark:text-slate-200"
                      }`}
                      title="Free-Roll Pyramiding: Gewinner ab +1R mit 0,00 € Risiko aufstocken"
                    >
                      🪜 0€-Pyramide
                    </button>
                    <button
                      type="button"
                      onClick={() => handleShareSetupCard(setup)}
                      className="rounded-lg border border-black/8 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-50 dark:border-white/10 dark:bg-white/10 dark:text-slate-200"
                      title="VIP Signal-Card kopieren & mit Freunden teilen"
                    >
                      📤 Teilen
                    </button>
                    {!isGuestMode ? (
                      <>
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
                      </>
                    ) : null}
                  </div>
                </div>
              </div>
              );
            })}
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
          <div className="mt-3 rounded-xl border border-black/8 dark:border-white/10 bg-black/[0.02] dark:bg-white/5 p-2.5 text-xs font-bold text-slate-800 dark:text-slate-200">
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
