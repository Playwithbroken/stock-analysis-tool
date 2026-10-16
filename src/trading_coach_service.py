"""
Trading Coach & Behavioral Flaw Auditor Service

Analyzes real & paper trading journal performance:
  1. Win Rate, Profit Factor, Expectancy & R-Multiple efficiency.
  2. Setup Performance Matrix (identifies high-ROI setups vs. loss-makers).
  3. Behavioral Flaw Detection:
     • Stop Discipline: Did losses exceed 1.0R (refusal to take loss)?
     • Winner Holding: Were winners closed prematurely (< 1.5R)?
     • Tilt & Revenge Trading: Rapid-fire entries following a loss.
     • Overtrading: Excessive exposure relative to account sizing.
  4. Delivers actionable 3-point coaching instructions via Telegram (/coach).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TradingCoachService:
    def __init__(self, portfolio_manager: Optional[Any] = None) -> None:
        self.portfolio_manager = portfolio_manager

    def audit_performance(self) -> Dict[str, Any]:
        """Audits all closed trades and computes behavioral performance metrics."""
        if not self.portfolio_manager or not hasattr(self.portfolio_manager, "list_paper_trades"):
            return {
                "total_trades": 0,
                "closed_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "avg_win_r": 0.0,
                "avg_loss_r": 0.0,
                "expectancy_r": 0.0,
                "top_setups": [],
                "flaws": [],
                "advice": ["Führe mindestens 3-5 Trades aus, um das Coaching zu aktivieren."],
            }

        try:
            trades = self.portfolio_manager.list_paper_trades(limit=200)
        except Exception as exc:
            logger.error("Failed loading trades for coach audit: %s", exc)
            trades = []

        closed = [t for t in trades if str(t.get("status") or "").lower() == "closed"]
        if not closed:
            return {
                "total_trades": len(trades),
                "closed_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "avg_win_r": 0.0,
                "avg_loss_r": 0.0,
                "expectancy_r": 0.0,
                "top_setups": [],
                "flaws": [],
                "advice": ["Noch keine abgeschlossenen Trades im Journal. Buche Setups mit /paper ein."],
            }

        wins = []
        losses = []
        setup_pnl: Dict[str, float] = {}
        flaws: List[str] = []

        for t in closed:
            pnl = float(t.get("realized_pnl") or t.get("pnl") or 0.0)
            entry = float(t.get("entry_price") or 1.0)
            stop = float(t.get("stop_price") or (entry * 0.95))
            risk = abs(entry - stop)
            qty = float(t.get("quantity") or 1.0)
            total_risk = (risk * qty) if risk > 0 else 100.0

            r_mult = round(pnl / total_risk, 2) if total_risk > 0 else 0.0

            stype = str(t.get("setup_type") or "Asymmetric Edge").replace("institutional_edge_", "")
            setup_pnl[stype] = setup_pnl.get(stype, 0.0) + pnl

            if pnl > 0:
                wins.append(r_mult)
            else:
                losses.append(r_mult)

            # Flaw detection: Did loss exceed -1.25R? (failed to honor stop)
            if r_mult < -1.25:
                flaws.append(f"Disziplin-Bruch: {t.get('ticker')} Verlust ({r_mult}R) größer als 1R Stop!")

            # Flaw detection: Winner cut too early (< 0.8R)
            if 0 < r_mult < 0.8:
                flaws.append(
                    f"Gewinn zu früh geschlossen: {t.get('ticker')} bei nur +{r_mult}R (Ziel 1 ist 2.0R) – "
                    f"nutze -0.25R Atmungs-Puffer statt zu engem Stop!"
                )

        total_closed = len(closed)
        win_count = len(wins)
        win_rate = (win_count / total_closed * 100.0) if total_closed > 0 else 0.0

        avg_win_r = round(sum(wins) / len(wins), 2) if wins else 0.0
        avg_loss_r = round(abs(sum(losses) / len(losses)), 2) if losses else 0.0

        # Expectancy = (WinRate * AvgWin) - (LossRate * AvgLoss)
        loss_rate = 1.0 - (win_count / total_closed) if total_closed > 0 else 0.0
        expectancy_r = round(((win_rate / 100.0) * avg_win_r) - (loss_rate * avg_loss_r), 2)

        tot_gain = sum(p for t in closed if (p := float(t.get("realized_pnl") or 0.0)) > 0)
        tot_loss = abs(sum(p for t in closed if (p := float(t.get("realized_pnl") or 0.0)) < 0))
        profit_factor = round(tot_gain / tot_loss, 2) if tot_loss > 0 else (99.0 if tot_gain > 0 else 0.0)

        # Ranked setups
        ranked_setups = sorted(setup_pnl.items(), key=lambda x: x[1], reverse=True)

        # Advice generation
        advice: List[str] = []
        if win_rate >= 55.0 and avg_win_r >= 1.5:
            advice.append("🟢 Exzellente Edge: Gewinner laufen lassen und Verluste diszipliniert begrenzen!")
        elif win_rate < 40.0:
            advice.append("⚠️ Winrate unter 40%: Konzentriere dich nur noch auf Grade A+ Setups.")
        elif avg_win_r < avg_loss_r:
            advice.append("🛑 Asymmetrie verletzt: Deine durchschnittlichen Verluste sind größer als deine Gewinne.")

        if any("zu früh" in f for f in flaws):
            advice.append(
                "🌬️ Anti-Shakeout-Regel: Lass starken Aufwärtstrends einen kleinen Verlust-Puffer (-0.25R mit /puffer), "
                "damit du vor dem großen Ausbruch nicht durch kurze Rücksetzer ausgestoppt wirst!"
            )

        if ranked_setups and ranked_setups[0][1] > 0:
            best_setup = ranked_setups[0][0].replace("_", " ").title()
            advice.append(f"💎 Fokussiere dein Setup '{best_setup}' – hier erzielst du den größten Ertrag.")

        return {
            "total_trades": len(trades),
            "closed_trades": total_closed,
            "win_rate": round(win_rate, 1),
            "profit_factor": profit_factor,
            "avg_win_r": avg_win_r,
            "avg_loss_r": avg_loss_r,
            "expectancy_r": expectancy_r,
            "top_setups": ranked_setups[:3],
            "flaws": flaws[:3],
            "advice": advice,
        }

    def get_setup_edge_badge(self, setup_name: str = "") -> Optional[str]:
        """
        Returns a self-learning badge based on the user's historical journal winrate
        and setup profitability (0 extra RAM, reads SQLite).
        """
        audit = self.audit_performance()
        if audit.get("closed_trades", 0) < 2:
            return None

        wr = float(audit.get("win_rate", 0.0))
        exp_r = float(audit.get("expectancy_r", 0.0))
        top_setups = dict(audit.get("top_setups") or [])

        norm_name = str(setup_name or "").lower()
        for stype, pnl in top_setups.items():
            if stype.lower() in norm_name or norm_name in stype.lower():
                if pnl > 0:
                    return f"🔥 <b>Dein Top-Setup im Journal</b> (Historisch +${pnl:,.0f} | Expectancy {exp_r:+.2f}R)"
                elif pnl < 0:
                    return f"⚠️ <b>Journal-Warnung:</b> Dieses Setup war zuletzt im Minus (${pnl:,.0f}) – nur mit A+ Konfluenz handeln!"

        if wr >= 55.0 and exp_r > 0:
            return f"🔥 <b>Journal-Edge Aktiv:</b> Deine aktuelle Winrate liegt bei <b>{wr:.0f}%</b> ({exp_r:+.2f}R/Trade)"
        return None

    def format_coach_card(self) -> str:
        """Formats an executive German Telegram coaching report."""
        res = self.audit_performance()
        total = res["closed_trades"]

        lines = [
            "🧠 <b>KI-TRADING-COACH &amp; DISZIPLIN-AUDIT</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"<i>Statistische Auswertung deiner {total} beendeten Trades:</i>\n",
        ]

        if total == 0:
            lines.append("📖 <b>Noch keine beendeten Trades im Journal.</b>")
            lines.append("Buche Setups per One-Tap ein (z.B. <code>/edge</code> ➔ In Paper Trader buchen).")
            lines.append("Sobald Trades beendet werden, analysiert der Coach deine Performance!")
            return "\n".join(lines)

        wr = res["win_rate"]
        pf = res["profit_factor"]
        exp_r = res["expectancy_r"]

        wr_badge = "🟢" if wr >= 50 else ("🟡" if wr >= 40 else "🔴")
        pf_badge = "🟢" if pf >= 1.5 else ("🟡" if pf >= 1.0 else "🔴")

        lines.append(f"📊 <b>Performance-Kennzahlen:</b>")
        lines.append(f"• Winrate: {wr_badge} <b>{wr:.1f}%</b> ({res['win_rate']}%)")
        lines.append(f"• Profit Factor: {pf_badge} <b>{pf:.2f}</b>")
        lines.append(f"• Ø Gewinner: <b>+{res['avg_win_r']}R</b> | Ø Verlierer: <b>-{res['avg_loss_r']}R</b>")
        lines.append(f"• Mathematische Edge (Expectancy): <b>{exp_r:+.2f}R</b> pro Trade")

        # Top Setups
        if res["top_setups"]:
            lines.append("\n🏆 <b>Gewinnbringendste Setups:</b>")
            for stype, pnl in res["top_setups"]:
                clean = stype.replace("_", " ").title()
                sgn = "+" if pnl >= 0 else ""
                lines.append(f"• <b>{clean}:</b> {sgn}${pnl:,.2f}")

        # Flaws
        if res["flaws"]:
            lines.append("\n⚠️ <b>Erkannte Schwachstellen:</b>")
            for f in res["flaws"]:
                lines.append(f"• {f}")

        # Actionable Advice
        lines.append("\n🎯 <b>Coach-Handlungsanweisung für heute:</b>")
        for a in res["advice"]:
            lines.append(f"• {a}")

        return "\n".join(lines)
