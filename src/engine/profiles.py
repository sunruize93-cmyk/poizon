"""品牌配置。换品牌/场景 = 加一个 BrandProfile（或从 config 载入）。"""
from __future__ import annotations

from .base import BrandProfile

# LV × 韩国直邮→得物 场景。域知识来自卖家实战：主营鞋/小皮具/腰带，
# 热门系列走量快，冷门/异皮/高珠宝难变现且压资金。价带为韩国零售价(KRW)粗界。
LV = BrandProfile(
    brand="LV",
    target_categories={"shoes", "slg", "belt"},
    price_band={
        "shoes": (1_200_000, 2_800_000),
        "slg":   (400_000, 1_700_000),
        "belt":  (600_000, 1_300_000),
    },
    hot_lines=[
        # 鞋
        "trainer", "tilted", "tactic", "run away", "archlight", "time out", "skate",
        "charlie", "squad", "lv 45", "millenium", "sneakerina",
        # 小皮具经典
        "zippy", "brazza", "sarah", "victorine", "multiple", "pocket organizer",
        "key pouch", "coin card", "discovery", "christopher",
        # 腰带
        "initiales", "reversible", "lv shape", "pyramide", "lv circle",
        # 经典印花（走量）
        "monogram", "damier", "empreinte", "eclipse",
    ],
    cold_signals=[
        # 异皮:难走量 + 跨境法律/CITES问题(硬排除)。含法语拼写
        "crocodile", "crocodilien", "croco", "alligator", "python", "lizard", "lezard",
        "ostrich", "autruche", "karung", "stingray", "exotic", "fur", "mink", "shearling",
        # 高珠宝/贵金属
        "gold", "diamond", "fine jewelry", "high jewelry", "18k", "platinum",
        # 定制/限量/非鞋皮具混入
        "personalis", "made to order", "bespoke", "exceptional",
        # 明显非目标
        "perfume", "fragrance", "candle", "book", "guide", "trunk", "malle",
    ],
    layer_caps={"price": 150, "signal": 60, "verify": 20},
)

REGISTRY = {"LV": LV}
