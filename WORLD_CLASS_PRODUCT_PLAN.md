# Broker Freund World-Class Product Plan

Stand: 12. Juni 2026

## Zielbild

Broker Freund soll von einer starken privaten Beta zu einem professionellen Anlageberater-System werden: schnell, kritisch, nachvollziehbar, mobil perfekt nutzbar und mit einer echten Informations-Edge. Das Produkt darf nicht nur mehr Daten zeigen. Es muss bessere Entscheidungen erzwingen: Quelle pruefen, Bedeutung erklaeren, Risiko sichtbar machen, These invalidieren, Fehler lernen.

## Nicht verhandelbare Prinzipien

1. Keine blinden Kauf-/Verkaufssignale.
2. Jede Aussage braucht Quelle, Kontext, Auswirkung, Trigger und Invalidierung.
3. Telegram Alerts sind selten, wichtig und kritisch.
4. Dashboard ist Priorisierung, nicht Datensammlung.
5. Analyzer ist Dossier, nicht Suchergebnis.
6. Portfolio ist Risiko- und Zielsystem, nicht nur Liste.
7. Jede neue Funktion bekommt QA, Logging und Fallback.
8. Beratungstauglichkeit braucht Dokumentation, Eignung, Risiko und Interessenkonflikt-Kontrolle.

## Phase 1: Advisory Core

Ziel: Aus der App wird ein ernsthafter Entscheidungsrahmen.

- Kunden-/Nutzerprofil: Anlageziel, Horizont, Risikotoleranz, Liquiditaetsbedarf, Erfahrung, Verlusttragfaehigkeit.
- Suitability Layer: Jede Strategie und jedes Signal wird gegen Profil und Portfolio geprueft.
- Empfehlungstypen trennen:
  - `Information`: reine Marktinformation
  - `Watch`: beobachten
  - `Setup`: These mit Trigger
  - `Action Candidate`: nur wenn Profil, Risiko und Daten passen
  - `Avoid`: Risiko/These ungueltig
- Suitability Report pro echter Empfehlung: Warum passt es, warum nicht, welche Risiken, welche Alternativen.
- Audit Trail: Jede Empfehlung speichert Datenstand, Quellen, Score, Prompt/Regeln, Nutzerprofil-Version und Ergebnis.

Definition of Done:
- Keine Empfehlung ohne Profilcheck.
- Jede Recommendation hat Trigger, Invalidierung, Risiko, Quellenstatus und Zeitstempel.
- Export als PDF/Markdown moeglich.

## Phase 2: Signal Quality Engine

Ziel: Weniger Alerts, bessere Alerts.

- Telegram bleibt Hauptkanal.
- Alert-Typen:
  - Macro Alert
  - Public Figure Statement
  - IPO / Listing
  - Earnings / Revenue Guidance
  - Portfolio Risk
  - Future Star Candidate
- Harte Gates:
  - trusted source
  - affected assets/sectors
  - why it matters
  - trigger
  - invalidation
  - score threshold
  - dedupe/cooldown
  - severity upgrade only
- Quellenqualitaet:
  - Tier 1: Reuters, Bloomberg, WSJ, FT, AP, CNBC, MarketWatch, offizielle Filings
  - Tier 2: grosse Finanzportale mit Link und Publisher
  - Crowd/Social: nur Briefing-Kontext, kein Sofortalert
- Forecast Learning:
  - Jede Top-News-Prognose wird nach 1h, 1d, 5d, 21d gemessen.
  - Trefferquote pro Quelle, Event-Typ, Asset-Klasse und Setup-Art.
  - Schlechte Signaltypen werden heruntergewichtet.

Definition of Done:
- Alert-History zeigt: gesendet, geblockt, Grund, Score, Quelle, Cooldown.
- Jeder Alert beantwortet: Was ist passiert? Warum wichtig? Was bedeutet es? Was bestaetigt? Was widerlegt?

## Phase 3: Best-in-Class Analyzer

Ziel: Jede Aktie, ETF und Crypto muss schnell ein brauchbares Dossier ergeben.

