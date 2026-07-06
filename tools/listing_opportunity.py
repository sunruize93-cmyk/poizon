#!/usr/bin/env python3
"""上架机会线(供给优先):LV 有货 × 得物没有 × 有潜力 = 你抢先上架、无人竞争的品。
翻转漏斗:从 LV 目录(小皮具)出发 → 剔除得物已有 → 潜力判断 → 出候选(再确认得物/抓价/查库存)。
用法: python tools/listing_opportunity.py [品类,默认slg] [top,默认40]
产出 data/listing_candidates.json。
"""
import sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.engine.profiles import REGISTRY

CAT = sys.argv[1] if len(sys.argv) > 1 else "slg"
TOP = int(sys.argv[2]) if len(sys.argv) > 2 else 40
prof = REGISTRY["LV"]

cat_items = [i for i in json.load(open("data/lv_catalog.json"))["items"] if i["category"] == CAT]
dewu = set(re.match(r"^([A-Z0-9]{5,8})", str(r["article_no"])).group(1)
           for r in json.load(open("data/dewu_market.json"))["rows"]
           if re.match(r"^([A-Z0-9]{5,8})", str(r["article_no"])))
missing = [i for i in cat_items if i["article_no"] not in dewu]  # 得物货号集里没有

def score(slug):
    s = slug.lower(); pts, why = 0.5, []
    hot = [p for p in prof.hot_lines if re.search(p.lower(), s)]
    cold = [p for p in prof.cold_signals if re.search(p.lower(), s)]
    if hot: pts += 0.3; why.append("经典/热门:" + ",".join(hot[:3]))
    if cold: pts -= 0.4; why.append("冷门:" + ",".join(cold[:2]))
    # 小皮具高流动关键词额外加分
    for kw in ["card", "key", "zippy", "coin", "compact", "pocket", "cles", "victorine", "sarah", "brazza"]:
        if kw in s: pts += 0.1; break
    return max(0, min(1, pts)), "；".join(why) or "小皮具"

rows = []
for i in missing:
    p, why = score(i["slug"])
    rows.append({"article_no": i["article_no"], "slug": i["slug"], "nvprod": i.get("nvprod", ""),
                 "potential": round(p, 3), "reason": why})
rows.sort(key=lambda r: r["potential"], reverse=True)

# --verify:对高潜力候选逐个查得物by-article,只留【得物真没有】的(sitemap-diff会高估)
if "--verify" in sys.argv:
    import warnings; warnings.filterwarnings("ignore")
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    from src.dewu_source.official_api import DewuOfficialClient
    import time
    c = DewuOfficialClient()
    verified = []
    print(f"逐个查得物确认(top{TOP})…")
    for r in rows[:TOP]:
        try:
            info = c.query_by_article_number(r["article_no"], region="KR")
            items = info.get("data") or []
            on = bool(items and items[0].get("skuInfoList"))
        except Exception:
            on = None
        r["dewu_has"] = on
        if on is False:
            verified.append(r)
        time.sleep(0.15)
    json.dump({"count": len(verified), "rows": verified}, open("data/listing_candidates.json", "w"), ensure_ascii=False, indent=1)
    print(f"\n★ 真·上架机会(得物没有 × 有潜力){len(verified)}款(top{TOP}中):")
    print(" 潜力 货号     名称(slug)")
    for r in verified:
        print(f" {r['potential']:.2f} {r['article_no']:8} {r['slug'][:44]}")
    print(f"\n✓ {len(verified)} 真机会 → data/listing_candidates.json  下一步:LV抓价+逐尺码库存→算上架/直发利润")
else:
    json.dump({"count": len(rows), "rows": rows}, open("data/listing_candidates.json", "w"), ensure_ascii=False, indent=1)
    print(f"上架机会候选(LV {CAT} {len(cat_items)}款,得物货号集里没有 {len(missing)}款;需--verify逐个确认):")
    print(" 潜力 货号     名称(slug)")
    for r in rows[:TOP]:
        print(f" {r['potential']:.2f} {r['article_no']:8} {r['slug'][:44]}")
    print(f"\n加 --verify 逐个查得物,只留真没有的。")
