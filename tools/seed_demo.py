# -*- coding: utf-8 -*-
"""造一批演示数据，方便看界面效果（只在本机调试用）。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import assets as A
import iconutil
import store as S

st = S.Store(A.data_path(), A.icon_dir())

targets = [
    (r"C:\Windows\System32\notepad.exe", "记事本", "g_office", "写点东西"),
    (r"C:\Windows\System32\calc.exe", "计算器", "g_tool", ""),
    (r"C:\Windows\System32\mspaint.exe", "画图", "g_media", "随手涂两笔"),
    (r"C:\Windows\System32\cmd.exe", "命令提示符", "g_tool", ""),
    (r"C:\Windows\System32\taskmgr.exe", "任务管理器", "g_tool", ""),
    (r"C:\Windows\explorer.exe", "文件资源管理器", "g_tool", ""),
    (r"C:\Windows\System32\mstsc.exe", "远程桌面", "g_tool", ""),
    (r"C:\Windows\System32\cleanmgr.exe", "磁盘清理", "g_tool", ""),
    (r"C:\Windows\System32\control.exe", "控制面板", "g_tool", ""),
    (r"C:\Windows\System32\osk.exe", "屏幕键盘", "g_tool", ""),
    (r"C:\Windows\System32\SnippingTool.exe", "截图工具", "g_media", ""),
    (r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "PowerShell", "g_tool", ""),
]

desk = os.path.join(os.environ["USERPROFILE"], "Desktop")
if os.path.isdir(desk):
    for f in os.listdir(desk):
        if f.lower().endswith(".lnk"):
            targets.append((os.path.join(desk, f), os.path.splitext(f)[0], "g_default", "桌面快捷方式"))

st.items = []
added = 0
for path, name, group, note in targets:
    if not os.path.exists(path):
        continue
    if st.find_by_path(path):
        continue
    it = st.add_app(path, name=name, group=group, note=note)
    got = iconutil.extract_icon(path)
    if got:
        it["icon"] = st.cache_icon(got)
    added += 1
    if added >= 16:
        break

st.items[0]["pinned"] = True
st.items[0]["count"] = 12
st.items[0]["last"] = "2026-10-14 15:20"
st.items[1]["count"] = 5
st.items[1]["last"] = "2026-10-14 14:02"
st.save()
print("已写入 %d 个演示程序 -> %s" % (added, A.data_path()))
