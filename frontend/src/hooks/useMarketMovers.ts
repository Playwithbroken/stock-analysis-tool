import { useCallback, useEffect, useState } from "react";
import { fetchJsonWithRetry } from "../lib/api";

type MoversStatus = "loading" | "ready" | "empty" | "error" | "stale";
type MoversPayload = { gainers: any[]; losers: any[] };

const MOVERS_CACHE = new Map<string, { items: any[]; savedAt: number }>();

export default function useMarketMovers<T>(
  selectedWindow: "1d" | "1w" | "1m",
  enabled: boolean,
  normalize: (payload: MoversPayload) => T[],
) {
  const cached = MOVERS_CACHE.get(selectedWindow);
  const [result, setResult] = useState<{ window: string; items: T[]; status: MoversStatus }>({
    window: selectedWindow,
    items: (cached?.items as T[]) || [],
    status: cached ? "ready" : "loading",
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

      // Show existing cached items immediately while background revalidation runs
      const existing = MOVERS_CACHE.get(selectedWindow);
      if (existing && existing.items.length > 0) {
        setResult({
          window: selectedWindow,
          items: existing.items as T[],
          status: "ready",
        });
      } else {
        setResult({
          window: selectedWindow,
          items: [],
          status: "loading",
        });
      }

      try {
        const [gainers, losers] = await Promise.all(["gainers", "losers"].map(side =>
          fetchJsonWithRetry<any[]>(`/api/discovery/${side}?window=${selectedWindow}`,
            { signal: controller.signal },
            { retries: 2, retryDelayMs: 600, timeoutMs: 12000 }
          ),
        ));
        if (controller.signal.aborted) return;
        const gList = Array.isArray(gainers) ? gainers : [];
        const lList = Array.isArray(losers) ? losers : [];
        const items = normalize({ gainers: gList, losers: lList });

        if (items.length > 0) {
          MOVERS_CACHE.set(selectedWindow, { items, savedAt: Date.now() });
          setResult({ window: selectedWindow, items, status: "ready" });
        } else {
          const fallback = MOVERS_CACHE.get(selectedWindow);
          if (fallback && fallback.items.length > 0) {
            setResult({ window: selectedWindow, items: fallback.items as T[], status: "ready" });
          } else {
            setResult({ window: selectedWindow, items: [], status: "empty" });
          }
        }
      } catch {
        if (controller.signal.aborted) return;
        const fallback = MOVERS_CACHE.get(selectedWindow);
        if (fallback && fallback.items.length > 0) {
          setResult({ window: selectedWindow, items: fallback.items as T[], status: "ready" });
        } else {
          setResult(current => {
            const items = current.window === selectedWindow ? current.items : [];
            return { window: selectedWindow, items, status: items.length ? "stale" : "error" };
          });
        }
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

  const matches = enabled && result.window === selectedWindow;
  return {
    items: matches ? result.items : ((MOVERS_CACHE.get(selectedWindow)?.items as T[]) || []),
    status: matches ? result.status : (MOVERS_CACHE.has(selectedWindow) ? "ready" : ("loading" as MoversStatus)),
    retry,
  };
}
