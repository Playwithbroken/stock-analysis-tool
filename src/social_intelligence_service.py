"""
Social Intelligence Service

Aggregates social signals, prediction markets, internet news, and a broad
earnings calendar for the morning brief.

Data sources (all free / no API key required):
- Reddit  — public JSON API (r/wallstreetbets, r/investing, r/stocks, r/options)
- Stocktwits — public stream API per ticker
- Google News RSS — per ticker and macro queries
- Polymarket — gamma REST API (prediction markets / event probabilities)
- Broad earnings calendar — yfinance for S&P 500 top-60 + user watchlist
"""

from __future__ import annotations

import re
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import requests

try:
    import feedparser  # type: ignore
    _HAS_FEEDPARSER = True
except ImportError:
    _HAS_FEEDPARSER = False

# ── HTTP session with browser-like headers ────────────────────────────────────
_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
})

# S&P 500 top 60 by market cap — used for broad earnings coverage
SP500_TOP60 = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "BRK-B",
    "LLY", "JPM", "V", "UNH", "XOM", "MA", "AVGO", "JNJ", "PG", "HD", "MRK",
    "COST", "ABBV", "CVX", "KO", "WMT", "BAC", "CRM", "NFLX", "AMD", "PEP",
    "MCD", "ORCL", "ACN", "LIN", "TMO", "WFC", "IBM", "DHR", "ABT", "CSCO",
    "GE", "INTC", "PM", "INTU", "CAT", "GS", "SPGI", "AMGN", "ISRG", "TXN",
    "RTX", "AXP", "BLK", "PFE", "NOW", "MS", "UBER", "BKNG", "AMAT", "DE",
]


