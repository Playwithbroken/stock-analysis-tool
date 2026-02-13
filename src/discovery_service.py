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

    async def _fetch_stock_basic(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Helper to fetch basic stock info in parallel."""
        try:
            # We wrap this in a thread because yfinance is blocking
            import asyncio
            from concurrent.futures import ThreadPoolExecutor
            
            def fetch():
                f = DataFetcher(ticker)
                p = f.get_price_data()
                return {
                    "ticker": ticker,
                    "name": f.info.get("longName", ticker),
                    "price": p.get("current_price"),
                    "change": p.get("change_1w"),
                    "trend_context": "Market momentum"
                }
            
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, fetch)
        except:
            return None

    async def get_market_movers(self, type: str = 'gainers') -> List[Dict[str, Any]]:
        """Identify real-time top gainers or losers from the selection universe with caching."""
        now = datetime.now()
        cache_key = f"movers_{type}"
        if hasattr(self, '_movers_cache') and cache_key in self._movers_cache:
            cache_data, timestamp = self._movers_cache[cache_key]
            if (now - timestamp).total_seconds() < 600:
                return cache_data

        scan_pool = random.sample(self.market_movers_universe, min(len(self.market_movers_universe), 15))
        
        import asyncio
        tasks = [self._fetch_stock_basic(t) for t in scan_pool]
        results = [r for r in await asyncio.gather(*tasks) if r]
                
        is_gainers = type == 'gainers'
        results.sort(key=lambda x: x['change'] or 0, reverse=is_gainers)
        
        if not hasattr(self, '_movers_cache'): self._movers_cache = {}
        self._movers_cache[cache_key] = (results, now)
        return results[:8]

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
