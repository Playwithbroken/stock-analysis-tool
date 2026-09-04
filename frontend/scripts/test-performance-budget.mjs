import { readFileSync, readdirSync, statSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const distDir = new URL("../dist/", import.meta.url);
const assetsDir = new URL("../dist/assets/", import.meta.url);
const assetsPath = fileURLToPath(assetsDir);
const indexHtml = readFileSync(new URL("index.html", distDir), "utf8");
const files = readdirSync(assetsDir);

function fail(message) {
  console.error(`[performance-budget] ${message}`);
  process.exitCode = 1;
}

function gzipKiB(fileName) {
  const payload = readFileSync(join(assetsPath, fileName));
  return gzipSync(payload).byteLength / 1024;
}

const entryMatch = indexHtml.match(/<script[^>]+src="\/assets\/(index-[^"]+\.js)"/);
const entryFile = entryMatch?.[1];
const mapFile = files.find((name) => /^WorldMarketMap-.*\.js$/.test(name));
const mapAsset = files.find((name) => /^world-map-wikimedia-.*\.svg$/.test(name));

if (!entryFile) fail("Initial JavaScript entry was not found in dist/index.html.");
if (!mapFile) fail("WorldMarketMap lazy chunk was not generated.");
if (!mapAsset) fail("World map geometry must be emitted as a separate cacheable SVG asset.");

if (entryFile) {
  const size = gzipKiB(entryFile);
  if (size > 120) fail(`Initial JavaScript is ${size.toFixed(1)} KiB gzip; budget is 120 KiB.`);
  else console.log(`[performance-budget] initial JS ${size.toFixed(1)} KiB gzip (budget 120 KiB)`);
}

if (mapFile) {
  const size = gzipKiB(mapFile);
  if (size > 30) fail(`WorldMarketMap code is ${size.toFixed(1)} KiB gzip; budget is 30 KiB.`);
  else console.log(`[performance-budget] map JS ${size.toFixed(1)} KiB gzip (budget 30 KiB)`);
}

if (mapAsset) {
  const size = statSync(join(assetsPath, mapAsset)).size / 1024;
  if (size > 320) fail(`World map SVG is ${size.toFixed(1)} KiB; budget is 320 KiB.`);
  else console.log(`[performance-budget] map SVG ${size.toFixed(1)} KiB (budget 320 KiB)`);
}

if (!process.exitCode) console.log("performance budget passed");
