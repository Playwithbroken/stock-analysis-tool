import { useEffect, useMemo, useRef, useState } from "react";

interface RealtimeQuote {
  symbol: string;
  price: number;
  change_1w?: number | null;
  change_1m?: number | null;
  volume_ratio?: number | null;
  asset_class?: string;
  currency?: string;
  headline?: string | null;
  publisher?: string | null;
  updated_at?: string;
}

interface RealtimePayload {
  type: string;
  generated_at: string;
  connection_state?: "live" | "degraded" | "snapshot";
  stale_seconds?: Record<string, number>;
  quotes: RealtimeQuote[];
}

const WS_UNAVAILABLE_UNTIL_KEY = "brokerfreund:ws-unavailable-until";
const WS_FAILURE_THRESHOLD = 1;
const WS_SUSPEND_MS = 6 * 60 * 60 * 1000; // 6h
let globalWsFailures = 0;
let globalWsUnavailable = false;

function buildRealtimeUrl(symbols: string[]) {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const params = new URLSearchParams({ symbols: symbols.join(",") });
  return `${protocol}://${window.location.host}/ws/realtime?${params.toString()}`;
}

function shouldPreferSnapshotOnly() {
  const host = (window.location.hostname || "").toLowerCase();
  const forceWs = (() => {
    try {
      return localStorage.getItem("brokerfreund:force-ws") === "1";
    } catch {
      return false;
    }
  })();
  if (forceWs) return false;
  return host.endsWith("railway.app");
}

