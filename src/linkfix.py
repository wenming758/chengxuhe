# -*- coding: utf-8 -*-
"""
快捷方式独立化
==============
用户拖进来的往往是一个桌面 .lnk。之前收纳盒把 .lnk 的路径原样存进
apps_data.json，等于收藏了一个「指向桌面快捷方式的引用」——桌面那份一删，
收纳盒里的卡片就找不到文件了。

这里把 .lnk 解析成「真实目标 exe 的绝对路径 + 启动参数 + 工作目录」，
存进数据后卡片直接指向程序本体：删桌面快捷方式、换桌面布局都不再影响。

解析优先走 Win32 COM（IShellLinkW，毫秒级，无需 pywin32），
COM 拿不到结果时才退回 PowerShell。
"""
import ctypes
import os
import subprocess
from ctypes import wintypes

CLSCTX_INPROC_SERVER = 1
STGM_READ = 0

_SHELL_DIRS = [
    os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                 r"Microsoft\Windows\Start Menu\Programs"),
    os.path.join(os.environ.get("APPDATA", ""),
                 r"Microsoft\Windows\Start Menu\Programs"),
    os.path.join(os.environ.get("USERPROFILE", ""), "Desktop"),
    os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Desktop"),
]


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


def _guid(text):
    parts = text.strip("{}").split("-")
    g = _GUID()
    g.Data1 = int(parts[0], 16)
    g.Data2 = int(parts[1], 16)
    g.Data3 = int(parts[2], 16)
    for i, b in enumerate(bytes.fromhex(parts[3] + parts[4])):
        g.Data4[i] = b
    return g


_CLSID_SHELLLINK = _guid("00021401-0000-0000-C000-000000000046")
_IID_ISHELLLINKW = _guid("000214F9-0000-0000-C000-000000000046")
_IID_IPERSISTFILE = _guid("0000010B-0000-0000-C000-000000000046")


def _vcall(ptr, index, restype, *argtypes):
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return proto(vtbl[index])


def _resolve_pywin32(lnk_path):
    """首选 pywin32 的 WScript.Shell：1~2 毫秒，路径按 Unicode 返回。"""
    try:
        import pythoncom
        import win32com.client
    except Exception:
        return None
    inited = False
    shell = None
    sc = None
    try:
        pythoncom.CoInitialize()
        inited = True
    except Exception:
        pass
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        sc = shell.CreateShortcut(lnk_path)
        return {"target": sc.TargetPath or "", "args": sc.Arguments or "",
                "cwd": sc.WorkingDirectory or "", "icon": sc.IconLocation or ""}
    except Exception:
        return None
    finally:
        del sc, shell
        if inited:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


def _resolve_com(lnk_path):
    """用 IShellLinkW 读取 .lnk 的 TargetPath / Arguments / WorkingDirectory。"""
    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx(None, 0x2)          # APARTMENTTHREADED
    link = ctypes.c_void_p()
    persist = ctypes.c_void_p()
    try:
        ole32.CoCreateInstance.argtypes = [
            ctypes.POINTER(_GUID), ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
        ole32.CoCreateInstance.restype = ctypes.c_long
        hr = ole32.CoCreateInstance(
            ctypes.byref(_CLSID_SHELLLINK), None, CLSCTX_INPROC_SERVER,
            ctypes.byref(_IID_ISHELLLINKW), ctypes.byref(link))
        if hr < 0 or not link:
            return None
        qi = _vcall(link, 0, ctypes.c_long,
                    ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))
        if qi(link, ctypes.byref(_IID_IPERSISTFILE),
              ctypes.byref(persist)) < 0 or not persist:
            return None
        load = _vcall(persist, 5, ctypes.c_long, ctypes.c_wchar_p,
                      wintypes.DWORD)
        if load(persist, os.path.abspath(lnk_path), STGM_READ) < 0:
            return None

        def _get(index, size=1024):
            """GetPath / GetWorkingDirectory / GetArguments 都是 (buf, cch)。"""
            buf = ctypes.create_unicode_buffer(size)
            fn = _vcall(link, index, ctypes.c_long, ctypes.c_void_p,
                        ctypes.c_int)
            if fn(link, ctypes.cast(buf, ctypes.c_void_p), size) < 0:
                return ""
            return buf.value or ""

        target = _get(3)
        cwd = _get(8)
        args = _get(10)
        icon = ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            idx = ctypes.c_int(0)
            fn = _vcall(link, 16, ctypes.c_long, ctypes.c_void_p,
                        ctypes.c_int, ctypes.POINTER(ctypes.c_int))
            if fn(link, ctypes.cast(buf, ctypes.c_void_p), 1024,
                  ctypes.byref(idx)) >= 0:
                icon = (buf.value or "").strip()
                if icon and idx.value:
                    icon += ",%d" % idx.value
        except Exception:
            pass
        return {"target": target, "cwd": cwd, "args": args, "icon": icon}
    except Exception:
        return None
    finally:
        for obj in (persist, link):
            if obj:
                try:
                    _vcall(obj, 2, ctypes.c_ulong)(obj)
                except Exception:
                    pass
        try:
            ole32.CoUninitialize()
        except Exception:
            pass


