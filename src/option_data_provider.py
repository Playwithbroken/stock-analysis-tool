from __future__ import annotations

import os
import time
from typing import Any, Dict, List

import requests

from src.provider_observability import classify_provider_error, record_provider_result


class TradierOptionDataProvider:
    """Read-only Tradier market-data client. It never exposes an order endpoint."""

    PRODUCTION_BASE_URL = "https://api.tradier.com/v1"
    SANDBOX_BASE_URL = "https://sandbox.tradier.com/v1"

    def __init__(self, access_token: str, environment: str = "production") -> None:
        normalized_environment = str(environment or "production").strip().lower()
        if normalized_environment not in {"production", "sandbox"}:
            normalized_environment = "production"
        self.access_token = str(access_token or "").strip()
        self.environment = normalized_environment
        self.base_url = (
            self.PRODUCTION_BASE_URL
            if normalized_environment == "production"
            else self.SANDBOX_BASE_URL
        )

    @classmethod
    def from_env(cls) -> "TradierOptionDataProvider":
        return cls(
            os.getenv("TRADIER_ACCESS_TOKEN", ""),
            os.getenv("TRADIER_ENVIRONMENT", "production"),
        )

    @property
    def configured(self) -> bool:
        return bool(self.access_token)

    @property
    def realtime(self) -> bool:
        return self.configured and self.environment == "production"

    def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        started = time.perf_counter()
        operation = path.rsplit("/", 1)[-1] or "request"
        if not self.configured:
            error = RuntimeError("tradier_access_token_not_configured")
            record_provider_result(
                "options",
                "tradier",
                operation,
                "disabled",
                latency_ms=(time.perf_counter() - started) * 1000,
                error_code=classify_provider_error("options", error=error),
                error_type=error.__class__.__name__,
            )
            raise error
        try:
            timeout = max(2.0, min(30.0, float(os.getenv("TRADIER_TIMEOUT_SECONDS", "8"))))
        except (TypeError, ValueError):
            timeout = 8.0
        response = None
        try:
            response = requests.get(
                f"{self.base_url}{path}",
                params=params,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Accept": "application/json",
                    "User-Agent": "BrokerFreund-OptionsResearch/1.0",
                },
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("tradier_response_not_object")
            record_provider_result(
                "options",
                "tradier",
                operation,
                "ok",
                latency_ms=(time.perf_counter() - started) * 1000,
                http_status=response.status_code,
            )
            return payload
        except Exception as exc:
            http_status = response.status_code if response is not None else None
            record_provider_result(
                "options",
                "tradier",
                operation,
                "error",
                latency_ms=(time.perf_counter() - started) * 1000,
                error_code=classify_provider_error(
                    "options", error=exc, http_status=http_status
                ),
                http_status=http_status,
                error_type=exc.__class__.__name__,
            )
            raise

    @staticmethod
    def _as_list(value: Any) -> List[Any]:
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    def get_expirations(self, symbol: str) -> List[str]:
        payload = self._get(
            "/markets/options/expirations",
            {"symbol": str(symbol).upper(), "includeAllRoots": "false"},
        )
        expirations = payload.get("expirations") or {}
        values = expirations.get("date") if isinstance(expirations, dict) else None
        return [str(value) for value in self._as_list(values) if value]

    def get_chain(self, symbol: str, expiration: str) -> List[Dict[str, Any]]:
        payload = self._get(
            "/markets/options/chains",
            {
                "symbol": str(symbol).upper(),
                "expiration": str(expiration),
                "greeks": "true",
            },
        )
        options = payload.get("options") or {}
        values = options.get("option") if isinstance(options, dict) else None
        return [value for value in self._as_list(values) if isinstance(value, dict)]

    def get_quote(self, option_symbol: str) -> Dict[str, Any]:
        payload = self._get(
            "/markets/quotes",
            {"symbols": str(option_symbol).upper(), "greeks": "true"},
        )
        quotes = payload.get("quotes") or {}
        values = quotes.get("quote") if isinstance(quotes, dict) else None
        rows = [value for value in self._as_list(values) if isinstance(value, dict)]
        if not rows:
            raise ValueError("tradier_option_quote_missing")
        return rows[0]
