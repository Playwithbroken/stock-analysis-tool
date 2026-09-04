"""
Options Edge Service — Market Maker Gamma Exposure (GEX) & Option Walls

Calculates:
  1. Black-Scholes Option Gamma per strike
  2. Dealer Net Gamma Exposure (GEX in $ per 1% move)
  3. Zero-Gamma Flip Level (threshold between mean-reverting and trending markets)
  4. Call Wall (major resistance / dealer pinning target)
  5. Put Wall (major support / dealer hedging barrier)
  6. Market Maker Regime: Positive Gamma (dampens volatility) vs Negative Gamma (accelerates volatility)
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
class _CacheEntry:
    timestamp: float
    data: Dict[str, Any]


class OptionsEdgeService:
    _cache: Dict[str, _CacheEntry] = {}
    TTL_SECONDS = 900  # 15 minutes cache

    def __init__(self, risk_free_rate: float = 0.045) -> None:
        self.risk_free_rate = risk_free_rate

    @staticmethod
    def _normal_pdf(x: float) -> float:
        """Standard normal probability density function N'(x)."""
        return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)

    def calculate_bs_gamma(
        self,
        spot: float,
        strike: float,
        t_years: float,
        iv: float,
    ) -> float:
        """Calculate Black-Scholes Gamma: N'(d1) / (S * sigma * sqrt(T))."""
        if spot <= 0 or strike <= 0 or t_years <= 0 or iv <= 0.001:
            return 0.0
        try:
            vol_sqrt_t = iv * math.sqrt(t_years)
            if vol_sqrt_t <= 1e-6:
                return 0.0
            d1 = (math.log(spot / strike) + (self.risk_free_rate + 0.5 * iv * iv) * t_years) / vol_sqrt_t
            pdf = self._normal_pdf(d1)
            gamma = pdf / (spot * vol_sqrt_t)
            return gamma if math.isfinite(gamma) else 0.0
        except Exception:
            return 0.0

    def analyze_gex(self, ticker: str, spot_override: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        Calculates Net Gamma Exposure (GEX) across active near-term expirations.
        """
        symbol = ticker.strip().upper()
        now = time.time()
        cached = self._cache.get(symbol)
        if cached and (now - cached.timestamp < self.TTL_SECONDS):
            return cached.data

        if not yf:
            logger.warning("yfinance is not available for OptionsEdgeService")
            return None

        try:
            t = yf.Ticker(symbol)
            expirations = getattr(t, "options", None)
            if not expirations:
                return None

            # Fetch spot price
            spot = spot_override
            if not spot or spot <= 0:
                fast_info = getattr(t, "fast_info", None)
                if fast_info:
                    spot = float(fast_info.get("lastPrice") or fast_info.get("regularMarketPreviousClose") or 0)
                if not spot or spot <= 0:
                    hist = t.history(period="5d")
                    if not hist.empty:
                        spot = float(hist["Close"].iloc[-1])
            if not spot or spot <= 0:
                return None

            # Evaluate active expirations within next 60 days (up to 12 cycles to capture monthly expirations)
            today = datetime.now(timezone.utc).date()
            valid_exps: List[tuple[str, float]] = []
            for exp_str in expirations[:12]:
                try:
                    exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                    days = (exp_date - today).days
                    if 0 <= days <= 60:
                        # Convert to years, minimum 0.5 day to avoid division by zero on expiry day
                        t_years = max(0.5 / 365.0, days / 365.0)
                        valid_exps.append((exp_str, t_years))
                except Exception:
                    continue

            if not valid_exps:
                return None

            # Strike aggregation: strike -> {call_gex: float, put_gex: float, call_oi: int, put_oi: int}
            strikes_data: Dict[float, Dict[str, float]] = {}

            total_call_gex = 0.0
            total_put_gex = 0.0
            total_call_oi = 0
            total_put_oi = 0

            for exp_str, t_years in valid_exps:
                try:
                    chain = t.option_chain(exp_str)
                except Exception:
                    continue

                # Process Calls (Dealers assumed SHORT calls -> LONG Gamma for dealers)
                calls_df = getattr(chain, "calls", None)
                if calls_df is not None and not calls_df.empty:
                    for _, row in calls_df.iterrows():
                        strike = float(row.get("strike") or 0)
                        oi_val = row.get("openInterest")
                        vol_val = row.get("volume")
                        oi = int(oi_val) if oi_val is not None and not math.isnan(float(oi_val)) else 0
                        vol = int(vol_val) if vol_val is not None and not math.isnan(float(vol_val)) else 0
                        activity = max(oi, vol)
                        if strike <= 0 or activity <= 0:
                            continue

                        iv = float(row.get("impliedVolatility") or 0)
                        if iv <= 0.005:
                            iv = 0.22  # Fallback IV proxy

                        gamma = self.calculate_bs_gamma(spot, strike, t_years, iv)
                        # Dollar GEX per 1% move: Gamma * activity * 100 * Spot * (Spot * 0.01)
                        dollar_gex = gamma * activity * 100 * spot * (spot * 0.01)

                        if strike not in strikes_data:
                            strikes_data[strike] = {"call_gex": 0.0, "put_gex": 0.0, "call_oi": 0, "put_oi": 0}
                        strikes_data[strike]["call_gex"] += dollar_gex
                        strikes_data[strike]["call_oi"] += activity
                        total_call_gex += dollar_gex
                        total_call_oi += activity

                # Process Puts (Dealers assumed SHORT puts -> SHORT Gamma for dealers)
                puts_df = getattr(chain, "puts", None)
                if puts_df is not None and not puts_df.empty:
                    for _, row in puts_df.iterrows():
                        strike = float(row.get("strike") or 0)
                        oi_val = row.get("openInterest")
                        vol_val = row.get("volume")
                        oi = int(oi_val) if oi_val is not None and not math.isnan(float(oi_val)) else 0
                        vol = int(vol_val) if vol_val is not None and not math.isnan(float(vol_val)) else 0
                        activity = max(oi, vol)
                        if strike <= 0 or activity <= 0:
                            continue

                        iv = float(row.get("impliedVolatility") or 0)
                        if iv <= 0.005:
                            iv = 0.22  # Fallback IV proxy

                        gamma = self.calculate_bs_gamma(spot, strike, t_years, iv)
                        # Negative sign because dealers are short gamma on puts
                        dollar_gex = - (gamma * activity * 100 * spot * (spot * 0.01))

                        if strike not in strikes_data:
                            strikes_data[strike] = {"call_gex": 0.0, "put_gex": 0.0, "call_oi": 0, "put_oi": 0}
                        strikes_data[strike]["put_gex"] += dollar_gex
                        strikes_data[strike]["put_oi"] += activity
                        total_put_gex += dollar_gex
                        total_put_oi += activity

            if not strikes_data:
                return None

            net_gex = total_call_gex + total_put_gex  # total_put_gex is negative

            # Identify Call Wall (Highest Call GEX/OI strike)
            call_wall_strike = max(
                strikes_data.keys(),
                key=lambda k: strikes_data[k]["call_gex"],
            )
            # Identify Put Wall (Most negative Put GEX / highest Put OI strike)
            put_wall_strike = min(
                strikes_data.keys(),
                key=lambda k: strikes_data[k]["put_gex"],
            )

            # Find Zero-Gamma Flip Level (where cumulative GEX changes sign)
            sorted_strikes = sorted(strikes_data.keys())
            zero_gamma_level = None
            for i in range(len(sorted_strikes) - 1):
                k1 = sorted_strikes[i]
                k2 = sorted_strikes[i + 1]
                net1 = strikes_data[k1]["call_gex"] + strikes_data[k1]["put_gex"]
                net2 = strikes_data[k2]["call_gex"] + strikes_data[k2]["put_gex"]
                if (net1 < 0 and net2 > 0) or (net1 > 0 and net2 < 0):
                    # Linear interpolation
                    denom = (net2 - net1) if (net2 - net1) != 0 else 1e-9
                    zero_gamma_level = round(k1 + (0 - net1) / denom * (k2 - k1), 2)
                    break

            if zero_gamma_level is None:
                zero_gamma_level = round(put_wall_strike, 2)

            # Pin strike (Strike with maximum absolute total gamma density near spot)
            strikes_near_spot = [
                k for k in sorted_strikes if 0.85 * spot <= k <= 1.15 * spot
            ] or sorted_strikes
            pin_strike = max(
                strikes_near_spot,
                key=lambda k: (strikes_data[k]["call_gex"] + abs(strikes_data[k]["put_gex"])),
            )

            # Determine regime
            is_positive_gamma = net_gex >= 0
            regime = "positive_gamma" if is_positive_gamma else "negative_gamma"
            regime_label = (
                "Positive Gamma (Mean-Reverting, Damped Volatility, Pinning)"
                if is_positive_gamma
                else "Negative Gamma (High Volatility, Trend Acceleration, Fast Breakouts)"
            )

            # Trade advice based on dealer positioning
            if is_positive_gamma:
                trade_implication = (
                    f"Market makers are long gamma. Volatility is compressed. "
                    f"Fading extremes towards Call Wall (${call_wall_strike:.2f}) and Put Wall (${put_wall_strike:.2f}) is favored. "
                    f"Magnet strike near ${pin_strike:.2f}."
                )
            else:
                trade_implication = (
                    f"Market makers are short gamma below Zero Gamma (${zero_gamma_level:.2f}). "
                    f"Dealer hedging will ACCELERATE moves. Breakouts can run fast; "
                    f"tight stops and momentum setups are favored."
                )

            # Format top strike distribution for UI/API
            top_strikes = []
            for k in sorted(strikes_near_spot, key=lambda s: abs(strikes_data[s]["call_gex"] + strikes_data[s]["put_gex"]), reverse=True)[:8]:
                top_strikes.append({
                    "strike": k,
                    "call_gex": round(strikes_data[k]["call_gex"], 2),
                    "put_gex": round(strikes_data[k]["put_gex"], 2),
                    "net_gex": round(strikes_data[k]["call_gex"] + strikes_data[k]["put_gex"], 2),
                    "call_oi": strikes_data[k]["call_oi"],
                    "put_oi": strikes_data[k]["put_oi"],
                })

            result: Dict[str, Any] = {
                "ticker": symbol,
                "spot_price": round(spot, 2),
                "net_gex": round(net_gex, 2),
                "call_gex": round(total_call_gex, 2),
                "put_gex": round(total_put_gex, 2),
                "regime": regime,
                "regime_label": regime_label,
                "call_wall": round(call_wall_strike, 2),
                "put_wall": round(put_wall_strike, 2),
                "zero_gamma_level": zero_gamma_level,
                "pin_strike": round(pin_strike, 2),
                "total_call_oi": total_call_oi,
                "total_put_oi": total_put_oi,
                "put_call_oi_ratio": round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 0.0,
                "trade_implication": trade_implication,
                "top_strikes": top_strikes,
                "calculated_at": datetime.now(timezone.utc).isoformat(),
            }

            self._cache[symbol] = _CacheEntry(timestamp=now, data=result)
            return result

        except Exception as exc:
            logger.error("Failed to analyze GEX for %s: %s", symbol, exc)
            return None
