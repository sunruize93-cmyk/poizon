#!/usr/bin/env python3
"""直发(Direct/POIZON)线机会榜 + 逐版本尺码明细。
对需求 shortlist 拿 POIZON 直发价(bt=27,KRW,逐SKU)→算直发净利→按利润率降序。
只对标 POIZON,不掺得物CNY。逐SKU价缓存 data/direct_prices.json(增量)。
产出 data/direct_board.json:{rows:货号级最优, sku_detail:逐SKU(版本/尺码/直发价/净利)}。
用法: python tools/direct_board.py [最多抓几个货号,默认30]
"""
import sys, os, json, warnings, time, re
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
import yaml
from src.dewu_source.official_api import DewuOfficialClient, _market_price
from src.scorer.score import direct_net

import argparse
from datetime import datetime
ap = argparse.ArgumentParser()
ap.add_argument("limit", nargs="?", type=int, default=30, help="抓多少个货号(默认30)")
ap.add_argument("--refresh", action="store_true", help="忽略缓存,全部重取实时POIZON价")
ap.add_argument("--ttl-hours", type=float, default=24.0, help="缓存价超过此小时数则重取(默认24)")
args = ap.parse_args()
LIMIT, REFRESH, TTL_H = args.limit, args.refresh, args.ttl_hours
NOW = datetime.now()
cfg = yaml.safe_load(open("config/settings.example.yaml", encoding="utf-8"))
if os.path.exists("config/settings.yaml"):
    cfg = yaml.safe_load(open("config/settings.yaml", encoding="utf-8"))
lv_prices = json.load(open("data/lv_prices.json")).get("results", {}) if os.path.exists("data/lv_prices.json") else {}
short = json.load(open("data/lv_demand_shortlist.json"))["rows"] if os.path.exists("data/lv_demand_shortlist.json") else []
cache = json.load(open("data/direct_prices.json")) if os.path.exists("data/direct_prices.json") else {}
c = DewuOfficialClient()


def clean(a):
    m = re.match(r"^([A-Z0-9]{5,8})", str(a)); return m.group(1) if m else None


def sku_edition_size(s):
    """从 regionSalePvInfoList 取 版本(Edition) + 尺码(优先KR,附CHN)。"""
    edition, kr, chn = "", "", ""
    for pv in s.get("regionSalePvInfoList") or []:
        if pv.get("sizeInfos"):
            for si in pv["sizeInfos"]:
                if si.get("sizeKey") == "KR" and si.get("value"):
                    kr = si["value"]
                elif si.get("sizeKey") == "CHN" and si.get("value"):
                    chn = si["value"]
        elif pv.get("value"):
            edition = pv["value"]
    size = (f"KR{kr}" if kr else "") + (f"/CHN{chn}" if chn else ("" if kr else (f"CHN{chn}" if chn else "")))
    return edition, size


arts = []
for r in short:
    a = clean(r["article_no"])
    if a and a in lv_prices and lv_prices[a].get("status") == 200 and a not in arts:
        arts.append(a)
arts = arts[:LIMIT]
mode = "全部实时重取" if REFRESH else f"缓存TTL {TTL_H:.0f}h(过期自动重取)"
print(f"直发线:对 {len(arts)} 个货号拿逐SKU POIZON直发价(bt=27) | {mode}…\n")


def _age_h(entry):
    """缓存条目价龄(小时)。旧格式(裸list,无时间戳)返回 None=当作过期。"""
    ts = entry.get("ts") if isinstance(entry, dict) else None
    if not ts:
        return None
    try:
        return round((NOW - datetime.fromisoformat(ts)).total_seconds() / 3600, 1)
    except Exception:
        return None


def fetch_skus(art):
    """返回 (skus, age_h)。命中未过期缓存直接用;否则实时取并盖时间戳。"""
    ent = cache.get(art)
    age = _age_h(ent)
    if ent is not None and not REFRESH and age is not None and age <= TTL_H:
        return ent.get("skus", []), age
    out = []
    try:
        info = c.query_by_article_number(art, region="KR")
        skus = [s for s in ((info.get("data") or [{}])[0].get("skuInfoList") or []) if s.get("buyStatus") == 1]
        for s in skus[:12]:   # 每货号最多12个SKU,控API量
            sid = s.get("skuId") or s.get("dwSkuId")
            p = _market_price(c.get_lowest_price(sid, region="KR", currency="KRW", bidding_type=27).get("data") or {}, "KRW")
            if p:
                ed, sz = sku_edition_size(s)
                out.append({"edition": ed, "size": sz, "direct_krw": int(p)})
            time.sleep(0.15)
    except Exception:
        pass
    cache[art] = {"ts": NOW.isoformat(timespec="seconds"), "skus": out}
    return out, 0.0


rows, detail = [], []
n_fresh = 0
for a in arts:
    lv_krw = float(lv_prices[a].get("priceRaw") or 0)
    name = lv_prices[a].get("name", "")
    skus, age_h = fetch_skus(a)
    if age_h == 0.0:
        n_fresh += 1
    if lv_krw <= 0 or not skus:
        continue
    best = None
    for sk in skus:
        d = direct_net(lv_krw, sk["direct_krw"], cfg)
        drow = {"article_no": a, "name": str(name)[:22], "edition": sk["edition"], "size": sk["size"],
                "direct_krw": sk["direct_krw"], "fee": d["fee"], "net_krw": d["net"], "margin": d["margin"],
                "cny_display": d["cny_display"], "declare": d["declare_needed"], "price_age_h": age_h}
        detail.append(drow)
        if best is None or d["margin"] > best["margin"]:
            best = drow
    if best:
        rows.append(best)

print(f"  价龄:{n_fresh} 个实时新取 / {len(arts) - n_fresh} 个用缓存(≤{TTL_H:.0f}h)")
json.dump(cache, open("data/direct_prices.json", "w"), ensure_ascii=False)
rows.sort(key=lambda r: r["margin"], reverse=True)
detail.sort(key=lambda r: r["margin"], reverse=True)
json.dump({"count": len(rows), "rows": rows, "sku_detail": detail},
          open("data/direct_board.json", "w"), ensure_ascii=False, indent=1)

print("★ 直发线机会榜(POIZON,货号级最优,按利润率降序):")
print(" 利润率 净利₩ 直发价₩ 得物显示¥ 货号     版本/尺码            名称")
for r in rows[:25]:
    flag = "⚠申报" if r.get("declare") else ""
    print(f" {r['margin']:>5.0%} {r['net_krw']:>8} {r['direct_krw']:>8} {r.get('cny_display',0):>7.0f}{flag:>4} {r['article_no']:8} {(r['edition'][:8]+' '+r['size'])[:16]:16} {str(r['name'])[:14]}")
print(f"\n✓ 货号级 {len(rows)} + 逐SKU明细 {len(detail)} → data/direct_board.json")
