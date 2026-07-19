#!/usr/bin/env python3
"""半自动 LV 抓价 —— 第 1 步：生成 Safari 控制台代码。

背景：patchright 自动暖机自 2026-07 起被 Akamai 首页级封死（换 profile/IP 都不行）。
可靠替代 = 让用户在 Safari 里手动过 Akamai，再在控制台 fetch 逐货号取价。
本脚本生成那段控制台代码（含固定 client 凭证），用户贴进 Safari 控制台跑，
结果自动复制到剪贴板，再用 tools/lv_merge_paste.py 合并回 data/lv_prices.json。

用法:
  python tools/lv_snippet_gen.py 货号1 货号2 ...      # 指定货号
  python tools/lv_snippet_gen.py --missing [最小销量]   # 自动=缺价且中国销量≥N(默认5)的货号
输出: data/lv_snippet.js（gitignored），并打印使用说明。
"""
import sys, os, re, json
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
load_dotenv(os.path.join(ROOT, ".env"))


def load_creds():
    """client_id/secret 是 LV 网页公钥(固定可复用)，存 .env(gitignored)。"""
    cid, csec = os.getenv("LV_CLIENT_ID"), os.getenv("LV_CLIENT_SECRET")
    if not (cid and csec):
        sys.exit("✗ 找不到 LV client 凭证。请在 .env 里设 LV_CLIENT_ID / LV_CLIENT_SECRET"
                 "（LV 网页公钥、固定可复用，从真实 PDP 请求头里抓）。")
    return cid, csec


def missing_arts(min_sold: int):
    """缺 LV 价、可出价、且中国30天销量≥min_sold 的货号，按销量降序。"""
    prices = json.load(open("data/lv_prices.json"))["results"] if os.path.exists("data/lv_prices.json") else {}
    have = set(prices)
    best = {}
    for r in json.load(open("data/dewu_market.json"))["rows"]:
        if r.get("bidable") == 1 and r.get("cn_sold", 0) > 0:
            m = re.match(r"^([A-Z0-9]{5,8})", str(r["article_no"]))
            if m and m.group(1) not in have:
                a = m.group(1); best[a] = max(best.get(a, 0), int(r.get("cn_sold", 0)))
    return [a for a, s in sorted(best.items(), key=lambda x: -x[1]) if s >= min_sold]


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "--missing":
        thr = int(argv[1]) if len(argv) > 1 else 5
        arts = missing_arts(thr)
        print(f"自动清单: 缺价且中国销量≥{thr} 的 {len(arts)} 个货号")
    else:
        arts = argv
    if not arts:
        sys.exit("用法: python tools/lv_snippet_gen.py 货号... | --missing [最小销量]")

    cid, csec = load_creds()
    arr = ",".join(f'"{a}"' for a in arts)
    snippet = (
        '(async () => {\n'
        f'  const ARTS = [{arr}];\n'
        f'  const CID="{cid}", CSEC="{csec}";\n'
        '  const B="https://api.louisvuitton.com/eco-as/lvcom-prodct-dtl-eapi/v2/products/kor-kr/skus";\n'
        '  const out={}; let i=0;\n'
        '  for (const art of ARTS){\n'
        '    try{\n'
        '      const r=await fetch(B+"/"+art,{headers:{accept:"application/json",client_id:CID,client_secret:CSEC,"x-correlation-id":Date.now()+"-"+Math.floor(Math.random()*99999)},credentials:"include"});\n'
        '      let d={}; try{d=await r.json();}catch{}\n'
        '      const sk=(d.skus||[]);\n'
        '      out[art]={status:r.status,priceRaw:d.priceRaw??null,sellable:d.sellable??null,backOrder:d.backOrder??null,name:d.name||"",color:d.color||"",productId:d.productId||"",newArrivalsDate:d.newArrivalsDate??null,locateInStore:!!d.locateInStore,nSell:sk.filter(x=>x.sellable).length,nStore:sk.filter(x=>x.csc_Sellable).length,nTotal:sk.length};\n'
        '    }catch(e){out[art]={status:-1,err:String(e)};}\n'
        '    if(++i%40===0) console.log(i+"/"+ARTS.length+" …");\n'
        '    await new Promise(r=>setTimeout(r, 380+Math.random()*160));\n'
        '  }\n'
        '  const n2=Object.values(out).filter(v=>v.status===200).length, n4=Object.values(out).filter(v=>v.status===410).length;\n'
        '  try{copy(JSON.stringify(out));console.log("✅ 完成 "+ARTS.length+" 个：200="+n2+" 410="+n4+"，已复制到剪贴板。");}\n'
        '  catch{console.log("✅ 完成。手动复制下面这行：\\n"+JSON.stringify(out));}\n'
        '})();'
    )
    out_path = "data/lv_snippet.js"
    os.makedirs("data", exist_ok=True)
    open(out_path, "w").write(snippet)
    print(f"\n✓ 已生成 {len(arts)} 货号的抓价代码 → {out_path}")
    print("——— 下一步 ———")
    print("1. Safari 打开 kr.louisvuitton.com（真人过 Akamai；若 Access Denied 按 ⌘R 刷新）")
    print("2. ⌥⌘C 开控制台，把 data/lv_snippet.js 整段贴进去回车（约 %ds）" % round(len(arts) * 0.46))
    print("3. 看到 ✅ 完成 后复制输出，跑: python tools/lv_merge_paste.py <粘贴内容存的文件>")


if __name__ == "__main__":
    main()
