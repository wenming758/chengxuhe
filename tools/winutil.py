# -*- coding: utf-8 -*-
"""Windows 自动化测试公共工具：真实鼠标点击、进程/窗口枚举、截屏。
供 tools/ 下的回归测试脚本复用。"""
import ctypes, os, sys, time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import pngutil

u = ctypes.windll.user32
k = ctypes.windll.kernel32
gdi = ctypes.windll.gdi32

u.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
u.IsWindowVisible.argtypes = [wintypes.HWND]
u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u.SetCursorPos.argtypes = [wintypes.LONG, wintypes.LONG]
u.WindowFromPoint.argtypes = [wintypes.POINT]
u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND,
                           ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                           ctypes.c_uint]
u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]


class MI(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p)]


class II(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("mi", MI)]


class BMIH(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClsUsed", wintypes.DWORD),
                ("biClsImportant", wintypes.DWORD)]


def snapshot(x, y, w, h, path):
    """截取屏幕矩形并存成 PNG，同时返回 (RGBA bytes, w, h)"""
    # gdi32/user32 是全进程共享的 cdll 对象，声明一旦被别的模块
    # （如 src/iconutil）覆盖就会 AttributeError/ArgumentError/OverflowError。
    # 凡本函数用到的 API 一律在调用时点显式声明（c_void_p / HANDLE 化），
    # 64 位句柄不会被截断成 32 位 int。GetDIBits 用 c_void_p 是因为
    # iconutil 把它声明成了 POINTER(BITMAPINFO)，byref(bi) 过不了它的检查，
    # 而 c_void_p 对 byref 结果和结构体实例都接受，是两边都安全的超集。
    u.GetDC.argtypes = [wintypes.HWND]
    u.GetDC.restype = wintypes.HDC
    u.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.DeleteDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi.SelectObject.restype = wintypes.HGDIOBJ
    gdi.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int,
                           ctypes.c_int, ctypes.c_int, wintypes.HDC,
                           ctypes.c_int, ctypes.c_int, wintypes.DWORD]
    gdi.DeleteObject.argtypes = [wintypes.HANDLE]
    hdc = u.GetDC(None)
    mem = gdi.CreateCompatibleDC(hdc)
    bmp = gdi.CreateCompatibleBitmap(hdc, w, h)
    gdi.SelectObject(mem, bmp)
    gdi.BitBlt(mem, 0, 0, w, h, hdc, x, y, 0x00CC0020)
    bi = BMIH()
    bi.biSize = ctypes.sizeof(BMIH)
    bi.biWidth = w
    bi.biHeight = -h
    bi.biPlanes = 1
    bi.biBitCount = 32
    buf = ctypes.create_string_buffer(w * h * 4)
    # 见上方注释：c_void_p 是 iconutil 的 POINTER(BITMAPINFO) 与本函数
    # byref(BMIH) 两边都接受的超集。
    gdi.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, ctypes.c_uint,
                              ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.c_uint]
    gdi.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    raw = bytearray(buf.raw)
    rgba = bytearray(w * h * 4)
    for i in range(0, len(raw), 4):
        rgba[i] = raw[i + 2]
        rgba[i + 1] = raw[i + 1]
        rgba[i + 2] = raw[i]
        rgba[i + 3] = 255
    pngutil.write_png(path, w, h, bytes(rgba))
    gdi.DeleteObject(bmp)
    gdi.DeleteDC(mem)
    u.ReleaseDC(None, hdc)
    return bytes(rgba), w, h


def real_click(x, y):
    """真实鼠标点击（SetCursorPos + SendInput）"""
    SW, SH = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    ax, ay = int(x * 65535 / (SW - 1)), int(y * 65535 / (SH - 1))
    for flags, dx, dy in ((0x8002, 0x40000, 0x40000),
                          (0x8000 | 0x0002, ax, ay),
                          (0x0002, ax, ay),
                          (0x0004, ax, ay)):
        ii = II(); ii.type = 0; ii.mi.dx = dx; ii.mi.dy = dy; ii.mi.dwFlags = flags
        u.SendInput(1, ctypes.byref(ii), ctypes.sizeof(ii))
        time.sleep(0.04)


def pids_by_image(name):
    """按映像名枚举进程 PID"""
    class PE(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_char * 260)]
    pe = PE(); pe.dwSize = ctypes.sizeof(PE)
    snap = k.CreateToolhelp32Snapshot(0x2, 0)
    out = []
    ok = k.Process32First(snap, ctypes.byref(pe))
    while ok:
        if pe.szExeFile.decode("mbcs", "ignore").lower() == name.lower():
            out.append(pe.th32ProcessID)
        ok = k.Process32Next(snap, ctypes.byref(pe))
    k.CloseHandle(snap)
    return out


def toplevels_of_pid(pid):
    """某进程的所有可见顶层窗口 [(hwnd, class), ...]"""
    hits = []
    def cb(h, _):
        p = wintypes.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u.IsWindowVisible(h):
            cls = ctypes.create_unicode_buffer(256)
            u.GetClassNameW(h, cls, 256)
            hits.append((int(h), cls.value))
        return True
    CB = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    u.EnumWindows(CB(cb), 0)
    return hits


def rect_of(hwnd):
    r = wintypes.RECT()
    u.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def pid_of(hwnd):
    p = wintypes.DWORD()
    u.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(p))
    return p.value


def point_belongs_to(hwnd_owner, x, y):
    """(x,y) 处最顶层的窗口是否属于 hwnd_owner 同一进程
    （Tk 界面由 TkTopLevel + TkChild 两个窗口组成，都算本进程）"""
    hit = u.WindowFromPoint(wintypes.POINT(x, y))
    return hit, pid_of(hit) == pid_of(hwnd_owner)


def hide_console():
    """把当前控制台窗口最小化，避免遮挡自动化点击"""
    con = k.GetConsoleWindow()
    if con:
        u.ShowWindow(con, 6)     # SW_MINIMIZE
    return bool(con)
