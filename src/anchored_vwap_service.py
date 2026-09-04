"""
Anchored VWAP (AVWAP) Service — Institutional Event Benchmarks & Volatility Bands

Calculates Volume-Weighted Average Price anchored to key structural inflection points:
  1. YTD AVWAP: Institutional year-to-date benchmark (Bulls vs Bears territory).
  2. Earnings AVWAP: Volume benchmark from the most recent quarterly report.
  3. Monthly AVWAP: Institutional cycle benchmark for the current month.
  4. Swing-Low AVWAP: Anchored at the lowest inflection point of the past 60 days.

Includes dynamic ±1.0σ and ±2.0σ standard deviation bands.
"""
from __future__ import annotations

import logging
import math
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore


class AnchoredVWAPService:
    def __init__(self, cache_ttl_seconds: int = 900) -> None:
        self.ttl = cache_ttl_seconds
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    def compute_anchored_vwaps(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Computes YTD, Earnings, Monthly, and Swing-Low Anchored VWAPs for a ticker.
        """
        symbol = ticker.strip().upper()
        cached = self._cache.get(symbol)
        if cached and (time.time() - cached[0]) < self.ttl:
            return cached[1]

        if not yf:
            return None

        try:
            t = yf.Ticker(symbol)
            # Fetch 1 year of daily bars to cover YTD, swing lows, and recent earnings
            hist = t.history(period="1y", interval="1d")
            if hist.empty or len(hist) < 10:
                return None

            hist = hist.dropna(subset=["Close", "Volume"])
            if len(hist) < 10:
                return None

            # Spot price
            spot = float(hist["Close"].iloc[-1])

            # Dates
            today = datetime.now(timezone.utc).date()
            ytd_start = date(today.year, 1, 1)
            monthly_start = date(today.year, today.month, 1)

            # Find Earnings Date anchor (most recent earnings in the past)
            earnings_anchor_date = self._find_recent_past_earnings_date(t, today)

            # Calculate YTD AVWAP
            ytd_res = self._calculate_avwap_from_date(hist, ytd_start, label="YTD")
            # Calculate Monthly AVWAP
            monthly_res = self._calculate_avwap_from_date(hist, monthly_start, label="Monthly")
            # Calculate Earnings AVWAP
            earnings_res = (
                self._calculate_avwap_from_date(hist, earnings_anchor_date, label="Earnings")
                if earnings_anchor_date else None
            )

            # Calculate Swing Low AVWAP (lowest low in past 60 bars)
            swing_low_res = self._calculate_swing_low_avwap(hist, lookback=60)

            # Retest checks (within 1.5% of key AVWAPs)
            retests: List[str] = []
            if ytd_res and abs(spot - ytd_res["avwap"]) / spot <= 0.015:
                retests.append(f"YTD AVWAP (${ytd_res['avwap']:.2f})")
            if earnings_res and abs(spot - earnings_res["avwap"]) / spot <= 0.015:
                retests.append(f"Earnings AVWAP (${earnings_res['avwap']:.2f})")
            if swing_low_res and abs(spot - swing_low_res["avwap"]) / spot <= 0.015:
                retests.append(f"Swing-Low AVWAP (${swing_low_res['avwap']:.2f})")

            # Institutional Bias: Bullish if above both YTD and Earnings AVWAP
            above_ytd = ytd_res and spot >= ytd_res["avwap"]
            above_earnings = (earnings_res and spot >= earnings_res["avwap"]) if earnings_res else True

            if above_ytd and above_earnings:
                institutional_bias = "BULLISH_ACCEPTANCE"
                bias_label = "🟢 Institutionelle Käufer im Gewinn (Bullenmarkt)"
            elif not above_ytd and not above_earnings:
                institutional_bias = "BEARISH_PRESSURE"
                bias_label = "🔴 Institutionelle Käufer unter Wasser (Verkaufsdruck)"
            else:
                institutional_bias = "NEUTRAL_CONTESTED"
                bias_label = "🟡 Umkämpft zwischen YTD und Earnings"

            result = {
                "ticker": symbol,
                "spot_price": round(spot, 2),
                "ytd": ytd_res,
                "earnings": earnings_res,
                "monthly": monthly_res,
                "swing_low": swing_low_res,
                "retests": retests,
                "institutional_bias": institutional_bias,
                "bias_label": bias_label,
            }

            self._cache[symbol] = (time.time(), result)
            return result

        except Exception as exc:
            logger.debug("Anchored VWAP computation error for %s: %s", symbol, exc)
            return None

    def _calculate_avwap_from_date(
        self,
        df: Any,
        start_date: date,
        label: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Calculates AVWAP and standard deviation bands from a given start date."""
        try:
            # Filter rows >= start_date
            mask = df.index.date >= start_date
            sub = df.loc[mask]
            if sub.empty or len(sub) < 2:
                return None

            highs = sub["High"].tolist()
            lows = sub["Low"].tolist()
            closes = sub["Close"].tolist()
            vols = sub["Volume"].tolist()

            total_vol = sum(vols)
            if total_vol <= 0:
                return None

            # Typical Price: (High + Low + Close) / 3
            typical_prices = [(h + l + c) / 3.0 for h, l, c in zip(highs, lows, closes)]
            cum_tp_vol = sum(tp * v for tp, v in zip(typical_prices, vols))
            avwap = cum_tp_vol / total_vol

            # Variance & Std Dev: sqrt( sum(v * (tp - avwap)^2) / sum(v) )
            weighted_var = sum(v * ((tp - avwap) ** 2) for tp, v in zip(typical_prices, vols)) / total_vol
            std_dev = math.sqrt(weighted_var)

            spot = closes[-1]
            dist_pct = round(((spot - avwap) / avwap) * 100.0, 2)

            return {
                "label": label,
                "anchor_date": start_date.isoformat(),
                "avwap": round(avwap, 2),
                "upper_band_1": round(avwap + (1.0 * std_dev), 2),
                "lower_band_1": round(avwap - (1.0 * std_dev), 2),
                "upper_band_2": round(avwap + (2.0 * std_dev), 2),
                "lower_band_2": round(avwap - (2.0 * std_dev), 2),
                "dist_pct": dist_pct,
                "bars_count": len(sub),
                "is_above": spot >= avwap,
            }
        except Exception:
            return None

    def _calculate_swing_low_avwap(self, df: Any, lookback: int = 60) -> Optional[Dict[str, Any]]:
        """Finds the lowest intraday low in the past `lookback` bars and anchors AVWAP there."""
        try:
            recent = df.tail(lookback)
            if recent.empty or len(recent) < 5:
                return None

            min_idx = recent["Low"].idxmin()
            anchor_date = min_idx.date() if hasattr(min_idx, "date") else None
            if not anchor_date:
                return None

            return self._calculate_avwap_from_date(df, anchor_date, label="Swing-Low")
        except Exception:
            return None

    def _find_recent_past_earnings_date(self, ticker_obj: Any, today: date) -> Optional[date]:
        """Extracts the date of the most recent quarterly earnings report in the past."""
        try:
            # 1. Try quarterly financial statement dates (most reliable for past reports)
            stmt = getattr(ticker_obj, "quarterly_income_stmt", None)
            if stmt is not None and not stmt.empty:
                cols = list(stmt.columns)
                past_dates = [
                    c.date() if hasattr(c, "date") else c
                    for c in cols
                    if (hasattr(c, "date") and c.date() <= today)
                ]
                if past_dates:
                    past_dates.sort(reverse=True)
                    return past_dates[0]

            # 2. Try calendar
            cal = getattr(ticker_obj, "calendar", None)
            if cal and isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if isinstance(ed, (list, tuple)) and ed:
                    d = ed[0].date() if hasattr(ed[0], "date") else ed[0]
                    if isinstance(d, date) and d <= today:
                        return d

            # 3. Fallback: ~45 days ago if unavailable
            return None
        except Exception:
            return None

    def format_telegram_avwap_card(self, data: Dict[str, Any]) -> str:
        """Formats an AVWAP overview card for Telegram."""
        sym = data.get("ticker", "")
        spot = data.get("spot_price", 0.0)
        bias_label = data.get("bias_label", "Neutral")

        lines = [
            f"⚓ <b>ANCHORED VWAP BENCHMARKS: {sym}</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"• <b>Aktueller Kurs:</b> ${spot:.2f}",
            f"• <b>Institutioneller Bias:</b> {bias_label}\n",
        ]

        ytd = data.get("ytd")
        if ytd:
            icon = "🟢" if ytd.get("is_above", False) else "🔴"
            lines.append(f"• <b>YTD AVWAP:</b> ${ytd['avwap']:.2f} ({ytd.get('dist_pct', 0.0):+.1f}%) {icon}")
            lines.append(f"  Bänder: ${ytd.get('lower_band_1', 0.0):.2f} &middot; ${ytd.get('upper_band_1', 0.0):.2f}")

        earnings = data.get("earnings")
        if earnings:
            icon = "🟢" if earnings.get("is_above", False) else "🔴"
            lines.append(f"• <b>Earnings AVWAP:</b> ${earnings['avwap']:.2f} ({earnings.get('dist_pct', 0.0):+.1f}%) {icon}")
            lines.append(f"  Seit Bericht am {earnings.get('anchor_date', 'N/A')}")

        monthly = data.get("monthly")
        if monthly:
            icon = "🟢" if monthly.get("is_above", False) else "🔴"
            lines.append(f"• <b>Monthly AVWAP:</b> ${monthly['avwap']:.2f} ({monthly.get('dist_pct', 0.0):+.1f}%) {icon}")

        swing = data.get("swing_low")
        if swing:
            lines.append(f"• <b>Swing-Low AVWAP:</b> ${swing['avwap']:.2f} ({swing['dist_pct']:+.1f}%)")

        retests = data.get("retests", [])
        if retests:
            lines.append(f"\n⚡ <b>Aktiver Retest:</b> Kurs testet gerade {', '.join(retests)}! Erhöhte Rebound-Wahrscheinlichkeit.")
        else:
            lines.append("\n💡 <i>Tipp: Kaufe Pullbacks an den Earnings- oder YTD-AVWAP, wenn der Kurs oberhalb schließt.</i>")

        return "\n".join(lines)
