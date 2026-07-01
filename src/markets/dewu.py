"""得物需求侧适配器。

- cheap_signal(): 官方 API by-article-number 查是否在售 + 想要人数/市场价（中成本，需 .env 凭证）。
  没凭证/失败时降级为 on_market=None（不误杀，交给 verify 用已抓数据判断）。
- verify():      读 data/dewu_sales/<货号>.json（屏幕 OCR 抓的真实成交），结合 L2 的 LV 供给价，
  按成本模型算每(码数×包装)净利/利润率 + 热度综合分 → Opportunity。缺成交数据的标记待抓取。
换平台照此写新 MarketAdapter。
"""
from __future__ import annotations

import os

from ..engine.base import Signaled, Opportunity, Priced
from ..models import LVProduct, DewuProduct, Candidate
from ..scorer.score import compute_profit
from ..scorer.heat import score_specs
from ..dewu_source import app_sales


class DewuMarket:
    name = "得物"

    def __init__(self, cfg: dict, krw_per_cny: float):
        self.cfg = cfg
        self.fx = krw_per_cny

    # ---- L3 廉价信号 ----
    def cheap_signal(self, items: list[Priced]) -> list[Signaled]:
        client = None
        try:
            from ..dewu_source.official_api import DewuOfficialClient
            if os.getenv("DEWU_APP_KEY") and os.getenv("DEWU_APP_SECRET"):
                client = DewuOfficialClient()
        except Exception:
            client = None

        out = []
        for it in items:
            s = Signaled(**{k: getattr(it, k) for k in
                            ("article_no", "name", "category", "source_id", "url", "raw",
                             "potential", "potential_reason", "keep", "supply_price",
                             "sellable", "price_currency")})
            if client:
                try:
                    dp = client.fetch_product(it.article_no)
                    s.on_market = bool(dp.spu_id and not dp.error)
                    s.demand_wish = dp.wish_count
                    s.demand_sold = dp.sales_30d
                    s.market_ref = dp.spu_id
                except Exception:
                    s.on_market = None  # 未知
            else:
                # 无凭证：用是否已有屏幕抓取数据兜底判断在售
                s.on_market = app_sales.load(it.article_no) is not None or None
            out.append(s)
        return out

    # ---- L4 成交核验 + 算利润/综合分 ----
    def verify(self, items: list[Signaled]) -> list[Signaled]:
        results, to_scrape = [], []
        for it in items:
            ps = app_sales.load(it.article_no)
            if ps is None or not ps.specs:
                to_scrape.append(it.article_no)
                continue
            rows = []
            for sp in ps.specs:
                cand = Candidate(
                    article_no=it.article_no,
                    lv=LVProduct(article_no=it.article_no, category=it.category,
                                 price_krw=it.supply_price, sellable=it.sellable),
                    dewu=DewuProduct(article_no=it.article_no,
                                     market_price_cny=sp.median_settle_cny,
                                     wish_count=it.demand_wish, seller_count=0),
                )
                compute_profit(cand, self.cfg, self.fx)
                rows.append({
                    "spec": f"{sp.size}/{sp.packaging}", "net_profit": cand.net_profit_cny,
                    "margin": cand.margin_rate, "velocity": sp.sold_per_month,
                    "last_sale_days": sp.last_sale_days, "n90": sp.n_90d,
                    "wish": it.demand_wish, "buyers": 0, "competition": 0,
                    "dmin": sp.median_settle_cny, "dmax": sp.median_settle_cny,
                    "dmid": sp.median_settle_cny,
                })
            scored = score_specs(rows, self.cfg)
            best = max((r for r in scored if r.get("passed")), key=lambda r: r["score"], default=None)
            op = Opportunity(**{k: getattr(it, k) for k in
                                ("article_no", "name", "category", "source_id", "url", "raw",
                                 "potential", "potential_reason", "keep", "supply_price",
                                 "sellable", "price_currency", "on_market", "demand_wish",
                                 "demand_sold", "market_ref")})
            if best:
                op.market_price = best["dmid"]
                op.velocity = best["velocity"]
                op.net_profit = best["net_profit"]
                op.margin = best["margin"]
                op.score = best["score"]
                op.detail = {"best_spec": best["spec"], "specs_scored": len(scored)}
            results.append(op)
        if to_scrape:
            print(f"  [得物] {len(to_scrape)} 品缺成交数据,待屏幕抓取: {', '.join(to_scrape[:10])}"
                  + ("..." if len(to_scrape) > 10 else ""))
        results.sort(key=lambda o: o.score, reverse=True)
        return results
