# Implementierungs-Prompt: Broker Freund – Paper Learning Engine v2

## Rolle und Auftrag

Du arbeitest als Senior Quant Engineer, Portfolio-Risk-Engineer und Full-Stack-Entwickler im bestehenden Projekt **Broker Freund**. Implementiere eine nachvollziehbare, versionierte und statistisch vorsichtige Lern-Engine, die aus echten Paper-Trades und zeitlich fälligen Paper-Outcomes lernt.

Das Ziel ist **kein autonomer Echtgeld-Trader**. Das Ziel ist ein Paper-Depot, das:

1. vor jedem Einstieg den vollständigen Entscheidungskontext unveränderlich speichert,
2. nach jedem Outcome zwischen Ergebnisqualität und Entscheidungsqualität unterscheidet,
3. wiederkehrende Fehler und funktionierende Bedingungen erkennt,
4. daraus überprüfbare Lernhypothesen erzeugt,
5. neue Regeln zuerst im Shadow-/Champion-Challenger-Modus testet,
6. Paper-Scores, Paper-Gates und Paper-Positionsgrößen nur bei ausreichender Evidenz vorsichtig anpasst,
7. jede Änderung erklärt, versioniert, auditierbar macht und zurückrollen kann.

Implementiere vollständig, teste proportional zum Risiko und dokumentiere das Ergebnis. Höre nicht nach einer reinen Analyse oder einem Plan auf.

## Bestehenden Stand zuerst respektieren

Lies vor Änderungen mindestens:

- `README.md`
- `APP_COMPLETION_PLAN.md`
- `src/paper_trading_service.py`
- `src/strategy_library.py`
- `src/forecast_learning_service.py`
- `src/trading_intelligence_service.py`
- `src/storage.py`
- `src/decision_scope.py`
- `src/compliance_gate.py`
- `api.py`
- `frontend/src/components/PaperTradingPanel.tsx`
- `frontend/src/components/LearningBoardPanel.tsx`
- die vorhandenen `qa_paper_*`, `qa_decision_*` und `qa_compliance_*`-Verträge

Erweitere vorhandene Strukturen, statt parallele inkompatible Systeme zu bauen. Bewahre bestehende Paper-Trades, Outcomes, Audit-Logs, Risikogates, Scheduler, Backups und Telegram-Verträge. Ändere keine bestehenden Daten destruktiv.

## Nicht verhandelbare Sicherheitsgrenzen

- Keine Brokerorder und keine automatische Echtgeld-Ausführung.
- `real_money_execution_allowed` und `automatic_execution_allowed` bleiben immer `false`.
- Das Lernen darf ausschließlich Paper-Scoring, Paper-Auswahl, Paper-Gates und Paper-Risikomultiplikatoren beeinflussen.
- Kein Modell darf Cash-, Exposure-, Positions-, Korrelations-, Optionsprämien-, Verlustserien-, Tagesverlust- oder Drawdown-Limits lockern.
- Harte Risiko-, Datenqualitäts-, Liquiditäts-, Compliance- und Quellen-Gates können durch Lernen niemals überschrieben werden.
- Keine simulierten Insiderdaten, erfundenen Peers, pauschalen Benchmarkwerte, zufälligen Handelsgründe oder sonstige Mock-Daten in entscheidungsrelevanten Pfaden.
- Fehlende Daten bleiben fehlend und blockieren gegebenenfalls den Paper-Einstieg. Nie schätzen, um ein Gate zu bestehen.
- Keine rückdatierten, synthetischen oder vorzeitig ausgewerteten Outcomes.
- Keine Nutzung zukünftiger Informationen, kein Look-ahead, kein Survivorship-Bias und keine nachträgliche Veränderung eines Entry-Snapshots.
- Ein profitabler Trade ist nicht automatisch eine gute Entscheidung. Ein Verlust ist nicht automatisch eine schlechte Entscheidung.
- Jede Lernregel benötigt Begründung, Datenbasis, Stichprobe, Unsicherheit, Version, Aktivierungsstatus und Rollback.

## Professioneller Investmentprozess als fachliche Grundlage

Baue den Prozess in dieser Reihenfolge auf:

