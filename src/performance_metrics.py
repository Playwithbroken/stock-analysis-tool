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
            "net_pnl_before_tax": 0.0,
            "total_tax_paid": 0.0,
            "tax_loss_pool": 0.0,
            "total_loss_pool_used": 0.0,
            "net_pnl_after_tax": 0.0,
            "freibetrag_limit_eur": 1000.0,
            "freibetrag_used_eur": 0.0,
            "freibetrag_remaining_eur": 1000.0,
            "tax_saved_via_freibetrag_eur": 0.0,
            "effective_tax_after_freibetrag": 0.0,
            "net_pnl_with_freibetrag": 0.0,
            "tax_rate_pct": 26.375,
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
            "current_equity_after_tax": starting_capital,
            "current_equity_with_freibetrag": starting_capital,
            "equity_curve": [{
                "trade_num": 0,
                "date": "Start",
                "equity": starting_capital,
                "equity_after_tax": starting_capital,
                "pnl": 0.0,
                "trade_tax_paid": 0.0,
                "trade_net_after_tax": 0.0,
                "loss_pool_balance": 0.0,
                "freibetrag_remaining": 1000.0,
                "drawdown_pct": 0.0,
            }],
        }

    wins_list = []
    losses_list = []
    be_count = 0
    total_fric = 0.0
    total_tax_paid = 0.0
    effective_tax_after_fb = 0.0
    loss_pool = 0.0
    total_loss_pool_used = 0.0
    freibetrag_remaining = 1000.0
    freibetrag_used_total = 0.0
    tax_saved_fb_total = 0.0

    cum_net_pnl = 0.0
    cum_net_after_tax = 0.0
    cum_net_with_fb = 0.0
    equity = starting_capital
    equity_after_tax = starting_capital
    equity_with_fb = starting_capital
    peak_equity = starting_capital
    max_dd_amount = 0.0
    max_dd_pct = 0.0

    curve = [{
        "trade_num": 0,
        "date": "Start",
        "equity": starting_capital,
        "equity_after_tax": starting_capital,
        "pnl": 0.0,
        "trade_tax_paid": 0.0,
        "trade_net_after_tax": 0.0,
        "loss_pool_balance": 0.0,
        "freibetrag_remaining": 1000.0,
        "drawdown_pct": 0.0,
    }]

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
        tax_step = calculate_paper_trade_german_tax_step(
            gross_pnl=gross,
            friction=fric,
            current_loss_pool=loss_pool,
            current_freibetrag=freibetrag_remaining,
        )
        net = tax_step["pnl_before_tax"]
        trade_tax = tax_step["tax_paid_eur"]
        net_after_tax = tax_step["net_after_tax"]
        loss_pool = tax_step["loss_pool_after"]
        freibetrag_remaining = tax_step["freibetrag_after"]
        freibetrag_used_total += tax_step["freibetrag_used"]
        tax_saved_fb_total += tax_step["tax_saved_via_freibetrag_eur"]
        effective_tax_after_fb += tax_step["tax_after_freibetrag_eur"]
        total_loss_pool_used += tax_step["loss_pool_used"]
        total_tax_paid += trade_tax
        total_fric += fric

        if net > 0.01:
            wins_list.append(net)
        elif net < -0.01:
            losses_list.append(abs(net))
        else:
            be_count += 1

        cum_net_pnl += net
        cum_net_after_tax += net_after_tax
        cum_net_with_fb += tax_step["net_after_freibetrag"]
        equity = round(starting_capital + cum_net_pnl, 2)
        equity_after_tax = round(starting_capital + cum_net_after_tax, 2)
        equity_with_fb = round(starting_capital + cum_net_with_fb, 2)
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
            "trade_tax_paid": trade_tax,
            "trade_tax_after_freibetrag": tax_step["tax_after_freibetrag_eur"],
            "trade_net_after_tax": net_after_tax,
            "trade_net_with_freibetrag": tax_step["net_after_freibetrag"],
            "loss_pool_balance": loss_pool,
            "freibetrag_remaining": freibetrag_remaining,
            "cumulative_pnl": round(cum_net_pnl, 2),
            "cumulative_pnl_after_tax": round(cum_net_after_tax, 2),
            "equity": equity,
            "equity_after_tax": equity_after_tax,
            "equity_with_freibetrag": equity_with_fb,
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
        "net_pnl_before_tax": round(cum_net_pnl, 2),
        "total_tax_paid": round(total_tax_paid, 2),
        "tax_loss_pool": round(loss_pool, 2),
        "total_loss_pool_used": round(total_loss_pool_used, 2),
        "net_pnl_after_tax": round(cum_net_after_tax, 2),
        "freibetrag_limit_eur": 1000.0,
        "freibetrag_used_eur": round(freibetrag_used_total, 2),
        "freibetrag_remaining_eur": round(freibetrag_remaining, 2),
        "tax_saved_via_freibetrag_eur": round(tax_saved_fb_total, 2),
        "effective_tax_after_freibetrag": round(effective_tax_after_fb, 2),
        "net_pnl_with_freibetrag": round(cum_net_with_fb, 2),
        "tax_rate_pct": 26.375,
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
        "current_equity_after_tax": equity_after_tax,
        "current_equity_with_freibetrag": equity_with_fb,
        "equity_curve": curve,
    }


