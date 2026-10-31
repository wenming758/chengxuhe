# -*- coding: utf-8 -*-
"""
对话框链路回归测试（新建分类 / 编辑分类 / 编辑程序）
背景 bug（两个叠加）：
  1) 三处对话框把 Launcher（普通对象）当父窗口传 → tk.Toplevel.__init__
     AttributeError，windowed 模式没有控制台 → 「点了没反应」
  2) BaseDialog.__init__ 里 `self._w, self._h = width, height` 覆盖了
     Tk 窗口路径 _w → tk.Canvas(self,...) 直接 int+str 崩溃

测试方式：
  - patch 掉 BaseDialog.show：显示对话框后，在 wait_window 嵌套循环内部
    「自动点保存」（优先真实鼠标点击；被环境遮挡则退回直接触发按钮 command）
  - 侧栏按钮同样用真实光标 + 真实事件链点击
数据目录重定向到临时副本，不碰真实数据。
"""
import ctypes, json, os, shutil, sys, tempfile, time, traceback
from ctypes import wintypes

SRC = r"C:/Users/Administrator/Desktop/DIY/汇总程序/src"
PROJ = os.path.dirname(SRC)
sys.path.insert(0, SRC)

TMP = tempfile.mkdtemp(prefix="wbtest_dlg_")
shutil.copy(os.path.join(PROJ, "apps_data.json"), os.path.join(TMP, "apps_data.json"))
os.makedirs(os.path.join(TMP, "icons"), exist_ok=True)
import assets as A
A.app_dir = lambda: TMP
A.data_path = lambda: os.path.join(TMP, "apps_data.json")
A.icon_dir = lambda: os.path.join(TMP, "icons")
import main as M

u = ctypes.windll.user32
u.SetCursorPos.argtypes = [wintypes.LONG, wintypes.LONG]
u.WindowFromPoint.argtypes = [wintypes.POINT]
u.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
u.IsWindowVisible.argtypes = [wintypes.HWND]
u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

ERRS = []
R = {"new_how": None, "edit_how": None, "app_how": None}


def pump():
    app.root.update()
    time.sleep(0.08)
    app.root.update()


def real_click(w):
    """光标移到控件中心，走真实 Tk 事件链（等价用户点击）"""
    app.root.update_idletasks()
    w.update_idletasks()
    x = w.winfo_rootx() + w.winfo_width() // 2
    y = w.winfo_rooty() + w.winfo_height() // 2
    u.SetCursorPos(x, y)
    pump()
    px, py = w.winfo_width() // 2, w.winfo_height() // 2
    w.event_generate("<Enter>")
    w.event_generate("<Button-1>", x=px, y=py)
    w.event_generate("<ButtonRelease-1>", x=px, y=py)
    app.root.update()


def toplevel_hwnd():
    pid = os.getpid()
    hits = []
    def cb(h, _):
        p = wintypes.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u.IsWindowVisible(h):
            cls = ctypes.create_unicode_buffer(256)
            u.GetClassNameW(h, cls, 256)
            if cls.value == "TkTopLevel":
                hits.append(int(h))
        return True
    CB = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    u.EnumWindows(CB(cb), 0)
    return hits[0] if hits else None


