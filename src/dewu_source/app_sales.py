"""得物 App「最近购买」成交记录 → 逐(码数×包装)销量速度 + 真实成交价。

数据来源：tools/dewu_app_sales.py 截图 → 视觉读出 → data/dewu_sales/<货号>.json。
官方 API 给不到销量/想要/竞价，这里补上，是选品「近期好卖」判断的正解。

成交价为得物 APP 含税价（买家付）。卖家结算口径=含税/(1+跨境税率)，税率按结算价档位：
<5000→9.1%，≥5000→20%。利润模型用结算口径，故这里同时给出 settle_price。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from statistics import median

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SALES_DIR = os.path.join(ROOT, "data", "dewu_sales")

TAX_LOW, TAX_HIGH, TAX_THRESHOLD = 0.091, 0.20, 5000.0


def settle_from_taxed(taxed: float) -> float:
    """含税成交价 → 卖家结算价（不含税）。税档按结算价是否≥5000 自洽求解。"""
    s = taxed / (1 + TAX_LOW)
    if s >= TAX_THRESHOLD:
        s = taxed / (1 + TAX_HIGH)
    return round(s, 2)


@dataclass
class SpecVelocity:
    """单一 (码数, 包装) 规格的销量与成交价画像。"""
    size: str
    packaging: str
    n_total: int = 0
    n_30d: int = 0
    n_60d: int = 0
    n_90d: int = 0
    sold_per_month: float = 0.0      # 月化成交速度（按观测窗口推算）
    last_sale_days: float = 999.0    # 距最近一笔成交天数
    median_taxed_cny: float = 0.0    # 含税成交价中位数（APP口径）
    median_settle_cny: float = 0.0   # 结算价中位数（选品/利润口径）
    min_taxed_cny: float = 0.0
    max_taxed_cny: float = 0.0


@dataclass
class ProductSales:
    article_no: str
    title: str = ""
    wish_count: int = 0
    buyer_count: int = 0
    seller_bid_count: int = 0
    stock_left: int = 0
    release_price_cny: float = 0.0
    avg_deal_price_cny: float = 0.0
    n_30d_total: int = 0             # 全规格近 30 天成交（→ 喂 sales_30d）
    sold_per_month_total: float = 0.0
    specs: list[SpecVelocity] = field(default_factory=list)

    def spec(self, size: str, packaging: str) -> "SpecVelocity | None":
        for s in self.specs:
            if s.size == size and s.packaging == packaging:
                return s
        return None


def _velocity(records: list[dict]) -> tuple[int, int, int, float, float]:
    """(n30,n60,n90,月化速度,最近成交天数)。月化按观测最大窗口推算，避免短窗偏高。"""
    n30 = sum(1 for r in records if r["days_ago"] <= 30)
    n60 = sum(1 for r in records if r["days_ago"] <= 60)
    n90 = sum(1 for r in records if r["days_ago"] <= 90)
    if not records:
        return 0, 0, 0, 0.0, 999.0
    span = max(max(r["days_ago"] for r in records), 1.0)
    per_month = round(len(records) / span * 30, 2)
    last = min(r["days_ago"] for r in records)
    return n30, n60, n90, per_month, last


def aggregate(data: dict) -> ProductSales:
    recs = data.get("records", [])
    ps = ProductSales(
        article_no=data["article_no"], title=data.get("title", ""),
        wish_count=data.get("wish_count", 0), buyer_count=data.get("buyer_count", 0),
        seller_bid_count=data.get("seller_bid_count", 0), stock_left=data.get("stock_left", 0),
        release_price_cny=data.get("release_price_cny", 0.0),
        avg_deal_price_cny=data.get("avg_deal_price_cny", 0.0),
    )
    # 按 (size, packaging) 分组
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in recs:
        groups.setdefault((r.get("size", ""), r.get("packaging", "")), []).append(r)
    for (size, pkg), rs in sorted(groups.items()):
        prices = [r["price_cny"] for r in rs]
        n30, n60, n90, pm, last = _velocity(rs)
        ps.specs.append(SpecVelocity(
            size=size, packaging=pkg, n_total=len(rs),
            n_30d=n30, n_60d=n60, n_90d=n90, sold_per_month=pm, last_sale_days=last,
            median_taxed_cny=round(median(prices), 2),
            median_settle_cny=settle_from_taxed(median(prices)),
            min_taxed_cny=min(prices), max_taxed_cny=max(prices),
        ))
    ps.n_30d_total = sum(1 for r in recs if r["days_ago"] <= 30)
    _, _, _, pm_all, _ = _velocity(recs)
    ps.sold_per_month_total = pm_all
    # 速度高→低排序，便于看哪个规格最好卖
    ps.specs.sort(key=lambda s: (s.sold_per_month, -s.last_sale_days), reverse=True)
    return ps


def load(article_no: str) -> "ProductSales | None":
    path = os.path.join(SALES_DIR, f"{article_no.upper()}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return aggregate(json.load(f))


def load_all() -> dict[str, ProductSales]:
    out = {}
    if not os.path.isdir(SALES_DIR):
        return out
    for fn in os.listdir(SALES_DIR):
        if fn.endswith(".json"):
            with open(os.path.join(SALES_DIR, fn), encoding="utf-8") as f:
                ps = aggregate(json.load(f))
            out[ps.article_no.upper()] = ps
    return out


if __name__ == "__main__":
    import sys
    art = sys.argv[1] if len(sys.argv) > 1 else "M4583"
    ps = load(art)
    if not ps:
        print(f"无数据：data/dewu_sales/{art.upper()}.json")
        sys.exit(1)
    print(f"\n{ps.article_no}  {ps.title}")
    print(f"  想要 {ps.wish_count} · 累计买家 {ps.buyer_count} · 竞价商家 {ps.seller_bid_count} "
          f"· 仅剩 {ps.stock_left} · 发售价 ¥{ps.release_price_cny} · 成交均价 ¥{ps.avg_deal_price_cny}")
    print(f"  全规格：近30天成交 {ps.n_30d_total} 笔 · 月化 {ps.sold_per_month_total} 笔/月\n")
    print(f"  {'码数':<5}{'包装':<8}{'月化':>6}{'30d':>5}{'90d':>5}{'最近':>7}"
          f"{'成交中位(含税)':>14}{'结算价':>10}{'区间(含税)':>18}")
    for s in ps.specs:
        print(f"  {s.size:<6}{s.packaging:<9}{s.sold_per_month:>6}{s.n_30d:>5}{s.n_90d:>5}"
              f"{s.last_sale_days:>6}d  ¥{s.median_taxed_cny:>11}  ¥{s.median_settle_cny:>8}"
              f"   ¥{s.min_taxed_cny:.0f}–{s.max_taxed_cny:.0f}")
