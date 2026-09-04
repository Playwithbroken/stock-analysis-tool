"""
Trading Signals Service — TIER 1 + TIER 2 edge data.

Aggregates fast actionable signals for daily Telegram briefs:
  1. Squeeze Score (short interest + RSI proxy) per ticker
  2. Insider cluster buys (openinsider.com)
  3. Unusual Options Activity (put/call vol skew vs OI)
  4. Analyst recommendation deltas
  5. Market Regime (VIX + Crypto Fear & Greed)
  6. Pre-market movers
  7. Sector rotation (1d/5d performance of SPDR sector ETFs)
  8. Yield curve spread (2Y/10Y proxy via ^FVX/^TNX)

All methods are best-effort — exceptions are swallowed and an empty/neutral
payload returned, so the morning brief never crashes if a source is down.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore

from src.options_edge_service import OptionsEdgeService
from src.volume_profile_service import VolumeProfileService
from src.asymmetric_trade_service import AsymmetricTradeService
from src.market_regime_service import MarketRegimeService


_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

SECTOR_ETFS = {
    "XLK": "Tech", "XLF": "Financials", "XLE": "Energy",
    "XLV": "Healthcare", "XLY": "Cons Disc", "XLP": "Cons Staples",
    "XLI": "Industrials", "XLB": "Materials", "XLU": "Utilities",
    "XLRE": "Real Estate", "XLC": "Communication",
}


@dataclass
class _Cache:
    ts: float = 0.0
    data: Any = None


class TradingSignalsService:
    # Class-level caches (cheap singletons)
    _c_squeeze: Dict[str, _Cache] = {}
    _c_insider: _Cache = _Cache()
    _c_options: Dict[str, _Cache] = {}
    _c_analyst: Dict[str, _Cache] = {}
    _c_regime: _Cache = _Cache()
    _c_premarket: _Cache = _Cache()
    _c_sectors: _Cache = _Cache()
    _c_yield: _Cache = _Cache()
    _c_gex: Dict[str, _Cache] = {}
    _c_vp: Dict[str, _Cache] = {}
    _c_asymmetric: _Cache = _Cache()

    def __init__(self) -> None:
        self.options_edge = OptionsEdgeService()
        self.volume_profile = VolumeProfileService()
        self.regime_service = MarketRegimeService()
        self.asymmetric_service = AsymmetricTradeService(
            options_service=self.options_edge,
            volume_service=self.volume_profile,
            regime_service=self.regime_service,
        )

    TTL_SHORT = 600       # 10 min
    TTL_MED = 3600        # 1 h
    TTL_LONG = 6 * 3600   # 6 h

    # ---------- 1. Squeeze Score ----------
    def get_squeeze_score(self, ticker: str) -> Optional[Dict[str, Any]]:
        if not yf:
            return None
        cache = self._c_squeeze.get(ticker)
        if cache and time.time() - cache.ts < self.TTL_LONG:
            return cache.data
        try:
            t = yf.Ticker(ticker)
            info = getattr(t, "info", {}) or {}
            short_pct = float(info.get("shortPercentOfFloat") or 0) * 100
            short_ratio = float(info.get("shortRatio") or 0)  # days to cover
            # RSI proxy from last 14 closes
            hist = t.history(period="1mo", interval="1d")
            rsi = self._rsi(hist["Close"].tolist()) if len(hist) > 14 else 50.0
            # Score 0-100: short_pct weight 50, days_to_cover 30, RSI<30 oversold bonus 20
            s = min(100, short_pct * 2.5) * 0.5 \
              + min(100, short_ratio * 10) * 0.3 \
              + (max(0, 50 - rsi) * 2) * 0.2
            payload = {
                "ticker": ticker,
                "score": round(s, 1),
                "short_pct_float": round(short_pct, 2),
                "days_to_cover": round(short_ratio, 2),
                "rsi": round(rsi, 1),
            }
            self._c_squeeze[ticker] = _Cache(time.time(), payload)
            return payload
        except Exception as e:
            logger.debug("squeeze %s: %s", ticker, e)
            return None

    @staticmethod
    def _rsi(closes: List[float], period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        gains, losses = [], []
        for i in range(1, len(closes)):
            d = closes[i] - closes[i - 1]
            (gains if d > 0 else losses).append(abs(d))
        avg_g = sum(gains[-period:]) / period if gains else 0
        avg_l = sum(losses[-period:]) / period if losses else 1e-9
        rs = avg_g / avg_l if avg_l else 100
        return 100 - 100 / (1 + rs)

    # ---------- 2. Insider Cluster Buys ----------
    def get_insider_trades(self, limit: int = 8) -> List[Dict[str, Any]]:
        if self._c_insider.data and time.time() - self._c_insider.ts < self.TTL_MED:
            return self._c_insider.data[:limit]
        out: List[Dict[str, Any]] = []
        try:
            url = "http://openinsider.com/screener?s=&o=&pl=&ph=&ll=&lh=&fd=7&fdr=&td=0&tdr=&fdlyl=&fdlyh=&daysago=&xp=1&xs=1&vl=100&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999&grp=0&nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&sortcol=1&cnt=20&page=1"
            r = requests.get(url, headers=_HEADERS, timeout=15)
            if r.status_code == 200:
                # Very light HTML parsing — rows in <table class="tinytable">
                import re
                rows = re.findall(r"<tr>(.*?)</tr>", r.text, flags=re.S)
                for row in rows:
                    cells = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)
                    if len(cells) < 13:
                        continue
                    def clean(s: str) -> str:
                        return re.sub(r"<[^>]+>", "", s).strip()
                    try:
                        ticker = clean(cells[3])
                        insider = clean(cells[5])
                        title = clean(cells[6])
                        value = clean(cells[12])
                        if ticker and value and "$" in value:
                            out.append({
                                "ticker": ticker, "insider": insider,
                                "title": title, "value": value,
                                "date": clean(cells[1]),
                            })
                    except Exception:
                        continue
                    if len(out) >= 20:
                        break
        except Exception as e:
            logger.debug("insider: %s", e)
        self._c_insider = _Cache(time.time(), out)
        return out[:limit]

    # ---------- 3. Unusual Options Activity ----------
    def get_unusual_options(self, ticker: str) -> Optional[Dict[str, Any]]:
        if not yf:
            return None
        cache = self._c_options.get(ticker)
        if cache and time.time() - cache.ts < self.TTL_SHORT:
            return cache.data
        try:
            t = yf.Ticker(ticker)
            exps = t.options
            if not exps:
                return None
            chain = t.option_chain(exps[0])
            calls_vol = float(chain.calls["volume"].fillna(0).sum())
            puts_vol = float(chain.puts["volume"].fillna(0).sum())
            calls_oi = float(chain.calls["openInterest"].fillna(0).sum())
            puts_oi = float(chain.puts["openInterest"].fillna(0).sum())
            pc_ratio = puts_vol / calls_vol if calls_vol else 0
            vol_oi_calls = calls_vol / calls_oi if calls_oi else 0
            vol_oi_puts = puts_vol / puts_oi if puts_oi else 0
            sentiment = "bullish" if pc_ratio < 0.7 else "bearish" if pc_ratio > 1.3 else "neutral"
            payload = {
                "ticker": ticker, "expiry": exps[0],
                "pc_ratio": round(pc_ratio, 2),
                "calls_vol": int(calls_vol), "puts_vol": int(puts_vol),
                "vol_oi_calls": round(vol_oi_calls, 2),
                "vol_oi_puts": round(vol_oi_puts, 2),
                "sentiment": sentiment,
            }
            self._c_options[ticker] = _Cache(time.time(), payload)
            return payload
        except Exception as e:
            logger.debug("options %s: %s", ticker, e)
            return None

    # ---------- 4. Analyst Actions ----------
    def _clean_analyst_value(self, value: Any) -> str:
        text = str(value or "").strip()
        if text.lower() in {"nan", "none", "null", "n/a", "na", "-", "--"}:
            return ""
        return text

    def get_analyst_actions(self, ticker: str) -> Optional[Dict[str, Any]]:
        if not yf:
            return None
        cache = self._c_analyst.get(ticker)
        if cache and time.time() - cache.ts < self.TTL_MED:
            return cache.data
        try:
            t = yf.Ticker(ticker)
            recs = t.recommendations
            if recs is None or recs.empty:
                return None
            cutoff = datetime.now() - timedelta(days=14)
            recent = recs[recs.index >= cutoff] if hasattr(recs.index, "to_pydatetime") else recs.tail(10)
            actions = []
            for idx, row in recent.iterrows():
                firm = self._clean_analyst_value(row.get("Firm", ""))
                to_grade = self._clean_analyst_value(row.get("To Grade", row.get("toGrade", "")))
                from_grade = self._clean_analyst_value(row.get("From Grade", row.get("fromGrade", "")))
                action = self._clean_analyst_value(row.get("Action", ""))
                if not (firm or to_grade or from_grade or action):
                    continue
                if not (to_grade or action):
                    continue
                if not firm and not from_grade and action.lower() in {"main", "reit", "init", "up", "down"}:
                    continue
                actions.append({
                    "date": str(idx)[:10],
                    "firm": firm,
                    "to": to_grade,
                    "from": from_grade,
                    "action": action,
                })
            if not actions:
                return None
            payload = {"ticker": ticker, "actions": actions[-8:]}
            self._c_analyst[ticker] = _Cache(time.time(), payload)
            return payload
        except Exception as e:
            logger.debug("analyst %s: %s", ticker, e)
            return None

    # ---------- 5. Market Regime ----------
    def get_market_regime(self) -> Dict[str, Any]:
        if self._c_regime.data and time.time() - self._c_regime.ts < self.TTL_SHORT:
            return self._c_regime.data
        out: Dict[str, Any] = {}
        try:
            macro = self.regime_service.get_market_regime()
            out.update(macro)
        except Exception as e:
            logger.debug("market_regime error: %s", e)
        # Crypto Fear & Greed
        try:
            r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
            if r.status_code == 200:
                d = r.json().get("data", [{}])[0]
                out["crypto_fng"] = {
                    "value": int(d.get("value", 50)),
                    "label": d.get("value_classification", "Neutral"),
                }
        except Exception as e:
            logger.debug("fng: %s", e)
        self._c_regime = _Cache(time.time(), out)
        return out

    # ---------- 6. Pre-Market Movers (top tickers from watchlist) ----------
    def get_premarket_movers(self, tickers: List[str], limit: int = 5) -> List[Dict[str, Any]]:
        if not yf or not tickers:
            return []
        if self._c_premarket.data and time.time() - self._c_premarket.ts < self.TTL_SHORT:
            return self._c_premarket.data[:limit]
        movers = []
        for tk in tickers[:30]:
            try:
                info = yf.Ticker(tk).info or {}
                pre = info.get("preMarketPrice") or info.get("regularMarketPreMarketPrice")
                prev = info.get("regularMarketPreviousClose") or info.get("previousClose")
                if pre and prev:
                    chg_pct = (pre - prev) / prev * 100
                    if abs(chg_pct) >= 1.0:
                        movers.append({"ticker": tk, "pre": round(pre, 2),
                                       "prev_close": round(prev, 2),
                                       "change_pct": round(chg_pct, 2)})
            except Exception:
                continue
        movers.sort(key=lambda m: abs(m["change_pct"]), reverse=True)
        self._c_premarket = _Cache(time.time(), movers)
        return movers[:limit]

    # ---------- 7. Sector Rotation ----------
    def get_sector_rotation(self) -> List[Dict[str, Any]]:
        if self._c_sectors.data and time.time() - self._c_sectors.ts < self.TTL_MED:
            return self._c_sectors.data
        if not yf:
            return []
        out = []
        for tk, name in SECTOR_ETFS.items():
            try:
                hist = yf.Ticker(tk).history(period="1mo", interval="1d")
                if len(hist) < 6:
                    continue
                close = hist["Close"]
                d1 = (close.iloc[-1] / close.iloc[-2] - 1) * 100
                d5 = (close.iloc[-1] / close.iloc[-6] - 1) * 100
                out.append({"ticker": tk, "name": name,
                            "change_1d": round(float(d1), 2),
                            "change_5d": round(float(d5), 2)})
            except Exception:
                continue
        out.sort(key=lambda x: x["change_5d"], reverse=True)
        self._c_sectors = _Cache(time.time(), out)
        return out

    # ---------- 8. Yield Curve ----------
    def get_yield_curve(self) -> Dict[str, Any]:
        if self._c_yield.data and time.time() - self._c_yield.ts < self.TTL_MED:
            return self._c_yield.data
        if not yf:
            return {}
        out = {}
        try:
            tnx = float(yf.Ticker("^TNX").history(period="5d")["Close"].iloc[-1])  # 10Y
            fvx = float(yf.Ticker("^FVX").history(period="5d")["Close"].iloc[-1])  # 5Y
            tyx = float(yf.Ticker("^TYX").history(period="5d")["Close"].iloc[-1])  # 30Y
            spread_10_5 = tnx - fvx
            out = {
                "us10y": round(tnx, 3),
                "us5y": round(fvx, 3),
                "us30y": round(tyx, 3),
                "spread_10y_5y": round(spread_10_5, 3),
                "inverted": spread_10_5 < 0,
            }
        except Exception as e:
            logger.debug("yield: %s", e)
        self._c_yield = _Cache(time.time(), out)
        return out

    # ---------- 9. Gamma Exposure (GEX) ----------
    def get_gex_profile(self, ticker: str) -> Optional[Dict[str, Any]]:
        cached = self._c_gex.get(ticker)
        if cached and time.time() - cached.ts < self.TTL_SHORT:
            return cached.data
        res = self.options_edge.analyze_gex(ticker)
        if res:
            self._c_gex[ticker] = _Cache(time.time(), res)
        return res

    # ---------- 10. Volume Profile (POC, VAH, VAL) ----------
    def get_volume_profile(self, ticker: str) -> Optional[Dict[str, Any]]:
        cached = self._c_vp.get(ticker)
        if cached and time.time() - cached.ts < self.TTL_SHORT:
            return cached.data
        res = self.volume_profile.compute_volume_profile(ticker)
        if res:
            self._c_vp[ticker] = _Cache(time.time(), res)
        return res

    # ---------- 11. Asymmetric Trade Setups (2.5:1+ R:R) ----------
    def get_asymmetric_setups(
        self,
        watchlist: List[str],
        portfolio_capital: float = 50000.0,
        risk_budget_pct: float = 0.75,
        limit: int = 4,
    ) -> List[Dict[str, Any]]:
        cached = self._c_asymmetric
        if cached.data and time.time() - cached.ts < self.TTL_SHORT:
            return cached.data[:limit]

        candidates = [tk for tk in watchlist if tk and not tk.startswith("^")][:8]
        # Always ensure key market leaders are represented if watchlist is small
        defaults = ["NVDA", "AAPL", "MSFT", "TSLA", "SPY", "QQQ"]
        for d in defaults:
            if d not in candidates and len(candidates) < 8:
                candidates.append(d)

        setups: List[Dict[str, Any]] = []
        for tk in candidates:
            try:
                setup = self.asymmetric_service.generate_trade_setup(
                    ticker=tk,
                    portfolio_capital=portfolio_capital,
                    risk_budget_pct=risk_budget_pct,
                )
                if setup and setup.get("risk_reward_ratio", 0) >= 2.0:
                    setups.append(setup)
            except Exception as e:
                logger.debug("setup generation for %s failed: %s", tk, e)
                continue

        setups.sort(key=lambda s: float(s.get("risk_reward_ratio") or 0), reverse=True)
        self._c_asymmetric = _Cache(time.time(), setups)
        return setups[:limit]

    def scan_and_dispatch_edge_alerts(
        self,
        alert_service: Any,
        watchlist: Optional[List[str]] = None,
        min_grade: tuple = ("A+", "A"),
        limit: int = 4,
    ) -> Dict[str, Any]:
        """
        Background scanner: evaluates setups across watchlist and dispatches
        high-conviction (Grade A+/A) trade cards to Telegram with deduplication.
        """
        if not alert_service:
            return {"status": "skipped", "reason": "No alert service provided"}

        tickers = list(watchlist or ["NVDA", "AAPL", "MSFT", "TSLA", "META", "AMZN", "GOOGL"])
        setups = self.get_asymmetric_setups(tickers, limit=limit * 2)

        dispatched = []
        deduped = []
        skipped = []

        for setup in setups:
            grade = setup.get("grade")
            score = setup.get("confluence_score", 0)
            ticker = setup.get("ticker")

            if grade not in min_grade and score < 70:
                skipped.append(ticker)
                continue

            # Dispatch via alert service (force=False ensures 1-push-per-day deduplication)
            res = alert_service.send_trading_edge_setup_alert(setup, force=False)
            if res.get("status") == "ok":
                dispatched.append(ticker)
            elif res.get("status") == "deduplicated":
                deduped.append(ticker)
            else:
                skipped.append(ticker)

        return {
            "status": "ok",
            "scanned_count": len(setups),
            "dispatched": dispatched,
            "deduplicated": deduped,
            "skipped": skipped,
        }

    # ---------- Aggregator ----------
    def get_full_edge_pack(self, watchlist: List[str]) -> Dict[str, Any]:
        """Build the entire trading edge payload in one call."""
        squeeze = []
        for tk in watchlist[:10]:
            s = self.get_squeeze_score(tk)
            if s and s["score"] >= 30:
                squeeze.append(s)
        squeeze.sort(key=lambda x: x["score"], reverse=True)

        options = []
        for tk in watchlist[:8]:
            o = self.get_unusual_options(tk)
            if o and (o["pc_ratio"] < 0.5 or o["pc_ratio"] > 1.5):
                options.append(o)

        analyst = []
        for tk in watchlist[:8]:
            a = self.get_analyst_actions(tk)
            if a and a["actions"]:
                analyst.append(a)

        # GEX profiles for top watchlist / market leaders
        gex_profiles = []
        for tk in watchlist[:4]:
            g = self.get_gex_profile(tk)
            if g:
                gex_profiles.append(g)

        # Volume profiles for top watchlist / market leaders
        volume_profiles = []
        for tk in watchlist[:4]:
            vp = self.get_volume_profile(tk)
            if vp:
                volume_profiles.append(vp)

        # Asymmetric setups with min 2.5:1 R:R
        asymmetric_setups = self.get_asymmetric_setups(watchlist, limit=4)

        return {
            "squeeze": squeeze[:5],
            "insider": self.get_insider_trades(limit=6),
            "options": options[:5],
            "analyst": analyst[:5],
            "regime": self.get_market_regime(),
            "premarket": self.get_premarket_movers(watchlist, limit=5),
            "sectors": self.get_sector_rotation(),
            "yield_curve": self.get_yield_curve(),
            "gex_profiles": gex_profiles,
            "volume_profiles": volume_profiles,
            "asymmetric_setups": asymmetric_setups,
        }
