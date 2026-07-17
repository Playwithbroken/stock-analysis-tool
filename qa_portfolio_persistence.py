import os
import tempfile
from concurrent.futures import ThreadPoolExecutor


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "portfolios.db")
        os.environ["PORTFOLIO_DB_PATH"] = db_path

        from src.storage import PortfolioManager, get_database_status, init_db

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
        assert saved is not None, "holding was not saved"
        assert saved["ticker"] == "AAPL"
        assert saved["shares"] == 2
        assert saved["buyPrice"] == 150.25
        assert saved["purchaseDate"] == "2026-06-07"

        portfolios = manager.get_portfolios()
        loaded = next((item for item in portfolios if item["id"] == portfolio["id"]), None)
        assert loaded is not None, "portfolio did not persist"
        assert len(loaded["holdings"]) == 1, "holding did not persist"
        holding = loaded["holdings"][0]
        assert holding["ticker"] == "AAPL"
        assert holding["shares"] == 2
        assert holding["buyPrice"] == 150.25
        assert holding["purchaseDate"] == "2026-06-07"

        restarted_manager = PortfolioManager()
        restarted = next(
            (item for item in restarted_manager.get_portfolios() if item["id"] == portfolio["id"]),
            None,
        )
        assert restarted is not None, "portfolio did not survive manager restart"
        assert restarted["holdings"][0]["ticker"] == "AAPL"

        def create_concurrent_portfolio(index: int):
            created = manager.create_portfolio(f"Concurrent {index}")
            holding = manager.add_holding(created["id"], "HOOD", index + 1, buy_price=95 + index)
            return created, holding

        with ThreadPoolExecutor(max_workers=8) as executor:
            concurrent_results = list(executor.map(create_concurrent_portfolio, range(12)))
        assert len(concurrent_results) == 12
        assert all(holding and holding["ticker"] == "HOOD" for _, holding in concurrent_results)
        persisted_ids = {item["id"] for item in manager.get_portfolios()}
        assert all(created["id"] in persisted_ids for created, _ in concurrent_results)

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

        merged = manager.add_holding(
            portfolio["id"],
            "AAPL",
            1,
            buy_price=170,
            purchase_date="2026-06-10",
        )
        assert merged is not None, "merged holding was not returned"
        assert merged["shares"] == 4
        assert round(merged["buyPrice"], 4) == 159.125

        os.environ["RAILWAY_PROJECT_ID"] = "qa-project"
        os.environ["RAILWAY_VOLUME_NAME"] = "qa-volume"
        os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tmp
        volume_status = get_database_status()
        assert volume_status["volume_attached"] is True
        assert volume_status["database_on_volume"] is True
        assert volume_status["persistence_ready"] is True

        os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = os.path.join(tmp, "wrong-mount")
        wrong_mount_status = get_database_status()
        assert wrong_mount_status["volume_attached"] is True
        assert wrong_mount_status["database_on_volume"] is False
        assert wrong_mount_status["persistence_ready"] is False

        paper_trade = manager.create_paper_trade(
            {
                "ticker": "AAPL",
                "asset_class": "equity",
                "direction": "long",
                "setup_type": "qa_ticket",
                "entry_price": 100,
                "stop_price": 96,
                "target_price": 108,
                "quantity": 10,
                "trade_ticket": {
                    "schema_version": "1.0",
                    "ticket_id": "qa-ticket",
                    "paper_ready": True,
                    "real_money_ready": False,
                },
            }
        )
        persisted_trade = next(item for item in manager.list_paper_trades() if item["id"] == paper_trade["id"])
        assert persisted_trade["trade_ticket"]["ticket_id"] == "qa-ticket"
        assert persisted_trade["trade_ticket"]["real_money_ready"] is False

    print("portfolio persistence QA ok")


if __name__ == "__main__":
    main()
