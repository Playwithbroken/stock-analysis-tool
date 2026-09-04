import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import ts from "typescript";

const sourcePath = path.resolve("src/lib/displayText.ts");
const source = await readFile(sourcePath, "utf8");
const uiCopySources = await Promise.all([
  readFile(path.resolve("src/App.tsx"), "utf8"),
  readFile(path.resolve("src/components/OnboardingWizard.tsx"), "utf8"),
  readFile(path.resolve("src/components/PriceChart.tsx"), "utf8"),
  readFile(path.resolve("src/components/SearchBar.tsx"), "utf8"),
  readFile(path.resolve("src/components/BrokerChat.tsx"), "utf8"),
  readFile(path.resolve("src/components/AnalysisResult.tsx"), "utf8"),
  readFile(path.resolve("src/lib/analysisQuality.ts"), "utf8"),
]);
const transpiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
});

const tempDir = await mkdtemp(path.join(tmpdir(), "broker-display-text-"));
const modulePath = path.join(tempDir, "displayText.mjs");

try {
  await writeFile(modulePath, transpiled.outputText, "utf8");
  const {
    localizeLearningMessage,
    localizeMarketRegime,
    localizeAnalysisLabel,
    localizeAnalysisText,
    localizeRecommendationAction,
    localizeResolutionConfidence,
    localizeSector,
    normalizeGermanDisplayText,
  } = await import(`file://${modulePath.replace(/\\/g, "/")}`);

  assert.equal(localizeMarketRegime("mixed"), "Gemischt");
  assert.equal(localizeMarketRegime("risk-off"), "Risikoscheu");
  assert.equal(localizeResolutionConfidence("high"), "Hohe Sicherheit");
  assert.equal(localizeResolutionConfidence("medium"), "Mittlere Sicherheit");
  assert.equal(localizeResolutionConfidence(undefined), "Erfolgreich aufgelöst");
  assert.equal(localizeAnalysisLabel("Technical Analysis"), "Technische Analyse");
  assert.equal(localizeAnalysisLabel("Data State"), "Datenstatus");
  assert.equal(localizeAnalysisLabel("Partial"), "Teilweise");
  assert.equal(localizeAnalysisLabel("Annualized Volatility"), "Annualisierte Volatilität");
  assert.equal(localizeAnalysisLabel("P/E Ratio"), "KGV");
  assert.equal(localizeAnalysisLabel("Revenue Growth vs Sector"), "Umsatzwachstum zur Branche");
  assert.equal(localizeAnalysisLabel("Reported Revenue YoY"), "Gemeldeter Umsatz zum Vorjahr");
  assert.equal(localizeAnalysisLabel("High Leverage Risk"), "Hohes Verschuldungsrisiko");
  assert.equal(localizeAnalysisLabel("4Q Beat/Miss Pattern"), "Muster der letzten 4 Quartale");
  assert.equal(localizeAnalysisLabel("Reported / Estimate EPS"), "Gemeldetes / geschätztes EPS");
  assert.equal(localizeAnalysisLabel("watch"), "Beobachten");
  assert.equal(localizeAnalysisLabel("not_dividend_stock"), "Keine Dividendenaktie");
  assert.equal(localizeAnalysisLabel("speculative"), "Spekulativ");
  assert.equal(localizeAnalysisLabel("intermediate"), "Fortgeschritten");
  assert.equal(localizeAnalysisLabel("Heavily Undervalued"), "Stark unterbewertet");
  assert.equal(
    localizeAnalysisText("Moderate decline over the past year"),
    "Moderater Rückgang im vergangenen Jahr",
  );
  assert.equal(
    localizeAnalysisText("High volatility stock - suitable for risk-tolerant investors"),
    "Hohe Volatilität – nur für risikotolerante Anleger geeignet",
  );
  assert.equal(
    localizeAnalysisText("Solid fundamentals with some positive aspects"),
    "Solide Fundamentaldaten mit einigen positiven Aspekten",
  );
  assert.equal(
    localizeAnalysisText("Earnings quality is mixed or in line; do not upgrade without price confirmation."),
    "Die Ergebnisqualität ist gemischt oder erwartungsgemäß; ohne Kursbestätigung nicht höher einstufen.",
  );
  assert.equal(
    localizeAnalysisText("Negative news sentiment - monitor closely (Verified alerts present)"),
    "Negative Nachrichtenstimmung – eng beobachten, verifizierte Warnmeldungen liegen vor",
  );
  assert.equal(localizeAnalysisText("Exceptional growth potential identified"), "Außergewöhnliches Wachstumspotenzial erkannt");
  assert.equal(localizeAnalysisText("No rebound setup detected"), "Kein belastbares Erholungsszenario erkannt");
  assert.equal(localizeAnalysisText("Identified 1 significant risk factors"), "1 wesentlicher Risikofaktor erkannt");
  assert.equal(localizeAnalysisText("Identified 4 positive factors"), "4 positive Faktoren erkannt");
  assert.equal(localizeAnalysisText("12,500 Shares"), "12.500 Aktien");
  assert.equal(localizeAnalysisText("70.6% annual"), "70.6% jährlich");
  assert.equal(localizeAnalysisText("No clear guidance read"), "Kein klares Ausblickssignal");
  assert.equal(localizeAnalysisText("No guidance signal"), "Kein Ausblickssignal");
  assert.equal(localizeAnalysisText("Guidance maintained"), "Ausblick bestätigt");
  assert.equal(localizeAnalysisText("6 Beat / 1 Miss"), "6 übertroffen / 1 verfehlt");
  assert.equal(localizeAnalysisText("2 beats / 1 misses"), "2 übertroffen / 1 verfehlt");
  assert.equal(localizeAnalysisText("Inline"), "Im Rahmen");
  assert.equal(localizeAnalysisText("Umsatzziele / Revenue-Qualitaet"), "Umsatzziele / Umsatzqualität");
  assert.equal(localizeAnalysisText("Earnings-Erwartung"), "Ergebniserwartung");
  assert.equal(localizeAnalysisText("Cash-/Margenqualitaet"), "Cash-/Margenqualität");
  assert.equal(localizeAnalysisText("Nicht klar erfuellt"), "Nicht klar erfüllt");
  assert.equal(
    localizeAnalysisText("Yield, Payout, Cashflow und Umsatztrend kombiniert"),
    "Dividendenrendite, Ausschüttungsquote, Cashflow und Umsatztrend kombiniert",
  );
  assert.equal(localizeAnalysisText("Margin +41.1% / FCF +35.4%"), "Marge +41.1% / FCF +35.4%");
  assert.equal(localizeAnalysisText("Likely"), "Wahrscheinlich");
  assert.equal(localizeRecommendationAction("HOLD / ACCUMULATE"), "Halten / Aufbauen");
  assert.equal(localizeRecommendationAction("STRONG SELL"), "Stark verkaufen");
  assert.equal(localizeSector("Financial Services"), "Finanzdienstleistungen");
  assert.equal(localizeSector("Consumer Defensive"), "Basiskonsumgüter");
  assert.equal(
    localizeLearningMessage("Promote morning_brief: 61.5% hit rate across 76 evaluated outcomes."),
    "Morning Briefing ausbauen: 61,5% Trefferquote aus 76 ausgewerteten Ergebnissen.",
  );
  assert.equal(
    normalizeGermanDisplayText("Signalrisiko liegt ueber der Toleranz. Trigger pruefen."),
    "Signalrisiko liegt über der Toleranz. Trigger prüfen.",
  );
  assert.equal(
    normalizeGermanDisplayText("Nur mit Folgequelle und Preisbestaetigung pushen."),
    "Nur mit Folgequelle und Preisbestätigung pushen.",
  );
  assert.equal(
    normalizeGermanDisplayText("Trigger, Positionsgroesse und Invalidierung pruefen."),
    "Trigger, Positionsgröße und Invalidierung prüfen.",
  );
  const uiCopy = uiCopySources.join("\n");
  for (const obsoleteCopy of [
    "Spaeter",
    "Aufgeloest:",
    "Retry Feed",
    ">Retry<",
    "Workspace Setup",
    "Setup abschliessen",
    "Search for a stock, ETF, or crypto ticker",
    "Fast lane",
    "Deep scan running",
    "Direct lookup ready",
    "Open Broker Freund Desk",
    "Open Desk",
    "Analysis Desk",
    "Price History",
    "Historical Market Data",
    "Intraday Minute Data",
    "Suitability score",
    "Advisory Suitability",
    "Suitability und Chart",
    "Suitability-Check geladen",
    "Live quote",
    "Dossier Intelligence",
    "Quality Score",
    "Bull Case",
    "Base Case",
    "Bear Case",
    "Business Quality Check",
    "Financial Statement Intelligence",
    "Top News & Sentiment",
    "Meine Einschaetzung",
    "Bollinger-Baender",
    "Aufwaertsdruck",
    "Kaeufer oder Verkaeufer",
    "Price Alert",
    "Target Price",
    ">Above<",
    ">Below<",
    ">Cancel<",
    "Aktivitaet / Bestaetigung",
    "Global Search",
    "Live | Market Briefing",
    "Pro Score",
    "hinzugefuegt",
    "gueltiges Alert-Level",
    "Alert setzen",
    "P/E hoch",
    "Umsatz, Earnings, Dividende",
  ]) {
    assert.equal(uiCopy.includes(obsoleteCopy), false, `Veralteter UI-Text gefunden: ${obsoleteCopy}`);
  }

  console.log("displayText tests passed");
} finally {
  await rm(tempDir, { recursive: true, force: true });
}
