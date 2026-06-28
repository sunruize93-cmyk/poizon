"""LV ↔ 得物 关联：以 LV 官方货号为键，把两侧数据拼成候选品。"""
from __future__ import annotations

from ..models import Candidate, DewuProduct, LVProduct


def build_candidates(
    lv_list: list[LVProduct],
    dewu_list: list[DewuProduct],
) -> list[Candidate]:
    """按 article_no 关联。两侧都有才成为候选品；只有一侧的记入 unmatched 由调用方决定如何处理。"""
    dewu_by_no = {d.article_no: d for d in dewu_list}
    candidates = []
    for lv in lv_list:
        dewu = dewu_by_no.get(lv.article_no)
        if dewu is None:
            continue
        candidates.append(Candidate(article_no=lv.article_no, lv=lv, dewu=dewu))
    return candidates


def diagnose(lv_list: list[LVProduct], dewu_list: list[DewuProduct]) -> dict:
    """关联诊断，便于排查为什么某些货号没进榜。"""
    lv_nos = {x.article_no for x in lv_list}
    dewu_nos = {x.article_no for x in dewu_list}
    return {
        "lv_total": len(lv_list),
        "dewu_total": len(dewu_list),
        "matched": sorted(lv_nos & dewu_nos),
        "only_lv": sorted(lv_nos - dewu_nos),
        "only_dewu": sorted(dewu_nos - lv_nos),
        "lv_fetch_errors": [x.article_no for x in lv_list if x.error],
        "dewu_fetch_errors": [x.article_no for x in dewu_list if x.error],
    }
