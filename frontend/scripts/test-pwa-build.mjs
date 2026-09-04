import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const serviceWorker = await readFile(new URL('../dist/sw.js', import.meta.url), 'utf8');

assert.equal(
  serviceWorker.includes('index.html'),
  false,
  'index.html must not be precached because navigations use NetworkFirst',
);
assert.match(serviceWorker, /NetworkFirst/, 'navigation requests must use NetworkFirst');
assert.match(serviceWorker, /broker-freund-pages/, 'navigation responses need an offline runtime cache');
assert.match(serviceWorker, /StaleWhileRevalidate/, 'lazy assets need a runtime cache after first use');
assert.match(serviceWorker, /broker-freund-assets/, 'lazy assets need the named runtime cache');

for (const lazyAsset of [
  'WorldMarketMap-',
  'MorningBriefPanel-',
  'DiscoveryPanel-',
  'PortfolioView-',
  'vendor-charts-',
  'world-map-wikimedia-',
]) {
  assert.equal(
    serviceWorker.includes(lazyAsset),
    false,
    `${lazyAsset} must load on demand instead of competing with the initial PWA install`,
  );
}

console.log('PWA build strategy tests passed');
