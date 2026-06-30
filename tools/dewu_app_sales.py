"""得物 Mac App「最近购买」抓取（屏幕控制兜底，官方 API 无此数据）。

得物 App=iOS app on Apple Silicon，证书固定、无网页层，只能屏幕控制+截图。
本工具把已验证的操作序列固化：商品详情页 → 打开「最近购买」弹层 → 逐屏下滚截图。
截图存 data/dewu_shots/<货号>/，再由人/视觉模型读出结构化成交记录写入
data/dewu_sales/<货号>.json，喂给 src/dewu_source/app_sales.py 算销量速度。

前置：得物 App 已登录；已授予 Ghostty 屏幕录制+辅助功能权限。
坐标=逻辑点（截图像素/2，retina 2x）。详情页「历史价格」区点 (1217,334) 开弹层。

用法：
  # 商品已停在详情页时，抓当前商品的最近购买（滚 N 屏）
  python tools/dewu_app_sales.py capture M4583 --scrolls 4
  # 仅打开弹层并截首屏
  python tools/dewu_app_sales.py open M4583
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uia  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(ROOT, "data", "dewu_shots")

# 详情页「历史价格/最近购买」入口（逻辑点）。点它弹出「最近购买」弹层。
HIST_ENTRY = (1217, 334)
BUY_BTN = (1145, 714)  # 立即购买——绝不点


def capture(article_no: str, scrolls: int = 4, settle: float = 2.0):
    """假设得物 App 已停在该货号详情页。打开最近购买弹层并逐屏下滚截图。"""
    out = os.path.join(SHOTS, article_no.upper())
    os.makedirs(out, exist_ok=True)
    # 开弹层 + 截首屏
    uia.activate()
    uia.click(*HIST_ENTRY)
    time.sleep(settle)
    uia.shot(os.path.join(out, "buy_00.png"))
    print(f"  · opened 最近购买, shot buy_00.png")
    # 逐屏下滚（每次约一屏，留重叠便于对齐去重）
    for i in range(1, scrolls + 1):
        uia.activate()
        uia.click(*HIST_ENTRY)   # 把焦点/光标放回弹层
        time.sleep(0.3)
        uia.scroll(-400)
        time.sleep(settle)
        uia.shot(os.path.join(out, f"buy_{i:02d}.png"))
        print(f"  · scroll {i}, shot buy_{i:02d}.png")
    print(f"[done] {scrolls + 1} 张截图 -> {out}")
    print("下一步：用视觉模型读这些截图，结构化写入 data/dewu_sales/"
          f"{article_no.upper()}.json（见 app_sales.py 的 schema）。")


def open_only(article_no: str):
    out = os.path.join(SHOTS, article_no.upper())
    os.makedirs(out, exist_ok=True)
    uia.activate()
    uia.click(*HIST_ENTRY)
    time.sleep(2.0)
    p = os.path.join(out, "buy_00.png")
    uia.shot(p)
    print(f"[done] {p}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["capture", "open"])
    ap.add_argument("article_no")
    ap.add_argument("--scrolls", type=int, default=4)
    args = ap.parse_args()
    if args.cmd == "capture":
        capture(args.article_no, scrolls=args.scrolls)
    else:
        open_only(args.article_no)
