// 决定性测试：真实 PDP 导航→抓 prodct-dtl 请求的 Authorization/头→同会话内用这套头
// 重放 prodct-dtl 取任意货号价。若成立=拿到 bearer 即可批量按货号取价(±nvprodId 也一并验证)。
// 用法: node tools/lv_auth_replay.mjs
import { chromium } from 'patchright';
import 'dotenv/config';
import fs from 'fs';

const raw = process.env.LV_PROXY || '';
const mm = raw.match(/^https?:\/\/([^:]+):([^@]+)@([^:]+):(\d+)$/);
const proxy = mm ? { server: `http://${mm[3]}:${mm[4]}`, username: mm[1], password: mm[2] } : undefined;
const PROFILE = process.env.LV_PROFILE || 'tools/.lv_profile_ar';
console.log('proxy:', proxy && proxy.server, '| profile:', PROFILE);

const ctx = await chromium.launchPersistentContext(PROFILE, {
  headless: false, viewport: null, locale: 'ko-KR', timezoneId: 'Asia/Seoul', proxy,
});
const page = ctx.pages()[0] || await ctx.newPage();
const denied = async () => /Access denied/i.test(await page.content().catch(() => ''));

// 抓 prodct-dtl 请求头
let capturedHeaders = null;
page.on('request', req => {
  const u = req.url();
  if (/lvcom-prodct-dtl-eapi.*\/skus\//i.test(u) && !capturedHeaders) {
    capturedHeaders = req.headers();
    console.log('   [捕获 prodct-dtl 请求头]', Object.keys(capturedHeaders).filter(k => /auth|token|key|x-|client/i.test(k)).join(','));
  }
});

console.log('→ homepage 暖机');
await page.goto('https://kr.louisvuitton.com/kor-kr/homepage', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(e => console.log(' warn', e.message.split('\n')[0]));
await page.waitForTimeout(5000);
if (await denied()) { console.log(' ✗ homepage denied'); await ctx.close(); process.exit(2); }
console.log(' ✓ homepage ok');
for (const t of ['모두 수락', 'Accept All']) { const b = page.getByRole('button', { name: t }); if (await b.count().catch(() => 0)) { await b.first().click().catch(() => {}); break; } }
await page.waitForTimeout(1500);

// SPA 点一个真实商品 → 触发真实 prodct-dtl 请求(拿 bearer)
const prods = await page.evaluate(() => Array.from(document.querySelectorAll('a[href*="/products/"]')).map(a => a.href));
console.log(' 首页商品链:', prods.length);
if (prods.length) {
  const path = new URL(prods[0]).pathname;
  await page.locator(`a[href*="${path}"]`).first().click({ timeout: 12000 }).catch(e => console.log(' click warn', e.message.split('\n')[0]));
  await page.waitForTimeout(7000);
  console.log(' PDP denied?', await denied());
}
console.log(' 是否抓到头:', !!capturedHeaders, '| authorization:', capturedHeaders && (capturedHeaders['authorization'] || '(无)').slice(0, 25));

// 用捕获的头重放 prodct-dtl 取用户货号
const hdrs = capturedHeaders || {};
const apiGet = (url, headers) => page.evaluate(async ({ u, h }) => {
  try { const r = await fetch(u, { headers: h, credentials: 'include' });
    const t = await r.text(); let price = null; try { price = JSON.parse(t).priceRaw; } catch {}
    return { status: r.status, len: t.length, price, snippet: t.slice(0, 90) }; }
  catch (e) { return { status: -1, snippet: String(e) }; }
}, { u: url, h: headers });

const B = 'https://api.louisvuitton.com/eco-as/lvcom-prodct-dtl-eapi/v2/products/kor-kr/skus';
const replayHdrs = { accept: 'application/json' };
for (const k of Object.keys(hdrs)) if (/^authorization$|token|^x-|client|^apikey$/i.test(k)) replayHdrs[k] = hdrs[k];
console.log('\n重放用头:', Object.keys(replayHdrs).join(','));
const out = {};
for (const [label, url] of [
  ['M29537 +pid', `${B}/M29537?productId=nvprod7830229v`],
  ['1AK8BN', `${B}/1AK8BN`],
  ['M4583', `${B}/M4583`],
]) {
  await page.waitForTimeout(1500);
  const r = await apiGet(url, replayHdrs);
  console.log(`[${label}] ${r.status}  price=${r.price}  ${(r.snippet || '').replace(/\s+/g, ' ')}`);
  out[label] = r;
}
fs.writeFileSync('tools/_lvar_out.json', JSON.stringify({ headers: hdrs, out }, null, 1));
await ctx.close();
