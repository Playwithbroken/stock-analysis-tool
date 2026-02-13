import requests
import json

BASE_URL = "http://localhost:8000"

def test_endpoint(endpoint):
    print(f"\n--- Testing {endpoint} ---")
    try:
        response = requests.get(f"{BASE_URL}{endpoint}")
        if response.status_code == 200:
            data = response.json()
            print(f"Count: {len(data)}")
            if len(data) > 0:
                print(f"First item: {data[0].get('ticker')} - {data[0].get('price')}")
        else:
            print(f"Error: {response.status_code}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test_endpoint("/api/discovery/trending")
    test_endpoint("/api/discovery/cryptos")
    test_endpoint("/api/discovery/commodities")
    test_endpoint("/api/discovery/small-caps")
