"""
Asymmetric Trade Service — High Conviction Setups with Institutional Confluence

Combines:
  1. Market Maker Gamma Exposure (GEX)
  2. Auction Market Theory (Volume Profile POC / VAH / VAL)
  3. Macro Market & Volatility Regime (SPY, QQQ, VIX filter)
  4. Mathematical Asymmetric Risk-Reward: Min 2.5:1 R:R, structural invalidation
  5. Deterministic Confluence Scoring (0-100 pts) & Grading (A+, A, B)
  6. Exact Portfolio Risk Sizing: fixed 0.75%–1.0% account risk ticket
  7. Visual Chart Overlay Coordinate Bundle
  8. Smartphone Telegram Card Formatter
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
from src.market_regime_service import MarketRegimeService
from src.relative_strength_service import RelativeStrengthService
from src.anchored_vwap_service import AnchoredVWAPService
from src.whale_flow_service import WhaleFlowService

logger = logging.getLogger(__name__)

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore


class AsymmetricTradeService:
    def __init__(
        self,
        options_service: Optional[OptionsEdgeService] = None,
        volume_service: Optional[VolumeProfileService] = None,
        regime_service: Optional[MarketRegimeService] = None,
        relative_strength_service: Optional[RelativeStrengthService] = None,
        anchored_vwap_service: Optional[AnchoredVWAPService] = None,
        whale_flow_service: Optional[WhaleFlowService] = None,
    ) -> None:
        self.options_service = options_service or OptionsEdgeService()
        self.volume_service = volume_service or VolumeProfileService()
        self.regime_service = regime_service or MarketRegimeService()
        self.rs_service = relative_strength_service or RelativeStrengthService()
        self.avwap_service = anchored_vwap_service or AnchoredVWAPService()
        self.whale_service = whale_flow_service or WhaleFlowService()

    def generate_trade_setup(
        self,
        ticker: str,
        portfolio_capital: float = 50000.0,
        risk_budget_pct: float = 0.75,
        catalyst_override: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Generates a high-conviction trade setup card combining GEX, Volume Profile,
        Macro Regime, and mathematical 2.5+:1 R:R invalidation levels.
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
            # 3. Fetch Macro Regime
            macro = self.regime_service.get_market_regime()
            # 4. Fetch Relative Strength vs SPY
            rs_data = None
            if self.rs_service and symbol != "SPY":
                try:
                    rs_data = self.rs_service.compute_relative_strength(symbol, benchmark="SPY")
                except Exception:
                    rs_data = None

            # 5. Fetch Anchored VWAPs
            avwap_data = None
            if self.avwap_service:
                try:
                    avwap_data = self.avwap_service.compute_anchored_vwaps(symbol)
                except Exception:
                    avwap_data = None

            # 6. Fetch Whale Flow Activity
            whale_data = None
            if self.whale_service:
                try:
                    whale_data = self.whale_service.analyze_whale_flow(symbol)
                except Exception:
                    whale_data = None

            poc = vp.get("poc_price", spot) if vp else spot
            vah = vp.get("vah_price", spot * 1.03) if vp else spot * 1.03
            val = vp.get("val_price", spot * 0.97) if vp else spot * 0.97
            market_loc = vp.get("market_location", "inside_value_area") if vp else "inside_value_area"

            direction = "LONG"
            setup_name = "Volume Profile Value Rebound"
            catalyst = catalyst_override or "Auction Value Area Support & Institutional Accumulation"

            call_wall = gex.get("call_wall") if gex else None
            put_wall = gex.get("put_wall") if gex else None
            gex_regime = gex.get("regime", "neutral") if gex else "neutral"

            # Structural Invalidation logic:
            # Stop MUST sit below structural support (VAL or POC or retested VAH)
            if market_loc == "above_value_area":
                setup_name = "Value Area High (VAH) Breakout & Expansion"
                catalyst = catalyst_override or "Bullish Value Acceptance > VAH with Volume Expansion"
                invalidation_price = round(vah * 0.985, 2)
                entry_price = round(spot, 2)
            elif market_loc == "inside_value_area" and spot <= poc:
                setup_name = "Value Area Low (VAL) Mean Reversion"
                catalyst = catalyst_override or "Support test at Value Area Low (VAL) rotating back to POC"
                invalidation_price = round(val * 0.98, 2)
                entry_price = round(spot, 2)
            else:
                setup_name = "Point of Control (POC) Structural Continuation"
                catalyst = catalyst_override or "Consolidation around highest liquidity node (POC)"
                invalidation_price = round(min(val, poc * 0.965), 2)
                entry_price = round(spot, 2)

            if invalidation_price >= entry_price:
                invalidation_price = round(entry_price * 0.95, 2)

            risk_per_share = round(entry_price - invalidation_price, 2)
            min_risk = entry_price * 0.015
            max_risk = entry_price * 0.075
            if risk_per_share < min_risk:
                invalidation_price = round(entry_price - min_risk, 2)
                risk_per_share = round(entry_price - invalidation_price, 2)
            elif risk_per_share > max_risk:
                invalidation_price = round(entry_price - max_risk, 2)
                risk_per_share = round(entry_price - invalidation_price, 2)

            # Mathematical Targets: Min 2.0R for Target 1, Min 3.5R for Target 2
            target_1 = round(entry_price + (2.0 * risk_per_share), 2)
            target_2 = round(entry_price + (3.5 * risk_per_share), 2)

            if call_wall and call_wall > target_1:
                target_2 = max(target_2, round(call_wall, 2))

            reward_per_share = round(target_2 - entry_price, 2)
            risk_reward_ratio = round(reward_per_share / risk_per_share, 2) if risk_per_share > 0 else 0.0

            # 4. Position Sizing
            max_risk_amount = portfolio_capital * (risk_budget_pct / 100.0)
            recommended_shares = max(1, int(max_risk_amount / risk_per_share))
            max_capital_allowed = portfolio_capital * 0.20
            if (recommended_shares * entry_price) > max_capital_allowed:
                recommended_shares = max(1, int(max_capital_allowed / entry_price))

            total_position_capital = round(recommended_shares * entry_price, 2)
            actual_risk_amount = round(recommended_shares * risk_per_share, 2)
            actual_risk_pct = round((actual_risk_amount / portfolio_capital) * 100.0, 2)

            # 5. Confluence Scoring & Grading (0 - 100 pts)
            confluence_score = 50
            confluence_factors: List[str] = []

            # Volume Profile Confluence
            if market_loc in ["inside_value_area", "above_value_area"]:
                confluence_score += 10
                confluence_factors.append("Struktur-Support im Volume Profile")
            if abs(spot - val) / spot < 0.035 or abs(spot - poc) / spot < 0.025:
                confluence_score += 15
                confluence_factors.append("Direkter Test von Key-Liquidität (VAL/POC)")

            # Options GEX Confluence
            if gex:
                if gex_regime == "positive_gamma":
                    confluence_score += 15
                    confluence_factors.append("Positives Gamma (Market Maker dämpfen Abverkäufe)")
                if put_wall and abs(spot - put_wall) / spot < 0.05:
                    confluence_score += 10
                    confluence_factors.append("Put Wall Support (Institutioneller Boden)")

            # Risk/Reward Asymmetry
            if risk_reward_ratio >= 3.5:
                confluence_score += 15
                confluence_factors.append(f"Hohe Asymmetrie ({risk_reward_ratio:.1f}:1 R:R)")
            elif risk_reward_ratio >= 2.8:
                confluence_score += 10
                confluence_factors.append(f"Solide Asymmetrie ({risk_reward_ratio:.1f}:1 R:R)")

            # Macro Market Confluence
            regime_stance = macro.get("stance", "RISK_ON")
            if regime_stance == "RISK_ON":
                confluence_score += 10
                confluence_factors.append("Makro-Rückenwind (SPY/QQQ stabil, VIX niedrig)")
            elif regime_stance == "RISK_OFF":
                confluence_score -= 20
                confluence_factors.append("⚠️ Makro-Gegenwind (Markt im Risk-Off Modus)")

            # Relative Strength Confluence vs SPY
            if rs_data:
                mansfield = rs_data.get("mansfield_rs", 0.0)
                alpha_1m = rs_data.get("alpha_1m", 0.0)
                if mansfield >= 5.0 and alpha_1m > 0:
                    confluence_score += 10
                    confluence_factors.append(f"Starke Relative Stärke vs. SPY (Mansfield RS: {mansfield:+.1f}%, Alpha: {alpha_1m:+.1f}%)")
                elif mansfield > 0:
                    confluence_score += 5
                    confluence_factors.append(f"Positive Relative Stärke vs. SPY ({mansfield:+.1f}%)")
                elif mansfield <= -5.0:
                    confluence_score -= 10
                    confluence_factors.append(f"⚠️ Schwächer als der Markt (Mansfield RS: {mansfield:+.1f}%)")

            # Anchored VWAP Confluence
            if avwap_data:
                retests = avwap_data.get("retests", [])
                if retests:
                    confluence_score += 10
                    confluence_factors.append(f"Retest von institutionellem {retests[0]}")
                elif avwap_data.get("institutional_bias") == "BULLISH_ACCEPTANCE":
                    confluence_score += 5
                    confluence_factors.append("Kurs oberhalb YTD & Earnings AVWAP (Fonds im Gewinn)")
                elif avwap_data.get("institutional_bias") == "BEARISH_PRESSURE":
                    confluence_score -= 10
                    confluence_factors.append("⚠️ Unterhalb YTD & Earnings AVWAP (Verkaufsdruck)")

            # Whale Flow / Dark Pool Confluence
            if whale_data and whale_data.get("is_whale_activity"):
                w_pat = whale_data.get("pattern")
                w_ratio = whale_data.get("volume_ratio", 1.0)
                if w_pat == "ACCUMULATION_ABSORPTION":
                    confluence_score += 12
                    confluence_factors.append(f"Whale-Absorption ({w_ratio:.1f}x Volumen am Support absorbiert)")
                elif w_pat == "INSTITUTIONAL_EXPANSION":
                    confluence_score += 10
                    confluence_factors.append(f"Institutioneller Volumenausbruch ({w_ratio:.1f}x Volumen)")
                elif w_pat == "DISTRIBUTION_EXHAUSTION":
                    confluence_score -= 15
                    confluence_factors.append("⚠️ Institutionelle Distribution erkannt (Verkauf in Hype)")

            # Earnings Proximity Shield
            earnings_info = self._check_earnings_proximity(t)
            if earnings_info:
                confluence_score -= 15
                confluence_factors.append(earnings_info["warning"])

            confluence_score = max(10, min(100, confluence_score))
            if confluence_score >= 85:
                grade = "A+"
                grade_badge = "💎 Grade A+"
                grade_title = "Elite Institutional Confluence"
            elif confluence_score >= 70:
                grade = "A"
                grade_badge = "⭐ Grade A"
                grade_title = "Starker Edge Trade"
            else:
                grade = "B"
                grade_badge = "🔹 Grade B"
                grade_title = "Selektiv handeln"

            # 6. Chart Overlay Level Bundle (for PriceChart / Visuals)
            chart_overlay_levels = {
                "poc": poc,
                "vah": vah,
                "val": val,
                "call_wall": call_wall,
                "put_wall": put_wall,
                "ytd_avwap": avwap_data.get("ytd", {}).get("avwap") if avwap_data and avwap_data.get("ytd") else None,
                "earnings_avwap": avwap_data.get("earnings", {}).get("avwap") if avwap_data and avwap_data.get("earnings") else None,
                "entry": entry_price,
                "invalidation": invalidation_price,
                "target_1": target_1,
                "target_2": target_2,
            }

            # 7. Trade Management Guidance
            trade_management = {
                "target_1_action": f"Bei ${target_1:.2f} (2.0R): 50% Teilgewinn sichern, Hard Stop auf Breakeven (${entry_price:.2f}) nachziehen.",
                "target_2_action": f"Bei ${target_2:.2f} (3.5R+): Restposition glattstellen oder Trailing Stop unter 9 EMA führen.",
                "earnings_shield": earnings_info.get("warning") if earnings_info else "Keine Quartalszahlen in den nächsten 5 Tagen.",
            }

            mgmt_text = (
                f"📋 <b>Trade Management & Trailing Stop:</b>\n"
                f"• <b>Ziel 1 (${target_1:.2f}):</b> 50% Teilgewinn & Stop auf Breakeven\n"
                f"• <b>Ziel 2 (${target_2:.2f}):</b> Rest glattstellen oder per 9 EMA Trailing-Stop\n"
            )
            if earnings_info:
                mgmt_text += f"\n{earnings_info['warning']}\n"

            # 8. Format Smartphone Telegram Card
            gex_summary = "N/A (keine US-Optionen)"
            if gex:
                gex_summary = f"{gex.get('regime_label', 'Neutral')} | Call Wall: ${call_wall:.2f} | Put Wall: ${put_wall:.2f}"

            vp_summary = f"POC: ${poc:.2f} | VAH: ${vah:.2f} | VAL: ${val:.2f} ({vp.get('location_label', 'Neutral') if vp else 'N/A'})"
            factors_text = "\n".join([f"  ✓ {f}" for f in confluence_factors])

            tg_html = (
                f"🎯 <b>TRADING EDGE SETUP: {symbol}</b> ({grade_badge})\n"
                f"<b>Typ:</b> {setup_name}\n"
                f"<b>Score:</b> {confluence_score}/100 ({grade_title})\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💡 <b>Katalysator & Logik:</b>\n{catalyst}\n\n"
                f"📊 <b>Konfluenz-Faktoren:</b>\n{factors_text}\n\n"
                f"📈 <b>Institutionelle Level:</b>\n"
                f"• <b>Volume Profile:</b> {vp_summary}\n"
                f"• <b>Optionen GEX:</b> {gex_summary}\n\n"
                f"⚡ <b>Einstieg:</b> ${entry_price:.2f}\n"
                f"🛑 <b>Invalidation (Hard Stop):</b> ${invalidation_price:.2f} (unter Struktur)\n"
                f"🎯 <b>Ziel 1 (2.0R):</b> ${target_1:.2f} (50% Teilgewinn)\n"
                f"🚀 <b>Ziel 2 (3.5R+):</b> ${target_2:.2f} (Runner / Call Wall)\n"
                f"⚖️ <b>Risk/Reward-Ratio:</b> <b>{risk_reward_ratio:.1f} : 1</b>\n\n"
                f"{mgmt_text}\n"
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
                "grade": grade,
                "grade_badge": grade_badge,
                "grade_title": grade_title,
                "confluence_score": confluence_score,
                "confluence_factors": confluence_factors,
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
                "chart_overlay_levels": chart_overlay_levels,
                "trade_management": trade_management,
                "earnings_info": earnings_info,
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
                "macro_regime": {
                    "stance": regime_stance,
                    "vix": macro.get("vix", {}).get("value"),
                },
                "relative_strength": rs_data,
                "anchored_vwap": avwap_data,
                "whale_flow": whale_data,
                "telegram_html": tg_html,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            return ticket

        except Exception as exc:
            logger.error("Failed to generate trade setup for %s: %s", symbol, exc)
            return None

    def _check_earnings_proximity(self, ticker_obj: Any, max_days_warning: int = 5) -> Optional[Dict[str, Any]]:
        """Checks if earnings are scheduled within max_days_warning days."""
        try:
            cal = getattr(ticker_obj, "calendar", None)
            if not cal:
                return None
            earnings_dates = None
            if isinstance(cal, dict):
                earnings_dates = cal.get("Earnings Date")
            elif hasattr(cal, "get"):
                earnings_dates = cal.get("Earnings Date")

            if not earnings_dates:
                return None
            if not isinstance(earnings_dates, (list, tuple)):
                earnings_dates = [earnings_dates]

            today = datetime.now(timezone.utc).date()
            for ed in earnings_dates:
                if hasattr(ed, "date"):
                    ed_date = ed.date()
                elif isinstance(ed, type(today)):
                    ed_date = ed
                else:
                    continue

                diff_days = (ed_date - today).days
                if 0 <= diff_days <= max_days_warning:
                    return {
                        "days_until_earnings": diff_days,
                        "earnings_date": ed_date.isoformat(),
                        "warning": (
                            f"⚠️ Quartalszahlen in {diff_days} Tagen ({ed_date.isoformat()}): "
                            "Hohes Übernacht-Gap- und IV-Crush-Risiko! Vor den Zahlen schließen oder halbieren."
                        ),
                    }
        except Exception as e:
            logger.debug("Earnings proximity check error: %s", e)
        return None
