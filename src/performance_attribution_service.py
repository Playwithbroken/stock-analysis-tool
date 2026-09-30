"""
Institutional Performance Attribution & Brinson-Fachler Decomposition Service.
Follows the GIPS (Global Investment Performance Standards) and CFA Institute standard:
Delta_R = R_port - R_bench = Allocation_Effect + Selection_Effect + Interaction_Effect
"""

import math
from typing import Dict, List, Any, Optional


class PerformanceAttributionService:
    """
    Computes GIPS Brinson-Fachler performance attribution, Active Share,
    and sector-level alpha drivers against global benchmarks.
    """

    # Institutional Benchmark Sector Allocation & 1-Year Returns (%)
    BENCHMARKS: Dict[str, Dict[str, Any]] = {
        "msci_world": {
            "name": "MSCI World Net Total Return",
            "benchmark_return_pct": 16.50,
            "sectors": {
                "Information Technology": {"weight_pct": 24.0, "return_pct": 28.5},
                "Financials": {"weight_pct": 15.0, "return_pct": 14.2},
                "Health Care": {"weight_pct": 12.0, "return_pct": 8.5},
                "Industrials": {"weight_pct": 11.0, "return_pct": 13.8},
                "Consumer Discretionary": {"weight_pct": 10.5, "return_pct": 15.0},
                "Communication Services": {"weight_pct": 8.0, "return_pct": 22.0},
                "Consumer Staples": {"weight_pct": 6.5, "return_pct": 5.2},
                "Energy": {"weight_pct": 4.5, "return_pct": 4.0},
                "Materials": {"weight_pct": 4.0, "return_pct": 6.8},
                "Utilities": {"weight_pct": 2.5, "return_pct": 7.5},
                "Real Estate": {"weight_pct": 2.0, "return_pct": 3.2},
            }
        },
        "sp500": {
            "name": "S&P 500 Total Return",
            "benchmark_return_pct": 19.20,
            "sectors": {
                "Information Technology": {"weight_pct": 30.5, "return_pct": 32.0},
                "Financials": {"weight_pct": 13.0, "return_pct": 15.5},
                "Health Care": {"weight_pct": 11.5, "return_pct": 9.0},
                "Consumer Discretionary": {"weight_pct": 10.5, "return_pct": 16.2},
                "Communication Services": {"weight_pct": 9.0, "return_pct": 24.5},
                "Industrials": {"weight_pct": 8.5, "return_pct": 14.5},
                "Consumer Staples": {"weight_pct": 6.0, "return_pct": 5.5},
                "Energy": {"weight_pct": 4.0, "return_pct": 3.8},
                "Materials": {"weight_pct": 2.5, "return_pct": 7.0},
                "Utilities": {"weight_pct": 2.5, "return_pct": 8.2},
                "Real Estate": {"weight_pct": 2.0, "return_pct": 4.0},
            }
        },
        "dax": {
            "name": "DAX 40 Performance-Index",
            "benchmark_return_pct": 12.80,
            "sectors": {
                "Industrials": {"weight_pct": 22.5, "return_pct": 12.0},
                "Financials": {"weight_pct": 18.0, "return_pct": 16.5},
                "Information Technology": {"weight_pct": 16.5, "return_pct": 25.0},
                "Consumer Discretionary": {"weight_pct": 12.0, "return_pct": 2.5},
                "Health Care": {"weight_pct": 11.0, "return_pct": 7.5},
                "Materials": {"weight_pct": 9.5, "return_pct": 5.0},
                "Utilities": {"weight_pct": 4.5, "return_pct": 6.0},
                "Communication Services": {"weight_pct": 3.5, "return_pct": 9.0},
                "Consumer Staples": {"weight_pct": 1.5, "return_pct": 4.5},
                "Energy": {"weight_pct": 0.5, "return_pct": 2.0},
                "Real Estate": {"weight_pct": 0.5, "return_pct": 1.5},
            }
        },
        "stoxx600": {
            "name": "STOXX Europe 600 Net Return",
            "benchmark_return_pct": 11.50,
            "sectors": {
                "Financials": {"weight_pct": 17.5, "return_pct": 15.0},
                "Health Care": {"weight_pct": 16.0, "return_pct": 8.0},
                "Industrials": {"weight_pct": 16.0, "return_pct": 13.5},
                "Consumer Staples": {"weight_pct": 10.0, "return_pct": 4.8},
                "Consumer Discretionary": {"weight_pct": 9.5, "return_pct": 7.5},
                "Information Technology": {"weight_pct": 8.5, "return_pct": 24.0},
                "Materials": {"weight_pct": 7.0, "return_pct": 5.5},
                "Energy": {"weight_pct": 6.0, "return_pct": 3.5},
                "Utilities": {"weight_pct": 4.5, "return_pct": 6.5},
                "Communication Services": {"weight_pct": 3.5, "return_pct": 8.5},
                "Real Estate": {"weight_pct": 1.5, "return_pct": 2.5},
            }
        }
    }

    # Ticker Sector Mapping Fallback
    TICKER_SECTOR_MAP: Dict[str, str] = {
        "AAPL": "Information Technology",
        "MSFT": "Information Technology",
        "NVDA": "Information Technology",
        "ASML": "Information Technology",
        "SAP": "Information Technology",
        "ORCL": "Information Technology",
        "CRM": "Information Technology",
        "GOOGL": "Communication Services",
        "GOOG": "Communication Services",
        "META": "Communication Services",
        "NFLX": "Communication Services",
        "DIS": "Communication Services",
        "AMZN": "Consumer Discretionary",
        "TSLA": "Consumer Discretionary",
        "HD": "Consumer Discretionary",
        "MCD": "Consumer Discretionary",
        "NKE": "Consumer Discretionary",
        "BMW": "Consumer Discretionary",
        "MBG": "Consumer Discretionary",
        "MC": "Consumer Discretionary",
        "JPM": "Financials",
        "BAC": "Financials",
        "V": "Financials",
        "MA": "Financials",
        "ALV": "Financials",
        "MUV2": "Financials",
        "SAN": "Financials",
        "BNP": "Financials",
        "UBSG": "Financials",
        "JNJ": "Health Care",
        "PFE": "Health Care",
        "UNH": "Health Care",
        "ABBV": "Health Care",
        "LLY": "Health Care",
        "NOVO": "Health Care",
        "NESN": "Consumer Staples",
        "PG": "Consumer Staples",
        "KO": "Consumer Staples",
        "PEP": "Consumer Staples",
        "CAT": "Industrials",
        "HON": "Industrials",
        "UNP": "Industrials",
        "SIE": "Industrials",
        "AIR": "Industrials",
        "XOM": "Energy",
        "CVX": "Energy",
        "SHEL": "Energy",
        "BP": "Energy",
        "LIN": "Materials",
        "BAS": "Materials",
        "NEE": "Utilities",
        "DUK": "Utilities",
        "PLD": "Real Estate",
        "AMT": "Real Estate"
    }

    @classmethod
    def detect_sector(cls, ticker: str, provided_sector: Optional[str] = None) -> str:
        """Resolves GICS sector for a ticker."""
        if provided_sector and str(provided_sector).strip() and str(provided_sector).strip().lower() != "unknown":
            return str(provided_sector).strip()
        clean = ticker.strip().upper()
        return cls.TICKER_SECTOR_MAP.get(clean, "Information Technology")

    @classmethod
    def calculate_brinson_attribution(
        cls,
        holdings: List[Dict[str, Any]],
        benchmark_key: str = "msci_world"
    ) -> Dict[str, Any]:
        """
        Calculates exact Brinson-Fachler (1985) performance attribution:
        Active Return (Delta R) = Allocation Effect + Selection Effect + Interaction Effect
        """
        if not holdings:
            return {
                "valid": False,
                "error": "Mindestens 1 Position für Attributions-Analyse erforderlich."
            }

        bench_data = cls.BENCHMARKS.get(benchmark_key.lower(), cls.BENCHMARKS["msci_world"])
        benchmark_name = bench_data["name"]
        bench_sectors = bench_data["sectors"]
        R_b = sum((s["weight_pct"] / 100.0) * s["return_pct"] for s in bench_sectors.values())

        # 1. Aggregate Portfolio by Sector
        total_val = 0.0
        sector_values: Dict[str, float] = {}
        sector_holdings: Dict[str, List[Dict[str, Any]]] = {}

        for h in holdings:
            t = str(h.get("ticker", "")).strip().upper()
            shares = float(h.get("shares") or 0.0)
            price = float(h.get("current_price") or h.get("buyPrice") or 100.0)
            val = shares * price
            total_val += val

            sec = cls.detect_sector(t, h.get("sector"))
            sector_values[sec] = sector_values.get(sec, 0.0) + val
            if sec not in sector_holdings:
                sector_holdings[sec] = []

            # Determine holding return (use gain_loss_pct or realistic synthetic proxy)
            gain_pct = h.get("gain_loss_pct")
            if gain_pct is None:
                buy_p = float(h.get("buyPrice") or price)
                gain_pct = ((price - buy_p) / buy_p * 100.0) if buy_p > 0 else 15.0

            sector_holdings[sec].append({
                "ticker": t,
                "name": h.get("name") or t,
                "value_eur": val,
                "return_pct": float(gain_pct)
            })

        if total_val <= 0:
            total_val = 1000.0

        # Calculate weighted return per sector in the portfolio
        portfolio_sectors: Dict[str, Dict[str, float]] = {}
        total_portfolio_return = 0.0

        for sec, sec_val in sector_values.items():
            w_p = sec_val / total_val
            # Weighted return of holdings inside this sector
            sec_return = sum((h["value_eur"] / sec_val) * h["return_pct"] for h in sector_holdings[sec]) if sec_val > 0 else 0.0
            portfolio_sectors[sec] = {
                "weight": w_p,
                "weight_pct": w_p * 100.0,
                "return_pct": sec_return
            }
            total_portfolio_return += w_p * sec_return

        R_p = total_portfolio_return
        active_return = R_p - R_b

        # 2. Brinson-Fachler Decomposition across all sectors (union of portfolio & benchmark)
        all_sector_names = sorted(list(set(list(bench_sectors.keys()) + list(portfolio_sectors.keys()))))

        attribution_rows = []
        total_alloc = 0.0
        total_select = 0.0
        total_interact = 0.0
        active_share_sum = 0.0

        for sec in all_sector_names:
            w_p_pct = portfolio_sectors.get(sec, {}).get("weight_pct", 0.0)
            w_p = w_p_pct / 100.0
            r_p = portfolio_sectors.get(sec, {}).get("return_pct", bench_sectors.get(sec, {}).get("return_pct", 0.0))

            w_b_pct = bench_sectors.get(sec, {}).get("weight_pct", 0.0)
            w_b = w_b_pct / 100.0
            r_b = bench_sectors.get(sec, {}).get("return_pct", R_b)

            # Brinson-Fachler Formulas:
            # Allocation Effect = (w_p - w_b) * (r_b - R_b)
            alloc_effect = (w_p - w_b) * (r_b - R_b)

            # Selection Effect = w_b * (r_p - r_b)
            select_effect = w_b * (r_p - r_b)

            # Interaction Effect = (w_p - w_b) * (r_p - r_b)
            interact_effect = (w_p - w_b) * (r_p - r_b)

            total_sector_effect = alloc_effect + select_effect + interact_effect

            total_alloc += alloc_effect
            total_select += select_effect
            total_interact += interact_effect

            active_share_sum += abs(w_p_pct - w_b_pct)

            attribution_rows.append({
                "sector": sec,
                "portfolio_weight_pct": round(w_p_pct, 2),
                "benchmark_weight_pct": round(w_b_pct, 2),
                "active_weight_pct": round(w_p_pct - w_b_pct, 2),
                "portfolio_return_pct": round(r_p, 2),
                "benchmark_return_pct": round(r_b, 2),
                "allocation_effect_pct": round(alloc_effect, 3),
                "selection_effect_pct": round(select_effect, 3),
                "interaction_effect_pct": round(interact_effect, 3),
                "total_effect_pct": round(total_sector_effect, 3)
            })

        # Sort sectors by total effect descending
        attribution_rows.sort(key=lambda x: x["total_effect_pct"], reverse=True)

        # Active Share: 0.5 * sum(|w_p - w_b|)
        active_share = min(100.0, max(0.0, round(active_share_sum / 2.0, 1)))

        # Individual Stock Selection Highlights
        stock_selection_highlights = []
        for sec, h_list in sector_holdings.items():
            r_b = bench_sectors.get(sec, {}).get("return_pct", R_b)
            for h in h_list:
                val = h["value_eur"]
                ret = h["return_pct"]
                weight_in_port = (val / total_val) * 100.0
                excess_ret = ret - r_b
                stock_selection_highlights.append({
                    "ticker": h["ticker"],
                    "name": h["name"],
                    "sector": sec,
                    "weight_pct": round(weight_in_port, 2),
                    "return_pct": round(ret, 2),
                    "benchmark_sector_return_pct": round(r_b, 2),
                    "excess_alpha_pct": round(excess_ret, 2),
                    "alpha_contribution_pct": round((weight_in_port / 100.0) * excess_ret, 3)
                })

        stock_selection_highlights.sort(key=lambda x: x["alpha_contribution_pct"], reverse=True)

        # Active Management Style Classification
        if active_share >= 80.0:
            style_label = "High Active Alpha (Konzentriertes Überzeugungsmandat)"
            style_tone = "border-emerald-500/30 bg-emerald-500/15 text-emerald-800 dark:text-emerald-300"
        elif active_share >= 60.0:
            style_label = "Aktives Management (Signifikante Benchmark-Abweichung)"
            style_tone = "border-teal-500/30 bg-teal-500/15 text-teal-800 dark:text-teal-300"
        elif active_share >= 35.0:
            style_label = "Moderat Aktiv (Benchmark-bewusstes Core-Satellit)"
            style_tone = "border-amber-500/30 bg-amber-500/15 text-amber-800 dark:text-amber-300"
        else:
            style_label = "Closet Indexing (Hohe Benchmark-Nähe)"
            style_tone = "border-rose-500/30 bg-rose-500/15 text-rose-800 dark:text-rose-300"

        return {
            "valid": True,
            "benchmark_key": benchmark_key,
            "benchmark_name": benchmark_name,
            "summary": {
                "portfolio_return_pct": round(R_p, 2),
                "benchmark_return_pct": round(R_b, 2),
                "active_return_pct": round(active_return, 2),
                "allocation_effect_pct": round(total_alloc, 3),
                "selection_effect_pct": round(total_select, 3),
                "interaction_effect_pct": round(total_interact, 3),
                "active_share_pct": active_share,
                "style_badge": {
                    "label": style_label,
                    "tone": style_tone
                }
            },
            "sectors": attribution_rows,
            "stock_highlights": stock_selection_highlights[:10]
        }
