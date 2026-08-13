#!/usr/bin/env python3
"""直发出价准备清单(bid_prep) —— 利润倒推出价,人工审改后走 API 挂单。

定价逻辑(用户 2026-08 确认):不"看最低价加一点",而是**利润倒推**:
  1) 定目标利润率 → 反算出价上限(₩): 出价 − 技术费(14%封顶15k~45k) − 成本(LV×0.8891) = 目标利润率×成本
  2) 和当前直发最低价(bt=27)做交集:
     - 目标价 ≤ 最低价 → 挂目标价(能抢单+达标)
     - 目标价 > 最低价 → 挂最低价薄利抢单(⚠人工定) 或 挂目标价等单
输出: 136款(用户人工核过的 PZ=可走直发) 建议出价/预期净利/竞争状态 → data/bid_prep.json + Excel
用法: python tools/bid_prep.py [--margin 0.15] [--top 40]
"""
import json, sys, os, argparse, warnings
warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from src.fx import krw_per_cny
import yaml
cfg = yaml.safe_load(open("config/settings.example.yaml", encoding="utf-8"))
fx = krw_per_cny(cfg)

FEE_MIN, FEE_MAX, FEE_RATE = 15000, 45000, 0.14


def fee(sell):
    return max(FEE_MIN, min(sell * FEE_RATE, FEE_MAX))


def net(sell, cost):
    return sell - fee(sell) - cost


def target_price(cost, m):
    """出价使净利=目标利润率×成本。高值款费封顶45k。"""
    t = cost * (1 + m) + FEE_MAX
    if fee(t) >= FEE_MAX:
        return t
    return cost * (1 + m) / (1 - FEE_RATE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--margin", type=float, default=0.15, help="目标利润率(默认15%)")
    ap.add_argument("--top", type=int, default=0, help="只出前N(0=全部)")
    args = ap.parse_args()
    M = args.margin

    arts = json.load(open("data/pz_136.json"))
    prices = json.load(open("data/lv_prices.json")).get("results", {})
    bd = {r["article_no"]: r for r in json.load(open("data/batch_direct.json"))["rows"]}

    rows = []
    for a in arts:
        lv = float((prices.get(a) or {}).get("priceRaw") or 0)
        r = bd.get(a)
        if lv <= 0 or not r:
            continue
        cost = lv * 0.8891
        lowest = r["direct_krw"]
        tp = target_price(cost, M)
        net_lowest = net(lowest, cost)
        mg_lowest = net_lowest / cost
        if tp <= lowest:
            bid, net_bid, mg_bid = tp, net(tp, cost), M
            status = "✓挂目标价即可抢单+达标"
        else:
            bid, net_bid, mg_bid = lowest, net_lowest, mg_lowest
            if mg_lowest >= 0.10:
                status = f"≈最低价利润率{mg_bid:.0%},挂最低价抢单(抢单需再低1档)"
            else:
                status = f"薄利({mg_bid:.0%}%),人工定: 降价抢单 or 挂目标价等单"
        rows.append({
            "article_no": a, "name": str(r["name"])[:22], "cn_sold": r["cn_sold"],
            "lv_krw": int(lv), "cost_krw": round(cost), "lowest_krw": int(lowest),
            "target_krw": round(tp), "bid_krw": round(bid),
            "net_krw": round(net_bid), "net_cny": round(net_bid / fx),
            "margin": mg_bid, "cny_display": round(bid / cfg["direct"]["dewu_fx"] * cfg["direct"]["cross_border_tax"]),
            "declare": bid > cfg["direct"]["declare_threshold_krw"],
            "status": status,
        })
    # 排序: 达标/可抢单优先, 再按净利
    rows.sort(key=lambda r: (r["status"].startswith("✓"), -r["net_cny"]))
    if args.top:
        rows = rows[: args.top]

    print(f"═══ 直发出价准备清单({len(rows)}款, 目标利润率{M:.0%}) ═══")
    print(" # 货号    名称                销量 LV价₩    成本₩   直发最低₩ 目标价₩ 建议出价₩ 净利₩ 净利¥ 利润率  显示¥  状态")
    for i, r in enumerate(rows, 1):
        fl = "⚠申报" if r["declare"] else ""
        print(f"{i:>2} {r['article_no']:8} {r['name'][:14]:14} {r['cn_sold']:>4} {r['lv_krw']:>8,} "
              f"{r['cost_krw']:>7,} {r['lowest_krw']:>8,} {r['target_krw']:>7,} {r['bid_krw']:>8,} "
              f"{r['net_krw']:>6,} {r['net_cny']:>5,} {r['margin']:>5.0%} {r['cny_display']:>5,}{fl}  {r['status'][:14]}")
    json.dump({"as_of": "2026-08-05", "target_margin": M, "rows": rows},
              open("data/bid_prep.json", "w"), ensure_ascii=False, indent=1)
    print(f"\n✓ → data/bid_prep.json")


if __name__ == "__main__":
    main()
