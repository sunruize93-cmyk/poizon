// LV PDP 价格提取：站内导航(已验证可绕 Akamai)进 PDP 后，全量抓 JSON XHR + 页面内嵌数据找价格。
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

const allJson = [];
page.on('response', async r => {
  try {
    const u = r.url();
    if (!/louisvuitton\.com/i.test(u)) return;
    const ct = r.headers()['content-type'] || '';
    if (!ct.includes('json')) return;
    let b; try { b = await r.text(); } catch { return; }
    allJson.push({ status: r.status(), url: u, len: b.length, body: b });
  } catch {}
});
const human = async (ms) => { await page.mouse.move(300 + (ms % 400), 200 + (ms % 300)); await page.evaluate(d => window.scrollBy(0, d), 400).catch(() => {}); await page.waitForTimeout(ms); };
const denied = async () => { const c = await page.content().catch(() => ''); return /Access denied/i.test(c); };

console.log('→ homepage');
await page.goto('https://kr.louisvuitton.com/kor-kr/homepage', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(e => console.log(' warn', e.message.split('\n')[0]));
await human(4000);
if (await denied()) { console.log(' ✗ homepage denied'); await ctx.close(); process.exit(2); }
for (const t of ['모두 수락', 'Accept All', '동의']) { const b = page.getByRole('button', { name: t }); if (await b.count().catch(() => 0)) { await b.first().click().catch(() => {}); break; } }
await human(2500);

const prods = await page.evaluate(() => Array.from(document.querySelectorAll('a[href*="/products/"]')).map(a => a.href));
console.log(' 商品链接:', prods.length);
const path = new URL(prods[0]).pathname;
console.log(' → 点击:', path);
await page.locator(`a[href*="${path}"]`).first().scrollIntoViewIfNeeded().catch(() => {});
await human(1500);
await page.locator(`a[href*="${path}"]`).first().click({ timeout: 15000 }).catch(e => console.log(' click warn', e.message.split('\n')[0]));
await page.waitForTimeout(9000);
await page.evaluate(() => window.scrollBy(0, 1000)).catch(() => {});
await page.waitForTimeout(4000);
console.log(' PDP denied?', await denied(), 'url:', page.url().slice(0, 80));

// 1) 页面可见价（符号前/后都认）
const dom = await page.evaluate(() => {
  const t = document.body.innerText;
  const rx = /(₩\s*[\d,]{5,}|[\d,]{5,}\s*원|KRW\s*[\d,]{5,})/g;
  const prices = [...new Set((t.match(rx) || []))].slice(0, 6);
  // JSON-LD 结构化数据
  const ld = Array.from(document.querySelectorAll('script[type="application/ld+json"]')).map(s => s.textContent).filter(x => /price|offer/i.test(x)).slice(0, 3);
  // 内嵌 state（Salesforce/Next 常见挂载点）
  const stateKeys = Object.keys(window).filter(k => /state|initial|product|__|apollo|redux/i.test(k)).slice(0, 20);
  return { prices, ld, stateKeys, title: document.title };
});
console.log(' 可见价:', dom.prices);
console.log(' JSON-LD:', dom.ld.map(x => x.slice(0, 120)));
console.log(' window state keys:', dom.stateKeys);

// 2) 全量 JSON XHR 里带价的
const withPrice = allJson.filter(j => /price|amount|"listPrice|salePrice|"value":\s*\d{5,}/i.test(j.body));
console.log('--- JSON XHR 总数:', allJson.length, '| 含价关键词:', withPrice.length, '---');
for (const j of withPrice) console.log(j.status, j.url.slice(0, 120), 'len=' + j.len, '|', (j.body.match(/.{0,30}(price|amount)[^,}]{0,40}/i) || [''])[0].replace(/\s+/g, ' '));
console.log('--- 所有 eco-as/api JSON 端点 ---');
for (const j of allJson.filter(j => /api\.louisvuitton|eco-as|eco-eu|catalog|product/i.test(j.url))) console.log(j.status, j.url.slice(0, 130));

await page.screenshot({ path: 'tools/_lvx.png' }).catch(() => {});
fs.writeFileSync('tools/_lvx_all.json', JSON.stringify(allJson, null, 1));
await ctx.close();
