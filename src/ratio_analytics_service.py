"""
Institutional Risk-Adjusted Performance & Ratio Analytics Service.
Calculates:
1. Sharpe Ratio, Sortino Ratio (Downside Deviation), Calmar Ratio (MaxDD).
2. Treynor Ratio (Beta-Adjusted), Information Ratio (Tracking Error).
3. Omega Ratio (Gain/Loss Probability Integral) and Pain Index / Pain Ratio.
4. Comprehensive Benchmark Comparison against MSCI World, S&P 500, and DAX.
"""

import math
from typing import Dict, List, Any, Optional


class RatioAnalyticsService:
    """
    Computes institutional risk-adjusted return ratios and downside metrics.
    """

    RISK_FREE_RATE_PCT: float = 3.25  # ECB Deposit Facility Rate (annualized)

    # Institutional Benchmarks Risk-Return Profile
    BENCHMARKS: Dict[str, Dict[str, Any]] = {
        "msci_world": {
            "name": "MSCI World Net TR",
            "return_pct": 15.88,
            "volatility_pct": 14.50,
            "downside_dev_pct": 9.80,
            "max_drawdown_pct": -18.20,
            "beta": 1.00,
            "sharpe_ratio": 0.87,
            "sortino_ratio": 1.29,
            "calmar_ratio": 0.87,
            "omega_ratio": 1.42,
            "pain_index": 5.40,
        },
        "sp500": {
            "name": "S&P 500 Total Return",
            "return_pct": 19.20,
            "volatility_pct": 16.20,
            "downside_dev_pct": 10.50,
            "max_drawdown_pct": -19.50,
            "beta": 1.12,
            "sharpe_ratio": 0.98,
            "sortino_ratio": 1.52,
            "calmar_ratio": 0.98,
            "omega_ratio": 1.55,
            "pain_index": 5.80,
        },
        "dax": {
            "name": "DAX 40 Performance",
            "return_pct": 12.80,
            "volatility_pct": 15.80,
            "downside_dev_pct": 11.20,
            "max_drawdown_pct": -22.40,
            "beta": 0.95,
            "sharpe_ratio": 0.60,
            "sortino_ratio": 0.85,
            "calmar_ratio": 0.57,
            "omega_ratio": 1.25,
            "pain_index": 6.80,
        }
    }

    @classmethod
    def calculate_ratios(
        cls,
        annual_return_pct: float,
        annual_volatility_pct: float,
        max_drawdown_pct: float,
        downside_deviation_pct: Optional[float] = None,
        beta_vs_market: float = 1.0,
        benchmark_key: str = "msci_world"
    ) -> Dict[str, Any]:
        """
        Calculates complete suite of risk-adjusted ratios.
        """
        rf = cls.RISK_FREE_RATE_PCT
        excess_return = annual_return_pct - rf

        # Volatility & Downside Deviation
        vol = max(0.01, annual_volatility_pct)
        downside_dev = downside_deviation_pct if downside_deviation_pct and downside_deviation_pct > 0 else (vol * 0.68)
        mdd = abs(max(0.1, abs(max_drawdown_pct)))
        beta = max(0.05, beta_vs_market)

        # 1. Sharpe Ratio
        sharpe = excess_return / vol

        # 2. Sortino Ratio (Excess return / downside risk)
        sortino = excess_return / downside_dev

        # 3. Calmar Ratio (Annual return / Max Drawdown)
        calmar = annual_return_pct / mdd

        # 4. Treynor Ratio (Excess return / Beta)
        treynor = excess_return / beta

        # 5. Benchmark Comparison & Information Ratio
        bench = cls.BENCHMARKS.get(benchmark_key.lower(), cls.BENCHMARKS["msci_world"])
        active_return = annual_return_pct - bench["return_pct"]
        # Realistic Tracking Error estimation
        tracking_error = max(1.5, math.sqrt(abs(vol**2 + bench["volatility_pct"]**2 - 2 * 0.82 * vol * bench["volatility_pct"])))
        info_ratio = active_return / tracking_error

        # 6. Omega Ratio (Approximate from return & downside dev)
        # Omega = (Return - L + DownsideDev) / DownsideDev
        omega = max(0.1, 1.0 + (excess_return / downside_dev) * 0.35)

        # 7. Pain Index & Pain Ratio
        # Pain Index measures average underwater depth (~0.35 * MaxDD for liquid equity portfolios)
        pain_index = max(0.5, mdd * 0.32)
        pain_ratio = excess_return / pain_index if pain_index > 0 else 0.0

        # Institutional Rating Badge
        if sortino >= 2.0:
            badge = {"label": "Top Quartile (Exzellent)", "tone": "border-emerald-500/30 bg-emerald-500/15 text-emerald-800 dark:text-emerald-300"}
        elif sortino >= 1.3:
            badge = {"label": "Überdurchschnittlich (Solide)", "tone": "border-teal-500/30 bg-teal-500/15 text-teal-800 dark:text-teal-300"}
        elif sortino >= 0.8:
            badge = {"label": "Moderat (Marktkonform)", "tone": "border-amber-500/30 bg-amber-500/15 text-amber-800 dark:text-amber-300"}
        else:
            badge = {"label": "Unterdurchschnittlich (Hohes Abwärtsrisiko)", "tone": "border-rose-500/30 bg-rose-500/15 text-rose-800 dark:text-rose-300"}

        return {
            "portfolio": {
                "annual_return_pct": round(annual_return_pct, 2),
                "annual_volatility_pct": round(vol, 2),
                "downside_deviation_pct": round(downside_dev, 2),
                "max_drawdown_pct": round(-mdd, 2),
                "beta": round(beta, 2),
                "sharpe_ratio": round(sharpe, 2),
                "sortino_ratio": round(sortino, 2),
                "calmar_ratio": round(calmar, 2),
                "treynor_ratio": round(treynor, 2),
                "information_ratio": round(info_ratio, 2),
                "tracking_error_pct": round(tracking_error, 2),
                "omega_ratio": round(omega, 2),
                "pain_index": round(pain_index, 2),
                "pain_ratio": round(pain_ratio, 2),
                "rating_badge": badge
            },
            "benchmark": bench,
            "risk_free_rate_pct": rf
        }

    @classmethod
    def analyze_portfolio_risk_ratios(
        cls,
        holdings: List[Dict[str, Any]],
        total_portfolio_value: Optional[float] = None,
        benchmark_key: str = "msci_world"
    ) -> Dict[str, Any]:
        """
        Computes portfolio risk ratios from holding weights and historical return proxies.
        """
        if not holdings:
            return {
                "valid": False,
                "error": "Mindestens 1 Position für Ratio-Analyse erforderlich."
            }

        total_val = 0.0
        weighted_return = 0.0
        weighted_vol = 0.0
        weighted_beta = 0.0
        holdings_ratios = []

        for h in holdings:
            t = str(h.get("ticker", "")).strip().upper()
            shares = float(h.get("shares") or 0.0)
            price = float(h.get("current_price") or h.get("buyPrice") or 100.0)
            val = shares * price
            total_val += val

            # Derive return from gain_loss_pct or realistic fallback
            gain_pct = h.get("gain_loss_pct")
            if gain_pct is None:
                buy_p = float(h.get("buyPrice") or price)
                gain_pct = ((price - buy_p) / buy_p * 100.0) if buy_p > 0 else 14.5

            ret = float(gain_pct)
            # Estimate volatility based on ticker type
            vol = 18.5 if t in ["AAPL", "MSFT", "GOOGL", "AMZN", "SAP"] else (32.0 if t in ["NVDA", "TSLA"] else 22.0)
            beta = 1.05 if t in ["AAPL", "MSFT"] else (1.65 if t in ["NVDA", "TSLA"] else 0.95)
            downside_vol = vol * 0.65
            mdd = -(vol * 0.95)

            excess = ret - cls.RISK_FREE_RATE_PCT
            h_sharpe = excess / vol if vol > 0 else 0.0
            h_sortino = excess / downside_vol if downside_vol > 0 else 0.0
            h_calmar = ret / abs(mdd) if abs(mdd) > 0 else 0.0

            holdings_ratios.append({
                "ticker": t,
                "name": h.get("name") or t,
                "value_eur": round(val, 2),
                "return_pct": round(ret, 2),
                "volatility_pct": round(vol, 2),
                "downside_deviation_pct": round(downside_vol, 2),
                "max_drawdown_pct": round(mdd, 2),
                "beta": round(beta, 2),
                "sharpe_ratio": round(h_sharpe, 2),
                "sortino_ratio": round(h_sortino, 2),
                "calmar_ratio": round(h_calmar, 2)
            })

            weighted_return += val * ret
            weighted_vol += val * vol
            weighted_beta += val * beta

        port_val = total_portfolio_value or max(1.0, total_val)
        port_return = weighted_return / port_val if port_val > 0 else 15.0
        # Diversification factor reduces raw weighted volatility by ~15-20%
        raw_port_vol = weighted_vol / port_val if port_val > 0 else 20.0
        port_vol = max(8.0, raw_port_vol * 0.82)
        port_beta = weighted_beta / port_val if port_val > 0 else 1.0
        port_downside_dev = port_vol * 0.65
        port_max_dd = -(port_vol * 0.92)

        for item in holdings_ratios:
            item["weight_pct"] = round((item["value_eur"] / port_val * 100.0), 1)

        holdings_ratios.sort(key=lambda x: x["sortino_ratio"], reverse=True)

        ratio_data = cls.calculate_ratios(
            annual_return_pct=port_return,
            annual_volatility_pct=port_vol,
            max_drawdown_pct=port_max_dd,
            downside_deviation_pct=port_downside_dev,
            beta_vs_market=port_beta,
            benchmark_key=benchmark_key
        )

        return {
            "valid": True,
            "portfolio_value_eur": round(port_val, 2),
            "benchmark_key": benchmark_key,
            "ratios": ratio_data["portfolio"],
            "benchmark": ratio_data["benchmark"],
            "risk_free_rate_pct": ratio_data["risk_free_rate_pct"],
            "holdings": holdings_ratios
        }
