from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent
COMPONENT = ROOT / "frontend" / "src" / "components" / "ProviderStatePanel.tsx"
APP = ROOT / "frontend" / "src" / "App.tsx"
DISCOVERY = ROOT / "frontend" / "src" / "components" / "DiscoveryPanel.tsx"
PORTFOLIO = ROOT / "frontend" / "src" / "components" / "PortfolioView.tsx"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_shared_provider_state_contract() -> None:
    source = COMPONENT.read_text(encoding="utf-8")
    for state in ("loading", "slow", "empty", "error", "degraded"):
        require(f"{state}:" in source, f"shared provider component missing state {state!r}")
    for marker in (
        "data-provider-state={state}",
        "useSlowProviderState",
        "aria-live=",
        'role={state === "error" ? "alert" : "status"}',
        "onRetry",
        "Erneut laden",
        "overflow-wrap:anywhere",
    ):
        require(marker in source, f"shared provider state contract missing {marker!r}")
    require("title=" not in source, "critical provider state information must not rely on hover")


def test_all_main_views_expose_explicit_states_and_retry() -> None:
    app = APP.read_text(encoding="utf-8")
    discovery = DISCOVERY.read_text(encoding="utf-8")
    portfolio = PORTFOLIO.read_text(encoding="utf-8")

    for view in ("dashboard-map", "dashboard-brief", "analyzer", "portfolio"):
        require(f'view="{view}"' in app, f"App main view missing provider state {view!r}")
    require("globalBriefSlow" in app, "dashboard must distinguish slow from initial loading")
    require('globalBriefStatus === "ready"' in app and '? "empty"' in app, "dashboard must distinguish a valid empty region response")
    require("Analyse erneut starten" in app, "analyzer errors need a scoped retry")
    require("Server erneut prüfen" in app, "portfolio fallback needs a server retry")

    require('view="markets"' in discovery, "Markets must expose a provider state")
    require("primaryFailureCount" in discovery, "Markets must distinguish partial provider failure")
    require("primaryDataEmpty" in discovery, "Markets must distinguish a valid empty response")
    require("providerSlow" in discovery, "Markets must distinguish slow loading")
    require("setProviderReloadTick" in discovery, "Markets must expose scoped retry")

    require('view="paper-trader"' in portfolio, "Paper Trader must expose a provider state")
    require("paperDashboardSlow" in portfolio, "Paper Trader must distinguish slow loading")
    require("paperDashboardError" in portfolio, "Paper Trader must distinguish provider error")
    require("Paper-Daten neu laden" in portfolio, "Paper Trader must expose scoped retry")


def main() -> int:
    tests = [test_shared_provider_state_contract, test_all_main_views_expose_explicit_states_and_retry]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"provider state QA ok: {len(tests)} contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
