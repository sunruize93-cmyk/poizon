"""LV 韩国官网抓取：按货号取价格(KRW) + 是否可售。

走 LV 移动 App 的内部接口，不爬网页（网页有 Akamai，直连 403）。
  GET https://pass-api.louisvuitton.com/api/catalog/product/{货号}?locale=ko_KR

关键字段（来自移动 App 接口逆向）：
  sellableStatus.price.price   价格
  sellableStatus.sellable      是否可线上下单
  isBackOrder                  是否可缺货预订
  skus[]                       规格：skuId / color / size

反爬要点：
  - 用 curl_cffi 的 impersonate 伪装真实 TLS/JA3 指纹（requests 会被 Akamai 拦）。
  - 走韩国住宅代理（机房 IP 直接封）。
  - 控制频率 + 随机间隔，避免行为分析触发。

⚠️ 待真机抓包确认（见 docs/方案.md 阶段 2）：
  - locale 拼写 ko_KR vs kor_KR
  - pass-api 当前是否仍在线、韩国是否同一 host
  - 是否需要额外 client_id / client_secret 头
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..models import LVProduct, LVVariant

try:
    from curl_cffi import requests as cffi_requests
except ImportError:  # 允许在未安装依赖时导入本模块（骨架阶段）
    cffi_requests = None

PASS_API = "https://pass-api.louisvuitton.com/api/catalog/product/{article}"
LOCALE = "ko_KR"            # 韩国；待抓包确认拼写
IMPERSONATE = "safari17_0"  # curl_cffi 伪装目标，对应 iOS App 的 TLS 指纹
DEFAULT_HEADERS = {
    "User-Agent": "LVapp/ios/6.40.1.17199 LVApp PRD",
    "Accept": "application/json",
    "Host": "pass-api.louisvuitton.com",
}


class LVRetryable(Exception):
    """可重试错误（429/5xx/网络）。"""


class LVClient:
    def __init__(self, proxy: str | None = None, locale: str = LOCALE,
                 min_interval: float = 1.5):
        if cffi_requests is None:
            raise RuntimeError("curl_cffi 未安装，请 pip install -r requirements.txt")
        self.proxy = proxy or os.getenv("LV_PROXY")
        self.locale = locale
        self.min_interval = min_interval   # 两次请求最小间隔（秒）
        self._last = 0.0
        self._session = cffi_requests.Session(impersonate=IMPERSONATE)

    def _throttle(self):
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    @retry(
        retry=retry_if_exception_type(LVRetryable),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        reraise=True,
    )
    def _get(self, article: str) -> dict:
        self._throttle()
        url = PASS_API.format(article=article)
        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
        resp = self._session.get(
            url, params={"locale": self.locale},
            headers=DEFAULT_HEADERS, proxies=proxies, timeout=20,
        )
        if resp.status_code in (429, 500, 502, 503, 504):
            raise LVRetryable(f"{resp.status_code} for {article}")
        if resp.status_code == 403:
            # Akamai 拦截：通常是 TLS 指纹/IP 问题，重试无意义，直接报
            raise RuntimeError(f"403 被 Akamai 拦截（检查代理/impersonate）: {article}")
        resp.raise_for_status()
        return resp.json()

    def fetch(self, article_no: str) -> LVProduct:
        """抓单个货号。失败时返回带 error 的 LVProduct，不抛出，便于批量容错。"""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            data = self._get(article_no)
        except Exception as e:  # noqa: BLE001  批量抓取需要逐个容错
            return LVProduct(article_no=article_no, fetched_at=now, error=str(e))

        return self._parse(article_no, data, now)

    @staticmethod
    def _parse(article_no: str, data: dict, fetched_at: str) -> LVProduct:
        status = data.get("sellableStatus", {}) or {}
        price = (status.get("price") or {}).get("price", 0) or 0
        variants = []
        for sku in data.get("skus", []) or []:
            variants.append(LVVariant(
                sku_id=str(sku.get("skuId", "")),
                color=sku.get("color", "") or "",
                size=sku.get("size", "") or "",
                sellable=bool(sku.get("sellable", False)),
            ))
        return LVProduct(
            article_no=article_no,
            name=data.get("name", "") or data.get("title", "") or "",
            price_krw=float(price),
            sellable=bool(status.get("sellable", False)),
            is_backorder=bool(data.get("isBackOrder", False)),
            variants=variants,
            fetched_at=fetched_at,
        )

    def fetch_many(self, article_nos: list[str]) -> list[LVProduct]:
        return [self.fetch(a) for a in article_nos]
