# -*- coding: utf-8 -*-
"""
打包版 exe「新建分类」全流程端到端验证
  1. 把 exe 拷到临时目录（数据文件跟着落在临时目录，不碰真实数据）
  2. 启动 → 真实鼠标点击「新建分类」→ 校验对话框弹出
  3. 真实鼠标点击对话框里的「保存」（实心橙按钮，右下角）
  4. 校验临时目录的 apps_data.json 里真的多了一个分类
  5. 关闭程序
"""
import ctypes, json, os, shutil, subprocess, sys, tempfile, time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from winutil import (u, k, snapshot, real_click, pids_by_image, toplevels_of_pid,
                     rect_of, pid_of, point_belongs_to, hide_console)

SRC_EXE = os.path.join(os.path.dirname(HERE), "程序收纳盒.exe")
WORK = tempfile.mkdtemp(prefix="wb_exe_test_")
EXE = os.path.join(WORK, "程序收纳盒.exe")
shutil.copy(SRC_EXE, EXE)
# 带上初始数据，保证点击前能读到基线分类数
DATA_SRC = os.path.join(os.path.dirname(HERE), "apps_data.json")
if os.path.exists(DATA_SRC):
    shutil.copy(DATA_SRC, os.path.join(WORK, "apps_data.json"))
SHOT = os.path.join(WORK, "_dlg.png")


def count_groups():
    try:
        with open(os.path.join(WORK, "apps_data.json"), encoding="utf-8") as f:
            return len(json.load(f)["groups"])
    except Exception:
        return -1


def save_button_center(dlg):
    """按对话框布局算「保存」按钮中心（客户端坐标转屏幕坐标）。

    布局来源 widgets.BaseDialog.add_footer_buttons：
      footer 高 62，pack(side="bottom") → 占客户端最下面 62px
      按钮 pady=12，高 38 → 按钮纵向位于客户端 y = H-62-12 .. H-62-12+38
      取消(宽104) 先 pack(side=right, padx=(10,18)) 在最右，
      保存(宽112) 接着 pack(side=right) 紧贴它左边 →
        保存 x = 470-18-104-112 .. 470-18-104 = 236..348
    返回 (screen_x, screen_y)；客户端尺寸不是 470x388 时返回 None
    （330 是被挤扁的旧版布局，保存按钮只有 1px 高、点不中）。
    """
    cr = wintypes.RECT()
    u.GetClientRect(wintypes.HWND(dlg), ctypes.byref(cr))
    if (cr.right, cr.bottom) != (470, 388):
        return None
    pt = wintypes.POINT(0, 0)
    u.ClientToScreen(wintypes.HWND(dlg), ctypes.byref(pt))
    return pt.x + 292, pt.y + 333        # 保存按钮中心