def calculate_paper_trade_german_tax_step(
    gross_pnl: float,
    friction: float,
    current_loss_pool: float = 0.0,
    current_freibetrag: float = 0.0,
) -> Dict[str, Any]:
    """
    Calculates German capital gains tax (25% Abgeltungsteuer + 5.5% Soli = 26.375%),
    sequential Aktien-Verlustverrechnungstopf (Stock Loss Offset Pool), and
    1.000 EUR Sparer-Pauschbetrag (Freistellungsauftrag) per § 20 EStG.
    """
    gross_val = float(gross_pnl or 0.0)
    fric_val = max(0.0, float(friction or 0.0))
    pnl_before_tax = round(gross_val - fric_val, 2)
    pool_before = round(max(0.0, float(current_loss_pool or 0.0)), 2)
    fb_before = round(max(0.0, float(current_freibetrag or 0.0)), 2)

    if pnl_before_tax < 0:
        loss_pool_used = 0.0
        loss_pool_added = round(abs(pnl_before_tax), 2)
        pool_after = round(pool_before + loss_pool_added, 2)
        taxable_gain = 0.0
        abgeltungsteuer_eur = 0.0
        soli_eur = 0.0
        tax_paid_eur = 0.0
        net_after_tax = pnl_before_tax
        fb_used = 0.0
        fb_after = fb_before
        taxable_after_fb = 0.0
        tax_after_fb_eur = 0.0
        tax_saved_fb_eur = 0.0
        net_after_fb = pnl_before_tax
    else:
        # 1. Bucket: Aktien-Verlustverrechnungstopf
        loss_pool_used = round(min(pnl_before_tax, pool_before), 2)
        loss_pool_added = 0.0
        pool_after = round(max(0.0, pool_before - loss_pool_used), 2)
        taxable_gain = round(max(0.0, pnl_before_tax - loss_pool_used), 2)

        # Standard 26.375% tax after Verlusttopf
        abgeltungsteuer_eur = round(taxable_gain * 0.25, 2)
        soli_eur = round(taxable_gain * 0.01375, 2)
        tax_paid_eur = round(abgeltungsteuer_eur + soli_eur, 2)
        net_after_tax = round(pnl_before_tax - tax_paid_eur, 2)

        # 2. Bucket: 1.000 EUR Sparer-Pauschbetrag (Freistellungsauftrag)
        fb_used = round(min(taxable_gain, fb_before), 2)
        fb_after = round(max(0.0, fb_before - fb_used), 2)
        taxable_after_fb = round(max(0.0, taxable_gain - fb_used), 2)
        abg_fb = round(taxable_after_fb * 0.25, 2)
        soli_fb = round(taxable_after_fb * 0.01375, 2)
        tax_after_fb_eur = round(abg_fb + soli_fb, 2)
        tax_saved_fb_eur = round(max(0.0, tax_paid_eur - tax_after_fb_eur), 2)
        net_after_fb = round(pnl_before_tax - tax_after_fb_eur, 2)

    return {
        "gross_pnl": round(gross_val, 2),
        "friction": round(fric_val, 2),
        "pnl_before_tax": pnl_before_tax,
        "loss_pool_before": pool_before,
        "loss_pool_used": loss_pool_used,
        "loss_pool_added": loss_pool_added,
        "loss_pool_after": pool_after,
        "taxable_gain": taxable_gain,
        "abgeltungsteuer_eur": abgeltungsteuer_eur,
        "soli_eur": soli_eur,
        "tax_paid_eur": tax_paid_eur,
        "net_after_tax": net_after_tax,
        "freibetrag_before": fb_before,
        "freibetrag_used": fb_used,
        "freibetrag_after": fb_after,
        "taxable_gain_after_freibetrag": taxable_after_fb,
        "tax_after_freibetrag_eur": tax_after_fb_eur,
        "tax_saved_via_freibetrag_eur": tax_saved_fb_eur,
        "net_after_freibetrag": net_after_fb,
        "tax_rate_pct": 26.375,
    }


