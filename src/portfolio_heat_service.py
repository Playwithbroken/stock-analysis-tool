"""
Portfolio Heat & Cross-Correlation Shield

Protects capital by calculating:
  1. Pairwise Rolling Returns Correlation (Pearson r) between assets.
  2. Total Portfolio Heat (% of equity at risk across all open positions).
  3. Correlated Cluster Risk: Flags when multiple positions share >0.70 correlation
     and could trigger simultaneous stop-outs during market/sector shocks.
"""
from __future__ import annotations

import logging
import math
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore


class PortfolioHeatService:
    def __init__(self, max_portfolio_heat_pct: float = 2.5, max_cluster_risk_pct: float = 1.8) -> None:
        self.max_portfolio_heat_pct = max_portfolio_heat_pct
        self.max_cluster_risk_pct = max_cluster_risk_pct
        self._price_cache: Dict[str, Tuple[float, List[float]]] = {}

    def compute_correlation_matrix(
        self,
        tickers: List[str],
        period: str = "3mo",
    ) -> Dict[str, Any]:
        """
        Calculates pairwise Pearson correlation coefficients from daily percentage returns.
        """
        clean_tickers = list(dict.fromkeys([t.upper().strip() for t in tickers if t]))
        if len(clean_tickers) < 2 or not yf:
            return {"tickers": clean_tickers, "matrix": {}, "high_correlation_pairs": []}

        # 1. Fetch price histories
        series_map: Dict[str, List[float]] = {}
        for sym in clean_tickers:
            cached = self._price_cache.get(sym)
            if cached and (time.time() - cached[0]) < 1800:
                series_map[sym] = cached[1]
                continue

            try:
                t = yf.Ticker(sym)
                hist = t.history(period=period, interval="1d")
                if not hist.empty and len(hist) >= 15:
                    closes = hist["Close"].tolist()
                    # Daily returns
                    returns = [
                        (closes[i] - closes[i - 1]) / closes[i - 1]
                        for i in range(1, len(closes))
                    ]
                    series_map[sym] = returns
                    self._price_cache[sym] = (time.time(), returns)
            except Exception as exc:
                logger.debug("Failed to fetch history for %s in correlation matrix: %s", sym, exc)

        valid_symbols = [s for s in clean_tickers if s in series_map]
        matrix: Dict[str, Dict[str, float]] = {s: {} for s in valid_symbols}
        high_corr_pairs: List[Dict[str, Any]] = []

        for i, s1 in enumerate(valid_symbols):
            matrix[s1][s1] = 1.0
            r1 = series_map[s1]
            for s2 in valid_symbols[i + 1:]:
                r2 = series_map[s2]
                min_len = min(len(r1), len(r2))
                if min_len < 10:
                    corr = 0.0
                else:
                    corr = self._pearson(r1[-min_len:], r2[-min_len:])

                matrix[s1][s2] = round(corr, 2)
                matrix.setdefault(s2, {})[s1] = round(corr, 2)

                if corr >= 0.70:
                    high_corr_pairs.append({
                        "ticker_a": s1,
                        "ticker_b": s2,
                        "correlation": round(corr, 2),
                        "cluster_level": "CRITICAL" if corr >= 0.85 else "HIGH",
                    })

        high_corr_pairs.sort(key=lambda x: x["correlation"], reverse=True)

        return {
            "tickers": valid_symbols,
            "matrix": matrix,
            "high_correlation_pairs": high_corr_pairs,
        }

    def evaluate_portfolio_heat(
        self,
        active_trades: List[Dict[str, Any]],
        portfolio_capital: float = 50000.0,
    ) -> Dict[str, Any]:
        """
        Calculates total equity at risk and checks for cluster concentration.
        Trades whose stops have moved to Breakeven have 0% open risk.
        """
        open_trades = [
            t for t in active_trades
            if t.get("status") in ("OPEN", "TARGET_1_HIT")
        ]

        total_risk_amount = 0.0
        trade_risks: List[Dict[str, Any]] = []

        for t in open_trades:
            sym = t["ticker"]
            entry = float(t.get("entry_price") or 0.0)
            stop = float(t.get("trailing_stop") or t.get("invalidation_price") or 0.0)
            shares = int(t.get("recommended_shares") or 1)
            status = t.get("status")

            # If stopped at or above entry, open capital risk is zero (house money)
            if status == "TARGET_1_HIT" and stop >= entry:
                risk_amt = 0.0
            else:
                risk_per_share = max(0.0, entry - stop)
                risk_amt = round(risk_per_share * shares, 2)

            risk_pct = round((risk_amt / portfolio_capital) * 100.0, 2)
            total_risk_amount += risk_amt
            trade_risks.append({
                "ticker": sym,
                "status": status,
                "shares": shares,
                "risk_amount": risk_amt,
                "risk_pct": risk_pct,
            })

        total_heat_pct = round((total_risk_amount / portfolio_capital) * 100.0, 2)

        # Check correlation among active positions
        tickers = [t["ticker"] for t in open_trades]
        corr_data = self.compute_correlation_matrix(tickers)
        high_pairs = corr_data.get("high_correlation_pairs", [])

        warnings: List[str] = []
        is_overheated = total_heat_pct > self.max_portfolio_heat_pct
        if is_overheated:
            warnings.append(
                f"⚠️ Portfolio Heat zu hoch: {total_heat_pct:.2f}% im Risiko (Limit: {self.max_portfolio_heat_pct:.2f}%). Keine neuen Positionen eröffnen!"
            )

        # Check cluster risks
        risk_by_sym = {r["ticker"]: r["risk_amount"] for r in trade_risks}
        cluster_warnings: List[Dict[str, Any]] = []
        for pair in high_pairs:
            ta = pair["ticker_a"]
            tb = pair["ticker_b"]
            combined_risk = risk_by_sym.get(ta, 0.0) + risk_by_sym.get(tb, 0.0)
            combined_pct = round((combined_risk / portfolio_capital) * 100.0, 2)
            if combined_pct >= self.max_cluster_risk_pct:
                warn_msg = (
                    f"⚠️ Hohe Korrelation ({pair['correlation']:.2f}) zwischen {ta} und {tb}! "
                    f"Kombiniertes Risiko beträgt {combined_pct:.2f}% (> {self.max_cluster_risk_pct:.2f}%)."
                )
                warnings.append(warn_msg)
                cluster_warnings.append({
                    "pair": f"{ta} + {tb}",
                    "correlation": pair["correlation"],
                    "combined_risk_amount": combined_risk,
                    "combined_risk_pct": combined_pct,
                })

        status_label = "SAFE" if not warnings else ("WARNING" if not is_overheated else "CRITICAL")

        return {
            "portfolio_capital": portfolio_capital,
            "total_risk_amount": round(total_risk_amount, 2),
            "portfolio_heat_pct": total_heat_pct,
            "max_portfolio_heat_pct": self.max_portfolio_heat_pct,
            "status": status_label,
            "is_overheated": is_overheated,
            "open_trades_count": len(open_trades),
            "trade_risks": trade_risks,
            "high_correlation_pairs": high_pairs,
            "cluster_warnings": cluster_warnings,
            "warnings": warnings,
        }

    def format_telegram_heat_card(self, heat: Dict[str, Any]) -> str:
        """Formats an attractive Telegram card for Portfolio Heat."""
        heat_pct = heat.get("portfolio_heat_pct", 0.0)
        max_heat = heat.get("max_portfolio_heat_pct", 2.5)
        risk_amt = heat.get("total_risk_amount", 0.0)
        status = heat.get("status", "SAFE")
        count = heat.get("open_trades_count", 0)

        icon = "🟢" if status == "SAFE" else ("🟡" if status == "WARNING" else "🔴")

        lines = [
            f"🛡️ <b>PORTFOLIO HEAT & RISIKO-SHIELD</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"• <b>Status:</b> {icon} <b>{status}</b>",
            f"• <b>Aktive Trades:</b> {count}",
            f"• <b>Gesamtrisiko (Heat):</b> <b>{heat_pct:.2f}%</b> (Max: {max_heat:.2f}%)",
            f"• <b>Kapital im Hard Stop:</b> ~{risk_amt:,.2f} EUR\n",
        ]

        warnings = heat.get("warnings", [])
        if warnings:
            lines.append("⚠️ <b>Risiko-Warnungen:</b>")
            for w in warnings:
                lines.append(f"• {w}")
            lines.append("")
        else:
            lines.append("✅ <i>Keine Klumpenrisiken. Das Gesamtrisiko liegt innerhalb der institutionellen Grenzen.</i>\n")

        lines.append("💡 <i>Tipp: Bei Marktschocks verhindern niedrige Korrelationen fatale Domino-Verluste.</i>")
        return "\n".join(lines)

    @staticmethod
    def _pearson(x: List[float], y: List[float]) -> float:
        n = len(x)
        if n < 2:
            return 0.0
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        den_x = sum((xi - mean_x) ** 2 for xi in x)
        den_y = sum((yi - mean_y) ** 2 for yi in y)
        den = math.sqrt(den_x * den_y)
        if den == 0:
            return 0.0
        return max(-1.0, min(1.0, num / den))
