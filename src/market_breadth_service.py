"""
Market Breadth & Internals Engine

Measures participation, trend breadth, and structural health across
European and US equity markets using multi-moving-average participation,
Advance/Decline ratios, and New-High/New-Low momentum indicators.
"""
from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore


DEFAULT_BREADTH_UNIVERSE = [
    # European / DAX Leaders
    "SAP.DE", "RHM.DE", "ASML.AS", "ALV.DE", "SIE.DE", "BAYN.DE", "BMW.DE",
    # US & International Tech & Momentum Leaders
    "NVDA", "MSFT", "AAPL", "AMZN", "PLTR", "TSLA", "META", "GOOGL", "AVGO",
    # Macro Benchmarks & Commodities
    "SPY", "QQQ", "GLD"
]


class MarketBreadthService:
    def __init__(self, cache_ttl_seconds: int = 300) -> None:
        self.cache_ttl = cache_ttl_seconds
        self._cache: Optional[Tuple[float, Dict[str, Any]]] = None

    def compute_market_breadth(
        self, tickers: Optional[List[str]] = None, force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Computes composite breadth indicators across the designated universe.
        """
        now = time.time()
        if not force_refresh and self._cache and (now - self._cache[0]) < self.cache_ttl:
            return self._cache[1]

        symbols = [t.upper().strip() for t in (tickers or DEFAULT_BREADTH_UNIVERSE) if t]
        symbols = list(dict.fromkeys(symbols))

        results_list: List[Dict[str, Any]] = []
        advancers = 0
        decliners = 0
        unchanged = 0
        above_ema20_cnt = 0
        above_sma50_cnt = 0
        above_sma200_cnt = 0
        near_52w_high_cnt = 0
        near_52w_low_cnt = 0

        for sym in symbols:
            try:
                if not yf:
                    continue
                tk = yf.Ticker(sym)
                df = tk.history(period="1y", interval="1d")
                if df.empty or len(df) < 50:
                    continue

                closes = df["Close"]
                spot = float(closes.iloc[-1])
                prev_close = float(closes.iloc[-2]) if len(closes) >= 2 else spot

                # Day change
                day_chg_pct = round(((spot - prev_close) / prev_close) * 100.0, 2) if prev_close > 0 else 0.0
                if day_chg_pct > 0.05:
                    advancers += 1
                elif day_chg_pct < -0.05:
                    decliners += 1
                else:
                    unchanged += 1

                # 20 EMA
                ema20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
                above_ema20 = spot > ema20
                if above_ema20:
                    above_ema20_cnt += 1

                # 50 SMA
                sma50 = float(closes.rolling(window=min(50, len(closes))).mean().iloc[-1])
                above_sma50 = spot > sma50
                if above_sma50:
                    above_sma50_cnt += 1

                # 200 SMA (or max available)
                window_200 = min(200, len(closes))
                sma200 = float(closes.rolling(window=window_200).mean().iloc[-1])
                above_sma200 = spot > sma200
                if above_sma200:
                    above_sma200_cnt += 1

                # 52w High / Low proximity
                high_52w = float(df["High"].max())
                low_52w = float(df["Low"].min())
                dist_high_pct = ((high_52w - spot) / high_52w) * 100.0 if high_52w > 0 else 100.0
                dist_low_pct = ((spot - low_52w) / low_52w) * 100.0 if low_52w > 0 else 100.0

                is_near_high = dist_high_pct <= 3.0
                is_near_low = dist_low_pct <= 3.0
                if is_near_high:
                    near_52w_high_cnt += 1
                if is_near_low:
                    near_52w_low_cnt += 1

                results_list.append({
                    "ticker": sym,
                    "spot": round(spot, 2),
                    "day_chg_pct": day_chg_pct,
                    "ema20": round(ema20, 2),
                    "above_ema20": above_ema20,
                    "sma50": round(sma50, 2),
                    "above_sma50": above_sma50,
                    "sma200": round(sma200, 2),
                    "above_sma200": above_sma200,
                    "high_52w": round(high_52w, 2),
                    "dist_52w_high_pct": round(dist_high_pct, 1),
                    "near_52w_high": is_near_high,
                    "near_52w_low": is_near_low,
                })
            except Exception as e:
                logger.debug("Breadth calc error for %s: %s", sym, e)
                continue

        total_valid = len(results_list)
        if total_valid == 0:
            total_valid = 1  # prevent div by zero fallback

        pct_ema20 = round((above_ema20_cnt / total_valid) * 100.0, 1)
        pct_sma50 = round((above_sma50_cnt / total_valid) * 100.0, 1)
        pct_sma200 = round((above_sma200_cnt / total_valid) * 100.0, 1)
        ad_ratio = round(advancers / max(1, decliners), 2)

        # Composite Breadth Score (0-100)
        ad_score_norm = min(100.0, ad_ratio * 40.0)
        cbs = round(
            (0.35 * pct_sma50) +
            (0.30 * pct_ema20) +
            (0.20 * pct_sma200) +
            (0.15 * ad_score_norm),
            1
        )
        cbs = max(0.0, min(100.0, cbs))

        # Regime classification
        if cbs >= 75.0:
            regime = "STRONG_EXPANSION"
            regime_label = "🟢 Starke Marktexpansion (Bullisher Rückenwind)"
            guidance = "Breite Marktteilnahme. Momentum-Ausbrüche besitzen hohe Follow-Through-Wahrscheinlichkeit. Standard-Sizing (1.5%) empfohlen."
        elif cbs >= 55.0:
            regime = "HEALTHY_ACCUMULATION"
            regime_label = "🟢 Gesunde Trendakkumulation"
            guidance = "Mehrheit der Einzeltitel über Trend-Durchschnitten. Gezielte Käufe von Grade A+/A Setups intakt."
        elif cbs >= 40.0:
            regime = "SELECTIVE_CHOP"
            regime_label = "🟡 Selektiver Seitwärtsmarkt / Range"
            guidance = "Gemischte Beteiligung. Nur absolute Leader mit starker Mansfield-Relativstärke handeln. Stops eng absichern."
        elif cbs >= 25.0:
            regime = "INTERNAL_DETERIORATION"
            regime_label = "🟠 Negative Divergenz (Interne Schwäche)"
            guidance = "Achtung: Wenige Mega-Caps stützen die Indizes, während die Marktbreite einbricht. Vorsicht vor Bullenfallen! Risiken auf 0.5%–0.75% reduzieren."
        else:
            regime = "SEVERE_CONTRACTION"
            regime_label = "🔴 Ernsthafte Marktkontraktion / Bären-Regime"
            guidance = "Große Mehrheit unter Schlüssel-Durchschnitten. Kapitalerhalt hat oberste Priorität. Keine aggressiven Breakouts kaufen."

        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sample_size": total_valid,
            "composite_breadth_score": cbs,
            "regime": regime,
            "regime_label": regime_label,
            "guidance": guidance,
            "pct_above_ema20": pct_ema20,
            "pct_above_sma50": pct_sma50,
            "pct_above_sma200": pct_sma200,
            "advance_decline": {
                "advancers": advancers,
                "decliners": decliners,
                "unchanged": unchanged,
                "ratio": ad_ratio,
            },
            "new_highs_lows": {
                "near_52w_high": near_52w_high_cnt,
                "near_52w_low": near_52w_low_cnt,
                "net": near_52w_high_cnt - near_52w_low_cnt,
            },
            "constituents": results_list,
        }

        self._cache = (now, payload)
        return payload

    def format_telegram_breadth_card(self, breadth: Dict[str, Any]) -> str:
        """Formats the institutional market breadth card for Telegram."""
        cbs = breadth.get("composite_breadth_score") if "composite_breadth_score" in breadth else breadth.get("composite_score", 50.0)
        regime_label = breadth.get("regime_label") or breadth.get("regime", "")
        guidance = breadth.get("guidance", "")
        p20 = breadth.get("pct_above_ema20") if "pct_above_ema20" in breadth else breadth.get("pct_above_20_ema", 0.0)
        p50 = breadth.get("pct_above_sma50") if "pct_above_sma50" in breadth else breadth.get("pct_above_50_sma", 0.0)
        p200 = breadth.get("pct_above_sma200") if "pct_above_sma200" in breadth else breadth.get("pct_above_200_sma", 0.0)
        ad = breadth.get("advance_decline", {})
        if not ad and "ad_ratio" in breadth:
            ad = {
                "advancers": breadth.get("advancing_count", 0),
                "decliners": breadth.get("declining_count", 0),
                "ratio": breadth.get("ad_ratio", 1.0),
            }
        nh = breadth.get("new_highs_lows", {})
        sample = breadth.get("sample_size") or breadth.get("scanned_count", 0)

        # Bar representations
        bar_len = 10
        filled = int(round(cbs / 10.0))
        gauge = "█" * filled + "░" * (bar_len - filled)

        adv = ad.get("advancers", 0)
        dec = ad.get("decliners", 0)
        adr = ad.get("ratio", 1.0)
        ad_emoji = "🟢" if adr >= 1.2 else ("🔴" if adr < 0.8 else "🟡")

        return (
            f"🌐 <b>INSTITUTIONELLE MARKTBREITE &amp; INTERNALS</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Composite Breadth Index:</b> <b>{cbs}/100</b>\n"
            f"  ➔ <code>[{gauge}]</code>\n"
            f"• <b>Regime:</b> {regime_label}\n\n"
            f"📊 <b>Gleitende Durchschnitte ({sample} Titel):</b>\n"
            f"• <b>Über 20 EMA (Kurzfristig):</b> <b>{p20:.1f}%</b>\n"
            f"• <b>Über 50 SMA (Mittelfristig):</b> <b>{p50:.1f}%</b>\n"
            f"• <b>Über 200 SMA (Strukturell):</b> <b>{p200:.1f}%</b>\n\n"
            f"⚖️ <b>Advance / Decline Dynamik:</b>\n"
            f"• {ad_emoji} <b>Advancers:</b> {adv} | <b>Decliners:</b> {dec} (Ratio: <b>{adr:.2f}</b>)\n"
            f"• 🎯 <b>52-Wochen-Hoch Nähe (&lt;3%):</b> {nh.get('near_52w_high', 0)} Titel\n"
            f"• ⚠️ <b>52-Wochen-Tief Nähe (&lt;3%):</b> {nh.get('near_52w_low', 0)} Titel\n\n"
            f"💡 <b>Taktischer Leitfaden:</b>\n"
            f"<i>{guidance}</i>"
        )
