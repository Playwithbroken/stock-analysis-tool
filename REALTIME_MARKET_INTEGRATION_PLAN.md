# Exakter Integrationsplan für echte Marktdaten und Broker-Paper-Trading

Stand: 27. August 2026, Europe/Berlin

## Ziel und klare Grenze

Das Projekt soll Aktien, ETFs und Krypto mit echten, zeitgestempelten Marktdaten beobachten, daraus reproduzierbare Signale erzeugen, Orders ausschließlich an echte Paper-Endpunkte senden und aus den tatsächlich gemeldeten Paper-Fills lernen.

MCP wird als Bedien-, Abfrage- und Diagnoseebene verwendet. Der zeitkritische Datenweg läuft direkt über die offiziellen WebSocket-/Broker-Schnittstellen. MCP darf keine Kurse erfinden, keine fehlenden Daten ergänzen und nicht zwischen Marktereignis und Risikoprüfung liegen.

```text
Offizieller Provider-WebSocket
          |
          v
 Feed-Adapter -> Normalisierung -> persistenter Event-Log
          |              |                 |
          |              v                 v
          |        Frische-/Qualitätsgate  Audit + Replay
          |              |
          v              v
       Signal -> Risiko-Gate -> Broker-Paper-Order
                                   |
                                   v
                          Order-/Fill-Stream
                              |         |
                              v         v
                         Telegram    Lernsystem

 MCP: Status, Evidenz, Paper-Depot, Regeln und Kill-Switch abfragen/bedienen
```

## Festgelegter Provider-Pfad

### Ausbaustufe 1: US-Aktien und ETFs

- Alpaca Market Data WebSocket für Trades, Quotes und Bars.
- Alpaca News WebSocket für maschinenlesbare Echtzeit-News.
- Alpaca Paper Trading für Orders, Statuswechsel, Teilfills und Fills.
- Der tatsächlich verwendete Feed wird gespeichert: `IEX`, `SIP`, verzögert oder indikativ.
- Für eine vollständige US-Marktabdeckung ist SIP ein eigenes Freigabe-Gate. Ein IEX-Feed darf nie als vollständiger Gesamtmarkt gekennzeichnet werden.

### Ausbaustufe 2: Krypto

- Direkter Coinbase Advanced Trade WebSocket für `ticker`, `market_trades`, `level2` und `heartbeats`.
- Sequenznummern werden geprüft; bei Lücken wird das Orderbuch verworfen und neu synchronisiert.
- Paper-Ausführung bleibt zunächst beim Broker-Paper-Adapter oder in einer ausdrücklich gekennzeichneten lokalen Shadow-Simulation. Ein lokaler Simulationsfill darf niemals als Broker-Fill gespeichert werden.
- Erst nach separatem Freigabeprozess darf ein authentifizierter User-/Order-Kanal ergänzt werden. Echtgeld-Keys gehören nicht in diese Phase.

### Ausbaustufe 3: Deutschland und weitere internationale Märkte

- IBKR Paper über IB Gateway/TWS für Aktien und ETFs außerhalb der Alpaca-Abdeckung.
- Erforderliche Börsendaten-Abonnements und Handelsberechtigungen werden je Börse dokumentiert.
- Paper- und Live-Port beziehungsweise Account-ID werden hart getrennt. Der Adapter verweigert unbekannte oder Live-Accounts.

### Bestehende Quellen

- `yfinance` bleibt Research-, historische Backfill- und Notfallquelle.
- RSS bleibt zusätzlicher Discovery-Kanal.
- Beide dürfen im schnellen Modus weder einen Entry freigeben noch einen Broker-Paper-Fill ersetzen.

## Zwei klar getrennte Betriebsmodi

| Eigenschaft | Swing-Paper | Fast-Paper |
|---|---:|---:|
| Kursquelle | Streaming bevorzugt, Backfill erlaubt | nur freigegebener Streaming-Feed |
| Maximales Quote-Alter beim Entry | 60 Sekunden | Aktien/ETF 2 Sekunden, Krypto 1 Sekunde |
| Maximales News-Alter beim Entry | strategieabhängig, höchstens 60 Minuten | grundsätzlich 120 Sekunden; Ereignistyp darf enger sein |
| Signalprüfung | Ereignis oder maximal 1 Minute | sofort pro relevantem Ereignis |
| Broker-ACK p95 | 5 Sekunden | 2 Sekunden |
| Telegram nach Statusänderung p95 | 10 Sekunden | 5 Sekunden |
| Fallback-Daten dürfen Entry auslösen | nur ausdrücklich markiert | nein |

