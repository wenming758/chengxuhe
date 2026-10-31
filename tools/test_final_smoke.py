# -*- coding: utf-8 -*-
"""最终交付冒烟测试：启动 exe → 校验任务栏图标（类图标非空）→ 干净退出。"""
import ctypes, os, subprocess, sys, time
from ctypes import wintypes

EXE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "程序收纳盒.exe")
EXE = os.path.abspath(EXE)
u = ctypes.windll.user32
k = ctypes.windll.kernel32
u.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
u.IsWindowVisible.argtypes = [wintypes.HWND]
u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u.GetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

GCLP_HICON = -14
GCLP_HICONSM = -34


def pids_by_image(name):
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


def main():
    p = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
    child = None
    t0 = time.time()
    while time.time() - t0 < 40:
        for pid in pids_by_image("程序收纳盒.exe"):
            if toplevels_of_pid(pid) and pid != p.pid:
                child = pid
                break
        if child:
            break
        time.sleep(0.5)
    if not child:
        print(">>> FAIL 没找到主窗口"); p.kill(); return 1
    time.sleep(2.5)         # 等 _ensure_taskbar_icon 跑完
    main_hwnd = toplevels_of_pid(child)[0][0]
    big = u.GetClassLongPtrW(wintypes.HWND(main_hwnd), GCLP_HICON)
    sml = u.GetClassLongPtrW(wintypes.HWND(main_hwnd), GCLP_HICONSM)
    print(">>> 主窗口 hwnd=0x%x" % main_hwnd)
    print(">>> 类图标 big=0x%x small=0x%x → %s" %
          (big & 0xFFFFFFFF, sml & 0xFFFFFFFF,
           "PASS（任务栏/Alt+Tab 用用户图标）" if (big and sml) else "FAIL"))
    # 干净退出
    u.PostMessageW(wintypes.HWND(main_hwnd), 0x0010, 0, 0)
    t1 = time.time()
    code = None
    while time.time() - t1 < 80:
        code = p.poll()
        if code is not None:
            break
        time.sleep(1.0)
    print(">>> 退出码=%s（子进程立即退出；父进程是 bootloader 自清理，最多等 ~60s）" % code)
    if code is None:
        p.kill()
    ok = bool(big) and bool(sml)
    print(">>> 总体: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
