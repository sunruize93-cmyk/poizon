#!/usr/bin/env python3
"""供给缺口榜(替代"得物没有"线):得物有SPU(有真实中国需求、能挂链接) × 韩国本地卖家≈0(供给缺口)。
= 你可抢先占位、低竞争的品。用真实销量数据,不是盲盒。
数据源 data/dewu_market.json(得物seller后台聚合)。排除异皮(法律)+限定(P开头)。
用法: python tools/supply_gap.py [中国销量下限,默认30] [本地卖家上限,默认3]
产出 data/supply_gap.json。
"""
import sys, os, json, re

MIN_CN = int(sys.argv[1]) if len(sys.argv) > 1 else 30
MAX_KR = int(sys.argv[2]) if len(sys.argv) > 2 else 3
g = json.load(open("data/dewu_market.json"))["rows"]
lvp = json.load(open("data/lv_prices.json")).get("results", {}) if os.path.exists("data/lv_prices.json") else {}

EXOTIC = ["鳄鱼", "蜥蜴", "鸵鸟", "crocodil", "lezard", "lizard", "python", "alligator", "ostrich", "exotic"]
def clean(a):
    m = re.match(r"^([A-Z0-9]{5,8})", str(a)); return m.group(1) if m else str(a)

rows = []
for r in g:
    if r.get("bidable") != 1:
        continue
    cn, kr = r.get("cn_sold", 0), r.get("kr_sold", 0)
    if cn < MIN_CN or kr > MAX_KR:
        continue
    title = str(r.get("title", ""))
    art = clean(r["article_no"])
    if any(e in title.lower() for e in EXOTIC) or art.upper().startswith("P"):
        continue  # 异皮法律/限定款排除
    st = (lvp.get(art) or {}).get("status")
    lv_status = "可采" if st == 200 else ("停售" if st == 410 else "未抓")
    rows.append({
        "article_no": art, "title": title[:26], "cat": r.get("cat2") or r.get("cat3"),
        "cn_sold": int(cn), "kr_sold": int(kr), "gap": round(cn / (kr + 1)),
        "cn_price_krw": int(r.get("cn_price", 0)),
        "lv_status": lv_status, "lv_krw": int((lvp.get(art) or {}).get("priceRaw") or 0) if st == 200 else 0,
    })
# 排序:LV可采优先(采不到=停售没意义),再韩国卖家少、中国需求大
rank = {"可采": 0, "未抓": 1, "停售": 2}
rows.sort(key=lambda r: (rank[r["lv_status"]], -(r["cn_sold"] if r["kr_sold"] == 0 else 0), -r["cn_sold"]))
json.dump({"count": len(rows), "rows": rows}, open("data/supply_gap.json", "w"), ensure_ascii=False, indent=1)

n_ok = sum(1 for r in rows if r["lv_status"] == "可采")
n_stop = sum(1 for r in rows if r["lv_status"] == "停售")
print(f"供给缺口榜(得物需求≥{MIN_CN}×韩卖≤{MAX_KR};排除异皮/限定):{len(rows)}款 | LV可采{n_ok} 停售{n_stop} 未抓{len(rows)-n_ok-n_stop}")
print(" 中国销量 韩卖 得物价₩ LV状态 LV价₩ 货号     名称")
for r in [x for x in rows if x["lv_status"] == "可采"][:30]:
    print(f" {r['cn_sold']:>6} {r['kr_sold']:>3} {r['cn_price_krw']:>8} {r['lv_status']:>4} {r['lv_krw']:>8} {r['article_no']:8} {r['title'][:20]}")
print(f"\n★ 关键:热门缺口多为LV停售(采不到)。真正可做=【LV可采】那 {n_ok} 款。→ data/supply_gap.json")
