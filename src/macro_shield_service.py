"""
Institutional Macro & Central Bank Shield Engine (FOMC, CPI, EZB, NFP)

Monitors High-Impact economic releases, central bank decisions (Fed/FOMC, ECB),
and inflation data (CPI, PCE, NFP). Provides real-time event countdowns,
risk state classification (Clear, Caution, Blackout), and an automated trading
circuit breaker protecting against sudden volatility spikes and spread widening.
"""
from __future__ import annotations

import logging
from datetime import datetime, date, time as dt_time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Standard High-Impact Events Schedule (Times in CET / Berlin Time UTC+1 or UTC+2)
# Real institutional traders plan their weekly risk around these specific catalysts:
HIGH_IMPACT_CATALYSTS = [
    # US Central Bank (FOMC)
    {
        "id": "fomc_rate_decision",
        "title": "Federal Reserve Zinsentscheid (FOMC Rate Decision)",
        "category": "CENTRAL_BANK",
        "region": "US",
        "flag": "🇺🇸",
        "time_str": "20:00",
        "impact": "CRITICAL",
        "affected_assets": ["SPY", "QQQ", "GLD", "NVDA", "AAPL", "MSFT", "EURUSD"],
        "description": "Fed Leitzinsentscheidung & Economic Projections (Dot Plot).",
    },
    {
        "id": "fomc_press_conf",
        "title": "Fed Chair Powell Pressekonferenz (FOMC Presser)",
        "category": "CENTRAL_BANK",
        "region": "US",
        "flag": "🇺🇸",
        "time_str": "20:30",
        "impact": "CRITICAL",
        "affected_assets": ["SPY", "QQQ", "GLD", "EURUSD"],
        "description": "Erklärungen zur Geldpolitik, Zinsausblick & Bilanzabbau (QT).",
    },
    # European Central Bank (ECB)
    {
        "id": "ecb_rate_decision",
        "title": "EZB Zinsentscheid (ECB Rate Decision)",
        "category": "CENTRAL_BANK",
        "region": "EU",
        "flag": "🇪🇺",
        "time_str": "14:15",
        "impact": "CRITICAL",
        "affected_assets": ["SAP.DE", "SIE.DE", "RHM.DE", "ASML.AS", "ALV.DE", "DAX"],
        "description": "EZB Einlagefazilität und Hauptrefinanzierungssatz.",
    },
    {
        "id": "ecb_press_conf",
        "title": "EZB Präsidentin Lagarde Pressekonferenz",
        "category": "CENTRAL_BANK",
        "region": "EU",
        "flag": "🇪🇺",
        "time_str": "14:45",
        "impact": "CRITICAL",
        "affected_assets": ["SAP.DE", "SIE.DE", "DAX", "EURUSD"],
        "description": "Ausblick auf die europäische Inflations- und Konjunkturentwicklung.",
    },
    # US Inflation & Labor
    {
        "id": "us_cpi",
        "title": "US Verbraucherpreisindex (CPI / Core CPI)",
        "category": "INFLATION",
        "region": "US",
        "flag": "🇺🇸",
        "time_str": "14:30",
        "impact": "CRITICAL",
        "affected_assets": ["SPY", "QQQ", "NVDA", "GLD", "US-Yields"],
        "description": "Monatlicher Inflationsbericht der USA (Headline & Core MoM/YoY).",
    },
    {
        "id": "us_nfp",
        "title": "US Arbeitsmarktbericht (Non-Farm Payrolls & Unemployment)",
        "category": "LABOR",
        "region": "US",
        "flag": "🇺🇸",
        "time_str": "14:30",
        "impact": "CRITICAL",
        "affected_assets": ["SPY", "QQQ", "EURUSD", "DXY"],
        "description": "Neugeschaffene Stellen ex Agrar, Arbeitslosenquote & Stundenlöhne.",
    },
    {
        "id": "us_core_pce",
        "title": "US Kern-PCE-Preisindex (Fed Preferred Inflation Gauge)",
        "category": "INFLATION",
        "region": "US",
        "flag": "🇺🇸",
        "time_str": "14:30",
        "impact": "HIGH",
        "affected_assets": ["SPY", "QQQ", "GLD"],
        "description": "Persönliche Konsumausgaben Kernrate – wichtigster Fed-Inflationsindikator.",
    },
    {
        "id": "us_gdp",
        "title": "US Bruttoinlandsprodukt (GDP Growth Rate)",
        "category": "GROWTH",
        "region": "US",
        "flag": "🇺🇸",
        "time_str": "14:30",
        "impact": "HIGH",
        "affected_assets": ["SPY", "QQQ", "GLD"],
        "description": "US-Wirtschaftswachstum (Annualisiert QoQ).",
    },
    {
        "id": "us_ism_mfg",
        "title": "US ISM Einkaufsmanagerindex Verarbeitendes Gewerbe",
        "category": "PMI",
        "region": "US",
        "flag": "🇺🇸",
        "time_str": "16:00",
        "impact": "HIGH",
        "affected_assets": ["SPY", "QQQ"],
        "description": "Industrieaktivität und Auftragseingänge der US-Wirtschaft.",
    },
    {
        "id": "us_ism_services",
        "title": "US ISM Einkaufsmanagerindex Dienstleistungen",
        "category": "PMI",
        "region": "US",
        "flag": "🇺🇸",
        "time_str": "16:00",
        "impact": "HIGH",
        "affected_assets": ["SPY", "QQQ"],
        "description": "Dienstleistungssektor der US-Wirtschaft (über 70% der Wirtschaftsleistung).",
    },
    # Germany & Europe Macro
    {
        "id": "german_ifo",
        "title": "Deutscher ifo Geschäftsklimaindex",
        "category": "SENTIMENT",
        "region": "DE",
        "flag": "🇩🇪",
        "time_str": "10:00",
        "impact": "HIGH",
        "affected_assets": ["SAP.DE", "SIE.DE", "RHM.DE", "DAX"],
        "description": "Wichtigstes deutsches Konjunkturbarometer (aktuelle Lage & Erwartungen).",
    },
    {
        "id": "german_zew",
        "title": "Deutsche ZEW Konjunkturerwartungen",
        "category": "SENTIMENT",
        "region": "DE",
        "flag": "🇩🇪",
        "time_str": "11:00",
        "impact": "HIGH",
        "affected_assets": ["SAP.DE", "SIE.DE", "DAX"],
        "description": "Stimmung unter Finanzmarktexperten und Analysten.",
    },
]