Das Projekt wird nicht als HFT- oder Scalping-System bezeichnet. Internet, Python, Drittanbieter und Paper-Broker liefern dafür keine garantierte deterministische Mikrosekunden-Latenz.

## Verbindlicher Ereignisvertrag

Jedes Provider-Ereignis wird vor der weiteren Verarbeitung in ein gemeinsames Schema übersetzt:

```json
{
  "event_id": "provider:channel:sequence-or-native-id",
  "event_type": "quote|trade|bar|news|order|fill|heartbeat",
  "provider": "alpaca|coinbase|ibkr",
  "feed": "iex|sip|coinbase|ibkr_exchange_bundle",
  "asset_class": "equity|etf|crypto",
  "symbol": "AAPL",
  "exchange": "NASDAQ",
  "provider_timestamp": "ISO-8601 UTC",
  "received_at": "ISO-8601 UTC",
  "normalized_at": "ISO-8601 UTC",
  "sequence": 12345,
  "bid": 0,
  "ask": 0,
  "last": 0,
  "size": 0,
  "source_payload_hash": "sha256",
  "quality": {
    "stale": false,
    "sequence_gap": false,
    "crossed_market": false,
    "fallback": false
  }
}
```

Für jede Signalentscheidung kommen zusätzlich `decision_at`, `data_age_ms`, `signal_version`, `rule_version`, `risk_snapshot_id` und die IDs aller verwendeten Marktereignisse hinzu. Damit kann später exakt rekonstruiert werden, was das System zu diesem Zeitpunkt wusste.

## Datenbank-Erweiterung

In `src/storage.py` werden additive Migrationen für folgende Tabellen angelegt:

1. `market_events`
   - normalisierte Quotes, Trades, Bars und Heartbeats,
   - eindeutiger Schlüssel aus Provider und `event_id`,
   - Provider-, Empfangs- und Normalisierungszeit.
2. `news_events`
   - native News-ID, Publisher, URL, Zeitstempel, Hash, Version und Korrekturstatus,
   - unveränderlicher Rohdaten-Hash sowie Symbolzuordnung.
3. `signal_decisions`
   - Eingabereferenzen, Strategie-/Regelversion, Ergebnis, Ablehnungsgrund und Datenalter.
4. `broker_orders`
   - interne `client_order_id`, Broker-ID, Account-Modus, Request-Hash und Status.
5. `broker_order_events`
   - komplette, idempotent gespeicherte Statusfolge einschließlich Teilfills und Ablehnungen.
6. `broker_positions_snapshots`
   - Brokerbestand und lokaler Bestand für Reconciliation.
7. `latency_samples`
   - Segmentzeiten `provider_to_receive`, `normalize`, `signal`, `risk`, `submit_ack`, `fill`, `telegram`.
8. `integration_incidents`
   - Verbindungsabbrüche, Sequenzlücken, Stale-Daten, Reconciliation-Differenzen und Zustellfehler.

Rohereignisse erhalten eine Aufbewahrungsfrist. Entscheidungen, Orders, Fills und Auditdaten bleiben dauerhaft erhalten. Secrets und vollständige Zugangsdaten werden niemals in diesen Tabellen gespeichert.

## Konkrete Projektmodule

### Neu anzulegen

- `src/integrations/contracts.py`
  - Datenklassen/Modelle für Market-, News-, Order- und Fill-Ereignisse.
- `src/integrations/market_data/base.py`
  - `MarketDataAdapter` mit `connect`, `subscribe`, `health`, `close`.
- `src/integrations/market_data/alpaca.py`
  - Alpaca Trades/Quotes/Bars/News, Reconnect, Subscription-ACK und Feed-Kennzeichnung.
- `src/integrations/market_data/coinbase.py`
  - Ticker/Trades/Level2/Heartbeat, Sequenzkontrolle und Resync.
- `src/integrations/brokers/base.py`
  - `BrokerAdapter` für Account, Order, Cancel, Orderstream, Positionen und Reconciliation.
- `src/integrations/brokers/alpaca_paper.py`
  - ausschließlich Paper-Basis-URL; Live-Basis-URL löst Startfehler aus.
