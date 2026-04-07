import { lazy, Suspense, useEffect, useState } from "react";
import SearchBar from "./components/SearchBar";
import LoadingState from "./components/LoadingState";
import { usePortfolios } from "./hooks/usePortfolios";
import { CurrencyProvider, useCurrency } from "./context/CurrencyContext";

const AnalysisResult = lazy(() => import("./components/AnalysisResult"));
const PortfolioView = lazy(() => import("./components/PortfolioView"));
const DiscoveryPanel = lazy(() => import("./components/DiscoveryPanel"));
const BrokerChat = lazy(() => import("./components/BrokerChat"));
const MyRadar = lazy(() => import("./components/MyRadar"));

interface AnalysisData {
  ticker: string;
  company_name: string;
  [key: string]: any;
}

interface AuthState {
  loading: boolean;
  authenticated: boolean;
  configured: boolean;
  profile: { display_name?: string } | null;
}

type Tab = "analyze" | "discovery" | "portfolio";

const NAV_ITEMS: Array<{ id: Tab; label: string; short: string }> = [
  { id: "analyze", label: "Analyzer", short: "Analyze" },
  { id: "discovery", label: "Markets", short: "Markets" },
  { id: "portfolio", label: "Portfolio", short: "Portfolio" },
];

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
      <div className="mx-auto max-w-5xl">
        <div className="surface-panel overflow-hidden rounded-[2.8rem] p-6 sm:p-8 lg:p-10">
          <div className="grid gap-8 lg:grid-cols-[1.15fr_0.85fr]">
            <div className="space-y-6">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#101114] text-white">
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l5-5 4 4 7-8" />
                </svg>
              </div>
              <div>
                <div className="text-[11px] font-extrabold uppercase tracking-[0.28em] text-slate-500">
                  Private Workspace
                </div>
                <h1 className="mt-3 max-w-3xl text-5xl leading-none text-slate-900 sm:text-6xl">
                  Market Intelligence, locked to your local workspace.
                </h1>
                <p className="mt-5 max-w-2xl text-base leading-7 text-slate-600">
                  Die App ist jetzt auf Single-User-Betrieb gehärtet: lokales Passwort, geschützte API,
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
            </div>

            <div className="surface-strong rounded-[2.4rem] p-6 sm:p-8">
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
              {status ? <div className="mt-4 text-sm text-white/75">{status}</div> : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function AppContent() {
  const [activeTab, setActiveTab] = useState<Tab>(() => {
    return (localStorage.getItem("activeTab") as Tab) || "analyze";
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

  const {
    portfolios,
    createPortfolio,
    deletePortfolio,
    addHolding,
    removeHolding,
  } = usePortfolios(auth.authenticated);

  const { currency, setCurrency } = useCurrency();

  const refreshAuth = async () => {
    const response = await fetch("/api/auth/status");
    const payload = await response.json();
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
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Login failed.");
    }
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
    await fetch("/api/auth/logout", { method: "POST" });
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

  return (
    <div className="min-h-screen pb-24 text-[var(--text-primary)] md:pb-8">
      <header className="sticky top-0 z-50 border-b border-black/6 bg-[rgba(245,243,238,0.82)] backdrop-blur-xl">
        <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6">
          <div className="app-shell rounded-[2rem] px-4 py-3 sm:px-5">
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
                <div className="hidden rounded-[1.1rem] bg-white/70 p-1 ring-1 ring-black/6 sm:flex">
                  <button
                    onClick={() => setCurrency("USD")}
                    className={`rounded-[0.9rem] px-3 py-2 text-xs font-extrabold uppercase tracking-[0.18em] transition-all ${
                      currency === "USD" ? "bg-[#101114] text-white" : "text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    USD
                  </button>
                  <button
                    onClick={() => setCurrency("EUR")}
                    className={`rounded-[0.9rem] px-3 py-2 text-xs font-extrabold uppercase tracking-[0.18em] transition-all ${
                      currency === "EUR" ? "bg-[#101114] text-white" : "text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    EUR
                  </button>
                </div>
                <div className="hidden rounded-[1rem] border border-black/8 bg-white/70 px-3 py-2 text-xs font-extrabold uppercase tracking-[0.16em] text-slate-600 sm:block">
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
          </div>
        </div>
      </header>

      <main className={`mx-auto max-w-7xl px-4 py-6 transition-all duration-300 sm:px-6 ${isChatOpen ? "mr-[480px]" : ""}`}>
        {activeTab === "analyze" ? (
          <>
            {showHero && (
              <section className="mb-8 space-y-6">
                <Suspense fallback={<LoadingState />}>
                  <MyRadar onAnalyze={handleSearch} onOpenSignals={() => setActiveTab("discovery")} />
                </Suspense>
                <div>
                  <SearchBar onSearch={handleSearch} loading={loading} />
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
              <Suspense fallback={<LoadingState />}>
                <AnalysisResult
                  data={analysis}
                  portfolios={portfolios}
                  onAddHolding={addHolding}
                  onOpenChat={() => setIsChatOpen(true)}
                  onSelectTicker={handleSearch}
                />
              </Suspense>
            )}

            {!analysis && !loading && !error && (
              <section className="grid gap-4 md:grid-cols-3">
                {[
                  {
                    title: "Public Signals",
                    body: "Berkshire, Congress und weitere oeffentliche Filings mit sichtbarem Delay statt Black-Box-Hype.",
                  },
                  {
                    title: "Decision Clarity",
                    body: "Ruhigere Layouts, klarere Scores und bessere Priorisierung von Risiko, Bewertung und Momentum.",
                  },
                  {
                    title: "Private Access",
                    body: "Single-User-Hardening mit Login, lokaler Session und gesperrten API-Triggern fuer deinen Workspace.",
                  },
                ].map((card) => (
                  <div key={card.title} className="surface-panel rounded-[2rem] p-6">
                    <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                      {card.title}
                    </div>
                    <p className="mt-3 text-sm leading-7 text-slate-600">{card.body}</p>
                  </div>
                ))}
              </section>
            )}
          </>
        ) : activeTab === "discovery" ? (
          <Suspense fallback={<LoadingState />}>
            <DiscoveryPanel onAnalyze={handleSearch} />
          </Suspense>
        ) : (
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
        <div className="mx-auto max-w-7xl px-4 py-6 text-center text-sm text-slate-500 sm:px-6">
          Local single-user workspace. Data provided for informational purposes only.
        </div>
      </footer>

      <Suspense fallback={null}>
        <BrokerChat currentTicker={analysis?.ticker} isOpen={isChatOpen} setIsOpen={setIsChatOpen} />
      </Suspense>
    </div>
  );
}

export default function App() {
  return (
    <CurrencyProvider>
      <AppContent />
    </CurrencyProvider>
  );
}
