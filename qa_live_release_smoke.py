import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests


DEFAULT_TARGET = "https://web-production-8546b.up.railway.app"
ROOT = Path(__file__).resolve().parent
LOCAL_DIST_INDEX = ROOT / "frontend" / "dist" / "index.html"


def get(url: str) -> requests.Response:
    return requests.get(url, timeout=20)


def require(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    target = (os.getenv("QA_TARGET_URL") or DEFAULT_TARGET).strip().rstrip("/")
    failures: list[str] = []

    index = get(f"{target}/")
    require(index.status_code == 200, failures, f"/ returned {index.status_code}")
    if index.status_code != 200:
        print_failures(target, failures)
        return 1

    body = index.text
    js_match = re.search(r"/assets/(index-[^\"']+\.js)", body)
    css_match = re.search(r"/assets/(index-[^\"']+\.css)", body)
    require(bool(js_match), failures, "index JS asset hash missing")
    require(bool(css_match), failures, "index CSS asset hash missing")
    local_js, local_css = local_dist_assets()
    if os.getenv("QA_SKIP_LOCAL_ASSET_MATCH", "").strip().lower() not in {"1", "true", "yes"}:
        if local_js:
            require(
                bool(js_match and js_match.group(1) == local_js),
                failures,
                f"live JS asset {js_match.group(1) if js_match else 'missing'} does not match local dist {local_js}",
            )
        if local_css:
            require(
                bool(css_match and css_match.group(1) == local_css),
                failures,
                f"live CSS asset {css_match.group(1) if css_match else 'missing'} does not match local dist {local_css}",
            )

    health = get(f"{target}/api/health")
    require(health.status_code == 200, failures, f"/api/health returned {health.status_code}")
    health_json = {}
    if health.status_code == 200:
        try:
            health_json = health.json()
        except ValueError:
            failures.append("/api/health returned invalid JSON")
    persistence = health_json.get("persistence") or {}
    release = health_json.get("release") or {}
    require(health_json.get("status") == "ok", failures, f"health status is {health_json.get('status')!r}")
    require(persistence.get("ready") is True, failures, "persistence.ready is not true")
    require(persistence.get("volume_attached") is True, failures, "persistence.volume_attached is not true")
    require(persistence.get("database_on_volume") is True, failures, "persistence.database_on_volume is not true")
    require(release.get("schema") == "release-identity.v1", failures, "release identity schema missing")
    require(bool(release.get("commit_sha")), failures, "release commit SHA missing")
    require(bool(release.get("deployment_id")), failures, "release deployment ID missing")
    expected_commit = os.getenv("QA_EXPECTED_COMMIT", "").strip()
    if expected_commit:
        require(
            str(release.get("commit_sha") or "").startswith(expected_commit),
            failures,
            f"live commit {release.get('commit_short')!r} does not match expected {expected_commit!r}",
        )

    expected_security = {
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "strict-origin-when-cross-origin",
    }
    for path, response in [("/", index), ("/api/health", health)]:
        check_security_headers(path, response, expected_security, failures)

    index_cache = index.headers.get("cache-control", "").lower()
    require("no-cache" in index_cache and "no-store" in index_cache, failures, f"/ cache-control unsafe: {index_cache!r}")

    asset_paths = []
    if js_match:
        asset_paths.append(f"/assets/{js_match.group(1)}")
    if css_match:
        asset_paths.append(f"/assets/{css_match.group(1)}")
    asset_paths.extend(["/manifest.json", "/sw.js", "/registerSW.js"])

    for path in asset_paths:
        response = get(urljoin(f"{target}/", path.lstrip("/")))
        require(response.status_code == 200, failures, f"{path} returned {response.status_code}")
        check_security_headers(path, response, expected_security, failures)
        cache = response.headers.get("cache-control", "").lower()
        if path.startswith("/assets/"):
            require(
                "max-age=31536000" in cache and "immutable" in cache,
                failures,
                f"{path} should be immutable cached, got {cache!r}",
            )
        elif path in {"/sw.js", "/registerSW.js"}:
            require("no-cache" in cache and "no-store" in cache, failures, f"{path} cache-control unsafe: {cache!r}")
        elif path == "/manifest.json":
            require("max-age=300" in cache, failures, f"{path} should be short cached, got {cache!r}")

    if failures:
        print_failures(target, failures)
        return 1

    print(f"live release smoke ok: {target}")
    print(
        f"version={health_json.get('version')} "
        f"commit={release.get('commit_short')} "
        f"js={js_match.group(1) if js_match else 'n/a'} "
        f"css={css_match.group(1) if css_match else 'n/a'}"
    )
    return 0


def local_dist_assets() -> tuple[str | None, str | None]:
    if not LOCAL_DIST_INDEX.exists():
        return None, None
    text = LOCAL_DIST_INDEX.read_text(encoding="utf-8", errors="ignore")
    js_match = re.search(r"/assets/(index-[^\"']+\.js)", text)
    css_match = re.search(r"/assets/(index-[^\"']+\.css)", text)
    return (
        js_match.group(1) if js_match else None,
        css_match.group(1) if css_match else None,
    )


def check_security_headers(path: str, response: requests.Response, expected: dict[str, str], failures: list[str]) -> None:
    headers = {key.lower(): value for key, value in response.headers.items()}
    for name, expected_value in expected.items():
        actual = headers.get(name, "")
        require(actual == expected_value, failures, f"{path} {name} expected {expected_value!r}, got {actual!r}")
    permissions = headers.get("permissions-policy", "")
    for item in ("camera=()", "microphone=()", "geolocation=()", "payment=()"):
        require(item in permissions, failures, f"{path} permissions-policy missing {item!r}")


def print_failures(target: str, failures: list[str]) -> None:
    print(f"live release smoke failed: {target}", file=sys.stderr)
    for failure in failures:
        print(f"- {failure}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
