# -*- coding: utf-8 -*-
"""纯 ctypes 抓全屏截图（调试用），输出 PNG。"""
import ctypes
import ctypes.wintypes as wt
import ctypes.wintypes as wintypes
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import pngutil

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

user32.GetDC.argtypes = [wt.HWND]
user32.GetDC.restype = wt.HDC
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
gdi32.SelectObject.argtypes = [wt.HDC, wt.HANDLE]
gdi32.SelectObject.restype = wt.HANDLE
gdi32.BitBlt.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         wt.HDC, ctypes.c_int, ctypes.c_int, wt.DWORD]
gdi32.DeleteObject.argtypes = [wt.HANDLE]
gdi32.DeleteDC.argtypes = [wt.HDC]
gdi32.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, ctypes.c_uint, ctypes.c_uint,
                            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
gdi32.GetDIBits.restype = ctypes.c_int


class BMIH(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


def capture(path, x=0, y=0, w=None, h=None):
    w = w or user32.GetSystemMetrics(0)
    h = h or user32.GetSystemMetrics(1)
    hdc = user32.GetDC(None)
    mem = gdi32.CreateCompatibleDC(hdc)
    hbmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, hbmp)
    SRCCOPY = 0x00CC0020
    gdi32.BitBlt(mem, 0, 0, w, h, hdc, x, y, SRCCOPY)

    bi = BMIH()
    bi.biSize = ctypes.sizeof(BMIH)
    bi.biWidth = w
    bi.biHeight = -h
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, hbmp, 0, h, buf, ctypes.byref(bi), 0)
    raw = bytearray(buf.raw)
    rgba = bytearray(w * h * 4)
    for i in range(0, len(raw), 4):
        rgba[i] = raw[i + 2]
        rgba[i + 1] = raw[i + 1]
        rgba[i + 2] = raw[i]
        rgba[i + 3] = 255
    pngutil.write_png(path, w, h, bytes(rgba))

    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(None, hdc)
    return w, h


def find_window(title):
    hwnd = user32.FindWindowW(None, title)
    if hwnd:
        return hwnd
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, l):
        n = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(h, n, 512)
        if title in n.value:
            found.append(h)
        return True
    user32.EnumWindows(cb, 0)
    return found[0] if found else 0


def activate(title):
    hwnd = find_window(title)
    if not hwnd:
        print("窗口未找到:", title)
        return 0
    user32.ShowWindow(hwnd, 9)          # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    return hwnd


def capture_window(title, path):
    hwnd = activate(title)
    if not hwnd:
        return None
    import time
    time.sleep(1.2)
    rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    capture(path, rect.left, rect.top, w, h)
    return w, h


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "_shot.png"
    title = sys.argv[2] if len(sys.argv) > 2 else ""
    if title:
        r = capture_window(title, out)
        print("saved", r, out)
    else:
        print("saved", capture(out), out)