1. **Mandat und Constraints:** Ziel, Horizont, Risikotoleranz, Verlusttragfähigkeit, Liquidität, maximale Positionsgröße, maximaler Drawdown, erlaubte Assetklassen und ausgeschlossene Produkte.
2. **Research und Signalbildung:** Mehrere unabhängige, messbare Signalfamilien statt eines Einzelindikators.
3. **Portfoliokontext:** Konzentration, Korrelation, Faktor-, Sektor-, Länder-, Währungs- und Makroexposure.
4. **Trade-Konstruktion:** Trigger, Limit/Referenzquote, Stop, Ziel, Haltedauer, Invalidierung, erwartete Kosten und maximales Risiko.
5. **Ausführungssimulation:** Bid/Ask, Spread, Slippage, Gebühren, Liquidität und Datenalter.
6. **Monitoring und Exit:** These, Stop, Ziel, Zeitablauf und geänderte Fakten separat überwachen.
7. **Attribution und Feedback:** Ergebnis gegen ursprünglichen Plan messen und nur langfristig belastbare Änderungen zulassen.

Die Engine darf Signale nicht als Wahrheiten behandeln. Sie sind Hypothesen mit Unsicherheit.

## Zulässige Signalfamilien

Jedes Signal braucht exakte Definition, Quelle, Zeitstempel, Datenalter und Verfügbarkeit. Verwende nur tatsächlich vorhandene oder sauber integrierte Daten.

### Übergreifend

- absolute und relative Trend-/Momentum-Maße über definierte Horizonte,
- Marktbreite und Benchmark-relative Stärke,
- realisierte Volatilität, ATR/Stopdistanz und Volatilitätsregime,
- Liquidität, durchschnittliches Handelsnotional, Spread und Datenalter,
- Zinsen, Dollar, Risikoappetit und Marktregime nur mit dokumentierten Proxys,
- Katalysator, Primärquelle, Veröffentlichungszeit und bestätigende Marktreaktion,
- Portfoliofit, Korrelation und bereits vorhandenes Risikofaktor-Exposure.

### Aktien

- Qualität: Profitabilität, Verschuldung und Stabilität der Ergebnisse,
- Bewertung sektoral/peer-relativ statt mit pauschalen globalen Grenzwerten,
- Wachstum und Ergebnisentwicklung,
- Earnings/Guidance, Revisionen und Überraschungen nur aus verifizierbaren Daten,
- Preis-/Volumenbestätigung,
- Corporate-Action- und Earnings-Risiko,
- Insiderdaten ausschließlich aus echten Filings mit Transaktionstyp und Zeitstempel.

### ETFs

- Index/Exposure, Assetklasse, Region, Sektor und Faktorprofil,
- TER, Fondsgröße, Fondsdomizil, Replikationsart und Ausschüttungsart, soweit verifiziert verfügbar,
- Tracking Difference/Tracking Error nur mit ausreichender Historie,
- Handelsvolumen, Spread und handelbarer Börsenplatz,
- Holdings-Overlap und Konzentration,
- Währungs- und gegebenenfalls Hedging-Exposure,
- Vergleich nur gegen fachlich passenden Benchmark oder echte Alternativen.

### Krypto

- Börse und konkretes Handelspaar als Teil der Instrumentidentität,
- 24/7-Datenfrische und Wochenend-/Liquiditätsregime,
- Spread, Orderbuchtiefe beziehungsweise belastbarer Liquiditätsproxy,
- Trend, Momentum, Volatilität und Volumen,
- Basis/Funding/Open Interest nur bei verifizierter Quelle und korrekter Produktzuordnung,
- Exchange-, Stablecoin-, Custody-, Manipulations- und Gap/Flash-Crash-Risiko,
- On-Chain-Daten höchstens als eigener verifizierter Research-Layer; nie als erfundener Fallback.

## Modul 1: Unveränderlicher Entry Feature Snapshot

Erweitere jedes Paper-Trade-Ticket um ein versioniertes Objekt `learning_feature_snapshot`. Speichere mindestens:

