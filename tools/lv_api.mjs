// LV 按货号批量抓价：暖机首页拿 Akamai cookie，之后全部走「页内 same-origin fetch」调 API。
// 这是 grace-XHR 模式：整页跳转会被 Akamai 拦，但同源 XHR 带 cookie 可过。
// 用法: node tools/lv_api.mjs 1AK8BN 1AK81F M4583
import { chromium } from 'patchright';
import 'dotenv/config';
import fs from 'fs';

const raw = process.env.LV_PROXY || '';
const m = raw.match(/^https?:\/\/([^:]+):([^@]+)@([^:]+):(\d+)$/);
const proxy = m ? { server: `http://${m[3]}:${m[4]}`, username: m[1], password: m[2] } : undefined;
const PROFILE = process.env.LV_PROFILE || 'tools/.lv_profile_api';
const ARTS = process.argv.slice(2);
if (!ARTS.length) { console.log('用法: node tools/lv_api.mjs 货号 [货号...]'); process.exit(1); }
console.log('proxy:', proxy && proxy.server, '| profile:', PROFILE, '| 货号:', ARTS.join(','));

const ctx = await chromium.launchPersistentContext(PROFILE, {
  headless: false, viewport: null, locale: 'ko-KR', timezoneId: 'Asia/Seoul', proxy,
});
const page = ctx.pages()[0] || await ctx.newPage();
const denied = async () => /Access denied/i.test(await page.content().catch(() => ''));

// 页内同源 fetch（带 cookie），返回 {status, body}
const apiGet = (url) => page.evaluate(async (u) => {
  try { const r = await fetch(u, { headers: { accept: 'application/json' }, credentials: 'include' });
    return { status: r.status, body: await r.text() }; }
  catch (e) { return { status: -1, body: String(e) }; }
}, url);

console.log('→ homepage 暖机');
await page.goto('https://kr.louisvuitton.com/kor-kr/homepage', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(e => console.log(' warn', e.message.split('\n')[0]));
await page.waitForTimeout(5000);
await page.mouse.move(500, 400); await page.evaluate(() => window.scrollBy(0, 600)).catch(() => {});
await page.waitForTimeout(2500);
if (await denied()) { console.log(' ✗ homepage denied — 换 profile 名重试'); await ctx.close(); process.exit(2); }
console.log(' ✓ homepage ok');

// 拿 guest userToken（records 需要）
let userToken = '';
try { const g = await apiGet('https://api.louisvuitton.com/eco-as/lvcom-tkn-handlr-eapi/v1/kor-kr/guest');
  userToken = (JSON.parse(g.body).usid) || ''; } catch {}
console.log(' guest usid:', userToken || '(空)');

const B = 'https://api.louisvuitton.com';
const out = {};
for (const art of ARTS) {
  await page.waitForTimeout(1200 + (art.length % 5) * 300); // 轻微间隔
  const rec = await apiGet(`${B}/eco-eu/search-merch-eapi/v1/kor-kr/records?keyword=${art}&page=0&exclude=store&state=default&userToken=${userToken}`);
  let hit = null, price = null, sellable = null, url = null, nvprod = null, name = null;
  try {
    const d = JSON.parse(rec.body);
    const hits = d.hits || d.records || (d.results && d.results.hits) || [];
    hit = hits[0] || null;
    if (hit) {
      url = hit.url || hit.productUrl || (hit.raw && hit.raw.url) || null;
      name = hit.title || hit.name || (hit.raw && hit.raw.title) || null;
      price = hit.price || hit.priceRaw || (hit.raw && (hit.raw.priceRaw || hit.raw.price)) || null;
      nvprod = url && (url.match(/nvprod\w+/) || [])[0];
    }
  } catch {}
  // 若搜索没直接给价，用商品详情端点补
  if (hit && !price && (nvprod || url)) {
    const dtl = await apiGet(`${B}/eco-as/lvcom-prodct-dtl-eapi/v2/products/kor-kr/skus/${art}${nvprod ? `?productId=${nvprod}` : ''}`);
    try { const p = JSON.parse(dtl.body); price = p.priceRaw; sellable = p.sellable; name = name || p.name; } catch {}
  }
  console.log(`\n[${art}] records=${rec.status}  →`, name || '?', '| priceRaw:', price, '| sellable:', sellable, '| nvprod:', nvprod, '| url:', url);
  out[art] = { records_status: rec.status, name, priceRaw: price, sellable, nvprod, url, raw: rec.body.slice(0, 400) };
}
fs.writeFileSync('tools/_lvapi_out.json', JSON.stringify(out, null, 1));
console.log('\n结果写入 tools/_lvapi_out.json');
await ctx.close();
