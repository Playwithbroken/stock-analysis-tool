"""
FastAPI Backend for Stock Analysis Tool
Provides REST API endpoints for stock analysis.
"""

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import difflib
import uvicorn
import numpy as np
import asyncio
import hashlib
import hmac
import secrets
import math
import requests
from datetime import datetime, timedelta

from src.data_fetcher import DataFetcher
from src.analyzer import StockAnalyzer, Rating, Valuation
from src.discovery_service import DiscoveryService
from src.email_alert_service import EmailAlertService
from src.morning_brief_service import MorningBriefService
from src.paper_trading_service import PaperTradingService
from src.signal_score_service import SignalScoreService
from src.session_list_service import SessionListService
from src.trading_intelligence_service import TradingIntelligenceService
from src.realtime_market_service import RealtimeMarketService
from src.public_signal_service import PublicSignalService
from src.storage import PortfolioManager

# Load environment variables
from dotenv import load_dotenv
import os
load_dotenv()


app = FastAPI(
    title="Stock Analysis API",
    description="Professional stock market analysis tool",
    version="1.0.0"
)

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


# Global services (Lazy initialized)
_discovery_service = None
_portfolio_manager = None
_public_signal_service = None
_email_alert_service = None
_signal_alert_task = None
_price_alert_task = None
_brief_warmup_task = None
_morning_brief_service = None
_signal_score_service = None
_session_list_service = None
_paper_trading_service = None
_trading_intelligence_service = None
_realtime_market_service = None
_push_service = None
SESSION_COOKIE_NAME = "brokerfreund_session"


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
    {"ticker": "BRK-B", "name": "Berkshire Hathaway"},
    {"ticker": "JPM", "name": "JPMorgan Chase"},
    {"ticker": "V", "name": "Visa"},
    {"ticker": "MA", "name": "Mastercard"},
    {"ticker": "SAP", "name": "SAP"},
    {"ticker": "ASML", "name": "ASML"},
    {"ticker": "INTC", "name": "Intel"},
    {"ticker": "AMD", "name": "Advanced Micro Devices"},
    {"ticker": "NFLX", "name": "Netflix"},
    {"ticker": "SPY", "name": "SPDR S&P 500 ETF"},
    {"ticker": "QQQ", "name": "Invesco QQQ Nasdaq ETF"},
    {"ticker": "DIA", "name": "SPDR Dow Jones ETF"},
    {"ticker": "IWM", "name": "iShares Russell 2000 ETF"},
    {"ticker": "GLD", "name": "SPDR Gold Shares ETF"},
    {"ticker": "TLT", "name": "iShares 20+ Year Treasury ETF"},
    {"ticker": "XLE", "name": "Energy Select Sector ETF"},
    {"ticker": "USO", "name": "United States Oil Fund"},
    {"ticker": "BTC-USD", "name": "Bitcoin"},
    {"ticker": "ETH-USD", "name": "Ethereum"},
    {"ticker": "SOL-USD", "name": "Solana"},
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
    "tesla": "TSLA",
    "bitcoin": "BTC-USD",
    "ethereum": "ETH-USD",
}


def _normalize_search_query(value: str) -> str:
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


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
        )
    return _email_alert_service

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

def get_push_service():
    global _push_service
    if _push_service is None:
        from src.push_service import PushService
        _push_service = PushService()
    return _push_service