- Schema- und Feature-Version,
- Trade-, Strategie- und Setup-ID,
- Assetklasse, Instrumentidentität, Richtung und Zeithorizont,
- Signal-Score vor Lernanpassung,
- jede einzelne Score-Komponente mit Wert, Quelle und Verfügbarkeit,
- angewendete Lernregel-Versionen und Score-Deltas,
- Marktregime mit allen verfügbaren Dimensionen,
- Benchmark und relative Stärke,
- Volatilität, Liquidität, Spread und Datenalter,
- News-/Katalysator-Evidenz,
- Portfoliokontext und Korrelationsbucket,
- geplanten Entry, Stop, Ziel, Chance-Risiko-Verhältnis und maximales Risiko,
- erwartete Gebühren/Slippage,
- verwendete Datenquellen und Zeitstempel,
- explizite Missing-Data-Flags,
- vollständige Gate-Entscheidung und Blockgründe.

Der Snapshot wird nach dem Entry niemals mutiert. Spätere Daten werden separat gespeichert.

## Modul 2: Outcome- und Trade-Attribution

Erweitere die Auswertung fälliger Outcomes und geschlossener Trades. Berechne, soweit mit echten historischen Zwischenständen möglich:

- realisierte Netto-P&L und Netto-P&L-Prozent,
- R-Multiple bezogen auf das ursprüngliche Risiko,
- Maximum Favorable Excursion (MFE),
- Maximum Adverse Excursion (MAE),
- Haltedauer,
- Ausführungskosten und Kostenanteil am Bruttoergebnis,
- Benchmarkrendite und aktive Rendite im identischen Zeitfenster,
- Ergebnis relativ zum ursprünglich geplanten Ziel/Stop,
- ob These, Trigger, Invalidierung und Zeitplan eingehalten wurden.

Erzeuge zwei getrennte Bewertungen:

### A. Outcome Quality

- profitabel / verlustreich / neutral,
- Ziel erreicht / Stop erreicht / Zeitablauf / manueller Exit,
- absolute und benchmark-relative Performance,
- Drawdown- und Kostenwirkung.

### B. Process Quality

- `good_process_good_outcome`,
- `good_process_bad_outcome`,
- `bad_process_good_outcome`,
- `bad_process_bad_outcome`,
- `insufficient_evidence`.

Eine gute Prozessqualität verlangt mindestens: vollständige Daten, gültiges Gate, dokumentierte These, Trigger, Stop, Ziel, Invalidierung, regelkonforme Positionsgröße und keine nachträgliche Regelverletzung.

## Modul 3: Erweiterte Fehler-Taxonomie

Ersetze zu grobe Pauschalkategorien nicht ersatzlos, sondern ergänze eine hierarchische, deterministische Taxonomie:

- `data_quality.*`
- `signal.false_positive`
- `signal.no_follow_through`
- `signal.late_entry`
- `signal.early_entry`
- `regime.mismatch`
- `benchmark.relative_weakness`
- `liquidity.spread_too_wide`
- `liquidity.slippage_dominated`
- `risk.position_too_large`
- `risk.stop_inside_normal_volatility`
- `risk.correlation_cluster`
- `exit.profit_not_protected`
- `exit.time_stop_too_long`
- `exit.premature`
- `news.unconfirmed`
- `news.reaction_faded`
- `option.timing_or_decay`
- `crypto.weekend_liquidity`
- `crypto.exchange_specific_dislocation`
- `etf.tracking_or_exposure_mismatch`
- `process.rule_violation`
- `unclassified`

Speichere primäre und optionale sekundäre Fehlerursachen, Evidenzfelder und Konfidenz. Behaupte keine Kausalität, wenn nur Korrelation vorliegt.

## Modul 4: Lernsegmente und statistische Auswertung

Gruppiere Ergebnisse mindestens nach:

- Strategie,
- Setup-Typ,
- Assetklasse,
- Richtung,
- Marktregime,
- Volatilitätsregime,
- Quelle/Quellentyp,
- Scoreband,
- Liquiditätsband,
- Haltedauer,
- Tages-/Sessionkontext,
- News-basiert versus nicht News-basiert.

Berechne je Segment:

