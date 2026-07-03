#!/usr/bin/env python3
"""从得物 seller 后台导出的商品表，发现「冷门但有潜力」的套利机会。

核心信号（AI 视角 > 人工）：
  中国市场销量 高  ×  本地(韩国)卖家销量 低  =  供给缺口 = 韩国卖家还没扎堆、你能吃的量
人工只盯显眼爆款；这里系统性扫全表，按「需求/本地供给」缺口排序，捞被忽略的潜力款。
产出 data/dewu_market.json（按货号聚合）+ 打印榜单。
用法: python tools/market_opportunities.py [export.xlsx]
"""
import sys
import re
import json
import pandas as pd

XLSX = sys.argv[1] if len(sys.argv) > 1 else "data/商品搜索导出20260703.xlsx"


def num(v) -> float:
    """'3,700+'→3700  '<5'→3  '--'/NaN→0  'KRW85,000'→85000"""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return 0.0
    s = str(v).replace(",", "").replace("KRW", "").replace("₩", "").replace("+", "").strip()
    if s in ("--", "", "-"):
        return 0.0
    m = re.search(r"<\s*(\d+)", s)
    if m:
        return float(m.group(1)) / 2  # "<5" 记 2.5
    m = re.search(r"[\d.]+", s)
    return float(m.group()) if m else 0.0


def main():
    df = pd.read_excel(XLSX)
    df.columns = [c.strip() for c in df.columns]
    # 聚合到货号（SPU）：China 销量/KR 销量按 SKU 求和，价格取均值
    df["_cn"] = df["中国市场总销量"].map(num)
    df["_kr"] = df["本地卖家总销量"].map(num)
    df["_avg"] = df["过去30天成交均价"].map(num)
    df["_low"] = df["当前中国最低出价"].map(num)
    g = df.groupby("商品货号").agg(
        title=("商品名称", "first"), brand=("商品品牌", "first"),
        cat1=("商品一级类目", "first"), cat2=("商品二级类目", "first"), cat3=("商品三级类目", "first"),
        cn_sold=("_cn", "sum"), kr_sold=("_kr", "sum"),
        avg_price=("_avg", "median"), low_price=("_low", "median"),
        spu_id=("spu_id", "first"),
    ).reset_index().rename(columns={"商品货号": "article_no"})

    # 缺口分：中国有量 + 本地卖家少。gap = 中国销量 / (本地销量+1)，再要求中国销量达门槛
    g["gap_ratio"] = g["cn_sold"] / (g["kr_sold"] + 1)
    # 「冷门潜力」= 中国销量中上 且 本地卖家极少（被忽视）
    print(f"总货号: {len(g)} | 有中国销量: {(g.cn_sold>0).sum()} | 本地卖家=0: {(g.kr_sold==0).sum()}")

    # 榜1：全站被忽视的高需求款（中国销量≥500 且 本地卖家≤5）
    under = g[(g.cn_sold >= 500) & (g.kr_sold <= 5)].sort_values("cn_sold", ascending=False)
    print(f"\n★ 冷门潜力（中国销量≥500 且 本地卖家≤5，即韩国几乎没人卖）: {len(under)} 款")
    print("  中国销量  本地  成交均价₩   品牌            货号        名称")
    for _, r in under.head(20).iterrows():
        print(f"  {int(r.cn_sold):>7}  {int(r.kr_sold):>3}  {int(r.avg_price):>9}  {str(r.brand)[:14]:14} {r.article_no:11} {str(r.title)[:26]}")

    # 榜2：LV 专项（用户主营），带缺口
    lv = g[g.brand.astype(str).str.contains(r"LOUIS VUITTON|路易威登|\bLV\b", case=False, na=False, regex=True)].sort_values("gap_ratio", ascending=False)
    print(f"\n★ LV 专项 缺口榜（中国销量/本地卖家）: 共 {len(lv)} 款 LV")
    print("  缺口比  中国销量  本地  成交均价₩   货号        名称")
    for _, r in lv[lv.cn_sold >= 100].head(15).iterrows():
        print(f"  {r.gap_ratio:>6.0f}  {int(r.cn_sold):>7}  {int(r.kr_sold):>3}  {int(r.avg_price):>9}  {r.article_no:11} {str(r.title)[:28]}")

    out = g.to_dict("records")
    json.dump({"count": len(out), "rows": out}, open("data/dewu_market.json", "w"), ensure_ascii=False, indent=1)
    print(f"\n✓ 聚合 {len(out)} 货号 → data/dewu_market.json")


if __name__ == "__main__":
    main()
