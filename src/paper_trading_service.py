from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import yfinance as yf

from src.storage import PortfolioManager


class PaperTradingService:
    def __init__(self, portfolio_manager: PortfolioManager) -> None:
        self.portfolio_manager = portfolio_manager

    def build_dashboard(self, scoreboard: Dict[str, Any], settings: Dict[str, Any] | None = None) -> Dict[str, Any]:
        settings = settings or {}
        rules = settings.get("do_not_trade") or {}
        playbooks = self._build_playbooks(scoreboard, rules)
        trades = self._enrich_trades(self.portfolio_manager.list_paper_trades(limit=150))
        open_trades = [trade for trade in trades if trade.get("status") == "open"]
        closed_trades = [trade for trade in trades if trade.get("status") == "closed"]
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "playbooks": playbooks,
            "open_trades": open_trades[:12],
            "closed_trades": closed_trades[:12],
            "stats": self._build_stats(trades),
            "setup_performance": self._build_setup_performance(closed_trades),
            "journal": self._build_journal(trades),
            "rules": rules,
        }

    def create_trade_from_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        trade = self.portfolio_manager.create_paper_trade(payload)
        return self._enrich_trade(trade)

    def create_trade_from_playbook(
        self,
        payload: Dict[str, Any],
        scoreboard: Dict[str, Any],
        settings: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        playbook_id = payload.get("playbook_id")
        direction = (payload.get("direction") or "long").lower()
        quantity = float(payload.get("quantity") or 1)
        leverage = float(payload.get("leverage") or 1)
        rules = (settings or {}).get("do_not_trade") or {}
        playbooks = self._build_playbooks(scoreboard, rules)
        playbook = next((item for item in playbooks if item.get("id") == playbook_id), None)
        if not playbook:
            raise ValueError("Playbook not found.")
        if playbook.get("do_not_trade_reasons"):
            raise ValueError("Playbook is blocked by do-not-trade rules.")

        last_price = self._get_last_price(playbook.get("ticker")) or float(playbook.get("reference_price") or 0)
        if last_price <= 0:
            raise ValueError("No valid market price available for this playbook.")

        risk_buffer = float(playbook.get("risk_buffer_pct") or 3.5) / 100
        reward_buffer = float(playbook.get("reward_buffer_pct") or 7.0) / 100
        stop_price = last_price * (1 - risk_buffer) if direction == "long" else last_price * (1 + risk_buffer)
        target_price = last_price * (1 + reward_buffer) if direction == "long" else last_price * (1 - reward_buffer)
        created = self.portfolio_manager.create_paper_trade(
            {
                "ticker": playbook["ticker"],
                "asset_class": playbook.get("asset_class") or "equity",
                "direction": direction,
                "setup_type": playbook.get("setup_type") or "signal_playbook",
                "thesis": playbook.get("thesis"),
                "entry_price": last_price,
                "stop_price": stop_price,
                "target_price": target_price,
                "quantity": quantity,
                "confidence_score": playbook.get("score"),
                "leverage": leverage,
                "notes": playbook.get("headline"),
            }
        )
        return self._enrich_trade(created)

    def close_trade(
        self,
        trade_id: str,
        closed_price: Optional[float] = None,
        notes: Optional[str] = None,
        exit_reason: Optional[str] = None,
        lessons_learned: Optional[str] = None,
    ) -> Dict[str, Any]:
        existing = next((item for item in self.portfolio_manager.list_paper_trades(limit=300) if item.get("id") == trade_id), None)
        if not existing:
            raise ValueError("Trade not found.")
        exit_price = float(closed_price or 0) or self._get_last_price(existing.get("ticker")) or float(existing.get("entry_price") or 0)
        if exit_price <= 0:
            raise ValueError("No valid close price available.")
        closed = self.portfolio_manager.close_paper_trade(trade_id, exit_price, notes, exit_reason, lessons_learned)
        if not closed:
            raise ValueError("Trade not found.")
        return self._enrich_trade(closed)

    def update_trade_journal(
        self,
        trade_id: str,
        notes: Optional[str] = None,
        exit_reason: Optional[str] = None,
        lessons_learned: Optional[str] = None,
    ) -> Dict[str, Any]:
        updated = self.portfolio_manager.update_paper_trade_journal(
            trade_id,
            notes=notes,
            exit_reason=exit_reason,
            lessons_learned=lessons_learned,
        )
        if not updated:
            raise ValueError("Trade not found.")
        return self._enrich_trade(updated)

    def _build_playbooks(self, scoreboard: Dict[str, Any], rules: Dict[str, Any]) -> List[Dict[str, Any]]:
        playbooks: List[Dict[str, Any]] = []

        for item in scoreboard.get("equities", [])[:4]:
            if not item.get("ticker"):
                continue
            direction = "long" if item.get("action") == "buy" else "short"
            score = float(item.get("total_score") or 0)
            playbooks.append(
                {
                    "id": f"equity-{item.get('ticker')}-{direction}",
                    "ticker": item.get("ticker"),
                    "asset_class": "equity",
                    "direction": direction,
                    "setup_type": "insider_follow",
                    "title": "Insider follow-through",
                    "headline": item.get("headline"),
                    "score": score,
                    "risk_buffer_pct": 3.5 if direction == "long" else 4.0,
                    "reward_buffer_pct": 7.5,
                    "thesis": (
                        f"{item.get('source_label')} with strong {direction} bias. "
                        f"Use only if price holds after filing delay of {item.get('delay_days') or 'n/a'} days."
                    ),
                    "tags": ["long" if direction == "long" else "short", "official filing", "equity"],
                    "reference_price": self._get_last_price(item.get("ticker")),
                }
            )

        for item in scoreboard.get("politics", [])[:3]:
            if not item.get("ticker"):
                continue
            direction = "long" if item.get("action") == "buy" else "short"
            playbooks.append(
                {
                    "id": f"politics-{item.get('ticker') or item.get('label')}-{direction}",
                    "ticker": item.get("ticker"),
                    "asset_class": "equity",
                    "direction": direction,
                    "setup_type": "political_copy_delay",
                    "title": "Political delay setup",
                    "headline": item.get("headline"),
                    "score": item.get("total_score"),
                    "risk_buffer_pct": 4.5,
                    "reward_buffer_pct": 8.5,
                    "thesis": (
                        f"Official PTR disclosure with {item.get('detail')}. "
                        "Only valid when the tape confirms after the delayed filing."
                    ),
                    "tags": ["delayed signal", "politics", direction],
                    "reference_price": self._get_last_price(item.get("ticker")),
                }
            )

        for item in scoreboard.get("etfs", [])[:2]:
            if not item.get("ticker"):
                continue
            playbooks.append(
                {
                    "id": f"etf-{item.get('ticker')}-long",
                    "ticker": item.get("ticker"),
                    "asset_class": "etf",
                    "direction": "long",
                    "setup_type": "etf_momentum",
                    "title": "ETF momentum continuation",
                    "headline": item.get("headline"),
                    "score": item.get("total_score"),
                    "risk_buffer_pct": 2.8,
                    "reward_buffer_pct": 6.0,
                    "thesis": "Liquid ETF with decent quality and momentum profile. Favor clean continuation over narrative chasing.",
                    "tags": ["etf", "momentum", "long"],
                    "reference_price": self._get_last_price(item.get("ticker")),
                }
            )

        for item in scoreboard.get("crypto", [])[:2]:
            if not item.get("ticker"):
                continue
            playbooks.append(
                {
                    "id": f"crypto-{item.get('ticker')}-long",
                    "ticker": item.get("ticker"),
                    "asset_class": "crypto",
                    "direction": "long",
                    "setup_type": "crypto_flow",
                    "title": "Crypto flow momentum",
                    "headline": item.get("headline"),
                    "score": item.get("total_score"),
                    "risk_buffer_pct": 5.5,
                    "reward_buffer_pct": 11.0,
                    "thesis": "Flow-driven crypto setup. Keep leverage conservative and size by volatility, not conviction alone.",
                    "tags": ["crypto", "momentum", "long"],
                    "reference_price": self._get_last_price(item.get("ticker")),
                }
            )

        for item in playbooks:
            rule_state = self._get_do_not_trade_state(item, rules)
            item["do_not_trade_reasons"] = rule_state["blocked"]
            item["leverage_warnings"] = rule_state["leverage"]
            item["tradeable"] = len(rule_state["blocked"]) == 0

        return sorted(playbooks, key=lambda item: float(item.get("score") or 0), reverse=True)[:10]

    def _build_stats(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        closed = [trade for trade in trades if trade.get("status") == "closed" and trade.get("realized_pnl_pct") is not None]
        open_trades = [trade for trade in trades if trade.get("status") == "open"]
        winners = [trade for trade in closed if float(trade.get("realized_pnl_pct") or 0) > 0]
        losers = [trade for trade in closed if float(trade.get("realized_pnl_pct") or 0) <= 0]
        total_realized = round(sum(float(trade.get("realized_pnl_pct") or 0) for trade in closed), 2)
        avg_open = round(
            sum(float(trade.get("unrealized_pnl_pct") or 0) for trade in open_trades) / len(open_trades),
            2,
        ) if open_trades else 0
        return {
            "total_trades": len(trades),
            "open_trades": len(open_trades),
            "closed_trades": len(closed),
            "win_rate": round((len(winners) / len(closed)) * 100, 1) if closed else 0,
            "avg_open_pnl_pct": avg_open,
            "realized_pnl_pct": total_realized,
            "best_trade_pct": round(max((float(trade.get("realized_pnl_pct") or 0) for trade in closed), default=0), 2),
            "worst_trade_pct": round(min((float(trade.get("realized_pnl_pct") or 0) for trade in closed), default=0), 2),
            "long_short_split": {
                "long": sum(1 for trade in trades if trade.get("direction") == "long"),
                "short": sum(1 for trade in trades if trade.get("direction") == "short"),
            },
            "loss_count": len(losers),
        }

    def _build_setup_performance(self, closed_trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        buckets: Dict[str, Dict[str, Any]] = {}
        for trade in closed_trades:
            setup_type = trade.get("setup_type") or "other"
            bucket = buckets.setdefault(
                setup_type,
                {
                    "setup_type": setup_type,
                    "trades": 0,
                    "wins": 0,
                    "avg_pnl_pct": 0.0,
                    "best_pnl_pct": None,
                    "worst_pnl_pct": None,
                },
            )
            pnl = float(trade.get("realized_pnl_pct") or 0)
            bucket["trades"] += 1
            bucket["wins"] += 1 if pnl > 0 else 0
            bucket["avg_pnl_pct"] += pnl
            bucket["best_pnl_pct"] = pnl if bucket["best_pnl_pct"] is None else max(bucket["best_pnl_pct"], pnl)
            bucket["worst_pnl_pct"] = pnl if bucket["worst_pnl_pct"] is None else min(bucket["worst_pnl_pct"], pnl)

        rows = []
        for bucket in buckets.values():
            trades = max(1, int(bucket["trades"]))
            rows.append(
                {
                    **bucket,
                    "avg_pnl_pct": round(float(bucket["avg_pnl_pct"]) / trades, 2),
                    "win_rate": round((int(bucket["wins"]) / trades) * 100, 1),
                }
            )
        rows.sort(key=lambda item: (item.get("win_rate", 0), item.get("avg_pnl_pct", 0)), reverse=True)
        return rows

    def _build_journal(self, trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows = []
        for trade in trades[:20]:
            pnl_pct = trade.get("realized_pnl_pct")
            if pnl_pct is None:
                pnl_pct = trade.get("unrealized_pnl_pct")
            rows.append(
                {
                    "id": trade.get("id"),
                    "ticker": trade.get("ticker"),
                    "direction": trade.get("direction"),
                    "setup_type": trade.get("setup_type"),
                    "status": trade.get("status"),
                    "opened_at": trade.get("opened_at"),
                    "closed_at": trade.get("closed_at"),
                    "thesis": trade.get("thesis"),
                    "notes": trade.get("notes"),
                    "exit_reason": trade.get("exit_reason"),
                    "lessons_learned": trade.get("lessons_learned"),
                    "pnl_pct": pnl_pct,
                    "risk_reward": trade.get("risk_reward"),
                    "confidence_score": trade.get("confidence_score"),
                }
            )
        return rows

    def _enrich_trades(self, trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        enriched = [self._enrich_trade(trade) for trade in trades]
        enriched.sort(
            key=lambda trade: (
                0 if trade.get("status") == "open" else 1,
                trade.get("closed_at") or trade.get("opened_at") or "",
            ),
            reverse=True,
        )
        return enriched

    def _enrich_trade(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        row = dict(trade)
        entry = float(row.get("entry_price") or 0)
        quantity = float(row.get("quantity") or 0)
        leverage = float(row.get("leverage") or 1)
        current_price = self._get_last_price(row.get("ticker"))
        row["current_price"] = current_price
        direction_multiplier = 1 if row.get("direction") == "long" else -1

        if row.get("status") == "closed":
            exit_price = float(row.get("closed_price") or 0)
            pnl_pct = self._calc_return_pct(entry, exit_price, direction_multiplier, leverage)
            row["realized_pnl_pct"] = pnl_pct
            row["realized_pnl_value"] = round(((exit_price - entry) * quantity * direction_multiplier * leverage), 2)
            row["unrealized_pnl_pct"] = None
            row["unrealized_pnl_value"] = None
        else:
            pnl_pct = self._calc_return_pct(entry, current_price, direction_multiplier, leverage) if current_price else None
            row["unrealized_pnl_pct"] = pnl_pct
            row["unrealized_pnl_value"] = (
                round(((current_price - entry) * quantity * direction_multiplier * leverage), 2)
                if current_price is not None
                else None
            )
            row["realized_pnl_pct"] = None
            row["realized_pnl_value"] = None

        row["risk_reward"] = self._calc_risk_reward(
            entry,
            row.get("stop_price"),
            row.get("target_price"),
            row.get("direction"),
        )
        return row

    def _get_do_not_trade_state(self, playbook: Dict[str, Any], rules: Dict[str, Any]) -> Dict[str, List[str]]:
        blocked: List[str] = []
        leverage_rules: List[str] = []
        score = float(playbook.get("score") or 0)
        min_trade_score = float(rules.get("min_score_for_new_trade") or 78)
        min_leverage_score = float(rules.get("min_score_for_leverage") or 88)
        if score < min_trade_score:
            blocked.append(f"Score below minimum trade score {min_trade_score:.0f}.")
        if playbook.get("setup_type") == "political_copy_delay":
            if score < min_trade_score + 2:
                blocked.append(f"Political delay setup needs stronger confirmation above {min_trade_score + 2:.0f}.")
        if playbook.get("asset_class") == "crypto" and playbook.get("direction") == "short":
            blocked.append("Crypto short playbooks are disabled in the current model.")
        if playbook.get("asset_class") == "crypto" and bool(rules.get("block_crypto_leverage", True)):
            leverage_rules.append("Crypto leverage is blocked in the current rule set.")
        if score < min_leverage_score:
            leverage_rules.append(f"No leverage allowed below score {min_leverage_score:.0f}.")
        return {"blocked": blocked, "leverage": leverage_rules}

    def _calc_return_pct(self, entry_price: float, other_price: Optional[float], direction_multiplier: int, leverage: float) -> Optional[float]:
        if not entry_price or other_price in (None, 0):
            return None
        return round((((float(other_price) - entry_price) / entry_price) * 100) * direction_multiplier * leverage, 2)

    def _calc_risk_reward(
        self,
        entry_price: float,
        stop_price: Optional[float],
        target_price: Optional[float],
        direction: Optional[str],
    ) -> Optional[str]:
        if not entry_price or stop_price in (None, 0) or target_price in (None, 0):
            return None
        if direction == "short":
            risk = float(stop_price) - entry_price
            reward = entry_price - float(target_price)
        else:
            risk = entry_price - float(stop_price)
            reward = float(target_price) - entry_price
        if risk <= 0 or reward <= 0:
            return None
        return f"1:{round(reward / risk, 2)}"

    def _get_last_price(self, ticker: Optional[str]) -> Optional[float]:
        if not ticker:
            return None
        try:
            hist = yf.Ticker(ticker).history(period="5d", interval="1d")
            if hist.empty:
                return None
            return round(float(hist["Close"].dropna().iloc[-1]), 2)
        except Exception:
            return None
