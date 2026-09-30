"""QA test suite for Bull vs. Bear Debate Engine."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.analyzer import StockAnalyzer


def test_growth_stock_debate():
    data = {
        "ticker": "NVDA",
        "company_name": "NVIDIA Corporation",
        "fundamentals": {
            "quote_type": "EQUITY",
            "revenue_growth": 0.45,
            "profit_margin": 0.28,
            "roe": 0.35,
            "pe_ratio": 55.0,
            "forward_pe": 38.0,
            "debt_to_equity": 30.0,
        },
        "price_data": {
            "current_price": 120.0,
            "change_1y": 85.0,
            "rsi": 62.0,
            "from_52w_high": -4.0,
        },
        "volatility": {"beta": 1.45, "volatility_annual": 38.0},
        "short_interest": {"short_percent_of_float": 2.1},
        "analyst_data": {"target_mean": 140.0},
    }
    analyzer = StockAnalyzer(data)
    debate = analyzer.analyze_bull_bear_debate()

    assert debate is not None
    assert 15 <= debate["bull_pct"] <= 85
    assert 15 <= debate["bear_pct"] <= 85
    assert debate["bull_pct"] + debate["bear_pct"] == 100
    assert len(debate["bull_thesis"]) >= 2
    assert len(debate["bear_thesis"]) >= 2
    assert any("Wachstum" in p["title"] or "Margen" in p["title"] for p in debate["bull_thesis"])
    assert any("Bewertung" in p["title"] or "KGV" in p["title"] for p in debate["bear_thesis"])
    assert len(debate["key_battleground"]) > 10
    assert len(debate["bull_catalysts"]) >= 2
    assert len(debate["invalidation_triggers"]) >= 2
    print("Growth stock debate test: PASSED")


def test_distressed_stock_debate():
    data = {
        "ticker": "DIST",
        "company_name": "Distressed Corp",
        "fundamentals": {
            "quote_type": "EQUITY",
            "revenue_growth": -0.15,
            "profit_margin": -0.12,
            "roe": -0.20,
            "pe_ratio": None,
            "debt_to_equity": 290.0,
        },
        "price_data": {
            "current_price": 8.0,
            "change_1y": -55.0,
            "rsi": 28.0,
            "from_52w_high": -60.0,
        },
        "short_interest": {"short_percent_of_float": 18.5},
    }
    analyzer = StockAnalyzer(data)
    debate = analyzer.analyze_bull_bear_debate()

    assert debate["bear_pct"] > debate["bull_pct"]
    assert any("Profitabilität" in p["title"] or "Rückläufige Erlöse" in p["title"] for p in debate["bear_thesis"])
    assert any("Rebound" in p["title"] or "Squeeze" in p["title"] or "Operative" in p["title"] for p in debate["bull_thesis"])
    print("Distressed stock debate test: PASSED")


def test_etf_and_crypto_fallbacks():
    etf_data = {
        "ticker": "VOO",
        "company_name": "Vanguard S&P 500 ETF",
        "fundamentals": {"quote_type": "ETF"},
        "price_data": {"current_price": 480.0, "change_1y": 22.0},
    }
    etf_analyzer = StockAnalyzer(etf_data)
    etf_debate = etf_analyzer.analyze_bull_bear_debate()
    assert len(etf_debate["bull_thesis"]) >= 2
    assert len(etf_debate["bear_thesis"]) >= 2

    crypto_data = {
        "ticker": "BTC-USD",
        "company_name": "Bitcoin USD",
        "fundamentals": {"quote_type": "CRYPTOCURRENCY"},
        "price_data": {"current_price": 62000.0, "change_1y": 110.0},
    }
    crypto_analyzer = StockAnalyzer(crypto_data)
    crypto_debate = crypto_analyzer.analyze_bull_bear_debate()
    assert len(crypto_debate["bull_thesis"]) >= 2
    assert len(crypto_debate["bear_thesis"]) >= 2
    print("ETF and Crypto fallbacks test: PASSED")


def test_ui_and_api_contract():
    api_code = (ROOT / "api.py").read_text(encoding="utf-8")
    analyzer_code = (ROOT / "src" / "analyzer.py").read_text(encoding="utf-8")
    ui_code = (ROOT / "frontend" / "src" / "components" / "AnalysisResult.tsx").read_text(encoding="utf-8")
    debate_component = (ROOT / "frontend" / "src" / "components" / "BullBearDebate.tsx").read_text(encoding="utf-8")

    assert '"bull_bear_debate": bull_bear_debate' in analyzer_code
    assert '"bull_bear_debate": result.get("bull_bear_debate")' in api_code
    assert "import BullBearDebate" in ui_code
    assert "<BullBearDebate" in ui_code
    assert "Bull vs. Bear Duell" in debate_component
    assert "Zentrales Schlachtfeld" in debate_component
    print("UI and API contract test: PASSED")


def main():
    test_growth_stock_debate()
    test_distressed_stock_debate()
    test_etf_and_crypto_fallbacks()
    test_ui_and_api_contract()
    print("\nALL BULL-VS-BEAR DEBATE QA TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
