"""
Factor & Smart Beta Decomposition Engine (Fama-French & Barra Multi-Factor Model)
Computes institutional factor exposures (Value, Quality, Momentum, Low Volatility, Size, Shareholder Yield),
Morningstar 9-Grid Style Box classification, benchmark comparisons, and regime vulnerability assessments.
"""

from typing import Dict, Any, List, Optional
import math


class FactorEngine:
    """
    Institutional Smart Beta & Multi-Factor Attribution Engine.
    """

    # Global Benchmark Reference Points (approximate MSCI World / S&P 500 median standards)
    BENCHMARK = {
        "pe_ratio": 21.0,
        "pb_ratio": 2.9,
        "fcf_yield": 0.045,
        "roe": 0.145,
        "profit_margin": 0.115,
        "debt_to_equity": 1.15,
        "beta": 1.0,
        "volatility": 0.165,
        "return_1y": 0.11,
        "return_3m": 0.028,
        "market_cap_billions": 48.0,
        "dividend_yield": 0.019
    }

    @staticmethod
    def _clamp(val: float, min_val: float, max_val: float) -> float:
        return max(min_val, min(max_val, float(val)))

    @staticmethod
    def _to_z_score(score_0_100: float) -> float:
        """Converts a 0-100 score (median ~50, std ~16.67) to a standard Z-score (-3.0 to +3.0)."""
        z = (score_0_100 - 50.0) / 16.67
        return round(max(-3.0, min(3.0, z)), 2)

    @staticmethod
    def score_value(
        pe: Optional[float] = None,
        pb: Optional[float] = None,
        fcf_yield: Optional[float] = None,
        dividend_yield: Optional[float] = None
    ) -> float:
        """
        Value Factor (HML): Higher score = Cheaper valuation / higher cashflow yield.
        Returns score in [0, 100].
        """
        sub_scores = []

        # P/E Score: PE 8 -> 95, PE 15 -> 70, PE 25 -> 40, PE 45 -> 15, PE > 70 -> 5
        if pe is not None and pe > 0:
            if pe <= 10:
                s = 90.0 + (10.0 - pe) * 1.0
            elif pe <= 20:
                s = 70.0 + (20.0 - pe) * 2.0
            elif pe <= 35:
                s = 40.0 + (35.0 - pe) * 2.0
            elif pe <= 60:
                s = 20.0 + (60.0 - pe) * 0.8
            else:
                s = max(5.0, 20.0 - (pe - 60.0) * 0.2)
            sub_scores.append(s)

        # P/B Score: PB 1.0 -> 90, PB 2.5 -> 60, PB 5.0 -> 35, PB > 10 -> 10
        if pb is not None and pb > 0:
            if pb <= 1.5:
                s = 85.0 + (1.5 - pb) * 10.0
            elif pb <= 3.5:
                s = 60.0 + (3.5 - pb) * 12.5
            elif pb <= 8.0:
                s = 30.0 + (8.0 - pb) * 6.67
            else:
                s = max(5.0, 30.0 - (pb - 8.0) * 2.0)
            sub_scores.append(s)

        # FCF Yield Score: 8% -> 90, 5% -> 65, 2% -> 40, <0% -> 15
        if fcf_yield is not None:
            if fcf_yield >= 0.08:
                s = 90.0 + min(10.0, (fcf_yield - 0.08) * 100.0)
            elif fcf_yield >= 0.04:
                s = 60.0 + (fcf_yield - 0.04) * 750.0
            elif fcf_yield >= 0.0:
                s = 30.0 + fcf_yield * 750.0
            else:
                s = max(5.0, 30.0 + fcf_yield * 200.0)
            sub_scores.append(s)

        if not sub_scores:
            return 50.0

        return round(FactorEngine._clamp(sum(sub_scores) / len(sub_scores), 0.0, 100.0), 1)

    @staticmethod
    def score_quality(
        roe: Optional[float] = None,
        profit_margin: Optional[float] = None,
        debt_to_equity: Optional[float] = None,
        overall_score: Optional[float] = None
    ) -> float:
        """
        Quality Factor (RMW): High return on capital, robust margins, disciplined leverage.
        Returns score in [0, 100].
        """
        sub_scores = []

        # ROE: ROE 25% -> 90, 15% -> 65, 8% -> 45, <0 -> 15
        if roe is not None:
            if roe >= 0.25:
                s = 85.0 + min(15.0, (roe - 0.25) * 50.0)
            elif roe >= 0.12:
                s = 60.0 + (roe - 0.12) * 192.3
            elif roe >= 0.0:
                s = 35.0 + roe * 208.3
            else:
                s = max(5.0, 35.0 + roe * 100.0)
            sub_scores.append(s)

        # Net Profit Margin: > 20% -> 90, 10% -> 60, 3% -> 35
        if profit_margin is not None:
            if profit_margin >= 0.20:
                s = 85.0 + min(15.0, (profit_margin - 0.20) * 50.0)
            elif profit_margin >= 0.08:
                s = 55.0 + (profit_margin - 0.08) * 250.0
            elif profit_margin >= 0.0:
                s = 30.0 + profit_margin * 312.5
            else:
                s = max(5.0, 30.0 + profit_margin * 100.0)
            sub_scores.append(s)

        # Debt to Equity: D/E < 0.5 -> 90, 1.0 -> 70, 2.5 -> 40, > 4.0 -> 15
        if debt_to_equity is not None and debt_to_equity >= 0:
            if debt_to_equity <= 0.5:
                s = 90.0 - debt_to_equity * 20.0
            elif debt_to_equity <= 1.5:
                s = 80.0 - (debt_to_equity - 0.5) * 20.0
            elif debt_to_equity <= 3.0:
                s = 60.0 - (debt_to_equity - 1.5) * 20.0
            else:
                s = max(5.0, 30.0 - (debt_to_equity - 3.0) * 10.0)
            sub_scores.append(s)

        if overall_score is not None and overall_score > 0:
            sub_scores.append(float(overall_score))

        if not sub_scores:
            return 50.0

        return round(FactorEngine._clamp(sum(sub_scores) / len(sub_scores), 0.0, 100.0), 1)

    @staticmethod
    def score_momentum(
        return_1y: Optional[float] = None,
        return_3m: Optional[float] = None,
        price_to_52w_high: Optional[float] = None
    ) -> float:
        """
        Momentum Factor (WML): Relative price strength over medium term.
        Returns score in [0, 100].
        """
        sub_scores = []

        if return_1y is not None:
            # 1Y Return: +35% -> 90, +10% -> 60, 0% -> 45, -25% -> 15
            if return_1y >= 0.30:
                s = 85.0 + min(15.0, (return_1y - 0.30) * 30.0)
            elif return_1y >= 0.08:
                s = 55.0 + (return_1y - 0.08) * 136.3
            elif return_1y >= -0.15:
                s = 30.0 + (return_1y + 0.15) * 108.7
            else:
                s = max(5.0, 30.0 + (return_1y + 0.15) * 50.0)
            sub_scores.append(s)

        if return_3m is not None:
            # 3M Return: +15% -> 90, +3% -> 60, -5% -> 35
            if return_3m >= 0.12:
                s = 85.0 + min(15.0, (return_3m - 0.12) * 50.0)
            elif return_3m >= 0.02:
                s = 55.0 + (return_3m - 0.02) * 300.0
            elif return_3m >= -0.10:
                s = 30.0 + (return_3m + 0.10) * 208.3
            else:
                s = max(5.0, 30.0 + (return_3m + 0.10) * 100.0)
            sub_scores.append(s)

        if price_to_52w_high is not None and price_to_52w_high > 0:
            # Distance from 52w high: 0.98 -> 90, 0.85 -> 65, 0.70 -> 35
            ratio = min(1.0, float(price_to_52w_high))
            s = 20.0 + ratio * 75.0
            sub_scores.append(s)

        if not sub_scores:
            return 50.0

        return round(FactorEngine._clamp(sum(sub_scores) / len(sub_scores), 0.0, 100.0), 1)

    @staticmethod
    def score_low_volatility(
        beta: Optional[float] = None,
        annual_volatility: Optional[float] = None
    ) -> float:
        """
        Low Volatility / Defensiveness Factor (BAB): Low market risk, lower drawdowns.
        Returns score in [0, 100]. Higher = More defensive.
        """
        sub_scores = []

        if beta is not None and beta > 0:
            # Beta: 0.5 -> 90, 0.8 -> 70, 1.0 -> 55, 1.3 -> 35, 1.8 -> 10
            if beta <= 0.6:
                s = 92.0 - beta * 10.0
            elif beta <= 1.0:
                s = 85.0 - (beta - 0.6) * 75.0
            elif beta <= 1.5:
                s = 55.0 - (beta - 1.0) * 50.0
            else:
                s = max(5.0, 30.0 - (beta - 1.5) * 25.0)
            sub_scores.append(s)

        if annual_volatility is not None and annual_volatility > 0:
            # Volatility: 12% -> 90, 18% -> 60, 28% -> 30, 45% -> 10
            vol = annual_volatility
            if vol <= 0.14:
                s = 90.0 - vol * 50.0
            elif vol <= 0.22:
                s = 80.0 - (vol - 0.14) * 312.5
            elif vol <= 0.35:
                s = 55.0 - (vol - 0.22) * 230.7
            else:
                s = max(5.0, 25.0 - (vol - 0.35) * 50.0)
            sub_scores.append(s)

        if not sub_scores:
            return 50.0

        return round(FactorEngine._clamp(sum(sub_scores) / len(sub_scores), 0.0, 100.0), 1)

    @staticmethod
    def score_size(market_cap_billions: Optional[float] = None) -> Dict[str, Any]:
        """
        Size Factor: Quantifies market cap tier (Mega, Large, Mid, Small, Micro).
        Higher size score = Mega/Large cap stability.
        """
        cap = market_cap_billions if (market_cap_billions and market_cap_billions > 0) else 45.0

        if cap >= 200.0:
            tier = "Mega Cap"
            score = 92.0
            box_cat = "Large"
        elif cap >= 50.0:
            tier = "Large Cap"
            score = 78.0
            box_cat = "Large"
        elif cap >= 10.0:
            tier = "Mid Cap"
            score = 52.0
            box_cat = "Mid"
        elif cap >= 2.0:
            tier = "Small Cap"
            score = 28.0
            box_cat = "Small"
        else:
            tier = "Micro Cap"
            score = 12.0
            box_cat = "Small"

        return {
            "score": score,
            "tier": tier,
            "style_box_category": box_cat,
            "market_cap_billions": round(cap, 2)
        }

    @staticmethod
    def score_shareholder_yield(
        dividend_yield: Optional[float] = None,
        buyback_yield: Optional[float] = None
    ) -> float:
        """
        Shareholder Yield: Cash dividends + Net share buyback yield.
        Returns score in [0, 100].
        """
        div = dividend_yield or 0.0
        # If dividend yield is given in percent (e.g. 3.5), convert to decimal
        if div > 1.0:
            div /= 100.0

        bb = buyback_yield or (0.015 if div > 0 else 0.0)  # Conservative buyback estimate

        total_yield = max(0.0, div + bb)

        if total_yield >= 0.07:
            score = 90.0 + min(10.0, (total_yield - 0.07) * 100.0)
        elif total_yield >= 0.04:
            score = 65.0 + (total_yield - 0.04) * 833.3
        elif total_yield >= 0.015:
            score = 40.0 + (total_yield - 0.015) * 1000.0
        else:
            score = 10.0 + total_yield * 2000.0

        return round(FactorEngine._clamp(score, 0.0, 100.0), 1)

    @staticmethod
    def classify_style_box(value_score: float, size_category: str) -> str:
        """
        Classifies position into one of the 9 Morningstar Style Box cells:
        [Large, Mid, Small] x [Value, Blend, Growth]
        """
        if value_score >= 58.0:
            val_cat = "Value"
        elif value_score <= 42.0:
            val_cat = "Growth"
        else:
            val_cat = "Blend"

        return f"{size_category} {val_cat}"

    @staticmethod
    def analyze_asset(
        ticker: str,
        name: str = "",
        pe: Optional[float] = None,
        pb: Optional[float] = None,
        fcf_yield: Optional[float] = None,
        roe: Optional[float] = None,
        profit_margin: Optional[float] = None,
        debt_to_equity: Optional[float] = None,
        beta: Optional[float] = None,
        annual_volatility: Optional[float] = None,
        return_1y: Optional[float] = None,
        return_3m: Optional[float] = None,
        market_cap_billions: Optional[float] = None,
        dividend_yield: Optional[float] = None,
        overall_score: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Full 6-factor decomposition for a single asset.
        """
        v_score = FactorEngine.score_value(pe, pb, fcf_yield, dividend_yield)
        q_score = FactorEngine.score_quality(roe, profit_margin, debt_to_equity, overall_score)
        m_score = FactorEngine.score_momentum(return_1y, return_3m)
        lv_score = FactorEngine.score_low_volatility(beta, annual_volatility)
        size_info = FactorEngine.score_size(market_cap_billions)
        sy_score = FactorEngine.score_shareholder_yield(dividend_yield)

        style_cell = FactorEngine.classify_style_box(v_score, size_info["style_box_category"])

        factors = {
            "value": {
                "score": v_score,
                "z_score": FactorEngine._to_z_score(v_score),
                "label": "Günstige Bewertung (HML)",
                "raw": {"pe": pe, "pb": pb, "fcf_yield": fcf_yield}
            },
            "quality": {
                "score": q_score,
                "z_score": FactorEngine._to_z_score(q_score),
                "label": "Rentabilität & Bilanz (RMW)",
                "raw": {"roe": roe, "margin": profit_margin, "debt_to_equity": debt_to_equity}
            },
            "momentum": {
                "score": m_score,
                "z_score": FactorEngine._to_z_score(m_score),
                "label": "Kurstrend & Relative Stärke (WML)",
                "raw": {"return_1y": return_1y, "return_3m": return_3m}
            },
            "low_volatility": {
                "score": lv_score,
                "z_score": FactorEngine._to_z_score(lv_score),
                "label": "Defensive Stabilität (BAB)",
                "raw": {"beta": beta, "volatility": annual_volatility}
            },
            "size": {
                "score": size_info["score"],
                "z_score": FactorEngine._to_z_score(size_info["score"]),
                "label": f"Unternehmensgröße ({size_info['tier']})",
                "raw": {"market_cap_billions": size_info["market_cap_billions"], "tier": size_info["tier"]}
            },
            "shareholder_yield": {
                "score": sy_score,
                "z_score": FactorEngine._to_z_score(sy_score),
                "label": "Dividenden & Rückkäufe",
                "raw": {"dividend_yield": dividend_yield}
            }
        }

        return {
            "ticker": ticker.upper(),
            "name": name or ticker.upper(),
            "factors": factors,
            "style_box": {
                "cell": style_cell,
                "size_category": size_info["style_box_category"],
                "value_category": style_cell.split(" ")[1] if " " in style_cell else "Blend"
            }
        }

    @staticmethod
    def analyze_portfolio(holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Aggregates factor scores across all portfolio positions using market weights.
        Returns radar coordinates, Morningstar 9-grid distribution, and regime analysis.
        """
        if not holdings:
            return {
                "holdings_count": 0,
                "portfolio_factors": {},
                "benchmark_factors": {},
                "style_box_grid": {},
                "dominant_style": "Keine Daten",
                "radar_data": [],
                "insights": [],
                "regime_risks": []
            }

        total_val = sum(float(h.get("total_value", 0.0) or (float(h.get("shares", 0.0) or 0.0) * float(h.get("current_price", 0.0) or 0.0))) for h in holdings)
        if total_val <= 0:
            total_val = float(len(holdings))

        analyzed_positions = []
        weighted_factors = {
            "value": 0.0,
            "quality": 0.0,
            "momentum": 0.0,
            "low_volatility": 0.0,
            "size": 0.0,
            "shareholder_yield": 0.0
        }

        # Initialize 9-Grid Morningstar Distribution
        style_box_grid = {
            "Large Value": 0.0, "Large Blend": 0.0, "Large Growth": 0.0,
            "Mid Value": 0.0,   "Mid Blend": 0.0,   "Mid Growth": 0.0,
            "Small Value": 0.0, "Small Blend": 0.0, "Small Growth": 0.0
        }

        for h in holdings:
            val = float(h.get("total_value", 0.0) or (float(h.get("shares", 0.0) or 0.0) * float(h.get("current_price", 0.0) or 0.0)))
            if val <= 0:
                val = 1.0
            weight = val / total_val

            ticker = str(h.get("ticker", "")).upper()
            name = str(h.get("name", ticker))
            score = float(h.get("score", 50.0) or 50.0)

            # Heuristics based on ticker / asset type if specific fundamental numbers aren't passed
            pe = float(h.get("pe", 0.0) or h.get("pe_ratio", 0.0) or 0.0)
            pb = float(h.get("pb", 0.0) or h.get("pb_ratio", 0.0) or 0.0)
            beta = float(h.get("beta", 0.0) or 0.0)
            div = float(h.get("dividend_yield", 0.0) or h.get("div_yield", 0.0) or 0.0)
            mcap = float(h.get("market_cap_billions", 0.0) or 0.0)
            ret_1y = float(h.get("change_1y", 0.0) or h.get("return_1y", 0.0) or 0.0)

            # Sensible defaults for known Mega/Quality/ETF assets if missing
            if not pe or pe <= 0:
                if "etf" in str(h.get("asset_type", "")).lower() or "msci" in name.lower():
                    pe = 20.5
                    pb = 2.8
                    beta = 1.0
                    mcap = 80.0
                    ret_1y = 0.12
                elif ticker in ["AAPL", "MSFT", "GOOGL", "NVDA", "AMZN", "META"]:
                    pe = 32.0
                    pb = 8.5
                    beta = 1.25
                    mcap = 1800.0
                    ret_1y = 0.28
                elif ticker in ["ALV.DE", "MUV2.DE", "BAS.DE", "BMW.DE", "BRK.B", "JNJ", "PG"]:
                    pe = 11.5
                    pb = 1.4
                    beta = 0.78
                    mcap = 110.0
                    ret_1y = 0.08
                else:
                    pe = 22.0
                    pb = 3.0
                    beta = 1.05
                    mcap = 45.0

            asset_analysis = FactorEngine.analyze_asset(
                ticker=ticker,
                name=name,
                pe=pe,
                pb=pb,
                beta=beta if beta > 0 else 1.0,
                dividend_yield=div,
                market_cap_billions=mcap if mcap > 0 else 45.0,
                return_1y=ret_1y if ret_1y != 0 else 0.10,
                overall_score=score
            )

            asset_analysis["weight_pct"] = round(weight * 100.0, 2)
            asset_analysis["position_value"] = round(val, 2)
            analyzed_positions.append(asset_analysis)

            # Add to weighted portfolio factors
            for f_key in weighted_factors:
                weighted_factors[f_key] += weight * asset_analysis["factors"][f_key]["score"]

            # Add to 9-grid style box
            cell = asset_analysis["style_box"]["cell"]
            if cell in style_box_grid:
                style_box_grid[cell] += weight * 100.0

        # Round style box percentages
        for c in style_box_grid:
            style_box_grid[c] = round(style_box_grid[c], 1)

        # Dominant style box
        dominant_style = max(style_box_grid.items(), key=lambda x: x[1])[0]

        # Benchmark standard scores (all centered around ~50 for balanced reference)
        benchmark_factors = {
            "value": 50.0,
            "quality": 50.0,
            "momentum": 50.0,
            "low_volatility": 50.0,
            "size": 65.0,
            "shareholder_yield": 45.0
        }

        portfolio_factors = {}
        radar_data = []

        labels = {
            "value": "Value (HML)",
            "quality": "Quality (RMW)",
            "momentum": "Momentum (WML)",
            "low_volatility": "Defensiv / Low-Beta",
            "size": "Size / Mega-Cap",
            "shareholder_yield": "Shareholder Yield"
        }

        for k, score in weighted_factors.items():
            final_score = round(score, 1)
            z = FactorEngine._to_z_score(final_score)
            bench_score = benchmark_factors[k]

            portfolio_factors[k] = {
                "score": final_score,
                "z_score": z,
                "benchmark_score": bench_score,
                "delta": round(final_score - bench_score, 1),
                "label": labels[k]
            }

            radar_data.append({
                "factor": labels[k],
                "key": k,
                "portfolio": final_score,
                "benchmark": bench_score,
                "fullMark": 100
            })

        # Regime & Macro Vulnerability Diagnosis
        regime_risks = []
        insights = []

        v_z = portfolio_factors["value"]["z_score"]
        q_z = portfolio_factors["quality"]["z_score"]
        m_z = portfolio_factors["momentum"]["z_score"]
        lv_z = portfolio_factors["low_volatility"]["z_score"]
        sy_z = portfolio_factors["shareholder_yield"]["z_score"]

        # 1. Rising Interest Rates / Duration Risk
        if v_z <= -0.8 and m_z >= 0.8:
            regime_risks.append({
                "type": "warning",
                "title": "Zinswende- & Bewertungsrisiko (Duration Risk)",
                "description": f"Hohe Konzentration in teuren Wachstums- & Momentum-Aktien (Value: {v_z:+0.2f}σ, Momentum: {m_z:+0.2f}σ). Bei steigenden Renditen am Anleihemarkt droht überproportionaler Bewertungsdruck."
            })
            insights.append("Empfehlung: Selektiv Value-Titel oder Dividendenaristokraten mit hohem Free-Cash-Flow beimischen, um das Durationsrisiko zu glätten.")

        # 2. Recession & Beta Risk
        if lv_z <= -0.7:
            regime_risks.append({
                "type": "caution",
                "title": "Hohes Marktrisiko (High Beta)",
                "description": f"Das Portfolio reagiert überdurchschnittlich volatil auf Marktschocks (Defensiv-Faktor: {lv_z:+0.2f}σ). In Bärenmärkten drohen tiefere Drawdowns als im MSCI World."
            })
            insights.append("Empfehlung: Low-Volatility / defensive Konsum- und Gesundheitswerte stärken, um den maximalen Drawdown abzufedern.")

        # 3. Quality Moat Assessment
        if q_z >= 0.8:
            regime_risks.append({
                "type": "positive",
                "title": "Exzellenter Qualitäts-Burggraben",
                "description": f"Hervorragende Profitabilität und Solvenz der Depotpositionen (Quality: {q_z:+0.2f}σ). Unternehmen besitzen Preissetzungsmacht gegen Inflation."
            })
        elif q_z <= -0.5:
            regime_risks.append({
                "type": "warning",
                "title": "Verschuldungs- oder Margendruck",
                "description": f"Unterdurchschnittliche Rentabilität (Quality: {q_z:+0.2f}σ). Erhöhte Sensitivität gegenüber Konjunkturabschwächung."
            })

        # 4. Shareholder Yield
        if sy_z >= 0.8:
            insights.append(f"Starker Cash-Rückfluss: Überdurchschnittliche Ausschüttungen und Buybacks ({sy_z:+0.2f}σ) stützen die Gesamtrendite.")

        if not regime_risks:
            regime_risks.append({
                "type": "positive",
                "title": "Ausgewogenes Smart-Beta-Profil",
                "description": "Das Portfolio weist keine extremen Faktor-Fehlallokationen auf und entspricht einer institutionell balancierten Multi-Faktor-Strategie."
            })

        return {
            "holdings_count": len(holdings),
            "total_value": round(total_val, 2),
            "portfolio_factors": portfolio_factors,
            "benchmark_factors": benchmark_factors,
            "style_box_grid": style_box_grid,
            "dominant_style": dominant_style,
            "radar_data": radar_data,
            "positions": sorted(analyzed_positions, key=lambda x: x["weight_pct"], reverse=True),
            "regime_risks": regime_risks,
            "insights": insights
        }
