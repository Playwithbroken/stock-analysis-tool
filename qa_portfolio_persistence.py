import os
import tempfile


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "portfolios.db")
        os.environ["PORTFOLIO_DB_PATH"] = db_path

        from src.storage import PortfolioManager, init_db

        init_db()
        manager = PortfolioManager()
        portfolio = manager.create_portfolio("QA Portfolio")
        assert portfolio["id"], "portfolio id missing"
        assert portfolio["name"] == "QA Portfolio"

        saved = manager.add_holding(
            portfolio["id"],
            "aapl",
            2,
            buy_price=150.25,
            purchase_date="2026-06-07",
        )
        assert saved is True, "holding was not saved"

        portfolios = manager.get_portfolios()
        loaded = next((item for item in portfolios if item["id"] == portfolio["id"]), None)
        assert loaded is not None, "portfolio did not persist"
        assert len(loaded["holdings"]) == 1, "holding did not persist"
        holding = loaded["holdings"][0]
        assert holding["ticker"] == "AAPL"
        assert holding["shares"] == 2
        assert holding["buyPrice"] == 150.25
        assert holding["purchaseDate"] == "2026-06-07"

        updated = manager.update_holding(
            portfolio["id"],
            "AAPL",
            shares=3,
            buy_price=155.5,
            purchase_date="2026-06-08",
        )
        assert updated is not None, "holding update failed"
        assert updated["shares"] == 3
        assert updated["buyPrice"] == 155.5
        assert updated["purchaseDate"] == "2026-06-08"

    print("portfolio persistence QA ok")


if __name__ == "__main__":
    main()
