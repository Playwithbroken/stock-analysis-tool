import asyncio
import sys

from api import _normalize_ticker_input, _resolve_asset_query, _resolve_search_results


CASES = [
    ("robinhood", "HOOD"),
    ("Robinhood Aktie", "HOOD"),
    ("hood app", "HOOD"),
    ("HOOD stock", "HOOD"),
    ("robinhood markets inc", "HOOD"),
    ("coinbase stock", "COIN"),
    ("Vanguard S&P 500", "VOO"),
    ("s&p 500 etf", "VOO"),
    ("VOO", "VOO"),
    ("vanguard total market etf", "VTI"),
    ("jepi dividend etf", "JEPI"),
    ("vanguard total world etf", "VT"),
    ("nasdaq 100 etf", "QQQ"),
    ("msci world etf", "URTH"),
    ("dogecoin", "DOGE-USD"),
    ("DOGE", "DOGE-USD"),
    ("ethereum coin", "ETH-USD"),
    ("solana crypto", "SOL-USD"),
    ("bnb crypto", "BNB-USD"),
    ("litecoin coin", "LTC-USD"),
    ("polygon token", "MATIC-USD"),
    ("blackrock bitcoin etf", "IBIT"),
    ("fidelity bitcoin etf", "FBTC"),
    ("iShares semiconductors", "SOXX"),
    ("sofi", "SOFI"),
    ("hims", "HIMS"),
    ("rocket lab", "RKLB"),
    ("rheinmetall", "RHM.DE"),
    ("berkshire b", "BRK-B"),
    ("berkshire hathaway b", "BRK-B"),
    ("rwe aktie", "RWE.DE"),
    ("deutsche bank aktie", "DBK.DE"),
]


async def main() -> int:
    failures: list[str] = []

    for query, expected in CASES:
        normalized = _normalize_ticker_input(query)
        results = await _resolve_search_results(query, limit=5)
        resolved = await _resolve_asset_query(query, limit=5)
        top = str(results[0].get("ticker", "")).upper() if results else ""
        tickers = [str(item.get("ticker", "")).upper() for item in results]
        resolved_ticker = str(resolved.get("ticker", "")).upper()
        confidence = str(resolved.get("confidence", ""))

        ok = resolved_ticker == expected and (top == expected or (normalized == expected and expected in tickers))
        status = "OK" if ok else "FAIL"
        print(
            f"{status} {query!r} -> normalized={normalized!r}, "
            f"resolved={resolved_ticker!r}, top={top!r}, confidence={confidence!r}, expected={expected!r}"
        )

        if not ok:
            failures.append(
                f"{query}: expected {expected}, got normalized={normalized}, "
                f"resolved={resolved_ticker}, top={top}, all={tickers}"
            )

    if failures:
        print("\nSearch resolution failures:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("\nSearch resolution smoke passed.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
