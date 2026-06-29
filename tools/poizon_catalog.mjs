// 点遍左侧每个 API 大类，截获 queryApiList（内嵌每个接口的完整 apiDoc），
// 汇总成 data/poizon_docs/catalog.json。
import { chromium } from 'playwright';
import fs from 'fs';

const OUT = 'data/poizon_docs';
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ storageState: 'tools/.auth.json', locale: 'zh-CN' });
const page = await context.newPage();

const byService = {};
page.on('response', async (resp) => {
  try {
    if (!resp.url().includes('/queryApiList')) return;
    const u = new URL(resp.url());
    const id = u.searchParams.get('id');
    const body = await resp.json();
    if (body?.data) byService[id] = body.data;
  } catch {}
});

await page.goto('https://open.poizon.com/doc/list/documentationDetail/33', { waitUntil: 'networkidle' });
await page.waitForTimeout(3000);

const services = ['Item', 'Listing & Inventory', 'Consignment', 'Order', 'Fulfillment',
                  'Bill', 'Return', 'Merchant', 'Smart Listing', 'Bonded'];
for (const s of services) {
  try {
    const loc = page.locator(`text="${s}"`).first();
    await loc.scrollIntoViewIfNeeded({ timeout: 5000 });
    await loc.click({ timeout: 5000, force: true });
    await page.waitForTimeout(2000);
    console.log('clicked', s);
  } catch (e) { console.log('miss', s, e.message.split('\n')[0]); }
}
await page.waitForTimeout(1500);

fs.writeFileSync(`${OUT}/catalog.json`, JSON.stringify(byService, null, 2));
const total = Object.values(byService).reduce((a, v) => a + v.length, 0);
console.log('captured services:', Object.keys(byService).join(','), 'total apis:', total);
await browser.close();