def get_current_tax_loss_pool(
    trades: List[Dict[str, Any]],
    exclude_trade_id: int | None = None,
) -> Dict[str, Any]:
    """
    Computes the current German Aktien-Verlustverrechnungstopf and 1.000 EUR Sparer-Pauschbetrag
    balance across all closed paper trades.
    Optionally excludes `exclude_trade_id` to retrieve the pool state immediately prior to closing that trade.
    """
    if not isinstance(trades, list):
        return {
            "loss_pool_balance": 0.0,
            "total_tax_paid": 0.0,
            "total_loss_pool_used": 0.0,
            "net_pnl_before_tax": 0.0,
            "net_pnl_after_tax": 0.0,
            "freibetrag_limit_eur": 1000.0,
            "freibetrag_used_eur": 0.0,
            "freibetrag_remaining_eur": 1000.0,
            "tax_saved_via_freibetrag_eur": 0.0,
            "effective_tax_after_freibetrag": 0.0,
            "net_pnl_with_freibetrag": 0.0,
        }

    filtered = [
        t for t in trades
        if isinstance(t, dict)
        and (exclude_trade_id is None or t.get("id") != exclude_trade_id)
    ]
    metrics = calculate_trading_journal_metrics(filtered, starting_capital=10000.0)
    return {
        "loss_pool_balance": float(metrics.get("tax_loss_pool", 0.0)),
        "total_tax_paid": float(metrics.get("total_tax_paid", 0.0)),
        "total_loss_pool_used": float(metrics.get("total_loss_pool_used", 0.0)),
        "net_pnl_before_tax": float(metrics.get("net_pnl_before_tax", 0.0)),
        "net_pnl_after_tax": float(metrics.get("net_pnl_after_tax", 0.0)),
        "freibetrag_limit_eur": float(metrics.get("freibetrag_limit_eur", 1000.0)),
        "freibetrag_used_eur": float(metrics.get("freibetrag_used_eur", 0.0)),
        "freibetrag_remaining_eur": float(metrics.get("freibetrag_remaining_eur", 1000.0)),
        "tax_saved_via_freibetrag_eur": float(metrics.get("tax_saved_via_freibetrag_eur", 0.0)),
        "effective_tax_after_freibetrag": float(metrics.get("effective_tax_after_freibetrag", 0.0)),
        "net_pnl_with_freibetrag": float(metrics.get("net_pnl_with_freibetrag", 0.0)),
    }


