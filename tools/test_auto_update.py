# -*- coding: utf-8 -*-
"""自动检测更新回归测试：启动后后台查发布页并弹窗提示

流程：
  1. 把打包好的 exe 拷到临时目录，写一份空数据（update_checked_at=0）
  2. 启动 exe，等后台检测（4 秒定时 + 网络）
  3. 枚举窗口，确认出现「发现新版本」提示框，并截图
  4. 关闭进程，检查 settings.update_checked_at 已写入（成功才记时间）

需要发布页上存在比 exe 内 APP_VERSION 更高的版本才会弹窗；
用法：python tools/test_auto_update.py [exe路径]
"""
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import store as S
import winutil

EXE_SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "程序收纳盒.exe")
TESTDIR = os.path.join(os.environ["TEMP"], "cxhe_auto_test")
SHOT = os.path.join(os.environ["TEMP"], "cxhe_auto_test.png")


def titles(pid):
    """返回该进程所有可见顶层窗口标题。"""
    u = winutil.u
    out = []

    def cb(h, _):
        try:
            if not u.IsWindowVisible(h):
                return True
            p = wintypes.DWORD()
            u.GetWindowThreadProcessId(h, ctypes.byref(p))
            if p.value != pid:
                return True
            n = u.GetWindowTextLengthW(h)
            if not n:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(h, buf, n + 1)
            out.append(buf.value)
        except Exception:
            pass
        return True

    u.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                     ctypes.c_void_p)(cb), 0)
    return out


def pids_of(name):
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + name,
                        "/FO", "CSV", "/NH"], capture_output=True, text=True)
    out = []
    for line in r.stdout.splitlines():
        cols = [c.strip('"') for c in line.split('","')]
        if len(cols) > 1 and cols[0].lower() == name.lower():
            try:
                out.append(int(cols[1]))
            except Exception:
                pass
    return out


def main():
    if os.path.isdir(TESTDIR):
        shutil.rmtree(TESTDIR, ignore_errors=True)
    os.makedirs(os.path.join(TESTDIR, "icons"))
    exe = os.path.join(TESTDIR, "程序收纳盒.exe")
    shutil.copy2(EXE_SRC, exe)
    data = {
        "app": S.APP_TITLE, "version": S.VERSION, "saved": "",
        "settings": {"sort": "manual", "view": "grid", "last_group": "",
                     "update_checked_at": 0},
        "groups": [dict(g) for g in S.DEFAULT_GROUPS],
        "items": [],
    }
    with open(os.path.join(TESTDIR, "apps_data.json"), "w",
              encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    proc = subprocess.Popen([exe], cwd=TESTDIR)
    print("启动 pid", proc.pid, "本地版本", S.APP_VERSION)
    ok = False
    try:
        deadline = time.time() + 25
        while time.time() < deadline:
            time.sleep(1)
            for pid in pids_of("程序收纳盒.exe"):
                ts = titles(pid)
                if any("发现新版本" in t for t in ts):
                    print("检测到提示框:", ts)
                    ok = True
                    time.sleep(1)
                    hwnd = 0
                    u = winutil.u
                    for t in ts:
                        if "程序收纳盒" in t:
                            # 找到主窗口矩形即可截到居中的提示框
                            pass
                    hwnds = []

                    def cb(h, _):
                        if u.IsWindowVisible(h):
                            n = u.GetWindowTextLengthW(h)
                            if n:
                                b = ctypes.create_unicode_buffer(n + 1)
                                u.GetWindowTextW(h, b, n + 1)
                                if "发现新版本" in b.value:
                                    hwnds.append(int(h))
                        return True

                    u.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                                     ctypes.c_void_p)(cb), 0)
                    if hwnds:
                        r = winutil.rect_of(hwnds[0])
                        if r:
                            winutil.snapshot(r[0] - 10, r[1] - 10,
                                             r[2] - r[0] + 20, r[3] - r[1] + 20,
                                             SHOT)
                            print("截图:", SHOT)
                    break
            if ok:
                break
        if not ok:
            print("未出现更新提示，窗口:", titles(proc.pid))
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True)
        for pid in pids_of("程序收纳盒.exe"):
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True)

    try:
        saved = json.load(open(os.path.join(TESTDIR, "apps_data.json"),
                               encoding="utf-8"))
        ts = saved.get("settings", {}).get("update_checked_at", 0)
        print("update_checked_at =", ts)
        if not ts:
            ok = False
    except Exception as e:
        print("读取数据失败:", e)
        ok = False
    print("结果:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
