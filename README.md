# Broker Freund

Private Beta fuer Aktienanalyse, Portfolio-Tracking, Marktueberblick, Telegram-Briefings und Paper-Trading.

## Produktplan

- [World-Class Product Plan](WORLD_CLASS_PRODUCT_PLAN.md): Roadmap zur professionellen Anlageberater-App mit Advisory Core, Signal Quality Engine, Analyzer Dossier, Portfolio Brain, Future Stars, UX, Infrastruktur und Compliance.

## Beta lokal starten

```powershell
cd frontend
npm install
npm run build
```

Backend lokal:

```powershell
pip install -r requirements.txt
$env:APP_ACCESS_PASSWORD="<your-6-digit-local-code>"
$env:APP_SESSION_SECRET="<your-long-random-local-secret>"
$env:APP_DATA_DIR="$PWD\data"
uvicorn api:app --reload --host 127.0.0.1 --port 8000
```

Frontend lokal:

```powershell
cd frontend
npm run dev
```

Die Web-App laeuft dann unter `http://localhost:3001`.

## Web, PWA und Desktop

- Web: FastAPI liefert die gebaute Vite-App aus.
- PWA: Manifest, Icons und Auto-Update-Service-Worker sind aktiv.
- Desktop: Chrome/Edge koennen die PWA ueber den Install-Button oder das Browser-Menue als App installieren.
- Briefings/Alerts: Versand laeuft in der Beta nur ueber Telegram, nicht per E-Mail oder Browser-Push.

## Paper-Learning-Konto

- Standard-Demo-Kapital: `500000` EUR, nur Paper-Learning, keine automatische Real-Money-Ausfuehrung.
- Standardprofil: `conviction`. Sehr starke Signale erhalten mehr Paper-Risiko; schwächere Lernideen bleiben kleiner. Die Zielauslastung erzwingt keinen Trade.
- Optional steuerbar per Env:
  - `PAPER_CAPITAL_PROFILE=conviction`
  - `PAPER_TRADING_STARTING_CAPITAL=500000`
  - `PAPER_TRADING_CURRENCY=EUR`
  - `PAPER_TRADING_RISK_PER_TRADE_PCT=0.75`
  - `PAPER_TRADING_MAX_OPEN_RISK_PCT=6.0`
  - `PAPER_TRADING_MAX_POSITION_PCT=20.0`
  - `PAPER_TRADING_MAX_GROSS_EXPOSURE_PCT=90.0`
  - `PAPER_TRADING_MIN_CASH_RESERVE_PCT=10.0`
  - `PAPER_TRADING_TARGET_GROSS_EXPOSURE_PCT=75.0`
  - `PAPER_TRADING_MAX_TICKER_EXPOSURE_PCT=25.0`
  - `PAPER_TRADING_SHORT_RISK_MULTIPLIER=0.75`
  - `PAPER_TRADING_MAX_SHORT_POSITION_PCT=12.0`
  - `PAPER_TRADING_MAX_TOTAL_SHORT_EXPOSURE_PCT=30.0`
  - `PAPER_TRADING_SYNTHETIC_CRYPTO_SHORTS_ENABLED=true`
  - `PAPER_TRADING_CRYPTO_SHORT_RISK_MULTIPLIER=0.50`
  - `PAPER_TRADING_MAX_CRYPTO_SHORT_POSITION_PCT=5.0`
  - `PAPER_TRADING_MAX_TOTAL_CRYPTO_SHORT_EXPOSURE_PCT=10.0`
  - `PAPER_TRADING_CRYPTO_SHORT_FUNDING_BPS_PER_DAY=5.0`
  - `PAPER_TRADING_HIGH_CONVICTION_MIN_SCORE=90`
  - `PAPER_TRADING_MEDIUM_CONVICTION_MIN_SCORE=80`
  - `PAPER_TRADING_MAX_OPTION_PREMIUM_PCT=0.75`
  - `PAPER_TRADING_MAX_OPEN_OPTION_PREMIUM_PCT=2.0`
  - `PAPER_TRADING_RISK_PER_OPTION_TRADE_PCT=0.25`
  - `PAPER_TRADING_MAX_OPEN_TRADES=16`
  - `PAPER_TRADING_DAILY_LOSS_LIMIT_PCT=1.5`
  - `PAPER_TRADING_MAX_DRAWDOWN_PCT=12.0`
  - `PAPER_TRADING_MAX_CONSECUTIVE_LOSSES=3`
  - `PAPER_TRADING_LOSS_STREAK_COOLDOWN_HOURS=24`
  - `PAPER_TRADING_AUTO_MIN_SCORE=88`
  - `PAPER_TRADING_EXPLORATION_MIN_SCORE=60`
  - `PAPER_TRADING_NEWS_CONTEXT_MAX_AGE_SECONDS=3600`
  - `PAPER_MARKET_DATA_MAX_AGE_HOURS=96`
  - `PAPER_MIN_AVG_DOLLAR_VOLUME=2000000`
  - `PAPER_EXECUTION_EQUITY_BPS=8`
  - `PAPER_EXECUTION_ETF_BPS=6`
  - `PAPER_EXECUTION_CRYPTO_BPS=18`

