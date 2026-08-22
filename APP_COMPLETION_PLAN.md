# Broker Freund – Abschlussplan

Stand: 21. August 2026

## Ziel und klare Endbedingung

Die App gilt als fertig, wenn sie als private, produktive Analyse- und Paper-Trading-Anwendung sieben Tage ohne kritischen Fehler läuft, jede Handlungsinformation reproduzierbar belegt ist und kein Demo-, Options- oder Hebelwert präziser dargestellt wird als die Datenquelle erlaubt.

„Fertig“ bedeutet nicht, dass jede denkbare Funktion eingebaut ist. Nach Erreichen der Abnahmekriterien werden neue Ideen in ein separates Backlog verschoben. Der Release-Scope bleibt dann eingefroren.

## Bereits belastbarer Stand

- Geschützter Workspace, persistente Datenbank auf Railway-Volume und Backup-Endpunkt.
- Aktien-, ETF- und Crypto-Analyse, Portfolio, Morning Briefs und Telegram-Versand.
- Paper-Konto mit 500.000 EUR, Stops, Zielen, Haltedauern, Risiko-Circuit, Re-Entry-Cooldown und automatischen Exits.
- Paper-Autopilot mit striktem, Lern- und aggressivem Lernmodus.
- Kapital-, Ticker-, Optionsprämien- und Gesamtrisikolimits.
- Korrelations-Buckets verhindern neue Doppelwetten im selben Risikofaktor.
- Kauf-, Verkauf-, Management-, Lern- und Konto-Risiko-Pushes über Telegram.
- News-Gates mit Quelle, Zeitstempel, Faktenbasis, Marktbestätigung und Invalidierung.
- Release-Smoke-Test sowie spezialisierte QA-Verträge für Auth, Persistenz, Alerts, Briefs und Trading.

## P0 – Trading- und Datenintegrität

Ziel: Kein Trade und keine Push-Nachricht darf auf erfundenen oder unklaren Handelsdaten beruhen.

- [x] Options-Alerts nach Basiswert und Richtung individualisieren.
- [x] Konkreten Optionsketten-Snapshot mit Kontrakt, Strike, Verfall, Bid/Ask, Spread, IV, Volumen, Open Interest, Break-even und Prämienrisiko modellieren.
- [x] Unbrauchbare oder einseitige Optionsquotes ausdrücklich als nicht verfügbar markieren.
- [x] Produktionsfähigen Optionsdatenanbieter integrieren: Die read-only Tradier-Schicht lädt bei konfiguriertem Produktionskonto Echtzeit-Optionsketten und gespeicherte Kontraktquotes; Sandbox und Yahoo bleiben ausdrücklich verzögert, jeder Quote fehlt bewusst eine Fill-Garantie und keinerlei Order-Endpunkt wird verwendet.
- [x] Greeks (Delta, Gamma, Theta, Vega) aus den von Tradier gelieferten ORATS-Werten übernehmen, Anbieterstatus, Quelle und Modellgrenze in App und Telegram kennzeichnen; fehlende oder partielle Greeks bleiben sichtbar.
- [x] Kontrakt-Mapping vom Paper-Einstieg bis zum Exit unveränderlich speichern; kein späterer Wechsel auf einen anderen Strike oder Verfall.
- [x] Options-Management gegen den gespeicherten Kontraktpreis auswerten; fehlt eine brauchbare Quote, P&L/Auto-Exit blockieren und den Underlying nur ausdrücklich als Outcome-Fallback verwenden.
- [x] News-getriebene Trades nur öffnen, wenn Primärquelle oder verifizierte Tier-1-Quelle, echte Veröffentlichungszeit sowie chronologisch plausibles Marktreaktionsfenster unveränderlich im Trade-Ticket gespeichert sind.
- [x] Hebel-End-to-End-Test für Aktien/ETFs, Standardoptionen und Anbieterprodukte: angebotener Hebel, Produktmultiplikator, eingebetteter Hebel, Stoprisiko und P&L werden exakt einmal angewendet.

Abnahme:

- 100 % der Optionsmeldungen nennen entweder einen konkreten Kontrakt mit Datenqualität oder eindeutig „kein verifizierbarer Kontrakt“.
- Kein Options- oder Hebeltrade passiert das finale Gate mit fehlendem Bid/Ask, abgelaufenem Kontrakt, zu breitem Spread oder undokumentiertem Maximalverlust.
- Derselbe gespeicherte Kontrakt wird in Kauf-, Management- und Verkaufsmeldung verwendet.

## P0 – Paper-Trader als belastbares Lernsystem

Ziel: Das große Demo-Portfolio produziert verwertbare Erkenntnisse, keine Aktivität um jeden Preis.