- Universal Resolver: Name, Ticker, ISIN/WKN spaeter, ETF, Crypto, ADR, deutsche Aktien.
- Analyzer-Sections:
  - Kurzurteil
  - Business / Asset Story
  - Umsatz/EPS/Cashflow/Schulden
  - Bewertung relativ zu Wachstum
  - News/Earnings/Guidance
  - Insider/Congress/Public Signals
  - Chart/Volume/Trend
  - Szenarien: Bull/Base/Bear
  - Trigger/Invalidierung
  - Portfolio-Fit
- Keine leeren Panels: Wenn Daten fehlen, klar sagen was fehlt und welche Quelle betroffen ist.
- Compare Mode: Aktie gegen Peers, ETF gegen Alternativen, Crypto gegen BTC/ETH.

Definition of Done:
- `AAPL`, `PFE`, `HOOD`, `RWE.DE`, `BTC-USD`, `VOO`, `URTH` laufen stabil.
- Suchfehler werden gemessen und als QA-Cases ergaenzt.

## Phase 4: Portfolio Brain

Ziel: Kapital halten, Risiken kennen, Chancen priorisieren.

- Portfolio-Ziele:
  - Long-term compound
  - Dividend income
  - Trading sleeve
  - Hedge/liquidity sleeve
- Risk Engine:
  - Konzentration
  - Sektor-/Faktor-Exposure
  - Korrelation
  - Drawdown-Risiko
  - Earnings-Cluster
  - Macro-Exposure
- Rebalancing-Kandidaten:
  - zu gross
  - These gebrochen
  - bessere Alternative
  - Dividende unsicher
  - Risiko steigt ohne Renditekompensation
- Lernsystem:
  - Kaufgrund speichern
  - Ergebnis messen
  - Fehlerkategorien bilden

Definition of Done:
- Portfolio kann nach Redeploy sicher weiter genutzt werden.
- Jede Position hat These, Risiko, Trigger, Invalidierung und Review-Date.

## Phase 5: Future Stars Scanner

Ziel: Kleine Aktien mit grossem Potenzial finden, aber nicht hypen.

- Universum:
  - Small/Mid Caps
  - IPOs
  - High revenue growth
  - Insider buying
  - Large TAM
  - Improving margins
  - Strong news confirmation
- Gates:
  - Umsatzwachstum
  - Cash runway / Verschuldung
  - Bruttomarge / operating leverage
  - Volumen/Relative Strength
  - echte Quelle, nicht Social-Hype
  - klare Risiken
- Ergebnis:
  - `Research Candidate`, nicht Kaufempfehlung
  - Peer-Vergleich
  - Was muss passieren, damit es interessant wird?
  - Was macht die These kaputt?

Definition of Done:
- Keine Future-Star-Meldung ohne Risikoabschnitt.
- Jeder Kandidat bekommt 30/90/180-Tage-Learning.

## Phase 6: World-Class UX

Ziel: Apple-Qualitaet: ruhig, schnell, klar.

- Dashboard:
  - Heute handeln/beobachten/meiden
  - Warum wichtig
  - Portfolio-Folgen
  - Nur danach Deep Dive
- Mobile:
  - Bottom Nav stabil trotz Browserleisten
  - keine abgeschnittenen Karten
  - ein Fokus pro Screen
  - schnelle Suche immer erreichbar
- Dark Mode:
  - keine hellgrauen Kartenfehler
  - Kontrastpruefung fuer Pills, Panels, Charts, Map
- Bot/FAB:
  - nie ueber wichtigen Inhalt legen
  - minimiert beim Scrollen
  - klares Ask-Buddy-Panel statt Stoerelement

Definition of Done:
- QA-Screenshots fuer 390x844, 768x1024, 1366x768, 1920x1080.
- Keine horizontalen Overflows.
- Keine Textueberlaeufe in Buttons/Pills.

## Phase 7: Data & Infrastructure

Ziel: stabil, schnell, nachvollziehbar.

- Data Provider Layer:
  - yfinance / RSS / trusted news / filings / calendar / realtime getrennt kapseln
  - pro Quelle Status, Latenz, Fehlerquote
  - Last-good-cache
