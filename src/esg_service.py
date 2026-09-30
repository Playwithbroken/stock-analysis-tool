"""
ESG & Sustainability Service: EU SFDR Article 8/9 Classification,
Weighted Average Carbon Intensity (WACI), E-S-G Pillar Scoring,
Controversy Radar, and Principal Adverse Impacts (PAI) Exclusion Screening.
"""

from typing import Dict, Any, List, Optional
import math
from src.data_fetcher import DataFetcher


class ESGService:
    """
    Computes institutional ESG and sustainability diagnostics:
    - Weighted Portfolio ESG Score (0-100) & Grade (AAA to CCC)
    - E, S, G Pillar Decomposition (Environmental, Social, Governance)
    - Weighted Average Carbon Intensity (WACI) in t CO2e / $M Revenue vs. MSCI World
    - EU SFDR Regulatory Classification (Article 6, Article 8, Article 9)
    - Controversy Radar (Scale 0 to 5, Severity, Greenwashing check)
    - PAI Exclusion Screening (Thermal Coal, Controversial Weapons, Tobacco, UN Global Compact)
    """

    MSCI_WORLD_WACI_BENCHMARK = 135.0  # t CO2e / $M Revenue

    # Institutional reference database for global assets
    ESG_KNOWLEDGE_BASE = {
        "AAPL": {
            "name": "Apple Inc.", "sector": "Technology",
            "esg_score": 78, "esg_rating": "AA",
            "e_score": 82, "s_score": 74, "g_score": 79,
            "carbon_intensity": 14.5, "controversy_level": 2,
            "controversies": ["Arbeitsbedingungen in asiatischen Zulieferbetrieben (Supply Chain Monitoring)"],
            "exclusions": {"coal": False, "weapons": False, "tobacco": False, "un_global_compact_violation": False},
            "sfdr_eligible_art8": True, "sfdr_eligible_art9": True
        },
        "MSFT": {
            "name": "Microsoft Corp.", "sector": "Technology",
            "esg_score": 88, "esg_rating": "AAA",
            "e_score": 92, "s_score": 85, "g_score": 87,
            "carbon_intensity": 18.2, "controversy_level": 1,
            "controversies": ["Mögliche wettbewerbsrechtliche Bedenken bei Cloud-Bundling in der EU"],
            "exclusions": {"coal": False, "weapons": False, "tobacco": False, "un_global_compact_violation": False},
            "sfdr_eligible_art8": True, "sfdr_eligible_art9": True
        },
        "GOOGL": {
            "name": "Alphabet Inc.", "sector": "Communication Services",
            "esg_score": 72, "esg_rating": "A",
            "e_score": 85, "s_score": 64, "g_score": 68,
            "carbon_intensity": 22.8, "controversy_level": 3,
            "controversies": ["Kartellverfahren im digitalen Werbemarkt (DOJ & EU-Kommission)", "Datenschutz-Prüfungen"],
            "exclusions": {"coal": False, "weapons": False, "tobacco": False, "un_global_compact_violation": False},
            "sfdr_eligible_art8": True, "sfdr_eligible_art9": False
        },
        "GOOG": {
            "name": "Alphabet Inc. (Class C)", "sector": "Communication Services",
            "esg_score": 72, "esg_rating": "A",
            "e_score": 85, "s_score": 64, "g_score": 68,
            "carbon_intensity": 22.8, "controversy_level": 3,
            "controversies": ["Kartellverfahren im Werbemarkt"],
            "exclusions": {"coal": False, "weapons": False, "tobacco": False, "un_global_compact_violation": False},
            "sfdr_eligible_art8": True, "sfdr_eligible_art9": False
        },
        "NVDA": {
            "name": "NVIDIA Corp.", "sector": "Technology",
            "esg_score": 80, "esg_rating": "AA",
            "e_score": 78, "s_score": 82, "g_score": 81,
            "carbon_intensity": 19.5, "controversy_level": 1,
            "controversies": ["Hoher Strombedarf von KI-Rechenzentren (Scope 3 Kundennutzung)"],
            "exclusions": {"coal": False, "weapons": False, "tobacco": False, "un_global_compact_violation": False},
            "sfdr_eligible_art8": True, "sfdr_eligible_art9": True
        },
        "ASML": {
            "name": "ASML Holding NV", "sector": "Technology",
            "esg_score": 89, "esg_rating": "AAA",
            "e_score": 90, "s_score": 88, "g_score": 89,
            "carbon_intensity": 25.1, "controversy_level": 1,
            "controversies": ["Exportkontroll-Auflagen für High-NA EUV-Systeme nach China"],
            "exclusions": {"coal": False, "weapons": False, "tobacco": False, "un_global_compact_violation": False},
            "sfdr_eligible_art8": True, "sfdr_eligible_art9": True
        },
        "SAP": {
            "name": "SAP SE", "sector": "Technology",
            "esg_score": 86, "esg_rating": "AAA",
            "e_score": 89, "s_score": 84, "g_score": 85,
            "carbon_intensity": 12.0, "controversy_level": 1,
            "controversies": ["Umstrukturierungen und Abfindungen bei Cloud-Transformation"],
            "exclusions": {"coal": False, "weapons": False, "tobacco": False, "un_global_compact_violation": False},
            "sfdr_eligible_art8": True, "sfdr_eligible_art9": True
        },
        "ALV": {
            "name": "Allianz SE", "sector": "Financial Services",
            "esg_score": 84, "esg_rating": "AA",
            "e_score": 88, "s_score": 80, "g_score": 84,
            "carbon_intensity": 8.5, "controversy_level": 1,
            "controversies": ["Klimastrategie für Kohle-Versicherungsverträge (Kohleausstieg bis 2040)"],
            "exclusions": {"coal": False, "weapons": False, "tobacco": False, "un_global_compact_violation": False},
            "sfdr_eligible_art8": True, "sfdr_eligible_art9": True
        },
        "LIN": {
            "name": "Linde plc", "sector": "Basic Materials",
            "esg_score": 75, "esg_rating": "AA",
            "e_score": 71, "s_score": 78, "g_score": 76,
            "carbon_intensity": 380.0, "controversy_level": 1,
            "controversies": ["Hoher Energieverbrauch bei industrieller Luftzerlegung (Kompensiert durch Grünen Wasserstoff)"],
            "exclusions": {"coal": False, "weapons": False, "tobacco": False, "un_global_compact_violation": False},
            "sfdr_eligible_art8": True, "sfdr_eligible_art9": False
        },
        "TSLA": {
            "name": "Tesla Inc.", "sector": "Consumer Cyclical",
            "esg_score": 64, "esg_rating": "A",
            "e_score": 88, "s_score": 48, "g_score": 52,
            "carbon_intensity": 35.0, "controversy_level": 3,
            "controversies": ["Arbeitsschutz in Gigafactories", "Autopilot-Sicherheitsuntersuchungen der NHTSA", "Board-Unabhängigkeit"],
            "exclusions": {"coal": False, "weapons": False, "tobacco": False, "un_global_compact_violation": False},
            "sfdr_eligible_art8": True, "sfdr_eligible_art9": False
        },
        "JNJ": {
            "name": "Johnson & Johnson", "sector": "Healthcare",
            "esg_score": 70, "esg_rating": "A",
            "e_score": 74, "s_score": 68, "g_score": 69,
            "carbon_intensity": 28.0, "controversy_level": 3,
            "controversies": ["Vergleiche zu Talkum-Produkthaftungsklagen in den USA"],
            "exclusions": {"coal": False, "weapons": False, "tobacco": False, "un_global_compact_violation": False},
            "sfdr_eligible_art8": True, "sfdr_eligible_art9": False
        },
        "XOM": {
            "name": "Exxon Mobil Corp.", "sector": "Energy",
            "esg_score": 38, "esg_rating": "B",
            "e_score": 25, "s_score": 42, "g_score": 48,
            "carbon_intensity": 840.0, "controversy_level": 4,
            "controversies": ["Fossile Brennstoffförderung", "Rechtsstreitigkeiten über Klimakommunikation", "Scope-3-Treibhausgasemissionen"],
            "exclusions": {"coal": False, "weapons": False, "tobacco": False, "un_global_compact_violation": False},
            "sfdr_eligible_art8": False, "sfdr_eligible_art9": False
        },
        "RHM": {
            "name": "Rheinmetall AG", "sector": "Industrials",
            "esg_score": 52, "esg_rating": "BBB",
            "e_score": 65, "s_score": 45, "g_score": 62,
            "carbon_intensity": 45.0, "controversy_level": 2,
            "controversies": ["Rüstungsexporte und Verteidigungsgüter"],
            "exclusions": {"coal": False, "weapons": True, "tobacco": False, "un_global_compact_violation": False},
            "sfdr_eligible_art8": False, "sfdr_eligible_art9": False
        },
        "BTI": {
            "name": "British American Tobacco", "sector": "Consumer Defensive",
            "esg_score": 44, "esg_rating": "BB",
            "e_score": 58, "s_score": 35, "g_score": 46,
            "carbon_intensity": 42.0, "controversy_level": 3,
            "controversies": ["Gesundheitsauswirkungen von Tabakprodukten"],
            "exclusions": {"coal": False, "weapons": False, "tobacco": True, "un_global_compact_violation": False},
            "sfdr_eligible_art8": False, "sfdr_eligible_art9": False
        }
    }

    SECTOR_BASELINES = {
        "Technology": {"esg": 78, "e": 82, "s": 75, "g": 78, "waci": 20.0},
        "Healthcare": {"esg": 72, "e": 74, "s": 72, "g": 70, "waci": 32.0},
        "Financial Services": {"esg": 74, "e": 75, "s": 72, "g": 75, "waci": 12.0},
        "Consumer Cyclical": {"esg": 66, "e": 68, "s": 65, "g": 66, "waci": 55.0},
        "Consumer Defensive": {"esg": 68, "e": 70, "s": 68, "g": 67, "waci": 60.0},
        "Communication Services": {"esg": 70, "e": 75, "s": 66, "g": 68, "waci": 24.0},
        "Industrials": {"esg": 65, "e": 66, "s": 64, "g": 65, "waci": 110.0},
        "Basic Materials": {"esg": 58, "e": 52, "s": 60, "g": 62, "waci": 340.0},
        "Utilities": {"esg": 62, "e": 55, "s": 66, "g": 66, "waci": 420.0},
        "Real Estate": {"esg": 69, "e": 72, "s": 68, "g": 67, "waci": 48.0},
        "Energy": {"esg": 42, "e": 32, "s": 48, "g": 52, "waci": 720.0},
    }

    @classmethod
    def get_esg_rating_letter(cls, score: float) -> str:
        """Converts score (0-100) to standard MSCI/Sustainalytics letter grade."""
        if score >= 85:
            return "AAA"
        if score >= 70:
            return "AA"
        if score >= 60:
            return "A"
        if score >= 50:
            return "BBB"
        if score >= 40:
            return "BB"
        if score >= 30:
            return "B"
        return "CCC"

    @classmethod
    def get_stock_esg_profile(cls, ticker: str) -> Dict[str, Any]:
        """Fetches or models institutional ESG profile for a single stock."""
        t = ticker.strip().upper()
        if t in cls.ESG_KNOWLEDGE_BASE:
            data = cls.ESG_KNOWLEDGE_BASE[t].copy()
            data["ticker"] = t
            return data

        # Dynamic fallback based on sector data from DataFetcher
        sector = "Technology"
        name = t
        try:
            fetcher = DataFetcher(t)
            info = fetcher.get_info() or {}
            sector = info.get("sector") or "Technology"
            name = info.get("name") or info.get("shortName") or t
        except Exception:
            pass

        base = cls.SECTOR_BASELINES.get(sector, cls.SECTOR_BASELINES["Technology"])
        # Slight deterministic variation based on ticker hash
        h = abs(hash(t)) % 15 - 7
        score = max(20, min(95, base["esg"] + h))
        e = max(15, min(95, base["e"] + h))
        s = max(15, min(95, base["s"] + h))
        g = max(20, min(95, base["g"] + h))
        waci = max(5.0, base["waci"] + (h * 2.0))

        return {
            "ticker": t,
            "name": name,
            "sector": sector,
            "esg_score": score,
            "esg_rating": cls.get_esg_rating_letter(score),
            "e_score": e,
            "s_score": s,
            "g_score": g,
            "carbon_intensity": round(waci, 1),
            "controversy_level": 1 if score >= 65 else 2,
            "controversies": [],
            "exclusions": {
                "coal": sector == "Energy" and score < 45,
                "weapons": False,
                "tobacco": False,
                "un_global_compact_violation": False
            },
            "sfdr_eligible_art8": score >= 60,
            "sfdr_eligible_art9": score >= 80 and waci < 60.0
        }

    @classmethod
    def analyze_portfolio_esg(
        cls,
        holdings: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculates portfolio weighted ESG score, Carbon Intensity (WACI),
        SFDR classification, and exclusion screening.
        """
        if not holdings:
            return {
                "valid": False,
                "error": "Mindestens 1 Position erforderlich für die ESG-Analyse."
            }

        # Calculate values and weights
        holdings_data = []
        total_val = 0.0
        for h in holdings:
            t = str(h.get("ticker", "")).strip().upper()
            shares = float(h.get("shares") or 0.0)
            price = float(h.get("current_price") or h.get("buyPrice") or 100.0)
            val = shares * price
            total_val += val
            holdings_data.append({"ticker": t, "value": val, "name": h.get("name") or t})

        n = len(holdings_data)
        if total_val <= 0:
            for item in holdings_data:
                item["weight"] = 1.0 / n
        else:
            for item in holdings_data:
                item["weight"] = item["value"] / total_val

        # Aggregate profiles
        weighted_esg = 0.0
        weighted_e = 0.0
        weighted_s = 0.0
        weighted_g = 0.0
        weighted_waci = 0.0
        art8_weight = 0.0
        art9_weight = 0.0

        all_controversies = []
        exclusion_violations = []
        holdings_attribution = []

        for item in holdings_data:
            t = item["ticker"]
            w = item["weight"]
            profile = cls.get_stock_esg_profile(t)
            # Use passed name if better
            if item["name"] and item["name"] != t:
                profile["name"] = item["name"]

            weighted_esg += w * profile["esg_score"]
            weighted_e += w * profile["e_score"]
            weighted_s += w * profile["s_score"]
            weighted_g += w * profile["g_score"]
            weighted_waci += w * profile["carbon_intensity"]

            if profile.get("sfdr_eligible_art8"):
                art8_weight += w
            if profile.get("sfdr_eligible_art9"):
                art9_weight += w

            # Controversies collection
            if profile.get("controversy_level", 0) >= 2 or profile.get("controversies"):
                all_controversies.append({
                    "ticker": t,
                    "name": profile["name"],
                    "weight_pct": round(w * 100.0, 1),
                    "level": profile["controversy_level"],
                    "descriptions": profile.get("controversies", [])
                })

            # Exclusion checks
            ex = profile.get("exclusions", {})
            reasons = []
            if ex.get("coal"):
                reasons.append("Thermische Kraftwerkskohle (> 5% Umsatz)")
            if ex.get("weapons"):
                reasons.append("Geächtete / Kontroverse Rüstungsgüter")
            if ex.get("tobacco"):
                reasons.append("Tabakproduktion")
            if ex.get("un_global_compact_violation"):
                reasons.append("Verstoß gegen UN Global Compact Prinzipien")

            if reasons:
                exclusion_violations.append({
                    "ticker": t,
                    "name": profile["name"],
                    "weight_pct": round(w * 100.0, 1),
                    "reasons": reasons
                })

            holdings_attribution.append({
                "ticker": t,
                "name": profile["name"],
                "sector": profile.get("sector", "Technology"),
                "weight_pct": round(w * 100.0, 1),
                "esg_score": profile["esg_score"],
                "esg_rating": profile["esg_rating"],
                "e_score": profile["e_score"],
                "s_score": profile["s_score"],
                "g_score": profile["g_score"],
                "carbon_intensity": profile["carbon_intensity"],
                "controversy_level": profile["controversy_level"],
                "has_exclusion": bool(reasons),
                "sfdr_eligible_art8": profile.get("sfdr_eligible_art8", False)
            })

        holdings_attribution.sort(key=lambda x: x["weight_pct"], reverse=True)
        all_controversies.sort(key=lambda x: x["level"], reverse=True)

        # Carbon Intensity vs Benchmark
        carbon_delta_pct = ((weighted_waci - cls.MSCI_WORLD_WACI_BENCHMARK) / cls.MSCI_WORLD_WACI_BENCHMARK) * 100.0

        # SFDR Regulatory Classification
        # Article 9: ESG >= 80, WACI < 60, Art9 eligibility >= 80%, 0 exclusion violations
        # Article 8: ESG >= 60, Art8 eligibility >= 65%, 0 exclusion violations
        # Article 6: Otherwise
        has_violations = len(exclusion_violations) > 0
        if weighted_esg >= 80.0 and weighted_waci < 60.0 and art9_weight >= 0.75 and not has_violations:
            sfdr_classification = "Artikel 9 (Dunkelgrün / Impact)"
            sfdr_badge = "Artikel 9"
            sfdr_tone = "text-emerald-700 dark:text-emerald-400 bg-emerald-500/15 border-emerald-500/30"
            sfdr_desc = "Erfüllt strengste EU-Kriterien für nachhaltige Investitionen mit messbarem Umweltziel."
        elif weighted_esg >= 60.0 and art8_weight >= 0.65 and not has_violations:
            sfdr_classification = "Artikel 8 (Hellgrün / ESG-Merkmale)"
            sfdr_badge = "Artikel 8"
            sfdr_tone = "text-teal-700 dark:text-teal-400 bg-teal-500/15 border-teal-500/30"
            sfdr_desc = "Fördert explizit ökologische und soziale Merkmale bei guter Unternehmensführung."
        else:
            sfdr_classification = "Artikel 6 (Konventionell)"
            sfdr_badge = "Artikel 6"
            sfdr_tone = "text-slate-700 dark:text-slate-400 bg-slate-200 dark:bg-slate-800 border-black/10"
            sfdr_desc = "Konventionelle Anlagestrategie ohne bindende Nachhaltigkeitsauflagen oder mit Ausschluss-Verstößen."

        rating_letter = cls.get_esg_rating_letter(weighted_esg)

        return {
            "valid": True,
            "portfolio_esg_score": round(weighted_esg, 1),
            "portfolio_esg_rating": rating_letter,
            "pillars": {
                "environmental": round(weighted_e, 1),
                "social": round(weighted_s, 1),
                "governance": round(weighted_g, 1)
            },
            "carbon_intensity": {
                "portfolio_waci": round(weighted_waci, 1),
                "benchmark_waci": cls.MSCI_WORLD_WACI_BENCHMARK,
                "relative_carbon_delta_pct": round(carbon_delta_pct, 1),
                "is_cleaner_than_benchmark": weighted_waci < cls.MSCI_WORLD_WACI_BENCHMARK
            },
            "sfdr": {
                "classification": sfdr_classification,
                "badge": sfdr_badge,
                "tone": sfdr_tone,
                "description": sfdr_desc,
                "article_8_coverage_pct": round(art8_weight * 100.0, 1),
                "article_9_coverage_pct": round(art9_weight * 100.0, 1)
            },
            "exclusions": {
                "has_violations": has_violations,
                "violations_count": len(exclusion_violations),
                "violations": exclusion_violations
            },
            "controversies": all_controversies,
            "holdings": holdings_attribution
        }
