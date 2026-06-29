"""选品榜单导出：Excel（主）+ CSV。"""
from __future__ import annotations

import csv
import os
from datetime import datetime, timezone

from ..models import Candidate

COLUMNS = [
    ("rank", "排名"),
    ("article_no", "货号"),
    ("name", "名称"),
    ("category", "类目"),
    ("score", "综合评分"),
    ("net_profit_cny", "净利润¥"),
    ("scenario", "场景"),
    ("margin_rate", "利润率"),
    ("profit_normal", "普通挂单利¥"),
    ("profit_instant", "立即变现利¥"),
    ("cost_cny", "总成本¥"),
    ("purchase_cost", "采购¥"),
    ("logistics", "物流¥"),
    ("dewu_price", "得物市场价¥"),
    ("lv_price_krw", "LV价格₩"),
    ("sales_30d", "近30天销量"),
    ("wish_count", "想要人数"),
    ("seller_count", "竞争(卖家数)"),
    ("lv_sellable", "LV可买"),
    ("passed", "进榜"),
    ("reject_reason", "淘汰原因"),
]


def _row(rank: int, c: Candidate) -> dict:
    return {
        "rank": rank,
        "article_no": c.article_no,
        "name": c.lv.name or c.dewu.title,
        "category": c.lv.category,
        "score": c.score,
        "net_profit_cny": c.net_profit_cny,
        "scenario": "立即变现" if c.sell_scenario == "instant" else "普通挂单",
        "margin_rate": f"{c.margin_rate:.1%}",
        "profit_normal": c.profit_normal_cny,
        "profit_instant": c.profit_instant_cny,
        "purchase_cost": c.purchase_cost_cny,
        "logistics": c.logistics_cny,
        "cost_cny": c.cost_cny,
        "dewu_price": c.dewu.market_price_cny,
        "lv_price_krw": c.lv.price_krw,
        "sales_30d": c.dewu.sales_30d,
        "wish_count": c.dewu.wish_count,
        "seller_count": c.dewu.seller_count,
        "lv_sellable": "是" if c.lv.sellable else "否",
        "passed": "✓" if c.passed_filter else "",
        "reject_reason": c.reject_reason,
    }


def export_csv(candidates: list[Candidate], path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow([label for _, label in COLUMNS])
        for i, c in enumerate(candidates, 1):
            r = _row(i, c)
            w.writerow([r[key] for key, _ in COLUMNS])
    return path


def export_excel(candidates: list[Candidate], path: str) -> str:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
    except ImportError:
        # 没装 openpyxl 时退化为 CSV
        return export_csv(candidates, path.replace(".xlsx", ".csv"))

    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "选品榜单"
    header_fill = PatternFill("solid", fgColor="00B386")
    ws.append([label for _, label in COLUMNS])
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
    pass_fill = PatternFill("solid", fgColor="E8F8F2")
    for i, c in enumerate(candidates, 1):
        r = _row(i, c)
        ws.append([r[key] for key, _ in COLUMNS])
        if c.passed_filter:
            for cell in ws[ws.max_row]:
                cell.fill = pass_fill
    for col in ws.columns:
        width = max((len(str(cell.value)) for cell in col if cell.value), default=8)
        ws.column_dimensions[col[0].column_letter].width = min(width + 2, 40)
    wb.save(path)
    return path


def default_paths(out_dir: str = "report") -> "tuple[str, str]":
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    return (
        os.path.join(out_dir, f"选品榜单_{ts}.xlsx"),
        os.path.join(out_dir, f"选品榜单_{ts}.csv"),
    )
