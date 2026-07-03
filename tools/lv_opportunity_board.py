#!/usr/bin/env python3
"""LV 机会榜：需求(得物seller后台) × 供给(LV韩价) → 净利,排出该进哪些冷门潜力款。

输入:
  data/lv_demand_shortlist.json  需求(中国销量/本地卖家/得物中国价KRW/品类)
  data/lv_prices.json            LV 韩国供给价(lv_prices.mjs 抓)
逻辑: 得物中国成交价(KRW)→CNY 作卖价, LV韩价作成本, 复用 compute_profit 算净利/利润率。
机会分 = 需求×利润 综合(低本地竞争已是前提)。
"""
import json
import os
import sys
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.fx import krw_per_cny
from src.models import LVProduct, DewuProduct, Candidate
from src.scorer.score import compute_profit

cfg = yaml.safe_load(open("config/settings.example.yaml", encoding="utf-8"))
if os.path.exists("config/settings.yaml"):
    cfg = yaml.safe_load(open("config/settings.yaml", encoding="utf-8"))
fx = krw_per_cny(cfg)
# 额外买入折扣(券/会员/免税叠加,除VAT退税外)。LV_DISCOUNT=0.15 表示再省15%。
extra_disc = float(os.getenv("LV_DISCOUNT", "0"))
if extra_disc:
    cfg["cost"]["voucher_rate"] = cfg["cost"].get("voucher_rate", 0.03) + extra_disc

demand = {r["article_no"]: r for r in json.load(open("data/lv_demand_shortlist.json"))["rows"]}
prices = json.load(open("data/lv_prices.json")).get("results", {}) if os.path.exists("data/lv_prices.json") else {}

rows = []
for art, d in demand.items():
    pr = prices.get(art) or prices.get(art.upper()) or {}
    lv_krw = float(pr.get("priceRaw") or 0)
    cn_krw = float(d.get("cn_price") or 0)
    if lv_krw <= 0 or cn_krw <= 0:
        continue   # 缺 LV 价或得物价,跳过(待补抓)
    cand = Candidate(
        article_no=art,
        lv=LVProduct(article_no=art, category=str(d.get("cat3") or d.get("cat2") or ""),
                     price_krw=lv_krw, sellable=bool(pr.get("sellable", True))),
        dewu=DewuProduct(article_no=art, market_price_cny=round(cn_krw / fx, 2),
                         wish_count=0, seller_count=0),
    )
    compute_profit(cand, cfg, fx)
    rows.append({
        "article_no": art, "title": str(d.get("title", ""))[:30],
        "cat": d.get("cat3") or d.get("cat2"), "cn_sold": int(d.get("cn_sold", 0)),
        "kr_sold": int(d.get("kr_sold", 0)), "lv_krw": int(lv_krw),
        "dewu_cn_cny": round(cn_krw / fx, 0), "net_cny": cand.net_profit_cny,
        "margin": cand.margin_rate, "scenario": cand.sell_scenario,
    })

prof = [r for r in rows if r["net_cny"] > 0]
# 机会分:偏「每单利润+利润率」(找冷门高毛利),需求只作次要加权(有量即可,不追爆款)。
# 低本地竞争是共同前提。这样才surface出「别人没盯上、单件却很赚」的冷门潜力款。
if prof:
    mx_sold = max(r["cn_sold"] for r in prof) or 1
    mx_net = max(r["net_cny"] for r in prof) or 1
    mx_mg = max(r["margin"] for r in prof) or 1
    for r in prof:
        r["opp"] = round(0.45 * (r["net_cny"] / mx_net) + 0.35 * (r["margin"] / mx_mg)
                         + 0.20 * (r["cn_sold"] / mx_sold), 3)
    prof.sort(key=lambda r: r["opp"], reverse=True)

print(f"参与计算 {len(rows)} 款(有LV价+得物价) | 盈利 {len(prof)} 款 | 汇率1CNY={fx:.0f}KRW\n")
print("★ LV 冷门潜力机会榜（低韩国竞争 × 有中国需求 × 盈利）:")
print(" 机会分 中国销量 韩卖 净利¥ 利润率 品类   LV韩价₩   得物中国¥  货号     名称")
for r in prof[:25]:
    print(f" {r['opp']:.3f} {r['cn_sold']:>6} {r['kr_sold']:>3} {r['net_cny']:>6.0f} {r['margin']:>5.0%} {str(r['cat'])[:4]:4} {r['lv_krw']:>9} {r['dewu_cn_cny']:>8.0f}  {r['article_no']:8} {r['title'][:20]}")

json.dump({"count": len(prof), "rows": prof}, open("data/lv_opportunity_board.json", "w"), ensure_ascii=False, indent=1)
print(f"\n✓ 机会榜 → data/lv_opportunity_board.json ({len(prof)} 盈利款)")
skipped = len(demand) - len(rows)
if skipped:
    print(f"  ({skipped} 款缺 LV价/得物价未算,补抓 LV 价后重跑)")