def convert_paper_trade_fx(
    ticker: str,
    amount_local: float,
    notional_local: float = 0.0,
) -> Dict[str, Any]:
    """
    Converts US ($) or UK (£) paper trade amounts into EUR (€) using realistic German broker
    Auto-FX rates and 0.15% FX conversion spread (Trade Republic / Scalable / Smartbroker).
    """
    sym = str(ticker or "").upper().strip()
    is_eu = any(sym.endswith(sfx) for sfx in [".DE", ".F", ".AS", ".PA", ".MI", ".MC"])
    is_uk = sym.endswith(".L")

    if is_eu:
        return {
            "is_foreign_currency": False,
            "currency": "EUR",
            "fx_rate": 1.0,
            "fx_markup_pct": 0.0,
            "fx_fee_eur": 0.0,
            "amount_eur": round(float(amount_local or 0.0), 2),
        }

    # Reference EUR/USD (1 EUR = 1.085 USD) or EUR/GBP (1 EUR = 0.855 GBP)
    fx_rate = 0.855 if is_uk else 1.085
    fx_markup_pct = 0.15  # 0.15% German broker Auto-FX spread
    raw_eur = float(amount_local or 0.0) / fx_rate
    notional_eur = (float(notional_local or abs(amount_local) or 0.0) / fx_rate)
    fx_fee_eur = round(notional_eur * (fx_markup_pct / 100.0), 2)
    amount_eur = round(raw_eur - fx_fee_eur, 2) if amount_local >= 0 else round(raw_eur - fx_fee_eur, 2)

    return {
        "is_foreign_currency": True,
        "currency": "GBP" if is_uk else "USD",
        "fx_rate": fx_rate,
        "fx_markup_pct": fx_markup_pct,
        "fx_fee_eur": fx_fee_eur,
        "amount_eur": amount_eur,
    }


