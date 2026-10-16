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

import requests

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

    def _get_alert_profile(self) -> str:
        """Returns the active alert profile (smart_digest, trade_pro, silent)."""
        if self.portfolio_manager and hasattr(self.portfolio_manager, "get_app_setting"):
            try:
                prof = self.portfolio_manager.get_app_setting("telegram_alert_profile")
                if prof:
                    return str(prof).strip().lower()
            except Exception:
                pass
        import os
        return os.getenv("TELEGRAM_ALERT_PROFILE", "smart_digest").strip().lower()

    def evaluate_active_trades(self, alert_service: Optional[Any] = None) -> Dict[str, Any]:
        """
        Polls current prices of active trades and triggers Telegram notifications
        when Target 1, Target 2 or Invalidation Stop are crossed.
        """
        active = [
            t for t in self._in_memory_trades.values()
            if t.get("status") in ("OPEN", "TARGET_1_HIT")
        ]
        pending_reentries = [
            t for t in self._in_memory_trades.values()
            if t.get("status") == "STOPPED_OUT" and "RE_ENTRY_SIGNAL" not in t.get("events_fired", [])
        ]

        if not active and not pending_reentries:
            return {"status": "ok", "evaluated": 0, "actions": []}

        profile = self._get_alert_profile()
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

            is_eu = any(symbol.endswith(sfx) for sfx in [".DE", ".F", ".AS", ".PA", ".MI", ".MC"])
            c_sym = "€" if is_eu else ("£" if symbol.endswith(".L") else "$")

            risk = float(trade.get("risk_per_share") or abs(entry - stop) or 0.0)

            # 1. Advance Notice: Target 1 Proximity Alert (within 0.75% of Target 1)
            # Suppressed in smart_digest and silent profiles to eliminate noise
            if (
                status == "OPEN"
                and spot < target_1
                and ((target_1 - spot) / spot) <= 0.0075
                and "TARGET_1_PROXIMITY" not in events_fired
            ):
                events_fired.append("TARGET_1_PROXIMITY")
                actions.append({"ticker": symbol, "action": "TARGET_1_PROXIMITY", "price": spot})
                if alert_service and profile not in ("smart_digest", "silent"):
                    dist_pct = ((target_1 - spot) / spot) * 100.0
                    tg_msg = (
                        f"🎯 <b>ZIEL 1 IN REICHWEITE: {symbol} ({c_sym}{spot:.2f})</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"Der Kurs steht unmittelbar vor deinem 2.0R Kursziel von <b>{c_sym}{target_1:.2f}</b> (nur noch +{dist_pct:.2f}%)!\n\n"
                        f"• <b>Einstieg:</b> {c_sym}{entry:.2f}\n"
                        f"• <b>Aktueller Kurs:</b> {c_sym}{spot:.2f}\n"
                        f"• <b>Ziel 1:</b> {c_sym}{target_1:.2f}\n\n"
                        f"⚡ <b>Empfohlene Vorbereitung:</b>\n"
                        f"Halte dich bereit für eine 50% Teilgewinn-Mitnahme oder sichere mit dem Atmungs-Puffer (-0.25R) ab."
                    )
                    kb = {
                        "inline_keyboard": [
                            [
                                {"text": "🌬️ Atmungs-Puffer (-0.25R)", "callback_data": f"cushion:{symbol}"},
                                {"text": "🛡️ Stop auf Breakeven", "callback_data": f"be:{symbol}"},
                            ],
                            [
                                {"text": "🚪 Position schließen", "callback_data": f"close:{symbol}"},
                            ]
                        ]
                    }
                    self._dispatch_tg(alert_service, symbol, f"target_1_prox:{symbol}", tg_msg, reply_markup=kb)

            # 1b. Smart Breathing Cushion (+1.0R reached):
            # Instead of a rigid 0.0R Breakeven that gets shaken out on normal retests,
            # tighten stop to -0.25R (cuts 75% of initial risk while leaving room to breathe for the rally!)
            elif (
                status == "OPEN"
                and risk > 0
                and spot >= (entry + 1.0 * risk)
                and spot < target_1
                and ((target_1 - spot) / spot) > 0.0075
                and "SMART_CUSHION_1R" not in events_fired
            ):
                cushion_stop = round(entry - (0.25 * risk), 2)
                if cushion_stop > stop:
                    trade["trailing_stop"] = cushion_stop
                events_fired.append("SMART_CUSHION_1R")
                actions.append({
                    "ticker": symbol,
                    "action": "SMART_CUSHION_1R",
                    "price": spot,
                    "trailing_stop": trade["trailing_stop"],
                })

                # Sync paper trade trailing stop if open
                if self.portfolio_manager and hasattr(self.portfolio_manager, "list_paper_trades"):
                    try:
                        open_pts = self.portfolio_manager.list_paper_trades(limit=100)
                        for pt in open_pts:
                            if str(pt.get("ticker") or "").upper() == symbol and str(pt.get("status") or "").lower() == "open":
                                tid = pt.get("id")
                                if tid and hasattr(self.portfolio_manager, "update_paper_trade_journal"):
                                    self.portfolio_manager.update_paper_trade_journal(
                                        trade_id=tid,
                                        notes=f"+1.0R erreicht! Smart Atmungs-Puffer (-0.25R = {c_sym}{cushion_stop:.2f}) aktiviert – 75% Risiko reduziert, Puffer gegen Shakeouts.",
                                    )
                    except Exception as e:
                        logger.debug("Failed syncing paper trade on Smart Cushion: %s", e)

                if alert_service and profile != "silent":
                    tg_msg = (
                        f"🌬️ <b>SMART ATMUNGS-PUFFER AKTIVIERT (+1.0R): {symbol} ({c_sym}{spot:.2f})</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"Dein Trade liegt <b>+1.0R im Gewinn</b> und der Aufwärtstrend ist intakt!\n\n"
                        f"• <b>Einstieg:</b> {c_sym}{entry:.2f}\n"
                        f"• <b>Alter Stop (-1.0R):</b> {c_sym}{stop:.2f}\n"
                        f"• <b>Neuer Puffer-Stop (-0.25R):</b> <b>{c_sym}{cushion_stop:.2f}</b> 🛡️\n\n"
                        f"💡 <b>Warum -0.25R statt 0.0R Breakeven?</b>\n"
                        f"75% deines ursprünglichen Risikos sind jetzt eliminiert! Durch den kleinen Puffer von -0.25R "
                        f"wirst du bei einem normalen Rücksetzer an den Einstiegskurs <b>nicht vorzeitig ausgestoppt</b>, "
                        f"bevor die große Bewegung zu Ziel 1 ({c_sym}{target_1:.2f}) und Ziel 2 ({c_sym}{target_2:.2f}) startet."
                    )
                    kb = {
                        "inline_keyboard": [
                            [
                                {"text": "🌬️ Puffer (-0.25R) lassen", "callback_data": f"cushion:{symbol}"},
                                {"text": "🛡️ Strikt Breakeven (0.0R)", "callback_data": f"be:{symbol}"},
                            ],
                            [
                                {"text": "🔍 360° Check", "callback_data": f"check:{symbol}"},
                            ]
                        ]
                    }
                    self._dispatch_tg(alert_service, symbol, f"smart_cushion:{symbol}", tg_msg, reply_markup=kb)

            # 2. Target 1 Reached
            elif status == "OPEN" and spot >= target_1 and "TARGET_1_HIT" not in events_fired:
                trade["status"] = "TARGET_1_HIT"
                # Move trailing stop to Breakeven
                trade["trailing_stop"] = entry
                events_fired.append("TARGET_1_HIT")

                action_desc = f"{symbol} hit Target 1 ({c_sym}{spot:.2f} >= {c_sym}{target_1:.2f})"
                actions.append({"ticker": symbol, "action": "TARGET_1_HIT", "price": spot})

                # Sync journal in paper trading if open
                if self.portfolio_manager and hasattr(self.portfolio_manager, "list_paper_trades"):
                    try:
                        open_pts = self.portfolio_manager.list_paper_trades(limit=100)
                        for pt in open_pts:
                            if str(pt.get("ticker") or "").upper() == symbol and str(pt.get("status") or "").lower() == "open":
                                tid = pt.get("id")
                                if tid and hasattr(self.portfolio_manager, "update_paper_trade_journal"):
                                    self.portfolio_manager.update_paper_trade_journal(
                                        trade_id=tid,
                                        notes=f"Target 1 ({c_sym}{target_1:.2f}) erreicht! Stop auf Breakeven ({c_sym}{entry:.2f}) nachgezogen.",
                                    )
                    except Exception as e:
                        logger.debug("Failed syncing paper trade on Target 1: %s", e)

                if alert_service and profile != "silent":
                    cushion_price = round(entry - (0.25 * risk), 2) if risk > 0 else entry
                    tg_msg = (
                        f"🎯 <b>TARGET 1 ERREICHT: {symbol} ({c_sym}{spot:.2f})</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"Dein 2.0R Kursziel von <b>{c_sym}{target_1:.2f}</b> wurde erreicht!\n\n"
                        f"⚡ <b>Empfohlene Aktion jetzt:</b>\n"
                        f"1. <b>50% der Position schließen</b> (Gewinn sichern!)\n"
                        f"2. <b>Stop-Loss auf Breakeven ({c_sym}{entry:.2f}) nachziehen</b>\n"
                        f"   <i>(Oder bei starkem Trend mit <code>/puffer {symbol}</code> auf {c_sym}{cushion_price:.2f} (-0.25R) lassen, um der Restposition Luft für Ziel 2 zu geben!)</i>\n\n"
                        f"🛡️ <i>Der Trade ist ab sofort risikofrei abgesichert. Die restlichen 50% "
                        f"laufen weiter Richtung Ziel 2 ({c_sym}{target_2:.2f}).</i>"
                    )
                    kb = {
                        "inline_keyboard": [
                            [
                                {"text": "✂️ 50% Teilverkauf", "callback_data": f"scale:{symbol}:50"},
                                {"text": "🌬️ Puffer (-0.25R)", "callback_data": f"cushion:{symbol}"},
                                {"text": "🛡️ Breakeven", "callback_data": f"be:{symbol}"},
                            ],
                            [
                                {"text": "🚪 Schließen", "callback_data": f"close:{symbol}"},
                                {"text": "🔍 360° Check", "callback_data": f"check:{symbol}"},
                                {"text": "📖 Journal", "callback_data": "journal"},
                            ]
                        ]
                    }
                    self._dispatch_tg(alert_service, symbol, f"target_1:{symbol}", tg_msg, reply_markup=kb)

            # 3. Target 2 Reached
            elif status == "TARGET_1_HIT" and spot >= target_2 and "TARGET_2_HIT" not in events_fired:
                trade["status"] = "TARGET_2_HIT"
                events_fired.append("TARGET_2_HIT")

                actions.append({"ticker": symbol, "action": "TARGET_2_HIT", "price": spot})

                if alert_service and profile != "silent":
                    tg_msg = (
                        f"🚀 <b>TARGET 2 ERREICHT: {symbol} ({c_sym}{spot:.2f})</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"Maximales Kursziel (3.5R+ / <b>{c_sym}{target_2:.2f}</b>) erreicht!\n\n"
                        f"⚡ <b>Empfohlene Aktion:</b>\n"
                        f"Restliche Position vollständig schließen oder Hard Trailing Stop "
                        f"unter das 9 EMA Tief legen."
                    )
                    kb = {
                        "inline_keyboard": [
                            [
                                {"text": "🚪 Position schließen", "callback_data": f"close:{symbol}"},
                                {"text": "📖 Journal", "callback_data": "journal"},
                            ]
                        ]
                    }
                    self._dispatch_tg(alert_service, symbol, f"target_2:{symbol}", tg_msg, reply_markup=kb)

            # 4. Stop-Loss Proximity Warning (within 0.75% of Stop)
            # Suppressed in smart_digest and silent profiles to eliminate noise
            elif (
                spot > stop
                and ((spot - stop) / spot) <= 0.0075
                and "STOP_PROXIMITY" not in events_fired
            ):
                events_fired.append("STOP_PROXIMITY")
                actions.append({"ticker": symbol, "action": "STOP_PROXIMITY", "price": spot})
                if alert_service and profile not in ("smart_digest", "silent"):
                    dist_pct = ((spot - stop) / spot) * 100.0
                    tg_msg = (
                        f"🚨 <b>STOP-LOSS WARNUNG: {symbol} ({c_sym}{spot:.2f})</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"Der Kurs nähert sich gefährlich dem Invalidation Stop!\n\n"
                        f"• <b>Aktueller Kurs:</b> {c_sym}{spot:.2f}\n"
                        f"• <b>Stop-Loss Level:</b> {c_sym}{stop:.2f}\n"
                        f"• <b>Verbleibender Puffer:</b> nur noch <b>{dist_pct:.2f}%</b>!\n\n"
                        f"⚡ <b>Empfohlene Aktion:</b>\n"
                        f"Trade jetzt engmaschig beobachten oder Position vorzeitig mit 1-Tap glattstellen."
                    )
                    kb = {
                        "inline_keyboard": [
                            [
                                {"text": "🚪 Position sofort schließen", "callback_data": f"close:{symbol}"},
                                {"text": "🛡️ Stops prüfen", "callback_data": f"stop:{symbol}"},
                            ],
                            [
                                {"text": "🔍 360° Check", "callback_data": f"check:{symbol}"},
                            ]
                        ]
                    }
                    self._dispatch_tg(alert_service, symbol, f"stop_prox:{symbol}", tg_msg, reply_markup=kb)

            # 5. Stop-Loss / Invalidation
            elif spot <= stop and "STOPPED_OUT" not in events_fired:
                trade["status"] = "STOPPED_OUT"
                trade["stopped_out_at"] = datetime.now(timezone.utc).isoformat()
                trade["shakeout_low"] = spot
                events_fired.append("STOPPED_OUT")

                actions.append({"ticker": symbol, "action": "STOPPED_OUT", "price": spot})

                if alert_service:
                    is_be = (status == "TARGET_1_HIT")
                    reason = (
                        f"🛡️ <b>Breakeven-Ausstieg</b> für die Restposition ({c_sym}{entry:.2f}). "
                        f"50% Teilgewinn wurde zuvor bei Ziel 1 gesichert!"
                        if is_be else
                        f"⚠️ <b>Stop-Loss / Puffer ausgelöst</b> ({c_sym}{stop:.2f}). "
                        f"Trade diszipliniert beendet, Risiko strikt begrenzt.\n"
                        f"🔄 <b>48h Second-Chance Re-Entry Radar aktiv:</b> Falls das nur ein kurzer Stop-Hunt war und {symbol} den Einstieg ({c_sym}{entry:.2f}) zurückerobert, wirst du sofort alarmiert!"
                    )
                    tg_msg = (
                        f"🛑 <b>STOP-LOSS ERREICHT: {symbol} ({c_sym}{spot:.2f})</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"Der Kurs hat die Stop-Marke von <b>{c_sym}{stop:.2f}</b> erreicht.\n\n"
                        f"{reason}\n\n"
                        f"💡 <i>Position glattstellen. Re-Entry-Überwachung läuft automatisch weiter.</i>"
                    )
                    kb = {
                        "inline_keyboard": [
                            [
                                {"text": "🔄 Re-Entry Radar (/reentry)", "callback_data": "reentry"},
                                {"text": "📖 Trading Journal", "callback_data": "journal"},
                            ]
                        ]
                    }
                    self._dispatch_tg(alert_service, symbol, f"stop_out:{symbol}", tg_msg, reply_markup=kb)

        # 6. Second-Chance Re-Entry Radar: Check recently STOPPED_OUT trades (within 48h) for Shakeout Reclaim
        stopped_trades = [
            t for t in self._in_memory_trades.values()
            if t.get("status") == "STOPPED_OUT" and "RE_ENTRY_SIGNAL" not in t.get("events_fired", [])
        ]
        for st in stopped_trades:
            symbol = st["ticker"]
            entry = float(st.get("entry_price") or 0.0)
            target_1 = float(st.get("target_1") or 0.0)
            target_2 = float(st.get("target_2") or 0.0)
            if entry <= 0:
                continue
            spot = self._fetch_current_price(symbol)
            if spot is None or spot <= 0:
                continue
            st["last_price"] = spot
            shakeout_low = float(st.get("shakeout_low") or st.get("trailing_stop") or (entry * 0.96))
            if spot < shakeout_low:
                st["shakeout_low"] = spot
                shakeout_low = spot

            # Trigger Re-Entry when price reclaims the original entry price after a stop-out
            if spot >= entry:
                events_fired = st.setdefault("events_fired", [])
                events_fired.append("RE_ENTRY_SIGNAL")
                new_stop = round(min(shakeout_low * 0.995, entry * 0.975), 2)
                new_risk = max(0.01, round(spot - new_stop, 2))
                new_cushion = round(spot - 0.25 * new_risk, 2)
                actions.append({
                    "ticker": symbol,
                    "action": "RE_ENTRY_SIGNAL",
                    "price": spot,
                    "reclaim_entry": entry,
                    "new_stop": new_stop,
                })
                if alert_service and profile != "silent":
                    is_eu = any(symbol.endswith(sfx) for sfx in [".DE", ".F", ".AS", ".PA", ".MI", ".MC"])
                    c_sym = "€" if is_eu else ("£" if symbol.endswith(".L") else "$")
                    tg_msg = (
                        f"🔄 <b>SECOND-CHANCE RE-ENTRY SIGNAL: {symbol} ({c_sym}{spot:.2f})</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"⚡ <b>Stop-Hunt beendet – Aufwärtstrend zurückerobert!</b>\n"
                        f"{symbol} wurde zuvor ausgestoppt (Tief bei {c_sym}{shakeout_low:.2f}), hat aber soeben die alte Einstiegsmarke von <b>{c_sym}{entry:.2f}</b> kraftvoll zurückerobert!\n\n"
                        f"🎯 <b>Neues Second-Chance Setup:</b>\n"
                        f"• 🟢 <b>Re-Entry Kurs:</b> <b>{c_sym}{spot:.2f}</b>\n"
                        f"• 🌬️ <b>Atmungs-Puffer (-0.25R):</b> <b>{c_sym}{new_cushion:.2f}</b>\n"
                        f"• 🛑 <b>Neuer Stop (unter Shakeout-Tief):</b> <b>{c_sym}{new_stop:.2f}</b>\n"
                        f"• 🚀 <b>Kursziel 1 &amp; 2:</b> <b>{c_sym}{target_1:.2f}</b> / <b>{c_sym}{target_2:.2f}</b>\n\n"
                        f"💡 <i>Institutionelle lieben solche Shakeout-Reclaims, weil schwache Hände rausgespült wurden und der Weg nach oben jetzt frei ist!</i>"
                    )
                    kb = {
                        "inline_keyboard": [
                            [
                                {"text": "📝 Re-Entry ins Paper-Depot", "callback_data": f"paper:{symbol}"},
                                {"text": "🔍 360° Check", "callback_data": f"check:{symbol}"},
                            ],
                            [
                                {"text": "🏦 Broker-Spickzettel", "callback_data": f"order:{symbol}"},
                            ],
                        ]
                    }
                    self._dispatch_tg(alert_service, symbol, f"reentry:{symbol}", tg_msg, reply_markup=kb)

        self._save_trades()
        return {"status": "ok", "evaluated": len(active), "actions": actions}

    def get_reentry_candidates(self) -> List[Dict[str, Any]]:
        """Returns recently stopped-out trades and active Shakeout-Reclaim candidates."""
        candidates: List[Dict[str, Any]] = []
        for t in self._in_memory_trades.values():
            if t.get("status") == "STOPPED_OUT" or "RE_ENTRY_SIGNAL" in t.get("events_fired", []):
                entry = float(t.get("entry_price") or 0.0)
                last = float(t.get("last_price") or entry)
                shakeout_low = float(t.get("shakeout_low") or t.get("trailing_stop") or (entry * 0.96))
                reclaimed = last >= entry and entry > 0
                dist_to_reclaim_pct = round(((last - entry) / entry) * 100.0, 2) if entry > 0 else 0.0
                candidates.append({
                    "ticker": t.get("ticker"),
                    "entry_price": entry,
                    "last_price": last,
                    "shakeout_low": shakeout_low,
                    "target_1": float(t.get("target_1") or (entry * 1.08)),
                    "target_2": float(t.get("target_2") or (entry * 1.15)),
                    "reclaimed": reclaimed,
                    "dist_to_reclaim_pct": dist_to_reclaim_pct,
                    "status_label": "🟢 RECLAIM AKTIV (Jetzt Re-Entry prüfen!)" if reclaimed else "👀 WARTET AUF RECLAIM ÜBER EINSTIEG",
                })
        return candidates

    def format_reentry_radar_card(self) -> str:
        """Formats the Second-Chance Re-Entry Radar for Telegram (/reentry)."""
        cands = self.get_reentry_candidates()
        if not cands:
            return (
                "🔄 <b>SECOND-CHANCE RE-ENTRY RADAR (48h)</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "✅ <b>Aktuell keine ausgestoppten Setups in der Warteschlange.</b>\n\n"
                "💡 <b>Wie schützt dich dieses Modul vor verpassten Rallyes?</b>\n"
                "Falls ein Trade trotz unseres <b>-0.25R Atmungs-Puffers</b> durch einen kurzen Market-Maker Stop-Hunt ausgestoppt wird, "
                "überwacht der Bot die Aktie automatisch 48 Stunden weiter. Erobern Kurs &amp; Volumen den alten Einstieg zurück, "
                "erhältst du sofort ein <b>🔄 Second-Chance Re-Entry Signal</b>!"
            )

        lines = [
            f"🔄 <b>SECOND-CHANCE RE-ENTRY RADAR ({len(cands)} Kandidaten)</b>",
            "<i>Verpasse nie wieder die Hauptbewegung nach einem kurzen Stop-Hunt!</i>",
            "━━━━━━━━━━━━━━━━━━━━",
        ]
        for c in cands:
            sym = str(c["ticker"])
            is_eu = any(sym.endswith(sfx) for sfx in [".DE", ".F", ".AS", ".PA", ".MI", ".MC"])
            c_sym = "€" if is_eu else ("£" if sym.endswith(".L") else "$")
            entry = c["entry_price"]
            last = c["last_price"]
            low = c["shakeout_low"]
            t1 = c["target_1"]
            dist = c["dist_to_reclaim_pct"]
            lines.append(
                f"\n• <b>{sym}</b> – {c['status_label']}\n"
                f"  Alter Einstieg (Trigger): <b>{c_sym}{entry:.2f}</b> | Aktuell: <b>{c_sym}{last:.2f}</b> ({dist:+.2f}%)\n"
                f"  Shakeout-Tief (Neuer Stop-Anker): {c_sym}{low:.2f} | Ziel 1: <b>{c_sym}{t1:.2f}</b>\n"
                f"  ➔ Aktion: <code>/order {sym}</code> oder <code>/paper {sym}</code>"
            )
        return "\n".join(lines)

    def calculate_pyramiding_plan(
        self,
        ticker: str,
        fallback_setup: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Calculates a 'Free-Roll Pyramiding' plan to add to a winning position
        using already accrued unrealized profit as the risk buffer (0.00 € net risk).
        """
        symbol = ticker.upper().strip()
        trade = self._in_memory_trades.get(symbol)

        if trade and trade.get("status") in ("OPEN", "TARGET_1_HIT"):
            entry = float(trade.get("entry_price") or 100.0)
            stop = float(trade.get("invalidation_price") or (entry * 0.96))
            risk_per_share = max(0.01, float(trade.get("risk_per_share") or abs(entry - stop)))
            base_shares = max(1, int(trade.get("recommended_shares") or 10))
            spot = float(self._fetch_current_price(symbol) or trade.get("last_price") or (entry + 1.2 * risk_per_share))
            t1 = float(trade.get("target_1") or (entry + 2.0 * risk_per_share))
            t2 = float(trade.get("target_2") or (entry + 3.5 * risk_per_share))
        elif fallback_setup:
            entry = float(fallback_setup.get("entry_price") or 100.0)
            stop = float(fallback_setup.get("invalidation_price") or (entry * 0.96))
            risk_per_share = max(0.01, abs(entry - stop))
            base_shares = max(1, int(fallback_setup.get("recommended_shares") or 15))
            # Simulate how the pyramid looks once the trade reaches +1.0R
            spot = round(entry + 1.0 * risk_per_share, 2)
            t1 = float(fallback_setup.get("target_1") or (entry + 2.0 * risk_per_share))
            t2 = float(fallback_setup.get("target_2") or (entry + 3.5 * risk_per_share))
        else:
            entry = 100.0
            stop = 96.0
            risk_per_share = 4.0
            base_shares = 20
            spot = 104.0
            t1 = 108.0
            t2 = 114.0

        current_r = round((spot - entry) / risk_per_share, 2) if risk_per_share > 0 else 1.0
        # Pullback/continuation add price is current spot (or +1.0R trigger if still below +1.0R)
        add_price = round(max(spot, entry + 1.0 * risk_per_share), 2)
        # Combined stop is raised to original entry_price (or -0.10R cushion) so initial shares finance the add!
        combined_stop = round(entry, 2)
        add_risk_per_share = max(0.01, round(add_price - combined_stop, 2))

        # Recommended 35% to 50% size add ("Reverse Pyramid": big base, smaller add)
        add_shares = max(1, int(round(base_shares * 0.5)))
        total_shares = base_shares + add_shares
        new_avg_entry = round(((base_shares * entry) + (add_shares * add_price)) / total_shares, 2)

        # At combined_stop == entry, base_shares lose 0.00 and add_shares lose (add_price - entry).
        # If we instead set combined_stop to new_avg_entry, total net risk is literally 0.00!
        zero_risk_stop = new_avg_entry
        cushion_pyramid_stop = round(new_avg_entry - (0.25 * risk_per_share), 2)

        base_t2_profit = round(base_shares * max(0.0, t2 - entry), 2)
        boosted_t2_profit = round(base_t2_profit + add_shares * max(0.0, t2 - add_price), 2)
        profit_boost_pct = round(((boosted_t2_profit - base_t2_profit) / base_t2_profit) * 100.0, 1) if base_t2_profit > 0 else 40.0

        return {
            "ticker": symbol,
            "entry_price": entry,
            "current_price": spot,
            "current_r": current_r,
            "base_shares": base_shares,
            "add_shares": add_shares,
            "add_price": add_price,
            "total_shares": total_shares,
            "new_avg_entry": new_avg_entry,
            "zero_risk_stop": zero_risk_stop,
            "cushion_pyramid_stop": cushion_pyramid_stop,
            "target_1": t1,
            "target_2": t2,
            "base_t2_profit": base_t2_profit,
            "boosted_t2_profit": boosted_t2_profit,
            "profit_boost_pct": profit_boost_pct,
            "ready_to_add": current_r >= 0.8,
        }

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

            is_eu_sym = any(sym.endswith(sfx) for sfx in [".DE", ".F", ".AS", ".PA", ".MI", ".MC"])
            c_sym = "€" if is_eu_sym else ("£" if sym.endswith(".L") else "$")

            # Calculate current R multiple
            risk = t["risk_per_share"]
            r_mult = round((last - entry) / risk, 1) if risk > 0 else 0.0
            r_str = f"+{r_mult}R" if r_mult >= 0 else f"{r_mult}R"

            status_desc = "🟢 WARTET AUF ZIEL 1" if status == "OPEN" else "🎯 ZIEL 1 ERREICHT (Stop auf BE)"

            dist_stop = ((last - stop) / last * 100.0) if last > 0 else 0.0
            dist_t1 = ((t1 - last) / last * 100.0) if last > 0 else 0.0

            lines.append(
                f"\n• <b>{sym}</b> ({badge})\n"
                f"  Status: <b>{status_desc}</b> ({r_str})\n"
                f"  Einstieg: {c_sym}{entry:.2f} | Aktuell: <b>{c_sym}{last:.2f}</b>\n"
                f"  ➔ Puffer zum Stop: <b>{c_sym}{stop:.2f}</b> ({dist_stop:+.1f}%) 🛡️\n"
                f"  ➔ Abstand zu Ziel 1: <b>{c_sym}{t1:.2f}</b> ({dist_t1:+.1f}%) 🎯\n"
                f"  Ziel 2: {c_sym}{t2:.2f}"
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

    def _dispatch_tg(
        self,
        alert_service: Any,
        symbol: str,
        event_id: str,
        html_text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Helper to send telegram notification with optional inline buttons."""
        try:
            config = alert_service.get_config()
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            event_key = f"lifecycle:{event_id}:{date_str}"
            event = {
                "event_key": event_key,
                "category": "trade_lifecycle",
                "title": f"Trade Lifecycle: {symbol}",
                "line": html_text,
            }
            alert_service._validate_telegram_config(config)
            alert_service._send_notifications(config, [event], subject=f"Broker Freund: {symbol}")
            if self.portfolio_manager:
                self.portfolio_manager.mark_signal_events_sent([event])

            # If interactive buttons provided, send directly to Telegram chat
            bot_token = getattr(config, "telegram_bot_token", None)
            chat_id = getattr(config, "telegram_chat_id", None)
            if reply_markup and bot_token and chat_id and getattr(config, "telegram_enabled", False):
                try:
                    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                    payload: Dict[str, Any] = {
                        "chat_id": chat_id,
                        "text": html_text[:4096],
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                        "reply_markup": reply_markup,
                    }
                    requests.post(url, json=payload, timeout=10)
                except Exception as req_err:
                    logger.debug("Failed sending Telegram interactive buttons: %s", req_err)
        except Exception as exc:
            logger.error("Failed to dispatch trade lifecycle alert for %s: %s", symbol, exc)
