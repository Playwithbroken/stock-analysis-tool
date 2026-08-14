from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend" / "src"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def luminance(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    channels = [int(value[index:index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(foreground: str, background: str) -> float:
    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def test_global_keyboard_and_motion_contract() -> None:
    app = (FRONTEND / "App.tsx").read_text(encoding="utf-8")
    css = (FRONTEND / "index.css").read_text(encoding="utf-8")
    for marker in (
        'href="#main-content"',
        'className="skip-link"',
        'id="main-content"',
        "tabIndex={-1}",
        'aria-current={activeTab === item.id ? "page" : undefined}',
    ):
        require(marker in app, f"main navigation accessibility contract missing {marker!r}")
    for marker in (":focus-visible", ".skip-link:focus-visible", "prefers-reduced-motion: reduce"):
        require(marker in css, f"global accessibility CSS missing {marker!r}")


def test_dialog_focus_and_screenreader_contract() -> None:
    hook = (FRONTEND / "hooks" / "useAccessibleDialog.ts").read_text(encoding="utf-8")
    for marker in (
        'event.key === "Escape"',
        'event.key !== "Tab"',
        "previousFocus?.focus()",
        'document.body.style.overflow = "hidden"',
        "FOCUSABLE_SELECTOR",
    ):
        require(marker in hook, f"dialog focus contract missing {marker!r}")

    files = {
        "app": FRONTEND / "App.tsx",
        "health": FRONTEND / "components" / "AdminHealthPanel.tsx",
        "holding": FRONTEND / "components" / "AddHoldingModal.tsx",
        "onboarding": FRONTEND / "components" / "OnboardingWizard.tsx",
        "portfolio": FRONTEND / "components" / "PortfolioView.tsx",
        "analysis": FRONTEND / "components" / "AnalysisResult.tsx",
    }
    for name, path in files.items():
        source = path.read_text(encoding="utf-8")
        require('role="dialog"' in source, f"{name} modal needs dialog semantics")
        require('aria-modal="true"' in source, f"{name} modal needs aria-modal")
        require("aria-labelledby=" in source, f"{name} modal needs an accessible title")
        require("useAccessibleDialog" in source, f"{name} modal needs focus trapping and restoration")


def test_state_controls_and_contrast_contract() -> None:
    app = (FRONTEND / "App.tsx").read_text(encoding="utf-8")
    discovery = (FRONTEND / "components" / "DiscoveryPanel.tsx").read_text(encoding="utf-8")
    provider = (FRONTEND / "components" / "ProviderStatePanel.tsx").read_text(encoding="utf-8")
    require("aria-pressed={marketMoversWindow === window}" in app, "market window control needs pressed state")
    require('role="tablist"' in discovery and 'role="tab"' in discovery, "Markets tabs need tab semantics")
    require("aria-selected={activeTab === tab.id}" in discovery, "Markets tabs need selected state")
    require('role={state === "error" ? "alert" : "status"}' in provider, "provider states need live semantics")

    text_pairs = (
        ("#121821", "#faf8f3", 4.5, "primary text"),
        ("#49505a", "#faf8f3", 4.5, "secondary text"),
        ("#0f766e", "#ffffff", 4.5, "accent text"),
        ("#b42318", "#ffffff", 4.5, "danger text"),
        ("#b54708", "#ffffff", 4.5, "warning text"),
    )
    for foreground, background, minimum, label in text_pairs:
        ratio = contrast(foreground, background)
        require(ratio >= minimum, f"{label} contrast {ratio:.2f} is below {minimum}")


def main() -> int:
    tests = [
        test_global_keyboard_and_motion_contract,
        test_dialog_focus_and_screenreader_contract,
        test_state_controls_and_contrast_contract,
    ]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"accessibility QA ok: {len(tests)} contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
