import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Calendar, Clock, TrendingUp } from "lucide-react";
import { useCurrency } from "../context/CurrencyContext";
import { fetchJsonWithRetry } from "../lib/api";
import MeasuredChartFrame from "./MeasuredChartFrame";
import useRealtimeFeed from "../hooks/useRealtimeFeed";

interface HistoryItem {
  time: string;
  full_date?: string;
  price: number;
  volume?: number;
}

interface HistoryPayload {
  items?: HistoryItem[];
  meta?: {
    mode?: "live" | "fallback" | "snapshot" | string;
    stale?: boolean;
    source?: string;
    period?: string;
    interval?: string;
    points?: number;
    fallback_reason?: string;
  };
}

interface PriceChartProps {
  ticker: string;
  onStatsUpdate?: (
    stats: { change: number; changePct: number },
    periodLabel: string,
  ) => void;
}

interface IndicatorSeries {
  rsi: Array<number | null>;
  macd: Array<number | null>;
  sma20: Array<number | null>;
  sma50: Array<number | null>;
  sma200: Array<number | null>;
  bbUpper: Array<number | null>;
  bbLower: Array<number | null>;
  vwap: Array<number | null>;
}

const PERIODS = [
  { id: "1d", label: "1D", interval: "5m" },
  { id: "5d", label: "5D", interval: "15m" },
  { id: "1mo", label: "1M", interval: "1d" },
  { id: "1y", label: "1Y", interval: "1wk" },
  { id: "5y", label: "5Y", interval: "1mo" },
  { id: "max", label: "MAX", interval: "1mo" },
];

const HISTORY_STATUS_LABELS: Record<"loading" | "ready" | "stale" | "snapshot" | "unavailable", string> = {
  loading: "laedt",
  ready: "Live-Historie",
  stale: "gespeicherte Historie",
  snapshot: "Snapshot-Fallback",
  unavailable: "nicht verfuegbar",
};

const friendlyRealtimeError = (error: string) => {
  if (error === "snapshot_fetch_failed") return "Snapshot wird automatisch erneut geladen";
  if (error.startsWith("snapshot_http_401") || error.startsWith("snapshot_http_403")) return "Session pruefen, Snapshot nicht freigegeben";
  if (error === "ws_unavailable" || error === "websocket_unavailable") return "Realtime laeuft im Snapshot-Modus";
  if (error.startsWith("ws_closed_") || error === "ws_error") return "WebSocket deaktiviert, Snapshot-Fallback aktiv";
  return error.replaceAll("_", " ");
};

const dataStatusLabel = (
  historyState: "loading" | "ready" | "stale" | "snapshot" | "unavailable",
  connectionState: "live" | "degraded" | "snapshot",
  transportMode: "ws" | "snapshot",
) => {
  if (historyState === "unavailable") return "Kursdaten aktuell nicht verfuegbar";
  if (historyState === "snapshot") return "Snapshot-Fallback aktiv";
  if (historyState === "stale") return "Gespeicherte Historie aktiv, Provider wird erneut versucht";
  if (connectionState === "degraded") return "Live-Feed verzoegert, Chart bleibt nutzbar";
  if (connectionState === "snapshot" || transportMode === "snapshot") return "Snapshot-Feed aktiv";
  return "Live-Daten aktiv";
};

const INDICATOR_HELP: Record<string, string> = {
  RSI: "RSI misst Momentum: ueber 70 oft ueberkauft, unter 30 oft ueberverkauft. Kein Kaufsignal allein.",
  MACD: "MACD zeigt Trend-Momentum: steigendes Histogramm spricht fuer zunehmenden Aufwaertsdruck, fallend fuer nachlassenden Druck.",
  SMA: "SMA ist der gleitende Durchschnitt. 20/50/200 Tage zeigen kurz-, mittel- und langfristigen Trend.",
  Bollinger: "Bollinger-Baender zeigen normale Schwankungsbreite. Ausbrueche koennen Momentum oder Uebertreibung markieren.",
  Volume: "Volume zeigt Handelsaktivitaet. Bewegungen mit hohem Volumen sind belastbarer als duenne Moves.",
  VWAP: "VWAP ist der volumengewichtete Durchschnittspreis. Intraday oft Referenz, ob Kaeufer oder Verkaeufer Kontrolle haben.",
};

