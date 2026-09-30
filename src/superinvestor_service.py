"""
Superinvestor & Insider Radar Service
Tracks SEC Form 4 insider transactions and 13F Superinvestor portfolios.
"""

import re
import math
from typing import Dict, Any, List, Optional
from datetime import datetime
import pandas as pd


# Curated verified 13F Superinvestor Holdings Database
SUPERINVESTORS = [
    {
        "id": "warren_buffett",
        "name": "Warren Buffett",
        "firm": "Berkshire Hathaway",
        "style": "Deep Value & Moat Investing",
        "avatar": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=120&h=120&fit=crop&crop=face",
        "holdings": {
            "AAPL": {"weight_pct": 28.5, "action": "REDUCED", "shares": 300000000, "comment": "Größte Portfolio-Position, trotz partieller Gewinnmitnahmen weiterhin Kerninvestment."},
            "AXP": {"weight_pct": 14.2, "action": "MAINTAINED", "shares": 151600000, "comment": "Jahrzehntelanger Burggraben im globalen Premium-Zahlungsverkehr."},
            "BAC": {"weight_pct": 10.8, "action": "REDUCED", "shares": 750000000, "comment": "Großbank mit starkem US-Einlagengeschäft; Teilverkäufe zur Umschichtung."},
            "KO": {"weight_pct": 11.5, "action": "MAINTAINED", "shares": 400000000, "comment": "Uralte Dividenden-Cash-Cow mit unvergleichlicher Preismacht."},
            "OXY": {"weight_pct": 5.8, "action": "BOUGHT", "shares": 255000000, "comment": "Kontinuierlicher Zukauf; Buffett hält über 28 % der Stammaktien."},
            "MCO": {"weight_pct": 4.2, "action": "MAINTAINED", "shares": 24670000, "comment": "Rating-Duopol mit unübertroffenen operativen Margen."},
            "KHC": {"weight_pct": 3.7, "action": "MAINTAINED", "shares": 325600000, "comment": "Basiskonsum-Cashflow."},
            "CVX": {"weight_pct": 5.2, "action": "MAINTAINED", "shares": 123000000, "comment": "Integrierter Energiegigant mit hoher Free-Cashflow-Rendite."},
            "CB": {"weight_pct": 2.6, "action": "BOUGHT", "shares": 27000000, "comment": "Das 'geheime' Buffett-Investment im Sachversicherungsmarkt."},
            "NU": {"weight_pct": 0.8, "action": "MAINTAINED", "shares": 107000000, "comment": "Lateinamerikanische Neo-Bank mit extremem Kundenwachstum."},
        }
    },
    {
        "id": "michael_burry",
        "name": "Michael Burry",
        "firm": "Scion Asset Management",
        "style": "Deep Value & Asymmetric Contrarian",
        "avatar": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=120&h=120&fit=crop&crop=face",
        "holdings": {
            "BABA": {"weight_pct": 16.5, "action": "BOUGHT", "shares": 200000, "comment": "Massive Unterbewertung chinesischer Tech-Giganten bei hohen Aktienrückkäufen."},
            "JD": {"weight_pct": 14.8, "action": "BOUGHT", "shares": 500000, "comment": "Führende E-Commerce-Logistik in Asien mit hoher Cash-Generierung."},
            "BIDU": {"weight_pct": 11.2, "action": "NEW", "shares": 120000, "comment": "Chinas führende Suchmaschine und autonomer Fahrpionier."},
            "UNH": {"weight_pct": 8.5, "action": "NEW", "shares": 35000, "comment": "Antizyklischer Einstieg nach regulatorischem Gegenwind im US-Healthcare-Sektor."},
            "CI": {"weight_pct": 7.8, "action": "NEW", "shares": 40000, "comment": "Managed Healthcare Value-Play mit attraktivem Forward-KGV."},
            "SQ": {"weight_pct": 5.4, "action": "REDUCED", "shares": 100000, "comment": "Block Inc. Turnaround im Cash App Ökosystem."},
            "BP": {"weight_pct": 9.2, "action": "BOUGHT", "shares": 450000, "comment": "Günstige europäische integrierte Energie mit Dividendenfokus."},
        }
    },
    {
        "id": "bill_ackman",
        "name": "Bill Ackman",
        "firm": "Pershing Square Capital",
        "style": "Concentrated Quality Activist",
        "avatar": "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=120&h=120&fit=crop&crop=face",
        "holdings": {
            "GOOGL": {"weight_pct": 12.8, "action": "MAINTAINED", "shares": 4200000, "comment": "Kerneinstieg wegen KI-Führung und extrem solider Bilanz."},
            "GOOG": {"weight_pct": 6.4, "action": "MAINTAINED", "shares": 2100000, "comment": "Kombinierte Alphabet-Position macht fast 20 % des Portfolios aus."},
            "CMG": {"weight_pct": 14.6, "action": "MAINTAINED", "shares": 2800000, "comment": "Chipotle Mexican Grill – herausragende Unit Economics und Same-Store-Sales."},
            "HLT": {"weight_pct": 15.2, "action": "MAINTAINED", "shares": 8900000, "comment": "Asset-light Franchise-Modell im Luxus- und Geschäftsreise-Segment."},
            "QSR": {"weight_pct": 13.5, "action": "MAINTAINED", "shares": 23000000, "comment": "Restaurant Brands (Burger King, Tim Hortons) mit globalem Expansionshebel."},
            "NKE": {"weight_pct": 8.9, "action": "BOUGHT", "shares": 5000000, "comment": "Turnaround-Wette auf die unangefochtene weltweite Sportartikel-Marke."},
            "CP": {"weight_pct": 11.2, "action": "MAINTAINED", "shares": 14500000, "comment": "Eisenbahnmonopol Canadian Pacific Kansas City über Nordamerika hinweg."},
        }
    },
    {
        "id": "li_lu",
        "name": "Li Lu",
        "firm": "Himalaya Capital",
        "style": "Munger-Protegé Compounder Value",
        "avatar": "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=120&h=120&fit=crop&crop=face",
        "holdings": {
            "GOOGL": {"weight_pct": 32.5, "action": "MAINTAINED", "shares": 2600000, "comment": "Größte Einzelüberzeugung von Li Lu; sieht Alphabet als langlebiges Monopol."},
            "BAC": {"weight_pct": 24.8, "action": "MAINTAINED", "shares": 14500000, "comment": "Starke US-Großbank mit massivem Einlagenüberschuss."},
            "BRK-B": {"weight_pct": 18.2, "action": "MAINTAINED", "shares": 950000, "comment": "Das ultimative Festungsinvestment von Charlie Mungers engem Vertrauten."},
            "AAPL": {"weight_pct": 15.4, "action": "MAINTAINED", "shares": 1600000, "comment": "Ökosystem-Lock-In und unübertroffenes Nutzer-Retention-Level."},
            "EWBC": {"weight_pct": 9.1, "action": "MAINTAINED", "shares": 2200000, "comment": "East West Bancorp – fokussierte US-Asien Handelsfinanzierung."},
        }
    },
    {
        "id": "cathie_wood",
        "name": "Cathie Wood",
        "firm": "ARK Invest",
        "style": "Disruptive Innovation & Growth",
        "avatar": "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=120&h=120&fit=crop&crop=face",
        "holdings": {
            "TSLA": {"weight_pct": 12.4, "action": "BOUGHT", "shares": 5200000, "comment": "Fokus auf autonomes Fahren (Robotaxi) und Robotik (Optimus)."},
            "ROKU": {"weight_pct": 8.2, "action": "MAINTAINED", "shares": 9500000, "comment": "Führendes TV-Streaming-Betriebssystem in Nordamerika."},
            "COIN": {"weight_pct": 8.8, "action": "REDUCED", "shares": 4100000, "comment": "Gewinnmitnahmen nach starkem Krypto-Rallye-Zyklus."},
            "PLTR": {"weight_pct": 5.8, "action": "BOUGHT", "shares": 7200000, "comment": "Enterprise-KI-Monetarisierung via AIP-Bootcamps."},
            "SHOP": {"weight_pct": 6.5, "action": "MAINTAINED", "shares": 6800000, "comment": "Rückenwind für weltweiten Direct-to-Consumer E-Commerce."},
            "CRSP": {"weight_pct": 5.1, "action": "MAINTAINED", "shares": 7100000, "comment": "Gen-Editing Durchbrüche bei seltenen Bluterkrankungen."},
            "HOOD": {"weight_pct": 4.9, "action": "BOUGHT", "shares": 18000000, "comment": "Retail-Brokerage Expansion und Krypto-Trading-Volumen."},
        }
    },
    {
        "id": "terry_smith",
        "name": "Terry Smith",
        "firm": "Fundsmith Equity Fund",
        "style": "Buy Good Companies, Don't Overpay, Do Nothing",
        "avatar": "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=120&h=120&fit=crop&crop=face",
        "holdings": {
            "MSFT": {"weight_pct": 10.4, "action": "MAINTAINED", "shares": 6500000, "comment": "Enterprise Software, Cloud Infrastructure und KI-Monetarisierung."},
            "META": {"weight_pct": 8.6, "action": "MAINTAINED", "shares": 4800000, "comment": "Unerreichte Werbemonetarisierung bei über 3 Milliarden täglichen Nutzern."},
            "PM": {"weight_pct": 7.5, "action": "MAINTAINED", "shares": 16000000, "comment": "ZYN und IQOS rauchfreie Produkte treiben anhaltendes Margenwachstum."},
            "V": {"weight_pct": 6.9, "action": "MAINTAINED", "shares": 7200000, "comment": "Tollbooth-Geschäftsmodell im bargeldlosen Weltzahlungssystem."},
            "PEP": {"weight_pct": 5.8, "action": "MAINTAINED", "shares": 8500000, "comment": "Frito-Lay Snack-Dominanz kombiniert mit Getränkegeschäft."},
            "IDXX": {"weight_pct": 4.9, "action": "MAINTAINED", "shares": 2900000, "comment": "Tiermedizinische Diagnostik mit über 85 % wiederkehrenden Umsätzen."},
            "GOOGL": {"weight_pct": 7.2, "action": "MAINTAINED", "shares": 12000000, "comment": "Hohe Kapitalrendite (ROCE) und massive freie Cashflows."},
        }
    },
    {
        "id": "stanley_druckenmiller",
        "name": "Stanley Druckenmiller",
        "firm": "Duquesne Family Office",
        "style": "Macro & Secular Growth Themes",
        "avatar": "https://images.unsplash.com/photo-1501196354995-cbb51c65aaea?w=120&h=120&fit=crop&crop=face",
        "holdings": {
            "NVDA": {"weight_pct": 11.8, "action": "REDUCED", "shares": 2500000, "comment": "Legendärer KI-Einstieg; Teilgewinnmitnahmen nach historischem Kurslauf."},
            "MSFT": {"weight_pct": 10.2, "action": "MAINTAINED", "shares": 1800000, "comment": "Software-Ökosystem und Copilot-Rollout."},
            "AMZN": {"weight_pct": 8.7, "action": "BOUGHT", "shares": 3400000, "comment": "AWS Cloud-Beschleunigung und Effizienzgewinne im US-Retail-Netz."},
            "LLY": {"weight_pct": 7.4, "action": "BOUGHT", "shares": 1200000, "comment": "Mounjaro/Zepbound Diabetes- und Adipositas-Megatrend."},
            "VST": {"weight_pct": 6.8, "action": "BOUGHT", "shares": 5600000, "comment": "Vistra Energy – Stromerzeugung für KI-Rechenzentren."},
        }
    }
]


