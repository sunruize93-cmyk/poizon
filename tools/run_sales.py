"""逐(码数×包装)选品榜单：用得物 App「最近购买」真实成交 + 销量速度算利润并排序。

与 run_real.py 的区别：run_real 用官方 API 的「最低出价」(ask)；本工具用 App 抓到的
**真实成交价**(deal) 折算结算口径算利润，并带上「近期好卖」速度，更贴近能否卖出。

数据来源：data/dewu_sales/<货号>.json（tools/dewu_app_sales.py 截图→视觉读出）。
LV 采购价取 config/skus.csv 的 lv_price_krw；category 决定物流。

用法：python tools/run_sales.py
"""
import csv
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import yaml
from dotenv import load_dotenv

from src.dewu_source.app_sales import load_all
from src.fx import krw_per_cny
from src.models import Candidate, DewuProduct, LVProduct
from src.scorer.score import compute_profit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))
cfg = yaml.safe_load(open(os.path.join(ROOT, "config", "settings.example.yaml"), encoding="utf-8"))
fx = krw_per_cny(cfg)

skus = {r["article_no"].upper(): r for r in
        csv.DictReader(open(os.path.join(ROOT, "config", "skus.csv"), encoding="utf-8-sig"))}
sales = load_all()

out = []
for art, ps in sales.items():
    meta = skus.get(art)
    if not meta or not (meta.get("lv_price_krw") or "").strip():
        print(f"  {art:<8} 跳过(skus.csv 无 LV 价)")
        continue
    lv_krw = float(meta["lv_price_krw"])
    cat = meta.get("category", "")
    print(f"  {art:<8} ✓ {ps.title[:30]} · {len(ps.specs)}规格 · 月化{ps.sold_per_month_total}")
    for s in ps.specs:
        cand = Candidate(
            article_no=art,
            lv=LVProduct(article_no=art, category=cat, price_krw=lv_krw, sellable=True),
            dewu=DewuProduct(article_no=art, market_price_cny=s.median_settle_cny,
                             sales_30d=s.n_30d, wish_count=ps.wish_count,
                             seller_count=ps.seller_bid_count))
        compute_profit(cand, cfg, fx)
        out.append(dict(
            art=art, title=ps.title[:30], size=s.size, pkg=s.packaging,
            spm=s.sold_per_month, n30=s.n_30d, n90=s.n_90d, last=s.last_sale_days,
            deal=s.median_taxed_cny, settle=s.median_settle_cny,
            cost=cand.cost_cny, pn=cand.profit_normal_cny, pi=cand.profit_instant_cny,
            profit=cand.net_profit_cny, margin=cand.margin_rate, scen=cand.sell_scenario,
            wish=ps.wish_count, bid=ps.seller_bid_count, stock=ps.stock_left))

# 机会分：近期好卖(速度) × 赚钱(净利)，都归一化后相乘，兼顾「卖得动」与「有利润」
if out:
    mx_spm = max(x["spm"] for x in out) or 1
    mx_pf = max(max(x["profit"] for x in out), 1)
    for x in out:
        v = x["spm"] / mx_spm
        p = max(x["profit"], 0) / mx_pf
        x["opp"] = round((v * p) ** 0.5, 3)  # 几何平均：任一为0则机会为0
out.sort(key=lambda x: x["opp"], reverse=True)

# 导出 Excel
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

wb = Workbook(); ws = wb.active; ws.title = "近期好卖榜"
cols = [("opp", "机会分"), ("art", "货号"), ("title", "品名"), ("size", "码数"), ("pkg", "包装"),
        ("spm", "月化销量"), ("n30", "30天"), ("last", "最近(天)"),
        ("deal", "成交价(含税)"), ("settle", "结算价"), ("cost", "总成本"),
        ("pn", "普通利"), ("pi", "立即变现利"), ("profit", "净利"), ("margin", "利润率"),
        ("scen", "场景"), ("wish", "想要"), ("bid", "竞价商家"), ("stock", "仅剩")]
ws.append([t for _, t in cols])
for cell in ws[1]:
    cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="00B386")
for x in out:
    x = dict(x); x["margin"] = f'{x["margin"]*100:.0f}%'
    x["scen"] = "立即变现" if x["scen"] == "instant" else "普通"
    ws.append([x[k] for k, _ in cols])
    # 又快又赚：月化≥3 且 净利≥300 高亮
    if x["spm"] >= 3 and x["profit"] >= 300:
        for cell in ws[ws.max_row]:
            cell.fill = PatternFill("solid", fgColor="E8F8F2")
for col in ws.columns:
    w = max((len(str(c.value)) for c in col if c.value), default=8)
    ws.column_dimensions[col[0].column_letter].width = min(w + 2, 30)
os.makedirs(os.path.join(ROOT, "report"), exist_ok=True)
path = os.path.join(ROOT, "report", "近期好卖榜单_逐码数.xlsx"); wb.save(path)

print(f"\n✓ 导出 {len(out)} 个(码数×包装) → {path}")
print(f"\nTOP（汇率 1CNY={fx:.1f}KRW）按机会分(销量×利润):")
print(f"{'机会':>5} {'货号':<8}{'码数':<6}{'包装':<8}{'月化':>5}{'净利':>7}{'利润率':>7}{'场景':>8}")
for x in out[:15]:
    print(f"{x['opp']:>5} {x['art']:<8}{x['size']:<6}{x['pkg']:<8}{x['spm']:>5}"
          f"¥{x['profit']:>5.0f}{x['margin']*100:>6.0f}% {'立即变现' if x['scen']=='instant' else '普通':>8}")