def is_orange(rgba, w, x, y):
    if not (0 <= x < w and 0 <= y < len(rgba) // (w * 4)):
        return False
    i = (y * w + x) * 4
    return rgba[i] > 220 and 90 < rgba[i + 1] < 190 and rgba[i + 2] < 110


def main():
    p = subprocess.Popen([EXE], cwd=WORK)
    print(">>> 启动 exe pid=%d (工作目录 %s)" % (p.pid, WORK))
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
        print(">>> FAIL: 没找到主窗口"); p.kill(); return 1
    time.sleep(2.0)
    main_hwnd = toplevels_of_pid(child)[0][0]

    hide_console()
    u.SetWindowPos(wintypes.HWND(main_hwnd), wintypes.HWND(0), 0, 0, 960, 600, 0x44)
    time.sleep(1.0)
    u.SetForegroundWindow(wintypes.HWND(main_hwnd))
    time.sleep(0.6)
    # ---- 1) 点「新建分类」（纯白按钮，侧栏底部）。窗口刚 resize 完可能还没
    # 画完，多重试几次截图
    cx0 = 111
    best = None
    for attempt in range(6):
        x, y, x2, y2 = rect_of(main_hwnd)
        rgba, w, h = snapshot(x, y, x2 - x, y2 - y, SHOT)
        print(">>> 第%d次截图 主窗口 (%d,%d)-(%d,%d) 尺寸 %dx%d"
              % (attempt + 1, x, y, x2, y2, x2 - x, y2 - y))
        for yy in range(h - 200, h - 20):
            run = 0
            for xx in range(18, 195):
                i = (yy * w + xx) * 4
                if rgba[i] >= 250 and rgba[i + 1] >= 250 and rgba[i + 2] >= 250:
                    run += 1
                    if run >= 120:
                        best = yy
                else:
                    run = 0
        if best is not None:
            break
        time.sleep(1.0)
    if best is None:
        print(">>> FAIL: 没找到「新建分类」按钮"); p.kill(); return 1
    y1, y2b = best, best
    while y1 - 1 > 0 and all(rgba[((y1 - 1) * w + cx0) * 4 + j] >= 250 for j in (0, 1, 2)):
        y1 -= 1
    while y2b + 1 < h and all(rgba[((y2b + 1) * w + cx0) * 4 + j] >= 250 for j in (0, 1, 2)):
        y2b += 1
    cx, cy = x + cx0, y + (y1 + y2b) // 2
    if not point_belongs_to(main_hwnd, cx, cy)[1]:
        print(">>> FAIL: 新建分类按钮被其它窗口盖住"); p.kill(); return 1
    n0 = count_groups()
    print(">>> 点击「新建分类」(%d,%d)，点击前分类数=%d" % (cx, cy, n0))
    tops_before = [t[0] for t in toplevels_of_pid(child)]
    u.SetCursorPos(cx, cy); time.sleep(0.15)
    real_click(cx, cy)
    time.sleep(1.2)

    # 新增的那个顶层窗口才是对话框（枚举顺序不保证，不能简单取 [-1]）
    tops = toplevels_of_pid(child)
    fresh = [t[0] for t in tops if t[0] not in tops_before]
    if not fresh:
        print(">>> FAIL: 点了按钮但对话框没出来（顶层窗口数=%d）" % len(tops))
        p.kill(); return 1
    dlg = fresh[-1]
    dx, dy, dx2, dy2 = rect_of(dlg)
    print(">>> 对话框出现 0x%x (%d,%d)-(%d,%d)" % (dlg, dx, dy, dx2, dy2))

    # ---- 2) 点对话框里的「保存」（实心橙按钮，footer 右侧）
    rgba, w, h = snapshot(dx, dy, dx2 - dx, dy2 - dy, SHOT)
    pos = save_button_center(dlg)
    if pos is not None and is_orange(rgba, w, pos[0] - dx, pos[1] - dy):
        ox, oy = pos
        print(">>> 「保存」按钮(按布局计算)= (%d,%d) 该点确为橙色 ✓" % (ox, oy))
    else:
        print(">>> 布局算出来的位置不是橙色，改为在 footer 区域里扫橙色")
        bw, bh = w, h
        cand = []
        for yy in range(int(bh * 0.75), bh):
            for xx in range(bw // 2, bw):
                if is_orange(rgba, w, xx, yy) and bh - 100 < yy < bh - 10:
                    cand.append((xx, yy))
        if not cand:
            print(">>> FAIL: 对话框里没找到橙色「保存」按钮"); p.kill(); return 1
        # 取色块重心
        ox = dx + sum(c[0] for c in cand) // len(cand)
        oy = dy + sum(c[1] for c in cand) // len(cand)
        print(">>> 「保存」按钮(扫描)= (%d,%d) n=%d" % (ox, oy, len(cand)))
    print(">>> 点击「保存」(%d,%d)" % (ox, oy))
    if not point_belongs_to(dlg, ox, oy)[1]:
        print(">>> FAIL: 保存按钮被其它窗口盖住")
        u.PostMessageW(wintypes.HWND(dlg), 0x0010, 0, 0)
        p.kill(); return 1
    u.SetCursorPos(ox, oy); time.sleep(0.15)
    real_click(ox, oy)
    time.sleep(1.5)

    tops2 = [t[0] for t in toplevels_of_pid(child) if t[0] != main_hwnd]
    closed = len(tops2) == 0
    n1 = count_groups()
    print(">>> 对话框已关闭: %s   分类数 %d -> %d" % (closed, n0, n1))
    names = []
    try:
        with open(os.path.join(WORK, "apps_data.json"), encoding="utf-8") as f:
            names = [g["name"] for g in json.load(f)["groups"]]
    except Exception:
        pass
    print(">>> 分类列表: %s" % names)
    ok = closed and n1 == n0 + 1
    print(">>> 新建分类并落盘: %s" % ("PASS" if ok else "FAIL"))

    # ---- 3) 关闭主程序
    u.PostMessageW(wintypes.HWND(main_hwnd), 0x0010, 0, 0)
    t1 = time.time()
    while time.time() - t1 < 75:
        if p.poll() is not None:
            break
        time.sleep(1.0)
    code = p.poll()
    if code is None:
        p.kill()
        print(">>> 主程序已强制结束（bootloader 自清理较慢，属正常）")
    else:
        print(">>> 主程序退出码=%s" % code)
    print(">>> 总体: %s" % ("PASS" if ok else "FAIL"))
    shutil.rmtree(WORK, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
