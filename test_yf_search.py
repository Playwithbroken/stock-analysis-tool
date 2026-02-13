import yfinance as yf
import json

def test_search(query):
    print(f"Searching for: {query}")
    try:
        search = yf.Search(query, max_results=5)
        print("Search results (quotes):")
        print(json.dumps(search.quotes, indent=2))
        
        # Test Search.quotes (older API)
        # print("Search results (quotes):")
        # print(json.dumps(search.quotes, indent=2))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_search("Pfizer")
    test_search("Microsoft")
