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

class DiscoveryService:
    def __init__(self):
        # Sample universes for scanning
        self.tech_universe = ["NVDA", "AMD", "TSLA", "PLTR", "SMCI", "ARM", "CELH", "MSFT", "AAPL", "GOOGL", "META", "NFLX"]
        self.small_cap_watch = ["FRGT", "SOFI", "PATH", "MSTR", "HOOD", "UPST", "OKLO", "S", "LUNR", "RKLB"]
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

    async def _fetch_stock_basic(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Helper to fetch basic stock info in parallel."""
        try:
            # We wrap this in a thread because yfinance is blocking
            import asyncio
            from concurrent.futures import ThreadPoolExecutor
            
            def fetch():
                f = DataFetcher(ticker)
                p = f.get_price_data()
                change_1d = None
                try:
                    hist = f.stock.history(period="7d", interval="1d")
                    if hist is not None and not hist.empty and len(hist["Close"]) >= 2:
                        last_close = float(hist["Close"].iloc[-1])
                        prev_close = float(hist["Close"].iloc[-2])
                        if prev_close:
                            change_1d = ((last_close / prev_close) - 1.0) * 100.0
                except Exception:
                    change_1d = None
                return {
                    "ticker": ticker,
                    "name": f.info.get("longName", ticker),
                    "price": p.get("current_price"),
                    "change": p.get("change_1w"),
                    "change_1d": change_1d,
                    "change_1w": p.get("change_1w"),
                    "change_1m": p.get("change_1m"),
                    "trend_context": "Market momentum"
                }
            
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, fetch)
        except:
            return None

    async def get_market_movers(self, type: str = 'gainers', window: str = "1w") -> List[Dict[str, Any]]:
        """Identify real-time top gainers or losers from the selection universe with caching."""
        now = datetime.now()
        normalized_window = (window or "1w").lower()
        if normalized_window not in {"1d", "1w", "1m"}:
            normalized_window = "1w"
        change_key = {
            "1d": "change_1d",
            "1w": "change_1w",
            "1m": "change_1m",
        }[normalized_window]
        cache_key = f"movers_{type}_{normalized_window}"
        if hasattr(self, '_movers_cache') and cache_key in self._movers_cache:
            cache_data, timestamp = self._movers_cache[cache_key]
            if (now - timestamp).total_seconds() < 600:
                return cache_data

        scan_pool = random.sample(self.market_movers_universe, min(len(self.market_movers_universe), 15))
        
        import asyncio
        tasks = [self._fetch_stock_basic(t) for t in scan_pool]
        results = [r for r in await asyncio.gather(*tasks) if r]
        for item in results:
            item["change"] = item.get(change_key)
                
        is_gainers = type == 'gainers'
        results.sort(key=lambda x: x['change'] or 0, reverse=is_gainers)
        
        if not hasattr(self, '_movers_cache'): self._movers_cache = {}
        self._movers_cache[cache_key] = (results, now)
        return results[:8]

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
        pool = random.sample(self.etf_universe, min(len(self.etf_universe), 12))
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
                        "trend_context": f"Kategorie: {fund.get('category', 'Global')}"
                    }
                import asyncio
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, fetch)
            except: return None

        import asyncio
        tasks = [fetch_etf_data(t) for t in pool]
        results = [r for r in await asyncio.gather(*tasks) if r]
        return results

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
                            "yield": y * 100,
                            "payout_ratio": (div.get("payout_ratio") or 0) * 100,
                            "score": 95 if y > 0.03 else 80
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
            
        return sorted(results, key=lambda x: x['growth'], reverse=True)

    async def get_star_assets(self) -> Dict[str, Any]:
        """Identify stars with parallel movers fetch."""
        import asyncio
        movers_task = self.get_market_movers(type='gainers')
        losers_task = self.get_market_movers(type='losers')
        movers, losers = await asyncio.gather(movers_task, losers_task)
        
        return {
            "day_winner": movers[0] if movers else None,
            "week_winner": sorted(movers, key=lambda x: x['change'] or 0, reverse=True)[0] if movers else None,
            "day_loser": losers[0] if losers else None,
            "week_loser": sorted(losers, key=lambda x: x['change'] or 0)[0] if losers else None,
            "for_you": random.sample(movers + losers, min(len(movers + losers), 2)) if movers or losers else []
        }

    async def get_sentiment_heatmap(self) -> List[Dict[str, Any]]:
        """Identify global market sentiment per sector and include top stocks."""
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
        heatmap = []
        for sector, tickers in sectors_config.items():
            sentiments = []
            top_stocks = []
            
            for t in tickers:
                fetcher = DataFetcher(t)
                price_data = fetcher.get_price_data()
                news = fetcher.get_news()
                
                # Mock average sentiment
                # Simplified: logic based on price change + news volume
                change = price_data.get("change_1w", 0)
                sentiment = 1 if change > 0 else -1
                sentiments.append(sentiment)
                
                top_stocks.append({
                    "ticker": t,
                    "price": price_data.get("current_price"),
                    "change_1w": change,
                    "name": fetcher.info.get("shortName", t)
                })
            
            avg_score = sum(sentiments) / len(sentiments)
            status = "BULLISH" if avg_score > 0.5 else "NEUTRAL" if avg_score > -0.5 else "BEARISH"
            
            heatmap.append({
                "sector": sector,
                "sentiment_score": avg_score,
                "status": status,
                "strength": min(100, (abs(avg_score) + 1) * 35),
                "hot_stocks": top_stocks
            })
        return heatmap

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