## Alpaca Broker-Paper-Abgleich

- Der Broker-Paper-Pfad akzeptiert ausschließlich `https://paper-api.alpaca.markets`.
- Alle 30 Sekunden werden Paper-Account, Orders und Positionen abgeglichen.
- Ein fehlender, veralteter oder fehlerhafter Abgleich blockiert neue Broker-Paper-Orders.
- Differenzen werden als Incident gespeichert; die echte Account-ID wird nur als SHA-256-Hash abgelegt.
- Manueller Abgleich: `POST /api/trading/broker-paper/reconcile`.
- Status: `GET /api/trading/broker-paper/status`.
- Paper-Shorts prüfen vor dem Senden `shortable`, `marginable` und den aktuellen `borrow_status` über Alpaca.
- Nur Easy-to-Borrow-Aktien/ETFs und ganze Stückzahlen dürfen neue Broker-Short-Positionen eröffnen. Hard-to-Borrow und Broker-Krypto-Shorts bleiben blockiert.
- Eine einzelne Short-Position ist auf 12 %, das gesamte Short-Exposure auf 30 % des Paper-Kontos begrenzt.
- Krypto kann ausschließlich lokal und synthetisch geshortet werden: maximal 5 % je Position, 10 % insgesamt, halbes Risikobudget und konfigurierbare tägliche Funding-Kosten inklusive Wochenende.
  - `PAPER_EXECUTION_OPTION_BPS=125`
- News-basierte Demo-Trades entstehen nur aus frischen, wichtigen Tier-1-Meldungen mit expliziter Ticker-Zuordnung und richtungskonformer relativer Preisbestätigung im Veröffentlichungsfenster.
- Quelle, Faktenbasis, Primärdokumentstatus und Marktreaktion werden im Paper-Trade-Ticket gespeichert; die Messung ist kein Kausalitätsbeweis und schaltet niemals Echtgeld-Ausführung frei.
- Vor jedem Paper-Einstieg werden Kurszeitpunkt, Datenalter und durchschnittliches Handelsnotional erneut geprueft. Veraltete oder sehr duenne Daten blockieren den Entry.
- Angeforderte Mengen werden am aktuellen Demo-Risikolimit hart begrenzt; Calls und Puts bleiben Paper-only und pruefen beim Einstieg erneut das Underlying.
- Entry, laufende Bewertung und Exit verwenden konservative Fill-Kosten. Referenzkurs, simulierter Ausfuehrungskurs und Kosten bleiben im Trade-Ticket und in Telegram sichtbar.
- Vor jedem Auto-Entry werden freies Cash, Gesamt-Exposure, kumulierte Ticker-Exposure und die gesamte offene Optionspraemie neu geprueft.
- Tagesverlust und Verlustserien koennen neue Paper-Entries temporaer pausieren. Ab dem Drawdown-Limit reduziert das System neue Demo-Risiken auf 25 Prozent.

### Learning Engine v2

