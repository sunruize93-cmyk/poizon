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
print(f"两条线对比 (1CNY={fx:.0f}KRW; 直发费率为占位默认待核实)\n")
for art in arts:
    lv_krw = float((prices.get(art) or {}).get("priceRaw") or 0)
    try:
        info = c.query_by_article_number(art, region="KR")
        items = info.get("data") or []
        if not items:
            print(f"[{art}] 得物KR未找到"); continue
        skus = [s for s in (items[0].get("skuInfoList") or []) if s.get("buyStatus") == 1]
        # 取整体最低:现货 bt=20 / 直发 bt=27
        spot = direct = 0.0
        for s in skus:
            sid = s.get("skuId") or s.get("dwSkuId")
            p20 = _market_price(c.get_lowest_price(sid, region="KR", currency="CNY", bidding_type=20).get("data") or {}, "CNY")
            p27 = _market_price(c.get_lowest_price(sid, region="KR", currency="CNY", bidding_type=27).get("data") or {}, "CNY")
            if p20 and (spot == 0 or p20 < spot): spot = p20
            if p27 and (direct == 0 or p27 < direct): direct = p27
        # 现货线:卖价=现货最低价,走现货成本模型
        spot_net = spot_mg = 0.0
        if spot and lv_krw:
            cand = Candidate(article_no=art, lv=LVProduct(article_no=art, category="shoes", price_krw=lv_krw, sellable=True),
                             dewu=DewuProduct(article_no=art, market_price_cny=spot))
            compute_profit(cand, cfg, fx); spot_net, spot_mg = cand.net_profit_cny, cand.margin_rate
        # 直发线:目标卖价=直发最低价+欧洲加价(抢速度);走直发成本模型
        target = (direct + d.get("europe_markup_cny", 0)) if direct else 0
        dn = direct_net(lv_krw, target, cfg, fx) if (target and lv_krw) else {"net": 0, "margin": 0}
        print(f"[{art}] LV买入 ₩{int(lv_krw)}")
        print(f"  现货线: 得物最低¥{spot:.0f} → 净利¥{spot_net:.0f} ({spot_mg:.0%})")
        print(f"  直发线: 直发最低¥{direct:.0f} +加价{d.get('europe_markup_cny',0)}=目标¥{target:.0f} → 净利¥{dn['net']:.0f} ({dn['margin']:.0%})")
    except Exception as e:
        print(f"[{art}] 出错: {e}")
