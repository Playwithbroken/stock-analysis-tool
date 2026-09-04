"""
Telegram Interactive Service — 2-Way Conversational Edge Trading Bot

Enables the user to control Broker Freund directly from their smartphone via Telegram:
  • /help /start: Overview of commands
  • /edge [ticker]: Top Grade A+/A asymmetric setups or on-demand ticker analysis
  • /gex <ticker>: Market Maker Gamma Exposure, Call/Put Walls & Volatility Regime
  • /levels <ticker>: Volume Profile (POC, VAH, VAL) & Value Area Acceptance
  • /regime: Macro Market Regime (SPY, QQQ, VIX & Stance)
  • /rs: Relative Strength leaders vs SPY (Mansfield RS / Alpha)
  • /track /trades: Live active setups & Trailing-Stop monitor
  • /scan: Trigger immediate watchlist scan

Security: Only messages originating from the configured TELEGRAM_CHAT_ID are processed.
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
        trading_signals_service: Optional[Any] = None,
        alert_service: Optional[Any] = None,
        portfolio_manager: Optional[Any] = None,
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
        self.signals_service = trading_signals_service
        self.alert_service = alert_service
        self.portfolio_manager = portfolio_manager

        self._last_update_id: int = 0
        self._is_running: bool = False

    def is_authorized(self, chat_id: Any) -> bool:
        """Verifies that the chat_id matches configured authorized chats."""
        if not self.allowed_chat_ids:
            return False
        return str(chat_id).strip() in self.allowed_chat_ids

    def send_message(self, chat_id: str, text: str, disable_preview: bool = True) -> bool:
        """Sends an HTML formatted message back to the user via Telegram."""
        if not self.bot_token:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text[:4096],
            "parse_mode": "HTML",
            "disable_web_page_preview": disable_preview,
        }
        try:
            res = requests.post(url, json=payload, timeout=15)
            if res.status_code == 400:
                # Fallback to plain text if HTML tags were unclosed/malformed
                plain = html.unescape(text)
                # Strip basic tags
                import re
                plain = re.sub(r"<[^>]*>", "", plain)[:4096]
                payload["text"] = plain
                payload.pop("parse_mode", None)
                res = requests.post(url, json=payload, timeout=15)
            res.raise_for_status()
            return True
        except Exception as exc:
            logger.error("Failed to send Telegram message to %s: %s", chat_id, exc)
            return False

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

        cmd = parts[0].lower().split("@")[0]  # strip bot username if present, e.g. /edge@MyBot
        args = parts[1:]

        try:
            if cmd in ("/start", "/help"):
                return self._cmd_help()
            elif cmd == "/edge":
                return self._cmd_edge(args)
            elif cmd == "/gex":
                return self._cmd_gex(args)
            elif cmd == "/levels":
                return self._cmd_levels(args)
            elif cmd == "/regime":
                return self._cmd_regime()
            elif cmd == "/rs":
                return self._cmd_relative_strength()
            elif cmd in ("/track", "/trades"):
                return self._cmd_track()
            elif cmd == "/scan":
                return self._cmd_scan()
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
            "⚡ <b>Verfügbare Befehle:</b>\n"
            "• <code>/edge</code> – Top Grade A+/A Setups mit Entry, Stop & Zielen\n"
            "• <code>/edge TICKER</code> – Ad-hoc Setup für Aktie (z.B. <code>/edge NVDA</code>)\n"
            "• <code>/gex TICKER</code> – Gamma Exposure & Market Maker Regime (z.B. <code>/gex TSLA</code>)\n"
            "• <code>/levels TICKER</code> – Volume Profile (POC, VAH, VAL) (z.B. <code>/levels AAPL</code>)\n"
            "• <code>/regime</code> – SPY/QQQ Trend & VIX Risiko-Status\n"
            "• <code>/rs</code> – Relative Stärke vs. SPY (Mansfield RS Leaders)\n"
            "• <code>/track</code> – Aktive Setups & Trailing-Stops im Blick\n"
            "• <code>/scan</code> – Watchlist-Scan sofort manuell ausführen\n"
            "• <code>/help</code> – Diese Übersicht anzeigen\n\n"
            "💡 <i>Tipp: Tippe einfach auf einen blau hinterlegten Befehl oben zum Ausführen.</i>"
        )

    def _cmd_edge(self, args: List[str]) -> str:
        if not self.asymmetric_service:
            return "⚠️ Asymmetric Trade Service ist nicht geladen."

        # Case 1: Specific ticker requested, e.g. /edge NVDA
        if args:
            ticker = args[0].upper().strip()
            setup = self.asymmetric_service.generate_trade_setup(ticker)
            if not setup:
                return f"❌ Konnte kein Setup für <b>{ticker}</b> berechnen (Kursdaten unvollständig oder nicht handelbar)."

            # Automatically register for live tracking if Grade A or higher
            if self.lifecycle_service and setup.get("confluence_score", 0) >= 65:
                self.lifecycle_service.register_trade(setup)

            return setup.get("telegram_html") or f"Setup für {ticker} berechnet."

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

        # Register top setups in lifecycle tracker
        if self.lifecycle_service:
            for s in setups:
                self.lifecycle_service.register_trade(s)

        # Return the best setup in full detail, and summarize any others
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

        interpretation = (
            "Market Maker dämpfen Kursausschläge. Rücksetzer zur Put Wall und Rallyes "
            "zur Call Wall neigen zu Mean-Reversion."
            if regime == "positive_gamma" else
            "Market Maker verstärken Trends (Hedging treibt Volatilität). "
            "Ausbrüche können explosionsartig laufen!"
        )

        return (
            f"⚡ <b>GAMMA EXPOSURE (GEX): {ticker}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Spot-Kurs:</b> ${spot:.2f}\n"
            f"• <b>MM-Regime:</b> <b>{regime_label}</b>\n"
            f"• <b>Call Wall (Resistenz / Pin):</b> ${cw:.2f}\n"
            f"• <b>Put Wall (Support / Boden):</b> ${pw:.2f}\n"
            f"• <b>Zero Gamma (Vol-Schwelle):</b> ${zg:.2f}\n"
            f"• <b>Net GEX:</b> {net_gex:+,.0f} $\n\n"
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

        return (
            f"📊 <b>VOLUME PROFILE (AMT): {ticker}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Aktueller Kurs:</b> ${spot:.2f}\n"
            f"• <b>Point of Control (POC):</b> <b>${poc:.2f}</b> (Höchste Liquidität)\n"
            f"• <b>Value Area High (VAH):</b> ${vah:.2f} (Obere 70%-Grenze)\n"
            f"• <b>Value Area Low (VAL):</b> ${val:.2f} (Untere 70%-Grenze)\n"
            f"• <b>Ort im Profil:</b> {loc}\n\n"
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
        default_list = ["NVDA", "AAPL", "MSFT", "TSLA", "META", "AMZN", "GOOGL"]
        if not self.portfolio_manager:
            return default_list
        try:
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
        Runs continuously in background of api.py.
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

        logger.info("Telegram interactive bot listener started. Listening for commands...")

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
                        self.send_message(chat_id, response_text)

                elif poll_res.status_code == 409:
                    # Another instance is polling (e.g., during zero-downtime deploy reload)
                    await asyncio.sleep(5)
                else:
                    await asyncio.sleep(2)

            except asyncio.CancelledError:
                self._is_running = False
                break
            except Exception as exc:
                logger.debug("Telegram polling exception: %s", exc)
                await asyncio.sleep(3)
