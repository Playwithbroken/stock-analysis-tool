# Fach-, Compliance- und Datenschutz-Reviewpaket

Stand: 19. August 2026 · Produktversion: 0.9.0-beta.1 · Status: **externe Prüfung ausstehend**

Dieses Dokument ist eine technische und organisatorische Prüfbasis, keine Rechtsberatung und keine
regulatorische Freigabe. Die offenen Punkte im `APP_COMPLETION_PLAN.md` dürfen erst nach einer echten,
dokumentierten Prüfung durch qualifizierte Personen geschlossen werden.

## 1. Geplanter Nutzungszweck und harte Scope-Grenze

Aktuell freigegeben ist ausschließlich ein privater Einzelarbeitsbereich für Research, Paper-Trading und
Lernmessung. Es gibt keine Brokeranbindung, keine Echtgeldorder, keine automatische Echtgeldausführung
und keine Gewinnzusage. Research, Paper-only und ein möglicher manueller Echtgeld-Prüfkandidat sind im
Backend über `decision-scope.v1` getrennt. Der letzte Status bedeutet ausdrücklich keine Orderfreigabe.

Eine Nutzung durch Dritte, ein öffentlicher Zugang, Verkauf, Beratung für Kunden oder Multi-User-Betrieb
ist technisch blockiert, solange das externe Freigabe-Gate nicht vollständig dokumentiert ist. Der
Disclaimer allein ist keine ausreichende Abgrenzung: Entscheidend sind Funktion, Personalisierung,
konkretes Instrument und tatsächliche Kommunikation.

## 2. Regulatorische Fragen für die externe Prüfung

| Thema | Warum relevant | Vom Reviewer verbindlich zu klären |
|---|---|---|
| Anlageberatung / Erlaubnis | Die App verarbeitet Portfolio-, Risiko- und Profildaten und nennt konkrete Instrumente. | Ob einzelne Flows bereits persönliche Empfehlungen darstellen; zulässiger Nutzerkreis; erforderliche Erlaubnis/Registrierung; verbotene Sprache und Funktionen. |
| MiFID-II-Geeignetheit | Bei Anlageberatung sind Kenntnisse/Erfahrung, finanzielle Situation, Verlusttragfähigkeit, Ziele und Risikotoleranz relevant. | Ob das bestehende Profil genügt, welche Pflichtangaben/Erklärungen/Aufzeichnungen nötig wären und ob Advice vollständig ausgeschlossen bleiben muss. |
| MAR / öffentliche Empfehlungen | Öffentliche Kauf-/Verkaufsideen oder Preismeinungen können Investment Recommendations sein. | Pflichten zu Urheber, Zeitpunkt, Methodik, Fakten/Meinungen, Quellen, Interessenkonflikten, Aktualisierung und Korrektur; Anwendbarkeit auf Telegram. |
| Kryptowerte und Derivate | Crypto, Optionen und Hebelprodukte können eigene Erlaubnis-, Produkt- und Risikopflichten auslösen. | Zulässige Darstellung je Instrument, Zielmarkt-/Angemessenheitsfragen, Verlustwarnungen und ausgeschlossene Produktarten. |
| Datenschutz / Profiling | Portfolio, Finanzlage, Risikotoleranz, Journal, Telegram-Kennung und Audit-Nutzeraktionen können personenbezogen sein. | Rechtsgrundlagen, Rollen, Informationspflichten, Auftragsverarbeitung, Drittlandtransfers, Betroffenenrechte, Löschung, Aufbewahrung und gegebenenfalls DSFA. |
| Automatisierte Entscheidungen | Ranking, Scoring und Profiling beeinflussen finanzielle Entscheidungen. | Ob DSGVO Art. 22 greift oder andere Transparenz-/Widerspruchs-/Human-review-Pflichten entstehen. |
| Haftung und Werbung | Falsche, verspätete oder missverständliche Signale können finanzielle Schäden verursachen. | Zulässige Haftungsbegrenzung, Pflichtwarnungen, Werbeaussagen, Nachweis- und Beschwerdeprozess. |

## 3. Dateninventar und Datenfluss

