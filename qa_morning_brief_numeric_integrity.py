import json
import math
import tempfile
from pathlib import Path

from src.morning_brief_service import MorningBriefService


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main() -> int:
    service = MorningBriefService.__new__(MorningBriefService)

    require(
        service._estimate_change_1d({"change_1d": float("nan"), "change_1w": 5.0}) is None,
        "missing 1-day return must not be invented from a weekly return",
    )
    require(
        service._estimate_change_1d({"change_1d": float("inf")}) is None,
        "infinite 1-day return must be rejected",
    )

    service._collect_assets = lambda tickers, fast=False: [
        {"ticker": "BAD", "change_1d": float("nan")},
        {"ticker": "GOOD", "change_1d": 1.25},
    ]
    region = service._collect_region([], "Asia")
    require(region["avg_change_1d"] == 1.25, "regional average must exclude non-finite values")

    service._collect_assets = lambda tickers, fast=False: [{"ticker": "BAD", "change_1d": float("nan")}]
    unavailable = service._collect_region([], "Asia")
    require(unavailable["avg_change_1d"] is None, "missing regional data must stay null")
    require(unavailable["tone"] == "unavailable", "missing regional data must be explicit")

    line = service._region_summary_line("Asia", unavailable)
    require("data unavailable" in line and "nan" not in line.lower(), "narrative must explain missing data")
    narrative = service._build_narrative(
        unavailable,
        {"label": "Europe", "tone": "mixed", "avg_change_1d": 0.2, "assets": []},
        {"label": "USA", "tone": "risk-on", "avg_change_1d": 0.6, "assets": []},
        [],
        [],
    )
    require(
        "data unavailable" in narrative["summary_points"][0],
        "complete narrative must preserve the explicit regional data gap",
    )

    payload = service._sanitize_non_finite(
        {"nan": float("nan"), "positive_inf": float("inf"), "nested": [1.0, -float("inf")]}
    )
    encoded = json.dumps(payload, allow_nan=False)
    require("NaN" not in encoded and "Infinity" not in encoded, "JSON output must contain no non-finite tokens")
    require(payload == {"nan": None, "positive_inf": None, "nested": [1.0, None]}, "sanitizer mismatch")

    with tempfile.TemporaryDirectory() as temp_dir:
        service._snapshot_path = str(Path(temp_dir) / "brief.json")
        service._persist_snapshot({"regions": {"asia": unavailable}, "bad": float("nan")})
        raw = Path(service._snapshot_path).read_text(encoding="utf-8")
        restored = json.loads(raw)
        require(restored["bad"] is None, "persisted snapshot must use JSON null")
        require(not any(token in raw for token in ("NaN", "Infinity")), "snapshot contains invalid JSON numbers")

    print("morning brief numeric integrity QA ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
