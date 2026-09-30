"""
Liquidity Service: Institutional Liquidity Risk, Days-to-Liquidate (DTL) Stress Test,
Almgren-Chriss Market Impact / Slippage Model, and Execution Cost Engine.
"""

from typing import Dict, Any, List, Optional
import math
import numpy as np
from src.data_fetcher import DataFetcher


class LiquidityService:
    """
    Computes institutional liquidity risk and execution slippage analytics:
    - Average Daily Volume (ADV) and Daily Turnover in EUR
    - Days-to-Liquidate (DTL) under participation rate constraints (e.g. 10% or 20% ADV)
    - Regulatory Liquidity Tiers (SEC Rule 22e-4 / UCITS standards)
    - Almgren-Chriss (2000) Square-Root Market Impact Model
    - Normal Orderly Liquidation vs. Emergency Fire-Sale Slippage
    - Algorithmic Order Execution Strategies (Single Limit, TWAP, VWAP, Dark Pool)
    - Liquidity Health Score (0-100)
    """

    DEFAULT_PARTICIPATION_RATE = 0.10  # Capping at 10% of ADV to minimize market distortion
    IMPACT_GAMMA = 0.314               # Kyle / Almgren-Chriss temporary impact coefficient

    # Known institutional baseline ADV and spreads for key tickers
    KNOWN_LIQUIDITY_BASELINES = {
        "AAPL": {"adv_shares": 52_000_000, "spread_bps": 2.5, "daily_vol_pct": 1.4},
        "MSFT": {"adv_shares": 22_000_000, "spread_bps": 2.8, "daily_vol_pct": 1.3},
        "GOOGL": {"adv_shares": 24_000_000, "spread_bps": 3.0, "daily_vol_pct": 1.6},
        "NVDA": {"adv_shares": 48_000_000, "spread_bps": 3.2, "daily_vol_pct": 2.8},
        "ASML": {"adv_shares": 1_200_000, "spread_bps": 6.5, "daily_vol_pct": 2.1},
        "SAP": {"adv_shares": 2_400_000, "spread_bps": 5.0, "daily_vol_pct": 1.4},
        "ALV": {"adv_shares": 1_100_000, "spread_bps": 6.0, "daily_vol_pct": 1.2},
        "LIN": {"adv_shares": 1_800_000, "spread_bps": 5.5, "daily_vol_pct": 1.3},
        "TSLA": {"adv_shares": 68_000_000, "spread_bps": 3.5, "daily_vol_pct": 3.2},
        "JNJ": {"adv_shares": 7_500_000, "spread_bps": 3.0, "daily_vol_pct": 0.9},
        "RHM": {"adv_shares": 380_000, "spread_bps": 12.0, "daily_vol_pct": 2.4},
        "BTI": {"adv_shares": 3_500_000, "spread_bps": 7.5, "daily_vol_pct": 1.1},
    }

    @classmethod
    def get_stock_liquidity_profile(
        cls,
        ticker: str,
        current_price: float = 100.0
    ) -> Dict[str, Any]:
        """Fetches or models institutional trading volume, bid-ask spread, and daily volatility."""
        t = ticker.strip().upper()
        if t in cls.KNOWN_LIQUIDITY_BASELINES:
            base = cls.KNOWN_LIQUIDITY_BASELINES[t]
            adv = base["adv_shares"]
            spread_pct = base["spread_bps"] / 100.0  # e.g. 5 bps = 0.05%
            daily_vol = base["daily_vol_pct"] / 100.0
            turnover = adv * current_price
            return {
                "ticker": t,
                "adv_shares": adv,
                "daily_turnover_eur": turnover,
                "bid_ask_spread_pct": round(spread_pct, 4),
                "daily_volatility": daily_vol
            }

        # Dynamic lookup from DataFetcher
        adv = 1_500_000
        daily_vol = 0.016
        spread_pct = 0.0012  # 12 bps default
        try:
            fetcher = DataFetcher(t)
            info = fetcher.get_info() or {}
            fetched_vol = info.get("volume") or info.get("averageVolume") or info.get("averageVolume10days")
            if fetched_vol and float(fetched_vol) > 10_000:
                adv = float(fetched_vol)
            # Rough estimate of spread based on market cap: larger cap -> tighter spread
            mcap = float(info.get("marketCap") or 5_000_000_000)
            if mcap > 100_000_000_000:
                spread_pct = 0.0003  # 3 bps
            elif mcap > 10_000_000_000:
                spread_pct = 0.0008  # 8 bps
            elif mcap > 2_000_000_000:
                spread_pct = 0.0020  # 20 bps
            else:
                spread_pct = 0.0060  # 60 bps for smallcaps
        except Exception:
            pass

        turnover = adv * current_price
        return {
            "ticker": t,
            "adv_shares": int(adv),
            "daily_turnover_eur": turnover,
            "bid_ask_spread_pct": round(spread_pct, 4),
            "daily_volatility": daily_vol
        }

    @classmethod
    def calculate_almgren_chriss_slippage(
        cls,
        order_shares: float,
        adv_shares: float,
        daily_vol: float,
        spread_pct: float,
        execution_days: float = 1.0
    ) -> Dict[str, float]:
        """
        Computes Almgren-Chriss (2000) market impact & execution cost.
        Total Cost % = Half Spread % + Gamma * Vol_daily * sqrt( Order_shares / (ADV * Days) )
        """
        half_spread = spread_pct / 2.0
        if adv_shares <= 0 or order_shares <= 0:
            return {
                "spread_cost_pct": round(half_spread * 100.0, 3),
                "market_impact_pct": 0.0,
                "total_slippage_pct": round(half_spread * 100.0, 3)
            }

        effective_adv = adv_shares * max(1.0, execution_days)
        participation = order_shares / effective_adv

        # Square-root law of market impact
        market_impact = cls.IMPACT_GAMMA * daily_vol * math.sqrt(participation)

        total_cost = half_spread + market_impact
        return {
            "spread_cost_pct": round(half_spread * 100.0, 3),
            "market_impact_pct": round(market_impact * 100.0, 3),
            "total_slippage_pct": round(total_cost * 100.0, 3)
        }

    @classmethod
    def analyze_portfolio_liquidity(
        cls,
        holdings: List[Dict[str, Any]],
        participation_rate: float = DEFAULT_PARTICIPATION_RATE
    ) -> Dict[str, Any]:
        """
        Calculates complete portfolio liquidity stress test, Days-to-Liquidate,
        tier segregation, and execution cost estimates.
        """
        if not holdings:
            return {
                "valid": False,
                "error": "Mindestens 1 Position für Liquiditätsanalyse erforderlich."
            }

        p_rate = max(0.01, min(0.50, participation_rate))
        holdings_results = []
        total_portfolio_value = 0.0

        for h in holdings:
            t = str(h.get("ticker", "")).strip().upper()
            shares = float(h.get("shares") or 0.0)
            price = float(h.get("current_price") or h.get("buyPrice") or 100.0)
            val = shares * price
            total_portfolio_value += val

            # Get liquidity metrics
            liq_prof = cls.get_stock_liquidity_profile(t, price)
            adv = liq_prof["adv_shares"]
            spread_pct = liq_prof["bid_ask_spread_pct"]
            daily_vol = liq_prof["daily_volatility"]

            # Days to Liquidate at capped participation rate
            max_daily_shares = adv * p_rate
            dtl = shares / max_daily_shares if max_daily_shares > 0 else 1.0
            dtl_rounded = max(0.05, round(dtl, 2))

            # Tier classification (SEC Rule 22e-4)
            if dtl_rounded <= 1.0:
                tier = 1
                tier_label = "Tier 1: Hochliquide (≤ 1 Tag)"
            elif dtl_rounded <= 5.0:
                tier = 2
                tier_label = "Tier 2: Liquide (2–5 Tage)"
            elif dtl_rounded <= 15.0:
                tier = 3
                tier_label = "Tier 3: Moderat (6–15 Tage)"
            else:
                tier = 4
                tier_label = "Tier 4: Illiquide (> 15 Tage)"

            # Normal Execution Slippage (spread across DTL days)
            normal_impact = cls.calculate_almgren_chriss_slippage(
                order_shares=shares,
                adv_shares=adv,
                daily_vol=daily_vol,
                spread_pct=spread_pct,
                execution_days=max(1.0, math.ceil(dtl))
            )

            # Fire-Sale Slippage (immediate 1-day forced market liquidation)
            fire_sale_impact = cls.calculate_almgren_chriss_slippage(
                order_shares=shares,
                adv_shares=adv,
                daily_vol=daily_vol,
                spread_pct=spread_pct,
                execution_days=1.0
            )

            # Execution Strategy recommendation
            participation_direct = shares / adv if adv > 0 else 0.0
            if participation_direct < 0.005:
                strategy = "Single Limit Order"
                strategy_desc = "Ordergröße verschwindend gering vs. ADV; sofortige Ausführung ohne spürbaren Impact."
            elif participation_direct < 0.05:
                strategy = "Intraday VWAP"
                strategy_desc = "Order über den Handelstag volumengewichtet staffeln, um Spreadkosten zu minimieren."
            elif dtl <= 3.0:
                strategy = "Multi-Day TWAP"
                strategy_desc = "Zeitgewichtete Ausführung über mehrere Handelstage zur Vermeidung von Preisdruck."
            else:
                strategy = "Algorithmic Dark Pool / Block Trade"
                strategy_desc = "Block-Trading via Dark Pools oder Broker-Crossing-Network dringend empfohlen."

            holdings_results.append({
                "ticker": t,
                "name": h.get("name") or t,
                "shares": shares,
                "price": price,
                "value_eur": val,
                "adv_shares": adv,
                "daily_turnover_eur": liq_prof["daily_turnover_eur"],
                "spread_pct": round(spread_pct * 100.0, 3),
                "days_to_liquidate": dtl_rounded,
                "tier": tier,
                "tier_label": tier_label,
                "normal_slippage_pct": normal_impact["total_slippage_pct"],
                "normal_slippage_eur": round(val * (normal_impact["total_slippage_pct"] / 100.0), 2),
                "fire_sale_slippage_pct": fire_sale_impact["total_slippage_pct"],
                "fire_sale_slippage_eur": round(val * (fire_sale_impact["total_slippage_pct"] / 100.0), 2),
                "recommended_strategy": strategy,
                "strategy_description": strategy_desc
            })

        # Portfolio Aggregations
        for row in holdings_results:
            row["weight_pct"] = round((row["value_eur"] / total_portfolio_value * 100.0), 1) if total_portfolio_value > 0 else 0.0

        # Tier breakdown
        tier_weights = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
        for row in holdings_results:
            tier_weights[row["tier"]] += row["weight_pct"]

        # Weighted Days-to-Liquidate
        weighted_dtl = sum((r["weight_pct"] / 100.0) * r["days_to_liquidate"] for r in holdings_results)
        max_dtl = max(r["days_to_liquidate"] for r in holdings_results)

        # Weighted Normal and Fire-Sale Slippage
        weighted_normal_slippage_pct = sum((r["weight_pct"] / 100.0) * r["normal_slippage_pct"] for r in holdings_results)
        total_normal_slippage_eur = sum(r["normal_slippage_eur"] for r in holdings_results)

        weighted_fire_sale_slippage_pct = sum((r["weight_pct"] / 100.0) * r["fire_sale_slippage_pct"] for r in holdings_results)
        total_fire_sale_slippage_eur = sum(r["fire_sale_slippage_eur"] for r in holdings_results)

        # Liquidity Health Score (0-100)
        # Penalizes high DTL, wide spreads, and low Tier 1 share
        base_score = tier_weights[1] * 0.70 + tier_weights[2] * 0.40 + tier_weights[3] * 0.15
        dtl_penalty = min(35.0, weighted_dtl * 5.0)
        slippage_penalty = min(35.0, weighted_fire_sale_slippage_pct * 15.0)
        liquidity_score = max(10.0, min(100.0, base_score + 30.0 - dtl_penalty - slippage_penalty))

        score_badge = (
            {"label": "Exzellent", "tone": "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30"}
            if liquidity_score >= 80
            else {"label": "Solide", "tone": "bg-teal-500/15 text-teal-700 dark:text-teal-400 border-teal-500/30"}
            if liquidity_score >= 60
            else {"label": "Erhöhtes Risiko", "tone": "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30"}
            if liquidity_score >= 40
            else {"label": "Illiquiditäts-Gefahr", "tone": "bg-rose-500/15 text-rose-700 dark:text-rose-400 border-rose-500/30"}
        )

        holdings_results.sort(key=lambda x: x["days_to_liquidate"], reverse=True)

        return {
            "valid": True,
            "participation_rate_pct": round(p_rate * 100.0, 1),
            "portfolio_value_eur": round(total_portfolio_value, 2),
            "liquidity_health_score": round(liquidity_score, 1),
            "liquidity_badge": score_badge,
            "portfolio_days_to_liquidate": round(weighted_dtl, 2),
            "max_position_dtl": round(max_dtl, 2),
            "tier_distribution": {
                "tier_1_pct": round(tier_weights[1], 1),
                "tier_2_pct": round(tier_weights[2], 1),
                "tier_3_pct": round(tier_weights[3], 1),
                "tier_4_pct": round(tier_weights[4], 1),
            },
            "execution_costs": {
                "normal_slippage_pct": round(weighted_normal_slippage_pct, 3),
                "normal_slippage_eur": round(total_normal_slippage_eur, 2),
                "fire_sale_slippage_pct": round(weighted_fire_sale_slippage_pct, 3),
                "fire_sale_slippage_eur": round(total_fire_sale_slippage_eur, 2),
                "panic_cost_delta_eur": round(total_fire_sale_slippage_eur - total_normal_slippage_eur, 2)
            },
            "holdings": holdings_results
        }

    @classmethod
    def simulate_order_impact(
        cls,
        ticker: str,
        order_value_eur: float,
        current_price: float = 100.0
    ) -> Dict[str, Any]:
        """Simulates custom order size impact on bid-ask and price for single asset."""
        prof = cls.get_stock_liquidity_profile(ticker, current_price)
        shares = order_value_eur / current_price if current_price > 0 else 0.0
        adv = prof["adv_shares"]
        spread_pct = prof["bid_ask_spread_pct"]
        daily_vol = prof["daily_volatility"]

        impact = cls.calculate_almgren_chriss_slippage(
            order_shares=shares,
            adv_shares=adv,
            daily_vol=daily_vol,
            spread_pct=spread_pct,
            execution_days=1.0
        )
        slippage_eur = order_value_eur * (impact["total_slippage_pct"] / 100.0)

        return {
            "ticker": ticker.upper(),
            "order_value_eur": round(order_value_eur, 2),
            "order_shares": round(shares, 2),
            "adv_shares": adv,
            "order_pct_of_adv": round((shares / adv * 100.0) if adv > 0 else 0.0, 3),
            "spread_cost_pct": impact["spread_cost_pct"],
            "market_impact_pct": impact["market_impact_pct"],
            "total_slippage_pct": impact["total_slippage_pct"],
            "total_slippage_eur": round(slippage_eur, 2)
        }
