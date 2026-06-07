import asyncio
import sys

from api import _normalize_ticker_input, _resolve_asset_query, _resolve_search_results


CASES = [
    ("robinhood", "HOOD"),
    ("hood app", "HOOD"),
    ("Vanguard S&P 500", "VOO"),
    ("VOO", "VOO"),
    ("dogecoin", "DOGE-USD"),
    ("DOGE", "DOGE-USD"),
    ("blackrock bitcoin etf", "IBIT"),
    ("iShares semiconductors", "SOXX"),
    ("sofi", "SOFI"),
    ("hims", "HIMS"),
    ("rocket lab", "RKLB"),
    ("rheinmetall", "RHM.DE"),
    ("berkshire b", "BRK-B"),
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
