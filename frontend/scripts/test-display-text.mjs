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
    localizeResolutionConfidence,
    normalizeGermanDisplayText,
  } = await import(`file://${modulePath.replace(/\\/g, "/")}`);

  assert.equal(localizeMarketRegime("mixed"), "Gemischt");
  assert.equal(localizeMarketRegime("risk-off"), "Risikoscheu");
  assert.equal(localizeResolutionConfidence("high"), "Hohe Sicherheit");
  assert.equal(localizeResolutionConfidence("medium"), "Mittlere Sicherheit");
  assert.equal(localizeResolutionConfidence(undefined), "Erfolgreich aufgelöst");
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
  ]) {
    assert.equal(uiCopy.includes(obsoleteCopy), false, `Veralteter UI-Text gefunden: ${obsoleteCopy}`);
  }

  console.log("displayText tests passed");
} finally {
  await rm(tempDir, { recursive: true, force: true });
}
