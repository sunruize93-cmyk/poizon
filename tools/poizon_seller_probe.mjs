// 探测 seller.poizon.com 商品搜索 API（含中国30天销量/成交均价/本地卖家销量）。
// 复用 open.poizon 的登录态(.auth.json)试 SSO 是否通;捕获返回商品表的 XHR。
import { chromium } from 'playwright';
import fs from 'fs';

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ storageState: 'tools/.auth.json', locale: 'zh-CN' });
const page = await ctx.newPage();

const hits = [];
page.on('response', async r => {
  try {
    const u = r.url();
    if (!/poizon\.com|dewu/i.test(u)) return;
    if (!(r.headers()['content-type'] || '').includes('json')) return;
    let b = ''; try { b = await r.text(); } catch { return; }
    // 商品表特征：含销量/成交价/spuId/最低价 等字段
    if (/soldNum|sold|spuId|spuTitle|lowestPrice|dealPrice|销量|成交|articleNumber|skuId/i.test(b) && b.length > 300) {
      hits.push({ status: r.status(), url: u, len: b.length, body: b });
      console.log('  [候选]', r.status(), u.replace(/https?:\/\/[^/]+/, '').slice(0, 90), 'len=' + b.length);
    }
  } catch {}
});

console.log('→ 打开 seller.poizon.com');
await page.goto('https://seller.poizon.com', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(e => console.log(' warn', e.message.split('\n')[0]));
await page.waitForTimeout(6000);
const url = page.url();
const title = await page.title().catch(() => '');
console.log(' 落地:', url.slice(0, 80), '| title:', title);
const isLogin = /passport|account\.poizon|\/login/i.test(url);
console.log(' 是否登录页:', isLogin, '(false=已登录)');

// SPA 导航进「商品搜索」：点左侧菜单 商品 → 商品搜索
async function tryClick(t) {
  try { const l = page.getByText(t, { exact: true }).first(); if (await l.count()) { await l.click({ timeout: 4000 }); return true; } } catch {}
  return false;
}
if (!isLogin) {
  // dump 导航结构，找商品搜索的真实路由
  const nav = await page.evaluate(() => {
    const out = [];
    document.querySelectorAll('a[href], [class*="menu"] *, [class*="nav"] *').forEach(e => {
      const t = (e.innerText || '').trim();
      const h = e.getAttribute && e.getAttribute('href');
      if (t && t.length < 12 && /商品|搜索|盘点|机会|分析|概览/.test(t)) out.push({ t, h });
    });
    return [...new Map(out.map(x => [x.t + (x.h || ''), x])).values()].slice(0, 25);
  });
  console.log(' 导航候选:', JSON.stringify(nav, null, 0).slice(0, 700));
  // 点「商品」展开再点「商品搜索」
  await page.getByText('商品', { exact: true }).first().click({ timeout: 4000 }).catch(() => {});
  await page.waitForTimeout(1500);
  await page.getByText('商品搜索', { exact: false }).first().click({ timeout: 4000 }).catch(e => console.log(' 点击失败', e.message.split('\n')[0]));
  await page.waitForTimeout(8000);
  console.log(' 当前页:', page.url().slice(0, 90));
}
await page.screenshot({ path: 'tools/_seller.png' }).catch(() => {});
fs.writeFileSync('tools/_seller_hits.json', JSON.stringify(hits.map(h => ({ status: h.status, url: h.url, len: h.len })), null, 1));
fs.writeFileSync('tools/_seller_bodies.json', JSON.stringify(hits, null, 1));
console.log('候选 API 数:', hits.length, '(详见 tools/_seller_hits.json)');
await browser.close();