- Stichprobe und entscheidende Stichprobe,
- Trefferquote mit Unsicherheitsintervall statt nur Punktwert,
- durchschnittlichen Gewinn und Verlust,
- Netto-Erwartungswert,
- Profit Factor,
- R-Multiple-Verteilung,
- maximalen Drawdown,
- MFE/MAE,
- Kostenanteil,
- Regimekonzentration,
- Anteil guter/schlechter Prozesse.

Verwende bei kleinen Stichproben Shrinkage oder ein transparentes Beta-Binomial-/Wilson-Verfahren. Zeige Rohwert und vorsichtig geschätzten Wert. Kleine Stichproben dürfen nie als starke Edge dargestellt werden.

## Modul 5: Lernhypothesen statt unkontrollierter Selbständerung

Erzeuge nur dann eine strukturierte Hypothese, wenn ein wiederkehrendes Muster vorliegt. Beispiel:

```json
{
  "hypothesis": "News-Long-Setups ohne Volumenbestätigung zeigen zu wenig Follow-through.",
  "segment": {"setup_type": "news_long", "volume_confirmation": false},
  "sample_size": 18,
  "decisive": 14,
  "observed_hit_rate": 21.4,
  "expected_effect": "Weniger Fehltrades und kleinerer Drawdown",
  "proposed_rule": "Require relative_volume >= 1.4 when available",
  "status": "proposed",
  "uncertainty": "medium"
}
```

Jede Hypothese benötigt:

- betroffene Strategie und Segmentdefinition,
- Datenbasis und exakte Trade-/Outcome-IDs,
- beobachtete Kennzahlen,
- Alternativerklärung und Unsicherheit,
- vorgeschlagene Paper-Regel,
- erwartete Wirkung,
- mögliche Nachteile,
- Mindeststichprobe für den Test,
- Erstellungs- und Ablaufdatum.

## Modul 6: Champion-Challenger-/Shadow-System

Neue Regeln werden nicht direkt produktiv. Implementiere:

- `champion`: aktuell aktive Paper-Regel,
- `challenger`: vorgeschlagene Regel,
- `shadow`: bewertet neue Kandidaten, beeinflusst aber weder Auswahl noch Positionsgröße,
- chronologische Zuordnung neuer Signale,
- unveränderliche Experimentversion,
- Vergleich auf zukünftigen Daten,
- keine rückwirkende Optimierung des Challengers,
- getrennte Trainings- und Evaluierungsfenster,
- Embargo/Purge bei überlappenden Trades oder Horizonten,
- Abbruch bei Datenfehlern oder Regelverletzungen.

Vergleiche mindestens Netto-Erwartungswert, Profit Factor, Drawdown, Verlustserie, Kosten, Process Quality und Stichprobe.

## Modul 7: Evidenz- und Promotion-Gates

Bewahre das bestehende Mindestziel von mindestens 30 geschlossenen Trades je freizugebender Strategie und mindestens 100 entscheidenden Outcomes global. Eine Promotion benötigt zusätzlich:

- positive Netto-Erwartung,
- Profit Factor mindestens gemäß vorhandener Strategiedefinition, grundsätzlich nicht unter 1,20,
- Drawdown innerhalb der vorhandenen Strategielimits,
- keine unvertretbare Konzentration auf ein einzelnes Marktregime oder Instrument,
- keine offenen Datenintegritätsprobleme,
- keine Verschlechterung der Process Quality,
- ausreichend zukünftige Shadow-/Challenger-Beobachtungen,
- dokumentierte Unsicherheit und bestandenes Holdout-/Walk-forward-Gate.

Regelaktionen:

- unter 8 entscheidenden Beobachtungen: nur sammeln, keine Scoreänderung,
- bei früher negativer Evidenz: höchstens Paper-Risiko reduzieren oder stärkere Bestätigung verlangen,
- bei belastbar negativer Evidenz: Paper-Setup pausieren/blockieren,
- bei belastbar positiver Evidenz: Score nur begrenzt erhöhen; Risikohardcaps niemals erhöhen,
- keine einzelne Regeländerung darf den Score um mehr als einen konfigurierbaren, konservativen Maximalwert verändern,
- gleichzeitig aktive Lernanpassungen benötigen ein Gesamt-Cap.

