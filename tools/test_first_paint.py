# -*- coding: utf-8 -*-
"""首帧绘制回归：exe 启动后窗口必须「一出现就是画好的」，不能是黑屏。

判定：窗口出现后，每一帧的近黑像素占比都 < 15%（黑屏时基本 > 90%）。
用法： python tools/test_first_paint.py [exe路径]
"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

from PIL import ImageGrab

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "程序收纳盒.exe")

u = ctypes.windll.user32
u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
u.FindWindowW.restype = ctypes.c_void_p
u.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]


def near_black_ratio(img):
    px = list(img.getdata())
    dark = sum(1 for c in px if sum(c) < 120)
    return 100.0 * dark / max(1, len(px))


proc = subprocess.Popen([EXE])
print("started", EXE, "pid", proc.pid, flush=True)

t0 = time.time()
seen = False
first_t = None
worst = 0.0
frames = []
try:
    while time.time() - t0 < 25:
        time.sleep(0.2)
        hwnd = u.FindWindowW(None, "程序收纳盒")
        if not hwnd:
            continue
        rect = wintypes.RECT()
        u.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
        box = (rect.left, rect.top, rect.right, rect.bottom)
        if box[2] - box[0] < 200:
            continue
        img = ImageGrab.grab(bbox=box).convert("RGB")
        r = near_black_ratio(img)
        dt = time.time() - t0
        if not seen:
            seen = True
            first_t = dt
        frames.append((dt, r))
        worst = max(worst, r)
        if dt > first_t + 4.0:
            break
finally:
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                   capture_output=True)

for dt, r in frames:
    print("  t=%5.2fs  near-black=%5.1f%%" % (dt, r))
print("window appeared at %.2fs, worst near-black=%.1f%%" % (first_t or -1, worst))
ok = seen and worst < 15.0
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
