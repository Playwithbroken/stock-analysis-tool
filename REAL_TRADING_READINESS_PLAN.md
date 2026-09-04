# Real-Trading-Readiness-Plan

Stand: 27. August 2026, Europe/Berlin

Der konkrete technische Einbau mit Modulstruktur, Datenverträgen, Latenzbudgets, MCP-Rolle und Abnahmetests ist in `REALTIME_MARKET_INTEGRATION_PLAN.md` beschrieben. Dieses Dokument bleibt die übergeordnete Freigabe- und Risikocheckliste.

## Ehrlicher Ist-Zustand

| Bereich | Befund | Status |
|---|---|---|
| Live-News | Der Live-Test lieferte 16 unterschiedliche Meldungen aus 6 Publishern. Alle 16 Titel waren eindeutig; die geprüften Links waren erreichbar. Quellen waren unter anderem CNBC, MarketWatch, Federal Reserve und BEA. | Funktioniert, aber überwiegend RSS/yfinance und nicht als lizenzierter Low-Latency-Feed |
| Paper-Trades | Vier lokale Paper-Trades wurden mit Marktpreisen geführt und am 27.08.2026 wegen abgelaufener Haltedauer geschlossen. Fills und Orders wurden lokal simuliert und nicht an einen Broker-Paper-Account gesendet. | Echte Marktbeobachtung, aber kein echter Broker-Simulator |
| Newsbezug der Trades | Die vier vorhandenen Trades enthalten keinen gespeicherten News-Titel, keine Source-URL und keinen belastbaren `data_as_of`-Wert im Ticket. | Nicht ausreichend für News-Lernen |
| Lernsystem | 4 geschlossene Trades, 4 Attributionen, 6 protokollierte Lernläufe, 0 Hypothesen und 0 Regeln. | Technisch aktiv, statistisch noch nicht nutzbar |
| Telegram | Bot-Token und Chat-ID sind gesetzt. Der offizielle `getMe`-Test antwortet jedoch mit HTTP 401 `Unauthorized`. Der letzte dokumentierte Briefversand stammt vom 15.04.2026; Briefjobs vom 24.07.2026 scheiterten ebenfalls mit 401. | Aktuell defekt |
| Deduplizierung | Persistente Event-Keys, semantische News-Deduplizierung und Cross-Channel-Deduplizierung sind implementiert und durch QA abgedeckt. | Code-seitig vorhanden, live wegen Telegram-Fehler nicht end-to-end bewiesen |
| Kursdaten | Hauptquelle ist yfinance/Yahoo mit Best-Effort-Intraday- und Tagesdaten sowie konservativer Fill-Simulation. | Für Forschung/Paper brauchbar, nicht als alleinige produktive Trading-Quelle |
| Echtgeld | Keine automatische Echtgeldausführung. | Muss bis zum Abschluss aller Gates gesperrt bleiben |

## Zielarchitektur

```text
Lizenzierte News + Broker-Marktdaten
             ↓
normalisierte, unveränderliche Evidenz
             ↓
Signal-Gates → Broker-Paper-Order → echte Paper-Fills
             ↓                         ↓
        Telegram-Ereignis       Reconciliation
             ↓                         ↓
      Outcome + Journal + Benchmark + Kosten
                         ↓
              Shadow-Lernen und Kill-Switch
```

## Phase 0 – Betrieb wiederherstellen

Priorität: sofort

1. Telegram-Token über BotFather neu erzeugen und nur als Secret hinterlegen.
2. `getMe`, Chat-ID und eine einzelne Testnachricht prüfen.
3. Erst nach erfolgreicher Zustellung den Event-Key persistieren.
4. Scheduler-Heartbeat und letzten erfolgreichen Lauf im Health Center anzeigen.
5. Alarm auslösen, wenn Telegram, News, Kurse, Outcome-Prüfung oder Lernlauf länger als den erlaubten Zeitraum ausbleiben.
6. Keine wiederholten Standardnachrichten senden: Ohne neues Ereignis wird nichts gesendet oder nur ein klar gekennzeichneter täglicher Status-Digest.

