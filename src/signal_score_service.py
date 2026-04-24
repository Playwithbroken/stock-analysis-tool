from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import yfinance as yf

from src.discovery_service import DiscoveryService


class SignalScoreService:
    def __init__(self) -> None:
        self.discovery_service = DiscoveryService()

    def build_conviction_index(
        self,
        snapshot: Dict[str, Any],
        settings: Dict[str, Any] | None = None,
    ) -> Dict[Any, float]:
        settings = settings or {}
        weights = settings.get("weights") or {
            "source": 0.35,
            "timing": 0.30,
            "conviction": 0.35,
        }
        min_score = float(settings.get("high_conviction_min_score") or 75)
        equities = self._score_equity_signals(snapshot.get("ticker_signals", []), weights)
        politics = self._score_politician_signals(snapshot.get("politician_signals", []), weights)
        allowed: Dict[Any, float] = {}
        for item in equities:
            if float(item.get("total_score") or 0) >= min_score and item.get("ticker"):
                allowed[("ticker", item.get("ticker"))] = float(item.get("total_score"))
        for item in politics:
            if float(item.get("total_score") or 0) >= min_score:
                allowed[("politician", item.get("label"), item.get("ticker"))] = float(item.get("total_score"))
        return allowed

    async def build_scoreboard(self, snapshot: Dict[str, Any], settings: Dict[str, Any] | None = None) -> Dict[str, Any]:
        settings = settings or {}
        weights = settings.get("weights") or {
            "source": 0.35,
            "timing": 0.30,
            "conviction": 0.35,
        }
        equities = self._score_equity_signals(snapshot.get("ticker_signals", []), weights)
        politics = self._score_politician_signals(snapshot.get("politician_signals", []), weights)
        etfs = self._score_etfs(await self.discovery_service.get_etfs(), weights)
        crypto = self._score_crypto(await self.discovery_service.get_cryptos(), weights)
        performance = self._build_post_signal_performance(snapshot)

        top_ideas = sorted(
            [
                *[{"bucket": "equity", **item} for item in equities[:6]],
                *[{"bucket": "politics", **item} for item in politics[:6]],
                *[{"bucket": "etf", **item} for item in etfs[:6]],
                *[{"bucket": "crypto", **item} for item in crypto[:6]],
            ],
            key=lambda item: item.get("total_score", 0),
            reverse=True,
        )[:8]

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "top_ideas": top_ideas,
            "equities": equities[:8],
            "politics": politics[:8],
            "etfs": etfs[:8],
            "crypto": crypto[:8],
            "performance": performance[:8],
            "settings": settings,
        }

    def _weighted_total(self, source_quality: float, timing_quality: float, conviction: float, weights: Dict[str, float]) -> float:
        return round(
            source_quality * float(weights.get("source", 0.35))
            + timing_quality * float(weights.get("timing", 0.30))
            + conviction * float(weights.get("conviction", 0.35)),
            1,
        )

    def _score_equity_signals(self, signals: List[Dict[str, Any]], weights: Dict[str, float]) -> List[Dict[str, Any]]:
        scored = []
        for signal in signals:
            event = next((item for item in signal.get("events", []) if item.get("shares")), None)
            if not event:
                continue
            source_quality = 94
            timing_quality = max(20, 100 - int(event.get("delay_days") or 35) * 2)
            conviction = 55
            owner_title = (event.get("owner_title") or "").lower()
            if any(term in owner_title for term in ["chief executive", "ceo", "chief financial", "cfo"]):
                conviction += 25
            elif "director" in owner_title:
                conviction += 12
            if event.get("action") == "buy":
                conviction += 15
            shares = float(event.get("shares") or 0)
            if shares > 100000:
                conviction += 10
            elif shares > 10000:
                conviction += 5
            total = self._weighted_total(source_quality, timing_quality, min(conviction, 100), weights)
            scored.append(
                {
                    "ticker": signal.get("ticker"),
                    "label": signal.get("ticker"),
                    "headline": f"{event.get('action', '').upper()} by {event.get('owner_name')}",
                    "source_quality": source_quality,
                    "timing_quality": timing_quality,
                    "conviction_score": min(conviction, 100),
                    "total_score": total,
                    "source_label": "SEC Form 4",
                    "trade_date": event.get("trade_date"),
                    "delay_days": event.get("delay_days"),
                    "action": event.get("action"),
                    "detail": owner_title or "insider",
                }
            )
        return sorted(scored, key=lambda item: item["total_score"], reverse=True)

    def _score_politician_signals(self, signals: List[Dict[str, Any]], weights: Dict[str, float]) -> List[Dict[str, Any]]:
        scored = []
        for signal in signals:
            trades = signal.get("trades", [])
            if not trades:
                continue
            latest = trades[0]
            summary = signal.get("summary", {})
            playbook = signal.get("playbook") or {}
            source_quality = 88
            delay = latest.get("delay_days")
            avg_delay = summary.get("avg_delay_days")
            timing_quality = max(15, 100 - int(delay if delay is not None else avg_delay or 45) * 2)
            conviction = 45
            conviction += min(20, int(summary.get("buy_count") or 0) * 8)
            conviction += min(10, int(summary.get("report_count") or 0) * 3)
            if latest.get("action") == "buy":
                conviction += 10
            exposure = float(summary.get("estimated_exposure") or playbook.get("estimated_exposure") or latest.get("amount_midpoint") or 0)
            if exposure >= 250_000:
                conviction += 12
            elif exposure >= 50_000:
                conviction += 7
            elif exposure >= 15_000:
                conviction += 3
            same_ticker_count = sum(
                1
                for trade in trades
                if trade.get("ticker") and trade.get("ticker") == latest.get("ticker")
            )
            if same_ticker_count >= 3:
                conviction += 8
            elif same_ticker_count >= 2:
                conviction += 4
            if playbook.get("signal_grade") == "fresh_copy_candidate":
                timing_quality = max(timing_quality, 72)
                conviction += 6
            elif playbook.get("signal_grade") == "watch_only":
                conviction -= 6
            total = self._weighted_total(source_quality, timing_quality, min(conviction, 100), weights)
            target = latest.get("ticker") or latest.get("asset")
            next_action = playbook.get("next_action") or (
                f"Open {latest.get('ticker')} and compare price versus trade date."
                if latest.get("ticker")
                else "Treat as delayed theme intelligence."
            )
            scored.append(
                {
                    "ticker": latest.get("ticker"),
                    "label": signal.get("name"),
                    "headline": f"Congress PTR {latest.get('action', '').upper()} {target}",
                    "source_quality": source_quality,
                    "timing_quality": timing_quality,
                    "conviction_score": min(conviction, 100),
                    "total_score": total,
                    "source_label": "Official House PTR",
                    "trade_date": latest.get("trade_date"),
                    "delay_days": delay,
                    "action": latest.get("action"),
                    "amount_range": latest.get("amount_range"),
                    "estimated_exposure": exposure,
                    "estimated_exposure_label": summary.get("estimated_exposure_label") or playbook.get("estimated_exposure_label"),
                    "top_tickers": summary.get("top_tickers") or playbook.get("top_tickers") or [],
                    "signal_grade": playbook.get("signal_grade"),
                    "freshness": playbook.get("freshness"),
                    "next_action": next_action,
                    "playbook": playbook,
                    "compliance_note": playbook.get("compliance_note") or "Official PTR data is delayed.",
                    "detail": f"{summary.get('buy_count', 0)} buys / {summary.get('sell_count', 0)} sells · {latest.get('amount_range') or 'amount n/a'}",
                }
            )
        return sorted(scored, key=lambda item: item["total_score"], reverse=True)

    def _score_etfs(self, items: List[Dict[str, Any]], weights: Dict[str, float]) -> List[Dict[str, Any]]:
        scored = []
        for item in items:
            ter = float(item.get("ter") or 0.45)
            change = float(item.get("change") or 0)
            assets = float(item.get("total_assets") or 0)
            quality = max(20, 100 - ter * 220)
            liquidity = 40
            if assets > 50_000_000_000:
                liquidity = 95
            elif assets > 10_000_000_000:
                liquidity = 82
            elif assets > 1_000_000_000:
                liquidity = 68
            flow = max(20, min(95, 50 + change * 7))
            total = self._weighted_total(quality, flow, liquidity, weights)
            scored.append(
                {
                    "ticker": item.get("ticker"),
                    "label": item.get("ticker"),
                    "headline": item.get("name"),
                    "source_quality": quality,
                    "timing_quality": flow,
                    "conviction_score": liquidity,
                    "total_score": total,
                    "detail": f"TER {ter:.2f}% · {item.get('category') or 'ETF'}",
                    "change": change,
                }
            )
        return sorted(scored, key=lambda item: item["total_score"], reverse=True)

    def _score_crypto(self, items: List[Dict[str, Any]], weights: Dict[str, float]) -> List[Dict[str, Any]]:
        scored = []
        for item in items:
            change = float(item.get("change") or 0)
            momentum = max(15, min(95, 50 + change * 8))
            source_quality = 62
            risk_adjustment = 72 if item.get("ticker") in {"BTC-USD", "ETH-USD"} else 48
            total = self._weighted_total(source_quality, momentum, risk_adjustment, weights)
            scored.append(
                {
                    "ticker": item.get("ticker"),
                    "label": item.get("ticker"),
                    "headline": item.get("name"),
                    "source_quality": source_quality,
                    "timing_quality": momentum,
                    "conviction_score": risk_adjustment,
                    "total_score": total,
                    "detail": item.get("trend_context") or "crypto flow",
                    "change": change,
                }
            )
        return sorted(scored, key=lambda item: item["total_score"], reverse=True)

    def _build_post_signal_performance(self, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        candidates: List[Dict[str, Any]] = []

        for signal in snapshot.get("ticker_signals", []):
            event = next((item for item in signal.get("events", []) if item.get("trade_date")), None)
            if event and signal.get("ticker"):
                candidates.append(
                    {
                        "kind": "equity",
                        "label": signal.get("ticker"),
                        "ticker": signal.get("ticker"),
                        "trade_date": event.get("trade_date"),
                        "headline": f"{event.get('action', '').upper()} by {event.get('owner_name')}",
                    }
                )

        for signal in snapshot.get("politician_signals", []):
            trade = next((item for item in signal.get("trades", []) if item.get("trade_date") and item.get("ticker")), None)
            if trade:
                candidates.append(
                    {
                        "kind": "politics",
                        "label": signal.get("name"),
                        "ticker": trade.get("ticker"),
                        "trade_date": trade.get("trade_date"),
                        "headline": f"{trade.get('action', '').upper()} {trade.get('ticker')}",
                    }
                )

        for candidate in candidates[:8]:
            perf = self._performance_since(candidate["ticker"], candidate["trade_date"])
            if perf is None:
                continue
            items.append(
                {
                    **candidate,
                    "performance_pct": round(perf, 2),
                }
            )
        items.sort(key=lambda item: abs(item.get("performance_pct", 0)), reverse=True)
        return items

    def _performance_since(self, ticker: str, trade_date: str | None) -> Optional[float]:
        if not ticker or not trade_date:
            return None
        try:
            start_date = datetime.fromisoformat(trade_date).date()
        except ValueError:
            return None
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(
                start=(start_date - timedelta(days=5)).isoformat(),
                end=(datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat(),
                interval="1d",
            )
            if hist.empty:
                return None
            entry_price = float(hist["Close"].iloc[0])
            latest_price = float(hist["Close"].iloc[-1])
            if entry_price == 0:
                return None
            return ((latest_price / entry_price) - 1) * 100
        except Exception:
            return None
