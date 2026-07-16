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

console.log('PWA build strategy tests passed');