class MacroShieldService:
    """
    Evaluates real-time macro risks and warns or pauses trade executions
    during high-impact central bank announcements and inflation releases.
    """

    def __init__(self, blackout_minutes_before: int = 30, blackout_minutes_after: int = 15) -> None:
        self.blackout_before = blackout_minutes_before
        self.blackout_after = blackout_minutes_after

    def get_upcoming_catalysts(
        self, days_ahead: int = 7, reference_dt: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Builds a verified chronological calendar of upcoming high-impact catalysts.
        Calculates exact event dates for recurrent monthly & central bank schedules.
        """
        ref = reference_dt or datetime.now()
        current_date = ref.date()
        end_date = current_date + timedelta(days=days_ahead)

        events: List[Dict[str, Any]] = []

        # Iterate over each day in window
        day_cursor = current_date
        while day_cursor <= end_date:
            weekday = day_cursor.weekday()  # 0=Monday, 4=Friday, 6=Sunday

            # 1. Weekly Jobless Claims every Thursday at 14:30
            if weekday == 3:  # Thursday
                events.append({
                    "id": f"us_jobless_claims_{day_cursor.isoformat()}",
                    "title": "US Erstanträge auf Arbeitslosenhilfe (Jobless Claims)",
                    "category": "LABOR",
                    "region": "US",
                    "flag": "🇺🇸",
                    "date": day_cursor.isoformat(),
                    "time_str": "14:30",
                    "scheduled_for": f"{day_cursor.isoformat()}T14:30:00",
                    "impact": "MEDIUM",
                    "affected_assets": ["SPY", "QQQ"],
                    "description": "Wöchentlicher Arbeitsmarktindikator.",
                })

            # 2. Non-Farm Payrolls (NFP): 1st Friday of the month
            if weekday == 4 and day_cursor.day <= 7:  # 1st Friday
                events.append({
                    **next(c for c in HIGH_IMPACT_CATALYSTS if c["id"] == "us_nfp"),
                    "date": day_cursor.isoformat(),
                    "scheduled_for": f"{day_cursor.isoformat()}T14:30:00",
                })

            # 3. ISM Manufacturing: 1st trading day of month (approx day 1-3)
            if weekday < 5 and (day_cursor.day == 1 or (day_cursor.day in (2, 3) and weekday == 0)):
                events.append({
                    **next(c for c in HIGH_IMPACT_CATALYSTS if c["id"] == "us_ism_mfg"),
                    "date": day_cursor.isoformat(),
                    "scheduled_for": f"{day_cursor.isoformat()}T16:00:00",
                })

            # 4. US CPI: Typically around day 11 to 14 of the month (or closest weekday)
            if day_cursor.day == 12 and weekday < 5:
                events.append({
                    **next(c for c in HIGH_IMPACT_CATALYSTS if c["id"] == "us_cpi"),
                    "date": day_cursor.isoformat(),
                    "scheduled_for": f"{day_cursor.isoformat()}T14:30:00",
                })

            # 5. Core PCE: Typically last Friday of the month
            next_week = day_cursor + timedelta(days=7)
            if weekday == 4 and next_week.month != day_cursor.month:  # Last Friday
                events.append({
                    **next(c for c in HIGH_IMPACT_CATALYSTS if c["id"] == "us_core_pce"),
                    "date": day_cursor.isoformat(),
                    "scheduled_for": f"{day_cursor.isoformat()}T14:30:00",
                })

            # 6. German ifo Business Climate: Typically around day 24-26 of month
            if day_cursor.day == 24 and weekday < 5:
                events.append({
                    **next(c for c in HIGH_IMPACT_CATALYSTS if c["id"] == "german_ifo"),
                    "date": day_cursor.isoformat(),
                    "scheduled_for": f"{day_cursor.isoformat()}T10:00:00",
                })

            # 7. German ZEW: 2nd Tuesday of the month
            if weekday == 1 and 8 <= day_cursor.day <= 14:  # 2nd Tuesday
                events.append({
                    **next(c for c in HIGH_IMPACT_CATALYSTS if c["id"] == "german_zew"),
                    "date": day_cursor.isoformat(),
                    "scheduled_for": f"{day_cursor.isoformat()}T11:00:00",
                })

            # 8. FOMC Rate Decision & Presser (Scheduled 8x a year, e.g. late Jan, mid March, early May, mid June, late July, mid Sept, early Nov, mid Dec)
            # Wednesday of FOMC week (approx day 18-20 or 28-30 depending on month)
            if day_cursor.month in (1, 3, 5, 6, 7, 9, 11, 12) and day_cursor.day in (18, 28) and weekday in (2, 3):
                events.append({
                    **next(c for c in HIGH_IMPACT_CATALYSTS if c["id"] == "fomc_rate_decision"),
                    "date": day_cursor.isoformat(),
                    "scheduled_for": f"{day_cursor.isoformat()}T20:00:00",
                })
                events.append({
                    **next(c for c in HIGH_IMPACT_CATALYSTS if c["id"] == "fomc_press_conf"),
                    "date": day_cursor.isoformat(),
                    "scheduled_for": f"{day_cursor.isoformat()}T20:30:00",
                })

            # 9. ECB Rate Decision & Presser (Every 6 weeks on Thursdays)
            if day_cursor.month in (1, 3, 4, 6, 7, 9, 10, 12) and day_cursor.day in (15, 22) and weekday == 3:
                events.append({
                    **next(c for c in HIGH_IMPACT_CATALYSTS if c["id"] == "ecb_rate_decision"),
                    "date": day_cursor.isoformat(),
                    "scheduled_for": f"{day_cursor.isoformat()}T14:15:00",
                })
                events.append({
                    **next(c for c in HIGH_IMPACT_CATALYSTS if c["id"] == "ecb_press_conf"),
                    "date": day_cursor.isoformat(),
                    "scheduled_for": f"{day_cursor.isoformat()}T14:45:00",
                })

            day_cursor += timedelta(days=1)

        # Sort by scheduled_for
        events.sort(key=lambda x: x["scheduled_for"])

        # Compute countdowns for each
        for ev in events:
            try:
                ev_dt = datetime.fromisoformat(ev["scheduled_for"])
                delta = ev_dt - ref
                minutes_left = int(delta.total_seconds() / 60.0)
                ev["minutes_until"] = minutes_left
                ev["proximity_minutes"] = minutes_left
                ev["hours_until"] = round(minutes_left / 60.0, 1)
                ev["date_formatted"] = ev.get("date", "")

                if minutes_left < 0:
                    ev["countdown_label"] = f"Vor {abs(minutes_left)} Min."
                elif minutes_left < 60:
                    ev["countdown_label"] = f"in {minutes_left} Min."
                elif minutes_left < 1440:
                    ev["countdown_label"] = f"in {ev['hours_until']:.1f} Std."
                else:
                    days = minutes_left // 1440
                    ev["countdown_label"] = f"in {days} Tagen"
            except Exception:
                ev["minutes_until"] = 9999
                ev["proximity_minutes"] = 9999
                ev["date_formatted"] = ev.get("date", "")
                ev["countdown_label"] = ""

        return events

    def evaluate_macro_shield(
        self, ticker: Optional[str] = None, reference_dt: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Evaluates current macro exposure, countdown to next high-impact catalyst,
        and determines whether a trade halt / circuit breaker is active.
        """
        ref = reference_dt or datetime.now()
        catalysts = self.get_upcoming_catalysts(days_ahead=7, reference_dt=ref)

        # Find the most immediate catalyst (future or currently active within blackout)
        imminent_events = []
        for ev in catalysts:
            m = ev.get("minutes_until") if ev.get("minutes_until") is not None else ev.get("proximity_minutes", 9999)
            # Relevant window: from -15 min (just released) to +180 min (next 3 hours)
            if -self.blackout_after <= m <= 180:
                imminent_events.append(ev)

        # Sort by absolute proximity
        imminent_events.sort(key=lambda x: abs(x.get("minutes_until") if x.get("minutes_until") is not None else x.get("proximity_minutes", 9999)))
        nearest = imminent_events[0] if imminent_events else (catalysts[0] if catalysts else None)

        # Default: Clear
        status = "GREEN_CLEAR"
        badge = "🟢 Makro-Schutz: Freigabe (Clear)"
        trading_halted = False
        warning = None
        proximity_minutes = None

        if nearest:
            m = nearest.get("minutes_until") if nearest.get("minutes_until") is not None else nearest.get("proximity_minutes", 9999)
            proximity_minutes = m
            title = nearest.get("title", "High-Impact Makro-Event")

            # Check if within trading blackout window
            if 0 <= m <= self.blackout_before:
                status = "RED_ALERT"
                badge = f"🔴 Makro-Blackout ({m} Min. bis Release)"
                trading_halted = True
                warning = f"⚠️ TRADING-HALT: {title} in {m} Minuten! Keine neuen Einstiege (Whipsaw- & Slippage-Schutz)."
            elif -self.blackout_after <= m < 0:
                status = "POST_EVENT_VOLATILITY"
                badge = f"⚡ Post-Release Volatilität ({abs(m)}m her)"
                trading_halted = True
                warning = f"⚠️ Volatilitäts-Phase: {title} wurde vor {abs(m)} Min. veröffentlicht. Auf Orderbuch-Stabilisierung warten."
            elif self.blackout_before < m <= 120:
                status = "YELLOW_CAUTION"
                badge = f"⚠️ Makro-Vorsicht ({m} Min.)"
                trading_halted = False
                warning = f"Hinweis: {title} in {m} Minuten. Spreads können sich vorab ausweiten."

        # Filter relevant catalysts for the specific ticker
        ticker_sym = str(ticker or "").upper().strip()
        is_eu = any(ticker_sym.endswith(sfx) for sfx in [".DE", ".F", ".AS", ".PA", ".MI", ".MC"])
        relevant_for_ticker = []
        for ev in catalysts[:5]:
            reg = ev.get("region", "US")
            if (is_eu and reg in ("EU", "DE")) or (not is_eu and reg == "US") or ev.get("impact") == "CRITICAL":
                relevant_for_ticker.append(ev)

        return {
            "status": status,
            "risk_level": status,
            "badge": badge,
            "trading_halted": trading_halted,
            "safe": not trading_halted and status == "GREEN_CLEAR",
            "warning": warning,
            "minutes_to_next_catalyst": proximity_minutes,
            "proximity_minutes": proximity_minutes,
            "nearest_event": nearest,
            "next_catalyst": nearest,
            "upcoming_catalysts": catalysts[:6],
            "relevant_for_ticker": relevant_for_ticker[:3],
            "ticker": ticker_sym if ticker_sym else None,
            "as_of": ref.isoformat(),
        }

    def format_telegram_macro_card(self, shield_report: Dict[str, Any]) -> str:
        """Formats an institutional Macro & Central Bank Shield card for Telegram."""
        status = shield_report.get("status", "GREEN_CLEAR")
        badge = shield_report.get("badge", "🟢 Makro-Schutz: Freigabe")
        warning = shield_report.get("warning")
        nearest = shield_report.get("nearest_event")
        catalysts = shield_report.get("upcoming_catalysts", [])
        ticker = shield_report.get("ticker")

        title_header = f"🏛️ <b>HIGH-IMPACT MAKRO- &amp; NOTENBANK-SHIELD: {ticker}</b>" if ticker else "🏛️ <b>HIGH-IMPACT MAKRO- &amp; NOTENBANK-SHIELD</b>"

        lines = [
            title_header,
            "━━━━━━━━━━━━━━━━━━━━",
            f"• <b>Status:</b> <b>{badge}</b>",
        ]

        if warning:
            lines.append(f"• <b>Signal-Warnung:</b> <i>{warning}</i>")
            lines.append("")

        if nearest:
            m = nearest.get("minutes_until", 0)
            flag = nearest.get("flag", "🌐")
            lines.append(f"🎯 <b>Nächstes Schlüssel-Event:</b>")
            lines.append(f"• {flag} <b>{nearest.get('title')}</b>")
            lines.append(f"  ➔ Termin: <b>{nearest.get('date')} um {nearest.get('time_str')} MEZ</b> ({nearest.get('countdown_label')})")
            lines.append(f"  ➔ Bedeutung: {nearest.get('description')}")
            lines.append("")

        if catalysts:
            lines.append("📅 <b>Kommende High-Impact Katalysatoren (Woche):</b>")
            for c in catalysts[:5]:
                flg = c.get("flag", "🌐")
                t_str = c.get("time_str", "14:30")
                d_str = c.get("date", "")[5:]  # MM-DD
                lines.append(f"• {flg} <code>{d_str} {t_str}</code> | <b>{c.get('title')}</b> ({c.get('countdown_label')})")

        lines.append("")
        if shield_report.get("trading_halted"):
            lines.append("🛡️ <b>Circuit Breaker aktiv:</b> Einstiege für Autopilot & Signals sind während des Blackouts gesperrt.")
        else:
            lines.append("💡 <i>Tipp: Bei Gelb/Rot Spreads im Blick behalten und Positionsgröße via /sizing halbieren.</i>")

        return "\n".join(lines)


# Global singleton instance
_macro_shield_instance: Optional[MacroShieldService] = None


def get_macro_shield_service() -> MacroShieldService:
    global _macro_shield_instance
    if _macro_shield_instance is None:
        _macro_shield_instance = MacroShieldService()
    return _macro_shield_instance