def evaluate_daily_tilt_breaker(
    trades: List[Dict[str, Any]],
    starting_capital: float = 50000.0,
) -> Dict[str, Any]:
    """
    Prop-Desk Daily Loss Limit & Anti-Revenge-Trading Breaker (Tilt-Schutz).
    Evaluates consecutive losing streaks and single-day drawdown in R-multiples (1R = 1% of capital).
    """
    one_r_eur = max(100.0, float(starting_capital or 50000.0) * 0.01)
    if not isinstance(trades, list):
        trades = []

    closed = [
        t for t in trades
        if isinstance(t, dict)
        and str(t.get("status") or "").lower() == "closed"
        and t.get("closed_price") is not None
        and t.get("entry_price") is not None
    ]
    closed.sort(key=lambda t: str(t.get("closed_at") or t.get("opened_at") or ""))

    if not closed:
        return {
            "tilt_status": "GREEN",
            "tilt_badge": "🟢 GRÜN – Disziplin & Risikolimit voll intakt",
            "consecutive_losses": 0,
            "latest_day_date": "Heute",
            "latest_day_trades": 0,
            "latest_day_losses": 0,
            "latest_day_pnl_eur": 0.0,
            "latest_day_r": 0.0,
            "recommended_risk_pct": 1.0,
            "is_locked": False,
            "coach_rule": "Volle Freigabe (1.0R Risiko) für A+ Setups (Edge-Score ≥ 70).",
        }

    # Count current consecutive losses from the end
    consecutive_losses = 0
    for t in reversed(closed):
        ep = float(t.get("entry_price") or 0.0)
        xp = float(t.get("closed_price") or ep)
        qty = float(t.get("quantity") or 1.0)
        pnl = (xp - ep) * qty
        if pnl < -0.01:
            consecutive_losses += 1
        else:
            break

    # Evaluate the most recent active trading day
    latest_day = str(closed[-1].get("closed_at") or closed[-1].get("opened_at") or "")[:10] or "Heute"
    day_trades = [
        t for t in closed
        if (str(t.get("closed_at") or t.get("opened_at") or "")[:10] or "Heute") == latest_day
    ]
    day_losses = 0
    day_pnl = 0.0
    for t in day_trades:
        ep = float(t.get("entry_price") or 0.0)
        xp = float(t.get("closed_price") or ep)
        qty = float(t.get("quantity") or 1.0)
        pnl = (xp - ep) * qty
        day_pnl += pnl
        if pnl < -0.01:
            day_losses += 1

    day_r = round(day_pnl / one_r_eur, 2)

    if day_losses >= 2 or consecutive_losses >= 3 or day_r <= -2.0:
        return {
            "tilt_status": "RED",
            "tilt_badge": "🔴 ROT – TILT-SCHUTZ AKTIV (Rache-Trading-Sperre!)",
            "consecutive_losses": consecutive_losses,
            "latest_day_date": latest_day,
            "latest_day_trades": len(day_trades),
            "latest_day_losses": day_losses,
            "latest_day_pnl_eur": round(day_pnl, 2),
            "latest_day_r": day_r,
            "recommended_risk_pct": 0.0,
            "is_locked": True,
            "coach_rule": (
                "🛑 PROP-DESK TILT-STOPP: Nach 2 Tagesverlusten oder -2.0R Tages-Drawdown "
                "keine neuen Impuls-Trades eröffnen! Erst 4h Cooldown abwarten – Rache-Trading vernichtet sonst die Monatsrendite."
            ),
        }
    elif day_losses == 1 or consecutive_losses == 2 or day_r <= -1.0:
        return {
            "tilt_status": "YELLOW",
            "tilt_badge": "🟡 GELB – Vorsicht (Positionsgröße auf 0.5R halbieren)",
            "consecutive_losses": consecutive_losses,
            "latest_day_date": latest_day,
            "latest_day_trades": len(day_trades),
            "latest_day_losses": day_losses,
            "latest_day_pnl_eur": round(day_pnl, 2),
            "latest_day_r": day_r,
            "recommended_risk_pct": 0.5,
            "is_locked": False,
            "coach_rule": (
                "⚠️ GELBE AMPEL: Nach einem Verlust-Trade wird das Risiko für den nächsten Trade "
                "automatisch auf 0.5% (halbe Positionsgröße) reduziert. Nur A+ Setups (Score ≥ 80) handeln!"
            ),
        }

    return {
        "tilt_status": "GREEN",
        "tilt_badge": "🟢 GRÜN – Disziplin & Risikolimit voll intakt",
        "consecutive_losses": consecutive_losses,
        "latest_day_date": latest_day,
        "latest_day_trades": len(day_trades),
        "latest_day_losses": day_losses,
        "latest_day_pnl_eur": round(day_pnl, 2),
        "latest_day_r": day_r,
        "recommended_risk_pct": 1.0,
        "is_locked": False,
        "coach_rule": "✅ GRÜNE AMPEL: Volle Freigabe (1.0R Risiko) für A+ Setups mit bestätigtem Orderflow.",
    }


