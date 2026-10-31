# -*- coding: utf-8 -*-
"""
程序收纳盒 —— 卡通风格的 Windows 程序启动器
==========================================
· 拖拽 exe / 快捷方式进窗口即可收藏，也能用「添加程序」按钮挑选
· 卡片流展示，单击启动，右键编辑 / 删除 / 移动分类 / 换图标
· 数据全部存在 exe 同目录（apps_data.json + icons/），拷走即用

入口文件，双击运行；打包见 build.spec。
"""
import ctypes
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk

# 保证能 import 同目录模块（PyInstaller 单文件模式同样适用）
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import assets as A          # noqa: E402
import blessings as B       # noqa: E402
import delta                # noqa: E402
import iconutil             # noqa: E402
import linkfix              # noqa: E402
import singleinst           # noqa: E402
import spawner              # noqa: E402
import store as S           # noqa: E402
import theme as T           # noqa: E402
import updater              # noqa: E402
import widgets as W         # noqa: E402

SORT_LABELS = [
    ("manual", "自定义顺序", "sort"),
    ("added", "添加时间", "calendar"),
    ("name", "程序名称", "memo"),
    ("count", "使用次数", "chart"),
    ("recent", "最近打开", "clock"),
]

EMOJI_HINTS = [
    ("游戏", "game"), ("播放", "movie"), ("视频", "movie"), ("音乐", "music"),
    ("音乐", "music"), ("浏览器", "globe"), ("网络", "globe"), ("下载", "import"),
    ("记事", "memo"), ("文本", "memo"), ("编辑", "pencil"), ("图片", "picture"),
    ("图像", "picture"), ("截图", "camera"), ("相机", "camera"), ("聊天", "chat"),
    ("微信", "chat"), ("QQ", "chat"), ("办公", "book"), ("文档", "book"),
    ("表格", "chart"), ("数据", "chart"), ("计算", "chart"), ("杀毒", "shield"),
    ("安全", "shield"), ("驱动", "wrench"), ("工具", "toolbox"), ("终端", "laptop"),
    ("命令", "laptop"), ("系统", "gear"), ("设置", "gear"), ("云", "cloud"),
    ("盘", "save"), ("压缩", "box"), ("解压", "box"), ("录屏", "camera"),
    ("远程", "monitor"), ("虚拟机", "monitor"), ("地图", "map"), ("邮件", "mail"),
    ("钱包", "money"), ("股票", "money"), ("财务", "money"), ("学习", "school"),
    ("词典", "book"), ("翻译", "globe"), ("宠物", "paw"), ("喵", "cat"),
]


def guess_emoji(path):
    """按扩展名 / 文件名猜一个合适的彩色 emoji 做兜底图标。"""
    low = os.path.basename(path).lower()
    ext = os.path.splitext(low)[1]
    ext_map = {
        ".lnk": "link", ".url": "globe", ".bat": "hammer", ".cmd": "hammer",
        ".ps1": "laptop", ".msc": "gear", ".jar": "coffee", ".vbs": "magic",
        ".com": "laptop", ".appref-ms": "cloud",
    }
    if ext in ext_map:
        return ext_map[ext]
    for kw, name in EMOJI_HINTS:
        if kw.lower() in low:
            return name
    return "rocket"


