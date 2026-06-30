"""得物 App UI 自动化：激活窗口→坐标点击/输入→截图，一条命令原子执行。
坐标用「逻辑点」(=截图像素/backingScale)。用法：
  python tools/uia.py size                      # 打印显示点尺寸 + 截图像素
  python tools/uia.py do "act;click 1047 212;sleep .6;type M4583;key 36;sleep 3;shot /tmp/s.png"
命令：act(激活得物) click X Y  type TEXT  key CODE  sleep S  shot PATH  scroll DY
"""
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


def scroll(dy):
    e = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitPixel, 1, int(dy))
    _post(e)


def shot(path):
    subprocess.run(["screencapture", "-x", path], capture_output=True)


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
        elif op == "sleep":
            time.sleep(float(arg))
        elif op == "shot":
            shot(arg)
        elif op == "scroll":
            scroll(arg)
        print(f"  · {cmd}")


if __name__ == "__main__":
    if sys.argv[1] == "size":
        size()
    elif sys.argv[1] == "do":
        run_seq(sys.argv[2])
