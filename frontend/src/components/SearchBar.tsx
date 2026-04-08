import { useState, FormEvent, useEffect, useRef } from "react";
import { Search, ArrowUpRight } from "lucide-react";

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
            if (data.Matches && data.Matches.length > 0) {
              setSuggestions({ Treffer: data.Matches });
            } else if (trimmedQuery.length > 0) {
              setSuggestions({});
            }
          })
          .catch((err) => console.error("Search suggestions error:", err));
      }, 240);
    } else if (trimmedQuery.length === 0) {
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
      setShowDropdown(false);
    }
  };

  const handleQuickSelect = (value: string) => {
    let tickerToSearch = value;
    if (value.includes("(") && value.includes(")")) {
      const match = value.match(/\((.*?)\)/);
      if (match) tickerToSearch = match[1];
    }
    setQuery(tickerToSearch);
    onSearch(tickerToSearch);
    setShowDropdown(false);
  };

  return (
    <form onSubmit={handleSubmit} className="mx-auto max-w-3xl">
      <div className="surface-panel relative overflow-hidden rounded-[2rem] p-3">
        <div className="absolute inset-x-6 top-0 h-px bg-linear-to-r from-transparent via-black/10 to-transparent" />

        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <div className="flex flex-1 items-center gap-4 rounded-[1.5rem] bg-white/70 px-5 py-4 ring-1 ring-black/5">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-[var(--accent)]">
              <Search size={18} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[11px] font-extrabold uppercase tracking-[0.24em] text-slate-500">
                Global Search
              </div>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onFocus={() => setShowDropdown(true)}
                placeholder="AAPL, NVDA, ASML, BTC-USD"
                className="mt-1 w-full border-0 bg-transparent p-0 text-lg font-semibold text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-0"
                disabled={loading}
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="flex h-[60px] min-w-[160px] items-center justify-center gap-2 rounded-[1.4rem] bg-[var(--accent)] px-6 text-sm font-extrabold uppercase tracking-[0.18em] text-white transition-all hover:bg-[var(--accent-strong)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? (
              <svg className="h-5 w-5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle
                  className="opacity-20"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-90"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                />
              </svg>
            ) : (
              <>
                Analyse
                <ArrowUpRight size={16} />
              </>
            )}
          </button>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2 px-1">
          {["NVDA", "MSFT", "BRK-B", "SAP", "BTC-USD"].map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => handleQuickSelect(item)}
              className="rounded-full border border-black/8 bg-white/60 px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-600 transition-colors hover:border-black/15 hover:bg-white hover:text-slate-900"
            >
              {item}
            </button>
          ))}
        </div>

        {showDropdown && Object.keys(suggestions).length > 0 && (
          <div
            ref={dropdownRef}
            className="absolute left-3 right-3 top-full z-50 mt-3 overflow-hidden rounded-[1.75rem] border border-black/8 bg-[rgba(255,255,255,0.94)] shadow-[0_24px_80px_rgba(17,24,39,0.12)] backdrop-blur-xl"
          >
            <div className="grid gap-1 p-3 md:grid-cols-2">
              {Object.entries(suggestions).map(([category, tickers]) => (
                <div key={category} className="rounded-2xl bg-black/[0.02] p-3">
                  <h4 className="mb-3 text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                    {category}
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {Array.isArray(tickers) &&
                      tickers.map((ticker) => (
                        <button
                          key={ticker}
                          type="button"
                          onClick={() => handleQuickSelect(ticker)}
                          className="rounded-full border border-black/8 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 transition-colors hover:border-[var(--accent)]/30 hover:text-[var(--accent)]"
                        >
                          {ticker}
                        </button>
                      ))}
                  </div>
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between border-t border-black/6 bg-black/[0.02] px-4 py-3 text-[11px] text-slate-500">
              <span>Suche nach Ticker, Unternehmen, ETF oder Marktsegment.</span>
              <button
                type="button"
                onClick={() => setShowDropdown(false)}
                className="font-bold uppercase tracking-[0.18em] text-slate-700"
              >
                Schließen
              </button>
            </div>
          </div>
        )}
      </div>
    </form>
  );
}
