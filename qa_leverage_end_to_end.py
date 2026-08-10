from qa_paper_demo_account import FakePortfolioManager, build_service, sample_scoreboard, sample_settings


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def provider_product(multiplier=1.0):
    return {
        "product_type": "knockout",
        "issuer": "QA Bank",
        "strike_or_knockout_level": 205.0,
        "expiry": "2030-01-17",
        "bid": 4.80,
        "ask": 4.95,
        "offered_leverage": 20,
        "contract_multiplier": multiplier,
        "distance_to_knockout_pct": 8.0,
        "overnight_risk_ack": True,
    }


def test_synthetic_equity_leverage_is_applied_exactly_once():
    manager = FakePortfolioManager()
    service = build_service(manager)
    trade = service.create_trade_from_playbook(
        {"playbook_id": "equity-AAPL-long", "direction": "long", "quantity": 0, "leverage": 2},
        sample_scoreboard(),
        sample_settings(),
    )
    require(trade["leverage"] == 2, "selected equity leverage must persist")
    require(trade["contract_multiplier"] == 1, "equity must retain unit multiplier")
    require(trade["trade_ticket"]["leverage_calculation"]["pnl_leverage_multiplier"] == 2, "ticket must audit one equity leverage application")
    expected_invested = round(trade["entry_price"] * trade["quantity"] * 2, 2)
    require(trade["invested_value"] == expected_invested, "equity exposure must apply leverage once")
    closed = service.close_trade(trade["id"], closed_price=105.0)
    expected_pnl = round(
        (closed["closed_price"] - trade["entry_price"]) * trade["quantity"] * 2,
        2,
    )
    require(closed["realized_pnl_value"] == expected_pnl, "equity exit P&L must apply leverage once")
    require(
        closed["realized_pnl_pct"]
        == service._calc_return_pct(trade["entry_price"], closed["closed_price"], 1, 2),
        "equity return percentage must apply leverage once",
    )


def test_provider_product_uses_quote_multiplier_and_never_reapplies_embedded_leverage():
    manager = FakePortfolioManager()
    service = build_service(manager)
    trade = service.create_trade_from_playbook(
        {
            "playbook_id": "commodity-option-GLD-call",
            "direction": "call",
            "quantity": 0,
            "leverage": 1,
            "product_data": provider_product(multiplier=0.1),
        },
        sample_scoreboard(),
        sample_settings(),
    )
    require(trade["leverage"] == 20, "provider-offered leverage must persist")
    require(trade["contract_multiplier"] == 0.1, "provider product ratio must replace option default 100")
    require(trade["trade_ticket"]["contract_multiplier"] == 0.1, "ticket must audit the product ratio")
    require(trade["trade_ticket"]["leverage_calculation"]["pnl_leverage_multiplier"] == 1, "ticket must block a second provider leverage application")
    require(
        trade["trade_ticket"]["leveraged_product"]["leverage_is_embedded_in_product_price"] is True,
        "provider leverage must be classified as embedded",
    )
    expected_invested = round(trade["entry_price"] * trade["quantity"] * 0.1, 2)
    require(trade["invested_value"] == expected_invested, "provider exposure must exclude a second 20x multiplier")
    closed = service.close_trade(trade["id"], closed_price=5.50)
    expected_pnl = round(
        (closed["closed_price"] - trade["entry_price"]) * trade["quantity"] * 0.1,
        2,
    )
    require(closed["realized_pnl_value"] == expected_pnl, "provider P&L must use price move and product ratio only")
    require(
        closed["realized_pnl_pct"]
        == service._calc_return_pct(trade["entry_price"], closed["closed_price"], 1, 1),
        "embedded provider leverage must not multiply return percentage again",
    )


def test_provider_leverage_and_multiplier_cannot_be_invented_or_overridden():
    service = build_service(FakePortfolioManager())
    missing_multiplier = provider_product()
    missing_multiplier.pop("contract_multiplier")
    validation = service.validate_leverage_product_data(missing_multiplier)
    require(validation["valid"] is False, "missing provider multiplier must block product")
    require("contract_multiplier_missing_or_invalid" in validation["errors"], "missing multiplier needs an explicit error")

    try:
        service.create_trade_from_playbook(
            {
                "playbook_id": "commodity-option-GLD-call",
                "direction": "call",
                "quantity": 0,
                "leverage": 10,
                "product_data": provider_product(),
            },
            sample_scoreboard(),
            sample_settings(),
        )
    except ValueError as exc:
        require("must exactly match" in str(exc), "provider mismatch must explain the fixed offered leverage")
    else:
        raise AssertionError("provider product accepted an invented leverage override")


def test_standard_option_keeps_contract_100_without_separate_leverage_multiplier():
    service = build_service(FakePortfolioManager())
    trade = service.create_trade_from_playbook(
        {"playbook_id": "option-AAPL-call", "direction": "call", "quantity": 0, "leverage": 1},
        sample_scoreboard(),
        sample_settings(),
    )
    require(trade["contract_multiplier"] == 100, "standard listed option must retain its contract multiplier")
    require(trade["leverage"] == 1, "option premium model must not add a second leverage field")
    require(
        trade["invested_value"] == round(trade["entry_price"] * trade["quantity"] * 100, 2),
        "listed option premium exposure must use contract multiplier exactly once",
    )


def main():
    tests = [
        test_synthetic_equity_leverage_is_applied_exactly_once,
        test_provider_product_uses_quote_multiplier_and_never_reapplies_embedded_leverage,
        test_provider_leverage_and_multiplier_cannot_be_invented_or_overridden,
        test_standard_option_keeps_contract_100_without_separate_leverage_multiplier,
    ]
    for test in tests:
        test()
    print(f"leverage end-to-end QA passed ({len(tests)} contracts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
