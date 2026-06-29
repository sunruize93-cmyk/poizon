// 复用登录态，进文档侧边栏点开指定接口，截获 API 详情 JSON（参数+返回字段）。
import { chromium } from 'playwright';
import fs from 'fs';

const OUT = 'data/poizon_docs';
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ storageState: 'tools/.auth.json', locale: 'zh-CN' });
const page = await context.newPage();

const log = fs.createWriteStream(`${OUT}/apidetail_net.jsonl`);
page.on('response', async (resp) => {
  try {
    const ct = resp.headers()['content-type'] || '';
    if (!ct.includes('json')) return;
    const url = resp.url();
    if (!/\/pop\/h5\/api\/|apiDetail|apiInfo|detail/i.test(url)) return;
    let body; try { body = await resp.json(); } catch { return; }
    log.write(JSON.stringify({ url, body }) + '\n');
  } catch {}
});

await page.goto('https://open.poizon.com/doc/list/documentationDetail/33', { waitUntil: 'networkidle' });
await page.waitForTimeout(3000);

// 要点开的接口：先点所属大类展开，再点接口名
const targets = [
  ['Item', 'Query Sku&Spu Information by Brand Official Item Number'],
  ['Bonded', "Get Platform's Lowest Price for SKU"],
  ['Bonded', "Get Real-time Inventory of Seller's On-sale SKU"],
  ['Listing & Inventory', 'Listing Recommendations'],
];

async function clickText(t) {
  const loc = page.locator(`text="${t}"`).first();
  try {
    await loc.scrollIntoViewIfNeeded({ timeout: 3000 });
    await loc.click({ timeout: 4000 });
    await page.waitForTimeout(2500);
    return true;
  } catch (e) { console.log('  click miss:', t, e.message.split('\n')[0]); return false; }
}

for (const [group, api] of targets) {
  console.log('>>', group, '/', api);
  await clickText(group);
  const ok = await clickText(api);
  if (ok) {
    const safe = api.replace(/[^a-z0-9]/gi, '_').slice(0, 50);
    const txt = await page.evaluate(() => document.body.innerText).catch(() => '');
    fs.writeFileSync(`${OUT}/api__${safe}.txt`, `URL ${page.url()}\nTAB ${api}\n\n${txt}`);
    console.log('  saved', safe, 'url=', page.url(), 'len', txt.length);
  }
}

await browser.close();
console.log('DONE');
