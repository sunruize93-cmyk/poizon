"""逐(码数×包装)综合选品榜单：得物 App 真实成交 + 销量速度/热度 + 利润 → 加权综合评分。

模型见 src/scorer/heat.py（流动性0.45 + 盈利0.40 + 风险0.15，先硬过滤再加权）。
数据来源 data/dewu_sales/<货号>.json（tools/dewu_app_sales.py 截图→视觉读出）。
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
from src.scorer.heat import score_specs
from src.scorer.score import compute_profit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))
cfg = yaml.safe_load(open(os.path.join(ROOT, "config", "settings.example.yaml"), encoding="utf-8"))
fx = krw_per_cny(cfg)

skus = {r["article_no"].upper(): r for r in
        csv.DictReader(open(os.path.join(ROOT, "config", "skus.csv"), encoding="utf-8-sig"))}
sales = load_all()

rows = []
for art, ps in sales.items():
    meta = skus.get(art)
    if not meta or not (meta.get("lv_price_krw") or "").strip():
        print(f"  {art:<8} 跳过(skus.csv 无 LV 价)")
        continue
    lv_krw = float(meta["lv_price_krw"]); cat = meta.get("category", "")
    print(f"  {art:<8} ✓ {ps.title[:28]} · {len(ps.specs)}规格 · 月化{ps.sold_per_month_total}")
    for s in ps.specs:
        cand = Candidate(
            article_no=art,
            lv=LVProduct(article_no=art, category=cat, price_krw=lv_krw, sellable=True),
            dewu=DewuProduct(article_no=art, market_price_cny=s.median_settle_cny))
        compute_profit(cand, cfg, fx)
        rows.append(dict(
            art=art, title=ps.title[:28], size=s.size, pkg=s.packaging,
            velocity=s.sold_per_month, n30=s.n_30d, n90=s.n_90d, last_sale_days=s.last_sale_days,
            deal=s.median_taxed_cny, settle=s.median_settle_cny,
            dmin=s.min_taxed_cny, dmax=s.max_taxed_cny, dmid=s.median_taxed_cny,
            cost=cand.cost_cny, pn=cand.profit_normal_cny, pi=cand.profit_instant_cny,
            net_profit=cand.net_profit_cny, margin=cand.margin_rate, scen=cand.sell_scenario,
            wish=ps.wish_count, buyers=ps.buyer_count, competition=ps.seller_bid_count,
            stock=ps.stock_left))

rows = score_specs(rows, cfg)

# 导出 Excel
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

wb = Workbook(); ws = wb.active; ws.title = "综合最优品"
cols = [("score", "综合分"), ("art", "货号"), ("title", "品名"), ("size", "码数"), ("pkg", "包装"),
        ("velocity", "月化销量"), ("n30", "30天"), ("last_sale_days", "最近(天)"),
        ("deal", "成交价含税"), ("settle", "结算价"), ("cost", "总成本"),
        ("pn", "普通利"), ("pi", "立即变现利"), ("net_profit", "净利"), ("margin", "利润率"),
        ("scen", "场景"), ("wish", "想要"), ("buyers", "累计买家"), ("competition", "竞价商家"),
        ("stock", "仅剩"), ("reject", "淘汰原因")]
ws.append([t for _, t in cols])
for cell in ws[1]:
    cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="00B386")
for x in rows:
    x = dict(x); x["margin"] = f'{x["margin"]*100:.0f}%'
    x["scen"] = "立即变现" if x["scen"] == "instant" else "普通"
    x["score"] = "" if not x["passed"] else round(x["score"], 3)
    ws.append([x.get(k, "") for k, _ in cols])
    fill = None
    if not x["passed"]:
        fill = "F2F2F2"                       # 淘汰：灰
    elif x["score"] and x["score"] >= 0.6:
        fill = "B7E9CF"                        # 优选：深绿
    elif x["score"] and x["score"] >= 0.45:
        fill = "E8F8F2"                        # 良好：浅绿
    if fill:
        for cell in ws[ws.max_row]:
            cell.fill = PatternFill("solid", fgColor=fill)
ws.freeze_panes = "A2"
for col in ws.columns:
    w = max((len(str(c.value)) for c in col if c.value), default=8)
    ws.column_dimensions[col[0].column_letter].width = min(w + 2, 30)
os.makedirs(os.path.join(ROOT, "report"), exist_ok=True)
path = os.path.join(ROOT, "report", "综合最优品榜单.xlsx"); wb.save(path)

passed = [x for x in rows if x["passed"]]
print(f"\n✓ {len(rows)} 个(码数×包装)，进榜 {len(passed)} 个 → {path}")
print(f"\nTOP（汇率 1CNY={fx:.1f}KRW · 综合分=流动性0.45+盈利0.40−风险0.15）:")
print(f"{'综合':>5} {'货号':<8}{'码数':<5}{'包装':<8}{'月化':>5}{'最近':>5}{'净利':>7}{'利率':>6} {'场景':<6}")
for x in passed[:20]:
    print(f"{x['score']:>5} {x['art']:<8}{x['size']:<5}{x['pkg']:<8}{x['velocity']:>5}"
          f"{x['last_sale_days']:>4.0f}d¥{x['net_profit']:>5.0f}{x['margin']*100:>5.0f}% "
          f"{'立即变现' if x['scen']=='instant' else '普通':<6}")
