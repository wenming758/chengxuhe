# -*- coding: utf-8 -*-
"""
卡通风格设计系统
================
暖奶油底 + 橙色主色（跟程序图标同一套色），圆角厚描边卡片，
糖果色轮换边框，配合彩色 emoji 做点缀。

所有颜色 / 圆角 / 间距都集中在这里，界面各模块统一取用。
"""
import tkinter as tk

# ============================================================ 颜色
BG_APP = "#FFF7EC"          # 窗口底（暖奶油）
BG_HEAD_A = "#FFC46B"       # 顶栏渐变起
BG_HEAD_B = "#FF8A3D"       # 顶栏渐变止
BG_HEAD_C = "#FF7A2E"
BG_SIDE = "#FFFCF6"         # 侧栏
BG_CARD = "#FFFFFF"         # 卡片
BG_CARD_SOFT = "#FFFDF8"    # 卡片悬停
BG_INPUT = "#FFFFFF"
BG_INPUT_SOFT = "#FFFBF4"
BG_TAG = "#FFF3E2"
BG_SEL = "#FFE7CC"          # 侧栏选中
BG_HOVER = "#FFF1DF"
BG_FOOT = "#FFF1DF"

SHADOW = "#F0DFC6"          # 卡通投影（比底色深一点的暖色）
SHADOW_HOVER = "#E4CCA9"
LINE = "#F2E0C8"            # 分隔线
LINE_STRONG = "#E7CFB2"

ACCENT = "#FF8A3D"          # 主橙
ACCENT_DK = "#E8701A"
ACCENT_LT = "#FFE9D6"
ACCENT_SOFT = "#FFB673"

TEXT = "#4A3728"            # 主文字（暖深棕）
TEXT_SUB = "#9A8270"
TEXT_MUTED = "#BCA895"
TEXT_ON_ACCENT = "#FFFFFF"

OK = "#4CC38A"
OK_LT = "#E8F9F0"
DANGER = "#FF6B6B"
DANGER_DK = "#E14C4C"
DANGER_LT = "#FFECEC"
WARN = "#FFB020"
WARN_LT = "#FFF6E3"
INFO = "#57B8FF"
INFO_LT = "#EAF6FF"
PURPLE = "#A98BFF"
PURPLE_LT = "#F3EEFF"

# 卡片糖果色边框（按索引轮换）
CARD_COLORS = [
    "#FFC94D",  # 柠檬黄
    "#63C9F5",  # 天蓝
    "#5FD0AE",  # 薄荷
    "#FF9EC4",  # 樱花粉
    "#B6A4FF",  # 香芋紫
    "#8FD97F",  # 青草绿
    "#FF9E7A",  # 蜜桃橙
    "#7FD8E8",  # 湖水青
    "#F5B7D5",  # 玫瑰粉
    "#9CC7FF",  # 淡蓝
]

# 分类可选的糖果色
GROUP_COLORS = [
    "#FF8A3D", "#FF9EC4", "#63C9F5", "#5FD0AE", "#B6A4FF",
    "#FFC94D", "#8FD97F", "#FF9E7A", "#7FD8E8", "#F5B7D5",
]


def card_color(idx):
    return CARD_COLORS[idx % len(CARD_COLORS)]


def group_color(idx):
    return GROUP_COLORS[idx % len(GROUP_COLORS)]


# ============================================================ 字体
UI_FONT = "Microsoft YaHei UI"
UI_FONT_ALT = "Microsoft YaHei"


def fonts():
    """Tk 初始化之后调用，返回字体字典。"""
    return {
        "logo": (UI_FONT, 18, "bold"),
        "logo_sub": (UI_FONT, 9),
        "head_btn": (UI_FONT, 10, "bold"),
        "section": (UI_FONT, 11, "bold"),
        "body": (UI_FONT, 10),
        "body_b": (UI_FONT, 10, "bold"),
        "small": (UI_FONT, 9),
        "small_b": (UI_FONT, 9, "bold"),
        "tiny": (UI_FONT, 8),
        "tiny_b": (UI_FONT, 8, "bold"),
        "card_title": (UI_FONT, 10, "bold"),
        "card_sub": (UI_FONT, 8),
        "dialog_title": (UI_FONT, 14, "bold"),
        "dialog_btn": (UI_FONT, 10, "bold"),
        "menu": (UI_FONT, 10),
    }


# ============================================================ 画布工具
_RRECT_CACHE = {}


