"""得物 App UI 自动化：激活窗口→坐标点击/输入→截图，一条命令原子执行。
坐标用「逻辑点」(=截图像素/backingScale)。用法：
  python tools/uia.py size                      # 打印显示点尺寸 + 截图像素
  python tools/uia.py do "act;click 1047 212;sleep .6;type M4583;key 36;sleep 3;shot /tmp/s.png"
命令：act click X Y  type TEXT  key CODE  cmd CODE  move X Y  sleep S  scroll DY
      shot PATH(全屏)  vshot PATH(裁得物窗+降采样,省token)  ocr(本地OCR→文本,读数据零图片token)
"""
import os
import subprocess
import sys
import time

import Quartz

PROC = "DUApp"


def activate():
    subprocess.run(["osascript", "-e",
        f'tell application "System Events" to set frontmost of process "{PROC}" to true'],
        capture_output=True)
    time.sleep(0.8)


def _post(ev):
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def click(x, y):
    pt = Quartz.CGPointMake(float(x), float(y))
    _post(Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, pt, 0)); time.sleep(0.08)
    _post(Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, pt, Quartz.kCGMouseButtonLeft)); time.sleep(0.06)
    _post(Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, pt, Quartz.kCGMouseButtonLeft))


def type_text(s):
    for ch in s:
        for down in (True, False):
            e = Quartz.CGEventCreateKeyboardEvent(None, 0, down)
            Quartz.CGEventKeyboardSetUnicodeString(e, len(ch), ch)
            _post(e); time.sleep(0.02)


def key(code):
    _post(Quartz.CGEventCreateKeyboardEvent(None, int(code), True)); time.sleep(0.03)
    _post(Quartz.CGEventCreateKeyboardEvent(None, int(code), False))


def key_combo(code, cmd=False, shift=False, opt=False):
    flags = 0
    if cmd: flags |= Quartz.kCGEventFlagMaskCommand
    if shift: flags |= Quartz.kCGEventFlagMaskShift
    if opt: flags |= Quartz.kCGEventFlagMaskAlternate
    d = Quartz.CGEventCreateKeyboardEvent(None, int(code), True)
    Quartz.CGEventSetFlags(d, flags); _post(d); time.sleep(0.04)
    u = Quartz.CGEventCreateKeyboardEvent(None, int(code), False)
    Quartz.CGEventSetFlags(u, flags); _post(u)


def move(x, y):
    pt = Quartz.CGPointMake(float(x), float(y))
    _post(Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, pt, 0)); time.sleep(0.05)


def scroll(dy):
    e = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitPixel, 1, int(dy))
    _post(e)


def shot(path):
    subprocess.run(["screencapture", "-x", path], capture_output=True)


# 得物窗口在屏幕左半（points）。只截它能去掉右侧终端噪声、省一半以上 token。
# 宽 800（≈显示 1060px）刚好在终端左缘内侧，避免终端文字混入。
DEWU_REGION = "0,0,800,870"


def vshot(path, region=DEWU_REGION):
    """裁到得物窗口并降采样：需要看版面找点击目标时用，比全屏截图省 token。"""
    subprocess.run(["screencapture", "-x", f"-R{region}", path], capture_output=True)
    subprocess.run(["sips", "-Z", "1200", path], capture_output=True)


def ocr(region=DEWU_REGION):
    """截得物窗口→本地 Vision OCR→打印文本行。读购买记录/属性用它，零图片 token。"""
    tmp = "/tmp/_ocr.png"
    subprocess.run(["screencapture", "-x", f"-R{region}", tmp], capture_output=True)
    here = os.path.dirname(os.path.abspath(__file__))
    out = subprocess.run([sys.executable, os.path.join(here, "ocr.py"), tmp],
                         capture_output=True, text=True)
    print(out.stdout, end="")
    if out.stderr.strip():
        print(out.stderr, end="")


def size():
    b = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
    print(f"display points: {int(b.size.width)} x {int(b.size.height)}")
    shot("/tmp/_cal.png")
    out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", "/tmp/_cal.png"],
                         capture_output=True, text=True).stdout
    print("screenshot px:", out.replace("\n", " "))


def run_seq(seq):
    for cmd in seq.split(";"):
        cmd = cmd.strip()
        if not cmd:
            continue
        parts = cmd.split(" ", 1)
        op = parts[0]
        arg = parts[1] if len(parts) > 1 else ""
        if op == "act":
            activate()
        elif op == "click":
            x, y = arg.split(); click(x, y)
        elif op == "type":
            type_text(arg)
        elif op == "key":
            key(arg)
        elif op == "cmd":          # cmd+<keycode>，如 cmd 0 = Cmd+A 全选
            key_combo(arg, cmd=True)
        elif op == "sleep":
            time.sleep(float(arg))
        elif op == "shot":
            shot(arg)
        elif op == "vshot":
            vshot(arg)
        elif op == "ocr":
            ocr(arg) if arg else ocr()
        elif op == "move":
            x, y = arg.split(); move(x, y)
        elif op == "scroll":
            scroll(arg)
        print(f"  · {cmd}")


if __name__ == "__main__":
    if sys.argv[1] == "size":
        size()
    elif sys.argv[1] == "do":
        run_seq(sys.argv[2])
