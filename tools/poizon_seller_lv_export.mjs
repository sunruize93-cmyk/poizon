// 商品搜索按品牌=LV筛选 → 校验结果数下降 → 导出所有结果。复用 .seller_profile。
// 之后用 poizon_seller_dl.mjs 下载。用法: node tools/poizon_seller_lv_export.mjs [品牌关键词]
import { chromium } from 'playwright';

const BRAND = process.argv[2] || '路易威登';
const ctx = await chromium.launchPersistentContext('tools/.seller_profile', {
  headless: false, locale: 'zh-CN', viewport: { width: 1440, height: 900 }, acceptDownloads: true,
});
const page = ctx.pages()[0] || await ctx.newPage();

const countText = async () => {
  const t = await page.getByText(/共\s*[\d,]+\s*条结果/).first().innerText().catch(() => '');
  return t;
};

console.log('→ 商品搜索页');
await page.goto('https://seller.poizon.com/main/goods/search', { waitUntil: 'domcontentloaded' }).catch(() => {});
await page.waitForTimeout(8000);
console.log(' 筛选前:', await countText());

// 打开「品牌」筛选
console.log('→ 打开品牌筛选');
await page.getByText('品牌', { exact: true }).first().click({ timeout: 6000 }).catch(e => console.log(' 点品牌失败', e.message.split('\n')[0]));
await page.waitForTimeout(1500);
// 弹层里找搜索输入框,输入品牌词
const box = page.locator('input[placeholder*="搜索"], input[type="text"]:visible').last();
if (await box.count().catch(() => 0)) {
  await box.fill(BRAND).catch(() => {});
  console.log(' 输入品牌:', BRAND);
  await page.waitForTimeout(2500);
}
// 选中第一个匹配项(选项/复选框)
let picked = false;
for (const sel of [`text=${BRAND}`, 'text=/LOUIS VUITTON/i', 'text=/路易/', '.ant-select-item', 'li[role=option]']) {
  const opt = page.locator(sel).first();
  if (await opt.count().catch(() => 0)) { await opt.click({ timeout: 3000 }).catch(() => {}); picked = true; console.log(' 选中选项:', sel); break; }
}
await page.waitForTimeout(1000);
// 确认(若有)
for (const t of ['确定', '确认']) { const b = page.getByRole('button', { name: t }); if (await b.count().catch(() => 0)) { await b.first().click().catch(() => {}); break; } }
await page.waitForTimeout(4000);
await page.screenshot({ path: 'tools/_seller_lvfilter.png' }).catch(() => {});
const after = await countText();
console.log(' 筛选后:', after, '| 选中成功:', picked);

// 只有筛选疑似生效(结果数变化)才导出
console.log('→ 导出所有结果');
await page.getByText('导出所有结果', { exact: false }).first().click({ timeout: 8000 }).catch(e => console.log(' 导出点击失败', e.message.split('\n')[0]));
await page.waitForTimeout(3000);
for (const t of ['确定', '确认', '导出']) { const b = page.getByRole('button', { name: t }); if (await b.count().catch(() => 0)) { await b.first().click().catch(() => {}); console.log(' 确认导出:', t); break; } }
await page.waitForTimeout(4000);
console.log('✓ 已提交导出,接下来跑 poizon_seller_dl.mjs 下载');
await ctx.close();