Nutze bestehende Strategie-Gates, aber zentralisiere die Lernpolicy so, dass Schwellen nicht widersprüchlich an mehreren Stellen verstreut sind.

## Modul 8: Versionierte Regelverwaltung und Rollback

Ergänze migrationssicher geeignete Tabellen oder persistente Strukturen für:

- Feature-Snapshots beziehungsweise deren indexierbare Kerndimensionen,
- Lernhypothesen,
- Lernregel-Versionen,
- Champion-Challenger-Experimente,
- Regelentscheidungen und Freigaben,
- Lern-Audit-Events.

Anforderungen:

- additive SQLite-Migrationen,
- sichere Defaults für vorhandene Datensätze,
- Backup/Restore-Kompatibilität,
- Aktivieren, pausieren, ablehnen und zurückrollen,
- unveränderliche Verbindung von Regelversion zu allen betroffenen Paper-Entscheidungen,
- vollständiger Decision-Audit-Eintrag bei jeder Statusänderung.

## Modul 9: API und Scheduler

Erweitere vorhandene APIs oder ergänze klar benannte Endpunkte für:

- Learning-v2-Dashboard,
- Segmentmetriken,
- Trade-/Outcome-Attribution,
- Hypothesenliste und Detail,
- Experimente und Champion-Challenger-Vergleich,
- Regelhistorie und Rollback-Vorschau,
- rein manuelle Freigabe einer ausreichend geprüften Paper-Regel.

Der vorhandene Scheduler soll:

1. nur fällige Outcomes evaluieren,
2. geschlossene Trades attribuieren,
3. Segmentmetriken aktualisieren,
4. neue Hypothesen dedupliziert erzeugen,
5. laufende Shadow-Experimente auswerten,
6. niemals selbst eine Echtgeldfähigkeit oder Brokerorder freischalten.

Jobs müssen idempotent, beobachtbar und nach Fehlern wiederholbar sein. Health Center um letzten Lauf, Alter, Fehler, verarbeitete Outcomes und offene Lernblocker ergänzen.

## Modul 10: Benutzeroberfläche

Baue eine ruhige, verständliche Lernansicht mit:

### Überblick

- Was hat das Paper-Depot bisher gelernt?
- Welche Regeln funktionieren möglicherweise?
- Welche Regeln funktionieren wahrscheinlich nicht?
- Wo ist die Stichprobe noch zu klein?
- Was ist der aktuell größte wiederkehrende Fehler?
- Welche Strategie sammelt als Nächstes Evidenz?

### Pro Trade

- ursprünglicher Plan,
- tatsächlicher Verlauf,
- Outcome Quality,
- Process Quality,
- primäre/sekundäre Fehlerursache,
- MFE, MAE, R-Multiple und Kosten,
- welche aktive Regel den Trade beeinflusst hat,
- was beim nächsten vergleichbaren Paper-Setup anders geprüft wird.

### Regel-Labor

- Champion gegen Challenger,
- Trainings- und zukünftige Shadow-Stichprobe,
- Kennzahlen mit Unsicherheit,
- Status `proposed`, `shadow`, `eligible_for_paper_review`, `active_paper`, `paused`, `rejected`; Rollbacks als auditierte Historienereignisse,
- laufender Monitor aktiver Paper-Regeln mit Rolling Window, Erwartungswert, Profit Factor, Drawdown und Verlustserie,
- automatische Paper-Pause bei klar definierten Kill-Switch-Schwellen,
- nach einer automatischen Sicherheitspause keine direkte Reaktivierung per Rollback, sondern eine neue Shadow-Version,
- klare Warnung: ausschließlich Paper-Lernen, keine Echtgeldfreigabe.

Keine reine Prozentanzeige ohne Stichprobe und Unsicherheit. Keine Formulierung wie „KI hat bewiesen“, wenn nur ein vorläufiges Muster vorliegt.

## Modul 11: Ausführungssimulation wie ein professioneller Prozess