def analyze_tax_loss_harvesting(
    trades: List[Dict[str, Any]],
    spot_lookup: Dict[str, float] | None = None,
) -> Dict[str, Any]:
    """
    Analyzes closed and open paper trades for German Tax-Loss Harvesting (Steuer-Ernte)
    and 1.000 EUR Sparer-Pauschbetrag year-end optimization (§ 20 EStG).
    """
    if not isinstance(trades, list):
        trades = []
    spots = spot_lookup if isinstance(spot_lookup, dict) else {}

    closed = [
        t for t in trades
        if isinstance(t, dict) and str(t.get("status") or "").lower() == "closed"
    ]
    open_trades = [
        t for t in trades
        if isinstance(t, dict) and str(t.get("status") or "").lower() == "open"
    ]

    m = calculate_trading_journal_metrics(closed, starting_capital=50000.0)
    tax_paid = float(m.get("total_tax_paid", 0.0))
    eff_tax_paid = float(m.get("effective_tax_after_freibetrag", 0.0))
    loss_pool = float(m.get("tax_loss_pool", 0.0))
    fb_rem = float(m.get("freibetrag_remaining_eur", 1000.0))

    loss_candidates: List[Dict[str, Any]] = []
    gain_candidates: List[Dict[str, Any]] = []

    for ot in open_trades:
        sym = str(ot.get("ticker") or "ASSET").upper().strip()
        ep = float(ot.get("entry_price") or 0.0)
        qty = float(ot.get("quantity") or 1.0)
        sp = float(spots.get(sym) or ot.get("current_price") or ep)
        if ep <= 0 or qty <= 0:
            continue

        unrealized = round((sp - ep) * qty, 2)
        if unrealized < -5.0:
            abs_loss = abs(unrealized)
            potential_refund = round(min(tax_paid, abs_loss * 0.26375), 2) if tax_paid > 0 else 0.0
            future_shield = round(abs_loss * 0.26375, 2)
            loss_candidates.append({
                "ticker": sym,
                "qty": int(qty),
                "entry_price": ep,
                "spot_price": sp,
                "unrealized_loss_eur": unrealized,
                "immediate_tax_refund_eur": potential_refund,
                "loss_pool_credit_eur": abs_loss,
                "future_tax_shield_eur": future_shield,
            })
        elif unrealized > 5.0:
            tax_free_capacity = round(loss_pool + fb_rem, 2)
            tax_free_harvest = round(min(unrealized, tax_free_capacity), 2)
            tax_saved = round(tax_free_harvest * 0.26375, 2)
            gain_candidates.append({
                "ticker": sym,
                "qty": int(qty),
                "entry_price": ep,
                "spot_price": sp,
                "unrealized_gain_eur": unrealized,
                "tax_free_harvest_eur": tax_free_harvest,
                "tax_saved_eur": tax_saved,
            })

    total_refundable_now = round(sum(c["immediate_tax_refund_eur"] for c in loss_candidates), 2)
    return {
        "total_tax_paid_eur": tax_paid,
        "effective_tax_after_freibetrag_eur": eff_tax_paid,
        "loss_pool_balance_eur": loss_pool,
        "freibetrag_remaining_eur": fb_rem,
        "loss_harvest_candidates": loss_candidates,
        "freibetrag_harvest_candidates": gain_candidates,
        "total_immediate_refund_potential_eur": total_refundable_now,
    }


