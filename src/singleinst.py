# -*- coding: utf-8 -*-
"""
单实例守卫（Windows）
=====================
目标：不管双击 / 快捷方式点多少次「程序收纳盒」，全系统始终只跑一个窗口。

做法（三层，互不依赖对方成功）：
1. 命名互斥体（Global\\<hash>）—— 主判据。
   已经有人持有 → 说明实例已存在，广播一条「请显身」消息并自杀。
2. 广播消息（RegisterWindowMessage + HWND_BROADCAST）——
   让已有实例把窗口前置、去最小化、抢焦点。
3. 兜底兜底：若互斥体说已存在但前台实例没响应（比如卡死），
   仍然退出，避免弹出第二个窗口。

为什么用 Global\\ 前缀：覆盖多用户会话/多桌面场景（同一台机器只跑一个）。
注意互斥体名字里不能有反斜杠之外的特殊字符，这里用十六进制摘要。
"""
import ctypes
import hashlib
import os
import sys
from ctypes import wintypes

# ------------------------------------------------------------------ 常量
ERROR_ALREADY_EXISTS = 183
HWND_BROADCAST = 0xFFFF
WM_COPYDATA = 0x004A
SW_RESTORE = 9
SW_SHOW = 5

# 自定义广播消息体（放在 COPYDATASTRUCT.lpData 里当"暗号"）
_TAG = "程序收纳盒".encode("utf-8") + b"\0activate\0"


class COPYDATASTRUCT(ctypes.Structure):
    _fields_ = [
        ("dwData", ctypes.c_void_p),
        ("cbData", wintypes.DWORD),
        ("lpData", ctypes.c_void_p),
    ]


def _kernel32():
    return ctypes.windll.kernel32


def _force_exit():
    """结束当前进程。

    PyInstaller 单文件模式下，『子进程』（真正跑 Python 的那个）退出后，
    『父进程』bootloader 会自动收尾并退出 —— 前提是子进程**正常退出**。
    所以这里优先用干净的 sys.exit / os._exit，只有万不得已才硬杀
    （硬杀会让 bootloader 父进程判断异常、反而赖着不走）。
    """
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    # 干净退出：让 onefile bootloader 正常收尾
    try:
        os._exit(0)
    except Exception:
        pass


def _hard_kill():
    """极端兜底：干净退出也失败时才用。"""
    try:
        k = _kernel32()
        k.GetCurrentProcess.restype = ctypes.c_void_p
        k.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        k.TerminateProcess(k.GetCurrentProcess(), 0)
    except Exception:
        pass
    try:
        os._exit(0)
    except Exception:
        raise SystemExit(0)


def _mutex_name():
    """按 exe 路径生成稳定且唯一的互斥体名。

    用 exe 所在目录做摘要：同一个 exe（含被拷到多处）共用一把锁；
    不同程序即使同名也不互相阻塞。
    """
    try:
        import assets as A
        base = A.exe_dir()
    except Exception:
        base = os.path.dirname(os.path.abspath(sys.executable))
    h = hashlib.md5(base.lower().encode("utf-8", "ignore")).hexdigest()[:20]
    return "Global\\程序收纳盒_single_%s" % h


def message_id():
    """注册（或取回）自定义广播消息 id。

    RegisterWindowMessageW 对同名消息在全系统返回同一个 id，
    所以两个实例各自调用也能对上。
    """
    u = ctypes.windll.user32
    u.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
    u.RegisterWindowMessageW.restype = wintypes.UINT
    return u.RegisterWindowMessageW("程序收纳盒_activate_v1")


