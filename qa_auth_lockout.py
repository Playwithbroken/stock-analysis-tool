import os
import tempfile
from datetime import datetime


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_ENV"] = "production"
        os.environ["APP_COOKIE_SECURE"] = "true"
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "auth-lockout-test.db")
        os.environ["APP_ACCESS_PASSWORD"] = "test-pass"
        os.environ["APP_SESSION_SECRET"] = "x" * 64
        os.environ["APP_LOGIN_MAX_ATTEMPTS"] = "2"
        os.environ["APP_LOGIN_LOCKOUT_MINUTES"] = "15"

        from fastapi.testclient import TestClient
        import api

        client = TestClient(api.app, base_url="https://testserver")
        manager = api.get_portfolio_manager()
        manager.reset_login_guard()

        first = client.post("/api/auth/login", json={"password": "wrong-1"})
        if first.status_code != 401:
            print(f"FAIL: first wrong login expected 401, got {first.status_code} {first.text}")
            return 1
        if "1 attempts left" not in first.text:
            print(f"FAIL: first wrong login did not report remaining attempts: {first.text}")
            return 1

        second = client.post("/api/auth/login", json={"password": "wrong-2"})
        if second.status_code != 429:
            print(f"FAIL: second wrong login expected 429, got {second.status_code} {second.text}")
            return 1

        guard = manager.get_login_guard_state()
        locked_until = guard.get("locked_until")
        if not locked_until:
            print(f"FAIL: guard did not persist locked_until: {guard}")
            return 1
        try:
            if datetime.fromisoformat(locked_until) <= datetime.now():
                print(f"FAIL: locked_until is not in the future: {locked_until}")
                return 1
        except ValueError:
            print(f"FAIL: locked_until is invalid ISO timestamp: {locked_until}")
            return 1

        correct_during_lockout = client.post("/api/auth/login", json={"password": "test-pass"})
        if correct_during_lockout.status_code != 429:
            print(
                "FAIL: correct password during lockout should stay blocked, "
                f"got {correct_during_lockout.status_code} {correct_during_lockout.text}"
            )
            return 1

        manager.reset_login_guard()
        success = client.post("/api/auth/login", json={"password": "test-pass"})
        if success.status_code != 200 or success.json().get("authenticated") is not True:
            print(f"FAIL: login after guard reset failed: {success.status_code} {success.text}")
            return 1
        reset_guard = manager.get_login_guard_state()
        if reset_guard.get("failed_attempts") != 0 or reset_guard.get("locked_until") is not None:
            print(f"FAIL: successful login did not clear guard: {reset_guard}")
            return 1

    print("auth lockout QA ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
