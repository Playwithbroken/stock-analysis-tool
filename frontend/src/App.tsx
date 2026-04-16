import { lazy, Suspense, useEffect, useRef, useState } from "react";
import SearchBar from "./components/SearchBar";
import LoadingState from "./components/LoadingState";
import ErrorBoundary from "./components/ErrorBoundary";
import { usePortfolios } from "./hooks/usePortfolios";
import { CurrencyProvider, useCurrency } from "./context/CurrencyContext";
import { ThemeProvider } from "./context/ThemeContext";
import useRealtimeFeed from "./hooks/useRealtimeFeed";
import { fetchJsonWithRetry } from "./lib/api";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";

const AnalysisResult = lazy(() => import("./components/AnalysisResult"));
const PortfolioView = lazy(() => import("./components/PortfolioView"));
const DiscoveryPanel = lazy(() => import("./components/DiscoveryPanel"));
const BrokerChat = lazy(() => import("./components/BrokerChat"));
const MyRadar = lazy(() => import("./components/MyRadar"));
const WorldMarketMap = lazy(() => import("./components/WorldMarketMap"));
const TradingEdgePanel = lazy(() => import("./components/TradingEdgePanel"));

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
  profile: { display_name?: string } | null;
}

interface WatchlistSnapshot {
  items?: Array<{
    kind?: string;
    value?: string;
  }>;
}

type Tab = "dashboard" | "analyze" | "discovery" | "portfolio";

