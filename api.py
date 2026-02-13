"""
FastAPI Backend for Stock Analysis Tool
Provides REST API endpoints for stock analysis.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import uvicorn
import numpy as np

from src.data_fetcher import DataFetcher
from src.analyzer import StockAnalyzer, Rating, Valuation
from src.discovery_service import DiscoveryService
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global services (Lazy initialized)
_discovery_service = None
_portfolio_manager = None

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
        return float(obj)
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


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "message": "Stock Analysis API is running"}


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
        resolved_ticker = ticker.upper()
        
        # If input contains brackets like 'Pfizer Inc. (PFE)', extract the ticker
        if "(" in ticker and ")" in ticker:
            import re
            match = re.search(r'\((.*?)\)', ticker)
            if match:
                resolved_ticker = match.group(1).upper()
                print(f"Extracted ticker '{resolved_ticker}' from '{ticker}'")
        elif len(ticker) > 5 or not ticker.isalnum():
            suggestions = await get_discovery_service().search_ticker(ticker)
            if suggestions:
                resolved_ticker = suggestions[0]['ticker']

        # Original stock fetch data
        fetcher = DataFetcher(resolved_ticker)
        data = fetcher.get_all_data()
        
        if "error" in data.get("price_data", {}):
            raise HTTPException(
                status_code=404,
                detail=f"Could not fetch data for ticker '{ticker}'. Please verify the symbol."
            )
        
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
    """
    try:
        fetcher = DataFetcher(ticker)
        history = fetcher.get_history(period=period, interval=interval)
        return convert_numpy_types(history)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch history: {str(e)}"
        )


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
        return await get_discovery_service().search_ticker(q)
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
    """Deep AI Oracle chat logic."""
    msg = req.message.lower()
    ticker = req.context_ticker
    
    # Context gathering
    context_info = ""
    if ticker:
        tickers = ticker.split(',') if ',' in ticker else [ticker]
        summaries = []
        for t in tickers:
            try:
                fetcher = DataFetcher(t)
                data = fetcher.get_all_data()
                analyzer = StockAnalyzer(data)
                score = analyzer.calculate_total_score()
                verdict = analyzer.get_one_sentence_verdict()
                summaries.append(f"{t}: Score {score:.1f}, '{verdict}'")
            except:
                continue
        context_info = " | ".join(summaries)

    # Simple logic-based 'Oracle' response (Simulation of LLM persona)
    if "vergleich" in msg or (ticker and ',' in ticker):
        response = f"Der Vergleich zwischen diesen Assets ({context_info}) zeigt spannende Unterschiede. Bei ETFs achte ich besonders auf die TER-Korrektur und die Sektor-Überschneidungen!"
    elif any(k in msg for k in ["kaufen", "buy", "investieren"]):
        if ticker:
             response = f"Basierend auf meinen Daten für {ticker} ({context_info}): Ich sehe hier eher {'eine Chance' if score > 15 else 'ein Risiko'}. Denke dran: Moonshots sind riskant, Big Player stabil."
        else:
            response = "Der Markt ist gerade volatil. Schau dir im Moonshot-Scanner die Titel mit hohem Volumen an, wenn du Risiko magst."
    elif any(k in msg for k in ["verkaufen", "sell", "raus"]):
        response = "Emotionale Verkäufe sind der Feind der Rendite. Prüfe den Critical Risk Audit – wenn da viele rote Flaggen sind, ist Vorsicht geboten."
    elif any(k in msg for k in ["portfolio", "bestand"]):
        response = "Dein Portfolio braucht Diversifikation. Wenn du zu viel Tech hast, schau dir Rohstoffe wie Gold (GC=F) an."
    else:
        response = "Interessante Frage. Ich analysiere die Korrelationen und das Sentiment für dich. Mein Rat: Bleib kritisch und achte auf die Insider-Cluster!"

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
    try:
        # Get portfolio holdings
        portfolios = get_portfolio_manager().get_portfolios()
        portfolio = next((p for p in portfolios if p['id'] == p_id), None)
        
        if not portfolio or not portfolio['holdings']:
            return []
            
        combined_history = {} # date -> total_value
        
        for holding in portfolio['holdings']:
            ticker = holding['ticker']
            shares = holding['shares']
            
            fetcher = DataFetcher(ticker)
            # Use '1d' interval for periods > 1d, '5m' for 1d
            interval = "1d" if period != "1d" else "5m"
            history = fetcher.get_history(period=period, interval=interval)
            
            for entry in history:
                date = entry['time']
                val = entry['price'] * shares
                combined_history[date] = combined_history.get(date, 0) + val
                
        # Convert back to sorted list
        result = [
            {"time": d, "price": v} 
            for d, v in sorted(combined_history.items())
        ]
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

@app.get("/api/discovery/gainers")
async def get_top_gainers():
    """Get market-wide top performers."""
    try:
        return await get_discovery_service().get_market_movers(type='gainers')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/discovery/losers")
async def get_top_losers():
    """Get market-wide top laggards."""
    try:
        return await get_discovery_service().get_market_movers(type='losers')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/discovery/small-caps")
async def get_small_cap_growth():
    """Identify high-growth small-cap stocks."""
    try:
        return await get_discovery_service().get_small_caps()
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


# --- Static Files & SPA Handling ---
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Check if dist folder exists
if os.path.exists("frontend/dist"):
    app.mount("/assets", StaticFiles(directory="frontend/dist/assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Allow API calls to pass through
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        
        # Serve index.html:
        return FileResponse("frontend/dist/index.html")
else:
    print("Warning: frontend/dist folder not found. Run 'npm run build' in frontend directory.")

if __name__ == "__main__":
    print("Starting Stock Analysis API...")
    import traceback
    try:
        uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)
    except Exception as e:
        print("CRITICAL: API failed to start")
        traceback.print_exc()