- Background Jobs:
  - Morning Brief
  - Alert scan
  - Forecast evaluation
  - Portfolio risk refresh
  - Backup check
- Observability:
  - Health Center mit Jobstatus
  - Alert block reasons
  - provider degradation
  - deploy version/hash
- Backup:
  - SQLite backup
  - Restore runbook
  - data integrity check

Definition of Done:
- Health Center zeigt nicht nur `ok`, sondern was gerade langsam/kaputt/aus Fallback ist.

## Phase 8: Compliance & Trust

Ziel: Beratung ernst nehmen.

- Regulatorischer Arbeitsstrom mit Fachanwalt/Compliance klaeren.
- EU/MiFID-II-orientierte Suitability-Anforderungen beachten, wenn echte Anlageberatung fuer Kunden geleistet wird.
- Bei US-Kontext Investment Adviser/Fiduciary-Duty/Disclosure-Themen beachten.
- Interessenkonflikte erfassen:
  - eigene Positionen
  - Verguetung
  - Affiliate/Referral
  - Datenanbieter
- Client Disclosure:
  - was die App kann
  - was sie nicht kann
  - Datenrisiken
  - keine Erfolgsgarantie
- Advice Archive:
  - jede Empfehlung reproduzierbar
  - jedes Kundenprofil versioniert
  - jede Aenderung nachvollziehbar

Definition of Done:
- Kein Produktivbetrieb als Anlageberater ohne geprueftes Compliance-Modell.

## 90-Tage-Umsetzungsplan

### Woche 1-2: Stabilisieren

- Alert block reasons speichern und im Health Center anzeigen.
- Search QA erweitern fuer weitere deutsche/US/ETF/Crypto-Faelle.
- Portfolio Persistence erneut live pruefen.
- Dashboard Mobile/Desktop QA automatisieren.

### Woche 3-4: Advisory Profile

- Nutzerprofil-Modell bauen.
- Portfolio-Ziele erfassen.
- Suitability Check als API und UI.
- Recommendation-Typen einfuehren.

### Woche 5-6: Analyzer Dossier

- Analyzer neu strukturieren.
- Bull/Base/Bear-Szenarien.
- Trigger/Invalidierung sichtbar.
- ETF/Crypto-spezifische Dossiers.

### Woche 7-8: Forecast Learning

- Top-News-Prognosen sauber speichern.
- Outcome-Auswertung 1h/1d/5d/21d.
- Trefferquote im Dashboard.
- Quellengewichtung automatisch anpassen.

### Woche 9-10: Portfolio Brain

- Risiko-Engine.
- Review-Date und Positions-These.
- Rebalancing-Kandidaten.
- Dividend-Qualitaetscheck.

### Woche 11-12: Future Stars + Release Hardening

- Small-Cap/IPO scanner.
- Quality gates.
- Full release QA.
- Live Monitoring 48h.

## Sofort naechste PRs

1. `Alert Audit Center`: Warum wurde ein Alert gesendet oder geblockt?
2. `Advisory Profile v1`: Ziele, Risiko, Horizont, Erfahrung.
3. `Recommendation Card`: Information/Watch/Setup/Action/Avoid.
4. `Analyzer Dossier v2`: Szenarien, Trigger, Invalidierung, Portfolio-Fit.
5. `Forecast Learning Dashboard`: Was lag richtig, was falsch?
6. `Mobile QA pass`: Bottom Nav, FAB, Header, Dashboard, Analyzer.

## Qualitaetsgate vor jedem Push

```powershell
python -m py_compile api.py src/morning_brief_service.py src/email_alert_service.py
python qa_search_resolution.py
python qa_macro_alert_quality.py
python qa_morning_brief_classification.py
python qa_portfolio_persistence.py
cd frontend
npm audit --audit-level=moderate
npm run build
```

Danach live pruefen:

- `/api/health`
- neues Frontend-Asset aktiv
- Login
- Portfolio speichern
- Analyzer-Suche
- Telegram-Diagnostik
- Dashboard Desktop/Mobile

