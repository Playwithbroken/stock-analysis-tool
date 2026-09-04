from types import MethodType

from src.morning_brief_service import MorningBriefService


def main() -> None:
    service = MorningBriefService.__new__(MorningBriefService)

    def collect_ready(self, tickers, label, fast=False):
        assert fast is True
        return {
            "label": label,
            "tone": "mixed",
            "avg_change_1d": 0.25,
            "assets": [{"ticker": tickers[0][0], "change_1d": 0.25}],
        }

    service._collect_region = MethodType(collect_ready, service)
    ready = service.get_regional_snapshot_fast()
    assert ready["quality"]["current"] is True
    assert ready["quality"]["missing_regions"] == []
    assert set(ready["regions"]) == {"asia", "europe", "usa"}

    def collect_partial(self, tickers, label, fast=False):
        region = collect_ready(self, tickers, label, fast)
        if label == "Asia":
            region["assets"] = []
            region["avg_change_1d"] = None
        return region

    service._collect_region = MethodType(collect_partial, service)
    partial = service.get_regional_snapshot_fast()
    assert partial["quality"]["current"] is False
    assert partial["quality"]["status"] == "partial"
    assert partial["quality"]["missing_regions"] == ["asia"]
    print("regional snapshot contract QA passed")


if __name__ == "__main__":
    main()
