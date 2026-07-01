// LV 类目抓取(诊断)：暖机首页→dump 类目导航链接→SPA 点进一个类目→列表页扫商品+价+抓 browse XHR。
// 用法: node tools/lv_category.mjs [类目关键词，默认 sneaker]
import { chromium } from 'patchright';
import 'dotenv/config';
import fs from 'fs';

const raw = process.env.LV_PROXY || '';
const mm = raw.match(/^https?:\/\/([^:]+):([^@]+)@([^:]+):(\d+)$/);
const proxy = mm ? { server: `http://${mm[3]}:${mm[4]}`, username: mm[1], password: mm[2] } : undefined;
const PROFILE = process.env.LV_PROFILE || 'tools/.lv_profile_cat';
const KW = (process.argv[2] || 'sneaker|스니커즈|운동화|신발|shoe').toLowerCase();
console.log('proxy:', proxy && proxy.server, '| profile:', PROFILE, '| 类目关键词:', KW);

const ctx = await chromium.launchPersistentContext(PROFILE, {
  headless: false, viewport: null, locale: 'ko-KR', timezoneId: 'Asia/Seoul', proxy,
});
const page = ctx.pages()[0] || await ctx.newPage();
const xhr = [];
page.on('response', async r => {
  try { const u = r.url(); if (!/louisvuitton\.com|vuitton\.net/i.test(u)) return;
    if (!/(catalog|browse|plp|product|category|list|nvcat|eco-)/i.test(u)) return;
    if (!(r.headers()['content-type'] || '').includes('json')) return;
    let b = ''; try { b = await r.text(); } catch {}
    xhr.push({ status: r.status(), url: u, len: b.length, body: b });
    if (/priceRaw|"price"|nvprod/i.test(b)) console.log('   [XHR含价]', r.status(), u.replace(/https:\/\/[^/]+/, '').slice(0, 85), 'len=' + b.length);
  } catch {}
});
const denied = async () => /Access denied/i.test(await page.content().catch(() => ''));

console.log('→ homepage 暖机');
await page.goto('https://kr.louisvuitton.com/kor-kr/homepage', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(e => console.log(' warn', e.message.split('\n')[0]));
await page.waitForTimeout(5000);
if (await denied()) { console.log(' ✗ homepage denied — 换 profile 名重试'); await ctx.close(); process.exit(2); }
console.log(' ✓ homepage ok');
for (const t of ['모두 수락', 'Accept All', '동의']) { const b = page.getByRole('button', { name: t }); if (await b.count().catch(() => 0)) { await b.first().click().catch(() => {}); break; } }
await page.waitForTimeout(1500);
await page.evaluate(() => window.scrollBy(0, 400)).catch(() => {});
await page.waitForTimeout(1500);

// dump 所有类目导航链接
const nav = await page.evaluate(() => Array.from(document.querySelectorAll('a[href*="/kor-kr/"]'))
  .map(a => ({ href: a.getAttribute('href'), txt: (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 16) }))
  .filter(x => x.href && !/homepage|account|store-locator|contact|legal|privacy|faq/i.test(x.href)));
const uniq = [...new Map(nav.map(x => [x.href, x])).values()];
console.log(' 导航链接总数:', uniq.length);
const catLinks = uniq.filter(x => new RegExp(KW, 'i').test(x.href + x.txt) || /\/(men|women|shoes|handbags|bags|wallets|belts|신발|가방|지갑|벨트)/i.test(x.href));
console.log(' 疑似类目链接:', JSON.stringify(catLinks.slice(0, 20)).slice(0, 700));

// 挑一个匹配关键词的类目，SPA 点击进入
const target = catLinks.find(x => new RegExp(KW, 'i').test(x.href + x.txt)) || catLinks[0];
if (target) {
  console.log('\n→ SPA 点进类目:', target.href, target.txt);
  await page.locator(`a[href="${target.href}"]`).first().scrollIntoViewIfNeeded().catch(() => {});
  await page.waitForTimeout(1000);
  await page.locator(`a[href="${target.href}"]`).first().click({ timeout: 12000 }).catch(e => console.log(' click warn', e.message.split('\n')[0]));
  await page.waitForTimeout(8000);
  console.log(' 列表页 url:', page.url().slice(0, 90), '| denied?', await denied());
  await page.evaluate(() => window.scrollBy(0, 1500)).catch(() => {});
  await page.waitForTimeout(4000);
  // 列表页商品 + 可见价
  const plp = await page.evaluate(() => {
    const cards = Array.from(document.querySelectorAll('a[href*="/products/"]'));
    const items = cards.map(a => {
      const box = a.closest('li,article,div') || a;
      const pm = (box.innerText || '').match(/(₩\s*[\d,]{5,}|[\d,]{5,}\s*원)/);
      return { href: a.getAttribute('href'), price: pm ? pm[0] : null };
    });
    return [...new Map(items.map(x => [x.href, x])).values()].slice(0, 15);
  });
  console.log(' 列表页商品数:', plp.length);
  for (const it of plp.slice(0, 12)) console.log('   ', it.price || '(无价)', it.href);
}
fs.writeFileSync('tools/_lvcat_all.json', JSON.stringify(xhr, null, 1));
console.log('\n抓到 JSON XHR:', xhr.length, '(详见 tools/_lvcat_all.json)');
await page.screenshot({ path: 'tools/_lvcat.png' }).catch(() => {});
await ctx.close();
