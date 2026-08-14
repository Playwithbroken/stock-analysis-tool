from __future__ import annotations

from typing import Any, Dict, Iterable


def build_trade_performance(trades: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Build realized, money-weighted evidence without implying certainty."""
    rows = [trade for trade in trades if trade.get("realized_pnl_pct") is not None]
    rows.sort(key=lambda trade: str(trade.get("closed_at") or trade.get("opened_at") or ""))
    pnl_values = [float(trade.get("realized_pnl_value") or 0) for trade in rows]
    pnl_pcts = [float(trade.get("realized_pnl_pct") or 0) for trade in rows]
    wins = [value for value in pnl_values if value > 0]
    losses = [value for value in pnl_values if value < 0]
    neutral_count = len(pnl_values) - len(wins) - len(losses)
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    sample_size = len(rows)

    if sample_size >= 30:
        evidence_status = "usable_sample"
        evidence_label = "belastbare Stichprobe"
    elif sample_size >= 10:
        evidence_status = "building_sample"
        evidence_label = "Stichprobe im Aufbau"
    else:
        evidence_status = "insufficient_sample"
        evidence_label = "zu wenig Daten"

    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else None
    avg_win = round(gross_profit / len(wins), 2) if wins else 0.0
    avg_loss = round(gross_loss / len(losses), 2) if losses else 0.0
    equity_index = 100.0
    peak_index = 100.0
    max_drawdown_pct = 0.0
    for pnl_pct in pnl_pcts:
        equity_index *= max(0.0, 1.0 + (pnl_pct / 100.0))
        peak_index = max(peak_index, equity_index)
        if peak_index > 0:
            max_drawdown_pct = max(max_drawdown_pct, ((peak_index - equity_index) / peak_index) * 100.0)

    return {
        "sample_size": sample_size,
        "wins": len(wins),
        "losses": len(losses),
        "neutral": neutral_count,
        "win_rate": round((len(wins) / sample_size) * 100, 1) if sample_size else 0.0,
        "gross_profit_value": round(gross_profit, 2),
        "gross_loss_value": round(gross_loss, 2),
        "net_pnl_value": round(sum(pnl_values), 2),
        "avg_win_value": avg_win,
        "avg_loss_value": avg_loss,
        "profit_factor": profit_factor,
        "payoff_ratio": round(avg_win / avg_loss, 2) if avg_loss > 0 else None,
        "expectancy_value": round(sum(pnl_values) / sample_size, 2) if sample_size else 0.0,
        "expectancy_pct": round(sum(pnl_pcts) / sample_size, 2) if sample_size else 0.0,
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "evidence_status": evidence_status,
        "evidence_label": evidence_label,
        "minimum_usable_sample": 30,
    }
