# -*- coding: utf-8 -*-
"""
卡通风格控件库
==============
· RoundButton / IconButton  圆角胶囊按钮、图标圆钮
· ScrollArea                带自绘细滚动条的滚动容器
· AppCard                   程序卡片（悬停抬起、右键菜单、双击启动）
· GroupRow                  侧栏分类行
· BaseDialog / 各种对话框   统一卡通外观
"""
import tkinter as tk

import theme as T


# ============================================================ 基础按钮
class RoundButton(tk.Canvas):
    """
    variant: primary(实心橙) / soft(白底橙字) / ghost(透明) / danger(红)
    """

    def __init__(self, master, text="", emoji_img=None, command=None,
                 variant="primary", width=120, height=36, font=None,
                 bg=None, radius=None):
        self.bg = bg or T.BG_APP
        tk.Canvas.__init__(self, master, width=width, height=height,
                           bg=self.bg, highlightthickness=0, bd=0)
        self.text = text
        self.emoji_img = emoji_img
        self.command = command
        self.variant = variant
        self.w, self.h = width, height
        self.radius = radius if radius is not None else height / 2.0
        self.font = font or T.fonts()["body_b"]
        self._enabled = True
        self._state = "normal"
        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    # ---- 配色
    def _palette(self):
        v = self.variant
        if v == "primary":
            base = T.ACCENT
            hover = T.ACCENT_DK
            fill = base if self._state == "normal" else hover
            return fill, T.TEXT_ON_ACCENT, ""
        if v == "danger":
            base = T.DANGER
            fill = base if self._state == "normal" else T.DANGER_DK
            return fill, "#FFFFFF", ""
        if v == "soft":
            fill = "#FFFFFF" if self._state == "normal" else T.ACCENT_LT
            return fill, T.ACCENT_DK, T.ACCENT_SOFT
        if v == "ghost":
            fill = self.bg if self._state == "normal" else T.BG_HOVER
            return fill, T.TEXT, ""
        if v == "success":
            fill = T.OK if self._state == "normal" else T.darken(T.OK, 0.12)
            return fill, "#FFFFFF", ""
        fill = "#FFFFFF" if self._state == "normal" else T.BG_HOVER
        return fill, T.TEXT, T.LINE_STRONG

    def _draw(self):
        self.delete("all")
        fill, fg, outline = self._palette()
        if self.variant != "ghost":
            # 卡通投影
            T.rrect(self, 2, 3, self.w - 1, self.h - 1, self.radius,
                    fill=T.SHADOW if self._state == "normal" else T.SHADOW_HOVER,
                    outline="")
        T.rrect(self, 1, 1, self.w - 3, self.h - 3, self.radius,
                fill=fill, outline=outline or fill, width=1)
        if self.variant in ("soft", "plain"):
            T.rrect(self, 1, 1, self.w - 3, self.h - 3, self.radius,
                    fill="", outline=T.LINE_STRONG, width=1)
        cx = self.w / 2.0 - 1
        cy = self.h / 2.0 - 1
        self._text_id = None
        if self.emoji_img is not None:
            iw = self.emoji_img.width()
            if self.text:
                total = iw + 6 + len(self.text) * 13
                x0 = cx - total / 2.0
                self.create_image(x0 + iw / 2.0, cy, image=self.emoji_img)
                self._text_id = self.create_text(x0 + iw + 6, cy, text=self.text,
                                                 anchor="w", font=self.font, fill=fg)
            else:
                self.create_image(cx, cy, image=self.emoji_img)
        elif self.text:
            self._text_id = self.create_text(cx, cy, text=self.text,
                                             font=self.font, fill=fg)
        if not self._enabled:
            T.rrect(self, 1, 1, self.w - 3, self.h - 3, self.radius,
                    fill="#FFFFFF", outline="", stipple="gray50")

    def set_text(self, text):
        if text == self.text:
            return
        self.text = text
        # 只改文字 item，不 delete 重建整颗按钮（切分类时会频繁调用）
        tid = getattr(self, "_text_id", None)
        if tid is None or not self.find_withtag(tid):
            self._draw()
            return
        cx = self.w / 2.0 - 1
        cy = self.h / 2.0 - 1
        if self.emoji_img is not None:
            iw = self.emoji_img.width()
            total = iw + 6 + len(self.text) * 13
            x0 = cx - total / 2.0
            self.coords(tid, x0 + iw + 6, cy)
        self.itemconfigure(tid, text=text)

    def set_emoji(self, img):
        self.emoji_img = img
        self._draw()

    def set_enabled(self, flag):
        self._enabled = bool(flag)
        self._draw()

    def _on_enter(self, _=None):
        if not self._enabled:
            return
        self._state = "hover"
        self.configure(cursor="hand2")
        self._draw()

    def _on_leave(self, _=None):
        self._state = "normal"
        self.configure(cursor="")
        self._draw()

    def _on_press(self, _=None):
        if not self._enabled:
            return
        self._state = "press"
        self._draw()

    def _on_release(self, _=None):
        if not self._enabled:
            return
        self._state = "hover"
        self._draw()
        inside = (0 <= self.winfo_pointerx() - self.winfo_rootx() <= self.w)
        if inside and self.command:
            self.command()


