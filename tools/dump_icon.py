# -*- coding: utf-8 -*-
"""把窗口的 class icon / WM_GETICON 取出来存成 PNG，用来确认任务栏到底显示什么。"""
import ctypes
import os
import shutil
import subprocess
import sys
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import pngutil

TEST = os.path.join(ROOT, "_icontest")
shutil.rmtree(TEST, ignore_errors=True)
os.makedirs(TEST)

if len(sys.argv) > 1 and sys.argv[1] == "--src":
    # 源码模式：写个 runner，把数据目录指到临时目录再跑
    # 注意：不能用 taskkill python.exe —— 那会把自己也杀掉
    runner = os.path.join(ROOT, "tools", "_icon_src.py")
    with open(runner, "w", encoding="utf-8") as f:
        f.write(
            "import sys, os\n"
            "sys.path.insert(0, %r)\n"
            "import assets as A\n"
            "A.app_dir = lambda: %r\n"
            "A.data_path = lambda: os.path.join(%r, 'apps_data.json')\n"
            "A.icon_dir = lambda: os.path.join(%r, 'icons')\n"
            "import main as M\n"
            "app = M.Launcher()\n"
            "app.run()\n" % (os.path.join(ROOT, "src"), TEST, TEST, TEST))
    cmd = [sys.executable, runner]
    cmd_str = [sys.executable, runner]
    IMAGE_NAME = None
    print("模式: 源码")
else:
    SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "程序收纳盒.exe")
    EXE = os.path.join(TEST, os.path.basename(SRC))
    shutil.copy2(SRC, EXE)
    cmd = [EXE]
    cmd_str = cmd
    IMAGE_NAME = os.path.splitext(os.path.basename(SRC))[0]
    print("模式: exe =", os.path.basename(SRC))

u = ctypes.windll.user32
u.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
u.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
u.IsWindowVisible.argtypes = [ctypes.c_void_p]
u.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
u.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                           wintypes.LPARAM]
u.SendMessageW.restype = ctypes.c_ssize_t
u.GetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
u.GetClassLongPtrW.restype = ctypes.c_ssize_t
u.DestroyIcon.argtypes = [wintypes.HICON]
CB = ctypes.WINFUNCTYPE(wintypes.BOOL, ctypes.c_void_p, ctypes.c_ssize_t)
WM_GETICON, ICON_BIG, ICON_SMALL = 0x007F, 1, 0
GCLP_HICON, GCLP_HICONSM = -14, -34

p = subprocess.Popen(cmd, cwd=TEST)
time.sleep(6)
tops = []


def cb(h, _):
    if u.IsWindowVisible(h):
        cn = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(h, cn, 256)
        n = u.GetWindowTextLengthW(h)
        t = ""
        if n:
            b = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(h, b, n + 1)
            t = b.value
        if cn.value == "TkTopLevel" and t == "程序收纳盒":
            tops.append(int(h))
    return True


u.EnumWindows(CB(cb), 0)
print("outer window:", [hex(x) for x in tops])


def save_hicon(hicon, path, size=None):
    """HICON -> PNG。"""
    if not hicon:
        print("  (no hicon)")
        return
    import iconutil
    got = iconutil._hicon_to_rgba(hicon)
    if not got:
        print("  (convert failed)")
        return
    w, h, data = got
    pngutil.write_png(path, w, h, data)
    print("  saved", path, (w, h))


for h in tops:
    for name, msg in (("class_big", GCLP_HICON), ("class_small", GCLP_HICONSM)):
        hi = u.GetClassLongPtrW(ctypes.c_void_p(h), msg)
        print(name, hex(hi))
        save_hicon(hi, os.path.join(ROOT, "_icon_%s.png" % name), 48)
    for name, ic in (("geticon_big", ICON_BIG), ("geticon_small", ICON_SMALL)):
        hi = u.SendMessageW(ctypes.c_void_p(h), WM_GETICON, ic, 0)
        print(name, hex(hi))
        save_hicon(hi, os.path.join(ROOT, "_icon_%s.png" % name), 48)

if IMAGE_NAME:
    subprocess.run(["taskkill", "/F", "/IM", IMAGE_NAME + ".exe"],
                   capture_output=True)
p.kill()
if os.path.exists(os.path.join(ROOT, "tools", "_icon_src.py")):
    os.remove(os.path.join(ROOT, "tools", "_icon_src.py"))
