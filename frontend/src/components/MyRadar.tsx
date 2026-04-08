import React, { useEffect, useMemo, useState } from "react";
import MorningBriefPanel from "./MorningBriefPanel";
import PaperTradingPanel from "./PaperTradingPanel";
import SignalScoreboardPanel from "./SignalScoreboardPanel";
import SessionListsPanel from "./SessionListsPanel";
import TradingIntelligencePanel from "./TradingIntelligencePanel";

interface MyRadarProps {
  onAnalyze: (ticker: string) => void;
  onOpenSignals: () => void;
}

interface WatchlistSnapshot {
  items: Array<{ kind: string; value: string }>;
  ticker_signals: any[];
  politician_signals: any[];
}

interface SignalHistoryItem {
  event_key: string;
  category: string;
  title: string;
  sent_at: string;
}

export default function MyRadar({ onAnalyze, onOpenSignals }: MyRadarProps) {
  const [watchlist, setWatchlist] = useState<WatchlistSnapshot | null>(null);
  const [history, setHistory] = useState<SignalHistoryItem[]>([]);
  const [brief, setBrief] = useState<any>(null);
  const [scoreboard, setScoreboard] = useState<any>(null);
  const [sessionLists, setSessionLists] = useState<any>(null);
  const [paperDashboard, setPaperDashboard] = useState<any>(null);
  const [tradingIntelligence, setTradingIntelligence] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [watchRes, historyRes, briefRes, scoreRes, sessionRes, paperRes, intelRes] = await Promise.all([
        fetch("/api/signals/watchlist").then((r) => r.json()),
        fetch("/api/signals/history?limit=8").then((r) => r.json()),
        fetch("/api/market/morning-brief").then((r) => r.json()),
        fetch("/api/signals/scoreboard").then((r) => r.json()),
        fetch("/api/market/session-lists").then((r) => r.json()),
        fetch("/api/trading/paper-dashboard").then((r) => r.json()),
        fetch("/api/trading/intelligence").then((r) => r.json()),
      ]);
      setWatchlist(watchRes);
      setHistory(historyRes);
      setBrief(briefRes);
      setScoreboard(scoreRes);
      setSessionLists(sessionRes);
      setPaperDashboard(paperRes);
      setTradingIntelligence(intelRes);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const summary = useMemo(() => {
    const tickerEvents =
      watchlist?.ticker_signals?.reduce(
        (sum: number, item: any) => sum + (item.events?.length || 0),
        0,
      ) || 0;
    const politicianEvents =
      watchlist?.politician_signals?.reduce(
        (sum: number, item: any) => sum + (item.trades?.length || 0),
        0,
      ) || 0;
    return {
      watchItems: watchlist?.items?.length || 0,
      tickerEvents,
      politicianEvents,
    };
  }, [watchlist]);

  const topTicker = watchlist?.ticker_signals?.find((item: any) => item.events?.length);
  const topPolitical = watchlist?.politician_signals?.find((item: any) => item.trades?.length);

  if (loading) {
    return <div className="surface-panel h-64 animate-pulse rounded-[2.5rem]" />;
  }

  return (
    <div className="space-y-6">
      <MorningBriefPanel brief={brief} onAnalyze={onAnalyze} />

      <section className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="surface-panel rounded-[2.5rem] p-6 sm:p-8">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-[var(--accent-soft)] px-3 py-1 text-[11px] font-extrabold uppercase tracking-[0.22em] text-[var(--accent)]">
              My Radar
            </span>
            <span className="rounded-full border border-black/8 bg-white/70 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
              Watchlist first
            </span>
          </div>

          <h1 className="mt-5 max-w-3xl text-5xl leading-none text-balance text-slate-900 sm:text-6xl">
            Your personal market terminal, centered on signals that matter.
          </h1>
          <p className="mt-5 max-w-2xl text-base leading-7 text-slate-600 sm:text-lg">
            Statt generischer Discovery startet die App jetzt bei deiner Watchlist: Insider, Congress-Filings,
            Berkshire-Signale, Morning Brief und persönlicher Alert-History.
          </p>

          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            <div className="rounded-[1.7rem] border border-black/8 bg-white/75 p-5">
              <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">Watchlist</div>
              <div className="mt-2 text-3xl font-black text-slate-900">{summary.watchItems}</div>
            </div>
            <div className="rounded-[1.7rem] border border-black/8 bg-white/75 p-5">
              <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">Insider events</div>
              <div className="mt-2 text-3xl font-black text-slate-900">{summary.tickerEvents}</div>
            </div>
            <div className="rounded-[1.7rem] border border-black/8 bg-white/75 p-5">
              <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">Congress trades</div>
              <div className="mt-2 text-3xl font-black text-slate-900">{summary.politicianEvents}</div>
            </div>
          </div>

          <div className="mt-8 flex flex-wrap gap-3">
            <button
              onClick={onOpenSignals}
              className="rounded-[1.2rem] bg-[var(--accent)] px-5 py-3 text-xs font-extrabold uppercase tracking-[0.18em] text-white transition-colors hover:bg-[var(--accent-strong)]"
            >
              Open Signals
            </button>
            {topTicker?.ticker && (
              <button
                onClick={() => onAnalyze(topTicker.ticker)}
                className="rounded-[1.2rem] border border-black/8 bg-white px-5 py-3 text-xs font-extrabold uppercase tracking-[0.18em] text-slate-700"
              >
                Analyze {topTicker.ticker}
              </button>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-[2.5rem] border border-[var(--accent)]/12 bg-[linear-gradient(180deg,rgba(15,118,110,0.08),rgba(255,255,255,0.88))] p-6 sm:p-8">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">Daily Brief</div>
            <div className="mt-4 space-y-3">
              <div className="rounded-[1.4rem] border border-black/8 bg-white/78 p-4 text-sm text-slate-700">
                {topTicker?.events?.[0]
                  ? `${topTicker.ticker}: ${topTicker.events[0].action} by ${topTicker.events[0].owner_name} on ${topTicker.events[0].trade_date}`
                  : "Noch keine Insider-Signale in deiner Watchlist."}
              </div>
              <div className="rounded-[1.4rem] border border-black/8 bg-white/78 p-4 text-sm text-slate-700">
                {topPolitical?.trades?.[0]
                  ? `${topPolitical.name}: ${topPolitical.trades[0].action} ${topPolitical.trades[0].ticker || topPolitical.trades[0].asset} on ${topPolitical.trades[0].trade_date}`
                  : "Noch keine Congress-Signale in deiner Watchlist."}
              </div>
            </div>
          </div>

          <div className="surface-panel rounded-[2rem] p-6">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">Alert History</div>
            <div className="mt-4 space-y-3">
              {history.length ? (
                history.map((item) => (
                  <div key={item.event_key} className="rounded-[1.2rem] border border-black/8 bg-white/75 p-4">
                    <div className="text-sm font-bold text-slate-900">{item.title}</div>
                    <div className="mt-1 text-xs text-slate-500">
                      {item.category} · {new Date(item.sent_at).toLocaleString()}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-sm text-slate-500">Noch keine gesendeten Alert-History-Einträge.</div>
              )}
            </div>
          </div>
        </div>
      </section>

      <SignalScoreboardPanel data={scoreboard} onAnalyze={onAnalyze} onRefresh={fetchData} />
      <TradingIntelligencePanel data={tradingIntelligence} onAnalyze={onAnalyze} />
      <PaperTradingPanel data={paperDashboard} onAnalyze={onAnalyze} onRefresh={fetchData} />
      <SessionListsPanel data={sessionLists} onAnalyze={onAnalyze} />
    </div>
  );
}