class IconButton(tk.Canvas):
    """纯图标圆钮（emoji 图片），用于顶栏 / 工具条。"""

    def __init__(self, master, emoji_img, command=None, size=34, bg=None,
                 tip="", round_bg=True):
        self.bg = bg or T.BG_APP
        tk.Canvas.__init__(self, master, width=size, height=size, bg=self.bg,
                           highlightthickness=0, bd=0)
        self.emoji_img = emoji_img
        self.command = command
        self.size = size
        self.tip = tip
        self.round_bg = round_bg
        self._hover = False
        self._draw()
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", self._click)

    def _draw(self):
        self.delete("all")
        s = self.size
        if self.round_bg and self._hover:
            T.rrect(self, 1, 1, s - 1, s - 1, 10, fill=T.BG_HOVER, outline="")
        if self.emoji_img is not None:
            self.create_image(s / 2.0, s / 2.0, image=self.emoji_img)

    def _enter(self, _=None):
        self._hover = True
        self.configure(cursor="hand2")
        self._draw()

    def _leave(self, _=None):
        self._hover = False
        self.configure(cursor="")
        self._draw()

    def _click(self, _=None):
        if self.command:
            self.command()


# ============================================================ 滚动容器
class ScrollArea(tk.Frame):
    """竖向滚动容器：Canvas + 内嵌 Frame + 自绘细滚动条。"""

    def __init__(self, master, bg=None, padding=(18, 14, 18, 14)):
        self.bg = bg or T.BG_APP
        tk.Frame.__init__(self, master, bg=self.bg)
        self.canvas = tk.Canvas(self, bg=self.bg, highlightthickness=0, bd=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=self.bg)
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.padding = padding
        self._sb = None
        self._drag_from = None
        self._sb_h = 60

        self.canvas.bind("<Configure>", self._on_canvas_conf)
        self.inner.bind("<Configure>", self._on_inner_conf)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.inner.bind("<MouseWheel>", self._on_wheel)

    def attach(self, widget):
        """把滚轮事件挂到子控件上（卡片等），否则鼠标停在卡片上滚不动。"""
        widget.bind("<MouseWheel>", self._on_wheel)
        return widget

    def _on_canvas_conf(self, _=None):
        self._resize_inner()
        self._draw_scrollbar()

    def _on_inner_conf(self, _=None):
        self._resize_inner()
        self._draw_scrollbar()

    def _resize_inner(self):
        cw = self.canvas.winfo_width()
        iw = self.inner.winfo_reqwidth()
        l, t, r, b = self.padding
        self.canvas.itemconfigure(self._win, width=max(cw, iw + l + r))
        self.canvas.coords(self._win, l, t)

    def _on_wheel(self, event):
        if self.canvas.yview() == (0.0, 1.0):
            return
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self._draw_scrollbar()

    def _draw_scrollbar(self):
        self.canvas.delete("sb")
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        total = self.inner.winfo_reqheight() + self.padding[1] + self.padding[3]
        if total <= ch or ch <= 1:
            return
        top, bottom = self.canvas.yview()
        bar_h = max(36, int(ch * (bottom - top)))
        y0 = int(top * ch)
        x1 = cw - 7
        x0 = x1 - 5
        if self._sb is None:
            self._sb = T.rrect(self.canvas, x0, y0, x1, y0 + bar_h, 3,
                               fill=T.LINE_STRONG, outline="", tags="sb")
            self.canvas.tag_bind("sb", "<Button-1>", self._sb_press)
            self.canvas.tag_bind("sb", "<B1-Motion>", self._sb_motion)
        else:
            self.canvas.coords(self._sb, *T.rounded_rect_points(x0, y0, x1, y0 + bar_h, 3))
        self.canvas.tag_raise("sb")

    def _sb_press(self, event):
        self._drag_from = (event.y, self.canvas.yview()[0])

    def _sb_motion(self, event):
        if not self._drag_from:
            return
        y0, v0 = self._drag_from
        ch = max(1, self.canvas.winfo_height())
        self.canvas.yview_moveto(max(0.0, min(1.0, v0 + (event.y - y0) / float(ch))))
        self._draw_scrollbar()

    def scroll_top(self):
        self.canvas.yview_moveto(0)
        self._draw_scrollbar()

    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self.scroll_top()


