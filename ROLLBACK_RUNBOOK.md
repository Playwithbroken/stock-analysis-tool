# Rollback-Runbook

Dieses Runbook gilt für die Railway-Produktion unter `https://web-production-8546b.up.railway.app`.
Das verbindliche Rollback-Ziel und die RTO stehen in `rollback/last-known-good.json`. Ein Rollback
ist erst abgeschlossen, wenn Anwendung **und** persistente Daten geprüft wurden.

## Auslöser und Verantwortlichkeit

Rollback auslösen, wenn ein Release Login, Portfoliozugriff, Paper-Trading, Alerts oder Datenintegrität
beeinträchtigt und eine sichere Korrektur nicht innerhalb von zehn Minuten möglich ist. Eine Person
führt die Schritte aus, eine zweite prüft Commit, Backup und Smoke-Ergebnis. Keine Datenbank ersetzen,
solange der exakte Pfad `/app/data/portfolios.db` und das Railway-Volume `/app/data` nicht bestätigt sind.

## Vor dem Rollback

1. Störungsbeginn, aktuelle Commit-ID und betroffene Funktionen protokollieren.
2. Schreibzugriffe stoppen beziehungsweise Maintenance-Modus aktivieren.
3. Über den geschützten Backup-Endpunkt ein konsistentes SQLite-Backup erzeugen und dessen
   `quick_check: ok` sowie Datenbankidentität festhalten. Das Backup außerhalb des zu ersetzenden
   Deployments aufbewahren.
4. `python scripts/run_rollback_drill.py` ausführen. Nur bei `status: passed`, identischer
   Datenbankidentität, unveränderten Zeilenzahlen und `within_rto: true` fortfahren.
5. Prüfen, dass der Commit aus `rollback/last-known-good.json` bereits als erfolgreich live verifiziert
   dokumentiert ist.

## Railway-Rollback

1. In Railway den Dienst auf den festgelegten Commit zurücksetzen oder diesen Commit erneut deployen.
   Das bestehende Volume nicht löschen, lösen oder neu anlegen.
2. Deployment- und Startprotokolle auf Migrationen, SQLite-Fehler und fehlende Umgebungsvariablen prüfen.
3. Innerhalb der maximalen RTO von 600 Sekunden ausführen:
   `python qa_live_release_smoke.py https://web-production-8546b.up.railway.app`.
4. Nach Anmeldung Health Center prüfen: `persistence_ready`, `volume_attached`, `database_on_volume`
   und `quick_check` müssen erfolgreich sein. Datenbankidentität und Kern-Zeilenzahlen müssen dem
   Vorher-Protokoll entsprechen.
5. Je einen lesenden Test für Portfolio/Paper-Trades sowie einen kontrollierten Schreib-/Lesetest
   durchführen. Telegram nur mit einem klar als Test markierten Ereignis prüfen.
6. Schreibzugriffe wieder freigeben und Endzeit, tatsächliche Wiederanlaufzeit, Commit, Backup-ID und
   Prüfergebnis protokollieren.

## Abbruch und Wiederherstellung

Bei abweichender Datenbankidentität, fehlenden Tabellen, sinkenden Zeilenzahlen oder fehlendem Volume
sofort abbrechen und den Dienst schreibgeschützt lassen. Das Vorab-Backup nur bei gestopptem Dienst
nach `/app/data/portfolios.db` zurückspielen, neu starten und sämtliche Prüfungen wiederholen. Niemals
eine ältere Datenbankkopie über eine intakte neuere Datenbank schreiben. Wenn das alte Release das
aktuelle Schema nicht öffnen kann, auf dem aktuellen Release bleiben und per korrigiertem Roll-forward
deployen.

## Was der automatisierte Drill beweist

Der Drill verändert weder Railway noch Produktionsdaten. Er exportiert den letzten guten Git-Commit,
erzeugt eine aktuelle Testdatenbank samt Markerdaten, öffnet eine konsistente Kopie mit dem alten
Storage-Code und vergleicht Integrität, Identität, Tabellen und alle Zeilenzahlen. Damit wird die lokale
Datenkompatibilität und technische Wiederanlaufzeit reproduzierbar geprüft. Die tatsächliche Railway-RTO
muss bei jedem realen Einsatz separat gemessen und im Störungsprotokoll festgehalten werden.
