"""探查工具：按 LV 货号调官方 API，打印得物侧 商品/行情/销量。
用法：python tools/poizon_probe.py M82533 M81234 ...   [--raw]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
from src.dewu_source.official_api import DewuOfficialClient  # noqa: E402

raw = "--raw" in sys.argv
articles = [a for a in sys.argv[1:] if not a.startswith("--")]
c = DewuOfficialClient()


def pick_data(resp):
    d = resp.get("data")
    if isinstance(d, list):
        return d[0] if d else None
    return d or None


for art in articles:
    print("\n" + "=" * 70)
    info = c.query_by_article_number(art, region="KR")
    if raw:
        print(json.dumps(info, ensure_ascii=False, indent=1)[:2000])
    data = pick_data(info)
    if not data:
        print(f"{art}: 得物未找到（data 为空）  msg={info.get('msg')} code={info.get('code')}")
        continue
    spu = data.get("spuInfo") or {}
    skus = data.get("skuInfoList") or []
    print(f"{art}  «{spu.get('title','?')}»  spuId={spu.get('spuId')} "
          f"brand={spu.get('brandName')} cat={spu.get('categoryName')} "
          f"上架={spu.get('status')} 可买={spu.get('buyStatus')}  SKU数={len(skus)}")
    for s in skus[:6]:
        sid = s.get("skuId") or s.get("dwSkuId")
        size = ""
        for pv in (s.get("regionSalePvInfoList") or []):
            if pv.get("value"):
                size = pv["value"]; break
        price = c.get_lowest_price(sid, region="KR", currency="CNY")
        p = price.get("data") or {}
        def yuan(x):
            return f"¥{float(x)/100:.0f}" if x else "-"
        sold = ""
        if s.get("barCode"):
            try:
                bc = c.query_by_barcodes([s["barCode"]])
                ct = (bc.get("data") or {}).get("contents") or []
                if ct:
                    sold = ct[0].get("localSoldNum30", "")
            except Exception as e:
                sold = f"err"
        print(f"   sku={sid} size={size:<8} 可买={s.get('buyStatus')} "
              f"最低{yuan(p.get('minPrice'))} 均{yuan(p.get('averagePrice'))} "
              f"高{yuan(p.get('maxPrice'))} 他台{yuan(p.get('otherPlatformMinPrice'))} "
              f"30天销量={sold}")
