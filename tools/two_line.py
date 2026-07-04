#!/usr/bin/env python3
"""两条业务线对比:现货(得物国内)vs 直发出价(Direct)。给定货号,拉两条线卖价基准+算净利。
用法: python tools/two_line.py 1AAREW 1AK8BN ...
现货卖价=得物最低价(bt=20);直发卖价=得物直发最低价(bt=27)+定价策略。
⚠️直发费率/物流用 settings 里的占位默认,待核实后才准。LV买入价读 data/lv_prices.json 缓存。
"""
import sys, os, json, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
import yaml
from src.dewu_source.official_api import DewuOfficialClient, _market_price
from src.fx import krw_per_cny
from src.models import LVProduct, DewuProduct, Candidate
from src.scorer.score import compute_profit, direct_net

cfg = yaml.safe_load(open("config/settings.example.yaml", encoding="utf-8"))
if os.path.exists("config/settings.yaml"):
    cfg = yaml.safe_load(open("config/settings.yaml", encoding="utf-8"))
fx = krw_per_cny(cfg)
prices = json.load(open("data/lv_prices.json")).get("results", {}) if os.path.exists("data/lv_prices.json") else {}
c = DewuOfficialClient()
d = cfg.get("direct", {})

arts = sys.argv[1:] or ["1AAREW"]
print(f"两条线对比 (1CNY={fx:.0f}KRW; 直发:14%费封顶₩15k~45k,月付物流不计)\n")
for art in arts:
    lv_krw = float((prices.get(art) or {}).get("priceRaw") or 0)
    try:
        info = c.query_by_article_number(art, region="KR")
        items = info.get("data") or []
        if not items:
            print(f"[{art}] 得物KR未找到"); continue
        skus = [s for s in (items[0].get("skuInfoList") or []) if s.get("buyStatus") == 1]
        # 现货 bt=20(CNY,得物国内);直发 bt=27(KRW,POIZON直发)
        spot_cny = direct_krw = 0.0
        for s in skus:
            sid = s.get("skuId") or s.get("dwSkuId")
            p20 = _market_price(c.get_lowest_price(sid, region="KR", currency="CNY", bidding_type=20).get("data") or {}, "CNY")
            p27 = _market_price(c.get_lowest_price(sid, region="KR", currency="KRW", bidding_type=27).get("data") or {}, "KRW")
            if p20 and (spot_cny == 0 or p20 < spot_cny): spot_cny = p20
            if p27 and (direct_krw == 0 or p27 < direct_krw): direct_krw = p27
        # 现货线(得物CNY)
        spot_net = spot_mg = 0.0
        if spot_cny and lv_krw:
            cand = Candidate(article_no=art, lv=LVProduct(article_no=art, category="shoes", price_krw=lv_krw, sellable=True),
                             dewu=DewuProduct(article_no=art, market_price_cny=spot_cny))
            compute_profit(cand, cfg, fx); spot_net, spot_mg = cand.net_profit_cny, cand.margin_rate
        # 直发线(POIZON KRW,14%封顶费,月付物流不计)
        dn = direct_net(lv_krw, direct_krw, cfg) if (direct_krw and lv_krw) else {"net": 0, "margin": 0, "fee": 0}
        print(f"[{art}] LV买入 ₩{int(lv_krw)}")
        print(f"  现货线(得物国内): 最低¥{spot_cny:.0f} → 净利¥{spot_net:.0f} ({spot_mg:.0%})")
        print(f"  直发线(POIZON):   直发最低₩{int(direct_krw)} 技术费₩{dn.get('fee',0)} → 净利₩{dn['net']} ({dn['margin']:.0%})")
    except Exception as e:
        print(f"[{art}] 出错: {e}")