def _resolve_ps(lnk_path):
    """COM 失败时的兜底：让 WScript.Shell 帮我们读，UTF-8 输出防乱码。"""
    sep = "\x1f"
    esc = lnk_path.replace("'", "''")
    script = (
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');"
        "$o=@($s.TargetPath,$s.Arguments,$s.WorkingDirectory,$s.IconLocation)"
        " -join [char]31;"
        "Write-Output $o" % esc)
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=10,
            creationflags=0x08000000)
    except Exception:
        return None
    raw = out.stdout or b""
    text = ""
    for enc in ("utf-8", "gbk"):
        try:
            text = raw.decode(enc).strip()
            break
        except Exception:
            continue
    if not text:
        return None
    parts = text.split(sep)
    while len(parts) < 4:
        parts.append("")
    return {"target": parts[0].strip(), "args": parts[1].strip(),
            "cwd": parts[2].strip(), "icon": parts[3].strip()}


def _norm(p):
    p = (p or "").strip().strip('"')
    if not p:
        return ""
    return os.path.expandvars(p)


def _long_path(p):
    """把 8.3 短路径还原成长路径（COM 有时返回短名）。"""
    p = _norm(p)
    if not p:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(32768)
        n = ctypes.windll.kernel32.GetLongPathNameW(p, buf, 32768)
        if 0 < n < 32768:
            return buf.value
    except Exception:
        pass
    return p


def resolve_lnk(path, depth=0):
    """
    解析 .lnk，返回 {target, args, cwd, icon}；失败返回 None。
    target 是展开环境变量后的绝对路径（.lnk 套 .lnk 会递归解析）。
    """
    if depth > 4 or not path or not os.path.isfile(path):
        return None
    info = _resolve_pywin32(path) or _resolve_com(path) or _resolve_ps(path)
    if not info:
        return None
    target = _norm(info.get("target"))
    cwd = _long_path(info.get("cwd"))
    args = (info.get("args") or "").strip()
    icon = _norm(info.get("icon"))
    if not target:
        return None
    if not os.path.isabs(target):
        target = os.path.normpath(os.path.join(cwd or os.path.dirname(path),
                                               target))
    target = os.path.normpath(target)
    if target.lower().endswith(".lnk") and os.path.isfile(target):
        inner = resolve_lnk(target, depth + 1)
        if inner:
            if inner.get("args"):
                args = (inner["args"] + " " + args).strip()
            cwd = inner.get("cwd") or cwd
            icon = inner.get("icon") or icon
            target = inner["target"]
    return {"target": target, "args": args, "cwd": cwd, "icon": icon}


def independent(path):
    """
    把一个拖进来 / 选进来的路径变成「独立条目」：
    返回 {path, args, cwd, icon_src, lnk}；.lnk 解析失败返回 None。
    非快捷方式原样返回（args/cwd 由调用方决定）。
    """
    if not path or not os.path.isfile(path):
        return None
    if not path.lower().endswith(".lnk"):
        return {"path": path, "args": "", "cwd": os.path.dirname(path),
                "icon_src": path, "lnk": ""}
    info = resolve_lnk(path)
    if not info or not os.path.exists(info["target"]):
        return None
    target = info["target"]
    cwd = info.get("cwd") or os.path.dirname(target)
    if not os.path.isdir(cwd):
        cwd = os.path.dirname(target)
    icon_src = info.get("icon") or target
    icon_src = icon_src.split(",")[0].strip().strip('"')
    if not os.path.isfile(icon_src):
        icon_src = target
    return {"path": target, "args": info.get("args", ""), "cwd": cwd,
            "icon_src": icon_src, "lnk": os.path.abspath(path)}


def find_shortcut(name, max_depth=4):
    """桌面快捷方式被删后，按显示名去开始菜单 / 桌面找回同名 .lnk。"""
    want = (name or "").strip().lower()
    if not want:
        return ""
    for root in _SHELL_DIRS:
        if not root or not os.path.isdir(root):
            continue
        base_depth = root.rstrip("\\").count(os.sep)
        for dirpath, dirnames, filenames in os.walk(root):
            if dirpath.count(os.sep) - base_depth >= max_depth:
                dirnames[:] = []
            for fn in filenames:
                if fn.lower() == want + ".lnk":
                    return os.path.join(dirpath, fn)
    return ""


def migrate_items(items, log_path=None, icon_cb=None):
    """
    把历史数据里的 .lnk 条目就地升级成绝对路径条目。
    返回实际转换的条目数；log_path 给了就追加一份可回溯日志。
    """
    lines = []
    changed = 0
    for it in items or []:
        raw = it.get("path") or ""
        if not raw.lower().endswith(".lnk"):
            continue
        lnk = raw
        if not os.path.isfile(lnk):
            # 桌面快捷方式已经不在了，去开始菜单按名字捞回来
            alt = find_shortcut(os.path.splitext(os.path.basename(raw))[0])
            if alt:
                lnk = alt
        info = independent(lnk) if os.path.isfile(lnk) else None
        if not info:
            lines.append("跳过  %s  （快捷方式已失效，未找到真实目标）" % raw)
            continue
        it["path"] = info["path"]
        if info.get("args") and not (it.get("args") or "").strip():
            it["args"] = info["args"]
        it["workdir"] = info["cwd"]
        it["lnk"] = info["lnk"]
        if icon_cb is not None:
            try:
                icon_cb(it, info["icon_src"])
            except Exception:
                pass
        changed += 1
        lines.append("修复  %s  ->  %s" % (raw, info["path"]))
    if log_path and lines:
        try:
            import time
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("\n[%s] 快捷方式独立化\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
                for ln in lines:
                    f.write("  " + ln + "\n")
        except Exception:
            pass
    return changed
