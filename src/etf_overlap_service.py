"""
ETF Overlap & Fee Drag (Gebuehren-Vampir) Detector Service
Analyzes true look-through holding concentration, pairwise ETF overlap,
and compound fee drag simulations over 10, 20, and 30 years.
"""

from typing import Dict, Any, List, Optional
import math

# Curated canonical ETF & Index profiles with verified top holdings and TERs
KNOWN_ETF_PROFILES: Dict[str, Dict[str, Any]] = {
    # 1. MSCI World Core
    "URTH": {
        "name": "iShares MSCI World ETF",
        "index": "MSCI World Index",
        "ter": 0.0020,  # 0.20%
        "is_etf": True,
        "holdings": {
            "AAPL": 4.8, "MSFT": 4.4, "NVDA": 4.2, "AMZN": 2.6,
            "META": 1.7, "GOOGL": 1.4, "GOOG": 1.2, "AVGO": 1.1,
            "TSLA": 1.0, "LLY": 0.9, "JPM": 0.9, "UNH": 0.8,
            "XOM": 0.7, "V": 0.7, "MA": 0.6, "COST": 0.6
        }
    },
    # 2. S&P 500 Core
    "SPY": {
        "name": "SPDR S&P 500 ETF Trust",
        "index": "S&P 500 Index",
        "ter": 0.0007,  # 0.07%
        "is_etf": True,
        "holdings": {
            "AAPL": 7.1, "MSFT": 6.6, "NVDA": 6.3, "AMZN": 3.8,
            "META": 2.5, "GOOGL": 2.1, "GOOG": 1.8, "BRK-B": 1.7,
            "AVGO": 1.6, "TSLA": 1.5, "JPM": 1.3, "LLY": 1.3,
            "UNH": 1.2, "V": 1.0, "XOM": 1.0, "MA": 0.9
        }
    },
    # 3. Nasdaq 100
    "QQQ": {
        "name": "Invesco QQQ Trust (Nasdaq 100)",
        "index": "Nasdaq 100 Index",
        "ter": 0.0020,  # 0.20%
        "is_etf": True,
        "holdings": {
            "AAPL": 8.9, "MSFT": 8.2, "NVDA": 7.8, "AMZN": 5.2,
            "META": 4.6, "AVGO": 4.4, "GOOGL": 2.7, "TSLA": 2.6,
            "GOOG": 2.5, "COST": 2.4, "NFLX": 2.1, "AMD": 1.9,
            "ADBE": 1.8, "PEP": 1.6, "LIN": 1.5, "TMUS": 1.4
        }
    },
    # 4. FTSE All-World
    "VWCE.DE": {
        "name": "Vanguard FTSE All-World UCITS ETF",
        "index": "FTSE All-World Index",
        "ter": 0.0022,  # 0.22%
        "is_etf": True,
        "holdings": {
            "AAPL": 4.2, "MSFT": 3.9, "NVDA": 3.7, "AMZN": 2.3,
            "META": 1.5, "GOOGL": 1.2, "TSM": 1.2, "GOOG": 1.1,
            "AVGO": 1.0, "TSLA": 0.9, "LLY": 0.8, "JPM": 0.8,
            "TENCENT": 0.6, "BABA": 0.4, "ASML": 0.5, "NOVARTIS": 0.4
        }
    },
    # 5. DAX 40 Core
    "EXS1.DE": {
        "name": "iShares Core DAX UCITS ETF",
        "index": "DAX 40 Index",
        "ter": 0.0016,  # 0.16%
        "is_etf": True,
        "holdings": {
            "SAP": 15.0, "SIE": 10.5, "ALV": 8.4, "AIR": 7.2,
            "DTE": 6.8, "MBG": 4.5, "BMW": 3.8, "BAS": 3.5,
            "MUV2": 3.4, "DHL": 3.1, "IFX": 3.0, "VOW3": 2.8,
            "SHL": 2.6, "BAYN": 2.5, "HEN3": 2.2, "DBK": 2.1
        }
    },
    # 6. MSCI Emerging Markets
    "EEM": {
        "name": "iShares MSCI Emerging Markets ETF",
        "index": "MSCI Emerging Markets Index",
        "ter": 0.0018,  # 0.18%
        "is_etf": True,
        "holdings": {
            "TSM": 8.8, "TENCENT": 4.2, "SAMSUNG": 3.8, "BABA": 2.4,
            "RELIANCE": 1.6, "MEITUAN": 1.3, "SK_HYNIX": 1.1,
            "INFOSYS": 1.0, "ICICI": 0.9, "PDD": 0.9
        }
    },
    # 7. Technology Sector ETF
    "XLK": {
        "name": "Technology Select Sector SPDR",
        "index": "S&P Technology Select",
        "ter": 0.0010,  # 0.10%
        "is_etf": True,
        "holdings": {
            "MSFT": 19.5, "AAPL": 15.8, "NVDA": 14.2, "AVGO": 5.4,
            "CRM": 3.2, "AMD": 3.0, "QCOM": 2.8, "ACN": 2.6,
            "CSCO": 2.4, "INTC": 2.0, "INTU": 2.0, "TXN": 1.8
        }
    },
    # 8. Semiconductor ETF
    "SMH": {
        "name": "VanEck Semiconductor ETF",
        "index": "MVIS US Listed Semiconductor 25",
        "ter": 0.0035,  # 0.35%
        "is_etf": True,
        "holdings": {
            "NVDA": 20.5, "TSM": 12.8, "AVGO": 7.5, "ASML": 6.2,
            "QCOM": 4.8, "TXN": 4.5, "AMD": 4.3, "AMAT": 4.1,
            "MU": 3.8, "LRCX": 3.5, "ADI": 3.2, "INTC": 3.0
        }
    },
    # 9. ARK Innovation (Teurer Themen-ETF)
    "ARKK": {
        "name": "ARK Innovation ETF",
        "index": "Disruptive Innovation",
        "ter": 0.0075,  # 0.75%
        "is_etf": True,
        "holdings": {
            "TSLA": 12.4, "ROKU": 8.2, "COIN": 8.8, "PLTR": 5.8,
            "SHOP": 6.5, "CRSP": 5.1, "HOOD": 4.9, "PATH": 4.5,
            "EXAS": 4.2, "SQ": 3.8
        }
    }
}

