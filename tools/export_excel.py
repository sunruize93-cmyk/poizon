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

# —— 选品清单 Top5(销量分层决策,2026-08 起的主输出)——
TLABEL = {0: "销量好", 1: "销量适中", 2: "销量不好"}
TSTRAT = {0: "挂普通单(不考虑立即变现)", 1: "备选", 2: "立即变现+考虑取消风险"}
top5 = pd.DataFrame()
if os.path.exists("data/top5_list.json"):
    t5 = json.load(open("data/top5_list.json"))
    def trow(i, r):
        return {"排名": i, "货号": r["article_no"], "名称": str(r["title"])[:24],
                "30天销量": r["cn_sold"], "挂单净利(¥)": r.get("net_normal"), "立即变现净利(¥)": r.get("net_instant"),
                "月利润潜力(¥)": round(r.get("_month") or r.get("month_profit") or 0),
                "分层": TLABEL.get(r.get("_tier"), ""), "策略": TSTRAT.get(r.get("_tier"), ""),
                "值得进软件核": "✓是" if r.get("_worth") else "—"}
    top5 = pd.DataFrame([trow(i, r) for i, r in enumerate(t5.get("rows", []), 1)])
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

# LV 侧库存(含首尔线下可买):lv_prices 的 locateInStore + skus[].storeSell
lvp = json.load(open("data/lv_prices.json")).get("results", {}) if os.path.exists("data/lv_prices.json") else {}
def store_info(art):
    """LV 库存标注。⚠️ storeSell/csc_Sellable 只代表『可下单/可订』,不是『店里现在有货』——
    实测 2026-08-05: 抓取全 true,官网却 4/5 售罄。官网实际库存才是准,此列仅供参考。"""
    v = lvp.get(art) or {}
    loc = v.get("locateInStore")
    if loc is True:
        n = v.get("nStore")
        if not n:
            n = len([s for s in (v.get("skus") or []) if s.get("storeSell")])
        return f"官网可订{n}尺码(实库以官网为准)" if n else "官网可订(实库以官网为准)"
    if loc is False:
        return "官网不可订"
    return "未抓(以官网为准)"

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
                      "净利(¥)": c.net_profit_cny, "利润率": c.margin_rate,
                      "首尔线下": store_info(art)})
    detail = pd.DataFrame(drows).sort_values("利润率", ascending=False)

# —— 直发线(POIZON)：货号级最优 + 逐版本尺码明细 ——
direct = direct_detail = pd.DataFrame()
if os.path.exists("data/direct_board.json"):
    db = json.load(open("data/direct_board.json"))
    def drow(r):
        age = r.get("price_age_h")
        return {"利润率": r.get("margin"), "净利(₩)": r.get("net_krw"), "技术费(₩)": r.get("fee"),
                "直发价(₩)": r.get("direct_krw"), "得物显示(¥)": r.get("cny_display"),
                "报价龄(h)": (round(age) if isinstance(age, (int, float)) else "?"),
                "超200万申报": "⚠是" if r.get("declare") else "", "货号": r.get("article_no"),
                "版本": r.get("edition", ""), "尺码": r.get("size", ""),
                "首尔线下": store_info(r.get("article_no")), "名称": str(r.get("name", ""))[:24]}
    direct = pd.DataFrame([drow(r) for r in db.get("rows", [])])
    direct_detail = pd.DataFrame([drow(r) for r in db.get("sku_detail", [])])

# —— 线3 供给缺口(得物有需求×韩国卖家≈0=抢先占位)——
listing = pd.DataFrame()
if os.path.exists("data/supply_gap.json"):
    sg = json.load(open("data/supply_gap.json")).get("rows", [])
    listing = pd.DataFrame([{
        "中国30天销量": r.get("cn_sold"), "韩国卖家": r.get("kr_sold"),
        "得物价(₩)": r.get("cn_price_krw"), "LV状态": r.get("lv_status"), "LV价(₩)": r.get("lv_krw") or "",
        "货号": r.get("article_no"), "品类": r.get("cat"), "首尔线下": store_info(r.get("article_no")),
        "名称": str(r.get("title", ""))[:26],
    } for r in sg])

