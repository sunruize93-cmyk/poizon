"""读 config/skus.csv（含 lv_price_krw），逐码数算净利并导出 Excel 榜单。"""
import os, sys, csv, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import yaml
from dotenv import load_dotenv; load_dotenv(os.path.join(os.path.dirname(__file__),"..",".env"))
from src.dewu_source.official_api import DewuOfficialClient, _market_price, _vol
from src.scorer.score import compute_profit
from src.fx import krw_per_cny
from src.models import Candidate, LVProduct, DewuProduct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cfg = yaml.safe_load(open(os.path.join(ROOT,"config","settings.example.yaml"),encoding="utf-8"))
fx = krw_per_cny(cfg)
c = DewuOfficialClient()
rows = list(csv.DictReader(open(os.path.join(ROOT,"config","skus.csv"),encoding="utf-8-sig")))

def split_pv(sku):
    size=pkg=color=""
    for pv in (sku.get("regionSalePvInfoList") or []):
        v=(pv.get("value") or "").strip(); n=(pv.get("name") or "").lower()
        if not v: continue
        if any(k in v for k in ["Box","Bag","Dust","Shopping","Pouch"]) or "pack" in n or "포장" in n: pkg=v
        elif v.replace(".","").isdigit() or "size" in n or "사이즈" in n or "eu" in v.lower(): size=v
        else: color=color or v
    return size, pkg, color

out=[]
for r in rows:
    art=r["article_no"].upper(); lv=(r.get("lv_price_krw") or "").strip()
    if not lv: print(f"  {art:<8} 跳过(无LV价)"); continue
    lv_krw=float(lv); cat=r.get("category","")
    info=c.query_by_article_number(art, region="KR"); items=info.get("data") or []
    if not items: print(f"  {art:<8} ❌ 得物未找到"); continue
    spu=items[0].get("spuInfo") or {}; skus=items[0].get("skuInfoList") or []
    title=spu.get("title","")[:34]; print(f"  {art:<8} ✓ {title} ({len(skus)}码)")
    for s in skus:
        if s.get("buyStatus")!=1: continue
        sid=s.get("skuId") or s.get("dwSkuId")
        pdata=(c.get_lowest_price(sid,region="KR",currency="CNY").get("data") or {})
        price=_market_price(pdata,"CNY")
        if price<=0: continue
        cand=Candidate(article_no=art,
            lv=LVProduct(article_no=art,category=cat,price_krw=lv_krw,sellable=True),
            dewu=DewuProduct(article_no=art,market_price_cny=price,price_volatility=_vol(pdata)))
        compute_profit(cand,cfg,fx)
        size,pkg,color=split_pv(s)
        tax=1.091 if price<5000 else 1.20
        out.append(dict(art=art,title=title,size=size,pkg=pkg,color=color,
            price=price,taxed=round(price*tax), cost=cand.cost_cny,
            pn=cand.profit_normal_cny, pi=cand.profit_instant_cny,
            profit=cand.net_profit_cny, margin=cand.margin_rate, scen=cand.sell_scenario))

out.sort(key=lambda x:x["profit"], reverse=True)
# 导出 Excel
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
wb=Workbook(); ws=wb.active; ws.title="选品榜单"
cols=[("art","货号"),("title","品名"),("size","码数"),("pkg","包装"),("color","颜色"),
 ("price","得物价(不含税)"),("taxed","含税(买家)"),("cost","总成本"),
 ("pn","普通利"),("pi","立即变现利"),("profit","净利"),("margin","利润率"),("scen","场景")]
ws.append([t for _,t in cols])
for cell in ws[1]: cell.font=Font(bold=True,color="FFFFFF"); cell.fill=PatternFill("solid",fgColor="00B386")
for x in out:
    x=dict(x); x["margin"]=f'{x["margin"]*100:.0f}%'; x["scen"]="立即变现" if x["scen"]=="instant" else "普通"
    ws.append([x[k] for k,_ in cols])
    if x["profit"]>=300:
        for cell in ws[ws.max_row]: cell.fill=PatternFill("solid",fgColor="E8F8F2")
for col in ws.columns:
    w=max((len(str(c.value)) for c in col if c.value),default=8); ws.column_dimensions[col[0].column_letter].width=min(w+2,30)
os.makedirs(os.path.join(ROOT,"report"),exist_ok=True)
path=os.path.join(ROOT,"report","选品榜单_逐码数.xlsx"); wb.save(path)
print(f"\n✓ 导出 {len(out)} 个码数 → {path}")
print(f"\nTOP 12（汇率 1CNY={fx:.1f}KRW）:")
print(f"{'货号':<8}{'码数':<7}{'包装':<22}{'不含税':>7}{'净利':>7}{'利润率':>7}")
for x in out[:12]:
    print(f"{x['art']:<8}{x['size'][:6]:<7}{x['pkg'][:20]:<22}¥{x['price']:>5.0f}¥{x['profit']:>5.0f}{x['margin']*100:>5.0f}%")
