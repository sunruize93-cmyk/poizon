"""选品评分算法 —— 系统的核心。

两步：
  1. compute_profit()  按成本参数算出每个候选品的净利润 / 利润率
  2. score_candidates() 把利润、销量、库存稳定性、竞争度等分项归一化后加权综合

设计原则
  - 所有"分项得分"统一转成"越大越好"再加权（负向指标取反），便于解释与调权。
  - 归一化用 min-max（跨当前候选集相对排名），样本太少时退化为绝对阈值，避免误导。
  - 硬过滤（利润/利润率下限、LV 必须可买）在打分前先淘汰，不让明显不赚钱的品挤占榜单。
"""
from __future__ import annotations

from typing import Iterable

from ..models import Candidate


# --------------------------------------------------------------------------- #
# 1. 利润计算
# --------------------------------------------------------------------------- #
def _logistics_cny(category: str, lg: dict) -> float:
    cat = (category or "").lower()
    key = "shoes" if "shoe" in cat or "鞋" in cat else (
        "wallet" if "wallet" in cat or "钱包" in cat else (
            "belt" if "belt" in cat or "皮带" in cat else "default"))
    rate = lg.get("rate_cny_per_kg", {}).get("shoes" if key == "shoes" else "default", 38)
    weight = lg.get("weight_kg", {}).get(key, lg.get("weight_kg", {}).get("default", 0.5))
    return rate * weight + lg.get("sf_express_cny", 50) + lg.get("packaging_cny", 20)


def _sell_net(price_cny: float, tech_rate: float, sell: dict) -> float:
    """得物到手价 = 售价×(1−技术费−转账费) − 操作费 − 邮补 [− 售后无忧]。"""
    net = price_cny * (1 - tech_rate - sell.get("transfer_fee_rate", 0))
    net -= sell.get("operation_fee_cny", 0)
    net -= sell.get("buyer_shipping_subsidy_cny", 0)
    if sell.get("include_worryfree"):
        net -= price_cny * sell.get("worryfree_fee_rate", 0)
    return net


def compute_profit(c: Candidate, cfg: dict, krw_per_cny: float | None = None) -> Candidate:
    """按实测成本表算 采购/物流/双场景利润。krw_per_cny 优先用实时汇率，否则用配置回退。"""
    cost = cfg["cost"]
    sell = cfg["sell"]
    fx = krw_per_cny or cfg["fx"].get("krw_per_cny", 224)

    # 采购成本(CNY)：含税价(KRW) × (10/11 − 券率 + 出口申报率) ÷ 汇率
    factor = (10 / 11) - cost.get("voucher_rate", 0) + cost.get("export_filing_rate", 0)
    purchase = c.lv.price_krw * factor / fx if c.lv.price_krw and fx else 0.0
    logistics = _logistics_cny(c.lv.category, cost.get("logistics", {}))
    total_cost = purchase + logistics

    price = c.dewu.market_price_cny
    # 普通挂单：卖市场最低价；立即变现：卖最高求购价(≈市场价×(1−折让))，技术费降至1%
    net_normal = _sell_net(price, sell.get("tech_fee_rate_normal", 0.05), sell)
    instant_price = price * (1 - sell.get("instant_bid_discount", 0.06))
    net_instant = _sell_net(instant_price, sell.get("tech_fee_rate_instant", 0.01), sell)

    c.purchase_cost_cny = round(purchase, 2)
    c.logistics_cny = round(logistics, 2)
    c.cost_cny = round(total_cost, 2)
    c.profit_normal_cny = round(net_normal - total_cost, 2)
    c.profit_instant_cny = round(net_instant - total_cost, 2)

    pref = sell.get("prefer_scenario", "best")
    if pref == "normal":
        chosen, scen, snet = c.profit_normal_cny, "normal", net_normal
    elif pref == "instant":
        chosen, scen, snet = c.profit_instant_cny, "instant", net_instant
    else:
        if c.profit_instant_cny > c.profit_normal_cny:
            chosen, scen, snet = c.profit_instant_cny, "instant", net_instant
        else:
            chosen, scen, snet = c.profit_normal_cny, "normal", net_normal
    c.sell_scenario = scen
    c.sell_net_cny = round(snet, 2)
    c.net_profit_cny = chosen
    c.margin_rate = round(chosen / total_cost, 4) if total_cost > 0 else 0.0
    return c


