from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd

from src.data_fetcher import DataFetcher


class TradingIntelligenceService:
    DEFAULT_TICKERS = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "BTC-USD"]

    def build_snapshot(self, watchlist_snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
        tickers = self._pick_tickers(watchlist_snapshot or {})
        indicators = [item for item in (self._build_indicator_item(ticker) for ticker in tickers) if item]
        rules = self._build_rules()
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "indicators": indicators,
            "rules": rules,
        }

    def _pick_tickers(self, snapshot: Dict[str, Any]) -> List[str]:
        selected: List[str] = []
        for signal in snapshot.get("ticker_signals", [])[:4]:
            ticker = (signal.get("ticker") or "").upper()
            if ticker and ticker not in selected:
                selected.append(ticker)
        for signal in snapshot.get("politician_signals", [])[:3]:
            for trade in signal.get("trades", []):
                ticker = (trade.get("ticker") or "").upper()
                if ticker and ticker not in selected:
                    selected.append(ticker)
                    break
        for item in self.DEFAULT_TICKERS:
            if item not in selected:
                selected.append(item)
        return selected[:8]

    def _build_indicator_item(self, ticker: str) -> Dict[str, Any] | None:
        try:
            fetcher = DataFetcher(ticker)
            hist = fetcher.stock.history(period="6mo", interval="1d")
            if hist.empty or len(hist) < 40:
                return None

            intraday = fetcher.stock.history(period="1d", interval="5m", prepost=True)

            close = hist["Close"].astype(float)
            high = hist["High"].astype(float)
            low = hist["Low"].astype(float)
            volume = hist["Volume"].astype(float)

            ema_20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
            ema_50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
            ema_200 = close.ewm(span=200, adjust=False).mean().iloc[-1]
            rsi_14 = self._rsi(close, 14)
            atr_14 = self._atr(high, low, close, 14)
            current = float(close.iloc[-1])
            avg_volume_20 = float(volume.tail(20).mean()) if volume.tail(20).mean() else 0
            volume_ratio = round(float(volume.iloc[-1]) / avg_volume_20, 2) if avg_volume_20 else 0
            gap_pct = self._gap_pct(close)
            intraday_levels = self._intraday_levels(intraday)
            breakout = self._breakout_state(close, high, low)

            signal = "neutral"
            rationale: List[str] = []
            if current > ema_20 > ema_50 and rsi_14 < 72:
                signal = "long"
                rationale.append("trend above EMA20 and EMA50")
            if current < ema_20 < ema_50 and rsi_14 > 32:
                signal = "short"
                rationale = ["trend below EMA20 and EMA50"]
            if volume_ratio >= 1.4:
                rationale.append("volume confirmation")
            if gap_pct >= 2:
                rationale.append("opening gap strength")
            elif gap_pct <= -2:
                rationale.append("opening gap weakness")
            if breakout["status"] != "range":
                rationale.append(breakout["label"])
            if rsi_14 >= 72:
                rationale.append("overbought risk")
            elif rsi_14 <= 32:
                rationale.append("oversold risk")

            price_data = fetcher.get_price_data()
            return {
                "ticker": ticker,
                "price": round(current, 2),
                "ema_20": round(float(ema_20), 2),
                "ema_50": round(float(ema_50), 2),
                "ema_200": round(float(ema_200), 2),
                "rsi_14": round(float(rsi_14), 1),
                "atr_14": round(float(atr_14), 2),
                "volume_ratio": volume_ratio,
                "vwap": intraday_levels["vwap"],
                "premarket_high": intraday_levels["premarket_high"],
                "premarket_low": intraday_levels["premarket_low"],
                "gap_pct": gap_pct,
                "breakout_status": breakout["status"],
                "breakout_label": breakout["label"],
                "support_level": breakout["support_level"],
                "resistance_level": breakout["resistance_level"],
                "change_1w": round(float(price_data.get("change_1w") or 0), 2),
                "from_52w_high": round(float(price_data.get("from_52w_high") or 0), 2),
                "from_52w_low": round(float(price_data.get("from_52w_low") or 0), 2),
                "signal": signal,
                "rationale": rationale[:3],
            }
        except Exception:
            return None

    def _build_rules(self) -> Dict[str, List[str]]:
        return {
            "long_rules": [
                "Trade long only when price holds above EMA20 and EMA50.",
                "Prefer long only with RSI below 72 and volume ratio above 1.2.",
                "Favor long only if price reclaims or holds above VWAP after the open.",
                "Best longs start from premarket high reclaim or a clean 20-day breakout.",
                "Do not chase longs more than 4% above EMA20 without a fresh catalyst.",
                "If ATR is high, reduce size before increasing conviction.",
            ],
            "short_rules": [
                "Trade short only when price stays below EMA20 and EMA50.",
                "Avoid new shorts when RSI is already below 32 unless there is a catalyst.",
                "Favor shorts only if price loses VWAP and fails back below premarket low.",
                "Use breakdowns below 20-day support instead of blind fading strength.",
                "Use lower size on squeezable names with strong volume spikes.",
                "Do not short against a broad market open if SPY and QQQ are both above EMA20.",
            ],
            "risk_rules": [
                "Risk per trade must be defined before entry through stop and position size.",
                "Leverage is only for A-setups with strong trend and liquidity confirmation.",
                "Gap trades without VWAP confirmation should be treated as lower quality.",
                "Premarket extremes are reference levels, not automatic entries.",
                "If volume confirmation is missing, size down or skip the trade.",
                "No trade is better than a low-quality trade.",
            ],
        }

    def _rsi(self, close: pd.Series, window: int) -> float:
        delta = close.diff()
        gains = delta.clip(lower=0).rolling(window=window).mean()
        losses = (-delta.clip(upper=0)).rolling(window=window).mean()
        rs = gains / losses.replace(0, pd.NA)
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.dropna().iloc[-1]) if not rsi.dropna().empty else 50.0

    def _atr(self, high: pd.Series, low: pd.Series, close: pd.Series, window: int) -> float:
        prev_close = close.shift(1)
        true_range = pd.concat(
            [
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = true_range.rolling(window=window).mean()
        return float(atr.dropna().iloc[-1]) if not atr.dropna().empty else 0.0

    def _gap_pct(self, close: pd.Series) -> float:
        if len(close) < 2 or float(close.iloc[-2]) == 0:
            return 0.0
        return round(((float(close.iloc[-1]) / float(close.iloc[-2])) - 1) * 100, 2)

    def _intraday_levels(self, intraday: pd.DataFrame) -> Dict[str, float | None]:
        if intraday.empty:
            return {"vwap": None, "premarket_high": None, "premarket_low": None}
        frame = intraday.copy()
        frame.index = pd.to_datetime(frame.index)
        typical = (frame["High"].astype(float) + frame["Low"].astype(float) + frame["Close"].astype(float)) / 3
        cumulative_volume = frame["Volume"].astype(float).cumsum()
        vwap_series = ((typical * frame["Volume"].astype(float)).cumsum() / cumulative_volume.replace(0, pd.NA)).dropna()
        market_open = frame.index[-1].normalize() + pd.Timedelta(hours=14, minutes=30)
        premarket = frame[frame.index < market_open]
        return {
            "vwap": round(float(vwap_series.iloc[-1]), 2) if not vwap_series.empty else None,
            "premarket_high": round(float(premarket["High"].max()), 2) if not premarket.empty else None,
            "premarket_low": round(float(premarket["Low"].min()), 2) if not premarket.empty else None,
        }

    def _breakout_state(self, close: pd.Series, high: pd.Series, low: pd.Series) -> Dict[str, Any]:
        resistance = float(high.tail(20).max())
        support = float(low.tail(20).min())
        current = float(close.iloc[-1])
        if current >= resistance * 0.998:
            status = "breakout"
            label = "testing 20-day breakout"
        elif current <= support * 1.002:
            status = "breakdown"
            label = "testing 20-day breakdown"
        else:
            status = "range"
            label = "inside 20-day range"
        return {
            "status": status,
            "label": label,
            "support_level": round(support, 2),
            "resistance_level": round(resistance, 2),
        }
