"""LV 韩国官网抓取：按货号取价格(KRW) + 是否可售 + 逐规格。

真实接口（2026-07 实测确认，旧 pass-api 已失效）：
  GET https://api.louisvuitton.com/eco-as/lvcom-prodct-dtl-eapi/v2/products/kor-kr/skus/{货号}?productId={nvprodId}
  → 200, JSON 约 13KB。关键字段：
      priceRaw      3040000        价格(KRW，干净整数；另有 price="₩ 3.040.000,00" 带格式)
      currency      KRW
      sellable      true           是否可线上下单
      backOrder     false          是否缺货预订
      backInStock   true
      name/color/macroColor/material
      skus[]        规格数组，每项 {skuId, color, size?, priceRaw, sellable, url}

⚠️ 传输层现实（实测）：此接口在 Akamai Bot Manager 之后。**纯 curl_cffi 直连必 403**
   （TLS 指纹能过，但缺浏览器 sensor 生成的 _abck cookie）。可行取数方式二选一：
     A. 浏览器直取（推荐）：patchright 真人化站内导航进 PDP，拦截本接口响应 → 见 tools/lv_extract.mjs。
        绕 Akamai 关键：①全新 profile（旧 profile 会被标记）②不深链 goto，从首页点商品卡进 PDP。
     B. cookie 收割回放：浏览器解 Akamai 后取 _abck/bm_sz + SLAS guest token(usid)，注入下方
        LVClient(cookies=...) 走 curl_cffi 快批；cookie 过期需重刷。
   本模块的 _parse() 两种方式通用（把接口 JSON → LVProduct）。

待办：货号→nvprodId(=productId) 解析（PDP URL 形如 .../{slug}-{nvprodId}/{货号}），
   大概率走站内搜索接口；productId 是否必填也待验证。见 docs/方案.md。
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

PRODUCT_API = "https://api.louisvuitton.com/eco-as/lvcom-prodct-dtl-eapi/v2/products/kor-kr/skus/{article}"
LOCALE = "kor-kr"           # 韩国区 locale（实测路径段用 kor-kr）
IMPERSONATE = "chrome131"   # curl_cffi 伪装目标（回放路径用；须配浏览器 cookie 才可能过 Akamai）
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Referer": "https://kr.louisvuitton.com/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


class LVRetryable(Exception):
    """可重试错误（429/5xx/网络）。"""


class LVClient:
    def __init__(self, proxy: str | None = None, cookies: dict | None = None,
                 min_interval: float = 1.5):
        """cookies：从浏览器会话收割的 Akamai/SLAS cookie（_abck/bm_sz/usid…）。
        没有它 curl_cffi 直连必被 Akamai 403 —— 见模块 docstring 的取数方式 A/B。"""
        if cffi_requests is None:
            raise RuntimeError("curl_cffi 未安装，请 pip install -r requirements.txt")
        self.proxy = proxy or os.getenv("LV_PROXY")
        self.cookies = cookies or {}
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
    def _get(self, article: str, product_id: str | None = None) -> dict:
        self._throttle()
        url = PRODUCT_API.format(article=article)
        params = {"productId": product_id} if product_id else {}
        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
        resp = self._session.get(
            url, params=params, headers=DEFAULT_HEADERS,
            cookies=self.cookies, proxies=proxies, timeout=20,
        )
        if resp.status_code in (429, 500, 502, 503, 504):
            raise LVRetryable(f"{resp.status_code} for {article}")
        if resp.status_code == 403:
            # Akamai 拦截：cookie 缺失/过期。重试无意义，需重新用浏览器收割 cookie。
            raise RuntimeError(f"403 被 Akamai 拦截（_abck cookie 缺失/过期，需浏览器重取）: {article}")
        resp.raise_for_status()
        return resp.json()

    def fetch(self, article_no: str, product_id: str | None = None) -> LVProduct:
        """抓单个货号。失败时返回带 error 的 LVProduct，不抛出，便于批量容错。"""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            data = self._get(article_no, product_id)
        except Exception as e:  # noqa: BLE001  批量抓取需要逐个容错
            return LVProduct(article_no=article_no, fetched_at=now, error=str(e))

        return self._parse(article_no, data, now)

    @staticmethod
    def parse(article_no: str, data: dict, fetched_at: str = "") -> LVProduct:
        """eco-as 商品详情 JSON → LVProduct。浏览器拦截的响应也可直接喂进来复用。"""
        variants = []
        for sku in data.get("skus", []) or []:
            variants.append(LVVariant(
                sku_id=str(sku.get("skuId", "")),
                color=sku.get("color", "") or "",
                size=str(sku.get("size", "") or ""),
                sellable=bool(sku.get("sellable", False)),
            ))
        return LVProduct(
            article_no=article_no,
            name=data.get("name", "") or "",
            category=data.get("product_category", "") or "",
            price_krw=float(data.get("priceRaw", 0) or 0),   # 干净整数 KRW
            sellable=bool(data.get("sellable", False)),
            is_backorder=bool(data.get("backOrder", False)),
            variants=variants,
            fetched_at=fetched_at,
        )

    # 向后兼容旧内部调用名
    _parse = parse

    def fetch_many(self, article_nos: list[str]) -> list[LVProduct]:
        return [self.fetch(a) for a in article_nos]
