// 取各应用的 AppSecret：进控制台逐个点 View，截获含 secret 的接口。
import { chromium } from 'playwright';
import fs from 'fs';

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ storageState: 'tools/.auth.json', locale: 'zh-CN' });
const page = await context.newPage();

const secrets = [];
page.on('response', async (resp) => {
  try {
    if (!resp.headers()['content-type']?.includes('json')) return;
    const body = await resp.json();
    const s = JSON.stringify(body);
    if (/secret/i.test(s)) {
      const d = body?.data || {};
      if (d.appSecret || d.appKey) secrets.push({ appKey: d.appKey, appName: d.appName, appSecret: d.appSecret, sandboxAppSecret: d.sandboxAppSecret });
    }
  } catch {}
});

await page.goto('https://open.poizon.com/application/list', { waitUntil: 'networkidle' });
await page.waitForTimeout(2500);
const views = page.locator('text="View"');
const n = await views.count();
console.log('apps:', n);
for (let i = 0; i < n; i++) {
  try {
    await page.goto('https://open.poizon.com/application/list', { waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);
    await page.locator('text="View"').nth(i).click({ timeout: 5000 });
    await page.waitForTimeout(2500);
    // 详情页可能有 Application Info 标签，点一下
    const info = page.locator('text=/Application Info|应用信息/').first();
    if (await info.count()) { await info.click().catch(() => {}); await page.waitForTimeout(1500); }
  } catch (e) { console.log('row', i, 'err', e.message.split('\n')[0]); }
}
fs.writeFileSync('tools/.secrets.json', JSON.stringify(secrets, null, 2));
console.log('captured secrets:', secrets.map(s => s.appName + ':' + (s.appSecret ? 'yes' : 'no')).join(', '));
await browser.close();