Abnahme:

- Telegram `getMe` = 200/`ok:true`.
- Testnachricht kommt im richtigen Chat an.
- Zweiter identischer Versand wird dedupliziert.
- Drei planmäßige Jobs laufen an drei aufeinanderfolgenden Tagen ohne Fehler.

## Phase 1 – Nachweisbare News-Evidenz pro Trade

Priorität: sehr hoch

Jeder News-basierte Kandidat benötigt vor dem Paper-Entry:

- Provider- und Artikel-ID,
- Original-Publisher und kanonische URL,
- `published_at`, `first_seen_at`, `fetched_at` und Datenalter,
- Titel- und Inhalts-Hash,
- betroffene Instrumente mit Begründung der Zuordnung,
- mindestens eine Primärquelle oder zwei unabhängige belastbare Sekundärquellen bei High-Impact-News,
- Status für Korrektur, Update, Widerruf und nicht mehr erreichbare Quelle,
- Kursreaktion relativ zum passenden Benchmark vor dem Einstieg,
- unveränderlichen News-Snapshot im Trade-Ticket.

Gates:

- Kein News-Trade ohne erreichbare Source-URL.
- Kein Trade auf eine alte, korrigierte oder semantisch nicht zum Instrument passende Meldung.
- Provider-bezogene Watchlist allein ist kein Beweis, dass eine Meldung das Instrument betrifft.
- Telegram nennt Quelle, Veröffentlichungszeit, Datenalter, Trigger und Invalidierung.

## Phase 2 – Professionelle Markt- und Newsdaten

Priorität: sehr hoch

1. Provider-Adapter einführen, damit yfinance nur Fallback bleibt.
2. Für US-Aktien/ETFs/Krypto zunächst einen authentifizierten Streaming-Feed mit Trades, Quotes, Bars und News anbinden.
3. Feed-Typ (`IEX`, `SIP`, verzögert, indikativ, OPRA), Exchange, Bid, Ask und Timestamp speichern.
4. Für deutsche/europäische Aktien einen Provider mit passender Börsenabdeckung ergänzen.
5. Zwei Datenquellen für kritische Preise vergleichen; bei Abweichung oder Stale-Status keinen Entry zulassen.
6. Lizenz- und Nutzungsrechte dokumentieren. yfinance bleibt Forschungs-/Fallbackquelle und darf nicht stillschweigend als institutioneller Echtzeitfeed behandelt werden.

Empfohlener erster Integrationspfad:

- Alpaca Paper für API-basierte US-Aktien/ETF/Krypto-Paperorders, Streamingkurse und News.
- Alternativ oder anschließend IBKR Paper für breitere internationale Instrumentabdeckung.
- Scalable bleibt nur Read-only, solange keine offiziell unterstützte Order-API und ausdrückliche Freigabe vorhanden sind.

## Phase 3 – Broker-Paper statt nur lokaler Simulation

Priorität: sehr hoch

1. Einheitliches `BrokerAdapter`-Interface für Account, Order, Fill, Position und Cancel.
2. Ausschließlich Paper-Credentials und Paper-Endpunkt zulassen; Live-Endpunkte technisch blockieren.
3. Jede lokale Order mit Broker-Order-ID, Statusfolge und Fill-Ereignissen speichern.
4. WebSocket-/SSE-Updates statt blindem Polling verwenden.
5. Lokales Depot und Broker-Paper-Depot regelmäßig reconciliieren.
6. Teilfills, Rejections, Market-Hours, Tick Size, Gebühren, Spread und Slippage abbilden.
7. Telegram nur bei echten Zustandsänderungen: akzeptiert, teilgefüllt, gefüllt, abgelehnt, Stop/Target, geschlossen.

Abnahme:

- 100 Testorders ohne unbekannten Status.
- 0 ungeklärte Reconciliation-Differenzen.
- Jeder Fill besitzt Provider, Timestamp, Bid/Ask und Order-ID.
- Neustarts erzeugen keine Doppelorders.

