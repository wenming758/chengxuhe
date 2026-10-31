# -*- coding: utf-8 -*-
"""验证多窗口挂钩：分别向 winfo_id（内部子窗口）和 TkTopLevel（真顶层）投递。

真实拖拽落在 TkTopLevel 上，但为了稳妥，
我们两处都挂 —— 这个测试确认任一处都能收到。
"""
import ctypes
import os
import shutil
import sys
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

LOG = open(os.path.join(ROOT, "_dndlog2.txt"), "w", encoding="utf-8")


def log(*a):
    LOG.write(" ".join(str(x) for x in a) + "\n")
    LOG.flush()


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
user32.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, ctypes.c_void_p, ctypes.c_ssize_t)


def find_own_toplevels(pid):
    got = []

    def cb(h, _):
        p = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(h):
            cn = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(h, cn, 256)
            if cn.value == "TkTopLevel":
                got.append(int(h))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return got


def make_hdrop(paths):
    class DF(ctypes.Structure):
        _fields_ = [("pFiles", wintypes.DWORD), ("pt", wintypes.POINT),
                    ("fNC", wintypes.BOOL), ("fWide", wintypes.BOOL)]
    blob = "".join(p + "\0" for p in paths)
    data = blob.encode("utf-16-le") + b"\0\0"
    hdr = DF()
    hdr.pt.x, hdr.pt.y = 60, 60
    hdr.fWide = 1
    hdr.pFiles = ctypes.sizeof(DF)
    size = ctypes.sizeof(DF) + len(data)
    h = kernel32.GlobalAlloc(2 | 64, size)
    ptr = kernel32.GlobalLock(h)
    ctypes.memmove(ptr, ctypes.byref(hdr), ctypes.sizeof(hdr))
    ctypes.memmove(ptr + ctypes.sizeof(hdr), data, len(data))
    kernel32.GlobalUnlock(h)
    return h


import assets as A
import main as M
import dnd

tmp = os.path.join(ROOT, "_dndtest2")
if os.path.isdir(tmp):
    shutil.rmtree(tmp)
os.makedirs(tmp)
A.app_dir = lambda: tmp
A.data_path = lambda: os.path.join(tmp, "apps_data.json")
A.icon_dir = lambda: os.path.join(tmp, "icons")

app = M.Launcher()
app.root.geometry("900x640")
app.root.update()
winfo = app.root.winfo_id()
time.sleep(0.2)
tops = find_own_toplevels(os.getpid())

log("dnd_ok =", app.dnd_ok)
log("挂了", len(app._dnd._win), "个窗口")
log("winfo_id =", hex(winfo), "在挂钩里 =", winfo in app._dnd._win)
log("TkTopLevel =", [hex(t) for t in tops],
    "在挂钩里 =", [(hex(t), t in app._dnd._win) for t in tops])
log("find_app_toplevels 找到:", [hex(x) for x in dnd.find_app_toplevels(winfo,
                                                        app.root.title())][:6])

targets = [os.path.join(os.environ["WINDIR"], "System32", "notepad.exe"),
           os.path.join(os.environ["WINDIR"], "System32", "calc.exe")]

# 1) 投给真顶层（模拟真实拖拽）
if tops:
    user32.PostMessageW(tops[0], 0x0233, make_hdrop(targets), 0)
    log("已投递给 TkTopLevel", hex(tops[0]))
else:
    log("!! 没找到 TkTopLevel")


def check():
    log("items =", len(app.store.items), "cards =", len(app.cards),
        "names =", [i.get("name") for i in app.store.items])
    app._quit()


app.root.after(900, check)
try:
    app.run()
except Exception as e:
    log("run 异常:", repr(e))
log("=== 结束 ===")
LOG.close()
shutil.rmtree(tmp, ignore_errors=True)
LOG = open(os.path.join(ROOT, "_dndlog2.txt"), "a", encoding="utf-8")
log("进程即将退出")
LOG.close()