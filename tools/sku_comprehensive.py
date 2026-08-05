#!/usr/bin/env python3
"""SKU 综合表单 —— 把选品从 SPU 细化到 SKU,过滤卖不动的极端尺码,按权重排出「能卖+赚钱」综合榜。

背景:货号中位价抹平机会;同一货号不同 (版本/包装 × 尺码) 净利差 ¥5000+。且极端小码/大码
(如鞋 KR≤235、KR≥280) 常规卖不动。本工具:
  1) 逐 SKU 算净利(得物 SKU 卖价 × 成本模型)
  2) 过滤: 净利>0; 极端尺码且无真实成交的淘汰; 需求(SKU有成交 或 SPU销量≥MIN)
  3) 加权综合分(权重在文件顶部可调,用户 2026-08 授权自设)
输出: data/sku_comprehensive.json + 控制台榜。用法: python tools/sku_comprehensive.py [--top 60]
"""
import pandas as pd, warnings, re, sys, os, json, glob
warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import yaml
from src.fx import krw_per_cny
from src.models import LVProduct, DewuProduct, Candidate
from src.scorer.score import compute_profit

cfg = yaml.safe_load(open("config/settings.example.yaml", encoding="utf-8"))
if os.path.exists("config/settings.yaml"):
    cfg = yaml.safe_load(open("config/settings.yaml", encoding="utf-8"))
fx = krw_per_cny(cfg)

# ---- 权重(用户授权自设): 净利/需求/利润率 ----
W_NET, W_DEMAND, W_MARGIN = 0.40, 0.30, 0.30
MIN_SPU_SALES = 3        # SPU 30天销量≥此 才算有需求
MIN_NET = 300            # 单件净利下限(¥):滤掉只赚几块钱的噪声
MIN_MARGIN = 0.05        # 利润率下限
SIZE_RANGE = {           # 常规尺码区间(鞋=KR码; 皮带=Ordered Size码)
    "板鞋": (235, 275), "一字拖鞋": (235, 275), "生活休闲鞋": (230, 275),
    "皮带": (85, 100),
}
CHN_RANGE = (36, 43)     # 生活休闲鞋的 CHN 码正常区间


def num(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).replace(",", "").replace("KRW", "").replace("₩", "").replace("+", "").strip()
    if s in ("--", "", "-"):
        return None
    m = re.search(r"[\d.]+", s)
    return float(m.group()) if m else None


def field(txt, key):
    m = re.search(rf"{key}[:：]([^;；]+)", str(txt))
    return m.group(1).strip() if m else ""


def _size_num(cat, spec):
    """提取尺码数值; 无尺码类(包/配件)返回 None。"""
    if cat in ("板鞋", "一字拖鞋"):
        m = re.search(r"KR\s*(\d+)", spec)
        return int(m.group(1)) if m else None
    if cat == "生活休闲鞋":
        m = re.search(r"KR\s*(\d+)", spec)
        if m:
            return int(m.group(1))
        m = re.search(r"CHN\s*([\d.]+)", spec)
        return float(m.group(1)) if m else None
    if cat == "皮带":
        m = re.search(r"(?:Ordered Size\s*)?(\d{2,3})", spec)
        return int(m.group(1)) if m else None
    return None


def size_ok(cat, spec, has_deal):
    """尺码是否常规/有销量。鞋/皮带过滤极端码;有真实成交的码一律放行(说明在卖)。"""
    if has_deal:
        return True
    rng = SIZE_RANGE.get(cat)
    if cat in ("板鞋", "一字拖鞋"):
        m = re.search(r"KR\s*(\d+)", spec)
        if m:
            return rng[0] <= int(m.group(1)) <= rng[1]
        return True   # 无KR码(异常),不硬拦
    if cat == "生活休闲鞋":
        m = re.search(r"KR\s*(\d+)", spec)
        if m:
            return rng[0] <= int(m.group(1)) <= rng[1]
        m = re.search(r"CHN\s*([\d.]+)", spec)
        if m:
            return CHN_RANGE[0] <= float(m.group(1)) <= CHN_RANGE[1]
        return True
    if cat == "皮带":
        m = re.search(r"(?:Ordered Size\s*)?(\d{2,3})", spec)
        if m:
            return rng[0] <= int(m.group(1)) <= rng[1]
        return True
    return True


