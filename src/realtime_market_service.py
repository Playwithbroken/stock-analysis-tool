from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from src.data_fetcher import DataFetcher


class RealtimeMarketService:
    MAX_SYMBOLS = 18

    def build_snapshot(self, symbols: List[str]) -> Dict[str, Any]:
        cleaned: List[str] = []
        for symbol in symbols:
            normalized = (symbol or "").strip().upper()
            if normalized and normalized not in cleaned:
                cleaned.append(normalized)
        cleaned = cleaned[: self.MAX_SYMBOLS]

        quotes = [item for item in (self._build_quote(symbol) for symbol in cleaned) if item]
        return {
            "type": "realtime_snapshot",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "quotes": quotes,
        }

    def _build_quote(self, symbol: str) -> Dict[str, Any] | None:
        try:
            fetcher = DataFetcher(symbol)
            price_data = fetcher.get_price_data()
            info = fetcher.info
            volatility = fetcher.get_volatility_data()
            news = fetcher.get_news()

            price = (
                price_data.get("current_price")
                or info.get("currentPrice")
                or info.get("regularMarketPrice")
            )
            if price is None:
                return None

            headline = None
            publisher = None
            if news:
                headline = news[0].get("title")
                publisher = news[0].get("publisher")

            return {
                "symbol": symbol,
                "price": round(float(price), 4),
                "change_1w": self._safe_round(price_data.get("change_1w")),
                "change_1m": self._safe_round(price_data.get("change_1m")),
                "volume_ratio": self._safe_round(volatility.get("volume_ratio")),
                "asset_class": self._infer_asset_class(symbol, info),
                "currency": info.get("currency") or price_data.get("currency") or "USD",
                "headline": headline,
                "publisher": publisher,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception:
            return None

    def _safe_round(self, value: Any, digits: int = 2) -> float | None:
        try:
            if value is None:
                return None
            return round(float(value), digits)
        except Exception:
            return None

    def _infer_asset_class(self, symbol: str, info: Dict[str, Any]) -> str:
        quote_type = (info.get("quoteType") or "").upper()
        if symbol.endswith("-USD") or quote_type == "CRYPTOCURRENCY":
            return "crypto"
        if quote_type == "ETF":
            return "etf"
        if quote_type in {"INDEX", "MUTUALFUND"} or symbol.startswith("^") or symbol.endswith("=F"):
            return "macro"
        return "equity"
