# Broker Freund – Abschlussplan

Stand: 10. August 2026

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
- [ ] Produktionsfähigen Optionsdatenanbieter oder Broker-Quote integrieren. Yahoo-Snapshots bleiben bis dahin verzögerte Research-Daten und niemals Ausführungsfreigabe.
- [ ] Greeks (Delta, Gamma, Theta, Vega) aus Anbieterwerten übernehmen oder mit dokumentiertem Modell berechnen und Quelle/Modell kennzeichnen.
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
- [ ] Portfolio-Korrelation quantitativ mit Renditehistorien messen; statische Buckets bleiben zusätzlicher Sicherheitsgurt.
- [ ] Marktregime beim Einstieg speichern: Trend, Volatilität, Zinsen, Dollar, Risikoappetit und Marktbreite.
- [ ] Slippage und Gebühren je Assetklasse regelmäßig gegen beobachtbare Spreads kalibrieren.
- [ ] Strategieauswertung nach Setup, Marktregime, Quelle, Scoreband und Risikobucket anzeigen.
- [ ] Mindestens 30 geschlossene Trades je freizugebender Strategie und mindestens 100 entscheidende Outcome-Prüfungen sammeln.
- [ ] Eine Strategie nur hochstufen, wenn Trefferquote, Profit Factor, Erwartungswert und Drawdown gleichzeitig die dokumentierten Mindestwerte erfüllen.

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
- [ ] Optional planbare Tagesübersicht aktivierbar machen, ohne die ereignisgesteuerten Risiko-Pushes zu verwässern.

Abnahme:

- Keine wichtige Nachricht ohne klickbare echte Quelle und Veröffentlichungszeit.
- Keine identischen Standardbegründungen für unterschiedliche Assets oder entgegengesetzte Richtungen.
- Telegram-Testmatrix deckt normale Zustände, Provider-Ausfälle, Duplikate und Cooldowns ab.

## P1 – Produktoberfläche und Bedienung

Ziel: Alle entscheidenden Funktionen sind mobil und am Desktop ohne versteckte Admin-Wege erreichbar.

- [ ] Optionskarte zeigt denselben Kontrakt- und Datenqualitätsblock wie Telegram.
- [ ] Paper-Trader zeigt Risikobuckets, Korrelationsblocker und verbleibende Kapazität direkt an jeder Kandidatenkarte.
- [ ] Nachrichtenansicht trennt bestätigte Fakten, Interpretation und offene Unsicherheit visuell.
- [ ] Leere, langsame und fehlerhafte Provider-Zustände für alle Hauptansichten gestalten.
- [ ] Accessibility: Tastaturbedienung, Fokusführung, Kontrast und Screenreader-Bezeichnungen prüfen.
- [ ] Visuelle QA für 390x844, 768x1024, 1366x768 und 1920x1080 automatisieren.

Abnahme:

- Kein horizontaler Overflow, kein verdeckter Hauptbutton und kein kritischer Wert nur per Hover.
- Dashboard, Analyzer, Portfolio, Paper Trader, News und Health Center bestehen die definierte Mobile-/Desktop-Testmatrix.

## P1 – Betrieb, Sicherheit und Wiederherstellung

Ziel: Ein Fehler wird erkannt, erklärt und ohne Datenverlust behoben.

- [x] Security Header, Login-Lockout, sichere Cookies und Origin-Regeln sind automatisiert geprüft.
- [x] Health Center prüft Persistenz, Telegram und Hintergrundjobs.
- [ ] Strukturierte Fehlercodes und Provider-Metriken für Quote-, News-, Options- und Telegram-Dienste vereinheitlichen.
- [ ] Automatisches tägliches Backup plus regelmäßig getesteter Restore auf leerer Instanz.
- [ ] Alarm bei ausgefallenem Scheduler, veralteten Kursdaten, Telegram-Fehlern und nicht beschreibbarem Volume.
- [ ] Abhängigkeiten prüfen und bekannte moderate/hohe Sicherheitslücken vor Release beseitigen oder dokumentiert akzeptieren.
- [ ] Rollback-Runbook mit letztem guten Commit, Datenbankkompatibilität und maximaler Wiederanlaufzeit testen.

Abnahme:

- Restore-Test stellt Portfolio, Paper-Trades, Outcomes, Einstellungen und Alert-Historie vollständig wieder her.
- Health Center erkennt jeden simulierten P0-Ausfall innerhalb eines Scheduler-Intervalls.
- Rollback auf den letzten guten Release ist ohne Datenverlust dokumentiert und einmal erfolgreich geprobt.

## P2 – Rechtliche und fachliche Produktgrenze

Ziel: Die App behauptet nicht, eine regulierte oder garantierte Anlageberatung zu sein.

- [ ] Nutzungszweck, Datenrisiken, Verzögerungen, Interessenkonflikte und Haftungsgrenzen fachlich prüfen lassen.
- [ ] Paper-only, Research und mögliche Echtgeld-Kandidaten technisch und sprachlich strikt trennen.
- [ ] Jede Empfehlung und Regeländerung mit Datenstand, Quellen, Version und Nutzeraktion auditierbar speichern.
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

1. `Options Contract Persistence`: gespeicherten Kontrakt vom Entry bis Exit verwenden.
2. `Options Provider Gate`: Broker-/Marktdatenanbieter auswählen und ausführbare Quote getrennt vom Research-Snapshot anbinden.
3. `Option Management`: P&L, Stop, Ziel und Zeitwert anhand des Kontrakts auswerten.
4. `News Evidence Schema`: Primärquelle, Sekundärquelle, Fakten, Interpretation und Korrekturstatus vereinheitlichen.
5. `Paper Evidence Dashboard`: Regime-, Bucket- und Strategieauswertung mit Mindeststichprobe.
6. `Release Recovery Drill`: Backup, Restore, Scheduler-Ausfall und Rollback praktisch testen.

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
