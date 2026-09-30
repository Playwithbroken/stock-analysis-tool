"""QA test suite for Portfolio Benchmark Comparison."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def mock_get_history(self, period="1y", interval="1d"):
    # Deterministic mock historical series based on ticker
    dates = [
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
        "2024-01-05",
        "2024-01-08",
        "2024-01-09",
        "2024-01-10",
        "2024-01-11",
        "2024-01-12",
        "2024-01-15",
    ]
    ticker = getattr(self, "ticker", "")
    if ticker in ("SPY", "URTH", "QQQ", "^GDAXI"):
        # Benchmark rises from 100 to 110 (+10%)
        prices = [100.0, 101.0, 102.0, 103.0, 102.5, 104.0, 106.0, 105.5, 108.0, 110.0]
    elif ticker == "AAPL":
        # Outperformer: rises from 150 to 180 (+20%)
        prices = [150.0, 153.0, 155.0, 158.0, 157.0, 162.0, 168.0, 170.0, 175.0, 180.0]
    else:
        # Generic: rises from 50 to 55
        prices = [50.0, 50.5, 51.0, 52.0, 51.5, 52.5, 53.0, 53.5, 54.0, 55.0]

    return [{"time": d, "price": p} for d, p in zip(dates, prices)]


def test_portfolio_benchmark_comparison():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_ENV"] = "production"
        os.environ["APP_COOKIE_SECURE"] = "false"
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "benchmark-test.db")
        os.environ["APP_ACCESS_PASSWORD"] = "test-pass"
        os.environ["APP_SESSION_SECRET"] = "x" * 64

        from fastapi.testclient import TestClient
        import api
        from src.data_fetcher import DataFetcher

        client = TestClient(api.app)

        # Login
        login_res = client.post("/api/auth/login", json={"password": "test-pass"})
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"

        # Test 1: 404 on missing portfolio
        res_404 = client.get("/api/portfolio/non-existent-id/benchmark")
        assert res_404.status_code == 404

        # Create test portfolio
        create_res = client.post("/api/portfolios", json={"name": "Alpha Growth Portfolio"})
        assert create_res.status_code == 200
        portfolio = create_res.json()
        p_id = portfolio["id"]

        # Test 2: Empty portfolio handles cleanly without crash
        res_empty = client.get(f"/api/portfolio/{p_id}/benchmark?benchmark=SPY")
        assert res_empty.status_code == 200
        data_empty = res_empty.json()
        assert data_empty["chart_data"] == []
        assert data_empty["metrics"]["total_return_portfolio_pct"] == 0.0

        # Add AAPL holding
        client.post(f"/api/portfolios/{p_id}/holdings", json={"ticker": "AAPL", "shares": 10, "buyPrice": 150.0})

        # Test 3: Benchmark comparison with mock data
        with patch.object(DataFetcher, "get_history", mock_get_history):
            res_bm = client.get(f"/api/portfolio/{p_id}/benchmark?benchmark=SPY&period=1y")
            assert res_bm.status_code == 200
            data_bm = res_bm.json()

            assert data_bm["portfolio_id"] == p_id
            assert data_bm["benchmark_symbol"] == "SPY"
            assert len(data_bm["chart_data"]) == 10

            first_pt = data_bm["chart_data"][0]
            assert first_pt["portfolio_pct"] == 0.0
            assert first_pt["benchmark_pct"] == 0.0

            last_pt = data_bm["chart_data"][-1]
            assert last_pt["portfolio_pct"] == 20.0
            assert last_pt["benchmark_pct"] == 10.0

            metrics = data_bm["metrics"]
            # Alpha = 20 - 10 = +10.0%
            assert metrics["alpha_excess_pct"] == 10.0
            assert metrics["total_return_portfolio_pct"] == 20.0
            assert metrics["total_return_benchmark_pct"] == 10.0
            assert metrics["beta"] > 0.0
            assert metrics["sharpe_ratio"] != 0.0
            assert "Hervorragende Outperformance" in data_bm["verdict"]

            # Test 4: Verify plural route alias
            res_alias = client.get(f"/api/portfolios/{p_id}/benchmark?benchmark=URTH")
            assert res_alias.status_code == 200
            assert res_alias.json()["benchmark_symbol"] == "URTH"

    print("All Portfolio Benchmark Comparison tests PASSED!")


if __name__ == "__main__":
    test_portfolio_benchmark_comparison()
