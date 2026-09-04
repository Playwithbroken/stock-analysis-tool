"""
FastAPI Backend for Stock Analysis Tool
Provides REST API endpoints for stock analysis.
"""

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor
import copy
import difflib
import json
import re
import uvicorn
import numpy as np
import asyncio
import time
import hashlib
import hmac
import secrets
import math
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src.data_fetcher import DataFetcher
from src.analyzer import StockAnalyzer, Rating, Valuation
from src.discovery_service import DiscoveryService
from src.email_alert_service import (
    DEFAULT_CLOSE_RECAP_TIME,
    DEFAULT_EUROPE_CLOSE_BRIEF_TIME,
    DEFAULT_EUROPE_OPEN_BRIEF_TIME,
    DEFAULT_MIDDAY_BRIEF_TIME,
    DEFAULT_MORNING_BRIEF_TIME,
    DEFAULT_US_CLOSE_BRIEF_TIME,
    DEFAULT_US_OPEN_BRIEF_TIME,
    EmailAlertService,
)
from src.morning_brief_service import MorningBriefService
from src.paper_trading_service import PaperTradeAlreadyClosedError, PaperTradingService
from src.strategy_library import StrategyLibrary
from src.forecast_learning_service import ForecastLearningService
from src.signal_score_service import SignalScoreService
from src.session_list_service import SessionListService
from src.trading_intelligence_service import TradingIntelligenceService
from src.trading_signals_service import TradingSignalsService
from src.asymmetric_trade_service import AsymmetricTradeService
from src.relative_strength_service import RelativeStrengthService
from src.trade_lifecycle_service import TradeLifecycleService
from src.telegram_interactive_service import TelegramInteractiveService
from src.portfolio_heat_service import PortfolioHeatService
from src.anchored_vwap_service import AnchoredVWAPService
from src.whale_flow_service import WhaleFlowService
from src.liquidity_zone_service import LiquidityZoneService
from src.multi_timeframe_service import MultiTimeframeService
from src.realtime_market_service import RealtimeMarketService
from src.integrations.market_data.alpaca import AlpacaMarketDataAdapter, AlpacaStreamConfig
from src.public_signal_service import PublicSignalService
from src.advisory_service import advisory_profile_subset, build_portfolio_advisory_check, build_suitability_check
from src.storage import DB_PATH, PortfolioManager, get_database_status, get_persistence_status
from src.scalable_integration_service import ScalableIntegrationError, ScalableIntegrationService
from src.scalable_decision_service import ScalableDecisionService
from src.backup_service import DatabaseBackupService
from src.provider_observability import (
    classify_provider_error,
    provider_metrics_snapshot,
    record_provider_result,
)
from src.decision_scope import attach_scope, paper_scope, research_scope, scope_for_strategy_status
from src.compliance_gate import get_compliance_status
from src.production_soak_service import read_production_soak, record_production_soak
from src.fast_paper_safety_service import FastPaperSafetyService
from src.latency_monitor_service import LatencyMonitorService
from src.financial_units import normalize_dividend_yield_pct, ratio_to_pct
from src.market_quality_service import MarketQualityService
from src.broker_order_store import BrokerOrderStore
from src.broker_reconciliation_service import (
    BrokerReconciliationBlockedError,
    BrokerReconciliationService,
)
from src.integrations.brokers.base import BrokerOrderRequest
from src.integrations.brokers.alpaca_paper import (
    AlpacaPaperBrokerAdapter,
    AlpacaPaperBrokerError,
    AlpacaPaperConfig,
    BrokerSubmissionUncertainError,
)

# Load environment variables
from dotenv import load_dotenv
import os
load_dotenv()

APP_VERSION = "0.9.0-beta.1"
PROCESS_STARTED_AT = datetime.now(timezone.utc)
PROCESS_STARTED_MONOTONIC = time.monotonic()


def get_release_identity() -> Dict[str, Any]:
    """Return a non-secret, reproducible identity for the running release."""
    commit_sha = os.getenv("RAILWAY_GIT_COMMIT_SHA", "").strip() or None
    deployment_id = os.getenv("RAILWAY_DEPLOYMENT_ID", "").strip() or None
    replica_id = os.getenv("RAILWAY_REPLICA_ID", "").strip() or None
    return {
        "schema": "release-identity.v1",
        "version": APP_VERSION,
        "commit_sha": commit_sha,
        "commit_short": commit_sha[:8] if commit_sha else None,
        "branch": os.getenv("RAILWAY_GIT_BRANCH", "").strip() or None,
        "deployment_id": deployment_id,
        "replica_id": replica_id,
        "region": os.getenv("RAILWAY_REPLICA_REGION", "").strip() or None,
        "service": os.getenv("RAILWAY_SERVICE_NAME", "").strip() or None,
        "environment": os.getenv("RAILWAY_ENVIRONMENT_NAME", "").strip() or os.getenv("APP_ENV", "development"),
        "started_at": PROCESS_STARTED_AT.isoformat(),
        "uptime_seconds": max(0, round(time.monotonic() - PROCESS_STARTED_MONOTONIC)),
        "provider": "railway" if deployment_id or replica_id or commit_sha else "local",
    }

app = FastAPI(
    title="Stock Analysis API",
    description="Professional stock market analysis tool",
    version=APP_VERSION,
)

_HISTORY_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="history-priority")

# Enable CORS for frontend
allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "APP_ALLOWED_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000,http://127.0.0.1:5173,http://localhost:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def add_api_timing_headers(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        duration_ms = int((time.perf_counter() - started) * 1000)
        response.headers["X-API-Duration-Ms"] = str(duration_ms)
        response.headers["Server-Timing"] = f"app;dur={duration_ms}"
    return response


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), payment=(), usb=(), bluetooth=()",
    )
    if use_secure_cookies() or os.getenv("APP_ENV", "").strip().lower() == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


# Global services (Lazy initialized)
_discovery_service = None
_portfolio_manager = None
_public_signal_service = None
_email_alert_service = None
_signal_alert_task = None
_price_alert_task = None
_brief_warmup_task = None
_scheduler_startup_catchup_task = None
_background_task_watchdog_task = None
_morning_brief_service = None
_signal_score_service = None
_session_list_service = None
_paper_trading_service = None
_trading_intelligence_service = None
_trading_signals_service = None
_asymmetric_trade_service = None
_relative_strength_service = None
_trade_lifecycle_service = None
_portfolio_heat_service = None
_anchored_vwap_service = None
_whale_flow_service = None
_liquidity_zone_service = None
_multi_timeframe_service = None
_telegram_interactive_service = None
_telegram_bot_task = None
_realtime_market_service = None
_forecast_learning_service = None
_forecast_learning_task = None
_push_service = None
_database_backup_service = None
_scalable_integration_service = None
_scalable_sync_task = None
_alpaca_stream_adapter = None
_alpaca_stream_task = None
_market_safety_task = None
_alpaca_paper_broker_adapter = None
_alpaca_paper_broker_task = None
_broker_reconciliation_task = None
SESSION_COOKIE_NAME = "brokerfreund_session"
_RESPONSE_CACHE: Dict[str, tuple[datetime, Any]] = {}
TRADING_EDGE_CACHE_KEY = "trading_edge:dashboard"


def get_database_backup_service() -> DatabaseBackupService:
    global _database_backup_service
    if _database_backup_service is None:
        _database_backup_service = DatabaseBackupService(DB_PATH)
    return _database_backup_service


def get_scalable_integration_service() -> ScalableIntegrationService:
    global _scalable_integration_service
    if _scalable_integration_service is None:
        _scalable_integration_service = ScalableIntegrationService(DB_PATH)
    return _scalable_integration_service


def _cache_get(key: str, ttl_seconds: int) -> Any | None:
    entry = _RESPONSE_CACHE.get(key)
    if not entry:
        return None
    created_at, payload = entry
    age_seconds = (datetime.utcnow() - created_at).total_seconds()
    if age_seconds > ttl_seconds:
        _RESPONSE_CACHE.pop(key, None)
        return None
    cloned = copy.deepcopy(payload)
    if isinstance(cloned, dict):
        meta = cloned.setdefault("meta", {})
        if isinstance(meta, dict):
            meta["cached"] = True
            meta["cache_age_seconds"] = int(age_seconds)
    return cloned


def _cache_get_stale(key: str, max_age_seconds: int) -> Any | None:
    entry = _RESPONSE_CACHE.get(key)
    if not entry:
        return None
    created_at, payload = entry
    age_seconds = (datetime.utcnow() - created_at).total_seconds()
    if age_seconds > max_age_seconds:
        return None
    cloned = copy.deepcopy(payload)
    if isinstance(cloned, dict):
        meta = cloned.setdefault("meta", {})
        if isinstance(meta, dict):
            meta["cached"] = True
            meta["cache_age_seconds"] = int(age_seconds)
            meta["mode"] = "fallback"
            meta["stale"] = True
            meta["source"] = f"{meta.get('source') or 'history'}_stale_cache"
            meta["fallback_reason"] = "provider_unavailable"
    return cloned


def _cache_set(key: str, payload: Any) -> Any:
    _RESPONSE_CACHE[key] = (datetime.utcnow(), copy.deepcopy(payload))
    return payload


def _cache_forget(prefix: str) -> None:
    for key in list(_RESPONSE_CACHE.keys()):
        if key.startswith(prefix):
            _RESPONSE_CACHE.pop(key, None)


def _env_enabled(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}

SEARCH_NAME_CATALOG: List[Dict[str, str]] = [
    {"ticker": "AAPL", "name": "Apple"},
    {"ticker": "MSFT", "name": "Microsoft"},
    {"ticker": "NVDA", "name": "NVIDIA"},
    {"ticker": "AMZN", "name": "Amazon"},
    {"ticker": "GOOGL", "name": "Alphabet Google"},
    {"ticker": "META", "name": "Meta Platforms Facebook"},
    {"ticker": "TSLA", "name": "Tesla"},
    {"ticker": "PFE", "name": "Pfizer"},
    {"ticker": "UNH", "name": "UnitedHealth Group"},
    {"ticker": "LLY", "name": "Eli Lilly"},
    {"ticker": "NVO", "name": "Novo Nordisk"},
    {"ticker": "JNJ", "name": "Johnson & Johnson"},
    {"ticker": "BRK-B", "name": "Berkshire Hathaway"},
    {"ticker": "JPM", "name": "JPMorgan Chase"},
    {"ticker": "BAC", "name": "Bank of America"},
    {"ticker": "GS", "name": "Goldman Sachs"},
    {"ticker": "V", "name": "Visa"},
    {"ticker": "MA", "name": "Mastercard"},
    {"ticker": "SAP", "name": "SAP"},
    {"ticker": "ASML", "name": "ASML"},
    {"ticker": "INTC", "name": "Intel"},
    {"ticker": "AMD", "name": "Advanced Micro Devices"},
    {"ticker": "NKE", "name": "Nike"},
    {"ticker": "NFLX", "name": "Netflix"},
    {"ticker": "CRM", "name": "Salesforce"},
    {"ticker": "ORCL", "name": "Oracle"},
    {"ticker": "NOW", "name": "ServiceNow"},
    {"ticker": "ADBE", "name": "Adobe"},
    {"ticker": "PLTR", "name": "Palantir"},
    {"ticker": "PANW", "name": "Palo Alto Networks"},
    {"ticker": "CRWD", "name": "CrowdStrike"},
    {"ticker": "SOFI", "name": "SoFi Technologies"},
    {"ticker": "HIMS", "name": "Hims & Hers Health"},
    {"ticker": "TTWO", "name": "Take-Two Interactive Rockstar GTA 6"},
    {"ticker": "BMW.DE", "name": "BMW"},
    {"ticker": "AIR.PA", "name": "Airbus"},
    {"ticker": "MBG.DE", "name": "Mercedes-Benz"},
    {"ticker": "VOW3.DE", "name": "Volkswagen"},
    {"ticker": "SIE.DE", "name": "Siemens"},
    {"ticker": "RHM.DE", "name": "Rheinmetall"},
    {"ticker": "RWE.DE", "name": "RWE"},
    {"ticker": "DBK.DE", "name": "Deutsche Bank"},
    {"ticker": "ALV.DE", "name": "Allianz"},
    {"ticker": "BAS.DE", "name": "BASF"},
    {"ticker": "DTE.DE", "name": "Deutsche Telekom"},
    {"ticker": "DHL.DE", "name": "DHL Group Deutsche Post"},
    {"ticker": "ADS.DE", "name": "Adidas"},
    {"ticker": "COIN", "name": "Coinbase"},
    {"ticker": "HOOD", "name": "Robinhood Markets trading app brokerage"},
    {"ticker": "MSTR", "name": "MicroStrategy"},
    {"ticker": "FLYYQ", "name": "Spirit Airlines"},
    {"ticker": "DHR", "name": "Danaher"},
    {"ticker": "GE", "name": "GE Aerospace"},
    {"ticker": "RTX", "name": "RTX"},
    {"ticker": "ISRG", "name": "Intuitive Surgical"},
    {"ticker": "PM", "name": "Philip Morris"},
    {"ticker": "PEP", "name": "PepsiCo"},
    {"ticker": "ABT", "name": "Abbott Laboratories"},
    {"ticker": "RKLB", "name": "Rocket Lab"},
    {"ticker": "LUNR", "name": "Intuitive Machines lunar space"},
    {"ticker": "ASTS", "name": "AST SpaceMobile"},
    {"ticker": "IONQ", "name": "IonQ Quantum"},
    {"ticker": "RGTI", "name": "Rigetti Computing quantum"},
    {"ticker": "PATH", "name": "UiPath Automation"},
    {"ticker": "S", "name": "SentinelOne cybersecurity"},
    {"ticker": "SOUN", "name": "SoundHound AI"},
    {"ticker": "RXRX", "name": "Recursion Pharmaceuticals AI Biotech"},
    {"ticker": "CELH", "name": "Celsius Holdings energy drinks"},
    {"ticker": "DUOL", "name": "Duolingo language learning"},
    {"ticker": "TTD", "name": "The Trade Desk advertising tech"},
    {"ticker": "CRSP", "name": "CRISPR Therapeutics gene editing"},
    {"ticker": "BEAM", "name": "Beam Therapeutics gene editing"},
    {"ticker": "ENVX", "name": "Enovix battery technology"},
    {"ticker": "JOBY", "name": "Joby Aviation eVTOL"},
    {"ticker": "ACHR", "name": "Archer Aviation eVTOL"},
    {"ticker": "OKLO", "name": "Oklo Nuclear Energy"},
    {"ticker": "VOO", "name": "Vanguard S&P 500 ETF"},
    {"ticker": "VTI", "name": "Vanguard Total Stock Market ETF"},
    {"ticker": "SCHD", "name": "Schwab US Dividend Equity ETF"},
    {"ticker": "SOXX", "name": "iShares Semiconductor ETF"},
    {"ticker": "VT", "name": "Vanguard Total World Stock ETF"},
    {"ticker": "VXUS", "name": "Vanguard Total International Stock ETF"},
    {"ticker": "VUG", "name": "Vanguard Growth ETF"},
    {"ticker": "VTV", "name": "Vanguard Value ETF"},
    {"ticker": "VNQ", "name": "Vanguard Real Estate ETF"},
    {"ticker": "VYM", "name": "Vanguard High Dividend Yield ETF"},
    {"ticker": "JEPI", "name": "JPMorgan Equity Premium Income ETF"},
    {"ticker": "JEPQ", "name": "JPMorgan Nasdaq Equity Premium Income ETF"},
    {"ticker": "IBIT", "name": "iShares Bitcoin Trust BlackRock Bitcoin ETF"},
    {"ticker": "FBTC", "name": "Fidelity Wise Origin Bitcoin Fund ETF"},
    {"ticker": "SPY", "name": "SPDR S&P 500 ETF"},
    {"ticker": "QQQ", "name": "Invesco QQQ Nasdaq ETF"},
    {"ticker": "QQQM", "name": "Invesco NASDAQ 100 ETF"},
    {"ticker": "DIA", "name": "SPDR Dow Jones ETF"},
    {"ticker": "IWM", "name": "iShares Russell 2000 ETF"},
    {"ticker": "URTH", "name": "iShares MSCI World ETF"},
    {"ticker": "GLD", "name": "SPDR Gold Shares ETF"},
    {"ticker": "TLT", "name": "iShares 20+ Year Treasury ETF"},
    {"ticker": "XLE", "name": "Energy Select Sector ETF"},
    {"ticker": "USO", "name": "United States Oil Fund"},
    {"ticker": "BTC-USD", "name": "Bitcoin"},
    {"ticker": "ETH-USD", "name": "Ethereum"},
    {"ticker": "SOL-USD", "name": "Solana"},
    {"ticker": "DOGE-USD", "name": "Dogecoin"},
    {"ticker": "XRP-USD", "name": "XRP Ripple"},
    {"ticker": "ADA-USD", "name": "Cardano"},
    {"ticker": "AVAX-USD", "name": "Avalanche"},
    {"ticker": "DOT-USD", "name": "Polkadot"},
    {"ticker": "LINK-USD", "name": "Chainlink"},
    {"ticker": "BNB-USD", "name": "BNB Binance Coin"},
    {"ticker": "TRX-USD", "name": "TRON"},
    {"ticker": "TON11419-USD", "name": "Toncoin"},
    {"ticker": "MATIC-USD", "name": "Polygon"},
    {"ticker": "LTC-USD", "name": "Litecoin"},
    {"ticker": "BCH-USD", "name": "Bitcoin Cash"},
    {"ticker": "UNI7083-USD", "name": "Uniswap"},
]
SEARCH_ALIASES: Dict[str, str] = {
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "facebook": "META",
    "berkshire": "BRK-B",
    "hathaway": "BRK-B",
    "amazon": "AMZN",
    "apple": "AAPL",
    "microsoft": "MSFT",
    "nvidia": "NVDA",
    "nvdia": "NVDA",
    "gpu": "NVDA",
    "geforce": "NVDA",
    "tesla": "TSLA",
    "pfizer": "PFE",
    "pfi": "PFE",
    "iphone": "AAPL",
    "ipad": "AAPL",
    "ios": "AAPL",
    "gta": "TTWO",
    "gta6": "TTWO",
    "rockstar": "TTWO",
    "bmw": "BMW.DE",
    "airbus": "AIR.PA",
    "nike": "NKE",
    "mercedes": "MBG.DE",
    "volkswagen": "VOW3.DE",
    "vw": "VOW3.DE",
    "spirit": "FLYYQ",
    "airline": "FLYYQ",
    "novo": "NVO",
    "lilly": "LLY",
    "palantir": "PLTR",
    "paloalto": "PANW",
    "crowdstrike": "CRWD",
    "coinbase": "COIN",
    "bitcoin": "BTC-USD",
    "btc": "BTC-USD",
    "sp500": "VOO",
    "sp500etf": "VOO",
    "sandp500": "VOO",
    "sandp500etf": "VOO",
    "sundp500": "VOO",
    "nasdaq100": "QQQ",
    "nasdaq100etf": "QQQ",
    "msciworld": "URTH",
    "msciworldetf": "URTH",
    "bitcoinetf": "IBIT",
    "blackrockbitcoinetf": "IBIT",
    "isharesbitcointrust": "IBIT",
    "ibit": "IBIT",
    "fidelitybitcoinetf": "FBTC",
    "fbtc": "FBTC",
    "crypto": "BTC-USD",
    "hood": "HOOD",
    "hoodapp": "HOOD",
    "robin": "HOOD",
    "robinhood": "HOOD",
    "robinhoodmarkets": "HOOD",
    "robinhoodapp": "HOOD",
    "tradingapp": "HOOD",
    "ethereum": "ETH-USD",
    "eth": "ETH-USD",
    "solana": "SOL-USD",
    "solanacrypto": "SOL-USD",
    "dogecoin": "DOGE-USD",
    "doge": "DOGE-USD",
    "xrp": "XRP-USD",
    "ripple": "XRP-USD",
    "cardano": "ADA-USD",
    "ada": "ADA-USD",
    "avalanche": "AVAX-USD",
    "avax": "AVAX-USD",
    "polkadot": "DOT-USD",
    "dot": "DOT-USD",
    "chainlink": "LINK-USD",
    "link": "LINK-USD",
    "bnb": "BNB-USD",
    "binance": "BNB-USD",
    "binancecoin": "BNB-USD",
    "tron": "TRX-USD",
    "trx": "TRX-USD",
    "ton": "TON11419-USD",
    "toncoin": "TON11419-USD",
    "polygon": "MATIC-USD",
    "matic": "MATIC-USD",
    "litecoin": "LTC-USD",
    "ltc": "LTC-USD",
    "bitcoincash": "BCH-USD",
    "bch": "BCH-USD",
    "uniswap": "UNI7083-USD",
    "uni": "UNI7083-USD",
    "nvidea": "NVDA",
    "tesler": "TSLA",
    "meta": "META",
    "rheinmetall": "RHM.DE",
    "siemens": "SIE.DE",
    "rwe": "RWE.DE",
    "deutschebank": "DBK.DE",
    "dbank": "DBK.DE",
    "allianz": "ALV.DE",
    "basf": "BAS.DE",
    "telekom": "DTE.DE",
    "deutschetelekom": "DTE.DE",
    "dhl": "DHL.DE",
    "deutschepost": "DHL.DE",
    "adidas": "ADS.DE",
    "brkb": "BRK-B",
    "brkbshares": "BRK-B",
    "berkshirehathaway": "BRK-B",
    "berkshirehathawayb": "BRK-B",
    "rocketlab": "RKLB",
    "rklb": "RKLB",
    "asts": "ASTS",
    "spacemobile": "ASTS",
    "ionq": "IONQ",
    "quantum": "IONQ",
    "uipath": "PATH",
    "path": "PATH",
    "soundhound": "SOUN",
    "soun": "SOUN",
    "recursion": "RXRX",
    "rxrx": "RXRX",
    "joby": "JOBY",
    "archer": "ACHR",
    "achr": "ACHR",
    "oklo": "OKLO",
    "vanguardtotalmarket": "VTI",
    "vanguardtotalmarketetf": "VTI",
    "vanguardtotalworld": "VT",
    "totalworldetf": "VT",
    "worldetf": "VT",
    "internationaletf": "VXUS",
    "vanguardinternational": "VXUS",
    "growthetf": "VUG",
    "valueetf": "VTV",
    "realestateetf": "VNQ",
    "dividendetf": "SCHD",
    "highdividendetf": "VYM",
    "jepi": "JEPI",
    "jepq": "JEPQ",
}

SEARCH_QUERY_NOISE_WORDS = {
    "aktie",
    "stock",
    "stocks",
    "share",
    "shares",
    "kurs",
    "analyse",
    "analysis",
    "company",
    "inc",
    "corp",
    "corporation",
    "ag",
    "se",
    "plc",
    "class",
    "app",
    "coin",
    "token",
    "crypto",
    "cryptocurrency",
    "etf",
    "fund",
    "trust",
    "dividend",
    "income",
    "yield",
}

KNOWN_CRYPTO_TICKERS = {
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "DOGE-USD",
    "XRP-USD",
    "ADA-USD",
    "AVAX-USD",
    "DOT-USD",
    "LINK-USD",
    "BNB-USD",
    "TRX-USD",
    "TON11419-USD",
    "MATIC-USD",
    "LTC-USD",
    "BCH-USD",
    "UNI7083-USD",
}

CRYPTO_INTENT_WORDS = {
    "bitcoin",
    "btc",
    "ethereum",
    "eth",
    "solana",
    "sol",
    "dogecoin",
    "doge",
    "xrp",
    "ripple",
    "cardano",
    "ada",
    "avalanche",
    "avax",
    "polkadot",
    "dot",
    "chainlink",
    "link",
    "bnb",
    "binance",
    "tron",
    "trx",
    "ton",
    "toncoin",
    "polygon",
    "matic",
    "litecoin",
    "ltc",
    "bitcoincash",
    "bch",
    "uniswap",
    "uni",
    "crypto",
    "coin",
    "token",
}


def _has_crypto_search_intent(query: str) -> bool:
    compact = _normalize_search_query(query)
    normalized = _normalize_ticker_input(query)
    if normalized in KNOWN_CRYPTO_TICKERS:
        return True
    return compact in CRYPTO_INTENT_WORDS or any(word in compact for word in ("crypto", "coin", "token"))


def _normalize_search_query(value: str) -> str:
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def _strip_search_noise(value: str) -> str:
    words = re.findall(r"[a-zA-Z0-9.\-^=]+", value or "")
    kept = [word for word in words if word.lower() not in SEARCH_QUERY_NOISE_WORDS]
    return " ".join(kept).strip()


def _search_query_variants(value: str) -> List[str]:
    raw = (value or "").strip()
    if not raw:
        return []
    stripped = _strip_search_noise(raw)
    normalized = _normalize_ticker_input(raw)
    variants = [raw, stripped, normalized]
    if normalized.endswith("-USD"):
        variants.append(normalized.replace("-USD", ""))
    compact = _normalize_search_query(stripped or raw)
    alias = SEARCH_ALIASES.get(compact)
    if alias:
        variants.append(alias)
    seen = set()
    unique: List[str] = []
    for item in variants:
        text = str(item or "").strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            unique.append(text)
    return unique[:4]


