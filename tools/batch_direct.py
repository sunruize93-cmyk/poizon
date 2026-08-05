#!/usr/bin/env python3
"""批量直发筛选 —— 把「能赚钱」的候选池放大到几百个,人只做最后一步「哪些有货」。

背景(用户 2026-08 口径):系统看不到线下有货,但人可以确认同一店有货。核心诉求=省人工:
机器把「能不能赚钱」筛完(全量 LV 候选 → 直发毛利>0),人只对筛出来的池去店里确认有货。
这一步可以 50/100/300 个,不是 Top10。

流水:
  1) 候选池 = 得物可出价 + 中国销量>0 + 有LV价(约342个)
  2) 直发价(bt=27)逐货号抓(缓存 data/direct_prices.json,TTL 24h,增量)
  3) 直发净利>0 = 赚钱候选 → 按直发月利润潜力=直发净利(₩→¥)×中国30天销量 降序
输出: data/batch_direct.json + 控制台(全量,可分页)。用法: python tools/batch_direct.py [--min-sold 0] [--limit 400]
"""
import json, sys, os, re, time, argparse, warnings
warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from datetime import datetime
from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))
import yaml
from src.fx import krw_per_cny
from src.dewu_source.official_api import DewuOfficialClient, _market_price
from src.scorer.score import direct_net

cfg = yaml.safe_load(open("config/settings.example.yaml", encoding="utf-8"))
if os.path.exists("config/settings.yaml"):
    cfg = yaml.safe_load(open("config/settings.yaml", encoding="utf-8"))
fx = krw_per_cny(cfg)
NOW = datetime.now()
TTL_H = float(os.getenv("DIRECT_TTL_H", "24"))

ap = argparse.ArgumentParser()
ap.add_argument("--min-sold", type=float, default=0, help="中国30天销量下限")
ap.add_argument("--limit", type=int, default=400, help="最多抓多少货号")
ap.add_argument("--skip-cache-ok", action="store_true", help="只用缓存,不新抓(纯离线排序)")
args = ap.parse_args()


def clean(a):
    m = re.match(r"^([A-Z0-9]{5,8})", str(a))
    return m.group(1) if m else None


