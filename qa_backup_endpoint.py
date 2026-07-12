import os
import tempfile


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "backup-endpoint-test.db")
        os.environ["APP_ACCESS_PASSWORD"] = "test-pass"
        os.environ["APP_SESSION_SECRET"] = "x" * 64
        os.environ["APP_COOKIE_SECURE"] = "false"

        from fastapi.testclient import TestClient
        import api

        manager = api.get_portfolio_manager()
        portfolio = manager.create_portfolio("Backup QA")
        manager.add_holding(portfolio["id"], "AAPL", 1, buy_price=100, purchase_date="2026-07-12")

        client = TestClient(api.app)

        unauthenticated = client.get("/api/admin/backup/portfolio-db")
        if unauthenticated.status_code != 401:
            print(f"FAIL: unauthenticated backup returned {unauthenticated.status_code}")
            return 1

        login = client.post("/api/auth/login", json={"password": "test-pass"})
        if login.status_code != 200:
            print(f"FAIL: login failed: {login.status_code} {login.text}")
            return 1

        backup = client.get("/api/admin/backup/portfolio-db")
        if backup.status_code != 200:
            print(f"FAIL: backup download failed: {backup.status_code} {backup.text}")
            return 1

        content_type = backup.headers.get("content-type", "")
        disposition = backup.headers.get("content-disposition", "")
        if "sqlite" not in content_type.lower():
            print(f"FAIL: unexpected backup content-type: {content_type}")
            return 1
        if "broker-freund-portfolio-backup-" not in disposition or ".db" not in disposition:
            print(f"FAIL: backup filename missing in content-disposition: {disposition}")
            return 1
        if not backup.content.startswith(b"SQLite format 3\x00"):
            print("FAIL: backup payload is not a SQLite database")
            return 1

    print("backup endpoint QA ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
