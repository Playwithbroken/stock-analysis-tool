"""
Trade Lifecycle Service — Live Tracking & Trailing Stop Alert Manager

Monitors active asymmetric edge setups:
  1. Tracks Entry, Target 1 (2.0R), Target 2 (3.5R+), and Invalidation Stop.
  2. Automatically fires action alerts via Telegram when Target 1 is reached:
     "50% Gewinn mitnehmen & Stop auf Breakeven nachziehen!"
  3. Trailing Stop Management: Once Target 1 is hit, stop moves to Breakeven (+0.1R).
  4. Invalidation & Target 2 completion alerts.
  5. Persistent state stored across restarts.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore


class TradeLifecycleService:
    SETTING_KEY = "edge_trade_lifecycle_registry"

    def __init__(self, portfolio_manager: Optional[Any] = None) -> None:
        self.portfolio_manager = portfolio_manager
        self._in_memory_trades: Dict[str, Dict[str, Any]] = {}
        self._load_trades()

    def _load_trades(self) -> None:
        """Loads trades from persistent storage or initializes empty registry."""
        if not self.portfolio_manager:
            return
        try:
            raw = self.portfolio_manager.get_app_setting(self.SETTING_KEY)
            if raw:
                self._in_memory_trades = json.loads(str(raw))
        except Exception as exc:
            logger.debug("Failed to load trade lifecycle registry: %s", exc)
            self._in_memory_trades = {}

    def _save_trades(self) -> None:
        """Persists trade registry."""
        if not self.portfolio_manager:
            return
        try:
            self.portfolio_manager.set_app_setting(
                self.SETTING_KEY, json.dumps(self._in_memory_trades)
            )
        except Exception as exc:
            logger.debug("Failed to save trade lifecycle registry: %s", exc)

    def register_trade(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """
        Registers or updates an asymmetric trade ticket for live tracking.
        """
        symbol = str(ticket.get("ticker") or "").upper().strip()
        if not symbol:
            return {"status": "error", "message": "Missing ticker"}

        entry_price = float(ticket.get("entry_price") or 0.0)
        invalidation_price = float(ticket.get("invalidation_price") or 0.0)
        target_1 = float(ticket.get("target_1") or 0.0)
        target_2 = float(ticket.get("target_2") or 0.0)
        risk_per_share = float(ticket.get("risk_per_share") or (entry_price - invalidation_price))

        existing = self._in_memory_trades.get(symbol)
        now_str = datetime.now(timezone.utc).isoformat()

        # If already tracked and open, don't overwrite if recent
        if existing and existing.get("status") in ("OPEN", "TARGET_1_HIT"):
            return {"status": "already_tracking", "ticker": symbol, "trade": existing}

        trade_record = {
            "ticker": symbol,
            "setup_name": ticket.get("setup_name", "Asymmetric Edge Setup"),
            "grade": ticket.get("grade", "A"),
            "grade_badge": ticket.get("grade_badge", "⭐ Grade A"),
            "confluence_score": ticket.get("confluence_score", 70),
            "entry_price": entry_price,
            "invalidation_price": invalidation_price,
            "trailing_stop": invalidation_price,
            "target_1": target_1,
            "target_2": target_2,
            "risk_per_share": risk_per_share,
            "recommended_shares": ticket.get("recommended_shares", 1),
            "status": "OPEN",  # OPEN -> TARGET_1_HIT -> TARGET_2_HIT | STOPPED_OUT
            "last_price": entry_price,
            "created_at": now_str,
            "updated_at": now_str,
            "events_fired": [],
        }

        self._in_memory_trades[symbol] = trade_record
        self._save_trades()
        return {"status": "registered", "ticker": symbol, "trade": trade_record}

    def evaluate_active_trades(self, alert_service: Optional[Any] = None) -> Dict[str, Any]:
        """
        Polls current prices of active trades and triggers Telegram notifications
        when Target 1, Target 2 or Invalidation Stop are crossed.
        """
        active = [
            t for t in self._in_memory_trades.values()
            if t.get("status") in ("OPEN", "TARGET_1_HIT")
        ]

        if not active:
            return {"status": "ok", "evaluated": 0, "actions": []}

        actions: List[Dict[str, Any]] = []

        for trade in active:
            symbol = trade["ticker"]
            status = trade["status"]
            entry = float(trade["entry_price"])
            target_1 = float(trade["target_1"])
            target_2 = float(trade["target_2"])
            stop = float(trade["trailing_stop"])

            spot = self._fetch_current_price(symbol)
            if spot is None or spot <= 0:
                continue

            trade["last_price"] = spot
            trade["updated_at"] = datetime.now(timezone.utc).isoformat()
            events_fired = trade.setdefault("events_fired", [])

            # 1. Target 1 Reached
            if status == "OPEN" and spot >= target_1 and "TARGET_1_HIT" not in events_fired:
                trade["status"] = "TARGET_1_HIT"
                # Move trailing stop to Breakeven
                trade["trailing_stop"] = entry
                events_fired.append("TARGET_1_HIT")

                action_desc = f"{symbol} hit Target 1 (${spot:.2f} >= ${target_1:.2f})"
                actions.append({"ticker": symbol, "action": "TARGET_1_HIT", "price": spot})

                if alert_service:
                    tg_msg = (
                        f"🎯 <b>TARGET 1 ERREICHT: {symbol} (${spot:.2f})</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"Dein 2.0R Kursziel von <b>${target_1:.2f}</b> wurde erreicht!\n\n"
                        f"⚡ <b>Empfohlene Aktion jetzt:</b>\n"
                        f"1. <b>50% der Position schließen</b> (Gewinn sichern!)\n"
                        f"2. <b>Stop-Loss auf Breakeven (${entry:.2f}) nachziehen</b>\n\n"
                        f"🛡️ <i>Der Trade ist ab sofort risikofrei abgesichert. Die restlichen 50% "
                        f"laufen weiter Richtung Ziel 2 (${target_2:.2f}).</i>"
                    )
                    self._dispatch_tg(alert_service, symbol, f"target_1:{symbol}", tg_msg)

            # 2. Target 2 Reached
            elif status == "TARGET_1_HIT" and spot >= target_2 and "TARGET_2_HIT" not in events_fired:
                trade["status"] = "TARGET_2_HIT"
                events_fired.append("TARGET_2_HIT")

                actions.append({"ticker": symbol, "action": "TARGET_2_HIT", "price": spot})

                if alert_service:
                    tg_msg = (
                        f"🚀 <b>TARGET 2 ERREICHT: {symbol} (${spot:.2f})</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"Maximales Kursziel (3.5R+ / <b>${target_2:.2f}</b>) erreicht!\n\n"
                        f"⚡ <b>Empfohlene Aktion:</b>\n"
                        f"Restliche Position vollständig schließen oder Hard Trailing Stop "
                        f"unter das 9 EMA Tief legen."
                    )
                    self._dispatch_tg(alert_service, symbol, f"target_2:{symbol}", tg_msg)

            # 3. Stop-Loss / Invalidation
            elif spot <= stop and "STOPPED_OUT" not in events_fired:
                trade["status"] = "STOPPED_OUT"
                events_fired.append("STOPPED_OUT")

                actions.append({"ticker": symbol, "action": "STOPPED_OUT", "price": spot})

                if alert_service:
                    is_be = (status == "TARGET_1_HIT")
                    reason = (
                        f"🛡️ <b>Breakeven-Ausstieg</b> für die Restposition (${entry:.2f}). "
                        f"50% Teilgewinn wurde zuvor bei Ziel 1 gesichert!"
                        if is_be else
                        f"⚠️ <b>Invalidation Stop ausgelöst</b> (${stop:.2f}). "
                        f"Trade diszipliniert beendet, Risiko strikt begrenzt."
                    )
                    tg_msg = (
                        f"🛑 <b>STOP-LOSS ERREICHT: {symbol} (${spot:.2f})</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"Der Kurs hat die Stop-Marke von <b>${stop:.2f}</b> erreicht.\n\n"
                        f"{reason}\n\n"
                        f"💡 <i>Position glattstellen. Kapital für das nächste Setup freigeben.</i>"
                    )
                    self._dispatch_tg(alert_service, symbol, f"stop_out:{symbol}", tg_msg)

        self._save_trades()
        return {"status": "ok", "evaluated": len(active), "actions": actions}

    def get_active_trades(self) -> List[Dict[str, Any]]:
        """Returns all trades currently tracked."""
        return list(self._in_memory_trades.values())

    def format_telegram_trades_list(self) -> str:
        """Formats an overview of all active trades for Telegram."""
        trades = [
            t for t in self._in_memory_trades.values()
            if t.get("status") in ("OPEN", "TARGET_1_HIT")
        ]
        if not trades:
            return (
                "ℹ️ <b>Keine aktiven Trades im Lifecycle-Monitor.</b>\n"
                "Nutze <code>/edge</code> oder warte auf den automatischen Watchlist-Scanner, "
                "um neue Grade A+/A Setups zu aktivieren."
            )

        lines = [
            f"📋 <b>AKTIV ÜBERWACHTE TRADES ({len(trades)})</b>",
            "━━━━━━━━━━━━━━━━━━━━",
        ]

        for t in trades:
            sym = t["ticker"]
            badge = t.get("grade_badge", "⭐ Grade A")
            entry = t["entry_price"]
            last = t.get("last_price", entry)
            t1 = t["target_1"]
            t2 = t["target_2"]
            stop = t["trailing_stop"]
            status = t["status"]

            # Calculate current R multiple
            risk = t["risk_per_share"]
            r_mult = round((last - entry) / risk, 1) if risk > 0 else 0.0
            r_str = f"+{r_mult}R" if r_mult >= 0 else f"{r_mult}R"

            status_desc = "🟢 WARTET AUF ZIEL 1" if status == "OPEN" else "🎯 ZIEL 1 ERREICHT (Stop auf BE)"

            lines.append(
                f"\n• <b>{sym}</b> ({badge})\n"
                f"  Status: <b>{status_desc}</b> ({r_str})\n"
                f"  Einstieg: ${entry:.2f} | Aktuell: <b>${last:.2f}</b>\n"
                f"  Ziel 1: ${t1:.2f} | Ziel 2: ${t2:.2f}\n"
                f"  Trailing Stop: <b>${stop:.2f}</b>"
            )

        return "\n".join(lines)

    def _fetch_current_price(self, symbol: str) -> Optional[float]:
        """Fetches latest spot price."""
        if not yf:
            return None
        try:
            t = yf.Ticker(symbol)
            fast = getattr(t, "fast_info", None)
            if fast:
                p = fast.get("lastPrice") or fast.get("regularMarketPreviousClose")
                if p and p > 0:
                    return round(float(p), 2)
            hist = t.history(period="1d")
            if not hist.empty:
                return round(float(hist["Close"].iloc[-1]), 2)
        except Exception:
            pass
        return None

    def _dispatch_tg(self, alert_service: Any, symbol: str, event_id: str, html_text: str) -> None:
        """Helper to send telegram notification through alert service."""
        try:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            event_key = f"lifecycle:{event_id}:{date_str}"
            event = {
                "event_key": event_key,
                "category": "trade_lifecycle",
                "title": f"Trade Lifecycle: {symbol}",
                "line": html_text,
            }
            config = alert_service.get_config()
            alert_service._validate_telegram_config(config)
            alert_service._send_notifications(config, [event], subject=f"Broker Freund: {symbol}")
            if self.portfolio_manager:
                self.portfolio_manager.mark_signal_events_sent([event])
        except Exception as exc:
            logger.error("Failed to dispatch trade lifecycle alert for %s: %s", symbol, exc)