# —— 重点款 SKU 级(现货 vs 直发,精确到版本尺码)——
picks = pd.DataFrame()
if os.path.exists("data/sku_picks.json"):
    sp = json.load(open("data/sku_picks.json")).get("rows", [])
    def prow(r):
        return {"货号": r["article_no"], "版本": r.get("edition", ""), "尺码": r.get("size", ""),
                "LV价(₩)": r.get("lv_krw"),
                "现货得物(¥)": r.get("spot_cny"), "现货净利(¥)": r.get("spot_net_cny"),
                "现货利润率": r.get("spot_margin"), "现货场景": r.get("spot_scenario"),
                "直发价(₩)": r.get("direct_krw"), "直发净利(₩)": r.get("direct_net_krw"),
                "直发利润率": r.get("direct_margin"), "直发显示(¥)": r.get("direct_cny_display"),
                "超200万申报": "⚠是" if r.get("declare") else "",
                "首尔线下": store_info(r["article_no"]), "名称": r.get("name", "")}
    # 每款内按两线最优利润率降序，货号成组
    def _best(r): return max([m for m in (r.get("spot_margin"), r.get("direct_margin")) if m is not None] or [-9])
    order = {}
    for r in sp: order[r["article_no"]] = max(order.get(r["article_no"], -9), _best(r))
    sp = sorted(sp, key=lambda r: (-order[r["article_no"]], r["article_no"], -_best(r)))
    picks = pd.DataFrame([prow(r) for r in sp])

# —— Top5 精确到尺码(类型×尺码,净利)——
sku5 = pd.DataFrame()
if os.path.exists("data/top5_skus.json"):
    sk5 = json.load(open("data/top5_skus.json"))
    srows = []
    for a, v in sk5.items():
        for r in v.get("top_skus", []):
            srows.append({"货号": a, "名称": v.get("name"), "LV价(₩)": v.get("lv_krw"),
                          "LV可买码": f"{v.get('lv_sizes',[None])[0]}~{v.get('lv_sizes',[None])[-1]}",
                          "颜色": r["颜色"], "版本": r["版本"], "尺码": r["尺码"],
                          "出价₩": r["出价₩"], "均价₩": r["均价₩"], "净利¥": r["净利¥"],
                          "利润率": r["利润率"], "真实成交": "实" if r["真实成交"] else "价"})
    sku5 = pd.DataFrame(srows)

# —— SKU 综合表单(常规码×权重) / 爆款预测 ——
comp = pred = pd.DataFrame()
if os.path.exists("data/sku_comprehensive.json"):
    sc = json.load(open("data/sku_comprehensive.json")).get("rows", [])
    comp = pd.DataFrame([{
        "综合分": r.get("score"), "货号": r.get("article_no"), "名称": r.get("title"),
        "类目": r.get("cat"), "颜色": r.get("颜色"), "版本": r.get("版本"), "包装": r.get("包装"),
        "尺码": r.get("尺码"), "尺码风险": r.get("尺码风险"),
        "SPU月销": r.get("spu_sales"), "净利¥": r.get("净利¥"), "利润率": r.get("利润率"),
        "月利润¥": r.get("月利润¥"), "真实成交": "有成交" if r.get("真实成交") else "仅出价",
    } for r in sc])
if os.path.exists("data/predict_hits.json"):
    ph = json.load(open("data/predict_hits.json"))
    pred = pd.DataFrame([{
        "信号": r.get("signal"), "货号": r.get("article_no"), "名称": r.get("name"),
        "30天销": r.get("cn_sold"), "上期销": r.get("cn_sold_prev"), "韩国卖家": r.get("kr_sold"),
        "现价净利¥": r.get("net_cny"), "利润率": r.get("margin"), "预测依据": r.get("why"),
    } for r in ph])

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with pd.ExcelWriter(OUT, engine="openpyxl") as xw:
    if len(top5): top5.to_excel(xw, sheet_name="选品清单Top5", index=False)
    if len(comp): comp.to_excel(xw, sheet_name="综合表单_SKU", index=False)
    if len(pred): pred.to_excel(xw, sheet_name="爆款预测", index=False)
    if len(sku5): sku5.to_excel(xw, sheet_name="Top5_尺码精确", index=False)
    prof.to_excel(xw, sheet_name="线1_现货机会榜", index=False)
    if len(direct): direct.to_excel(xw, sheet_name="线2_直发机会榜", index=False)
    if len(listing): listing.to_excel(xw, sheet_name="线3_供给缺口", index=False)
    if len(picks): picks.to_excel(xw, sheet_name="重点款_尺码版本", index=False)
    if len(direct_detail): direct_detail.to_excel(xw, sheet_name="直发_版本尺码明细", index=False)
    if len(allc): allc.to_excel(xw, sheet_name="现货_全部测算", index=False)
    if len(detail): detail.to_excel(xw, sheet_name="现货_版本尺码明细", index=False)
    for ws in xw.sheets.values():
        ws.freeze_panes = "A2"
        for col in ws.columns:
            w = max((len(str(c.value)) for c in col if c.value is not None), default=8)
            ws.column_dimensions[col[0].column_letter].width = min(max(w + 2, 10), 42)
        for row in ws.iter_rows(min_row=2):
            for c in row:
                if "利润率" in str(ws.cell(1, c.column).value or "") and isinstance(c.value, (int, float)):
                    c.number_format = "0%"
print(f"✓ 导出 {len(prof)}盈利 + {len(allc)}测算 + {len(detail)}个SKU明细 → {OUT}")
