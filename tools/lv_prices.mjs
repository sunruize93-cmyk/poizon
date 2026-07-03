// LV 批量抓价(生产版)：暖机首页拿 Akamai cookie + 抓 client_id/secret →
// 逐货号页内 fetch 商品详情(货号即可,无需 nvprodId) → 写回 config/skus.csv 的 lv_price_krw + 出 data/lv_prices.json。
// 用法: node tools/lv_prices.mjs [货号...]   不带参数=读 config/skus.csv 全部货号
import { chromium } from 'patchright';
import 'dotenv/config';
import fs from 'fs';

const raw = process.env.LV_PROXY || '';
const mm = raw.match(/^https?:\/\/([^:]+):([^@]+)@([^:]+):(\d+)$/);
const proxy = mm ? { server: `http://${mm[3]}:${mm[4]}`, username: mm[1], password: mm[2] } : undefined;
const PROFILE = process.env.LV_PROFILE || 'tools/.lv_profile_px';

// —— 读 skus.csv ——
const CSV = 'config/skus.csv';
const rows = fs.readFileSync(CSV, 'utf8').replace(/\r/g, '').split('\n').filter(Boolean).map(l => l.split(','));
const header = rows[0];
const iArt = header.indexOf('article_no'), iPrice = header.indexOf('lv_price_krw');
const csvArts = rows.slice(1).map(r => r[iArt]).filter(Boolean);
const ARTS = process.argv.slice(2).length ? process.argv.slice(2) : csvArts;
console.log('proxy:', proxy && proxy.server, '| profile:', PROFILE, '| 货号数:', ARTS.length);

const ctx = await chromium.launchPersistentContext(PROFILE, {
  headless: false, viewport: null, locale: 'ko-KR', timezoneId: 'Asia/Seoul', proxy,
});
const page = ctx.pages()[0] || await ctx.newPage();
const denied = async () => /Access denied/i.test(await page.content().catch(() => ''));

let creds = null;
page.on('request', req => {
  if (/lvcom-prodct-dtl-eapi.*\/skus\//i.test(req.url()) && !creds) {
    const h = req.headers(); creds = { client_id: h['client_id'], client_secret: h['client_secret'] };
  }
});

console.log('→ homepage 暖机');
await page.goto('https://kr.louisvuitton.com/kor-kr/homepage', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(e => console.log(' warn', e.message.split('\n')[0]));
await page.waitForTimeout(5000);
if (await denied()) { console.log(' ✗ homepage denied — 换 profile 名重试(LV_PROFILE=tools/.lv_profile_px2)'); await ctx.close(); process.exit(2); }
console.log(' ✓ homepage ok');
for (const t of ['모두 수락', 'Accept All']) { const b = page.getByRole('button', { name: t }); if (await b.count().catch(() => 0)) { await b.first().click().catch(() => {}); break; } }
await page.waitForTimeout(1200);

// 环境变量优先；否则点一个首页商品触发请求抓 client_id/secret
if (process.env.LV_CLIENT_ID && process.env.LV_CLIENT_SECRET) {
  creds = { client_id: process.env.LV_CLIENT_ID, client_secret: process.env.LV_CLIENT_SECRET };
  console.log(' 用 .env 里的 client 凭证');
} else {
  const prods = await page.evaluate(() => Array.from(document.querySelectorAll('a[href*="/products/"]')).map(a => a.href));
  if (prods.length) { await page.locator(`a[href*="${new URL(prods[0]).pathname}"]`).first().click({ timeout: 12000 }).catch(() => {}); await page.waitForTimeout(6000); }
  console.log(' 抓取 client 凭证:', creds ? 'ok' : '失败');
}
if (!creds || !creds.client_id) { console.log(' ✗ 没拿到 client 凭证,退出'); await ctx.close(); process.exit(3); }

const B = 'https://api.louisvuitton.com/eco-as/lvcom-prodct-dtl-eapi/v2/products/kor-kr/skus';
const fetchOne = (art) => page.evaluate(async ({ u, cid, csec, corr }) => {
  try {
    const r = await fetch(u, { headers: { accept: 'application/json', client_id: cid, client_secret: csec, 'x-correlation-id': corr }, credentials: 'include' });
    const t = await r.text(); let d = {}; try { d = JSON.parse(t); } catch {}
    return { status: r.status, priceRaw: d.priceRaw ?? null, sellable: d.sellable ?? null, backOrder: d.backOrder ?? null, name: d.name || '', productId: d.productId || '', color: d.color || '', newArrivalsDate: d.newArrivalsDate ?? null };
  } catch (e) { return { status: -1, err: String(e) }; }
}, { u: `${B}/${art}`, cid: creds.client_id, csec: creds.client_secret, corr: `${Date.now()}-${Math.floor(Math.random() * 99999)}` });

console.log('\n货号            状态  LV价(KRW)   可售  名称');
const results = {};
for (const art of ARTS) {
  await page.waitForTimeout(1100);
  const r = await fetchOne(art);
  results[art] = r;
  const price = r.priceRaw != null ? String(r.priceRaw).padStart(9) : '    —    ';
  const st = r.status === 200 ? '200' : (r.status === 410 ? '410停售' : String(r.status));
  console.log(`${art.padEnd(14)} ${st.padEnd(6)}${price}   ${r.sellable === true ? '可' : r.sellable === false ? '否' : '?'}   ${(r.name || '').slice(0, 24)}`);
}

// 写回 skus.csv 的 lv_price_krw（仅 200 且有价的更新）+ 出 data/lv_prices.json
let updated = 0;
for (let i = 1; i < rows.length; i++) {
  const art = rows[i][iArt]; const r = results[art];
  if (r && r.status === 200 && r.priceRaw != null && iPrice >= 0) {
    if (rows[i][iPrice] !== String(r.priceRaw)) updated++;
    rows[i][iPrice] = String(r.priceRaw);
  }
}
fs.writeFileSync(CSV, rows.map(r => r.join(',')).join('\n') + '\n');
fs.mkdirSync('data', { recursive: true });
// 合并已有价格(增量抓取累积,不覆盖之前的)
let merged = {};
try { merged = JSON.parse(fs.readFileSync('data/lv_prices.json', 'utf8')).results || {}; } catch {}
Object.assign(merged, results);
fs.writeFileSync('data/lv_prices.json', JSON.stringify({ fetchedAt: new Date().toISOString(), results: merged }, null, 1));
console.log(`\n✓ 写回 ${CSV}: 更新 ${updated} 个价格 | 本次 ${Object.keys(results).length} 款 | 累计 ${Object.keys(merged).length} → data/lv_prices.json`);
await ctx.close();