| Datenkategorie | Beispiele | Speicher/Empfänger | Hauptrisiko | Vor Drittfreigabe |
|---|---|---|---|---|
| Profil und Eignung | Name, E-Mail, Zeitzone, Ziele, Erfahrung, Verlusttragfähigkeit | SQLite/Railway | Finanzprofil, falsche Personalisierung | Rechtsgrundlage, Pflichtfelder, Export/Löschung, Zugriffskonzept |
| Portfolio | Ticker, Stückzahl, Kaufpreis, Kaufdatum | SQLite, Kursanbieter über Ticker | Vermögensrückschluss | Minimierung, Verschlüsselung/Secrets, Retention |
| Paper-Trading | Trades, Hebel, P&L, Journal, Fehlergründe | SQLite, Telegram bei Alerts | Verhaltensprofil, Fehlinterpretation als Echtgeld | klare Kennzeichnung, Löschfrist, Empfängerprüfung |
| Kommunikation | Telegram Chat-ID, Zustellung, Browser-Push | Telegram/Push-Anbieter | externer Empfänger, Metadaten/Drittland | AVV/Rollen/Transfer, Einwilligung bzw. Rechtsgrundlage |
| Audit | Empfehlung, Datenstand, Quellen, Version, Nutzeraktion, Hash-Kette | SQLite/Backup | lange Aufbewahrung, Personenbezug | Zweck, Zugriff, Retention, Auskunft/Löschkonzept und regulatorische Aufbewahrung abgleichen |
| Markt-/Newsdaten | Kurse, Filings, Headlines, Quellenlinks | externe Provider, Cache | Lizenz, Verzögerung, Fehler/Korrektur | Providerbedingungen, Anzeige-/Speicherrechte, SLA und Korrekturprozess |

Provider und Rollen müssen konkret je Produktionskonfiguration erfasst werden. Dazu gehören mindestens
Railway, Telegram, Kurs-/Newsanbieter, Optionsanbieter und gegebenenfalls E-Mail/Push. API-Schlüssel und
Chat-IDs dürfen nicht in Audit-Payloads, Client-Bundles oder Support-Exports gelangen.

## 4. Fachliche Risikomatrix

| Risiko | Bestehende Kontrolle | Restrisiko / Reviewer-Entscheidung |
|---|---|---|
| Veraltete oder nicht ausführbare Kurse | Datenstand, Providerstatus, Delayed-/Research-Kennzeichnung, Entry-Gates | maximale zulässige Verzögerung je Asset/Session; Verhalten bei Marktunterbrechung |
| Falsche oder korrigierte News | Primär-/Sekundärquelle, Fakten/Interpretation getrennt, Korrekturstatus, Revalidierung | verbindliche Quellenhierarchie und menschliche Eskalation bei High-impact-News |
| Scheinkausalität | Preisbestätigung und Hinweis „kein Kausalitätsbeweis“ | zulässige Sprache für Impact-/Richtungsaussagen |
| Interessenkonflikte | derzeit keine monetären Interessen modelliert | Betreiberpositionen, Affiliate-/Providervergütung, bezahlte Inhalte und Auswahlbias offenlegen |
| Übervertrauen in Scores | Paper-only, Mindeststichprobe, Audit, keine automatische Echtgeldfreigabe | Grenzen der Kennzahlen, Out-of-sample-Prüfung, Modelländerungsfreigabe |
| Hebel-/Optionsverlust | definierter Maximalverlust, Produktdaten-Gates, Paper-only | Produktverbote, Zielmarkt, Totalverlustrisiko und verständliche Darstellung |
| Telegram-Kontextverlust | Quellen-, Zeit-, Risiko- und Modusfelder, Deduplizierung | Mindestinhalt jeder Nachricht und Umgang mit Weiterleitung/Screenshots |
| Ausfall/Datenverlust | Health Center, Alarmierung, Backup/Restore, Rollback | externe Uptime-Meldung, Incident-/Breach-Prozess und Meldefristen |

## 5. Interessenkonflikt-Erklärung – auszufüllen

