import requests
import time

def test_api():
    base_url = "http://localhost:8000"
    try:
        print(f"Testing connectivity to {base_url}...")
        start = time.time()
        r = requests.get(f"{base_url}/")
        print(f"Root status: {r.status_code}, time: {time.time()-start:.2f}s")
        
        print("Testing /api/discovery/stars...")
        start = time.time()
        r = requests.get(f"{base_url}/api/discovery/stars")
        print(f"Stars status: {r.status_code}, time: {time.time()-start:.2f}s")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_api()
