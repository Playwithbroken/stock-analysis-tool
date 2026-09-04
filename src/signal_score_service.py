from __future__ import annotations

import asyncio
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
        filing_equities = self._score_equity_signals(snapshot.get("ticker_signals", []), weights)
        politics = self._score_politician_signals(snapshot.get("politician_signals", []), weights)
        equity_rows, etf_rows, crypto_rows = await asyncio.gather(
            self.discovery_service.get_paper_equity_candidates(),
            self.discovery_service.get_etfs(),
            self.discovery_service.get_cryptos(),
        )
        market_equities = self._score_market_equities(equity_rows, weights)
        small_cap_equities = [
            item
            for item in market_equities
            if 0 < float((item.get("market_evidence") or {}).get("market_cap") or 0) < 5_000_000_000
        ]
        equity_by_ticker: Dict[str, Dict[str, Any]] = {}
        for item in [*filing_equities, *market_equities]:
            ticker = str(item.get("ticker") or "").upper()
            if not ticker:
                continue
            previous = equity_by_ticker.get(ticker)
            if previous is None or float(item.get("total_score") or 0) > float(previous.get("total_score") or 0):
                equity_by_ticker[ticker] = item
        equities = sorted(equity_by_ticker.values(), key=lambda item: float(item.get("total_score") or 0), reverse=True)
        etfs = self._score_etfs(etf_rows, weights)
        crypto = self._score_crypto(crypto_rows, weights)
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
            "market_equities": market_equities[:12],
            "small_cap_equities": small_cap_equities[:8],
            "politics": politics[:8],
            "etfs": etfs[:8],
            "crypto": crypto[:8],
            "performance": performance[:8],
            "equity_feed": {
                "status": "loaded" if market_equities else "unavailable",
                "filing_candidates": len(filing_equities),
                "broad_market_candidates": len(market_equities),
                "small_cap_candidates": len(small_cap_equities),
                "method": "deterministic diversified universe; 1d/1m/3m trend, moving averages, volume, volatility and available fundamentals",
                "research_only": True,
            },
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
                    "detail": f"{summary.get('buy_count', 0)} buys / {summary.get('sell_count', 0)} sells / {latest.get('amount_range') or 'amount offen'}",
                }
            )
        return sorted(scored, key=lambda item: item["total_score"], reverse=True)

    def _score_market_equities(self, items: List[Dict[str, Any]], weights: Dict[str, float]) -> List[Dict[str, Any]]:
        scored: List[Dict[str, Any]] = []
        for item in items:
            ticker = str(item.get("ticker") or "").upper()
            price = item.get("price")
            if not ticker or not isinstance(price, (int, float)) or float(price) <= 0:
                continue
            change_1m = float(item.get("change_1m") or 0)
            change_3m = float(item.get("change_3m") or 0)
            volume_ratio = float(item.get("volume_ratio") or 1)
            revenue_growth = item.get("revenue_growth_pct")
            earnings_growth = item.get("earnings_growth_pct")
            profit_margin = item.get("profit_margin_pct")
            market_cap = float(item.get("market_cap") or 0)
            volatility = item.get("volatility_annual_pct")

            quality = 48.0
            if market_cap >= 200_000_000_000:
                quality += 16
            elif market_cap >= 20_000_000_000:
                quality += 10
            elif market_cap >= 2_000_000_000:
                quality += 5
            if isinstance(profit_margin, (int, float)):
                quality += max(-8, min(16, float(profit_margin) * 0.45))
            if isinstance(revenue_growth, (int, float)):
                quality += max(-8, min(12, float(revenue_growth) * 0.35))
            if isinstance(earnings_growth, (int, float)):
                quality += max(-8, min(12, float(earnings_growth) * 0.20))

            timing = 45.0 + max(-18, min(20, change_1m * 1.8)) + max(-10, min(15, change_3m * 0.45))
            timing += max(-5, min(10, (volume_ratio - 1.0) * 12))
            conviction = 42.0
            conviction += 14 if item.get("above_sma20") else -10
            conviction += 16 if item.get("above_sma50") else -12
            if isinstance(volatility, (int, float)):
                conviction += 8 if float(volatility) <= 35 else -8 if float(volatility) >= 65 else 0
            total = self._weighted_total(
                max(15, min(98, quality)),
                max(15, min(98, timing)),
                max(15, min(98, conviction)),
                weights,
            )
            if not item.get("above_sma20") and not item.get("above_sma50") and change_1m < 0:
                continue
            scored.append(
                {
                    "ticker": ticker,
                    "label": item.get("name") or ticker,
                    "headline": f"Broad equity quality/momentum screen: {item.get('sector') or 'Unknown'}",
                    "source_quality": round(max(15, min(98, quality)), 1),
                    "timing_quality": round(max(15, min(98, timing)), 1),
                    "conviction_score": round(max(15, min(98, conviction)), 1),
                    "total_score": total,
                    "source_label": item.get("source_label") or "Yahoo Finance market/fundamental snapshot",
                    "action": "buy",
                    "signal_type": "broad_equity_quality_momentum",
                    "trade_date": item.get("data_as_of"),
                    "delay_days": 0,
                    "detail": (
                        f"1M {change_1m:+.1f}% / 3M {change_3m:+.1f}% / Volumen x{volume_ratio:.2f} / "
                        f"Marge {float(profit_margin):.1f}%" if isinstance(profit_margin, (int, float)) else
                        f"1M {change_1m:+.1f}% / 3M {change_3m:+.1f}% / Volumen x{volume_ratio:.2f} / Marge offen"
                    ),
                    "market_evidence": item,
                    "data_quality": {
                        "status": "complete" if all(
                            isinstance(item.get(key), (int, float))
                            for key in ("change_1m", "change_3m", "volume_ratio", "market_cap")
                        ) else "partial",
                        "fundamentals_available": any(
                            isinstance(item.get(key), (int, float))
                            for key in ("revenue_growth_pct", "earnings_growth_pct", "profit_margin_pct")
                        ),
                        "research_only": True,
                    },
                }
            )
        return sorted(scored, key=lambda item: float(item.get("total_score") or 0), reverse=True)

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
                    "detail": f"TER {ter:.2f}% / {item.get('category') or 'ETF'}",
                    "change": change,
                    "asset_evidence": {
                        "source": item.get("source"),
                        "data_as_of": item.get("data_as_of"),
                        "fallback": bool(item.get("fallback")),
                        "category": item.get("category"),
                        "expense_ratio": item.get("ter"),
                        "total_assets": item.get("total_assets"),
                        "change_1w_pct": item.get("change"),
                    },
                }
            )
        return sorted(scored, key=lambda item: item["total_score"], reverse=True)

    def _score_crypto(self, items: List[Dict[str, Any]], weights: Dict[str, float]) -> List[Dict[str, Any]]:
        scored = []
        for item in items:
            change = float(item.get("change") or 0)
            long_momentum = max(15, min(95, 50 + change * 8))
            short_momentum = max(15, min(95, 50 - change * 8))
            source_quality = 62
            risk_adjustment = 72 if item.get("ticker") in {"BTC-USD", "ETH-USD"} else 48
            long_total = self._weighted_total(source_quality, long_momentum, risk_adjustment, weights)
            short_total = self._weighted_total(source_quality, short_momentum, risk_adjustment, weights)
            directional_bias = "short" if change <= -1.0 else "long"
            momentum = short_momentum if directional_bias == "short" else long_momentum
            total = short_total if directional_bias == "short" else long_total
            scored.append(
                {
                    "ticker": item.get("ticker"),
                    "label": item.get("ticker"),
                    "headline": item.get("name"),
                    "source_quality": source_quality,
                    "timing_quality": momentum,
                    "conviction_score": risk_adjustment,
                    "total_score": total,
                    "long_score": long_total,
                    "short_score": short_total,
                    "directional_bias": directional_bias,
                    "detail": item.get("trend_context") or "crypto flow",
                    "change": change,
                    "asset_evidence": {
                        "source": item.get("source"),
                        "data_as_of": item.get("data_as_of"),
                        "fallback": bool(item.get("fallback")),
                        "trading_pair": item.get("ticker"),
                        "change_1w_pct": item.get("change"),
                        "price": item.get("price"),
                    },
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
