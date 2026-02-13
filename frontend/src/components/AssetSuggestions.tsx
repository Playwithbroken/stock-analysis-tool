import React, { useState, useEffect } from "react";
import { Sparkles, ArrowRight, Layers } from "lucide-react";

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
        const json = await res.json();
        setSuggestions(json);
      } catch (e) {
        console.error("Failed to fetch suggestions", e);
      } finally {
        setLoading(false);
      }
    };
    if (portfolioId) fetchSuggestions();
  }, [portfolioId]);

  if (loading || suggestions.length === 0) return null;

  return (
    <div className="bg-linear-to-r from-purple-900/20 to-black rounded-2xl p-6 border border-purple-500/20 shadow-lg shadow-purple-500/5">
      <h3 className="text-sm font-bold text-purple-300 uppercase tracking-widest mb-4 flex items-center gap-2">
        <Sparkles size={16} className="animate-pulse" />
        Strategische Portfolio-Ergänzungen
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {suggestions.map((item) => (
          <div
            key={item.ticker}
            className="group p-4 bg-white/5 rounded-xl border border-white/5 hover:border-purple-500/40 transition-all cursor-pointer"
            onClick={() => onAdd(item.ticker)}
          >
            <div className="flex justify-between items-start mb-2">
              <div>
                <div className="text-lg font-bold text-white group-hover:text-purple-400 transition-colors">
                  {item.ticker}
                </div>
                <div className="text-[10px] text-gray-500 truncate max-w-[120px]">
                  {item.name}
                </div>
              </div>
              <div className="p-1 px-2 bg-purple-500/10 rounded text-[10px] text-purple-400 font-bold uppercase">
                Diversify
              </div>
            </div>
            <div className="flex items-center justify-between mt-3 text-[11px]">
              <span className="text-gray-400 font-medium">{item.reason}</span>
              <ArrowRight
                size={14}
                className="text-gray-600 group-hover:text-purple-500 group-hover:translate-x-1 transition-all"
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
