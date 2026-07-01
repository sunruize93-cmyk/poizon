// LV 搜索 UI 自动化(诊断+动作一把梭)：暖机→找搜索框(dump真实DOM)→逐字键入货号→
// 触发 records 搜索→抓商品结果→点进 PDP→拦 prodct-dtl 价格。verbose 日志便于学 DOM。
// 用法: node tools/lv_search2.mjs 1AK8BN
import { chromium } from 'patchright';
import 'dotenv/config';
import fs from 'fs';

const raw = process.env.LV_PROXY || '';
const mm = raw.match(/^https?:\/\/([^:]+):([^@]+)@([^:]+):(\d+)$/);
const proxy = mm ? { server: `http://${mm[3]}:${mm[4]}`, username: mm[1], password: mm[2] } : undefined;
const PROFILE = process.env.LV_PROFILE || 'tools/.lv_profile_ss';
const ART = process.argv[2] || '1AK8BN';
console.log('proxy:', proxy && proxy.server, '| profile:', PROFILE, '| 货号:', ART);

const ctx = await chromium.launchPersistentContext(PROFILE, {
  headless: false, viewport: null, locale: 'ko-KR', timezoneId: 'Asia/Seoul', proxy,
});
const page = ctx.pages()[0] || await ctx.newPage();
const xhr = [];
page.on('response', async r => {
  try { const u = r.url(); if (!/louisvuitton\.com|vuitton\.net|search4retail/i.test(u)) return;
    if (!/(records|autocomplete|prodct-dtl|search-merch|search4retail|autocomplete|browse|retail)/i.test(u)) return;
    let b = ''; try { b = await r.text(); } catch {}
    xhr.push({ status: r.status(), url: u, body: b });
    console.log('   [XHR]', r.status(), u.replace(/https:\/\/[^/]+/, '').slice(0, 95));
  } catch {}
});
const denied = async () => /Access denied/i.test(await page.content().catch(() => ''));

console.log('→ homepage 暖机');
await page.goto('https://kr.louisvuitton.com/kor-kr/homepage', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(e => console.log(' warn', e.message.split('\n')[0]));
await page.waitForTimeout(5000);
if (await denied()) { console.log(' ✗ homepage denied — 换 profile 名重试'); await ctx.close(); process.exit(2); }
console.log(' ✓ homepage ok:', await page.title());
for (const t of ['모두 수락', 'Accept All', '동의']) { const b = page.getByRole('button', { name: t }); if (await b.count().catch(() => 0)) { await b.first().click().catch(() => {}); console.log(' cookie 同意:', t); break; } }
await page.waitForTimeout(1500);

// —— 诊断：dump 页面里所有可能的搜索控件 ——
const diag = await page.evaluate(() => {
  const desc = el => ({ tag: el.tagName, type: el.type || '', name: el.name || '', id: el.id || '',
    aria: el.getAttribute('aria-label') || '', ph: el.getAttribute('placeholder') || '',
    cls: (el.className || '').toString().slice(0, 60), txt: (el.innerText || '').trim().slice(0, 20),
    href: el.getAttribute && (el.getAttribute('href') || '') });
  const inputs = Array.from(document.querySelectorAll('input')).map(desc);
  const searchBtns = Array.from(document.querySelectorAll('button,a,[role=button]'))
    .filter(e => /search|검색/i.test((e.getAttribute('aria-label') || '') + (e.className || '') + (e.getAttribute('data-testid') || '') + (e.getAttribute('href') || '')))
    .map(desc).slice(0, 10);
  return { inputs, searchBtns };
});
console.log(' [DOM] inputs:', JSON.stringify(diag.inputs).slice(0, 400));
console.log(' [DOM] search控件:', JSON.stringify(diag.searchBtns).slice(0, 500));

// —— 动作：点开搜索 → 逐字键入 → 等 records ——
async function tryClick(sel) { const el = page.locator(sel).first(); if (await el.count().catch(() => 0)) { await el.click({ timeout: 5000 }).catch(() => {}); return true; } return false; }
for (const s of ['button[aria-label*="검색" i]', 'button[aria-label*="search" i]', '[data-testid*="search" i]', 'a[href*="/search"]', 'button:has(svg[aria-label*="search" i])']) {
  if (await tryClick(s)) { console.log(' 点开搜索:', s); break; }
}
await page.waitForTimeout(1800);
// 点开搜索后再 dump 一次(输入框在遮罩层里)
const diag2 = await page.evaluate(() => Array.from(document.querySelectorAll('input')).map(el => ({ type: el.type, name: el.name, id: el.id, aria: el.getAttribute('aria-label') || '', ph: el.getAttribute('placeholder') || '' })));
console.log(' [DOM2] 打开后 inputs:', JSON.stringify(diag2).slice(0, 300));
const input = page.locator('input[type="search"], input[name*="search" i], input[placeholder*="검색" i], input[aria-label*="검색" i], input:visible').first();
if (await input.count().catch(() => 0)) {
  await input.click().catch(() => {});
  await page.keyboard.type(ART, { delay: 150 });   // 逐字触发真实结果
  console.log(' 已键入货号,等遮罩层结果(不回车)...');
  await page.waitForTimeout(5000);
} else { console.log(' ✗ 没定位到搜索输入框(看上面 DOM dump 调选择器)'); }

console.log(' 当前 url:', page.url().slice(0, 90), '| denied?', await denied());

// 抓遮罩层里的商品链接 + 全部链接样本
const linkInfo = await page.evaluate(() => {
  const prod = Array.from(document.querySelectorAll('a[href*="/products/"]')).map(a => a.href);
  const sample = Array.from(document.querySelectorAll('a[href]')).map(a => a.getAttribute('href')).filter(h => /product|search|1ak|result/i.test(h)).slice(0, 12);
  return { prod: [...new Set(prod)].slice(0, 6), sample: [...new Set(sample)].slice(0, 12) };
});
console.log(' 遮罩层商品链接:', linkInfo.prod.length, linkInfo.prod[0] || '');
console.log(' 相关链接样本:', JSON.stringify(linkInfo.sample).slice(0, 400));
const prods = linkInfo.prod;
if (prods.length) {
  await page.locator(`a[href*="${new URL(prods[0]).pathname}"]`).first().click({ timeout: 12000 }).catch(e => console.log(' click warn', e.message.split('\n')[0]));
  await page.waitForTimeout(8000);
  console.log(' PDP url:', page.url().slice(0, 90), '| denied?', await denied());
}

// 汇总价格
for (const h of xhr.filter(j => /prodct-dtl.*\/skus\//i.test(j.url))) {
  try { const d = JSON.parse(h.body); console.log(` ★ 价格: ${d.name} priceRaw=${d.priceRaw} sellable=${d.sellable} nvprod=${(h.url.match(/nvprod\w+/) || [])[0]}`); } catch {}
}
await page.screenshot({ path: 'tools/_lvss.png' }).catch(() => {});
fs.writeFileSync('tools/_lvss_all.json', JSON.stringify(xhr, null, 1));
console.log('\n完. 详见 tools/_lvss_all.json / _lvss.png');
await ctx.close();
