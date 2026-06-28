"""得物开放平台 (open.poizon.com / openapi.dewu.com) 官方 API 客户端。

已确认存在、对选品有用的接口：
  - 按品牌 ID 批量查 SPU（拉 LV 全量 SPU/SKU）         apiDetail/160
  - 按货号/条码查 SKU+SPU                              Query SKU & SPU by barcode
  - 按 spuId/skuId 查 SPU/SKU                          apiDetail/107
  - 商家自身 出价/库存/订单 管理

签名机制（已确认要素，公式待登录文档最终确认）：
  公共参数 app_key, timestamp(ms), sign, language, timeZone
  sign 算法：参数字典序拼接 + app_secret，做 MD5/HMAC（确切方式见文档「Authentication for Poizon Sellers」）

⚠️ 待用商家账号登录核实（docs/方案.md 阶段 1）：
  1) 接口返回是否含「市场最低价 / 历史成交 / 销量 / 想要人数」—— 决定能否纯靠官方 API 选品
  2) SPU/SKU 返回是否含 LV 官方货号字段（用于和 LV 端关联）
  3) sign 的确切算法与各接口的真实 path / 入参 / 出参
"""
from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timezone

import requests

from ..models import DewuProduct


def _now_ms() -> int:
    return int(time.time() * 1000)


def make_sign(params: dict, app_secret: str) -> str:
    """默认签名：键按字典序拼成 k=v，尾接 app_secret，MD5 大写。

    ⚠️ 这是基于得物开放平台常见约定的占位实现，登录文档「Authentication for
    Poizon Sellers」核实后替换为官方公式（可能是 HMAC-SHA256 或 MD5(appKey_secret_param)）。
    """
    items = sorted((k, v) for k, v in params.items() if k != "sign" and v is not None)
    raw = "".join(f"{k}{v}" for k, v in items) + app_secret
    return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()


class DewuOfficialClient:
    def __init__(self, app_key: str | None = None, app_secret: str | None = None,
                 access_token: str | None = None, base: str | None = None):
        self.app_key = app_key or os.getenv("DEWU_APP_KEY", "")
        self.app_secret = app_secret or os.getenv("DEWU_APP_SECRET", "")
        self.access_token = access_token or os.getenv("DEWU_ACCESS_TOKEN", "")
        self.base = (base or os.getenv("DEWU_API_BASE", "https://openapi.dewu.com")).rstrip("/")
        self._session = requests.Session()

    def _call(self, path: str, biz: dict) -> dict:
        """通用调用：注入公共参数 + 签名 + access_token。"""
        params = {
            "app_key": self.app_key,
            "timestamp": _now_ms(),
            "language": "zh_CN",
            "timeZone": "Asia/Shanghai",
            **biz,
        }
        if self.access_token:
            params["access_token"] = self.access_token
        params["sign"] = make_sign(params, self.app_secret)
        resp = self._session.post(f"{self.base}{path}", json=params, timeout=20)
        resp.raise_for_status()
        return resp.json()

    # ----- 商品发现：按品牌拉 LV 全量 SPU（apiDetail/160）-----
    def query_spu_by_brand(self, brand_id: int, scroll_id: str = "") -> dict:
        # TODO: path 与参数名以文档为准
        return self._call("/dop/api/v1/spu/queryByBrand",
                          {"brandId": brand_id, "scrollId": scroll_id})

    # ----- 按货号/条码查 SKU+SPU -----
    def query_by_barcode(self, barcode: str) -> dict:
        # TODO: path 与参数名以文档为准
        return self._call("/dop/api/v1/sku/queryByBarcode", {"barcode": barcode})

    # ----- 行情：能否拿到取决于平台开放程度，待核实 -----
    def query_market_quote(self, spu_id: str) -> dict:
        """获取某 SPU 的市场行情（最低价/销量）。若官方不开放，本方法保留空实现，
        由 screen_control 兜底。"""
        raise NotImplementedError("行情接口待核实；官方若不开放则改用 screen_control")

    # ----- 归一化为统一模型 -----
    @staticmethod
    def to_product(article_no: str, spu: dict, quote: dict | None = None) -> DewuProduct:
        """把官方返回拼装成 DewuProduct。字段映射待按真实返回结构调整。"""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        quote = quote or {}
        return DewuProduct(
            article_no=article_no,
            spu_id=str(spu.get("spuId", "")),
            title=spu.get("title", "") or spu.get("name", ""),
            market_price_cny=float(quote.get("minPrice", 0) or 0),
            sales_30d=int(quote.get("sales30d", 0) or 0),
            wish_count=int(quote.get("wishCount", 0) or 0),
            seller_count=int(quote.get("sellerCount", 0) or 0),
            price_volatility=float(quote.get("priceVolatility", 0) or 0),
            fetched_at=now,
            source="official_api",
        )
