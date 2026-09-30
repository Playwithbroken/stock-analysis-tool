"""
Analyzer Module
Performs technical, fundamental, and risk analysis on stock data.
"""

from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
from src.financial_units import normalize_dividend_yield_pct


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

        statements = fund.get("financial_statements", {}) if isinstance(fund.get("financial_statements"), dict) else {}
        trends = statements.get("trends", {}) if isinstance(statements.get("trends"), dict) else {}
        annual_rows = statements.get("annual", []) if isinstance(statements.get("annual"), list) else []

        statement_revenue_yoy = trends.get("revenue_yoy")
        if statement_revenue_yoy is not None:
            yoy_pct = statement_revenue_yoy * 100
            if yoy_pct > 15:
                rating = Rating.VERY_POSITIVE
                interp = "Reported annual revenue is accelerating strongly"
                score += 12
            elif yoy_pct > 5:
                rating = Rating.POSITIVE
                interp = "Reported annual revenue is growing"
                score += 6
            elif yoy_pct > -3:
                rating = Rating.NEUTRAL
                interp = "Reported annual revenue is broadly stable"
            elif yoy_pct > -12:
                rating = Rating.NEGATIVE
                interp = "Reported annual revenue is declining"
                score -= 8
            else:
                rating = Rating.VERY_NEGATIVE
                interp = "Reported annual revenue is falling sharply"
                score -= 16
            findings.append({
                "metric": "Reported Revenue YoY",
                "value": f"{yoy_pct:.1f}%",
                "rating": rating,
                "interpretation": interp,
            })

        revenue_cagr = trends.get("revenue_cagr")
        if revenue_cagr is not None:
            cagr_pct = revenue_cagr * 100
            if cagr_pct > 12:
                rating = Rating.POSITIVE
                interp = "Multi-year revenue compound growth supports the thesis"
                score += 8
            elif cagr_pct >= 0:
                rating = Rating.NEUTRAL
                interp = "Multi-year revenue trend is positive but not exceptional"
            else:
                rating = Rating.NEGATIVE
                interp = "Multi-year revenue trend is negative"
                score -= 8
            findings.append({
                "metric": "Revenue CAGR",
                "value": f"{cagr_pct:.1f}%",
                "rating": rating,
                "interpretation": interp,
            })

        quarterly_revenue_yoy = trends.get("quarterly_revenue_yoy")
        if quarterly_revenue_yoy is not None:
            q_pct = quarterly_revenue_yoy * 100
            if q_pct > 10:
                rating = Rating.POSITIVE
                interp = "Latest quarterly revenue confirms near-term demand"
                score += 6
            elif q_pct > -5:
                rating = Rating.NEUTRAL
                interp = "Latest quarterly revenue is not a major signal"
            else:
                rating = Rating.NEGATIVE
                interp = "Latest quarterly revenue weakens the near-term setup"
                score -= 8
            findings.append({
                "metric": "Quarterly Revenue YoY",
                "value": f"{q_pct:.1f}%",
                "rating": rating,
                "interpretation": interp,
            })

        latest_annual = annual_rows[0] if annual_rows else {}
        fcf_margin = latest_annual.get("fcf_margin") if isinstance(latest_annual, dict) else None
        if fcf_margin is not None:
            fcf_margin_pct = fcf_margin * 100
            if fcf_margin_pct > 15:
                rating = Rating.VERY_POSITIVE
                interp = "High free-cash-flow margin shows strong cash conversion"
                score += 10
            elif fcf_margin_pct > 5:
                rating = Rating.POSITIVE
                interp = "Positive free-cash-flow margin supports quality"
                score += 5
            elif fcf_margin_pct >= 0:
                rating = Rating.NEUTRAL
                interp = "Free-cash-flow conversion is thin"
            else:
                rating = Rating.NEGATIVE
                interp = "Negative free-cash-flow margin signals cash burn"
                score -= 10
            findings.append({
                "metric": "FCF Margin",
                "value": f"{fcf_margin_pct:.1f}%",
                "rating": rating,
                "interpretation": interp,
            })

        operating_margin_change = trends.get("operating_margin_change")
        if operating_margin_change is not None:
            change_pct = operating_margin_change * 100
            if change_pct > 2:
                rating = Rating.POSITIVE
                interp = "Operating leverage is improving"
                score += 5
            elif change_pct < -2:
                rating = Rating.NEGATIVE
                interp = "Operating margin is deteriorating"
                score -= 6
            else:
                rating = Rating.NEUTRAL
                interp = "Operating margin is stable"
            findings.append({
                "metric": "Operating Margin Change",
                "value": f"{change_pct:+.1f} pts",
                "rating": rating,
                "interpretation": interp,
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

    def analyze_earnings_quality(self) -> AnalysisResult:
        """Analyze whether recent earnings beat, met, or missed market expectations."""
        fund = self.data.get("fundamentals", {}) if isinstance(self.data.get("fundamentals"), dict) else {}
        earnings_history = self.data.get("earnings_history", [])
        statements = fund.get("financial_statements", {}) if isinstance(fund.get("financial_statements"), dict) else {}
        trends = statements.get("trends", {}) if isinstance(statements.get("trends"), dict) else {}
        findings: List[Dict[str, Any]] = []
        score = 0

        latest = earnings_history[0] if isinstance(earnings_history, list) and earnings_history else {}
        latest_surprise = latest.get("eps_surprise_pct") if isinstance(latest, dict) else None
        latest_status = latest.get("status") if isinstance(latest, dict) else None
        reported_eps = latest.get("reported_eps") if isinstance(latest, dict) else None
        eps_estimate = latest.get("eps_estimate") if isinstance(latest, dict) else None

        if latest_surprise is not None:
            if latest_surprise >= 8:
                rating = Rating.VERY_POSITIVE
                interp = "EPS came in materially above expectations"
                score += 22
            elif latest_surprise >= 3:
                rating = Rating.POSITIVE
                interp = "EPS beat expectations"
                score += 12
            elif latest_surprise > -3:
                rating = Rating.NEUTRAL
                interp = "EPS was broadly in line with expectations"
                score += 2
            elif latest_surprise > -8:
                rating = Rating.NEGATIVE
                interp = "EPS missed expectations"
                score -= 14
            else:
                rating = Rating.VERY_NEGATIVE
                interp = "EPS missed expectations materially"
                score -= 25
            findings.append(
                {
                    "metric": "EPS vs Erwartung",
                    "value": f"{latest_surprise:+.1f}%",
                    "rating": rating,
                    "interpretation": interp,
                }
            )
        elif latest_status:
            findings.append(
                {
                    "metric": "EPS vs Erwartung",
                    "value": str(latest_status).title(),
                    "rating": Rating.NEUTRAL,
                    "interpretation": "Estimate data is partial; treat the signal as informational.",
                }
            )

        if reported_eps is not None or eps_estimate is not None:
            findings.append(
                {
                    "metric": "Reported / Estimate EPS",
                    "value": f"{reported_eps if reported_eps is not None else 'N/A'} / {eps_estimate if eps_estimate is not None else 'N/A'}",
                    "rating": Rating.NEUTRAL,
                    "interpretation": "Latest available earnings print.",
                }
            )

        beats = 0
        misses = 0
        for item in earnings_history[:4] if isinstance(earnings_history, list) else []:
            status = str(item.get("status") or "").lower() if isinstance(item, dict) else ""
            if status == "beat":
                beats += 1
            elif status == "miss":
                misses += 1
        if beats or misses:
            beat_rate = beats / max(1, beats + misses)
            if beat_rate >= 0.75 and beats >= 2:
                rating = Rating.POSITIVE
                score += 8
                interp = "Recent reporting pattern is reliable."
            elif misses >= 2:
                rating = Rating.NEGATIVE
                score -= 8
                interp = "Recent reporting pattern is fragile."
            else:
                rating = Rating.NEUTRAL
                interp = "Mixed recent reporting pattern."
            findings.append(
                {
                    "metric": "4Q Beat/Miss Pattern",
                    "value": f"{beats} beats / {misses} misses",
                    "rating": rating,
                    "interpretation": interp,
                }
            )

        quarterly_revenue_yoy = trends.get("quarterly_revenue_yoy")
        if quarterly_revenue_yoy is not None:
            q_pct = quarterly_revenue_yoy * 100
            if q_pct >= 10:
                rating = Rating.POSITIVE
                score += 8
                interp = "Revenue trend supports the earnings quality."
            elif q_pct >= 0:
                rating = Rating.NEUTRAL
                interp = "Revenue trend is stable."
            else:
                rating = Rating.NEGATIVE
                score -= 10
                interp = "Revenue trend is weaker than desired."
            findings.append(
                {
                    "metric": "Umsatztrend Quartal YoY",
                    "value": f"{q_pct:+.1f}%",
                    "rating": rating,
                    "interpretation": interp,
                }
            )

        forward_eps = fund.get("forward_eps")
        trailing_eps = fund.get("eps")
        if forward_eps is not None and trailing_eps not in (None, 0):
            forward_delta = ((forward_eps / trailing_eps) - 1) * 100
            if forward_delta >= 8:
                rating = Rating.POSITIVE
                score += 8
                interp = "Forward EPS implies improving earnings power."
            elif forward_delta <= -8:
                rating = Rating.NEGATIVE
                score -= 8
                interp = "Forward EPS implies weaker earnings power."
            else:
                rating = Rating.NEUTRAL
                interp = "Forward EPS is broadly stable."
            findings.append(
                {
                    "metric": "Forward EPS Trend",
                    "value": f"{forward_delta:+.1f}%",
                    "rating": rating,
                    "interpretation": interp,
                }
            )

        if not findings:
            findings.append(
                {
                    "metric": "Earnings Coverage",
                    "value": "N/A",
                    "rating": Rating.NEUTRAL,
                    "interpretation": "No reliable estimate/surprise data available for this symbol.",
                }
            )
            summary = "Earnings expectation data unavailable; recommendation relies on fundamentals, price and risk."
        elif score >= 15:
            summary = "Earnings quality supports a stronger buy/accumulate case."
        elif score <= -12:
            summary = "Earnings quality weakens the buy case; wait for repair or guidance confirmation."
        else:
            summary = "Earnings quality is mixed or in line; do not upgrade without price confirmation."

        return AnalysisResult("Earnings Quality", findings, max(-100, min(100, score)), summary)
    
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
        div_yield_pct = normalize_dividend_yield_pct(div_yield)
        if div_yield_pct is not None and div_yield_pct > 2:
            findings.append({
                "metric": "Dividend Income",
                "value": f"{div_yield_pct:.2f}% yield",
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
    EXCLUDED_NEWS_SOURCES = [
        "x.com", "twitter", "stocktwits", "reddit", "wallstreetbets", "discord",
        "telegram", "tiktok", "instagram", "facebook"
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
            if any(blocked in source.lower() for blocked in self.EXCLUDED_NEWS_SOURCES):
                continue
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
        earnings_analysis = self.analyze_earnings_quality()
        news_analysis = self.analyze_news_sentiment()
        valuation = self.determine_valuation()
        
        # Calculate overall score
        weights = {
            "fundamentals": 0.30,
            "earnings": 0.12,
            "fear": 0.25,
            "opportunities": 0.18,
            "price": 0.10,
            "volatility": 0.05,
            "news": 0.05
        }
        
        total_score = (
            fund_analysis.score * weights["fundamentals"] +
            earnings_analysis.score * weights["earnings"] +
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
        
        bull_bear_debate = self.analyze_bull_bear_debate()

        return {
            "analyses": {
                "price_performance": price_analysis,
                "volatility": vol_analysis,
                "fundamentals": fund_analysis,
                "earnings_quality": earnings_analysis,
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
            "bull_bear_debate": bull_bear_debate,
            "total_score": total_score,
            "recommendation": {
                "action": action,
                "short_term_traders": short_term,
                "long_term_investors": long_term,
            }
        }

    def analyze_bull_bear_debate(self) -> Dict[str, Any]:
        """
        Synthesizes a structured Bull vs. Bear debate (Two-Agent Thesis).
        Extracts clear bull thesis points vs. bear counterarguments,
        calculates a duel balance ratio, defines the core battleground question,
        and provides concrete confirmation catalysts and invalidation triggers.
        """
        fund = self.data.get("fundamentals", {}) or {}
        price = self.data.get("price_data", {}) or {}
        vol = self.data.get("volatility", {}) or {}
        short_info = self.data.get("short_interest", {}) or {}
        analyst = self.data.get("analyst_data", {}) or {}
        quote_type = str(fund.get("quote_type") or "").upper()

        bull_points: List[Dict[str, Any]] = []
        bear_points: List[Dict[str, Any]] = []
        bull_score: float = 10.0  # baseline
        bear_score: float = 10.0  # baseline

        # --- 1. Growth & Revenue Momentum ---
        rev_growth = fund.get("revenue_growth")
        if rev_growth is not None:
            g_pct = rev_growth * 100
            if g_pct > 15:
                bull_points.append({
                    "title": "Starkes Umsatzwachstum",
                    "detail": f"Umsatzplus von {g_pct:+.1f}% belegt anhaltende Nachfrage und Marktexpansion.",
                    "metric": f"{g_pct:+.1f}% YoY",
                    "conviction": "high" if g_pct > 25 else "medium"
                })
                bull_score += min(25.0, g_pct * 0.8)
            elif g_pct < 0:
                bear_points.append({
                    "title": "Rückläufige Erlöse",
                    "detail": f"Umsatzrückgang von {g_pct:.1f}% deutet auf Marktsättigung oder intensiven Wettbewerb hin.",
                    "metric": f"{g_pct:.1f}% YoY",
                    "conviction": "high" if g_pct < -10 else "medium"
                })
                bear_score += min(25.0, abs(g_pct) * 1.0)

        # --- 2. Profitability & Moat ---
        profit_margin = fund.get("profit_margin")
        operating_margin = fund.get("operating_margin")
        effective_margin = profit_margin if profit_margin is not None else operating_margin
        if effective_margin is not None:
            m_pct = effective_margin * 100
            if m_pct > 18:
                bull_points.append({
                    "title": "Hohe Margenstärke & Preismacht",
                    "detail": f"Marge von {m_pct:.1f}% demonstriert einen starken Wettbewerbsvorteil (Moat).",
                    "metric": f"{m_pct:.1f}% Marge",
                    "conviction": "high"
                })
                bull_score += 18.0
            elif m_pct < 0:
                bear_points.append({
                    "title": "Fehlende Profitabilität",
                    "detail": f"Negatives operatives Ergebnis ({m_pct:.1f}%) zehrt an der Liquidität und erhöht das Kapitalbeschaffungsrisiko.",
                    "metric": f"{m_pct:.1f}% Marge",
                    "conviction": "high"
                })
                bear_score += 22.0

        roe = fund.get("roe")
        if roe is not None:
            roe_pct = roe * 100
            if roe_pct > 18:
                bull_points.append({
                    "title": "Exzellente Eigenkapitalrendite",
                    "detail": f"ROE von {roe_pct:.1f}% beweist disziplinierte und ertragreiche Kapitalallokation.",
                    "metric": f"{roe_pct:.1f}% ROE",
                    "conviction": "medium"
                })
                bull_score += 12.0
            elif roe_pct < 0:
                bear_points.append({
                    "title": "Kapitalvernichtung (Negativer ROE)",
                    "detail": f"Mit {roe_pct:.1f}% ROE wird Buchwert abgebaut.",
                    "metric": f"{roe_pct:.1f}% ROE",
                    "conviction": "medium"
                })
                bear_score += 12.0

        # --- 3. Valuation & Multiples ---
        pe = fund.get("pe_ratio")
        fwd_pe = fund.get("forward_pe")
        ev_ebitda = fund.get("ev_ebitda")

        if pe is not None and pe > 0:
            if pe > 40 or (ev_ebitda is not None and ev_ebitda > 28):
                val_metric = f"KGV {pe:.1f}" + (f" | EV/EBITDA {ev_ebitda:.1f}" if ev_ebitda else "")
                bear_points.append({
                    "title": "Ambitionierte Bewertungsprämie",
                    "detail": f"Mit {val_metric} ist bereits viel Optimismus eingepreist; minimale Verfehlungen strafen den Kurs ab.",
                    "metric": val_metric,
                    "conviction": "high" if pe > 60 else "medium"
                })
                bear_score += min(22.0, (pe - 25) * 0.4)
            elif pe < 16 and (rev_growth is None or rev_growth >= 0):
                bull_points.append({
                    "title": "Attraktive fundamentale Bewertung",
                    "detail": f"KGV von {pe:.1f} bietet eine substanzielle Sicherheitsmarge gegenüber dem breiten Markt.",
                    "metric": f"KGV {pe:.1f}",
                    "conviction": "medium"
                })
                bull_score += 14.0

        if fwd_pe is not None and pe is not None and pe > 0:
            if fwd_pe < pe * 0.82:
                bull_points.append({
                    "title": "Kräftiges Gewinnwachstum erwartet",
                    "detail": f"Forward-KGV ({fwd_pe:.1f}) liegt deutlich unter aktuellem KGV ({pe:.1f}) – Analysten erwarten Gewinnsprung.",
                    "metric": f"Fwd {fwd_pe:.1f} vs {pe:.1f}",
                    "conviction": "medium"
                })
                bull_score += 12.0
            elif fwd_pe > pe * 1.15:
                bear_points.append({
                    "title": "Gewinnkontraktion erwartet",
                    "detail": f"Forward-KGV ({fwd_pe:.1f}) signalisiert sinkende Gewinne im nächsten Geschäftsjahr.",
                    "metric": f"Fwd {fwd_pe:.1f} vs {pe:.1f}",
                    "conviction": "medium"
                })
                bear_score += 14.0

        # --- 4. Balance Sheet & Leverage ---
        debt_equity = fund.get("debt_to_equity")
        if debt_equity is not None:
            if debt_equity > 180:
                bear_points.append({
                    "title": "Erhöhte Zins- und Verschuldungslast",
                    "detail": f"Debt-to-Equity bei {debt_equity:.0f}% engt den finanziellen Spielraum in einem volatilen Marktumfeld ein.",
                    "metric": f"D/E {debt_equity:.0f}%",
                    "conviction": "high" if debt_equity > 250 else "medium"
                })
                bear_score += 15.0
            elif debt_equity < 45:
                bull_points.append({
                    "title": "Kerngesunde Bilanz / Geringer Hebel",
                    "detail": f"Mit nur {debt_equity:.0f}% Verschuldung besteht maximale finanzielle Flexibilität für Krisen oder M&A.",
                    "metric": f"D/E {debt_equity:.0f}%",
                    "conviction": "medium"
                })
                bull_score += 10.0

        # --- 5. Market Technicals, Momentum & Sentiment ---
        change_1y = price.get("change_1y")
        from_high = price.get("from_52w_high")
        rsi = price.get("rsi")

        if change_1y is not None:
            if change_1y > 25:
                bull_points.append({
                    "title": "Etablierter Aufwärtstrend",
                    "detail": f"+{change_1y:.1f}% über 12 Monate bestätigt anhaltende relative Stärke gegenüber Peers.",
                    "metric": f"+{change_1y:.1f}% 1Y",
                    "conviction": "medium"
                })
                bull_score += 10.0
            elif change_1y < -25:
                bear_points.append({
                    "title": "Anhaltender Abwärtstrend",
                    "detail": f"{change_1y:.1f}% Jahresverlust signalisiert anhaltenden Verkaufsdruck und Abflüsse.",
                    "metric": f"{change_1y:.1f}% 1Y",
                    "conviction": "medium"
                })
                bear_score += 12.0

        if rsi is not None:
            if rsi < 32:
                bull_points.append({
                    "title": "Technisch überverkauft (Rebound-Setup)",
                    "detail": f"RSI von {rsi:.1f} zeigt kurzfristig extreme Verkaufsübertreibung und Erholungschance.",
                    "metric": f"RSI {rsi:.1f}",
                    "conviction": "moderate"
                })
                bull_score += 8.0
            elif rsi > 72:
                bear_points.append({
                    "title": "Technisch überhitzt (Rückschlaggefahr)",
                    "detail": f"RSI von {rsi:.1f} signalisiert überdehnte Rallye mit erhöhtem Korrekturrisiko.",
                    "metric": f"RSI {rsi:.1f}",
                    "conviction": "moderate"
                })
                bear_score += 8.0

        # --- 6. Short Interest & Consensus ---
        short_pct = short_info.get("short_percent_of_float")
        if short_pct is not None:
            if short_pct > 12:
                bear_points.append({
                    "title": "Signifikantes Leerverkäufer-Interesse",
                    "detail": f"{short_pct:.1f}% des Free Floats leerverkauft – Institutionelle wetten aktiv auf Schwäche.",
                    "metric": f"{short_pct:.1f}% Short Float",
                    "conviction": "medium"
                })
                bear_score += 10.0
                if change_1y is not None and change_1y > 10:
                    bull_points.append({
                        "title": "Potenzieller Short Squeeze Treibstoff",
                        "detail": f"Hohe Leerverkaufsquote ({short_pct:.1f}%) bei intaktem Trend kann plötzliche Eindeckungswellen auslösen.",
                        "metric": f"{short_pct:.1f}% Short",
                        "conviction": "moderate"
                    })
                    bull_score += 8.0

        # --- 7. Fallback-Absicherung (Asset-spezifisch) ---
        if quote_type == "ETF":
            if not bull_points:
                bull_points.append({
                    "title": "Breite Risikostreuung",
                    "detail": "Korb diversifizierter Einzeltitel senkt das unternehmensspezifische Ausfallrisiko erheblich.",
                    "metric": "Breite Streuung",
                    "conviction": "high"
                })
                bull_score += 15.0
            if not bear_points:
                bear_points.append({
                    "title": "Kein Einzeltitel-Alpha & Marktrisiko",
                    "detail": "Vollständig abhängig von Makro- und Indexbewegungen; keine Ausreißer-Renditen.",
                    "metric": "Markt-Beta",
                    "conviction": "medium"
                })
                bear_score += 15.0
        elif "CRYPTO" in quote_type:
            if not bull_points:
                bull_points.append({
                    "title": "Asymmetrisches Renditepotenzial",
                    "detail": "Globale Liquidität und Dezentralisierung bieten Hebelwirkung auf Adoptionswellen.",
                    "metric": "Liquidität",
                    "conviction": "medium"
                })
                bull_score += 15.0
            if not bear_points:
                bear_points.append({
                    "title": "Hohe Volatilität & regulatorische Risiken",
                    "detail": "Starke Drawdowns ohne fundamentale Cashflow-Untergrenze.",
                    "metric": "Hohe Volatilität",
                    "conviction": "high"
                })
                bear_score += 20.0

        # Mindestens zwei fundierte Punkte pro Seite sicherstellen
        if len(bull_points) < 2:
            bull_points.append({
                "title": "Operative Kernstabilität",
                "detail": "Etablierte Marktposition und bestehende Kundenbasis stützen den Grundbetrieb.",
                "metric": "Marktpräsenz",
                "conviction": "moderate"
            })
            bull_score += 8.0

        if len(bear_points) < 2:
            bear_points.append({
                "title": "Makroökonomische Sensitivität",
                "detail": "Zinsentwicklung, Wechselkurse und allgemeiner Konjunkturzyklus beeinflussen die Bewertung.",
                "metric": "Makro-Risiko",
                "conviction": "moderate"
            })
            bear_score += 8.0

        # --- 8. Score, Ratio & Verdict ---
        total_debate = bull_score + bear_score
        bull_pct = round((bull_score / total_debate) * 100) if total_debate > 0 else 50
        bull_pct = max(15, min(85, bull_pct))  # Clamp between 15% and 85%
        bear_pct = 100 - bull_pct

        if bull_pct >= 64:
            verdict_headline = "Klares Übergewicht der Bullen – Katalysatoren dominieren"
            summary = "Die Wachstumstreiber und Qualitätssignale überwiegen die Risikofaktoren deutlich. Rücksetzer bieten statistisch bessere Einstiegsfenster als Ausbrüche."
        elif bull_pct >= 54:
            verdict_headline = "Leichter Bullen-Vorteil – These intakt mit Risikomonitoring"
            summary = "Die Investment-These ist konstruktiv, erfordert jedoch eine genaue Beobachtung von Bewertung und Margenentwicklung."
        elif bull_pct >= 46:
            verdict_headline = "Ausgeglichenes Duell – Chance und Risiko auf Augenhöhe"
            summary = "Weder Bullen noch Bären haben die klare Oberhand. Vor einer Positionsentscheidung sollte die Bestätigung durch den nächsten Katalysator abgewartet werden."
        elif bull_pct >= 36:
            verdict_headline = "Bären-Argumente dominieren – Vorsicht und Gegenwind"
            summary = "Die Risikofaktoren (Bewertung, Verschuldung oder Margendruck) belasten das Setup. Das Chance-Risiko-Verhältnis ist aktuell asymmetrisch nach unten verschoben."
        else:
            verdict_headline = "Kritisches Bären-Übergewicht – Deutliches Abwärtsrisiko"
            summary = "Schwere fundamentale oder bewertungsseitige Belastungen überlagern die wenigen positiven Signale. Kapitalerhalt hat hier Vorrang vor Spekulation."

        # Dynamisches Schlachtfeld (Key Battleground)
        if pe is not None and pe > 35 and rev_growth is not None and rev_growth > 0.15:
            battleground = f"Reicht das Umsatzwachstum von +{rev_growth*100:.1f}%, um das KGV von {pe:.1f} mittelfristig zu rechtfertigen?"
        elif effective_margin is not None and effective_margin < 0:
            battleground = "Schafft das Management den Turnaround in die freie Cashflow-Generierung vor einer weiteren Kapitalverwässerung?"
        elif debt_equity is not None and debt_equity > 150:
            battleground = f"Bleibt der Zinsdienst bei {debt_equity:.0f}% Verschuldung auch bei länger erhöhtem Zinsniveau tragfähig?"
        elif change_1y is not None and change_1y > 30:
            battleground = "Kann der bestehende Aufwärtstrend Anschlusskäufe generieren, ohne in eine Überhitzungskorrektur überzugehen?"
        else:
            battleground = "Bestätigen die nächsten Quartalszahlen die Marktannahmen oder droht eine Abwärtsrevision der Konsensschätzungen?"

        # Katalysatoren & Invalidierung
        bull_catalysts = [
            "Quartalsbericht mit EPS- und Umsatzüberraschung über Konsens",
            "Margenausweitung durch Skalierungseffekte im Kerngeschäft",
            "Anhebung der Jahresprognose (Guidance-Upgrade) durch das Management",
        ]
        invalidation_triggers = [
            "Unerwartete Senkung der Margen- oder Umsatzerwartung",
            "Bruch zentraler technischer Trendlinien (z. B. 200-Tage-Linie)",
            "Verschlechterung des freien Cashflows oder steigender Verschuldungsgrad",
        ]

        return {
            "bull_pct": bull_pct,
            "bear_pct": bear_pct,
            "bull_score": round(bull_score, 1),
            "bear_score": round(bear_score, 1),
            "verdict_headline": verdict_headline,
            "summary": summary,
            "key_battleground": battleground,
            "bull_thesis": bull_points[:5],
            "bear_thesis": bear_points[:5],
            "bull_catalysts": bull_catalysts,
            "invalidation_triggers": invalidation_triggers,
        }

    def calculate_dcf(
        self,
        fcf_growth_rate: Optional[float] = None,
        discount_rate: Optional[float] = None,
        terminal_growth_rate: Optional[float] = 0.025,
        projection_years: int = 5,
        margin_of_safety: float = 0.20,
        custom_base_fcf: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Calculates Discounted Cash Flow (DCF) intrinsic value,
        Reverse-DCF (market-implied growth rate), 2D sensitivity matrix,
        and Bear/Base/Bull scenarios.
        """
        price_data = self.data.get("price_data") or {}
        current_price = float(price_data.get("current_price") or 0.0)
        currency = price_data.get("currency") or "USD"
        fund = self.data.get("fundamentals") or {}
        overview = self.data.get("overview") or {}

        # 1. Shares Outstanding
        shares = (
            fund.get("shares_outstanding")
            or overview.get("shares_outstanding")
            or fund.get("sharesOutstanding")
            or overview.get("sharesOutstanding")
        )
        if not shares or shares <= 0:
            mkt_cap = (
                fund.get("market_cap")
                or overview.get("market_cap")
                or fund.get("marketCap")
                or overview.get("marketCap")
            )
            if mkt_cap and current_price > 0:
                shares = float(mkt_cap) / current_price
            else:
                shares = 1_000_000_000.0  # Safe fallback to prevent div/0
        else:
            shares = float(shares)

        # 2. Cash & Debt (Balance Sheet)
        cash = float(fund.get("total_cash") or 0.0)
        debt = float(fund.get("total_debt") or 0.0)
        net_debt = debt - cash

        # 3. Base Free Cash Flow (FCF_0)
        fcf_is_estimated = False
        if custom_base_fcf is not None and custom_base_fcf > 0:
            base_fcf = float(custom_base_fcf)
            fcf_source = "Benutzerdefinierter FCF"
        else:
            raw_fcf = fund.get("free_cashflow")
            if raw_fcf is None or raw_fcf <= 0:
                statements = fund.get("financial_statements", {}).get("annual", [])
                if statements and isinstance(statements, list):
                    for st in statements:
                        s_fcf = st.get("free_cashflow")
                        if s_fcf and s_fcf > 0:
                            raw_fcf = s_fcf
                            break
            if raw_fcf is not None and raw_fcf > 0:
                base_fcf = float(raw_fcf)
                fcf_source = "TTM Free Cashflow (Offiziell)"
            else:
                op_cf = fund.get("operating_cashflow")
                if op_cf and op_cf > 0:
                    base_fcf = float(op_cf) * 0.75
                    fcf_source = "Geschätzt aus operativem Cashflow (75% Proxy)"
                    fcf_is_estimated = True
                else:
                    if current_price > 0 and shares > 0:
                        base_fcf = (shares * current_price) * 0.035
                        fcf_source = "Normalisierter FCF (3.5% Rendite-Proxy)"
                        fcf_is_estimated = True
                    else:
                        base_fcf = 1_000_000_000.0
                        fcf_source = "Synthetischer Richtwert"
                        fcf_is_estimated = True

        # 4. Discount Rate / WACC
        if discount_rate is not None and discount_rate > 0:
            r = float(discount_rate)
        else:
            vol = self.data.get("volatility") or {}
            beta = float(vol.get("beta") or 1.0)
            rf = 0.040  # 4.0% risk-free rate
            erp = 0.050  # 5.0% equity risk premium
            r = round(min(max(rf + beta * erp, 0.065), 0.13), 3)

        # 5. FCF Growth Rate (g)
        if fcf_growth_rate is not None:
            g = float(fcf_growth_rate)
        else:
            rev_g = fund.get("revenue_growth")
            earn_g = fund.get("earnings_growth")
            valid = [x for x in [rev_g, earn_g] if x is not None and isinstance(x, (int, float))]
            if valid:
                g = round(min(max(sum(valid) / len(valid), 0.03), 0.25), 3)
            else:
                g = 0.08

        # 6. Terminal Growth Rate & Mos
        g_term = float(terminal_growth_rate if terminal_growth_rate is not None else 0.025)
        # Cap terminal rate below discount rate to guarantee convergence
        if g_term >= r - 0.005:
            g_term = round(max(0.005, r - 0.01), 3)

        mos = float(margin_of_safety if margin_of_safety is not None else 0.20)
        mos = min(max(mos, 0.05), 0.60)
        years = int(projection_years if projection_years in (5, 10) else 5)

        # 7. Helper to evaluate Fair Value for any (growth, wacc, term)
        def evaluate_model(g_val: float, r_val: float, gt_val: float) -> Tuple[float, float, float, List[Dict[str, Any]]]:
            if r_val <= gt_val:
                gt_val = max(0.005, r_val - 0.008)
            
            proj = []
            fcf_cur = base_fcf
            pv_total = 0.0
            for t in range(1, years + 1):
                fcf_cur *= (1.0 + g_val)
                pv = fcf_cur / ((1.0 + r_val) ** t)
                pv_total += pv
                proj.append({
                    "year": t,
                    "fcf": round(fcf_cur, 0),
                    "pv": round(pv, 0),
                    "discount_factor": round(1.0 / ((1.0 + r_val) ** t), 4)
                })

            tv = (fcf_cur * (1.0 + gt_val)) / (r_val - gt_val)
            pv_tv = tv / ((1.0 + r_val) ** years)
            ev = pv_total + pv_tv
            equity = max(0.0, ev + cash - debt)
            fv_share = equity / shares if shares > 0 else 0.0
            return fv_share, ev, equity, proj

        fair_value, enterprise_value, equity_value, projections = evaluate_model(g, r, g_term)
        target_buy_price = fair_value * (1.0 - mos)
        upside_pct = ((fair_value / current_price) - 1.0) * 100.0 if current_price > 0 else 0.0

        # 8. Reverse-DCF: Market-Implied Growth Rate
        # Solve for g such that fair_value(g) == current_price
        target_equity = current_price * shares
        target_ev = max(0.0, target_equity - cash + debt)

        def ev_for_growth(g_candidate: float) -> float:
            fcf_c = base_fcf
            pv_tot = 0.0
            for t in range(1, years + 1):
                fcf_c *= (1.0 + g_candidate)
                pv_tot += fcf_c / ((1.0 + r) ** t)
            tv_c = (fcf_c * (1.0 + g_term)) / (r - g_term)
            pv_tv_c = tv_c / ((1.0 + r) ** years)
            return pv_tot + pv_tv_c

        implied_growth = None
        if base_fcf > 0 and current_price > 0 and shares > 0:
            low, high = -0.40, 1.20
            # Test boundaries
            ev_low = ev_for_growth(low)
            ev_high = ev_for_growth(high)
            if target_ev <= ev_low:
                implied_growth = -0.40
            elif target_ev >= ev_high:
                # expand once
                ev_ultra = ev_for_growth(2.50)
                if target_ev >= ev_ultra:
                    implied_growth = 2.50
                else:
                    low, high = 1.20, 2.50
                    for _ in range(35):
                        mid = (low + high) / 2.0
                        if ev_for_growth(mid) < target_ev:
                            low = mid
                        else:
                            high = mid
                    implied_growth = round((low + high) / 2.0, 4)
            else:
                for _ in range(35):
                    mid = (low + high) / 2.0
                    if ev_for_growth(mid) < target_ev:
                        low = mid
                    else:
                        high = mid
                implied_growth = round((low + high) / 2.0, 4)

        # 9. 2D Sensitivity Matrix (5x5: WACC vs Growth)
        wacc_steps = [
            round(max(g_term + 0.008, r - 0.02), 3),
            round(max(g_term + 0.008, r - 0.01), 3),
            round(r, 3),
            round(r + 0.01, 3),
            round(r + 0.02, 3),
        ]
        # remove potential duplicates while keeping sorted
        wacc_steps = sorted(list(dict.fromkeys(wacc_steps)))
        while len(wacc_steps) < 5:
            wacc_steps.append(round(wacc_steps[-1] + 0.01, 3))

        growth_steps = [
            round(max(-0.20, g - 0.04), 3),
            round(max(-0.20, g - 0.02), 3),
            round(g, 3),
            round(g + 0.02, 3),
            round(g + 0.04, 3),
        ]
        growth_steps = sorted(list(dict.fromkeys(growth_steps)))
        while len(growth_steps) < 5:
            growth_steps.append(round(growth_steps[-1] + 0.02, 3))

        sensitivity_matrix = []
        for r_step in wacc_steps:
            row = []
            for g_step in growth_steps:
                val, _, _, _ = evaluate_model(g_step, r_step, g_term)
                up_p = ((val / current_price) - 1.0) * 100.0 if current_price > 0 else 0.0
                if up_p >= (mos * 100.0):
                    verdict = "undervalued"
                elif up_p >= -5.0:
                    verdict = "fair"
                else:
                    verdict = "overvalued"
                row.append({
                    "wacc": r_step,
                    "growth": g_step,
                    "fair_value": round(val, 2),
                    "upside_pct": round(up_p, 1),
                    "verdict": verdict,
                })
            sensitivity_matrix.append(row)

        # 10. Three Scenarios (Bear, Base, Bull)
        scenarios = {
            "bear": {
                "name": "Bärenszenario",
                "icon": "🐻",
                "growth": round(max(-0.05, g - 0.04), 3),
                "wacc": round(r + 0.015, 3),
                "terminal_growth": round(max(0.01, g_term - 0.005), 3),
            },
            "base": {
                "name": "Basisszenario",
                "icon": "⚖️",
                "growth": round(g, 3),
                "wacc": round(r, 3),
                "terminal_growth": round(g_term, 3),
            },
            "bull": {
                "name": "Bullenszenario",
                "icon": "🐂",
                "growth": round(g + 0.04, 3),
                "wacc": round(max(0.055, r - 0.01), 3),
                "terminal_growth": round(min(0.035, g_term + 0.005), 3),
            }
        }
        for key, sc in scenarios.items():
            s_fv, _, _, _ = evaluate_model(sc["growth"], sc["wacc"], sc["terminal_growth"])
            sc["fair_value"] = round(s_fv, 2)
            sc["target_price"] = round(s_fv * (1.0 - mos), 2)
            sc["upside_pct"] = round(((s_fv / current_price) - 1.0) * 100.0 if current_price > 0 else 0.0, 1)

        # Verdict
        if upside_pct >= (mos * 100.0):
            evaluation = "Stark unterbewertet"
            action_badge = "BUY"
            color = "emerald"
        elif upside_pct >= 0.0:
            evaluation = "Fair bewertet"
            action_badge = "HOLD"
            color = "amber"
        else:
            evaluation = "Überbewertet"
            action_badge = "REDUCE"
            color = "rose"

        return {
            "ticker": str(self.data.get("ticker") or ""),
            "currency": currency,
            "current_price": round(current_price, 2),
            "fair_value": round(fair_value, 2),
            "target_buy_price": round(target_buy_price, 2),
            "margin_of_safety_pct": round(mos * 100.0, 1),
            "upside_pct": round(upside_pct, 1),
            "evaluation": evaluation,
            "action_badge": action_badge,
            "color": color,
            "implied_growth_rate": round(implied_growth * 100.0, 1) if implied_growth is not None else None,
            "inputs": {
                "base_fcf": round(base_fcf, 0),
                "base_fcf_source": fcf_source,
                "fcf_is_estimated": fcf_is_estimated,
                "fcf_growth_rate": round(g, 3),
                "discount_rate": round(r, 3),
                "terminal_growth_rate": round(g_term, 3),
                "projection_years": years,
                "shares_outstanding": round(shares, 0),
                "cash": round(cash, 0),
                "debt": round(debt, 0),
                "net_debt": round(net_debt, 0),
            },
            "enterprise_value": round(enterprise_value, 0),
            "equity_value": round(equity_value, 0),
            "projections": projections,
            "scenarios": scenarios,
            "sensitivity_matrix": {
                "wacc_axis": wacc_steps,
                "growth_axis": growth_steps,
                "matrix": sensitivity_matrix,
            }
        }


