"""
Institutional Position Sizing & Kelly Criterion Engine

Calculates mathematical position sizing, capital allocation, and risk limits:
  1. Fixed Fractional Risk (e.g. 0.5% - 2.0% per trade).
  2. Half-Kelly & Quarter-Kelly optimal risk percentage.
  3. Strict portfolio heat limits (max 2.50% total equity at risk).
  4. Realistisches Slippage- & Spread-Modell (Gross PnL vs. Net PnL).
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class PositionSizingService:
    def __init__(self, default_capital: float = 50000.0, max_portfolio_heat: float = 2.50) -> None:
        self.default_capital = default_capital
        self.max_portfolio_heat = max_portfolio_heat

    @staticmethod
    def is_european_ticker(ticker: str) -> bool:
        sym = ticker.upper().strip()
        return any(sym.endswith(sfx) for sfx in [".DE", ".F", ".AS", ".PA", ".MI", ".MC"])

    def calculate_sizing(
        self,
        ticker: str,
        entry_price: float,
        stop_price: float,
        target_1: float,
        target_2: Optional[float] = None,
        capital: float = 50000.0,
        risk_pct: float = 0.75,
        win_rate: float = 0.60,
        reward_risk_ratio: float = 2.0,
        current_portfolio_heat: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Calculates position size, share count, monetary risk, and Kelly criterion guidance.
        """
        ticker = ticker.upper().strip()
        capital = max(1000.0, float(capital))
        risk_pct = max(0.1, min(float(risk_pct), 5.0))
        entry_price = max(0.01, float(entry_price))
        stop_price = max(0.01, float(stop_price))

        risk_per_share = abs(entry_price - stop_price)
        if risk_per_share <= 0:
            risk_per_share = entry_price * 0.03

        # Currency
        is_eu = self.is_european_ticker(ticker)
        currency = "EUR" if is_eu else ("GBP" if ticker.endswith(".L") else "USD")
        curr_sym = "€" if currency == "EUR" else ("£" if currency == "GBP" else "$")

        # 1. Fixed Fractional Risk Budget
        risk_budget = round(capital * (risk_pct / 100.0), 2)
        shares = max(1, int(risk_budget // risk_per_share))
        pos_value = round(shares * entry_price, 2)
        capital_alloc_pct = round((pos_value / capital) * 100.0, 2)
        actual_risk_amount = round(shares * risk_per_share, 2)
        actual_risk_pct = round((actual_risk_amount / capital) * 100.0, 2)

        # 2. Target 1 & Target 2 Projected Profit
        target_1_profit = round(shares * abs(target_1 - entry_price), 2) if target_1 > 0 else 0.0
        target_2_profit = round(shares * abs(target_2 - entry_price), 2) if target_2 and target_2 > 0 else 0.0

        # 3. Realistic Friction Model (Spread + Slippage + Commission)
        # European stocks: 0.08% spread + 0.03% slippage + 1.00 € commission per leg
        # US stocks: 0.04% spread + 0.02% slippage + 0.00 $ commission
        spread_pct = 0.08 if is_eu else 0.04
        slippage_pct = 0.03 if is_eu else 0.02
        commission_leg = 1.0 if is_eu else 0.0

        friction_entry = (pos_value * ((spread_pct / 2.0 + slippage_pct) / 100.0)) + commission_leg
        friction_exit_target1 = ((shares * target_1) * ((spread_pct / 2.0 + slippage_pct) / 100.0)) + commission_leg
        total_roundtrip_friction = round(friction_entry + friction_exit_target1, 2)
        net_target_1_profit = round(max(0.0, target_1_profit - total_roundtrip_friction), 2)

        # 4. Kelly Criterion Calculations
        # Full Kelly = W - (1 - W) / R
        w = max(0.1, min(win_rate, 0.95))
        r = max(0.5, reward_risk_ratio)
        full_kelly = w - ((1.0 - w) / r)
        full_kelly_pct = round(max(0.0, full_kelly * 100.0), 2)
        half_kelly_pct = round(full_kelly_pct / 2.0, 2)
        quarter_kelly_pct = round(full_kelly_pct / 4.0, 2)

        # Guidance
        if risk_pct > half_kelly_pct and half_kelly_pct > 0:
            kelly_verdict = "⚠️ ÜBER HALF-KELLY"
            kelly_note = f"Gewähltes Risiko ({risk_pct:.2f}%) liegt über dem sicheren Half-Kelly-Limit ({half_kelly_pct:.2f}%)."
        else:
            kelly_verdict = "🟢 IM KELLY-SICHERHEITSBEREICH"
            kelly_note = f"Risiko ist optimal durch Half-Kelly ({half_kelly_pct:.2f}%) abgesichert."

        # 5. Portfolio Heat Check
        projected_heat = round(current_portfolio_heat + actual_risk_pct, 2)
        heat_warning = projected_heat > self.max_portfolio_heat

        return {
            "ticker": ticker,
            "currency": currency,
            "currency_symbol": curr_sym,
            "capital": capital,
            "risk_pct_selected": risk_pct,
            "entry_price": entry_price,
            "stop_price": stop_price,
            "target_1": target_1,
            "target_2": target_2,
            "risk_per_share": round(risk_per_share, 2),
            "recommended_shares": shares,
            "position_value": pos_value,
            "capital_allocation_pct": capital_alloc_pct,
            "max_risk_amount": actual_risk_amount,
            "actual_risk_pct": actual_risk_pct,
            "target_1_profit_gross": target_1_profit,
            "target_1_profit_net": net_target_1_profit,
            "target_2_profit": target_2_profit,
            "friction_cost_est": total_roundtrip_friction,
            "friction_breakdown": {
                "spread_pct": spread_pct,
                "slippage_pct": slippage_pct,
                "commission_per_leg": commission_leg,
            },
            "kelly_analysis": {
                "win_rate_assumed": round(w * 100.0, 1),
                "reward_to_risk": round(r, 2),
                "full_kelly_pct": full_kelly_pct,
                "half_kelly_pct": half_kelly_pct,
                "quarter_kelly_pct": quarter_kelly_pct,
                "verdict": kelly_verdict,
                "note": kelly_note,
            },
            "portfolio_heat": {
                "current_heat_pct": current_portfolio_heat,
                "projected_heat_pct": projected_heat,
                "max_heat_pct": self.max_portfolio_heat,
                "is_overheated": heat_warning,
            },
        }

    def format_telegram_sizing_card(self, sizing: Dict[str, Any]) -> str:
        """Formats the position sizing & Kelly recommendation card for Telegram."""
        ticker = sizing["ticker"]
        sym = sizing["currency_symbol"]
        shares = sizing["recommended_shares"]
        pos_val = sizing["position_value"]
        alloc = sizing["capital_allocation_pct"]
        risk_eur = sizing["max_risk_amount"]
        risk_pct = sizing["actual_risk_pct"]
        t1_gross = sizing["target_1_profit_gross"]
        t1_net = sizing["target_1_profit_net"]
        fric = sizing["friction_cost_est"]
        kelly = sizing["kelly_analysis"]
        heat = sizing["portfolio_heat"]

        heat_str = "🔴 LIMIT ÜBERSCHRITTEN" if heat["is_overheated"] else "🟢 SAFE"

        lines = [
            f"⚖️ <b>POSITION SIZING &amp; KELLY ENGINE: {ticker}</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"• <b>Kapitalbasis:</b> {sym}{sizing['capital']:,.0f} | <b>Risiko:</b> {risk_pct:.2f}%",
            f"• <b>Order-Empfehlung:</b> <b>{shares} Stück</b> (~{sym}{pos_val:,.2f} / {alloc:.1f}% Depot)",
            f"• <b>Maximaler Verlust (Stop-Out):</b> -{sym}{risk_eur:,.2f} (-{risk_pct:.2f}%)\n",
            f"🎯 <b>Gewinnerwartung &amp; Realistische Reibung:</b>",
            f"• <b>Ziel 1 Brutto-Gewinn (2.0R):</b> +{sym}{t1_gross:,.2f}",
            f"• <b>Geschätzte Slippage &amp; Spreads:</b> -{sym}{fric:.2f}",
            f"• <b>Ziel 1 Netto-Gewinn:</b> <b>+{sym}{t1_net:,.2f}</b>\n",
            f"🧠 <b>Kelly-Kriterium &amp; Portfolio Heat:</b>",
            f"• <b>Half-Kelly Limit:</b> <b>{kelly['half_kelly_pct']:.2f}%</b> ({kelly['verdict']})",
            f"• <b>Portfolio Heat:</b> {heat['current_heat_pct']:.2f}% ➔ <b>{heat['projected_heat_pct']:.2f}%</b> (Max {heat['max_heat_pct']:.2f}%) [{heat_str}]\n",
            f"💡 <i>Tipp: Buche diese Stückzahl direkt mit <code>/paper {ticker}</code> ins Demokonto ein.</i>"
        ]
        return "\n".join(lines)
