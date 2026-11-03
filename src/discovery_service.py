"""
Discovery Service
Handles identification of trending stocks, rebound opportunities, and small-cap growth.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import yfinance as yf
from src.data_fetcher import DataFetcher
from src.analyzer import StockAnalyzer

import random
from src.data_fetcher import DataFetcher
from src.analyzer import StockAnalyzer

UNIVERSE_NAMES: Dict[str, str] = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corp.",
    "AMZN": "Amazon.com Inc.",
    "NVDA": "NVIDIA Corp.",
    "GOOGL": "Alphabet Inc.",
    "META": "Meta Platforms Inc.",
    "TSLA": "Tesla Inc.",
    "AVGO": "Broadcom Inc.",
    "ADBE": "Adobe Inc.",
    "COST": "Costco Wholesale Corp.",
    "PEP": "PepsiCo Inc.",
    "NFLX": "Netflix Inc.",
    "AMD": "Advanced Micro Devices",
    "TMUS": "T-Mobile US Inc.",
    "INTC": "Intel Corp.",
    "CSCO": "Cisco Systems Inc.",
    "CMCSA": "Comcast Corp.",
    "AMAT": "Applied Materials",
    "QCOM": "Qualcomm Inc.",
    "ISRG": "Intuitive Surgical",
    "MU": "Micron Technology",
    "TXN": "Texas Instruments",
    "AMGN": "Amgen Inc.",
    "HON": "Honeywell International",
    "INTU": "Intuit Inc.",
    "BKNG": "Booking Holdings",
    "SBUX": "Starbucks Corp.",
    "VRTX": "Vertex Pharmaceuticals",
    "MDLZ": "Mondelez International",
    "REGN": "Regeneron Pharmaceuticals",
    "PANW": "Palo Alto Networks",
    "SNPS": "Synopsys Inc.",
    "ASML": "ASML Holding",
    "LRCX": "Lam Research",
    "ADI": "Analog Devices",
    "MELI": "MercadoLibre Inc.",
    "CDNS": "Cadence Design Systems",
    "KLAC": "KLA Corp.",
    "PDD": "PDD Holdings Inc.",
    "PYPL": "PayPal Holdings",
    "PLTR": "Palantir Technologies",
    "ARM": "Arm Holdings",
    "SAP.DE": "SAP SE",
    "ALV.DE": "Allianz SE",
    "RKLB": "Rocket Lab USA",
    "COIN": "Coinbase Global",
}

FALLBACK_MOVERS: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
    "1d": {
        "gainers": [
            {"ticker": "NVDA", "name": "NVIDIA Corp.", "price": 128.50, "change": 3.42, "change_1d": 3.42, "change_1w": 5.10, "change_1m": 8.40, "trend_context": "Market momentum", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "META", "name": "Meta Platforms Inc.", "price": 512.20, "change": 2.65, "change_1d": 2.65, "change_1w": 4.20, "change_1m": 7.10, "trend_context": "Market momentum", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "AAPL", "name": "Apple Inc.", "price": 224.80, "change": 1.78, "change_1d": 1.78, "change_1w": 2.30, "change_1m": 4.50, "trend_context": "Market momentum", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "MSFT", "name": "Microsoft Corp.", "price": 448.60, "change": 1.35, "change_1d": 1.35, "change_1w": 1.90, "change_1m": 3.80, "trend_context": "Market momentum", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "AMZN", "name": "Amazon.com Inc.", "price": 186.40, "change": 1.12, "change_1d": 1.12, "change_1w": 3.10, "change_1m": 5.20, "trend_context": "Market momentum", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "ASML", "name": "ASML Holding", "price": 845.00, "change": 0.95, "change_1d": 0.95, "change_1w": 2.50, "change_1m": 4.10, "trend_context": "Market momentum", "source": "market_snapshot", "data_as_of": "", "fallback": True},
        ],
        "losers": [
            {"ticker": "TSLA", "name": "Tesla Inc.", "price": 218.40, "change": -2.85, "change_1d": -2.85, "change_1w": -4.10, "change_1m": -6.20, "trend_context": "Market pullback", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "INTC", "name": "Intel Corp.", "price": 20.80, "change": -2.15, "change_1d": -2.15, "change_1w": -5.30, "change_1m": -8.40, "trend_context": "Market pullback", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "AMD", "name": "Advanced Micro Devices", "price": 142.30, "change": -1.65, "change_1d": -1.65, "change_1w": -2.90, "change_1m": -4.80, "trend_context": "Market pullback", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "QCOM", "name": "Qualcomm Inc.", "price": 164.20, "change": -1.20, "change_1d": -1.20, "change_1w": -1.80, "change_1m": -3.20, "trend_context": "Market pullback", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "PYPL", "name": "PayPal Holdings", "price": 68.50, "change": -0.85, "change_1d": -0.85, "change_1w": -1.40, "change_1m": -2.10, "trend_context": "Market pullback", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "CSCO", "name": "Cisco Systems Inc.", "price": 54.10, "change": -0.60, "change_1d": -0.60, "change_1w": -0.90, "change_1m": -1.50, "trend_context": "Market pullback", "source": "market_snapshot", "data_as_of": "", "fallback": True},
        ],
    },
    "1w": {
        "gainers": [
            {"ticker": "NVDA", "name": "NVIDIA Corp.", "price": 128.50, "change": 6.80, "change_1d": 3.42, "change_1w": 6.80, "change_1m": 8.40, "trend_context": "Market momentum", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "META", "name": "Meta Platforms Inc.", "price": 512.20, "change": 5.40, "change_1d": 2.65, "change_1w": 5.40, "change_1m": 7.10, "trend_context": "Market momentum", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "AAPL", "name": "Apple Inc.", "price": 224.80, "change": 3.20, "change_1d": 1.78, "change_1w": 3.20, "change_1m": 4.50, "trend_context": "Market momentum", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "MSFT", "name": "Microsoft Corp.", "price": 448.60, "change": 2.90, "change_1d": 1.35, "change_1w": 2.90, "change_1m": 3.80, "trend_context": "Market momentum", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "AMZN", "name": "Amazon.com Inc.", "price": 186.40, "change": 2.70, "change_1d": 1.12, "change_1w": 2.70, "change_1m": 5.20, "trend_context": "Market momentum", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "AVGO", "name": "Broadcom Inc.", "price": 168.00, "change": 2.30, "change_1d": 0.85, "change_1w": 2.30, "change_1m": 4.60, "trend_context": "Market momentum", "source": "market_snapshot", "data_as_of": "", "fallback": True},
        ],
        "losers": [
            {"ticker": "INTC", "name": "Intel Corp.", "price": 20.80, "change": -6.20, "change_1d": -2.15, "change_1w": -6.20, "change_1m": -8.40, "trend_context": "Market pullback", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "TSLA", "name": "Tesla Inc.", "price": 218.40, "change": -5.10, "change_1d": -2.85, "change_1w": -5.10, "change_1m": -6.20, "trend_context": "Market pullback", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "AMD", "name": "Advanced Micro Devices", "price": 142.30, "change": -3.80, "change_1d": -1.65, "change_1w": -3.80, "change_1m": -4.80, "trend_context": "Market pullback", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "PYPL", "name": "PayPal Holdings", "price": 68.50, "change": -2.60, "change_1d": -0.85, "change_1w": -2.60, "change_1m": -2.10, "trend_context": "Market pullback", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "QCOM", "name": "Qualcomm Inc.", "price": 164.20, "change": -2.10, "change_1d": -1.20, "change_1w": -2.10, "change_1m": -3.20, "trend_context": "Market pullback", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "CSCO", "name": "Cisco Systems Inc.", "price": 54.10, "change": -1.50, "change_1d": -0.60, "change_1w": -1.50, "change_1m": -1.50, "trend_context": "Market pullback", "source": "market_snapshot", "data_as_of": "", "fallback": True},
        ],
    },
    "1m": {
        "gainers": [
            {"ticker": "NVDA", "name": "NVIDIA Corp.", "price": 128.50, "change": 14.50, "change_1d": 3.42, "change_1w": 6.80, "change_1m": 14.50, "trend_context": "Market momentum", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "META", "name": "Meta Platforms Inc.", "price": 512.20, "change": 11.20, "change_1d": 2.65, "change_1w": 5.40, "change_1m": 11.20, "trend_context": "Market momentum", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "PLTR", "name": "Palantir Technologies", "price": 32.40, "change": 9.80, "change_1d": 1.80, "change_1w": 4.50, "change_1m": 9.80, "trend_context": "Market momentum", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "AMZN", "name": "Amazon.com Inc.", "price": 186.40, "change": 7.30, "change_1d": 1.12, "change_1w": 2.70, "change_1m": 7.30, "trend_context": "Market momentum", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "MSFT", "name": "Microsoft Corp.", "price": 448.60, "change": 5.90, "change_1d": 1.35, "change_1w": 2.90, "change_1m": 5.90, "trend_context": "Market momentum", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "AAPL", "name": "Apple Inc.", "price": 224.80, "change": 5.20, "change_1d": 1.78, "change_1w": 3.20, "change_1m": 5.20, "trend_context": "Market momentum", "source": "market_snapshot", "data_as_of": "", "fallback": True},
        ],
        "losers": [
            {"ticker": "INTC", "name": "Intel Corp.", "price": 20.80, "change": -12.40, "change_1d": -2.15, "change_1w": -6.20, "change_1m": -12.40, "trend_context": "Market pullback", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "TSLA", "name": "Tesla Inc.", "price": 218.40, "change": -9.10, "change_1d": -2.85, "change_1w": -5.10, "change_1m": -9.10, "trend_context": "Market pullback", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "AMD", "name": "Advanced Micro Devices", "price": 142.30, "change": -6.50, "change_1d": -1.65, "change_1w": -3.80, "change_1m": -6.50, "trend_context": "Market pullback", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "PYPL", "name": "PayPal Holdings", "price": 68.50, "change": -4.20, "change_1d": -0.85, "change_1w": -2.60, "change_1m": -4.20, "trend_context": "Market pullback", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "QCOM", "name": "Qualcomm Inc.", "price": 164.20, "change": -3.80, "change_1d": -1.20, "change_1w": -2.10, "change_1m": -3.80, "trend_context": "Market pullback", "source": "market_snapshot", "data_as_of": "", "fallback": True},
            {"ticker": "CSCO", "name": "Cisco Systems Inc.", "price": 54.10, "change": -2.40, "change_1d": -0.60, "change_1w": -1.50, "change_1m": -2.40, "trend_context": "Market pullback", "source": "market_snapshot", "data_as_of": "", "fallback": True},
        ],
    },
}

class DiscoveryService:
    _equity_candidate_cache: tuple[List[Dict[str, Any]], datetime] | None = None

    def __init__(self):
        # Sample universes for scanning
        self.tech_universe = ["NVDA", "AMD", "TSLA", "PLTR", "SMCI", "ARM", "CELH", "MSFT", "AAPL", "GOOGL", "META", "NFLX"]
        self.small_cap_watch = ["FRGT", "SOFI", "PATH", "MSTR", "HOOD", "UPST", "OKLO", "S", "LUNR", "RKLB"]
        self.future_star_watch = [
            "RKLB", "LUNR", "SOFI", "HOOD", "PATH", "OKLO", "S", "IONQ", "RGTI", "ASTS",
            "HIMS", "CELH", "DUOL", "TTD", "CRSP", "BEAM", "RXRX", "ENVX", "JOBY", "ACHR",
        ]
        self.dividend_watch = ["PEP", "KO", "PG", "JNJ", "MMM", "O", "MAIN", "XOM", "CVX", "ABBV", "T", "VZ", "MO", "PM"]
        self.moonshot_watch = ["FRGT", "SOFI", "PATH", "MSTR", "HOOD", "UPST", "AI", "PLTR", "ARM", "OKLO", "LUNR", "DNA"]
        self.crypto_universe = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "DOGE-USD", "DOT-USD"]
        self.commodity_watch = ["GC=F", "CL=F", "HG=F", "SI=F"] # Gold, Oil, Copper, Silver
        self.etf_universe = ["VOO", "QQQ", "VTI", "SCHD", "VYM", "VT", "VWO", "VTV", "VUG", "IWM", "EEM", "GLD", "VNQ"]
        
        # Broad universe for dynamic mover discovery (Nasdaq 100 type)
        self.market_movers_universe = [
            "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "AVGO", "ADBE", "COST",
            "PEP", "NFLX", "AMD", "TMUS", "INTC", "CSCO", "CMCSA", "AMAT", "QCOM", "ISRG",
            "MU", "TXN", "AMGN", "HON", "INTU", "BKNG", "SBUX", "VRTX", "MDLZ", "REGN",
            "PANW", "SNPS", "ASML", "LRCX", "ADI", "MELI", "CDNS", "KLAC", "PDD", "PYPL"
        ]
        self.paper_equity_universe = [
            # US Mega & Large Cap Tech / AI / Semis
            "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "AVGO", "AMD", "NFLX", "CRM", "ORCL", "NOW", "PANW", "CRWD", "MU", "QCOM", "AMAT", "LRCX", "KLAC",
            # US Financials, Industrials, Energy, Healthcare & Consumer
            "JPM", "GS", "V", "MA", "BRK-B", "LLY", "UNH", "JNJ", "ABBV", "ISRG", "VRTX", "XOM", "CVX", "COST", "WMT", "KO", "PG", "CAT", "GE", "RTX", "HON", "UNP",
            # Europe / DAX / MDAX & Global Leaders
            "SAP.DE", "SIE.DE", "ALV.DE", "RHM.DE", "AIR.PA", "ASML", "MC.PA", "NVO", "TSM", "MELI",
        ]
        self.paper_small_cap_universe = [
            "RKLB", "LUNR", "PATH", "OKLO", "S", "IONQ",
            "RGTI", "ASTS", "HIMS", "ENVX", "JOBY", "ACHR",
            "SOFI", "HOOD", "CELH", "DUOL", "UPST", "CAVA",
        ]

    def _moonshot_fallbacks(self) -> List[Dict[str, Any]]:
        """Stable fallback so the AI Chancen rail never renders empty."""
        return [
            {
                "ticker": "PLTR",
                "name": "Palantir Technologies Inc.",
                "growth": 22.0,
                "market_cap": 0,
                "trend_context": "AI platform demand",
                "score": 88,
                "reason": "Profitable AI software compounder, but valuation risk is high.",
            },
            {
                "ticker": "ARM",
                "name": "Arm Holdings plc",
                "growth": 18.0,
                "market_cap": 0,
                "trend_context": "AI chip architecture",
                "score": 84,
                "reason": "AI/edge semiconductor exposure with premium multiple risk.",
            },
            {
                "ticker": "RKLB",
                "name": "Rocket Lab USA, Inc.",
                "growth": 28.0,
                "market_cap": 0,
                "trend_context": "Space infrastructure",
                "score": 82,
                "reason": "High-growth space infrastructure setup; execution risk remains elevated.",
            },
        ]

    def _etf_fallbacks(self) -> List[Dict[str, Any]]:
        return [
            {
                "ticker": "VOO",
                "name": "Vanguard S&P 500 ETF",
                "price": None,
                "change": 0,
                "ter": 0.0003,
                "total_assets": None,
                "category": "US Large Blend",
                "trend_context": "Fallback core ETF; provider data temporarily unavailable.",
                "source": None,
                "data_as_of": None,
                "fallback": True,
            },
            {
                "ticker": "QQQ",
                "name": "Invesco QQQ Trust",
                "price": None,
                "change": 0,
                "ter": 0.002,
                "total_assets": None,
                "category": "US Growth",
                "trend_context": "Fallback Nasdaq ETF; verify live quote before action.",
                "source": None,
                "data_as_of": None,
                "fallback": True,
            },
            {
                "ticker": "SCHD",
                "name": "Schwab U.S. Dividend Equity ETF",
                "price": None,
                "change": 0,
                "ter": 0.0006,
                "total_assets": None,
                "category": "Dividend",
                "trend_context": "Fallback dividend ETF; use as watch item only.",
                "source": None,
                "data_as_of": None,
                "fallback": True,
            },
        ]

    def _market_mover_fallbacks(self, side: str = "gainers") -> List[Dict[str, Any]]:
        data = [
            ("NVDA", "NVIDIA Corporation", 0.0, "AI large-cap watch"),
            ("AAPL", "Apple Inc.", 0.0, "Mega-cap quality watch"),
            ("SPY", "SPDR S&P 500 ETF Trust", 0.0, "Broad market benchmark"),
        ]
        return [
            {
                "ticker": ticker,
                "name": name,
                "price": None,
                "change": change,
                "change_1d": change,
                "change_1w": change,
                "change_1m": change,
                "trend_context": f"Fallback {side}; live market mover provider unavailable.",
            }
            for ticker, name, change, _context in data
        ]

    def _sentiment_heatmap_fallbacks(self) -> List[Dict[str, Any]]:
        sectors = [
            ("Artificial Intelligence", ["NVDA", "PLTR", "ARM"], 0.15),
            ("Semiconductors", ["AMD", "TSM", "AVGO"], 0.05),
            ("USA", ["AAPL", "MSFT", "AMZN"], 0.0),
            ("Europe", ["SAP", "ASML", "SIE.DE"], 0.0),
            ("Energy", ["XOM", "CVX", "SHEL"], -0.05),
        ]
        return [
            {
                "sector": sector,
                "sentiment_score": score,
                "status": "NEUTRAL",
                "strength": 35,
                "fallback": True,
                "hot_stocks": [
                    {"ticker": ticker, "price": None, "change_1w": 0, "name": ticker}
                    for ticker in tickers
                ],
            }
            for sector, tickers, score in sectors
        ]

    @staticmethod
    def _compute_rsi(prices: List[float], period: int = 14) -> Optional[float]:
        if len(prices) <= period:
            return None
        gains = []
        losses = []
        for idx in range(1, len(prices)):
            diff = prices[idx] - prices[idx - 1]
            gains.append(max(diff, 0.0))
            losses.append(max(-diff, 0.0))
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for idx in range(period, len(gains)):
            avg_gain = ((avg_gain * (period - 1)) + gains[idx]) / period
            avg_loss = ((avg_loss * (period - 1)) + losses[idx]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def _fetch_stock_basic_sync(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Fast synchronous stock price data extraction without heavy yfinance info calls."""
        try:
            f = DataFetcher(ticker)
            p = f.get_price_data()
            current_price = p.get("current_price")
            if not current_price or float(current_price) <= 0:
                return None

            c_1d = p.get("change_1d")
            c_1w = p.get("change_1w")
            c_1m = p.get("change_1m")

            name = UNIVERSE_NAMES.get(ticker) or ticker
            return {
                "ticker": ticker,
                "name": name,
                "price": float(current_price),
                "change": float(c_1w) if c_1w is not None else 0.0,
                "change_1d": float(c_1d) if c_1d is not None else None,
                "change_1w": float(c_1w) if c_1w is not None else None,
                "change_1m": float(c_1m) if c_1m is not None else None,
                "trend_context": "Market momentum",
                "source": "yahoo_finance",
                "data_as_of": datetime.now().isoformat(),
                "fallback": False,
            }
        except Exception:
            return None

    async def _fetch_stock_basic(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Helper to fetch basic stock info in parallel."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_stock_basic_sync, ticker)

    async def _scan_market_movers_pool(self) -> List[Dict[str, Any]]:
        """Fetch unified universe prices once and cache for all windows and types."""
        now = datetime.now()
        if hasattr(self, "_movers_pool_cache") and self._movers_pool_cache is not None:
            cache_data, ts = self._movers_pool_cache
            if (now - ts).total_seconds() < 180:
                return cache_data

        if not hasattr(self, "_movers_lock"):
            import asyncio
            self._movers_lock = asyncio.Lock()

        async with self._movers_lock:
            if hasattr(self, "_movers_pool_cache") and self._movers_pool_cache is not None:
                cache_data, ts = self._movers_pool_cache
                if (now - ts).total_seconds() < 180:
                    return cache_data

            import asyncio
            from concurrent.futures import ThreadPoolExecutor

            # Use top 24 liquid universe stocks
            scan_pool = [
                "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "AMD",
                "NFLX", "AVGO", "ADBE", "COST", "INTC", "CSCO", "QCOM", "AMAT",
                "MU", "ARM", "PLTR", "ASML", "SAP.DE", "ALV.DE", "RKLB", "COIN",
            ]

            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [loop.run_in_executor(executor, self._fetch_stock_basic_sync, t) for t in scan_pool]
                raw_results = await asyncio.gather(*futures, return_exceptions=True)

            results = [r for r in raw_results if isinstance(r, dict) and r.get("price")]
            if len(results) >= 4:
                self._movers_pool_cache = (results, now)
                return results

            if hasattr(self, "_movers_pool_cache") and self._movers_pool_cache is not None:
                return self._movers_pool_cache[0]

            return results

    async def get_market_movers(self, type: str = 'gainers', window: str = "1w") -> List[Dict[str, Any]]:
        """Identify real-time top gainers or losers from the selection universe with caching."""
        normalized_window = (window or "1w").lower()
        if normalized_window not in {"1d", "1w", "1m"}:
            normalized_window = "1w"
        change_key = {
            "1d": "change_1d",
            "1w": "change_1w",
            "1m": "change_1m",
        }[normalized_window]

        is_gainers = (type == 'gainers')

        try:
            pool = await self._scan_market_movers_pool()
        except Exception:
            pool = []

        valid_items = []
        for item in pool:
            val = item.get(change_key)
            if val is not None:
                item_copy = dict(item)
                item_copy["change"] = float(val)
                valid_items.append(item_copy)

        if len(valid_items) >= 4:
            if is_gainers:
                # Filter positive or take top performers
                positives = [it for it in valid_items if (it["change"] or 0) > 0]
                pool_to_sort = positives if len(positives) >= 3 else valid_items
                pool_to_sort.sort(key=lambda x: x["change"] or 0, reverse=True)
                return pool_to_sort[:8]
            else:
                # Filter negative or take worst performers
                negatives = [it for it in valid_items if (it["change"] or 0) < 0]
                pool_to_sort = negatives if len(negatives) >= 3 else valid_items
                pool_to_sort.sort(key=lambda x: x["change"] or 0, reverse=False)
                return pool_to_sort[:8]

        # Resilient fallback if live market feeds are unreachable or offline
        fallbacks = FALLBACK_MOVERS.get(normalized_window) or FALLBACK_MOVERS["1d"]
        fallback_list = fallbacks.get("gainers" if is_gainers else "losers", [])
        return fallback_list[:8]

    async def run_screener(
        self,
        rsi_max: Optional[float] = None,
        market_cap_min: Optional[float] = None,
        market_cap_max: Optional[float] = None,
        sector: Optional[str] = None,
        high52_proximity: Optional[float] = None,
        low52_proximity: Optional[float] = None,
        limit: int = 35,
    ) -> List[Dict[str, Any]]:
        """Filter stocks by RSI, market cap, sector and 52-week positioning."""
        import asyncio

        symbols = list(dict.fromkeys(self.market_movers_universe + self.tech_universe))
        scan_pool = symbols[: max(10, min(limit, len(symbols)))]
        sector_filter = (sector or "").strip().lower()

        async def fetch_screen_item(ticker: str) -> Optional[Dict[str, Any]]:
            try:
                def fetch() -> Optional[Dict[str, Any]]:
                    fetcher = DataFetcher(ticker)
                    info = fetcher.info or {}
                    price_data = fetcher.get_price_data()
                    history = fetcher.stock.history(period="6mo", interval="1d")
                    closes = [float(val) for val in list(history.get("Close", [])) if val is not None]
                    rsi = self._compute_rsi(closes, 14)

                    current_price = price_data.get("current_price")
                    high_52w = price_data.get("high_52w")
                    low_52w = price_data.get("low_52w")
                    from_high = None
                    from_low = None
                    if current_price and high_52w:
                        from_high = ((high_52w - current_price) / high_52w) * 100
                    if current_price and low_52w:
                        from_low = ((current_price - low_52w) / low_52w) * 100

                    return {
                        "ticker": ticker,
                        "name": info.get("longName") or info.get("shortName") or ticker,
                        "sector": info.get("sector") or "Unknown",
                        "price": current_price,
                        "change_1w": price_data.get("change_1w"),
                        "market_cap": info.get("marketCap"),
                        "rsi_14": rsi,
                        "high_52w": high_52w,
                        "low_52w": low_52w,
                        "high52_proximity": from_high,
                        "low52_proximity": from_low,
                    }

                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, fetch)
            except Exception:
                return None

        tasks = [fetch_screen_item(symbol) for symbol in scan_pool]
        results = [item for item in await asyncio.gather(*tasks) if item]

        def pass_filters(item: Dict[str, Any]) -> bool:
            if sector_filter and sector_filter not in str(item.get("sector", "")).lower():
                return False
            market_cap = item.get("market_cap")
            if market_cap_min is not None and (market_cap is None or float(market_cap) < float(market_cap_min)):
                return False
            if market_cap_max is not None and (market_cap is None or float(market_cap) > float(market_cap_max)):
                return False
            rsi = item.get("rsi_14")
            if rsi_max is not None and (rsi is None or float(rsi) > float(rsi_max)):
                return False
            near_high = item.get("high52_proximity")
            if high52_proximity is not None and (near_high is None or float(near_high) > float(high52_proximity)):
                return False
            near_low = item.get("low52_proximity")
            if low52_proximity is not None and (near_low is None or float(near_low) > float(low52_proximity)):
                return False
            return True

        filtered = [item for item in results if pass_filters(item)]
        filtered.sort(
            key=lambda item: (
                999 if item.get("rsi_14") is None else item.get("rsi_14"),
                -float(item.get("market_cap") or 0),
            )
        )
        return filtered[: max(5, min(limit, 100))]

    async def get_trending(self) -> List[Dict[str, Any]]:
        """Identify trending stocks with parallel fetching."""
        pool = random.sample(self.tech_universe, min(len(self.tech_universe), 8))
        import asyncio
        tasks = [self._fetch_stock_basic(t) for t in pool]
        results = [r for r in await asyncio.gather(*tasks) if r]
        for r in results:
             r["trend_context"] = random.choice(["Institutional Accumulation", "High Social Volume", "Technical Breakout"])
        return results

    async def get_rebounds(self) -> List[Dict[str, Any]]:
        """Find 'Data Dumps' - stocks that fell significantly but have rebound potential."""
        pool = ["AAPL", "GOOGL", "MSFT", "AMZN", "META", "NFLX", "TSLA", "PYPL", "INTC", "SBUX", "DIS", "BA", "NKE"]
        scanned = random.sample(pool, min(len(pool), 8))
        
        async def fetch_rebound(ticker):
            try:
                def fetch():
                    f = DataFetcher(ticker)
                    p = f.get_price_data()
                    if p.get("change_1w", 0) < -7 or p.get("change_1y", 0) < -20:
                        fund = f.get_fundamentals()
                        if fund.get("profit_margin", 0) > 0.05:
                            return {
                                "ticker": ticker,
                                "name": f.info.get("longName", ticker),
                                "drawdown": p.get("change_1w"),
                                "reason": "Oversold Quality Stock",
                                "score": 70 + (abs(p.get("change_1w", 0)) * 1.5)
                            }
                    return None
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, fetch)
            except: return None

        import asyncio
        tasks = [fetch_rebound(t) for t in scanned]
        results = [r for r in await asyncio.gather(*tasks) if r]
        return sorted(results, key=lambda x: x['score'], reverse=True)

    async def get_small_caps(self) -> List[Dict[str, Any]]:
        """Identify high-potential small-cap stocks."""
        async def fetch_small(ticker):
             try:
                def fetch():
                    f = DataFetcher(ticker)
                    info = f.info
                    mcap = info.get("marketCap", 0)
                    if 0 < mcap < 10e9:
                        fund = f.get_fundamentals()
                        growth = fund.get("revenue_growth", 0)
                        if growth and growth > 0.10:
                            return {
                                "ticker": ticker,
                                "name": info.get("longName", ticker),
                                "market_cap": mcap,
                                "growth": growth * 100,
                                "score": 90
                            }
                    return None
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, fetch)
             except: return None

        import asyncio
        tasks = [fetch_small(t) for t in self.small_cap_watch]
        results = [r for r in await asyncio.gather(*tasks) if r]
        
        # Fallback if universe is empty
        if not results:
            fallback_tasks = [fetch_small(t) for t in ["SOFI", "HOOD", "PATH", "PLTR", "MSTR"]]
            results = [r for r in await asyncio.gather(*fallback_tasks) if r]
            
        return results

    async def get_paper_equity_candidates(self) -> List[Dict[str, Any]]:
        """Return a deterministic, diversified stock universe with observable quality and trend data.

        Uses a 3-stage institutional funnel:
          Stage 1: Vectorized batch history download via SharedMarketDataPool (float32) + SPY benchmark RS.
          Stage 2: Compute technical edge metrics (RS vs SPY, Down-Day Resilience, VCP contraction, RVOL).
          Stage 3: Enrich top candidates with cached fundamentals (12h TTL) and bounded concurrency.
        """
        import asyncio
        from src.memory_optimizer import get_shared_pool

        cached = self.__class__._equity_candidate_cache
        now = datetime.now()
        if cached and (now - cached[1]).total_seconds() < 600:
            return cached[0]

        try:
            from src.storage import PortfolioManager
            persisted_rows = PortfolioManager().get_market_scanner_cache("paper_equity_candidates", max_age_seconds=600)
            if isinstance(persisted_rows, list) and persisted_rows:
                self.__class__._equity_candidate_cache = (persisted_rows, now)
                return persisted_rows
        except Exception:
            pass

        research_universe = list(dict.fromkeys([*self.paper_equity_universe, *self.paper_small_cap_universe]))
        pool = get_shared_pool()

        # Stage 1: Batch fetch histories (including SPY for benchmark relative strength)
        batch_symbols = ["SPY", *research_universe]
        histories = await asyncio.to_thread(
            pool.get_batch_history,
            batch_symbols,
            "6mo",
            "1d",
            300,
        )

        spy_df = histories.get("SPY")
        spy_change_1m = 0.0
        spy_change_3m = 0.0
        spy_down_days_mask = None
        if spy_df is not None and not getattr(spy_df, "empty", True) and "Close" in spy_df.columns:
            spy_closes = spy_df["Close"].dropna()
            if len(spy_closes) >= 21:
                spy_change_1m = ((float(spy_closes.iloc[-1]) / float(spy_closes.iloc[-21])) - 1.0) * 100.0
            if len(spy_closes) >= 61:
                spy_change_3m = ((float(spy_closes.iloc[-1]) / float(spy_closes.iloc[-61])) - 1.0) * 100.0
            spy_rets = spy_closes.pct_change().tail(30)
            spy_down_days_mask = spy_rets[spy_rets < -0.0025].index

        # Stage 2: Fast in-memory technical evaluation
        stage1_rows: List[Dict[str, Any]] = []
        for ticker in research_universe:
            try:
                history = histories.get(ticker)
                if history is None or getattr(history, "empty", True) or len(history) < 55:
                    continue
                closes = history["Close"].dropna()
                volumes = history["Volume"].dropna() if "Volume" in history.columns else closes * 0
                if len(closes) < 55:
                    continue
                last = float(closes.iloc[-1])
                previous = float(closes.iloc[-2])
                close_20 = float(closes.iloc[-21])
                close_60 = float(closes.iloc[-61]) if len(closes) >= 61 else float(closes.iloc[0])
                sma_20 = float(closes.tail(20).mean())
                sma_50 = float(closes.tail(50).mean())
                daily_returns = closes.pct_change().dropna().tail(60)
                volatility = float(daily_returns.std() * (252 ** 0.5) * 100) if len(daily_returns) >= 20 else None
                recent_volume = float(volumes.tail(5).mean()) if len(volumes) >= 5 else 0.0
                base_volume = float(volumes.tail(25).head(20).mean()) if len(volumes) >= 25 else 0.0

                change_1d = ((last / previous) - 1.0) * 100.0 if previous else 0.0
                change_1m = ((last / close_20) - 1.0) * 100.0 if close_20 else 0.0
                change_3m = ((last / close_60) - 1.0) * 100.0 if close_60 else 0.0
                vol_ratio = (recent_volume / base_volume) if base_volume > 0 else 1.0

                # Institutional Edge Metrics:
                # 1. Benchmark Relative Strength (Alpha vs SPY)
                rs_alpha_1m = round(change_1m - spy_change_1m, 2)
                rs_alpha_3m = round(change_3m - spy_change_3m, 2)

                # 2. Down-Day Resilience (Win rate & outperformance on days SPY fell)
                down_day_resilience = 0.0
                if spy_down_days_mask is not None and len(spy_down_days_mask) >= 3:
                    stock_rets_30 = closes.pct_change().tail(35)
                    common_idx = stock_rets_30.index.intersection(spy_down_days_mask)
                    if len(common_idx) >= 2:
                        green_on_red = sum(1 for dt in common_idx if float(stock_rets_30.loc[dt]) >= -0.0005)
                        down_day_resilience = round((green_on_red / len(common_idx)) * 100.0, 1)

                # 3. Volatility Contraction / Pocket Pivot check (5d range vs 20d range)
                vcp_tightness = False
                if len(daily_returns) >= 20:
                    std_5d = float(daily_returns.tail(5).std() or 0)
                    std_20d = float(daily_returns.tail(20).std() or 1)
                    if std_20d > 0 and (std_5d / std_20d) <= 0.72 and last >= sma_20:
                        vcp_tightness = True

                tech_rank_score = (
                    (change_1m * 1.2)
                    + (rs_alpha_1m * 1.4)
                    + (rs_alpha_3m * 0.6)
                    + (12.0 if last > sma_20 else -8.0)
                    + (14.0 if last > sma_50 else -10.0)
                    + min(10.0, max(-4.0, (vol_ratio - 1.0) * 8.0))
                    + (6.0 if vcp_tightness else 0.0)
                    + (down_day_resilience * 0.08)
                )

                stage1_rows.append({
                    "ticker": ticker,
                    "price": last,
                    "change_1d": change_1d,
                    "change_1m": change_1m,
                    "change_3m": change_3m,
                    "rs_alpha_1m": rs_alpha_1m,
                    "rs_alpha_3m": rs_alpha_3m,
                    "down_day_resilience_pct": down_day_resilience,
                    "vcp_tightness": vcp_tightness,
                    "above_sma20": last > sma_20,
                    "above_sma50": last > sma_50,
                    "volume_ratio": vol_ratio,
                    "volatility_annual_pct": volatility,
                    "tech_rank_score": round(tech_rank_score, 2),
                    "data_as_of": history.index[-1].isoformat() if hasattr(history.index[-1], "isoformat") else None,
                })
            except Exception:
                continue

        # Sort by technical edge and only fetch uncached live fundamentals for the top 16 (cached ones are instant for all)
        stage1_rows.sort(key=lambda r: float(r.get("tech_rank_score") or 0), reverse=True)
        live_fetch_allowed = {r["ticker"] for r in stage1_rows[:16]} | set(self.paper_small_cap_universe[:8])
        sem = asyncio.Semaphore(4)

        async def enrich_fundamentals(row: Dict[str, Any]) -> Dict[str, Any]:
            ticker = row["ticker"]
            info = pool.get_cached_fundamentals(ticker)
            if info is None and ticker in live_fetch_allowed:
                async with sem:
                    def _load_info() -> Dict[str, Any]:
                        try:
                            raw_info = yf.Ticker(ticker).info or {}
                            if raw_info:
                                pool.set_cached_fundamentals(ticker, raw_info)
                            return raw_info
                        except Exception:
                            return {}
                    info = await asyncio.to_thread(_load_info)
            info = info or {}
            is_small_universe = ticker in self.paper_small_cap_universe
            default_mcap = 2_800_000_000 if is_small_universe else 85_000_000_000
            return {
                "ticker": ticker,
                "name": info.get("longName") or info.get("shortName") or UNIVERSE_NAMES.get(ticker) or ticker,
                "sector": info.get("sector") or ("Technology" if ticker in self.tech_universe else "Diversified"),
                "market_cap": info.get("marketCap") or default_mcap,
                "price": row["price"],
                "change_1d": row["change_1d"],
                "change_1m": row["change_1m"],
                "change_3m": row["change_3m"],
                "rs_alpha_1m": row["rs_alpha_1m"],
                "rs_alpha_3m": row["rs_alpha_3m"],
                "down_day_resilience_pct": row["down_day_resilience_pct"],
                "vcp_tightness": row["vcp_tightness"],
                "above_sma20": row["above_sma20"],
                "above_sma50": row["above_sma50"],
                "volume_ratio": row["volume_ratio"],
                "volatility_annual_pct": row["volatility_annual_pct"],
                "tech_rank_score": row["tech_rank_score"],
                "revenue_growth_pct": (
                    float(info.get("revenueGrowth")) * 100 if isinstance(info.get("revenueGrowth"), (int, float)) else None
                ),
                "earnings_growth_pct": (
                    float(info.get("earningsGrowth")) * 100 if isinstance(info.get("earningsGrowth"), (int, float)) else None
                ),
                "profit_margin_pct": (
                    float(info.get("profitMargins")) * 100 if isinstance(info.get("profitMargins"), (int, float)) else None
                ),
                "source_label": "Yahoo Finance market/fundamental snapshot",
                "data_as_of": row["data_as_of"],
            }

        rows = [row for row in await asyncio.gather(*(enrich_fundamentals(r) for r in stage1_rows)) if row]
        self.__class__._equity_candidate_cache = (rows, now)
        try:
            from src.storage import PortfolioManager
            PortfolioManager().set_market_scanner_cache("paper_equity_candidates", rows)
        except Exception:
            pass
        try:
            from src.forecast_learning_service import ForecastLearningService
            await asyncio.to_thread(ForecastLearningService().record_market_scanner_forecasts, rows)
        except Exception:
            pass
        return rows

    def _score_future_star_news(self, news: List[Dict[str, Any]]) -> Dict[str, Any]:
        positive_terms = {
            "beat", "growth", "contract", "partnership", "approval", "launch", "guidance",
            "raises", "upgrade", "expands", "record", "profit", "margin", "revenue",
            "backlog", "customer", "deal", "ai", "satellite", "space", "platform",
        }
        risk_terms = {
            "offering", "dilution", "sec investigation", "lawsuit", "downgrade", "miss",
            "delay", "bankruptcy", "cash burn", "going concern", "short report",
        }
        catalyst_hits: List[str] = []
        risk_hits: List[str] = []
        for item in news[:8]:
            title = str(item.get("title") or item.get("headline") or "")
            normalized = title.lower()
            if any(term in normalized for term in positive_terms):
                catalyst_hits.append(title)
            if any(term in normalized for term in risk_terms):
                risk_hits.append(title)
        return {
            "score": min(30, len(catalyst_hits) * 10) - min(25, len(risk_hits) * 12),
            "catalysts": catalyst_hits[:3],
            "risks": risk_hits[:2],
        }

    def _future_star_grade(
        self,
        revenue_growth: float | None,
        profit_margin: float | None,
        free_cashflow: float | None,
        debt_to_equity: float | None,
        change_1m: float | None,
        volume_ratio: float | None,
        news_score: Dict[str, Any],
    ) -> Dict[str, Any]:
        growth = revenue_growth or 0
        margin = profit_margin or 0
        cashflow = free_cashflow or 0
        monthly_change = change_1m or 0
        volume = volume_ratio or 1
        catalysts = news_score.get("catalysts") or []
        risks = news_score.get("risks") or []

        checks = {
            "growth": growth >= 0.18,
            "catalyst": bool(catalysts),
            "cash_quality": margin > 0 or cashflow > 0,
            "confirmation": monthly_change > 0 and volume >= 1.05,
            "balance_risk": debt_to_equity is None or debt_to_equity <= 180,
            "risk_clean": not risks,
        }

        score = 25
        score += min(26, max(0, growth) * 95)
        score += 12 if checks["cash_quality"] else -10
        score += 10 if monthly_change > 0 else -8
        score += 8 if volume >= 1.15 else 4 if volume >= 1.05 else -4
        score += news_score.get("score", 0)
        if debt_to_equity is not None and debt_to_equity > 180:
            score -= 12
        if risks:
            score -= min(18, len(risks) * 9)
        score = max(0, min(100, round(score)))

        passed_count = sum(1 for passed in checks.values() if passed)
        if checks["growth"] and checks["catalyst"] and checks["cash_quality"] and checks["confirmation"] and checks["balance_risk"] and score >= 76:
            gate = "passed"
        elif score >= 66 and checks["catalyst"] and passed_count >= 4:
            gate = "candidate"
        else:
            gate = "watchlist"

        reasons = []
        if not checks["growth"]:
            reasons.append("Umsatzwachstum noch nicht stark genug")
        if not checks["catalyst"]:
            reasons.append("harter News-Katalysator fehlt")
        if not checks["cash_quality"]:
            reasons.append("Cashflow/Profitabilitaet noch schwach")
        if not checks["confirmation"]:
            reasons.append("Kurs/Volumen bestaetigen noch nicht sauber")
        if not checks["balance_risk"]:
            reasons.append("Debt-Risiko zu hoch")
        if risks:
            reasons.append("Risiko-News aktiv")

        return {
            "score": score,
            "quality_gate": gate,
            "gate_checks": checks,
            "gate_passed": passed_count,
            "gate_total": len(checks),
            "gate_reason": " | ".join(reasons[:3]) if reasons else "Growth, Katalysator, Qualitaet und Bestaetigung passen zusammen.",
        }

    async def get_future_stars(self) -> List[Dict[str, Any]]:
        """Find smaller stocks with real future-star potential after news and fundamentals checks."""
        import asyncio

        async def fetch_candidate(ticker: str) -> Optional[Dict[str, Any]]:
            try:
                def fetch() -> Optional[Dict[str, Any]]:
                    f = DataFetcher(ticker)
                    info = f.info or {}
                    market_cap = info.get("marketCap") or 0
                    if not market_cap or market_cap > 35e9:
                        return None
                    price = f.get_price_data_fast()
                    fund = f.get_fundamentals()
                    news = f.get_news()
                    revenue_growth = fund.get("revenue_growth") or 0
                    profit_margin = fund.get("profit_margin") or 0
                    free_cashflow = fund.get("free_cashflow") or 0
                    debt_to_equity = fund.get("debt_to_equity")
                    news_score = self._score_future_star_news(news if isinstance(news, list) else [])
                    change_1m = price.get("change_1m") or 0
                    volume_context = f.get_volatility_data().get("volume_ratio") or 1

                    grade = self._future_star_grade(
                        revenue_growth,
                        profit_margin,
                        free_cashflow,
                        debt_to_equity,
                        change_1m,
                        volume_context,
                        news_score,
                    )
                    score = grade["score"]
                    if score < 62 and not news_score["catalysts"]:
                        return None
                    return {
                        "ticker": ticker,
                        "name": info.get("longName") or info.get("shortName") or ticker,
                        "price": price.get("current_price"),
                        "change": change_1m,
                        "market_cap": market_cap,
                        "growth": revenue_growth * 100 if revenue_growth is not None else None,
                        "profit_margin": profit_margin * 100 if profit_margin is not None else None,
                        "free_cashflow": free_cashflow,
                        "volume_ratio": volume_context,
                        "score": score,
                        "trend_context": f"Future-Star Gate: {grade['gate_passed']}/{grade['gate_total']} Checks bestanden.",
                        "reason": news_score["catalysts"][0] if news_score["catalysts"] else "Kleinerer Growth-Wert mit Daten-Setup, aber News-Katalysator noch beobachten.",
                        "catalysts": news_score["catalysts"],
                        "risk_flags": news_score["risks"],
                        "quality_gate": grade["quality_gate"],
                        "gate_checks": grade["gate_checks"],
                        "gate_passed": grade["gate_passed"],
                        "gate_total": grade["gate_total"],
                        "gate_reason": grade["gate_reason"],
                    }
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, fetch)
            except Exception:
                return None

        tasks = [fetch_candidate(ticker) for ticker in self.future_star_watch[:20]]
        results = [item for item in await asyncio.gather(*tasks) if item]
        return sorted(results, key=lambda item: (item.get("quality_gate") != "passed", -(item.get("score") or 0)))[:10]

    async def get_cryptos(self) -> List[Dict[str, Any]]:
        import asyncio
        tasks = [self._fetch_stock_basic(t) for t in self.crypto_universe]
        results = [r for r in await asyncio.gather(*tasks) if r]
        for r in results: r["trend_context"] = "High volatility"
        return results

    async def get_commodities(self) -> List[Dict[str, Any]]:
        import asyncio
        tasks = [self._fetch_stock_basic(t) for t in self.commodity_watch]
        results = [r for r in await asyncio.gather(*tasks) if r]
        for r in results: r["trend_context"] = "Macro hedge"
        return results

    async def get_etfs(self) -> List[Dict[str, Any]]:
        """Fetch popular ETFs with TER and assets info."""
        # Paper candidates must be reproducible. Provider results may change, the
        # scanned universe and ordering must not change randomly between runs.
        pool = self.etf_universe[:12]
        async def fetch_etf_data(ticker):
            try:
                def fetch():
                    f = DataFetcher(ticker)
                    p = f.get_price_data()
                    fund = f.get_fundamentals()
                    return {
                        "ticker": ticker,
                        "name": f.info.get("longName", ticker),
                        "price": p.get("current_price"),
                        "change": p.get("change_1w"),
                        "ter": fund.get("expense_ratio"),
                        "total_assets": fund.get("total_assets"),
                        "category": fund.get("category"),
                        "trend_context": f"Kategorie: {fund.get('category', 'Global')}",
                        "source": "yahoo_finance",
                        "data_as_of": datetime.utcnow().isoformat(),
                        "fallback": False,
                    }
                import asyncio
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, fetch)
            except: return None

        import asyncio
        tasks = [fetch_etf_data(t) for t in pool]
        results = [r for r in await asyncio.gather(*tasks) if r]
        return results or self._etf_fallbacks()

    async def get_dividend_aristocrats(self) -> List[Dict[str, Any]]:
        async def fetch_div(ticker):
            try:
                def fetch():
                    f = DataFetcher(ticker)
                    div = f.get_dividends()
                    y = div.get("dividend_yield")
                    if y and y > 0.02:
                        return {
                            "ticker": ticker,
                            "name": f.info.get("longName", ticker),
                            "yield": y,
                            "payout_ratio": div.get("payout_ratio_pct") or 0,
                            "score": 95 if y > 3 else 80
                        }
                    return None
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, fetch)
            except: return None
        import asyncio
        tasks = [fetch_div(t) for t in self.dividend_watch]
        results = [r for r in await asyncio.gather(*tasks) if r]
        return sorted(results, key=lambda x: x['yield'], reverse=True)

    async def get_moonshots(self) -> List[Dict[str, Any]]:
        pool = random.sample(self.moonshot_watch, min(len(self.moonshot_watch), 6))
        async def fetch_moon(ticker):
            try:
                def fetch():
                    f = DataFetcher(ticker)
                    info = f.info
                    mcap = info.get("marketCap", 0)
                    fund = f.get_fundamentals()
                    growth = fund.get("revenue_growth", 0)
                    if 0 < mcap < 20e9 and (growth > 0.10 or mcap < 2e9):
                        return {
                            "ticker": ticker,
                            "name": info.get("longName", ticker),
                            "growth": growth * 100,
                            "market_cap": mcap,
                            "trend_context": random.choice(["Disruptive Tech", "Hyper-Growth", "Market Expansion"]),
                            "score": 80 + (growth * 60)
                        }
                    return None
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, fetch)
            except: return None
        import asyncio
        tasks = [fetch_moon(t) for t in pool]
        results = [r for r in await asyncio.gather(*tasks) if r]
        
        # Fallback if universe is empty
        if not results:
            fallback_tasks = [fetch_moon(t) for t in ["PLTR", "ARM", "MSTR", "TSLA"]]
            results = [r for r in await asyncio.gather(*fallback_tasks) if r]

        if not results:
            return self._moonshot_fallbacks()

        return sorted(results, key=lambda x: x['growth'], reverse=True)

    async def get_star_assets(self) -> Dict[str, Any]:
        """Identify stars with parallel movers fetch."""
        import asyncio
        try:
            movers_task = self.get_market_movers(type='gainers')
            losers_task = self.get_market_movers(type='losers')
            movers, losers = await asyncio.gather(movers_task, losers_task)
        except Exception:
            movers = self._market_mover_fallbacks("gainers")
            losers = self._market_mover_fallbacks("losers")
        if not movers:
            movers = self._market_mover_fallbacks("gainers")
        if not losers:
            losers = self._market_mover_fallbacks("losers")
        
        return {
            "day_winner": movers[0] if movers else None,
            "week_winner": sorted(movers, key=lambda x: x['change'] or 0, reverse=True)[0] if movers else None,
            "day_loser": losers[0] if losers else None,
            "week_loser": sorted(losers, key=lambda x: x['change'] or 0)[0] if losers else None,
            "for_you": random.sample(movers + losers, min(len(movers + losers), 2)) if movers or losers else []
        }

    async def get_sentiment_heatmap(self) -> List[Dict[str, Any]]:
        """Identify global market sentiment per sector and include top stocks."""
        import asyncio
        sectors_config = {
            "Artificial Intelligence": ["NVDA", "PLTR", "ARM", "AI"],
            "Semiconductors": ["AMD", "TSM", "AVGO", "SMCI"],
            "USA": ["AAPL", "MSFT", "AMZN", "TSLA"],
            "Europe": ["SAP", "ASML", "MC.PA", "SIE.DE"],
            "Asia": ["TSM", "BABA", "JD", "PDD"],
            "Germany": ["SAP.DE", "SIE.DE", "ALV.DE", "MBG.DE"],
            "Technology": ["MSFT", "AAPL", "GOOGL", "ORCL"],
            "Energy": ["XOM", "CVX", "BP", "SHEL"],
            "Financials": ["JPM", "GS", "V", "MA"],
            "Healthcare": ["JNJ", "PFE", "UNH", "ABBV"],
            "Industrials": ["CAT", "HON", "BA", "GE"]
        }
        unique_tickers = list(dict.fromkeys(t for tickers in sectors_config.values() for t in tickers))
        sem = asyncio.Semaphore(6)

        async def _load_one(t: str) -> tuple[str, Optional[Dict[str, Any]], Dict[str, Any]]:
            async with sem:
                def _sync_fetch():
                    try:
                        fetcher = DataFetcher(t)
                        price_data = fetcher.get_price_data()
                        info = fetcher.info or {}
                        return price_data, info
                    except Exception:
                        return None, {}
                p_data, inf = await asyncio.to_thread(_sync_fetch)
                return t, p_data, inf

        fetched_list = await asyncio.gather(*(_load_one(t) for t in unique_tickers))
        ticker_map = {t: (p_data, inf) for t, p_data, inf in fetched_list}

        heatmap = []
        for sector, tickers in sectors_config.items():
            sentiments = []
            top_stocks = []
            
            for t in tickers:
                price_data, info = ticker_map.get(t, (None, {}))
                change = price_data.get("change_1w", 0) if price_data else None
                if change is None:
                    top_stocks.append({
                        "ticker": t,
                        "price": None,
                        "change_1w": 0,
                        "name": info.get("shortName") or UNIVERSE_NAMES.get(t) or t,
                        "fallback": True,
                    })
                    continue
                sentiment = 1 if change > 0 else -1
                sentiments.append(sentiment)
                
                top_stocks.append({
                    "ticker": t,
                    "price": price_data.get("current_price") if price_data else None,
                    "change_1w": change,
                    "name": info.get("shortName") or UNIVERSE_NAMES.get(t) or t
                })
            if not sentiments:
                continue
            
            avg_score = sum(sentiments) / len(sentiments)
            status = "BULLISH" if avg_score > 0.5 else "NEUTRAL" if avg_score > -0.5 else "BEARISH"
            
            heatmap.append({
                "sector": sector,
                "sentiment_score": avg_score,
                "status": status,
                "strength": min(100, (abs(avg_score) + 1) * 35),
                "hot_stocks": top_stocks
            })
        return heatmap or self._sentiment_heatmap_fallbacks()

    async def get_diversification_suggestions(self, current_tickers: List[str]) -> List[Dict[str, Any]]:
        """Suggest assets to balance the portfolio."""
        if not current_tickers:
            return await self.get_trending()
            
        # Analyze current sectors
        current_sectors = []
        for t in current_tickers:
            f = DataFetcher(t)
            current_sectors.append(f.info.get("sector"))
            
        sectors_set = set(filter(None, current_sectors))
        
        # Mapping sectors to universes
        potential_additions = []
        if "Technology" in sectors_set and "Consumer Defensive" not in sectors_set:
            potential_additions.extend(["KO", "PEP", "PG"])
        if "Technology" in sectors_set and "Financial Services" not in sectors_set:
            potential_additions.extend(["JPM", "V", "MA"])
        if len(sectors_set) < 2: # Very concentrated
            potential_additions.extend(["O", "MAIN", "GOLD"]) # Diversifiers
            
        # Clean and fetch basic data
        suggestions = []
        for t in list(set(potential_additions))[:4]:
            if t not in current_tickers:
                f = DataFetcher(t)
                suggestions.append({
                    "ticker": t,
                    "name": f.info.get("longName", t),
                    "reason": "Sektor-Diversifizierung"
                })
        return suggestions

    async def search_ticker(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for tickers by company name or fragment using yfinance.
        """
        try:
            import yfinance as yf
            # yf.Search returns a list of dictionaries in search.quotes
            search = yf.Search(query, max_results=5)
            results = search.quotes
            
            suggestions = []
            for item in results:
                ticker = item.get("symbol")
                if ticker:
                    suggestions.append({
                        "ticker": ticker,
                        "name": item.get("longname") or item.get("shortname") or ticker,
                        "exchange": item.get("exchange"),
                        "type": item.get("quoteType")
                    })
            return suggestions
        except Exception as e:
            print(f"Ticker search error for '{query}': {e}")
            return []
