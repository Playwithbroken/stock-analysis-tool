import requests
import sys

BASE_URL = "http://127.0.0.1:8000"

def test_endpoint(name, url):
    print(f"Testing {name} ({url})...", end=" ")
    try:
        res = requests.get(f"{BASE_URL}{url}")
        if res.status_code == 200:
            print("OK")
            return res.json()
        else:
            print(f"FAILED ({res.status_code})")
            print(res.text)
            return None
    except Exception as e:
        print(f"ERROR: {e}")
        return None

def verify_verdict():
    data = test_endpoint("Analysis", "/api/analyze/AAPL")
    if data:
        if "verdict" in data:
            print("  [PASS] 'verdict' field found in response.")
        else:
            print("  [FAIL] 'verdict' field MISSING in response.")

def verify_dividends():
    # Need a portfolio ID first
    portfolios = test_endpoint("Portfolios", "/api/portfolios")
    if portfolios and len(portfolios) > 0:
        pid = portfolios[0]['id']
        div_data = test_endpoint("Dividends", f"/api/portfolio/{pid}/dividends")
        if div_data:
            if "monthly" in div_data:
                print("  [PASS] 'monthly' field found in dividend response.")
            else:
                 print("  [FAIL] 'monthly' field MISSING in dividend response.")
    else:
        print("  [SKIP] No portfolios found to test dividends.")

if __name__ == "__main__":
    print("--- Starting Endpoint Verification ---")
    verify_verdict()
    verify_dividends()
    print("--- Verification Complete ---")