# ============================================================ 程序卡片
class AppCard(tk.Canvas):
    W, H = 122, 130          # 放大版：图标区从 48px 升到 56px，可放 48px 程序图标（带留白）

    def __init__(self, master, app, color, icon_img, emoji_img, on_open,
                 on_menu, on_select, on_hover, bg=None, group_name=""):
        self.bg = bg or T.BG_APP
        tk.Canvas.__init__(self, master, width=self.W, height=self.H, bg=self.bg,
                           highlightthickness=0, bd=0)
        self.app = app
        self.color = color
        self.icon_img = icon_img
        self.emoji_img = emoji_img
        self.group_name = group_name
        self.on_open = on_open
        self.on_menu = on_menu
        self.on_select = on_select
        self.on_hover = on_hover
        self.selected = False
        self._hover = False
        self._ids = None          # 复用画布 item 的 id 集合（避免反复 delete/recreate）
        self._draw()
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", self._click)
        self.bind("<Button-3>", self._menu)
        self.bind("<Motion>", lambda e: self.configure(cursor="hand2"))

    # ---- 绘制
    # 结构只在首帧画一次；hover / 选中只更新既有 item 的颜色和线宽，
    # 不再 delete("all") 重建整张卡（那是 hover 卡顿的根因）。
    def _draw(self):
        if self._ids is None:
            self._draw_full()
        self._restyle()

    def _draw_full(self):
        self.delete("all")
        w, h = self.W, self.H
        ids = {}
        ids["shadow"] = T.rrect(self, 5, 7, w - 2, h - 2, 13,
                                fill=T.SHADOW, outline="")
        ids["border"] = T.rrect(self, 3, 3, w - 8, h - 10, 13,
                                fill="#FFFFFF", outline=self.color, width=2)
        ids["tint"] = T.rrect(self, 4, 4, w - 9, 60, 12,
                              fill=T.lighten(self.color, 0.90), outline="")

        cy = 32
        if self.icon_img is not None:
            ids["icon"] = self.create_image(w / 2.0 - 1, cy, image=self.icon_img)
        elif self.emoji_img is not None:
            ids["icon"] = self.create_image(w / 2.0 - 1, cy, image=self.emoji_img)
        else:
            ids["icon"] = T.rrect(self, w / 2.0 - 13, cy - 13, w / 2.0 + 10,
                                  cy + 10, 7, fill=T.lighten(self.color, 0.7),
                                  outline="")

        title = T.ellipsis(self.app.get("name", ""), T.fonts()["card_title"], w - 22)
        ids["title"] = self.create_text(
            w / 2.0 - 1, 72, text=title, font=T.fonts()["card_title"],
            fill=T.TEXT)
        sub = self.app.get("note") or self.app.get("path", "")
        sub = sub.split("\\")[-1] if sub else ""
        ids["sub"] = self.create_text(
            w / 2.0 - 1, 88,
            text=T.ellipsis(sub, T.fonts()["card_sub"], w - 22),
            font=T.fonts()["card_sub"], fill=T.TEXT_MUTED)

        # 底部分类胶囊
        gname = self.group_name or "未分类"
        pill_w = min(w - 14, 16 + len(gname) * 11)
        x1 = w / 2.0 - 1 - pill_w / 2.0
        ids["pill"] = T.rrect(self, x1, 96, x1 + pill_w, 112, 8,
                              fill=T.lighten(self.color, 0.82), outline="")
        ids["pill_t"] = self.create_text(
            w / 2.0 - 1, 104,
            text=T.ellipsis(gname, T.fonts()["tiny"], pill_w - 12),
            font=T.fonts()["tiny"], fill=T.darken(self.color, 0.42))

        # 使用次数
        n = self.app.get("count", 0)
        if n:
            ids["count"] = self.create_text(
                w - 12, 104, text="%d" % n, anchor="e",
                font=T.fonts()["tiny"], fill=T.TEXT_MUTED)

        if self.app.get("pinned"):
            ids["pin_bg"] = self.create_oval(w - 30, 6, w - 8, 28,
                                             fill="#FFFFFF", outline="")
            ids["pin"] = self.create_text(w - 19, 17, text="★",
                                          font=(T.UI_FONT, 10, "bold"),
                                          fill=T.ACCENT)

        # 选中角标：常驻但默认隐藏（用 state 切换，省得反复建/删）
        ids["sel_bg"] = self.create_oval(5, 5, 24, 24, fill=T.ACCENT, outline="",
                                         state="hidden")
        ids["sel_ck"] = self.create_text(14.5, 14.5, text="✓",
                                         font=(T.UI_FONT, 8, "bold"),
                                         fill="#FFFFFF", state="hidden")
        self._ids = ids

    def _update_content(self):
        """复用已有 item，仅更新文字 / 图标 / 配色（不 delete、不重建）。

        切分类 / 刷新时绝大多数卡片的画布结构可以原样保留，
        只改内容最快。
        """
        ids = self._ids
        w = self.W
        # 配色
        self.itemconfigure(ids["tint"], fill=T.lighten(self.color, 0.90))
        self.itemconfigure(ids["pill"], fill=T.lighten(self.color, 0.82))
        self.itemconfigure(ids["pill_t"], fill=T.darken(self.color, 0.42))
        # 图标（换了图标就换 image；emoji 图标是矩形占位时忽略）
        if "icon" in ids:
            newimg = self.icon_img if self.icon_img is not None else self.emoji_img
            if newimg is not None:
                try:
                    self.itemconfigure(ids["icon"], image=newimg)
                except Exception:
                    pass
        # 文字
        title = T.ellipsis(self.app.get("name", ""), T.fonts()["card_title"], w - 22)
        self.itemconfigure(ids["title"], text=title)
        sub = self.app.get("note") or self.app.get("path", "")
        sub = sub.split("\\")[-1] if sub else ""
        self.itemconfigure(ids["sub"],
                           text=T.ellipsis(sub, T.fonts()["card_sub"], w - 22))
        gname = self.group_name or "未分类"
        self.itemconfigure(ids["pill_t"],
                           text=T.ellipsis(gname, T.fonts()["tiny"],
                                           min(w - 14, 16 + len(gname) * 11) - 12))
        n = self.app.get("count", 0)
        if "count" in ids:
            self.itemconfigure(ids["count"], text="%d" % n, state="normal" if n else "hidden")
        elif n:
            ids["count"] = self.create_text(
                w - 12, 104, text="%d" % n, anchor="e",
                font=T.fonts()["tiny"], fill=T.TEXT_MUTED)
        # 置顶星标
        pinned = bool(self.app.get("pinned"))
        if "pin" in ids:
            st = "normal" if pinned else "hidden"
            self.itemconfigure(ids["pin"], state=st)
            self.itemconfigure(ids["pin_bg"], state=st)
        elif pinned:
            ids["pin_bg"] = self.create_oval(w - 30, 6, w - 8, 28,
                                             fill="#FFFFFF", outline="")
            ids["pin"] = self.create_text(w - 19, 17, text="★",
                                          font=(T.UI_FONT, 10, "bold"),
                                          fill=T.ACCENT)

    def _restyle(self):
        """只改颜色/线宽/图标位置，不重建 item。"""
        ids = self._ids
        hot = self._hover or self.selected
        self.itemconfigure(ids["shadow"], fill=T.SHADOW_HOVER if hot else T.SHADOW)
        border = T.ACCENT if self.selected else (
            T.darken(self.color, 0.10) if self._hover else self.color)
        self.itemconfigure(ids["border"], outline=border, width=3 if hot else 2)
        # 悬停时图标上浮 1px（原来靠 destroy+重建实现，这里只挪坐标）
        if "icon" in ids:
            self.coords(ids["icon"], self.W / 2.0 - 1, 32 - (1 if self._hover else 0))
        state = "normal" if self.selected else "hidden"
        self.itemconfigure(ids["sel_bg"], state=state)
        self.itemconfigure(ids["sel_ck"], state=state)

    def rebind(self, app, color, icon_img, emoji_img, group_name=""):
        """把这张卡换成另一个程序（复用控件与画布 item，不重建）。

        刷新 / 切分类时如果控件还在，只更新内容即可 —— 这是把
        切换卡顿降下来的关键。
        """
        same = (self.app is app and self.color == color
                and self.icon_img is icon_img and self.emoji_img is emoji_img
                and self.group_name == group_name)
        if same:
            return
        self.app = app
        self.icon_img = icon_img
        self.emoji_img = emoji_img
        self.group_name = group_name
        self.selected = False
        self._hover = False
        if self._ids is None:
            self.color = color
            self._draw_full()
        else:
            # 结构可复用：只改内容与配色，避免 delete("all") + 重建
            self.color = color
            self._update_content()
        self._restyle()

    # ---- 事件
    def _enter(self, _=None):
        self._hover = True
        self._draw()
        if self.on_hover:
            self.on_hover(self.app, True)

    def _leave(self, _=None):
        self._hover = False
        self._draw()
        if self.on_hover:
            self.on_hover(self.app, False)

    def _click(self, _=None):
        # 单击即启动：先选中（右键菜单 / 键盘操作依赖选中态），再打开
        if self.on_select:
            self.on_select(self.app)
        if self.on_open:
            self.on_open(self.app)

    def _menu(self, event):
        if self.on_select:
            self.on_select(self.app)
        if self.on_menu:
            self.on_menu(self.app, event.x_root, event.y_root)

    def set_selected(self, flag):
        if self.selected != flag:
            self.selected = flag
            self._draw()


