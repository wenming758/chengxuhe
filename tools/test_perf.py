# -*- coding: utf-8 -*-
"""性能回归：确认切换分类 / 刷新 / hover 都足够快，且功能仍正确。

阈值取得比实测宽不少（沙箱机器负载高，抖动大），只用来拦住
「又退回每次都全量重建」这类明显劣化。
"""
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

import assets as A                      # noqa: E402
A.app_dir = lambda: A.exe_dir()         # 固定路径，隔离沙箱 remove 垫片
import main as M                        # noqa: E402
import store as S                       # noqa: E402
import theme as T                       # noqa: E402


def timed(fn, n=25, warm=6):
    for _ in range(warm):
        fn()
    ts = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t) * 1000)
    ts.sort()
    return statistics.median(ts), ts[int(len(ts) * 0.9)], ts[-1]


def main():
    fails = []
    app = M.Launcher()
    app.root.update()

    groups = [g["id"] for g in app.store.groups]
    user_groups = [g for g in groups if g not in (S.G_ALL, S.G_FAV, S.G_RECENT)]

    # --- 1) 切分类（含空分类来回切，验证不再反复重建空态）
    seq = user_groups + [S.G_ALL, S.G_FAV]
    idx = {"i": 0}

    def switch():
        g = seq[idx["i"] % len(seq)]
        idx["i"] += 1
        app._select_group(g)
    med, p90, mx = timed(switch, n=30)
    print(">>> 切换分类: med=%.2fms p90=%.2fms max=%.2fms" % (med, p90, mx))
    if med > 30:
        fails.append("切换分类中位数过慢 (%.1fms)" % med)

    # --- 2) 刷新
    med, p90, mx = timed(lambda: app.refresh(reset_scroll=False), n=30)
    print(">>> refresh:   med=%.2fms p90=%.2fms max=%.2fms" % (med, p90, mx))
    if med > 20:
        fails.append("refresh 中位数过慢 (%.1fms)" % med)

    # --- 3) hover 卡片（重绘）
    app._select_group(S.G_ALL)
    app.root.update()
    if app.cards:
        c = app.cards[0]
        med, p90, mx = timed(lambda: (c._enter(), c._leave()), n=40)
        print(">>> hover 卡片: med=%.2fms p90=%.2fms max=%.2fms" % (med, p90, mx))
        if med > 15:
            fails.append("hover 重绘过慢 (%.1fms)" % med)
    else:
        print(">>> hover 卡片: 跳过（无卡片）")

    # --- 4) 功能正确性：切到有内容的分类应显示卡片，切到空分类应显示空态
    all_items = app.store.visible_items(S.G_ALL, "", "manual")
    app._select_group(S.G_ALL)
    app.root.update()
    if all_items:
        if len(app.cards) < len(all_items):
            fails.append("全部分类未渲染出全部卡片")
        if not app.cards[0].winfo_ismapped():
            fails.append("卡片未显示")
        print(">>> 全部分类: %d 张卡片可见 = %s"
              % (len(app.cards), app.cards[0].winfo_ismapped()))

    # 找一个空的自建分类
    empty_gid = None
    for g in user_groups:
        if not app.store.visible_items(g, "", "manual"):
            empty_gid = g
            break
    if empty_gid:
        app._select_group(empty_gid)
        app.root.update()
        vis = [c for c in app.cards if c.winfo_ismapped()]
        if vis:
            fails.append("空分类仍显示卡片")
        if app._empty_frame is None or not app._empty_frame.winfo_ismapped():
            fails.append("空分类未显示空态提示")
        print(">>> 空分类: 可见卡片=%d, 空态显示=%s"
              % (len(vis), bool(app._empty_frame and app._empty_frame.winfo_ismapped())))
        # 再切回全部，空态应隐藏
        app._select_group(S.G_ALL)
        app.root.update()
        if app._empty_frame.winfo_ismapped():
            fails.append("切回全部后空态未隐藏")

    app.root.destroy()
    print(">>> 总体: %s" % ("PASS" if not fails else "FAIL -> " + "; ".join(fails)))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