- `src/integrations/brokers/ibkr_paper.py`
  - spätere internationale Paper-Anbindung mit erlaubter Account-ID.
- `src/market_event_store.py`
  - idempotente Persistenz und Replay.
- `src/market_quality_service.py`
  - Stale-, Spread-, Sequenz-, Session- und Cross-Provider-Gates.
- `src/order_execution_service.py`
  - idempotente Ordererstellung und Statusautomat.
- `src/broker_reconciliation_service.py`
  - Abgleich lokaler Orders/Positionen mit dem Broker.
- `src/latency_monitor_service.py`
  - persistente p50/p95/p99-Auswertung und Alarme.
- `src/mcp_trading_server.py`
  - sichere MCP-Werkzeuge auf Basis der normalisierten Daten.

### Gezielt umzubauen

- `src/realtime_market_service.py`
  - liest den letzten validierten Streamzustand statt synchron `DataFetcher`/yfinance aufzurufen;
  - `updated_at` stammt vom Provider und nicht von der lokalen Erstellungszeit.
- `src/paper_trading_service.py`
  - trennt `local_simulation`, `broker_paper` und später `live` als nicht verwechselbare Ausführungsarten;
  - akzeptiert im Fast-Modus keine 24/96 Stunden alten Kurse;
  - lernt Ausführung nur aus Broker-Fills.
- `src/paper_learning_service.py`
  - bewertet Signalqualität und Ausführungsqualität getrennt;
  - nutzt nur abgeschlossene, reconciliierte Broker-Paper-Trades für Regelpromotionen.
- `src/provider_observability.py`
  - schreibt Metriken persistent und ergänzt p99, Disconnects, Sequenzlücken und Datenalter.
- `src/email_alert_service.py`
  - Telegram wird durch gespeicherte Zustandsereignisse ausgelöst;
  - Versandbestätigung wird erst nach erfolgreicher Telegram-Antwort persistiert.
- `api.py`
  - startet und beendet Stream-Worker kontrolliert;
  - liefert Health, Feedstatus, Brokerstatus, Latenzen und Reconciliation;
  - Polling-Scheduler bleibt nur für Wartung, Backfill und Outcome-Auswertung.
- `.env.example`
  - erhält ausschließlich Platzhalter und sichere Paper-Defaults.

## MCP-Einbettung

Der lokale MCP-Server stellt zunächst nur folgende Werkzeuge bereit:

- `market_status`: Provider, Feed, Verbindung, letztes Ereignis, Alter, p95/p99.
- `get_quote_evidence`: letzter validierter Quote mit Provider- und Börsenzeit.
- `get_news_evidence`: Originalquelle, Veröffentlichungszeit, Version und Korrekturstatus.
- `list_paper_orders`: Broker-Paper-Orders und komplette Statusfolge.
- `get_paper_portfolio`: reconciliierte Positionen, Cash und offene Risiken.
- `explain_signal`: Eingabeereignisse, Regelversion, Risikoentscheidung und Ablehnungsgründe.
- `pause_paper_trading`: globaler Paper-Kill-Switch.
- `resume_paper_trading`: nur mit expliziter Bestätigung und bestandenem Health-Gate.

In der ersten Version gibt es über MCP keine Live-Orderfunktion. Eine MCP-Aktion darf höchstens einen Paper-Order-Kandidaten erzeugen; Risiko-Gate und Paper-only-Brokeradapter bleiben zwingend. Markt- und Newsdaten im MCP stammen ausschließlich aus dem Event-Store und tragen immer Zeit und Datenalter.

## Sichere Konfiguration

Neue Variablen, alle standardmäßig sicher/deaktiviert:

```dotenv
TRADING_MODE=research
FAST_PAPER_ENABLED=false
LIVE_TRADING_ENABLED=false

ALPACA_PAPER_ENABLED=false
ALPACA_API_KEY_ID=<secret>
ALPACA_API_SECRET_KEY=<secret>
ALPACA_MARKET_FEED=iex

COINBASE_MARKET_DATA_ENABLED=false
COINBASE_PRODUCTS=BTC-USD,ETH-USD

IBKR_PAPER_ENABLED=false
IBKR_HOST=127.0.0.1
IBKR_PAPER_PORT=7497
IBKR_ALLOWED_ACCOUNT=<paper-account-id>

FAST_EQUITY_MAX_QUOTE_AGE_MS=2000
FAST_CRYPTO_MAX_QUOTE_AGE_MS=1000
FAST_NEWS_MAX_AGE_SECONDS=120
MARKET_STREAM_DISCONNECT_KILL_SECONDS=5
BROKER_RECONCILIATION_INTERVAL_SECONDS=30
```

