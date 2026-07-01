#!/usr/bin/env python3
"""机会引擎入口：跑漏斗 Layer0-1（发现+潜力初判），输出高潜力候选清单。

默认只跑到 Layer1（零抓取成本），产出：
  data/lv_candidates.json   —— 全部候选(带 potential 分,降序)
  data/lv_judge_batch.json  —— 规则存活的 Top-N,给 Claude 做 LLM 精排的输入
用法:
  python tools/run_engine.py                 # 发现+规则初判
  python tools/run_engine.py --top 40        # 导出 Top40 给 LLM 打分
之后我(Claude)读 data/lv_judge_batch.json 打分→回填→再进 Layer2 报价。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.profiles import REGISTRY
from src.engine.judge import HybridJudge
from src.engine import funnel
from src.sources.lv import LVSource


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="LV")
    ap.add_argument("--top", type=int, default=40, help="导出多少个给 LLM 精排")
    ap.add_argument("--apply", metavar="SCORES.json", help="回填 LLM 精排分并重排,出最终 shortlist")
    ap.add_argument("--full", action="store_true", help="跑完整漏斗 L0-L4 出机会榜(用已有缓存数据)")
    ap.add_argument("--price-live", action="store_true", help="--full 时实起浏览器抓 LV 价(否则读缓存)")
    args = ap.parse_args()

    profile = REGISTRY[args.brand]

    # --full：完整漏斗 → 机会榜（得物侧用已抓的成交数据，LV 价默认读缓存）
    if args.full:
        import yaml
        from src.fx import krw_per_cny
        from src.markets.dewu import DewuMarket
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cfg_path = os.path.join(root, "config", "settings.yaml")
        if not os.path.exists(cfg_path):
            cfg_path = os.path.join(root, "config", "settings.example.yaml")
        cfg = yaml.safe_load(open(cfg_path, encoding="utf-8"))
        fx = krw_per_cny(cfg)
        llm = json.load(open("data/lv_llm_scores.json")).get("scores", {}) if os.path.exists("data/lv_llm_scores.json") else None
        res = funnel.run(profile, LVSource(live=args.price_live), HybridJudge(),
                         market=DewuMarket(cfg, fx), do_price=True, llm_scores=llm)
        ops = res["opportunities"]
        print(f"\n★ 机会榜（{len(ops)} 品有成交可算,汇率 1CNY={fx:.0f}KRW）:")
        print("  潜力 综合分  货号      净利¥    利润率  月化   品类   名称")
        for o in ops[:20]:
            print(f"  {o.potential:.2f} {o.score:.3f}  {o.article_no:8} {o.net_profit:>7.0f}  {o.margin:>5.0%}  {o.velocity:>5}  {o.category:5} {o.name[:20]}")
        json.dump({"opportunities": [vars(o) for o in ops]}, open("data/lv_opportunities.json", "w"), ensure_ascii=False, indent=1, default=str)
        print(f"\n✓ 机会榜 → data/lv_opportunities.json")
        return

    # --apply：回填 Claude 的 LLM 精排分 → 重排 → 出 shortlist（喂 Layer2 报价）
    if args.apply:
        from src.engine.base import RawItem
        cand = json.load(open("data/lv_candidates.json"))["items"]
        items = [RawItem(article_no=c["article_no"], name=c["name"], category=c["category"],
                         source_id=c.get("nvprod", ""), raw=c) for c in cand]
        for it, c in zip(items, cand):
            it.potential, it.potential_reason = c["potential"], c["reason"]
        scores = json.load(open(args.apply)).get("scores", {})
        HybridJudge.apply_llm_scores(items, scores)
        short = [{"article_no": it.article_no, "category": it.category, "name": it.name,
                  "potential": it.potential, "reason": it.potential_reason,
                  "nvprod": it.source_id} for it in items if it.potential >= 0.6]
        json.dump({"count": len(short), "items": short}, open("data/lv_shortlist.json", "w"),
                  ensure_ascii=False, indent=1)
        print(f"精排后 shortlist（potential≥0.6）{len(short)} 品，Top20:")
        for it in items[:20]:
            print(f"  {it.potential:.2f}  {it.article_no:8} {it.category:6} {it.name[:34]:34} {it.potential_reason[-40:]}")
        print(f"\n✓ shortlist → data/lv_shortlist.json（下一步喂 Layer2 抓价）")
        return

    source = LVSource()
    judge = HybridJudge()   # 无 llm_scorer → 先纯规则；LLM 分随后回填

    res = funnel.run(profile, source, judge, market=None, do_price=False)

    kept = res["kept"]
    os.makedirs("data", exist_ok=True)
    cand = [{"article_no": it.article_no, "category": it.category, "name": it.name,
             "potential": it.potential, "reason": it.potential_reason,
             "nvprod": it.source_id} for it in kept]
    json.dump({"count": len(cand), "items": cand}, open("data/lv_candidates.json", "w"),
              ensure_ascii=False, indent=1)

    batch = HybridJudge.export_for_llm(kept[:args.top])
    json.dump({"items": batch}, open("data/lv_judge_batch.json", "w"), ensure_ascii=False, indent=1)

    print(f"\n潜力 Top{min(args.top, len(kept))}（规则分,待 LLM 精排）:")
    for it in kept[:args.top]:
        print(f"  {it.potential:.2f}  {it.article_no:8} {it.category:6} {it.name[:42]}")
    print(f"\n✓ 候选 {len(cand)} → data/lv_candidates.json")
    print(f"✓ Top{args.top} 待精排 → data/lv_judge_batch.json")


if __name__ == "__main__":
    main()