const NAV_ITEMS: Array<{ id: Tab; label: string; short: string }> = [
  { id: "dashboard", label: "Dashboard", short: "Home" },
  { id: "analyze", label: "Analyzer", short: "Analyze" },
  { id: "discovery", label: "Markets", short: "Markets" },
  { id: "portfolio", label: "Portfolio", short: "Portfolio" },
];

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
  onLogin: (password: string) => Promise<void>;
  status: string;
}) {
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!password.trim()) return;
    setSubmitting(true);
    try {
      await onLogin(password);
      setPassword("");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[var(--bg-base)] px-4 py-10 text-[var(--text-primary)] sm:px-6">
      <div className="layout-shell max-w-[1400px]">
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
                  className="w-full rounded-[1.2rem] border border-white/10 bg-white/8 px-4 py-3 text-sm font-semibold text-white placeholder:text-white/35"
                  placeholder="6-digit access code"
                />
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
  const [auth, setAuth] = useState<AuthState>({
    loading: true,
    authenticated: false,
    configured: false,
    profile: null,
  });
  const [authStatus, setAuthStatus] = useState("");
  const [tapeMovers, setTapeMovers] = useState<TapeMover[]>([]);
  const [globalBrief, setGlobalBrief] = useState<any>(null);
  const [tradingEdge, setTradingEdge] = useState<any>(null);
  const [tradingEdgeLoading, setTradingEdgeLoading] = useState(false);
  const [selectedGeoRegion, setSelectedGeoRegion] = useState("Europe");
  const [watchlist, setWatchlist] = useState<WatchlistSnapshot | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const {
    portfolios,
    createPortfolio,
    deletePortfolio,
    addHolding,
    removeHolding,
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
  const { quotes: headerQuotes, connected: headerRealtimeConnected } = useRealtimeFeed(favoriteSymbols, auth.authenticated);

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
          fetchJsonWithRetry<any[]>("/api/discovery/gainers", undefined, {
            retries: 1,
            retryDelayMs: 700,
          }),
          fetchJsonWithRetry<any[]>("/api/discovery/losers", undefined, {
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
  }, [auth.authenticated]);

  useEffect(() => {
    if (!auth.authenticated) return;

    let cancelled = false;

    const loadGlobalBrief = async () => {
      try {
        const payload = await fetchJsonWithRetry<any>("/api/market/morning-brief", undefined, {
          retries: 1,
          retryDelayMs: 700,
        });
        if (!cancelled) {
          setGlobalBrief(payload);
          setSelectedGeoRegion(payload?.regions?.europe?.label || payload?.regions?.usa?.label || "Europe");
        }
      } catch {
        if (!cancelled) {
          setGlobalBrief(null);
        }
      }
    };

    loadGlobalBrief();
    const interval = window.setInterval(loadGlobalBrief, 120000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [auth.authenticated]);

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
    if (analysis) {
      localStorage.setItem("lastAnalysis", JSON.stringify(analysis));
    }
  }, [analysis]);

  const handleLogin = async (password: string) => {
    setAuthStatus("");
    const payload = await fetchJsonWithRetry<any>(
      "/api/auth/login",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
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

  const loginAction = async (password: string) => {
    try {
      await handleLogin(password);
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
    setLoading(true);
    setError(null);
    setAnalysis(null);
    setActiveTab("analyze");

    try {
      const response = await fetch(`/api/analyze/${ticker}`);

      if (!response.ok) {
        let errorMsg = "Failed to fetch analysis";
        try {
          const errData = await response.json();
          errorMsg = errData.detail || errorMsg;
        } catch {
          errorMsg = `Server Error: ${response.status} ${response.statusText}`;
        }
        throw new Error(errorMsg);
      }

      const data = await response.json();
      setAnalysis(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred");
    } finally {
      setLoading(false);
    }
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

  return (
    <div className="min-h-screen pb-24 text-[var(--text-primary)] md:pb-8">
      <header className="sticky top-0 z-50 bg-[linear-gradient(180deg,rgba(250,248,243,0.98),rgba(250,248,243,0.94)_72%,rgba(250,248,243,0.82))] backdrop-blur-xl">
        <div className="layout-shell px-4 pt-4 pb-3 sm:px-6 xl:px-8 2xl:px-10">
          <div className="app-shell app-shell-header rounded-[2.1rem] px-4 py-3 sm:px-5">
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

              <div className="hidden items-center gap-2 rounded-[1.2rem] bg-white/70 p-1.5 ring-1 ring-black/6 md:flex">
                {NAV_ITEMS.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => setActiveTab(item.id)}
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

              <div className="flex items-center gap-2">
                {/* Desktop: full USD / EUR toggle */}
                <div className="hidden rounded-[1.1rem] bg-white/70 p-1 ring-1 ring-black/6 sm:flex">
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
                  className="rounded-[1rem] border border-black/8 bg-white/70 px-3 py-2 text-xs font-extrabold uppercase tracking-[0.18em] text-slate-800 transition-colors hover:bg-white sm:hidden"
                >
                  {currency}
                </button>
                {/* Username — visible on all screen sizes */}
                <div className="rounded-[1rem] border border-black/8 bg-white/70 px-3 py-2 text-xs font-extrabold uppercase tracking-[0.16em] text-slate-600">
                  {auth.profile?.display_name || "Private"}
                </div>
                <button
                  onClick={() => setIsChatOpen(true)}
                  className="rounded-[1rem] border border-black/8 bg-white/70 px-4 py-2.5 text-xs font-extrabold uppercase tracking-[0.18em] text-slate-800 transition-colors hover:bg-white"
                >
                  AI Desk
                </button>
                <button
                  onClick={handleLogout}
                  className="rounded-[1rem] border border-black/8 bg-white/70 px-4 py-2.5 text-xs font-extrabold uppercase tracking-[0.18em] text-slate-800 transition-colors hover:bg-white"
                >
                  Lock
                </button>
              </div>
            </div>
            <div className="mt-3 space-y-2">
              <div className="overflow-x-auto no-scrollbar">
                <div className="flex min-w-max items-center gap-2">
                  <div className={`rounded-full px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] ${headerRealtimeConnected ? "bg-emerald-500/10 text-emerald-700" : "bg-white/70 text-slate-500 ring-1 ring-black/6"}`}>
                    {headerRealtimeConnected ? "Favorites feed" : "Favorites snapshot"}
                  </div>
                  {favoriteSymbols.map((symbol) => (
                    <HeaderTickerChip key={symbol} symbol={symbol} quote={headerQuotes[symbol]} />
                  ))}
                </div>
              </div>

              {tapeMovers.length ? (
                <div className="ticker-marquee-wrap rounded-[1.15rem] border border-white/55 bg-white/46 px-3 py-2">
                  <div className="mb-2 flex items-center justify-between gap-3 px-1">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                      Market movers
                    </div>
                    <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                      Winners, losers, broad tape
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
              ) : null}
            </div>
          </div>
        </div>
      </header>

      <main
        className={`content-shell px-4 py-6 transition-all duration-300 sm:px-6 xl:px-8 2xl:px-10 ${
          isChatOpen ? "xl:pr-[32rem] 2xl:pr-[36rem]" : ""
        }`}
      >
        {activeTab === "dashboard" ? (
          <div className="space-y-8">
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
                {globalBrief?.macro_regime ? (
                  <div className="rounded-full border border-black/8 bg-white/75 px-3 py-1 text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                    {globalBrief.macro_regime}
                  </div>
                ) : null}
              </div>
            </section>

            {globalBrief && geoRegions.length ? (
              <ErrorBoundary>
                <Suspense fallback={<LoadingState />}>
                  <WorldMarketMap
                    regions={geoRegions}
                    selectedRegion={selectedGeoRegion}
                    onSelectRegion={setSelectedGeoRegion}
                    news={globalBrief.top_news || []}
                    eventLayer={globalBrief.event_layer || []}
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
            ) : !globalBrief ? (
              <LoadingState />
            ) : null}

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
              <DiscoveryPanel onAnalyze={handleSearch} />
            </Suspense>
          </ErrorBoundary>
        ) : (
          <ErrorBoundary>
            <Suspense fallback={<LoadingState />}>
              <PortfolioView
                portfolios={portfolios}
                onCreatePortfolio={createPortfolio}
                onDeletePortfolio={deletePortfolio}
                onAddHolding={addHolding}
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

      <nav className="fixed bottom-4 left-1/2 z-50 w-[calc(100%-1.5rem)] max-w-md -translate-x-1/2 rounded-[1.8rem] border border-black/8 bg-[rgba(255,255,255,0.9)] p-2 shadow-[0_20px_60px_rgba(17,24,39,0.14)] backdrop-blur-xl md:hidden">
        <div className="grid grid-cols-3 gap-1">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`rounded-[1.1rem] px-3 py-3 text-center text-[11px] font-extrabold uppercase tracking-[0.16em] transition-all ${
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
          <BrokerChat currentTicker={analysis?.ticker} isOpen={isChatOpen} setIsOpen={setIsChatOpen} />
        </Suspense>
      </ErrorBoundary>
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