def click_ok(dlg):
    """点对话框的「保存」按钮；返回 'real-click' / 'command-invoke' / None"""
    try:
        ok = dlg.ok_button
        ok.update_idletasks()
        x = ok.winfo_rootx() + ok.winfo_width() // 2
        y = ok.winfo_rooty() + ok.winfo_height() // 2
        top = toplevel_hwnd()
        if top and ok.winfo_ismapped() and u.WindowFromPoint(wintypes.POINT(x, y)) == top:
            u.SetCursorPos(x, y)
            pump()
            ok.event_generate("<Button-1>", x=ok.winfo_width() // 2,
                              y=ok.winfo_height() // 2)
            ok.event_generate("<ButtonRelease-1>", x=ok.winfo_width() // 2,
                              y=ok.winfo_height() // 2)
            app.root.update()
            return "real-click"
    except Exception:
        ERRS.append(traceback.format_exc())
    try:
        dlg.ok_button.command()      # 环境遮挡时的兜底
        app.root.update()
        return "command-invoke"
    except Exception:
        ERRS.append(traceback.format_exc())
        return None


def patched_show(self):
    self.deiconify()
    self.lift()
    try:
        self.grab_set()
        self.focus_force()
    except Exception:
        pass
    self.update_idletasks()

    def auto_ok(tries=10):
        if not self.winfo_exists():
            return
        if not self.winfo_ismapped() and tries > 0:
            self.after(80, lambda: auto_ok(tries - 1))
            return
        how = click_ok(self)
        R["last_how"] = how
        # 兜底：对话框 1.5 秒还在就直接取消，避免测试挂死
        self.after(1500, lambda: self.winfo_exists() and self.on_cancel())

    self.after(250, lambda: auto_ok())
    self.wait_window(self)
    return self._result


M.W.BaseDialog.show = patched_show
app = M.Launcher()
app.root.report_callback_exception = lambda e, v, t: ERRS.append(
    "".join(traceback.format_exception(e, v, t)))


def stage_new_group():
    R["last_how"] = None
    orig = M.GroupDialog.__init__
    def init2(self, master, bank, store, group=None, focus_icon=False):
        orig(self, master, bank, store, group, focus_icon)
        if self.is_new:
            self.var_name.set("回归测试分类")
    M.GroupDialog.__init__ = init2
    try:
        real_click(app.btn_new_group)
    finally:
        M.GroupDialog.__init__ = orig
    R["new_how"] = R.get("last_how")
    names = [g["name"] for g in app.store.groups]
    R["new"] = "回归测试分类" in names
    print(">>> 新建分类: %s (保存方式=%s)  分类=%s"
          % ("PASS" if R["new"] else "FAIL", R["new_how"], names))


def stage_edit_group():
    gid = app.store.groups[0]["id"]
    orig = M.GroupDialog.__init__
    def init2(self, master, bank, store, group=None, focus_icon=False):
        orig(self, master, bank, store, group, focus_icon)
        if not self.is_new:
            self.var_name.set("回归分类改名")
    M.GroupDialog.__init__ = init2
    try:
        R["last_how"] = None
        app.dialog_edit_group(gid)
    finally:
        M.GroupDialog.__init__ = orig
    R["edit_how"] = R.get("last_how")
    names = [g["name"] for g in app.store.groups]
    R["edit"] = "回归分类改名" in names
    print(">>> 编辑分类: %s (保存方式=%s)  分类=%s"
          % ("PASS" if R["edit"] else "FAIL", R["edit_how"], names))


def stage_edit_app():
    it = app.store.items[0]
    orig = M.AppDialog.__init__
    def init2(self, master, bank, icon_bank, store, app=None):
        orig(self, master, bank, icon_bank, store, app)
        self.var_note.set("回归测试备注")
    M.AppDialog.__init__ = init2
    try:
        R["last_how"] = None
        app.dialog_edit(it)
    finally:
        M.AppDialog.__init__ = orig
    R["app_how"] = R.get("last_how")
    notes = any(i.get("note") == "回归测试备注" for i in app.store.items)
    print(">>> 编辑程序: %s (保存方式=%s)"
          % ("PASS" if notes else "FAIL", R["app_how"]))


def run_tests():
    stage_new_group()
    stage_edit_group()
    stage_edit_app()
    app.root.quit()


app.root.after(700, run_tests)
app.root.after(60000, app.root.quit)
app.run()

on_disk = note_disk = False
try:
    with open(os.path.join(TMP, "apps_data.json"), encoding="utf-8") as f:
        data = json.load(f)
    on_disk = "回归测试分类" in [g["name"] for g in data["groups"]]
    note_disk = any(i.get("note") == "回归测试备注" for i in data["items"])
except Exception as e:
    print("   读 JSON 失败: %s" % e)

notes = any(i.get("note") == "回归测试备注" for i in app.store.items)
print(">>> JSON 落盘(新分类): %s" % ("PASS" if on_disk else "FAIL"))
print(">>> JSON 落盘(备注): %s" % ("PASS" if note_disk else "FAIL"))
print(">>> 回调异常: %s" % (ERRS or "无"))
ok = bool(R.get("new")) and bool(R.get("edit")) and bool(notes) and on_disk and note_disk
print(">>> 总体: %s" % ("PASS" if ok else "FAIL"))
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(0 if ok else 1)
