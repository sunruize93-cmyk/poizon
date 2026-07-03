// 轮询下载中心,等「商品搜索导出」任务完成后点「成功结果」下载。复用 .seller_profile。
import { chromium } from 'playwright';

const ctx = await chromium.launchPersistentContext('tools/.seller_profile', {
  headless: false, locale: 'zh-CN', viewport: { width: 1440, height: 900 }, acceptDownloads: true,
});
const page = ctx.pages()[0] || await ctx.newPage();

let saved = null;
page.on('download', async d => {
  const p = `data/${d.suggestedFilename() || 'seller_export.xlsx'}`;
  await d.saveAs(p).catch(() => {}); saved = p; console.log('  ✓ 下载:', p);
});

console.log('→ 下载中心 exportCenter');
await page.goto('https://seller.poizon.com/main/exportCenter', { waitUntil: 'domcontentloaded' }).catch(() => {});
await page.waitForTimeout(4000);

for (let i = 0; i < 20 && !saved; i++) {
  // 找「商品搜索导出」所在行；若该行有「成功结果」则点下载
  const row = page.locator('tr', { hasText: '商品搜索导出' }).first();
  const done = await row.getByText('成功结果', { exact: false }).count().catch(() => 0);
  const status = await row.innerText().catch(() => '');
  console.log(` 轮询${i + 1}: ${/处理中/.test(status) ? '处理中' : done ? '已完成' : '?'}`);
  if (done) { await row.getByText('成功结果', { exact: false }).first().click({ timeout: 5000 }).catch(() => {}); await page.waitForTimeout(3000); }
  if (saved) break;
  await page.waitForTimeout(6000);
  await page.reload().catch(() => {}); await page.waitForTimeout(3000);
}
console.log('结果:', saved || '仍未完成/未下到,可稍后重跑本脚本');
await page.waitForTimeout(1500);
await ctx.close();
