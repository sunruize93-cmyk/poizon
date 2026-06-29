"""实时汇率：KRW per CNY（1 CNY = ? KRW）。

来源优先级可配（settings.fx.source）：
  naver  → 네이버 금융 실시간 CNY/KRW
  api    → open.er-api.com 免费中间价
  manual → 直接用配置 krw_per_cny
任一来源失败自动回退到配置值，保证流程不中断。
卖家实际换汇走中国银行首尔分行/hana/熟人，汇率略优，可在 settings 手动覆盖。
"""
from __future__ import annotations

import requests


def _from_naver() -> float:
    # 네이버 모바일 금융 실시간 환율
    url = "https://m.stock.naver.com/front-api/marketIndex/productDetail"
    r = requests.get(url, params={"category": "exchange", "reutersCode": "FX_CNYKRW"},
                     timeout=8, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    d = r.json()
    res = d.get("result") or d.get("datas") or {}
    for k in ("closePrice", "calcPrice", "price"):
        v = res.get(k) if isinstance(res, dict) else None
        if v:
            return float(str(v).replace(",", ""))
    raise ValueError("naver 解析失败")


def _from_api() -> float:
    r = requests.get("https://open.er-api.com/v6/latest/CNY", timeout=8)
    r.raise_for_status()
    return float(r.json()["rates"]["KRW"])


def krw_per_cny(cfg: dict) -> float:
    """返回 1 CNY 对应多少 KRW。"""
    fx = cfg.get("fx", {})
    fallback = float(fx.get("krw_per_cny", 224))
    source = fx.get("source", "naver")
    if source == "manual":
        return fallback
    chain = ([_from_naver, _from_api] if source == "naver" else [_from_api, _from_naver])
    for fn in chain:
        try:
            v = fn()
            if 150 < v < 300:   # 合理性校验，防脏数据
                print(f"[fx] {fn.__name__} → 1 CNY = {v:.2f} KRW")
                return v
        except Exception as e:  # noqa: BLE001
            print(f"[fx] {fn.__name__} 失败：{e}")
    print(f"[fx] 实时获取失败，回退配置 {fallback}")
    return fallback


if __name__ == "__main__":
    import yaml, os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "config", "settings.example.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    print("KRW per CNY =", krw_per_cny(cfg))
