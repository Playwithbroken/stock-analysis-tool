import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RUNNER = ROOT / "frontend" / "qa_smoke_playwright.mjs"
RUNBOOK = ROOT / "frontend" / "RELEASE_QA_RUNBOOK.md"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def test_exact_release_viewports():
    source = RUNNER.read_text(encoding="utf-8")
    pairs = re.findall(r'\{ name: "(\d+x\d+)", width: (\d+), height: (\d+) \}', source)
    actual = [(name, int(width), int(height)) for name, width, height in pairs]
    expected = [
        ("390x844", 390, 844),
        ("768x1024", 768, 1024),
        ("1366x768", 1366, 768),
        ("1920x1080", 1920, 1080),
    ]
    require(actual == expected, f"visual QA viewports differ: {actual!r}")


def test_each_surface_has_overflow_and_screenshot_gate():
    source = RUNNER.read_text(encoding="utf-8")
    require(
        'await checkHorizontalOverflow(page, `${viewportName}/${target.name}`);' in source,
        "each primary surface must receive an overflow check",
    )
    require(
        "await page.screenshot({ path: path.join(runDir, target.file), fullPage: true });" in source,
        "each primary surface must create a full-page artifact",
    )
    for surface in ("Analyzer", "Markets", "Portfolio", "Dashboard"):
        require(f'{{ name: "{surface}"' in source, f"missing visual surface: {surface}")


def test_runner_has_failure_telemetry_and_secure_auth_input():
    source = RUNNER.read_text(encoding="utf-8")
    for marker in (
        "horizontalOverflow",
        "requestFailedNonAborted",
        "http404",
        "http5xx",
        "pageerror",
        "summary.issues.length > 0",
        "QA_ACCESS_CODE is required",
    ):
        require(marker in source, f"visual gate missing contract marker: {marker}")
    require("<current-qa-access-code>" not in source, "runner must not contain a concrete access code")


def test_runbook_matches_automation():
    text = RUNBOOK.read_text(encoding="utf-8")
    for viewport in ("390x844", "768x1024", "1366x768", "1920x1080"):
        require(f"`{viewport}`" in text, f"runbook missing viewport {viewport}")
    require("qa-artifacts/<run-id>" in text, "runbook must document visual artifacts")


if __name__ == "__main__":
    test_exact_release_viewports()
    test_each_surface_has_overflow_and_screenshot_gate()
    test_runner_has_failure_telemetry_and_secure_auth_input()
    test_runbook_matches_automation()
    print("visual viewport contract QA passed (4 viewports, 4 primary surfaces)")