def evaluate_weekend_gap_exposure(
    open_trades: List[Dict[str, Any]],
    spot_lookup: Dict[str, float] | None = None,
) -> Dict[str, Any]:
    """
    Evaluates open paper/lifecycle trades for Friday & Holiday Weekend Gap Risk.
    """
    if not isinstance(open_trades, list):
        open_trades = []
    spots = spot_lookup if isinstance(spot_lookup, dict) else {}

    assessments: List[Dict[str, Any]] = []
    high_risk_count = 0
    safe_count = 0

    for t in open_trades:
        if not isinstance(t, dict):
            continue
        status = str(t.get("status") or "open").lower()
        if status not in ("open", "target_1_hit"):
            continue

        sym = str(t.get("ticker") or "ASSET").upper().strip()
        ep = float(t.get("entry_price") or 0.0)
        stop = float(t.get("stop_price") or t.get("invalidation_price") or t.get("trailing_stop") or (ep * 0.96))
        qty = float(t.get("quantity") or 10.0)
        sp = float(spots.get(sym) or t.get("current_price") or t.get("last_price") or ep)

        risk_per_share = max(0.01, abs(ep - (ep * 0.96 if abs(ep - stop) < 0.01 else stop)))
        current_r = round((sp - ep) / risk_per_share, 2) if ep > 0 else 0.0
        cushion_stop = round(ep - 0.25 * risk_per_share, 2)

        if current_r >= 1.0:
            action_code = "SAFE_HOLD"
            badge = "🟢 SICHER HALTEN (Gewinnpuffer ≥ +1.0R)"
            instruction = f"Stop auf -0.25R Puffer ({cushion_stop:.2f}) oder Einstand ({ep:.2f}) sichern – risikofrei übers Wochenende halten."
            safe_count += 1
        elif current_r >= 0.25:
            action_code = "PARTIAL_TRIM"
            badge = "🟡 TEIL-SICHERUNG (+0.25R bis +1.0R)"
            instruction = f"Kleiner Puffer vorhanden ({current_r:+.2f}R). Vor Freitag 21:30 Uhr Stop auf -0.25R ({cushion_stop:.2f}) nachziehen."
        else:
            action_code = "HIGH_GAP_RISK"
            badge = "🔴 GAP-RISIKO (Kein Gewinnpuffer vor Wochenende)"
            instruction = f"Position bei {current_r:+.2f}R nahe Einstieg. Vor Freitag 21:30 Uhr 50% reduzieren ({max(1, int(qty // 2))} Stk.), um Wochenend-Gap-Risiko zu halbieren!"
            high_risk_count += 1

        assessments.append({
            "ticker": sym,
            "qty": int(qty),
            "entry_price": ep,
            "spot_price": sp,
            "current_r": current_r,
            "cushion_stop": cushion_stop,
            "action_code": action_code,
            "badge": badge,
            "instruction": instruction,
        })

    return {
        "total_open": len(assessments),
        "safe_hold_count": safe_count,
        "high_gap_risk_count": high_risk_count,
        "assessments": assessments,
    }


