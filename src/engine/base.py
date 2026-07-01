"""引擎的数据契约 + 适配器接口（品牌/平台无关）。

漏斗每层把「候选」逐步富化并减量：
    RawItem   —Discover→  货号+名字+品类(供给侧目录，零成本)
      │ Triage(潜力初判：规则+LLM)  给 potential 分 + 决定是否继续
    Priced    —Price→     + 供给价(KRW)/是否可售
      │ 落在利润带?
    Signaled  —MarketSignal→ + 需求侧廉价信号(在售?想要?销量?)
      │ 有需求?
    Verified  —Verify→    + 真实成交速度/价 → 净利/利润率/综合分
      │
    Opportunity 排序输出

换品牌只写新的 SourceAdapter；换转卖平台只写新的 MarketAdapter。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Optional


# --------------------------------------------------------------------------- #
# 逐层富化的候选对象
# --------------------------------------------------------------------------- #
@dataclass
class RawItem:
    """Layer0 发现：供给侧目录里的一个商品（未抓价）。"""
    article_no: str
    name: str = ""              # 商品名/slug，供潜力判断用
    category: str = ""          # 归一化品类：shoes/slg/belt/bag/acc/...
    source_id: str = ""         # 供给侧内部 id（如 LV 的 nvprod）
    url: str = ""
    raw: dict = field(default_factory=dict)

    # Triage 产物
    potential: float = 0.0      # 0~1 潜力分（规则×LLM）
    potential_reason: str = ""
    keep: bool = True           # 是否进入下一层


@dataclass
class Priced(RawItem):
    """Layer2 供给报价后。"""
    supply_price: float = 0.0   # 供给侧价（本币，如 KRW）
    sellable: bool = False
    price_currency: str = "KRW"


@dataclass
class Signaled(Priced):
    """Layer3 需求侧廉价信号后。"""
    on_market: bool = False     # 转卖平台是否有此货号
    demand_wish: int = 0        # 想要/收藏人数
    demand_sold: int = 0        # 粗销量信号
    market_ref: str = ""        # 平台内商品 id


@dataclass
class Opportunity(Signaled):
    """Layer4 核验+算利润后的最终机会。"""
    market_price: float = 0.0   # 转卖成交价（本币，如 CNY）
    velocity: float = 0.0       # 月化成交速度
    net_profit: float = 0.0
    margin: float = 0.0
    score: float = 0.0          # 综合分（scorer 产出）
    detail: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# 适配器接口（Protocol：鸭子类型，实现类无需显式继承）
# --------------------------------------------------------------------------- #
class SourceAdapter(Protocol):
    """供给侧（如 LV 官网）。换品牌 = 换实现。"""
    name: str

    def discover(self, profile: "BrandProfile") -> list[RawItem]:
        """枚举目录（零/低成本，如读 sitemap）。"""
        ...

    def price(self, items: list[RawItem]) -> list[Priced]:
        """批量抓供给价 + 是否可售（中成本）。"""
        ...


class MarketAdapter(Protocol):
    """需求侧（转卖平台，如得物）。换平台 = 换实现。"""
    name: str

    def cheap_signal(self, items: list[Priced]) -> list[Signaled]:
        """廉价需求信号：在售/想要/粗销量（中成本，如官方 API）。"""
        ...

    def verify(self, items: list[Signaled]) -> list[Signaled]:
        """昂贵核验：真实成交速度+价（如屏幕 OCR）。只跑入围的。"""
        ...


class PotentialJudge(Protocol):
    """Layer1 潜力初判：给 RawItem 打 potential 分并决定是否保留。"""

    def judge(self, items: list[RawItem], profile: "BrandProfile") -> list[RawItem]:
        ...


# --------------------------------------------------------------------------- #
# 品牌/场景配置（可迁移的关键：换品牌换这个）
# --------------------------------------------------------------------------- #
@dataclass
class BrandProfile:
    """一个品牌+场景的全部可配置项。"""
    brand: str                                  # "LV"
    target_categories: set[str] = field(default_factory=set)   # 主营品类
    # 每品类的供给价带（本币），落带外的潜力压低/淘汰
    price_band: dict[str, tuple[float, float]] = field(default_factory=dict)
    # 高流动性/经典系列关键词（命中加潜力分）
    hot_lines: list[str] = field(default_factory=list)
    # 冷门/难变现关键词（命中减潜力分）
    cold_signals: list[str] = field(default_factory=list)
    # 漏斗每层预算上限（进入下一层的最大数量），控制成本
    layer_caps: dict[str, int] = field(default_factory=lambda: {
        "price": 200, "signal": 80, "verify": 25})
    cost_cfg: dict = field(default_factory=dict)   # 成本模型参数（喂 scorer）
