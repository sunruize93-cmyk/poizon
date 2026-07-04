#!/usr/bin/env python3
"""直发(Direct/POIZON)线机会榜:对需求 shortlist 拿 POIZON 直发价(bt=27,KRW)→算直发净利→按利润率降序。
只对标 POIZON 出价,不掺得物CNY。直发价缓存 data/direct_prices.json(增量,免重复调API)。
用法: python tools/direct_board.py [最多抓几个货号,默认30]
"""
import sys, os, json, warnings, time
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
import yaml
from src.dewu_source.official_api import DewuOfficialClient, _market_price
from src.scorer.score import direct_net

LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 30
cfg = yaml.safe_load(open("config/settings.example.yaml", encoding="utf-8"))
if os.path.exists("config/settings.yaml"):
    cfg = yaml.safe_load(open("config/settings.yaml", encoding="utf-8"))

lv_prices = json.load(open("data/lv_prices.json")).get("results", {}) if os.path.exists("data/lv_prices.json") else {}
short = json.load(open("data/lv_demand_shortlist.json"))["rows"] if os.path.exists("data/lv_demand_shortlist.json") else []
cache = json.load(open("data/direct_prices.json")) if os.path.exists("data/direct_prices.json") else {}
c = DewuOfficialClient()

import re
def clean(a):
    m = re.match(r"^([A-Z0-9]{5,8})", str(a)); return m.group(1) if m else None

# 候选=有需求(shortlist)且已抓LV价的货号
arts = []
for r in short:
    a = clean(r["article_no"])
    if a and a in lv_prices and lv_prices[a].get("status") == 200 and a not in arts:
        arts.append(a)
arts = arts[:LIMIT]
print(f"直发线:对 {len(arts)} 个货号拿 POIZON 直发价(bt=27)…\n")

def fetch_direct_krw(art):
    if art in cache:
        return cache[art]
    try:
        info = c.query_by_article_number(art, region="KR")
        skus = [s for s in ((info.get("data") or [{}])[0].get("skuInfoList") or []) if s.get("buyStatus") == 1]
        low = 0.0
        for s in skus[:8]:  # 限每货号最多8个SKU,控API量
            sid = s.get("skuId") or s.get("dwSkuId")
            p = _market_price(c.get_lowest_price(sid, region="KR", currency="KRW", bidding_type=27).get("data") or {}, "KRW")
            if p and (low == 0 or p < low): low = p
            time.sleep(0.2)
        cache[art] = low
        return low
    except Exception:
        cache[art] = 0
        return 0

rows = []
for a in arts:
    lv_krw = float(lv_prices[a].get("priceRaw") or 0)
    direct_krw = fetch_direct_krw(a)
    if lv_krw <= 0 or direct_krw <= 0:
        continue
    d = direct_net(lv_krw, direct_krw, cfg)
    name = lv_prices[a].get("name", "")
    rows.append({"article_no": a, "name": name, "lv_krw": int(lv_krw), "direct_krw": int(direct_krw),
                 "fee": d["fee"], "net_krw": d["net"], "margin": d["margin"]})

json.dump(cache, open("data/direct_prices.json", "w"), ensure_ascii=False)
rows.sort(key=lambda r: r["margin"], reverse=True)
json.dump({"count": len(rows), "rows": rows}, open("data/direct_board.json", "w"), ensure_ascii=False, indent=1)

print("★ 直发线机会榜(POIZON,按利润率降序):")
print(" 利润率 净利₩ 技术费₩ 直发价₩ LV买入₩ 货号     名称")
for r in rows[:25]:
    print(f" {r['margin']:>5.0%} {r['net_krw']:>8} {r['fee']:>6} {r['direct_krw']:>8} {r['lv_krw']:>8} {r['article_no']:8} {str(r['name'])[:18]}")
print(f"\n✓ {len(rows)} 款 → data/direct_board.json (直发价缓存 data/direct_prices.json)")
