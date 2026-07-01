// 关键测试：暖机首页后，用页内同源 fetch 直调「商品详情」服务(lvcom-prodct-dtl-eapi，非被封的 search-merch)。
// 若成立→只要货号(±nvprodId)就能批量取价，绕开所有导航/发现端点。
// 用法: node tools/lv_dtl_fetch.mjs
import { chromium } from 'patchright';
import 'dotenv/config';

const raw = process.env.LV_PROXY || '';
const mm = raw.match(/^https?:\/\/([^:]+):([^@]+)@([^:]+):(\d+)$/);
const proxy = mm ? { server: `http://${mm[3]}:${mm[4]}`, username: mm[1], password: mm[2] } : undefined;
const PROFILE = process.env.LV_PROFILE || 'tools/.lv_profile_df';
console.log('proxy:', proxy && proxy.server, '| profile:', PROFILE);

const ctx = await chromium.launchPersistentContext(PROFILE, {
  headless: false, viewport: null, locale: 'ko-KR', timezoneId: 'Asia/Seoul', proxy,
});
const page = ctx.pages()[0] || await ctx.newPage();
const denied = async () => /Access denied/i.test(await page.content().catch(() => ''));
const apiGet = (url) => page.evaluate(async (u) => {
  try { const r = await fetch(u, { headers: { accept: 'application/json' }, credentials: 'include' });
    const t = await r.text(); return { status: r.status, len: t.length, snippet: t.slice(0, 120) }; }
  catch (e) { return { status: -1, len: 0, snippet: String(e) }; }
}, url);

console.log('→ homepage 暖机');
await page.goto('https://kr.louisvuitton.com/kor-kr/homepage', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(e => console.log(' warn', e.message.split('\n')[0]));
await page.waitForTimeout(5000);
if (await denied()) { console.log(' ✗ homepage denied — 换 profile 名重试'); await ctx.close(); process.exit(2); }
console.log(' ✓ homepage ok\n');

const B = 'https://api.louisvuitton.com/eco-as/lvcom-prodct-dtl-eapi/v2/products/kor-kr/skus';
const tests = [
  ['M29537 +productId', `${B}/M29537?productId=nvprod7830229v`],   // 已知可用组合
  ['M29537 无productId', `${B}/M29537`],                            // 测 productId 是否必填
  ['1AK8BN 无productId', `${B}/1AK8BN`],                            // 用户货号，无 nvprod
  ['M4583  无productId', `${B}/M4583`],
];
for (const [label, url] of tests) {
  await page.waitForTimeout(1500);
  const r = await apiGet(url);
  console.log(`[${label}] ${r.status}  len=${r.len}  ${r.snippet.replace(/\s+/g, ' ')}`);
}
await ctx.close();
