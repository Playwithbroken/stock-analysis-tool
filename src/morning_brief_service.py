"""
Morning brief service.

Builds a market-opening brief across Asia, Europe, and the US using public
market data, best-effort event classification, and watchlist-aware calendars.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Sequence

import pandas as pd

from src.data_fetcher import DataFetcher


class MorningBriefService:
    _cache: Dict[str, Any] | None = None
    _cache_time: datetime | None = None
    _ttl_seconds = 60 * 10

    ASIA = [
        ("^N225", "Nikkei 225"),
        ("^HSI", "Hang Seng"),
        ("000001.SS", "Shanghai Composite"),
    ]
    EUROPE = [
        ("^GDAXI", "DAX"),
        ("^FTSE", "FTSE 100"),
        ("^FCHI", "CAC 40"),
    ]
    USA = [
        ("ES=F", "S&P 500 Futures"),
        ("NQ=F", "Nasdaq Futures"),
        ("YM=F", "Dow Futures"),
    ]
    MACRO = [
        ("CL=F", "Oil"),
        ("GC=F", "Gold"),
        ("BTC-USD", "Bitcoin"),
        ("^TNX", "US 10Y Yield"),
        ("DX-Y.NYB", "US Dollar Index"),
    ]
    NEWS_TICKERS = ["SPY", "QQQ", "GLD", "TLT", "XLE", "NVDA", "AAPL", "MSFT"]
    DEFAULT_BRIEF_TIMEZONE = "Europe/Berlin"
    CONTRARIAN_PUBLISHERS = {"CNBC", "Bloomberg", "Reuters", "MarketWatch", "Barron's", "Barrons", "WSJ"}
    TRUSTED_PUBLISHERS = {
        "Reuters",
        "Bloomberg",
        "Financial Times",
        "The Wall Street Journal",
        "Wall Street Journal",
        "CNBC",
        "Barron's",
        "Barrons",
        "MarketWatch",
        "The Economist",
        "Associated Press",
        "AP News",
        "Nikkei Asia",
        "WSJ",
    }
    ALLOWED_DOMAINS = {
        "reuters.com",
        "bloomberg.com",
        "ft.com",
        "wsj.com",
        "cnbc.com",
        "barrons.com",
        "marketwatch.com",
        "economist.com",
        "apnews.com",
        "nikkei.com",
        "finance.yahoo.com",
    }
    EXCLUDED_SOURCE_TERMS = {
        "x.com",
        "twitter",
        "tiktok",
        "instagram",
        "facebook",
        "truth social",
        "discord",
        "telegram",
        "stocktwits",
        "youtube",
        "substack",
        "medium",
        "blog",
    }
    CROWD_SOURCE_TERMS = {
        "reddit",
        "reddit.com",
        "wallstreetbets",
    }

    def get_brief(self, watchlist_snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        if (
            self._cache is not None
            and self._cache_time is not None
            and (now - self._cache_time).total_seconds() < self._ttl_seconds
        ):
            return self._merge_watchlist_impact(dict(self._cache), watchlist_snapshot)

        asia = self._collect_region(self.ASIA, "Asia")
        europe = self._collect_region(self.EUROPE, "Europe")
        usa = self._collect_region(self.USA, "USA")
        macro = self._collect_assets(self.MACRO)
        top_news = self._collect_news()
        crowd_news = self._collect_crowd_news()
        social_news = self._collect_social_news()
        event_layer = self._build_event_layer(top_news)
        contrarian_signals = self._build_contrarian_signals(top_news, watchlist_snapshot)
        earnings_calendar = self._collect_earnings_calendar(watchlist_snapshot)
        economic_calendar = self._build_economic_calendar(event_layer)
        opening_timeline = self._build_opening_timeline(
            [asia, europe, usa],
            top_news,
            event_layer,
            economic_calendar,
            earnings_calendar,
        )
        narrative = self._build_narrative(asia, europe, usa, macro, event_layer)

        brief = {
            "generated_at": now.isoformat(),
            "macro_score": narrative["macro_score"],
            "macro_regime": narrative["macro_regime"],
            "opening_bias": narrative["opening_bias"],
            "headline": narrative["headline"],
            "summary_points": narrative["summary_points"],
            "regions": {
                "asia": asia,
                "europe": europe,
                "usa": usa,
            },
            "macro_assets": macro,
            "top_news": top_news,
            "crowd_signals": self._build_crowd_signals(crowd_news),
            "social_signals": self._build_social_signals(social_news),
            "source_policy": {
                "trusted_publishers": sorted(self.TRUSTED_PUBLISHERS),
                "allowed_domains": sorted(self.ALLOWED_DOMAINS),
                "excluded_sources": sorted(self.EXCLUDED_SOURCE_TERMS),
                "crowd_sources": sorted(self.CROWD_SOURCE_TERMS),
                "note": "Top News zeigt nur priorisierte serioese Quellen. Social/X und Reddit laufen separat ueber Social und Crowd Radar, nicht im Trusted-News-Block.",
            },
            "event_layer": event_layer,
            "contrarian_signals": contrarian_signals,
            "economic_calendar": economic_calendar,
            "earnings_calendar": earnings_calendar,
            "opening_timeline": opening_timeline,
            "action_board": self._build_action_board(top_news, event_layer, watchlist_snapshot, narrative["macro_regime"]),
            "watchlist_impact": [],
        }
        self._cache = brief
        self._cache_time = now
        return self._merge_watchlist_impact(dict(brief), watchlist_snapshot)

    def _collect_region(self, tickers: Sequence[tuple[str, str]], label: str) -> Dict[str, Any]:
        assets = self._collect_assets(tickers)
        changes = [item["change_1d"] for item in assets if item.get("change_1d") is not None]
        avg_change = sum(changes) / len(changes) if changes else 0
        tone = "risk-on" if avg_change > 0.45 else "risk-off" if avg_change < -0.45 else "mixed"
        return {
            "label": label,
            "tone": tone,
            "avg_change_1d": avg_change,
            "assets": assets,
        }

    def _collect_assets(self, tickers: Sequence[tuple[str, str]]) -> List[Dict[str, Any]]:
        assets = []
        for ticker, label in tickers:
            fetcher = DataFetcher(ticker)
            price = fetcher.get_price_data()
            assets.append(
                {
                    "ticker": ticker,
                    "label": label,
                    "price": price.get("current_price"),
                    "change_1d": self._estimate_change_1d(price),
                    "change_1w": price.get("change_1w"),
                }
            )
        return assets

    def _collect_news(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        seen_titles = set()
        for ticker in self.NEWS_TICKERS:
            news = DataFetcher(ticker).get_news()
            for item in news[:2]:
                title = item.get("title") or ""
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                text = title.lower()
                publisher = item.get("publisher") or ""
                link = item.get("link")
                source_meta = self._source_meta(publisher, link)
                classification = self._classify_news_signal(text)
                if source_meta["exclude"]:
                    continue
                items.append(
                    {
                        "ticker": ticker,
                        "title": title,
                        "publisher": publisher,
                        "link": link,
                        "source_domain": source_meta["domain"],
                        "source_type": source_meta["source_type"],
                        "source_quality": source_meta["quality"],
                        "is_trusted_source": source_meta["trusted"],
                        "impact": classification["impact"],
                        "region": classification["region"],
                        "event_type": classification["event_type"],
                        "severity": classification["severity"],
                    }
                )
        trusted_items = [item for item in items if item.get("is_trusted_source")]
        trusted_items.sort(
            key=lambda item: (
                0 if item.get("source_quality") == "tier_1" else 1,
                0 if item["impact"] == "high" else 1 if item["impact"] == "medium" else 2,
                0 if item.get("severity") == "critical" else 1 if item.get("severity") == "elevated" else 2,
                item["region"],
            )
        )
        return trusted_items[:12]

    def _build_event_layer(self, news: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        layer = []
        for item in news:
            event_type = item.get("event_type") or "macro"
            severity = item.get("severity") or "normal"
            if event_type == "macro" and item.get("impact") == "low":
                continue
            layer.append(
                {
                    "title": item.get("title"),
                    "link": item.get("link"),
                    "region": item.get("region"),
                    "impact": item.get("impact"),
                    "event_type": event_type,
                    "severity": severity,
                    "publisher": item.get("publisher"),
                    "source_quality": item.get("source_quality"),
                    "ticker": item.get("ticker"),
                }
            )
        return layer[:8]

    def _build_contrarian_signals(
        self,
        news: List[Dict[str, Any]],
        watchlist_snapshot: Dict[str, Any] | None,
    ) -> List[Dict[str, Any]]:
        watch_tickers = [
            (item.get("value") or "").upper()
            for item in (watchlist_snapshot or {}).get("items", [])
            if item.get("kind") == "ticker"
        ]
        candidates = []
        seen = set()
        for item in news:
            title = (item.get("title") or "").lower()
            publisher = item.get("publisher") or ""
            ticker = (item.get("ticker") or "").upper()
            if publisher not in self.CONTRARIAN_PUBLISHERS:
                continue
            if not any(term in title for term in ["buy", "sell", "bull", "bear", "upgrade", "downgrade", "top pick", "call"]):
                continue
            if not ticker or ticker in seen:
                continue
            if watch_tickers and ticker not in watch_tickers and ticker not in {"SPY", "QQQ", "AAPL", "MSFT", "NVDA"}:
                continue
            technical = self._build_contrarian_technical(ticker)
            if not technical:
                continue
            media_bias = "long" if any(term in title for term in ["buy", "bull", "upgrade", "top pick"]) else "short"
            contrarian_bias = "short" if media_bias == "long" else "long"
            if not self._contrarian_confirmation(media_bias, technical):
                continue
            score = self._contrarian_score(technical)
            candidates.append(
                {
                    "ticker": ticker,
                    "title": item.get("title"),
                    "publisher": publisher,
                    "region": item.get("region") or "usa",
                    "media_bias": media_bias,
                    "contrarian_bias": contrarian_bias,
                    "score": score,
                    "rsi_14": technical["rsi_14"],
                    "volume_ratio": technical["volume_ratio"],
                    "ema_stack": technical["ema_stack"],
                    "reason": technical["reason"],
                    "link": item.get("link"),
                }
            )
            seen.add(ticker)
        candidates.sort(key=lambda row: row["score"], reverse=True)
        return candidates[:6]

    def _build_contrarian_technical(self, ticker: str) -> Dict[str, Any] | None:
        try:
            hist = DataFetcher(ticker).stock.history(period="6mo", interval="1d")
            if hist.empty or len(hist) < 50:
                return None
            close = hist["Close"].astype(float)
            volume = hist["Volume"].astype(float)
            ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
            ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
            current = float(close.iloc[-1])
            volume_ratio = float(volume.iloc[-1] / volume.tail(20).mean()) if float(volume.tail(20).mean() or 0) else 0
            rsi = self._rsi(close, 14)
            if current > ema20 > ema50:
                ema_stack = "bullish"
            elif current < ema20 < ema50:
                ema_stack = "bearish"
            else:
                ema_stack = "mixed"
            return {
                "rsi_14": round(rsi, 1),
                "volume_ratio": round(volume_ratio, 2),
                "ema_stack": ema_stack,
                "reason": f"RSI {rsi:.1f}, RVOL {volume_ratio:.2f}, EMA stack {ema_stack}",
            }
        except Exception:
            return None

    def _contrarian_confirmation(self, media_bias: str, technical: Dict[str, Any]) -> bool:
        rsi = float(technical.get("rsi_14") or 50)
        volume_ratio = float(technical.get("volume_ratio") or 0)
        ema_stack = technical.get("ema_stack")
        if media_bias == "long":
            return (rsi >= 67 and ema_stack == "bullish") or (rsi >= 72) or (volume_ratio >= 1.8 and rsi >= 64)
        return (rsi <= 33 and ema_stack == "bearish") or (rsi <= 28) or (volume_ratio >= 1.8 and rsi <= 36)

    def _contrarian_score(self, technical: Dict[str, Any]) -> float:
        rsi = float(technical.get("rsi_14") or 50)
        volume_ratio = float(technical.get("volume_ratio") or 1)
        distance = abs(rsi - 50)
        return round(min(95, 52 + distance * 1.15 + max(0, volume_ratio - 1) * 14), 1)

    def _rsi(self, close: pd.Series, window: int) -> float:
        delta = close.diff()
        gains = delta.clip(lower=0).rolling(window=window).mean()
        losses = (-delta.clip(upper=0)).rolling(window=window).mean()
        rs = gains / losses.replace(0, pd.NA)
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.dropna().iloc[-1]) if not rsi.dropna().empty else 50.0

    def _collect_crowd_news(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        seen_titles = set()
        for ticker in self.NEWS_TICKERS:
            news = DataFetcher(ticker).get_news()
            for item in news[:4]:
                title = item.get("title") or ""
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                publisher = item.get("publisher") or ""
                link = item.get("link")
                source_meta = self._source_meta(publisher, link)
                if source_meta["source_type"] != "crowd":
                    continue
                classification = self._classify_news_signal(title.lower())
                items.append(
                    {
                        "ticker": ticker,
                        "title": title,
                        "publisher": publisher,
                        "link": link,
                        "source_domain": source_meta["domain"],
                        "source_type": source_meta["source_type"],
                        "source_quality": source_meta["quality"],
                        "impact": classification["impact"],
                        "region": classification["region"],
                        "event_type": classification["event_type"],
                        "severity": classification["severity"],
                    }
                )
        return items

    def _build_crowd_signals(self, news: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}
        for item in news:
            if item.get("source_type") != "crowd":
                continue
            key = (item.get("ticker") or "") + ":" + (item.get("event_type") or "macro")
            bucket = grouped.setdefault(
                key,
                {
                    "ticker": item.get("ticker"),
                    "event_type": item.get("event_type"),
                    "region": item.get("region"),
                    "mentions": 0,
                    "titles": [],
                },
            )
            bucket["mentions"] += 1
            if item.get("title"):
                bucket["titles"].append(item["title"])
        signals = [item for item in grouped.values() if item["mentions"] >= 2]
        signals.sort(key=lambda item: item["mentions"], reverse=True)
        return signals[:6]

    def _collect_social_news(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        seen_titles = set()
        for ticker in self.NEWS_TICKERS:
            news = DataFetcher(ticker).get_news()
            for item in news[:5]:
                title = item.get("title") or ""
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                publisher = item.get("publisher") or ""
                link = item.get("link")
                source_meta = self._source_meta(publisher, link)
                if source_meta["source_type"] != "social":
                    continue
                classification = self._classify_news_signal(title.lower())
                items.append(
                    {
                        "ticker": ticker,
                        "title": title,
                        "publisher": publisher,
                        "link": link,
                        "source_domain": source_meta["domain"],
                        "source_type": source_meta["source_type"],
                        "source_quality": source_meta["quality"],
                        "impact": classification["impact"],
                        "region": classification["region"],
                        "event_type": classification["event_type"],
                        "severity": classification["severity"],
                    }
                )
        return items

    def _build_social_signals(self, news: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}
        for item in news:
            if item.get("source_type") != "social":
                continue
            key = f"{item.get('ticker') or 'macro'}:{item.get('publisher') or item.get('source_domain') or 'social'}:{item.get('event_type') or 'macro'}"
            bucket = grouped.setdefault(
                key,
                {
                    "ticker": item.get("ticker"),
                    "event_type": item.get("event_type"),
                    "region": item.get("region"),
                    "publisher": item.get("publisher") or item.get("source_domain") or "Social",
                    "mentions": 0,
                    "titles": [],
                },
            )
            bucket["mentions"] += 1
            if item.get("title"):
                bucket["titles"].append(item["title"])
        signals = list(grouped.values())
        signals.sort(key=lambda item: (item["mentions"], item.get("ticker") is not None), reverse=True)
        return signals[:8]

    def _collect_earnings_calendar(self, watchlist_snapshot: Dict[str, Any] | None) -> List[Dict[str, Any]]:
        tickers: List[str] = []
        watched_tickers = set()
        if watchlist_snapshot:
            for item in watchlist_snapshot.get("items", []):
                if item.get("kind") != "ticker":
                    continue
                value = item.get("value", "")
                tickers.append(value)
                watched_tickers.add((value or "").upper().strip())
        tickers.extend(self.NEWS_TICKERS)

        unique_tickers = []
        seen = set()
        for ticker in tickers:
            normalized = (ticker or "").upper().strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique_tickers.append(normalized)

        entries: List[Dict[str, Any]] = []
        horizon = datetime.now(timezone.utc) + timedelta(days=21)
        for ticker in unique_tickers[:12]:
            try:
                info = DataFetcher(ticker).info
                earnings_at = self._extract_earnings_datetime(info)
                if not earnings_at or earnings_at > horizon:
                    continue
                entries.append(
                    {
                        "ticker": ticker,
                        "company": info.get("shortName") or info.get("longName") or ticker,
                        "scheduled_for": earnings_at.isoformat(),
                        "session": self._classify_earnings_session(earnings_at),
                        "importance": "watchlist" if ticker in watched_tickers else "market",
                        "region": self._region_from_country(info.get("country")),
                    }
                )
            except Exception:
                continue

        entries.sort(key=lambda item: item["scheduled_for"])
        return entries[:8]

    def _build_economic_calendar(self, event_layer: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        tz = ZoneInfo(self.DEFAULT_BRIEF_TIMEZONE)
        today = datetime.now(tz).date()
        windows = [
            {
                "title": "Europe cash open",
                "category": "session",
                "region": "europe",
                "scheduled_for": datetime.combine(today, time(9, 0), tzinfo=tz).isoformat(),
                "importance": "high",
                "source": "market_hours",
            },
            {
                "title": "US macro release window",
                "category": "macro",
                "region": "usa",
                "scheduled_for": datetime.combine(today, time(14, 30), tzinfo=tz).isoformat(),
                "importance": "high",
                "source": "macro_window",
            },
            {
                "title": "US cash open",
                "category": "session",
                "region": "usa",
                "scheduled_for": datetime.combine(today, time(15, 30), tzinfo=tz).isoformat(),
                "importance": "high",
                "source": "market_hours",
            },
        ]

        event_titles = set()
        for event in event_layer[:5]:
            title = event.get("event_type", "macro").replace("_", " ").title()
            region = event.get("region") or "global"
            key = f"{title}:{region}"
            if key in event_titles:
                continue
            event_titles.add(key)
            windows.append(
                {
                    "title": title,
                    "category": event.get("event_type") or "macro",
                    "region": region,
                    "scheduled_for": datetime.combine(today, time(8, 0), tzinfo=tz).isoformat(),
                    "importance": "high" if event.get("severity") == "critical" else "medium",
                    "source": "news_signal",
                }
            )

        windows.sort(key=lambda item: item["scheduled_for"])
        return windows[:8]

    def _build_opening_timeline(
        self,
        regions: List[Dict[str, Any]],
        top_news: List[Dict[str, Any]],
        event_layer: List[Dict[str, Any]],
        economic_calendar: List[Dict[str, Any]],
        earnings_calendar: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        order = ["Asia", "Europe", "USA"]
        timeline: List[Dict[str, Any]] = []
        for idx, label in enumerate(order):
            region = next((item for item in regions if item.get("label") == label), None)
            if not region:
                continue
            region_key = label.lower()
            driver = next(
                (
                    item.get("title")
                    for item in top_news
                    if item.get("region") == region_key
                ),
                region.get("assets", [{}])[0].get("label", "Cross-asset confirmation needed"),
            )
            catalysts = [
                item["title"]
                for item in economic_calendar
                if item.get("region") in {region_key, "global"}
            ][:2]
            earnings = [
                item["ticker"]
                for item in earnings_calendar
                if item.get("region") in {region_key, "global"}
            ][:2]
            timeline.append(
                {
                    "stage": "Asia close" if idx == 0 else "Europe handoff" if idx == 1 else "US open",
                    "label": label,
                    "tone": region.get("tone"),
                    "move": region.get("avg_change_1d", 0),
                    "driver": driver,
                    "catalysts": catalysts,
                    "earnings": earnings,
                    "event_types": [
                        item.get("event_type")
                        for item in event_layer
                        if item.get("region") in {region_key, "global"}
                    ][:3],
                }
            )
        return timeline

    def _build_narrative(
        self,
        asia: Dict[str, Any],
        europe: Dict[str, Any],
        usa: Dict[str, Any],
        macro: List[Dict[str, Any]],
        event_layer: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        macro_score = 0
        oil = self._find_asset(macro, "CL=F")
        gold = self._find_asset(macro, "GC=F")
        bitcoin = self._find_asset(macro, "BTC-USD")
        dollar = self._find_asset(macro, "DX-Y.NYB")

        for region in [asia, europe, usa]:
            avg = region.get("avg_change_1d", 0) or 0
            macro_score += 1 if avg > 0.35 else -1 if avg < -0.35 else 0

        if oil and (oil.get("change_1d") or 0) > 1:
            macro_score -= 1
        if gold and (gold.get("change_1d") or 0) > 1:
            macro_score -= 1
        if bitcoin and (bitcoin.get("change_1d") or 0) > 1:
            macro_score += 1
        if dollar and (dollar.get("change_1d") or 0) > 0.6:
            macro_score -= 1

        critical_events = sum(1 for item in event_layer if item.get("severity") == "critical")
        central_bank_events = sum(1 for item in event_layer if item.get("event_type") == "central_bank")
        if critical_events:
            macro_score -= min(2, critical_events)
        if central_bank_events:
            macro_score -= 1

        macro_regime = "risk-on" if macro_score >= 2 else "risk-off" if macro_score <= -2 else "mixed"
        opening_bias = {
            "risk-on": "Constructive open, growth and cyclicals favored.",
            "risk-off": "Defensive open, energy, gold and duration likely in focus.",
            "mixed": "Selective open, cross-asset confirmation needed.",
        }[macro_regime]

        headline = (
            f"{macro_regime.upper()} setup: Asia {asia['tone']}, Europe {europe['tone']}, "
            f"US futures {usa['tone']}."
        )

        summary_points = [
            f"Asia: {asia['tone']} with average move {asia['avg_change_1d']:+.2f}%.",
            f"Europe: {europe['tone']} with average move {europe['avg_change_1d']:+.2f}%.",
            f"US futures: {usa['tone']} with average move {usa['avg_change_1d']:+.2f}%.",
        ]
        if oil:
            summary_points.append(f"Oil: {oil['change_1d']:+.2f}% overnight.")
        if gold:
            summary_points.append(f"Gold: {gold['change_1d']:+.2f}% overnight.")
        if event_layer:
            event = event_layer[0]
            summary_points.append(
                f"Event layer: {event.get('event_type', 'macro').replace('_', ' ')} in {event.get('region', 'global')}."
            )

        return {
            "macro_score": macro_score,
            "macro_regime": macro_regime,
            "opening_bias": opening_bias,
            "headline": headline,
            "summary_points": summary_points,
        }

    def _build_action_board(
        self,
        news: List[Dict[str, Any]],
        event_layer: List[Dict[str, Any]],
        watchlist_snapshot: Dict[str, Any] | None,
        macro_regime: str,
    ) -> List[Dict[str, Any]]:
        watched_tickers = {
            str(item.get("value") or "").upper()
            for item in (watchlist_snapshot or {}).get("items", [])
            if item.get("kind") == "ticker"
        }
        board: List[Dict[str, Any]] = []
        for item in news[:10]:
            ticker = str(item.get("ticker") or "").upper() or None
            event_type = item.get("event_type") or "macro"
            impact = item.get("impact") or "low"
            setup = "watch"
            leverage = "avoid"
            trigger = "Wait for confirmation after the open."
            risk = "Do not force size without confirmation."
            thesis = item.get("title") or "Market-moving headline."

            if event_type in {"conflict", "policy"}:
                setup = "hedge"
                leverage = "avoid"
                trigger = "Watch oil, gold and broad index reaction first."
                risk = "Headline risk can reverse fast."
            elif event_type == "election":
                setup = "watch"
                leverage = "avoid"
                trigger = "Wait for the first market read after voting or coalition headlines."
                risk = "Election headlines can violently reprice sectors before direction settles."
            elif event_type == "disaster":
                setup = "hedge"
                leverage = "avoid"
                trigger = "Focus on supply-chain, insurers, commodities and transport sensitivity first."
                risk = "Initial panic often overshoots before the economic damage is clear."
            elif event_type in {"central_bank", "macro_data"}:
                setup = "short" if macro_regime == "risk-off" else "long" if macro_regime == "risk-on" else "watch"
                leverage = "conditional" if impact == "medium" else "avoid"
                trigger = "Use only after rates, dollar and index futures confirm."
                risk = "Macro reversals can invalidate the move quickly."
            elif event_type == "energy":
                setup = "long" if macro_regime != "risk-off" else "hedge"
                leverage = "conditional"
                trigger = "Energy strength should hold after the Europe or US open."
                risk = "Oil spikes can fade on policy headlines."
            elif event_type == "earnings":
                setup = "long" if "upgrade" in (item.get("title") or "").lower() else "short" if "downgrade" in (item.get("title") or "").lower() else "watch"
                leverage = "conditional" if impact == "medium" else "avoid"
                trigger = "Wait for price to hold above or below the first impulse."
                risk = "Single-name moves fail often without volume confirmation."

            if ticker and ticker in watched_tickers:
                trigger = f"Watch {ticker} first. It is already on your radar."

            board.append(
                {
                    "title": thesis,
                    "region": item.get("region") or "usa",
                    "ticker": ticker,
                    "event_type": event_type,
                    "impact": impact,
                    "setup": setup,
                    "leverage": leverage,
                    "thesis": self._action_thesis(event_type, macro_regime, ticker),
                    "trigger": trigger,
                    "risk": risk,
                    "source": item.get("publisher"),
                    "link": item.get("link"),
                }
            )

        if not board and event_layer:
            for item in event_layer[:4]:
                board.append(
                    {
                        "title": item.get("title"),
                        "region": item.get("region") or "global",
                        "ticker": item.get("ticker"),
                        "event_type": item.get("event_type") or "macro",
                        "impact": item.get("impact") or "medium",
                        "setup": "watch",
                        "leverage": "avoid",
                        "thesis": self._action_thesis(item.get("event_type") or "macro", macro_regime, item.get("ticker")),
                        "trigger": "Wait for market structure to confirm direction.",
                        "risk": "Do not use leverage on headline noise alone.",
                        "source": item.get("publisher"),
                        "link": item.get("link"),
                    }
                )
        return board[:8]

    def _action_thesis(self, event_type: str, macro_regime: str, ticker: str | None) -> str:
        if event_type == "conflict":
            return "Defensive assets and hedges matter more than aggressive upside chasing."
        if event_type == "central_bank":
            return "Rates and dollar direction should decide whether growth can extend or needs to fade."
        if event_type == "policy":
            return "Policy headlines can reprice sectors quickly. Prefer broad-theme trades over blind copy trades."
        if event_type == "energy":
            return "Energy-sensitive names and inflation expectations become more relevant."
        if event_type == "election":
            return "Election outcomes can rotate capital across rates, defense, energy and domestic cyclicals."
        if event_type == "disaster":
            return "Natural disasters matter when they hit supply chains, insurers, commodities or transport routes."
        if event_type == "earnings" and ticker:
            return f"{ticker} needs follow-through, not just the headline."
        if macro_regime == "risk-off":
            return "Protect first. Shorts or hedges matter more than chasing momentum."
        if macro_regime == "risk-on":
            return "Constructive tape, but only names with confirmation deserve leverage."
        return "Mixed regime. Keep conviction selective and size smaller."

    def _merge_watchlist_impact(
        self,
        brief: Dict[str, Any],
        watchlist_snapshot: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        if not watchlist_snapshot:
            return brief

        watched_tickers = {
            item["value"]
            for item in watchlist_snapshot.get("items", [])
            if item.get("kind") == "ticker"
        }
        impact = []

        for signal in watchlist_snapshot.get("ticker_signals", []):
            if signal.get("ticker") not in watched_tickers:
                continue
            event = (signal.get("events") or [None])[0]
            if event:
                impact.append(
                    {
                        "ticker": signal.get("ticker"),
                        "type": "insider",
                        "summary": (
                            f"{signal.get('ticker')}: {event.get('action')} by {event.get('owner_name')} "
                            f"on {event.get('trade_date')}"
                        ),
                    }
                )
        for news in brief.get("top_news", []):
            if news.get("ticker") in watched_tickers:
                impact.append(
                    {
                        "ticker": news.get("ticker"),
                        "type": "news",
                        "summary": f"{news.get('title')} ({news.get('publisher')})",
                    }
                )
        brief["watchlist_impact"] = impact[:8]
        return brief

    def _source_meta(self, publisher: str | None, link: str | None) -> Dict[str, Any]:
        publisher_value = (publisher or "").strip()
        publisher_lower = publisher_value.lower()
        domain = self._extract_domain(link)
        domain_lower = domain.lower()

        social_hit = any(term in publisher_lower or term in domain_lower for term in self.EXCLUDED_SOURCE_TERMS)
        crowd_hit = any(term in publisher_lower or term in domain_lower for term in self.CROWD_SOURCE_TERMS)
        trusted_publisher = any(
            trusted.lower() in publisher_lower for trusted in self.TRUSTED_PUBLISHERS
        )
        trusted_domain = any(
            domain_lower == allowed or domain_lower.endswith(f".{allowed}")
            for allowed in self.ALLOWED_DOMAINS
        )

        if social_hit:
            return {
                "domain": domain,
                "trusted": False,
                "exclude": True,
                "quality": "excluded",
                "source_type": "social",
            }
        if crowd_hit:
            return {
                "domain": domain,
                "trusted": False,
                "exclude": False,
                "quality": "crowd",
                "source_type": "crowd",
            }
        if trusted_publisher or trusted_domain:
            quality = "tier_1" if trusted_publisher and trusted_domain else "tier_2"
            return {
                "domain": domain,
                "trusted": True,
                "exclude": False,
                "quality": quality,
                "source_type": "publisher",
            }
        return {
            "domain": domain,
            "trusted": False,
            "exclude": True,
            "quality": "unverified",
            "source_type": "unverified",
        }

    def _extract_domain(self, link: str | None) -> str:
        if not link:
            return ""
        try:
            parsed = urlparse(link)
            return (parsed.netloc or "").lower().removeprefix("www.")
        except Exception:
            return ""

    def _estimate_change_1d(self, price_data: Dict[str, Any]) -> float | None:
        change_1w = price_data.get("change_1w")
        if change_1w is None:
            return None
        return change_1w / 5

    def _classify_news_signal(self, text: str) -> Dict[str, str]:
        event_type = "macro"
        impact = "low"
        severity = "normal"

        if any(term in text for term in ["war", "missile", "attack", "israel", "iran", "russia", "ukraine"]):
            event_type = "conflict"
            impact = "high"
            severity = "critical"
        elif any(term in text for term in ["fed", "ecb", "boj", "central bank", "rate", "yield"]):
            event_type = "central_bank"
            impact = "high"
            severity = "elevated"
        elif any(term in text for term in ["oil", "opec", "gas", "crude"]):
            event_type = "energy"
            impact = "medium"
            severity = "elevated"
        elif any(term in text for term in ["election", "vote", "ballot", "president", "prime minister", "parliament", "coalition", "campaign"]):
            event_type = "election"
            impact = "high"
            severity = "elevated"
        elif any(term in text for term in ["earthquake", "wildfire", "flood", "storm", "hurricane", "typhoon", "tsunami", "drought", "disaster"]):
            event_type = "disaster"
            impact = "high"
            severity = "critical"
        elif any(term in text for term in ["tariff", "sanction", "trade", "regulation", "policy"]):
            event_type = "policy"
            impact = "high"
            severity = "elevated"
        elif any(term in text for term in ["inflation", "cpi", "ppi", "recession", "payrolls", "jobs"]):
            event_type = "macro_data"
            impact = "high"
            severity = "elevated"
        elif any(term in text for term in ["earnings", "guidance", "upgrade", "downgrade"]):
            event_type = "earnings"
            impact = "medium"
            severity = "normal"
        elif any(term in text for term in ["china", "japan", "hong kong", "taiwan"]):
            event_type = "regional_macro"
            impact = "medium"
            severity = "normal"

        return {
            "impact": impact,
            "region": self._infer_region(text),
            "event_type": event_type,
            "severity": severity,
        }

    def _infer_region(self, text: str) -> str:
        if any(term in text for term in ["china", "japan", "asia", "hong kong", "taiwan", "korea", "india"]):
            return "asia"
        if any(term in text for term in ["europe", "germany", "uk", "france", "ecb", "italy"]):
            return "europe"
        if any(term in text for term in ["global", "opec", "oil", "war", "sanction"]):
            return "global"
        return "usa"

    def _extract_earnings_datetime(self, info: Dict[str, Any]) -> datetime | None:
        candidates = [
            info.get("earningsTimestamp"),
            info.get("earningsTimestampStart"),
            info.get("earningsTimestampEnd"),
            info.get("earningsDate"),
        ]
        for candidate in candidates:
            parsed = self._parse_earnings_candidate(candidate)
            if parsed:
                return parsed
        return None

    def _parse_earnings_candidate(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, date):
            return datetime.combine(value, time(21, 0), tzinfo=timezone.utc)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for item in value:
                parsed = self._parse_earnings_candidate(item)
                if parsed:
                    return parsed
        return None

    def _classify_earnings_session(self, earnings_at: datetime) -> str:
        hour = earnings_at.astimezone(ZoneInfo("America/New_York")).hour
        if hour < 9:
            return "pre-market"
        if hour >= 16:
            return "after-hours"
        return "intraday"

    def _region_from_country(self, country: str | None) -> str:
        value = (country or "").lower()
        if any(term in value for term in ["germany", "france", "united kingdom", "uk", "italy", "europe"]):
            return "europe"
        if any(term in value for term in ["china", "japan", "india", "hong kong", "taiwan", "south korea"]):
            return "asia"
        if value:
            return "usa"
        return "global"

    def _find_asset(self, assets: List[Dict[str, Any]], ticker: str) -> Dict[str, Any] | None:
        return next((asset for asset in assets if asset.get("ticker") == ticker), None)
