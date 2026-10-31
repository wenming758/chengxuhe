# -*- coding: utf-8 -*-
"""
资源与路径管理
==============
· app_dir()   程序（exe）所在目录 —— 数据就存这里，保证绿色便携
· res_dir()   打包进去的静态资源目录（单文件 exe 解包后的临时目录）
· EmojiBank   彩色 emoji 图片池（按尺寸缓存 tk.PhotoImage）
· AppIconBank 程序图标图片池（从 icons/*.png 读取并按需缩放缓存）
"""
import os
import sys
import tkinter as tk

import emoji_data

# ---------------------------------------------------------------- 目录
APP_NAME = "程序收纳盒"
DATA_FILE = "apps_data.json"
ICON_DIR = "icons"


def is_frozen():
    return getattr(sys, "frozen", False)


def exe_dir():
    """exe（或脚本）所在目录。"""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def res_dir():
    """打包进 exe 的静态资源所在目录。

    build.spec 里是 datas=[(assets/*, "assets")]，
    所以打包后资源在 _MEIPASS\assets 底下，
    不是 _MEIPASS 根目录 —— 少了 "assets" 这一层就全找不到。
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "assets")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def app_dir():
    """
    数据落盘目录。默认跟 exe 同目录（绿色便携）；
    如果那个目录不可写（比如放在只读位置），退到 %APPDATA%。
    """
    d = exe_dir()
    try:
        probe = os.path.join(d, ".wb_write_test")
        with open(probe, "w") as f:
            f.write("1")
        os.remove(probe)
        return d
    except Exception:
        pass
    fallback = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
    os.makedirs(fallback, exist_ok=True)
    return fallback


def data_path():
    return os.path.join(app_dir(), DATA_FILE)


def icon_dir():
    d = os.path.join(app_dir(), ICON_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def resource(name):
    return os.path.join(res_dir(), name)


# ---------------------------------------------------------------- 尺寸档位
# emoji 原图 56px，用 subsample 得到整数分之一，保证像素干净
SIZES = (56, 28, 18)


def snap_size(size):
    """把请求尺寸吸附到最接近的可用档位（档位是 56/28/18）。"""
    for s in sorted(SIZES):          # 从小到大找第一个够大的
        if s >= size:
            return s
    return max(SIZES)


class EmojiBank(object):
    """彩色 emoji 图片池。"""

    def __init__(self):
        self._cache = {}
        self._missing = set()

    def get(self, name, size=28):
        if not name:
            return None
        size = snap_size(size)
        key = (name, size)
        if key in self._cache:
            return self._cache[key]
        b64 = emoji_data.DATA.get(name)
        if not b64:
            self._missing.add(name)
            return None
        try:
            img = tk.PhotoImage(data=b64)
        except Exception:
            return None
        if size != emoji_data.SIZE:
            factor = max(1, int(round(emoji_data.SIZE / float(size))))
            img = img.subsample(factor, factor)
        self._cache[key] = img
        return img

    def names(self):
        return emoji_data.NAMES


class AppIconBank(object):
    """
    程序图标池。磁盘上存的是 48x48 PNG（store.ICON_SIZE=48）；
    小尺寸用 subsample 取整（48→24），保证清晰。
    """

    CACHE_SIZE = 48

    def __init__(self, folder):
        self.folder = folder
        self._cache = {}

    def path_of(self, filename):
        if not filename:
            return None
        p = filename
        if not os.path.isabs(p):
            p = os.path.join(self.folder, filename)
        return p if os.path.exists(p) else None

    def get(self, filename, size=48):
        p = self.path_of(filename)
        if not p:
            return None
        factor = 1
        if size <= 24:
            factor = 2
        key = (p, factor, os.path.getmtime(p))
        if key in self._cache:
            return self._cache[key]
        try:
            img = tk.PhotoImage(file=p)
        except Exception:
            return None
        if factor > 1:
            img = img.subsample(factor, factor)
        self._cache[key] = img
        return img

    def clear(self):
        self._cache.clear()


# ---------------------------------------------------------------- 杂项
def open_in_explorer(path):
    import subprocess
    if os.path.isfile(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        os.startfile(path)
