"""QA test suite for Dividend Snowball & Freedom Calculator."""

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def test_dividend_forecast():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_ENV"] = "production"
        os.environ["APP_COOKIE_SECURE"] = "false"
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "divforecast-test.db")
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
        res_404 = client.post("/api/portfolio/missing-id/dividend-forecast", json={})
        assert res_404.status_code == 404

        # 3. Create portfolio
        create_res = client.post("/api/portfolios", json={"name": "Dividend Snowball Depot"})
        assert create_res.status_code == 200
        p_id = create_res.json()["id"]

        # 4. Test empty portfolio
        res_empty = client.post(f"/api/portfolio/{p_id}/dividend-forecast", json={})
        assert res_empty.status_code == 200
        data_empty = res_empty.json()
        assert data_empty["timeline"] == []
        assert data_empty["summary"]["end_portfolio_value"] == 0.0

        # 5. Add holdings: JNJ (30 shares @ 150) and O (100 shares @ 55)
        client.post(f"/api/portfolios/{p_id}/holdings", json={"ticker": "JNJ", "shares": 30, "buyPrice": 150.0})
        client.post(f"/api/portfolios/{p_id}/holdings", json={"ticker": "O", "shares": 100, "buyPrice": 55.0})

        # Pre-populate DataFetcher cache with realistic dividend rates
        now = datetime.now()
        DataFetcher._global_cache["info_JNJ"] = ({
            "currentPrice": 160.0,
            "shortName": "Johnson & Johnson",
        }, now)
        DataFetcher._global_cache["info_O"] = ({
            "currentPrice": 55.0,
            "shortName": "Realty Income",
        }, now)

        # Mock DataFetcher.get_dividends
        def mock_get_dividends(self):
            ticker = getattr(self, "ticker", "")
            if ticker == "JNJ":
                return {"dividend_rate": 4.80, "dividend_yield": 3.0}
            elif ticker == "O":
                return {"dividend_rate": 3.12, "dividend_yield": 5.6}
            return {"dividend_rate": 0.0, "dividend_yield": 0.0}

        with patch.object(DataFetcher, "get_dividends", mock_get_dividends):
            # 6. Run 10-year projection with DRIP & 250 €/mo savings
            res_drip = client.post(
                f"/api/portfolio/{p_id}/dividend-forecast",
                json={
                    "years": 10,
                    "monthly_contribution": 250.0,
                    "reinvest_dividends": True,
                    "dividend_growth_rate": 6.0,
                    "capital_growth_rate": 4.0,
                    "tax_allowance": 1000.0,
                },
            )
            assert res_drip.status_code == 200
            data_drip = res_drip.json()

            # Verify initial status:
            # JNJ: 30 * 160 = 4800, div = 30 * 4.80 = 144
            # O: 100 * 55 = 5500, div = 100 * 3.12 = 312
            # Total value = 10300, Total annual div = 456
            init = data_drip["initial_status"]
            assert init["initial_value"] == 10300.0
            assert init["initial_annual_gross_dividend"] == 456.0
            # 456 < 1000 allowance, so 0 taxes now
            assert init["taxes_paid_now"] == 0.0
            assert init["allowance_used_pct"] == 45.6

            # Timeline must have 10 years
            assert len(data_drip["timeline"]) == 10
            y1 = data_drip["timeline"][0]
            y10 = data_drip["timeline"][9]
            # Compounding: Year 10 portfolio value & dividends must be substantially higher than Year 1
            assert y10["portfolio_value"] > y1["portfolio_value"]
            assert y10["gross_dividend_yearly"] > y1["gross_dividend_yearly"]
            assert y10["total_contributed"] == 10300.0 + (10 * 12 * 250.0)

            # Milestones check
            assert len(data_drip["milestones"]) == 6
            streaming = next(m for m in data_drip["milestones"] if m["id"] == "streaming")
            assert streaming["target_monthly"] == 25.0
            assert streaming["current_monthly_net"] == 38.0  # 456 / 12 = 38
            assert streaming["is_reached_now"] is True  # 38 > 25

            # 7. Compare with NO DRIP (Cash payout mode)
            res_no_drip = client.post(
                f"/api/portfolio/{p_id}/dividend-forecast",
                json={
                    "years": 10,
                    "monthly_contribution": 250.0,
                    "reinvest_dividends": False,
                    "dividend_growth_rate": 6.0,
                    "capital_growth_rate": 4.0,
                    "tax_allowance": 1000.0,
                },
            )
            assert res_no_drip.status_code == 200
            data_no_drip = res_no_drip.json()
            # With DRIP, end portfolio value and dividends must be higher than without DRIP
            assert data_drip["summary"]["end_portfolio_value"] > data_no_drip["summary"]["end_portfolio_value"]
            assert data_drip["summary"]["end_annual_gross_dividend"] > data_no_drip["summary"]["end_annual_gross_dividend"]
            print("DRIP Compounding Effect: PASSED")

            # 8. Tax Allowance Comparison: 1000 € vs 2000 €
            res_single = client.post(
                f"/api/portfolio/{p_id}/dividend-forecast",
                json={"years": 20, "monthly_contribution": 500.0, "tax_allowance": 1000.0},
            )
            res_married = client.post(
                f"/api/portfolio/{p_id}/dividend-forecast",
                json={"years": 20, "monthly_contribution": 500.0, "tax_allowance": 2000.0},
            )
            assert res_single.status_code == 200 and res_married.status_code == 200
            single_tax = res_single.json()["summary"]["total_taxes_paid"]
            married_tax = res_married.json()["summary"]["total_taxes_paid"]
            assert married_tax < single_tax
            assert res_married.json()["summary"]["total_taxes_saved"] > res_single.json()["summary"]["total_taxes_saved"]
            print("Sparerpauschbetrag Tax Optimization: PASSED")

            # 9. Plural Route Alias Test
            res_alias = client.post(
                f"/api/portfolios/{p_id}/dividend-forecast",
                json={"years": 5},
            )
            assert res_alias.status_code == 200
            assert len(res_alias.json()["timeline"]) == 5
            print("Route aliases: PASSED")

    print("ALL DIVIDEND FORECAST QA TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    test_dividend_forecast()
