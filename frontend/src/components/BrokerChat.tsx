import React, { useEffect, useRef, useState } from "react";
import { X, Send, Bot, User, ChevronUp, ChevronDown } from "lucide-react";

interface Message {
  role: "user" | "oracle";
  content: string;
}

interface BrokerChatProps {
  currentTicker?: string | string[];
  activeTab?: string;
  contextSymbols?: string[];
  portfolioSnapshot?: any;
  liveQuotes?: Record<string, any>;
  signalScore?: any;
  morningBriefSummary?: any;
  learningSummary?: any;
  onAnalyzeTicker?: (ticker: string) => void;
  onOpenTab?: (tab: string) => void;
  onOpenHealth?: () => void;
  isInline?: boolean;
  initialMessage?: string;
  onClose?: () => void;
  isOpen?: boolean;
  setIsOpen?: (open: boolean) => void;
}

export default function BrokerChat({
  currentTicker,
  activeTab,
  contextSymbols,
  portfolioSnapshot,
  liveQuotes,
  signalScore,
  morningBriefSummary,
  learningSummary,
  onAnalyzeTicker,
  onOpenTab,
  onOpenHealth,
  isInline = false,
  initialMessage,
  onClose,
  isOpen: externalIsOpen,
  setIsOpen: externalSetIsOpen,
}: BrokerChatProps) {
  const [internalIsOpen, setInternalIsOpen] = useState(false);
  const isOpen = externalIsOpen !== undefined ? externalIsOpen : internalIsOpen;
  const setIsOpen =
    externalSetIsOpen !== undefined ? externalSetIsOpen : setInternalIsOpen;

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [mobileSheetMode, setMobileSheetMode] = useState<"peek" | "full">("peek");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMessages([
      {
        role: "oracle",
        content:
          initialMessage ||
          "Hallo. Ich bin dein Broker Freund Desk. Ich kann dir Portfolio, Live-Kurse, Morning Brief, Signale, Risiken und konkrete Trigger erklaeren. Frag mich z.B. warum ein Setup wichtig ist, was du beobachten sollst oder wo dein Risiko liegt.",
      },
    ]);
  }, [initialMessage]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (isOpen) {
      setMobileSheetMode("peek");
    }
  }, [isOpen]);

  useEffect(() => {
    if (isInline || !isOpen || typeof window === "undefined") return;
    const isDesktop = window.matchMedia("(min-width: 768px)").matches;
    if (isDesktop) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isInline, isOpen]);

  const submitMessage = async (rawMessage: string) => {
    const userMsg = rawMessage.trim();
    if (!userMsg || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setLoading(true);

    try {
      const response = await fetch("/api/oracle/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userMsg,
          context_ticker: Array.isArray(currentTicker)
            ? currentTicker.join(",")
            : currentTicker,
          active_tab: activeTab,
          context_symbols: contextSymbols,
          portfolio_snapshot: portfolioSnapshot,
          live_quotes: liveQuotes,
          signal_score: signalScore,
          morning_brief_summary: morningBriefSummary,
          learning_summary: learningSummary,
        }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setMessages((prev) => [
        ...prev,
        { role: "oracle", content: data.response ?? "Keine Antwort erhalten." },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "oracle",
          content:
            "Verbindung kurz unterbrochen. Versuch es direkt noch einmal.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    await submitMessage(input);
  };

  const latestOracleMessage =
    [...messages].reverse().find((message) => message.role === "oracle")?.content ||
    "Broker Freund analysiert gerade Markt, Signale und dein Setup.";

  const topSignalTicker =
    signalScore?.top_ideas?.find((item: any) => item?.ticker || item?.symbol)?.ticker ||
    signalScore?.top_ideas?.find((item: any) => item?.ticker || item?.symbol)?.symbol ||
    contextSymbols?.[0] ||
    (liveQuotes ? Object.keys(liveQuotes)[0] : "");
  const primaryTicker = Array.isArray(currentTicker) ? currentTicker[0] : currentTicker || topSignalTicker;
  const setupCount = Array.isArray(morningBriefSummary?.trade_setups)
    ? morningBriefSummary.trade_setups.length
    : 0;
  const congressCount = Array.isArray(morningBriefSummary?.congress_watch)
    ? morningBriefSummary.congress_watch.length
    : 0;
  const eventPingCount = Array.isArray(morningBriefSummary?.event_pings)
    ? morningBriefSummary.event_pings.length
    : 0;
  const earningsCount = Array.isArray(morningBriefSummary?.earnings_calendar)
    ? morningBriefSummary.earnings_calendar.length
    : 0;
  const productCatalystCount = Array.isArray(morningBriefSummary?.product_catalysts)
    ? morningBriefSummary.product_catalysts.length
    : 0;
  const moverCount =
    (morningBriefSummary?.market_movers?.gainers?.length || 0) +
    (morningBriefSummary?.market_movers?.losers?.length || 0);
  const forecastCount = learningSummary?.summary?.forecasts || learningSummary?.summary?.total || 0;
  const evaluatedCount = learningSummary?.summary?.evaluated || 0;

  const contextStats = [
    { label: "Setups", value: setupCount, active: setupCount > 0 },
    { label: "Congress", value: congressCount, active: congressCount > 0 },
    { label: "Events", value: eventPingCount, active: eventPingCount > 0 },
    { label: "Earnings", value: earningsCount, active: earningsCount > 0 },
    { label: "Products", value: productCatalystCount, active: productCatalystCount > 0 },
    { label: "Movers", value: moverCount, active: moverCount > 0 },
    { label: "Learning", value: evaluatedCount || forecastCount, active: Boolean(evaluatedCount || forecastCount) },
  ];

  const deskCommands = [
    {
      label: "Markets",
      detail: "Mover / Explorer",
      disabled: !onOpenTab || activeTab === "discovery",
      run: () => onOpenTab?.("discovery"),
    },
    {
      label: primaryTicker ? `${String(primaryTicker).toUpperCase()} Check` : "Analyze",
      detail: primaryTicker ? "Dossier + Chart" : "Suche starten",
      disabled: primaryTicker ? !onAnalyzeTicker : !onOpenTab,
      run: () => {
        if (primaryTicker && onAnalyzeTicker) {
          onAnalyzeTicker(String(primaryTicker).toUpperCase());
          return;
        }
        onOpenTab?.("analyze");
      },
    },
    {
      label: "Portfolio",
      detail: "Rendite / Risiko",
      disabled: !onOpenTab || activeTab === "portfolio",
      run: () => onOpenTab?.("portfolio"),
    },
    {
      label: "Briefing",
      detail: `${setupCount} Setups / ${eventPingCount} Events`,
      disabled: loading,
      run: () => void submitMessage("Erklaere mir das aktuelle Briefing: wichtigste Setups, Risiken, Datenluecken und was ich anklicken soll."),
    },
    {
      label: "Health",
      detail: "Scheduler / Daten",
      disabled: !onOpenHealth,
      run: () => onOpenHealth?.(),
    },
  ];

  const quickActions = [
    activeTab === "discovery"
      ? "Markets: Welche Karte soll ich zuerst pruefen?"
      : activeTab === "portfolio"
        ? "Portfolio: groesstes Risiko und naechste Aktion?"
        : activeTab === "analyze"
          ? "Analyse: Was ist der wichtigste Punkt?"
          : "Dashboard: Was ist heute wichtig?",
    currentTicker
      ? `Trigger fuer ${Array.isArray(currentTicker) ? currentTicker[0] : currentTicker}?`
      : activeTab === "discovery"
        ? "Beste Market-Idee und warum?"
        : activeTab === "portfolio"
          ? "Rendite seit Kauf pruefen?"
          : "Wichtigstes Setup heute?",
    currentTicker
      ? `Dossier ${Array.isArray(currentTicker) ? currentTicker[0] : currentTicker}: Umsatz, Margen, Bewertung?`
      : "Welche Prognose lag zuletzt daneben?",
    activeTab === "discovery"
      ? "Top Gewinner/Verlierer mit echtem Grund?"
      : activeTab === "portfolio"
        ? "Welche Holding ist heute gefaehrdet?"
        : "Welche News/Earnings sind wirklich wichtig?",
    "Warum ist das Briefing so gerankt?",
    "Welche Daten fehlen gerade?",
    "Welche Learnings verbessern heute die Signale?",
    "Wo ist heute das groesste Risiko?",
    "Welche Hedge-Idee ist heute am sinnvollsten?",
    activeTab === "discovery" ? "Erklaere mir Market Explorer vs Top Movers." : "Welche App-Aktion soll ich als naechstes machen?",
    activeTab === "portfolio" ? "Welche Position sollte ich wegen Rendite seit Kauf pruefen?" : "Welche Daten fehlen fuer eine saubere Entscheidung?",
  ];
  const visibleQuickActions = quickActions.slice(0, 6);
  const tabName =
    activeTab === "discovery"
      ? "Markets"
      : activeTab === "analyze"
        ? "Analyze"
        : activeTab === "portfolio"
          ? "Portfolio"
          : "Dashboard";
  const activeDataCount = contextStats.filter((item) => item.active).length;
  const dataReadiness =
    activeDataCount >= 4
      ? "Datenlage stark"
      : activeDataCount >= 2
        ? "Datenlage brauchbar"
        : "Datenlage duenn";
  const assistantFocus =
    activeTab === "discovery"
      ? "Ich kann Scanner-Karten priorisieren, Gewinner/Verlierer einordnen und sagen, welche Analyse sich lohnt."
      : activeTab === "analyze"
        ? "Ich kann Dossier, Chart, Umsatz, Bewertung, Trigger und Invalidierung Schritt fuer Schritt einordnen."
        : activeTab === "portfolio"
          ? "Ich kann Rendite seit Kauf, Positionsrisiko, Klumpenrisiken und naechste Watch-Aktionen erklaeren."
          : "Ich kann Morning Brief, Weltkarte, Setups, Events und Datenluecken zu einem Tagesplan verdichten.";
  const tabGuide =
    activeTab === "discovery"
      ? {
          title: "Markets Desk",
          steps: [
            "Erst Top Movers lesen: Gewinner/Verlierer nur mit Volumen, News oder Event bestaetigen.",
            "Dann Market Explorer nutzen: Signals, Screener, ETFs und Internals getrennt pruefen.",
            "Analyse erst starten, wenn Trigger, Risiko und Datenquelle klar sind.",
          ],
          prompt: "Fuehre mich durch Markets und sag mir, welche Karte ich jetzt als erstes pruefen soll.",
        }
      : activeTab === "analyze"
        ? {
            title: "Analyze Desk",
            steps: [
              "Dossier zuerst: Umsatz, Margen, Bewertung, Guidance und Risiken einordnen.",
              "Dann Chart: Trend, SMA, RSI, Volume und Kursverlauf gegen die These pruefen.",
              "Zum Schluss Trigger/Invalidierung definieren, nicht nur Score lesen.",
            ],
            prompt: currentTicker
              ? `Erklaere mir ${Array.isArray(currentTicker) ? currentTicker[0] : currentTicker} Schritt fuer Schritt: Dossier, Chart, Risiko, Trigger.`
              : "Erklaere mir, wie ich eine Analyse sauber lese.",
          }
        : activeTab === "portfolio"
          ? {
              title: "Portfolio Desk",
              steps: [
                "Rendite seit Kauf und Positionsgroesse zuerst pruefen.",
                "Dann Risiko-Cluster: gleiche Sektoren, gleiche Makro-Abhaengigkeit, gleiche Event-Gefahr.",
                "Am Ende konkrete Watchlist: halten, reduzieren, beobachten, nachkaufen nur mit Trigger.",
              ],
              prompt: "Pruefe mein Portfolio: Rendite seit Kauf, groesste Risiken und naechste sinnvolle Aktion.",
            }
          : {
              title: "Dashboard Desk",
              steps: [
                "Regime und World Map zuerst lesen: Risk-on/off/mixed bestimmt Positionsgroesse.",
                "Morning Brief nach Now/Next/Avoid und Event-Pings sortieren.",
                "Nur Setups weiterverfolgen, die News, Chart und Datenvertrauen gemeinsam bestaetigen.",
              ],
              prompt: "Erklaere mir das Dashboard und was ich heute wirklich beachten soll.",
            };

  const deskActions = [
    primaryTicker && onAnalyzeTicker
      ? {
          label: `${String(primaryTicker).toUpperCase()} analysieren`,
          action: () => onAnalyzeTicker(String(primaryTicker).toUpperCase()),
          tone: "bg-[var(--accent)] text-white border-[var(--accent)]",
        }
      : null,
    onOpenTab && activeTab !== "discovery"
      ? {
          label: "Markets oeffnen",
          action: () => {
            onOpenTab("discovery");
            if (!isInline) setMobileSheetMode("peek");
          },
          tone: "bg-white text-slate-700 border-black/8",
        }
      : null,
    onOpenTab && activeTab !== "portfolio"
      ? {
          label: "Portfolio pruefen",
          action: () => {
            onOpenTab("portfolio");
            if (!isInline) setMobileSheetMode("peek");
          },
          tone: "bg-white text-slate-700 border-black/8",
        }
      : null,
    onOpenTab && activeTab !== "analyze"
      ? {
          label: "Analyze Desk",
          action: () => {
            onOpenTab("analyze");
            if (!isInline) setMobileSheetMode("peek");
          },
          tone: "bg-white text-slate-700 border-black/8",
        }
      : null,
  ].filter(Boolean) as Array<{ label: string; action: () => void; tone: string }>;

  const contextLabel = currentTicker
    ? Array.isArray(currentTicker)
      ? currentTicker.join(", ")
      : currentTicker
    : activeTab
      ? `${activeTab} context`
    : "Marktueberblick";

  const activeContextStats = contextStats.filter((item) => item.active);
  const portfolioReturnPct = portfolioSnapshot?.summary?.return_since_buy_pct;
  const contextReadout = [
    `Tab: ${tabName}`,
    primaryTicker ? `Fokus: ${String(primaryTicker).toUpperCase()}` : null,
    portfolioSnapshot?.summary?.num_holdings
      ? `Portfolio: ${portfolioSnapshot.summary.num_holdings} Holdings${
          Number.isFinite(Number(portfolioReturnPct))
            ? ` / ${Number(portfolioReturnPct).toFixed(2)}% seit Kauf`
            : ""
        }`
      : null,
    morningBriefSummary?.macro_regime ? `Regime: ${morningBriefSummary.macro_regime}` : null,
    activeContextStats.length
      ? `Daten: ${activeContextStats.slice(0, 4).map((item) => `${item.label} ${item.value}`).join(" / ")}`
      : "Daten: Live-Kontext aktiv",
  ].filter(Boolean);

  const peekCards = [
    {
      label: "Setup",
      value: currentTicker ? "Fokus-Setup" : "Markt-Scan",
      detail: currentTicker
        ? `Priorisiere ${contextLabel} nur bei bestaetigtem Trigger.`
        : "Suche nach frischem Trigger, bevor du Momentum jagst.",
      tone:
        "border-emerald-200/80 bg-[linear-gradient(180deg,rgba(16,185,129,0.08),rgba(255,255,255,0.92))]",
    },
    {
      label: "Risk",
      value: "Taktisch bleiben",
      detail:
        "Groesse klein halten, solange Newsflow oder Open-Richtung nicht sauber bestaetigt sind.",
      tone:
        "border-amber-200/80 bg-[linear-gradient(180deg,rgba(245,158,11,0.09),rgba(255,255,255,0.92))]",
    },
    {
      label: "Hedge",
      value: "Bereithalten",
      detail: currentTicker
        ? `Pruefe Hedge-Ideen gegen ${contextLabel}, falls das Setup kippt.`
        : "GLD, UUP oder TLT nur dann aktivieren, wenn Risiko wirklich hochzieht.",
      tone:
        "border-sky-200/80 bg-[linear-gradient(180deg,rgba(14,165,233,0.08),rgba(255,255,255,0.92))]",
    },
  ];

  const chatContent = (
    <div
      className={`${
        isInline
          ? "flex h-full flex-col"
          : `surface-panel fixed inset-x-2 top-auto z-50 flex w-auto max-w-[calc(100vw-1rem)] flex-col overflow-hidden rounded-[1.75rem] border border-black/8 bg-[rgba(250,248,244,0.98)] shadow-[0_-18px_48px_rgba(17,24,39,0.18)] backdrop-blur-3xl transition-[height,bottom] duration-300 ${mobileSheetMode === "full" ? "bottom-[calc(0.5rem+env(safe-area-inset-bottom))] h-[min(86dvh,56rem)]" : "bottom-[calc(5.15rem+env(safe-area-inset-bottom))] h-[min(47dvh,29rem)]"} md:inset-y-0 md:right-0 md:left-auto md:bottom-0 md:top-0 md:h-auto md:w-full md:max-w-md md:rounded-none md:rounded-l-[2rem] md:border-l md:border-t-0 md:shadow-[-20px_0_50px_rgba(17,24,39,0.12)] xl:max-w-[28rem] 2xl:max-w-[31rem]`
      }`}
    >
      {!isInline && (
        <div className="flex justify-center pt-2 md:hidden">
          <button
            type="button"
            onClick={() => setMobileSheetMode((prev) => (prev === "peek" ? "full" : "peek"))}
            className="flex items-center gap-2 rounded-full border border-black/8 bg-white/80 px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500"
            aria-label={mobileSheetMode === "peek" ? "Broker Desk erweitern" : "Broker Desk einklappen"}
          >
            <span className="h-1.5 w-10 rounded-full bg-slate-300" />
            {mobileSheetMode === "peek" ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>
      )}
      <div
        className={`flex items-center justify-between border-b border-black/8 bg-[linear-gradient(90deg,rgba(15,118,110,0.08),transparent)] p-4 sm:p-6 ${isInline ? "px-0 pt-0" : ""}`}
      >
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-[1rem] border border-[var(--accent)]/15 bg-[var(--accent-soft)] text-[var(--accent)]">
            <Bot size={22} />
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-900">Broker Freund Desk</h3>
            <div className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
              <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
                Live-Kontext
              </span>
            </div>
          </div>
        </div>
        {!isInline && (
          <button
            onClick={() => {
              setIsOpen(false);
              onClose?.();
            }}
            className="rounded-lg p-2 text-slate-500 transition-all hover:bg-black/[0.04] hover:text-slate-900"
          >
            <X size={20} />
          </button>
        )}
      </div>

      <div
        className={`flex-1 overflow-y-auto ${isInline ? "px-0 py-4" : "p-4 sm:p-6"} space-y-6 scrollbar-hide`}
      >
        {!isInline && mobileSheetMode === "peek" ? (
          <div className="space-y-4 md:hidden">
            <div className="rounded-[1.3rem] border border-black/8 bg-white/82 p-4">
              <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                Desk-Snapshot
              </div>
              <div className="mt-3 text-sm leading-6 text-slate-700">
                {latestOracleMessage}
              </div>
              <div className="mt-3 rounded-[1rem] border border-[var(--accent)]/14 bg-[var(--accent-soft)] px-3 py-2 text-xs font-semibold leading-5 text-[var(--accent)]">
                {assistantFocus}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {contextStats.slice(0, 6).map((item) => (
                <div
                  key={item.label}
                  className={`rounded-[1rem] border px-3 py-2 ${
                    item.active
                      ? "border-[var(--accent)]/20 bg-[var(--accent-soft)] text-[var(--accent)]"
                      : "border-black/8 bg-white/72 text-slate-400"
                  }`}
                >
                  <div className="text-[9px] font-extrabold uppercase tracking-[0.14em]">
                    {item.label}
                  </div>
                  <div className="mt-1 text-sm font-black">{item.value || 0}</div>
                </div>
              ))}
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-[1.15rem] border border-black/8 bg-white/76 p-3">
                <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                  Kontext
                </div>
                <div className="mt-2 text-sm font-bold text-slate-900">
                  {tabName}
                </div>
              </div>
              <div className="rounded-[1.15rem] border border-black/8 bg-white/76 p-3">
                <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                  Daten
                </div>
                <div className="mt-2 text-sm font-bold text-slate-900">
                  {dataReadiness}
                </div>
              </div>
              <div className="rounded-[1.15rem] border border-black/8 bg-white/76 p-3">
                <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                  Naechster Schritt
                </div>
                <div className="mt-2 text-sm font-bold text-slate-900">
                  Hochziehen oder Prompt waehlen
                </div>
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              {peekCards.map((card) => (
                <div
                  key={card.label}
                  className={`rounded-[1.2rem] border p-3 ${card.tone}`}
                >
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                    {card.label}
                  </div>
                  <div className="mt-2 text-sm font-bold text-slate-900">
                    {card.value}
                  </div>
                  <div className="mt-2 text-[12px] leading-5 text-slate-600">
                    {card.detail}
                  </div>
                </div>
              ))}
            </div>
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                {primaryTicker && onAnalyzeTicker ? (
                  <button
                    type="button"
                    onClick={() => {
                      setMobileSheetMode("full");
                      onAnalyzeTicker(String(primaryTicker).toUpperCase());
                    }}
                    className="rounded-[1.1rem] bg-[var(--accent)] px-4 py-3 text-left text-xs font-extrabold uppercase tracking-[0.14em] text-white"
                  >
                    {String(primaryTicker).toUpperCase()} analysieren
                  </button>
                ) : null}
                {onOpenTab ? (
                  <button
                    type="button"
                    onClick={() => {
                      setMobileSheetMode("full");
                      onOpenTab(activeTab === "discovery" ? "analyze" : "discovery");
                      if (activeTab !== "discovery") setMobileSheetMode("peek");
                    }}
                    className="rounded-[1.1rem] border border-black/8 bg-white/78 px-4 py-3 text-left text-xs font-extrabold uppercase tracking-[0.14em] text-slate-700"
                  >
                    {activeTab === "discovery" ? "Analyze oeffnen" : "Markets oeffnen"}
                  </button>
                ) : null}
              </div>
              {quickActions.map((action) => (
                <button
                  key={action}
                  type="button"
                  onClick={() => {
                    setMobileSheetMode("full");
                    void submitMessage(action);
                  }}
                  className="block w-full rounded-[1.1rem] border border-black/8 bg-white/78 px-4 py-3 text-left text-sm font-semibold text-slate-700 transition-colors hover:bg-[var(--accent-soft)]"
                >
                  {action}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            <div className="rounded-[1.2rem] border border-black/8 bg-white/76 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                    Kontextspeicher
                  </div>
                  <div className="mt-1 text-sm font-black text-slate-900">
                    {contextLabel}
                  </div>
                </div>
                <span className="rounded-full border border-emerald-500/18 bg-emerald-500/10 px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-emerald-700">
                  {dataReadiness}
                </span>
              </div>
              <div className="mt-3 rounded-[1rem] border border-[var(--accent)]/12 bg-[var(--accent-soft)] px-3 py-2 text-xs font-semibold leading-5 text-[var(--accent)]">
                {assistantFocus}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {contextReadout.map((item) => (
                  <span
                    key={String(item)}
                    className="rounded-full border border-black/8 bg-white/82 px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500"
                  >
                    {item}
                  </span>
                ))}
              </div>
            </div>
            <div className="rounded-[1.2rem] border border-[var(--accent)]/14 bg-[linear-gradient(180deg,rgba(15,118,110,0.07),rgba(255,255,255,0.86))] p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-[var(--accent)]">
                    Aktueller Plan
                  </div>
                  <div className="mt-1 text-sm font-black text-slate-900">
                    {tabGuide.title}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => void submitMessage(tabGuide.prompt)}
                  disabled={loading}
                  className="rounded-full border border-[var(--accent)]/20 bg-white/80 px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.14em] text-[var(--accent)] disabled:opacity-50"
                >
                  Seite erklaeren
                </button>
              </div>
              <div className="mt-3 grid gap-2">
                {tabGuide.steps.map((step, index) => (
                  <div
                    key={step}
                    className="flex gap-2 rounded-[0.9rem] border border-black/6 bg-white/62 px-3 py-2 text-xs leading-5 text-slate-600"
                  >
                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-[10px] font-black text-white">
                      {index + 1}
                    </span>
                    <span>{step}</span>
                  </div>
                ))}
              </div>
            </div>
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`flex max-w-[85%] gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}
                >
                  <div
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border ${
                      msg.role === "user"
                        ? "border-slate-300 bg-slate-200/70"
                        : "border-[var(--accent)]/15 bg-[var(--accent-soft)]"
                    }`}
                  >
                    {msg.role === "user" ? (
                      <User size={16} className="text-slate-700" />
                    ) : (
                      <Bot size={16} className="text-[var(--accent)]" />
                    )}
                  </div>
                  <div
                    className={`whitespace-pre-line rounded-2xl border p-4 text-sm leading-relaxed ${
                      msg.role === "user"
                        ? "border-slate-300 bg-slate-100 text-slate-800"
                        : "border-black/8 bg-white/80 text-slate-700"
                    }`}
                  >
                    {msg.content}
                  </div>
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex justify-start">
                <div className="flex items-center gap-2 rounded-2xl border border-black/8 bg-white/80 p-4">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--accent)]"></span>
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--accent)] [animation-delay:0.2s]"></span>
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--accent)] [animation-delay:0.4s]"></span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      <div
        className={`${isInline ? "border-t border-black/8 pt-4" : "border-t border-black/8 bg-white/60 p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] sm:p-6 sm:pb-[calc(1.5rem+env(safe-area-inset-bottom))] md:pb-6"}`}
      >
        {currentTicker && !isInline && (
          <div className="mb-4 flex items-center gap-2">
            <span className="rounded-md border border-[var(--accent)]/15 bg-[var(--accent-soft)] px-2 py-1 text-[10px] font-bold uppercase tracking-widest text-[var(--accent)]">
              Kontext: {currentTicker}
            </span>
          </div>
        )}
        {!isInline && mobileSheetMode === "full" && deskActions.length ? (
          <div className="mb-3 flex gap-2 overflow-x-auto pb-1 no-scrollbar">
            {deskActions.map((item) => (
              <button
                key={item.label}
                type="button"
                onClick={item.action}
                className={`shrink-0 rounded-xl border px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.14em] ${item.tone}`}
              >
                {item.label}
              </button>
            ))}
          </div>
        ) : null}
        {(isInline || mobileSheetMode === "full") && (
          <div className="mb-3 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-black/8 bg-white/70 px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                {tabName} Desk
              </span>
              {primaryTicker ? (
                <span className="rounded-full border border-[var(--accent)]/18 bg-[var(--accent-soft)] px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-[var(--accent)]">
                  Fokus {String(primaryTicker).toUpperCase()}
                </span>
              ) : null}
              {portfolioSnapshot?.summary?.num_holdings ? (
                <span className="rounded-full border border-black/8 bg-white/70 px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                  {portfolioSnapshot.summary.num_holdings} Holdings
                </span>
              ) : null}
              {morningBriefSummary?.macro_regime ? (
                <span className="rounded-full border border-black/8 bg-white/70 px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                  {morningBriefSummary.macro_regime}
                </span>
              ) : null}
              {contextStats.filter((item) => item.active).slice(0, 5).map((item) => (
                <span
                  key={item.label}
                  className="rounded-full border border-[var(--accent)]/18 bg-[var(--accent-soft)] px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-[var(--accent)]"
                >
                  {item.label} {item.value}
                </span>
              ))}
            </div>
            <div className="flex gap-2 overflow-x-auto pb-1 no-scrollbar">
              {deskCommands.map((command) => (
                <button
                  key={command.label}
                  type="button"
                  onClick={command.run}
                  disabled={command.disabled}
                  className="shrink-0 rounded-xl border border-[var(--accent)]/20 bg-[var(--accent-soft)] px-3 py-2 text-left text-[11px] font-extrabold uppercase tracking-[0.12em] text-[var(--accent)] transition-colors hover:bg-white disabled:border-black/8 disabled:bg-white/60 disabled:text-slate-400"
                >
                  <span className="block">{command.label}</span>
                  <span className="mt-0.5 block text-[9px] font-bold tracking-[0.1em] text-slate-500">
                    {command.detail}
                  </span>
                </button>
              ))}
              {visibleQuickActions.map((action) => (
                <button
                  key={action}
                  type="button"
                  onClick={() => void submitMessage(action)}
                  disabled={loading}
                  className="shrink-0 rounded-xl border border-black/8 bg-white/82 px-3 py-2 text-left text-[11px] font-bold text-slate-700 transition-colors hover:border-[var(--accent)]/25 hover:bg-[var(--accent-soft)] disabled:opacity-50"
                >
                  {action}
                </button>
              ))}
            </div>
          </div>
        )}
        {!isInline && mobileSheetMode === "peek" ? (
          <div className="grid gap-2 md:hidden">
            <button
              type="button"
              onClick={() => setMobileSheetMode("full")}
              className="w-full rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-700 transition-colors hover:bg-[var(--accent-soft)]"
            >
              Vollstaendige Desk-Ansicht oeffnen
            </button>
            {primaryTicker && onAnalyzeTicker ? (
              <button
                type="button"
                onClick={() => onAnalyzeTicker(String(primaryTicker).toUpperCase())}
                className="w-full rounded-xl bg-[var(--accent)] px-4 py-3 text-sm font-extrabold uppercase tracking-[0.14em] text-white"
              >
                {String(primaryTicker).toUpperCase()} analysieren
              </button>
            ) : null}
          </div>
        ) : (
          <div className="relative">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              placeholder="Frage nach Markt, Aktie, ETF oder Risiko..."
              className="w-full rounded-xl border border-black/8 bg-white py-3.5 pl-4 pr-12 text-sm text-slate-900 placeholder:text-slate-400 transition-all focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/20"
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || loading}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg bg-[var(--accent)] p-2 text-white transition-all hover:bg-[var(--accent-strong)] disabled:opacity-50"
            >
              <Send size={18} />
            </button>
          </div>
        )}
        {!isInline && (
          <p className="mt-4 text-center text-[10px] text-slate-500">
            Broker Freund Desk analysiert Live-Daten. Keine direkte Anlageberatung.
          </p>
        )}
      </div>
    </div>
  );

  if (isInline) return chatContent;

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className={`group fixed bottom-[calc(5.85rem+env(safe-area-inset-bottom))] right-3 z-40${isOpen ? " hidden" : ""} flex h-12 w-12 items-center justify-center rounded-[1.05rem] border border-white/65 bg-[linear-gradient(180deg,rgba(15,118,110,0.98),rgba(14,92,87,0.96))] px-0 text-white shadow-[0_18px_38px_rgba(15,118,110,0.22)] transition-all hover:scale-[1.01] hover:shadow-[0_28px_64px_rgba(15,118,110,0.3)] active:scale-[0.99] md:bottom-5 md:left-auto md:right-5 md:h-16 md:w-16 md:justify-center md:rounded-[1.45rem] md:px-0`}
        aria-label="Open Broker Freund Desk"
      >
        <div className="absolute inset-0 rounded-[1.45rem] bg-white/8 opacity-0 transition-opacity group-hover:opacity-100"></div>
        <div className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-[0.95rem] border border-white/16 bg-white/14 md:h-11 md:w-11 md:rounded-[1rem]">
          <Bot size={20} />
        </div>
        <div className="relative hidden min-w-0 pr-1 text-left">
          <div className="text-[9px] font-extrabold uppercase tracking-[0.18em] text-white/70">
            Broker Freund
          </div>
          <div className="truncate text-sm font-bold text-white">
            {isOpen ? "Desk Live" : "Open Desk"}
          </div>
        </div>
        <div className="relative hidden rounded-full border border-white/14 bg-white/10 px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-white/80">
          Desk
        </div>
        <div className="pointer-events-none absolute bottom-0 right-[calc(100%+12px)] hidden w-[15.5rem] rounded-[1.3rem] border border-white/18 bg-[linear-gradient(180deg,rgba(11,18,22,0.95),rgba(15,118,110,0.92))] px-4 py-3 text-left text-white opacity-0 shadow-[0_24px_54px_rgba(15,23,42,0.24)] transition-all duration-200 group-hover:translate-x-0 group-hover:opacity-100 lg:block lg:translate-x-2">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-white/65">
              Broker Freund
            </div>
            <span className="rounded-full bg-white/12 px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.14em] text-white/80">
              Desk
            </span>
          </div>
          <div className="mt-1 text-sm font-bold text-white">Open Desk</div>
          <div className="mt-1 text-[11px] leading-5 text-white/72">
            Signals, news, macro and crowd context without covering the workspace.
          </div>
        </div>
      </button>

      {isOpen ? (
        <>
          <button
            type="button"
            aria-label="Close broker desk backdrop"
            onClick={() => {
              setIsOpen(false);
              onClose?.();
            }}
            className="fixed inset-0 z-40 bg-black/12 backdrop-blur-[1px] md:hidden"
          />
          {chatContent}
        </>
      ) : null}
    </>
  );
}
