import { useState, FormEvent, useEffect, useRef, useMemo, RefObject, useCallback } from "react";
import { Search, ArrowUpRight } from "lucide-react";
import { fetchJsonWithRetry } from "../lib/api";

const LOCAL_SEARCH_ASSETS = [
  "Apple Inc. (AAPL)",
  "Microsoft Corporation (MSFT)",
  "NVIDIA Corporation (NVDA)",
  "Amazon.com Inc. (AMZN)",
  "Alphabet Inc. (GOOGL)",
  "Meta Platforms Inc. (META)",
  "Tesla Inc. (TSLA)",
  "Advanced Micro Devices Inc. (AMD)",
  "Broadcom Inc. (AVGO)",
  "Pfizer Inc. (PFE)",
  "UnitedHealth Group Incorporated (UNH)",
  "Eli Lilly and Company (LLY)",
  "Novo Nordisk A/S (NVO)",
  "Johnson & Johnson (JNJ)",
  "JPMorgan Chase & Co. (JPM)",
  "Bank of America Corporation (BAC)",
  "Goldman Sachs Group Inc. (GS)",
  "Berkshire Hathaway Inc. (BRK-B)",
  "Visa Inc. (V)",
  "Mastercard Incorporated (MA)",
  "SAP SE (SAP)",
  "ASML Holding N.V. (ASML)",
  "Intel Corporation (INTC)",
  "Netflix Inc. (NFLX)",
  "Salesforce Inc. (CRM)",
  "Oracle Corporation (ORCL)",
  "ServiceNow Inc. (NOW)",
  "Adobe Inc. (ADBE)",
  "Palo Alto Networks Inc. (PANW)",
  "CrowdStrike Holdings Inc. (CRWD)",
  "Taiwan Semiconductor Manufacturing Company Limited (TSM)",
  "Arm Holdings plc (ARM)",
  "Super Micro Computer Inc. (SMCI)",
  "Dell Technologies Inc. (DELL)",
  "Take-Two Interactive Software Inc. (TTWO)",
  "BMW AG (BMW.DE)",
  "BYD Company Limited (BYDDY)",
  "Airbus SE (AIR.PA)",
  "Mercedes-Benz Group AG (MBG.DE)",
  "Volkswagen AG (VOW3.DE)",
  "Siemens AG (SIE.DE)",
  "Rheinmetall AG (RHM.DE)",
  "Coinbase Global Inc. (COIN)",
  "Robinhood Markets Inc. (HOOD)",
  "MicroStrategy Incorporated (MSTR)",
  "Spirit Airlines Inc. (FLYYQ)",
  "Danaher Corporation (DHR)",
  "GE Aerospace (GE)",
  "RTX Corporation (RTX)",
  "Intuitive Surgical Inc. (ISRG)",
  "Philip Morris International Inc. (PM)",
  "PepsiCo Inc. (PEP)",
  "Abbott Laboratories (ABT)",
  "Palantir Technologies Inc. (PLTR)",
  "Rocket Lab USA Inc. (RKLB)",
  "AST SpaceMobile Inc. (ASTS)",
  "IonQ Inc. (IONQ)",
  "UiPath Inc. (PATH)",
  "SoundHound AI Inc. (SOUN)",
  "Recursion Pharmaceuticals Inc. (RXRX)",
  "Joby Aviation Inc. (JOBY)",
  "Archer Aviation Inc. (ACHR)",
  "Oklo Inc. (OKLO)",
  "SPDR S&P 500 ETF Trust (SPY)",
  "Invesco QQQ Trust (QQQ)",
  "iShares Russell 2000 ETF (IWM)",
  "SPDR Gold Shares (GLD)",
  "iShares 20+ Year Treasury Bond ETF (TLT)",
  "Energy Select Sector SPDR Fund (XLE)",
  "United States Oil Fund (USO)",
  "Bitcoin USD (BTC-USD)",
  "Ethereum USD (ETH-USD)",
  "Solana USD (SOL-USD)",
];