- [x] Risikobasierte Positionsgrößen und hohe Kapitalnutzung bei ausreichenden Setups.
- [x] Unabhängige Risikobuckets innerhalb eines Laufs und gegenüber offenen Trades.
- [x] Automatische Kauf-, Management- und Verkaufsmeldungen.
- [x] Portfolio-Korrelation quantitativ mit sechs Monaten Tagesrenditen messen; extreme Korrelation blockiert erst ab dokumentierter Mindeststichprobe, statische Buckets bleiben zusätzlicher Sicherheitsgurt.
- [x] Marktregime beim Einstieg unveränderlich speichern: Trend, Volatilitäts-Proxy, Zinsen, Dollar, Risikoappetit und Breiten-Proxy; Proxy-Methoden und fehlende Dimensionen bleiben sichtbar.
- [x] Slippage und Gebühren je Assetklasse regelmäßig gegen beobachtbare Spreads kalibrieren: Das versionierte 90-Tage-Modell nutzt mindestens die halbe beobachtete Bid/Ask-Spanne pro Seite, trennt Gebühren, Slippage, Liquiditäts- und Altersaufschläge, zeigt Stichprobe/Fallback je Assetklasse und speichert die vollständige Kalibrierung unveränderlich im Entry-/Exit-Fill.
- [x] Strategieauswertung nach Setup, Marktregime, Quelle, Scoreband und Risikobucket mit Trefferquote, Profit Factor, Erwartungswert, Drawdown und Stichprobenstatus anzeigen.
- [ ] Mindestens 30 geschlossene Trades je freizugebender Strategie und mindestens 100 entscheidende Outcome-Prüfungen sammeln.
  Technische Evidenzkampagne misst sechs Strategien getrennt, priorisiert unterrepräsentierte Strategien nur unter bereits qualifizierten Paper-Kandidaten und zählt ausschließlich echte fällige Outcomes; der Punkt bleibt bis zur realen Stichprobe offen.
- [x] Eine Strategie nur hochstufen, wenn mindestens 30 geschlossene Trades/klare Prüfungen, Trefferquote, Profit Factor, positive Erwartung und Drawdown gleichzeitig die dokumentierten Mindestwerte erfüllen.
- [x] Kapitalfreigabe-Fahrplan zeigt für offene Trades die nächste planmäßige Zeitprüfung, potenziell innerhalb von 72 Stunden frei werdendes Paper-Kapital und die danach priorisierte Evidenzstrategie; aktuelle Paper-Werte sind ausdrücklich keine garantierten Verkaufserlöse und alle Entry-Gates werden erneut geprüft.
- [x] Wochen-, Monats- und Jahresupdate für das Paper-Portfolio basiert auf unveränderlichen täglichen Konto-Snapshots, trennt Equity-Veränderung von realisierten Trades und zeigt fehlende historische Baselines in App und Telegram ausdrücklich statt rückwirkend Renditen zu schätzen.

Abnahme:

- Kein Modus eröffnet eine korrelierte Doppelposition oder überschreitet Cash-, Exposure-, Risiko-, Optionsprämien- oder Slot-Limits.
- Vorschau und tatsächliche Ausführung stimmen innerhalb der dokumentierten Fill-/Slippage-Toleranz überein.
- Jede Strategie zeigt Stichprobe, Trefferquote, Profit Factor, Erwartungswert, Drawdown und klare Readiness-Lücken.

## P1 – Informationsqualität und Telegram

Ziel: Jede Push-Nachricht beantwortet in unter einer Minute, was passiert ist und was daraus folgt.

- [x] Kauf/Verkauf enthält Kontoübersicht, Risiko, Trigger und Invalidierung.
- [x] Management-Push bei Stopnähe, Zielnähe, schwacher Anschlussbewegung und abgelaufener Haltedauer.
- [x] Einheitliches Schema für wichtige Nachrichten: Fakt, Originalquelle, Zeitpunkt, betroffene Assets, erwarteter Mechanismus, bestätigende Marktreaktion, Gegenargument, Trigger, Invalidierung und Unsicherheit.
- [x] Primärquelle und berichtende Sekundärquelle getrennt speichern und anzeigen.
- [x] Korrektur- und Widerrufsmarker bei der Erfassung erkennen und das News-Trade-Gate blockieren.
- [x] Korrektur-/Widerrufsmonitor: Eine geänderte Quelle bewertet den bestehenden News-Trade neu und löst eine deduplizierte Exit-Prüfung aus; Abruffehler allein invalidieren nicht.
- [x] Telegram-Deduplizierung in QA für Kauf, Verkauf, Management, Kontoübersicht und News vollständig abdecken; fehlgeschlagene Zustellung bleibt wiederholbar.
- [x] Telegram-News kanalübergreifend per stabiler und semantischer Story-ID deduplizieren; nur frische, link-verifizierte Tier-1-/Primärquellen mit Veröffentlichungszeit zulassen und erst nach erfolgreicher Zustellung als gesendet markieren.
- [x] Öffnungs-, Halbzeit- und Schlussbriefings laden Gewinner/Verlierer separat als reproduzierbares 1-Tages-Ranking aus dem überwachten Universum plus Watchlist; bei Provider-Ausfall werden keine Wochen- oder Fantasiewerte eingesetzt.
- [x] Optional planbare Tagesübersicht aktivierbar machen, ohne die ereignisgesteuerten Risiko-Pushes zu verwässern: eigener lokaler Datenpfad, eigene Deduplizierung erst nach erfolgreichem Telegram-Versand und Scheduler-Priorität nach Kauf-/Verkauf-/Risiko-Scans.

