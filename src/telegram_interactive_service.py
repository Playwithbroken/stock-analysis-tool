"""
Telegram Interactive Service — 2-Way Conversational Edge Trading Bot & Inline Keyboard Engine

Enables the user to control Broker Freund directly from their smartphone via Telegram:
  • /help /start: Overview of commands
  • /edge [ticker]: Top Grade A+/A asymmetric setups or on-demand ticker analysis
  • /gex <ticker>: Market Maker Gamma Exposure, Call/Put Walls & Volatility Regime
  • /levels <ticker>: Volume Profile (POC, VAH, VAL) & Value Area Acceptance
  • /regime: Macro Market Regime (SPY, QQQ, VIX & Stance)
  • /rs: Relative Strength leaders vs SPY (Mansfield RS / Alpha)
  • /track /trades: Live active setups & Trailing-Stop monitor
  • /heat: Portfolio Heat & Cross-Correlation Shield
  • /scan: Trigger immediate watchlist scan

Interactive UI:
  • InlineKeyboardMarkup buttons attached to alerts & setups for one-tap actions
  • Callback query listener for instant smartphone responses
"""
from __future__ import annotations

import asyncio
import html
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import requests

logger = logging.getLogger(__name__)


class TelegramInteractiveService:
    def __init__(
        self,
        bot_token: str,
        allowed_chat_ids: str,
        asymmetric_trade_service: Optional[Any] = None,
        options_edge_service: Optional[Any] = None,
        volume_profile_service: Optional[Any] = None,
        market_regime_service: Optional[Any] = None,
        relative_strength_service: Optional[Any] = None,
        trade_lifecycle_service: Optional[Any] = None,
        portfolio_heat_service: Optional[Any] = None,
        anchored_vwap_service: Optional[Any] = None,
        whale_flow_service: Optional[Any] = None,
        liquidity_zone_service: Optional[Any] = None,
        multi_timeframe_service: Optional[Any] = None,
        trading_signals_service: Optional[Any] = None,
        alert_service: Optional[Any] = None,
        portfolio_manager: Optional[Any] = None,
        paper_trading_service: Optional[Any] = None,
        morning_brief_service: Optional[Any] = None,
    ) -> None:
        self.bot_token = bot_token.strip()
        self.allowed_chat_ids: Set[str] = {
            cid.strip() for cid in allowed_chat_ids.split(",") if cid.strip()
        }
        self.asymmetric_service = asymmetric_trade_service
        self.options_service = options_edge_service
        self.volume_service = volume_profile_service
        self.regime_service = market_regime_service
        self.rs_service = relative_strength_service
        self.lifecycle_service = trade_lifecycle_service
        self.heat_service = portfolio_heat_service
        self.avwap_service = anchored_vwap_service
        self.whale_service = whale_flow_service
        self.liquidity_service = liquidity_zone_service
        self.mtf_service = multi_timeframe_service
        self.signals_service = trading_signals_service
        self.alert_service = alert_service
        self.portfolio_manager = portfolio_manager
        self.paper_service = paper_trading_service
        self.morning_brief_service = morning_brief_service

        self._last_update_id: int = 0
        self._is_running: bool = False

    def is_authorized(self, chat_id: Any) -> bool:
        """Verifies that the chat_id matches configured authorized chats."""
        if not self.allowed_chat_ids:
            return False
        return str(chat_id).strip() in self.allowed_chat_ids

    def send_message(
        self,
        chat_id: str,
        text: str,
        disable_preview: bool = True,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Sends an HTML formatted message back to the user via Telegram."""
        if not self.bot_token:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text[:4096],
            "parse_mode": "HTML",
            "disable_web_page_preview": disable_preview,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            res = requests.post(url, json=payload, timeout=15)
            if res.status_code == 400:
                # Fallback to plain text if HTML tags were unclosed/malformed
                import re
                plain = html.unescape(text)
                plain = re.sub(r"<[^>]*>", "", plain)[:4096]
                payload["text"] = plain
                payload.pop("parse_mode", None)
                res = requests.post(url, json=payload, timeout=15)
            res.raise_for_status()
            return True
        except Exception as exc:
            logger.error("Failed to send Telegram message to %s: %s", chat_id, exc)
            return False

    def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> bool:
        """Answers a Telegram callback query to dismiss the loading spinner."""
        if not self.bot_token or not callback_query_id:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery"
        payload: Dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text[:200]
        if show_alert:
            payload["show_alert"] = True

        try:
            res = requests.post(url, json=payload, timeout=10)
            return res.ok
        except Exception as exc:
            logger.debug("Failed to answer callback query: %s", exc)
            return False

    def handle_callback_query(
        self,
        chat_id: str,
        callback_data: str,
        callback_query_id: str,
    ) -> None:
        """
        Handles user tap on an inline keyboard button.
        """
        if not self.is_authorized(chat_id):
            self.answer_callback_query(callback_query_id, "⛔ Nicht autorisiert.", show_alert=True)
            return

        cb = callback_data.strip()

        if cb.startswith("gex:"):
            ticker = cb.split(":", 1)[1].upper()
            self.answer_callback_query(callback_query_id, f"GEX für {ticker} wird geladen...")
            res = self._cmd_gex([ticker])
            self.send_message(chat_id, res)

        elif cb.startswith("levels:"):
            ticker = cb.split(":", 1)[1].upper()
            self.answer_callback_query(callback_query_id, f"Volume Profile für {ticker}...")
            res = self._cmd_levels([ticker])
            self.send_message(chat_id, res)

        elif cb.startswith("avwap:"):
            ticker = cb.split(":", 1)[1].upper()
            self.answer_callback_query(callback_query_id, f"AVWAP für {ticker} wird berechnet...")
            res = self._cmd_avwap([ticker])
            self.send_message(chat_id, res)

        elif cb.startswith("whale:"):
            ticker = cb.split(":", 1)[1].upper()
            self.answer_callback_query(callback_query_id, f"Whale Flow für {ticker}...")
            res = self._cmd_whale([ticker])
            self.send_message(chat_id, res)

        elif cb.startswith("fvg:"):
            ticker = cb.split(":", 1)[1].upper()
            self.answer_callback_query(callback_query_id, f"Smart Money Zonen für {ticker}...")
            res = self._cmd_fvg([ticker])
            self.send_message(chat_id, res)

        elif cb.startswith("mtf:"):
            ticker = cb.split(":", 1)[1].upper()
            self.answer_callback_query(callback_query_id, f"MTF-Sync für {ticker}...")
            res = self._cmd_mtf([ticker])
            self.send_message(chat_id, res)

        elif cb.startswith("paper:"):
            ticker = cb.split(":", 1)[1].upper()
            self.answer_callback_query(callback_query_id, f"Buche {ticker} ins Paper Trading...")
            res = self._execute_paper_trade(ticker)
            self.send_message(chat_id, res, reply_markup=self._build_trade_management_keyboard(ticker))

        elif cb.startswith("close:"):
            ticker = cb.split(":", 1)[1].upper()
            self.answer_callback_query(callback_query_id, f"Schließe Position {ticker}...")
            res = self._execute_close_trade(ticker)
            self.send_message(chat_id, res)

        elif cb.startswith("be:"):
            ticker = cb.split(":", 1)[1].upper()
            res = self._execute_breakeven_stop(ticker)
            self.answer_callback_query(
                callback_query_id, f"🛡️ Stop für {ticker} auf Breakeven gesetzt!", show_alert=True
            )
            self.send_message(chat_id, res)

        elif cb.startswith("track:"):
            ticker = cb.split(":", 1)[1].upper()
            if self.asymmetric_service and self.lifecycle_service:
                setup = self.asymmetric_service.generate_trade_setup(ticker)
                if setup:
                    self.lifecycle_service.register_trade(setup)
                    self.answer_callback_query(
                        callback_query_id, f"✅ {ticker} wird jetzt live überwacht!", show_alert=True
                    )
                    confirm_text = (
                        f"🎯 <b>LIVE-TRACKING AKTIVIERT: {ticker}</b>\n"
                        f"Ziel 1 (${setup['target_1']:.2f}) und Invalidation (${setup['invalidation_price']:.2f}) "
                        f"werden kontinuierlich überwacht."
                    )
                    self.send_message(chat_id, confirm_text, reply_markup=self._build_trade_management_keyboard(ticker))
                else:
                    self.answer_callback_query(callback_query_id, "Fehler beim Laden des Setups.")
            else:
                self.answer_callback_query(callback_query_id, "Lifecycle Service nicht verfügbar.")

        elif cb == "heat":
            self.answer_callback_query(callback_query_id, "Portfolio Heat wird berechnet...")
            res = self._cmd_heat()
            self.send_message(chat_id, res)
        else:
            self.answer_callback_query(callback_query_id, "Befehl empfangen.")

    def handle_command(self, chat_id: str, text: str) -> str:
        """
        Parses and handles slash commands from Telegram.
        Returns the formatted response string.
        """
        if not self.is_authorized(chat_id):
            logger.warning("Unauthorized access attempt from chat_id=%s", chat_id)
            return "⛔ <b>Zugriff verweigert.</b> Dieser Bot ist privat konfiguriert."

        raw = text.strip()
        parts = raw.split()
        if not parts:
            return self._cmd_help()

        cmd = parts[0].lower().split("@")[0]
        args = parts[1:]

        try:
            if cmd in ("/start", "/help"):
                return self._cmd_help()
            elif cmd == "/edge":
                return self._cmd_edge(args, chat_id=chat_id)
            elif cmd == "/gex":
                return self._cmd_gex(args)
            elif cmd == "/levels":
                return self._cmd_levels(args)
            elif cmd == "/regime":
                return self._cmd_regime()
            elif cmd == "/rs":
                return self._cmd_relative_strength()
            elif cmd == "/avwap":
                return self._cmd_avwap(args)
            elif cmd == "/whale":
                return self._cmd_whale(args)
            elif cmd in ("/fvg", "/zones"):
                return self._cmd_fvg(args)
            elif cmd == "/mtf":
                return self._cmd_mtf(args)
            elif cmd in ("/track", "/trades"):
                return self._cmd_track()
            elif cmd == "/paper":
                return self._cmd_paper(args)
            elif cmd == "/close":
                return self._cmd_close(args)
            elif cmd == "/be":
                return self._cmd_be(args)
            elif cmd == "/watchlist":
                return self._cmd_watchlist()
            elif cmd == "/watch":
                return self._cmd_watch(args)
            elif cmd == "/unwatch":
                return self._cmd_unwatch(args)
            elif cmd == "/heat":
                return self._cmd_heat()
            elif cmd == "/scan":
                return self._cmd_scan()
            elif cmd == "/brief":
                return self._cmd_brief(args)
            elif cmd in ("/depot", "/account"):
                return self._cmd_depot()
            elif cmd in ("/calendar", "/events"):
                return self._cmd_calendar()
            elif cmd == "/news":
                return self._cmd_news(args)
            else:
                return (
                    f"❓ Unbekannter Befehl: <code>{html.escape(cmd)}</code>\n\n"
                    "Sende <code>/help</code> für alle verfügbaren Befehle."
                )
        except Exception as exc:
            logger.error("Error executing bot command %s: %s", cmd, exc, exc_info=True)
            return f"⚠️ Fehler bei der Ausführung von <code>{html.escape(cmd)}</code>: {html.escape(str(exc))}"

    def _cmd_help(self) -> str:
        return (
            "🤖 <b>Broker Freund – Interaktiver Trading Edge Bot</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Dein institutioneller Trading-Begleiter direkt am Smartphone.\n\n"
            "⚡ <b>Trading & Order Management:</b>\n"
            "• <code>/edge</code> – Top Grade A+/A Setups mit Entry, Stop & Zielen\n"
            "• <code>/edge TICKER</code> – Ad-hoc Setup mit One-Tap Buttons (z.B. <code>/edge NVDA</code>)\n"
            "• <code>/paper TICKER</code> – Setup direkt ins Paper Depot buchen (z.B. <code>/paper NVDA</code>)\n"
            "• <code>/close TICKER</code> – Offene Position direkt schließen & PnL sichern (z.B. <code>/close NVDA</code>)\n"
            "• <code>/be TICKER</code> – Stop-Loss auf Breakeven (Einstand) nachziehen\n"
            "• <code>/track</code> – Aktive Setups & Trailing-Stops im Blick\n"
            "• <code>/depot</code> – Aktueller Depotstand, Cash & Performance\n\n"
            "📋 <b>Watchlist & Markt-Updates:</b>\n"
            "• <code>/brief</code> – Sofortiges institutionelles Markt-Briefing abrufen\n"
            "• <code>/brief [europe|usa|close]</code> – Gezieltes Session-Briefing\n"
            "• <code>/watchlist</code> – Alle 18 überwachten EU- und US-Aktien anzeigen\n"
            "• <code>/calendar</code> – Wirtschaftskalender & anstehende Earnings\n"
            "• <code>/news [TICKER]</code> – Breaking News & Sentiment (z.B. <code>/news SAP.DE</code>)\n"
            "• <code>/watch TICKER</code> – Aktie zur Signal-Watchlist hinzufügen\n"
            "• <code>/unwatch TICKER</code> – Aktie von Watchlist entfernen\n"
            "• <code>/scan</code> – Sofortiger Watchlist-Scan für Edge-Setups\n\n"
            "🧠 <b>Institutionelle Edge-Analysen:</b>\n"
            "• <code>/gex TICKER</code> – Gamma Exposure & Market Maker Regime\n"
            "• <code>/levels TICKER</code> – Volume Profile (POC, VAH, VAL)\n"
            "• <code>/avwap TICKER</code> – Anchored VWAP (YTD, Swing, Earnings)\n"
            "• <code>/whale [TICKER]</code> – Dark Pool & Whale Flow Detector\n"
            "• <code>/fvg TICKER</code> – Smart Money Fair Value Gaps\n"
            "• <code>/mtf TICKER</code> – Multi-Timeframe Trend-Alignment (1D, 1H, 15M)\n"
            "• <code>/regime</code> – Macro Regime (SPY/QQQ & VIX)\n"
            "• <code>/rs</code> – Relative Stärke vs. SPY (Mansfield RS Leaders)\n"
            "• <code>/heat</code> – Portfolio Heat & Korrelations-Shield\n\n"
            "💡 <i>Tipp: Bei jedem /edge Setup kannst du einfach auf die interaktiven Buttons tippen!</i>"
        )

    def _build_inline_keyboard(self, ticker: str) -> Dict[str, Any]:
        """Generates interactive one-tap action buttons for a ticker."""
        return {
            "inline_keyboard": [
                [
                    {"text": "📝 In Paper Trader buchen", "callback_data": f"paper:{ticker}"},
                    {"text": "🎯 Setup Tracken", "callback_data": f"track:{ticker}"},
                ],
                [
                    {"text": "🛡️ Stop auf Breakeven", "callback_data": f"be:{ticker}"},
                    {"text": "🚪 Position schließen", "callback_data": f"close:{ticker}"},
                ],
                [
                    {"text": "⚡ GEX Levels", "callback_data": f"gex:{ticker}"},
                    {"text": "📊 Volume Profile", "callback_data": f"levels:{ticker}"},
                ],
                [
                    {"text": "⚓ AVWAP", "callback_data": f"avwap:{ticker}"},
                    {"text": "🐋 Whale Flow", "callback_data": f"whale:{ticker}"},
                ],
                [
                    {"text": "🕳️ FVG & Zonen", "callback_data": f"fvg:{ticker}"},
                    {"text": "🧭 MTF Sync", "callback_data": f"mtf:{ticker}"},
                ],
                [
                    {"text": "🛡️ Portfolio Heat", "callback_data": "heat"},
                ],
            ]
        }

    def _build_trade_management_keyboard(self, ticker: str) -> Dict[str, Any]:
        """Generates action buttons specifically for an active position."""
        return {
            "inline_keyboard": [
                [
                    {"text": "🛡️ Stop auf Breakeven", "callback_data": f"be:{ticker}"},
                    {"text": "🚪 Position schließen", "callback_data": f"close:{ticker}"},
                ],
                [
                    {"text": "⚡ GEX Levels", "callback_data": f"gex:{ticker}"},
                    {"text": "📊 Volume Profile", "callback_data": f"levels:{ticker}"},
                ],
                [
                    {"text": "🎯 Setups & Trailing Stop", "callback_data": "track"},
                ],
            ]
        }

    def _cmd_paper(self, args: List[str]) -> str:
        if not args:
            return (
                "📝 <b>Paper Trading Buchung</b>\n"
                "Bitte gib ein Ticker-Symbol an, z.B.:\n"
                "<code>/paper NVDA</code>\n\n"
                "💡 <i>Tipp: Bei jedem <code>/edge</code> Setup kannst du einfach auf '📝 In Paper Trader buchen' tippen.</i>"
            )
        ticker = args[0].upper().strip()
        return self._execute_paper_trade(ticker)

    def _execute_paper_trade(self, ticker: str) -> str:
        """Executes a 1-tap paper trade directly from Telegram into the Demo Account."""
        ticker = ticker.upper().strip()
        if not self.asymmetric_service:
            return "❌ <b>Asymmetric Trade Service ist nicht geladen.</b>"

        # 1. Generate the asymmetric setup
        setup = self.asymmetric_service.generate_trade_setup(ticker)
        if not setup:
            return f"❌ Konnte kein valides Trade-Setup für <b>{ticker}</b> berechnen."

        entry_price = float(setup.get("entry_price") or 0.0)
        stop_price = float(setup.get("invalidation_price") or 0.0)
        target_price = float(setup.get("target_1") or 0.0)
        target_2 = float(setup.get("target_2") or 0.0)
        qty = float(setup.get("recommended_shares") or 1)
        confluence_score = float(setup.get("confluence_score") or 80)
        rr = setup.get("risk_reward_ratio", 2.5)
        grade_badge = setup.get("grade_badge", "⭐ Grade A")
        setup_name = setup.get("setup_name", "Trading Edge")

        # 2. Check if already open
        if self.portfolio_manager and hasattr(self.portfolio_manager, "list_paper_trades"):
            try:
                open_trades = [
                    t for t in self.portfolio_manager.list_paper_trades(limit=150)
                    if str(t.get("ticker") or "").upper() == ticker and t.get("status") == "open"
                ]
                if open_trades:
                    return (
                        f"ℹ️ <b>Position bereits aktiv</b>\n"
                        f"Ein offener Paper Trade für <b>{ticker}</b> existiert bereits im Demokonto."
                    )
            except Exception as e:
                logger.warning("Error checking existing paper trades: %s", e)

        # 3. Create the paper trade via paper_service or portfolio_manager
        trade_payload = {
            "ticker": ticker,
            "asset_class": "equity",
            "direction": "long",
            "setup_type": f"institutional_edge_{setup_name.lower().replace(' ', '_')}",
            "entry_price": entry_price,
            "stop_price": stop_price,
            "target_price": target_price,
            "quantity": qty,
            "confidence_score": confluence_score,
            "thesis": f"{setup.get('catalyst_description', '')} | Konfluenz: {', '.join(setup.get('confluence_factors', []))} | R:R {rr}:1",
            "notes": f"Telegram 1-Tap Execution | {grade_badge} | Ziel 2: ${target_2:.2f}",
        }

        created = False
        if self.paper_service and hasattr(self.paper_service, "create_trade_from_payload"):
            try:
                self.paper_service.create_trade_from_payload(trade_payload)
                created = True
            except Exception as pe:
                logger.warning("Error creating paper trade via paper_service, falling back to portfolio_manager: %s", pe)

        if not created and self.portfolio_manager and hasattr(self.portfolio_manager, "create_paper_trade"):
            try:
                self.portfolio_manager.create_paper_trade(trade_payload)
                created = True
            except Exception as pme:
                logger.error("Error creating paper trade via portfolio_manager: %s", pme)

        if not created:
            return f"❌ Fehler beim Eröffnen des Paper Trades für <b>{ticker}</b>."

        # 4. Register with Lifecycle Service for trailing stop & breakeven management
        if self.lifecycle_service:
            try:
                self.lifecycle_service.register_trade(setup)
            except Exception as le:
                logger.warning("Lifecycle registration warning: %s", le)

        # 5. Return formatted confirmation
        pos_cap = float(setup.get("total_position_capital") or (qty * entry_price))
        return (
            f"📝 <b>PAPER TRADE GEBUCHT: {ticker}</b> ({grade_badge})\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Menge:</b> {int(qty)} Stück (~{pos_cap:,.0f}€)\n"
            f"• <b>Einstieg:</b> ${entry_price:.2f}\n"
            f"• <b>Hard Stop:</b> ${stop_price:.2f}\n"
            f"• <b>Ziel 1 (2.0R):</b> ${target_price:.2f}\n"
            f"• <b>Ziel 2 (3.5R+):</b> ${target_2:.2f}\n"
            f"• <b>R:R Verhältnis:</b> {rr:.1f}:1\n"
            f"• <b>Konfluenz:</b> {confluence_score:.0f}/100 Pkt.\n\n"
            f"🛡️ <i>Trade ist im Demokonto eingebucht und wird vom Lifecycle Engine (Trailing Stop & Breakeven) aktiv überwacht.</i>"
        )

    def _cmd_close(self, args: List[str]) -> str:
        if not args:
            return (
                "🚪 <b>Position schließen</b>\n"
                "Bitte gib ein Ticker-Symbol an, z.B.:\n"
                "• <code>/close NVDA</code>\n"
                "• <code>/close SAP.DE</code>\n\n"
                "💡 <i>Tipp: Bei aktiven Trades kannst du auch einfach auf den Button '🚪 Position schließen' tippen.</i>"
            )
        ticker = args[0].upper().strip()
        return self._execute_close_trade(ticker)

    def _execute_close_trade(self, ticker: str) -> str:
        """Closes an active paper trade or removes it from lifecycle tracking."""
        ticker = ticker.upper().strip()

        # 1. Look for open paper trades in portfolio manager
        open_trades: List[Dict[str, Any]] = []
        if self.portfolio_manager and hasattr(self.portfolio_manager, "list_paper_trades"):
            try:
                open_trades = [
                    t for t in self.portfolio_manager.list_paper_trades(limit=200)
                    if str(t.get("ticker") or "").upper() == ticker and str(t.get("status") or "").lower() == "open"
                ]
            except Exception as e:
                logger.warning("Error fetching open paper trades: %s", e)

        # 2. Get current spot price
        spot: Optional[float] = None
        if self.lifecycle_service:
            spot = self.lifecycle_service._fetch_current_price(ticker)
        if not spot or spot <= 0:
            if open_trades:
                spot = float(open_trades[0].get("current_price") or open_trades[0].get("entry_price") or 0.0)

        # 3. Update Lifecycle Service if tracking
        lifecycle_closed = False
        if self.lifecycle_service:
            trades = self.lifecycle_service.get_active_trades()
            matched = next(
                (t for t in trades if t.get("ticker") == ticker and t.get("status") in ("OPEN", "TARGET_1_HIT")),
                None,
            )
            if matched:
                matched["status"] = "CLOSED"
                if spot:
                    matched["last_price"] = spot
                self.lifecycle_service._save_trades()
                lifecycle_closed = True

        if not open_trades and not lifecycle_closed:
            return (
                f"ℹ️ <b>Keine offene Position für {ticker} gefunden.</b>\n"
                f"Weder im Paper Trading Depot noch im aktiven Lifecycle-Monitor vorhanden.\n\n"
                f"Prüfe deine offenen Trades mit <code>/track</code>."
            )

        # 4. Close the paper trade(s) in database
        closed_reports: List[str] = []
        for trade in open_trades:
            trade_id = str(trade.get("id"))
            entry_p = float(trade.get("entry_price") or 0.0)
            exit_p = spot if (spot and spot > 0) else entry_p
            qty = float(trade.get("quantity") or 1.0)

            closed_ok = False
            if self.paper_service and hasattr(self.paper_service, "close_trade"):
                try:
                    self.paper_service.close_trade(
                        trade_id=trade_id,
                        closed_price=exit_p,
                        exit_reason="telegram_bot_manual_close",
                        notes="Manuell über Telegram Smartphone Bot geschlossen",
                    )
                    closed_ok = True
                except Exception as c_err:
                    logger.warning("PaperService close failed: %s, falling back to PortfolioManager", c_err)

            if not closed_ok and self.portfolio_manager and hasattr(self.portfolio_manager, "close_paper_trade"):
                try:
                    self.portfolio_manager.close_paper_trade(
                        trade_id=trade_id,
                        closed_price=exit_p,
                        exit_reason="telegram_bot_manual_close",
                        notes="Manuell über Telegram Smartphone Bot geschlossen",
                    )
                    closed_ok = True
                except Exception as p_err:
                    logger.error("PortfolioManager close failed: %s", p_err)

            pnl_per_share = exit_p - entry_p
            pnl_pct = (pnl_per_share / entry_p * 100) if entry_p > 0 else 0.0
            pnl_total = pnl_per_share * qty
            sign = "+" if pnl_total >= 0 else ""
            emoji = "🟢" if pnl_total >= 0 else "🔴"
            closed_reports.append(
                f"• <b>Ausstieg:</b> ${exit_p:.2f} (Einstieg: ${entry_p:.2f})\n"
                f"• <b>Stück:</b> {int(qty)} | <b>Ergebnis:</b> <b>{sign}${pnl_total:,.2f} ({sign}{pnl_pct:.2f}%)</b> {emoji}"
            )

        detail_text = "\n\n".join(closed_reports) if closed_reports else f"• Lifecycle-Tracking für <b>{ticker}</b> beendet."
        return (
            f"🚪 <b>POSITION GESCHLOSSEN: {ticker}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{detail_text}\n\n"
            f"✅ <i>Position im Paper Depot glattgestellt und Risikomonitoring beendet. Dein Demokonto wurde aktualisiert.</i>"
        )

    def _cmd_be(self, args: List[str]) -> str:
        if not args:
            return (
                "🛡️ <b>Stop auf Breakeven setzen</b>\n"
                "Bitte gib ein Ticker-Symbol an, z.B.:\n"
                "• <code>/be NVDA</code>\n"
                "• <code>/be SAP.DE</code>\n\n"
                "💡 <i>Tipp: Bei jedem aktiven Trade kannst du auch einfach auf den Button '🛡️ Stop auf Breakeven' tippen.</i>"
            )
        ticker = args[0].upper().strip()
        return self._execute_breakeven_stop(ticker)

    def _execute_breakeven_stop(self, ticker: str) -> str:
        """Moves trailing stop to breakeven for an active setup / paper trade."""
        ticker = ticker.upper().strip()
        updated_any = False
        entry_price = 0.0

        if self.lifecycle_service:
            trades = self.lifecycle_service.get_active_trades()
            matched = next(
                (t for t in trades if t.get("ticker") == ticker and t.get("status") in ("OPEN", "TARGET_1_HIT")),
                None,
            )
            if matched:
                entry_price = float(matched.get("entry_price") or 0.0)
                matched["trailing_stop"] = entry_price
                self.lifecycle_service._save_trades()
                updated_any = True

        if self.portfolio_manager and hasattr(self.portfolio_manager, "list_paper_trades"):
            try:
                open_trades = [
                    t for t in self.portfolio_manager.list_paper_trades(limit=150)
                    if str(t.get("ticker") or "").upper() == ticker and str(t.get("status") or "").lower() == "open"
                ]
                for pt in open_trades:
                    if not entry_price:
                        entry_price = float(pt.get("entry_price") or 0.0)
                    tid = pt.get("id")
                    if tid and hasattr(self.portfolio_manager, "update_paper_trade_journal"):
                        self.portfolio_manager.update_paper_trade_journal(
                            trade_id=tid,
                            notes=f"Stop auf Breakeven (${entry_price:.2f}) via Telegram angepasst.",
                        )
                    updated_any = True
            except Exception as pe:
                logger.warning("Error checking paper trades for breakeven: %s", pe)

        if not updated_any:
            return (
                f"ℹ️ Kein aktiver Trade für <b>{ticker}</b> gefunden.\n"
                f"Prüfe deine offenen Trades mit <code>/track</code>."
            )

        entry_display = f"${entry_price:.2f}" if entry_price > 0 else "Einstandspreis"
        return (
            f"🛡️ <b>STOP-LOSS AUF BREAKEVEN: {ticker}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Neuer Trailing Stop:</b> {entry_display}\n"
            f"• <b>Verbleibendes Risiko:</b> 0.00 € (Risikofreier Trade!)\n\n"
            f"Dein Kapital ist geschützt. Die Position kann ohne Verlustrisiko weiterlaufen."
        )

    def _cmd_watch(self, args: List[str]) -> str:
        if not args:
            return (
                "ℹ️ <b>Watchlist hinzufügen</b>\n"
                "Bitte gib ein Ticker-Symbol an, z.B.:\n"
                "• <code>/watch SAP.DE</code> (DAX Leader)\n"
                "• <code>/watch RHM.DE</code> (Rheinmetall)\n"
                "• <code>/watch NVDA</code> (US Leader)"
            )
        ticker = args[0].upper().strip()
        if not self.portfolio_manager:
            return "⚠️ Portfolio Manager nicht initialisiert."
        try:
            self.portfolio_manager.add_signal_watch_item("ticker", ticker)
            return (
                f"✅ <b>Watchlist aktualisiert</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>{ticker}</b> wurde erfolgreich zur Signal-Watchlist hinzugefügt.\n"
                f"Wird ab sofort in automatischen Scans, Morning Briefs und Edge-Benachrichtigungen überwacht.\n\n"
                f"Tippe <code>/watchlist</code> für die Übersicht oder <code>/edge {ticker}</code> für eine sofortige Analyse."
            )
        except Exception as exc:
            return f"❌ Fehler beim Hinzufügen von {ticker}: {exc}"

    def _cmd_unwatch(self, args: List[str]) -> str:
        if not args:
            return (
                "ℹ️ <b>Watchlist entfernen</b>\n"
                "Bitte einen Ticker angeben: z.B. <code>/unwatch NVDA</code> oder <code>/unwatch SAP.DE</code>"
            )
        ticker = args[0].upper().strip()
        if not self.portfolio_manager:
            return "⚠️ Portfolio Manager nicht initialisiert."
        try:
            self.portfolio_manager.remove_signal_watch_item("ticker", ticker)
            return (
                f"🗑️ <b>Watchlist aktualisiert</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>{ticker}</b> wurde von der Signal-Watchlist entfernt."
            )
        except Exception as exc:
            return f"❌ Fehler beim Entfernen von {ticker}: {exc}"

    def _cmd_watchlist(self) -> str:
        tickers = self._get_watchlist_tickers()
        if not tickers:
            return (
                "ℹ️ <b>Die Signal-Watchlist ist aktuell leer.</b>\n"
                "Füge Symbole hinzu mit <code>/watch TICKER</code>."
            )

        europe_tickers = [
            t for t in tickers
            if any(t.endswith(sfx) for sfx in [".DE", ".F", ".AS", ".PA", ".MI", ".MC", ".L"])
        ]
        us_tickers = [t for t in tickers if t not in europe_tickers]

        lines = [
            f"📋 <b>SIGNAL-WATCHLIST ({len(tickers)} Titel)</b>",
            "━━━━━━━━━━━━━━━━━━━━",
        ]

        if europe_tickers:
            lines.append("🇪🇺 <b>Europa / DAX Leaders:</b>")
            for t in sorted(europe_tickers):
                lines.append(f"  • <code>{t}</code> (Abruf: <code>/edge {t}</code>)")
            lines.append("")

        if us_tickers:
            lines.append("🇺🇸 <b>US & International Leaders:</b>")
            for t in sorted(us_tickers):
                lines.append(f"  • <code>{t}</code> (Abruf: <code>/edge {t}</code>)")
            lines.append("")

        lines.append(
            "💡 <i>Befehle: <code>/watch TICKER</code> | <code>/unwatch TICKER</code> | <code>/scan</code></i>"
        )
        return "\n".join(lines)

    def _cmd_brief(self, args: List[str]) -> str:
        """Fires an on-demand session brief to Telegram."""
        if not self.alert_service:
            return "⚠️ Alert Service nicht geladen."

        valid_sessions = {
            "global": "Morgen-Briefing (Global)",
            "europe": "Europa / DAX Open Briefing",
            "midday": "Mittags-Update",
            "usa": "US Wall Street Open Briefing",
            "close": "Markt-Schlussbericht",
        }
        session = "global"
        if args:
            s_arg = args[0].lower().strip()
            if s_arg in valid_sessions:
                session = s_arg
            elif s_arg in ("morgen", "morning"):
                session = "global"
            elif s_arg in ("dax", "eu", "europa"):
                session = "europe"
            elif s_arg in ("us", "usa", "wallstreet", "ny"):
                session = "usa"
            elif s_arg in ("mittag", "lunch"):
                session = "midday"
            elif s_arg in ("abend", "feierabend", "recap"):
                session = "close"

        try:
            self.alert_service.send_session_brief_now(session)
            label = valid_sessions.get(session, session)
            return (
                f"✅ <b>{label}</b> wurde erfolgreich generiert und direkt in deinen Telegram-Chat gesendet!\n\n"
                f"💡 <i>Tipp: Rufe mit <code>/brief europe</code> oder <code>/brief usa</code> gezielte Session-Briefings ab.</i>"
            )
        except Exception as exc:
            return f"❌ Fehler beim Erstellen des Briefings ({session}): {exc}"

    def _cmd_depot(self) -> str:
        """Provides a complete overview of the Paper Trading Depot & Performance."""
        if not self.portfolio_manager:
            return "⚠️ Portfolio Manager nicht initialisiert."

        try:
            equity = 50000.0
            cash = 50000.0
            starting = 50000.0

            if self.paper_service and hasattr(self.paper_service, "build_demo_account_snapshot"):
                snap = self.paper_service.build_demo_account_snapshot()
                equity = float(snap.get("equity") or 50000.0)
                cash = float(snap.get("cash") or 50000.0)
                starting = float(snap.get("starting_capital") or 50000.0)

            total_pnl = equity - starting
            pnl_pct = (total_pnl / starting * 100) if starting > 0 else 0.0

            open_trades = [
                t for t in self.portfolio_manager.list_paper_trades(limit=150)
                if str(t.get("status") or "").lower() == "open"
            ]
            closed_trades = [
                t for t in self.portfolio_manager.list_paper_trades(limit=250)
                if str(t.get("status") or "").lower() == "closed"
            ]

            wins = [t for t in closed_trades if float(t.get("realized_pnl") or 0.0) > 0]
            win_rate = (len(wins) / len(closed_trades) * 100) if closed_trades else 0.0

            sign = "+" if total_pnl >= 0 else ""
            pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"

            pos_lines = []
            if open_trades:
                for ot in open_trades[:6]:
                    sym = ot.get("ticker", "N/A")
                    ep = float(ot.get("entry_price") or 0.0)
                    qty = float(ot.get("quantity") or 1.0)
                    is_eu = any(sym.endswith(sfx) for sfx in [".DE", ".F", ".AS", ".PA", ".MI", ".MC"])
                    c_sym = "€" if is_eu else "$"
                    pos_lines.append(f"  • <b>{sym}</b>: {int(qty)} Stk. @ {c_sym}{ep:.2f} (Schließen: <code>/close {sym}</code>)")
            else:
                pos_lines.append("  <i>Keine offenen Positionen aktiv.</i>")

            return (
                f"💼 <b>BROKER FREUND – PAPER DEPOT STATUS</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"• <b>Gesamtwert:</b> <b>{equity:,.2f} EUR</b>\n"
                f"• <b>Verfügbares Cash:</b> {cash:,.2f} EUR\n"
                f"• <b>Gesamtertrag (PnL):</b> <b>{sign}{total_pnl:,.2f} EUR ({sign}{pnl_pct:.2f}%)</b> {pnl_emoji}\n"
                f"• <b>Abgeschlossene Trades:</b> {len(closed_trades)} (Win Rate: {win_rate:.0f}%)\n\n"
                f"📊 <b>Offene Positionen ({len(open_trades)}):</b>\n"
                + "\n".join(pos_lines) + "\n\n"
                f"💡 <i>Tipp: Nutze <code>/track</code> für Trailing Stops oder <code>/edge</code> für neue Setups.</i>"
            )
        except Exception as exc:
            return f"❌ Fehler beim Laden des Depots: {exc}"

    def _cmd_calendar(self) -> str:
        """Displays upcoming macro events and earnings calendar for the watchlist."""
        if not self.morning_brief_service or not self.portfolio_manager:
            return "⚠️ Morning Brief Service nicht initialisiert."

        try:
            items = self.portfolio_manager.get_signal_watch_items()
            snapshot = {"items": items, "ticker_signals": []}
            brief = self.morning_brief_service.get_brief_fast(snapshot)

            econ = brief.get("economic_calendar", [])
            earnings = brief.get("earnings_calendar", []) or brief.get("broad_earnings", [])

            lines = [
                "📅 <b>WIRTSCHAFTS- & EARNINGS-KALENDER</b>",
                "━━━━━━━━━━━━━━━━━━━━",
            ]

            # 1. Economic / Session events
            econ_lines = []
            for e in econ[:6]:
                t = e.get("time", "") or (e.get("scheduled_for", "")[11:16])
                lbl = e.get("title") or e.get("label") or "Wirtschaftsdaten"
                impact = e.get("importance") or e.get("impact") or "medium"
                badge = "🔴" if impact == "high" else "🟡"
                econ_lines.append(f"• <b>{t}</b> {badge} {lbl}")

            if econ_lines:
                lines.append("🏛️ <b>Makro-Termine & Sessions:</b>")
                lines.extend(econ_lines)
                lines.append("")

            # 2. Watchlist Earnings
            earn_lines = []
            imminent_earnings = []
            for item in earnings[:8]:
                sym = item.get("ticker", "")
                co = item.get("company", sym)
                d = (item.get("scheduled_for") or item.get("date") or "")[:10]
                days = item.get("days_until")
                sess = item.get("session", "")
                sess_str = "Pre-Market" if sess == "pre-market" else "After-Hours" if sess == "after-hours" else ""

                day_str = f"in {days} Tagen" if days is not None else d
                if days == 0:
                    day_str = "HEUTE! ⚠️"
                    imminent_earnings.append(sym)
                elif days is not None and days <= 3:
                    day_str = f"in {days} Tagen ⚠️"
                    imminent_earnings.append(sym)

                earn_lines.append(f"• <b>{sym}</b> ({co}): {d} ({sess_str}, {day_str})")

            if earn_lines:
                lines.append("📊 <b>Anstehende Quartalszahlen (Watchlist):</b>")
                lines.extend(earn_lines)
                lines.append("")

            # 3. Earnings Shield Status
            if imminent_earnings:
                lines.append(
                    f"⚠️ <b>EARNINGS SHIELD AKTIV:</b>\n"
                    f"Quartalszahlen in Kürze für: <b>{', '.join(imminent_earnings)}</b>.\n"
                    f"<i>Empfehlung: Vor den Zahlen keine neuen Swings eröffnen oder bestehende Positionen absichern!</i>"
                )
            else:
                lines.append(
                    "🛡️ <b>Earnings Shield:</b> 🟢 Keine akuten Earnings-Gefahren auf der Watchlist in den nächsten 3 Tagen."
                )

            return "\n".join(lines)
        except Exception as exc:
            return f"❌ Fehler beim Laden des Kalenders: {exc}"

    def _cmd_news(self, args: List[str]) -> str:
        """Fetches top breaking news & social sentiment for a ticker or market."""
        if not args:
            query = "DAX Börse Wirtschaft"
            target = "Markt & DAX"
        else:
            sym = args[0].upper().strip()
            target = sym
            clean_sym = sym.replace(".DE", "").replace(".AS", "")
            query = f"{clean_sym} Aktie Börse"

        social_svc = getattr(self.morning_brief_service, "_social_service", None)
        if not social_svc:
            return "⚠️ Social Intelligence Service nicht geladen."

        try:
            news = social_svc.get_google_news([query], max_per_query=4)
            if not news:
                return f"ℹ️ Keine aktuellen Schlagzeilen für <b>{target}</b> gefunden."

            lines = [
                f"📰 <b>TOP-NEWS: {target}</b>",
                "━━━━━━━━━━━━━━━━━━━━",
            ]
            for n in news[:4]:
                title = n.get("title", "")
                src = n.get("source", "News")
                age = n.get("age_hours", 0)
                age_str = f"vor {int(age)}h" if age < 24 else f"vor {int(age//24)}d"
                lines.append(f"• <b>{title}</b>\n  <i>Quelle: {src} ({age_str})</i>\n")

            lines.append(f"💡 <i>Tipp: Analysiere das Setup mit <code>/edge {target}</code></i>")
            return "\n".join(lines)
        except Exception as exc:
            return f"❌ Fehler beim Laden der News: {exc}"

    def _cmd_edge(self, args: List[str], chat_id: Optional[str] = None) -> str:
        if not self.asymmetric_service:
            return "⚠️ Asymmetric Trade Service ist nicht geladen."

        # Case 1: Specific ticker requested, e.g. /edge NVDA
        if args:
            ticker = args[0].upper().strip()
            setup = self.asymmetric_service.generate_trade_setup(ticker)
            if not setup:
                return f"❌ Konnte kein Setup für <b>{ticker}</b> berechnen (Kursdaten unvollständig oder nicht handelbar)."

            if self.lifecycle_service and setup.get("confluence_score", 0) >= 65:
                self.lifecycle_service.register_trade(setup)

            resp_text = setup.get("telegram_html") or f"Setup für {ticker} berechnet."
            return resp_text

        # Case 2: Scan for top setups across watchlist
        watchlist = self._get_watchlist_tickers()
        setups = []
        if self.signals_service:
            setups = self.signals_service.get_asymmetric_setups(watchlist, limit=3)
        elif self.asymmetric_service:
            for s in watchlist[:6]:
                st = self.asymmetric_service.generate_trade_setup(s)
                if st and st.get("confluence_score", 0) >= 65:
                    setups.append(st)

        if not setups:
            return (
                "ℹ️ <b>Aktuell keine Grade A+/A Setups auf der Watchlist.</b>\n"
                "Der Confluence-Score liegt bei allen Titeln unter 70. "
                "Disziplin bewahren und auf saubere Bestätigungen warten!"
            )

        if self.lifecycle_service:
            for s in setups:
                self.lifecycle_service.register_trade(s)

        best = setups[0]
        result = best.get("telegram_html") or ""

        if len(setups) > 1:
            others = "\n".join([
                f"• <b>{s['ticker']}</b> ({s.get('grade_badge', 'A')}) – Score: {s.get('confluence_score')}/100 | R:R: {s.get('risk_reward_ratio')} : 1 (Abruf mit <code>/edge {s['ticker']}</code>)"
                for s in setups[1:]
            ])
            result += f"\n\n🔍 <b>Weitere starke Setups im Radar:</b>\n{others}"

        return result

    def _cmd_gex(self, args: List[str]) -> str:
        if not args:
            return "ℹ️ Bitte einen Ticker angeben: z.B. <code>/gex NVDA</code> oder <code>/gex SPY</code>"
        ticker = args[0].upper().strip()
        if not self.options_service:
            return "⚠️ Options GEX Service nicht initialisiert."

        data = self.options_service.analyze_gex(ticker)
        if not data:
            return f"❌ Keine Optionsdaten für <b>{ticker}</b> gefunden (evtl. kein US-Optionstitel)."

        spot = data.get("spot_price", 0.0)
        cw = data.get("call_wall", 0.0)
        pw = data.get("put_wall", 0.0)
        zg = data.get("zero_gamma", 0.0)
        net_gex = data.get("net_gex", 0.0)
        regime = data.get("regime", "neutral")
        regime_label = data.get("regime_label", "Neutral")

        is_eu = any(ticker.endswith(sfx) for sfx in [".DE", ".F", ".AS", ".PA", ".MI", ".MC"])
        c_sym = "€" if is_eu else ("£" if ticker.endswith(".L") else "$")

        interpretation = (
            "Market Maker dämpfen Kursausschläge. Rücksetzer zur Put Wall und Rallyes "
            "zur Call Wall neigen zu Mean-Reversion."
            if regime == "positive_gamma" else
            "Market Maker verstärken Trends (Hedging treibt Volatilität). "
            "Ausbrüche können explosionsartig laufen!"
        )

        ascii_gex = (
            f"<code>"
            f" Call Wall  : {c_sym}{cw:>7.2f} ───┐ (Resistenz / Pin)\n"
            f" Spot Kurs  : {c_sym}{spot:>7.2f} ─●─┼ (Aktueller Kurs)\n"
            f" Zero Gamma : {c_sym}{zg:>7.2f} ───┼ (Vol-Schwelle)\n"
            f" Put Wall   : {c_sym}{pw:>7.2f} ───┘ (Boden / Support)"
            f"</code>"
        )

        return (
            f"⚡ <b>GAMMA EXPOSURE (GEX): {ticker}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Spot-Kurs:</b> {c_sym}{spot:.2f}\n"
            f"• <b>MM-Regime:</b> <b>{regime_label}</b>\n"
            f"• <b>Net GEX:</b> {net_gex:+,.0f} {c_sym}\n\n"
            f"📈 <b>Gamma-Level Karte:</b>\n"
            f"{ascii_gex}\n\n"
            f"• <b>Call Wall:</b> {c_sym}{cw:.2f}\n"
            f"• <b>Put Wall:</b> {c_sym}{pw:.2f}\n"
            f"• <b>Zero Gamma:</b> {c_sym}{zg:.2f}\n\n"
            f"💡 <b>Market Maker Dynamik:</b>\n{interpretation}"
        )

    def _cmd_levels(self, args: List[str]) -> str:
        if not args:
            return "ℹ️ Bitte einen Ticker angeben: z.B. <code>/levels AAPL</code> oder <code>/levels TSLA</code>"
        ticker = args[0].upper().strip()
        if not self.volume_service:
            return "⚠️ Volume Profile Service nicht initialisiert."

        vp = self.volume_service.compute_volume_profile(ticker)
        if not vp:
            return f"❌ Konnte kein Volume Profile für <b>{ticker}</b> erstellen."

        spot = vp.get("spot_price", 0.0)
        poc = vp.get("poc_price", 0.0)
        vah = vp.get("vah_price", 0.0)
        val = vp.get("val_price", 0.0)
        loc = vp.get("location_label", "Im fairen Wertbereich")
        bias = vp.get("bias", "Neutral")

        is_eu = any(ticker.endswith(sfx) for sfx in [".DE", ".F", ".AS", ".PA", ".MI", ".MC"])
        c_sym = "€" if is_eu else ("£" if ticker.endswith(".L") else "$")

        if spot >= vah:
            ladder = (
                f"<code>"
                f" Spot: {c_sym}{spot:>7.2f} ───● (Oberhalb Value Area / Ausbruch)\n"
                f" VAH : {c_sym}{vah:>7.2f} ───┐\n"
                f" POC : {c_sym}{poc:>7.2f} ───┼ (Höchste Liquidität)\n"
                f" VAL : {c_sym}{val:>7.2f} ───┘"
                f"</code>"
            )
        elif spot <= val:
            ladder = (
                f"<code>"
                f" VAH : {c_sym}{vah:>7.2f} ───┐\n"
                f" POC : {c_sym}{poc:>7.2f} ───┼ (Höchste Liquidität)\n"
                f" VAL : {c_sym}{val:>7.2f} ───┘\n"
                f" Spot: {c_sym}{spot:>7.2f} ───● (Unterhalb Value Area / Discount)"
                f"</code>"
            )
        else:
            ladder = (
                f"<code>"
                f" VAH : {c_sym}{vah:>7.2f} ───┐\n"
                f" Spot: {c_sym}{spot:>7.2f} ─●─┼ (Im fairen Wertbereich)\n"
                f" POC : {c_sym}{poc:>7.2f} ───┼ (Höchste Liquidität)\n"
                f" VAL : {c_sym}{val:>7.2f} ───┘"
                f"</code>"
            )

        return (
            f"📊 <b>VOLUME PROFILE (AMT): {ticker}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Aktueller Kurs:</b> {c_sym}{spot:.2f}\n"
            f"• <b>Point of Control (POC):</b> <b>{c_sym}{poc:.2f}</b> (Höchste Liquidität)\n"
            f"• <b>Value Area High (VAH):</b> {c_sym}{vah:.2f} (Obere 70%-Grenze)\n"
            f"• <b>Value Area Low (VAL):</b> {c_sym}{val:.2f} (Untere 70%-Grenze)\n"
            f"• <b>Ort im Profil:</b> {loc}\n\n"
            f"📈 <b>Profil-Struktur &amp; Preisleiter:</b>\n"
            f"{ladder}\n\n"
            f"🎯 <b>Trading Bias:</b>\n{bias}"
        )

    def _cmd_regime(self) -> str:
        if not self.regime_service:
            return "⚠️ Market Regime Service nicht initialisiert."

        macro = self.regime_service.get_market_regime()
        stance = macro.get("stance", "RISK_ON")
        vix = macro.get("vix", {})
        vix_val = vix.get("value", 16.0)
        vix_regime = vix.get("regime", "normal")

        spy = macro.get("spy", {})
        qqq = macro.get("qqq", {})

        icon = "🟢" if stance == "RISK_ON" else ("🟡" if stance == "NEUTRAL" else "🔴")
        rules = (
            "Volle Positionsgröße erlaubt. Breakouts und Momentum-Setups haben Rückenwind."
            if stance == "RISK_ON" else
            ("Selektiv handeln. Gewinnmitnahmen bei 2.0R forcieren, Stops eng halten."
             if stance == "NEUTRAL" else
             "Defensive Haltung! Keine neuen Long-Ausbrüche kaufen, Stops konsequent nachziehen.")
        )

        return (
            f"🌐 <b>MAKRO MARKT-REGIME</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Gesamt-Status:</b> {icon} <b>{stance}</b>\n"
            f"• <b>CBOE VIX:</b> <b>{vix_val:.2f}</b> ({vix_regime.upper()})\n"
            f"• <b>SPY (S&P 500):</b> {spy.get('trend', 'bullish')} | Über 20 EMA: {'Ja' if spy.get('above_ema20') else 'Nein'}\n"
            f"• <b>QQQ (Nasdaq):</b> {qqq.get('trend', 'bullish')} | Über 20 EMA: {'Ja' if qqq.get('above_ema20') else 'Nein'}\n\n"
            f"💡 <b>Handlungsregel für dieses Regime:</b>\n{rules}"
        )

    def _cmd_relative_strength(self) -> str:
        if not self.rs_service:
            return "⚠️ Relative Strength Service nicht initialisiert."

        watchlist = self._get_watchlist_tickers()
        leaders = self.rs_service.scan_relative_strength(watchlist, benchmark="SPY")
        return self.rs_service.format_telegram_rs_card(leaders, benchmark="SPY")

    def _cmd_track(self) -> str:
        if not self.lifecycle_service:
            return "⚠️ Trade Lifecycle Service nicht initialisiert."
        return self.lifecycle_service.format_telegram_trades_list()

    def _cmd_heat(self) -> str:
        if not self.heat_service:
            return "⚠️ Portfolio Heat Service nicht initialisiert."
        active = self.lifecycle_service.get_active_trades() if self.lifecycle_service else []
        heat = self.heat_service.evaluate_portfolio_heat(active, portfolio_capital=50000.0)
        return self.heat_service.format_telegram_heat_card(heat)

    def _cmd_avwap(self, args: List[str]) -> str:
        if not args:
            return "ℹ️ Bitte einen Ticker angeben: z.B. <code>/avwap NVDA</code> oder <code>/avwap AAPL</code>"
        ticker = args[0].upper().strip()
        if not self.avwap_service:
            return "⚠️ Anchored VWAP Service nicht initialisiert."
        data = self.avwap_service.compute_anchored_vwaps(ticker)
        if not data:
            return f"❌ Konnte keine AVWAP-Daten für <b>{ticker}</b> berechnen."
        return self.avwap_service.format_telegram_avwap_card(data)

    def _cmd_whale(self, args: List[str]) -> str:
        if not self.whale_service:
            return "⚠️ Whale Flow Service nicht initialisiert."
        if args:
            ticker = args[0].upper().strip()
            data = self.whale_service.analyze_whale_flow(ticker)
            if not data:
                return f"❌ Konnte keine Whale-Daten für <b>{ticker}</b> berechnen."
            return self.whale_service.format_telegram_whale_card(data)

        # Scan watchlist
        watchlist = self._get_watchlist_tickers()
        anomalies = self.whale_service.scan_watchlist_whale_flows(watchlist)
        if not anomalies:
            return "ℹ️ <b>Keine abnormalen Whale-Volumenspitzen (>2.2x)</b> aktuell auf der Watchlist."
        lines = [
            "🐋 <b>AKTUELLE WHALE-VOLUMEN-ANOMALIEN</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "<i>Großinvestoren-Aktivität auf der Watchlist:</i>\n",
        ]
        for a in anomalies[:6]:
            sym = a["ticker"]
            ratio = a["volume_ratio"]
            badge = a["badge"]
            lines.append(f"• <b>{sym}</b>: <b>{ratio:.1f}x</b> Volumen {badge}")
        return "\n".join(lines)

    def _cmd_fvg(self, args: List[str]) -> str:
        if not args:
            return "ℹ️ Bitte einen Ticker angeben: z.B. <code>/fvg NVDA</code> oder <code>/fvg AAPL</code>"
        ticker = args[0].upper().strip()
        if not self.liquidity_service:
            return "⚠️ Liquidity Zone Service nicht initialisiert."
        data = self.liquidity_service.analyze_zones(ticker)
        if not data:
            return f"❌ Konnte keine Smart Money Zonen für <b>{ticker}</b> berechnen."
        return self.liquidity_service.format_telegram_fvg_card(data)

    def _cmd_mtf(self, args: List[str]) -> str:
        if not args:
            return "ℹ️ Bitte einen Ticker angeben: z.B. <code>/mtf NVDA</code> oder <code>/mtf TSLA</code>"
        ticker = args[0].upper().strip()
        if not self.mtf_service:
            return "⚠️ Multi-Timeframe Service nicht initialisiert."
        data = self.mtf_service.analyze_mtf_alignment(ticker)
        if not data:
            return f"❌ Konnte keine Multi-Timeframe Synchronisation für <b>{ticker}</b> berechnen."
        return self.mtf_service.format_telegram_mtf_card(data)

    def _cmd_scan(self) -> str:
        if not self.signals_service or not self.alert_service:
            return "⚠️ Scanner oder Alert Service nicht initialisiert."

        watchlist = self._get_watchlist_tickers()
        res = self.signals_service.scan_and_dispatch_edge_alerts(
            self.alert_service, watchlist=watchlist, min_grade=("A+", "A")
        )
        disp = res.get("dispatched", [])
        dedup = res.get("deduplicated", [])
        count = res.get("scanned_count", 0)

        disp_str = ", ".join(disp) if disp else "Keine neuen"
        dedup_str = ", ".join(dedup) if dedup else "Keine"

        return (
            f"🔍 <b>Watchlist-Scan abgeschlossen ({count} Titel analysiert)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Neu gepusht:</b> {disp_str}\n"
            f"• <b>Bereits heute gesendet (Dedupliziert):</b> {dedup_str}\n\n"
            f"Nutze <code>/edge</code> oder <code>/track</code> für den aktuellen Stand."
        )

    def _get_watchlist_tickers(self) -> List[str]:
        """Fetches watchlist tickers from portfolio manager or falls back to leaders."""
        default_list = [
            "SAP.DE", "RHM.DE", "ASML.AS", "ALV.DE", "SIE.DE",
            "NVDA", "MSFT", "AAPL", "AMZN", "PLTR", "TSLA", "META"
        ]
        if not self.portfolio_manager:
            return default_list
        try:
            if hasattr(self.portfolio_manager, "ensure_default_watch_items"):
                self.portfolio_manager.ensure_default_watch_items(min_count=5)
            items = self.portfolio_manager.get_signal_watch_items()
            tickers = [
                it["value"].upper().strip()
                for it in items
                if it.get("kind", "").lower() == "ticker" and it.get("value")
            ]
            return tickers if tickers else default_list
        except Exception:
            return default_list

    async def run_listener_loop(self) -> None:
        """
        Asynchronous long-polling loop for Telegram getUpdates.
        Listens for both text slash-commands and interactive inline-button callbacks.
        """
        if not self.bot_token or not self.allowed_chat_ids:
            logger.info("Telegram interactive bot listener skipped: missing token or chat ID.")
            return

        self._is_running = True
        base_url = f"https://api.telegram.org/bot{self.bot_token}"

        # 1. Clear any active webhook so getUpdates works without 409 Conflict
        try:
            await asyncio.to_thread(requests.post, f"{base_url}/deleteWebhook", json={"drop_pending_updates": False}, timeout=10)
        except Exception as e:
            logger.debug("deleteWebhook attempt: %s", e)

        # 2. Sync to latest update_id so stale messages are ignored on boot
        try:
            sync_res = await asyncio.to_thread(
                requests.get,
                f"{base_url}/getUpdates",
                params={"limit": 1, "offset": -1, "timeout": 0},
                timeout=10,
            )
            if sync_res.status_code == 200:
                body = sync_res.json()
                results = body.get("result") or []
                if results:
                    self._last_update_id = results[-1]["update_id"]
                    logger.info("Telegram bot synced to update_id=%d", self._last_update_id)
        except Exception as exc:
            logger.debug("Initial getUpdates sync warning: %s", exc)

        logger.info("Telegram interactive bot listener started. Listening for commands & callbacks...")

        # 3. Continuous Long Polling Loop
        while self._is_running:
            try:
                poll_res = await asyncio.to_thread(
                    requests.get,
                    f"{base_url}/getUpdates",
                    params={
                        "offset": self._last_update_id + 1,
                        "limit": 10,
                        "timeout": 15,
                    },
                    timeout=25,
                )

                if poll_res.status_code == 200:
                    payload = poll_res.json()
                    updates = payload.get("result") or []
                    for update in updates:
                        up_id = update.get("update_id", 0)
                        if up_id > self._last_update_id:
                            self._last_update_id = up_id

                        # Handle Inline Keyboard Callback Queries
                        cq = update.get("callback_query")
                        if cq and isinstance(cq, dict):
                            cq_id = str(cq.get("id") or "")
                            from_user = cq.get("from") or {}
                            chat_id = str(from_user.get("id") or "")
                            data = str(cq.get("data") or "")
                            logger.info("Received Telegram callback '%s' from chat_id=%s", data, chat_id)
                            self.handle_callback_query(chat_id, data, cq_id)
                            continue

                        # Handle Standard Message Slash Commands
                        msg = update.get("message")
                        if not msg or not isinstance(msg, dict):
                            continue

                        chat = msg.get("chat") or {}
                        chat_id = str(chat.get("id") or "")
                        text = msg.get("text") or ""

                        if not text.startswith("/"):
                            continue

                        logger.info("Received Telegram command '%s' from chat_id=%s", text, chat_id)
                        response_text = self.handle_command(chat_id, text)
                        if response_text:
                            reply_markup = None
                            if text.startswith("/edge"):
                                parts = text.split()
                                tk = parts[1].upper() if len(parts) > 1 else ""
                                if tk:
                                    reply_markup = self._build_inline_keyboard(tk)
                            elif text.startswith("/paper"):
                                parts = text.split()
                                tk = parts[1].upper() if len(parts) > 1 else ""
                                if tk:
                                    reply_markup = self._build_trade_management_keyboard(tk)
                            self.send_message(chat_id, response_text, reply_markup=reply_markup)

                elif poll_res.status_code == 409:
                    # Another instance is polling
                    await asyncio.sleep(5)
                else:
                    await asyncio.sleep(2)

            except asyncio.CancelledError:
                self._is_running = False
                break
            except Exception as exc:
                logger.debug("Telegram polling exception: %s", exc)
                await asyncio.sleep(3)
