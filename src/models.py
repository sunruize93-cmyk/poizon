"""跨模块共享的数据结构。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LVVariant:
    """LV 单个 SKU 规格（颜色/尺码）。"""
    sku_id: str
    color: str = ""
    size: str = ""
    sellable: bool = False


@dataclass
class LVProduct:
    """LV 韩国官网某货号的状态。来源：pass-api.louisvuitton.com"""
    article_no: str
    name: str = ""
    category: str = ""
    price_krw: float = 0.0
    sellable: bool = False          # 当前是否可线上下单
    is_backorder: bool = False      # 是否可缺货预订
    variants: list[LVVariant] = field(default_factory=list)
    fetched_at: str = ""
    error: Optional[str] = None     # 抓取失败时记录原因


@dataclass
class DewuProduct:
    """得物某货号的市场行情。来源：官方 API 或屏幕控制。"""
    article_no: str
    spu_id: str = ""
    title: str = ""
    market_price_cny: float = 0.0   # 市场最低价（选品基准）
    sales_30d: int = 0              # 近 30 天成交量；拿不到时用近似
    wish_count: int = 0             # 想要人数
    seller_count: int = 0           # 在售卖家数 / 出价数量（竞争度）
    price_volatility: float = 0.0   # 价格波动率（标准差/均值），拿不到留 0
    fetched_at: str = ""
    source: str = ""                # "official_api" | "screen_control"
    error: Optional[str] = None


@dataclass
class Candidate:
    """关联 + 评分后的候选品。"""
    article_no: str
    lv: LVProduct
    dewu: DewuProduct
    # —— 利润计算 ——
    cost_cny: float = 0.0           # 采购总成本（到得物入库）
    sell_net_cny: float = 0.0       # 得物到手价
    net_profit_cny: float = 0.0     # 净利润 = 到手价 - 成本
    margin_rate: float = 0.0        # 利润率 = 净利润 / 成本
    # —— 评分 ——
    score: float = 0.0
    subscores: dict = field(default_factory=dict)
    passed_filter: bool = True
    reject_reason: str = ""
