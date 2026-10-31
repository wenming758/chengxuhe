# -*- coding: utf-8 -*-
"""真·端到端测试：直接拖进打包好的 exe

流程：
  1. 把 exe 拷到独立目录（不污染交付数据）
  2. 启动 exe
  3. 用 EnumWindows 找到标题为「程序收纳盒」的顶层窗口
  4. 给它 PostMessage WM_DROPFILES（notepad.exe + calc.exe）
  5. 读 _exetest/apps_data.json，确认两个程序已被收录
  6. 发 WM_CLOSE，确认进程能干净退出
"""
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTDIR = os.path.join(ROOT, "_exetest")
SRC_EXE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "程序收纳盒.exe")
LOG = open(os.path.join(ROOT, "_exetest_log.txt"), "w", encoding="utf-8")


def log(*a):
    LOG.write("[%.2f] %s\n" % (time.time() % 1000, " ".join(str(x) for x in a)))
    LOG.flush()


# ------------------------------ 准备
if os.path.isdir(TESTDIR):
    shutil.rmtree(TESTDIR, ignore_errors=True)
os.makedirs(TESTDIR)
EXE = os.path.join(TESTDIR, "程序收纳盒.exe")
shutil.copy2(SRC_EXE, EXE)
log("已复制 exe 到", TESTDIR, "大小", os.path.getsize(EXE))

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WM_DROPFILES = 0x0233
GMEM_MOVEABLE = 0x0002
GMEM_ZEROINIT = 0x0040
WM_CLOSE = 0x0010

kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, ctypes.c_void_p, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, ctypes.c_void_p, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                 ctypes.c_void_p)
TARGET = "程序收纳盒"


def find_window(pid):
    """按 PID 精确定位属于本进程的 TkTopLevel 窗口。

    注意：不能只按标题找 —— 桌面上可能残留别的同名窗口，
    而且 Tk 的顶层窗口类名是 TkTopLevel（winfo_id 只是内部子窗口）。
    """
    got = []

    def cb(h, _):
        try:
            owner = ctypes.c_ulong(0)
            user32.GetWindowThreadProcessId(h, ctypes.byref(owner))
            if owner.value != pid or not user32.IsWindowVisible(h):
                return True
            n = user32.GetWindowTextLengthW(h)
            title = ""
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(h, buf, n + 1)
                title = buf.value
            cn = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(h, cn, 256)
            got.append((int(h), title, cn.value))
        except Exception:
            pass
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    log("  pid %d 的窗口: %s" % (pid, [(hex(h), t, c) for h, t, c in got]))
    for h, t, c in got:
        if c == "TkTopLevel":
            return h
    for h, t, c in got:
        if t == TARGET:
            return h
    return got[0][0] if got else 0


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
    h = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, size)
    ptr = kernel32.GlobalLock(h)
    ctypes.memmove(ptr, ctypes.byref(hdr), ctypes.sizeof(hdr))
    ctypes.memmove(ptr + ctypes.sizeof(hdr), data, len(data))
    kernel32.GlobalUnlock(h)
    return h


# ------------------------------ 启动
# PyInstaller onefile 会起两个同名进程：
#   父进程 = bootloader，子进程 = 真正跑 Python 的（窗口属于它）
# 所以先枚举同名进程，再从中挑出真正有窗口的那个。
IMAGE = os.path.splitext(os.path.basename(EXE))[0]

TH32CS_SNAPPROCESS = 0x00000002
kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


def pids_by_imagename():
    """枚举所有映像名等于 exe 名的进程 pid。"""
    out = []
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == wintypes.HANDLE(-1).value:
        return out
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        if not kernel32.Process32FirstW(snap, ctypes.byref(e)):
            return out
        while True:
            name = e.szExeFile.lower()
            if name == (IMAGE + ".exe").lower():
                out.append(int(e.th32ProcessID))
            if not kernel32.Process32NextW(snap, ctypes.byref(e)):
                break
    finally:
        kernel32.CloseHandle(snap)
    return out


proc = subprocess.Popen([EXE], cwd=TESTDIR)
log("exe 已启动 pid =", proc.pid)

hwnd = 0
for i in range(80):
    for pid in pids_by_imagename() or [proc.pid]:
        hwnd = find_window(pid)
        if hwnd:
            break
    if hwnd:
        break
    if proc.poll() is not None and not pids_by_imagename():
        break
    time.sleep(0.5)
if not hwnd:
    log("!! 找不到窗口，终止")
    proc.kill()
    LOG.close()
    sys.exit(2)
log("找到窗口 hwnd =", hex(hwnd))

time.sleep(2.0)     # 等界面初始化完
base_json = os.path.join(TESTDIR, "apps_data.json")
log("启动后已有数据文件:", os.path.exists(base_json))

targets = [os.path.join(os.environ["WINDIR"], "System32", "notepad.exe"),
           os.path.join(os.environ["WINDIR"], "System32", "calc.exe")]
ok = user32.PostMessageW(hwnd, WM_DROPFILES, make_hdrop(targets), 0)
log("PostMessage WM_DROPFILES =", ok)
time.sleep(3.0)

# ------------------------------ 校验数据
data = None
if os.path.exists(base_json):
    try:
        with open(base_json, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log("!! 读数据失败:", repr(e))
if data is None:
    log("!! 没有生成 apps_data.json")
else:
    paths = [it.get("path", "").lower() for it in data.get("items", [])]
    names = [it.get("name", "") for it in data.get("items", [])]
    log("items =", len(paths), "names =", names)
    hit = sum(1 for t in targets if t.lower() in paths)
    log("目标程序命中 =", hit, "/", len(targets))
    if hit == len(targets):
        log(">>> 拖拽添加成功")

icons = os.path.join(TESTDIR, "icons")
log("icons 目录文件数 =", len(os.listdir(icons)) if os.path.isdir(icons) else 0)

# ------------------------------ 关闭
owner = ctypes.c_ulong(0)
user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
log("窗口所属 pid =", owner.value)
user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
log("已发送 WM_CLOSE ->", hex(hwnd))
for i in range(60):
    left = pids_by_imagename()
    if not left:
        log(">>> 所有同名进程已退出（关闭正常）")
        break
    time.sleep(0.5)
else:
    log("!! 30 秒后仍有进程:", pids_by_imagename(), "强制结束")
    proc.kill()
    subprocess.run(["taskkill", "/F", "/IM", IMAGE + ".exe"],
                   capture_output=True)

LOG.close()
