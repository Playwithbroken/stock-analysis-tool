"""
Earnings Expected-Move & Implied Volatility (IV) Crush Calculator

Calculates the Wall Street market-maker implied move for upcoming corporate earnings:
  1. ATM Straddle Pricing: Expected Move ≈ 0.85 × (ATM Call + ATM Put).
  2. Implied Price Corridor (Upper & Lower Breakeven bounds).
  3. IV Crush Hazard Meter: Explains risk of option value destruction overnight.
  4. Institutional Execution Protocol: Pre-Earnings Avoidance vs. Post-Earnings ORB Momentum.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None  # type: ignore


class EarningsExpectedMoveService:
    def __init__(self) -> None:
        pass

    def calculate_expected_move(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Calculates expected move and IV crush hazard for a ticker."""
        if not yf:
            return None

        sym = str(symbol).strip().upper()
        if not sym:
            return None

        try:
            ticker = yf.Ticker(sym)
            fast = getattr(ticker, "fast_info", None)
            spot = 0.0
            if fast:
                spot = float(fast.get("lastPrice") or fast.get("regularMarketPreviousClose") or 0.0)

            hist = ticker.history(period="30d")
            if spot <= 0 and not hist.empty:
                spot = float(hist["Close"].iloc[-1])

            if spot <= 0:
                return None

            is_eu = any(sym.endswith(sfx) for sfx in [".DE", ".F", ".AS", ".PA", ".MI", ".MC"])
            c_sym = "€" if is_eu else ("£" if sym.endswith(".L") else "$")

            # Try reading next earnings date
            earnings_date_str = "Demnächst"
            try:
                cal = ticker.calendar
                if cal is not None:
                    if isinstance(cal, dict) and "Earnings Date" in cal:
                        ed = cal["Earnings Date"]
                        if isinstance(ed, list) and ed:
                            earnings_date_str = str(ed[0])[:10]
                        else:
                            earnings_date_str = str(ed)[:10]
                    elif hasattr(cal, "T") and "Earnings Date" in cal.T:
                        ed = cal.T["Earnings Date"].iloc[0]
                        earnings_date_str = str(ed)[:10]
            except Exception:
                pass

            # Options calculation if available
            exp_move = 0.0
            method = "implied_options"
            options_exp = None

            try:
                expirations = ticker.options
                if expirations:
                    options_exp = expirations[0]
                    chain = ticker.option_chain(options_exp)
                    calls = chain.calls
                    puts = chain.puts

                    if not calls.empty and not puts.empty:
                        # Find strike closest to spot
                        calls["strike_diff"] = (calls["strike"] - spot).abs()
                        puts["strike_diff"] = (puts["strike"] - spot).abs()

                        best_call = calls.sort_values("strike_diff").iloc[0]
                        best_put = puts.sort_values("strike_diff").iloc[0]

                        c_price = float(best_call.get("lastPrice") or ((best_call.get("bid", 0) + best_call.get("ask", 0)) / 2) or 0)
                        p_price = float(best_put.get("lastPrice") or ((best_put.get("bid", 0) + best_put.get("ask", 0)) / 2) or 0)

                        if c_price > 0 and p_price > 0:
                            # Standard rule of thumb: ~85% of straddle cost
                            exp_move = round((c_price + p_price) * 0.85, 2)
            except Exception as opt_err:
                logger.debug("Option chain retrieval fallback for %s: %s", sym, opt_err)

            # Fallback to ATR-derived statistical expected move if options absent
            if exp_move <= 0:
                method = "statistical_atr"
                if not hist.empty and len(hist) >= 14:
                    high_low = hist["High"] - hist["Low"]
                    atr = float(high_low.tail(14).mean())
                    exp_move = round(atr * 2.5, 2)
                else:
                    exp_move = round(spot * 0.065, 2)

            exp_move_pct = round((exp_move / spot) * 100.0, 2)
            upper_bound = round(spot + exp_move, 2)
            lower_bound = round(spot - exp_move, 2)

            # IV Crush Hazard Meter
            if exp_move_pct >= 7.5:
                hazard_badge = "🚨 EXTREM HOCH (> 7.5%)"
                hazard_desc = "Optionen sind massiv überteuert. Nackter Kauf birgt extremes Totalverlust-Risiko!"
            elif exp_move_pct >= 4.5:
                hazard_badge = "⚠️ HOCH (4.5% – 7.5%)"
                hazard_desc = "Erheblicher IV-Rückgang nach Veröffentlichung. Vorab-Hebel meiden."
            else:
                hazard_badge = "🟢 MODERAT (< 4.5%)"
                hazard_desc = "Typische Standard-Schwankung ohne exzessive Options-Prämie."

            return {
                "symbol": sym,
                "currency_symbol": c_sym,
                "spot_price": spot,
                "earnings_date": earnings_date_str,
                "expected_move": exp_move,
                "expected_move_pct": exp_move_pct,
                "upper_bound": upper_bound,
                "lower_bound": lower_bound,
                "hazard_badge": hazard_badge,
                "hazard_desc": hazard_desc,
                "method": method,
                "options_expiration": options_exp,
            }

        except Exception as exc:
            logger.error("Error calculating expected move for %s: %s", symbol, exc)
            return None

    def format_earnings_card(self, symbol: str) -> str:
        """Formats an executive German Telegram briefing for earnings volatility."""
        res = self.calculate_expected_move(symbol)
        if not res:
            return f"⚠️ Keine Earnings- oder Optionsdaten für <b>{symbol.upper()}</b> gefunden."

        c_sym = res["currency_symbol"]
        spot = res["spot_price"]
        em = res["expected_move"]
        em_pct = res["expected_move_pct"]
        up = res["upper_bound"]
        lo = res["lower_bound"]

        lines = [
            f"⚡ <b>EARNINGS EXPECTED-MOVE: {res['symbol']}</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"• <b>Aktueller Kurs:</b> {c_sym}{spot:.2f}",
            f"• <b>Nächste Quartalszahlen:</b> <b>{res['earnings_date']}</b>",
            f"• <b>Implizierte Schwankung (Expected Move):</b> <b>±{c_sym}{em:.2f} (±{em_pct:.1f}%)</b>\n",
            "📊 <b>Erwarteter Preiskorridor der Wall Street:</b>",
            f"  🟢 Oberes Ziel: <b>{c_sym}{up:.2f}</b> (+{em_pct:.1f}%)",
            f"  🔴 Unteres Ziel: <b>{c_sym}{lo:.2f}</b> (-{em_pct:.1f}%)\n",
            f"💥 <b>IV-Crush Risiko:</b> {res['hazard_badge']}",
            f"<i>{res['hazard_desc']}</i>\n",
            "🏛️ <b>Institutionelle Ausführungs-Regeln:</b>",
            "1. 🛑 <b>Vor den Zahlen:</b> Keine nackten Long-Calls/Puts über Nacht halten (Gefahr der IV-Implosion).",
            "2. 🎯 <b>Am Tag nach den Zahlen:</b> Warte die ersten 15-30 Minuten ab und handle den Ausbruch (ORB) in Trendrichtung der Zahlen!",
        ]

        return "\n".join(lines)
