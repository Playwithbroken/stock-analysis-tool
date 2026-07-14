from __future__ import annotations

import os
import tempfile
from datetime import datetime as RealDateTime
from zoneinfo import ZoneInfo


class FixedDateTime(RealDateTime):
    @classmethod
    def now(cls, tz=None):
        fixed = RealDateTime(2026, 7, 13, 8, 35, tzinfo=ZoneInfo("Europe/Berlin"))
        return fixed.astimezone(tz) if tz is not None else fixed.replace(tzinfo=None)


class FakePublicSignalService:
    def build_watchlist_snapshot(self, items):
        return {"items": [], "ticker_signals": []}


class FakeMorningBriefService:
    def get_brief_fast(self, snapshot=None, force_refresh=False):
        return {
            "generated_at": "2026-07-13T08:35:00+02:00",
            "headline": "QA Morning Brief",
            "opening_bias": "Selective",
            "regions": {"europe": {"assets": [{"ticker": "DAX"}]}},
            "trade_setups": [],
            "quality": {"status": "ready", "score": 85},
        }

    def _is_usable_brief(self, brief):
        return bool(brief and brief.get("headline"))

    def get_trading_edge(self, snapshot=None):
        return {"status": "qa"}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "brief-scheduler-delivery.db")
        os.environ["SCHEDULED_BRIEFS_ENABLED"] = "true"
        os.environ["TELEGRAM_ALERTS_ENABLED"] = "true"
        os.environ["TELEGRAM_BOT_TOKEN"] = ""
        os.environ["TELEGRAM_CHAT_ID"] = "qa-chat-placeholder"
        os.environ["BRIEF_SCHEDULE_TIMEZONE"] = "Europe/Berlin"
        os.environ["BRIEF_SCHEDULE_WEEKDAYS"] = "mon"
        os.environ["MORNING_BRIEF_TIME"] = "08:30"
        os.environ["EUROPE_OPEN_BRIEF_TIME"] = "09:00"
        os.environ["MIDDAY_BRIEF_TIME"] = "12:30"
        os.environ["US_OPEN_BRIEF_TIME"] = "15:10"
        os.environ["EUROPE_CLOSE_BRIEF_TIME"] = "17:30"
        os.environ["CLOSE_RECAP_TIME"] = "21:45"
        os.environ["US_CLOSE_BRIEF_TIME"] = "22:15"

        import src.email_alert_service as alert_module
        from src.email_alert_service import EmailAlertService
        from src.storage import PortfolioManager

        original_datetime = alert_module.datetime
        alert_module.datetime = FixedDateTime
        manager = PortfolioManager()
        service = EmailAlertService(
            manager,
            FakePublicSignalService(),
            morning_brief_service=FakeMorningBriefService(),
        )
        telegram_deliveries: list[str] = []
        preflight_attempts = {"count": 0}
        send_attempts = {"count": 0}

        def legacy_builder_must_not_run(*args, **kwargs):
            raise RuntimeError("legacy event builder must not block rich briefs")

        service._build_open_brief_events = legacy_builder_must_not_run
        def flaky_preflight(config):
            preflight_attempts["count"] += 1
            if preflight_attempts["count"] == 1:
                raise RuntimeError("qa telegram preflight outage")

        def flaky_rich_brief(config, brief, session):
            send_attempts["count"] += 1
            if send_attempts["count"] == 1:
                raise RuntimeError("qa telegram send outage")
            telegram_deliveries.append(session)

        service._telegram_preflight = flaky_preflight
        service._send_telegram_rich_brief = flaky_rich_brief

        failures: list[str] = []
        try:
            missing_config = service.send_scheduled_open_briefs()
            missing_status = service.get_brief_job_status("morning-brief")
            missing_sent_keys = manager.get_sent_signal_event_keys()
            os.environ["TELEGRAM_BOT_TOKEN"] = "qa-token-placeholder"
            preflight_failure = service.send_scheduled_open_briefs()
            preflight_status = service.get_brief_job_status("morning-brief")
            preflight_sent_keys = manager.get_sent_signal_event_keys()
            send_failure = service.send_scheduled_open_briefs()
            send_failure_status = service.get_brief_job_status("morning-brief")
            send_failure_sent_keys = manager.get_sent_signal_event_keys()
            first = service.send_scheduled_open_briefs()
            second = service.send_scheduled_open_briefs()
        finally:
            alert_module.datetime = original_datetime
            service._brief_executor.shutdown(wait=False, cancel_futures=True)

        failed = [row for row in missing_config if row.get("status") == "failed"]
        if len(failed) != 1 or "config_failed" not in str(failed[0].get("error")):
            failures.append(f"missing Telegram config was not recorded cleanly: {missing_config}")
        if missing_status.get("status") != "failed" or not missing_status.get("last_error"):
            failures.append(f"missing config diagnostics absent: {missing_status}")
        if "morning-brief:2026-07-13" in missing_sent_keys:
            failures.append("failed configuration was incorrectly marked as sent")

        preflight_failed = [row for row in preflight_failure if row.get("status") == "failed"]
        if len(preflight_failed) != 1 or "qa telegram preflight outage" not in str(preflight_failed[0].get("error")):
            failures.append(f"preflight failure was not recorded cleanly: {preflight_failure}")
        if preflight_status.get("status") != "failed" or "qa telegram preflight outage" not in str(preflight_status.get("last_error")):
            failures.append(f"preflight diagnostics absent: {preflight_status}")
        if "morning-brief:2026-07-13" in preflight_sent_keys:
            failures.append("preflight failure was incorrectly marked as sent")

        send_failed = [row for row in send_failure if row.get("status") == "failed"]
        if len(send_failed) != 1 or "qa telegram send outage" not in str(send_failed[0].get("error")):
            failures.append(f"send failure was not recorded cleanly: {send_failure}")
        if send_failure_status.get("status") != "failed" or "qa telegram send outage" not in str(send_failure_status.get("last_error")):
            failures.append(f"send failure diagnostics absent: {send_failure_status}")
        if "morning-brief:2026-07-13" in send_failure_sent_keys:
            failures.append("send failure was incorrectly marked as sent")

        sent = [row for row in first if row.get("status") == "sent"]
        if len(sent) != 1 or sent[0].get("job") != "morning-brief":
            failures.append(f"expected one sent morning brief, got {first}")
        if telegram_deliveries != ["global"]:
            failures.append(f"expected one Telegram rich brief, got {telegram_deliveries}")
        if preflight_attempts["count"] != 3:
            failures.append(f"expected three preflight attempts before success, got {preflight_attempts['count']}")
        if send_attempts["count"] != 2:
            failures.append(f"expected two send attempts before success, got {send_attempts['count']}")
        if not second or second[0].get("status") != "idle":
            failures.append(f"second scheduler run was not deduped: {second}")

        event_key = "morning-brief:2026-07-13"
        if event_key not in manager.get_sent_signal_event_keys():
            failures.append("successful job was not persisted for daily dedupe")
        status = service.get_brief_job_status("morning-brief")
        if status.get("status") != "sent" or not status.get("last_success_at"):
            failures.append(f"job status missing success diagnostics: {status}")

        if failures:
            print("\nBrief scheduler delivery failures:")
            for failure in failures:
                print(f"- {failure}")
            return 1

    print("Brief scheduler delivery and dedupe QA passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
