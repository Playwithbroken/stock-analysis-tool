"""
Morning brief service.

Builds a market-opening brief across Asia, Europe, and the US using public
market data, best-effort event classification, and watchlist-aware calendars.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from html import unescape
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Sequence
from copy import deepcopy
import json
import os
import re
import time as perf_time

import pandas as pd
import requests
import yfinance as yf

from src.data_fetcher import DataFetcher
from src.storage import PortfolioManager
from src.social_intelligence_service import SocialIntelligenceService
from src.trading_signals_service import TradingSignalsService
from src.provider_observability import record_provider_result
from src.decision_scope import paper_scope, research_scope

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
    NEWS_ENTITY_ALIASES = {
        "NVDA": ["nvidia"],
        "AAPL": ["apple"],
        "MSFT": ["microsoft"],
        "TSLA": ["tesla"],
        "AMZN": ["amazon"],
        "META": ["meta platforms", "meta"],
        "GOOGL": ["alphabet", "google"],
        "TTWO": ["take-two", "take two", "rockstar games"],
        "BMW.DE": ["bmw", "rolls-royce motor cars"],
    }
    SEC_CIK_BY_TICKER = {
        "NVDA": "0001045810",
        "AAPL": "0000320193",
        "MSFT": "0000789019",
        "TSLA": "0001318605",
        "AMZN": "0001018724",
        "META": "0001326801",
        "GOOGL": "0001652044",
        "TTWO": "0000946581",
    }
    FUNDAMENTAL_EXCLUDED_TICKERS = {"SPY", "QQQ", "GLD", "TLT", "XLE", "XLK", "XLY", "XLV", "XLU", "XLRE", "IWM"}
    PRODUCT_CATALYST_ALIASES = {
        "NVDA": ["nvidia", "geforce", "rtx", "blackwell", "gpu", "graphics card", "ai chip"],
        "AAPL": ["apple", "iphone", "ipad", "macbook", "vision pro", "ios"],
        "TTWO": ["take-two", "take two", "rockstar", "gta", "grand theft auto", "gta 6", "gta vi"],
        "BMW.DE": ["bmw", "mini cooper", "rolls-royce motor cars", "neue klasse"],
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
        ("https://www.federalreserve.gov/feeds/press_monetary.xml", "Federal Reserve Board"),
        ("https://www.bls.gov/feed/bls_latest.rss", "U.S. Bureau of Labor Statistics"),
        ("https://www.bea.gov/rss/rss.xml", "U.S. Bureau of Economic Analysis"),
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
    OFFICIAL_PUBLISHERS = {
        "Federal Reserve Board",
        "U.S. Bureau of Labor Statistics",
        "U.S. Bureau of Economic Analysis",
    }
    OFFICIAL_DOMAINS = {
        "federalreserve.gov",
        "bls.gov",
        "bea.gov",
    }
    MARKET_MOVING_PERSON_TERMS = {
        "trump",
        "powell",
        "yellen",
        "bessent",
        "lutnick",
        "musk",
        "huang",
        "jensen huang",
        "cook",
        "tim cook",
        "zuckerberg",
        "bezos",
        "dimon",
        "jamie dimon",
        "lagarde",
        "von der leyen",
    }
    MARKET_MOVING_STATEMENT_TERMS = {
        "says",
        "said",
        "warns",
        "warned",
        "backs",
        "calls for",
        "announces",
        "threatens",
        "plans",
        "pledges",
        "statement",
        "speech",
        "interview",
        "tariff",
        "rates",
        "rate",
        "crypto",
        "oil",
        "china",
        "defense",
        "ai",
        "regulation",
    }
    IPO_TERMS = {
        "ipo",
        "initial public offering",
        "go public",
        "goes public",
        "listing",
        "listed",
        "market debut",
        "debut",
        "prices shares",
        "files for ipo",
        "confidentially files",
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
        *OFFICIAL_DOMAINS,
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
    _sec_filing_cache: Dict[str, tuple[Dict[str, Any], datetime]] = {}
    _sec_filing_ttl_seconds = 60 * 30
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
        if self._cache is not None and self._is_usable_brief(self._cache):
            return self._prepare_brief_for_delivery(self._cache, watchlist_snapshot)
        persisted = self._load_persisted_snapshot()
        if persisted is not None and self._is_usable_brief(persisted):
            return self._prepare_brief_for_delivery(persisted, watchlist_snapshot)
        return None

    def _prepare_brief_for_delivery(
        self,
        brief: Dict[str, Any],
        watchlist_snapshot: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        refreshed = self._refresh_cached_event_guidance(brief)
        refreshed["top_news"] = self._attach_news_decision_readiness(
            refreshed.get("top_news") or []
        )
        refreshed["google_news_extra"] = self._attach_news_decision_readiness(
            refreshed.get("google_news_extra") or []
        )
        refreshed["quality"] = self._build_quality_report(refreshed)
        return self._merge_watchlist_impact(refreshed, watchlist_snapshot)

    def _refresh_cached_event_guidance(self, brief: Dict[str, Any]) -> Dict[str, Any]:
        refreshed = deepcopy(brief)

        for event in refreshed.get("event_layer") or []:
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("event_type") or "macro").lower()
            impact = str(event.get("impact") or "medium").lower()
            guidance = self._event_action_hint(event_type, impact)
            intelligence = event.get("event_intelligence") if isinstance(event.get("event_intelligence"), dict) else {}
            intelligence.update({
                key: guidance[key]
                for key in ("action", "leverage", "why_now", "trigger", "invalidation", "execution_window")
                if guidance.get(key)
            })
            event["event_intelligence"] = intelligence

        for ping in refreshed.get("event_pings") or []:
            if not isinstance(ping, dict):
                continue
            event_type = str(ping.get("type") or "macro").lower()
            severity = str(ping.get("severity") or "normal").lower()
            impact = "high" if severity in {"critical", "elevated", "high"} else "medium"
            guidance = self._event_action_hint(event_type, impact)
            trade_impact = ping.get("trade_impact") if isinstance(ping.get("trade_impact"), dict) else {}
            trade_impact.update({
                "action": guidance.get("action") or trade_impact.get("action") or "watch",
                "baseline_scenario": guidance.get("why_now") or trade_impact.get("baseline_scenario"),
                "trigger": guidance.get("trigger") or trade_impact.get("trigger"),
                "invalidation": guidance.get("invalidation") or trade_impact.get("invalidation"),
                "window": guidance.get("execution_window") or trade_impact.get("window"),
            })
            ping["trade_impact"] = trade_impact

        return refreshed

    def _is_usable_brief(self, brief: Dict[str, Any] | None) -> bool:
        if not isinstance(brief, dict):
            return False
        quality = brief.get("quality") if isinstance(brief.get("quality"), dict) else {}
        if quality.get("fallback") or int(quality.get("score") or 0) <= 0:
            return False
        regions = brief.get("regions") if isinstance(brief.get("regions"), dict) else {}
        has_region_assets = any((region or {}).get("assets") for region in regions.values())
        return has_region_assets or bool(brief.get("top_news")) or bool(brief.get("trade_setups"))

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
            "congress_watch": [],
            "trade_setups": [],
            "learning_adjustments": [],
            "trade_setups_status": "insufficient_signal",
            "setup_board": {"now": [], "next": [], "avoid": []},
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
            "data_status": {
                "mode": "fallback",
                "deferred": [],
                "sources": {},
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
            return self._prepare_brief_for_delivery(self._cache, watchlist_snapshot)

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
        top_news = self._attach_news_market_confirmation(
            self._collect_news(extra_tickers=watchlist_tickers),
            fast=False,
        )
        top_news = self._attach_news_primary_sources(top_news, fast=False)
        top_news = self._attach_news_decision_readiness(top_news)
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
        if not event_pings:
            event_pings = self._build_macro_event_ping_fallback(macro)
        product_catalysts = self._build_product_catalysts(top_news)
        if not product_catalysts:
            product_catalysts = self._build_product_watch_fallback(watchlist_tickers)
        market_movers = self._collect_market_movers(watchlist_tickers)
        contrarian_signals = self._build_contrarian_signals(top_news, watchlist_snapshot)
        earnings_calendar = self._collect_earnings_calendar(watchlist_snapshot)
        if not earnings_calendar:
            earnings_calendar = self._build_earnings_watch_fallback(watchlist_snapshot)
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
        congress_watch = self._build_congress_watch(action_board)
        learning_bias = self._build_learning_bias()
        trade_setups = self._build_trade_setups(action_board, top_news, market_movers, learning_bias)
        setup_board = self._build_setup_board(trade_setups)
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
                "note": (
                    "Top News benötigt einen klickbaren Bericht einer freigegebenen Quelle. "
                    "Als wichtig markiert werden nur Tier-1-Berichte mit Zeitstempel und hoher Relevanz. "
                    "Faktenbasis und Analyse sind getrennt; ein einzelner Bericht gilt nicht als unabhängig bestätigt. "
                    "Fed-, BLS- und BEA-Releases werden direkt aus offiziellen Behördenfeeds als Primärquellen geladen. "
                    "Bei unterstützten Earnings wird ein konkretes SEC-Filing nur nach Dokument-HTTP-200 als Primärquelle markiert. "
                    "Social/X und Reddit bleiben außerhalb des Trusted-News-Blocks."
                ),
            },
            "event_layer": event_layer,
            "event_pings": event_pings,
            "product_catalysts": product_catalysts,
            "market_movers": market_movers,
            "future_stars": self._build_future_stars_brief(),
            "contrarian_signals": contrarian_signals,
            "economic_calendar": economic_calendar,
            "earnings_calendar": earnings_calendar,
            "broad_earnings": broad_earnings,
            "earnings_results": earnings_results,
            "opening_timeline": opening_timeline,
            "action_board": action_board,
            "congress_watch": congress_watch,
            "trade_setups": trade_setups,
            "learning_adjustments": learning_bias.get("summary", []),
            "trade_setups_status": "ready" if trade_setups else "insufficient_signal",
            "setup_board": setup_board,
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
                "watched_themes": self._build_prediction_market_watch_themes(event_layer, macro),
                "message": (
                    "Live Polymarket-Signale aktiv."
                    if prediction_signals
                    else "Polymarket-Feed aktuell ohne verwertbare Live-Treffer; Makro-Themen werden weiter beobachtet."
                ),
            },
            "google_news_extra": google_news_extra[:8],
            "trading_edge": trading_edge,
            "data_status": {
                "mode": "full",
                "deferred": [],
                "sources": {
                    "reddit": "loaded" if reddit_posts else "empty_or_unavailable",
                    "stocktwits": "loaded" if stocktwits_data else "empty_or_unavailable",
                    "polymarket": "loaded" if polymarket_events else "empty_or_unavailable",
                    "google_news": "loaded" if google_news_extra else "empty_or_unavailable",
                    "earnings_calendar": "loaded" if broad_earnings else "empty_or_unavailable",
                    "earnings_results": "loaded" if earnings_results else "no_recent_results",
                },
            },
        }
        brief["quality"] = self._build_quality_report(brief)
        self._attach_playbook_context(brief)
        self._cache = brief
        self._cache_time = now
        self._persist_snapshot(brief)
        return self._prepare_brief_for_delivery(brief, watchlist_snapshot)

    def get_brief_fast(
        self,
        watchlist_snapshot: Dict[str, Any] | None = None,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Fast brief path for API/dashboard rendering under strict latency budget."""
        now = datetime.now(timezone.utc)
        if (
            not force_refresh
            and
            self._cache is not None
            and self._cache_time is not None
            and self._is_usable_brief(self._cache)
            and (now - self._cache_time).total_seconds() < self._ttl_seconds
        ):
            return self._prepare_brief_for_delivery(self._cache, watchlist_snapshot)

        watchlist_tickers = [
            (item.get("value") or "").upper()
            for item in (watchlist_snapshot or {}).get("items", [])
            if item.get("kind") == "ticker" and item.get("value")
        ]

        asia = self._collect_region(self.ASIA, "Asia", fast=True)
        europe = self._collect_region(self.EUROPE, "Europe", fast=True)
        usa = self._collect_region(self.USA, "USA", fast=True)
        macro = self._collect_assets(self.MACRO, fast=True)
        top_news = self._attach_news_market_confirmation(
            self._collect_news(extra_tickers=watchlist_tickers, fast=True),
            fast=True,
        )
        top_news = self._attach_news_primary_sources(top_news, fast=True)
        top_news = self._attach_news_decision_readiness(top_news)
        event_layer = self._build_event_layer(top_news)
        event_pings = self._build_event_pings(event_layer)
        if not event_pings:
            event_pings = self._build_macro_event_ping_fallback(macro)
        product_catalysts = self._build_product_catalysts(top_news)
        if not product_catalysts:
            product_catalysts = self._build_product_watch_fallback(watchlist_tickers)
        try:
            broad_earnings = self._social_service.get_broad_earnings_calendar(
                extra_tickers=watchlist_tickers,
                days_ahead=21,
            )
        except Exception:
            broad_earnings = []
        earnings_calendar = [
            {
                "ticker": item.get("ticker"),
                "company": item.get("company"),
                "scheduled_for": item.get("date"),
                "session": item.get("session") or "watch",
                "region": "USA",
                "date_status": "confirmed",
                "summary": (
                    f"{item.get('ticker')}: Earnings in {item.get('days_until')}d. "
                    "EPS, revenue and guidance reaction stay on watch."
                ),
            }
            for item in (broad_earnings or [])[:8]
            if item.get("ticker")
        ]
        if not earnings_calendar:
            earnings_calendar = self._build_earnings_watch_fallback(watchlist_snapshot)
        try:
            polymarket_events = self._social_service.get_polymarket_events()
        except Exception:
            polymarket_events = []
        prediction_signals = self._build_prediction_signals(polymarket_events)
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
        congress_watch = self._build_congress_watch(action_board)
        learning_bias = self._build_learning_bias()
        trade_setups = self._build_trade_setups(action_board, top_news, {"gainers": [], "losers": []}, learning_bias)
        setup_board = self._build_setup_board(trade_setups)

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
                "note": (
                    "Fast Mode: klickbare Trusted-News-Berichte werden priorisiert; wichtig erfordert Tier 1, "
                    "Zeitstempel und hohe Relevanz. Offizielle Fed-/BLS-/BEA-Feeds haben Primärquellenstatus. "
                    "Faktenbasis und Analyse bleiben getrennt; unterstützte Earnings erhalten "
                    "bei erfolgreicher SEC-Prüfung einen konkreten Primärquellen-Link."
                ),
            },
            "event_layer": event_layer,
            "event_pings": event_pings,
            "product_catalysts": product_catalysts,
            "market_movers": {"gainers": [], "losers": []},
            "future_stars": self._build_future_stars_brief(fast=True),
            "contrarian_signals": self._build_contrarian_signals(top_news, watchlist_snapshot),
            "economic_calendar": economic_calendar,
            "earnings_calendar": earnings_calendar,
            "broad_earnings": broad_earnings[:12],
            "earnings_results": [],
            "opening_timeline": opening_timeline,
            "action_board": action_board,
            "congress_watch": congress_watch,
            "trade_setups": trade_setups,
            "learning_adjustments": learning_bias.get("summary", []),
            "trade_setups_status": "ready" if trade_setups else "insufficient_signal",
            "setup_board": setup_board,
            "portfolio_brain": self._build_portfolio_brain(action_board),
            "watchlist_impact": [],
            "reddit_posts": [],
            "stocktwits": [],
            "polymarket": polymarket_events[:8],
            "prediction_signals": prediction_signals,
            "prediction_markets": {
                "kalshi_enabled": self._kalshi_enabled,
                "status": "live" if prediction_signals else "watch_only",
                "watched_themes": self._build_prediction_market_watch_themes(event_layer, macro),
                "message": (
                    "Polymarket-Livefeed aktiv: relevante Maerkte werden als Wahrscheinlichkeiten gezeigt."
                    if prediction_signals
                    else "Polymarket-Livefeed liefert gerade keine belastbaren Finance-Maerkte; Makro-Themen bleiben auf Watch."
                ),
            },
            "google_news_extra": [],
            "trading_edge": {},
            "data_status": {
                "mode": "fast",
                "deferred": [
                    "reddit_posts",
                    "stocktwits",
                    "google_news_extra",
                    "earnings_results",
                    "market_movers",
                ],
                "sources": {
                    "polymarket": "loaded" if polymarket_events else "empty_or_unavailable",
                    "broad_earnings": "loaded" if broad_earnings else "empty_or_unavailable",
                    "deep_social": "deferred_fast_mode",
                    "earnings_results": "deferred_fast_mode",
                    "market_movers": "deferred_fast_mode",
                },
            },
        }
        brief["quality"] = self._build_quality_report(brief)
        brief["quality"]["mode"] = "fast"
        self._attach_playbook_context(brief)
        self._cache = brief
        self._cache_time = now
        self._persist_snapshot(brief)
        return self._prepare_brief_for_delivery(brief, watchlist_snapshot)

    def _attach_playbook_context(self, brief: Dict[str, Any]) -> None:
        setup_board = brief.get("setup_board") or {}
        quality = brief.get("quality") or {}
        data_status = brief.get("data_status") or {}
        sources = data_status.get("sources") if isinstance(data_status.get("sources"), dict) else {}
        deferred = data_status.get("deferred") if isinstance(data_status.get("deferred"), list) else []
        missing = quality.get("missing") if isinstance(quality.get("missing"), list) else []
        missing_reasons: List[str] = []

        if brief.get("trade_setups_status") == "insufficient_signal":
            missing_reasons.append("Kein Setup erreicht aktuell Trigger-, Konfidenz- und Datenqualitaet gleichzeitig.")
        if missing:
            missing_reasons.append(f"Qualitaetscheck offen: {', '.join(str(item) for item in missing[:3])}.")
        if deferred:
            missing_reasons.append(f"Fast Mode laedt nach: {', '.join(str(item) for item in deferred[:4])}.")
        delayed_sources = [
            name
            for name, state in sources.items()
            if str(state) not in {"loaded", "ready", "live"}
        ]
        if delayed_sources:
            missing_reasons.append(f"Datenquellen nicht vollstaendig: {', '.join(delayed_sources[:4])}.")

        brief["data_health"] = {
            "mode": data_status.get("mode") or quality.get("mode") or "full",
            "status": "ready" if quality.get("status") == "ready" and not deferred else "refreshing" if deferred else quality.get("status") or "unknown",
            "score": quality.get("score"),
            "missing": missing[:6],
            "deferred": deferred[:8],
            "sources": sources,
        }
        brief["missing_signal_reasons"] = missing_reasons[:4]
        brief["playbook_summary"] = {
            "now": len(setup_board.get("now") or []),
            "next": len(setup_board.get("next") or []),
            "avoid": len(setup_board.get("avoid") or []),
            "data_missing": len(missing_reasons),
            "status": brief.get("trade_setups_status") or "unknown",
            "message": (
                "Setups bereit: Trigger, Zeitfenster und Ungueltig-wenn vor Ausfuehrung pruefen."
                if brief.get("trade_setups")
                else "Keine belastbare Edge: zuerst Datenluecken und fehlende Trigger pruefen."
            ),
        }

    def _build_future_stars_brief(self, fast: bool = False) -> List[Dict[str, Any]]:
        cache_key = "_future_stars_fast" if fast else "_future_stars_full"
        cache_time_key = f"{cache_key}_time"
        cached = getattr(self, cache_key, None)
        cached_at = getattr(self, cache_time_key, None)
        if cached is not None and isinstance(cached_at, datetime):
            if (datetime.now(timezone.utc) - cached_at).total_seconds() < 3600:
                return cached

        universe = ["RKLB", "LUNR", "SOFI", "HOOD", "PATH", "OKLO"] if fast else [
            "RKLB", "LUNR", "SOFI", "HOOD", "PATH", "OKLO", "S", "IONQ", "ASTS", "HIMS",
        ]
        positive_terms = ("contract", "partnership", "approval", "launch", "growth", "beat", "raises", "ai", "space", "customer", "record")
        risk_terms = ("offering", "dilution", "lawsuit", "downgrade", "miss", "delay", "cash burn", "short report")
        candidates: List[Dict[str, Any]] = []
        for ticker in universe:
            try:
                fetcher = DataFetcher(ticker)
                info = fetcher.info or {}
                market_cap = info.get("marketCap") or 0
                if not market_cap or market_cap > 35e9:
                    continue
                fundamentals = fetcher.get_fundamentals()
                revenue_growth = fundamentals.get("revenue_growth") or 0
                profit_margin = fundamentals.get("profit_margin") or 0
                free_cashflow = fundamentals.get("free_cashflow") or 0
                news = fetcher.get_news()
                titles = [str(item.get("title") or item.get("headline") or "") for item in news[:6] if isinstance(item, dict)]
                catalysts = [title for title in titles if any(term in title.lower() for term in positive_terms)]
                risks = [title for title in titles if any(term in title.lower() for term in risk_terms)]
                price = fetcher.get_price_data_fast()
                volatility = fetcher.get_volatility_data()
                change_1m = price.get("change_1m") or 0
                volume_ratio = volatility.get("volume_ratio") or 1
                debt_to_equity = fundamentals.get("debt_to_equity")
                gate_checks = {
                    "growth": revenue_growth >= 0.18,
                    "catalyst": bool(catalysts),
                    "cash_quality": profit_margin > 0 or free_cashflow > 0,
                    "confirmation": change_1m > 0 and volume_ratio >= 1.05,
                    "balance_risk": debt_to_equity is None or debt_to_equity <= 180,
                    "risk_clean": not risks,
                }
                score = 25 + min(26, max(0, revenue_growth) * 95)
                score += 12 if gate_checks["cash_quality"] else -10
                score += 10 if change_1m > 0 else -8
                score += 8 if volume_ratio >= 1.15 else 4 if volume_ratio >= 1.05 else -4
                score += min(25, len(catalysts) * 9)
                score -= min(18, len(risks) * 9)
                if debt_to_equity is not None and debt_to_equity > 180:
                    score -= 12
                score = max(0, min(100, round(score)))
                if score < 62 and not catalysts:
                    continue
                passed_count = sum(1 for passed in gate_checks.values() if passed)
                if (
                    gate_checks["growth"]
                    and gate_checks["catalyst"]
                    and gate_checks["cash_quality"]
                    and gate_checks["confirmation"]
                    and gate_checks["balance_risk"]
                    and score >= 76
                ):
                    quality_gate = "passed"
                elif score >= 66 and gate_checks["catalyst"] and passed_count >= 4:
                    quality_gate = "candidate"
                else:
                    quality_gate = "watch"
                gate_reasons = []
                if not gate_checks["growth"]:
                    gate_reasons.append("Umsatzwachstum noch nicht stark genug")
                if not gate_checks["catalyst"]:
                    gate_reasons.append("harter News-Katalysator fehlt")
                if not gate_checks["cash_quality"]:
                    gate_reasons.append("Cashflow/Profitabilitaet noch schwach")
                if not gate_checks["confirmation"]:
                    gate_reasons.append("Kurs/Volumen bestaetigen noch nicht sauber")
                if not gate_checks["balance_risk"]:
                    gate_reasons.append("Debt-Risiko zu hoch")
                if risks:
                    gate_reasons.append("Risiko-News aktiv")
                candidates.append({
                    "ticker": ticker,
                    "name": info.get("shortName") or info.get("longName") or ticker,
                    "market_cap": market_cap,
                    "score": score,
                    "revenue_growth": revenue_growth * 100 if revenue_growth is not None else None,
                    "profit_margin": profit_margin * 100 if profit_margin is not None else None,
                    "free_cashflow": free_cashflow,
                    "change_1m": change_1m,
                    "volume_ratio": volume_ratio,
                    "quality_gate": quality_gate,
                    "gate_checks": gate_checks,
                    "gate_passed": passed_count,
                    "gate_total": len(gate_checks),
                    "gate_reason": " | ".join(gate_reasons[:3]) if gate_reasons else "Growth, Katalysator, Qualitaet und Bestaetigung passen zusammen.",
                    "catalyst": catalysts[0] if catalysts else "Noch kein harter News-Katalysator; weiter beobachten.",
                    "risk": risks[0] if risks else "",
                })
            except Exception:
                continue
        candidates.sort(key=lambda item: (item.get("quality_gate") != "passed", -(item.get("score") or 0)))
        result = candidates[:5]
        setattr(self, cache_key, result)
        setattr(self, cache_time_key, datetime.now(timezone.utc))
        return result

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
            max(0, int((now_utc - generated_at).total_seconds() // 60))
            if generated_at is not None
            else None
        )
        freshness = (
            "fresh"
            if age_minutes is not None and age_minutes <= 20
            else "recent"
            if age_minutes is not None and age_minutes <= 90
            else "stale"
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
        data_status = brief.get("data_status") if isinstance(brief.get("data_status"), dict) else {}
        deferred = data_status.get("deferred") if isinstance(data_status.get("deferred"), list) else []
        sources = data_status.get("sources") if isinstance(data_status.get("sources"), dict) else {}

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
            "freshness": freshness,
            "missing": missing,
            "checks": checks,
            "mode": data_status.get("mode") or "full",
            "deferred": deferred,
            "sources": sources,
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
        seen_reports: set[tuple[str, str]] = set()
        for feed_url, feed_publisher in self.RSS_FEEDS:
            try:
                parsed = feedparser.parse(feed_url, request_headers={"User-Agent": "Mozilla/5.0"})
                for entry in (parsed.entries or [])[:5]:
                    title = (entry.get("title") or "").strip()
                    link = entry.get("link") or ""
                    report_key = (self._news_identity(title), self._extract_domain(link) or feed_publisher.lower())
                    if not title or report_key in seen_reports:
                        continue
                    # Filter out very old entries (older than 18 hours)
                    published = entry.get("published_parsed")
                    if published:
                        import time as _time
                        age_hours = (_time.time() - _time.mktime(published)) / 3600
                        max_age_hours = 96 if feed_publisher in self.OFFICIAL_PUBLISHERS else 18
                        if age_hours > max_age_hours:
                            continue
                        published_at = datetime.fromtimestamp(_time.mktime(published), timezone.utc).isoformat()
                    else:
                        age_hours = None
                        published_at = None
                    seen_reports.add(report_key)
                    source_summary = self._clean_news_summary(
                        entry.get("summary") or entry.get("description")
                    )
                    text = f"{title} {link}".lower()
                    source_meta = self._source_meta(feed_publisher, link)
                    classification = self._classify_news_signal(text)
                    if (
                        feed_publisher == "U.S. Bureau of Labor Statistics"
                        and title == "Major Economic Indicators Latest Numbers"
                    ):
                        classification = {
                            "impact": "high",
                            "region": "usa",
                            "event_type": "macro_data",
                            "severity": "elevated",
                        }
                    product_catalyst = self._classify_product_catalyst(text)
                    if source_meta["exclude"]:
                        continue
                    if self._is_high_risk_unverified_headline(title, source_meta):
                        continue
                    related_tickers = self._extract_related_news_tickers(text)
                    ticker = related_tickers[0] if len(related_tickers) == 1 else None
                    association_basis = "explicit_title_entity" if related_tickers else "none"
                    if not ticker and not related_tickers and product_catalyst:
                        ticker = product_catalyst.get("ticker")
                        if ticker and ticker not in related_tickers:
                            related_tickers.append(ticker)
                            association_basis = "product_catalyst_alias"
                    news_item = {
                            "ticker": ticker,
                            "related_tickers": related_tickers,
                            "ticker_association_basis": association_basis,
                            "title": title,
                            "publisher": feed_publisher,
                            "link": link,
                            "source_url": link,
                            "source_summary": source_summary,
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
                    items.append(self._enrich_news_item(news_item))
            except Exception:
                continue
        return items

    def _collect_news(self, extra_tickers: List[str] | None = None, fast: bool = False) -> List[Dict[str, Any]]:
        started = perf_time.perf_counter()
        items: List[Dict[str, Any]] = []
        seen_reports: set[tuple[str, str]] = set()
        provider_errors = 0

        # 1. Collect from RSS feeds (real-time, highest priority)
        rss_items = self._collect_rss_news()
        for item in rss_items:
            title = item.get("title") or ""
            identity = self._news_identity(title)
            report_key = (identity, str(item.get("source_domain") or item.get("publisher") or "").lower())
            if title and report_key not in seen_reports:
                seen_reports.add(report_key)
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
            try:
                news = DataFetcher(ticker).get_news()
            except Exception:
                provider_errors += 1
                continue
            for item in news[:per_ticker_limit]:
                title = item.get("title") or ""
                identity = self._news_identity(title)
                publisher = item.get("publisher") or ""
                link = item.get("link")
                source_summary = self._clean_news_summary(item.get("summary"))
                text = f"{title} {link or ''}".lower()
                source_meta = self._source_meta(publisher, link)
                report_key = (identity, str(source_meta.get("domain") or publisher).lower())
                if not title or report_key in seen_reports:
                    continue
                classification = self._classify_news_signal(text)
                product_catalyst = self._classify_product_catalyst(text)
                if source_meta["exclude"]:
                    continue
                if self._is_high_risk_unverified_headline(title, source_meta):
                    continue
                age_hours, published_at = self._news_age(item.get("published_at") or item.get("timestamp"))
                if age_hours is not None and age_hours > 30:
                    continue
                seen_reports.add(report_key)
                explicit_related_tickers = self._extract_related_news_tickers(text)
                resolved_ticker = (
                    explicit_related_tickers[0]
                    if len(explicit_related_tickers) == 1
                    else None
                )
                news_item = {
                        "ticker": resolved_ticker,
                        "related_tickers": explicit_related_tickers,
                        "provider_related_ticker": ticker,
                        "ticker_association_basis": (
                            "explicit_title_entity"
                            if explicit_related_tickers
                            else "provider_related_feed_only"
                        ),
                        "title": title,
                        "publisher": publisher,
                        "link": link,
                        "source_url": link,
                        "source_summary": source_summary,
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
                items.append(self._enrich_news_item(news_item))

        trusted_candidates = [
            item for item in items
            if (
                item.get("is_trusted_source")
                and item.get("source_url")
                and (item.get("source_evidence") or {}).get("link_verified")
                and self._news_relevance_score(item) > 0
            )
        ]
        trusted_items = self._cluster_news_events(trusted_candidates)
        trusted_items.sort(
            key=lambda item: (
                0 if item.get("is_important") else 1,
                -int(item.get("importance_score") or 0),
                -self._news_relevance_score(item),
                0 if item.get("source_quality") == "tier_1" else 1,
                0 if item["impact"] == "high" else 1 if item["impact"] == "medium" else 2,
                0 if item.get("severity") == "critical" else 1 if item.get("severity") == "elevated" else 2,
                item["region"],
            )
        )
        result = trusted_items[:16]
        status = "ok" if result and provider_errors == 0 else "degraded"
        error_code = None
        if provider_errors:
            error_code = "NEWS_PARTIAL_PROVIDER_FAILURE"
        elif not result:
            error_code = "NEWS_EMPTY_RESPONSE"
        record_provider_result(
            "news",
            "rss_yfinance_aggregator",
            "collect_news_fast" if fast else "collect_news",
            status,
            latency_ms=(perf_time.perf_counter() - started) * 1000,
            error_code=error_code,
        )
        return result

    def _news_identity(self, title: str) -> str:
        text = re.sub(r"[^a-z0-9 ]+", " ", str(title or "").lower())
        stop = {"the", "a", "an", "to", "of", "and", "or", "for", "on", "in", "with", "as", "at", "is"}
        tokens = [token for token in text.split() if token not in stop]
        return " ".join(tokens[:12])

    def _extract_related_news_tickers(self, text: str) -> List[str]:
        related = [
            ticker for ticker in self.NEWS_TICKERS
            if self._contains_news_term(text, [ticker])
        ]
        for ticker, aliases in self.NEWS_ENTITY_ALIASES.items():
            if ticker not in related and self._contains_news_term(text, aliases):
                related.append(ticker)
        return related

    def _news_cluster_tokens(self, title: str) -> set[str]:
        text = re.sub(r"[^a-z0-9 ]+", " ", str(title or "").lower())
        stop = {
            "the", "a", "an", "to", "of", "and", "or", "for", "on", "in", "with",
            "as", "at", "is", "are", "be", "by", "from", "after", "before", "amid",
            "says", "said", "report", "reports", "latest", "live", "update", "updates",
            "stock", "stocks", "market", "markets", "shares",
        }
        return {token for token in text.split() if len(token) >= 3 and token not in stop}

    def _same_news_event(self, left: Dict[str, Any], right: Dict[str, Any]) -> bool:
        if str(left.get("event_type") or "") != str(right.get("event_type") or ""):
            return False
        left_tickers = set(left.get("related_tickers") or ([left.get("ticker")] if left.get("ticker") else []))
        right_tickers = set(right.get("related_tickers") or ([right.get("ticker")] if right.get("ticker") else []))
        if left_tickers and right_tickers and not left_tickers.intersection(right_tickers):
            return False
        left_tokens = self._news_cluster_tokens(left.get("title") or "")
        right_tokens = self._news_cluster_tokens(right.get("title") or "")
        overlap = left_tokens.intersection(right_tokens)
        if len(overlap) < 3:
            return False
        union = left_tokens.union(right_tokens)
        jaccard = len(overlap) / max(1, len(union))
        containment = len(overlap) / max(1, min(len(left_tokens), len(right_tokens)))
        return jaccard >= 0.34 or containment >= 0.58

    def _news_headline_stance(self, title: str) -> str:
        text = str(title or "").lower()
        positive = self._contains_news_term(
            text,
            [
                "rises", "rising", "surges", "surging", "soars", "soaring", "jumps", "jumping",
                "beats", "raises guidance", "strong", "approved", "deal reached",
            ],
        )
        negative = self._contains_news_term(
            text,
            [
                "falls", "falling", "drops", "dropping", "slumps", "slumping", "sinks", "sinking",
                "misses", "cuts guidance", "weak", "rejected", "delayed", "warning",
            ],
        )
        if positive and not negative:
            return "positive"
        if negative and not positive:
            return "negative"
        return "neutral"

    def _cluster_news_events(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        clusters: List[List[Dict[str, Any]]] = []
        for item in items:
            matching = next(
                (cluster for cluster in clusters if any(self._same_news_event(item, member) for member in cluster)),
                None,
            )
            if matching is None:
                clusters.append([item])
            else:
                matching.append(item)

        merged: List[Dict[str, Any]] = []
        for cluster in clusters:
            ranked = sorted(
                cluster,
                key=lambda item: (
                    0 if item.get("source_quality") == "tier_1" else 1,
                    0 if item.get("source_summary") else 1,
                    -self._news_relevance_score(item),
                ),
            )
            primary = deepcopy(ranked[0])
            sources: List[Dict[str, Any]] = []
            seen_source_keys: set[tuple[str, str]] = set()
            for report in ranked:
                publisher = str(report.get("publisher") or "Unbekannt").strip()
                domain = str(report.get("source_domain") or "").strip()
                key = (publisher.lower(), domain.lower())
                if key in seen_source_keys:
                    continue
                seen_source_keys.add(key)
                sources.append(
                    {
                        "publisher": publisher,
                        "domain": domain,
                        "url": report.get("source_url") or report.get("link"),
                        "published_at": report.get("published_at"),
                        "quality": report.get("source_quality"),
                        "title": report.get("title"),
                    }
                )

            publisher_count = len({source["publisher"].lower() for source in sources if source["publisher"]})
            domain_count = len({source["domain"].lower() for source in sources if source["domain"]})
            stances = {
                self._news_headline_stance(report.get("title") or "")
                for report in ranked
            } - {"neutral"}
            agreement = "mixed_headline_signal" if len(stances) > 1 else "consistent_or_neutral"
            corroboration = "multi_publisher" if publisher_count >= 2 else "single_source"
            evidence = {
                **(primary.get("source_evidence") or {}),
                "corroboration": corroboration,
                "publisher_count": publisher_count,
                "domain_count": domain_count,
                "source_agreement": agreement,
                "independence_basis": "distinct_publishers" if publisher_count >= 2 else "single_publisher",
                "editorial_independence_verified": False,
                "syndication_checked": False,
            }
            intelligence = {**(primary.get("news_intelligence") or {})}
            score = int(primary.get("importance_score") or intelligence.get("importance_score") or 0)
            if publisher_count >= 2 and agreement == "consistent_or_neutral":
                score = min(25, score + 2)
                if intelligence.get("confidence") in {"niedrig", "mittel"}:
                    intelligence["confidence"] = "mittel"
                intelligence["precision_note"] = (
                    f"{intelligence.get('precision_note', '')} Das Ereignis wird von {publisher_count} "
                    "verschiedenen Publishern berichtet; redaktionelle Unabhängigkeit/Syndizierung ist technisch nicht verifiziert."
                ).strip()
            elif agreement == "mixed_headline_signal":
                intelligence["confidence"] = "offen"
                intelligence["assessment"] = (
                    "Mehrere ähnliche Meldungen zeigen unterschiedliche Richtungssignale. "
                    "Vor einem Trade die Quellen und Marktreaktion gegeneinander prüfen."
                )
                intelligence["precision_note"] = (
                    f"{intelligence.get('precision_note', '')} Möglicher Widerspruch zwischen den Headlines erkannt."
                ).strip()
            intelligence["importance_score"] = score
            primary_title = str(primary.get("title") or "")
            personal_finance = self._contains_news_term(
                primary_title,
                [
                    "retire", "retirees", "inherit", "inherited", "estate", "adviser",
                    "advisor", "401", "credit card", "mortgage", "personal finance", "student loan",
                ],
            )
            important_eligible = bool(
                primary.get("source_quality") == "tier_1"
                and (primary.get("source_url") or primary.get("link"))
                and primary.get("published_at")
                and not personal_finance
            )
            is_important = bool(important_eligible and score >= 12)
            intelligence["is_important"] = is_important
            primary.update(
                {
                    "corroborating_sources": sources,
                    "source_evidence": evidence,
                    "importance_score": score,
                    "is_important": is_important,
                    "news_intelligence": intelligence,
                }
            )
            merged.append(primary)
        return merged

    def _news_benchmark_ticker(self, ticker: str, event_type: str) -> str:
        normalized = str(ticker or "").upper()
        if normalized == "BMW.DE":
            return "^GDAXI"
        if normalized == "QQQ":
            return "SPY"
        if normalized in {"NVDA", "AAPL", "MSFT", "TSLA", "AMZN", "META", "GOOGL", "TTWO"}:
            return "QQQ"
        if normalized == "XLE" or event_type == "energy":
            return "SPY"
        if normalized in {"GLD", "TLT"}:
            return "SPY"
        return "SPY"

    def _attach_news_market_confirmation(
        self,
        news: List[Dict[str, Any]],
        fast: bool = False,
    ) -> List[Dict[str, Any]]:
        enriched = deepcopy(news)
        reaction_limit = 4 if fast else 7
        measured = 0
        for item in enriched:
            if measured >= reaction_limit:
                break
            if item.get("ticker_association_basis") == "provider_related_feed_only":
                continue
            related = list(dict.fromkeys(item.get("related_tickers") or []))
            ticker = str(item.get("ticker") or (related[0] if len(related) == 1 else "")).upper()
            published_at = item.get("published_at")
            if not ticker or not published_at:
                continue
            measured += 1
            event_type = str(item.get("event_type") or "")
            benchmark = self._news_benchmark_ticker(ticker, event_type)
            asset_reaction = DataFetcher(ticker).get_intraday_reaction(published_at)
            if asset_reaction.get("error"):
                item["market_confirmation"] = {
                    "status": "unavailable",
                    "ticker": ticker,
                    "benchmark": benchmark,
                    "reason": asset_reaction.get("error"),
                    "causality_proven": False,
                }
                continue
            benchmark_reaction = DataFetcher(benchmark).get_intraday_reaction(published_at)
            asset_move = asset_reaction.get("change_since_publication")
            benchmark_move = benchmark_reaction.get("change_since_publication")
            relative_move = (
                float(asset_move) - float(benchmark_move)
                if isinstance(asset_move, (int, float)) and isinstance(benchmark_move, (int, float))
                else None
            )
            expected = self._news_headline_stance(item.get("title") or "")
            threshold = 0.35
            if expected == "positive" and isinstance(relative_move, (int, float)):
                status = "confirmed" if relative_move >= threshold else "contradicted" if relative_move <= -threshold else "inconclusive"
            elif expected == "negative" and isinstance(relative_move, (int, float)):
                status = "confirmed" if relative_move <= -threshold else "contradicted" if relative_move >= threshold else "inconclusive"
            else:
                status = "observed_only"
            item["market_confirmation"] = {
                "status": status,
                "expected_headline_direction": expected,
                "ticker": ticker,
                "asset_move_since_publication": asset_move,
                "benchmark": benchmark,
                "benchmark_move_since_publication": benchmark_move,
                "relative_move_since_publication": relative_move,
                "baseline_at": asset_reaction.get("baseline_at"),
                "observed_at": asset_reaction.get("observed_at"),
                "bar_interval": asset_reaction.get("bar_interval"),
                "measurement_basis": asset_reaction.get("measurement_basis"),
                "event_window_aligned": asset_reaction.get("event_window_aligned") is True,
                "causality_proven": False,
                "precision_note": (
                    "Gemessene Preisreaktion ab dem letzten 15-Minuten-Kursbalken vor Veröffentlichung. "
                    "Relative Stärke ist kein Beweis, dass die Meldung die Bewegung verursacht hat."
                ),
            }
        return enriched

    def _find_sec_earnings_filing(self, ticker: str, published_at: Any) -> Dict[str, Any]:
        normalized = str(ticker or "").upper()
        cik = self.SEC_CIK_BY_TICKER.get(normalized)
        if not cik:
            return {"status": "unsupported_ticker"}
        try:
            publication_time = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
            if publication_time.tzinfo is None:
                publication_time = publication_time.replace(tzinfo=timezone.utc)
            publication_date = publication_time.astimezone(timezone.utc).date()
        except Exception:
            return {"status": "invalid_publication_time"}

        cache_key = f"{normalized}:{publication_date.isoformat()}"
        now = datetime.now(timezone.utc)
        cached = self._sec_filing_cache.get(cache_key)
        if cached and (now - cached[1]).total_seconds() < self._sec_filing_ttl_seconds:
            return deepcopy(cached[0])

        explicit_user_agent = str(os.getenv("SEC_USER_AGENT", "")).strip()
        contact_email = str(
            os.getenv("SEC_CONTACT_EMAIL")
            or os.getenv("SMTP_FROM")
            or os.getenv("SMTP_USER")
            or ""
        ).strip()
        if not explicit_user_agent and ("@" not in contact_email or " " in contact_email):
            return {
                "status": "contact_not_configured",
                "authority": "U.S. Securities and Exchange Commission",
                "submissions_url": f"https://data.sec.gov/submissions/CIK{cik}.json",
                "reason": "SEC_CONTACT_EMAIL or SEC_USER_AGENT is required for declared automated access",
            }
        user_agent = explicit_user_agent or f"BrokerFreund/0.9 {contact_email}"
        headers = {
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json,text/html",
        }
        submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        try:
            response = requests.get(submissions_url, headers=headers, timeout=8)
            response.raise_for_status()
            recent = ((response.json().get("filings") or {}).get("recent") or {})
            accessions = recent.get("accessionNumber") or []
            candidates: List[Dict[str, Any]] = []
            for index, accession in enumerate(accessions):
                def field(name: str) -> Any:
                    values = recent.get(name) or []
                    return values[index] if index < len(values) else None

                form = str(field("form") or "")
                filed = str(field("filingDate") or "")
                primary_document = str(field("primaryDocument") or "")
                items = str(field("items") or "")
                if not accession or not filed or not primary_document:
                    continue
                is_results_8k = form == "8-K" and "2.02" in items
                if form not in {"10-Q", "10-K", "6-K"} and not is_results_8k:
                    continue
                try:
                    filed_date = date.fromisoformat(filed)
                except Exception:
                    continue
                distance_days = abs((filed_date - publication_date).days)
                if distance_days > 7:
                    continue
                form_rank = 0 if is_results_8k else 1 if form == "10-Q" else 2 if form == "10-K" else 3
                candidates.append(
                    {
                        "form": form,
                        "accession": accession,
                        "filed_at": filed,
                        "report_date": field("reportDate"),
                        "accepted_at": field("acceptanceDateTime"),
                        "primary_document": primary_document,
                        "items": items,
                        "distance_days": distance_days,
                        "form_rank": form_rank,
                    }
                )
            if not candidates:
                result = {
                    "status": "not_found",
                    "authority": "U.S. Securities and Exchange Commission",
                    "submissions_url": submissions_url,
                }
                self._sec_filing_cache[cache_key] = (result, now)
                return deepcopy(result)

            filing = sorted(candidates, key=lambda candidate: (candidate["distance_days"], candidate["form_rank"]))[0]
            accession_path = str(filing["accession"]).replace("-", "")
            cik_path = str(int(cik))
            document_url = (
                f"https://www.sec.gov/Archives/edgar/data/{cik_path}/"
                f"{accession_path}/{filing['primary_document']}"
            )
            document_response = requests.get(document_url, headers=headers, timeout=8, stream=True)
            verified = document_response.status_code == 200
            document_response.close()
            result = {
                "status": "verified" if verified else "document_unreachable",
                "authority": "U.S. Securities and Exchange Commission",
                "ticker": normalized,
                "cik": cik,
                "form": filing["form"],
                "accession": filing["accession"],
                "filed_at": filing["filed_at"],
                "report_date": filing["report_date"],
                "accepted_at": filing["accepted_at"],
                "items": filing["items"],
                "url": document_url,
                "submissions_url": submissions_url,
                "document_http_status": document_response.status_code,
                "verified_at": now.isoformat() if verified else None,
                "event_match_basis": "ticker_form_and_filing_date_within_7_days",
            }
        except Exception as exc:
            result = {
                "status": "lookup_error",
                "authority": "U.S. Securities and Exchange Commission",
                "submissions_url": submissions_url,
                "reason": str(exc)[:180],
            }
        self._sec_filing_cache[cache_key] = (result, now)
        return deepcopy(result)

    def _attach_news_primary_sources(
        self,
        news: List[Dict[str, Any]],
        fast: bool = False,
    ) -> List[Dict[str, Any]]:
        enriched = deepcopy(news)
        lookup_limit = 2 if fast else 4
        looked_up = 0
        for item in enriched:
            if looked_up >= lookup_limit:
                break
            if str(item.get("event_type") or "") != "earnings":
                continue
            if item.get("ticker_association_basis") == "provider_related_feed_only":
                continue
            ticker = str(item.get("ticker") or "").upper()
            published_at = item.get("published_at")
            if not ticker or not published_at or ticker not in self.SEC_CIK_BY_TICKER:
                continue
            looked_up += 1
            filing = self._find_sec_earnings_filing(ticker, published_at)
            evidence = {**(item.get("source_evidence") or {})}
            evidence["primary_source_lookup"] = filing.get("status")
            if filing.get("status") == "verified":
                evidence["original_document_verified"] = True
                evidence["primary_source_count"] = 1
                item["primary_sources"] = [filing]
                intelligence = {**(item.get("news_intelligence") or {})}
                intelligence["precision_note"] = (
                    f"{intelligence.get('precision_note', '')} Konkretes SEC-{filing.get('form')} "
                    "wurde ticker-, formular- und zeitbezogen gefunden und per HTTP 200 verifiziert; "
                    "die einzelnen Kennzahlen der Publisher-Meldung wurden dadurch nicht automatisch abgeglichen."
                ).strip()
                item["news_intelligence"] = intelligence
            else:
                evidence["original_document_verified"] = False
                item["primary_source_lookup"] = filing
            item["source_evidence"] = evidence
        return enriched

    def _attach_news_decision_readiness(
        self,
        news: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Turn evidence into an explicit, conservative paper-trade verdict.

        This gate deliberately separates a relevant headline from a trade-ready
        event. It never authorizes real-money execution.
        """
        enriched = deepcopy(news)
        labels = {
            "explicit_ticker_missing": "kein eindeutig handelbarer Ticker",
            "ticker_not_explicit_in_title": "Ticker nicht ausdrücklich in der Überschrift zugeordnet",
            "directional_stance_missing": "keine belastbare positive oder negative Richtung",
            "tier_1_source_missing": "Quelle ist nicht Tier 1",
            "verified_source_link_missing": "verifizierter Quellenlink fehlt",
            "publication_timestamp_missing": "Veröffentlichungszeit fehlt",
            "importance_gate_not_met": "Meldung unterschreitet das Wichtigkeits-Gate",
            "source_signal_conflict": "vergleichbare Quellen liefern widersprüchliche Richtungssignale",
            "price_reaction_contradicted": "Kursreaktion widerspricht der Meldungsrichtung",
            "news_age_unavailable": "Meldungsalter ist nicht belastbar",
            "news_older_than_24h": "Meldung ist älter als 24 Stunden",
            "price_confirmation_missing": "richtungskonforme Preisbestätigung fehlt",
            "event_window_not_aligned": "Preisfenster ist nicht an die Veröffentlichung ausgerichtet",
            "earnings_primary_document_missing": "Earnings-Originaldokument ist nicht verifiziert",
        }
        for item in enriched:
            evidence = item.get("source_evidence") if isinstance(item.get("source_evidence"), dict) else {}
            intelligence = item.get("news_intelligence") if isinstance(item.get("news_intelligence"), dict) else {}
            confirmation = item.get("market_confirmation") if isinstance(item.get("market_confirmation"), dict) else {}
            ticker = str(item.get("ticker") or confirmation.get("ticker") or "").upper().strip()
            expected = str(
                confirmation.get("expected_headline_direction")
                or self._news_headline_stance(item.get("title") or "")
                or ""
            ).lower()
            age_hours = item.get("age_hours")
            hard_codes: List[str] = []
            gap_codes: List[str] = []

            if not ticker:
                hard_codes.append("explicit_ticker_missing")
            if str(item.get("ticker_association_basis") or "") != "explicit_title_entity":
                hard_codes.append("ticker_not_explicit_in_title")
            if expected not in {"positive", "negative"}:
                hard_codes.append("directional_stance_missing")
            if str(item.get("source_quality") or evidence.get("quality") or "") != "tier_1":
                hard_codes.append("tier_1_source_missing")
            if evidence.get("link_verified") is not True or not bool(item.get("source_url") or item.get("link")):
                hard_codes.append("verified_source_link_missing")
            if not item.get("published_at"):
                hard_codes.append("publication_timestamp_missing")
            if not (item.get("is_important") is True or intelligence.get("is_important") is True):
                hard_codes.append("importance_gate_not_met")
            if evidence.get("source_agreement") == "mixed_headline_signal":
                hard_codes.append("source_signal_conflict")

            confirmation_status = str(confirmation.get("status") or "")
            if confirmation_status == "contradicted":
                hard_codes.append("price_reaction_contradicted")
            elif confirmation_status != "confirmed":
                gap_codes.append("price_confirmation_missing")
            if confirmation.get("event_window_aligned") is not True:
                gap_codes.append("event_window_not_aligned")
            if str(item.get("event_type") or "") == "earnings" and evidence.get("original_document_verified") is not True:
                gap_codes.append("earnings_primary_document_missing")
            if not isinstance(age_hours, (int, float)) or float(age_hours) < 0:
                hard_codes.append("news_age_unavailable")
            elif float(age_hours) > 24:
                hard_codes.append("news_older_than_24h")

            hard_codes = list(dict.fromkeys(hard_codes))
            gap_codes = list(dict.fromkeys(gap_codes))
            if hard_codes:
                status = "reject"
                action = "Kein Trade. Erst die harten Blocker auflösen; die Wichtigkeit allein ist kein Setup."
            elif gap_codes:
                status = "monitor"
                action = "Beobachten. Paper-Trade erst nach Auflösung aller Verifikationslücken prüfen."
            else:
                status = "ready_for_paper_review"
                action = "Nur für Paper-Review: Entry, Stop und Positionsgröße separat validieren."
            direction = "long" if expected == "positive" else "short" if expected == "negative" else "watch"
            status_label = {
                "ready_for_paper_review": "Paper-Review bereit",
                "monitor": "Beobachten",
                "reject": "Ablehnen",
            }[status]
            summary_parts = [labels[code] for code in hard_codes + gap_codes if code in labels]
            item["decision_readiness"] = {
                "status": status,
                "label": status_label,
                "direction": direction,
                "expected_headline_direction": expected or "undetermined",
                "hard_blocker_codes": hard_codes,
                "hard_blockers": [labels[code] for code in hard_codes],
                "verification_gap_codes": gap_codes,
                "verification_gaps": [labels[code] for code in gap_codes],
                "summary": " · ".join(summary_parts) if summary_parts else "Quellen-, Zeit-, Richtungs- und Preis-Gates erfüllt.",
                "action": action,
                "paper_review_only": status == "ready_for_paper_review",
                "real_money_ready": False,
                "causality_proven": False,
                "precision_note": "Regelbasiertes Evidenz-Gate; keine Renditeprognose und kein Kausalitätsbeweis.",
                "decision_scope": paper_scope() if status == "ready_for_paper_review" else research_scope(),
            }
        return enriched

    def _clean_news_summary(self, value: Any) -> str:
        text = unescape(str(value or ""))
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:700]

    def _news_correction_status(self, item: Dict[str, Any]) -> Dict[str, Any]:
        title = str(item.get("title") or "")
        summary = self._clean_news_summary(item.get("source_summary"))
        haystack = f"{title} {summary}".lower()
        retraction_markers = ("retraction", "retracted", "withdrawn report", "story withdrawn")
        correction_markers = ("correction:", "corrected:", "corrects ", "corrected version")
        if any(marker in haystack for marker in retraction_markers):
            status = "retracted_or_withdrawn"
            signals = [marker for marker in retraction_markers if marker in haystack]
        elif any(marker in haystack for marker in correction_markers):
            status = "correction_detected"
            signals = [marker for marker in correction_markers if marker in haystack]
        else:
            status = "not_detected_at_capture"
            signals = []
        return {
            "status": status,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "signals": signals,
            "monitoring_scope": "headline_and_publisher_summary_at_capture",
            "ongoing_monitor_verified": False,
        }

    def _enrich_news_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        intelligence = self._build_news_intelligence(item)
        source_url = str(item.get("source_url") or item.get("link") or "").strip()
        source_domain = str(item.get("source_domain") or self._extract_domain(source_url))
        source_quality = str(item.get("source_quality") or "unverified")
        published_at = item.get("published_at")
        source_summary = str(item.get("source_summary") or "").strip()
        is_official_primary = bool(
            item.get("source_type") == "official_primary"
            and source_url
            and any(
                source_domain == official or source_domain.endswith(f".{official}")
                for official in self.OFFICIAL_DOMAINS
            )
        )
        reporting_basis = (
            "official_release_summary"
            if is_official_primary and source_summary
            else "official_release_headline"
            if is_official_primary
            else "publisher_summary"
            if source_summary
            else "headline_only"
        )
        evidence = {
            "publisher": item.get("publisher") or "Unbekannt",
            "domain": source_domain,
            "url": source_url,
            "published_at": published_at,
            "quality": source_quality,
            "link_verified": bool(source_url and source_domain),
            "reporting_basis": reporting_basis,
            "corroboration": "single_source",
            "original_document_verified": is_official_primary,
            "primary_source_verification": (
                "official_rss_and_allowlisted_domain" if is_official_primary else None
            ),
            "correction_status": self._news_correction_status(item),
        }
        primary_sources = list(item.get("primary_sources") or [])
        if is_official_primary:
            primary_sources.append(
                {
                    "authority": item.get("publisher"),
                    "form": "Official Release",
                    "url": source_url,
                    "published_at": published_at,
                    "verification_status": "official_rss_and_allowlisted_domain",
                }
            )
        return {
            **item,
            "source_url": source_url,
            "primary_sources": primary_sources,
            "source_evidence": evidence,
            "importance_score": intelligence["importance_score"],
            "is_important": intelligence["is_important"],
            "news_intelligence": intelligence,
        }

    def _build_news_intelligence(self, item: Dict[str, Any]) -> Dict[str, Any]:
        event_type = str(item.get("event_type") or "macro").lower()
        impact = str(item.get("impact") or "low").lower()
        severity = str(item.get("severity") or "normal").lower()
        source_quality = str(item.get("source_quality") or "unverified").lower()
        source_type = str(item.get("source_type") or "publisher").lower()
        source_url = str(item.get("source_url") or item.get("link") or "").strip()
        source_summary = self._clean_news_summary(item.get("source_summary"))
        title = str(item.get("title") or "").strip()
        age_hours = item.get("age_hours")
        published_at = item.get("published_at")

        profiles: Dict[str, Dict[str, Any]] = {
            "central_bank": {
                "meaning": "Die Meldung kann Zinserwartungen und damit Bewertungsmultiplikatoren neu preisen.",
                "channels": ["Staatsanleiherenditen", "US-Dollar", "Index-Futures", "Growth vs. Value"],
                "bull": "Fallende Renditen und ein schwächerer Dollar bestätigen eine risk-on Interpretation.",
                "bear": "Steigende Renditen und ein stärkerer Dollar belasten besonders zinssensitive Wachstumswerte.",
                "confirm": ["Richtung der 2Y-/10Y-Renditen", "DXY-Reaktion", "Bestätigung durch SPY/QQQ nach Eröffnung"],
                "invalidate": "Renditen und Dollar widersprechen der ersten Aktienmarktreaktion.",
                "bias": "reaktionsabhängig",
                "horizon": "Minuten bis 3 Handelstage",
            },
            "macro_data": {
                "meaning": "Entscheidend ist die Abweichung zur Markterwartung, nicht die absolute Zahl allein.",
                "channels": ["Zinserwartungen", "US-Dollar", "Index-Futures", "zyklische Sektoren"],
                "bull": "Daten stützen Wachstum, ohne neue Inflations- oder Zinsangst auszulösen.",
                "bear": "Inflations-/Zinsdruck oder deutliche Wachstumsschwäche dominieren die Reaktion.",
                "confirm": ["Konsensabweichung prüfen", "2Y-Rendite und DXY beobachten", "Marktbreite nach Eröffnung"],
                "invalidate": "Die ersten Zins- und Indexbewegungen werden innerhalb der ersten Stunde vollständig zurückgenommen.",
                "bias": "reaktionsabhängig",
                "horizon": "Minuten bis 2 Handelstage",
            },
            "conflict": {
                "meaning": "Geopolitisches Risiko wirkt primär über Energie, Lieferketten, Inflation und Risikoaufschläge.",
                "channels": ["Öl/Gas", "Gold", "Volatilität", "Transport und Defense"],
                "bull": "Deeskalation oder begrenzte wirtschaftliche Übertragung lässt Risikoaufschläge wieder fallen.",
                "bear": "Ausweitung auf Versorgung, Schifffahrt oder Sanktionen verstärkt den risk-off Impuls.",
                "confirm": ["Brent/WTI und Gold", "VIX und Index-Futures", "offizielle Folgeerklärungen"],
                "invalidate": "Energie und Volatilität bestätigen die Schlagzeile nicht.",
                "bias": "Volatilität / möglicher risk-off Impuls",
                "horizon": "Intraday bis mehrere Wochen",
            },
            "policy": {
                "meaning": "Politikmeldungen werden handelbar, wenn konkrete Umsetzung, Umfang und betroffene Sektoren feststehen.",
                "channels": ["betroffene Branchen", "Währungen", "Inflationserwartungen", "Lieferketten"],
                "bull": "Umsetzung fällt milder aus als eingepreist oder begünstigt klar identifizierbare Sektoren.",
                "bear": "Konkrete Zölle, Sanktionen oder Regulierung erhöhen Kosten und Unsicherheit.",
                "confirm": ["Primärdokument/Behördenstatement", "Sektorrelative Stärke", "Währungs- und Renditereaktion"],
                "invalidate": "Die Meldung bleibt unverbindliche Rhetorik ohne Termin, Umfang oder Marktbestätigung.",
                "bias": "erst nach Umsetzungsdetails",
                "horizon": "Intraday bis mehrere Monate",
            },
            "energy": {
                "meaning": "Die Meldung betrifft Energiepreise und kann über Inflation auf Renditen und Aktienbewertungen wirken.",
                "channels": ["Brent/WTI", "Energieaktien", "Inflationserwartungen", "Transportkosten"],
                "bull": "Öl und Energieaktien halten den Impuls mit Volumen.",
                "bear": "Der Preisschub belastet Konsum/Transport oder fällt nach politischen Gegenmaßnahmen zurück.",
                "confirm": ["Brent/WTI-Futures", "XLE relativ zu SPY", "Volumen und Terminkurve"],
                "invalidate": "Öl gibt den Headline-Impuls schnell wieder ab.",
                "bias": "bedingt energiepositiv",
                "horizon": "Intraday bis mehrere Wochen",
            },
            "earnings": {
                "meaning": "Für die nachhaltige Kurswirkung zählen Guidance, Margen und Erwartungen stärker als der reine EPS-Schlag.",
                "channels": ["Einzelaktie", "Peer Group", "Sektor-ETF", "Optionsvolatilität"],
                "bull": "Guidance und Margenqualität bestätigen den positiven Erstimpuls.",
                "bear": "Schwache Guidance oder Qualitätsprobleme relativieren einen oberflächlichen Beat.",
                "confirm": ["Originalbericht/Investor Relations", "Guidance und Margen", "Preis hält Impuls mit Volumen"],
                "invalidate": "Kurs und Peer Group verwerfen die erste Reaktion.",
                "bias": "nur mit Fundamentaldetails und Preisbestätigung",
                "horizon": "After-hours bis 5 Handelstage",
            },
            "product_catalyst": {
                "meaning": "Produktmeldungen beeinflussen Erwartungen erst nachhaltig, wenn Termin, Nachfrage und wirtschaftlicher Beitrag belastbar sind.",
                "channels": ["Einzelaktie", "Zulieferer", "Analystenschätzungen", "Volumen"],
                "bull": "Offizielle Bestätigung und Nachfrageindikatoren stützen höhere Umsatz-/Margenerwartungen.",
                "bear": "Verzögerung, schwache Nachfrage oder fehlende wirtschaftliche Relevanz dominieren.",
                "confirm": ["Unternehmensquelle", "Termin/Preis/Verfügbarkeit", "Kurs und Volumen"],
                "invalidate": "Keine offizielle Bestätigung oder kein Preis-Follow-through.",
                "bias": "Watchlist bis zur Bestätigung",
                "horizon": "Intraday bis mehrere Monate",
            },
            "public_figure": {
                "meaning": "Eine Aussage ist zunächst Rhetorik; marktbewegend wird sie durch konkrete Maßnahmen oder glaubwürdige Folgequellen.",
                "channels": ["Index-Futures", "betroffene Sektoren", "Währungen", "Volatilität"],
                "bull": "Details reduzieren Unsicherheit oder fallen marktfreundlicher aus als befürchtet.",
                "bear": "Konkrete Maßnahmen erhöhen Kosten, Zinsen oder geopolitische Risiken.",
                "confirm": ["vollständiges Statement/Transkript", "offizielle Folgequelle", "Futures-, Rendite- und Sektorreaktion"],
                "invalidate": "Keine Umsetzung und vollständiger Rücklauf der Marktreaktion.",
                "bias": "keine Richtung ohne Umsetzung",
                "horizon": "Minuten bis mehrere Wochen",
            },
            "ipo": {
                "meaning": "IPO-Meldungen zeigen Risikoappetit, sind aber ohne Bewertung, Free Float und Nachfrage kein breites Kaufsignal.",
                "channels": ["IPO-Aktie", "vergleichbare Unternehmen", "Growth-Sentiment", "Volatilität"],
                "bull": "Solide Nachfrage bei vertretbarer Bewertung und stabilem Handel nach dem Debüt.",
                "bear": "Aggressive Bewertung, kleiner Free Float oder schwacher Sekundärmarkt.",
                "confirm": ["Prospekt/Regulatory Filing", "Preisspanne und Bewertung", "Volumen nach Handelsstart"],
                "invalidate": "Debüt kann Preisniveau trotz hoher Aufmerksamkeit nicht halten.",
                "bias": "beobachten, nicht der Eröffnung hinterherlaufen",
                "horizon": "Debüttag bis mehrere Wochen",
            },
        }
        profile = profiles.get(
            event_type,
            {
                "meaning": "Die Schlagzeile ist ein Kontextsignal; erst Marktreaktion und belastbare Details machen sie handelbar.",
                "channels": ["betroffener Basiswert", "Sektor", "Index-Futures", "Volumen"],
                "bull": "Positive Details werden durch relative Stärke und Volumen bestätigt.",
                "bear": "Negative Details oder fehlende Bestätigung dominieren.",
                "confirm": ["Originalquelle öffnen", "betroffenen Markt prüfen", "Preis und Volumen bestätigen lassen"],
                "invalidate": "Keine Folgequelle und kein nachhaltiger Preisimpuls.",
                "bias": "neutral bis bestätigt",
                "horizon": "Intraday bis 3 Handelstage",
            },
        )

        relevance = self._news_relevance_score(item)
        importance_score = relevance
        importance_score += 3 if impact == "high" else 1 if impact == "medium" else 0
        importance_score += 2 if severity == "critical" else 1 if severity == "elevated" else 0
        importance_score += 2 if source_quality == "tier_1" else 0
        importance_score += 1 if source_url else 0
        importance_score += 1 if published_at else 0
        if isinstance(age_hours, (int, float)):
            importance_score += 1 if age_hours <= 6 else 0
            importance_score -= 2 if age_hours > 24 else 0
        importance_score = max(0, min(25, int(importance_score)))
        is_personal_finance = self._contains_news_term(
            title,
            [
                "retire",
                "retirees",
                "inherit",
                "inherited",
                "estate",
                "adviser",
                "advisor",
                "401",
                "credit card",
                "mortgage",
                "personal finance",
                "student loan",
            ],
        )
        is_important = bool(
            importance_score >= 12
            and source_quality == "tier_1"
            and source_url
            and published_at
            and not is_personal_finance
        )
        confidence = (
            "hoch"
            if source_quality == "tier_1" and source_url and published_at and isinstance(age_hours, (int, float)) and age_hours <= 12
            else "mittel"
            if source_quality in {"tier_1", "tier_2"} and source_url
            else "niedrig"
        )
        fact_basis = (
            "official_release_summary"
            if source_type == "official_primary" and source_summary
            else "official_release_headline"
            if source_type == "official_primary"
            else "publisher_summary"
            if source_summary
            else "headline_only"
        )
        fact_summary = source_summary or title
        assessment = (
            "Hohe Relevanz: sofort auf Marktbestätigung und Folgedetails prüfen."
            if is_important
            else "Relevantes Kontextsignal, aber noch kein eigenständiges Trade-Signal."
        )
        precision_note = (
            "Faktenbasis ist die offizielle Behörden-Zusammenfassung; Einordnung und Szenarien sind Analyse."
            if fact_basis == "official_release_summary"
            else "Faktenbasis ist die Überschrift einer offiziellen Behördenmeldung; Details in der Primärquelle prüfen."
            if fact_basis == "official_release_headline"
            else "Faktenbasis ist die Publisher-Zusammenfassung; Einordnung und Szenarien sind Analyse."
            if fact_basis == "publisher_summary"
            else "Faktenbasis ist nur die Überschrift; Details vor einer Trading-Entscheidung in der Quelle prüfen."
        )
        return {
            "fact_summary": fact_summary[:700],
            "fact_basis": fact_basis,
            "meaning": profile["meaning"],
            "market_channels": profile["channels"],
            "bull_case": profile["bull"],
            "bear_case": profile["bear"],
            "confirmation": profile["confirm"],
            "invalidation": profile["invalidate"],
            "directional_bias": profile["bias"],
            "execution_horizon": profile["horizon"],
            "assessment": assessment,
            "confidence": confidence,
            "importance_score": importance_score,
            "is_important": is_important,
            "precision_note": precision_note,
            "evidence_layers": {
                "schema_version": "1.0",
                "facts": {
                    "summary": fact_summary[:700],
                    "basis": fact_basis,
                    "source_type": source_type,
                },
                "interpretation": {
                    "meaning": profile["meaning"],
                    "assessment": assessment,
                    "directional_bias": profile["bias"],
                    "execution_horizon": profile["horizon"],
                    "market_channels": profile["channels"],
                },
                "uncertainty": {
                    "counterargument": profile["bear"],
                    "confirmation_needed": profile["confirm"],
                    "invalidation": profile["invalidate"],
                    "confidence": confidence,
                    "precision_note": precision_note,
                },
            },
        }

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
        if event_type in {"conflict", "central_bank", "energy", "policy", "public_figure", "ipo", "macro_data", "earnings", "product_catalyst"}:
            score += 4
        if self._contains_news_term(title, [
            "fed", "federal reserve", "fomc", "rate", "yield", "inflation",
            "consumer price index", "cpi", "producer price index", "ppi",
            "gdp", "gross domestic product", "personal income and outlays", "pce",
            "employment situation", "jobs", "payrolls", "unemployment",
            "earnings", "guidance", "upgrade", "downgrade", "oil", "opec", "war",
            "tariff", "sanction", "market", "stock", "futures", "nasdaq", "s&p",
            "dow", "dollar", "gold", "bitcoin", "crypto", "launch", "unveil", "delay",
            "postpone", "iphone", "gpu", "gta", "model", "product", "preorder",
            "ipo", "listing", "debut", "files for ipo", "prices shares",
        ]):
            score += 3
        if self._is_market_moving_person_statement(title):
            score += 5
        if self._is_ipo_headline(title):
            score += 5
        if self._contains_news_term(title, [
            "retire", "retirees", "retirement", "inherit", "inherited", "estate", "adviser", "advisor",
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
                or "Der Makro-Katalysator ist aktiv."
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
                    hedge_idea = "TLT / Liquiditätspuffer"
                else:
                    hedge_idea = "Gesamtrisiko reduzieren"
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

    def _build_macro_event_ping_fallback(self, macro: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
        """Create transparent watch pings when no hard geo/event headline is active."""
        now = datetime.now(timezone.utc)
        rows: List[Dict[str, Any]] = []
        macro = macro or []
        candidates = [
            ("CL=F", "energy", "Öl-Impuls beobachten", "Öl und Energieaktien bestätigen gemeinsam.", "Öl verliert den Impuls oder XLE bestätigt nicht.", ["XLE", "CVX", "OXY"]),
            ("GC=F", "conflict", "Gold-Absicherung beobachten", "Gold bleibt gefragt, während Indizes oder Renditen Stress zeigen.", "Gold dreht und der VIX bleibt begrenzt.", ["GLD", "NEM"]),
            ("^TNX", "central_bank", "Renditen beobachten", "Renditen, Dollar und Nasdaq-Futures bewegen sich gemeinsam.", "Renditen bewegen sich ohne Bestätigung durch Aktien.", ["TLT", "QQQ"]),
            ("DX-Y.NYB", "policy", "Dollar-Druck beobachten", "Dollar-Stärke belastet Risikoanlagen und internationale Konzerne.", "Die Dollar-Bewegung lässt vor der US-Eröffnung nach.", ["UUP", "SPY"]),
        ]
        lookup = {str(item.get("symbol") or "").upper(): item for item in macro}
        for symbol, event_type, title, trigger, invalidation, symbols in candidates:
            asset = lookup.get(symbol.upper())
            change = asset.get("change_1d") if isinstance(asset, dict) else None
            if isinstance(change, (int, float)) and abs(change) < 0.12:
                continue
            rows.append(
                {
                    "id": f"watch:{event_type}:{int(now.timestamp())}",
                    "type": event_type,
                    "severity": "normal",
                    "region": "global",
                    "symbols": symbols,
                    "started_at": now.isoformat(),
                    "confidence": 45,
                    "title": title,
                    "source_status": "watch_fallback",
                    "trade_impact": {
                        "action": "watch",
                        "baseline_scenario": "Kein belastbarer Schlagzeilen-Alarm ist aktiv, dieser Makro-Indikator bleibt aber beobachtenswert.",
                        "symbols": symbols,
                        "trigger": trigger,
                        "invalidation": invalidation,
                        "window": "Heute",
                        "hedge_idea": "Gesamtrisiko bis zur Bestätigung kleiner halten.",
                    },
                }
            )
            if len(rows) >= 3:
                break
        return rows

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
                    "trigger": "Offizielle Bestätigung plus Anschlussbewegung bei Kurs und Volumen.",
                    "invalidation": "Das Gerücht verliert Wirkung, das Unternehmen widerspricht oder der erste Impuls dreht vollständig.",
                }
            )
        return catalysts[:6]

    def _build_product_watch_fallback(self, watchlist_tickers: List[str] | None = None) -> List[Dict[str, Any]]:
        """Keep product radar visible without pretending a fresh headline exists."""
        priority = list(dict.fromkeys([*(watchlist_tickers or []), "NVDA", "AAPL", "TTWO", "BMW.DE", "TSLA"]))
        themes = {
            "NVDA": "GPU / AI chip cycle",
            "AAPL": "iPhone / device cycle",
            "TTWO": "GTA 6 / release timing",
            "BMW.DE": "Neue Klasse / EV launch",
            "TSLA": "Robotaxi / vehicle refresh",
            "MSFT": "Copilot / Azure AI",
            "AMZN": "AWS / Anthropic",
            "META": "AI devices / ads",
            "GOOGL": "Gemini / Search / Waymo",
        }
        rows: List[Dict[str, Any]] = []
        seen = set()
        for raw in priority:
            ticker = (raw or "").upper().strip()
            if not ticker or ticker in seen or ticker not in themes:
                continue
            seen.add(ticker)
            rows.append(
                {
                    "ticker": ticker,
                    "title": f"{themes[ticker]} watch",
                    "theme": themes[ticker],
                    "catalyst_type": "watch_fallback",
                    "direction_hint": "watch",
                    "publisher": "Internal radar",
                    "link": "",
                    "impact": "watch",
                    "confidence": 42,
                    "source_status": "no_fresh_headline",
                    "trigger": "Only promote to setup after a trusted headline, official confirmation, volume and price follow-through.",
                    "invalidation": "Ignore if the story remains rumour-only or price does not react.",
                }
            )
            if len(rows) >= 4:
                break
        return rows

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

    def collect_market_movers_for_delivery(
        self,
        extra_tickers: List[str] | None = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Build deterministic 1-day movers for time-sensitive session delivery.

        A single threaded batch request is materially faster than loading company
        metadata one ticker at a time. The result deliberately ranks only the
        configured universe plus the user's watchlist and never substitutes a
        weekly move when today's move is unavailable.
        """
        now = datetime.now(timezone.utc)
        if (
            self._market_movers_cache is not None
            and (now - self._market_movers_cache[1]).total_seconds() < self._market_movers_ttl_seconds
        ):
            cached = self._market_movers_cache[0]
            cached_daily = [
                row
                for row in [*(cached.get("gainers") or []), *(cached.get("losers") or [])]
                if isinstance(row.get("change_1d"), (int, float))
            ]
            cached_gainers = sorted(
                [row for row in cached_daily if float(row.get("change_1d") or 0) > 0],
                key=lambda row: float(row.get("change_1d") or 0),
                reverse=True,
            )[:8]
            cached_losers = sorted(
                [row for row in cached_daily if float(row.get("change_1d") or 0) < 0],
                key=lambda row: float(row.get("change_1d") or 0),
            )[:8]
            if cached_gainers or cached_losers:
                return {"gainers": cached_gainers, "losers": cached_losers}

        symbols = []
        for raw in [*(extra_tickers or []), *self.MARKET_MOVER_UNIVERSE]:
            ticker = str(raw or "").upper().strip()
            if (
                ticker
                and ticker not in symbols
                and not ticker.startswith("^")
                and not ticker.endswith("=F")
                and not ticker.endswith("-USD")
            ):
                symbols.append(ticker)
        if not symbols:
            return {"gainers": [], "losers": []}

        frame = yf.download(
            symbols,
            period="7d",
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
            timeout=8,
        )
        rows: List[Dict[str, Any]] = []
        for ticker in symbols:
            try:
                if isinstance(frame.columns, pd.MultiIndex):
                    closes = frame[ticker]["Close"].dropna()
                else:
                    closes = frame["Close"].dropna()
                if len(closes) < 2:
                    continue
                previous_close = float(closes.iloc[-2])
                latest_close = float(closes.iloc[-1])
                if not previous_close or not pd.notna(previous_close) or not pd.notna(latest_close):
                    continue
                change_1d = ((latest_close / previous_close) - 1.0) * 100.0
                rows.append(
                    {
                        "ticker": ticker,
                        "name": ticker,
                        "price": latest_close,
                        "change_1d": change_1d,
                        "mover_window": "1d",
                        "as_of": now.isoformat(),
                    }
                )
            except (KeyError, TypeError, ValueError, IndexError):
                continue

        gainers = sorted(
            [row for row in rows if float(row.get("change_1d") or 0) > 0],
            key=lambda row: float(row.get("change_1d") or 0),
            reverse=True,
        )[:8]
        losers = sorted(
            [row for row in rows if float(row.get("change_1d") or 0) < 0],
            key=lambda row: float(row.get("change_1d") or 0),
        )[:8]
        payload = {"gainers": gainers, "losers": losers}
        self._market_movers_cache = (payload, now)
        return payload

    def _build_learning_bias(self) -> Dict[str, Any]:
        """Build transparent ranking nudges from evaluated forecast outcomes."""
        try:
            outcomes = self._get_portfolio_manager().list_signal_forecast_outcomes(limit=1000)
        except Exception:
            return {"source": {}, "setup_type": {}, "summary": []}

        evaluated = [item for item in outcomes if item.get("status") == "evaluated"]
        if not evaluated:
            return {"source": {}, "setup_type": {}, "summary": []}

        source_bias = self._quality_bias(evaluated, "source_label")
        setup_bias = self._quality_bias(evaluated, "setup_type")
        summary: List[Dict[str, Any]] = []
        for label, payload in sorted(source_bias.items(), key=lambda row: abs(row[1].get("score_delta", 0)), reverse=True)[:4]:
            if payload.get("evaluated", 0) < 3:
                continue
            summary.append(
                {
                    "axis": "source",
                    "label": label,
                    "hit_rate": payload.get("hit_rate"),
                    "score_delta": payload.get("score_delta"),
                    "reason": payload.get("reason"),
                }
            )
        for label, payload in sorted(setup_bias.items(), key=lambda row: abs(row[1].get("score_delta", 0)), reverse=True)[:4]:
            if payload.get("evaluated", 0) < 3:
                continue
            summary.append(
                {
                    "axis": "setup_type",
                    "label": label,
                    "hit_rate": payload.get("hit_rate"),
                    "score_delta": payload.get("score_delta"),
                    "reason": payload.get("reason"),
                }
            )
        return {"source": source_bias, "setup_type": setup_bias, "summary": summary[:6]}

    def _quality_bias(self, outcomes: List[Dict[str, Any]], key: str) -> Dict[str, Dict[str, Any]]:
        buckets: Dict[str, List[Dict[str, Any]]] = {}
        for item in outcomes:
            buckets.setdefault(str(item.get(key) or "unknown"), []).append(item)

        bias: Dict[str, Dict[str, Any]] = {}
        for label, items in buckets.items():
            hits = [item for item in items if item.get("result") == "hit"]
            misses = [item for item in items if item.get("result") == "miss"]
            hit_base = len(hits) + len(misses)
            if len(items) < 3 or hit_base == 0:
                delta = 0.0
                reason = "Not enough evaluated outcomes yet."
            else:
                hit_rate = (len(hits) / hit_base) * 100
                if hit_rate >= 65:
                    delta = 5.0
                    reason = "Recent outcomes support a higher ranking."
                elif hit_rate <= 35:
                    delta = -6.0
                    reason = "Recent outcomes require stricter confirmation."
                else:
                    delta = 0.0
                    reason = "Recent outcomes are neutral."
            hit_rate = round((len(hits) / max(1, hit_base)) * 100, 1)
            bias[label] = {
                "evaluated": len(items),
                "hit_rate": hit_rate,
                "score_delta": delta,
                "reason": reason,
            }
        return bias

    def _learning_adjustment(
        self,
        learning_bias: Dict[str, Any],
        setup_type: str,
        source_label: str,
    ) -> Dict[str, Any]:
        source_payload = (learning_bias.get("source") or {}).get(source_label) or {}
        setup_payload = (learning_bias.get("setup_type") or {}).get(setup_type) or {}
        source_delta = float(source_payload.get("score_delta") or 0)
        setup_delta = float(setup_payload.get("score_delta") or 0)
        score_delta = max(-8.0, min(8.0, source_delta + setup_delta))
        reasons = [
            value
            for value in [
                source_payload.get("reason") if source_delta else None,
                setup_payload.get("reason") if setup_delta else None,
            ]
            if value
        ]
        return {
            "source_label": source_label,
            "setup_type": setup_type,
            "score_delta": round(score_delta, 2),
            "source_hit_rate": source_payload.get("hit_rate"),
            "setup_hit_rate": setup_payload.get("hit_rate"),
            "reason": " ".join(reasons) if reasons else "No learning bias applied yet.",
        }

    def _infer_setup_source_label(self, item: Dict[str, Any]) -> str:
        if item.get("congress_signal"):
            return "congress_watch"
        if item.get("product_catalyst"):
            return "product_news"
        setup_source = str(item.get("setup_source") or item.get("source") or "").lower()
        if "earning" in setup_source:
            return "earnings"
        if setup_source:
            return setup_source
        return "morning_brief"

    def _build_trade_setups(
        self,
        action_board: List[Dict[str, Any]],
        news: List[Dict[str, Any]],
        market_movers: Dict[str, List[Dict[str, Any]]] | None = None,
        learning_bias: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        learning_bias = learning_bias or {"source": {}, "setup_type": {}, "summary": []}
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
            trust = {"tier_1": 1.0, "official_house_ptr": 0.92, "tier_2": 0.78, "crowd": 0.45, "excluded": 0.2}.get(
                str(item.get("source_quality") or source_item.get("source_quality") or "tier_2"),
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
            setup_source = str(item.get("setup_source") or "single_name")
            learning_adjustment = self._learning_adjustment(learning_bias, setup_source, self._infer_setup_source_label(item))
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
                            (item.get("congress_signal") or {}).get("signal_grade"),
                            (item.get("product_catalyst") or {}).get("theme"),
                        ]
                        if value
                    ],
                    "product_catalyst": item.get("product_catalyst"),
                    "congress_signal": item.get("congress_signal"),
                    "setup_type": setup_source,
                    "learning_adjustment": learning_adjustment,
                    "direction": item.get("setup"),
                    "_score": round(
                        score
                        + conviction_rank * 8
                        + (4 if setup_source == "single_name" else 0)
                        + float(learning_adjustment.get("score_delta") or 0),
                        2,
                    ),
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
                learning_adjustment = self._learning_adjustment(learning_bias, "market_mover", "market_mover")
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
                        "learning_adjustment": learning_adjustment,
                        "_score": round(
                            52
                            + min(abs_move, 15) * 2.2
                            + (6 if is_gainer else 3)
                            + float(learning_adjustment.get("score_delta") or 0),
                            2,
                        ),
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

    def _build_setup_board(self, trade_setups: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        buckets: Dict[str, List[Dict[str, Any]]] = {"now": [], "next": [], "avoid": []}
        for setup in trade_setups or []:
            direction = str(setup.get("direction") or "").lower()
            quality = str(setup.get("decision_quality") or "").lower()
            confidence = int(setup.get("confidence") or 0)
            if direction in {"short", "watch-short", "hedge", "rebound_or_avoid"}:
                target_bucket = "avoid"
            elif quality == "high conviction" and confidence >= 80:
                target_bucket = "now"
            else:
                target_bucket = "next"

            if len(buckets[target_bucket]) >= 3:
                continue
            buckets[target_bucket].append(
                {
                    "symbol": setup.get("symbol"),
                    "thesis": setup.get("thesis"),
                    "trigger": setup.get("trigger"),
                    "invalidation": setup.get("invalidation"),
                    "confidence": setup.get("confidence"),
                    "decision_quality": setup.get("decision_quality"),
                    "size_guidance": setup.get("size_guidance"),
                    "expected_move": setup.get("expected_move"),
                    "rank": setup.get("rank"),
                    "window": setup.get("window"),
                }
            )
        return buckets

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
        finance_terms = (
            "fed", "rate", "rates", "inflation", "cpi", "ppi", "gdp", "recession",
            "stock", "stocks", "market", "nasdaq", "s&p", "spx", "dow", "earnings",
            "bitcoin", "crypto", "ethereum", "oil", "opec", "gold", "dollar",
            "tariff", "trade", "election", "powell", "treasury", "bond", "yield",
            "unemployment", "jobs", "fomc", "ecb", "china", "war", "conflict",
        )
        signals: List[Dict[str, Any]] = []
        for event in polymarket_events or []:
            question = str(event.get("question") or "").strip()
            if not question:
                continue
            question_lc = question.lower()
            if not any(term in question_lc for term in finance_terms):
                continue
            probability = self._normalize_probability(event.get("probability_yes"))
            if probability is None:
                continue
            volume_usd = self._safe_float(event.get("volume_usd")) or 0.0
            relevance = max(10, min(100, int(self._event_relevance_score({"title": question}) * 60 + (volume_usd / 2_000_000))))
            if relevance < 18 and volume_usd < 250_000:
                continue
            signal_status = "active" if relevance >= 28 else "watch"
            signals.append(
                {
                    "source": "polymarket",
                    "market": question,
                    "probability": probability,
                    "delta_24h": None,
                    "relevance": relevance,
                    "signal_status": signal_status,
                    "volume_usd": volume_usd,
                    "end_date": event.get("end_date"),
                    "url": event.get("url"),
                    "why": (
                        "Relevance, volume and macro/market keywords are strong enough for the briefing signal rail."
                        if signal_status == "active"
                        else "Visible watch item: market is relevant enough to monitor, but not strong enough for a trade setup."
                    ),
                }
            )

        signals.sort(key=lambda row: (row.get("signal_status") == "active", row.get("relevance", 0)), reverse=True)
        return signals[:8]

    def _build_prediction_market_watch_themes(
        self,
        event_layer: List[Dict[str, Any]] | None,
        macro: List[Dict[str, Any]] | None,
    ) -> List[Dict[str, Any]]:
        themes: List[Dict[str, Any]] = []
        seen = set()

        for event in (event_layer or [])[:5]:
            event_type = str(event.get("event_type") or "macro").replace("_", " ").title()
            title = str(event.get("title") or event_type)
            key = event_type.lower()
            if key in seen:
                continue
            seen.add(key)
            themes.append(
                {
                    "theme": event_type,
                    "why": title[:140],
                    "status": "watching",
                    "source": "event_layer",
                }
            )

        macro_lookup = {str(item.get("symbol") or "").upper(): item for item in (macro or [])}
        for symbol, label in [("CL=F", "Oil / inflation"), ("BTC-USD", "Crypto risk"), ("GC=F", "Gold hedge"), ("DX-Y.NYB", "Dollar pressure")]:
            if label.lower() in seen:
                continue
            asset = macro_lookup.get(symbol)
            move = asset.get("change_1d") if asset else None
            if asset and isinstance(move, (int, float)) and abs(move) < 0.15:
                continue
            seen.add(label.lower())
            themes.append(
                {
                    "theme": label,
                    "why": f"{symbol} bewegt sich auffaellig und kann Prediction-Market-Relevanz bekommen." if asset else f"{label} bleibt im Makro-Watch.",
                    "status": "watching",
                    "source": "macro_assets",
                }
            )
            if len(themes) >= 5:
                break

        if not themes:
            themes.append(
                {
                    "theme": "Fed / rates / inflation",
                    "why": "Standard-Makro-Set fuer Polymarket-Relevanz, bis der Live-Feed wieder belastbare Treffer liefert.",
                    "status": "watching",
                    "source": "fallback_watch",
                }
            )
        return themes[:5]

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

    def _build_earnings_watch_fallback(self, watchlist_snapshot: Dict[str, Any] | None) -> List[Dict[str, Any]]:
        tickers: List[str] = []
        watched_tickers = set()
        if watchlist_snapshot:
            for item in watchlist_snapshot.get("items", []):
                if item.get("kind") != "ticker":
                    continue
                value = (item.get("value") or "").upper().strip()
                if value:
                    tickers.append(value)
                    watched_tickers.add(value)
        tickers.extend(["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA", "AMD"])

        entries: List[Dict[str, Any]] = []
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
            company = normalized
            region = "global"
            try:
                info = DataFetcher(normalized).info or {}
                company = info.get("shortName") or info.get("longName") or normalized
                region = self._region_from_country(info.get("country"))
            except Exception:
                pass
            entries.append(
                {
                    "ticker": normalized,
                    "company": company,
                    "scheduled_for": None,
                    "session": "monitoring",
                    "days_until": None,
                    "importance": "watchlist" if normalized in watched_tickers else "market",
                    "region": region,
                    "date_status": "provider_pending",
                    "summary": "Noch kein belastbares Earnings-Datum vom Datenprovider. Wird weiter fuer Ueberraschung, Guidance und Umsatztrend beobachtet.",
                }
            )
            if len(entries) >= 8:
                break
        return entries

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
        stale_references: List[Dict[str, Any]] = []
        max_age_days = int(os.getenv("BRIEF_EARNINGS_RESULT_MAX_AGE_DAYS", "10"))
        stale_max_age_days = int(os.getenv("BRIEF_EARNINGS_RESULT_STALE_MAX_AGE_DAYS", "420"))
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
                if days_since < 0:
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
                freshness = "fresh" if days_since <= max_age_days else "stale_reference"
                if freshness == "stale_reference":
                    if days_since > stale_max_age_days:
                        continue
                    action_hint = "stale_reference_only"
                    summary = (
                        f"Letzte bekannte Zahlen sind {days_since} Tage alt. "
                        f"Nicht als frisches Setup nutzen; nur Kontext fuer Qualitaet, Bewertung und naechste Earnings-Erwartung. "
                        f"{summary}"
                    )
                info = fetcher.info or {}
                row = {
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
                    "freshness": freshness,
                    "action_hint": action_hint,
                    "summary": summary,
                    "source": "yfinance_earnings_dates",
                }
                if freshness == "fresh":
                    results.append(row)
                else:
                    stale_references.append(row)
            except Exception:
                continue

        def sort_key(item: Dict[str, Any]) -> tuple:
            surprise = item.get("eps_surprise_pct")
            surprise_abs = abs(float(surprise)) if isinstance(surprise, (int, float)) else 0.0
            status_rank = {"beat": 3, "miss": 2, "inline": 1}.get(str(item.get("status")), 0)
            return (status_rank, surprise_abs)

        results.sort(key=sort_key, reverse=True)
        if results:
            return results[:6]
        stale_references.sort(key=sort_key, reverse=True)
        return stale_references[:4]

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

        congress_items = self._build_congress_action_items(watchlist_snapshot)
        for item in congress_items:
            signature = f"{item.get('ticker') or 'congress'}:{item.get('setup')}:{item.get('event_type')}:{item.get('title')}"
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            board.append(item)

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
        board.sort(
            key=lambda item: (
                0 if item.get("source_quality") == "official_house_ptr" else 1,
                0 if item.get("impact") == "high" else 1 if item.get("impact") == "medium" else 2,
                -int((item.get("event_intelligence") or {}).get("confidence_score") or 0),
            )
        )
        return board[:8]

    def _build_congress_action_items(
        self,
        watchlist_snapshot: Dict[str, Any] | None,
    ) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        snapshot = watchlist_snapshot or {}
        for signal in (snapshot.get("politician_signals") or [])[:8]:
            trades = signal.get("trades") or []
            if not trades:
                continue
            latest = trades[0]
            ticker = str(latest.get("ticker") or "").upper()
            if not ticker:
                continue
            playbook = signal.get("playbook") or {}
            setup_raw = str(playbook.get("setup") or "watch").lower()
            setup = {
                "copy-long": "long",
                "watch-short": "short",
            }.get(setup_raw, "watch")
            delay = latest.get("delay_days")
            amount_midpoint = latest.get("amount_midpoint")
            is_large = isinstance(amount_midpoint, (int, float)) and amount_midpoint >= 50_000
            is_fresh = isinstance(delay, int) and delay <= 20
            impact = "high" if is_fresh and is_large else "medium" if is_fresh or is_large else "low"
            severity = "elevated" if impact in {"high", "medium"} else "normal"
            intelligence = self._build_event_intelligence(
                event_type="congress_trade",
                impact=impact,
                severity=severity,
                source_quality="official_house_ptr",
                ticker=ticker,
            )
            confidence = int(playbook.get("confidence") or intelligence.get("confidence_score") or 68)
            intelligence["confidence_score"] = max(intelligence.get("confidence_score") or 0, confidence)
            if setup in {"long", "short"}:
                intelligence["action"] = setup
                intelligence["decision_quality"] = "selective" if confidence >= 72 else "tactical only"
                intelligence["size_guidance"] = "reduced risk"
                intelligence["execution_bias"] = "follow strength" if setup == "long" else "fade weakness"
            intelligence["trigger"] = playbook.get("trigger") or intelligence.get("trigger")
            intelligence["invalidation"] = playbook.get("invalidation") or intelligence.get("invalidation")
            intelligence["why_now"] = playbook.get("thesis") or intelligence.get("why_now")
            intelligence["execution_window"] = "today / next 3 sessions"
            name = signal.get("name") or "Congress member"
            action = str(latest.get("action") or "trade").upper()
            amount = latest.get("amount_range") or playbook.get("estimated_exposure_label") or "amount offen"
            items.append(
                {
                    "title": f"Congress Watch: {name} {action} {ticker} ({amount})",
                    "region": "usa",
                    "ticker": ticker,
                    "original_ticker": ticker,
                    "event_type": "congress_trade",
                    "impact": impact,
                    "setup": setup,
                    "setup_source": "congress_ptr",
                    "leverage": playbook.get("leverage") or "avoid",
                    "thesis": playbook.get("thesis") or f"Official delayed PTR filing touches {ticker}.",
                    "trigger": playbook.get("next_action") or playbook.get("trigger") or "Compare current price versus the reported trade date before acting.",
                    "risk": playbook.get("invalidation") or "Official PTR data is delayed; invalid if the move already played out.",
                    "source": "Official House PTR",
                    "source_quality": "official_house_ptr",
                    "link": latest.get("source_url") or signal.get("source_url"),
                    "congress_signal": {
                        "name": name,
                        "action": latest.get("action"),
                        "trade_date": latest.get("trade_date"),
                        "notification_date": latest.get("notification_date"),
                        "delay_days": delay,
                        "amount_range": latest.get("amount_range"),
                        "signal_grade": playbook.get("signal_grade"),
                        "freshness": playbook.get("freshness"),
                        "top_tickers": playbook.get("top_tickers") or [],
                        "compliance_note": playbook.get("compliance_note"),
                    },
                    "event_intelligence": intelligence,
                    "portfolio_exposure": self._build_portfolio_exposure(
                        ticker,
                        watchlist_snapshot,
                        intelligence,
                    ),
                }
            )
        items.sort(
            key=lambda item: (
                0 if item.get("impact") == "high" else 1 if item.get("impact") == "medium" else 2,
                -int((item.get("event_intelligence") or {}).get("confidence_score") or 0),
            )
        )
        return items[:4]

    def _build_congress_watch(self, action_board: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        congress_items = [
            item for item in action_board
            if item.get("setup_source") == "congress_ptr" or item.get("event_type") == "congress_trade"
        ]
        watch: List[Dict[str, Any]] = []
        for item in congress_items[:6]:
            signal = item.get("congress_signal") or {}
            intelligence = item.get("event_intelligence") or {}
            delay = signal.get("delay_days")
            confidence = int(intelligence.get("confidence_score") or 0)
            ticker = item.get("ticker")
            setup = item.get("setup") or "watch"
            action = signal.get("action") or setup
            amount = signal.get("amount_range") or "amount offen"
            freshness = signal.get("freshness") or ("fresh" if isinstance(delay, int) and delay <= 20 else "delayed")
            delay_bucket = (
                "fresh" if isinstance(delay, int) and delay <= 10
                else "usable" if isinstance(delay, int) and delay <= 30
                else "stale" if isinstance(delay, int)
                else "offen"
            )
            setup_quality = (
                "strong" if item.get("impact") == "high" and confidence >= 72
                else "selective" if item.get("impact") in {"high", "medium"} and confidence >= 60
                else "watch_only"
            )
            amount_note = "large disclosure" if amount != "amount offen" and any(token in str(amount).lower() for token in ["50,000", "100,000", "250,000", "500,000", "1,000,000", "million"]) else "size not decisive"
            watch.append(
                {
                    "ticker": ticker,
                    "name": signal.get("name") or item.get("title"),
                    "action": action,
                    "setup": setup,
                    "impact": item.get("impact") or "medium",
                    "confidence": confidence,
                    "trade_date": signal.get("trade_date"),
                    "notification_date": signal.get("notification_date"),
                    "delay_days": delay,
                    "amount_range": amount,
                    "freshness": freshness,
                    "delay_bucket": delay_bucket,
                    "setup_quality": setup_quality,
                    "amount_note": amount_note,
                    "score_explainer": (
                        f"{setup_quality.replace('_', ' ')}: PTR delay {delay if delay is not None else 'offen'}d, "
                        f"impact {item.get('impact') or 'medium'}, confidence {confidence}."
                    ),
                    "cluster": signal.get("top_tickers") or ([ticker] if ticker else []),
                    "trigger": item.get("trigger") or intelligence.get("trigger"),
                    "invalidation": item.get("risk") or intelligence.get("invalidation"),
                    "thesis": item.get("thesis") or intelligence.get("why_now"),
                    "compliance_note": signal.get("compliance_note") or "Official PTR data is delayed; use as research signal, not blind copy.",
                    "link": item.get("link"),
                }
            )
        watch.sort(
            key=lambda item: (
                0 if item.get("impact") == "high" else 1 if item.get("impact") == "medium" else 2,
                -(item.get("confidence") or 0),
                item.get("delay_days") if item.get("delay_days") is not None else 999,
            )
        )
        return watch[:5]

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
            "official_house_ptr": 82,
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
            "public_figure": {
                "sectors": ["Policy-sensitive sectors", "Rates", "Mega-cap leadership"],
                "assets": ["S&P 500 Futures", "Nasdaq Futures", "Dollar", "US 10Y Yield"],
            },
            "ipo": {
                "sectors": ["New listings", "Small-cap growth", "Sector peers"],
                "assets": ["IPO basket", "QQQ", "IWM", "Peer group"],
            },
            "macro_data": {
                "sectors": ["Growth", "Consumer", "Financials"],
                "assets": ["Treasuries", "Dollar", "Index futures"],
            },
            "product_catalyst": {
                "sectors": ["Single-name growth", "Semis", "Consumer discretionary"],
                "assets": ["Product owner stock", "Peers", "Options IV"],
            },
            "congress_trade": {
                "sectors": ["Single-name equities", "Policy-sensitive sectors", "Options flow"],
                "assets": ["PTR ticker", "Peers", "Sector ETF"],
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
                "why_now": "Konfliktrisiken begünstigen Verteidigung, Öl und Gold gegenüber aggressiven Long-Positionen.",
                "trigger": "Nur handeln, wenn Öl, Gold oder Verteidigungswerte ihre erste Reaktion nach der Eröffnung halten.",
                "invalidation": "Die Absicherungsthese reduzieren, wenn Öl und Gold unter den ersten Impuls zurückfallen.",
                "execution_window": "Eröffnung bis zu den ersten 90 Minuten",
            }
        if event_type == "central_bank":
            return {
                "action": "watch",
                "leverage": "conditional" if impact == "medium" else "avoid",
                "why_now": "Renditen, Dollar und Futures müssen sich bestätigen, bevor eine Richtung gehandelt wird.",
                "trigger": "Abwarten, bis Renditen, Dollar und Index-Futures dieselbe Richtung bestätigen.",
                "invalidation": "Kein Trade, wenn Anleihen, Dollar und Futures nach der Veröffentlichung auseinanderlaufen.",
                "execution_window": "Makro-Veröffentlichung bis zur ersten Stunde",
            }
        if event_type == "energy":
            return {
                "action": "long",
                "leverage": "conditional",
                "why_now": "Die Anschlussdynamik im Energiesektor zählt, wenn die Öl-Stärke die Eröffnung übersteht.",
                "trigger": "Nur handeln, wenn Öl und Energieaktien nach der Europa- oder US-Eröffnung relative Stärke halten.",
                "invalidation": "Auslassen, wenn Öl steigt, aber XLE und zyklische Werte die Bewegung nicht bestätigen.",
                "execution_window": "Europa-Übergang bis zur US-Eröffnung",
            }
        if event_type == "election":
            return {
                "action": "watch",
                "leverage": "avoid",
                "why_now": "Wahlergebnisse verschieben Sektoren oft, bevor ein klarer Trend entsteht.",
                "trigger": "Zuerst eine Sektorrotation bei Banken, Versorgern, Verteidigung oder heimischen Indizes abwarten.",
                "invalidation": "Meiden, wenn sich die erste Reaktion im nächsten Nachrichtenzyklus umkehrt.",
                "execution_window": "Veröffentlichung bis zum Sitzungsschluss",
            }
        if event_type == "disaster":
            return {
                "action": "hedge",
                "leverage": "avoid",
                "why_now": "Belastungen für Lieferketten und Versicherer zählen oft vor einzelnen Aktiengeschichten.",
                "trigger": "Transport, Versicherer und Rohstoffrouten beobachten, bevor Einzelwerte gehandelt werden.",
                "invalidation": "Nicht handeln, wenn das Ereignis schnell eingedämmt wird und sich der Transport normalisiert.",
                "execution_window": "Erste Sitzung nach dem Ereignisschock",
            }
        if event_type == "policy":
            return {
                "action": "short",
                "leverage": "avoid" if impact == "high" else "conditional",
                "why_now": "Politische Schocks können schnell verblassen; Risikokontrolle zählt mehr als Geschwindigkeit.",
                "trigger": "Nur nutzen, wenn betroffene Sektoren Unterstützung verlieren und der breite Markt den Schock bestätigt.",
                "invalidation": "Kein Short, wenn der Markt die Meldung bereits im ersten Impuls absorbiert.",
                "execution_window": "Meldung bis zur ersten Trendbestätigung",
            }
        if event_type == "public_figure":
            return {
                "action": "watch",
                "leverage": "avoid",
                "why_now": "Aussagen wichtiger Personen können Märkte schnell bewegen, drehen aber oft nach Kontext oder offizieller Einordnung.",
                "trigger": "Nur hochstufen, wenn das Zitat aus einer vertrauenswürdigen Quelle stammt und Futures, Renditen, Dollar oder Sektor-ETFs gemeinsam bestätigen.",
                "invalidation": "Nicht handeln, wenn die Aussage zurückgenommen wird, politische Details fehlen oder der betroffene Marktkorb nicht reagiert.",
                "execution_window": "Meldung bis zu den ersten 60 Minuten",
            }
        if event_type == "ipo":
            return {
                "action": "watch",
                "leverage": "conditional",
                "why_now": "IPO-Anmeldungen und Börsendebüts zeigen die Risikobereitschaft am Kapitalmarkt und können Vergleichswerte neu bewerten.",
                "trigger": "Nur hochstufen, wenn Anmeldung, Preis oder Debüt bestätigt sind und Vergleichswerte oder der IPO-Korb mit Volumen reagieren.",
                "invalidation": "Ignorieren, wenn Bewertung, Streubesitz, Haltefrist oder erste Kursreaktion keine Sektorwirkung stützen.",
                "execution_window": "Anmeldung oder Preisfestsetzung bis zu den ersten zwei Sitzungen",
            }
        if event_type == "product_catalyst":
            return {
                "action": "watch",
                "leverage": "conditional",
                "why_now": "Produktmeldungen können Nachfrageerwartungen verändern, doch die erste Überschrift ist oft unvollständig.",
                "trigger": "Nur handeln, wenn offizielle Bestätigung, Volumen und Analysten- oder Vertriebskanalprüfungen die Bewegung stützen.",
                "invalidation": "Auslassen, wenn Unternehmen, verlässliche Presse oder Kursbewegung die Meldung nicht bestätigen.",
                "execution_window": "Meldung bis zur nächsten Sitzung",
            }
        if event_type == "congress_trade":
            return {
                "action": "watch",
                "leverage": "avoid",
                "why_now": "Eine verspätete offizielle PTR-Meldung kann ein Thema bestätigen, aber die Kursbestätigung zählt mehr als die Meldung allein.",
                "trigger": "Aktuellen Kurs mit dem Handelstag vergleichen und Trend, Volumen sowie Sektorbestätigung verlangen.",
                "invalidation": "Ignorieren, wenn die Bewegung bereits gelaufen ist oder die Aktie nach der Meldung keine relative Stärke zeigt.",
                "execution_window": "Heute bis zu den nächsten drei Sitzungen",
            }
        return {
            "action": "watch",
            "leverage": "avoid",
            "why_now": "Die Marktstruktur muss die Meldung zuerst bestätigen.",
            "trigger": "Abwarten, bis Kurs, Renditen und Sektorführung übereinstimmen.",
            "invalidation": "Kein Trade, wenn die erste Reaktion sofort nachlässt.",
            "execution_window": "Vom Ereignis abhängig",
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
            str(item["value"]).upper().strip()
            for item in watchlist_snapshot.get("items", [])
            if item.get("kind") == "ticker" and item.get("value")
        }
        impact: List[Dict[str, Any]] = []
        seen_keys: set[tuple[str, str]] = set()
        impacted_tickers: set[str] = set()

        def add_impact(ticker: Any, impact_type: str, summary: str, **extra: Any) -> None:
            normalized = str(ticker or "").upper().strip()
            if not normalized or normalized not in watched_tickers or not summary:
                return
            key = (normalized, impact_type)
            if key in seen_keys:
                return
            seen_keys.add(key)
            if impact_type != "monitoring":
                impacted_tickers.add(normalized)
            impact.append(
                {
                    "ticker": normalized,
                    "type": impact_type,
                    "summary": summary,
                    **extra,
                }
            )

        for signal in watchlist_snapshot.get("ticker_signals", []):
            ticker = str(signal.get("ticker") or "").upper().strip()
            event = (signal.get("events") or [None])[0]
            if event:
                add_impact(
                    ticker,
                    "insider",
                    f"{ticker}: {event.get('action')} by {event.get('owner_name')} on {event.get('trade_date')}",
                    source="public_signal",
                )

        for news in brief.get("top_news", []):
            add_impact(
                news.get("ticker"),
                "news",
                f"{news.get('title')} ({news.get('publisher')})",
                source="trusted_news",
            )

        for catalyst in brief.get("product_catalysts", []):
            ticker = catalyst.get("ticker") or catalyst.get("symbol")
            label = catalyst.get("label") or catalyst.get("type") or "product catalyst"
            title = catalyst.get("title") or catalyst.get("summary") or ""
            add_impact(
                ticker,
                "product_catalyst",
                f"{str(ticker).upper()}: {label} - {title}".strip(),
                source="product_news",
            )

        for result in brief.get("earnings_results", []):
            ticker = result.get("ticker")
            status = str(result.get("status") or "reported").upper()
            freshness = result.get("freshness") or "fresh"
            age = result.get("days_since")
            summary = result.get("summary") or "Earnings result in watch context."
            age_text = f" ({age}d old, reference only)" if freshness == "stale_reference" and age is not None else ""
            add_impact(
                ticker,
                "earnings_result",
                f"{str(ticker).upper()}: {status} earnings{age_text}. {summary}",
                source="earnings_results",
                freshness=freshness,
            )

        earnings_sources = [*(brief.get("earnings_calendar", []) or []), *(brief.get("broad_earnings", []) or [])]
        for earnings in earnings_sources:
            ticker = earnings.get("ticker")
            status = earnings.get("date_status")
            date = earnings.get("scheduled_for") or earnings.get("date") or "pending"
            summary = (
                f"{str(ticker).upper()}: Earnings-Datum noch nicht bestaetigt, aber Umsatz/EPS/Guidance bleiben im Briefing-Watch."
                if status == "provider_pending"
                else f"{str(ticker).upper()}: Earnings am {date}. Reaktion auf EPS, Umsatz und Guidance beobachten."
            )
            add_impact(ticker, "earnings", summary, source="earnings_calendar")

        movers = brief.get("market_movers", {}) if isinstance(brief.get("market_movers"), dict) else {}
        for bucket, label in (("gainers", "Top Winner"), ("losers", "Top Loser")):
            for mover in (movers.get(bucket) or [])[:8]:
                ticker = mover.get("ticker") or mover.get("symbol")
                change = mover.get("change")
                if change is None:
                    change = mover.get("change_1w")
                change_text = f"{float(change):+.2f}%" if isinstance(change, (int, float)) else "move offen"
                add_impact(
                    ticker,
                    "market_mover",
                    f"{str(ticker).upper()}: {label} {change_text}. Nur analysieren, wenn News/Volumen und Briefing-Kontext bestaetigen.",
                    source="market_movers",
                )

        for ping in brief.get("event_pings", []):
            symbols = ping.get("symbols") or []
            if not isinstance(symbols, list):
                continue
            for ticker in symbols:
                severity = ping.get("severity") or "normal"
                ping_type = ping.get("type") or "event"
                region = ping.get("region") or ping.get("country") or "global"
                add_impact(
                    ticker,
                    "event_ping",
                    f"{str(ticker).upper()}: {ping_type}/{severity} Event in {region}. Trade Impact und Hedge-Idee vor Analyse pruefen.",
                    source="event_pings",
                )

        if watched_tickers:
            for ticker in list(watched_tickers)[:5]:
                if ticker in impacted_tickers:
                    continue
                add_impact(
                    ticker,
                    "monitoring",
                    f"{ticker}: Keine harte direkte News im aktuellen Brief, aber Kurs, News, Earnings und Event-Pings werden weiter ueberwacht.",
                    source="fallback_monitoring",
                )
                if len(impact) >= 5:
                    break
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
        official_publisher = any(
            official.lower() == publisher_lower for official in self.OFFICIAL_PUBLISHERS
        )
        official_domain = any(
            domain_lower == official or domain_lower.endswith(f".{official}")
            for official in self.OFFICIAL_DOMAINS
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
        if official_publisher and official_domain:
            return {
                "domain": domain,
                "trusted": True,
                "exclude": False,
                "quality": "tier_1",
                "source_type": "official_primary",
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
        change_1d = price_data.get("change_1d")
        if isinstance(change_1d, (int, float)):
            return float(change_1d)
        change_1w = price_data.get("change_1w")
        if change_1w is None:
            return None
        return change_1w / 5

    def _contains_news_term(self, text: str, terms: Sequence[str]) -> bool:
        normalized = re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()
        for term in terms:
            normalized_term = re.sub(r"[^a-z0-9]+", " ", str(term or "").lower()).strip()
            if normalized_term and re.search(
                rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])",
                normalized,
            ):
                return True
        return False

    def _classify_news_signal(self, text: str) -> Dict[str, str]:
        event_type = "macro"
        impact = "low"
        severity = "normal"

        if self._is_market_moving_person_statement(text):
            event_type = "public_figure"
            impact = "high"
            severity = "elevated"
        elif self._is_ipo_headline(text):
            event_type = "ipo"
            impact = "high"
            severity = "elevated"
        elif self._contains_news_term(text, ["war", "missile", "attack", "israel", "iran", "russia", "ukraine", "lebanon", "beirut"]):
            event_type = "conflict"
            impact = "high"
            severity = "critical"
        elif self._contains_news_term(
            text,
            ["fed", "federal reserve", "fomc", "ecb", "boj", "central bank", "rate", "yield"],
        ):
            event_type = "central_bank"
            impact = "high"
            severity = "elevated"
        elif self._contains_news_term(text, ["oil", "opec", "gas", "crude"]):
            event_type = "energy"
            impact = "medium"
            severity = "elevated"
        elif self._contains_news_term(text, ["election", "vote", "ballot", "president", "prime minister", "parliament", "coalition", "campaign"]):
            event_type = "election"
            impact = "high"
            severity = "elevated"
        elif self._contains_news_term(text, ["earthquake", "wildfire", "flood", "storm", "hurricane", "typhoon", "tsunami", "drought", "disaster"]):
            event_type = "disaster"
            impact = "high"
            severity = "critical"
        elif self._contains_news_term(text, ["tariff", "sanction", "trade war", "trade policy", "regulation", "policy"]):
            event_type = "policy"
            impact = "high"
            severity = "elevated"
        elif self._contains_news_term(
            text,
            [
                "inflation", "consumer price index", "cpi", "producer price index", "ppi",
                "gdp", "gross domestic product", "personal income and outlays", "pce",
                "employment situation", "payrolls", "jobs", "unemployment", "recession",
            ],
        ):
            event_type = "macro_data"
            impact = "high"
            severity = "elevated"
        elif self._contains_news_term(text, ["earnings", "guidance", "upgrade", "downgrade"]):
            event_type = "earnings"
            impact = "medium"
            severity = "normal"
        elif self._classify_product_catalyst(text):
            product = self._classify_product_catalyst(text) or {}
            event_type = "product_catalyst"
            impact = "medium"
            severity = "elevated" if self._contains_news_term(text, ["delay", "delayed", "postpone", "postponed", "launch", "unveil", "release"]) else "normal"
            product_region = {"BMW.DE": "europe"}.get(str(product.get("ticker") or ""))
            if product_region:
                return {
                    "impact": impact,
                    "region": product_region,
                    "event_type": event_type,
                    "severity": severity,
                }
        elif self._contains_news_term(text, ["china", "japan", "hong kong", "taiwan"]):
            event_type = "regional_macro"
            impact = "medium"
            severity = "normal"

        return {
            "impact": impact,
            "region": "usa" if event_type in {"public_figure", "ipo"} and self._infer_region(text) == "global" else self._infer_region(text),
            "event_type": event_type,
            "severity": severity,
        }

    def _is_market_moving_person_statement(self, text: str) -> bool:
        normalized = str(text or "").lower()
        if not normalized:
            return False
        has_person = self._contains_news_term(normalized, self.MARKET_MOVING_PERSON_TERMS)
        has_statement = self._contains_news_term(normalized, self.MARKET_MOVING_STATEMENT_TERMS)
        return has_person and has_statement

    def _is_ipo_headline(self, text: str) -> bool:
        normalized = str(text or "").lower()
        if not normalized:
            return False
        if not self._contains_news_term(normalized, self.IPO_TERMS):
            return False
        return self._contains_news_term(normalized, ["file", "files", "pricing", "prices", "raise", "raises", "valuation", "debut", "listing", "shares", "revenue", "growth"])

    def _classify_product_catalyst(self, text: str) -> Dict[str, str] | None:
        normalized = (text or "").lower()
        if not normalized:
            return None

        matched_ticker = None
        matched_theme = None
        for ticker, aliases in self.PRODUCT_CATALYST_ALIASES.items():
            for alias in aliases:
                if self._contains_news_term(normalized, [alias]):
                    matched_ticker = ticker
                    matched_theme = alias
                    break
            if matched_ticker:
                break
        if not matched_ticker:
            return None

        delay_terms = ["delay", "delayed", "postpone", "postponed", "pushed back", "misses launch", "slips"]
        launch_terms = ["launch", "unveil", "release", "preorder", "new", "next-gen", "upgrade", "ship", "debut"]
        catalyst_type = (
            "delay"
            if self._contains_news_term(normalized, delay_terms)
            else "launch"
            if self._contains_news_term(normalized, launch_terms)
            else "product_news"
        )
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
