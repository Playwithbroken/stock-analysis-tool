"""
Opening Range Breakout (ORB) Scanner & Engine

Analyzes the initial 15-minute and 30-minute cash-session range (High/Low)
for European (XETRA 09:00-09:30 CET) and US (15:30-16:00 CET) equities.
Detects high-momentum breakouts confirmed by Relative Volume (RV > 1.25).
"""
from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore


class OpeningRangeBreakoutService:
    def __init__(self, cache_ttl_seconds: int = 300) -> None:
        self.cache_ttl = cache_ttl_seconds
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    def is_european_ticker(self, ticker: str) -> bool:
        sym = ticker.upper().strip()
        return any(sym.endswith(sfx) for sfx in [".DE", ".F", ".AS", ".PA", ".MI", ".MC"])

    def analyze_orb(self, ticker: str, or_minutes: int = 30) -> Optional[Dict[str, Any]]:
        """
        Calculates Opening Range (High, Low, Mid) and checks breakout status.
        or_minutes: 15 or 30 minutes.
        """
        ticker = ticker.upper().strip()
        if not ticker or not yf:
            return None

        cache_key = f"{ticker}:{or_minutes}"
        cached = self._cache.get(cache_key)
        if cached and (time.time() - cached[0]) < self.cache_ttl:
            return cached[1]

        try:
            t = yf.Ticker(ticker)
            # Fetch intraday 5m data for the last 5 days
            df = t.history(period="5d", interval="5m")
            if df.empty or len(df) < 6:
                return None

            # Determine trading days
            df = df.copy()
            df["Date"] = df.index.date
            unique_dates = df["Date"].unique()
            if len(unique_dates) == 0:
                return None

            last_date = unique_dates[-1]
            last_day_df = df[df["Date"] == last_date]

            if last_day_df.empty or len(last_day_df) < 3:
                # If current day just opened or has too few bars, look at previous full session
                if len(unique_dates) >= 2:
                    last_date = unique_dates[-2]
                    last_day_df = df[df["Date"] == last_date]
                else:
                    return None

            # Calculate candles count for opening range (5-min candles: 15m=3, 30m=6)
            candles_needed = max(2, or_minutes // 5)
            or_df = last_day_df.iloc[:candles_needed]
            if len(or_df) < 2:
                return None

            orb_high = float(or_df["High"].max())
            orb_low = float(or_df["Low"].min())
            orb_mid = round((orb_high + orb_low) / 2.0, 2)
            orb_range = round(orb_high - orb_low, 2)
            orb_volume = float(or_df["Volume"].sum())

            # Current price & latest candle
            current_spot = float(last_day_df.iloc[-1]["Close"])
            latest_bar = last_day_df.iloc[-1]
            latest_volume = float(latest_bar["Volume"])

            # Compute Relative Volume (compare with other days at same period if possible)
            avg_bar_volume = float(df["Volume"].mean()) if not df["Volume"].empty else 1.0
            rv = round(latest_volume / avg_bar_volume, 2) if avg_bar_volume > 0 else 1.0

            # Target 1 (1.0x OR range above ORB High for long, below ORB Low for short)
            target_1_long = round(orb_high + (1.0 * orb_range), 2)
            target_2_long = round(orb_high + (2.0 * orb_range), 2)
            stop_long = orb_mid  # Mid-point invalidation

            target_1_short = round(orb_low - (1.0 * orb_range), 2)
            stop_short = orb_mid

            # Breakout state evaluation
            buffer_pct = 0.0015  # 0.15% buffer
            is_breakout_long = current_spot > (orb_high * (1.0 + buffer_pct))
            is_breakdown_short = current_spot < (orb_low * (1.0 - buffer_pct))

            if is_breakout_long:
                state = "BULLISH_BREAKOUT"
                badge = "🚀 BULLISH BREAKOUT"
                direction = "long"
                dist_pct = round(((current_spot - orb_high) / orb_high) * 100, 2)
                vol_confirmed = rv >= 1.20
            elif is_breakdown_short:
                state = "BEARISH_BREAKDOWN"
                badge = "⚡ BEARISH BREAKDOWN"
                direction = "short"
                dist_pct = round(((orb_low - current_spot) / orb_low) * 100, 2)
                vol_confirmed = rv >= 1.20
            else:
                state = "INSIDE_RANGE"
                badge = "⏳ INSIDE RANGE"
                direction = "neutral"
                dist_pct = 0.0
                vol_confirmed = False

            currency = "EUR" if self.is_european_ticker(ticker) else ("GBP" if ticker.endswith(".L") else "USD")
            curr_sym = "€" if currency == "EUR" else ("£" if currency == "GBP" else "$")

            result: Dict[str, Any] = {
                "ticker": ticker,
                "or_minutes": or_minutes,
                "session_date": str(last_date),
                "spot_price": current_spot,
                "currency": currency,
                "currency_symbol": curr_sym,
                "orb_high": orb_high,
                "orb_low": orb_low,
                "orb_mid": orb_mid,
                "orb_range": orb_range,
                "orb_range_pct": round((orb_range / orb_low * 100) if orb_low > 0 else 0.0, 2),
                "state": state,
                "badge": badge,
                "direction": direction,
                "distance_pct": dist_pct,
                "relative_volume": rv,
                "volume_confirmed": vol_confirmed,
                "target_1": target_1_long if direction == "long" else target_1_short,
                "target_2": target_2_long if direction == "long" else None,
                "invalidation_stop": stop_long if direction == "long" else stop_short,
            }

            self._cache[cache_key] = (time.time(), result)
            return result

        except Exception as exc:
            logger.warning("Error computing ORB for %s: %s", ticker, exc)
            return None

    def scan_watchlist_orb(
        self,
        tickers: List[str],
        or_minutes: int = 30,
    ) -> Dict[str, Any]:
        """
        Scans a list of tickers for active Opening Range Breakouts.
        """
        clean_tickers = list(dict.fromkeys([t.upper().strip() for t in tickers if t]))
        breakouts = []
        breakdowns = []
        inside_range = []

        for sym in clean_tickers:
            data = self.analyze_orb(sym, or_minutes=or_minutes)
            if not data:
                continue

            if data["state"] == "BULLISH_BREAKOUT":
                breakouts.append(data)
            elif data["state"] == "BEARISH_BREAKDOWN":
                breakdowns.append(data)
            else:
                inside_range.append(data)

        breakouts.sort(key=lambda x: (x["volume_confirmed"], x["distance_pct"]), reverse=True)
        breakdowns.sort(key=lambda x: (x["volume_confirmed"], x["distance_pct"]), reverse=True)

        return {
            "scanned_count": len(clean_tickers),
            "or_minutes": or_minutes,
            "breakouts_count": len(breakouts),
            "breakdowns_count": len(breakdowns),
            "breakouts": breakouts,
            "breakdowns": breakdowns,
            "inside_range_count": len(inside_range),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def format_telegram_orb_card(self, orb: Dict[str, Any]) -> str:
        """Formats single-asset ORB detail for Telegram."""
        ticker = orb["ticker"]
        sym = orb.get("currency_symbol", "$")
        spot = orb.get("spot_price", 0.0)
        h = orb.get("orb_high", 0.0)
        l = orb.get("orb_low", 0.0)
        mid = orb.get("orb_mid", 0.0)
        state = orb.get("state", "INSIDE_RANGE")
        badge = orb.get("badge", "⏳ INSIDE RANGE")
        rv = orb.get("relative_volume", 1.0)
        vol_badge = "🔥 Hohes Volumen" if orb.get("volume_confirmed") else "⚪ Normales Volumen"
        or_min = orb.get("or_minutes", 30)

        lines = [
            f"⚡ <b>OPENING RANGE BREAKOUT (ORB): {ticker}</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"• <b>Status:</b> {badge}",
            f"• <b>Aktueller Kurs:</b> {sym}{spot:.2f}\n",
            f"📐 <b>{or_min}-Minuten Eröffnungs-Range:</b>",
            f"• <b>ORB High:</b> {sym}{h:.2f}",
            f"• <b>ORB Mid (Stop):</b> {sym}{mid:.2f}",
            f"• <b>ORB Low:</b> {sym}{l:.2f}",
            f"• <b>Range-Spanne:</b> {sym}{orb.get('orb_range', 0.0):.2f} ({orb.get('orb_range_pct', 0.0):.1f}%)\n",
            f"📊 <b>Volumen &amp; Bestätigung:</b>",
            f"• Relatives Volumen (RV): <b>{rv:.1f}x</b> ({vol_badge})",
        ]

        if state == "BULLISH_BREAKOUT":
            lines.extend([
                "",
                "🎯 <b>Breakout-Ziele &amp; Risikomanagement:</b>",
                f"• <b>Einstieg:</b> Markt / über {sym}{h:.2f}",
                f"• <b>Stop-Loss:</b> {sym}{mid:.2f} (Mid-Range Invalidation)",
                f"• <b>Ziel 1 (+1.0x Range):</b> {sym}{orb.get('target_1', 0.0):.2f}",
                f"• <b>Ziel 2 (+2.0x Range):</b> {sym}{orb.get('target_2', 0.0):.2f}",
            ])
        elif state == "BEARISH_BREAKDOWN":
            lines.extend([
                "",
                "🎯 <b>Breakdown-Ziele:</b>",
                f"• <b>Short-Einstieg:</b> unter {sym}{l:.2f}",
                f"• <b>Stop-Loss:</b> {sym}{mid:.2f}",
                f"• <b>Ziel 1:</b> {sym}{orb.get('target_1', 0.0):.2f}",
            ])
        else:
            lines.extend([
                "",
                "⏳ <i>Kurs konsolidiert innerhalb der Eröffnungsrange. Warten auf Ausbruch über ORB-High oder Breakdown unter ORB-Low.</i>"
            ])

        lines.extend([
            "",
            f"💡 <i>Tipp: Buche das Setup direkt mit <code>/paper {ticker}</code> oder rufe <code>/edge {ticker}</code> ab.</i>"
        ])
        return "\n".join(lines)

    def format_telegram_orb_scan_summary(self, scan: Dict[str, Any]) -> str:
        """Formats watchlist ORB scan for Telegram."""
        mins = scan.get("or_minutes", 30)
        b_outs = scan.get("breakouts", [])
        b_downs = scan.get("breakdowns", [])

        lines = [
            f"⚡ <b>INTRADAY ORB RADAR ({mins}m Session Range)</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"Gescannte Watchlist-Titel: <b>{scan.get('scanned_count', 0)}</b>",
            f"Bullische Ausbrüche: <b>{len(b_outs)}</b> | Bärische Breakdowns: <b>{len(b_downs)}</b>\n",
        ]

        if b_outs:
            lines.append("🚀 <b>Aktive Bullische Ausbrüche (> ORB High):</b>")
            for b in b_outs[:6]:
                sym = b.get("currency_symbol", "$")
                vol_str = f" 🔥 RV: {b['relative_volume']}x" if b.get("volume_confirmed") else ""
                lines.append(
                    f"• <b>{b['ticker']}</b>: {sym}{b['spot_price']:.2f} (+{b['distance_pct']:.1f}% über High {sym}{b['orb_high']:.2f}){vol_str}"
                )
            lines.append("")

        if b_downs:
            lines.append("⚡ <b>Aktive Bärische Breakdowns (< ORB Low):</b>")
            for b in b_downs[:4]:
                sym = b.get("currency_symbol", "$")
                lines.append(
                    f"• <b>{b['ticker']}</b>: {sym}{b['spot_price']:.2f} (-{b['distance_pct']:.1f}% unter Low {sym}{b['orb_low']:.2f})"
                )
            lines.append("")

        if not b_outs and not b_downs:
            lines.append("⏳ <i>Keine aktiven Ausbrüche im Moment. Alle Titel konsolidieren innerhalb der Opening Range.</i>\n")

        lines.append(
            "💡 <i>Abruf: <code>/orb TICKER</code> für Ziel- &amp; Stop-Level oder <code>/edge</code> für 360°-Konfluenz.</i>"
        )
        return "\n".join(lines)