def main():
    mkt = [r for r in json.load(open("data/dewu_market.json"))["rows"]]
    prices = json.load(open("data/lv_prices.json")).get("results", {})
    cache = json.load(open("data/direct_prices.json")) if os.path.exists("data/direct_prices.json") else {}

    # 候选池: 可出价 + 有销量 + 有LV价
    pool = {}
    for r in mkt:
        a = clean(r["article_no"])
        if not a or a not in prices or prices[a].get("status") != 200:
            continue
        if r.get("bidable") != 1 or (r.get("cn_sold") or 0) <= args.min_sold:
            continue
        if a not in pool or r["cn_sold"] > pool[a]["cn_sold"]:
            pool[a] = {"cn_sold": r["cn_sold"], "cn_masked": r.get("cn_masked", 0),
                       "kr_sold": r.get("kr_sold", 0), "cn_price": r.get("cn_price", 0),
                       "title": r.get("title", ""), "cat3": r.get("cat3", "")}
    pool = dict(list(pool.items())[: args.limit])
    print(f"候选池 {len(pool)} 个(可出价+销量>{args.min_sold}+有LV价)")

    def age_h(entry):
        ts = entry.get("ts") if isinstance(entry, dict) else None
        if not ts:
            return None
        try:
            return round((NOW - datetime.fromisoformat(ts)).total_seconds() / 3600, 1)
        except Exception:
            return None

    c = DewuOfficialClient()
    results = {}
    to_fetch = []
    for a in pool:
        ent = cache.get(a)
        if args.skip_cache_ok:
            # 离线模式:只用缓存,缺价跳过,不抓API
            if ent is not None:
                results[a] = {"skus": ent.get("skus", []), "age_h": age_h(ent)}
            continue
        if ent is not None:
            ag = age_h(ent)
            if ag is not None and ag <= TTL_H:
                results[a] = {"skus": ent.get("skus", []), "age_h": ag}
                continue
        to_fetch.append(a)

    if args.skip_cache_ok:
        print(f"离线模式:只用缓存,缺价跳过(有缓存 {len(results)} 个)")
    elif to_fetch:
        print(f"需新抓 {len(to_fetch)} 个直发价(~{len(to_fetch)*8//60}分钟)…")
    for a in to_fetch:
        out = []
        try:
            info = c.query_by_article_number(a, region="KR")
            skus = [s for s in ((info.get("data") or [{}])[0].get("skuInfoList") or []) if s.get("buyStatus") == 1]
            for s in skus[:12]:
                sid = s.get("skuId") or s.get("dwSkuId")
                pp = _market_price(c.get_lowest_price(sid, region="KR", currency="KRW", bidding_type=27).get("data") or {}, "KRW")
                if pp:
                    out.append({"edition": "", "size": "", "direct_krw": int(pp)})
                time.sleep(0.15)
        except Exception:
            pass
        cache[a] = {"ts": NOW.isoformat(timespec="seconds"), "skus": out}
        results[a] = {"skus": out, "age_h": 0.0}
        if len(to_fetch) >= 20 and (to_fetch.index(a) + 1) % 20 == 0:
            json.dump(cache, open("data/direct_prices.json", "w"), ensure_ascii=False)
            print(f"  进度 {to_fetch.index(a)+1}/{len(to_fetch)}…")
    json.dump(cache, open("data/direct_prices.json", "w"), ensure_ascii=False)

    rows = []
    for a, d in pool.items():
        skus = results.get(a, {}).get("skus", [])
        lv_krw = float(prices[a].get("priceRaw") or 0)
        if lv_krw <= 0 or not skus:
            continue
        best = None
        for sk in skus:
            dd = direct_net(lv_krw, sk["direct_krw"], cfg)
            if best is None or dd["margin"] > best["margin"]:
                best = dd
        if best is None:
            continue
        cn = d["cn_sold"]
        net_y = round(best["net"] / fx)
        rows.append({"article_no": a, "name": str(d["title"])[:22], "cn_sold": cn,
                     "cn_masked": d["cn_masked"], "kr_sold": d["kr_sold"],
                     "direct_krw": best["sell"], "net_krw": best["net"], "net_cny": net_y,
                     "margin": best["margin"], "cny_display": best["cny_display"],
                     "declare": best["declare_needed"], "month_y": round(net_y * cn)})
    prof = [r for r in rows if r["net_krw"] > 0]
    prof.sort(key=lambda r: -r["month_y"])

    print(f"\n═══ 批量直发筛选: 候选{len(rows)} 个算出毛利, 能赚钱(直发净利>0) {len(prof)} 个 ═══")
    print(" # 货号    名称                中国30天销 直发价₩   直发净利₩  净利¥ 利润率 月利润¥")
    for i, r in enumerate(prof, 1):
        est = "*" if r["cn_masked"] else " "
        flag = "⚠" if r["declare"] else " "
        print(f"{i:>3} {r['article_no']:8} {r['name'][:16]:16} {r['cn_sold']:>6.0f}{est} {r['direct_krw']:>8,} "
              f"{r['net_krw']:>8,} {r['net_cny']:>6,} {r['margin']:>5.0%} {r['month_y']:>8,}{flag}")
        if i >= 60 and (i % 60 == 0):
            print("  …继续(全量见 data/batch_direct.json)")
    json.dump({"count": len(prof), "as_of": "2026-08-05", "rows": prof},
              open("data/batch_direct.json", "w"), ensure_ascii=False, indent=1)
    print(f"\n✓ 赚钱候选池 {len(prof)} 个 → data/batch_direct.json")


if __name__ == "__main__":
    main()
