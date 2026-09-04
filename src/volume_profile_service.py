"""
Volume Profile Service — Auction Market Theory (POC, VAH, VAL, LVN)

Calculates:
  1. Volume at Price (Volume Profile distribution across price bins)
  2. Point of Control (POC) — the fairest price with highest traded volume
  3. Value Area High (VAH) & Value Area Low (VAL) — 70% volume bracket
  4. Low Volume Nodes (LVN) — price vacuum zones where fast moves occur
  5. Current price positioning (Inside Value, Bullish Acceptance > VAH, Bearish Acceptance < VAL)
  6. Structural support/resistance levels for invalidation & stop placement
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore


@dataclass
class _VPCacheEntry:
    timestamp: float
    data: Dict[str, Any]


class VolumeProfileService:
    _cache: Dict[str, _VPCacheEntry] = {}
    TTL_SECONDS = 900  # 15 minutes cache

    def __init__(self, num_bins: int = 50, value_area_pct: float = 0.70) -> None:
        self.num_bins = num_bins
        self.value_area_pct = value_area_pct

    def compute_volume_profile(
        self,
        ticker: str,
        period: str = "1mo",
        interval: str = "30m",
    ) -> Optional[Dict[str, Any]]:
        """
        Computes the volume profile distribution, POC, VAH, and VAL from historical bars.
        """
        symbol = ticker.strip().upper()
        cache_key = f"{symbol}_{period}_{interval}"
        now = time.time()
        cached = self._cache.get(cache_key)
        if cached and (now - cached.timestamp < self.TTL_SECONDS):
            return cached.data

        if not yf:
            logger.warning("yfinance is not available for VolumeProfileService")
            return None

        try:
            t = yf.Ticker(symbol)
            hist = t.history(period=period, interval=interval)
            # Fallback to daily if intraday interval has insufficient bars
            if hist.empty or len(hist) < 15:
                hist = t.history(period="3mo", interval="1d")
            if hist.empty or len(hist) < 10:
                return None

            highs = hist["High"].astype(float).tolist()
            lows = hist["Low"].astype(float).tolist()
            closes = hist["Close"].astype(float).tolist()
            volumes = hist["Volume"].astype(float).tolist()

            min_price = min(lows)
            max_price = max(highs)
            current_price = closes[-1]

            if min_price >= max_price or max_price <= 0:
                return None

            bin_size = (max_price - min_price) / float(self.num_bins)
            if bin_size <= 0:
                return None

            # Distribute volume across price bins
            bin_volumes = [0.0] * self.num_bins
            bin_mid_prices = [min_price + (i + 0.5) * bin_size for i in range(self.num_bins)]

            total_volume = 0.0
            for h, l, v in zip(highs, lows, volumes):
                if v <= 0 or h < l:
                    continue
                total_volume += v
                # Find covered bins
                low_bin = max(0, min(self.num_bins - 1, int((l - min_price) / bin_size)))
                high_bin = max(0, min(self.num_bins - 1, int((h - min_price) / bin_size)))
                num_covered = max(1, high_bin - low_bin + 1)
                vol_per_bin = v / float(num_covered)
                for b in range(low_bin, high_bin + 1):
                    bin_volumes[b] += vol_per_bin

            if total_volume <= 0:
                return None

            # 1. Point of Control (POC) — bin with maximum volume
            poc_bin = max(range(self.num_bins), key=lambda b: bin_volumes[b])
            poc_price = bin_mid_prices[poc_bin]

            # 2. Value Area (70% of volume starting from POC)
            target_va_vol = total_volume * self.value_area_pct
            current_va_vol = bin_volumes[poc_bin]

            low_ptr = poc_bin
            high_ptr = poc_bin

            while current_va_vol < target_va_vol and (low_ptr > 0 or high_ptr < self.num_bins - 1):
                next_up_vol = bin_volumes[high_ptr + 1] if high_ptr < self.num_bins - 1 else 0.0
                next_down_vol = bin_volumes[low_ptr - 1] if low_ptr > 0 else 0.0

                if next_up_vol >= next_down_vol and high_ptr < self.num_bins - 1:
                    high_ptr += 1
                    current_va_vol += next_up_vol
                elif low_ptr > 0:
                    low_ptr -= 1
                    current_va_vol += next_down_vol
                elif high_ptr < self.num_bins - 1:
                    high_ptr += 1
                    current_va_vol += next_up_vol
                else:
                    break

            val_price = bin_mid_prices[low_ptr] - (0.5 * bin_size)
            vah_price = bin_mid_prices[high_ptr] + (0.5 * bin_size)

            # 3. Identify Low Volume Nodes (LVN) — potential fast travel zones
            # An LVN has volume significantly lower than surrounding bins
            lvns: List[float] = []
            for b in range(2, self.num_bins - 2):
                local_avg = (bin_volumes[b - 2] + bin_volumes[b - 1] + bin_volumes[b + 1] + bin_volumes[b + 2]) / 4.0
                if local_avg > 0 and bin_volumes[b] < 0.45 * local_avg:
                    lvns.append(round(bin_mid_prices[b], 2))

            # Deduplicate close LVNs
            filtered_lvns = []
            for lvn in lvns:
                if not filtered_lvns or abs(lvn - filtered_lvns[-1]) / filtered_lvns[-1] > 0.015:
                    filtered_lvns.append(lvn)

            # 4. Determine market acceptance & position relative to Value Area
            if current_price > vah_price:
                market_location = "above_value_area"
                location_label = "Bullish Acceptance (> VAH)"
                trade_bias = "Bullish continuation if VAH holds as support; look for retest of VAH"
                structural_support = round(vah_price, 2)
                structural_resistance = round(max_price, 2)
            elif current_price < val_price:
                market_location = "below_value_area"
                location_label = "Bearish Acceptance (< VAL)"
                trade_bias = "Bearish continuation if VAL holds as resistance; look for lower lows or retest failure"
                structural_support = round(min_price, 2)
                structural_resistance = round(val_price, 2)
            else:
                market_location = "inside_value_area"
                location_label = "Inside Value Area (Rotation / Balance)"
                trade_bias = "Rotational market. Mean reversion towards POC. Avoid chasing breakouts inside the bracket."
                structural_support = round(val_price, 2)
                structural_resistance = round(vah_price, 2)

            poc_distance_pct = ((current_price - poc_price) / poc_price) * 100.0

            # 5. Format top volume profile nodes for charts
            profile_nodes = []
            max_bin_vol = max(bin_volumes) if bin_volumes else 1.0
            for i in range(self.num_bins):
                profile_nodes.append({
                    "price": round(bin_mid_prices[i], 2),
                    "volume": round(bin_volumes[i], 0),
                    "volume_pct": round((bin_volumes[i] / total_volume) * 100.0, 2),
                    "relative_width": round(bin_volumes[i] / max_bin_vol, 3),
                    "is_poc": (i == poc_bin),
                    "in_value_area": (low_ptr <= i <= high_ptr),
                })

            result: Dict[str, Any] = {
                "ticker": symbol,
                "current_price": round(current_price, 2),
                "poc_price": round(poc_price, 2),
                "vah_price": round(vah_price, 2),
                "val_price": round(val_price, 2),
                "value_area_spread_pct": round(((vah_price - val_price) / poc_price) * 100.0, 2),
                "poc_distance_pct": round(poc_distance_pct, 2),
                "market_location": market_location,
                "location_label": location_label,
                "trade_bias": trade_bias,
                "structural_support": structural_support,
                "structural_resistance": structural_resistance,
                "low_volume_nodes": filtered_lvns[:4],
                "sample_bars": len(hist),
                "profile_nodes": profile_nodes,
                "calculated_at": datetime.now(timezone.utc).isoformat(),
            }

            self._cache[cache_key] = _VPCacheEntry(timestamp=now, data=result)
            return result

        except Exception as exc:
            logger.error("Failed to compute volume profile for %s: %s", symbol, exc)
            return None
