#!/usr/bin/env python3
"""LV 机会榜导 Excel(中文表头,带时间戳),含 3 个 sheet:
  盈利机会榜 / 全部测算 / 版本尺码明细(每个货号哪个颜色·版本·尺码有得物价+对应净利)。
用法: python tools/export_excel.py [输出.xlsx]
"""
import sys, json, os, re, glob
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import warnings; warnings.filterwarnings("ignore")
from datetime import datetime
import pandas as pd
import yaml
from src.fx import krw_per_cny
from src.models import LVProduct, DewuProduct, Candidate
from src.scorer.score import compute_profit

_ts = datetime.now().strftime("%Y%m%d_%H%M")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(f"~/Desktop/poizon选品/LV机会榜_{_ts}.xlsx")
b = json.load(open("data/lv_opportunity_board.json"))
cfg = yaml.safe_load(open("config/settings.example.yaml", encoding="utf-8"))
if os.path.exists("config/settings.yaml"):
    cfg = yaml.safe_load(open("config/settings.yaml", encoding="utf-8"))
fx = krw_per_cny(cfg)

# 盈利机会榜:把量化标准各项加权分拆开显示 + 总分,按总分降序
COLS = {"opp": "总分", "s_demand": "需求分(0.40)", "s_net": "净利分(0.35)", "s_margin": "利润率分(0.25)",
        "article_no": "货号", "title": "名称", "cat": "品类", "cn_sold": "30天销量", "kr_sold": "韩国卖家",
        "lv_krw": "LV韩国价(₩)", "dewu_cny": "得物价(¥)", "net_cny": "净利(¥)", "margin": "利润率",
        "month_profit": "月利润潜力(¥)"}
def norm(rows):
    out = []
    for r in rows:
        r = dict(r); r.setdefault("dewu_cny", r.get("dewu_cn_cny"))
        out.append({v: r.get(k) for k, v in COLS.items()})
    return pd.DataFrame(out)

prof = norm(sorted(b.get("profitable", b.get("rows", [])), key=lambda r: r.get("opp", 0), reverse=True))
allc = norm(sorted(b.get("all_computed", []), key=lambda r: r.get("net_cny", 0), reverse=True))

# —— 版本尺码明细:读原始导出,拆颜色/版本/尺码,算每个可交易SKU的净利 ——
def num(v):
    if v is None or (isinstance(v, float) and pd.isna(v)): return 0.0
    s = str(v).replace(",", "").replace("KRW", "").replace("₩", "").replace("+", "").strip()
    if s in ("--", "", "-"): return 0.0
    m = re.search(r"[\d.]+", s); return float(m.group()) if m else 0.0
def field(txt, key):
    m = re.search(rf"{key}[:：]([^;；]+)", str(txt)); return m.group(1).strip() if m else ""

xs = sorted(glob.glob("data/商品搜索导出*.xlsx"))
detail = pd.DataFrame()
if xs:
    raw = pd.read_excel(xs[-1]); raw.columns = [c.strip() for c in raw.columns]
    lvmap = {r["article_no"]: r for r in b.get("profitable", [])}
    drows = []
    for _, row in raw.iterrows():
        art = str(row["商品货号"])
        if art not in lvmap:
            continue
        dewu_krw = num(row["过去30天成交均价"]) or num(row["当前中国最低出价"])
        if dewu_krw <= 0:
            continue  # 只列有得物价(可成交)的 SKU
        lv = lvmap[art]
        c = Candidate(article_no=art, lv=LVProduct(article_no=art, category=str(lv["cat"]), price_krw=lv["lv_krw"], sellable=True),
                      dewu=DewuProduct(article_no=art, market_price_cny=round(dewu_krw / fx, 2)))
        compute_profit(c, cfg, fx)
        spec = row["尺码/规格/颜色"]
        drows.append({"货号": art, "名称": str(lv["title"])[:24], "颜色": field(spec, "颜色"),
                      "版本": field(spec, "版本"), "尺码": field(spec, "尺码"),
                      "得物价(¥)": round(dewu_krw / fx), "LV价(₩)": lv["lv_krw"],
                      "净利(¥)": c.net_profit_cny, "利润率": c.margin_rate})
    detail = pd.DataFrame(drows).sort_values("利润率", ascending=False)

# —— 直发线(POIZON)——
direct = pd.DataFrame()
if os.path.exists("data/direct_board.json"):
    dr = json.load(open("data/direct_board.json")).get("rows", [])
    direct = pd.DataFrame([{
        "利润率": r.get("margin"), "净利(₩)": r.get("net_krw"), "技术费(₩)": r.get("fee"),
        "直发价(₩)": r.get("direct_krw"), "LV买入(₩)": r.get("lv_krw"),
        "货号": r.get("article_no"), "名称": str(r.get("name", ""))[:24],
    } for r in dr])

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with pd.ExcelWriter(OUT, engine="openpyxl") as xw:
    prof.to_excel(xw, sheet_name="线1_现货机会榜", index=False)
    if len(direct): direct.to_excel(xw, sheet_name="线2_直发机会榜", index=False)
    if len(allc): allc.to_excel(xw, sheet_name="现货_全部测算", index=False)
    if len(detail): detail.to_excel(xw, sheet_name="现货_版本尺码明细", index=False)
    for ws in xw.sheets.values():
        ws.freeze_panes = "A2"
        for col in ws.columns:
            w = max((len(str(c.value)) for c in col if c.value is not None), default=8)
            ws.column_dimensions[col[0].column_letter].width = min(max(w + 2, 10), 42)
        for row in ws.iter_rows(min_row=2):
            for c in row:
                if ws.cell(1, c.column).value == "利润率" and isinstance(c.value, (int, float)):
                    c.number_format = "0%"
print(f"✓ 导出 {len(prof)}盈利 + {len(allc)}测算 + {len(detail)}个SKU明细 → {OUT}")
