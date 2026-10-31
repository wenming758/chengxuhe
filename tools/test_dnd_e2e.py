# -*- coding: utf-8 -*-
"""复现 2：完整 Launcher + dnd + 发送 WM_DROPFILES，把输出写文件防缓冲丢失。"""
import ctypes
import os
import shutil
import sys
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

LOG = open(os.path.join(ROOT, "_dndlog.txt"), "w", encoding="utf-8")


def log(*a):
    s = " ".join(str(x) for x in a)
    LOG.write(s + "\n")
    LOG.flush()


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WM_DROPFILES = 0x0233
GMEM_MOVEABLE = 0x0002
GMEM_ZEROINIT = 0x0040

kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL


def make_hdrop(paths):
    class DF(ctypes.Structure):
        _fields_ = [("pFiles", wintypes.DWORD), ("pt", wintypes.POINT),
                    ("fNC", wintypes.BOOL), ("fWide", wintypes.BOOL)]

    blob = ""
    for p in paths:
        blob += p + "\0"
    data = blob.encode("utf-16-le") + b"\0\0"
    hdr = DF()
    hdr.pt.x, hdr.pt.y = 60, 60
    hdr.fNC = 0
    hdr.fWide = 1
    hdr.pFiles = ctypes.sizeof(DF)
    size = ctypes.sizeof(DF) + len(data)
    h = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, size)
    ptr = kernel32.GlobalLock(h)
    ctypes.memmove(ptr, ctypes.byref(hdr), ctypes.sizeof(hdr))
    ctypes.memmove(ptr + ctypes.sizeof(hdr), data, len(data))
    kernel32.GlobalUnlock(h)
    return h


import assets as A
import main as M

tmp = os.path.join(ROOT, "_dndtest")
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
hwnd = app._real_toplevel_hwnd()
log("init ok, dnd_ok =", app.dnd_ok)
log("winfo_id =", hex(winfo), "真顶层 =", hex(hwnd),
    "不同 =", hwnd != winfo)

# 直接观察回调是否被调用（绕过 add_paths）
called = {"n": 0}
orig = app._on_drop


def spy(files):
    called["n"] += 1
    log(">>> _on_drop 被调用, files =", files)
    try:
        orig(files)
        log("    add_paths 返回正常")
    except Exception as e:
        log("    add_paths 异常:", repr(e))


app._dnd.on_files = spy

targets = [
    os.path.join(os.environ["WINDIR"], "System32", "notepad.exe"),
    os.path.join(os.environ["WINDIR"], "System32", "calc.exe"),
]
h = make_hdrop(targets)
user32.PostMessageW(hwnd, WM_DROPFILES, h, 0)
log("已发送 WM_DROPFILES")


def check():
    log("check: called =", called["n"], "items =", len(app.store.items),
        "cards =", len(app.cards))
    app._quit()          # 走真实关闭路径：quit + detach


app.root.after(600, check)
app.root.after(8000, lambda: app.root.destroy())
try:
    app.run()
except Exception as e:
    log("run 异常:", repr(e))

import faulthandler
faulthandler.dump_traceback_later(20, exit=True,
                                  file=open(os.path.join(ROOT, "_dndlog.txt"),
                                            "a", encoding="utf-8"))

log("=== 结束 ===")
LOG.close()
shutil.rmtree(tmp, ignore_errors=True)
LOG = open(os.path.join(ROOT, "_dndlog.txt"), "a", encoding="utf-8")
log("rmtree 完成，进程即将退出")
LOG.close()
