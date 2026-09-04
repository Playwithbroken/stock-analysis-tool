import { useCallback, useEffect, useState } from "react";
import { fetchJsonWithRetry } from "../lib/api";

type MoversStatus = "loading" | "ready" | "empty" | "error" | "stale";
type MoversPayload = { gainers: any[]; losers: any[] };

export default function useMarketMovers<T>(
  selectedWindow: "1d" | "1w" | "1m",
  enabled: boolean,
  normalize: (payload: MoversPayload) => T[],
) {
  const [result, setResult] = useState<{ window: string; items: T[]; status: MoversStatus }>({
    window: selectedWindow, items: [], status: "loading",
  });
  const [retryCount, setRetryCount] = useState(0);
  const retry = useCallback(() => setRetryCount(count => count + 1), []);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    let pending = false;
    const load = async () => {
      if (pending) return;
      pending = true;
      setResult(current => ({
        window: selectedWindow,
        items: current.window === selectedWindow ? current.items : [],
        status: "loading",
      }));
      try {
        const [gainers, losers] = await Promise.all(["gainers", "losers"].map(side =>
          fetchJsonWithRetry<any[]>(`/api/discovery/${side}?window=${selectedWindow}`,
            { signal: controller.signal }, { retries: 0, retryDelayMs: 250, timeoutMs: 4500 }),
        ));
        if (controller.signal.aborted) return;
        if (!Array.isArray(gainers) || !Array.isArray(losers)) throw new Error("Invalid movers response");
        const items = normalize({ gainers, losers });
        setResult({ window: selectedWindow, items, status: items.length ? "ready" : "empty" });
      } catch {
        if (controller.signal.aborted) return;
        setResult(current => {
          const items = current.window === selectedWindow ? current.items : [];
          return { window: selectedWindow, items, status: items.length ? "stale" : "error" };
        });
      } finally {
        pending = false;
      }
    };
    void load();
    const timer = window.setInterval(load, 60000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [selectedWindow, enabled, normalize, retryCount]);

  // Hide a previous window synchronously, before effects start the next request.
  const matches = enabled && result.window === selectedWindow;
  return { items: matches ? result.items : [], status: matches ? result.status : "loading" as MoversStatus, retry };
}
