# -*- coding: utf-8 -*-
"""
Windows 文件拖拽支持（纯 ctypes，无第三方依赖）
================================================
直接给 Tk 顶层窗口挂钩窗口过程，处理 WM_DROPFILES。

为什么不直接用 windnd 库：
  它的 WNDPROC 原型声明了 5 个参数（实际只有 4 个），
  且 DragQueryFileW 未声明 argtypes，在 64 位下会抛
  「ctypes.ArgumentError: argument 1: TypeError: wrong type」，
  结果是消息收到了、文件列表却是空的 —— 表现就是拖不进来。
  这里自己实现一遍，所有 API 都显式声明参数类型。

**关键限制：窗口过程回调里绝对不能调用任何 Tk/Tcl API**
  实测（tools/repro.py）：
    - 回调里只读文件、只写日志        → 正常
    - 回调里 root.title(...) 改标题   → 正常
    - 回调里 root.after(0, ...) 派发  → Fatal Python error:
      PyEval_RestoreThread: ... the GIL is released (thread state is NULL)
      进程直接崩掉
  原因：Windows 从 Tcl_DoOneEvent 里 DispatchMessage 调我们的窗口过程，
  此刻 _tkinter 已释放 GIL（Py_BEGIN_ALLOW_THREADS），
  ctypes 回调重新拿 GIL 后再让 Tk 执行 Tcl 命令就会炸。
  所以回调只做只读的 ctypes 活（读路径），
  把文件放进 self.pending，由调用方在自己的 Tk after 轮询里
  调 poll() 触发业务逻辑 —— 那时 GIL / 线程状态都正常。
"""
import ctypes
from ctypes import wintypes

WM_DROPFILES = 0x0233
WM_CLOSE = 0x0010
WM_ACTIVATE = 0x0006
WM_SIZE = 0x0005
WM_SHOWWINDOW = 0x0018
GWL_WNDPROC = -4
MAX_PATH_CHARS = 1024

SIZE_RESTORED, SIZE_MINIMIZED, SIZE_MAXIMIZED = 0, 1, 2

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_void_p, ctypes.c_uint,
                             ctypes.c_void_p, ctypes.c_ssize_t)

# ---- API 签名（必须显式声明，否则 64 位句柄会被当 int 截断）----
VOIDP = ctypes.c_void_p
if hasattr(user32, "SetWindowLongPtrW"):
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, VOIDP]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    _set_wndproc = user32.SetWindowLongPtrW
else:                                    # 老系统 32 位
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, VOIDP]
    user32.SetWindowLongW.restype = ctypes.c_long
    _set_wndproc = user32.SetWindowLongW

user32.CallWindowProcW.argtypes = [WNDPROC, ctypes.c_void_p, ctypes.c_uint,
                                   ctypes.c_void_p, ctypes.c_ssize_t]
user32.CallWindowProcW.restype = LRESULT
# DefWindowProcW 原来没声明 argtypes —— 64 位下 hwnd 一超过 2^31 就会
# "OverflowError: int too long to convert"（窗口过程里每个未处理的消息都会调它）。
user32.DefWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                  ctypes.c_void_p, ctypes.c_ssize_t]
user32.DefWindowProcW.restype = LRESULT

# 枚举窗口用
user32.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.EnumChildWindows.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ssize_t]
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
user32.GetWindow.argtypes = [ctypes.c_void_p, wintypes.UINT]
user32.GetWindow.restype = ctypes.c_void_p
user32.GetParent.argtypes = [ctypes.c_void_p]
user32.GetParent.restype = ctypes.c_void_p
user32.IsWindowVisible.argtypes = [ctypes.c_void_p]

GW_OWNER = 4
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, ctypes.c_void_p, ctypes.c_ssize_t)


def _self_pid():
    return ctypes.windll.kernel32.GetCurrentProcessId()


def _class_name(h):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(ctypes.c_void_p(h), buf, 256)
    return buf.value


def _title_of(h):
    n = user32.GetWindowTextLengthW(ctypes.c_void_p(h))
    if not n:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(ctypes.c_void_p(h), buf, n + 1)
    return buf.value


def _pid_of(h):
    pid = ctypes.c_ulong(0)
    user32.GetWindowThreadProcessId(ctypes.c_void_p(h), ctypes.byref(pid))
    return pid.value


def _descendants(h):
    """收集某窗口的所有子孙窗口。"""
    out = []

    def cb(k, _):
        out.append(int(k))
        return True

    try:
        user32.EnumChildWindows(ctypes.c_void_p(h), WNDENUMPROC(cb), 0)
    except Exception:
        pass
    return out


