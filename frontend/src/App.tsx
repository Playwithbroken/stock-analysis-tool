import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { ComponentType, LazyExoticComponent } from "react";
import SearchBar, { normalizeTickerInput } from "./components/SearchBar";
import LoadingState from "./components/LoadingState";
import ErrorBoundary from "./components/ErrorBoundary";
import AdminHealthPanel from "./components/AdminHealthPanel";
import { usePortfolios } from "./hooks/usePortfolios";
import type { Holding, Portfolio } from "./hooks/usePortfolios";
import { CurrencyProvider, useCurrency } from "./context/CurrencyContext";
import { ThemeProvider, useTheme } from "./context/ThemeContext";
import useRealtimeFeed from "./hooks/useRealtimeFeed";
import { fetchJsonWithRetry } from "./lib/api";
import { normalizeGeoRegions } from "./lib/geoRegions";
import { localizeMarketRegime, normalizeGermanDisplayText } from "./lib/displayText";
import { getBriefLoadState, guardBriefForDecisions, isBriefDecisionCurrent } from "./lib/briefSafety";
import { Activity, ArrowDownRight, ArrowUpRight, Download, LockKeyhole, Moon, Smartphone, Sun } from "lucide-react";
import useInstallPrompt from "./hooks/useInstallPrompt";

const CHUNK_RELOAD_GUARD_KEY = "brokerfreund:chunk-reload-once";

function lazyWithChunkRetry<T extends ComponentType<any>>(
  loader: () => Promise<{ default: T }>,
): LazyExoticComponent<T> {
  return lazy(async () => {
    try {
      const mod = await loader();
      try {
        sessionStorage.removeItem(CHUNK_RELOAD_GUARD_KEY);
      } catch {
        // Ignore sessionStorage failures in hardened browsers.
      }
      return mod;
    } catch (error) {
      const message = String((error as { message?: string } | null)?.message ?? error ?? "");
      const isChunkError = /ChunkLoadError|Loading chunk|dynamically imported module|Failed to fetch/i.test(message);
      if (isChunkError) {
        let alreadyReloaded = false;
        try {
          alreadyReloaded = sessionStorage.getItem(CHUNK_RELOAD_GUARD_KEY) === "1";
          if (!alreadyReloaded) {
            sessionStorage.setItem(CHUNK_RELOAD_GUARD_KEY, "1");
            window.location.reload();
            await new Promise<never>(() => {});
          }
        } catch {
          window.location.reload();
          await new Promise<never>(() => {});
        }
      }
      throw error;
    }
  }) as LazyExoticComponent<T>;
}

const AnalysisResult = lazyWithChunkRetry(() => import("./components/AnalysisResult"));
const PortfolioView = lazyWithChunkRetry(() => import("./components/PortfolioView"));
const DiscoveryPanel = lazyWithChunkRetry(() => import("./components/DiscoveryPanel"));
const BrokerChat = lazyWithChunkRetry(() => import("./components/BrokerChat"));
const WorldMarketMap = lazyWithChunkRetry(() => import("./components/WorldMarketMap"));
const EdgeDashboardPanel = lazyWithChunkRetry(() => import("./components/EdgeDashboardPanel"));
const MorningBriefPanel = lazyWithChunkRetry(() => import("./components/MorningBriefPanel"));
const OnboardingWizard = lazyWithChunkRetry(() => import("./components/OnboardingWizard"));

interface AnalysisData {
  ticker: string;
  company_name: string;
  [key: string]: any;
}

interface TapeMover {
  symbol: string;
  price?: number | null;
  change?: number | null;
  label?: string;
  side: "winner" | "loser";
}

const normalizeTapeMover = (item: any, side: TapeMover["side"]): TapeMover | null => {
  const symbol = String(item?.ticker || item?.symbol || "").trim().toUpperCase();
  if (!symbol) return null;
  return {
    symbol,
    price: item?.price ?? item?.current_price ?? null,
    change: item?.change ?? item?.change_percent ?? item?.change_1d ?? null,
    label: item?.name || item?.label,
    side,
  };
};

const marketMoversToTape = (marketMovers: any, limit = 6): TapeMover[] => {
  const winners = Array.isArray(marketMovers?.gainers)
    ? marketMovers.gainers
        .slice(0, limit)
        .map((item: any) => normalizeTapeMover(item, "winner"))
        .filter(Boolean)
    : [];
  const losers = Array.isArray(marketMovers?.losers)
    ? marketMovers.losers
        .slice(0, limit)
        .map((item: any) => normalizeTapeMover(item, "loser"))
        .filter(Boolean)
    : [];
  return [...winners, ...losers] as TapeMover[];
};

interface AuthState {
  loading: boolean;
  authenticated: boolean;
  configured: boolean;
  profile: { display_name?: string; onboarding_done?: boolean } | null;
}

interface WatchlistSnapshot {
  items?: Array<{
    kind?: string;
    value?: string;
  }>;
}

type Tab = "dashboard" | "analyze" | "discovery" | "portfolio";
type MoversWindow = "1d" | "1w" | "1m";

const NAV_ITEMS: Array<{ id: Tab; label: string; short: string }> = [
  { id: "dashboard", label: "Dashboard", short: "Home" },
  { id: "analyze", label: "Analyzer", short: "Analyze" },
  { id: "discovery", label: "Markets", short: "Markets" },
  { id: "portfolio", label: "Portfolio", short: "Portfolio" },
];