- Verwende die bestehende konservative Kostenkalibrierung.
- Speichere Referenzkurs, simulierten Fill, Spread, Slippage, Gebühren und Datenalter getrennt.
- Modellierte Limit-Ausführung darf nicht als garantiert gefüllt gelten.
- Miss, ob ein vermeintlicher Edge nach Kosten bestehen bleibt.
- Kennzeichne Trades, deren Ergebnis überwiegend durch unrealistisch günstige Ausführung entstehen würde.
- Berücksichtige bei Krypto 24/7-, Wochenend- und Exchange-Kontext.
- Berücksichtige bei ETFs Spread, Handelsplatz, Fonds-/Underlying-Liquidität und NAV-/Tracking-Kontext, soweit Daten vorhanden sind.

## Modul 12: Backtest- und Overfitting-Schutz

Wenn historische Simulation ergänzt oder verwendet wird:

- chronologische Splits statt zufälliger Zeilenmischung,
- Walk-forward-Auswertung,
- Purging/Embargo bei überlappenden Labels,
- Transaktionskosten und Slippage,
- Corporate Actions,
- passender Benchmark,
- Zahl getesteter Varianten protokollieren,
- keine Auswahl nur nach maximaler Sharpe Ratio,
- Deflated Sharpe Ratio oder gleichwertige transparente Multiple-Testing-Korrektur vorsehen,
- Backtest, Paper-Shadow und Live-Paper strikt getrennt berichten.

Ein gutes Backtestergebnis darf niemals fehlende echte Paper-Evidenz ersetzen.

## QA-Pflichten

Erstelle mindestens folgende neue Verträge:

1. Entry-Snapshot ist vollständig, versioniert und nach Entry unveränderlich.
2. Fehlende Daten blockieren statt positive Defaultwerte zu erzeugen.
3. Outcome wird niemals vor `due_at` ausgewertet.
4. Derselbe Outcome wird bei wiederholtem Schedulerlauf nicht doppelt gezählt.
5. Outcome Quality und Process Quality können bewusst unterschiedliche Bewertungen liefern.
6. Kleine Stichprobe erzeugt keine Promotion und keinen positiven Score-Boost.
7. Negative frühe Evidenz kann Paper-Risiko reduzieren, aber keine Hardcaps verändern.
8. Champion und Challenger verwenden nur Daten nach Experimentstart.
9. Purge/Embargo verhindert überlappende Leakage-Fälle.
10. Promotion verlangt alle Evidenz-, Performance-, Drawdown- und Datenintegritäts-Gates.
11. Rollback stellt exakt die vorherige Paper-Regelversion wieder her.
12. Jede Regeländerung erzeugt einen Decision-Audit-Eintrag.
13. Vier aufeinanderfolgende Verluste einer aktiven Paper-Regel lösen den Paper-Kill-Switch aus.
14. Ein automatisch pausierter Challenger kann nicht direkt wieder aktiviert werden.
15. Die erneute Validierung beginnt als neue Regelversion mit neuer Shadow-Zeitgrenze.
16. Lernstatistiken trennen mindestens Setup, Assetklasse, Richtung, Trend- und Volatilitätsregime.
17. Ein unbekanntes Entry-Regime darf keine neue Lernregel erzeugen oder eine regimespezifische Regel anwenden.
18. Eine aktive regimespezifische Regel beeinflusst ausschließlich Paper-Setups im exakt passenden Entry-Regime.
19. Relative Rendite wird nur aus einem am Entry gespeicherten und am Outcome erneut gemessenen Benchmarkkurs berechnet.
20. Fehlende Benchmarkdaten bleiben `unavailable`; pauschale oder erfundene Marktrenditen sind verboten.
21. Optionsrenditen erhalten ohne belastbare Delta-/Underlying-Normalisierung kein scheinpräzises Alpha.
13. Keine Lernregel kann Real-Money- oder Automatic-Execution-Flags aktivieren.
14. Aktien-, ETF- und Krypto-Snapshots besitzen korrekte assetklassenspezifische Felder und Missing-Data-Flags.
15. Keine API-Antwort aus dem Lern-/Entscheidungspfad enthält simulierte Insider-, Peer-, Benchmark- oder zufällige Handelsgründe.
16. Backup-/Restore-Vertrag umfasst neue Lernstrukturen.
17. UI zeigt Stichprobe, Unsicherheit, Regelversion und Paper-only-Status.
18. Bestehende QA-Verträge bleiben grün.

