import React, { Fragment, useState, useEffect } from "react";
import PortfolioPerformance from "./PortfolioPerformance";
import PortfolioHeatmap from "./PortfolioHeatmap";
import DividendDashboard from "./DividendDashboard";
import RiskCorrelationMatrix from "./RiskCorrelationMatrix";
import AssetSuggestions from "./AssetSuggestions";
import AddHoldingModal from "./AddHoldingModal";
import PaperTradingPanel from "./PaperTradingPanel";
import ProviderStatePanel, { useSlowProviderState } from "./ProviderStatePanel";
import { Plus, Download, LayoutGrid, RefreshCw, Trash2, Check, X, ShieldAlert, ShieldCheck } from "lucide-react";
import { Portfolio, Holding, PortfolioDataSource } from "../hooks/usePortfolios";
import { useCurrency } from "../context/CurrencyContext";
import useAccessibleDialog from "../hooks/useAccessibleDialog";

interface PortfolioViewProps {
  portfolios: Portfolio[];
  dataSource: PortfolioDataSource;
  dataSourceMessage?: string;
  loading?: boolean;
  onCreatePortfolio: (name: string) => Promise<Portfolio>;
  onDeletePortfolio: (id: string) => void;
  onAddHolding: (portfolioId: string, holding: Holding) => Promise<void> | void;
  onUpdateHolding: (portfolioId: string, ticker: string, patch: Partial<Holding>) => void;
  onRemoveHolding: (portfolioId: string, ticker: string) => void;
  onAnalyzeStock: (ticker: string) => void;
  onRefresh: () => Promise<unknown> | unknown;
}

interface PortfolioAnalysis {
  holdings: any[];
  summary: {
    total_value: number;
    total_cost: number;
    gain_loss: number;
    gain_loss_pct: number;
    return_since_buy?: number;
    return_since_buy_pct?: number;
    num_holdings: number;
    avg_score: number;
    avg_holding_days?: number | null;
    sector_allocation: Record<string, number>;
  };
}

const PORTFOLIO_ANALYSIS_CACHE_TTL_MS = 5 * 60 * 1000;
const PORTFOLIO_ANALYSIS_CACHE_MAX = 8;
const portfolioAnalysisCache = new Map<string, { payload: PortfolioAnalysis; cachedAt: number }>();

function portfolioAnalysisKey(portfolio: Portfolio) {
  const holdings = [...portfolio.holdings]
    .map((holding) => ({
      ticker: holding.ticker.trim().toUpperCase(),
      shares: holding.shares,
      buyPrice: holding.buyPrice,
      purchaseDate: holding.purchaseDate || "",
    }))
    .sort((a, b) => a.ticker.localeCompare(b.ticker));
  return JSON.stringify({ id: portfolio.id, holdings });
}

function cachePortfolioAnalysis(key: string, payload: PortfolioAnalysis) {
  portfolioAnalysisCache.set(key, { payload, cachedAt: Date.now() });
  if (portfolioAnalysisCache.size > PORTFOLIO_ANALYSIS_CACHE_MAX) {
    const oldestKey = portfolioAnalysisCache.keys().next().value;
    if (oldestKey !== undefined) portfolioAnalysisCache.delete(oldestKey);
  }
}

interface PriceAlert {
  id: string;
  symbol: string;
  direction: "above" | "below";
  target_price: number;
  enabled: boolean;
  cooldown_minutes: number;
  last_triggered_at?: string | null;
}

interface ScalableIntegrationStatus {
  enabled: boolean;
  cli_installed: boolean;
  read_only: boolean;
  status: "never_synced" | "ok" | "error" | string;
  last_success_at?: string | null;
  last_attempt_at?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  position_count?: number;
  managed_portfolio_id?: string;
  auto_sync_enabled?: boolean;
  auto_sync_interval_minutes?: number;
  next_sync_due_at?: string | null;
  snapshot_stale?: boolean;
}

interface AdvisoryProfile {
  advisory_profile_complete?: boolean;
  risk_tolerance?: string;
  loss_capacity?: string;
  experience_level?: string;
  max_single_position_pct?: number;
  max_portfolio_drawdown_pct?: number;
  preferred_strategy?: string;
}

interface PortfolioAdvisoryCheck {
  status: "ok" | "review" | "blocked" | string;
  decision: string;
  advisory_headline?: string;
  advisory_score: number;
  issues: string[];
  required_next_steps: string[];
  review_actions?: Array<{
    priority?: number;
    level?: "blocker" | "review" | "opportunity" | string;
    title?: string;
    detail?: string;
    next_step?: string;
    flag?: string;
  }>;
  risk_flags: string[];
  top_holding?: {
    ticker?: string;
    position_pct?: number;
    position_value?: number;
  } | null;
  portfolio_metrics?: {
    max_single_position_pct?: number;
    max_portfolio_drawdown_pct?: number;
  };
  profile_limits?: {
    risk_tolerance?: string;
    loss_capacity?: string;
    preferred_strategy?: string;
  };
}

const toFiniteNumber = (value: unknown): number | null => {
  const number = typeof value === "number" ? value : Number(value);
  return Number.isFinite(number) ? number : null;
};

const formatPercent = (value: unknown, digits = 2, fallback = "N/A"): string => {
  const number = toFiniteNumber(value);
  if (number == null) return fallback;
  const sign = number >= 0 ? "+" : "";
  return `${sign}${number.toFixed(digits)}%`;
};

const formatNumber = (value: unknown, digits = 1, fallback = "N/A"): string => {
  const number = toFiniteNumber(value);
  return number == null ? fallback : number.toFixed(digits);
};

const formatPurchaseDate = (value?: string | null): string => {
  if (!value) return "Kein Kaufdatum";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Kein Kaufdatum";
  return date.toLocaleDateString();
};