def _toplevel_candidates(winfo_id=None, title=None):
    """枚举本进程里「可见的顶层窗口」（TkTopLevel），不含子孙窗口。

    为什么不能用 GetAncestor(winfo_id, GA_ROOT)：
      Windows 上 Tk 的顶层窗口（类名 TkTopLevel）和 Tk 内部子窗口
      （winfo_id，类名 TkChild）是【兄弟】关系，不是父子 ——
      TkTopLevel 的 GetParent() 是 0、
      TkChild 的 GetParent() 是桌面窗口。
      所以从 winfo_id 往上找永远到不了 TkTopLevel。
    """
    pid = _self_pid()
    cands = []

    def cb(h, _):
        try:
            hi = int(h)
            if _pid_of(hi) != pid:
                return True
            if not user32.IsWindowVisible(ctypes.c_void_p(hi)):
                return True
            cls = _class_name(hi)
            if cls == "TkTopLevel":
                cands.append(hi)
            elif winfo_id and hi == int(winfo_id):
                # 兜底：万一 Tk 版本不同、类名不是 TkTopLevel
                cands.append(hi)
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(WNDENUMPROC(cb), 0)
    except Exception:
        pass

    # 优先选标题对得上的那个（同一进程可能有多个 Tk 顶层，比如对话框）
    if title:
        for h in cands:
            if _title_of(h) == title:
                cands = [h] + [x for x in cands if x != h]
                break
    return cands


def find_toplevels(winfo_id=None, title=None):
    """只返回真正承载界面的顶层窗口（不含子孙窗口）。

    给「设窗口图标 / 强制重绘」这类只需要顶层窗口的场景用。
    find_app_toplevels 会把几百个子窗口一起返回，
    逐个 SendMessage / RedrawWindow 又慢又容易把首帧搅乱。
    """
    return _toplevel_candidates(winfo_id, title)


def find_app_toplevels(winfo_id=None, title=None):
    """
    找出「本进程」里真正承载界面的顶层窗口 + 它们的全部子孙窗口。

    返回顺序：先 TkTopLevel，再所有子孙 ——
    这样无论拖到窗口哪个位置，都能收到 WM_DROPFILES。
    """
    order = []
    seen = set()
    for h in _toplevel_candidates(winfo_id, title):
        if h not in seen:
            order.append(h)
            seen.add(h)
        for k in _descendants(h):
            if k not in seen:
                order.append(k)
                seen.add(k)
    return order


def root_hwnd(winfo_id, title=None):
    """兼容旧接口：返回本进程的 Tk 顶层窗口（找不到就原样返回）。"""
    got = find_app_toplevels(winfo_id, title)
    return got[0] if got else int(winfo_id)

shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, wintypes.UINT,
                                   ctypes.c_void_p, wintypes.UINT]
shell32.DragQueryFileW.restype = wintypes.UINT
shell32.DragFinish.argtypes = [ctypes.c_void_p]


