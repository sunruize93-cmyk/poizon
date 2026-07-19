#!/usr/bin/env python3
"""重点款 SKU 级利润明细：对指定货号，逐 SKU(版本×尺码)同时取
现货(bt=20, 得物CNY) 与 直发(bt=27, POIZON KRW) 价，各算净利/利润率，
标出每款最赚的规格。产出 data/sku_picks.json（export_excel 会并入「重点款_尺码版本」sheet）。

用法: python tools/sku_detail.py [货号...]   不带参数=用内置精选赢家款
"""
import sys, os, json, time, warnings, re
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
import yaml
from src.fx import krw_per_cny
from src.models import LVProduct, DewuProduct, Candidate
from src.scorer.score import compute_profit, direct_net
from src.dewu_source.official_api import DewuOfficialClient, _market_price

# 内置精选：两条线各自的高毛利赢家（现货+直发）
DEFAULT_PICKS = ["M4760T", "1ACNYF", "1AK45P", "1AIJ44", "Z2063U",
                 "M28426", "M46222", "M25143", "1AKKHJ", "1A8WAV", "M13391"]
PICKS = sys.argv[1:] or DEFAULT_PICKS

cfg = yaml.safe_load(open("config/settings.example.yaml", encoding="utf-8"))
if os.path.exists("config/settings.yaml"):
    cfg = yaml.safe_load(open("config/settings.yaml", encoding="utf-8"))
fx = krw_per_cny(cfg)
lv_prices = json.load(open("data/lv_prices.json"))["results"] if os.path.exists("data/lv_prices.json") else {}
# 货号→品类(得物 cat3，用于物流估重)
cat_map = {}
for r in json.load(open("data/dewu_market.json"))["rows"]:
    m = re.match(r"^([A-Z0-9]{5,8})", str(r["article_no"]))
    if m:
        cat_map.setdefault(m.group(1), r.get("cat3") or r.get("cat2") or "")

c = DewuOfficialClient()


def sku_edition_size(s):
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


rows = []
for art in PICKS:
    pr = lv_prices.get(art) or lv_prices.get(art.upper()) or {}
    lv_krw = float(pr.get("priceRaw") or 0)
    cat = cat_map.get(art, "")
    if lv_krw <= 0:
        print(f"  {art}: 无 LV 价，跳过"); continue
    try:
        info = c.query_by_article_number(art, region="KR")
        skus = [s for s in ((info.get("data") or [{}])[0].get("skuInfoList") or []) if s.get("buyStatus") == 1]
    except Exception as e:
        print(f"  {art}: 查询失败 {e}"); continue
    for s in skus[:14]:
        sid = s.get("skuId") or s.get("dwSkuId")
        if not sid:
            continue
        ed, sz = sku_edition_size(s)
        # 现货 bt=20 (CNY)
        spot_cny = _market_price(c.get_lowest_price(sid, region="KR", currency="CNY", bidding_type=20).get("data") or {}, "CNY")
        time.sleep(0.15)
        # 直发 bt=27 (KRW)
        dir_krw = _market_price(c.get_lowest_price(sid, region="KR", currency="KRW", bidding_type=27).get("data") or {}, "KRW")
        time.sleep(0.15)
        spot_net = spot_mg = spot_scen = None
        if spot_cny > 0:
            cand = Candidate(article_no=art,
                             lv=LVProduct(article_no=art, category=cat, price_krw=lv_krw, sellable=True),
                             dewu=DewuProduct(article_no=art, market_price_cny=spot_cny, wish_count=0, seller_count=0))
            compute_profit(cand, cfg, fx)
            spot_net, spot_mg, spot_scen = cand.net_profit_cny, cand.margin_rate, cand.sell_scenario
        dnet = direct_net(lv_krw, dir_krw, cfg) if dir_krw > 0 else None
        rows.append({
            "article_no": art, "name": str(pr.get("name", ""))[:20], "edition": ed, "size": sz,
            "lv_krw": int(lv_krw),
            "spot_cny": spot_cny or None, "spot_net_cny": spot_net, "spot_margin": spot_mg, "spot_scenario": spot_scen,
            "direct_krw": int(dir_krw) if dir_krw else None,
            "direct_net_krw": dnet["net"] if dnet else None, "direct_margin": dnet["margin"] if dnet else None,
            "direct_cny_display": dnet["cny_display"] if dnet else None, "declare": dnet["declare_needed"] if dnet else None,
        })
    print(f"  {art}: {len([r for r in rows if r['article_no']==art])} SKU")

json.dump({"fx": fx, "rows": rows}, open("data/sku_picks.json", "w"), ensure_ascii=False, indent=1)

# 打印：每款按"该款最优线利润率"排，SKU 内按利润率降序
def best_mg(r):
    return max([m for m in (r.get("spot_margin"), r.get("direct_margin")) if m is not None] or [-9])

print(f"\n★ 重点款 SKU 级明细(现货bt20 / 直发bt27) 汇率1CNY={fx:.0f}KRW")
print(" 货号     版本/尺码           现货¥  现货净利 现货率  直发₩净利 直发率  最优")
for art in PICKS:
    rs = sorted([r for r in rows if r["article_no"] == art], key=best_mg, reverse=True)
    for r in rs:
        spot = f"{r['spot_cny']:>6.0f} {r['spot_net_cny']:>6.0f} {r['spot_margin']:>4.0%}" if r["spot_net_cny"] is not None else "   --     --   -- "
        drc = f"{r['direct_net_krw']:>8} {r['direct_margin']:>4.0%}" if r["direct_net_krw"] is not None else "     --   -- "
        sm, dm = r.get("spot_margin"), r.get("direct_margin")
        best = "直发" if (dm is not None and (sm is None or dm > sm)) else ("现货" if sm is not None else "-")
        tag = (r["edition"][:6] + " " + r["size"])[:18]
        print(f" {art:8} {tag:18} {spot}  {drc}  {best}")

print(f"\n✓ SKU 明细 {len(rows)} 行 → data/sku_picks.json")
