from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.data_fetcher import DataFetcher
from src.discovery_service import DiscoveryService
from src.morning_brief_service import MorningBriefService


class SessionListService:
    SESSION_UNIVERSES = {
        "asia": {
            "label": "Asia",
            "equities": ["TSM", "BABA", "JD", "PDD", "NTES", "BIDU", "INFY", "HMC"],
            "etfs": ["AAXJ", "EWJ", "MCHI", "FXI"],
        },
        "europe": {
            "label": "Europe",
            "equities": ["ASML", "SAP", "NVO", "SHEL", "BP", "AZN", "UL", "ING"],
            "etfs": ["VGK", "EZU", "FEZ", "EWG"],
        },
        "usa": {
            "label": "USA",
            "equities": ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "PLTR"],
            "etfs": ["SPY", "QQQ", "IWM", "DIA"],
        },
    }
    CRYPTO = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD"]
    PHASES = {
        "pre_open": "Pre-Open",
        "post_open": "Post-Open",
        "end_of_day": "End of Day",
    }

    def __init__(self) -> None:
        self.discovery = DiscoveryService()
        self.brief_service = MorningBriefService()

    async def build_session_lists(self, snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
        brief = self.brief_service.get_brief(snapshot)
        sessions: Dict[str, Any] = {}
        for key, config in self.SESSION_UNIVERSES.items():
            sessions[key] = await self._build_session_payload(key, config, brief, snapshot or {})
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sessions": sessions,
        }

    async def _build_session_payload(
        self,
        region_key: str,
        config: Dict[str, Any],
        brief: Dict[str, Any],
        snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        equities = await self._collect_assets(config["equities"], kind="equity", snapshot=snapshot)
        etfs = await self._collect_assets(config["etfs"], kind="etf", snapshot=snapshot)
        crypto = await self._collect_assets(self.CRYPTO, kind="crypto", snapshot=snapshot)
        news = [
            item for item in (brief.get("top_news") or [])
            if item.get("region") in {region_key, "global"}
        ][:4]

        return {
            "label": config["label"],
            "phases": {
                phase_key: {
                    "label": phase_label,
                    "equities": self._rank_for_phase(equities, phase_key)[:6],
                    "etfs": self._rank_for_phase(etfs, phase_key)[:4],
                    "crypto": self._rank_for_phase(crypto, phase_key)[:4],
                    "news": news,
                }
                for phase_key, phase_label in self.PHASES.items()
            },
        }

    async def _collect_assets(
        self,
        tickers: List[str],
        kind: str,
        snapshot: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        tasks = [self._fetch_asset(ticker, kind, snapshot) for ticker in tickers]
        results = [item for item in await asyncio.gather(*tasks) if item]
        return results

    async def _fetch_asset(
        self,
        ticker: str,
        kind: str,
        snapshot: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        def fetch() -> Dict[str, Any] | None:
            try:
                data = DataFetcher(ticker)
                price = data.get_price_data()
                info = data.info
                signal_hit = self._signal_hit(snapshot, ticker)
                quality = 50
                if kind == "etf":
                    assets = float(info.get("totalAssets") or 0)
                    ter = float(info.get("annualReportExpenseRatio") or 0.45)
                    quality = max(25, min(95, 85 - ter * 200 + (10 if assets > 1_000_000_000 else 0)))
                elif kind == "crypto":
                    quality = 75 if ticker in {"BTC-USD", "ETH-USD"} else 55
                elif kind == "equity":
                    quality = 82 if signal_hit else 62
                return {
                    "ticker": ticker,
                    "label": info.get("shortName") or info.get("longName") or ticker,
                    "change_1w": float(price.get("change_1w") or 0),
                    "change_1m": float(price.get("change_1m") or 0),
                    "price": price.get("current_price"),
                    "signal_hit": signal_hit,
                    "quality": quality,
                    "kind": kind,
                }
            except Exception:
                return None

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, fetch)

    def _rank_for_phase(self, items: List[Dict[str, Any]], phase_key: str) -> List[Dict[str, Any]]:
        ranked = []
        for item in items:
            if phase_key == "pre_open":
                score = item["quality"] * 0.55 + item["change_1m"] * 1.5 + (12 if item["signal_hit"] else 0)
            elif phase_key == "post_open":
                score = item["quality"] * 0.35 + item["change_1w"] * 4 + (10 if item["signal_hit"] else 0)
            else:
                score = item["quality"] * 0.40 + abs(item["change_1w"]) * 3 + (8 if item["signal_hit"] else 0)
            ranked.append({**item, "phase_score": round(score, 1)})
        return sorted(ranked, key=lambda item: item["phase_score"], reverse=True)

    def _signal_hit(self, snapshot: Dict[str, Any], ticker: str) -> bool:
        ticker_upper = (ticker or "").upper()
        for signal in snapshot.get("ticker_signals", []):
            if (signal.get("ticker") or "").upper() == ticker_upper and signal.get("events"):
                return True
        for signal in snapshot.get("politician_signals", []):
            for trade in signal.get("trades", []):
                if (trade.get("ticker") or "").upper() == ticker_upper:
                    return True
        return False
