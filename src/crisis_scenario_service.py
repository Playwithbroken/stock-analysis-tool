"""
Institutional Historical Crisis Scenario Replay & Geopolitical Shock Service.
Stress-tests portfolio holdings against major historical financial crises and macro shocks:
- 1987 Black Monday Flash Crash
- 2000-2002 Dot-Com Bubble Bust
- 2008 Lehman Brothers Global Financial Crisis
- 2011 European Sovereign Debt Crisis
- 2020 Covid-19 Pandemic Crash & V-Recovery
- 2022 Stagflation & Rate Shock
- Geopolitical Energy & Trade Route Shock
"""

from typing import Dict, Any, List, Optional
import math


class CrisisScenarioService:
    """
    Simulates portfolio behavior across historical crises using multi-factor sensitivity models,
    beta scaling, sector transmission vectors, and duration impacts.
    """

    CRISIS_SCENARIOS = {
        "black_monday_1987": {
            "id": "black_monday_1987",
            "name": "1987 Black Monday Flash Crash",
            "period": "19. Oktober 1987",
            "category": "Liquiditätsschock",
            "description": "Größter Tagesverlust der Börsengeschichte (-22,6% im Dow Jones an einem Tag) durch algorithmische Portfolio-Insurance und Liquiditätsverdampfung.",
            "benchmark_drawdown": -33.5,
            "benchmark_name": "S&P 500",
            "recovery_months": 18,
            "volatility_spike": 150.0,
            "sector_factors": {
                "technology": 1.15,
                "financial": 1.25,
                "consumer_cyclical": 1.10,
                "consumer_defensive": 0.65,
                "healthcare": 0.70,
                "utilities": 0.60,
                "energy": 0.95,
                "industrials": 1.05,
                "real_estate": 1.20,
                "materials": 1.00,
                "communication": 1.00,
            },
            "asset_class_factors": {
                "equity": 1.00,
                "fixed_income": -0.15,  # Bonds rallied as flight to safety
                "gold": -0.25,          # Gold gained
                "cash": 0.00,
            },
            "trajectory": [
                {"label": "Start (T-0)", "month": 0, "market_pct": 0.0},
                {"label": "Crash-Tag (T+1)", "month": 1, "market_pct": -22.6},
                {"label": "Tiefpunkt", "month": 2, "market_pct": -33.5},
                {"label": "Zwischenerholung (6M)", "month": 6, "market_pct": -19.2},
                {"label": "Konsolidierung (12M)", "month": 12, "market_pct": -8.5},
                {"label": "Erholung (18M)", "month": 18, "market_pct": 0.0},
            ]
        },
        "dotcom_bust_2000": {
            "id": "dotcom_bust_2000",
            "name": "2000–2002 Dot-Com Crash",
            "period": "März 2000 – Oktober 2002",
            "category": "Bewertungsblase",
            "description": "Platzen der Technologie- und Internet-Blase. Nasdaq stürzt um 78% ab, während defensive Value- und Dividendentitel stabil bleiben.",
            "benchmark_drawdown": -49.1,
            "benchmark_name": "S&P 500",
            "recovery_months": 56,
            "volatility_spike": 85.0,
            "sector_factors": {
                "technology": 1.65,
                "communication": 1.50,
                "financial": 0.85,
                "consumer_cyclical": 1.10,
                "consumer_defensive": 0.40,
                "healthcare": 0.45,
                "utilities": 0.50,
                "energy": 0.55,
                "industrials": 0.90,
                "real_estate": 0.40,
                "materials": 0.70,
            },
            "asset_class_factors": {
                "equity": 1.00,
                "fixed_income": -0.30,  # Treasuries surged
                "gold": -0.20,
                "cash": 0.00,
            },
            "trajectory": [
                {"label": "Start (März 2000)", "month": 0, "market_pct": 0.0},
                {"label": "Erster Rutsch (6M)", "month": 6, "market_pct": -15.4},
                {"label": "Bärenmarkt (12M)", "month": 12, "market_pct": -28.0},
                {"label": "Tiefpunkt (30M)", "month": 30, "market_pct": -49.1},
                {"label": "Bodenbildung (36M)", "month": 36, "market_pct": -34.0},
                {"label": "Erholung (56M)", "month": 56, "market_pct": 0.0},
            ]
        },
        "gfc_lehman_2008": {
            "id": "gfc_lehman_2008",
            "name": "2008 Lehman Global Financial Crisis",
            "period": "Oktober 2007 – März 2009",
            "category": "Systemische Bankenkrise",
            "description": "Kollaps des US-Subprime-Marktes und Insolvenz von Lehman Brothers. Weltweiter Krediteinfrierungsschock mit -56,8% Kursverlust.",
            "benchmark_drawdown": -56.8,
            "benchmark_name": "MSCI World",
            "recovery_months": 48,
            "volatility_spike": 220.0,
            "sector_factors": {
                "financial": 1.55,
                "real_estate": 1.45,
                "consumer_cyclical": 1.25,
                "industrials": 1.20,
                "materials": 1.20,
                "technology": 0.90,
                "energy": 1.10,
                "communication": 0.85,
                "consumer_defensive": 0.55,
                "healthcare": 0.60,
                "utilities": 0.65,
            },
            "asset_class_factors": {
                "equity": 1.00,
                "fixed_income": -0.20,
                "gold": -0.35,  # Gold +25%
                "cash": 0.00,
            },
            "trajectory": [
                {"label": "Start (Okt 2007)", "month": 0, "market_pct": 0.0},
                {"label": "Lehman-Insolvenz (11M)", "month": 11, "market_pct": -24.5},
                {"label": "Panikverkäufe (14M)", "month": 14, "market_pct": -45.2},
                {"label": "Tiefpunkt (17M)", "month": 17, "market_pct": -56.8},
                {"label": "Rebound (24M)", "month": 24, "market_pct": -28.4},
                {"label": "Erholung (48M)", "month": 48, "market_pct": 0.0},
            ]
        },
        "euro_debt_2011": {
            "id": "euro_debt_2011",
            "name": "2011 Euro-Staatsschuldenkrise",
            "period": "Mai 2011 – Oktober 2011",
            "category": "Staatsschuldenkrise",
            "description": "Eskalation der Schuldenkrise in Griechenland, Italien und Spanien mit Euro-Zerfallsängsten und massiver Bonitäts-Spreadausweitung.",
            "benchmark_drawdown": -24.2,
            "benchmark_name": "EuroStoxx 50",
            "recovery_months": 14,
            "volatility_spike": 90.0,
            "sector_factors": {
                "financial": 1.60,
                "real_estate": 1.25,
                "industrials": 1.15,
                "materials": 1.10,
                "consumer_cyclical": 1.05,
                "energy": 1.00,
                "technology": 0.85,
                "communication": 0.80,
                "healthcare": 0.55,
                "consumer_defensive": 0.50,
                "utilities": 0.70,
            },
            "asset_class_factors": {
                "equity": 1.00,
                "fixed_income": -0.15,
                "gold": -0.40,
                "cash": 0.00,
            },
            "trajectory": [
                {"label": "Start (Mai 2011)", "month": 0, "market_pct": 0.0},
                {"label": "Griechenland-Schock (2M)", "month": 2, "market_pct": -12.4},
                {"label": "Tiefpunkt (5M)", "month": 5, "market_pct": -24.2},
                {"label": "Whatever it takes (8M)", "month": 8, "market_pct": -11.0},
                {"label": "Erholung (14M)", "month": 14, "market_pct": 0.0},
            ]
        },
        "covid_crash_2020": {
            "id": "covid_crash_2020",
            "name": "2020 Covid-19 Pandemie & V-Erholung",
            "period": "Februar 2020 – April 2020",
            "category": "Exogener Angebotsschock",
            "description": "Historisch rasantester 30%-Einbruch in 22 Handelstagen durch globale Lockdowns, gefolgt von unbegrenzter Notenbank-Liquidität.",
            "benchmark_drawdown": -34.0,
            "benchmark_name": "S&P 500",
            "recovery_months": 6,
            "volatility_spike": 280.0,
            "sector_factors": {
                "energy": 1.55,
                "consumer_cyclical": 1.30,
                "real_estate": 1.25,
                "financial": 1.20,
                "industrials": 1.15,
                "materials": 1.05,
                "communication": 0.75,
                "technology": 0.70,
                "utilities": 0.65,
                "healthcare": 0.50,
                "consumer_defensive": 0.45,
            },
            "asset_class_factors": {
                "equity": 1.00,
                "fixed_income": -0.25,
                "gold": -0.30,
                "cash": 0.00,
            },
            "trajectory": [
                {"label": "Start (Feb 2020)", "month": 0, "market_pct": 0.0},
                {"label": "Lockdown-Schock (1M)", "month": 1, "market_pct": -24.0},
                {"label": "Tiefpunkt (23. März)", "month": 2, "market_pct": -34.0},
                {"label": "Fed-Bazooka (3M)", "month": 3, "market_pct": -14.5},
                {"label": "Tech-Rallye (4M)", "month": 4, "market_pct": -5.2},
                {"label": "Neues Allzeithoch (6M)", "month": 6, "market_pct": 2.5},
            ]
        },
        "stagflation_2022": {
            "id": "stagflation_2022",
            "name": "2022 Stagflations- & Zinsschock",
            "period": "Januar 2022 – Oktober 2022",
            "category": "Zinswende & Inflation",
            "description": "Inflationsschub auf 9% und aggressiver Zinserhöhungszyklus. Historischer Fehlschlag der klassischen 60/40-Allokation (Aktien -25%, Anleihen -16%).",
            "benchmark_drawdown": -25.4,
            "benchmark_name": "S&P 500",
            "recovery_months": 24,
            "volatility_spike": 65.0,
            "sector_factors": {
                "technology": 1.45,
                "communication": 1.40,
                "consumer_cyclical": 1.30,
                "real_estate": 1.25,
                "financial": 0.90,
                "industrials": 0.85,
                "materials": 0.80,
                "utilities": 0.50,
                "healthcare": 0.40,
                "consumer_defensive": 0.35,
                "energy": -0.80,  # Energy surged +60%
            },
            "asset_class_factors": {
                "equity": 1.00,
                "fixed_income": 0.65,  # Bonds fell heavily due to duration!
                "gold": 0.10,
                "cash": 0.00,
            },
            "trajectory": [
                {"label": "Start (Jan 2022)", "month": 0, "market_pct": 0.0},
                {"label": "Kriegsausbruch (2M)", "month": 2, "market_pct": -10.2},
                {"label": "75bps Fed-Hike (5M)", "month": 5, "market_pct": -18.5},
                {"label": "Tiefpunkt (10M)", "month": 10, "market_pct": -25.4},
                {"label": "Bodenbildung (14M)", "month": 14, "market_pct": -14.0},
                {"label": "Erholung (24M)", "month": 24, "market_pct": 0.0},
            ]
        },
        "geopolitical_energy_shock": {
            "id": "geopolitical_energy_shock",
            "name": "Geopolitischer Energie- & Handelskrisenschock",
            "period": "Stresstest-Szenario",
            "category": "Geopolitische Blockade",
            "description": "Blockade der Straße von Hormus und des Roten Meeres: Ölpreis springt auf 140 $/Barrel, Transportkosten verfünffachen sich, Lieferkettenstau.",
            "benchmark_drawdown": -28.5,
            "benchmark_name": "MSCI World",
            "recovery_months": 16,
            "volatility_spike": 110.0,
            "sector_factors": {
                "consumer_cyclical": 1.45,
                "industrials": 1.35,
                "technology": 1.15,
                "financial": 1.10,
                "materials": 1.00,
                "communication": 0.90,
                "real_estate": 1.20,
                "consumer_defensive": 0.60,
                "healthcare": 0.50,
                "utilities": 0.70,
                "energy": -1.20,  # Energy companies boom
            },
            "asset_class_factors": {
                "equity": 1.00,
                "fixed_income": 0.35,  # Rates rise due to inflation
                "gold": -0.45,         # Gold soars as geopolitical safe haven
                "cash": 0.00,
            },
            "trajectory": [
                {"label": "Normalzustand (T-0)", "month": 0, "market_pct": 0.0},
                {"label": "Öl-Spike +70% (1M)", "month": 1, "market_pct": -14.0},
                {"label": "Tiefpunkt (3M)", "month": 3, "market_pct": -28.5},
                {"label": "Diplomatische Entspannung (6M)", "month": 6, "market_pct": -16.2},
                {"label": "Routenöffnung (10M)", "month": 10, "market_pct": -7.5},
                {"label": "Erholung (16M)", "month": 16, "market_pct": 0.0},
            ]
        }
    }

    SECTOR_KEYWORDS = {
        "technology": ["tech", "software", "semiconductor", "chip", "it", "cloud", "ai", "hardware", "apple", "microsoft", "nvidia", "asml", "sap", "amd", "intel"],
        "financial": ["bank", "insurance", "financial", "asset management", "jpmorgan", "allianz", "visa", "mastercard"],
        "consumer_cyclical": ["automotive", "car", "retail", "luxury", "tesla", "amazon", "mercedes", "bmw", "nike", "lvmh"],
        "consumer_defensive": ["food", "beverage", "staple", "household", "tobacco", "nestle", "pepsi", "coca", "procter", "unilever"],
        "healthcare": ["health", "pharma", "biotech", "medical", "drug", "novartis", "roche", "pfizer", "novo", "johnson"],
        "energy": ["oil", "gas", "petroleum", "energy", "shell", "bp", "total", "exxon", "chevron"],
        "industrials": ["industrial", "aerospace", "defense", "machinery", "siemens", "boeing", "airbus", "caterpillar"],
        "utilities": ["utility", "electric", "power", "water", "e.on", "rwe", "iberdrola", "enel"],
        "real_estate": ["reit", "real estate", "property", "immobilien", "vonovia"],
        "materials": ["chemical", "mining", "steel", "gold", "basf", "linde", "rio tinto"],
        "communication": ["telecom", "media", "entertainment", "telekom", "alphabet", "meta", "netflix", "disney"],
    }

    @classmethod
    def detect_sector(cls, ticker: str, name: str) -> str:
        text = f"{ticker} {name}".lower()
        for sector, keywords in cls.SECTOR_KEYWORDS.items():
            if any(k in text for k in keywords):
                return sector
        return "technology"  # default market-sensitive proxy

    @classmethod
    def detect_asset_class(cls, ticker: str, name: str) -> str:
        text = f"{ticker} {name}".lower()
        if any(k in text for k in ["gold", "gld", "xau", "silber"]):
            return "gold"
        if any(k in text for k in ["bond", "treasury", "bund", "renten", "fixed income", "yield", "anleihe"]):
            return "fixed_income"
        if any(k in text for k in ["cash", "geldmarkt", "overnight", "liquidity"]):
            return "cash"
        return "equity"

    @classmethod
    def analyze_portfolio(cls, holdings: List[Dict[str, Any]], total_value: float = 0.0) -> Dict[str, Any]:
        """
        Runs comprehensive historical crisis scenario replay across all 7 pre-calibrated macro events.
        """
        if not holdings:
            return {"error": "Portfolio has no holdings"}

        # Calculate total portfolio value if not provided
        if total_value <= 0:
            total_value = sum(float(h.get("shares", 0)) * float(h.get("current_price", 0)) for h in holdings)
        if total_value <= 0:
            total_value = sum(float(h.get("value", 0)) for h in holdings)
        if total_value <= 0:
            total_value = 100000.0  # Normalized fallback

        # Extract weights and metadata
        parsed_holdings = []
        for h in holdings:
            shares = float(h.get("shares", 0))
            price = float(h.get("current_price", h.get("price", 0)))
            val = float(h.get("value", shares * price if shares and price else 0))
            if val <= 0 and total_value > 0:
                val = total_value / len(holdings)
            weight = (val / total_value) if total_value > 0 else (1.0 / len(holdings))

            ticker = str(h.get("ticker", "UNKNOWN")).upper()
            name = str(h.get("name", ticker))
            beta = float(h.get("beta", 1.0))
            if beta <= 0 or math.isnan(beta):
                beta = 1.0

            sector = cls.detect_sector(ticker, name)
            asset_class = cls.detect_asset_class(ticker, name)

            parsed_holdings.append({
                "ticker": ticker,
                "name": name,
                "value": val,
                "weight": weight,
                "beta": beta,
                "sector": sector,
                "asset_class": asset_class,
            })

        # Calculate safe haven percentage (Cash + Gold + Govt Bonds)
        safe_haven_pct = sum(
            h["weight"] * 100.0 for h in parsed_holdings
            if h["asset_class"] in ["cash", "gold", "fixed_income"] or h["sector"] in ["utilities", "consumer_defensive"]
        )

        scenario_results = {}
        worst_drawdown = 0.0
        worst_crisis_name = ""

        for crisis_key, scenario in cls.CRISIS_SCENARIOS.items():
            bench_dd = scenario["benchmark_drawdown"]  # e.g. -33.5%
            sec_factors = scenario["sector_factors"]
            asset_factors = scenario["asset_class_factors"]

            holdings_impact = []
            port_drawdown_pct = 0.0

            for h in parsed_holdings:
                # Base market drop
                base_drop = bench_dd

                # Asset class adjustment
                if h["asset_class"] != "equity":
                    # Non-equity assets follow asset_class_factors
                    asset_factor = asset_factors.get(h["asset_class"], 0.0)
                    h_loss_pct = bench_dd * asset_factor
                else:
                    # Sector factor
                    sec_factor = sec_factors.get(h["sector"], 1.0)
                    # Beta scaling (capped for stability)
                    effective_beta = max(0.4, min(2.2, h["beta"]))
                    h_loss_pct = base_drop * effective_beta * sec_factor

                # Bound drop to -99% minimum
                h_loss_pct = max(-98.0, min(100.0, h_loss_pct))
                h_loss_eur = h["value"] * (h_loss_pct / 100.0)
                port_drawdown_pct += (h_loss_pct * h["weight"])

                # Resilience classification
                if h_loss_pct > 2.0:
                    resilience_label = "Krisen-Hedge (Profitiert)"
                    resilience_tone = "green"
                elif h_loss_pct >= -15.0:
                    resilience_label = "Resistent (Geringer Verlust)"
                    resilience_tone = "blue"
                elif h_loss_pct >= -35.0:
                    resilience_label = "Moderat betroffen"
                    resilience_tone = "amber"
                else:
                    resilience_label = "Fragil (Hohes Krisenrisiko)"
                    resilience_tone = "red"

                holdings_impact.append({
                    "ticker": h["ticker"],
                    "name": h["name"],
                    "value": round(h["value"], 2),
                    "weight_pct": round(h["weight"] * 100.0, 2),
                    "sector": h["sector"],
                    "asset_class": h["asset_class"],
                    "beta": round(h["beta"], 2),
                    "projected_loss_pct": round(h_loss_pct, 2),
                    "projected_loss_eur": round(h_loss_eur, 2),
                    "resilience_label": resilience_label,
                    "resilience_tone": resilience_tone,
                })

            # Sort holdings by loss (worst first)
            holdings_impact.sort(key=lambda x: x["projected_loss_pct"])

            port_loss_eur = total_value * (port_drawdown_pct / 100.0)

            if port_drawdown_pct < worst_drawdown:
                worst_drawdown = port_drawdown_pct
                worst_crisis_name = scenario["name"]

            # Compute crisis trajectory replay
            # Scales historical trajectory steps relative to the portfolio's specific drawdown
            trajectory = []
            scale_ratio = (port_drawdown_pct / bench_dd) if bench_dd != 0 else 1.0
            for step in scenario["trajectory"]:
                m_pct = step["market_pct"]
                p_pct = m_pct * scale_ratio
                p_val = total_value * (1.0 + p_pct / 100.0)
                m_val = total_value * (1.0 + m_pct / 100.0)
                trajectory.append({
                    "label": step["label"],
                    "month": step["month"],
                    "portfolio_pct": round(p_pct, 2),
                    "market_pct": round(m_pct, 2),
                    "portfolio_value": round(p_val, 2),
                    "market_value": round(m_val, 2),
                })

            # Relative performance vs benchmark
            alpha_in_crisis = port_drawdown_pct - bench_dd

            scenario_results[crisis_key] = {
                "id": scenario["id"],
                "name": scenario["name"],
                "period": scenario["period"],
                "category": scenario["category"],
                "description": scenario["description"],
                "benchmark_name": scenario["benchmark_name"],
                "benchmark_drawdown": scenario["benchmark_drawdown"],
                "recovery_months": scenario["recovery_months"],
                "volatility_spike": scenario["volatility_spike"],
                "portfolio_drawdown_pct": round(port_drawdown_pct, 2),
                "portfolio_loss_eur": round(port_loss_eur, 2),
                "alpha_in_crisis": round(alpha_in_crisis, 2),
                "outperformed_benchmark": port_drawdown_pct > bench_dd,
                "trajectory": trajectory,
                "top_vulnerable": holdings_impact[:3],
                "top_resilient": sorted(holdings_impact, key=lambda x: x["projected_loss_pct"], reverse=True)[:3],
                "holdings": holdings_impact,
            }

        # Overall Portfolio Crisis Resilience Score (0 to 100)
        # 100 = minimal drawdown, high diversification, high safe-havens
        # 0 = extreme fragile, hyper-levered, beta > 1.8
        avg_drawdown = sum(s["portfolio_drawdown_pct"] for s in scenario_results.values()) / len(scenario_results)
        avg_bench_drawdown = sum(s["benchmark_drawdown"] for s in scenario_results.values()) / len(scenario_results)
        
        # Base score starts around 50, adjusted by drawdown vs benchmark and safe havens
        resilience_score = 50.0 + (avg_drawdown - avg_bench_drawdown) * 1.8 + (safe_haven_pct * 0.4)
        resilience_score = round(max(5.0, min(95.0, resilience_score)), 1)

        if resilience_score >= 75:
            resilience_rating = "Hohe Krisenfestigkeit (Defensiver Schutzschild)"
            resilience_badge = "Exzellent"
        elif resilience_score >= 50:
            resilience_rating = "Solide Resilienz (Marktkonform)"
            resilience_badge = "Solide"
        elif resilience_score >= 35:
            resilience_rating = "Erhöhte Krisen-Verletzlichkeit"
            resilience_badge = "Mäßig"
        else:
            resilience_rating = "Akute Krisenanfälligkeit (Klumpen- & Betarisiko)"
            resilience_badge = "Kritisch"

        avg_recovery_months = round(sum(s["recovery_months"] for s in scenario_results.values()) / len(scenario_results), 1)

        # Institutional Playbook recommendations
        playbook = [
            {
                "title": "Asymmetrische Put-Absicherung (Tail-Hedging)",
                "type": "Hedge",
                "priority": "Hoch" if resilience_score < 50 else "Empfohlen",
                "description": "Erwägen Sie 2–3% Portfolio-Allokation in OTM-Put-Optionen (Delta 0.15–0.25) auf S&P 500 oder DAX 40 zur Dämpfung extremer Flash-Crashes."
            },
            {
                "title": "Liquiditäts- & Safe-Haven-Puffer",
                "type": "Allokation",
                "priority": "Dringend" if safe_haven_pct < 5.0 else "Solide",
                "description": f"Aktuelle Safe-Haven-Quote beträgt {round(safe_haven_pct, 1)}%. Institutionalisierte Standards empfehlen mindestens 10–15% in Gold, Geldmarkt oder kurzlaufenden Staatsanleihen."
            },
            {
                "title": "Anti-Zyklische Rebalancing-Bänder",
                "type": "Strategie",
                "priority": "Standard",
                "description": "Definieren Sie feste Kauf-Trigger bei -20% und -30% Marktrückgang, um in der Talsohle historischer Krisen schrittweise günstige Qualitätsaktien nachzukaufen."
            },
            {
                "title": "Sektorale Klumpenrisiko-Reduktion",
                "type": "Risiko",
                "priority": "Mittel",
                "description": "Überprüfen Sie Titel mit Beta > 1.4 in hoch bewerteten Wachstumsbranchen, da diese in Zinsschocks und Liquiditätskrisen überproportional fallen."
            }
        ]

        return {
            "portfolio_value": round(total_value, 2),
            "safe_haven_pct": round(safe_haven_pct, 2),
            "resilience_score": resilience_score,
            "resilience_rating": resilience_rating,
            "resilience_badge": resilience_badge,
            "worst_drawdown_pct": round(worst_drawdown, 2),
            "worst_drawdown_eur": round(total_value * (worst_drawdown / 100.0), 2),
            "worst_crisis_name": worst_crisis_name,
            "avg_recovery_months": avg_recovery_months,
            "scenarios": scenario_results,
            "playbook": playbook,
            "holdings_count": len(parsed_holdings),
        }

    @classmethod
    def simulate_custom_shock(
        cls,
        holdings: List[Dict[str, Any]],
        total_value: float,
        equity_shock_pct: float = -20.0,
        rate_shock_bps: float = 100.0,
        oil_shock_pct: float = 30.0,
        credit_spread_bps: float = 150.0,
        usd_shock_pct: float = 5.0,
    ) -> Dict[str, Any]:
        """
        Dynamically simulates custom macro shock vectors across equities, duration, commodities, and credit spreads.
        """
        if total_value <= 0:
            total_value = sum(float(h.get("value", 0)) for h in holdings)
        if total_value <= 0:
            total_value = 100000.0

        simulated_holdings = []
        total_loss_eur = 0.0

        for h in holdings:
            shares = float(h.get("shares", 0))
            price = float(h.get("current_price", h.get("price", 0)))
            val = float(h.get("value", shares * price if shares and price else 0))
            if val <= 0 and total_value > 0:
                val = total_value / len(holdings)

            ticker = str(h.get("ticker", "UNKNOWN")).upper()
            name = str(h.get("name", ticker))
            beta = float(h.get("beta", 1.0))
            sector = cls.detect_sector(ticker, name)
            asset_class = cls.detect_asset_class(ticker, name)

            # Impact calculation
            if asset_class == "equity":
                # Equity shock scaled by beta
                loss_pct = equity_shock_pct * max(0.5, min(2.2, beta))
                # Sector sensitivity to oil
                if sector == "energy":
                    loss_pct += (oil_shock_pct * 0.4)
                elif sector in ["consumer_cyclical", "industrials"]:
                    loss_pct -= (oil_shock_pct * 0.1)
                # Rate shock impact on tech/real estate
                if sector in ["technology", "real_estate"]:
                    loss_pct -= (rate_shock_bps / 100.0) * 2.5
            elif asset_class == "fixed_income":
                # Duration loss: -ModD * dY
                approx_duration = 6.5
                loss_pct = -(approx_duration * (rate_shock_bps / 100.0)) - (credit_spread_bps / 100.0 * 1.5)
            elif asset_class == "gold":
                # Gold gains in geopolitical and equity shocks
                loss_pct = (-equity_shock_pct * 0.25) + (oil_shock_pct * 0.15)
            else:  # Cash
                loss_pct = 0.0

            loss_pct = max(-98.0, min(150.0, loss_pct))
            loss_eur = val * (loss_pct / 100.0)
            total_loss_eur += loss_eur

            simulated_holdings.append({
                "ticker": ticker,
                "name": name,
                "sector": sector,
                "asset_class": asset_class,
                "value": round(val, 2),
                "loss_pct": round(loss_pct, 2),
                "loss_eur": round(loss_eur, 2),
            })

        total_loss_pct = (total_loss_eur / total_value * 100.0) if total_value > 0 else 0.0

        return {
            "total_value": round(total_value, 2),
            "total_loss_eur": round(total_loss_eur, 2),
            "total_loss_pct": round(total_loss_pct, 2),
            "resulting_value": round(total_value + total_loss_eur, 2),
            "parameters": {
                "equity_shock_pct": equity_shock_pct,
                "rate_shock_bps": rate_shock_bps,
                "oil_shock_pct": oil_shock_pct,
                "credit_spread_bps": credit_spread_bps,
                "usd_shock_pct": usd_shock_pct,
            },
            "holdings": sorted(simulated_holdings, key=lambda x: x["loss_pct"]),
        }
