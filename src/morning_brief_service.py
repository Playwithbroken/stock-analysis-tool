"""
Morning brief service.

Builds a market-opening brief across Asia, Europe, and the US using public
market data, best-effort event classification, and watchlist-aware calendars.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Sequence

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
        event_layer = self._build_event_layer(top_news)
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
            "event_layer": event_layer,
            "economic_calendar": economic_calendar,
            "earnings_calendar": earnings_calendar,
            "opening_timeline": opening_timeline,
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
                classification = self._classify_news_signal(text)
                items.append(
                    {
                        "ticker": ticker,
                        "title": title,
                        "publisher": item.get("publisher"),
                        "link": item.get("link"),
                        "impact": classification["impact"],
                        "region": classification["region"],
                        "event_type": classification["event_type"],
                        "severity": classification["severity"],
                    }
                )
        items.sort(
            key=lambda item: (
                0 if item["impact"] == "high" else 1 if item["impact"] == "medium" else 2,
                0 if item.get("severity") == "critical" else 1 if item.get("severity") == "elevated" else 2,
                item["region"],
            )
        )
        return items[:12]

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
                    "ticker": item.get("ticker"),
                }
            )
        return layer[:8]

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
                        "summary": news.get("title"),
                    }
                )
        brief["watchlist_impact"] = impact[:8]
        return brief

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