- Betreiber hält/handelt erwähnte Instrumente: `offen`
- Vergütung, Affiliate- oder Referral-Beziehungen: `offen`
- Bezahlte Daten, Emittenten- oder Brokerbeziehungen: `offen`
- Methodischer Bias durch Datenanbieter/Universum: `vorhanden; konkret bewerten`
- Verfahren zur Offenlegung pro Empfehlung: `extern freizugeben`
- Verantwortliche Person für Aktualisierung/Korrektur: `offen`

## 6. Pflichtnachweise vor Drittfreigabe

1. Schriftliche rechtliche Einordnung des konkreten Funktionsumfangs und Nutzerkreises.
2. Fachreview von Zweck, Datenrisiken, Verzögerungen, Konflikten, Modellgrenzen und Haftungstexten.
3. Benannter Verantwortlicher/Data Controller, Datenschutzhinweise, Rechtsgrundlagen und Verzeichnis der Verarbeitungstätigkeiten.
4. Verträge/Rollen/Transfers aller Anbieter; Lösch-, Export-, Auskunfts- und Incident-Prozess getestet.
5. Freigegebene Formulierungsmatrix für App und Telegram sowie MAR-/Konfliktprozess, falls anwendbar.
6. Technischer Security-/Privacy-Test und dokumentierte Freigabe der geprüften Produktversion.
7. Eintrag der Freigabedaten ausschließlich als Produktions-Secrets; niemals eine selbst ausgestellte Scheinfreigabe committen.

Erforderliche Produktionsfelder für einen externen Modus:
`APP_DISTRIBUTION_MODE`, `EXTERNAL_COMPLIANCE_APPROVED`, `EXTERNAL_COMPLIANCE_REVIEWER`,
`EXTERNAL_COMPLIANCE_REVIEWED_AT`, `EXTERNAL_COMPLIANCE_REVIEW_SCOPE`,
`EXTERNAL_COMPLIANCE_REFERENCE`, `DATA_CONTROLLER_NAME`, `PRIVACY_NOTICE_URL` und
`DATA_RETENTION_POLICY_VERSION`. Die Freigabe verfällt technisch nach 365 Tagen.

## 7. Sign-off

| Rolle | Name/Organisation | Qualifikation | Scope/Version | Ergebnis/Auflagen | Datum/Unterschrift/Referenz |
|---|---|---|---|---|---|
| Fachreview Trading/Risiko |  |  |  |  |  |
| Compliance/Regulatory |  |  |  |  |  |
| Datenschutz |  |  |  |  |  |
| Security/Operations |  |  |  |  |  |
| Product Owner – Auflagen umgesetzt |  |  |  |  |  |

## 8. Offizielle Ausgangsquellen

- [BaFin: Abgrenzung persönlicher Empfehlungen bei Robo-Advice](https://www.bafin.de/SharedDocs/Downloads/DE/BaFinJournal/2017/bj_1708.pdf?__blob=publicationFile&v=3)
- [MiFID II, insbesondere Artikel 24 und 25](https://eur-lex.europa.eu/eli/dir/2014/65/oj/eng)
- [Market Abuse Regulation, insbesondere Definitionen und Artikel 20](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32014R0596)
- [ESMA: Anforderungen an Investment Recommendations in sozialen Medien](https://www.esma.europa.eu/press-news/esma-news/requirements-when-posting-investments-recommendations-social-media)
- [Delegierte Verordnung (EU) 2016/958 zu Darstellung und Interessenkonflikten](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32016R0958)
- [DSGVO, insbesondere Artikel 5, 13, 22, 25 und 32](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32016R0679)
- [BfDI: Datenschutz durch Technikgestaltung und Pseudonymisierung](https://www.bfdi.bund.de/SharedDocs/Downloads/DE/DokumenteBfDI/Reden_Gastbeitraege/2024/Datenschutz-durch-Technik-BvD.pdf?__blob=publicationFile&v=1)
- [BaFin: Erlaubnispflichten im Zusammenhang mit Kryptowerten](https://www.bafin.de/webcode?id=19629702)

Die Quellen sind Ausgangspunkte, keine abschließende Rechtsanalyse. Reviewer müssen die am Prüfungstag
geltende deutsche und europäische Rechtslage sowie das tatsächliche Geschäftsmodell prüfen.
