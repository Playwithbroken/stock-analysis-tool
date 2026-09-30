"""
Options & Stillhalter-Strategie Service (Covered Call & Cash-Secured Put Optimizer)
Mathematical Black-Scholes-Merton Engine, Greeks, Probability of Profit (POP),
and automated portfolio income scanning.
"""

from typing import Dict, Any, List, Optional
import math


def norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function using error function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * x * x)


class BlackScholesEngine:
    """
    Standard Black-Scholes-Merton pricing engine for European options.
    S: Current asset price
    K: Strike price
    T: Time to maturity in years (dte / 365.0)
    r: Risk-free interest rate (e.g. 0.035 for 3.5%)
    sigma: Volatility (annualized, e.g. 0.25 for 25%)
    """

    @staticmethod
    def calculate_d1_d2(S: float, K: float, T: float, r: float, sigma: float):
        if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
            return 0.0, 0.0
        d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        return d1, d2

    @staticmethod
    def call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
        if T <= 0:
            return max(0.0, S - K)
        d1, d2 = BlackScholesEngine.calculate_d1_d2(S, K, T, r, sigma)
        call = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
        return max(0.01, round(call, 2))

    @staticmethod
    def put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
        if T <= 0:
            return max(0.0, K - S)
        d1, d2 = BlackScholesEngine.calculate_d1_d2(S, K, T, r, sigma)
        put = K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)
        return max(0.01, round(put, 2))

    @staticmethod
    def call_delta(S: float, K: float, T: float, r: float, sigma: float) -> float:
        if T <= 0:
            return 1.0 if S > K else 0.0
        d1, _ = BlackScholesEngine.calculate_d1_d2(S, K, T, r, sigma)
        return round(norm_cdf(d1), 3)

    @staticmethod
    def put_delta(S: float, K: float, T: float, r: float, sigma: float) -> float:
        if T <= 0:
            return -1.0 if S < K else 0.0
        d1, _ = BlackScholesEngine.calculate_d1_d2(S, K, T, r, sigma)
        return round(norm_cdf(d1) - 1.0, 3)

    @staticmethod
    def theta(S: float, K: float, T: float, r: float, sigma: float, is_call: bool = True) -> float:
        """Theta per calendar day (decay of option value each day)."""
        if T <= 0:
            return 0.0
        d1, d2 = BlackScholesEngine.calculate_d1_d2(S, K, T, r, sigma)
        first_term = -(S * norm_pdf(d1) * sigma) / (2.0 * math.sqrt(T))
        if is_call:
            second_term = -r * K * math.exp(-r * T) * norm_cdf(d2)
        else:
            second_term = r * K * math.exp(-r * T) * norm_cdf(-d2)
        annual_theta = first_term + second_term
        # Daily theta
        return round(annual_theta / 365.0, 3)


