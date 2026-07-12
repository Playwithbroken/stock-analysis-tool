from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SKIP_PREFIXES = (
    ".git/",
    ".venv/",
    "frontend/dist/",
    "frontend/node_modules/",
    "frontend/package-lock.json",
    "node_modules/",
)

SKIP_SUFFIXES = (
    ".db",
    ".db-shm",
    ".db-wal",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
)

PLACEHOLDER_MARKERS = (
    "<",
    "$",
    "your-",
    "changeme",
    "change-me",
    "example",
    "placeholder",
    "local-",
    "test-",
    "dummy",
)

TELEGRAM_TOKEN_RE = re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b")
ENV_ASSIGN_RE = re.compile(
    r"\b(?P<name>APP_ACCESS_PASSWORD|APP_SESSION_SECRET|TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID)\b\s*=\s*[\"']?(?P<value>[^\"'\s#]+)"
)


def git_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def should_skip(path: str) -> bool:
    lower = path.lower()
    return lower.startswith(SKIP_PREFIXES) or lower.endswith(SKIP_SUFFIXES)


def looks_like_placeholder(value: str) -> bool:
    normalized = value.strip().strip("\"'").lower()
    return not normalized or normalized.startswith(PLACEHOLDER_MARKERS)


def scan_file(path: str) -> list[str]:
    full_path = ROOT / path
    try:
        text = full_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = full_path.read_text(encoding="utf-8", errors="ignore")

    findings: list[str] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if TELEGRAM_TOKEN_RE.search(line):
            findings.append(f"{path}:{line_no} contains a Telegram bot token pattern")

        for match in ENV_ASSIGN_RE.finditer(line):
            name = match.group("name")
            value = match.group("value")
            if looks_like_placeholder(value):
                continue
            if name == "TELEGRAM_CHAT_ID" and not value.isdigit():
                continue
            findings.append(f"{path}:{line_no} contains a concrete {name} value")

    return findings


def main() -> int:
    findings: list[str] = []
    for path in git_files():
        if should_skip(path):
            continue
        findings.extend(scan_file(path))

    if findings:
        print("[check-secrets] Refusing to continue. Concrete secrets were found in tracked files:", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        print("[check-secrets] Move real values to Railway/local env and keep only placeholders in Git.", file=sys.stderr)
        return 1

    print("[check-secrets] OK: no concrete app secrets found in tracked files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
