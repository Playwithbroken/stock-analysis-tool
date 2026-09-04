from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class MarketDataAdapter(ABC):
    @abstractmethod
    async def run(self) -> None:
        """Run until stopped or cancelled."""

    @abstractmethod
    async def close(self) -> None:
        """Request a graceful shutdown."""

    @abstractmethod
    def health(self) -> Dict[str, Any]:
        """Return a secret-free provider health snapshot."""

