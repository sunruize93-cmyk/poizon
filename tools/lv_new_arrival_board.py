#!/usr/bin/env python3
"""上新窗口机会板(v1,图片日期近似 newness;diff 快照成熟后升级为精确)。

新品套利窗口 = 近期上架(得物图片上传日近) × 本地卖家≈0(韩国没人卖) × 可出价 × 得物价支撑毛利。
用得物SKU图片路径里的上传日(YYYYMMDD)近似上架时间——注意是弱代理(有重传噪声)。
用法: python tools/lv_new_arrival_board.py [近N天,默认120]
产出: data/lv_new_candidates.json(待抓价的近期上新)+ 打印。
"""
import sys, re, json, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import warnings
warnings.filterwarnings("ignore")
import pandas as pd
import yaml
from datetime import date

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 120
XLSX = "data/商品搜索导出20260703.xlsx"
TODAY = 20260703  # 快照日(与导出同日)


def num(v):
    if v is None or (isinstance(v, float) and pd.isna(v)): return 0.0
    s = str(v).replace(",", "").replace("KRW", "").replace("₩", "").replace("+", "").strip()
    if s in ("--", "", "-"): return 0.0
    m = re.search(r"<\s*(\d+)", s)
    if m: return float(m.group(1)) / 2
    m = re.search(r"[\d.]+", s); return float(m.group()) if m else 0.0


def days_between(d1, d2):
    from datetime import date as _d
    def parse(x): return _d(int(str(x)[:4]), int(str(x)[4:6]), int(str(x)[6:8]))
    return (parse(d2) - parse(d1)).days


df = pd.read_excel(XLSX)
df.columns = [c.strip() for c in df.columns]
df["imgdate"] = df["SKU图片"].map(lambda u: (re.search(r'/(\d{8})/', str(u)) or [None, None])[1])
df["_cn"] = df["中国市场总销量"].map(num); df["_kr"] = df["本地卖家总销量"].map(num)
df["_avg"] = df["过去30天成交均价"].map(num).replace(0, pd.NA)
df["_low"] = df["当前中国最低出价"].map(num).replace(0, pd.NA)
df["_bid"] = pd.to_numeric(df["用户是否能出价 1:允许出价 0:不可出价"], errors="coerce").fillna(0)

g = df.groupby("商品货号").agg(
    title=("商品名称", "first"), cat2=("商品二级类目", "first"),
    imgdate=("imgdate", "max"), cn_sold=("_cn", "sum"), kr_sold=("_kr", "sum"),
    avg=("_avg", "median"), low=("_low", "median"), bid=("_bid", "max"),
).reset_index().rename(columns={"商品货号": "article_no"})
g["cn_price"] = g["avg"].fillna(g["low"]).fillna(0)
g = g[g.imgdate.notna()]
g["age_days"] = g.imgdate.map(lambda d: days_between(d, TODAY))

# 近期上架 × 可出价 × 本地卖家薄
recent = g[(g.age_days <= DAYS) & (g.bid == 1) & (g.kr_sold <= 2)].copy()
recent = recent.sort_values("age_days")
prices = json.load(open("data/lv_prices.json")).get("results", {}) if os.path.exists("data/lv_prices.json") else {}

def clean(a):
    m = re.match(r'^([A-Z0-9]{5,8})', str(a)); return m.group(1) if m else None

recent["clean"] = recent.article_no.map(clean)
print(f"近{DAYS}天上架(图片日近似) × 可出价 × 本地卖家≤2: {len(recent)} 款")
have = recent[recent.clean.isin(prices.keys())]
need = recent[~recent.clean.isin(prices.keys()) & recent.clean.notna()]
print(f"  已抓价 {len(have)} | 待抓价 {len(need)}\n")

# 已抓价的直接算毛利
cfg = yaml.safe_load(open("config/settings.example.yaml", encoding="utf-8"))
from src.fx import krw_per_cny
from src.models import LVProduct, DewuProduct, Candidate
from src.scorer.score import compute_profit
fx = krw_per_cny(cfg)
board = []
for _, r in have.iterrows():
    pr = prices.get(r.clean, {})
    lv = float(pr.get("priceRaw") or 0)
    if lv <= 0 or r.cn_price <= 0 or pr.get("status") != 200: continue
    c = Candidate(article_no=r.clean, lv=LVProduct(article_no=r.clean, category=str(r.cat2), price_krw=lv, sellable=True),
                  dewu=DewuProduct(article_no=r.clean, market_price_cny=round(r.cn_price / fx, 2)))
    compute_profit(c, cfg, fx)
    board.append({"article_no": r.clean, "title": str(r.title)[:26], "cat": r.cat2, "age_days": int(r.age_days),
                  "imgdate": r.imgdate, "cn_sold": int(r.cn_sold), "kr_sold": int(r.kr_sold),
                  "lv_krw": int(lv), "dewu_cny": round(r.cn_price / fx), "net": c.net_profit_cny, "margin": c.margin_rate})
board.sort(key=lambda x: (x["margin"], -x["age_days"]), reverse=True)
print("★ 近期上架 × 已抓价 机会板(按毛利):")
print("  上架天 中国销量 韩卖 净利¥ 利润率  LV韩价₩  得物¥ 货号     名称")
for b in board[:20]:
    print(f"  {b['age_days']:>4} {b['cn_sold']:>6} {b['kr_sold']:>3} {b['net']:>6.0f} {b['margin']:>5.0%} {b['lv_krw']:>8} {b['dewu_cny']:>6} {b['article_no']:8} {b['title'][:20]}")

json.dump({"need_price": [c for c in need.clean.dropna().tolist()], "board": board},
          open("data/lv_new_candidates.json", "w"), ensure_ascii=False, indent=1)
print(f"\n✓ {len(board)}款已算 + {len(need)}款待抓价 → data/lv_new_candidates.json")
