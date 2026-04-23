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
import json
import os
import re

import pandas as pd
import requests

from src.data_fetcher import DataFetcher
from src.storage import PortfolioManager
from src.social_intelligence_service import SocialIntelligenceService
from src.trading_signals_service import TradingSignalsService

try:
    import feedparser  # type: ignore
    _HAS_FEEDPARSER = True
except ImportError:
    _HAS_FEEDPARSER = False


class MorningBriefService:
    _cache: Dict[str, Any] | None = None
    _cache_time: datetime | None = None
    _ttl_seconds = 60 * 10
    _snapshot_path = os.path.join("data", "morning_brief_snapshot.json")

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
    NEWS_TICKERS = [
        "SPY", "QQQ", "GLD", "TLT", "XLE",
        "NVDA", "AAPL", "MSFT", "TSLA", "AMZN", "META", "GOOGL",
        "TTWO", "BMW.DE",
    ]
    FUNDAMENTAL_EXCLUDED_TICKERS = {"SPY", "QQQ", "GLD", "TLT", "XLE", "XLK", "XLY", "XLV", "XLU", "XLRE", "IWM"}
    PRODUCT_CATALYST_ALIASES = {
        "NVDA": ["nvidia", "geforce", "rtx", "blackwell", "gpu", "graphics card", "ai chip"],
        "AAPL": ["apple", "iphone", "ipad", "macbook", "vision pro", "ios"],
        "TTWO": ["take-two", "take two", "rockstar", "gta", "grand theft auto", "gta 6", "gta vi"],
        "BMW.DE": ["bmw", "mini cooper", "rolls-royce", "neue klasse"],
        "TSLA": ["tesla", "model y", "model 3", "cybertruck", "robotaxi"],
        "MSFT": ["microsoft", "xbox", "copilot", "windows", "azure"],
        "AMZN": ["amazon", "aws", "kindle", "alexa", "anthropic"],
        "META": ["meta", "quest", "ray-ban", "instagram", "whatsapp", "facebook"],
        "GOOGL": ["google", "android", "pixel", "gemini", "waymo", "youtube"],
    }
    MARKET_MOVER_UNIVERSE = [
        "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "AVGO", "ADBE", "COST",
        "PEP", "NFLX", "AMD", "TMUS", "INTC", "CSCO", "CMCSA", "AMAT", "QCOM", "ISRG",
        "MU", "TXN", "AMGN", "HON", "INTU", "BKNG", "SBUX", "VRTX", "MDLZ", "REGN",
        "PANW", "SNPS", "ASML", "LRCX", "ADI", "MELI", "CDNS", "KLAC", "PDD", "PYPL",
        "SOFI", "HOOD", "PLTR", "ARM", "SMCI", "RKLB", "LUNR", "OKLO", "UPST", "PATH",
        "UNH", "DHR", "GE", "RTX", "ISRG", "PM", "CRM", "ORCL", "BLK", "PEP", "ABT",
        "BMW.DE", "TTWO",
    ]

    # Free RSS feeds for real-time headlines
    RSS_FEEDS = [
        ("https://feeds.reuters.com/reuters/businessNews", "Reuters"),
        ("https://feeds.reuters.com/reuters/technologyNews", "Reuters"),
        ("https://feeds.reuters.com/news/economy", "Reuters"),
        ("https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001147", "CNBC"),
        ("https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135", "CNBC"),
        ("https://feeds.marketwatch.com/marketwatch/topstories/", "MarketWatch"),
        ("https://feeds.marketwatch.com/marketwatch/marketpulse/", "MarketWatch"),
        ("https://finance.yahoo.com/news/rssindex", "Yahoo Finance"),
        ("https://www.investing.com/rss/news.rss", "Investing.com"),
    ]
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
    GEO_LOOKUP: List[Dict[str, Any]] = [
        {"terms": ["budapest", "hungary"], "place": "Budapest", "country": "Hungary", "lat": 47.4979, "lon": 19.0402},
        {"terms": ["kyiv", "ukraine"], "place": "Kyiv", "country": "Ukraine", "lat": 50.4501, "lon": 30.5234},
        {"terms": ["warsaw", "poland"], "place": "Warsaw", "country": "Poland", "lat": 52.2297, "lon": 21.0122},
        {"terms": ["berlin", "germany"], "place": "Berlin", "country": "Germany", "lat": 52.5200, "lon": 13.4050},
        {"terms": ["paris", "france"], "place": "Paris", "country": "France", "lat": 48.8566, "lon": 2.3522},
        {"terms": ["london", "britain", "united kingdom"], "place": "London", "country": "United Kingdom", "lat": 51.5074, "lon": -0.1278},
        {"terms": ["rome", "italy"], "place": "Rome", "country": "Italy", "lat": 41.9028, "lon": 12.4964},
        {"terms": ["ankara", "turkey"], "place": "Ankara", "country": "Turkey", "lat": 39.9334, "lon": 32.8597},
        {"terms": ["moscow", "russia"], "place": "Moscow", "country": "Russia", "lat": 55.7558, "lon": 37.6173},
        {"terms": ["beirut", "lebanon"], "place": "Beirut", "country": "Lebanon", "lat": 33.8938, "lon": 35.5018},
        {"terms": ["tehran", "iran"], "place": "Tehran", "country": "Iran", "lat": 35.6892, "lon": 51.3890},
        {"terms": ["jerusalem", "israel", "gaza"], "place": "Jerusalem", "country": "Israel", "lat": 31.7683, "lon": 35.2137},
        {"terms": ["riyadh", "saudi"], "place": "Riyadh", "country": "Saudi Arabia", "lat": 24.7136, "lon": 46.6753},
        {"terms": ["opec", "brent", "crude", "oil", "gulf", "middle east", "red sea"], "place": "Gulf Region", "country": "Middle East", "lat": 26.0000, "lon": 50.5000},
        {"terms": ["cairo", "egypt"], "place": "Cairo", "country": "Egypt", "lat": 30.0444, "lon": 31.2357},
        {"terms": ["mumbai", "delhi", "india"], "place": "Mumbai", "country": "India", "lat": 19.0760, "lon": 72.8777},
        {"terms": ["beijing", "shanghai", "china"], "place": "Beijing", "country": "China", "lat": 39.9042, "lon": 116.4074},
        {"terms": ["taipei", "taiwan"], "place": "Taipei", "country": "Taiwan", "lat": 25.0330, "lon": 121.5654},
        {"terms": ["tokyo", "japan"], "place": "Tokyo", "country": "Japan", "lat": 35.6762, "lon": 139.6503},
        {"terms": ["hong kong"], "place": "Hong Kong", "country": "Hong Kong", "lat": 22.3193, "lon": 114.1694},
        {"terms": ["seoul", "korea"], "place": "Seoul", "country": "South Korea", "lat": 37.5665, "lon": 126.9780},
        {"terms": ["sydney", "australia"], "place": "Sydney", "country": "Australia", "lat": -33.8688, "lon": 151.2093},
        {"terms": ["sao paulo", "brazil"], "place": "Sao Paulo", "country": "Brazil", "lat": -23.5505, "lon": -46.6333},
        {"terms": ["mexico city", "mexico"], "place": "Mexico City", "country": "Mexico", "lat": 19.4326, "lon": -99.1332},
        {"terms": ["canada", "toronto"], "place": "Toronto", "country": "Canada", "lat": 43.6532, "lon": -79.3832},
        {"terms": ["washington", "new york", "wall street", "federal reserve", "usa", "u.s."], "place": "New York", "country": "United States", "lat": 40.7128, "lon": -74.0060},
        {"terms": ["california", "silicon valley", "san francisco"], "place": "San Francisco", "country": "United States", "lat": 37.7749, "lon": -122.4194},
        {"terms": ["johannesburg", "south africa"], "place": "Johannesburg", "country": "South Africa", "lat": -26.2041, "lon": 28.0473},
        {"terms": ["lagos", "nigeria"], "place": "Lagos", "country": "Nigeria", "lat": 6.5244, "lon": 3.3792},
    ]
    _portfolio_manager: PortfolioManager | None = None
    _holding_profile_cache: Dict[str, Dict[str, Any]] = {}
    _social_service: SocialIntelligenceService = SocialIntelligenceService()
    _signals_service: TradingSignalsService = TradingSignalsService()
    _event_ping_cooldown: Dict[str, datetime] = {}
    _event_ping_cooldown_seconds = 60 * 30
    _market_movers_cache: tuple[Dict[str, Any], datetime] | None = None
    _market_movers_ttl_seconds = 60 * 15
    _kalshi_enabled = str(os.getenv("KALSHI_ENABLED", "false")).strip().lower() in {"1", "true", "yes", "on"}

    def _persist_snapshot(self, brief: Dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(self._snapshot_path), exist_ok=True)
            with open(self._snapshot_path, "w", encoding="utf-8") as fh:
                json.dump(brief, fh, ensure_ascii=True)
        except Exception:
            pass

    def _load_persisted_snapshot(self) -> Dict[str, Any] | None:
        try:
            if not os.path.exists(self._snapshot_path):
                return None
            with open(self._snapshot_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    def get_cached_or_last_brief(
        self,
        watchlist_snapshot: Dict[str, Any] | None = None,
    ) -> Dict[str, Any] | None:
        if self._cache is not None:
            return self._merge_watchlist_impact(dict(self._cache), watchlist_snapshot)
        persisted = self._load_persisted_snapshot()
        if persisted is not None:
            return self._merge_watchlist_impact(dict(persisted), watchlist_snapshot)
        return None

    def build_empty_brief(self, reason: str = "degraded") -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        empty_regions = {
            "asia": {"label": "Asia", "tone": "mixed", "avg_change_1d": 0.0, "assets": []},
            "europe": {"label": "Europe", "tone": "mixed", "avg_change_1d": 0.0, "assets": []},
            "usa": {"label": "USA", "tone": "mixed", "avg_change_1d": 0.0, "assets": []},
        }
        return {
            "generated_at": now,
            "macro_score": 0,
            "macro_regime": "mixed",
            "opening_bias": "Data loading fallback active",
            "headline": "Morning brief temporarily degraded",
            "summary_points": [
                "Data providers are currently slow.",
                "Retry in a few moments for full event depth.",
            ],
            "regions": empty_regions,
            "macro_assets": [],
            "top_news": [],
            "crowd_signals": [],
            "social_signals": [],
            "source_policy": {
                "trusted_publishers": sorted(self.TRUSTED_PUBLISHERS),
                "allowed_domains": sorted(self.ALLOWED_DOMAINS),
                "excluded_sources": sorted(self.EXCLUDED_SOURCE_TERMS),
                "crowd_sources": sorted(self.CROWD_SOURCE_TERMS),
                "note": "Fallback response due to upstream timeout.",
            },
            "event_layer": [],
            "event_pings": [],
            "product_catalysts": [],
            "market_movers": {"gainers": [], "losers": []},
            "contrarian_signals": [],
            "economic_calendar": [],
            "earnings_calendar": [],
            "broad_earnings": [],
            "earnings_results": [],
            "opening_timeline": [],
            "action_board": [],
            "trade_setups": [],
            "trade_setups_status": "insufficient_signal",
            "portfolio_brain": [],
            "watchlist_impact": [],
            "reddit_posts": [],
            "stocktwits": [],
            "polymarket": [],
            "prediction_signals": [],
            "prediction_markets": {
                "kalshi_enabled": self._kalshi_enabled,
                "status": "data_delayed",
            },
            "google_news_extra": [],
            "trading_edge": {},
            "quality": {
                "status": "partial",
                "score": 0,
                "passed": 0,
                "total": 0,
                "age_minutes": None,
                "missing": ["upstream_data"],
                "checks": [],
                "fallback": reason,
            },
        }

    def get_trading_edge(self, watchlist_snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Heavy trading-signals payload (squeeze, insider, options, etc.).

        Built lazily so the main brief stays fast. The underlying service
        caches each component (10min – 6h) so repeated calls are cheap.
        """
        watchlist_tickers = [
            (item.get("value") or "").upper()
            for item in (watchlist_snapshot or {}).get("items", [])
            if item.get("kind") == "ticker" and item.get("value")
        ]
        try:
            return self._signals_service.get_full_edge_pack(
                (watchlist_tickers or []) + self.NEWS_TICKERS[:6]
            )
        except Exception:
            return {}

    def get_brief(self, watchlist_snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        if (
            self._cache is not None
            and self._cache_time is not None
            and (now - self._cache_time).total_seconds() < self._ttl_seconds
        ):
            return self._merge_watchlist_impact(dict(self._cache), watchlist_snapshot)

        # Include user watchlist tickers in news fetch
        watchlist_tickers = [
            (item.get("value") or "").upper()
            for item in (watchlist_snapshot or {}).get("items", [])
            if item.get("kind") == "ticker" and item.get("value")
        ]

        asia = self._collect_region(self.ASIA, "Asia")
        europe = self._collect_region(self.EUROPE, "Europe")
        usa = self._collect_region(self.USA, "USA")
        macro = self._collect_assets(self.MACRO)
        top_news = self._collect_news(extra_tickers=watchlist_tickers)
        crowd_news = self._collect_crowd_news()
        social_news = self._collect_social_news()

        # Social intelligence — Reddit, Stocktwits, Polymarket, Google News, broad earnings
        try:
            reddit_posts = self._social_service.get_reddit_sentiment(watchlist_tickers or [])
        except Exception:
            reddit_posts = []
        try:
            stocktwits_data = self._social_service.get_stocktwits_sentiment(
                (watchlist_tickers or []) + self.NEWS_TICKERS[:4]
            )
        except Exception:
            stocktwits_data = []
        try:
            polymarket_events = self._social_service.get_polymarket_events()
        except Exception:
            polymarket_events = []
        try:
            google_news_extra = self._social_service.get_google_news(
                (watchlist_tickers or [])[:4] + ["S&P 500", "Fed interest rates", "market today"]
            )
        except Exception:
            google_news_extra = []
        try:
            broad_earnings = self._social_service.get_broad_earnings_calendar(
                extra_tickers=watchlist_tickers or [], days_ahead=14
            )
        except Exception:
            broad_earnings = []
        # NOTE: trading_edge is intentionally NOT computed here — it is heavy
        # (yfinance options chains, insider scrape, sector ETFs) and would
        # block the brief response. Frontend fetches /api/market/trading-edge
        # separately; scheduled Telegram briefs build it just-in-time below.
        trading_edge: Dict[str, Any] = {}

        event_layer = self._build_event_layer(top_news)
        event_pings = self._build_event_pings(event_layer)
        product_catalysts = self._build_product_catalysts(top_news)
        market_movers = self._collect_market_movers(watchlist_tickers)
        contrarian_signals = self._build_contrarian_signals(top_news, watchlist_snapshot)
        earnings_calendar = self._collect_earnings_calendar(watchlist_snapshot)
        earnings_results = self._collect_earnings_results(watchlist_snapshot, earnings_calendar, broad_earnings)
        economic_calendar = self._build_economic_calendar(event_layer)
        opening_timeline = self._build_opening_timeline(
            [asia, europe, usa],
            top_news,
            event_layer,
            economic_calendar,
            earnings_calendar,
        )
        narrative = self._build_narrative(asia, europe, usa, macro, event_layer)
        action_board = self._build_action_board(top_news, event_layer, watchlist_snapshot, narrative["macro_regime"])
        trade_setups = self._build_trade_setups(action_board, top_news, market_movers)
        prediction_signals = self._build_prediction_signals(polymarket_events)

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
            "event_pings": event_pings,
            "product_catalysts": product_catalysts,
            "market_movers": market_movers,
            "contrarian_signals": contrarian_signals,
            "economic_calendar": economic_calendar,
            "earnings_calendar": earnings_calendar,
            "broad_earnings": broad_earnings,
            "earnings_results": earnings_results,
            "opening_timeline": opening_timeline,
            "action_board": action_board,
            "trade_setups": trade_setups,
            "trade_setups_status": "ready" if trade_setups else "insufficient_signal",
            "portfolio_brain": self._build_portfolio_brain(action_board),
            "watchlist_impact": [],
            # Social intelligence
            "reddit_posts": reddit_posts[:10],
            "stocktwits": stocktwits_data,
            "polymarket": polymarket_events[:8],
            "prediction_signals": prediction_signals,
            "prediction_markets": {
                "kalshi_enabled": self._kalshi_enabled,
                "status": "live" if prediction_signals else "data_delayed",
            },
            "google_news_extra": google_news_extra[:8],
            "trading_edge": trading_edge,
        }
        brief["quality"] = self._build_quality_report(brief)
        self._cache = brief
        self._cache_time = now
        self._persist_snapshot(brief)
        return self._merge_watchlist_impact(dict(brief), watchlist_snapshot)

    def get_brief_fast(self, watchlist_snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Fast brief path for API/dashboard rendering under strict latency budget."""
        now = datetime.now(timezone.utc)
        if (
            self._cache is not None
            and self._cache_time is not None
            and (now - self._cache_time).total_seconds() < self._ttl_seconds
        ):
            return self._merge_watchlist_impact(dict(self._cache), watchlist_snapshot)

        watchlist_tickers = [
            (item.get("value") or "").upper()
            for item in (watchlist_snapshot or {}).get("items", [])
            if item.get("kind") == "ticker" and item.get("value")
        ]

        asia = self._collect_region(self.ASIA, "Asia", fast=True)
        europe = self._collect_region(self.EUROPE, "Europe", fast=True)
        usa = self._collect_region(self.USA, "USA", fast=True)
        macro = self._collect_assets(self.MACRO, fast=True)
        top_news = self._collect_news(extra_tickers=watchlist_tickers, fast=True)
        event_layer = self._build_event_layer(top_news)
        event_pings = self._build_event_pings(event_layer)
        economic_calendar = self._build_economic_calendar(event_layer)
        opening_timeline = self._build_opening_timeline(
            [asia, europe, usa],
            top_news,
            event_layer,
            economic_calendar,
            [],
        )
        narrative = self._build_narrative(asia, europe, usa, macro, event_layer)
        action_board = self._build_action_board(top_news, event_layer, watchlist_snapshot, narrative["macro_regime"])
        trade_setups = self._build_trade_setups(action_board, top_news, {"gainers": [], "losers": []})

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
            "crowd_signals": [],
            "social_signals": [],
            "source_policy": {
                "trusted_publishers": sorted(self.TRUSTED_PUBLISHERS),
                "allowed_domains": sorted(self.ALLOWED_DOMAINS),
                "excluded_sources": sorted(self.EXCLUDED_SOURCE_TERMS),
                "crowd_sources": sorted(self.CROWD_SOURCE_TERMS),
                "note": "Fast brief mode: trusted sources prioritised, deep social layers deferred.",
            },
            "event_layer": event_layer,
            "event_pings": event_pings,
            "product_catalysts": self._build_product_catalysts(top_news),
            "market_movers": {"gainers": [], "losers": []},
            "contrarian_signals": self._build_contrarian_signals(top_news, watchlist_snapshot),
            "economic_calendar": economic_calendar,
            "earnings_calendar": [],
            "broad_earnings": [],
            "earnings_results": [],
            "opening_timeline": opening_timeline,
            "action_board": action_board,
            "trade_setups": trade_setups,
            "trade_setups_status": "ready" if trade_setups else "insufficient_signal",
            "portfolio_brain": self._build_portfolio_brain(action_board),
            "watchlist_impact": [],
            "reddit_posts": [],
            "stocktwits": [],
            "polymarket": [],
            "prediction_signals": [],
            "prediction_markets": {
                "kalshi_enabled": self._kalshi_enabled,
                "status": "data_delayed",
            },
            "google_news_extra": [],
            "trading_edge": {},
        }
        brief["quality"] = self._build_quality_report(brief)
        brief["quality"]["mode"] = "fast"
        self._cache = brief
        self._cache_time = now
        self._persist_snapshot(brief)
        return self._merge_watchlist_impact(dict(brief), watchlist_snapshot)

    def _build_quality_report(self, brief: Dict[str, Any]) -> Dict[str, Any]:
        now_utc = datetime.now(timezone.utc)
        generated_at_raw = brief.get("generated_at")
        generated_at = None
        if generated_at_raw:
            try:
                generated_at = datetime.fromisoformat(str(generated_at_raw).replace("Z", "+00:00"))
            except Exception:
                generated_at = None
        age_minutes = (
            int((now_utc - generated_at).total_seconds() // 60)
            if generated_at is not None
            else None
        )

        checks = [
            {
                "key": "regions_complete",
                "label": "Regions data",
                "ok": bool(brief.get("regions", {}).get("asia") and brief.get("regions", {}).get("europe") and brief.get("regions", {}).get("usa")),
            },
            {
                "key": "event_layer_depth",
                "label": "Event layer depth",
                "ok": len(brief.get("event_layer") or []) >= 5,
            },
            {
                "key": "trusted_news_depth",
                "label": "Trusted news depth",
                "ok": len(brief.get("top_news") or []) >= 6,
            },
            {
                "key": "opening_timeline",
                "label": "Opening timeline",
                "ok": len(brief.get("opening_timeline") or []) >= 5,
            },
            {
                "key": "action_board_depth",
                "label": "Action board",
                "ok": len(brief.get("action_board") or []) >= 4,
            },
            {
                "key": "trade_setups",
                "label": "Trade setups",
                "ok": len(brief.get("trade_setups") or []) >= 3,
            },
            {
                "key": "freshness",
                "label": "Freshness",
                "ok": age_minutes is not None and age_minutes <= 20,
            },
        ]

        passed = sum(1 for check in checks if check["ok"])
        total = len(checks)
        score = round((passed / total) * 100) if total else 0
        missing = [check["label"] for check in checks if not check["ok"]]
        status = "ready" if score >= 84 and not missing else "partial"
        return {
            "status": status,
            "score": score,
            "passed": passed,
            "total": total,
            "age_minutes": age_minutes,
            "missing": missing,
            "checks": checks,
        }

    def _collect_region(self, tickers: Sequence[tuple[str, str]], label: str, fast: bool = False) -> Dict[str, Any]:
        assets = self._collect_assets(tickers, fast=fast)
        changes = [item["change_1d"] for item in assets if item.get("change_1d") is not None]
        avg_change = sum(changes) / len(changes) if changes else 0
        tone = "risk-on" if avg_change > 0.45 else "risk-off" if avg_change < -0.45 else "mixed"
        return {
            "label": label,
            "tone": tone,
            "avg_change_1d": avg_change,
            "assets": assets,
        }

    def _collect_assets(self, tickers: Sequence[tuple[str, str]], fast: bool = False) -> List[Dict[str, Any]]:
        assets = []
        for ticker, label in tickers:
            fetcher = DataFetcher(ticker)
            price = fetcher.get_price_data_fast() if fast else fetcher.get_price_data()
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

    def _collect_rss_news(self) -> List[Dict[str, Any]]:
        """Fetch fresh headlines from free RSS feeds (Reuters, CNBC, MarketWatch, etc.)"""
        if not _HAS_FEEDPARSER:
            return []
        items: List[Dict[str, Any]] = []
        seen_titles: set = set()
        for feed_url, feed_publisher in self.RSS_FEEDS:
            try:
                parsed = feedparser.parse(feed_url, request_headers={"User-Agent": "Mozilla/5.0"})
                for entry in (parsed.entries or [])[:5]:
                    title = (entry.get("title") or "").strip()
                    link = entry.get("link") or ""
                    if not title or title in seen_titles:
                        continue
                    # Filter out very old entries (older than 18 hours)
                    published = entry.get("published_parsed")
                    if published:
                        import time as _time
                        age_hours = (_time.time() - _time.mktime(published)) / 3600
                        if age_hours > 18:
                            continue
                        published_at = datetime.fromtimestamp(_time.mktime(published), timezone.utc).isoformat()
                    else:
                        age_hours = None
                        published_at = None
                    seen_titles.add(title)
                    text = title.lower()
                    source_meta = self._source_meta(feed_publisher, link)
                    classification = self._classify_news_signal(text)
                    product_catalyst = self._classify_product_catalyst(text)
                    if source_meta["exclude"]:
                        continue
                    if self._is_high_risk_unverified_headline(title, source_meta):
                        continue
                    # Try to associate with a known ticker
                    ticker = None
                    for t in self.NEWS_TICKERS:
                        if t.lower() in text:
                            ticker = t
                            break
                    if not ticker and product_catalyst:
                        ticker = product_catalyst.get("ticker")
                    items.append(
                        {
                            "ticker": ticker,
                            "title": title,
                            "publisher": feed_publisher,
                            "link": link,
                            "source_domain": source_meta["domain"],
                            "source_type": source_meta["source_type"],
                            "source_quality": source_meta["quality"],
                            "is_trusted_source": source_meta["trusted"],
                            "published_at": published_at,
                            "age_hours": round(age_hours, 2) if isinstance(age_hours, (int, float)) else None,
                            "impact": classification["impact"],
                            "region": classification["region"],
                            "event_type": classification["event_type"],
                            "severity": classification["severity"],
                            "product_catalyst": product_catalyst,
                            "source": "rss",
                        }
                    )
            except Exception:
                continue
        return items

    def _collect_news(self, extra_tickers: List[str] | None = None, fast: bool = False) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        seen_titles: set = set()

        # 1. Collect from RSS feeds (real-time, highest priority)
        rss_items = self._collect_rss_news()
        for item in rss_items:
            title = item.get("title") or ""
            identity = self._news_identity(title)
            if title and identity not in seen_titles:
                seen_titles.add(identity)
                items.append(item)

        # 2. Collect from yfinance per ticker (includes user watchlist tickers)
        all_tickers = list(self.NEWS_TICKERS[:4] if fast else self.NEWS_TICKERS)
        if extra_tickers:
            for t in extra_tickers:
                if t and t not in all_tickers:
                    all_tickers.append(t)
        if fast:
            all_tickers = all_tickers[:6]

        per_ticker_limit = 2 if fast else 3
        for ticker in all_tickers:
            news = DataFetcher(ticker).get_news()
            for item in news[:per_ticker_limit]:
                title = item.get("title") or ""
                identity = self._news_identity(title)
                if not title or identity in seen_titles:
                    continue
                text = title.lower()
                publisher = item.get("publisher") or ""
                link = item.get("link")
                source_meta = self._source_meta(publisher, link)
                classification = self._classify_news_signal(text)
                product_catalyst = self._classify_product_catalyst(text)
                if source_meta["exclude"]:
                    continue
                if self._is_high_risk_unverified_headline(title, source_meta):
                    continue
                age_hours, published_at = self._news_age(item.get("published_at") or item.get("timestamp"))
                if age_hours is not None and age_hours > 30:
                    continue
                seen_titles.add(identity)
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
                        "published_at": published_at,
                        "age_hours": round(age_hours, 2) if isinstance(age_hours, (int, float)) else None,
                        "impact": classification["impact"],
                        "region": classification["region"],
                        "event_type": classification["event_type"],
                        "severity": classification["severity"],
                        "product_catalyst": product_catalyst,
                    }
                )

        trusted_items = [
            item for item in items
            if item.get("is_trusted_source") and self._news_relevance_score(item) > 0
        ]
        trusted_items.sort(
            key=lambda item: (
                -self._news_relevance_score(item),
                0 if item.get("source_quality") == "tier_1" else 1,
                0 if item["impact"] == "high" else 1 if item["impact"] == "medium" else 2,
                0 if item.get("severity") == "critical" else 1 if item.get("severity") == "elevated" else 2,
                item["region"],
            )
        )
        return trusted_items[:16]

    def _news_identity(self, title: str) -> str:
        text = re.sub(r"[^a-z0-9 ]+", " ", str(title or "").lower())
        stop = {"the", "a", "an", "to", "of", "and", "or", "for", "on", "in", "with", "as", "at", "is"}
        tokens = [token for token in text.split() if token not in stop]
        return " ".join(tokens[:12])

    def _news_age(self, value: Any) -> tuple[float | None, str | None]:
        if not value:
            return None, None
        try:
            if isinstance(value, (int, float)):
                dt = datetime.fromtimestamp(value, timezone.utc)
            else:
                raw = str(value).strip().replace("Z", "+00:00")
                dt = datetime.fromisoformat(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600
            return max(0.0, age_hours), dt.astimezone(timezone.utc).isoformat()
        except Exception:
            return None, str(value)

    def _is_high_risk_unverified_headline(self, title: str, source_meta: Dict[str, Any]) -> bool:
        text = str(title or "").lower()
        high_risk_terms = [
            "ceo stepping down",
            "ceo to step down",
            "leaving as ceo",
            "replacing",
            "succeeded by",
            "bankruptcy",
            "files for bankruptcy",
            "takeover",
            "acquisition talks",
        ]
        if not any(term in text for term in high_risk_terms):
            return False
        return source_meta.get("quality") != "tier_1"

    def _news_relevance_score(self, item: Dict[str, Any]) -> int:
        title = str(item.get("title") or "").lower()
        ticker = str(item.get("ticker") or "").upper()
        event_type = str(item.get("event_type") or "").lower()
        publisher = str(item.get("publisher") or "").lower()
        source_quality = str(item.get("source_quality") or "").lower()
        score = 0
        if ticker:
            score += 3
        if event_type in {"conflict", "central_bank", "energy", "policy", "macro_data", "earnings", "product_catalyst"}:
            score += 4
        if any(term in title for term in [
            "fed", "rate", "yield", "inflation", "cpi", "ppi", "jobs", "payrolls",
            "earnings", "guidance", "upgrade", "downgrade", "oil", "opec", "war",
            "tariff", "sanction", "market", "stock", "futures", "nasdaq", "s&p",
            "dow", "dollar", "gold", "bitcoin", "crypto", "launch", "unveil", "delay",
            "postpone", "iphone", "gpu", "gta", "model", "product", "preorder",
        ]):
            score += 3
        if any(term in title for term in [
            "retire", "retirees", "inherit", "estate", "adviser", "advisor",
            "irs", "tax", "401", "credit card", "mortgage", "personal finance",
            "student loan",
        ]):
            score -= 6
        if "video" in publisher:
            score -= 2
        rumor_terms = [
            "stepping down",
            "steps down",
            "replacing",
            "successor",
            "names new ceo",
            "named ceo",
            "leaving",
        ]
        if "ceo" in title and any(term in title for term in rumor_terms) and source_quality != "tier_1":
            score -= 8
        return score

    def _build_event_layer(self, news: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        layer = []
        for item in news:
            event_type = item.get("event_type") or "macro"
            severity = item.get("severity") or "normal"
            if event_type == "macro" and item.get("impact") == "low":
                continue
            geo = self._resolve_event_geo(item)
            impact = item.get("impact") or "low"
            map_priority = 100
            if impact == "high":
                map_priority -= 40
            elif impact == "medium":
                map_priority -= 20
            if severity == "critical":
                map_priority -= 30
            elif severity == "elevated":
                map_priority -= 15

            layer.append(
                {
                    "title": item.get("title"),
                    "link": item.get("link"),
                    "region": item.get("region"),
                    "impact": impact,
                    "event_type": event_type,
                    "severity": severity,
                    "publisher": item.get("publisher"),
                    "source_quality": item.get("source_quality"),
                    "ticker": item.get("ticker"),
                    "product_catalyst": item.get("product_catalyst"),
                    "geo": geo,
                    "map_priority": max(1, map_priority),
                    "event_intelligence": self._build_event_intelligence(
                        event_type=event_type,
                        impact=impact,
                        severity=severity,
                        source_quality=item.get("source_quality") or "tier_2",
                        ticker=item.get("ticker"),
                    ),
                }
            )
        return layer[:8]

    def _build_event_pings(self, event_layer: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        dedup: Dict[tuple[str, str], Dict[str, Any]] = {}
        for event in event_layer:
            event_type = str(event.get("event_type") or "macro").lower()
            geo = event.get("geo") if isinstance(event.get("geo"), dict) else {}
            place = str(geo.get("place") or event.get("region") or "Global")
            key = (event_type, place.lower())
            map_priority = int(event.get("map_priority") or 100)
            if key not in dedup or map_priority < int(dedup[key].get("map_priority") or 100):
                dedup[key] = event

        pings: List[Dict[str, Any]] = []
        for event in sorted(dedup.values(), key=lambda item: int(item.get("map_priority") or 100)):
            event_type = str(event.get("event_type") or "macro").lower()
            geo = event.get("geo") if isinstance(event.get("geo"), dict) else {}
            place = str(geo.get("place") or event.get("region") or "Global")
            cooldown_key = f"{event_type}:{place.lower()}"
            last_seen = self._event_ping_cooldown.get(cooldown_key)
            if last_seen and (now - last_seen).total_seconds() < self._event_ping_cooldown_seconds:
                continue
            self._event_ping_cooldown[cooldown_key] = now

            event_intelligence = event.get("event_intelligence") or {}
            affected_assets = list(event_intelligence.get("affected_assets") or [])
            base_symbols = [event.get("ticker")] + affected_assets
            symbols = list(dict.fromkeys([symbol for symbol in base_symbols if symbol]))[:4]
            trade_action = str(event_intelligence.get("action") or "watch")
            baseline_scenario = (
                event_intelligence.get("why_now")
                or event.get("thesis")
                or event.get("title")
                or "Macro catalyst active."
            )
            hedge_idea = (
                (event.get("portfolio_exposure") or {}).get("hedge_candidates", [{}])[0].get("ticker")
                if isinstance(event.get("portfolio_exposure"), dict)
                else None
            )
            if not hedge_idea:
                if event_type in {"conflict", "energy"}:
                    hedge_idea = "GLD / XLE"
                elif event_type in {"central_bank", "policy"}:
                    hedge_idea = "TLT / cash buffer"
                else:
                    hedge_idea = "Reduce gross exposure"
            pings.append(
                {
                    "id": f"{cooldown_key}:{int(now.timestamp())}",
                    "type": event_type,
                    "severity": event.get("severity") or "normal",
                    "region": event.get("region") or "global",
                    "symbols": symbols,
                    "started_at": now.isoformat(),
                    "confidence": int(event_intelligence.get("confidence_score") or 0),
                    "title": event.get("title"),
                    "trade_impact": {
                        "action": trade_action,
                        "baseline_scenario": baseline_scenario,
                        "symbols": symbols,
                        "trigger": event_intelligence.get("trigger"),
                        "invalidation": event_intelligence.get("invalidation"),
                        "window": event_intelligence.get("execution_window") or "open+60m",
                        "hedge_idea": hedge_idea,
                    },
                }
            )
        return pings[:8]

    def _build_product_catalysts(self, news: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        catalysts: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item in news:
            product = item.get("product_catalyst")
            if not product:
                continue
            ticker = str(product.get("ticker") or item.get("ticker") or "").upper()
            title = item.get("title") or ""
            key = f"{ticker}:{title.lower()[:80]}"
            if not ticker or key in seen:
                continue
            seen.add(key)
            catalyst_type = product.get("catalyst_type") or "product_news"
            catalysts.append(
                {
                    "ticker": ticker,
                    "title": title,
                    "theme": product.get("theme") or ticker,
                    "catalyst_type": catalyst_type,
                    "direction_hint": product.get("direction_hint") or "watch",
                    "publisher": item.get("publisher"),
                    "link": item.get("link"),
                    "impact": item.get("impact") or "medium",
                    "confidence": 78 if item.get("source_quality") == "tier_1" else 64,
                    "trigger": "Official confirmation plus price/volume follow-through.",
                    "invalidation": "Rumour fades, company denies it, or first impulse fully reverses.",
                }
            )
        return catalysts[:6]

    def _collect_market_movers(self, extra_tickers: List[str] | None = None) -> Dict[str, List[Dict[str, Any]]]:
        now = datetime.now(timezone.utc)
        if (
            self._market_movers_cache is not None
            and (now - self._market_movers_cache[1]).total_seconds() < self._market_movers_ttl_seconds
        ):
            return self._market_movers_cache[0]

        symbols = list(dict.fromkeys([*(extra_tickers or []), *self.MARKET_MOVER_UNIVERSE]))
        rows: List[Dict[str, Any]] = []
        for symbol in symbols[:48]:
            normalized = (symbol or "").upper().strip()
            if not normalized or normalized.startswith("^") or normalized.endswith("=F") or normalized.endswith("-USD"):
                continue
            try:
                fetcher = DataFetcher(normalized)
                info = fetcher.info or {}
                price = fetcher.get_price_data()
                change_1d = None
                try:
                    hist = fetcher.stock.history(period="7d", interval="1d")
                    if hist is not None and not hist.empty and len(hist["Close"]) >= 2:
                        last_close = float(hist["Close"].iloc[-1])
                        prev_close = float(hist["Close"].iloc[-2])
                        if prev_close:
                            change_1d = ((last_close / prev_close) - 1.0) * 100.0
                except Exception:
                    change_1d = None

                change_1w = price.get("change_1w")
                if change_1d is None and change_1w is None:
                    continue
                rows.append(
                    {
                        "ticker": normalized,
                        "name": info.get("shortName") or info.get("longName") or normalized,
                        "price": price.get("current_price"),
                        "change_1d": change_1d,
                        "change_1w": change_1w,
                        "change_1m": price.get("change_1m"),
                        "market_cap": info.get("marketCap"),
                        "sector": info.get("sector"),
                    }
                )
            except Exception:
                continue

        def move_value(item: Dict[str, Any]) -> float:
            value = item.get("change_1d")
            if isinstance(value, (int, float)):
                return float(value)
            value = item.get("change_1w")
            return float(value) if isinstance(value, (int, float)) else 0.0

        gainers = sorted([row for row in rows if move_value(row) > 0], key=move_value, reverse=True)[:8]
        losers = sorted([row for row in rows if move_value(row) < 0], key=move_value)[:8]
        payload = {"gainers": gainers, "losers": losers}
        self._market_movers_cache = (payload, now)
        return payload

    def _build_trade_setups(
        self,
        action_board: List[Dict[str, Any]],
        news: List[Dict[str, Any]],
        market_movers: Dict[str, List[Dict[str, Any]]] | None = None,
    ) -> List[Dict[str, Any]]:
        source_lookup: Dict[str, Dict[str, Any]] = {}
        for item in news:
            ticker = str(item.get("ticker") or "").upper()
            if ticker and ticker not in source_lookup:
                source_lookup[ticker] = item

        scored: List[Dict[str, Any]] = []
        for item in action_board:
            ticker = str(item.get("ticker") or "").upper()
            if not ticker:
                continue
            intelligence = item.get("event_intelligence") or {}
            source_item = source_lookup.get(ticker, {})
            impact_value = {"high": 1.0, "medium": 0.65, "low": 0.35}.get(str(item.get("impact") or "low"), 0.35)
            relevance = self._event_relevance_score(item)
            decay = str(intelligence.get("decay") or "active")
            recency = {"developing": 1.0, "active": 0.85, "fading": 0.55}.get(decay, 0.7)
            trust = {"tier_1": 1.0, "tier_2": 0.78, "crowd": 0.45, "excluded": 0.2}.get(
                str(source_item.get("source_quality") or "tier_2"),
                0.7,
            )
            confidence = int(intelligence.get("confidence_score") or 55)
            score = round((impact_value * relevance * recency * trust * confidence), 2)
            decision_quality = str(intelligence.get("decision_quality") or "tactical only")
            size_guidance = str(intelligence.get("size_guidance") or "small risk")
            conviction_rank = {
                "high conviction": 3,
                "selective": 2,
                "tactical only": 1,
            }.get(decision_quality, 1)
            confidence = min(99, confidence + (6 if conviction_rank == 3 else 2 if conviction_rank == 2 else 0))
            expected_move = item.get("impact") or "medium"
            expected_move_map = {
                "high": "1.5-3.0%",
                "medium": "0.8-1.8%",
                "low": "0.3-1.0%",
            }
            scored.append(
                {
                    "symbol": ticker,
                    "thesis": item.get("thesis") or item.get("title") or "Set-up requires confirmation.",
                    "trigger": item.get("trigger") or intelligence.get("trigger") or "Wait for structure confirmation.",
                    "invalidation": item.get("risk") or intelligence.get("invalidation") or "Invalid if first impulse fully reverses.",
                    "window": intelligence.get("execution_window") or "open+60m",
                    "confidence": confidence,
                    "decision_quality": decision_quality,
                    "size_guidance": size_guidance,
                    "expected_move": expected_move_map.get(str(expected_move), str(expected_move)),
                    "catalysts": [
                        value
                        for value in [
                            item.get("event_type"),
                            item.get("region"),
                            item.get("source"),
                            (item.get("product_catalyst") or {}).get("theme"),
                        ]
                        if value
                    ],
                    "product_catalyst": item.get("product_catalyst"),
                    "setup_type": item.get("setup_source") or "single_name",
                    "direction": item.get("setup"),
                    "_score": round(score + conviction_rank * 8 + (4 if setup_source == "single_name" else 0), 2),
                }
            )

        mover_payload = market_movers or {"gainers": [], "losers": []}
        existing_symbols = {str(row.get("symbol") or "").upper() for row in scored}
        for bucket, direction in (("gainers", "long_watch"), ("losers", "rebound_or_avoid")):
            for mover in (mover_payload.get(bucket) or [])[:4]:
                symbol = str(mover.get("ticker") or "").upper()
                if not symbol or symbol in existing_symbols:
                    continue
                change = mover.get("change_1d")
                if not isinstance(change, (int, float)):
                    change = mover.get("change_1w")
                if not isinstance(change, (int, float)):
                    continue
                abs_move = abs(float(change))
                confidence = min(82, max(52, int(48 + min(abs_move, 12) * 3)))
                is_gainer = bucket == "gainers"
                scored.append(
                    {
                        "symbol": symbol,
                        "thesis": (
                            f"{symbol} is one of today's strongest movers. Momentum can work, but only if it holds VWAP/first pullback."
                            if is_gainer
                            else f"{symbol} is one of today's weakest movers. Treat as rebound candidate only after capitulation stabilizes."
                        ),
                        "trigger": (
                            "Price should hold the first pullback and keep relative strength versus the index."
                            if is_gainer
                            else "Wait for selling pressure to slow, then require a reclaim of intraday support before any rebound trade."
                        ),
                        "invalidation": (
                            "Invalid if the mover gives back the first impulse or volume fades."
                            if is_gainer
                            else "Invalid if new lows continue without stabilization."
                        ),
                        "window": "today / next session",
                        "confidence": confidence,
                        "decision_quality": "selective" if is_gainer else "tactical only",
                        "size_guidance": "reduced risk" if is_gainer else "small risk",
                        "expected_move": f"{abs_move:.1f}% observed move",
                        "catalysts": ["market_mover", bucket, mover.get("sector") or "broad_universe"],
                        "setup_type": "market_mover",
                        "direction": direction,
                        "market_mover": {
                            "change_1d": mover.get("change_1d"),
                            "change_1w": mover.get("change_1w"),
                            "price": mover.get("price"),
                            "name": mover.get("name"),
                        },
                        "_score": round(52 + min(abs_move, 15) * 2.2 + (6 if is_gainer else 3), 2),
                    }
                )
                existing_symbols.add(symbol)

        scored.sort(key=lambda row: (row["_score"], row["confidence"]), reverse=True)
        for index, row in enumerate(scored, start=1):
            row["rank"] = index
            row["rank_score"] = round(float(row.get("_score") or 0), 2)
            row["setup_id"] = f"{row.get('symbol','UNK')}-{index}"
            row.pop("_score", None)
        return scored[:5]

    def _is_direct_single_name_signal(self, item: Dict[str, Any], ticker: str | None) -> bool:
        if not ticker:
            return False
        title = str(item.get("title") or "").lower()
        event_type = str(item.get("event_type") or "").lower()
        ticker_l = ticker.lower()
        if event_type == "earnings":
            return True
        if event_type == "product_catalyst":
            return True
        stock_terms = [
            "earnings",
            "revenue",
            "sales",
            "guidance",
            "profit",
            "margin",
            "eps",
            "upgrade",
            "downgrade",
            "price target",
            "initiates",
            "beats",
            "misses",
            "forecast",
            "outlook",
            "sec filing",
            "13f",
            "insider",
        ]
        if ticker_l in title and any(term in title for term in stock_terms):
            return True
        return False

    def _macro_proxy_symbol(self, event_type: str, setup: str, macro_regime: str) -> str | None:
        event_type = (event_type or "macro").lower()
        setup = (setup or "watch").lower()
        if event_type == "conflict":
            return "GLD" if setup == "hedge" else "XLE"
        if event_type == "energy":
            return "XLE" if setup in {"long", "watch"} else "USO"
        if event_type == "central_bank":
            if macro_regime == "risk-on":
                return "QQQ"
            if macro_regime == "risk-off":
                return "TLT"
            return "SPY"
        if event_type == "macro_data":
            if macro_regime == "risk-on":
                return "SPY"
            if macro_regime == "risk-off":
                return "TLT"
            return "QQQ"
        if event_type == "policy":
            return "SMH"
        if event_type == "election":
            return "SPY"
        if event_type == "disaster":
            return "XLI"
        return None

    def _macro_proxy_thesis(self, event_type: str, symbol: str | None, macro_regime: str) -> str:
        if not symbol:
            return self._action_thesis(event_type, macro_regime, None)
        if event_type == "conflict":
            return f"{symbol} is the cleaner conflict-risk expression than forcing a random single-stock trade."
        if event_type == "energy":
            return f"{symbol} tracks the energy impulse directly. Confirm crude strength before acting."
        if event_type in {"central_bank", "macro_data"}:
            return f"{symbol} is the macro proxy. Direction depends on rates, dollar and futures confirming together."
        if event_type == "policy":
            return f"{symbol} is the sector proxy for policy risk. Avoid single-name conviction until details are clear."
        return f"{symbol} is the broad-market proxy for this event. Wait for confirmation."

    def _build_prediction_signals(self, polymarket_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        signals: List[Dict[str, Any]] = []
        for event in polymarket_events or []:
            question = str(event.get("question") or "").strip()
            if not question:
                continue
            probability = self._normalize_probability(event.get("probability_yes"))
            if probability is None:
                continue
            volume_usd = self._safe_float(event.get("volume_usd")) or 0.0
            relevance = max(10, min(100, int(self._event_relevance_score({"title": question}) * 60 + (volume_usd / 2_000_000))))
            if relevance < 28:
                continue
            signals.append(
                {
                    "source": "polymarket",
                    "market": question,
                    "probability": probability,
                    "delta_24h": None,
                    "relevance": relevance,
                }
            )

        signals.sort(key=lambda row: row.get("relevance", 0), reverse=True)
        return signals[:8]

    def _normalize_probability(self, value: Any) -> float | None:
        parsed = self._safe_float(value)
        if parsed is None:
            return None
        if parsed > 1.0:
            parsed = parsed / 100.0
        parsed = max(0.0, min(1.0, parsed))
        return round(parsed, 4)

    def _event_relevance_score(self, item: Dict[str, Any]) -> float:
        title = str(item.get("title") or item.get("thesis") or "").lower()
        ticker = str(item.get("ticker") or item.get("symbol") or "").upper()
        event_type = str(item.get("event_type") or "").lower()
        score = 1.0
        if ticker:
            score += 0.35
        if event_type in {"conflict", "central_bank", "policy", "energy", "macro_data"}:
            score += 0.4
        if any(keyword in title for keyword in ["fed", "opec", "oil", "war", "inflation", "rates", "earnings", "guidance", "election"]):
            score += 0.3
        return min(2.0, score)

    def _resolve_event_geo(self, item: Dict[str, Any]) -> Dict[str, Any]:
        # Priority 1: upstream/provider geo values if present.
        geo = item.get("geo") if isinstance(item.get("geo"), dict) else {}
        lat = self._safe_float(geo.get("lat"))
        lon = self._safe_float(geo.get("lon"))
        if lat is not None and lon is not None:
            return {
                "lat": lat,
                "lon": lon,
                "place": geo.get("place"),
                "country": geo.get("country"),
                "confidence": "high",
                "source": "provider",
            }

        # Priority 2: deterministic mapping table.
        title = str(item.get("title") or "").lower()
        region = str(item.get("region") or "").lower()
        event_type = str(item.get("event_type") or "").lower()
        haystack = f"{title} {region} {event_type}"
        for row in self.GEO_LOOKUP:
            if any(term in haystack for term in row["terms"]):
                return {
                    "lat": row["lat"],
                    "lon": row["lon"],
                    "place": row["place"],
                    "country": row["country"],
                    "confidence": "medium",
                    "source": "resolver",
                }

        # Priority 3: region fallback.
        fallback = {
            "usa": {"lat": 40.0, "lon": -98.0, "place": "United States", "country": "United States"},
            "europe": {"lat": 50.0, "lon": 14.0, "place": "Europe", "country": "Europe"},
            "asia": {"lat": 34.0, "lon": 103.0, "place": "Asia", "country": "Asia"},
            "global": {"lat": 20.0, "lon": 20.0, "place": "Global", "country": "Global"},
        }.get(region, {"lat": 20.0, "lon": 20.0, "place": "Global", "country": "Global"})
        return {
            "lat": fallback["lat"],
            "lon": fallback["lon"],
            "place": fallback["place"],
            "country": fallback["country"],
            "confidence": "low",
            "source": "fallback",
        }

    def _safe_float(self, value: Any) -> float | None:
        try:
            if value is None:
                return None
            parsed = float(value)
            if parsed != parsed:  # NaN guard
                return None
            return parsed
        except (TypeError, ValueError):
            return None

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
                    "impact": item.get("impact"),
                },
            )
            bucket["mentions"] += 1
            if item.get("title"):
                bucket["titles"].append(item["title"])
        signals = [item for item in grouped.values() if item["mentions"] >= 2]
        for item in signals:
            mentions = int(item.get("mentions") or 0)
            event_type = item.get("event_type") or "macro"
            score = min(92, 44 + mentions * 12 + (8 if event_type in {"policy", "conflict", "energy"} else 0))
            bias = "contrarian fade" if mentions >= 4 else "watch" if mentions == 2 else "crowd long"
            style = "meme risk" if mentions >= 4 else "crowd pressure" if mentions == 3 else "retail buildup"
            risk = "avoid leverage" if mentions >= 4 else "needs tape confirmation"
            action = "fade only if price stalls" if mentions >= 4 else "watch for squeeze continuation" if mentions >= 3 else "track only"
            item["crowd_score"] = score
            item["crowd_bias"] = bias
            item["crowd_style"] = style
            item["crowd_risk"] = risk
            item["crowd_action"] = action
            item["crowd_intensity"] = "high" if mentions >= 4 else "medium" if mentions == 3 else "low"
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
                    "impact": item.get("impact"),
                },
            )
            bucket["mentions"] += 1
            if item.get("title"):
                bucket["titles"].append(item["title"])
        signals = list(grouped.values())
        for item in signals:
            mentions = int(item.get("mentions") or 0)
            event_type = item.get("event_type") or "macro"
            score = min(88, 40 + mentions * 10 + (6 if event_type in {"policy", "election", "energy"} else 0))
            bias = "contrarian fade" if mentions >= 4 else "retail chase" if mentions >= 3 else "watch"
            style = "retail chase" if mentions >= 4 else "narrative build" if mentions == 3 else "social pulse"
            risk = "high noise / avoid leverage" if mentions >= 4 else "needs price and volume confirmation"
            action = "fade only after exhaustion" if mentions >= 4 else "watch for breakout follow-through" if mentions >= 3 else "monitor"
            item["social_score"] = score
            item["social_bias"] = bias
            item["social_style"] = style
            item["social_risk"] = risk
            item["social_action"] = action
            item["social_intensity"] = "high" if mentions >= 4 else "medium" if mentions == 3 else "low"
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
        now = datetime.now(timezone.utc)
        horizon = now + timedelta(days=21)
        for ticker in unique_tickers[:12]:
            try:
                info = DataFetcher(ticker).info
                earnings_at = self._extract_earnings_datetime(info)
                if not earnings_at or earnings_at > horizon or earnings_at < now - timedelta(hours=8):
                    continue
                days_until = (earnings_at.date() - now.date()).days
                entries.append(
                    {
                        "ticker": ticker,
                        "company": info.get("shortName") or info.get("longName") or ticker,
                        "scheduled_for": earnings_at.isoformat(),
                        "session": self._classify_earnings_session(earnings_at),
                        "days_until": days_until,
                        "importance": "watchlist" if ticker in watched_tickers else "market",
                        "region": self._region_from_country(info.get("country")),
                    }
                )
            except Exception:
                continue

        entries.sort(key=lambda item: item["scheduled_for"])
        return entries[:8]

    def _collect_earnings_results(
        self,
        watchlist_snapshot: Dict[str, Any] | None,
        earnings_calendar: List[Dict[str, Any]] | None = None,
        broad_earnings: List[Dict[str, Any]] | None = None,
    ) -> List[Dict[str, Any]]:
        tickers: List[str] = []
        if watchlist_snapshot:
            for item in watchlist_snapshot.get("items", []):
                if item.get("kind") == "ticker":
                    tickers.append(item.get("value", ""))

        for source in (earnings_calendar or [])[:8]:
            tickers.append(source.get("ticker", ""))
        for source in (broad_earnings or [])[:8]:
            tickers.append(source.get("ticker", ""))
        tickers.extend(["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA"])

        unique_tickers: List[str] = []
        seen = set()
        for ticker in tickers:
            normalized = (ticker or "").upper().strip()
            if (
                not normalized
                or normalized in seen
                or normalized in self.FUNDAMENTAL_EXCLUDED_TICKERS
                or normalized.startswith("^")
                or normalized.endswith("=F")
                or normalized.endswith("-USD")
            ):
                continue
            seen.add(normalized)
            unique_tickers.append(normalized)

        results: List[Dict[str, Any]] = []
        for ticker in unique_tickers[:10]:
            try:
                fetcher = DataFetcher(ticker)
                history = fetcher.get_earnings_history()
                reported_rows = [
                    row for row in history
                    if row.get("reported_eps") is not None or row.get("eps_surprise_pct") is not None
                ]
                latest = reported_rows[0] if reported_rows else (history[0] if history else None)
                if not latest:
                    continue
                period_dt = self._parse_earnings_period(latest.get("period"))
                if period_dt is None:
                    continue
                now_utc = datetime.now(timezone.utc)
                days_since = (now_utc.date() - period_dt.date()).days
                if days_since < 0 or days_since > int(os.getenv("BRIEF_EARNINGS_RESULT_MAX_AGE_DAYS", "10")):
                    continue

                surprise = latest.get("eps_surprise_pct")
                reported = latest.get("reported_eps")
                estimate = latest.get("eps_estimate")
                if surprise is None and reported is None and estimate is None:
                    continue

                status = latest.get("status") or self._earnings_result_status(surprise)
                fundamentals = fetcher.get_fundamentals() or {}
                trends = ((fundamentals.get("financial_statements") or {}).get("trends") or {})
                revenue_yoy = trends.get("quarterly_revenue_yoy")
                guidance_signal = fetcher.get_guidance_signal() or {}
                guidance_sentiment = str(guidance_signal.get("sentiment") or "unknown").lower()
                action_hint, summary = self._earnings_result_action(
                    status,
                    surprise,
                    revenue_yoy,
                    guidance_sentiment,
                )
                info = fetcher.info or {}
                results.append(
                    {
                        "ticker": ticker,
                        "company": info.get("shortName") or info.get("longName") or ticker,
                        "period": latest.get("period"),
                        "reported_at": period_dt.isoformat(),
                        "days_since": days_since,
                        "reported_eps": reported,
                        "eps_estimate": estimate,
                        "eps_surprise_pct": surprise,
                        "revenue_yoy": revenue_yoy,
                        "guidance_label": guidance_signal.get("label"),
                        "guidance_sentiment": guidance_sentiment,
                        "status": status,
                        "action_hint": action_hint,
                        "summary": summary,
                        "source": "yfinance_earnings_dates",
                    }
                )
            except Exception:
                continue

        def sort_key(item: Dict[str, Any]) -> tuple:
            surprise = item.get("eps_surprise_pct")
            surprise_abs = abs(float(surprise)) if isinstance(surprise, (int, float)) else 0.0
            status_rank = {"beat": 3, "miss": 2, "inline": 1}.get(str(item.get("status")), 0)
            return (status_rank, surprise_abs)

        results.sort(key=sort_key, reverse=True)
        return results[:6]

    def _parse_earnings_period(self, value: Any) -> datetime | None:
        if not value:
            return None
        try:
            if isinstance(value, datetime):
                dt = value
            else:
                dt = datetime.fromisoformat(str(value)[:10])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None

    def _earnings_result_status(self, surprise: Any) -> str:
        if isinstance(surprise, (int, float)):
            if surprise >= 3:
                return "beat"
            if surprise <= -3:
                return "miss"
        return "inline"

    def _earnings_result_action(
        self,
        status: str,
        surprise: Any,
        revenue_yoy: Any = None,
        guidance_sentiment: str = "unknown",
    ) -> tuple[str, str]:
        surprise_value = float(surprise) if isinstance(surprise, (int, float)) else 0.0
        revenue_value = float(revenue_yoy) if isinstance(revenue_yoy, (int, float)) else None
        has_positive_revenue = revenue_value is not None and revenue_value >= 0.08
        has_negative_revenue = revenue_value is not None and revenue_value < 0

        if status == "beat" and surprise_value >= 8 and guidance_sentiment == "positive":
            return (
                "constructive_if_follow_through",
                "Deutlicher EPS-Beat mit positiver Guidance. Kauf nur bei sauberem Preis-Follow-through, nicht blind in den ersten Spike.",
            )
        if status == "beat" and (has_positive_revenue or guidance_sentiment == "positive"):
            return (
                "constructive_watch",
                "EPS ueber Erwartung. Setup wird konstruktiver, weil Guidance oder Umsatztrend mitziehen. Jetzt nur noch Preisreaktion bestaetigen.",
            )
        if status == "beat":
            return (
                "watch_pullback_or_follow_through",
                "EPS-Beat ohne klare Guidance-Bestaetigung. Kein Chase, erst Reaktion und Umsatztrend bestaetigen.",
            )
        if status == "miss" and (guidance_sentiment == "negative" or has_negative_revenue):
            return (
                "avoid_until_repair",
                "EPS-Miss plus schwache Guidance oder negatives Umsatzmomentum. Kein Kauf, bis Management und Preisstruktur die Schaeden reparieren.",
            )
        if status == "miss":
            return (
                "caution_until_repair",
                "EPS unter Erwartung. Erst beobachten, bis Management-Ausblick und Kursstruktur wieder Stabilitaet zeigen.",
            )
        if guidance_sentiment == "positive" and has_positive_revenue:
            return (
                "constructive_watch",
                "EPS nahe Erwartung, aber Guidance und Umsatztrend bleiben stabil. Watchlist-Kandidat statt aggressiver Einstieg.",
            )
        return (
            "needs_guidance_confirmation",
            "EPS nahe Erwartung. Kein Upgrade ohne starke Guidance, Umsatzbeschleunigung oder klare Marktreaktion.",
        )

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
        seen_signatures: set[str] = set()
        for item in news[:10]:
            raw_ticker = str(item.get("ticker") or "").upper() or None
            ticker = raw_ticker
            event_type = item.get("event_type") or "macro"
            impact = item.get("impact") or "low"
            if impact == "low" and not ticker:
                continue
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
            elif event_type == "product_catalyst":
                catalyst = item.get("product_catalyst") or {}
                catalyst_type = catalyst.get("catalyst_type")
                setup = "short" if catalyst_type == "delay" else "watch"
                leverage = "conditional"
                trigger = "Wait for price, volume and analyst/channel checks to confirm the product headline."
                risk = "Product headlines are often rumour-driven; invalid if official confirmation or price follow-through fails."

            direct_single_name = self._is_direct_single_name_signal(item, raw_ticker)
            setup_source = "single_name" if direct_single_name else "macro_proxy"
            if raw_ticker and not direct_single_name:
                proxy = self._macro_proxy_symbol(str(event_type), setup, macro_regime)
                ticker = proxy
                if ticker:
                    thesis = f"{item.get('title') or 'Macro event'}"
                    trigger = self._macro_proxy_trigger(str(event_type), setup)
                    risk = self._macro_proxy_risk(str(event_type))
                else:
                    ticker = None
                    setup_source = "macro"
            elif not raw_ticker:
                ticker = self._macro_proxy_symbol(str(event_type), setup, macro_regime)
                setup_source = "macro_proxy" if ticker else "macro"
                if ticker:
                    trigger = self._macro_proxy_trigger(str(event_type), setup)
                    risk = self._macro_proxy_risk(str(event_type))

            if raw_ticker and direct_single_name and raw_ticker in watched_tickers:
                trigger = f"Watch {ticker} first. It is already on your radar."
            if setup == "watch" and not ticker and impact != "high":
                continue
            signature = f"{ticker or 'macro'}:{setup}:{event_type}:{trigger}"
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)

            intelligence = self._build_event_intelligence(
                event_type=event_type,
                impact=impact,
                severity=item.get("severity") or "normal",
                source_quality=item.get("source_quality") or "tier_2",
                ticker=ticker,
            )
            action_thesis = (
                self._action_thesis(str(event_type), macro_regime, ticker)
                if setup_source == "single_name"
                else self._macro_proxy_thesis(str(event_type), ticker, macro_regime)
            )
            board.append(
                {
                    "title": thesis,
                    "region": item.get("region") or "usa",
                    "ticker": ticker,
                    "original_ticker": raw_ticker,
                    "event_type": event_type,
                    "impact": impact,
                    "setup": setup,
                    "setup_source": setup_source,
                    "leverage": leverage,
                    "thesis": action_thesis,
                    "trigger": trigger,
                    "risk": risk,
                    "source": item.get("publisher"),
                    "source_quality": item.get("source_quality"),
                    "product_catalyst": item.get("product_catalyst"),
                    "link": item.get("link"),
                    "event_intelligence": intelligence,
                    "portfolio_exposure": self._build_portfolio_exposure(
                        raw_ticker if setup_source == "single_name" else ticker,
                        watchlist_snapshot,
                        intelligence,
                    ),
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
                        "event_intelligence": item.get("event_intelligence") or self._build_event_intelligence(
                            event_type=item.get("event_type") or "macro",
                            impact=item.get("impact") or "medium",
                            severity=item.get("severity") or "normal",
                            source_quality=item.get("source_quality") or "tier_2",
                            ticker=item.get("ticker"),
                        ),
                        "portfolio_exposure": self._build_portfolio_exposure(
                            item.get("ticker"),
                            watchlist_snapshot,
                            item.get("event_intelligence") or {},
                        ),
                    }
                )
        return board[:8]

    def _macro_proxy_trigger(self, event_type: str, setup: str) -> str:
        event_type = (event_type or "macro").lower()
        if event_type == "conflict":
            return "Act only if gold/oil hold the first impulse and index breadth weakens or defense bid confirms."
        if event_type == "energy":
            return "Crude and XLE should hold above the opening impulse; avoid chasing if both fade."
        if event_type in {"central_bank", "macro_data"}:
            return "Use only after yields, dollar and index futures confirm in the same direction."
        if event_type == "policy":
            return "Wait for sector ETF confirmation before selecting single names."
        if event_type == "election":
            return "Wait for index breadth and rates to confirm the first political headline reaction."
        if event_type == "disaster":
            return "Trade only after affected sectors show volume confirmation, not the first panic print."
        return "Wait for market structure to confirm direction."

    def _macro_proxy_risk(self, event_type: str) -> str:
        event_type = (event_type or "macro").lower()
        if event_type in {"conflict", "policy", "election"}:
            return "Headline reversals can invalidate the setup quickly."
        if event_type == "energy":
            return "Oil spikes often fade on policy or supply headlines."
        if event_type in {"central_bank", "macro_data"}:
            return "No trade if bonds, dollar and futures disagree after the release."
        return "Invalid if the first impulse fully reverses."

    def _build_portfolio_brain(self, action_board: List[Dict[str, Any]]) -> Dict[str, Any]:
        summary = {
            "at_risk": 0,
            "beneficiaries": 0,
            "hedges": 0,
        }
        items: List[Dict[str, Any]] = []
        seen: set[str] = set()

        for item in action_board:
            exposure = item.get("portfolio_exposure") or {}
            matched_holdings = [
                str(value or "").upper()
                for value in exposure.get("matched_holdings") or []
                if value
            ]
            if not matched_holdings:
                continue

            setup = str(item.get("setup") or exposure.get("action") or "watch").lower()
            if setup in {"short", "watch-short"}:
                portfolio_action = "reduce"
                bucket = "at_risk"
            elif setup == "hedge":
                portfolio_action = "hedge"
                bucket = "hedges"
            elif setup == "long":
                portfolio_action = "add"
                bucket = "beneficiaries"
            else:
                portfolio_action = "watch"
                bucket = "at_risk"

            summary[bucket] += len(matched_holdings)
            hedges = [
                hedge for hedge in (exposure.get("hedge_candidates") or [])
                if hedge and hedge.get("ticker")
            ][:3]

            for holding in matched_holdings[:4]:
                dedupe_key = f"{holding}:{item.get('title')}:{portfolio_action}"
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                items.append(
                    {
                        "ticker": holding,
                        "title": item.get("title"),
                        "portfolio_action": portfolio_action,
                        "bucket": bucket,
                        "reason": exposure.get("note") or item.get("thesis"),
                        "event_type": item.get("event_type"),
                        "impact": item.get("impact"),
                        "exposure_strength": exposure.get("exposure_strength"),
                        "trigger": item.get("trigger") or item.get("event_intelligence", {}).get("trigger"),
                        "hedge_candidates": hedges,
                    }
                )

        items.sort(
            key=lambda row: (
                0 if row.get("exposure_strength") == "high" else 1 if row.get("exposure_strength") == "medium" else 2,
                0 if row.get("bucket") == "hedges" else 1 if row.get("bucket") == "at_risk" else 2,
                0 if row.get("impact") == "high" else 1 if row.get("impact") == "medium" else 2,
            )
        )
        return {
            "summary": summary,
            "actions": items[:8],
        }

    def _build_event_intelligence(
        self,
        event_type: str,
        impact: str,
        severity: str,
        source_quality: str,
        ticker: str | None,
    ) -> Dict[str, Any]:
        impact_score = {"high": 88, "medium": 68, "low": 48}.get(impact, 50)
        confidence = {
            "tier_1": 86,
            "tier_2": 74,
            "crowd": 46,
            "excluded": 32,
        }.get(source_quality, 58)
        if severity == "critical":
            impact_score += 6
            confidence += 4
            decay = "developing"
        elif severity == "elevated":
            impact_score += 3
            decay = "active"
        else:
            decay = "fading" if impact == "low" else "active"

        affected = self._event_affected_buckets(event_type, ticker)
        action = self._event_action_hint(event_type, impact)
        decision = self._decision_profile(
            impact_score=min(99, impact_score),
            confidence=min(95, confidence),
            action=action["action"],
            leverage=action["leverage"],
            decay=decay,
        )
        return {
            "impact_score": min(99, impact_score),
            "confidence_score": min(95, confidence),
            "decay": decay,
            "affected_sectors": affected["sectors"],
            "affected_assets": affected["assets"],
            "action": action["action"],
            "leverage": action["leverage"],
            "why_now": action["why_now"],
            "trigger": action["trigger"],
            "invalidation": action["invalidation"],
            "execution_window": action["execution_window"],
            "decision_quality": decision["decision_quality"],
            "size_guidance": decision["size_guidance"],
            "execution_bias": decision["execution_bias"],
        }

    def _event_affected_buckets(self, event_type: str, ticker: str | None) -> Dict[str, List[str]]:
        mapping = {
            "conflict": {
                "sectors": ["Energy", "Defense", "Airlines"],
                "assets": ["Oil", "Gold", "S&P 500 Futures"],
            },
            "central_bank": {
                "sectors": ["Growth", "Financials", "REITs"],
                "assets": ["US 10Y Yield", "US Dollar Index", "Nasdaq Futures"],
            },
            "energy": {
                "sectors": ["Energy", "Industrials", "Airlines"],
                "assets": ["Oil", "XLE", "Gold"],
            },
            "election": {
                "sectors": ["Defense", "Utilities", "Banks"],
                "assets": ["Domestic indices", "Rates", "EUR/USD"],
            },
            "disaster": {
                "sectors": ["Insurers", "Industrials", "Transport"],
                "assets": ["Commodities", "Shipping", "Regional equities"],
            },
            "policy": {
                "sectors": ["Industrials", "Semis", "Autos"],
                "assets": ["Dollar", "Regional indices", "Commodity baskets"],
            },
            "macro_data": {
                "sectors": ["Growth", "Consumer", "Financials"],
                "assets": ["Treasuries", "Dollar", "Index futures"],
            },
            "product_catalyst": {
                "sectors": ["Single-name growth", "Semis", "Consumer discretionary"],
                "assets": ["Product owner stock", "Peers", "Options IV"],
            },
        }
        payload = mapping.get(event_type, {"sectors": ["Broad market"], "assets": ["Index futures", "Dollar"]})
        if ticker:
            payload = {
                "sectors": payload["sectors"],
                "assets": [ticker, *payload["assets"]][:4],
            }
        return payload

    def _event_action_hint(self, event_type: str, impact: str) -> Dict[str, str]:
        if event_type == "conflict":
            return {
                "action": "hedge",
                "leverage": "avoid",
                "why_now": "Conflict risk favors defense, oil and gold over aggressive longs.",
                "trigger": "Only act if oil, gold or defense holds its first reaction after the open.",
                "invalidation": "If crude and gold fade back below the first impulse, reduce the hedge thesis.",
                "execution_window": "Open to first 90 minutes",
            }
        if event_type == "central_bank":
            return {
                "action": "watch",
                "leverage": "conditional" if impact == "medium" else "avoid",
                "why_now": "Rates, dollar and futures need confirmation before directional trades.",
                "trigger": "Wait for yields, dollar and index futures to confirm in the same direction.",
                "invalidation": "No trade if bonds, dollar and futures disagree after the release.",
                "execution_window": "Macro release to first hour",
            }
        if event_type == "energy":
            return {
                "action": "long",
                "leverage": "conditional",
                "why_now": "Energy follow-through matters if oil strength survives the open.",
                "trigger": "Take only if oil and energy equities keep relative strength after Europe or US open.",
                "invalidation": "Skip if oil spikes but XLE and cyclicals do not confirm.",
                "execution_window": "Europe handoff to US open",
            }
        if event_type == "election":
            return {
                "action": "watch",
                "leverage": "avoid",
                "why_now": "Election outcomes rotate sectors before a clean trend appears.",
                "trigger": "Let sector rotation show up first in banks, utilities, defense or domestic indices.",
                "invalidation": "Avoid if the first reaction reverses into the next headline cycle.",
                "execution_window": "Headline release to session close",
            }
        if event_type == "disaster":
            return {
                "action": "hedge",
                "leverage": "avoid",
                "why_now": "Supply-chain and insurer stress often matter before stock-specific narratives.",
                "trigger": "Watch transport, insurers and commodity routes before acting on single names.",
                "invalidation": "Stand down if the event gets contained quickly and transport normalizes.",
                "execution_window": "First session after event shock",
            }
        if event_type == "policy":
            return {
                "action": "short",
                "leverage": "avoid" if impact == "high" else "conditional",
                "why_now": "Policy shocks can fade, so risk control matters more than speed.",
                "trigger": "Use only if affected sectors lose support and broad tape confirms the policy shock.",
                "invalidation": "No short if the market absorbs the headline within the first impulse.",
                "execution_window": "Headline to first trend confirmation",
            }
        if event_type == "product_catalyst":
            return {
                "action": "watch",
                "leverage": "conditional",
                "why_now": "Product news can change demand expectations, but the first headline is often incomplete.",
                "trigger": "Act only if official confirmation, volume and analyst/channel checks support the move.",
                "invalidation": "Skip if the company, reliable press or price action does not confirm the headline.",
                "execution_window": "Headline to next session",
            }
        return {
            "action": "watch",
            "leverage": "avoid",
            "why_now": "Wait for market structure to confirm the headline.",
            "trigger": "Stand by until price, rates and sector leadership align.",
            "invalidation": "No trade if the first reaction fades immediately.",
            "execution_window": "Event dependent",
        }

    def _decision_profile(
        self,
        impact_score: int,
        confidence: int,
        action: str,
        leverage: str,
        decay: str,
    ) -> Dict[str, str]:
        if action == "watch":
            return {
                "decision_quality": "watch only",
                "size_guidance": "no position until confirmation",
                "execution_bias": "wait",
            }

        combined = impact_score + confidence
        if combined >= 170 and decay in {"developing", "active"} and leverage != "avoid":
            quality = "high conviction"
            sizing = "normal risk"
        elif combined >= 150 and decay != "fading":
            quality = "selective"
            sizing = "reduced risk"
        else:
            quality = "tactical only"
            sizing = "small risk"

        execution_bias = {
            "long": "follow strength",
            "short": "fade weakness",
            "hedge": "protect first",
        }.get(action, "wait")

        if leverage == "avoid":
            sizing = "no leverage"
        elif leverage == "conditional" and sizing == "normal risk":
            sizing = "reduced leverage"

        return {
            "decision_quality": quality,
            "size_guidance": sizing,
            "execution_bias": execution_bias,
        }

    def _build_portfolio_exposure(
        self,
        ticker: str | None,
        watchlist_snapshot: Dict[str, Any] | None,
        intelligence: Dict[str, Any],
    ) -> Dict[str, Any]:
        workspace_holdings = self._get_workspace_holdings()
        normalized_ticker = str(ticker or "").upper()
        sectors = [str(item or "").strip() for item in (intelligence.get("affected_sectors") or []) if item]
        event_action = intelligence.get("action")
        event_type = self._infer_event_type_from_intelligence(intelligence)
        watched_tickers = {
            str(item.get("value") or "").upper()
            for item in (watchlist_snapshot or {}).get("items", [])
            if item.get("kind") == "ticker"
        }
        if normalized_ticker:
            direct_holding = next(
                (item for item in workspace_holdings if item.get("ticker") == normalized_ticker),
                None,
            )
            if direct_holding:
                portfolio_name = direct_holding.get("portfolio_name") or "deinem Portfolio"
                return {
                    "ticker": normalized_ticker,
                    "status": "direct_holding",
                    "note": f"{normalized_ticker} liegt direkt in {portfolio_name} und ist vom Event betroffen.",
                    "action": event_action,
                    "exposure_strength": "high",
                    "matched_holdings": [normalized_ticker],
                    "matched_sectors": sectors[:3],
                    "hedge_candidates": self._build_portfolio_hedges(
                        sectors=sectors,
                        event_type=event_type,
                        matched_holdings=[direct_holding],
                    ),
                }

        if normalized_ticker and normalized_ticker in watched_tickers:
            return {
                "ticker": normalized_ticker,
                "status": "direct",
                "note": f"{normalized_ticker} ist direkt auf deiner Watchlist und vom Event betroffen.",
                "action": event_action,
                "exposure_strength": "medium",
                "matched_holdings": [normalized_ticker],
                "matched_sectors": sectors[:3],
                "hedge_candidates": self._build_portfolio_hedges(
                    sectors=sectors,
                    event_type=event_type,
                    matched_holdings=[],
                ),
            }

        sector_matches = self._match_holdings_by_sector(workspace_holdings, sectors)
        if sector_matches:
            labels = ", ".join(item["ticker"] for item in sector_matches[:3])
            return {
                "ticker": normalized_ticker or sector_matches[0]["ticker"],
                "status": "portfolio_sector",
                "note": f"Portfolio-Exposure ueber {labels} in {', '.join(sectors[:2])}.",
                "action": event_action,
                "exposure_strength": "medium" if len(sector_matches) == 1 else "high",
                "matched_holdings": [item["ticker"] for item in sector_matches[:4]],
                "matched_sectors": sectors[:3],
                "hedge_candidates": self._build_portfolio_hedges(
                    sectors=sectors,
                    event_type=event_type,
                    matched_holdings=sector_matches,
                ),
            }

        if sectors:
            return {
                "ticker": normalized_ticker or ticker,
                "status": "sector",
                "note": f"Indirekter Impact ueber {', '.join(sectors[:2])}.",
                "action": event_action,
                "exposure_strength": "low",
                "matched_holdings": [],
                "matched_sectors": sectors[:3],
                "hedge_candidates": self._build_portfolio_hedges(
                    sectors=sectors,
                    event_type=event_type,
                    matched_holdings=[],
                ),
            }
        return {
            "ticker": normalized_ticker or ticker,
            "status": "market",
            "note": "Vor allem Makro- und Sentiment-Effekt, kein klarer Direktbezug.",
            "action": event_action,
            "exposure_strength": "low",
            "matched_holdings": [],
            "matched_sectors": [],
            "hedge_candidates": self._build_portfolio_hedges(
                sectors=[],
                event_type=event_type,
                matched_holdings=[],
            ),
        }

    def _infer_event_type_from_intelligence(self, intelligence: Dict[str, Any]) -> str:
        sectors = {str(item or "").lower() for item in intelligence.get("affected_sectors") or []}
        action = str(intelligence.get("action") or "").lower()
        assets = " ".join(str(item or "").lower() for item in intelligence.get("affected_assets") or [])

        if "defense" in sectors or "oil" in assets or "gold" in assets:
            return "conflict"
        if "financials" in sectors or "reits" in sectors or "nasdaq futures" in assets:
            return "central_bank"
        if "energy" in sectors:
            return "energy"
        if "utilities" in sectors or "banks" in sectors:
            return "election"
        if "insurers" in sectors or "transport" in sectors:
            return "disaster"
        if "semis" in sectors or "autos" in sectors:
            return "policy"
        if action == "hedge":
            return "conflict"
        if action == "short":
            return "policy"
        return "macro"

    def _build_portfolio_hedges(
        self,
        sectors: List[str],
        event_type: str,
        matched_holdings: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        ideas: List[Dict[str, str]] = []
        seen: set[str] = set()

        def add(ticker: str, label: str) -> None:
            normalized = str(ticker or "").upper()
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            ideas.append({"ticker": normalized, "label": label})

        event_defaults = {
            "conflict": [("GLD", "Gold hedge"), ("XLE", "Energy cushion"), ("TLT", "Rates hedge")],
            "central_bank": [("TLT", "Duration hedge"), ("UUP", "Dollar hedge"), ("QQQ", "Growth reaction")],
            "energy": [("XLE", "Energy leaders"), ("USO", "Oil follow-through"), ("GLD", "Inflation hedge")],
            "election": [("XLU", "Utilities"), ("XLF", "Banks"), ("ITA", "Defense")],
            "disaster": [("GLD", "Shock hedge"), ("DBA", "Commodity stress"), ("IYT", "Transport read")],
            "policy": [("XLI", "Industrials"), ("SMH", "Semis"), ("UUP", "Dollar protection")],
            "macro": [("SPY", "Broad market"), ("GLD", "Macro hedge")],
        }
        sector_defaults = {
            "Energy": [("XLE", "Sector hedge"), ("USO", "Oil beta")],
            "Defense": [("ITA", "Defense basket")],
            "Airlines": [("JETS", "Airlines read")],
            "Growth": [("QQQ", "Growth proxy")],
            "Financials": [("XLF", "Financials")],
            "REITs": [("VNQ", "REITs")],
            "Utilities": [("XLU", "Utilities")],
            "Banks": [("KBE", "Banks")],
            "Insurers": [("KIE", "Insurers")],
            "Industrials": [("XLI", "Industrials")],
            "Transport": [("IYT", "Transport")],
            "Semis": [("SMH", "Semis")],
            "Autos": [("CARZ", "Autos")],
            "Consumer": [("XLY", "Consumer")],
        }

        for ticker, label in event_defaults.get(event_type, event_defaults["macro"]):
            add(ticker, label)
        for sector in sectors[:3]:
            for ticker, label in sector_defaults.get(sector, []):
                add(ticker, label)
        if matched_holdings:
            add("SPY", "Index hedge")

        return ideas[:4]

    def _get_portfolio_manager(self) -> PortfolioManager:
        if self._portfolio_manager is None:
            self._portfolio_manager = PortfolioManager()
        return self._portfolio_manager

    def _get_workspace_holdings(self) -> List[Dict[str, Any]]:
        holdings: List[Dict[str, Any]] = []
        try:
            portfolios = self._get_portfolio_manager().get_portfolios()
        except Exception:
            return holdings

        for portfolio in portfolios:
            portfolio_name = portfolio.get("name") or "Portfolio"
            for holding in portfolio.get("holdings", []):
                ticker = str(holding.get("ticker") or "").upper()
                if not ticker:
                    continue
                holdings.append(
                    {
                        "ticker": ticker,
                        "portfolio_name": portfolio_name,
                        "shares": holding.get("shares"),
                        "buy_price": holding.get("buyPrice"),
                    }
                )
        return holdings

    def _get_holding_profile(self, ticker: str) -> Dict[str, Any]:
        normalized = str(ticker or "").upper()
        if not normalized:
            return {}
        if normalized in self._holding_profile_cache:
            return self._holding_profile_cache[normalized]

        try:
            fundamentals = DataFetcher(normalized).get_fundamentals()
        except Exception:
            fundamentals = {}
        profile = {
            "sector": str(fundamentals.get("sector") or "").strip(),
            "industry": str(fundamentals.get("industry") or "").strip(),
            "quote_type": str(fundamentals.get("quote_type") or "").strip(),
        }
        self._holding_profile_cache[normalized] = profile
        return profile

    def _match_holdings_by_sector(
        self,
        holdings: List[Dict[str, Any]],
        sectors: List[str],
    ) -> List[Dict[str, Any]]:
        if not holdings or not sectors:
            return []

        sector_map = {
            "Energy": ["energy", "oil", "gas"],
            "Defense": ["aerospace", "defense"],
            "Airlines": ["airline", "travel", "transportation"],
            "Growth": ["technology", "software", "semiconductor", "internet"],
            "Financials": ["financial", "bank", "insurance", "capital markets"],
            "REITs": ["reit", "real estate"],
            "Utilities": ["utility"],
            "Banks": ["bank", "financial"],
            "Insurers": ["insurance"],
            "Industrials": ["industrial", "manufacturing", "transportation"],
            "Transport": ["transportation", "shipping", "airline", "logistics"],
            "Semis": ["semiconductor"],
            "Autos": ["auto", "vehicle", "automaker"],
            "Consumer": ["consumer", "retail", "apparel", "restaurant"],
        }

        matches: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for holding in holdings:
            profile = self._get_holding_profile(holding["ticker"])
            haystack = f"{profile.get('sector', '')} {profile.get('industry', '')}".lower()
            for sector in sectors:
                aliases = sector_map.get(sector, [sector.lower()])
                if any(alias in haystack for alias in aliases):
                    if holding["ticker"] not in seen:
                        seen.add(holding["ticker"])
                        matches.append(holding)
                    break
        return matches

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
        if event_type == "product_catalyst" and ticker:
            return f"{ticker} product catalyst. Treat it as a tradeable watch item only after official confirmation, volume and price reaction align."
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

        if any(term in text for term in ["war", "missile", "attack", "israel", "iran", "russia", "ukraine", "lebanon", "beirut"]):
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
        elif self._classify_product_catalyst(text):
            product = self._classify_product_catalyst(text) or {}
            event_type = "product_catalyst"
            impact = "medium"
            severity = "elevated" if any(term in text for term in ["delay", "delayed", "postpone", "postponed", "launch", "unveil", "release"]) else "normal"
            product_region = {"BMW.DE": "europe"}.get(str(product.get("ticker") or ""))
            if product_region:
                return {
                    "impact": impact,
                    "region": product_region,
                    "event_type": event_type,
                    "severity": severity,
                }
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

    def _classify_product_catalyst(self, text: str) -> Dict[str, str] | None:
        normalized = (text or "").lower()
        if not normalized:
            return None

        matched_ticker = None
        matched_theme = None
        for ticker, aliases in self.PRODUCT_CATALYST_ALIASES.items():
            for alias in aliases:
                if alias in normalized:
                    matched_ticker = ticker
                    matched_theme = alias
                    break
            if matched_ticker:
                break
        if not matched_ticker:
            return None

        delay_terms = ["delay", "delayed", "postpone", "postponed", "pushed back", "misses launch", "slips"]
        launch_terms = ["launch", "unveil", "release", "preorder", "new", "next-gen", "upgrade", "ship", "debut"]
        catalyst_type = "delay" if any(term in normalized for term in delay_terms) else "launch" if any(term in normalized for term in launch_terms) else "product_news"
        if catalyst_type == "product_news" and matched_theme in {"gpu", "iphone", "gta", "gta 6", "gta vi", "model y", "neue klasse"}:
            catalyst_type = "launch"

        direction_hint = "negative" if catalyst_type == "delay" else "positive_watch" if catalyst_type == "launch" else "watch"
        return {
            "ticker": matched_ticker,
            "theme": matched_theme or matched_ticker,
            "catalyst_type": catalyst_type,
            "direction_hint": direction_hint,
        }

    def _infer_region(self, text: str) -> str:
        asia_match = any(term in text for term in ["china", "japan", "asia", "hong kong", "taiwan", "korea", "india"])
        europe_match = any(term in text for term in ["europe", "germany", "uk", "france", "ecb", "italy", "ukraine", "hungary", "poland"])
        middle_east_match = any(term in text for term in ["iran", "lebanon", "beirut", "israel", "gaza", "middle east", "red sea"])
        global_match = any(term in text for term in ["global", "opec", "oil", "war", "sanction"])

        if (europe_match and middle_east_match) or global_match:
            return "global"
        if asia_match:
            return "asia"
        if europe_match:
            return "europe"
        if middle_east_match:
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
