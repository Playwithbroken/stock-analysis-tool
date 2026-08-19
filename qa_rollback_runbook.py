import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main() -> int:
    failures: list[str] = []
    target = json.loads((ROOT / "rollback" / "last-known-good.json").read_text(encoding="utf-8"))
    runbook = (ROOT / "ROLLBACK_RUNBOOK.md").read_text(encoding="utf-8")
    for phrase in ["/app/data/portfolios.db", "quick_check", "600 Sekunden", "qa_live_release_smoke.py"]:
        if phrase not in runbook:
            failures.append(f"runbook missing required contract: {phrase}")
    if target.get("schema") != "rollback-target.v1":
        failures.append("rollback target schema is invalid")
    if not target.get("commit") or target.get("production_rto_seconds") != 600:
        failures.append("rollback target commit or RTO is invalid")

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_rollback_drill.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        failures.append(f"rollback drill failed: {result.stderr or result.stdout}")
    else:
        try:
            report = json.loads(result.stdout)
            for field in ["database_compatible", "identity_preserved", "tables_preserved", "row_counts_preserved", "within_rto", "temporary_environment_removed"]:
                if report.get(field) is not True:
                    failures.append(f"rollback report did not confirm {field}")
            if report.get("production_mutated") is not False:
                failures.append("rollback drill must be non-destructive")
        except json.JSONDecodeError as exc:
            failures.append(f"rollback report is not valid JSON: {exc}")

    if failures:
        print("Rollback runbook QA failures:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("rollback runbook QA ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