`LIVE_TRADING_ENABLED` bleibt im Code zusätzlich hart deaktiviert, bis ein eigener, späterer Freigabe-Change geprüft wurde. Das bloße Setzen einer Umgebungsvariable darf Echtgeldhandel nicht aktivieren.

## Umsetzung in neun Pull-Request-großen Arbeitspaketen

Umsetzungsstand:

- Paket 1 ist am 27.08.2026 implementiert und lokal verifiziert: versionierte Markt-, News- und Broker-Paper-Ereignisverträge, acht additive Evidenz-/Betriebstabellen, kanonische Payload-Hashes, idempotenter Market-Event-Store und deterministisches Replay.
- Paket 2 ist am 27.08.2026 code-seitig implementiert und mit offiziellen Offline-Fixtures verifiziert: Alpaca-Authentifizierung und Subscription-Verträge, Quotes/Trades/Bars/News, Reconnect, News-Versionierung, Stream-Health sowie Einbindung in App-Start und Echtzeit-Snapshot. Die Live-Abnahme einschließlich achtstündigem Markt-Soak steht aus, weil noch keine Alpaca-Paper-Zugangsdaten freigegeben wurden.
- Paket 3 ist am 27.08.2026 code-seitig implementiert und lokal verifiziert: harte Alters-, Bid/Ask-, Spread-, Provider-, Feed-, Session- und Clock-Skew-Gates, persistente p50/p95/p99-Latenzen, Ping/Pong-Transportüberwachung, automatischer Fast-Paper-Kill-Switch und persistente Incidents. Die Grenzwerte sind im Fast-Paper-Modus fail-closed an beide Paper-Entry-Pfade gebunden. Die Live-Latenzabnahme steht bis zur Provider-Aktivierung aus.
- Paket 4 ist am 27.08.2026 code-seitig implementiert und lokal verifiziert: hart auf `paper-api.alpaca.markets` begrenzter Brokeradapter, idempotente `client_order_id`, Statusautomat, Teilfills/Fills, Trade-Update-WebSocket, Cancel/Refresh-API und Schutz vor blindem Retry bei unklarem Submission-Ausgang. Die Live-Abnahme steht aus, weil noch keine Alpaca-Paper-Zugangsdaten freigegeben wurden.
- Paket 5 ist am 27.08.2026 code-seitig implementiert und lokal verifiziert: Account-, Order- und Positionsabgleich, persistente Snapshots, Cash-/Equity-Konsistenz, kritische Incidents, automatische Auflösung nach sauberem Folgeabgleich sowie ein frisches Reconciliation-Gate vor jeder neuen Broker-Paper-Order. Mismatch, Teilfill, Cancel und Neustart sind durch Offline-QA abgedeckt; die Live-Abnahme wartet auf Paper-Zugangsdaten.
- Short-Learning ist am 28.08.2026 ergänzt: Aktien/ETFs erhalten score- und stopbasiertes Paper-Sizing, 12 % Positions-/30 % Gesamtlimit sowie Broker-Gates für `shortable`, `marginable`, ganze Stücke und den aktuellen Alpaca-`borrow_status`. Krypto-Shorts laufen ausschließlich als lokale synthetische Paper-Positionen mit 5 % Positions-/10 % Gesamtlimit, halbem Risikobudget und kontinuierlichen Funding-Kosten; sie sind niemals Broker-routbar.
- Das lokale Lernkonto nutzt jetzt ein explizites `conviction`-Kapitalprofil für 500.000 EUR: 0,75 % Basisrisiko pro starkem Trade, scoreabhängige Staffelung, 20 % Positionslimit, 90 % harte Bruttoobergrenze, 10 % Cashreserve und 75 % Zielauslastung. Zielauslastung ist kein Kaufzwang; alle Qualitäts-, Diversifikations-, Verlust- und Kill-Switch-Gates bleiben zwingend.
- Pakete 6–9 sind noch nicht implementiert. Insbesondere fehlen zustandsgetriebene Telegram-Ereignisse, der sichere MCP-Bedienpfad sowie Coinbase und IBKR.

