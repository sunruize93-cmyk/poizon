// 验证「注入锚点点击」绕 Akamai：暖机首页→往 DOM 注入目标 PDP 链接→点击(同源 SPA 路由)→抓价。
// 若成立：货号→PDP URL 可用外部(Google/目录)解析,再批量注入点击取价,绕开被 403 的站内搜索。
// 用法: node tools/lv_inject.mjs /kor-kr/products/nano-frivole-monogram-nvprod7830229v/M29537 [更多PDP路径]
import { chromium } from 'patchright';
import 'dotenv/config';
import fs from 'fs';

const raw = process.env.LV_PROXY || '';
const mm = raw.match(/^https?:\/\/([^:]+):([^@]+)@([^:]+):(\d+)$/);
const proxy = mm ? { server: `http://${mm[3]}:${mm[4]}`, username: mm[1], password: mm[2] } : undefined;
const PROFILE = process.env.LV_PROFILE || 'tools/.lv_profile_inj';
const PATHS = process.argv.slice(2);
if (!PATHS.length) { console.log('用法: node tools/lv_inject.mjs /kor-kr/products/... [...]'); process.exit(1); }
console.log('proxy:', proxy && proxy.server, '| profile:', PROFILE, '| PDP:', PATHS.length);

const ctx = await chromium.launchPersistentContext(PROFILE, {
  headless: false, viewport: null, locale: 'ko-KR', timezoneId: 'Asia/Seoul', proxy,
});
const page = ctx.pages()[0] || await ctx.newPage();
const prices = {};
page.on('response', async r => {
  try { const u = r.url(); if (!/prodct-dtl.*\/skus\//i.test(u)) return;
    const b = await r.text(); const d = JSON.parse(b);
    const art = (u.match(/\/skus\/([^/?]+)/) || [])[1];
    prices[art] = { name: d.name, priceRaw: d.priceRaw, sellable: d.sellable, backOrder: d.backOrder, nvprod: (u.match(/nvprod\w+/) || [])[0] };
    console.log('   ★', art, d.name, 'priceRaw=' + d.priceRaw, 'sellable=' + d.sellable);
  } catch {}
});
const denied = async () => /Access denied/i.test(await page.content().catch(() => ''));

console.log('→ homepage 暖机');
await page.goto('https://kr.louisvuitton.com/kor-kr/homepage', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(e => console.log(' warn', e.message.split('\n')[0]));
await page.waitForTimeout(5000);
if (await denied()) { console.log(' ✗ homepage denied — 换 profile 名重试'); await ctx.close(); process.exit(2); }
console.log(' ✓ homepage ok');
await page.mouse.move(500, 400); await page.evaluate(() => window.scrollBy(0, 500)).catch(() => {});
await page.waitForTimeout(2000);

for (const p of PATHS) {
  console.log('\n=== 注入并点击:', p, '===');
  // 注入一个可见锚点到页面顶部
  await page.evaluate((href) => {
    let a = document.getElementById('__inj');
    if (!a) { a = document.createElement('a'); a.id = '__inj'; a.textContent = 'go';
      a.style.cssText = 'position:fixed;top:8px;left:8px;z-index:99999;background:#fff;padding:6px'; document.body.appendChild(a); }
    a.setAttribute('href', href);
  }, p);
  await page.waitForTimeout(800);
  await page.locator('#__inj').click({ timeout: 10000 }).catch(e => console.log(' click warn', e.message.split('\n')[0]));
  await page.waitForTimeout(7000);
  console.log(' 落地 url:', page.url().slice(0, 90), '| denied?', await denied());
  // 若 SPA 没触发详情接口，尝试滚动激活
  await page.evaluate(() => window.scrollBy(0, 800)).catch(() => {});
  await page.waitForTimeout(3000);
  // 回首页以便下一次注入(保持同源会话)
  if (PATHS.indexOf(p) < PATHS.length - 1) {
    await page.evaluate(() => history.pushState({}, '', '/kor-kr/homepage')).catch(() => {});
    await page.waitForTimeout(1500);
  }
}
fs.writeFileSync('tools/_lvinj_out.json', JSON.stringify(prices, null, 1));
console.log('\n结果:', JSON.stringify(prices));
await page.screenshot({ path: 'tools/_lvinj.png' }).catch(() => {});
await ctx.close();
