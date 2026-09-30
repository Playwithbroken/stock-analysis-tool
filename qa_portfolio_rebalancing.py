"""QA test suite for Portfolio Rebalancing Wizard."""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def test_rebalance_endpoint_and_logic():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_ENV"] = "production"
        os.environ["APP_COOKIE_SECURE"] = "false"
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "rebalance-test.db")
        os.environ["APP_ACCESS_PASSWORD"] = "test-pass"
        os.environ["APP_SESSION_SECRET"] = "x" * 64

        from fastapi.testclient import TestClient
        import api

        client = TestClient(api.app)

        # Login
        login_res = client.post("/api/auth/login", json={"password": "test-pass"})
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"

        # Create test portfolio
        create_res = client.post("/api/portfolios", json={"name": "Rebalance Test Portfolio"})
        assert create_res.status_code == 200, f"Create portfolio failed: {create_res.text}"
        portfolio = create_res.json()
        p_id = portfolio["id"]

        # Add 3 holdings: Overweighted AAPL, medium MSFT, small NVDA
        client.post(f"/api/portfolios/{p_id}/holdings", json={"ticker": "AAPL", "shares": 50, "buyPrice": 150.0})
        client.post(f"/api/portfolios/{p_id}/holdings", json={"ticker": "MSFT", "shares": 10, "buyPrice": 300.0})
        client.post(f"/api/portfolios/{p_id}/holdings", json={"ticker": "NVDA", "shares": 5, "buyPrice": 100.0})

        # --- Test 1: Equal Weight Rebalance ---
        res_equal = client.post(
            f"/api/portfolio/{p_id}/rebalance",
            json={"mode": "equal", "fresh_cash": 0.0, "max_position_pct": 25.0},
        )
        assert res_equal.status_code == 200, f"Equal rebalance failed: {res_equal.text}"
        data_equal = res_equal.json()
        assert len(data_equal["items"]) == 3
        # In equal weight mode with 3 assets, each target weight should be ~33.33%
        for item in data_equal["items"]:
            assert 33.0 <= item["target_weight_pct"] <= 34.0
        assert data_equal["summary"]["trades_count"] > 0
        print("Equal weight rebalance: PASSED")

        # --- Test 2: Cap Weighting Rebalance ---
        res_cap = client.post(
            f"/api/portfolio/{p_id}/rebalance",
            json={"mode": "cap", "fresh_cash": 0.0, "max_position_pct": 40.0},
        )
        assert res_cap.status_code == 200
        data_cap = res_cap.json()
        for item in data_cap["items"]:
            assert item["target_weight_pct"] <= 40.5, f"{item['ticker']} exceeds 40% cap: {item['target_weight_pct']}%"
        print("Cap weight rebalance: PASSED")

        # --- Test 3: Tax-Efficient Fresh Cash Rebalance ---
        res_cash = client.post(
            f"/api/portfolio/{p_id}/rebalance",
            json={"mode": "equal", "fresh_cash": 2000.0, "max_position_pct": 25.0},
        )
        assert res_cash.status_code == 200
        data_cash = res_cash.json()
        assert data_cash["fresh_cash"] == 2000.0
        assert data_cash["new_total_value"] > data_cash["current_total_value"]
        # Underweight holdings must receive positive cash_only_shares
        has_cash_buy = any(item["cash_only_action"] == "BUY" and item["cash_only_shares"] > 0 for item in data_cash["items"])
        assert has_cash_buy, "Expected at least one cash-only buy allocation"
        print("Tax-efficient fresh cash rebalance: PASSED")

        # --- Test 4: Custom Target Weights ---
        res_custom = client.post(
            f"/api/portfolio/{p_id}/rebalance",
            json={
                "mode": "custom",
                "target_weights": {"AAPL": 50.0, "MSFT": 30.0, "NVDA": 20.0},
                "fresh_cash": 0.0,
            },
        )
        assert res_custom.status_code == 200
        data_custom = res_custom.json()
        weights_map = {item["ticker"]: item["target_weight_pct"] for item in data_custom["items"]}
        assert round(weights_map["AAPL"]) == 50
        assert round(weights_map["MSFT"]) == 30
        assert round(weights_map["NVDA"]) == 20
        print("Custom target weights rebalance: PASSED")


def test_ui_contract():
    ui_view = (ROOT / "frontend" / "src" / "components" / "PortfolioView.tsx").read_text(encoding="utf-8")
    wizard_comp = (ROOT / "frontend" / "src" / "components" / "RebalanceWizard.tsx").read_text(encoding="utf-8")

    assert "import RebalanceWizard" in ui_view
    assert "<RebalanceWizard" in ui_view
    assert "Rebalancing-Rechner" in ui_view
    assert "1-Klick-Rebalancing-Kalkulator" in wizard_comp
    assert "Steueroptimiertes Cash-Rebalancing" in wizard_comp
    assert "ORDER-CHECKLISTE" in wizard_comp
    print("UI contracts: PASSED")


def main():
    test_rebalance_endpoint_and_logic()
    test_ui_contract()
    print("\nALL PORTFOLIO REBALANCING QA TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