- Jeder neue Paper-Trade speichert einen gehashten, nach dem Einstieg unveraenderlichen Feature-Snapshot mit Plan, Score, Quellen-, Markt-, Regime-, Liquiditaets-, Ausfuehrungs- und Portfoliokontext.
- Geschlossene Trades werden getrennt nach `Outcome Quality` und `Process Quality` bewertet. Gewinn ist nicht automatisch ein guter Prozess; Verlust ist nicht automatisch ein schlechter Prozess.
- Die Attribution misst Netto-P&L, R-Multiple, MFE/MAE, Kosten und wiederkehrende Fehlerkategorien, soweit echte Daten vorliegen.
- Segmentauswertungen zeigen Stichprobe, Trefferquote und Wilson-Unsicherheitsintervall nach Setup und Assetklasse.
- Erst ab acht entscheidenden Beobachtungen darf eine negative Lernhypothese entstehen. Sie startet ausschliesslich als zukuenftige Shadow-Regel.
- Eine Paper-Regel kann erst nach mindestens 30 zukuenftigen entscheidenden Checks und 30 geschlossenen Trades, Profit Factor `>= 1.20`, positiver Erwartung und bestandenem Drawdown-Gate manuell geprueft werden.
- Lernregeln duerfen Paper-Scores oder Paper-Risikomultiplikatoren reduzieren, aber niemals harte Konto-Risikogrenzen lockern oder Echtgeld-/Automatik-Ausfuehrung aktivieren.
- Dashboard/API: `GET /api/trading/paper-learning-v2`; manuelle Neuberechnung: `POST /api/trading/paper-learning-v2/refresh`.
- Der vollstaendige fachliche Implementierungsrahmen steht in [PAPER_LEARNING_ENGINE_V2_PROMPT.md](PAPER_LEARNING_ENGINE_V2_PROMPT.md).

## Daten und Backups

- Die SQLite-Datenbank liegt standardmaessig unter `data/portfolios.db`.
- In Railway muss ein Volume nach `/app/data` gemountet und `APP_DATA_DIR=/app/data` gesetzt werden.
- Das Health Center bietet `DB Backup` fuer einen geschuetzten Download der SQLite-Datei.
- Restore: Backup als `portfolios.db` in den Datenordner legen, Service neu starten, `/api/health` und Portfolio-Liste pruefen.

## Scalable Capital Read-only-Sync

Broker Freund verwendet ausschliesslich die offizielle Scalable CLI. Login, OAuth-Token und
2FA bleiben bei der CLI; die App akzeptiert keine Broker-Zugangsdaten und stellt keine
Handelsbefehle bereit.

1. In Scalable im Web unter `Profil > Sicherheit > Agentic Investing` den CLI-Zugriff aktivieren.
2. Die offizielle Linux-CLI aus den Scalable-Releases installieren und Signatur sowie SHA-256
   nach der offiziellen Anleitung verifizieren.
3. Auf demselben Host wie Broker Freund persoenlich `sc login --local-read-only` ausfuehren.
4. Den CLI-Konfigurationsordner auf einem geschuetzten persistenten Volume halten und
   `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_STATE_HOME` und `XDG_CACHE_HOME` darauf setzen.
5. `SCALABLE_CLI_SHA256` auf den Hash der geprueften Binary pinnen und erst danach
   `SCALABLE_INTEGRATION_ENABLED=true` setzen.

Der Sync liest nur `broker holdings` und `broker overview`. Vor einer atomaren Uebernahme
werden Konto-/Portfoliokontext, ISIN-Eindeutigkeit, Tickerzuordnung und die Summe der
Brokerbewertungen geprueft. Bei einem Fehler bleibt der letzte gueltige Snapshot aktiv.
Das erzeugte Portfolio `Scalable Capital (Read-only)` kann in der App nicht manuell
veraendert oder geloescht werden.

Optional aktualisiert `SCALABLE_AUTO_SYNC_ENABLED=true` den geprüften Snapshot im
Hintergrund. Das Intervall beträgt standardmäßig 15 Minuten, verwendet gespeicherte
ISIN-Ticker-Zuordnungen und übernimmt bei Fehlern keinen unvollständigen Stand.