def size_risk(cat, spec):
    """偏大/偏小风险标注(即使有成交也提示;包/配件无尺码→常规)。"""
    v = _size_num(cat, spec)
    if v is None:
        return ""
    rng = SIZE_RANGE.get(cat)
    if cat == "生活休闲鞋":
        m = re.search(r"KR\s*(\d+)", spec)
        if not m:
            return "偏大" if v > CHN_RANGE[1] else ("偏小" if v < CHN_RANGE[0] else "")
    if rng and v > rng[1]:
        return "⚠偏大码"
    if rng and v < rng[0]:
        return "⚠偏小码"
    return ""


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=60, help="综合榜保留前N")
    args = ap.parse_args()

    b = json.load(open("data/lv_opportunity_board.json"))
    spu = {r["article_no"]: r for r in b["all_computed"] if (r.get("net_cny") or 0) > 0}
    if not spu:
        sys.exit("✗ 没有盈利 SPU,先跑 run_select/lv_opportunity_board")
    prices = json.load(open("data/lv_prices.json")).get("results", {})
    xs = sorted(glob.glob("data/商品搜索导出*.xlsx"))
    raw = pd.read_excel(xs[-1]); raw.columns = [c.strip() for c in raw.columns]

    rows = []
    for _, r in raw.iterrows():
        art = str(r["商品货号"])
        sp = spu.get(art)
        if not sp:
            continue
        ask, avg = num(r["当前中国最低出价"]), num(r["过去30天成交均价"])
        sell_krw = avg or ask
        if not sell_krw:
            continue
        cat = str(r["商品三级类目"])
        spec = str(r["尺码/规格/颜色"])
        has_deal = bool(avg)
        if not size_ok(cat, spec, has_deal):
            continue
        lv_krw = float(prices.get(art, {}).get("priceRaw") or sp["lv_krw"])
        c = Candidate(article_no=art, lv=LVProduct(article_no=art, category=cat, price_krw=lv_krw, sellable=True),
                      dewu=DewuProduct(article_no=art, market_price_cny=round(sell_krw / fx, 2)))
        compute_profit(c, cfg, fx)
        if c.net_profit_cny < MIN_NET or c.margin_rate < MIN_MARGIN:
            continue
        if not (has_deal or int(sp["cn_sold"]) >= MIN_SPU_SALES):
            continue   # 既无该码成交、SPU又冷 → 卖不动
        rows.append({
            "article_no": art, "title": str(sp["title"])[:26], "cat": cat,
            "颜色": field(spec, "颜色"), "版本": field(spec, "版本"),
            "包装": field(spec, "包装") or field(spec, "礼盒"),
            "尺码": field(spec, "尺码"),
            "尺码风险": size_risk(cat, spec),
            "spu_sales": int(sp["cn_sold"]), "kr_sold": int(sp["kr_sold"]),
            "出价₩": int(ask or 0), "均价₩": int(avg or 0),
            "净利¥": round(c.net_profit_cny), "利润率": round(c.margin_rate, 4),
            "真实成交": has_deal,
        })
    if not rows:
        sys.exit("✗ 过滤后无 SKU,放宽 MIN_SPU_SALES/尺码区间")

    # 归一化+加权
    mx_net = max(r["净利¥"] for r in rows) or 1
    mx_margin = max(r["利润率"] for r in rows) or 1e-9
    mx_demand = max(r["spu_sales"] for r in rows) or 1
    for r in rows:
        n_net, n_margin = r["净利¥"] / mx_net, r["利润率"] / mx_margin
        demand = (r["spu_sales"] / mx_demand) * (1.0 if r["真实成交"] else 0.6)
        r["score"] = round(W_NET * n_net + W_MARGIN * n_margin + W_DEMAND * demand, 4)
        r["月利润¥"] = round(r["净利¥"] * r["spu_sales"])
    rows.sort(key=lambda r: -r["score"])

    print(f"═══ SKU 综合表单（净利{W_NET} + 需求{W_DEMAND} + 利润率{W_MARGIN}; 已过滤极端尺码）═══")
    print(f"参与 {len(rows)} 个 SKU / {len(set(r['article_no'] for r in rows))} 个货号 | 常规码区间: {SIZE_RANGE}\n")
    print(" # 综合分 货号    类型(颜色/版本/包装)    尺码      净利¥ 利润率  SPU月销 月利润¥  真实成交  风险")
    for i, r in enumerate(rows[: args.top], 1):
        typ = (r["颜色"] or r["版本"] or r["包装"] or "")[:16]
        tag = "有成交" if r["真实成交"] else "仅出价"
        print(f"{i:>2} {r['score']:.3f} {r['article_no']:8} {typ:16} {r['尺码'][:10]:10} "
              f"{r['净利¥']:>6.0f} {r['利润率']:>5.0%} {r['spu_sales']:>5} {r['月利润¥']:>7.0f}  {tag:4} {r['尺码风险']}")
    json.dump({"as_of": "2026-08-05", "weights": {"net": W_NET, "demand": W_DEMAND, "margin": W_MARGIN},
               "rows": rows[: args.top]}, open("data/sku_comprehensive.json", "w"), ensure_ascii=False, indent=1)
    print(f"\n✓ → data/sku_comprehensive.json (Top{args.top})")


if __name__ == "__main__":
    main()