const LOCAL_SEARCH_ALIASES: Record<string, string> = {
  ai: "NVIDIA Corporation (NVDA)",
  nvdia: "NVIDIA Corporation (NVDA)",
  nvidea: "NVIDIA Corporation (NVDA)",
  nvidia: "NVIDIA Corporation (NVDA)",
  gpu: "NVIDIA Corporation (NVDA)",
  grafikarte: "NVIDIA Corporation (NVDA)",
  grafikkarte: "NVIDIA Corporation (NVDA)",
  cuda: "NVIDIA Corporation (NVDA)",
  geforce: "NVIDIA Corporation (NVDA)",
  blackwell: "NVIDIA Corporation (NVDA)",
  quartalszahlennvidia: "NVIDIA Corporation (NVDA)",
  msft: "Microsoft Corporation (MSFT)",
  microsoft: "Microsoft Corporation (MSFT)",
  windows: "Microsoft Corporation (MSFT)",
  azure: "Microsoft Corporation (MSFT)",
  googl: "Alphabet Inc. (GOOGL)",
  google: "Alphabet Inc. (GOOGL)",
  alphabet: "Alphabet Inc. (GOOGL)",
  youtube: "Alphabet Inc. (GOOGL)",
  amazon: "Amazon.com Inc. (AMZN)",
  amzn: "Amazon.com Inc. (AMZN)",
  aws: "Amazon.com Inc. (AMZN)",
  facebook: "Meta Platforms Inc. (META)",
  instagram: "Meta Platforms Inc. (META)",
  meta: "Meta Platforms Inc. (META)",
  iphone: "Apple Inc. (AAPL)",
  aapl: "Apple Inc. (AAPL)",
  apple: "Apple Inc. (AAPL)",
  ios: "Apple Inc. (AAPL)",
  ipad: "Apple Inc. (AAPL)",
  quartalszahlenapple: "Apple Inc. (AAPL)",
  gta: "Take-Two Interactive Software Inc. (TTWO)",
  gta6: "Take-Two Interactive Software Inc. (TTWO)",
  rockstar: "Take-Two Interactive Software Inc. (TTWO)",
  gta6verschiebung: "Take-Two Interactive Software Inc. (TTWO)",
  bmw: "BMW AG (BMW.DE)",
  auto: "BMW AG (BMW.DE)",
  byd: "BYD Company Limited (BYDDY)",
  ev: "Tesla Inc. (TSLA)",
  tesler: "Tesla Inc. (TSLA)",
  elektroauto: "Tesla Inc. (TSLA)",
  airbus: "Airbus SE (AIR.PA)",
  rheinmetall: "Rheinmetall AG (RHM.DE)",
  defense: "Rheinmetall AG (RHM.DE)",
  ruestung: "Rheinmetall AG (RHM.DE)",
  pfizer: "Pfizer Inc. (PFE)",
  pfi: "Pfizer Inc. (PFE)",
  novo: "Novo Nordisk A/S (NVO)",
  obesity: "Eli Lilly and Company (LLY)",
  bitcoin: "Bitcoin USD (BTC-USD)",
  btc: "Bitcoin USD (BTC-USD)",
  crypto: "Bitcoin USD (BTC-USD)",
  ethereum: "Ethereum USD (ETH-USD)",
  eth: "Ethereum USD (ETH-USD)",
  spirit: "Spirit Airlines Inc. (FLYYQ)",
  airline: "Spirit Airlines Inc. (FLYYQ)",
  tsmc: "Taiwan Semiconductor Manufacturing Company Limited (TSM)",
  chips: "Taiwan Semiconductor Manufacturing Company Limited (TSM)",
  semiconductor: "Taiwan Semiconductor Manufacturing Company Limited (TSM)",
  smci: "Super Micro Computer Inc. (SMCI)",
  supermicro: "Super Micro Computer Inc. (SMCI)",
  arm: "Arm Holdings plc (ARM)",
  dell: "Dell Technologies Inc. (DELL)",
  brkb: "Berkshire Hathaway Inc. (BRK-B)",
  "brk.b": "Berkshire Hathaway Inc. (BRK-B)",
  "brk-b": "Berkshire Hathaway Inc. (BRK-B)",
  berkshire: "Berkshire Hathaway Inc. (BRK-B)",
  rocketlab: "Rocket Lab USA Inc. (RKLB)",
  rklb: "Rocket Lab USA Inc. (RKLB)",
  asts: "AST SpaceMobile Inc. (ASTS)",
  spacemobile: "AST SpaceMobile Inc. (ASTS)",
  ionq: "IonQ Inc. (IONQ)",
  quantum: "IonQ Inc. (IONQ)",
  uipath: "UiPath Inc. (PATH)",
  path: "UiPath Inc. (PATH)",
  soundhound: "SoundHound AI Inc. (SOUN)",
  soun: "SoundHound AI Inc. (SOUN)",
  recursion: "Recursion Pharmaceuticals Inc. (RXRX)",
  rxrx: "Recursion Pharmaceuticals Inc. (RXRX)",
  joby: "Joby Aviation Inc. (JOBY)",
  archer: "Archer Aviation Inc. (ACHR)",
  achr: "Archer Aviation Inc. (ACHR)",
  oklo: "Oklo Inc. (OKLO)",
  hood: "Robinhood Markets Inc. (HOOD)",
  hoodapp: "Robinhood Markets Inc. (HOOD)",
  robinhood: "Robinhood Markets Inc. (HOOD)",
  robinhoodmarkets: "Robinhood Markets Inc. (HOOD)",
  robinhoodapp: "Robinhood Markets Inc. (HOOD)",
  tradingapp: "Robinhood Markets Inc. (HOOD)",
};

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