Mit `SCALABLE_TELEGRAM_DECISIONS_ENABLED=true` folgt nach jedem erfolgreichen Sync ein
geänderter, deduplizierter Telegram-Depotcheck. Er zeigt je Position `HALTEN`,
`DATEN PRÜFEN`, `AUFSTOCKEN PRÜFEN`, `REDUZIEREN PRÜFEN` oder `VERKAUFEN PRÜFEN` und
höchstens drei neue strikte Paper-Ideen samt Trigger, Invalidierung und Paper-Risiko.
Ein negativer Depotgewinn allein erzeugt niemals ein Verkaufssignal. Veraltete Kurse
sperren Kauf und Verkauf. Die Integration bleibt read-only und führt keine Order aus.
Ein bestätigter Freitagsschlusskurs wird am Wochenende als `MARKT GESCHLOSSEN`
statt als technischer Datenfehler ausgewiesen; Krypto ist davon ausgenommen.
Empfehlung und Ausführbarkeit sind getrennt: Die Empfehlung stammt aus dem Signal-
und Paper-Lernsystem. Der Scalable-Kurs steuert nur, ob sie jetzt prüfbar ist.

Nach jedem erfolgreichen Depotabgleich werden außerdem echte Broker-Kurse, ein
begrenzter rotierender News-Block und die jüngsten Transaktionen read-only
abgerufen. Provider-Transaktions-IDs werden vor dem Speichern gehasht. Ein
Teilfehler dieser optionalen Kontextdaten überschreibt den gültigen Depotstand
nicht. Kauf-, Verkaufs- und Order-Befehle bleiben gesperrt.

Geschuetzte Endpunkte:

- `GET /api/integrations/scalable/status`
- `GET /api/integrations/scalable/snapshot`
- `GET /api/integrations/scalable/market-context`
- `GET /api/integrations/scalable/decisions?fresh=true`
- `POST /api/integrations/scalable/sync`
- `POST /api/integrations/scalable/market-context/refresh`
- `POST /api/integrations/scalable/decisions/send`

## Beta-Gate

```powershell
python -m py_compile api.py
python qa_auth_lockout.py
python qa_auth_cookie_security.py
python qa_backup_endpoint.py
python qa_health_center_contract.py
python qa_global_asset_api.py
python qa_morning_brief_availability.py
python qa_brief_scheduler_delivery.py
python qa_portfolio_persistence.py
python qa_portfolio_api_persistence.py
python qa_scalable_readonly.py
python qa_telegram_only_notifications.py
python qa_macro_alerts.py
python qa_macro_alert_quality.py
python qa_paper_demo_account.py
python qa_paper_learning_alerts.py
python qa_paper_learning_v2.py
python qa_option_contract_alerts.py
python qa_leverage_end_to_end.py
python qa_news_evidence_schema.py
python qa_news_trade_entry_gate.py
python qa_news_source_revalidation.py
python qa_telegram_deduplication.py
python qa_static_cache_headers.py
python qa_security_headers.py
cd frontend
npm run verify
```

Vor dem Live-Go:

```powershell
python qa_search_resolution.py
python qa_auth_lockout.py
python qa_auth_cookie_security.py
python qa_backup_endpoint.py
python qa_health_center_contract.py
python qa_global_asset_api.py
python qa_morning_brief_availability.py
python qa_brief_scheduler_delivery.py
python qa_portfolio_persistence.py
python qa_portfolio_api_persistence.py
python qa_scalable_readonly.py
python qa_telegram_only_notifications.py
python qa_macro_alerts.py
python qa_macro_alert_quality.py
python qa_paper_demo_account.py
python qa_paper_learning_alerts.py
python qa_option_contract_alerts.py
python qa_leverage_end_to_end.py
python qa_news_evidence_schema.py
python qa_news_trade_entry_gate.py
python qa_news_source_revalidation.py
python qa_telegram_deduplication.py
python qa_static_cache_headers.py
python qa_security_headers.py
python qa_live_release_smoke.py
cd frontend
npm run qa:release
```

Die Screenshots und das Ergebnis liegen danach in `frontend/qa-artifacts/<run-id>`.
