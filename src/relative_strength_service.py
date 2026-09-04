"""
Relative Strength Service — Mansfield Relative Strength & Institutional Alpha vs SPY

Measures whether a stock is outperforming the broader market (SPY/QQQ).
True institutional market leaders (e.g., NVDA, PLTR) consistently show
positive Mansfield RS, especially holding up or breaking out while the market pulls back.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore


@dataclass
class _RSCache:
    timestamp: float
    data: Any


class RelativeStrengthService:
    def __init__(self, ttl_seconds: int = 900) -> None:
        self.ttl = ttl_seconds
        self._cache: Dict[str, _RSCache] = {}

    def compute_relative_strength(
        self,
        ticker: str,
        benchmark: str = "SPY",
    ) -> Optional[Dict[str, Any]]:
        """
        Computes Mansfield Relative Strength and 1-month / 3-month Alpha vs Benchmark.
        Formula:
          RS_ratio = Close(Ticker) / Close(Benchmark)
          Mansfield_RS = ((RS_ratio / SMA50(RS_ratio)) - 1.0) * 100.0
        """
        symbol = ticker.strip().upper()
        bench = benchmark.strip().upper()
        cache_key = f"{symbol}:{bench}"

        cached = self._cache.get(cache_key)
        if cached and (time.time() - cached.timestamp) < self.ttl:
            return cached.data

        if not yf:
            return None

        try:
            # Fetch ~4 months of daily data to have at least 50 bars for the RS SMA
            ticker_obj = yf.Ticker(symbol)
            bench_obj = yf.Ticker(bench)

            t_hist = ticker_obj.history(period="4mo", interval="1d")
            b_hist = bench_obj.history(period="4mo", interval="1d")

            if t_hist.empty or b_hist.empty or len(t_hist) < 20 or len(b_hist) < 20:
                return None

            # Align timestamps
            df = t_hist[["Close"]].rename(columns={"Close": "stock_close"}).join(
                b_hist[["Close"]].rename(columns={"Close": "bench_close"}),
                how="inner",
            ).dropna()

            if len(df) < 20:
                return None

            stock_prices = df["stock_close"].tolist()
            bench_prices = df["bench_close"].tolist()

            # RS Ratio
            rs_ratios = [s / b for s, b in zip(stock_prices, bench_prices)]

            # Mansfield RS over 50 bars (or all available if 20 <= len < 50)
            sma_len = min(50, len(rs_ratios))
            sma_val = sum(rs_ratios[-sma_len:]) / sma_len
            current_rs = rs_ratios[-1]
            mansfield_rs = round(((current_rs / sma_val) - 1.0) * 100.0, 2)

            # Performance calculations
            # 1 Month (~21 trading days)
            lookback_1m = min(21, len(stock_prices) - 1)
            stock_perf_1m = round(((stock_prices[-1] / stock_prices[-lookback_1m]) - 1.0) * 100.0, 2)
            bench_perf_1m = round(((bench_prices[-1] / bench_prices[-lookback_1m]) - 1.0) * 100.0, 2)
            alpha_1m = round(stock_perf_1m - bench_perf_1m, 2)

            # 3 Month (~63 trading days)
            lookback_3m = min(63, len(stock_prices) - 1)
            stock_perf_3m = round(((stock_prices[-1] / stock_prices[-lookback_3m]) - 1.0) * 100.0, 2)
            bench_perf_3m = round(((bench_prices[-1] / bench_prices[-lookback_3m]) - 1.0) * 100.0, 2)
            alpha_3m = round(stock_perf_3m - bench_perf_3m, 2)

            # 20 EMA check for divergence
            def calc_ema(prices: List[float], span: int = 20) -> float:
                if len(prices) < span:
                    return prices[-1]
                alpha = 2.0 / (span + 1)
                val = prices[0]
                for p in prices[1:]:
                    val = alpha * p + (1.0 - alpha) * val
                return val

            stock_ema20 = calc_ema(stock_prices, 20)
            bench_ema20 = calc_ema(bench_prices, 20)
            stock_above_ema20 = stock_prices[-1] > stock_ema20
            bench_above_ema20 = bench_prices[-1] > bench_ema20

            # Divergent strength: stock above 20 EMA while benchmark is below
            divergent_strength = bool(stock_above_ema20 and not bench_above_ema20)

            # Quality classification
            if mansfield_rs >= 5.0 and alpha_1m > 3.0:
                status = "leader"
                badge = "🔥 Starker Leader"
                bias = "Institutional Accumulation"
            elif mansfield_rs > 0.0:
                status = "outperformer"
                badge = "⭐ Outperformer"
                bias = "Moderate Relative Strength"
            elif mansfield_rs >= -3.0:
                status = "in_line"
                badge = "⚖️ Marktkonform"
                bias = "Neutral vs SPY"
            else:
                status = "laggard"
                badge = "⚠️ Laggard (Schwächer als Markt)"
                bias = "Underperformance"

            result = {
                "ticker": symbol,
                "benchmark": bench,
                "spot_price": round(stock_prices[-1], 2),
                "mansfield_rs": mansfield_rs,
                "alpha_1m": alpha_1m,
                "alpha_3m": alpha_3m,
                "stock_perf_1m": stock_perf_1m,
                "bench_perf_1m": bench_perf_1m,
                "stock_perf_3m": stock_perf_3m,
                "bench_perf_3m": bench_perf_3m,
                "stock_above_ema20": stock_above_ema20,
                "bench_above_ema20": bench_above_ema20,
                "divergent_strength": divergent_strength,
                "status": status,
                "badge": badge,
                "bias": bias,
            }

            self._cache[cache_key] = _RSCache(time.time(), result)
            return result

        except Exception as exc:
            logger.debug("Relative strength computation error for %s: %s", symbol, exc)
            return None

    def scan_relative_strength(
        self,
        watchlist: List[str],
        benchmark: str = "SPY",
        min_mansfield: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Scans a watchlist against the benchmark and ranks by Mansfield RS.
        """
        results: List[Dict[str, Any]] = []
        for symbol in watchlist:
            if not symbol or symbol.upper() == benchmark.upper():
                continue
            res = self.compute_relative_strength(symbol, benchmark=benchmark)
            if res:
                if min_mansfield is not None and res["mansfield_rs"] < min_mansfield:
                    continue
                results.append(res)

        results.sort(key=lambda x: x["mansfield_rs"], reverse=True)
        return results

    def format_telegram_rs_card(self, leaders: List[Dict[str, Any]], benchmark: str = "SPY") -> str:
        """Formats a smartphone card for Telegram."""
        if not leaders:
            return f"ℹ️ Keine Relative-Stärke-Daten verfügbar (Vergleichsindex: {benchmark})."

        lines = [
            f"💪 <b>RELATIVE STÄRKE VS. {benchmark} (LEADERS)</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "<i>Titel, die sich bei Marktkorrekturen weigern zu fallen (Institutionelle Akkumulation):</i>\n",
        ]

        for i, item in enumerate(leaders[:8], 1):
            t = item["ticker"]
            m_rs = item["mansfield_rs"]
            a_1m = item["alpha_1m"]
            badge = item["badge"]
            div = " ⚡ [Stark trotz Markt]" if item.get("divergent_strength") else ""

            lines.append(
                f"<b>{i}. {t}</b>: <b>{m_rs:+.1f}% RS</b> | Alpha 1M: <b>{a_1m:+.1f}%</b> {badge}{div}"
            )

        lines.append("\n💡 <b>Regel:</b> Kaufe bei Marktrücksetzern nur die Top-Leader mit positivem RS.")
        return "\n".join(lines)
