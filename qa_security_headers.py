import os
import re
import tempfile


REQUIRED_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
}

REQUIRED_PERMISSIONS = (
    "camera=()",
    "microphone=()",
    "geolocation=()",
    "payment=()",
)


def check_common_headers(path: str, headers) -> list[str]:
    failures: list[str] = []
    normalized = {key.lower(): value for key, value in headers.items()}
    for name, expected in REQUIRED_HEADERS.items():
        actual = normalized.get(name, "")
        if actual != expected:
            failures.append(f"{path}: {name} expected {expected!r}, got {actual!r}")

    permissions = normalized.get("permissions-policy", "")
    for item in REQUIRED_PERMISSIONS:
        if item not in permissions:
            failures.append(f"{path}: permissions-policy missing {item!r}: {permissions!r}")
    return failures


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_ENV"] = "production"
        os.environ["APP_COOKIE_SECURE"] = "true"
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "security-headers-test.db")
        os.environ["APP_ACCESS_PASSWORD"] = "test-pass"
        os.environ["APP_SESSION_SECRET"] = "x" * 64

        from fastapi.testclient import TestClient
        import api

        client = TestClient(api.app)
        failures: list[str] = []

        index = client.get("/")
        if index.status_code != 200:
            print(f"FAIL: / returned {index.status_code}")
            return 1
        failures.extend(check_common_headers("/", index.headers))
        hsts = index.headers.get("strict-transport-security", "")
        if "max-age=31536000" not in hsts or "includeSubDomains" not in hsts:
            failures.append(f"/: strict-transport-security missing or weak: {hsts!r}")

        health = client.get("/api/health")
        if health.status_code != 200:
            print(f"FAIL: /api/health returned {health.status_code}")
            return 1
        failures.extend(check_common_headers("/api/health", health.headers))

        js_match = re.search(r"/assets/(index-[^\"']+\.js)", index.text)
        if not js_match:
            print("FAIL: built JS asset hash not found")
            return 1
        asset_path = f"/assets/{js_match.group(1)}"
        asset = client.get(asset_path)
        if asset.status_code != 200:
            print(f"FAIL: {asset_path} returned {asset.status_code}")
            return 1
        failures.extend(check_common_headers(asset_path, asset.headers))

        if failures:
            print("Security header QA failures:")
            for failure in failures:
                print(f"- {failure}")
            return 1

    print("security header QA ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
