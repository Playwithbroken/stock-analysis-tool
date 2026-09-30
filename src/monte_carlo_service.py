"""
Monte Carlo Portfolio Wealth Simulator & Sequence-of-Returns Risk Engine
Simulates 1,000 to 10,000 dynamic geometric Brownian motion wealth paths with
monthly contributions, inflation adjustments, retirement withdrawals, and ruin probabilities.
"""

from typing import Dict, Any, List, Optional
import math
import numpy as np


class MonteCarloSimulator:
    """
    High-performance stochastic Monte Carlo wealth simulator.
    """

    @staticmethod
    def infer_portfolio_profile(holdings: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Infers expected annual return and volatility from current portfolio holdings.
        Falls back to diversified market baseline if holdings are sparse.
        """
        if not holdings:
            return {
                "expected_return": 0.08,   # 8.0% p.a.
                "volatility": 0.16,        # 16.0% p.a.
                "total_value": 0.0
            }

        total_value = 0.0
        weighted_return = 0.0
        weighted_volatility = 0.0

        for h in holdings:
            val = float(h.get("total_value", 0.0) or 0.0)
            if val <= 0:
                shares = float(h.get("shares", 0.0) or 0.0)
                price = float(h.get("current_price", 0.0) or 0.0)
                val = shares * price
            total_value += val

            # Estimate asset volatility & return based on asset class/name/score
            asset_type = str(h.get("asset_type", "stock")).lower()
            score = float(h.get("score", 50) or 50)

            if "etf" in asset_type or "msci" in str(h.get("name", "")).lower():
                exp_ret = 0.075
                vol = 0.14
            elif "bond" in asset_type or "anleihe" in str(h.get("name", "")).lower():
                exp_ret = 0.038
                vol = 0.06
            elif "crypto" in asset_type:
                exp_ret = 0.14
                vol = 0.65
            else:
                # Individual stock
                # High-score quality stocks tend to have slightly better risk-adjusted profiles
                exp_ret = 0.085 + (score - 50) * 0.0006
                vol = 0.22 - (score - 50) * 0.0008

            weighted_return += val * exp_ret
            weighted_volatility += val * vol

        if total_value > 0:
            final_return = max(0.02, min(0.25, weighted_return / total_value))
            # Apply diversification factor (cross-correlation discount to individual volatilities)
            num_assets = max(1, len(holdings))
            div_discount = max(0.70, 1.0 - 0.03 * math.sqrt(num_assets))
            final_vol = max(0.05, min(0.40, (weighted_volatility / total_value) * div_discount))
        else:
            final_return = 0.08
            final_vol = 0.16

        return {
            "expected_return": round(final_return, 4),
            "volatility": round(final_vol, 4),
            "total_value": round(total_value, 2)
        }

    @staticmethod
    def simulate(
        initial_wealth: float,
        annual_return: float = 0.08,
        annual_volatility: float = 0.16,
        monthly_savings: float = 500.0,
        monthly_withdrawal: float = 0.0,
        horizon_years: int = 20,
        inflation_rate: float = 0.02,
        target_wealth: float = 1000000.0,
        num_simulations: int = 2000,
        withdrawal_inflation_adjusted: bool = True,
        seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Executes a vectorized Monte Carlo simulation with monthly time-steps.
        """
        if seed is not None:
            np.random.seed(seed)

        # Sanitize and clamp inputs
        initial_wealth = max(0.0, float(initial_wealth))
        annual_return = max(-0.20, min(0.50, float(annual_return)))
        annual_volatility = max(0.01, min(1.0, float(annual_volatility)))
        monthly_savings = max(0.0, float(monthly_savings))
        monthly_withdrawal = max(0.0, float(monthly_withdrawal))
        horizon_years = max(1, min(50, int(horizon_years)))
        inflation_rate = max(0.0, min(0.20, float(inflation_rate)))
        target_wealth = max(100.0, float(target_wealth))
        num_simulations = max(100, min(10000, int(num_simulations)))

        dt = 1.0 / 12.0  # Monthly intervals
        total_months = horizon_years * 12

        # Monthly drift and diffusion
        monthly_drift = (annual_return - 0.5 * (annual_volatility ** 2)) * dt
        monthly_diffusion = annual_volatility * math.sqrt(dt)

        # Generate standard normal shocks: shape (num_simulations, total_months)
        z = np.random.normal(0.0, 1.0, size=(num_simulations, total_months))

        # Track paths: shape (num_simulations, total_months + 1)
        paths = np.zeros((num_simulations, total_months + 1), dtype=np.float64)
        paths[:, 0] = initial_wealth

        current_wealth = np.full(num_simulations, initial_wealth, dtype=np.float64)
        ever_reached_target = np.zeros(num_simulations, dtype=bool)
        ruined = np.zeros(num_simulations, dtype=bool)

        if initial_wealth >= target_wealth:
            ever_reached_target[:] = True

        monthly_inflation_factor = (1.0 + inflation_rate) ** (1.0 / 12.0)

        for m in range(total_months):
            # Active (solvent) paths
            alive_mask = current_wealth > 0

            # Determine inflation adjusted withdrawal for this month
            if withdrawal_inflation_adjusted and inflation_rate > 0:
                cur_withdrawal = monthly_withdrawal * (monthly_inflation_factor ** m)
            else:
                cur_withdrawal = monthly_withdrawal

            net_cashflow = monthly_savings - cur_withdrawal

            # Growth factor for alive paths
            growth = np.exp(monthly_drift + monthly_diffusion * z[:, m])

            # Apply market shock to invested capital, then add net cashflow
            current_wealth[alive_mask] = (current_wealth[alive_mask] * growth[alive_mask]) + net_cashflow

            # Depleted paths clamp to 0 and remain ruined
            ruined = ruined | (current_wealth <= 0)
            current_wealth[current_wealth < 0] = 0.0

            # Check target achievement
            ever_reached_target = ever_reached_target | (current_wealth >= target_wealth)

            paths[:, m + 1] = current_wealth

        # Percentile slices for every year (month 0, 12, 24, ..., total_months)
        yearly_month_indices = [y * 12 for y in range(horizon_years + 1)]
        yearly_paths = paths[:, yearly_month_indices]  # (num_simulations, horizon_years + 1)

        p10 = np.percentile(yearly_paths, 10, axis=0)
        p25 = np.percentile(yearly_paths, 25, axis=0)
        p50 = np.percentile(yearly_paths, 50, axis=0)
        p75 = np.percentile(yearly_paths, 75, axis=0)
        p90 = np.percentile(yearly_paths, 90, axis=0)
        means = np.mean(yearly_paths, axis=0)

        # Calculate survival rate (fraction of paths > 0) per year
        survival_rates = np.mean(yearly_paths > 0, axis=0) * 100.0

        # Build trajectory array
        annual_trajectories = []
        for yr, idx in enumerate(range(horizon_years + 1)):
            inf_discount = (1.0 + inflation_rate) ** yr

            nominal_entry = {
                "p10": round(float(p10[idx]), 2),
                "p25": round(float(p25[idx]), 2),
                "p50": round(float(p50[idx]), 2),
                "p75": round(float(p75[idx]), 2),
                "p90": round(float(p90[idx]), 2),
                "mean": round(float(means[idx]), 2),
            }

            real_entry = {
                "p10": round(float(p10[idx] / inf_discount), 2),
                "p25": round(float(p25[idx] / inf_discount), 2),
                "p50": round(float(p50[idx] / inf_discount), 2),
                "p75": round(float(p75[idx] / inf_discount), 2),
                "p90": round(float(p90[idx] / inf_discount), 2),
                "mean": round(float(means[idx] / inf_discount), 2),
            }

            annual_trajectories.append({
                "year": yr,
                "nominal": nominal_entry,
                "real": real_entry,
                "survival_rate": round(float(survival_rates[idx]), 1)
            })

        # Summary KPIs
        final_values = paths[:, -1]
        final_inf_discount = (1.0 + inflation_rate) ** horizon_years

        total_contributions = monthly_savings * total_months
        total_withdrawals = monthly_withdrawal * total_months

        target_success_prob = float(np.mean(final_values >= target_wealth) * 100.0)
        target_ever_reached_prob = float(np.mean(ever_reached_target) * 100.0)
        ruin_prob = float(np.mean(ruined) * 100.0)

        median_final = float(np.median(final_values))
        real_median_final = float(median_final / final_inf_discount)

        # Estimate Safe Withdrawal Rate (SWR) for this portfolio & horizon
        # Trinity study benchmark adjusted for volatility and horizon
        safe_withdrawal_rate_pct = max(0.02, min(0.065, 0.045 - 0.0005 * (horizon_years - 30) - 0.02 * (annual_volatility - 0.15)))
        safe_annual_withdrawal = initial_wealth * safe_withdrawal_rate_pct
        safe_monthly_withdrawal = round(safe_annual_withdrawal / 12.0, 2)

        # Sequence of Returns Stress Scenarios
        # Scenario A: Early Crash (-30% in year 1, then median recovery)
        early_crash_wealth = initial_wealth * 0.70
        for m in range(total_months):
            if early_crash_wealth <= 0:
                early_crash_wealth = 0.0
                break
            early_crash_wealth = early_crash_wealth * (1.0 + annual_return * dt) + (monthly_savings - monthly_withdrawal)

        # Scenario B: Smooth linear compounding
        linear_wealth = initial_wealth
        for m in range(total_months):
            linear_wealth = linear_wealth * (1.0 + annual_return * dt) + (monthly_savings - monthly_withdrawal)
            if linear_wealth <= 0:
                linear_wealth = 0.0
                break

        return {
            "parameters": {
                "initial_wealth": initial_wealth,
                "annual_return": annual_return,
                "annual_volatility": annual_volatility,
                "monthly_savings": monthly_savings,
                "monthly_withdrawal": monthly_withdrawal,
                "horizon_years": horizon_years,
                "inflation_rate": inflation_rate,
                "target_wealth": target_wealth,
                "num_simulations": num_simulations,
                "withdrawal_inflation_adjusted": withdrawal_inflation_adjusted
            },
            "summary": {
                "median_final_wealth": round(median_final, 2),
                "real_median_final_wealth": round(real_median_final, 2),
                "p10_final_wealth": round(float(np.percentile(final_values, 10)), 2),
                "p25_final_wealth": round(float(np.percentile(final_values, 25)), 2),
                "p75_final_wealth": round(float(np.percentile(final_values, 75)), 2),
                "p90_final_wealth": round(float(np.percentile(final_values, 90)), 2),
                "target_probability": round(target_success_prob, 1),
                "target_ever_reached_probability": round(target_ever_reached_prob, 1),
                "ruin_probability": round(ruin_prob, 1),
                "survival_probability": round(100.0 - ruin_prob, 1),
                "total_contributions": round(total_contributions, 2),
                "total_withdrawals": round(total_withdrawals, 2),
                "median_net_profit": round(median_final - (initial_wealth + total_contributions), 2),
                "safe_withdrawal_rate_pct": round(safe_withdrawal_rate_pct * 100.0, 2),
                "safe_monthly_withdrawal": safe_monthly_withdrawal
            },
            "annual_trajectories": annual_trajectories,
            "stress_tests": {
                "early_crash_final_wealth": round(max(0.0, early_crash_wealth), 2),
                "deterministic_linear_wealth": round(max(0.0, linear_wealth), 2),
                "sorr_risk_delta": round(max(0.0, linear_wealth - early_crash_wealth), 2)
            }
        }
