# -*- coding: utf-8 -*-
"""
在线升级（Gitee 仓库发布页）
============================
· 升级源：wenming760/chengxuhe 的 Gitee Release
· 判定方式：拿最新 Release 的 tag_name（如 v0.1.2）和本地版本号比大小，
  远程版本号更大 => 有新版本可升。
· 下载：取 Release 里名字以 .exe 结尾的资产，直接下载到临时文件，
  再写一个小 bat 等本程序退出后把新 exe 覆盖到源文件并重启。

说明：升级源是公开的 Git 发布页，无需鉴权；这里只做「读最新版本 + 下 exe」。
"""
import json
import os
import re
import ssl
import sys
import time
import urllib.request
import urllib.error

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

# 单文件模式（PyInstaller onefile）下，sys.executable 指向临时解包目录里的
# 副本，不是用户真正运行的那个 exe；启动时的 argv[0] 才是磁盘上的真身。
def real_exe_path():
    return os.path.abspath(sys.argv[0])


def _ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def parse_version(v):
    """'v0.1.2' / '0.1.2' -> (0, 1, 2)，用于按大小比对。"""
    v = (v or "").strip().lstrip("vVuU")
    parts = re.findall(r"\d+", v)
    return tuple(int(p) for p in parts) or (0,)


def human_size(n):
    try:
        n = int(n)
    except Exception:
        return "?"
    if n >= 1024 * 1024:
        return "%.1f MB" % (n / 1024.0 / 1024.0)
    if n >= 1024:
        return "%.1f KB" % (n / 1024.0)
    return "%d B" % n


def probe_size(url):
    """探测下载直链的真实大小（字节）。HEAD 不行就退回 GET 只读响应头。

    只在确认框里用，省得显示「0 B」。读头不读体，几乎不耗流量。
    """
    hdrs = {"User-Agent": _UA, "Referer": "https://gitee.com/"}
    # 先试 HEAD（不传 body），多数 CDN 会回 Content-Length
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers=hdrs)
            r = urllib.request.urlopen(req, context=_ctx(), timeout=20)
            try:
                cl = int(r.headers.get("Content-Length", "0") or 0)
            finally:
                r.close()
            if cl:
                return cl
        except Exception:
            continue
    return 0


