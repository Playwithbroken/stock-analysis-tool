"""
Risk Scanner Module
Identifies high-risk, high-reward stock opportunities using AI-driven analysis.
"""

from typing import List, Dict, Any
import pandas as pd
from src.data_fetcher import DataFetcher
from src.analyzer import StockAnalyzer

class RiskScanner:
    def __init__(self):
        # Expanded universe for high-risk scanning
        self.scan_universe = [
            # Small-cap growth
            "SOFI", "PLTR", "PATH", "HOOD", "UPST", "FRGT", "MSTR",
            # Volatile tech
            "SMCI", "ARM", "AI", "CELH", "IONQ", "RKLB",
            # Biotech/speculative
            "CRSP", "EDIT", "NTLA", "BEAM",
            # Crypto-adjacent
            "COIN", "MARA", "RIOT", "CLSK",
            # EV/Clean energy
            "RIVN", "LCID", "PLUG", "FCEL", "ENPH",
            # Emerging tech
            "U", "SNOW", "DDOG", "NET", "CRWD"
        ]

    def fallback_opportunities(self) -> List[Dict[str, Any]]:
        """Return stable high-risk ideas when live scoring is slow or sparse."""
        return [
            {
                "ticker": "IONQ",
                "name": "IonQ, Inc.",
                "risk_score": 82.0,
                "reward_score": 74.0,
                "opportunity_score": 76.4,
                "recommendation": "WATCH - Quantum moonshot, only on confirmed momentum",
                "confidence": "Low",
                "price": None,
                "market_cap": None,
                "reasons": ["Very high volatility", "Quantum narrative", "Execution risk"],
                "volatility": None,
                "growth": None,
                "upside_potential": None,
                "data_mode": "fallback",
            },
            {
                "ticker": "RKLB",
                "name": "Rocket Lab USA, Inc.",
                "risk_score": 76.0,
                "reward_score": 70.0,
                "opportunity_score": 71.8,
                "recommendation": "WATCH - Space infrastructure growth setup",
                "confidence": "Low",
                "price": None,
                "market_cap": None,
                "reasons": ["Space infrastructure", "Contract-driven upside", "Execution risk"],
                "volatility": None,
                "growth": None,
                "upside_potential": None,
                "data_mode": "fallback",
            },
            {
                "ticker": "SOFI",
                "name": "SoFi Technologies, Inc.",
                "risk_score": 68.0,
                "reward_score": 66.0,
                "opportunity_score": 66.6,
                "recommendation": "WATCH - Fintech growth with rate sensitivity",
                "confidence": "Low",
                "price": None,
                "market_cap": None,
                "reasons": ["Fintech growth", "Rate sensitivity", "Profitability watch"],
                "volatility": None,
                "growth": None,
                "upside_potential": None,
                "data_mode": "fallback",
            },
        ]
    
    def calculate_risk_reward_score(self, ticker: str) -> Dict[str, Any]:
        """
        Calculate comprehensive risk-reward score for a stock.
        Returns dict with score, reasoning, and key metrics.
        """
        try:
            fetcher = DataFetcher(ticker)
            data = fetcher.get_all_data()
            analyzer = StockAnalyzer(data)
            
            # Get all analysis components
            price_data = data.get("price_data", {})
            fundamentals = data.get("fundamentals", {})
            volatility = data.get("volatility", {})
            
            # Initialize scoring
            risk_score = 0  # 0-100, higher = more risk
            reward_score = 0  # 0-100, higher = more potential
            reasons = []
            
            # === RISK FACTORS ===
            
            # 1. Volatility (high volatility = high risk)
            vol_annual = volatility.get("volatility_annual", 0)
            if vol_annual > 60:
                risk_score += 30
                reasons.append(f"Extreme volatility: {vol_annual:.1f}% annual")
            elif vol_annual > 40:
                risk_score += 20
                reasons.append(f"High volatility: {vol_annual:.1f}% annual")
            
            # 2. Market cap (smaller = riskier)
            market_cap = fundamentals.get("market_cap", 0)
            if market_cap < 1e9:  # < $1B
                risk_score += 25
                reasons.append("Micro-cap: High liquidity risk")
            elif market_cap < 5e9:  # < $5B
                risk_score += 15
                reasons.append("Small-cap: Elevated risk")
            
            # 3. Profitability
            profit_margin = fundamentals.get("profit_margin", 0)
            if profit_margin < 0:
                risk_score += 20
                reasons.append("Unprofitable: Burning cash")
            
            # 4. Debt
            debt_equity = fundamentals.get("debt_to_equity", 0)
            if debt_equity > 150:
                risk_score += 15
                reasons.append(f"High debt: {debt_equity:.0f}% D/E ratio")
            
            # === REWARD FACTORS ===
            
            # 1. Revenue growth (high growth = high potential)
            rev_growth = fundamentals.get("revenue_growth", 0)
            if rev_growth > 0.40:  # >40% growth
                reward_score += 35
                reasons.append(f"Explosive growth: {rev_growth*100:.1f}% revenue")
            elif rev_growth > 0.20:  # >20% growth
                reward_score += 25
                reasons.append(f"Strong growth: {rev_growth*100:.1f}% revenue")
            
            # 2. Oversold condition (potential rebound)
            from_52w_high = price_data.get("from_52w_high", 0)
            if from_52w_high < -40:  # Down >40% from high
                reward_score += 25
                reasons.append(f"Deeply oversold: {from_52w_high:.1f}% from 52W high")
            elif from_52w_high < -25:
                reward_score += 15
                reasons.append(f"Oversold: {from_52w_high:.1f}% from 52W high")
            
            # 3. Analyst upside
            analyst_data = data.get("analyst_data", {})
            current_price = price_data.get("current_price", 0)
            target_mean = analyst_data.get("target_mean", 0)
            if current_price and target_mean:
                upside = ((target_mean / current_price) - 1) * 100
                if upside > 50:
                    reward_score += 20
                    reasons.append(f"Massive analyst upside: +{upside:.0f}%")
                elif upside > 25:
                    reward_score += 10
                    reasons.append(f"Strong analyst upside: +{upside:.0f}%")
            
            # 4. Positive momentum despite drawdown
            change_1m = price_data.get("change_1m", 0)
            if from_52w_high < -20 and change_1m > 5:
                reward_score += 15
                reasons.append("Reversal signal: Recent bounce from lows")
            
            # === FINAL SCORING ===
            
            # Normalize scores
            risk_score = min(100, risk_score)
            reward_score = min(100, reward_score)
            
            # Calculate risk-adjusted opportunity score
            # We want high reward and moderate-to-high risk
            if risk_score < 30:  # Too safe, not what we're looking for
                opportunity_score = 0
            else:
                # Reward high-risk, high-reward combinations
                opportunity_score = (reward_score * 0.7) + (risk_score * 0.3)
            
            # AI Recommendation
            if opportunity_score > 70 and reward_score > 60:
                recommendation = "STRONG BUY - High conviction speculative play"
                confidence = "High"
            elif opportunity_score > 55 and reward_score > 45:
                recommendation = "BUY - Attractive risk-reward setup"
                confidence = "Moderate"
            elif opportunity_score > 40:
                recommendation = "WATCH - Potential developing"
                confidence = "Low"
            else:
                recommendation = "PASS - Insufficient upside for risk"
                confidence = "N/A"
            
            return {
                "ticker": ticker,
                "name": data.get("company_name", ticker),
                "risk_score": float(round(risk_score, 1)),
                "reward_score": float(round(reward_score, 1)),
                "opportunity_score": float(round(opportunity_score, 1)),
                "recommendation": recommendation,
                "confidence": confidence,
                "price": float(current_price) if current_price else None,
                "market_cap": int(market_cap) if market_cap else None,
                "reasons": reasons[:5],  # Top 5 reasons
                "volatility": float(vol_annual) if vol_annual else None,
                "growth": float(rev_growth * 100) if rev_growth else 0.0,
                "upside_potential": float(upside) if current_price and target_mean else None
            }
            
        except Exception as e:
            print(f"Error scanning {ticker}: {str(e)}")
            return None
    
    async def calculate_risk_reward_score_async(self, ticker: str) -> Dict[str, Any]:
        """Async wrapper for risk-reward calculation."""
        import asyncio
        try:
            def fetch_and_score():
                return self.calculate_risk_reward_score(ticker)
            
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, fetch_and_score)
        except Exception as e:
            print(f"Error async scanning {ticker}: {str(e)}")
            return None
    
    async def scan_opportunities(self, min_opportunity_score: float = 40) -> List[Dict[str, Any]]:
        """
        Scan universe in parallel and return top high-risk opportunities.
        """
        import asyncio
        tasks = [self.calculate_risk_reward_score_async(ticker) for ticker in self.scan_universe[:18]]
        try:
            raw_results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
        except asyncio.TimeoutError:
            raw_results = []
        results = [r for r in raw_results if r]
        
        # Filter and sort
        opportunities = [r for r in results if r["opportunity_score"] >= min_opportunity_score]
        opportunities.sort(key=lambda x: x["opportunity_score"], reverse=True)
        
        if not opportunities:
            return self.fallback_opportunities()

        return opportunities[:10]  # Top 10
