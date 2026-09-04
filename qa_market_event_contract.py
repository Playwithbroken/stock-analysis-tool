from __future__ import annotations

from datetime import datetime, timezone

from src.integrations.contracts import (
    BrokerOrderEvent,
    EventQuality,
    MarketEvent,
    NewsEvent,
    canonical_json,
    payload_sha256,
)


NOW = "2026-08-27T12:00:00+00:00"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sample_market_event(**overrides) -> MarketEvent:
    values = {
        "event_id": "Q.AAPL.0001",
        "event_type": "quote",
        "provider": "Alpaca",
        "feed": "IEX",
        "asset_class": "equity",
        "symbol": "aapl",
        "exchange": "NASDAQ",
        "provider_timestamp": NOW,
        "received_at": "2026-08-27T12:00:00.100+00:00",
        "normalized_at": "2026-08-27T12:00:00.110+00:00",
        "sequence": 10,
        "bid": 230.10,
        "ask": 230.12,
        "last": 230.11,
        "size": 100,
    }
    values.update(overrides)
    return MarketEvent(**values)


def test_market_contract_normalizes_without_inventing_time() -> None:
    event = sample_market_event()
    require(event.provider == "alpaca" and event.feed == "iex", "provider/feed must normalize")
    require(event.symbol == "AAPL", "symbol must normalize")
    require(event.event_id == "Q.AAPL.0001", "provider-native event IDs must retain case")
    require(event.provider_timestamp == NOW, "provider timestamp must be retained in UTC")
    require(event.schema_version == "market-event.v1", "schema version must be explicit")


def test_market_contract_rejects_unsafe_or_ambiguous_data() -> None:
    bad_cases = (
        {"provider_timestamp": "2026-08-27T12:00:00"},
        {"event_type": "prediction"},
        {"bid": 231.0, "ask": 230.0},
        {"last": float("nan")},
    )
    for overrides in bad_cases:
        try:
            sample_market_event(**overrides)
        except ValueError:
            continue
        raise AssertionError(f"invalid market event accepted: {overrides}")

    crossed = sample_market_event(
        bid=231.0,
        ask=230.0,
        quality=EventQuality(crossed_market=True, reasons=("provider_crossed_quote",)),
    )
    require(crossed.quality.crossed_market, "explicit crossed-market evidence must be retained")


def test_payload_hash_is_canonical() -> None:
    left = {"symbol": "AAPL", "price": 230.1, "nested": {"b": 2, "a": 1}}
    right = {"nested": {"a": 1, "b": 2}, "price": 230.1, "symbol": "AAPL"}
    require(canonical_json(left) == canonical_json(right), "canonical JSON must ignore key order")
    require(payload_sha256(left) == payload_sha256(right), "payload hash must be reproducible")


def test_news_and_broker_contracts_are_evidence_safe() -> None:
    news = NewsEvent(
        event_id="news-1",
        provider="Alpaca",
        publisher="Example Wire",
        headline="Issuer publishes results",
        source_url="https://example.com/results",
        published_at=NOW,
        received_at=NOW,
        normalized_at=NOW,
        symbols=("aapl", "AAPL"),
    )
    require(news.symbols == ("AAPL",), "news symbols must be normalized and deduplicated")
    url_optional = NewsEvent.from_dict({**news.to_dict(), "event_id": "news-2", "source_url": ""})
    require(url_optional.source_url == "", "provider news without an optional URL must remain honest")

    paper_event = BrokerOrderEvent(
        event_id="fill-1",
        provider="alpaca",
        client_order_id="Client-ABC",
        broker_order_id="Broker-XYZ",
        event_type="filled",
        account_mode="paper",
        symbol="aapl",
        provider_timestamp=NOW,
        received_at=NOW,
        filled_quantity=1,
        fill_price=230.12,
    )
    require(paper_event.account_mode == "paper", "paper broker event must be explicit")
    require(paper_event.client_order_id == "Client-ABC", "order IDs must retain provider casing")
    try:
        BrokerOrderEvent(**{**paper_event.to_dict(), "account_mode": "live"})
    except ValueError:
        pass
    else:
        raise AssertionError("live broker event must be rejected by the paper contract")


if __name__ == "__main__":
    test_market_contract_normalizes_without_inventing_time()
    test_market_contract_rejects_unsafe_or_ambiguous_data()
    test_payload_hash_is_canonical()
    test_news_and_broker_contracts_are_evidence_safe()
    print("market event contract QA passed")
