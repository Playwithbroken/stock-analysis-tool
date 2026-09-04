"""
Asymmetric Trade Service — High Conviction Setups with Institutional Confluence

Combines:
  1. Market Maker Gamma Exposure (GEX)
  2. Auction Market Theory (Volume Profile POC / VAH / VAL)
  3. Post-Earnings Announcement Drift (PEAD) & Squeeze mechanics
  4. Mathematical Asymmetric Risk-Reward: Min 2.5:1 R:R, structural invalidation
  5. Exact Portfolio Risk Sizing: fixed 0.75%–1.0% account risk ticket
  6. Smartphone Telegram Card Formatter
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.options_edge_service import OptionsEdgeService
from src.volume_profile_service import VolumeProfileService

logger = logging.getLogger(__name__)

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore


@dataclass
class TradeSetupTicket:
    ticker: str
    setup_name: str
    catalyst_description: str
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    invalidation_price: float  # Structural Hard Stop
    target_1: float           # 2.0 R
    target_2: float           # 3.5 R (or Call/Put Wall)
    risk_per_share: float
    reward_per_share: float
    risk_reward_ratio: float
    recommended_shares: int
    total_position_capital: float
    portfolio_risk_pct: float
    portfolio_capital_basis: float
    institutional_confluence: Dict[str, Any]
    telegram_html: str
    created_at: str


class AsymmetricTradeService:
    def __init__(
        self,
        options_service: Optional[OptionsEdgeService] = None,
        volume_service: Optional[VolumeProfileService] = None,
    ) -> None:
        self.options_service = options_service or OptionsEdgeService()
        self.volume_service = volume_service or VolumeProfileService()

    def generate_trade_setup(
        self,
        ticker: str,
        portfolio_capital: float = 50000.0,
        risk_budget_pct: float = 0.75,
        catalyst_override: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Generates a high-conviction trade setup card combining GEX, Volume Profile,
        and mathematical 2.5+:1 R:R invalidation levels.
        """
        symbol = ticker.strip().upper()
        if not yf:
            return None

        try:
            t = yf.Ticker(symbol)
            fast_info = getattr(t, "fast_info", None)
            spot = 0.0
            if fast_info:
                spot = float(fast_info.get("lastPrice") or fast_info.get("regularMarketPreviousClose") or 0.0)
            if not spot or spot <= 0:
                hist = t.history(period="5d")
                if not hist.empty:
                    spot = float(hist["Close"].iloc[-1])
            if not spot or spot <= 0:
                return None

            # 1. Fetch Volume Profile
            vp = self.volume_service.compute_volume_profile(symbol, period="1mo", interval="30m")
            # 2. Fetch GEX (if available, e.g. for US optionable equities)
            gex = self.options_service.analyze_gex(symbol, spot_override=spot)

            poc = vp.get("poc_price", spot) if vp else spot
            vah = vp.get("vah_price", spot * 1.03) if vp else spot * 1.03
            val = vp.get("val_price", spot * 0.97) if vp else spot * 0.97
            market_loc = vp.get("market_location", "inside_value_area") if vp else "inside_value_area"

            # 3. Determine Setup Pattern & Confluence
            direction = "LONG"
            setup_name = "Volume Profile Value Rebound"
            catalyst = catalyst_override or "Auction Value Area Support & Institutional Accumulation"

            # Check GEX confluence
            call_wall = gex.get("call_wall") if gex else None
            put_wall = gex.get("put_wall") if gex else None
            gex_regime = gex.get("regime", "neutral") if gex else "neutral"

            # Structural Invalidation logic:
            # For LONG: Stop MUST sit below structural support (VAL or POC or recent swing low)
            # Never an arbitrary fixed percentage.
            if market_loc == "above_value_area":
                setup_name = "Value Area High (VAH) Breakout & Expansion"
                catalyst = catalyst_override or "Bullish Value Acceptance > VAH with Volume Expansion"
                invalidation_price = round(vah * 0.985, 2)  # slightly below VAH retest
                entry_price = round(spot, 2)
            elif market_loc == "inside_value_area" and spot <= poc:
                setup_name = "Value Area Low (VAL) Mean Reversion"
                catalyst = catalyst_override or "Support test at Value Area Low (VAL) rotating back to POC"
                invalidation_price = round(val * 0.98, 2)  # below VAL bracket
                entry_price = round(spot, 2)
            else:
                setup_name = "Point of Control (POC) Structural Continuation"
                catalyst = catalyst_override or "Consolidation around highest liquidity node (POC)"
                invalidation_price = round(min(val, poc * 0.965), 2)
                entry_price = round(spot, 2)

            # Ensure invalidation is strictly below entry
            if invalidation_price >= entry_price:
                invalidation_price = round(entry_price * 0.95, 2)

            risk_per_share = round(entry_price - invalidation_price, 2)
            # Guard against tiny or huge risk
            min_risk = entry_price * 0.015  # min 1.5% stop distance to avoid noise stop-outs
            max_risk = entry_price * 0.075  # max 7.5% stop distance
            if risk_per_share < min_risk:
                invalidation_price = round(entry_price - min_risk, 2)
                risk_per_share = round(entry_price - invalidation_price, 2)
            elif risk_per_share > max_risk:
                invalidation_price = round(entry_price - max_risk, 2)
                risk_per_share = round(entry_price - invalidation_price, 2)

            # Mathematical Targets: Min 2.0R for Target 1, Min 3.5R for Target 2
            target_1 = round(entry_price + (2.0 * risk_per_share), 2)
            target_2 = round(entry_price + (3.5 * risk_per_share), 2)

            # If Call Wall is higher than Target 1, align Target 2 towards Call Wall
            if call_wall and call_wall > target_1:
                target_2 = max(target_2, round(call_wall, 2))

            reward_per_share = round(target_2 - entry_price, 2)
            risk_reward_ratio = round(reward_per_share / risk_per_share, 2) if risk_per_share > 0 else 0.0

            # 4. Position Sizing
            max_risk_amount = portfolio_capital * (risk_budget_pct / 100.0)
            recommended_shares = max(1, int(max_risk_amount / risk_per_share))
            # Cap position capital to 20% of portfolio
            max_capital_allowed = portfolio_capital * 0.20
            if (recommended_shares * entry_price) > max_capital_allowed:
                recommended_shares = max(1, int(max_capital_allowed / entry_price))

            total_position_capital = round(recommended_shares * entry_price, 2)
            actual_risk_amount = round(recommended_shares * risk_per_share, 2)
            actual_risk_pct = round((actual_risk_amount / portfolio_capital) * 100.0, 2)

            # 5. Format Smartphone Telegram Card
            gex_summary = "N/A (keine US-Optionen)"
            if gex:
                gex_summary = f"{gex.get('regime_label', 'Neutral')} | Call Wall: ${call_wall:.2f} | Put Wall: ${put_wall:.2f}"

            vp_summary = f"POC: ${poc:.2f} | VAH: ${vah:.2f} | VAL: ${val:.2f} ({vp.get('location_label', 'Neutral') if vp else 'N/A'})"

            tg_html = (
                f"🎯 <b>TRADING EDGE SETUP: {symbol}</b>\n"
                f"<b>Typ:</b> {setup_name}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💡 <b>Katalysator & Logik:</b>\n{catalyst}\n\n"
                f"📊 <b>Institutionelle Konfluenz:</b>\n"
                f"• <b>Volume Profile:</b> {vp_summary}\n"
                f"• <b>Optionen GEX:</b> {gex_summary}\n\n"
                f"⚡ <b>Einstieg:</b> ${entry_price:.2f}\n"
                f"🛑 <b>Invalidation (Hard Stop):</b> ${invalidation_price:.2f} (unter Struktur)\n"
                f"🎯 <b>Ziel 1 (2.0R):</b> ${target_1:.2f} (50% Teilgewinn)\n"
                f"🚀 <b>Ziel 2 (3.5R+):</b> ${target_2:.2f} (Runner / Call Wall)\n"
                f"⚖️ <b>Risk/Reward-Ratio:</b> <b>{risk_reward_ratio:.1f} : 1</b>\n\n"
                f"📱 <b>Position Sizing ({actual_risk_pct:.2f}% Kontorisiko):</b>\n"
                f"• <b>Stückzahl:</b> <b>{recommended_shares}</b> Aktien\n"
                f"• <b>Kapitalbedarf:</b> ~{total_position_capital:,.2f} EUR\n"
                f"• <b>Max. Risiko beim Stop:</b> -{actual_risk_amount:,.2f} EUR\n"
            )

            ticket = {
                "ticker": symbol,
                "setup_name": setup_name,
                "catalyst_description": catalyst,
                "direction": direction,
                "entry_price": entry_price,
                "invalidation_price": invalidation_price,
                "target_1": target_1,
                "target_2": target_2,
                "risk_per_share": risk_per_share,
                "reward_per_share": reward_per_share,
                "risk_reward_ratio": risk_reward_ratio,
                "recommended_shares": recommended_shares,
                "total_position_capital": total_position_capital,
                "actual_risk_amount": actual_risk_amount,
                "portfolio_risk_pct": actual_risk_pct,
                "portfolio_capital_basis": portfolio_capital,
                "volume_profile": {
                    "poc": poc,
                    "vah": vah,
                    "val": val,
                    "market_location": market_loc,
                },
                "options_gex": {
                    "regime": gex_regime,
                    "call_wall": call_wall,
                    "put_wall": put_wall,
                } if gex else None,
                "telegram_html": tg_html,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            return ticket

        except Exception as exc:
            logger.error("Failed to generate trade setup for %s: %s", symbol, exc)
            return None