### Paket 1 – Verträge, Datenbank und Replay

- Gemeinsame Ereignismodelle und additive Migrationen implementieren.
- Idempotenz und UTC-Zeitbehandlung testen.
- Ein aufgezeichnetes Ereignis muss nach Neustart identisch wiedergegeben werden.

Abnahme: Doppelte Provider-Events erzeugen keine doppelten Datensätze; Replay produziert denselben normalisierten Zustand.

### Paket 2 – Alpaca-Streamingdaten und News

- Authentifizierung, Subscriptions, Reconnect mit Backoff/Jitter und Heartbeat bauen.
- Providerzeit, Empfangszeit und Feedtyp speichern.
- yfinance nur für Backfill verwenden.

Abnahme: acht Stunden Markt-Soak ohne unbemerkten Disconnect; jede Lücke wird erkannt; keine Stale-Quote wird als live ausgegeben.

### Paket 3 – Qualitäts- und Latenz-Gates

- Stale-, Spread-, Session-, Sequenz- und Crossed-Market-Prüfung implementieren.
- p50/p95/p99 persistent messen.
- Bei Feedverlust Fast-Paper automatisch pausieren.

Abnahme: künstlich alte, vertauschte, doppelte und lückenhafte Events werden deterministisch abgelehnt.

### Paket 4 – Alpaca Broker-Paper

- Paper-Account verifizieren und Live-Endpunkt blockieren.
- Idempotente `client_order_id`, Orderautomat und Trade-Update-Stream bauen.
- Teilfills, Rejections, Cancels und Neustarts abdecken.

Abnahme: 100 automatisierte Paper-Testorders, keine Doppelorder, kein unbekannter Endstatus.

### Paket 5 – Reconciliation und Paper-Depot

- Brokerorders, Positionen und Cash regelmäßig mit der lokalen Datenbank vergleichen.
- Differenzen blockieren neue Orders und öffnen einen Incident.
- Das Dashboard zeigt Brokerwerte und lokale Werte nebeneinander.

Abnahme: null ungeklärte Differenzen nach Neustart-, Teilfill- und Cancel-Tests.

### Paket 6 – Ereignisgesteuerte Signale und Telegram

- Signale direkt aus validierten Events anstoßen.
- Telegram-Token reparieren und über `getMe`/Testnachricht prüfen.
- Nur neue Zustandsversionen senden; Quelle, Zeit, Alter, Feed, Risiko und Paper-Order-ID anzeigen.

Abnahme: Signal bis Telegram p95 höchstens fünf Sekunden; identisches Event wird genau einmal versendet.

### Paket 7 – MCP-Server

- Read-only Status-, Evidenz-, Depot- und Erklärwerkzeuge implementieren.
- Paper-Kill-Switch mit Auditlog ergänzen.
- Alle Ausgaben tragen `as_of`, Provider, Feed und Datenalter.

Abnahme: MCP liefert nie frischere Zeitstempel als der zugrunde liegende Provider und kann keine Live-Order auslösen.

### Paket 8 – Coinbase und danach IBKR Paper

- Coinbase-Sequenz-, Heartbeat- und Orderbuchlogik ergänzen.
- Nach stabilem Krypto-Soak IBKR Paper separat anbinden.
- Symbolmapping nutzt Provider-Instrument-IDs statt nur Tickersymbole.

Abnahme: Krypto-Resync nach absichtlicher Sequenzlücke; IBKR-Test auf mindestens einer deutschen und einer US-Handelsroute im Paper-Konto.

### Paket 9 – Lernkampagne und Produktions-Soak

- Alte lokale Trades als `legacy_local_simulation` markieren und nicht mit Broker-Paper-Fills vermischen.
- Mindestens 100 reconciliierte Broker-Paper-Trades sammeln, mindestens 30 je Regel/Segment.
- 30 Tage unbeaufsichtigter Soak mit Incident- und Latenzbericht.

Abnahme: positive Erwartung nach Spread, Slippage und Gebühren ist vorhanden; Drawdown- und Datenqualitätsgrenzen wurden nie unbemerkt verletzt. Dies ist noch keine Garantie für zukünftige Gewinne.

## Neue QA-Dateien

