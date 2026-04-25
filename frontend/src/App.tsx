import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { ComponentType, LazyExoticComponent } from "react";
import SearchBar from "./components/SearchBar";
import LoadingState from "./components/LoadingState";
import ErrorBoundary from "./components/ErrorBoundary";
import AdminHealthPanel from "./components/AdminHealthPanel";
import { usePortfolios } from "./hooks/usePortfolios";
import { CurrencyProvider, useCurrency } from "./context/CurrencyContext";
import { ThemeProvider, useTheme } from "./context/ThemeContext";
import useRealtimeFeed from "./hooks/useRealtimeFeed";
import { fetchJsonWithRetry } from "./lib/api";
import { ArrowDownRight, ArrowUpRight, Bell, BellOff, BellRing, Moon, Sun } from "lucide-react";
import usePushNotifications from "./hooks/usePushNotifications";

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
const MyRadar = lazyWithChunkRetry(() => import("./components/MyRadar"));
const WorldMarketMap = lazyWithChunkRetry(() => import("./components/WorldMarketMap"));
const TradingEdgePanel = lazyWithChunkRetry(() => import("./components/TradingEdgePanel"));
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
  safeImport(() => import("./components/MyRadar"));
  safeImport(() => import("./components/WorldMarketMap"));
  safeImport(() => import("./components/TradingEdgePanel"));
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
        {formatTickerPrice(quote?.price)}
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
                    ? "Cannot connect to the server — check that the backend is running."
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
  const push = usePushNotifications();
  const [activeTab, setActiveTab] = useState<Tab>(() => {
    return (localStorage.getItem("activeTab") as Tab) || "dashboard";
  });
  const [analysis, setAnalysis] = useState<AnalysisData | null>(() => {
    const saved = localStorage.getItem("lastAnalysis");
    return saved ? JSON.parse(saved) : null;
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isHealthOpen, setIsHealthOpen] = useState(false);
  const [showNotifHelp, setShowNotifHelp] = useState(false);
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
    createPortfolio,
    deletePortfolio,
    addHolding,
    updateHolding,
    removeHolding,
    needsRestore,
    cachedPortfolios,
    restoreFromCache,
    discardRestore,
  } = usePortfolios(auth.authenticated);

  const { currency, setCurrency } = useCurrency();
  const watchlistTickerSymbols = (watchlist?.items || [])
    .filter((item) => item.kind === "ticker" && item.value)
    .map((item) => (item.value || "").toUpperCase());
  const portfolioTickerSymbols = portfolios
    .flatMap((portfolio) => portfolio.holdings || [])
    .map((holding) => (holding.ticker || "").toUpperCase())
    .filter(Boolean);
  const headerSymbols = Array.from(
    new Set([
      analysis?.ticker?.toUpperCase(),
      ...watchlistTickerSymbols,
      ...portfolioTickerSymbols,
    ].filter(Boolean) as string[]),
  ).slice(0, 10);
  const headerFallbackSymbols = ["SPY", "QQQ", "AAPL", "NVDA", "BTC-USD", "GLD"];
  const favoriteSymbols = headerSymbols.length ? headerSymbols : headerFallbackSymbols;
  const {
    quotes: headerQuotes,
    connected: headerRealtimeConnected,
    connectionState: headerConnectionState,
    transportMode: headerTransportMode,
  } = useRealtimeFeed(favoriteSymbols, auth.authenticated);
  const portfolioSnapshotForChat = useMemo(() => {
    const holdings = portfolios.flatMap((portfolio) =>
      (portfolio.holdings || []).map((holding) => ({
        ticker: holding.ticker,
        shares: holding.shares,
        buy_price: holding.buyPrice ?? null,
        portfolio: portfolio.name,
      })),
    );
    return {
      summary: {
        num_holdings: holdings.length,
        portfolios: portfolios.length,
      },
      holdings: holdings.slice(0, 50),
    };
  }, [portfolios]);
  const briefSummaryForChat = useMemo(
    () =>
      globalBrief
        ? {
            headline: globalBrief.headline,
            opening_bias: globalBrief.opening_bias,
            macro_regime: globalBrief.macro_regime,
          }
        : null,
    [globalBrief],
  );

  useEffect(() => {
    if (!auth.authenticated) return;

    let cancelled = false;

    const loadWatchlist = async () => {
      try {
        const payload = await fetchJsonWithRetry<WatchlistSnapshot>("/api/signals/watchlist", undefined, {
          retries: 1,
          retryDelayMs: 700,
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
            retries: 1,
            retryDelayMs: 700,
          }),
          fetchJsonWithRetry<any[]>(`/api/discovery/losers?window=${marketMoversWindow}`, undefined, {
            retries: 1,
            retryDelayMs: 700,
          }),
        ]);

        if (cancelled) return;

        const winners = (gainers || []).slice(0, 6).map((item) => ({
          symbol: item.ticker || item.symbol,
          price: item.price ?? item.current_price ?? null,
          change: item.change ?? item.change_percent ?? item.change_1d ?? null,
          label: item.name || item.label,
          side: "winner" as const,
        }));

        const losersTape = (losers || []).slice(0, 6).map((item) => ({
          symbol: item.ticker || item.symbol,
          price: item.price ?? item.current_price ?? null,
          change: item.change ?? item.change_percent ?? item.change_1d ?? null,
          label: item.name || item.label,
          side: "loser" as const,
        }));

        setTapeMovers([...winners, ...losersTape].filter((item) => item.symbol));
      } catch {
        if (!cancelled) {
          setTapeMovers([]);
        }
      }
    };

    loadMovers();
    loadWatchlist();
    const interval = window.setInterval(loadMovers, 60000);
    const watchlistInterval = window.setInterval(loadWatchlist, 90000);
    return () => {
      cancelled = true;
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
    loadSignalContext();
    const interval = window.setInterval(loadSignalContext, 120000);
    return () => {
      cancelled = true;
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
        "/api/market/morning-brief",
        "/api/signals/scoreboard",
        "/api/signals/watchlist",
        `/api/discovery/gainers?window=${marketMoversWindow}`,
        `/api/discovery/losers?window=${marketMoversWindow}`,
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
    }, 1800);

    const interval = window.setInterval(() => {
      void warmBackgroundData();
    }, 180000);

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
      }, 12000);
      try {
        const payload = await fetchJsonWithRetry<any>("/api/market/morning-brief", undefined, {
          retries: 1,
          retryDelayMs: 700,
          timeoutMs: 12000,
        });
        if (!cancelled && briefRequestIdRef.current === requestId) {
          setGlobalBrief(payload);
          setSelectedGeoRegion(payload?.regions?.europe?.label || payload?.regions?.usa?.label || "Europe");
          setGlobalBriefStatus("ready");
        }
      } catch {
        if (!cancelled && briefRequestIdRef.current === requestId) {
          setGlobalBrief(null);
          setGlobalBriefStatus("error");
        }
      } finally {
        window.clearTimeout(timeoutGuard);
      }
    };

    loadGlobalBrief();
    const interval = window.setInterval(loadGlobalBrief, 120000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [auth.authenticated, briefReloadTick]);

  // Trading edge — heavy payload, loaded separately with own spinner.
  // Refresh every 5 min; backend caches per-component (10min – 6h).
  useEffect(() => {
    if (!auth.authenticated) return;
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
    loadEdge();
    const interval = window.setInterval(loadEdge, 300000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [auth.authenticated]);

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
      // Network error — clear local session anyway
    }
    setAuth((prev) => ({ ...prev, authenticated: false }));
    setAuthStatus("Abgemeldet.");
  };

  const handleSearch = async (ticker: string) => {
    const searchTicker = ticker.trim().toUpperCase();
    if (!searchTicker) return;
    const requestId = searchRequestIdRef.current + 1;
    searchRequestIdRef.current = requestId;
    searchAbortRef.current?.abort();
    const controller = new AbortController();
    searchAbortRef.current = controller;

    setLoading(true);
    setError(null);
    setAnalysis(null);
    setActiveTab("analyze");

    try {
      const data = await fetchJsonWithRetry<any>(
        `/api/analyze/${encodeURIComponent(searchTicker)}`,
        { signal: controller.signal },
        { retries: 0, retryDelayMs: 400, timeoutMs: 15000 },
      );
      if (controller.signal.aborted || searchRequestIdRef.current !== requestId) return;
      setAnalysis(data);
    } catch (err) {
      if (controller.signal.aborted || searchRequestIdRef.current !== requestId) return;
      const message = err instanceof Error ? err.message : "An error occurred";
      if (message.toLowerCase().includes("timeout")) {
        setError("Analyse-Request Timeout. Bitte erneut versuchen.");
      } else {
        setError(message);
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
  const favoriteTape = (
    <div className="overflow-x-auto no-scrollbar">
      <div className="flex min-w-max items-center gap-2">
        <div className={`rounded-full px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] ${headerRealtimeConnected ? "bg-emerald-500/10 text-emerald-700" : "bg-white/70 text-slate-500 ring-1 ring-black/6"}`}>
          {headerRealtimeConnected ? `Favorites ${headerConnectionState}` : `Favorites ${headerTransportMode}`}
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
                  {formatTickerPrice(item.price)}
                </span>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  ) : null;
  const mobileMarketTape = (
    <section className="mobile-market-tape md:hidden">
      <div className="rounded-[1.25rem] border border-black/8 bg-white/72 p-2.5 shadow-[0_12px_30px_rgba(17,24,39,0.06)] backdrop-blur-xl">
        {favoriteTape}
        {activeTab === "dashboard" && moversTape ? (
          <div className="mt-2 max-h-[8.5rem] overflow-hidden">
            {moversTape}
          </div>
        ) : null}
      </div>
    </section>
  );

  return (
    <div className="min-h-screen pb-24 text-[var(--text-primary)] md:pb-8">
      <header className="sticky top-0 z-50 header-gradient backdrop-blur-xl">
        <div className="mobile-topbar-shell px-3 pb-2 pt-[calc(0.55rem+env(safe-area-inset-top))] md:hidden">
          <div className="mobile-topbar flex h-[58px] items-center justify-between gap-2 rounded-[1.25rem] border border-white/70 bg-white/86 px-3 shadow-[0_14px_34px_rgba(17,24,39,0.09)] backdrop-blur-xl">
            <div className="flex min-w-0 items-center gap-2.5">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[0.95rem] bg-[#101114] text-white">
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l5-5 4 4 7-8" />
                </svg>
              </div>
              <div className="min-w-0">
                <div className="truncate text-[9px] font-extrabold uppercase tracking-[0.2em] text-slate-500">
                  Broker Freund
                </div>
                <div className="truncate text-[15px] font-black leading-tight text-slate-950">
                  {activeNavItem.label}
                </div>
              </div>
            </div>

            <div className="flex shrink-0 items-center gap-1.5">
              <span
                className={`flex h-2.5 w-2.5 rounded-full ${
                  headerRealtimeConnected ? "bg-emerald-500 shadow-[0_0_0_4px_rgba(16,185,129,0.12)]" : "bg-amber-500"
                }`}
                title={`Market data: ${headerStatusLabel}`}
              />
              <button
                onClick={() => setCurrency(currency === "USD" ? "EUR" : "USD")}
                aria-label={`Switch to ${currency === "USD" ? "EUR" : "USD"}`}
                className="rounded-full border border-black/8 bg-white/76 px-2.5 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-800"
              >
                {currency}
              </button>
              <button
                onClick={toggleTheme}
                aria-label="Toggle dark mode"
                className="flex h-8 w-8 items-center justify-center rounded-full border border-black/8 bg-white/76 text-slate-600"
              >
                {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
              </button>
              <button
                onClick={() => setIsHealthOpen(true)}
                aria-label="Open health center"
                className="flex h-8 items-center justify-center rounded-full border border-black/8 bg-white/76 px-2 text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-700"
              >
                Health
              </button>
              <button
                onClick={handleLogout}
                aria-label="Lock workspace"
                className="flex h-8 items-center justify-center rounded-full bg-[#101114] px-2.5 text-[9px] font-extrabold uppercase tracking-[0.14em] text-white"
              >
                Lock
              </button>
            </div>
          </div>
        </div>

        <div className="layout-shell hidden px-3 pt-3 pb-3 md:block sm:px-6 xl:px-8 2xl:px-10">
          <div className="app-shell app-shell-header rounded-[1.7rem] px-3 py-3 sm:rounded-[2.1rem] sm:px-5">
            <div className="flex items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#101114] text-white">
                  <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l5-5 4 4 7-8" />
                  </svg>
                </div>
                <div className="min-w-0">
                  <div className="truncate text-sm font-extrabold uppercase tracking-[0.28em] text-slate-500">
                    Broker Freund
                  </div>
                  <div className="truncate text-lg font-semibold text-slate-900">
                    Market Intelligence Terminal
                  </div>
                </div>
              </div>

              <div className="hidden items-center gap-2 rounded-[1.2rem] bg-[var(--bg-elevated)] p-1.5 ring-1 ring-[var(--line-subtle)] md:flex">
                {NAV_ITEMS.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => selectTab(item.id)}
                    className={`rounded-[1rem] px-4 py-2.5 text-sm font-bold transition-all ${
                      activeTab === item.id
                        ? "bg-[#101114] text-white shadow-[0_10px_30px_rgba(17,24,39,0.18)]"
                        : "text-slate-600 hover:bg-black/[0.04] hover:text-slate-900"
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>

              <div className="flex flex-wrap items-center justify-end gap-2 md:flex-nowrap">
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
                {/* Mobile: compact toggle that cycles USD ↔ EUR */}
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
                {/* Push notifications toggle */}
                {push.state !== "unsupported" && (
                  <button
                    onClick={() => {
                      if (push.state === "subscribed") push.unsubscribe();
                      else if (push.state === "denied") setShowNotifHelp(true);
                      else push.subscribe();
                    }}
                    disabled={push.loading}
                    aria-label="Toggle push notifications"
                    title={
                      push.state === "subscribed"
                        ? "Push aktiv — klicke zum Deaktivieren"
                        : push.state === "denied"
                          ? "Notifications blockiert — klicken für Hilfe"
                          : "Push Notifications aktivieren"
                    }
                    className={`rounded-[1rem] border p-2.5 transition-colors ${
                      push.state === "subscribed"
                        ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700"
                        : push.state === "denied"
                          ? "cursor-pointer border-amber-500/20 bg-amber-500/10 text-amber-600 hover:bg-amber-500/20"
                          : "border-[var(--line-subtle)] bg-[var(--bg-elevated)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                    }`}
                  >
                    {push.loading ? (
                      <BellRing size={16} className="animate-pulse" />
                    ) : push.state === "subscribed" ? (
                      <Bell size={16} />
                    ) : push.state === "denied" ? (
                      <BellOff size={16} />
                    ) : (
                      <Bell size={16} />
                    )}
                  </button>
                )}
                {/* Username — visible on all screen sizes */}
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
            <div className="mt-3 space-y-2">
              {favoriteTape}
              {moversTape}
            </div>
          </div>
        </div>
      </header>

      <main
        className={`content-shell px-4 pb-[11rem] pt-3 transition-all duration-300 sm:px-6 sm:pb-8 md:pt-6 xl:px-8 2xl:px-10 ${
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

            <section className="surface-panel rounded-[2rem] p-5 sm:p-7">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                    Dashboard
                  </div>
                  <h2 className="mt-2 text-3xl text-slate-900">
                    World watch, sectors and live trading edge
                  </h2>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
                    Übersicht über globale Märkte, Wars / Wahlen / Energie / Policy events
                    sowie Squeeze-, Insider- und Options-Signale auf einen Blick.
                  </p>
                </div>
                {globalBrief?.macro_regime ? (() => {
                  const r = (globalBrief.macro_regime || "").toLowerCase();
                  const isOn = r.includes("risk-on") || r.includes("on");
                  const isOff = r.includes("risk-off") || r.includes("off");
                  const icon = isOn ? "↗" : isOff ? "↘" : "⚖";
                  const cls = isOn
                    ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700"
                    : isOff
                      ? "border-red-500/20 bg-red-500/10 text-red-700"
                      : "border-amber-500/20 bg-amber-500/10 text-amber-700";
                  return (
                    <div className={`rounded-full border ${cls} px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em]`}>
                      {icon} {globalBrief.macro_regime}
                    </div>
                  );
                })() : null}
              </div>
            </section>

            <div className="grid items-start gap-6 2xl:grid-cols-[minmax(0,1.35fr)_minmax(440px,0.65fr)]">
              <div className="space-y-6">
                {globalBrief && geoRegions.length ? (
                  <ErrorBoundary>
                    <Suspense fallback={<LoadingState />}>
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

                {(tradingEdge || tradingEdgeLoading) ? (
                  <ErrorBoundary>
                    <Suspense fallback={<LoadingState />}>
                      <TradingEdgePanel
                        edge={tradingEdge}
                        loading={tradingEdgeLoading && !tradingEdge}
                        onSelectTicker={(t) => {
                          setActiveTab("analyze");
                          handleSearch(t);
                        }}
                      />
                    </Suspense>
                  </ErrorBoundary>
                ) : null}
              </div>

              <div className="space-y-6 2xl:sticky 2xl:top-40">
                {globalBrief ? (
                  <ErrorBoundary>
                    <Suspense fallback={<LoadingState />}>
                      <MorningBriefPanel
                        brief={globalBrief}
                        onAnalyze={(t) => {
                          setActiveTab("analyze");
                          handleSearch(t);
                        }}
                        hideMap
                      />
                    </Suspense>
                  </ErrorBoundary>
                ) : (
                  <LoadingState />
                )}
              </div>
            </div>
          </div>
        ) : activeTab === "analyze" ? (
          <>
            {showHero && (
              <section className="mb-8 space-y-6">
                <ErrorBoundary>
                  <Suspense fallback={<LoadingState />}>
                    <MyRadar onAnalyze={handleSearch} onOpenSignals={() => setActiveTab("discovery")} />
                  </Suspense>
                </ErrorBoundary>
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
            {needsRestore && cachedPortfolios.length > 0 && (
              <div className="mb-4 rounded-[1.4rem] border border-amber-400/30 bg-amber-50 p-5 shadow-sm">
                <div className="flex flex-wrap items-start gap-4">
                  <div className="flex-1">
                    <div className="text-sm font-extrabold text-amber-800">📦 Portfolios wiederherstellen</div>
                    <p className="mt-1 text-sm text-amber-700">
                      Der Server wurde neu gestartet und die Daten wurden zurückgesetzt.
                      Es wurden <strong>{cachedPortfolios.length} Portfolio{cachedPortfolios.length > 1 ? "s" : ""}</strong> lokal gespeichert —
                      sollen sie wiederhergestellt werden?
                    </p>
                    <div className="mt-1 text-xs text-amber-600">
                      {cachedPortfolios.map(p => `${p.name} (${p.holdings.length} Positionen)`).join(" · ")}
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
                onCreatePortfolio={createPortfolio}
                onDeletePortfolio={deletePortfolio}
                onAddHolding={addHolding}
                onUpdateHolding={updateHolding}
                onRemoveHolding={removeHolding}
                onAnalyzeStock={(ticker) => {
                  setActiveTab("analyze");
                  handleSearch(ticker);
                }}
              />
            </Suspense>
          </ErrorBoundary>
        )}
      </main>

      <nav className="fixed bottom-[calc(0.75rem+env(safe-area-inset-bottom))] left-1/2 z-50 w-[calc(100%-1rem)] max-w-md -translate-x-1/2 rounded-[1.6rem] border border-black/8 bg-[rgba(255,255,255,0.94)] p-2 shadow-[0_20px_60px_rgba(17,24,39,0.14)] backdrop-blur-xl md:hidden">
        <div className="grid grid-cols-4 gap-1">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              onClick={() => selectTab(item.id)}
              className={`min-w-0 rounded-[1rem] px-2 py-3 text-center text-[10px] font-extrabold uppercase tracking-[0.14em] transition-all ${
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
          Local single-user workspace. Data provided for informational purposes only.
        </div>
      </footer>

      <ErrorBoundary fallback={<></>}>
        <Suspense fallback={null}>
          <BrokerChat
            currentTicker={analysis?.ticker}
            portfolioSnapshot={portfolioSnapshotForChat}
            liveQuotes={headerQuotes}
            signalScore={signalScoreContext}
            morningBriefSummary={briefSummaryForChat}
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

      {/* Push notifications blocked — help modal */}
      {showNotifHelp && (
        <div
          className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 backdrop-blur-sm"
          onClick={() => setShowNotifHelp(false)}
        >
          <div
            className="surface-panel mx-4 w-full max-w-sm rounded-[2rem] p-8 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="text-lg font-black text-[var(--text-primary)]">🔔 Benachrichtigungen entsperren</div>
            <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
              Dein Browser hat Benachrichtigungen für diese Seite blockiert. So entsperrst du sie:
            </p>
            <ol className="mt-4 space-y-3 text-sm text-[var(--text-primary)]">
              <li className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--accent-soft)] text-[11px] font-extrabold text-[var(--accent)]">1</span>
                <span>Klicke auf das <strong>🔒 Schloss-Symbol</strong> links in der Adressleiste</span>
              </li>
              <li className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--accent-soft)] text-[11px] font-extrabold text-[var(--accent)]">2</span>
                <span>Wähle <strong>„Benachrichtigungen"</strong></span>
              </li>
              <li className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--accent-soft)] text-[11px] font-extrabold text-[var(--accent)]">3</span>
                <span>Stelle es auf <strong>„Erlauben"</strong> um</span>
              </li>
              <li className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--accent-soft)] text-[11px] font-extrabold text-[var(--accent)]">4</span>
                <span>Lade die Seite neu — die Glocke wird dann aktiv</span>
              </li>
            </ol>
            <button
              onClick={() => setShowNotifHelp(false)}
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
