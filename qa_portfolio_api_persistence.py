import os
import tempfile


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_ENV"] = "production"
        os.environ["APP_COOKIE_SECURE"] = "false"
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "portfolio-api-test.db")
        os.environ["APP_ACCESS_PASSWORD"] = "test-pass"
        os.environ["APP_SESSION_SECRET"] = "x" * 64

        from fastapi.testclient import TestClient
        import api

        client = TestClient(api.app)

        unauthenticated = client.get("/api/portfolios")
        if unauthenticated.status_code != 401:
            print(f"FAIL: unauthenticated portfolio list returned {unauthenticated.status_code}")
            return 1

        login = client.post("/api/auth/login", json={"password": "test-pass"})
        if login.status_code != 200:
            print(f"FAIL: login failed: {login.status_code} {login.text}")
            return 1

        created = client.post("/api/portfolios", json={"name": "API Persistence QA"})
        if created.status_code != 200:
            print(f"FAIL: create portfolio failed: {created.status_code} {created.text}")
            return 1
        portfolio = created.json()
        portfolio_id = portfolio.get("id")
        if not portfolio_id or portfolio.get("name") != "API Persistence QA":
            print(f"FAIL: unexpected portfolio payload: {portfolio}")
            return 1

        holding = client.post(
            f"/api/portfolios/{portfolio_id}/holdings",
            json={
                "ticker": "hood",
                "shares": 12.5,
                "buy_price": 98.05,
                "purchase_date": "2026-07-12",
            },
        )
        if holding.status_code != 200:
            print(f"FAIL: add holding failed: {holding.status_code} {holding.text}")
            return 1
        saved_holding = holding.json()
        if saved_holding.get("ticker") != "HOOD" or saved_holding.get("shares") != 12.5:
            print(f"FAIL: holding was not normalized/saved: {saved_holding}")
            return 1

        first_list = client.get("/api/portfolios")
        if first_list.status_code != 200:
            print(f"FAIL: first portfolio list failed: {first_list.status_code} {first_list.text}")
            return 1
        loaded = find_portfolio(first_list.json(), portfolio_id)
        if not loaded or not loaded.get("holdings"):
            print(f"FAIL: portfolio/holding missing before restart: {first_list.json()}")
            return 1

        # Simulate an app-level manager restart while keeping the same SQLite file.
        api._portfolio_manager = None
        restarted_list = client.get("/api/portfolios")
        if restarted_list.status_code != 200:
            print(f"FAIL: restarted portfolio list failed: {restarted_list.status_code} {restarted_list.text}")
            return 1
        restarted = find_portfolio(restarted_list.json(), portfolio_id)
        if not restarted:
            print(f"FAIL: portfolio missing after manager restart: {restarted_list.json()}")
            return 1
        restarted_holding = next((item for item in restarted.get("holdings") or [] if item.get("ticker") == "HOOD"), None)
        if not restarted_holding:
            print(f"FAIL: holding missing after manager restart: {restarted}")
            return 1
        if restarted_holding.get("shares") != 12.5 or restarted_holding.get("buyPrice") != 98.05:
            print(f"FAIL: holding values changed after restart: {restarted_holding}")
            return 1

        patched = client.patch(
            f"/api/portfolios/{portfolio_id}/holdings/HOOD",
            json={"shares": 13, "buy_price": 101.25, "purchase_date": "2026-07-13"},
        )
        if patched.status_code != 200:
            print(f"FAIL: update holding failed: {patched.status_code} {patched.text}")
            return 1
        updated = patched.json()
        if updated.get("shares") != 13 or updated.get("buyPrice") != 101.25 or updated.get("purchaseDate") != "2026-07-13":
            print(f"FAIL: updated holding payload incorrect: {updated}")
            return 1

        api._portfolio_manager = None
        final_list = client.get("/api/portfolios")
        final = find_portfolio(final_list.json(), portfolio_id) if final_list.status_code == 200 else None
        final_holding = next((item for item in (final or {}).get("holdings") or [] if item.get("ticker") == "HOOD"), None)
        if not final_holding or final_holding.get("shares") != 13 or final_holding.get("buyPrice") != 101.25:
            print(f"FAIL: updated holding did not persist after restart: {final_list.status_code} {final_list.text}")
            return 1

    print("portfolio API persistence QA ok")
    return 0


def find_portfolio(portfolios, portfolio_id):
    return next((item for item in portfolios if item.get("id") == portfolio_id), None)


if __name__ == "__main__":
    raise SystemExit(main())
