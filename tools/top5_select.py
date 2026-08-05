#!/usr/bin/env python3
"""选品清单 Top5：按销量分层决定变现策略，输出「一次只做 5 个」的可执行清单。

决策框架(用户口径,2026-08):
  销量好(30天≥GOOD)  → 挂普通单,不考虑立即变现(正常能卖就不牺牲6%折让)
  销量不好(30天≤BAD) → 立即变现 + 考虑取消风险(库存别压);但立即变现价和72小时销量
                       要进软件看 → 先按模型预判「值不值得进软件核」
  销量适中           → 备选(有精力再做)

排序(赚钱第一性原理):月利润潜力 = 该策略下单件净利 × 30天销量
  好→挂单净利; 不好→立即变现净利(单次变现即回本,资金效率高); 适中→两场景取高
输出: 每行含 货号/名称/30天销量/挂单净利/立即变现净利/策略/是否值得进软件核72h。
用法: python tools/top5_select.py [--top 5]
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

# ---- 可调阈值 ----
GOOD_SALES = 10       # 30天销量≥此=销量好
BAD_SALES = 2         # 30天销量≤此=销量不好(中间=适中)
WORTH_MIN_NET = 200   # 进软件核的净利下限(¥):低于此预判不值得进软件
WORTH_MIN_MARGIN = 0.10  # 进软件核的利润率下限

TIER_LABEL = {0: "销量好", 1: "销量适中", 2: "销量不好"}
STRATEGY = {0: "挂普通单(不考虑立即变现)", 1: "备选(卖得慢,资金回笼慢)", 2: "立即变现+考虑取消风险"}


def tier(row):
    s = int(row.get("cn_sold", 0))
    if s >= GOOD_SALES:
        return 0
    if s <= BAD_SALES:
        return 2
    return 1


def tier_profit(row, t):
    """该策略下用哪档净利排月利润潜力。"""
    if t == 0:
        return row.get("net_normal", 0) or 0
    if t == 2:
        return row.get("net_instant", 0) or 0
    return max(row.get("net_normal", 0) or 0, row.get("net_instant", 0) or 0)


def worth_check(row, t):
    """预判值不值得进软件核72h销量+实际立即变现价。
    只有『销量不好→立即变现』策略的款才需要核；销量好/适中不核。"""
    if t != 2:
        return False, "挂单/备选策略,不立即变现,无需进软件"
    profit = row.get("net_instant", 0) or 0
    margin = row.get("margin", 0) or 0
    if profit >= WORTH_MIN_NET and margin >= WORTH_MIN_MARGIN:
        return True, f"立即变现净利¥{profit:.0f}≥¥{WORTH_MIN_NET} 且利润率{margin:.0%}≥{WORTH_MIN_MARGIN:.0%},值得进软件核"
    return False, f"立即变现净利¥{profit:.0f}<¥{WORTH_MIN_NET} 或利润率{margin:.0%}<{WORTH_MIN_MARGIN:.0%},不值得核"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=5)
    args = ap.parse_args()

    board = json.load(open("data/lv_opportunity_board.json"))
    rows = [r for r in board["all_computed"] if (r.get("net_cny") or 0) > 0]
    for r in rows:
        t = tier(r)
        r["_tier"] = t
        r["_tp"] = tier_profit(r, t)
        r["_month"] = r["_tp"] * int(r.get("cn_sold", 0))
    # 月利润潜力降序 = 该策略下一个月能赚多少钱
    rows.sort(key=lambda r: r["_month"], reverse=True)

    top = rows[: args.top]
    print(f"═══ 选品清单 Top{args.top}（销量分层→变现策略; {GOOD_SALES}好/{BAD_SALES}不好 为界）═══\n")
    print(" # 货号    名称                30天销 挂单净利 立即变现净利 月利润¥  分层     策略                       值不值得进软件")
    for i, r in enumerate(top, 1):
        worth, why = worth_check(r, r["_tier"])
        r["_worth"] = worth
        mark = "✓核" if worth else "—"
        print(f"{i:>2} {r['article_no']:8} {r['title'][:16]:16} {r['cn_sold']:>5} "
              f"{r.get('net_normal', 0):>7.0f} {r.get('net_instant', 0):>10.0f} "
              f"{r['_month']:>8.0f}  {TIER_LABEL[r['_tier']]:5}  {STRATEGY[r['_tier']]:18} {mark}")

    print("\n—— 每款进软件前先按上面『值不值得核』预判; ✓核 = 值得进软件看72h销量+实际立即变现价 ——")
    print("—— 备选(销量适中)只在 Top5 里那几款都做不动时再补 ——")

    out = {"as_of": "2026-08-05", "top_n": args.top, "rows": top}
    json.dump(out, open("data/top5_list.json", "w"), ensure_ascii=False, indent=1)
    print(f"\n✓ → data/top5_list.json")


if __name__ == "__main__":
    main()
