#!/usr/bin/env python3
"""本地 OCR：用 macOS Vision 框架把截图识别成文本行，省 token。
用法: ocr.py IMAGE [x,y,w,h]   # 可选裁剪区域(像素，基于图片本身)
按 y 坐标聚行，行内按 x 从左到右拼接，直接打印纯文本。"""
import sys
import Vision
import Quartz
from Foundation import NSURL


def ocr(path, region=None):
    url = NSURL.fileURLWithPath_(path)
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    W = Quartz.CGImageGetWidth(img)
    H = Quartz.CGImageGetHeight(img)

    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setRecognitionLanguages_(["zh-Hans", "en-US"])
    req.setUsesLanguageCorrection_(False)

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(img, None)
    handler.performRequests_error_([req], None)

    items = []  # (cx, cy, text)
    for obs in req.results():
        txt = obs.topCandidates_(1)[0].string()
        bb = obs.boundingBox()  # 归一化, 原点左下
        x = bb.origin.x * W
        y = (1 - bb.origin.y - bb.size.height) * H  # 转成左上原点
        w = bb.size.width * W
        h = bb.size.height * H
        if region:
            rx, ry, rw, rh = region
            if not (x + w > rx and x < rx + rw and y + h > ry and y < ry + rh):
                continue
        items.append((x, y, txt))

    # 按 y 聚行（同行阈值=行高的一半，约18px）
    items.sort(key=lambda t: t[1])
    rows, cur, cy = [], [], None
    for x, y, txt in items:
        if cy is None or abs(y - cy) <= 18:
            cur.append((x, txt))
            cy = y if cy is None else (cy + y) / 2
        else:
            rows.append(cur)
            cur, cy = [(x, txt)], y
    if cur:
        rows.append(cur)

    for row in rows:
        row.sort(key=lambda t: t[0])
        print("  ".join(t for _, t in row))


if __name__ == "__main__":
    path = sys.argv[1]
    reg = [float(v) for v in sys.argv[2].split(",")] if len(sys.argv) > 2 else None
    ocr(path, reg)