const emptyIndicators = (): IndicatorSeries => ({
  rsi: [],
  macd: [],
  sma20: [],
  sma50: [],
  sma200: [],
  bbUpper: [],
  bbLower: [],
  vwap: [],
});

const rollingAverage = (values: number[], period: number): Array<number | null> => {
  const out: Array<number | null> = new Array(values.length).fill(null);
  if (period <= 0) return out;
  let sum = 0;
  for (let idx = 0; idx < values.length; idx += 1) {
    sum += values[idx];
    if (idx >= period) {
      sum -= values[idx - period];
    }
    if (idx >= period - 1) {
      out[idx] = sum / period;
    }
  }
  return out;
};

const rollingStdDev = (values: number[], period: number): Array<number | null> => {
  const out: Array<number | null> = new Array(values.length).fill(null);
  for (let idx = period - 1; idx < values.length; idx += 1) {
    const window = values.slice(idx - period + 1, idx + 1);
    const mean = window.reduce((acc, val) => acc + val, 0) / period;
    const variance = window.reduce((acc, val) => acc + (val - mean) ** 2, 0) / period;
    out[idx] = Math.sqrt(variance);
  }
  return out;
};

const computeRsi = (prices: number[], period = 14): Array<number | null> => {
  const rsiValues: Array<number | null> = new Array(prices.length).fill(null);
  if (prices.length <= period) return rsiValues;

  let avgGain = 0;
  let avgLoss = 0;
  for (let idx = 1; idx <= period; idx += 1) {
    const diff = prices[idx] - prices[idx - 1];
    if (diff >= 0) {
      avgGain += diff;
    } else {
      avgLoss += -diff;
    }
  }
  avgGain /= period;
  avgLoss /= period;
  rsiValues[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);

  for (let idx = period + 1; idx < prices.length; idx += 1) {
    const diff = prices[idx] - prices[idx - 1];
    avgGain = (avgGain * (period - 1) + (diff > 0 ? diff : 0)) / period;
    avgLoss = (avgLoss * (period - 1) + (diff < 0 ? -diff : 0)) / period;
    rsiValues[idx] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  }
  return rsiValues;
};

const computeMacdHistogram = (prices: number[]): Array<number | null> => {
  if (!prices.length) return [];
  const ema = (src: number[], span: number): number[] => {
    const k = 2 / (span + 1);
    const out: number[] = [src[0]];
    for (let idx = 1; idx < src.length; idx += 1) {
      out.push(src[idx] * k + out[idx - 1] * (1 - k));
    }
    return out;
  };
  const ema12 = ema(prices, 12);
  const ema26 = ema(prices, 26);
  const macdLine = ema12.map((val, idx) => val - ema26[idx]);
  const signal = ema(macdLine, 9);
  return macdLine.map((val, idx) => val - signal[idx]);
};

