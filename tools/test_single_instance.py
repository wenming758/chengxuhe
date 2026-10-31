# -*- coding: utf-8 -*-
"""单实例端到端测试：
1) 启动 exe  → 应出现 1 个进程、1 个主窗口
2) 再启动一次 → 第二个进程应立刻退出；窗口数仍为 1
3) 清理
"""
import ctypes, os, subprocess, sys, time
from ctypes import wintypes

EXE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "..", "程序收纳盒.exe"))
u = ctypes.windll.user32
k = ctypes.windll.kernel32
u.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
u.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                       ctypes.POINTER(wintypes.DWORD)]
u.IsWindowVisible.argtypes = [wintypes.HWND]
u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                           wintypes.LPARAM]


def pids_by_image(name):
    class PE(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD),
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


def wait_for_window(proc, timeout=40):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for pid in pids_by_image("程序收纳盒.exe"):
            if pid != proc.pid and toplevels_of_pid(pid):
                return pid
        time.sleep(0.5)
    return None


def visible_windows():
    """当前所有属于本 exe 进程的可见顶层窗口。"""
    out = []
    for pid in pids_by_image("程序收纳盒.exe"):
        out.extend(toplevels_of_pid(pid))
    return out


def main():
    fails = []

    p1 = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
    pid1 = wait_for_window(p1, 45)
    if not pid1:
        print(">>> FAIL 第一个实例没起窗口")
        p1.kill()
        return 1
    print(">>> 实例1 pid=%s 窗口数=%d" % (pid1, len(visible_windows())))
    time.sleep(2.0)
    n1 = len(visible_windows())
    print(">>> 启动 1 次后可见主窗口数 = %d（应为 1）" % n1)
    if n1 != 1:
        fails.append("首个实例窗口数 != 1")

    # 第二次点击
    p2 = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
    time.sleep(6.0)
    n2 = len(visible_windows())
    print(">>> 第二次启动后：可见窗口数 = %d（应为 1）" % n2)
    if n2 != 1:
        fails.append("第二次启动后窗口数 != 1（多开了）")

    # 第三次也试一下
    p3 = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
    time.sleep(6.0)
    n3 = len(visible_windows())
    print(">>> 第三次启动后：可见窗口数 = %d（应为 1）" % n3)
    if n3 != 1:
        fails.append("第三次启动后窗口数 != 1")

    # 第二次/第三次的「真正干活的子进程」应立即退出。
    # 注意：PyInstaller 单文件模式的父 bootloader 会拖尾最长 ~90s 才收尾，
    # 这是已知行为（本程序文档里也写了），不能当成"多开"。这里只校验：
    #   (a) 没有多出窗口；(b) 多出来的进程没有窗口（即只是 bootloader 残留）。
    stray = [pid for pid, _ in [(x, None) for x in pids_by_image("程序收纳盒.exe")]
             if toplevels_of_pid(pid)]
    print(">>> 有窗口的进程数 = %d（应为 1，即始终只有那一个真实例）" % len(stray))
    if len(stray) != 1:
        fails.append("有窗口的进程数 != 1")

    # 收尾：关掉唯一那个实例
    wins = visible_windows()
    if wins:
        u.PostMessageW(wintypes.HWND(wins[0][0]), 0x0010, 0, 0)
    for p in (p1, p2, p3):
        try:
            if p.poll() is None:
                p.terminate()
        except Exception:
            pass

    print(">>> 总体: %s" % ("PASS" if not fails else "FAIL -> " + "; ".join(fails)))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
