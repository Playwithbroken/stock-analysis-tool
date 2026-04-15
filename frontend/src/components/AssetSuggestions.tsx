import React, { useEffect, useState } from "react";
import { ArrowRight, Sparkles } from "lucide-react";

interface Suggestion {
  ticker: string;
  name: string;
  reason: string;
}

interface AssetSuggestionsProps {
  portfolioId: string;
  onAdd: (ticker: string) => void;
}

export default function AssetSuggestions({
  portfolioId,
  onAdd,
}: AssetSuggestionsProps) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchSuggestions = async () => {
      setLoading(true);
      try {
        const res = await fetch(`/api/portfolio/${portfolioId}/suggestions`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        setSuggestions(Array.isArray(json) ? json : []);
      } catch {
        setSuggestions([]);
      } finally {
        setLoading(false);
      }
    };
    if (portfolioId) fetchSuggestions();
  }, [portfolioId]);

  if (loading || suggestions.length === 0) return null;

  return (
    <div className="surface-panel rounded-2xl p-6">
      <h3 className="mb-4 flex items-center gap-2 text-sm font-bold uppercase tracking-widest text-[var(--accent)]">
        <Sparkles size={16} className="animate-pulse" />
        Strategische Portfolio-Ergaenzungen
      </h3>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {suggestions.map((item) => (
          <div
            key={item.ticker}
            className="group cursor-pointer rounded-xl border border-black/8 bg-white/75 p-4 transition-all hover:border-[var(--accent)]/25 hover:bg-white"
            onClick={() => onAdd(item.ticker)}
          >
            <div className="mb-2 flex items-start justify-between">
              <div>
                <div className="text-lg font-bold text-slate-900 transition-colors group-hover:text-[var(--accent)]">
                  {item.ticker}
                </div>
                <div className="max-w-[120px] truncate text-[10px] text-slate-500">
                  {item.name}
                </div>
              </div>
              <div className="rounded bg-[var(--accent-soft)] px-2 py-1 text-[10px] font-bold uppercase text-[var(--accent)]">
                Diversify
              </div>
            </div>
            <div className="mt-3 flex items-center justify-between text-[11px]">
              <span className="font-medium text-slate-600">{item.reason}</span>
              <ArrowRight
                size={14}
                className="text-slate-500 transition-all group-hover:translate-x-1 group-hover:text-[var(--accent)]"
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
