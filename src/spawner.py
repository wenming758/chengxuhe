# -*- coding: utf-8 -*-
"""
程序启动器
==========
桌面双击是 explorer 直接 CreateProcess 目标 exe，而以前收纳盒走的是
os.startfile(.lnk) —— ShellExecute 要先解析快捷方式、加载 shell 扩展，
实测 IDM 在 .lnk 上要 2.3 秒才返回，UI 还会跟着卡住。

现在对 exe 直接 CreateProcess（毫秒级返回），只有文档 / .url / .msc
这类必须交给系统关联的才走 ShellExecute。
"""
import ctypes
import os
import subprocess

EXE_EXT = (".exe", ".com")


def is_exe(path):
    return os.path.splitext(path or "")[1].lower() in EXE_EXT


def shell_execute(path, args="", cwd="", verb="open"):
    """ShellExecuteW：交给系统按关联打开，返回是否成功。"""
    SW_SHOWNORMAL = 1
    r = ctypes.windll.shell32.ShellExecuteW(
        None, verb, path, args or None, cwd or None, SW_SHOWNORMAL)
    return r > 32


def run(path, args="", cwd="", admin=False):
    """
    启动一个程序。成功返回 True；文件不存在返回 False；
    启动出错抛异常（由调用方提示用户）。
    """
    path = (path or "").strip().strip('"')
    if not path or not os.path.exists(path):
        return False
    args = (args or "").strip()
    if not cwd or not os.path.isdir(cwd):
        cwd = os.path.dirname(path) if os.path.isfile(path) else ""
    if admin:
        return shell_execute(path, args, cwd, verb="runas")
    if os.path.isfile(path) and is_exe(path):
        # 和资源管理器双击同一条路径：CreateProcess 直接拉起来，不经过 Shell
        cmdline = '"%s"' % path
        if args:
            cmdline += " " + args
        subprocess.Popen(cmdline, cwd=cwd or None, close_fds=True)
        return True
    return shell_execute(path, args, cwd)