function scheduleIdle(task: () => void, timeout = 1500) {
  const win = window as Window & {
    requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
    cancelIdleCallback?: (id: number) => void;
  };
  if (typeof win.requestIdleCallback === "function") {
    const id = win.requestIdleCallback(task, { timeout });
    return () => {
      if (typeof win.cancelIdleCallback === "function") {
        win.cancelIdleCallback(id);
      }
    };
  }
  const timer = window.setTimeout(task, Math.min(timeout, 1000));
  return () => window.clearTimeout(timer);
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function isPageHidden() {
  return document.visibilityState === "hidden";
}

function shouldReduceBackgroundWork() {
  const connection = (navigator as Navigator & {
    connection?: { saveData?: boolean; effectiveType?: string };
  }).connection;
  const effectiveType = String(connection?.effectiveType || "").toLowerCase();
  return Boolean(connection?.saveData) || /(^|-)2g$/.test(effectiveType);
}

let lazyScreensPreloadStarted = false;

function preloadLazyScreens() {
  if (lazyScreensPreloadStarted || shouldReduceBackgroundWork()) return;
  lazyScreensPreloadStarted = true;
  const loaders = [
    () => import("./components/AnalysisResult"),
    () => import("./components/WorldMarketMap"),
    () => import("./components/MorningBriefPanel"),
    () => import("./components/EdgeDashboardPanel"),
    () => import("./components/PortfolioView"),
    () => import("./components/DiscoveryPanel"),
    () => import("./components/BrokerChat"),
  ];
  loaders.forEach((loader, index) => {
    window.setTimeout(() => {
      if (isPageHidden()) return;
      void loader().catch(() => undefined);
    }, 450 * index);
  });
}

function formatTickerPrice(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return "...";
  if (Math.abs(value) >= 1000) return value.toFixed(0);
  if (Math.abs(value) >= 100) return value.toFixed(2);
  if (Math.abs(value) >= 1) return value.toFixed(2);
  return value.toFixed(4);
}

function formatTickerMove(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return null;
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function HeaderTickerChip({
  symbol,
  quote,
}: {
  symbol: string;
  quote: any;
}) {
  const { formatPrice } = useCurrency();
  const previousPriceRef = useRef<number | null>(null);
  const [priceDirection, setPriceDirection] = useState<"up" | "down" | null>(null);

  useEffect(() => {
    const nextPrice = typeof quote?.price === "number" ? quote.price : null;
    const prevPrice = previousPriceRef.current;
    if (nextPrice == null) return;
    if (prevPrice != null && prevPrice !== nextPrice) {
      setPriceDirection(nextPrice > prevPrice ? "up" : "down");
      const timer = window.setTimeout(() => setPriceDirection(null), 950);
      previousPriceRef.current = nextPrice;
      return () => window.clearTimeout(timer);
    }
    previousPriceRef.current = nextPrice;
  }, [quote?.price]);

  const move = quote?.change_1w;
  const moveTone = move != null && move < 0 ? "text-red-700" : "text-emerald-700";
  const priceTone =
    priceDirection === "up"
      ? "ticker-chip-flash-up"
      : priceDirection === "down"
        ? "ticker-chip-flash-down"
        : "";
  const ArrowIcon = priceDirection === "down" ? ArrowDownRight : ArrowUpRight;

  return (
    <div
      className={`rounded-full border border-black/8 bg-white/78 px-3 py-1.5 text-xs font-bold text-slate-700 transition-colors ${priceTone}`}
    >
      <span className="mr-2 uppercase text-slate-500">{symbol}</span>
      <span className="mr-2 inline-flex items-center gap-1 text-slate-900">
        {priceDirection ? (
          <ArrowIcon
            size={12}
            className={priceDirection === "up" ? "text-emerald-700" : "text-red-700"}
          />
        ) : null}
        {typeof quote?.price === "number" ? formatPrice(quote.price) : "..."}
      </span>
      {move != null ? (
        <span className={moveTone}>
          {formatTickerMove(move)}
        </span>
      ) : null}
    </div>
  );
}

function AnalyzerLoadingPanel({ ticker }: { ticker?: string }) {
  const label = ticker ? ticker.toUpperCase() : "Dossier";
  return (
    <section className="analyzer-loading-panel surface-panel rounded-[2rem] p-5 sm:p-7">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
            Analysis Desk
          </div>
          <h3 className="mt-2 text-2xl text-slate-900 sm:text-3xl">
            {label} wird aufgebaut
          </h3>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            Kursdaten, Fundamentaldaten, Suitability und Chart werden getrennt geladen, damit die App nicht leer wirkt.
          </p>
        </div>
        <div className="inline-flex items-center gap-2 rounded-full border border-[var(--accent)]/20 bg-[var(--accent-soft)] px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.16em] text-[var(--accent)]">
          <Activity size={14} className="animate-pulse" />
            Wird geladen
        </div>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="rounded-[1.5rem] border border-black/8 bg-white/68 p-4">
          <div className="h-48 rounded-[1.1rem] bg-[linear-gradient(90deg,rgba(15,23,42,0.05),rgba(15,118,110,0.10),rgba(15,23,42,0.05))] bg-[length:200%_100%] loading-pulse sm:h-64" />
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            {["Kursverlauf", "Risiko", "Trigger"].map((item) => (
              <div key={item} className="rounded-[1rem] border border-black/8 bg-white/70 p-3">
                <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">{item}</div>
                <div className="mt-3 h-3 w-3/4 rounded-full bg-slate-200 loading-pulse" />
                <div className="mt-2 h-3 w-1/2 rounded-full bg-slate-200 loading-pulse" />
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-[1.5rem] border border-black/8 bg-white/72 p-4">
          <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
            Ladeschritte
          </div>
          <div className="mt-4 space-y-3">
            {["Symbol auflösen", "Datenquelle prüfen", "Dossier berechnen", "Ansicht stabilisieren"].map((step, index) => (
              <div key={step} className="flex items-center gap-3 text-sm font-semibold text-slate-700">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--accent-soft)] text-[11px] font-black text-[var(--accent)]">
                  {index + 1}
                </span>
                {step}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function LoginScreen({
  configured,
  onLogin,
  status,
}: {
  configured: boolean;
  onLogin: (password: string, rememberDevice: boolean) => Promise<void>;
  status: string;
}) {
  const [password, setPassword] = useState("");
  const [rememberDevice, setRememberDevice] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!password.trim()) return;
    setSubmitting(true);
    try {
      await onLogin(password, rememberDevice);
      setPassword("");
    } catch {
      // The parent exposes the concrete login error below the form.
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[var(--bg-base)] px-4 py-10 text-[var(--text-primary)] sm:px-6">
      <div className="layout-shell max-w-[1680px]">
        <div className="surface-panel relative overflow-hidden rounded-[2.8rem] p-6 sm:p-8 lg:p-10">
          <div className="pointer-events-none absolute inset-x-0 top-0 h-40 bg-[radial-gradient(circle_at_top_left,rgba(15,118,110,0.12),transparent_58%)]" />
          <div className="pointer-events-none absolute bottom-0 right-0 h-56 w-56 rounded-full bg-[radial-gradient(circle,rgba(16,17,20,0.08),transparent_68%)]" />
          <div className="grid gap-8 lg:grid-cols-[1.15fr_0.85fr]">
            <div className="order-last space-y-6 lg:order-first">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#101114] text-white">
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l5-5 4 4 7-8" />
                </svg>
              </div>
              <div>
                <div className="text-[11px] font-extrabold uppercase tracking-[0.28em] text-slate-500">
                  Privater Arbeitsbereich
                </div>
                <h1 className="mt-3 max-w-3xl text-3xl leading-none text-slate-900 sm:text-5xl lg:text-6xl">
                  Marktinformationen, geschützt in deinem privaten Arbeitsbereich.
                </h1>
                <p className="mt-5 max-w-2xl text-base leading-7 text-slate-600">
                  Die App ist für den privaten Einzelbetrieb abgesichert: Zugangscode, geschützte API,
                  kontrollierte Herkunftsfreigaben und keine offenen Alarm-Endpunkte.
                </p>
              </div>
              <div className="grid gap-4 sm:grid-cols-3">
                {[
                  "API hinter Session-Cookie",
                  "Zugriffe auf erlaubte Domains begrenzt",
                  "Alarme und Einstellungen geschützt",
                ].map((item) => (
                  <div key={item} className="rounded-[1.6rem] border border-black/8 bg-white/75 p-4 text-sm font-semibold text-slate-700">
                    {item}
                  </div>
                ))}
              </div>
              <div className="grid gap-4 sm:grid-cols-3">
                {[
                  ["Signale zuerst", "Morning Briefing, Watchlist und Echtzeitdaten direkt im Startpfad."],
                  ["Privat", "Nur dein Arbeitsbereich, keine offene Mehrbenutzerfläche."],
                  ["Handlungsbereit", "Score, Paper-Trading und Sitzungslisten in einem Ablauf."],
                ].map(([title, body]) => (
                  <div
                    key={title}
                    className="rounded-[1.7rem] border border-black/8 bg-[rgba(255,255,255,0.76)] p-5"
                  >
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-slate-500">
                      {title}
                    </div>
                    <div className="mt-3 text-sm leading-6 text-slate-700">{body}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="order-first surface-strong rounded-[2.4rem] p-6 sm:p-8 lg:order-last">
              <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-white/50">
                Zugang
              </div>
              <div className="mt-4 text-3xl font-black text-white">
                Zugangscode eingeben
              </div>
              <p className="mt-3 text-sm leading-7 text-white/70">
                {configured
                  ? "Nur mit lokaler Session wird die App geladen."
                  : status.includes("automatisch erneut geprüft")
                    ? "Der Server startet noch. Die Verbindung wird im Hintergrund erneut geprüft."
                  : "Der Server braucht noch APP_ACCESS_PASSWORD und APP_SESSION_SECRET."}
              </p>
              <div className="mt-6 space-y-3">
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") submit();
                  }}
                  aria-label="6-stelliger Zugangscode"
                  className="login-password-input w-full rounded-[1.2rem] border px-4 py-3 text-sm font-semibold"
                  placeholder="6-stelliger Zugangscode"
                />
                <label className="flex items-center gap-2 rounded-[1rem] border border-white/12 bg-white/8 px-3 py-2 text-xs text-white/80">
                  <input
                    type="checkbox"
                    checked={rememberDevice}
                    onChange={(e) => setRememberDevice(e.target.checked)}
                    className="h-4 w-4 rounded border-white/30 bg-transparent"
                  />
                  Auf diesem Gerät angemeldet bleiben (7 Tage)
                </label>
                <button
                  onClick={submit}
                  disabled={submitting || !configured}
                  className="w-full rounded-[1.2rem] bg-white px-4 py-3 text-xs font-extrabold uppercase tracking-[0.18em] text-slate-900 disabled:opacity-50"
                >
                  {submitting ? "Zugang wird geprüft..." : "Entsperren"}
                </button>
              </div>
              <div className="mt-6 grid grid-cols-2 gap-3">
                <div className="rounded-[1.2rem] border border-white/10 bg-white/8 p-4">
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-white/45">
                    Zugangsmodell
                  </div>
                  <div className="mt-2 text-sm font-semibold text-white">Ein privater Zugangscode</div>
                </div>
                <div className="rounded-[1.2rem] border border-white/10 bg-white/8 p-4">
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-white/45">
                    Plattform
                  </div>
                  <div className="mt-2 text-sm font-semibold text-white">Für Web und Smartphone</div>
                </div>
              </div>
              {status ? (
                <div className="mt-4 text-sm text-white/75">
                  {status.includes("500")
                    ? "Keine Verbindung zum Server. Bitte den Backend-Status prüfen."
                    : status.includes("401") || status.includes("403")
                      ? "Der Zugangscode ist falsch. Bitte erneut versuchen."
                      : status}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function AppContent() {
  const ONBOARDING_DISMISSED_AT_KEY = "onboardingDismissedAt";
  const ONBOARDING_DISMISS_COOLDOWN_MS = 7 * 24 * 60 * 60 * 1000;
  const ONBOARDING_NUDGE_ENABLED = false;
  const { theme, setTheme } = useTheme();
  const toggleTheme = () => setTheme(theme === "dark" ? "premium-light" : "dark");
  const installPrompt = useInstallPrompt();
  const [activeTab, setActiveTab] = useState<Tab>(() => {
    return (localStorage.getItem("activeTab") as Tab) || "dashboard";
  });
  const [analysis, setAnalysis] = useState<AnalysisData | null>(() => {
    const saved = localStorage.getItem("lastAnalysis");
    return saved ? JSON.parse(saved) : null;
  });
  const [loading, setLoading] = useState(false);
  const [pendingAnalysisTicker, setPendingAnalysisTicker] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [searchResolution, setSearchResolution] = useState<{
    query: string;
    ticker: string;
    name?: string;
    confidence?: string;
  } | null>(null);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isHealthOpen, setIsHealthOpen] = useState(false);
  const [showInstallHelp, setShowInstallHelp] = useState(false);
  const [hideOnboardingNudge, setHideOnboardingNudge] = useState(false);
  const [auth, setAuth] = useState<AuthState>({
    loading: true,
    authenticated: false,
    configured: false,
    profile: null,
  });
  const [authStatus, setAuthStatus] = useState("");
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [tapeMovers, setTapeMovers] = useState<TapeMover[]>([]);
  const [marketMoversWindow, setMarketMoversWindow] = useState<MoversWindow>("1w");
  const [globalBrief, setGlobalBrief] = useState<any>(null);
  const [globalBriefStatus, setGlobalBriefStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [briefReloadTick, setBriefReloadTick] = useState(0);
  const [signalScoreContext, setSignalScoreContext] = useState<any>(null);
  const [learningContext, setLearningContext] = useState<any>(null);
  const [tradingEdge, setTradingEdge] = useState<any>(null);
  const [tradingEdgeLoading, setTradingEdgeLoading] = useState(false);
  const [selectedGeoRegion, setSelectedGeoRegion] = useState("Europe");
  const [watchlist, setWatchlist] = useState<WatchlistSnapshot | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const searchAbortRef = useRef<AbortController | null>(null);
  const searchRequestIdRef = useRef(0);
  const briefRequestIdRef = useRef(0);
  const discoveryAnalyzeEnabledAtRef = useRef(0);

  const {
    portfolios,
    loading: portfolioLoading,
    dataSource: portfolioDataSource,
    dataSourceMessage: portfolioDataSourceMessage,
    createPortfolio,
    deletePortfolio,
    addHolding,
    updateHolding,
    removeHolding,
    needsRestore,
    cachedPortfolios,
    restoreFromCache,
    discardRestore,
    refresh: refreshPortfolios,
  } = usePortfolios(auth.authenticated);

  const { currency, setCurrency, formatPrice } = useCurrency();
  const safeWatchlistItems = Array.isArray(watchlist?.items) ? watchlist.items : [];
  const safePortfolios: Portfolio[] = Array.isArray(portfolios) ? portfolios : [];
  const getSafeHoldings = (portfolio: Portfolio): Holding[] =>
    Array.isArray(portfolio?.holdings) ? portfolio.holdings : [];
  const watchlistTickerSymbols = safeWatchlistItems
    .filter((item) => item.kind === "ticker" && item.value)
    .map((item) => (item.value || "").toUpperCase());
  const portfolioTickerSymbols = safePortfolios
    .flatMap((portfolio) => getSafeHoldings(portfolio))
    .map((holding) => (holding.ticker || "").toUpperCase())
    .filter(Boolean);
  const userTrackedSymbols = Array.from(
    new Set([
      ...watchlistTickerSymbols,
      ...portfolioTickerSymbols,
    ].filter(Boolean) as string[]),
  ).slice(0, 10);
  const headerFallbackSymbols = ["SPY", "QQQ", "AAPL", "NVDA", "BTC-USD", "GLD"];
  const favoriteSymbols = userTrackedSymbols.length ? userTrackedSymbols : headerFallbackSymbols;
  const favoriteTapeLabel = userTrackedSymbols.length ? "Watchlist / Portfolio" : "Marktüberblick";
  const {
    quotes: headerQuotes,
    connected: headerRealtimeConnected,
    connectionState: headerConnectionState,
    transportMode: headerTransportMode,
  } = useRealtimeFeed(favoriteSymbols, auth.authenticated);
  const portfolioSnapshotForChat = useMemo(() => {
    const holdings = safePortfolios.flatMap((portfolio) =>
      getSafeHoldings(portfolio).map((holding) => {
        const ticker = String(holding.ticker || "").toUpperCase();
        const shares = Number(holding.shares || 0);
        const buyPrice = holding.buyPrice != null ? Number(holding.buyPrice) : null;
        const quotePrice = headerQuotes?.[ticker]?.price != null ? Number(headerQuotes[ticker].price) : null;
        const currentValue = quotePrice != null ? quotePrice * shares : null;
        const costBasis = buyPrice != null ? buyPrice * shares : null;
        const returnSinceBuy = currentValue != null && costBasis != null ? currentValue - costBasis : null;
        const returnSinceBuyPct =
          quotePrice != null && buyPrice != null && buyPrice > 0 ? ((quotePrice / buyPrice) - 1) * 100 : null;
        return {
          ticker,
          shares,
          buy_price: buyPrice,
          purchase_date: holding.purchaseDate ?? null,
          current_price: quotePrice,
          current_value: currentValue,
          return_since_buy: returnSinceBuy,
          return_since_buy_pct: returnSinceBuyPct,
          portfolio: portfolio.name,
        };
      }),
    );
    const totalValue = holdings.reduce((sum, holding) => sum + Number(holding.current_value || 0), 0);
    const totalCost = holdings.reduce((sum, holding) => {
      const buyPrice = holding.buy_price;
      return sum + (buyPrice != null ? buyPrice * Number(holding.shares || 0) : 0);
    }, 0);
    const totalReturn = holdings.reduce((sum, holding) => sum + Number(holding.return_since_buy || 0), 0);
    return {
      summary: {
        num_holdings: holdings.length,
        portfolios: safePortfolios.length,
        total_value: totalValue || null,
        return_since_buy: totalReturn || null,
        return_since_buy_pct: totalCost > 0 ? (totalReturn / totalCost) * 100 : null,
      },
      holdings: holdings.slice(0, 50),
    };
  }, [headerQuotes, safePortfolios]);
  const decisionBrief = useMemo(() => guardBriefForDecisions(globalBrief), [globalBrief]);
  const briefSummaryForChat = useMemo(
    () =>
      decisionBrief
        ? {
            headline: decisionBrief.headline,
            opening_bias: decisionBrief.opening_bias,
            macro_regime: decisionBrief.macro_regime,
            quality: decisionBrief.quality || null,
            decision_gate: decisionBrief.decision_gate || { allowed: true },
            trade_setups: (decisionBrief.trade_setups || []).slice(0, 5),
            setup_board: decisionBrief.setup_board || null,
            learning_adjustments: decisionBrief.learning_adjustments || [],
            congress_watch: (decisionBrief.congress_watch || []).slice(0, 5),
            event_pings: (decisionBrief.event_pings || []).slice(0, 5),
            earnings_calendar: (decisionBrief.earnings_calendar || []).slice(0, 8),
            earnings_results: (decisionBrief.earnings_results || []).slice(0, 6),
            market_movers: {
              gainers: (decisionBrief.market_movers?.gainers || []).slice(0, 6),
              losers: (decisionBrief.market_movers?.losers || []).slice(0, 6),
            },
            product_catalysts: (decisionBrief.product_catalysts || []).slice(0, 6),
            watchlist_impact: (decisionBrief.watchlist_impact || []).slice(0, 8),
            prediction_signals: (decisionBrief.prediction_signals || []).slice(0, 6),
          }
        : null,
    [decisionBrief],
  );

  useEffect(() => {
    if (!auth.authenticated || marketMoversWindow !== "1w") return;
    const seededMovers = marketMoversToTape(globalBrief?.market_movers, 6);
    if (!seededMovers.length) return;
    setTapeMovers((current) => (current.length ? current : seededMovers));
  }, [auth.authenticated, globalBrief, marketMoversWindow]);

  useEffect(() => {
    if (!auth.authenticated) return;

    let cancelled = false;

    const loadWatchlist = async () => {
      try {
        const payload = await fetchJsonWithRetry<WatchlistSnapshot>("/api/signals/watchlist", undefined, {
          retries: 0,
          retryDelayMs: 250,
          timeoutMs: 4500,
        });
        if (!cancelled) {
          setWatchlist(payload || { items: [] });
        }
      } catch {
        if (!cancelled) {
          setWatchlist({ items: [] });
        }
      }
    };

    const loadMovers = async () => {
      try {
        const [gainers, losers] = await Promise.all([
          fetchJsonWithRetry<any[]>(`/api/discovery/gainers?window=${marketMoversWindow}`, undefined, {
            retries: 0,
            retryDelayMs: 250,
            timeoutMs: 4500,
          }),
          fetchJsonWithRetry<any[]>(`/api/discovery/losers?window=${marketMoversWindow}`, undefined, {
            retries: 0,
            retryDelayMs: 250,
            timeoutMs: 4500,
          }),
        ]);

        if (cancelled) return;

        setTapeMovers(marketMoversToTape({ gainers, losers }, 6));
      } catch {
        if (!cancelled) {
          setTapeMovers((current) => current);
        }
      }
    };

    const initialMoversTimer = window.setTimeout(loadMovers, marketMoversWindow === "1w" ? 1800 : 0);
    loadWatchlist();
    const interval = window.setInterval(loadMovers, 60000);
    const watchlistInterval = window.setInterval(loadWatchlist, 90000);
    return () => {
      cancelled = true;
      window.clearTimeout(initialMoversTimer);
      window.clearInterval(interval);
      window.clearInterval(watchlistInterval);
    };
  }, [auth.authenticated, marketMoversWindow]);

  useEffect(() => {
    if (!auth.authenticated) return;
    let cancelled = false;
    const loadSignalContext = async () => {
      try {
        const payload = await fetchJsonWithRetry<any>("/api/signals/scoreboard", undefined, {
          retries: 1,
          retryDelayMs: 700,
        });
        if (!cancelled) {
          setSignalScoreContext(payload);
        }
      } catch {
        if (!cancelled) {
          setSignalScoreContext(null);
        }
      }
    };
    const cancelIdle = scheduleIdle(loadSignalContext, 3500);
    const interval = window.setInterval(loadSignalContext, 120000);
    return () => {
      cancelled = true;
      cancelIdle();
      window.clearInterval(interval);
    };
  }, [auth.authenticated]);

  useEffect(() => {
    if (!auth.authenticated) return;

    let cancelled = false;
    const loadLearningContext = async () => {
      try {
        const payload = await fetchJsonWithRetry<any>("/api/learning/forecasts", undefined, {
          retries: 1,
          retryDelayMs: 700,
          timeoutMs: 12000,
        });
        if (!cancelled) {
          setLearningContext(payload);
        }
      } catch {
        if (!cancelled) {
          setLearningContext(null);
        }
      }
    };
    const cancelIdle = scheduleIdle(loadLearningContext, 5000);
    const interval = window.setInterval(loadLearningContext, 180000);
    return () => {
      cancelled = true;
      cancelIdle();
      window.clearInterval(interval);
    };
  }, [auth.authenticated]);

  useEffect(() => {
    if (!auth.authenticated) return;
    let cancelled = false;

    const warmBackgroundData = async () => {
      if (isPageHidden() || shouldReduceBackgroundWork()) {
        preloadLazyScreens();
        return;
      }
      const ticker = analysis?.ticker?.toUpperCase();
      const historyPath = ticker
        ? `/api/history/${encodeURIComponent(ticker)}?period=1mo&interval=1d`
        : null;
      const paths = [
        "/api/discovery/stars",
        "/api/discovery/sentiment-heatmap",
        "/api/radar/bootstrap?limit=8",
        historyPath,
      ].filter(Boolean) as string[];

      for (const path of paths) {
        if (cancelled || isPageHidden()) break;
        await fetchJsonWithRetry<any>(path, undefined, {
          retries: 0,
          retryDelayMs: 250,
          timeoutMs: 9000,
        }).catch(() => undefined);
        await wait(250);
      }
      if (cancelled) return;
      preloadLazyScreens();
    };

    const warmVisibleData = () => {
      void warmBackgroundData();
    };

    const cancelIdle = scheduleIdle(warmVisibleData, 8000);

    const interval = window.setInterval(() => {
      if (!isPageHidden()) {
        warmVisibleData();
      }
    }, 600000);

    return () => {
      cancelled = true;
      cancelIdle();
      window.clearInterval(interval);
    };
  }, [auth.authenticated, analysis?.ticker, marketMoversWindow]);

  useEffect(() => {
    if (!auth.authenticated) return;

    let cancelled = false;
    let retryTimeout: number | undefined;

    const loadGlobalBrief = async () => {
      let displayableBriefLoaded = false;
      let currentBriefLoaded = false;
      const requestId = briefRequestIdRef.current + 1;
      briefRequestIdRef.current = requestId;
      if (!cancelled) setGlobalBriefStatus("loading");
      const timeoutGuard = window.setTimeout(() => {
        if (!cancelled && briefRequestIdRef.current === requestId && !displayableBriefLoaded) {
          setGlobalBriefStatus("error");
        }
      }, 10000);
      try {
        const fastPayload = await fetchJsonWithRetry<any>("/api/market/morning-brief?fast=true", undefined, {
          retries: 0,
          retryDelayMs: 250,
          timeoutMs: 2500,
        });
        if (!cancelled && briefRequestIdRef.current === requestId) {
          setGlobalBrief(fastPayload);
          setSelectedGeoRegion(fastPayload?.regions?.europe?.label || fastPayload?.regions?.usa?.label || "Europe");
          const fastState = getBriefLoadState(fastPayload);
          displayableBriefLoaded = fastState.displayable;
          currentBriefLoaded = fastState.current;
          setGlobalBriefStatus(displayableBriefLoaded ? "ready" : "loading");
        }

        await new Promise((resolve) => window.setTimeout(resolve, 300));
        const payload = await fetchJsonWithRetry<any>("/api/market/morning-brief", undefined, {
          retries: 0,
          retryDelayMs: 250,
          timeoutMs: 8500,
        });
        if (!cancelled && briefRequestIdRef.current === requestId) {
          const fullState = getBriefLoadState(payload);
          const fullBriefDisplayable = fullState.displayable;
          const fullBriefCurrent = fullState.current;
          if (fullBriefCurrent || !displayableBriefLoaded) {
            setGlobalBrief(payload);
            setSelectedGeoRegion(payload?.regions?.europe?.label || payload?.regions?.usa?.label || "Europe");
          }
          displayableBriefLoaded = displayableBriefLoaded || fullBriefDisplayable;
          currentBriefLoaded = currentBriefLoaded || fullBriefCurrent;
          setGlobalBriefStatus(displayableBriefLoaded ? "ready" : "error");
        }
      } catch {
        if (!cancelled && briefRequestIdRef.current === requestId && !displayableBriefLoaded) {
          setGlobalBriefStatus("error");
        }
      } finally {
        window.clearTimeout(timeoutGuard);
        if (!cancelled && briefRequestIdRef.current === requestId && !currentBriefLoaded) {
          window.clearTimeout(retryTimeout);
          retryTimeout = window.setTimeout(loadGlobalBrief, 12000);
        }
      }
    };

    loadGlobalBrief();
    const interval = window.setInterval(loadGlobalBrief, 300000);
    return () => {
      cancelled = true;
      window.clearTimeout(retryTimeout);
      window.clearInterval(interval);
    };
  }, [auth.authenticated, briefReloadTick]);

  // Trading edge - heavy payload, loaded separately with own spinner.
  // Refresh every 5 min; backend caches per-component (10min - 6h).
  useEffect(() => {
    if (!auth.authenticated || activeTab !== "dashboard") return;
    let cancelled = false;
    const loadEdge = async () => {
      setTradingEdgeLoading(true);
      try {
        const payload = await fetchJsonWithRetry<any>("/api/market/trading-edge", undefined, {
          retries: 1,
          retryDelayMs: 1000,
          timeoutMs: 15000,
        });
        if (!cancelled) setTradingEdge(payload);
      } catch {
        if (!cancelled) setTradingEdge(null);
      } finally {
        if (!cancelled) setTradingEdgeLoading(false);
      }
    };
    const cancelIdle = scheduleIdle(loadEdge, 6000);
    const interval = window.setInterval(loadEdge, 300000);
    return () => {
      cancelled = true;
      cancelIdle();
      window.clearInterval(interval);
    };
  }, [auth.authenticated, activeTab]);

  const refreshAuth = async (timeoutMs = 6000) => {
    const payload = await fetchJsonWithRetry<any>("/api/auth/status", undefined, {
      retries: 0,
      timeoutMs,
    });
    setAuth({
      loading: false,
      authenticated: Boolean(payload.authenticated),
      configured: Boolean(payload.configured),
      profile: payload.profile || null,
    });
  };

  useEffect(() => {
    let cancelled = false;
    let retryTimeout: number | undefined;
    let checkAttempt = 0;

    const checkAuth = async () => {
      try {
        await refreshAuth(checkAttempt === 0 ? 6000 : 20000);
        if (!cancelled) setAuthStatus("");
      } catch {
        if (cancelled) return;
        checkAttempt += 1;
        setAuth({
          loading: false,
          authenticated: false,
          configured: false,
          profile: null,
        });
        setAuthStatus("Server wird noch verbunden. Der Zugang wird automatisch erneut geprüft.");
        retryTimeout = window.setTimeout(checkAuth, 12000);
      }
    };

    void checkAuth();
    return () => {
      cancelled = true;
      window.clearTimeout(retryTimeout);
    };
  }, []);

  useEffect(() => {
    window.dispatchEvent(
      new CustomEvent("app:auth-state", {
        detail: { authenticated: auth.authenticated },
      }),
    );
  }, [auth.authenticated]);

  useEffect(() => {
    // Silent start: onboarding should never auto-block app opening.
    setShowOnboarding(false);
  }, [auth.authenticated, auth.profile]);

  useEffect(() => {
    const onUnauthorized = () => {
      setAuth((prev) => ({ ...prev, authenticated: false }));
      setAuthStatus("Session abgelaufen. Bitte erneut anmelden.");
    };
    window.addEventListener("app:unauthorized", onUnauthorized);
    return () => window.removeEventListener("app:unauthorized", onUnauthorized);
  }, []);

  useEffect(() => {
    localStorage.setItem("activeTab", activeTab);
  }, [activeTab]);

  useEffect(() => {
    if (activeTab === "discovery") {
      // Guard against click-through when switching tabs:
      // prevents accidental immediate jump into Analyze.
      discoveryAnalyzeEnabledAtRef.current = Date.now() + 2800;
    }
  }, [activeTab]);

  useEffect(() => {
    if (analysis) {
      localStorage.setItem("lastAnalysis", JSON.stringify(analysis));
    }
  }, [analysis]);

  useEffect(() => {
    return () => {
      searchAbortRef.current?.abort();
    };
  }, []);

  const handleLogin = async (password: string, rememberDevice: boolean) => {
    setAuthStatus("");
    const payload = await fetchJsonWithRetry<any>(
      "/api/auth/login",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password, remember_device: rememberDevice }),
      },
      { retries: 0, timeoutMs: 12000 },
    );
    setAuth({
      loading: false,
      authenticated: true,
      configured: true,
      profile: payload.profile || null,
    });
  };

  const loginAction = async (password: string, rememberDevice: boolean) => {
    try {
      await handleLogin(password, rememberDevice);
    } catch (err) {
      const statusCode = (err as Error & { status?: number } | null)?.status;
      setAuthStatus(
        statusCode === 401
          ? "Der Zugangscode ist nicht korrekt."
          : statusCode === 429
            ? "Zu viele Versuche. Bitte warte bis die Zugangssperre abgelaufen ist."
            : err instanceof Error
              ? err.message
              : "Der Zugang konnte nicht geprüft werden.",
      );
      throw err;
    }
  };

  const handleLogout = async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch {
      // Network error - clear local session anyway
    }
    setAuth((prev) => ({ ...prev, authenticated: false }));
    setAuthStatus("Abgemeldet.");
  };

  const shouldResolveBeforeAnalyze = (raw: string, normalized: string) => {
    const trimmed = raw.trim();
    if (!trimmed) return false;
    if (trimmed.includes("(") && trimmed.includes(")")) return false;
    const compactInput = trimmed.replace(/^[#$]+/, "");
    const directTickerShape = /^[A-Z0-9.^=-]{1,12}$/.test(compactInput);
    if (directTickerShape && normalized.length <= 12) return false;
    if (/^[a-z][a-z0-9.-]{2,20}$/.test(compactInput) && normalized === compactInput.toUpperCase()) return true;
    return (
      /\s/.test(trimmed) ||
      /[&+]/.test(trimmed) ||
      trimmed.length > 12 ||
      normalized.split("-").length > 2 ||
      trimmed !== trimmed.toUpperCase()
    );
  };

  const resolveTickerForAnalyze = async (raw: string, controller: AbortController) => {
    const normalized = normalizeTickerInput(raw);
    if (!normalized || !shouldResolveBeforeAnalyze(raw, normalized)) {
      setSearchResolution(null);
      return normalized;
    }
    try {
      const payload = await fetchJsonWithRetry<any>(
        `/api/search/resolve?q=${encodeURIComponent(raw.trim())}`,
        { signal: controller.signal },
        { retries: 1, retryDelayMs: 200, timeoutMs: 4500 },
      );
      const bestTicker = payload?.ticker || normalizeTickerInput(payload?.normalized || "");
      if (bestTicker && bestTicker !== normalized) {
        setSearchResolution({
          query: raw.trim(),
          ticker: bestTicker,
          name: payload?.name,
          confidence: payload?.confidence,
        });
      } else {
        setSearchResolution(null);
      }
      return bestTicker || normalized;
    } catch {
      setSearchResolution(null);
      return normalized;
    }
  };

  const handleSearch = async (ticker: string) => {
    const requestId = searchRequestIdRef.current + 1;
    searchRequestIdRef.current = requestId;
    searchAbortRef.current?.abort();
    const controller = new AbortController();
    searchAbortRef.current = controller;

    setLoading(true);
    setError(null);
    setSearchResolution(null);
    setAnalysis(null);
    setActiveTab("analyze");

    let searchTicker = normalizeTickerInput(ticker);
    setPendingAnalysisTicker(searchTicker || ticker);
    try {
      searchTicker = await resolveTickerForAnalyze(ticker, controller);
      if (controller.signal.aborted || searchRequestIdRef.current !== requestId || !searchTicker) return;
      setPendingAnalysisTicker(searchTicker);
      const data = await fetchJsonWithRetry<any>(
        `/api/analyze/${encodeURIComponent(searchTicker)}`,
        { signal: controller.signal },
        { retries: 0, retryDelayMs: 400, timeoutMs: 45000 },
      );
      if (controller.signal.aborted || searchRequestIdRef.current !== requestId) return;
      setAnalysis(data);
    } catch (err) {
      if (controller.signal.aborted || searchRequestIdRef.current !== requestId) return;
      const message = err instanceof Error ? err.message : "An error occurred";
      if (message.toLowerCase().includes("timeout")) {
        setError(`Die Analyse für ${searchTicker} dauert zu lange. Bitte erneut starten oder den Ticker direkt eingeben.`);
      } else {
        setError(`Die Analyse für ${searchTicker} konnte nicht geladen werden. ${message}`);
      }
    } finally {
      if (!controller.signal.aborted && searchRequestIdRef.current === requestId) {
        setLoading(false);
        setPendingAnalysisTicker("");
      }
    }
  };

  const handleDiscoveryAnalyze = (ticker: string) => {
    if (Date.now() < discoveryAnalyzeEnabledAtRef.current) return;
    void handleSearch(ticker);
  };

  const selectTab = (tab: Tab) => {
    if (tab === "discovery") {
      // Reset click-through guard on every explicit discovery tab click.
      discoveryAnalyzeEnabledAtRef.current = Date.now() + 2800;
    }
    setActiveTab(tab);
  };

  const handleInstallApp = async () => {
    if (installPrompt.canInstall) {
      await installPrompt.install();
      return;
    }
    setShowInstallHelp(true);
  };

  if (auth.loading) {
    return <div className="min-h-screen"><LoadingState label="Arbeitsbereich wird verbunden..." /></div>;
  }

  if (!auth.authenticated) {
    return (
      <LoginScreen
        configured={auth.configured}
        onLogin={loginAction}
        status={authStatus}
      />
    );
  }

  const showHero = activeTab === "analyze" && !analysis && !loading;
  const geoRegions = normalizeGeoRegions(decisionBrief?.regions);
  const onboardingDone = Boolean(auth.profile?.onboarding_done);
  const onboardingDismissedAtRaw = localStorage.getItem(ONBOARDING_DISMISSED_AT_KEY);
  const onboardingDismissedAt = onboardingDismissedAtRaw ? Number(onboardingDismissedAtRaw) : 0;
  const onboardingInCooldown =
    Number.isFinite(onboardingDismissedAt) &&
    onboardingDismissedAt > 0 &&
    Date.now() - onboardingDismissedAt < ONBOARDING_DISMISS_COOLDOWN_MS;
  const showOnboardingNudge = !onboardingDone && !onboardingInCooldown && !hideOnboardingNudge;
  const shouldShowOnboardingNudge = ONBOARDING_NUDGE_ENABLED && showOnboardingNudge;
  const activeNavItem = NAV_ITEMS.find((item) => item.id === activeTab) || NAV_ITEMS[0];
  const headerStatusLabel = headerRealtimeConnected ? headerConnectionState : headerTransportMode;
  const briefDecisionCurrent = isBriefDecisionCurrent(globalBrief);
  const macroRegimeLabel = localizeMarketRegime(decisionBrief?.macro_regime);
  const briefCommandStats = [
    ["Setups", decisionBrief?.trade_setups?.length || 0, "border-emerald-500/20 bg-emerald-500/10 text-emerald-700"],
    ["Ereignisse", decisionBrief?.event_pings?.length || 0, "border-amber-500/20 bg-amber-500/10 text-amber-700"],
    ["Kongress", decisionBrief?.congress_watch?.length || 0, "border-sky-500/20 bg-sky-500/10 text-sky-700"],
    ["Quartalszahlen", decisionBrief?.earnings_calendar?.length || 0, "border-indigo-500/20 bg-indigo-500/10 text-indigo-700"],
    ["Produkte", decisionBrief?.product_catalysts?.length || 0, "border-fuchsia-500/20 bg-fuchsia-500/10 text-fuchsia-700"],
  ];
  const dashboardPriorityCards = [
    {
      label: "Jetzt wichtig",
      title:
        (globalBrief && !briefDecisionCurrent ? "Briefing aktualisieren, bevor du handelst" : "") ||
        normalizeGermanDisplayText(decisionBrief?.opening_bias) ||
        normalizeGermanDisplayText(decisionBrief?.headline) ||
        "Noch kein klares Marktsignal",
      detail:
        globalBrief && !briefDecisionCurrent
          ? "Setups und Ereignisse sind bis zu einem frischen Datenstand gesperrt."
          : decisionBrief?.macro_regime
          ? `Regime: ${macroRegimeLabel}`
          : "Die Datenquelle lädt Setups, Ereignisse und Portfolio-Bezug.",
      tone: "border-emerald-500/18 bg-emerald-500/8 text-emerald-800",
    },
    {
      label: "Nächste Prüfung",
      title:
        decisionBrief?.trade_setups?.[0]?.ticker ||
        decisionBrief?.watchlist_impact?.[0]?.ticker ||
        decisionBrief?.product_catalysts?.[0]?.ticker ||
        "Watchlist",
      detail:
        normalizeGermanDisplayText(decisionBrief?.trade_setups?.[0]?.thesis) ||
        normalizeGermanDisplayText(decisionBrief?.watchlist_impact?.[0]?.reason) ||
        normalizeGermanDisplayText(decisionBrief?.product_catalysts?.[0]?.title) ||
        "Nur starke Signale werden in Analyzer/Markets vertieft.",
      tone: "border-sky-500/18 bg-sky-500/8 text-sky-800",
    },
    {
      label: "Risiko",
      title:
        normalizeGermanDisplayText(decisionBrief?.risk_note) ||
        normalizeGermanDisplayText(decisionBrief?.event_pings?.[0]?.title) ||
        "Keine harte Bremse",
      detail:
        normalizeGermanDisplayText(decisionBrief?.event_pings?.[0]?.summary) ||
        normalizeGermanDisplayText(decisionBrief?.opening_read?.summary) ||
        "Bei unklaren Daten erst beobachten, dann handeln.",
      tone: "border-amber-500/18 bg-amber-500/8 text-amber-800",
    },
  ];
  const favoriteTape = (
    <div className="header-favorites-tape overflow-x-auto no-scrollbar">
      <div className="flex min-w-max items-center gap-2">
        <div className={`rounded-full px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] ${headerRealtimeConnected ? "bg-emerald-500/10 text-emerald-700" : "bg-white/70 text-slate-500 ring-1 ring-black/6"}`}>
          {headerRealtimeConnected
            ? `${favoriteTapeLabel} ${headerConnectionState}`
            : `${favoriteTapeLabel} ${headerTransportMode}`}
        </div>
        {favoriteSymbols.map((symbol) => (
          <HeaderTickerChip key={symbol} symbol={symbol} quote={headerQuotes[symbol]} />
        ))}
      </div>
    </div>
  );
  const moversTape = tapeMovers.length ? (
    <div className="ticker-marquee-wrap header-movers-tape rounded-[1.15rem] border border-white/55 bg-white/46 px-2 py-1.5 sm:px-3">
      <div className="header-movers-meta flex items-center justify-between gap-3 px-1">
        <div className="text-[10px] font-extrabold uppercase leading-none tracking-[0.18em] text-slate-500">
          Marktbewegungen
        </div>
        <div className="flex shrink-0 items-center justify-end gap-2">
          <div className="rounded-full border border-black/8 bg-white/65 p-0.5">
            {(["1d", "1w", "1m"] as MoversWindow[]).map((window) => (
              <button
                key={window}
                type="button"
                onClick={() => setMarketMoversWindow(window)}
                className={`rounded-full px-2.5 py-1 text-[10px] font-extrabold uppercase leading-none tracking-[0.14em] transition-colors ${
                  marketMoversWindow === window
                    ? "bg-[#101114] text-white"
                    : "text-slate-500 hover:text-slate-800"
                }`}
              >
                {window.toUpperCase()}
              </button>
            ))}
          </div>
          <div className="hidden text-[10px] font-semibold uppercase leading-none tracking-[0.14em] text-slate-400 xl:block">
            Gewinner, Verlierer ({marketMoversWindow.toUpperCase()})
          </div>
        </div>
      </div>
      <div className="ticker-marquee-track">
        {[...tapeMovers, ...tapeMovers].map((item, index) => {
          const isWinner = item.side === "winner";
          const ArrowIcon = isWinner ? ArrowUpRight : ArrowDownRight;
          return (
            <div
              key={`${item.side}-${item.symbol}-${index}`}
              className="ticker-marquee-chip"
            >
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.16em] ${
                  isWinner
                    ? "bg-emerald-500/10 text-emerald-700"
                    : "bg-red-500/10 text-red-700"
                }`}
              >
                {isWinner ? "Gewinner" : "Verlierer"}
              </span>
              <span className="text-xs font-extrabold uppercase tracking-[0.14em] text-slate-700">
                {item.symbol}
              </span>
              <span
                className={`inline-flex items-center gap-1 text-xs font-bold ${
                  isWinner ? "text-emerald-700" : "text-red-700"
                }`}
              >
                <ArrowIcon size={12} />
                {typeof item.change === "number"
                  ? `${item.change >= 0 ? "+" : ""}${item.change.toFixed(2)}%`
                  : "Move"}
              </span>
              {item.price != null ? (
                <span className="text-xs font-semibold text-slate-500">
                  {formatPrice(item.price)}
                </span>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  ) : null;
  const mobileMarketTape = (
    <section className="mobile-market-tape lg:hidden">
      <div className="rounded-[1.25rem] border border-black/8 bg-white/72 p-2.5 shadow-[0_12px_30px_rgba(17,24,39,0.06)] backdrop-blur-xl">
        {favoriteTape}
        {activeTab === "dashboard" && moversTape ? (
          <div className="mt-2 max-h-[6.4rem] overflow-hidden">
            {moversTape}
          </div>
        ) : null}
      </div>
    </section>
  );

  return (
    <div className="min-h-screen pb-20 text-[var(--text-primary)] md:pb-8">
      <header className="sticky top-0 z-50 header-gradient backdrop-blur-xl">
        <div className="mobile-topbar-shell px-3 pb-2 pt-[calc(0.55rem+env(safe-area-inset-top))] lg:hidden">
          <div className="mobile-topbar flex h-[54px] items-center justify-between gap-2 rounded-[1.15rem] px-2.5">
            <div className="flex min-w-0 items-center gap-2.5">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[0.85rem] bg-[#101114] text-white">
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l5-5 4 4 7-8" />
                </svg>
              </div>
              <div className="min-w-0">
                <div className="truncate text-[9px] font-extrabold uppercase tracking-[0.2em] text-slate-500">
                  Broker Freund
                </div>
                <div className="truncate text-[14px] font-black leading-tight text-slate-950">
                  {activeNavItem.label}
                </div>
              </div>
            </div>

            <div className="flex shrink-0 items-center gap-1">
              <span
                className={`flex h-2.5 w-2.5 rounded-full ${
                  headerRealtimeConnected ? "bg-emerald-500 shadow-[0_0_0_4px_rgba(16,185,129,0.12)]" : "bg-amber-500"
                }`}
                title={`Marktdaten: ${headerStatusLabel}`}
              />
              <button
                onClick={() => setCurrency(currency === "USD" ? "EUR" : "USD")}
                aria-label={`Währung auf ${currency === "USD" ? "EUR" : "USD"} wechseln`}
                className="mobile-topbar-button px-2.5 py-1.5 text-[10px]"
              >
                {currency}
              </button>
              <button
                onClick={toggleTheme}
                aria-label="Darstellung wechseln"
                className="mobile-topbar-icon"
              >
                {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
              </button>
              <button
                onClick={handleInstallApp}
                aria-label="App installieren"
                className={`mobile-topbar-icon ${
                  installPrompt.installed ? "text-emerald-700" : "text-slate-700"
                }`}
                title={installPrompt.installed ? "App ist installiert" : "App installieren"}
              >
                {installPrompt.installed ? <Smartphone size={14} /> : <Download size={14} />}
              </button>
              <button
                onClick={() => setIsHealthOpen(true)}
                aria-label="Statuszentrum öffnen"
                className="mobile-topbar-icon"
                title="Statuszentrum"
              >
                <Activity size={14} />
              </button>
              <button
                onClick={handleLogout}
                aria-label="Arbeitsbereich sperren"
                className="flex h-8 w-8 items-center justify-center rounded-full bg-[#101114] text-white"
                title="Arbeitsbereich sperren"
              >
                <LockKeyhole size={14} />
              </button>
            </div>
          </div>
        </div>

        <div className="layout-shell hidden px-3 pb-2 pt-2 lg:block sm:px-6 xl:px-8 2xl:px-10">
          <div className="app-shell app-shell-header app-shell-header-compact rounded-[1.4rem] px-3 py-2.5 sm:rounded-[1.7rem] sm:px-4">
            <div className="grid items-center gap-3 lg:grid-cols-[minmax(18rem,1fr)_auto_minmax(18rem,1fr)]">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-[0.9rem] bg-[#101114] text-white">
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l5-5 4 4 7-8" />
                  </svg>
                </div>
                <div className="min-w-0">
                  <div className="truncate text-[11px] font-extrabold uppercase tracking-[0.24em] text-slate-500">
                    Broker Freund
                  </div>
                  <div className="truncate text-base font-semibold text-slate-900">
                    Marktintelligenz-Terminal
                  </div>
                </div>
              </div>

              <div className="hidden justify-self-center items-center gap-1.5 rounded-[1rem] bg-[var(--bg-elevated)] p-1 ring-1 ring-[var(--line-subtle)] lg:flex">
                {NAV_ITEMS.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => selectTab(item.id)}
                    className={`rounded-[0.85rem] px-3 py-2 text-xs font-bold transition-all ${
                      activeTab === item.id
                        ? "bg-[#101114] text-white shadow-[0_10px_30px_rgba(17,24,39,0.18)]"
                        : "text-slate-600 hover:bg-black/[0.04] hover:text-slate-900"
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>

              <div className="flex min-w-0 flex-wrap items-center justify-end gap-2 md:flex-nowrap">
                {/* Desktop: full USD / EUR toggle */}
                <div className="hidden rounded-[1.1rem] bg-[var(--bg-elevated)] p-1 ring-1 ring-[var(--line-subtle)] sm:flex">
                  <button
                    onClick={() => setCurrency("USD")}
                    aria-label="Währung auf USD wechseln"
                    className={`rounded-[0.9rem] px-3 py-2 text-xs font-extrabold uppercase tracking-[0.18em] transition-all ${
                      currency === "USD" ? "bg-[#101114] text-white" : "text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    USD
                  </button>
                  <button
                    onClick={() => setCurrency("EUR")}
                    aria-label="Währung auf EUR wechseln"
                    className={`rounded-[0.9rem] px-3 py-2 text-xs font-extrabold uppercase tracking-[0.18em] transition-all ${
                      currency === "EUR" ? "bg-[#101114] text-white" : "text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    EUR
                  </button>
                </div>
                {/* Mobile: compact toggle that cycles USD <-> EUR */}
                <button
                  onClick={() => setCurrency(currency === "USD" ? "EUR" : "USD")}
                  aria-label={`Währung auf ${currency === "USD" ? "EUR" : "USD"} wechseln`}
                  className="rounded-[1rem] border border-[var(--line-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-xs font-extrabold uppercase tracking-[0.18em] text-[var(--text-primary)] transition-colors sm:hidden"
                >
                  {currency}
                </button>
                {/* Theme toggle */}
                <button
                  onClick={toggleTheme}
                  aria-label="Darstellung wechseln"
                  className="rounded-[1rem] border border-[var(--line-subtle)] bg-[var(--bg-elevated)] p-2.5 text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
                >
                  {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
                </button>
                <button
                  onClick={handleInstallApp}
                  className={`whitespace-nowrap rounded-[1rem] border px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.16em] transition-colors sm:px-4 sm:py-2.5 sm:text-xs sm:tracking-[0.18em] ${
                    installPrompt.installed
                      ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700"
                      : "border-[var(--line-subtle)] bg-[var(--bg-elevated)] text-[var(--text-primary)] hover:bg-[var(--bg-panel)]"
                  }`}
                  title={installPrompt.installed ? "App ist installiert" : "Als App installieren"}
                >
                  {installPrompt.installed ? "Installiert" : "Installieren"}
                </button>
                {/* Username - visible on all screen sizes */}
                <div className="max-w-[7.5rem] truncate rounded-[1rem] border border-[var(--line-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.16em] text-[var(--text-secondary)] sm:max-w-none sm:text-xs">
                  {auth.profile?.display_name || "Private"}
                </div>
                <button
                  onClick={() => setIsHealthOpen(true)}
                  className="whitespace-nowrap rounded-[1rem] border border-[var(--line-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.16em] text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-panel)] sm:px-4 sm:py-2.5 sm:text-xs sm:tracking-[0.18em]"
                >
                  Status
                </button>
                <button
                  onClick={handleLogout}
                  className="whitespace-nowrap rounded-[1rem] border border-[var(--line-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.16em] text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-panel)] sm:px-4 sm:py-2.5 sm:text-xs sm:tracking-[0.18em]"
                >
                  Sperren
                </button>
              </div>
            </div>
            <div className="desktop-market-strip mt-2">
              <div className="desktop-favorite-tape min-w-0">{favoriteTape}</div>
              {moversTape ? <div className="desktop-movers-tape min-w-0">{moversTape}</div> : null}
            </div>
          </div>
        </div>
      </header>

      <main
        className={`content-shell px-4 pt-3 transition-all duration-300 sm:px-6 lg:pt-5 xl:px-8 2xl:px-10 ${
          isChatOpen ? "xl:pr-[32rem] 2xl:pr-[36rem]" : ""
        }`}
      >
        {mobileMarketTape}
        {activeTab === "dashboard" ? (
          <div className="space-y-8">
            {shouldShowOnboardingNudge ? (
              <section className="rounded-[1.6rem] border border-[var(--accent)]/16 bg-[linear-gradient(180deg,rgba(15,118,110,0.07),rgba(255,255,255,0.9))] p-4 sm:p-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-[var(--accent)]">
                      Optionale Einrichtung
                    </div>
                    <div className="mt-1 text-sm font-semibold text-slate-800">
                      Die Ersteinrichtung ist optional und blockiert den Start nicht.
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setShowOnboarding(true)}
                      className="rounded-[0.9rem] bg-[var(--accent)] px-3 py-2 text-xs font-extrabold uppercase tracking-[0.14em] text-white"
                    >
                      Jetzt einrichten
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        localStorage.setItem(ONBOARDING_DISMISSED_AT_KEY, String(Date.now()));
                        setHideOnboardingNudge(true);
                      }}
                      className="rounded-[0.9rem] border border-black/10 bg-white px-3 py-2 text-xs font-extrabold uppercase tracking-[0.14em] text-slate-600"
                    >
                      Spaeter
                    </button>
                  </div>
                </div>
              </section>
            ) : null}

            <ErrorBoundary>
              <Suspense fallback={<LoadingState />}>
                <EdgeDashboardPanel
                  signalScore={signalScoreContext}
                  learning={learningContext}
                  tradingEdge={tradingEdge}
                  globalBrief={decisionBrief}
                  portfolios={portfolios}
                  quotes={headerQuotes}
                  loading={
                    globalBriefStatus === "loading" ||
                    tradingEdgeLoading ||
                    !signalScoreContext ||
                    !learningContext
                  }
                  onAnalyzeTicker={(ticker) => {
                    setActiveTab("analyze");
                    handleSearch(ticker);
                  }}
                  onOpenPortfolio={() => setActiveTab("portfolio")}
                  onOpenMarkets={() => setActiveTab("discovery")}
                />
              </Suspense>
            </ErrorBoundary>

            <section className="surface-panel dashboard-command-panel dashboard-guide-panel rounded-[1.5rem] p-4 sm:p-5">
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center">
                <div className="min-w-0">
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                    Lesereihenfolge
                  </div>
                  <h2 className="mt-1 max-w-4xl text-2xl text-slate-900 sm:text-3xl">
                    Erst Entscheidung, dann Marktbild, dann Details.
                  </h2>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                    Das Dashboard ist die kurze Zusammenfassung. Tiefe Listen liegen in Markets,
                    einzelne Werte im Analyzer und Positionen im Portfolio.
                  </p>
                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <div className={`rounded-full border px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] ${
                      headerRealtimeConnected
                        ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700"
                        : "border-amber-500/20 bg-amber-500/10 text-amber-700"
                    }`}>
                      Daten {headerStatusLabel}
                    </div>
                    {globalBrief?.macro_regime ? (
                      <div className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-amber-700">
                        Regime {macroRegimeLabel}
                      </div>
                    ) : null}
                  </div>
                </div>
                {globalBrief?.macro_regime ? (() => {
                  const r = (globalBrief.macro_regime || "").toLowerCase();
                  const isOn = r.includes("risk-on") || r.includes("on");
                  const isOff = r.includes("risk-off") || r.includes("off");
                  const icon = isOn ? "UP" : isOff ? "DOWN" : "FLAT";
                  const cls = isOn
                    ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700"
                    : isOff
                      ? "border-red-500/20 bg-red-500/10 text-red-700"
                      : "border-amber-500/20 bg-amber-500/10 text-amber-700";
                  return (
                    <div className={`hidden rounded-full border ${cls} px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em]`}>
                      {icon} {macroRegimeLabel}
                    </div>
                  );
                })() : null}
                <div className="rounded-[1.25rem] border border-black/8 bg-white/72 p-3 shadow-[0_12px_28px_rgba(17,24,39,0.05)]">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-slate-500">
                        Kurzstatus
                      </div>
                      <div className="mt-1 text-sm font-bold text-slate-900">
                        Entscheidung / Markt / Briefing
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => setIsChatOpen(true)}
                      className="rounded-full bg-[#101114] px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-white"
                    >
                      Buddy fragen
                    </button>
                  </div>
                  <div className="mt-3 grid grid-cols-5 gap-2">
                    {briefCommandStats.map(([label, value, tone]) => (
                      <div key={String(label)} className={`rounded-[1rem] border p-2 text-center ${tone}`}>
                        <div className="text-lg font-black leading-none">{value}</div>
                        <div className="mt-1 truncate text-[8px] font-extrabold uppercase tracking-[0.12em]">
                          {label}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </section>

            <div className="dashboard-section-label">
              <span>Heute wichtig</span>
              <span>3 Prioritäten, danach Details</span>
            </div>
            <div className="dashboard-priority-strip">
              {dashboardPriorityCards.map((item) => (
                <div key={item.label} className={`dashboard-priority-card ${item.tone}`}>
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] opacity-70">
                    {item.label}
                  </div>
                  <div className="mt-2 line-clamp-1 text-base font-black text-slate-950 dark:text-white">
                    {String(item.title).slice(0, 96)}
                  </div>
                  <div className="mt-1 line-clamp-2 text-xs font-semibold leading-5 text-slate-600 dark:text-slate-300">
                    {String(item.detail).slice(0, 180)}
                  </div>
                </div>
              ))}
            </div>

            <div className="dashboard-section-label">
              <span>Detailanalyse</span>
              <span>Marktbild links, Briefing rechts</span>
            </div>
            <div className="dashboard-intel-grid">
                {geoRegions.length ? (
                  <ErrorBoundary>
                    <Suspense fallback={<LoadingState />}>
                      <div className="dashboard-map-slot">
                        <WorldMarketMap
                          regions={geoRegions}
                          selectedRegion={selectedGeoRegion}
                          onSelectRegion={setSelectedGeoRegion}
                          news={decisionBrief?.top_news || []}
                          eventLayer={decisionBrief?.event_layer || []}
                          eventPings={decisionBrief?.event_pings || []}
                          watchlistImpact={decisionBrief?.watchlist_impact || []}
                          contrarianSignals={decisionBrief?.contrarian_signals || []}
                          openingTimeline={decisionBrief?.opening_timeline || []}
                          onAnalyze={(t) => {
                            setActiveTab("analyze");
                            handleSearch(t);
                          }}
                          focusTicker={analysis?.ticker}
                        />
                      </div>
                    </Suspense>
                  </ErrorBoundary>
                ) : (
                  <section className="surface-panel rounded-[2rem] p-6">
                    <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                      Weltkarten-Daten
                    </div>
                    <div className="mt-3 text-base font-semibold text-slate-800">
                      Live-Morning-Briefing aktuell nicht verfügbar.
                    </div>
                    <p className="mt-2 text-sm leading-6 text-slate-600">
                      Die Datenquelle antwortet gerade langsam oder unvollständig. Du kannst sofort neu laden.
                    </p>
                    <button
                      type="button"
                      onClick={() => setBriefReloadTick((prev) => prev + 1)}
                      className="mt-4 rounded-[0.95rem] bg-[var(--accent)] px-4 py-2 text-xs font-extrabold uppercase tracking-[0.16em] text-white"
                    >
                      Retry Feed
                    </button>
                  </section>
                )}
                {decisionBrief ? (
                  <ErrorBoundary>
                    <Suspense fallback={<LoadingState />}>
                      <div className="dashboard-brief-slot">
                        <MorningBriefPanel
                          brief={decisionBrief}
                          onAnalyze={(t) => {
                            setActiveTab("analyze");
                            handleSearch(t);
                          }}
                          hideMap
                        />
                      </div>
                    </Suspense>
                  </ErrorBoundary>
                ) : globalBriefStatus === "loading" || globalBriefStatus === "idle" ? (
                  <LoadingState />
                ) : (
                  <section className="surface-panel rounded-[2rem] p-5 sm:p-6">
                    <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                      Briefing-Daten
                    </div>
                    <div className="mt-3 text-base font-semibold text-slate-800">
                      Briefing gerade nicht verfügbar.
                    </div>
                    <p className="mt-2 text-sm leading-6 text-slate-600">
                      Die World Map bleibt nutzbar. Lade nur den Briefing-Feed erneut, ohne das Dashboard zu blockieren.
                    </p>
                    <button
                      type="button"
                      onClick={() => setBriefReloadTick((prev) => prev + 1)}
                      className="mt-4 rounded-[0.95rem] bg-[var(--accent)] px-4 py-2 text-xs font-extrabold uppercase tracking-[0.16em] text-white"
                    >
                      Briefing neu laden
                    </button>
                  </section>
                )}
            </div>
          </div>
        ) : activeTab === "analyze" ? (
          <>
            {showHero && (
              <section className="mb-8 space-y-6">
                <div>
                  <SearchBar onSearch={handleSearch} loading={loading} inputRef={searchInputRef} />
                </div>
              </section>
            )}

            {!showHero && (
              <div className="mb-8">
                <SearchBar onSearch={handleSearch} loading={loading} />
              </div>
            )}

            {searchResolution && (
              <div className="surface-panel mb-8 flex flex-wrap items-center justify-between gap-3 rounded-[1.35rem] border border-emerald-500/18 bg-emerald-500/[0.06] px-4 py-3 text-sm text-emerald-900">
                <div>
                  <span className="font-extrabold">Aufgeloest:</span>{" "}
                  <span className="text-emerald-800">{searchResolution.query}</span>{" "}
                  <span className="text-emerald-700">{"->"}</span>{" "}
                  <span className="font-black">{searchResolution.ticker}</span>
                  {searchResolution.name ? (
                    <span className="text-emerald-800"> / {searchResolution.name}</span>
                  ) : null}
                </div>
                <span className="rounded-full border border-emerald-500/20 bg-white/70 px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-emerald-700">
                  {searchResolution.confidence || "resolved"}
                </span>
              </div>
            )}

            {error && (
              <div className="surface-panel mb-8 rounded-[1.75rem] border border-red-200 bg-red-50/80 p-4 text-sm text-red-700">
                {error}
              </div>
            )}

            {loading && <AnalyzerLoadingPanel ticker={pendingAnalysisTicker} />}

            {analysis && !loading && (
              <div className="space-y-8">
                <ErrorBoundary>
                  <Suspense fallback={<LoadingState />}>
                    <AnalysisResult
                      data={analysis}
                      portfolios={portfolios}
                      onAddHolding={addHolding}
                      onOpenChat={() => setIsChatOpen(true)}
                      onSelectTicker={handleSearch}
                    />
                  </Suspense>
                </ErrorBoundary>
              </div>
            )}

            {!analysis && !loading && !error && (
              <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
                <div className="surface-panel rounded-[2rem] p-6">
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                    Analyse-Start
                  </div>
                  <h3 className="mt-3 text-2xl text-slate-900">
                    Erst suchen, dann Analyse, Signale und Handlungsrahmen gemeinsam prüfen.
                  </h3>
                  <div className="mt-6 grid gap-3 sm:grid-cols-3">
                    {[
                      {
                        title: "Öffentliche Signale",
                        body: "Berkshire, Kongress und weitere öffentliche Meldungen mit sichtbarer Verzögerung.",
                        cta: "Markets öffnen",
                        action: () => setActiveTab("discovery" as Tab),
                      },
                      {
                        title: "Klare Einordnung",
                        body: "Ruhigere Scores und klare Priorisierung von Risiko, Bewertung und Momentum.",
                        cta: "Analyse starten",
                        action: () => {
                          searchInputRef.current?.focus();
                        },
                      },
                      {
                        title: "Privater Zugang",
                        body: "Geschützter Einzelzugang mit Sitzung und abgesicherten Triggern.",
                        cta: "Portfolio öffnen",
                        action: () => setActiveTab("portfolio" as Tab),
                      },
                    ].map((item) => (
                      <button
                        key={item.title}
                        type="button"
                        onClick={item.action}
                        className="rounded-[1.4rem] border border-black/8 bg-white/75 p-4 text-left transition-all hover:border-black/14 hover:bg-white hover:shadow-[0_16px_34px_rgba(15,23,42,0.08)]"
                      >
                        <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                          {item.title}
                        </div>
                        <p className="mt-2 text-sm leading-6 text-slate-600">{item.body}</p>
                        <div className="mt-4 inline-flex rounded-full border border-black/8 bg-white px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] text-[var(--accent)]">
                          {item.cta}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
                <div className="rounded-[2rem] border border-[var(--accent)]/14 bg-[linear-gradient(180deg,rgba(15,118,110,0.08),rgba(255,255,255,0.88))] p-6">
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                    Arbeitsablauf
                  </div>
                  <div className="mt-4 space-y-3">
                    {[
                      {
                        copy: "1. Aktie, ETF oder Kryptowährung suchen.",
                        cta: "Suche fokussieren",
                        action: () => {
                          const searchInput = document.querySelector<HTMLInputElement>('input[placeholder="AAPL, NVDA, ASML, BTC-USD"]');
                          searchInput?.focus();
                        },
                      },
                      {
                        copy: "2. Live-Kurs, Score-Kontext und Risikoprofil prüfen.",
                        cta: "Markets öffnen",
                        action: () => setActiveTab("discovery" as Tab),
                      },
                      {
                        copy: "3. Nur bei bestätigtem Setup zu Paper-Trading oder Signalen wechseln.",
                        cta: "Portfolio öffnen",
                        action: () => setActiveTab("portfolio" as Tab),
                      },
                    ].map((item) => (
                      <button
                        key={item.copy}
                        type="button"
                        onClick={item.action}
                        className="rounded-[1.3rem] border border-black/8 bg-white/78 p-4 text-left text-sm text-slate-700 transition-all hover:border-black/14 hover:bg-white"
                      >
                        <div>{item.copy}</div>
                        <div className="mt-3 inline-flex rounded-full border border-black/8 bg-white px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-[var(--accent)]">
                          {item.cta}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              </section>
            )}
          </>
        ) : activeTab === "discovery" ? (
          <ErrorBoundary>
            <Suspense fallback={<LoadingState />}>
              <DiscoveryPanel onAnalyze={handleDiscoveryAnalyze} />
            </Suspense>
          </ErrorBoundary>
        ) : (
          <ErrorBoundary>
            {portfolioDataSource !== "server" && portfolioDataSource !== "empty" ? (
              <div className="mb-4 rounded-[1.4rem] border border-amber-400/30 bg-amber-50 p-5 shadow-sm">
                <div className="text-sm font-extrabold text-amber-800">
                  Portfolio-Datenquelle: {portfolioDataSource === "local-cache" ? "lokale Browser-Sicherung" : portfolioDataSource}
                </div>
                <p className="mt-1 text-sm leading-6 text-amber-700">
                  {portfolioDataSourceMessage || "Serverdaten sind gerade nicht verfügbar."}
                </p>
              </div>
            ) : null}
            {needsRestore && cachedPortfolios.length > 0 && (
              <div className="mb-4 rounded-[1.4rem] border border-amber-400/30 bg-amber-50 p-5 shadow-sm">
                <div className="flex flex-wrap items-start gap-4">
                  <div className="flex-1">
                    <div className="text-sm font-extrabold text-amber-800">Portfolios wiederherstellen</div>
                    <p className="mt-1 text-sm text-amber-700">
                      Der Server wurde neu gestartet und die Daten wurden zurückgesetzt.
                      Es wurden <strong>{cachedPortfolios.length} Portfolio{cachedPortfolios.length > 1 ? "s" : ""}</strong> lokal gespeichert -
                      sollen sie wiederhergestellt werden?
                    </p>
                    <div className="mt-1 text-xs text-amber-600">
                      {cachedPortfolios.map(p => `${p.name} (${p.holdings.length} Positionen)`).join(" / ")}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={restoreFromCache}
                      className="rounded-[0.9rem] bg-amber-500 px-4 py-2 text-xs font-extrabold uppercase tracking-[0.14em] text-white hover:bg-amber-600"
                    >
                      Wiederherstellen
                    </button>
                    <button
                      onClick={discardRestore}
                      className="rounded-[0.9rem] border border-amber-300 bg-white px-4 py-2 text-xs font-extrabold uppercase tracking-[0.14em] text-amber-700 hover:bg-amber-50"
                    >
                      Verwerfen
                    </button>
                  </div>
                </div>
              </div>
            )}
            <Suspense fallback={<LoadingState />}>
              <PortfolioView
                portfolios={portfolios}
                dataSource={portfolioDataSource}
                dataSourceMessage={portfolioDataSourceMessage}
                loading={portfolioLoading}
                onCreatePortfolio={createPortfolio}
                onDeletePortfolio={deletePortfolio}
                onAddHolding={addHolding}
                onUpdateHolding={updateHolding}
                onRemoveHolding={removeHolding}
                onRefresh={refreshPortfolios}
                onAnalyzeStock={(ticker) => {
                  setActiveTab("analyze");
                  handleSearch(ticker);
                }}
              />
            </Suspense>
          </ErrorBoundary>
        )}
      </main>

      <nav className="mobile-tabbar fixed inset-x-2 z-50 mx-auto w-auto max-w-md rounded-[1.35rem] p-1.5 lg:hidden">
        <div className="grid grid-cols-4 gap-1">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              onClick={() => selectTab(item.id)}
              className={`mobile-tabbar-button rounded-[0.95rem] px-1.5 py-2.5 text-center text-[9px] font-extrabold uppercase tracking-[0.12em] transition-all ${
                activeTab === item.id ? "bg-[#101114] text-white" : "text-slate-500 hover:bg-black/[0.04]"
              }`}
            >
              {item.short}
            </button>
          ))}
        </div>
      </nav>

      <footer className="border-t border-black/6 bg-white/50">
        <div className="layout-shell px-4 py-6 text-center text-sm text-slate-500 sm:px-6 xl:px-8 2xl:px-10">
          Broker Freund {__APP_VERSION__} Beta. Privater Einzelarbeitsbereich. Informationen sind ein Entscheidungsrahmen, keine Gewinnzusage.
        </div>
      </footer>

      <ErrorBoundary fallback={<></>}>
        <Suspense fallback={null}>
          <BrokerChat
            currentTicker={analysis?.ticker}
            activeTab={activeTab}
            contextSymbols={favoriteSymbols}
            portfolioSnapshot={portfolioSnapshotForChat}
            liveQuotes={headerQuotes}
            signalScore={signalScoreContext}
            morningBriefSummary={briefSummaryForChat}
            learningSummary={learningContext}
            onAnalyzeTicker={(ticker) => {
              setIsChatOpen(false);
              setActiveTab("analyze");
              handleSearch(ticker);
            }}
            onOpenTab={(tab) => selectTab(tab as Tab)}
            onOpenHealth={() => setIsHealthOpen(true)}
            isOpen={isChatOpen}
            setIsOpen={setIsChatOpen}
          />
        </Suspense>
      </ErrorBoundary>

      <AdminHealthPanel isOpen={isHealthOpen} onClose={() => setIsHealthOpen(false)} />

      <Suspense fallback={null}>
        <OnboardingWizard
          isOpen={showOnboarding}
          onCreatePortfolio={createPortfolio}
          onComplete={async () => {
            setShowOnboarding(false);
            localStorage.removeItem(ONBOARDING_DISMISSED_AT_KEY);
            await refreshAuth().catch(() => undefined);
          }}
          onDismiss={() => {
            localStorage.setItem(ONBOARDING_DISMISSED_AT_KEY, String(Date.now()));
            setShowOnboarding(false);
          }}
        />
      </Suspense>
      {showInstallHelp && (
        <div
          className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 px-4 backdrop-blur-sm"
          onClick={() => setShowInstallHelp(false)}
        >
          <div
            className="surface-panel w-full max-w-md rounded-[2rem] p-7 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[1rem] bg-[var(--accent-soft)] text-[var(--accent)]">
                <Smartphone size={18} />
              </div>
              <div>
                <div className="text-lg font-black text-[var(--text-primary)]">App installieren</div>
                <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
              Wenn kein Installationsdialog erscheint, nutze im Browser-Menü den Punkt
              "App installieren" oder "Zum Startbildschirm hinzufügen".
                </p>
              </div>
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <div className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4 text-sm text-slate-700">
                Desktop: Menü in Chrome oder Edge öffnen und "App installieren" wählen.
              </div>
              <div className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4 text-sm text-slate-700">
                iPhone: Teilen-Dialog öffnen und "Zum Home-Bildschirm" wählen.
              </div>
            </div>
            <button
              onClick={() => setShowInstallHelp(false)}
              className="mt-6 w-full rounded-[1.2rem] bg-[var(--accent)] py-3 text-sm font-extrabold uppercase tracking-[0.16em] text-white hover:bg-[var(--accent-strong)]"
            >
              Verstanden
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <CurrencyProvider>
        <AppContent />
      </CurrencyProvider>
    </ThemeProvider>
  );
}
