## Railway Deploy

Set these environment variables in Railway:

```env
APP_ENV=production
APP_COOKIE_SECURE=true
APP_ACCESS_PASSWORD=<strong-private-access-code>
APP_SESSION_SECRET=<long-random-session-secret>
APP_ALLOWED_ORIGINS=https://your-app.up.railway.app
APP_LOGIN_MAX_ATTEMPTS=5
APP_LOGIN_LOCKOUT_MINUTES=15
APP_DATA_DIR=/app/data

SIGNAL_ALERTS_ENABLED=true

TELEGRAM_ALERTS_ENABLED=true
TELEGRAM_BOT_TOKEN=<telegram-bot-token>
TELEGRAM_CHAT_ID=<telegram-chat-id>

BRIEF_SCHEDULE_TIMEZONE=Europe/Berlin
EUROPE_OPEN_BRIEF_TIME=08:40
US_OPEN_BRIEF_TIME=15:10
```

Notes:

- Railway starts the backend via `Procfile` / `nixpacks.toml`.
- Frontend assets are built during deploy with `cd frontend && npm run build`.
- Keep `.env` local and do not upload local secrets to git.
- For a private single-user setup, keep the app behind the local access code and use a strong `APP_SESSION_SECRET`.
- Briefings und Alerts laufen in dieser Beta nur ueber Telegram. SMTP/E-Mail und Browser-Push fuer Briefings bleiben aus.

## Persistente SQLite auf Railway (Volume)

Damit Portfolios, Alerts und Watchlists nach Redeploys erhalten bleiben:

1. In Railway beim Service ein Volume anlegen und nach `/app/data` mounten.
2. Das Volume muss am Web-Service `web-production-8546b` haengen, nicht an einem separaten Worker oder Environment.
3. Redeploy ausloesen und im Log pruefen, dass die App normal startet.
4. Healthcheck:
   - `GET /api/health` -> `status: ok` und `persistence.ready: true`
   - Im Health Center muessen Volume-Name, Mount `/app/data` und `Volume aktiv` erscheinen.
   - Neues Portfolio anlegen, Redeploy ausfuehren, danach `GET /api/portfolios` pruefen.
   - Im Health Center `DB Backup` klicken und pruefen, dass eine `.db`-Datei heruntergeladen wird.
5. Redeploy-Beweis:
   - DB-ID im Health Center notieren.
   - Testportfolio anlegen und erneut deployen.
   - Go nur, wenn DB-ID und Testportfolio unveraendert erhalten bleiben.
6. Recovery-Checkliste:
   - Wenn Daten fehlen: Mount-Pfad `/app/data` kontrollieren.
   - Sicherstellen, dass nur ein Service auf dieselbe DB schreibt.
   - Backup der `data/portfolios.db` regelmaessig exportieren.

## Restore aus Backup

1. Railway Service stoppen oder kurzfristig auf Maintenance setzen.
2. Backup-Datei als `/app/data/portfolios.db` in das Volume legen.
3. Service neu starten.
4. `GET /api/health` pruefen und im Health Center den SQLite-Quick-Check kontrollieren.
5. Portfolio-Liste oeffnen und ein bekanntes Portfolio gegenpruefen.
