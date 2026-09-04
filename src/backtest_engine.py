"""
Backtest Engine — Statistical Strategy Validation & Expectancy Testing

Evaluates historical setups to separate real statistical alpha from curve-fitted noise.
Metrics:
  - Total Trades & Sample Size
  - Win Rate (%)
  - Profit Factor (Gross Gains / Gross Losses)
  - Mathematical Expectancy E[R] per trade
  - Max Drawdown (in R-multiples)
  - Average Win / Average Loss ratio
  - Statistical Edge Verdict: "Validated Edge" vs "Unproven / Negative Expectancy"
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore


@dataclass
class BacktestResult:
    strategy_name: str
    ticker: str
    sample_trades: int
    wins: int
    losses: int
    win_rate_pct: float
    profit_factor: float
    expectancy_r: float
    avg_win_r: float
    avg_loss_r: float
    max_consecutive_losses: int
    max_drawdown_r: float
    is_statistically_valid: bool
    verdict: str
    trade_log: List[Dict[str, Any]]


class BacktestEngine:
    def __init__(self, min_sample_size: int = 15, target_profit_factor: float = 1.35) -> None:
        self.min_sample_size = min_sample_size
        self.target_profit_factor = target_profit_factor

    def backtest_strategy(
        self,
        ticker: str,
        strategy: str = "volume_breakout",
        period: str = "2y",
        risk_per_trade_pct: float = 0.035,  # 3.5% stop distance
        target_r: float = 2.5,              # 2.5 : 1 R:R
        max_holding_bars: int = 15,
    ) -> Optional[Dict[str, Any]]:
        """
        Backtests a breakout / momentum strategy on historical daily bars.
        """
        symbol = ticker.strip().upper()
        if not yf:
            return None

        try:
            t = yf.Ticker(symbol)
            hist = t.history(period=period, interval="1d")
            if hist.empty or len(hist) < 60:
                return None

            closes = hist["Close"].astype(float).tolist()
            highs = hist["High"].astype(float).tolist()
            lows = hist["Low"].astype(float).tolist()
            volumes = hist["Volume"].astype(float).tolist()
            dates = [str(d)[:10] for d in hist.index]

            trades: List[Dict[str, Any]] = []

            # Simulate strategy across bars (skipping first 30 bars for indicator warmup)
            i = 30
            while i < len(closes) - max_holding_bars:
                # 20-day high and 20-day volume average
                prior_highs = highs[i - 20:i]
                prior_volumes = volumes[i - 20:i]
                ref_20_high = max(prior_highs) if prior_highs else closes[i]
                avg_vol_20 = sum(prior_volumes) / len(prior_volumes) if prior_volumes else volumes[i]

                current_close = closes[i]
                current_vol = volumes[i]

                trigger = False
                if strategy == "volume_breakout":
                    # Breakout above 20-day high on volume > 1.4x 20d average
                    if current_close > ref_20_high and avg_vol_20 > 0 and (current_vol / avg_vol_20) >= 1.35:
                        trigger = True
                elif strategy == "pullback_continuation":
                    # 50-day trend up, short term 3-day pullback into support
                    if i >= 50:
                        ma50 = sum(closes[i - 50:i]) / 50.0
                        if current_close > ma50 and closes[i - 1] < closes[i - 2] < closes[i - 3] and current_close > closes[i - 1]:
                            trigger = True
                else:
                    # Default simple momentum
                    if current_close > ref_20_high:
                        trigger = True

                if trigger:
                    entry_price = current_close
                    stop_loss = entry_price * (1.0 - risk_per_trade_pct)
                    target_price = entry_price + (entry_price - stop_loss) * target_r
                    risk_amount = entry_price - stop_loss

                    # Track trade forward
                    exit_price = entry_price
                    exit_date = dates[i]
                    outcome = "timeout"
                    r_multiple = 0.0

                    for step in range(1, max_holding_bars + 1):
                        bar_idx = i + step
                        h = highs[bar_idx]
                        l = lows[bar_idx]
                        c = closes[bar_idx]

                        # Check Stop Loss first (conservative)
                        if l <= stop_loss:
                            exit_price = stop_loss
                            exit_date = dates[bar_idx]
                            outcome = "loss"
                            r_multiple = -1.0
                            i = bar_idx  # advance pointer to avoid overlapping same trade
                            break
                        # Check Target
                        elif h >= target_price:
                            exit_price = target_price
                            exit_date = dates[bar_idx]
                            outcome = "win"
                            r_multiple = target_r
                            i = bar_idx
                            break
                    else:
                        # Holding period timeout: exit at last close
                        last_c = closes[i + max_holding_bars]
                        exit_price = last_c
                        exit_date = dates[i + max_holding_bars]
                        r_multiple = round((exit_price - entry_price) / risk_amount, 2)
                        outcome = "win" if r_multiple > 0 else "loss"
                        i += max_holding_bars

                    trades.append({
                        "entry_date": dates[i],
                        "entry_price": round(entry_price, 2),
                        "exit_date": exit_date,
                        "exit_price": round(exit_price, 2),
                        "outcome": outcome,
                        "r_multiple": r_multiple,
                    })

                i += 1

            if not trades:
                return {
                    "strategy_name": strategy,
                    "ticker": symbol,
                    "sample_trades": 0,
                    "win_rate_pct": 0.0,
                    "profit_factor": 0.0,
                    "expectancy_r": 0.0,
                    "verdict": "Insufficient historical setups to establish edge.",
                    "trade_log": [],
                }

            wins = [t for t in trades if t["r_multiple"] > 0]
            losses = [t for t in trades if t["r_multiple"] <= 0]
            win_count = len(wins)
            loss_count = len(losses)
            total_count = len(trades)

            win_rate = (win_count / total_count) * 100.0 if total_count > 0 else 0.0
            sum_gains = sum(t["r_multiple"] for t in wins)
            sum_losses = abs(sum(t["r_multiple"] for t in losses))

            profit_factor = (sum_gains / sum_losses) if sum_losses > 0 else (99.0 if sum_gains > 0 else 0.0)
            avg_win = (sum_gains / win_count) if win_count > 0 else 0.0
            avg_loss = (sum_losses / loss_count) if loss_count > 0 else 0.0

            expectancy_r = round((sum_gains - sum_losses) / total_count, 2) if total_count > 0 else 0.0

            # Max Drawdown in R
            cum_r = 0.0
            peak_r = 0.0
            max_dd_r = 0.0
            consec_losses = 0
            max_consec_losses = 0

            for t in trades:
                r = t["r_multiple"]
                cum_r += r
                if cum_r > peak_r:
                    peak_r = cum_r
                dd = peak_r - cum_r
                if dd > max_dd_r:
                    max_dd_r = dd
                if r <= 0:
                    consec_losses += 1
                    if consec_losses > max_consec_losses:
                        max_consec_losses = consec_losses
                else:
                    consec_losses = 0

            is_valid = (
                total_count >= self.min_sample_size
                and profit_factor >= self.target_profit_factor
                and expectancy_r >= 0.20
            )

            if is_valid:
                verdict = (
                    f"✅ STATISTICALLY VALIDATED EDGE: Expectancy +{expectancy_r:.2f}R per trade, "
                    f"Profit Factor {profit_factor:.2f}, Win Rate {win_rate:.1f}% über {total_count} Trades."
                )
            elif total_count < self.min_sample_size:
                verdict = f"⚠️ Unzureichende Stichprobe ({total_count}/{self.min_sample_size} Trades)."
            else:
                verdict = (
                    f"❌ KEINE EDGE: Profit Factor {profit_factor:.2f} oder Erwartungswert {expectancy_r:+.2f}R "
                    f"unter Schwellenwert. Setup sollte nicht ungefiltert gehandelt werden."
                )

            return {
                "strategy_name": strategy,
                "ticker": symbol,
                "period": period,
                "sample_trades": total_count,
                "wins": win_count,
                "losses": loss_count,
                "win_rate_pct": round(win_rate, 1),
                "profit_factor": round(profit_factor, 2),
                "expectancy_r": expectancy_r,
                "avg_win_r": round(avg_win, 2),
                "avg_loss_r": round(avg_loss, 2),
                "max_consecutive_losses": max_consec_losses,
                "max_drawdown_r": round(max_dd_r, 2),
                "is_statistically_valid": is_valid,
                "verdict": verdict,
                "trade_log": trades[-10:],  # last 10 trades
            }

        except Exception as exc:
            logger.error("Failed backtest for %s: %s", symbol, exc)
            return None
