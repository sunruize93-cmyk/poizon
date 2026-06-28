"""全流程编排：读货号 → 抓 LV → 取得物行情 → 关联 → 算利润&评分 → 出榜单。

用法：
  python -m src.pipeline.run            # 真实抓取（需配 .env / settings.yaml）
  python -m src.pipeline.run --demo     # 合成数据跑通，验证算法与报表（无需任何凭证）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import yaml

from ..matcher.match import build_candidates, diagnose
from ..models import DewuProduct, LVProduct, LVVariant
from ..report import export
from ..scorer.score import apply_filters, compute_profit, score_candidates

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_config() -> dict:
    for name in ("config/settings.yaml", "config/settings.example.yaml"):
        path = os.path.join(ROOT, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            print(f"[config] 使用 {name}")
            return cfg
    raise FileNotFoundError("找不到 config/settings.yaml")


def _load_skus() -> list[dict]:
    import csv
    for name in ("config/skus.csv", "config/skus.example.csv"):
        path = os.path.join(ROOT, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            print(f"[skus] 使用 {name}，{len(rows)} 个货号")
            return rows
    raise FileNotFoundError("找不到 config/skus.csv")


# --------------------------------------------------------------------------- #
# 数据获取
# --------------------------------------------------------------------------- #
def fetch_real(skus: list[dict]) -> "tuple[list[LVProduct], list[DewuProduct]]":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))

    from ..lv_scraper.client import LVClient
    article_nos = [s["article_no"] for s in skus]

    print(f"[LV] 抓取 {len(article_nos)} 个货号 ...")
    lv_list = LVClient().fetch_many(article_nos)

    # 得物：优先官方 API；行情接口未接通时退化为屏幕控制占位
    print("[得物] 取行情 ...")
    from ..dewu_source.screen_control import ScreenControlSource
    src = ScreenControlSource()
    name_by_no = {s["article_no"]: s.get("name", "") for s in skus}
    dewu_list = [src.fetch(a, name_by_no.get(a, "")) for a in article_nos]
    return lv_list, dewu_list


def fetch_demo(skus: list[dict]) -> "tuple[list[LVProduct], list[DewuProduct]]":
    """合成数据：价格/销量按货号哈希派生，确定且可复现，用于验证算法链路。"""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lv_list, dewu_list = [], []
    for i, s in enumerate(skus):
        no = s["article_no"]
        h = sum(ord(ch) for ch in no)
        price_krw = 700000 + (h % 9) * 150000          # 70万~190万₩
        sellable = (h % 5) != 0                         # ~80% 可买
        dewu_price = price_krw * 0.0053 * (1.25 + (h % 7) * 0.06)  # 在采购价上加成
        lv_list.append(LVProduct(
            article_no=no, name=s.get("name", ""), category=s.get("category", ""),
            price_krw=price_krw, sellable=sellable, is_backorder=(h % 11 == 0),
            variants=[LVVariant(sku_id=f"{no}-1", color=s.get("color", ""), sellable=sellable)],
            fetched_at=now,
        ))
        dewu_list.append(DewuProduct(
            article_no=no, spu_id=f"SPU{1000+i}", title=s.get("name", ""),
            market_price_cny=round(dewu_price, 0),
            sales_30d=(h % 13) * 4, wish_count=(h % 17) * 12,
            seller_count=1 + (h % 9), price_volatility=round((h % 5) * 0.03, 3),
            fetched_at=now, source="demo",
        ))
    return lv_list, dewu_list


# --------------------------------------------------------------------------- #
def run(demo: bool = False, top: int = 50) -> list:
    cfg = _load_config()
    skus = _load_skus()

    lv_list, dewu_list = (fetch_demo if demo else fetch_real)(skus)

    diag = diagnose(lv_list, dewu_list)
    print(f"[关联] 命中 {len(diag['matched'])} / LV {diag['lv_total']} / 得物 {diag['dewu_total']}")
    if diag["lv_fetch_errors"]:
        print(f"[关联] LV 抓取失败: {diag['lv_fetch_errors']}")

    candidates = build_candidates(lv_list, dewu_list)
    for c in candidates:
        c.lv.category = c.lv.category or next(
            (s.get("category", "") for s in skus if s["article_no"] == c.article_no), "")
        compute_profit(c, cfg)
    candidates = apply_filters(candidates, cfg)
    ranked = score_candidates(candidates, cfg)

    # 产出
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    snap = os.path.join(ROOT, "data", f"snapshot_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json")
    with open(snap, "w", encoding="utf-8") as f:
        json.dump({"diagnose": diag,
                   "candidates": [_dump(c) for c in ranked]}, f, ensure_ascii=False, indent=2)

    xlsx, csv_path = export.default_paths(os.path.join(ROOT, "report"))
    export.export_excel(ranked[:top], xlsx)
    export.export_csv(ranked, csv_path)

    passed = [c for c in ranked if c.passed_filter]
    print(f"\n[结果] 进榜 {len(passed)} 个，榜单已出：")
    print(f"  {xlsx}\n  {csv_path}\n  {snap}")
    print("\nTOP 10：")
    for i, c in enumerate(passed[:10], 1):
        print(f"  {i:>2}. {c.article_no:<8} 评分{c.score:.3f}  净利¥{c.net_profit_cny:<7} "
              f"利润率{c.margin_rate:.0%}  销量{c.dewu.sales_30d}  {c.lv.name}")
    return ranked


def _dump(c) -> dict:
    return {
        "article_no": c.article_no, "score": c.score,
        "net_profit_cny": c.net_profit_cny, "margin_rate": c.margin_rate,
        "cost_cny": c.cost_cny, "dewu_price": c.dewu.market_price_cny,
        "lv_price_krw": c.lv.price_krw, "lv_sellable": c.lv.sellable,
        "sales_30d": c.dewu.sales_30d, "wish_count": c.dewu.wish_count,
        "seller_count": c.dewu.seller_count,
        "passed": c.passed_filter, "reject_reason": c.reject_reason,
        "subscores": c.subscores,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="用合成数据跑通，无需凭证")
    ap.add_argument("--top", type=int, default=50, help="Excel 榜单保留前 N")
    args = ap.parse_args()
    try:
        run(demo=args.demo, top=args.top)
    except FileNotFoundError as e:
        print(f"[错误] {e}", file=sys.stderr)
        sys.exit(1)
