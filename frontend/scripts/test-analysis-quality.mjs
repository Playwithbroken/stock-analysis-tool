import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import ts from "typescript";

const source = await readFile(path.resolve("src/lib/analysisQuality.ts"), "utf8");
const transpiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
});
const tempDir = await mkdtemp(path.join(tmpdir(), "broker-analysis-quality-"));
const modulePath = path.join(tempDir, "analysisQuality.mjs");

try {
  await writeFile(modulePath, transpiled.outputText, "utf8");
  const { getAnalysisQualityState, formatAnalysisFetchTime } = await import(
    `file://${modulePath.replace(/\\/g, "/")}`
  );

  assert.equal(getAnalysisQualityState().level, "full");
  assert.equal(getAnalysisQualityState({ degraded: true }).level, "degraded");
  assert.equal(getAnalysisQualityState({ degraded: true }).blocksDecision, true);
  assert.equal(
    getAnalysisQualityState({ degraded: true, insufficient_signal: true }).level,
    "insufficient",
  );
  assert.equal(formatAnalysisFetchTime("not-a-date"), null);
  assert.match(formatAnalysisFetchTime("2026-07-17 13:45:00"), /17\.07\.26/);
  console.log("analysis quality tests passed");
} finally {
  await rm(tempDir, { recursive: true, force: true });
}
