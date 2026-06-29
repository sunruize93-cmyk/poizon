// 复用登录态，抓取 open.poizon 文档站接口与页面文本，落到 data/poizon_docs/。
import { chromium } from 'playwright';
import fs from 'fs';

const OUT = 'data/poizon_docs';
fs.mkdirSync(`${OUT}/net`, { recursive: true });

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ storageState: 'tools/.auth.json', locale: 'zh-CN' });
const page = await context.newPage();

const log = fs.createWriteStream(`${OUT}/net.jsonl`);
let captured = 0;
page.on('response', async (resp) => {
  try {
    const ct = resp.headers()['content-type'] || '';
    if (!ct.includes('json')) return;
    const url = resp.url();
    let body;
    try { body = await resp.json(); } catch { return; }
    log.write(JSON.stringify({ url, status: resp.status(), body }) + '\n');
    captured++;
  } catch {}
});

async function visit(url, label) {
  await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 })
    .catch(e => console.log('warn', label, e.message));
  await page.waitForTimeout(3500);
  const txt = await page.evaluate(() => document.body.innerText).catch(() => '');
  fs.writeFileSync(`${OUT}/${label}.txt`, `URL ${url}\n\n${txt}`);
  console.log('visited', label, 'url=', page.url(), 'textlen', txt.length);
}

await visit('https://open.poizon.com/application/list', 'console_app_list');
await visit('https://open.poizon.com/doc/list/documentationDetail/33', 'api_list');
await visit('https://open.poizon.com/doc/list/documentationDetail/15', 'api_intro');
await visit('https://open.poizon.com/doc/list/documentationDetail/9', 'auth_sign');

await browser.close();
console.log('DONE captured', captured, 'json responses');
