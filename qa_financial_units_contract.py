import math

from src.analyzer import StockAnalyzer
from src.financial_units import normalize_dividend_yield_pct, ratio_to_pct, relative_change_pct


def main() -> None:
    assert math.isclose(normalize_dividend_yield_pct(0.0614) or 0, 6.14)
    assert math.isclose(normalize_dividend_yield_pct(6.14) or 0, 6.14)
    assert normalize_dividend_yield_pct(None) is None
    assert ratio_to_pct(0.65) == 65.0
    assert math.isclose(ratio_to_pct(2.3087) or 0, 230.87)
    assert math.isclose(relative_change_pct(120, 100) or 0, 20.0)
    assert relative_change_pct(120, 0) is None
    assert relative_change_pct(120, None) is None
    assert relative_change_pct(float("inf"), 100) is None

    for provider_value in (0.0614, 6.14):
        result = StockAnalyzer({"fundamentals": {"dividend_yield": provider_value}}).analyze_opportunities()
        dividend = next(item for item in result.findings if item["metric"] == "Dividend Income")
        assert dividend["value"] == "6.14% yield"
    print("financial unit contract QA passed")


if __name__ == "__main__":
    main()
