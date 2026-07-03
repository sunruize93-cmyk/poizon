// 验证正确的款级销量来源:在商品搜索框输货号→抓 aurora-spu 响应→读 SPU 级 saleInfo。
import { chromium } from 'playwright';
const ART = process.argv[2] || '1ACNYF';
const ctx = await chromium.launchPersistentContext('tools/.seller_profile', {
  headless: false, locale: 'zh-CN', viewport: { width: 1440, height: 900 },
});
const page = ctx.pages()[0] || await ctx.newPage();
let hit = null;
page.on('response', async r => {
  try {
    if (!/aurora-spu\/merchant\/search/i.test(r.url())) return;
    const d = JSON.parse(await r.text());
    const list = d?.data?.merchantSpuDtoList || [];
    for (const x of list) if (x.articleNumber === ART) hit = x;
  } catch {}
});
await page.goto('https://seller.poizon.com/main/goods/search', { waitUntil: 'domcontentloaded' }).catch(()=>{});
await page.waitForTimeout(6000);
// 顶部搜索框输货号
const box = page.locator('input[placeholder*="名称"], input[placeholder*="货号"], input[type="text"]:visible').first();
await box.click().catch(()=>{}); await box.fill(ART).catch(()=>{});
await page.keyboard.press('Enter');
await page.waitForTimeout(7000);
if (hit) {
  console.log(`货号 ${ART}: ${hit.title}`);
  console.log('  saleInfo:', JSON.stringify(hit.saleInfo));
  console.log('  中国最低价:', hit.priceInfo?.globalMinPrice?.localizedDisplayText,
              '| CN成交均价:', hit.salePriceAndNumMap?.CN?.globalLowestAvgPrice?.localizedDisplayText,
              '| CN销量:', hit.salePriceAndNumMap?.CN?.globalSoldNum);
} else console.log(`未捕获到 ${ART} 的 SPU 响应(可能搜索框交互没触发)`);
await ctx.close();
