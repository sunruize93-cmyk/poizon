"""得物电脑版「屏幕控制」兜底取数。

仅当官方 API 不开放行情（市场价/销量）时启用。思路：
  1. 打开得物电脑版 App，按货号在搜索框检索
  2. 截图 → OCR/视觉识别商品卡片上的：最低价、X人付款、X人想要
  3. 结构化为 DewuProduct

实现选项（择一，阶段 1 核实后定）：
  A. 由 Claude 通过屏幕控制驱动（人在环，半自动，适合几十个货号的小范围）
  B. 本地脚本 pyautogui + 截图 + OCR（paddleocr/tesseract），全自动但需调坐标
  C. 得物电脑版若是 Electron，尝试接其本地接口/抓包（最高效，需逆向）

本文件先定义统一接口，具体驱动方式接通后实现。屏幕控制相比逆向爬虫更不易触发
风控（行为接近真人），但吞吐低、需保持 App 前台。
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..models import DewuProduct


class ScreenControlSource:
    def __init__(self, settle_seconds: float = 2.0):
        self.settle_seconds = settle_seconds  # 每次搜索后等待页面稳定再识别

    def fetch(self, article_no: str, name_hint: str = "") -> DewuProduct:
        """按货号在得物电脑版检索并识别行情。

        TODO 接通后实现：搜索 -> 截图 -> 识别 -> 解析价格/销量/想要
        当前返回带 error 的占位，保证 pipeline 不中断。
        """
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return DewuProduct(
            article_no=article_no, title=name_hint, fetched_at=now,
            source="screen_control", error="screen_control 待接通",
        )

    @staticmethod
    def parse_card(text: str) -> dict:
        """从识别出的商品卡片文本里抽取数值。

        例：'¥7510  19人付款' / '81人想要' 。返回 {market_price_cny, sales_30d, wish_count}
        """
        import re
        out = {"market_price_cny": 0.0, "sales_30d": 0, "wish_count": 0}
        if m := re.search(r"[¥￥]\s*([\d,]+)", text):
            out["market_price_cny"] = float(m.group(1).replace(",", ""))
        if m := re.search(r"([\d.]+万?)\s*\+?\s*人付款", text):
            out["sales_30d"] = _to_int(m.group(1))
        if m := re.search(r"([\d.]+万?)\s*人想要", text):
            out["wish_count"] = _to_int(m.group(1))
        return out


def _to_int(s: str) -> int:
    """'1.4万' -> 14000, '35' -> 35"""
    s = s.strip()
    if s.endswith("万"):
        return int(float(s[:-1]) * 10000)
    return int(float(s))
