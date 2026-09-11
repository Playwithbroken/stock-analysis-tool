import { chromium } from './node_modules/playwright/index.mjs';

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1100 },
    serviceWorkers: 'block'
  });
  const page = await context.newPage();

  await page.goto('https://web-production-8546b.up.railway.app');
  await page.evaluate(async () => {
    await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: '100363', remember_device: true })
    });
    localStorage.setItem('activeTab', 'portfolio');
  });

  await page.reload({ waitUntil: 'domcontentloaded' });
  console.log('Waiting for Paper-Konto Geldfluss...');
  await page.waitForSelector('text=Paper-Konto Geldfluss', { timeout: 25000 });
  console.log('Paper-Konto Geldfluss is VISIBLE!');

  // Scroll to Paper Trading Panel
  const paperHeader = page.locator('text=Paper-Konto Geldfluss').first();
  await paperHeader.scrollIntoViewIfNeeded();
  await page.waitForTimeout(2000);
  await page.screenshot({
    path: 'C:/Users/menke/.gemini/antigravity/brain/18475303-559c-4098-890f-9c90c6e57424/paper_trading_100k_live.png',
    fullPage: false
  });
  console.log('Saved paper_trading_100k_live.png');

  // Scroll up to Scalable Capital positions table
  await page.evaluate(() => window.scrollTo(0, 350));
  await page.waitForTimeout(2000);
  await page.screenshot({
    path: 'C:/Users/menke/.gemini/antigravity/brain/18475303-559c-4098-890f-9c90c6e57424/scalable_portfolio_table_live.png',
    fullPage: false
  });
  console.log('Saved scalable_portfolio_table_live.png');

  await browser.close();
}

main().catch(err => {
  console.error('Error:', err);
  process.exit(1);
});
