import { chromium } from 'patchright';
import fs from 'fs';
const ART = process.argv[2] || 'M80726';
// patchright 推荐：persistent context + 默认UA + 不加自动化args
const ctx = await chromium.launchPersistentContext('tools/.lv_profile', {
  headless: false, viewport: null, locale: 'ko-KR', timezoneId: 'Asia/Seoul',
});
const page = ctx.pages()[0] || await ctx.newPage();
const hits = [];
page.on('response', async (r) => { try { const u=r.url(); if(!/louisvuitton/i.test(u))return;
  const ct=r.headers()['content-type']||''; if(!ct.includes('json'))return; let b; try{b=await r.text();}catch{return;}
  if(/price|stock|sellable|availab|product|catalog|search|won|krw/i.test(b+u)) hits.push({status:r.status(),url:u.slice(0,120),snip:b.slice(0,200)});
}catch{} });
console.log('→ homepage');
await page.goto('https://kr.louisvuitton.com/kor-kr/homepage',{waitUntil:'domcontentloaded',timeout:60000}).catch(e=>console.log(' warn',e.message.split('\n')[0]));
await page.waitForTimeout(6000);
await page.screenshot({path:'tools/_lv2_home.png'});
const denied1 = (await page.content()).includes('Access denied')||(await page.content()).includes('Accès refusé');
console.log('homepage denied?', denied1, 'title:', await page.title());
if(!denied1){
  await page.goto(`https://kr.louisvuitton.com/kor-kr/search/${ART}`,{waitUntil:'networkidle',timeout:60000}).catch(e=>console.log(' warn',e.message.split('\n')[0]));
  await page.waitForTimeout(5000);
  await page.screenshot({path:'tools/_lv2_search.png'});
  const links = await page.evaluate(()=>[...document.querySelectorAll('a[href]')].map(a=>a.getAttribute('href')).filter(h=>h&&/\/products\/|nvprod/i.test(h)).slice(0,6));
  console.log('product links:', links);
}
await ctx.storageState({path:'tools/.lv_auth.json'}).catch(()=>{});
fs.writeFileSync('tools/_lv_hits.json',JSON.stringify(hits,null,1));
console.log('json XHR:',hits.length); for(const h of hits.slice(0,15)) console.log(h.status,h.url,'|',h.snip.replace(/\s+/g,' ').slice(0,100));
await ctx.close();
