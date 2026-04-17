import { useState, FormEvent, useEffect, useRef, useMemo, RefObject, useCallback } from "react";
import { Search, ArrowUpRight } from "lucide-react";
import { fetchJsonWithRetry } from "../lib/api";

interface SearchBarProps {
  onSearch: (ticker: string) => void;
  loading: boolean;
  /** Optional ref forwarded to the underlying text input for programmatic focus */
  inputRef?: RefObject<HTMLInputElement | null>;
}

/** Extract ticker from suggestion strings like "Apple Inc. (AAPL)" → "AAPL" */
function extractTicker(value: string): string {
  if (value.includes("(") && value.includes(")")) {
    const m = value.match(/\(([^)]+)\)/);
    if (m) return m[1];
  }
  return value;
}

export default function SearchBar({ onSearch, loading, inputRef }: SearchBarProps) {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Record<string, string[]>>({});
  const [showDropdown, setShowDropdown] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  /** Inline ghost-text completion (Google-style) */
  const [ghostText, setGhostText] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flatSuggestions = useMemo(
    () =>
      Object.entries(suggestions).flatMap(([category, values]) =>
        (values || []).map((value) => ({ category, value })),
      ),
    [suggestions],
  );

  // Compute ghost-text: first flat suggestion that starts with query (case-insensitive)
  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed || trimmed.length < 1) {
      setGhostText("");
      return;
    }
    const lower = trimmed.toLowerCase();
    for (const { value } of flatSuggestions) {
      const ticker = extractTicker(value);
      if (ticker.toLowerCase().startsWith(lower) && ticker.toLowerCase() !== lower) {
        setGhostText(ticker.slice(trimmed.length));
        return;
      }
    }
    // Also check full suggestion labels
    for (const { value } of flatSuggestions) {
      if (value.toLowerCase().startsWith(lower) && value.toLowerCase() !== lower) {
        setGhostText(value.slice(trimmed.length));
        return;
      }
    }
    setGhostText("");
  }, [query, flatSuggestions]);

  // Load default suggestions on mount
  useEffect(() => {
    fetchJsonWithRetry<Record<string, string[]>>("/api/search/suggestions", undefined, {
      retries: 2,
      retryDelayMs: 900,
    })
      .then((data) => setSuggestions(data))
      .catch(() => setSuggestions({}));
  }, []);

  // Debounced live search
  useEffect(() => {
    const trimmedQuery = query.trim();
    if (debounceTimer.current) clearTimeout(debounceTimer.current);

    if (trimmedQuery.length > 1) {
      debounceTimer.current = setTimeout(() => {
        fetchJsonWithRetry<any>(`/api/search/suggestions?q=${encodeURIComponent(trimmedQuery)}`, undefined, {
          retries: 2,
          retryDelayMs: 900,
        })
          .then((data) => {
            if (data.Matches && data.Matches.length > 0) {
              setSuggestions({ Treffer: data.Matches });
            } else {
              setSuggestions({});
            }
          })
          .catch(() => setSuggestions({}));
      }, 120); // faster than before (was 240ms)
    } else if (trimmedQuery.length === 0) {
      fetchJsonWithRetry<Record<string, string[]>>("/api/search/suggestions", undefined, {
        retries: 2,
        retryDelayMs: 900,
      })
        .then((data) => setSuggestions(data))
        .catch(() => setSuggestions({}));
    }
  }, [query]);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Reset active index when suggestions change
  useEffect(() => {
    setActiveIndex(0);
  }, [query, suggestions]);

  const handleQuickSelect = useCallback(
    (value: string) => {
      const ticker = extractTicker(value);
      setQuery(ticker);
      setGhostText("");
      onSearch(ticker);
      setShowDropdown(false);
    },
    [onSearch],
  );

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const raw = query.trim();
    if (!raw) return;
    setShowDropdown(false);
    setGhostText("");

    // Accept ghost text auto-complete if there is exactly one match
    if (flatSuggestions.length === 1) {
      handleQuickSelect(flatSuggestions[0].value);
      return;
    }

    // If query looks like a company name, resolve to ticker first
    const looksLikeName =
      raw.includes(" ") || raw !== raw.toUpperCase() || raw.length > 5;
    if (looksLikeName) {
      try {
        const data = await fetchJsonWithRetry<any>(
          `/api/search/suggestions?q=${encodeURIComponent(raw)}`,
          undefined,
          { retries: 1, retryDelayMs: 300 },
        );
        const bestTicker = data?.Ticker?.[0] || extractTicker(data?.Matches?.[0] || "");
        if (bestTicker) {
          onSearch(bestTicker);
          return;
        }
      } catch {
        // fallthrough
      }
      try {
        const direct = await fetchJsonWithRetry<any[]>(
          `/api/search?q=${encodeURIComponent(raw)}`,
          undefined,
          { retries: 1, retryDelayMs: 300 },
        );
        const bestTicker = direct?.[0]?.ticker;
        if (bestTicker) {
          onSearch(bestTicker);
          return;
        }
      } catch {
        // fallthrough
      }
    }
    onSearch(raw.toUpperCase());
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    // Tab or ArrowRight at end of input → accept ghost text
    if ((e.key === "Tab" || e.key === "ArrowRight") && ghostText) {
      const input = e.currentTarget;
      if (e.key === "Tab" || input.selectionStart === input.value.length) {
        e.preventDefault();
        const completed = query.trim() + ghostText;
        setQuery(completed);
        setGhostText("");
        setShowDropdown(true);
        return;
      }
    }

    if (!showDropdown || flatSuggestions.length === 0) {
      if (e.key === "Enter") handleSubmit(e as unknown as FormEvent);
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((prev) => (prev + 1) % flatSuggestions.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((prev) => (prev - 1 + flatSuggestions.length) % flatSuggestions.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      handleQuickSelect(flatSuggestions[activeIndex]?.value || query);
    } else if (e.key === "Escape") {
      setShowDropdown(false);
      setGhostText("");
    }
  };

  return (
    <form onSubmit={handleSubmit} className="mx-auto max-w-3xl">
      <div className="surface-panel relative overflow-hidden rounded-[2rem] p-3">
        <div className="absolute inset-x-6 top-0 h-px bg-linear-to-r from-transparent via-black/10 to-transparent" />

        <div className="flex flex-col gap-3 md:flex-row md:items-center">
          <div className="flex flex-1 items-center gap-4 rounded-[1.5rem] bg-white/70 px-5 py-4 ring-1 ring-black/5">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-[var(--accent)]">
              <Search size={18} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[11px] font-extrabold uppercase tracking-[0.24em] text-slate-500">
                Global Search
              </div>
              {/* Ghost-text overlay: shows query + ghost as overlaid read-only span */}
              <div className="relative mt-1">
                {ghostText && (
                  <span
                    aria-hidden="true"
                    className="pointer-events-none absolute inset-0 flex items-center text-lg font-semibold"
                  >
                    <span className="invisible">{query}</span>
                    <span className="text-slate-300 dark:text-slate-600">{ghostText}</span>
                  </span>
                )}
                <input
                  ref={inputRef}
                  type="text"
                  value={query}
                  onChange={(e) => {
                    setQuery(e.target.value);
                    setShowDropdown(true);
                  }}
                  onFocus={() => setShowDropdown(true)}
                  onKeyDown={handleKeyDown}
                  placeholder={ghostText ? "" : "AAPL, NVDA, ASML, BTC-USD"}
                  aria-label="Search for a stock, ETF, or crypto ticker"
                  className="relative w-full border-0 bg-transparent p-0 text-lg font-semibold text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-0"
                  style={{ caretColor: "currentColor" }}
                  disabled={loading}
                  autoComplete="off"
                  spellCheck={false}
                />
              </div>
            </div>
            {/* Ghost-text hint pill */}
            {ghostText && (
              <span className="hidden shrink-0 rounded-md border border-black/8 bg-white/70 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400 sm:inline">
                Tab →
              </span>
            )}
          </div>

          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="flex h-[60px] min-w-[160px] items-center justify-center gap-2 rounded-[1.4rem] bg-[var(--accent)] px-6 text-sm font-extrabold uppercase tracking-[0.18em] text-white transition-all hover:bg-[var(--accent-strong)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? (
              <svg className="h-5 w-5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
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

        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 px-1 text-[11px] text-slate-500">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-black/8 bg-white/65 px-3 py-1 font-bold uppercase tracking-[0.14em] text-slate-600">
              Fast lane
            </span>
            <span>Tippe einen Namen oder Ticker — Tab vervollständigt automatisch.</span>
          </div>
          <div className="font-bold uppercase tracking-[0.16em] text-[var(--accent)]">
            {loading ? "Deep scan running" : "Ready"}
          </div>
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
                  <div className="flex flex-col gap-2">
                    {Array.isArray(tickers) &&
                      tickers.map((ticker) => {
                        const flatIndex = flatSuggestions.findIndex(
                          (item) => item.category === category && item.value === ticker,
                        );
                        const active = flatIndex === activeIndex;
                        return (
                          <button
                            key={ticker}
                            type="button"
                            onClick={() => handleQuickSelect(ticker)}
                            className={`rounded-2xl border px-3 py-2 text-left text-xs font-bold transition-colors ${
                              active
                                ? "border-[var(--accent)]/30 bg-[var(--accent-soft)] text-[var(--accent)]"
                                : "border-black/8 bg-white text-slate-700 hover:border-[var(--accent)]/30 hover:text-[var(--accent)]"
                            }`}
                          >
                            {ticker}
                          </button>
                        );
                      })}
                  </div>
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between border-t border-black/6 bg-black/[0.02] px-4 py-3 text-[11px] text-slate-500">
              <span>↑↓ navigieren · Enter auswählen · Tab vervollständigen</span>
              <button
                type="button"
                onClick={() => setShowDropdown(false)}
                className="font-bold uppercase tracking-[0.18em] text-slate-700"
              >
                Schliessen
              </button>
            </div>
          </div>
        )}
      </div>
    </form>
  );
}
