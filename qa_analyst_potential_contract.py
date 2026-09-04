"""Regression contract for analyst target/upside data between backend and UI."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main() -> None:
    fetcher = (ROOT / "src" / "data_fetcher.py").read_text(encoding="utf-8")
    ui = (ROOT / "frontend" / "src" / "components" / "AnalysisResult.tsx").read_text(encoding="utf-8")
    assert '"target_mean": info.get("targetMeanPrice")' in fetcher
    assert '"target_mean_price": info.get("targetMeanPrice")' in fetcher
    assert "analystData?.target_mean ?? analystData?.target_mean_price" in ui
    assert "currentPrice > 0 && targetMeanPrice > 0" in ui
    print("Analyst potential API/UI contract: OK")


if __name__ == "__main__":
    main()
