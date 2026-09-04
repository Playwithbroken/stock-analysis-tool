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
import {
  calculateChartChangePct,
  describeChartFeed,
  formatChartAxisDate,
  formatChartTooltipDate,
  parseChartNumber,
  resolveChartPointIndex,
  resolveChartTooltipPoint,
} from "../lib/chartTooltip";
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
    requested_period?: string;
    requested_interval?: string;
    points?: number;
    fallback_reason?: string;
    error?: string;
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
  { id: "1d", label: "1T", title: "1 Tag", interval: "5m" },
  { id: "5d", label: "5T", title: "5 Tage", interval: "15m" },
  { id: "1mo", label: "1M", title: "1 Monat", interval: "1d" },
  { id: "1y", label: "1J", title: "1 Jahr", interval: "1wk" },
  { id: "5y", label: "5J", title: "5 Jahre", interval: "1mo" },
  { id: "max", label: "MAX", title: "Gesamter Zeitraum", interval: "1mo" },
];

type HistoryState = "loading" | "ready" | "stale" | "snapshot" | "unavailable";

const HISTORY_STATUS_LABELS: Record<HistoryState, string> = {
  loading: "lädt",
  ready: "Historie geladen",
  stale: "gespeicherte Historie",
  snapshot: "Snapshot-Fallback",
  unavailable: "nicht verfügbar",
};

const friendlyRealtimeError = (error: string) => {
  if (error === "snapshot_fetch_failed") return "Snapshot wird erneut geladen";
  if (error.startsWith("snapshot_http_401") || error.startsWith("snapshot_http_403")) return "Session prüfen, Snapshot nicht freigegeben";
  if (error === "ws_unavailable" || error === "websocket_unavailable") return "Realtime läuft im Snapshot-Modus";
  if (error.startsWith("ws_closed_") || error === "ws_error") return "WebSocket deaktiviert, Snapshot-Fallback aktiv";
  return error.replaceAll("_", " ");
};

const dataStatusLabel = (
  historyState: HistoryState,
  feedStatus: string,
) => {
  if (historyState === "unavailable") return "Kursdaten aktuell nicht verfügbar";
  if (historyState === "snapshot") return "Snapshot-Fallback aktiv";
  if (historyState === "stale") return "Gespeicherte Historie aktiv";
  return `${feedStatus}, Historie separat`;
};

const friendlyHistoryReason = (reason?: string) => {
  if (!reason) return "";
  if (reason === "provider_unavailable_using_last_good_history") return "Provider langsam, letzter guter Kursverlauf aktiv";
  if (reason === "provider_timeout") return "Datenprovider antwortet zu langsam";
  if (reason === "no_history_available") return "Für diesen Zeitraum sind aktuell keine historischen Kurse verfügbar. Der Live-Kurs bleibt davon unabhängig.";
  if (reason === "no_history_or_snapshot_available") return "Weder Historie noch Snapshot liefern gerade Daten";
  return reason.replaceAll("_", " ");
};

const displayMetaValue = (value?: string | number | null, fallback = "offen") => {
  if (value === null || value === undefined || value === "") return fallback;
  const text = String(value);
  if (text.toLowerCase() === "unknown" || text.toLowerCase() === "n/a") return fallback;
  return text;
};