Abnahme:

- Keine wichtige Nachricht ohne klickbare echte Quelle und Veröffentlichungszeit.
- Keine identischen Standardbegründungen für unterschiedliche Assets oder entgegengesetzte Richtungen.
- Telegram-Testmatrix deckt normale Zustände, Provider-Ausfälle, Duplikate und Cooldowns ab.

## P1 – Produktoberfläche und Bedienung

Ziel: Alle entscheidenden Funktionen sind mobil und am Desktop ohne versteckte Admin-Wege erreichbar.

- [x] Optionskarte zeigt denselben Kontrakt- und Datenqualitätsblock wie Telegram: Symbol, Richtung, Strike, Verfall, Bid/Ask, Spread, IV, Liquidität, Break-even, maximaler Prämienverlust, Quelle, Zeitstempel und ehrlicher Nicht-verifizierbar-Fallback.
- [x] Paper-Trader zeigt Risikobuckets, quantitative Korrelationsblocker, Assetklassen-Limits, Cashreserve und verbleibende Kapazität direkt an jeder Kandidatenkarte.
- [x] Nachrichtenansicht trennt bestätigte Fakten, Interpretation und offene Unsicherheit als drei gleichzeitig sichtbare Blöcke; Quellenbasis, Publisher/Domain, Veröffentlichungszeit, Link- und Primärquellenstatus, Gegenargument, Bestätigung und Invalidierung bleiben explizit prüfbar.
- [x] Leere, langsame und fehlerhafte Provider-Zustände sind für Dashboard, Analyzer, Markets, Portfolio und Paper-Trader vereinheitlicht; Teil-Ausfälle und lokale Fallbacks bleiben sichtbar und jeder Fehlerpfad hat einen gezielten Retry.
- [x] Accessibility: global sichtbarer Tastaturfokus, Skip-Link, Reduced-Motion, aktive Navigation, semantische Tabs/Statusmeldungen sowie Fokusfang, Escape-Schließen und Fokus-Rückgabe für die kritischen Dialoge sind automatisiert und im Browser geprüft; zentrale Textfarben bestehen den WCAG-AA-Kontrastvertrag.
- [x] Visuelle QA für 390x844, 768x1024, 1366x768 und 1920x1080 automatisieren: Playwright erzeugt je Größe und Hauptansicht Screenshots, prüft Horizontal-Overflow, Browser-/HTTP-Fehler und hält den exakten Viewport-Vertrag in der Release-Suite fest.

Abnahme:

- Kein horizontaler Overflow, kein verdeckter Hauptbutton und kein kritischer Wert nur per Hover.
- Dashboard, Analyzer, Portfolio, Paper Trader, News und Health Center bestehen die definierte Mobile-/Desktop-Testmatrix.

## P1 – Betrieb, Sicherheit und Wiederherstellung

Ziel: Ein Fehler wird erkannt, erklärt und ohne Datenverlust behoben.

- [x] Security Header, Login-Lockout, sichere Cookies und Origin-Regeln sind automatisiert geprüft.
- [x] Health Center prüft Persistenz, Telegram und Hintergrundjobs.
- [x] Strukturierte Fehlercodes und Provider-Metriken für Quote-, News-, Options- und Telegram-Dienste vereinheitlichen: versionierter gemeinsamer Vertrag mit stabiler Fehlertaxonomie, Erfolgs-/Fehlerzählern, Erfolgsquote, Durchschnitts-/P95-Latenz und letztem Fehler im Health Center.
- [x] Automatisches tägliches konsistentes SQLite-Backup mit Retention plus wöchentlicher, nicht-destruktiver Restore-Test auf temporärer leerer Instanz; Health Center zeigt Alter, Fehler und letzten erfolgreichen Drill.
- [x] Deduplizierter Betriebsalarm bei Scheduler-Fehlern, veralteten Kursdaten und nicht beschreibbarem Volume; Telegram-Ausfälle werden als nicht über denselben Kanal zustellbar im Health Center protokolliert. Für echte Out-of-band-Meldung bei komplettem App-/Telegram-Ausfall bleibt ein externer Uptime-Kanal erforderlich.
- [x] Frontend- und Backend-Abhängigkeiten prüfen: `npm audit --audit-level=moderate` und `pip-audit -r requirements.txt` ohne bekannte Schwachstellen; vier gemeldete Frontend-Pakete wurden auf sichere kompatible Versionen aktualisiert.
- [x] Rollback-Runbook mit letztem guten Commit, Datenbankkompatibilität und maximaler Wiederanlaufzeit testen.
- [x] Release-Identität mit Commit, Deployment, Replica, Region, Prozessstart und Laufzeit in Health API und Health Center sichtbar machen; der Live-Smoke-Test kann den erwarteten Commit verbindlich prüfen.