export default function PriceChart({ ticker, onStatsUpdate }: PriceChartProps) {
  const { formatPrice } = useCurrency();
  const [data, setData] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(false);
  const [fetchErrorMessage, setFetchErrorMessage] = useState<string>("");
  const [period, setPeriod] = useState(PERIODS[2]);
  const [stats, setStats] = useState({ change: 0, changePct: 0 });
  const [showRSI, setShowRSI] = useState(false);
  const [showMACD, setShowMACD] = useState(false);
  const [showSMA, setShowSMA] = useState(true);
  const [showBollinger, setShowBollinger] = useState(false);
  const [showVolume, setShowVolume] = useState(true);
  const [showVWAP, setShowVWAP] = useState(false);
  const [retryCounter, setRetryCounter] = useState(0);
  const [indicators, setIndicators] = useState<IndicatorSeries>(emptyIndicators());
  const [historyState, setHistoryState] = useState<"loading" | "ready" | "stale" | "snapshot" | "unavailable">("loading");
  const [historyMeta, setHistoryMeta] = useState<HistoryPayload["meta"] | null>(null);
  const tickerSymbol = ticker.toUpperCase();
  const { quotes, connected, lastUpdated, connectionState, staleSeconds, transportMode, lastError } = useRealtimeFeed([ticker], true);
  const realtimeQuote = quotes[tickerSymbol];

  const requestIdRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const onStatsUpdateRef = useRef(onStatsUpdate);

  useEffect(() => {
    onStatsUpdateRef.current = onStatsUpdate;
  }, [onStatsUpdate]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!loading || fetchError) return;
    const timeoutGuard = window.setTimeout(() => {
      abortRef.current?.abort();
      setFetchError(true);
      setFetchErrorMessage("Kursverlauf braucht zu lange. Bitte Retry klicken.");
      setData([]);
      setLoading(false);
      setHistoryState("unavailable");
    }, 12000);
    return () => {
      window.clearTimeout(timeoutGuard);
    };
  }, [loading, fetchError, tickerSymbol, period.id]);

  useEffect(() => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const fetchHistory = async () => {
      setLoading(true);
      setHistoryState("loading");
      setFetchError(false);
      setFetchErrorMessage("");
      setData([]);
      setHistoryMeta(null);
      setIndicators(emptyIndicators());

      try {
        const unpackHistoryPayload = (payload: HistoryItem[] | HistoryPayload): { items: any[]; meta: HistoryPayload["meta"] | null } => {
          if (Array.isArray(payload)) {
            return { items: payload, meta: null };
          }
          if (payload && Array.isArray((payload as HistoryPayload).items)) {
            return { items: (payload as HistoryPayload).items || [], meta: (payload as HistoryPayload).meta || null };
          }
          return { items: [], meta: null };
        };

        const normalizeHistory = (raw: any[]): HistoryItem[] =>
          (raw || [])
            .map((item) => {
              const priceNum = Number(item?.price);
              const volumeNum = Number(item?.volume);
              return {
                time: String(item?.time ?? ""),
                full_date: item?.full_date ? String(item.full_date) : undefined,
                price: priceNum,
                volume: Number.isFinite(volumeNum) ? volumeNum : 0,
              } as HistoryItem;
            })
            .filter((item) => item.time && Number.isFinite(item.price));

        const historyRequests = [
          `/api/history/${tickerSymbol}?period=${period.id}&interval=${period.interval}`,
          `/api/history/${tickerSymbol}?period=1mo&interval=1d`,
        ];

        let normalized: HistoryItem[] = [];
        let responseMeta: HistoryPayload["meta"] | null = null;
        let lastRequestError: unknown = null;
        let usedSnapshotFallback = false;
        for (const url of historyRequests) {
          try {
            const histData = await fetchJsonWithRetry<HistoryItem[] | HistoryPayload>(
              url,
              { signal: controller.signal },
              { retries: 0, retryDelayMs: 250, timeoutMs: 3500 },
            );
            const unpacked = unpackHistoryPayload(histData);
            normalized = normalizeHistory(unpacked.items);
            responseMeta = unpacked.meta;
            if (normalized.length > 0) break;
          } catch (error) {
            lastRequestError = error;
          }
        }

        if (normalized.length === 0 && lastRequestError) {
          try {
            const snapshot = await fetchJsonWithRetry<any>(
              `/api/realtime/snapshot?symbols=${encodeURIComponent(tickerSymbol)}`,
              { signal: controller.signal },
              { retries: 0, retryDelayMs: 250, timeoutMs: 2500 },
            );
            const quote = Array.isArray(snapshot?.quotes)
              ? snapshot.quotes.find((item: any) => String(item?.symbol || "").toUpperCase() === tickerSymbol)
              : null;
            const fallbackPrice = Number(quote?.price);
            if (Number.isFinite(fallbackPrice)) {
              const now = Date.now();
              const fallbackVolume = Number(quote?.volume ?? 0) || 0;
              normalized = Array.from({ length: 5 }, (_, idx) => {
                const stamp = new Date(now - (4 - idx) * 15 * 60 * 1000);
                return {
                  time: stamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
                  full_date: stamp.toISOString(),
                  price: fallbackPrice,
                  volume: fallbackVolume,
                };
              });
              usedSnapshotFallback = true;
              responseMeta = {
                mode: "snapshot",
                stale: true,
                source: "realtime_snapshot",
                period: "snapshot",
                interval: "snapshot",
                points: normalized.length,
              };
            }
          } catch {
            // ignore and throw original history error
          }
          if (normalized.length === 0) {
            throw lastRequestError;
          }
        }

        if (requestIdRef.current !== requestId) return;
        normalized = normalized.map((item) => ({
          ...item,
          full_date: item.full_date || item.time,
          volume: Number.isFinite(item.volume as number) ? Number(item.volume) : 0,
        }));

        if (!normalized.length) {
          setData([]);
          setFetchError(true);
          setFetchErrorMessage("Keine Kursdaten erhalten. Bitte erneut versuchen.");
          setHistoryState("unavailable");
          return;
        }

        setData(normalized);
        setHistoryMeta(responseMeta);
        if (usedSnapshotFallback || responseMeta?.mode === "snapshot") {
          setHistoryState("snapshot");
        } else if (responseMeta?.stale || responseMeta?.mode === "fallback") {
          setHistoryState("stale");
        } else {
          setHistoryState("ready");
        }
        if (normalized.length > 1) {
          const first = normalized[0].price;
          const last = normalized[normalized.length - 1].price;
          const change = last - first;
          const changePct = first !== 0 ? (change / first) * 100 : 0;
          setStats({ change, changePct });
          onStatsUpdateRef.current?.({ change, changePct }, period.label);
        } else {
          setStats({ change: 0, changePct: 0 });
          onStatsUpdateRef.current?.({ change: 0, changePct: 0 }, period.label);
        }

        const prices = normalized.map((item) => item.price);
        const volumes = normalized.map((item) => item.volume || 0);
        const sma20 = rollingAverage(prices, 20);
        const sma50 = rollingAverage(prices, 50);
        const sma200 = rollingAverage(prices, 200);
        const std20 = rollingStdDev(prices, 20);
        const bbUpper = sma20.map((sma, idx) =>
          sma != null && std20[idx] != null ? sma + (std20[idx] as number) * 2 : null,
        );
        const bbLower = sma20.map((sma, idx) =>
          sma != null && std20[idx] != null ? sma - (std20[idx] as number) * 2 : null,
        );
        const rsi = computeRsi(prices, 14);
        const macd = computeMacdHistogram(prices);
        let cumulativePV = 0;
        let cumulativeVol = 0;
        const vwap = prices.map((pricePoint, idx) => {
          const volume = Math.max(0, volumes[idx] || 0);
          cumulativePV += pricePoint * volume;
          cumulativeVol += volume;
          return cumulativeVol > 0 ? cumulativePV / cumulativeVol : null;
        });

        setIndicators({
          rsi,
          macd,
          sma20,
          sma50,
          sma200,
          bbUpper,
          bbLower,
          vwap,
        });
      } catch (error) {
        if (controller.signal.aborted || requestIdRef.current !== requestId) {
          return;
        }
        const message = error instanceof Error ? error.message : "Kursdaten konnten nicht geladen werden.";
        if (message.includes("504")) {
          setFetchErrorMessage("Datenprovider-Timeout. Bitte mit Retry erneut laden.");
        } else if (message.includes("401")) {
          setFetchErrorMessage("Session abgelaufen. Bitte kurz neu einloggen und Retry klicken.");
        } else if (message.includes("404")) {
          setFetchErrorMessage("Keine Historie fuer diesen Zeitraum. Zeitraum wechseln oder Retry nutzen.");
        } else if (message.toLowerCase().includes("timeout")) {
          setFetchErrorMessage("Request-Timeout beim Laden des Kursverlaufs. Bitte Retry nutzen.");
        } else if (message.includes("Failed to fetch")) {
          setFetchErrorMessage("Netzwerkproblem beim Laden der Historie.");
        } else {
          setFetchErrorMessage(message);
        }
        setData([]);
        setHistoryMeta(null);
        setFetchError(true);
        setHistoryState("unavailable");
      } finally {
        if (!controller.signal.aborted && requestIdRef.current === requestId) {
          setLoading(false);
        }
      }
    };

    fetchHistory();
    return () => {
      controller.abort();
    };
  }, [tickerSymbol, period, retryCounter]);

  const chartData = useMemo(() => {
    const livePrice =
      realtimeQuote?.symbol?.toUpperCase() === tickerSymbol && Number.isFinite(realtimeQuote?.price)
        ? Number(realtimeQuote.price)
        : null;
    return data.map((entry, idx) => {
      const isLast = idx === data.length - 1;
      return {
        ...entry,
        price: isLast && livePrice != null ? livePrice : entry.price,
        _rsi: indicators.rsi[idx],
        _macd: indicators.macd[idx],
        _sma20: indicators.sma20[idx],
        _sma50: indicators.sma50[idx],
        _sma200: indicators.sma200[idx],
        _bbUpper: indicators.bbUpper[idx],
        _bbLower: indicators.bbLower[idx],
        _vwap: indicators.vwap[idx],
        _volume: entry.volume || 0,
      };
    });
  }, [data, indicators, realtimeQuote, tickerSymbol]);

  const isPositive = stats.changePct >= 0;
  const subPanels = [showVolume, showRSI, showMACD].filter(Boolean).length;
  const mainHeightPercent = subPanels > 0 ? Math.max(40, 100 - subPanels * 20) : 100;
  const subPanelHeightPercent = subPanels > 0 ? Math.max(18, Math.floor((100 - mainHeightPercent) / subPanels)) : 0;
  const hasUsableHistory = data.length > 0 && historyState !== "unavailable";
  const benignRealtimeError = lastError === "snapshot_fetch_failed" && hasUsableHistory;
  const displayedRealtimeError = benignRealtimeError ? "" : lastError;
  const staleForTicker = staleSeconds?.[tickerSymbol];
  const shouldShowDataStatus =
    historyState === "stale" ||
    historyState === "snapshot" ||
    historyState === "unavailable" ||
    connectionState !== "live" ||
    Boolean(displayedRealtimeError);
  const indicatorToggles: Array<{
    label: string;
    active: boolean;
    setActive: React.Dispatch<React.SetStateAction<boolean>>;
    activeTone: string;
    help: string;
  }> = [
    { label: "RSI", active: showRSI, setActive: setShowRSI, activeTone: "border-amber-500/30 bg-amber-500/10 text-amber-700", help: INDICATOR_HELP.RSI },
    { label: "MACD", active: showMACD, setActive: setShowMACD, activeTone: "border-sky-500/30 bg-sky-500/10 text-sky-700", help: INDICATOR_HELP.MACD },
    { label: "SMA", active: showSMA, setActive: setShowSMA, activeTone: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700", help: INDICATOR_HELP.SMA },
    { label: "Bollinger", active: showBollinger, setActive: setShowBollinger, activeTone: "border-fuchsia-500/30 bg-fuchsia-500/10 text-fuchsia-700", help: INDICATOR_HELP.Bollinger },
    { label: "Volume", active: showVolume, setActive: setShowVolume, activeTone: "border-indigo-500/30 bg-indigo-500/10 text-indigo-700", help: INDICATOR_HELP.Volume },
    { label: "VWAP", active: showVWAP, setActive: setShowVWAP, activeTone: "border-cyan-500/30 bg-cyan-500/10 text-cyan-700", help: INDICATOR_HELP.VWAP },
  ];

  const CustomTooltip = useCallback(
    ({ active, payload }: any) => {
      if (active && payload && payload.length) {
        const d = payload[0].payload;
        return (
          <div className="rounded-xl border border-black/8 bg-white/92 p-3 shadow-[0_18px_36px_rgba(17,24,39,0.1)]">
            <p className="mb-1 text-xs text-slate-500">{d.full_date || d.time}</p>
            <p className="text-lg font-bold text-slate-900">{formatPrice(d.price)}</p>
            {d._volume > 0 ? (
              <p className="mt-1 text-[10px] text-slate-500">
                Vol: {Number(d._volume).toLocaleString()}
              </p>
            ) : null}
            {d._rsi != null && showRSI ? (
              <p className="mt-1 text-[10px] text-amber-600">RSI: {d._rsi.toFixed(1)}</p>
            ) : null}
            {d._macd != null && showMACD ? (
              <p className="mt-1 text-[10px] text-sky-600">MACD: {d._macd.toFixed(3)}</p>
            ) : null}
          </div>
        );
      }
      return null;
    },
    [formatPrice, showMACD, showRSI],
  );

  return (
    <div className="surface-panel rounded-[2rem] p-6">
      <div className="mb-8 flex flex-col justify-between gap-4 md:flex-row md:items-center">
        <div>
          <div className="mb-1 flex items-center gap-2 text-slate-500">
            <TrendingUp size={16} className={isPositive ? "text-emerald-600" : "text-red-600"} />
            <span className="text-sm font-semibold">Price History ({period.label})</span>
            <span
              className={`rounded-full px-2 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] ${
                connected ? "bg-emerald-500/10 text-emerald-700" : "bg-slate-500/10 text-slate-500"
              }`}
            >
              {connected ? "Live" : transportMode === "snapshot" ? "Snapshot" : "Polling"}
            </span>
            <span
              className={`rounded-full px-2 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] ${
                historyState === "ready"
                  ? "bg-emerald-500/10 text-emerald-700"
                  : historyState === "stale"
                    ? "bg-amber-500/10 text-amber-700"
                    : historyState === "snapshot"
                      ? "bg-sky-500/10 text-sky-700"
                    : historyState === "unavailable"
                      ? "bg-red-500/10 text-red-700"
                      : "bg-slate-500/10 text-slate-500"
              }`}
            >
              {historyState === "ready"
                ? "ready"
                : historyState === "stale"
                  ? "fallback"
                  : historyState === "snapshot"
                    ? "snapshot"
                    : historyState}
            </span>
          </div>
          <div className="flex items-baseline gap-3">
            <div className={`text-xl font-bold ${isPositive ? "text-emerald-700" : "text-red-700"}`}>
              {isPositive ? "+" : ""}
              {stats.changePct.toFixed(2)}%
            </div>
            <div className="text-sm text-slate-500">
              ({isPositive ? "+" : ""}
              {formatPrice(stats.change)})
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1 rounded-xl border border-black/8 bg-white/80 p-1">
          {PERIODS.map((p) => (
            <button
              key={p.id}
              onClick={() => setPeriod(p)}
              className={`rounded-lg px-4 py-1.5 text-xs font-bold transition-all ${
                period.id === p.id
                  ? "bg-[var(--accent)] text-white shadow-[0_12px_24px_rgba(15,118,110,0.18)]"
                  : "text-slate-500 hover:bg-black/[0.04] hover:text-slate-900"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {indicatorToggles.map((toggle) => (
          <button
            key={toggle.label}
            onClick={() => toggle.setActive((prev) => !prev)}
            title={toggle.help}
            aria-label={`${toggle.label}: ${toggle.help}`}
            className={`group relative rounded-lg border px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.16em] transition-all ${
              toggle.active ? toggle.activeTone : "border-black/8 bg-white/80 text-slate-500"
            }`}
          >
            <span className="inline-flex items-center gap-1.5">
              {toggle.label}
              <span className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-current/20 bg-white/55 text-[9px] normal-case tracking-normal opacity-70">
                ?
              </span>
            </span>
            <span className="pointer-events-none absolute left-1/2 top-full z-30 mt-2 hidden w-64 -translate-x-1/2 rounded-[0.9rem] border border-black/8 bg-white/96 p-3 text-left text-[11px] font-semibold normal-case leading-5 tracking-normal text-slate-600 opacity-0 shadow-[0_16px_34px_rgba(15,23,42,0.14)] transition-opacity group-hover:block group-hover:opacity-100 group-focus-visible:block group-focus-visible:opacity-100">
              <span className="mb-1 block text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-900">
                {toggle.label}
              </span>
              {toggle.help}
            </span>
          </button>
        ))}
      </div>

      <MeasuredChartFrame
        className={`w-full ${subPanels > 0 ? "h-[520px]" : "h-[320px]"}`}
        minHeight={subPanels > 0 ? 520 : 320}
        fallback={
          <div className="flex h-full w-full items-center justify-center rounded-[1.4rem] border border-black/8 bg-white/70">
            <span className="text-sm text-slate-500">Chart-Layout wird vorbereitet...</span>
          </div>
        }
      >
        {(size) => {
          const totalHeight = Math.max(size.h, subPanels > 0 ? 520 : 320);
          const gapPx = subPanels > 0 ? 8 * (subPanels + 1) : 0;
          const availableHeight = Math.max(220, totalHeight - gapPx);
          const mainHeightPx = subPanels > 0
            ? Math.max(200, Math.floor((availableHeight * mainHeightPercent) / 100))
            : availableHeight;
          const subHeightPx = subPanels > 0
            ? Math.max(74, Math.floor((availableHeight - mainHeightPx) / subPanels))
            : 0;

          return loading ? (
          <div className="flex h-full w-full flex-col items-center justify-center gap-3 rounded-[1.4rem] border border-black/8 bg-white/70">
            <svg className="h-6 w-6 animate-spin text-[var(--accent)]" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="text-sm text-slate-500">Lade Kursverlauf...</span>
          </div>
        ) : fetchError ? (
          <div className="flex h-full w-full flex-col items-center justify-center gap-3 rounded-[1.4rem] border border-dashed border-red-200 bg-red-50/60 text-slate-600">
            <span className="text-2xl">!</span>
            <p className="text-sm font-semibold">Kursdaten konnten nicht geladen werden.</p>
            {fetchErrorMessage ? (
              <p className="max-w-md text-center text-xs text-slate-500">{fetchErrorMessage}</p>
            ) : null}
            <button
              onClick={() => setRetryCounter((prev) => prev + 1)}
              className="rounded-[0.8rem] border border-black/8 bg-white px-4 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50"
            >
              Retry
            </button>
          </div>
        ) : chartData.length > 0 ? (
          <div className="flex h-full w-full flex-col gap-2">
            <div style={{ height: mainHeightPx }} className="min-h-[200px]">
              <ResponsiveContainer width={size.w} height={mainHeightPx} minWidth={0} minHeight={180}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={isPositive ? "#0f766e" : "#dc2626"} stopOpacity={0.22} />
                      <stop offset="95%" stopColor={isPositive ? "#0f766e" : "#dc2626"} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(22,28,36,0.08)" vertical={false} />
                  <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fill: "#7c848f", fontSize: 10 }} minTickGap={30} />
                  <YAxis hide domain={["auto", "auto"]} />
                  <Tooltip content={<CustomTooltip />} cursor={{ stroke: "rgba(22,28,36,0.2)", strokeWidth: 1 }} />
                  {showBollinger ? (
                    <>
                      <Line type="monotone" dataKey="_bbUpper" stroke="#c026d3" strokeOpacity={0.6} strokeWidth={1.2} dot={false} />
                      <Line type="monotone" dataKey="_bbLower" stroke="#c026d3" strokeOpacity={0.6} strokeWidth={1.2} dot={false} />
                    </>
                  ) : null}
                  {showSMA ? (
                    <>
                      <Line type="monotone" dataKey="_sma20" stroke="#0f766e" strokeOpacity={0.9} strokeWidth={1.5} dot={false} />
                      <Line type="monotone" dataKey="_sma50" stroke="#0369a1" strokeOpacity={0.9} strokeWidth={1.4} dot={false} />
                      <Line type="monotone" dataKey="_sma200" stroke="#7c3aed" strokeOpacity={0.85} strokeWidth={1.3} dot={false} />
                    </>
                  ) : null}
                  {showVWAP ? (
                    <Line type="monotone" dataKey="_vwap" stroke="#0891b2" strokeWidth={1.4} strokeOpacity={0.9} dot={false} />
                  ) : null}
                  <Area type="monotone" dataKey="price" stroke={isPositive ? "#0f766e" : "#dc2626"} strokeWidth={2.4} fillOpacity={1} fill="url(#colorPrice)" animationDuration={850} />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {showVolume ? (
              <div style={{ height: subHeightPx }} className="min-h-[74px]">
                <ResponsiveContainer width={size.w} height={subHeightPx} minWidth={0} minHeight={74}>
                  <BarChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(22,28,36,0.06)" vertical={false} />
                    <XAxis dataKey="time" hide />
                    <YAxis hide />
                    <Bar dataKey="_volume" animationDuration={550}>
                      {chartData.map((entry, idx) => (
                        <Cell key={`vol-${idx}`} fill={(entry._macd ?? 0) >= 0 ? "#2563eb" : "#64748b"} fillOpacity={0.6} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <div className="px-2 text-[9px] font-bold uppercase tracking-wider text-slate-400">Volume</div>
              </div>
            ) : null}

            {showRSI ? (
              <div style={{ height: subHeightPx }} className="min-h-[74px]">
                <ResponsiveContainer width={size.w} height={subHeightPx} minWidth={0} minHeight={74}>
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(22,28,36,0.06)" vertical={false} />
                    <XAxis dataKey="time" hide />
                    <YAxis domain={[0, 100]} hide />
                    <ReferenceLine y={70} stroke="#dc2626" strokeDasharray="4 4" strokeOpacity={0.5} />
                    <ReferenceLine y={30} stroke="#0f766e" strokeDasharray="4 4" strokeOpacity={0.5} />
                    <Line type="monotone" dataKey="_rsi" stroke="#d97706" strokeWidth={1.5} dot={false} animationDuration={600} />
                  </LineChart>
                </ResponsiveContainer>
                <div className="flex justify-between px-2 text-[9px] font-bold uppercase tracking-wider text-slate-400">
                  <span>RSI 14</span>
                  <span className="text-red-400">70</span>
                  <span className="text-emerald-500">30</span>
                </div>
              </div>
            ) : null}

            {showMACD ? (
              <div style={{ height: subHeightPx }} className="min-h-[74px]">
                <ResponsiveContainer width={size.w} height={subHeightPx} minWidth={0} minHeight={74}>
                  <BarChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(22,28,36,0.06)" vertical={false} />
                    <XAxis dataKey="time" hide />
                    <YAxis hide />
                    <ReferenceLine y={0} stroke="rgba(22,28,36,0.15)" />
                    <Bar dataKey="_macd" animationDuration={600}>
                      {chartData.map((entry, idx) => (
                        <Cell key={`macd-${idx}`} fill={(entry._macd ?? 0) >= 0 ? "#0f766e" : "#dc2626"} fillOpacity={0.7} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <div className="px-2 text-[9px] font-bold uppercase tracking-wider text-slate-400">
                  MACD Histogram (12/26/9)
                </div>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center rounded-[1.4rem] border border-dashed border-black/8 bg-white/70 text-slate-500">
            <Calendar size={32} className="mb-2 opacity-30" />
            <p className="text-sm">Keine historischen Daten fuer diesen Zeitraum.</p>
          </div>
        );
        }}
      </MeasuredChartFrame>

      <div className="mt-4 flex items-center justify-between text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
        <div className="flex items-center gap-1">
          <Clock size={10} />
          {period.id === "1d" ? "Intraday Minute Data" : "Historical Market Data"}
        </div>
        <div>
          {connected && lastUpdated
            ? `Live ${new Date(lastUpdated).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`
            : "YFinance-Engine v2.0"}
        </div>
      </div>
      {shouldShowDataStatus ? (
        <div
          className={`mt-3 rounded-[0.9rem] border px-3 py-2 text-[11px] font-semibold ${
            historyState === "unavailable"
              ? "border-red-500/20 bg-red-500/10 text-red-700"
              : "border-amber-500/20 bg-amber-500/10 text-amber-700"
          }`}
        >
          Datenstatus: {dataStatusLabel(historyState, connectionState, transportMode)}.
          {" "}Kursverlauf: {HISTORY_STATUS_LABELS[historyState]} - Feed: {transportMode}
          {typeof staleForTicker === "number" && staleForTicker > 5 ? ` - stale ${staleForTicker}s` : ""}
          {displayedRealtimeError ? ` - ${friendlyRealtimeError(displayedRealtimeError)}` : ""}
        </div>
      ) : null}
      {historyMeta ? (
        <div className="mt-2 rounded-[0.9rem] border border-black/8 bg-white/70 px-3 py-2 text-[11px] font-semibold text-slate-500">
          History: {historyMeta.source || "unknown"} - {historyMeta.period || "n/a"}/{historyMeta.interval || "n/a"}
          {typeof historyMeta.points === "number" ? ` - ${historyMeta.points} Punkte` : ""}
          {historyMeta.fallback_reason ? ` - ${String(historyMeta.fallback_reason).replaceAll("_", " ")}` : ""}
        </div>
      ) : null}
    </div>
  );
}
