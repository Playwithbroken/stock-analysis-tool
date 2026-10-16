"""
Asymmetric Trade Service — High Conviction Setups with Institutional Confluence

Combines:
  1. Market Maker Gamma Exposure (GEX)
  2. Auction Market Theory (Volume Profile POC / VAH / VAL)
  3. Macro Market & Volatility Regime (SPY, QQQ, VIX filter)
  4. Mathematical Asymmetric Risk-Reward: Min 2.5:1 R:R, structural invalidation
  5. Deterministic Confluence Scoring (0-100 pts) & Grading (A+, A, B)
  6. Exact Portfolio Risk Sizing: fixed 0.75%–1.0% account risk ticket
  7. Visual Chart Overlay Coordinate Bundle
  8. Smartphone Telegram Card Formatter
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.options_edge_service import OptionsEdgeService
from src.volume_profile_service import VolumeProfileService
from src.market_regime_service import MarketRegimeService
from src.relative_strength_service import RelativeStrengthService
from src.anchored_vwap_service import AnchoredVWAPService
from src.whale_flow_service import WhaleFlowService
from src.liquidity_zone_service import LiquidityZoneService
from src.multi_timeframe_service import MultiTimeframeService
from src.trading_coach_service import TradingCoachService

logger = logging.getLogger(__name__)

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore


GERMAN_WKN_ISIN_REGISTRY: Dict[str, Dict[str, str]] = {
    "NVDA": {"wkn": "918422", "isin": "US67066G1040", "name": "NVIDIA Corp."},
    "AAPL": {"wkn": "865985", "isin": "US0378331005", "name": "Apple Inc."},
    "MSFT": {"wkn": "870747", "isin": "US5949181045", "name": "Microsoft Corp."},
    "AMZN": {"wkn": "906866", "isin": "US0231351067", "name": "Amazon.com Inc."},
    "META": {"wkn": "A1JWVX", "isin": "US30303M1027", "name": "Meta Platforms Inc."},
    "GOOGL": {"wkn": "A14Y6F", "isin": "US02079K3059", "name": "Alphabet Inc. (Class A)"},
    "GOOG": {"wkn": "A14Y6H", "isin": "US02079K1079", "name": "Alphabet Inc. (Class C)"},
    "TSLA": {"wkn": "A1CX3T", "isin": "US88160R1014", "name": "Tesla Inc."},
    "PLTR": {"wkn": "A2QA4J", "isin": "US69608A1088", "name": "Palantir Technologies"},
    "AMD": {"wkn": "863186", "isin": "US0079031078", "name": "Advanced Micro Devices"},
    "AVGO": {"wkn": "A2JG9Z", "isin": "US11135F1012", "name": "Broadcom Inc."},
    "NFLX": {"wkn": "552484", "isin": "US64110L1061", "name": "Netflix Inc."},
    "LLY": {"wkn": "858560", "isin": "US5324571083", "name": "Eli Lilly and Co."},
    "BRK-B": {"wkn": "A0YJQ2", "isin": "US0846707026", "name": "Berkshire Hathaway B"},
    "JPM": {"wkn": "850628", "isin": "US46625H1005", "name": "JPMorgan Chase & Co."},
    "V": {"wkn": "A0NC7B", "isin": "US92826C8394", "name": "Visa Inc."},
    "MA": {"wkn": "A0F602", "isin": "US57636Q1040", "name": "Mastercard Inc."},
    "CRM": {"wkn": "A0B87V", "isin": "US79466L3024", "name": "Salesforce Inc."},
    "ORCL": {"wkn": "871460", "isin": "US68389X1054", "name": "Oracle Corp."},
    "COIN": {"wkn": "A2QP7J", "isin": "US19260Q1076", "name": "Coinbase Global"},
    "MSTR": {"wkn": "722713", "isin": "US5949724083", "name": "Strategy (MicroStrategy)"},
    "SMCI": {"wkn": "A0MKJF", "isin": "US86800U1043", "name": "Super Micro Computer"},
    "ARM": {"wkn": "A3EUCD", "isin": "US0420682058", "name": "Arm Holdings plc"},
    "MU": {"wkn": "869020", "isin": "US5951121038", "name": "Micron Technology"},
    "INTC": {"wkn": "855681", "isin": "US4581401001", "name": "Intel Corp."},
    "QCOM": {"wkn": "883121", "isin": "US7475251036", "name": "Qualcomm Inc."},
    "UBER": {"wkn": "A2PHHG", "isin": "US90353T1007", "name": "Uber Technologies"},
    "PANW": {"wkn": "A1JZ0Q", "isin": "US6974351057", "name": "Palo Alto Networks"},
    "CRWD": {"wkn": "A2PK2R", "isin": "US22788C1053", "name": "CrowdStrike Holdings"},
    "NOW": {"wkn": "A1JX4P", "isin": "US81762P1021", "name": "ServiceNow Inc."},
    "SNOW": {"wkn": "A2QB38", "isin": "US8334451098", "name": "Snowflake Inc."},
    "SHOP": {"wkn": "A14TJP", "isin": "CA82509L1076", "name": "Shopify Inc."},
    "SAP.DE": {"wkn": "716460", "isin": "DE0007164600", "name": "SAP SE"},
    "SAP": {"wkn": "716460", "isin": "DE0007164600", "name": "SAP SE"},
    "RHM.DE": {"wkn": "703000", "isin": "DE0007030009", "name": "Rheinmetall AG"},
    "SIE.DE": {"wkn": "723610", "isin": "DE0007236101", "name": "Siemens AG"},
    "ALV.DE": {"wkn": "840400", "isin": "DE0008404005", "name": "Allianz SE"},
    "MUV2.DE": {"wkn": "843002", "isin": "DE0008430026", "name": "Münchener Rück"},
    "IFX.DE": {"wkn": "623100", "isin": "DE0006231004", "name": "Infineon Technologies"},
    "DTG.DE": {"wkn": "DTR0CK", "isin": "DE000DTR0CK8", "name": "Daimler Truck Holding"},
    "DTE.DE": {"wkn": "555750", "isin": "DE0005557508", "name": "Deutsche Telekom AG"},
    "MBG.DE": {"wkn": "710000", "isin": "DE0007100000", "name": "Mercedes-Benz Group"},
    "BMW.DE": {"wkn": "519000", "isin": "DE0005190003", "name": "BMW AG"},
    "ADS.DE": {"wkn": "A1EWWW", "isin": "DE000A1EWWW0", "name": "adidas AG"},
    "DBK.DE": {"wkn": "514000", "isin": "DE0005140008", "name": "Deutsche Bank AG"},
    "CBK.DE": {"wkn": "CBK100", "isin": "DE000CBK1001", "name": "Commerzbank AG"},
    "ENR.DE": {"wkn": "ENER6Y", "isin": "DE000ENER6Y0", "name": "Siemens Energy AG"},
    "ASML.AS": {"wkn": "A1J4U4", "isin": "NL0010273215", "name": "ASML Holding N.V."},
    "ASML": {"wkn": "A1J4U4", "isin": "NL0010273215", "name": "ASML Holding N.V."},
    "MC.PA": {"wkn": "853292", "isin": "FR0000121014", "name": "LVMH Moët Hennessy"},
    "NOVO-B.CO": {"wkn": "A3EU6F", "isin": "DK0062498333", "name": "Novo Nordisk A/S"},
    "NVO": {"wkn": "A3EU6F", "isin": "DK0062498333", "name": "Novo Nordisk A/S"},
}


def get_wkn_isin(ticker: str) -> Dict[str, str]:
    """Resolves a ticker symbol to its German WKN and ISIN for Trade Republic / Scalable / ING."""
    sym = str(ticker or "").strip().upper()
    if sym in GERMAN_WKN_ISIN_REGISTRY:
        info = GERMAN_WKN_ISIN_REGISTRY[sym]
        return {
            "ticker": sym,
            "wkn": info["wkn"],
            "isin": info["isin"],
            "name": info["name"],
            "found": "true",
        }
    base = sym.split(".")[0]
    if base in GERMAN_WKN_ISIN_REGISTRY:
        info = GERMAN_WKN_ISIN_REGISTRY[base]
        return {
            "ticker": sym,
            "wkn": info["wkn"],
            "isin": info["isin"],
            "name": info["name"],
            "found": "true",
        }
    return {
        "ticker": sym,
        "wkn": f"Suche: {base}",
        "isin": f"Ticker {sym}",
        "name": sym,
        "found": "false",
    }


def compute_german_net_tax(
    gross_tp1_eur: float,
    gross_tp2_eur: float,
    gross_risk_eur: float,
    order_fee_eur: float = 1.0,
) -> Dict[str, float]:
    """
    Calculates German net profit after 26.375% Abgeltungsteuer + Soli and broker order fees
    (e.g., 1.00 € per execution at Trade Republic / Scalable Capital), plus Verlustverrechnungstopf credit.
    """
    tax_rate = 0.26375  # 25% Abgeltungsteuer + 5.5% Solidaritätszuschlag
    roundtrip_fee = round(order_fee_eur * 2.0, 2)

    taxable_tp1 = max(0.0, gross_tp1_eur - roundtrip_fee)
    tax_tp1 = round(taxable_tp1 * tax_rate, 2)
    net_tp1 = round(max(0.0, gross_tp1_eur - tax_tp1 - roundtrip_fee), 2)

    taxable_tp2 = max(0.0, gross_tp2_eur - roundtrip_fee)
    tax_tp2 = round(taxable_tp2 * tax_rate, 2)
    net_tp2 = round(max(0.0, gross_tp2_eur - tax_tp2 - roundtrip_fee), 2)

    gross_loss_with_fee = round(abs(gross_risk_eur) + roundtrip_fee, 2)
    tax_shield_credit = round(gross_loss_with_fee * tax_rate, 2)
    effective_net_risk = round(gross_loss_with_fee - tax_shield_credit, 2)

    gross_buffer_loss = round(abs(gross_risk_eur) * 0.25 + roundtrip_fee, 2)
    net_buffer_loss = round(gross_buffer_loss * (1.0 - tax_rate), 2)

    return {
        "tax_rate_pct": 26.375,
        "roundtrip_fee_eur": roundtrip_fee,
        "gross_tp1_eur": round(gross_tp1_eur, 2),
        "tax_tp1_eur": tax_tp1,
        "net_tp1_eur": net_tp1,
        "gross_tp2_eur": round(gross_tp2_eur, 2),
        "tax_tp2_eur": tax_tp2,
        "net_tp2_eur": net_tp2,
        "gross_risk_eur": round(abs(gross_risk_eur), 2),
        "tax_shield_credit_eur": tax_shield_credit,
        "effective_net_risk_eur": effective_net_risk,
        "gross_buffer_025r_eur": gross_buffer_loss,
        "net_buffer_025r_eur": net_buffer_loss,
    }


def evaluate_entry_timing(
    ticker: str,
    spot: Optional[float] = None,
    entry_price: Optional[float] = None,
    risk_per_share: Optional[float] = None,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Evaluates intraday execution timing (German XETRA & US Wall Street opening spread traps)
    and checks whether the current price is already extended above Entry (Anti-FOMO / Anti-Chasing).
    """
    dt = now_utc or datetime.now(timezone.utc)
    # Approximate CET/CEST (UTC+2 in summer, UTC+1 in winter)
    month = dt.month
    cet_offset = 2 if 4 <= month <= 10 else 1
    cet_hour = (dt.hour + cet_offset) % 24
    cet_min = dt.minute
    cet_Minutes = cet_hour * 60 + cet_min
    is_weekend = dt.weekday() >= 5

    sym = str(ticker or "").strip().upper()
    is_eu = any(sym.endswith(sfx) for sfx in [".DE", ".F", ".AS", ".PA", ".MI", ".MC"])

    if is_weekend:
        session_status = "WEEKEND_CLOSED"
        session_badge = "🟡 Wochenende (Börse geschlossen – Limit-Order für Montagvormittag ab 09:15 Uhr planen)"
        spread_quality = "Börse geschlossen"
    elif 9 * 60 <= cet_Minutes < 9 * 60 + 15:
        session_status = "WAIT_OPEN_VOLATILITY"
        session_badge = "🔴 XETRA-Eröffnung (09:00–09:15 Uhr): Hohe Spreads & Stop-Hunts! 15 Min warten!"
        spread_quality = "Breit (Amateur-Hour)"
    elif not is_eu and (15 * 60 + 30 <= cet_Minutes < 15 * 60 + 45):
        session_status = "WAIT_OPEN_VOLATILITY"
        session_badge = "🔴 US-Eröffnung (15:30–15:45 Uhr): Wall-Street Stop-Hunt Phase! Bis 15:45 Uhr warten!"
        spread_quality = "Extrem volatil (Eröffnungs-Shakeout)"
    elif not is_eu and (9 * 60 + 15 <= cet_Minutes < 15 * 60 + 30):
        session_status = "PRE_US_OPEN"
        session_badge = "🟡 US-Vorbörse auf XETRA/Tradegate: Leicht erhöhter Spread – streng mit Limit-Order arbeiten (Optimum ab 15:45 Uhr)"
        spread_quality = "Mittel (Vorbörslich US)"
    elif (9 * 60 + 15 <= cet_Minutes <= 17 * 60 + 30) or (not is_eu and 15 * 60 + 45 <= cet_Minutes <= 21 * 60 + 50):
        session_status = "PRIME_INSTITUTIONAL"
        session_badge = "🟢 Prime-Handelsfenster: Maximale Liquidität & engste institutionelle Spreads"
        spread_quality = "Exzellent (Enge Spreads)"
    else:
        session_status = "AFTER_HOURS"
        session_badge = "🟡 Randhandelszeit / After-Hours: Verbreiterte Spreads – niemals Market-Orders nutzen!"
        spread_quality = "Erhöht (Randzeit)"

    extension_r = 0.0
    is_chasing = False
    chasing_badge = "✅ Kurs im optimalen Einstiegs-Korridor (Kein FOMO-Chasing)"
    if spot and entry_price and risk_per_share and risk_per_share > 0:
        extension_r = round((spot - entry_price) / risk_per_share, 2)
        if extension_r > 0.40:
            is_chasing = True
            chasing_badge = (
                f"🚫 ANTI-FOMO WARNUNG: Kurs ist bereits +{extension_r:.2f}R über Entry davongelaufen! "
                f"Nicht hinterherspringen – Kauflimit stur bei {entry_price:.2f} belassen!"
            )
        elif extension_r < -0.35:
            chasing_badge = (
                f"⏳ Geduld: Kurs notiert {extension_r:+.2f}R unter Trigger – erst bei Rückeroberung von {entry_price:.2f} aktiv werden."
            )
        else:
            chasing_badge = (
                f"🟢 Perfekter Einstiegs-Korridor ({extension_r:+.2f}R vom Entry) – Limit-Order direkt ausführbar."
            )

    return {
        "ticker": sym,
        "cet_time": f"{cet_hour:02d}:{cet_min:02d} Uhr",
        "session_status": session_status,
        "session_badge": session_badge,
        "spread_quality": spread_quality,
        "extension_r": extension_r,
        "is_chasing": is_chasing,
        "chasing_badge": chasing_badge,
        "best_window_hint": "09:15–11:30 Uhr & 15:45–17:30 Uhr (DE/EU) | 15:45–17:30 Uhr & 20:00–21:45 Uhr (US)",
    }


