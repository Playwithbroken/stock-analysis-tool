"""QA test suite for Portfolio Stress-Test & Crisis Simulator."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def mock_get_info(self):
    ticker = getattr(self, "ticker", "")
    data = {
        "AAPL": {"currentPrice": 180.0, "sector": "Technology", "beta": 1.25, "shortName": "Apple Inc."},
        "JNJ": {"currentPrice": 150.0, "sector": "Healthcare", "beta": 0.55, "shortName": "Johnson & Johnson"},
        "XOM": {"currentPrice": 110.0, "sector": "Energy", "beta": 0.85, "shortName": "Exxon Mobil"},
        "JPM": {"currentPrice": 200.0, "sector": "Financial Services", "beta": 1.15, "shortName": "JPMorgan Chase"},
    }
    return data.get(ticker, {"currentPrice": 100.0, "sector": "Diversified", "beta": 1.0, "shortName": ticker})


def test_portfolio_stress_test():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_ENV"] = "production"
        os.environ["APP_COOKIE_SECURE"] = "false"
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "stresstest-test.db")
        os.environ["APP_ACCESS_PASSWORD"] = "test-pass"
        os.environ["APP_SESSION_SECRET"] = "x" * 64

        from fastapi.testclient import TestClient
        import api
        from src.data_fetcher import DataFetcher

        client = TestClient(api.app)

        # 1. Login
        login_res = client.post("/api/auth/login", json={"password": "test-pass"})
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"

        # 2. Test 404 on missing portfolio
        res_404 = client.post("/api/portfolio/missing-id/stress-test", json={"scenario": "covid_crash_2020"})
        assert res_404.status_code == 404

        # 3. Create portfolio
        create_res = client.post("/api/portfolios", json={"name": "Stress Test Portfolio"})
        assert create_res.status_code == 200
        p_id = create_res.json()["id"]

        # 4. Empty portfolio test
        res_empty = client.post(f"/api/portfolio/{p_id}/stress-test", json={"scenario": "financial_crisis_2008"})
        assert res_empty.status_code == 200
        data_empty = res_empty.json()
        assert data_empty["summary"]["initial_value"] == 0.0
        assert data_empty["summary"]["loss_eur"] == 0.0

        # 5. Add 4 diversified holdings
        client.post(f"/api/portfolios/{p_id}/holdings", json={"ticker": "AAPL", "shares": 10, "buyPrice": 170.0})
        client.post(f"/api/portfolios/{p_id}/holdings", json={"ticker": "JNJ", "shares": 10, "buyPrice": 140.0})
        client.post(f"/api/portfolios/{p_id}/holdings", json={"ticker": "XOM", "shares": 10, "buyPrice": 100.0})
        client.post(f"/api/portfolios/{p_id}/holdings", json={"ticker": "JPM", "shares": 10, "buyPrice": 190.0})

        from datetime import datetime
        now = datetime.now()
        for t, d in [
            ("AAPL", {"currentPrice": 180.0, "sector": "Technology", "beta": 1.25, "shortName": "Apple Inc."}),
            ("JNJ", {"currentPrice": 150.0, "sector": "Healthcare", "beta": 0.55, "shortName": "Johnson & Johnson"}),
            ("XOM", {"currentPrice": 110.0, "sector": "Energy", "beta": 0.85, "shortName": "Exxon Mobil"}),
            ("JPM", {"currentPrice": 200.0, "sector": "Financial Services", "beta": 1.15, "shortName": "JPMorgan Chase"}),
        ]:
            DataFetcher._global_cache[f"info_{t}"] = (d, now)

        # 6. Test 2008 Financial Crisis Scenario
        res_2008 = client.post(
            f"/api/portfolio/{p_id}/stress-test",
            json={"scenario": "financial_crisis_2008"},
        )
        assert res_2008.status_code == 200
        data_2008 = res_2008.json()
        assert data_2008["scenario"] == "financial_crisis_2008"
        assert "2008" in data_2008["scenario_name"]
        summary_2008 = data_2008["summary"]
        # Initial = 10*180 + 10*150 + 10*110 + 10*200 = 1800 + 1500 + 1100 + 2000 = 6400
        assert summary_2008["initial_value"] == 6400.0
        assert summary_2008["loss_eur"] > 0.0
        assert summary_2008["simulated_value"] < summary_2008["initial_value"]
        # Financials (JPM) should be among most vulnerable in 2008 GFC
        vulnerable_tickers = [v["ticker"] for v in data_2008["vulnerable_assets"]]
        assert "JPM" in vulnerable_tickers
        # Healthcare (JNJ) should be among resilient in 2008 GFC
        resilient_tickers = [r["ticker"] for r in data_2008["resilient_assets"]]
        assert "JNJ" in resilient_tickers
        print("2008 Crisis Scenario: PASSED")

        # 7. Test 2022 Rate Shock Scenario (Energy XOM should outperform)
        res_2022 = client.post(
            f"/api/portfolio/{p_id}/stress-test",
            json={"scenario": "rate_shock_2022"},
        )
        assert res_2022.status_code == 200
        data_2022 = res_2022.json()
        # In 2022, XOM gained (+22%) so its shock_pct should be positive
        xom_holding = next(h for h in data_2022["holdings"] if h["ticker"] == "XOM")
        assert xom_holding["shock_pct"] > 0.0
        assert xom_holding["simulated_value"] > xom_holding["current_value"]
        assert data_2022["resilient_assets"][0]["ticker"] == "XOM"
        print("2022 Rate Shock Scenario: PASSED")

        # 8. Test Custom Market Drop Scenario (-25%)
        res_custom = client.post(
            f"/api/portfolio/{p_id}/stress-test",
            json={"scenario": "custom", "custom_market_drop_pct": 25.0},
        )
        assert res_custom.status_code == 200
        data_custom = res_custom.json()
        # High beta AAPL (1.25) should drop more (-31.25%) than low beta JNJ (0.55 * -25% = -13.75%)
        aapl_custom = next(h for h in data_custom["holdings"] if h["ticker"] == "AAPL")
        jnj_custom = next(h for h in data_custom["holdings"] if h["ticker"] == "JNJ")
        assert aapl_custom["shock_pct"] < jnj_custom["shock_pct"]
        print("Custom Shock Scenario: PASSED")

        # 9. Test Plural Route Alias
        res_alias = client.post(
            f"/api/portfolios/{p_id}/stress-test",
            json={"scenario": "covid_crash_2020"},
        )
        assert res_alias.status_code == 200
        assert res_alias.json()["scenario"] == "covid_crash_2020"
        print("Route aliases: PASSED")

    print("ALL PORTFOLIO STRESS-TEST QA TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    test_portfolio_stress_test()
