import { readdir, rm, stat } from "node:fs/promises";
import { join, extname, basename } from "node:path";

const assetsDir = join(process.cwd(), "dist", "assets");
const keepPerChunk = Number.parseInt(process.env.DIST_ASSET_KEEP_PER_CHUNK || "3", 10);
const hashedExts = new Set([".js", ".css"]);

function chunkPrefix(fileName) {
  const ext = extname(fileName);
  if (!hashedExts.has(ext)) return null;
  const stem = basename(fileName, ext);
  const idx = stem.lastIndexOf("-");
  if (idx <= 0) return null;
  return `${stem.slice(0, idx)}${ext}`;
}

try {
  const files = await readdir(assetsDir);
  const groups = new Map();

  for (const fileName of files) {
    const prefix = chunkPrefix(fileName);
    if (!prefix) continue;
    const filePath = join(assetsDir, fileName);
    const meta = await stat(filePath);
    const list = groups.get(prefix) || [];
    list.push({ fileName, filePath, mtimeMs: meta.mtimeMs });
    groups.set(prefix, list);
  }

  let removed = 0;
  for (const list of groups.values()) {
    list.sort((a, b) => b.mtimeMs - a.mtimeMs);
    for (const item of list.slice(Math.max(1, keepPerChunk))) {
      await rm(item.filePath, { force: true });
      removed += 1;
    }
  }

  if (removed > 0) {
    console.log(`[prune-dist-assets] removed ${removed} old hashed asset(s), kept ${keepPerChunk} per chunk.`);
  }
} catch (error) {
  if (error?.code !== "ENOENT") {
    console.warn(`[prune-dist-assets] skipped: ${error?.message || error}`);
  }
}
