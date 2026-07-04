#!/usr/bin/env python3
"""一键选品:把确定性分析串成一条命令,并明确告诉你还差哪些(需浏览器/AI 的)步骤。

用法: python tools/select.py [--brand LV] [--min-margin 0.03] [--fresh-days 3]
它做(纯本地、无浏览器):
  1. 找最新得物导出 xlsx → market_opportunities.py 聚合+缺口 shortlist
  2. lv_opportunity_board.py 用已抓的 LV 价算利润 → 机会榜
  3. 报告:机会榜 Top + 还缺哪些 LV 价(货号) + 导出是否过期(该重导)
浏览器步骤(导出/抓价)仍由 AI 或 Sonnet 子代理执行——本脚本会打印出该跑的命令。
"""
import argparse, glob, json, os, re, subprocess, sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
PY = ".venv/bin/python"


def newest_export():
    xs = sorted(glob.glob("data/商品搜索导出*.xlsx"))
    return xs[-1] if xs else None


def export_age_days(path):
    m = re.search(r"(\d{8})", os.path.basename(path))
    if not m:
        return 999
    d = m.group(1)
    return (date.today() - date(int(d[:4]), int(d[4:6]), int(d[6:8]))).days


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="LV")
    ap.add_argument("--min-margin", type=float, default=0.0)
    ap.add_argument("--fresh-days", type=int, default=3, help="得物导出超过几天算过期")
    ap.add_argument("--direct-limit", type=int, default=30, help="直发线抓多少个货号的POIZON价(API,慢)")
    ap.add_argument("--no-direct", action="store_true", help="跳过直发线(只出现货线)")
    args = ap.parse_args()

    print(f"═══ 一键选品 [{args.brand}] ═══\n")
    exp = newest_export()
    if not exp:
        print("✗ 没有得物导出数据。请让 AI 跑: 后台按品牌筛选→导出→下载")
        print("  (poizon_seller_lv_export.mjs + poizon_seller_dl.mjs)")
        return
    age = export_age_days(exp)
    print(f"得物导出: {os.path.basename(exp)} ({age} 天前)" + ("  ⚠️ 建议重导" if age > args.fresh_days else "  ✓"))

    # 1) 需求聚合 + shortlist
    subprocess.run([PY, "tools/market_opportunities.py", exp], capture_output=True)
    # 2) 机会榜
    r = subprocess.run([PY, "tools/lv_opportunity_board.py"], capture_output=True, text=True)
    board_out = r.stdout

    # 3) 缺价检测
    short = json.load(open("data/lv_demand_shortlist.json"))["rows"] if os.path.exists("data/lv_demand_shortlist.json") else []
    prices = json.load(open("data/lv_prices.json")).get("results", {}) if os.path.exists("data/lv_prices.json") else {}
    need = []
    for s in short:
        m = re.match(r"^([A-Z0-9]{5,8})", str(s["article_no"]))
        if m and m.group(1) not in prices:
            need.append(m.group(1))
    need = list(dict.fromkeys(need))

    # 打印机会榜(过滤 min-margin 由 board 已排序,这里直接展示 board 输出的核心)
    print("\n══ 线① 中国得物(现货)══")
    for line in board_out.splitlines():
        if any(k in line for k in ["机会榜", "机会分", "盈利", "✓", "净利", "%"]) or re.search(r"\d", line):
            print(line)

    # 4) 线② 直发(POIZON, bt=27, API 抓价, 按利润率降序)
    if not args.no_direct:
        print(f"\n══ 线② 直发出价(POIZON, Top{args.direct_limit})══")
        dr = subprocess.run([PY, "tools/direct_board.py", str(args.direct_limit)], capture_output=True, text=True)
        for line in dr.stdout.splitlines():
            if any(k in line for k in ["直发线", "利润率", "✓"]) or re.search(r"\d", line):
                print(line)

    print("\n── 下一步(需浏览器/AI)──")
    if age > args.fresh_days:
        print(f"• 得物导出已 {age} 天,建议重导最新销量")
    if need:
        print(f"• {len(need)} 款有中国需求但缺 LV 价 → 让 Sonnet 抓价:")
        print(f"  LV_PROFILE=tools/.lv_profile_$(date +%s) node tools/lv_prices.mjs {' '.join(need[:60])}")
        print("  抓完重跑 python tools/select.py 即得完整榜")
    else:
        print("• LV 价已齐,机会榜即最终结果")
    # 上新窗口
    newf = sorted(glob.glob("data/snapshots/new_*.txt"))
    if newf:
        print(f"• 上新窗口: 最新差分 {os.path.basename(newf[-1])} (cron 每日累积)")


if __name__ == "__main__":
    main()
