// LV 韩国价格端点探测：busts Akamai via reload-on-deny，抓商品/价格 XHR。
// 用法: node tools/lv_probe_price.mjs [productURL]
import { chromium } from 'patchright';
import 'dotenv/config';
import fs from 'fs';

const m = (process.env.LV_PROXY || '').match(/^https?:\/\/([^:]+):([^@]+)@([^:]+):(\d+)$/)
       || (process.env.LV_PROXY || '').match(/^https?:\/\/([^:]+):(\d+)$/);
let proxy;
if (m && m.length === 5) proxy = { server: `http://${m[3]}:${m[4]}`, username: m[1], password: m[2] };
else if (m) proxy = { server: `http://${m[1]}:${m[2]}` };
console.log('proxy:', proxy && proxy.server);

const PURL = process.argv[2] || 'https://kr.louisvuitton.com/kor-kr/products/multiple-wallet-taiga-leather-nvprod1420109v/M30295';
const ctx = await chromium.launchPersistentContext('tools/.lv_profile', {
  headless: false, viewport: null, locale: 'ko-KR', timezoneId: 'Asia/Seoul', proxy,
});
const page = ctx.pages()[0] || await ctx.newPage();

const hits = [];
page.on('response', async r => {
  try {
    const u = r.url();
    if (!/louisvuitton\.com/i.test(u)) return;
    if (!/(product|catalog|price|sku|pdp|stock|availab|eco-as|eco-eu)/i.test(u)) return;
    const ct = r.headers()['content-type'] || '';
    if (!ct.includes('json')) return;
    let b; try { b = await r.text(); } catch { return; }
    if (/price|amount|sku|sellable|availab|"M\d{5}/i.test(b)) hits.push({ status: r.status(), url: u, len: b.length, body: b });
  } catch {}
});

const denied = async () => {
  const c = await page.content();
  return c.includes('Access denied') || c.includes('Access Denied') || c.includes('Accès refusé');
};

console.log('→ homepage warmup');
await page.goto('https://kr.louisvuitton.com/kor-kr/homepage', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(e => console.log(' warn', e.message.split('\n')[0]));
await page.waitForTimeout(4000);
await page.mouse.move(400, 300); await page.mouse.move(600, 500);
await page.evaluate(() => window.scrollBy(0, 600)).catch(() => {});
await page.waitForTimeout(2500);

console.log('→ product', PURL);
let ok = false;
for (let i = 1; i <= 4; i++) {
  await page.goto(PURL, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(e => console.log(' warn', e.message.split('\n')[0]));
  await page.waitForTimeout(4000);
  const d = await denied();
  console.log(`  try ${i}: denied=${d} url=${page.url().slice(0, 70)}`);
  if (!d) { ok = true; break; }
  await page.waitForTimeout(3000); // 让 Akamai sensor 充分跑完再 reload
}
if (ok) {
  await page.evaluate(() => window.scrollBy(0, 800)).catch(() => {});
  await page.waitForTimeout(5000);
  const price = await page.evaluate(() => { const m = document.body.innerText.match(/[\d,]{6,}\s*(원|₩|KRW)/); return m ? m[0] : null; });
  console.log(' visible price:', price);
}
await page.screenshot({ path: 'tools/_lvprice.png' }).catch(() => {});

console.log('--- price-bearing XHR:', hits.length, '---');
for (const h of hits) console.log(h.status, h.url.slice(0, 130), 'len=' + h.len);
fs.writeFileSync('tools/_lvprice_full.json', JSON.stringify(hits, null, 1));
await ctx.close();
