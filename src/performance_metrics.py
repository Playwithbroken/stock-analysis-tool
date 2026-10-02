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


def calculate_trading_journal_metrics(
    trades: Iterable[Dict[str, Any]],
    starting_capital: float = 50000.0,
) -> Dict[str, Any]:
    """
    Computes statistical edge and expectancy metrics for closed trades,
    including realistic friction deductions and an equity curve series.
    """
    closed = [
        t for t in trades
        if str(t.get("status") or "").lower() == "closed"
        and t.get("closed_price") is not None
        and t.get("entry_price") is not None
    ]
    closed.sort(key=lambda t: str(t.get("closed_at") or t.get("opened_at") or ""))

    if not closed:
        return {
            "total_closed_trades": 0,
            "wins": 0,
            "losses": 0,
            "breakeven": 0,
            "win_rate": 0.0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "total_friction": 0.0,
            "net_pnl": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
            "payoff_ratio": 0.0,
            "expectancy_eur": 0.0,
            "expectancy_pct": 0.0,
            "max_drawdown_amount": 0.0,
            "max_drawdown_pct": 0.0,
            "starting_capital": starting_capital,
            "current_equity": starting_capital,
            "equity_curve": [{"trade_num": 0, "date": "Start", "equity": starting_capital, "pnl": 0.0, "drawdown_pct": 0.0}],
        }

    wins_list = []
    losses_list = []
    be_count = 0
    total_fric = 0.0
    processed_trades = []

    cum_net_pnl = 0.0
    equity = starting_capital
    peak_equity = starting_capital
    max_dd_amount = 0.0
    max_dd_pct = 0.0

    curve = [{"trade_num": 0, "date": "Start", "equity": starting_capital, "pnl": 0.0, "drawdown_pct": 0.0}]

    for idx, t in enumerate(closed, 1):
        ticker = str(t.get("ticker") or "").upper().strip()
        entry = float(t.get("entry_price") or 0.0)
        exit_p = float(t.get("closed_price") or entry)
        qty = float(t.get("quantity") or 1.0)
        date_str = str(t.get("closed_at") or "")[:10]

        is_eu = any(ticker.endswith(sfx) for sfx in [".DE", ".F", ".AS", ".PA", ".MI", ".MC"])
        spread_pct = 0.08 if is_eu else 0.04
        slippage_pct = 0.03 if is_eu else 0.02
        comm = 2.0 if is_eu else 0.0

        gross = (exit_p - entry) * qty
        fric = (entry * qty + exit_p * qty) * ((spread_pct / 2.0 + slippage_pct) / 100.0) + comm
        net = round(gross - fric, 2)
        total_fric += fric

        if net > 0.01:
            wins_list.append(net)
        elif net < -0.01:
            losses_list.append(abs(net))
        else:
            be_count += 1

        cum_net_pnl += net
        equity = round(starting_capital + cum_net_pnl, 2)
        if equity > peak_equity:
            peak_equity = equity

        dd_amount = max(0.0, peak_equity - equity)
        dd_pct = (dd_amount / peak_equity * 100.0) if peak_equity > 0 else 0.0
        if dd_amount > max_dd_amount:
            max_dd_amount = dd_amount
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct

        curve.append({
            "trade_num": idx,
            "date": date_str,
            "ticker": ticker,
            "trade_net_pnl": net,
            "cumulative_pnl": round(cum_net_pnl, 2),
            "equity": equity,
            "drawdown_pct": round(dd_pct, 2),
        })

    n = len(closed)
    win_cnt = len(wins_list)
    loss_cnt = len(losses_list)
    win_rate = (win_cnt / n) if n > 0 else 0.0
    loss_rate = (loss_cnt / n) if n > 0 else 0.0

    gross_win_sum = sum(wins_list)
    gross_loss_sum = sum(losses_list)
    avg_win = (gross_win_sum / win_cnt) if win_cnt > 0 else 0.0
    avg_loss = (gross_loss_sum / loss_cnt) if loss_cnt > 0 else 0.0

    # Mathematical Expectancy: E = (W * AvgWin) - (L * AvgLoss)
    expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
    expectancy_pct = (expectancy / starting_capital * 100.0) if starting_capital > 0 else 0.0
    profit_factor = round(gross_win_sum / gross_loss_sum, 2) if gross_loss_sum > 0 else (99.0 if gross_win_sum > 0 else 0.0)
    payoff_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0

    return {
        "total_closed_trades": n,
        "wins": win_cnt,
        "losses": loss_cnt,
        "breakeven": be_count,
        "win_rate": round(win_rate * 100.0, 1),
        "gross_profit": round(gross_win_sum, 2),
        "gross_loss": round(gross_loss_sum, 2),
        "total_friction": round(total_fric, 2),
        "net_pnl": round(cum_net_pnl, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": profit_factor,
        "payoff_ratio": payoff_ratio,
        "expectancy_eur": round(expectancy, 2),
        "expectancy_pct": round(expectancy_pct, 2),
        "max_drawdown_amount": round(max_dd_amount, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "starting_capital": starting_capital,
        "current_equity": equity,
        "equity_curve": curve,
    }