class AsymmetricTradeService:
    def __init__(
        self,
        options_service: Optional[OptionsEdgeService] = None,
        volume_service: Optional[VolumeProfileService] = None,
        regime_service: Optional[MarketRegimeService] = None,
        relative_strength_service: Optional[RelativeStrengthService] = None,
        anchored_vwap_service: Optional[AnchoredVWAPService] = None,
        whale_flow_service: Optional[WhaleFlowService] = None,
        liquidity_zone_service: Optional[LiquidityZoneService] = None,
        multi_timeframe_service: Optional[MultiTimeframeService] = None,
        coach_service: Optional[TradingCoachService] = None,
        portfolio_manager: Optional[Any] = None,
    ) -> None:
        self.options_service = options_service or OptionsEdgeService()
        self.volume_service = volume_service or VolumeProfileService()
        self.regime_service = regime_service or MarketRegimeService()
        self.rs_service = relative_strength_service or RelativeStrengthService()
        self.avwap_service = anchored_vwap_service or AnchoredVWAPService()
        self.whale_service = whale_flow_service or WhaleFlowService()
        self.liquidity_service = liquidity_zone_service or LiquidityZoneService()
        self.mtf_service = multi_timeframe_service or MultiTimeframeService()
        self.coach_service = coach_service or TradingCoachService(portfolio_manager=portfolio_manager)

    def generate_trade_setup(
        self,
        ticker: str,
        portfolio_capital: float = 50000.0,
        risk_budget_pct: float = 0.75,
        catalyst_override: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Generates a high-conviction trade setup card combining GEX, Volume Profile,
        Macro Regime, and mathematical 2.5+:1 R:R invalidation levels.
        """
        symbol = ticker.strip().upper()
        if not yf:
            return None

        try:
            t = yf.Ticker(symbol)
            fast_info = getattr(t, "fast_info", None)
            spot = 0.0
            if fast_info:
                spot = float(fast_info.get("lastPrice") or fast_info.get("regularMarketPreviousClose") or 0.0)
            if not spot or spot <= 0:
                hist = t.history(period="5d")
                if not hist.empty:
                    spot = float(hist["Close"].iloc[-1])
            if not spot or spot <= 0:
                return None

            # 1. Fetch Volume Profile
            vp = self.volume_service.compute_volume_profile(symbol, period="1mo", interval="30m")
            # 2. Fetch GEX (if available, e.g. for US optionable equities)
            gex = self.options_service.analyze_gex(symbol, spot_override=spot)
            # 3. Fetch Macro Regime
            macro = self.regime_service.get_market_regime()
            # 4. Fetch Relative Strength vs SPY
            rs_data = None
            if self.rs_service and symbol != "SPY":
                try:
                    rs_data = self.rs_service.compute_relative_strength(symbol, benchmark="SPY")
                except Exception:
                    rs_data = None

            # 5. Fetch Anchored VWAPs
            avwap_data = None
            if self.avwap_service:
                try:
                    avwap_data = self.avwap_service.compute_anchored_vwaps(symbol)
                except Exception:
                    avwap_data = None

            # 6. Fetch Whale Flow Activity
            whale_data = None
            if self.whale_service:
                try:
                    whale_data = self.whale_service.analyze_whale_flow(symbol)
                except Exception:
                    whale_data = None

            # 7. Fetch Smart Money Liquidity Zones (FVG & Order Blocks)
            fvg_data = None
            if self.liquidity_service:
                try:
                    fvg_data = self.liquidity_service.analyze_zones(symbol)
                except Exception:
                    fvg_data = None

            # 8. Fetch Multi-Timeframe Alignment
            mtf_data = None
            if self.mtf_service:
                try:
                    mtf_data = self.mtf_service.analyze_mtf_alignment(symbol)
                except Exception:
                    mtf_data = None

            poc = vp.get("poc_price", spot) if vp else spot
            vah = vp.get("vah_price", spot * 1.03) if vp else spot * 1.03
            val = vp.get("val_price", spot * 0.97) if vp else spot * 0.97
            market_loc = vp.get("market_location", "inside_value_area") if vp else "inside_value_area"

            direction = "LONG"
            setup_name = "Volume Profile Value Rebound"
            catalyst = catalyst_override or "Auction Value Area Support & Institutional Accumulation"

            call_wall = gex.get("call_wall") if gex else None
            put_wall = gex.get("put_wall") if gex else None
            gex_regime = gex.get("regime", "neutral") if gex else "neutral"

            # Structural Invalidation logic:
            # Stop MUST sit below structural support (VAL or POC or retested VAH)
            if market_loc == "above_value_area":
                setup_name = "Value Area High (VAH) Breakout & Expansion"
                catalyst = catalyst_override or "Bullish Value Acceptance > VAH with Volume Expansion"
                invalidation_price = round(vah * 0.985, 2)
                entry_price = round(spot, 2)
            elif market_loc == "inside_value_area" and spot <= poc:
                setup_name = "Value Area Low (VAL) Mean Reversion"
                catalyst = catalyst_override or "Support test at Value Area Low (VAL) rotating back to POC"
                invalidation_price = round(val * 0.98, 2)
                entry_price = round(spot, 2)
            else:
                setup_name = "Point of Control (POC) Structural Continuation"
                catalyst = catalyst_override or "Consolidation around highest liquidity node (POC)"
                invalidation_price = round(min(val, poc * 0.965), 2)
                entry_price = round(spot, 2)

            if invalidation_price >= entry_price:
                invalidation_price = round(entry_price * 0.95, 2)

            risk_per_share = round(entry_price - invalidation_price, 2)
            min_risk = entry_price * 0.015
            max_risk = entry_price * 0.075
            if risk_per_share < min_risk:
                invalidation_price = round(entry_price - min_risk, 2)
                risk_per_share = round(entry_price - invalidation_price, 2)
            elif risk_per_share > max_risk:
                invalidation_price = round(entry_price - max_risk, 2)
                risk_per_share = round(entry_price - invalidation_price, 2)

            # Mathematical Targets: Min 2.0R for Target 1, Min 3.5R for Target 2
            target_1 = round(entry_price + (2.0 * risk_per_share), 2)
            target_2 = round(entry_price + (3.5 * risk_per_share), 2)

            if call_wall and call_wall > target_1:
                target_2 = max(target_2, round(call_wall, 2))

            reward_per_share = round(target_2 - entry_price, 2)
            risk_reward_ratio = round(reward_per_share / risk_per_share, 2) if risk_per_share > 0 else 0.0

            # 4. Position Sizing
            max_risk_amount = portfolio_capital * (risk_budget_pct / 100.0)
            recommended_shares = max(1, int(max_risk_amount / risk_per_share))
            max_capital_allowed = portfolio_capital * 0.20
            if (recommended_shares * entry_price) > max_capital_allowed:
                recommended_shares = max(1, int(max_capital_allowed / entry_price))

            total_position_capital = round(recommended_shares * entry_price, 2)
            actual_risk_amount = round(recommended_shares * risk_per_share, 2)
            actual_risk_pct = round((actual_risk_amount / portfolio_capital) * 100.0, 2)

            # 5. Confluence Scoring & Grading (0 - 100 pts)
            confluence_score = 50
            confluence_factors: List[str] = []

            # Volume Profile Confluence
            if market_loc in ["inside_value_area", "above_value_area"]:
                confluence_score += 10
                confluence_factors.append("Struktur-Support im Volume Profile")
            if abs(spot - val) / spot < 0.035 or abs(spot - poc) / spot < 0.025:
                confluence_score += 15
                confluence_factors.append("Direkter Test von Key-Liquidität (VAL/POC)")

            # Options GEX Confluence
            if gex:
                if gex_regime == "positive_gamma":
                    confluence_score += 15
                    confluence_factors.append("Positives Gamma (Market Maker dämpfen Abverkäufe)")
                if put_wall and abs(spot - put_wall) / spot < 0.05:
                    confluence_score += 10
                    confluence_factors.append("Put Wall Support (Institutioneller Boden)")

            # Risk/Reward Asymmetry
            if risk_reward_ratio >= 3.5:
                confluence_score += 15
                confluence_factors.append(f"Hohe Asymmetrie ({risk_reward_ratio:.1f}:1 R:R)")
            elif risk_reward_ratio >= 2.8:
                confluence_score += 10
                confluence_factors.append(f"Solide Asymmetrie ({risk_reward_ratio:.1f}:1 R:R)")

            # Macro Market Confluence
            regime_stance = macro.get("stance", "RISK_ON")
            if regime_stance == "RISK_ON":
                confluence_score += 10
                confluence_factors.append("Makro-Rückenwind (SPY/QQQ stabil, VIX niedrig)")
            elif regime_stance == "RISK_OFF":
                confluence_score -= 20
                confluence_factors.append("⚠️ Makro-Gegenwind (Markt im Risk-Off Modus)")

            # Relative Strength Confluence vs SPY
            if rs_data:
                mansfield = rs_data.get("mansfield_rs", 0.0)
                alpha_1m = rs_data.get("alpha_1m", 0.0)
                if mansfield >= 5.0 and alpha_1m > 0:
                    confluence_score += 10
                    confluence_factors.append(f"Starke Relative Stärke vs. SPY (Mansfield RS: {mansfield:+.1f}%, Alpha: {alpha_1m:+.1f}%)")
                elif mansfield > 0:
                    confluence_score += 5
                    confluence_factors.append(f"Positive Relative Stärke vs. SPY ({mansfield:+.1f}%)")
                elif mansfield <= -5.0:
                    confluence_score -= 10
                    confluence_factors.append(f"⚠️ Schwächer als der Markt (Mansfield RS: {mansfield:+.1f}%)")

            # Anchored VWAP Confluence
            if avwap_data:
                retests = avwap_data.get("retests", [])
                if retests:
                    confluence_score += 10
                    confluence_factors.append(f"Retest von institutionellem {retests[0]}")
                elif avwap_data.get("institutional_bias") == "BULLISH_ACCEPTANCE":
                    confluence_score += 5
                    confluence_factors.append("Kurs oberhalb YTD & Earnings AVWAP (Fonds im Gewinn)")
                elif avwap_data.get("institutional_bias") == "BEARISH_PRESSURE":
                    confluence_score -= 10
                    confluence_factors.append("⚠️ Unterhalb YTD & Earnings AVWAP (Verkaufsdruck)")

            # Whale Flow / Dark Pool Confluence
            if whale_data and whale_data.get("is_whale_activity"):
                w_pat = whale_data.get("pattern")
                w_ratio = whale_data.get("volume_ratio", 1.0)
                if w_pat == "ACCUMULATION_ABSORPTION":
                    confluence_score += 12
                    confluence_factors.append(f"Whale-Absorption ({w_ratio:.1f}x Volumen am Support absorbiert)")
                elif w_pat == "INSTITUTIONAL_EXPANSION":
                    confluence_score += 10
                    confluence_factors.append(f"Institutioneller Volumenausbruch ({w_ratio:.1f}x Volumen)")
                elif w_pat == "DISTRIBUTION_EXHAUSTION":
                    confluence_score -= 15
                    confluence_factors.append("⚠️ Institutionelle Distribution erkannt (Verkauf in Hype)")

            # Smart Money Liquidity Zones (FVG & Order Block) Confluence
            if fvg_data:
                if fvg_data.get("in_demand_zone"):
                    confluence_score += fvg_data.get("confluence_bonus", 10)
                    confluence_factors.append(fvg_data.get("zone_label", "Im Smart-Money-Demand-Bereich"))
                elif fvg_data.get("confluence_bonus", 0) > 0:
                    confluence_score += fvg_data.get("confluence_bonus", 4)
                    confluence_factors.append("Nahe Fair Value Gap Support")

            # Multi-Timeframe Alignment Confluence
            if mtf_data:
                mtf_bonus = mtf_data.get("confluence_bonus", 0)
                confluence_score += mtf_bonus
                if mtf_bonus > 0:
                    confluence_factors.append(f"MTF-Trend-Synchronisation ({mtf_data.get('badge')})")
                elif mtf_bonus < 0:
                    confluence_factors.append(f"⚠️ {mtf_data.get('badge')}")

            # Earnings Proximity Shield
            earnings_info = self._check_earnings_proximity(t)
            if earnings_info:
                confluence_score -= 15
                confluence_factors.append(earnings_info["warning"])

            # Institutional Pro-Strategy Playbook & Bayesian Self-Learning Adjustment
            pro_playbook = None
            if self.coach_service:
                try:
                    pro_playbook = self.coach_service.evaluate_setup_learning_adjustment(
                        setup_name=setup_name,
                        has_positive_gex=bool(gex and gex_regime == "positive_gamma"),
                        has_avwap_support=bool(avwap_data and (avwap_data.get("retests") or avwap_data.get("institutional_bias") == "BULLISH_ACCEPTANCE")),
                        has_fvg_demand=bool(fvg_data and (fvg_data.get("in_demand_zone") or fvg_data.get("confluence_bonus", 0) > 0)),
                        has_strong_rs=bool(rs_data and float(rs_data.get("mansfield_rs") or 0.0) >= 3.0),
                        has_whale_expansion=bool(whale_data and whale_data.get("is_whale_activity")),
                    )
                    if pro_playbook:
                        adj = int(pro_playbook.get("score_adjustment") or 0)
                        confluence_score += adj
                        confluence_factors.append(pro_playbook["summary_badge"])
                except Exception as e:
                    logger.debug("Playbook learning adjustment error: %s", e)

            confluence_score = max(10, min(100, confluence_score))
            if confluence_score >= 85:
                grade = "A+"
                grade_badge = "💎 Grade A+"
                grade_title = "Elite Institutional Confluence"
            elif confluence_score >= 70:
                grade = "A"
                grade_badge = "⭐ Grade A"
                grade_title = "Starker Edge Trade"
            else:
                grade = "B"
                grade_badge = "🔹 Grade B"
                grade_title = "Selektiv handeln"

            # 6. Chart Overlay Level Bundle (for PriceChart / Visuals)
            nearest_fvg = fvg_data.get("nearest_bullish_fvg") if fvg_data else None
            chart_overlay_levels = {
                "poc": poc,
                "vah": vah,
                "val": val,
                "call_wall": call_wall,
                "put_wall": put_wall,
                "ytd_avwap": avwap_data.get("ytd", {}).get("avwap") if avwap_data and avwap_data.get("ytd") else None,
                "earnings_avwap": avwap_data.get("earnings", {}).get("avwap") if avwap_data and avwap_data.get("earnings") else None,
                "fvg_low": nearest_fvg.get("gap_low") if nearest_fvg else None,
                "fvg_high": nearest_fvg.get("gap_high") if nearest_fvg else None,
                "entry": entry_price,
                "invalidation": invalidation_price,
                "target_1": target_1,
                "target_2": target_2,
            }

            is_eu = any(symbol.endswith(sfx) for sfx in [".DE", ".F", ".AS", ".PA", ".MI", ".MC"])
            curr_sym = "€" if is_eu else ("£" if symbol.endswith(".L") else "$")

            # German WKN / ISIN, Anti-FOMO Entry Timing & German Net Tax (26.375%)
            wkn_info = get_wkn_isin(symbol)
            entry_timing = evaluate_entry_timing(
                ticker=symbol,
                spot=spot,
                entry_price=entry_price,
                risk_per_share=risk_per_share,
            )
            gross_tp1_eur = round((target_1 - entry_price) * recommended_shares, 2)
            gross_tp2_eur = round((target_2 - entry_price) * recommended_shares, 2)
            german_tax = compute_german_net_tax(
                gross_tp1_eur=gross_tp1_eur,
                gross_tp2_eur=gross_tp2_eur,
                gross_risk_eur=actual_risk_amount,
            )

            # 7. Trade Management Guidance
            trade_management = {
                "target_1_action": f"Bei {curr_sym}{target_1:.2f} (2.0R): 50% Teilgewinn sichern, Hard Stop auf Breakeven ({curr_sym}{entry_price:.2f}) nachziehen.",
                "target_2_action": f"Bei {curr_sym}{target_2:.2f} (3.5R+): Restposition glattstellen oder Trailing Stop unter 9 EMA führen.",
                "earnings_shield": earnings_info.get("warning") if earnings_info else "Keine Quartalszahlen in den nächsten 5 Tagen.",
            }

            mgmt_text = (
                f"📋 <b>Trade Management & Trailing Stop:</b>\n"
                f"• <b>Ziel 1 ({curr_sym}{target_1:.2f}):</b> 50% Teilgewinn & Stop auf Breakeven\n"
                f"• <b>Ziel 2 ({curr_sym}{target_2:.2f}):</b> Rest glattstellen oder per 9 EMA Trailing-Stop\n"
            )
            if earnings_info:
                mgmt_text += f"\n{earnings_info['warning']}\n"

            # 8. Format Smartphone Telegram Card
            gex_summary = "N/A (keine US-Optionen)"
            if gex:
                gex_summary = f"{gex.get('regime_label', 'Neutral')} | Call Wall: {curr_sym}{call_wall:.2f} | Put Wall: {curr_sym}{put_wall:.2f}"

            vp_summary = f"POC: {curr_sym}{poc:.2f} | VAH: {curr_sym}{vah:.2f} | VAL: {curr_sym}{val:.2f} ({vp.get('location_label', 'Neutral') if vp else 'N/A'})"
            factors_text = "\n".join([f"  ✓ {f}" for f in confluence_factors])

            ascii_roadmap = (
                f"<code>"
                f" 🎯 Ziel 2 : {curr_sym}{target_2:>7.2f} ───┐ (Runner 3.5R+)\n"
                f" 🎯 Ziel 1 : {curr_sym}{target_1:>7.2f} ───┼─ 50% TP &amp; BE Stop\n"
                f" ⚡ Entry  : {curr_sym}{entry_price:>7.2f} ─●─┼─ Spot\n"
                f" 🛑 Inval. : {curr_sym}{invalidation_price:>7.2f} ───┘ (Risk: 1.0R)"
                f"</code>"
            )

            wkn_line = (
                f"🇩🇪 <b>WKN:</b> <code>{wkn_info['wkn']}</code> | <b>ISIN:</b> <code>{wkn_info['isin']}</code>\n"
                if wkn_info.get("found") == "true"
                else f"🇩🇪 <b>Ticker-Suche im Broker:</b> <code>{symbol}</code>\n"
            )

            tg_html = (
                f"🎯 <b>TRADING EDGE SETUP: {symbol}</b> ({grade_badge})\n"
                f"{wkn_line}"
                f"<b>Typ:</b> {setup_name}\n"
                f"<b>Score:</b> {confluence_score}/100 ({grade_title})\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💡 <b>Katalysator &amp; Logik:</b>\n{catalyst}\n\n"
                f"📊 <b>Konfluenz-Faktoren:</b>\n{factors_text}\n\n"
                f"⏳ <b>Timing &amp; Anti-FOMO Check:</b>\n"
                f"• {entry_timing['session_badge']}\n"
                f"• {entry_timing['chasing_badge']}\n\n"
                f"📈 <b>Institutionelle Roadmap:</b>\n"
                f"{ascii_roadmap}\n\n"
                f"🏛️ <b>Key Level Referenz:</b>\n"
                f"• <b>Volume Profile:</b> {vp_summary}\n"
                f"• <b>Optionen GEX:</b> {gex_summary}\n\n"
                f"⚡ <b>Einstieg:</b> {curr_sym}{entry_price:.2f}\n"
                f"🛑 <b>Invalidation (Hard Stop):</b> {curr_sym}{invalidation_price:.2f} (unter Struktur)\n"
                f"🎯 <b>Ziel 1 (2.0R):</b> {curr_sym}{target_1:.2f} (50% Teilgewinn)\n"
                f"🚀 <b>Ziel 2 (3.5R+):</b> {curr_sym}{target_2:.2f} (Runner / Call Wall)\n"
                f"⚖️ <b>Risk/Reward-Ratio:</b> <b>{risk_reward_ratio:.1f} : 1</b>\n\n"
                f"{mgmt_text}\n"
                f"📱 <b>Position Sizing ({actual_risk_pct:.2f}% Kontorisiko):</b>\n"
                f"• <b>Stückzahl:</b> <b>{recommended_shares}</b> Aktien\n"
                f"• <b>Kapitalbedarf:</b> ~{total_position_capital:,.2f} EUR\n"
                f"• <b>Max. Risiko beim Stop:</b> -{actual_risk_amount:,.2f} EUR (Netto nach Verlusttopf: ~-{german_tax['effective_net_risk_eur']:,.2f} EUR)\n"
                f"• <b>Netto-Gewinn nach 26,38% Abgeltungsteuer:</b> Ziel 1: <b>+{german_tax['net_tp1_eur']:,.2f} EUR</b> | Ziel 2: <b>+{german_tax['net_tp2_eur']:,.2f} EUR</b>\n"
            )

            ticket = {
                "ticker": symbol,
                "wkn_isin": wkn_info,
                "setup_name": setup_name,
                "catalyst_description": catalyst,
                "direction": direction,
                "grade": grade,
                "grade_badge": grade_badge,
                "grade_title": grade_title,
                "confluence_score": confluence_score,
                "confluence_factors": confluence_factors,
                "entry_price": entry_price,
                "invalidation_price": invalidation_price,
                "target_1": target_1,
                "target_2": target_2,
                "risk_per_share": risk_per_share,
                "reward_per_share": reward_per_share,
                "risk_reward_ratio": risk_reward_ratio,
                "recommended_shares": recommended_shares,
                "total_position_capital": total_position_capital,
                "actual_risk_amount": actual_risk_amount,
                "portfolio_risk_pct": actual_risk_pct,
                "portfolio_capital_basis": portfolio_capital,
                "chart_overlay_levels": chart_overlay_levels,
                "trade_management": trade_management,
                "earnings_info": earnings_info,
                "entry_timing": entry_timing,
                "german_tax": german_tax,
                "pro_playbook": pro_playbook,
                "volume_profile": {
                    "poc": poc,
                    "vah": vah,
                    "val": val,
                    "market_location": market_loc,
                },
                "options_gex": {
                    "regime": gex_regime,
                    "call_wall": call_wall,
                    "put_wall": put_wall,
                } if gex else None,
                "macro_regime": {
                    "stance": regime_stance,
                    "vix": macro.get("vix", {}).get("value"),
                },
                "relative_strength": rs_data,
                "anchored_vwap": avwap_data,
                "whale_flow": whale_data,
                "liquidity_zones": fvg_data,
                "mtf_alignment": mtf_data,
                "telegram_html": tg_html,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            return ticket

        except Exception as exc:
            logger.error("Failed to generate trade setup for %s: %s", symbol, exc)
            return None

    def _check_earnings_proximity(self, ticker_obj: Any, max_days_warning: int = 5) -> Optional[Dict[str, Any]]:
        """Checks if earnings are scheduled within max_days_warning days."""
        try:
            cal = getattr(ticker_obj, "calendar", None)
            if not cal:
                return None
            earnings_dates = None
            if isinstance(cal, dict):
                earnings_dates = cal.get("Earnings Date")
            elif hasattr(cal, "get"):
                earnings_dates = cal.get("Earnings Date")

            if not earnings_dates:
                return None
            if not isinstance(earnings_dates, (list, tuple)):
                earnings_dates = [earnings_dates]

            today = datetime.now(timezone.utc).date()
            for ed in earnings_dates:
                if hasattr(ed, "date"):
                    ed_date = ed.date()
                elif isinstance(ed, type(today)):
                    ed_date = ed
                else:
                    continue

                diff_days = (ed_date - today).days
                if 0 <= diff_days <= max_days_warning:
                    return {
                        "days_until_earnings": diff_days,
                        "earnings_date": ed_date.isoformat(),
                        "warning": (
                            f"⚠️ Quartalszahlen in {diff_days} Tagen ({ed_date.isoformat()}): "
                            "Hohes Übernacht-Gap- und IV-Crush-Risiko! Vor den Zahlen schließen oder halbieren."
                        ),
                    }
        except Exception as e:
            logger.debug("Earnings proximity check error: %s", e)
        return None
