"""Evidence-gated Scalable portfolio decisions for read-only Telegram reports."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, Iterable, List


class ScalableDecisionService:
    """Combine a reconciled broker snapshot with paper-trading candidates.

    The output is research/paper guidance. It deliberately has no broker execution path.
    """

    SCHEMA = "scalable-telegram-decisions.v1"

    def build(
        self,
        portfolio_analysis: Dict[str, Any],
        paper_dashboard: Dict[str, Any],
        *,
        max_ideas: int = 3,
        now: datetime | None = None,
    ) -> Dict[str, Any]:
        current = now or datetime.now(timezone.utc)
        current = current.replace(tzinfo=timezone.utc) if current.tzinfo is None else current.astimezone(timezone.utc)
        generated_at = current.isoformat()
        summary = portfolio_analysis.get("summary") or {}
        holdings = [row for row in portfolio_analysis.get("holdings") or [] if isinstance(row, dict)]
        auto = paper_dashboard.get("auto_selection") or {}
        strict = self._unique_candidates(auto.get("selected") or [])
        learning = self._unique_candidates(
            [*(auto.get("exploration") or []), *(auto.get("aggressive_exploration") or [])]
        )
        research = self._research_candidates(
            paper_dashboard.get("playbooks") or [],
            self._number(auto.get("min_score")) or 88.0,
        )
        strict_by_ticker = {self._ticker(row): row for row in strict if self._ticker(row)}
        research_by_ticker = {self._ticker(row): row for row in research if self._ticker(row)}
        learning_by_ticker = {self._ticker(row): row for row in learning if self._ticker(row)}

        decisions: List[Dict[str, Any]] = []
        held_tickers: set[str] = set()
        for holding in holdings:
            ticker = self._ticker(holding)
            if ticker:
                held_tickers.add(ticker)
            candidate = strict_by_ticker.get(ticker)
            evidence_level = (
                "strict" if candidate else "research_strict" if ticker in research_by_ticker
                else "learning" if ticker in learning_by_ticker else "none"
            )
            candidate = candidate or research_by_ticker.get(ticker) or learning_by_ticker.get(ticker)
            decisions.append(self._holding_decision(holding, candidate, evidence_level, current))

        ideas: List[Dict[str, Any]] = []
        used_buckets: set[str] = set()
        for candidate in self._unique_candidates([*strict, *research]):
            ticker = self._ticker(candidate)
            if not ticker or ticker in held_tickers:
                continue
            bucket = str(candidate.get("risk_bucket") or ticker)
            if bucket in used_buckets:
                continue
            idea = self._idea(candidate)
            if not idea:
                continue
            ideas.append(idea)
            used_buckets.add(bucket)
            if len(ideas) >= max(1, int(max_ideas)):
                break

        material = {
            "decisions": [
                {
                    "ticker": row["ticker"],
                    "action": row["action"],
                    "execution_status": row.get("execution_status"),
                    "direction": row.get("direction"),
                    "trigger": row.get("trigger"),
                    "invalidation": row.get("invalidation"),
                }
                for row in decisions
            ],
            "ideas": [
                {
                    "ticker": row["ticker"],
                    "action": row["action"],
                    "direction": row.get("direction"),
                    "trigger": row.get("trigger"),
                    "invalidation": row.get("invalidation"),
                }
                for row in ideas
            ],
        }
        fingerprint = hashlib.sha256(
            json.dumps(material, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {
            "schema": self.SCHEMA,
            "status": "ok",
            "generated_at": generated_at,
            "portfolio_as_of": summary.get("as_of"),
            "currency": summary.get("currency") or "EUR",
            "portfolio_value": summary.get("total_value"),
            "portfolio_gain_loss_pct": summary.get("gain_loss_pct"),
            "decisions": decisions,
            "ideas": ideas,
            "counts": self._counts(decisions, ideas),
            "fingerprint": fingerprint,
            "source": "scalable_cli_reconciled_plus_paper_signal_engine",
            "scope": "research_and_paper_only",
            "automatic_broker_execution": False,
            "disclaimer": "Keine Orderausführung. Kauf-, Reduzierungs- und Verkaufssignale müssen manuell geprüft werden.",
        }

    def _holding_decision(
        self,
        holding: Dict[str, Any],
        candidate: Dict[str, Any] | None,
        evidence_level: str,
        now: datetime,
    ) -> Dict[str, Any]:
        ticker = self._ticker(holding)
        stale = holding.get("quote_is_outdated") is not False or not holding.get("quote_timestamp_utc")
        expected_weekend_close = stale and self._is_expected_weekend_close(
            ticker, holding.get("quote_timestamp_utc"), now
        )
        score = self._number((candidate or {}).get("score"))
        direction = str((candidate or {}).get("direction") or "").lower()
        strict_signal = evidence_level in {"strict", "research_strict"}
        if strict_signal and direction == "short" and score >= 92:
            action = "VERKAUFEN_PRUEFEN"
            reasons = ["Striktes negatives Paper-Setup mit hohem Score; Exit nur nach manueller Bestätigung."]
        elif strict_signal and direction == "short":
            action = "REDUZIEREN_PRUEFEN"
            reasons = ["Striktes negatives Paper-Setup; Positionsrisiko manuell prüfen."]
        elif evidence_level == "learning" and direction == "short":
            action = "HALTEN"
            reasons = ["Negatives Lernsignal ist noch nicht strikt bestätigt; beobachten, keine Depotaktion."]
        elif strict_signal and direction == "long" and score >= 90:
            action = "AUFSTOCKEN_PRUEFEN"
            reasons = ["Striktes positives Paper-Setup; Positionsgröße und Gesamtrisiko vor Kauf prüfen."]
        else:
            action = "HALTEN"
            reasons = ["Kein bestätigtes striktes Gegensignal; Verlust allein ist kein Verkaufsgrund."]
        if expected_weekend_close:
            execution_status = "MARKT_GESCHLOSSEN"
            execution_reason = "Letzter bestätigter Freitagsschlusskurs; Ausführung erst nach neuem Handelskurs prüfen."
        elif stale:
            execution_status = "KURS_VERALTET"
            execution_reason = "Brokerkurs fehlt oder ist veraltet; keine Ausführung zulässig."
        else:
            execution_status = "PRUEFBAR"
            execution_reason = "Brokerkurs ist aktuell; Trigger und Risiko müssen trotzdem manuell bestätigt werden."
        reasons.append(execution_reason)
        return {
            "ticker": ticker,
            "name": holding.get("name") or ticker,
            "position_value": self._number(holding.get("position_value")),
            "gain_loss_pct": self._number(holding.get("gain_loss_pct")),
            "action": action,
            "execution_status": execution_status,
            "actionable_now": action != "HALTEN" and execution_status == "PRUEFBAR",
            "score": score if candidate else None,
            "direction": direction or None,
            "setup_type": (candidate or {}).get("setup_type"),
            "evidence_level": evidence_level,
            "trigger": (candidate or {}).get("trigger"),
            "invalidation": (candidate or {}).get("invalidation"),
            "quote_timestamp_utc": holding.get("quote_timestamp_utc"),
            "quote_is_outdated": stale,
            "reasons": reasons,
        }

    def _idea(self, candidate: Dict[str, Any]) -> Dict[str, Any] | None:
        direction = str(candidate.get("direction") or "").lower()
        trigger = str(candidate.get("trigger") or "").strip()
        invalidation = str(candidate.get("invalidation") or "").strip()
        if direction not in {"long", "short"} or not trigger or not invalidation:
            return None
        return {
            "ticker": self._ticker(candidate),
            "asset_class": candidate.get("asset_class"),
            "direction": direction,
            "action": "KAUF_PRUEFEN" if direction == "long" else "SHORT_PRUEFEN",
            "execution_status": "LIVE_KURS_PRUEFEN",
            "actionable_now": False,
            "score": self._number(candidate.get("score")),
            "setup_type": candidate.get("setup_type"),
            "trigger": trigger,
            "invalidation": invalidation,
            "suggested_notional_value": self._number(candidate.get("suggested_notional_value")),
            "suggested_max_loss_value": self._number(candidate.get("suggested_max_loss_value")),
            "risk_bucket": candidate.get("risk_bucket"),
            "evidence_level": candidate.get("_research_evidence_level") or "strict",
        }

    @classmethod
    def _research_candidates(cls, rows: Iterable[Dict[str, Any]], min_score: float) -> List[Dict[str, Any]]:
        """Find strict research setups independently from Paper-account capacity gates."""
        candidates: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict) or str(row.get("asset_class") or "").lower() == "option":
                continue
            ticker = cls._ticker(row)
            direction = str(row.get("direction") or "").strip().lower()
            framework = row.get("decision_framework") if isinstance(row.get("decision_framework"), dict) else {}
            market = row.get("market_data") if isinstance(row.get("market_data"), dict) else {}
            if (
                not ticker or direction not in {"long", "short"}
                or cls._number(row.get("score")) < min_score
                or row.get("tradeable") is not True or bool(row.get("do_not_trade_reasons"))
                or cls._number(row.get("reference_price")) <= 0
                or str(market.get("freshness") or "").lower() != "fresh"
                or not row.get("data_as_of") or not str(row.get("thesis") or "").strip()
                or not str(framework.get("entry_trigger") or "").strip()
                or not str(framework.get("invalidation") or "").strip()
            ):
                continue
            candidates.append({
                **row,
                "trigger": framework.get("entry_trigger"),
                "invalidation": framework.get("invalidation"),
                "_research_evidence_level": "research_strict",
            })
        return cls._unique_candidates(candidates)

    @staticmethod
    def _unique_candidates(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        best: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            ticker = ScalableDecisionService._ticker(row)
            if not ticker:
                continue
            if ticker not in best or ScalableDecisionService._number(row.get("score")) > ScalableDecisionService._number(best[ticker].get("score")):
                best[ticker] = row
        return sorted(best.values(), key=lambda row: ScalableDecisionService._number(row.get("score")), reverse=True)

    @staticmethod
    def _counts(decisions: List[Dict[str, Any]], ideas: List[Dict[str, Any]]) -> Dict[str, int]:
        result: Dict[str, int] = {"positions": len(decisions), "ideas": len(ideas)}
        for row in decisions:
            key = str(row.get("action") or "UNKNOWN").lower()
            result[key] = result.get(key, 0) + 1
            execution_key = f"execution_{str(row.get('execution_status') or 'UNKNOWN').lower()}"
            result[execution_key] = result.get(execution_key, 0) + 1
        return result

    @staticmethod
    def _ticker(row: Dict[str, Any]) -> str:
        return str(row.get("ticker") or "").strip().upper()

    @staticmethod
    def _is_expected_weekend_close(ticker: str, quote_timestamp: Any, now: datetime) -> bool:
        if now.weekday() not in {5, 6} or ticker.endswith("-USD"):
            return False
        try:
            quote_at = datetime.fromisoformat(str(quote_timestamp).replace("Z", "+00:00"))
            if quote_at.tzinfo is None:
                quote_at = quote_at.replace(tzinfo=timezone.utc)
            quote_at = quote_at.astimezone(timezone.utc)
        except (TypeError, ValueError):
            return False
        age_seconds = (now - quote_at).total_seconds()
        return quote_at.weekday() == 4 and 0 <= age_seconds <= 72 * 3600

    @staticmethod
    def _number(value: Any) -> float:
        try:
            return round(float(value or 0), 2)
        except (TypeError, ValueError):
            return 0.0
