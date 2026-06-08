import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { ComponentType, LazyExoticComponent } from "react";
import SearchBar, { normalizeTickerInput } from "./components/SearchBar";
import LoadingState from "./components/LoadingState";
import ErrorBoundary from "./components/ErrorBoundary";
import AdminHealthPanel from "./components/AdminHealthPanel";
import { usePortfolios } from "./hooks/usePortfolios";
import { CurrencyProvider, useCurrency } from "./context/CurrencyContext";
import { ThemeProvider, useTheme } from "./context/ThemeContext";
import useRealtimeFeed from "./hooks/useRealtimeFeed";
import { fetchJsonWithRetry } from "./lib/api";
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

function preloadLazyScreens() {
  const safeImport = (loader: () => Promise<unknown>) => {
    void loader().catch(() => undefined);
  };
  safeImport(() => import("./components/AnalysisResult"));
  safeImport(() => import("./components/DiscoveryPanel"));
  safeImport(() => import("./components/PortfolioView"));
  safeImport(() => import("./components/BrokerChat"));
  safeImport(() => import("./components/WorldMarketMap"));
  safeImport(() => import("./components/EdgeDashboardPanel"));
  safeImport(() => import("./components/MorningBriefPanel"));
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
                  Private Workspace
                </div>
                <h1 className="mt-3 max-w-3xl text-3xl leading-none text-slate-900 sm:text-5xl lg:text-6xl">
                  Market Intelligence, locked to your local workspace.
                </h1>
                <p className="mt-5 max-w-2xl text-base leading-7 text-slate-600">
                  Die App ist jetzt auf Single-User-Betrieb gehaertet: lokales Passwort, geschuetzte API,
                  localhost-only und keine offenen Alert-Endpunkte mehr.
                </p>
              </div>
              <div className="grid gap-4 sm:grid-cols-3">
                {[
                  "API hinter Session-Cookie",
                  "CORS auf lokale Origins begrenzt",
                  "Alerts und Settings nicht mehr offen",
                ].map((item) => (
                  <div key={item} className="rounded-[1.6rem] border border-black/8 bg-white/75 p-4 text-sm font-semibold text-slate-700">
                    {item}
                  </div>
                ))}
              </div>
              <div className="grid gap-4 sm:grid-cols-3">
                {[
                  ["Signal-first", "Morning Brief, Watchlist und Realtime direkt im Startpfad."],
                  ["Private", "Nur dein Workspace, keine offene Multi-User-Flaeche."],
                  ["Execution-ready", "Score, Paper Trading und Session-Listen in einem Flow."],
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
                Access
              </div>
              <div className="mt-4 text-3xl font-black text-white">
                Enter workspace code
              </div>
              <p className="mt-3 text-sm leading-7 text-white/70">
                {configured
                  ? "Nur mit lokaler Session wird die App geladen."
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
                  aria-label="6-digit workspace access code"
                  className="login-password-input w-full rounded-[1.2rem] border px-4 py-3 text-sm font-semibold"
                  placeholder="6-digit access code"
                />
                <label className="flex items-center gap-2 rounded-[1rem] border border-white/12 bg-white/8 px-3 py-2 text-xs text-white/80">
                  <input
                    type="checkbox"
                    checked={rememberDevice}
                    onChange={(e) => setRememberDevice(e.target.checked)}
                    className="h-4 w-4 rounded border-white/30 bg-transparent"
                  />
                  Auf diesem Geraet angemeldet bleiben (7 Tage)
                </label>
                <button
                  onClick={submit}
                  disabled={submitting || !configured}
                  className="w-full rounded-[1.2rem] bg-white px-4 py-3 text-xs font-extrabold uppercase tracking-[0.18em] text-slate-900 disabled:opacity-50"
                >
                  Unlock
                </button>
              </div>
              <div className="mt-6 grid grid-cols-2 gap-3">
                <div className="rounded-[1.2rem] border border-white/10 bg-white/8 p-4">
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-white/45">
                    Access Model
                  </div>
                  <div className="mt-2 text-sm font-semibold text-white">Single workspace code</div>
                </div>
                <div className="rounded-[1.2rem] border border-white/10 bg-white/8 p-4">
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-white/45">
                    Runtime
                  </div>
                  <div className="mt-2 text-sm font-semibold text-white">Web and phone ready</div>
                </div>
              </div>
              {status ? (
                <div className="mt-4 text-sm text-white/75">
                  {status.includes("500")
                    ? "Cannot connect to the server â€” check that the backend is running."
                    : status.includes("401") || status.includes("403")
                      ? "Incorrect code. Please try again."
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
  const watchlistTickerSymbols = (watchlist?.items || [])
    .filter((item) => item.kind === "ticker" && item.value)
    .map((item) => (item.value || "").toUpperCase());
  const portfolioTickerSymbols = portfolios
    .flatMap((portfolio) => portfolio.holdings || [])
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
  const favoriteTapeLabel = userTrackedSymbols.length ? "Watchlist / Portfolio" : "Market Snapshot";
  const {
    quotes: headerQuotes,
    connected: headerRealtimeConnected,
    connectionState: headerConnectionState,
    transportMode: headerTransportMode,
  } = useRealtimeFeed(favoriteSymbols, auth.authenticated);
  const portfolioSnapshotForChat = useMemo(() => {
    const holdings = portfolios.flatMap((portfolio) =>
      (portfolio.holdings || []).map((holding) => {
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
        portfolios: portfolios.length,
        total_value: totalValue || null,
        return_since_buy: totalReturn || null,
        return_since_buy_pct: totalCost > 0 ? (totalReturn / totalCost) * 100 : null,
      },
      holdings: holdings.slice(0, 50),
    };
  }, [headerQuotes, portfolios]);
  const briefSummaryForChat = useMemo(
    () =>
      globalBrief
        ? {
            headline: globalBrief.headline,
            opening_bias: globalBrief.opening_bias,
            macro_regime: globalBrief.macro_regime,
            trade_setups: (globalBrief.trade_setups || []).slice(0, 5),
            setup_board: globalBrief.setup_board || null,
            learning_adjustments: globalBrief.learning_adjustments || [],
            congress_watch: (globalBrief.congress_watch || []).slice(0, 5),
            event_pings: (globalBrief.event_pings || []).slice(0, 5),
            earnings_calendar: (globalBrief.earnings_calendar || []).slice(0, 8),
            earnings_results: (globalBrief.earnings_results || []).slice(0, 6),
            market_movers: {
              gainers: (globalBrief.market_movers?.gainers || []).slice(0, 6),
              losers: (globalBrief.market_movers?.losers || []).slice(0, 6),
            },
            product_catalysts: (globalBrief.product_catalysts || []).slice(0, 6),
            watchlist_impact: (globalBrief.watchlist_impact || []).slice(0, 8),
            prediction_signals: (globalBrief.prediction_signals || []).slice(0, 6),
          }
        : null,
    [globalBrief],
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

      await Promise.allSettled(
        paths.map((path) =>
          fetchJsonWithRetry<any>(path, undefined, {
            retries: 0,
            retryDelayMs: 250,
            timeoutMs: 12000,
          }),
        ),
      );
      if (cancelled) return;
      preloadLazyScreens();
    };

    const cancelIdle = scheduleIdle(() => {
      void warmBackgroundData();
    }, 8000);

    const interval = window.setInterval(() => {
      void warmBackgroundData();
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

    const loadGlobalBrief = async () => {
      const requestId = briefRequestIdRef.current + 1;
      briefRequestIdRef.current = requestId;
      if (!cancelled) setGlobalBriefStatus("loading");
      const timeoutGuard = window.setTimeout(() => {
        if (!cancelled && briefRequestIdRef.current === requestId) {
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
          setGlobalBriefStatus(fastPayload?.quality?.fallback ? "error" : "ready");
        }

        await new Promise((resolve) => window.setTimeout(resolve, 300));
        const payload = await fetchJsonWithRetry<any>("/api/market/morning-brief", undefined, {
          retries: 0,
          retryDelayMs: 250,
          timeoutMs: 8500,
        });
        if (!cancelled && briefRequestIdRef.current === requestId) {
          setGlobalBrief(payload);
          setSelectedGeoRegion(payload?.regions?.europe?.label || payload?.regions?.usa?.label || "Europe");
          setGlobalBriefStatus("ready");
        }
      } catch {
        if (!cancelled && briefRequestIdRef.current === requestId) {
          setGlobalBriefStatus("error");
        }
      } finally {
        window.clearTimeout(timeoutGuard);
      }
    };

    loadGlobalBrief();
    const interval = window.setInterval(loadGlobalBrief, 300000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [auth.authenticated, briefReloadTick]);

  // Trading edge â€” heavy payload, loaded separately with own spinner.
  // Refresh every 5 min; backend caches per-component (10min â€“ 6h).
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

  const refreshAuth = async () => {
    const payload = await fetchJsonWithRetry<any>("/api/auth/status", undefined, {
      retries: 1,
      retryDelayMs: 700,
    });
    setAuth({
      loading: false,
      authenticated: Boolean(payload.authenticated),
      configured: Boolean(payload.configured),
      profile: payload.profile || null,
    });
  };

  useEffect(() => {
    refreshAuth().catch(() => {
      setAuth({
        loading: false,
        authenticated: false,
        configured: false,
        profile: null,
      });
      setAuthStatus("Server-Status konnte nicht geladen werden.");
    });
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
      { retries: 1, retryDelayMs: 700 },
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
      setAuthStatus(err instanceof Error ? err.message : "Login failed.");
    }
  };

  const handleLogout = async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch {
      // Network error â€” clear local session anyway
    }
    setAuth((prev) => ({ ...prev, authenticated: false }));
    setAuthStatus("Abgemeldet.");
  };

  const shouldResolveBeforeAnalyze = (raw: string, normalized: string) => {
    const trimmed = raw.trim();
    if (!trimmed) return false;
    if (trimmed.includes("(") && trimmed.includes(")")) return false;
    if (/^[#$]?[A-Z0-9.^=-]{1,12}$/i.test(trimmed) && normalized.length <= 12) return false;
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
    try {
      searchTicker = await resolveTickerForAnalyze(ticker, controller);
      if (controller.signal.aborted || searchRequestIdRef.current !== requestId || !searchTicker) return;
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
        setError(`Analyse fuer ${searchTicker} dauert zu lange. Bitte noch einmal starten oder den Ticker direkt eingeben.`);
      } else {
        setError(`Analyse fuer ${searchTicker} konnte nicht geladen werden. ${message}`);
      }
    } finally {
      if (!controller.signal.aborted && searchRequestIdRef.current === requestId) {
        setLoading(false);
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
    return <div className="min-h-screen"><LoadingState /></div>;
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
  const geoRegions = [
    globalBrief?.regions?.asia,
    globalBrief?.regions?.europe,
    globalBrief?.regions?.usa,
  ].filter(Boolean);
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
  const briefCommandStats = [
    ["Setups", globalBrief?.trade_setups?.length || 0, "border-emerald-500/20 bg-emerald-500/10 text-emerald-700"],
    ["Events", globalBrief?.event_pings?.length || 0, "border-amber-500/20 bg-amber-500/10 text-amber-700"],
    ["Congress", globalBrief?.congress_watch?.length || 0, "border-sky-500/20 bg-sky-500/10 text-sky-700"],
    ["Earnings", globalBrief?.earnings_calendar?.length || 0, "border-indigo-500/20 bg-indigo-500/10 text-indigo-700"],
    ["Products", globalBrief?.product_catalysts?.length || 0, "border-fuchsia-500/20 bg-fuchsia-500/10 text-fuchsia-700"],
  ];
  const dashboardPriorityCards = [
    {
      label: "Jetzt wichtig",
      title:
        globalBrief?.opening_bias ||
        globalBrief?.headline ||
        "Noch kein klares Marktsignal",
      detail:
        globalBrief?.macro_regime
          ? `Regime: ${globalBrief.macro_regime}`
          : "Feed laedt Setups, Events und Portfolio-Bezug.",
      tone: "border-emerald-500/18 bg-emerald-500/8 text-emerald-800",
    },
    {
      label: "Naechster Check",
      title:
        globalBrief?.trade_setups?.[0]?.ticker ||
        globalBrief?.watchlist_impact?.[0]?.ticker ||
        globalBrief?.product_catalysts?.[0]?.ticker ||
        "Watchlist",
      detail:
        globalBrief?.trade_setups?.[0]?.thesis ||
        globalBrief?.watchlist_impact?.[0]?.reason ||
        globalBrief?.product_catalysts?.[0]?.title ||
        "Nur starke Signale werden in Analyzer/Markets vertieft.",
      tone: "border-sky-500/18 bg-sky-500/8 text-sky-800",
    },
    {
      label: "Risiko",
      title:
        globalBrief?.risk_note ||
        globalBrief?.event_pings?.[0]?.title ||
        "Keine harte Bremse",
      detail:
        globalBrief?.event_pings?.[0]?.summary ||
        globalBrief?.opening_read?.summary ||
        "Bei unklaren Daten erst beobachten, dann handeln.",
      tone: "border-amber-500/18 bg-amber-500/8 text-amber-800",
    },
  ];
  const favoriteTape = (
    <div className="overflow-x-auto no-scrollbar">
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
    <div className="ticker-marquee-wrap rounded-[1.15rem] border border-white/55 bg-white/46 px-2 py-2 sm:px-3">
      <div className="mb-2 flex flex-col items-start gap-2 px-1 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
        <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
          Market movers
        </div>
        <div className="flex w-full items-center justify-between gap-2 sm:w-auto sm:justify-end">
          <div className="rounded-full border border-black/8 bg-white/65 p-0.5">
            {(["1d", "1w", "1m"] as MoversWindow[]).map((window) => (
              <button
                key={window}
                type="button"
                onClick={() => setMarketMoversWindow(window)}
                className={`rounded-full px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] transition-colors ${
                  marketMoversWindow === window
                    ? "bg-[#101114] text-white"
                    : "text-slate-500 hover:text-slate-800"
                }`}
              >
                {window.toUpperCase()}
              </button>
            ))}
          </div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
            Winners, losers ({marketMoversWindow.toUpperCase()})
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
                {isWinner ? "Winner" : "Loser"}
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
                title={`Market data: ${headerStatusLabel}`}
              />
              <button
                onClick={() => setCurrency(currency === "USD" ? "EUR" : "USD")}
                aria-label={`Switch to ${currency === "USD" ? "EUR" : "USD"}`}
                className="mobile-topbar-button px-2.5 py-1.5 text-[10px]"
              >
                {currency}
              </button>
              <button
                onClick={toggleTheme}
                aria-label="Toggle dark mode"
                className="mobile-topbar-icon"
              >
                {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
              </button>
              <button
                onClick={handleInstallApp}
                aria-label="Install app"
                className={`mobile-topbar-icon ${
                  installPrompt.installed ? "text-emerald-700" : "text-slate-700"
                }`}
                title={installPrompt.installed ? "App ist installiert" : "App installieren"}
              >
                {installPrompt.installed ? <Smartphone size={14} /> : <Download size={14} />}
              </button>
              <button
                onClick={() => setIsHealthOpen(true)}
                aria-label="Open health center"
                className="mobile-topbar-icon"
                title="Health center"
              >
                <Activity size={14} />
              </button>
              <button
                onClick={handleLogout}
                aria-label="Lock workspace"
                className="flex h-8 w-8 items-center justify-center rounded-full bg-[#101114] text-white"
                title="Lock workspace"
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
                    Market Intelligence Terminal
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
                    aria-label="Switch to USD"
                    className={`rounded-[0.9rem] px-3 py-2 text-xs font-extrabold uppercase tracking-[0.18em] transition-all ${
                      currency === "USD" ? "bg-[#101114] text-white" : "text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    USD
                  </button>
                  <button
                    onClick={() => setCurrency("EUR")}
                    aria-label="Switch to EUR"
                    className={`rounded-[0.9rem] px-3 py-2 text-xs font-extrabold uppercase tracking-[0.18em] transition-all ${
                      currency === "EUR" ? "bg-[#101114] text-white" : "text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    EUR
                  </button>
                </div>
                {/* Mobile: compact toggle that cycles USD â†” EUR */}
                <button
                  onClick={() => setCurrency(currency === "USD" ? "EUR" : "USD")}
                  aria-label={`Switch to ${currency === "USD" ? "EUR" : "USD"}`}
                  className="rounded-[1rem] border border-[var(--line-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-xs font-extrabold uppercase tracking-[0.18em] text-[var(--text-primary)] transition-colors sm:hidden"
                >
                  {currency}
                </button>
                {/* Theme toggle */}
                <button
                  onClick={toggleTheme}
                  aria-label="Toggle dark mode"
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
                  {installPrompt.installed ? "Installed" : "Install"}
                </button>
                {/* Username â€” visible on all screen sizes */}
                <div className="max-w-[7.5rem] truncate rounded-[1rem] border border-[var(--line-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.16em] text-[var(--text-secondary)] sm:max-w-none sm:text-xs">
                  {auth.profile?.display_name || "Private"}
                </div>
                <button
                  onClick={() => setIsHealthOpen(true)}
                  className="whitespace-nowrap rounded-[1rem] border border-[var(--line-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.16em] text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-panel)] sm:px-4 sm:py-2.5 sm:text-xs sm:tracking-[0.18em]"
                >
                  Health
                </button>
                <button
                  onClick={handleLogout}
                  className="whitespace-nowrap rounded-[1rem] border border-[var(--line-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.16em] text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-panel)] sm:px-4 sm:py-2.5 sm:text-xs sm:tracking-[0.18em]"
                >
                  Lock
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
                      Optional Setup
                    </div>
                    <div className="mt-1 text-sm font-semibold text-slate-800">
                      First Run ist jetzt optional und blockiert den Start nicht mehr.
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
                  globalBrief={globalBrief}
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
                      feed {headerStatusLabel}
                    </div>
                    {globalBrief?.macro_regime ? (
                      <div className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-amber-700">
                        regime {globalBrief.macro_regime}
                      </div>
                    ) : null}
                  </div>
                </div>
                {globalBrief?.macro_regime ? (() => {
                  const r = (globalBrief.macro_regime || "").toLowerCase();
                  const isOn = r.includes("risk-on") || r.includes("on");
                  const isOff = r.includes("risk-off") || r.includes("off");
                  const icon = isOn ? "â†—" : isOff ? "â†˜" : "âš–";
                  const cls = isOn
                    ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700"
                    : isOff
                      ? "border-red-500/20 bg-red-500/10 text-red-700"
                      : "border-amber-500/20 bg-amber-500/10 text-amber-700";
                  return (
                    <div className={`hidden rounded-full border ${cls} px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em]`}>
                      {icon} {globalBrief.macro_regime}
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
                        Decision / Market / Brief
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => setIsChatOpen(true)}
                      className="rounded-full bg-[#101114] px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-white"
                    >
                      Ask Buddy
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
              <span>3 Prioritaeten, danach Details</span>
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
              <span>Deep Dive</span>
              <span>Marktbild links, Briefing rechts</span>
            </div>
            <div className="dashboard-intel-grid">
                {globalBrief && geoRegions.length ? (
                  <ErrorBoundary>
                    <Suspense fallback={<LoadingState />}>
                      <div className="dashboard-map-slot">
                        <WorldMarketMap
                          regions={geoRegions}
                          selectedRegion={selectedGeoRegion}
                          onSelectRegion={setSelectedGeoRegion}
                          news={globalBrief.top_news || []}
                          eventLayer={globalBrief.event_layer || []}
                          eventPings={globalBrief.event_pings || []}
                          watchlistImpact={globalBrief.watchlist_impact || []}
                          contrarianSignals={globalBrief.contrarian_signals || []}
                          openingTimeline={globalBrief.opening_timeline || []}
                          onAnalyze={(t) => {
                            setActiveTab("analyze");
                            handleSearch(t);
                          }}
                          focusTicker={analysis?.ticker}
                        />
                      </div>
                    </Suspense>
                  </ErrorBoundary>
                ) : globalBriefStatus === "loading" || globalBriefStatus === "idle" ? (
                  <LoadingState />
                ) : (
                  <section className="surface-panel rounded-[2rem] p-6">
                    <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                      World Map Feed
                    </div>
                    <div className="mt-3 text-base font-semibold text-slate-800">
                      Live-Morning-Brief aktuell nicht verfuegbar.
                    </div>
                    <p className="mt-2 text-sm leading-6 text-slate-600">
                      Datenquelle antwortet gerade langsam oder unvollstaendig. Du kannst sofort neu laden.
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
                {globalBrief ? (
                  <ErrorBoundary>
                    <Suspense fallback={<LoadingState />}>
                      <div className="dashboard-brief-slot">
                        <MorningBriefPanel
                          brief={globalBrief}
                          onAnalyze={(t) => {
                            setActiveTab("analyze");
                            handleSearch(t);
                          }}
                          hideMap
                        />
                      </div>
                    </Suspense>
                  </ErrorBoundary>
                ) : (
                  <LoadingState />
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

            {loading && <LoadingState />}

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
                    Ready Desk
                  </div>
                  <h3 className="mt-3 text-2xl text-slate-900">
                    Search first, then move straight into analysis, signals and execution context.
                  </h3>
                  <div className="mt-6 grid gap-3 sm:grid-cols-3">
                    {[
                      {
                        title: "Public Signals",
                        body: "Berkshire, Congress und weitere oeffentliche Filings mit sichtbarem Delay.",
                        cta: "Open Markets",
                        action: () => setActiveTab("discovery" as Tab),
                      },
                      {
                        title: "Decision Clarity",
                        body: "Ruhigere Scores und bessere Priorisierung von Risiko, Bewertung und Momentum.",
                        cta: "Run Analysis",
                        action: () => {
                          searchInputRef.current?.focus();
                        },
                      },
                      {
                        title: "Private Access",
                        body: "Single-User-Hardening mit Login, lokaler Session und gesperrten Triggern.",
                        cta: "Open Portfolio",
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
                    Workflow
                  </div>
                  <div className="mt-4 space-y-3">
                    {[
                      {
                        copy: "1. Search a ticker, ETF or crypto pair.",
                        cta: "Focus Search",
                        action: () => {
                          const searchInput = document.querySelector<HTMLInputElement>('input[placeholder="AAPL, NVDA, ASML, BTC-USD"]');
                          searchInput?.focus();
                        },
                      },
                      {
                        copy: "2. Read the live quote, score context and risk profile.",
                        cta: "Open Markets",
                        action: () => setActiveTab("discovery" as Tab),
                      },
                      {
                        copy: "3. Move into paper trading or signals only if the setup holds.",
                        cta: "Open Portfolio",
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
                  {portfolioDataSourceMessage || "Serverdaten sind gerade nicht verfuegbar."}
                </p>
              </div>
            ) : null}
            {needsRestore && cachedPortfolios.length > 0 && (
              <div className="mb-4 rounded-[1.4rem] border border-amber-400/30 bg-amber-50 p-5 shadow-sm">
                <div className="flex flex-wrap items-start gap-4">
                  <div className="flex-1">
                    <div className="text-sm font-extrabold text-amber-800">ðŸ“¦ Portfolios wiederherstellen</div>
                    <p className="mt-1 text-sm text-amber-700">
                      Der Server wurde neu gestartet und die Daten wurden zurÃ¼ckgesetzt.
                      Es wurden <strong>{cachedPortfolios.length} Portfolio{cachedPortfolios.length > 1 ? "s" : ""}</strong> lokal gespeichert â€”
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
          Broker Freund {__APP_VERSION__} beta. Local single-user workspace. Data is informational only.
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
                  Wenn kein Install-Dialog erscheint, nutze im Browser-Menue den Punkt
                  "App installieren" oder "Zum Startbildschirm hinzufuegen".
                </p>
              </div>
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <div className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4 text-sm text-slate-700">
                Desktop: Chrome oder Edge Menue oeffnen und "App installieren" waehlen.
              </div>
              <div className="rounded-[1.2rem] border border-black/8 bg-white/70 p-4 text-sm text-slate-700">
                iPhone: Teilen-Dialog oeffnen und "Zum Home-Bildschirm" waehlen.
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
