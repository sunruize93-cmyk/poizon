#!/usr/bin/env python3
"""热门款清单 —— 中国30天销量最高(真实数字非屏蔽)的 LV 款,给用户逐款去官网确认可买。

现实:热门款(高需求)恰恰是竞争压价款,LV零售下普遍负毛利;赚钱靠买入折扣或价格冲高。
本工具对每款算「零售毛利 + 额外折扣 10%/15%/20% 时毛利」,标出需要多大折扣才赚钱,
用户据此优先去官网确认可买的款。
用法: python tools/hot_items.py [--min-sales 30] [--top 20]
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import yaml
from src.fx import krw_per_cny
from src.models import LVProduct, DewuProduct, Candidate
from src.scorer.score import compute_profit

cfg0 = yaml.safe_load(open("config/settings.example.yaml", encoding="utf-8"))
if os.path.exists("config/settings.yaml"):
    cfg0 = yaml.safe_load(open("config/settings.yaml", encoding="utf-8"))
fx = krw_per_cny(cfg0)
DISCOUNTS = [0, 0.10, 0.15, 0.20]


def margin_with_extra(art, sell_krw, extra, lv_krw):
    if lv_krw <= 0 or sell_krw <= 0:
        return None
    cfg = json.loads(json.dumps(cfg0))
    cfg["cost"]["voucher_rate"] = cfg["cost"].get("voucher_rate", 0.03) + extra
    c = Candidate(article_no=art, lv=LVProduct(article_no=art, category="", price_krw=lv_krw, sellable=True),
                  dewu=DewuProduct(article_no=art, market_price_cny=round(sell_krw / fx, 2)))
    compute_profit(c, cfg, fx)
    return round(c.net_profit_cny), round(c.margin_rate, 4)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-sales", type=float, default=30)
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()
    mkt = [r for r in json.load(open("data/dewu_market.json"))["rows"]]
    p = json.load(open("data/lv_prices.json")).get("results", {})
    hot = [r for r in mkt if r.get("cn_sold", 0) >= args.min_sales and r.get("bidable") == 1
           and r.get("cn_masked", 0) == 0]
    hot.sort(key=lambda r: -r["cn_sold"])

    rows = []
    for r in hot[: args.top]:
        art = r["article_no"][:8]
        lv_krw = float(p.get(art, {}).get("priceRaw") or 0)
        sell = r.get("cn_price") or 0
        row = {"article_no": art, "name": str(r.get("title", ""))[:26],
               "cn_sold": r["cn_sold"], "kr_sold": r.get("kr_sold", 0),
               "cn_price_krw": int(sell), "lv_krw": int(lv_krw) if lv_krw else 0}
        for d in DISCOUNTS:
            m = margin_with_extra(art, sell, d, lv_krw)
            row[f"net_d{d:.0%}"] = (m[0] if m else None)
            row[f"margin_d{d:.0%}"] = (m[1] if m else None)
        # 需要多大额外折扣才到正毛利
        need = next((d for d in DISCOUNTS if (row.get(f"net_d{d:.0%}") or -9e9) > 0), None)
        row["discount_needed"] = need
        rows.append(row)
    rows.sort(key=lambda r: (r.get("lv_krw") <= 0, -(r.get("net_d20%") or -9e9)))

    print(f"═══ 热门款 Top{args.top}（中国30天销量≥{args.min_sales}, 真实数字）═══")
    print(" # 货号    名称                    销量  零售净利  9折   85折   8折    需折扣")
    for i, r in enumerate(rows, 1):
        def f(k):
            v = r.get(f"net_d{k}")
            return f"{v:+,.0f}" if v is not None else "缺LV价"
        need = f"{r['discount_needed']:.0%}" if r.get("discount_needed") is not None else "≥20%/缺价"
        print(f"{i:>2} {r['article_no']:8} {r['name'][:20]:20} {r['cn_sold']:>5.0f} "
              f"{f('0%'):>7} {f('10%'):>6} {f('15%'):>6} {f('20%'):>6}  {need}")
    json.dump(rows, open("data/hot_items.json", "w"), ensure_ascii=False, indent=1)
    print(f"\n✓ → data/hot_items.json ({len(rows)} 款)")


if __name__ == "__main__":
    main()
