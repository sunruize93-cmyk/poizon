"""漏斗编排：Discover → Triage → Price → (Signal → Verify)。

每层用 profile.layer_caps 限制进入下一层的数量，把昂贵操作压在少数高潜力候选上。
Layer0-2（发现/初判/报价）可全自动；Layer3-4（得物信号/成交核验）由 MarketAdapter 提供，
得物侧含屏幕 OCR，通常半自动，故 verify 只对入围 shortlist 跑。
"""
from __future__ import annotations

from .base import SourceAdapter, MarketAdapter, PotentialJudge, BrandProfile, RawItem


def run(profile: BrandProfile, source: SourceAdapter, judge: PotentialJudge,
        market: "MarketAdapter | None" = None, do_price: bool = True,
        llm_scores: "dict | None" = None, verbose: bool = True):
    log = print if verbose else (lambda *a, **k: None)

    # Layer0 发现
    raw = source.discover(profile)
    log(f"[L0 发现] {source.name} 目录 {len(raw)} 品")

    # Layer1 潜力初判（规则 + 可选 LLM 精排回填）
    judged = judge.judge(raw, profile)
    if llm_scores:
        from .judge import HybridJudge
        HybridJudge.apply_llm_scores(judged, llm_scores)
        for it in judged:
            it.keep = it.potential >= 0.5
        log(f"[L1 LLM] 回填精排分 {len(llm_scores)} 项")
    kept = [it for it in judged if it.keep]
    log(f"[L1 初判] 潜力≥阈值 {len(kept)} / {len(judged)}  （砍掉 {len(judged) - len(kept)}）")
    cap = profile.layer_caps.get("price", 200)
    to_price = kept[:cap]
    log(f"[L1→L2] 取潜力 Top{len(to_price)} 进报价（cap={cap}）")

    # Layer2 供给报价
    if not do_price:
        return {"raw": raw, "kept": kept, "to_price": to_price, "priced": [], "opportunities": []}
    priced = source.price(to_price)
    ok = [p for p in priced if p.supply_price > 0]
    # 报价后再用价带精修潜力（可选）+ 过滤可售
    band = profile.price_band
    in_band = [p for p in ok if not band.get(p.category) or band[p.category][0] <= p.supply_price <= band[p.category][1]]
    log(f"[L2 报价] 成功 {len(ok)}/{len(priced)}  在利润带内且可售 {sum(1 for p in in_band if p.sellable)}")

    result = {"raw": raw, "kept": kept, "priced": priced, "in_band": in_band, "opportunities": []}
    if market is None:
        return result

    # Layer3 需求侧廉价信号
    cap_s = profile.layer_caps.get("signal", 80)
    signaled = market.cheap_signal(in_band[:cap_s])
    has_demand = [s for s in signaled if s.on_market]
    log(f"[L3 需求信号] {market.name} 命中 {len(has_demand)}/{len(signaled)}")

    # Layer4 成交核验（贵，只跑入围）
    cap_v = profile.layer_caps.get("verify", 25)
    verified = market.verify(has_demand[:cap_v])
    log(f"[L4 核验] 核验 {len(verified)} 品 → 交给 scorer 排机会榜")
    result["opportunities"] = verified
    return result
