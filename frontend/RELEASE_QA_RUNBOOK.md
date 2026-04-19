# Release QA Runbook (Go/No-Go)

Stand: 19. April 2026  
Ziel: deterministische Abnahme vor Montag-Release.

## 1) Voraussetzungen

- Backend und Frontend laufen auf dem Zielsystem (Railway oder Preview).
- Gültiger Workspace-Code vorhanden (`QA_ACCESS_CODE`).
- Playwright installiert (`npm install` im `frontend`-Ordner).

## 2) Automatisierter Gate-Run

Ausführen:

```powershell
cd frontend
npm run qa:release
```

Optional mit Overrides:

```powershell
$env:QA_TARGET_URL="https://web-production-8546b.up.railway.app/"
$env:QA_ACCESS_CODE="100363"
$env:QA_TICKERS="AAPL,PFE,BTC-USD"
$env:QA_MARKETS_STRESS_COUNT="20"
npm run qa:release
```

Artefakte:

- `frontend/qa-artifacts/<run-id>/summary.json`
- `frontend/qa-artifacts/<run-id>/*.png`

## 3) Was der Runner prüft

- Viewports: `1366x768`, `1536x960`, `1920x1080`
- Navigation: `Analyzer`, `Markets`, `Portfolio`, `Dashboard`
- Markets-Stresstest: `20x` Klick auf `Markets`, dabei kein unerwarteter Sprung nach Analyze
- Analyzer-Ticker-Flow: `AAPL`, `PFE`, `BTC-USD`
- Chart hängt nicht im Ladezustand
- HTTP-/Request-Fehler-Telemetrie:
  - `http404`
  - `http5xx`
  - `requestFailedNonAborted`
  - `requestFailedAborted` (nur Info, oft durch Navigationsabbrüche)

## 4) Go/No-Go Regeln

`GO`, wenn alle Punkte erfüllt sind:

1. `metrics.marketsUnexpectedAnalyze === 0`
2. `metrics.http404 === 0`
3. `metrics.http5xx === 0`
4. `metrics.requestFailedNonAborted === 0`
5. `metrics.chartStillLoading === 0`
6. `issues` enthält keine `ui`/`ux`/`pageerror`-Einträge

`NO-GO`, wenn eines davon verletzt ist.

## 5) Manuelle Zusatzchecks (10 Minuten)

1. In jedem Viewport prüfen:
   - kein dominanter Leerraum im Hauptcontent
   - Map und rechte Panels nutzen Breite sichtbar sinnvoll
2. Dashboard:
   - Morning Brief zeigt entweder Top-Setups oder klar `insufficient signal`
3. Markets:
   - kein automatischer Jump nach Analyze nur durch Tabwechsel
4. Analyzer:
   - Kursverlauf für `AAPL`, `PFE`, `BTC-USD` sichtbar (live/stale/fallback akzeptiert)

## 6) Freigabeprotokoll (Kurzformat)

In der Release-Notiz festhalten:

- `Run ID`
- Ergebnis `GO` oder `NO-GO`
- Auffälligkeiten (falls vorhanden)
- Verantwortlicher + Zeitpunkt

