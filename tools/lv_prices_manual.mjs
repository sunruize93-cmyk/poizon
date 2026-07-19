// LV 抓价(半自动/人工过 Akamai 版)：自动暖机被 Akamai 封时用这个。
// 开一个隐身窗口 → 用户手动打开 kr.louisvuitton.com 并点进任意商品(真人过 Akamai)→
// 脚本从该 PDP 触发的 API 请求里抓到 client_id/secret(=有效会话)后，自动逐货号 fetch 抓价 →
// 合并写 data/lv_prices.json + 回写 config/skus.csv 的 lv_price_krw（逻辑与 lv_prices.mjs 一致）。
// 用法: LV_PROFILE=tools/.lv_profile_m$(date +%s) node tools/lv_prices_manual.mjs 货号1 货号2 ...
import { chromium } from 'patchright';
import 'dotenv/config';
import fs from 'fs';

const raw = process.env.LV_PROXY || '';
const mm = raw.match(/^https?:\/\/([^:]+):([^@]+)@([^:]+):(\d+)$/);
const proxy = mm ? { server: `http://${mm[3]}:${mm[4]}`, username: mm[1], password: mm[2] } : undefined;
const PROFILE = process.env.LV_PROFILE || 'tools/.lv_profile_manual';
const WAIT_MS = Number(process.env.LV_WAIT_MS || 360000); // 等用户操作最多 6 分钟

const CSV = 'config/skus.csv';
const rows = fs.readFileSync(CSV, 'utf8').replace(/\r/g, '').split('\n').filter(Boolean).map(l => l.split(','));
const header = rows[0];
const iArt = header.indexOf('article_no'), iPrice = header.indexOf('lv_price_krw');
const csvArts = rows.slice(1).map(r => r[iArt]).filter(Boolean);
const ARTS = process.argv.slice(2).length ? process.argv.slice(2) : csvArts;
console.log('proxy:', proxy && proxy.server, '| profile:', PROFILE, '| 货号数:', ARTS.length);

const sleep = ms => new Promise(r => setTimeout(r, ms));
let browserAlive = true;
const ctx = await chromium.launchPersistentContext(PROFILE, {
  headless: false, viewport: null, locale: 'ko-KR', timezoneId: 'Asia/Seoul', proxy,
});
ctx.on('close', () => { browserAlive = false; });
const page = ctx.pages()[0] || await ctx.newPage();

// 抓 client 凭证：用户浏览任意页面时 LV 的 JS 会带 client_id/secret 打 api.louisvuitton.com
let creds = process.env.LV_CLIENT_ID && process.env.LV_CLIENT_SECRET
  ? { client_id: process.env.LV_CLIENT_ID, client_secret: process.env.LV_CLIENT_SECRET } : null;
const grab = req => {
  if (/api\.louisvuitton\.com/i.test(req.url()) && !creds) {
    const h = req.headers();
    if (h['client_id'] && h['client_secret']) { creds = { client_id: h['client_id'], client_secret: h['client_secret'] }; }
  }
};
ctx.on('request', grab); // 监听整个 context（含用户新开的标签页）

// 给个起点，被 Access Denied 也没关系——用户手动刷新/操作即可。别绑死这个 page 句柄。
await page.goto('https://kr.louisvuitton.com/kor-kr/homepage', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});

console.log('\n════════════════════════════════════════════════════');
console.log('  请在弹出的浏览器窗口里操作：');
console.log('  1) 打开 kr.louisvuitton.com（若显示 Access Denied，按 ⌘R 刷新一两次）');
console.log('  2) 随便点进一个 包/钱包/鞋 的商品详情页');
console.log('  脚本检测到有效会话后会【自动开始抓价】，无需其它操作。');
console.log('════════════════════════════════════════════════════\n');

