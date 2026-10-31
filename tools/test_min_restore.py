# -*- coding: utf-8 -*-
"""最小化再恢复回归：恢复后窗口必须还是画好的，不能一片黑。

用法： python tools/test_min_restore.py [exe路径]
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
u.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
u.ShowWindow.restype = ctypes.c_int
u.IsIconic.argtypes = [ctypes.c_void_p]
u.IsIconic.restype = ctypes.c_int

SW_MINIMIZE, SW_RESTORE = 6, 9
LIMIT = 15.0     # 近黑像素占比阈值


def ratio():
    hwnd = u.FindWindowW(None, "程序收纳盒")
    if not hwnd:
        return None
    rect = wintypes.RECT()
    u.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w < 200 or h < 150:
        return None
    img = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right,
                               rect.bottom)).convert("RGB")
    px = list(img.getdata())
    return 100.0 * sum(1 for c in px if sum(c) < 120) / len(px)


proc = subprocess.Popen([EXE])
print("started", EXE, "pid", proc.pid, flush=True)

t0 = time.time()
hwnd = None
while time.time() - t0 < 20 and not hwnd:
    time.sleep(0.2)
    hwnd = u.FindWindowW(None, "程序收纳盒")
if not hwnd:
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                   capture_output=True)
    print("RESULT: FAIL（窗口没出现）")
    sys.exit(1)

time.sleep(2.0)                      # 等首帧稳下来
rows = []
try:
    r = ratio()
    rows.append(("启动后", r))
    for i in (1, 2):
        u.ShowWindow(ctypes.c_void_p(hwnd), SW_MINIMIZE)
        time.sleep(1.2)
        u.ShowWindow(ctypes.c_void_p(hwnd), SW_RESTORE)
        time.sleep(1.6)
        rows.append(("第 %d 次恢复" % i, ratio()))
finally:
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                   capture_output=True)

for k, v in rows:
    print("  %-12s near-black = %5.1f%%" % (k, v if v is not None else -1))
worst = max(v for _, v in rows if v is not None)
ok = all(v is None or v < LIMIT for _, v in rows) and worst >= 0
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
