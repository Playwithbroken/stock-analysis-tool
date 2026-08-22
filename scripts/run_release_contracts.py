import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_TESTS = [
    "qa_analyzer_resolution.py",
    "qa_global_asset_api.py",
    "qa_search_resolution.py",
    "qa_search_dynamic_suggestions.py",
    "qa_radar_bootstrap_resilience.py",
    "qa_discovery_resilience.py",
    "qa_auth_cookie_security.py",
    "qa_auth_lockout.py",
    "qa_health_center_contract.py",
    "qa_backup_endpoint.py",
    "qa_backup_restore_recovery.py",
    "qa_operational_alerts.py",
    "qa_security_headers.py",
    "qa_static_cache_headers.py",
    "qa_provider_states.py",
    "qa_accessibility_contract.py",
    "qa_advisory_profile.py",
    "qa_paper_demo_account.py",
    "qa_paper_learning_alerts.py",
    "qa_option_contract_alerts.py",
    "qa_tradier_option_provider.py",
    "qa_option_card_contract.py",
    "qa_leverage_end_to_end.py",
    "qa_execution_cost_calibration.py",
    "qa_paper_entry_market_regime.py",
    "qa_paper_diversification.py",
    "qa_news_evidence_schema.py",
    "qa_news_evidence_layers.py",
    "qa_news_trade_entry_gate.py",
    "qa_news_source_revalidation.py",
    "qa_telegram_deduplication.py",
    "qa_telegram_news_integrity.py",
    "qa_macro_alert_quality.py",
    "qa_session_market_movers.py",
    "qa_morning_brief_classification.py",
    "qa_morning_brief_numeric_integrity.py",
    "qa_daily_overview_scheduler.py",
    "qa_visual_viewport_contract.py",
    "qa_provider_observability.py",
    "qa_rollback_runbook.py",
    "qa_decision_scope_contract.py",
    "qa_decision_audit.py",
    "qa_compliance_release_gate.py",
    "qa_paper_evidence_campaign.py",
    "qa_capital_release_forecast.py",
    "qa_paper_period_performance.py",
]


def main() -> int:
    for relative_path in CONTRACT_TESTS:
        print(f"[release-contract] {relative_path}", flush=True)
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / relative_path)],
            cwd=PROJECT_ROOT,
            check=False,
        )
        if result.returncode != 0:
            print(f"[release-contract] FAILED: {relative_path}", file=sys.stderr)
            return result.returncode
    print(f"release contract QA passed ({len(CONTRACT_TESTS)} contracts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