Abnahme:

- Restore-Test stellt Portfolio, Paper-Trades, Outcomes, Einstellungen und Alert-Historie vollständig wieder her.
- Health Center erkennt jeden simulierten P0-Ausfall innerhalb eines Scheduler-Intervalls.
- Rollback auf den letzten guten Release ist ohne Datenverlust dokumentiert und einmal erfolgreich geprobt.

## P2 – Rechtliche und fachliche Produktgrenze

Ziel: Die App behauptet nicht, eine regulierte oder garantierte Anlageberatung zu sein.

- [ ] Nutzungszweck, Datenrisiken, Verzögerungen, Interessenkonflikte und Haftungsgrenzen fachlich prüfen lassen.
- [x] Paper-only, Research und mögliche Echtgeld-Kandidaten technisch und sprachlich strikt trennen.
- [x] Jede Empfehlung und Regeländerung mit Datenstand, Quellen, Version und Nutzeraktion auditierbar speichern.
- [ ] Vor Nutzung für Dritte ein passendes Compliance-/Datenschutzmodell rechtlich prüfen lassen.

Abnahme:

- Kein Echtgeld-Autotrading im Release-Scope.
- Jede entscheidungsrelevante Ausgabe ist mit Version, Zeitpunkt und Quellenstatus reproduzierbar.

## Release-Freeze und finale Abnahme

1. Alle P0-Punkte schließen.
2. P1-Punkte schließen oder mit dokumentierter, nicht sicherheitskritischer Begründung aus dem Release entfernen.
3. Vollständige Backend-QA, Frontend-Build, Dependency-Audit und Live-Smoke-Test grün.
4. Backup und Restore testen.
5. Sieben Tage Produktions-Soak ohne Datenverlust, doppelte Kauf-/Verkaufsmeldung oder unbemerkten Scheduler-Ausfall.
6. Danach Release-Tag setzen und neue Funktionen nur noch über ein priorisiertes Backlog aufnehmen.

## Unmittelbar nächste Arbeitspakete

1. `Paper Evidence Campaign`: ausschließlich echte fällige Outcomes weiterführen, bis jede freizugebende Strategie mindestens 30 geschlossene Trades und die Kampagne mindestens 100 entscheidende Outcomes erreicht.
2. `Production Soak`: denselben identifizierbaren Release sieben Tage ohne kritischen Fehler, Datenverlust, doppelte Kauf-/Verkaufsmeldung oder unbemerkten Scheduler-Ausfall betreiben.
3. `External Uptime`: einen unabhängigen Kanal für kompletten App-/Telegram-Ausfall anbinden und den Alarmweg praktisch testen.
4. `Independent Review`: Nutzungszweck, Datenrisiken, Verzögerungen, Interessenkonflikte und Haftungsgrenzen fachlich prüfen lassen.
5. `Legal/Privacy Review`: vor Nutzung für Dritte Compliance- und Datenschutzmodell rechtlich freigeben lassen.
6. `Release Tag`: erst nach Evidenz, Soak und erforderlichen externen Freigaben den geprüften Commit taggen; neue Funktionen danach ins Backlog verschieben.

## Pflichtprüfung für jeden Abschluss-Commit

```powershell
python -m py_compile api.py src/*.py qa_*.py
python qa_option_contract_alerts.py
python qa_paper_demo_account.py
python qa_paper_learning_alerts.py
python qa_macro_alert_quality.py
python qa_brief_scheduler_delivery.py
python qa_health_center_contract.py
python qa_security_headers.py
python qa_auth_cookie_security.py
python qa_portfolio_persistence.py
Set-Location frontend
npm audit --audit-level=moderate
npm run build
```

Nach Deployment:

- Live-Health und Volume-Persistenz prüfen.
- Login und Session prüfen.
- Paper-Dashboard und Autopilot-Vorschau prüfen.
- Telegram-Test sowie eine deduplizierte Kauf-/Verkaufssimulation prüfen.
- Neues Frontend-Asset und Cache-Header mit `qa_live_release_smoke.py` bestätigen.
