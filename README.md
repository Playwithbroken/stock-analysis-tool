# Broker Freund

Private Beta fuer Aktienanalyse, Portfolio-Tracking, Marktueberblick, Telegram-Briefings und Paper-Trading.

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

## Daten und Backups

- Die SQLite-Datenbank liegt standardmaessig unter `data/portfolios.db`.
- In Railway muss ein Volume nach `/app/data` gemountet und `APP_DATA_DIR=/app/data` gesetzt werden.
- Das Health Center bietet `DB Backup` fuer einen geschuetzten Download der SQLite-Datei.
- Restore: Backup als `portfolios.db` in den Datenordner legen, Service neu starten, `/api/health` und Portfolio-Liste pruefen.

## Beta-Gate

```powershell
python qa_search_resolution.py
cd frontend
npm run qa:release
```

Die Screenshots und das Ergebnis liegen danach in `frontend/qa-artifacts/<run-id>`.
