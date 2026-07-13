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
python ..\qa_auth_cookie_security.py
python ..\qa_auth_lockout.py
python ..\qa_backup_endpoint.py
python ..\qa_health_center_contract.py
python ..\qa_global_asset_api.py
python ..\qa_morning_brief_availability.py
python ..\qa_brief_scheduler_delivery.py
python ..\qa_portfolio_persistence.py
python ..\qa_portfolio_api_persistence.py
python ..\qa_telegram_only_notifications.py
python ..\qa_macro_alerts.py
python ..\qa_macro_alert_quality.py
python ..\qa_paper_demo_account.py
python ..\qa_paper_learning_alerts.py
python ..\qa_static_cache_headers.py
python ..\qa_security_headers.py
cd frontend
npm run qa:release
```

Optional mit Overrides:

```powershell
$env:QA_TARGET_URL="https://web-production-8546b.up.railway.app/"
$env:QA_ACCESS_CODE="<current-qa-access-code>"
$env:QA_TICKERS="AAPL,PFE,BTC-USD"
$env:QA_MARKETS_STRESS_COUNT="20"
npm run qa:release
```

Nach Railway-Deploy:

```powershell
$env:QA_TARGET_URL="https://web-production-8546b.up.railway.app"
python ..\qa_live_release_smoke.py
```

Der Live-Smoke vergleicht standardmaessig die Live-Asset-Hashes mit `frontend/dist/index.html`.
Nur fuer externe Checks ohne lokales Dist-Artefakt: `QA_SKIP_LOCAL_ASSET_MATCH=1`.

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
7. Auth-Gates sind grün: Cookie-Sicherheit und Login-Lockout
8. Health Center ist geschützt und liefert den Betriebsvertrag für App, DB, Schedule, Telegram und Feeds
9. Suche und Analyzer lösen Aktien, ETFs und Krypto auch bei Provider-Ausfällen stabil auf
10. Morning Brief liefert bei Cache-, Provider- und Service-Ausfällen einen lesbaren Partial-Status statt `500`
11. Scheduler sendet fällige Rich-Briefings genau einmal und speichert Erfolg oder Fehler für das Health Center
12. Notification-Gate ist grün: Telegram aktiv, E-Mail und Browser-Push für diese Beta aus
13. Macro-Alert-Gates sind grün: Qualität, Einordnung, Dedupe und Severity-Upgrade
14. Paper-Trading-Gates sind grün: Demo-Kapital, Geldfluss, Learning und Telegram-Status
15. Portfolio-Gates sind grün: API-Speichern, Holdings und SQLite-Restart-Persistenz

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

5. PWA / Desktop:
   - `/manifest.json`, `/sw.js`, `/registerSW.js`, `/icons/icon-192.png` liefern HTTP 200
   - Browser registriert `/sw.js` als einzigen Root-Scope-Service-Worker
   - Install-Button zeigt Install-Dialog oder klare Installationshilfe
6. Private Daten:
   - Health Center zeigt App-Version, SQLite-Status `ok` und einen aktiven `DB Backup`-Button
   - Backup-Download liefert eine `.db`-Datei
   - Portfolio-Tab zeigt klar, falls nur lokale Browser-Sicherung genutzt wird

## 6) Freigabeprotokoll (Kurzformat)

In der Release-Notiz festhalten:

- `Run ID`
- Ergebnis `GO` oder `NO-GO`
- Auffälligkeiten (falls vorhanden)
- Verantwortlicher + Zeitpunkt
