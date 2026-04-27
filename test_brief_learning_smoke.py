import unittest

from src.email_alert_service import EmailAlertConfig, EmailAlertService
from src.forecast_learning_service import ForecastLearningService


class _DummyPortfolioManager:
    def __init__(self) -> None:
        self.settings: dict[str, str] = {}

    def get_app_setting(self, key: str, default: str = "") -> str:
        return self.settings.get(key, default)

    def set_app_setting(self, key: str, value: str) -> None:
        self.settings[key] = value


class _DummyPublicSignalService:
    pass


class _CapturingAlertService(EmailAlertService):
    def __init__(self) -> None:
        self.dummy_portfolio_manager = _DummyPortfolioManager()
        super().__init__(self.dummy_portfolio_manager, _DummyPublicSignalService())
        self.telegram_messages: list[str] = []

    def _tg_post(self, token: str, chat_id: str, text: str, disable_preview: bool = True) -> None:
        self.telegram_messages.append(text)


def _telegram_config() -> EmailAlertConfig:
    return EmailAlertConfig(
        enabled=True,
        smtp_host="",
        smtp_port=587,
        smtp_user="",
        smtp_password="",
        smtp_from="",
        smtp_to="",
        smtp_starttls=True,
        telegram_enabled=True,
        telegram_bot_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        telegram_chat_id="8419486873",
        scheduled_briefs_enabled=True,
    )


class BriefLearningSmokeTest(unittest.TestCase):
    def test_telegram_brief_renders_learning_bias(self) -> None:
        service = _CapturingAlertService()
        brief = {
            "generated_at": "2026-04-27T08:30:00",
            "macro_regime": "mixed",
            "opening_bias": "Selective open, confirmation needed.",
            "regions": {},
            "macro_assets": [],
            "top_news": [],
            "trade_setups": [
                {
                    "rank": 1,
                    "symbol": "NVDA",
                    "confidence": 78,
                    "thesis": "NVDA needs follow-through, not just the headline.",
                    "trigger": "Hold above first impulse with volume.",
                    "invalidation": "Fails if the impulse fully reverses.",
                    "expected_move": "1.5-3.0%",
                    "decision_quality": "selective",
                    "size_guidance": "small risk",
                    "window": "open+60m",
                    "learning_adjustment": {
                        "score_delta": 5.0,
                        "reason": "Recent outcomes support a higher ranking.",
                        "source_hit_rate": 72.0,
                        "setup_hit_rate": 68.0,
                    },
                }
            ],
            "action_board": [],
            "portfolio_brain": {},
            "contrarian_signals": [],
            "trading_edge": {},
        }

        service._send_telegram_rich_brief(_telegram_config(), brief, "global")

        rendered = "\n\n".join(service.telegram_messages)
        self.assertIn("Highest Conviction Setups", rendered)
        self.assertIn("Learning applied", rendered)
        self.assertIn("NVDA", rendered)
        self.assertIn("learning +5.0", rendered)
        self.assertIn("source 72.0%", rendered)

    def test_congress_watch_is_collected_as_forecast_setup(self) -> None:
        service = ForecastLearningService(_DummyPortfolioManager())
        setups = service._collect_forecast_setups(
            {
                "trade_setups": [
                    {
                        "symbol": "AAPL",
                        "setup_type": "single_name",
                        "trigger": "Confirm above VWAP.",
                    }
                ],
                "congress_watch": [
                    {
                        "ticker": "MSFT",
                        "action": "buy",
                        "confidence": 74,
                        "thesis": "PTR cluster supports watchlist priority.",
                    }
                ],
            },
            limit=8,
        )

        self.assertEqual([item["symbol"] for item in setups], ["AAPL", "MSFT"])
        congress = setups[1]
        self.assertEqual(congress["setup_type"], "congress_watch")
        self.assertEqual(congress["direction"], "long")
        self.assertEqual(congress["setup_source"], "congress_watch")
        self.assertIn("congress_signal", congress)

    def test_brief_status_tracks_missed_and_clears_after_sent(self) -> None:
        service = _CapturingAlertService()
        service._set_brief_job_status(
            "morning-brief",
            {
                "status": "missed",
                "message": "Brief missed its delivery grace window.",
                "scheduled_at": "2026-04-27T08:30:00+02:00",
            },
        )

        missed = service.get_brief_job_status("morning-brief")
        self.assertEqual(missed["status"], "missed")
        self.assertEqual(missed["last_error"], "Brief missed its delivery grace window.")

        service._set_brief_job_status(
            "morning-brief",
            {
                "status": "sent",
                "sent_at": "2026-04-27T08:35:00+02:00",
                "scheduled_at": "2026-04-27T08:30:00+02:00",
            },
        )

        sent = service.get_brief_job_status("morning-brief")
        self.assertEqual(sent["status"], "sent")
        self.assertEqual(sent["last_success_at"], "2026-04-27T08:35:00+02:00")
        self.assertIsNone(sent["last_error"])


if __name__ == "__main__":
    unittest.main()
