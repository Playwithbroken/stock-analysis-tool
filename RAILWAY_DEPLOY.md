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
APP_DAILY_BACKUP_ENABLED=true
APP_BACKUP_DIR=/app/data/backups
APP_BACKUP_INTERVAL_HOURS=24
APP_BACKUP_RETENTION_COUNT=14
APP_RESTORE_TEST_INTERVAL_DAYS=7
OPERATIONAL_ALERTS_ENABLED=true

# Optional Scalable Capital read-only integration. Enable only after the official
# CLI binary was verified, installed and personally logged in with --local-read-only.
SCALABLE_INTEGRATION_ENABLED=false
SCALABLE_AUTO_SYNC_ENABLED=true
SCALABLE_AUTO_SYNC_INTERVAL_MINUTES=15
SCALABLE_AUTO_SYNC_START_DELAY_SECONDS=60
SCALABLE_CLI_PATH=/app/data/scalable-cli/bin/sc
SCALABLE_CLI_SHA256=<sha256-of-verified-official-binary>
XDG_CONFIG_HOME=/app/data/scalable-cli/xdg/config
XDG_DATA_HOME=/app/data/scalable-cli/xdg/data
XDG_STATE_HOME=/app/data/scalable-cli/xdg/state
XDG_CACHE_HOME=/app/data/scalable-cli/xdg/cache
SCALABLE_RECONCILIATION_TOLERANCE_EUR=0.05

SIGNAL_ALERTS_ENABLED=true

TELEGRAM_ALERTS_ENABLED=true
TELEGRAM_BOT_TOKEN=<telegram-bot-token>
TELEGRAM_CHAT_ID=<telegram-chat-id>

# Optional read-only realtime US options data (no order endpoint is used).
TRADIER_ACCESS_TOKEN=<tradier-production-market-data-token>
TRADIER_ENVIRONMENT=production

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
- `TRADIER_ENVIRONMENT=production` nutzt bei einem berechtigten Brokerage-Konto Echtzeit-Optionsmarktdaten; `sandbox` ist verzoegert. Broker Freund greift nur lesend auf Marktdaten zu, sendet keine Orders und garantiert keinen Fill.
- Die Scalable CLI muss im laufenden Linux-Service aus den offiziellen Releases installiert und vor dem Login verifiziert werden. OAuth-Login immer persoenlich mit `sc login --local-read-only`; die `XDG_*_HOME`-Verzeichnisse muessen auf dem geschuetzten persistenten Volume liegen. Erst nach einem erfolgreichen `sc whoami` und gesetztem Binary-Hash `SCALABLE_INTEGRATION_ENABLED=true` aktivieren.

## Persistente SQLite auf Railway (Volume)

Damit Portfolios, Alerts und Watchlists nach Redeploys erhalten bleiben:

1. In Railway beim Service ein Volume anlegen und nach `/app/data` mounten.
2. Das Volume muss am Web-Service `web-production-8546b` haengen, nicht an einem separaten Worker oder Environment.
3. Redeploy ausloesen und im Log pruefen, dass die App normal startet.
4. Healthcheck:
   - `GET /api/health` -> `status: ok` und `persistence.ready: true`
   - Im Health Center muessen Volume-Name, Mount `/app/data` und `Volume aktiv` erscheinen.
   - Neues Portfolio anlegen, Redeploy ausfuehren, danach `GET /api/portfolios` pruefen.
   - Im Health Center `DB Backup` klicken und pruefen, dass eine konsistente `.db`-Datei heruntergeladen wird.
   - `Restore testen` ausfuehren. Der Drill kopiert das Backup nur in eine temporaere leere Datenbank und veraendert die Live-DB nicht.
5. Redeploy-Beweis:
   - DB-ID im Health Center notieren.
   - Testportfolio anlegen und erneut deployen.
   - Go nur, wenn DB-ID und Testportfolio unveraendert erhalten bleiben.
6. Recovery-Checkliste:
   - Wenn Daten fehlen: Mount-Pfad `/app/data` kontrollieren.
   - Sicherstellen, dass nur ein Service auf dieselbe DB schreibt.
   - Automatische Sicherungen unter `/app/data/backups` und den letzten Restore-Test im Health Center pruefen.

## Restore aus Backup

Der automatische Restore-Test ist nicht-destruktiv. Eine echte Wiederherstellung der Live-Datenbank bleibt bewusst ein manueller Wartungsvorgang:

1. Railway Service stoppen oder kurzfristig auf Maintenance setzen.
2. Backup-Datei als `/app/data/portfolios.db` in das Volume legen.
3. Service neu starten.
4. `GET /api/health` pruefen und im Health Center den SQLite-Quick-Check kontrollieren.
5. Portfolio-Liste oeffnen und ein bekanntes Portfolio gegenpruefen.
