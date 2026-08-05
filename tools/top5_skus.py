#!/usr/bin/env python3
"""Top5 精确到「类型(版本/颜色)×尺码」—— 选品清单的 SKU 级输出。

背景:货号中位价会抹平真实机会。同一货号,不同 (版本[有盒/无盒/钢印] × 尺码) 得物价差巨大,
净利可从 +¥4000 到 -¥1300。选品必须看到 SKU 级。

数据源:
  得物: 商品搜索导出*.xlsx 的逐 SKU 行(尺码/规格/颜色 → 颜色/版本/尺码; 过去30天成交均价/当前中国最低出价)
  LV:   data/lv_prices.json 的 skus[] (size/priceRaw/sellable/storeSell, 由 Safari 半自动抓取)
逻辑: 得物 SKU 卖价 × 成本模型(compute_profit) → 逐 SKU 净利; 拼 LV 侧尺码可购性。
输出: data/top5_skus.json + 控制台清单。用法: python tools/top5_skus.py
"""
import pandas as pd, warnings, re, sys, os, json
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import yaml
from src.fx import krw_per_cny
from src.models import LVProduct, DewuProduct, Candidate
from src.scorer.score import compute_profit

cfg = yaml.safe_load(open("config/settings.example.yaml", encoding="utf-8"))
if os.path.exists("config/settings.yaml"):
    cfg = yaml.safe_load(open("config/settings.yaml", encoding="utf-8"))
fx = krw_per_cny(cfg)


def num(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).replace(",", "").replace("KRW", "").replace("₩", "").replace("+", "").strip()
    if s in ("--", "", "-"):
        return None
    m = re.search(r"[\d.]+", s)
    return float(m.group()) if m else None


def field(txt, key):
    m = re.search(rf"{key}[:：]([^;；]+)", str(txt))
    return m.group(1).strip() if m else ""


def main():
    raw = pd.read_excel("data/商品搜索导出20260805.xlsx")
    raw.columns = [c.strip() for c in raw.columns]
    p = json.load(open("data/lv_prices.json")).get("results", {})
    t5 = [r["article_no"] for r in json.load(open("data/top5_list.json"))["rows"]]

    out = {}
    for a in t5:
        lv = p.get(a, {})
        lv_krw = float(lv.get("priceRaw") or 0)
        skus = lv.get("skus") or []
        lv_sizes = sorted({s.get("size") for s in skus if s.get("sellable")})
        lv_colors = sorted({s.get("color") for s in skus})
        n_store = len([s for s in skus if s.get("storeSell")])
        sub = raw[raw["商品货号"].astype(str) == a]
        cat = str(sub.iloc[0]["商品三级类目"]) if len(sub) else ""
        rows = []
        for _, r in sub.iterrows():
            ask, avg = num(r["当前中国最低出价"]), num(r["过去30天成交均价"])
            sell_krw = avg or ask
            if not sell_krw:
                continue
            c = Candidate(article_no=a, lv=LVProduct(article_no=a, category=cat, price_krw=lv_krw, sellable=True),
                          dewu=DewuProduct(article_no=a, market_price_cny=round(sell_krw / fx, 2)))
            compute_profit(c, cfg, fx)
            spec = str(r["尺码/规格/颜色"])
            rows.append({"颜色": field(spec, "颜色"), "版本": field(spec, "版本"), "尺码": field(spec, "尺码"),
                         "出价₩": int(ask or 0), "均价₩": int(avg or 0), "净利¥": round(c.net_profit_cny),
                         "利润率": round(c.margin_rate, 4), "真实成交": bool(avg)})
        rows.sort(key=lambda x: -x["净利¥"])
        out[a] = {"name": str(sub.iloc[0]["商品名称"])[:30], "lv_krw": lv_krw, "lv_sizes": lv_sizes,
                  "lv_colors": lv_colors, "n_store_sizes": n_store, "top_skus": rows}
        print(f"\n══ {a} {out[a]['name']} | LV {lv_krw:,.0f}₩ ══")
        print(f"   LV可买: {len(lv_sizes)}码 ({lv_sizes[0]}-{lv_sizes[-1]}) {lv_colors} | store可订{n_store}码 | LV价各码一致")
        for r in rows[:5]:
            tag = "实" if r["真实成交"] else "价"
            print(f"   {r['颜色'][:6]:6} {r['版本'][:12]:12} {r['尺码']:12} 净利¥{r['净利¥']:+6.0f} {r['利润率']:>5.0%} [{tag}]")
        neg = [r for r in rows if r["净利¥"] < 0]
        if neg:
            print(f"   ⚠️ 亏钱SKU: " + "; ".join(f"{r['版本'][:8]}{r['尺码']}({r['净利¥']:+})" for r in neg[:4]))
    json.dump(out, open("data/top5_skus.json", "w"), ensure_ascii=False, indent=1)
    print(f"\n✓ → data/top5_skus.json")


if __name__ == "__main__":
    main()
