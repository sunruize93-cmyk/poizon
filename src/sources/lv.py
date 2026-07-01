"""LV 供给侧适配器：发现(sitemap 目录) + 报价(prodct-dtl 浏览器批量)。

- discover(): 读 data/lv_catalog.json（tools/lv_catalog.py 从 sitemap 生成，零 Akamai）。
- price():    调 node tools/lv_prices.mjs 批量抓价（暖机浏览器 + client 凭证），读回 data/lv_prices.json。
换品牌时照此模式写 GucciSource 等。
"""
from __future__ import annotations

import json
import os
import subprocess

from ..engine.base import RawItem, Priced, BrandProfile

CATALOG = "data/lv_catalog.json"
PRICES = "data/lv_prices.json"


class LVSource:
    name = "LV"

    def __init__(self, live: bool = True):
        self.live = live   # False = 只读 data/lv_prices.json 缓存，不起浏览器

    def discover(self, profile: BrandProfile) -> list[RawItem]:
        if not os.path.exists(CATALOG):
            raise FileNotFoundError(f"{CATALOG} 不存在，先跑 python tools/lv_catalog.py")
        data = json.load(open(CATALOG))
        items = []
        for it in data["items"]:
            items.append(RawItem(
                article_no=it["article_no"], name=it["slug"].replace("-", " "),
                category=it["category"], source_id=it.get("nvprod", ""), url=it.get("url", ""),
                raw=it,
            ))
        return items

    def price(self, items: list[RawItem], run: bool | None = None) -> list[Priced]:
        """抓供给价。run=True 时实跑浏览器；否则只读已有 data/lv_prices.json 缓存。"""
        if run is None:
            run = self.live
        arts = [it.article_no for it in items]
        if run and arts:
            # 每次全新 profile 名，避开 Akamai 的 profile 级封禁
            env = {**os.environ, "LV_PROFILE": f"tools/.lv_profile_eng"}
            subprocess.run(["node", "tools/lv_prices.mjs", *arts], env=env, timeout=600)
        cache = json.load(open(PRICES)).get("results", {}) if os.path.exists(PRICES) else {}
        out = []
        for it in items:
            r = cache.get(it.article_no, {})
            out.append(Priced(
                **{k: getattr(it, k) for k in ("article_no", "name", "category", "source_id", "url", "raw",
                                               "potential", "potential_reason", "keep")},
                supply_price=float(r.get("priceRaw") or 0),
                sellable=bool(r.get("sellable")),
            ))
        return out