class SuperinvestorService:
    """Provides insider transactions and 13F superinvestor tracking."""

    @staticmethod
    def get_superinvestors_for_ticker(ticker: str) -> List[Dict[str, Any]]:
        """Find all superinvestors who hold the specified ticker."""
        normalized = ticker.upper().strip()
        matches = []
        for inv in SUPERINVESTORS:
            holdings = inv.get("holdings", {})
            if normalized in holdings:
                h = holdings[normalized]
                matches.append({
                    "investor_id": inv["id"],
                    "investor_name": inv["name"],
                    "firm": inv["firm"],
                    "style": inv["style"],
                    "avatar": inv["avatar"],
                    "weight_pct": h["weight_pct"],
                    "action": h["action"],
                    "shares": h["shares"],
                    "comment": h["comment"]
                })

        # Sort by portfolio weight descending
        matches.sort(key=lambda x: x["weight_pct"], reverse=True)
        return matches

    @staticmethod
    def parse_insider_transactions(raw_df: Any) -> List[Dict[str, Any]]:
        """Parse yfinance insider_transactions DataFrame into structured records."""
        if raw_df is None or not isinstance(raw_df, pd.DataFrame) or raw_df.empty:
            return []

        results = []
        for _, row in raw_df.head(25).iterrows():
            raw_shares = row.get("Shares")
            shares = float(raw_shares) if raw_shares is not None and not pd.isna(raw_shares) else 0.0
            
            raw_val = row.get("Value")
            value = float(raw_val) if raw_val is not None and not pd.isna(raw_val) else 0.0

            text_col = str(row.get("Text") or "")
            trans_col = str(row.get("Transaction") or "")
            comb = (trans_col + " " + text_col).lower()

            if any(k in comb for k in ["purchase", "buy", "bought", "acquis"]):
                trans_type = "Kauf"
                is_purchase = True
                badge_color = "emerald"
            elif any(k in comb for k in ["sale", "sell", "sold", "disposit"]):
                trans_type = "Verkauf"
                is_purchase = False
                badge_color = "rose"
            elif any(k in comb for k in ["award", "grant"]):
                trans_type = "Vergütung (Grant)"
                is_purchase = False
                badge_color = "slate"
            elif any(k in comb for k in ["option", "exercise"]):
                trans_type = "Optionsausübung"
                is_purchase = False
                badge_color = "indigo"
            else:
                trans_type = "Transaktion"
                is_purchase = False
                badge_color = "slate"

            price_per_share = round(value / shares, 2) if shares > 0 and value > 0 else None
            if price_per_share is None:
                # Try regex matching 'price X.XX'
                m = re.search(r"price\s+([\d.]+)", text_col)
                if m:
                    try:
                        price_per_share = float(m.group(1))
                    except Exception:
                        pass

            date_val = row.get("Start Date")
            date_str = ""
            if date_val is not None and not pd.isna(date_val):
                if hasattr(date_val, "strftime"):
                    date_str = date_val.strftime("%Y-%m-%d")
                else:
                    date_str = str(date_val)[:10]

            results.append({
                "date": date_str,
                "insider": str(row.get("Insider") or "Unbekannter Insider"),
                "position": str(row.get("Position") or "Führungskraft / Vorstand"),
                "transaction_type": trans_type,
                "is_purchase": is_purchase,
                "badge_color": badge_color,
                "shares": int(shares),
                "value": round(value, 2),
                "price_per_share": price_per_share,
                "text": text_col
            })

        return results

    @staticmethod
    def parse_insider_summary(raw_purchases_df: Any, parsed_transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate 6m insider sentiment from purchases and transaction list."""
        buy_count = sum(1 for t in parsed_transactions if t["is_purchase"])
        sell_count = sum(1 for t in parsed_transactions if t["transaction_type"] == "Verkauf")
        total_buy_value = sum(t["value"] for t in parsed_transactions if t["is_purchase"])
        total_sell_value = sum(t["value"] for t in parsed_transactions if t["transaction_type"] == "Verkauf")

        # Check raw_purchases_df from yfinance
        if raw_purchases_df is not None and isinstance(raw_purchases_df, pd.DataFrame) and not raw_purchases_df.empty:
            try:
                for _, row in raw_purchases_df.iterrows():
                    col_name = str(row.iloc[0]).lower()
                    shares_val = row.get("Shares")
                    if not pd.isna(shares_val):
                        if "purchases" in col_name and "net" not in col_name:
                            buy_count = max(buy_count, int(row.get("Trans", buy_count) or buy_count))
                        elif "sales" in col_name and "net" not in col_name:
                            sell_count = max(sell_count, int(row.get("Trans", sell_count) or sell_count))
            except Exception:
                pass

        if buy_count > sell_count and total_buy_value >= total_sell_value:
            sentiment = "BULLISH"
            sentiment_label = "Netto-Käufe (Positives Insider-Signal)"
            sentiment_color = "emerald"
        elif sell_count > buy_count * 2:
            sentiment = "BEARISH"
            sentiment_label = "Überwiegend Verkäufe (Gewinnmitnahmen)"
            sentiment_color = "amber"  # Verkäufe sind oft Liquidation/Steuern, nicht immer Panik
        else:
            sentiment = "NEUTRAL"
            sentiment_label = "Ausgeglichen / Gemischte Transaktionen"
            sentiment_color = "slate"

        return {
            "sentiment": sentiment,
            "sentiment_label": sentiment_label,
            "sentiment_color": sentiment_color,
            "buy_count": buy_count,
            "sell_count": sell_count,
            "total_buy_value": round(total_buy_value, 2),
            "total_sell_value": round(total_sell_value, 2),
            "recent_activity": len(parsed_transactions) > 0,
        }

    @staticmethod
    def parse_institutional_holders(raw_inst_df: Any) -> List[Dict[str, Any]]:
        """Parse top institutional holders (e.g. BlackRock, Vanguard)."""
        if raw_inst_df is None or not isinstance(raw_inst_df, pd.DataFrame) or raw_inst_df.empty:
            return []

        records = []
        for _, row in raw_inst_df.head(6).iterrows():
            holder = str(row.get("Holder") or "")
            if not holder:
                continue

            shares = float(row.get("Shares") or 0.0)
            value = float(row.get("Value") or 0.0)
            pct_held = float(row.get("pctHeld") or 0.0)
            pct_change = float(row.get("pctChange") or 0.0)

            records.append({
                "holder": holder,
                "shares": int(shares),
                "value": round(value, 2),
                "pct_held": round(pct_held * 100.0, 2) if pct_held <= 1.0 else round(pct_held, 2),
                "pct_change": round(pct_change * 100.0, 2) if abs(pct_change) <= 1.0 else round(pct_change, 2)
            })

        return records

    @staticmethod
    def get_portfolio_superinvestors(holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Cross-references all portfolio holdings with Superinvestor 13F filings."""
        total_holdings_count = len(holdings)
        matched_tickers = set()
        ticker_superinvestors: Dict[str, List[Dict[str, Any]]] = {}
        all_investors_involved = set()

        def get_val(h_dict):
            if h_dict.get("value") is not None and float(h_dict.get("value") or 0) > 0:
                return float(h_dict["value"])
            sh = float(h_dict.get("shares") or 0)
            pr = float(h_dict.get("current_price") or h_dict.get("currentPrice") or h_dict.get("buy_price") or h_dict.get("buyPrice") or 1.0)
            return max(1.0, sh * pr)

        total_portfolio_value = sum(get_val(h) for h in holdings)
        endorsed_portfolio_value = 0.0

        for h in holdings:
            t = str(h.get("ticker") or "").upper().strip()
            supes = SuperinvestorService.get_superinvestors_for_ticker(t)
            if supes:
                matched_tickers.add(t)
                ticker_superinvestors[t] = supes
                for s in supes:
                    all_investors_involved.add(s["investor_name"])
                
                endorsed_portfolio_value += get_val(h)

        smart_money_pct = round((endorsed_portfolio_value / total_portfolio_value) * 100.0, 1) if total_portfolio_value > 0 else 0.0

        # Build list of matching items
        items = []
        for h in holdings:
            t = str(h.get("ticker") or "").upper().strip()
            if t in ticker_superinvestors:
                items.append({
                    "ticker": t,
                    "name": h.get("name") or t,
                    "superinvestors": ticker_superinvestors[t],
                    "superinvestors_count": len(ticker_superinvestors[t])
                })

        # Sort items by number of backing superinvestors descending
        items.sort(key=lambda x: x["superinvestors_count"], reverse=True)

        return {
            "total_holdings": total_holdings_count,
            "endorsed_holdings_count": len(matched_tickers),
            "smart_money_percentage": smart_money_pct,
            "superinvestors_involved": sorted(list(all_investors_involved)),
            "superinvestors_count": len(all_investors_involved),
            "endorsed_holdings": items,
            "headline": f"{len(matched_tickers)} von {total_holdings_count} Aktien von Superinvestoren gehalten ({smart_money_pct}% Depot-Abdeckung)" if matched_tickers else "Keine direkten Superinvestor-13F-Positionen im Depot gefunden."
        }
