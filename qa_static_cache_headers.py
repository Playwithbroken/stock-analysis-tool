import os
import re
import tempfile


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "static-cache-test.db")
        os.environ["APP_ACCESS_PASSWORD"] = "test-pass"
        os.environ["APP_SESSION_SECRET"] = "x" * 64

        from fastapi.testclient import TestClient
        import api

        client = TestClient(api.app)

        index = client.get("/")
        if index.status_code != 200:
            print(f"FAIL: / returned {index.status_code}")
            return 1
        index_cache = index.headers.get("cache-control", "")
        if "no-cache" not in index_cache.lower() or "no-store" not in index_cache.lower():
            print(f"FAIL: index.html cache-control is unsafe: {index_cache}")
            return 1

        html = index.text
        js_match = re.search(r"/assets/(index-[^\"']+\.js)", html)
        css_match = re.search(r"/assets/(index-[^\"']+\.css)", html)
        if not js_match or not css_match:
            print("FAIL: built index asset hashes not found")
            return 1

        for asset in (js_match.group(1), css_match.group(1)):
            response = client.get(f"/assets/{asset}")
            if response.status_code != 200:
                print(f"FAIL: /assets/{asset} returned {response.status_code}")
                return 1
            cache = response.headers.get("cache-control", "").lower()
            if "max-age=31536000" not in cache or "immutable" not in cache:
                print(f"FAIL: /assets/{asset} cache-control is not immutable: {cache}")
                return 1

        for path in ("/sw.js", "/registerSW.js"):
            response = client.get(path)
            if response.status_code != 200:
                print(f"FAIL: {path} returned {response.status_code}")
                return 1
            cache = response.headers.get("cache-control", "").lower()
            if "no-cache" not in cache or "no-store" not in cache:
                print(f"FAIL: {path} cache-control is unsafe: {cache}")
                return 1

        manifest = client.get("/manifest.json")
        if manifest.status_code != 200:
            print(f"FAIL: /manifest.json returned {manifest.status_code}")
            return 1
        manifest_cache = manifest.headers.get("cache-control", "").lower()
        if "max-age=300" not in manifest_cache:
            print(f"FAIL: manifest cache-control should be short-lived: {manifest_cache}")
            return 1

    print("static cache header QA ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
