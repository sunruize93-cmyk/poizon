#!/usr/bin/env python3
"""直发选品(单模块,2026-08 起) —— 只做韩国 POIZON 直发。

背景:现货(Ship-to-Verify)与直发(Direct)合并为一个模块。用户当前看不了国内得物立即变现
信息 → 砍掉「立即变现」策略分支,只按直发口径做。卖价=POIZON 直发最低价(bt=27,KRW),
成本=LV×0.8891(无物流,月付固定),技术费=14%封顶₩15k~45k。

排序(赚钱第一性原理): 直发月利润潜力 = 直发净利(₩→¥) × 中国30天销量
分层: 销量好(≥10)→直发优先 / 适中(3-9)→备选 / 不好(≤2)→仅毛利极高才做
输入: data/direct_board.json(direct_board.py 产出) + data/dewu_market.json(需求)
用法: python tools/direct_select.py [--top 20]
"""
import json, sys, os, argparse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from src.fx import krw_per_cny
import yaml
cfg = yaml.safe_load(open("config/settings.example.yaml", encoding="utf-8"))
fx = krw_per_cny(cfg)

GOOD, BAD = 10, 2


def tier(sales):
    if sales >= GOOD:
        return "销量好"
    if sales <= BAD:
        return "销量不好"
    return "销量适中"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()
    db = json.load(open("data/direct_board.json"))
    mkt = {r["article_no"][:8]: r for r in json.load(open("data/dewu_market.json"))["rows"]}
    rows = []
    for r in db["rows"]:
        a = r["article_no"]
        d = mkt.get(a, {})
        cn = int(d.get("cn_sold") or 0)
        masked = int(d.get("cn_masked") or 0)
        net_y = round((r["net_krw"] or 0) / fx)   # 直发净利 ₩→¥
        rows.append({
            "article_no": a, "name": str(r.get("name", ""))[:22],
            "cn_sold": cn, "cn_masked": masked, "kr_sold": int(d.get("kr_sold") or 0),
            "direct_krw": r.get("direct_krw"), "net_krw": r.get("net_krw"),
            "net_cny": net_y, "margin": r.get("margin"), "cny_display": r.get("cny_display"),
            "declare": r.get("declare"), "edition": r.get("edition", ""), "size": r.get("size", ""),
            "month_y": round((r["net_krw"] or 0) / fx * cn),
        })
    rows.sort(key=lambda r: -r["month_y"])
    pos = [r for r in rows if r["net_krw"] > 0]
    print(f"═══ 直发选品(单模块,只做韩国POIZON直发) — {len(rows)}款,正毛利{len(pos)}款 ═══")
    print(" # 货号    名称                中国30天销 直发价₩   直发净利₩  净利¥ 利润率  直发显示¥ 月利润¥ 分层")
    for i, r in enumerate(rows[: args.top], 1):
        flag = "⚠申报" if r.get("declare") else ""
        est = "*" if r.get("cn_masked") else " "
        print(f"{i:>2} {r['article_no']:8} {r['name'][:16]:16} {r['cn_sold']:>5}{est} {r['direct_krw']:>8,} "
              f"{r['net_krw']:>9,} {r['net_cny']:>6,} {r['margin']:>5.0%} {r.get('cny_display',0):>7.0f}{flag:>3} "
              f"{r['month_y']:>7,}  {tier(r['cn_sold'])}")
    print("\n *=30天销量含<5估算; 只做直发(无立即变现); 直发显示¥=得物买家看到的CNY价; ⚠申报=超200万KRW")
    json.dump({"as_of": "2026-08-05", "fx_krw_per_cny": fx, "rows": rows[: args.top]},
              open("data/direct_select.json", "w"), ensure_ascii=False, indent=1)
    print(f"\n✓ → data/direct_select.json (Top{args.top})")


if __name__ == "__main__":
    main()