class DragDrop(object):
    """给指定窗口挂上文件拖拽接收能力。

    用法：
        dnd = DragDrop(hwnd, on_files)

        # 在主循环里轮询（推荐 60~150ms 一次）
        def poll():
            dnd.poll()
            root.after(100, poll)
        root.after(100, poll)

    说明：
        on_files(files) 只会在 poll() 里被调用，
        也就是说一定运行在正常的 Tk 上下文里，
        可以放心操作 Tk 控件。
    """

    def __init__(self, hwnd, on_files, title=None, on_close=None):
        self.hwnd = int(hwnd)
        self.on_files = on_files
        self.on_close = on_close
        self.title = title
        self.attached = False
        self.pending = []          # 窗口过程收到的文件，等 poll() 处理
        self.closing = False       # 收到过 WM_CLOSE
        self.needs_repaint = False  # 窗口重新显示 → 需要补一次全窗重绘
        self._was_minimized = False
        self._proc = None          # 防止被 GC
        self._win = {}             # hwnd -> 原窗口过程（用于还原）
        self._attach()

    def attach_to(self, num_retries=0, delay_ms=350, scheduler=None):
        """补挂：枚举本进程所有 Tk 窗口再挂一遍。

        scheduler(fn, ms) 传进来的话，挂不到就按 delay_ms 重试，
        最多 num_retries 次（窗口刚创建时 TkTopLevel 可能还没出现）。
        """
        def once():
            got = 0
            try:
                for h in find_app_toplevels(self.hwnd, self.title):
                    if h not in self._win and self._attach_one(h):
                        got += 1
            except Exception:
                got = 0
            self.attached = bool(self._win)
            return got

        got = once()
        if got == 0 and num_retries > 0 and scheduler is not None:
            left = {"n": num_retries}

            def again():
                if once() == 0 and left["n"] > 0:
                    left["n"] -= 1
                    scheduler(again, delay_ms)

            scheduler(again, delay_ms)
        return got

    # -------------------------------------------------- 挂载
    def _attach_one(self, hwnd):
        """给单个窗口挂 DragAcceptFiles + 子类化窗口过程。"""
        hwnd = int(hwnd)
        try:
            shell32.DragAcceptFiles(ctypes.c_void_p(hwnd), True)
        except Exception:
            pass
        old = _set_wndproc(ctypes.c_void_p(hwnd), GWL_WNDPROC,
                           ctypes.cast(self._proc, VOIDP))
        if old:
            self._win[hwnd] = WNDPROC(old)
            return True
        return False

    def _attach(self):
        self._proc = WNDPROC(self._handler)
        # 1) 显式指定的窗口
        if self.hwnd:
            self._attach_one(self.hwnd)
        # 2) 本进程所有 Tk 顶层窗口 + 它们的子孙窗口
        #    （Tk 的 winfo_id 只是内部子窗口，拖拽真正落在 TkTopLevel 上）
        extra = []
        try:
            extra = find_app_toplevels(self.hwnd, self.title)
        except Exception:
            extra = []
        for h in extra:
            if h not in self._win:
                self._attach_one(h)
        self.attached = bool(self._win)
        return self.attached

    def detach(self):
        if not self.attached and not self._win:
            return
        for hwnd, old_proc in list(self._win.items()):
            try:
                _set_wndproc(ctypes.c_void_p(hwnd), GWL_WNDPROC,
                             ctypes.cast(old_proc, VOIDP))
            except Exception:
                pass
        self._win = {}
        self.attached = False
        self._proc = None

    # -------------------------------------------------- 轮询（在 Tk after 里调）
    def poll(self):
        """把窗口过程收到的文件交给业务回调。返回本次处理的文件列表。"""
        if not self.pending:
            return []
        files, self.pending = self.pending, []
        if self.on_files is not None:
            self.on_files(files)
        return files

    def has_pending(self):
        return bool(self.pending)

    # -------------------------------------------------- 兜底：直接问系统要文件
    def query_dropped_files(self):
        """
        窗口过程万一没被调到时（例如某些冻结/打包环境里
        ctypes 回调被丢弃），直接调用 DragQueryFileW(hwnd) 兜底：
        拖拽悬停时系统会把文件列表挂到窗口上，这里主动去取。
        """
        out = []
        for hwnd in list(self._win.keys()) + [self.hwnd]:
            if not hwnd:
                continue
            try:
                got = self._read_files(hwnd)
            except Exception:
                got = []
            for f in got:
                if f not in out:
                    out.append(f)
            if got:
                try:
                    shell32.DragFinish(ctypes.c_void_p(int(hwnd)))
                except Exception:
                    pass
        return out

    # -------------------------------------------------- 自检信息
    def info(self):
        return {
            "hwnd": self.hwnd,
            "attached": self.attached,
            "windows": [hex(h) for h in self._win],
        }

    # -------------------------------------------------- 窗口可见性监听
    def _watch_visibility(self, msg, wp):
        """记下「窗口刚被重新显示」的时刻，交给 poll() 补一次全窗重绘。

        Tk on Windows 上最小化再恢复，Windows 只重画受损区域，
        Tk 内部又认为自己已经画过了 —— 结果整块客户区停在黑底，
        只有鼠标划过的控件各自补画（就是「鼠标扫过才有内容」）。
        这里在窗口过程里只置一个 flag（不碰任何 Tk API），
        真正重画由 _poll_dnd 在自己的 after 里做。
        """
        try:
            w = int(wp or 0)
        except Exception:
            w = 0
        if msg == WM_SIZE:
            if w == SIZE_MINIMIZED:
                self._was_minimized = True
            elif w in (SIZE_RESTORED, SIZE_MAXIMIZED) and self._was_minimized:
                self._was_minimized = False
                self.needs_repaint = True
        elif msg == WM_SHOWWINDOW and w:
            self.needs_repaint = True
        elif msg == WM_ACTIVATE and w:
            self.needs_repaint = True

    # -------------------------------------------------- 窗口过程
    def _handler(self, hwnd, msg, wp, lp):
        # 注意：这里绝不能调用任何 Tk API，见模块注释
        try:
            if msg == WM_DROPFILES:
                files = self._read_files(wp)
                shell32.DragFinish(wp)
                if files:
                    self.pending.extend(files)
                return 0
            if msg == WM_CLOSE:
                # 顶层窗口（TkTopLevel）的关闭消息不一定走 Tk 的
                # WM_DELETE_WINDOW，这里标记一下，交给 poll() 触发退出
                self.closing = True
            self._watch_visibility(msg, wp)
        except Exception:
            pass
        # 还原到该窗口原本的窗口过程
        try:
            key = int(hwnd or 0)
        except Exception:
            key = 0
        old = self._win.get(key)
        if old is not None:
            return user32.CallWindowProcW(old, hwnd, msg, wp, lp)
        return user32.DefWindowProcW(hwnd, msg, wp, lp)

    # -------------------------------------------------- 读文件列表
    @staticmethod
    def _read_files(hdrop):
        n = shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
        if not n:
            return []
        out = []
        for i in range(n):
            buf = ctypes.create_unicode_buffer(MAX_PATH_CHARS)
            got = shell32.DragQueryFileW(hdrop, i, buf, MAX_PATH_CHARS)
            if got:
                out.append(buf.value)
        return out


# 兼容旧调用名
hook_dropfiles = DragDrop
