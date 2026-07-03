// 得物 seller 后台批量拉商品需求数据(中国30天销量/本地卖家销量/成交均价)。
// 复用 .seller_profile 登录态,捕获商品搜索请求模板 → 在页面内 fetch 分页拉全 → data/dewu_market.json。
import { chromium } from 'playwright';
import fs from 'fs';

const MAX_PAGES = parseInt(process.env.MAX_PAGES || '20');   // 每页 pageSize，抓多少页
const PAGE_SIZE = parseInt(process.env.PAGE_SIZE || '100');

const ctx = await chromium.launchPersistentContext('tools/.seller_profile', {
  headless: false, locale: 'zh-CN', viewport: { width: 1440, height: 900 },
});
const page = ctx.pages()[0] || await ctx.newPage();

// 捕获商品搜索请求模板（url+method+postData+headers，含 sign）
let tmpl = null;
page.on('request', req => {
  if (/aurora-spu\/merchant\/search/i.test(req.url()) && !tmpl) {
    tmpl = { url: req.url(), method: req.method(), headers: req.headers(), postData: req.postData() };
    console.log('  [捕获请求模板]', req.method(), req.url().replace(/https?:\/\/[^/]+/, '').split('?')[0]);
  }
});

console.log('→ 商品搜索页(触发首个请求拿模板)');
await page.goto('https://seller.poizon.com/main/goods/search', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
await page.waitForTimeout(9000);
if (!tmpl) { console.log(' ✗ 未捕获到搜索请求,可能未登录/页面结构变了'); await ctx.close(); process.exit(2); }

// 解析原始 payload，尝试改 page/pageSize 在页面内 fetch（复用会话；测 sign 是否放行）
let basePayload = {};
try { basePayload = JSON.parse(tmpl.postData || "{}"); } catch {}
console.log(' 原始 payload 键:', Object.keys(basePayload).join(','), '| 原分页:', basePayload.page, basePayload.pageSize);

const pull = (payload) => page.evaluate(async ({ url, headers, body }) => {
  try {
    const r = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body), credentials: 'include' });
    const t = await r.text(); return { status: r.status, body: t };
  } catch (e) { return { status: -1, body: String(e) }; }
}, { url: tmpl.url, headers: tmpl.headers, body: payload });

const all = [];
let total = null;
for (let p = 1; p <= MAX_PAGES; p++) {
  const payload = { ...basePayload, page: p, pageSize: PAGE_SIZE };
  const res = await pull(payload);
  let d; try { d = JSON.parse(res.body); } catch { console.log(` page${p}: 非JSON(${res.status})`); break; }
  if (d.code !== 200 && d.status !== 200) { console.log(` page${p}: code=${d.code} msg=${d.msg} → sign 可能拦截,停止`); break; }
  const lst = (d.data && d.data.merchantSpuDtoList) || [];
  total = (d.data && d.data.total) ?? total;
  all.push(...lst);
  console.log(` page${p}: +${lst.length}  累计 ${all.length}/${total}`);
  if (!lst.length || all.length >= (total || 0)) break;
  await page.waitForTimeout(600);
}

// 抽取关键字段
const rows = all.map(x => ({
  article_no: x.articleNumber, spu_id: x.dwSpuId, title: x.title,
  cat1: x.categoryInfo?.levelOneCategoryName, cat2: x.categoryInfo?.levelTwoCategoryName, cat3: x.categoryInfo?.levelThreeCategoryName,
  cn_sold_30d: x.saleInfo?.last30GlobalSaleNum, kr_sold_30d: x.saleInfo?.last30LocalSaleNum,
  cn_avg_price_krw: x.salePriceAndNumMap?.CN?.globalLowestAvgPrice?.money?.minUnitVal,
  cn_lowest_krw: x.salePriceAndNumMap?.CN?.dealLowestPrice?.money?.minUnitVal,
  min_price_krw: x.priceInfo?.globalMinPrice?.money?.minUnitVal,
}));
fs.writeFileSync('data/dewu_market.json', JSON.stringify({ total, count: rows.length, rows }, null, 1));
console.log(`\n✓ 拉取 ${rows.length} 商品 → data/dewu_market.json (total=${total})`);
await ctx.close();