def _normalize_ticker_input(value: str) -> str:
    text = (value or "").strip()
    if "(" in text and ")" in text:
        match = re.search(r"\(([A-Z0-9.\-^=]+)\)", text.upper())
        if match:
            return match.group(1)
    cleaned = re.sub(r"^[#$]+", "", text)
    cleaned = re.sub(r"\b(aktie|stock|share|shares|kurs|analyse|analysis|usd|eur)\b", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"[/:]+", "-", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    compact = re.sub(r"[^a-z0-9.\-]+", "", cleaned.lower())
    alias = SEARCH_ALIASES.get(compact) or SEARCH_ALIASES.get(_normalize_search_query(cleaned))
    if alias:
        return alias
    stripped = _strip_search_noise(cleaned)
    stripped_alias = SEARCH_ALIASES.get(_normalize_search_query(stripped))
    if stripped_alias:
        return stripped_alias
    if re.fullmatch(r"brk[.\s-]?b", cleaned, flags=re.I):
        return "BRK-B"
    crypto_aliases = {
        "btc": "BTC-USD",
        "eth": "ETH-USD",
        "sol": "SOL-USD",
        "doge": "DOGE-USD",
        "xrp": "XRP-USD",
        "ada": "ADA-USD",
        "avax": "AVAX-USD",
        "dot": "DOT-USD",
        "link": "LINK-USD",
        "bnb": "BNB-USD",
        "trx": "TRX-USD",
        "ton": "TON11419-USD",
        "matic": "MATIC-USD",
        "ltc": "LTC-USD",
        "bch": "BCH-USD",
        "uni": "UNI7083-USD",
    }
    if cleaned.lower() in crypto_aliases:
        return crypto_aliases[cleaned.lower()]
    normalized = re.sub(r"[^A-Z0-9.\-^=]+", "-", cleaned.upper())
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized


def _fuzzy_catalog_search(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    needle = _normalize_search_query(query)
    if not needle:
        return []

    if needle in SEARCH_ALIASES:
        ticker = SEARCH_ALIASES[needle]
        exact = next((item for item in SEARCH_NAME_CATALOG if item["ticker"] == ticker), None)
        if exact:
            return [{"ticker": exact["ticker"], "name": exact["name"], "exchange": None, "type": "alias"}]

    scored: List[tuple[float, Dict[str, Any]]] = []
    for item in SEARCH_NAME_CATALOG:
        ticker = item["ticker"]
        name = item["name"]
        ticker_norm = _normalize_search_query(ticker)
        name_norm = _normalize_search_query(name)

        if needle == ticker_norm:
            score = 1.0
        elif ticker_norm.startswith(needle) or name_norm.startswith(needle):
            score = 0.95
        elif needle in ticker_norm or needle in name_norm:
            score = 0.88
        else:
            score = max(
                difflib.SequenceMatcher(None, needle, ticker_norm).ratio(),
                difflib.SequenceMatcher(None, needle, name_norm).ratio(),
            )
        if score >= 0.62:
            scored.append((score, {"ticker": ticker, "name": name, "exchange": None, "type": "fuzzy"}))

    scored.sort(key=lambda row: row[0], reverse=True)
    return [row[1] for row in scored[:limit]]


def _catalog_match_for_ticker(ticker: str) -> Dict[str, Any] | None:
    normalized = (ticker or "").strip().upper()
    if not normalized:
        return None
    exact = next((item for item in SEARCH_NAME_CATALOG if item["ticker"] == normalized), None)
    if not exact:
        return None
    return {
        "ticker": exact["ticker"],
        "name": exact["name"],
        "exchange": None,
        "type": "alias",
        "source": "catalog_normalized",
    }


def _quote_search_score(query: str, item: Dict[str, Any]) -> float:
    needle = _normalize_search_query(query)
    ticker = _normalize_search_query(str(item.get("ticker", "")))
    name = _normalize_search_query(str(item.get("name", "")))
    quote_type = str(item.get("type") or "").upper()
    symbol = str(item.get("ticker", "")).upper()
    has_crypto_intent = _has_crypto_search_intent(query)
    score = 0.0
    if quote_type == "ALIAS":
        score += 145
    elif quote_type == "FUZZY" and needle and (needle == ticker or name.startswith(needle)):
        score += 132
    elif quote_type == "CRYPTOCURRENCY" and needle and name == f"{needle}usd":
        score += 138
    elif quote_type == "CRYPTOCURRENCY" and len(needle) >= 4 and needle and name.startswith(needle) and ticker.endswith("usd"):
        score += 126
    elif quote_type == "ETF" and needle and ("etf" in needle or "fund" in needle) and name.startswith(needle):
        score += 116
    elif needle and needle == ticker:
        score += 120
    elif needle and ticker.startswith(needle):
        score += 105
    elif needle and name.startswith(needle):
        score += 94
    elif needle and (needle in ticker or needle in name):
        score += 82
    else:
        score += max(
            difflib.SequenceMatcher(None, needle, ticker).ratio(),
            difflib.SequenceMatcher(None, needle, name).ratio(),
        ) * 70

    if quote_type in {"EQUITY", "ETF", "CRYPTOCURRENCY"}:
        score += 12
    elif quote_type in {"MUTUALFUND", "INDEX"}:
        score += 4
    if quote_type == "CRYPTOCURRENCY" and "tokenizedstock" in name and "tokenized" not in needle:
        score -= 55
    if quote_type == "CRYPTOCURRENCY":
        normalized = _normalize_ticker_input(query)
        if symbol not in KNOWN_CRYPTO_TICKERS and not has_crypto_intent:
            score -= 140
        if normalized.endswith("-USD") and symbol == normalized:
            score += 35
        elif normalized.endswith("-USD") and not symbol.endswith("-USD"):
            score -= 35
        elif symbol.endswith("-USD"):
            score += 8
    if "." in str(item.get("ticker", "")) and not any(part in needle for part in ("de", "to", "pa", "mi", "f", "bk")):
        score -= 30
    return score


def _is_supported_search_quote(item: Dict[str, Any]) -> bool:
    quote_type = str(item.get("type") or "").upper()
    if not quote_type:
        return True
    return quote_type in {"ALIAS", "FUZZY", "EQUITY", "ETF", "CRYPTOCURRENCY", "MUTUALFUND", "INDEX"}


def _yahoo_search_sync(query: str, limit: int = 8) -> List[Dict[str, Any]]:
    try:
        response = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={
                "q": query,
                "quotesCount": max(10, limit),
                "newsCount": 0,
                "enableFuzzyQuery": "true",
                "quotesQueryId": "tss_match_phrase_query",
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=3.0,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        print(f"Yahoo quote search error for '{query}': {exc}")
        return []

    results: List[Dict[str, Any]] = []
    for item in payload.get("quotes", []) or []:
        ticker = str(item.get("symbol") or "").strip().upper()
        if not ticker:
            continue
        quote_type = str(item.get("quoteType") or item.get("typeDisp") or "").upper()
        if quote_type and quote_type not in {"EQUITY", "ETF", "CRYPTOCURRENCY", "MUTUALFUND", "INDEX"}:
            continue
        name = (
            item.get("longname")
            or item.get("shortname")
            or item.get("name")
            or item.get("exchDisp")
            or ticker
        )
        results.append({
            "ticker": ticker,
            "name": str(name),
            "exchange": item.get("exchange") or item.get("exchDisp"),
            "type": quote_type or item.get("typeDisp") or "quote",
            "source": "yahoo_search",
        })

    scored = [(_quote_search_score(query, row), row) for row in results]
    scored = [(score, row) for score, row in scored if score >= 62]
    scored.sort(key=lambda row: row[0], reverse=True)
    return [row for _, row in scored[:limit]]


async def _search_yahoo_finance(query: str, limit: int = 8) -> List[Dict[str, Any]]:
    return await asyncio.to_thread(_yahoo_search_sync, query, limit)


SEARCH_DISCOVERY_TIMEOUT_SECONDS = 1.25
SEARCH_QUOTE_PROVIDER_TIMEOUT_SECONDS = 2.6


async def _resolve_search_results(q: str, limit: int = 6) -> List[Dict[str, Any]]:
    normalized_query = _normalize_search_query(q)
    if not normalized_query:
        return []

    cache_key = f"search:query:{normalized_query}:{limit}"
    cached = _cache_get(cache_key, _safe_int_env("SEARCH_QUERY_CACHE_TTL_SECONDS", 300, minimum=30))
    if cached is not None:
        return cached

    normalized_ticker = _normalize_ticker_input(q)
    pinned_catalog = _catalog_match_for_ticker(normalized_ticker)
    query_variants = _search_query_variants(q)
    catalog_results: List[Dict[str, Any]] = []
    for variant in query_variants or [q]:
        catalog_results.extend(_fuzzy_catalog_search(variant, limit=limit))
    if pinned_catalog:
        catalog_results = [pinned_catalog, *catalog_results]
    live_results: List[Dict[str, Any]] = []
    yahoo_results: List[Dict[str, Any]] = []
    live_task = asyncio.create_task(get_discovery_service().search_ticker(q))
    yahoo_task = asyncio.gather(
        *[
            _search_yahoo_finance(variant, limit=max(limit, 8))
            for variant in (query_variants or [q])[:3]
        ]
    )
    provider_results = await asyncio.gather(
        asyncio.wait_for(live_task, timeout=SEARCH_DISCOVERY_TIMEOUT_SECONDS),
        asyncio.wait_for(yahoo_task, timeout=SEARCH_QUOTE_PROVIDER_TIMEOUT_SECONDS),
        return_exceptions=True,
    )
    live_result, yahoo_result = provider_results
    if not isinstance(live_result, BaseException):
        live_results = live_result or []
    if not isinstance(yahoo_result, BaseException):
        yahoo_results = [item for batch in yahoo_result for item in (batch or [])]

    merged: List[Dict[str, Any]] = []
    seen = set()
    scored_items = [item for item in [*catalog_results, *yahoo_results, *live_results] if _is_supported_search_quote(item)]
    scored_items.sort(key=lambda row: _quote_search_score(q, row), reverse=True)
    for item in scored_items:
        ticker = str(item.get("ticker", "")).upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            merged.append(item)
    return _cache_set(cache_key, merged[:limit])


async def _resolve_asset_query(q: str, limit: int = 6) -> Dict[str, Any]:
    raw = (q or "").strip()
    normalized = _normalize_ticker_input(raw)
    results = await _resolve_search_results(raw, limit=max(limit, 3))
    best = results[0] if results else None

    if best:
        best_score = _quote_search_score(raw, best)
        best_type = str(best.get("type") or "").lower()
        if best_type in {"alias", "fuzzy"}:
            best_score = max(best_score, 118)
        confidence = "high" if best_score >= 115 else "medium" if best_score >= 82 else "low"
        return {
            "query": raw,
            "normalized": normalized,
            "ticker": str(best.get("ticker", "")).upper(),
            "name": best.get("name") or best.get("ticker"),
            "exchange": best.get("exchange"),
            "type": best.get("type"),
            "source": best.get("source") or best.get("type") or "catalog",
            "confidence": confidence,
            "score": round(best_score, 2),
            "alternatives": results[1:limit],
        }

    return {
        "query": raw,
        "normalized": normalized,
        "ticker": normalized,
        "name": normalized,
        "exchange": None,
        "type": "direct",
        "source": "normalizer",
        "confidence": "low",
        "score": 0,
        "alternatives": [],
    }


def _fallback_search_results(q: str) -> List[Dict[str, Any]]:
    """Keep direct tickers and curated aliases usable when live search fails."""
    raw = (q or "").strip()
    normalized = _normalize_ticker_input(raw)
    if not normalized:
        return []

    catalog = _catalog_match_for_ticker(normalized)
    if catalog:
        return [catalog]

    direct_symbol = re.fullmatch(r"[$#]?[A-Za-z0-9][A-Za-z0-9.\-^=]{0,19}", raw)
    if not direct_symbol:
        return []

    quote_type = "CRYPTOCURRENCY" if normalized.endswith("-USD") else "EQUITY"
    return [{
        "ticker": normalized,
        "name": normalized,
        "exchange": None,
        "type": quote_type,
        "source": "normalizer_fallback",
    }]


DEFAULT_SEARCH_SUGGESTIONS = {
    "Jetzt interessant": [
        "NVIDIA Corporation (NVDA)",
        "Apple Inc. (AAPL)",
        "Robinhood Markets Inc. (HOOD)",
        "NIKE Inc. (NKE)",
        "Palantir Technologies Inc. (PLTR)",
    ],
    "ETFs & Makro": [
        "SPDR S&P 500 ETF Trust (SPY)",
        "Invesco QQQ Trust (QQQ)",
        "SPDR Gold Shares (GLD)",
        "iShares 20+ Year Treasury Bond ETF (TLT)",
        "Energy Select Sector SPDR Fund (XLE)",
    ],
    "Crypto": ["Bitcoin USD (BTC-USD)", "Ethereum USD (ETH-USD)", "Solana USD (SOL-USD)"],
}


def _search_display_for_ticker(ticker: str, fallback_name: str = "") -> str:
    symbol = (ticker or "").strip().upper()
    if not symbol:
        return ""
    catalog = _catalog_match_for_ticker(symbol)
    name = fallback_name or (catalog or {}).get("name") or symbol
    return f"{name} ({symbol})"


def _search_asset_type_label(item: Dict[str, Any]) -> str:
    symbol = str(item.get("ticker") or item.get("symbol") or "").strip().upper()
    quote_type = str(item.get("type") or "").strip().upper()
    if symbol.endswith("-USD") or quote_type == "CRYPTOCURRENCY":
        return "Crypto"
    if symbol.startswith("^") or symbol.endswith("=F") or quote_type == "INDEX":
        return "Index"
    if quote_type in {"ETF", "MUTUALFUND", "FUND"}:
        return "ETF"
    if symbol in {
        "SPY",
        "QQQ",
        "QQQM",
        "VOO",
        "VTI",
        "VT",
        "VXUS",
        "SCHD",
        "SOXX",
        "IBIT",
        "FBTC",
        "GBTC",
        "BITO",
        "DIA",
        "IWM",
        "URTH",
        "GLD",
        "TLT",
        "XLE",
        "USO",
        "VUG",
        "VTV",
        "VNQ",
        "VYM",
        "JEPI",
        "JEPQ",
    }:
        return "ETF"
    return "Aktie"


def _extract_search_symbol(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    return str(item.get("ticker") or item.get("symbol") or item.get("asset") or item.get("value") or "").strip().upper()


def _add_search_suggestion(bucket: List[str], seen: set[str], item: Any, limit: int = 6) -> None:
    if len(bucket) >= limit:
        return
    symbol = _extract_search_symbol(item)
    if not symbol:
        return
    normalized = _normalize_ticker_input(symbol)
    if not normalized or normalized in seen:
        return
    name = ""
    if isinstance(item, dict):
        name = str(item.get("name") or item.get("company") or item.get("label") or "").strip()
    display = _search_display_for_ticker(normalized, name)
    if display:
        seen.add(normalized)
        bucket.append(display)


def _macro_search_rows_from_brief(brief: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    def add_symbol(value: Any) -> None:
        symbol = _normalize_ticker_input(str(value or "").strip())
        if symbol:
            rows.append({"ticker": symbol})

    for ping in (brief.get("event_pings") or [])[:6]:
        if not isinstance(ping, dict):
            continue
        for symbol in ping.get("symbols") or []:
            add_symbol(symbol)
        trade_impact = ping.get("trade_impact") if isinstance(ping.get("trade_impact"), dict) else {}
        for symbol in trade_impact.get("symbols") or []:
            add_symbol(symbol)

    for event in (brief.get("event_layer") or [])[:6]:
        if not isinstance(event, dict):
            continue
        add_symbol(event.get("ticker"))
        intelligence = event.get("event_intelligence") if isinstance(event.get("event_intelligence"), dict) else {}
        for symbol in intelligence.get("affected_assets") or []:
            add_symbol(symbol)

    for news in (brief.get("top_news") or [])[:6]:
        if isinstance(news, dict):
            add_symbol(news.get("ticker") or news.get("symbol"))

    return rows


async def _build_dynamic_search_suggestions() -> Dict[str, List[str]]:
    cache_key = "search:suggestions:dynamic"
    cached = _cache_get(cache_key, _safe_int_env("SEARCH_SUGGESTIONS_CACHE_TTL_SECONDS", 120, minimum=20))
    if cached is not None:
        if isinstance(cached, dict):
            cached.pop("meta", None)
        return cached

    brief = get_morning_brief_service().get_cached_or_last_brief() or {}
    market_movers = brief.get("market_movers", {}) if isinstance(brief, dict) else {}
    if not isinstance(market_movers, dict):
        market_movers = {}

    suggestions: Dict[str, List[str]] = {}
    live_movers: Dict[str, List[Dict[str, Any]]] = {"gainers": [], "losers": []}

    try:
        discovery = get_discovery_service()
        gainers_task = asyncio.create_task(discovery.get_market_movers("gainers", "1d"))
        losers_task = asyncio.create_task(discovery.get_market_movers("losers", "1d"))
        gainers_result, losers_result = await asyncio.wait_for(
            asyncio.gather(gainers_task, losers_task, return_exceptions=True),
            timeout=1.15,
        )
        if isinstance(gainers_result, list):
            live_movers["gainers"] = [item for item in gainers_result if isinstance(item, dict)]
        if isinstance(losers_result, list):
            live_movers["losers"] = [item for item in losers_result if isinstance(item, dict)]
    except Exception:
        live_movers = {"gainers": [], "losers": []}

    def add_category(name: str, rows: List[Any], limit: int = 6) -> None:
        bucket: List[str] = []
        # A ticker may be relevant for multiple contexts (for example a
        # Future Star that is also an open Paper Trade). Deduplicate only
        # inside one category so those context signals remain visible.
        category_seen: set[str] = set()
        for row in rows or []:
            _add_search_suggestion(bucket, category_seen, row, limit=limit)
        if bucket:
            suggestions[name] = bucket

    if isinstance(brief, dict):
        mover_gainers = (market_movers.get("gainers") or [])[:3] if isinstance(market_movers, dict) else []
        add_category(
            "Jetzt interessant",
            [
                *(brief.get("trade_setups") or [])[:3],
                *(brief.get("watchlist_impact") or [])[:3],
                *(brief.get("product_catalysts") or [])[:3],
                *live_movers["gainers"][:3],
                *mover_gainers,
            ],
        )
        add_category("Macro Alerts", _macro_search_rows_from_brief(brief), limit=6)
        add_category(
            "Katalysatoren",
            [
                *(brief.get("earnings_calendar") or [])[:3],
                *(brief.get("earnings_results") or [])[:3],
                *(brief.get("product_catalysts") or [])[:4],
            ],
        )

    if isinstance(market_movers, dict):
        add_category(
            "Market Movers",
            [
                *live_movers["gainers"][:4],
                *live_movers["losers"][:4],
                *(market_movers.get("gainers") or [])[:4],
                *(market_movers.get("losers") or [])[:4],
            ],
        )

    try:
        # Keep search suggestions fast: the full Future-Star scanner performs many
        # market-data calls, so the search bar uses the curated radar universe only.
        future_rows = []
        for ticker in getattr(get_discovery_service(), "future_star_watch", [])[:6]:
            catalog = _catalog_match_for_ticker(ticker) or {}
            future_rows.append({"ticker": ticker, "name": catalog.get("name") or ticker})
        add_category("Future Stars", future_rows, limit=6)
    except Exception:
        pass

    try:
        radar_rows: List[Dict[str, Any]] = []
        for item in get_portfolio_manager().get_signal_watch_items()[:8]:
            if isinstance(item, dict) and str(item.get("kind", "")).lower() == "ticker":
                radar_rows.append({"ticker": item.get("value"), "name": item.get("value")})
        for portfolio in get_portfolio_manager().get_portfolios()[:3]:
            for holding in (portfolio.get("holdings") or [])[:4]:
                radar_rows.append(holding)
        add_category("Mein Radar", radar_rows, limit=6)
    except Exception:
        pass

    try:
        paper_rows: List[Dict[str, Any]] = []
        for trade in get_portfolio_manager().list_paper_trades(status="open", limit=12):
            if isinstance(trade, dict):
                paper_rows.append(
                    {
                        "ticker": trade.get("ticker"),
                    }
                )
        add_category("Paper Trading", paper_rows, limit=6)
    except Exception:
        pass

    try:
        forecast_rows: List[Dict[str, Any]] = []
        for forecast in get_portfolio_manager().list_signal_forecasts(limit=12):
            if isinstance(forecast, dict):
                forecast_rows.append(
                    {
                        "ticker": forecast.get("symbol"),
                    }
                )
        add_category("Lernsignale", forecast_rows, limit=6)
    except Exception:
        pass

    for category, values in DEFAULT_SEARCH_SUGGESTIONS.items():
        if category not in suggestions:
            suggestions[category] = values

    return _cache_set(cache_key, {key: values[:6] for key, values in suggestions.items() if values})


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except Exception:
        return None


def _format_ratio_pct(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    pct = value * 100 if abs(value) <= 1 else value
    return f"{pct:+.1f}%"


def _format_dividend_yield(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    pct = normalize_dividend_yield_pct(value)
    if pct is None:
        return "n/a"
    return f"{pct:+.1f}%"


def _build_business_quality_checks(data: Dict[str, Any]) -> Dict[str, Any]:
    fundamentals = data.get("fundamentals", {}) if isinstance(data.get("fundamentals"), dict) else {}
    statements = fundamentals.get("financial_statements", {}) if isinstance(fundamentals.get("financial_statements"), dict) else {}
    trends = statements.get("trends", {}) if isinstance(statements.get("trends"), dict) else {}
    annual = statements.get("annual", []) if isinstance(statements.get("annual"), list) else []
    latest_annual = annual[0] if annual and isinstance(annual[0], dict) else {}
    earnings_history = data.get("earnings_history", []) if isinstance(data.get("earnings_history"), list) else []
    latest_earnings = earnings_history[0] if earnings_history and isinstance(earnings_history[0], dict) else {}

    revenue_growth = _safe_float(fundamentals.get("revenue_growth"))
    revenue_yoy = _safe_float(trends.get("revenue_yoy"))
    quarterly_revenue_yoy = _safe_float(trends.get("quarterly_revenue_yoy"))
    revenue_cagr = _safe_float(trends.get("revenue_cagr"))
    profit_margin = _safe_float(fundamentals.get("profit_margin"))
    fcf_margin = _safe_float(latest_annual.get("fcf_margin"))
    dividend_yield = _safe_float(fundamentals.get("dividend_yield"))
    payout_ratio = _safe_float(fundamentals.get("payout_ratio"))
    payout_ratio_pct = ratio_to_pct(payout_ratio)
    free_cashflow = _safe_float(fundamentals.get("free_cashflow") or latest_annual.get("free_cashflow"))
    eps_surprise = _safe_float(latest_earnings.get("eps_surprise_pct"))

    revenue_inputs = [revenue_growth, revenue_yoy, quarterly_revenue_yoy, revenue_cagr]
    revenue_known = sum(value is not None for value in revenue_inputs)
    revenue_positive = sum(
        1
        for value, hurdle in [
            (revenue_growth, 0.05),
            (revenue_yoy, 0),
            (quarterly_revenue_yoy, 0),
            (revenue_cagr, 0.03),
        ]
        if value is not None and value >= hurdle
    )
    revenue_status = "unknown"
    if revenue_known:
        revenue_status = "met" if revenue_positive >= max(1, math.ceil(revenue_known / 2)) else "missed"

    dividend_reasons: List[str] = []
    dividend_status = "not_dividend_stock"
    if dividend_yield is not None and dividend_yield > 0:
        dividend_status = "solid"
        dividend_reasons.append(f"Yield {_format_dividend_yield(dividend_yield)}")
        if payout_ratio_pct is not None:
            dividend_reasons.append(f"Payout {payout_ratio_pct:+.1f}%")
            if payout_ratio_pct > 80:
                dividend_status = "watch"
        if free_cashflow is not None and free_cashflow <= 0:
            dividend_status = "risk"
            dividend_reasons.append("Free Cashflow negativ")
        if revenue_yoy is not None and revenue_yoy < 0 and dividend_status == "solid":
            dividend_status = "watch"
            dividend_reasons.append("Umsatz ruecklaeufig")

    return {
        "revenue_status": revenue_status,
        "dividend_status": dividend_status,
        "checks": [
            {
                "label": "Umsatzziele / Revenue-Qualitaet",
                "status": revenue_status,
                "value": _format_ratio_pct(quarterly_revenue_yoy if quarterly_revenue_yoy is not None else revenue_growth),
                "detail": "Erfuellt" if revenue_status == "met" else "Nicht klar erfuellt" if revenue_status == "missed" else "Zu wenig Daten",
            },
            {
                "label": "Earnings-Erwartung",
                "status": latest_earnings.get("status") or "unknown",
                "value": f"{eps_surprise:+.1f}%" if eps_surprise is not None else "n/a",
                "detail": "Letztes Quartal gegen Konsens",
            },
            {
                "label": "Dividenden-Nutzung",
                "status": dividend_status,
                "value": ", ".join(dividend_reasons[:2]) if dividend_reasons else "Keine belastbare Dividendenbasis",
                "detail": "Yield, Payout, Cashflow und Umsatztrend kombiniert",
            },
            {
                "label": "Cash-/Margenqualitaet",
                "status": "solid" if (profit_margin or 0) > 0 and (fcf_margin or 0) > 0 else "watch",
                "value": f"Margin {_format_ratio_pct(profit_margin)} / FCF {_format_ratio_pct(fcf_margin)}",
                "detail": "Langfristige Haltbarkeit der Aktie",
            },
        ],
    }


def get_app_password() -> str:
    return os.getenv("APP_ACCESS_PASSWORD", "").strip()


def get_session_secret() -> str:
    return os.getenv("APP_SESSION_SECRET", "").strip()


def get_login_max_attempts() -> int:
    return max(1, int(os.getenv("APP_LOGIN_MAX_ATTEMPTS", "5")))


def get_login_lockout_minutes() -> int:
    return max(1, int(os.getenv("APP_LOGIN_LOCKOUT_MINUTES", "15")))


def use_secure_cookies() -> bool:
    explicit = os.getenv("APP_COOKIE_SECURE")
    if explicit is not None and explicit.strip() != "":
        return explicit.strip().lower() in {"1", "true", "yes", "on"}
    return bool(
        os.getenv("RAILWAY_PUBLIC_DOMAIN")
        or os.getenv("RAILWAY_STATIC_URL")
        or os.getenv("APP_ENV", "").strip().lower() in {"production", "prod"}
    )


def create_session_value() -> str:
    token = secrets.token_urlsafe(24)
    signature = hmac.new(
        get_session_secret().encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{token}.{signature}"


def is_valid_session(session_value: str | None) -> bool:
    if not session_value or "." not in session_value or not get_session_secret():
        return False
    token, signature = session_value.split(".", 1)
    expected = hmac.new(
        get_session_secret().encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, expected)

def get_discovery_service():
    global _discovery_service
    if _discovery_service is None:
        print("Initializing DiscoveryService...")
        _discovery_service = DiscoveryService()
    return _discovery_service

def get_portfolio_manager():
    global _portfolio_manager
    if _portfolio_manager is None:
        print("Initializing PortfolioManager...")
        _portfolio_manager = PortfolioManager()
    return _portfolio_manager

def get_public_signal_service():
    global _public_signal_service
    if _public_signal_service is None:
        print("Initializing PublicSignalService...")
        _public_signal_service = PublicSignalService()
    return _public_signal_service

def get_email_alert_service():
    global _email_alert_service
    if _email_alert_service is None:
        print("Initializing EmailAlertService...")
        _email_alert_service = EmailAlertService(
            get_portfolio_manager(),
            get_public_signal_service(),
            get_morning_brief_service(),
            get_session_list_service(),
            get_signal_score_service(),
            get_push_service(),
            get_forecast_learning_service(),
        )
    return _email_alert_service

def get_forecast_learning_service():
    global _forecast_learning_service
    if _forecast_learning_service is None:
        print("Initializing ForecastLearningService...")
        _forecast_learning_service = ForecastLearningService(get_portfolio_manager())
    return _forecast_learning_service

def get_morning_brief_service():
    global _morning_brief_service
    if _morning_brief_service is None:
        print("Initializing MorningBriefService...")
        _morning_brief_service = MorningBriefService()
    return _morning_brief_service

def get_signal_score_service():
    global _signal_score_service
    if _signal_score_service is None:
        _signal_score_service = SignalScoreService()
    return _signal_score_service

def get_session_list_service():
    global _session_list_service
    if _session_list_service is None:
        _session_list_service = SessionListService()
    return _session_list_service

def get_paper_trading_service():
    global _paper_trading_service
    if _paper_trading_service is None:
        _paper_trading_service = PaperTradingService(get_portfolio_manager())
    return _paper_trading_service

def get_trading_signals_service():
    global _trading_signals_service
    if _trading_signals_service is None:
        _trading_signals_service = TradingSignalsService()
    return _trading_signals_service

def get_asymmetric_trade_service():
    global _asymmetric_trade_service
    if _asymmetric_trade_service is None:
        _asymmetric_trade_service = AsymmetricTradeService(
            anchored_vwap_service=get_anchored_vwap_service(),
            whale_flow_service=get_whale_flow_service(),
            liquidity_zone_service=get_liquidity_zone_service(),
            multi_timeframe_service=get_multi_timeframe_service(),
        )
    return _asymmetric_trade_service

def get_relative_strength_service():
    global _relative_strength_service
    if _relative_strength_service is None:
        _relative_strength_service = RelativeStrengthService()
    return _relative_strength_service

def get_trade_lifecycle_service():
    global _trade_lifecycle_service
    if _trade_lifecycle_service is None:
        _trade_lifecycle_service = TradeLifecycleService(get_portfolio_manager())
    return _trade_lifecycle_service

def get_portfolio_heat_service():
    global _portfolio_heat_service
    if _portfolio_heat_service is None:
        _portfolio_heat_service = PortfolioHeatService()
    return _portfolio_heat_service

def get_anchored_vwap_service():
    global _anchored_vwap_service
    if _anchored_vwap_service is None:
        _anchored_vwap_service = AnchoredVWAPService()
    return _anchored_vwap_service

def get_whale_flow_service():
    global _whale_flow_service
    if _whale_flow_service is None:
        _whale_flow_service = WhaleFlowService()
    return _whale_flow_service

def get_liquidity_zone_service():
    global _liquidity_zone_service
    if _liquidity_zone_service is None:
        _liquidity_zone_service = LiquidityZoneService()
    return _liquidity_zone_service

def get_multi_timeframe_service():
    global _multi_timeframe_service
    if _multi_timeframe_service is None:
        _multi_timeframe_service = MultiTimeframeService()
    return _multi_timeframe_service

def get_telegram_interactive_service():
    global _telegram_interactive_service
    if _telegram_interactive_service is None:
        cfg = get_email_alert_service().get_config()
        _telegram_interactive_service = TelegramInteractiveService(
            bot_token=cfg.telegram_bot_token,
            allowed_chat_ids=cfg.telegram_chat_id,
            asymmetric_trade_service=get_asymmetric_trade_service(),
            options_edge_service=getattr(get_asymmetric_trade_service(), "options_service", None),
            volume_profile_service=getattr(get_asymmetric_trade_service(), "volume_service", None),
            market_regime_service=getattr(get_asymmetric_trade_service(), "regime_service", None),
            relative_strength_service=get_relative_strength_service(),
            trade_lifecycle_service=get_trade_lifecycle_service(),
            portfolio_heat_service=get_portfolio_heat_service(),
            anchored_vwap_service=get_anchored_vwap_service(),
            whale_flow_service=get_whale_flow_service(),
            liquidity_zone_service=get_liquidity_zone_service(),
            multi_timeframe_service=get_multi_timeframe_service(),
            trading_signals_service=get_trading_signals_service(),
            alert_service=get_email_alert_service(),
            portfolio_manager=get_portfolio_manager(),
        )
    return _telegram_interactive_service


def _get_paper_news_context(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Reuse a recent brief or build a fast one without making news a hard dependency."""
    cached = _cache_get(
        "morning_brief:full",
        _safe_int_env("PAPER_TRADING_NEWS_CONTEXT_MAX_AGE_SECONDS", 3600, minimum=60),
    )
    if isinstance(cached, dict):
        return cached
    try:
        brief = get_morning_brief_service().get_brief_fast(snapshot)
        return brief if isinstance(brief, dict) else {}
    except Exception:
        return {}


async def _refresh_scalable_readonly_context() -> Dict[str, Any]:
    """Refresh optional broker context without invalidating a reconciled holdings snapshot."""
    service = get_scalable_integration_service()
    timeout_seconds = _safe_int_env("SCALABLE_CONTEXT_REFRESH_TIMEOUT_SECONDS", 120, minimum=30)
    result: Dict[str, Any] = {"read_only": True}
    for key, refresh in (
        ("market_context", service.refresh_market_context),
        ("transactions", service.refresh_transactions),
    ):
        try:
            result[key] = await asyncio.wait_for(asyncio.to_thread(refresh), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            result[key] = {"status": "error", "error_code": "refresh_timeout"}
        except ScalableIntegrationError as exc:
            result[key] = {"status": "error", "error_code": exc.code}
        except Exception as exc:
            result[key] = {"status": "error", "error_type": exc.__class__.__name__}
    return result


async def _build_scalable_decision_report() -> Dict[str, Any]:
    """Build a fresh, evidence-gated read-only report after a reconciled sync."""
    timeout_seconds = _safe_int_env("SCALABLE_DECISION_TIMEOUT_SECONDS", 120, minimum=30)
    analysis = await asyncio.wait_for(
        asyncio.to_thread(get_scalable_integration_service().portfolio_analysis),
        timeout=timeout_seconds,
    )
    items = await asyncio.to_thread(get_portfolio_manager().get_signal_watch_items)
    watched_tickers = {
        str(item.get("value") or "").strip().upper()
        for item in items
        if str(item.get("kind") or "").strip().lower() == "ticker"
    }
    for holding in analysis.get("holdings") or []:
        ticker = str(holding.get("ticker") or "").strip().upper()
        if ticker and ticker not in watched_tickers:
            items.append({"kind": "ticker", "value": ticker, "source": "scalable_read_only"})
            watched_tickers.add(ticker)
    snapshot = await asyncio.wait_for(
        asyncio.to_thread(get_public_signal_service().build_watchlist_snapshot, items),
        timeout=timeout_seconds,
    )
    settings = await asyncio.to_thread(get_portfolio_manager().get_signal_score_settings)
    scoreboard = await asyncio.wait_for(
        get_signal_score_service().build_scoreboard(snapshot, settings),
        timeout=timeout_seconds,
    )
    news_context = await asyncio.to_thread(_get_paper_news_context, snapshot)
    paper_dashboard = await asyncio.wait_for(
        asyncio.to_thread(
            get_paper_trading_service().build_dashboard,
            scoreboard,
            settings,
            news_context,
        ),
        timeout=timeout_seconds,
    )
    report = ScalableDecisionService().build(analysis, paper_dashboard)
    previous_raw = await asyncio.to_thread(
        get_portfolio_manager().get_app_setting,
        "scalable_decision_report_v1",
        "",
    )
    try:
        previous_report = json.loads(previous_raw) if previous_raw else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        previous_report = {}
    if report.get("fingerprint") != previous_report.get("fingerprint") or not previous_report.get("audit"):
        report["audit"] = await asyncio.to_thread(
            get_portfolio_manager().record_decision_audit,
            event_type="scalable_decision_report",
            subject="scalable-capital-read-only",
            decision="portfolio_actions_and_research_ideas",
            data_as_of=report.get("portfolio_as_of"),
            source_status="reconciled_read_only",
            sources=[],
            model_version=str(report.get("schema") or "scalable-telegram-decisions.v1"),
            rule_version="scalable-decision-gates.v2",
            user_action="decision_report_changed",
            payload={
                "fingerprint": report.get("fingerprint"),
                "decisions": report.get("decisions") or [],
                "ideas": report.get("ideas") or [],
            },
        )
    await asyncio.to_thread(
        get_portfolio_manager().set_app_setting,
        "scalable_decision_report_v1",
        json.dumps(report, ensure_ascii=False),
    )
    return report


async def _send_scalable_decision_report(*, force: bool = False) -> Dict[str, Any]:
    report = await _build_scalable_decision_report()
    delivery = await asyncio.to_thread(
        get_email_alert_service().send_scalable_decision_report,
        report,
        force=force,
    )
    return {"report": report, "telegram": delivery}

def get_trading_intelligence_service():
    global _trading_intelligence_service
    if _trading_intelligence_service is None:
        _trading_intelligence_service = TradingIntelligenceService()
    return _trading_intelligence_service

def get_realtime_market_service():
    global _realtime_market_service
    if _realtime_market_service is None:
        _realtime_market_service = RealtimeMarketService()
    return _realtime_market_service


def get_alpaca_stream_adapter() -> AlpacaMarketDataAdapter:
    global _alpaca_stream_adapter
    if _alpaca_stream_adapter is None:
        _alpaca_stream_adapter = AlpacaMarketDataAdapter(AlpacaStreamConfig.from_env())
    return _alpaca_stream_adapter


def _alpaca_stream_health() -> Dict[str, Any]:
    try:
        return get_alpaca_stream_adapter().health()
    except Exception as exc:
        return {
            "provider": "alpaca",
            "enabled": _env_enabled("ALPACA_MARKET_DATA_ENABLED", "false"),
            "state": "configuration_error",
            "error_type": exc.__class__.__name__,
            "message": str(exc),
            "credentials_present": bool(
                os.getenv("ALPACA_API_KEY_ID", "").strip()
                and os.getenv("ALPACA_API_SECRET_KEY", "").strip()
            ),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


def get_alpaca_paper_broker_adapter() -> AlpacaPaperBrokerAdapter:
    global _alpaca_paper_broker_adapter
    if _alpaca_paper_broker_adapter is None:
        _alpaca_paper_broker_adapter = AlpacaPaperBrokerAdapter(AlpacaPaperConfig.from_env())
    return _alpaca_paper_broker_adapter


def _alpaca_paper_broker_health() -> Dict[str, Any]:
    try:
        return get_alpaca_paper_broker_adapter().health()
    except Exception as exc:
        return {
            "provider": "alpaca",
            "account_mode": "paper",
            "paper_only": True,
            "enabled": _env_enabled("ALPACA_PAPER_ENABLED", "false"),
            "state": "configuration_error",
            "error_type": exc.__class__.__name__,
            "message": str(exc),
            "credentials_present": bool(
                (os.getenv("ALPACA_PAPER_API_KEY_ID", "").strip() or os.getenv("APCA_API_KEY_ID", "").strip())
                and (os.getenv("ALPACA_PAPER_API_SECRET_KEY", "").strip() or os.getenv("APCA_API_SECRET_KEY", "").strip())
            ),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


def get_broker_reconciliation_service() -> BrokerReconciliationService:
    return BrokerReconciliationService(get_alpaca_paper_broker_adapter())

def get_push_service():
    global _push_service
    if _push_service is None:
        from src.push_service import PushService
        _push_service = PushService()
    return _push_service


def browser_push_enabled() -> bool:
    return _env_enabled("BROWSER_PUSH_ENABLED", "false")


@app.middleware("http")
async def require_single_user_auth(request: Request, call_next):
    path = request.url.path
    open_paths = {
        "/api/health",
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/status",
        "/api/compliance/status",
    }
    if not path.startswith("/api") or path in open_paths:
        return await call_next(request)

    password = get_app_password()
    secret = get_session_secret()
    if not password or not secret:
        return JSONResponse(
            status_code=503,
            content={"detail": "App security is not configured. Set APP_ACCESS_PASSWORD and APP_SESSION_SECRET."},
        )

    session_value = request.cookies.get(SESSION_COOKIE_NAME)
    if not is_valid_session(session_value):
        return JSONResponse(status_code=401, content={"detail": "Authentication required."})

    return await call_next(request)


@app.middleware("http")
async def require_external_compliance_approval(request: Request, call_next):
    path = request.url.path
    status = get_compliance_status()
    if status.get("request_allowed") or path in {"/api/health", "/api/compliance/status"}:
        return await call_next(request)
    return JSONResponse(
        status_code=503,
        content={
            "detail": "External distribution is blocked until legal, compliance and privacy approval is documented.",
            "compliance": status,
        },
    )

async def _signal_alert_loop():
    interval_minutes = _scheduler_loop_interval_minutes()
    await asyncio.sleep(5)
    while True:
        now = datetime.now(ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin")))
        try:
            get_portfolio_manager().set_app_setting("brief_scheduler_loop_tick_started_at", now.isoformat())
            tick_timeout_seconds = _safe_int_env("BRIEF_SCHEDULER_TICK_TIMEOUT_SECONDS", 180, minimum=30)
            include_missed = _env_enabled("SCHEDULED_BRIEF_INCLUDE_MISSED_ON_LOOP", "true")
            await asyncio.wait_for(
                _run_scheduler_tick(include_missed=include_missed),
                timeout=tick_timeout_seconds,
            )
            get_portfolio_manager().set_app_setting(
                "brief_scheduler_loop_completed_at",
                datetime.now(ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin"))).isoformat(),
            )
            get_portfolio_manager().set_app_setting("brief_scheduler_loop_error", "")
            get_portfolio_manager().set_app_setting("brief_scheduler_loop_error_at", "")
        except asyncio.TimeoutError:
            message = f"Scheduler tick timed out after {tick_timeout_seconds}s"
            print(f"Signal alert loop error: {message}")
            try:
                get_portfolio_manager().set_app_setting("brief_scheduler_loop_error", message)
                get_portfolio_manager().set_app_setting("brief_scheduler_loop_error_at", datetime.now(timezone.utc).isoformat())
            except Exception:
                pass
        except Exception as e:
            print(f"Signal alert loop error: {e}")
            try:
                get_portfolio_manager().set_app_setting("brief_scheduler_loop_error", str(e))
                get_portfolio_manager().set_app_setting("brief_scheduler_loop_error_at", datetime.now(timezone.utc).isoformat())
            except Exception:
                pass
        interval_minutes = _scheduler_loop_interval_minutes()
        try:
            next_tick = datetime.now(ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin"))) + timedelta(
                minutes=max(1, interval_minutes)
            )
            get_portfolio_manager().set_app_setting("brief_scheduler_loop_next_tick_at", next_tick.isoformat())
        except Exception:
            pass
        await asyncio.sleep(max(1, interval_minutes) * 60)


async def _run_scheduler_tick(include_missed: bool = False) -> None:
    get_portfolio_manager().set_app_setting(
        "brief_scheduler_loop_seen_at",
        datetime.now(ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin"))).isoformat(),
    )
    get_portfolio_manager().set_app_setting("brief_scheduler_last_step_error", "")
    step_timeout = _safe_int_env("BRIEF_SCHEDULER_STEP_TIMEOUT_SECONDS", 90, minimum=15)

    async def run_step(label: str, callback: Any) -> None:
        try:
            await asyncio.wait_for(asyncio.to_thread(callback), timeout=step_timeout)
        except asyncio.TimeoutError:
            message = f"{label} timed out after {step_timeout}s; next scheduler step continues."
            print(f"Scheduler step warning: {message}")
            get_portfolio_manager().set_app_setting("brief_scheduler_last_step_error", message)
        except Exception as exc:
            message = f"{label} failed: {exc}"
            print(f"Scheduler step warning: {message}")
            get_portfolio_manager().set_app_setting("brief_scheduler_last_step_error", message)

    if _env_enabled("SIGNAL_ALERTS_ENABLED", "false"):
        await run_step(
            "Signal alert scan",
            lambda: get_email_alert_service().check_and_send_alerts(False),
        )
    if _env_enabled("CRITICAL_MARKET_ALERTS_ENABLED", "true"):
        await run_step(
            "Critical market alert scan",
            lambda: get_email_alert_service().check_and_send_critical_market_alerts(False),
        )
    if _env_enabled("DAILY_OVERVIEW_ENABLED", "false"):
        await run_step(
            "Daily overview delivery",
            lambda: get_email_alert_service().send_scheduled_daily_overview(include_missed),
        )
    if _env_enabled("PAPER_PERIOD_UPDATES_ENABLED", "true"):
        await run_step(
            "Paper portfolio period update",
            lambda: get_email_alert_service().send_scheduled_paper_period_update(
                lambda: get_paper_trading_service().build_demo_account_snapshot(),
                include_missed,
            ),
        )
    await run_step(
        "Scheduled brief delivery",
        lambda: get_email_alert_service().send_scheduled_open_briefs(include_missed),
    )
    if _env_enabled("APP_DAILY_BACKUP_ENABLED", "true"):
        await run_step("Daily database backup", _run_backup_cycle)
    if _env_enabled("OPERATIONAL_ALERTS_ENABLED", "true"):
        await run_step("Operational health alerts", _run_operational_alert_cycle)
    if _env_enabled("EDGE_SCANNER_ALERTS_ENABLED", "true"):
        await run_step("Trading edge auto-scanner", _run_trading_edge_scanner_cycle)
    if _env_enabled("TRADE_LIFECYCLE_ENABLED", "true"):
        await run_step(
            "Trade lifecycle & trailing stops",
            lambda: get_trade_lifecycle_service().evaluate_active_trades(get_email_alert_service()),
        )
    await run_step("Production soak observation", _record_production_soak_observation)


def _setting_datetime(key: str) -> datetime | None:
    raw = get_portfolio_manager().get_app_setting(key)
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _run_trading_edge_scanner_cycle() -> Dict[str, Any]:
    """
    Automated background cycle:
      1. Checks Macro Regime Shift (VIX spike or flip to RISK_OFF) and notifies via Telegram.
      2. Scans watchlist for Grade A+/A asymmetric setups and dispatches them directly to Telegram.
    """
    manager = get_portfolio_manager()
    alert_service = get_email_alert_service()
    signals_service = get_trading_signals_service()

    # 1. Macro Regime Check & Shift Alert
    try:
        regime = signals_service.get_market_regime()
        stance = regime.get("stance", "RISK_ON")
        vix_val = regime.get("vix", {}).get("value", 16.0)
        prev_stance = manager.get_app_setting("edge_last_macro_stance") or "RISK_ON"

        if stance == "RISK_OFF" and prev_stance != "RISK_OFF":
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            event_key = f"macro_regime_shift:RISK_OFF:{date_str}"
            if event_key not in manager.get_sent_signal_event_keys():
                msg = (
                    f"🚨 <b>MARKT-REGIME ALARM: RISK-OFF AKTIV</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Der CBOE Volatilitätsindex (VIX) steht bei <b>{vix_val}</b>.\n"
                    f"Die Marktbreite (SPY/QQQ) ist im Abwärtstrend.\n\n"
                    f"💡 <b>Handlungsempfehlung:</b>\n"
                    f"• Keine neuen Ausbrüche kaufen (erhöhte Fehlausbruch-Gefahr)\n"
                    f"• Bestehende Longs eng absichern oder 50% Teilgewinne mitnehmen\n"
                    f"• Positionsgrößen bei Neugeschäften auf max. 50% reduzieren."
                )
                config = alert_service.get_config()
                alert_service._validate_telegram_config(config)
                event = {"event_key": event_key, "category": "macro_regime", "title": "Markt-Regime: RISK-OFF", "line": msg}
                alert_service._send_notifications(config, [event], subject="Broker Freund Alarm: RISK-OFF")
                manager.mark_signal_events_sent([event])

        manager.set_app_setting("edge_last_macro_stance", stance)
    except Exception as e:
        print(f"Macro regime shift check error: {e}")

    # 2. Watchlist Setups Auto-Scan & Dispatch
    try:
        items = manager.get_signal_watch_items()
        watchlist = [str(item.get("value") or "").upper() for item in items if item.get("kind") == "ticker" and item.get("value")]
        res = signals_service.scan_and_dispatch_edge_alerts(alert_service, watchlist=watchlist, min_grade=("A+", "A"))

        # 3. Automatic Paper-Trader Bridge: Auto-open Grade A+ setups in Demo Account
        auto_opened_paper_trades = []
        try:
            paper_svc = get_paper_trading_service()
            existing_open = {
                str(t.get("ticker") or "").upper()
                for t in paper_svc._enrich_trades(manager.list_paper_trades(limit=150))
                if t.get("status") == "open"
            }
            # For each newly dispatched setup
            for ticker in res.get("dispatched", []):
                if ticker not in existing_open:
                    acc_snap = paper_svc.build_demo_account_snapshot()
                    avail_cash = float(acc_snap.get("cash") or 50000.0)
                    ticket = signals_service.asymmetric_service.generate_trade_setup(
                        ticker, portfolio_capital=avail_cash, risk_budget_pct=0.75
                    )
                    if ticket and ticket.get("grade") in ("A+", "A"):
                        qty = float(ticket.get("recommended_shares") or 1)
                        trade_payload = {
                            "ticker": ticker,
                            "asset_class": "equity",
                            "direction": "long",
                            "setup_type": f"institutional_edge_{ticket.get('setup_name', 'continuation').lower().replace(' ', '_')}",
                            "entry_price": float(ticket.get("entry_price") or 0.0),
                            "stop_price": float(ticket.get("invalidation_price") or 0.0),
                            "target_price": float(ticket.get("target_1") or 0.0),
                            "quantity": qty,
                            "confidence_score": float(ticket.get("confluence_score") or 95.0),
                            "thesis": f"{ticket.get('catalyst_description', '')} | Konfluenz: {', '.join(ticket.get('confluence_factors', []))} | R:R {ticket.get('risk_reward_ratio')}:1",
                            "notes": f"{ticket.get('grade_badge', '💎 Grade A+')} | Auto-Edge-Scanner | POC ${ticket.get('volume_profile', {}).get('poc')}",
                        }
                        try:
                            paper_svc.create_trade_from_payload(trade_payload, _get_paper_news_context(None))
                            auto_opened_paper_trades.append(ticker)
                            existing_open.add(ticker)
                        except Exception as open_err:
                            print(f"Auto paper trade open error for {ticker}: {open_err}")
            res["auto_opened_paper_trades"] = auto_opened_paper_trades
        except Exception as e:
            print(f"Auto paper trade bridging error: {e}")

        return res
    except Exception as exc:
        print(f"Trading edge auto-scanner failed: {exc}")
        return {"status": "error", "error": str(exc)}


def _run_backup_cycle(force_backup: bool = False, force_restore_test: bool = False) -> Dict[str, Any]:
    """Create due backups and verify restores without touching the live database."""
    manager = get_portfolio_manager()
    service = get_database_backup_service()
    now = datetime.now(timezone.utc)
    backup_interval_hours = _safe_int_env("APP_BACKUP_INTERVAL_HOURS", 24, minimum=1)
    restore_interval_days = _safe_int_env("APP_RESTORE_TEST_INTERVAL_DAYS", 7, minimum=1)
    last_backup = _setting_datetime("database_backup_last_success_at")
    backup_due = force_backup or last_backup is None or (now - last_backup) >= timedelta(hours=backup_interval_hours)
    result: Dict[str, Any] = {"status": "ok", "checked_at": now.isoformat(), "backup_due": backup_due}
    stage = "backup"
    try:
        if backup_due:
            backup = service.create_backup()
            result["backup"] = backup
            manager.set_app_setting("database_backup_last_success_at", backup["created_at"])
            manager.set_app_setting("database_backup_last_result", json.dumps(backup))
            manager.set_app_setting("database_backup_last_error", "")
        else:
            result["backup"] = {"status": "not_due"}

        last_restore = _setting_datetime("database_restore_test_last_success_at")
        restore_due = force_restore_test or last_restore is None or (now - last_restore) >= timedelta(days=restore_interval_days)
        result["restore_test_due"] = restore_due
        if restore_due:
            stage = "restore_test"
            restore = service.verify_restore()
            result["restore_test"] = restore
            manager.set_app_setting("database_restore_test_last_success_at", restore["verified_at"])
            manager.set_app_setting("database_restore_test_last_result", json.dumps(restore))
            manager.set_app_setting("database_restore_test_last_error", "")
        else:
            result["restore_test"] = {"status": "not_due"}
        return result
    except Exception as exc:
        message = f"{exc.__class__.__name__}: {exc}"
        if stage == "backup":
            manager.set_app_setting("database_backup_last_error", message)
        else:
            manager.set_app_setting("database_restore_test_last_error", message)
        result.update({"status": "error", "error": message})
        raise


def _record_production_soak_observation() -> Dict[str, Any]:
    """Persist one automatic stability observation for the exact live deployment."""
    manager = get_portfolio_manager()
    loop_error_at = _setting_datetime("brief_scheduler_loop_error_at")
    current_process_loop_error = (
        manager.get_app_setting("brief_scheduler_loop_error")
        if loop_error_at and loop_error_at >= PROCESS_STARTED_AT
        else None
    )
    return record_production_soak(
        manager,
        release=get_release_identity(),
        database=get_database_status(),
        notification_status=get_email_alert_service().get_notification_status(),
        scheduler_error=current_process_loop_error,
        scheduler_step_error=manager.get_app_setting("brief_scheduler_last_step_error"),
        backup_error=manager.get_app_setting("database_backup_last_error"),
        restore_error=manager.get_app_setting("database_restore_test_last_error"),
        provider_metrics=provider_metrics_snapshot(),
        sent_events=manager.get_sent_signal_events(limit=5000),
    )


def _run_operational_alert_cycle() -> Dict[str, Any]:
    """Detect launch-critical failures and send cooldown-protected Telegram alarms."""
    manager = get_portfolio_manager()
    issues: list[Dict[str, str]] = []
    database = get_database_status()
    if not database.get("writable"):
        issues.append({
            "code": "database_not_writable",
            "title": "Volume/Datenbank nicht beschreibbar",
            "detail": str(database.get("error") or database.get("path") or "SQLite write check failed"),
            "action": "Railway Volume, Mount-Pfad und Schreibrechte sofort pruefen.",
        })
    if database.get("railway_runtime") and not database.get("persistence_ready"):
        issues.append({
            "code": "database_volume_missing",
            "title": "Persistentes Railway Volume fehlt",
            "detail": "Die Datenbank liegt nicht sicher auf dem erkannten Volume.",
            "action": "Volume unter /app/data mounten und PORTFOLIO_DB_PATH abgleichen.",
        })

    scheduler_error = manager.get_app_setting("brief_scheduler_loop_error")
    scheduler_step_error = manager.get_app_setting("brief_scheduler_last_step_error")
    if scheduler_error or scheduler_step_error:
        issues.append({
            "code": "scheduler_error",
            "title": "Scheduler-Fehler erkannt",
            "detail": str(scheduler_error or scheduler_step_error),
            "action": "Health Center und Railway Logs pruefen; faellige Briefings kontrollieren.",
        })

    feed_health = _market_feed_health_check()
    realtime = feed_health.get("realtime") or {}
    yfinance = feed_health.get("yfinance") or {}
    stale_values = []
    for value in (realtime.get("stale_seconds") or {}).values() if isinstance(realtime.get("stale_seconds"), dict) else []:
        try:
            stale_values.append(float(value))
        except (TypeError, ValueError):
            continue
    stale_limit = _safe_int_env("OPERATIONAL_QUOTE_STALE_SECONDS", 900, minimum=60)
    realtime_state = str(realtime.get("status") or "unknown").lower()
    quotes_stale = bool(stale_values and max(stale_values) > stale_limit)
    realtime_required = bool(feed_health.get("realtime_required"))
    realtime_problem = realtime_required and realtime_state in {"error", "degraded", "disconnected", "failed"}
    feed_problem = yfinance.get("status") != "ok" or realtime_problem or quotes_stale
    try:
        previous_feed_failures = int(manager.get_app_setting("operational_market_feed_failure_streak", "0") or 0)
    except (TypeError, ValueError):
        previous_feed_failures = 0
    feed_failure_streak = previous_feed_failures + 1 if feed_problem else 0
    manager.set_app_setting("operational_market_feed_failure_streak", str(feed_failure_streak))
    confirmation_checks = _safe_int_env("OPERATIONAL_MARKET_FEED_CONFIRMATION_CHECKS", 3, minimum=1)
    if feed_problem and feed_failure_streak >= confirmation_checks:
        max_stale_label = f"{max(stale_values):.0f}s" if stale_values else "n/a"
        issues.append({
            "code": "market_quotes_stale",
            "title": "Kursdaten fehlerhaft oder veraltet",
            "detail": (
                f"yfinance={yfinance.get('status')}; realtime={realtime_state}; "
                f"realtime_required={str(realtime_required).lower()}; max_stale={max_stale_label}; "
                f"confirmed={feed_failure_streak}/{confirmation_checks}"
            ),
            "action": "Keine neuen Paper-Trades freigeben; Provider und Kurszeitstempel pruefen.",
        })

    telegram = _telegram_health_check()
    if telegram.get("status") != "ok":
        issues.append({
            "code": "telegram_unavailable",
            "title": "Telegram-Zustellung nicht verfuegbar",
            "detail": str(telegram.get("diagnosis") or telegram.get("error") or telegram.get("status")),
            "action": str(telegram.get("next_step") or "Telegram-Konfiguration pruefen."),
        })

    deliveries: list[Dict[str, Any]] = []
    for issue in issues:
        if issue["code"] == "telegram_unavailable":
            deliveries.append({"code": issue["code"], "status": "unavailable_same_channel"})
            continue
        try:
            delivery = get_email_alert_service().send_operational_alert(
                issue["code"], issue["title"], issue["detail"], issue["action"]
            )
            deliveries.append({"code": issue["code"], **delivery})
        except Exception as exc:
            deliveries.append({"code": issue["code"], "status": "delivery_error", "error": f"{exc.__class__.__name__}: {exc}"})
    payload = {
        "status": "ok" if not issues else "degraded",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "issues": issues,
        "deliveries": deliveries,
        "market_feed_confirmation": {
            "problem_now": feed_problem,
            "failure_streak": feed_failure_streak,
            "required_checks": confirmation_checks,
            "realtime_required": realtime_required,
        },
    }
    manager.set_app_setting("operational_alerts_last_result", json.dumps(payload))
    return payload


async def _scheduler_startup_catchup() -> None:
    await asyncio.sleep(8)
    try:
        await _run_scheduler_tick(include_missed=True)
    except Exception as e:
        print(f"Scheduler startup catchup error: {e}")
        try:
            get_portfolio_manager().set_app_setting("brief_scheduler_loop_error", str(e))
        except Exception:
            pass


def _scheduler_loop_interval_minutes() -> int:
    signal_minutes = _safe_int_env("SIGNAL_ALERTS_INTERVAL_MINUTES", 15, minimum=1)
    brief_minutes = _safe_int_env("BRIEF_SCHEDULER_INTERVAL_MINUTES", 5, minimum=1)
    return min(signal_minutes, brief_minutes)


def _safe_int_env(name: str, default: int, minimum: int | None = None) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except Exception:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


async def _brief_warmup_loop():
    if not _env_enabled("BRIEF_WARMUP_ENABLED", "true"):
        return
    await asyncio.sleep(
        max(0, _safe_int_env("BRIEF_WARMUP_INITIAL_DELAY_SECONDS", 1, minimum=0))
    )
    while True:
        try:
            await _warm_brief_once()
        except Exception as e:
            print(f"Brief warmup loop error: {e}")
        interval_seconds = int(os.getenv("BRIEF_WARMUP_INTERVAL_SECONDS", "300"))
        await asyncio.sleep(max(60, interval_seconds))


async def _run_paper_outcome_cycle(*, force_alerts: bool) -> Dict[str, Any]:
    result = await asyncio.to_thread(get_paper_trading_service().evaluate_due_outcomes)
    paper_learning = get_paper_trading_service()._build_outcome_learning_adjustments()
    try:
        alert_result = await asyncio.to_thread(
            get_email_alert_service().send_paper_learning_alerts,
            paper_learning,
            force_alerts,
        )
    except Exception as alert_error:
        alert_result = {"status": "error", "message": str(alert_error)}

    payload = {
        "checked_at": datetime.utcnow().isoformat(),
        **result,
        "paper_learning_alerts": alert_result,
    }
    get_portfolio_manager().set_app_setting(
        "paper_trade_outcomes_last_result",
        json.dumps(payload),
    )
    return payload


async def _forecast_learning_loop():
    if not _env_enabled("FORECAST_LEARNING_ENABLED", "true"):
        return
    await asyncio.sleep(20)
    while True:
        try:
            result = await asyncio.to_thread(get_forecast_learning_service().evaluate_due_forecasts)
            paper_cycle = await _run_paper_outcome_cycle(force_alerts=False)
            paper_result = {
                key: value
                for key, value in paper_cycle.items()
                if key not in {"checked_at", "paper_learning_alerts"}
            }
            paper_alert_result = paper_cycle.get("paper_learning_alerts") or {}
            paper_news_source_revalidation = await asyncio.to_thread(_run_paper_news_source_revalidation)
            paper_managed_exits = await asyncio.to_thread(_run_paper_managed_exits)
            paper_autopilot_result = await asyncio.to_thread(
                _run_scheduled_paper_learning_autopilot,
                bool(paper_managed_exits.get("closed")),
            )
            paper_capital_rotation = get_paper_trading_service().build_capital_rotation_summary(
                paper_managed_exits,
                paper_autopilot_result,
            )
            paper_management_alerts = await asyncio.to_thread(_send_paper_trade_management_alerts)
            paper_account_status_alerts = await asyncio.to_thread(
                _send_paper_account_status_alerts,
                paper_capital_rotation,
            )
            get_portfolio_manager().set_app_setting(
                "forecast_learning_last_result",
                json.dumps(
                    {
                        "checked_at": datetime.utcnow().isoformat(),
                        **result,
                        "paper_trades": paper_result,
                        "paper_learning_alerts": paper_alert_result,
                        "paper_learning_autopilot": paper_autopilot_result,
                        "paper_capital_rotation": paper_capital_rotation,
                        "paper_news_source_revalidation": paper_news_source_revalidation,
                        "paper_management_alerts": paper_management_alerts,
                        "paper_account_status_alerts": paper_account_status_alerts,
                        "paper_managed_exits": paper_managed_exits,
                    }
                ),
            )
        except Exception as e:
            print(f"Forecast learning loop error: {e}")
            try:
                get_portfolio_manager().set_app_setting("forecast_learning_loop_error", str(e))
            except Exception:
                pass
        interval_minutes = _safe_int_env("FORECAST_OUTCOME_INTERVAL_MINUTES", 30, minimum=5)
        await asyncio.sleep(interval_minutes * 60)


def _run_paper_news_source_revalidation() -> Dict[str, Any]:
    if not _env_enabled("PAPER_NEWS_SOURCE_REVALIDATION_ENABLED", "true"):
        return {"status": "disabled", "message": "Paper-News-Quellenmonitor ist deaktiviert."}
    try:
        return get_paper_trading_service().revalidate_open_news_sources(limit=50)
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _send_paper_trade_management_alerts() -> Dict[str, Any]:
    if not _env_enabled("PAPER_TRADE_MANAGEMENT_ALERTS_ENABLED", "true"):
        return {"status": "disabled", "message": "Paper-Trade-Management-Alerts sind deaktiviert."}
    try:
        trades = get_paper_trading_service()._enrich_trades(
            get_portfolio_manager().list_paper_trades(status="open", limit=50)
        )
        return get_email_alert_service().send_paper_trade_management_alerts(trades)
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _send_paper_account_status_alerts(
    capital_rotation: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not _env_enabled("PAPER_ACCOUNT_STATUS_ALERTS_ENABLED", "true"):
        return {"status": "disabled", "message": "Paper-Konto-Status-Alerts sind deaktiviert."}
    try:
        service = get_paper_trading_service()
        trades = service._enrich_trades(get_portfolio_manager().list_paper_trades(limit=300))
        open_trades = [trade for trade in trades if trade.get("status") == "open"]
        demo_account = service._build_demo_account(trades, [])
        service._attach_period_performance(demo_account, trades)
        readiness = StrategyLibrary.build_readiness(
            trades,
            get_portfolio_manager().list_paper_trade_outcomes(limit=800),
        )
        evidence_campaign = StrategyLibrary.build_evidence_campaign(readiness)
        strategy_candidate_coverage: List[Dict[str, Any]] = []
        raw_autopilot = get_portfolio_manager().get_app_setting("paper_learning_autopilot_last_run", "{}")
        try:
            autopilot_payload = json.loads(raw_autopilot or "{}")
            if isinstance(autopilot_payload, dict) and isinstance(autopilot_payload.get("strategy_candidate_coverage"), list):
                strategy_candidate_coverage = autopilot_payload.get("strategy_candidate_coverage") or []
        except (TypeError, ValueError, json.JSONDecodeError):
            strategy_candidate_coverage = []
        return get_email_alert_service().send_paper_account_status_alert(
            demo_account,
            open_trades,
            evidence_campaign=evidence_campaign,
            strategy_candidate_coverage=strategy_candidate_coverage,
            capital_rotation=capital_rotation,
        )
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _run_paper_managed_exits() -> Dict[str, Any]:
    if not _env_enabled("PAPER_TRADE_AUTO_CLOSE_ON_STOP_TARGET", "true"):
        return {"status": "disabled", "message": "Paper managed exits are disabled."}
    try:
        result = get_paper_trading_service().close_trades_on_management_exits(limit=50)
        if result.get("closed"):
            try:
                result["telegram_alerts"] = get_email_alert_service().send_paper_trade_closed_alerts(
                    result.get("closed") or [],
                    get_paper_trading_service().build_demo_account_snapshot(),
                )
            except Exception as alert_error:
                result["telegram_alerts"] = {"status": "error", "message": str(alert_error)}
        return result
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _run_scheduled_paper_learning_autopilot(
    managed_exit_freed_capacity: bool = False,
) -> Dict[str, Any]:
    if not _env_enabled("PAPER_TRADING_AUTO_LEARN_ENABLED", "true"):
        return {"status": "disabled", "message": "Paper auto-learn is disabled."}

    now = datetime.utcnow()
    cooldown_minutes = _safe_int_env("PAPER_TRADING_AUTO_LEARN_COOLDOWN_MINUTES", 360, minimum=30)
    last_raw = get_portfolio_manager().get_app_setting("paper_learning_autopilot_last_run")
    if last_raw:
        try:
            last_payload = json.loads(last_raw)
            last_run = datetime.fromisoformat(str(last_payload.get("checked_at")))
            last_opened = len(last_payload.get("opened") or []) if isinstance(last_payload, dict) else 0
            effective_cooldown = cooldown_minutes if last_opened else _safe_int_env(
                "PAPER_TRADING_AUTO_LEARN_EMPTY_COOLDOWN_MINUTES",
                30,
                minimum=5,
            )
            next_allowed = last_run + timedelta(minutes=effective_cooldown)
            if now < next_allowed and not managed_exit_freed_capacity:
                return {
                    "status": "cooldown",
                    "checked_at": now.isoformat(),
                    "next_allowed_at": next_allowed.isoformat(),
                    "cooldown_minutes": effective_cooldown,
                    "message": "Paper auto-learn cooldown active.",
                }
        except Exception:
            pass

    try:
        items = get_portfolio_manager().get_signal_watch_items()
        snapshot = get_public_signal_service().build_watchlist_snapshot(items)
        settings = get_portfolio_manager().get_signal_score_settings()
        autopilot_settings = get_portfolio_manager().get_paper_autopilot_settings()
        scoreboard = asyncio.run(get_signal_score_service().build_scoreboard(snapshot, settings))
        news_context = _get_paper_news_context(snapshot)
        result = get_paper_trading_service().run_auto_selection(
            scoreboard,
            settings,
            max_trades=_safe_int_env(
                "PAPER_TRADING_AUTO_LEARN_MAX_TRADES",
                int(autopilot_settings.get("max_trades") or 3),
                minimum=1,
            ),
            execute=True,
            mode=os.getenv("PAPER_TRADING_AUTO_LEARN_MODE", str(autopilot_settings.get("mode") or "aggressive_learning")),
            news_context=news_context,
        )
        if result.get("opened"):
            try:
                result["telegram_alerts"] = get_email_alert_service().send_paper_trade_opened_alerts(
                    result.get("opened") or [],
                    result.get("selected") or [],
                    result.get("demo_account_after") or {},
                )
            except Exception as alert_error:
                result["telegram_alerts"] = {"status": "error", "message": str(alert_error)}
        payload = {
            "checked_at": now.isoformat(),
            "cooldown_minutes": cooldown_minutes,
            "cooldown_bypassed_reason": (
                "managed_exit_freed_capacity"
                if managed_exit_freed_capacity
                else None
            ),
            **convert_numpy_types(result),
        }
        get_portfolio_manager().set_app_setting("paper_learning_autopilot_last_run", json.dumps(payload))
        return payload
    except Exception as exc:
        payload = {
            "status": "error",
            "checked_at": now.isoformat(),
            "message": str(exc),
        }
        get_portfolio_manager().set_app_setting("paper_learning_autopilot_last_run", json.dumps(payload))
        return payload


def _task_state(task: Any) -> str:
    if task is None:
        return "missing"
    try:
        if task.cancelled():
            return "cancelled"
        if task.done():
            return "done"
        return "running"
    except Exception:
        return "unknown"


def _remember_finished_task_error(setting_key: str, task: Any) -> None:
    if task is None or not getattr(task, "done", lambda: False)():
        return
    try:
        exc = task.exception()
    except Exception as error:
        exc = error
    if exc:
        try:
            get_portfolio_manager().set_app_setting(setting_key, str(exc))
        except Exception:
            pass


def _ensure_background_tasks() -> None:
    global _signal_alert_task, _price_alert_task, _brief_warmup_task, _forecast_learning_task, _scheduler_startup_catchup_task, _scalable_sync_task, _alpaca_stream_task, _market_safety_task, _alpaca_paper_broker_task, _broker_reconciliation_task, _telegram_bot_task

    alerts_enabled = _env_enabled("SIGNAL_ALERTS_ENABLED", "false")
    scheduled_briefs_enabled = _env_enabled("SCHEDULED_BRIEFS_ENABLED", "true")

    if alerts_enabled or scheduled_briefs_enabled:
        if _signal_alert_task is None or _signal_alert_task.done():
            _remember_finished_task_error("brief_scheduler_loop_error", _signal_alert_task)
            _signal_alert_task = asyncio.create_task(_signal_alert_loop())

    if scheduled_briefs_enabled and _scheduler_startup_catchup_task is None:
        _scheduler_startup_catchup_task = asyncio.create_task(_scheduler_startup_catchup())

    if scheduled_briefs_enabled:
        if _brief_warmup_task is None or _brief_warmup_task.done():
            _remember_finished_task_error("brief_warmup_loop_error", _brief_warmup_task)
            _brief_warmup_task = asyncio.create_task(_brief_warmup_loop())

    if _price_alert_task is None or _price_alert_task.done():
        _price_alert_task = asyncio.create_task(_price_alert_loop())

    if _forecast_learning_task is None or _forecast_learning_task.done():
        _remember_finished_task_error("forecast_learning_loop_error", _forecast_learning_task)
        _forecast_learning_task = asyncio.create_task(_forecast_learning_loop())

    if _env_enabled("SCALABLE_INTEGRATION_ENABLED", "false") and _env_enabled("SCALABLE_AUTO_SYNC_ENABLED", "true"):
        if _scalable_sync_task is None or _scalable_sync_task.done():
            _remember_finished_task_error("scalable_auto_sync_task_error", _scalable_sync_task)
            _scalable_sync_task = asyncio.create_task(_scalable_auto_sync_loop())

    if _env_enabled("ALPACA_MARKET_DATA_ENABLED", "false"):
        if _alpaca_stream_task is None or _alpaca_stream_task.done():
            _remember_finished_task_error("alpaca_stream_task_error", _alpaca_stream_task)
            try:
                _alpaca_stream_task = asyncio.create_task(get_alpaca_stream_adapter().run())
            except Exception as exc:
                get_portfolio_manager().set_app_setting("alpaca_stream_task_error", str(exc))

    if _env_enabled("FAST_PAPER_ENABLED", "false"):
        if _market_safety_task is None or _market_safety_task.done():
            _remember_finished_task_error("market_safety_task_error", _market_safety_task)
            _market_safety_task = asyncio.create_task(_market_safety_loop())

    if _env_enabled("ALPACA_PAPER_ENABLED", "false"):
        if _alpaca_paper_broker_task is None or _alpaca_paper_broker_task.done():
            _remember_finished_task_error("alpaca_paper_broker_task_error", _alpaca_paper_broker_task)
            try:
                _alpaca_paper_broker_task = asyncio.create_task(get_alpaca_paper_broker_adapter().run())
            except Exception as exc:
                get_portfolio_manager().set_app_setting("alpaca_paper_broker_task_error", str(exc))
        if _broker_reconciliation_task is None or _broker_reconciliation_task.done():
            _remember_finished_task_error("broker_reconciliation_task_error", _broker_reconciliation_task)
            _broker_reconciliation_task = asyncio.create_task(_broker_reconciliation_loop())

    # Interactive 2-Way Telegram Bot Loop
    if _env_enabled("TELEGRAM_INTERACTIVE_BOT_ENABLED", "true"):
        tg_cfg = get_email_alert_service().get_config()
        if tg_cfg.telegram_enabled and tg_cfg.telegram_bot_token and tg_cfg.telegram_chat_id:
            if _telegram_bot_task is None or _telegram_bot_task.done():
                _remember_finished_task_error("telegram_bot_task_error", _telegram_bot_task)
                _telegram_bot_task = asyncio.create_task(get_telegram_interactive_service().run_listener_loop())


async def _market_safety_loop() -> None:
    await asyncio.sleep(1)
    while True:
        try:
            FastPaperSafetyService(get_portfolio_manager()).monitor_stream(_alpaca_stream_health())
        except Exception as exc:
            get_portfolio_manager().set_app_setting("market_safety_loop_error", str(exc))
        await asyncio.sleep(_safe_int_env("MARKET_SAFETY_INTERVAL_SECONDS", 2, minimum=1))


async def _broker_reconciliation_loop() -> None:
    await asyncio.sleep(_safe_int_env("BROKER_RECONCILIATION_START_DELAY_SECONDS", 5, minimum=1))
    while True:
        try:
            await asyncio.to_thread(get_broker_reconciliation_service().reconcile)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            get_portfolio_manager().set_app_setting(
                "broker_reconciliation_last_error",
                json.dumps(
                    {
                        "type": exc.__class__.__name__,
                        "message": str(exc),
                        "at": datetime.now(timezone.utc).isoformat(),
                    }
                ),
            )
        await asyncio.sleep(_safe_int_env("BROKER_RECONCILIATION_INTERVAL_SECONDS", 30, minimum=10))


async def _background_task_watchdog_loop():
    await asyncio.sleep(30)
    while True:
        try:
            _ensure_background_tasks()
            get_portfolio_manager().set_app_setting(
                "background_task_watchdog_seen_at",
                datetime.now(ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin"))).isoformat(),
            )
            get_portfolio_manager().set_app_setting("background_task_watchdog_error", "")
        except Exception as e:
            print(f"Background task watchdog error: {e}")
            try:
                get_portfolio_manager().set_app_setting("background_task_watchdog_error", str(e))
            except Exception:
                pass
        await asyncio.sleep(_safe_int_env("BACKGROUND_TASK_WATCHDOG_INTERVAL_SECONDS", 60, minimum=15))


async def _scalable_auto_sync_loop():
    await asyncio.sleep(_safe_int_env("SCALABLE_AUTO_SYNC_START_DELAY_SECONDS", 60, minimum=15))
    while True:
        try:
            timeout_seconds = _safe_int_env("SCALABLE_AUTO_SYNC_TIMEOUT_SECONDS", 90, minimum=30)
            await asyncio.wait_for(
                asyncio.to_thread(get_scalable_integration_service().sync),
                timeout=timeout_seconds,
            )
            await _refresh_scalable_readonly_context()
            if os.getenv("SCALABLE_TELEGRAM_DECISIONS_ENABLED", "true").strip().lower() not in {
                "0", "false", "no", "off"
            }:
                await _send_scalable_decision_report()
        except asyncio.TimeoutError:
            print("Scalable auto-sync warning: timeout")
        except ScalableIntegrationError as exc:
            print(f"Scalable auto-sync warning: {exc.code}")
        except Exception as exc:
            print(f"Scalable auto-sync warning: {exc.__class__.__name__}")
        interval_minutes = _safe_int_env("SCALABLE_AUTO_SYNC_INTERVAL_MINUTES", 15, minimum=5)
        await asyncio.sleep(interval_minutes * 60)


async def _warm_brief_once() -> Dict[str, Any]:
    started = datetime.now(ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin")))
    items = await asyncio.to_thread(get_portfolio_manager().get_signal_watch_items)
    snapshot = await asyncio.wait_for(
        asyncio.to_thread(get_public_signal_service().build_watchlist_snapshot, items),
        timeout=float(os.getenv("BRIEF_WARMUP_SNAPSHOT_TIMEOUT_SECONDS", "5")),
    )
    brief = await asyncio.wait_for(
        asyncio.to_thread(get_morning_brief_service().get_brief_fast, snapshot, True),
        timeout=float(os.getenv("BRIEF_WARMUP_TIMEOUT_SECONDS", "30")),
    )
    try:
        trading_edge = await asyncio.wait_for(
            asyncio.to_thread(get_morning_brief_service().get_trading_edge, snapshot),
            timeout=float(os.getenv("BRIEF_WARMUP_EDGE_TIMEOUT_SECONDS", "18")),
        )
        _cache_set(TRADING_EDGE_CACHE_KEY, trading_edge or {})
    except Exception:
        # Trading Edge is heavy and optional for delivery. The brief cache is still useful without it.
        pass
    elapsed_ms = int((datetime.now(ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin"))) - started).total_seconds() * 1000)
    return {
        "status": "ok",
        "started_at": started.isoformat(),
        "elapsed_ms": elapsed_ms,
        "watch_items": len(items or []),
        "snapshot_items": len(snapshot.get("items") or []),
        "generated_at": brief.get("generated_at"),
        "quality": brief.get("quality"),
        "headline": brief.get("headline") or brief.get("opening_bias"),
    }


def _is_alert_in_cooldown(last_triggered_at: Optional[str], cooldown_minutes: int) -> bool:
    if not last_triggered_at:
        return False
    try:
        last_ts = datetime.fromisoformat(last_triggered_at)
    except Exception:
        return False
    return datetime.now() < (last_ts + timedelta(minutes=max(1, cooldown_minutes)))


async def _price_alert_loop():
    await asyncio.sleep(8)
    while True:
        try:
            manager = get_portfolio_manager()
            alerts = await asyncio.to_thread(manager.list_price_alerts, True)
            if alerts:
                symbols = sorted({str(alert.get("symbol", "")).upper() for alert in alerts if alert.get("symbol")})
                snapshot = await asyncio.to_thread(get_realtime_market_service().build_snapshot, symbols)
                quote_map = {
                    str(item.get("symbol", "")).upper(): item
                    for item in snapshot.get("quotes", [])
                    if item and item.get("symbol")
                }
                for alert in alerts:
                    symbol = str(alert.get("symbol", "")).upper()
                    quote = quote_map.get(symbol)
                    if not quote:
                        continue
                    current_price = quote.get("price")
                    if current_price is None:
                        continue
                    direction = str(alert.get("direction", "")).lower()
                    target = float(alert.get("target_price") or 0)
                    triggered = (
                        direction == "above" and float(current_price) >= target
                    ) or (
                        direction == "below" and float(current_price) <= target
                    )
                    if not triggered:
                        continue
                    cooldown_minutes = int(alert.get("cooldown_minutes") or 5)
                    if _is_alert_in_cooldown(alert.get("last_triggered_at"), cooldown_minutes):
                        continue

                    alert_id = alert.get("id")
                    if alert_id:
                        manager.update_price_alert(
                            str(alert_id),
                            {"last_triggered_at": datetime.now().isoformat()},
                        )

                    condition = f"{direction} {target:.2f}"
                    try:
                        get_email_alert_service().send_price_alert(
                            symbol=symbol,
                            direction=direction,
                            target_price=target,
                            current_price=float(current_price),
                        )
                    except Exception as notify_error:
                        print(f"Email/Telegram price alert failed for {symbol}: {notify_error}")
        except Exception as e:
            print(f"Price alert loop error: {e}")

        await asyncio.sleep(15)

@app.on_event("startup")
async def startup_event():
    global _background_task_watchdog_task
    _ensure_background_tasks()
    if _background_task_watchdog_task is None or _background_task_watchdog_task.done():
        _background_task_watchdog_task = asyncio.create_task(_background_task_watchdog_loop())


@app.on_event("shutdown")
async def shutdown_event():
    global _alpaca_stream_task, _alpaca_paper_broker_task, _broker_reconciliation_task
    if _alpaca_stream_adapter is not None:
        await _alpaca_stream_adapter.close()
    if _alpaca_stream_task is not None and not _alpaca_stream_task.done():
        _alpaca_stream_task.cancel()
        await asyncio.gather(_alpaca_stream_task, return_exceptions=True)
    if _alpaca_paper_broker_adapter is not None:
        await _alpaca_paper_broker_adapter.close()
    if _alpaca_paper_broker_task is not None and not _alpaca_paper_broker_task.done():
        _alpaca_paper_broker_task.cancel()
        await asyncio.gather(_alpaca_paper_broker_task, return_exceptions=True)
    if _broker_reconciliation_task is not None and not _broker_reconciliation_task.done():
        _broker_reconciliation_task.cancel()
        await asyncio.gather(_broker_reconciliation_task, return_exceptions=True)

# Response Models
class AnalysisResponse(BaseModel):
    ticker: str
    company_name: str
    price_data: Dict[str, Any]
    volatility: Dict[str, Any]
    fundamentals: Dict[str, Any]
    analyst_data: Dict[str, Any]
    short_interest: Dict[str, Any]
    news: List[Dict[str, Any]]
    comparison: Dict[str, Any]
    analysis: Dict[str, Any]
    etf_analysis: Optional[Dict[str, Any]] = None
    recommendation: Dict[str, Any]
    valuation: str
    total_score: float


class PortfolioHolding(BaseModel):
    model_config = ConfigDict(validate_by_name=True)

    ticker: str
    shares: float
    buy_price: Optional[float] = Field(default=None, alias="buyPrice")
    purchase_date: Optional[str] = Field(default=None, alias="purchaseDate")


class PortfolioRequest(BaseModel):
    holdings: List[PortfolioHolding]
    portfolio_id: Optional[str] = None

class CreatePortfolioRequest(BaseModel):
    name: str

class AddHoldingRequest(BaseModel):
    model_config = ConfigDict(validate_by_name=True)

    ticker: str
    shares: float
    buy_price: Optional[float] = Field(default=None, alias="buyPrice")
    purchase_date: Optional[str] = Field(default=None, alias="purchaseDate")


class UpdateHoldingRequest(BaseModel):
    model_config = ConfigDict(validate_by_name=True)

    shares: Optional[float] = None
    buy_price: Optional[float] = Field(default=None, alias="buyPrice")
    purchase_date: Optional[str] = Field(default=None, alias="purchaseDate")

class OracleRequest(BaseModel):
    message: str
    context_ticker: Optional[str] = None
    active_tab: Optional[str] = None
    context_symbols: Optional[List[str]] = None
    portfolio_snapshot: Optional[Dict[str, Any]] = None
    live_quotes: Optional[Dict[str, Any]] = None
    signal_score: Optional[Dict[str, Any]] = None
    morning_brief_summary: Optional[Dict[str, Any]] = None
    learning_summary: Optional[Dict[str, Any]] = None


class PriceAlertCreateRequest(BaseModel):
    symbol: str
    direction: str
    target_price: float
    enabled: bool = True
    cooldown_minutes: int = 5


class PriceAlertUpdateRequest(BaseModel):
    symbol: Optional[str] = None
    direction: Optional[str] = None
    target_price: Optional[float] = None
    enabled: Optional[bool] = None
    cooldown_minutes: Optional[int] = None

class SignalWatchItemRequest(BaseModel):
    kind: str
    value: str

class WorkspaceProfileRequest(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    timezone: Optional[str] = None
    browser_notifications: Optional[bool] = None
    theme: Optional[str] = None
    onboarding_done: Optional[bool] = None
    advisory_enabled: Optional[bool] = None
    investment_objective: Optional[str] = None
    time_horizon: Optional[str] = None
    risk_tolerance: Optional[str] = None
    experience_level: Optional[str] = None
    loss_capacity: Optional[str] = None
    liquidity_need: Optional[str] = None
    preferred_strategy: Optional[str] = None
    max_single_position_pct: Optional[float] = None
    max_portfolio_drawdown_pct: Optional[float] = None
    suitability_notes: Optional[str] = None


class AdvisoryProfileRequest(BaseModel):
    advisory_enabled: Optional[bool] = None
    investment_objective: Optional[str] = None
    time_horizon: Optional[str] = None
    risk_tolerance: Optional[str] = None
    experience_level: Optional[str] = None
    loss_capacity: Optional[str] = None
    liquidity_need: Optional[str] = None
    preferred_strategy: Optional[str] = None
    max_single_position_pct: Optional[float] = None
    max_portfolio_drawdown_pct: Optional[float] = None
    suitability_notes: Optional[str] = None


class SuitabilityCheckRequest(BaseModel):
    symbol: Optional[str] = None
    asset_class: Optional[str] = "equity"
    action: Optional[str] = "watch"
    strategy: Optional[str] = None
    risk_level: Optional[str] = "medium"
    position_pct: Optional[float] = None
    time_horizon: Optional[str] = None
    thesis: Optional[str] = None


class PortfolioAdvisoryCheckRequest(BaseModel):
    holdings: List[Dict[str, Any]] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)


class LoginRequest(BaseModel):
    password: str
    remember_device: bool = True


class PaperTradeCreateRequest(BaseModel):
    ticker: str
    asset_class: str = "equity"
    direction: str = "long"
    setup_type: str = "signal_follow"
    thesis: Optional[str] = None
    entry_price: float
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    quantity: float = 1
    confidence_score: Optional[float] = None
    leverage: float = Field(default=1, ge=1, le=1000)
    notes: Optional[str] = None
    exit_reason: Optional[str] = None
    lessons_learned: Optional[str] = None


class PaperTradeFromPlaybookRequest(BaseModel):
    playbook_id: str
    direction: Optional[str] = "long"
    quantity: float = 1
    leverage: float = Field(default=1, ge=1, le=1000)
    product_data: Dict[str, Any] = Field(default_factory=dict)


class BrokerPaperOrderRequest(BaseModel):
    client_order_id: str = Field(min_length=8, max_length=128)
    symbol: str = Field(min_length=1, max_length=32)
    asset_class: str = Field(default="equity", pattern="^(equity|etf)$")
    quantity: float = Field(gt=0)
    side: str = Field(pattern="^(buy|sell)$")
    order_type: str = Field(default="market", pattern="^(market|limit|stop|stop_limit)$")
    time_in_force: str = Field(default="day", pattern="^(day|gtc|opg|cls|ioc|fok)$")
    limit_price: Optional[float] = Field(default=None, gt=0)
    stop_price: Optional[float] = Field(default=None, gt=0)
    extended_hours: bool = False
    signal_decision_id: Optional[str] = None


class LeverageProductValidationRequest(BaseModel):
    product_data: Dict[str, Any] = Field(default_factory=dict)


class PaperAutoSelectionRequest(BaseModel):
    execute: bool = False
    max_trades: int = Field(default=3, ge=1, le=8)
    mode: str = Field(default="strict", pattern="^(strict|learn|aggressive_learning)$")


class PaperAutopilotSettingsRequest(BaseModel):
    mode: Optional[str] = Field(default=None, pattern="^(strict|learn|aggressive_learning)$")
    max_trades: Optional[int] = Field(default=None, ge=1, le=8)
    strict_min_score: Optional[float] = Field(default=None, ge=50, le=99)
    learning_min_score: Optional[float] = Field(default=None, ge=40, le=95)
    aggressive_min_score: Optional[float] = Field(default=None, ge=35, le=90)
    learning_risk_multiplier: Optional[float] = Field(default=None, ge=0.03, le=0.35)
    aggressive_risk_multiplier: Optional[float] = Field(default=None, ge=0.03, le=0.65)
    show_interesting_now: Optional[bool] = None


class PaperTradeCloseRequest(BaseModel):
    closed_price: Optional[float] = None
    notes: Optional[str] = None
    exit_reason: Optional[str] = None
    lessons_learned: Optional[str] = None


class PaperTradeJournalRequest(BaseModel):
    notes: Optional[str] = None
    exit_reason: Optional[str] = None
    lessons_learned: Optional[str] = None


class PaperLearningRuleActionRequest(BaseModel):
    action: str = Field(pattern="^(pause|reject|rollback|activate_paper|restart_shadow)$")
    reason: str = Field(min_length=8, max_length=1000)


class SendEdgeSetupTelegramRequest(BaseModel):
    ticker: Optional[str] = None
    force: bool = False
    portfolio_capital: Optional[float] = 50000.0
    risk_budget_pct: Optional[float] = 0.75


class OpenEdgePaperTradeRequest(BaseModel):
    ticker: str
    quantity: Optional[float] = None
    force: bool = False


def rating_to_string(rating: Rating) -> str:
    """Convert Rating enum to string."""
    mapping = {
        Rating.VERY_POSITIVE: "very_positive",
        Rating.POSITIVE: "positive",
        Rating.NEUTRAL: "neutral",
        Rating.NEGATIVE: "negative",
        Rating.VERY_NEGATIVE: "very_negative",
    }
    return mapping.get(rating, "neutral")


def convert_numpy_types(obj: Any) -> Any:
    """Recursively convert numpy types to Python native types."""
    if isinstance(obj, dict):
        return {k: convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        value = float(obj)
        return None if math.isnan(value) or math.isinf(value) else value
    elif isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else obj
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def _audit_sources(payload: Any, limit: int = 50) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def visit(value: Any) -> None:
        if len(found) >= limit:
            return
        if isinstance(value, dict):
            label = value.get("source_label") or value.get("source") or value.get("publisher")
            url = value.get("source_url") or value.get("link") or value.get("url")
            if label or url:
                key = (str(label or ""), str(url or ""))
                if key not in seen:
                    seen.add(key)
                    found.append({"label": label, "url": url})
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(payload)
    return found


def _audit_and_attach(
    payload: Dict[str, Any],
    *,
    event_type: str,
    subject: str,
    decision: str,
    data_as_of: Any,
    source_status: str,
    model_version: str,
    rule_version: str,
    user_action: str,
    audit_payload: Dict[str, Any],
) -> Dict[str, Any]:
    result = copy.deepcopy(payload)
    result["audit"] = get_portfolio_manager().record_decision_audit(
        event_type=event_type,
        subject=subject,
        decision=decision,
        data_as_of=str(data_as_of) if data_as_of not in (None, "") else None,
        source_status=source_status,
        sources=_audit_sources(audit_payload),
        model_version=model_version,
        rule_version=rule_version,
        user_action=user_action,
        payload=audit_payload,
    )
    return result


def _audit_morning_brief(payload: Dict[str, Any], user_action: str) -> Dict[str, Any]:
    quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
    audit_payload = {
        "headline": payload.get("headline"),
        "quality": quality,
        "top_news": payload.get("top_news") or [],
        "trade_setups": payload.get("trade_setups") or [],
        "decision_scope": payload.get("decision_scope"),
    }
    return _audit_and_attach(
        payload,
        event_type="recommendation_snapshot",
        subject="morning-brief",
        decision="research_brief",
        data_as_of=payload.get("generated_at") or payload.get("data_as_of"),
        source_status=str(quality.get("status") or quality.get("delivery_mode") or "unknown"),
        model_version="morning-brief.v2",
        rule_version="news-evidence-gate.v2",
        user_action=user_action,
        audit_payload=audit_payload,
    )


def serialize_analysis_result(result) -> Dict[str, Any]:
    """Serialize AnalysisResult to dict."""
    findings = []
    for f in result.findings:
        finding = dict(f)
        if "rating" in finding and isinstance(finding["rating"], Rating):
            finding["rating"] = rating_to_string(finding["rating"])
        findings.append(finding)
    
    return {
        "category": result.category,
        "findings": findings,
        "score": result.score,
        "summary": result.summary
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    persistence = get_persistence_status()
    persistence_ready = bool(persistence.get("persistence_ready"))
    compliance = get_compliance_status()
    ready = persistence_ready and bool(compliance.get("request_allowed"))
    return {
        "status": "ok" if ready else "degraded",
        "version": APP_VERSION,
        "release": get_release_identity(),
        "message": "Stock Analysis API is running" if ready else "API is running, but a release gate is not satisfied",
        "persistence": {
            "ready": persistence_ready,
            "volume_attached": bool(persistence.get("volume_attached")),
            "database_on_volume": bool(persistence.get("database_on_volume")),
        },
        "compliance": compliance,
    }


@app.get("/api/compliance/status")
async def compliance_status():
    return get_compliance_status()


@app.get("/api/auth/status")
async def auth_status(request: Request):
    profile = get_portfolio_manager().get_workspace_profile()
    guard = get_portfolio_manager().get_login_guard_state()
    return {
        "authenticated": is_valid_session(request.cookies.get(SESSION_COOKIE_NAME)),
        "configured": bool(get_app_password() and get_session_secret()),
        "profile": profile,
        "login_guard": guard,
    }


@app.post("/api/auth/login")
async def auth_login(req: LoginRequest, response: Response):
    password = get_app_password()
    secret = get_session_secret()
    if not password or not secret:
        raise HTTPException(status_code=503, detail="Security config missing on server.")
    guard = get_portfolio_manager().get_login_guard_state()
    locked_until = guard.get("locked_until")
    if locked_until:
        try:
            locked_dt = datetime.fromisoformat(locked_until)
            if locked_dt > datetime.now():
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many failed attempts. Locked until {locked_dt.strftime('%H:%M')}.",
                )
        except ValueError:
            get_portfolio_manager().reset_login_guard()
    if not hmac.compare_digest(req.password, password):
        guard = get_portfolio_manager().record_failed_login(
            get_login_max_attempts(),
            get_login_lockout_minutes(),
        )
        if guard.get("locked_until"):
            locked_dt = datetime.fromisoformat(guard["locked_until"])
            raise HTTPException(
                status_code=429,
                detail=f"Too many failed attempts. Locked until {locked_dt.strftime('%H:%M')}.",
            )
        remaining = max(0, get_login_max_attempts() - int(guard.get("failed_attempts", 0)))
        raise HTTPException(status_code=401, detail=f"Invalid code. {remaining} attempts left.")

    get_portfolio_manager().reset_login_guard()

    max_age = 60 * 60 * 24 * 7 if req.remember_device else 60 * 60 * 12
    response.set_cookie(
        SESSION_COOKIE_NAME,
        create_session_value(),
        httponly=True,
        samesite="lax",
        secure=use_secure_cookies(),
        max_age=max_age,
    )
    return {
        "status": "ok",
        "authenticated": True,
        "profile": get_portfolio_manager().get_workspace_profile(),
    }


@app.post("/api/auth/logout")
async def auth_logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME, samesite="lax")
    return {"status": "ok", "authenticated": False}


@app.get("/api/analyze/{ticker}")
async def analyze_stock(ticker: str) -> Dict[str, Any]:
    """
    Analyze a stock or an entire sector.
    """
    try:
        # Detect if searching for a sector
        sectors_map = {
            "tech": "Technology", "technology": "Technology",
            "ai": "Artificial Intelligence", "ki": "Artificial Intelligence", "artificial intelligence": "Artificial Intelligence",
            "semiconductors": "Semiconductors", "halbleiter": "Semiconductors",
            "energy": "Energy", "energie": "Energy",
            "financials": "Financials", "finanzen": "Financials",
            "healthcare": "Healthcare", "gesundheit": "Healthcare",
            "industrials": "Industrials", "industrie": "Industrials",
            "usa": "USA", "us": "USA", "amerika": "USA",
            "europe": "Europe", "europa": "Europe",
            "asia": "Asia", "asien": "Asia", "china": "Asia",
            "germany": "Germany", "deutschland": "Germany", "dax": "Germany"
        }
        
        target_sector = sectors_map.get(ticker.lower())
        
        if target_sector:
            # Sector-level aggregate analysis
            heatmap = await get_discovery_service().get_sentiment_heatmap()
            sector_data = next((s for s in heatmap if s['sector'] == target_sector), None)
            
            if not sector_data:
                raise HTTPException(status_code=404, detail=f"Sector data for {target_sector} not found.")
            
            # Aggregate analysis logic
            avg_change = sum(s['change_1w'] for s in sector_data['hot_stocks']) / len(sector_data['hot_stocks'])
            
            return {
                "is_sector": True,
                "decision_scope": research_scope(),
                "sector_name": target_sector,
                "status": sector_data['status'],
                "strength": sector_data['strength'],
                "avg_change_1w": avg_change,
                "top_stocks": sector_data['hot_stocks'],
                "verdict": f"Der {target_sector}-Sektor zeigt momentan eine {sector_data['status'].lower()}e Tendenz mit einer durchschnittlichen Wochenperformance von {avg_change:+.2f}%."
            }

        # Check for company names or 'Name (TICKER)' format
        resolved_ticker = _normalize_ticker_input(ticker)

        # If input contains brackets like 'Pfizer Inc. (PFE)', extract the ticker
        if "(" in ticker and ")" in ticker:
            match = re.search(r'\(([A-Z0-9.\-^=]+)\)', ticker.upper())
            if match:
                resolved_ticker = match.group(1)
                print(f"Extracted ticker '{resolved_ticker}' from '{ticker}'")
        else:
            # Always try to resolve via search for inputs that look like
            # company names (contains space, too long, or lowercase letters)
            looks_like_name = (
                " " in ticker
                or len(ticker) > 5
                or not ticker.replace("-", "").replace(".", "").replace("^", "").replace("=", "").isalnum()
                or ticker != ticker.upper()  # has lowercase = probably a name
            )
            if looks_like_name:
                try:
                    suggestions = await _resolve_search_results(ticker, limit=3)
                    if suggestions:
                        resolved_ticker = suggestions[0]['ticker']
                        print(f"Resolved '{ticker}' -> '{resolved_ticker}'")
                except Exception:
                    pass

        # Original stock fetch data
        fetcher = DataFetcher(resolved_ticker)
        data = fetcher.get_all_data()

        price_data = data.get("price_data", {}) or {}
        degraded_price_source = False

        # Do not fail hard on transient provider errors: degrade to fast snapshot pricing first.
        if "error" in price_data:
            fast_price_data = fetcher.get_price_data_fast()
            if "error" not in (fast_price_data or {}):
                data["price_data"] = fast_price_data
                degraded_price_source = True
            else:
                info = fetcher.info or {}
                current_price = info.get("currentPrice") or info.get("regularMarketPrice")
                fallback_price_data = {
                    "current_price": current_price,
                    "currency": info.get("currency", "USD"),
                    "change_1w": None,
                    "change_1m": None,
                    "change_6m": None,
                    "change_1y": None,
                    "high_52w": info.get("fiftyTwoWeekHigh"),
                    "low_52w": info.get("fiftyTwoWeekLow"),
                    "from_52w_high": None,
                    "from_52w_low": None,
                }
                fallback_analysis = {
                    "technical": {
                        "category": "Technische Analyse",
                        "score": 0.0,
                        "summary": "Live-Marktdaten reichen aktuell nicht aus. Bitte die vollständige Analyse erneut laden.",
                        "findings": [
                            {"metric": "Datenstatus", "value": "Signal unzureichend", "rating": "neutral"}
                        ],
                    },
                    "fundamental": {
                        "category": "Fundamentalanalyse",
                        "score": 0.0,
                        "summary": "Die Live-Kursversorgung ist vorübergehend eingeschränkt.",
                        "findings": [
                            {"metric": "Datenabdeckung", "value": "Teilweise", "rating": "neutral"}
                        ],
                    },
                    "sentiment": {
                        "category": "Sentimentanalyse",
                        "score": 0.0,
                        "summary": "Der Signal-Feed ist momentan nicht verfügbar.",
                        "findings": [
                            {"metric": "Belastbarkeit", "value": "Niedrig", "rating": "neutral"}
                        ],
                    },
                }
                return convert_numpy_types({
                    "ticker": resolved_ticker,
                    "company_name": info.get("longName", resolved_ticker),
                    "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "price_data": fallback_price_data,
                    "data_quality": {
                        "price_source": "unavailable_fallback",
                        "degraded": True,
                        "insufficient_signal": True,
                    },
                    "volatility": {},
                    "fundamentals": {},
                    "analyst_data": {},
                    "short_interest": {},
                    "news": [],
                    "comparison": {},
                    "earnings_history": [],
                    "guidance_signal": {},
                    "analysis": fallback_analysis,
                    "etf_analysis": None,
                    "recommendation": {
                        "action": "HOLD",
                        "reason": "Das Live-Marktsignal reicht nicht aus. Bitte die Analyse in Kürze erneut laden.",
                    },
                    "valuation": Valuation.FAIRLY_VALUED.value,
                    "total_score": 0,
                    "verdict": "Die Signalqualität reicht aktuell nicht aus. Bitte die vollständige Analyse erneut laden.",
                })
        
        # Analyze
        analyzer = StockAnalyzer(data)
        result = analyzer.generate_recommendation()
        
        # Serialize analyses
        analyses = {}
        for key, analysis in result.get("analyses", {}).items():
            analyses[key] = serialize_analysis_result(analysis)
        
        analysis_payload = {
            "ticker": data.get("ticker"),
            "decision_scope": research_scope(),
            "company_name": data.get("company_name"),
            "fetch_time": data.get("fetch_time"),
            "price_data": data.get("price_data"),
            "data_quality": {
                "price_source": "fast_snapshot" if degraded_price_source else "full",
                "degraded": degraded_price_source,
            },
            "volatility": data.get("volatility"),
            "fundamentals": data.get("fundamentals"),
            "analyst_data": data.get("analyst_data"),
            "short_interest": data.get("short_interest"),
            "news": data.get("news", []),
            "comparison": data.get("comparison"),
            "earnings_history": data.get("earnings_history", []),
            "guidance_signal": data.get("guidance_signal", {}),
            "business_quality": _build_business_quality_checks(data),
            "analysis": analyses,
            "etf_analysis": analyzer.analyze_etf() if data.get("fundamentals", {}).get("quote_type") == "ETF" else None,
            "recommendation": result.get("recommendation"),
            "valuation": result.get("valuation", Valuation.FAIRLY_VALUED).value,
            "total_score": result.get("total_score", 0),
            "verdict": analyzer.get_one_sentence_verdict()
        }
        audited_payload = _audit_and_attach(
            analysis_payload,
            event_type="recommendation_snapshot",
            subject=str(data.get("ticker") or resolved_ticker),
            decision=str((result.get("recommendation") or {}).get("action") or "HOLD"),
            data_as_of=data.get("fetch_time"),
            source_status=str(analysis_payload["data_quality"].get("price_source") or "unknown"),
            model_version="stock-analyzer.v1",
            rule_version="analysis-recommendation.v1",
            user_action="analysis_requested",
            audit_payload={
                "ticker": data.get("ticker"),
                "recommendation": result.get("recommendation"),
                "total_score": result.get("total_score", 0),
                "valuation": analysis_payload["valuation"],
                "verdict": analysis_payload["verdict"],
                "fetch_time": data.get("fetch_time"),
                "data_quality": analysis_payload["data_quality"],
                "news": data.get("news", []),
                "decision_scope": analysis_payload["decision_scope"],
            },
        )
        return convert_numpy_types(audited_payload)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )


@app.get("/api/analysis/basic")
async def get_basic_analysis(ticker: str):
    """Get basic metadata for comparison (TER, performance, etc)."""
    try:
        from src.data_fetcher import DataFetcher
        from src.analyzer import StockAnalyzer
        fetcher = DataFetcher(ticker.upper())
        data = fetcher.get_all_data()
        analyzer = StockAnalyzer(data)
        
        return convert_numpy_types({
            "ticker": ticker.upper(),
            "price_data": data.get("price_data"),
            "etf_analysis": analyzer.analyze_etf() if data.get("fundamentals", {}).get("quote_type") == "ETF" else None
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/history/{ticker}")
async def get_history(ticker: str, period: str = "1mo", interval: str = "1d") -> Dict[str, Any]:
    """
    Get historical price data for a ticker.
    Runs the blocking history call in a thread executor with an 8-second timeout
    so it never hangs the event loop indefinitely.
    """
    normalized_ticker = ticker.upper().strip()
    # Versioned keys exclude older cross-period and synthetic snapshot entries.
    cache_key = f"history:v2:{normalized_ticker}:{period}:{interval}"
    last_good_key = f"history:v2:lastgood:{normalized_ticker}:{period}:{interval}"
    cached = _cache_get(cache_key, int(os.getenv("HISTORY_CACHE_TTL_SECONDS", "180")))
    if cached is not None:
        return convert_numpy_types(cached)

    attempts: List[tuple[str, str]] = [
        (period, interval),
    ]
    seen_attempts = set()
    last_error: Optional[Exception] = None

    for try_period, try_interval in attempts:
        key = (try_period, try_interval)
        if key in seen_attempts:
            continue
        seen_attempts.add(key)

        def _fetch(fetch_period: str = try_period, fetch_interval: str = try_interval):
            fetcher = DataFetcher(normalized_ticker)
            return fetcher.get_history(period=fetch_period, interval=fetch_interval)

        try:
            history = await asyncio.wait_for(
                asyncio.get_running_loop().run_in_executor(_HISTORY_EXECUTOR, _fetch),
                timeout=8.0,
            )
            if history:
                mode = "live" if (try_period, try_interval) == (period, interval) else "fallback"
                payload = {
                        "items": history,
                        "meta": {
                            "symbol": normalized_ticker,
                            "mode": mode,
                            "stale": mode != "live",
                            "source": "yfinance",
                            "period": try_period,
                            "interval": try_interval,
                            "points": len(history),
                            "requested_period": period,
                            "requested_interval": interval,
                        },
                    }
                _cache_set(last_good_key, payload)
                return convert_numpy_types(_cache_set(cache_key, payload))
        except asyncio.TimeoutError as e:
            last_error = e
            continue
        except Exception as e:
            last_error = e
            continue

    stale = _cache_get_stale(
        last_good_key,
        _safe_int_env("HISTORY_STALE_CACHE_TTL_SECONDS", 86400, minimum=300),
    )
    if stale is not None:
        try:
            stale = copy.deepcopy(stale)
            meta = stale.setdefault("meta", {})
            meta["mode"] = "stale"
            meta["stale"] = True
            meta.setdefault("source", "cached_history")
            meta["fallback_reason"] = "provider_unavailable_using_last_good_history"
        except Exception:
            pass
        return convert_numpy_types(stale)

    unavailable_reason = (
        "provider_timeout"
        if isinstance(last_error, asyncio.TimeoutError)
        else "no_history_available"
    )
    payload = {
        "items": [],
        "meta": {
            "symbol": normalized_ticker,
            "mode": "unavailable",
            "stale": True,
            "source": "history_service",
            "period": period,
            "interval": interval,
            "points": 0,
            "requested_period": period,
            "requested_interval": interval,
            "fallback_reason": unavailable_reason,
            "error": "Kursverlauf aktuell nicht verfuegbar. Retry oder anderen Zeitraum nutzen.",
        },
    }
    # Do not cache an outage: an explicit retry should contact the provider again.
    return convert_numpy_types(payload)


@app.get("/api/quick/{ticker}")
async def quick_lookup(ticker: str) -> Dict[str, Any]:
    """
    Quick lookup for basic stock info (for search suggestions).
    """
    try:
        fetcher = DataFetcher(ticker)
        info = fetcher.info
        price_data = fetcher.get_price_data()
        
        return convert_numpy_types({
            "ticker": ticker.upper(),
            "name": info.get("longName") or info.get("shortName") or ticker,
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "price": price_data.get("current_price") or info.get("currentPrice") or info.get("regularMarketPrice"),
            "currency": info.get("currency", "USD"),
            "change_1d": price_data.get("change_1w", 0) / 5 if price_data.get("change_1w") else 0,
            "change_1y": price_data.get("change_1y"),
            "market_cap": info.get("marketCap"),
        })
    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"Ticker not found: {ticker}"
        )


@app.get("/api/portfolios")
async def get_portfolios():
    portfolios = get_portfolio_manager().get_portfolios()
    return convert_numpy_types(portfolios)


@app.get("/api/integrations/scalable/status")
async def scalable_integration_status(check_session: bool = False):
    """Return redacted integration health; broker identity and tokens never leave the CLI."""
    service = get_scalable_integration_service()
    return await asyncio.to_thread(service.status, check_session=check_session)


@app.get("/api/integrations/scalable/snapshot")
async def scalable_integration_snapshot():
    """Return the last reconciled, normalized read-only broker snapshot."""
    return await asyncio.to_thread(get_scalable_integration_service().snapshot)


@app.get("/api/integrations/scalable/market-context")
async def scalable_market_context():
    """Return cached quotes, security news and hashed recent transactions."""
    return await asyncio.to_thread(get_scalable_integration_service().market_context_snapshot)


@app.post("/api/integrations/scalable/market-context/refresh")
async def refresh_scalable_market_context():
    """Refresh the optional read-only quote, news and transaction context."""
    return await _refresh_scalable_readonly_context()


@app.get("/api/integrations/scalable/transaction-feedback")
async def scalable_transaction_feedback():
    """Measure whether read-only broker transactions followed preceding audited signals."""
    return await asyncio.to_thread(get_scalable_integration_service().transaction_feedback)


@app.get("/api/integrations/scalable/decisions")
async def scalable_decisions(fresh: bool = False):
    """Return the last decision report or rebuild it without sending Telegram."""
    if fresh:
        return await _build_scalable_decision_report()
    raw = await asyncio.to_thread(
        get_portfolio_manager().get_app_setting,
        "scalable_decision_report_v1",
        "",
    )
    if raw:
        try:
            return json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    raise HTTPException(status_code=404, detail="Noch kein Scalable-Entscheidungsreport vorhanden.")


@app.post("/api/integrations/scalable/sync")
async def sync_scalable_portfolio():
    """Synchronize holdings, then best-effort read-only market and transaction context."""
    try:
        synced = await asyncio.to_thread(get_scalable_integration_service().sync)
        result = dict(synced)
        result["readonly_context"] = await _refresh_scalable_readonly_context()
        if os.getenv("SCALABLE_TELEGRAM_DECISIONS_ENABLED", "true").strip().lower() not in {
            "0", "false", "no", "off"
        }:
            try:
                decision_result = await _send_scalable_decision_report()
                result["decision_report"] = decision_result["report"]
                result["telegram_decisions"] = decision_result["telegram"]
            except Exception as exc:
                # The reconciled broker snapshot remains valid even when signal
                # enrichment or Telegram is temporarily unavailable.
                result["telegram_decisions"] = {
                    "status": "error",
                    "sent": 0,
                    "error_type": exc.__class__.__name__,
                }
        return result
    except ScalableIntegrationError as exc:
        status_code = 503 if exc.code in {
            "integration_disabled",
            "cli_not_installed",
            "cli_unavailable",
            "cli_timeout",
        } else 409
        if exc.code in {"no_session", "refresh_relogin_required", "device_locked"}:
            status_code = 401
        raise HTTPException(
            status_code=status_code,
            detail={"code": exc.code, "message": exc.public_message, "details": exc.details},
        )


@app.post("/api/integrations/scalable/decisions/send")
async def send_scalable_decisions(force: bool = False):
    """Rebuild and send the current read-only decision report; unchanged reports deduplicate."""
    try:
        return await _send_scalable_decision_report(force=force)
    except ScalableIntegrationError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": exc.public_message, "details": exc.details},
        )


@app.get("/api/portfolio/{p_id}/verdict")
async def get_portfolio_verdict(p_id: str):
    """Generate an AI verdict for the entire portfolio."""
    if get_scalable_integration_service().is_managed_portfolio(p_id):
        return {"verdict": None, "source": "scalable_cli_reconciled"}
    try:
        portfolios = get_portfolio_manager().get_portfolios()
        portfolio = next((p for p in portfolios if p['id'] == p_id), None)
        if not portfolio or not portfolio['holdings']:
            return {"verdict": "Füge Assets hinzu, um eine Portfolio-Analyse zu erhalten."}
            
        scores = []
        for h in portfolio['holdings']:
            # Quick score fetch
            fetcher = DataFetcher(h['ticker'])
            data = fetcher.get_all_data()
            analyzer = StockAnalyzer(data)
            res = analyzer.generate_recommendation()
            scores.append(res.get('total_score', 0))
            
        avg_score = sum(scores) / len(scores) if scores else 0
        
        if avg_score > 30:
            v = "Dieses Portfolio ist exzellent aufgestellt und zeigt eine starke fundamentale Basis mit hohem Wachstumspotenzial."
        elif avg_score > 10:
            v = "Ein solides Portfolio mit ausgewogenem Risiko. Die meisten Positionen befinden sich in einem gesunden Trend."
        elif avg_score > -10:
            v = "Dieses Portfolio zeigt eine neutrale bis leicht volatile Tendenz. Einige Positionen benötigen Aufmerksamkeit."
        else:
            v = "Achtung: Das Portfolio weist signifikante Risiken auf. Eine fundamentale Umschichtung könnte ratsam sein."
            
        return {"verdict": v}
    except Exception as e:
        return {"verdict": "Portfolio-Analyse derzeit nicht möglich."}


@app.get("/api/portfolio/{p_id}/dividends")
async def get_portfolio_dividends(p_id: str):
    """Calculate expected dividend income."""
    try:
        portfolios = get_portfolio_manager().get_portfolios()
        portfolio = next((p for p in portfolios if p['id'] == p_id), None)
        if not portfolio or not portfolio['holdings']:
            return {"monthly": [0]*12, "yearly_total": 0}
            
        monthly_income = [0.0] * 12
        yearly_total = 0.0
        
        for h in portfolio['holdings']:
            fetcher = DataFetcher(h['ticker'])
            div = fetcher.get_dividends()
            rate = div.get("dividend_rate")
            
            if rate:
                income = rate * h['shares']
                yearly_total += income
                # Distribute roughly (YFinance doesn't give precise future dates easily, 
                # so we estimate quarterly if common or monthly)
                # For demo, we spread it across standard payout months
                start_month = 0 if "Dividends" not in str(h['ticker']) else 1
                for i in range(start_month, 12, 3):
                    monthly_income[i] += income / 4
                    
        return {
            "monthly": monthly_income,
            "yearly_total": yearly_total,
            "yield_on_cost": (yearly_total / sum(h.get('buyPrice', 0) * h['shares'] for h in portfolio['holdings']) * 100) if any(h.get('buyPrice') for h in portfolio['holdings']) else 0
        }
    except Exception as e:
        print(f"Error calculating dividends: {e}")
        return {
            "monthly": [0]*12, 
            "yearly_total": 0, 
            "yield_on_cost": 0,
            "error": str(e)
        }


@app.get("/api/portfolio/{p_id}/correlation")
async def get_portfolio_correlation(p_id: str):
    """Calculate correlation matrix between holdings."""
    import pandas as pd
    try:
        portfolios = get_portfolio_manager().get_portfolios()
        portfolio = next((p for p in portfolios if p['id'] == p_id), None)
        if not portfolio or len(portfolio['holdings']) < 2:
            return {"matrix": []}
            
        data = {}
        for h in portfolio['holdings']:
            f = DataFetcher(h['ticker'])
            hist = f.get_history(period="1y", interval="1d")
            data[h['ticker']] = [e['price'] for e in hist]
            
        # Ensure equal lengths
        min_len = min(len(v) for v in data.values())
        df = pd.DataFrame({k: v[:min_len] for k, v in data.items()})
        corr = df.pct_change().corr()
        
        return {
            "labels": list(corr.columns),
            "values": corr.values.tolist()
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/discovery/dividends")
async def get_dividend_stocks():
    return await get_discovery_service().get_dividend_aristocrats()


@app.get("/api/search")
async def search_ticker(q: str):
    """Search for tickers."""
    try:
        return await _resolve_search_results(q, limit=6)
    except Exception as exc:
        print(f"Search lookup fallback for {q!r}: {exc}")
        return convert_numpy_types(_fallback_search_results(q))


@app.get("/api/search/resolve")
async def resolve_search_query(q: str):
    """Resolve a natural-language asset query to the best stock/ETF/crypto ticker."""
    try:
        return convert_numpy_types(await _resolve_asset_query(q, limit=6))
    except Exception as exc:
        print(f"Search resolve fallback for {q!r}: {exc}")
        fallback = _fallback_search_results(q)
        best = fallback[0] if fallback else None
        normalized = _normalize_ticker_input(q)
        return convert_numpy_types({
            "query": (q or "").strip(),
            "normalized": normalized,
            "ticker": str((best or {}).get("ticker") or normalized).upper(),
            "name": (best or {}).get("name") or normalized,
            "exchange": (best or {}).get("exchange"),
            "type": (best or {}).get("type") or "direct",
            "source": (best or {}).get("source") or "normalizer_fallback",
            "confidence": "medium" if best else "low",
            "score": 82 if best else 0,
            "alternatives": [],
            "degraded": True,
        })


@app.get("/api/discovery/moonshots")
async def get_moonshot_stocks():
    return await get_discovery_service().get_moonshots()


@app.get("/api/discovery/sentiment-heatmap")
async def get_sentiment_heatmap():
    try:
        return convert_numpy_types(await get_discovery_service().get_sentiment_heatmap())
    except Exception:
        return convert_numpy_types(get_discovery_service()._sentiment_heatmap_fallbacks())


@app.get("/api/search/suggestions")
async def get_search_suggestions(q: str = None):
    """Fast search suggestions. Query mode may use live lookup; default mode must not block UI."""
    if q and len(q) > 1:
        try:
            results = await _resolve_search_results(q, limit=6)
        except Exception as exc:
            # A provider outage must not turn an Analyzer search into a 5xx.
            print(f"Search suggestion lookup fallback for {q!r}: {exc}")
            results = _fallback_search_results(q)
        return {
            "Matches": [f"{r['name']} ({r['ticker']})" for r in results[:5]],
            "Ticker": [r['ticker'] for r in results[:5]],
            "Types": [_search_asset_type_label(r) for r in results[:5]],
        }

    try:
        return convert_numpy_types(await _build_dynamic_search_suggestions())
    except Exception as exc:
        # Search must stay usable when the brief or a discovery provider is slow.
        # Keep the response shape stable and let the next request retry dynamic data.
        print(f"Dynamic search suggestions fallback: {exc}")
        return convert_numpy_types({
            **DEFAULT_SEARCH_SUGGESTIONS,
            "meta": {"source": "curated_fallback", "degraded": True},
        })


@app.post("/api/oracle/chat")
async def oracle_chat(req: OracleRequest):
    """Deterministic Broker desk response with market and portfolio context."""
    message = (req.message or "").strip()
    msg = message.lower()
    ticker_raw = (req.context_ticker or "").strip()
    tickers = [
        item.strip().upper()
        for item in ticker_raw.split(",")
        if item and item.strip()
    ][:3]
    if not tickers and req.context_symbols:
        tickers = [
            str(item).strip().upper()
            for item in req.context_symbols
            if str(item).strip()
        ][:3]

    ticker_context: List[Dict[str, Any]] = []
    for symbol in tickers:
        try:
            fetcher = DataFetcher(symbol)
            data = fetcher.get_all_data()
            analyzer = StockAnalyzer(data)
            recommendation = analyzer.generate_recommendation()
            price_data = data.get("price_data", {})
            ticker_context.append(
                {
                    "symbol": symbol,
                    "price": price_data.get("current_price"),
                    "change_1w": price_data.get("change_1w"),
                    "score": float(recommendation.get("total_score", 0)),
                    "verdict": analyzer.get_one_sentence_verdict(),
                    "fundamentals": data.get("fundamentals", {}) or {},
                    "analyst_data": data.get("analyst_data", {}) or {},
                    "earnings_history": data.get("earnings_history", []) or [],
                    "guidance_signal": data.get("guidance_signal", {}) or {},
                    "news": data.get("news", []) or [],
                    "short_interest": data.get("short_interest", {}) or {},
                }
            )
        except Exception:
            continue

    live_quotes = req.live_quotes or {}
    for item in ticker_context:
        quote = live_quotes.get(item["symbol"]) if isinstance(live_quotes, dict) else None
        if isinstance(quote, dict) and quote.get("price") is not None:
            item["price"] = quote.get("price")
        if isinstance(quote, dict) and quote.get("change_1w") is not None:
            item["change_1w"] = quote.get("change_1w")

    top_signal = None
    signal_items = []
    if isinstance(req.signal_score, dict):
        signal_items = req.signal_score.get("top_ideas", []) or []
    if signal_items:
        top_signal = signal_items[0]

    profile = req.portfolio_snapshot or {}
    portfolio_summary = profile.get("summary", {}) if isinstance(profile, dict) else {}
    holdings_count = int(portfolio_summary.get("num_holdings") or 0)
    total_value = float(portfolio_summary.get("total_value") or 0)
    gain_loss_pct = float(
        portfolio_summary.get("return_since_buy_pct")
        or portfolio_summary.get("gain_loss_pct")
        or 0
    )
    portfolio_holdings = profile.get("holdings", []) if isinstance(profile, dict) else []
    holding_names = [
        str(item.get("ticker") or "").upper()
        for item in portfolio_holdings
        if isinstance(item, dict) and item.get("ticker")
    ][:6]

    brief = req.morning_brief_summary or {}
    brief_decision_gate = brief.get("decision_gate") if isinstance(brief, dict) else {}
    brief_decision_allowed = not (
        isinstance(brief_decision_gate, dict)
        and brief_decision_gate.get("allowed") is False
    )
    macro_regime = brief.get("macro_regime") if isinstance(brief, dict) and brief_decision_allowed else None
    headline = brief.get("headline") if isinstance(brief, dict) and brief_decision_allowed else None
    opening_bias = brief.get("opening_bias") if isinstance(brief, dict) and brief_decision_allowed else None

    primary = ticker_context[0] if ticker_context else None
    score = float(primary.get("score", 0)) if primary else 0.0
    symbol = primary.get("symbol") if primary else "MARKET"
    week_change = float(primary.get("change_1w") or 0) if primary else 0.0
    price = primary.get("price") if primary else None
    primary_fundamentals = primary.get("fundamentals", {}) if primary else {}
    primary_analysts = primary.get("analyst_data", {}) if primary else {}
    primary_earnings = primary.get("earnings_history", []) if primary else []
    primary_guidance = primary.get("guidance_signal", {}) if primary else {}
    primary_news = primary.get("news", []) if primary else []
    primary_short = primary.get("short_interest", {}) if primary else {}

    def _safe_float(value: Any) -> Optional[float]:
        try:
            if value in (None, "", "N/A"):
                return None
            parsed = float(value)
            if not math.isfinite(parsed):
                return None
            return parsed
        except Exception:
            return None

    def _pick_number(source: Dict[str, Any], *keys: str) -> Optional[float]:
        for key in keys:
            value = _safe_float(source.get(key))
            if value is not None:
                return value
        return None

    def _format_pct(value: Optional[float]) -> str:
        if value is None:
            return "n/a"
        normalized = value * 100 if abs(value) <= 1 else value
        return f"{normalized:+.1f}%"

    def _format_compact_money(value: Optional[float]) -> str:
        if value is None:
            return "n/a"
        abs_value = abs(value)
        if abs_value >= 1_000_000_000_000:
            return f"${value / 1_000_000_000_000:.1f}T"
        if abs_value >= 1_000_000_000:
            return f"${value / 1_000_000_000:.1f}B"
        if abs_value >= 1_000_000:
            return f"${value / 1_000_000:.1f}M"
        return f"${value:,.0f}"

    revenue_growth = _pick_number(
        primary_fundamentals,
        "revenue_growth",
        "revenueGrowth",
        "quarterly_revenue_growth",
    )
    profit_margin = _pick_number(primary_fundamentals, "profit_margin", "profitMargins")
    gross_margin = _pick_number(primary_fundamentals, "gross_margin", "grossMargins")
    free_cashflow = _pick_number(
        primary_fundamentals,
        "free_cashflow",
        "freeCashflow",
        "free_cash_flow",
    )
    market_cap = _pick_number(primary_fundamentals, "market_cap", "marketCap")
    fcf_yield = (free_cashflow / market_cap * 100) if free_cashflow and market_cap else None
    pe_ratio = _pick_number(primary_fundamentals, "pe_ratio", "trailingPE", "trailing_pe")
    forward_pe = _pick_number(primary_fundamentals, "forward_pe", "forwardPE")
    debt_to_equity = _pick_number(primary_fundamentals, "debt_to_equity", "debtToEquity")
    target_mean = _pick_number(
        primary_analysts,
        "target_mean_price",
        "targetMeanPrice",
        "mean_target_price",
    )
    analyst_upside = None
    if target_mean is not None and price:
        current_price = _safe_float(price)
        if current_price:
            analyst_upside = (target_mean / current_price - 1) * 100
    latest_earning = primary_earnings[0] if isinstance(primary_earnings, list) and primary_earnings else {}
    latest_surprise = (
        _pick_number(latest_earning, "surprise_percent", "eps_surprise_percent", "surprise")
        if isinstance(latest_earning, dict)
        else None
    )
    latest_earning_label = ""
    if isinstance(latest_earning, dict):
        latest_earning_label = str(
            latest_earning.get("date")
            or latest_earning.get("period")
            or latest_earning.get("quarter")
            or ""
        )
    guidance_label = ""
    guidance_score = None
    if isinstance(primary_guidance, dict):
        guidance_label = str(
            primary_guidance.get("label")
            or primary_guidance.get("tone")
            or primary_guidance.get("summary")
            or ""
        )
        guidance_score = _pick_number(primary_guidance, "score", "sentiment_score")
    short_percent = (
        _pick_number(primary_short, "short_percent_float", "shortPercentOfFloat", "short_float")
        if isinstance(primary_short, dict)
        else None
    )

    if primary:
        if score >= 30 and week_change >= 0:
            thesis = f"{symbol} bleibt konstruktiv, solange Momentum und Score stabil bleiben."
        elif score <= -20 or week_change < -3:
            thesis = f"{symbol} zeigt fragiles Profil; Kapitalerhalt ist aktuell wichtiger als Aggression."
        else:
            thesis = f"{symbol} ist aktuell neutral, Setup nur bei klarem Trigger handeln."
    else:
        active_area = (req.active_tab or "app").title()
        thesis = f"Im Bereich {active_area} liegt der Fokus auf Regime, Risiko und bestaetigten Triggern."

    if "short" in msg or "sell" in msg or "verkauf" in msg:
        thesis = f"{thesis} Short-Ideen nur mit bestätigtem Bruch und engem Risikorahmen."
    elif "long" in msg or "buy" in msg or "kauf" in msg:
        thesis = f"{thesis} Long nur mit Folgekäufen und sauberem Volumen."

    wants_app_guide = any(
        token in msg
        for token in [
            "fuehre",
            "fuehr",
            "durch",
            "anklicken",
            "klicken",
            "bedienen",
            "seite",
            "app",
            "wo soll",
            "was jetzt",
            "naechst",
            "weiter",
            "machen",
            "hilfe",
            "help",
        ]
    )

    risk_line_parts: List[str] = []
    if not brief_decision_allowed:
        risk_line_parts.append("Morning Brief gesperrt: veraltete oder eingeschraenkte Daten nicht fuer Entscheidungen verwenden")
    if macro_regime:
        risk_line_parts.append(f"Regime: {macro_regime}")
    if req.active_tab:
        risk_line_parts.append(f"App-Kontext: {req.active_tab}")
    if holdings_count > 0:
        risk_line_parts.append(
            f"Portfolio {holdings_count} Positionen, P&L {gain_loss_pct:+.2f}% auf {total_value:,.0f} Gesamtwert"
        )
    if top_signal:
        risk_line_parts.append(
            f"Top-Signal: {top_signal.get('label', 'Idea')} (Score {float(top_signal.get('total_score') or 0):.0f})"
        )
    if primary:
        if revenue_growth is not None and revenue_growth < 0:
            risk_line_parts.append(f"Umsatz schrumpft ({_format_pct(revenue_growth)})")
        if profit_margin is not None and profit_margin < 0:
            risk_line_parts.append(f"Negative Profit-Marge ({_format_pct(profit_margin)})")
        if pe_ratio is not None and pe_ratio > 45 and revenue_growth is not None and revenue_growth < 0.15:
            risk_line_parts.append(f"Hohe Bewertung ohne starkes Wachstum (P/E {pe_ratio:.1f})")
        if latest_surprise is not None and latest_surprise < -2:
            risk_line_parts.append(f"Letzter Earnings-Surprise negativ ({latest_surprise:+.1f}%)")
        if short_percent is not None and short_percent > 12:
            risk_line_parts.append(f"Erhoehte Short-Quote ({_format_pct(short_percent)})")
    if not risk_line_parts:
        risk_line_parts.append("Keine erweiterten Risiko-Metadaten, Standard-Risikobudget nutzen.")

    if primary and price:
        up_trigger = float(price) * 1.01
        down_trigger = float(price) * 0.99
        trigger_line = (
            f"Long-Trigger über {up_trigger:.2f}, defensiv unter {down_trigger:.2f}. "
            f"Nur handeln, wenn der Move bestätigt wird."
        )
        invalidation_line = (
            f"Invalidierung bei Rücklauf unter {down_trigger:.2f} oder wenn Newsflow gegen das Setup dreht."
        )
        levels = [
            f"{symbol} Spot: {float(price):.2f}",
            f"Breakout-Zone: {up_trigger:.2f}",
            f"Risk-Cut-Zone: {down_trigger:.2f}",
        ]
    else:
        trigger_line = "Trigger über frische Tageshochs mit Volumenbestätigung oder klare Makro-Breaks."
        invalidation_line = "Invalidierung bei fehlender Anschlussdynamik und gegenteiligen Headlines."
        levels = ["SPY / QQQ Richtung", "VIX-Regime", "US10Y / DXY Reaktion"]

    if headline:
        levels.append(f"Brief-Headline: {headline}")
    if opening_bias:
        levels.append(f"Opening Bias: {opening_bias}")
    if target_mean is not None:
        analyst_text = f"Analysten-Ziel: {target_mean:.2f}"
        if analyst_upside is not None:
            analyst_text += f" ({analyst_upside:+.1f}% vs Spot)"
        levels.append(analyst_text)
    if latest_surprise is not None:
        suffix = f" ({latest_earning_label})" if latest_earning_label else ""
        levels.append(f"Letztes Earnings-Signal: {latest_surprise:+.1f}% Surprise{suffix}")
    if guidance_label:
        guidance_suffix = f", Score {guidance_score:+.1f}" if guidance_score is not None else ""
        levels.append(f"Guidance: {guidance_label}{guidance_suffix}")
    if isinstance(primary_news, list) and primary_news:
        top_news = primary_news[0]
        if isinstance(top_news, dict):
            title = str(top_news.get("title") or top_news.get("headline") or "").strip()
            source = str(top_news.get("source") or top_news.get("publisher") or "").strip()
            if title:
                levels.append(f"Top-News: {title[:120]}" + (f" ({source})" if source else ""))

    learning_context = req.learning_summary
    if not isinstance(learning_context, dict):
        try:
            learning_context = get_forecast_learning_service().build_dashboard()
        except Exception:
            learning_context = {}
    learning_summary = learning_context.get("summary", {}) if isinstance(learning_context, dict) else {}
    source_quality = learning_context.get("by_source", []) if isinstance(learning_context, dict) else []
    weak_sources = learning_context.get("weak_sources", []) if isinstance(learning_context, dict) else []
    weak_setup_types = learning_context.get("weak_setup_types", []) if isinstance(learning_context, dict) else []
    learning_lessons = learning_context.get("lessons", []) if isinstance(learning_context, dict) else []
    recent_forecasts = learning_context.get("recent_forecasts", []) if isinstance(learning_context, dict) else []
    current_setups = brief.get("trade_setups", []) if isinstance(brief, dict) else []
    current_learning_adjustments = brief.get("learning_adjustments", []) if isinstance(brief, dict) else []
    current_congress_watch = brief.get("congress_watch", []) if isinstance(brief, dict) else []
    current_earnings_calendar = brief.get("earnings_calendar", []) if isinstance(brief, dict) else []
    current_earnings_results = brief.get("earnings_results", []) if isinstance(brief, dict) else []
    current_market_movers = brief.get("market_movers", {}) if isinstance(brief, dict) else {}
    current_product_catalysts = brief.get("product_catalysts", []) if isinstance(brief, dict) else []
    current_event_pings = brief.get("event_pings", []) if isinstance(brief, dict) else []
    current_watchlist_impact = brief.get("watchlist_impact", []) if isinstance(brief, dict) else []
    current_prediction_signals = brief.get("prediction_signals", []) if isinstance(brief, dict) else []
    prediction_status = brief.get("prediction_markets", {}) if isinstance(brief, dict) else {}
    current_quality = brief.get("quality", {}) if isinstance(brief, dict) and isinstance(brief.get("quality"), dict) else {}
    current_source_states = current_quality.get("sources", {}) if isinstance(current_quality.get("sources"), dict) else {}
    current_deferred_layers = current_quality.get("deferred", []) if isinstance(current_quality.get("deferred"), list) else []
    current_missing_checks = current_quality.get("missing", []) if isinstance(current_quality.get("missing"), list) else []

    def _item_symbol(item: Dict[str, Any]) -> str:
        return str(item.get("symbol") or item.get("ticker") or item.get("value") or "").upper().strip()

    def _item_change(item: Dict[str, Any]) -> str:
        raw = item.get("change") if item.get("change") is not None else item.get("change_1w")
        value = _safe_float(raw)
        if value is None:
            return "move n/a"
        return f"{value:+.2f}%"

    gainers = current_market_movers.get("gainers", []) if isinstance(current_market_movers, dict) else []
    losers = current_market_movers.get("losers", []) if isinstance(current_market_movers, dict) else []
    worst_holding = None
    best_holding = None
    if isinstance(portfolio_holdings, list) and portfolio_holdings:
        sortable_holdings = [
            item
            for item in portfolio_holdings
            if isinstance(item, dict) and _safe_float(item.get("return_since_buy_pct")) is not None
        ]
        if sortable_holdings:
            worst_holding = min(sortable_holdings, key=lambda item: float(item.get("return_since_buy_pct") or 0))
            best_holding = max(sortable_holdings, key=lambda item: float(item.get("return_since_buy_pct") or 0))

    explain_lines = []
    if primary:
        explain_lines.append(
            f"{symbol} wird aus Score, Wochenmomentum, Live-Preis und aktuellem Marktregime eingeordnet."
        )
        dossier_parts = []
        if revenue_growth is not None:
            dossier_parts.append(f"Umsatzwachstum {_format_pct(revenue_growth)}")
        if profit_margin is not None:
            dossier_parts.append(f"Profit-Marge {_format_pct(profit_margin)}")
        elif gross_margin is not None:
            dossier_parts.append(f"Bruttomarge {_format_pct(gross_margin)}")
        if fcf_yield is not None:
            dossier_parts.append(f"FCF-Yield {fcf_yield:+.1f}%")
        if pe_ratio is not None:
            dossier_parts.append(f"P/E {pe_ratio:.1f}")
        if forward_pe is not None:
            dossier_parts.append(f"Forward P/E {forward_pe:.1f}")
        if analyst_upside is not None:
            dossier_parts.append(f"Analysten-Upside {analyst_upside:+.1f}%")
        if dossier_parts:
            explain_lines.append("Finanzprofil: " + ", ".join(dossier_parts) + ".")
    else:
        explain_lines.append(
            "Ohne manuell gewaehlten Einzelticker nutze ich aktive Seite, Watchlist, Portfolio und Signalboard als Kontext."
        )
    if holdings_count > 0:
        explain_lines.append(
            f"Dein Portfolio-Kontext ist aktiv ({holdings_count} Positionen"
            + (f": {', '.join(holding_names)}" if holding_names else "")
            + ")."
        )
    if top_signal:
        explain_lines.append("Das Signalboard fliesst als Priorisierung ein, nicht als blinder Kaufbefehl.")
    if isinstance(brief, dict):
        explain_lines.append(
            "Aktive Daten im Briefing: "
            f"{len(current_setups)} Setups, {len(current_congress_watch)} Congress-Signale, "
            f"{len(current_event_pings)} Event-Pings, {len(current_earnings_calendar)} Earnings, "
            f"{len(current_product_catalysts)} Produkt-Katalysatoren."
        )
    if learning_summary.get("forecasts"):
        explain_lines.append(
            f"Learning Loop aktiv: {learning_summary.get('forecasts')} gespeicherte Setups, "
            f"{learning_summary.get('evaluated', 0)} Outcomes, Trefferquote {learning_summary.get('hit_rate', 0)}%."
        )
    if current_learning_adjustments:
        promoted = [item for item in current_learning_adjustments if float(item.get("score_delta") or 0) > 0]
        downgraded = [item for item in current_learning_adjustments if float(item.get("score_delta") or 0) < 0]
        if promoted:
            explain_lines.append(
                "Aktuelles Briefing hebt bewaehrte Muster an: "
                + ", ".join(f"{item.get('label')} ({item.get('score_delta'):+})" for item in promoted[:3])
                + "."
            )
        if downgraded:
            explain_lines.append(
                "Aktuelles Briefing stuft schwache Muster vorsichtiger ein: "
                + ", ".join(f"{item.get('label')} ({item.get('score_delta'):+})" for item in downgraded[:3])
                + "."
            )

    if wants_app_guide:
        area = (req.active_tab or "dashboard").lower()
        if area == "discovery":
            levels.append("Markets Guide: erst Top Movers fuer echte Staerke/Schwaeche pruefen, dann Market Explorer fuer Sektor/ETF-Kontext nutzen.")
            levels.append("Markets Guide: Karten nur ueber explizite Analyse-Buttons oeffnen; nicht jeder Klick ist ein Trade-Signal.")
            levels.append("Markets Guide: Winner/Loser mit Briefing, News und Volumen bestaetigen, bevor ein Ticker in Analyze geht.")
        elif area == "portfolio":
            levels.append("Portfolio Guide: zuerst Rendite seit Kauf, Positionsgroesse und Klumpenrisiko ansehen.")
            levels.append("Portfolio Guide: rote Positionen nicht automatisch verkaufen; Trigger, Earnings und Marktregime gegenpruefen.")
            levels.append("Portfolio Guide: bei hoher Konzentration Hedge- oder Reduce-Idee im Briefing suchen.")
        elif area == "analyze":
            levels.append("Analyze Guide: zuerst Kurslauf/History, dann Dossier-Finanzen, dann Trigger/Invalidierung lesen.")
            levels.append("Analyze Guide: wenn Price History nur Snapshot zeigt, Entscheidung vertagen oder Tageschart spaeter neu laden.")
            levels.append("Analyze Guide: Analystenziele und News sind Kontext, entscheidend ist die bestaetigte Kursreaktion.")
        else:
            levels.append("Dashboard Guide: Morning Brief zeigt Regime und Top Setups, Map zeigt Event-Pings, Trading Edge zeigt taktische Ideen.")
            levels.append("Dashboard Guide: zuerst Regime/Risk-off vs Mixed lesen, danach nur die Setups mit Trigger und Invalidierung verfolgen.")
            levels.append("Dashboard Guide: Health pruefen, wenn Briefings oder Telegram nicht rechtzeitig kamen.")

    active_area = (req.active_tab or "dashboard").lower()
    if active_area == "discovery":
        explain_lines.append(
            "Markets-Modus aktiv: ich priorisiere Gewinner/Verlierer, Sektorstaerke, Event-Pings und den expliziten Analyze-Klick."
        )
        if gainers:
            winner = gainers[0]
            if isinstance(winner, dict):
                levels.append(f"Markets Next Click: Top Winner {_item_symbol(winner)} ({_item_change(winner)}) zuerst nur analysieren, nicht blind kaufen.")
        if losers:
            loser = losers[0]
            if isinstance(loser, dict):
                levels.append(f"Markets Risk Check: Top Loser {_item_symbol(loser)} ({_item_change(loser)}) nur handeln, wenn News und Volumen passen.")
        if current_event_pings:
            levels.append("Markets Filter: Event-Pings vor Einzelaktie lesen, weil Makro/Policy die Moves uebersteuern kann.")
        else:
            levels.append("Markets Filter: keine starken Event-Pings; dann haben relative Staerke und Volumen mehr Gewicht.")
    elif active_area == "portfolio":
        explain_lines.append(
            "Portfolio-Modus aktiv: ich bewerte zuerst Rendite seit Kauf, Positionsgroesse, Klumpenrisiko und Briefing-Auswirkung."
        )
        if isinstance(worst_holding, dict):
            levels.append(
                f"Portfolio Risk: {_item_symbol(worst_holding)} ist der schwaechste Kauf-Return "
                f"({_format_pct(_safe_float(worst_holding.get('return_since_buy_pct')))})."
            )
        if isinstance(best_holding, dict):
            levels.append(
                f"Portfolio Strength: {_item_symbol(best_holding)} traegt am staerksten "
                f"({_format_pct(_safe_float(best_holding.get('return_since_buy_pct')))} seit Kauf)."
            )
        if current_watchlist_impact:
            levels.append("Portfolio Briefing: Watchlist Impact ist aktiv; betroffene Holdings zuerst pruefen.")
    elif active_area == "analyze":
        explain_lines.append(
            "Analyze-Modus aktiv: ich lese erst Kursverlauf/History-Status, dann Dossier, dann Trigger und Invalidierung."
        )
        if primary:
            levels.append(f"Analyze Reihenfolge: {symbol} Chart -> Finanzprofil -> News/Earnings -> Trigger -> Positionsgroesse.")
        if primary and latest_surprise is None and not guidance_label:
            levels.append("Analyze Datenluecke: keine belastbare Earnings/Guidance-Zusammenfassung im aktuellen Snapshot.")
    else:
        explain_lines.append(
            "Dashboard-Modus aktiv: ich verbinde Morning Brief, Map-Pings, Trading Edge, Portfolio und Learning zu einer Prioritaet."
        )
        if current_setups:
            setup = current_setups[0]
            if isinstance(setup, dict):
                levels.append(
                    f"Dashboard Top Setup: {str(setup.get('symbol') or setup.get('ticker') or '').upper()} - "
                    f"{str(setup.get('trigger') or setup.get('thesis') or '')[:110]}"
                )

    wants_dossier = any(
        token in msg
        for token in [
            "dossier",
            "finanz",
            "umsatz",
            "marge",
            "cashflow",
            "bewertung",
            "earnings",
            "guidance",
            "zahlen",
            "erklaer",
            "erklär",
        ]
    )
    dossier_lines: List[str] = []
    if primary and wants_dossier:
        dossier_lines.append(
            f"Quality: Wachstum {_format_pct(revenue_growth)}, Profit-Marge {_format_pct(profit_margin)}, "
            f"FCF-Yield {fcf_yield:+.1f}%" if fcf_yield is not None else
            f"Quality: Wachstum {_format_pct(revenue_growth)}, Profit-Marge {_format_pct(profit_margin)}, FCF-Yield n/a"
        )
        valuation_bits = []
        if pe_ratio is not None:
            valuation_bits.append(f"P/E {pe_ratio:.1f}")
        if forward_pe is not None:
            valuation_bits.append(f"Forward P/E {forward_pe:.1f}")
        if analyst_upside is not None:
            valuation_bits.append(f"Analysten-Upside {analyst_upside:+.1f}%")
        if market_cap is not None:
            valuation_bits.append(f"Market Cap {_format_compact_money(market_cap)}")
        dossier_lines.append("Bewertung: " + (", ".join(valuation_bits) if valuation_bits else "keine belastbaren Bewertungsdaten"))
        if latest_surprise is not None or guidance_label:
            dossier_lines.append(
                "Zahlen/Guidance: "
                + (f"Surprise {latest_surprise:+.1f}% " if latest_surprise is not None else "")
                + (f"Guidance {guidance_label}" if guidance_label else "")
            )
        balance_bits = []
        if debt_to_equity is not None:
            balance_bits.append(f"Debt/Equity {debt_to_equity:.1f}")
        if short_percent is not None:
            balance_bits.append(f"Short Float {_format_pct(short_percent)}")
        dossier_lines.append("Bilanz/Risiko: " + (", ".join(balance_bits) if balance_bits else "keine roten Zusatzdaten im aktuellen Snapshot"))
        dossier_lines.append(
            "Interpretation: stark wird das Setup erst, wenn Finanzprofil, Kurs-Trigger und Newsflow gleichzeitig in dieselbe Richtung zeigen."
        )

    if any(token in msg for token in ["falsch", "fehler", "treffer", "quelle", "learning", "gelernt"]):
        best_source = source_quality[0] if source_quality else None
        weak_source = weak_sources[0] if weak_sources else None
        weak_setup = weak_setup_types[0] if weak_setup_types else None
        latest = recent_forecasts[0] if recent_forecasts else None
        if best_source:
            levels.append(
                f"Beste Quelle bisher: {best_source.get('label')} ({best_source.get('hit_rate')}% hit-rate)"
            )
        if weak_source:
            levels.append(
                f"Schwaechste Quelle zuletzt: {weak_source.get('label')} ({weak_source.get('hit_rate')}% hit-rate)"
            )
        if weak_setup:
            levels.append(
                f"Setup-Typ mit strengeren Triggern: {weak_setup.get('label')} ({weak_setup.get('hit_rate')}% hit-rate)"
            )
        if latest:
            levels.append(
                f"Letztes gespeichertes Setup: {latest.get('symbol')} / {latest.get('direction')}"
            )
        for lesson in learning_lessons[:3]:
            if isinstance(lesson, dict) and lesson.get("message"):
                levels.append(f"Learning Lesson: {lesson.get('message')}")

    if any(token in msg for token in ["warum", "setup", "ranking", "oben", "priorisiert", "briefing"]):
        if not current_setups:
            levels.append("Briefing-Luecke: keine belastbaren Trade Setups; Ursache ist meist fehlender Trigger, schwache Datenlage oder Upstream-Timeout.")
        for setup in current_setups[:3]:
            if not isinstance(setup, dict):
                continue
            adjustment = setup.get("learning_adjustment") or {}
            delta = float(adjustment.get("score_delta") or 0)
            if delta:
                levels.append(
                    f"{setup.get('symbol')} Ranking-Bias {delta:+.1f}: {adjustment.get('reason')}"
                )
        if current_congress_watch:
            symbols = [
                str(item.get("symbol") or item.get("ticker") or "").upper()
                for item in current_congress_watch
                if isinstance(item, dict) and (item.get("symbol") or item.get("ticker"))
            ][:4]
            if symbols:
                levels.append(f"Congress Watch aktiv fuer: {', '.join(symbols)}")
        elif any(token in msg for token in ["congress", "politiker", "senat", "house"]):
            levels.append("Congress Watch: aktuell keine hoch priorisierte PTR-Cluster-Lage im Briefing.")

    if any(token in msg for token in ["earning", "earnings", "zahlen", "quartal", "beat", "miss", "guidance"]):
        if not current_earnings_results and not current_earnings_calendar:
            levels.append("Earnings: keine nahen oder ausgewerteten Zahlen im aktuellen Briefing-Kontext.")
        for item in current_earnings_results[:3]:
            if isinstance(item, dict):
                ticker = str(item.get("symbol") or item.get("ticker") or "").upper()
                tone = item.get("tone") or item.get("status") or "reported"
                detail = item.get("summary") or item.get("headline") or item.get("reaction") or ""
                levels.append(f"Earnings Result: {ticker} {tone} - {str(detail)[:110]}")
        for item in current_earnings_calendar[:4]:
            if isinstance(item, dict):
                ticker = str(item.get("symbol") or item.get("ticker") or "").upper()
                when = item.get("date") or item.get("report_date") or item.get("time") or "soon"
                name = item.get("name") or item.get("company") or ticker
                levels.append(f"Earnings Watch: {ticker} {name} - {when}")

    if any(token in msg for token in ["mover", "winner", "loser", "gewinner", "verlierer", "market"]):
        if not gainers and not losers:
            levels.append("Market Movers: Feed aktuell leer oder verzoegert; zuerst Markets-Tab neu laden und dann Gewinner/Verlierer bestaetigen.")
        for item in (gainers or [])[:3]:
            if isinstance(item, dict):
                levels.append(
                    f"Top Winner: {_item_symbol(item)} {_item_change(item)}"
                )
        for item in (losers or [])[:3]:
            if isinstance(item, dict):
                levels.append(
                    f"Top Loser: {_item_symbol(item)} {_item_change(item)}"
                )

    if any(token in msg for token in ["produkt", "iphone", "nvidia", "gpu", "gta", "bmw", "news", "katalysator"]):
        if not current_product_catalysts:
            levels.append("Produkt-News: kein belastbarer Produkt-Katalysator im aktuellen Briefing. Nicht jede Headline reicht als Setup.")
        for item in current_product_catalysts[:5]:
            if isinstance(item, dict):
                ticker = str(item.get("symbol") or item.get("ticker") or "").upper()
                title = item.get("title") or item.get("headline") or item.get("summary") or ""
                source = item.get("source") or item.get("publisher") or ""
                levels.append(f"Product Catalyst: {ticker} - {str(title)[:120]}" + (f" ({source})" if source else ""))

    if any(token in msg for token in ["event", "ping", "krieg", "war", "policy", "map", "karte", "impact"]):
        if not current_event_pings:
            levels.append("Event Map: keine priorisierten Pings im Filter. Das bedeutet nicht 'kein Risiko', sondern keinen starken App-Trigger.")
        for ping in current_event_pings[:5]:
            if isinstance(ping, dict):
                ping_type = ping.get("type") or "event"
                severity = ping.get("severity") or "normal"
                region = ping.get("region") or ping.get("country") or "global"
                symbols = ping.get("symbols") or []
                levels.append(
                    f"Event Ping: {ping_type}/{severity} in {region}"
                    + (f" -> {', '.join(map(str, symbols[:4]))}" if isinstance(symbols, list) and symbols else "")
                )
        for impact in current_watchlist_impact[:4]:
            if isinstance(impact, dict):
                ticker = str(impact.get("symbol") or impact.get("ticker") or "").upper()
                action = impact.get("action") or impact.get("impact") or "watch"
                reason = impact.get("reason") or impact.get("summary") or ""
                levels.append(f"Watchlist Impact: {ticker} {action} - {str(reason)[:110]}")

    if any(token in msg for token in ["polymarket", "prediction", "wetten", "wahrscheinlichkeit"]):
        if current_prediction_signals:
            for item in current_prediction_signals[:4]:
                market = str(item.get("market") or "")[:120]
                probability = item.get("probability")
                relevance = item.get("relevance")
                prob_text = f"{float(probability) * 100:.0f}%" if isinstance(probability, (int, float)) else "n/a"
                levels.append(f"Polymarket: {prob_text} | relevance {relevance} - {market}")
        else:
            status_text = prediction_status.get("status") if isinstance(prediction_status, dict) else "data_delayed"
            reason = prediction_status.get("message") if isinstance(prediction_status, dict) else ""
            levels.append(f"Polymarket: {status_text}. {reason or 'Feed leer oder verzoegert; Abschnitt bleibt sichtbar.'}")

    wants_data_diagnostics = any(
        token in msg
        for token in [
            "daten",
            "quelle",
            "quellen",
            "fehlt",
            "fehlen",
            "leer",
            "zeigt nichts",
            "warum nichts",
            "status",
            "diagnose",
            "diagnostics",
            "unavailable",
            "deferred",
            "fast mode",
        ]
    )
    if wants_data_diagnostics:
        quality_score = current_quality.get("score")
        quality_status = current_quality.get("status")
        quality_mode = current_quality.get("mode")
        if quality_score is not None or quality_status or quality_mode:
            levels.append(
                f"Briefing Data Quality: {quality_status or 'unknown'} / {quality_score if quality_score is not None else 'n/a'} "
                f"im Modus {quality_mode or 'full'}."
            )
        for source, state in list(current_source_states.items())[:8]:
            state_text = str(state).replace("_", " ")
            source_label = str(source).replace("_", " ")
            if str(state).lower() == "loaded":
                meaning = "aktiv im Brief"
            elif "deferred" in str(state).lower():
                meaning = "wird nachgeladen, deshalb im ersten Blick eventuell leer"
            elif "no_recent" in str(state).lower():
                meaning = "Quelle funktioniert, aber keine frischen Treffer"
            elif "empty" in str(state).lower() or "unavailable" in str(state).lower():
                meaning = "gerade leer oder temporaer nicht erreichbar"
            else:
                meaning = "Status pruefen"
            levels.append(f"Datenquelle {source_label}: {state_text} - {meaning}.")
        if current_deferred_layers:
            levels.append("Nachlade-Layer: " + ", ".join(map(str, current_deferred_layers[:6])) + ".")
        if current_missing_checks:
            levels.append("Fehlende Checks: " + ", ".join(map(str, current_missing_checks[:6])) + ".")

    wants_briefing = any(
        token in msg
        for token in ["brief", "briefing", "morgen", "midday", "telegram", "scheduler", "health", "status"]
    )
    if wants_briefing:
        try:
            scheduler_seen = get_portfolio_manager().get_app_setting("brief_scheduler_loop_seen_at")
            scheduler_error = get_portfolio_manager().get_app_setting("brief_scheduler_loop_error")
            scheduler_next = get_portfolio_manager().get_app_setting("brief_scheduler_loop_next_tick_at")
            if scheduler_seen:
                try:
                    seen_dt = datetime.fromisoformat(str(scheduler_seen).replace("Z", "+00:00"))
                    if seen_dt.tzinfo is not None:
                        seen_dt = seen_dt.astimezone(timezone.utc).replace(tzinfo=None)
                    age_minutes = max(0, int((datetime.utcnow() - seen_dt).total_seconds() // 60))
                    levels.append(f"Scheduler Loop: letzter Tick vor {age_minutes}m, naechster Tick {scheduler_next or 'n/a'}.")
                except Exception:
                    levels.append(f"Scheduler Loop: letzter Tick {scheduler_seen}, naechster Tick {scheduler_next or 'n/a'}.")
            else:
                levels.append("Scheduler Loop: noch kein Tick gespeichert. Health Center/Railway Worker pruefen.")
            if scheduler_error:
                levels.append(f"Scheduler Fehler: {scheduler_error}")
            alert_service = get_email_alert_service()
            brief_statuses = [
                alert_service.get_brief_job_status(job["job_key"])
                for job in _brief_schedule_jobs_for_health()
            ]
            last_success = next(
                (
                    item
                    for item in sorted(
                        [status for status in brief_statuses if status.get("last_success_at")],
                        key=lambda status: str(status.get("last_success_at")),
                        reverse=True,
                    )
                ),
                None,
            )
            last_failure = next(
                (
                    item
                    for item in sorted(
                        [status for status in brief_statuses if status.get("last_error")],
                        key=lambda status: str(status.get("updated_at")),
                        reverse=True,
                    )
                ),
                None,
            )
            if last_success:
                levels.append(
                    f"Letztes Briefing erfolgreich: {last_success.get('job')} um {last_success.get('last_success_at')}"
                )
            if last_failure:
                levels.append(
                    f"Letzter Briefing-Fehler: {last_failure.get('job')} - {last_failure.get('last_error')}"
                )
        except Exception:
            levels.append("Briefing-Status konnte gerade nicht geladen werden.")

    next_steps = [
        "1. Erst den Trigger abwarten, nicht vor der Bestaetigung handeln.",
        "2. Positionsgroesse klein halten, wenn Regime oder Newsflow gemischt sind.",
        "3. Bei Gegenreaktion sofort Invalidierung pruefen.",
    ]
    if primary and wants_dossier:
        next_steps.append("4. Bei der naechsten Quartalszahl zuerst Umsatzwachstum, Marge und Guidance gegen die Erwartung pruefen.")
        next_steps.append("5. Analysten-Ziel nur als Kontext nutzen; Kursreaktion und Volumen muessen es bestaetigen.")

    active_tab = (req.active_tab or "").lower()
    app_actions: List[str] = []
    if primary:
        app_actions.append(f"Analyze: {symbol} Kursverlauf, Dossier und Trigger pruefen.")
    elif tickers:
        app_actions.append(f"Analyze: {tickers[0]} als Fokus-Ticker oeffnen.")
    if active_tab == "discovery":
        app_actions.append("Markets: Gewinner/Verlierer erst filtern, dann nur per Analyze-Button in die Detailanalyse.")
        app_actions.append("Markets: Bei Event-Ping zuerst betroffene Ticker und Hedge-Idee lesen.")
    else:
        app_actions.append("Markets: Top Movers, Market Explorer und Event-Pings gegenchecken.")
    if active_tab == "portfolio":
        app_actions.append("Portfolio: Schwaechste Rendite seit Kauf, groesste Position und Briefing-Auswirkung vergleichen.")
    else:
        app_actions.append("Portfolio: Exposure, Rendite seit Kauf und Hedge-Bedarf pruefen.")
    if active_tab == "analyze":
        app_actions.append("Analyze: Wenn History nur Snapshot/Stale ist, Setup erst nach aktualisiertem Chart bestaetigen.")
    else:
        app_actions.append("Analyze: Fokus-Ticker oeffnen und Dossier/Chart gegen das Briefing pruefen.")
    if wants_briefing:
        app_actions.append("Health: Scheduler/Telegram im Health Center pruefen, falls ein Brief fehlt.")
    if learning_summary.get("forecasts"):
        app_actions.append("Learning Board: letzte Treffer/Misses ansehen, bevor ein Signal hoeher gewichtet wird.")

    response = (
        f"These: {thesis}\n"
        f"Erklaerung: {' '.join(explain_lines)}\n"
        f"Risiko: {' | '.join(risk_line_parts)}\n"
        f"Trigger: {trigger_line}\n"
        f"Invalidierung: {invalidation_line}\n"
        + (("Dossier:\n" + "\n".join([f"- {line}" for line in dossier_lines]) + "\n") if dossier_lines else "")
        +
        "Beobachtbare Levels:\n"
        + "\n".join([f"- {line}" for line in levels])
        + "\nNaechste Schritte:\n"
        + "\n".join([f"- {line}" for line in next_steps])
        + "\nApp-Aktionen:\n"
        + "\n".join([f"- {line}" for line in app_actions])
    )
    return {"response": response}


@app.get("/api/portfolio/{p_id}/suggestions")
async def get_suggestions(p_id: str):
    portfolios = get_portfolio_manager().get_portfolios()
    portfolio = next((p for p in portfolios if p['id'] == p_id), None)
    tickers = [h['ticker'] for h in portfolio['holdings']] if portfolio else []
    return await get_discovery_service().get_diversification_suggestions(tickers)


@app.post("/api/portfolios")
async def create_portfolio(req: CreatePortfolioRequest):
    try:
        return get_portfolio_manager().create_portfolio(req.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Portfolio could not be saved: {exc.__class__.__name__}")

@app.delete("/api/portfolios/{p_id}")
async def delete_portfolio(p_id: str):
    if get_scalable_integration_service().is_managed_portfolio(p_id):
        raise HTTPException(status_code=409, detail="Scalable-Portfolio wird ausschließlich durch Read-only-Sync verwaltet.")
    get_portfolio_manager().delete_portfolio(p_id)
    return {"status": "deleted"}

@app.post("/api/portfolios/{p_id}/holdings")
async def add_holding(p_id: str, req: AddHoldingRequest):
    if get_scalable_integration_service().is_managed_portfolio(p_id):
        raise HTTPException(status_code=409, detail="Scalable-Positionen können nur synchronisiert werden.")
    try:
        saved = get_portfolio_manager().add_holding(p_id, req.ticker, req.shares, req.buy_price, req.purchase_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not saved:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return saved

@app.patch("/api/portfolios/{p_id}/holdings/{ticker}")
async def update_holding(p_id: str, ticker: str, req: UpdateHoldingRequest):
    if get_scalable_integration_service().is_managed_portfolio(p_id):
        raise HTTPException(status_code=409, detail="Scalable-Positionen können nur synchronisiert werden.")
    updated = get_portfolio_manager().update_holding(
        p_id,
        ticker,
        shares=req.shares,
        buy_price=req.buy_price,
        purchase_date=req.purchase_date,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Holding not found")
    return updated

@app.delete("/api/portfolios/{p_id}/holdings/{ticker}")
async def remove_holding(p_id: str, ticker: str):
    if get_scalable_integration_service().is_managed_portfolio(p_id):
        raise HTTPException(status_code=409, detail="Scalable-Positionen können nur synchronisiert werden.")
    get_portfolio_manager().remove_holding(p_id, ticker)
    return {"status": "removed"}


@app.post("/api/portfolio/analyze")
async def analyze_portfolio(request: PortfolioRequest) -> Dict[str, Any]:
    """
    Analyze a portfolio of stocks.
    
    Args:
        request: Portfolio holdings with ticker, shares, and optional buy price
    
    Returns:
        Portfolio analysis including total value, performance, and individual stock analyses
    """
    try:
        if get_scalable_integration_service().is_managed_portfolio(request.portfolio_id or ""):
            return convert_numpy_types(
                await asyncio.to_thread(get_scalable_integration_service().portfolio_analysis)
            )
        holdings_data = []
        total_value = 0
        total_cost = 0
        weighted_score = 0
        sector_allocation = {}
        
        for holding in request.holdings:
            try:
                fetcher = DataFetcher(holding.ticker)
                info = fetcher.info
                price_data = fetcher.get_price_data()
                purchase_date = str(holding.purchase_date or "").strip() or None
                holding_days = None
                if purchase_date:
                    try:
                        purchase_dt = datetime.fromisoformat(purchase_date[:10]).date()
                        holding_days = max(0, (datetime.now(timezone.utc).date() - purchase_dt).days)
                        purchase_date = purchase_dt.isoformat()
                    except Exception:
                        purchase_date = None
                
                current_price = price_data.get("current_price") or 0
                position_value = current_price * holding.shares
                cost_basis = (holding.buy_price or current_price) * holding.shares
                gain_loss = position_value - cost_basis
                gain_loss_pct = ((position_value / cost_basis) - 1) * 100 if cost_basis > 0 else 0
                
                # Quick analysis for score
                data = fetcher.get_all_data()
                analyzer = StockAnalyzer(data)
                result = analyzer.generate_recommendation()
                
                sector = info.get("sector", "Other")
                if sector in sector_allocation:
                    sector_allocation[sector] += position_value
                else:
                    sector_allocation[sector] = position_value
                
                holdings_data.append({
                    "ticker": holding.ticker.upper(),
                    "name": info.get("longName") or info.get("shortName") or holding.ticker,
                    "shares": holding.shares,
                    "current_price": current_price,
                    "buy_price": holding.buy_price,
                    "purchase_date": purchase_date,
                    "holding_days": holding_days,
                    "position_value": position_value,
                    "cost_basis": cost_basis,
                    "gain_loss": gain_loss,
                    "gain_loss_pct": gain_loss_pct,
                    "return_since_buy": gain_loss,
                    "return_since_buy_pct": gain_loss_pct,
                    "change_1d": price_data.get("change_1w", 0) / 5 if price_data.get("change_1w") else 0,
                    "change_1y": price_data.get("change_1y"),
                    "sector": sector,
                    "score": result.get("total_score", 0),
                    "recommendation": result.get("recommendation", {}).get("action", "HOLD"),
                    "valuation": result.get("valuation", Valuation.FAIRLY_VALUED).value,
                })
                
                total_value += position_value
                total_cost += cost_basis
                weighted_score += result.get("total_score", 0) * position_value
                
            except Exception as e:
                holdings_data.append({
                    "ticker": holding.ticker.upper(),
                    "error": str(e),
                    "shares": holding.shares,
                })
        
        # Calculate portfolio metrics
        portfolio_gain_loss = total_value - total_cost
        portfolio_gain_loss_pct = ((total_value / total_cost) - 1) * 100 if total_cost > 0 else 0
        avg_score = weighted_score / total_value if total_value > 0 else 0
        holding_day_values = [float(h.get("holding_days")) for h in holdings_data if h.get("holding_days") is not None]
        
        # Convert sector allocation to percentages
        sector_pct = {}
        for sector, value in sector_allocation.items():
            sector_pct[sector] = (value / total_value) * 100 if total_value > 0 else 0
        
        return convert_numpy_types({
            "holdings": holdings_data,
            "summary": {
                "total_value": total_value,
                "total_cost": total_cost,
                "gain_loss": portfolio_gain_loss,
                "gain_loss_pct": portfolio_gain_loss_pct,
                "return_since_buy": portfolio_gain_loss,
                "return_since_buy_pct": portfolio_gain_loss_pct,
                "num_holdings": len([h for h in holdings_data if "error" not in h]),
                "avg_score": avg_score,
                "avg_holding_days": (sum(holding_day_values) / len(holding_day_values)) if holding_day_values else None,
                "sector_allocation": sector_pct,
            }
        })
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Portfolio analysis failed: {str(e)}"
        )


@app.get("/api/portfolio/{p_id}/history")
async def get_portfolio_history(p_id: str, period: str = "1mo"):
    """
    Calculate historical value of the entire portfolio.
    """
    portfolios = get_portfolio_manager().get_portfolios()
    portfolio = next((p for p in portfolios if p["id"] == p_id), None)

    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    holdings = portfolio.get("holdings") or []
    if not holdings:
        return []

    interval = "1d" if period != "1d" else "5m"
    combined_history: Dict[str, float] = {}
    fallback_value = 0.0
    symbols: List[str] = []

    async def _fetch_holding_history(ticker: str) -> List[Dict[str, Any]]:
        def _fetch() -> List[Dict[str, Any]]:
            return DataFetcher(ticker).get_history(period=period, interval=interval)

        return await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=14.0)

    for holding in holdings:
        ticker = str(holding.get("ticker") or "").upper().strip()
        if not ticker:
            continue
        symbols.append(ticker)

        try:
            shares = float(holding.get("shares") or 0)
        except (TypeError, ValueError):
            shares = 0.0
        if shares <= 0:
            continue

        buy_price = holding.get("buyPrice", holding.get("buy_price"))
        try:
            fallback_value += shares * float(buy_price or 0)
        except (TypeError, ValueError):
            pass

        try:
            history = await _fetch_holding_history(ticker)
        except Exception:
            history = []

        for entry in history or []:
            try:
                price = float(entry.get("price"))
            except (TypeError, ValueError):
                continue
            if not math.isfinite(price):
                continue

            date = str(entry.get("time") or entry.get("full_date") or "")
            if not date:
                continue
            combined_history[date] = combined_history.get(date, 0.0) + (price * shares)

    if combined_history:
        return convert_numpy_types([
            {"time": d, "price": v}
            for d, v in sorted(combined_history.items())
            if math.isfinite(v)
        ])

    # Last-resort snapshot fallback keeps portfolio widgets from turning provider issues into HTTP 500s.
    try:
        snapshot = get_realtime_market_service().build_snapshot(symbols)
        quotes = {
            str(item.get("symbol") or "").upper(): item
            for item in snapshot.get("quotes", [])
            if isinstance(item, dict)
        }
        snapshot_value = 0.0
        for holding in holdings:
            ticker = str(holding.get("ticker") or "").upper().strip()
            quote = quotes.get(ticker)
            if not quote:
                continue
            try:
                shares = float(holding.get("shares") or 0)
                price = float(quote.get("price"))
            except (TypeError, ValueError):
                continue
            if math.isfinite(shares) and math.isfinite(price):
                snapshot_value += shares * price
        if snapshot_value > 0:
            return [{"time": "snapshot", "price": snapshot_value, "stale": True}]
    except Exception:
        pass

    if fallback_value > 0:
        return [{"time": "cost_basis", "price": fallback_value, "stale": True}]

    return []

@app.get("/api/portfolio/{p_id}/export/csv")
async def export_portfolio_csv(p_id: str):
    """Export portfolio as CSV."""
    import csv
    import io
    from fastapi.responses import StreamingResponse
    
    portfolios = get_portfolio_manager().get_portfolios()
    portfolio = next((p for p in portfolios if p['id'] == p_id), None)
    
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
        
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Ticker", "Shares", "Buy Price", "Purchase Date"])
    
    for h in portfolio['holdings']:
        writer.writerow([h['ticker'], h['shares'], h.get('buyPrice', 'N/A'), h.get('purchaseDate', '')])
        
    output.seek(0)
    return StreamingResponse(
        output, 
        media_type="text/csv", 
        headers={"Content-Disposition": f"attachment; filename=portfolio_{p_id}.csv"}
    )


@app.get("/api/discovery/trending")
async def get_trending_stocks():
    """Get trending stocks based on social/market sentiment."""
    try:
        return await get_discovery_service().get_trending()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/discovery/rebounds")
async def get_rebound_opportunities():
    """Find oversold quality stocks."""
    try:
        return await get_discovery_service().get_rebounds()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/discovery/cryptos")
async def get_trending_cryptos():
    """Get trending cryptocurrencies."""
    try:
        return await get_discovery_service().get_cryptos()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/discovery/commodities")
async def get_trending_commodities():
    """Get trending commodities."""
    try:
        return await get_discovery_service().get_commodities()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/discovery/etfs")
async def get_discovery_etfs():
    """Get popular ETFs for discovery."""
    try:
        return convert_numpy_types(await get_discovery_service().get_etfs())
    except Exception:
        return convert_numpy_types(get_discovery_service()._etf_fallbacks())

@app.get("/api/discovery/stars")
async def get_star_assets():
    """Get the spotlight assets (Day/Week winners/losers)."""
    try:
        return convert_numpy_types(await get_discovery_service().get_star_assets())
    except Exception:
        service = get_discovery_service()
        movers = service._market_mover_fallbacks("gainers")
        losers = service._market_mover_fallbacks("losers")
        return convert_numpy_types({
            "day_winner": movers[0],
            "week_winner": movers[0],
            "day_loser": losers[0],
            "week_loser": losers[0],
            "for_you": movers[:1] + losers[:1],
            "fallback": True,
        })

@app.get("/api/discovery/public-signals")
async def get_public_signals():
    """Get delayed public copy-trade style signals from official sources."""
    try:
        return convert_numpy_types(get_public_signal_service().get_public_signals())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/signals/watchlist")
async def get_signal_watchlist():
    try:
        cached = _cache_get("signals:watchlist", int(os.getenv("WATCHLIST_CACHE_TTL_SECONDS", "45")))
        if cached is not None:
            return convert_numpy_types(cached)
        items = get_portfolio_manager().get_signal_watch_items()
        summary = get_public_signal_service().build_watchlist_snapshot(items)
        return convert_numpy_types(_cache_set("signals:watchlist", summary))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/signals/watchlist/items")
async def add_signal_watch_item(req: SignalWatchItemRequest):
    try:
        get_portfolio_manager().add_signal_watch_item(req.kind, req.value)
        _cache_forget("signals:")
        _cache_forget("radar_bootstrap:")
        _cache_forget("morning_brief:")
        items = get_portfolio_manager().get_signal_watch_items()
        return convert_numpy_types(get_public_signal_service().build_watchlist_snapshot(items))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/signals/watchlist/items")
async def delete_signal_watch_item(kind: str, value: str):
    try:
        get_portfolio_manager().remove_signal_watch_item(kind, value)
        _cache_forget("signals:")
        _cache_forget("radar_bootstrap:")
        _cache_forget("morning_brief:")
        items = get_portfolio_manager().get_signal_watch_items()
        return convert_numpy_types(get_public_signal_service().build_watchlist_snapshot(items))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/alerts")
async def list_price_alerts():
    try:
        return convert_numpy_types(get_portfolio_manager().list_price_alerts())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/alerts")
async def create_price_alert(req: PriceAlertCreateRequest):
    try:
        payload = get_portfolio_manager().create_price_alert(
            symbol=req.symbol,
            direction=req.direction,
            target_price=req.target_price,
            enabled=req.enabled,
            cooldown_minutes=req.cooldown_minutes,
        )
        return convert_numpy_types(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/alerts/{alert_id}")
async def update_price_alert(alert_id: str, req: PriceAlertUpdateRequest):
    try:
        updated = get_portfolio_manager().update_price_alert(
            alert_id,
            req.model_dump(exclude_none=True),
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Alert not found")
        return convert_numpy_types(updated)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/alerts/{alert_id}")
async def delete_price_alert(alert_id: str):
    try:
        removed = get_portfolio_manager().delete_price_alert(alert_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Alert not found")
        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/signals/alerts/check")
async def check_signal_alerts():
    try:
        return get_email_alert_service().check_and_send_alerts(force=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/signals/alerts/test")
async def send_test_signal_alert():
    try:
        return get_email_alert_service().send_test_email()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/signals/alerts/critical-market")
async def check_critical_market_alerts():
    try:
        return get_email_alert_service().check_and_send_critical_market_alerts(force=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/notifications/status")
async def get_notification_status():
    try:
        return get_email_alert_service().get_notification_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/settings/profile")
async def get_workspace_profile():
    try:
        return convert_numpy_types(get_portfolio_manager().get_workspace_profile())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/settings/profile")
async def save_workspace_profile(req: WorkspaceProfileRequest):
    try:
        payload = req.model_dump(exclude_none=True)
        return convert_numpy_types(get_portfolio_manager().save_workspace_profile(payload))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/advisory/profile")
async def get_advisory_profile():
    try:
        profile = get_portfolio_manager().get_workspace_profile()
        return convert_numpy_types(advisory_profile_subset(profile))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/advisory/profile")
async def save_advisory_profile(req: AdvisoryProfileRequest):
    try:
        payload = req.model_dump(exclude_none=True)
        profile = get_portfolio_manager().save_workspace_profile(payload)
        return convert_numpy_types(advisory_profile_subset(profile))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/advisory/suitability-check")
async def check_signal_suitability(req: SuitabilityCheckRequest):
    try:
        profile = get_portfolio_manager().get_workspace_profile()
        result = build_suitability_check(profile, req.model_dump(exclude_none=True))
        return convert_numpy_types(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/advisory/portfolio-check")
async def check_portfolio_advisory(req: PortfolioAdvisoryCheckRequest):
    try:
        profile = get_portfolio_manager().get_workspace_profile()
        result = build_portfolio_advisory_check(profile, req.model_dump())
        return convert_numpy_types(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/settings/signal-score")
async def get_signal_score_settings():
    try:
        return convert_numpy_types(get_portfolio_manager().get_signal_score_settings())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/settings/signal-score")
async def save_signal_score_settings(payload: Dict[str, Any]):
    try:
        manager = get_portfolio_manager()
        before = manager.get_signal_score_settings()
        saved = manager.save_signal_score_settings(payload)
        audit = manager.record_decision_audit(
            event_type="rule_change",
            subject="signal-score-settings",
            decision="settings_updated",
            data_as_of=datetime.now(timezone.utc).isoformat(),
            source_status="internal_configuration",
            sources=[],
            model_version="signal-score.v1",
            rule_version="signal-score-settings.v2",
            user_action="signal_score_settings_saved",
            payload={"before": before, "requested_change": payload, "after": saved},
        )
        return convert_numpy_types({**saved, "audit": audit})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/signals/alerts/daily-brief")
async def send_daily_brief():
    try:
        return get_email_alert_service().send_daily_brief()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/signals/alerts/a-setup-digest")
async def send_a_setup_digest():
    try:
        return await get_email_alert_service().send_a_setup_digest_async()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/signals/history")
async def get_signal_history(limit: int = 100):
    try:
        return convert_numpy_types(get_portfolio_manager().get_sent_signal_events(limit=limit))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def build_radar_bootstrap(limit: int = 8) -> Dict[str, Any]:
    started_at = time.perf_counter()
    cache_key = f"radar_bootstrap:{limit}"
    cached = _cache_get(cache_key, int(os.getenv("RADAR_BOOTSTRAP_CACHE_TTL_SECONDS", "180")))
    if cached is not None:
        return cached

    items = get_portfolio_manager().get_signal_watch_items()
    settings = get_portfolio_manager().get_signal_score_settings()
    component_status: Dict[str, Dict[str, Any]] = {}

    async def bounded(name: str, awaitable: Any, timeout_seconds: float, fallback: Any) -> Any:
        component_started = time.perf_counter()
        try:
            result = await asyncio.wait_for(awaitable, timeout=timeout_seconds)
            component_status[name] = {
                "status": "ready",
                "latency_ms": round((time.perf_counter() - component_started) * 1000),
            }
            return result
        except asyncio.TimeoutError:
            component_status[name] = {
                "status": "timeout",
                "latency_ms": round((time.perf_counter() - component_started) * 1000),
                "message": f"{name} exceeded the radar time budget; partial data returned.",
            }
            return fallback
        except Exception as exc:
            component_status[name] = {
                "status": "error",
                "latency_ms": round((time.perf_counter() - component_started) * 1000),
                "message": str(exc)[:240],
            }
            return fallback

    snapshot = _cache_get("signals:watchlist", int(os.getenv("RADAR_WATCHLIST_CACHE_TTL_SECONDS", "300")))
    if snapshot is not None:
        component_status["watchlist"] = {"status": "cached", "latency_ms": 0}
    else:
        snapshot = await bounded(
            "watchlist",
            asyncio.to_thread(get_public_signal_service().build_watchlist_snapshot, items),
            float(os.getenv("RADAR_WATCHLIST_TIMEOUT_SECONDS", "5")),
            {
                "items": items,
                "ticker_signals": [],
                "status": "partial",
                "message": "Watchlist provider timed out; configured items returned without fresh enrichment.",
            },
        )
        if component_status["watchlist"]["status"] == "ready":
            _cache_set("signals:watchlist", snapshot)

    scoreboard_cached = _cache_get(
        "signals:scoreboard",
        int(os.getenv("RADAR_SCOREBOARD_CACHE_TTL_SECONDS", "300")),
    )
    if scoreboard_cached is not None:
        component_status["scoreboard"] = {"status": "cached", "latency_ms": 0}

    scoreboard_fallback = {
        "stocks": [],
        "crypto": [],
        "meta": {
            "status": "partial",
            "source": "radar_timeout_fallback",
            "message": "Scoreboard time budget exceeded; no synthetic scores were inserted.",
        },
    }
    scoreboard_task = (
        asyncio.sleep(0, result=scoreboard_cached)
        if scoreboard_cached is not None
        else bounded(
            "scoreboard",
            asyncio.to_thread(
                lambda: asyncio.run(get_signal_score_service().build_scoreboard(snapshot, settings))
            ),
            float(os.getenv("RADAR_SCOREBOARD_TIMEOUT_SECONDS", "10")),
            scoreboard_fallback,
        )
    )
    brief_task = bounded(
        "brief",
        asyncio.to_thread(get_morning_brief_service().get_brief_fast, snapshot),
        float(os.getenv("RADAR_BRIEF_TIMEOUT_SECONDS", "8")),
        get_morning_brief_service().build_empty_brief("radar_timeout"),
    )
    session_task = bounded(
        "session_lists",
        asyncio.to_thread(
            lambda: asyncio.run(get_session_list_service().build_session_lists(snapshot))
        ),
        float(os.getenv("RADAR_SESSION_LIST_TIMEOUT_SECONDS", "8")),
        {
            "status": "partial",
            "message": "Session lists timed out; no fallback movers were invented.",
            "regions": {},
        },
    )
    intelligence_task = bounded(
        "trading_intelligence",
        asyncio.to_thread(get_trading_intelligence_service().build_snapshot, snapshot),
        float(os.getenv("RADAR_INTELLIGENCE_TIMEOUT_SECONDS", "6")),
        {"status": "partial", "message": "Trading intelligence timed out."},
    )
    learning_task = bounded(
        "learning",
        asyncio.to_thread(get_forecast_learning_service().build_dashboard),
        float(os.getenv("RADAR_LEARNING_TIMEOUT_SECONDS", "5")),
        {"status": "partial", "message": "Learning dashboard timed out."},
    )

    scoreboard, brief, session_lists, trading_intelligence, learning = await asyncio.gather(
        scoreboard_task,
        brief_task,
        session_task,
        intelligence_task,
        learning_task,
    )
    if scoreboard_cached is None and component_status.get("scoreboard", {}).get("status") == "ready":
        _cache_set("signals:scoreboard", scoreboard)

    paper_dashboard = await bounded(
        "paper_dashboard",
        asyncio.to_thread(
            get_paper_trading_service().build_dashboard,
            scoreboard,
            settings,
            brief,
        ),
        float(os.getenv("RADAR_PAPER_DASHBOARD_TIMEOUT_SECONDS", "8")),
        {
            "status": "partial",
            "playbooks": [],
            "open_trades": [],
            "message": "Paper dashboard timed out; no candidate or trade was fabricated.",
        },
    )
    overall_status = (
        "ready"
        if all(item.get("status") in {"ready", "cached"} for item in component_status.values())
        else "partial"
    )
    payload = {
        "watchlist": convert_numpy_types(snapshot),
        "history": convert_numpy_types(get_portfolio_manager().get_sent_signal_events(limit=limit)),
        "brief": convert_numpy_types(brief),
        "scoreboard": convert_numpy_types(scoreboard),
        "session_lists": convert_numpy_types(session_lists),
        "paper_dashboard": convert_numpy_types(paper_dashboard),
        "trading_intelligence": convert_numpy_types(trading_intelligence),
        "learning": convert_numpy_types(learning),
        "bootstrap_status": {
            "schema": "radar-bootstrap-status.v1",
            "status": overall_status,
            "latency_ms": round((time.perf_counter() - started_at) * 1000),
            "components": component_status,
            "policy": "Bounded partial response; missing providers never create synthetic market or trade data.",
        },
    }
    return _cache_set(cache_key, payload)


@app.get("/api/radar/bootstrap")
async def get_radar_bootstrap(limit: int = 8):
    try:
        return await build_radar_bootstrap(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/learning/forecasts")
async def get_forecast_learning_dashboard():
    try:
        return convert_numpy_types(get_forecast_learning_service().build_dashboard())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/learning/evaluate")
async def evaluate_forecast_learning():
    try:
        result = await asyncio.to_thread(get_forecast_learning_service().evaluate_due_forecasts)
        get_portfolio_manager().set_app_setting(
            "forecast_learning_last_result",
            json.dumps({"checked_at": datetime.utcnow().isoformat(), **result}),
        )
        return convert_numpy_types(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def _emergency_morning_brief(reason: str) -> Dict[str, Any]:
    """Stable frontend contract when the brief service itself cannot start."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "macro_score": 0,
        "macro_regime": "mixed",
        "opening_bias": "Daten werden aktualisiert",
        "headline": "Morning Brief voruebergehend eingeschraenkt",
        "summary_points": [
            "Marktdaten sind momentan nicht vollstaendig verfuegbar.",
            "Keine Entscheidung auf Basis dieses eingeschraenkten Briefings treffen.",
        ],
        "regions": {
            "asia": {"label": "Asia", "tone": "mixed", "avg_change_1d": 0.0, "assets": []},
            "europe": {"label": "Europe", "tone": "mixed", "avg_change_1d": 0.0, "assets": []},
            "usa": {"label": "USA", "tone": "mixed", "avg_change_1d": 0.0, "assets": []},
        },
        "macro_assets": [],
        "top_news": [],
        "event_layer": [],
        "event_pings": [],
        "market_movers": {"gainers": [], "losers": []},
        "trade_setups": [],
        "trade_setups_status": "insufficient_signal",
        "setup_board": {"now": [], "next": [], "avoid": []},
        "action_board": [],
        "portfolio_brain": [],
        "watchlist_impact": [],
        "trading_edge": {},
        "data_status": {"mode": "fallback", "deferred": [], "sources": {}},
        "quality": {
            "status": "partial",
            "score": 0,
            "passed": 0,
            "total": 0,
            "missing": ["upstream_data"],
            "checks": [],
            "fallback": reason,
        },
    }


def _stamp_brief_freshness(brief: Dict[str, Any]) -> Dict[str, Any]:
    quality = brief.get("quality")
    if not isinstance(quality, dict):
        quality = {}
        brief["quality"] = quality
    generated_at = None
    try:
        generated_at = datetime.fromisoformat(str(brief.get("generated_at") or "").replace("Z", "+00:00"))
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        generated_at = None
    age_minutes = (
        max(0, int((datetime.now(timezone.utc) - generated_at.astimezone(timezone.utc)).total_seconds() // 60))
        if generated_at is not None
        else None
    )
    quality["age_minutes"] = age_minutes
    quality["freshness"] = (
        "fresh"
        if age_minutes is not None and age_minutes <= 20
        else "recent"
        if age_minutes is not None and age_minutes <= 90
        else "stale"
    )
    return brief


def _safe_morning_brief_fallback(
    service: Any,
    reason: str,
    snapshot: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    fallback = None
    try:
        fallback = service.get_cached_or_last_brief(snapshot)
    except Exception:
        pass
    if fallback is None:
        try:
            fallback = service.build_empty_brief(reason)
        except Exception:
            fallback = _emergency_morning_brief(reason)
    if (
        not isinstance(fallback, dict)
        or not str(fallback.get("headline") or "").strip()
        or not isinstance(fallback.get("regions"), dict)
    ):
        fallback = _emergency_morning_brief(reason)
    fallback = _stamp_brief_freshness(copy.deepcopy(fallback))
    quality = fallback.get("quality")
    if not isinstance(quality, dict):
        quality = {}
        fallback["quality"] = quality
    regions = fallback.get("regions") if isinstance(fallback.get("regions"), dict) else {}
    has_region_assets = any((region or {}).get("assets") for region in regions.values())
    try:
        quality_score = int(quality.get("score") or 0)
    except (TypeError, ValueError):
        quality_score = 0
    is_usable = (
        not quality.get("fallback")
        and quality_score > 0
        and (has_region_assets or bool(fallback.get("top_news")) or bool(fallback.get("trade_setups")))
    )
    if is_usable:
        quality["delivery_mode"] = "cached"
        quality["refresh_state"] = reason
    else:
        quality["status"] = "partial"
        quality["fallback"] = reason
        quality["delivery_mode"] = "degraded"
    return fallback


@app.get("/api/market/regions")
async def get_market_regions():
    """Independent low-latency regional indices for the world map."""
    cached = _cache_get("market:regions", 45)
    if cached is not None:
        return convert_numpy_types(cached)
    try:
        payload = await asyncio.wait_for(
            asyncio.to_thread(get_morning_brief_service().get_regional_snapshot_fast),
            timeout=6.0,
        )
        return convert_numpy_types(_cache_set("market:regions", payload))
    except Exception:
        return convert_numpy_types({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "regions": {},
            "quality": {
                "current": False,
                "status": "unavailable",
                "missing_regions": ["asia", "europe", "usa"],
                "source": "regional_chart",
            },
        })


@app.get("/api/market/morning-brief")
async def get_morning_brief(fast: bool = False):
    try:
        service = get_morning_brief_service()
    except Exception as exc:
        print(f"Morning brief service initialization fallback: {exc}")
        fallback = attach_scope(_emergency_morning_brief("service_initialization"), research_scope())
        return convert_numpy_types(_audit_morning_brief(fallback, "brief_fallback_served"))
    try:
        if fast:
            fallback = _safe_morning_brief_fallback(service, "warming_up")
            quality = fallback.setdefault("quality", {})
            quality["cache_mode"] = "fast_cached"
            return convert_numpy_types(_audit_morning_brief(attach_scope(fallback, research_scope()), "fast_brief_requested"))

        cached = _cache_get("morning_brief:full", int(os.getenv("MORNING_BRIEF_HTTP_CACHE_TTL_SECONDS", "90")))
        if cached is not None:
            return convert_numpy_types(attach_scope(cached, research_scope()))

        items = get_portfolio_manager().get_signal_watch_items()
        try:
            snapshot = await asyncio.wait_for(
                asyncio.to_thread(get_public_signal_service().build_watchlist_snapshot, items),
                timeout=4.0,
            )
        except asyncio.TimeoutError:
            snapshot = {"items": [], "ticker_signals": []}
        except Exception:
            snapshot = {"items": [], "ticker_signals": []}
        try:
            brief = await asyncio.wait_for(
                asyncio.to_thread(service.get_brief_fast, snapshot),
                timeout=float(os.getenv("MORNING_BRIEF_API_TIMEOUT_SECONDS", "20")),
            )
        except asyncio.TimeoutError:
            fallback = _safe_morning_brief_fallback(service, "timeout", snapshot)
            return convert_numpy_types(_audit_morning_brief(attach_scope(fallback, research_scope()), "brief_timeout_fallback_served"))
        except Exception:
            fallback = _safe_morning_brief_fallback(service, "error", snapshot)
            return convert_numpy_types(_audit_morning_brief(attach_scope(fallback, research_scope()), "brief_error_fallback_served"))

        brief = _stamp_brief_freshness(brief)
        quality = brief.setdefault("quality", {})
        quality["delivery_mode"] = "generated"
        quality["refresh_state"] = "ready"
        scoped_brief = attach_scope(brief, research_scope())
        audited_brief = _audit_morning_brief(scoped_brief, "brief_generated")
        return convert_numpy_types(_cache_set("morning_brief:full", audited_brief))
    except Exception:
        fallback = attach_scope(_safe_morning_brief_fallback(service, "server_error"), research_scope())
        return convert_numpy_types(_audit_morning_brief(fallback, "brief_server_fallback_served"))


@app.get("/api/market/trading-edge")
async def get_trading_edge():
    """Heavy trading-signals payload (squeeze, insider, options, regime,
    sectors, yield curve). Loaded by the frontend separately so the main
    brief stays fast. Cached internally per-component (10min – 6h)."""
    cache_ttl = int(os.getenv("TRADING_EDGE_HTTP_CACHE_TTL_SECONDS", "300"))
    stale_ttl = int(os.getenv("TRADING_EDGE_STALE_CACHE_TTL_SECONDS", "1800"))
    timeout_seconds = float(os.getenv("TRADING_EDGE_API_TIMEOUT_SECONDS", "12"))

    cached = _cache_get(TRADING_EDGE_CACHE_KEY, cache_ttl)
    if cached is not None:
        return convert_numpy_types(cached)

    def _build_trading_edge_payload() -> Dict[str, Any]:
        items = get_portfolio_manager().get_signal_watch_items()
        snapshot = get_public_signal_service().build_watchlist_snapshot(items)
        payload = get_morning_brief_service().get_trading_edge(snapshot) or {}
        if isinstance(payload, dict):
            meta = payload.setdefault("meta", {})
            if isinstance(meta, dict):
                meta["delivery_mode"] = "generated"
                meta["refresh_state"] = "ready"
        return payload

    try:
        payload = await asyncio.wait_for(
            asyncio.to_thread(_build_trading_edge_payload),
            timeout=timeout_seconds,
        )
        return convert_numpy_types(_cache_set(TRADING_EDGE_CACHE_KEY, payload))
    except asyncio.TimeoutError:
        stale = _cache_get_stale(TRADING_EDGE_CACHE_KEY, stale_ttl)
        if stale is not None:
            return convert_numpy_types(stale)
        return convert_numpy_types(
            {
                "meta": {
                    "delivery_mode": "degraded",
                    "refresh_state": "timeout",
                    "fallback_reason": "trading_edge_timeout",
                    "message": "Trading Edge wird im Hintergrund neu geladen.",
                }
            }
        )
    except Exception as e:
        stale = _cache_get_stale(TRADING_EDGE_CACHE_KEY, stale_ttl)
        if stale is not None:
            return convert_numpy_types(stale)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/send-telegram-brief")
async def send_telegram_brief_now(session: str = "global"):
    """Manually trigger a rich Telegram brief without waiting for the
    scheduled slot. Useful for testing or on-demand market checks.

    session: global | europe | midday | usa | europe_close | close | usa_close
    """
    valid = {"global", "europe", "midday", "usa", "europe_close", "close", "usa_close"}
    if session not in valid:
        raise HTTPException(status_code=400, detail=f"session must be one of {sorted(valid)}")
    try:
        result = get_email_alert_service().send_session_brief_now(session)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/send-paper-account-status")
async def send_paper_account_status_now():
    """Manually send the current paper-account status to Telegram."""
    try:
        service = get_paper_trading_service()
        items = get_portfolio_manager().get_signal_watch_items()
        snapshot = get_public_signal_service().build_watchlist_snapshot(items)
        settings = get_portfolio_manager().get_signal_score_settings()
        scoreboard = await get_signal_score_service().build_scoreboard(snapshot, settings)
        dashboard = service.build_dashboard(
            scoreboard,
            settings,
            _get_paper_news_context(snapshot),
        )
        open_trades = dashboard.get("open_trades") or []
        demo_account = dashboard.get("demo_account") or {}
        evidence_campaign = dashboard.get("evidence_campaign") or {}
        strategy_candidate_coverage = dashboard.get("strategy_candidate_coverage") or []
        alert_result = get_email_alert_service().send_paper_account_status_alert(
            demo_account,
            open_trades,
            force=True,
            evidence_campaign=evidence_campaign,
            strategy_candidate_coverage=strategy_candidate_coverage,
        )
        return convert_numpy_types(
            {
                **alert_result,
                "demo_account": {
                    "equity": demo_account.get("equity"),
                    "day_status": demo_account.get("day_status"),
                    "day_action": demo_account.get("day_action"),
                    "net_pnl_value": demo_account.get("net_pnl_value"),
                    "net_pnl_pct": demo_account.get("net_pnl_pct"),
                    "open_trade_count": demo_account.get("open_trade_count"),
                    "management_counts": demo_account.get("management_counts") or {},
                    "performance": demo_account.get("performance") or {},
                },
                "evidence_campaign": evidence_campaign,
                "strategy_candidate_coverage": strategy_candidate_coverage,
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/send-brief-job/{job_key}")
async def send_brief_job_now(job_key: str):
    """Manually resend a specific scheduled brief and mark that job as done today."""
    job = next((item for item in _brief_schedule_jobs_for_health() if item.get("job_key") == job_key), None)
    if not job:
        raise HTTPException(status_code=404, detail="Brief job not found.")
    try:
        tz = ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin"))
    except Exception:
        tz = ZoneInfo("Europe/Berlin")
    event_key = f"{job['job_key']}:{datetime.now(tz).date().isoformat()}"
    try:
        result = get_email_alert_service().send_session_brief_now(str(job["session"]))
        marked = get_email_alert_service().mark_manual_brief_job_sent(
            job_key=str(job["job_key"]),
            title=str(job["label"]),
            category="manual_scheduled_brief",
            event_key=event_key,
            session_label=str(job["session"]),
        )
        return convert_numpy_types(
            {
                **result,
                "job_key": job["job_key"],
                "label": job["label"],
                "event_key": event_key,
                "marked": marked,
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/warm-brief")
async def warm_brief_now():
    """Precompute the market brief cache on demand.

    This is useful before a scheduled Telegram send or when the dashboard
    should become responsive immediately after a deploy/restart.
    """
    try:
        return convert_numpy_types(await _warm_brief_once())
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Brief warmup timed out.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/run-scheduled-briefs")
async def run_scheduled_briefs_now(include_missed: bool = False):
    """Run the scheduled brief dispatcher immediately.

    By default it only sends jobs that are due in the configured grace window.
    With include_missed=true it also catches up already missed jobs from today.
    """
    try:
        return convert_numpy_types(
            await asyncio.to_thread(
                get_email_alert_service().send_scheduled_open_briefs,
                include_missed,
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/performance-cache")
async def get_performance_cache_status():
    now = datetime.utcnow()
    entries = []
    for key, (created_at, payload) in sorted(_RESPONSE_CACHE.items()):
        entries.append(
            {
                "key": key,
                "age_seconds": int((now - created_at).total_seconds()),
                "shape": "dict" if isinstance(payload, dict) else "list" if isinstance(payload, list) else type(payload).__name__,
                "items": len(payload) if isinstance(payload, list) else len(payload.keys()) if isinstance(payload, dict) else None,
            }
        )
    return {"entries": entries, "count": len(entries)}


@app.get("/api/admin/telegram-diagnostics")
async def telegram_diagnostics():
    """Diagnose Telegram bot/chat configuration without exposing the token."""
    config = get_email_alert_service().get_config()
    result: Dict[str, Any] = {
        "telegram_enabled": config.telegram_enabled,
        "token_configured": bool(config.telegram_bot_token),
        "chat_id_configured": bool(config.telegram_chat_id),
        "configured_chat_id": config.telegram_chat_id or None,
        "bot": None,
        "configured_chat_sendable": None,
        "recent_chats": [],
        "next_steps": [],
    }
    if not config.telegram_enabled:
        result["next_steps"].append("Set TELEGRAM_ALERTS_ENABLED=true in Railway.")
    if not config.telegram_bot_token:
        result["next_steps"].append("Set TELEGRAM_BOT_TOKEN to the raw BotFather token.")
    if not config.telegram_chat_id:
        result["next_steps"].append("Set TELEGRAM_CHAT_ID to the chat id shown in recent_chats.")
    if not (config.telegram_bot_token and config.telegram_enabled):
        return result

    base_url = f"https://api.telegram.org/bot{config.telegram_bot_token}"

    def telegram_payload(method: str, **kwargs: Any) -> Dict[str, Any]:
        try:
            response = requests.request(
                kwargs.pop("http_method", "GET"),
                f"{base_url}/{method}",
                timeout=12,
                **kwargs,
            )
            try:
                payload = response.json()
            except Exception:
                payload = {"ok": False, "description": "Telegram returned a non-JSON response."}
            if not response.ok:
                return {
                    "ok": False,
                    "error_code": response.status_code,
                    "description": payload.get("description") or response.reason,
                }
            return payload
        except Exception as exc:
            return {"ok": False, "description": exc.__class__.__name__}

    me = telegram_payload("getMe")
    if me.get("ok") and isinstance(me.get("result"), dict):
        bot = me["result"]
        result["bot"] = {
            "id": bot.get("id"),
            "username": bot.get("username"),
            "first_name": bot.get("first_name"),
        }
    else:
        result["bot"] = me
        result["next_steps"].append("Bot token is not accepted by Telegram. Regenerate it in BotFather.")
        return result

    updates = telegram_payload("getUpdates", params={"limit": 20, "timeout": 0})
    chats: Dict[str, Dict[str, Any]] = {}
    if updates.get("ok") and isinstance(updates.get("result"), list):
        for update in updates["result"]:
            for key in ("message", "channel_post", "edited_message", "my_chat_member"):
                event = update.get(key)
                chat = event.get("chat") if isinstance(event, dict) else None
                if not isinstance(chat, dict) or chat.get("id") is None:
                    continue
                chat_id = str(chat.get("id"))
                chats[chat_id] = {
                    "chat_id": chat_id,
                    "type": chat.get("type"),
                    "title": chat.get("title") or chat.get("username") or chat.get("first_name"),
                }
    result["recent_chats"] = list(chats.values())[:10]

    if config.telegram_chat_id:
        send_check = telegram_payload(
            "sendChatAction",
            http_method="POST",
            json={"chat_id": config.telegram_chat_id, "action": "typing"},
        )
        if send_check.get("ok"):
            result["configured_chat_sendable"] = {"ok": True}
        else:
            result["configured_chat_sendable"] = send_check
            error_code = send_check.get("error_code")
            if error_code == 403:
                result["next_steps"].append(
                    "Open the bot in Telegram and send /start, or add it to the configured group/channel with send rights."
                )
            elif error_code == 400:
                result["next_steps"].append(
                    "TELEGRAM_CHAT_ID is wrong. Use one of recent_chats after sending /start to the bot."
                )

    if not result["recent_chats"]:
        result["next_steps"].append(
            "Send /start to the bot in Telegram, then reload this diagnostic endpoint so getUpdates can show the chat id."
        )
    return result

def _brief_schedule_jobs_for_health() -> List[Dict[str, str]]:
    return [
        {"job_key": "morning-brief", "label": "Morning Brief", "session": "global", "time": os.getenv("MORNING_BRIEF_TIME", DEFAULT_MORNING_BRIEF_TIME)},
        {"job_key": "open-brief:europe", "label": "Europe Open", "session": "europe", "time": os.getenv("EUROPE_OPEN_BRIEF_TIME", DEFAULT_EUROPE_OPEN_BRIEF_TIME)},
        {"job_key": "midday-brief", "label": "Midday Update", "session": "midday", "time": os.getenv("MIDDAY_BRIEF_TIME", DEFAULT_MIDDAY_BRIEF_TIME)},
        {"job_key": "open-brief:usa", "label": "US Open", "session": "usa", "time": os.getenv("US_OPEN_BRIEF_TIME", DEFAULT_US_OPEN_BRIEF_TIME)},
        {"job_key": "close-brief:europe", "label": "Europe Close", "session": "europe_close", "time": os.getenv("EUROPE_CLOSE_BRIEF_TIME", DEFAULT_EUROPE_CLOSE_BRIEF_TIME)},
        {"job_key": "close-recap", "label": "Daily Recap", "session": "close", "time": os.getenv("CLOSE_RECAP_TIME", DEFAULT_CLOSE_RECAP_TIME)},
        {"job_key": "close-brief:usa", "label": "US Close", "session": "usa_close", "time": os.getenv("US_CLOSE_BRIEF_TIME", DEFAULT_US_CLOSE_BRIEF_TIME)},
    ]


def _next_schedule_time(now: datetime, raw_time: str, weekdays: set[int]) -> datetime | None:
    try:
        hour, minute = [int(part) for part in str(raw_time).split(":", 1)]
    except Exception:
        return None
    for offset in range(0, 8):
        day = (now + timedelta(days=offset)).date()
        candidate = datetime.combine(day, datetime.min.time(), tzinfo=now.tzinfo).replace(hour=hour, minute=minute)
        if candidate.weekday() not in weekdays:
            continue
        if candidate > now:
            return candidate
    return None


def _schedule_time_for_day(now: datetime, raw_time: str) -> datetime | None:
    try:
        hour, minute = [int(part) for part in str(raw_time).split(":", 1)]
    except Exception:
        return None
    return datetime.combine(now.date(), datetime.min.time(), tzinfo=now.tzinfo).replace(hour=hour, minute=minute)


def _telegram_health_check() -> Dict[str, Any]:
    config = get_email_alert_service().get_config()
    config_fingerprint = hashlib.sha256(
        f"{config.telegram_enabled}:{config.telegram_bot_token}:{config.telegram_chat_id}".encode("utf-8")
    ).hexdigest()[:16]
    cache_key = f"health:telegram:{config_fingerprint}"
    cached = _cache_get(
        cache_key,
        _safe_int_env("HEALTH_TELEGRAM_CACHE_TTL_SECONDS", 60, minimum=15),
    )
    if cached is not None:
        return cached
    started = time.perf_counter()
    payload: Dict[str, Any] = {
        "enabled": config.telegram_enabled,
        "token_configured": bool(config.telegram_bot_token),
        "chat_id_configured": bool(config.telegram_chat_id),
        "chat_id": config.telegram_chat_id or None,
        "sendable": False,
        "status": "disabled" if not config.telegram_enabled else "missing_config",
        "error": None,
        "diagnosis": None,
        "next_step": None,
    }
    if not (config.telegram_enabled and config.telegram_bot_token and config.telegram_chat_id):
        record_provider_result(
            "telegram",
            "telegram_bot_api",
            "health_preflight",
            "disabled",
            latency_ms=(time.perf_counter() - started) * 1000,
            error_code="TELEGRAM_NOT_CONFIGURED",
        )
        return _cache_set(cache_key, payload)
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{config.telegram_bot_token}/sendChatAction",
            json={"chat_id": config.telegram_chat_id, "action": "typing"},
            timeout=_safe_int_env("HEALTH_TELEGRAM_TIMEOUT_SECONDS", 3, minimum=1),
        )
        if response.ok:
            payload.update({"sendable": True, "status": "ok", "diagnosis": "sendable", "next_step": None})
        else:
            body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            detail = body.get("description") if isinstance(body, dict) else response.text
            error_code = body.get("error_code") if isinstance(body, dict) else response.status_code
            diagnosis = "telegram_error"
            next_step = "Telegram bot settings in Railway pruefen."
            if response.status_code == 401 or error_code == 401:
                diagnosis = "invalid_bot_token"
                next_step = "TELEGRAM_BOT_TOKEN ist falsch oder enthaelt Prefix/Anfuehrungszeichen. Raw BotFather Token setzen."
            elif response.status_code == 403 or error_code == 403:
                diagnosis = "bot_not_allowed_for_chat"
                next_step = "Bot in Telegram mit /start aktivieren oder als Admin/Mitglied in Gruppe/Kanal hinzufuegen."
            elif response.status_code == 400 or error_code == 400:
                diagnosis = "invalid_chat_id"
                next_step = "TELEGRAM_CHAT_ID gegen /api/admin/telegram-diagnostics recent_chats abgleichen."
            payload.update({"status": "error", "error": detail or response.reason, "diagnosis": diagnosis, "next_step": next_step})
    except Exception as exc:
        payload.update({
            "status": "error",
            "error": exc.__class__.__name__,
            "diagnosis": "telegram_network_error",
            "next_step": "Railway outbound network / Telegram API Erreichbarkeit pruefen.",
        })
    record_provider_result(
        "telegram",
        "telegram_bot_api",
        "health_preflight",
        "ok" if payload.get("status") == "ok" else "error",
        latency_ms=(time.perf_counter() - started) * 1000,
        error_code=(
            None
            if payload.get("status") == "ok"
            else classify_provider_error(
                "telegram",
                http_status=(
                    int(error_code)
                    if "error_code" in locals() and str(error_code).isdigit()
                    else None
                ),
                detail=str(payload.get("diagnosis") or payload.get("error") or ""),
            )
        ),
        http_status=(
            int(error_code)
            if "error_code" in locals() and str(error_code).isdigit()
            else None
        ),
        error_type=str(payload.get("diagnosis") or "") or None,
    )
    return _cache_set(cache_key, payload)


def _market_feed_health_check() -> Dict[str, Any]:
    cache_key = "health:market-feeds"
    cached = _cache_get(
        cache_key,
        _safe_int_env("HEALTH_MARKET_FEEDS_CACHE_TTL_SECONDS", 60, minimum=15),
    )
    if cached is not None:
        return cached

    feeds: Dict[str, Any] = {}
    started = time.perf_counter()
    try:
        aapl = DataFetcher("AAPL").get_price_data()
        quote_status = "ok" if aapl.get("current_price") else "degraded"
        feeds["yfinance"] = {
            "status": quote_status,
            "sample": "AAPL",
            "price": aapl.get("current_price"),
        }
        record_provider_result(
            "quote",
            "yfinance",
            "health_quote",
            quote_status,
            latency_ms=(time.perf_counter() - started) * 1000,
            error_code=None if quote_status == "ok" else "QUOTE_INVALID_RESPONSE",
        )
    except Exception as exc:
        feeds["yfinance"] = {"status": "error", "error": exc.__class__.__name__}
        record_provider_result(
            "quote",
            "yfinance",
            "health_quote",
            "error",
            latency_ms=(time.perf_counter() - started) * 1000,
            error_code=classify_provider_error("quote", error=exc),
            error_type=exc.__class__.__name__,
        )
    realtime_required = _env_enabled("ALPACA_MARKET_DATA_ENABLED", "false")
    feeds["realtime_required"] = realtime_required
    if not realtime_required:
        feeds["realtime"] = {
            "status": "disabled",
            "reason": "alpaca_market_data_not_enabled",
            "quotes": 0,
            "stale_seconds": {},
        }
    else:
        started = time.perf_counter()
        try:
            snapshot = get_realtime_market_service().build_snapshot(["AAPL"])
            realtime_state = snapshot.get("connection_state") or "unknown"
            feeds["realtime"] = {
                "status": realtime_state,
                "quotes": len(snapshot.get("quotes") or []),
                "stale_seconds": snapshot.get("stale_seconds") or {},
            }
        except Exception as exc:
            feeds["realtime"] = {"status": "error", "error": exc.__class__.__name__}
            record_provider_result(
                "quote",
                "realtime_aggregator",
                "health_snapshot",
                "error",
                latency_ms=(time.perf_counter() - started) * 1000,
                error_code=classify_provider_error("quote", error=exc),
                error_type=exc.__class__.__name__,
            )
    return _cache_set(cache_key, feeds)


def _news_feed_health_check() -> Dict[str, Any]:
    cache_key = "health:news-feed"
    cached = _cache_get(
        cache_key,
        _safe_int_env("HEALTH_NEWS_CACHE_TTL_SECONDS", 60, minimum=15),
    )
    if cached is not None:
        return cached
    started = time.perf_counter()
    try:
        brief = get_morning_brief_service().get_cached_or_last_brief() or {}
        news_items = brief.get("top_news") or []
        data_status = brief.get("data_status") or {}
        sources = data_status.get("sources") or {}
        status = "ok" if news_items else "degraded"
        payload = {
            "status": status,
            "items": len(news_items),
            "generated_at": brief.get("generated_at"),
            "sources": sources,
        }
        record_provider_result(
            "news",
            "morning_brief",
            "cached_news_snapshot",
            status,
            latency_ms=(time.perf_counter() - started) * 1000,
            error_code=None if status == "ok" else "NEWS_EMPTY_RESPONSE",
        )
    except Exception as exc:
        payload = {"status": "error", "error": exc.__class__.__name__}
        record_provider_result(
            "news",
            "morning_brief",
            "cached_news_snapshot",
            "error",
            latency_ms=(time.perf_counter() - started) * 1000,
            error_code=classify_provider_error("news", error=exc),
            error_type=exc.__class__.__name__,
        )
    return _cache_set(cache_key, payload)


@app.get("/api/admin/decision-audit")
async def get_decision_audit(limit: int = 100):
    try:
        manager = get_portfolio_manager()
        return convert_numpy_types(
            {
                "schema": "decision-audit.v1",
                "chain": manager.verify_decision_audit_chain(),
                "entries": manager.list_decision_audit(limit=limit),
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/health-center")
async def admin_health_center():
    """Operational health for launch: delivery, scheduler and data feeds."""
    now_utc = datetime.utcnow()
    tz_name = os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Europe/Berlin")
        tz_name = "Europe/Berlin"
    now_local = datetime.now(tz)
    notification_status = get_email_alert_service().get_notification_status()
    production_soak = read_production_soak(get_portfolio_manager(), now_utc.replace(tzinfo=timezone.utc))
    database_status = get_database_status()
    backup_status = get_database_backup_service().status()
    backup_status.update(
        {
            "last_success_at": get_portfolio_manager().get_app_setting("database_backup_last_success_at"),
            "last_error": get_portfolio_manager().get_app_setting("database_backup_last_error"),
            "restore_test_last_success_at": get_portfolio_manager().get_app_setting("database_restore_test_last_success_at"),
            "restore_test_last_error": get_portfolio_manager().get_app_setting("database_restore_test_last_error"),
            "interval_hours": _safe_int_env("APP_BACKUP_INTERVAL_HOURS", 24, minimum=1),
            "restore_test_interval_days": _safe_int_env("APP_RESTORE_TEST_INTERVAL_DAYS", 7, minimum=1),
        }
    )
    schedule_status = notification_status.get("schedule", {})
    on_time_window_minutes = int(schedule_status.get("on_time_window_minutes") or 30)
    grace_minutes = int(schedule_status.get("delivery_grace_minutes") or 720)
    sent_events = get_portfolio_manager().get_sent_signal_events(limit=80)
    sent_keys = {event.get("event_key") for event in sent_events}
    weekdays_raw = os.getenv("BRIEF_SCHEDULE_WEEKDAYS", "mon,tue,wed,thu,fri").lower().split(",")
    weekday_map = {"mon": 0, "monday": 0, "tue": 1, "tuesday": 1, "wed": 2, "wednesday": 2, "thu": 3, "thursday": 3, "fri": 4, "friday": 4, "sat": 5, "saturday": 5, "sun": 6, "sunday": 6}
    weekdays = {weekday_map.get(day.strip(), 0) for day in weekdays_raw if day.strip()}
    if not weekdays:
        weekdays = {0, 1, 2, 3, 4}

    schedule_jobs = []
    alert_service = get_email_alert_service()
    for job in _brief_schedule_jobs_for_health():
        event_key = f"{job['job_key']}:{now_local.date().isoformat()}"
        last_event = next((event for event in sent_events if str(event.get("event_key", "")).startswith(job["job_key"])), None)
        job_status = alert_service.get_brief_job_status(job["job_key"])
        scheduled_today = _schedule_time_for_day(now_local, job["time"])
        next_due = _next_schedule_time(now_local, job["time"], weekdays)
        minutes_late = (
            max(0, int((now_local - scheduled_today).total_seconds() // 60))
            if scheduled_today and now_local >= scheduled_today
            else None
        )
        on_time_until = scheduled_today + timedelta(minutes=on_time_window_minutes) if scheduled_today else None
        grace_until = scheduled_today + timedelta(minutes=grace_minutes) if scheduled_today else None
        sent_today = event_key in sent_keys
        due_now = (
            bool(scheduled_today)
            and now_local.weekday() in weekdays
            and not sent_today
            and now_local >= scheduled_today
            and bool(on_time_until)
            and now_local < on_time_until
        )
        catchup_available = (
            bool(scheduled_today)
            and now_local.weekday() in weekdays
            and not sent_today
            and now_local >= scheduled_today
            and bool(grace_until)
            and now_local < grace_until
        )
        missed_today = (
            bool(scheduled_today)
            and now_local.weekday() in weekdays
            and not sent_today
            and bool(grace_until)
            and now_local >= grace_until
        )
        schedule_jobs.append(
            {
                **job,
                "sent_today": sent_today,
                "due_now": due_now,
                "missed_today": missed_today,
                "scheduled_at_today": scheduled_today.isoformat() if scheduled_today else None,
                "event_key_today": event_key,
                "last_sent_at": last_event.get("sent_at") if last_event else None,
                "last_success_at": job_status.get("last_success_at") or (last_event.get("sent_at") if last_event else None),
                "last_error": job_status.get("last_error"),
                "last_message": job_status.get("message"),
                "last_status": job_status.get("status"),
                "last_status_updated_at": job_status.get("updated_at"),
                "next_due_at": next_due.isoformat() if next_due else None,
                "minutes_late": minutes_late,
                "on_time_until": on_time_until.isoformat() if on_time_until else None,
                "grace_until": grace_until.isoformat() if grace_until else None,
                "catchup_available": catchup_available,
            }
        )

    brief_snapshot = get_morning_brief_service().get_cached_or_last_brief()
    data_feeds: Dict[str, Any] = {
        "morning_brief": {
            "status": "ok" if brief_snapshot else "missing",
            "generated_at": brief_snapshot.get("generated_at") if brief_snapshot else None,
            "quality": brief_snapshot.get("quality") if brief_snapshot else None,
        }
    }
    telegram, market_feed_status, news_feed_status = await asyncio.gather(
        asyncio.to_thread(_telegram_health_check),
        asyncio.to_thread(_market_feed_health_check),
        asyncio.to_thread(_news_feed_health_check),
    )
    data_feeds.update(market_feed_status)
    data_feeds["news"] = news_feed_status

    try:
        learning_dashboard = get_forecast_learning_service().build_dashboard()
        learning_last_result_raw = get_portfolio_manager().get_app_setting(
            "forecast_learning_last_result",
            "{}",
        )
        try:
            learning_last_result = json.loads(learning_last_result_raw or "{}")
        except Exception:
            learning_last_result = {}
        data_feeds["forecast_learning"] = {
            "status": "ok",
            "summary": learning_dashboard.get("summary"),
            "last_result": learning_last_result,
        }
    except Exception as exc:
        learning_dashboard = {"summary": {}}
        data_feeds["forecast_learning"] = {"status": "error", "error": exc.__class__.__name__}
    try:
        paper_learning_v2_dashboard = get_paper_trading_service().paper_learning.build_dashboard()
        raw_paper_learning_v2 = get_portfolio_manager().get_app_setting("paper_learning_v2_last_result", "{}")
        paper_learning_v2_last = json.loads(raw_paper_learning_v2 or "{}")
        if not isinstance(paper_learning_v2_last, dict):
            paper_learning_v2_last = {}
        paper_learning_v2_operations = paper_learning_v2_dashboard.get("operations") or {}
        paper_learning_v2_age = (paper_learning_v2_operations.get("last_run") or {}).get("age_minutes")
        paper_learning_v2_stale_after = _safe_int_env("PAPER_LEARNING_V2_STALE_AFTER_MINUTES", 360, minimum=30)
        paper_learning_v2_stale = bool(
            paper_learning_v2_age is not None
            and int(paper_learning_v2_age) > paper_learning_v2_stale_after
        )
        paper_learning_v2_run_status = str(paper_learning_v2_last.get("status") or "not_started")
        data_feeds["paper_learning_v2"] = {
            "status": (
                "error"
                if paper_learning_v2_run_status == "error"
                else "stuck"
                if paper_learning_v2_run_status == "running" and paper_learning_v2_stale
                else "stale"
                if paper_learning_v2_stale
                else paper_learning_v2_run_status
                if paper_learning_v2_run_status in {"running", "not_started"}
                else "ok"
            ),
            "summary": paper_learning_v2_dashboard.get("summary") or {},
            "operations": paper_learning_v2_operations,
            "last_result": paper_learning_v2_last,
            "age_minutes": paper_learning_v2_age,
            "stale": paper_learning_v2_stale,
            "stale_after_minutes": paper_learning_v2_stale_after,
            "last_error": get_portfolio_manager().get_app_setting("paper_learning_v2_last_error", ""),
            "paper_only": True,
        }
    except Exception as exc:
        paper_learning_v2_dashboard = {"summary": {}, "hypotheses": [], "rules": []}
        paper_learning_v2_last = {"status": "error", "error": str(exc)}
        paper_learning_v2_run_status = "error"
        paper_learning_v2_stale = False
        data_feeds["paper_learning_v2"] = {"status": "error", "error": exc.__class__.__name__}

    scheduler_last_checked_at = get_portfolio_manager().get_app_setting("brief_scheduler_last_checked_at")
    scheduler_loop_seen_at = get_portfolio_manager().get_app_setting("brief_scheduler_loop_seen_at")
    scheduler_loop_error = get_portfolio_manager().get_app_setting("brief_scheduler_loop_error")
    scheduler_step_error = get_portfolio_manager().get_app_setting("brief_scheduler_last_step_error")
    loop_age_minutes = None
    if scheduler_loop_seen_at:
        try:
            loop_seen_dt = datetime.fromisoformat(str(scheduler_loop_seen_at).replace("Z", "+00:00"))
            if loop_seen_dt.tzinfo is not None:
                loop_seen_dt = loop_seen_dt.astimezone(timezone.utc).replace(tzinfo=None)
            loop_age_minutes = max(0, int((now_utc - loop_seen_dt).total_seconds() // 60))
        except Exception:
            loop_age_minutes = None
    loop_stale_after_minutes = _safe_int_env("BRIEF_SCHEDULER_STALE_AFTER_MINUTES", 20, minimum=5)
    scheduler_loop_stale = (
        bool(notification_status.get("schedule", {}).get("enabled"))
        and (loop_age_minutes is None or loop_age_minutes > loop_stale_after_minutes)
    )
    raw_scheduler_result = get_portfolio_manager().get_app_setting("brief_scheduler_last_result", "[]")
    try:
        scheduler_last_result = json.loads(raw_scheduler_result or "[]")
    except Exception:
        scheduler_last_result = []
    raw_operational_alerts = get_portfolio_manager().get_app_setting("operational_alerts_last_result", "{}")
    try:
        operational_alerts = json.loads(raw_operational_alerts or "{}")
        if not isinstance(operational_alerts, dict):
            operational_alerts = {}
    except Exception:
        operational_alerts = {}
    paper_autopilot_enabled = _env_enabled("PAPER_TRADING_AUTO_LEARN_ENABLED", "true")
    forecast_loop_enabled = _env_enabled("FORECAST_LEARNING_ENABLED", "true")
    paper_autopilot_raw = get_portfolio_manager().get_app_setting("paper_learning_autopilot_last_run", "{}")
    try:
        paper_autopilot_last = json.loads(paper_autopilot_raw or "{}")
        if not isinstance(paper_autopilot_last, dict):
            paper_autopilot_last = {}
    except Exception:
        paper_autopilot_last = {}
    paper_autopilot_checked_at = paper_autopilot_last.get("checked_at")
    paper_autopilot_age_minutes = None
    paper_autopilot_checked_dt = None
    if paper_autopilot_checked_at:
        try:
            paper_autopilot_checked_dt = datetime.fromisoformat(str(paper_autopilot_checked_at).replace("Z", "+00:00"))
            if paper_autopilot_checked_dt.tzinfo is not None:
                paper_autopilot_checked_dt = paper_autopilot_checked_dt.astimezone(timezone.utc).replace(tzinfo=None)
            paper_autopilot_age_minutes = max(
                0,
                int((now_utc - paper_autopilot_checked_dt).total_seconds() // 60),
            )
        except Exception:
            paper_autopilot_checked_dt = None
    paper_autopilot_opened = paper_autopilot_last.get("opened") or []
    paper_autopilot_selected = paper_autopilot_last.get("selected") or []

    def _paper_autopilot_item_summary(item: Any) -> Dict[str, Any]:
        if not isinstance(item, dict):
            return {}
        return {
            "ticker": item.get("ticker"),
            "asset_class": item.get("asset_class"),
            "direction": item.get("direction"),
            "setup_type": item.get("setup_type"),
            "score": item.get("score") or item.get("confidence_score"),
            "entry_price": item.get("entry_price") or item.get("reference_price"),
            "notional_value": item.get("suggested_notional_value") or item.get("notional_value"),
            "max_loss_value": item.get("suggested_max_loss_value") or item.get("max_loss_value"),
            "thesis": item.get("thesis"),
        }

    paper_autopilot_last_selected = [
        summary
        for summary in (_paper_autopilot_item_summary(item) for item in paper_autopilot_selected[:3])
        if summary.get("ticker")
    ]
    paper_autopilot_last_opened = [
        summary
        for summary in (_paper_autopilot_item_summary(item) for item in paper_autopilot_opened[:3])
        if summary.get("ticker")
    ]
    paper_autopilot_demo_account = paper_autopilot_last.get("demo_account_after") or {}
    if not isinstance(paper_autopilot_demo_account, dict):
        paper_autopilot_demo_account = {}

    paper_autopilot_cooldown = (
        _safe_int_env("PAPER_TRADING_AUTO_LEARN_COOLDOWN_MINUTES", 360, minimum=30)
        if paper_autopilot_opened
        else _safe_int_env("PAPER_TRADING_AUTO_LEARN_EMPTY_COOLDOWN_MINUTES", 30, minimum=5)
    )
    forecast_interval = _safe_int_env("FORECAST_OUTCOME_INTERVAL_MINUTES", 30, minimum=5)
    paper_autopilot_stale_after = paper_autopilot_cooldown + (forecast_interval * 2)
    paper_autopilot_stale = bool(
        paper_autopilot_enabled
        and forecast_loop_enabled
        and paper_autopilot_age_minutes is not None
        and paper_autopilot_age_minutes > paper_autopilot_stale_after
    )
    paper_autopilot_next_check_at = (
        (paper_autopilot_checked_dt + timedelta(minutes=paper_autopilot_cooldown)).isoformat()
        if paper_autopilot_checked_dt
        else None
    )
    paper_autopilot_status = str(paper_autopilot_last.get("status") or "not_started")
    paper_autopilot_blocker = paper_autopilot_last.get("blocker_summary") or {}
    next_blocked_candidate = paper_autopilot_blocker.get("next_best_rejected") or {}
    raw_block_reasons = next_blocked_candidate.get("display_reasons") or next_blocked_candidate.get("reasons") or []
    paper_autopilot_block_reasons = list(
        dict.fromkeys(str(reason).strip() for reason in raw_block_reasons if str(reason).strip())
    )[:3]
    paper_autopilot_next_candidate = _paper_autopilot_item_summary(next_blocked_candidate)
    try:
        paper_outcome_dashboard = get_paper_trading_service()._build_outcome_dashboard()
    except Exception as exc:
        paper_outcome_dashboard = {
            "summary": {},
            "top_errors": [],
            "recent": [],
            "error": str(exc),
        }
    raw_paper_outcome_last_result = get_portfolio_manager().get_app_setting("paper_trade_outcomes_last_result", "{}")
    try:
        paper_outcome_last_result = json.loads(raw_paper_outcome_last_result or "{}")
        if not isinstance(paper_outcome_last_result, dict):
            paper_outcome_last_result = {}
    except Exception:
        paper_outcome_last_result = {}
    paper_outcome_summary = paper_outcome_dashboard.get("summary") or {}
    paper_outcome_last_checked_at = paper_outcome_last_result.get("checked_at")
    paper_outcome_age_minutes = None
    paper_outcome_checked_dt = None
    if paper_outcome_last_checked_at:
        try:
            paper_outcome_checked_dt = datetime.fromisoformat(str(paper_outcome_last_checked_at).replace("Z", "+00:00"))
            if paper_outcome_checked_dt.tzinfo is not None:
                paper_outcome_checked_dt = paper_outcome_checked_dt.astimezone(timezone.utc).replace(tzinfo=None)
            paper_outcome_age_minutes = max(
                0,
                int((now_utc - paper_outcome_checked_dt).total_seconds() // 60),
            )
        except Exception:
            paper_outcome_checked_dt = None
    try:
        paper_outcome_pending = int(paper_outcome_summary.get("pending") or 0)
    except (TypeError, ValueError):
        paper_outcome_pending = 0
    paper_outcome_stale_after = _safe_int_env("PAPER_OUTCOME_STALE_AFTER_MINUTES", 360, minimum=30)
    paper_outcome_pending_warn = _safe_int_env("PAPER_OUTCOME_PENDING_WARN_COUNT", 10, minimum=1)
    paper_outcome_last_errors = paper_outcome_last_result.get("errors") or []
    paper_outcome_last_status = str(paper_outcome_last_result.get("status") or "not_started")
    paper_outcome_stale = bool(
        paper_autopilot_enabled
        and forecast_loop_enabled
        and paper_outcome_age_minutes is not None
        and paper_outcome_age_minutes > paper_outcome_stale_after
    )
    decision_audit_status = get_portfolio_manager().verify_decision_audit_chain()
    compliance_status = get_compliance_status()
    alpaca_paper_broker_health = _alpaca_paper_broker_health()
    broker_reconciliation_status = BrokerReconciliationService().status()
    problems = []
    if telegram.get("status") != "ok":
        problems.append("telegram")
    if data_feeds.get("yfinance", {}).get("status") not in {"ok"}:
        problems.append("yfinance")
    if not notification_status.get("schedule", {}).get("enabled"):
        problems.append("schedule_disabled")
    if not database_status.get("exists"):
        problems.append("database_missing")
    if database_status.get("quick_check") not in {None, "ok"}:
        problems.append("database_integrity")
    if not database_status.get("writable"):
        problems.append("database_not_writable")
    if database_status.get("railway_runtime") and not database_status.get("persistence_ready"):
        problems.append("database_volume_missing")
    if backup_status.get("enabled") and not backup_status.get("latest_at"):
        problems.append("backup_missing")
    if backup_status.get("enabled") and backup_status.get("latest_age_hours") is not None and float(backup_status["latest_age_hours"]) > float(backup_status["interval_hours"] + 6):
        problems.append("backup_stale")
    if backup_status.get("last_error"):
        problems.append("backup_error")
    if backup_status.get("restore_test_last_error"):
        problems.append("restore_test_error")
    if backup_status.get("enabled") and not backup_status.get("restore_test_last_success_at"):
        problems.append("restore_test_missing")
    if notification_status.get("schedule", {}).get("enabled") and not scheduler_loop_seen_at:
        problems.append("scheduler_not_seen")
    if scheduler_loop_stale:
        problems.append("scheduler_loop_stale")
    if scheduler_loop_error or scheduler_step_error:
        problems.append("scheduler_error")
    if any(job.get("missed_today") for job in schedule_jobs):
        problems.append("brief_missed_today")
    if any(job.get("catchup_available") for job in schedule_jobs):
        problems.append("brief_catchup_available")
    if any(job.get("last_status") == "blocked" for job in schedule_jobs):
        problems.append("brief_quality_blocked")
    if paper_autopilot_enabled and not forecast_loop_enabled:
        problems.append("paper_autopilot_loop_disabled")
    if paper_autopilot_enabled and not paper_autopilot_checked_at:
        problems.append("paper_autopilot_not_seen")
    if paper_autopilot_status == "error":
        problems.append("paper_autopilot_error")
    if paper_autopilot_stale:
        problems.append("paper_autopilot_stale")
    if paper_autopilot_enabled and not paper_outcome_last_checked_at:
        problems.append("paper_outcomes_not_seen")
    if paper_outcome_last_status == "error" or paper_outcome_last_errors:
        problems.append("paper_outcomes_error")
    if paper_outcome_stale:
        problems.append("paper_outcomes_stale")
    if paper_outcome_pending >= paper_outcome_pending_warn:
        problems.append("paper_outcomes_backlog")
    if paper_learning_v2_run_status == "error":
        problems.append("paper_learning_v2_error")
    if data_feeds.get("paper_learning_v2", {}).get("status") == "stuck":
        problems.append("paper_learning_v2_stuck")
    elif paper_learning_v2_stale:
        problems.append("paper_learning_v2_stale")
    if paper_autopilot_enabled and paper_learning_v2_run_status == "not_started":
        problems.append("paper_learning_v2_not_seen")
    if decision_audit_status.get("valid") is not True:
        problems.append("decision_audit_invalid")
    if compliance_status.get("request_allowed") is not True:
        problems.append("external_compliance_blocked")
    if alpaca_paper_broker_health.get("enabled") is True and broker_reconciliation_status.get("trade_allowed") is not True:
        problems.append("broker_reconciliation_blocked")
    overall = "ok" if not problems else "degraded"
    next_job = next(
        (
            job
            for job in sorted(
                [item for item in schedule_jobs if item.get("next_due_at")],
                key=lambda item: str(item.get("next_due_at")),
            )
        ),
        None,
    )
    last_success_job = next(
        (
            job
            for job in sorted(
                [item for item in schedule_jobs if item.get("last_success_at")],
                key=lambda item: str(item.get("last_success_at")),
                reverse=True,
            )
        ),
        None,
    )
    last_error_job = next(
        (
            job
            for job in sorted(
                [item for item in schedule_jobs if item.get("last_error")],
                key=lambda item: str(item.get("last_status_updated_at") or item.get("last_success_at") or ""),
                reverse=True,
            )
        ),
        None,
    )
    due_now_jobs = [job for job in schedule_jobs if job.get("due_now")]
    catchup_jobs = [job for job in schedule_jobs if job.get("catchup_available")]
    missed_jobs = [job for job in schedule_jobs if job.get("missed_today")]
    return convert_numpy_types(
        {
            "status": overall,
            "generated_at": now_utc.isoformat(),
            "timezone": tz_name,
            "telegram": telegram,
            "notifications": notification_status,
            "app": {
                "version": APP_VERSION,
                "environment": os.getenv("APP_ENV", "development"),
                "release": get_release_identity(),
                "cookie_secure": use_secure_cookies(),
                "allowed_origins": allowed_origins,
                "auth_configured": bool(get_app_password() and get_session_secret()),
            },
            "database": database_status,
            "backup": backup_status,
            "operational_alerts": operational_alerts,
            "provider_metrics": provider_metrics_snapshot(),
            "alpaca_stream": _alpaca_stream_health(),
            "alpaca_paper_broker": alpaca_paper_broker_health,
            "broker_reconciliation": broker_reconciliation_status,
            "fast_paper_safety": FastPaperSafetyService(get_portfolio_manager()).status(),
            "latency_monitor": LatencyMonitorService().snapshot(
                window_minutes=_safe_int_env("LATENCY_MONITOR_WINDOW_MINUTES", 60, minimum=1)
            ),
            "production_soak": production_soak,
            "decision_audit": decision_audit_status,
            "compliance": compliance_status,
            "schedule": {
                "enabled": notification_status.get("schedule", {}).get("enabled"),
                "weekdays": os.getenv("BRIEF_SCHEDULE_WEEKDAYS", "mon,tue,wed,thu,fri"),
                "last_checked_at": scheduler_last_checked_at,
                "loop_seen_at": scheduler_loop_seen_at,
                "loop_completed_at": get_portfolio_manager().get_app_setting("brief_scheduler_loop_completed_at"),
                "loop_next_tick_at": get_portfolio_manager().get_app_setting("brief_scheduler_loop_next_tick_at"),
                "loop_age_minutes": loop_age_minutes,
                "loop_stale_after_minutes": loop_stale_after_minutes,
                "loop_stale": scheduler_loop_stale,
                "loop_error": scheduler_loop_error,
                "last_step_error": scheduler_step_error,
                "last_result": scheduler_last_result,
                "on_time_window_minutes": on_time_window_minutes,
                "delivery_grace_minutes": grace_minutes,
                "summary": {
                    "next_job_key": next_job.get("job_key") if next_job else None,
                    "next_label": next_job.get("label") if next_job else None,
                    "next_due_at": next_job.get("next_due_at") if next_job else None,
                    "last_success_job": last_success_job.get("label") if last_success_job else None,
                    "last_success_at": last_success_job.get("last_success_at") if last_success_job else None,
                    "last_error_job": last_error_job.get("label") if last_error_job else None,
                    "last_error": last_error_job.get("last_error") if last_error_job else None,
                    "last_error_at": last_error_job.get("last_status_updated_at") if last_error_job else None,
                    "due_now_count": len(due_now_jobs),
                    "catchup_count": len(catchup_jobs),
                    "catchup_jobs": [job.get("label") for job in catchup_jobs],
                    "missed_count": len(missed_jobs),
                    "loop_state": "stale" if scheduler_loop_stale else "seen" if scheduler_loop_seen_at else "not_seen",
                    "needs_manual_run": bool(catchup_jobs) or bool(due_now_jobs),
                },
                "jobs": schedule_jobs,
            },
            "learning": learning_dashboard,
            "paper_learning_v2": paper_learning_v2_dashboard,
            "paper_autopilot": {
                "enabled": paper_autopilot_enabled,
                "loop_enabled": forecast_loop_enabled,
                "status": paper_autopilot_status if paper_autopilot_enabled else "disabled",
                "checked_at": (
                    paper_autopilot_checked_dt.replace(tzinfo=timezone.utc).isoformat()
                    if paper_autopilot_checked_dt
                    else None
                ),
                "age_minutes": paper_autopilot_age_minutes,
                "stale_after_minutes": paper_autopilot_stale_after,
                "stale": paper_autopilot_stale,
                "next_check_at": paper_autopilot_next_check_at,
                "cooldown_minutes": paper_autopilot_cooldown,
                "opened_count": len(paper_autopilot_opened),
                "selected_count": len(paper_autopilot_selected),
                "last_selected": paper_autopilot_last_selected,
                "last_opened": paper_autopilot_last_opened,
                "demo_account_after": {
                    "starting_capital": paper_autopilot_demo_account.get("starting_capital"),
                    "equity_value": paper_autopilot_demo_account.get("equity_value") or paper_autopilot_demo_account.get("equity"),
                    "cash_available_value": paper_autopilot_demo_account.get("cash_available_value"),
                    "open_exposure_value": paper_autopilot_demo_account.get("open_exposure_value"),
                    "net_pnl_value": paper_autopilot_demo_account.get("net_pnl_value"),
                    "net_pnl_pct": paper_autopilot_demo_account.get("net_pnl_pct"),
                    "performance": paper_autopilot_demo_account.get("performance") or {},
                },
                "mode": paper_autopilot_last.get("mode"),
                "message": paper_autopilot_last.get("message"),
                "next_candidate": next_blocked_candidate.get("ticker"),
                "next_candidate_summary": paper_autopilot_next_candidate if paper_autopilot_next_candidate.get("ticker") else None,
                "block_reasons": paper_autopilot_block_reasons,
            },
            "paper_outcomes": {
                "status": (
                    "error"
                    if paper_outcome_last_status == "error" or paper_outcome_last_errors
                    else "stale"
                    if paper_outcome_stale
                    else "backlog"
                    if paper_outcome_pending >= paper_outcome_pending_warn
                    else "not_seen"
                    if paper_autopilot_enabled and not paper_outcome_last_checked_at
                    else "ok"
                ),
                "age_minutes": paper_outcome_age_minutes,
                "stale": paper_outcome_stale,
                "stale_after_minutes": paper_outcome_stale_after,
                "pending_warn_count": paper_outcome_pending_warn,
                "summary": {
                    "total": paper_outcome_summary.get("total", 0),
                    "evaluated": paper_outcome_summary.get("evaluated", 0),
                    "pending": paper_outcome_pending,
                    "hit_rate": paper_outcome_summary.get("hit_rate", 0),
                    "misses": paper_outcome_summary.get("misses", 0),
                },
                "top_errors": (paper_outcome_dashboard.get("top_errors") or [])[:4],
                "recent": (paper_outcome_dashboard.get("recent") or [])[:5],
                "last_run": {
                    "checked_at": paper_outcome_last_result.get("checked_at"),
                    "status": paper_outcome_last_result.get("status"),
                    "due": paper_outcome_last_result.get("due"),
                    "evaluated": paper_outcome_last_result.get("evaluated"),
                    "pending_data": paper_outcome_last_result.get("pending_data"),
                    "errors": paper_outcome_last_result.get("errors") or [],
                    "telegram_status": (paper_outcome_last_result.get("paper_learning_alerts") or {}).get("status"),
                },
                "error": paper_outcome_dashboard.get("error"),
            },
            "data_feeds": data_feeds,
            "recent_deliveries": sent_events[:12],
            "problems": problems,
        }
    )


@app.get("/api/admin/backup/portfolio-db")
async def download_portfolio_db_backup():
    """Create and download a consistent SQLite online backup."""
    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=404, detail="Portfolio database not found.")
    try:
        result = await asyncio.to_thread(get_database_backup_service().create_backup)
        get_portfolio_manager().set_app_setting("database_backup_last_success_at", result["created_at"])
        get_portfolio_manager().set_app_setting("database_backup_last_result", json.dumps(result))
        get_portfolio_manager().set_app_setting("database_backup_last_error", "")
    except Exception as exc:
        get_portfolio_manager().set_app_setting("database_backup_last_error", f"{exc.__class__.__name__}: {exc}")
        raise HTTPException(status_code=500, detail="Consistent database backup failed.") from exc
    return FileResponse(
        result["path"],
        media_type="application/vnd.sqlite3",
        filename=result["filename"],
    )


@app.post("/api/admin/backup/run")
async def run_database_backup():
    try:
        return await asyncio.to_thread(_run_backup_cycle, True, False)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database backup failed: {exc}") from exc


@app.post("/api/admin/backup/verify-restore")
async def verify_database_restore():
    try:
        return await asyncio.to_thread(_run_backup_cycle, False, True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Restore verification failed: {exc}") from exc

@app.get("/api/signals/scoreboard")
async def get_signal_scoreboard():
    try:
        cached = _cache_get("signals:scoreboard", int(os.getenv("SIGNAL_SCOREBOARD_CACHE_TTL_SECONDS", "90")))
        if cached is not None:
            return convert_numpy_types(cached)
        items = get_portfolio_manager().get_signal_watch_items()
        snapshot = get_public_signal_service().build_watchlist_snapshot(items)
        settings = get_portfolio_manager().get_signal_score_settings()
        scoreboard = await get_signal_score_service().build_scoreboard(snapshot, settings)
        return convert_numpy_types(_cache_set("signals:scoreboard", scoreboard))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trading/paper-dashboard")
async def get_paper_trading_dashboard():
    try:
        items = get_portfolio_manager().get_signal_watch_items()
        snapshot = get_public_signal_service().build_watchlist_snapshot(items)
        settings = get_portfolio_manager().get_signal_score_settings()
        scoreboard = await get_signal_score_service().build_scoreboard(snapshot, settings)
        news_context = _get_paper_news_context(snapshot)
        dashboard = get_paper_trading_service().build_dashboard(scoreboard, settings, news_context)
        scoped_dashboard = attach_scope(dashboard, paper_scope())
        audited_dashboard = _audit_and_attach(
            scoped_dashboard,
            event_type="recommendation_snapshot",
            subject="paper-dashboard",
            decision=str((dashboard.get("paper_autopilot_profile") or {}).get("recommendation_tone") or "paper_review"),
            data_as_of=dashboard.get("generated_at"),
            source_status=str((scoreboard.get("meta") or {}).get("status") or "mixed_sources"),
            model_version="paper-dashboard.v2",
            rule_version="paper-risk-and-selection.v2",
            user_action="paper_dashboard_requested",
            audit_payload={
                "generated_at": dashboard.get("generated_at"),
                "playbooks": dashboard.get("playbooks") or [],
                "strategy_readiness": dashboard.get("strategy_readiness") or [],
                "strategy_candidate_coverage": dashboard.get("strategy_candidate_coverage") or [],
                "paper_autopilot_profile": dashboard.get("paper_autopilot_profile") or {},
                "rules": dashboard.get("rules") or {},
                "decision_scope": scoped_dashboard.get("decision_scope"),
            },
        )
        return convert_numpy_types(audited_dashboard)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/trading/paper-outcomes/evaluate")
async def evaluate_paper_trade_outcomes():
    try:
        result = await _run_paper_outcome_cycle(force_alerts=True)
        return convert_numpy_types(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trading/paper-learning-v2")
async def get_paper_learning_v2_dashboard():
    try:
        payload = get_paper_trading_service().paper_learning.build_dashboard()
        return convert_numpy_types(attach_scope(payload, paper_scope()))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trading/paper-learning-v2/trades/{trade_id}")
async def get_paper_learning_v2_trade_detail(trade_id: str):
    try:
        payload = get_paper_trading_service().paper_learning.build_trade_detail(trade_id)
        return convert_numpy_types(attach_scope(payload, paper_scope()))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trading/paper-learning-v2/refresh")
async def refresh_paper_learning_v2():
    try:
        result = await asyncio.to_thread(get_paper_trading_service().paper_learning.refresh_learning_state)
        return convert_numpy_types(attach_scope(result, paper_scope()))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trading/paper-learning-v2/rules/{rule_id}/rollback-preview")
async def preview_paper_learning_v2_rule_rollback(rule_id: str):
    try:
        result = get_paper_trading_service().paper_learning.rollback_preview(rule_id)
        return convert_numpy_types(attach_scope(result, paper_scope()))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trading/paper-learning-v2/rules/{rule_id}/action")
async def review_paper_learning_v2_rule(rule_id: str, req: PaperLearningRuleActionRequest):
    try:
        result = get_paper_trading_service().paper_learning.review_rule(
            rule_id,
            req.action,
            req.reason or "",
        )
        return convert_numpy_types(attach_scope(result, paper_scope()))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trading/intelligence")
async def get_trading_intelligence():
    try:
        items = get_portfolio_manager().get_signal_watch_items()
        snapshot = get_public_signal_service().build_watchlist_snapshot(items)
        payload = get_trading_intelligence_service().build_snapshot(snapshot)
        return convert_numpy_types(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trading/strategy-library")
async def get_strategy_library():
    try:
        trades = get_paper_trading_service()._enrich_trades(get_portfolio_manager().list_paper_trades(limit=300))
        outcomes = get_portfolio_manager().list_paper_trade_outcomes(limit=800)
        return convert_numpy_types(
            {
                "status": "ok",
                "generated_at": datetime.utcnow().isoformat(),
                "strategies": StrategyLibrary.all(),
                "readiness": [
                    attach_scope(row, scope_for_strategy_status(row.get("status")))
                    for row in StrategyLibrary.build_readiness(trades, outcomes)
                ],
                "decision_scope": paper_scope(),
                "policy": "Paper-Lernen zuerst. Echtgeld-Nutzung erfordert manuelle Prüfung und dokumentiertes Risiko.",
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trading/broker-paper/status")
async def get_broker_paper_status():
    reconciliation = BrokerReconciliationService().status()
    return convert_numpy_types(
        {
            "broker": _alpaca_paper_broker_health(),
            "reconciliation": reconciliation,
            "fast_paper_safety": FastPaperSafetyService(get_portfolio_manager()).status(),
            "paper_only": True,
            "real_money_enabled": False,
        }
    )


@app.post("/api/trading/broker-paper/reconcile")
async def reconcile_broker_paper():
    try:
        result = await asyncio.to_thread(get_broker_reconciliation_service().reconcile)
        return convert_numpy_types(result)
    except (AlpacaPaperBrokerError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.get("/api/trading/broker-paper/orders")
async def list_broker_paper_orders(limit: int = 100):
    return convert_numpy_types(
        {
            "orders": BrokerOrderStore().list_orders(limit=limit),
            "paper_only": True,
        }
    )


@app.post("/api/trading/broker-paper/orders")
async def submit_broker_paper_order(req: BrokerPaperOrderRequest):
    safety = FastPaperSafetyService(get_portfolio_manager())
    safety_status = safety.status()
    if safety_status.get("enabled") is not True:
        raise HTTPException(status_code=409, detail="FAST_PAPER_ENABLED must be true for broker-paper orders.")
    try:
        safety.enforce_not_paused()
        get_broker_reconciliation_service().enforce_reconciled()
        quality = await asyncio.to_thread(
            MarketQualityService().evaluate_latest,
            req.symbol,
            req.asset_class,
        )
        if quality.get("trade_allowed") is not True:
            raise HTTPException(
                status_code=409,
                detail="Broker-paper market quality gate: "
                + ", ".join(quality.get("blockers") or ["unknown_market_quality_error"]),
            )
        short_sale_gate = None
        if req.side == "sell":
            short_sale_gate = await asyncio.to_thread(
                get_alpaca_paper_broker_adapter().assess_short_sale,
                symbol=req.symbol,
                quantity=req.quantity,
                reference_price=float(quality.get("midpoint") or 0),
            )
            if short_sale_gate.get("allowed") is not True:
                raise HTTPException(
                    status_code=409,
                    detail="Broker-paper short gate: "
                    + ", ".join(short_sale_gate.get("reasons") or ["short_not_allowed"]),
                )
        order_request = BrokerOrderRequest(
            client_order_id=req.client_order_id,
            symbol=req.symbol,
            quantity=str(req.quantity),
            side=req.side,
            order_type=req.order_type,
            time_in_force=req.time_in_force,
            limit_price=str(req.limit_price) if req.limit_price is not None else None,
            stop_price=str(req.stop_price) if req.stop_price is not None else None,
            extended_hours=req.extended_hours,
            signal_decision_id=req.signal_decision_id,
        )
        order = await asyncio.to_thread(get_alpaca_paper_broker_adapter().submit_order, order_request)
        return convert_numpy_types(
            {
                "order": order,
                "market_quality_gate": quality,
                "short_sale_gate": short_sale_gate,
                "paper_only": True,
                "real_money_enabled": False,
            }
        )
    except HTTPException:
        raise
    except BrokerSubmissionUncertainError as exc:
        stored = BrokerOrderStore().get(req.client_order_id)
        return JSONResponse(
            status_code=202,
            content=convert_numpy_types(
                {
                    "status": "submission_uncertain",
                    "message": str(exc),
                    "order": stored,
                    "automatic_resubmission_blocked": True,
                    "paper_only": True,
                }
            ),
        )
    except (AlpacaPaperBrokerError, BrokerReconciliationBlockedError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/api/trading/broker-paper/orders/{broker_order_id}/cancel")
async def cancel_broker_paper_order(broker_order_id: str):
    try:
        result = await asyncio.to_thread(
            get_alpaca_paper_broker_adapter().cancel_order,
            broker_order_id,
        )
        return convert_numpy_types(result)
    except (AlpacaPaperBrokerError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/api/trading/broker-paper/orders/by-client/{client_order_id}/refresh")
async def refresh_broker_paper_order(client_order_id: str):
    try:
        order = await asyncio.to_thread(
            get_alpaca_paper_broker_adapter().get_order_by_client_id,
            client_order_id,
        )
        return convert_numpy_types({"order": order, "paper_only": True})
    except (AlpacaPaperBrokerError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))

@app.post("/api/trading/paper-trades")
async def create_paper_trade(req: PaperTradeCreateRequest):
    try:
        payload = req.model_dump()
        items = get_portfolio_manager().get_signal_watch_items()
        snapshot = get_public_signal_service().build_watchlist_snapshot(items)
        trade = get_paper_trading_service().create_trade_from_payload(
            payload,
            _get_paper_news_context(snapshot),
        )
        _cache_forget("search:suggestions")
        return convert_numpy_types(attach_scope(trade, paper_scope()))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/trading/paper-trades/from-playbook")
async def create_paper_trade_from_playbook(req: PaperTradeFromPlaybookRequest):
    try:
        items = get_portfolio_manager().get_signal_watch_items()
        snapshot = get_public_signal_service().build_watchlist_snapshot(items)
        settings = get_portfolio_manager().get_signal_score_settings()
        scoreboard = await get_signal_score_service().build_scoreboard(snapshot, settings)
        payload = req.model_dump()
        payload["alert_source_label"] = "Paper-Playbook manuell"
        news_context = _get_paper_news_context(snapshot)
        trade = get_paper_trading_service().create_trade_from_playbook(
            payload,
            scoreboard,
            settings,
            news_context,
        )
        _cache_forget("search:suggestions")
        try:
            trade["alert_source_label"] = "Paper-Playbook manuell"
            trade["telegram_alerts"] = get_email_alert_service().send_paper_trade_opened_alerts(
                [trade],
                [trade.get("source_playbook") or {}],
                get_paper_trading_service().build_demo_account_snapshot(),
            )
        except Exception as alert_error:
            trade["telegram_alerts"] = {"status": "error", "message": str(alert_error)}
        return convert_numpy_types(attach_scope(trade, paper_scope()))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trading/leverage-product/validate")
async def validate_leverage_product(req: LeverageProductValidationRequest):
    try:
        result = get_paper_trading_service().validate_leverage_product_data(req.product_data)
        return convert_numpy_types(
            {
                **result,
                "status": "valid" if result.get("valid") else "blocked",
                "message": (
                    "Produktdaten sind fuer einen Paper-Test ausreichend."
                    if result.get("valid")
                    else "Produktdaten reichen noch nicht fuer einen Paper-Test."
                ),
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trading/paper-autopilot/settings")
async def get_paper_autopilot_settings():
    try:
        return convert_numpy_types(get_portfolio_manager().get_paper_autopilot_settings())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trading/paper-autopilot/settings")
async def save_paper_autopilot_settings(req: PaperAutopilotSettingsRequest):
    try:
        payload = {key: value for key, value in req.model_dump().items() if value is not None}
        manager = get_portfolio_manager()
        before = manager.get_paper_autopilot_settings()
        saved = manager.save_paper_autopilot_settings(payload)
        audit = manager.record_decision_audit(
            event_type="rule_change",
            subject="paper-autopilot-settings",
            decision="settings_updated",
            data_as_of=datetime.now(timezone.utc).isoformat(),
            source_status="internal_configuration",
            sources=[],
            model_version="paper-autopilot.v2",
            rule_version="paper-autopilot-settings.v2",
            user_action="paper_autopilot_settings_saved",
            payload={"before": before, "requested_change": payload, "after": saved},
        )
        _cache_forget("signals:scoreboard")
        _cache_forget("search:suggestions")
        return convert_numpy_types({**saved, "audit": audit})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trading/paper-autopilot")
async def run_paper_autopilot(req: PaperAutoSelectionRequest):
    try:
        items = get_portfolio_manager().get_signal_watch_items()
        snapshot = get_public_signal_service().build_watchlist_snapshot(items)
        settings = get_portfolio_manager().get_signal_score_settings()
        scoreboard = await get_signal_score_service().build_scoreboard(snapshot, settings)
        news_context = _get_paper_news_context(snapshot)
        result = get_paper_trading_service().run_auto_selection(
            scoreboard,
            settings,
            max_trades=req.max_trades,
            execute=req.execute,
            mode=req.mode,
            news_context=news_context,
        )
        if req.execute and result.get("opened"):
            _cache_forget("search:suggestions")
            try:
                result["telegram_alerts"] = get_email_alert_service().send_paper_trade_opened_alerts(
                    result.get("opened") or [],
                    result.get("selected") or [],
                    result.get("demo_account_after") or {},
                )
            except Exception as alert_error:
                result["telegram_alerts"] = {"status": "error", "message": str(alert_error)}
        return convert_numpy_types(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trading/paper-trades/{trade_id}/close")
async def close_paper_trade(trade_id: str, req: PaperTradeCloseRequest):
    try:
        trade = get_paper_trading_service().close_trade(
            trade_id,
            closed_price=req.closed_price,
            notes=req.notes,
            exit_reason=req.exit_reason,
            lessons_learned=req.lessons_learned,
        )
        _cache_forget("search:suggestions")
        try:
            telegram_alerts = get_email_alert_service().send_paper_trade_closed_alerts(
                [trade],
                get_paper_trading_service().build_demo_account_snapshot(),
            )
        except Exception as alert_error:
            telegram_alerts = {"status": "error", "message": str(alert_error)}
        return convert_numpy_types({**trade, "telegram_alerts": telegram_alerts})
    except PaperTradeAlreadyClosedError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/trading/paper-trades/{trade_id}/journal")
async def update_paper_trade_journal(trade_id: str, req: PaperTradeJournalRequest):
    try:
        trade = get_paper_trading_service().update_trade_journal(
            trade_id,
            notes=req.notes,
            exit_reason=req.exit_reason,
            lessons_learned=req.lessons_learned,
        )
        return convert_numpy_types(trade)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trading/gex/{ticker}")
async def get_trading_gex(ticker: str):
    """Returns Options Market Maker Gamma Exposure (GEX), Call/Put Walls, and Zero-Gamma Level."""
    try:
        service = get_trading_signals_service()
        result = await asyncio.to_thread(service.get_gex_profile, ticker)
        if not result:
            raise HTTPException(status_code=404, detail=f"No options GEX data available for {ticker}")
        return convert_numpy_types(result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trading/volume-profile/{ticker}")
async def get_trading_volume_profile(ticker: str, period: str = "1mo", interval: str = "30m"):
    """Returns Volume Profile, Point of Control (POC), Value Area (VAH/VAL), and Low Volume Nodes."""
    try:
        service = get_trading_signals_service()
        result = await asyncio.to_thread(service.volume_profile.compute_volume_profile, ticker, period, interval)
        if not result:
            raise HTTPException(status_code=404, detail=f"No volume profile data available for {ticker}")
        return convert_numpy_types(result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trading/market-regime")
async def get_trading_market_regime():
    """Returns macro market regime combining SPY, QQQ and VIX volatility stance."""
    try:
        service = get_trading_signals_service()
        regime = await asyncio.to_thread(service.get_market_regime)
        return convert_numpy_types(regime)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trading/asymmetric-setups")
async def get_asymmetric_trade_setups(limit: int = 6):
    """Returns top asymmetric trade setups with minimum 2.5:1 R:R, structural invalidation, and sizing."""
    try:
        items = get_portfolio_manager().get_signal_watch_items()
        watchlist = [str(item.get("value") or "").upper() for item in items if item.get("kind") == "ticker" and item.get("value")]
        service = get_trading_signals_service()
        setups = await asyncio.to_thread(service.get_asymmetric_setups, watchlist, limit=limit)
        return convert_numpy_types({"setups": setups, "count": len(setups)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trading/telegram/send-edge-setup")
async def send_trading_edge_setup_telegram(req: SendEdgeSetupTelegramRequest):
    """Dispatches a high-conviction trade setup card directly to the user's smartphone via Telegram."""
    try:
        service = get_trading_signals_service()
        ticker = (req.ticker or "").strip().upper()

        ticket = None
        if ticker:
            ticket = await asyncio.to_thread(
                service.asymmetric_service.generate_trade_setup,
                ticker,
                req.portfolio_capital or 50000.0,
                req.risk_budget_pct or 0.75,
            )
        else:
            items = get_portfolio_manager().get_signal_watch_items()
            watchlist = [str(item.get("value") or "").upper() for item in items if item.get("kind") == "ticker" and item.get("value")]
            setups = await asyncio.to_thread(
                service.get_asymmetric_setups,
                watchlist,
                req.portfolio_capital or 50000.0,
                req.risk_budget_pct or 0.75,
                1,
            )
            if setups:
                ticket = setups[0]

        if not ticket:
            raise HTTPException(status_code=404, detail="No suitable asymmetric trade setup found.")

        alert_result = await asyncio.to_thread(
            get_email_alert_service().send_trading_edge_setup_alert,
            ticket,
            req.force,
        )
        return convert_numpy_types({
            "status": "ok",
            "alert_result": alert_result,
            "ticket": ticket,
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trading/open-edge-paper-trade")
async def open_edge_paper_trade(req: OpenEdgePaperTradeRequest):
    """
    Opens an official Paper Trade from a high-conviction Grade A+/A setup.
    - Sized according to Demo Account cash and 0.75% risk model.
    - Configured with structural invalidation stop and Target 1 (2.0R).
    - Linked to TradeLifecycleService for trailing stop & breakeven management.
    """
    try:
        ticker = (req.ticker or "").strip().upper()
        if not ticker:
            raise HTTPException(status_code=400, detail="Ticker ist erforderlich.")

        service = get_trading_signals_service()
        paper_service = get_paper_trading_service()
        manager = get_portfolio_manager()

        # Check if trade is already open
        if not req.force:
            existing = [
                t for t in paper_service._enrich_trades(manager.list_paper_trades(limit=150))
                if str(t.get("ticker") or "").upper() == ticker and t.get("status") == "open"
            ]
            if existing:
                return convert_numpy_types({
                    "status": "already_open",
                    "message": f"Ein offener Paper Trade für {ticker} ist bereits im Demokonto aktiv.",
                    "trade": attach_scope(existing[0], paper_scope()),
                })

        # Sizing according to available demo cash
        account_snap = paper_service.build_demo_account_snapshot()
        avail_cash = float(account_snap.get("cash") or 50000.0)
        risk_budget = 0.75

        ticket = await asyncio.to_thread(
            service.asymmetric_service.generate_trade_setup,
            ticker,
            avail_cash,
            risk_budget,
        )
        if not ticket:
            raise HTTPException(status_code=404, detail=f"Kein asymmetrisches Setup für {ticker} berechenbar.")

        entry_price = float(ticket.get("entry_price") or 0.0)
        stop_price = float(ticket.get("invalidation_price") or 0.0)
        target_price = float(ticket.get("target_1") or 0.0)
        rec_shares = float(ticket.get("recommended_shares") or 1)
        qty = float(req.quantity) if req.quantity and req.quantity > 0 else rec_shares

        trade_payload = {
            "ticker": ticker,
            "asset_class": "equity",
            "direction": "long",
            "setup_type": f"institutional_edge_{ticket.get('setup_name', 'continuation').lower().replace(' ', '_')}",
            "entry_price": entry_price,
            "stop_price": stop_price,
            "target_price": target_price,
            "quantity": qty,
            "confidence_score": float(ticket.get("confluence_score") or 90.0),
            "thesis": f"{ticket.get('catalyst_description', '')} | Konfluenz: {', '.join(ticket.get('confluence_factors', []))} | R:R {ticket.get('risk_reward_ratio')}:1",
            "notes": f"{ticket.get('grade_badge', 'Grade A')} | POC ${ticket.get('volume_profile', {}).get('poc')} | GEX {ticket.get('options_gex', {}).get('regime')} | Ziel 2: ${ticket.get('target_2')}",
        }

        trade = await asyncio.to_thread(
            paper_service.create_trade_from_payload,
            trade_payload,
            _get_paper_news_context(None),
        )

        # Register in TradeLifecycleService for trailing stop & breakeven monitoring
        try:
            alert_service = get_email_alert_service()
            if getattr(alert_service, "trade_lifecycle_service", None):
                alert_service.trade_lifecycle_service.register_trade(ticket)
            else:
                from src.trade_lifecycle_service import TradeLifecycleService
                alert_service.trade_lifecycle_service = TradeLifecycleService(manager)
                alert_service.trade_lifecycle_service.register_trade(ticket)
        except Exception as lifecycle_err:
            print(f"Failed to register with lifecycle service: {lifecycle_err}")

        _cache_forget("search:suggestions")

        return convert_numpy_types({
            "status": "ok",
            "message": f"Paper Trade für {ticker} ({int(qty)} Stk @ ${entry_price:.2f}) eröffnet.",
            "trade": attach_scope(trade, paper_scope()),
            "ticket": ticket,
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trading/scanner/run-now")
async def trigger_trading_edge_scanner_now():
    """Immediately runs the background edge scanner cycle and dispatches due Grade A+/A setups."""
    try:
        result = await asyncio.to_thread(_run_trading_edge_scanner_cycle)
        return convert_numpy_types(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trading/relative-strength")
async def get_trading_relative_strength(benchmark: str = "SPY"):
    """Returns Mansfield Relative Strength and Alpha for the watchlist vs SPY."""
    try:
        items = get_portfolio_manager().get_signal_watch_items()
        watchlist = [str(item.get("value") or "").upper() for item in items if item.get("kind") == "ticker" and item.get("value")]
        service = get_relative_strength_service()
        leaders = await asyncio.to_thread(service.scan_relative_strength, watchlist, benchmark=benchmark)
        return convert_numpy_types({"benchmark": benchmark, "leaders": leaders, "count": len(leaders)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trading/active-trades")
async def get_trading_active_trades():
    """Returns active monitored trade setups and trailing stops."""
    try:
        service = get_trade_lifecycle_service()
        trades = service.get_active_trades()
        return convert_numpy_types({"trades": trades, "count": len(trades)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trading/lifecycle/evaluate-now")
async def evaluate_trading_lifecycle_now():
    """Immediately triggers price checks on active setups for Target 1, Target 2 and Trailing Stops."""
    try:
        service = get_trade_lifecycle_service()
        alert_svc = get_email_alert_service()
        res = await asyncio.to_thread(service.evaluate_active_trades, alert_svc)
        return convert_numpy_types(res)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trading/portfolio-heat")
async def get_trading_portfolio_heat(portfolio_capital: float = 50000.0):
    """Calculates total portfolio risk (heat) and cross-correlation clusters."""
    try:
        lifecycle_svc = get_trade_lifecycle_service()
        trades = lifecycle_svc.get_active_trades()
        heat_svc = get_portfolio_heat_service()
        report = await asyncio.to_thread(heat_svc.evaluate_portfolio_heat, trades, portfolio_capital)
        return convert_numpy_types(report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trading/avwap")
async def get_trading_anchored_vwap(ticker: str):
    """Calculates YTD, Earnings, Monthly, and Swing Low Anchored VWAPs for a ticker."""
    try:
        sym = (ticker or "").strip().upper()
        if not sym:
            raise HTTPException(status_code=400, detail="Ticker parameter required.")
        service = get_anchored_vwap_service()
        data = await asyncio.to_thread(service.compute_anchored_vwaps, sym)
        if not data:
            raise HTTPException(status_code=404, detail=f"No AVWAP data available for {sym}")
        return convert_numpy_types(data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trading/whale-flow")
async def get_trading_whale_flow(ticker: Optional[str] = None):
    """Analyzes volume spikes, absorption and institutional expansion for ticker or watchlist."""
    try:
        service = get_whale_flow_service()
        if ticker:
            sym = ticker.strip().upper()
            data = await asyncio.to_thread(service.analyze_whale_flow, sym)
            if not data:
                raise HTTPException(status_code=404, detail=f"No volume flow data for {sym}")
            return convert_numpy_types(data)

        items = get_portfolio_manager().get_signal_watch_items()
        watchlist = [str(item.get("value") or "").upper() for item in items if item.get("kind") == "ticker" and item.get("value")]
        anomalies = await asyncio.to_thread(service.scan_watchlist_whale_flows, watchlist)
        return convert_numpy_types({"anomalies": anomalies, "count": len(anomalies)})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trading/liquidity-zones")
async def get_trading_liquidity_zones(ticker: str):
    """Calculates Fair Value Gaps (FVG) and Order Blocks for a ticker."""
    try:
        sym = (ticker or "").strip().upper()
        if not sym:
            raise HTTPException(status_code=400, detail="Ticker parameter required.")
        service = get_liquidity_zone_service()
        data = await asyncio.to_thread(service.analyze_zones, sym)
        if not data:
            raise HTTPException(status_code=404, detail=f"No liquidity zones found for {sym}")
        return convert_numpy_types(data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trading/mtf-alignment")
async def get_trading_mtf_alignment(ticker: str):
    """Evaluates multi-timeframe trend and momentum alignment (1D, 1H, 15M)."""
    try:
        sym = (ticker or "").strip().upper()
        if not sym:
            raise HTTPException(status_code=400, detail="Ticker parameter required.")
        service = get_multi_timeframe_service()
        data = await asyncio.to_thread(service.analyze_mtf_alignment, sym)
        if not data:
            raise HTTPException(status_code=404, detail=f"No MTF alignment data for {sym}")
        return convert_numpy_types(data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trading/backtest")
async def run_strategy_backtest(
    ticker: str = "SPY",
    strategy: str = "volume_breakout",
    period: str = "2y",
    target_r: float = 2.5,
):
    """Runs a historical backtest for a strategy on the specified ticker."""
    from src.backtest_engine import BacktestEngine
    try:
        engine = BacktestEngine()
        res = await asyncio.to_thread(
            engine.backtest_strategy,
            ticker=ticker,
            strategy=strategy,
            period=period,
            target_r=target_r,
        )
        if not res:
            raise HTTPException(status_code=404, detail=f"Insufficient data for backtest of {ticker}")
        return convert_numpy_types(res)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/market/session-lists")
async def get_market_session_lists():
    try:
        items = get_portfolio_manager().get_signal_watch_items()
        snapshot = get_public_signal_service().build_watchlist_snapshot(items)
        payload = await get_session_list_service().build_session_lists(snapshot)
        return convert_numpy_types(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/signals/alerts/morning-brief")
async def send_morning_brief():
    try:
        return get_email_alert_service().send_session_brief_now("global")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/signals/alerts/open-brief/{session}")
async def send_open_brief(session: str):
    try:
        normalized = (session or "").strip().lower()
        if normalized not in {"europe", "usa"}:
            raise HTTPException(status_code=400, detail="session must be 'europe' or 'usa'")
        return get_email_alert_service().send_session_brief_now(normalized)
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/signals/alerts/session-list/{region}/{phase}")
async def send_session_list_alert(region: str, phase: str):
    try:
        return await get_email_alert_service().send_session_list_alert_async(region, phase)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/realtime/snapshot")
async def get_realtime_snapshot(symbols: str):
    try:
        requested = [item.strip() for item in symbols.split(",") if item.strip()]
        normalized = sorted({item.upper() for item in requested})
        cache_key = f"realtime:snapshot:{','.join(normalized)}"
        cached = _cache_get(cache_key, int(os.getenv("REALTIME_SNAPSHOT_CACHE_TTL_SECONDS", "5")))
        if cached is not None:
            return convert_numpy_types(cached)
        payload = get_realtime_market_service().build_snapshot(normalized)
        if isinstance(payload, dict):
            payload.setdefault("connection_state", "snapshot")
        return convert_numpy_types(_cache_set(cache_key, payload))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/realtime")
async def websocket_realtime_feed(websocket: WebSocket):
    await websocket.accept()

    password = get_app_password()
    secret = get_session_secret()
    if not password or not secret:
        try:
            await websocket.send_json(
                {"type": "error", "reason": "realtime_not_configured", "message": "Realtime stream not configured"}
            )
        except Exception:
            pass
        await websocket.close(code=1011, reason="realtime_not_configured")
        return

    session_value = websocket.cookies.get(SESSION_COOKIE_NAME)
    if not is_valid_session(session_value):
        try:
            await websocket.send_json(
                {"type": "error", "reason": "unauthorized", "message": "Authentication required for realtime stream"}
            )
        except Exception:
            pass
        await websocket.close(code=1008, reason="unauthorized")
        return

    symbols_param = websocket.query_params.get("symbols", "")
    symbols = [item.strip() for item in symbols_param.split(",") if item.strip()]
    if not symbols:
        symbols = ["SPY", "QQQ", "BTC-USD", "AAPL"]
    service = get_realtime_market_service()

    try:
        while True:
            payload = convert_numpy_types(service.build_snapshot(symbols))
            await websocket.send_json(payload)
            await asyncio.sleep(8)
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await websocket.close(code=1011)
        except Exception:
            pass

@app.get("/api/discovery/gainers")
async def get_top_gainers(window: str = "1w"):
    """Get market-wide top performers."""
    cache_key = None
    try:
        normalized_window = (window or "1w").strip().lower()
        cache_key = f"discovery:gainers:{normalized_window}"
        cached = _cache_get(
            cache_key,
            _safe_int_env("DISCOVERY_MOVERS_CACHE_TTL_SECONDS", 75, minimum=15),
        )
        if cached is not None:
            return convert_numpy_types(cached)
        payload = await get_discovery_service().get_market_movers(type="gainers", window=normalized_window)
        return convert_numpy_types(_cache_set(cache_key, payload))
    except Exception as e:
        if cache_key:
            stale = _cache_get_stale(
                cache_key,
                _safe_int_env("DISCOVERY_MOVERS_STALE_CACHE_TTL_SECONDS", 900, minimum=60),
            )
            if stale is not None:
                return convert_numpy_types(stale)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/discovery/losers")
async def get_top_losers(window: str = "1w"):
    """Get market-wide top laggards."""
    cache_key = None
    try:
        normalized_window = (window or "1w").strip().lower()
        cache_key = f"discovery:losers:{normalized_window}"
        cached = _cache_get(
            cache_key,
            _safe_int_env("DISCOVERY_MOVERS_CACHE_TTL_SECONDS", 75, minimum=15),
        )
        if cached is not None:
            return convert_numpy_types(cached)
        payload = await get_discovery_service().get_market_movers(type="losers", window=normalized_window)
        return convert_numpy_types(_cache_set(cache_key, payload))
    except Exception as e:
        if cache_key:
            stale = _cache_get_stale(
                cache_key,
                _safe_int_env("DISCOVERY_MOVERS_STALE_CACHE_TTL_SECONDS", 900, minimum=60),
            )
            if stale is not None:
                return convert_numpy_types(stale)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/discovery/small-caps")
async def get_small_cap_growth():
    """Identify high-growth small-cap stocks."""
    try:
        return await get_discovery_service().get_small_caps()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/discovery/future-stars")
async def get_future_stars():
    """Small/mid-cap future-star candidates validated against news and fundamentals."""
    try:
        cache_key = "discovery:future-stars"
        cached = _cache_get(cache_key, _safe_int_env("DISCOVERY_FUTURE_STARS_CACHE_TTL_SECONDS", 900, minimum=60))
        if cached is not None:
            return convert_numpy_types(cached)
        payload = await get_discovery_service().get_future_stars()
        return convert_numpy_types(_cache_set(cache_key, payload))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/screener")
async def run_market_screener(
    rsi_max: Optional[float] = None,
    market_cap_min: Optional[float] = None,
    market_cap_max: Optional[float] = None,
    sector: Optional[str] = None,
    high52_proximity: Optional[float] = None,
    low52_proximity: Optional[float] = None,
    limit: int = 35,
):
    try:
        return convert_numpy_types(
            await get_discovery_service().run_screener(
                rsi_max=rsi_max,
                market_cap_min=market_cap_min,
                market_cap_max=market_cap_max,
                sector=sector,
                high52_proximity=high52_proximity,
                low52_proximity=low52_proximity,
                limit=limit,
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/discovery/high-risk-opportunities")
async def get_high_risk_opportunities():
    """AI-powered high-risk, high-reward stock scanner."""
    try:
        from src.risk_scanner import RiskScanner
        scanner = RiskScanner()
        opportunities = await scanner.scan_opportunities(min_opportunity_score=40)
        return opportunities or scanner.fallback_opportunities()
    except Exception as e:
        try:
            from src.risk_scanner import RiskScanner
            return RiskScanner().fallback_opportunities()
        except Exception:
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/market/exchange-rate")
async def get_exchange_rate():
    """Get the current EUR/USD exchange rate."""
    try:
        import yfinance as yf
        ticker = yf.Ticker("USDEUR=X")
        # Get the most recent close
        rate = ticker.history(period="1d")['Close'].iloc[-1]
        return {"rate": rate}
    except Exception as e:
        print(f"Error fetching exchange rate: {e}")
        return {"rate": 0.92} # Fallback


# ── Push Notifications ────────────────────────────────────────────────────

@app.get("/api/push/vapid-key")
async def get_vapid_public_key():
    """Return the VAPID public key for push subscription."""
    if not browser_push_enabled():
        raise HTTPException(status_code=410, detail="Browser Push ist deaktiviert. Telegram ist der aktive Push-Kanal.")
    return {"publicKey": get_push_service().public_key}

@app.post("/api/push/subscribe")
async def push_subscribe(request: Request):
    """Register a push subscription."""
    if not browser_push_enabled():
        raise HTTPException(status_code=410, detail="Browser Push ist deaktiviert. Telegram ist der aktive Push-Kanal.")
    body = await request.json()
    is_new = get_push_service().subscribe(body)
    return {"ok": True, "new": is_new, "total": get_push_service().subscription_count}

@app.post("/api/push/unsubscribe")
async def push_unsubscribe(request: Request):
    """Remove a push subscription."""
    if not browser_push_enabled():
        return {"ok": True, "removed": False, "disabled": True}
    body = await request.json()
    endpoint = body.get("endpoint", "")
    removed = get_push_service().unsubscribe(endpoint)
    return {"ok": True, "removed": removed}

@app.post("/api/push/test")
async def push_test():
    """Send a test notification to all subscribers."""
    if not browser_push_enabled():
        raise HTTPException(status_code=410, detail="Browser Push ist deaktiviert. Telegram ist der aktive Push-Kanal.")
    result = get_push_service().send_notification(
        title="Broker Freund",
        body="Push Notifications sind aktiv! Du bekommst jetzt Briefings, Signale und Alerts direkt im Browser.",
        tag="test",
    )
    return result


@app.get("/api/market/internals")
async def get_market_internals():
    """Market breadth, VIX term structure, put/call ratio, advance/decline."""
    import yfinance as yf
    from datetime import datetime, timedelta
    result = {}
    try:
        # VIX + VIX futures proxy (VIX3M)
        vix = yf.Ticker("^VIX")
        vix_hist = vix.history(period="1mo")
        vix_price = float(vix_hist["Close"].iloc[-1]) if len(vix_hist) > 0 else None
        vix_5d = list(vix_hist["Close"].tail(5).round(2)) if len(vix_hist) >= 5 else []
        vix3m = yf.Ticker("^VIX3M")
        vix3m_hist = vix3m.history(period="5d")
        vix3m_price = float(vix3m_hist["Close"].iloc[-1]) if len(vix3m_hist) > 0 else None
        contango = None
        if vix_price and vix3m_price:
            contango = round((vix3m_price - vix_price) / vix_price * 100, 2)
        result["vix"] = {
            "current": round(vix_price, 2) if vix_price else None,
            "vix3m": round(vix3m_price, 2) if vix3m_price else None,
            "contango_pct": contango,
            "term_structure": "contango" if (contango or 0) > 0 else "backwardation",
            "history_5d": vix_5d,
        }
    except Exception:
        result["vix"] = None
    try:
        # Put/Call ratio via CBOE index options proxy
        pcr_ticker = yf.Ticker("^VIX")
        pcr_info = pcr_ticker.info or {}
        # Approximate from options if available
        try:
            opts = pcr_ticker.option_chain(pcr_ticker.options[0]) if pcr_ticker.options else None
            if opts:
                put_vol = int(opts.puts["volume"].sum())
                call_vol = int(opts.calls["volume"].sum())
                result["put_call_ratio"] = round(put_vol / max(call_vol, 1), 2)
            else:
                result["put_call_ratio"] = None
        except Exception:
            result["put_call_ratio"] = None
    except Exception:
        result["put_call_ratio"] = None
    try:
        # Advance/Decline proxy — compare % of S&P sector ETFs positive today
        sectors = ["XLK","XLF","XLV","XLE","XLI","XLY","XLP","XLU","XLB","XLRE","XLC"]
        adv, dec = 0, 0
        sector_perfs = []
        for sym in sectors:
            try:
                h = yf.Ticker(sym).history(period="5d")
                if len(h) >= 2:
                    chg = (h["Close"].iloc[-1] / h["Close"].iloc[-2] - 1) * 100
                    sector_perfs.append({"symbol": sym, "change_1d": round(chg, 2)})
                    if chg >= 0: adv += 1
                    else: dec += 1
            except Exception:
                continue
        result["breadth"] = {
            "advancing_sectors": adv,
            "declining_sectors": dec,
            "total_sectors": len(sectors),
            "ratio": round(adv / max(dec, 1), 2),
            "sectors": sorted(sector_perfs, key=lambda x: x["change_1d"], reverse=True),
        }
    except Exception:
        result["breadth"] = None
    try:
        # Fear & Greed (alternative.me crypto, but correlates)
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://api.alternative.me/fng/?limit=7", timeout=8)
            if resp.status_code == 200:
                fng_data = resp.json().get("data", [])
                result["fear_greed"] = [
                    {"value": int(d["value"]), "label": d["value_classification"], "date": d["timestamp"]}
                    for d in fng_data[:7]
                ]
            else:
                result["fear_greed"] = None
    except Exception:
        result["fear_greed"] = None
    try:
        # Yield curve (2Y vs 10Y)
        t2y = yf.Ticker("^IRX")  # 13-week T-bill
        t10y = yf.Ticker("^TNX")  # 10Y
        t2y_hist = t2y.history(period="5d")
        t10y_hist = t10y.history(period="5d")
        y2 = float(t2y_hist["Close"].iloc[-1]) if len(t2y_hist) > 0 else None
        y10 = float(t10y_hist["Close"].iloc[-1]) if len(t10y_hist) > 0 else None
        spread = round(y10 - y2, 3) if y2 is not None and y10 is not None else None
        result["yield_spread"] = {
            "t13w": round(y2, 3) if y2 else None,
            "t10y": round(y10, 3) if y10 else None,
            "spread": spread,
            "inverted": (spread or 0) < 0,
        }
    except Exception:
        result["yield_spread"] = None
    return result


# --- Static Files & SPA Handling ---
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Unauth diagnostic endpoint (open) — reports whether frontend was built
@app.get("/healthz")
async def healthz():
    dist_exists = os.path.exists("frontend/dist")
    index_exists = os.path.exists("frontend/dist/index.html")
    try:
        listing = os.listdir("frontend/dist") if dist_exists else os.listdir("frontend") if os.path.exists("frontend") else os.listdir(".")
    except Exception as e:
        listing = [f"err:{e}"]
    scheduler_seen_at = None
    scheduler_next_tick_at = None
    scheduler_error = None
    watchdog_seen_at = None
    watchdog_error = None
    try:
        manager = get_portfolio_manager()
        scheduler_seen_at = manager.get_app_setting("brief_scheduler_loop_seen_at")
        scheduler_next_tick_at = manager.get_app_setting("brief_scheduler_loop_next_tick_at")
        scheduler_error = manager.get_app_setting("brief_scheduler_loop_error")
        watchdog_seen_at = manager.get_app_setting("background_task_watchdog_seen_at")
        watchdog_error = manager.get_app_setting("background_task_watchdog_error")
    except Exception as e:
        watchdog_error = f"settings_unavailable:{e}"
    return {
        "ok": True,
        "dist": dist_exists,
        "index": index_exists,
        "cwd": os.getcwd(),
        "listing": listing[:30],
        "scheduler": {
            "enabled": _env_enabled("SCHEDULED_BRIEFS_ENABLED", "true"),
            "loop_seen_at": scheduler_seen_at,
            "next_tick_at": scheduler_next_tick_at,
            "loop_error": scheduler_error,
            "watchdog_seen_at": watchdog_seen_at,
            "watchdog_error": watchdog_error,
            "tasks": {
                "scheduler": _task_state(_signal_alert_task),
                "warmup": _task_state(_brief_warmup_task),
                "startup_catchup": _task_state(_scheduler_startup_catchup_task),
                "price_alerts": _task_state(_price_alert_task),
                "forecast_learning": _task_state(_forecast_learning_task),
                "watchdog": _task_state(_background_task_watchdog_task),
            },
        },
    }

# Check if dist folder exists
if os.path.exists("frontend/dist"):
    # NOTE: /assets is served by a custom endpoint below so we can provide
    # hash-fallback compatibility across deploys (prevents blank screens when
    # older cached HTML requests previous chunk hashes).

    # Mount icons + any other static folder explicitly so PWA assets work
    if os.path.exists("frontend/dist/icons"):
        app.mount("/icons", StaticFiles(directory="frontend/dist/icons"), name="icons")

    _DIST_ROOT_FILES = {
        "registerSW.js": "application/javascript",
        "sw.js": "application/javascript",
        "manifest.json": "application/manifest+json",
        "vite.svg": "image/svg+xml",
        "favicon.ico": "image/x-icon",
        "robots.txt": "text/plain",
    }

    @app.get("/assets/{asset_path:path}")
    async def serve_asset(asset_path: str):
        dist_assets_root = os.path.normpath(os.path.join("frontend", "dist", "assets"))
        candidate = os.path.normpath(os.path.join("frontend", "dist", "assets", asset_path))

        if not candidate.startswith(dist_assets_root):
            raise HTTPException(status_code=404, detail="Asset not found")

        ext_map = {
            ".js": "application/javascript",
            ".mjs": "application/javascript",
            ".css": "text/css",
            ".json": "application/json",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".ico": "image/x-icon",
            ".woff2": "font/woff2",
            ".map": "application/json",
        }

        if os.path.isfile(candidate):
            ext = os.path.splitext(candidate)[1].lower()
            response = FileResponse(candidate, media_type=ext_map.get(ext))
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return response

        filename = os.path.basename(asset_path)
        stem, ext = os.path.splitext(filename)
        if "-" in stem and ext in {".js", ".css"}:
            prefix = stem.rsplit("-", 1)[0]
            try:
                matches = [
                    fn for fn in os.listdir(dist_assets_root)
                    if fn.startswith(f"{prefix}-") and fn.endswith(ext)
                ]
                if matches:
                    matches.sort(
                        key=lambda fn: os.path.getmtime(os.path.join(dist_assets_root, fn)),
                        reverse=True,
                    )
                    fallback_path = os.path.join(dist_assets_root, matches[0])
                    response = FileResponse(
                        fallback_path,
                        media_type=ext_map.get(ext),
                    )
                    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
                    response.headers["X-Asset-Fallback"] = "1"
                    return response
            except Exception:
                pass

        raise HTTPException(status_code=404, detail="Asset not found")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Allow API calls to pass through
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="API endpoint not found")

        # Serve real dist file if it exists (PWA: registerSW.js, sw.js,
        # workbox-*.js, manifest.json, icons, etc.) — otherwise SPA fallback.
        if full_path:
            candidate = os.path.normpath(os.path.join("frontend", "dist", full_path))
            # Guard against path traversal
            if candidate.startswith(os.path.normpath("frontend/dist")) and os.path.isfile(candidate):
                # Force correct MIME for known extensions
                media_type = None
                ext = os.path.splitext(full_path)[1].lower()
                ext_map = {
                    ".js": "application/javascript",
                    ".mjs": "application/javascript",
                    ".css": "text/css",
                    ".json": "application/json",
                    ".webmanifest": "application/manifest+json",
                    ".svg": "image/svg+xml",
                    ".png": "image/png",
                    ".ico": "image/x-icon",
                    ".woff2": "font/woff2",
                    ".map": "application/json",
                }
                media_type = ext_map.get(ext)
                if full_path in _DIST_ROOT_FILES:
                    media_type = _DIST_ROOT_FILES[full_path]
                response = FileResponse(candidate, media_type=media_type)
                filename = os.path.basename(candidate)
                is_sw_related = filename in {"sw.js", "registerSW.js"} or filename.startswith("workbox-")
                is_hashed_asset = "/assets/" in candidate.replace("\\", "/") and "-" in filename
                if is_sw_related:
                    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                    response.headers["Pragma"] = "no-cache"
                    response.headers["Expires"] = "0"
                elif is_hashed_asset:
                    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
                else:
                    response.headers["Cache-Control"] = "public, max-age=300"
                return response

        # SPA fallback for client-side routes (/, /portfolio, etc.)
        response = FileResponse("frontend/dist/index.html", media_type="text/html")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
else:
    print("Warning: frontend/dist folder not found. Run 'npm run build' in frontend directory.")

    @app.get("/")
    async def root_fallback():
        return JSONResponse(status_code=503, content={
            "detail": "Frontend build missing. Check Railway build logs.",
            "hint": "Visit /healthz for diagnostics.",
        })

@app.get("/api/debug/files")
async def debug_files():
    import os
    cwd = os.getcwd()
    files = []
    for root, dirs, filenames in os.walk("."):
        for filename in filenames:
            files.append(os.path.join(root, filename))
    return {
        "cwd": cwd,
        "files": files[:100], # Limit to first 100 to avoid potential huge payload
        "frontend_dist_exists": os.path.exists("frontend/dist"),
        "frontend_exists": os.path.exists("frontend")
    }

if __name__ == "__main__":
    print("Starting Stock Analysis API...")
    import traceback
    try:
        import uvicorn
        uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)
    except Exception as e:
        print("CRITICAL: API failed to start")
        traceback.print_exc()
