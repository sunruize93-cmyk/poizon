"""逐(码数×包装)「近期好卖 × 利润」综合评分模型。

为何这样设计（业务逻辑）
  跨境倒卖小皮具，资金有限、压货=死钱，所以「能不能快速卖出」与「赚多少」同等重要，
  再用「竞争/价格波动」做风险扣分。三大维度：
    流动性/热度 0.45  能否快速卖出（速度/新鲜度/想要/累计买家）——本场景第一优先
    盈利性     0.40  绝对净利 + 利润率（资金效率）
    风险       0.15  竞价商家数、成交价波动（负向）
  先硬过滤：不赚钱(净利/利润率低于下限) 或 滞销(90天0成交) 直接淘汰，不让其挤占榜单；
  再对幸存者 min-max 归一化后加权综合。归一化使分数是「相对当前候选集」的排名，样本太少
  时区间退化为中性 0.5（如单一商品时商品级指标 wish/buyers/竞价相同——多商品批量后自然区分）。

输入 rows：每个 dict 至少含
  net_profit / margin / velocity(月化) / last_sale_days / n90 /
  wish / buyers / competition / dmin / dmax / dmid（成交价区间与中位，算波动）
输出：就地写入 score(0~1) / passed(bool) / reject(str) / sub(各分项归一化值)，并按 score 降序返回。
"""
from __future__ import annotations


def _norm(x: float, lo: float, hi: float) -> float:
    if hi - lo < 1e-9:
        return 0.5
    return (x - lo) / (hi - lo)


def _recency(last_days: float, full: float, zero: float) -> float:
    """距今天数 → 0~1。≤full 满分，≥zero 0 分，中间线性。"""
    if last_days <= full:
        return 1.0
    if last_days >= zero:
        return 0.0
    return 1.0 - (last_days - full) / (zero - full)


def score_specs(rows: list[dict], cfg: dict) -> list[dict]:
    h = cfg["scoring"]["heat"]
    w = h["weights"]
    f = h["filters"]
    full, zero = h.get("recency_full_days", 1), h.get("recency_zero_days", 60)

    # 1) 硬过滤
    for r in rows:
        reasons = []
        if r["net_profit"] < f.get("min_abs_profit_cny", 0):
            reasons.append(f"净利<{f['min_abs_profit_cny']}")
        if r["margin"] < f.get("min_margin_rate", 0):
            reasons.append(f"利润率<{f['min_margin_rate']:.0%}")
        if r.get("n90", 0) < f.get("min_sales_90d", 1):
            reasons.append("90天滞销")
        r["passed"] = not reasons
        r["reject"] = "；".join(reasons)

    passed = [r for r in rows if r["passed"]]
    if not passed:
        for r in rows:
            r["score"], r["sub"] = 0.0, {}
        rows.sort(key=lambda r: r["net_profit"], reverse=True)
        return rows

    # 2) 派生指标 + 归一化区间
    for r in passed:
        r["_recency"] = _recency(r["last_sale_days"], full, zero)
        mid = r.get("dmid") or 1
        r["_vol"] = (r.get("dmax", mid) - r.get("dmin", mid)) / mid if mid else 0.0

    cols = {
        "velocity":    [r["velocity"] for r in passed],
        "recency":     [r["_recency"] for r in passed],
        "wish":        [r["wish"] for r in passed],
        "buyers":      [r["buyers"] for r in passed],
        "profit_abs":  [r["net_profit"] for r in passed],
        "margin":      [r["margin"] for r in passed],
        "competition": [r["competition"] for r in passed],
        "volatility":  [r["_vol"] for r in passed],
    }
    rng = {k: (min(v), max(v)) for k, v in cols.items()}
    negative = {"competition", "volatility"}  # 越大越差，归一化后取反

    # 3) 加权综合
    keys = {
        "velocity": "velocity", "recency": "_recency", "wish": "wish", "buyers": "buyers",
        "profit_abs": "net_profit", "margin": "margin",
        "competition": "competition", "volatility": "_vol",
    }
    for r in passed:
        sub, total = {}, 0.0
        for mk, weight in w.items():
            lo, hi = rng[mk]
            n = _norm(r[keys[mk]], lo, hi)
            if mk in negative:
                n = 1.0 - n
            sub[mk] = round(n, 3)
            total += weight * n
        r["sub"] = sub
        r["score"] = round(total, 4)

    rejected = [r for r in rows if not r["passed"]]
    for r in rejected:
        r["score"], r["sub"] = 0.0, {}
    passed.sort(key=lambda r: r["score"], reverse=True)
    rejected.sort(key=lambda r: r["net_profit"], reverse=True)
    return passed + rejected
