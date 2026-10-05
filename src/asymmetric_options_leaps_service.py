"""
Asymmetric Options & LEAPS Strategy Service
Implements institutional Stock Replacement & Deep-In-The-Money LEAPS (Delta ~0.80)
for asymmetric multi-bagger wealth compounding with capped downside risk.
"""

from __future__ import annotations

import logging
import math
from typing import Dict, Any, List, Optional
from src.options_service import BlackScholesEngine

logger = logging.getLogger(__name__)


class AsymmetricOptionsLeapsService:
    """
    Calculates high-leverage, risk-capped LEAPS (Long-Term Equity Anticipation Securities)
    as a stock replacement strategy for high-conviction quality compounders.
    """

    def __init__(self, risk_free_rate: float = 0.045) -> None:
        self.risk_free_rate = risk_free_rate

    def calculate_leaps_strategy(
        self,
        ticker: str,
        spot_price: float,
        annual_iv: float = 0.32,
        target_dte: int = 450,
        target_delta: float = 0.80,
    ) -> Dict[str, Any]:
        """
        Calculates optimal DITM LEAPS call parameters:
        - Target Delta: ~0.80 (replicates 80% of stock movement with 25-35% of capital)
        - Expiration: ~12 to 18 months (450 DTE) to minimize theta decay
        """
        S = float(spot_price)
        if S <= 0:
            raise ValueError(f"Invalid spot price: {S}")

        T = target_dte / 365.0
        sigma = max(0.10, annual_iv)
        r = self.risk_free_rate

        # Iterate strikes below spot to find strike closest to target_delta (~0.80)
        # Deep in the money strike is typically 80% to 85% of spot
        best_strike = round(S * 0.80, 2)
        best_delta = 0.80
        best_diff = 999.0

        step = 1.0 if S < 50 else (2.5 if S < 200 else 5.0)
        min_k = S * 0.65
        max_k = S * 0.95

        k = round(min_k / step) * step
        while k <= max_k:
            d = BlackScholesEngine.call_delta(S, k, T, r, sigma)
            diff = abs(d - target_delta)
            if diff < best_diff:
                best_diff = diff
                best_strike = k
                best_delta = d
            k += step

        call_premium = BlackScholesEngine.call_price(S, best_strike, T, r, sigma)
        intrinsic_val = max(0.0, S - best_strike)
        extrinsic_val = max(0.0, call_premium - intrinsic_val)
        breakeven_price = best_strike + call_premium
        breakeven_pct = ((breakeven_price - S) / S) * 100.0

        # Capital required for 1 contract (100 shares equivalent)
        capital_leaps_100 = call_premium * 100.0
        capital_shares_100 = S * 100.0
        capital_saved_pct = (1.0 - (call_premium / S)) * 100.0

        # Effective leverage = (S * Delta) / Premium
        effective_leverage = (S * best_delta) / call_premium if call_premium > 0 else 1.0

        # Scenario Matrix (+20%, +50%, +100%, -25% at expiration)
        scenarios = []
        for stock_move in [0.20, 0.50, 1.00, -0.25]:
            future_s = S * (1.0 + stock_move)
            future_opt_val = max(0.0, future_s - best_strike)
            opt_pnl = future_opt_val - call_premium
            opt_return_pct = (opt_pnl / call_premium) * 100.0
            stock_return_pct = stock_move * 100.0
            scenarios.append({
                "stock_change_pct": round(stock_return_pct, 1),
                "stock_target_price": round(future_s, 2),
                "leaps_value": round(future_opt_val, 2),
                "leaps_return_pct": round(opt_return_pct, 1),
                "alpha_multiplier": round(opt_return_pct / stock_return_pct, 1) if stock_return_pct != 0 else 0.0,
            })

        return {
            "ticker": ticker.upper().strip(),
            "spot_price": round(S, 2),
            "target_dte": target_dte,
            "annual_iv_pct": round(sigma * 100, 1),
            "optimal_strike": round(best_strike, 2),
            "delta": round(best_delta, 3),
            "call_premium": round(call_premium, 2),
            "intrinsic_value": round(intrinsic_val, 2),
            "extrinsic_value": round(extrinsic_val, 2),
            "breakeven_price": round(breakeven_price, 2),
            "breakeven_pct": round(breakeven_pct, 1),
            "capital_leaps_100": round(capital_leaps_100, 2),
            "capital_shares_100": round(capital_shares_100, 2),
            "capital_saved_pct": round(capital_saved_pct, 1),
            "effective_leverage": round(effective_leverage, 2),
            "scenarios": scenarios,
        }

    def format_telegram_leaps_card(self, data: Dict[str, Any]) -> str:
        """Formats the LEAPS strategy into a concise institutional telegram card."""
        tk = data["ticker"]
        spot = data["spot_price"]
        strike = data["optimal_strike"]
        delta = data["delta"]
        premium = data["call_premium"]
        dte = data["target_dte"]
        lev = data["effective_leverage"]
        saved = data["capital_saved_pct"]
        be = data["breakeven_price"]
        be_pct = data["breakeven_pct"]

        is_eu = any(tk.endswith(sfx) for sfx in [".DE", ".F", ".AS", ".PA", ".MI", ".MC"])
        c = "€" if is_eu else "$"

        sc_lines = []
        for s in data["scenarios"]:
            sgn = "+" if s["stock_change_pct"] > 0 else ""
            opt_sgn = "+" if s["leaps_return_pct"] > 0 else ""
            sc_lines.append(
                f"  • Aktie {sgn}{s['stock_change_pct']}% ({c}{s['stock_target_price']:.2f}) ➔ LEAPS <b>{opt_sgn}{s['leaps_return_pct']}%</b>"
            )

        return (
            f"🚀 <b>LEAPS ASYMMETRIE-RECHNER: {tk}</b>\n"
            f"<i>Stock Replacement Strategy (Deep-in-the-Money Call)</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Spot-Kurs:</b> {c}{spot:.2f}\n"
            f"• <b>Empfohlener Strike:</b> <b>{c}{strike:.2f} Call</b> (Delta <b>{delta:.2f}</b>)\n"
            f"• <b>Laufzeit:</b> ~{dte} Tage (12-15 Monate / minimaler Theta-Zerfall)\n"
            f"• <b>Prämie (Fair Value):</b> <b>{c}{premium:.2f}</b> pro Aktie ({c}{premium*100:,.0f} pro Kontrakt)\n"
            f"• <b>Breakeven bei Verfall:</b> {c}{be:.2f} (+{be_pct:.1f}%)\n"
            f"• <b>Effektiver Hebel:</b> <b>{lev:.1f}x Hebelwirkung</b>\n"
            f"• <b>Kapitalersparnis:</b> <b>{saved:.1f}%</b> weniger Kapital gebunden als bei 100 Aktien!\n\n"
            f"📈 <b>Rendite-Hebel Szenarien:</b>\n"
            + "\n".join(sc_lines) + "\n\n"
            f"🛡️ <b>Asymmetrischer Vorteil:</b>\n"
            f"Maximales Risiko ist auf die bezahlte Prämie begrenzt. <b>Keine Nachschusspflicht, kein Margin Call, kein Liquidierungsrisiko.</b>"
        )


_leaps_service_instance: Optional[AsymmetricOptionsLeapsService] = None

def get_asymmetric_options_leaps_service() -> AsymmetricOptionsLeapsService:
    global _leaps_service_instance
    if _leaps_service_instance is None:
        _leaps_service_instance = AsymmetricOptionsLeapsService()
    return _leaps_service_instance
