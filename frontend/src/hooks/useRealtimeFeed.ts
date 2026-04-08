import { useEffect, useMemo, useState } from "react";

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
  quotes: RealtimeQuote[];
}

function buildRealtimeUrl(symbols: string[]) {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const params = new URLSearchParams({ symbols: symbols.join(",") });
  return `${protocol}://${window.location.host}/ws/realtime?${params.toString()}`;
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

  useEffect(() => {
    if (!enabled || cleaned.length === 0) return;

    let socket: WebSocket | null = null;
    let retry: number | null = null;
    let closed = false;

    const connect = () => {
      socket = new WebSocket(buildRealtimeUrl(cleaned));
      socket.onopen = () => setConnected(true);
      socket.onclose = () => {
        setConnected(false);
        if (!closed) {
          retry = window.setTimeout(connect, 3000);
        }
      };
      socket.onerror = () => setConnected(false);
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as RealtimePayload;
          const next: Record<string, RealtimeQuote> = {};
          for (const quote of payload.quotes || []) {
            next[quote.symbol] = quote;
          }
          setQuotes(next);
          setLastUpdated(payload.generated_at);
        } catch {
          // ignore malformed frames
        }
      };
    };

    connect();

    return () => {
      closed = true;
      setConnected(false);
      if (retry) window.clearTimeout(retry);
      socket?.close();
    };
  }, [symbolKey, enabled]);

  return { quotes, connected, lastUpdated };
}
