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
$env:APP_ACCESS_PASSWORD="100363"
$env:APP_SESSION_SECRET="change-me-local-secret"
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
  - `PAPER_TRADING_MAX_OPTION_PREMIUM_PCT=0.75`
  - `PAPER_TRADING_RISK_PER_OPTION_TRADE_PCT=0.25`
  - `PAPER_TRADING_MAX_OPEN_TRADES=12`

## Daten und Backups

- Die SQLite-Datenbank liegt standardmaessig unter `data/portfolios.db`.
- In Railway muss ein Volume nach `/app/data` gemountet und `APP_DATA_DIR=/app/data` gesetzt werden.
- Das Health Center bietet `DB Backup` fuer einen geschuetzten Download der SQLite-Datei.
- Restore: Backup als `portfolios.db` in den Datenordner legen, Service neu starten, `/api/health` und Portfolio-Liste pruefen.

## Beta-Gate

```powershell
python -m py_compile api.py
cd frontend
npm run verify
```

Vor dem Live-Go:

```powershell
python qa_search_resolution.py
cd frontend
npm run qa:release
```

Die Screenshots und das Ergebnis liegen danach in `frontend/qa-artifacts/<run-id>`.
