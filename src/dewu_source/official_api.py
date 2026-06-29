"""得物开放平台 (open.poizon.com) 官方 API 客户端。

经登录文档核实，选品所需三类数据官方 API 全部提供：
  - 货号关联   id=140  by-article-number   入: articleNumber → 出: skuId/globalSkuId/barCode/上架状态
  - 市场行情   id=93   recommend-bid/price  入: skuId+region+currency → 出: 30天 min/max/avg 成交价
  - 销量       id=181  by-barcodes         入: barCode → 出: localSoldNum30 / commoditySales

签名（文档 Authentication for Poizon Sellers 确认）：
  含 app_key + timestamp(ms) 的全部非空参数，按 key 升序，Java URLEncoder 编码后拼成
  k=v&k=v，末尾直接接 app_secret，整体 MD5(32位) 转大写。
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from urllib.parse import quote_plus

import requests

from ..models import DewuProduct

# 接口路径（来自开放平台 catalog）
PATH_BY_ARTICLE = "/dop/api/v1/pop/api/v1/intl-commodity/intl/sku/sku-basic-info/by-article-number"
PATH_BY_BARCODES = "/dop/api/v1/pop/api/v1/intl-commodity/intl/sku/sku-basic-info/by-barcodes"
PATH_LOWEST_PRICE = "/dop/api/v1/pop/api/v1/recommend-bid/price"
PATH_LOWEST_PRICE_BATCH = "/dop/api/v1/pop/api/v1/recommend-bid/batchPrice"


def _enc(s) -> str:
    """Java URLEncoder.encode 风格：空格→+，保留 -_.*，其余百分号编码。"""
    return quote_plus(str(s), safe="*")


def _norm(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, tuple)):
        return ",".join(json.dumps(x, separators=(",", ":"), ensure_ascii=False) for x in v)
    if isinstance(v, dict):
        return json.dumps(v, separators=(",", ":"), ensure_ascii=False)
    return v


def make_sign(params: dict, app_secret: str) -> str:
    parts = []
    for k in sorted(params.keys()):
        if k == "sign":
            continue
        v = params[k]
        if v is None or v == "":
            continue
        parts.append(f"{_enc(k)}={_enc(_norm(v))}")
    string_a = "&".join(parts)
    return hashlib.md5((string_a + app_secret).encode("utf-8")).hexdigest().upper()


class DewuOfficialClient:
    def __init__(self, app_key=None, app_secret=None, base=None):
        self.app_key = app_key or os.getenv("DEWU_APP_KEY", "")
        self.app_secret = app_secret or os.getenv("DEWU_APP_SECRET", "")
        self.base = (base or os.getenv("DEWU_API_BASE", "https://open.poizon.com")).rstrip("/")
        self._session = requests.Session()

    def _call(self, path: str, biz: dict) -> dict:
        params = {"app_key": self.app_key, "timestamp": int(time.time() * 1000), **biz}
        params["sign"] = make_sign(params, self.app_secret)
        resp = self._session.post(f"{self.base}{path}", json=params, timeout=20,
                                  headers={"Content-Type": "application/json"})
        resp.raise_for_status()
        return resp.json()

    # ---- 货号 → SKU 信息（含 skuId / barCode / 上架状态）----
    def query_by_article_number(self, article_number: str, region="KR", language="en",
                                seller_status=True, buy_status=True) -> dict:
        return self._call(PATH_BY_ARTICLE, {
            "articleNumber": article_number, "region": region, "language": language,
            "sellerStatusEnable": seller_status, "buyStatusEnable": buy_status,
        })

    # ---- 市场行情：30天成交价 ----
    def get_lowest_price(self, sku_id: int, region="KR", currency="CNY",
                         bidding_type=20, sale_type=0) -> dict:
        return self._call(PATH_LOWEST_PRICE, {
            "skuId": sku_id, "region": region, "currency": currency,
            "biddingType": bidding_type, "saleType": sale_type,
        })

    # ---- 销量：barCode → 30天销量 ----
    def query_by_barcodes(self, barcodes: list[str], page_size=100, page_num=1) -> dict:
        return self._call(PATH_BY_BARCODES, {
            "barcodes": barcodes, "pageSize": page_size, "pageNum": page_num,
            "sellerStatusEnable": True, "buyStatusEnable": True,
        })

    # ---- 组合：从 LV 货号拿到选品所需的得物行情，拼成 DewuProduct ----
    def fetch_product(self, article_number: str, region="KR", currency="CNY") -> DewuProduct:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            info = self.query_by_article_number(article_number, region=region)
            items = info.get("data") or []
            if not items:
                return DewuProduct(article_no=article_number, fetched_at=now,
                                   source="official_api", error="得物KR未找到/未上架")
            item = items[0]
            spu = item.get("spuInfo") or {}
            skus = item.get("skuInfoList") or []
            # 遍历可买 SKU 取得物市场最低价（不同 SKU 价差大，取整体最低作选品基准）
            best_price = 0.0
            best_vol = 0.0
            for s in skus:
                if s.get("buyStatus") != 1:
                    continue
                sid = s.get("skuId") or s.get("dwSkuId")
                pdata = (self.get_lowest_price(sid, region=region, currency=currency).get("data") or {})
                p = _market_price(pdata, currency)
                if p > 0 and (best_price == 0 or p < best_price):
                    best_price = p
                    best_vol = _vol(pdata)
            return DewuProduct(
                article_no=article_number,
                spu_id=str(spu.get("spuId", "")),
                title=spu.get("title", ""),
                market_price_cny=best_price,
                sales_30d=0,        # barCode 多为空，销量改走 id=86，见 TODO
                wish_count=0,
                seller_count=0,
                price_volatility=best_vol,
                fetched_at=now, source="official_api",
            )
        except Exception as e:  # noqa: BLE001
            return DewuProduct(article_no=article_number, fetched_at=now,
                               source="official_api", error=str(e))


def _market_price(pdata: dict, currency: str) -> float:
    """从行情返回提取市场最低价并换算到货币单位。
    CNY/USD/EUR 等返回值是最小单位(分)，需 /100；KRW/JPY 无小数，原值。"""
    raw = pdata.get("globalMinPrice") or pdata.get("asiaMinPrice") or 0
    if not raw:
        leaks = pdata.get("leakInfos") or []
        raw = leaks[0].get("leakPrice", 0) if leaks else 0
    if not raw:
        return 0.0
    div = 1 if currency in ("KRW", "JPY") else 100
    return round(float(raw) / div, 2)


def _vol(pdata: dict) -> float:
    """用价格分布 (p90-p10)/p50 粗估波动（分位值单位一致，比值无需换算）。"""
    items = {it.get("percentValue"): it.get("price") for it in (pdata.get("priceRangeItems") or [])}
    p10, p50, p90 = items.get(10), items.get(50), items.get(90)
    try:
        if p10 and p50 and p90 and float(p50) > 0:
            return round((float(p90) - float(p10)) / float(p50), 3)
    except Exception:
        pass
    return 0.0


if __name__ == "__main__":
    # 只读实测：验证签名/鉴权/链路。用法 python -m src.dewu_source.official_api M81234
    import sys
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    art = sys.argv[1] if len(sys.argv) > 1 else "M81234"
    c = DewuOfficialClient()
    print(f"[test] query_by_article_number({art}, region=KR)")
    r = c.query_by_article_number(art)
    print(json.dumps(r, ensure_ascii=False, indent=2)[:1500])
