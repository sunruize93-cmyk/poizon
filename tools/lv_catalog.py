#!/usr/bin/env python3
"""Layer 0-1：从 LV sitemap 发现全量商品 + 按 slug 归类初筛(零抓取成本)。
sitemap-product.xml 无 Akamai 墙,curl_cffi 直取。产出 data/lv_catalog.json。
用法: python tools/lv_catalog.py
"""
import json
import re
import os
from curl_cffi import requests as r

SITEMAP = "https://kr.louisvuitton.com/content/louisvuitton/sitemap/kor_KR/sitemap-product.xml"

# slug 关键词 → 品类。顺序即优先级(先命中先归)。
CATEGORY_RULES = [
    ("shoes",   r"sneaker|trainer|tilted|sandal|loafer|derby|mule|pump|ballerina|boot|moccasin|espadrille|slipper|runner|skate|oxford|richelieu"),
    ("slg",     r"wallet|card-holder|cardholder|coin|key-|key-pouch|pouch|zippy|brazza|sarah|victorine|multiple|pocket-organizer"),
    ("belt",    r"belt|reversible|ceinture|initiales|lv-?shape"),
    ("bag",     r"bag|backpack|tote|duffle|keepall|speedy|neverfull|pochette|messenger|alma|onthego|noe|petite-malle|danube|nano|bumbag"),
    ("acc",     r"ring|bracelet|necklace|earring|pendant|brooch|scarf|bandeau|stole|sunglass|hat|cap|beanie|glove|tie|charm|keychain"),
    ("apparel", r"shirt|jacket|pants|trouser|dress|knit|cardigan|coat|hoodie|sweat|jean|denim|skirt|blazer|polo|tee|t-shirt|short|vest|parka"),
    ("fragrance", r"perfume|fragrance|cologne|eau-de|candle|scent"),
    ("other",   r"guide|book|toy|home|plate|cup|tray|game|puzzle|deco|frame|blanket|towel"),
]
# 用户当前主营(可迁移: 换品牌改这里/走 config)
TARGET = {"shoes", "slg", "belt"}


def categorize(slug: str) -> str:
    s = slug.lower()
    for cat, pat in CATEGORY_RULES:
        if re.search(pat, s):
            return cat
    return "unknown"


def parse_url(url: str):
    # /kor-kr/products/{slug}-{nvprodId}/{货号}
    m = re.search(r"/products/(.+?)-(nvprod\w+)/([A-Z0-9]{5,7})$", url)
    if not m:
        return None
    slug, nvprod, art = m.group(1), m.group(2), m.group(3)
    return {"article_no": art, "nvprod": nvprod, "slug": slug,
            "category": categorize(slug), "url": url}


def main():
    print("→ 拉取 sitemap...")
    resp = r.get(SITEMAP, impersonate="chrome131", timeout=30)
    locs = re.findall(r"<loc>([^<]+)</loc>", resp.text)
    items = [x for x in (parse_url(u) for u in locs) if x]
    print(f"  商品 URL: {len(locs)} → 解析出货号: {len(items)}")

    from collections import Counter
    by_cat = Counter(i["category"] for i in items)
    print("\n全量品类分布:")
    for cat, n in by_cat.most_common():
        print(f"  {cat:10} {n}")

    target = [i for i in items if i["category"] in TARGET]
    print(f"\n★ 目标品类({'/'.join(sorted(TARGET))})候选: {len(target)}  ← 6647 一步砍到这么多,再进 Layer2 报价")
    tc = Counter(i["category"] for i in target)
    print("  ", dict(tc))
    print("  样本:")
    for i in target[:8]:
        print(f"    {i['article_no']:8} {i['category']:6} {i['slug'][:48]}")

    os.makedirs("data", exist_ok=True)
    with open("data/lv_catalog.json", "w") as f:
        json.dump({"count": len(items), "target_count": len(target), "items": items}, f, ensure_ascii=False, indent=1)
    print("\n✓ 全量目录写入 data/lv_catalog.json")


if __name__ == "__main__":
    main()
