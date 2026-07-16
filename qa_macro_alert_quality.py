import sys

from src.email_alert_service import EmailAlertService
from src.morning_brief_service import MorningBriefService


def service() -> EmailAlertService:
    instance = EmailAlertService.__new__(EmailAlertService)
    instance.portfolio_manager = None
    return instance


def main() -> int:
    svc = service()

    brief_service = MorningBriefService.__new__(MorningBriefService)
    for event_type in (
        "conflict",
        "central_bank",
        "energy",
        "election",
        "disaster",
        "policy",
        "public_figure",
        "ipo",
        "product_catalyst",
        "congress_trade",
    ):
        guidance = brief_service._event_action_hint(event_type, "high")
        for field in ("why_now", "trigger", "invalidation", "execution_window"):
            if not str(guidance.get(field) or "").strip():
                print(f"FAIL {event_type} has no {field}")
                return 1
        combined = " ".join(str(guidance[field]) for field in ("why_now", "trigger", "invalidation"))
        if any(raw in combined for raw in ("Only ", "Invalid ", "Stand down", "Wait for ", "Ignore if ")):
            print(f"FAIL {event_type} still exposes English decision guidance: {combined}")
            return 1

    for event_type in ("Conflict", "Energy", "Central Bank", "Election", "Policy", "Public Figure", "IPO", "Disaster"):
        if not svc._default_macro_trigger(event_type) or not svc._default_macro_invalidation(event_type):
            print(f"FAIL {event_type} has incomplete Telegram defaults")
            return 1

    cached_brief = {
        "event_layer": [
            {
                "event_type": "public_figure",
                "impact": "high",
                "event_intelligence": {
                    "why_now": "Old English context.",
                    "trigger": "Old English trigger.",
                    "invalidation": "Old English invalidation.",
                },
            }
        ],
        "event_pings": [
            {
                "type": "public_figure",
                "severity": "critical",
                "trade_impact": {
                    "baseline_scenario": "Old English context.",
                    "trigger": "Old English trigger.",
                    "invalidation": "Old English invalidation.",
                },
            }
        ],
    }
    refreshed_brief = brief_service._refresh_cached_event_guidance(cached_brief)
    refreshed_intelligence = refreshed_brief["event_layer"][0]["event_intelligence"]
    refreshed_impact = refreshed_brief["event_pings"][0]["trade_impact"]
    if "Aussagen wichtiger Personen" not in refreshed_intelligence.get("why_now", ""):
        print(f"FAIL cached event guidance was not refreshed: {refreshed_intelligence}")
        return 1
    if "vertrauenswürdigen Quelle" not in refreshed_impact.get("trigger", ""):
        print(f"FAIL cached ping guidance was not refreshed: {refreshed_impact}")
        return 1
    if cached_brief["event_layer"][0]["event_intelligence"]["why_now"] != "Old English context.":
        print("FAIL cache refresh mutated the stored source payload")
        return 1

    weak_event = {
        "title": "Oil rumour hits tape",
        "summary": "Unconfirmed social flow mentions possible supply disruption.",
        "event_type": "energy",
        "region": "Middle East",
        "source_status": "social rumour",
        "impact_score": 94,
        "symbols": ["XLE", "USO"],
    }
    if svc._normalize_macro_alert_event(weak_event, 82) is not None:
        print("FAIL weak rumour event passed the macro alert gate")
        return 1

    thin_event = {
        "title": "Confirmed attack near energy corridor",
        "summary": "Confirmed report, but no explicit trigger or invalidation is available yet.",
        "event_type": "conflict",
        "country": "Middle East",
        "source_status": "official confirmed",
        "impact_score": 91,
        "symbols": ["XLE", "USO", "GLD"],
    }
    if svc._normalize_macro_alert_event(thin_event, 82) is not None:
        print("FAIL event without explicit decision context passed the macro alert gate")
        return 1

    strong_event = {
        "title": "Official escalation near Red Sea shipping corridor",
        "summary": "Confirmed escalation can affect oil, shipping, insurance and European risk appetite into the next liquid session.",
        "event_type": "conflict",
        "country": "Middle East",
        "source_status": "official confirmed wire",
        "impact_score": 93,
        "symbols": ["XLE", "USO", "GLD", "DAX"],
        "trigger": "Brent and energy equities hold the move for 30 minutes after the European open.",
        "invalidation": "Ignore if official follow-up denies supply risk and crude reverses below the pre-headline level.",
    }
    normalized = svc._normalize_macro_alert_event(strong_event, 82)
    if not normalized:
        print("FAIL strong confirmed event did not pass the macro alert gate")
        return 1
    rendered = svc._render_telegram_macro_alert(normalized)
    required = [
        "Sicherheit:",
        "Faktenstatus:",
        "Quellenqualitaet:",
        "Zeithorizont:",
        "Warum wichtig:",
        "Was es aussagt:",
        "Marktmechanismus:",
        "Basisszenario (bedingt):",
        "Read-through:",
        "Kritischer Check:",
        "Als Naechstes pruefen:",
        "Trigger:",
        "Invalidierung:",
    ]
    missing = [part for part in required if part not in rendered]
    if missing:
        print(f"FAIL rendered alert missing sections: {missing}")
        return 1
    if normalized.get("fact_status") != "bestaetigt" or not normalized.get("horizon"):
        print(f"FAIL normalized alert missing classification: {normalized}")
        return 1
    if "Krieg / Konflikt" not in rendered or "beobachten und bestaetigen" not in rendered:
        print(f"FAIL rendered alert still exposes raw event/action labels: {rendered}")
        return 1

    weak_person = {
        "title": "Trump comments circulate on social media",
        "summary": "Unconfirmed posts claim a market-moving statement may be coming.",
        "publisher": "social rumour",
        "impact_score": 96,
    }
    if svc._normalize_macro_alert_event(weak_person, 82) is not None:
        print("FAIL weak public-figure rumour passed the macro alert gate")
        return 1

    strong_person = {
        "title": "Trump says new China tariff plan is under review",
        "summary": "A confirmed policy statement can affect China-exposed equities, industrials, retailers, inflation expectations and broad index risk.",
        "publisher": "Reuters",
        "impact_score": 91,
        "symbols": ["SPY", "DAX", "CNH", "XLI"],
    }
    normalized_person = svc._normalize_macro_alert_event(strong_person, 82)
    if not normalized_person or normalized_person.get("event_type") != "Public Figure":
        print("FAIL strong public-figure statement did not pass as Public Figure alert")
        return 1
    person_rendered = svc._render_telegram_macro_alert(normalized_person)
    if "voller Wortlaut" not in person_rendered or "Statement-Read-through" not in person_rendered:
        print(f"FAIL public-figure alert missing critical statement context: {person_rendered}")
        return 1

    strong_ipo = {
        "title": "AI infrastructure startup files for IPO after revenue doubles",
        "summary": "A confirmed IPO filing can reset peer valuation, risk appetite and capital-market demand across AI infrastructure and small-cap growth.",
        "publisher": "Bloomberg",
        "impact_score": 90,
        "symbols": ["QQQ", "IWM", "IPO", "AI"],
    }
    normalized_ipo = svc._normalize_macro_alert_event(strong_ipo, 82)
    if not normalized_ipo or normalized_ipo.get("event_type") != "IPO":
        print("FAIL strong IPO filing did not pass as IPO alert")
        return 1
    ipo_rendered = svc._render_telegram_macro_alert(normalized_ipo)
    if "Filing/Pricing" not in ipo_rendered or "Kapitalmarkt-Read-through" not in ipo_rendered:
        print(f"FAIL IPO alert missing critical IPO context: {ipo_rendered}")
        return 1

    print("Macro alert quality smoke passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