@app.middleware("http")
async def require_single_user_auth(request: Request, call_next):
    path = request.url.path
    open_paths = {
        "/api/health",
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/status",
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

async def _signal_alert_loop():
    interval_minutes = int(os.getenv("SIGNAL_ALERTS_INTERVAL_MINUTES", "15"))
    await asyncio.sleep(5)
    while True:
        try:
            if _env_enabled("SIGNAL_ALERTS_ENABLED", "false"):
                await asyncio.to_thread(get_email_alert_service().check_and_send_alerts, False)
            await asyncio.to_thread(get_email_alert_service().send_scheduled_open_briefs)
        except Exception as e:
            print(f"Signal alert loop error: {e}")
        await asyncio.sleep(max(1, interval_minutes) * 60)


async def _brief_warmup_loop():
    if not _env_enabled("BRIEF_WARMUP_ENABLED", "true"):
        return
    await asyncio.sleep(12)
    while True:
        try:
            items = await asyncio.to_thread(get_portfolio_manager().get_signal_watch_items)
            snapshot = await asyncio.wait_for(
                asyncio.to_thread(get_public_signal_service().build_watchlist_snapshot, items),
                timeout=float(os.getenv("BRIEF_WARMUP_SNAPSHOT_TIMEOUT_SECONDS", "5")),
            )
            await asyncio.wait_for(
                asyncio.to_thread(get_morning_brief_service().get_brief_fast, snapshot),
                timeout=float(os.getenv("BRIEF_WARMUP_TIMEOUT_SECONDS", "20")),
            )
        except Exception as e:
            print(f"Brief warmup loop error: {e}")
        interval_seconds = int(os.getenv("BRIEF_WARMUP_INTERVAL_SECONDS", "300"))
        await asyncio.sleep(max(60, interval_seconds))


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
                        get_push_service().notify_price_alert(symbol, float(current_price), condition)
                    except Exception as push_error:
                        print(f"Push price alert failed for {symbol}: {push_error}")

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
    global _signal_alert_task, _price_alert_task, _brief_warmup_task
    alerts_enabled = _env_enabled("SIGNAL_ALERTS_ENABLED", "false")
    scheduled_briefs_enabled = _env_enabled("SCHEDULED_BRIEFS_ENABLED", "true")
    if (alerts_enabled or scheduled_briefs_enabled) and _signal_alert_task is None:
        _signal_alert_task = asyncio.create_task(_signal_alert_loop())
    if scheduled_briefs_enabled and _brief_warmup_task is None:
        _brief_warmup_task = asyncio.create_task(_brief_warmup_loop())
    if _price_alert_task is None:
        _price_alert_task = asyncio.create_task(_price_alert_loop())

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
    ticker: str
    shares: float
    buy_price: Optional[float] = None


class PortfolioRequest(BaseModel):
    holdings: List[PortfolioHolding]

class CreatePortfolioRequest(BaseModel):
    name: str

class AddHoldingRequest(BaseModel):
    ticker: str
    shares: float
    buy_price: Optional[float] = None

class OracleRequest(BaseModel):
    message: str
    context_ticker: Optional[str] = None
    portfolio_snapshot: Optional[Dict[str, Any]] = None
    live_quotes: Optional[Dict[str, Any]] = None
    signal_score: Optional[Dict[str, Any]] = None
    morning_brief_summary: Optional[Dict[str, Any]] = None


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
    leverage: float = 1
    notes: Optional[str] = None
    exit_reason: Optional[str] = None
    lessons_learned: Optional[str] = None


class PaperTradeFromPlaybookRequest(BaseModel):
    playbook_id: str
    direction: Optional[str] = "long"
    quantity: float = 1
    leverage: float = 1


class PaperTradeCloseRequest(BaseModel):
    closed_price: Optional[float] = None
    notes: Optional[str] = None
    exit_reason: Optional[str] = None
    lessons_learned: Optional[str] = None


class PaperTradeJournalRequest(BaseModel):
    notes: Optional[str] = None
    exit_reason: Optional[str] = None
    lessons_learned: Optional[str] = None


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
    return {"status": "ok", "message": "Stock Analysis API is running (v2)"}


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
                "sector_name": target_sector,
                "status": sector_data['status'],
                "strength": sector_data['strength'],
                "avg_change_1w": avg_change,
                "top_stocks": sector_data['hot_stocks'],
                "verdict": f"Der {target_sector}-Sektor zeigt momentan eine {sector_data['status'].lower()}e Tendenz mit einer durchschnittlichen Wochenperformance von {avg_change:+.2f}%."
            }

        # Check for company names or 'Name (TICKER)' format
        resolved_ticker = ticker.upper().strip()

        # If input contains brackets like 'Pfizer Inc. (PFE)', extract the ticker
        if "(" in ticker and ")" in ticker:
            import re
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
                    suggestions = await get_discovery_service().search_ticker(ticker)
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
                        "category": "Technical Analysis",
                        "score": 0.0,
                        "summary": "Insufficient live market data. Retry for full signal quality.",
                        "findings": [
                            {"metric": "Data State", "value": "Insufficient signal", "rating": "neutral"}
                        ],
                    },
                    "fundamental": {
                        "category": "Fundamental Analysis",
                        "score": 0.0,
                        "summary": "Live market pricing is temporarily degraded.",
                        "findings": [
                            {"metric": "Coverage", "value": "Partial", "rating": "neutral"}
                        ],
                    },
                    "sentiment": {
                        "category": "Sentiment Analysis",
                        "score": 0.0,
                        "summary": "Signal feed unavailable for this moment.",
                        "findings": [
                            {"metric": "Confidence", "value": "Low", "rating": "neutral"}
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
                    "analysis": fallback_analysis,
                    "etf_analysis": None,
                    "recommendation": {
                        "action": "HOLD",
                        "reason": "Insufficient live market signal. Retry shortly.",
                    },
                    "valuation": Valuation.FAIRLY_VALUED.value,
                    "total_score": 0,
                    "verdict": "Insufficient signal quality right now. Please retry for a full analysis.",
                })
        
        # Analyze
        analyzer = StockAnalyzer(data)
        result = analyzer.generate_recommendation()
        
        # Serialize analyses
        analyses = {}
        for key, analysis in result.get("analyses", {}).items():
            analyses[key] = serialize_analysis_result(analysis)
        
        return convert_numpy_types({
            "ticker": data.get("ticker"),
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
            "analysis": analyses,
            "etf_analysis": analyzer.analyze_etf() if data.get("fundamentals", {}).get("quote_type") == "ETF" else None,
            "recommendation": result.get("recommendation"),
            "valuation": result.get("valuation", Valuation.FAIRLY_VALUED).value,
            "total_score": result.get("total_score", 0),
            "verdict": analyzer.get_one_sentence_verdict()
        })
        
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
async def get_history(ticker: str, period: str = "1mo", interval: str = "1d") -> List[Dict[str, Any]]:
    """
    Get historical price data for a ticker.
    Runs the blocking yfinance call in a thread executor with a 20-second timeout
    so it never hangs the event loop indefinitely.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    normalized_ticker = ticker.upper().strip()
    attempts: List[tuple[str, str]] = [
        (period, interval),
        ("1mo", "1d"),
        ("5d", "15m"),
    ]
    seen_attempts = set()
    last_error: Optional[Exception] = None

    loop = asyncio.get_event_loop()

    for try_period, try_interval in attempts:
        key = (try_period, try_interval)
        if key in seen_attempts:
            continue
        seen_attempts.add(key)

        def _fetch():
            fetcher = DataFetcher(normalized_ticker)
            return fetcher.get_history(period=try_period, interval=try_interval)

        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                history = await asyncio.wait_for(
                    loop.run_in_executor(pool, _fetch),
                    timeout=12.0,
                )
            if history:
                return convert_numpy_types(history)
        except asyncio.TimeoutError as e:
            last_error = e
            continue
        except Exception as e:
            last_error = e
            continue

    # Snapshot fallback: return one synthetic datapoint instead of hard failure.
    try:
        snapshot = get_realtime_market_service().build_snapshot([normalized_ticker])
        quotes = snapshot.get("quotes", [])
        quote = next(
            (item for item in quotes if str(item.get("symbol", "")).upper() == normalized_ticker),
            None,
        )
        price = float(quote.get("price")) if quote and quote.get("price") is not None else None
        if price is not None:
            fallback_history = [{
                "time": "fallback",
                "full_date": datetime.now().isoformat(),
                "price": price,
                "volume": float(quote.get("volume") or 0),
            }]
            return convert_numpy_types(fallback_history)
    except Exception:
        pass

    if isinstance(last_error, asyncio.TimeoutError):
        raise HTTPException(status_code=504, detail="History fetch timed out - data provider not responding")
    raise HTTPException(status_code=404, detail="No history data available for this symbol right now")


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


@app.get("/api/portfolio/{p_id}/verdict")
async def get_portfolio_verdict(p_id: str):
    """Generate an AI verdict for the entire portfolio."""
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
        results = await get_discovery_service().search_ticker(q)
        if results:
            return results
        return _fuzzy_catalog_search(q, limit=6)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/discovery/moonshots")
async def get_moonshot_stocks():
    return await get_discovery_service().get_moonshots()


@app.get("/api/discovery/sentiment-heatmap")
async def get_sentiment_heatmap():
    return await get_discovery_service().get_sentiment_heatmap()


@app.get("/api/search/suggestions")
async def get_search_suggestions(q: str = None):
    """Aggregate trending, moonshot, and commodity suggestions for search."""
    if q and len(q) > 1:
        # If user provides a query, prioritize name searches
        results = await get_discovery_service().search_ticker(q)
        if not results:
            results = _fuzzy_catalog_search(q, limit=6)
        return {
            "Matches": [f"{r['name']} ({r['ticker']})" for r in results[:5]],
            "Ticker": [r['ticker'] for r in results[:5]]
        }

    trending = await get_discovery_service().get_trending()
    moonshots = await get_discovery_service().get_moonshots()
    
    suggestions = {
        "Trending": [t['ticker'] for t in trending[:3]],
        "Moonshots": [m['ticker'] for m in moonshots[:3]],
        "Sektoren": ["Artificial Intelligence", "Semiconductors", "Technology"],
        "Regionen": ["USA", "Europe", "Asia", "Germany"],
        "Rohstoffe": ["GC=F", "CL=F", "SI=F"],
        "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD"]
    }
    return suggestions


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
    macro_regime = brief.get("macro_regime") if isinstance(brief, dict) else None
    headline = brief.get("headline") if isinstance(brief, dict) else None

    primary = ticker_context[0] if ticker_context else None
    score = float(primary.get("score", 0)) if primary else 0.0
    symbol = primary.get("symbol") if primary else "MARKET"
    week_change = float(primary.get("change_1w") or 0) if primary else 0.0
    price = primary.get("price") if primary else None

    if primary:
        if score >= 30 and week_change >= 0:
            thesis = f"{symbol} bleibt konstruktiv, solange Momentum und Score stabil bleiben."
        elif score <= -20 or week_change < -3:
            thesis = f"{symbol} zeigt fragiles Profil; Kapitalerhalt ist aktuell wichtiger als Aggression."
        else:
            thesis = f"{symbol} ist aktuell neutral, Setup nur bei klarem Trigger handeln."
    else:
        thesis = "Ohne konkreten Ticker liegt der Fokus auf Regime, Risiko und bestätigten Triggern."

    if "short" in msg or "sell" in msg or "verkauf" in msg:
        thesis = f"{thesis} Short-Ideen nur mit bestätigtem Bruch und engem Risikorahmen."
    elif "long" in msg or "buy" in msg or "kauf" in msg:
        thesis = f"{thesis} Long nur mit Folgekäufen und sauberem Volumen."

    risk_line_parts: List[str] = []
    if macro_regime:
        risk_line_parts.append(f"Regime: {macro_regime}")
    if holdings_count > 0:
        risk_line_parts.append(
            f"Portfolio {holdings_count} Positionen, P&L {gain_loss_pct:+.2f}% auf {total_value:,.0f} Gesamtwert"
        )
    if top_signal:
        risk_line_parts.append(
            f"Top-Signal: {top_signal.get('label', 'Idea')} (Score {float(top_signal.get('total_score') or 0):.0f})"
        )
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

    explain_lines = []
    if primary:
        explain_lines.append(
            f"{symbol} wird aus Score, Wochenmomentum, Live-Preis und aktuellem Marktregime eingeordnet."
        )
    else:
        explain_lines.append(
            "Ohne Einzelticker ordne ich zuerst Marktregime, Portfolio-Risiko und die besten Signale ein."
        )
    if holdings_count > 0:
        explain_lines.append(
            f"Dein Portfolio-Kontext ist aktiv ({holdings_count} Positionen"
            + (f": {', '.join(holding_names)}" if holding_names else "")
            + ")."
        )
    if top_signal:
        explain_lines.append("Das Signalboard fliesst als Priorisierung ein, nicht als blinder Kaufbefehl.")

    next_steps = [
        "1. Erst den Trigger abwarten, nicht vor der Bestaetigung handeln.",
        "2. Positionsgroesse klein halten, wenn Regime oder Newsflow gemischt sind.",
        "3. Bei Gegenreaktion sofort Invalidierung pruefen.",
    ]

    response = (
        f"These: {thesis}\n"
        f"Erklaerung: {' '.join(explain_lines)}\n"
        f"Risiko: {' | '.join(risk_line_parts)}\n"
        f"Trigger: {trigger_line}\n"
        f"Invalidierung: {invalidation_line}\n"
        "Beobachtbare Levels:\n"
        + "\n".join([f"- {line}" for line in levels])
        + "\nNaechste Schritte:\n"
        + "\n".join([f"- {line}" for line in next_steps])
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
    return get_portfolio_manager().create_portfolio(req.name)

@app.delete("/api/portfolios/{p_id}")
async def delete_portfolio(p_id: str):
    get_portfolio_manager().delete_portfolio(p_id)
    return {"status": "deleted"}

@app.post("/api/portfolios/{p_id}/holdings")
async def add_holding(p_id: str, req: AddHoldingRequest):
    get_portfolio_manager().add_holding(p_id, req.ticker, req.shares, req.buy_price)
    return {"status": "added"}

@app.delete("/api/portfolios/{p_id}/holdings/{ticker}")
async def remove_holding(p_id: str, ticker: str):
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
    writer.writerow(["Ticker", "Shares", "Buy Price"])
    
    for h in portfolio['holdings']:
        writer.writerow([h['ticker'], h['shares'], h.get('buyPrice', 'N/A')])
        
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
        return await get_discovery_service().get_etfs()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/discovery/stars")
async def get_star_assets():
    """Get the spotlight assets (Day/Week winners/losers)."""
    try:
        return await get_discovery_service().get_star_assets()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        items = get_portfolio_manager().get_signal_watch_items()
        summary = get_public_signal_service().build_watchlist_snapshot(items)
        return convert_numpy_types(summary)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/signals/watchlist/items")
async def add_signal_watch_item(req: SignalWatchItemRequest):
    try:
        get_portfolio_manager().add_signal_watch_item(req.kind, req.value)
        items = get_portfolio_manager().get_signal_watch_items()
        return convert_numpy_types(get_public_signal_service().build_watchlist_snapshot(items))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/signals/watchlist/items")
async def delete_signal_watch_item(kind: str, value: str):
    try:
        get_portfolio_manager().remove_signal_watch_item(kind, value)
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

@app.get("/api/settings/signal-score")
async def get_signal_score_settings():
    try:
        return convert_numpy_types(get_portfolio_manager().get_signal_score_settings())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/settings/signal-score")
async def save_signal_score_settings(payload: Dict[str, Any]):
    try:
        return convert_numpy_types(get_portfolio_manager().save_signal_score_settings(payload))
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
    items = get_portfolio_manager().get_signal_watch_items()
    snapshot = get_public_signal_service().build_watchlist_snapshot(items)
    settings = get_portfolio_manager().get_signal_score_settings()
    scoreboard = await get_signal_score_service().build_scoreboard(snapshot, settings)

    return {
        "watchlist": convert_numpy_types(snapshot),
        "history": convert_numpy_types(get_portfolio_manager().get_sent_signal_events(limit=limit)),
        "brief": convert_numpy_types(get_morning_brief_service().get_brief_fast(snapshot)),
        "scoreboard": convert_numpy_types(scoreboard),
        "session_lists": convert_numpy_types(await get_session_list_service().build_session_lists(snapshot)),
        "paper_dashboard": convert_numpy_types(get_paper_trading_service().build_dashboard(scoreboard, settings)),
        "trading_intelligence": convert_numpy_types(get_trading_intelligence_service().build_snapshot(snapshot)),
    }


@app.get("/api/radar/bootstrap")
async def get_radar_bootstrap(limit: int = 8):
    try:
        return await build_radar_bootstrap(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/market/morning-brief")
async def get_morning_brief():
    service = get_morning_brief_service()
    try:
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
                timeout=12.0,
            )
        except asyncio.TimeoutError:
            fallback = service.get_cached_or_last_brief(snapshot)
            if fallback is None:
                fallback = service.build_empty_brief("timeout")
            quality = fallback.setdefault("quality", {})
            quality["status"] = "partial"
            quality["fallback"] = "timeout"
            return convert_numpy_types(fallback)
        except Exception:
            fallback = service.get_cached_or_last_brief(snapshot)
            if fallback is None:
                fallback = service.build_empty_brief("error")
            quality = fallback.setdefault("quality", {})
            quality["status"] = "partial"
            quality["fallback"] = "error"
            return convert_numpy_types(fallback)

        return convert_numpy_types(brief)
    except Exception as e:
        fallback = service.get_cached_or_last_brief()
        if fallback is not None:
            quality = fallback.setdefault("quality", {})
            quality["status"] = "partial"
            quality["fallback"] = "server_error"
            return convert_numpy_types(fallback)
        return convert_numpy_types(service.build_empty_brief("server_error"))


@app.get("/api/market/trading-edge")
async def get_trading_edge():
    """Heavy trading-signals payload (squeeze, insider, options, regime,
    sectors, yield curve). Loaded by the frontend separately so the main
    brief stays fast. Cached internally per-component (10min – 6h)."""
    try:
        items = get_portfolio_manager().get_signal_watch_items()
        snapshot = get_public_signal_service().build_watchlist_snapshot(items)
        return convert_numpy_types(
            get_morning_brief_service().get_trading_edge(snapshot)
        )
    except Exception as e:
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
        # Also send browser push notification
        try:
            brief = get_morning_brief_service().get_brief()
            headline = brief.get("headline") or brief.get("opening_bias") or "Neues Briefing verfuegbar"
            get_push_service().notify_brief(session, headline)
        except Exception:
            pass
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

@app.get("/api/signals/scoreboard")
async def get_signal_scoreboard():
    try:
        items = get_portfolio_manager().get_signal_watch_items()
        snapshot = get_public_signal_service().build_watchlist_snapshot(items)
        settings = get_portfolio_manager().get_signal_score_settings()
        scoreboard = await get_signal_score_service().build_scoreboard(snapshot, settings)
        return convert_numpy_types(scoreboard)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trading/paper-dashboard")
async def get_paper_trading_dashboard():
    try:
        items = get_portfolio_manager().get_signal_watch_items()
        snapshot = get_public_signal_service().build_watchlist_snapshot(items)
        settings = get_portfolio_manager().get_signal_score_settings()
        scoreboard = await get_signal_score_service().build_scoreboard(snapshot, settings)
        dashboard = get_paper_trading_service().build_dashboard(scoreboard, settings)
        return convert_numpy_types(dashboard)
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

@app.post("/api/trading/paper-trades")
async def create_paper_trade(req: PaperTradeCreateRequest):
    try:
        payload = req.model_dump()
        trade = get_paper_trading_service().create_trade_from_payload(payload)
        return convert_numpy_types(trade)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/trading/paper-trades/from-playbook")
async def create_paper_trade_from_playbook(req: PaperTradeFromPlaybookRequest):
    try:
        items = get_portfolio_manager().get_signal_watch_items()
        snapshot = get_public_signal_service().build_watchlist_snapshot(items)
        settings = get_portfolio_manager().get_signal_score_settings()
        scoreboard = await get_signal_score_service().build_scoreboard(snapshot, settings)
        trade = get_paper_trading_service().create_trade_from_playbook(req.model_dump(), scoreboard, settings)
        return convert_numpy_types(trade)
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
        return convert_numpy_types(trade)
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
        return get_email_alert_service().send_morning_brief()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/signals/alerts/open-brief/{session}")
async def send_open_brief(session: str):
    try:
        return get_email_alert_service().send_open_brief(session)
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
        return convert_numpy_types(get_realtime_market_service().build_snapshot(requested))
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
    try:
        return await get_discovery_service().get_market_movers(type='gainers', window=window)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/discovery/losers")
async def get_top_losers(window: str = "1w"):
    """Get market-wide top laggards."""
    try:
        return await get_discovery_service().get_market_movers(type='losers', window=window)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/discovery/small-caps")
async def get_small_cap_growth():
    """Identify high-growth small-cap stocks."""
    try:
        return await get_discovery_service().get_small_caps()
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
        return opportunities
    except Exception as e:
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
    return {"publicKey": get_push_service().public_key}

@app.post("/api/push/subscribe")
async def push_subscribe(request: Request):
    """Register a push subscription."""
    body = await request.json()
    is_new = get_push_service().subscribe(body)
    return {"ok": True, "new": is_new, "total": get_push_service().subscription_count}

@app.post("/api/push/unsubscribe")
async def push_unsubscribe(request: Request):
    """Remove a push subscription."""
    body = await request.json()
    endpoint = body.get("endpoint", "")
    removed = get_push_service().unsubscribe(endpoint)
    return {"ok": True, "removed": removed}

@app.post("/api/push/test")
async def push_test():
    """Send a test notification to all subscribers."""
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
    return {"ok": True, "dist": dist_exists, "index": index_exists, "cwd": os.getcwd(), "listing": listing[:30]}

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