# ============================================================ 侧栏分类行
class GroupRow(tk.Canvas):
    H = 42
    DRAG_THRESHOLD = 5  # 移动超过 5px 才算拖拽，避免误吞单击

    def __init__(self, master, gid, name, emoji_img, count, selected, on_click,
                 on_menu, bg=None, width=196, draggable=False, on_drop=None):
        self.bg = bg or T.BG_SIDE
        tk.Canvas.__init__(self, master, width=width, height=self.H, bg=self.bg,
                           highlightthickness=0, bd=0)
        self.gid = gid
        self.name = name
        self.emoji_img = emoji_img
        self.count = count
        self.selected = selected
        self.on_click = on_click
        self.on_menu = on_menu
        self.w = width
        self._hover = False
        self._dragging = False
        self._drag_sx = self._drag_sy = 0
        self.draggable = draggable
        self.on_drop = on_drop    # on_drop(phase, gid, x_root, y_root)
                                   #   phase: "start" / "move" / "end" / "cancel"
        self._draw()
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-3>", self._menu)
        if draggable:
            # 拖拽模式下把单击合成到 Release 里（避免点一下就误触）
            self.bind("<ButtonPress-1>", self._on_press)
            self.bind("<B1-Motion>", self._on_motion)
            self.bind("<ButtonRelease-1>", self._on_release)
        else:
            self.bind("<Button-1>", self._click)

    def _draw(self):
        self.delete("all")
        w, h = self.w, self.H
        if self._dragging:
            # 拖拽中：去掉圆角和强调条，用更柔的底色 + 描边表示「抬起」
            T.rrect(self, 4, 3, w - 4, h - 3, 12, fill=T.BG_HOVER, outline=T.ACCENT, width=2)
        elif self.selected:
            T.rrect(self, 4, 3, w - 4, h - 3, 12, fill=T.BG_SEL, outline="")
            T.rrect(self, 6, 11, 10, h - 11, 2, fill=T.ACCENT, outline="")
        elif self._hover:
            T.rrect(self, 4, 3, w - 4, h - 3, 12, fill=T.BG_HOVER, outline="")
        if self.emoji_img is not None:
            self.create_image(26, h / 2.0, image=self.emoji_img)
        self.create_text(46, h / 2.0, text=T.ellipsis(self.name, T.fonts()["body_b"], 92),
                         anchor="w", font=T.fonts()["body_b"],
                         fill=T.ACCENT_DK if self.selected else T.TEXT)
        if self.count:
            cx = w - 30
            T.rrect(self, cx - 13, h / 2.0 - 9, cx + 13, h / 2.0 + 9, 9,
                    fill="#FFFFFF" if self.selected else T.BG_TAG, outline="")
            self.create_text(cx, h / 2.0, text=str(self.count),
                             font=T.fonts()["tiny_b"],
                             fill=T.ACCENT_DK if self.selected else T.TEXT_SUB)

    def _enter(self, _=None):
        if self._dragging:
            return
        self._hover = True
        self.configure(cursor="fleur" if self.draggable else "hand2")
        self._draw()

    def set_selected(self, flag):
        """只更新选中态（用于切换分类，避免整栏重建）。"""
        if self.selected != flag:
            self.selected = flag
            self._draw()

    def _leave(self, _=None):
        if self._dragging:
            return
        self._hover = False
        self._draw()

    def _click(self, _=None):
        if self.on_click:
            self.on_click(self.gid)

    def _menu(self, event):
        if self.on_menu:
            self.on_menu(self.gid, self.name, event.x_root, event.y_root)

    # ----------------------------------------------------- 拖拽
    def _on_press(self, event):
        if not self.draggable:
            return
        self._drag_sx, self._drag_sy = event.x_root, event.y_root
        self._dragging = False

    def _on_motion(self, event):
        if not self.draggable or self.on_drop is None:
            return
        if not self._dragging:
            # 还没超过阈值 —— 算一下位移
            if abs(event.x_root - self._drag_sx) < self.DRAG_THRESHOLD and \
               abs(event.y_root - self._drag_sy) < self.DRAG_THRESHOLD:
                return
            self._dragging = True
            self._hover = False
            self.configure(cursor="fleur")
            self._draw()
            # 注意：Canvas.lift() 被重载成画布内 item 的 raise（tag_raise），
            # 会报 wrong # args。控件整体置顶要用 Tcl 的 raise 命令。
            self.tk.call("raise", self._w)
            self.on_drop("start", self.gid, event.x_root, event.y_root)
        self.on_drop("move", self.gid, event.x_root, event.y_root)

    def _on_release(self, event):
        if not self.draggable:
            return
        was_dragging = self._dragging
        self._dragging = False
        if was_dragging:
            if self.on_drop:
                self.on_drop("end", self.gid, event.x_root, event.y_root)
            # _reorder_group 里 _render_groups() 会销毁本控件（重新建行），
            # 之后再碰 self 会 invalid command name。先确认还活着。
            if self.winfo_exists():
                self._hover = self._inside(event.x_root, event.y_root)
                self.configure(
                    cursor="fleur" if (self.draggable and self._hover) else "hand2")
                self._draw()
        else:
            # 没动 —— 就是普通点击
            if self.on_click:
                self.on_click(self.gid)
            # on_click 可能是 _select_group，里面会 _render_groups() 把本控件销毁
            # （点击用户分类切换时正是这条路径：group_box 整个重建，本 grouprow 没了），
            # 之后再碰 self 会 invalid command name "...!grouprowNN"。
            if self.winfo_exists():
                self._draw()

    def _inside(self, x_root, y_root):
        try:
            x = self.winfo_rootx()
            y = self.winfo_rooty()
            w, h = self.winfo_width(), self.winfo_height()
            return x <= x_root <= x + w and y <= y_root <= y + h
        except Exception:
            return False