const INDICATOR_HELP: Record<string, string> = {
  RSI: "RSI misst Momentum: über 70 oft überkauft, unter 30 oft überverkauft. Kein Kaufsignal allein.",
  MACD: "MACD zeigt Trend-Momentum: Ein steigendes Histogramm spricht für zunehmenden Aufwärtsdruck, ein fallendes für nachlassenden Druck.",
  SMA: "SMA ist der gleitende Durchschnitt. 20/50/200 Tage zeigen kurz-, mittel- und langfristigen Trend.",
  Bollinger: "Bollinger-Bänder zeigen die normale Schwankungsbreite. Ausbrüche können Momentum oder Übertreibung markieren.",
  Volume: "Volumen zeigt die Handelsaktivität. Bewegungen mit hohem Volumen sind belastbarer als dünne Bewegungen.",
  VWAP: "VWAP ist der volumengewichtete Durchschnittspreis. Intraday dient er oft als Referenz, ob Käufer oder Verkäufer die Kontrolle haben.",
  EdgeLevels: "Institutionelle Edge Level: Volume Profile POC (gelb), VAH/VAL (grün/rot) und Options GEX Call/Put Walls.",
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
  const [discardedPoints, setDiscardedPoints] = useState(0);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(false);
  const [fetchErrorMessage, setFetchErrorMessage] = useState<string>("");
  const [period, setPeriod] = useState(PERIODS[2]);
  const [inspectedIndex, setInspectedIndex] = useState<number | null>(null);
  const [tooltipSuppressed, setTooltipSuppressed] = useState(false);
  const [touchSelection, setTouchSelection] = useState(() =>
    typeof window !== "undefined" && window.matchMedia("(hover: none)").matches,
  );
  useEffect(() => {
    const query = window.matchMedia("(hover: none)");
    const updateInputMode = () => setTouchSelection(query.matches);
    updateInputMode();
    query.addEventListener("change", updateInputMode);
    return () => query.removeEventListener("change", updateInputMode);
  }, []);
  const [loadedHistoryKey, setLoadedHistoryKey] = useState("");
  const [showRSI, setShowRSI] = useState(false);
  const [showMACD, setShowMACD] = useState(false);
  const [showSMA, setShowSMA] = useState(true);
  const [showBollinger, setShowBollinger] = useState(false);
  const [showVolume, setShowVolume] = useState(true);
  const [showVWAP, setShowVWAP] = useState(false);
  const [showEdgeLevels, setShowEdgeLevels] = useState(false);
  const [edgeOverlay, setEdgeOverlay] = useState<{
    poc?: number;
    vah?: number;
    val?: number;
    call_wall?: number;
    put_wall?: number;
  } | null>(null);
  const [retryCounter, setRetryCounter] = useState(0);
  const [indicators, setIndicators] = useState<IndicatorSeries>(emptyIndicators());
  const [historyState, setHistoryState] = useState<HistoryState>("loading");
  const [historyMeta, setHistoryMeta] = useState<HistoryPayload["meta"] | null>(null);
  const tickerSymbol = ticker.toUpperCase();

  useEffect(() => {
    if (!showEdgeLevels || !tickerSymbol) {
      setEdgeOverlay(null);
      return;
    }
    let active = true;
    Promise.allSettled([
      fetchJsonWithRetry<any>(`/api/trading/volume-profile/${tickerSymbol}`, {}, { retries: 0, timeoutMs: 5000 }),
      fetchJsonWithRetry<any>(`/api/trading/gex/${tickerSymbol}`, {}, { retries: 0, timeoutMs: 5000 }),
    ]).then(([vpRes, gexRes]) => {
      if (!active) return;
      const vp = vpRes.status === "fulfilled" ? vpRes.value : null;
      const gex = gexRes.status === "fulfilled" ? gexRes.value : null;
      if (vp || gex) {
        setEdgeOverlay({
          poc: typeof vp?.poc_price === "number" ? vp.poc_price : undefined,
          vah: typeof vp?.vah_price === "number" ? vp.vah_price : undefined,
          val: typeof vp?.val_price === "number" ? vp.val_price : undefined,
          call_wall: typeof gex?.call_wall === "number" ? gex.call_wall : undefined,
          put_wall: typeof gex?.put_wall === "number" ? gex.put_wall : undefined,
        });
      }
    });
    return () => {
      active = false;
    };
  }, [showEdgeLevels, tickerSymbol]);
  const { quotes, connected, connectionState, staleSeconds, transportMode, lastError } = useRealtimeFeed([ticker], true);
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
      setFetchErrorMessage("Kursverlauf braucht zu lange. Bitte erneut laden.");
      setData([]);
      setLoading(false);
      setHistoryState("unavailable");
    }, 12000);
    return () => {
      window.clearTimeout(timeoutGuard);
    };
  }, [loading, fetchError, tickerSymbol, period.id, retryCounter]);

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
      setDiscardedPoints(0);
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
            .flatMap((item): HistoryItem[] => {
              const priceNum = parseChartNumber(item?.price);
              const time = typeof item?.time === "string" ? item.time.trim() : "";
              if (priceNum === null || !time) return [];
              const volumeNum = parseChartNumber(item?.volume);
              return [{
                time,
                full_date: typeof item?.full_date === "string" ? item.full_date : undefined,
                price: priceNum,
                volume: volumeNum ?? 0,
              }];
            });

        const historyRequests = [
          `/api/history/${tickerSymbol}?period=${period.id}&interval=${period.interval}`,
        ];

        let normalized: HistoryItem[] = [];
        let rejectedCount = 0;
        let responseMeta: HistoryPayload["meta"] | null = null;
        let lastRequestError: unknown = null;
        for (const url of historyRequests) {
          try {
            const histData = await fetchJsonWithRetry<HistoryItem[] | HistoryPayload>(
              url,
              { signal: controller.signal },
              { retries: 0, retryDelayMs: 250, timeoutMs: 10000 },
            );
            const unpacked = unpackHistoryPayload(histData);
            if (
              unpacked.meta?.mode === "snapshot" ||
              (unpacked.meta?.period && unpacked.meta.period !== period.id) ||
              (unpacked.meta?.interval && unpacked.meta.interval !== period.interval)
            ) {
              throw new Error("Die Datenquelle liefert keine passende Historie für diesen Zeitraum. Bitte erneut laden.");
            }
            normalized = normalizeHistory(unpacked.items);
            rejectedCount = unpacked.items.length - normalized.length;
            responseMeta = unpacked.meta;
            if (normalized.length > 0) break;
          } catch (error) {
            lastRequestError = error;
          }
        }

        if (normalized.length === 0 && lastRequestError) throw lastRequestError;

        if (controller.signal.aborted || requestIdRef.current !== requestId) return;
        setDiscardedPoints(rejectedCount);
        normalized = normalized.map((item) => ({
          ...item,
          full_date: item.full_date || item.time,
          volume: Number.isFinite(item.volume as number) ? Number(item.volume) : 0,
        }));

        if (!normalized.length) {
          setData([]);
          setHistoryMeta(responseMeta);
          setFetchError(true);
          setFetchErrorMessage(
            responseMeta?.error ||
              friendlyHistoryReason(responseMeta?.fallback_reason) ||
              "Keine Kursdaten erhalten. Bitte erneut versuchen.",
          );
          setHistoryState("unavailable");
          return;
        }

        setData(normalized);
        setLoadedHistoryKey(`${tickerSymbol}:${period.id}`);
        setHistoryMeta(responseMeta);
        if (responseMeta?.stale || responseMeta?.mode === "fallback") {
          setHistoryState("stale");
        } else {
          setHistoryState("ready");
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
          setFetchErrorMessage("Datenprovider-Timeout. Bitte erneut laden.");
        } else if (message.includes("401")) {
          setFetchErrorMessage("Session abgelaufen. Bitte kurz neu einloggen und den Kursverlauf erneut laden.");
        } else if (message.includes("404")) {
          setFetchErrorMessage("Keine Historie für diesen Zeitraum. Zeitraum wechseln oder erneut laden.");
        } else if (message.toLowerCase().includes("timeout")) {
          setFetchErrorMessage("Zeitüberschreitung beim Laden des Kursverlaufs. Bitte erneut laden.");
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
    return data.map((entry, idx) => {
      return {
        ...entry,
        _chartIndex: idx,
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
  }, [data, indicators]);

  // Snapshot updated_at can be a retrieval time, not the price's market time.
  // Keep the quote separate rather than relabeling a historical observation.
  const feedPrice = realtimeQuote?.symbol?.toUpperCase() === tickerSymbol &&
    Number.isFinite(realtimeQuote?.price) && realtimeQuote.price > 0
    ? realtimeQuote.price : null;
  const feedStatus = describeChartFeed({
    connected: connected && feedPrice !== null,
    connectionState,
    transportMode,
    streaming: realtimeQuote?.streaming,
  });

  const stats = useMemo(() => {
    if (chartData.length < 2) return { change: 0, changePct: 0 };
    const first = chartData[0].price;
    const last = chartData[chartData.length - 1].price;
    return { change: last - first, changePct: calculateChartChangePct(first, last) ?? 0 };
  }, [chartData]);

  useEffect(() => {
    if (!loading && !fetchError && chartData.length && loadedHistoryKey === `${tickerSymbol}:${period.id}`) {
      onStatsUpdateRef.current?.(stats, period.label);
    }
  }, [stats, loading, fetchError, chartData.length, loadedHistoryKey, tickerSymbol, period.id, period.label]);

  useEffect(() => {
    setInspectedIndex(null);
    setTooltipSuppressed(false);
  }, [data, period.id, tickerSymbol]);

  const inspectFromControls = useCallback((index: number) => {
    // A click tooltip belongs to the chart's last tap, not the slider's new point.
    setTooltipSuppressed(true);
    setInspectedIndex(index);
  }, []);

  const displayedIndex = chartData.length
    ? Math.min(inspectedIndex ?? chartData.length - 1, chartData.length - 1)
    : 0;
  const inspectedPoint = chartData[displayedIndex] || null;
  const latestChartPrice = chartData.at(-1)?.price;
  const inspectedChangePct = inspectedPoint
    ? calculateChartChangePct(inspectedPoint.price, latestChartPrice)
    : null;
  const yDomain = useMemo(() => {
    if (!chartData || chartData.length === 0) return ["auto", "auto"];
    let min = Infinity;
    let max = -Infinity;
    for (const pt of chartData) {
      if (typeof pt.price === "number") {
        if (pt.price < min) min = pt.price;
        if (pt.price > max) max = pt.price;
      }
    }
    if (!Number.isFinite(min) || !Number.isFinite(max)) return ["auto", "auto"];
    if (showEdgeLevels && edgeOverlay) {
      const levels = [edgeOverlay.poc, edgeOverlay.vah, edgeOverlay.val, edgeOverlay.call_wall, edgeOverlay.put_wall].filter(
        (v): v is number => typeof v === "number" && v > 0 && Math.abs(v - min) / min < 0.40
      );
      for (const lvl of levels) {
        if (lvl < min) min = lvl;
        if (lvl > max) max = lvl;
      }
    }
    const pad = (max - min) * 0.05 || 1;
    return [Math.max(0, min - pad), max + pad];
  }, [chartData, showEdgeLevels, edgeOverlay]);

  const historicalPriceLabel =
    period.interval === "1mo" ? "Monatskurs" : period.interval === "1wk" ? "Wochenkurs" : "Kurs";
  const inspectChartPoint = useCallback(
    (state: any) => {
      const activeIndex = resolveChartPointIndex(state?.activeTooltipIndex, chartData.length);
      if (activeIndex !== null) {
        setTooltipSuppressed(false);
        setInspectedIndex(activeIndex);
        return;
      }
      const point = resolveChartTooltipPoint(state?.activePayload);
      if (!point) return;
      const pointKey = point.full_date || point.time;
      const nextIndex = chartData.findIndex((item) => (item.full_date || item.time) === pointKey);
      if (nextIndex >= 0) {
        setTooltipSuppressed(false);
        setInspectedIndex(nextIndex);
      }
    },
    [chartData],
  );

  const isPositive = stats.changePct >= 0;
  const subPanels = [showVolume, showRSI, showMACD].filter(Boolean).length;
  const mainHeightPercent = subPanels > 0 ? Math.max(40, 100 - subPanels * 20) : 100;
  const subPanelHeightPercent = subPanels > 0 ? Math.max(18, Math.floor((100 - mainHeightPercent) / subPanels)) : 0;
  const hasUsableHistory = data.length > 0 && historyState !== "unavailable";
  const benignRealtimeError = lastError === "snapshot_fetch_failed" && hasUsableHistory;
  const displayedRealtimeError = benignRealtimeError || (lastError === "snapshot_fetch_failed" && historyState === "unavailable")
    ? ""
    : lastError;
  const realtimeFallbackNote = benignRealtimeError
    ? "Realtime-Snapshot wird erneut versucht, Historie bleibt nutzbar"
    : "";
  const staleForTicker = staleSeconds?.[tickerSymbol];
  const feedNeedsAttention =
    connectionState === "degraded" ||
    ((connectionState === "snapshot" || transportMode === "snapshot") && !hasUsableHistory);
  const shouldShowDataStatus =
    historyState === "stale" ||
    historyState === "snapshot" ||
    historyState === "unavailable" ||
    feedNeedsAttention ||
    Boolean(realtimeFallbackNote) ||
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
    { label: "⚡ Edge", active: showEdgeLevels, setActive: setShowEdgeLevels, activeTone: "border-amber-500/40 bg-amber-500/15 text-amber-900 dark:text-amber-300 font-bold", help: INDICATOR_HELP.EdgeLevels },
  ];
  const activeIndicatorHelp = indicatorToggles.filter((toggle) => toggle.active);

  const CustomTooltip = useCallback(
    ({ active, payload }: any) => {
      const d = active ? resolveChartTooltipPoint(payload) : null;
      if (d) {
        const changeToLatest = calculateChartChangePct(d.price, latestChartPrice);
        return (
          <div className="min-w-36 rounded-xl border border-black/10 bg-white/96 p-3 shadow-[0_18px_36px_rgba(17,24,39,0.16)] dark:border-white/15 dark:bg-slate-950/96">
            <p className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
              Datum / Zeit
            </p>
            <p className="mt-1 text-xs font-semibold text-slate-700 dark:text-slate-200">
              {formatChartTooltipDate(d, period.id)}
            </p>
            <p className="mt-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
              {historicalPriceLabel}
            </p>
            <p className="mt-0.5 text-lg font-black text-slate-950 dark:text-white">{formatPrice(d.price)}</p>
            {changeToLatest != null ? (
              <p className={`mt-1 text-[10px] font-bold ${changeToLatest >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400"}`}>
                Änderung bis zum letzten Kurspunkt {changeToLatest >= 0 ? "+" : ""}{changeToLatest.toLocaleString("de-DE", { maximumFractionDigits: 2 })}% · ohne Div.
              </p>
            ) : null}
            {Number(d._volume) > 0 ? (
              <p className="mt-1 text-[10px] text-slate-500 dark:text-slate-400">
                Volumen: {Number(d._volume).toLocaleString("de-DE")}
              </p>
            ) : null}
            {d._rsi != null && showRSI ? (
              <p className="mt-1 text-[10px] text-amber-600 dark:text-amber-400">RSI: {d._rsi.toFixed(1)}</p>
            ) : null}
            {d._macd != null && showMACD ? (
              <p className="mt-1 text-[10px] text-sky-600 dark:text-sky-400">MACD: {d._macd.toFixed(3)}</p>
            ) : null}
          </div>
        );
      }
      return null;
    },
    [formatPrice, historicalPriceLabel, latestChartPrice, period.id, showMACD, showRSI],
  );

  return (
    <div className="price-chart analysis-primary-panel surface-panel rounded-[1.5rem] p-4 sm:rounded-[2rem] sm:p-6">
      <div className="mb-5 flex flex-col justify-between gap-4 md:flex-row md:flex-wrap md:items-center">
        <div>
          <div className="mb-1 flex flex-wrap items-center gap-2 text-slate-500">
            <TrendingUp size={16} className={isPositive ? "text-emerald-600" : "text-red-600"} />
            <span className="text-sm font-semibold">Kursverlauf ({period.label})</span>
            <span
              className={`rounded-full px-2 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] ${
                feedStatus === "Live-Feed" ? "bg-emerald-500/10 text-emerald-700" : "bg-slate-500/10 text-slate-500"
              }`}
            >
              {feedStatus}
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
              {HISTORY_STATUS_LABELS[historyState]}
            </span>
          </div>
          <div className="flex items-baseline gap-3">
            <div className={`text-xl font-bold ${isPositive ? "text-emerald-700" : "text-red-700"}`}>
              {loading || fetchError ? "—" : `${isPositive ? "+" : ""}${stats.changePct.toFixed(2)}%`}
            </div>
            {!loading && !fetchError ? <div className="text-sm text-slate-500">
              ({isPositive ? "+" : ""}
              {formatPrice(stats.change)})
            </div> : null}
          </div>
          {feedPrice !== null ? (
            <div role="group" aria-label="Separater Feed-Kurs" className="mt-2 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-xs text-slate-500">
              <span>Letzter Feed-Kurs</span>
              <span className="font-semibold text-slate-700">{formatPrice(feedPrice)}</span>
              <span className="text-[11px]">Separat von der Historie</span>
            </div>
          ) : null}
        </div>

        <div
          className="chart-period-selector grid w-full max-w-full grid-cols-6 items-center gap-0.5 rounded-xl border border-black/8 bg-white/80 p-1 sm:flex sm:w-auto sm:gap-1"
          role="group"
          aria-label="Zeitraum für den Kursverlauf"
        >
          {PERIODS.map((p) => (
            <button
              key={p.id}
              type="button"
              aria-label={`${p.title} im Kursverlauf anzeigen`}
              aria-pressed={period.id === p.id}
              title={p.title}
              onClick={() => {
                setInspectedIndex(null);
                if (period.id === p.id) {
                  setRetryCounter((current) => current + 1);
                  return;
                }
                setPeriod(p);
              }}
              className={`relative min-h-10 min-w-0 shrink-0 touch-manipulation rounded-lg px-1 py-2 text-xs font-bold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 sm:min-w-11 sm:px-4 ${
                period.id === p.id
                  ? "bg-[var(--accent)] text-white shadow-[0_12px_24px_rgba(15,118,110,0.18)]"
                  : "text-slate-500 hover:bg-black/[0.04] hover:text-slate-900"
              }`}
            >
              <span className="inline-flex items-center gap-1.5">
                {p.label}
                {loading && period.id === p.id ? (
                  <span className="absolute bottom-1 left-1/2 h-1 w-1 -translate-x-1/2 animate-pulse rounded-full bg-current opacity-80" aria-hidden="true" />
                ) : null}
              </span>
            </button>
          ))}
        </div>
      </div>

      <div
        className="chart-indicator-controls relative mb-4 grid grid-cols-3 gap-2 sm:flex sm:flex-wrap"
        role="group"
        aria-label="Technische Indikatoren"
      >
        {indicatorToggles.map((toggle) => (
          <button
            key={toggle.label}
            type="button"
            onClick={() => toggle.setActive((prev) => !prev)}
            title={toggle.help}
            aria-label={`${toggle.label}: ${toggle.help}`}
            aria-pressed={toggle.active}
            data-indicator={toggle.label}
            className={`chart-indicator-toggle group flex min-h-10 min-w-0 touch-manipulation items-center justify-center rounded-lg border px-1.5 py-2 text-[10px] font-bold uppercase tracking-[0.06em] transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 sm:w-auto sm:shrink-0 sm:px-3 sm:tracking-[0.12em] ${
              toggle.active ? toggle.activeTone : "border-black/8 bg-white/80 text-slate-500"
            }`}
          >
            <span className="inline-flex items-center gap-1.5">
              {toggle.label}
              <span className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-current/20 bg-white/55 text-[9px] normal-case tracking-normal opacity-70">
                ?
              </span>
            </span>
            <span aria-hidden="true" className="indicator-hover-help pointer-events-none rounded-[0.9rem] border border-black/8 bg-white/96 p-3 text-left text-[11px] font-semibold normal-case leading-5 tracking-normal text-slate-600 shadow-[0_16px_34px_rgba(15,23,42,0.14)]">
              <span className="mb-1 block text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-900">
                {toggle.label}
              </span>
              {toggle.help}
            </span>
          </button>
        ))}
      </div>
      {activeIndicatorHelp.length ? (
        <>
          <details className="indicator-mobile-help mb-4 rounded-[0.9rem] border border-black/8 bg-white/68 sm:hidden">
            <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 px-3.5 py-2.5 text-[11px] font-extrabold uppercase tracking-[0.13em] text-slate-700">
              <span>Aktive Indikatoren erklären</span>
              <span className="rounded-full bg-black/[0.05] px-2 py-1 text-[10px] text-slate-500">
                {activeIndicatorHelp.length}
              </span>
            </summary>
            <div className="grid gap-2 border-t border-black/8 p-2.5">
              {activeIndicatorHelp.map((toggle) => (
                <div
                  key={toggle.label}
                  className="indicator-help-card rounded-[0.8rem] border border-black/8 bg-white/68 px-3 py-2.5 text-[11px] leading-5 text-slate-600"
                >
                  <span className="indicator-help-label mr-1 font-extrabold uppercase tracking-[0.14em] text-slate-800">
                    {toggle.label}
                  </span>
                  {toggle.help}
                </div>
              ))}
            </div>
          </details>

          <div className="mb-4 hidden gap-2 sm:grid sm:grid-cols-2 xl:grid-cols-3">
            {activeIndicatorHelp.slice(0, 3).map((toggle) => (
              <div
                key={toggle.label}
                className="indicator-help-card rounded-[0.9rem] border border-black/8 bg-white/68 px-3.5 py-2.5 text-[11px] leading-5 text-slate-600"
              >
                <span className="indicator-help-label mr-1 font-extrabold uppercase tracking-[0.14em] text-slate-800">
                  {toggle.label}
                </span>
                {toggle.help}
              </div>
            ))}
          </div>
          {activeIndicatorHelp.length > 3 ? (
            <details className="indicator-mobile-help indicator-extra-help mb-4 hidden rounded-[0.9rem] border border-black/8 bg-white/68 sm:block">
              <summary className="min-h-11 cursor-pointer px-3.5 py-3 text-xs font-semibold text-slate-700">
                Weitere {activeIndicatorHelp.length - 3} Indikatoren erklären
              </summary>
              <div className="grid gap-2 border-t border-black/8 p-2.5 sm:grid-cols-2 xl:grid-cols-3">
                {activeIndicatorHelp.slice(3).map((toggle) => (
                  <div key={toggle.label} className="indicator-help-card rounded-[0.8rem] border border-black/8 bg-white/68 px-3 py-2.5 text-[11px] leading-5 text-slate-600">
                    <span className="indicator-help-label mr-1 font-extrabold uppercase tracking-[0.14em] text-slate-800">{toggle.label}</span>
                    {toggle.help}
                  </div>
                ))}
              </div>
            </details>
          ) : null}
        </>
      ) : null}

      <div className="mb-3 rounded-[1rem] border border-black/8 bg-white/72 px-3 py-2.5 dark:border-white/10 dark:bg-slate-950/55">
        <div className="flex flex-wrap items-center justify-between gap-2" aria-live="polite">
          <div>
            <div className="text-[9px] font-extrabold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
              Historischer Kurspunkt
            </div>
            <div className="mt-1 text-xs font-semibold text-slate-700 dark:text-slate-200">
              {inspectedPoint ? formatChartTooltipDate(inspectedPoint, period.id) : "Keine Kursdaten"}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
              {historicalPriceLabel}
            </div>
            <div className="mt-0.5 text-base font-black text-slate-950 dark:text-white">
              {inspectedPoint ? formatPrice(inspectedPoint.price) : "—"}
            </div>
            {inspectedChangePct != null ? (
              <div className={`mt-0.5 text-[10px] font-extrabold ${inspectedChangePct >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400"}`}>
                Änderung bis zum letzten Kurspunkt {inspectedChangePct >= 0 ? "+" : ""}{inspectedChangePct.toLocaleString("de-DE", { maximumFractionDigits: 2 })}% · ohne Div.
              </div>
            ) : null}
          </div>
        </div>
        <div className="mt-2 flex items-center gap-2">
          <button
            type="button"
            onClick={() => inspectFromControls(Math.max(0, displayedIndex - 1))}
            disabled={!chartData.length || displayedIndex <= 0}
            className="min-h-9 shrink-0 rounded-lg border border-black/8 bg-white px-2.5 text-[10px] font-extrabold text-slate-600 disabled:opacity-35 dark:border-white/10 dark:bg-slate-900 dark:text-slate-200"
            aria-label="Einen Kurspunkt früher"
          >
            ← Früher
          </button>
          <input
            type="range"
            min={0}
            max={Math.max(0, chartData.length - 1)}
            step={1}
            value={displayedIndex}
            disabled={!chartData.length}
            onChange={(event) => inspectFromControls(Number(event.target.value))}
            aria-label={`Historischen Kurspunkt für ${period.label} auswählen`}
            aria-valuetext={
              inspectedPoint
                ? `${formatChartTooltipDate(inspectedPoint, period.id)}, ${formatPrice(inspectedPoint.price)}`
                : "Keine Kursdaten"
            }
            className="h-9 min-w-0 flex-1 cursor-pointer accent-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-40"
          />
          <button
            type="button"
            onClick={() => inspectFromControls(Math.min(chartData.length - 1, displayedIndex + 1))}
            disabled={!chartData.length || displayedIndex >= chartData.length - 1}
            className="min-h-9 shrink-0 rounded-lg border border-black/8 bg-white px-2.5 text-[10px] font-extrabold text-slate-600 disabled:opacity-35 dark:border-white/10 dark:bg-slate-900 dark:text-slate-200"
            aria-label="Einen Kurspunkt später"
          >
            Später →
          </button>
        </div>
        <div className="flex items-center justify-between gap-2 text-[9px] font-bold uppercase tracking-[0.12em] text-slate-400">
          <button
            type="button"
            onClick={() => inspectFromControls(0)}
            disabled={!chartData.length || displayedIndex === 0}
            className="rounded-md px-1.5 py-1 text-left transition-colors hover:bg-black/[0.04] hover:text-[var(--accent)] disabled:pointer-events-none disabled:opacity-45"
            aria-label="Zum ersten historischen Kurspunkt springen"
          >
            Start · {chartData[0] ? formatChartTooltipDate(chartData[0], period.id) : "—"}
          </button>
          <span className="hidden text-center sm:inline">Wischen, tippen oder über den Chart fahren</span>
          <button
            type="button"
            onClick={() => inspectFromControls(Math.max(0, chartData.length - 1))}
            disabled={!chartData.length || displayedIndex === chartData.length - 1}
            className="rounded-md px-1.5 py-1 text-right transition-colors hover:bg-black/[0.04] hover:text-[var(--accent)] disabled:pointer-events-none disabled:opacity-45"
            aria-label="Zum neuesten Kurspunkt springen"
          >
            Letzter Punkt · {chartData.at(-1) ? formatChartTooltipDate(chartData.at(-1)!, period.id) : "—"}
          </button>
        </div>
      </div>

      <MeasuredChartFrame
        className={`w-full ${subPanels > 0 ? "h-[430px] sm:h-[520px]" : "h-[280px] sm:h-[320px]"}`}
        minHeight={subPanels > 0 ? 430 : 280}
        fallback={
          <div className="flex h-full w-full items-center justify-center rounded-[1.4rem] border border-black/8 bg-white/70">
            <span className="text-sm text-slate-500">Chart-Layout wird vorbereitet...</span>
          </div>
        }
      >
        {(size) => {
          const totalHeight = Math.max(size.h, subPanels > 0 ? 430 : 280);
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
              Erneut laden
            </button>
          </div>
        ) : chartData.length > 0 ? (
          <div className="flex h-full w-full flex-col gap-2">
            <div style={{ height: mainHeightPx }} className="min-h-[200px]">
              <ResponsiveContainer width={size.w} height={mainHeightPx} minWidth={0} minHeight={180}>
                <AreaChart
                  data={chartData}
                  margin={{ top: 8, right: 24, bottom: 0, left: 8 }}
                  onMouseMove={inspectChartPoint}
                  onClick={inspectChartPoint}
                >
                  <defs>
                    <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={isPositive ? "var(--chart-up)" : "var(--chart-down)"} stopOpacity={0.22} />
                      <stop offset="95%" stopColor={isPositive ? "var(--chart-up)" : "var(--chart-down)"} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(22,28,36,0.08)" vertical={false} />
                  <XAxis dataKey="_chartIndex" tickFormatter={(index) => formatChartAxisDate(chartData[Number(index)], period.id)} interval="preserveStartEnd" axisLine={false} tickLine={false} tick={{ fill: "var(--chart-axis)", fontSize: 11 }} minTickGap={30} />
                  <YAxis hide domain={yDomain} />
                  {showEdgeLevels && edgeOverlay ? (
                    <>
                      {edgeOverlay.poc ? (
                        <ReferenceLine
                          y={edgeOverlay.poc}
                          stroke="#d97706"
                          strokeWidth={1.8}
                          strokeDasharray="4 4"
                          label={{ value: `POC: $${edgeOverlay.poc}`, fill: "#d97706", fontSize: 10, position: "insideRight" }}
                        />
                      ) : null}
                      {edgeOverlay.vah ? (
                        <ReferenceLine
                          y={edgeOverlay.vah}
                          stroke="#059669"
                          strokeWidth={1.2}
                          strokeDasharray="2 2"
                          label={{ value: `VAH: $${edgeOverlay.vah}`, fill: "#059669", fontSize: 9, position: "insideRight" }}
                        />
                      ) : null}
                      {edgeOverlay.val ? (
                        <ReferenceLine
                          y={edgeOverlay.val}
                          stroke="#dc2626"
                          strokeWidth={1.2}
                          strokeDasharray="2 2"
                          label={{ value: `VAL: $${edgeOverlay.val}`, fill: "#dc2626", fontSize: 9, position: "insideRight" }}
                        />
                      ) : null}
                      {edgeOverlay.call_wall ? (
                        <ReferenceLine
                          y={edgeOverlay.call_wall}
                          stroke="#7c3aed"
                          strokeWidth={1.6}
                          strokeDasharray="5 3"
                          label={{ value: `Call Wall: $${edgeOverlay.call_wall}`, fill: "#7c3aed", fontSize: 10, position: "insideRight" }}
                        />
                      ) : null}
                      {edgeOverlay.put_wall ? (
                        <ReferenceLine
                          y={edgeOverlay.put_wall}
                          stroke="#2563eb"
                          strokeWidth={1.6}
                          strokeDasharray="5 3"
                          label={{ value: `Put Wall: $${edgeOverlay.put_wall}`, fill: "#2563eb", fontSize: 10, position: "insideRight" }}
                        />
                      ) : null}
                    </>
                  ) : null}
                  {inspectedPoint ? (
                    <ReferenceLine
                      x={displayedIndex}
                      stroke="var(--chart-marker)"
                      strokeDasharray="3 3"
                    />
                  ) : null}
                  <Tooltip
                    active={tooltipSuppressed ? false : undefined}
                    trigger={touchSelection ? "click" : "hover"}
                    content={<CustomTooltip />}
                    cursor={{ stroke: "var(--chart-cursor)", strokeWidth: 1.2 }}
                    allowEscapeViewBox={{ x: false, y: true }}
                    wrapperStyle={{ zIndex: 40, pointerEvents: "none" }}
                  />
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
                  <Area
                    type="monotone"
                    dataKey="price"
                    name="Kurs"
                    stroke={isPositive ? "var(--chart-up)" : "var(--chart-down)"}
                    strokeWidth={2.4}
                    fillOpacity={1}
                    fill="url(#colorPrice)"
                    activeDot={{ r: 4.5, strokeWidth: 2, stroke: "#ffffff" }}
                    animationDuration={850}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {showVolume ? (
              <div style={{ height: subHeightPx }} className="min-h-[74px]">
                <ResponsiveContainer width={size.w} height={subHeightPx} minWidth={0} minHeight={74}>
                  <BarChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(22,28,36,0.06)" vertical={false} />
                    <XAxis dataKey="_chartIndex" hide />
                    <YAxis hide />
                    <Bar dataKey="_volume" animationDuration={550}>
                      {chartData.map((entry, idx) => (
                        <Cell key={`vol-${idx}`} fill={(entry._macd ?? 0) >= 0 ? "#2563eb" : "#64748b"} fillOpacity={0.6} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <div
                  className="px-2 text-[9px] font-bold uppercase tracking-wider text-slate-400"
                  title={INDICATOR_HELP.Volume}
                >
                  Volumen / Hover: Aktivität / Bestätigung
                </div>
              </div>
            ) : null}

            {showRSI ? (
              <div style={{ height: subHeightPx }} className="min-h-[74px]">
                <ResponsiveContainer width={size.w} height={subHeightPx} minWidth={0} minHeight={74}>
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(22,28,36,0.06)" vertical={false} />
                    <XAxis dataKey="_chartIndex" hide />
                    <YAxis domain={[0, 100]} hide />
                    <ReferenceLine y={70} stroke="#dc2626" strokeDasharray="4 4" strokeOpacity={0.5} />
                    <ReferenceLine y={30} stroke="#0f766e" strokeDasharray="4 4" strokeOpacity={0.5} />
                    <Line type="monotone" dataKey="_rsi" stroke="#d97706" strokeWidth={1.5} dot={false} animationDuration={600} />
                  </LineChart>
                </ResponsiveContainer>
                <div
                  className="flex justify-between px-2 text-[9px] font-bold uppercase tracking-wider text-slate-400"
                  title={INDICATOR_HELP.RSI}
                >
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
                    <XAxis dataKey="_chartIndex" hide />
                    <YAxis hide />
                    <ReferenceLine y={0} stroke="rgba(22,28,36,0.15)" />
                    <Bar dataKey="_macd" animationDuration={600}>
                      {chartData.map((entry, idx) => (
                        <Cell key={`macd-${idx}`} fill={(entry._macd ?? 0) >= 0 ? "#0f766e" : "#dc2626"} fillOpacity={0.7} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <div
                  className="px-2 text-[9px] font-bold uppercase tracking-wider text-slate-400"
                  title={INDICATOR_HELP.MACD}
                >
                  MACD Histogram (12/26/9) / Momentum
                </div>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center rounded-[1.4rem] border border-dashed border-black/8 bg-white/70 text-slate-500">
            <Calendar size={32} className="mb-2 opacity-30" />
            <p className="text-sm">Keine historischen Daten für diesen Zeitraum.</p>
          </div>
        );
        }}
      </MeasuredChartFrame>

      {discardedPoints > 0 && data.length > 0 ? (
        <p role="status" className="mt-3 text-xs text-slate-600">
          {discardedPoints} ungültige Kurspunkte ausgelassen. Die Linie verbindet die verbleibenden, unveränderten Kurspunkte.
        </p>
      ) : null}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
        <div className="flex items-center gap-1">
          <Clock size={10} />
          {({ "5m": "5-Minuten-Kurse", "15m": "15-Minuten-Kurse", "1d": "Tageskurse", "1wk": "Wochenkurse", "1mo": "Monatskurse" } as Record<string, string>)[period.interval]}
        </div>
        <div>
          Quelle: {displayMetaValue(historyMeta?.source, "nicht angegeben")}
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
          Datenstatus: {dataStatusLabel(historyState, feedStatus)}.
          {" "}Chart: {HISTORY_STATUS_LABELS[historyState]} / Feed: {feedStatus}
          {typeof staleForTicker === "number" && staleForTicker > 5 ? ` / verzögert ${staleForTicker}s` : ""}
          {realtimeFallbackNote ? ` / ${realtimeFallbackNote}` : ""}
          {displayedRealtimeError ? ` / ${friendlyRealtimeError(displayedRealtimeError)}` : ""}
        </div>
      ) : null}
      {historyMeta ? (
        <div className="chart-history-meta mt-2 rounded-[0.9rem] border border-black/8 bg-white/70 px-3 py-2 text-[11px] font-semibold text-slate-500">
          Historie: {displayMetaValue(historyMeta.source)} / {displayMetaValue(historyMeta.period)}/{displayMetaValue(historyMeta.interval)}
          {historyMeta.requested_period && historyMeta.requested_period !== historyMeta.period
            ? ` / angefragt ${historyMeta.requested_period}/${displayMetaValue(historyMeta.requested_interval)}`
            : ""}
          {` / ${data.length} Punkte`}
          {historyMeta.fallback_reason ? ` / ${friendlyHistoryReason(historyMeta.fallback_reason)}` : ""}
        </div>
      ) : null}
    </div>
  );
}
