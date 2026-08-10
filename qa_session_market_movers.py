from types import SimpleNamespace
from unittest.mock import patch
from datetime import datetime, timezone

import pandas as pd

from src.email_alert_service import EmailAlertService
from src.morning_brief_service import MorningBriefService


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def batch_frame():
    columns = pd.MultiIndex.from_tuples(
        [(ticker, "Close") for ticker in ("WIN1", "WIN2", "LOSE1", "LOSE2")]
    )
    return pd.DataFrame(
        [[100.0, 100.0, 100.0, 100.0], [110.0, 105.0, 98.0, 92.0]],
        columns=columns,
    )


def test_batch_movers_are_deterministic_daily_rankings():
    service = MorningBriefService.__new__(MorningBriefService)
    service._market_movers_cache = None
    service.MARKET_MOVER_UNIVERSE = ["WIN1", "WIN2", "LOSE1", "LOSE2"]
    with patch("src.morning_brief_service.yf.download", return_value=batch_frame()) as download:
        movers = service.collect_market_movers_for_delivery([])
    require(download.call_args.kwargs.get("period") == "7d", "batch scan did not request daily history")
    require([row["ticker"] for row in movers["gainers"]] == ["WIN1", "WIN2"], "gainers not sorted")
    require([row["ticker"] for row in movers["losers"]] == ["LOSE2", "LOSE1"], "losers not sorted")
    require(round(movers["gainers"][0]["change_1d"], 2) == 10.0, "winner move is not 1-day return")
    require(round(movers["losers"][0]["change_1d"], 2) == -8.0, "loser move is not 1-day return")

    service._market_movers_cache = (
        {"gainers": [{"ticker": "STALE", "change_1d": None, "change_1w": 99.0}], "losers": []},
        datetime.now(timezone.utc),
    )
    with patch("src.morning_brief_service.yf.download", return_value=batch_frame()) as refreshed:
        service.collect_market_movers_for_delivery([])
    require(refreshed.called, "weekly-only cache was incorrectly reused for a daily mover ranking")


class MoverProvider:
    MARKET_MOVER_UNIVERSE = ["WIN1", "WIN2", "LOSE1", "LOSE2"]

    def __init__(self, fail=False):
        self.fail = fail

    def collect_market_movers_for_delivery(self, tickers):
        if self.fail:
            raise RuntimeError("provider down")
        return {
            "gainers": [{"ticker": "WIN1", "name": "Winner One", "price": 110.0, "change_1d": 10.0}],
            "losers": [{"ticker": "LOSE2", "name": "Loser Two", "price": 92.0, "change_1d": -8.0}],
        }


def telegram_service(fail=False):
    service = EmailAlertService.__new__(EmailAlertService)
    service.morning_brief_service = MoverProvider(fail=fail)
    service._run_with_timeout = lambda label, fn, timeout: fn()
    service.messages = []
    service._tg_post = lambda token, chat, message, disable_preview=True: service.messages.append(message)
    return service


def render_brief(service, brief):
    service._send_telegram_rich_brief(
        SimpleNamespace(
            telegram_enabled=True,
            telegram_bot_token="token",
            telegram_chat_id="chat",
        ),
        {
            "macro_regime": "mixed",
            "opening_bias": "neutral",
            "regions": {},
            "macro_assets": [],
            **brief,
        },
        "midday",
    )
    return "\n".join(service.messages)


def test_delivery_attachment_and_honest_rendering():
    service = telegram_service()
    enriched = service._attach_delivery_market_movers({}, {"items": [{"kind": "ticker", "value": "AAPL"}]})
    require((enriched.get("market_movers_meta") or {}).get("status") == "ready", "mover attach failed")
    rendered = render_brief(service, enriched)
    for marker in ("Biggest Winners / Losers", "1-Tages-Bewegung", "WIN1", "+10.00%", "LOSE2", "-8.00%"):
        require(marker in rendered, f"Telegram movers missing {marker}")

    failed = telegram_service(fail=True)
    unavailable = failed._attach_delivery_market_movers({}, {"items": []})
    require((unavailable.get("market_movers_meta") or {}).get("status") == "unavailable", "failure not disclosed")
    rendered_failure = render_brief(failed, unavailable)
    require("keine Ersatzwerte ausgegeben" in rendered_failure, "Telegram silently hid unavailable movers")


def main():
    tests = [
        test_batch_movers_are_deterministic_daily_rankings,
        test_delivery_attachment_and_honest_rendering,
    ]
    for test in tests:
        test()
    print(f"Session market movers QA passed ({len(tests)} test groups).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
