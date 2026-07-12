import os
import tempfile


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_ENV"] = "production"
        os.environ["APP_COOKIE_SECURE"] = "true"
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "auth-cookie-test.db")
        os.environ["APP_ACCESS_PASSWORD"] = "test-pass"
        os.environ["APP_SESSION_SECRET"] = "x" * 64

        from fastapi.testclient import TestClient
        import api

        client = TestClient(api.app, base_url="https://testserver")

        login = client.post("/api/auth/login", json={"password": "test-pass", "remember_device": True})
        if login.status_code != 200:
            print(f"FAIL: login failed: {login.status_code} {login.text}")
            return 1

        login_cookie = login.headers.get("set-cookie", "")
        failures = []
        failures.extend(
            require_cookie_flags(
                "login",
                login_cookie,
                required=("brokerfreund_session=", "HttpOnly", "SameSite=lax", "Secure", "Max-Age=604800"),
            )
        )

        status = client.get("/api/auth/status")
        if status.status_code != 200 or status.json().get("authenticated") is not True:
            failures.append(f"auth status did not accept secure session cookie: {status.status_code} {status.text}")

        logout = client.post("/api/auth/logout")
        if logout.status_code != 200:
            failures.append(f"logout failed: {logout.status_code} {logout.text}")
        logout_cookie = logout.headers.get("set-cookie", "")
        failures.extend(
            require_cookie_flags(
                "logout",
                logout_cookie,
                required=("brokerfreund_session=", "SameSite=lax", "Max-Age=0"),
            )
        )

        if failures:
            print("Auth cookie QA failures:")
            for failure in failures:
                print(f"- {failure}")
            return 1

    print("auth cookie security QA ok")
    return 0


def require_cookie_flags(label: str, cookie: str, required: tuple[str, ...]) -> list[str]:
    failures = []
    if not cookie:
        return [f"{label}: Set-Cookie header missing"]
    lowered = cookie.lower()
    for item in required:
        if item.lower() not in lowered:
            failures.append(f"{label}: Set-Cookie missing {item!r}: {cookie!r}")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
