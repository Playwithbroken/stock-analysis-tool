"""
Tax Harvesting & Freistellungsauftrag (FSA) Optimizer Service
Specialized for German tax law (§ 20 EStG):
- Separation into Aktien-Verlusttopf (stocks) vs. Allgemeiner Verlusttopf (ETFs/funds/derivatives).
- Abgeltungsteuer (25%) + Solidaritaetszuschlag (5.5%) = 26.375% (optional church tax up to 27.995%).
- Market-continuation replacement assets (Substitutes) to harvest losses without missing market upside.
- Freistellungsauftrag multi-broker allocator and Dec 31 tax deadline countdown.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import math


# High-correlation substitute pairs (same asset class/exposure, different ISIN/ticker)
# Avoids wash sale psychological drag & keeps investor 100% market invested
KNOWN_SUBSTITUTES: Dict[str, Dict[str, Any]] = {
    # World ETFs
    "URTH": {
        "substitute_ticker": "VWCE.DE",
        "substitute_name": "Vanguard FTSE All-World UCITS ETF",
        "correlation": 0.99,
        "reason": "Sehr hohe Schnittmenge (98%+ globale Aktien), separate Fondsgesellschaft und WKN."
    },
    "EUNL.DE": {
        "substitute_ticker": "VWCE.DE",
        "substitute_name": "Vanguard FTSE All-World UCITS ETF",
        "correlation": 0.99,
        "reason": "Weltweite Diversifikation mit identischem Risikoprofil, kein Klumpenwechsel."
    },
    "VWCE.DE": {
        "substitute_ticker": "EUNL.DE",
        "substitute_name": "iShares Core MSCI World UCITS ETF",
        "correlation": 0.99,
        "reason": "Klassischer Gegenpol für All-World Anleger."
    },
    # US Large Cap
    "SPY": {
        "substitute_ticker": "SXR8.DE",
        "substitute_name": "iShares Core S&P 500 UCITS ETF",
        "correlation": 1.00,
        "reason": "Exakt identischer S&P 500 Index, andere Fondstranche."
    },
    "SXR8.DE": {
        "substitute_ticker": "VUAA.DE",
        "substitute_name": "Vanguard S&P 500 UCITS ETF",
        "correlation": 1.00,
        "reason": "Identischer Leitindex, Vanguard statt iShares."
    },
    # Tech & Nasdaq
    "QQQ": {
        "substitute_ticker": "XLK",
        "substitute_name": "Technology Select Sector SPDR",
        "correlation": 0.96,
        "reason": "Fokus auf US-Tech-Schwergewichte bei reduzierter Nebengewichtung."
    },
    "XLK": {
        "substitute_ticker": "QQQ",
        "substitute_name": "Invesco QQQ Trust (Nasdaq 100)",
        "correlation": 0.96,
        "reason": "Breitere Abdeckung aller Nasdaq-Technologieführer."
    },
    # DAX
    "EXS1.DE": {
        "substitute_ticker": "DAXEX.DE",
        "substitute_name": "Deka DAX UCITS ETF",
        "correlation": 1.00,
        "reason": "Deutscher Leitindex über alternativen Fondsanbieter."
    },
    # Emerging Markets
    "EEM": {
        "substitute_ticker": "IS3N.DE",
        "substitute_name": "iShares Core MSCI EM IMI UCITS ETF",
        "correlation": 0.98,
        "reason": "Breitere Schwellenländer-Abdeckung inklusive Small-Caps."
    },
    "IS3N.DE": {
        "substitute_ticker": "VFEM.DE",
        "substitute_name": "Vanguard FTSE Emerging Markets UCITS ETF",
        "correlation": 0.98,
        "reason": "FTSE-Schwellenländer-Alternative."
    },
    # Mega-Cap Equities Peer Substitutes
    "AAPL": {
        "substitute_ticker": "MSFT",
        "substitute_name": "Microsoft Corp.",
        "correlation": 0.85,
        "reason": "Vergleichbare Burggraben-Qualität und Enterprise/Consumer-Stabilität."
    },
    "MSFT": {
        "substitute_ticker": "GOOGL",
        "substitute_name": "Alphabet Inc.",
        "correlation": 0.84,
        "reason": "Starker Cloud- und KI-Marktanteil mit robusten Bilanzen."
    },
    "GOOGL": {
        "substitute_ticker": "META",
        "substitute_name": "Meta Platforms Inc.",
        "correlation": 0.82,
        "reason": "Führende Digitalwerbungs- und KI-Plattform."
    },
    "NVDA": {
        "substitute_ticker": "SMH",
        "substitute_name": "VanEck Semiconductor ETF",
        "correlation": 0.88,
        "reason": "Behält Halbleiter-Rückenwind bei breiterer Streuung."
    },
    "TSLA": {
        "substitute_ticker": "QQQ",
        "substitute_name": "Invesco QQQ Trust",
        "correlation": 0.75,
        "reason": "Breitere Tech-Alternative mit hoher Tesla-Beteiligung."
    }
}


class TaxHarvestingService:
    @staticmethod
    def calculate_effective_tax_rate(church_tax_rate: float = 0.0) -> float:
        """
        Calculates the effective German capital gains tax rate (§ 32d Abs. 1 EStG):
        e = (0.25 * (1 + k + 0.055)) / (1 + 0.25 * k)
        where k is church tax (0.0, 0.08, or 0.09).
        Without church tax: 25% * 1.055 = 26.375%.
        With 8% church tax: ~27.819%.
        With 9% church tax: ~27.995%.
        """
        k = max(0.0, float(church_tax_rate))
        if k == 0.0:
            return 0.26375
        effective = (0.25 * (1.0 + k + 0.055)) / (1.0 + 0.25 * k)
        return round(effective, 5)

    @staticmethod
    def get_days_until_year_end() -> int:
        """Days remaining until December 31 for the current tax year."""
        now = datetime.now(timezone.utc)
        year_end = datetime(now.year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        delta = (year_end - now).days
        return max(0, delta)

    @staticmethod
    def analyze_portfolio(
        holdings: List[Dict[str, Any]],
        church_tax_type: str = "none",  # "none", "8%", "9%"
        fsa_allowance: float = 1000.0,   # 1000 EUR (Single) or 2000 EUR (Married)
        fsa_used: float = 0.0,           # Already claimed FSA this year
        broker_splits: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Comprehensive Tax Loss Harvesting and Freistellungsauftrag Analysis.
        """
        # 1. Determine tax rate
        church_rate = 0.08 if church_tax_type == "8%" else (0.09 if church_tax_type == "9%" else 0.0)
        eff_tax_rate = TaxHarvestingService.calculate_effective_tax_rate(church_rate)
        eff_tax_rate_pct = round(eff_tax_rate * 100.0, 3)

        # 2. Classify holdings and calculate unrealized gains/losses
        loss_candidates_stocks: List[Dict[str, Any]] = []
        loss_candidates_general: List[Dict[str, Any]] = []
        gain_positions: List[Dict[str, Any]] = []

        total_unrealized_stock_loss = 0.0
        total_unrealized_general_loss = 0.0
        total_unrealized_gains = 0.0

        for h in holdings:
            t = str(h.get("ticker") or "").upper().strip()
            if not t:
                continue

            sh = float(h.get("shares") or 0.0)
            if sh <= 0:
                continue

            # Buy price & current price
            bp = float(h.get("buyPrice") or h.get("buy_price") or 1.0)
            cp = float(h.get("current_price") or h.get("currentPrice") or bp)
            
            cost_basis = sh * bp
            current_value = sh * cp
            gain_loss_eur = current_value - cost_basis
            gain_loss_pct = (gain_loss_eur / cost_basis * 100.0) if cost_basis > 0 else 0.0

            # Determine whether holding is an ETF/fund or single equity
            # ETFs typically contain .DE, or are recognized index ETFs, or have is_etf flag
            from src.etf_overlap_service import KNOWN_ETF_PROFILES
            is_etf = (
                bool(h.get("is_etf")) or
                t in KNOWN_ETF_PROFILES or
                any(t.endswith(suf) for suf in [".DE", ".PA", ".AS", ".L", ".SW"]) and ("ETF" in str(h.get("name", "")).upper() or "UCITS" in str(h.get("name", "")).upper()) or
                t in ["URTH", "SPY", "QQQ", "VWCE.DE", "EXS1.DE", "SMH", "XLK", "EEM", "IS3N.DE", "ARKK"]
            )

            # Substitute recommendation
            sub_info = KNOWN_SUBSTITUTES.get(t)
            if not sub_info:
                if is_etf:
                    sub_info = {
                        "substitute_ticker": "VWCE.DE",
                        "substitute_name": "Vanguard FTSE All-World UCITS ETF",
                        "correlation": 0.95,
                        "reason": "Breit diversifizierter All-World Core ETF als stabiles Park-Asset."
                    }
                else:
                    sub_info = {
                        "substitute_ticker": "QQQ",
                        "substitute_name": "Invesco QQQ Trust",
                        "correlation": 0.80,
                        "reason": "Breit gestreuter Technologieführer-Korb zur Risikosenkung."
                    }

            pos_item = {
                "ticker": t,
                "name": h.get("name") or t,
                "shares": sh,
                "buy_price": round(bp, 2),
                "current_price": round(cp, 2),
                "cost_basis": round(cost_basis, 2),
                "current_value": round(current_value, 2),
                "gain_loss_eur": round(gain_loss_eur, 2),
                "gain_loss_pct": round(gain_loss_pct, 2),
                "is_etf": is_etf,
                "loss_pot": "Allgemeiner Verlusttopf" if is_etf else "Aktien-Verlusttopf",
                "potential_tax_shield_eur": round(abs(gain_loss_eur) * eff_tax_rate, 2) if gain_loss_eur < 0 else 0.0,
                "substitute": sub_info,
            }

            if gain_loss_eur < -1.0:  # Realizable loss candidate
                if is_etf:
                    loss_candidates_general.append(pos_item)
                    total_unrealized_general_loss += abs(gain_loss_eur)
                else:
                    loss_candidates_stocks.append(pos_item)
                    total_unrealized_stock_loss += abs(gain_loss_eur)
            elif gain_loss_eur > 1.0:
                gain_positions.append(pos_item)
                total_unrealized_gains += gain_loss_eur

        # Sort candidates descending by loss size
        loss_candidates_stocks.sort(key=lambda x: x["gain_loss_eur"])
        loss_candidates_general.sort(key=lambda x: x["gain_loss_eur"])

        all_losses = total_unrealized_stock_loss + total_unrealized_general_loss
        total_potential_tax_shield = round(all_losses * eff_tax_rate, 2)
        stock_tax_shield = round(total_unrealized_stock_loss * eff_tax_rate, 2)
        general_tax_shield = round(total_unrealized_general_loss * eff_tax_rate, 2)

        # 3. Freistellungsauftrag (FSA) status
        fsa_remaining = max(0.0, fsa_allowance - fsa_used)
        fsa_used_pct = round((fsa_used / fsa_allowance * 100.0), 1) if fsa_allowance > 0 else 0.0
        days_left = TaxHarvestingService.get_days_until_year_end()

        # Multi-broker distribution recommendation
        # If user provides or default 2-broker split (e.g. Scalable 60%, Trade Republic 40%)
        default_brokers = broker_splits or [
            {"broker": "Hauptbroker (z.B. Scalable Capital)", "pct": 60},
            {"broker": "Zweitbroker (z.B. Trade Republic)", "pct": 40},
        ]
        recommended_splits = [
            {
                "broker": b["broker"],
                "percentage": b["pct"],
                "recommended_fsa_eur": round(fsa_allowance * (b["pct"] / 100.0), 0),
            }
            for b in default_brokers
        ]

        # Strategic Guidance Headline
        if total_potential_tax_shield >= 500.0:
            strategy_headline = f"Hohes Steuer-Sparpotenzial: Bis zu {total_potential_tax_shield:,.2f} € Steuerrückerstattung durch gezieltes Loss Harvesting möglich!"
            urgency = "HIGH"
        elif total_potential_tax_shield > 50.0:
            strategy_headline = f"Solides Optimierungspotenzial: {total_potential_tax_shield:,.2f} € Steuererstattung vor dem 31.12. sicherbar."
            urgency = "MEDIUM"
        else:
            strategy_headline = "Kaum Buchverluste vorhanden. Dein Portfolio steht steuerlich effizient im Plus."
            urgency = "LOW"

        return {
            "effective_tax_rate_pct": eff_tax_rate_pct,
            "effective_tax_rate_decimal": eff_tax_rate,
            "church_tax_type": church_tax_type,
            "days_until_year_end": days_left,
            "total_potential_tax_shield_eur": total_potential_tax_shield,
            "stock_tax_shield_eur": stock_tax_shield,
            "general_tax_shield_eur": general_tax_shield,
            "total_unrealized_stock_loss_eur": round(total_unrealized_stock_loss, 2),
            "total_unrealized_general_loss_eur": round(total_unrealized_general_loss, 2),
            "total_unrealized_losses_eur": round(all_losses, 2),
            "total_unrealized_gains_eur": round(total_unrealized_gains, 2),
            "strategy_headline": strategy_headline,
            "urgency": urgency,
            "loss_candidates_stocks": loss_candidates_stocks,
            "loss_candidates_general": loss_candidates_general,
            "gain_positions_count": len(gain_positions),
            "fsa": {
                "total_allowance": fsa_allowance,
                "used_amount": fsa_used,
                "remaining_amount": round(fsa_remaining, 2),
                "used_percentage": fsa_used_pct,
                "recommended_splits": recommended_splits,
                "warning": (
                    f"Achtung: Noch {fsa_remaining:,.0f} € Freistellungsauftrag ungenutzt! Nach dem 31.12. verfällt der Freibetrag für dieses Kalenderjahr."
                    if fsa_remaining >= 100.0 and days_left <= 90
                    else None
                ),
            }
        }
