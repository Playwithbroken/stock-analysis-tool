"""
Macro Commodity & Crypto Radar Service

Monitors global macro assets & digital assets outside traditional equities:
  1. Precious Metals: Gold (GLD), Silver (SLV)
  2. Energy & Industrial: Crude Oil (USO), Natural Gas (UNG), Copper (CPER)
  3. Macro Anchors: US Dollar Index (UUP), 20Y+ Treasuries (TLT)
  4. Digital Crypto Leaders: Bitcoin (BTC-USD), Ethereum (ETH-USD), Solana (SOL-USD)

Generates:
  • Intermarket Trend Regime (50/200 SMA Golden/Death Cross & 20 EMA Momentum)
  • Macro Confluence Analysis (Dollar weakness + Yield drop = Bullish tailwind for Gold & BTC)
  • Institutional German Telegram cards with 1-tap chart and setup action buttons
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None  # type: ignore


class MacroCommodityCryptoService:
    COMMODITIES = {
        "GLD": {"name": "Gold ETF (Physical)", "type": "Precious Metal", "c_sym": "$"},
        "SLV": {"name": "Silver Trust ETF", "type": "Precious Metal", "c_sym": "$"},
        "USO": {"name": "WTI Crude Oil Fund", "type": "Energy", "c_sym": "$"},
        "UNG": {"name": "US Natural Gas Fund", "type": "Energy", "c_sym": "$"},
        "CPER": {"name": "Copper Index Fund", "type": "Industrial Metal", "c_sym": "$"},
    }

    MACRO_ANCHORS = {
        "UUP": {"name": "US Dollar Index Bullish Fund", "type": "Currency (USD)", "c_sym": "$"},
        "TLT": {"name": "iShares 20+ Year Treasury Bond", "type": "Bonds / Yields", "c_sym": "$"},
    }

    CRYPTO_ASSETS = {
        "BTC-USD": {"name": "Bitcoin", "type": "Store of Value / Layer 1", "c_sym": "$"},
        "ETH-USD": {"name": "Ethereum", "type": "Smart Contracts / DeFi", "c_sym": "$"},
        "SOL-USD": {"name": "Solana", "type": "High-Throughput L1", "c_sym": "$"},
    }

    def __init__(self) -> None:
        pass

    def _fetch_asset_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetches spot, 1d change, moving averages, and trend status for a symbol."""
        if not yf:
            return None
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period="1y")
            if hist.empty or len(hist) < 20:
                return None

            close_series = hist["Close"]
            spot = float(close_series.iloc[-1])
            prev = float(close_series.iloc[-2]) if len(close_series) > 1 else spot
            pct_chg = ((spot - prev) / prev) * 100.0

            ema20 = float(close_series.ewm(span=20, adjust=False).mean().iloc[-1])
            sma50 = float(close_series.rolling(50).mean().iloc[-1]) if len(close_series) >= 50 else ema20
            sma200 = float(close_series.rolling(200).mean().iloc[-1]) if len(close_series) >= 200 else sma50

            # Trend Determination
            if spot > sma50 and sma50 > sma200:
                trend_state = "BULLISH_TREND"
                badge = "🟢 Stier-Trend"
            elif spot < sma50 and sma50 < sma200:
                trend_state = "BEARISH_TREND"
                badge = "🔴 Bär-Trend"
            elif spot > ema20:
                trend_state = "MOMENTUM_PULLBACK"
                badge = "🟡 Momentum-Rebound"
            else:
                trend_state = "CONSOLIDATION"
                badge = "⚪ Konsolidierung"

            # 14-day RSI
            delta = close_series.diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.rolling(14).mean().iloc[-1]
            avg_loss = loss.rolling(14).mean().iloc[-1]
            rs = avg_gain / avg_loss if avg_loss != 0 else 1.0
            rsi = 100.0 - (100.0 / (1.0 + rs)) if (1.0 + rs) != 0 else 50.0

            return {
                "symbol": symbol,
                "spot": round(spot, 2),
                "pct_change_1d": round(pct_chg, 2),
                "ema20": round(ema20, 2),
                "sma50": round(sma50, 2),
                "sma200": round(sma200, 2),
                "rsi14": round(rsi, 1),
                "trend_state": trend_state,
                "badge": badge,
            }
        except Exception as exc:
            logger.debug("Failed fetching macro asset %s: %s", symbol, exc)
            return None

    def get_commodities_overview(self) -> Dict[str, Any]:
        """Scans all commodity and macro anchor assets."""
        results = {}
        for sym, meta in {**self.COMMODITIES, **self.MACRO_ANCHORS}.items():
            data = self._fetch_asset_data(sym)
            if data:
                data.update(meta)
                results[sym] = data
        return results

    def get_crypto_overview(self) -> Dict[str, Any]:
        """Scans all leading cryptocurrency assets."""
        results = {}
        for sym, meta in self.CRYPTO_ASSETS.items():
            data = self._fetch_asset_data(sym)
            if data:
                data.update(meta)
                results[sym] = data
        return results

    def format_commodities_card(self) -> str:
        """Formats an executive commodities & macro anchor Telegram briefing."""
        data = self.get_commodities_overview()
        if not data:
            return "⚠️ Rohstoff-Daten aktuell nicht verfügbar."

        lines = [
            "🪙 <b>ROHSTOFF- &amp; MAKRO-RADAR</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "<i>Institutionelle Ströme in Edelmetallen, Energie &amp; Währungen:</i>\n",
        ]

        # Precious Metals
        lines.append("🌟 <b>Edelmetalle (Sicherer Hafen):</b>")
        for sym in ["GLD", "SLV"]:
            item = data.get(sym)
            if item:
                sgn = "+" if item["pct_change_1d"] >= 0 else ""
                lines.append(
                    f"• <b>{sym} ({item['name']}):</b> ${item['spot']:.2f} ({sgn}{item['pct_change_1d']:.2f}%) "
                    f"| {item['badge']} | RSI {item['rsi14']:.0f}"
                )

        # Energy & Industrials
        lines.append("\n🛢️ <b>Energie &amp; Industrie:</b>")
        for sym in ["USO", "UNG", "CPER"]:
            item = data.get(sym)
            if item:
                sgn = "+" if item["pct_change_1d"] >= 0 else ""
                lines.append(
                    f"• <b>{sym} ({item['name']}):</b> ${item['spot']:.2f} ({sgn}{item['pct_change_1d']:.2f}%) "
                    f"| {item['badge']} | RSI {item['rsi14']:.0f}"
                )

        # Macro Anchors (USD & Treasuries)
        lines.append("\n🏛️ <b>Makro-Taktgeber (Dollar &amp; Anleihen):</b>")
        for sym in ["UUP", "TLT"]:
            item = data.get(sym)
            if item:
                sgn = "+" if item["pct_change_1d"] >= 0 else ""
                lines.append(
                    f"• <b>{sym} ({item['name']}):</b> ${item['spot']:.2f} ({sgn}{item['pct_change_1d']:.2f}%) "
                    f"| {item['badge']}"
                )

        # Macro Synthesis
        uup = data.get("UUP")
        gld = data.get("GLD")
        tlt = data.get("TLT")
        lines.append("\n💡 <b>Makro-Konfluenz:</b>")
        if uup and gld and uup["pct_change_1d"] < -0.2 and gld["pct_change_1d"] > 0.3:
            lines.append("• 🟢 <b>Dollar-Schwäche:</b> Rückenwind für Gold, Silber und Krypto!")
        elif uup and uup["pct_change_1d"] > 0.4:
            lines.append("• 🔴 <b>Starker Dollar (Liquiditätsabzug):</b> Bremsklotz für Rohstoffe & Tech-Wachstumswerte.")
        else:
            lines.append("• ⚖️ <b>Neutrale Währungsdynamik:</b> Gezieltes Stock-Picking hat Vorrang.")

        return "\n".join(lines)

    def format_crypto_card(self) -> str:
        """Formats an executive cryptocurrency Telegram briefing."""
        data = self.get_crypto_overview()
        if not data:
            return "⚠️ Krypto-Daten aktuell nicht verfügbar."

        lines = [
            "₿ <b>KRYPTO-RADAR &amp; DIGITALE ASSETS</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "<i>Trend-Alignment &amp; Relative Stärke der Top-Assets (24/7):</i>\n",
        ]

        for sym in ["BTC-USD", "ETH-USD", "SOL-USD"]:
            item = data.get(sym)
            if item:
                clean_name = item["name"]
                sgn = "+" if item["pct_change_1d"] >= 0 else ""
                spot_formatted = f"${item['spot']:,.2f}" if item['spot'] >= 1000 else f"${item['spot']:.2f}"
                lines.append(
                    f"• <b>{clean_name} ({sym.split('-')[0]}):</b> <b>{spot_formatted}</b> ({sgn}{item['pct_change_1d']:.2f}%)\n"
                    f"  Status: {item['badge']} | 20 EMA: ${item['ema20']:,.0f} | RSI: {item['rsi14']:.0f}\n"
                    f"  50 SMA: ${item['sma50']:,.0f} | 200 SMA: ${item['sma200']:,.0f}"
                )

        btc = data.get("BTC-USD")
        if btc:
            spot = btc["spot"]
            ema20 = btc["ema20"]
            lines.append("\n🎯 <b>Bitcoin Trading-Regel:</b>")
            if spot > ema20:
                lines.append(f"• 🟢 Kurs über 20 EMA (${ema20:,.0f}): Trendfolge-Longs intakt. Dips kaufen.")
            else:
                lines.append(f"• ⚠️ Kurs unter 20 EMA (${ema20:,.0f}): Konsolidierung aktiv. Geduldig auf Umkehrkerze warten.")

        return "\n".join(lines)