## Phase 4 – Telegram als Ereigniskanal

Priorität: hoch

Ereignis-ID statt Textvorlage als Dedupe-Grundlage:

`provider_event_id + instrument + event_version + decision_state`

Telegram sendet nur bei:

- neuer verifizierter News,
- materieller Artikelkorrektur,
- neuem oder verändertem Signalzustand,
- Broker-Paper-Order-/Fill-Änderung,
- Stop, Target, Invalidierung oder Ablauf,
- neuem abgeschlossenen Lernurteil,
- echtem Betriebsfehler.

Jede Nachricht zeigt:

- warum sie neu ist,
- Quelle und Zeit,
- Instrument und Richtung,
- Marktpreis mit Feed und Datenalter,
- Entry-Bedingung, Stop, Ziel und Positionsrisiko,
- Paper-Order-/Trade-ID,
- was die These widerlegt,
- ob es nur Research, Paper-Kandidat oder ausgeführter Paper-Trade ist.

## Phase 5 – Belastbare Lernkampagne

Priorität: hoch, benötigt Zeit

1. Mindestens 100 globale entscheidende Outcomes sammeln.
2. Mindestens 30 zukünftige geschlossene Trades je Challenger vor Promotion.
3. Aktien, ETFs und Krypto sowie Trend-/Volatilitätsregime getrennt bewerten.
4. Nur echte Broker-Paper-Fills für die finale Ausführungsbewertung verwenden.
5. News-Setups nach Quelle, Ereignistyp, Alter und Reaktionsphase segmentieren.
6. Benchmarkrendite, aktive Rendite, Profit Factor, Erwartungswert, Drawdown, Kosten und Prozessqualität berichten.
7. Kein Score-Boost aus kleinen Stichproben; negative Evidenz darf Paper-Risiko früh reduzieren.
8. Aktive Regeln bleiben unter Live-Paper-Monitor und Kill-Switch.

## Phase 6 – Produktions- und Echtgeld-Gates

Echtgeld bleibt gesperrt, bis alle Punkte erfüllt sind:

- mindestens 30 Tage unbeaufsichtigter Paper-Soak ohne kritischen Betriebsfehler,
- mindestens 100 Broker-Paper-Trades und ausreichende Stichprobe je freigegebener Strategie,
- positive Erwartung nach Kosten und gegenüber Benchmark,
- akzeptabler Drawdown und keine unvertretbare Ticker-/Regimekonzentration,
- keine ungeklärten Order-, Fill- oder Depotabweichungen,
- getesteter globaler Kill-Switch und maximale Tages-/Positionsverluste,
- Secret Rotation, Backup/Restore, Audit-Export und Incident-Runbook,
- manuelle Freigabe jeder Strategie und jeder Kapitalerhöhung,
- zuerst kleinstmögliche Kapitalstufe; keine autonome Hochskalierung.

## Unmittelbar nächste Arbeitspakete

1. Telegram-Credentials reparieren und End-to-End-Zustellung beweisen.
2. News-Evidence-Contract zwingend an jeden News-Paper-Entry binden.
3. Alpaca-Paper-Adapter hinter einer harten Paper-only-Sperre implementieren.
4. Order-/Fill-Reconciliation und idempotente Client-Order-IDs bauen.
5. Telegram auf echte Event-/Order-Versionen umstellen und einen Inhalts-Fingerprint speichern.
6. Neue Paper-Kampagne ausschließlich mit nachweisbaren News-, Kurs- und Broker-Fill-Daten starten.

## Aktuelle Entscheidung

Das Projekt ist heute ein fortgeschrittenes Research- und lokales Paper-Learning-System. Es ist noch kein verlässliches Werkzeug für Echtgeldhandel. Die größten Blocker sind der ungültige Telegram-Token, fehlende Broker-Paper-Ausführung, zu geringe Lernstichprobe und fehlende News-Evidenz bei den bisherigen Trades.
