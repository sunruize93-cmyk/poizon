// 点「导出所有结果」批量导出商品需求数据 → 抓下载文件到 data/。复用 .seller_profile。
// 导出可能是直接下载或异步进「下载中心」。本脚本先试直接下载,失败则截图看去向。
import { chromium } from 'playwright';
import fs from 'fs';

const ctx = await chromium.launchPersistentContext('tools/.seller_profile', {
  headless: false, locale: 'zh-CN', viewport: { width: 1440, height: 900 }, acceptDownloads: true,
});
const page = ctx.pages()[0] || await ctx.newPage();

console.log('→ 商品搜索页');
await page.goto('https://seller.poizon.com/main/goods/search', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
await page.waitForTimeout(8000);

// 准备接收下载
let saved = null;
page.on('download', async d => {
  const name = d.suggestedFilename() || 'seller_export.xlsx';
  const p = `data/${name}`;
  await d.saveAs(p).catch(() => {});
  saved = p; console.log('  ✓ 下载:', p);
});

console.log('→ 点击 导出所有结果');
const clicked = await page.getByText('导出所有结果', { exact: false }).first().click({ timeout: 8000 }).then(() => true).catch(e => { console.log(' 点击失败', e.message.split('\n')[0]); return false; });
await page.waitForTimeout(4000);

// 可能弹确认框
for (const t of ['确定', '确认', '导出']) {
  const b = page.getByRole('button', { name: t });
  if (await b.count().catch(() => 0)) { await b.first().click().catch(() => {}); console.log(' 点确认:', t); break; }
}

// 等直接下载
for (let i = 0; i < 12 && !saved; i++) await page.waitForTimeout(2000);

if (!saved) {
  console.log(' 无直接下载,去「下载中心」看导出任务');
  await page.getByText('下载中心', { exact: false }).first().click({ timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(6000);
  await page.screenshot({ path: 'tools/_seller_dlcenter.png' }).catch(() => {});
  console.log(' 已截图 下载中心 → tools/_seller_dlcenter.png');
}
console.log('结果:', saved || '未捕获直接下载,看截图');
await page.waitForTimeout(2000);
await ctx.close();
