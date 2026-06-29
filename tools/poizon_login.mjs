// 打开可见浏览器登录 open.poizon.com，自动预填账号密码，等用户过验证码后
// 通过 tools/.login_done 文件信号保存登录态到 tools/.auth.json。
// 用法：node tools/poizon_login.mjs   （建议后台运行，保持浏览器存活）
import { chromium } from 'playwright';
import 'dotenv/config';
import fs from 'fs';

const AUTH = 'tools/.auth.json';
const SENTINEL = 'tools/.login_done';
const SHOT = 'tools/_shot.png';

if (fs.existsSync(SENTINEL)) fs.unlinkSync(SENTINEL);

const browser = await chromium.launch({ headless: false, args: ['--start-maximized'] });
const context = await browser.newContext({ viewport: null, locale: 'zh-CN' });
const page = await context.newPage();

await page.goto('https://open.poizon.com', { waitUntil: 'domcontentloaded', timeout: 60000 })
  .catch(e => console.log('goto warn:', e.message));
await page.waitForTimeout(3500);

// 尽力预填账号密码（找不到字段不报错，交给用户手动）
const user = process.env.POIZON_LOGIN_USER, pass = process.env.POIZON_LOGIN_PASS;
async function prefill() {
  for (const f of page.frames()) {
    try {
      const u = await f.$('input[type=text]:visible, input[placeholder*="账号"], input[placeholder*="手机"], input[placeholder*="邮箱"]');
      if (u && user) await u.fill(user);
      const p = await f.$('input[type=password]:visible');
      if (p && pass) await p.fill(pass);
      if (u || p) return true;
    } catch {}
  }
  return false;
}
await prefill().catch(() => {});
await page.screenshot({ path: SHOT }).catch(() => {});
console.log('READY url=', page.url());

// 等待握手信号；其间每 3s 刷新一次截图供主控查看
const deadline = Date.now() + 15 * 60 * 1000;
while (!fs.existsSync(SENTINEL)) {
  if (Date.now() > deadline) { console.log('TIMEOUT'); await browser.close(); process.exit(2); }
  await page.waitForTimeout(3000);
  await page.screenshot({ path: SHOT }).catch(() => {});
}

await context.storageState({ path: AUTH });
await page.screenshot({ path: 'tools/_shot_after.png' }).catch(() => {});
console.log('SAVED', AUTH, 'final url=', page.url());
await browser.close();
process.exit(0);
