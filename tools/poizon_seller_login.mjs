// 登录 seller.poizon.com 并持久化会话到 tools/.seller_profile（复用,免重登）。
// 凭证从 env 读(POIZON_LOGIN_USER/PASS)，不写入文件。可见窗口,验证码由用户在窗口内手动过。
// 登录成功后截图 + 捕获商品表 XHR。用法: POIZON_LOGIN_USER=.. POIZON_LOGIN_PASS=.. node tools/poizon_seller_login.mjs
import { chromium } from 'playwright';
import 'dotenv/config';
import fs from 'fs';

const USER = process.env.POIZON_LOGIN_USER, PASS = process.env.POIZON_LOGIN_PASS;
if (!USER || !PASS) { console.log('缺 POIZON_LOGIN_USER/PASS 环境变量'); process.exit(1); }

const ctx = await chromium.launchPersistentContext('tools/.seller_profile', {
  headless: false, locale: 'zh-CN', viewport: { width: 1440, height: 900 },
});
const page = ctx.pages()[0] || await ctx.newPage();

const hits = [];
page.on('response', async r => {
  try {
    const u = r.url(); if (!/poizon\.com|dewu/i.test(u)) return;
    if (!(r.headers()['content-type'] || '').includes('json')) return;
    let b = ''; try { b = await r.text(); } catch { return; }
    if (/soldNum|sold30|spuId|spuTitle|lowestPrice|dealPrice|销量|成交均价|articleNumber/i.test(b) && b.length > 400
        && !/configCenter|validate_rule/i.test(u)) {
      hits.push({ status: r.status(), url: u, len: b.length, body: b });
      console.log('  [商品表候选]', r.status(), u.replace(/https?:\/\/[^/]+/, '').slice(0, 85), 'len=' + b.length);
    }
  } catch {}
});

const loggedIn = async () => {
  // 登录页有「账号登录」;登录后消失
  const c = await page.content().catch(() => '');
  return !/账号登录|请输入密码/.test(c);
};

console.log('→ seller.poizon.com');
await page.goto('https://seller.poizon.com', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(e => console.log(' warn', e.message.split('\n')[0]));
await page.waitForTimeout(4000);

if (!(await loggedIn())) {
  console.log('→ 填账号密码');
  await page.getByPlaceholder(/手机号|邮箱/).first().fill(USER).catch(() => {});
  await page.getByPlaceholder(/密码/).first().fill(PASS).catch(() => {});
  await page.getByRole('button', { name: '登录' }).first().click({ timeout: 5000 }).catch(() => {});
  console.log('→ 已提交,等待登录成功(如有验证码请在弹出的浏览器窗口手动完成,最多等 150s)...');
  for (let i = 0; i < 30; i++) {
    await page.waitForTimeout(5000);
    if (await loggedIn()) { console.log(' ✓ 登录成功'); break; }
    if (i % 3 === 0) console.log(`   等待中...${(i + 1) * 5}s`);
  }
}
const ok = await loggedIn();
console.log(' 登录态:', ok, '| url:', page.url().slice(0, 70), '| title:', await page.title().catch(() => ''));
await page.waitForTimeout(3000);
await page.screenshot({ path: 'tools/_seller_dash.png', fullPage: false }).catch(() => {});
fs.writeFileSync('tools/_seller_bodies.json', JSON.stringify(hits, null, 1));
console.log('商品表候选:', hits.length, '| 会话已存 tools/.seller_profile');
await ctx.close();
