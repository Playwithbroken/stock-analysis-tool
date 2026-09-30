# Walkthrough: Feature 19 – Institutional Multi-Currency FX Exposure & Currency Hedging Terminal (Covered Interest Parity Forward Cost, FX Value-at-Risk & Minimum Variance Hedge Ratio)

Wir haben das institutionelle **Multi-Currency FX Exposure & Currency Hedging Terminal** nach internationalen Bankenstandards (Covered Interest Parity, FX-VaR, Minimum Variance Hedge Ratio & Makro-Schock-Simulation) erfolgreich implementiert, getestet und in das Portfolio-Dashboard integriert.

---

## 1. Mathematisches & Regulatorisches Modell (`src/currency_hedging_service.py`)

- **Look-Through Net Currency Exposure**:
  - Automatische Erkennung und Zuordnung der Handels- und Abrechnungswährungen aller Portfolio-Assets (**EUR, USD, CHF, GBP, JPY, CAD, AUD**).
  - Berechnung der Netto-Gewichtung je Währung und Ausweisung der ungesicherten Fremdwährungsquote.
- **Covered Interest Parity (CIP) & Forward-Hedging-Kosten**:
  - Exakte Berechnung des 1-Jahres-Terminkurses (Forward Rate) und der Forward-Punkte:
    $$F = S \cdot \frac{1 + r_{\text{foreign}}}{1 + r_{\text{EUR}}}$$
  - Quantifizierung des annualisierten Carry:
    - **USD (Fed 4,75 % vs. EZB 3,25 %)**: $+1,50 \%$ p.a. Hedging-Kosten (Negativer Carry).
    - **CHF (SNB 1,00 % vs. EZB 3,25 %)**: $-2,25 \%$ p.a. Hedging-Kosten (Positiver Carry / Zinsvorteil für EUR-Anleger!).
    - **GBP (BoE 4,75 % vs. EZB 3,25 %)**: $+1,50 \%$ p.a. Hedging-Kosten.
- **Minimum Variance Hedge Ratio (MVHR)**:
  - Mathematisch optimale Absicherungsquote zur Minimierung der Portfoliovolatilität in Euro:
    $$h^* = -\rho(R_{\text{asset}}, R_{\text{fx}}) \cdot \frac{\sigma_{\text{asset}}}{\sigma_{\text{fx}}}$$
  - Berücksichtigt die empirisch negative Korrelation von US-Aktien zu EUR/USD bei Marktstress (Flight-to-Safety).
- **FX Value-at-Risk (Parametrisch & Diversifiziert)**:
  - Isolierte Berechnung des reinen Währungsrisikos (ohne Aktienkursrisiko):
    $$\text{VaR}_{95\%} = 1{,}645 \cdot \sigma_{\text{FX, port}} \cdot \text{Wert}_{\text{Port, FX}}$$
    $$\text{VaR}_{99\%} = 2{,}326 \cdot \sigma_{\text{FX, port}} \cdot \text{Wert}_{\text{Port, FX}}$$
  - Ausweisung auf 1-Tages- und 1-Jahres-Horizont in Euro und Prozent.
- **Makro- und Geopolitische FX-Szenarien**:
  - Standard-Szenarien:
    1. *EUR-Rallye (+10 %)*: Euro erstarkt durch EZB-Zinsüberraschung; breite Abwertung von Fremdwährungsbeständen.
    2. *US-Dollar Rallye (+10 %)*: Dollar gewinnt; Währungsgewinn auf US-Positionen.
    3. *Swiss Franc Safe-Haven Shock (+8 %)*: Geopolitische Eskalation treibt Kapital in den CHF.
    4. *EUR/USD Paritäts-Crash (1,00)*: Historischer Dollar-Höchststand mit $+8{,}5 \%$ FX-Rückenwind.

---

## 2. API-Endpunkte (`api.py`)

