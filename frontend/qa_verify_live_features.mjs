import { chromium } from './node_modules/playwright/index.mjs';

const BASE_URL = 'https://web-production-8546b.up.railway.app';
const ACCESS_CODE = '100363';

async function main() {
  console.log('Starting live verification on Railway...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  const page = await context.newPage();

  console.log('Logging in via /api/auth/login...');
  await context.request.post(`${BASE_URL}/api/auth/login`, {
    data: { password: ACCESS_CODE, remember_device: true }
  });

  console.log('Navigating to app root...');
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
  await page.evaluate((code) => {
    localStorage.setItem('stock_analyzer_access_code', code);
    localStorage.setItem('hasAccess', 'true');
    localStorage.setItem('activeTab', 'portfolio');
  }, ACCESS_CODE);

  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);

  // Click on Portfolio tab explicitly to ensure it is active
  const portfolioBtn = page.locator('button:has-text("Portfolio")').first();
  if (await portfolioBtn.isVisible()) {
    await portfolioBtn.click();
    await page.waitForTimeout(2000);
  }

  // Scroll to Scalable positions and screenshot
  await page.screenshot({
    path: 'C:/Users/menke/.gemini/antigravity/brain/18475303-559c-4098-890f-9c90c6e57424/scalable_portfolio_updated_live.png',
    fullPage: false
  });
  console.log('Captured scalable_portfolio_updated_live.png');

  // Scroll down to Paper Trading Panel and screenshot
  const paperSection = page.locator('text=Paper-Konto Geldfluss').first();
  if (await paperSection.isVisible()) {
    await paperSection.scrollIntoViewIfNeeded();
    await page.waitForTimeout(1500);
    await page.screenshot({
      path: 'C:/Users/menke/.gemini/antigravity/brain/18475303-559c-4098-890f-9c90c6e57424/paper_trading_100k_live.png',
      fullPage: false
    });
    console.log('Captured paper_trading_100k_live.png');
  } else {
    console.log('Paper section not immediately visible; taking full page screenshot...');
    await page.screenshot({
      path: 'C:/Users/menke/.gemini/antigravity/brain/18475303-559c-4098-890f-9c90c6e57424/paper_trading_100k_live.png',
      fullPage: true
    });
  }

  await browser.close();
  console.log('Verification completed successfully.');
}

main().catch(err => {
  console.error('Error:', err);
  process.exit(1);
});