# ============================================================ 对话框基类
class BaseDialog(tk.Toplevel):
    """统一卡通外观的模态对话框。"""

    def __init__(self, master, title, emoji_img=None, width=460, height=320,
                 subtitle=""):
        # 容错：master 可能是宿主对象（如主界面的 Launcher，普通类不是 Tk 控件），
        # 取它里面的 .root；都不行再退回 None。否则 Toplevel 会
        # AttributeError: object has no attribute 'tk'。
        if not isinstance(master, tk.Misc):
            master = getattr(master, "root", None)
        tk.Toplevel.__init__(self, master)
        self.withdraw()
        self.title(title)
        self.configure(bg=T.BG_APP)
        self.resizable(False, False)
        if master is not None:
            try:
                self.transient(master)
            except Exception:
                pass
        self._result = None
        # 注意：千万不要用 self._w / self._h —— `_w` 是 Tk 的窗口路径
        # （".!groupdialog"），被 int 覆盖后所有子控件创建都会
        # TypeError: unsupported operand type(s) for +: 'int' and 'str'
        self._dw, self._dh = width, height

        head = tk.Canvas(self, width=width, height=62, bg=T.BG_HEAD_B,
                         highlightthickness=0, bd=0)
        head.pack(fill="x")
        T.hgrad(head, 0, 0, width, 62, T.BG_HEAD_A, T.BG_HEAD_B, steps=48)
        head.create_oval(width - 70, -30, width + 10, 40, fill=T.BG_HEAD_A, outline="")
        head.create_oval(-30, 26, 46, 100, fill=T.BG_HEAD_A, outline="")
        if emoji_img is not None:
            head.create_image(34, 31, image=emoji_img)
            head.create_text(62, 24, text=title, anchor="w",
                             font=T.fonts()["dialog_title"], fill="#FFFFFF")
        else:
            head.create_text(20, 24, text=title, anchor="w",
                             font=T.fonts()["dialog_title"], fill="#FFFFFF")
        if subtitle:
            head.create_text(62 if emoji_img else 20, 45, text=subtitle, anchor="w",
                             font=T.fonts()["tiny"], fill="#FFF3E2")
        self.head = head

        self.body = tk.Frame(self, bg=T.BG_APP)
        self.body.pack(fill="both", expand=True, padx=0, pady=0)

        self.footer = tk.Frame(self, bg=T.BG_FOOT, height=62)
        self.footer.pack(fill="x", side="bottom")
        self.footer.pack_propagate(False)

        self._center(master, width, height)
        self.bind("<Escape>", lambda e: self.on_cancel())

    def _center(self, master, w, h):
        try:
            master.update_idletasks()
            x = master.winfo_rootx() + (master.winfo_width() - w) // 2
            y = master.winfo_rooty() + (master.winfo_height() - h) // 3
            self.geometry("%dx%d+%d+%d" % (w, h, max(0, x), max(0, y)))
        except Exception:
            self.geometry("%dx%d" % (w, h))

    def show(self):
        # 关键：内容可能比预设高度高（实测「新建分类」对话框需要 388px，
        # 而预设只有 330px）。高度不够时 packer 会把 footer 和里面的
        # 「保存 / 取消」按钮挤压到 1~4 像素 —— 用户看到的就是「没有确认按钮」。
        # 所以这里先按实际需要的高度把窗口撑开，再居中显示。
        self.update_idletasks()
        w = max(self._dw, self.winfo_reqwidth())
        h = max(self._dh, self.winfo_reqheight())
        if (w, h) != (self._dw, self._dh):
            self.geometry("%dx%d" % (w, h))
        self._center(self.master, w, h)
        self.deiconify()
        self.lift()
        self.grab_set()
        self.focus_force()
        self.wait_window(self)
        return self._result

    def on_cancel(self):
        self._result = None
        self.destroy()

    def on_ok(self):
        self._result = True
        self.destroy()

    def add_footer_buttons(self, ok_text="确定", cancel_text="取消", ok_emoji=None,
                           cancel_emoji=None, ok_variant="primary", on_ok=None):
        cancel = RoundButton(self.footer, text=cancel_text, emoji_img=cancel_emoji,
                             variant="plain", width=104, height=38, bg=T.BG_FOOT,
                             command=self.on_cancel)
        cancel.pack(side="right", padx=(10, 18), pady=12)
        ok = RoundButton(self.footer, text=ok_text, emoji_img=ok_emoji,
                         variant=ok_variant, width=112, height=38, bg=T.BG_FOOT,
                         command=on_ok or self.on_ok)
        ok.pack(side="right", pady=12)
        self.ok_button = ok
        return ok


