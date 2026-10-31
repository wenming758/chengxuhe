# -*- coding: utf-8 -*-
"""图标修复回归测试：旧缓存自动重抓 + 卡片图标尺寸

流程：
  1. 把打包好的 exe 拷到临时目录
  2. 造一份 apps_data.json：条目指向真实程序，但图标是旧版「整张画布缩放」
     生成的小米粒 PNG，iconv 保持旧值 0
  3. 启动 exe，等后台线程重抓图标
  4. 关闭 exe，检查 apps_data.json 里的 iconv 已升到 ICON_FORMAT，
     新 PNG 的有效内容占满 48x48 画布，并截一张主界面图
"""
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import iconutil
import pngutil
import store as S
import winutil

EXE_SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "程序收纳盒.exe")
TESTDIR = os.path.join(os.environ["TEMP"], "cxhe_icon_test")
SHOT = os.path.join(os.environ["TEMP"], "cxhe_icon_test.png")
LOG = open(os.path.join(os.environ["TEMP"], "cxhe_icon_test.log"), "w", encoding="utf-8")

# 已知 JUMBO 画布有大片透明留白的程序
APPS = [
    ("Internet Download Manager", r"E:\Program Files (x86)\IDM\IDM-v6.38.7.2简体中文特别解锁绿色版\IDMan.exe"),
    ("7-Zip 文件管理器", r"C:\Program Files\7-Zip\7zFM.exe"),
    ("RustDesk", r"E:\Program Files (x86)\RustDesk\rustdesk.exe"),
    ("FinalShell", r"E:\NAS管理\SSH\FinalShell-v4.5.3\finalshell.exe"),
    ("绘图", r"C:\Windows\System32\mspaint.exe"),
]


def log(*a):
    line = "[%.2f] %s" % (time.time() % 1000, " ".join(str(x) for x in a))
    print(line)
    LOG.write(line + "\n")
    LOG.flush()


def find_main_window():
    """PyInstaller 单文件模式会另起子进程，按标题找 TkTopLevel 最稳。"""
    import ctypes
    from ctypes import wintypes
    u = winutil.u
    found = []

    def cb(h, _):
        try:
            if not u.IsWindowVisible(h):
                return True
            n = u.GetWindowTextLengthW(h)
            if not n:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(h, buf, n + 1)
            if "程序收纳盒" not in buf.value:
                return True
            cn = ctypes.create_unicode_buffer(256)
            u.GetClassNameW(h, cn, 256)
            if cn.value == "TkTopLevel":
                found.append(int(h))
        except Exception:
            pass
        return True

    u.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                     ctypes.c_void_p)(cb), 0)
    return found[0] if found else 0


def old_style_icon(path):
    """复刻旧版行为：整张 256 画布直接缩到 48。"""
    raw = iconutil._icon_from_image_list(path, iconutil.SHIL_JUMBO)
    if not raw:
        raw = iconutil.extract_icon(path)
    if not raw:
        return None
    w, h, rgba = raw
    return pngutil.encode_rgba_scaled(w, h, rgba, 48, 48)


def main():
    if os.path.isdir(TESTDIR):
        shutil.rmtree(TESTDIR, ignore_errors=True)
    os.makedirs(os.path.join(TESTDIR, "icons"))
    exe = os.path.join(TESTDIR, "程序收纳盒.exe")
    shutil.copy2(EXE_SRC, exe)
    log("exe 已复制:", exe, os.path.getsize(exe), "字节")

    items = []
    icon_dir = os.path.join(TESTDIR, "icons")
    for i, (name, path) in enumerate(APPS):
        if not os.path.exists(path):
            log("跳过（本机不存在）:", path)
            continue
        png = old_style_icon(path)
        if not png:
            log("跳过（旧图标提取失败）:", path)
            continue
        fn = "old_%d.png" % i
        with open(os.path.join(icon_dir, fn), "wb") as f:
            f.write(png)
        items.append({
            "id": "t%d" % i, "name": name, "path": path, "args": "",
            "note": "", "group": "g_default", "icon": fn, "emoji": "rocket",
            "pinned": False, "count": 0, "added": "2026-10-31 10:00",
            "last": "", "workdir": "", "lnk": "", "iconv": 0,
        })
        log("测试条目:", name, "旧图标:", fn, "大小:", len(png))
    if not items:
        log("没有可测试的程序，退出")
        return 1

    data = {
        "app": S.APP_TITLE, "version": S.VERSION, "saved": "2026-10-31 10:00",
        "settings": {"sort": "manual", "view": "grid", "last_group": ""},
        "groups": [dict(g) for g in S.DEFAULT_GROUPS],
        "items": items,
    }
    with open(os.path.join(TESTDIR, "apps_data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log("apps_data.json 已写入:", len(items), "条")

    proc = subprocess.Popen([exe], cwd=TESTDIR)
    log("已启动 exe, pid=", proc.pid)
    time.sleep(7)          # 1s 定时 + 后台提取

    hwnd = find_main_window()
    if hwnd:
        try:
            u = winutil.u
            u.ShowWindow(hwnd, 9)                  # SW_RESTORE
            # 置顶，防止别的窗口压在截图区域上
            u.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(-1),
                           0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
            u.SetForegroundWindow(hwnd)
        except Exception:
            pass
        time.sleep(0.8)
        r = winutil.rect_of(hwnd)
        if r and (r[2] - r[0]) > 600:
            winutil.snapshot(r[0], r[1], r[2] - r[0], r[3] - r[1], SHOT)
            log("截图:", SHOT, r)
    else:
        log("未找到主窗口，跳过截图")

    new = json.load(open(os.path.join(TESTDIR, "apps_data.json"), encoding="utf-8"))
    ok = True
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    try:
        for it in new.get("items", []):
            if not it.get("id", "").startswith("t"):
                continue
            iconv = int(it.get("iconv", 0) or 0)
            icon = it.get("icon", "")
            old = icon.startswith("old_")
            log("检查:", it.get("name"), "iconv=", iconv, "icon=", icon, "旧图标=", old)
            if iconv != S.ICON_FORMAT or old or not icon:
                ok = False
                continue
            p = os.path.join(icon_dir, icon)
            if not os.path.exists(p):
                ok = False
                log("  新图标文件不存在:", p)
                continue
            # pngutil 无解码，这里用 Tk 读像素统计有效占比
            img = tk.PhotoImage(file=p)
            w, h = img.width(), img.height()
            op = 0
            for y in range(h):
                for x in range(w):
                    if img.transparency_get(x, y) is False:
                        op += 1
            ratio = op / float(w * h)
            log("  新图标 %dx%d 有效像素占比 %.2f" % (w, h, ratio))
            if ratio < 0.4:
                ok = False
    finally:
        root.destroy()
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True)
    log("结果:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
