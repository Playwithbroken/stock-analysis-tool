"""Canonical conversions for provider ratios and percentage-point values."""

from __future__ import annotations

import math
from typing import Any, Optional


def _finite_number(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def normalize_dividend_yield_pct(value: Any) -> Optional[float]:
    """Return dividend yield in percentage points.

    Yahoo-compatible providers have returned both ratio form (0.0614) and
    percentage-point form (6.14). Dividend yields at or below 20% are a safe
    boundary for distinguishing the two representations used by those feeds.
    """

    number = _finite_number(value)
    if number is None:
        return None
    return number * 100 if abs(number) <= 0.2 else number


def ratio_to_pct(value: Any) -> Optional[float]:
    """Convert a documented ratio value, such as payoutRatio, to percent."""

    number = _finite_number(value)
    return number * 100 if number is not None else None


def relative_change_pct(current: Any, reference: Any) -> Optional[float]:
    """Return the percentage change from a valid, non-zero reference value."""

    current_number = _finite_number(current)
    reference_number = _finite_number(reference)
    if current_number is None or reference_number in (None, 0):
        return None
    return ((current_number / reference_number) - 1) * 100