export default function useRealtimeFeed(symbols: string[], enabled = true) {
  const symbolKey = useMemo(() => symbols.map((item) => item.trim().toUpperCase()).filter(Boolean).join(","), [symbols]);
  const cleaned = useMemo(
    () => Array.from(new Set(symbols.map((item) => item.trim().toUpperCase()).filter(Boolean))).slice(0, 18),
    [symbolKey],
  );
  const [quotes, setQuotes] = useState<Record<string, RealtimeQuote>>({});
  const [connected, setConnected] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [connectionState, setConnectionState] = useState<"live" | "degraded" | "snapshot">("snapshot");
  const [staleSeconds, setStaleSeconds] = useState<Record<string, number>>({});
  const [transportMode, setTransportMode] = useState<"ws" | "snapshot">("snapshot");
  const [lastError, setLastError] = useState<string | null>(null);
  const lastFrameRef = useRef<number>(0);
  const reconnectAttemptRef = useRef<number>(0);
  const wsDisabledRef = useRef<boolean>(false);

  const clearWsUnavailable = () => {
    try {
      localStorage.removeItem(WS_UNAVAILABLE_UNTIL_KEY);
      globalWsUnavailable = false;
    } catch {
      // ignore storage errors
    }
  };

  const markWsUnavailable = () => {
    try {
      localStorage.setItem(WS_UNAVAILABLE_UNTIL_KEY, String(Date.now() + WS_SUSPEND_MS));
      globalWsUnavailable = true;
    } catch {
      // ignore storage errors
    }
  };

  const isWsUnavailable = () => {
    try {
      const raw = localStorage.getItem(WS_UNAVAILABLE_UNTIL_KEY);
      if (!raw) return false;
      const until = Number(raw);
      return Number.isFinite(until) && until > Date.now();
    } catch {
      return false;
    }
  };

  useEffect(() => {
    if (!enabled || cleaned.length === 0) return;

    let socket: WebSocket | null = null;
    let retry: number | null = null;
    let staleTimer: number | null = null;
    let pollTimer: number | null = null;
    let closed = false;

    setQuotes({});
    setLastUpdated(null);
    setConnected(false);
    setConnectionState("snapshot");
    setStaleSeconds({});
    setTransportMode("snapshot");
    setLastError(null);
    lastFrameRef.current = 0;
    reconnectAttemptRef.current = 0;
    wsDisabledRef.current = globalWsUnavailable || isWsUnavailable() || shouldPreferSnapshotOnly();

    const allowedSymbols = new Set(cleaned);

    const mergeQuotes = (incoming: RealtimeQuote[]) => {
      setQuotes((prev) => {
        const next: Record<string, RealtimeQuote> = {};
        for (const symbol of allowedSymbols) {
          if (prev[symbol]) {
            next[symbol] = prev[symbol];
          }
        }
        for (const quote of incoming || []) {
          if (quote?.symbol && allowedSymbols.has(quote.symbol)) {
            next[quote.symbol] = quote;
          }
        }
        return next;
      });
    };

    const scheduleStaleCheck = () => {
      if (staleTimer) window.clearTimeout(staleTimer);
      staleTimer = window.setTimeout(() => {
        const now = Date.now();
        if (lastFrameRef.current && now - lastFrameRef.current > 14000) {
          setConnected(false);
        }
      }, 15000);
    };

    const fetchSnapshot = async () => {
      if (closed || cleaned.length === 0) return;
      try {
        const response = await fetch(`/api/realtime/snapshot?symbols=${encodeURIComponent(cleaned.join(","))}`);
        if (!response.ok) {
          setLastError(`snapshot_http_${response.status}`);
          return;
        }
        const payload = (await response.json()) as RealtimePayload;
        mergeQuotes(payload.quotes || []);
        setLastUpdated(payload.generated_at);
        setConnectionState(payload.connection_state || "snapshot");
        setStaleSeconds(payload.stale_seconds || {});
        setTransportMode("snapshot");
        if ((payload.quotes || []).length > 0) {
          setConnected(true);
        }
      } catch {
        setLastError("snapshot_fetch_failed");
      }
    };

    const getBackoffDelayMs = (attempt: number) => {
      const schedule = [3000, 6000, 12000, 30000, 60000];
      const base = schedule[Math.min(attempt, schedule.length - 1)];
      const jitter = Math.floor(Math.random() * 700);
      return Math.min(60000, base + jitter);
    };

    const scheduleReconnect = () => {
      if (closed || retry != null || wsDisabledRef.current) return;
      const attempt = reconnectAttemptRef.current;
      if (attempt >= 4) {
        wsDisabledRef.current = true;
        markWsUnavailable();
        setTransportMode("snapshot");
        setConnectionState("snapshot");
        return;
      }
      const waitMs = getBackoffDelayMs(attempt);
      reconnectAttemptRef.current = attempt + 1;
      retry = window.setTimeout(() => {
        retry = null;
        connect();
      }, waitMs);
    };

    const connect = () => {
      if (wsDisabledRef.current) return;
      socket = new WebSocket(buildRealtimeUrl(cleaned));
      socket.onopen = () => {
        reconnectAttemptRef.current = 0;
        globalWsFailures = 0;
        clearWsUnavailable();
        wsDisabledRef.current = false;
        setLastError(null);
        setTransportMode("ws");
        scheduleStaleCheck();
      };
      socket.onclose = (event) => {
        setConnected(false);
        setTransportMode("snapshot");
        // Auth/permission/configuration close codes should switch to snapshot mode
        // instead of retrying websocket forever.
        if (event.code === 1008 || event.code === 1011) {
          wsDisabledRef.current = true;
          markWsUnavailable();
          setConnectionState("snapshot");
          setLastError(`ws_closed_${event.code}`);
          return;
        }
        if (event.code === 1005 || event.code === 1006 || event.code === 1015) {
          globalWsFailures += 1;
          if (globalWsFailures >= WS_FAILURE_THRESHOLD) {
            wsDisabledRef.current = true;
            markWsUnavailable();
            setConnectionState("snapshot");
            setLastError(`ws_closed_${event.code}`);
            return;
          }
        }
        setLastError(`ws_closed_${event.code || 0}`);
        scheduleReconnect();
      };
      socket.onerror = () => {
        setConnected(false);
        setLastError("ws_error");
        if (globalWsFailures >= WS_FAILURE_THRESHOLD - 1) {
          wsDisabledRef.current = true;
          markWsUnavailable();
          setConnectionState("snapshot");
          socket?.close();
        }
      };
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as RealtimePayload;
          lastFrameRef.current = Date.now();
          setConnected(true);
          setTransportMode("ws");
          mergeQuotes(payload.quotes || []);
          setLastUpdated(payload.generated_at);
          setConnectionState(payload.connection_state || "live");
          setStaleSeconds(payload.stale_seconds || {});
          scheduleStaleCheck();
        } catch {
          // ignore malformed frames
        }
      };
    };

    if (!wsDisabledRef.current) connect();
    fetchSnapshot();
    pollTimer = window.setInterval(() => {
      const stale = !lastFrameRef.current || Date.now() - lastFrameRef.current > 12000;
      if (stale) {
        fetchSnapshot();
      }
    }, 10000);

    return () => {
      closed = true;
      setConnected(false);
      setTransportMode("snapshot");
      if (retry) window.clearTimeout(retry);
      if (staleTimer) window.clearTimeout(staleTimer);
      if (pollTimer) window.clearInterval(pollTimer);
      socket?.close();
    };
  }, [symbolKey, enabled]);

  return { quotes, connected, lastUpdated, connectionState, staleSeconds, transportMode, lastError };
}
