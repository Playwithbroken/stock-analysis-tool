"""Consistent SQLite backups and non-destructive restore verification."""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class DatabaseBackupService:
    def __init__(self, database_path: str):
        self.database_path = Path(database_path).resolve()
        configured_dir = os.getenv("APP_BACKUP_DIR", "").strip()
        self.backup_dir = (
            Path(configured_dir).resolve()
            if configured_dir
            else (self.database_path.parent / "backups").resolve()
        )

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _safe_int(name: str, default: int, minimum: int = 1) -> int:
        try:
            return max(minimum, int(os.getenv(name, str(default))))
        except (TypeError, ValueError):
            return default

    def _backup_files(self) -> list[Path]:
        if not self.backup_dir.is_dir():
            return []
        return sorted(
            (
                path
                for path in self.backup_dir.glob("broker-freund-portfolio-backup-*.db")
                if path.is_file() and path.parent.resolve() == self.backup_dir
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

    @staticmethod
    def _database_snapshot(path: Path) -> Dict[str, Any]:
        connection = sqlite3.connect(str(path), timeout=10)
        try:
            quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
            tables = [
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                ).fetchall()
            ]
            counts = {}
            for table in tables:
                safe_table = table.replace('"', '""')
                counts[table] = int(connection.execute(f'SELECT COUNT(*) FROM "{safe_table}"').fetchone()[0])
            identity_row = connection.execute(
                "SELECT value FROM app_settings WHERE key='database_identity'"
            ).fetchone() if "app_settings" in tables else None
            return {
                "quick_check": quick_check,
                "tables": tables,
                "counts": counts,
                "identity": identity_row[0] if identity_row else None,
            }
        finally:
            connection.close()

    def create_backup(self) -> Dict[str, Any]:
        if not self.database_path.is_file():
            raise FileNotFoundError(f"Database not found: {self.database_path}")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = self._utc_now().strftime("%Y%m%d-%H%M%S-%f")
        final_path = self.backup_dir / f"broker-freund-portfolio-backup-{stamp}.db"
        temporary_path = self.backup_dir / f".{final_path.name}.tmp"
        source = None
        target = None
        try:
            source = sqlite3.connect(str(self.database_path), timeout=10)
            target = sqlite3.connect(str(temporary_path), timeout=10)
            source.backup(target)
            target.commit()
            target.close()
            target = None
            source.close()
            source = None
            snapshot = self._database_snapshot(temporary_path)
            if snapshot["quick_check"] != "ok":
                raise RuntimeError(f"Backup integrity check failed: {snapshot['quick_check']}")
            os.replace(temporary_path, final_path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        finally:
            if target is not None:
                target.close()
            if source is not None:
                source.close()
        removed = self._apply_retention(exclude=final_path)
        return {
            "status": "ok",
            "created_at": self._utc_now().isoformat(),
            "path": str(final_path),
            "filename": final_path.name,
            "size_bytes": final_path.stat().st_size,
            "quick_check": snapshot["quick_check"],
            "table_count": len(snapshot["tables"]),
            "counts": snapshot["counts"],
            "removed_by_retention": removed,
        }

    def _apply_retention(self, exclude: Path) -> list[str]:
        keep = self._safe_int("APP_BACKUP_RETENTION_COUNT", 14, minimum=2)
        removed: list[str] = []
        files = [path for path in self._backup_files() if path != exclude]
        for path in files[max(0, keep - 1):]:
            if path.parent.resolve() != self.backup_dir or not path.name.startswith("broker-freund-portfolio-backup-"):
                continue
            path.unlink()
            removed.append(path.name)
        return removed

    def verify_restore(self, backup_path: str | Path | None = None) -> Dict[str, Any]:
        selected = Path(backup_path).resolve() if backup_path else next(iter(self._backup_files()), None)
        if selected is None or not selected.is_file() or selected.parent.resolve() != self.backup_dir:
            raise FileNotFoundError("No valid managed backup found for restore verification.")
        expected = self._database_snapshot(selected)
        with tempfile.TemporaryDirectory(prefix="broker-freund-restore-") as temp_dir:
            restored_path = Path(temp_dir) / "restored-empty-instance.db"
            shutil.copy2(selected, restored_path)
            restored = self._database_snapshot(restored_path)
        matching = (
            expected["quick_check"] == "ok"
            and restored["quick_check"] == "ok"
            and expected["identity"] == restored["identity"]
            and expected["tables"] == restored["tables"]
            and expected["counts"] == restored["counts"]
        )
        if not matching:
            raise RuntimeError("Restore verification did not reproduce schema, identity and row counts.")
        return {
            "status": "ok",
            "verified_at": self._utc_now().isoformat(),
            "backup_path": str(selected),
            "filename": selected.name,
            "quick_check": restored["quick_check"],
            "database_identity": restored["identity"],
            "table_count": len(restored["tables"]),
            "counts": restored["counts"],
            "temporary_restore_removed": True,
        }

    def status(self) -> Dict[str, Any]:
        files = self._backup_files()
        latest = files[0] if files else None
        age_hours = None
        if latest:
            age_hours = max(0.0, (self._utc_now().timestamp() - latest.stat().st_mtime) / 3600)
        return {
            "enabled": os.getenv("APP_DAILY_BACKUP_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"},
            "directory": str(self.backup_dir),
            "directory_exists": self.backup_dir.is_dir(),
            "writable": os.access(self.backup_dir, os.W_OK) if self.backup_dir.is_dir() else os.access(self.backup_dir.parent, os.W_OK),
            "backup_count": len(files),
            "latest_path": str(latest) if latest else None,
            "latest_filename": latest.name if latest else None,
            "latest_at": datetime.fromtimestamp(latest.stat().st_mtime, timezone.utc).isoformat() if latest else None,
            "latest_age_hours": round(age_hours, 2) if age_hours is not None else None,
            "retention_count": self._safe_int("APP_BACKUP_RETENTION_COUNT", 14, minimum=2),
        }