- `qa_market_event_contract.py`
- `qa_market_event_replay.py`
- `qa_alpaca_stream_resilience.py`
- `qa_market_staleness_gate.py`
- `qa_latency_budget.py`
- `qa_broker_paper_only_gate.py`
- `qa_broker_order_idempotency.py`
- `qa_broker_reconciliation.py`
- `qa_coinbase_sequence_resync.py`
- `qa_mcp_market_evidence.py`
- `qa_mcp_live_order_block.py`
- `qa_telegram_event_latency.py`

Providerabhängige Tests laufen nur mit ausdrücklich bereitgestellten Paper-/Test-Credentials. Offline-Vertragstests verwenden gespeicherte, anonymisierte Fixtures.

## Go-/No-Go-Gates

Fast-Paper startet nur, wenn gleichzeitig gilt:

- Stream verbunden und korrekter Feed identifiziert,
- letzte Heartbeats innerhalb der Grenze,
- Quote und News innerhalb der Strategiegrenze,
- keine Sequenzlücke oder offene Reconciliation-Differenz,
- Broker-Paper-Account eindeutig bestätigt,
- Tagesverlust-, Drawdown-, Positions- und Gesamtrisikolimits frei,
- Telegram und Auditlog gesund,
- globaler Kill-Switch nicht aktiv.

Bei einem Fehler lautet die Standardaktion `NO_TRADE`. Es gibt keinen automatischen Wechsel auf alte yfinance-, RSS- oder Cache-Daten.

## Reihenfolge und realistischer Aufwand

| Abschnitt | Pakete | Grober Entwicklungsaufwand |
|---|---|---:|
| Fundament | 1–3 | 8–12 Arbeitstage |
| Echter Broker-Paper-Pfad | 4–6 | 10–15 Arbeitstage |
| MCP und weitere Märkte | 7–8 | 8–15 Arbeitstage |
| Lernnachweis | 9 | mindestens 30 Kalendertage Soak |

Der erste sinnvolle Meilenstein ist nicht „alle Märkte“, sondern ein vollständig belegbarer Pfad für wenige liquide US-Aktien/ETFs: Stream -> Qualitätsgate -> Signal -> Alpaca-Paper-Order -> Broker-Fill -> Telegram -> Outcome -> Lernen. Erst danach werden Krypto und IBKR ergänzt.

## Was vom Betreiber benötigt wird

1. Neues gültiges Telegram-Bot-Token und bestätigte Chat-ID.
2. Alpaca-Paper-Konto und Market-Data-Berechtigung; Entscheidung zwischen IEX und SIP.
3. Liste der ersten 10–20 US-Aktien/ETFs für den kontrollierten Pilot.
4. Für Krypto die gewünschten Coinbase-Produkte.
5. Später ein IBKR-Paper-Konto und die benötigten Börsendaten-Abonnements für Europa.

Alle Zugangsdaten werden ausschließlich als lokale oder Deployment-Secrets hinterlegt. Sie gehören weder in Git noch in Telegram, Logs, MCP-Antworten oder Datenbankexporte.

## Offizielle technische Grundlagen

- Alpaca: [Market Data](https://docs.alpaca.markets/us/docs/about-market-data-api), [Streaming Market Data](https://docs.alpaca.markets/us/docs/streaming-market-data), [Realtime News](https://docs.alpaca.markets/us/docs/streaming-real-time-news) und [Paper Trading](https://docs.alpaca.markets/us/v1.4.2/docs/paper-trading).
- Coinbase Advanced Trade: [WebSocket Overview](https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/websocket/websocket-overview) sowie [Heartbeats, Ticker, Trades und Level 2](https://docs.cdp.coinbase.com/coinbase-business/advanced-trade-apis/websocket/websocket-channels).
- Interactive Brokers: [Paper-Konto und API](https://interactivebrokers.github.io/tws-api/introduction.html), [Streaming Market Data](https://interactivebrokers.github.io/tws-api/market_data.html) und [getrennte Paper-Konfiguration](https://interactivebrokers.github.io/tws-api/initial_setup.html).
- Telegram: [Bot API](https://core.telegram.org/bots/api/) und [Webhook-/Long-Polling-Verhalten](https://core.telegram.org/bots/faq).

Diese Dokumentation ist vor jeder Provider-Implementierung erneut auf Endpunkte, Limits, Berechtigungen und Lizenzbedingungen zu prüfen.
