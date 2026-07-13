from __future__ import annotations

import os
import tempfile


def _validate_contract(payload: dict, expected_fallback: str) -> list[str]:
    failures: list[str] = []
    for field in ("generated_at", "headline", "opening_bias", "regions", "quality", "trade_setups_status"):
        if field not in payload:
            failures.append(f"missing field {field}")
    if not str(payload.get("headline") or "").strip():
        failures.append("headline is blank")
    if not str(payload.get("opening_bias") or "").strip():
        failures.append("opening_bias is blank")
    quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
    if quality.get("status") != "partial":
        failures.append(f"quality status is not partial: {quality}")
    if quality.get("fallback") != expected_fallback:
        failures.append(f"expected fallback {expected_fallback}, got {quality.get('fallback')}")
    if payload.get("trade_setups_status") != "insufficient_signal":
        failures.append("fallback does not block trade setups")
    return failures


class BrokenBriefService:
    def get_cached_or_last_brief(self, snapshot=None):
        raise RuntimeError("cache intentionally unavailable")

    def build_empty_brief(self, reason: str):
        raise RuntimeError("service fallback intentionally unavailable")

    def get_brief_fast(self, snapshot=None):
        raise RuntimeError("brief provider intentionally unavailable")


class BrokenPublicSignalService:
    def build_watchlist_snapshot(self, items):
        raise RuntimeError("public signal provider intentionally unavailable")


class MalformedCacheService(BrokenBriefService):
    def get_cached_or_last_brief(self, snapshot=None):
        return {"quality": "corrupt-cache-value"}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "morning-brief-availability.db")
        os.environ["APP_ACCESS_PASSWORD"] = "test-pass"
        os.environ["APP_SESSION_SECRET"] = "x" * 64
        os.environ["APP_COOKIE_SECURE"] = "false"

        from fastapi.testclient import TestClient
        import api

        client = TestClient(api.app)
        login = client.post("/api/auth/login", json={"password": "test-pass"})
        if login.status_code != 200:
            print(f"FAIL login: HTTP {login.status_code}")
            return 1

        failures: list[str] = []
        original_brief_service = api.get_morning_brief_service
        original_signal_service = api.get_public_signal_service

        broken_service = BrokenBriefService()
        api.get_morning_brief_service = lambda: broken_service
        api.get_public_signal_service = lambda: BrokenPublicSignalService()
        api._cache_forget("morning_brief:full")
        try:
            fast = client.get("/api/market/morning-brief", params={"fast": "true"})
            full = client.get("/api/market/morning-brief")
            if fast.status_code != 200:
                failures.append(f"fast endpoint returned HTTP {fast.status_code}")
            else:
                failures.extend(f"fast: {item}" for item in _validate_contract(fast.json(), "warming_up"))
                if fast.json().get("quality", {}).get("cache_mode") != "fast_cached":
                    failures.append("fast: cache_mode missing")
            if full.status_code != 200:
                failures.append(f"full endpoint returned HTTP {full.status_code}")
            else:
                failures.extend(f"full: {item}" for item in _validate_contract(full.json(), "error"))

            api.get_morning_brief_service = lambda: MalformedCacheService()
            malformed = client.get("/api/market/morning-brief", params={"fast": "true"})
            if malformed.status_code != 200:
                failures.append(f"malformed cache fallback returned HTTP {malformed.status_code}")
            else:
                failures.extend(
                    f"malformed: {item}"
                    for item in _validate_contract(malformed.json(), "warming_up")
                )

            def fail_initialization():
                raise RuntimeError("service initialization intentionally unavailable")

            api.get_morning_brief_service = fail_initialization
            initialization = client.get("/api/market/morning-brief")
            if initialization.status_code != 200:
                failures.append(f"initialization fallback returned HTTP {initialization.status_code}")
            else:
                failures.extend(
                    f"initialization: {item}"
                    for item in _validate_contract(initialization.json(), "service_initialization")
                )
        finally:
            api.get_morning_brief_service = original_brief_service
            api.get_public_signal_service = original_signal_service

        if failures:
            print("\nMorning brief availability failures:")
            for failure in failures:
                print(f"- {failure}")
            return 1

    print("Morning brief availability QA passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