class SocialIntelligenceService:
    """
    Provides Reddit sentiment, Stocktwits sentiment, Google News headlines,
    Polymarket event probabilities, and a broad earnings calendar.
    All data is cached aggressively to avoid repeated external calls.
    """

    _reddit_cache: Optional[List[Dict[str, Any]]] = None
    _reddit_cache_time: float = 0.0
    _reddit_ttl: float = 900.0  # 15 min

    _stocktwits_cache: Dict[str, Any] = {}
    _stocktwits_ttl: float = 600.0  # 10 min

    _polymarket_cache: Optional[List[Dict[str, Any]]] = None
    _polymarket_cache_time: float = 0.0
    _polymarket_ttl: float = 1800.0  # 30 min

    _earnings_cache: Optional[List[Dict[str, Any]]] = None
    _earnings_cache_time: float = 0.0
    _earnings_ttl: float = 3600.0 * 4  # 4h

    _google_news_cache: Dict[str, Any] = {}
    _google_news_ttl: float = 900.0  # 15 min

    # ── Reddit ────────────────────────────────────────────────────────────────

    SUBREDDITS = [
        ("wallstreetbets", "WSB"),
        ("investing", "r/investing"),
        ("stocks", "r/stocks"),
        ("options", "r/options"),
        ("stockmarket", "r/stockmarket"),
    ]

    def get_reddit_sentiment(
        self,
        tickers: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return a list of hot Reddit posts from finance subreddits.
        Each item has: subreddit, title, score, num_comments, url, ticker_matches,
        sentiment (bullish/bearish/neutral), created_utc.
        """
        now = _time.time()
        if self._reddit_cache is not None and (now - self._reddit_cache_time) < self._reddit_ttl:
            posts = self._reddit_cache
        else:
            posts = self._fetch_reddit_posts()
            self.__class__._reddit_cache = posts
            self.__class__._reddit_cache_time = now

        if tickers:
            upper = {t.upper() for t in tickers}
            filtered = [p for p in posts if upper & set(p.get("ticker_matches", []))]
            return filtered if filtered else posts[:10]
        return posts[:15]

    def _fetch_reddit_posts(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for sub, label in self.SUBREDDITS:
            try:
                url = f"https://www.reddit.com/r/{sub}/hot.json?limit=20&t=day"
                resp = _SESSION.get(url, timeout=10)
                if not resp.ok:
                    continue
                data = resp.json()
                posts = data.get("data", {}).get("children", [])
                for post in posts:
                    p = post.get("data", {})
                    title = p.get("title") or ""
                    if not title:
                        continue
                    score = int(p.get("score") or 0)
                    if score < 50:  # Skip low-engagement posts
                        continue
                    ticker_matches = _extract_tickers_from_text(title + " " + (p.get("selftext") or ""))
                    sentiment = _classify_sentiment(title)
                    results.append({
                        "source": "reddit",
                        "subreddit": label,
                        "title": title,
                        "score": score,
                        "num_comments": int(p.get("num_comments") or 0),
                        "url": f"https://reddit.com{p.get('permalink', '')}",
                        "ticker_matches": ticker_matches,
                        "sentiment": sentiment,
                        "created_utc": int(p.get("created_utc") or 0),
                    })
            except Exception:
                continue
        # Sort by engagement
        results.sort(key=lambda x: x["score"] + x["num_comments"] * 3, reverse=True)
        return results[:40]

    # ── Stocktwits ────────────────────────────────────────────────────────────

    def get_stocktwits_sentiment(
        self, tickers: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Return Stocktwits stream summary per ticker.
        Each item has: ticker, bullish_count, bearish_count, bull_ratio,
        top_messages, sentiment_label.
        """
        results: List[Dict[str, Any]] = []
        now = _time.time()
        for ticker in tickers[:8]:  # Limit to avoid rate-limits
            key = ticker.upper()
            cached = self._stocktwits_cache.get(key)
            if cached and (now - cached.get("_ts", 0)) < self._stocktwits_ttl:
                results.append(cached)
                continue
            item = self._fetch_stocktwits(key)
            if item:
                item["_ts"] = now
                self.__class__._stocktwits_cache[key] = item
                results.append(item)
        return results

    def _fetch_stocktwits(self, ticker: str) -> Optional[Dict[str, Any]]:
        try:
            url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json?limit=30"
            resp = _SESSION.get(url, timeout=8)
            if not resp.ok:
                return None
            data = resp.json()
            messages = data.get("messages") or []
            bullish = sum(1 for m in messages if (m.get("entities", {}).get("sentiment", {}) or {}).get("basic") == "Bullish")
            bearish = sum(1 for m in messages if (m.get("entities", {}).get("sentiment", {}) or {}).get("basic") == "Bearish")
            total = bullish + bearish or 1
            bull_ratio = round(bullish / total * 100)
            top_msgs = [
                {
                    "text": (m.get("body") or "")[:200],
                    "sentiment": (m.get("entities", {}).get("sentiment", {}) or {}).get("basic", "Neutral"),
                    "likes": m.get("likes", {}).get("total", 0) if isinstance(m.get("likes"), dict) else 0,
                }
                for m in sorted(messages, key=lambda m: (m.get("likes") or {}).get("total", 0) if isinstance(m.get("likes"), dict) else 0, reverse=True)[:3]
            ]
            label = "bullish" if bull_ratio >= 60 else "bearish" if bull_ratio <= 40 else "neutral"
            return {
                "source": "stocktwits",
                "ticker": ticker,
                "bullish_count": bullish,
                "bearish_count": bearish,
                "bull_ratio": bull_ratio,
                "sentiment_label": label,
                "message_count": len(messages),
                "top_messages": top_msgs,
            }
        except Exception:
            return None

    # ── Google News RSS ───────────────────────────────────────────────────────

    def get_google_news(
        self, queries: List[str], max_per_query: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Fetch Google News RSS headlines for the given search queries.
        Returns deduped list sorted by freshness.
        """
        if not _HAS_FEEDPARSER:
            return []
        results: List[Dict[str, Any]] = []
        seen: set = set()
        now = _time.time()

        for query in queries[:6]:  # limit queries
            cache_key = query.lower().strip()
            cached = self._google_news_cache.get(cache_key)
            if cached and (now - cached.get("_ts", 0)) < self._google_news_ttl:
                for item in cached.get("items", []):
                    if item["title"] not in seen:
                        seen.add(item["title"])
                        results.append(item)
                continue

            url = (
                f"https://news.google.com/rss/search?"
                f"q={quote_plus(query)}&hl=de&gl=DE&ceid=DE:de"
            )
            items_for_query: List[Dict[str, Any]] = []
            try:
                parsed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0"})
                for entry in (parsed.entries or [])[:max_per_query]:
                    title = (entry.get("title") or "").strip()
                    # Google News wraps titles with source: "Title - Source"
                    source = ""
                    if " - " in title:
                        parts = title.rsplit(" - ", 1)
                        title = parts[0].strip()
                        source = parts[1].strip()
                    link = entry.get("link") or ""
                    if not title or title in seen:
                        continue
                    age_hours = 999.0
                    pub = entry.get("published_parsed")
                    if pub:
                        age_hours = (_time.time() - _time.mktime(pub)) / 3600
                    if age_hours > 24:
                        continue
                    seen.add(title)
                    item = {
                        "source": "google_news",
                        "title": title,
                        "publisher": source,
                        "link": link,
                        "query": query,
                        "age_hours": round(age_hours, 1),
                    }
                    items_for_query.append(item)
                    results.append(item)
            except Exception:
                pass

            self.__class__._google_news_cache[cache_key] = {
                "_ts": now,
                "items": items_for_query,
            }

        return results

    # ── Polymarket ────────────────────────────────────────────────────────────

    POLYMARKET_FINANCE_KEYWORDS = {
        "fed", "rate", "inflation", "cpi", "gdp", "recession", "stock", "market",
        "bitcoin", "crypto", "etf", "earnings", "trump", "tariff", "trade",
        "election", "powell", "ecb", "boe", "oil", "gold", "dollar",
        "nasdaq", "s&p", "dow", "economy", "debt", "bank", "interest",
    }

    def get_polymarket_events(self) -> List[Dict[str, Any]]:
        """
        Return active Polymarket prediction markets relevant to finance/macro.
        Each item has: question, probability_yes (%), volume_usd, end_date, url.
        """
        now = _time.time()
        if (
            self._polymarket_cache is not None
            and (now - self._polymarket_cache_time) < self._polymarket_ttl
        ):
            return self._polymarket_cache

        results = self._fetch_polymarket()
        self.__class__._polymarket_cache = results
        self.__class__._polymarket_cache_time = now
        return results

    def _fetch_polymarket(self) -> List[Dict[str, Any]]:
        try:
            # Gamma API — free, no auth
            url = (
                "https://gamma-api.polymarket.com/markets"
                "?active=true&closed=false&limit=50"
                "&order=volume&ascending=false"
            )
            resp = _SESSION.get(url, timeout=12)
            if not resp.ok:
                return []
            markets = resp.json()
            if not isinstance(markets, list):
                markets = markets.get("markets") or markets.get("data") or []

            results: List[Dict[str, Any]] = []
            for m in markets:
                question = (m.get("question") or m.get("title") or "").strip()
                if not question:
                    continue
                # Filter to finance/macro relevant markets
                q_lower = question.lower()
                if not any(kw in q_lower for kw in self.POLYMARKET_FINANCE_KEYWORDS):
                    continue
                # Parse probability
                outcomes = m.get("outcomes") or []
                prob_yes: Optional[float] = None
                if outcomes:
                    for outcome in outcomes:
                        if str(outcome.get("name") or "").lower() in {"yes", "ja"}:
                            try:
                                prob_yes = round(float(outcome.get("price") or 0) * 100, 1)
                            except (ValueError, TypeError):
                                pass
                            break
                # Fallback: outcomePrices field
                if prob_yes is None:
                    prices = m.get("outcomePrices") or []
                    if isinstance(prices, list) and prices:
                        try:
                            prob_yes = round(float(prices[0]) * 100, 1)
                        except (ValueError, TypeError):
                            pass
                    elif isinstance(prices, str):
                        # Sometimes it's a JSON string "["0.72","0.28"]"
                        try:
                            import json
                            parsed = json.loads(prices)
                            prob_yes = round(float(parsed[0]) * 100, 1)
                        except Exception:
                            pass

                volume = 0.0
                try:
                    volume = float(m.get("volume") or m.get("volumeClob") or 0)
                except (ValueError, TypeError):
                    pass

                end_date = (m.get("endDate") or m.get("end_date") or "")[:10]
                slug = m.get("slug") or m.get("conditionId") or ""
                market_url = f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com"

                results.append({
                    "source": "polymarket",
                    "question": question,
                    "probability_yes": prob_yes,
                    "volume_usd": volume,
                    "end_date": end_date,
                    "url": market_url,
                })

            # Sort by volume
            results.sort(key=lambda x: x["volume_usd"], reverse=True)
            return results[:12]

        except Exception:
            return []

    # ── Broad Earnings Calendar ───────────────────────────────────────────────

    def get_broad_earnings_calendar(
        self, extra_tickers: Optional[List[str]] = None, days_ahead: int = 14
    ) -> List[Dict[str, Any]]:
        """
        Return upcoming earnings for S&P 500 top 60 + extra tickers.
        Cached for 4 hours. Each item: ticker, company, date, session,
        importance (watchlist/sp500), days_until.
        """
        now = _time.time()
        if (
            self._earnings_cache is not None
            and (now - self._earnings_cache_time) < self._earnings_ttl
        ):
            results = self._earnings_cache
        else:
            results = self._fetch_broad_earnings()
            self.__class__._earnings_cache = results
            self.__class__._earnings_cache_time = now

        # Add extra tickers if provided and not already in results
        watchlist_set = {t.upper() for t in (extra_tickers or [])}
        if watchlist_set:
            covered = {r["ticker"] for r in results}
            missing = watchlist_set - covered
            if missing:
                fresh = self._fetch_earnings_for_tickers(list(missing), days_ahead * 2)
                for item in fresh:
                    item["importance"] = "watchlist"
                results = results + fresh

        horizon_date = datetime.now(timezone.utc).date() + timedelta(days=days_ahead)
        filtered = [
            r for r in results
            if r.get("date") and r["date"][:10] <= horizon_date.isoformat()
        ]
        filtered.sort(key=lambda x: x.get("date", ""))
        return filtered[:20]

    def _fetch_broad_earnings(self) -> List[Dict[str, Any]]:
        return self._fetch_earnings_for_tickers(SP500_TOP60, days_ahead=21)

    def _fetch_earnings_for_tickers(
        self, tickers: List[str], days_ahead: int = 21
    ) -> List[Dict[str, Any]]:
        import yfinance as yf
        results: List[Dict[str, Any]] = []
        horizon = datetime.now(timezone.utc) + timedelta(days=days_ahead)
        for ticker in tickers:
            try:
                stock = yf.Ticker(ticker)
                info = stock.info or {}
                earnings_ts = (
                    info.get("earningsTimestamp")
                    or info.get("earningsTimestampStart")
                )
                if not earnings_ts:
                    cal = stock.calendar
                    if cal is not None and not (hasattr(cal, "empty") and cal.empty):
                        if hasattr(cal, "get"):
                            earnings_ts = cal.get("Earnings Date")
                            if hasattr(earnings_ts, "__iter__"):
                                try:
                                    earnings_ts = list(earnings_ts)[0]
                                    earnings_ts = int(earnings_ts.timestamp()) if hasattr(earnings_ts, "timestamp") else None
                                except Exception:
                                    earnings_ts = None
                if not earnings_ts:
                    continue
                dt = datetime.fromtimestamp(int(earnings_ts), tz=timezone.utc)
                if dt > horizon:
                    continue
                hour = dt.hour
                session = "pre-market" if hour < 12 else "after-hours" if hour >= 16 else "intraday"
                days_until = (dt.date() - datetime.now(timezone.utc).date()).days
                results.append({
                    "ticker": ticker.upper(),
                    "company": info.get("shortName") or info.get("longName") or ticker,
                    "date": dt.isoformat(),
                    "session": session,
                    "days_until": days_until,
                    "importance": "sp500",
                    "market_cap": info.get("marketCap"),
                    "eps_estimate": info.get("forwardEps"),
                })
            except Exception:
                continue
        return results


# ── Helpers ───────────────────────────────────────────────────────────────────

# Common stock tickers to recognise in free text (extend as needed)
_KNOWN_TICKERS = set(SP500_TOP60) | {
    "GME", "AMC", "PLTR", "SOFI", "RIVN", "LCID", "NIO", "BABA",
    "DIS", "NFLX", "PYPL", "SQ", "COIN", "HOOD", "RBLX", "SNAP",
    "TWTR", "SHOP", "SPOT", "DDOG", "NET", "ZM", "DOCU", "OKTA",
}
_TICKER_RE = re.compile(r'\b([A-Z]{1,5})\b')


def _extract_tickers_from_text(text: str) -> List[str]:
    """Extract known stock ticker symbols from a block of text."""
    upper = text.upper()
    found = [t for t in _TICKER_RE.findall(upper) if t in _KNOWN_TICKERS]
    return list(dict.fromkeys(found))  # deduplicate, preserve order


_BULLISH_WORDS = {
    "bull", "bullish", "buy", "long", "calls", "squeeze", "moon", "breakout",
    "upgrade", "beat", "surge", "rally", "boom", "rocket", "pump", "strong",
    "outperform", "buy the dip", "all time high", "ath", "higher", "upside",
}
_BEARISH_WORDS = {
    "bear", "bearish", "sell", "short", "puts", "crash", "dump", "drop",
    "downgrade", "miss", "sink", "plunge", "correction", "recession", "weak",
    "underperform", "lower", "downside", "fall", "fear",
}


def _classify_sentiment(text: str) -> str:
    lower = text.lower()
    bull_score = sum(1 for w in _BULLISH_WORDS if w in lower)
    bear_score = sum(1 for w in _BEARISH_WORDS if w in lower)
    if bull_score > bear_score:
        return "bullish"
    if bear_score > bull_score:
        return "bearish"
    return "neutral"
