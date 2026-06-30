// LV 韩国抓价：patchright 真人化站内导航(首页→列表→点商品卡)绕 Akamai PDP 校验。
// 不深链 goto 商品页。用法: node tools/lv_fetch.mjs
// 环境: LV_PROXY(可选,.env), LV_PROFILE(可选,默认全新 profile 避开已被标记的 .lv_profile)
import { chromium } from 'patchright';
import 'dotenv/config';
import fs from 'fs';

const raw = process.env.LV_PROXY || '';
const m = raw.match(/^https?:\/\/([^:]+):([^@]+)@([^:]+):(\d+)$/);
const proxy = m ? { server: `http://${m[3]}:${m[4]}`, username: m[1], password: m[2] } : undefined;
const PROFILE = process.env.LV_PROFILE || 'tools/.lv_profile_fresh';
console.log('proxy:', proxy && proxy.server, '| profile:', PROFILE);

const ctx = await chromium.launchPersistentContext(PROFILE, {
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
const denied = async () => { const c = await page.content().catch(() => ''); return /Access denied/i.test(c) || c.includes('Accès refusé'); };
const human = async (ms) => { await page.mouse.move(300 + Math.floor(ms % 400), 200 + Math.floor(ms % 300)); await page.evaluate(d => window.scrollBy(0, d), 300 + (ms % 500)).catch(() => {}); await page.waitForTimeout(ms); };

console.log('→ homepage');
await page.goto('https://kr.louisvuitton.com/kor-kr/homepage', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(e => console.log(' warn', e.message.split('\n')[0]));
await human(4000);
if (await denied()) { console.log(' ✗ homepage Access Denied — IP/profile 仍被标记,需更久冷却或换 IP'); await page.screenshot({ path: 'tools/_lvf_denied.png' }).catch(() => {}); await ctx.close(); process.exit(2); }
console.log(' ✓ homepage ok:', await page.title());

// 处理 cookie 同意条(若有)
for (const t of ['모두 수락', 'Accept All', '동의']) { const b = page.getByRole('button', { name: t }); if (await b.count().catch(() => 0)) { await b.first().click().catch(() => {}); break; } }
await human(2500);

// 真人化站内导航：优先直接点商品链接；没有则进一个分类列表页再点商品卡
async function collectProducts() {
  return await page.evaluate(() => Array.from(document.querySelectorAll('a[href*="/products/"]')).map(a => a.href));
}
let prods = await collectProducts();
console.log(' homepage 商品链接:', prods.length);
if (!prods.length) {
  const cats = await page.evaluate(() => Array.from(document.querySelectorAll('a[href*="/kor-kr/"]'))
    .map(a => a.href).filter(h => /\/(men|women|man|woman|shoes|bags|handbags|wallets|gifts|new)/i.test(h)));
  console.log(' 候选分类:', cats.length, cats[0] || '');
  if (cats.length) {
    await page.locator(`a[href="${new URL(cats[0]).pathname}"]`).first().click({ timeout: 12000 }).catch(() => page.goto(cats[0], { waitUntil: 'domcontentloaded' }).catch(() => {}));
    await human(6000);
    console.log(' 分类页 denied?', await denied(), 'url:', page.url().slice(0, 70));
    prods = await collectProducts();
    console.log(' 列表页商品链接:', prods.length);
  }
}

if (prods.length) {
  const path = new URL(prods[0]).pathname;
  console.log(' → 点击商品:', path);
  await page.locator(`a[href*="${path}"]`).first().scrollIntoViewIfNeeded().catch(() => {});
  await human(1500);
  await page.locator(`a[href*="${path}"]`).first().click({ timeout: 15000 }).catch(e => console.log(' click warn', e.message.split('\n')[0]));
  await human(7000);
  console.log(' PDP denied?', await denied(), 'url:', page.url().slice(0, 80));
  const price = await page.evaluate(() => { const m = document.body.innerText.match(/[\d,]{6,}\s*(원|₩|KRW)/); return m ? m[0] : null; });
  console.log(' visible price:', price, '| 货号:', (page.url().match(/\/(M\d{5}\w*|N\d{5}\w*)/) || [])[1] || '?');
}
await page.screenshot({ path: 'tools/_lvf.png' }).catch(() => {});
console.log('--- price XHR:', hits.length, '---');
for (const h of hits) console.log(h.status, h.url.slice(0, 130), 'len=' + h.len, '|', h.body.slice(0, 70).replace(/\s+/g, ' '));
fs.writeFileSync('tools/_lvf_full.json', JSON.stringify(hits, null, 1));
await ctx.close();
