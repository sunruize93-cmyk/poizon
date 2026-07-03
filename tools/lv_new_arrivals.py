#!/usr/bin/env python3
"""上新缺口监控:靠「快照对比」发现新到货号(LV 无发售日接口/sitemap 无日期,时间差分最可靠)。

- snapshot: 把当前 LV 目录(sitemap) + 得物 LV 市场 的货号集存成带日期的快照。
- diff A B: 对比两次快照,列出「新出现」的货号(=新品),并给出得物是否已有/价/本地卖家。
  新品缺口 = 新出现 + 得物价高(未被压) + 本地卖家≈0 → 就是"国内无货、只和欧洲竞争"的窗口。
首次运行只能建基线;之后每隔几天 snapshot 一次,diff 即得新品流。
用法:
  python tools/lv_new_arrivals.py snapshot
  python tools/lv_new_arrivals.py diff data/snapshots/<旧>.json data/snapshots/<新>.json
"""
import sys, os, json, glob

SNAP_DIR = "data/snapshots"


def load_articles():
    """当前 LV 全量货号(得物侧,带需求/价)+ LV 目录货号(供给侧)。"""
    dewu = {}
    if os.path.exists("data/dewu_market.json"):
        for r in json.load(open("data/dewu_market.json"))["rows"]:
            dewu[r["article_no"]] = {
                "cn_sold": r.get("cn_sold", 0), "kr_sold": r.get("kr_sold", 0),
                "cn_price": r.get("cn_price", 0), "bidable": r.get("bidable", 0),
                "title": r.get("title", ""), "cat": r.get("cat2") or r.get("cat3"),
            }
    lv_cat = set()
    if os.path.exists("data/lv_catalog.json"):
        lv_cat = {i["article_no"] for i in json.load(open("data/lv_catalog.json"))["items"]}
    return dewu, lv_cat


def snapshot(date_tag):
    dewu, lv_cat = load_articles()
    os.makedirs(SNAP_DIR, exist_ok=True)
    path = f"{SNAP_DIR}/{date_tag}.json"
    json.dump({"date": date_tag, "dewu": dewu, "lv_catalog": sorted(lv_cat)},
              open(path, "w"), ensure_ascii=False)
    print(f"✓ 快照 {date_tag}: 得物LV {len(dewu)} 款, LV目录 {len(lv_cat)} 款 → {path}")


def diff(old_path, new_path):
    old = json.load(open(old_path)); new = json.load(open(new_path))
    # 新品 = 新快照有、旧快照没有
    new_dewu = set(new["dewu"]) - set(old["dewu"])
    new_cat = set(new["lv_catalog"]) - set(old["lv_catalog"])
    print(f"对比 {old['date']} → {new['date']}")
    print(f"  得物LV 新增货号: {len(new_dewu)} | LV目录 新增: {len(new_cat)}")
    # 新到且得物已有价+本地卖家薄 = 缺口窗口
    print("\n★ 新出现在得物 且 本地卖家≤2 的新品(上新缺口窗口):")
    print("  中国销量 韩卖 得物价¥ 可出价 货号     名称")
    rows = []
    for a in new_dewu:
        d = new["dewu"][a]
        if d.get("kr_sold", 0) <= 2:
            rows.append(d | {"a": a})
    for d in sorted(rows, key=lambda x: x.get("cn_price", 0), reverse=True)[:25]:
        print(f"  {int(d.get('cn_sold',0)):>6} {int(d.get('kr_sold',0)):>3} {int(d.get('cn_price',0)):>7} {'可' if d.get('bidable') else '否'}   {d['a']:8} {str(d.get('title',''))[:26]}")
    print(f"\n(LV 上但得物还没有的新品 {len(new_cat)} 个 = 最早窗口,代购都还没上)")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "snapshot":
        tag = sys.argv[2] if len(sys.argv) > 2 else "baseline"
        snapshot(tag)
    elif len(sys.argv) >= 4 and sys.argv[1] == "diff":
        diff(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        snaps = sorted(glob.glob(f"{SNAP_DIR}/*.json"))
        print("已有快照:", [os.path.basename(s) for s in snaps])