const formatHoldingPeriod = (days?: number | null): string => {
  if (days == null || !Number.isFinite(days)) return "Kaufdatum fehlt";
  if (days <= 0) return "Heute";
  if (days < 30) return `${Math.round(days)}d`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}m`;
  const years = Math.floor(months / 12);
  const restMonths = months % 12;
  return restMonths > 0 ? `${years}y ${restMonths}m` : `${years}y`;
};

const recommendationLabel = (value?: string | null): string => {
  const normalized = String(value || "").trim().toUpperCase();
  if (normalized.includes("AVOID")) return "Meiden";
  if (normalized.includes("SELL")) return "Verkaufen";
  if (normalized.includes("BUY")) return "Kaufen";
  if (normalized.includes("ACCUMULATE")) return "Halten / Aufbauen";
  if (normalized.includes("HOLD")) return "Halten";
  if (normalized.includes("WATCH")) return "Beobachten";
  return value || "Beobachten";
};

const alertDirectionLabel = (value?: string | null): string =>
  String(value || "").toLowerCase() === "below" ? "Unterschreitet" : "Überschreitet";

const profileValueLabel = (value?: string | null): string => {
  const labels: Record<string, string> = {
    aggressive: "offensiv",
    conservative: "konservativ",
    high: "hoch",
    intermediate: "fortgeschritten",
    long_term: "langfristig",
    low: "niedrig",
    medium: "mittel",
    mixed: "gemischt",
    moderate: "moderat",
    short_term: "kurzfristig",
  };
  const normalized = String(value || "").trim().toLowerCase();
  return labels[normalized] || value || "offen";
};

const advisoryLevelLabel = (value?: string | null): string => {
  const labels: Record<string, string> = {
    blocker: "Sperre",
    opportunity: "Chance",
    review: "Prüfen",
  };
  const normalized = String(value || "").trim().toLowerCase();
  return labels[normalized] || value || "Prüfen";
};

export default function PortfolioView({
  portfolios,
  dataSource,
  dataSourceMessage,
  loading: portfoliosLoading = false,
  onCreatePortfolio,
  onDeletePortfolio,
  onAddHolding,
  onUpdateHolding,
  onRemoveHolding,
  onAnalyzeStock,
  onRefresh,
}: PortfolioViewProps) {
  const { formatPrice } = useCurrency();
  const [selectedPortfolio, setSelectedPortfolio] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showAddHoldingModal, setShowAddHoldingModal] = useState(false);
  const [editingHoldingTicker, setEditingHoldingTicker] = useState<string | null>(null);
  const [editHoldingShares, setEditHoldingShares] = useState("");
  const [editHoldingBuyPrice, setEditHoldingBuyPrice] = useState("");
  const [editHoldingPurchaseDate, setEditHoldingPurchaseDate] = useState("");
  const [savingHoldingEdit, setSavingHoldingEdit] = useState(false);
  const [holdingEditNotice, setHoldingEditNotice] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);
  const [newPortfolioName, setNewPortfolioName] = useState("");
  const [newHolding, setNewHolding] = useState({
    ticker: "",
    shares: "",
    buyPrice: "",
  });
  const [analysis, setAnalysis] = useState<PortfolioAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [portfolioVerdict, setPortfolioVerdict] = useState<string | null>(null);
  const [creatingPortfolio, setCreatingPortfolio] = useState(false);
  const [createPortfolioError, setCreatePortfolioError] = useState<string | null>(null);
  const [createPortfolioNotice, setCreatePortfolioNotice] = useState<string | null>(null);
  const [refreshingPortfolios, setRefreshingPortfolios] = useState(false);
  const [scalableStatus, setScalableStatus] = useState<ScalableIntegrationStatus | null>(null);
  const [scalableSyncing, setScalableSyncing] = useState(false);
  const [scalableNotice, setScalableNotice] = useState("");
  const [alerts, setAlerts] = useState<PriceAlert[]>([]);
  const [alertsLoading, setAlertsLoading] = useState(false);
  const [newAlertSymbol, setNewAlertSymbol] = useState("");
  const [newAlertDirection, setNewAlertDirection] = useState<"above" | "below">("above");
  const [newAlertTarget, setNewAlertTarget] = useState("");
  const [advisoryProfile, setAdvisoryProfile] = useState<AdvisoryProfile | null>(null);
  const [portfolioAdvisory, setPortfolioAdvisory] = useState<PortfolioAdvisoryCheck | null>(null);
  const [portfolioAdvisoryLoading, setPortfolioAdvisoryLoading] = useState(false);
  const [paperDashboard, setPaperDashboard] = useState<any>(null);
  const [paperDashboardLoading, setPaperDashboardLoading] = useState(false);
  const [paperDashboardError, setPaperDashboardError] = useState("");
  const paperDashboardSlow = useSlowProviderState(paperDashboardLoading, 5500);
  const createPortfolioDialogRef = useAccessibleDialog<HTMLDivElement>(
    showCreateModal,
    () => setShowCreateModal(false),
    "input",
  );

  const currentPortfolio = Array.isArray(portfolios)
    ? portfolios.find((p) => p.id === selectedPortfolio)
    : undefined;
  const isScalableManagedPortfolio =
    !!currentPortfolio && currentPortfolio.id === scalableStatus?.managed_portfolio_id;
  const isEditingHolding = (ticker?: string) => !!ticker && editingHoldingTicker === ticker;

  useEffect(() => {
    if (portfolios.length === 0) {
      if (selectedPortfolio) setSelectedPortfolio(null);
      return;
    }
    const selectedStillExists = portfolios.some((portfolio) => portfolio.id === selectedPortfolio);
    if (!selectedPortfolio || !selectedStillExists) {
      setSelectedPortfolio(portfolios[0].id);
    }
  }, [portfolios, selectedPortfolio]);

  useEffect(() => {
    if (selectedPortfolio && portfolios && Array.isArray(portfolios)) {
      const portfolio = portfolios.find((p) => p.id === selectedPortfolio);
      if (portfolio && portfolio.holdings && portfolio.holdings.length > 0) {
        analyzePortfolio(portfolio);
        if (portfolio.id !== "scalable-capital-read-only") {
          fetchPortfolioVerdict(selectedPortfolio);
        } else {
          setPortfolioVerdict(null);
        }
      } else {
        setAnalysis(null);
        setPortfolioVerdict(null);
      }
    } else {
      setAnalysis(null);
      setPortfolioVerdict(null);
    }
  }, [selectedPortfolio, portfolios]);

  const fetchScalableStatus = async () => {
    try {
      const response = await fetch("/api/integrations/scalable/status", { credentials: "same-origin" });
      if (!response.ok) return;
      setScalableStatus(await response.json());
    } catch {
      // This optional integration must never make the local portfolio unavailable.
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(fetchScalableStatus, 1200);
    return () => window.clearTimeout(timer);
  }, []);

  const syncScalablePortfolio = async () => {
    setScalableSyncing(true);
    setScalableNotice("Scalable-Positionen werden gelesen und mit der Brokerübersicht abgeglichen …");
    try {
      const response = await fetch("/api/integrations/scalable/sync", {
        method: "POST",
        credentials: "same-origin",
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        const detail = payload?.detail;
        throw new Error(detail?.message || detail || `Scalable-Sync fehlgeschlagen (${response.status})`);
      }
      await fetchScalableStatus();
      await onRefresh();
      const managedId = payload?.status?.managed_portfolio_id || scalableStatus?.managed_portfolio_id;
      if (managedId) setSelectedPortfolio(String(managedId));
      setScalableNotice("Scalable-Portfolio wurde read-only synchronisiert und geprüft.");
    } catch (error) {
      setScalableNotice(error instanceof Error ? error.message : "Scalable-Sync fehlgeschlagen.");
      await fetchScalableStatus();
    } finally {
      setScalableSyncing(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    const loadAlerts = async () => {
      setAlertsLoading(true);
      try {
        const response = await fetch("/api/alerts");
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = (await response.json()) as PriceAlert[];
        if (!cancelled) {
          setAlerts(Array.isArray(payload) ? payload : []);
        }
      } catch {
        if (!cancelled) setAlerts([]);
      } finally {
        if (!cancelled) setAlertsLoading(false);
      }
    };
    let interval: number | undefined;
    const timer = window.setTimeout(() => {
      void loadAlerts();
      interval = window.setInterval(loadAlerts, 30000);
    }, 700);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      if (interval !== undefined) window.clearInterval(interval);
    };
  }, []);

  const refreshPaperDashboard = async () => {
    setPaperDashboardLoading(true);
    setPaperDashboardError("");
    try {
      const response = await fetch("/api/trading/paper-dashboard");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      setPaperDashboard(payload || null);
    } catch {
      setPaperDashboard(null);
      setPaperDashboardError("Paper-Dashboard konnte vom Server nicht geladen werden.");
    } finally {
      setPaperDashboardLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    const loadPaperDashboard = async () => {
      setPaperDashboardLoading(true);
      setPaperDashboardError("");
      try {
        const response = await fetch("/api/trading/paper-dashboard");
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        if (!cancelled) setPaperDashboard(payload || null);
      } catch {
        if (!cancelled) {
          setPaperDashboard(null);
          setPaperDashboardError("Paper-Dashboard konnte vom Server nicht geladen werden.");
        }
      } finally {
        if (!cancelled) setPaperDashboardLoading(false);
      }
    };
    const timer = window.setTimeout(loadPaperDashboard, 1800);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const runPortfolioAdvisoryCheck = async () => {
      if (!analysis) {
        setPortfolioAdvisory(null);
        setPortfolioAdvisoryLoading(false);
        return;
      }
      setPortfolioAdvisoryLoading(true);
      try {
        const response = await fetch("/api/advisory/portfolio-check", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            holdings: analysis.holdings,
            summary: analysis.summary,
          }),
        });
        const payload = await response.json().catch(() => null);
        if (!response.ok || !payload) throw new Error("Portfolio advisory check failed");
        if (!cancelled) setPortfolioAdvisory(payload);
      } catch {
        if (!cancelled) setPortfolioAdvisory(null);
      } finally {
        if (!cancelled) setPortfolioAdvisoryLoading(false);
      }
    };
    runPortfolioAdvisoryCheck();
    return () => {
      cancelled = true;
    };
  }, [analysis]);

  useEffect(() => {
    let cancelled = false;
    const loadAdvisoryProfile = async () => {
      try {
        const response = await fetch("/api/advisory/profile");
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        if (!cancelled) setAdvisoryProfile(payload);
      } catch {
        if (!cancelled) setAdvisoryProfile(null);
      }
    };
    const timer = window.setTimeout(loadAdvisoryProfile, 2400);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  const createPriceAlert = async () => {
    const symbol = newAlertSymbol.trim().toUpperCase();
    const target = Number(newAlertTarget);
    if (!symbol || !Number.isFinite(target) || target <= 0) {
      return;
    }
    try {
      const response = await fetch("/api/alerts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol,
          direction: newAlertDirection,
          target_price: target,
          cooldown_minutes: 5,
          enabled: true,
        }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const created = (await response.json()) as PriceAlert;
      setAlerts((prev) => [created, ...prev]);
      setNewAlertSymbol("");
      setNewAlertTarget("");
    } catch {
      // keep UI stable without modal errors
    }
  };

  const toggleAlert = async (alert: PriceAlert) => {
    try {
      const response = await fetch(`/api/alerts/${alert.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !alert.enabled }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const updated = (await response.json()) as PriceAlert;
      setAlerts((prev) => prev.map((item) => (item.id === alert.id ? updated : item)));
    } catch {
      // ignore failed toggle
    }
  };

  const deleteAlert = async (alert: PriceAlert) => {
    try {
      const response = await fetch(`/api/alerts/${alert.id}`, { method: "DELETE" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setAlerts((prev) => prev.filter((item) => item.id !== alert.id));
    } catch {
      // ignore failed delete
    }
  };

  const fetchPortfolioVerdict = async (id: string) => {
    try {
      const res = await fetch(`/api/portfolio/${id}/verdict`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setPortfolioVerdict(data.verdict ?? null);
    } catch {
      setPortfolioVerdict(null);
    }
  };

  const analyzePortfolio = async (portfolio: Portfolio, forceRefresh = false) => {
    if (portfolio.holdings.length === 0) return;

    const cacheKey = portfolioAnalysisKey(portfolio);
    const cached = portfolioAnalysisCache.get(cacheKey);
    if (!forceRefresh && cached && Date.now() - cached.cachedAt < PORTFOLIO_ANALYSIS_CACHE_TTL_MS) {
      setAnalysis(cached.payload);
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const response = await fetch("/api/portfolio/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          portfolio_id: portfolio.id,
          holdings: portfolio.holdings.map((h) => ({
            ticker: h.ticker,
            shares: h.shares,
            buy_price: h.buyPrice,
            purchase_date: h.purchaseDate,
          })),
        }),
      });

      if (response.ok) {
        const data = (await response.json()) as PortfolioAnalysis;
        cachePortfolioAnalysis(cacheKey, data);
        setAnalysis(data);
      }
    } catch {
      setAnalysis(null);
    } finally {
      setLoading(false);
    }
  };

  const handleCreatePortfolio = async () => {
    const name = newPortfolioName.trim();
    if (name) {
      setCreatingPortfolio(true);
      setCreatePortfolioError(null);
      setCreatePortfolioNotice("Portfolio wird gespeichert und danach serverseitig geprüft...");
      try {
        const created = await onCreatePortfolio(name);
        setSelectedPortfolio(created.id);
        setCreatePortfolioNotice(`Gespeichert und geprüft: ${created.name}`);
        setNewPortfolioName("");
        window.setTimeout(() => {
          setShowCreateModal(false);
          setCreatePortfolioNotice(null);
        }, 700);
      } catch (error) {
        setCreatePortfolioNotice(null);
        setCreatePortfolioError(error instanceof Error ? error.message : "Portfolio konnte nicht gespeichert werden.");
      } finally {
        setCreatingPortfolio(false);
      }
    }
  };

  const openEditHolding = (holding: Holding) => {
    setHoldingEditNotice(null);
    setEditingHoldingTicker(holding.ticker);
    setEditHoldingShares(String(holding.shares ?? ""));
    setEditHoldingBuyPrice(
      holding.buyPrice != null && Number.isFinite(Number(holding.buyPrice))
        ? String(holding.buyPrice)
        : "",
    );
    setEditHoldingPurchaseDate(holding.purchaseDate?.slice(0, 10) || "");
  };

  const closeEditHolding = () => {
    setEditingHoldingTicker(null);
    setEditHoldingShares("");
    setEditHoldingBuyPrice("");
    setEditHoldingPurchaseDate("");
    setSavingHoldingEdit(false);
  };

  const saveHoldingEdit = async () => {
    if (!currentPortfolio || !editingHoldingTicker) return;
    const parsedShares = Number(editHoldingShares);
    const parsedBuyPrice = editHoldingBuyPrice.trim() === "" ? undefined : Number(editHoldingBuyPrice);
    if (!Number.isFinite(parsedShares) || parsedShares <= 0) return;
    if (parsedBuyPrice !== undefined && (!Number.isFinite(parsedBuyPrice) || parsedBuyPrice <= 0)) return;

    setSavingHoldingEdit(true);
    try {
      await onUpdateHolding(currentPortfolio.id, editingHoldingTicker, {
        shares: parsedShares,
        buyPrice: parsedBuyPrice,
        purchaseDate: editHoldingPurchaseDate || undefined,
      });
      setHoldingEditNotice({
        type: "success",
        message: `${editingHoldingTicker} wurde aktualisiert.`,
      });
      closeEditHolding();
    } catch (error) {
      setHoldingEditNotice({
        type: "error",
        message: error instanceof Error ? error.message : "Holding konnte nicht aktualisiert werden.",
      });
    } finally {
      setSavingHoldingEdit(false);
    }
  };

  const scoreTone = (score: number) =>
    score > 10 ? "text-emerald-700" : score < -10 ? "text-red-700" : "text-amber-700";

  const returnValue = analysis?.summary.return_since_buy ?? analysis?.summary.gain_loss ?? 0;
  const returnPct = analysis?.summary.return_since_buy_pct ?? analysis?.summary.gain_loss_pct ?? 0;
  const avgHoldingDays = analysis?.summary.avg_holding_days;
  const maxSinglePositionPct = Number(
    portfolioAdvisory?.portfolio_metrics?.max_single_position_pct ??
      advisoryProfile?.max_single_position_pct ??
      12.5,
  );
  const topHolding = analysis?.holdings
    ?.filter((holding) => !holding.error)
    .reduce<any | null>((top, holding) => {
      const value = Number(holding.position_value || 0);
      if (!top || value > Number(top.position_value || 0)) return holding;
      return top;
    }, null);
  const topHoldingPct =
    analysis?.summary.total_value && topHolding?.position_value
      ? (Number(topHolding.position_value) / Number(analysis.summary.total_value)) * 100
      : null;
  const localAdvisoryIssues = [
    advisoryProfile && !advisoryProfile.advisory_profile_complete
      ? "Beratungsprofil ist noch nicht bestätigt."
      : null,
    topHoldingPct != null && topHoldingPct > maxSinglePositionPct
      ? `${topHolding?.ticker} liegt bei ${formatNumber(topHoldingPct)}% und damit über dem Limit von ${formatNumber(maxSinglePositionPct)}%.`
      : null,
    analysis?.summary.num_holdings != null && analysis.summary.num_holdings > 0 && analysis.summary.num_holdings < 5
      ? "Weniger als 5 Positionen: Diversifikation ist noch dünn."
      : null,
    analysis?.summary.avg_score != null && analysis.summary.avg_score < 0
      ? "Durchschnittlicher Portfolio-Score ist negativ."
      : null,
  ].filter(Boolean) as string[];
  const advisoryIssues = portfolioAdvisory?.issues?.length ? portfolioAdvisory.issues : localAdvisoryIssues;
  const advisoryStatus =
    portfolioAdvisory?.status === "ok"
      ? "ok"
      : portfolioAdvisory?.status === "review" || portfolioAdvisory?.status === "blocked"
        ? "review"
        : portfolioAdvisoryLoading
          ? "loading"
          : !analysis
      ? "loading"
      : advisoryIssues.length
        ? "review"
        : "ok";
  const advisoryStatusCopy =
    advisoryStatus === "ok"
      ? "Portfolio passt zum aktuellen Beratungsrahmen."
      : advisoryStatus === "review"
        ? "Portfolio braucht Prüfung vor einer neuen Aktion."
        : "Portfolio wird geprüft.";
  const advisoryTone =
    advisoryStatus === "ok"
      ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-800"
      : "border-amber-500/25 bg-amber-500/10 text-amber-800";
  const advisoryTopHolding = portfolioAdvisory?.top_holding || topHolding;
  const advisoryTopHoldingPct =
    portfolioAdvisory?.top_holding?.position_pct != null
      ? Number(portfolioAdvisory.top_holding.position_pct)
      : topHoldingPct;
  const advisoryProfileLimits = portfolioAdvisory?.profile_limits;
  const advisoryHeadline =
    portfolioAdvisory?.advisory_headline ||
    (advisoryStatus === "ok"
      ? "Portfolio im Rahmen, neue Setups diszipliniert prüfen."
      : "Vor neuen Risiken diese Punkte prüfen.");
  const advisoryReviewActions =
    portfolioAdvisory?.review_actions?.length
      ? portfolioAdvisory.review_actions.slice(0, 3)
      : advisoryIssues.slice(0, 3).map((issue, index) => ({
          priority: 50 + index,
          level: "review",
        title: "Prüfpunkt",
          detail: issue,
          next_step: "These, Positionsgröße und Invalidierung dokumentieren.",
          flag: `local_${index}`,
        }));
  const advisoryActionTone = (level?: string) =>
    level === "blocker"
      ? "border-red-200 bg-red-50 text-red-800"
      : level === "opportunity"
        ? "border-emerald-200 bg-emerald-50 text-emerald-800"
        : "border-amber-200 bg-amber-50 text-amber-800";
  const sourceCopy = (() => {
    if (dataSource === "server") {
      return {
        label: "Server gespeichert",
        detail: "SQLite/Server ist aktiv. Neue Portfolios bleiben nach Reload erhalten.",
        tone: "border-emerald-400/30 bg-emerald-50 text-emerald-800",
        dot: "bg-emerald-500",
      };
    }
    if (dataSource === "local-cache") {
      return {
        label: "Lokale Sicherung",
        detail: dataSourceMessage || "Serverdaten sind gerade nicht erreichbar. Änderungen bleiben im Browser-Fallback.",
        tone: "border-amber-400/40 bg-amber-50 text-amber-800",
        dot: "bg-amber-500",
      };
    }
    if (dataSource === "disabled") {
      return {
        label: "Gesperrt",
        detail: "Login erforderlich, bevor Portfolios geladen oder gespeichert werden.",
        tone: "border-slate-300 bg-slate-50 text-slate-700",
        dot: "bg-slate-400",
      };
    }
    return {
      label: "Bereit",
      detail: "Noch kein Portfolio gespeichert. Das nächste neue Portfolio wird serverseitig angelegt.",
      tone: "border-slate-300 bg-white text-slate-700",
      dot: "bg-slate-400",
    };
  })();
  const refreshPortfolioList = async () => {
    setRefreshingPortfolios(true);
    try {
      await onRefresh();
    } finally {
      setRefreshingPortfolios(false);
    }
  };

  return (
    <div className="space-y-6">
      <section className="surface-panel rounded-[2.4rem] p-6 sm:p-8">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="text-[11px] font-extrabold uppercase tracking-[0.24em] text-slate-500">
              Portfolio-Zentrale
            </div>
            <h1 className="mt-2 text-4xl text-slate-900 sm:text-5xl">
              Klare Entscheidungen statt Datenchaos.
            </h1>
            <p className="mt-4 max-w-3xl text-base leading-7 text-slate-600">
              Klare Übersicht über Positionen, Risiko, Dividenden und Korrelationen in derselben
              visuellen Sprache wie dein Radar und Morning Briefing.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className={`flex max-w-md items-center gap-3 rounded-[1.2rem] border px-4 py-3 text-xs font-bold ${sourceCopy.tone}`}>
              <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${sourceCopy.dot}`} />
              <div>
                <div className="font-extrabold uppercase tracking-[0.14em]">{sourceCopy.label}</div>
                <div className="mt-1 normal-case leading-5 opacity-80">{sourceCopy.detail}</div>
              </div>
            </div>
            <button
              onClick={refreshPortfolioList}
              disabled={portfoliosLoading || refreshingPortfolios}
              className="inline-flex items-center gap-2 rounded-[1.2rem] border border-black/8 bg-white px-4 py-3 text-xs font-extrabold uppercase tracking-[0.16em] text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RefreshCw className={`h-4 w-4 ${portfoliosLoading || refreshingPortfolios ? "animate-spin" : ""}`} />
              Aktualisieren
            </button>
            <button
              onClick={() => {
                setCreatePortfolioError(null);
                setCreatePortfolioNotice(null);
                setShowCreateModal(true);
              }}
              className="rounded-[1.2rem] border border-black/8 bg-white px-5 py-3 text-xs font-extrabold uppercase tracking-[0.18em] text-slate-700"
            >
              Neues Portfolio
            </button>
            {currentPortfolio && !isScalableManagedPortfolio && (
              <button
                onClick={() => setShowAddHoldingModal(true)}
                className="rounded-[1.2rem] bg-[var(--accent)] px-5 py-3 text-xs font-extrabold uppercase tracking-[0.18em] text-white transition-colors hover:bg-[var(--accent-strong)]"
              >
                Position hinzufügen
              </button>
            )}
          </div>
        </div>

        {scalableStatus && (
          <div className="mt-6 flex flex-col gap-4 rounded-[1.5rem] border border-sky-200 bg-sky-50/80 p-5 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-sky-800">
                <ShieldCheck className="h-4 w-4" />
                Scalable Capital · Read-only
              </div>
              <div className="mt-2 text-sm font-bold text-slate-800">
                {!scalableStatus.enabled
                  ? "Integration ist vorbereitet, aber serverseitig noch nicht aktiviert."
                  : !scalableStatus.cli_installed
                    ? "Offizielle Scalable CLI wurde auf dem Server noch nicht gefunden."
                    : scalableStatus.status === "ok"
                      ? scalableStatus.snapshot_stale
                        ? `${scalableStatus.position_count || 0} Positionen vorhanden · Snapshot ist überfällig.`
                        : `${scalableStatus.position_count || 0} Positionen geprüft synchronisiert.`
                      : scalableStatus.error_message || "Bereit für den ersten sicheren Abgleich."}
              </div>
              <div className="mt-1 text-xs leading-5 text-slate-600">
                {scalableStatus.last_success_at
                  ? `Letzter gültiger Stand: ${new Date(scalableStatus.last_success_at).toLocaleString()}${
                      scalableStatus.auto_sync_enabled
                        ? ` · automatisch alle ${scalableStatus.auto_sync_interval_minutes || 15} Minuten`
                        : ""
                    }`
                  : "Keine Orders, Sparpläne oder Änderungen – ausschließlich Portfolio-Lesedaten."}
              </div>
              {scalableNotice && <div className="mt-2 text-xs font-bold text-sky-900">{scalableNotice}</div>}
            </div>
            <button
              onClick={syncScalablePortfolio}
              disabled={!scalableStatus.enabled || !scalableStatus.cli_installed || scalableSyncing}
              className="inline-flex shrink-0 items-center justify-center gap-2 rounded-[1.2rem] bg-sky-700 px-5 py-3 text-xs font-extrabold uppercase tracking-[0.16em] text-white transition-colors hover:bg-sky-800 disabled:cursor-not-allowed disabled:opacity-45"
            >
              <RefreshCw className={`h-4 w-4 ${scalableSyncing ? "animate-spin" : ""}`} />
              {scalableSyncing ? "Prüfe …" : "Scalable synchronisieren"}
            </button>
          </div>
        )}

        <div className="mt-6 grid gap-4 sm:grid-cols-3">
          <div className="rounded-[1.5rem] border border-black/8 bg-white/75 p-5">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
              Portfolios
            </div>
            <div className="mt-2 text-3xl font-black text-slate-900">{portfolios.length}</div>
          </div>
          <div className="rounded-[1.5rem] border border-black/8 bg-white/75 p-5">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
              Ausgewählt
            </div>
            <div className="mt-2 text-xl font-black text-slate-900">
              {currentPortfolio?.name || "Kein Portfolio"}
            </div>
          </div>
          <div className="rounded-[1.5rem] border border-black/8 bg-white/75 p-5">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
              Aktive Positionen
            </div>
            <div className="mt-2 text-3xl font-black text-slate-900">
              {currentPortfolio?.holdings.length || 0}
            </div>
          </div>
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          {portfolios.map((portfolio) => (
            <button
              key={portfolio.id}
              onClick={() => setSelectedPortfolio(portfolio.id)}
              className={`rounded-full px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.16em] transition-all ${
                selectedPortfolio === portfolio.id
                  ? "bg-[var(--accent)] text-white shadow-[0_14px_30px_rgba(15,118,110,0.16)]"
                  : "border border-black/8 bg-white text-slate-600"
              }`}
            >
              {portfolio.name} ({portfolio.holdings.length})
            </button>
          ))}
        </div>
      </section>

      {currentPortfolio ? (
        <div className="space-y-6">
          <section className="surface-panel rounded-[2.2rem] p-6 sm:p-8">
            <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
              <div>
                <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                  Aktives Portfolio
                </div>
                <h2 className="mt-2 text-4xl text-slate-900">{currentPortfolio.name}</h2>
                <p className="mt-2 text-sm text-slate-500">
                  {currentPortfolio.holdings.length} Positionen im aktuellen Portfolio.
                </p>
              </div>

              <div className="flex flex-wrap gap-3">
                <button
                  onClick={() => currentPortfolio && analyzePortfolio(currentPortfolio, true)}
                  disabled={loading || currentPortfolio.holdings.length === 0}
                  className="rounded-[1.1rem] border border-black/8 bg-white px-4 py-2.5 text-xs font-extrabold uppercase tracking-[0.16em] text-slate-700 disabled:opacity-50"
                >
                  <span className="inline-flex items-center gap-2">
                    <RefreshCw size={14} />
                    {loading ? "Wird aktualisiert" : "Aktualisieren"}
                  </span>
                </button>
                <button
                  onClick={() => window.open(`/api/portfolio/${selectedPortfolio}/export/csv`)}
                  className="rounded-[1.1rem] border border-black/8 bg-white px-4 py-2.5 text-xs font-extrabold uppercase tracking-[0.16em] text-slate-700"
                >
                  <span className="inline-flex items-center gap-2">
                    <Download size={14} />
                    CSV exportieren
                  </span>
                </button>
                {!isScalableManagedPortfolio && <button
                  onClick={() => {
                    if (confirm("Dieses Portfolio wirklich löschen?")) {
                      onDeletePortfolio(currentPortfolio.id);
                      setSelectedPortfolio(null);
                    }
                  }}
                  className="rounded-[1.1rem] border border-red-200 bg-red-50 px-4 py-2.5 text-xs font-extrabold uppercase tracking-[0.16em] text-red-700"
                >
                  <span className="inline-flex items-center gap-2">
                    <Trash2 size={14} />
                    Löschen
                  </span>
                </button>}
              </div>
            </div>

            {analysis && (
              <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
                <div className="rounded-[1.5rem] border border-black/8 bg-white/75 p-5">
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                    Gesamtwert
                  </div>
                  <div className="mt-2 text-3xl font-black text-slate-900">
                    {formatPrice(analysis.summary.total_value)}
                  </div>
                </div>
                <div className="rounded-[1.5rem] border border-black/8 bg-white/75 p-5">
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                    Investiert
                  </div>
                  <div className="mt-2 text-3xl font-black text-slate-900">
                    {formatPrice(analysis.summary.total_cost)}
                  </div>
                </div>
                <div className="rounded-[1.5rem] border border-black/8 bg-white/75 p-5">
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                    Rendite seit Kauf
                  </div>
                  <div className={`mt-2 text-3xl font-black ${returnValue >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                    {formatPrice(returnValue)}
                  </div>
                  <div className={`mt-1 text-sm font-bold ${returnPct >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                    {formatPercent(returnPct)}
                  </div>
                </div>
                <div className="rounded-[1.5rem] border border-black/8 bg-white/75 p-5">
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                    Portfolio-Score
                  </div>
                  <div className={`mt-2 text-3xl font-black ${scoreTone(analysis.summary.avg_score)}`}>
                    {formatNumber(analysis.summary.avg_score)}
                  </div>
                </div>
                <div className="rounded-[1.5rem] border border-black/8 bg-white/75 p-5">
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                    Positionen
                  </div>
                  <div className="mt-2 text-3xl font-black text-slate-900">
                    {analysis.summary.num_holdings}
                  </div>
                  {avgHoldingDays != null && (
                    <div className="hidden">
                      Ø Haltedauer {formatHoldingPeriod(avgHoldingDays)}
                    </div>
                  )}
                  {avgHoldingDays != null && (
                    <div className="mt-1 text-xs font-bold uppercase tracking-[0.14em] text-slate-500">
                      Ø Haltedauer {formatHoldingPeriod(avgHoldingDays)}
                    </div>
                  )}
                </div>
              </div>
            )}

            {analysis && (
              <section className="mt-6 rounded-[1.7rem] border border-black/8 bg-white/75 p-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                      Portfolio-Beratungscheck
                    </div>
                    <h3 className="mt-2 text-2xl text-slate-900">
                      {advisoryHeadline}
                    </h3>
                    <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                      Prüft Konzentration, Positionslimit, Diversifikation und Score gegen dein Beratungsprofil.
                    </p>
                  </div>
                  <div className={`inline-flex items-center gap-2 rounded-full border px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.16em] ${advisoryTone}`}>
                    {advisoryStatus === "ok" ? <ShieldCheck size={16} /> : <ShieldAlert size={16} />}
                    {portfolioAdvisoryLoading ? "Prüft" : advisoryStatus === "ok" ? "Passt" : "Prüfen"}
                  </div>
                </div>

                <div className="mt-5 grid gap-3 lg:grid-cols-4">
                  <div className="rounded-2xl border border-black/8 bg-white/80 p-4">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                      Status
                    </div>
                    <div className="mt-2 text-sm font-black leading-6 text-slate-900">{advisoryStatusCopy}</div>
                  </div>
                  <div className="rounded-2xl border border-black/8 bg-white/80 p-4">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                      Top Position
                    </div>
                    <div className="mt-2 text-2xl font-black text-slate-900">
                      {advisoryTopHolding?.ticker || "n/a"}
                    </div>
                    <div className="mt-1 text-xs font-semibold text-slate-500">
                      {advisoryTopHoldingPct != null ? `${formatNumber(advisoryTopHoldingPct)}% vom Portfolio` : "Keine Bewertung"}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-black/8 bg-white/80 p-4">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                      Positionslimit
                    </div>
                    <div className="mt-2 text-2xl font-black text-slate-900">
                      {formatNumber(maxSinglePositionPct)}%
                    </div>
                    <div className="mt-1 text-xs font-semibold text-slate-500">
                      aus deinem Beratungsprofil
                    </div>
                  </div>
                  <div className="rounded-2xl border border-black/8 bg-white/80 p-4">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                      Profil
                    </div>
                    <div className="mt-2 text-sm font-black leading-6 text-slate-900">
                      {profileValueLabel(advisoryProfileLimits?.preferred_strategy || advisoryProfile?.preferred_strategy || "mixed")} / {profileValueLabel(advisoryProfileLimits?.risk_tolerance || advisoryProfile?.risk_tolerance || "medium")}
                    </div>
                    <div className="mt-1 text-xs font-semibold text-slate-500">
                      Verlusttragfähigkeit {profileValueLabel(advisoryProfileLimits?.loss_capacity || advisoryProfile?.loss_capacity || "medium")}
                    </div>
                  </div>
                </div>

                <div className="mt-4 rounded-2xl border border-black/8 bg-white/70 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                      Priorisierte Prüfliste
                    </div>
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-400">
                      Score {portfolioAdvisoryLoading ? "--" : portfolioAdvisory?.advisory_score ?? "--"}/100
                    </div>
                  </div>
                  <div className="mt-3 grid gap-3 lg:grid-cols-3">
                    {advisoryReviewActions.map((item, index) => (
                      <div
                        key={`${item.flag || item.title || "review"}-${index}`}
                        className={`rounded-2xl border p-4 ${advisoryActionTone(item.level)}`}
                      >
                        <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] opacity-75">
                          {advisoryLevelLabel(item.level)} #{index + 1}
                        </div>
                        <div className="mt-2 text-sm font-black leading-5">
                          {item.title || "Prüfpunkt"}
                        </div>
                        <div className="mt-2 text-xs font-semibold leading-5 opacity-90">
                          {item.detail || "Keine harte Bremse erkannt."}
                        </div>
                        <div className="mt-3 rounded-xl bg-white/70 px-3 py-2 text-xs font-bold leading-5 text-slate-700">
                          {item.next_step || "Trigger, Zielgewicht und Invalidierung dokumentieren."}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </section>
            )}

            {holdingEditNotice && (
              <div
                className={`mt-6 rounded-[1.2rem] border px-4 py-3 text-sm font-semibold ${
                  holdingEditNotice.type === "success"
                    ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                    : "border-red-200 bg-red-50 text-red-700"
                }`}
              >
                {holdingEditNotice.message}
              </div>
            )}

            <section className="surface-panel rounded-[2rem] p-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                    Preisalarme
                  </div>
                  <p className="mt-1 text-sm text-slate-600">
                    Auslösung bei Kursberührung mit fünf Minuten Sperrzeit. Alarme werden in dieser Beta nur per Telegram versendet.
                  </p>
                </div>
                <div className="rounded-full border border-black/8 bg-white px-3 py-1 text-xs font-bold text-slate-500">
                  {alerts.filter((item) => item.enabled).length} aktiv
                </div>
              </div>

              <div className="mt-4 grid gap-3 md:grid-cols-[1fr_180px_140px_120px]">
                <input
                  value={newAlertSymbol}
                  onChange={(e) => setNewAlertSymbol(e.target.value.toUpperCase())}
                  placeholder="Ticker (z.B. AAPL)"
                  className="rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800"
                />
                <select
                  value={newAlertDirection}
                  onChange={(e) => setNewAlertDirection(e.target.value as "above" | "below")}
                  className="rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800"
                >
                  <option value="above">Überschreitet</option>
                  <option value="below">Unterschreitet</option>
                </select>
                <input
                  value={newAlertTarget}
                  onChange={(e) => setNewAlertTarget(e.target.value)}
                  type="number"
                  step="0.01"
                  placeholder="Zielkurs"
                  className="rounded-xl border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800"
                />
                <button
                  onClick={createPriceAlert}
                  className="rounded-xl bg-[var(--accent)] px-4 py-3 text-xs font-extrabold uppercase tracking-[0.16em] text-white"
                >
                  Alarm hinzufügen
                </button>
              </div>

              <div className="mt-5 overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="border-b border-black/6 bg-black/[0.02] text-left text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                      <th className="px-4 py-3">Ticker</th>
                      <th className="px-4 py-3">Regel</th>
                      <th className="px-4 py-3 text-right">Zielkurs</th>
                      <th className="px-4 py-3">Letzte Auslösung</th>
                      <th className="px-4 py-3 text-right">Status</th>
                      <th className="px-4 py-3 text-right">Verwalten</th>
                    </tr>
                  </thead>
                  <tbody>
                    {alertsLoading ? (
                      <tr>
                        <td className="px-4 py-4 text-sm text-slate-500" colSpan={6}>
                          Alerts werden geladen...
                        </td>
                      </tr>
                    ) : alerts.length === 0 ? (
                      <tr>
                        <td className="px-4 py-4 text-sm text-slate-500" colSpan={6}>
                          Noch keine Alerts vorhanden.
                        </td>
                      </tr>
                    ) : (
                      alerts.map((alert) => (
                        <tr key={alert.id} className="border-b border-black/6 last:border-b-0">
                          <td className="px-4 py-4 text-sm font-extrabold text-slate-900">{alert.symbol}</td>
                          <td className="px-4 py-4 text-sm font-semibold text-slate-700">{alertDirectionLabel(alert.direction)}</td>
                          <td className="px-4 py-4 text-right text-sm font-semibold text-slate-700">
                            {formatPrice(alert.target_price)}
                          </td>
                          <td className="px-4 py-4 text-xs text-slate-500">
                            {alert.last_triggered_at
                              ? new Date(alert.last_triggered_at).toLocaleString()
                              : "Noch nie"}
                          </td>
                          <td className="px-4 py-4 text-right">
                            <span
                              className={`rounded-full px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] ${
                                alert.enabled
                                  ? "bg-emerald-500/10 text-emerald-700"
                                  : "bg-slate-200 text-slate-500"
                              }`}
                            >
                              {alert.enabled ? "Aktiv" : "Pausiert"}
                            </span>
                          </td>
                          <td className="px-4 py-4">
                            <div className="flex justify-end gap-2">
                              <button
                                onClick={() => toggleAlert(alert)}
                                className="rounded-lg border border-black/8 bg-white px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-slate-700"
                              >
                                {alert.enabled ? "Pausieren" : "Aktivieren"}
                              </button>
                              <button
                                onClick={() => deleteAlert(alert)}
                                className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-red-700"
                              >
                                Entfernen
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            {portfolioVerdict && (
              <div className="mt-6 flex items-start gap-4 rounded-[1.8rem] border border-[var(--accent)]/12 bg-[linear-gradient(135deg,rgba(240,253,250,0.92),rgba(255,255,255,0.9))] p-6 text-slate-900 shadow-[0_18px_45px_rgba(15,23,42,0.08)]">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-[var(--accent)]">
                  <LayoutGrid size={22} />
                </div>
                <div>
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                    Portfolio-Einordnung
                  </div>
                  <p className="mt-3 text-base leading-7 text-slate-700">{portfolioVerdict}</p>
                </div>
              </div>
            )}
          </section>

          {analysis && analysis.holdings.length > 0 ? (
            <>
              <div className="grid gap-6 lg:grid-cols-2">
                {isScalableManagedPortfolio ? (
                  <section className="surface-panel rounded-[2rem] border border-sky-200 bg-sky-50/70 p-6">
                    <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-sky-800">
                      Verifizierter Broker-Snapshot
                    </div>
                    <p className="mt-3 text-sm leading-6 text-slate-700">
                      Aktueller Wert und FIFO-Einstand stammen direkt aus dem abgeglichenen Scalable-Snapshot.
                      Eine historische Kurve wird erst angezeigt, wenn Scalable dafür vollständig vergleichbare
                      Zeitreihen liefert.
                    </p>
                  </section>
                ) : (
                  <PortfolioPerformance portfolioId={selectedPortfolio!} />
                )}
                <PortfolioHeatmap holdings={analysis.holdings} />
              </div>

              <div className="grid gap-6 lg:grid-cols-2">
                {!isScalableManagedPortfolio && <DividendDashboard portfolioId={selectedPortfolio!} />}
                <RiskCorrelationMatrix portfolioId={selectedPortfolio!} />
              </div>

              {selectedPortfolio && !isScalableManagedPortfolio && (
                <AssetSuggestions
                  portfolioId={selectedPortfolio}
                  onAdd={(ticker: string) => {
                    setNewHolding({ ticker, shares: "1", buyPrice: "" });
                    setShowAddHoldingModal(true);
                  }}
                />
              )}

              {Object.keys(analysis.summary.sector_allocation).length > 0 && (
                <section className="surface-panel rounded-[2rem] p-6">
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                    Sector Allocation
                  </div>
                  <div className="mt-5 space-y-3">
                    {Object.entries(analysis.summary.sector_allocation)
                      .sort((a, b) => b[1] - a[1])
                      .map(([sector, pct]) => (
                        <div key={sector} className="grid items-center gap-3 md:grid-cols-[180px_1fr_70px]">
                          <div className="text-sm font-bold text-slate-800">{sector}</div>
                          <div className="h-2 overflow-hidden rounded-full bg-black/[0.06]">
                            <div
                              className="h-full rounded-full bg-[linear-gradient(90deg,var(--accent),#244f4a)]"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          <div className="text-right text-sm font-bold text-slate-500">
                            {formatNumber(pct)}%
                          </div>
                        </div>
                      ))}
                  </div>
                </section>
              )}

              <section className="surface-panel overflow-hidden rounded-[2rem] p-0">
                <div className="border-b border-black/6 px-6 py-5">
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                    Positionen
                  </div>
                </div>
                <div className="space-y-3 p-4 md:hidden">
                  {analysis.holdings.map((holding) => {
                    const holdingReturn = holding.return_since_buy ?? holding.gain_loss ?? 0;
                    const holdingReturnPct = holding.return_since_buy_pct ?? holding.gain_loss_pct ?? 0;
                    const hasEntry = holding.buy_price != null && Number.isFinite(Number(holding.buy_price));
                    const isEditing = isEditingHolding(holding.ticker);
                    return (
                      <div
                        key={`mobile-${holding.ticker}`}
                        className="rounded-[1.3rem] border border-black/8 bg-white/80 p-4"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="font-extrabold text-slate-900">{holding.ticker}</div>
                            <div className="truncate text-sm text-slate-500">{holding.name}</div>
                          </div>
                          <span className={`rounded-full px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] ${
                            holding.recommendation?.includes("BUY")
                              ? "bg-emerald-500/10 text-emerald-700"
                              : holding.recommendation?.includes("SELL") || holding.recommendation?.includes("AVOID")
                                ? "bg-red-500/10 text-red-700"
                                : "bg-amber-500/10 text-amber-700"
                          }`}>
                            {recommendationLabel(holding.recommendation)}
                          </span>
                        </div>

                        <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                          <div className="rounded-xl border border-black/6 bg-black/[0.02] px-3 py-2">
                            <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">Anteile</div>
                            <div className="mt-1 font-bold text-slate-900">{holding.shares}</div>
                          </div>
                          <div className="rounded-xl border border-black/6 bg-black/[0.02] px-3 py-2">
                            <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">Wert</div>
                            <div className="mt-1 font-bold text-slate-900">{formatPrice(holding.position_value || 0)}</div>
                          </div>
                          <div className="rounded-xl border border-black/6 bg-black/[0.02] px-3 py-2">
                            <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">Kaufkurs</div>
                            <div className="mt-1 font-bold text-slate-900">
                              {hasEntry ? formatPrice(holding.buy_price) : "Kurs fehlt"}
                            </div>
                          </div>
                          <div className="rounded-xl border border-black/6 bg-black/[0.02] px-3 py-2">
                            <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">Aktuell</div>
                            <div className="mt-1 font-bold text-slate-900">{formatPrice(holding.current_price || 0)}</div>
                          </div>
                        </div>

                        <div className="mt-4 flex flex-wrap items-center gap-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                          <span className="rounded-full border border-black/8 bg-white px-3 py-1">
                            Kaufdatum {formatPurchaseDate(holding.purchase_date)}
                          </span>
                          <span className="rounded-full border border-black/8 bg-white px-3 py-1">
                            Seit Kauf {formatHoldingPeriod(holding.holding_days)}
                          </span>
                          <span className={`rounded-full px-3 py-1 ${scoreTone(holding.score || 0)} bg-black/[0.04]`}>
                            Score {formatNumber(holding.score, 0, "0")}
                          </span>
                        </div>
                        {!hasEntry && (
                          <button
                            type="button"
                            onClick={() => openEditHolding({
                              ticker: holding.ticker,
                              shares: holding.shares,
                              buyPrice: holding.buy_price,
                              purchaseDate: holding.purchase_date,
                            })}
                            className="mt-3 w-full rounded-xl border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-left text-xs font-semibold text-amber-800"
                          >
                            Kaufkurs fehlt: Einstand eintragen, damit Rendite seit Kauf korrekt berechnet wird.
                          </button>
                        )}

                        <div className="mt-4 flex items-end justify-between gap-3">
                          <div>
                            <div className={`text-base font-extrabold ${holdingReturn >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                              {formatPrice(holdingReturn)}
                            </div>
                            <div className={`text-xs font-bold ${holdingReturnPct >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                              {formatPercent(holdingReturnPct)}
                            </div>
                          </div>
                          <div className="flex gap-2">
                            <button
                              onClick={() => onAnalyzeStock(holding.ticker)}
                              className="rounded-xl border border-black/8 bg-white px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-slate-700"
                            >
                              Analysieren
                            </button>
                            <button
                              onClick={() => openEditHolding({
                                ticker: holding.ticker,
                                shares: holding.shares,
                                buyPrice: holding.buy_price,
                                purchaseDate: holding.purchase_date,
                              })}
                              className={`rounded-xl border px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.14em] ${
                                isEditing
                                  ? "border-[var(--accent)]/30 bg-[var(--accent-soft)] text-[var(--accent)]"
                                  : "border-black/8 bg-white text-slate-700"
                              }`}
                            >
                              {isEditing ? "Bearbeitung" : "Bearbeiten"}
                            </button>
                            <button
                              onClick={() => onRemoveHolding(currentPortfolio.id, holding.ticker)}
                              className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-red-700"
                            >
                              Entfernen
                            </button>
                          </div>
                        </div>

                        {isEditing && (
                          <div className="mt-4 rounded-[1.2rem] border border-[var(--accent)]/20 bg-[var(--accent-soft)]/40 p-4">
                            <div className="grid gap-3">
                              <label className="block">
                                <div className="mb-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                                  Anteile
                                </div>
                                <input
                                  type="number"
                                  min="0"
                                  step="0.0001"
                                  value={editHoldingShares}
                                  onChange={(e) => setEditHoldingShares(e.target.value)}
                                  className="w-full rounded-xl border border-black/8 bg-white px-3 py-2.5 text-sm font-semibold text-slate-800"
                                />
                              </label>
                              <label className="block">
                                <div className="mb-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                                  Kaufkurs (USD)
                                </div>
                                <input
                                  type="number"
                                  min="0"
                                  step="0.0001"
                                  value={editHoldingBuyPrice}
                                  onChange={(e) => setEditHoldingBuyPrice(e.target.value)}
                                  placeholder="Optional"
                                  className="w-full rounded-xl border border-black/8 bg-white px-3 py-2.5 text-sm font-semibold text-slate-800"
                                />
                              </label>
                              <label className="block">
                                <div className="mb-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                                  Kaufdatum
                                </div>
                                <input
                                  type="date"
                                  value={editHoldingPurchaseDate}
                                  onChange={(e) => setEditHoldingPurchaseDate(e.target.value)}
                                  className="w-full rounded-xl border border-black/8 bg-white px-3 py-2.5 text-sm font-semibold text-slate-800"
                                />
                              </label>
                            </div>
                            <div className="mt-4 flex justify-end gap-2">
                              <button
                                onClick={closeEditHolding}
                                className="rounded-xl border border-black/8 bg-white px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-slate-700"
                              >
                                <span className="inline-flex items-center gap-1">
                                  <X size={12} />
                                  Abbrechen
                                </span>
                              </button>
                              <button
                                onClick={saveHoldingEdit}
                                disabled={savingHoldingEdit || !editHoldingShares.trim()}
                                className="rounded-xl bg-[var(--accent)] px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-white disabled:opacity-50"
                              >
                                <span className="inline-flex items-center gap-1">
                                  <Check size={12} />
                                  {savingHoldingEdit ? "Speichert" : "Speichern"}
                                </span>
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
                <div className="hidden overflow-x-auto md:block">
                  <table className="min-w-full">
                    <thead>
                      <tr className="border-b border-black/6 bg-black/[0.02] text-left text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                        <th className="px-6 py-4">Aktie</th>
                        <th className="px-4 py-4 text-right">Anteile</th>
                        <th className="px-4 py-4 text-right">Kaufdatum</th>
                        <th className="px-4 py-4 text-right">Haltedauer</th>
                        <th className="px-4 py-4 text-right">Kaufkurs</th>
                        <th className="px-4 py-4 text-right">Kurs</th>
                        <th className="px-4 py-4 text-right">Wert</th>
                        <th className="px-4 py-4 text-right">Seit Kauf</th>
                        <th className="px-4 py-4 text-right">Score</th>
                        <th className="px-4 py-4 text-center">Signal</th>
                        <th className="px-6 py-4 text-right">Verwalten</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analysis.holdings.map((holding) => {
                        const holdingReturn = holding.return_since_buy ?? holding.gain_loss ?? 0;
                        const holdingReturnPct = holding.return_since_buy_pct ?? holding.gain_loss_pct ?? 0;
                        const hasEntry = holding.buy_price != null && Number.isFinite(Number(holding.buy_price));
                        const isEditing = isEditingHolding(holding.ticker);
                        return (
                        <Fragment key={`desktop-${holding.ticker}`}>
                          <tr key={holding.ticker} className="border-b border-black/6 last:border-b-0 hover:bg-black/[0.02]">
                            <td className="px-6 py-4">
                              <div className="font-extrabold text-slate-900">{holding.ticker}</div>
                              <div className="max-w-[220px] truncate text-sm text-slate-500">{holding.name}</div>
                            </td>
                            <td className="px-4 py-4 text-right text-sm font-semibold text-slate-700">
                              {holding.shares}
                            </td>
                            <td className="px-4 py-4 text-right text-sm font-semibold text-slate-700">
                              {formatPurchaseDate(holding.purchase_date)}
                            </td>
                            <td className="px-4 py-4 text-right text-sm font-semibold text-slate-700">
                              {formatHoldingPeriod(holding.holding_days)}
                            </td>
                            <td className="px-4 py-4 text-right text-sm font-semibold text-slate-700">
                              {hasEntry ? formatPrice(holding.buy_price) : "Kaufkurs fehlt"}
                            </td>
                            <td className="px-4 py-4 text-right text-sm font-semibold text-slate-700">
                              {formatPrice(holding.current_price || 0)}
                            </td>
                            <td className="px-4 py-4 text-right text-sm font-extrabold text-slate-900">
                              {formatPrice(holding.position_value || 0)}
                            </td>
                            <td className="px-4 py-4 text-right">
                              <div className={`text-sm font-extrabold ${holdingReturn >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                                {formatPrice(holdingReturn)}
                              </div>
                              <div className={`text-xs font-bold ${holdingReturnPct >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                                {formatPercent(holdingReturnPct)}
                              </div>
                              {!hasEntry && (
                                <div className="mt-0.5 text-[10px] font-semibold text-slate-400">
                                  Bearbeiten für eine korrekte Rendite
                                </div>
                              )}
                            </td>
                            <td className="px-4 py-4 text-right">
                              <span className={`rounded-full px-3 py-1 text-xs font-extrabold ${scoreTone(holding.score || 0)} bg-black/[0.04]`}>
                                {formatNumber(holding.score, 0, "0")}
                              </span>
                            </td>
                            <td className="px-4 py-4 text-center">
                              <span
                                className={`rounded-full px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] ${
                                  holding.recommendation?.includes("BUY")
                                    ? "bg-emerald-500/10 text-emerald-700"
                                    : holding.recommendation?.includes("SELL") || holding.recommendation?.includes("AVOID")
                                      ? "bg-red-500/10 text-red-700"
                                      : "bg-amber-500/10 text-amber-700"
                                }`}
                              >
                                {recommendationLabel(holding.recommendation)}
                              </span>
                            </td>
                            <td className="px-6 py-4">
                              <div className="flex justify-end gap-2">
                                <button
                                  onClick={() => onAnalyzeStock(holding.ticker)}
                                  className="rounded-xl border border-black/8 bg-white px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-slate-700"
                                >
                                  Analysieren
                                </button>
                                <button
                                  onClick={() => openEditHolding({
                                    ticker: holding.ticker,
                                    shares: holding.shares,
                                    buyPrice: holding.buy_price,
                                    purchaseDate: holding.purchase_date,
                                  })}
                                  className={`rounded-xl border px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.14em] ${
                                    isEditing
                                      ? "border-[var(--accent)]/30 bg-[var(--accent-soft)] text-[var(--accent)]"
                                      : "border-black/8 bg-white text-slate-700"
                                  }`}
                                >
                                  {isEditing ? "Bearbeitung" : "Bearbeiten"}
                                </button>
                                <button
                                  onClick={() => onRemoveHolding(currentPortfolio.id, holding.ticker)}
                                  className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-red-700"
                                >
                                  Entfernen
                                </button>
                              </div>
                            </td>
                          </tr>
                          {isEditing && (
                            <tr className="border-b border-black/6 bg-[var(--accent-soft)]/30">
                              <td colSpan={10} className="px-6 py-4">
                                <div className="grid gap-4 xl:grid-cols-[1fr_1fr_1fr_auto] xl:items-end">
                                  <label className="block">
                                    <div className="mb-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                                      Anteile
                                    </div>
                                    <input
                                      type="number"
                                      min="0"
                                      step="0.0001"
                                      value={editHoldingShares}
                                      onChange={(e) => setEditHoldingShares(e.target.value)}
                                      className="w-full rounded-xl border border-black/8 bg-white px-3 py-2.5 text-sm font-semibold text-slate-800"
                                    />
                                  </label>
                                  <label className="block">
                                    <div className="mb-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                                      Kaufkurs (USD)
                                    </div>
                                    <input
                                      type="number"
                                      min="0"
                                      step="0.0001"
                                      value={editHoldingBuyPrice}
                                      onChange={(e) => setEditHoldingBuyPrice(e.target.value)}
                                      placeholder="Optional"
                                      className="w-full rounded-xl border border-black/8 bg-white px-3 py-2.5 text-sm font-semibold text-slate-800"
                                    />
                                  </label>
                                  <label className="block">
                                    <div className="mb-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                                      Kaufdatum
                                    </div>
                                    <input
                                      type="date"
                                      value={editHoldingPurchaseDate}
                                      onChange={(e) => setEditHoldingPurchaseDate(e.target.value)}
                                      className="w-full rounded-xl border border-black/8 bg-white px-3 py-2.5 text-sm font-semibold text-slate-800"
                                    />
                                  </label>
                                  <div className="flex justify-end gap-2">
                                    <button
                                      onClick={closeEditHolding}
                                      className="rounded-xl border border-black/8 bg-white px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-slate-700"
                                    >
                                      <span className="inline-flex items-center gap-1">
                                        <X size={12} />
                                        Abbrechen
                                      </span>
                                    </button>
                                    <button
                                      onClick={saveHoldingEdit}
                                      disabled={savingHoldingEdit || !editHoldingShares.trim()}
                                      className="rounded-xl bg-[var(--accent)] px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-white disabled:opacity-50"
                                    >
                                      <span className="inline-flex items-center gap-1">
                                        <Check size={12} />
                                        {savingHoldingEdit ? "Speichert" : "Speichern"}
                                      </span>
                                    </button>
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      )})}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          ) : (
            <section className="surface-panel rounded-[2.4rem] p-10 text-center">
              <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-[2rem] bg-black/[0.04]">
                <Plus size={32} className="text-slate-400" />
              </div>
              <h3 className="mt-6 text-2xl text-slate-900">Noch keine Positionen</h3>
              <p className="mx-auto mt-3 max-w-md text-sm leading-7 text-slate-500">
                Füge deine erste Position hinzu, um Rendite, Erträge, Risiko und Diversifikation auszuwerten.
              </p>
              <div className="mt-6 flex flex-wrap justify-center gap-3">
                <button
                  onClick={() => window.open(`/api/portfolio/${selectedPortfolio}/export/csv`)}
                  className="rounded-[1.2rem] border border-black/8 bg-white px-5 py-3 text-xs font-extrabold uppercase tracking-[0.16em] text-slate-700"
                >
                  CSV exportieren
                </button>
                {!isScalableManagedPortfolio && <button
                  onClick={() => setShowAddHoldingModal(true)}
                  className="rounded-[1.2rem] bg-[var(--accent)] px-5 py-3 text-xs font-extrabold uppercase tracking-[0.16em] text-white transition-colors hover:bg-[var(--accent-strong)]"
                >
                  Aktie hinzufügen
                </button>}
              </div>
            </section>
          )}
        </div>
      ) : (
        <section className="surface-panel rounded-[2.6rem] p-10 text-center">
          <div className="mx-auto flex h-24 w-24 items-center justify-center rounded-[2rem] bg-black/[0.04]">
            <LayoutGrid size={34} className="text-slate-400" />
          </div>
          <h3 className="mt-6 text-3xl text-slate-900">
            {portfolios.length === 0 ? "Erstelle dein erstes Portfolio" : "Portfolio auswählen"}
          </h3>
          <p className="mx-auto mt-4 max-w-xl text-base leading-7 text-slate-500">
            {portfolios.length === 0
              ? "Bündele Positionen, Allokation, Risiko und Entscheidungen an einem Ort."
              : "Wähle oben ein Portfolio aus, um die vollständige Arbeitsansicht zu öffnen."}
          </p>
          {portfolios.length === 0 && (
            <button
              onClick={() => {
                setCreatePortfolioError(null);
                setCreatePortfolioNotice(null);
                setShowCreateModal(true);
              }}
              className="mt-6 rounded-[1.3rem] bg-[var(--accent)] px-6 py-4 text-xs font-extrabold uppercase tracking-[0.18em] text-white transition-colors hover:bg-[var(--accent-strong)]"
            >
              Erstes Portfolio erstellen
            </button>
          )}
        </section>
      )}

      {paperDashboard ? (
        <PaperTradingPanel
          data={paperDashboard}
          onAnalyze={onAnalyzeStock}
          onRefresh={refreshPaperDashboard}
        />
      ) : (
        <ProviderStatePanel
          view="paper-trader"
          state={paperDashboardLoading ? (paperDashboardSlow ? "slow" : "loading") : paperDashboardError ? "error" : "empty"}
          title={
            paperDashboardLoading
              ? paperDashboardSlow
                ? "Paper-Lernkonto antwortet langsam"
                : "Paper-Lernkonto wird geladen"
              : paperDashboardError
                ? "Paper-Lernkonto nicht erreichbar"
                : "Noch keine Paper-Trading-Daten"
          }
          description={
            paperDashboardLoading
              ? "Demo-Trades, Geldfluss, Risikobuckets und Lernstände werden getrennt geladen."
              : paperDashboardError || "Der Provider hat geantwortet, aber noch keine Demo-Trades oder Lernstände geliefert."
          }
          source="Paper-Trading-Service"
          onRetry={() => void refreshPaperDashboard()}
          retryLabel="Paper-Daten neu laden"
        />
      )}

      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4" role="presentation">
          <div ref={createPortfolioDialogRef} role="dialog" aria-modal="true" aria-labelledby="create-portfolio-title" tabIndex={-1} className="surface-panel w-full max-w-md rounded-[2rem] p-6">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Neues Portfolio
            </div>
            <h3 id="create-portfolio-title" className="mt-2 text-2xl text-slate-900">Portfolio anlegen</h3>
            <input
              type="text"
              value={newPortfolioName}
              onChange={(e) => {
                setNewPortfolioName(e.target.value);
                setCreatePortfolioError(null);
              }}
              placeholder="Name des Portfolios"
              className="mt-5 w-full rounded-[1.2rem] border border-black/8 bg-white px-4 py-3 text-sm font-semibold text-slate-800"
              autoFocus
            />
            {createPortfolioError ? (
              <div role="alert" className="mt-3 rounded-[1rem] border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm font-bold text-red-700">
                {createPortfolioError}
              </div>
            ) : null}
            {createPortfolioNotice ? (
              <div role="status" aria-live="polite" className="mt-3 rounded-[1rem] border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-sm font-bold text-emerald-700">
                {createPortfolioNotice}
              </div>
            ) : null}
            <div className="mt-5 flex justify-end gap-3">
              <button
                onClick={() => {
                  setCreatePortfolioError(null);
                  setCreatePortfolioNotice(null);
                  setShowCreateModal(false);
                }}
                disabled={creatingPortfolio}
                className="rounded-[1rem] border border-black/8 bg-white px-4 py-2.5 text-xs font-extrabold uppercase tracking-[0.16em] text-slate-700"
              >
                Abbrechen
              </button>
              <button
                onClick={handleCreatePortfolio}
                disabled={!newPortfolioName.trim() || creatingPortfolio}
                className="rounded-[1rem] bg-[var(--accent)] px-4 py-2.5 text-xs font-extrabold uppercase tracking-[0.16em] text-white transition-colors hover:bg-[var(--accent-strong)] disabled:opacity-50"
              >
                {creatingPortfolio ? "Wird gespeichert..." : "Erstellen"}
              </button>
            </div>
          </div>
        </div>
      )}

      <AddHoldingModal
        isOpen={showAddHoldingModal}
        onClose={() => setShowAddHoldingModal(false)}
        onAdd={onAddHolding}
        portfolios={portfolios}
        initialTicker={newHolding.ticker}
        initialPrice={parseFloat(newHolding.buyPrice) || undefined}
      />

    </div>
  );
}
