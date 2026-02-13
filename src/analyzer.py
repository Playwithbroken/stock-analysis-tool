"""
Analyzer Module
Performs technical, fundamental, and risk analysis on stock data.
"""

from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class Rating(Enum):
    VERY_NEGATIVE = -2
    NEGATIVE = -1
    NEUTRAL = 0
    POSITIVE = 1
    VERY_POSITIVE = 2


class Valuation(Enum):
    HEAVILY_UNDERVALUED = "Heavily Undervalued"
    UNDERVALUED = "Undervalued"
    FAIRLY_VALUED = "Fairly Valued"
    OVERVALUED = "Overvalued"
    HEAVILY_OVERVALUED = "Heavily Overvalued"


@dataclass
class AnalysisResult:
    """Container for analysis results."""
    category: str
    findings: List[Dict[str, Any]]
    score: float  # -100 to +100
    summary: str


class StockAnalyzer:
    """Analyzes stock data and provides insights."""
    
    # Industry average benchmarks (simplified)
    BENCHMARKS = {
        "pe_ratio": {"low": 10, "mid": 20, "high": 35},
        "pb_ratio": {"low": 1, "mid": 3, "high": 5},
        "ev_ebitda": {"low": 8, "mid": 15, "high": 25},
        "debt_to_equity": {"low": 30, "mid": 100, "high": 200},
        "profit_margin": {"low": 0.05, "mid": 0.15, "high": 0.25},
        "roe": {"low": 0.08, "mid": 0.15, "high": 0.25},
        "revenue_growth": {"low": 0.05, "mid": 0.15, "high": 0.30},
    }

    # Best-in-class ETFs for benchmarking and relative comparison
    ETF_BENCHMARKS = {
        "S&P 500": {"ticker": "VOO", "ter": 0.03, "name": "Vanguard S&P 500 ETF"},
        "Nasdaq 100": {"ticker": "QQQM", "ter": 0.15, "name": "Invesco NASDAQ 100 ETF"},
        "Total Stock Market": {"ticker": "VTI", "ter": 0.03, "name": "Vanguard Total Stock Market ETF"},
        "Dividend Growth": {"ticker": "SCHD", "ter": 0.06, "name": "Schwab US Dividend Equity ETF"},
        "High Dividend": {"ticker": "VYM", "ter": 0.06, "name": "Vanguard High Dividend Yield ETF"},
        "World Stock": {"ticker": "VT", "ter": 0.07, "name": "Vanguard World Stock ETF"},
        "Emerging Markets": {"ticker": "VWO", "ter": 0.08, "name": "Vanguard FTSE Emerging Markets ETF"},
        "Value": {"ticker": "VTV", "ter": 0.04, "name": "Vanguard Value ETF"},
        "Growth": {"ticker": "VUG", "ter": 0.04, "name": "Vanguard Growth ETF"},
    }
    
    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.ticker = data.get("ticker", "UNKNOWN")
        self.company_name = data.get("company_name", self.ticker)
        
    def calculate_total_score(self) -> float:
        """Central calculation for the stock's overall health score."""
        res = self.generate_recommendation()
        return res.get("total_score", 0)

    def get_one_sentence_verdict(self) -> str:
        """Helper for the Oracle and other brief summaries."""
        total_score = self.calculate_total_score()
        return self.generate_verdict(total_score)

    def generate_verdict(self, score: float) -> str:
        """Convert a score into a descriptive growth verdict."""
        if score > 30: return "Außergewöhnliches Wachstumspotenzial mit starken Fundamentaldaten."
        if score > 10: return "Solider Wachstumswert mit moderatem Aufwärtspotenzial."
        if score > -10: return "Neutrale Marktstellung mit Fokus auf Stabilität."
        if score > -25: return "Erhöhtes Risiko, Fundamentaldaten weisen Schwächen auf."
        return "Kritisches Risikoprofil – Vorsicht geboten."

    def analyze_insider_trades(self) -> AnalysisResult:
        """Analyze executive buying/selling activity."""
        # Simple simulation based on news or dummy values for now
        # In production, this would parse SEC filings or specialized data providers
        findings = [
            {"metric": "Insider Buy (CEO)", "value": "12,500 Shares", "rating": Rating.POSITIVE, "interpretation": "High conviction"},
            {"metric": "Insider Sell (CFO)", "value": "2,000 Shares", "rating": Rating.NEUTRAL, "interpretation": "Routine tax/diversification"},
        ]
        return AnalysisResult("Insider Activity", findings, 15, "Slightly positive insider sentiment")

    def analyze_peers(self) -> AnalysisResult:
        """Benchmark against industry peers."""
        fund = self.data.get("fundamentals", {})
        pe = fund.get("pe_ratio")
        sector_pe = 22 # Mock average
        
        findings = []
        if pe is not None:
            if pe < sector_pe:
                findings.append({"metric": "P/E relative to Sector", "value": f"{pe:.1f} vs {sector_pe}", "rating": Rating.POSITIVE})
            else:
                findings.append({"metric": "P/E relative to Sector", "value": f"{pe:.1f} vs {sector_pe}", "rating": Rating.NEGATIVE})
        else:
            findings.append({"metric": "P/E relative to Sector", "value": "N/A", "rating": Rating.NEUTRAL, "interpretation": "No P/E data available for sector comparison"})

        findings.append({"metric": "Revenue Growth vs Sector", "value": "+15%", "rating": Rating.POSITIVE})
        
        return AnalysisResult("Peer Benchmarking", findings, 10, "Competitive position within industry")

    def analyze_price_performance(self) -> AnalysisResult:
        """Analyze price performance over different timeframes."""
        price_data = self.data.get("price_data", {})
        findings = []
        score = 0
        
        if "error" in price_data:
            return AnalysisResult("Price Performance", [{"error": price_data["error"]}], 0, "No data available")
        
        # Current price context
        current = price_data.get("current_price")
        currency = price_data.get("currency", "USD")
        
        if current:
            findings.append({
                "metric": "Current Price",
                "value": f"{current:.2f} {currency}",
                "rating": Rating.NEUTRAL
            })
        
        # Performance over periods
        periods = [
            ("change_1w", "1 Week"),
            ("change_1m", "1 Month"),
            ("change_6m", "6 Months"),
            ("change_1y", "1 Year"),
        ]
        
        for key, label in periods:
            change = price_data.get(key)
            if change is not None:
                rating = Rating.POSITIVE if change > 5 else Rating.NEGATIVE if change < -5 else Rating.NEUTRAL
                score += change / 10  # Weighted contribution
                findings.append({
                    "metric": f"Performance {label}",
                    "value": f"{change:+.2f}%",
                    "rating": rating
                })
        
        # 52-week position
        from_high = price_data.get("from_52w_high")
        from_low = price_data.get("from_52w_low")
        
        if from_high is not None:
            findings.append({
                "metric": "From 52-Week High",
                "value": f"{from_high:.2f}%",
                "rating": Rating.NEGATIVE if from_high < -20 else Rating.NEUTRAL
            })
            
        if from_low is not None:
            findings.append({
                "metric": "From 52-Week Low",
                "value": f"+{from_low:.2f}%",
                "rating": Rating.POSITIVE if from_low > 20 else Rating.NEUTRAL
            })
        
        # Determine summary
        change_1y = price_data.get("change_1y", 0) or 0
        if change_1y > 30:
            summary = "Strong uptrend over the past year"
        elif change_1y > 10:
            summary = "Moderate positive performance"
        elif change_1y > -10:
            summary = "Sideways movement, no clear trend"
        elif change_1y > -30:
            summary = "Moderate decline over the past year"
        else:
            summary = "Significant downtrend - caution advised"
        
        return AnalysisResult("Price Performance", findings, max(-100, min(100, score)), summary)
    
    def analyze_volatility(self) -> AnalysisResult:
        """Analyze volatility and trading activity."""
        vol_data = self.data.get("volatility", {})
        findings = []
        score = 0
        
        if "error" in vol_data:
            return AnalysisResult("Volatility", [{"error": vol_data["error"]}], 0, "No data available")
        
        # Annual volatility
        vol_annual = vol_data.get("volatility_annual")
        if vol_annual is not None:
            rating = Rating.NEGATIVE if vol_annual > 50 else Rating.NEUTRAL if vol_annual > 25 else Rating.POSITIVE
            findings.append({
                "metric": "Annualized Volatility",
                "value": f"{vol_annual:.1f}%",
                "rating": rating,
                "interpretation": "High risk" if vol_annual > 50 else "Moderate risk" if vol_annual > 25 else "Lower risk"
            })
            score -= (vol_annual - 30) / 2  # Higher volatility = lower score
        
        # Beta
        beta = vol_data.get("beta")
        if beta is not None:
            if beta > 1.5:
                rating = Rating.NEGATIVE
                interp = "Much more volatile than market"
            elif beta > 1.1:
                rating = Rating.NEUTRAL
                interp = "Slightly more volatile than market"
            elif beta > 0.9:
                rating = Rating.NEUTRAL
                interp = "Moves with the market"
            else:
                rating = Rating.POSITIVE
                interp = "Less volatile than market (defensive)"
                
            findings.append({
                "metric": "Beta",
                "value": f"{beta:.2f}",
                "rating": rating,
                "interpretation": interp
            })
        
        # Volume analysis
        volume_ratio = vol_data.get("volume_ratio")
        if volume_ratio is not None:
            if volume_ratio > 2:
                rating = Rating.NEUTRAL
                interp = "Unusually high trading activity"
            elif volume_ratio > 1.2:
                rating = Rating.NEUTRAL
                interp = "Above average volume"
            elif volume_ratio < 0.5:
                rating = Rating.NEGATIVE
                interp = "Low liquidity warning"
            else:
                rating = Rating.NEUTRAL
                interp = "Normal trading volume"
                
            findings.append({
                "metric": "Volume Ratio (vs Avg)",
                "value": f"{volume_ratio:.2f}x",
                "rating": rating,
                "interpretation": interp
            })
        
        summary = "High volatility stock - suitable for risk-tolerant investors" if (vol_annual or 0) > 40 else "Moderate volatility" if (vol_annual or 0) > 25 else "Relatively stable stock"
        
        return AnalysisResult("Volatility & Risk", findings, max(-100, min(100, score)), summary)
    
    def analyze_fundamentals(self) -> AnalysisResult:
        """Comprehensive fundamental analysis."""
        fund = self.data.get("fundamentals", {})
        findings = []
        score = 0
        
        if "error" in fund:
            return AnalysisResult("Fundamentals", [{"error": fund["error"]}], 0, "No data available")
        
        # Valuation metrics
        pe = fund.get("pe_ratio")
        if pe is not None:
            if pe < 0:
                rating = Rating.VERY_NEGATIVE
                interp = "Negative earnings - company is unprofitable"
                score -= 20
            elif pe < 15:
                rating = Rating.POSITIVE
                interp = "Low valuation - potentially undervalued"
                score += 15
            elif pe < 25:
                rating = Rating.NEUTRAL
                interp = "Fair valuation"
            elif pe < 40:
                rating = Rating.NEGATIVE
                interp = "Expensive - high expectations priced in"
                score -= 10
            else:
                rating = Rating.VERY_NEGATIVE
                interp = "Very expensive - significant downside risk"
                score -= 20
            
            findings.append({
                "metric": "P/E Ratio",
                "value": f"{pe:.2f}",
                "rating": rating,
                "interpretation": interp
            })
        
        # Forward P/E
        fwd_pe = fund.get("forward_pe")
        if fwd_pe is not None and pe is not None:
            if fwd_pe < pe * 0.85:
                findings.append({
                    "metric": "Forward P/E",
                    "value": f"{fwd_pe:.2f}",
                    "rating": Rating.POSITIVE,
                    "interpretation": "Earnings expected to grow significantly"
                })
                score += 10
            elif fwd_pe > pe * 1.1:
                findings.append({
                    "metric": "Forward P/E",
                    "value": f"{fwd_pe:.2f}",
                    "rating": Rating.NEGATIVE,
                    "interpretation": "Earnings expected to decline"
                })
                score -= 10
        
        # P/B Ratio
        pb = fund.get("pb_ratio")
        if pb is not None:
            if pb < 1:
                rating = Rating.POSITIVE
                interp = "Trading below book value"
                score += 10
            elif pb < 3:
                rating = Rating.NEUTRAL
                interp = "Reasonable price to book"
            else:
                rating = Rating.NEGATIVE
                interp = "High premium to book value"
                score -= 5
            
            findings.append({
                "metric": "P/B Ratio",
                "value": f"{pb:.2f}",
                "rating": rating,
                "interpretation": interp
            })
        
        # EV/EBITDA
        ev_ebitda = fund.get("ev_ebitda")
        if ev_ebitda is not None:
            if ev_ebitda < 8:
                rating = Rating.POSITIVE
                interp = "Cheap on enterprise value basis"
                score += 10
            elif ev_ebitda < 15:
                rating = Rating.NEUTRAL
                interp = "Fair enterprise valuation"
            elif ev_ebitda < 25:
                rating = Rating.NEGATIVE
                interp = "Expensive enterprise valuation"
                score -= 10
            else:
                rating = Rating.VERY_NEGATIVE
                interp = "Very high EV/EBITDA"
                score -= 15
            
            findings.append({
                "metric": "EV/EBITDA",
                "value": f"{ev_ebitda:.2f}",
                "rating": rating,
                "interpretation": interp
            })
        
        # Profitability
        profit_margin = fund.get("profit_margin")
        if profit_margin is not None:
            margin_pct = profit_margin * 100
            if margin_pct > 20:
                rating = Rating.VERY_POSITIVE
                interp = "Excellent profitability"
                score += 15
            elif margin_pct > 10:
                rating = Rating.POSITIVE
                interp = "Good profit margins"
                score += 5
            elif margin_pct > 0:
                rating = Rating.NEUTRAL
                interp = "Modest profitability"
            else:
                rating = Rating.NEGATIVE
                interp = "Unprofitable"
                score -= 15
            
            findings.append({
                "metric": "Profit Margin",
                "value": f"{margin_pct:.1f}%",
                "rating": rating,
                "interpretation": interp
            })
        
        # ROE
        roe = fund.get("roe")
        if roe is not None:
            roe_pct = roe * 100
            if roe_pct > 20:
                rating = Rating.VERY_POSITIVE
                interp = "Excellent return on equity"
                score += 10
            elif roe_pct > 12:
                rating = Rating.POSITIVE
                interp = "Good capital efficiency"
                score += 5
            elif roe_pct > 0:
                rating = Rating.NEUTRAL
                interp = "Modest returns"
            else:
                rating = Rating.NEGATIVE
                interp = "Destroying shareholder value"
                score -= 10
            
            findings.append({
                "metric": "Return on Equity",
                "value": f"{roe_pct:.1f}%",
                "rating": rating,
                "interpretation": interp
            })
        
        # Revenue Growth
        rev_growth = fund.get("revenue_growth")
        if rev_growth is not None:
            growth_pct = rev_growth * 100
            if growth_pct > 25:
                rating = Rating.VERY_POSITIVE
                interp = "High growth company"
                score += 15
            elif growth_pct > 10:
                rating = Rating.POSITIVE
                interp = "Solid growth"
                score += 5
            elif growth_pct > 0:
                rating = Rating.NEUTRAL
                interp = "Modest growth"
            elif growth_pct > -10:
                rating = Rating.NEGATIVE
                interp = "Revenue declining"
                score -= 10
            else:
                rating = Rating.VERY_NEGATIVE
                interp = "Significant revenue decline"
                score -= 20
            
            findings.append({
                "metric": "Revenue Growth",
                "value": f"{growth_pct:.1f}%",
                "rating": rating,
                "interpretation": interp
            })
        
        # Debt analysis
        debt_equity = fund.get("debt_to_equity")
        if debt_equity is not None:
            if debt_equity < 30:
                rating = Rating.VERY_POSITIVE
                interp = "Very low debt - strong balance sheet"
                score += 10
            elif debt_equity < 80:
                rating = Rating.POSITIVE
                interp = "Manageable debt levels"
                score += 5
            elif debt_equity < 150:
                rating = Rating.NEUTRAL
                interp = "Moderate leverage"
            elif debt_equity < 250:
                rating = Rating.NEGATIVE
                interp = "High debt - financial risk"
                score -= 15
            else:
                rating = Rating.VERY_NEGATIVE
                interp = "Excessive debt - high risk"
                score -= 25
            
            findings.append({
                "metric": "Debt/Equity",
                "value": f"{debt_equity:.1f}%",
                "rating": rating,
                "interpretation": interp
            })
        
        # Free Cash Flow
        fcf = fund.get("free_cashflow")
        if fcf is not None:
            if fcf > 0:
                fcf_formatted = f"${fcf/1e9:.2f}B" if fcf > 1e9 else f"${fcf/1e6:.1f}M"
                rating = Rating.POSITIVE
                interp = "Generating positive cash flow"
                score += 10
            else:
                fcf_formatted = f"-${abs(fcf)/1e9:.2f}B" if abs(fcf) > 1e9 else f"-${abs(fcf)/1e6:.1f}M"
                rating = Rating.NEGATIVE
                interp = "Burning cash"
                score -= 15
            
            findings.append({
                "metric": "Free Cash Flow",
                "value": fcf_formatted,
                "rating": rating,
                "interpretation": interp
            })
        
        # Market Cap
        market_cap = fund.get("market_cap")
        if market_cap is not None:
            if market_cap > 200e9:
                cap_str = f"${market_cap/1e9:.0f}B (Mega Cap)"
            elif market_cap > 10e9:
                cap_str = f"${market_cap/1e9:.1f}B (Large Cap)"
            elif market_cap > 2e9:
                cap_str = f"${market_cap/1e9:.1f}B (Mid Cap)"
            elif market_cap > 300e6:
                cap_str = f"${market_cap/1e6:.0f}M (Small Cap)"
            else:
                cap_str = f"${market_cap/1e6:.0f}M (Micro Cap)"
            
            findings.append({
                "metric": "Market Cap",
                "value": cap_str,
                "rating": Rating.NEUTRAL
            })
        
        # Summary determination
        if score > 30:
            summary = "Strong fundamentals - quality company at reasonable valuation"
        elif score > 10:
            summary = "Solid fundamentals with some positive aspects"
        elif score > -10:
            summary = "Mixed fundamentals - neither clearly cheap nor expensive"
        elif score > -30:
            summary = "Weak fundamentals - several concerns"
        else:
            summary = "Poor fundamentals - significant risks present"
        
        return AnalysisResult("Fundamental Analysis", findings, max(-100, min(100, score)), summary)
    
    def analyze_fear_factors(self) -> AnalysisResult:
        """Identify risk factors and fear indicators."""
        findings = []
        score = 0
        
        fund = self.data.get("fundamentals", {})
        short_data = self.data.get("short_interest", {})
        vol_data = self.data.get("volatility", {})
        price_data = self.data.get("price_data", {})
        
        # Short Interest
        short_pct = short_data.get("short_percent_float")
        if short_pct is not None:
            short_pct_val = short_pct * 100 if short_pct < 1 else short_pct
            if short_pct_val > 20:
                rating = Rating.VERY_NEGATIVE
                interp = "Very high short interest - significant bearish sentiment"
                score -= 25
            elif short_pct_val > 10:
                rating = Rating.NEGATIVE
                interp = "Elevated short interest - notable bearish bets"
                score -= 15
            elif short_pct_val > 5:
                rating = Rating.NEUTRAL
                interp = "Moderate short interest"
                score -= 5
            else:
                rating = Rating.NEUTRAL
                interp = "Low short interest"
            
            findings.append({
                "metric": "Short Interest (% Float)",
                "value": f"{short_pct_val:.1f}%",
                "rating": rating,
                "interpretation": interp,
                "category": "Market Sentiment"
            })
        
        # Short Ratio (Days to Cover)
        short_ratio = short_data.get("short_ratio")
        if short_ratio is not None:
            if short_ratio > 10:
                rating = Rating.NEGATIVE
                interp = "High days to cover - potential short squeeze but also high bearishness"
            elif short_ratio > 5:
                rating = Rating.NEUTRAL
                interp = "Moderate short covering timeline"
            else:
                rating = Rating.NEUTRAL
                interp = "Low days to cover"
            
            findings.append({
                "metric": "Days to Cover",
                "value": f"{short_ratio:.1f} days",
                "rating": rating,
                "interpretation": interp,
                "category": "Market Sentiment"
            })
        
        # High Debt
        debt_equity = fund.get("debt_to_equity")
        if debt_equity is not None and debt_equity > 150:
            findings.append({
                "metric": "High Leverage Risk",
                "value": f"D/E: {debt_equity:.0f}%",
                "rating": Rating.NEGATIVE,
                "interpretation": "High debt levels increase risk in downturn or rising rates",
                "category": "Financial Risk"
            })
            score -= 15
        
        # Negative Cash Flow
        fcf = fund.get("free_cashflow")
        if fcf is not None and fcf < 0:
            findings.append({
                "metric": "Cash Burn",
                "value": f"${abs(fcf)/1e6:.0f}M negative FCF",
                "rating": Rating.NEGATIVE,
                "interpretation": "Company burning cash - may need financing",
                "category": "Financial Risk"
            })
            score -= 15
        
        # High Volatility
        vol_annual = vol_data.get("volatility_annual")
        if vol_annual is not None and vol_annual > 50:
            findings.append({
                "metric": "High Volatility",
                "value": f"{vol_annual:.1f}% annual",
                "rating": Rating.NEGATIVE,
                "interpretation": "Expect large price swings - not for conservative investors",
                "category": "Market Risk"
            })
            score -= 10
        
        # Distance from 52-week high
        from_high = price_data.get("from_52w_high")
        if from_high is not None and from_high < -30:
            findings.append({
                "metric": "Significant Drawdown",
                "value": f"{from_high:.1f}% from 52W high",
                "rating": Rating.NEGATIVE,
                "interpretation": "Stock has fallen significantly - may indicate problems or opportunity",
                "category": "Price Risk"
            })
            score -= 10
        
        # Negative revenue growth
        rev_growth = fund.get("revenue_growth")
        if rev_growth is not None and rev_growth < 0:
            findings.append({
                "metric": "Revenue Decline",
                "value": f"{rev_growth*100:.1f}%",
                "rating": Rating.NEGATIVE,
                "interpretation": "Shrinking business - structural concerns",
                "category": "Business Risk"
            })
            score -= 15
        
        # High P/E with low growth
        pe = fund.get("pe_ratio")
        earnings_growth = fund.get("earnings_growth")
        if pe is not None and pe > 30 and earnings_growth is not None and earnings_growth < 0.1:
            findings.append({
                "metric": "Valuation Risk",
                "value": f"P/E {pe:.0f} with {(earnings_growth or 0)*100:.0f}% growth",
                "rating": Rating.NEGATIVE,
                "interpretation": "High valuation not supported by growth",
                "category": "Valuation Risk"
            })
            score -= 15
        
        if not findings:
            findings.append({
                "metric": "No Major Red Flags",
                "value": "-",
                "rating": Rating.POSITIVE,
                "interpretation": "No significant fear factors identified"
            })
        
        summary = f"Identified {len([f for f in findings if f['rating'] in [Rating.NEGATIVE, Rating.VERY_NEGATIVE]])} significant risk factors"
        
        return AnalysisResult("Fear Factors & Risks", findings, max(-100, min(100, score)), summary)
    
    def analyze_opportunities(self) -> AnalysisResult:
        """Identify positive catalysts and opportunities."""
        findings = []
        score = 0
        
        fund = self.data.get("fundamentals", {})
        analyst = self.data.get("analyst_data", {})
        price_data = self.data.get("price_data", {})
        comparison = self.data.get("comparison", {})
        
        # Strong Revenue Growth
        rev_growth = fund.get("revenue_growth")
        if rev_growth is not None and rev_growth > 0.15:
            findings.append({
                "metric": "Strong Growth",
                "value": f"{rev_growth*100:.1f}% revenue growth",
                "rating": Rating.POSITIVE,
                "interpretation": "Business expanding rapidly"
            })
            score += 15
        
        # High Margins
        profit_margin = fund.get("profit_margin")
        if profit_margin is not None and profit_margin > 0.20:
            findings.append({
                "metric": "High Profitability",
                "value": f"{profit_margin*100:.1f}% profit margin",
                "rating": Rating.POSITIVE,
                "interpretation": "Strong pricing power and efficiency"
            })
            score += 10
        
        # Strong Balance Sheet
        debt_equity = fund.get("debt_to_equity")
        cash = fund.get("total_cash")
        debt = fund.get("total_debt")
        if cash and debt and cash > debt:
            findings.append({
                "metric": "Net Cash Position",
                "value": f"${(cash-debt)/1e9:.1f}B net cash",
                "rating": Rating.POSITIVE,
                "interpretation": "Strong financial position - flexibility for growth or buybacks"
            })
            score += 15
        
        # Analyst Upside
        current = price_data.get("current_price")
        target = analyst.get("target_mean")
        if current and target:
            upside = ((target / current) - 1) * 100
            if upside > 20:
                findings.append({
                    "metric": "Analyst Upside",
                    "value": f"+{upside:.0f}% to target ${target:.2f}",
                    "rating": Rating.POSITIVE,
                    "interpretation": f"Analysts see significant upside potential"
                })
                score += 15
            elif upside > 0:
                findings.append({
                    "metric": "Analyst Target",
                    "value": f"+{upside:.0f}% to target ${target:.2f}",
                    "rating": Rating.NEUTRAL,
                    "interpretation": "Modest upside according to analysts"
                })
        
        # Low Valuation
        pe = fund.get("pe_ratio")
        if pe is not None and 0 < pe < 15:
            findings.append({
                "metric": "Value Opportunity",
                "value": f"P/E of {pe:.1f}",
                "rating": Rating.POSITIVE,
                "interpretation": "Trading at attractive valuation"
            })
            score += 10
        
        # Outperforming Market
        rel_perf = comparison.get("relative_performance")
        if rel_perf is not None and rel_perf > 15:
            findings.append({
                "metric": "Market Outperformance",
                "value": f"+{rel_perf:.1f}% vs index",
                "rating": Rating.POSITIVE,
                "interpretation": "Demonstrating relative strength"
            })
            score += 10
        
        # Dividend
        div_yield = fund.get("dividend_yield")
        if div_yield is not None and div_yield > 0.02:
            findings.append({
                "metric": "Dividend Income",
                "value": f"{div_yield*100:.2f}% yield",
                "rating": Rating.POSITIVE,
                "interpretation": "Provides income while waiting"
            })
            score += 5
        
        # Strong Free Cash Flow
        fcf = fund.get("free_cashflow")
        market_cap = fund.get("market_cap")
        if fcf and market_cap and fcf > 0:
            fcf_yield = (fcf / market_cap) * 100
            if fcf_yield > 5:
                findings.append({
                    "metric": "FCF Yield",
                    "value": f"{fcf_yield:.1f}%",
                    "rating": Rating.POSITIVE,
                    "interpretation": "Strong cash generation relative to valuation"
                })
                score += 10
        
        if not findings:
            findings.append({
                "metric": "Limited Catalysts",
                "value": "-",
                "rating": Rating.NEUTRAL,
                "interpretation": "No obvious near-term catalysts identified"
            })
        
        summary = f"Identified {len([f for f in findings if f['rating'] == Rating.POSITIVE])} positive factors"
        
        return AnalysisResult("Opportunities & Catalysts", findings, max(-100, min(100, score)), summary)
    
    TRUSTED_SOURCES = [
        "Bloomberg", "Reuters", "CNBC", "Financial Times", "Wall Street Journal", 
        "Yahoo Finance", "Forbes", "MarketWatch", "Barrons", "Seeking Alpha",
        "Business Insider", "The Economist", "investors.com", "Investor's Business Daily"
    ]


    def is_trusted_source(self, source: str) -> bool:
        """Check if a news source is in the trusted whitelist."""
        if not source: return False
        return any(trusted.lower() in source.lower() for trusted in self.TRUSTED_SOURCES)

    def analyze_etf(self) -> Dict[str, Any]:
        """Specific analysis for ETFs focusing on costs and alternatives."""
        fund = self.data.get("fundamentals", {})
        holdings = self.data.get("etf_holdings", [])
        
        ter = fund.get("expense_ratio")
        category = fund.get("category", "")
        
        alternatives = []
        is_best_in_class = True
        
        # Check against benchmarks
        matched_benchmark = None
        for key, bench in self.ETF_BENCHMARKS.items():
            if key.lower() in category.lower() or (ter is not None and abs(ter - bench['ter']) < 0.05 and key.lower() in category.lower()):
                matched_benchmark = bench
                break
        
        if matched_benchmark:
            if ter is not None and ter > matched_benchmark['ter'] + 0.05:
                is_best_in_class = False
                alternatives.append({
                    "ticker": matched_benchmark['ticker'],
                    "name": matched_benchmark['name'],
                    "ter": matched_benchmark['ter'],
                    "reason": f"Günstigere Alternative im Bereich {category}"
                })
        
        return {
            "ter": ter,
            "category": category,
            "is_best_in_class": is_best_in_class,
            "alternatives": alternatives,
            "holdings": holdings,
            "total_assets": fund.get("total_assets")
        }

    def analyze_news_sentiment(self) -> AnalysisResult:
        """Analyze recent news sentiment with source verification."""
        news = self.data.get("news", [])
        findings = []
        
        if not news or (len(news) > 0 and "error" in news[0]):
            return AnalysisResult("News Analysis", [{"note": "No recent news available"}], 0, "Unable to assess news sentiment")
        
        # Keywords
        positive_keywords = ["beat", "growth", "profit", "upgrade", "buy", "outperform", "raise", "positive", "strong", "record", "bullish", "superior"]
        negative_keywords = ["miss", "cut", "downgrade", "sell", "loss", "decline", "weak", "concern", "risk", "warning", "lawsuit", "investigation", "bearish"]
        
        sentiment_scores = []
        
        for item in news[:15]:
            title_raw = item.get("title") or ""
            title = title_raw.lower()
            source = item.get("publisher") or item.get("source") or ""
            is_trusted = self.is_trusted_source(source)
            
            sentiment = "neutral"
            pos_count = sum(1 for kw in positive_keywords if kw in title)
            neg_count = sum(1 for kw in negative_keywords if kw in title)
            
            score = 0
            if pos_count > neg_count:
                sentiment = "positive"
                score = 1
            elif neg_count > pos_count:
                sentiment = "negative"
                score = -1
            
            # Weight trusted sources more heavily
            if is_trusted:
                score *= 1.5
                
            sentiment_scores.append(score)
            
            findings.append({
                "title": title_raw,
                "date": item.get("timestamp") or "",
                "source": source,
                "link": item.get("link") or "",
                "sentiment": sentiment,
                "is_trusted": is_trusted
            })
        
        avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0
        
        if avg_sentiment > 0.3:
            summary = "Generally positive news flow from verified sources" if any(f.get('is_trusted') for f in findings if f['sentiment'] == 'positive') else "Positive news sentiment identified"
        elif avg_sentiment < -0.3:
            summary = "Negative news sentiment - monitor closely (Verified alerts present)" if any(f.get('is_trusted') for f in findings if f['sentiment'] == 'negative') else "Caution: Negative news sentiment detected"
        else:
            summary = "Mixed or neutral news sentiment"
        
        return AnalysisResult("Recent News", findings, max(-100, min(100, avg_sentiment * 50)), summary)
    
    def analyze_potential(self) -> AnalysisResult:
        """Analyze long-term growth and upside potential."""
        findings = []
        score = 0
        
        fund = self.data.get("fundamentals", {})
        analyst = self.data.get("analyst_data", {})
        price_data = self.data.get("price_data", {})
        
        # Growth potential
        rev_growth = fund.get("revenue_growth", 0) or 0
        if rev_growth > 0.25:
            findings.append({"metric": "Hyper Growth", "value": f"{rev_growth*100:.1f}%", "rating": Rating.VERY_POSITIVE})
            score += 30
        elif rev_growth > 0.15:
            findings.append({"metric": "Strong Growth", "value": f"{rev_growth*100:.1f}%", "rating": Rating.POSITIVE})
            score += 15
            
        # Analyst Upside
        current = price_data.get("current_price")
        target = analyst.get("target_mean")
        if current and target:
            upside = ((target / current) - 1) * 100
            if upside > 30:
                findings.append({"metric": "High Upside", "value": f"+{upside:.1f}%", "rating": Rating.VERY_POSITIVE})
                score += 30
            elif upside > 15:
                findings.append({"metric": "Moderate Upside", "value": f"+{upside:.1f}%", "rating": Rating.POSITIVE})
                score += 10
                
        # PEG Ratio (Price/Earnings to Growth)
        peg = fund.get("peg_ratio")
        if peg is not None:
            if peg < 1.0:
                findings.append({"metric": "Attractive PEG", "value": f"{peg:.2f}", "rating": Rating.VERY_POSITIVE})
                score += 10
            elif peg < 1.5:
                findings.append({"metric": "Reasonable PEG", "value": f"{peg:.2f}", "rating": Rating.POSITIVE})
                score += 10
                
        summary = "Exceptional growth potential identified" if score > 50 else "Moderate growth potential" if score > 20 else "Limited growth catalysts"
        return AnalysisResult("Potential Analysis", findings, max(0, min(100, score)), summary)

    def analyze_rebound(self) -> AnalysisResult:
        """Analyze rebound potential after a sharp drop (Data Dump)."""
        findings = []
        score = 0
        
        price_data = self.data.get("price_data", {})
        fund = self.data.get("fundamentals", {})
        
        change_1w = price_data.get("change_1w", 0) or 0
        change_1m = price_data.get("change_1m", 0) or 0
        
        if change_1w < -10 or change_1m < -20:
            findings.append({"metric": "Sharp Sell-off", "value": f"{change_1w:.1f}% (1w)", "rating": Rating.NEGATIVE})
            score += 40 # Base score for being 'dumped'
            
            # Check if company is still profitable (quality bounce)
            margin = fund.get("profit_margin", 0) or 0
            if margin > 0.1:
                findings.append({"metric": "Quality Business", "value": f"{margin*100:.1f}% margin", "rating": Rating.POSITIVE})
                score += 30
            
            # Check if RSI is oversold (simulated)
            findings.append({"metric": "Oversold Condition", "value": "Likely", "rating": Rating.POSITIVE})
            score += 20
            
        summary = "High probability rebound candidate" if score > 70 else "Speculative rebound" if score > 40 else "No rebound setup detected"
        return AnalysisResult("Rebound Analysis", findings, max(0, min(100, score)), summary)
    
    def determine_valuation(self) -> Valuation:
        """Determine overall valuation assessment."""
        fund = self.data.get("fundamentals", {})
        
        scores = []
        
        pe = fund.get("pe_ratio")
        if pe is not None:
            if pe < 0:
                scores.append(0)  # Unprofitable
            elif pe < 12:
                scores.append(2)
            elif pe < 20:
                scores.append(1)
            elif pe < 30:
                scores.append(0)
            elif pe < 45:
                scores.append(-1)
            else:
                scores.append(-2)
        
        pb = fund.get("pb_ratio")
        if pb is not None:
            if pb < 1:
                scores.append(2)
            elif pb < 2:
                scores.append(1)
            elif pb < 4:
                scores.append(0)
            else:
                scores.append(-1)
        
        ev_ebitda = fund.get("ev_ebitda")
        if ev_ebitda is not None:
            if ev_ebitda < 8:
                scores.append(2)
            elif ev_ebitda < 12:
                scores.append(1)
            elif ev_ebitda < 18:
                scores.append(0)
            else:
                scores.append(-1)
        
        if not scores:
            return Valuation.FAIRLY_VALUED
        
        avg = sum(scores) / len(scores)
        
        if avg >= 1.5:
            return Valuation.HEAVILY_UNDERVALUED
        elif avg >= 0.5:
            return Valuation.UNDERVALUED
        elif avg >= -0.5:
            return Valuation.FAIRLY_VALUED
        elif avg >= -1.5:
            return Valuation.OVERVALUED
        else:
            return Valuation.HEAVILY_OVERVALUED
    
    def generate_recommendation(self) -> Dict[str, Any]:
        """Generate final recommendation."""
        # Run all analyses
        price_analysis = self.analyze_price_performance()
        vol_analysis = self.analyze_volatility()
        fund_analysis = self.analyze_fundamentals()
        fear_analysis = self.analyze_fear_factors()
        opp_analysis = self.analyze_opportunities()
        news_analysis = self.analyze_news_sentiment()
        valuation = self.determine_valuation()
        
        # Calculate overall score
        weights = {
            "fundamentals": 0.35,
            "fear": 0.25,
            "opportunities": 0.20,
            "price": 0.10,
            "volatility": 0.05,
            "news": 0.05
        }
        
        total_score = (
            fund_analysis.score * weights["fundamentals"] +
            fear_analysis.score * weights["fear"] +
            opp_analysis.score * weights["opportunities"] +
            price_analysis.score * weights["price"] +
            vol_analysis.score * weights["volatility"] +
            news_analysis.score * weights["news"]
        )
        
        # Determine recommendations
        if total_score > 25:
            short_term = "Potentially attractive for momentum trades"
            long_term = "Strong candidate for long-term investment"
            action = "BUY"
        elif total_score > 10:
            short_term = "Neutral - wait for better entry"
            long_term = "Consider for long-term if fundamentals align with thesis"
            action = "HOLD / ACCUMULATE"
        elif total_score > -10:
            short_term = "No clear trading opportunity"
            long_term = "Hold if owned, wait for better value to buy"
            action = "HOLD"
        elif total_score > -25:
            short_term = "Avoid - risk/reward unfavorable"
            long_term = "Caution advised - address concerns before investing"
            action = "REDUCE / AVOID"
        else:
            short_term = "Avoid - high risk"
            long_term = "Not recommended - significant concerns"
            action = "SELL / AVOID"
        
        return {
            "analyses": {
                "price_performance": price_analysis,
                "volatility": vol_analysis,
                "fundamentals": fund_analysis,
                "fear_factors": fear_analysis,
                "opportunities": opp_analysis,
                "news": news_analysis,
                "insider": self.analyze_insider_trades(),
                "peers": self.analyze_peers(),
            },
            "verdict": self.generate_verdict(total_score),
            "valuation": valuation,
            "potential": self.analyze_potential(),
            "rebound": self.analyze_rebound(),
            "total_score": total_score,
            "recommendation": {
                "action": action,
                "short_term_traders": short_term,
                "long_term_investors": long_term,
            }
        }
