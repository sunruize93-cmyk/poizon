#!/usr/bin/env python3
"""爆款预测(未来1-3个月) —— 四类信号叠加: 上新窗口 / 销量动量 / 联名限定 / 供给缺口。

现实:LV零售价下多数款得物套利负毛利(得物成交价<LV韩国零售),盈利靠买入折扣或上新窗口
(代购未进场、得物价格未被压)。所以本工具对每款算清楚「现价毛利」,分档:
  A. 现在就有正毛利 × 需求在涨/新上 → 立刻值得做
  B. 负毛利但需求强/新品 → 等折扣窗口/盯着得物价格冲过LV零售价那一下
  C. 联名限定 → 稀缺性,上新即可能冲
输出: data/predict_hits.json + 控制台清单。用法: python tools/predict_hits.py
"""
import pandas as pd, warnings, re, sys, os, json, glob
warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import yaml
from src.fx import krw_per_cny
from src.models import LVProduct, DewuProduct, Candidate
from src.scorer.score import compute_profit

cfg = yaml.safe_load(open("config/settings.example.yaml", encoding="utf-8"))
if os.path.exists("config/settings.yaml"):
    cfg = yaml.safe_load(open("config/settings.yaml", encoding="utf-8"))
fx = krw_per_cny(cfg)

LINKED = ["M81266", "M12925", "M27509", "M82717", "M12874", "M29537", "M26587", "M2A078",
          "M46197", "M45321", "M41113", "M71040", "M27064", "1A9JG9", "M00587", "M00544"]
NEW_ARRIVALS = {   # 7/28→8/5 得物新上(上新窗口)
    "1AIZKK": "REMIX 牛皮革 厚底", "1AHTJD": "Trainer 圆头平底", "1A8KBQ": "Trainer 牛皮 清",
    "1AJRU7": "Sunset 小牛皮 烫", "M96507": "原创设计 Bandeau",
}
TM = ["M13391", "M94967", "M13399", "M28388"]   # x 村上隆
NIGO = ["1AIKR3"]


def load_sales(f):
    raw = pd.read_excel(f); raw.columns = [c.strip() for c in raw.columns]
    d = {}
    for _, r in raw.iterrows():
        a = str(r["商品货号"]); v = r.get("中国市场总销量")
        try: s = int(str(v).replace(",", ""))
        except Exception: s = 0
        d[a] = max(d.get(a, 0), s)
    return d


def margin_of(art, sell_krw, cat="板鞋"):
    lv = json.load(open("data/lv_prices.json")).get("results", {}).get(art, {})
    lv_krw = float(lv.get("priceRaw") or 0)
    if lv_krw <= 0 or sell_krw <= 0:
        return None
    c = Candidate(article_no=art, lv=LVProduct(article_no=art, category=cat, price_krw=lv_krw, sellable=True),
                  dewu=DewuProduct(article_no=art, market_price_cny=round(sell_krw / fx, 2)))
    compute_profit(c, cfg, fx)
    return round(c.net_profit_cny), round(c.margin_rate, 4)


def main():
    old, new = load_sales("data/商品搜索导出20260718.xlsx"), load_sales("data/商品搜索导出20260805.xlsx")
    mkt = {r["article_no"][:8]: r for r in json.load(open("data/dewu_market.json"))["rows"]}
    board = {r["article_no"]: r for r in json.load(open("data/lv_opportunity_board.json"))["all_computed"]}

    rows = []

    # A. 上新窗口(得物新上, 韩卖0, 价格没被代购压)
    for art, nm in NEW_ARRIVALS.items():
        d = mkt.get(art, {})
        m_ = margin_of(art, d.get("cn_price") or 0)
        net, mg = (m_ if m_ else (None, None))
        rows.append({"article_no": art, "name": nm, "signal": "上新窗口", "cn_sold": int(d.get("cn_sold") or 0),
                     "kr_sold": int(d.get("kr_sold") or 0), "net_cny": net, "margin": mg,
                     "why": "7/28-8/5 得物新上,韩国0卖家,launch窗口价未压,代购未进场"})

    # B. 销量动量(7/18→8/5 上涨)
    mom = []
    for a in set(old) & set(new):
        o, nn = old[a], new[a]
        if o > 0 and nn > o * 1.2 and nn - o >= 4:
            mom.append((a, o, nn))
    mom.sort(key=lambda x: -x[2])
    for art, o, nn in mom[:14]:
        if art in NEW_ARRIVALS:
            continue
        d = mkt.get(art, {})
        m_ = margin_of(art, d.get("cn_price") or 0, cat=str(d.get("cat3") or "板鞋"))
        net, mg = (m_ if m_ else (None, None))
        rows.append({"article_no": art, "name": str(d.get("title", ""))[:22], "signal": "销量动量",
                     "cn_sold": nn, "cn_sold_prev": o, "kr_sold": int(d.get("kr_sold") or 0),
                     "net_cny": net, "margin": mg,
                     "why": f"30天销量 {o}→{nn} (需求在涨) 且韩国0卖家; 毛利{'正' if (net or 0) > 0 else '负(等折扣/盯价格冲高)'}"})

    # C. 联名限定
    for art in TM + NIGO:
        d = mkt.get(art, {})
        b = board.get(art, {})
        m_ = margin_of(art, d.get("cn_price") or 0, cat=str(d.get("cat3") or "板鞋"))
        net, mg = (m_ if m_ else (None, None))
        rows.append({"article_no": art, "name": str(d.get("title", ""))[:22], "signal": "联名限定",
                     "cn_sold": int(d.get("cn_sold") or 0), "kr_sold": int(d.get("kr_sold") or 0),
                     "net_cny": net or round(b.get("net_cny") or 0), "margin": mg or b.get("margin"),
                     "why": "联名(村上隆TM/Nigo),稀缺性,上新/补货即可能冲价"})

    # 排序: 正毛利优先, 需求动量次之, 最后负毛利
    for r in rows:
        r["prio"] = (1 if (r.get("net_cny") or 0) > 0 else 0) * 2 + (1 if r.get("signal") == "上新窗口" else 0)
    rows.sort(key=lambda r: (-r["prio"], -(r.get("cn_sold") or 0)))

    print("═══ 爆款预测(未来1-3个月) ═══")
    print(" # 货号    信号     名称                  30天销 韩卖 现价净利¥ 利润率  依据")
    for i, r in enumerate(rows, 1):
        net = f"{r['net_cny']:+.0f}" if r.get("net_cny") is not None else "缺LV价"
        mg = f"{r['margin']:.0%}" if r.get("margin") is not None else "-"
        print(f"{i:>2} {r['article_no']:8} {r['signal']:6} {r['name'][:18]:18} {r['cn_sold']:>5} "
              f"{r.get('kr_sold',0):>3} {net:>8} {mg:>6}  {r['why'][:38]}")
    json.dump(rows, open("data/predict_hits.json", "w"), ensure_ascii=False, indent=1)
    print(f"\n✓ → data/predict_hits.json ({len(rows)} 款)")


if __name__ == "__main__":
    main()