class OptionsService:
    DEFAULT_RISK_FREE_RATE = 0.035  # 3.5% EZB/Fed risk-free benchmark

    # Fallback Implied Volatilities by ticker category if live market data not provided
    DEFAULT_VOLATILITIES: Dict[str, float] = {
        "TSLA": 0.48, "NVDA": 0.42, "AMD": 0.40, "ARKK": 0.38,
        "META": 0.32, "AMZN": 0.28, "GOOGL": 0.24, "MSFT": 0.22,
        "AAPL": 0.20, "SPY": 0.14, "QQQ": 0.18, "URTH": 0.13,
        "VWCE.DE": 0.13, "EXS1.DE": 0.15, "ALV.DE": 0.16, "SAP.DE": 0.20,
    }

    @staticmethod
    def resolve_iv(ticker: str, custom_iv: Optional[float] = None) -> float:
        if custom_iv is not None and custom_iv > 0.05:
            return min(1.5, max(0.10, custom_iv))
        t = ticker.upper().strip()
        return OptionsService.DEFAULT_VOLATILITIES.get(t, 0.26)

    @staticmethod
    def get_stock_options_suite(
        ticker: str,
        current_price: float,
        shares: int = 100,
        dte: int = 30,
        custom_iv: Optional[float] = None,
        risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
    ) -> Dict[str, Any]:
        """
        Calculates 3 Covered Call scenarios and 3 Cash-Secured Put scenarios
        for an individual stock.
        """
        S = max(1.0, float(current_price))
        T = max(1, dte) / 365.0
        r = risk_free_rate
        sigma = OptionsService.resolve_iv(ticker, custom_iv)

        num_contracts = max(1, shares // 100)
        contract_multiplier = 100

        # --- 1. COVERED CALL SCENARIOS ---
        # A: Conservative (OTM ~8%, Target Delta ~0.15, high POP ~85%)
        # B: Balanced (OTM ~4%, Target Delta ~0.25, optimal yield ~75% POP)
        # C: Aggressive (OTM ~1.5%, Target Delta ~0.40, max premium ~60% POP)
        cc_configs = [
            {
                "name": "Konservativ",
                "badge": "Hohe Sicherheit",
                "color": "emerald",
                "strike_mult": 1.08,
                "target_delta_desc": "Delta ~0.15",
                "ideal_for": "Fokus auf Kursgewinne der Aktie; geringes Risiko, ausgebucht zu werden."
            },
            {
                "name": "Ausgewogen",
                "badge": "Optimaler Ertrag",
                "color": "cyan",
                "strike_mult": 1.04,
                "target_delta_desc": "Delta ~0.25",
                "ideal_for": "Bester Kompromiss aus hoher Prämie und noch verbleibendem Kurspotenzial."
            },
            {
                "name": "Aggressiv",
                "badge": "Maximaler Cashflow",
                "color": "amber",
                "strike_mult": 1.015,
                "target_delta_desc": "Delta ~0.40",
                "ideal_for": "Maximale Sofortprämie; ideal bei leicht seitwärts tendierenden Märkten."
            }
        ]

        covered_calls = []
        for cfg in cc_configs:
            # Round strike to practical increments
            raw_k = S * cfg["strike_mult"]
            if S > 200:
                K = round(raw_k / 5.0) * 5.0
            elif S > 50:
                K = round(raw_k / 2.5) * 2.5
            else:
                K = round(raw_k)

            # Ensure OTM
            if K <= S:
                K = S + 1.0

            prem = BlackScholesEngine.call_price(S, K, T, r, sigma)
            delta = BlackScholesEngine.call_delta(S, K, T, r, sigma)
            daily_theta = BlackScholesEngine.theta(S, K, T, r, sigma, is_call=True)

            total_prem_eur = prem * contract_multiplier * num_contracts
            annualized_yield = (prem / S) * (365.0 / dte) * 100.0
            downside_buffer_pct = (prem / S) * 100.0
            max_capital_gain_pct = ((K - S) / S) * 100.0
            max_total_return_pct = downside_buffer_pct + max_capital_gain_pct
            pop_pct = round(max(10.0, min(95.0, (1.0 - delta) * 100.0)), 1)
            break_even = round(S - prem, 2)

            covered_calls.append({
                "scenario": cfg["name"],
                "badge": cfg["badge"],
                "color": cfg["color"],
                "ideal_for": cfg["ideal_for"],
                "strike": round(K, 2),
                "premium_per_share": prem,
                "total_premium_eur": round(total_prem_eur, 2),
                "annualized_yield_pct": round(annualized_yield, 1),
                "downside_buffer_pct": round(downside_buffer_pct, 2),
                "max_total_return_pct": round(max_total_return_pct, 1),
                "pop_pct": pop_pct,
                "delta": delta,
                "daily_theta": daily_theta,
                "break_even": break_even,
            })

        # --- 2. CASH-SECURED PUT SCENARIOS ---
        # A: Tiefer Discount (OTM -10%, Target Put Delta ~-0.15)
        # B: Moderater Discount (OTM -5%, Target Put Delta ~-0.25)
        # C: Knapper Einstieg (OTM -2%, Target Put Delta ~-0.38)
        put_configs = [
            {
                "name": "Tiefer Discount",
                "badge": "10% Sicherheitsabstand",
                "color": "emerald",
                "strike_mult": 0.90,
                "ideal_for": "Sehr günstige Einstiegschance mit hoher Sicherheitsmarge."
            },
            {
                "name": "Moderater Rabatt",
                "badge": "5% Kaufrabatt",
                "color": "cyan",
                "strike_mult": 0.95,
                "ideal_for": "Realistische Kaufchance bei gesunder Rendite auf das hinterlegte Cash."
            },
            {
                "name": "Aktiver Einstieg",
                "badge": "Maximaler Zins",
                "color": "amber",
                "strike_mult": 0.98,
                "ideal_for": "Aktie soll möglichst zeitnah ins Depot; maximale Stillhalter-Prämie."
            }
        ]

        cash_secured_puts = []
        for cfg in put_configs:
            raw_k = S * cfg["strike_mult"]
            if S > 200:
                K = round(raw_k / 5.0) * 5.0
            elif S > 50:
                K = round(raw_k / 2.5) * 2.5
            else:
                K = round(raw_k)

            if K >= S:
                K = S - 1.0

            prem = BlackScholesEngine.put_price(S, K, T, r, sigma)
            delta = BlackScholesEngine.put_delta(S, K, T, r, sigma)
            daily_theta = BlackScholesEngine.theta(S, K, T, r, sigma, is_call=False)

            capital_required = K * contract_multiplier * num_contracts
            total_prem_eur = prem * contract_multiplier * num_contracts
            roc_annualized = (prem / K) * (365.0 / dte) * 100.0
            net_entry_price = round(K - prem, 2)
            discount_to_market_pct = round(((S - net_entry_price) / S) * 100.0, 1)
            pop_pct = round(max(10.0, min(95.0, (1.0 - abs(delta)) * 100.0)), 1)

            cash_secured_puts.append({
                "scenario": cfg["name"],
                "badge": cfg["badge"],
                "color": cfg["color"],
                "ideal_for": cfg["ideal_for"],
                "strike": round(K, 2),
                "premium_per_share": prem,
                "total_premium_eur": round(total_prem_eur, 2),
                "capital_required_eur": round(capital_required, 2),
                "return_on_capital_pct": round(roc_annualized, 1),
                "net_entry_price": net_entry_price,
                "discount_to_market_pct": discount_to_market_pct,
                "pop_pct": pop_pct,
                "delta": delta,
                "daily_theta": daily_theta,
            })

        return {
            "ticker": ticker.upper(),
            "current_price": round(S, 2),
            "shares_analyzed": shares,
            "contracts_count": num_contracts,
            "dte": dte,
            "implied_volatility_pct": round(sigma * 100.0, 1),
            "risk_free_rate_pct": round(r * 100.0, 2),
            "covered_calls": covered_calls,
            "cash_secured_puts": cash_secured_puts,
        }

    @staticmethod
    def analyze_portfolio_options(
        holdings: List[Dict[str, Any]],
        dte: int = 30
    ) -> Dict[str, Any]:
        """
        Scans all portfolio holdings for covered-call income opportunities.
        Identifies eligible holdings (scaled per 100 shares), calculates total
        monthly and annual cashflow potential.
        """
        eligible_positions = []
        total_monthly_cashflow_eur = 0.0
        total_annual_cashflow_eur = 0.0
        total_covered_value_eur = 0.0

        for h in holdings:
            t = str(h.get("ticker") or "").upper().strip()
            if not t:
                continue

            sh = float(h.get("shares") or 0.0)
            if sh < 1:
                continue

            cp = float(h.get("current_price") or h.get("currentPrice") or h.get("buy_price") or h.get("buyPrice") or 1.0)
            val = sh * cp

            # Analyze option suite
            suite = OptionsService.get_stock_options_suite(
                ticker=t,
                current_price=cp,
                shares=int(sh),
                dte=dte
            )

            # Use "Ausgewogen" as standard baseline
            balanced_cc = next((c for c in suite["covered_calls"] if c["scenario"] == "Ausgewogen"), suite["covered_calls"][0])
            
            # If shares >= 100, can sell physical contracts immediately;
            # if < 100, calculate fractional / synthetic potential
            is_full_lot = sh >= 100
            actual_contracts = int(sh // 100) if is_full_lot else 1
            monthly_prem = (balanced_cc["premium_per_share"] * 100.0 * actual_contracts) if is_full_lot else (balanced_cc["premium_per_share"] * sh)
            annual_prem = monthly_prem * (365.0 / dte)

            if is_full_lot:
                total_monthly_cashflow_eur += monthly_prem
                total_annual_cashflow_eur += annual_prem
                total_covered_value_eur += (actual_contracts * 100.0 * cp)

            eligible_positions.append({
                "ticker": t,
                "name": h.get("name") or t,
                "shares": sh,
                "current_price": round(cp, 2),
                "position_value": round(val, 2),
                "is_full_lot": is_full_lot,
                "contracts": actual_contracts if is_full_lot else 0,
                "strike": balanced_cc["strike"],
                "premium_per_share": balanced_cc["premium_per_share"],
                "estimated_monthly_income_eur": round(monthly_prem, 2),
                "annualized_yield_pct": balanced_cc["annualized_yield_pct"],
                "pop_pct": balanced_cc["pop_pct"],
                "downside_buffer_pct": balanced_cc["downside_buffer_pct"],
                "iv_pct": suite["implied_volatility_pct"],
            })

        eligible_positions.sort(key=lambda x: (x["is_full_lot"], x["estimated_monthly_income_eur"]), reverse=True)
        full_lots_count = sum(1 for p in eligible_positions if p["is_full_lot"])

        return {
            "dte": dte,
            "total_monthly_cashflow_eur": round(total_monthly_cashflow_eur, 2),
            "total_annual_cashflow_eur": round(total_annual_cashflow_eur, 2),
            "total_covered_value_eur": round(total_covered_value_eur, 2),
            "full_lots_count": full_lots_count,
            "positions": eligible_positions,
            "summary_headline": (
                f"Aktives Prämien-Potenzial: {total_monthly_cashflow_eur:,.0f} €/Monat ({total_annual_cashflow_eur:,.0f} €/Jahr) mit {full_lots_count} handelbaren 100er-Positionen!"
                if full_lots_count > 0
                else "Keine vollen 100er-Positionen im Depot vorhanden. Aufstockung auf 100 Stück schaltet physische Covered Calls frei!"
            ),
        }