def _fetch_latest(api_url):
    req = urllib.request.Request(api_url + "/releases/latest",
                                 headers={"User-Agent": _UA,
                                          "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, context=_ctx(), timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _pick_patch(assets, local_version):
    """从发布资产里找「本地版本 -> 最新版本」的增量补丁。"""
    local = parse_version(local_version)
    best = None
    for a in assets:
        name = str(a.get("name", ""))
        m = re.match(r"^patch_(.+?)_to_(.+?)\.(?:bin|patch)$", name, re.I)
        if not m:
            continue
        if parse_version(m.group(1)) != local:
            continue
        size = a.get("size", 0) or 0
        cand = {"url": a.get("browser_download_url", ""),
                "size": size, "name": name,
                "to": m.group(2)}
        if best is None or (cand["size"] and cand["size"] < best["size"]):
            best = cand
    return best


def check_for_update(apis, local_version):
    """返回 (available: bool, info: dict)。

    apis 可以是单个 API 地址或列表：依次尝试，第一个成功的为准。
    info 字段：version、name、size、url、patch_url、patch_size、error。
    发布里如果有匹配当前版本的增量补丁，patch_url 非空，客户端只下补丁。
    """
    info = {"version": "", "name": "", "size": 0, "url": "",
            "patch_url": "", "patch_size": 0, "error": ""}
    if isinstance(apis, str):
        apis = [apis]
    data = None
    errors = []
    for api in apis or []:
        try:
            data = _fetch_latest(api)
            break
        except urllib.error.HTTPError as e:
            errors.append("%d" % e.code)
        except Exception as e:
            errors.append(str(e))
    if data is None:
        info["error"] = "检查更新失败：%s" % ("；".join(errors) or "网络不可用")
        return False, info

    tag = (data.get("tag_name") or "").strip()
    assets = data.get("assets") or []
    exe = [a for a in assets if str(a.get("name", "")).lower().endswith(".exe")]
    if not exe:
        info["error"] = "最新发布里没有找到 exe 安装包"
        return False, info
    info["version"] = tag
    info["name"] = exe[0].get("name", "")
    info["size"] = exe[0].get("size", 0) or 0
    info["url"] = exe[0].get("browser_download_url", "")
    # Gitee 的 Release 资产经常不返回 size 字段（为 None），
    # 这里用下载直链补探一次真实的 Content-Length，让确认框显示准确体积。
    if not info["size"] and info["url"]:
        info["size"] = probe_size(info["url"])

    patch = _pick_patch(assets, local_version)
    if patch and parse_version(patch.get("to")) == parse_version(tag):
        info["patch_url"] = patch["url"]
        info["patch_size"] = patch["size"] or probe_size(patch["url"])

    # 按版本号大小比对：远程更大才算有升级
    try:
        available = parse_version(tag) > parse_version(local_version)
    except Exception:
        available = False
    return available, info


def download_file(dl_url, dest_path, on_progress=None):
    """下载任意发布资产到 dest_path（.new/.patch 临时名）。

    on_progress(got, total) 在下载过程中回调，total 可能为 0（未知大小）。
    """
    req = urllib.request.Request(
        dl_url, headers={"User-Agent": _UA,
                         "Accept": "application/octet-stream"})
    with urllib.request.urlopen(req, context=_ctx(), timeout=300) as r:
        total = int(r.headers.get("Content-Length", "0") or 0)
        with open(dest_path, "wb") as f:
            got = 0
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if on_progress:
                    on_progress(got, total)
    return dest_path


download_exe = download_file


def make_updater_script(target_exe, new_exe):
    """写一个 VBS：等本程序退出（源文件解锁）后，把 new_exe 覆盖到
    target_exe，再启动新的 exe。返回脚本路径。

    用 VBScript 而不是 bat：脚本以 UTF-16LE 保存，中文/空格路径不会被
    控制台代码页搞乱，也不会闪黑框。循环重试是必要的 —— 旧 exe 还占着
    文件时复制会失败，进程退出后才能写入。
    """
    d = os.path.dirname(target_exe) or "."
    script = os.path.join(d, "update_helper.vbs")
    log = os.path.join(d, "update_helper.log")

    def vb(s):
        return '"%s"' % s.replace('"', '""')

    content = (
        'Set fso = CreateObject("Scripting.FileSystemObject")\r\n'
        'Set sh = CreateObject("WScript.Shell")\r\n'
        'newFile = %s\r\n' % vb(new_exe) +
        'tgt = %s\r\n' % vb(target_exe) +
        'ok = False\r\n'
        'For i = 1 To 120\r\n'
        '  On Error Resume Next\r\n'
        '  fso.CopyFile newFile, tgt, True\r\n'
        '  If Err.Number = 0 Then\r\n'
        '    ok = True\r\n'
        '    Err.Clear\r\n'
        '    Exit For\r\n'
        '  End If\r\n'
        '  Err.Clear\r\n'
        '  On Error GoTo 0\r\n'
        '  WScript.Sleep 1000\r\n'
        'Next\r\n'
        'On Error GoTo 0\r\n'
        'If ok Then\r\n'
        '  On Error Resume Next\r\n'
        '  fso.DeleteFile newFile, True\r\n'
        '  On Error GoTo 0\r\n'
        'Else\r\n'
        '  On Error Resume Next\r\n'
        '  Set lg = fso.OpenTextFile(%s, 8, True)\r\n' % vb(log) +
        '  lg.WriteLine Now & " 更新失败：无法覆盖 " & tgt\r\n'
        '  lg.Close\r\n'
        '  On Error GoTo 0\r\n'
        'End If\r\n'
        'sh.Run """" & tgt & """", 1, False\r\n'
    )
    with open(script, "w", encoding="utf-16") as f:
        f.write(content)
    return script
