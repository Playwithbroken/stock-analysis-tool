import sys

from src.email_alert_service import EmailAlertService


def service() -> EmailAlertService:
    instance = EmailAlertService.__new__(EmailAlertService)
    instance.portfolio_manager = None
    return instance


def main() -> int:
    svc = service()

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
    required = ["Sicherheit:", "Warum wichtig:", "Was es aussagt:", "Kritischer Check:", "Trigger:", "Invalidierung:"]
    missing = [part for part in required if part not in rendered]
    if missing:
        print(f"FAIL rendered alert missing sections: {missing}")
        return 1

    print("Macro alert quality smoke passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
