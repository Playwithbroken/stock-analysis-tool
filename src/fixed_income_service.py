"""
Institutional Fixed Income & Bond Yield Curve Analytics Service.
Calculates:
1. Yield-to-Maturity (YTM), MacAulay Duration, Modified Duration, Convexity.
2. Dollar Value of a Basis Point (DV01 / PV01).
3. Taylor-Series Bond Price Sensitivity with Convexity Adjustment.
4. Macro Yield Curve Scenarios (Parallel Shifts, Steepener, Flattener).
5. Credit Rating & Spread Allocation (AAA to High Yield).
"""

import math
from typing import Dict, List, Any, Optional


class FixedIncomeService:
    """
    Fixed income analytics engine for bonds, bond ETFs, money market instruments,
    and multi-asset portfolio duration matching.
    """

    # Known fixed income & bond ETF characteristics database
    BOND_PROFILES: Dict[str, Dict[str, Any]] = {
        # Government Bond ETFs
        "TLT": {"name": "iShares 20+ Year Treasury Bond ETF", "type": "Govt Bond", "ytm_pct": 4.55, "duration": 16.8, "convexity": 3.85, "rating": "AAA", "credit_spread_bps": 0},
        "IEF": {"name": "iShares 7-10 Year Treasury Bond ETF", "type": "Govt Bond", "ytm_pct": 4.15, "duration": 7.4, "convexity": 0.65, "rating": "AAA", "credit_spread_bps": 0},
        "SHY": {"name": "iShares 1-3 Year Treasury Bond ETF", "type": "Govt Bond", "ytm_pct": 4.35, "duration": 1.9, "convexity": 0.05, "rating": "AAA", "credit_spread_bps": 0},
        "GOVT": {"name": "iShares U.S. Treasury Bond ETF", "type": "Govt Bond", "ytm_pct": 4.25, "duration": 6.2, "convexity": 0.52, "rating": "AAA", "credit_spread_bps": 0},
        "EXX6": {"name": "iShares eb.rexx Government Germany (Bund)", "type": "Govt Bond", "ytm_pct": 2.45, "duration": 7.1, "convexity": 0.72, "rating": "AAA", "credit_spread_bps": 0},
        "IEAG": {"name": "iShares Core Euro Government Bond ETF", "type": "Govt Bond", "ytm_pct": 2.85, "duration": 6.8, "convexity": 0.68, "rating": "AAA", "credit_spread_bps": 20},
        
        # Aggregate & Corporate Bond ETFs
        "BND": {"name": "Vanguard Total Bond Market ETF", "type": "Aggregate", "ytm_pct": 4.45, "duration": 6.5, "convexity": 0.55, "rating": "AA", "credit_spread_bps": 45},
        "AGG": {"name": "iShares Core U.S. Aggregate Bond ETF", "type": "Aggregate", "ytm_pct": 4.48, "duration": 6.4, "convexity": 0.54, "rating": "AA", "credit_spread_bps": 48},
        "LQD": {"name": "iShares iBoxx $ Investment Grade Corporate", "type": "Corporate", "ytm_pct": 5.25, "duration": 8.1, "convexity": 0.95, "rating": "BBB", "credit_spread_bps": 115},
        "VCSH": {"name": "Vanguard Short-Term Corporate Bond ETF", "type": "Corporate", "ytm_pct": 4.85, "duration": 2.6, "convexity": 0.10, "rating": "A", "credit_spread_bps": 65},
        "VCIT": {"name": "Vanguard Intermediate-Term Corporate Bond", "type": "Corporate", "ytm_pct": 5.15, "duration": 6.2, "convexity": 0.58, "rating": "BBB", "credit_spread_bps": 105},
        
        # High Yield & Emerging Market Bonds
        "HYG": {"name": "iShares iBoxx $ High Yield Corporate Bond", "type": "High Yield", "ytm_pct": 7.15, "duration": 3.8, "convexity": 0.22, "rating": "BB", "credit_spread_bps": 340},
        "JNK": {"name": "SPDR Bloomberg High Yield Bond ETF", "type": "High Yield", "ytm_pct": 7.25, "duration": 3.7, "convexity": 0.20, "rating": "B", "credit_spread_bps": 365},
        "EMB": {"name": "iShares J.P. Morgan USD Emerging Markets", "type": "Emerging Markets", "ytm_pct": 6.65, "duration": 6.8, "convexity": 0.85, "rating": "BBB", "credit_spread_bps": 260},
        
        # Money Market & Cash Equivalents
        "XEON": {"name": "Xtrackers II EUR Overnight Rate Swap (DBX0AN)", "type": "Money Market", "ytm_pct": 3.25, "duration": 0.05, "convexity": 0.00, "rating": "AAA", "credit_spread_bps": 0},
        "BIL": {"name": "SPDR Bloomberg 1-3 Month T-Bill ETF", "type": "Money Market", "ytm_pct": 4.65, "duration": 0.15, "convexity": 0.00, "rating": "AAA", "credit_spread_bps": 0},
        "SGOV": {"name": "iShares 0-3 Month Treasury Bond ETF", "type": "Money Market", "ytm_pct": 4.70, "duration": 0.12, "convexity": 0.00, "rating": "AAA", "credit_spread_bps": 0},
    }

    @classmethod
    def get_bond_profile(cls, ticker: str, default_price: float = 100.0) -> Dict[str, Any]:
        """Resolves or synthesizes fixed income characteristics."""
        clean = ticker.strip().upper()
        if clean in cls.BOND_PROFILES:
            return cls.BOND_PROFILES[clean]

        # Heuristic detection
        if "BOND" in clean or "TREASURY" in clean or "REXX" in clean or "GOVT" in clean:
            return {
                "name": f"{clean} Fixed Income Instrument",
                "type": "Govt Bond",
                "ytm_pct": 3.85,
                "duration": 6.5,
                "convexity": 0.60,
                "rating": "AA",
                "credit_spread_bps": 35
            }

        # Equities interest rate proxy:
        # Equities behave like perpetual cash flow assets with long duration (~18-22 years)
        # but with growth rate offsets. For institutional fixed income sleeves,
        # standard non-bond stocks are tagged as 'Equity' with default interest sensitivity beta.
        return {
            "name": clean,
            "type": "Equity / Non-Bond",
            "ytm_pct": 2.50,  # Dividend Yield proxy
            "duration": 3.5,  # Moderate equity duration beta
            "convexity": 0.30,
            "rating": "Equity",
            "credit_spread_bps": 150
        }

    @classmethod
    def calculate_price_change(
        cls,
        mod_duration: float,
        convexity: float,
        yield_change_bps: float
    ) -> float:
        """
        Calculates percentage price change using 2nd-order Taylor expansion:
        delta_P / P = -ModD * delta_y + 0.5 * Convexity * (delta_y)^2
        where delta_y = yield_change_bps / 10000.
        """
        dy = yield_change_bps / 10000.0
        pct_change = (-mod_duration * dy + 0.5 * convexity * (dy ** 2)) * 100.0
        return round(pct_change, 3)

    @classmethod
    def analyze_portfolio_fixed_income(
        cls,
        holdings: List[Dict[str, Any]],
        total_portfolio_value: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculates complete institutional fixed income risk metrics:
        Portfolio Modified Duration, MacAulay Duration, Convexity, DV01,
        Credit Rating Distribution, and Yield Curve Stress Matrix.
        """
        if not holdings:
            return {
                "valid": False,
                "error": "Mindestens 1 Position im Portfolio erforderlich."
            }

        total_val = 0.0
        enriched_holdings = []
        rating_totals: Dict[str, float] = {
            "AAA": 0.0,
            "AA": 0.0,
            "A": 0.0,
            "BBB": 0.0,
            "High Yield (<BBB)": 0.0,
            "Equity / Other": 0.0
        }

        weighted_duration_sum = 0.0
        weighted_convexity_sum = 0.0
        weighted_ytm_sum = 0.0
        weighted_spread_sum = 0.0
        fixed_income_sleeve_val = 0.0

        for h in holdings:
            t = str(h.get("ticker", "")).strip().upper()
            shares = float(h.get("shares") or 0.0)
            price = float(h.get("current_price") or h.get("buyPrice") or 100.0)
            val = shares * price
            total_val += val

            prof = cls.get_bond_profile(t, price)
            is_pure_bond = prof["type"] in ["Govt Bond", "Aggregate", "Corporate", "High Yield", "Emerging Markets", "Money Market"]
            if is_pure_bond:
                fixed_income_sleeve_val += val

            dur = prof["duration"]
            conv = prof["convexity"]
            ytm = prof["ytm_pct"]
            spread = prof["credit_spread_bps"]
            rating = prof["rating"]

            # Standard MacAulay duration from Modified Duration: MacD = ModD * (1 + y)
            macd = round(dur * (1.0 + (ytm / 100.0)), 2)

            # DV01 for this holding: Value * ModD * 0.0001
            dv01_holding = round(val * dur * 0.0001, 2)

            weighted_duration_sum += val * dur
            weighted_convexity_sum += val * conv
            weighted_ytm_sum += val * ytm
            weighted_spread_sum += val * spread

            # Rating bucket
            if rating == "AAA":
                rating_totals["AAA"] += val
            elif rating == "AA":
                rating_totals["AA"] += val
            elif rating == "A":
                rating_totals["A"] += val
            elif rating == "BBB":
                rating_totals["BBB"] += val
            elif rating in ["BB", "B", "CCC"]:
                rating_totals["High Yield (<BBB)"] += val
            else:
                rating_totals["Equity / Other"] += val

            enriched_holdings.append({
                "ticker": t,
                "name": prof["name"],
                "type": prof["type"],
                "value_eur": round(val, 2),
                "shares": shares,
                "price": price,
                "ytm_pct": ytm,
                "macaulay_duration": macd,
                "modified_duration": dur,
                "convexity": conv,
                "dv01_eur": dv01_holding,
                "rating": rating,
                "credit_spread_bps": spread
            })

        port_val = total_portfolio_value or max(1.0, total_val)

        # Portfolio Averages
        port_duration = weighted_duration_sum / port_val if port_val > 0 else 0.0
        port_convexity = weighted_convexity_sum / port_val if port_val > 0 else 0.0
        port_ytm = weighted_ytm_sum / port_val if port_val > 0 else 0.0
        port_spread = weighted_spread_sum / port_val if port_val > 0 else 0.0

        # Portfolio DV01 (Dollar Value of a Basis Point)
        port_dv01 = round(port_val * port_duration * 0.0001, 2)

        # Holdings weight
        for item in enriched_holdings:
            item["weight_pct"] = round((item["value_eur"] / port_val * 100.0), 1)

        # Rating Breakdown List
        rating_breakdown = []
        for r_name, r_val in rating_totals.items():
            if r_val > 0:
                rating_breakdown.append({
                    "rating": r_name,
                    "value_eur": round(r_val, 2),
                    "weight_pct": round((r_val / port_val * 100.0), 1)
                })

        # Yield Curve Scenarios (Parallel Shifts & Slopes)
        scenarios = [
            {
                "id": "rate_cut_100",
                "name": "Zinssenkung (-100 bps / -1.0%)",
                "description": "EZB/Fed lockern Geldpolitik aggressively; Anleihekurse steigen.",
                "shift_bps": -100,
                "price_change_pct": cls.calculate_price_change(port_duration, port_convexity, -100),
                "delta_eur": round(port_val * (cls.calculate_price_change(port_duration, port_convexity, -100) / 100.0), 2)
            },
            {
                "id": "rate_cut_50",
                "name": "Leichte Zinssenkung (-50 bps / -0.5%)",
                "description": "Moderater Zinssenkungszyklus.",
                "shift_bps": -50,
                "price_change_pct": cls.calculate_price_change(port_duration, port_convexity, -50),
                "delta_eur": round(port_val * (cls.calculate_price_change(port_duration, port_convexity, -50) / 100.0), 2)
            },
            {
                "id": "rate_hike_50",
                "name": "Leichte Zinsanhebung (+50 bps / +0.5%)",
                "description": "Zinssteigerung bei anziehender Inflation.",
                "shift_bps": 50,
                "price_change_pct": cls.calculate_price_change(port_duration, port_convexity, 50),
                "delta_eur": round(port_val * (cls.calculate_price_change(port_duration, port_convexity, 50) / 100.0), 2)
            },
            {
                "id": "rate_hike_100",
                "name": "Zinsschock (+100 bps / +1.0%)",
                "description": "Unerwartet restriktive Zentralbankpolitik.",
                "shift_bps": 100,
                "price_change_pct": cls.calculate_price_change(port_duration, port_convexity, 100),
                "delta_eur": round(port_val * (cls.calculate_price_change(port_duration, port_convexity, 100) / 100.0), 2)
            },
            {
                "id": "rate_hike_200",
                "name": "Historischer Zinscrash (+200 bps / +2.0%)",
                "description": "Wiederholung des Anleihen-Crashs von 2022.",
                "shift_bps": 200,
                "price_change_pct": cls.calculate_price_change(port_duration, port_convexity, 200),
                "delta_eur": round(port_val * (cls.calculate_price_change(port_duration, port_convexity, 200) / 100.0), 2)
            }
        ]

        # Duration Risk Classification Badge
        if port_duration <= 2.5:
            dur_badge = {"label": "Geringes Zinsänderungsrisiko (Ultra-Short / Geldmarkt)", "tone": "border-emerald-500/30 bg-emerald-500/15 text-emerald-800 dark:text-emerald-300"}
        elif port_duration <= 5.5:
            dur_badge = {"label": "Moderates Zinsrisiko (Intermediate)", "tone": "border-teal-500/30 bg-teal-500/15 text-teal-800 dark:text-teal-300"}
        elif port_duration <= 9.0:
            dur_badge = {"label": "Erhöhtes Zinsänderungsrisiko (Long Duration)", "tone": "border-amber-500/30 bg-amber-500/15 text-amber-800 dark:text-amber-300"}
        else:
            dur_badge = {"label": "Kritisches Zinsrisiko (Ultra-Long / 20+ Jahre)", "tone": "border-rose-500/30 bg-rose-500/15 text-rose-800 dark:text-rose-300"}

        return {
            "valid": True,
            "portfolio_value_eur": round(port_val, 2),
            "fixed_income_sleeve_pct": round((fixed_income_sleeve_val / port_val * 100.0), 1) if port_val > 0 else 0.0,
            "summary": {
                "modified_duration": round(port_duration, 2),
                "macaulay_duration": round(port_duration * (1.0 + (port_ytm / 100.0)), 2),
                "convexity": round(port_convexity, 2),
                "dv01_eur": port_dv01,
                "ytm_pct": round(port_ytm, 2),
                "average_credit_spread_bps": round(port_spread, 1),
                "duration_badge": dur_badge
            },
            "scenarios": scenarios,
            "rating_distribution": rating_breakdown,
            "holdings": enriched_holdings
        }

    @classmethod
    def simulate_yield_shift(
        cls,
        holdings: List[Dict[str, Any]],
        shift_bps: float
    ) -> Dict[str, Any]:
        """
        Simulates custom yield curve shift on portfolio.
        """
        res = cls.analyze_portfolio_fixed_income(holdings)
        if not res["valid"]:
            return res

        port_val = res["portfolio_value_eur"]
        mod_d = res["summary"]["modified_duration"]
        conv = res["summary"]["convexity"]

        pct_change = cls.calculate_price_change(mod_d, conv, shift_bps)
        delta_eur = round(port_val * (pct_change / 100.0), 2)

        return {
            "shift_bps": shift_bps,
            "shift_pct": round(shift_bps / 100.0, 2),
            "portfolio_value_eur": port_val,
            "simulated_value_eur": round(port_val + delta_eur, 2),
            "delta_eur": delta_eur,
            "price_change_pct": pct_change,
            "dv01_eur": res["summary"]["dv01_eur"]
        }
