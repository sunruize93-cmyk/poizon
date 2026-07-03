#!/usr/bin/env python3
"""把 LV 机会榜导成留档 Excel(中文表头,两个 sheet:盈利机会榜 + 全部测算)。
用法: python tools/export_excel.py [输出路径.xlsx]
"""
import sys, json, os
from datetime import datetime
import pandas as pd

# 默认输出到桌面留档文件夹,文件名自动带日期+时间(每次都有时间戳)
_ts = datetime.now().strftime("%Y%m%d_%H%M")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(f"~/Desktop/poizon选品/LV机会榜_{_ts}.xlsx")
b = json.load(open("data/lv_opportunity_board.json"))

COLS = {
    "opp": "机会分", "article_no": "货号", "title": "名称", "cat": "品类",
    "cn_sold": "中国30天销量", "kr_sold": "韩国卖家销量",
    "lv_krw": "LV韩国价(₩)", "dewu_cny": "得物中国价(¥)",
    "net_cny": "净利(¥)", "margin": "利润率",
}
# 兼容旧字段名 dewu_cn_cny
def norm(rows):
    out = []
    for r in rows:
        r = dict(r)
        r.setdefault("dewu_cny", r.get("dewu_cn_cny"))
        out.append({COLS[k]: r.get(k) for k in COLS})
    return pd.DataFrame(out)

prof = norm(b.get("profitable", b.get("rows", [])))
allc = norm(b.get("all_computed", []))

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with pd.ExcelWriter(OUT, engine="openpyxl") as xw:
    prof.to_excel(xw, sheet_name="盈利机会榜", index=False)
    if len(allc):
        allc.to_excel(xw, sheet_name="全部测算", index=False)
    for name, ws in xw.sheets.items():
        ws.freeze_panes = "A2"
        for col in ws.columns:
            w = max((len(str(c.value)) for c in col if c.value is not None), default=8)
            ws.column_dimensions[col[0].column_letter].width = min(max(w + 2, 10), 40)
        # 利润率列显示百分比
        for row in ws.iter_rows(min_row=2):
            for c in row:
                if ws.cell(1, c.column).value == "利润率" and isinstance(c.value, (int, float)):
                    c.number_format = "0%"
print(f"✓ 导出 {len(prof)} 盈利 + {len(allc)} 测算 → {OUT}")