def rrect(canvas, x1, y1, x2, y2, r, **kw):
    """圆角矩形。

    同尺寸的圆角矩形（卡片、按钮、底纹等大量复用）顶点坐标直接复用，
    省掉每次重绘现算 22 个点 + smooth 多边形的开销。
    """
    r = max(0, min(r, abs(x2 - x1) / 2.0, abs(y2 - y1) / 2.0))
    ck = (x1, y1, x2, y2, r)
    pts = _RRECT_CACHE.get(ck)
    if pts is None:
        pts = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        if len(_RRECT_CACHE) > 3000:
            _RRECT_CACHE.clear()
        _RRECT_CACHE[ck] = pts
    return canvas.create_polygon(pts, smooth=True, **kw)


def pill(canvas, x1, y1, x2, y2, **kw):
    return rrect(canvas, x1, y1, x2, y2, (y2 - y1) / 2.0, **kw)


def _h2r(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def hgrad(canvas, x1, y1, x2, y2, c1, c2, steps=64, tags=None):
    r1, g1, b1 = _h2r(c1)
    r2, g2, b2 = _h2r(c2)
    w = max(1, x2 - x1)
    sw = w / float(steps)
    ids = []
    for i in range(steps):
        t = i / float(max(steps - 1, 1))
        col = "#%02X%02X%02X" % (int(r1 + (r2 - r1) * t),
                                 int(g1 + (g2 - g1) * t),
                                 int(b1 + (b2 - b1) * t))
        ids.append(canvas.create_rectangle(x1 + i * sw, y1, x1 + (i + 1) * sw + 1, y2,
                                           fill=col, outline="", tags=tags))
    return ids


def vgrad(canvas, x1, y1, x2, y2, c1, c2, steps=40, tags=None):
    r1, g1, b1 = _h2r(c1)
    r2, g2, b2 = _h2r(c2)
    h = max(1, y2 - y1)
    sh = h / float(steps)
    ids = []
    for i in range(steps):
        t = i / float(max(steps - 1, 1))
        col = "#%02X%02X%02X" % (int(r1 + (r2 - r1) * t),
                                 int(g1 + (g2 - g1) * t),
                                 int(b1 + (b2 - b1) * t))
        ids.append(canvas.create_rectangle(x1, y1 + i * sh, x2, y1 + (i + 1) * sh + 1,
                                           fill=col, outline="", tags=tags))
    return ids


def lighten(hex_color, ratio=0.85):
    r, g, b = _h2r(hex_color)
    r = int(r + (255 - r) * ratio)
    g = int(g + (255 - g) * ratio)
    b = int(b + (255 - b) * ratio)
    return "#%02X%02X%02X" % (r, g, b)


def darken(hex_color, ratio=0.18):
    r, g, b = _h2r(hex_color)
    return "#%02X%02X%02X" % (int(r * (1 - ratio)), int(g * (1 - ratio)), int(b * (1 - ratio)))


def mix(c1, c2, t):
    r1, g1, b1 = _h2r(c1)
    r2, g2, b2 = _h2r(c2)
    return "#%02X%02X%02X" % (int(r1 + (r2 - r1) * t),
                              int(g1 + (g2 - g1) * t),
                              int(b1 + (b2 - b1) * t))


_FONT_CACHE = {}
_ELLIPSIS_CACHE = {}


def _tkfont(spec):
    key = tuple(spec)
    f = _FONT_CACHE.get(key)
    if f is None:
        try:
            from tkinter import font as tkfont
            f = tkfont.Font(font=spec)
        except Exception:
            return None
        _FONT_CACHE[key] = f
    return f


def ellipsis(text, font, max_w):
    """按像素宽度截断文字并加省略号（Tk 没有原生省略）。

    结果做缓存：卡片每次 hover 重绘都会调 3 次，命中缓存后几乎零成本。
    """
    if not text or max_w <= 0:
        return text or ""
    key = (text, tuple(font) if not isinstance(font, str) else font,
           int(max_w))
    cached = _ELLIPSIS_CACHE.get(key)
    if cached is not None:
        return cached
    f = _tkfont(font)
    if f is None:
        return text
    try:
        if f.measure(text) <= max_w:
            out = text
        else:
            ell = "…"
            ew = f.measure(ell)
            lo, hi = 0, len(text)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if f.measure(text[:mid]) + ew <= max_w:
                    lo = mid
                else:
                    hi = mid - 1
            out = text[:lo] + ell if lo > 0 else ell
    except Exception:
        out = text
    # 缓存有上限，避免极端情况下无限增长
    if len(_ELLIPSIS_CACHE) > 4000:
        _ELLIPSIS_CACHE.clear()
    _ELLIPSIS_CACHE[key] = out
    return out


def rounded_rect_points(x1, y1, x2, y2, r):
    r = max(0, min(r, (x2 - x1) / 2.0, (y2 - y1) / 2.0))
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