# --------------------------------------------------------------------------- #
# 2. 评分
# --------------------------------------------------------------------------- #
def _minmax(values: list[float]) -> "tuple[float, float]":
    lo, hi = min(values), max(values)
    return lo, hi


def _norm(x: float, lo: float, hi: float) -> float:
    """min-max 归一化到 0..1；区间退化时返回 0.5（中性）。"""
    if hi - lo < 1e-9:
        return 0.5
    return (x - lo) / (hi - lo)


def _sales_speed(c: Candidate) -> float:
    """销量速度代理指标：优先用近30天成交，缺失时用想要人数打折近似。"""
    if c.dewu.sales_30d > 0:
        return float(c.dewu.sales_30d)
    return c.dewu.wish_count * 0.3


def _stock_stability(c: Candidate) -> float:
    """LV 端库存稳定性。单次快照只能粗判；接入历史后改为 sellable 连续天数比例。"""
    if not c.lv.sellable:
        return 0.0
    return 0.6 if c.lv.is_backorder else 1.0


def apply_filters(candidates: Iterable[Candidate], cfg: dict) -> list[Candidate]:
    """硬过滤：不赚钱 / LV 买不到的直接标记淘汰。返回全部（含被淘汰的，便于审计）。"""
    f = cfg["scoring"]["filters"]
    out = []
    for c in candidates:
        reasons = []
        if f.get("require_lv_sellable", True) and not c.lv.sellable:
            reasons.append("LV不可买")
        if c.net_profit_cny < f.get("min_abs_profit_cny", 0):
            reasons.append(f"净利润<{f['min_abs_profit_cny']}")
        if c.margin_rate < f.get("min_margin_rate", 0):
            reasons.append(f"利润率<{f['min_margin_rate']}")
        c.passed_filter = not reasons
        c.reject_reason = "；".join(reasons)
        out.append(c)
    return out


def score_candidates(candidates: list[Candidate], cfg: dict) -> list[Candidate]:
    """对通过过滤的候选品打综合分，按分数降序返回（被淘汰的排在最后）。"""
    weights = cfg["scoring"]["weights"]
    passed = [c for c in candidates if c.passed_filter]
    if not passed:
        return sorted(candidates, key=lambda c: c.net_profit_cny, reverse=True)

    # 收集各分项原始值
    metrics = {
        "margin_rate":    [c.margin_rate for c in passed],
        "abs_profit":     [c.net_profit_cny for c in passed],
        "sales_speed":    [_sales_speed(c) for c in passed],
        "stock_stability":[_stock_stability(c) for c in passed],
        "competition":    [float(c.dewu.seller_count) for c in passed],
        "capital_tied":   [c.cost_cny for c in passed],
        "price_volatility":[c.dewu.price_volatility for c in passed],
    }
    ranges = {k: _minmax(v) for k, v in metrics.items()}
    # 负向指标：越大越差，归一化后取反
    negative = {"competition", "capital_tied", "price_volatility"}

    for i, c in enumerate(passed):
        sub = {}
        total = 0.0
        for k, w in weights.items():
            lo, hi = ranges[k]
            n = _norm(metrics[k][i], lo, hi)
            if k in negative:
                n = 1.0 - n
            sub[k] = round(n, 3)
            total += w * n
        c.subscores = sub
        c.score = round(total, 4)

    passed.sort(key=lambda c: c.score, reverse=True)
    rejected = sorted(
        (c for c in candidates if not c.passed_filter),
        key=lambda c: c.net_profit_cny, reverse=True,
    )
    return passed + rejected
