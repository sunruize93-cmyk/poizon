#!/usr/bin/env python3
"""半自动 LV 抓价 —— 第 2 步：把 Safari 控制台跑出的 JSON 合并回 data/lv_prices.json。

用户在 Safari 控制台跑 tools/lv_snippet_gen.py 生成的代码后，把输出(剪贴板/打印那行)
存到一个文件，本脚本读入 → 增量合并进 data/lv_prices.json（不覆盖已有其它货号）。

兼容两种粘贴形态：
  A. 纯 JSON 对象  {"M78656": {...}, ...}
  B. 双重转义字符串 "{\\"M78656\\": {...}}"（copy() 生效时的形态），自动二次解析。

用法: python tools/lv_merge_paste.py <粘贴内容文件>    # 不传则读 stdin
"""
import sys, os, json, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)


def main():
    raw = (open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else sys.stdin.read()).strip()
    data = json.loads(raw)
    if isinstance(data, str):        # 双重转义形态：再解析一次
        data = json.loads(data)
    if not isinstance(data, dict):
        sys.exit("✗ 解析结果不是对象，检查粘贴内容。")

    n200 = sum(1 for v in data.values() if v.get("status") == 200)
    n410 = sum(1 for v in data.values() if v.get("status") == 410)
    print(f"解析: {len(data)} 货号 | 200(有价)={n200} 410(停售)={n410}")

    p = "data/lv_prices.json"
    cur = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"results": {}}
    cur.setdefault("results", {})
    before = len(cur["results"])
    cur["results"].update(data)
    cur["fetchedAt"] = datetime.datetime.now().isoformat()
    json.dump(cur, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    tot200 = sum(1 for v in cur["results"].values() if v.get("status") == 200)
    print(f"✓ 合并 {before} → {len(cur['results'])} 货号 | 200有价共 {tot200} → {p}")
    print("  下一步: python tools/run_select.py  重跑三条线出榜")


if __name__ == "__main__":
    main()