Nutze deterministische Fixtures. Erzeuge keine synthetischen Erfolge, um Readiness zu erreichen.

## Akzeptanzkriterien

Die Arbeit ist erst abgeschlossen, wenn:

- jeder neue Paper-Trade einen unveränderlichen Feature-Snapshot besitzt,
- jeder fällige Outcome nachvollziehbar attribuiert wird,
- Prozess und Ergebnis getrennt bewertet werden,
- Lernhypothesen vollständig belegt und dedupliziert sind,
- neue Regeln zuerst als zukünftige Shadow-Experimente laufen,
- kleine Stichproben keine aggressiven Anpassungen auslösen,
- Regelaktivierung und Rollback auditierbar sind,
- das Dashboard verständlich zeigt, was gelernt wurde und was noch unsicher ist,
- alle Lernwirkungen Paper-only bleiben,
- keine bestehenden Risiko- oder Compliance-Gates abgeschwächt wurden,
- Backend-QA, Frontend-Tests und Produktionsbuild grün sind.

## Pflichtprüfung

Führe mindestens aus:

```powershell
python -m py_compile api.py src/*.py qa_*.py
python qa_paper_demo_account.py
python qa_paper_learning_alerts.py
python qa_paper_evidence_campaign.py
python qa_paper_loss_streak_recovery.py
python qa_decision_audit.py
python qa_decision_scope_contract.py
python qa_compliance_release_gate.py
python qa_backup_restore_recovery.py
python qa_health_center_contract.py
cd frontend
npm run test
npm run build
```

Ergänze die neuen Learning-v2-QA-Dateien in die Release-Contracts und in die relevante Projektdokumentation.

## Erwartete Abschlussmeldung

Berichte am Ende knapp und evidenzbasiert:

- was implementiert wurde,
- welche Dateien und Datenstrukturen geändert wurden,
- wie die Lernschleife jetzt funktioniert,
- welche Paper-Anpassungen erlaubt beziehungsweise ausdrücklich verboten sind,
- welche QA- und Build-Prüfungen bestanden wurden,
- welche reale Evidenz noch fehlt,
- welche bekannten Grenzen bestehen.

Behaupte niemals, die Strategie sei profitabel oder für Echtgeld geeignet, wenn die echte zukünftige Paper-Stichprobe das nicht belegt.

## Fachliche Quellenbasis

Nutze diese Quellen als konzeptionelle Leitplanken, nicht als Garantie zukünftiger Renditen:

- CFA Institute, Portfolio Management Process und Investment Policy Statement: https://www.cfainstitute.org/sites/default/files/-/media/documents/article/refresher-readings-free/rr-2018-l2v6r47.pdf
- CFA Institute, Suitability im Kontext des Gesamtportfolios: https://www.cfainstitute.org/standards/professionals/code-ethics-standards/standards-of-practice-iii-c
- MSCI, Foundations of Factor Investing: https://www.msci.com/research-and-insights/paper/foundations-of-factor-investing
- Asness, Moskowitz und Pedersen, Value and Momentum Everywhere: https://w4.stern.nyu.edu/facdir/lpederse/papers/ValMomEverywhere.pdf
- Moskowitz, Ooi und Pedersen, Time Series Momentum / Forschungsdaten: https://www.aqr.com/Insights/Datasets/Time-Series-Momentum-Original-Paper-Data
- Bailey und López de Prado, Deflated Sharpe Ratio: https://doi.org/10.2139/ssrn.2460551
- Bailey, Borwein, López de Prado und Zhu, Probability of Backtest Overfitting: https://carmamaths.org/resources/jon/backtest2.pdf
- SEC, Trading Basics und Ordertypen: https://www.sec.gov/tm/investor-alerts-bulletins/trading101basics.pdf
- CFTC, Risiken des Handels mit virtuellen Währungen: https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/understand_risks_of_virtual_currency.html
- ESMA/AMIC ETF Working Group, ETF-Auswahl-, Liquiditäts- und Trackingaspekte: https://www.esma.europa.eu/sites/default/files/AMIC_ETF_WG___ESMA_response_FINAL_1.pdf
