
import asyncio
from src.risk_scanner import RiskScanner

async def test():
    scanner = RiskScanner()
    # Test with just one ticker to see the error
    scanner.scan_universe = ["SOFI"]
    print("Starting scan...")
    try:
        results = await scanner.scan_opportunities()
        print(f"Results: {results}")
    except Exception as e:
        print(f"Caught error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
