"""QA test suite for Portfolio Earnings & Event Radar."""

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def test_earnings_radar():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_ENV"] = "production"
        os.environ["APP_COOKIE_SECURE"] = "false"
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "earningsradar-test.db")
        os.environ["APP_ACCESS_PASSWORD"] = "test-pass"
        os.environ["APP_SESSION_SECRET"] = "x" * 64

        from fastapi.testclient import TestClient
        import api
        from src.data_fetcher import DataFetcher

        client = TestClient(api.app)

        # 1. Login
        login_res = client.post("/api/auth/login", json={"password": "test-pass"})
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"

        # 2. Test 404
        res_404 = client.get("/api/portfolio/missing-id/earnings-radar")
        assert res_404.status_code == 404

        # 3. Create test portfolio
        create_res = client.post("/api/portfolios", json={"name": "Earnings Radar Portfolio"})
        assert create_res.status_code == 200
        p_id = create_res.json()["id"]

        # 4. Test empty portfolio
        res_empty = client.get(f"/api/portfolio/{p_id}/earnings-radar")
        assert res_empty.status_code == 200
        data_empty = res_empty.json()
        assert data_empty["upcoming_events"] == []
        assert data_empty["summary"]["total_holdings"] == 0

        # 5. Add 3 holdings: AAPL (urgent: 3 days), MSFT (upcoming: 25 days), NVDA (upcoming: 45 days)
        client.post(f"/api/portfolios/{p_id}/holdings", json={"ticker": "AAPL", "shares": 10, "buyPrice": 180.0})
        client.post(f"/api/portfolios/{p_id}/holdings", json={"ticker": "MSFT", "shares": 5, "buyPrice": 400.0})
        client.post(f"/api/portfolios/{p_id}/holdings", json={"ticker": "NVDA", "shares": 20, "buyPrice": 120.0})

        now = datetime.now()
        DataFetcher._global_cache["info_AAPL"] = ({"currentPrice": 185.0, "shortName": "Apple Inc."}, now)
        DataFetcher._global_cache["info_MSFT"] = ({"currentPrice": 420.0, "shortName": "Microsoft Corp."}, now)
        DataFetcher._global_cache["info_NVDA"] = ({"currentPrice": 125.0, "shortName": "NVIDIA Corp."}, now)

        def mock_get_upcoming_earnings(self):
            ticker = getattr(self, "ticker", "")
            if ticker == "AAPL":
                return {"date": "2026-09-17", "timing": "After Market Close (AMC)", "days_until": 3, "eps_estimate": 1.62}
            elif ticker == "MSFT":
                return {"date": "2026-10-09", "timing": "Before Market Open (BMO)", "days_until": 25, "eps_estimate": 3.10}
            elif ticker == "NVDA":
                return {"date": "2026-10-29", "timing": "After Market Close (AMC)", "days_until": 45, "eps_estimate": 0.75}
            return None

        def mock_get_earnings_history(self):
            ticker = getattr(self, "ticker", "")
            if ticker == "AAPL":
                # 3 beats, 1 miss -> 75% beat rate
                return [
                    {"period": "2026-06-30", "status": "beat", "eps_surprise_pct": 5.2, "reported_eps": 1.40, "eps_estimate": 1.33},
                    {"period": "2026-03-31", "status": "beat", "eps_surprise_pct": 3.8, "reported_eps": 1.53, "eps_estimate": 1.47},
                    {"period": "2025-12-31", "status": "miss", "eps_surprise_pct": -2.1, "reported_eps": 2.18, "eps_estimate": 2.23},
                    {"period": "2025-09-30", "status": "beat", "eps_surprise_pct": 4.0, "reported_eps": 1.46, "eps_estimate": 1.40},
                ]
            elif ticker == "MSFT":
                # 4 beats -> 100% beat rate
                return [
                    {"period": "2026-06-30", "status": "beat", "eps_surprise_pct": 4.1, "reported_eps": 2.95, "eps_estimate": 2.83},
                    {"period": "2026-03-31", "status": "beat", "eps_surprise_pct": 6.2, "reported_eps": 2.94, "eps_estimate": 2.77},
                    {"period": "2025-12-31", "status": "beat", "eps_surprise_pct": 2.8, "reported_eps": 2.93, "eps_estimate": 2.85},
                    {"period": "2025-09-30", "status": "beat", "eps_surprise_pct": 5.0, "reported_eps": 2.99, "eps_estimate": 2.85},
                ]
            return []

        with patch.object(DataFetcher, "get_upcoming_earnings", mock_get_upcoming_earnings):
            with patch.object(DataFetcher, "get_earnings_history", mock_get_earnings_history):
                # 6. Test Radar Endpoint
                res_radar = client.get(f"/api/portfolio/{p_id}/earnings-radar")
                assert res_radar.status_code == 200
                data_radar = res_radar.json()

                # Verify upcoming events
                upcoming = data_radar["upcoming_events"]
                assert len(upcoming) == 3
                # Sorted ascending by days_until: AAPL (3) -> MSFT (25) -> NVDA (45)
                assert upcoming[0]["ticker"] == "AAPL"
                assert upcoming[0]["days_until"] == 3
                assert upcoming[1]["ticker"] == "MSFT"
                assert upcoming[2]["ticker"] == "NVDA"

                # Verify urgent events (days <= 7)
                urgent = data_radar["urgent_events"]
                assert len(urgent) == 1
                assert urgent[0]["ticker"] == "AAPL"
                assert urgent[0]["is_urgent"] is True

                # Verify Beat Rates
                track = {t["ticker"]: t for t in data_radar["track_records"]}
                assert track["AAPL"]["beat_rate_pct"] == 75.0
                assert track["AAPL"]["beat_count"] == 3
                assert track["AAPL"]["miss_count"] == 1
                assert track["MSFT"]["beat_rate_pct"] == 100.0
                print("Earnings Radar Timeline & Beat Rates: PASSED")

                # 7. Test ICS Calendar Export
                res_ics = client.get(f"/api/portfolio/{p_id}/earnings/export/ics")
                assert res_ics.status_code == 200
                assert "text/calendar" in res_ics.headers.get("Content-Type", "")
                ics_text = res_ics.text
                assert "BEGIN:VCALENDAR" in ics_text
                assert "END:VCALENDAR" in ics_text
                assert "SUMMARY:📊 AAPL Quartalszahlen" in ics_text
                assert "SUMMARY:📊 MSFT Quartalszahlen" in ics_text
                assert "BEGIN:VALARM" in ics_text  # 24h reminder
                print("ICS Calendar Export: PASSED")

                # 8. Test Route Aliases
                res_alias = client.get(f"/api/portfolios/{p_id}/earnings-radar")
                assert res_alias.status_code == 200
                assert len(res_alias.json()["upcoming_events"]) == 3
                print("Route aliases: PASSED")

    print("ALL PORTFOLIO EARNINGS RADAR QA TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    test_earnings_radar()