class FieldRow(object):
    """表单行：左标签 + 右输入控件。"""

    @staticmethod
    def label(parent, text, bg=None):
        return tk.Label(parent, text=text, bg=bg or T.BG_APP, fg=T.TEXT_SUB,
                        font=T.fonts()["small_b"], anchor="w")

    @staticmethod
    def entry(parent, textvariable, width=30, bg=None):
        frame = tk.Frame(parent, bg=T.LINE_STRONG, bd=0)
        e = tk.Entry(frame, textvariable=textvariable, font=T.fonts()["body"],
                     bg=T.BG_INPUT, fg=T.TEXT, relief="flat", bd=0,
                     insertbackground=T.ACCENT, width=width)
        e.pack(fill="both", expand=True, padx=2, pady=2)
        return frame, e


# ============================================================ emoji 选择器
class EmojiPickerDialog(BaseDialog):
    COLS = 10

    def __init__(self, master, bank, current=None, title="选一个彩色图标"):
        BaseDialog.__init__(self, master, title, emoji_img=bank.get("palette", 28),
                            width=560, height=430,
                            subtitle="点一下即可替换，共 %d 个可选" % len(bank.names()))
        self.bank = bank
        self.selected = current
        area = ScrollArea(self.body, bg=T.BG_APP, padding=(16, 12, 16, 12))
        area.pack(fill="both", expand=True)
        self._cells = {}
        grid = tk.Frame(area.inner, bg=T.BG_APP)
        grid.pack(anchor="nw")
        names = bank.names()
        for i, name in enumerate(names):
            img = bank.get(name, 28)
            c = tk.Canvas(grid, width=46, height=46, bg=T.BG_APP,
                          highlightthickness=0, bd=0)
            c.grid(row=i // self.COLS, column=i % self.COLS, padx=3, pady=3)
            c._name = name
            c._img = img
            self._cells[name] = c
            c.bind("<Enter>", lambda e, cc=c: self._hover(cc, True))
            c.bind("<Leave>", lambda e, cc=c: self._hover(cc, False))
            c.bind("<Button-1>", lambda e, n=name: self._pick(n))
            self._paint(c)
        self.add_footer_buttons(ok_text="使用这个", cancel_text="取消",
                                ok_emoji=bank.get("check", 18),
                                cancel_emoji=bank.get("cross", 18))
        self.ok_button.set_enabled(bool(current))

    def _paint(self, c):
        c.delete("all")
        name = c._name
        hot = getattr(c, "_hot", False)
        sel = (name == self.selected)
        if sel:
            T.rrect(c, 1, 1, 45, 45, 12, fill=T.ACCENT_LT, outline=T.ACCENT, width=2)
        elif hot:
            T.rrect(c, 1, 1, 45, 45, 12, fill=T.BG_HOVER, outline=T.LINE, width=1)
        if c._img is not None:
            c.create_image(23, 23, image=c._img)

    def _hover(self, c, flag):
        c._hot = flag
        c.configure(cursor="hand2" if flag else "")
        self._paint(c)

    def _pick(self, name):
        self.selected = name
        for c in self._cells.values():
            self._paint(c)
        self.ok_button.set_enabled(True)

    def on_ok(self):
        self._result = self.selected
        self.destroy()


# ============================================================ 确认框
class ConfirmDialog(BaseDialog):
    def __init__(self, master, bank, title, message, detail="", danger=True):
        BaseDialog.__init__(self, master, title,
                            emoji_img=bank.get("warn" if danger else "question", 28),
                            width=430, height=250 if detail else 210,
                            subtitle="")
        wrap = tk.Frame(self.body, bg=T.BG_APP)
        wrap.pack(fill="both", expand=True, padx=26, pady=(20, 8))
        tk.Label(wrap, text=message, bg=T.BG_APP, fg=T.TEXT,
                 font=T.fonts()["body_b"], wraplength=360, justify="left",
                 anchor="w").pack(anchor="w")
        if detail:
            tk.Label(wrap, text=detail, bg=T.BG_APP, fg=T.TEXT_SUB,
                     font=T.fonts()["small"], wraplength=360, justify="left",
                     anchor="w").pack(anchor="w", pady=(8, 0))
        self.add_footer_buttons(ok_text="确定", cancel_text="取消",
                                ok_emoji=bank.get("check", 18),
                                cancel_emoji=bank.get("cross", 18),
                                ok_variant="danger" if danger else "primary")
        self.bind("<Return>", lambda e: self.on_ok())


# ============================================================ 提示气泡
class Toast(object):
    """在父窗口底部浮现一条卡通提示，2 秒后自动消失。"""

    def __init__(self, master):
        self.master = master
        self._win = None

    def show(self, text, emoji_img=None, ms=2200):
        self.hide()
        top = tk.Toplevel(self.master)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        try:
            top.attributes("-alpha", 0.97)
        except Exception:
            pass
        w = max(220, 60 + len(text) * 9)
        c = tk.Canvas(top, width=w, height=44, bg=T.ACCENT_DK,
                      highlightthickness=0, bd=0)
        c.pack()
        T.rrect(c, 0, 0, w - 1, 42, 14, fill=T.TEXT, outline="")
        x = 20
        if emoji_img is not None:
            c.create_image(24, 21, image=emoji_img)
            x = 42
        c.create_text(x, 21, text=text, anchor="w", font=T.fonts()["small_b"],
                      fill="#FFFFFF")
        self.master.update_idletasks()
        mx = self.master.winfo_rootx() + (self.master.winfo_width() - w) // 2
        my = self.master.winfo_rooty() + self.master.winfo_height() - 96
        top.geometry("+%d+%d" % (max(0, mx), max(0, my)))
        self._win = top
        top.after(ms, self.hide)

    def hide(self):
        if self._win is not None:
            try:
                self._win.destroy()
            except Exception:
                pass
            self._win = None
