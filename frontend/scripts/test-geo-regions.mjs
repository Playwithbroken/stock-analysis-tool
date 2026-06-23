import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import ts from "typescript";

const sourcePath = path.resolve("src/lib/geoRegions.ts");
const source = await readFile(sourcePath, "utf8");
const transpiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
});

const tempDir = await mkdtemp(path.join(tmpdir(), "broker-geo-regions-"));
const modulePath = path.join(tempDir, "geoRegions.mjs");

try {
  await writeFile(modulePath, transpiled.outputText, "utf8");
  const { normalizeGeoRegions } = await import(`file://${modulePath.replace(/\\/g, "/")}`);

  const empty = normalizeGeoRegions(null);
  assert.equal(empty.length, 3);
  assert.deepEqual(empty.map((region) => region.label), ["Asia", "Europe", "USA"]);
  assert.equal(empty[0].assets[0].ticker, "^N225");
  assert.equal(empty[1].assets[0].ticker, "^GDAXI");
  assert.equal(empty[2].assets[0].ticker, "SPY");

  const partial = normalizeGeoRegions({
    europe: {
      label: "Europe",
      tone: "risk-on",
      avg_change_1d: "1.25",
      assets: [{ ticker: "DAX", label: "DAX", change_1d: 1.25 }],
    },
  });
  assert.equal(partial[1].tone, "risk-on");
  assert.equal(partial[1].avg_change_1d, 1.25);
  assert.equal(partial[1].assets[0].ticker, "DAX");
  assert.equal(partial[0].label, "Asia");
  assert.equal(partial[2].label, "USA");

  const malformed = normalizeGeoRegions({
    asia: [],
    europe: { avg_change_1d: "not-a-number", assets: [] },
    usa: "bad",
  });
  assert.equal(malformed.length, 3);
  assert.equal(malformed[0].avg_change_1d, 0);
  assert.equal(malformed[1].avg_change_1d, 0);
  assert.equal(malformed[2].assets[0].ticker, "SPY");

  console.log("geoRegions tests passed");
} finally {
  await rm(tempDir, { recursive: true, force: true });
}
