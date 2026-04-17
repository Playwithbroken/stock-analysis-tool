## Railway Deploy

Set these environment variables in Railway:

```env
APP_ENV=production
APP_COOKIE_SECURE=true
APP_ACCESS_PASSWORD=your-6-digit-code
APP_SESSION_SECRET=generate-a-long-random-secret
APP_ALLOWED_ORIGINS=https://your-app.up.railway.app
APP_LOGIN_MAX_ATTEMPTS=5
APP_LOGIN_LOCKOUT_MINUTES=15

SIGNAL_ALERTS_ENABLED=true
SMTP_HOST=...
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
SMTP_FROM=...
ALERT_EMAIL_TO=...
SMTP_STARTTLS=true

TELEGRAM_ALERTS_ENABLED=true
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

BRIEF_SCHEDULE_TIMEZONE=Europe/Berlin
EUROPE_OPEN_BRIEF_TIME=08:40
US_OPEN_BRIEF_TIME=15:10
```

Notes:

- Railway starts the backend via `Procfile` / `nixpacks.toml`.
- Frontend assets are built during deploy with `cd frontend && npm run build`.
- Keep `.env` local and do not upload local secrets to git.
- For a private single-user setup, keep the app behind the local access code and use a strong `APP_SESSION_SECRET`.

## Persistente SQLite auf Railway (Volume)

Damit Portfolios, Alerts und Watchlists nach Redeploys erhalten bleiben:

1. In Railway beim Service ein Volume anlegen und nach `/app/data` mounten.
2. Redeploy ausloesen und im Log pruefen, dass die App normal startet.
3. Healthcheck:
   - `GET /api/health` -> `status: ok`
   - Neues Portfolio anlegen, Redeploy ausfuehren, danach `GET /api/portfolios` pruefen.
4. Recovery-Checkliste:
   - Wenn Daten fehlen: Mount-Pfad `/app/data` kontrollieren.
   - Sicherstellen, dass nur ein Service auf dieselbe DB schreibt.
   - Backup der `data/portfolios.db` regelmaessig exportieren.