def simulate_what_if_scenarios_eur(
    ticker: str,
    entry_price: float,
    stop_price: float,
    target_1: float,
    target_2: float,
    investment_eur: float = 2000.0,
    loss_pool_eur: float = 0.0,
    freibetrag_eur: float = 0.0,
) -> Dict[str, Any]:
    """
    Simulates a concrete EUR investment (e.g. 2.000 EUR) across 3 real-world outcomes:
    1) Target 1 (+2.0R) & Target 2 (+3.5R+) hit -> Net EUR after fees, FX, Verlusttopf, Freibetrag & 26.375% tax
    2) Pullback after +1.0R -> Smart -0.25R Breathing Cushion exit (saves 75% of risk!)
    3) Immediate Hard Stop (-1.0R) -> Full loss + Verlustverrechnungstopf tax shield credit
    """
    sym = str(ticker or "ASSET").upper().strip()
    inv_eur = max(100.0, float(investment_eur or 2000.0))
    ep = max(0.01, float(entry_price or 100.0))
    sp = float(stop_price or (ep * 0.96))
    t1 = float(target_1 or (ep * 1.08))
    t2 = float(target_2 or (ep * 1.14))

    fx_entry = convert_paper_trade_fx(sym, ep, notional_local=ep)
    ep_eur = max(0.01, float(fx_entry["amount_eur"] or ep))
    fx_rate = float(fx_entry["fx_rate"] or 1.0)
    is_fx = bool(fx_entry["is_foreign_currency"])

    shares = max(1, int(round(inv_eur / ep_eur)))
    actual_invested_eur = round(shares * ep_eur, 2)

    risk_per_share_eur = max(0.01, abs(ep - sp) / fx_rate)
    reward_t1_per_share_eur = max(0.01, abs(t1 - ep) / fx_rate)
    reward_t2_per_share_eur = max(0.01, abs(t2 - ep) / fx_rate)

    # Roundtrip friction: 2.00 EUR order fee + 0.30% roundtrip FX/spread on foreign stocks
    base_friction_eur = round(2.0 + (actual_invested_eur * 0.003 if is_fx else actual_invested_eur * 0.001), 2)

    # Scenario 1A: Target 1 (+2.0R)
    gross_t1_eur = round(shares * reward_t1_per_share_eur, 2)
    step_t1 = calculate_paper_trade_german_tax_step(
        gross_pnl=gross_t1_eur,
        friction=base_friction_eur,
        current_loss_pool=loss_pool_eur,
        current_freibetrag=freibetrag_eur,
    )

    # Scenario 1B: Target 2 (+3.5R+)
    gross_t2_eur = round(shares * reward_t2_per_share_eur, 2)
    step_t2 = calculate_paper_trade_german_tax_step(
        gross_pnl=gross_t2_eur,
        friction=base_friction_eur,
        current_loss_pool=loss_pool_eur,
        current_freibetrag=freibetrag_eur,
    )

    # Scenario 2: Smart -0.25R Breathing Cushion Exit
    cushion_price = round(ep - 0.25 * abs(ep - sp), 2)
    gross_cushion_loss_eur = -round(shares * (0.25 * risk_per_share_eur), 2)
    step_cushion = calculate_paper_trade_german_tax_step(
        gross_pnl=gross_cushion_loss_eur,
        friction=base_friction_eur,
        current_loss_pool=loss_pool_eur,
        current_freibetrag=freibetrag_eur,
    )
    cushion_tax_shield_eur = round(abs(step_cushion["pnl_before_tax"]) * 0.26375, 2)
    cushion_effective_net_eur = -round(abs(step_cushion["pnl_before_tax"]) - cushion_tax_shield_eur, 2)

    # Scenario 3: Full -1.0R Hard Stop
    gross_stop_loss_eur = -round(shares * risk_per_share_eur, 2)
    step_stop = calculate_paper_trade_german_tax_step(
        gross_pnl=gross_stop_loss_eur,
        friction=base_friction_eur,
        current_loss_pool=loss_pool_eur,
        current_freibetrag=freibetrag_eur,
    )
    stop_tax_shield_eur = round(abs(step_stop["pnl_before_tax"]) * 0.26375, 2)
    stop_effective_net_eur = -round(abs(step_stop["pnl_before_tax"]) - stop_tax_shield_eur, 2)

    saved_by_cushion_eur = round(abs(step_stop["pnl_before_tax"]) - abs(step_cushion["pnl_before_tax"]), 2)

    return {
        "ticker": sym,
        "requested_investment_eur": inv_eur,
        "shares": shares,
        "actual_invested_eur": actual_invested_eur,
        "entry_price": ep,
        "cushion_price": cushion_price,
        "stop_price": sp,
        "target_1": t1,
        "target_2": t2,
        "friction_eur": base_friction_eur,
        "target_1_gross_eur": gross_t1_eur,
        "target_1_tax_eur": step_t1["tax_paid_eur"],
        "target_1_net_eur": step_t1["net_after_tax"],
        "target_1_net_with_freibetrag_eur": step_t1["net_after_freibetrag"],
        "target_2_gross_eur": gross_t2_eur,
        "target_2_tax_eur": step_t2["tax_paid_eur"],
        "target_2_net_eur": step_t2["net_after_tax"],
        "target_2_net_with_freibetrag_eur": step_t2["net_after_freibetrag"],
        "cushion_loss_before_shield_eur": step_cushion["pnl_before_tax"],
        "cushion_tax_shield_eur": cushion_tax_shield_eur,
        "cushion_effective_net_eur": cushion_effective_net_eur,
        "saved_by_cushion_eur": saved_by_cushion_eur,
        "hard_stop_loss_before_shield_eur": step_stop["pnl_before_tax"],
        "hard_stop_tax_shield_eur": stop_tax_shield_eur,
        "hard_stop_effective_net_eur": stop_effective_net_eur,
    }