- **`GET /api/portfolio/{p_id}/currency-hedging`**:
  - Liefert Net FX Exposure, FX-VaR (95 % & 99 %), Devisenterminkurse (CIP), Zinsdifferenzen, optimale Absicherungsquoten und Holdings-Zuordnung.
- **`POST /api/portfolio/currency-hedging/simulate`**:
  - Simuliert benutzerdefinierte Devisenschocks (z. B. USD $+5\%$, CHF $-3\%$) mit sofortiger Euro- und Prozent-Auswirkung auf das Portfolio.

---

## 3. Institutional Frontend (`frontend/src/components/CurrencyHedgingTerminal.tsx`)

- **4 Institutional KPI Scorecards**:
  - **Fremdwährungs-Quote**: z. B. `74,2 %` mit Risikobadge (*Erhöht* / *Moderat* / *Gering*).
  - **FX Value-at-Risk (1J, 95 %)**: z. B. `4.820 €` (`6,8 %`).
  - **Optimale Absicherung (MVHR)**: z. B. `38.400 €` (Minimum-Variance-Optimum).
  - **Hedging Carry-Kosten**: z. B. `-1,45 % p.a.` basierend auf Zinssatzdifferenzen (CIP).
- **3 Interaktive Tabs**:
  1. **Währungsallokation & Zinsdifferenzen**:
     - Recharts Bar Chart (mit `MeasuredChartFrame`) für die Währungsallokation.
     - Detaillierte Zins- & Forward-Karten je Währung (Spot-Kurs, 1J-Terminkurs, Zinsdifferenz, Carry-Status).
  2. **Holdings FX-Attribution**:
     - Vollständige Tabelle aller Titel: Ticker, Währung, Positionswert, 1J-Hedging-Kosten %, empfohlene Quote (MVHR), empfohlene Absicherungssumme in €.
     - Klick auf Ticker öffnet die Einzelanalyse.
  3. **Interaktiver FX-Stresstest**:
     - 4 vordefinierte Makro-Szenarien mit Euro-Gewinn/Verlust.
     - Interaktive Schieberegler für USD, CHF und GBP ($-20\%$ bis $+20\%$) mit Echtzeit-Berechnung des simulierten Portfolio-Effekts in Euro und Prozent.
- **Aktionsleisten-Integration in `PortfolioView.tsx`**:
  - Button **„FX & Währungsrisiko“** mit `Coins`-Icon.

---

## 4. Qualitätssicherung & Verifikation

1. **`qa_currency_hedging.py`**:
   - 4/4 Tests erfolgreich bestanden:
     - Währungserkennung und Allokationsaggregation (Summe = 100 %).
     - Covered Interest Parity Terminkurse und Carry-Dynamiken (USD negativer Carry, CHF positiver Carry, EUR neutral).
     - FX-VaR (99 % $\ge$ 95 %) und Minimum Variance Hedge Ratio Grenzen.
     - Alle API-Endpunkte mit Authentifizierung und Session-Cookies verifiziert.
2. **Gesamte Regression-Suite (15 Test-Suites)**:
   - `qa_currency_hedging.py`
   - `qa_liquidity_risk.py`
   - `qa_esg_sustainability.py`
   - `qa_tail_risk_terminal.py`
   - `qa_efficient_frontier_optimizer.py`
   - `qa_correlation_risk_matrix.py`
   - `qa_factor_decomposition.py`
   - `qa_monte_carlo_simulator.py`
   - `qa_tax_harvesting.py`
   - `qa_options_pricing.py`
   - `qa_etf_overlap_feedetector.py`
   - `qa_superinvestor_radar.py`
   - `qa_dcf_valuation.py`
   - `qa_portfolio_rebalancing.py`
   - `qa_bull_bear_debate.py`
   - **Ergebnis: 55 von 55 Tests bestanden (OK in 9,6s).**
3. **Frontend Production Build**:
   - `npm run build` erfolgreich in 5,47s ohne TypeScript- oder Bundling-Fehler ausgeführt.
