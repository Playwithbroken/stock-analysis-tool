import { useState, FormEvent, useEffect, useRef } from "react";
import {
  Search,
  ChevronDown,
  Rocket,
  TrendingUp,
  Globe,
  Coins,
} from "lucide-react";

interface SearchBarProps {
  onSearch: (ticker: string) => void;
  loading: boolean;
}

export default function SearchBar({ onSearch, loading }: SearchBarProps) {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Record<string, string[]>>({});
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const debounceTimer = useRef<any>(null);

  useEffect(() => {
    // Initial fetch for categories
    fetch("/api/search/suggestions")
      .then((res) => res.json())
      .then((data) => setSuggestions(data))
      .catch((err) => console.error("Suggestions fetch error:", err));
  }, []);

  useEffect(() => {
    const trimmedQuery = query.trim();
    if (trimmedQuery.length > 1) {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
      debounceTimer.current = setTimeout(() => {
        fetch(`/api/search/suggestions?q=${encodeURIComponent(trimmedQuery)}`)
          .then((res) => res.json())
          .then((data) => {
            // Merge or replace suggestions based on response format
            if (data.Matches && data.Matches.length > 0) {
              setSuggestions({ "Top Matches": data.Matches });
            } else if (trimmedQuery.length > 0) {
              setSuggestions({});
            }
          })
          .catch((err) => console.error("Search suggestions error:", err));
      }, 300);
    } else if (trimmedQuery.length === 0) {
      // Revert to defaults
      fetch("/api/search/suggestions")
        .then((res) => res.json())
        .then((data) => setSuggestions(data))
        .catch((err) => console.error("Suggestions fetch error:", err));
    }
  }, [query]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      onSearch(query.trim().toUpperCase());
    }
  };

  return (
    <form onSubmit={handleSubmit} className="max-w-2xl mx-auto">
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setShowDropdown(true)}
          placeholder="Ticker eingeben (z.B. AAPL, BTC-USD, GC=F)"
          className="w-full px-6 py-4 bg-[#050507] border border-white/10 rounded-2xl text-white placeholder-gray-600 focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 transition-all text-lg shadow-inner"
          disabled={loading}
        />

        {showDropdown && Object.keys(suggestions).length > 0 && (
          <div
            ref={dropdownRef}
            className="absolute top-full left-0 right-0 mt-2 bg-[#050507] border border-white/10 rounded-2xl shadow-2xl z-50 overflow-hidden backdrop-blur-xl bg-opacity-95"
          >
            <div className="p-2 grid grid-cols-2 gap-1">
              {Object.entries(suggestions).map(([category, tickers]) => (
                <div key={category} className="p-3">
                  <h4 className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-gray-500 mb-2 px-2">
                    {category === "Trending" && (
                      <TrendingUp size={12} className="text-green-400" />
                    )}
                    {category === "Moonshots" && (
                      <Rocket size={12} className="text-purple-400" />
                    )}
                    {category === "Rohstoffe" && (
                      <Globe size={12} className="text-yellow-400" />
                    )}
                    {category === "Crypto" && (
                      <Coins size={12} className="text-blue-400" />
                    )}
                    {category === "Sektoren" && (
                      <ChevronDown
                        size={12}
                        className="text-pink-400 rotate-180"
                      />
                    )}
                    {category === "Regionen" && (
                      <Globe size={12} className="text-yellow-400" />
                    )}
                    {category}
                  </h4>
                  <div className="flex flex-wrap gap-1">
                    {Array.isArray(tickers) &&
                      tickers.map((ticker) => (
                        <button
                          key={ticker}
                          type="button"
                          onClick={() => {
                            let tickerToSearch = ticker;
                            if (ticker.includes("(") && ticker.includes(")")) {
                              const match = ticker.match(/\((.*?)\)/);
                              if (match) tickerToSearch = match[1];
                            }
                            onSearch(tickerToSearch);
                            setQuery(tickerToSearch);
                            setShowDropdown(false);
                          }}
                          className="px-3 py-1.5 bg-white/5 hover:bg-purple-600/20 hover:text-purple-300 rounded-lg text-xs font-bold transition-all border border-white/5 hover:border-purple-500/30 text-gray-400"
                        >
                          {ticker}
                        </button>
                      ))}
                  </div>
                </div>
              ))}
            </div>
            <div className="bg-white/5 p-3 border-t border-white/5 flex justify-between items-center">
              <span className="text-[10px] text-gray-500 font-medium">
                ✨ Profi-Tipp: Nutze Gold (GC=F) oder Bitcoin (BTC-USD)
              </span>
              <button
                type="button"
                onClick={() => setShowDropdown(false)}
                className="text-[10px] text-purple-400 font-bold hover:underline"
              >
                Schließen
              </button>
            </div>
          </div>
        )}
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="absolute right-2 top-1/2 -translate-y-1/2 px-6 py-2.5 bg-linear-to-r from-purple-500 to-indigo-600 text-white rounded-xl font-medium hover:from-purple-600 hover:to-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
        >
          {loading ? (
            <svg
              className="w-5 h-5 animate-spin"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              ></circle>
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              ></path>
            </svg>
          ) : (
            "Analyze"
          )}
        </button>
      </div>
    </form>
  );
}