// 轮询等待有效会话
const t0 = Date.now();
while (!creds && Date.now() - t0 < WAIT_MS) {
  await page.waitForTimeout(2000);
  const secs = Math.round((Date.now() - t0) / 1000);
  if (secs % 10 === 0) console.log(`  …等待你在窗口里点进一个商品页 (${secs}s / 已过 ${Math.round(WAIT_MS/1000)}s)`);
}
if (!creds) { console.log('✗ 超时没拿到有效会话（可能一直没点进商品页/一直被拒）。退出。'); await ctx.close(); process.exit(3); }
console.log('\n✓ 拿到有效会话（client 凭证 + Akamai cookie），开始抓价…\n');

// 用户当前所在的 LV 页面来跑页内 fetch（cookie 有效、同源）
const lvPage = ctx.pages().find(p => /louisvuitton\.com/.test(p.url())) || page;

const B = 'https://api.louisvuitton.com/eco-as/lvcom-prodct-dtl-eapi/v2/products/kor-kr/skus';
const fetchOne = (art) => lvPage.evaluate(async ({ u, cid, csec, corr }) => {
  try {
    const r = await fetch(u, { headers: { accept: 'application/json', client_id: cid, client_secret: csec, 'x-correlation-id': corr }, credentials: 'include' });
    const t = await r.text(); let d = {}; try { d = JSON.parse(t); } catch {}
    const skus = (d.skus || []).map(x => ({ size: x.size || x.sizeName || x.name || '', sellable: !!x.sellable, storeSell: !!x.csc_Sellable, skuId: x.skuId }));
    return { status: r.status, priceRaw: d.priceRaw ?? null, sellable: d.sellable ?? null, backOrder: d.backOrder ?? null, name: d.name || '', productId: d.productId || '', color: d.color || '', newArrivalsDate: d.newArrivalsDate ?? null, locateInStore: !!d.locateInStore, skus, nSell: skus.filter(x => x.sellable).length, nStore: skus.filter(x => x.storeSell).length, nTotal: skus.length };
  } catch (e) { return { status: -1, err: String(e) }; }
}, { u: `${B}/${art}`, cid: creds.client_id, csec: creds.client_secret, corr: `${Date.now()}-${Math.floor(Math.random() * 99999)}` });

console.log('货号            状态  LV价(KRW)   可售  名称');
const results = {};
for (const art of ARTS) {
  await lvPage.waitForTimeout(1100);
  const r = await fetchOne(art);
  results[art] = r;
  const price = r.priceRaw != null ? String(r.priceRaw).padStart(9) : '    —    ';
  const st = r.status === 200 ? '200' : (r.status === 410 ? '410停售' : String(r.status));
  console.log(`${art.padEnd(14)} ${st.padEnd(6)}${price}   ${r.sellable === true ? '可' : r.sellable === false ? '否' : '?'}   ${(r.name || '').slice(0, 24)}`);
}

// 回写 skus.csv（仅 200 有价）
let updated = 0;
for (let i = 1; i < rows.length; i++) {
  const art = rows[i][iArt]; const r = results[art];
  if (r && r.status === 200 && r.priceRaw != null && iPrice >= 0) {
    if (rows[i][iPrice] !== String(r.priceRaw)) updated++;
    rows[i][iPrice] = String(r.priceRaw);
  }
}
if (iPrice >= 0) fs.writeFileSync(CSV, rows.map(r => r.join(',')).join('\n') + '\n');

// 增量合并 data/lv_prices.json（不覆盖之前的）
fs.mkdirSync('data', { recursive: true });
let merged = {};
try { merged = JSON.parse(fs.readFileSync('data/lv_prices.json', 'utf8')).results || {}; } catch {}
Object.assign(merged, results);
fs.writeFileSync('data/lv_prices.json', JSON.stringify({ fetchedAt: new Date().toISOString(), results: merged }, null, 1));

const n200 = Object.values(results).filter(r => r.status === 200).length;
const n410 = Object.values(results).filter(r => r.status === 410).length;
const nerr = ARTS.length - n200 - n410;
console.log(`\n✓ 完成：200(有价) ${n200} / 410(停售) ${n410} / 失败 ${nerr}  | skus.csv 更新 ${updated} 行 | 合并后共 ${Object.keys(merged).length} 货号`);
await ctx.close();
process.exit(0);