function normalizeSearchValue(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "");
}

export function normalizeTickerInput(value: string): string {
  const raw = extractTicker(value)
    .trim()
    .replace(/^[#$]+/, "")
    .replace(/\b(aktie|stock|share|shares|kurs|analyse|analysis|usd|eur)\b/gi, " ")
    .replace(/[/:]+/g, "-")
    .replace(/\s+/g, " ")
    .trim();
  const compact = raw.toLowerCase().replace(/[^a-z0-9.-]+/g, "");
  const alias = LOCAL_SEARCH_ALIASES[compact] || LOCAL_SEARCH_ALIASES[normalizeSearchValue(raw)];
  if (alias) return extractTicker(alias);
  if (/^brk[.\s-]?b$/i.test(raw)) return "BRK-B";
  if (/^btc$/i.test(raw)) return "BTC-USD";
  if (/^eth$/i.test(raw)) return "ETH-USD";
  if (/^sol$/i.test(raw)) return "SOL-USD";
  return raw.toUpperCase().replace(/[^A-Z0-9.^=-]+/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "");
}

function uniqueValues(values: string[]): string[] {
  return Array.from(new Set(values));
}

function buildLocalMatches(query: string): string[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return [];
  const normalizedNeedle = normalizeSearchValue(needle);
  const alias =
    LOCAL_SEARCH_ALIASES[normalizedNeedle] ||
    LOCAL_SEARCH_ALIASES[needle] ||
    Object.entries(LOCAL_SEARCH_ALIASES).find(([key]) => key.length >= 3 && normalizedNeedle.includes(key))?.[1];
  const scored = LOCAL_SEARCH_ASSETS.map((value) => {
    const ticker = extractTicker(value).toLowerCase();
    const lowerValue = value.toLowerCase();
    const normalizedValue = normalizeSearchValue(value);
    let score = 0;
    if (alias === value) score = 120;
    else if (ticker === needle) score = 110;
    else if (ticker.startsWith(needle)) score = 100;
    else if (lowerValue.startsWith(needle)) score = 92;
    else if (lowerValue.includes(` ${needle}`)) score = 86;
    else if (lowerValue.includes(needle) || normalizedValue.includes(normalizedNeedle)) score = 74;
    else {
      const compactTicker = normalizeSearchValue(ticker);
      const overlap = [...normalizedNeedle].filter((char, index) => compactTicker[index] === char).length;
      score = normalizedNeedle.length >= 3 && overlap >= Math.min(3, normalizedNeedle.length) ? 52 : 0;
    }
    return { value, score };
  })
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score)
    .map((item) => item.value);
  return uniqueValues(alias ? [alias, ...scored] : scored).slice(0, 8);
}

function buildDefaultSuggestions(): Record<string, string[]> {
  return {
    "Aktien": LOCAL_SEARCH_ASSETS.slice(0, 14),
    "Themen": ["NVIDIA Corporation (NVDA)", "Apple Inc. (AAPL)", "Take-Two Interactive Software Inc. (TTWO)", "BMW AG (BMW.DE)", "Pfizer Inc. (PFE)", "Palo Alto Networks Inc. (PANW)"],
    "ETFs & Makro": ["SPDR S&P 500 ETF Trust (SPY)", "Invesco QQQ Trust (QQQ)", "iShares Russell 2000 ETF (IWM)", "SPDR Gold Shares (GLD)", "iShares 20+ Year Treasury Bond ETF (TLT)", "Energy Select Sector SPDR Fund (XLE)"],
    "Crypto": ["Bitcoin USD (BTC-USD)", "Ethereum USD (ETH-USD)", "Solana USD (SOL-USD)"],
  };
}

function buildDirectSearchSuggestion(query: string): Record<string, string[]> {
  const value = normalizeTickerInput(query);
  return value.length >= 2 ? { "Direkt suchen": [value] } : {};
}

export default function SearchBar({ onSearch, loading, inputRef }: SearchBarProps) {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Record<string, string[]>>(() => buildDefaultSuggestions());
  const [showDropdown, setShowDropdown] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  /** Inline ghost-text completion (Google-style) */
  const [ghostText, setGhostText] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchRequestRef = useRef(0);
  const suggestionAbortRef = useRef<AbortController | null>(null);
  const latestQueryRef = useRef("");

  const flatSuggestions = useMemo(
    () =>
      Object.entries(suggestions).flatMap(([category, values]) =>
        (values || []).filter(Boolean).map((value) => ({ category, value })),
      ),
    [suggestions],
  );
  const directSearchActive = Boolean(query.trim()) && flatSuggestions.some((item) => item.category === "Direkt suchen");

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
    setGhostText("");
  }, [query, flatSuggestions]);

  // Load default suggestions on mount
  useEffect(() => {
    const controller = new AbortController();
    fetchJsonWithRetry<Record<string, string[]>>("/api/search/suggestions", { signal: controller.signal }, {
      retries: 2,
      retryDelayMs: 900,
      timeoutMs: 2500,
    })
      .then((data) => {
        if (!controller.signal.aborted && !latestQueryRef.current.trim() && data && Object.keys(data).length > 0) {
          setSuggestions(data);
        }
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  // Debounced live search
  useEffect(() => {
    const trimmedQuery = query.trim();
    latestQueryRef.current = trimmedQuery;
    if (debounceTimer.current) clearTimeout(debounceTimer.current);

    if (trimmedQuery.length > 0) {
      const localMatches = buildLocalMatches(trimmedQuery);
      if (localMatches.length > 0) {
        setSuggestions({ Treffer: localMatches });
        setShowDropdown(true);
      }
      if (trimmedQuery.length === 1) {
        suggestionAbortRef.current?.abort();
        if (localMatches.length === 0) setSuggestions(buildDefaultSuggestions());
        return;
      }
      const requestId = searchRequestRef.current + 1;
      searchRequestRef.current = requestId;
      suggestionAbortRef.current?.abort();
      const controller = new AbortController();
      suggestionAbortRef.current = controller;
      debounceTimer.current = setTimeout(() => {
        fetchJsonWithRetry<any>(`/api/search/suggestions?q=${encodeURIComponent(trimmedQuery)}`, { signal: controller.signal }, {
          retries: 0,
          retryDelayMs: 150,
          timeoutMs: 1200,
        })
          .then((data) => {
            if (controller.signal.aborted || searchRequestRef.current !== requestId) return;
            if (data.Matches && data.Matches.length > 0) {
              setSuggestions({ Treffer: uniqueValues([...localMatches, ...data.Matches]).slice(0, 8) });
            } else if (localMatches.length === 0) {
              setSuggestions(buildDirectSearchSuggestion(trimmedQuery));
            }
          })
          .catch(() => {
            if (!controller.signal.aborted && searchRequestRef.current === requestId && localMatches.length === 0) {
              setSuggestions(buildDirectSearchSuggestion(trimmedQuery));
            }
          });
      }, 90);
    } else if (trimmedQuery.length === 0) {
      suggestionAbortRef.current?.abort();
      setSuggestions(buildDefaultSuggestions());
      setGhostText("");
    }

    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
      suggestionAbortRef.current?.abort();
    };
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
      const ticker = normalizeTickerInput(value);
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

    const localMatches = buildLocalMatches(raw);
    const exactLocal = localMatches.find((value) => {
      const ticker = extractTicker(value);
      return ticker.toLowerCase() === raw.toLowerCase() || value.toLowerCase() === raw.toLowerCase();
    });
    if (exactLocal) {
      handleQuickSelect(exactLocal);
      return;
    }

    // If query looks like a company name, resolve to ticker first
    const looksLikeName =
      raw.includes(" ") || raw !== raw.toUpperCase() || raw.length > 5;
    if (looksLikeName) {
      if (localMatches.length > 0) {
        handleQuickSelect(localMatches[0]);
        return;
      }
      try {
        const data = await fetchJsonWithRetry<any>(
          `/api/search/suggestions?q=${encodeURIComponent(raw)}`,
          undefined,
          { retries: 1, retryDelayMs: 300 },
        );
        const bestTicker = data?.Ticker?.[0] || extractTicker(data?.Matches?.[0] || "");
        if (bestTicker) {
          setQuery(bestTicker);
          setGhostText("");
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
          setQuery(bestTicker);
          setGhostText("");
          onSearch(bestTicker);
          return;
        }
      } catch {
        // fallthrough
      }
    }
    const fallbackLocal = localMatches[0];
    if (fallbackLocal && raw.length >= 3) {
      handleQuickSelect(fallbackLocal);
      return;
    }
    onSearch(normalizeTickerInput(raw));
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    // Tab or ArrowRight at end of input accepts ghost text.
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
    <form onSubmit={handleSubmit} className="mx-auto w-full max-w-[1320px]">
      <div className="surface-panel relative overflow-visible rounded-[1.6rem] p-3 sm:rounded-[2rem]">
        <div className="absolute inset-x-6 top-0 h-px bg-linear-to-r from-transparent via-black/10 to-transparent" />

        <div className="flex flex-col gap-3 md:flex-row md:items-center">
          <div className="flex flex-1 items-center gap-3 rounded-[1.3rem] bg-white/70 px-4 py-3 ring-1 ring-black/5 sm:gap-4 sm:rounded-[1.5rem] sm:px-5 sm:py-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-soft)] text-[var(--accent)] sm:h-11 sm:w-11 sm:rounded-2xl">
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
                    className="pointer-events-none absolute inset-0 flex items-center overflow-hidden text-base font-semibold sm:text-lg"
                  >
                    <span className="invisible whitespace-nowrap">{query}</span>
                    <span className="truncate whitespace-nowrap text-slate-300 dark:text-slate-600">{ghostText}</span>
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
                  onFocus={() => {
                    const localMatches = buildLocalMatches(query);
                    if (query.trim() && localMatches.length > 0) {
                      setSuggestions({ Treffer: localMatches });
                    } else if (query.trim() && Object.keys(suggestions).length === 0) {
                      setSuggestions(buildDirectSearchSuggestion(query));
                    } else if (!query.trim() && Object.keys(suggestions).length === 0) {
                      setSuggestions(buildDefaultSuggestions());
                    }
                    setShowDropdown(true);
                  }}
                  onKeyDown={handleKeyDown}
                  placeholder={ghostText ? "" : "AAPL, NVDA, ASML, BTC-USD"}
                  aria-label="Search for a stock, ETF, or crypto ticker"
                  aria-expanded={showDropdown}
                  aria-controls="search-suggestion-list"
                  aria-autocomplete="list"
                  className="relative w-full border-0 bg-transparent p-0 text-base font-semibold text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-0 sm:text-lg"
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
                Tab
              </span>
            )}
          </div>

          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="flex h-14 min-w-0 items-center justify-center gap-2 rounded-[1.2rem] bg-[var(--accent)] px-5 text-sm font-extrabold uppercase tracking-[0.16em] text-white transition-all hover:bg-[var(--accent-strong)] disabled:cursor-not-allowed disabled:opacity-50 md:h-[60px] md:min-w-[160px] md:rounded-[1.4rem] md:px-6 md:tracking-[0.18em]"
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
            <span>Tippe einen Namen oder Ticker - Tab vervollstaendigt automatisch.</span>
          </div>
          <div className="font-bold uppercase tracking-[0.16em] text-[var(--accent)]">
            {loading ? "Deep scan running" : directSearchActive ? "Direct lookup ready" : "Ready"}
          </div>
        </div>

        {showDropdown && Object.keys(suggestions).length > 0 && (
          <div
            ref={dropdownRef}
            id="search-suggestion-list"
            role="listbox"
            className="absolute left-3 right-3 top-full z-50 mt-3 overflow-hidden rounded-[1.75rem] border border-black/8 bg-[rgba(255,255,255,0.94)] shadow-[0_24px_80px_rgba(17,24,39,0.12)] backdrop-blur-xl"
          >
            <div className="grid gap-1 p-3 md:grid-cols-2">
              {Object.entries(suggestions).filter(([, tickers]) => Array.isArray(tickers) && tickers.length > 0).map(([category, tickers]) => (
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
                            role="option"
                            aria-selected={active}
                            onMouseDown={(event) => event.preventDefault()}
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
              <span>Pfeile navigieren - Enter auswaehlen - Tab vervollstaendigen</span>
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
