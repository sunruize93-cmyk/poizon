// LV 按货号抓价：全新 profile → 首页 → 站内搜索货号 → 抓 eco-as 搜索/商品 XHR(含价+nvprodId)。
// 用法: node tools/lv_search.mjs 1AK8BN [货号2 ...]
import { chromium } from 'patchright';
import 'dotenv/config';
import fs from 'fs';

const raw = process.env.LV_PROXY || '';
const m = raw.match(/^https?:\/\/([^:]+):([^@]+)@([^:]+):(\d+)$/);
const proxy = m ? { server: `http://${m[3]}:${m[4]}`, username: m[1], password: m[2] } : undefined;
// 每次全新 profile（封禁是 profile 级；用时间无关的递增名，靠 argv 传入避免 Date）
const PROFILE = process.env.LV_PROFILE || 'tools/.lv_profile_s1';
const ARTS = process.argv.slice(2);
if (!ARTS.length) { console.log('用法: node tools/lv_search.mjs 货号 [货号...]'); process.exit(1); }
console.log('proxy:', proxy && proxy.server, '| profile:', PROFILE, '| 货号:', ARTS.join(','));

const ctx = await chromium.launchPersistentContext(PROFILE, {
  headless: false, viewport: null, locale: 'ko-KR', timezoneId: 'Asia/Seoul', proxy,
});
const page = ctx.pages()[0] || await ctx.newPage();
const allJson = [];
page.on('response', async r => {
  try { const u = r.url(); if (!/louisvuitton\.com/i.test(u)) return;
    if (!(r.headers()['content-type'] || '').includes('json')) return;
    let b; try { b = await r.text(); } catch { return; }
    allJson.push({ status: r.status(), url: u, body: b });
  } catch {}
});
const human = async (ms) => { await page.mouse.move(300 + (ms % 400), 200 + (ms % 300)); await page.waitForTimeout(ms); };
const denied = async () => /Access denied/i.test(await page.content().catch(() => ''));

console.log('→ homepage'); await page.goto('https://kr.louisvuitton.com/kor-kr/homepage', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(e => console.log(' warn', e.message.split('\n')[0]));
await human(4000);
if (await denied()) { console.log(' ✗ homepage denied — 换个 profile 名重试(LV_PROFILE=tools/.lv_profile_s2)'); await ctx.close(); process.exit(2); }
for (const t of ['모두 수락', 'Accept All', '동의']) { const b = page.getByRole('button', { name: t }); if (await b.count().catch(() => 0)) { await b.first().click().catch(() => {}); break; } }
await human(2000);

const results = {};
for (const art of ARTS) {
  const before = allJson.length;
  console.log(`\n=== 搜索 ${art} ===`);
  // 打开搜索框：常见为 header 的搜索按钮，回退到直接聚焦 input
  const openers = ['button[aria-label*="검색" i]', 'button[aria-label*="search" i]', 'a[href*="/search"]', '[data-testid*="search" i]'];
  for (const s of openers) { const el = page.locator(s).first(); if (await el.count().catch(() => 0)) { await el.click({ timeout: 5000 }).catch(() => {}); break; } }
  await human(1500);
  const input = page.locator('input[type="search"], input[name*="search" i], input[placeholder*="검색" i], input[aria-label*="검색" i]').first();
  if (await input.count().catch(() => 0)) {
    await input.click().catch(() => {}); await input.fill(art).catch(() => {});
    await page.keyboard.press('Enter').catch(() => {});
  } else {
    console.log(' 未找到搜索框,回退站内导航 goto /search'); // 同源导航(非冷启动深链)
    await page.evaluate(a => { location.assign(`/kor-kr/search/${a}`); }, art).catch(() => {});
  }
  await human(6000);
  console.log(' denied?', await denied(), 'url:', page.url().slice(0, 80));
  // 点第一个商品结果进 PDP（触发 prodct-dtl 价格接口）
  const link = page.locator('a[href*="/products/"]').first();
  if (await link.count().catch(() => 0)) {
    const href = await link.getAttribute('href').catch(() => '');
    console.log(' 首个结果:', href);
    await link.click({ timeout: 12000 }).catch(e => console.log(' click warn', e.message.split('\n')[0]));
    await human(7000);
  } else console.log(' 无商品结果链接');
  // 汇总本轮抓到的价格接口
  const priceHits = allJson.slice(before).filter(j => /prodct-dtl.*\/skus\/|"priceRaw"|search/i.test(j.url + j.body));
  for (const h of priceHits) {
    let info = ''; try { const d = JSON.parse(h.body); if (d.priceRaw) info = `${d.name} priceRaw=${d.priceRaw} sellable=${d.sellable}`; } catch {}
    console.log(' ', h.status, h.url.slice(0, 110), info && '| ' + info);
  }
  results[art] = priceHits.map(h => ({ url: h.url, status: h.status }));
  await human(1500);
}
await page.screenshot({ path: 'tools/_lvsearch.png' }).catch(() => {});
fs.writeFileSync('tools/_lvsearch_all.json', JSON.stringify(allJson, null, 1));
await ctx.close();
