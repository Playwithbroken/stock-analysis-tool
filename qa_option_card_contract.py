from pathlib import Path


ROOT = Path(__file__).resolve().parent
PANEL = ROOT / "frontend" / "src" / "components" / "PaperTradingPanel.tsx"


def main() -> int:
    source = PANEL.read_text(encoding="utf-8")
    failures: list[str] = []
    required_contract_fields = [
        "contract_symbol",
        "option_type",
        "strike",
        "expiry",
        "days_to_expiry",
        "underlying_price",
        "bid",
        "ask",
        "spread_pct",
        "implied_volatility_pct",
        "volume",
        "open_interest",
        "moneyness_pct",
        "break_even",
        "distance_to_break_even_pct",
        "max_loss_per_contract",
        "quote_quality",
        "selection_basis",
        "data_as_of",
    ]
    required_copy = [
        "Konkreter Optionskontrakt",
        "Delayed Research · nicht ausführbar",
        "Optionsdaten nicht verifizierbar",
        "Die angezeigte Prämie ist nur eine Schätzung und keine ausführbare Quote.",
        "keine verifizierte Broker-Ausführungsquote",
        "Greeks nicht verifiziert",
        'data-testid="option-contract-evidence"',
        "<OptionContractEvidence item={item} />",
    ]
    for field in required_contract_fields:
        if f"contract.{field}" not in source:
            failures.append(f"option card does not render contract.{field}")
    for text in required_copy:
        if text not in source:
            failures.append(f"option card missing required copy/marker: {text}")
    if 'contract.status === "available"' not in source:
        failures.append("option card has no explicit available/unavailable branch")
    if 'String(item?.asset_class || "").toLowerCase() !== "option"' not in source:
        failures.append("option evidence is not scoped to option playbooks")

    if failures:
        print("Option card contract QA failures:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"option card contract QA ok ({len(required_contract_fields)} fields)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
