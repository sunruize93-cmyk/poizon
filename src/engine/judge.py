"""Layer1 潜力初判：混合 = 规则打底 + LLM(Claude) 精排。

规则层（零成本、可解释）：品类是否主营、供给价是否在利润带、是否命中热门/冷门系列关键词
→ 给每个候选一个 0~1 的 potential 分，并砍掉明显没戏的。
LLM 层（便宜、聪明）：把规则存活的候选（只有名字/系列，无需抓价）交给 Claude 批量打分，
按「韩中价差潜力 + 系列热度 + 经典 vs 冷门」精排。二者相乘/加权得最终 potential。

LLM 打分是可插拔的：给 HybridJudge 传一个 llm_scorer 回调即可；不传就退化为纯规则。
交互式用法：export_for_llm() 导出紧凑清单 → 我(Claude)读并给分 → apply_llm_scores() 回填。
"""
from __future__ import annotations

import re
from typing import Callable, Optional

from .base import RawItem, BrandProfile


def _hits(text: str, patterns: list[str]) -> list[str]:
    t = text.lower()
    return [p for p in patterns if re.search(p.lower(), t)]


class HybridJudge:
    """规则 + 可选 LLM 的潜力判官。"""

    def __init__(self, llm_scorer: Optional[Callable[[list[RawItem], BrandProfile], dict]] = None,
                 llm_weight: float = 0.6):
        # llm_scorer(items, profile) -> {article_no: {"score": 0~1, "reason": str}}
        self.llm_scorer = llm_scorer
        self.llm_weight = llm_weight   # 最终 = (1-w)*规则 + w*LLM

    # ---- 规则层 ----
    def _rule_score(self, it: RawItem, profile: BrandProfile) -> tuple[float, str]:
        reasons = []
        # 1) 品类闸门：非主营直接判负（保留但压到很低，便于审计）
        if profile.target_categories and it.category not in profile.target_categories:
            return 0.05, f"非主营品类({it.category})"
        score = 0.5  # 主营品类基准
        # 2) 热门/经典系列关键词
        hot = _hits(it.name, profile.hot_lines)
        if hot:
            score += 0.25
            reasons.append("热门系列:" + ",".join(hot[:3]))
        # 3) 冷门/难变现信号
        cold = _hits(it.name, profile.cold_signals)
        if cold:
            score -= 0.3
            reasons.append("冷门信号:" + ",".join(cold[:3]))
        # 4) 供给价带（若已抓价；发现阶段通常未知，跳过）
        band = profile.price_band.get(it.category)
        sp = getattr(it, "supply_price", 0) or 0
        if band and sp:
            lo, hi = band
            if lo <= sp <= hi:
                score += 0.15; reasons.append("价带内")
            else:
                score -= 0.2; reasons.append(f"价带外({int(sp)})")
        return max(0.0, min(1.0, score)), "；".join(reasons) or "主营品类"

    # ---- 编排 ----
    def judge(self, items: list[RawItem], profile: BrandProfile,
              keep_threshold: float = 0.5) -> list[RawItem]:
        for it in items:
            it.potential, it.potential_reason = self._rule_score(it, profile)

        # 规则存活者才送 LLM（省算力）
        survivors = [it for it in items if it.potential >= 0.3]
        if self.llm_scorer and survivors:
            scores = self.llm_scorer(survivors, profile) or {}
            for it in survivors:
                s = scores.get(it.article_no)
                if s:
                    llm = float(s.get("score", it.potential))
                    it.potential = round((1 - self.llm_weight) * it.potential + self.llm_weight * llm, 3)
                    if s.get("reason"):
                        it.potential_reason += f" | LLM:{s['reason']}"

        for it in items:
            it.keep = it.potential >= keep_threshold
        items.sort(key=lambda x: x.potential, reverse=True)
        return items

    # ---- 交互式 LLM 打分辅助 ----
    @staticmethod
    def export_for_llm(items: list[RawItem]) -> list[dict]:
        """导出给 Claude 批量打分的紧凑清单（只名字/品类，无需抓价）。"""
        return [{"article_no": it.article_no, "category": it.category, "name": it.name} for it in items]

    @staticmethod
    def apply_llm_scores(items: list[RawItem], scores: dict, llm_weight: float = 0.6) -> list[RawItem]:
        for it in items:
            s = scores.get(it.article_no)
            if s:
                llm = float(s.get("score", it.potential))
                it.potential = round((1 - llm_weight) * it.potential + llm_weight * llm, 3)
                if s.get("reason"):
                    it.potential_reason += f" | LLM:{s['reason']}"
        items.sort(key=lambda x: x.potential, reverse=True)
        return items