# Aliases mapping European & global tickers to canonical profiles
TICKER_ALIASES: Dict[str, str] = {
    # Core MSCI World
    "EUNL.DE": "URTH", "IWDA.AS": "URTH", "SWRD.L": "URTH", "XDWD.DE": "URTH",
    # S&P 500
    "VOO": "SPY", "IVV": "SPY", "SXR8.DE": "SPY", "VUSA.DE": "SPY", "VUAA.DE": "SPY",
    # Nasdaq 100
    "EQAC.DE": "QQQ", "UST.PA": "QQQ", "CNDX.L": "QQQ", "SXRV.DE": "QQQ",
    # All-World
    "VT": "VWCE.DE", "VGWL.DE": "VWCE.DE", "SSAC.L": "VWCE.DE",
    # DAX
    "DAXEX.DE": "EXS1.DE", "^GDAXI": "EXS1.DE",
    # Emerging Markets
    "IS3N.DE": "EEM", "VWO": "EEM",
    # Tech
    "QDVE.DE": "XLK",
    # Semis
    "VVSM.DE": "SMH",
}


class ETFOverlapService:
    """Calculates ETF overlap, look-through portfolio concentration, and fee drag."""

    @staticmethod
    def resolve_profile(ticker: str) -> Dict[str, Any]:
        """Resolves ticker to an ETF profile, or treats as single stock."""
        t = ticker.upper().strip()
        canonical = TICKER_ALIASES.get(t, t)

        if canonical in KNOWN_ETF_PROFILES:
            profile = dict(KNOWN_ETF_PROFILES[canonical])
            profile["ticker"] = t
            return profile

        # Default treatment as single equity
        return {
            "ticker": t,
            "name": t,
            "index": "Einzeltitel",
            "ter": 0.0,
            "is_etf": False,
            "holdings": {t: 100.0}
        }

    @staticmethod
    def calculate_pairwise_overlap(ticker_a: str, ticker_b: str) -> Dict[str, Any]:
        """Calculates overlap percentage and shared holdings between two tickers."""
        prof_a = ETFOverlapService.resolve_profile(ticker_a)
        prof_b = ETFOverlapService.resolve_profile(ticker_b)

        holdings_a = prof_a.get("holdings", {})
        holdings_b = prof_b.get("holdings", {})

        shared_keys = set(holdings_a.keys()).intersection(set(holdings_b.keys()))
        overlap_pct = 0.0
        shared_details = []

        for k in shared_keys:
            w_a = holdings_a[k]
            w_b = holdings_b[k]
            min_w = min(w_a, w_b)
            overlap_pct += min_w
            shared_details.append({
                "ticker": k,
                "weight_in_a": w_a,
                "weight_in_b": w_b,
                "overlap_contribution": round(min_w, 2),
            })

        shared_details.sort(key=lambda x: x["overlap_contribution"], reverse=True)

        sum_a = sum(holdings_a.values()) or 1.0
        sum_b = sum(holdings_b.values()) or 1.0

        if ticker_a.strip().upper() == ticker_b.strip().upper() or prof_a.get("name") == prof_b.get("name"):
            final_overlap = 100.0
        else:
            final_overlap = round(min(100.0, (overlap_pct / min(sum_a, sum_b)) * 100.0), 1)

        return {
            "etf_a": {"ticker": ticker_a, "name": prof_a["name"], "ter": prof_a["ter"]},
            "etf_b": {"ticker": ticker_b, "name": prof_b["name"], "ter": prof_b["ter"]},
            "overlap_percentage": final_overlap,
            "shared_holdings_count": len(shared_details),
            "shared_holdings": shared_details[:10],
            "verdict": (
                "Kritisch hoher Gleichlauf (> 70 %): Kaum echte Diversifikation!"
                if final_overlap >= 70
                else "Moderater Overlap (40 - 70 %): Teilweise doppelt investiert."
                if final_overlap >= 40
                else "Niedriger Overlap (< 40 %): Gute Komplementarität."
            )
        }

    @staticmethod
    def analyze_portfolio(
        holdings: List[Dict[str, Any]],
        monthly_savings: float = 250.0,
        gross_return: float = 0.07,
    ) -> Dict[str, Any]:
        """
        Computes portfolio-wide look-through stock concentration,
        pairwise ETF overlap matrix, weighted TER, and compound fee drag.
        """
        def val_of(h):
            if h.get("value") is not None and float(h.get("value") or 0) > 0:
                return float(h["value"])
            sh = float(h.get("shares") or 0)
            pr = float(h.get("current_price") or h.get("currentPrice") or h.get("buy_price") or h.get("buyPrice") or 1.0)
            return max(1.0, sh * pr)

        total_val = sum(val_of(h) for h in holdings) or 1.0
        
        # 1. Classify holdings & collect ETF profiles
        enriched_holdings = []
        etf_list = []
        direct_stocks = []

        for h in holdings:
            t = str(h.get("ticker") or "").upper().strip()
            v = val_of(h)
            w_port = v / total_val  # fraction 0..1
            prof = ETFOverlapService.resolve_profile(t)
            
            item = {
                "ticker": t,
                "name": h.get("name") or prof["name"],
                "value": v,
                "weight_pct": round(w_port * 100.0, 1),
                "weight_fraction": w_port,
                "is_etf": prof["is_etf"],
                "ter": prof["ter"],
                "profile": prof,
            }
            enriched_holdings.append(item)
            if prof["is_etf"]:
                etf_list.append(item)
            else:
                direct_stocks.append(item)

        # 2. Look-Through Concentration (Wahre Klumpen)
        # Sum of (etf_weight * holding_pct) + direct_holding_pct
        look_through_map: Dict[str, float] = {}
        for item in enriched_holdings:
            w_port = item["weight_fraction"]
            h_dict = item["profile"].get("holdings", {})
            for stock_sym, pct_in_fund in h_dict.items():
                effective_add = (w_port * pct_in_fund)  # already in % terms
                look_through_map[stock_sym] = look_through_map.get(stock_sym, 0.0) + effective_add

        top_concentrations = [
            {
                "ticker": k,
                "effective_portfolio_weight_pct": round(v, 2),
                "is_mega_cluster": v >= 10.0,
            }
            for k, v in look_through_map.items()
        ]
        top_concentrations.sort(key=lambda x: x["effective_portfolio_weight_pct"], reverse=True)
        top_10_clusters = top_concentrations[:10]
        top_3_sum = round(sum(x["effective_portfolio_weight_pct"] for x in top_10_clusters[:3]), 1)

        cluster_warning = None
        if top_10_clusters and top_10_clusters[0]["effective_portfolio_weight_pct"] >= 15.0:
            cluster_warning = f"Hohe Klumpenbildung: {top_10_clusters[0]['ticker']} macht über {top_10_clusters[0]['effective_portfolio_weight_pct']}% deines Gesamtdepots aus!"
        elif top_3_sum >= 35.0:
            cluster_warning = f"Top-3 Konzentration: Deine 3 größten Werte machen bereits {top_3_sum}% deines gesamten Depots aus."

        # 3. Pairwise ETF Overlap Matrix
        overlap_matrix = []
        if len(etf_list) >= 2:
            for i, etf_a in enumerate(etf_list):
                row = []
                for j, etf_b in enumerate(etf_list):
                    if i == j:
                        row.append({
                            "etf_a": etf_a["ticker"],
                            "etf_b": etf_b["ticker"],
                            "overlap_pct": 100.0,
                            "is_self": True,
                        })
                    else:
                        pair_res = ETFOverlapService.calculate_pairwise_overlap(etf_a["ticker"], etf_b["ticker"])
                        row.append({
                            "etf_a": etf_a["ticker"],
                            "etf_b": etf_b["ticker"],
                            "overlap_pct": pair_res["overlap_percentage"],
                            "is_self": False,
                        })
                overlap_matrix.append(row)

        # 4. Fee Drag & Gebuehren-Vampir Calculation
        # Weighted average TER
        weighted_ter = sum(item["weight_fraction"] * item["ter"] for item in enriched_holdings)
        weighted_ter_pct = round(weighted_ter * 100.0, 3)

        # Low-cost benchmark: 0.12% TER (Core All-World / S&P 500)
        benchmark_ter = 0.0012
        fee_drag_spread = max(0.0, weighted_ter - benchmark_ter)

        # Compound growth function with monthly deposit
        def future_wealth(r_annual: float, years: int) -> float:
            r_monthly = r_annual / 12.0
            months = years * 12
            # Initial capital compound
            fv_init = total_val * math.pow(1.0 + r_annual, years)
            # Monthly annuity compound
            if r_monthly > 0:
                fv_annuity = monthly_savings * ((math.pow(1.0 + r_monthly, months) - 1.0) / r_monthly)
            else:
                fv_annuity = monthly_savings * months
            return fv_init + fv_annuity

        # Fee simulations over 10, 20, 30 years
        simulations = []
        for yrs in [10, 20, 30]:
            r_gross = gross_return
            r_current = max(0.0, r_gross - weighted_ter)
            r_bench = max(0.0, r_gross - benchmark_ter)

            val_current = future_wealth(r_current, yrs)
            val_bench = future_wealth(r_bench, yrs)
            lost_fees = max(0.0, val_bench - val_current)

            simulations.append({
                "years": yrs,
                "projected_portfolio_value": round(val_current, 0),
                "benchmark_value": round(val_bench, 0),
                "lost_to_fees": round(lost_fees, 0),
                "fee_drag_pct": round((lost_fees / val_bench) * 100.0, 1) if val_bench > 0 else 0.0,
            })

        # Score & Recommendations
        if weighted_ter_pct <= 0.20:
            fee_score = "CHAMPION"
            fee_headline = "Kosten-Champion (Sehr geringe laufende Gebühren)"
            fee_badge_color = "emerald"
        elif weighted_ter_pct <= 0.40:
            fee_score = "MODERATE"
            fee_headline = "Moderates Gebührenniveau (Solide Kostenstruktur)"
            fee_badge_color = "amber"
        else:
            fee_score = "VAMPIRE"
            fee_headline = "Gebühren-Vampir-Alarm (Hoher Zinseszins-Verlust!)"
            fee_badge_color = "rose"

        # Find specific expensive ETFs (TER >= 0.35%)
        expensive_positions = [
            {
                "ticker": item["ticker"],
                "name": item["name"],
                "ter_pct": round(item["ter"] * 100.0, 2),
                "weight_pct": item["weight_pct"],
                "annual_cost_eur": round(item["value"] * item["ter"], 2),
                "cheaper_alternative": "iShares Core MSCI World (0.20%) oder Vanguard FTSE All-World (0.22%)",
            }
            for item in enriched_holdings
            if item["is_etf"] and item["ter"] >= 0.0035
        ]

        return {
            "total_portfolio_value": round(total_val, 2),
            "etf_count": len(etf_list),
            "single_stock_count": len(direct_stocks),
            "weighted_ter_pct": weighted_ter_pct,
            "fee_score": fee_score,
            "fee_headline": fee_headline,
            "fee_badge_color": fee_badge_color,
            "top_look_through_clusters": top_10_clusters,
            "top_3_concentration_pct": top_3_sum,
            "cluster_warning": cluster_warning,
            "etf_overlap_matrix": overlap_matrix,
            "etf_list": [{"ticker": e["ticker"], "name": e["name"], "ter": round(e["ter"] * 100.0, 2), "weight": e["weight_pct"]} for e in etf_list],
            "fee_simulations": simulations,
            "expensive_positions": expensive_positions,
            "monthly_savings_input": monthly_savings,
        }
