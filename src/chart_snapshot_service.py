"""
Chart Snapshot Service — Institutional Dark-Themed Telegram Chart Engine

Generates crisp, high-resolution candlestick charts directly from price feeds:
  • 9 EMA & 21 EMA Trend Ribbon
  • High-impact Asymmetric Trade Levels (Entry, Invalidation Stop, Target 1, Target 2)
  • Volume histogram with color-coded buying/selling pressure
  • Direct Telegram delivery via sendPhoto API
"""
from __future__ import annotations

import io
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

import gc

plt = None  # Lazy-loaded on demand to save ~50 MB baseline RAM

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None  # type: ignore

import requests


def _get_plt():
    global plt
    if plt is not None:
        return plt
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as _plt
        plt = _plt
        return plt
    except Exception as e:  # pragma: no cover
        logger.debug("matplotlib import error: %s", e)
        return None


class ChartSnapshotService:
    def __init__(self, asymmetric_service: Optional[Any] = None) -> None:
        self.asymmetric_service = asymmetric_service

    def generate_chart_png(
        self,
        symbol: str,
        levels: Optional[Dict[str, float]] = None,
        period: str = "60d",
    ) -> Optional[bytes]:
        """
        Generates dark-themed candlestick chart image for a symbol.
        Returns PNG bytes or None if data unavailable.
        """
        active_plt = _get_plt()
        if not active_plt or not yf:
            logger.warning("ChartSnapshotService requires matplotlib and yfinance.")
            return None

        sym = str(symbol).strip().upper()
        if not sym:
            return None

        try:
            ticker = yf.Ticker(sym)
            df = ticker.history(period=period)
            if df.empty or len(df) < 5:
                return None

            # Calculate 9 EMA and 21 EMA
            df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
            df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()

            # Currency symbol
            is_eu = any(sym.endswith(sfx) for sfx in [".DE", ".F", ".AS", ".PA", ".MI", ".MC"])
            c_sym = "€" if is_eu else ("£" if sym.endswith(".L") else "$")

            last_spot = float(df["Close"].iloc[-1])
            prev_close = float(df["Close"].iloc[-2]) if len(df) > 1 else last_spot
            chg_pct = ((last_spot - prev_close) / prev_close) * 100.0

            # Create figure with dark institutional style
            fig, (ax_main, ax_vol) = plt.subplots(
                2,
                1,
                figsize=(10, 5.5),
                gridspec_kw={"height_ratios": [3.2, 1.0], "hspace": 0.08},
                facecolor="#0d1117",
            )
            ax_main.set_facecolor("#161b22")
            ax_vol.set_facecolor("#161b22")

            # X-axis indices
            indices = list(range(len(df)))
            dates = df.index

            # Plot Candlesticks
            width = 0.6
            width2 = 0.12
            up = df[df["Close"] >= df["Open"]]
            down = df[df["Close"] < df["Open"]]

            # Up candles (Green #26a69a)
            if not up.empty:
                up_indices = [df.index.get_loc(idx) for idx in up.index]
                ax_main.bar(up_indices, up["Close"] - up["Open"], width, bottom=up["Open"], color="#26a69a", alpha=0.9)
                ax_main.bar(up_indices, up["High"] - up["Close"], width2, bottom=up["Close"], color="#26a69a", alpha=0.9)
                ax_main.bar(up_indices, up["Low"] - up["Open"], width2, bottom=up["Open"], color="#26a69a", alpha=0.9)

            # Down candles (Red #ef5350)
            if not down.empty:
                down_indices = [df.index.get_loc(idx) for idx in down.index]
                ax_main.bar(down_indices, down["Close"] - down["Open"], width, bottom=down["Open"], color="#ef5350", alpha=0.9)
                ax_main.bar(down_indices, down["High"] - down["Open"], width2, bottom=down["Open"], color="#ef5350", alpha=0.9)
                ax_main.bar(down_indices, down["Low"] - down["Close"], width2, bottom=down["Close"], color="#ef5350", alpha=0.9)

            # Plot EMA 9 & EMA 21
            ax_main.plot(indices, df["EMA9"], color="#38bdf8", linewidth=1.5, label="9 EMA (Fast)", alpha=0.85)
            ax_main.plot(indices, df["EMA21"], color="#f59e0b", linewidth=1.5, label="21 EMA (Base)", alpha=0.85)

            # Overlay Asymmetric Levels if provided
            if not levels and self.asymmetric_service:
                try:
                    ticket = self.asymmetric_service.generate_trade_setup(sym)
                    if ticket and ticket.get("entry_price"):
                        levels = {
                            "entry": float(ticket.get("entry_price") or 0.0),
                            "stop": float(ticket.get("invalidation_price") or 0.0),
                            "target_1": float(ticket.get("target_1") or 0.0),
                            "target_2": float(ticket.get("target_2") or 0.0),
                        }
                except Exception:
                    pass

            if levels:
                entry = levels.get("entry")
                stop = levels.get("stop")
                t1 = levels.get("target_1")
                t2 = levels.get("target_2")

                if entry and entry > 0:
                    ax_main.axhline(entry, color="#10b981", linestyle="-", linewidth=1.2, alpha=0.9)
                    ax_main.text(len(df) - 1, entry, f" Entry {c_sym}{entry:.2f}", color="#10b981", va="center", fontsize=9, fontweight="bold")
                if stop and stop > 0:
                    ax_main.axhline(stop, color="#ef4444", linestyle="-", linewidth=1.2, alpha=0.9)
                    ax_main.text(len(df) - 1, stop, f" Stop {c_sym}{stop:.2f}", color="#ef4444", va="center", fontsize=9, fontweight="bold")
                if t1 and t1 > 0:
                    ax_main.axhline(t1, color="#06b6d4", linestyle="--", linewidth=1.2, alpha=0.9)
                    ax_main.text(len(df) - 1, t1, f" T1 (2.0R) {c_sym}{t1:.2f}", color="#06b6d4", va="center", fontsize=9, fontweight="bold")
                if t2 and t2 > 0:
                    ax_main.axhline(t2, color="#059669", linestyle="--", linewidth=1.2, alpha=0.9)
                    ax_main.text(len(df) - 1, t2, f" T2 (3.5R) {c_sym}{t2:.2f}", color="#059669", va="center", fontsize=9, fontweight="bold")

            # Volume Bar Subplot
            if "Volume" in df.columns:
                vol_colors = ["#26a69a" if c >= o else "#ef5350" for c, o in zip(df["Close"], df["Open"])]
                ax_vol.bar(indices, df["Volume"], color=vol_colors, width=0.7, alpha=0.75)
                ax_vol.set_ylabel("Vol", color="#8b949e", fontsize=8)

            # Styling & Spines
            for ax in (ax_main, ax_vol):
                ax.tick_params(colors="#8b949e", labelsize=8)
                ax.grid(True, color="#21262d", linestyle="--", linewidth=0.5, alpha=0.7)
                for spine in ax.spines.values():
                    spine.set_color("#30363d")

            # Date Formatting on X-axis (sample 6 tick labels)
            tick_step = max(1, len(df) // 6)
            tick_locs = indices[::tick_step]
            tick_labels = [dates[i].strftime("%d.%b") for i in tick_locs]
            ax_vol.set_xticks(tick_locs)
            ax_vol.set_xticklabels(tick_labels, color="#8b949e", fontsize=8)
            ax_main.set_xticks([])

            # Title
            chg_color = "#26a69a" if chg_pct >= 0 else "#ef5350"
            chg_sign = "+" if chg_pct >= 0 else ""
            title_text = f"{sym}   {c_sym}{last_spot:.2f}   ({chg_sign}{chg_pct:.2f}%)"
            ax_main.set_title(title_text, color="#f0f6fc", fontsize=13, fontweight="bold", pad=10, loc="left")

            # Legend
            leg = ax_main.legend(loc="upper left", facecolor="#161b22", edgecolor="#30363d", fontsize=8)
            for text in leg.get_texts():
                text.set_color("#c9d1d9")

            # Export PNG
            buf = io.BytesIO()
            fig.savefig(buf, format="png", bbox_inches="tight", dpi=130, facecolor=fig.get_facecolor())
            fig.clf()
            active_plt.close(fig)
            active_plt.close("all")
            png_bytes = buf.getvalue()
            buf.close()
            del df
            gc.collect()
            try:
                from src.memory_optimizer import _call_linux_malloc_trim
                _call_linux_malloc_trim()
            except Exception:
                pass
            return png_bytes

        except Exception as exc:
            logger.error("Error generating chart for %s: %s", symbol, exc, exc_info=True)
            if active_plt:
                try:
                    active_plt.close("all")
                except Exception:
                    pass
            gc.collect()
            return None

    def send_chart_to_telegram(
        self,
        bot_token: str,
        chat_id: str,
        png_bytes: bytes,
        caption: str = "",
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Uploads PNG chart directly to Telegram chat via sendPhoto API."""
        if not bot_token or not chat_id or not png_bytes:
            return False
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            files = {"photo": ("chart.png", png_bytes, "image/png")}
            data: Dict[str, Any] = {
                "chat_id": chat_id,
                "caption": caption[:1024],
                "parse_mode": "HTML",
            }
            if reply_markup:
                import json
                data["reply_markup"] = json.dumps(reply_markup)

            resp = requests.post(url, data=data, files=files, timeout=20)
            return resp.status_code == 200
        except Exception as exc:
            logger.error("Failed sending chart to Telegram: %s", exc)
            return False
