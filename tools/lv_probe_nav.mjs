// LV PDP via in-site navigation (click-through) — 绕过对深链 goto 的 Akamai 拦截。
import { chromium } from 'patchright';
import 'dotenv/config';
import fs from 'fs';

const raw = process.env.LV_PROXY || '';
const m = raw.match(/^https?:\/\/([^:]+):([^@]+)@([^:]+):(\d+)$/);
const proxy = m ? { server: `http://${m[3]}:${m[4]}`, username: m[1], password: m[2] } : undefined;
console.log('proxy:', proxy && proxy.server);

const ctx = await chromium.launchPersistentContext('tools/.lv_profile', {
  headless: false, viewport: null, locale: 'ko-KR', timezoneId: 'Asia/Seoul', proxy,
});
const page = ctx.pages()[0] || await ctx.newPage();

const hits = [];
page.on('response', async r => {
  try {
    const u = r.url(); if (!/louisvuitton\.com/i.test(u)) return;
    if (!/(product|catalog|price|sku|pdp|stock|availab|eco-as|eco-eu)/i.test(u)) return;
    if (!(r.headers()['content-type'] || '').includes('json')) return;
    let b; try { b = await r.text(); } catch { return; }
    if (/price|amount|sku|sellable|availab|"M\d{5}/i.test(b)) hits.push({ status: r.status(), url: u, len: b.length, body: b });
  } catch {}
});
const denied = async () => { const c = await page.content(); return /Access denied/i.test(c) || c.includes('Accès refusé'); };

console.log('→ homepage'); await page.goto('https://kr.louisvuitton.com/kor-kr/homepage', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(e => console.log(' warn', e.message.split('\n')[0]));
await page.waitForTimeout(4000); console.log(' homepage denied?', await denied());
await page.mouse.move(500, 400); await page.evaluate(() => window.scrollBy(0, 700)).catch(() => {}); await page.waitForTimeout(2500);

// 找首页上的商品链接，模拟真人点击进入 PDP（同源路由，带 referer/历史）
const hrefs = await page.evaluate(() =>
  Array.from(document.querySelectorAll('a[href*="/products/"]')).map(a => a.href).slice(0, 8));
console.log(' product links on homepage:', hrefs.length, hrefs[0] || '');
if (hrefs.length) {
  const sel = `a[href*="${new URL(hrefs[0]).pathname}"]`;
  await page.locator(sel).first().scrollIntoViewIfNeeded().catch(() => {});
  await page.waitForTimeout(1200);
  await page.locator(sel).first().click({ timeout: 15000 }).catch(e => console.log(' click warn', e.message.split('\n')[0]));
  await page.waitForTimeout(7000);
  console.log(' after click denied?', await denied(), 'url:', page.url().slice(0, 80));
  await page.evaluate(() => window.scrollBy(0, 900)).catch(() => {}); await page.waitForTimeout(4000);
  const price = await page.evaluate(() => { const m = document.body.innerText.match(/[\d,]{6,}\s*(원|₩|KRW)/); return m ? m[0] : null; });
  console.log(' visible price:', price);
}
await page.screenshot({ path: 'tools/_lvnav.png' }).catch(() => {});
console.log('--- price XHR:', hits.length, '---');
for (const h of hits) console.log(h.status, h.url.slice(0, 130), 'len=' + h.len, '|', h.body.slice(0, 70).replace(/\s+/g, ' '));
fs.writeFileSync('tools/_lvnav_full.json', JSON.stringify(hits, null, 1));
await ctx.close();
