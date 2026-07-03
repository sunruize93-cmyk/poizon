// 复用 .seller_profile(已登录) → 进商品搜索 → 捕获商品表 API(含中国30天销量/成交均价/本地卖家销量)。
import { chromium } from 'playwright';
import fs from 'fs';

const ctx = await chromium.launchPersistentContext('tools/.seller_profile', {
  headless: false, locale: 'zh-CN', viewport: { width: 1440, height: 900 },
});
const page = ctx.pages()[0] || await ctx.newPage();

const hits = [];
page.on('response', async r => {
  try {
    const u = r.url(); if (!/poizon\.com|dewu/i.test(u)) return;
    if (!(r.headers()['content-type'] || '').includes('json')) return;
    let b = ''; try { b = await r.text(); } catch { return; }
    if (/sold|销量|成交|spuId|lowestPrice|dealAvg|articleNumber|skuId/i.test(b) && b.length > 500
        && !/configCenter|validate_rule|SysPermission/i.test(u)) {
      hits.push({ status: r.status(), url: u, len: b.length, body: b });
      console.log('  [候选]', r.status(), u.replace(/https?:\/\/[^/]+/, '').split('?')[0].slice(0, 80), 'len=' + b.length);
    }
  } catch {}
});

console.log('→ dataBoard');
await page.goto('https://seller.poizon.com/main/dataBoard', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
await page.waitForTimeout(4000);

// dump 左侧导航路由
const nav = await page.evaluate(() =>
  [...new Set([...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href')).filter(h => h && h.includes('/main')))].slice(0, 40));
console.log(' /main 路由:', JSON.stringify(nav).slice(0, 500));

// 点「商品搜索」
const clicked = await page.getByText('商品搜索', { exact: false }).first().click({ timeout: 5000 }).then(() => true).catch(() => false);
console.log(' 点商品搜索:', clicked);
await page.waitForTimeout(9000);
console.log(' 当前:', page.url().slice(0, 90));
await page.screenshot({ path: 'tools/_seller_search.png' }).catch(() => {});
fs.writeFileSync('tools/_seller_bodies.json', JSON.stringify(hits, null, 1));
console.log('候选 API:', hits.length);
await ctx.close();