class Launcher(object):

    MAX_COLS = 12             # 每行最多铺 12 个卡片（再宽也不无限拉散）

    def __init__(self):
        self.root = tk.Tk()
        self.F = T.fonts()
        self._setup_window()

        self.bank = A.EmojiBank()
        self.icon_bank = A.AppIconBank(A.icon_dir())
        self.store = S.Store(A.data_path(), A.icon_dir())
        # 历史数据里存的是桌面 .lnk 路径，桌面一删就失效。
        # 启动时解析成真实 exe 的绝对路径，一次性升级，日志留在同目录。
        try:
            fixed = linkfix.migrate_items(
                self.store.items,
                log_path=os.path.join(A.app_dir(), "修复日志.txt"))
            if fixed:
                self.store.save()
        except Exception:
            pass
        # 记住上次退出时所在的分类；若该分类已被删除或已加锁则回退到「全部程序」
        last = self.store.settings.get("last_group", "")
        if (last and (last in (S.G_ALL, S.G_FAV, S.G_RECENT)
                      or self.store.group_by_id(last))
                and not self.store.group_locked(last)):
            self.cur_group = last
        else:
            self.cur_group = S.G_ALL
        self.keyword = ""
        self.selected_id = None
        self.cards = []
        self._last_cols = 0
        self._empty_frame = None
        self._empty_showing = False
        self._laid_n = -1
        self._visible_n = 0
        self._sort = self.store.settings.get("sort", "manual")
        self._hit = None
        # 缩放/最大化期间合并重绘请求，防止连续 Configure 把界面拖死
        self._hdr_pending = False
        self._hdr_size = (0, 0)
        self._layout_pending = False
        self._resize_at = 0.0
        self._repaint_at = 0.0
        self._repaint_deferred = False

        self._setup_style()
        self._build_ui()
        self._render_groups()
        self._bind_keys()
        self._hook_dnd()
        # 先把骨架（顶栏 / 侧栏 / 状态栏）显示出来并强制整窗重绘一次，
        # 卡片留到下一个事件循环再填 —— 首屏立刻可见，不会黑屏。
        self._show_window()
        self.root.after(1, self._first_fill)

    # ================================================== 窗口
    def _setup_window(self):
        r = self.root
        # 先把窗口藏起来：等骨架搭完、首帧画完再一次性显示。
        # 否则窗口在「还在建控件」的阶段就被系统显示出来，用户先看到
        # 一大片黑（Windows 对还没画完首帧的窗口就显示黑底）。
        try:
            r.withdraw()
        except Exception:
            pass
        r.title(S.APP_TITLE + " " + S.APP_VERSION)
        r.configure(bg=T.BG_APP)
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        w = min(1180, max(960, sw - 120))
        h = min(780, max(600, sh - 110))
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2 - 20)
        r.geometry("%dx%d+%d+%d" % (w, h, x, y))
        r.minsize(960, 600)
        ico = A.resource("launcher_orange.ico")
        if os.path.exists(ico):
            try:
                r.iconbitmap(ico)
            except Exception:
                pass
        else:
            png = A.resource("logo_56.png")
            if os.path.exists(png):
                try:
                    r.iconphoto(True, tk.PhotoImage(file=png))
                except Exception:
                    pass
        self.logo_img = None
        for name in ("logo_56.png", "launcher_orange.png"):
            p = A.resource(name)
            if os.path.exists(p):
                try:
                    img = tk.PhotoImage(file=p)
                    if img.width() > 56:
                        f = max(1, int(round(img.width() / 56.0)))
                        img = img.subsample(f, f)
                    self.logo_img = img
                    break
                except Exception:
                    pass
        # 关闭窗口：默认先解绑拖拽挂钩再退出。
        # 注意：真正承载界面的顶层窗口是 TkTopLevel。Tk 默认只把键盘焦点
        # 交给内部子窗口，外层 TkTopLevel 拿不到焦点 —— 这样 Alt+F4、
        # Ctrl+Q 之类的键盘事件根本进不来。所以显式抢一次焦点。
        r.protocol("WM_DELETE_WINDOW", self._quit)
        r.after(200, self._grab_focus)
        r.bind("<Destroy>", self._on_root_destroy, add="+")
        # 最小化再恢复、或被别的窗口挡住又切回来时，Windows 有时不会
        # 重画整块客户区（Tk 内部也以为自己画过了）—— 表现就是恢复后
        # 一片黑、只有鼠标划过的控件才补画。这里监听 <Map>，一恢复就
        # 补一次全窗重绘（另一条更可靠的路在 dnd 的 WM_SIZE/WM_ACTIVATE
        # 监听里，见 _watch_visibility）。
        r.bind("<Map>", self._on_reshow, add="+")
        # 任务栏 / Alt+Tab / 标题栏图标：TkTopLevel 是窗口映射后才出现的，
        # 所以定时补挂几次（跟拖拽挂钩用同一套窗口枚举逻辑）
        r.after(120, self._ensure_taskbar_icon)
        # 按钮回调里抛异常时，Tk 默认只往 stderr 打 —— windowed 模式没有
        # 控制台，用户看到的就是「点了没反应」。这里改成弹框 + 打印，
        # 保证任何按钮出问题都能看见原因。
        r.report_callback_exception = self._report_callback_error

    def _report_callback_error(self, exc, val, tb):
        try:
            import traceback
            msg = "".join(traceback.format_exception(exc, val, tb))
        except Exception:
            msg = "%s: %s" % (getattr(exc, "__name__", "Error"), val)
        try:
            sys.stderr.write(msg + "\n")
            sys.stderr.flush()
        except Exception:
            pass
        # windowed 模式 stderr 会丢，顺手把完整堆栈落到 exe 同目录的
        # 程序收纳盒_error.log，出问题时把这份日志发回来即可定位。
        try:
            import time
            import assets as _A
            log_path = os.path.join(_A.app_dir(), "程序收纳盒_error.log")
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("==== %s ====\n%s\n" % (stamp, msg))
        except Exception:
            pass
        try:
            from tkinter import messagebox
            messagebox.showerror(
                "程序收纳盒 · 操作失败",
                "刚才这一步没做成，报错信息：\n\n%s" % val,
                parent=self.root)
        except Exception:
            pass

    def _ensure_taskbar_icon(self):
        """把用户给的图标挂到真正的顶层窗口上（任务栏按钮就是它）。"""
        if getattr(self, "_closing", False):
            return
        ico = A.resource("launcher_orange.ico")
        if not os.path.exists(ico):
            return                      # 没有 ico 就维持 Tk 默认，不强求
        # 只给**顶层窗口**挂图标：任务栏按钮 / Alt+Tab 都只看顶层窗口。
        # 之前对几百个子窗口逐个 SendMessage(WM_SETICON) + SetClassLongPtr，
        # 每次启动要打上万次系统调用，既拖慢启动又容易把首帧搅花。
        try:
            import dnd
            wins = dnd.find_toplevels(self.root.winfo_id(),
                                      self.root.title())
        except Exception:
            wins = []
        if not wins:
            wins = [int(self.root.winfo_id())]
        n = 0
        try:
            import iconutil
            for h in wins:
                if iconutil.set_window_icon(h, ico):
                    n += 1
        except Exception:
            n = 0
        # TkTopLevel 出现得比主窗口晚，多试几次；成功后也再确认一次
        left = getattr(self, "_icon_tries", 0)
        if n == 0 and left < 8:
            self._icon_tries = left + 1
            self.root.after(250, self._ensure_taskbar_icon)
        elif n and left < 3:
            self._icon_tries = left + 1
            self.root.after(1200, self._ensure_taskbar_icon)

    def _grab_focus(self):
        """把键盘焦点明确交给本窗口，保证快捷键 / Alt+F4 能被收到。"""
        try:
            import ctypes
            from ctypes import wintypes
            u = ctypes.windll.user32
            u.GetAncestor.argtypes = [ctypes.c_void_p, wintypes.UINT]
            u.GetAncestor.restype = ctypes.c_void_p
            u.SetForegroundWindow.argtypes = [ctypes.c_void_p]
            u.SetActiveWindow.argtypes = [ctypes.c_void_p]
            u.SetFocus.argtypes = [ctypes.c_void_p]
            h = int(self.root.winfo_id())
            root = u.GetAncestor(ctypes.c_void_p(h), 2)   # GA_ROOT
            target = int(root) if root else h
            u.SetForegroundWindow(ctypes.c_void_p(target))
            u.SetActiveWindow(ctypes.c_void_p(target))
            u.SetFocus(ctypes.c_void_p(h))
        except Exception:
            pass
        try:
            self.root.focus_force()
        except Exception:
            pass

    # ================================================== 首屏显示 / 重绘
    def _show_window(self):
        """把窗口显示出来，并强制整窗（含所有子控件）重绘一次。"""
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        try:
            self.root.deiconify()
        except Exception:
            pass
        try:
            self.root.lift()
        except Exception:
            pass
        # 主循环还没起来，这里要顺手把事件泵一遍
        self._force_repaint(pump=True)
        # TkTopLevel 出现得比内部子窗口晚；慢机器 / 远程桌面下首帧还可能
        # 被系统整块吞掉。头几秒里多补几次全窗重绘，确保不会停在「一片黑」。
        for ms in (60, 250, 600, 1200, 2000, 3000):
            try:
                self.root.after(ms, self._force_repaint)
            except Exception:
                pass

    def _on_reshow(self, _=None):
        """窗口重新显示：合并同一时刻的多次请求，再强制重绘一次。"""
        if getattr(self, "_reshow_pending", False):
            return
        self._reshow_pending = True

        def go():
            self._reshow_pending = False
            if getattr(self, "_closing", False):
                return
            self._force_repaint()

        try:
            self.root.after(30, go)
        except Exception:
            self._reshow_pending = False

    def _first_fill(self):
        """骨架显示之后再填卡片（分帧，首屏不会空白太久）。"""
        try:
            self.refresh()
        except Exception:
            pass
        self._force_repaint()
        try:
            self.root.after(150, self._focus_search)
        except Exception:
            pass
        try:
            self.root.after(1000, self._refresh_icons_once)
        except Exception:
            pass
        try:
            self.root.after(4000, self._auto_check_update)
        except Exception:
            pass
        try:
            self.root.after(B.INTERVAL_MS, self._rotate_blessing)
        except Exception:
            pass

    def _auto_check_update(self):
        """启动后后台静默检查更新，有新版才弹提示。"""
        if getattr(self, "_update_checking", False):
            return
        try:
            last = float(self.store.settings.get("update_checked_at") or 0)
        except Exception:
            last = 0
        if time.time() - last < 6 * 3600:
            return
        self._update_checking = True

        def work():
            avail, info = False, None
            try:
                avail, info = updater.check_for_update(S.UPDATE_APIS,
                                                       S.APP_VERSION)
            except Exception:
                pass

            def done():
                self._update_checking = False
                if getattr(self, "_closing", False):
                    return
                if info and not info.get("error"):
                    self.store.settings["update_checked_at"] = time.time()
                    self.store.save()
                if avail and info:
                    self._on_update_checked(True, info)

            try:
                self.root.after(0, done)
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _refresh_icons_once(self):
        """旧版缓存里的图标只有左上角一小块，启动后后台重抓一次。"""
        todo = [it for it in list(self.store.items)
                if it.get("icon")
                and int(it.get("iconv", 0) or 0) < S.ICON_FORMAT]
        if not todo:
            return

        def work():
            results = {}
            for it in todo:
                try:
                    got = iconutil.extract_icon(it.get("path", ""))
                except Exception:
                    got = None
                if got:
                    results[it["id"]] = got
            try:
                self.root.after(0, lambda: self._apply_icon_refresh(todo, results))
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _apply_icon_refresh(self, todo, results):
        if getattr(self, "_closing", False):
            return
        try:
            for it in todo:
                got = results.get(it["id"])
                if got:
                    fn = self.store.cache_icon(got)
                    if not fn:
                        continue    # 编码失败：保留旧图标，下次启动再试
                    it["icon"] = fn
                # 抓不到也记下版本，避免每次启动都白试一遍
                it["iconv"] = S.ICON_FORMAT
            self.store.save()
            self.icon_bank.clear()
            self.refresh()
        except Exception:
            pass

    def _force_repaint(self, pump=False):
        """强制整窗重绘一次。

        Windows 上偶发「窗口一片黑，鼠标扫到哪里才出现哪里」——
        首帧的 WM_PAINT 没覆盖整块客户区，之后只有被鼠标划过的控件
        各自补画。这里用 RedrawWindow 把所有子窗口一次性标脏并立即
        重画，等于手动补一次全窗重绘。

        注意只对**顶层窗口**操作：带上 RDW_ALLCHILDREN 已经覆盖全部
        子窗口，逐个去 RedrawWindow 几百个子窗口反而更慢、更容易抖动。
        """
        if getattr(self, "_repaint_busy", False):
            return
        if not pump:
            now = time.time()
            # 最大化 / 拖边缘时窗口还没稳定，此刻同步重绘会把消息循环卡住；
            # 等尺寸停下来 0.25 秒后再补一次。
            if now - getattr(self, "_resize_at", 0.0) < 0.25:
                if not self._repaint_deferred:
                    self._repaint_deferred = True
                    try:
                        self.root.after(320, self._repaint_later)
                    except Exception:
                        self._repaint_deferred = False
                return
            if now - getattr(self, "_repaint_at", 0.0) < 0.2:
                return
            self._repaint_at = now
        self._repaint_busy = True
        try:
            try:
                self.root.update_idletasks()
            except Exception:
                pass
            targets = []
            try:
                import dnd
                targets = dnd.find_toplevels(self.root.winfo_id(),
                                             self.root.title())
            except Exception:
                targets = []
            if not targets:
                targets = [int(self.root.winfo_id())]
            try:
                u = ctypes.windll.user32
                u.RedrawWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                           ctypes.c_void_p, ctypes.c_uint]
                u.RedrawWindow.restype = ctypes.c_int
                # INVALIDATE | ERASE | ALLCHILDREN | UPDATENOW
                flags = 0x0001 | 0x0004 | 0x0080 | 0x0100
                for h in targets:
                    try:
                        u.RedrawWindow(ctypes.c_void_p(int(h)), None, None,
                                       flags)
                    except Exception:
                        pass
            except Exception:
                pass
            # 只有在主循环起来之前才需要手动泵事件；
            # 之后 RDW_UPDATENOW 已经同步把 WM_PAINT 走完了。
            if pump:
                try:
                    self.root.update()
                except Exception:
                    pass
        finally:
            self._repaint_busy = False

    def _on_root_destroy(self, event=None):
        try:
            if event is not None and event.widget is not self.root:
                return
        except Exception:
            pass
        try:
            d = getattr(self, "_dnd", None)
            if d is not None:
                d.detach()
        except Exception:
            pass
        # 窗口真没了就顺手放锁（双保险，_quit 已经放过一次）
        try:
            g = getattr(self, "_single", None)
            if g is not None:
                g.release()
                self._single = None
        except Exception:
            pass

    def _quit(self):
        # 先退出主循环，等 run() 里再销毁窗口。
        # 不要在事件回调里直接 destroy()：实测那样会卡死解释器收尾，
        # 进程点完关闭后不退出的问题就是这么来的。
        try:
            d = getattr(self, "_dnd", None)
            if d is not None:
                d.detach()
                d.attached = False
        except Exception:
            pass
        self._closing = True
        self.root.quit()
        # 松开单实例锁，让用户下次还能正常打开
        try:
            g = getattr(self, "_single", None)
            if g is not None:
                g.release()
                self._single = None
        except Exception:
            pass

    def _setup_style(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("Cartoon.TCombobox",
                     fieldbackground=T.BG_INPUT, background=T.BG_INPUT,
                     foreground=T.TEXT, arrowcolor=T.ACCENT,
                     bordercolor=T.LINE_STRONG, lightcolor=T.LINE_STRONG,
                     darkcolor=T.LINE_STRONG, relief="flat", padding=5)
        st.map("Cartoon.TCombobox",
               fieldbackground=[("readonly", T.BG_INPUT)],
               bordercolor=[("focus", T.ACCENT)])

    # ================================================== 界面骨架
    BLESS_LEFT = 340          # 顶栏标题区占到这个位置，祝福语从它后面开始

    def _build_ui(self):
        self._bless = B.pick()
        self.header = tk.Frame(self.root, height=88, bg=T.BG_HEAD_B)
        self.header.pack(fill="x", side="top")
        self.header.pack_propagate(False)
        self.head_cv = tk.Canvas(self.header, bg=T.BG_HEAD_B,
                                 highlightthickness=0, bd=0)
        self.head_cv.pack(fill="both", expand=True)
        self.head_cv.bind("<Configure>", self._on_header_configure)

        body = tk.Frame(self.root, bg=T.BG_APP)
        body.pack(fill="both", expand=True)

        self._build_sidebar(body)
        self._build_main(body)
        self._build_footer()

    # -------------------------------------------------- 顶栏
    def _on_header_configure(self, _=None):
        """顶栏尺寸变化：合并同一批事件，并且尺寸没变就不重画。"""
        if self._hdr_pending:
            return
        self._hdr_pending = True
        try:
            self.root.after_idle(self._flush_header)
        except Exception:
            self._hdr_pending = False

    def _flush_header(self):
        self._hdr_pending = False
        try:
            size = (self.head_cv.winfo_width(), self.head_cv.winfo_height())
        except Exception:
            return
        if size == self._hdr_size:
            return
        self._hdr_size = size
        self._draw_header()

    def _draw_header(self):
        c = self.head_cv
        w = max(1, c.winfo_width())
        h = max(1, c.winfo_height())
        c.delete("all")
        T.hgrad(c, 0, 0, w, h, T.BG_HEAD_A, T.BG_HEAD_B, steps=72)
        # 卡通泡泡装饰
        c.create_oval(w * 0.42, -46, w * 0.42 + 130, 84, fill=T.lighten(T.BG_HEAD_A, 0.18), outline="")
        c.create_oval(w - 190, h - 54, w - 40, h + 96, fill=T.lighten(T.BG_HEAD_B, 0.22), outline="")
        c.create_oval(-40, h - 40, 60, h + 60, fill=T.lighten(T.BG_HEAD_A, 0.12), outline="")
        c.create_text(w - 22, 16, text="", anchor="e")

        if self.logo_img is not None:
            c.create_image(50, 44, image=self.logo_img)
        c.create_text(90, 32, text=S.APP_TITLE + " " + S.APP_VERSION, anchor="w",
                      font=self.F["logo"], fill="#FFFFFF")
        c.create_text(92, 57, text="单击启动 · 拖进来就能收藏 · 右键管理",
                      anchor="w", font=self.F["logo_sub"], fill="#FFF3E2")
        self._place_header_widgets(w)
        self._draw_blessing(w, h)

    def _draw_blessing(self, w, h):
        """顶栏中间的祝福语：每 5 分钟换一条，窗口太窄放不下就干脆不画。"""
        c = self.head_cv
        c.delete("bless")
        item = getattr(self, "_bless", None)
        if not item:
            return
        left = self.BLESS_LEFT
        right = getattr(self, "_search_x", w) - 14
        if right - left < 250:
            return
        font = self.F["small_b"]
        img = self.bank.get(item[0], 18)
        icon_w = 22 if img is not None else 0
        text = T.ellipsis(item[1], font, right - left - 28 - icon_w)

        tid = c.create_text(0, 0, text=text, anchor="w", font=font,
                            fill="#FFFFFF")
        bb = c.bbox(tid)
        c.delete(tid)
        if not bb:
            return
        gw = icon_w + 6 + (bb[2] - bb[0])
        x0 = left + max(0, (right - left - gw) // 2)
        cy = h // 2
        T.pill(c, x0 - 14, cy - 17, x0 + gw + 14, cy + 17,
               fill=T.lighten(self._head_bg_at(x0 + gw / 2.0, w), 0.26),
               tags="bless")
        if img is not None:
            c.create_image(x0 + 11, cy, image=img, tags="bless")
        c.create_text(x0 + icon_w + 6, cy, text=text, anchor="w", font=font,
                      fill="#FFFFFF", tags="bless")

    def _rotate_blessing(self):
        """换一条祝福语；顶栏可能还没画出来，尺寸留着下次重绘时用。"""
        try:
            self._bless = B.pick(getattr(self, "_bless", (None, ""))[1])
            w = self.head_cv.winfo_width()
            h = self.head_cv.winfo_height()
            if w > 1 and h > 1:
                self._draw_blessing(w, h)      # 窗口没显示时，下次顶栏重绘自然带上
        except Exception:
            pass
        try:
            self.root.after(B.INTERVAL_MS, self._rotate_blessing)
        except Exception:
            pass

    def _head_bg_at(self, x, w):
        t = max(0.0, min(1.0, x / float(max(1, w))))
        return T.mix(T.BG_HEAD_A, T.BG_HEAD_B, t)

    def _place_header_widgets(self, w):
        # 右侧依次：设置 / 添加程序 / 搜索框
        if not hasattr(self, "btn_settings"):
            self.var_search = tk.StringVar()
            self.entry_search = tk.Entry(
                self.header, textvariable=self.var_search, font=self.F["small"],
                bg="#FFFFFF", fg=T.TEXT, relief="flat", bd=0,
                insertbackground=T.ACCENT)
            self.var_search.trace_add("write", lambda *a: self._on_search())
            self.entry_search.bind("<Escape>", lambda e: self._clear_search())
            self.entry_search.bind("<FocusIn>", lambda e: self.head_cv.delete("searchbox"))
            self.entry_search.bind("<FocusOut>", lambda e: self._draw_search_box())
            self.head_cv.tag_bind("searchbox", "<Button-1>",
                                  lambda e: self._focus_search())

            self.btn_add = W.RoundButton(
                self.header, text="添加程序", emoji_img=self.bank.get("plus", 18),
                variant="soft", width=132, height=38, command=self.dialog_add,
                bg=T.BG_HEAD_B)
            self.btn_settings = W.IconButton(
                self.header, self.bank.get("gear", 28), command=self.menu_settings,
                size=38, bg=T.BG_HEAD_B, tip="设置")
            # 明确的退出按钮（Alt+F4 / 任务栏关闭在某些环境下不生效）
            self.btn_quit = W.IconButton(
                self.header, self.bank.get("cross", 28), command=self._quit,
                size=38, bg=T.BG_HEAD_B, tip="退出程序（Ctrl+Q）")

        right = 20
        qx_ = w - right - 38
        sx = qx_ - 10 - 38
        ax = sx - 12 - 132
        qw = 250
        qx = ax - 12 - qw
        self._search_x, self._search_w = qx, qw

        self.btn_quit.place(x=qx_, y=25)
        self._repaint_btn(self.btn_quit, qx_ + 19, w)
        self.btn_settings.place(x=sx, y=25)
        self._repaint_btn(self.btn_settings, sx + 19, w)
        self.btn_add.place(x=ax, y=25)
        self._repaint_btn(self.btn_add, ax + 66, w)

        self._draw_search_box()
        self.entry_search.place(x=qx + 32, y=32, width=qw - 46, height=22)

    def _repaint_btn(self, btn, cx, w):
        col = self._head_bg_at(cx, w)
        btn.bg = col
        btn.configure(bg=col)
        btn._draw()

    def _draw_search_box(self):
        w = self.head_cv.winfo_width()
        qw = getattr(self, "_search_w", 250)
        qx = getattr(self, "_search_x", max(0, w - 460))
        self.head_cv.delete("searchbox")
        T.rrect(self.head_cv, qx, 24, qx + qw, 62, 19, fill="#FFFFFF",
                outline="", tags="searchbox")
        img = self.bank.get("search", 18)
        if img is not None:
            self.head_cv.create_image(qx + 18, 43, image=img, tags="searchbox")
        if not self.var_search.get():
            self.head_cv.create_text(qx + 34, 43, text="搜索名称 / 路径…",
                                     anchor="w", font=self.F["small"],
                                     fill=T.TEXT_MUTED, tags="searchbox")
        self.head_cv.tag_lower("searchbox")

    # -------------------------------------------------- 侧栏
    def _build_sidebar(self, parent):
        side = tk.Frame(parent, width=212, bg=T.BG_SIDE)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        self.sidebar = side

        top = tk.Frame(side, bg=T.BG_SIDE, height=54)
        top.pack(fill="x")
        top.pack_propagate(False)
        tk.Label(top, text="分类", bg=T.BG_SIDE, fg=T.TEXT,
                 font=self.F["section"]).pack(side="left", padx=(20, 6), pady=16)
        if self.bank.get("folder2", 18) is not None:
            lbl = tk.Label(top, image=self.bank.get("folder2", 18), bg=T.BG_SIDE)
            lbl.pack(side="left", pady=16)

        bottom = tk.Frame(side, bg=T.BG_SIDE)
        bottom.pack(side="bottom", fill="x", pady=14)
        # 先把底部按钮区占住，再把分类列表放进可滚动区域：
        # 否则分类一多，group_box 会把 212px 侧栏撑满，
        # 「新建分类」被挤到窗口外，只有最大化后才看得见。
        self.btn_new_group = W.RoundButton(
            bottom, text="新建分类", emoji_img=self.bank.get("new", 18),
            variant="plain", width=176, height=38, bg=T.BG_SIDE,
            command=self.dialog_add_group)
        self.btn_new_group.pack(padx=18, pady=(0, 10))

        tk.Frame(side, bg=T.LINE, height=1).pack(side="bottom", fill="x",
                                                 padx=16, pady=(0, 6))

        self.group_scroll = W.ScrollArea(side, bg=T.BG_SIDE,
                                         padding=(0, 2, 0, 2))
        self.group_scroll.pack(side="top", fill="both", expand=True)
        self.group_box = self.group_scroll.inner

        tip = tk.Frame(bottom, bg=T.BG_TAG)
        tip.pack(fill="x", padx=14)
        inner = tk.Frame(tip, bg=T.BG_TAG)
        inner.pack(fill="x", padx=12, pady=10)
        head = tk.Frame(inner, bg=T.BG_TAG)
        head.pack(fill="x")
        if self.bank.get("teddy", 18) is not None:
            tk.Label(head, image=self.bank.get("teddy", 18), bg=T.BG_TAG).pack(side="left")
        tk.Label(head, text="小提示", bg=T.BG_TAG, fg=T.ACCENT_DK,
                 font=self.F["small_b"]).pack(side="left", padx=(4, 0))
        tk.Label(inner, text="把 exe 或桌面快捷方式\n直接拖进窗口就能收藏",
                 bg=T.BG_TAG, fg=T.TEXT_SUB, font=self.F["tiny"],
                 justify="left", anchor="w").pack(anchor="w", pady=(4, 0))

    def _render_groups(self):
        for w in self.group_box.winfo_children():
            w.destroy()
        # 固定三行（不可拖）
        fixed = [
            (S.G_ALL, "全部程序", "box", "#FF8A3D"),
            (S.G_FAV, "常用置顶", "star", "#FFC94D"),
            (S.G_RECENT, "最近打开", "clock", "#63C9F5"),
        ]
        self._group_rows = {}     # gid -> GroupRow
        for gid, name, emoji, color in fixed:
            row = W.GroupRow(self.group_box, gid, name, self.bank.get(emoji, 28),
                             self.store.count_of_group(gid),
                             self.cur_group == gid, self._select_group, None,
                             bg=T.BG_SIDE, draggable=False)
            row.pack(fill="x", padx=8, pady=1)
            self.group_scroll.attach(row)
            self._group_rows[gid] = row
        if self.store.groups:
            tk.Frame(self.group_box, bg=T.LINE, height=1).pack(fill="x", padx=20, pady=6)
        # 用户自建分类：可拖
        for g in self.store.groups:
            gid = g["id"]
            row = W.GroupRow(self.group_box, gid, g["name"],
                             self.bank.get(g.get("emoji", "folder2"), 28),
                             self.store.count_of_group(gid),
                             self.cur_group == gid, self._select_group,
                             self._group_menu, bg=T.BG_SIDE,
                             draggable=True, on_drop=self._on_group_drop,
                             locked_img=(self.bank.get("lock", 16)
                                         if self.store.group_locked(gid) else None))
            row.pack(fill="x", padx=8, pady=1)
            self.group_scroll.attach(row)
            self._group_rows[gid] = row
        # 拖拽时的插入指示条（默认隐藏）
        self._drop_bar = tk.Frame(self.group_box, height=2, bg=T.ACCENT_DK)
        self._drop_bar.place_forget()

    def _user_group_rows(self):
        """返回当前显示中、属于 store.groups 的 GroupRow，按 Y 从上到下排。
        拖拽指示条的位置 / 落点索引都靠它算。"""
        gids = {g["id"] for g in self.store.groups}
        rows = [r for gid, r in self._group_rows.items()
                if gid in gids and getattr(r, "draggable", False)]
        rows.sort(key=lambda r: r.winfo_rooty())
        return rows

    def _on_group_drop(self, phase, dragged_gid, x_root, y_root):
        """GroupRow 拖拽回调。phase: start / move / end / cancel。"""
        if phase == "start":
            # 进入拖拽：让其他 GroupRow 走 _leave 避免 hover 高亮和被点中
            return
        if phase == "move":
            idx = self._drop_index(y_root)
            self._show_drop_bar(idx)
            return
        if phase == "end":
            idx = self._drop_index(y_root)
            self._hide_drop_bar()
            self._reorder_group(dragged_gid, idx)
            return
        if phase == "cancel":
            self._hide_drop_bar()
            return

    def _drop_index(self, y_root):
        """根据当前光标 Y 算落点索引（在 store.groups 内，0..len）。
        在某行上半 → 插它前面；在下半 → 插它后面；超过最后一行 → 末尾。"""
        rows = self._user_group_rows()
        if not rows:
            return 0
        # 拖到分隔线以上 → 0；拖到末尾行下半之后 → len
        for i, r in enumerate(rows):
            if y_root < r.winfo_rooty() + r.winfo_height() / 2:
                return i
        return len(rows)

    def _show_drop_bar(self, idx):
        if not hasattr(self, "_drop_bar"):
            return
        rows = self._user_group_rows()
        if not rows:
            self._drop_bar.place_forget()
            return
        box_y = self.group_box.winfo_rooty()
        if idx >= len(rows):
            last = rows[-1]
            y = last.winfo_rooty() - box_y + last.winfo_height() - 1
        else:
            target = rows[idx]
            y = target.winfo_rooty() - box_y - 1
        self._drop_bar.place(x=8, y=y, width=self._group_w() - 16, height=2)
        self._drop_bar.lift()

    def _hide_drop_bar(self):
        if hasattr(self, "_drop_bar"):
            self._drop_bar.place_forget()

    def _group_w(self):
        try:
            return self.group_box.winfo_width()
        except Exception:
            return 196

    def _reorder_group(self, dragged_gid, new_idx):
        groups = self.store.groups
        cur = next((i for i, g in enumerate(groups) if g["id"] == dragged_gid), None)
        if cur is None:
            return
        # 同一位置或夹在自己前后一格就不动
        if new_idx == cur or new_idx == cur + 1:
            return
        g = groups.pop(cur)
        if new_idx > cur:
            new_idx -= 1
        groups.insert(new_idx, g)
        self.store.save()
        self._render_groups()
        self.refresh()

    # -------------------------------------------------- 主区
    def _build_main(self, parent):
        main = tk.Frame(parent, bg=T.BG_APP)
        main.pack(side="left", fill="both", expand=True)
        self.main = main

        bar = tk.Frame(main, bg=T.BG_APP, height=52)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        left = tk.Frame(bar, bg=T.BG_APP)
        left.pack(side="left", padx=(18, 0), pady=12)
        if self.bank.get("sparkles", 18) is not None:
            tk.Label(left, image=self.bank.get("sparkles", 18), bg=T.BG_APP).pack(side="left")
        self.lbl_count = tk.Label(left, text="", bg=T.BG_APP, fg=T.TEXT,
                                  font=self.F["body_b"])
        self.lbl_count.pack(side="left", padx=(6, 0))

        right = tk.Frame(bar, bg=T.BG_APP)
        right.pack(side="right", padx=(0, 18), pady=9)
        self.btn_sort = W.RoundButton(
            right, text="", emoji_img=self.bank.get("sort", 18), variant="plain",
            width=146, height=34, bg=T.BG_APP, command=self.menu_sort)
        self.btn_sort.pack(side="left", padx=(0, 8))
        self.btn_refresh = W.IconButton(right, self.bank.get("refresh", 28),
                                        command=self.refresh, size=34, bg=T.BG_APP,
                                        tip="刷新")
        self.btn_refresh.pack(side="left", padx=(0, 8))
        self.btn_view = W.IconButton(right, self.bank.get("grid", 28),
                                     command=self.toggle_view, size=34, bg=T.BG_APP,
                                     tip="切换视图")
        self.btn_view.pack(side="left")

        wrap = tk.Frame(main, bg=T.BG_APP)
        wrap.pack(fill="both", expand=True)
        self.area = W.ScrollArea(wrap, bg=T.BG_APP, padding=(18, 8, 22, 24))
        self.area.pack(fill="both", expand=True)
        self.area.canvas.bind("<Configure>", self._on_area_configure, add="+")
        self.area.inner.bind("<Button-3>", self._blank_menu)

    # -------------------------------------------------- 底栏
    def _build_footer(self):
        bar = tk.Frame(self.root, bg=T.BG_FOOT, height=30)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self.lbl_status = tk.Label(bar, text="", bg=T.BG_FOOT, fg=T.TEXT_SUB,
                                   font=self.F["small"], anchor="w")
        self.lbl_status.pack(side="left", padx=(20, 0), pady=6)
        self.lbl_data = tk.Label(bar, text="", bg=T.BG_FOOT, fg=T.TEXT_MUTED,
                                 font=self.F["tiny"], anchor="e")
        self.lbl_data.pack(side="right", padx=(0, 20), pady=6)
        self.toast = W.Toast(self.root)
        self._hit = tk.Label(self.main, text="", bg=T.BG_APP, fg=T.ACCENT_DK,
                             font=self.F["small_b"], anchor="center", pady=4)
        self.set_status("拖拽程序进窗口即可添加 · 单击卡片启动 · 右键查看更多操作", "info")

    def set_status(self, text, emoji="info"):
        self.lbl_status.configure(text=text)
        self.lbl_data.configure(text="数据目录：%s" % A.app_dir())

    # ================================================== 交互
    def _bind_keys(self):
        r = self.root
        r.bind("<F5>", lambda e: self.refresh())
        r.bind("<Control-n>", lambda e: self.dialog_add())
        r.bind("<Control-f>", lambda e: self._focus_search())
        r.bind("<Control-e>", lambda e: self.edit_selected())
        r.bind("<Delete>", lambda e: self.delete_selected())
        r.bind("<Return>", lambda e: self.open_selected())
        # 退出：Alt+F4 在部分 Tk/Windows 组合下收不到，
        # 另外给一个明确的快捷键和按钮，保证一定关得掉
        r.bind("<Control-q>", lambda e: self._quit())
        r.bind("<Configure>", self._on_root_configure, add="+")
        r.protocol("WM_DELETE_WINDOW", self._quit)

    def _on_root_configure(self, _=None):
        """窗口尺寸变化（含最大化/还原）的时间戳。"""
        self._resize_at = time.time()
        if self._repaint_deferred:
            return
        self._repaint_deferred = True
        try:
            self.root.after(360, self._repaint_later)
        except Exception:
            self._repaint_deferred = False

    def _repaint_later(self):
        self._repaint_deferred = False
        if getattr(self, "_closing", False):
            return
        self._force_repaint()

    def _focus_search(self):
        try:
            self.entry_search.focus_set()
        except Exception:
            pass

    def _clear_search(self):
        self.var_search.set("")
        self._draw_search_box()

    def _on_search(self):
        self.keyword = self.var_search.get().strip()
        self._draw_search_box()
        self.refresh(reset_scroll=True)

    def _select_group(self, gid):
        if gid == self.cur_group:
            return
        # 加密分类：先过密码，输对后 24 小时内不再询问
        if self.store.group_locked(gid):
            dlg = GroupPasswordDialog(self.root, self.bank, self.store, gid)
            if not dlg.show():
                return
            self._render_groups()
            self.toast.show("已解锁，24 小时内免输密码",
                            self.bank.get("key", 18))
        self.cur_group = gid
        self.selected_id = None
        # 记住当前分类，下次启动直接进入这里
        try:
            self.store.settings["last_group"] = gid
            self.store.save()
        except Exception:
            pass
        # 只切换高亮，不整栏重建（重建 6 行 GroupRow 有几十毫秒的抖动）
        rows = getattr(self, "_group_rows", {})
        if rows and gid in rows:
            for rgid, row in rows.items():
                row.set_selected(rgid == gid)
        else:
            self._render_groups()
        self.refresh()

    def toggle_view(self):
        cur = self.store.settings.get("view", "grid")
        nxt = "list" if cur == "grid" else "grid"
        self.store.settings["view"] = nxt
        self.store.save()
        self.refresh()
        self.set_status("已切换为「%s」" % ("卡片视图" if nxt == "grid" else "紧凑视图"))

    # ================================================== 卡片渲染
    def refresh(self, reset_scroll=True):
        # 不 clear 图标缓存：磁盘图标文件基本不变，缓存的 tk.PhotoImage
        # 可以跨 refresh 复用。之前每次 refresh 都清空 → 每张 PNG 都要
        # 重新解码，是切换分类卡顿的主因之一。
        items = self.store.visible_items(self.cur_group, self.keyword, self._sort)
        gname = {S.G_ALL: "全部程序", S.G_FAV: "常用置顶", S.G_RECENT: "最近打开"}.get(
            self.cur_group, self.store.group_name(self.cur_group))
        self.lbl_count.configure(text="%s · 共 %d 个程序" % (gname, len(items)))
        self.btn_sort.set_text("排序：%s" % dict((k, v) for k, v, _ in SORT_LABELS).get(self._sort, "自定义顺序"))

        if not items:
            # 空态：只在第一次构建，之后复用（反复 destroy/build 是切分类卡顿元凶）
            self._hide_cards()
            self._show_empty()
            if reset_scroll:
                self.area.scroll_top()
            return

        self._hide_empty()
        # 卡片池复用：已有卡片够用就不重建控件，只把数据 bind 进去。
        if not self.cards or self.cards[0].master is not self.area.inner:
            if self.cards:
                for c in self.cards:
                    try:
                        c.destroy()
                    except Exception:
                        pass
            self.cards = []
            self._last_cols = -1

        n_have = len(self.cards)
        n_need = len(items)
        self._visible_n = n_need
        for idx, app in enumerate(items):
            img = self.icon_bank.get(app.get("icon"), 48)
            emo = None
            if img is None:
                emo = self.bank.get(app.get("emoji") or "rocket", 40)
            gn = self.store.group_name(app.get("group"))
            if idx < n_have:
                self.cards[idx].rebind(app, T.card_color(idx), img, emo, gn)
            else:
                card = W.AppCard(self.area.inner, app, T.card_color(idx), img, emo,
                                 self.launch, self._card_menu, self._select_card,
                                 self._hover_card, bg=T.BG_APP, group_name=gn)
                self.area.attach(card)
                self.cards.append(card)
        # 多余的卡片藏起来（不销毁，留给下次复用）
        for c in self.cards[n_need:]:
            c.grid_forget()
        self._layout_cards(visible=n_need)
        if reset_scroll:
            self.area.scroll_top()

    def _show_empty(self):
        """显示空态（首次才真正构建，之后只 pack/forget）。"""
        if getattr(self, "_empty_frame", None) is None:
            self._build_empty()
        try:
            self._empty_frame.pack(pady=(70, 0))
            self._empty_showing = True
        except Exception:
            pass

    def _hide_empty(self):
        self._empty_showing = False
        ef = getattr(self, "_empty_frame", None)
        if ef is not None:
            try:
                ef.pack_forget()
            except Exception:
                pass

    def _hide_cards(self):
        for c in self.cards:
            try:
                c.grid_forget()
            except Exception:
                pass
        # 布局缓存作废，保证下次显示时一定会重新 grid
        self._laid_out = False
        self._laid_n = -1
        self._visible_n = 0
        self._last_cols = -1

    def _build_empty(self):
        f = self._empty_frame = tk.Frame(self.area.inner, bg=T.BG_APP)
        big = self.bank.get("balloon", 56)
        if big is not None:
            tk.Label(f, image=big, bg=T.BG_APP).pack()
        tk.Label(f, text="这里还空空的", bg=T.BG_APP, fg=T.TEXT,
                 font=(T.UI_FONT, 15, "bold")).pack(pady=(12, 4))
        tk.Label(f, text="把 exe 或桌面快捷方式拖进来，或者点下面的按钮挑一个",
                 bg=T.BG_APP, fg=T.TEXT_SUB, font=self.F["small"]).pack()
        W.RoundButton(f, text="添加程序", emoji_img=self.bank.get("plus", 18),
                      variant="primary", width=150, height=40, bg=T.BG_APP,
                      command=self.dialog_add).pack(pady=18)
        row = tk.Frame(f, bg=T.BG_APP)
        row.pack()
        for name, tip in (("rocket", "单击启动"), ("pencil", "右键编辑"),
                          ("folder", "打开位置"), ("shield", "管理员运行")):
            img = self.bank.get(name, 28)
            if img is None:
                continue
            cell = tk.Frame(row, bg=T.BG_APP)
            cell.pack(side="left", padx=10)
            tk.Label(cell, image=img, bg=T.BG_APP).pack()
            tk.Label(cell, text=tip, bg=T.BG_APP, fg=T.TEXT_MUTED,
                     font=self.F["tiny"]).pack()

    def _draw_empty(self):
        """兼容旧调用：显示空态。"""
        self._hide_cards()
        self._show_empty()

    # -------------------------------------------------- 卡片布局
    def _on_area_configure(self, _=None):
        if self._layout_pending:
            return
        self._layout_pending = True
        try:
            self.root.after_idle(self._flush_layout)
        except Exception:
            self._layout_pending = False

    def _flush_layout(self):
        self._layout_pending = False
        try:
            self._layout_cards()
        except Exception:
            pass

    def _layout_cards(self, visible=None):
        if not self.cards:
            return
        # 空态用的是 pack，卡片用的是 grid；同一个父容器不能混用。
        # 空态显示期间（尤其是窗口最大化触发 <Configure>）绝不能去 grid。
        if getattr(self, "_empty_showing", False):
            return
        # 始终只排当前分类可见的那几张：self.cards 是复用池，池里还留着
        # 其它分类的卡片（已被 grid_forget）。若这里按 len(self.cards) 排，
        # 最大化触发重排时会把它们全部重新 grid 出来 —— 分类里突然冒出
        # 全部程序，点一下别的分类才恢复，就是这个原因。
        n = getattr(self, "_visible_n", 0) if visible is None else visible
        self._visible_n = n
        # 按「卡片区实际能放下几列」来算，别再强制至少 7 列 ——
        # 小屏（比如 1200x720）上强制 7 列会让第 7 列被裁掉，
        # 卡片既点不到，多出来的宽度还会让每次重排更慢。
        step = W.AppCard.W + 8
        avail = max(step, self.area.canvas.winfo_width() - 40)
        cols = max(1, min(self.MAX_COLS, int(avail // step)))
        if cols == self._last_cols and getattr(self, "_laid_out", False) \
                and n == getattr(self, "_laid_n", -1):
            return
        self._last_cols = cols
        self._laid_n = n
        self._laid_out = True
        for i, c in enumerate(self.cards):
            if i >= n:
                continue
            c.grid(row=i // cols, column=i % cols, padx=4, pady=5, sticky="nw")

    def _select_card(self, app):
        self.selected_id = app.get("id")
        for c in self.cards:
            c.set_selected(c.app.get("id") == self.selected_id)

    def _show_hit(self, show):
        if self._hit is None:
            return
        # 用 place 浮层而不是 pack：pack 会挤动整片卡片区，鼠标每次
        # 进 / 出窗口都要把几百张卡重排一遍，肉眼就是一次明显卡顿。
        if show:
            self._hit.configure(text="⬇  松开鼠标即可把程序添加进来",
                                bg=T.BG_TAG, fg=T.ACCENT_DK)
            try:
                self._hit.place(relx=0.5, rely=1.0, y=-14, anchor="s")
                self._hit.lift()
            except Exception:
                pass
        else:
            try:
                self._hit.place_forget()
            except Exception:
                pass

    def _hover_card(self, app, entering):
        if entering:
            self.lbl_status.configure(text=app.get("path", ""))
        else:
            self.set_status("拖拽程序进窗口即可添加 · 单击卡片启动 · 右键查看更多操作")

    # ================================================== 启动 / 打开
    def launch(self, app, admin=False):
        path = app.get("path", "")
        args = (app.get("args") or "").strip()
        # 老数据兜底：还是 .lnk 的就地解析，之后直接记绝对路径
        if path.lower().endswith(".lnk") and os.path.isfile(path):
            ind = linkfix.independent(path)
            if ind:
                app["path"] = path = ind["path"]
                if ind["args"] and not args:
                    app["args"] = args = ind["args"]
                app["workdir"] = ind["cwd"]
                app["lnk"] = ind["lnk"]
                self.store.save()
        if not path or not os.path.exists(path):
            self.toast.show("文件不存在：%s" % path, self.bank.get("warn", 18))
            return
        cwd = app.get("workdir") or os.path.dirname(path)
        try:
            ok = spawner.run(path, args, cwd, admin=admin)
        except Exception as e:
            self.toast.show("启动失败：%s" % e, self.bank.get("cross", 18))
            return
        if not ok:
            self.toast.show("已取消管理员启动" if admin else "启动失败",
                            self.bank.get("warn", 18))
            return
        self.store.record_launch(app.get("id"))
        self.toast.show("已启动 %s" % app.get("name", ""), self.bank.get("rocket", 18))
        if self._sort in ("count", "recent"):
            self.root.after(400, self.refresh)

    def open_location(self, app):
        p = app.get("path", "")
        if p and os.path.exists(p):
            try:
                A.open_in_explorer(p)
            except Exception:
                os.startfile(os.path.dirname(p))
        else:
            self.toast.show("路径不存在", self.bank.get("warn", 18))

    def copy_path(self, app):
        self.root.clipboard_clear()
        self.root.clipboard_append(app.get("path", ""))
        self.toast.show("已复制完整路径", self.bank.get("clipboard", 18))

    # ================================================== 右键菜单
    def _menu(self):
        m = tk.Menu(self.root, tearoff=0, bg="#FFFFFF", fg=T.TEXT,
                    activebackground=T.BG_SEL, activeforeground=T.ACCENT_DK,
                    bd=0, relief="flat", font=self.F["menu"])
        return m

    def _mi(self, menu, label, emoji=None, command=None, submenu=None, accel=None):
        kw = {"label": " " + label, "command": command, "font": self.F["menu"]}
        if accel:
            kw["accelerator"] = accel
        if submenu is not None:
            kw["menu"] = submenu
            kw.pop("command", None)
        img = self.bank.get(emoji, 18) if emoji else None
        if img is not None:
            kw["image"] = img
            kw["compound"] = "left"
        menu.add_cascade(**kw) if submenu is not None else menu.add_command(**kw)
        return menu

    def _card_menu(self, app, x, y):
        m = self._menu()
        self._mi(m, "启动程序", "rocket", lambda: self.launch(app), accel="单击")
        self._mi(m, "以管理员身份运行", "shield", lambda: self.launch(app, True))
        self._mi(m, "打开所在位置", "folder", lambda: self.open_location(app))
        self._mi(m, "复制完整路径", "clipboard", lambda: self.copy_path(app))
        m.add_separator()
        self._mi(m, "编辑程序信息…", "pencil", lambda: self.dialog_edit(app))
        self._mi(m, "取消置顶" if app.get("pinned") else "置顶到最前", "pin",
                 lambda: self._toggle_pin(app))

        sub = self._menu()
        for g in self.store.groups:
            img = self.bank.get(g.get("emoji", "folder2"), 18)
            kw = {"label": " " + g["name"],
                  "command": (lambda gid=g["id"]: self._move_to(app, gid))}
            if img is not None:
                kw["image"] = img
                kw["compound"] = "left"
            sub.add_command(**kw)
        self._mi(m, "移动到分类", "tag", submenu=sub)

        sub2 = self._menu()
        self._mi(sub2, "从文件重新提取图标", "refresh",
                 lambda: self._reload_icon(app))
        self._mi(sub2, "换成彩色 emoji", "palette",
                 lambda: self._pick_emoji_for(app))
        self._mi(m, "更换图标", "palette", submenu=sub2)
        m.add_separator()
        self._mi(m, "删除这个程序", "trash", lambda: self.delete_app(app))
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    def _blank_menu(self, event):
        m = self._menu()
        self._mi(m, "添加程序…", "plus", self.dialog_add, accel="Ctrl+N")
        self._mi(m, "从剪贴板添加路径", "clipboard", self.add_from_clipboard)
        self._mi(m, "刷新列表", "refresh", self.refresh, accel="F5")
        m.add_separator()
        sub = self._menu()
        for key, label, emoji in SORT_LABELS:
            img = self.bank.get(emoji, 18)
            kw = {"label": " " + label + ("   ✓" if key == self._sort else ""),
                  "command": (lambda k=key: self.set_sort(k))}
            if img is not None:
                kw["image"] = img
                kw["compound"] = "left"
            sub.add_command(**kw)
        self._mi(m, "排序方式", "sort", submenu=sub)
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def menu_sort(self):
        m = self._menu()
        for key, label, emoji in SORT_LABELS:
            img = self.bank.get(emoji, 18)
            kw = {"label": " " + label + ("   ✓" if key == self._sort else ""),
                  "command": (lambda k=key: self.set_sort(k))}
            if img is not None:
                kw["image"] = img
                kw["compound"] = "left"
            m.add_command(**kw)
        x = self.btn_sort.winfo_rootx()
        y = self.btn_sort.winfo_rooty() + self.btn_sort.winfo_height()
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    def menu_settings(self):
        m = self._menu()
        self._mi(m, "打开数据目录", "folder", lambda: A.open_in_explorer(A.app_dir()))
        self._mi(m, "导出收藏数据…", "export", self.do_export)
        self._mi(m, "导入收藏数据…", "import", self.do_import)
        m.add_separator()
        self._mi(m, "整理重复项", "magic", self.dedupe)
        self._mi(m, "重新提取全部图标", "refresh", self.rebuild_icons)
        m.add_separator()
        self._mi(m, "检查更新…", "cloud", self.check_update)
        self._mi(m, "关于 %s" % S.APP_TITLE, "info", self.about)
        x = self.btn_settings.winfo_rootx() - 90
        y = self.btn_settings.winfo_rooty() + self.btn_settings.winfo_height()
        try:
            m.tk_popup(max(0, x), y)
        finally:
            m.grab_release()

    def _group_menu(self, gid, name, x, y):
        m = self._menu()
        self._mi(m, "重命名分类…", "pencil", lambda: self.dialog_edit_group(gid))
        self._mi(m, "换个图标 / 颜色…", "palette",
                 lambda: self.dialog_edit_group(gid, focus_icon=True))
        g = self.store.group_by_id(gid) or {}
        self._mi(m, "修改打开密码…" if g.get("password") else "设置打开密码…",
                 "lock", lambda: self.dialog_edit_group(gid, focus_pw=True))
        m.add_separator()
        self._mi(m, "删除这个分类", "trash", lambda: self.delete_group(gid, name))
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    # ================================================== 增删改
    def set_sort(self, key):
        self._sort = key
        self.store.settings["sort"] = key
        self.store.save()
        self.refresh()

    def _toggle_pin(self, app):
        self.store.update_app(app["id"], pinned=not app.get("pinned"))
        self.refresh()
        self.set_status("已%s「%s」" % ("取消置顶" if app.get("pinned") else "置顶",
                                    app.get("name", "")))

    def _move_to(self, app, gid):
        self.store.update_app(app["id"], group=gid)
        self.refresh()
        self.toast.show("已移动到「%s」" % self.store.group_name(gid),
                        self.bank.get("tag", 18))

    def _reload_icon(self, app):
        got = iconutil.extract_icon(app.get("path", ""))
        if not got:
            self.toast.show("没能提取到图标，已保留原图标",
                            self.bank.get("warn", 18))
            return
        fn = self.store.cache_icon(got)
        if not fn:
            self.toast.show("图标缓存失败，已保留原图标",
                            self.bank.get("warn", 18))
            return
        self.store.update_app(app["id"], icon=fn, iconv=S.ICON_FORMAT)
        self.icon_bank.clear()
        self.refresh()
        self.toast.show("图标已更新", self.bank.get("check", 18))

    def _pick_emoji_for(self, app):
        dlg = W.EmojiPickerDialog(self.root, self.bank, app.get("emoji"),
                                  "给「%s」选个图标" % app.get("name", ""))
        got = dlg.show()
        if got:
            self.store.update_app(app["id"], emoji=got, icon="")
            self.refresh()
            self.toast.show("图标已换成 emoji", self.bank.get("palette", 18))

    def delete_app(self, app):
        dlg = W.ConfirmDialog(
            self.root, self.bank, "删除程序",
            "确定要从收藏里删除「%s」吗？" % app.get("name", ""),
            "只删除收藏记录，不会删除电脑上的原文件。\n%s" % app.get("path", ""))
        if dlg.show():
            self.store.remove_app(app["id"])
            self.icon_bank.clear()
            self.refresh()
            self._render_groups()
            self.toast.show("已删除", self.bank.get("trash", 18))

    def delete_selected(self):
        app = self.store.get(self.selected_id)
        if app:
            self.delete_app(app)

    def edit_selected(self):
        app = self.store.get(self.selected_id)
        if app:
            self.dialog_edit(app)
        else:
            self.toast.show("先用鼠标点一下要编辑的卡片",
                            self.bank.get("eyes", 18))

    def open_selected(self):
        app = self.store.get(self.selected_id)
        if app:
            self.launch(app)

    def delete_group(self, gid, name):
        n = self.store.count_of_group(gid)
        dlg = W.ConfirmDialog(
            self.root, self.bank, "删除分类",
            "确定删除分类「%s」吗？" % name,
            "该分类下的 %d 个程序不会被删除，会移动到「%s」。" % (n, self.store.group_name("g_default")))
        if dlg.show():
            self.store.remove_group(gid)
            if self.cur_group == gid:
                self.cur_group = S.G_ALL
            # 被删的分类若正是记住的上次分类，同步回退到「全部程序」
            if self.store.settings.get("last_group") == gid:
                self.store.settings["last_group"] = S.G_ALL
                self.store.save()
            self._render_groups()
            self.refresh()
            self.toast.show("分类已删除", self.bank.get("trash", 18))

    def add_from_clipboard(self):
        try:
            txt = self.root.clipboard_get()
        except Exception:
            txt = ""
        paths = [l.strip().strip('"') for l in txt.splitlines() if l.strip()]
        if not paths:
            self.toast.show("剪贴板里没有路径", self.bank.get("warn", 18))
            return
        self.add_paths(paths)

    # ================================================== 添加程序
    def add_paths(self, paths, group=None):
        added, dup, bad = 0, 0, 0
        self.set_status("正在添加并提取图标…")
        self.root.update_idletasks()
        for p in paths:
            p = os.path.normpath(p.strip().strip('"'))
            if not os.path.isfile(p):
                bad += 1
                continue
            # .lnk 在这里就解析成真实目标的绝对路径：之后删掉桌面图标也不影响
            ind = linkfix.independent(p)
            if ind is None:
                target, largs, wdir, icon_src, src_lnk = p, "", "", p, ""
            else:
                target = ind["path"]
                largs = ind["args"]
                wdir = ind["cwd"]
                icon_src = ind["icon_src"]
                src_lnk = ind["lnk"]
            if self.store.find_by_path(target) or self.store.find_by_lnk(p):
                dup += 1
                continue
            it = self.store.add_app(target, group=group or self._default_group(),
                                    args=largs, workdir=wdir, lnk=src_lnk)
            it["name"] = os.path.splitext(os.path.basename(p))[0]
            it["emoji"] = guess_emoji(p)
            got = iconutil.extract_icon(icon_src)
            if got:
                it["icon"] = self.store.cache_icon(got)
            added += 1
        self.store.save()
        self.icon_bank.clear()
        self.refresh()
        self._render_groups()
        if added:
            msg = "已添加 %d 个程序" % added
            if dup:
                msg += "，跳过 %d 个重复" % dup
            if bad:
                msg += "，%d 个不是有效文件" % bad
            self.toast.show(msg, self.bank.get("check", 18))
        elif dup:
            self.toast.show("这些程序已经在收藏里了（跳过 %d 个）" % dup,
                            self.bank.get("info", 18))
        else:
            self.toast.show("没有找到可添加的程序", self.bank.get("warn", 18))
        self.set_status("拖拽程序进窗口即可添加 · 双击卡片启动 · 右键查看更多操作")

    def _default_group(self):
        if self.cur_group not in (S.G_ALL, S.G_FAV, S.G_RECENT):
            return self.cur_group
        for g in self.store.groups:
            if g["id"] == "g_default":
                return g["id"]
        return self.store.groups[0]["id"] if self.store.groups else "g_default"

    def dialog_add(self):
        paths = filedialog.askopenfilenames(
            title="选择要收藏的程序（可多选）",
            filetypes=[("程序 / 快捷方式", "*.exe;*.lnk;*.bat;*.cmd;*.com;*.msc;*.ps1;*.url;*.jar"),
                       ("所有文件", "*.*")])
        if paths:
            self.add_paths(list(paths))

    # ================================================== 编辑对话框
    def dialog_edit(self, app):
        # 注意 master 必须传 self.root（真正的 Tk 窗口）。
        # Launcher 本身是普通对象，不是 Tk 控件，传 self 会在
        # tk.Toplevel.__init__ 里 AttributeError，windowed 模式下
        # 没有控制台能看到堆栈 → 表现为「点了没反应」。
        dlg = AppDialog(self.root, self.bank, self.icon_bank, self.store, app)
        if dlg.show():
            self.icon_bank.clear()
            self.refresh()
            self._render_groups()
            self.toast.show("已保存修改", self.bank.get("save", 18))

    def dialog_add_group(self):
        dlg = GroupDialog(self.root, self.bank, self.store, None)
        if dlg.show():
            self._render_groups()
            self.refresh()

    def dialog_edit_group(self, gid, focus_icon=False, focus_pw=False):
        g = self.store.group_by_id(gid)
        if not g:
            return
        dlg = GroupDialog(self.root, self.bank, self.store, g, focus_icon, focus_pw)
        if dlg.show():
            self._render_groups()
            self.refresh()

    # ================================================== 数据操作
    def do_export(self):
        p = filedialog.asksaveasfilename(
            title="导出收藏数据", defaultextension=".json",
            initialfile="程序收藏_%s.json" % __import__("time").strftime("%Y%m%d_%H%M"),
            filetypes=[("JSON 数据", "*.json")])
        if not p:
            return
        try:
            self.store.export_to(p)
            self.toast.show("已导出到 %s" % os.path.basename(p),
                            self.bank.get("export", 18))
        except Exception as e:
            self.toast.show("导出失败：%s" % e, self.bank.get("cross", 18))

    def do_import(self):
        p = filedialog.askopenfilename(title="导入收藏数据",
                                       filetypes=[("JSON 数据", "*.json"),
                                                  ("所有文件", "*.*")])
        if not p:
            return
        try:
            n = self.store.import_from(p, merge=True)
            self.icon_bank.clear()
            self.refresh()
            self._render_groups()
            self.toast.show("已导入 %d 个程序" % n, self.bank.get("import", 18))
        except Exception as e:
            self.toast.show("导入失败：%s" % e, self.bank.get("cross", 18))

    def dedupe(self):
        seen = {}
        drop = []
        for it in self.store.items:
            key = os.path.normcase(os.path.abspath(it.get("path", "")))
            if key in seen:
                drop.append(it)
            else:
                seen[key] = it
        if not drop:
            self.toast.show("没有发现重复项", self.bank.get("check", 18))
            return
        dlg = W.ConfirmDialog(self.root, self.bank, "整理重复项",
                              "发现 %d 个重复收藏，要清理掉吗？" % len(drop),
                              "只删除重复的收藏记录，不会动原文件。")
        if dlg.show():
            ids = {i["id"] for i in drop}
            self.store.items = [i for i in self.store.items if i["id"] not in ids]
            self.store.save()
            self.refresh()
            self._render_groups()
            self.toast.show("已清理 %d 个重复项" % len(drop), self.bank.get("magic", 18))

    def rebuild_icons(self):
        dlg = W.ConfirmDialog(self.root, self.bank, "重新提取图标",
                              "要为全部 %d 个程序重新提取图标吗？" % len(self.store.items),
                              "会从原文件重新抓一遍图标，可能需要几秒钟。", danger=False)
        if not dlg.show():
            return
        n = 0
        for it in self.store.items:
            got = iconutil.extract_icon(it.get("path", ""))
            if got:
                it["icon"] = self.store.cache_icon(got)
                n += 1
            it["iconv"] = S.ICON_FORMAT
        self.store.save()
        self.icon_bank.clear()
        self.refresh()
        self.toast.show("已刷新 %d 个图标" % n, self.bank.get("refresh", 18))

    def about(self):
        dlg = W.BaseDialog(self.root, "关于 %s" % S.APP_TITLE,
                           emoji_img=self.bank.get("info", 28),
                           width=470, height=350,
                           subtitle="版本 %s" % S.APP_VERSION)
        wrap = tk.Frame(dlg.body, bg=T.BG_APP)
        wrap.pack(fill="both", expand=True, padx=26, pady=18)
        if self.logo_img is not None:
            tk.Label(wrap, image=self.logo_img, bg=T.BG_APP).pack(anchor="w")
        for line in (
            "一个卡通风格的程序收藏夹：把常用的 exe、桌面快捷方式拖进来，",
            "单击即可启动，右键可以编辑、删除、分类、换图标。",
            "",
            "软件作者：%s" % S.AUTHOR,
            "",
            "数据目录：%s" % A.app_dir(),
            "数据文件：apps_data.json    图标缓存：icons/",
            "",
            "整个文件夹拷到别的电脑就能直接用，无需安装。",
        ):
            tk.Label(wrap, text=line, bg=T.BG_APP, fg=T.TEXT_SUB,
                     font=self.F["small"], anchor="w", justify="left").pack(anchor="w")
        dlg.add_footer_buttons(ok_text="知道了", cancel_text="打开数据目录",
                               ok_emoji=self.bank.get("check", 18),
                               cancel_emoji=self.bank.get("folder", 18))
        dlg.show()

    # ================================================== 在线升级（Gitee 发布页）
    def check_update(self):
        """手动检查更新：后台线程拉最新 Release，按版本号比大小。"""
        self.toast.show("正在检查更新…", self.bank.get("cloud", 18))

        def work():
            try:
                avail, info = updater.check_for_update(S.UPDATE_APIS,
                                                       S.APP_VERSION)
            except Exception as e:
                avail, info = False, {"error": "检查更新失败：%s" % e}
            self.root.after(0, lambda: self._on_update_checked(avail, info))

        threading.Thread(target=work, daemon=True).start()

    def _on_update_checked(self, avail, info):
        if info.get("error"):
            self.toast.show(info["error"], self.bank.get("cross", 18))
            return
        if not avail:
            self.toast.show("已经是最新版本 (%s)" % S.APP_VERSION,
                            self.bank.get("check", 18))
            return
        # 有新版：弹确认框
        dlg = W.BaseDialog(self.root, "发现新版本",
                           emoji_img=self.bank.get("cloud", 28),
                           width=460, height=280,
                           subtitle="最新版本 %s" % info.get("version", ""))
        wrap = tk.Frame(dlg.body, bg=T.BG_APP)
        wrap.pack(fill="both", expand=True, padx=26, pady=18)
        patch_size = info.get("patch_size", 0)
        lines = [
            "当前版本：%s" % S.APP_VERSION,
            "最新版本：%s" % info.get("version", ""),
        ]
        if info.get("patch_url"):
            lines.append("增量更新包：%s（只下载变化的部分）"
                         % updater.human_size(patch_size))
            lines.append("完整安装包：%s" % updater.human_size(info.get("size", 0)))
        else:
            lines.append("安装包大小：%s" % updater.human_size(info.get("size", 0)))
        lines += ["", "是否立即下载并更新到最新版？"]
        for t in lines:
            tk.Label(wrap, text=t, bg=T.BG_APP, fg=T.TEXT_SUB,
                     font=self.F["small"], anchor="w").pack(anchor="w", pady=2)
        dlg.add_footer_buttons(ok_text="立即升级", cancel_text="稍后再说",
                               ok_emoji=self.bank.get("cloud", 18),
                               cancel_emoji=self.bank.get("cross", 18))
        dlg.show()
        if dlg._result:
            self.do_update(info)

    def do_update(self, info):
        """优先下载增量补丁，合并成本地新 exe；没有补丁则回退整包下载。"""
        url = info.get("url", "")
        patch_url = info.get("patch_url", "")
        if not url and not patch_url:
            self.toast.show("没有可用的下载地址", self.bank.get("cross", 18))
            return
        real = updater.real_exe_path()
        d = os.path.dirname(real) or "."
        new_exe = os.path.join(d, "程序收纳盒.new")
        patch_file = os.path.join(d, "程序收纳盒.patch")

        # 进度窗口（非阻塞：不调用 show() 的 wait_window）
        dlg = W.BaseDialog(self.root, "正在升级",
                           emoji_img=self.bank.get("cloud", 28),
                           width=440, height=170,
                           subtitle="下载更新中…")
        wrap = tk.Frame(dlg.body, bg=T.BG_APP)
        wrap.pack(fill="both", expand=True, padx=26, pady=18)
        lab = tk.Label(wrap, text="准备下载…", bg=T.BG_APP, fg=T.TEXT_SUB,
                       font=self.F["small"], anchor="w")
        lab.pack(anchor="w", pady=(0, 10))
        pb = ttk.Progressbar(wrap, orient="horizontal", length=360, mode="determinate")
        pb.pack(fill="x")
        dlg.update_idletasks()
        w = max(dlg._dw, dlg.winfo_reqwidth())
        h = max(dlg._dh, dlg.winfo_reqheight())
        dlg.geometry("%dx%d" % (w, h))
        dlg._center(self.root, w, h)
        # 下载/合并期间禁止关闭，避免半截升级
        dlg.protocol("WM_DELETE_WINDOW", lambda: None)
        dlg.bind("<Escape>", lambda e: None)
        dlg.deiconify(); dlg.lift(); dlg.grab_set(); dlg.focus_force()

        def work():
            if int(pb["value"]) and pb["mode"] == "indeterminate":
                pb.stop()
            used_patch = False
            if patch_url:
                try:
                    lab2 = "下载增量补丁…"

                    def prog_patch(got, total):
                        self.root.after(0, lambda: self._update_progress(
                            lab, pb, got, total, lab2))

                    updater.download_file(patch_url, patch_file,
                                          on_progress=prog_patch)
                    self.root.after(0, lambda: self._update_progress(
                        lab, pb, 0, 0, "正在合并更新…"))
                    delta.apply_patch(
                        real, patch_file, new_exe,
                        on_progress=lambda got, total: self.root.after(
                            0, lambda: self._update_progress(
                                lab, pb, got, total, "正在合并更新…")))
                    used_patch = True
                except Exception:
                    used_patch = False
                    try:
                        os.remove(patch_file)
                    except Exception:
                        pass
            if not used_patch:
                if not url:
                    self.root.after(0, lambda: self._update_error(
                        dlg, "增量合并失败，且没有可用的完整安装包"))
                    return
                self.root.after(0, lambda: self._update_progress(
                    lab, pb, 0, 0, "下载完整安装包…"))

                def prog_full(got, total):
                    self.root.after(0, lambda: self._update_progress(
                        lab, pb, got, total, "下载完整安装包…"))

                try:
                    updater.download_file(url, new_exe, on_progress=prog_full)
                except Exception as e:
                    self.root.after(0, lambda: self._update_error(dlg, str(e)))
                    return
            try:
                os.remove(patch_file)
            except Exception:
                pass
            self.root.after(0, lambda: self._finish_update(dlg, new_exe, real))

        threading.Thread(target=work, daemon=True).start()

    def _update_progress(self, lab, pb, got, total, prefix="下载中…"):
        if total:
            pb["mode"] = "determinate"
            pb["value"] = int(got * 100.0 / total)
            lab["text"] = "%s %d%%  (%s / %s)" % (
                prefix, int(got * 100.0 / total),
                updater.human_size(got), updater.human_size(total))
        else:
            pb["mode"] = "indeterminate"
            if prefix != getattr(self, "_pb_prefix", None):
                self._pb_prefix = prefix
                pb.start(20)
            lab["text"] = prefix

    def _update_error(self, dlg, msg):
        if dlg.winfo_exists():
            dlg.destroy()
        self.toast.show("升级失败：%s" % msg, self.bank.get("cross", 18))

    def _finish_update(self, dlg, new_exe, real):
        try:
            if not os.path.isfile(new_exe) or os.path.getsize(new_exe) < 1024 * 1024:
                raise RuntimeError("更新文件不完整")
            script = updater.make_updater_script(real, new_exe)
            wscript = os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                                   "System32", "wscript.exe")
            if not os.path.isfile(wscript):
                wscript = "wscript.exe"
            # 必须真的把这个助手跑起来：之前只写了脚本没启动，程序退出后
            # 什么都没发生，所以再次打开还是旧版本。
            # 环境要洗干净：本进程是单文件 exe 解出来的子进程，带着
            # _PYI_* / TCL_LIBRARY / TK_LIBRARY 这些指向自己临时目录的变量，
            # 直接继承给 wscript 再继承给新 exe，新实例可能去已经删掉的
            # _MEIxxxx 里找 python312.dll，报「Failed to load Python DLL」。
            import subprocess
            junk = ("_PYI_", "_MEI", "MEIPASS", "PYTHONHOME", "PYTHONPATH",
                    "TCL_LIBRARY", "TK_LIBRARY")
            env = {k: v for k, v in os.environ.items()
                   if not any(s in k.upper() for s in junk)}
            subprocess.Popen([wscript, "//B", "//Nologo", script],
                             close_fds=True, env=env,
                             creationflags=0x00000008 | 0x00000200)
        except Exception as e:
            if dlg.winfo_exists():
                dlg.destroy()
            self.toast.show("升级准备失败：%s" % e, self.bank.get("cross", 18))
            return
        if dlg.winfo_exists():
            dlg.destroy()
        # 退出主循环，把覆盖 + 重启交给 update_helper.vbs
        self._quit()

    # ================================================== 拖拽
    def _real_toplevel_hwnd(self):
        """返回本进程真正承载界面的顶层窗口句柄（调试/兼容用）。"""
        try:
            dnd = __import__("dnd")
            return dnd.root_hwnd(self.root.winfo_id(),
                                 self.root.title())
        except Exception:
            return self.root.winfo_id()

    def _hook_dnd(self):
        self.dnd_ok = False
        self._dnd = None
        self._closing = False
        try:
            import dnd
            # 注意三点：
            #  1) 窗口过程回调里不能碰 Tk，所以 DragDrop 只负责收文件，
            #     真正的处理由 _poll_dnd 在自己的 after 里做。
            #  2) Tk 的 winfo_id() 是内部子窗口，拖拽真正落在另一个
            #     类名为 TkTopLevel 的顶层窗口上。
            #  3) 标题是在 __init__ 之后才 set 的，第一次挂可能还认不出
            #     顶层窗口，所以用 attach_to 补挂几次。
            self._dnd = dnd.DragDrop(self.root.winfo_id(), self._on_drop,
                                     title=self.root.title(),
                                     on_close=self._quit)
            self._dnd.attach_to(num_retries=8, delay_ms=300,
                                scheduler=lambda fn, ms: self.root.after(ms, fn))
            self.dnd_ok = bool(self._dnd._win)
        except Exception:
            self.dnd_ok = False
        self.root.after(100, self._poll_dnd)
        # 鼠标进入/离开窗口时给出拖拽引导提示
        self.root.bind("<Enter>", lambda e: self._show_hit(True))
        self.root.bind("<Leave>", lambda e: self._show_hit(False))
        self.root.bind("<FocusOut>", lambda e: self._show_hit(False))

    def _poll_dnd(self):
        if self._dnd is None or self._closing:
            return
        try:
            self._dnd.poll()
        except Exception:
            pass
        # 窗口被重新显示（最小化再恢复 / 切回前台）：补一次全窗重绘。
        # 不补的话整块客户区会停在黑底，只有鼠标划过的控件才会补画。
        if getattr(self._dnd, "needs_repaint", False):
            self._dnd.needs_repaint = False
            self._force_repaint()
        # 窗口过程没触发时，直接去系统取「拖拽进来的文件列表」兜底
        try:
            if not self._dnd.pending:
                files = self._dnd.query_dropped_files()
                if files:
                    self._on_drop(files)
        except Exception:
            pass
        # 顶层窗口（TkTopLevel）收到 WM_CLOSE —— 点任务栏关闭 / Alt+F4
        try:
            if self._dnd.closing and not self._closing:
                self._show_hit(False)
                self._closing = True
                cb = getattr(self._dnd, "on_close", None)
                if cb is not None:
                    cb()
                else:
                    self._quit()
                return
        except Exception:
            pass
        try:
            if self.root.winfo_exists():
                self.root.after(100, self._poll_dnd)
        except Exception:
            pass

    def _on_drop(self, files):
        self._show_hit(False)
        paths = []
        for f in files:
            if isinstance(f, bytes):
                try:
                    f = f.decode("gbk")
                except Exception:
                    f = f.decode("utf-8", "ignore")
            paths.append(f)
        self.add_paths(paths)

    # ================================================== 启动
    def run(self):
        self.root.mainloop()
        # 主循环结束后（_quit 已 detach 拖拽挂钩）再销毁窗口，
        # 保证解释器能干净收尾、进程正常退出
        try:
            if self.root.winfo_exists():
                self.root.destroy()
        except Exception:
            pass


# ====================================================== 程序编辑对话框
class AppDialog(W.BaseDialog):

    def __init__(self, master, bank, icon_bank, store, app=None):
        self.app = app
        self.is_new = app is None
        self.store = store
        self.icon_bank = icon_bank
        self.bank = bank
        self.F = T.fonts()
        title = "添加程序" if self.is_new else "编辑程序"
        W.BaseDialog.__init__(self, master, title, emoji_img=bank.get("pencil", 28),
                              width=540, height=474,
                              subtitle="路径可以直接拖进来，也可以点「浏览」挑")
        self.var_name = tk.StringVar(value=(app or {}).get("name", ""))
        self.var_path = tk.StringVar(value=(app or {}).get("path", ""))
        self.var_args = tk.StringVar(value=(app or {}).get("args", ""))
        self.var_note = tk.StringVar(value=(app or {}).get("note", ""))
        self.var_group = tk.StringVar()
        self.emoji_name = (app or {}).get("emoji") or "rocket"
        self.icon_file = (app or {}).get("icon", "")
        self._build()

    def _row(self, parent, label, emoji):
        row = tk.Frame(parent, bg=T.BG_APP)
        row.pack(fill="x", pady=(0, 10))
        head = tk.Frame(row, bg=T.BG_APP)
        head.pack(fill="x", pady=(0, 4))
        img = self.bank.get(emoji, 18)
        if img is not None:
            tk.Label(head, image=img, bg=T.BG_APP).pack(side="left")
        tk.Label(head, text=label, bg=T.BG_APP, fg=T.TEXT_SUB,
                 font=self.F["small_b"]).pack(side="left", padx=(4, 0))
        return row

    def _build(self):
        body = tk.Frame(self.body, bg=T.BG_APP)
        body.pack(fill="both", expand=True, padx=26, pady=(16, 4))

        # 名称
        row = self._row(body, "程序名称", "memo")
        f1 = tk.Frame(row, bg=T.LINE_STRONG)
        f1.pack(fill="x")
        tk.Entry(f1, textvariable=self.var_name, font=self.F["body"], bg=T.BG_INPUT,
                 fg=T.TEXT, relief="flat", bd=0, insertbackground=T.ACCENT).pack(
            fill="x", padx=2, pady=3)

        # 路径
        row = self._row(body, "程序路径（exe / 快捷方式）", "folder")
        f2 = tk.Frame(row, bg=T.BG_APP)
        f2.pack(fill="x")
        pf = tk.Frame(f2, bg=T.LINE_STRONG)
        pf.pack(side="left", fill="x", expand=True)
        tk.Entry(pf, textvariable=self.var_path, font=self.F["small"], bg=T.BG_INPUT,
                 fg=T.TEXT, relief="flat", bd=0, insertbackground=T.ACCENT).pack(
            fill="x", padx=2, pady=3)
        W.RoundButton(f2, text="浏览", emoji_img=self.bank.get("search", 18),
                      variant="plain", width=82, height=30, bg=T.BG_APP,
                      command=self._browse).pack(side="left", padx=(8, 0))

        # 参数 + 分类
        two = tk.Frame(body, bg=T.BG_APP)
        two.pack(fill="x")
        left = tk.Frame(two, bg=T.BG_APP)
        left.pack(side="left", fill="x", expand=True)
        row = self._row(left, "启动参数（可留空）", "wrench")
        f3 = tk.Frame(row, bg=T.LINE_STRONG)
        f3.pack(fill="x")
        tk.Entry(f3, textvariable=self.var_args, font=self.F["small"], bg=T.BG_INPUT,
                 fg=T.TEXT, relief="flat", bd=0, insertbackground=T.ACCENT).pack(
            fill="x", padx=2, pady=3)

        right = tk.Frame(two, bg=T.BG_APP)
        right.pack(side="left", fill="x", padx=(14, 0))
        row = self._row(right, "所属分类", "tag")
        names = [g["name"] for g in self.store.groups]
        self.combo = ttk.Combobox(row, values=names, state="readonly", width=13,
                                  style="Cartoon.TCombobox", font=self.F["small"])
        self.combo.pack(anchor="w")
        cur = (self.app or {}).get("group")
        g = self.store.group_by_id(cur) if cur else None
        if g:
            self.combo.set(g["name"])
        elif names:
            self.combo.set(names[0])

        # 备注
        row = self._row(body, "备注（可留空）", "chat")
        f4 = tk.Frame(row, bg=T.LINE_STRONG)
        f4.pack(fill="x")
        tk.Entry(f4, textvariable=self.var_note, font=self.F["small"], bg=T.BG_INPUT,
                 fg=T.TEXT, relief="flat", bd=0, insertbackground=T.ACCENT).pack(
            fill="x", padx=2, pady=3)

        # 图标
        row = self._row(body, "图标（默认自动抓取程序自带图标）", "palette")
        pick = tk.Frame(row, bg=T.BG_APP)
        pick.pack(fill="x")
        self.prev = tk.Canvas(pick, width=68, height=68, bg=T.BG_APP,
                              highlightthickness=0, bd=0)
        self.prev.pack(side="left")
        btns = tk.Frame(pick, bg=T.BG_APP)
        btns.pack(side="left", padx=(12, 0))
        W.RoundButton(btns, text="重新抓取图标", emoji_img=self.bank.get("refresh", 18),
                      variant="plain", width=150, height=32, bg=T.BG_APP,
                      command=self._fetch_icon).pack(anchor="w", pady=(2, 6))
        W.RoundButton(btns, text="换个彩色 emoji", emoji_img=self.bank.get("palette", 18),
                      variant="plain", width=150, height=32, bg=T.BG_APP,
                      command=self._pick_emoji).pack(anchor="w")

        self.add_footer_buttons(ok_text="保存", cancel_text="取消",
                                ok_emoji=self.bank.get("check", 18),
                                cancel_emoji=self.bank.get("cross", 18),
                                on_ok=self._save)
        self._paint_preview()
        if self.is_new and not self.var_path.get():
            self.bind("<Return>", lambda e: None)

    def _paint_preview(self):
        c = self.prev
        c.delete("all")
        T.rrect(c, 2, 2, 66, 66, 15, fill=T.BG_TAG, outline=T.LINE, width=1)
        img = self.icon_bank.get(self.icon_file, 48)
        if img is not None:
            c.create_image(34, 34, image=img)
        else:
            e = self.bank.get(self.emoji_name, 56)
            if e is not None:
                c.create_image(34, 34, image=e)

    def _browse(self):
        p = filedialog.askopenfilename(
            title="选择程序",
            filetypes=[("程序 / 快捷方式", "*.exe;*.lnk;*.bat;*.cmd;*.com;*.msc;*.ps1;*.url;*.jar"),
                       ("所有文件", "*.*")])
        if not p:
            return
        self.var_path.set(os.path.normpath(p))
        if not self.var_name.get():
            self.var_name.set(os.path.splitext(os.path.basename(p))[0])
        self.emoji_name = guess_emoji(p)
        self.icon_file = ""
        self._fetch_icon(silent=True)

    def _fetch_icon(self, silent=False):
        p = self.var_path.get().strip()
        if not p or not os.path.exists(p):
            return
        got = iconutil.extract_icon(p)
        if not got:
            return
        self.icon_file = self.store.cache_icon(got)
        self.icon_bank.clear()
        self._paint_preview()

    def _pick_emoji(self):
        dlg = W.EmojiPickerDialog(self, self.bank, self.emoji_name)
        got = dlg.show()
        if got:
            self.emoji_name = got
            self.icon_file = ""
            self._paint_preview()

    def _save(self):
        name = self.var_name.get().strip()
        path = self.var_path.get().strip().strip('"')
        args = self.var_args.get().strip()
        workdir = ""
        src_lnk = ""
        if not path:
            self.toast_err("请先选择程序路径")
            return
        # 选的是快捷方式：存真实目标 + 参数 + 工作目录，删掉源快捷方式也不失效
        if path.lower().endswith(".lnk") and os.path.isfile(path):
            ind = linkfix.independent(path)
            if ind:
                if ind["args"]:
                    args = (ind["args"] + " " + args).strip()
                    self.var_args.set(args)
                path = ind["path"]
                workdir = ind["cwd"]
                src_lnk = ind["lnk"]
                self.var_path.set(path)
                if not self.icon_file:
                    got = iconutil.extract_icon(ind["icon_src"])
                    if got:
                        self.icon_file = self.store.cache_icon(got)
        if not name:
            name = os.path.splitext(os.path.basename(path))[0]
            self.var_name.set(name)
        gname = self.combo.get().strip()
        gid = None
        for g in self.store.groups:
            if g["name"] == gname:
                gid = g["id"]
                break
        if gid is None:
            gid = self.store.groups[0]["id"] if self.store.groups else "g_default"

        if self.is_new:
            it = self.store.add_app(path, name=name, group=gid,
                                    note=self.var_note.get().strip(),
                                    args=self.var_args.get().strip(),
                                    emoji=self.emoji_name,
                                    icon_file=self.icon_file,
                                    workdir=workdir, lnk=src_lnk)
            if not it.get("icon"):
                got = iconutil.extract_icon(path)
                if got:
                    it["icon"] = self.store.cache_icon(got)
        else:
            fields = dict(name=name, path=path, group=gid,
                          note=self.var_note.get().strip(),
                          args=self.var_args.get().strip(),
                          emoji=self.emoji_name, icon=self.icon_file)
            if self.icon_file and self.icon_file != self.app.get("icon"):
                fields["iconv"] = S.ICON_FORMAT
            if workdir or src_lnk:
                fields["workdir"] = workdir or os.path.dirname(path)
                fields["lnk"] = src_lnk
            self.store.update_app(self.app["id"], **fields)
        self.store.save()
        self._result = True
        self.destroy()

    def toast_err(self, msg):
        if not hasattr(self, "_errlbl"):
            self._errlbl = tk.Label(self.body, text="", bg=T.BG_APP, fg=T.DANGER,
                                    font=T.fonts()["small_b"])
            self._errlbl.pack(anchor="w", padx=26)
        self._errlbl.configure(text="⚠ " + msg)


# ====================================================== 分类对话框
class GroupPasswordDialog(W.BaseDialog):
    """进入加密分类前的密码框；输对后 24 小时内免输。"""

    def __init__(self, master, bank, store, gid):
        self.store = store
        self.gid = gid
        g = store.group_by_id(gid) or {}
        self.gname = g.get("name", "分类")
        self.has_hint = bool(store.group_hints(gid))
        W.BaseDialog.__init__(self, master, "输入密码",
                              emoji_img=bank.get("lock", 28),
                              width=430, height=280,
                              subtitle="「%s」已加锁" % self.gname)
        self.bank = bank
        self.F = T.fonts()
        body = tk.Frame(self.body, bg=T.BG_APP)
        body.pack(fill="both", expand=True, padx=26, pady=18)
        tk.Label(body, text="请输入打开密码", bg=T.BG_APP, fg=T.TEXT_SUB,
                 font=self.F["small_b"]).pack(anchor="w")
        row = tk.Frame(body, bg=T.BG_APP)
        row.pack(fill="x", pady=(4, 6))
        f = tk.Frame(row, bg=T.LINE_STRONG)
        f.pack(side="left", fill="x", expand=True)
        self.var = tk.StringVar()
        self.ent = tk.Entry(f, textvariable=self.var, show="●",
                            font=self.F["body"], bg=T.BG_INPUT, fg=T.TEXT,
                            relief="flat", bd=0, insertbackground=T.ACCENT)
        self.ent.pack(fill="x", padx=2, pady=3)
        self._show = False
        eye = tk.Label(row, image=bank.get("eyes", 18), bg=T.BG_APP,
                       cursor="hand2")
        eye.pack(side="left", padx=(8, 0))
        eye.bind("<Button-1>", lambda e: self._toggle())
        self.lbl_err = tk.Label(body, text="", bg=T.BG_APP, fg=T.DANGER_DK,
                                font=self.F["tiny"], anchor="w")
        self.lbl_err.pack(anchor="w", pady=(2, 4))
        if self.has_hint:
            link = tk.Label(body, text="忘记密码？点这里找回", bg=T.BG_APP,
                            fg=T.ACCENT_DK, font=self.F["tiny"], cursor="hand2")
            link.pack(anchor="w")
            link.bind("<Button-1>", lambda e: self._recover())
        else:
            tk.Label(body, text="这个分类没有设置找回问题", bg=T.BG_APP,
                     fg=T.TEXT_SUB, font=self.F["tiny"]).pack(anchor="w")
        self.add_footer_buttons(ok_text="解锁", cancel_text="取消",
                                ok_emoji=bank.get("key", 18),
                                cancel_emoji=bank.get("cross", 18),
                                on_ok=self._ok)
        self.ent.bind("<Return>", lambda e: self._ok())
        self.ent.focus_set()

    def _toggle(self):
        self._show = not self._show
        self.ent.configure(show="" if self._show else "●")

    def _ok(self):
        if self.store.unlock_group(self.gid, self.var.get()):
            self._result = True
            self.destroy()
        else:
            self.lbl_err.configure(text="密码不对，再试一次")
            self.var.set("")
            self.ent.focus_set()

    def _recover(self):
        dlg = GroupRecoverDialog(self, self.bank, self.store, self.gid)
        ok = dlg.show()
        try:
            self.grab_set()
        except Exception:
            pass
        if ok:
            self._result = True
            self.destroy()


class GroupRecoverDialog(W.BaseDialog):
    """答对找回问题后直接显示分类密码，并解锁该分类。"""

    def __init__(self, master, bank, store, gid):
        self.store = store
        self.gid = gid
        g = store.group_by_id(gid) or {}
        self.gname = g.get("name", "分类")
        self.hints = store.group_hints(gid)
        self.password = g.get("password", "")
        W.BaseDialog.__init__(self, master, "找回密码",
                              emoji_img=bank.get("key", 28),
                              width=450, height=300,
                              subtitle="「%s」" % self.gname)
        self.F = T.fonts()
        self._verified = False
        body = tk.Frame(self.body, bg=T.BG_APP)
        body.pack(fill="both", expand=True, padx=26, pady=18)
        if not self.hints:
            tk.Label(body, text="这个分类没有设置密码提示，\n只能取消后重新设置密码。",
                     bg=T.BG_APP, fg=T.TEXT_SUB, font=self.F["small"],
                     justify="left").pack(anchor="w")
            W.RoundButton(self.footer, text="关闭",
                          emoji_img=bank.get("cross", 18), variant="plain",
                          width=104, height=38, bg=T.BG_FOOT,
                          command=self.on_cancel).pack(side="right", padx=18,
                                                       pady=12)
            return
        tk.Label(body, text="密码提示（答对任意一条即可）", bg=T.BG_APP,
                 fg=T.TEXT_SUB, font=self.F["small_b"]).pack(anchor="w")
        tk.Label(body, text="\n".join("%d. %s" % (i + 1, h["q"])
                                      for i, h in enumerate(self.hints)),
                 bg=T.BG_APP, fg=T.TEXT, font=self.F["body"],
                 wraplength=390, justify="left",
                 anchor="w").pack(anchor="w", pady=(2, 12))
        tk.Label(body, text="你的答案", bg=T.BG_APP, fg=T.TEXT_SUB,
                 font=self.F["small_b"]).pack(anchor="w")
        f = tk.Frame(body, bg=T.LINE_STRONG)
        f.pack(fill="x", pady=(4, 6))
        self.var = tk.StringVar()
        self.ent = tk.Entry(f, textvariable=self.var, font=self.F["body"],
                            bg=T.BG_INPUT, fg=T.TEXT, relief="flat", bd=0,
                            insertbackground=T.ACCENT)
        self.ent.pack(fill="x", padx=2, pady=3)
        self.lbl_err = tk.Label(body, text="", bg=T.BG_APP, fg=T.DANGER_DK,
                                font=self.F["tiny"], anchor="w",
                                wraplength=390, justify="left")
        self.lbl_err.pack(anchor="w")
        self.lbl_pw = tk.Label(body, text="", bg=T.BG_APP, fg=T.ACCENT_DK,
                               font=self.F["body_b"], anchor="w",
                               wraplength=390, justify="left")
        self.lbl_pw.pack(anchor="w", pady=(4, 0))
        self.add_footer_buttons(ok_text="验证并显示密码", cancel_text="取消",
                                ok_emoji=bank.get("key", 18),
                                cancel_emoji=bank.get("cross", 18),
                                on_ok=self._ok)
        self.ent.bind("<Return>", lambda e: self._ok())
        self.ent.focus_set()

    def _ok(self):
        if self._verified:
            self._result = True
            self.destroy()
            return
        if self.store.check_group_answer(self.gid, self.var.get()):
            self._verified = True
            self.lbl_err.configure(text="")
            self.lbl_pw.configure(text="密码是：%s" % self.password)
            self.ent.configure(state="disabled")
            self.store.unlock_group(self.gid, self.password)
            try:
                self.ok_button.set_text("解锁并进入")
            except Exception:
                pass
        else:
            self.lbl_err.configure(text="答案不对，再试试")
            self.var.set("")
            self.ent.focus_set()


class GroupHintsDialog(W.BaseDialog):
    """设置密保：成组的问题 + 答案，答对任意一组即可找回密码。"""

    CN = "一二三四五六七八九十"

    def __init__(self, master, bank, hints=None):
        self.bank = bank
        self.F = T.fonts()
        self.hints = []
        self._vars = [(tk.StringVar(value=h.get("q", "")),
                       tk.StringVar(value=h.get("a", "")))
                      for h in (hints or [])]
        # 默认只给一组问题 + 答案，不够用再点「添加问题」
        if not self._vars:
            self._vars.append((tk.StringVar(), tk.StringVar()))
        W.BaseDialog.__init__(self, master, "设置密保",
                              emoji_img=bank.get("lock", 28),
                              width=470, height=300,
                              subtitle="答对任意一组即可找回密码")
        self._build()

    def _num(self, i):
        return self.CN[i] if i < len(self.CN) else str(i + 1)

    def _build(self):
        body = tk.Frame(self.body, bg=T.BG_APP)
        body.pack(fill="both", expand=True, padx=26, pady=(14, 8))
        tk.Label(body,
                 text="为了避免遗忘，请您填写真实信息，这将帮助您以后通过密保问题找回密码",
                 bg=T.BG_APP, fg=T.TEXT_SUB, font=self.F["small"],
                 wraplength=410, justify="left").pack(anchor="w")
        self.box = tk.Frame(body, bg=T.BG_APP)
        self.box.pack(fill="x", pady=(10, 0))
        self._render_rows()
        W.RoundButton(body, text="＋ 添加问题",
                      emoji_img=self.bank.get("plus", 16),
                      variant="plain", width=126, height=30, bg=T.BG_APP,
                      command=self._add).pack(anchor="w", pady=(2, 0))
        self.lbl_err = tk.Label(body, text="", bg=T.BG_APP, fg=T.DANGER_DK,
                                font=self.F["tiny"], anchor="w", justify="left",
                                wraplength=410)
        self.lbl_err.pack(anchor="w", pady=(4, 0))
        self.add_footer_buttons(ok_text="保存", cancel_text="取消",
                                ok_emoji=self.bank.get("check", 18),
                                cancel_emoji=self.bank.get("cross", 18),
                                on_ok=self._save)
        if self._entries:
            self._entries[0].focus_set()

    def _render_rows(self):
        for w in self.box.winfo_children():
            w.destroy()
        self._entries = []
        self._labels = []
        for i, (vq, va) in enumerate(self._vars):
            card = tk.Frame(self.box, bg=T.BG_APP)
            card.pack(fill="x", pady=(0, 8))
            row_q = tk.Frame(card, bg=T.BG_APP)
            row_q.pack(fill="x")
            lq = tk.Label(row_q, text="问题%s：" % self._num(i), bg=T.BG_APP,
                          fg=T.TEXT_SUB, font=self.F["small_b"], width=5,
                          anchor="e")
            lq.pack(side="left")
            self._labels.append(lq)
            fq = tk.Frame(row_q, bg=T.LINE_STRONG)
            fq.pack(side="left", fill="x", expand=True, padx=(4, 0))
            eq = tk.Entry(fq, textvariable=vq, font=self.F["small"],
                          bg=T.BG_INPUT, fg=T.TEXT, relief="flat", bd=0,
                          insertbackground=T.ACCENT)
            eq.pack(fill="x", padx=2, pady=2)
            if len(self._vars) > 1:
                x = tk.Label(row_q, image=self.bank.get("cross", 16),
                             bg=T.BG_APP, cursor="hand2")
                x.pack(side="left", padx=(6, 0))
                x.bind("<Button-1>", lambda e, idx=i: self._del(idx))
            row_a = tk.Frame(card, bg=T.BG_APP)
            row_a.pack(fill="x", pady=(4, 0))
            tk.Label(row_a, text="答案：", bg=T.BG_APP, fg=T.TEXT_SUB,
                     font=self.F["small_b"], width=5, anchor="e").pack(side="left")
            fa = tk.Frame(row_a, bg=T.LINE_STRONG)
            fa.pack(side="left", fill="x", expand=True, padx=(4, 0))
            ea = tk.Entry(fa, textvariable=va, font=self.F["small"],
                          bg=T.BG_INPUT, fg=T.TEXT, relief="flat", bd=0,
                          insertbackground=T.ACCENT)
            ea.pack(fill="x", padx=2, pady=2)
            self._entries.append(eq)

    def _add(self):
        self._vars.append((tk.StringVar(), tk.StringVar()))
        self._render_rows()
        self._fit_rows()
        try:
            self._entries[-1].focus_set()
        except Exception:
            pass

    def _del(self, idx):
        if len(self._vars) <= 1:
            return
        self._vars.pop(idx)
        self._render_rows()
        self._fit_rows()

    def _fit_rows(self):
        """增删问题后窗口高度跟着内容走，位置不动，免得按钮跑出屏幕。"""
        try:
            self.update_idletasks()
            h = self.winfo_reqheight()
            l, t, r, b = W.BaseDialog._work_area()
            if b > t:
                h = min(h, b - t - 40)
            h = max(h, self._dh)
            self.geometry("%dx%d%+d%+d" % (self._dw, h,
                                           self.winfo_x(), self.winfo_y()))
        except Exception:
            pass

    def _save(self):
        rows = [{"q": vq.get().strip(), "a": va.get().strip()}
                for vq, va in self._vars]
        filled = [h for h in rows if h["q"] or h["a"]]
        if not filled:
            self.lbl_err.configure(text="请至少填写一组密保问题")
            return
        for i, h in enumerate(rows):
            if (h["q"] or h["a"]) and not (h["q"] and h["a"]):
                self.lbl_err.configure(
                    text="第%s组的问题和答案都要填完整" % self._num(i))
                return
        self.hints = [h for h in rows if h["q"] and h["a"]]
        self._result = True
        self.destroy()


class GroupDialog(W.BaseDialog):

    def __init__(self, master, bank, store, group=None, focus_icon=False,
                 focus_pw=False):
        self.group = group
        self.store = store
        self.bank = bank
        self.is_new = group is None
        W.BaseDialog.__init__(self, master,
                              "新建分类" if self.is_new else "编辑分类",
                              emoji_img=bank.get("folder2", 28),
                              width=470, height=330,
                              subtitle="给分类起个名字，再挑一个彩色图标")
        self.var_name = tk.StringVar(value=(group or {}).get("name", ""))
        self.emoji_name = (group or {}).get("emoji", "folder2")
        self.color = (group or {}).get("color", T.GROUP_COLORS[0])
        self.var_pw = tk.StringVar(value=(group or {}).get("password", ""))
        # 密保问答按分类独立保存，可在「设置密保」里增删
        self.hints = [{"q": h.get("q", ""), "a": h.get("a", "")}
                      for h in (group or {}).get("pw_hints", [])]
        self._show_pw = False
        self._focus_pw = focus_pw
        self._build()

    def _build(self):
        self.F = T.fonts()
        body = tk.Frame(self.body, bg=T.BG_APP)
        body.pack(fill="both", expand=True, padx=26, pady=18)

        tk.Label(body, text="分类名称", bg=T.BG_APP, fg=T.TEXT_SUB,
                 font=self.F["small_b"]).pack(anchor="w")
        f = tk.Frame(body, bg=T.LINE_STRONG)
        f.pack(fill="x", pady=(4, 14))
        e = tk.Entry(f, textvariable=self.var_name, font=self.F["body"], bg=T.BG_INPUT,
                     fg=T.TEXT, relief="flat", bd=0, insertbackground=T.ACCENT)
        e.pack(fill="x", padx=2, pady=3)
        self.ent_name = e

        tk.Label(body, text="分类图标", bg=T.BG_APP, fg=T.TEXT_SUB,
                 font=self.F["small_b"]).pack(anchor="w")
        row = tk.Frame(body, bg=T.BG_APP)
        row.pack(fill="x", pady=(6, 14))
        self.prev = tk.Canvas(row, width=58, height=58, bg=T.BG_APP,
                              highlightthickness=0, bd=0)
        self.prev.pack(side="left")
        W.RoundButton(row, text="选个 emoji", emoji_img=self.bank.get("palette", 18),
                      variant="plain", width=136, height=32, bg=T.BG_APP,
                      command=self._pick).pack(side="left", padx=(12, 0))

        tk.Label(body, text="分类颜色", bg=T.BG_APP, fg=T.TEXT_SUB,
                 font=self.F["small_b"]).pack(anchor="w")
        cols = tk.Frame(body, bg=T.BG_APP)
        cols.pack(anchor="w", pady=(6, 0))
        self._swatches = {}
        for c in T.GROUP_COLORS:
            cv = tk.Canvas(cols, width=30, height=30, bg=T.BG_APP,
                           highlightthickness=0, bd=0)
            cv.pack(side="left", padx=3)
            cv._color = c
            cv.bind("<Button-1>", lambda ev, cc=cv: self._set_color(cc._color))
            self._swatches[c] = cv
        self._paint()

        # ---- 打开密码（可选，不限长度和字符）
        tk.Label(body, text="打开密码（可选）", bg=T.BG_APP, fg=T.TEXT_SUB,
                 font=self.F["small_b"]).pack(anchor="w", pady=(16, 0))
        pw_row = tk.Frame(body, bg=T.BG_APP)
        pw_row.pack(fill="x", pady=(4, 8))
        pf = tk.Frame(pw_row, bg=T.LINE_STRONG)
        pf.pack(side="left", fill="x", expand=True)
        self.ent_pw = tk.Entry(pf, textvariable=self.var_pw, show="●",
                               font=self.F["body"], bg=T.BG_INPUT, fg=T.TEXT,
                               relief="flat", bd=0, insertbackground=T.ACCENT)
        self.ent_pw.pack(fill="x", padx=2, pady=3)
        eye = tk.Label(pw_row, image=self.bank.get("eyes", 18), bg=T.BG_APP,
                       cursor="hand2")
        eye.pack(side="left", padx=(8, 0))
        eye.bind("<Button-1>", lambda e: self._toggle_pw())

        tk.Label(body, text="密保问题（忘记密码时回答任意一组即可找回）",
                 bg=T.BG_APP, fg=T.TEXT_SUB, font=self.F["small_b"]
                 ).pack(anchor="w", pady=(8, 0))
        hint_row = tk.Frame(body, bg=T.BG_APP)
        hint_row.pack(fill="x", pady=(6, 6))
        self.lbl_hints = tk.Label(hint_row, text="", bg=T.BG_APP,
                                  fg=T.TEXT_SUB, font=self.F["small"],
                                  anchor="w")
        self.lbl_hints.pack(side="left")
        self.btn_hints = W.RoundButton(
            hint_row, text="设置密保问题…",
            emoji_img=self.bank.get("lock", 16), variant="plain",
            width=150, height=32, bg=T.BG_APP, command=self._edit_hints)
        self.btn_hints.pack(side="right")
        self._paint_hints()

        self.lbl_err = tk.Label(body, text="", bg=T.BG_APP, fg=T.DANGER_DK,
                                font=self.F["tiny"], anchor="w", justify="left",
                                wraplength=400)
        self.lbl_err.pack(anchor="w")
        tk.Label(body, text="密码留空 = 不加密；设置了密码需要至少一组密保问题。"
                            "输对密码后 24 小时内免输。",
                 bg=T.BG_APP, fg=T.TEXT_SUB, font=self.F["tiny"],
                 anchor="w", justify="left", wraplength=400).pack(anchor="w")

        self.add_footer_buttons(ok_text="保存", cancel_text="取消",
                                ok_emoji=self.bank.get("check", 18),
                                cancel_emoji=self.bank.get("cross", 18),
                                on_ok=self._save)
        (self.ent_pw if self._focus_pw else self.ent_name).focus_set()

    def _paint(self):
        c = self.prev
        c.delete("all")
        T.rrect(c, 2, 2, 56, 56, 14, fill=T.lighten(self.color, 0.86),
                outline=self.color, width=2)
        img = self.bank.get(self.emoji_name, 28)
        if img is not None:
            c.create_image(29, 29, image=img)
        for col, cv in self._swatches.items():
            cv.delete("all")
            T.rrect(cv, 2, 2, 28, 28, 9, fill=col, outline="")
            if col == self.color:
                cv.create_oval(9, 9, 21, 21, fill="#FFFFFF", outline="")
                cv.create_oval(13, 13, 17, 17, fill=col, outline="")

    def _set_color(self, col):
        self.color = col
        self._paint()

    def _toggle_pw(self):
        self._show_pw = not self._show_pw
        self.ent_pw.configure(show="" if self._show_pw else "●")

    def _edit_hints(self):
        dlg = GroupHintsDialog(self, self.bank, self.hints)
        ok = dlg.show()
        try:
            self.grab_set()
        except Exception:
            pass
        if ok:
            self.hints = dlg.hints
            self.lbl_err.configure(text="")
            self._paint_hints()

    def _paint_hints(self):
        n = len(self.hints)
        if n:
            self.lbl_hints.configure(text="已设置 %d 组密保问题" % n,
                                     fg=T.ACCENT_DK)
        else:
            self.lbl_hints.configure(text="还未设置", fg=T.TEXT_MUTED)
        try:
            self.btn_hints.set_text("修改密保问题…" if n else "设置密保问题…")
        except Exception:
            pass

    def _pick(self):
        dlg = W.EmojiPickerDialog(self, self.bank, self.emoji_name)
        got = dlg.show()
        if got:
            self.emoji_name = got
            self._paint()

    def _save(self):
        name = self.var_name.get().strip()
        if not name:
            name = "新分类"
        pw = self.var_pw.get()
        hints = [dict(h) for h in self.hints if h.get("q") and h.get("a")]
        if pw and not hints:
            # 有密码就至少要有「一组」密保问答；直接弹出密保窗口，
            # 让用户当场填好，而不是只丢一句错误提示。
            self._edit_hints()
            hints = [dict(h) for h in self.hints if h.get("q") and h.get("a")]
            if not hints:
                self.lbl_err.configure(
                    text="设置了密码，就必须至少填写一组密保问题和答案")
                return
        if self.is_new:
            self.store.add_group(name, self.emoji_name, self.color, pw, hints)
        else:
            self.store.update_group(self.group["id"], name=name,
                                    emoji=self.emoji_name, color=self.color)
            self.store.set_group_password(self.group["id"], pw, hints)
        self._result = True
        self.destroy()


def main():
    # 单实例守卫：必须在建窗口之前抢锁。
    # 抢不到 = 已经有一个收纳盒在跑 → 广播让它显身，本进程直接退出。
    guard = singleinst.claim_or_exit()
    try:
        app = Launcher()
    except Exception:
        guard.release()
        raise
    app._single = guard
    # 让已有实例能收到「再来一个」的广播（点多次 exe 时前置已有窗口）
    try:
        guard.bind(app.root)
    except Exception:
        pass
    app.run()


if __name__ == "__main__":
    main()