# ================================================================== 守卫
class SingleInstance(object):
    """持有 = 本进程是唯一的那个；失败 = 已有实例在跑。"""

    def __init__(self, name=None):
        self.name = name or _mutex_name()
        self._handle = None
        self._msg = None
        self._activated = False

    # -------------------------------------------------- 尝试持锁
    def acquire(self):
        k = _kernel32()
        k.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL,
                                   wintypes.LPCWSTR]
        k.CreateMutexW.restype = ctypes.c_void_p
        h = k.CreateMutexW(None, False, self.name)
        err = k.GetLastError()
        if not h:
            return True                     # 拿不到锁也别拦着自己启动
        if err == ERROR_ALREADY_EXISTS:
            k.CloseHandle(ctypes.c_void_p(h))
            self._handle = None
            return False                    # 已经有实例了
        self._handle = h
        self._msg = message_id()
        return True

    # -------------------------------------------------- 广播显身
    def ping_existing(self):
        """请已有实例把窗口跑到前台。"""
        try:
            u = ctypes.windll.user32
            mid = self._msg or message_id()
            payload = _TAG
            buf = ctypes.create_string_buffer(payload, len(payload))
            cds = COPYDATASTRUCT()
            cds.dwData = 0x5742                      # 任意魔法值
            cds.cbData = len(payload)
            cds.lpData = ctypes.cast(buf, ctypes.c_void_p)
            u.SendMessageW.argtypes = [ctypes.c_void_p, wintypes.UINT,
                                       wintypes.WPARAM, ctypes.c_void_p]
            u.SendMessageW.argtypes = [ctypes.c_void_p, wintypes.UINT,
                                       wintypes.WPARAM, ctypes.c_void_p]
            # HWND_BROADCAST 才能送达「另一个进程的顶层窗口」
            u.SendNotifyMessageW.argtypes = [ctypes.c_void_p, wintypes.UINT,
                                             wintypes.WPARAM,
                                             ctypes.c_void_p]
            u.SendNotifyMessageW(ctypes.c_void_p(HWND_BROADCAST), mid, 0,
                                 ctypes.byref(cds))
            # 双保险：普通广播（部分窗口对 SendNotifyMessage 不响应）
            u.PostMessageW.argtypes = [ctypes.c_void_p, wintypes.UINT,
                                       wintypes.WPARAM, ctypes.c_void_p]
            u.PostMessageW(ctypes.c_void_p(HWND_BROADCAST), mid, 0,
                           ctypes.byref(cds))
        except Exception:
            pass

    def activate(self):
        """前台实例收到广播后的动作：还原 + 置顶 + 抢焦点。"""
        try:
            u = ctypes.windll.user32
            # 枚举所有顶层窗口，找本进程的可见主窗口
            mine = []
            pid = _kernel32().GetCurrentProcessId()

            def cb(hwnd, _):
                p = wintypes.DWORD()
                u.GetWindowThreadProcessId(ctypes.c_void_p(hwnd),
                                           ctypes.byref(p))
                if p.value == pid and u.IsWindowVisible(ctypes.c_void_p(hwnd)):
                    mine.append(hwnd)
                return True

            CB = ctypes.WINFUNCTYPE(wintypes.BOOL, ctypes.c_void_p,
                                    ctypes.c_void_p)
            u.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            u.EnumWindows(CB(cb), None)
            if not mine:
                return False
            hwnd = ctypes.c_void_p(mine[0])
            if u.IsIconic(hwnd):
                u.ShowWindow(hwnd, SW_RESTORE)
            else:
                u.ShowWindow(hwnd, SW_SHOW)
            # SetForegroundWindow 有前台锁定，先 Simulation 一下更稳
            try:
                u.AllowSetForegroundWindow(ctypes.c_void_p(-1))
            except Exception:
                pass
            u.BringWindowToTop(hwnd)
            u.SetForegroundWindow(hwnd)
            self._activated = True
            return True
        except Exception:
            return False

    @property
    def activated(self):
        return self._activated

    # -------------------------------------------------- 挂到 Tk 窗口
    def bind(self, tk_root):
        """让已有实例监听「显身」广播。

        Tk 没有直接暴露窗口过程，所以用户自己子类化窗口
        （SetWindowLongPtrW 换 WndProc），收到消息时回调。
        """
        if not self._msg:
            self._msg = message_id()
        self._tk_root = tk_root
        self._old_proc = None
        try:
            win = ctypes.windll.user32
            hwnd = ctypes.c_void_p(int(tk_root.winfo_id()))
            GWLP_WNDPROC = -4
            WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_void_p,
                                         wintypes.UINT, ctypes.c_size_t,
                                         ctypes.c_ssize_t)

            def myproc(h, msg, wp, lp):
                if msg == self._msg:
                    try:
                        tk_root.after(0, self.activate)
                    except Exception:
                        self.activate()
                    return 0
                return win.CallWindowProcW(self._old_proc, h, msg, wp, lp)

            self._proc = WNDPROC(myproc)
            win.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                              ctypes.c_void_p]
            win.SetWindowLongPtrW.restype = ctypes.c_void_p
            self._old_proc = win.SetWindowLongPtrW(hwnd, GWLP_WNDPROC,
                                                   ctypes.cast(self._proc,
                                                               ctypes.c_void_p))
            self._hwnd = hwnd
            return True
        except Exception:
            return False

    # -------------------------------------------------- 清理
    def release(self):
        try:
            if getattr(self, "_old_proc", None) and getattr(self, "_hwnd", None):
                u = ctypes.windll.user32
                u.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                                ctypes.c_void_p]
                u.SetWindowLongPtrW.restype = ctypes.c_void_p
                u.SetWindowLongPtrW(self._hwnd, -4,
                                    ctypes.cast(self._old_proc,
                                                ctypes.c_void_p))
                self._old_proc = None
        except Exception:
            pass
        try:
            if self._handle:
                _kernel32().CloseHandle(ctypes.c_void_p(self._handle))
                self._handle = None
        except Exception:
            pass


# ================================================================== 工具
def claim_or_exit():
    """入口处调用。

    返回已持锁的 SingleInstance（本进程继续跑）；
    若已有实例，广播让它显身并**强制结束本进程**。

    注意：frozen（PyInstaller 单文件）下 sys.exit(0) 有时不能立刻结束
    进程（bootloader 还在跑），所以这里三重保险：先广播、再 sys.exit、
    最后 OsExitProcess 硬杀。
    """
    guard = SingleInstance()
    if guard.acquire():
        return guard
    guard.ping_existing()
    # 干净退出（os._exit）—— onefile bootloader 会跟着收尾，不留幽灵进程
    _force_exit()
    _hard_kill()
