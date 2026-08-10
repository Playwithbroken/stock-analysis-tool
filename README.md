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
- Optional steuerbar per Env:
  - `PAPER_TRADING_STARTING_CAPITAL=500000`
  - `PAPER_TRADING_CURRENCY=EUR`
  - `PAPER_TRADING_RISK_PER_TRADE_PCT=0.35`
  - `PAPER_TRADING_MAX_OPEN_RISK_PCT=3.0`
  - `PAPER_TRADING_MAX_POSITION_PCT=10.0`
  - `PAPER_TRADING_MAX_GROSS_EXPOSURE_PCT=60.0`
  - `PAPER_TRADING_MAX_TICKER_EXPOSURE_PCT=12.0`
  - `PAPER_TRADING_MAX_OPTION_PREMIUM_PCT=0.75`
  - `PAPER_TRADING_MAX_OPEN_OPTION_PREMIUM_PCT=2.0`
  - `PAPER_TRADING_RISK_PER_OPTION_TRADE_PCT=0.25`
  - `PAPER_TRADING_MAX_OPEN_TRADES=12`
  - `PAPER_TRADING_DAILY_LOSS_LIMIT_PCT=1.0`
  - `PAPER_TRADING_MAX_DRAWDOWN_PCT=8.0`
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
  - `PAPER_EXECUTION_OPTION_BPS=125`
- News-basierte Demo-Trades entstehen nur aus frischen, wichtigen Tier-1-Meldungen mit expliziter Ticker-Zuordnung und richtungskonformer relativer Preisbestätigung im Veröffentlichungsfenster.
- Quelle, Faktenbasis, Primärdokumentstatus und Marktreaktion werden im Paper-Trade-Ticket gespeichert; die Messung ist kein Kausalitätsbeweis und schaltet niemals Echtgeld-Ausführung frei.
- Vor jedem Paper-Einstieg werden Kurszeitpunkt, Datenalter und durchschnittliches Handelsnotional erneut geprueft. Veraltete oder sehr duenne Daten blockieren den Entry.
- Angeforderte Mengen werden am aktuellen Demo-Risikolimit hart begrenzt; Calls und Puts bleiben Paper-only und pruefen beim Einstieg erneut das Underlying.
- Entry, laufende Bewertung und Exit verwenden konservative Fill-Kosten. Referenzkurs, simulierter Ausfuehrungskurs und Kosten bleiben im Trade-Ticket und in Telegram sichtbar.
- Vor jedem Auto-Entry werden freies Cash, Gesamt-Exposure, kumulierte Ticker-Exposure und die gesamte offene Optionspraemie neu geprueft.
- Tagesverlust und Verlustserien koennen neue Paper-Entries temporaer pausieren. Ab dem Drawdown-Limit reduziert das System neue Demo-Risiken auf 25 Prozent.

## Daten und Backups

- Die SQLite-Datenbank liegt standardmaessig unter `data/portfolios.db`.
- In Railway muss ein Volume nach `/app/data` gemountet und `APP_DATA_DIR=/app/data` gesetzt werden.
- Das Health Center bietet `DB Backup` fuer einen geschuetzten Download der SQLite-Datei.
- Restore: Backup als `portfolios.db` in den Datenordner legen, Service neu starten, `/api/health` und Portfolio-Liste pruefen.

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
python qa_telegram_only_notifications.py
python qa_macro_alerts.py
python qa_macro_alert_quality.py
python qa_paper_demo_account.py
python qa_paper_learning_alerts.py
python qa_option_contract_alerts.py
python qa_news_evidence_schema.py
python qa_news_source_revalidation.py
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
python qa_telegram_only_notifications.py
python qa_macro_alerts.py
python qa_macro_alert_quality.py
python qa_paper_demo_account.py
python qa_paper_learning_alerts.py
python qa_option_contract_alerts.py
python qa_news_evidence_schema.py
python qa_news_source_revalidation.py
python qa_static_cache_headers.py
python qa_security_headers.py
python qa_live_release_smoke.py
cd frontend
npm run qa:release
```

Die Screenshots und das Ergebnis liegen danach in `frontend/qa-artifacts/<run-id>`.
